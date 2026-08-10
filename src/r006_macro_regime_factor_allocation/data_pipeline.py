"""m1：A 股市场迁移数据底座与时点安全。

稳定数据合同围绕四条红线组织：

1. 财务字段只通过 ``info_publ_date <= signal_date`` 的 as-of 连接进入信号；
2. 宏观值的可用日取真实披露日与 AS16 固定保守滞后的较晚者；
3. T 月末信号的执行日必须是严格晚于 T 的首个交易日；
4. walk-forward 只允许 expanding 训练、固定 144 月验证和逐年冻结预测。

模块支持只读 schema/dry-run。正式因子文件缺失、布局不明确或基准指数代码未配置时
会清晰失败，绝不自动生成 synthetic 数据。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Sequence
import unicodedata

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from common.data_loader import (
    load_limit_status,
    load_st_data,
    load_stock_price_forward,
    load_suspend_status,
    load_trade_calendar,
)

from .config import (
    DEFAULT_CONFIG,
    MacroSeriesSpec,
    R006M1Config,
    SourceSpec,
)


class DataContractError(ValueError):
    """输入字段、时点或窗口不满足 m1 合同。"""


class FormalDataUnavailableError(FileNotFoundError):
    """正式数据缺失；调用方不得用 synthetic 数据替代。"""


@dataclass(frozen=True)
class SourceAuditResult:
    """本地源文件、字段和覆盖盘点结果。"""

    files: pd.DataFrame
    fields: pd.DataFrame
    issues: tuple[str, ...]

    @property
    def formal_ready(self) -> bool:
        """是否未发现阻断正式构建的数据合同问题。"""
        return not self.issues


@dataclass(frozen=True)
class FactorCrosswalkResult:
    """AS26 一对一家族交叉表、汇总与冻结哈希。"""

    table: pd.DataFrame
    summary: pd.DataFrame
    sha256: str


@dataclass(frozen=True)
class FactorAlignmentResult:
    """因子源观测到正式月末信号日的对齐表与 PIT 审计。"""

    table: pd.DataFrame
    audit: pd.DataFrame


@dataclass(frozen=True)
class FrozenFactorDirections:
    """一个预测周期只由训练期估计并冻结的逐因子方向。"""

    table: pd.DataFrame
    sha256: str
    crosswalk_sha256: str
    window_id: str
    prediction_year: int
    prediction_start: pd.Timestamp
    prediction_end: pd.Timestamp
    train_start: pd.Timestamp
    train_end: pd.Timestamp


@dataclass(frozen=True)
class CommonMonthResult:
    """真实共同月索引及逐候选月八块可用性诊断。"""

    month_index: pd.DatetimeIndex
    diagnostics: pd.DataFrame


@dataclass(frozen=True)
class SA11SensitivityResult:
    """SA11 五条同样本收益路径、比较汇总与滚动暴露审计。"""

    returns: pd.DataFrame
    summary: pd.DataFrame
    exposure_audit: pd.DataFrame


@dataclass(frozen=True)
class M1Dataset:
    """供 m2-m5 稳定消费的 m1 数据合同。"""

    source_audit: SourceAuditResult
    substitution_manifest: pd.DataFrame
    factor_crosswalk: FactorCrosswalkResult
    factor_panel: pd.DataFrame
    factor_availability: pd.DataFrame
    fixed_factor_universe: tuple[str, ...]
    publication_coverage: pd.DataFrame
    execution_schedule: pd.DataFrame
    monthly_stock_panel: pd.DataFrame
    financial_pit_panel: pd.DataFrame
    macro_inputs: pd.DataFrame
    macro_asof: pd.DataFrame
    index_state_inputs: pd.DataFrame
    capacity_control_panel: pd.DataFrame
    common_month_index: pd.DatetimeIndex
    common_month_diagnostics: pd.DataFrame
    walk_forward_windows: pd.DataFrame
    point_in_time_audit: pd.DataFrame
    issues: tuple[str, ...]
    dry_run: bool


def _source_by_key(config: R006M1Config) -> dict[str, SourceSpec]:
    """按 key 索引集中配置的数据源。"""
    return {spec.key: spec for spec in config.source_specs}


def _stat_to_text(value: Any, config: R006M1Config) -> str:
    """把 parquet 统计值规范化为可稳定写入审计表的文本。"""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(config.hash_encoding, errors="replace")
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).strftime(config.coverage_date_format)
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _column_statistics(
    parquet_file: pq.ParquetFile,
    column: str,
    config: R006M1Config,
) -> tuple[int | None, float | None, str, str]:
    """只读 row-group metadata 汇总列缺失率与覆盖；不扫描大文件。"""
    names = parquet_file.schema_arrow.names
    if column not in names:
        return None, None, "", ""
    column_index = parquet_file.schema_arrow.get_field_index(column)
    null_counts: list[int] = []
    minima: list[Any] = []
    maxima: list[Any] = []
    all_have_null_counts = True
    for row_group_index in range(parquet_file.metadata.num_row_groups):
        statistics = parquet_file.metadata.row_group(row_group_index).column(
            column_index
        ).statistics
        if statistics is None:
            all_have_null_counts = False
            continue
        if statistics.null_count is None:
            all_have_null_counts = False
        else:
            null_counts.append(int(statistics.null_count))
        if statistics.has_min_max:
            minima.append(statistics.min)
            maxima.append(statistics.max)
    null_count = sum(null_counts) if all_have_null_counts else None
    missing_rate = (
        null_count / parquet_file.metadata.num_rows
        if null_count is not None and parquet_file.metadata.num_rows
        else None
    )
    minimum = _stat_to_text(min(minima), config) if minima else ""
    maximum = _stat_to_text(max(maxima), config) if maxima else ""
    return null_count, missing_rate, minimum, maximum


def audit_local_sources(
    config: R006M1Config = DEFAULT_CONFIG,
) -> SourceAuditResult:
    """真实盘点配置指向的本地文件、字段、行数、缺失率和日期覆盖。

    parquet 只读取 footer metadata；目录只枚举实际 ``*.parquet`` 文件。
    ``factors/`` 为空会登记为 formal 阻断项，但不会影响 dry-run 继续生成元数据交叉表。
    """
    file_rows: list[dict[str, Any]] = []
    field_rows: list[dict[str, Any]] = []
    issues: list[str] = []
    for spec in config.source_specs:
        path = config.data_root / spec.relative_path
        if spec.kind == "directory":
            files = (
                sorted(path.rglob(f"*{config.factor_file_suffix}"))
                if path.is_dir()
                else []
            )
            status = "available" if files else "missing"
            file_rows.append(
                {
                    "source_key": spec.key,
                    "path": str(path),
                    "kind": spec.kind,
                    "status": status,
                    "row_count": pd.NA,
                    "column_count": pd.NA,
                    "factor_file_count": len(files),
                    "coverage": "",
                }
            )
            if spec.required_for_formal and len(files) < config.formal_factor_min_files:
                issues.append(
                    f"{spec.key}: {path} 中实际因子 parquet 数量 "
                    f"{len(files)} < {config.formal_factor_min_files}"
                )
            continue

        if not path.is_file():
            file_rows.append(
                {
                    "source_key": spec.key,
                    "path": str(path),
                    "kind": spec.kind,
                    "status": "missing",
                    "row_count": pd.NA,
                    "column_count": pd.NA,
                    "factor_file_count": pd.NA,
                    "coverage": "",
                }
            )
            if spec.required_for_formal:
                issues.append(f"{spec.key}: 缺少文件 {path}")
            continue

        parquet_file = pq.ParquetFile(path)
        schema_columns = tuple(parquet_file.schema_arrow.names)
        required = set(spec.required_columns)
        missing_columns = sorted(required.difference(schema_columns))
        coverage: dict[str, dict[str, str]] = {}
        audit_columns = sorted(set(schema_columns).union(required))
        for column in audit_columns:
            exists = column in schema_columns
            null_count, missing_rate, minimum, maximum = _column_statistics(
                parquet_file, column, config
            )
            field_rows.append(
                {
                    "source_key": spec.key,
                    "path": str(path),
                    "field": column,
                    "required": column in required,
                    "exists": exists,
                    "null_count": null_count if null_count is not None else pd.NA,
                    "missing_rate": (
                        missing_rate if missing_rate is not None else np.nan
                    ),
                    "coverage_start": minimum,
                    "coverage_end": maximum,
                }
            )
            if column in spec.coverage_columns and exists:
                coverage[column] = {"start": minimum, "end": maximum}
        status = "available" if not missing_columns else "schema_mismatch"
        file_rows.append(
            {
                "source_key": spec.key,
                "path": str(path),
                "kind": spec.kind,
                "status": status,
                "row_count": parquet_file.metadata.num_rows,
                "column_count": len(schema_columns),
                "factor_file_count": pd.NA,
                "coverage": json.dumps(
                    coverage, ensure_ascii=False, sort_keys=True
                ),
            }
        )
        if spec.required_for_formal and missing_columns:
            issues.append(f"{spec.key}: 缺少必需字段 {missing_columns}")
    return SourceAuditResult(
        files=pd.DataFrame(file_rows),
        fields=pd.DataFrame(field_rows),
        issues=tuple(issues),
    )


def assert_formal_sources_available(audit: SourceAuditResult) -> None:
    """正式构建前阻断任何缺文件、空因子目录或字段不匹配。"""
    if audit.issues:
        details = "\n- ".join(audit.issues)
        raise FormalDataUnavailableError(
            "r006 m1 正式数据合同不满足，禁止自动 synthetic：\n- " + details
        )


def build_substitution_manifest(
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """固化 D1-D10 的原对象、A 股替代、理由、假设与源文件映射。"""
    sources = _source_by_key(config)
    rows = []
    for item in config.substitutes:
        configured_usage = dict(item.source_usage)
        rows.append(
            {
                "element_id": item.element_id,
                "status": "substitute",
                "original_data": item.original_data,
                "local_substitute": item.local_substitute,
                "reason": item.reason,
                "assumptions": ",".join(item.assumptions),
                "source_keys": ",".join(item.source_keys),
                "source_paths": ";".join(
                    str(config.data_root / sources[key].relative_path)
                    for key in item.source_keys
                ),
                "source_usage": json.dumps(
                    {
                        key: configured_usage.get(key, "direct_or_audit")
                        for key in item.source_keys
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        )
    return pd.DataFrame(rows)


def _normalize_mapping_text(value: Any) -> str:
    """按 AS26：NFKC、小写、去空白和标点。"""
    if pd.isna(value):
        return ""
    normalized = unicodedata.normalize("NFKC", str(value)).lower()
    return "".join(
        char
        for char in normalized
        if not unicodedata.category(char).startswith(("P", "Z"))
    )


def _keyword_matches(
    value: Any,
    keyword: str,
    config: R006M1Config,
) -> bool:
    """匹配 AS26 关键词；英文短词只按完整 token 匹配。"""
    if pd.isna(value):
        return False
    raw = unicodedata.normalize("NFKC", str(value)).lower()
    keyword_lower = unicodedata.normalize("NFKC", keyword).lower()
    if keyword_lower in config.short_english_keywords:
        pattern = rf"(?<![a-z0-9]){re.escape(keyword_lower)}(?![a-z0-9])"
        return re.search(pattern, raw) is not None
    return _normalize_mapping_text(keyword_lower) in _normalize_mapping_text(raw)


def _crosswalk_hash_payload(
    table: pd.DataFrame,
    config: R006M1Config,
) -> bytes:
    """构造包含关键词配置与逐因子归属的稳定哈希载荷。"""
    columns = (
        "factor_id",
        "family",
        "matched_field",
        "matched_keyword",
        "mapping_status",
    )
    records = (
        table.loc[:, columns]
        .fillna("")
        .sort_values("factor_id", kind="stable")
        .to_dict(orient="records")
    )
    payload = {
        "field_priority": config.family_field_priority,
        "family_order": config.family_order,
        "family_keywords": config.family_keywords,
        "records": records,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode(config.hash_encoding)


def build_factor_crosswalk(
    factor_metadata: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
    *,
    strict: bool = True,
) -> FactorCrosswalkResult:
    """按 AS26 固定优先级/最长词/家族顺序生成一对一家族映射。

    未命中因子保留在审计表但不进入袖套。``strict=True`` 时，重复 factor_id、
    空家族或一对多归属会清晰失败。
    """
    required = {"factor_id", *config.family_field_priority}
    missing = sorted(required.difference(factor_metadata.columns))
    if missing:
        raise DataContractError(f"因子元数据缺少字段: {missing}")
    metadata_columns = list(
        dict.fromkeys(["factor_id", *config.family_field_priority])
    )
    metadata = factor_metadata.loc[:, metadata_columns].copy()
    metadata["factor_id"] = metadata["factor_id"].astype(str)
    if metadata["factor_id"].duplicated().any():
        duplicates = sorted(
            metadata.loc[metadata["factor_id"].duplicated(False), "factor_id"].unique()
        )
        raise DataContractError(f"因子元数据 factor_id 重复: {duplicates[:10]}")

    family_rank = {family: rank for rank, family in enumerate(config.family_order)}
    rows: list[dict[str, Any]] = []
    for record in metadata.to_dict(orient="records"):
        field_trace: list[dict[str, Any]] = []
        chosen_field = ""
        chosen_matches: list[tuple[str, str]] = []
        for field_name in config.family_field_priority:
            matches = [
                (family, keyword)
                for family, keywords in config.family_keywords
                for keyword in keywords
                if _keyword_matches(record[field_name], keyword, config)
            ]
            field_trace.append(
                {
                    "field": field_name,
                    "value": "" if pd.isna(record[field_name]) else str(record[field_name]),
                    "matches": [
                        {"family": family, "keyword": keyword}
                        for family, keyword in matches
                    ],
                }
            )
            if matches and not chosen_matches:
                chosen_field = field_name
                chosen_matches = matches
        if chosen_matches:
            ordered = sorted(
                chosen_matches,
                key=lambda item: (
                    -len(_normalize_mapping_text(item[1])),
                    family_rank[item[0]],
                    _normalize_mapping_text(item[1]),
                ),
            )
            family, keyword = ordered[0]
            status = "mapped"
        else:
            family, keyword, status = "", "", "unmapped"
        rows.append(
            {
                **record,
                "family": family,
                "mapping_status": status,
                "matched_field": chosen_field,
                "matched_keyword": keyword,
                "selected_field_match_count": len(chosen_matches),
                "selected_field_family_count": len(
                    {item[0] for item in chosen_matches}
                ),
                "multiple_match": len(chosen_matches) > 1,
                "match_trace": json.dumps(
                    field_trace, ensure_ascii=False, sort_keys=True
                ),
            }
        )
    table = pd.DataFrame(rows).sort_values("factor_id", kind="stable").reset_index(
        drop=True
    )
    digest = hashlib.new(config.crosswalk_hash_algorithm)
    digest.update(_crosswalk_hash_payload(table, config))
    sha256 = digest.hexdigest()
    table["crosswalk_sha256"] = sha256

    counts = (
        table.loc[table["mapping_status"].eq("mapped"), "family"]
        .value_counts()
        .reindex(config.family_order, fill_value=0)
    )
    summary_rows = [
        {"metric": "total_factors", "value": len(table)},
        {
            "metric": "mapped_factors",
            "value": int(table["mapping_status"].eq("mapped").sum()),
        },
        {
            "metric": "unmapped_factors",
            "value": int(table["mapping_status"].eq("unmapped").sum()),
        },
        {
            "metric": "multiple_match_factors",
            "value": int(table["multiple_match"].sum()),
        },
        *[
            {"metric": f"family::{family}", "value": int(counts[family])}
            for family in config.family_order
        ],
        {"metric": "crosswalk_sha256", "value": sha256},
    ]
    summary = pd.DataFrame(summary_rows)
    result = FactorCrosswalkResult(table=table, summary=summary, sha256=sha256)
    if strict:
        validate_factor_crosswalk(result, config)
    return result


def validate_factor_crosswalk(
    result: FactorCrosswalkResult,
    config: R006M1Config = DEFAULT_CONFIG,
) -> None:
    """执行 AS26 的一对一、非空家族与哈希可重算约束。"""
    table = result.table
    if table["factor_id"].duplicated().any():
        raise DataContractError("家族交叉表存在重复 factor_id")
    mapped = table.loc[table["mapping_status"].eq("mapped")]
    counts = mapped["family"].value_counts()
    empty_families = [
        family for family in config.family_order if int(counts.get(family, 0)) == 0
    ]
    if empty_families:
        raise DataContractError(f"AS26 家族为空: {empty_families}")
    if not mapped["family"].isin(config.family_order).all():
        raise DataContractError("家族交叉表出现配置外家族")
    digest = hashlib.new(config.crosswalk_hash_algorithm)
    digest.update(_crosswalk_hash_payload(table, config))
    if digest.hexdigest() != result.sha256:
        raise DataContractError("家族交叉表 SHA-256 无法重复生成")


def discover_factor_files(
    config: R006M1Config = DEFAULT_CONFIG,
) -> tuple[Path, ...]:
    """列出 ``factors/`` 下实际 parquet；空目录不伪造文件。"""
    factor_spec = _source_by_key(config)["factor_panel_dir"]
    directory = config.data_root / factor_spec.relative_path
    if not directory.is_dir():
        return ()
    return tuple(sorted(directory.rglob(f"*{config.factor_file_suffix}")))


def load_local_factor_panel(
    factor_metadata: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
    *,
    files: Sequence[Path] | None = None,
) -> pd.DataFrame:
    """加载实际本地因子文件并统一为长表。

    明确支持三种可审计布局：含 ``factor_id`` 的长表；文件名等于 factor_id 的
    单因子表；字段名等于元数据 factor_id 的宽表。其他布局直接失败，不猜测数值列。
    """
    factor_files = tuple(files) if files is not None else discover_factor_files(config)
    if not factor_files:
        raise FormalDataUnavailableError(
            f"{config.data_root / 'factors'} 中没有实际 parquet；禁止 synthetic"
        )
    known_factors = set(factor_metadata["factor_id"].astype(str))
    frames: list[pd.DataFrame] = []
    for path in factor_files:
        parquet_file = pq.ParquetFile(path)
        columns = set(parquet_file.schema_arrow.names)
        date_column = next(
            (
                column
                for column in (config.source_date_key, config.signal_date_key)
                if column in columns
            ),
            None,
        )
        if config.stock_key not in columns or date_column is None:
            raise DataContractError(
                f"因子文件缺 stock_code/date 合同字段: {path}"
            )
        value_column = next(
            (column for column in config.factor_value_candidates if column in columns),
            None,
        )
        if "factor_id" in columns and value_column is not None:
            frame = pd.read_parquet(
                path,
                columns=[
                    config.stock_key,
                    date_column,
                    "factor_id",
                    value_column,
                ],
            ).rename(
                columns={
                    date_column: "source_date",
                    value_column: "factor_value",
                }
            )
        else:
            wide_factors = sorted(known_factors.intersection(columns))
            if wide_factors:
                wide = pd.read_parquet(
                    path,
                    columns=[config.stock_key, date_column, *wide_factors],
                ).rename(columns={date_column: "source_date"})
                frame = wide.melt(
                    id_vars=[config.stock_key, "source_date"],
                    value_vars=wide_factors,
                    var_name="factor_id",
                    value_name="factor_value",
                )
            elif path.stem in known_factors and (
                value_column is not None or path.stem in columns
            ):
                single_value = value_column or path.stem
                frame = pd.read_parquet(
                    path,
                    columns=[config.stock_key, date_column, single_value],
                ).rename(
                    columns={
                        date_column: "source_date",
                        single_value: "factor_value",
                    }
                )
                frame["factor_id"] = path.stem
            else:
                raise DataContractError(
                    f"因子文件布局不属于已登记三种合同，拒绝猜测: {path}"
                )
        frame["source_file"] = str(path)
        frame["source_date_semantics"] = (
            "explicit_signal_date"
            if date_column == config.signal_date_key
            else "observation_date"
        )
        frames.append(frame)

    panel = pd.concat(frames, ignore_index=True)
    panel[config.stock_key] = panel[config.stock_key].astype(str).str.zfill(6)
    panel["source_date"] = pd.to_datetime(
        panel["source_date"], errors="coerce"
    ).dt.normalize()
    panel["factor_id"] = panel["factor_id"].astype(str)
    panel["factor_value"] = pd.to_numeric(panel["factor_value"], errors="coerce")
    if panel[[config.stock_key, "source_date", "factor_id"]].isna().any(
        axis=None
    ):
        raise DataContractError("因子面板存在不可解析 stock_code/date/factor_id")
    keys = [config.stock_key, "source_date", "factor_id"]
    duplicated = panel.duplicated(keys, keep=False)
    if duplicated.any():
        conflicts = (
            panel.loc[duplicated]
            .groupby(keys, observed=True)["factor_value"]
            .nunique(dropna=False)
        )
        if conflicts.gt(1).any():
            raise DataContractError("因子面板同一 stock-source_date-factor 存在冲突值")
        panel = panel.drop_duplicates(keys, keep="last")
    panel[config.source_date_key] = panel["source_date"]
    return panel.sort_values(keys, kind="stable").reset_index(drop=True)


def align_factor_panel_to_schedule(
    factor_panel: pd.DataFrame,
    execution_schedule: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
    *,
    strict: bool = True,
) -> FactorAlignmentResult:
    """把正式因子源观测映射到同月交易月末信号日并生成 PIT 审计。

    普通 ``observation_date`` 取同一股票-月-因子的最后一条已知观测；声明为
    ``explicit_signal_date`` 的布局必须与交易日历的正式 signal_date 精确相等。
    """
    required_factor = {
        config.stock_key,
        "source_date",
        "source_date_semantics",
        "factor_id",
        "factor_value",
    }
    required_schedule = {
        "signal_month",
        config.signal_date_key,
        "execution_date",
    }
    missing_factor = sorted(required_factor.difference(factor_panel.columns))
    missing_schedule = sorted(required_schedule.difference(execution_schedule.columns))
    if missing_factor:
        raise DataContractError(f"factor_panel 缺少 PIT 字段: {missing_factor}")
    if missing_schedule:
        raise DataContractError(f"execution_schedule 缺少字段: {missing_schedule}")

    panel = factor_panel.copy()
    panel["source_date"] = pd.to_datetime(
        panel["source_date"], errors="coerce"
    ).dt.normalize()
    panel["source_month"] = panel["source_date"].dt.to_period(
        config.schedule_month_frequency
    )
    schedule = execution_schedule[
        ["signal_month", config.signal_date_key, "execution_date"]
    ].drop_duplicates("signal_month")
    panel = panel.merge(
        schedule,
        left_on="source_month",
        right_on="signal_month",
        how="left",
        validate="many_to_one",
    )
    mapped = panel[config.signal_date_key].notna()
    source_not_after = mapped & panel["source_date"].le(
        panel[config.signal_date_key]
    )
    explicit = panel["source_date_semantics"].eq("explicit_signal_date")
    explicit_exact = ~explicit | (
        mapped & panel["source_date"].eq(panel[config.signal_date_key])
    )
    audit_rows = [
        {
            "check": "factor_source_month_maps_to_schedule",
            "observations": len(panel),
            "violations": int((~mapped).sum()),
        },
        {
            "check": "factor_source_date_not_after_signal",
            "observations": int(mapped.sum()),
            "violations": int((mapped & ~source_not_after).sum()),
        },
        {
            "check": "explicit_factor_signal_date_exact",
            "observations": int(explicit.sum()),
            "violations": int((explicit & ~explicit_exact).sum()),
        },
    ]
    invalid = ~mapped | ~source_not_after | ~explicit_exact
    if strict and invalid.any():
        raise DataContractError(
            "正式因子时点语义无法证明："
            f"unmapped={int((~mapped).sum())}, "
            f"source_after_signal={int((mapped & ~source_not_after).sum())}, "
            f"explicit_not_exact={int((explicit & ~explicit_exact).sum())}"
        )
    valid = panel.loc[~invalid].copy()
    source_keys = [
        config.stock_key,
        config.signal_date_key,
        "factor_id",
        "source_date",
    ]
    duplicate_source = valid.duplicated(source_keys, keep=False)
    if duplicate_source.any():
        conflicts = (
            valid.loc[duplicate_source]
            .groupby(source_keys, observed=True)["factor_value"]
            .nunique(dropna=False)
        )
        if conflicts.gt(1).any():
            raise DataContractError(
                "同一 stock-signal-factor-source_date 存在冲突值"
            )
        valid = valid.drop_duplicates(source_keys, keep="last")
    monthly_keys = [config.stock_key, config.signal_date_key, "factor_id"]
    valid = (
        valid.sort_values([*monthly_keys, "source_date"], kind="stable")
        .drop_duplicates(monthly_keys, keep="last")
        .sort_values(monthly_keys, kind="stable")
        .reset_index(drop=True)
    )
    duplicate_monthly = valid.duplicated(monthly_keys).sum()
    audit_rows.append(
        {
            "check": "factor_stock_month_factor_unique",
            "observations": len(valid),
            "violations": int(duplicate_monthly),
        }
    )
    if strict and duplicate_monthly:
        raise DataContractError("正式因子 stock-month-factor 不唯一")
    valid[config.source_date_key] = valid["source_date"]
    return FactorAlignmentResult(
        table=valid,
        audit=pd.DataFrame(audit_rows),
    )


def compute_factor_availability(
    factor_panel: pd.DataFrame,
    crosswalk: FactorCrosswalkResult,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """统计每个本地因子的首次/末次非缺失月，作为 D10 替代审计。"""
    date_column = (
        config.signal_date_key
        if config.signal_date_key in factor_panel.columns
        else config.source_date_key
    )
    required = {date_column, "factor_id", "factor_value"}
    missing = sorted(required.difference(factor_panel.columns))
    if missing:
        raise DataContractError(f"因子面板缺少可用性字段: {missing}")
    valid = factor_panel.loc[
        factor_panel["factor_value"].notna(),
        ["factor_id", date_column],
    ].copy()
    valid["month"] = (
        pd.to_datetime(valid[date_column])
        .dt.to_period(config.schedule_month_frequency)
        .dt.to_timestamp(config.schedule_month_frequency)
    )
    availability = (
        valid.groupby("factor_id", observed=True)["month"]
        .agg(first_available_month="min", last_available_month="max", observations="size")
        .reset_index()
    )
    mapping = crosswalk.table[
        ["factor_id", "family", "mapping_status", "crosswalk_sha256"]
    ]
    return mapping.merge(availability, on="factor_id", how="left", validate="one_to_one")


def build_publication_year_coverage(
    factor_availability: pd.DataFrame,
    prediction_years: Iterable[int],
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """按 AS10/F16 生成“首次可用年 <= Y-1”的本地覆盖曲线。"""
    years = pd.DataFrame(
        {"prediction_year": sorted({int(year) for year in prediction_years})}
    )
    available = factor_availability.loc[
        factor_availability["first_available_month"].notna()
    ].copy()
    if years.empty:
        return pd.DataFrame(
            columns=[
                "prediction_year",
                "eligible_signals",
                "share_of_local_universe",
                *config.family_order,
            ]
        )
    if available.empty:
        result = years.assign(
            eligible_signals=0,
            share_of_local_universe=0.0,
        )
        return result.assign(**{family: 0 for family in config.family_order})
    available["first_available_year"] = pd.to_datetime(
        available["first_available_month"]
    ).dt.year
    eligible = years.merge(available, how="cross")
    eligible = eligible.loc[
        eligible["first_available_year"] <= eligible["prediction_year"] - 1
    ]
    family_counts = (
        eligible.loc[eligible["mapping_status"].eq("mapped")]
        .pivot_table(
            index="prediction_year",
            columns="family",
            values="factor_id",
            aggfunc="nunique",
            fill_value=0,
        )
        .reindex(columns=config.family_order, fill_value=0)
    )
    totals = eligible.groupby("prediction_year")["factor_id"].nunique()
    result = years.set_index("prediction_year").join(
        totals.rename("eligible_signals")
    ).join(family_counts)
    result["eligible_signals"] = result["eligible_signals"].fillna(0).astype(int)
    for family in config.family_order:
        result[family] = result[family].fillna(0).astype(int)
    universe_size = int(available["factor_id"].nunique())
    result["share_of_local_universe"] = (
        result["eligible_signals"] / universe_size if universe_size else 0.0
    )
    return result.reset_index()


def freeze_main_factor_universe(
    factor_availability: pd.DataFrame,
    common_start_month: pd.Timestamp,
) -> tuple[str, ...]:
    """按 AS20 冻结共同起点前已实际可用的主测试因子集。"""
    cutoff = pd.Timestamp(common_start_month).to_period("M").to_timestamp("M")
    selected = factor_availability.loc[
        factor_availability["first_available_month"].notna()
        & (
            pd.to_datetime(factor_availability["first_available_month"])
            <= cutoff
        ),
        "factor_id",
    ]
    return tuple(sorted(selected.astype(str).unique()))


def build_execution_schedule(
    trade_calendar: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """构造 T 月末信号、T+1 首个交易日与下一信号日的严格执行日历。"""
    required = {"date", "IfTradingDay", "IfMonthEnd"}
    missing = sorted(required.difference(trade_calendar.columns))
    if missing:
        raise DataContractError(f"交易日历缺少字段: {missing}")
    calendar = trade_calendar.copy()
    calendar["date"] = pd.to_datetime(calendar["date"], errors="coerce").dt.normalize()
    calendar = (
        calendar.loc[calendar["IfTradingDay"].eq(1)]
        .dropna(subset=["date"])
        .drop_duplicates("date")
        .sort_values("date")
    )
    trading_dates = calendar["date"].to_numpy(dtype="datetime64[ns]")
    signals = (
        calendar.loc[calendar["IfMonthEnd"].eq(1), ["date"]]
        .drop_duplicates()
        .rename(columns={"date": config.signal_date_key})
        .sort_values(config.signal_date_key)
        .reset_index(drop=True)
    )
    positions = np.searchsorted(
        trading_dates,
        signals[config.signal_date_key].to_numpy(dtype="datetime64[ns]"),
        side="right",
    )
    has_execution = positions < len(trading_dates)
    signals = signals.loc[has_execution].copy()
    positions = positions[has_execution]
    signals["execution_date"] = pd.to_datetime(trading_dates[positions])
    signals["signal_month"] = signals[config.signal_date_key].dt.to_period("M")
    signals["next_signal_date"] = signals[config.signal_date_key].shift(-1)
    if not (
        signals["execution_date"] > signals[config.signal_date_key]
    ).all():
        raise DataContractError("执行日必须严格晚于信号日")
    return signals[
        [
            "signal_month",
            config.signal_date_key,
            "execution_date",
            "next_signal_date",
        ]
    ].reset_index(drop=True)


def _interval_flag(
    keys: pd.DataFrame,
    intervals: pd.DataFrame,
    *,
    date_column: str,
    start_column: str,
    end_column: str,
    stock_column: str,
) -> pd.Series:
    """向量化标记股票日期是否落入半开状态区间。"""
    if intervals.empty:
        return pd.Series(False, index=keys.index)
    left = keys[[stock_column, date_column]].copy()
    left["_row_id"] = np.arange(len(left))
    right = intervals[[stock_column, start_column, end_column]].copy()
    right[start_column] = pd.to_datetime(right[start_column], errors="coerce")
    right[end_column] = pd.to_datetime(right[end_column], errors="coerce")
    joined = left.merge(right, on=stock_column, how="left")
    active = joined[
        joined[start_column].le(joined[date_column])
        & (
            joined[end_column].gt(joined[date_column])
            | joined[end_column].isna()
        )
    ]["_row_id"].unique()
    return pd.Series(left["_row_id"].isin(active).to_numpy(), index=keys.index)


def build_monthly_stock_panel(
    price: pd.DataFrame,
    trade: pd.DataFrame,
    stock_master: pd.DataFrame,
    trade_calendar: pd.DataFrame,
    *,
    st_data: pd.DataFrame | None = None,
    suspend_status: pd.DataFrame | None = None,
    limit_status: pd.DataFrame | None = None,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """由前复权行情与交易字段构造 PIT 股票月面板及 T+1 可交易标记。"""
    price_required = {config.stock_key, "date", "close"}
    trade_required = {
        config.stock_key,
        "date",
        "market_value",
        "negotiable_market_value",
        "turn_value",
        "turnover_rate_free",
    }
    master_required = {config.stock_key, "list_date"}
    for name, frame, required in (
        ("price", price, price_required),
        ("trade", trade, trade_required),
        ("stock_master", stock_master, master_required),
    ):
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise DataContractError(f"{name} 缺少字段: {missing}")

    price_columns = [
        config.stock_key,
        "date",
        "close",
        *(["open"] if "open" in price.columns else []),
    ]
    daily = price[price_columns].merge(
        trade[
            [
                config.stock_key,
                "date",
                "market_value",
                "negotiable_market_value",
                "turn_value",
                "turnover_rate_free",
            ]
        ],
        on=[config.stock_key, "date"],
        how="inner",
        validate="one_to_one",
    )
    daily[config.stock_key] = daily[config.stock_key].astype(str).str.zfill(6)
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce").dt.normalize()
    daily = daily.dropna(subset=["date"]).sort_values(
        [config.stock_key, "date"], kind="stable"
    )
    daily["signal_month"] = daily["date"].dt.to_period("M")
    aggregation: dict[str, tuple[str, str]] = {
        "last_observation_date": ("date", "last"),
        "close": ("close", "last"),
        "market_value": ("market_value", "last"),
        "negotiable_market_value": ("negotiable_market_value", "last"),
        "turn_value_month": ("turn_value", "sum"),
        "turnover_rate_free_month": ("turnover_rate_free", "sum"),
    }
    if "open" in daily.columns:
        aggregation["open"] = ("open", "last")
    monthly = (
        daily.groupby([config.stock_key, "signal_month"], observed=True)
        .agg(**aggregation)
        .reset_index()
        .sort_values([config.stock_key, "signal_month"], kind="stable")
    )
    grouped = monthly.groupby(config.stock_key, observed=True)
    monthly["prior_close"] = grouped["close"].shift(1)
    monthly["prior_month"] = grouped["signal_month"].shift(1)
    monthly["month_return"] = (
        monthly["close"] / monthly["prior_close"] - 1.0
    ).where(monthly["prior_month"].eq(monthly["signal_month"] - 1))

    schedule = build_execution_schedule(trade_calendar, config)
    monthly = monthly.merge(
        schedule,
        on="signal_month",
        how="inner",
        validate="many_to_one",
    )
    master = stock_master[[config.stock_key, "list_date"]].copy()
    master[config.stock_key] = master[config.stock_key].astype(str).str.zfill(6)
    master["list_date"] = pd.to_datetime(master["list_date"], errors="coerce")
    master = master.drop_duplicates(config.stock_key, keep="last")
    monthly = monthly.merge(master, on=config.stock_key, how="left", validate="many_to_one")

    calendar_dates = (
        pd.to_datetime(
            trade_calendar.loc[trade_calendar["IfTradingDay"].eq(1), "date"],
            errors="coerce",
        )
        .dropna()
        .drop_duplicates()
        .sort_values()
        .to_numpy(dtype="datetime64[ns]")
    )
    list_values = monthly["list_date"].to_numpy(dtype="datetime64[ns]")
    signal_values = monthly[config.signal_date_key].to_numpy(dtype="datetime64[ns]")
    valid_list_date = monthly["list_date"].notna().to_numpy()
    start_positions = np.searchsorted(calendar_dates, list_values, side="left")
    end_positions = np.searchsorted(calendar_dates, signal_values, side="right")
    listing_days = end_positions - start_positions
    monthly["listing_trading_days"] = np.where(
        valid_list_date, listing_days, np.nan
    )

    if st_data is None:
        monthly["is_st_on_signal"] = False
        monthly["is_st_on_execution"] = False
    else:
        st = st_data.copy()
        st[config.stock_key] = st[config.stock_key].astype(str).str.zfill(6)
        monthly["is_st_on_signal"] = _interval_flag(
            monthly,
            st,
            date_column=config.signal_date_key,
            start_column="implement_date",
            end_column="remove_date",
            stock_column=config.stock_key,
        )
        monthly["is_st_on_execution"] = _interval_flag(
            monthly,
            st,
            date_column="execution_date",
            start_column="implement_date",
            end_column="remove_date",
            stock_column=config.stock_key,
        )

    if suspend_status is not None:
        suspend = suspend_status[
            [config.stock_key, "date", "if_suspend"]
        ].copy()
        suspend[config.stock_key] = suspend[config.stock_key].astype(str).str.zfill(6)
        suspend["date"] = pd.to_datetime(suspend["date"], errors="coerce")
        monthly = monthly.merge(
            suspend.rename(columns={"date": "execution_date"}),
            on=[config.stock_key, "execution_date"],
            how="left",
            validate="many_to_one",
        )
    else:
        monthly["if_suspend"] = 0
    if limit_status is not None:
        limits = limit_status[
            [config.stock_key, "date", "surged_limit", "decline_limit"]
        ].copy()
        limits[config.stock_key] = limits[config.stock_key].astype(str).str.zfill(6)
        limits["date"] = pd.to_datetime(limits["date"], errors="coerce")
        monthly = monthly.merge(
            limits.rename(columns={"date": "execution_date"}),
            on=[config.stock_key, "execution_date"],
            how="left",
            validate="many_to_one",
        )
    else:
        monthly["surged_limit"] = 0
        monthly["decline_limit"] = 0

    monthly["is_signal_eligible"] = (
        monthly["last_observation_date"].eq(monthly[config.signal_date_key])
        & monthly["close"].gt(0)
        & monthly["negotiable_market_value"].gt(0)
        & monthly["listing_trading_days"].ge(config.minimum_listing_trading_days)
        & ~monthly["is_st_on_signal"]
    )
    monthly["execution_buyable"] = (
        monthly["if_suspend"].fillna(0).ne(1)
        & monthly["surged_limit"].fillna(0).ne(1)
        & ~monthly["is_st_on_execution"]
    )
    monthly["execution_sellable"] = (
        monthly["if_suspend"].fillna(0).ne(1)
        & monthly["decline_limit"].fillna(0).ne(1)
        & ~monthly["is_st_on_execution"]
    )
    grouped = monthly.groupby(config.stock_key, observed=True)
    next_month = grouped["signal_month"].shift(-1)
    monthly["forward_return"] = grouped["month_return"].shift(-1).where(
        next_month.eq(monthly["signal_month"] + 1)
    )
    monthly["forward_return_date"] = grouped[config.signal_date_key].shift(-1).where(
        next_month.eq(monthly["signal_month"] + 1)
    )
    monthly["signal_source_max_date"] = monthly["last_observation_date"]
    if (
        monthly["signal_source_max_date"] > monthly[config.signal_date_key]
    ).any():
        raise DataContractError("股票月面板出现 source_date > signal_date")
    if not (
        monthly["execution_date"] > monthly[config.signal_date_key]
    ).all():
        raise DataContractError("股票月面板出现 execution_date <= signal_date")
    return monthly.sort_values(
        [config.signal_date_key, config.stock_key], kind="stable"
    ).reset_index(drop=True)


def load_monthly_stock_panel(
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """从真实本地 parquet 加载指定区间并构造股票月面板。"""
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    read_start = start - pd.DateOffset(months=config.monthly_macro_lag_months)
    read_end = end + pd.DateOffset(months=config.prediction_freeze_months // 12)
    price = load_stock_price_forward(
        config.data_root,
        columns=["stock_code", "date", "open", "close"],
        start_date=str(read_start.date()),
        end_date=str(read_end.date()),
    )
    trade_spec = _source_by_key(config)["stock_trade"]
    trade = pd.read_parquet(
        config.data_root / trade_spec.relative_path,
        columns=[
            "stock_code",
            "date",
            "market_value",
            "negotiable_market_value",
            "turn_value",
            "turnover_rate_free",
        ],
        filters=[
            ("date", ">=", read_start),
            ("date", "<=", read_end),
        ],
    )
    master_spec = _source_by_key(config)["stock_master"]
    master = pd.read_parquet(
        config.data_root / master_spec.relative_path,
        columns=["stock_code", "list_date"],
    )
    calendar = load_trade_calendar(
        config.data_root,
        start_date=str(read_start.date()),
        end_date=str(read_end.date()),
    )
    st_data = load_st_data(config.data_root)
    stock_codes = sorted(price["stock_code"].astype(str).unique())
    suspend = load_suspend_status(
        config.data_root,
        stock_codes=stock_codes,
        start_date=str(read_start.date()),
    )
    limits = load_limit_status(
        config.data_root,
        stock_codes=stock_codes,
        start_date=str(read_start.date()),
    )
    panel = build_monthly_stock_panel(
        price,
        trade,
        master,
        calendar,
        st_data=st_data,
        suspend_status=suspend,
        limit_status=limits,
        config=config,
    )
    return panel.loc[
        panel[config.signal_date_key].between(start, end, inclusive="both")
    ].reset_index(drop=True)


def build_industry_pit_mapping(
    signal_keys: pd.DataFrame,
    industry_records: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
    *,
    strict: bool = True,
) -> pd.DataFrame:
    """按行业生效区间连接申万一级分类；无生效日时不得把静态分类伪装成 PIT。"""
    required_signal = {config.stock_key, config.signal_date_key}
    required_industry = {
        config.stock_key,
        "first_industry_name",
        "standard_code",
    }
    missing_signal = sorted(required_signal.difference(signal_keys.columns))
    missing_industry = sorted(required_industry.difference(industry_records.columns))
    if missing_signal:
        raise DataContractError(f"signal_keys 缺少字段: {missing_signal}")
    if missing_industry:
        raise DataContractError(f"industry_records 缺少字段: {missing_industry}")
    start_column = next(
        (
            column
            for column in config.industry_start_date_candidates
            if column in industry_records.columns
        ),
        None,
    )
    if start_column is None:
        raise FormalDataUnavailableError(
            "ashare_stock_industry 缺少行业生效日字段 "
            f"{config.industry_start_date_candidates}，无法证明申万一级历史 PIT"
        )
    end_column = next(
        (
            column
            for column in config.industry_end_date_candidates
            if column in industry_records.columns
        ),
        None,
    )
    left = signal_keys[[config.stock_key, config.signal_date_key]].copy()
    left[config.stock_key] = left[config.stock_key].astype(str).str.zfill(6)
    left[config.signal_date_key] = pd.to_datetime(
        left[config.signal_date_key], errors="coerce"
    ).dt.normalize()
    left["_signal_row"] = np.arange(len(left))
    columns = [
        config.stock_key,
        "first_industry_name",
        "standard_code",
        start_column,
        *([end_column] if end_column is not None else []),
    ]
    right = industry_records[columns].copy()
    right[config.stock_key] = right[config.stock_key].astype(str).str.zfill(6)
    right = right.loc[
        pd.to_numeric(right["standard_code"], errors="coerce").eq(
            config.industry_standard_code
        )
    ]
    right[start_column] = pd.to_datetime(
        right[start_column], errors="coerce"
    ).dt.normalize()
    if end_column is None:
        right["_industry_end_date"] = pd.NaT
        end_column = "_industry_end_date"
    else:
        right[end_column] = pd.to_datetime(
            right[end_column], errors="coerce"
        ).dt.normalize()
    joined = left.merge(right, on=config.stock_key, how="left")
    active = joined.loc[
        joined[start_column].notna()
        & joined[start_column].le(joined[config.signal_date_key])
        & (
            joined[end_column].isna()
            | joined[end_column].gt(joined[config.signal_date_key])
        )
    ].copy()
    active_counts = active.groupby("_signal_row", observed=True).size()
    conflicts = active_counts.gt(1)
    if conflicts.any():
        conflicting_rows = set(active_counts.index[conflicts])
        conflict_names = (
            active.loc[active["_signal_row"].isin(conflicting_rows)]
            .groupby("_signal_row", observed=True)["first_industry_name"]
            .nunique(dropna=False)
        )
        if conflict_names.gt(1).any() or strict:
            raise DataContractError("同一股票信号日存在多个有效申万一级行业记录")
    active = active.sort_values(
        ["_signal_row", start_column], kind="stable"
    ).drop_duplicates("_signal_row", keep="last")
    output = left.merge(
        active[
            [
                "_signal_row",
                "first_industry_name",
                start_column,
                end_column,
            ]
        ],
        on="_signal_row",
        how="left",
        validate="one_to_one",
    ).rename(
        columns={
            "first_industry_name": "industry_name",
            start_column: "industry_effective_date",
            end_column: "industry_end_date",
        }
    )
    output = output.drop(columns="_signal_row")
    if strict and output["industry_name"].isna().any():
        missing_count = int(output["industry_name"].isna().sum())
        raise FormalDataUnavailableError(
            f"{missing_count} 个股票-信号日没有可证明时点有效的申万一级行业"
        )
    if (
        output["industry_effective_date"].notna()
        & output["industry_effective_date"].gt(output[config.signal_date_key])
    ).any():
        raise DataContractError("行业映射出现 effective_date > signal_date")
    return output


def load_industry_pit_mapping(
    signal_keys: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """读取实际申万行业文件并执行历史生效区间连接。"""
    spec = _source_by_key(config)["stock_industry"]
    records = pd.read_parquet(config.data_root / spec.relative_path)
    return build_industry_pit_mapping(signal_keys, records, config, strict=True)


def calculate_historical_market_beta(
    monthly_stock_panel: pd.DataFrame,
    index_state_inputs: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """只用截至 T 月的历史月收益估计股票对明确宽基的滚动 beta。"""
    stock_required = {
        config.stock_key,
        config.signal_date_key,
        "month_return",
    }
    index_required = {config.signal_date_key, "market_return"}
    missing_stock = sorted(stock_required.difference(monthly_stock_panel.columns))
    missing_index = sorted(index_required.difference(index_state_inputs.columns))
    if missing_stock:
        raise DataContractError(f"monthly_stock_panel 缺少 beta 字段: {missing_stock}")
    if missing_index:
        raise DataContractError(f"index_state_inputs 缺少 beta 字段: {missing_index}")
    frame = monthly_stock_panel[
        [config.stock_key, config.signal_date_key, "month_return"]
    ].merge(
        index_state_inputs[
            [config.signal_date_key, "market_return"]
        ].drop_duplicates(config.signal_date_key),
        on=config.signal_date_key,
        how="left",
        validate="many_to_one",
    )
    frame = frame.sort_values(
        [config.stock_key, config.signal_date_key], kind="stable"
    )
    frame["_xy"] = frame["month_return"] * frame["market_return"]
    grouped = frame.groupby(config.stock_key, observed=True)
    window = config.market_beta_window_months
    minimum = config.market_beta_min_observations
    mean_x = grouped["month_return"].transform(
        lambda series: series.rolling(window, min_periods=minimum).mean()
    )
    mean_y = grouped["market_return"].transform(
        lambda series: series.rolling(window, min_periods=minimum).mean()
    )
    mean_xy = grouped["_xy"].transform(
        lambda series: series.rolling(window, min_periods=minimum).mean()
    )
    mean_y2 = grouped["market_return"].transform(
        lambda series: series.pow(2).rolling(window, min_periods=minimum).mean()
    )
    covariance = mean_xy - mean_x * mean_y
    variance = mean_y2 - mean_y.pow(2)
    frame["historical_market_beta"] = (
        covariance / variance
    ).where(variance.abs().gt(config.market_beta_variance_floor))
    frame["beta_source_max_date"] = frame[config.signal_date_key]
    if (
        frame["beta_source_max_date"] > frame[config.signal_date_key]
    ).any():
        raise DataContractError("历史 beta 使用了信号日后的收益")
    return frame[
        [
            config.stock_key,
            config.signal_date_key,
            "historical_market_beta",
            "beta_source_max_date",
        ]
    ].reset_index(drop=True)


def build_capacity_control_panel(
    monthly_stock_panel: pd.DataFrame,
    index_state_inputs: pd.DataFrame,
    industry_pit: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """汇总 D9 的 T 时点流通市值、行业、历史 beta 与成交换手代理。"""
    base_columns = [
        config.stock_key,
        config.signal_date_key,
        "negotiable_market_value",
        "turn_value_month",
        "turnover_rate_free_month",
    ]
    missing = sorted(set(base_columns).difference(monthly_stock_panel.columns))
    if missing:
        raise DataContractError(f"monthly_stock_panel 缺少 D9 字段: {missing}")
    beta = calculate_historical_market_beta(
        monthly_stock_panel, index_state_inputs, config
    )
    industry_columns = [
        config.stock_key,
        config.signal_date_key,
        "industry_name",
        "industry_effective_date",
        "industry_end_date",
    ]
    missing_industry = sorted(set(industry_columns).difference(industry_pit.columns))
    if missing_industry:
        raise DataContractError(f"industry_pit 缺少 D9 字段: {missing_industry}")
    output = (
        monthly_stock_panel[base_columns]
        .merge(
            industry_pit[industry_columns],
            on=[config.stock_key, config.signal_date_key],
            how="left",
            validate="one_to_one",
        )
        .merge(
            beta,
            on=[config.stock_key, config.signal_date_key],
            how="left",
            validate="one_to_one",
        )
    )
    if output["industry_name"].isna().all():
        raise FormalDataUnavailableError("D9 没有任何可证明时点有效的申万一级行业")
    if output["historical_market_beta"].notna().sum() == 0:
        raise FormalDataUnavailableError("D9 历史 beta 无任何满足最小窗口的估计")
    return output


def build_financial_asof(
    signal_keys: pd.DataFrame,
    financial_records: pd.DataFrame,
    value_columns: Sequence[str],
    *,
    source_key: str,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """将一张财务表按 ``info_publ_date`` 连接到股票信号时点。

    ``end_date`` 只作为报告期标签；同一股票截至信号日选择报告期最新、同报告期
    披露版本最新的记录，绝不按报告期直接对齐。
    """
    signal_required = {config.stock_key, config.signal_date_key}
    financial_required = {
        config.stock_key,
        config.financial_period_key,
        config.financial_publication_key,
        *value_columns,
    }
    missing_signal = sorted(signal_required.difference(signal_keys.columns))
    missing_financial = sorted(financial_required.difference(financial_records.columns))
    if missing_signal:
        raise DataContractError(f"signal_keys 缺少字段: {missing_signal}")
    if missing_financial:
        raise DataContractError(f"{source_key} 缺少字段: {missing_financial}")

    left = signal_keys[[config.stock_key, config.signal_date_key]].copy()
    left[config.stock_key] = left[config.stock_key].astype(str).str.zfill(6)
    left[config.signal_date_key] = pd.to_datetime(
        left[config.signal_date_key], errors="coerce"
    ).dt.normalize()
    left["_original_order"] = np.arange(len(left))
    right = financial_records[
        [
            config.stock_key,
            config.financial_period_key,
            config.financial_publication_key,
            *value_columns,
        ]
    ].copy()
    right[config.stock_key] = right[config.stock_key].astype(str).str.zfill(6)
    for column in (
        config.financial_period_key,
        config.financial_publication_key,
    ):
        right[column] = pd.to_datetime(right[column], errors="coerce").dt.normalize()
    right = right.dropna(
        subset=[
            config.stock_key,
            config.financial_period_key,
            config.financial_publication_key,
        ]
    ).sort_values(
        [
            config.stock_key,
            config.financial_publication_key,
            config.financial_period_key,
        ],
        kind="stable",
    )
    cumulative_latest_period = right.groupby(
        config.stock_key, observed=True
    )[config.financial_period_key].cummax()
    right = right.loc[
        right[config.financial_period_key].ge(cumulative_latest_period)
    ].drop_duplicates(
        [config.stock_key, config.financial_publication_key],
        keep="last",
    )
    left_sorted = left.sort_values(
        [config.signal_date_key, config.stock_key], kind="stable"
    )
    right_sorted = right.sort_values(
        [config.financial_publication_key, config.stock_key], kind="stable"
    )
    merged = pd.merge_asof(
        left_sorted,
        right_sorted,
        left_on=config.signal_date_key,
        right_on=config.financial_publication_key,
        by=config.stock_key,
        direction="backward",
        allow_exact_matches=True,
    ).sort_values("_original_order", kind="stable")
    rename = {
        config.financial_period_key: f"{source_key}_end_date",
        config.financial_publication_key: f"{source_key}_info_publ_date",
        **{column: f"{source_key}_{column}" for column in value_columns},
    }
    merged = merged.rename(columns=rename).drop(columns="_original_order")
    source_publication = f"{source_key}_info_publ_date"
    if (
        merged[source_publication].notna()
        & merged[source_publication].gt(merged[config.signal_date_key])
    ).any():
        raise DataContractError(
            f"{source_key} 出现 info_publ_date > signal_date"
        )
    return merged


def load_financial_pit_panel(
    signal_keys: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """读取三张真实财务表并生成 PIT 基础字段面板。"""
    source_values = {
        "stock_balance": (
            "total_assets",
            "total_liability",
            "total_shareholder_equity",
        ),
        "stock_income": (
            "total_operating_revenue",
            "operating_profit",
            "net_profit",
        ),
        "stock_cashflow": ("net_operate_cash_flow",),
    }
    sources = _source_by_key(config)
    output = signal_keys[[config.stock_key, config.signal_date_key]].copy()
    max_signal = pd.to_datetime(output[config.signal_date_key]).max()
    stock_codes = sorted(output[config.stock_key].astype(str).unique())
    for source_key, value_columns in source_values.items():
        spec = sources[source_key]
        records = pd.read_parquet(
            config.data_root / spec.relative_path,
            columns=[
                config.stock_key,
                config.financial_period_key,
                config.financial_publication_key,
                *value_columns,
            ],
            filters=[
                (config.stock_key, "in", stock_codes),
                (config.financial_publication_key, "<=", max_signal),
            ],
        )
        asof = build_financial_asof(
            signal_keys,
            records,
            value_columns,
            source_key=source_key,
            config=config,
        )
        value_output = [
            column
            for column in asof.columns
            if column not in {config.stock_key, config.signal_date_key}
        ]
        output = output.merge(
            asof[
                [config.stock_key, config.signal_date_key, *value_output]
            ],
            on=[config.stock_key, config.signal_date_key],
            how="left",
            validate="one_to_one",
        )
    return output


def apply_conservative_publication_lag(
    observations: pd.DataFrame,
    *,
    frequency: str,
    lag_months: int,
    observation_column: str = "observation_date",
    publication_column: str = "info_publ_date",
) -> pd.DataFrame:
    """以真实披露日和固定保守下限的较晚者生成宏观 ``available_date``。"""
    frame = observations.copy()
    frame[observation_column] = pd.to_datetime(
        frame[observation_column], errors="coerce"
    ).dt.normalize()
    observation_month_end = (
        frame[observation_column].dt.to_period("M").dt.to_timestamp("M")
    )
    conservative_floor = observation_month_end + pd.offsets.MonthEnd(lag_months)
    if publication_column in frame.columns:
        publication = pd.to_datetime(
            frame[publication_column], errors="coerce"
        ).dt.normalize()
    else:
        publication = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    frame["available_date"] = pd.concat(
        [conservative_floor.rename("floor"), publication.rename("publication")],
        axis=1,
    ).max(axis=1)
    frame["timing_method"] = np.where(
        publication.notna(),
        f"max(info_publ_date,{frequency}_lag_{lag_months}m)",
        f"{frequency}_lag_{lag_months}m",
    )
    return frame


def _read_macro_candidate(
    spec: MacroSeriesSpec,
    config: R006M1Config,
    cache: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """读取一个配置化宏观候选，保留真实源日与披露日。"""
    source = _source_by_key(config)[spec.source_key]
    if spec.source_key not in cache:
        source_path = config.data_root / source.relative_path
        cache[spec.source_key] = pd.read_parquet(source_path)
    raw = cache[spec.source_key]
    if spec.source_key == "macro_cache":
        frame = raw.reset_index()
        date_candidates = [
            config.source_date_key,
            "__index_level_0__",
            "index",
        ]
        date_column = next(
            (column for column in date_candidates if column in frame.columns),
            None,
        )
        if date_column is None or spec.value_column not in frame.columns:
            return pd.DataFrame()
        selected = frame[[date_column, spec.value_column]].rename(
            columns={
                date_column: "observation_date",
                spec.value_column: "value",
            }
        )
    elif spec.source_key in {"bond_yield_curve", "bond_shibor"}:
        selected = _transform_market_macro_candidate(raw, spec, config)
    else:
        required = {
            "date",
            "info_publ_date",
            "indicator_code",
            spec.value_column,
        }
        if not required.issubset(raw.columns):
            return pd.DataFrame()
        selected = raw.loc[
            raw["indicator_code"].astype(str).eq(str(spec.indicator_code)),
            ["date", "info_publ_date", spec.value_column],
        ].rename(
            columns={"date": "observation_date", spec.value_column: "value"}
        )
    selected["observation_date"] = pd.to_datetime(
        selected["observation_date"], errors="coerce"
    ).dt.normalize()
    selected["value"] = pd.to_numeric(selected["value"], errors="coerce")
    selected = selected.dropna(subset=["observation_date", "value"])
    if selected.empty:
        return selected
    if spec.frequency == "daily_market":
        selected["available_date"] = selected["observation_date"]
        selected["timing_method"] = "same_day_market_close"
    else:
        selected = apply_conservative_publication_lag(
            selected,
            frequency=spec.frequency,
            lag_months=spec.lag_months,
        )
    selected["block"] = spec.block
    selected["series_id"] = spec.series_id
    selected["source_key"] = spec.source_key
    selected["source_file"] = str(config.data_root / source.relative_path)
    selected["frequency"] = spec.frequency
    selected["configured_lag_months"] = spec.lag_months
    return selected[
        [
            "block",
            "series_id",
            "observation_date",
            "available_date",
            "value",
            "source_key",
            "source_file",
            "frequency",
            "configured_lag_months",
            "timing_method",
        ]
    ]


def _transform_market_macro_candidate(
    raw: pd.DataFrame,
    spec: MacroSeriesSpec,
    config: R006M1Config,
) -> pd.DataFrame:
    """把债券收益率曲线或 SHIBOR 转成配置登记的宏观候选。"""
    if spec.source_key == "bond_shibor":
        required = {"date", "maturity_raw", "rate"}
        if not required.issubset(raw.columns):
            return pd.DataFrame()
        selected = raw.copy()
        for column, value in spec.selectors:
            selected = selected.loc[selected[column].eq(value)]
        return selected[["date", "rate"]].rename(
            columns={"date": "observation_date", "rate": "value"}
        )

    required = {
        "date",
        "curve_code",
        "years_to_maturity",
        "yield_type",
        "yield_value",
    }
    if not required.issubset(raw.columns):
        return pd.DataFrame()
    curve = raw.copy()
    curve["curve_code"] = pd.to_numeric(curve["curve_code"], errors="coerce")
    curve["years_to_maturity"] = pd.to_numeric(
        curve["years_to_maturity"], errors="coerce"
    )
    if spec.transform == "direct":
        selected = curve
        for column, value in spec.selectors:
            selected = selected.loc[selected[column].eq(value)]
        return selected[["date", "yield_value"]].rename(
            columns={"date": "observation_date", "yield_value": "value"}
        )
    if spec.transform == "government_term_spread_10y_1y":
        selected = curve.loc[
            curve["curve_code"].eq(config.government_curve_code)
            & curve["yield_type"].eq(config.bond_yield_type)
            & curve["years_to_maturity"].isin(
                [config.short_maturity_years, config.long_maturity_years]
            )
        ]
        pivoted = selected.pivot_table(
            index="date",
            columns="years_to_maturity",
            values="yield_value",
            aggfunc="last",
        )
        required_maturities = {
            config.short_maturity_years,
            config.long_maturity_years,
        }
        if not required_maturities.issubset(pivoted.columns):
            return pd.DataFrame()
        value = (
            pd.to_numeric(
                pivoted[config.long_maturity_years], errors="coerce"
            )
            - pd.to_numeric(
                pivoted[config.short_maturity_years], errors="coerce"
            )
        )
        return value.rename("value").reset_index().rename(
            columns={"date": "observation_date"}
        )
    if spec.transform == "corporate_aaa_minus_government_10y":
        selected = curve.loc[
            curve["yield_type"].eq(config.bond_yield_type)
            & curve["years_to_maturity"].eq(config.long_maturity_years)
            & curve["curve_code"].isin(
                [
                    config.government_curve_code,
                    config.corporate_aaa_curve_code,
                ]
            )
        ]
        pivoted = selected.pivot_table(
            index="date",
            columns="curve_code",
            values="yield_value",
            aggfunc="last",
        )
        required_curves = {
            config.government_curve_code,
            config.corporate_aaa_curve_code,
        }
        if not required_curves.issubset(pivoted.columns):
            return pd.DataFrame()
        value = (
            pd.to_numeric(
                pivoted[config.corporate_aaa_curve_code], errors="coerce"
            )
            - pd.to_numeric(
                pivoted[config.government_curve_code], errors="coerce"
            )
        )
        return value.rename("value").reset_index().rename(
            columns={"date": "observation_date"}
        )
    raise DataContractError(f"未实现的宏观转换: {spec.transform}")


def load_macro_conditioning_inputs(
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """按 series_id 优先 macro_cache，源级缺失时才用明细表候选。"""
    cache: dict[str, pd.DataFrame] = {}
    frames: list[pd.DataFrame] = []
    grouped_specs: dict[str, list[MacroSeriesSpec]] = {}
    for spec in config.macro_series_specs:
        grouped_specs.setdefault(spec.series_id, []).append(spec)
    for series_id, candidates in grouped_specs.items():
        chosen = pd.DataFrame()
        for candidate in sorted(candidates, key=lambda item: item.priority):
            chosen = _read_macro_candidate(candidate, config, cache)
            if not chosen.empty:
                break
        if chosen.empty:
            raise FormalDataUnavailableError(
                f"宏观序列 {series_id} 的配置候选均无实际非缺失值"
            )
        frames.append(chosen)
    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(
        ["series_id", "available_date", "observation_date"], kind="stable"
    ).drop_duplicates(["series_id", "available_date"], keep="last")
    if (result["available_date"] < result["observation_date"]).any():
        raise DataContractError("宏观 available_date 早于 observation_date")
    return result.reset_index(drop=True)


def align_macro_asof(
    signal_dates: Sequence[pd.Timestamp] | pd.Series | pd.DatetimeIndex,
    macro_inputs: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """仅向后把已可用宏观值连接到每个信号日，并保留源日审计列。"""
    required = {
        "block",
        "series_id",
        "observation_date",
        "available_date",
        "value",
        "source_key",
    }
    missing = sorted(required.difference(macro_inputs.columns))
    if missing:
        raise DataContractError(f"macro_inputs 缺少字段: {missing}")
    signal_date_values = pd.Series(
        pd.to_datetime(signal_dates, errors="coerce"),
        copy=False,
    )
    if isinstance(signal_date_values.dtype, pd.DatetimeTZDtype):
        raise DataContractError("signal_date 必须是无时区日期")
    signal_date_values = (
        signal_date_values.dt.normalize().astype("datetime64[ns]")
    )
    signals = pd.DataFrame(
        {config.signal_date_key: signal_date_values.unique()}
    ).sort_values(config.signal_date_key)
    aligned_frames: list[pd.DataFrame] = []
    for series_id, group in macro_inputs.groupby("series_id", observed=True):
        right = group.copy()
        for date_key in ("observation_date", "available_date"):
            normalized = pd.to_datetime(right[date_key], errors="coerce")
            if isinstance(normalized.dtype, pd.DatetimeTZDtype):
                raise DataContractError(f"{date_key} 必须是无时区日期")
            right[date_key] = normalized.astype("datetime64[ns]")
        right = right.sort_values("available_date", kind="stable")
        aligned = pd.merge_asof(
            signals,
            right,
            left_on=config.signal_date_key,
            right_on="available_date",
            direction="backward",
            allow_exact_matches=True,
        )
        aligned["series_id"] = series_id
        aligned_frames.append(aligned)
    result = pd.concat(aligned_frames, ignore_index=True)
    violations = result["available_date"].notna() & result["available_date"].gt(
        result[config.signal_date_key]
    )
    if violations.any():
        raise DataContractError("宏观 as-of 连接出现 available_date > signal_date")
    return result.sort_values(
        [config.signal_date_key, "series_id"], kind="stable"
    ).reset_index(drop=True)


def load_index_state_inputs(
    trade_calendar: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
    *,
    index_code: str | None = None,
) -> pd.DataFrame:
    """加载调用方明确指定的 A 股宽基指数月末原料；不静默猜测代码。"""
    selected_code = index_code or config.benchmark_index_code
    if selected_code is None:
        raise FormalDataUnavailableError(
            "spec 未指定 A 股市场基准；须显式传入 index_code，禁止臆测"
        )
    sources = _source_by_key(config)
    trade = pd.read_parquet(
        config.data_root / sources["csiindex_trade"].relative_path,
        columns=[
            "index_code",
            "index_name",
            "date",
            "close",
            "change_pct",
            "turnover_value",
            "total_mv",
            "pe",
            "dv",
        ],
        filters=[("index_code", "==", str(selected_code))],
    )
    if trade.empty:
        raise FormalDataUnavailableError(
            f"ashare_csiindex_trade 中没有 index_code={selected_code}"
        )
    value = pd.read_parquet(
        config.data_root / sources["index_value"].relative_path,
        columns=[
            "index_code",
            "date",
            "pe_ttm",
            "pb_lf",
            "ps_ttm",
            "dv",
        ],
        filters=[("index_code", "==", str(selected_code))],
    )
    index_trade = pd.read_parquet(
        config.data_root / sources["index_trade"].relative_path,
        columns=[
            "index_code",
            "date",
            "turnover_value",
            "change_pct",
            "negotiable_market_value",
        ],
        filters=[("index_code", "==", str(selected_code))],
    )
    schedule = build_execution_schedule(trade_calendar, config)
    schedule_map = schedule[["signal_month", config.signal_date_key, "execution_date"]]

    def _monthly_last(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        local = frame.copy()
        local["date"] = pd.to_datetime(local["date"], errors="coerce")
        local["signal_month"] = local["date"].dt.to_period("M")
        value_columns = [
            column
            for column in local.columns
            if column not in {"index_code", "index_name", "date", "signal_month"}
        ]
        renamed = {column: f"{prefix}_{column}" for column in value_columns}
        return (
            local.sort_values("date")
            .groupby("signal_month", observed=True)
            .last()
            .reset_index()[["signal_month", "date", *value_columns]]
            .rename(
                columns={
                    "date": f"{prefix}_source_date",
                    **renamed,
                }
            )
        )

    output = schedule_map.merge(
        _monthly_last(trade, "csi"),
        on="signal_month",
        how="left",
        validate="one_to_one",
    ).merge(
        _monthly_last(value, "value"),
        on="signal_month",
        how="left",
        validate="one_to_one",
    ).merge(
        _monthly_last(index_trade, "index_trade"),
        on="signal_month",
        how="left",
        validate="one_to_one",
    )
    source_date_columns = [
        column for column in output.columns if column.endswith("_source_date")
    ]
    output["source_max_date"] = output[source_date_columns].max(axis=1)
    if (
        output["source_max_date"].notna()
        & output["source_max_date"].gt(output[config.signal_date_key])
    ).any():
        raise DataContractError("指数市场状态原料出现 source_date > signal_date")
    output["market_return"] = output["csi_close"].pct_change(fill_method=None)
    output["index_code"] = str(selected_code)
    return output


def build_market_macro_inputs(
    index_state_inputs: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """由 D7 明确指数输入构造 D5 的 Trend 块，不重复读取或猜测基准。"""
    required = {
        config.signal_date_key,
        "source_max_date",
        "market_return",
        "index_code",
    }
    missing = sorted(required.difference(index_state_inputs.columns))
    if missing:
        raise DataContractError(f"index_state_inputs 缺少 Trend 字段: {missing}")
    frame = index_state_inputs[
        [
            config.signal_date_key,
            "source_max_date",
            "market_return",
            "index_code",
        ]
    ].copy()
    frame = frame.loc[frame["market_return"].notna()]
    frame["block"] = "Trend"
    frame["series_id"] = "broad_market_return"
    frame["observation_date"] = pd.to_datetime(
        frame["source_max_date"], errors="coerce"
    ).dt.normalize()
    frame["available_date"] = frame["observation_date"]
    frame["value"] = pd.to_numeric(frame["market_return"], errors="coerce")
    frame["source_key"] = "csiindex_trade"
    frame["source_file"] = frame["index_code"].map(
        lambda code: (
            f"{config.data_root / _source_by_key(config)['csiindex_trade'].relative_path}"
            f"#index_code={code}"
        )
    )
    frame["frequency"] = "monthly_market"
    frame["configured_lag_months"] = 0
    frame["timing_method"] = "same_day_market_close"
    if (
        frame["available_date"].notna()
        & frame["available_date"].gt(frame[config.signal_date_key])
    ).any():
        raise DataContractError("Trend 指数原料出现 available_date > signal_date")
    return frame[
        [
            "block",
            "series_id",
            "observation_date",
            "available_date",
            "value",
            "source_key",
            "source_file",
            "frequency",
            "configured_lag_months",
            "timing_method",
        ]
    ].reset_index(drop=True)


def ensure_macro_block_coverage(
    macro_inputs: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
) -> None:
    """正式入口要求八个配置块均有实际非缺失输入。"""
    required = {"block", "series_id", "value"}
    missing_columns = sorted(required.difference(macro_inputs.columns))
    if missing_columns:
        raise DataContractError(f"macro_inputs 缺少块覆盖字段: {missing_columns}")
    available = set(
        macro_inputs.loc[macro_inputs["value"].notna(), "block"].astype(str)
    )
    missing_blocks = [
        block for block in config.required_macro_blocks if block not in available
    ]
    if missing_blocks:
        raise FormalDataUnavailableError(
            f"D5 八块宏观角色覆盖不足，缺少实际块: {missing_blocks}"
        )


def build_common_month_index(
    factor_panel: pd.DataFrame,
    monthly_stock_panel: pd.DataFrame,
    macro_asof: pd.DataFrame,
    index_state_inputs: pd.DataFrame,
    config: R006M1Config = DEFAULT_CONFIG,
    *,
    return_diagnostics: bool = False,
) -> pd.DatetimeIndex | CommonMonthResult:
    """按四类实际非缺失月及逐月八块宏观完整性构造共同月。"""
    factor_required = {
        config.signal_date_key,
        "factor_id",
        "factor_value",
    }
    stock_required = {
        config.signal_date_key,
        "is_signal_eligible",
        "month_return",
    }
    macro_required = {
        config.signal_date_key,
        "block",
        "series_id",
        "value",
    }
    index_required = {
        config.signal_date_key,
        "source_max_date",
        "market_return",
    }
    for name, frame, required in (
        ("factor_panel", factor_panel, factor_required),
        ("monthly_stock_panel", monthly_stock_panel, stock_required),
        ("macro_asof", macro_asof, macro_required),
        ("index_state_inputs", index_state_inputs, index_required),
    ):
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise DataContractError(f"{name} 缺少共同月字段: {missing}")

    factor_months = set(
        pd.to_datetime(
            factor_panel.loc[
                factor_panel["factor_value"].notna(), config.signal_date_key
            ]
        ).dt.to_period("M")
    )
    stock_months = set(
        pd.to_datetime(
            monthly_stock_panel.loc[
                monthly_stock_panel["is_signal_eligible"]
                & monthly_stock_panel["month_return"].notna(),
                config.signal_date_key,
            ]
        ).dt.to_period("M")
    )
    index_valid = (
        index_state_inputs["market_return"].notna()
        & index_state_inputs["source_max_date"].notna()
        & index_state_inputs["source_max_date"].le(
            index_state_inputs[config.signal_date_key]
        )
    )
    index_months = set(
        pd.to_datetime(
            index_state_inputs.loc[index_valid, config.signal_date_key]
        ).dt.to_period("M")
    )
    candidate_periods = sorted(
        factor_months & stock_months & index_months
    )
    if not candidate_periods:
        raise FormalDataUnavailableError(
            "因子、股票与指数没有实际共同非缺失候选月份"
        )
    macro = macro_asof[
        [config.signal_date_key, "block", "series_id", "value"]
    ].copy()
    macro["signal_month"] = pd.to_datetime(
        macro[config.signal_date_key], errors="coerce"
    ).dt.to_period("M")
    macro["has_available_value"] = pd.to_numeric(
        macro["value"], errors="coerce"
    ).notna()
    block_availability = (
        macro.groupby(["signal_month", "block"], observed=True)[
            "has_available_value"
        ]
        .any()
        .unstack("block", fill_value=False)
        .reindex(
            index=pd.PeriodIndex(
                candidate_periods, freq="M", name="signal_month"
            ),
            columns=list(config.required_macro_blocks),
            fill_value=False,
        )
        .fillna(False)
        .astype(bool)
    )
    diagnostics = block_availability.rename(
        columns=lambda block: f"macro_block::{block}"
    ).reset_index()
    block_columns = [
        f"macro_block::{block}" for block in config.required_macro_blocks
    ]
    diagnostics["all_required_macro_blocks"] = diagnostics[
        block_columns
    ].all(axis=1)
    diagnostics["missing_macro_blocks"] = diagnostics.apply(
        lambda row: ",".join(
            block
            for block in config.required_macro_blocks
            if not bool(row[f"macro_block::{block}"])
        ),
        axis=1,
    )
    diagnostics["eligible_common_month"] = diagnostics[
        "all_required_macro_blocks"
    ]
    common_periods = diagnostics.loc[
        diagnostics["eligible_common_month"], "signal_month"
    ].tolist()
    if not common_periods:
        missing_summary = (
            diagnostics["missing_macro_blocks"].value_counts().head(3).to_dict()
        )
        raise FormalDataUnavailableError(
            "候选信号月没有任何月份同时具备八个宏观块；"
            f"缺块诊断={missing_summary}"
        )
    month_index = pd.DatetimeIndex(
        [period.to_timestamp("M") for period in common_periods],
        name=config.signal_date_key,
    )
    result = CommonMonthResult(
        month_index=month_index,
        diagnostics=diagnostics,
    )
    return result if return_diagnostics else result.month_index


def build_walk_forward_windows(
    monthly_dates: Sequence[pd.Timestamp] | pd.DatetimeIndex | pd.Series,
    config: R006M1Config = DEFAULT_CONFIG,
    *,
    strict: bool = True,
) -> pd.DataFrame:
    """按共同样本首月锚定 120/144/12 月块，生成 expanding walk-forward。"""
    periods = pd.PeriodIndex(pd.to_datetime(monthly_dates), freq="M").unique().sort_values()
    columns = [
        "window_id",
        "prediction_year",
        "train_start",
        "train_end",
        "train_start_period",
        "train_end_period",
        "train_months",
        "validation_start",
        "validation_end",
        "validation_start_period",
        "validation_end_period",
        "validation_months",
        "prediction_start",
        "prediction_end",
        "prediction_start_period",
        "prediction_end_period",
        "prediction_months",
        "freeze_months",
        "dropped_tail_months",
    ]
    if len(periods) < config.minimum_total_history_months:
        if strict:
            raise DataContractError(
                f"共同历史 {len(periods)} 月 < "
                f"{config.minimum_total_history_months} 月"
            )
        result = pd.DataFrame(columns=columns)
        result.attrs["dropped_tail_months"] = 0
        return result
    expected = pd.period_range(periods.min(), periods.max(), freq="M")
    if not periods.equals(expected):
        missing_periods = expected.difference(periods)
        raise DataContractError(
            f"共同月序列不连续，缺失 {len(missing_periods)} 月: "
            f"{list(map(str, missing_periods[:6]))}"
        )

    rows: list[dict[str, Any]] = []
    history_months = config.training_months + config.validation_months
    prediction_offset = history_months
    while (
        prediction_offset + config.prediction_freeze_months
        <= len(periods)
    ):
        training_end = prediction_offset - config.validation_months
        training = periods[:training_end]
        validation = periods[
            training_end : training_end + config.validation_months
        ]
        prediction = periods[
            prediction_offset : prediction_offset
            + config.prediction_freeze_months
        ]
        if (
            len(validation) != config.validation_months
            or len(prediction) != config.prediction_freeze_months
        ):
            break
        window_id = (
            f"wf_{prediction.min().strftime('%Y%m')}_"
            f"{prediction.max().strftime('%Y%m')}"
        )
        rows.append(
            {
                "window_id": window_id,
                "prediction_year": prediction.min().year,
                "train_start": training.min().to_timestamp("M"),
                "train_end": training.max().to_timestamp("M"),
                "train_start_period": training.min(),
                "train_end_period": training.max(),
                "train_months": len(training),
                "validation_start": validation.min().to_timestamp("M"),
                "validation_end": validation.max().to_timestamp("M"),
                "validation_start_period": validation.min(),
                "validation_end_period": validation.max(),
                "validation_months": len(validation),
                "prediction_start": prediction.min().to_timestamp("M"),
                "prediction_end": prediction.max().to_timestamp("M"),
                "prediction_start_period": prediction.min(),
                "prediction_end_period": prediction.max(),
                "prediction_months": len(prediction),
                "freeze_months": config.prediction_freeze_months,
            }
        )
        prediction_offset += config.prediction_freeze_months
    dropped_tail_months = max(len(periods) - prediction_offset, 0)
    for row in rows:
        row["dropped_tail_months"] = dropped_tail_months
    result = pd.DataFrame(rows, columns=columns)
    result.attrs["dropped_tail_months"] = dropped_tail_months
    if strict and result.empty:
        if dropped_tail_months:
            raise DataContractError(
                "共同历史仅剩 "
                f"{dropped_tail_months} 个尾部预测月，少于完整 "
                f"{config.prediction_freeze_months} 月，已丢弃且不生成预测窗"
            )
        raise DataContractError("共同历史虽满 264 月，但无法形成年度预测窗口")
    if not result.empty:
        if not result["validation_months"].eq(config.validation_months).all():
            raise DataContractError("验证窗口不是固定 144 月")
        if not result["prediction_months"].eq(
            config.prediction_freeze_months
        ).all():
            raise DataContractError("预测窗口不是完整 12 月")
        if not result["freeze_months"].eq(
            config.prediction_freeze_months
        ).all():
            raise DataContractError("冻结窗口不是完整 12 月")
        if (result["train_end"] >= result["validation_start"]).any():
            raise DataContractError("训练与验证窗口重叠")
        if (result["validation_end"] >= result["prediction_start"]).any():
            raise DataContractError("验证与预测窗口重叠")
        if not result["train_months"].is_monotonic_increasing:
            raise DataContractError("训练窗口未 expanding")
        if int(result.iloc[0]["train_months"]) != config.training_months:
            raise DataContractError("首个训练窗口不是精确 120 月")
        train_differences = result["train_months"].diff().dropna()
        if not train_differences.eq(config.prediction_freeze_months).all():
            raise DataContractError("训练窗口未按每周期 12 月 expanding")
    return result


def select_walk_forward_window(
    walk_forward_windows: pd.DataFrame,
    prediction_year: int | None = None,
    *,
    window_id: str | None = None,
) -> pd.Series:
    """以不可歧义 window_id 为优先，兼容唯一 prediction_year 查询窗口。"""
    if window_id is not None:
        if "window_id" not in walk_forward_windows.columns:
            raise DataContractError("walk-forward 窗口缺少 window_id")
        selected = walk_forward_windows.loc[
            walk_forward_windows["window_id"].eq(str(window_id))
        ]
        selector = f"window_id={window_id}"
    elif prediction_year is not None:
        if "prediction_year" not in walk_forward_windows.columns:
            raise DataContractError("walk-forward 窗口缺少 prediction_year")
        selected = walk_forward_windows.loc[
            walk_forward_windows["prediction_year"].eq(int(prediction_year))
        ]
        selector = f"prediction_year={prediction_year}"
    else:
        raise DataContractError("必须提供 window_id 或 prediction_year")
    if len(selected) != 1:
        raise DataContractError(f"{selector} 必须唯一对应一个窗口")
    return selected.iloc[0]


def select_training_history(
    data: pd.DataFrame,
    walk_forward_windows: pd.DataFrame,
    prediction_year: int | None = None,
    *,
    window_id: str | None = None,
    observation_date_column: str,
    realization_date_column: str | None = None,
) -> pd.DataFrame:
    """为某预测年截取只落在 expanding 训练窗内的拟合/方向估计样本。

    若标签另有实现日，``realization_date_column`` 也必须不晚于 ``train_end``；
    因此训练窗最后一个月的 T+1 标签不会跨入验证窗。
    """
    required_window_columns = {"train_start", "train_end"}
    missing_windows = sorted(
        required_window_columns.difference(walk_forward_windows.columns)
    )
    if missing_windows:
        raise DataContractError(f"walk-forward 窗口缺少字段: {missing_windows}")
    required_data_columns = {observation_date_column}
    if realization_date_column is not None:
        required_data_columns.add(realization_date_column)
    missing_data = sorted(required_data_columns.difference(data.columns))
    if missing_data:
        raise DataContractError(f"训练数据缺少字段: {missing_data}")
    window = select_walk_forward_window(
        walk_forward_windows,
        prediction_year,
        window_id=window_id,
    )
    observation_dates = pd.to_datetime(
        data[observation_date_column], errors="coerce"
    )
    observation_periods = observation_dates.dt.to_period("M")
    train_start_period = pd.Timestamp(window["train_start"]).to_period("M")
    train_end_period = pd.Timestamp(window["train_end"]).to_period("M")
    mask = observation_periods.ge(train_start_period) & observation_periods.le(
        train_end_period
    )
    if realization_date_column is not None:
        realization_dates = pd.to_datetime(
            data[realization_date_column], errors="coerce"
        )
        mask &= realization_dates.notna() & realization_dates.dt.to_period(
            "M"
        ).le(
            train_end_period
        )
    result = data.loc[mask].copy()
    if not result.empty:
        if (
            pd.to_datetime(result[observation_date_column])
            .dt.to_period("M")
            .max()
            > train_end_period
        ):
            raise DataContractError("拟合样本观察日穿越 train_end")
        if (
            realization_date_column is not None
            and pd.to_datetime(result[realization_date_column])
            .dt.to_period("M")
            .max()
            > train_end_period
        ):
            raise DataContractError("拟合样本标签实现日穿越 train_end")
    return result


def fit_annual_frozen_factor_directions(
    scored_panel: pd.DataFrame,
    crosswalk: FactorCrosswalkResult,
    walk_forward_windows: pd.DataFrame,
    prediction_year: int | None = None,
    config: R006M1Config = DEFAULT_CONFIG,
    *,
    window_id: str | None = None,
) -> FrozenFactorDirections:
    """仅以 expanding 训练窗的逐月横截面 IC 估计方向并冻结一个预测周期。"""
    required = {
        config.stock_key,
        config.signal_date_key,
        "factor_id",
        "factor_value",
        "forward_return",
        "forward_return_date",
    }
    missing = sorted(required.difference(scored_panel.columns))
    if missing:
        raise DataContractError(f"方向估计面板缺少字段: {missing}")
    window = select_walk_forward_window(
        walk_forward_windows,
        prediction_year,
        window_id=window_id,
    )
    required_window_fields = {
        "window_id",
        "prediction_year",
        "prediction_start",
        "prediction_end",
        "train_start",
        "train_end",
    }
    missing_window_fields = sorted(
        required_window_fields.difference(window.index)
    )
    if missing_window_fields:
        raise DataContractError(
            f"方向冻结窗口缺少字段: {missing_window_fields}"
        )
    selected_window_id = str(window["window_id"])
    selected_prediction_year = int(window["prediction_year"])
    training = select_training_history(
        scored_panel,
        walk_forward_windows,
        window_id=selected_window_id,
        observation_date_column=config.signal_date_key,
        realization_date_column="forward_return_date",
    )
    mapped_factors = tuple(
        sorted(
            crosswalk.table.loc[
                crosswalk.table["mapping_status"].eq("mapped"), "factor_id"
            ].astype(str)
        )
    )
    training = training.loc[
        training["factor_id"].astype(str).isin(mapped_factors)
    ].copy()
    training["factor_value"] = pd.to_numeric(
        training["factor_value"], errors="coerce"
    )
    training["forward_return"] = pd.to_numeric(
        training["forward_return"], errors="coerce"
    )
    training = training.dropna(subset=["factor_value", "forward_return"])
    group_keys = ["factor_id", config.signal_date_key]
    counts = training.groupby(group_keys, observed=True)[config.stock_key].transform(
        "size"
    )
    usable = training.loc[counts.ge(config.direction_min_cross_section)]
    monthly_ic = (
        usable.groupby(group_keys, observed=True)
        .apply(
            lambda group: group["factor_value"].corr(group["forward_return"]),
            include_groups=False,
        )
        .rename("monthly_ic")
        .dropna()
        .reset_index()
    )
    estimates = (
        monthly_ic.groupby("factor_id", observed=True)["monthly_ic"]
        .agg(direction_estimate="mean", estimation_months="size")
        .reindex(mapped_factors)
        .reset_index()
    )
    missing_direction = estimates["direction_estimate"].isna()
    zero_direction = estimates["direction_estimate"].eq(0)
    if missing_direction.any() and config.direction_missing_policy == "fail":
        factor_ids = estimates.loc[missing_direction, "factor_id"].tolist()
        raise FormalDataUnavailableError(
            f"训练窗内无法估计因子方向: {factor_ids[:10]}"
        )
    if zero_direction.any() and config.direction_zero_policy == "fail":
        factor_ids = estimates.loc[zero_direction, "factor_id"].tolist()
        raise DataContractError(f"训练窗方向均值精确为零: {factor_ids[:10]}")
    estimates["direction"] = np.sign(estimates["direction_estimate"]).astype(
        "Int64"
    )
    estimates["window_id"] = selected_window_id
    estimates["prediction_year"] = selected_prediction_year
    estimates["crosswalk_sha256"] = crosswalk.sha256
    train_start = pd.Timestamp(window["train_start"])
    train_end = pd.Timestamp(window["train_end"])
    prediction_start = pd.Timestamp(window["prediction_start"])
    prediction_end = pd.Timestamp(window["prediction_end"])
    estimates["train_start"] = train_start
    estimates["train_end"] = train_end
    estimates["prediction_start"] = prediction_start
    estimates["prediction_end"] = prediction_end
    hash_columns = [
        "factor_id",
        "direction_estimate",
        "direction",
        "estimation_months",
        "window_id",
        "prediction_year",
        "crosswalk_sha256",
        "train_start",
        "train_end",
        "prediction_start",
        "prediction_end",
    ]
    records = (
        estimates[hash_columns]
        .sort_values("factor_id", kind="stable")
        .assign(
            train_start=lambda frame: frame["train_start"].dt.strftime("%Y-%m-%d"),
            train_end=lambda frame: frame["train_end"].dt.strftime("%Y-%m-%d"),
            prediction_start=lambda frame: frame[
                "prediction_start"
            ].dt.strftime("%Y-%m-%d"),
            prediction_end=lambda frame: frame[
                "prediction_end"
            ].dt.strftime("%Y-%m-%d"),
        )
        .to_dict(orient="records")
    )
    payload = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode(config.hash_encoding)
    digest = hashlib.new(config.direction_hash_algorithm)
    digest.update(payload)
    return FrozenFactorDirections(
        table=estimates.sort_values("factor_id", kind="stable").reset_index(
            drop=True
        ),
        sha256=digest.hexdigest(),
        crosswalk_sha256=crosswalk.sha256,
        window_id=selected_window_id,
        prediction_year=selected_prediction_year,
        prediction_start=prediction_start,
        prediction_end=prediction_end,
        train_start=train_start,
        train_end=train_end,
    )


def apply_annual_frozen_factor_directions(
    factor_panel: pd.DataFrame,
    frozen: FrozenFactorDirections,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """把已冻结方向应用于其完整 12 月预测块，不按自然年截断。"""
    required = {"factor_id", "factor_value", config.signal_date_key}
    missing = sorted(required.difference(factor_panel.columns))
    if missing:
        raise DataContractError(f"factor_panel 缺少方向应用字段: {missing}")
    frame = factor_panel.copy()
    signal_dates = pd.to_datetime(frame[config.signal_date_key], errors="coerce")
    signal_periods = signal_dates.dt.to_period("M")
    prediction_start_period = frozen.prediction_start.to_period("M")
    prediction_end_period = frozen.prediction_end.to_period("M")
    outside = signal_periods.lt(prediction_start_period) | signal_periods.gt(
        prediction_end_period
    )
    if outside.any():
        outside_months = sorted(
            signal_periods.loc[outside].dropna().astype(str).unique()
        )
        raise DataContractError(
            f"方向冻结表 {frozen.window_id} 不能应用于窗口外月份: "
            f"{outside_months[:6]}"
        )
    direction_table = frozen.table[
        ["factor_id", "direction", "direction_estimate"]
    ]
    output = frame.merge(
        direction_table,
        on="factor_id",
        how="left",
        validate="many_to_one",
    )
    if output["direction"].isna().any():
        missing_factors = sorted(
            output.loc[output["direction"].isna(), "factor_id"].astype(str).unique()
        )
        raise DataContractError(f"预测面板因子缺少冻结方向: {missing_factors[:10]}")
    output["directed_factor_value"] = (
        pd.to_numeric(output["factor_value"], errors="coerce")
        * output["direction"].astype(float)
    )
    output["direction_sha256"] = frozen.sha256
    output["direction_window_id"] = frozen.window_id
    output["direction_prediction_start"] = frozen.prediction_start
    output["direction_prediction_end"] = frozen.prediction_end
    return output


def _rolling_past_beta(
    returns: pd.DataFrame,
    benchmark: pd.Series,
    *,
    window: int,
    minimum_observations: int,
    variance_floor: float,
) -> pd.DataFrame:
    """用严格滞后一期的历史样本估计多列收益对基准的滚动 beta。"""
    lagged_returns = returns.shift(1)
    lagged_benchmark = benchmark.shift(1)
    covariance = lagged_returns.rolling(
        window, min_periods=minimum_observations
    ).cov(lagged_benchmark)
    variance = lagged_benchmark.rolling(
        window, min_periods=minimum_observations
    ).var()
    return covariance.div(variance, axis=0).where(
        variance.abs().gt(variance_floor), axis=0
    )


def run_sa11_sensitivity(
    sleeve_returns: pd.DataFrame,
    base_weights: pd.DataFrame,
    market_returns: pd.Series,
    config: R006M1Config = DEFAULT_CONFIG,
) -> SA11SensitivityResult:
    """在同一有效月份比较基准、额外滞后、市场残差、正交化与等权五条路径。"""
    if sleeve_returns.empty:
        raise DataContractError("SA11 sleeve_returns 为空")
    if not sleeve_returns.columns.equals(base_weights.columns):
        raise DataContractError("SA11 权重列与袖套收益列不一致")
    returns = sleeve_returns.apply(pd.to_numeric, errors="coerce").sort_index()
    weights = base_weights.reindex(returns.index).apply(
        pd.to_numeric, errors="coerce"
    )
    market = pd.to_numeric(
        market_returns.reindex(returns.index), errors="coerce"
    )
    periods = pd.PeriodIndex(pd.to_datetime(returns.index), freq="M")
    if periods.has_duplicates:
        raise DataContractError("SA11 月份索引重复")
    expected = pd.period_range(periods.min(), periods.max(), freq="M")
    if not periods.equals(expected):
        raise DataContractError("SA11 月份索引不连续")

    def _normalize_weights(frame: pd.DataFrame) -> pd.DataFrame:
        denominator = frame.abs().sum(axis=1).replace(0, np.nan)
        return frame.div(denominator, axis=0)

    normalized = _normalize_weights(weights)
    lagged_weights = _normalize_weights(
        weights.shift(config.sa11_extra_lag_months)
    )
    equal_weight_sleeve = returns.mean(axis=1)
    market_beta = _rolling_past_beta(
        returns,
        market,
        window=config.sa11_beta_window_months,
        minimum_observations=config.sa11_beta_min_observations,
        variance_floor=config.sa11_variance_floor,
    )
    market_residuals = returns - market_beta.mul(market, axis=0)
    orthogonal_beta = _rolling_past_beta(
        returns,
        equal_weight_sleeve,
        window=config.sa11_beta_window_months,
        minimum_observations=config.sa11_beta_min_observations,
        variance_floor=config.sa11_variance_floor,
    )
    orthogonalized = returns - orthogonal_beta.mul(
        equal_weight_sleeve, axis=0
    )
    paths = pd.DataFrame(
        {
            "base": (normalized * returns).sum(axis=1, min_count=1),
            "extra_lag": (lagged_weights * returns).sum(axis=1, min_count=1),
            "market_beta_residualized": (
                normalized * market_residuals
            ).sum(axis=1, min_count=1),
            "orthogonalized": (
                normalized * orthogonalized
            ).sum(axis=1, min_count=1),
            "equal_weight": equal_weight_sleeve,
        }
    ).dropna(how="any")
    if paths.empty:
        raise FormalDataUnavailableError("SA11 五条路径没有共同有效月份")
    summary = (
        paths.mean()
        .rename("mean_return")
        .to_frame()
        .assign(
            difference_vs_equal_weight=lambda frame: (
                frame["mean_return"]
                - float(frame.loc["equal_weight", "mean_return"])
            ),
            observations=len(paths),
        )
        .rename_axis("path")
        .reset_index()
    )
    exposure_audit = pd.concat(
        {
            "market": market_beta,
            "equal_weight_sleeve": orthogonal_beta,
        },
        names=["exposure_type", config.signal_date_key],
    ).reset_index().melt(
        id_vars=["exposure_type", config.signal_date_key],
        var_name="family",
        value_name="rolling_beta",
    )
    exposure_audit["beta_source_max_date"] = (
        pd.to_datetime(exposure_audit[config.signal_date_key])
        - pd.offsets.MonthEnd(1)
    )
    return SA11SensitivityResult(
        returns=paths,
        summary=summary,
        exposure_audit=exposure_audit,
    )


def build_point_in_time_audit(
    *,
    schedule: pd.DataFrame,
    factor_panel: pd.DataFrame | None = None,
    monthly_stock_panel: pd.DataFrame | None = None,
    financial_pit_panel: pd.DataFrame | None = None,
    macro_asof: pd.DataFrame | None = None,
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """汇总 T/T+1、股票源日、财务披露日与宏观可用日违规计数。"""
    rows: list[dict[str, Any]] = []

    def _append(
        check: str,
        frame: pd.DataFrame,
        source_column: str,
        signal_column: str,
        *,
        strict_later: bool = False,
    ) -> None:
        valid = frame[source_column].notna() & frame[signal_column].notna()
        if strict_later:
            violations = valid & frame[source_column].le(frame[signal_column])
        else:
            violations = valid & frame[source_column].gt(frame[signal_column])
        rows.append(
            {
                "check": check,
                "observations": int(valid.sum()),
                "violations": int(violations.sum()),
                "max_source_date": (
                    pd.to_datetime(frame.loc[valid, source_column]).max()
                    if valid.any()
                    else pd.NaT
                ),
                "max_signal_date": (
                    pd.to_datetime(frame.loc[valid, signal_column]).max()
                    if valid.any()
                    else pd.NaT
                ),
            }
        )

    _append(
        "execution_date_strictly_after_signal",
        schedule,
        "execution_date",
        config.signal_date_key,
        strict_later=True,
    )
    if factor_panel is not None and not factor_panel.empty:
        _append(
            "factor_source_not_after_signal",
            factor_panel,
            "source_date",
            config.signal_date_key,
        )
        factor_keys = [
            config.stock_key,
            config.signal_date_key,
            "factor_id",
        ]
        rows.append(
            {
                "check": "factor_stock_month_factor_unique",
                "observations": len(factor_panel),
                "violations": int(factor_panel.duplicated(factor_keys).sum()),
                "max_source_date": pd.to_datetime(
                    factor_panel["source_date"], errors="coerce"
                ).max(),
                "max_signal_date": pd.to_datetime(
                    factor_panel[config.signal_date_key], errors="coerce"
                ).max(),
            }
        )
    if monthly_stock_panel is not None and not monthly_stock_panel.empty:
        _append(
            "stock_source_not_after_signal",
            monthly_stock_panel,
            "signal_source_max_date",
            config.signal_date_key,
        )
    if financial_pit_panel is not None and not financial_pit_panel.empty:
        for column in financial_pit_panel.columns:
            if column.endswith("_info_publ_date"):
                _append(
                    f"{column}_not_after_signal",
                    financial_pit_panel,
                    column,
                    config.signal_date_key,
                )
    if macro_asof is not None and not macro_asof.empty:
        _append(
            "macro_available_not_after_signal",
            macro_asof,
            "available_date",
            config.signal_date_key,
        )
    return pd.DataFrame(rows)


def _empty_crosswalk_result() -> FactorCrosswalkResult:
    """元数据文件也缺失时供 dry-run 返回的空合同。"""
    return FactorCrosswalkResult(pd.DataFrame(), pd.DataFrame(), "")


def build_m1_dataset(
    config: R006M1Config = DEFAULT_CONFIG,
    *,
    dry_run: bool = False,
    factor_files: Sequence[Path] | None = None,
    index_code: str | None = None,
) -> M1Dataset:
    """构建完整 m1 数据合同，或只执行 schema/crosswalk dry-run。

    正式模式读取实际因子、股票、财务、宏观和显式基准指数；任何正式源缺失即停止。
    """
    source_audit = audit_local_sources(config)
    substitutions = build_substitution_manifest(config)
    issues = list(source_audit.issues)
    metadata_spec = _source_by_key(config)["factor_metadata"]
    metadata_path = config.data_root / metadata_spec.relative_path
    if metadata_path.is_file():
        factor_metadata = pd.read_parquet(
            metadata_path,
            columns=["factor_id", "factor_id_cn", "level1", "level2"],
        )
        try:
            crosswalk = build_factor_crosswalk(
                factor_metadata, config, strict=True
            )
        except DataContractError as exc:
            issues.append(str(exc))
            crosswalk = build_factor_crosswalk(
                factor_metadata, config, strict=False
            )
    else:
        factor_metadata = pd.DataFrame()
        crosswalk = _empty_crosswalk_result()

    empty = pd.DataFrame()
    if dry_run:
        return M1Dataset(
            source_audit=source_audit,
            substitution_manifest=substitutions,
            factor_crosswalk=crosswalk,
            factor_panel=empty.copy(),
            factor_availability=empty.copy(),
            fixed_factor_universe=(),
            publication_coverage=empty.copy(),
            execution_schedule=empty.copy(),
            monthly_stock_panel=empty.copy(),
            financial_pit_panel=empty.copy(),
            macro_inputs=empty.copy(),
            macro_asof=empty.copy(),
            index_state_inputs=empty.copy(),
            capacity_control_panel=empty.copy(),
            common_month_index=pd.DatetimeIndex([], name=config.signal_date_key),
            common_month_diagnostics=empty.copy(),
            walk_forward_windows=empty.copy(),
            point_in_time_audit=empty.copy(),
            issues=tuple(issues),
            dry_run=True,
        )

    assert_formal_sources_available(source_audit)
    validate_factor_crosswalk(crosswalk, config)
    raw_factor_panel = load_local_factor_panel(
        factor_metadata, config, files=factor_files
    )
    valid_factor_dates = raw_factor_panel.loc[
        raw_factor_panel["factor_value"].notna(), "source_date"
    ]
    if valid_factor_dates.empty:
        raise FormalDataUnavailableError("正式因子面板没有任何非缺失值")
    factor_start = (
        pd.to_datetime(valid_factor_dates).min().to_period("M").to_timestamp("M")
    )
    factor_end = (
        pd.to_datetime(valid_factor_dates).max().to_period("M").to_timestamp("M")
    )
    calendar = load_trade_calendar(
        config.data_root,
        start_date=str(factor_start.to_period("M").start_time.date()),
        end_date=str(
            (factor_end + pd.DateOffset(months=config.monthly_macro_lag_months)).date()
        ),
    )
    schedule = build_execution_schedule(calendar, config)
    factor_alignment = align_factor_panel_to_schedule(
        raw_factor_panel, schedule, config, strict=True
    )
    factor_panel = factor_alignment.table
    factor_availability = compute_factor_availability(
        factor_panel, crosswalk, config
    )
    monthly_stock = load_monthly_stock_panel(factor_start, factor_end, config)
    if monthly_stock.empty:
        raise FormalDataUnavailableError("因子覆盖区间内没有 A 股股票月面板")
    index_inputs = load_index_state_inputs(
        calendar, config, index_code=index_code
    )
    external_macro_inputs = load_macro_conditioning_inputs(config)
    market_macro_inputs = build_market_macro_inputs(index_inputs, config)
    macro_inputs = pd.concat(
        [external_macro_inputs, market_macro_inputs], ignore_index=True
    )
    ensure_macro_block_coverage(macro_inputs, config)
    macro_asof = align_macro_asof(
        schedule[config.signal_date_key], macro_inputs, config
    )
    common_month_result = build_common_month_index(
        factor_panel,
        monthly_stock,
        macro_asof,
        index_inputs,
        config,
        return_diagnostics=True,
    )
    if not isinstance(common_month_result, CommonMonthResult):
        raise DataContractError("共同月构建未返回诊断合同")
    common_month_index = common_month_result.month_index
    windows = build_walk_forward_windows(
        common_month_index, config, strict=True
    )
    common_start = common_month_index.min()
    prediction_years = windows["prediction_year"].astype(int).tolist()
    publication_coverage = build_publication_year_coverage(
        factor_availability, prediction_years, config
    )
    fixed_factor_universe = freeze_main_factor_universe(
        factor_availability, common_start
    )
    if not fixed_factor_universe:
        raise FormalDataUnavailableError("共同起点前没有可冻结的本地主测试因子")
    signal_keys = monthly_stock.loc[
        monthly_stock[config.signal_date_key].dt.to_period("M").isin(
            common_month_index.to_period("M")
        ),
        [config.stock_key, config.signal_date_key],
    ].drop_duplicates()
    financial = load_financial_pit_panel(signal_keys, config)
    industry_pit = load_industry_pit_mapping(signal_keys, config)
    capacity_controls = build_capacity_control_panel(
        monthly_stock,
        index_inputs,
        industry_pit,
        config,
    )
    pit_audit = build_point_in_time_audit(
        schedule=schedule,
        factor_panel=factor_panel,
        monthly_stock_panel=monthly_stock,
        financial_pit_panel=financial,
        macro_asof=macro_asof,
        config=config,
    )
    if pit_audit["violations"].sum() != 0:
        raise DataContractError("m1 point-in-time 审计存在违规")
    return M1Dataset(
        source_audit=source_audit,
        substitution_manifest=substitutions,
        factor_crosswalk=crosswalk,
        factor_panel=factor_panel,
        factor_availability=factor_availability,
        fixed_factor_universe=fixed_factor_universe,
        publication_coverage=publication_coverage,
        execution_schedule=schedule,
        monthly_stock_panel=monthly_stock,
        financial_pit_panel=financial,
        macro_inputs=macro_inputs,
        macro_asof=macro_asof,
        index_state_inputs=index_inputs,
        capacity_control_panel=capacity_controls,
        common_month_index=common_month_index,
        common_month_diagnostics=common_month_result.diagnostics,
        walk_forward_windows=windows,
        point_in_time_audit=pit_audit,
        issues=tuple(issues),
        dry_run=False,
    )
