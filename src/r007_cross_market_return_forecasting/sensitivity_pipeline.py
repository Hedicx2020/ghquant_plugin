"""r007 m5：R2 与 SA1–SA7 的可复用敏感性计算接口。

本模块只消费 m1–m4 已固定的股票池、日期、标签、图快照和组合字段。
主结果参数不会根据敏感性结果回写；除 R2 外仅输出观测量与方向性证据，
不包含通过/失败裁决。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import product
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from common.ml_pipeline import fit_regression_model_batch
from common.ml_portfolio import (
    SignedLiquidityPortfolioResult,
    SignedLiquidityPortfolioSettings,
    run_signed_liquidity_portfolios,
)

from .config import DEFAULT_M5_CONFIG, M3Config, M5Config
from .data_pipeline import build_causal_calendar_mapping
from .graph_pipeline import (
    GraphSnapshot,
    build_daily_feature_audit,
    build_feature_mapping,
    build_sparse_biadjacency,
    materialize_target_feature_batch,
    summarize_target_indegree,
)
from .portfolio_pipeline import (
    align_three_specifications,
    audit_execution_timing,
    enforce_complete_ten_model_groups,
)
from .strategy import build_ensemble_predictions, initialize_base_estimators


@dataclass
class RandomizedEdgeResult:
    """固定一个图快照和替换比例的边表及守恒审计。"""

    edges: pd.DataFrame
    audit: pd.DataFrame


@dataclass
class RandomizedSnapshotResult:
    """随机化后的图快照及逐目标边替换证据。"""

    snapshot: GraphSnapshot
    audit: pd.DataFrame


@dataclass
class JointPredictionResult:
    """SA7 单个联合快照的预测及混合时点审计。"""

    predictions: pd.DataFrame
    training_audit: pd.DataFrame
    model_audit: pd.DataFrame


@dataclass
class SingleModelPredictionResult:
    """SA3 单模型/单快照的预测与拟合审计。"""

    predictions: pd.DataFrame
    model_audit: pd.DataFrame


@dataclass
class ModelMedianSharpeResult:
    """SA1/SA2 十模型中位数及完整模型集合审计。"""

    summary: pd.DataFrame
    audit: pd.DataFrame


@dataclass
class IndustryMappingResult:
    """AS4 中信一级确定性去重结果及原始重复证据。"""

    mapping: pd.DataFrame
    summary_audit: pd.DataFrame
    duplicate_rows: pd.DataFrame


@dataclass
class CNThreeSpecificationResult:
    """SA4 单一 CN 目标腿的三规格组合及可比性审计。"""

    predictions: pd.DataFrame
    model_completeness_audit: pd.DataFrame
    comparability_audit: pd.DataFrame
    execution_timing_audit: pd.DataFrame
    portfolios: SignedLiquidityPortfolioResult


@dataclass
class SA7ComparisonResult:
    """SA7 联合规格与同样本 US-only 基线的严格配对证据。"""

    paired: pd.DataFrame
    audit: pd.DataFrame
    summary: pd.DataFrame


class R2ConfigurationCoverageError(ValueError):
    """R2 聚合前配置出口不完整，并保留未过滤的逐行审计表。"""

    def __init__(self, message: str, audit: pd.DataFrame) -> None:
        super().__init__(message)
        self.audit = audit.reset_index(drop=True).copy()


def _require_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
    context: str,
) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise KeyError(f"{context} 缺少字段: {missing}")


def _stable_seed(
    base_seed: int,
    *parts: str | int | float | pd.Timestamp,
) -> int:
    payload = "\x1f".join(str(part) for part in (base_seed, *parts))
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**32)


def build_hyperparameter_grid(
    *,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> pd.DataFrame:
    """按 AS7 展开七模型完整网格，多参数模型使用笛卡尔积。"""
    rows: list[dict[str, Any]] = []
    for model, parameter_axes in config.sensitivity.hyperparameter_grid:
        names = tuple(name for name, _ in parameter_axes)
        axes = tuple(values for _, values in parameter_axes)
        for configuration_number, values in enumerate(product(*axes), start=1):
            parameters = dict(zip(names, values, strict=True))
            payload = json.dumps(
                parameters,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            rows.append(
                {
                    "model": model,
                    "configuration_number": configuration_number,
                    "configuration_id": hashlib.sha256(
                        f"{model}:{payload}".encode("utf-8")
                    ).hexdigest()[:16],
                    "parameters_json": payload,
                    **parameters,
                }
            )
    grid = pd.DataFrame(rows)
    expected_counts = {
        "LASSO": 8,
        "RIDGE": 8,
        "SVM": 5,
        "XGBoost": 27,
        "LGBM": 27,
        "RF": 9,
        "AdaBoost": 27,
    }
    observed = grid.groupby("model", sort=False).size().to_dict()
    if observed != expected_counts:
        raise AssertionError(
            f"SA3 笛卡尔积配置数不一致: actual={observed}, "
            f"expected={expected_counts}"
        )
    if len(grid) != config.sensitivity.hyperparameter_configuration_count:
        raise AssertionError("SA3 超参数配置总数与集中配置不一致")
    return grid


def build_hyperparameter_factory(
    model: str,
    parameters: Mapping[str, Any],
    *,
    m3_config: M3Config,
) -> Callable[[], Any]:
    """以 AS15 主快照为原型，只覆盖当前 SA3 格子的声明参数。"""
    prototypes = initialize_base_estimators(m3_config, check_versions=False)
    if model not in prototypes:
        raise KeyError(f"SA3 未登记模型: {model}")
    from sklearn.base import clone

    prototype = clone(prototypes[model])
    prototype.set_params(**dict(parameters))
    return lambda: clone(prototype)


def predict_snapshot_single_model(
    snapshot: GraphSnapshot,
    source_panel: pd.DataFrame,
    target_panel: pd.DataFrame,
    *,
    model: str,
    model_factory: Callable[[], Any],
    config: M5Config = DEFAULT_M5_CONFIG,
) -> SingleModelPredictionResult:
    """SA3 复用冻结图与 complete-case 口径，仅拟合当前网格模型。"""
    target_actual = target_panel.loc[
        pd.to_datetime(target_panel["date"], errors="raise")
        .dt.normalize()
        .isin(snapshot.prediction_dates),
        ["stock_code", "date", config.m4.m3.prediction.target_value_column],
    ].rename(
        columns={
            "stock_code": "target_code",
            "date": "target_date",
            config.m4.m3.prediction.target_value_column: "actual_return",
        }
    )
    target_actual["target_code"] = target_actual["target_code"].astype(str)
    target_actual["target_date"] = pd.to_datetime(
        target_actual["target_date"], errors="raise"
    ).dt.normalize()
    prediction_parts: list[pd.DataFrame] = []
    audit_parts: list[pd.DataFrame] = []
    for target_code in snapshot.feature_mapping["target_code"].astype(str):
        batch = materialize_target_feature_batch(
            snapshot,
            source_panel,
            target_panel,
            target_code=target_code,
            source_value_column=config.m4.m3.prediction.source_value_column,
            target_value_column=config.m4.m3.prediction.target_value_column,
            config=config.m4.m3.pipeline,
        )
        if not batch.feature_columns:
            batch_row = batch.audit.iloc[0]
            audit_parts.append(
                pd.DataFrame(
                    [
                        {
                            "direction": snapshot.direction,
                            "anchor_date": snapshot.anchor_date,
                            "target_code": target_code,
                            "model": model,
                            "feature_count": 0,
                            "training_input_rows": int(
                                batch_row["training_input_rows"]
                            ),
                            "training_complete_rows": 0,
                            "training_dropped_rows": int(
                                batch_row["training_dropped_rows"]
                            ),
                            "required_training_rows": 0,
                            "training_fit_start": pd.NaT,
                            "training_fit_end": pd.NaT,
                            "prediction_input_rows": int(
                                batch_row["prediction_rows"]
                            ),
                            "prediction_complete_rows": 0,
                            "prediction_missing_rows": int(
                                batch_row["prediction_missing_rows"]
                            ),
                            "prediction_start": min(snapshot.prediction_dates),
                            "prediction_end": max(snapshot.prediction_dates),
                            "fit_end_strictly_before_prediction": pd.NA,
                            "estimator_class": pd.NA,
                            "status": "skipped_no_inbound_edges",
                            "error_type": pd.NA,
                            "error_message": pd.NA,
                            "transaction_status": (
                                "skipped_no_inbound_edges"
                            ),
                            "failed_models": pd.NA,
                        }
                    ]
                )
            )
            continue
        regression = fit_regression_model_batch(
            batch.training_frame,
            batch.prediction_frame,
            feature_columns=batch.feature_columns,
            target_column=config.m4.m3.prediction.target_column,
            model_factories={model: model_factory},
            prediction_key_columns=("target_date", "source_date"),
            training_date_column="target_date",
            prediction_date_column="target_date",
        )
        audit = regression.model_audit.copy()
        audit.insert(0, "target_code", target_code)
        audit.insert(0, "anchor_date", snapshot.anchor_date)
        audit.insert(0, "direction", snapshot.direction)
        audit_parts.append(audit)
        if regression.predictions.empty:
            continue
        prediction = regression.predictions.copy()
        prediction.insert(0, "target_code", target_code)
        prediction.insert(0, "anchor_date", snapshot.anchor_date)
        prediction.insert(0, "direction", snapshot.direction)
        prediction_parts.append(prediction)
    predictions = (
        pd.concat(prediction_parts, ignore_index=True)
        if prediction_parts
        else pd.DataFrame()
    )
    if not predictions.empty:
        predictions = predictions.merge(
            target_actual,
            on=["target_code", "target_date"],
            how="left",
            validate="many_to_one",
        )
    return SingleModelPredictionResult(
        predictions=predictions,
        model_audit=(
            pd.concat(audit_parts, ignore_index=True)
            if audit_parts
            else pd.DataFrame()
        ),
    )


def build_r2_reference_table(
    *,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> pd.DataFrame:
    """把 spec R2 的 42 个精确均值/标准差格转换成长表。"""
    portfolios = tuple(
        name for name, _ in config.m4.portfolio.portfolio_fractions
    )
    rows = [
        {
            "element_id": "R2",
            "model": model,
            "portfolio": portfolio,
            "reference_mean": float(means[index]),
            "reference_std": float(stds[index]),
            "reference_source": "spec.md R2 Table A.1 p36",
        }
        for model, means, stds in config.sensitivity.r2_reference
        for index, portfolio in enumerate(portfolios)
    ]
    reference = pd.DataFrame(rows)
    if len(reference) != config.sensitivity.r2_reference_cell_count:
        raise AssertionError("R2 精确参考表必须包含七模型×六组合共42格")
    return reference


def summarize_hyperparameter_sharpe(
    configuration_results: pd.DataFrame,
    *,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """先硬核验完整 111×6 出口，再按 AS7 聚合，禁止过滤失败行。"""
    required = (
        "model",
        "configuration_id",
        "portfolio",
        "annualized_sharpe",
        "sharpe_status",
    )
    _require_columns(configuration_results, required, "SA3 配置结果")
    expected_grid = build_hyperparameter_grid(config=config)
    portfolios = tuple(
        name for name, _ in config.m4.portfolio.portfolio_fractions
    )
    expected_rows = (
        expected_grid.loc[
            :, ["configuration_id", "model", "parameters_json"]
        ]
        .rename(
            columns={
                "model": "expected_model",
                "parameters_json": "expected_parameters_json",
            }
        )
        .merge(pd.DataFrame({"portfolio": portfolios}), how="cross")
    )
    expected_total_rows = (
        config.sensitivity.hyperparameter_configuration_count
        * len(portfolios)
    )
    if (
        len(expected_grid)
        != config.sensitivity.hyperparameter_configuration_count
        or len(expected_rows) != expected_total_rows
    ):
        raise AssertionError("SA3 先验网格必须严格为 111×6=666 行")
    actual = configuration_results.copy()
    actual["configuration_id"] = actual["configuration_id"].astype(str)
    actual["model"] = actual["model"].astype(str)
    actual["portfolio"] = actual["portfolio"].astype(str)
    duplicate_mask = actual.duplicated(
        ["configuration_id", "portfolio"],
        keep=False,
    )
    actual["_sharpe_numeric"] = pd.to_numeric(
        actual["annualized_sharpe"], errors="coerce"
    )
    row_audit = expected_rows.merge(
        actual.loc[
            :,
            [
                "configuration_id",
                "portfolio",
                "model",
                "sharpe_status",
                "_sharpe_numeric",
            ],
        ],
        on=["configuration_id", "portfolio"],
        how="outer",
        indicator="configuration_row_merge",
    )
    row_audit["model_ownership_correct"] = row_audit["model"].eq(
        row_audit["expected_model"]
    )
    row_audit["sharpe_status_ok"] = row_audit["sharpe_status"].astype(
        "string"
    ).eq("ok")
    row_audit["sharpe_finite"] = np.isfinite(
        pd.to_numeric(
            row_audit["_sharpe_numeric"], errors="coerce"
        ).to_numpy(dtype=float)
    )
    row_audit["unique_configuration_portfolio_row"] = ~row_audit.duplicated(
        ["configuration_id", "portfolio"],
        keep=False,
    )
    row_audit["status"] = np.where(
        row_audit["configuration_row_merge"].astype(str).eq("both")
        & row_audit["model_ownership_correct"]
        & row_audit["sharpe_status_ok"]
        & row_audit["sharpe_finite"]
        & row_audit["unique_configuration_portfolio_row"],
        "complete",
        "incomplete",
    )
    hard_gate_complete = (
        len(actual) == expected_total_rows
        and not duplicate_mask.any()
        and len(row_audit) == expected_total_rows
        and row_audit["status"].eq("complete").all()
    )
    row_audit["expected_total_rows"] = expected_total_rows
    row_audit["observed_total_rows"] = len(actual)
    row_audit["full_configuration_grid_complete"] = hard_gate_complete
    if not hard_gate_complete:
        failed = row_audit.loc[~row_audit["status"].eq("complete")]
        raise R2ConfigurationCoverageError(
            "R2 聚合前 111×6 完整配置门禁失败: "
            f"observed_rows={len(actual)}, duplicate_rows={int(duplicate_mask.sum())}, "
            f"failed={failed.head(20).to_dict(orient='records')}",
            row_audit,
        )

    expected_by_model = (
        expected_grid.groupby("model", sort=False)["configuration_id"]
        .nunique()
        .rename("expected_configuration_count")
        .reset_index()
    )
    summary = (
        actual.groupby(["model", "portfolio"], observed=True, sort=False)
        .agg(
            observed_configuration_count=("configuration_id", "nunique"),
            reproduced_mean=("_sharpe_numeric", "mean"),
            reproduced_std=("_sharpe_numeric", "std"),
            minimum_sharpe=("_sharpe_numeric", "min"),
            maximum_sharpe=("_sharpe_numeric", "max"),
        )
        .reset_index()
        .merge(expected_by_model, on="model", how="left", validate="many_to_one")
    )
    summary["configuration_set_complete"] = summary[
        "observed_configuration_count"
    ].eq(summary["expected_configuration_count"])
    if len(summary) != 42 or not summary[
        "configuration_set_complete"
    ].all():
        raise ValueError("R2 42 个模型×组合汇总格配置集合不完整")
    return summary, row_audit


def build_r2_comparison(
    hyperparameter_summary: pd.DataFrame,
    *,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> pd.DataFrame:
    """逐格对齐 R2 精确数值，输出偏差但不设置裁决字段。"""
    required = (
        "model",
        "portfolio",
        "reproduced_mean",
        "reproduced_std",
        "observed_configuration_count",
        "expected_configuration_count",
        "configuration_set_complete",
    )
    _require_columns(hyperparameter_summary, required, "R2 复现汇总")
    reference = build_r2_reference_table(config=config)
    comparison = reference.merge(
        hyperparameter_summary.loc[:, list(required)],
        on=["model", "portfolio"],
        how="outer",
        validate="one_to_one",
        indicator="reference_merge_status",
    )
    complete_merge = comparison["reference_merge_status"].astype(str).eq(
        "both"
    )
    finite_values = np.isfinite(
        comparison.loc[
            :,
            ["reproduced_mean", "reproduced_std"],
        ]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy(dtype=float)
    ).all(axis=1)
    complete_configurations = comparison[
        "configuration_set_complete"
    ].fillna(False)
    if (
        len(comparison) != config.sensitivity.r2_reference_cell_count
        or not complete_merge.all()
        or not finite_values.all()
        or not complete_configurations.all()
    ):
        raise ValueError(
            "R2 参考表逐格合并门禁失败: "
            f"{comparison.loc[~(complete_merge & finite_values & complete_configurations)].head(20).to_dict(orient='records')}"
        )
    comparison["mean_deviation"] = (
        comparison["reproduced_mean"] - comparison["reference_mean"]
    )
    comparison["std_deviation"] = (
        comparison["reproduced_std"] - comparison["reference_std"]
    )
    comparison["mean_absolute_deviation"] = comparison["mean_deviation"].abs()
    comparison["std_absolute_deviation"] = comparison["std_deviation"].abs()
    comparison["comparison_scope"] = (
        "逐格精确数值对照；最终容差与判定由 verifier/check_gates 执行"
    )
    return comparison


def randomly_replace_graph_edges(
    edges: pd.DataFrame,
    *,
    source_codes: Sequence[str],
    replacement_fraction: float,
    seed: int,
) -> RandomizedEdgeResult:
    """SA1 仅用原图未连接源节点替换边，并严格保持每个目标入度。"""
    _require_columns(edges, ("source_code", "target_code"), "SA1 原始边表")
    if not 0.0 <= replacement_fraction <= 1.0:
        raise ValueError("边替换比例必须位于 [0, 1]")
    sources = tuple(dict.fromkeys(str(value) for value in source_codes))
    if not sources:
        raise ValueError("SA1 源节点集合为空")
    if edges.duplicated(["source_code", "target_code"]).any():
        raise ValueError("SA1 原始边表存在重复边")
    unknown = set(edges["source_code"].astype(str)) - set(sources)
    if unknown:
        raise KeyError(f"SA1 边表含源节点全集外代码: {sorted(unknown)[:10]}")

    randomized_parts: list[pd.DataFrame] = []
    audit_rows: list[dict[str, Any]] = []
    for target_code, target_edges in edges.groupby(
        "target_code",
        observed=True,
        sort=True,
    ):
        group = target_edges.copy().reset_index(drop=True)
        original_sources = tuple(group["source_code"].astype(str))
        degree = len(group)
        requested = int(np.rint(degree * replacement_fraction))
        disconnected = tuple(sorted(set(sources) - set(original_sources)))
        if requested > len(disconnected):
            raise ValueError(
                f"目标 {target_code} 入度 {degree}、未连接源节点 "
                f"{len(disconnected)}，无法按 {replacement_fraction:.0%} "
                "仅用原先未连接节点完成替换"
            )
        local_seed = _stable_seed(
            seed,
            str(target_code),
            f"{replacement_fraction:.10f}",
        )
        generator = np.random.default_rng(local_seed)
        if requested:
            removed_positions = np.sort(
                generator.choice(degree, size=requested, replace=False)
            )
            replacements = generator.choice(
                np.asarray(disconnected, dtype=object),
                size=requested,
                replace=False,
            )
            group.loc[removed_positions, "source_code"] = replacements
        else:
            removed_positions = np.asarray([], dtype=np.int64)
        if group.duplicated(["source_code", "target_code"]).any():
            raise AssertionError("SA1 随机替换后产生重复边")
        randomized_parts.append(group)
        audit_rows.append(
            {
                "target_code": str(target_code),
                "replacement_fraction_requested": replacement_fraction,
                "original_edge_count": degree,
                "requested_replacement_count": requested,
                "realized_replacement_count": requested,
                "realized_replacement_fraction": (
                    requested / degree if degree else np.nan
                ),
                "originally_disconnected_source_count": len(disconnected),
                "target_indegree_preserved": len(group) == degree,
                "replacement_uses_only_previously_disconnected_sources": bool(
                    set(group["source_code"].astype(str)) - set(original_sources)
                    <= set(disconnected)
                ),
                "seed": int(local_seed),
            }
        )
    randomized = (
        pd.concat(randomized_parts, ignore_index=True)
        if randomized_parts
        else edges.copy()
    )
    audit = pd.DataFrame(audit_rows)
    if len(randomized) != len(edges):
        raise AssertionError("SA1 随机化前后总边数不一致")
    return RandomizedEdgeResult(edges=randomized, audit=audit)


def randomize_graph_snapshot(
    snapshot: GraphSnapshot,
    *,
    replacement_fraction: float,
    seed: int,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> RandomizedSnapshotResult:
    """把 SA1 边随机化结果回装为 m3 可直接消费的 GraphSnapshot。"""
    randomized = randomly_replace_graph_edges(
        snapshot.edges,
        source_codes=snapshot.adjacency.source_codes,
        replacement_fraction=replacement_fraction,
        seed=_stable_seed(
            seed,
            snapshot.direction,
            snapshot.anchor_date,
            replacement_fraction,
        ),
    )
    adjacency = build_sparse_biadjacency(
        randomized.edges,
        source_codes=snapshot.adjacency.source_codes,
        target_codes=snapshot.adjacency.target_codes,
    )
    indegree, indegree_quantiles = summarize_target_indegree(
        randomized.edges,
        direction=snapshot.direction,
        anchor_date=snapshot.anchor_date,
        target_codes=snapshot.adjacency.target_codes,
    )
    feature_mapping = build_feature_mapping(
        randomized.edges,
        direction=snapshot.direction,
        anchor_date=snapshot.anchor_date,
        target_codes=snapshot.adjacency.target_codes,
    )
    daily_feature_audit = build_daily_feature_audit(
        feature_mapping,
        direction=snapshot.direction,
        anchor_date=snapshot.anchor_date,
        prediction_dates=snapshot.prediction_dates,
    )
    graph_audit = snapshot.graph_audit.copy()
    graph_audit["sensitivity_id"] = "SA1"
    graph_audit["replacement_fraction"] = replacement_fraction
    graph_audit["original_edge_count"] = snapshot.adjacency.nnz
    graph_audit["randomized_edge_count"] = adjacency.nnz
    graph_audit["total_indegree_preserved"] = (
        snapshot.adjacency.nnz == adjacency.nnz
    )
    audit = randomized.audit.copy()
    audit.insert(0, "anchor_date", snapshot.anchor_date)
    audit.insert(0, "direction", snapshot.direction)
    return RandomizedSnapshotResult(
        snapshot=replace(
            snapshot,
            edges=randomized.edges,
            adjacency=adjacency,
            feature_mapping=feature_mapping,
            indegree=indegree,
            indegree_quantiles=indegree_quantiles,
            graph_audit=graph_audit,
            daily_feature_audit=daily_feature_audit,
        ),
        audit=audit,
    )


def build_information_lag_mapping(
    target_calendar: pd.DataFrame,
    source_calendar: pd.DataFrame,
    *,
    lag: int,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> pd.DataFrame:
    """SA2 将 US→CN 最近已完成源日进一步回移到第 ``lag`` 个源日。"""
    if lag < 1:
        raise ValueError("US→CN 的 SA2 信息滞后必须至少为1")
    base_direction = config.m4.m3.pipeline.calendar.direction("US_TO_CN")
    direction = replace(base_direction, lag_parameter=lag)
    mapping = build_causal_calendar_mapping(
        target_calendar,
        source_calendar,
        direction=direction,
        calendar_config=config.m4.m3.pipeline.calendar,
    )
    source_dates = pd.DatetimeIndex(
        pd.to_datetime(source_calendar["date"], errors="raise")
        .dt.normalize()
        .drop_duplicates()
        .sort_values()
    )
    positions = pd.Series(
        np.arange(len(source_dates), dtype=np.int64),
        index=source_dates,
    )
    base_positions = mapping["source_date"].map(positions)
    shifted_positions = base_positions - (lag - 1)
    available = shifted_positions.notna() & shifted_positions.ge(0)
    shifted_source_date = pd.Series(pd.NaT, index=mapping.index, dtype="datetime64[ns]")
    shifted_source_date.loc[available] = source_dates.take(
        shifted_positions.loc[available].astype("int64")
    ).to_numpy()
    mapping["source_date"] = shifted_source_date

    source_session = config.m4.m3.pipeline.calendar.session("US")
    naive_close = pd.DatetimeIndex(
        shifted_source_date.loc[available]
        + pd.to_timedelta(source_session.close_time)
    )
    source_close = pd.Series(pd.NaT, index=mapping.index, dtype="datetime64[ns, UTC]")
    source_close.loc[available] = naive_close.tz_localize(
        ZoneInfo(source_session.timezone),
        ambiguous="raise",
        nonexistent="raise",
    ).tz_convert("UTC")
    mapping["source_close_utc"] = source_close
    mapping["lag_parameter"] = lag
    mapping["causal_available"] = available
    mapping["information_age_hours"] = (
        mapping["target_open_utc"] - mapping["source_close_utc"]
    ).dt.total_seconds() / 3600.0
    violation = mapping["source_close_utc"].notna() & mapping[
        "source_close_utc"
    ].ge(mapping["target_open_utc"])
    if violation.any():
        raise AssertionError("SA2 信息滞后映射含目标开盘后源信息")
    mapping["history_only"] = ~violation
    return mapping


def run_sensitivity_portfolios(
    predictions: pd.DataFrame,
    *,
    group_columns: Sequence[str],
    portfolio_fractions: Sequence[tuple[str, float]] | None = None,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> SignedLiquidityPortfolioResult:
    """复用 m4 完全相同的容量、PnL、年化与 T+1 已准备字段。"""
    fractions = tuple(
        portfolio_fractions or config.m4.portfolio.portfolio_fractions
    )
    settings = SignedLiquidityPortfolioSettings(
        group_columns=tuple(group_columns),
        date_column="target_date",
        stock_column="target_code",
        prediction_column="prediction",
        realized_return_column="actual_return",
        liquidity_column="historical_liquidity",
        market_column="target_market",
        portfolio_fractions=fractions,
        participation_rate=config.m4.portfolio.liquidity_participation_rate,
        market_position_caps=config.m4.portfolio.position_caps(),
        periods_per_year=config.m4.portfolio.annualization_days,
        minimum_sharpe_observations=(
            config.m4.portfolio.minimum_sharpe_observations
        ),
        transaction_cost_rate=config.m4.portfolio.transaction_cost_rate,
    )
    return run_signed_liquidity_portfolios(predictions, settings)


def run_cn_three_specification_portfolios(
    specification_frames: Mapping[str, pd.DataFrame],
    *,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> CNThreeSpecificationResult:
    """SA4 只比较 CN 三规格，不调用要求 CN/US 双腿齐全的 m4 总入口。"""
    expected_specs = config.m4.baseline.specifications
    if set(specification_frames) != set(expected_specs):
        raise ValueError(
            "SA4 三规格名称不完整: "
            f"actual={sorted(specification_frames)}, "
            f"expected={sorted(expected_specs)}"
        )
    parts: list[pd.DataFrame] = []
    for specification in expected_specs:
        frame = specification_frames[specification].copy()
        _require_columns(
            frame,
            ("specification", "target_market", "direction"),
            f"SA4 {specification}",
        )
        if set(frame["specification"].astype(str)) != {specification}:
            raise ValueError(f"SA4 {specification} 输入规格字段不唯一")
        if set(frame["target_market"].astype(str)) != {"CN"}:
            raise ValueError("SA4 单方向装配只允许 target_market=CN")
        expected_direction = config.m4.baseline.expected_direction(
            specification,
            "CN",
        )
        if set(frame["direction"].astype(str)) != {expected_direction}:
            raise ValueError(
                f"SA4 {specification} 方向不是 {expected_direction}"
            )
        parts.append(frame)
    combined = pd.concat(parts, ignore_index=True)
    complete = enforce_complete_ten_model_groups(
        combined,
        config=config.m4,
    )
    comparable = align_three_specifications(
        complete.predictions,
        config=config.m4,
    )
    if comparable.predictions.empty:
        raise ValueError("SA4 CN 三规格无共同日期/股票可进入组合")
    timing = audit_execution_timing(
        comparable.predictions,
        config=config.m4,
    )
    portfolios = run_sensitivity_portfolios(
        comparable.predictions,
        group_columns=(
            "specification",
            "feature_set",
            "direction",
            "target_market",
            "model",
        ),
        config=config,
    )
    return CNThreeSpecificationResult(
        predictions=comparable.predictions,
        model_completeness_audit=complete.audit,
        comparability_audit=comparable.audit,
        execution_timing_audit=timing,
        portfolios=portfolios,
    )


def summarize_model_median_sharpe(
    sharpe_metrics: pd.DataFrame,
    *,
    sensitivity_columns: Sequence[str],
    config: M5Config = DEFAULT_M5_CONFIG,
) -> ModelMedianSharpeResult:
    """SA1/SA2 仅在精确十模型均有效时计算每个 qr 的中位数。"""
    required = (
        *sensitivity_columns,
        "portfolio",
        "model",
        "annualized_sharpe",
        "sharpe_status",
    )
    _require_columns(sharpe_metrics, required, "敏感性 Sharpe")
    expected_models = config.m4.m3.prediction.all_model_names
    expected_set = frozenset(expected_models)
    working = sharpe_metrics.copy()
    working["model"] = working["model"].astype(str)
    working["annualized_sharpe"] = pd.to_numeric(
        working["annualized_sharpe"], errors="coerce"
    )
    group_columns = [*sensitivity_columns, "portfolio"]
    rows: list[dict[str, Any]] = []
    for keys, group in working.groupby(
        group_columns,
        observed=True,
        sort=False,
        dropna=False,
    ):
        key_values = keys if isinstance(keys, tuple) else (keys,)
        key_record = dict(zip(group_columns, key_values, strict=True))
        model_counts = group["model"].value_counts()
        observed_set = frozenset(group["model"])
        duplicate_models = tuple(sorted(model_counts[model_counts.gt(1)].index))
        missing_models = tuple(
            model for model in expected_models if model not in observed_set
        )
        unknown_models = tuple(sorted(observed_set - expected_set))
        non_ok_models = tuple(
            model
            for model in expected_models
            if model
            in set(group.loc[~group["sharpe_status"].eq("ok"), "model"])
        )
        nonfinite_models = tuple(
            model
            for model in expected_models
            if model
            in set(
                group.loc[
                    ~np.isfinite(group["annualized_sharpe"]),
                    "model",
                ]
            )
        )
        complete = not (
            missing_models
            or unknown_models
            or duplicate_models
            or non_ok_models
            or nonfinite_models
        )
        values = group["annualized_sharpe"] if complete else pd.Series(dtype=float)
        rows.append(
            {
                **key_record,
                "expected_model_count": len(expected_models),
                "model_count": len(observed_set & expected_set),
                "valid_model_count": (
                    int(
                        (
                            group["model"].isin(expected_set)
                            & group["sharpe_status"].eq("ok")
                            & np.isfinite(group["annualized_sharpe"])
                        ).sum()
                    )
                ),
                "observed_model_set": tuple(
                    model for model in expected_models if model in observed_set
                ),
                "missing_models": missing_models,
                "unknown_models": unknown_models,
                "duplicate_models": duplicate_models,
                "non_ok_models": non_ok_models,
                "nonfinite_models": nonfinite_models,
                "complete_ten_model_set": complete,
                "median_status": (
                    "ok_complete_ten_models"
                    if complete
                    else "incomplete_model_set"
                ),
                "median_sharpe": float(values.median()) if complete else np.nan,
                "minimum_model_sharpe": (
                    float(values.min()) if complete else np.nan
                ),
                "maximum_model_sharpe": (
                    float(values.max()) if complete else np.nan
                ),
            }
        )
    audit = pd.DataFrame(rows)
    summary_columns = [
        *group_columns,
        "expected_model_count",
        "model_count",
        "valid_model_count",
        "complete_ten_model_set",
        "median_status",
        "median_sharpe",
        "minimum_model_sharpe",
        "maximum_model_sharpe",
    ]
    return ModelMedianSharpeResult(
        summary=audit.loc[:, summary_columns].copy(),
        audit=audit,
    )


def attach_nested_us_shock_quantiles(
    predictions: pd.DataFrame,
    us_market_returns: pd.DataFrame,
    *,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SA5 用目标开盘前已知的美国冲击及其历史扩展分位构造嵌套日集。"""
    _require_columns(predictions, ("source_date", "target_date"), "SA5 预测")
    _require_columns(
        us_market_returns,
        ("date", config.sensitivity.shock_feature_column),
        "SA5 美国市场收益",
    )
    shock = us_market_returns.loc[
        :, ["date", config.sensitivity.shock_feature_column]
    ].copy()
    shock["date"] = pd.to_datetime(shock["date"], errors="raise").dt.normalize()
    if shock.duplicated("date").any():
        raise ValueError("SA5 美国市场冲击表存在重复日期")
    shock["absolute_us_shock"] = pd.to_numeric(
        shock[config.sensitivity.shock_feature_column],
        errors="coerce",
    ).abs()
    shock = shock.sort_values("date").reset_index(drop=True)
    shock["expanding_percentile"] = shock["absolute_us_shock"].expanding().apply(
        lambda values: (
            np.count_nonzero(values <= values[-1]) / values.size
            if np.isfinite(values[-1])
            else np.nan
        ),
        raw=True,
    )
    shock["history_observation_count"] = (
        shock["absolute_us_shock"].notna().cumsum()
    )

    working = predictions.copy()
    working["source_date"] = pd.to_datetime(
        working["source_date"], errors="raise"
    ).dt.normalize()
    working = working.merge(
        shock.rename(columns={"date": "source_date"}),
        on="source_date",
        how="left",
        validate="many_to_one",
    )
    if working["absolute_us_shock"].isna().any():
        raise ValueError("SA5 存在无法匹配目标开盘前美国冲击的预测行")
    quantiles = pd.DataFrame(
        config.m4.portfolio.portfolio_fractions,
        columns=["shock_quantile", "retained_fraction"],
    )
    expanded = working.merge(quantiles, how="cross")
    expanded["shock_percentile_cutoff"] = 1.0 - expanded["retained_fraction"]
    expanded = expanded.loc[
        expanded["expanding_percentile"].ge(
            expanded["shock_percentile_cutoff"]
        )
    ].copy()
    expanded["shock_known_before_target"] = expanded["source_date"].lt(
        pd.to_datetime(expanded["target_date"], errors="raise").dt.normalize()
    )
    if not expanded["shock_known_before_target"].all():
        raise AssertionError("SA5 子样本使用了目标日开盘后才可得的冲击")
    audit = (
        expanded.groupby("shock_quantile", observed=True, sort=False)
        .agg(
            prediction_rows=("target_code", "size"),
            source_date_count=("source_date", "nunique"),
            first_source_date=("source_date", "min"),
            last_source_date=("source_date", "max"),
            minimum_history_count=("history_observation_count", "min"),
            all_shocks_known_before_target=("shock_known_before_target", "all"),
        )
        .reset_index()
    )
    return expanded, audit


def load_citic_level_one_industry(
    *,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> IndustryMappingResult:
    """读取 AS4 中信一级映射；仅对完全同值重复做确定性去重。"""
    path = config.m4.m3.pipeline.data.path(
        config.m4.m3.pipeline.data.cn_stock_industry
    )
    frame = pd.read_parquet(
        path,
        columns=["stock_code", "first_industry_name", "standard_code"],
    )
    frame = frame.loc[
        pd.to_numeric(frame["standard_code"], errors="coerce").eq(
            config.sensitivity.citic_standard_code
        ),
        ["stock_code", "first_industry_name", "standard_code"],
    ].copy()
    frame["stock_code"] = frame["stock_code"].astype(str)
    frame["first_industry_name"] = frame["first_industry_name"].astype("string")
    frame = frame.sort_values(
        ["stock_code", "first_industry_name", "standard_code"],
        kind="mergesort",
    ).reset_index(drop=True)
    duplicate_mask = frame.duplicated("stock_code", keep=False)
    duplicate_rows = frame.loc[duplicate_mask].copy()
    conflicts = (
        duplicate_rows.groupby("stock_code", observed=True)
        .agg(
            industry_value_count=("first_industry_name", "nunique"),
            standard_value_count=("standard_code", "nunique"),
        )
        .reset_index()
    )
    conflicts["has_conflict"] = (
        conflicts["industry_value_count"].gt(1)
        | conflicts["standard_value_count"].gt(1)
    )
    conflict_codes = tuple(
        conflicts.loc[conflicts["has_conflict"], "stock_code"].astype(str)
    )
    if conflict_codes:
        raise ValueError(
            "中信一级重复股票存在行业冲突，禁止任意选取: "
            f"{list(conflict_codes[:20])}"
        )
    if not duplicate_rows.empty:
        duplicate_rows = duplicate_rows.merge(
            conflicts,
            on="stock_code",
            how="left",
            validate="many_to_one",
        )
        duplicate_rows["duplicate_group_size"] = duplicate_rows.groupby(
            "stock_code",
            observed=True,
        )["stock_code"].transform("size")
        duplicate_rows["selected_after_dedup"] = ~duplicate_rows.duplicated(
            "stock_code",
            keep="first",
        )
        duplicate_rows["selection_rule"] = "完全同值重复按稳定排序保留第一行"
    mapping = frame.drop_duplicates("stock_code", keep="first").rename(
        columns={
            "stock_code": "target_code",
            "first_industry_name": "target_industry",
        }
    )
    summary = pd.DataFrame(
        [
            {
                "standard_code": config.sensitivity.citic_standard_code,
                "raw_row_count": len(frame),
                "unique_stock_count": mapping["target_code"].nunique(),
                "duplicate_key_count": int(
                    frame.loc[duplicate_mask, "stock_code"].nunique()
                ),
                "duplicate_row_count": int(duplicate_mask.sum()),
                "conflicting_duplicate_key_count": len(conflict_codes),
                "selection_rule": "完全同值重复按稳定排序保留第一行",
                "conflict_policy": "行业或口径冲突时明确失败",
            }
        ]
    )
    return IndustryMappingResult(
        mapping=mapping.reset_index(drop=True),
        summary_audit=summary,
        duplicate_rows=duplicate_rows.reset_index(drop=True),
    )


def attach_target_industry(
    predictions: pd.DataFrame,
    industry_mapping: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SA6 仅附加 A 股目标行业，不构造缺失的美股行业块。"""
    _require_columns(predictions, ("target_code", "target_market"), "SA6 预测")
    _require_columns(
        industry_mapping,
        ("target_code", "target_industry", "standard_code"),
        "SA6 行业映射",
    )
    if set(predictions["target_market"].astype(str)) != {"CN"}:
        raise ValueError("SA6 只能消费 A 股目标市场预测")
    working = predictions.copy()
    working["target_code"] = working["target_code"].astype(str)
    mapping = industry_mapping.copy()
    mapping["target_code"] = mapping["target_code"].astype(str)
    working = working.merge(
        mapping,
        on="target_code",
        how="left",
        validate="many_to_one",
    )
    working["industry_mapping_status"] = np.where(
        working["target_industry"].notna(),
        "mapped_citic_level_one",
        "missing_target_industry",
    )
    audit = (
        working.groupby("industry_mapping_status", observed=True)
        .agg(
            prediction_rows=("target_code", "size"),
            target_stock_count=("target_code", "nunique"),
        )
        .reset_index()
    )
    return (
        working.loc[
            working["industry_mapping_status"].eq("mapped_citic_level_one")
        ].copy(),
        audit,
    )


def _prefix_feature_batch(
    frame: pd.DataFrame,
    feature_columns: Sequence[str],
    *,
    prefix: str,
    source_date_name: str,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    renamed = {column: f"{prefix}{column}" for column in feature_columns}
    renamed["source_date"] = source_date_name
    return frame.rename(columns=renamed), tuple(
        renamed[column] for column in feature_columns
    )


def predict_joint_graph_snapshots(
    us_snapshot: GraphSnapshot,
    cn_snapshot: GraphSnapshot,
    us_panel: pd.DataFrame,
    cn_panel: pd.DataFrame,
    *,
    us_feature_column: str,
    cn_feature_column: str,
    model_factories: Mapping[str, Callable[[], Any]],
    config: M5Config = DEFAULT_M5_CONFIG,
) -> JointPredictionResult:
    """SA7 把同锚点 US→CN 与 CN→CN 图特征合并后一次拟合十模型。"""
    if (
        us_snapshot.target_market != "CN"
        or cn_snapshot.source_market != "CN"
        or cn_snapshot.target_market != "CN"
    ):
        raise ValueError("SA7 快照方向必须为 US→CN 与 CN→CN")
    if us_snapshot.anchor_date != cn_snapshot.anchor_date:
        raise ValueError("SA7 两图快照锚点不一致")
    if us_snapshot.prediction_dates != cn_snapshot.prediction_dates:
        raise ValueError("SA7 两图快照预测日期块不一致")
    target_codes = sorted(
        set(us_snapshot.feature_mapping["target_code"].astype(str))
        & set(cn_snapshot.feature_mapping["target_code"].astype(str))
    )
    prediction_parts: list[pd.DataFrame] = []
    training_audits: list[dict[str, Any]] = []
    model_audits: list[pd.DataFrame] = []
    target_actual = cn_panel.loc[
        pd.to_datetime(cn_panel["date"], errors="raise")
        .dt.normalize()
        .isin(us_snapshot.prediction_dates),
        ["stock_code", "date", config.m4.m3.prediction.target_value_column],
    ].rename(
        columns={
            "stock_code": "target_code",
            "date": "target_date",
            config.m4.m3.prediction.target_value_column: "actual_return",
        }
    )
    target_actual["target_code"] = target_actual["target_code"].astype(str)
    target_actual["target_date"] = pd.to_datetime(
        target_actual["target_date"], errors="raise"
    ).dt.normalize()

    for target_code in target_codes:
        us_batch = materialize_target_feature_batch(
            us_snapshot,
            us_panel,
            cn_panel,
            target_code=target_code,
            source_value_column=us_feature_column,
            target_value_column=config.m4.m3.prediction.target_value_column,
            config=config.m4.m3.pipeline,
        )
        cn_batch = materialize_target_feature_batch(
            cn_snapshot,
            cn_panel,
            cn_panel,
            target_code=target_code,
            source_value_column=cn_feature_column,
            target_value_column=config.m4.m3.prediction.target_value_column,
            config=config.m4.m3.pipeline,
        )
        if not us_batch.feature_columns or not cn_batch.feature_columns:
            training_audits.append(
                {
                    "anchor_date": us_snapshot.anchor_date,
                    "target_code": target_code,
                    "status": "skipped_missing_one_market_predictor_set",
                    "us_feature_count": len(us_batch.feature_columns),
                    "cn_feature_count": len(cn_batch.feature_columns),
                }
            )
            continue
        us_training, us_columns = _prefix_feature_batch(
            us_batch.training_frame,
            us_batch.feature_columns,
            prefix="US::",
            source_date_name="source_date_us",
        )
        cn_training, cn_columns = _prefix_feature_batch(
            cn_batch.training_frame,
            cn_batch.feature_columns,
            prefix="CN::",
            source_date_name="source_date_cn",
        )
        us_prediction, _ = _prefix_feature_batch(
            us_batch.prediction_frame,
            us_batch.feature_columns,
            prefix="US::",
            source_date_name="source_date_us",
        )
        cn_prediction, _ = _prefix_feature_batch(
            cn_batch.prediction_frame,
            cn_batch.feature_columns,
            prefix="CN::",
            source_date_name="source_date_cn",
        )
        training = us_training.merge(
            cn_training.drop(columns="target_value"),
            on="target_date",
            how="inner",
            validate="one_to_one",
        )
        prediction = us_prediction.drop(columns="predictor_complete").merge(
            cn_prediction.drop(columns="predictor_complete"),
            on="target_date",
            how="inner",
            validate="one_to_one",
        )
        training["source_date"] = training[
            ["source_date_us", "source_date_cn"]
        ].max(axis=1)
        prediction["source_date"] = prediction[
            ["source_date_us", "source_date_cn"]
        ].max(axis=1)
        combined_columns = (*us_columns, *cn_columns)
        regression = fit_regression_model_batch(
            training,
            prediction,
            feature_columns=combined_columns,
            target_column="target_value",
            model_factories=model_factories,
            prediction_key_columns=(
                "target_date",
                "source_date",
                "source_date_us",
                "source_date_cn",
            ),
            training_date_column="target_date",
            prediction_date_column="target_date",
        )
        audit = regression.model_audit.copy()
        audit.insert(0, "target_code", target_code)
        audit.insert(0, "anchor_date", us_snapshot.anchor_date)
        model_audits.append(audit)
        all_models_fitted = set(audit["status"].astype(str)) == {"fitted"}
        training_audits.append(
            {
                "anchor_date": us_snapshot.anchor_date,
                "target_code": target_code,
                "status": (
                    "fitted_all_base_models"
                    if all_models_fitted
                    else "model_transaction_not_complete"
                ),
                "us_feature_count": len(us_columns),
                "cn_feature_count": len(cn_columns),
                "combined_feature_count": len(combined_columns),
                "training_rows": len(training),
                "training_end": training["target_date"].max(),
                "training_strictly_before_anchor": bool(
                    training["target_date"].max() < us_snapshot.anchor_date
                ),
                "both_source_dates_before_target": bool(
                    prediction["source_date_us"].lt(
                        prediction["target_date"]
                    ).all()
                    and prediction["source_date_cn"].lt(
                        prediction["target_date"]
                    ).all()
                ),
            }
        )
        if regression.predictions.empty or not all_models_fitted:
            continue
        base = regression.predictions.copy()
        base.insert(0, "target_code", target_code)
        base.insert(0, "anchor_date", us_snapshot.anchor_date)
        base.insert(0, "direction", "US_CN_TO_CN")
        predictions = build_ensemble_predictions(
            base,
            group_columns=(
                "direction",
                "anchor_date",
                "target_code",
                "target_date",
                "source_date",
            ),
            config=config.m4.m3,
        )
        predictions = predictions.merge(
            target_actual,
            on=["target_code", "target_date"],
            how="left",
            validate="many_to_one",
        )
        prediction_parts.append(predictions)
    return JointPredictionResult(
        predictions=(
            pd.concat(prediction_parts, ignore_index=True)
            if prediction_parts
            else pd.DataFrame()
        ),
        training_audit=pd.DataFrame(training_audits),
        model_audit=(
            pd.concat(model_audits, ignore_index=True)
            if model_audits
            else pd.DataFrame()
        ),
    )


def build_sa7_us_only_comparison(
    joint_sharpe: pd.DataFrame,
    us_only_sharpe: pd.DataFrame,
    *,
    config: M5Config = DEFAULT_M5_CONFIG,
) -> SA7ComparisonResult:
    """按 feature combination×model×qr 严格配对联合与 US-only Sharpe。"""
    required_joint = (
        "feature_combination",
        "model",
        "portfolio",
        "annualized_sharpe",
        "sharpe_status",
    )
    required_baseline = (
        "feature_combination",
        "model",
        "portfolio",
        "annualized_sharpe",
        "sharpe_status",
    )
    _require_columns(joint_sharpe, required_joint, "SA7 联合规格 Sharpe")
    _require_columns(us_only_sharpe, required_baseline, "SA7 US-only Sharpe")
    keys = ["feature_combination", "model", "portfolio"]
    if joint_sharpe.duplicated(keys).any():
        raise ValueError("SA7 联合规格存在重复 feature/model/qr 键")
    if us_only_sharpe.duplicated(keys).any():
        raise ValueError("SA7 US-only 基线存在重复 feature/model/qr 键")
    combinations = tuple(
        name for name, _, _ in config.sensitivity.feature_combinations
    )
    expected = pd.MultiIndex.from_product(
        (
            combinations,
            config.m4.m3.prediction.all_model_names,
            tuple(
                name for name, _ in config.m4.portfolio.portfolio_fractions
            ),
        ),
        names=keys,
    ).to_frame(index=False)
    joint = joint_sharpe.loc[:, list(required_joint)].rename(
        columns={
            "annualized_sharpe": "joint_sharpe",
            "sharpe_status": "joint_sharpe_status",
        }
    )
    baseline = us_only_sharpe.loc[:, list(required_baseline)].rename(
        columns={
            "annualized_sharpe": "us_only_sharpe",
            "sharpe_status": "us_only_sharpe_status",
        }
    )
    paired = (
        expected.merge(joint, on=keys, how="left", validate="one_to_one")
        .merge(baseline, on=keys, how="left", validate="one_to_one")
    )
    paired["joint_sharpe"] = pd.to_numeric(
        paired["joint_sharpe"], errors="coerce"
    )
    paired["us_only_sharpe"] = pd.to_numeric(
        paired["us_only_sharpe"], errors="coerce"
    )
    paired["paired_complete"] = (
        paired["joint_sharpe_status"].eq("ok")
        & paired["us_only_sharpe_status"].eq("ok")
        & np.isfinite(paired["joint_sharpe"])
        & np.isfinite(paired["us_only_sharpe"])
    )
    paired["sharpe_delta"] = np.where(
        paired["paired_complete"],
        paired["joint_sharpe"] - paired["us_only_sharpe"],
        np.nan,
    )
    paired["observed_relation"] = np.select(
        [
            ~paired["paired_complete"],
            paired["sharpe_delta"].gt(0),
            paired["sharpe_delta"].eq(0),
        ],
        [
            "incomplete_pair",
            "joint_above_us_only",
            "joint_equal_us_only",
        ],
        default="joint_below_us_only",
    )
    paired["reference_expectation"] = (
        "部分联合美中预测规格 Sharpe 超过同样本 US-only 基线"
    )
    paired["verifier_verdict"] = pd.NA
    audit = paired.loc[
        :,
        [
            *keys,
            "joint_sharpe_status",
            "us_only_sharpe_status",
            "paired_complete",
            "observed_relation",
        ],
    ].copy()
    summary = (
        paired.groupby("feature_combination", observed=True, sort=False)
        .agg(
            expected_pair_count=("paired_complete", "size"),
            complete_pair_count=("paired_complete", "sum"),
            positive_delta_count=(
                "sharpe_delta",
                lambda values: int(values.gt(0).sum()),
            ),
            positive_delta_fraction=(
                "sharpe_delta",
                lambda values: (
                    float(values.dropna().gt(0).mean())
                    if len(values.dropna())
                    else np.nan
                ),
            ),
        )
        .reset_index()
    )
    summary["pairing_complete"] = summary["complete_pair_count"].eq(
        summary["expected_pair_count"]
    )
    summary["any_joint_above_us_only"] = summary[
        "positive_delta_count"
    ].gt(0)
    summary["reference_expectation"] = (
        "部分联合美中预测规格 Sharpe 超过同样本 US-only 基线"
    )
    summary["verifier_verdict"] = pd.NA
    return SA7ComparisonResult(
        paired=paired,
        audit=audit,
        summary=summary,
    )


def build_directional_sensitivity_comparison(
    tables: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    """为 SA1–SA7 登记原文方向性基准及可复核观测摘要。"""
    expectations = {
        "SA1": "边替换比例越高，SR通常下降；qr6相对更有韧性",
        "SA2": "l增大时SR通常下降；qr6降幅较小；Lag4后可能轻微趋稳",
        "SA3": "替代超参数配置下风险调整表现稳健；精确数值另见R2",
        "SA4": "OPCL特征下图通常有增量，但跨市场信息增量显著更弱",
        "SA5": "非线性集成模型qr4–qr6较高；OLS qr6最高；RIDGE不稳定",
        "SA6": "科技与必需消费行业SR相对较高，需结合行业股票数解释",
        "SA7": "部分联合美中预测规格优于仅美国预测变量基线",
    }
    rows: list[dict[str, Any]] = []
    for element_id, expectation in expectations.items():
        frame = tables.get(element_id, pd.DataFrame())
        numeric = frame.select_dtypes(include=[np.number])
        rows.append(
            {
                "element_id": element_id,
                "reference_expectation": expectation,
                "observation_row_count": len(frame),
                "numeric_cell_count": int(numeric.notna().sum().sum()),
                "observed_numeric_minimum": (
                    float(numeric.min().min())
                    if not numeric.empty and numeric.notna().any().any()
                    else np.nan
                ),
                "observed_numeric_maximum": (
                    float(numeric.max().max())
                    if not numeric.empty and numeric.notna().any().any()
                    else np.nan
                ),
                "evidence_boundary": (
                    "原文无逐格底层数值，不从图估读；仅提供方向性观测接口"
                    if element_id != "SA3"
                    else "SA3方向性观测；R2按Table A.1逐格精确对照"
                ),
                "verdict": pd.NA,
            }
        )
    return pd.DataFrame(rows)
