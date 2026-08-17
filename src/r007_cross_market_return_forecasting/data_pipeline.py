"""m1：双市场替代数据、收益面板、审计与因果日历接口。

实现边界：

* AS11–AS13、AS19/AS24–AS26 只替换数据供应商和市场基准，不声称与 CRSP/Wind/SPY/
  513500.SH 数值口径一致；
* AS2 对缺失值只做逐窗完整样本删除，不填补收益；
* AS3 用目标开盘时刻与源市场收盘时刻做 ``backward as-of`` 配对；
* AS5 的缩尾参数只由更新锚点之前的 250 个目标交易日拟合；
* AS9 的美股成交金额为 ``close × volume``，A 股为 ``turn_value``。

大表读取均支持列裁剪、日期过滤和股票过滤；A 股全市场平均市值通过
``pyarrow.dataset`` 分批聚合，美国侧直接使用 manifest 合格的固定成分池。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as pads
import pyarrow.parquet as pq

from .config import (
    DEFAULT_CONFIG,
    CalendarConfig,
    DirectionConfig,
    M1Config,
    MarketSession,
)


US_SOURCE_REQUIRED_COLUMNS = (
    "stock_code",
    "source_symbol",
    "yahoo_symbol",
    "date",
    "open_raw",
    "high_raw",
    "low_raw",
    "close_raw",
    "adj_close",
    "volume",
    "dividends",
    "stock_splits",
    "adj_factor",
    "open_adj",
    "high_adj",
    "low_adj",
    "close_adj",
    "ohlc_logic_valid",
    "return_eligible",
)
CN_PRICE_REQUIRED_COLUMNS = (
    "stock_code",
    "date",
    "open",
    "high",
    "low",
    "close",
)
CN_TRADE_REQUIRED_COLUMNS = (
    "stock_code",
    "date",
    "volume",
    "turn_value",
    "market_value",
)
INDEX_REQUIRED_COLUMNS = (
    "index_code",
    "index_name",
    "date",
    "open",
    "high",
    "low",
    "close",
)

US_UNIT_CONTRACT = {
    "open": "USD/股（Yahoo Adj Close/Close 派生复权，AS19）",
    "high": "USD/股（Yahoo Adj Close/Close 派生复权，AS19）",
    "low": "USD/股（Yahoo Adj Close/Close 派生复权，AS19）",
    "close": "USD/股（Yahoo Adj Close，AS19）",
    "open_raw": "USD/股（Yahoo 原始字段，AS19）",
    "high_raw": "USD/股（Yahoo 原始字段，AS19）",
    "low_raw": "USD/股（Yahoo 原始字段，AS19）",
    "close_raw": "USD/股（Yahoo 原始字段，AS19）",
    "volume": "股",
    "traded_amount": "USD（原始 close×volume，AS9/AS19）",
}
CN_UNIT_CONTRACT = {
    "open": "CNY/股（AS11 前复权价格）",
    "high": "CNY/股（AS11 前复权价格）",
    "low": "CNY/股（AS11 前复权价格）",
    "close": "CNY/股（AS11 前复权价格）",
    "volume": "股",
    "market_cap": "CNY（ashare_stock_trade.market_value）",
    "traded_amount": "CNY（ashare_stock_trade.turn_value，AS9）",
}


@dataclass(frozen=True)
class IndexSelection:
    """美国宽基指数自动探测结果及覆盖证据。"""

    index_code: str
    index_name: str
    expected_trading_days: int
    valid_ohlc_days: int
    calendar_coverage: float


@dataclass
class DualMarketSources:
    """已按选定股票裁剪的 m1 原始替代数据。"""

    us_quotes: pd.DataFrame
    cn_quotes: pd.DataFrame
    us_index: pd.DataFrame
    cn_index: pd.DataFrame
    us_calendar: pd.DataFrame
    cn_calendar: pd.DataFrame
    us_index_selection: IndexSelection


@dataclass
class DualMarketReturnPanels:
    """后续图与模型可直接消费的双市场收益面板。"""

    us: pd.DataFrame
    cn: pd.DataFrame


def _unique_preserving_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _require_file(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"本地数据文件不存在: {resolved}")
    return resolved


def parquet_columns(path: Path) -> tuple[str, ...]:
    """仅读 Parquet 元数据并返回真实字段，避免为探测字段加载大表。"""
    resolved = _require_file(path)
    return tuple(pq.ParquetFile(resolved).schema_arrow.names)


def _require_parquet_columns(
    path: Path,
    required_columns: Sequence[str],
    context: str,
) -> None:
    actual = set(parquet_columns(path))
    missing = sorted(set(required_columns) - actual)
    if missing:
        raise KeyError(f"{context} 缺少字段 {missing}: {path}")


def _require_frame_columns(
    frame: pd.DataFrame,
    required_columns: Sequence[str],
    context: str,
) -> None:
    missing = sorted(set(required_columns) - set(frame.columns))
    if missing:
        raise KeyError(f"{context} 缺少字段: {missing}")


def _normalize_keys(frame: pd.DataFrame, code_column: str) -> pd.DataFrame:
    result = frame.copy()
    result[code_column] = result[code_column].astype("string")
    result["date"] = pd.to_datetime(result["date"], errors="raise").dt.normalize()
    return result


def _assert_unique_keys(
    frame: pd.DataFrame,
    key_columns: Sequence[str],
    context: str,
) -> None:
    duplicated = frame.duplicated(list(key_columns), keep=False)
    if duplicated.any():
        examples = frame.loc[duplicated, list(key_columns)].head(5).to_dict("records")
        raise ValueError(
            f"{context} 存在 {int(duplicated.sum())} 行重复键，示例: {examples}"
        )


def _read_parquet_filtered(
    path: Path,
    *,
    columns: Sequence[str],
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    code_column: str | None = None,
    codes: Sequence[str] | None = None,
) -> pd.DataFrame:
    """列裁剪并下推日期/代码过滤；不允许空代码集合退化为全表读取。"""
    resolved = _require_file(path)
    selected_columns = _unique_preserving_order(columns)
    _require_parquet_columns(resolved, selected_columns, resolved.name)
    filters: list[tuple[str, str, Any]] = []
    if start_date is not None:
        filters.append(("date", ">=", pd.Timestamp(start_date)))
    if end_date is not None:
        filters.append(("date", "<=", pd.Timestamp(end_date)))
    if codes is not None:
        if code_column is None:
            raise ValueError("指定 codes 时必须同时指定 code_column")
        normalized_codes = _unique_preserving_order(str(code) for code in codes)
        if not normalized_codes:
            raise ValueError("股票/指数代码集合为空，拒绝退化为全表加载")
        filters.append((code_column, "in", normalized_codes))
    try:
        result = pd.read_parquet(
            resolved,
            columns=selected_columns,
            filters=filters or None,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Parquet 筛选读取失败: {resolved}; "
            f"columns={selected_columns}, filters={filters}"
        ) from exc
    if "date" in result:
        result["date"] = pd.to_datetime(result["date"], errors="raise").dt.normalize()
    return result


def load_us_stock_quotes(
    stock_codes: Sequence[str],
    *,
    config: M1Config = DEFAULT_CONFIG,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    extra_columns: Sequence[str] = (),
) -> pd.DataFrame:
    """按列、日期和股票筛选加载 AS24–AS26 合并 Yahoo 缓存。"""
    columns = _unique_preserving_order((*US_SOURCE_REQUIRED_COLUMNS, *extra_columns))
    frame = _read_parquet_filtered(
        config.us_yahoo.merged_panel_path,
        columns=columns,
        start_date=start_date or config.sample.start_date,
        end_date=end_date or config.sample.end_date,
        code_column="stock_code",
        codes=stock_codes,
    )
    frame = _normalize_keys(frame, "stock_code")
    _assert_unique_keys(frame, ("stock_code", "date"), "美股日频行情")
    return frame.sort_values(["stock_code", "date"]).reset_index(drop=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_us_fixed_constituent_universe(
    config: M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """从 manifest 读取 AS24–AS26 合格的固定联合池，不伪造历史市值。"""
    manifest_path = _require_file(config.us_yahoo.manifest_path)
    constituents_path = _require_file(config.us_yahoo.constituents_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    constituents = pd.read_csv(
        constituents_path,
        dtype={"source_symbol": "string", "yahoo_symbol": "string"},
    )
    required = (
        "source_symbol",
        "yahoo_symbol",
        "mapping_reason",
        "pool_source",
        "snapshot_oldid",
        "source_html_sha256",
        "symbol_list_sha256",
    )
    _require_frame_columns(constituents, required, "固定 S&P 500 成分清单")
    if (
        len(constituents) != config.us_yahoo.expected_constituents
        or constituents["source_symbol"].nunique()
        != config.us_yahoo.expected_constituents
    ):
        raise ValueError("固定 Yahoo 联合候选清单不是 501 个唯一证券")
    pool_counts = constituents["pool_source"].value_counts().to_dict()
    if pool_counts != {
        "primary_precheck_pass": 462,
        "supplement_precheck_pass": 39,
    }:
        raise ValueError(f"固定联合池来源计数不一致: {pool_counts}")
    entries = manifest.get("entries", {})
    qualified: list[str] = []
    for symbol in constituents["source_symbol"].astype(str):
        entry = entries.get(symbol, {})
        if entry.get("status") != "success":
            continue
        relative = entry.get("file")
        expected_hash = entry.get("file_sha256")
        if not relative or not expected_hash:
            continue
        path = config.us_yahoo.cache_dir / str(relative)
        if path.is_file() and _file_sha256(path) == expected_hash:
            qualified.append(symbol)
    failed_count = config.us_yahoo.expected_constituents - len(qualified)
    if (
        len(qualified) < config.us_yahoo.minimum_successful_securities
        or failed_count > config.us_yahoo.maximum_failed_securities
    ):
        raise ValueError(
            f"美国固定成分池仅 {len(qualified)} 个合格证券、"
            f"{failed_count} 个未合格；AS26 要求至少 "
            f"{config.us_yahoo.minimum_successful_securities} 个成功且最多 "
            f"{config.us_yahoo.maximum_failed_securities} 个失败"
        )
    selected = constituents.loc[
        constituents["source_symbol"].astype(str).isin(qualified),
        ["source_symbol", "yahoo_symbol", "mapping_reason"],
    ].copy()
    selected.insert(0, "market", "US")
    selected = selected.rename(columns={"source_symbol": "stock_code"})
    selected.insert(
        2,
        "constituent_order",
        np.arange(1, len(selected) + 1, dtype="int64"),
    )
    selected["selection_method"] = "sp500_yahoo_union500_v1"
    selected["selection_uses_fixed_dual_snapshot_precheck"] = True
    selected["survivorship_and_queryability_bias_acknowledged"] = True
    return selected.reset_index(drop=True)


def load_cn_stock_quotes(
    stock_codes: Sequence[str],
    *,
    config: M1Config = DEFAULT_CONFIG,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    extra_price_columns: Sequence[str] = (),
    extra_trade_columns: Sequence[str] = (),
) -> pd.DataFrame:
    """加载 AS11 前复权价与成交市值，并按一对一键外连接保留缺失。"""
    start = start_date or config.sample.start_date
    end = end_date or config.sample.end_date
    price = _read_parquet_filtered(
        config.data.path(config.data.cn_stock_price_forward),
        columns=_unique_preserving_order(
            (*CN_PRICE_REQUIRED_COLUMNS, *extra_price_columns)
        ),
        start_date=start,
        end_date=end,
        code_column="stock_code",
        codes=stock_codes,
    )
    trade = _read_parquet_filtered(
        config.data.path(config.data.cn_stock_trade),
        columns=_unique_preserving_order(
            (*CN_TRADE_REQUIRED_COLUMNS, *extra_trade_columns)
        ),
        start_date=start,
        end_date=end,
        code_column="stock_code",
        codes=stock_codes,
    )
    price = _normalize_keys(price, "stock_code")
    trade = _normalize_keys(trade, "stock_code")
    _assert_unique_keys(price, ("stock_code", "date"), "A股前复权行情")
    _assert_unique_keys(trade, ("stock_code", "date"), "A股成交市值")
    merged = price.merge(
        trade,
        on=["stock_code", "date"],
        how="outer",
        validate="one_to_one",
        indicator="source_merge_status",
    )
    return merged.sort_values(["stock_code", "date"]).reset_index(drop=True)


def stream_average_market_cap(
    path: Path,
    *,
    code_column: str,
    date_column: str,
    market_cap_column: str,
    start_date: str | pd.Timestamp,
    end_date: str | pd.Timestamp,
    batch_rows: int,
    candidate_codes: Sequence[str] | None = None,
) -> pd.DataFrame:
    """分批聚合全样本平均市值，不把全市场日频表一次性载入内存。"""
    if batch_rows <= 0:
        raise ValueError("batch_rows 必须为正整数")
    resolved = _require_file(path)
    required = (code_column, date_column, market_cap_column)
    _require_parquet_columns(resolved, required, "平均市值数据")
    dataset = pads.dataset(resolved, format="parquet")
    predicate = (pads.field(date_column) >= pd.Timestamp(start_date).to_pydatetime()) & (
        pads.field(date_column) <= pd.Timestamp(end_date).to_pydatetime()
    )
    if candidate_codes is not None:
        normalized_codes = _unique_preserving_order(
            str(code) for code in candidate_codes
        )
        if not normalized_codes:
            raise ValueError("candidate_codes 为空")
        predicate &= pads.field(code_column).isin(normalized_codes)

    cap_sum = pd.Series(dtype="float64")
    cap_count = pd.Series(dtype="int64")
    scanner = dataset.scanner(
        columns=list(required),
        filter=predicate,
        batch_size=batch_rows,
        use_threads=True,
    )
    for batch in scanner.to_batches():
        chunk = batch.to_pandas()
        chunk[code_column] = chunk[code_column].astype("string")
        chunk[market_cap_column] = pd.to_numeric(
            chunk[market_cap_column], errors="coerce"
        )
        valid = chunk.loc[
            np.isfinite(chunk[market_cap_column])
            & chunk[market_cap_column].gt(0),
            [code_column, market_cap_column],
        ]
        if valid.empty:
            continue
        grouped = valid.groupby(code_column, observed=True)[market_cap_column].agg(
            market_cap_sum="sum",
            observation_count="count",
        )
        cap_sum = cap_sum.add(grouped["market_cap_sum"], fill_value=0.0)
        cap_count = cap_count.add(grouped["observation_count"], fill_value=0).astype(
            "int64"
        )
    if cap_count.empty:
        raise ValueError(
            f"样本区间内没有正的可用市值记录: {resolved}, "
            f"{pd.Timestamp(start_date).date()}–{pd.Timestamp(end_date).date()}"
        )
    result = pd.DataFrame(
        {
            code_column: cap_sum.index.astype("string"),
            "average_market_cap": (
                cap_sum.reindex(cap_count.index) / cap_count
            ).to_numpy(),
            "market_cap_observations": cap_count.to_numpy(dtype="int64"),
        }
    )
    result["selection_start"] = pd.Timestamp(start_date).normalize()
    result["selection_end"] = pd.Timestamp(end_date).normalize()
    result["selection_uses_full_sample"] = True
    return result.sort_values(
        ["average_market_cap", code_column],
        ascending=[False, True],
    ).reset_index(drop=True)


def select_average_market_cap_universe(
    path: Path,
    *,
    market: str,
    code_column: str,
    market_cap_column: str,
    config: M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """按 B1 选取 2014–2021 全样本平均市值最高的 500 只股票。"""
    ranked = stream_average_market_cap(
        path,
        code_column=code_column,
        date_column="date",
        market_cap_column=market_cap_column,
        start_date=config.sample.start_date,
        end_date=config.sample.end_date,
        batch_rows=config.sample.market_cap_batch_rows,
    )
    requested = config.sample.stocks_per_market
    if len(ranked) < requested:
        raise ValueError(
            f"{market} 仅有 {len(ranked)} 只股票具备正市值，少于 B1 要求的 "
            f"{requested} 只"
        )
    selected = ranked.head(requested).copy()
    selected.insert(0, "market", market)
    selected.insert(2, "market_cap_rank", np.arange(1, requested + 1))
    selected["mechanical_lookahead_acknowledged"] = True
    return selected


def build_dual_market_universes(
    config: M1Config = DEFAULT_CONFIG,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """构建 AS25 固定联合美股池与 AS11 平均市值 A 股池。"""
    us = load_us_fixed_constituent_universe(config)
    cn = select_average_market_cap_universe(
        config.data.path(config.data.cn_stock_trade),
        market="CN",
        code_column="stock_code",
        market_cap_column="market_value",
        config=config,
    )
    return us, cn


def load_us_trade_calendar(
    *,
    config: M1Config = DEFAULT_CONFIG,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """按 D8 从 AS24 合格联合池的实际行情日期并集衍生日历。"""
    raw = _read_parquet_filtered(
        config.us_yahoo.merged_panel_path,
        columns=["date"],
        start_date=start_date or config.sample.start_date,
        end_date=end_date or config.sample.end_date,
    )
    dates = pd.to_datetime(raw["date"], errors="raise").dt.normalize()
    return pd.DataFrame({"date": dates.drop_duplicates().sort_values()}).reset_index(
        drop=True
    )


def load_cn_trade_calendar(
    *,
    config: M1Config = DEFAULT_CONFIG,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """按 D8 加载 A 股交易日历并对多市场记录去重。"""
    raw = _read_parquet_filtered(
        config.data.path(config.data.cn_trade_calendar),
        columns=["date", "IfTradingDay"],
        start_date=start_date or config.sample.start_date,
        end_date=end_date or config.sample.end_date,
    )
    result = raw.loc[raw["IfTradingDay"].eq(1), ["date"]]
    return result.drop_duplicates().sort_values("date").reset_index(drop=True)


def discover_us_broad_index(
    *,
    config: M1Config = DEFAULT_CONFIG,
    expected_calendar: pd.DataFrame | None = None,
) -> IndexSelection:
    """以元数据名称和 2014–2021 OHLC/日历覆盖自动确认美国宽基。

    不预设代码：先按配置中的宽基指数精确名称匹配元数据，再要求候选指数
    对美股实际交易日历达到 100% 的有效开收盘覆盖；候选不唯一时中止。
    """
    metadata_path = config.data.path(config.data.us_index_metadata)
    _require_parquet_columns(
        metadata_path,
        ("index_code", "index_name"),
        "美国指数元数据",
    )
    metadata = pd.read_parquet(
        _require_file(metadata_path),
        columns=["index_code", "index_name"],
    )
    metadata["index_code"] = metadata["index_code"].astype("string")
    metadata["index_name"] = metadata["index_name"].astype("string")
    candidates = metadata.loc[
        metadata["index_name"].isin(config.calendar.us_broad_index_exact_names),
        ["index_code", "index_name"],
    ].drop_duplicates()
    if candidates.empty:
        raise ValueError(
            "美国指数元数据中没有匹配的宽基名称；可配置名称为 "
            f"{config.calendar.us_broad_index_exact_names}"
        )
    if expected_calendar is None:
        expected_calendar = load_us_trade_calendar(config=config)
    _require_frame_columns(expected_calendar, ("date",), "美股预期交易日历")
    expected_dates = pd.DatetimeIndex(
        pd.to_datetime(expected_calendar["date"], errors="raise").dt.normalize()
    ).unique()
    if expected_dates.empty:
        raise ValueError("美股预期交易日历为空")

    index_path = config.data.path(config.data.overseas_index_price)
    raw = _read_parquet_filtered(
        index_path,
        columns=INDEX_REQUIRED_COLUMNS,
        start_date=config.sample.start_date,
        end_date=config.sample.end_date,
        code_column="index_code",
        codes=candidates["index_code"].tolist(),
    )
    raw = _normalize_keys(raw, "index_code")
    audit_rows: list[dict[str, Any]] = []
    for candidate in candidates.itertuples(index=False):
        item = raw.loc[raw["index_code"].eq(candidate.index_code)].copy()
        duplicate_keys = int(item.duplicated(["index_code", "date"]).sum())
        valid = item.loc[
            item["open"].gt(0)
            & item["close"].gt(0)
            & np.isfinite(item["open"])
            & np.isfinite(item["close"])
        ]
        valid_dates = pd.DatetimeIndex(valid["date"].drop_duplicates())
        covered = int(expected_dates.isin(valid_dates).sum())
        coverage = covered / len(expected_dates)
        audit_rows.append(
            {
                "index_code": str(candidate.index_code),
                "index_name": str(candidate.index_name),
                "expected_trading_days": len(expected_dates),
                "valid_ohlc_days": covered,
                "calendar_coverage": coverage,
                "duplicate_keys": duplicate_keys,
            }
        )
    audit = pd.DataFrame(audit_rows)
    eligible = audit.loc[
        audit["calendar_coverage"].ge(
            config.calendar.required_index_calendar_coverage
        )
        & audit["duplicate_keys"].eq(0)
    ]
    if len(eligible) != 1:
        raise ValueError(
            "美国宽基指数覆盖审计后候选不唯一，拒绝猜测代码: "
            f"{audit.to_dict('records')}"
        )
    selected = eligible.iloc[0]
    return IndexSelection(
        index_code=str(selected["index_code"]),
        index_name=str(selected["index_name"]),
        expected_trading_days=int(selected["expected_trading_days"]),
        valid_ohlc_days=int(selected["valid_ohlc_days"]),
        calendar_coverage=float(selected["calendar_coverage"]),
    )


def load_us_market_index(
    selection: IndexSelection,
    *,
    config: M1Config = DEFAULT_CONFIG,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """加载已由 :func:`discover_us_broad_index` 审计确认的美国宽基。"""
    raw = _read_parquet_filtered(
        config.data.path(config.data.overseas_index_price),
        columns=INDEX_REQUIRED_COLUMNS,
        start_date=start_date or config.sample.start_date,
        end_date=end_date or config.sample.end_date,
        code_column="index_code",
        codes=[selection.index_code],
    )
    raw = _normalize_keys(raw, "index_code")
    _assert_unique_keys(raw, ("index_code", "date"), "美国市场宽基")
    return raw.sort_values("date").reset_index(drop=True)


def load_cn_market_index(
    *,
    config: M1Config = DEFAULT_CONFIG,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """按 AS13 加载沪深 300 日频 OHLC。"""
    raw = _read_parquet_filtered(
        config.data.path(config.data.cn_index_trade),
        columns=INDEX_REQUIRED_COLUMNS,
        start_date=start_date or config.sample.start_date,
        end_date=end_date or config.sample.end_date,
        code_column="index_code",
        codes=[config.calendar.cn_market_index_code],
    )
    raw = _normalize_keys(raw, "index_code")
    _assert_unique_keys(raw, ("index_code", "date"), "A股市场宽基")
    return raw.sort_values("date").reset_index(drop=True)


def load_dual_market_sources(
    us_stock_codes: Sequence[str],
    cn_stock_codes: Sequence[str],
    *,
    config: M1Config = DEFAULT_CONFIG,
) -> DualMarketSources:
    """一次装载已裁剪的双市场 m1 原料，不运行图、模型或回测。"""
    us_calendar = load_us_trade_calendar(config=config)
    cn_calendar = load_cn_trade_calendar(config=config)
    selection = discover_us_broad_index(
        config=config,
        expected_calendar=us_calendar,
    )
    return DualMarketSources(
        us_quotes=load_us_stock_quotes(us_stock_codes, config=config),
        cn_quotes=load_cn_stock_quotes(cn_stock_codes, config=config),
        us_index=load_us_market_index(selection, config=config),
        cn_index=load_cn_market_index(config=config),
        us_calendar=us_calendar,
        cn_calendar=cn_calendar,
        us_index_selection=selection,
    )


def standardize_us_quotes(
    raw: pd.DataFrame,
    *,
    config: M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """标准化 AS19 双轨字段，并从正式收益代理池排除资格失败证券。"""
    _require_frame_columns(raw, US_SOURCE_REQUIRED_COLUMNS, "美股行情标准化")
    result = _normalize_keys(raw, "stock_code")
    qualification_rows = [
        _audit_us_security_qualification(
            security,
            stock_code=str(stock_code),
            minimum_rate=config.us_yahoo.minimum_ohlcv_non_null_rate,
        )[0]
        for stock_code, security in result.groupby(
            "stock_code",
            sort=False,
            observed=True,
        )
    ]
    qualification = pd.DataFrame(qualification_rows)
    hard_failures = qualification.loc[
        ~qualification["hard_contract_pass"].fillna(False)
    ]
    if not hard_failures.empty:
        raise ValueError(
            "美股收益代理池存在独立标志、复权衍生或收益隔离硬失败: "
            f"{hard_failures[['stock_code', 'failure_reasons']].head(20).to_dict('records')}"
        )
    qualified_codes = set(
        qualification.loc[
            qualification["qualified"].fillna(False),
            "stock_code",
        ].astype(str)
    )
    result = result.loc[
        result["stock_code"].astype(str).isin(qualified_codes)
    ].copy()
    if result.empty:
        raise ValueError("美股收益代理池没有满足 AS26 双 95% 门槛的证券")
    numeric_columns = [
        "open_raw",
        "high_raw",
        "low_raw",
        "close_raw",
        "adj_close",
        "volume",
        "dividends",
        "stock_splits",
        "adj_factor",
        "open_adj",
        "high_adj",
        "low_adj",
        "close_adj",
    ]
    result[numeric_columns] = result[numeric_columns].apply(
        pd.to_numeric, errors="coerce"
    )
    result["open"] = result["open_adj"]
    result["high"] = result["high_adj"]
    result["low"] = result["low_adj"]
    result["close"] = result["close_adj"]
    traded_amount = result["close_raw"] * result["volume"]
    result["traded_amount"] = traded_amount.where(
        result["close_raw"].gt(0)
        & result["volume"].ge(0)
        & np.isfinite(traded_amount)
    )
    result["market"] = "US"
    return result[
        [
            "market",
            "stock_code",
            "source_symbol",
            "yahoo_symbol",
            "date",
            "open",
            "high",
            "low",
            "close",
            "open_raw",
            "high_raw",
            "low_raw",
            "close_raw",
            "adj_close",
            "volume",
            "dividends",
            "stock_splits",
            "adj_factor",
            "ohlc_logic_valid",
            "return_eligible",
            "traded_amount",
        ]
    ].sort_values(["stock_code", "date"]).reset_index(drop=True)


def standardize_cn_quotes(raw: pd.DataFrame) -> pd.DataFrame:
    """标准化 AS11 字段，并按 AS9 直接采用 ``turn_value`` 成交金额。"""
    _require_frame_columns(
        raw,
        (*CN_PRICE_REQUIRED_COLUMNS, *CN_TRADE_REQUIRED_COLUMNS[2:]),
        "A股行情标准化",
    )
    result = _normalize_keys(raw, "stock_code")
    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "market_value",
        "turn_value",
    ]
    result[numeric_columns] = result[numeric_columns].apply(
        pd.to_numeric, errors="coerce"
    )
    result["market"] = "CN"
    result["market_cap"] = result["market_value"]
    result["traded_amount"] = result["turn_value"].where(
        result["turn_value"].ge(0) & np.isfinite(result["turn_value"])
    )
    return result[
        [
            "market",
            "stock_code",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "market_cap",
            "traded_amount",
        ]
    ].sort_values(["stock_code", "date"]).reset_index(drop=True)


def calculate_raw_log_returns(
    frame: pd.DataFrame,
    *,
    entity_column: str,
    pvclcl_column: str = "pvclcl_raw",
    opcl_column: str = "opcl_raw",
) -> pd.DataFrame:
    """向量化计算 F1 pvCLCL 与 F2 OPCL；缺失/非正价格不填补。"""
    _require_frame_columns(
        frame,
        (entity_column, "date", "open", "close"),
        "原始收益计算",
    )
    result = frame.sort_values([entity_column, "date"]).copy()
    open_price = pd.to_numeric(result["open"], errors="coerce")
    close_price = pd.to_numeric(result["close"], errors="coerce")
    open_price = open_price.where(open_price.gt(0) & np.isfinite(open_price))
    close_price = close_price.where(close_price.gt(0) & np.isfinite(close_price))
    previous_close = close_price.groupby(
        result[entity_column], sort=False, observed=True
    ).shift(1)
    result[pvclcl_column] = np.log(close_price / previous_close)
    result[opcl_column] = np.log(close_price / open_price)
    return result


def calculate_market_log_returns(index_frame: pd.DataFrame) -> pd.DataFrame:
    """计算迁移后宽基的同口径 F1/F2 市场收益。"""
    _require_frame_columns(index_frame, INDEX_REQUIRED_COLUMNS, "市场收益计算")
    result = calculate_raw_log_returns(
        index_frame,
        entity_column="index_code",
        pvclcl_column="pvclcl_market",
        opcl_column="opcl_market",
    )
    if result["index_code"].nunique() != 1:
        raise ValueError("市场收益表必须且只能包含一个宽基指数")
    return result[["date", "pvclcl_market", "opcl_market"]]


def attach_market_excess_returns(
    stock_returns: pd.DataFrame,
    market_returns: pd.DataFrame,
) -> pd.DataFrame:
    """按交易日扣减宽基收益，形成 F3/B3 市场超额收益。"""
    _require_frame_columns(
        stock_returns,
        ("date", "pvclcl_raw", "opcl_raw"),
        "个股原始收益",
    )
    _require_frame_columns(
        market_returns,
        ("date", "pvclcl_market", "opcl_market"),
        "宽基收益",
    )
    _assert_unique_keys(market_returns, ("date",), "宽基收益")
    result = stock_returns.merge(
        market_returns,
        on="date",
        how="left",
        validate="many_to_one",
    )
    result["pvclcl_excess"] = result["pvclcl_raw"] - result["pvclcl_market"]
    result["opcl_excess"] = result["opcl_raw"] - result["opcl_market"]
    return result


def add_trailing_traded_amount_median(
    frame: pd.DataFrame,
    *,
    window_days: int,
    minimum_observations: int | None = None,
) -> pd.DataFrame:
    """计算预测日前 AS9 的 21 日成交金额中位数，明确排除当日。"""
    _require_frame_columns(
        frame,
        ("stock_code", "date", "traded_amount"),
        "成交金额滚动中位数",
    )
    if window_days <= 0:
        raise ValueError("window_days 必须为正整数")
    minimum = window_days if minimum_observations is None else minimum_observations
    if not 1 <= minimum <= window_days:
        raise ValueError("minimum_observations 必须在 [1, window_days] 内")
    result = frame.sort_values(["stock_code", "date"]).copy()
    result["traded_amount_median_21d"] = result.groupby(
        "stock_code",
        sort=False,
        observed=True,
    )["traded_amount"].transform(
        lambda values: values.shift(1).rolling(
            window=window_days,
            min_periods=minimum,
        ).median()
    )
    return result


def build_market_return_panel(
    stock_quotes: pd.DataFrame,
    market_index: pd.DataFrame,
    *,
    market: str,
    config: M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """构造单市场标准价量、F1–F3 与 AS9 流动性面板。"""
    if market == "US":
        standardized = standardize_us_quotes(stock_quotes, config=config)
    elif market == "CN":
        standardized = standardize_cn_quotes(stock_quotes)
    else:
        raise KeyError(f"未知市场代码: {market}")
    raw_returns = calculate_raw_log_returns(
        standardized,
        entity_column="stock_code",
        pvclcl_column=config.returns.pvclcl_raw_column,
        opcl_column=config.returns.opcl_raw_column,
    )
    index_returns = calculate_market_log_returns(market_index)
    excess = attach_market_excess_returns(raw_returns, index_returns)
    return add_trailing_traded_amount_median(
        excess,
        window_days=config.returns.liquidity_window_days,
    )


def build_dual_market_return_panels(
    sources: DualMarketSources,
    *,
    config: M1Config = DEFAULT_CONFIG,
) -> DualMarketReturnPanels:
    """由已裁剪原料构造双市场收益面板；不训练模型、不产生策略信号。"""
    return DualMarketReturnPanels(
        us=build_market_return_panel(
            sources.us_quotes,
            sources.us_index,
            market="US",
            config=config,
        ),
        cn=build_market_return_panel(
            sources.cn_quotes,
            sources.cn_index,
            market="CN",
            config=config,
        ),
    )


def complete_case_training_rows(
    frame: pd.DataFrame,
    *,
    target_column: str,
    feature_columns: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按 AS2 删除逐目标—特征缺失行，不填补、不跨期借值。"""
    required = _unique_preserving_order((target_column, *feature_columns))
    _require_frame_columns(frame, required, "训练窗完整样本删除")
    missing_mask = frame[required].isna()
    keep = ~missing_mask.any(axis=1)
    audit = pd.DataFrame(
        {
            "column": required,
            "missing_rows": missing_mask.sum().reindex(required).to_numpy(),
            "input_rows": len(frame),
        }
    )
    audit["complete_rows"] = int(keep.sum())
    audit["dropped_rows"] = int((~keep).sum())
    return frame.loc[keep].copy(), audit


def fit_stock_winsor_limits(
    frame: pd.DataFrame,
    *,
    anchor_date: str | pd.Timestamp,
    value_columns: Sequence[str],
    config: M1Config = DEFAULT_CONFIG,
    stock_column: str = "stock_code",
    date_column: str = "date",
) -> pd.DataFrame:
    """只用锚点前 250 个目标日，逐股拟合 AS5 的 0.5%/99.5% 分位。"""
    _require_frame_columns(
        frame,
        (stock_column, date_column, *value_columns),
        "训练窗缩尾拟合",
    )
    anchor = pd.Timestamp(anchor_date).normalize()
    dates = pd.DatetimeIndex(
        pd.to_datetime(frame[date_column], errors="raise").dt.normalize()
    )
    historical_dates = dates[dates < anchor].unique().sort_values()
    window_days = config.returns.training_window_days
    if len(historical_dates) < window_days:
        raise ValueError(
            f"锚点 {anchor.date()} 前仅 {len(historical_dates)} 个历史交易日，"
            f"不足 AS5/B5 要求的 {window_days} 日"
        )
    selected_dates = historical_dates[-window_days:]
    window = frame.loc[dates.isin(selected_dates), [stock_column, date_column, *value_columns]]
    long = window.melt(
        id_vars=[stock_column, date_column],
        value_vars=list(value_columns),
        var_name="value_column",
        value_name="value",
    )
    long["value"] = pd.to_numeric(long["value"], errors="coerce").replace(
        [np.inf, -np.inf],
        np.nan,
    )
    valid = long.dropna(subset=["value"])
    if valid.empty:
        raise ValueError("训练窗内没有可用于缩尾的有限收益")
    grouped = valid.groupby(
        [stock_column, "value_column"],
        observed=True,
    )["value"]
    lower = grouped.quantile(config.returns.winsor_lower_quantile)
    upper = grouped.quantile(config.returns.winsor_upper_quantile)
    count = grouped.count()
    limits = pd.concat(
        [
            lower.rename("winsor_lower"),
            upper.rename("winsor_upper"),
            count.rename("observation_count"),
        ],
        axis=1,
    ).reset_index()
    limits["anchor_date"] = anchor
    limits["fit_start"] = selected_dates.min()
    limits["fit_end"] = selected_dates.max()
    limits["training_window_days"] = window_days
    limits["lower_quantile"] = config.returns.winsor_lower_quantile
    limits["upper_quantile"] = config.returns.winsor_upper_quantile
    if not limits["fit_end"].lt(anchor).all():
        raise AssertionError("缩尾拟合窗口包含锚点或未来日期")
    return limits


def apply_stock_winsor_limits(
    frame: pd.DataFrame,
    limits: pd.DataFrame,
    *,
    value_columns: Sequence[str],
    stock_column: str = "stock_code",
) -> pd.DataFrame:
    """以既有训练窗参数截尾，不在变换期重新估计任何分位数。"""
    _require_frame_columns(frame, (stock_column, *value_columns), "缩尾变换")
    _require_frame_columns(
        limits,
        (stock_column, "value_column", "winsor_lower", "winsor_upper"),
        "缩尾参数",
    )
    _assert_unique_keys(limits, (stock_column, "value_column"), "缩尾参数")
    result = frame.copy()
    indexed = limits.set_index([stock_column, "value_column"])
    stock_codes = result[stock_column]
    for column in value_columns:
        try:
            item = indexed.xs(column, level="value_column")
        except KeyError as exc:
            raise KeyError(f"缩尾参数缺少收益列: {column}") from exc
        lower = stock_codes.map(item["winsor_lower"])
        upper = stock_codes.map(item["winsor_upper"])
        values = pd.to_numeric(result[column], errors="coerce")
        result[column] = values.clip(lower=lower, upper=upper)
    return result


def winsorize_training_window(
    frame: pd.DataFrame,
    *,
    anchor_date: str | pd.Timestamp,
    value_columns: Sequence[str],
    config: M1Config = DEFAULT_CONFIG,
    stock_column: str = "stock_code",
    date_column: str = "date",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """AS5 纯函数接口：返回历史训练窗截尾值及其逐股参数证据。"""
    limits = fit_stock_winsor_limits(
        frame,
        anchor_date=anchor_date,
        value_columns=value_columns,
        config=config,
        stock_column=stock_column,
        date_column=date_column,
    )
    anchor = pd.Timestamp(anchor_date).normalize()
    historical = frame.loc[
        pd.to_datetime(frame[date_column], errors="raise").dt.normalize().lt(anchor)
    ].copy()
    selected_dates = (
        pd.to_datetime(historical[date_column], errors="raise")
        .dt.normalize()
        .drop_duplicates()
        .sort_values()
        .tail(config.returns.training_window_days)
    )
    window = historical.loc[
        pd.to_datetime(historical[date_column], errors="raise")
        .dt.normalize()
        .isin(selected_dates)
    ].copy()
    return (
        apply_stock_winsor_limits(
            window,
            limits,
            value_columns=value_columns,
            stock_column=stock_column,
        ),
        limits,
    )


def _session_timestamp_utc(
    dates: pd.Series,
    session: MarketSession,
    local_time: str,
) -> pd.Series:
    normalized = pd.to_datetime(dates, errors="raise").dt.normalize()
    naive = pd.DatetimeIndex(normalized + pd.to_timedelta(local_time))
    localized = naive.tz_localize(
        ZoneInfo(session.timezone),
        ambiguous="raise",
        nonexistent="raise",
    )
    return pd.Series(localized.tz_convert("UTC"), index=dates.index)


def build_causal_calendar_mapping(
    target_calendar: pd.DataFrame,
    source_calendar: pd.DataFrame,
    *,
    direction: str | DirectionConfig,
    calendar_config: CalendarConfig,
) -> pd.DataFrame:
    """按 AS3 将每个目标开盘映射到此前最近已完成的源市场交易日。"""
    _require_frame_columns(target_calendar, ("date",), "目标市场日历")
    _require_frame_columns(source_calendar, ("date",), "源市场日历")
    direction_config = (
        calendar_config.direction(direction)
        if isinstance(direction, str)
        else direction
    )
    target_session = calendar_config.session(direction_config.target_market)
    source_session = calendar_config.session(direction_config.source_market)

    target = pd.DataFrame(
        {
            "target_date": pd.to_datetime(
                target_calendar["date"], errors="raise"
            ).dt.normalize()
        }
    ).drop_duplicates()
    source = pd.DataFrame(
        {
            "source_date": pd.to_datetime(
                source_calendar["date"], errors="raise"
            ).dt.normalize()
        }
    ).drop_duplicates()
    target["target_open_utc"] = _session_timestamp_utc(
        target["target_date"],
        target_session,
        target_session.open_time,
    )
    source["source_close_utc"] = _session_timestamp_utc(
        source["source_date"],
        source_session,
        source_session.close_time,
    )
    mapped = pd.merge_asof(
        target.sort_values("target_open_utc"),
        source.sort_values("source_close_utc"),
        left_on="target_open_utc",
        right_on="source_close_utc",
        direction="backward",
        allow_exact_matches=False,
    )
    mapped.insert(0, "direction", direction_config.name)
    mapped.insert(1, "source_market", direction_config.source_market)
    mapped.insert(2, "target_market", direction_config.target_market)
    mapped["lag_parameter"] = direction_config.lag_parameter
    mapped["causal_available"] = mapped["source_close_utc"].notna()
    mapped["information_age_hours"] = (
        mapped["target_open_utc"] - mapped["source_close_utc"]
    ).dt.total_seconds() / 3600.0
    violation = mapped["source_close_utc"].notna() & mapped[
        "source_close_utc"
    ].ge(mapped["target_open_utc"])
    if violation.any():
        raise AssertionError("跨市场日历映射出现源市场收盘不早于目标开盘")
    return mapped.sort_values("target_date").reset_index(drop=True)


def build_bidirectional_calendar_mappings(
    us_calendar: pd.DataFrame,
    cn_calendar: pd.DataFrame,
    *,
    config: M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """生成 US→CN(l=1) 与 CN→US(l=0) 两方向的逐日因果证据。"""
    us_to_cn = build_causal_calendar_mapping(
        cn_calendar,
        us_calendar,
        direction="US_TO_CN",
        calendar_config=config.calendar,
    )
    cn_to_us = build_causal_calendar_mapping(
        us_calendar,
        cn_calendar,
        direction="CN_TO_US",
        calendar_config=config.calendar,
    )
    return pd.concat([us_to_cn, cn_to_us], ignore_index=True)


def map_signals_to_next_target_session(
    signal_dates: Sequence[str | pd.Timestamp] | pd.Series,
    target_calendar: pd.DataFrame,
) -> pd.DataFrame:
    """将 T 日信号映射到严格晚于 T 的下一目标交易日（T+1 执行）。"""
    _require_frame_columns(target_calendar, ("date",), "目标市场日历")
    calendar = np.sort(
        pd.to_datetime(target_calendar["date"], errors="raise")
        .dt.normalize()
        .drop_duplicates()
        .to_numpy(dtype="datetime64[ns]")
    )
    signals = pd.to_datetime(pd.Series(signal_dates), errors="raise").dt.normalize()
    positions = np.searchsorted(
        calendar,
        signals.to_numpy(dtype="datetime64[ns]"),
        side="right",
    )
    valid = positions < len(calendar)
    execution = np.full(len(signals), np.datetime64("NaT"), dtype="datetime64[ns]")
    execution[valid] = calendar[positions[valid]]
    result = pd.DataFrame(
        {
            "signal_date": signals,
            "execution_date": pd.to_datetime(execution),
            "has_next_session": valid,
        }
    )
    if (
        result.loc[result["has_next_session"], "execution_date"]
        <= result.loc[result["has_next_session"], "signal_date"]
    ).any():
        raise AssertionError("T+1 执行日未严格晚于信号日")
    return result


def audit_parquet_schema(
    path: Path,
    *,
    dataset_name: str,
    required_columns: Sequence[str],
    unit_contract: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """仅基于元数据产出字段存在性、真实类型与单位合同审计。"""
    resolved = _require_file(path)
    schema = pq.ParquetFile(resolved).schema_arrow
    actual = set(schema.names)
    units = unit_contract or {}
    rows: list[dict[str, Any]] = []
    for column in required_columns:
        present = column in actual
        rows.append(
            {
                "dataset": dataset_name,
                "audit_type": "schema",
                "item": column,
                "actual": str(schema.field(column).type) if present else None,
                "expected": "字段必须存在",
                "status": "pass" if present else "fail",
                "detail": str(resolved),
            }
        )
        if column in units:
            rows.append(
                {
                    "dataset": dataset_name,
                    "audit_type": "unit_contract",
                    "item": column,
                    "actual": units[column],
                    "expected": "由 spec/assumptions 规定的计算量纲",
                    "status": "declared_not_source_certified",
                    "detail": str(resolved),
                }
            )
    return pd.DataFrame(rows)


def audit_m1_source_schemas(
    config: M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """集中审计 D1–D8 的 Yahoo 缓存与六个本地替代文件。"""
    specifications = (
        (
            config.us_yahoo.merged_panel_path,
            "us_yahoo_union500_v1",
            US_SOURCE_REQUIRED_COLUMNS,
            US_UNIT_CONTRACT,
        ),
        (
            config.data.path(config.data.cn_stock_price_forward),
            "ashare_stock_price_forward",
            CN_PRICE_REQUIRED_COLUMNS,
            {
                column: CN_UNIT_CONTRACT[column]
                for column in ("open", "high", "low", "close")
            },
        ),
        (
            config.data.path(config.data.cn_stock_trade),
            "ashare_stock_trade",
            CN_TRADE_REQUIRED_COLUMNS,
            {
                "volume": "股",
                "turn_value": "CNY 成交金额（AS9）",
                "market_value": "CNY 市值（AS11）",
            },
        ),
        (
            config.data.path(config.data.us_index_metadata),
            "usshare_index",
            ("index_code", "index_name"),
            {},
        ),
        (
            config.data.path(config.data.overseas_index_price),
            "osshare_index_price",
            INDEX_REQUIRED_COLUMNS,
            {
                column: "指数点"
                for column in ("open", "high", "low", "close")
            },
        ),
        (
            config.data.path(config.data.cn_index_trade),
            "ashare_csiindex_trade",
            INDEX_REQUIRED_COLUMNS,
            {
                column: "指数点"
                for column in ("open", "high", "low", "close")
            },
        ),
        (
            config.data.path(config.data.cn_trade_calendar),
            "ashare_tradeday",
            ("date", "IfTradingDay"),
            {},
        ),
    )
    return pd.concat(
        [
            audit_parquet_schema(
                file_path,
                dataset_name=dataset_name,
                required_columns=required_columns,
                unit_contract=unit_contract,
            )
            for file_path, dataset_name, required_columns, unit_contract in specifications
        ],
        ignore_index=True,
    )


_NON_SEMANTIC_ARROW_SCHEMA_METADATA_KEYS = frozenset({b"pandas"})


def _semantic_arrow_schema_metadata(
    schema: pa.Schema,
) -> dict[bytes, bytes] | None:
    """去掉只描述 DataFrame 容器的 pandas metadata，保留其余语义 metadata。"""
    if not schema.metadata:
        return None
    retained = {
        key: value
        for key, value in schema.metadata.items()
        if key not in _NON_SEMANTIC_ARROW_SCHEMA_METADATA_KEYS
    }
    return retained or None


def _semantic_arrow_schema_sha256(schema: pa.Schema) -> str:
    """对字段合同及非 pandas schema metadata 生成稳定证据哈希。"""
    normalized = pa.schema(
        list(schema),
        metadata=_semantic_arrow_schema_metadata(schema),
    )
    return hashlib.sha256(normalized.serialize().to_pybytes()).hexdigest()


def _semantic_arrow_schema_differences(
    actual: pa.Schema,
    expected: pa.Schema,
) -> list[str]:
    """逐项比较会影响数据语义的 Arrow schema 合同。"""
    differences: list[str] = []
    if actual.names != expected.names:
        differences.append(
            f"列名或顺序不同: actual={actual.names}, expected={expected.names}"
        )
    if len(actual) != len(expected):
        differences.append(
            f"字段数不同: actual={len(actual)}, expected={len(expected)}"
        )
    for index, (actual_field, expected_field) in enumerate(
        zip(actual, expected)
    ):
        if actual_field.name != expected_field.name:
            differences.append(
                f"字段[{index}]名称不同: "
                f"actual={actual_field.name}, expected={expected_field.name}"
            )
        if actual_field.type != expected_field.type:
            differences.append(
                f"字段[{index}]类型不同: "
                f"actual={actual_field.type}, expected={expected_field.type}"
            )
        if actual_field.nullable != expected_field.nullable:
            differences.append(
                f"字段[{index}] nullability 不同: "
                f"actual={actual_field.nullable}, "
                f"expected={expected_field.nullable}"
            )
        if (actual_field.metadata or {}) != (expected_field.metadata or {}):
            differences.append(f"字段[{index}]语义 metadata 不同")
    actual_metadata = _semantic_arrow_schema_metadata(actual)
    expected_metadata = _semantic_arrow_schema_metadata(expected)
    if actual_metadata != expected_metadata:
        differences.append(
            "非 pandas 的 schema 级语义 metadata 不同"
        )
    return differences


def _assert_semantic_arrow_schema_equal(
    actual: pa.Schema,
    expected: pa.Schema,
    *,
    context: str,
) -> None:
    """只忽略 pandas 容器 metadata，其余字段合同必须严格相等。"""
    differences = _semantic_arrow_schema_differences(actual, expected)
    if differences:
        raise ValueError(
            f"{context} schema 不一致: {'; '.join(differences[:20])}"
        )


_US_RAW_OHLC_COLUMNS = (
    "open_raw",
    "high_raw",
    "low_raw",
    "close_raw",
)
_US_RAW_OHLCV_COLUMNS = (*_US_RAW_OHLC_COLUMNS, "volume")
_US_ADJUSTED_OHLC_MAPPING = (
    ("open_raw", "open_adj"),
    ("high_raw", "high_adj"),
    ("low_raw", "low_adj"),
    ("close_raw", "close_adj"),
)


def _numeric_values_match(
    actual: pd.Series,
    expected: pd.Series,
) -> pd.Series:
    """严格比较数值与 NaN 位置，不把无穷值或缺失静默等同。"""
    actual_array = pd.to_numeric(actual, errors="coerce").to_numpy(
        dtype="float64",
        na_value=np.nan,
    )
    expected_array = pd.to_numeric(expected, errors="coerce").to_numpy(
        dtype="float64",
        na_value=np.nan,
    )
    matches = (
        (np.isnan(actual_array) & np.isnan(expected_array))
        | (actual_array == expected_array)
    )
    return pd.Series(matches, index=actual.index, dtype=bool)


def _boolean_values_match(
    actual: pd.Series,
    expected: pd.Series,
) -> pd.Series:
    """布尔标志必须逐行存在且与独立重算值完全一致。"""
    try:
        normalized = actual.astype("boolean")
    except (TypeError, ValueError):
        return pd.Series(False, index=actual.index, dtype=bool)
    return normalized.eq(expected.astype("boolean")).fillna(False).astype(bool)


def _independent_us_row_contract(security: pd.DataFrame) -> pd.DataFrame:
    """仅由原始字段独立重算 AS19 行级逻辑、复权价格与收益资格。"""
    _require_frame_columns(
        security,
        US_SOURCE_REQUIRED_COLUMNS,
        "美股逐证券独立行级合同",
    )
    result = security.copy()
    numeric_columns = [
        *_US_RAW_OHLCV_COLUMNS,
        "adj_close",
        "adj_factor",
        *(adjusted for _, adjusted in _US_ADJUSTED_OHLC_MAPPING),
    ]
    numeric = result[numeric_columns].apply(pd.to_numeric, errors="coerce")
    complete_ohlc = numeric[list(_US_RAW_OHLC_COLUMNS)].notna().all(axis=1)
    ohlc_logic = (
        numeric["open_raw"].gt(0)
        & numeric["close_raw"].gt(0)
        & numeric["high_raw"].ge(
            numeric[["open_raw", "close_raw"]].max(axis=1)
        )
        & numeric["low_raw"].le(
            numeric[["open_raw", "close_raw"]].min(axis=1)
        )
        & numeric["high_raw"].ge(numeric["low_raw"])
    )
    result["effective_row_expected"] = numeric[
        list(_US_RAW_OHLCV_COLUMNS)
    ].notna().any(axis=1)
    result["complete_ohlc_expected"] = complete_ohlc
    result["ohlc_logic_valid_expected"] = (~complete_ohlc) | ohlc_logic

    factor = numeric["adj_close"] / numeric["close_raw"]
    factor_valid = factor.gt(0) & np.isfinite(factor)
    result["adj_factor_expected"] = factor.where(factor_valid)
    for raw_column, adjusted_column in _US_ADJUSTED_OHLC_MAPPING:
        adjusted = numeric[raw_column] * result["adj_factor_expected"]
        result[f"{adjusted_column}_expected"] = adjusted.where(
            result["ohlc_logic_valid_expected"] & np.isfinite(adjusted)
        )
    expected_open = result["open_adj_expected"]
    expected_close = result["close_adj_expected"]
    result["return_eligible_expected"] = (
        result["ohlc_logic_valid_expected"]
        & expected_open.gt(0)
        & expected_close.gt(0)
        & np.isfinite(expected_open)
        & np.isfinite(expected_close)
    )
    return result


def _audit_us_security_qualification(
    security: pd.DataFrame,
    *,
    stock_code: str,
    minimum_rate: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """独立重算一只证券的数据资格、硬合同与异常行审计。"""
    if not 0.0 <= minimum_rate <= 1.0:
        raise ValueError("美股逐证券资格比例阈值必须位于 [0, 1]")
    _assert_unique_keys(
        security,
        ("stock_code", "date"),
        f"{stock_code} 逐证券缓存",
    )
    observed_codes = set(security["stock_code"].astype(str))
    if observed_codes != {stock_code}:
        raise ValueError(
            f"{stock_code} 逐证券缓存代码不唯一或不匹配: "
            f"observed={sorted(observed_codes)}"
        )
    contract = _independent_us_row_contract(security)
    effective_mask = contract["effective_row_expected"].astype(bool)
    effective_rows = int(effective_mask.sum())
    non_null_rates = (
        contract.loc[
            effective_mask,
            list(_US_RAW_OHLCV_COLUMNS),
        ].notna().mean()
        if effective_rows
        else pd.Series(0.0, index=_US_RAW_OHLCV_COLUMNS)
    )
    minimum_non_null_rate = (
        float(non_null_rates.min()) if effective_rows else 0.0
    )

    ohlc_expected = contract["ohlc_logic_valid_expected"].astype(bool)
    eligible_expected = contract["return_eligible_expected"].astype(bool)
    ohlc_flag_matches = _boolean_values_match(
        contract["ohlc_logic_valid"],
        ohlc_expected,
    )
    eligible_flag_matches = _boolean_values_match(
        contract["return_eligible"],
        eligible_expected,
    )
    ohlc_flag_mismatch_count = int((~ohlc_flag_matches).sum())
    eligible_flag_mismatch_count = int((~eligible_flag_matches).sum())

    factor_matches = _numeric_values_match(
        contract["adj_factor"],
        contract["adj_factor_expected"],
    )
    adjusted_mismatch_counts: dict[str, int] = {}
    adjusted_matches: dict[str, pd.Series] = {}
    for _, adjusted_column in _US_ADJUSTED_OHLC_MAPPING:
        matches = _numeric_values_match(
            contract[adjusted_column],
            contract[f"{adjusted_column}_expected"],
        )
        adjusted_matches[adjusted_column] = matches
        adjusted_mismatch_counts[adjusted_column] = int((~matches).sum())

    violation_mask = (
        contract["complete_ohlc_expected"].astype(bool) & ~ohlc_expected
    )
    adjusted_is_null = contract[
        [adjusted for _, adjusted in _US_ADJUSTED_OHLC_MAPPING]
    ].isna().all(axis=1)
    stored_eligible_false = _boolean_values_match(
        contract["return_eligible"],
        pd.Series(False, index=contract.index, dtype=bool),
    )
    isolation_complete = adjusted_is_null & stored_eligible_false
    unisolated_violation_count = int(
        (violation_mask & ~isolation_complete).sum()
    )

    stored_open = pd.to_numeric(
        contract["open_adj"],
        errors="coerce",
    ).where(
        pd.to_numeric(contract["open_adj"], errors="coerce").gt(0)
        & np.isfinite(pd.to_numeric(contract["open_adj"], errors="coerce"))
    )
    stored_close = pd.to_numeric(
        contract["close_adj"],
        errors="coerce",
    ).where(
        pd.to_numeric(contract["close_adj"], errors="coerce").gt(0)
        & np.isfinite(pd.to_numeric(contract["close_adj"], errors="coerce"))
    )
    previous_stored_close = stored_close.shift(1)
    actual_opcl = np.log(stored_close / stored_open)
    actual_pvclcl = np.log(stored_close / previous_stored_close)
    previous_expected_eligible = eligible_expected.shift(
        1,
        fill_value=False,
    ).astype(bool)
    invalid_row_used_in_opcl_count = int(
        ((~eligible_expected) & actual_opcl.notna()).sum()
    )
    invalid_or_missing_previous_close_used_in_pvclcl_count = int(
        (
            (~eligible_expected | ~previous_expected_eligible)
            & actual_pvclcl.notna()
        ).sum()
    )

    return_eligible_rows = int(eligible_expected.loc[effective_mask].sum())
    return_eligible_rate = (
        return_eligible_rows / effective_rows if effective_rows else 0.0
    )
    ohlc_violation_count = int(violation_mask.sum())
    factor_mismatch_count = int((~factor_matches).sum())
    adjusted_ohlc_mismatch_count = int(
        sum(adjusted_mismatch_counts.values())
    )
    flag_mismatch_count = (
        ohlc_flag_mismatch_count + eligible_flag_mismatch_count
    )

    hard_failure_reasons: list[str] = []
    if ohlc_flag_mismatch_count:
        hard_failure_reasons.append("ohlc_logic_valid_flag_mismatch")
    if eligible_flag_mismatch_count:
        hard_failure_reasons.append("return_eligible_flag_mismatch")
    if factor_mismatch_count:
        hard_failure_reasons.append("adj_factor_mismatch")
    if adjusted_ohlc_mismatch_count:
        hard_failure_reasons.append("adjusted_ohlc_mismatch")
    if unisolated_violation_count:
        hard_failure_reasons.append("ohlc_violation_not_isolated")
    if invalid_row_used_in_opcl_count:
        hard_failure_reasons.append("invalid_row_used_in_opcl")
    if invalid_or_missing_previous_close_used_in_pvclcl_count:
        hard_failure_reasons.append(
            "invalid_or_missing_previous_close_used_in_pvclcl"
        )

    qualification_failures: list[str] = []
    if not effective_rows:
        qualification_failures.append("empty_effective_interval")
    if minimum_non_null_rate < minimum_rate:
        qualification_failures.append("ohlcv_non_null_rate_below_threshold")
    if return_eligible_rate < minimum_rate:
        qualification_failures.append("return_eligible_rate_below_threshold")
    failure_reasons = [*hard_failure_reasons, *qualification_failures]
    qualified = not failure_reasons
    if hard_failure_reasons:
        qualification_status = "hard_contract_failure"
    elif qualification_failures:
        qualification_status = "failed_rate_threshold"
    else:
        qualification_status = "qualified"

    row: dict[str, Any] = {
        "audit_record_type": "security",
        "market": "US",
        "stock_code": stock_code,
        "rows": len(contract),
        "effective_rows": effective_rows,
        "non_null_ratio": minimum_non_null_rate,
        "minimum_ohlcv_non_null_rate": minimum_non_null_rate,
        "required_minimum_ohlcv_non_null_rate": minimum_rate,
        "ohlc_logic_violation_count": ohlc_violation_count,
        "ohlc_logic_violation_count_independent": ohlc_violation_count,
        "return_eligible_rows": return_eligible_rows,
        "return_eligible_rows_independent": return_eligible_rows,
        "return_eligible_rate": return_eligible_rate,
        "return_eligible_rate_independent": return_eligible_rate,
        "ohlc_logic_valid_mismatch_count": ohlc_flag_mismatch_count,
        "return_eligible_mismatch_count": eligible_flag_mismatch_count,
        "flag_mismatch_count": flag_mismatch_count,
        "adj_factor_mismatch_count": factor_mismatch_count,
        "adjusted_ohlc_mismatch_count": adjusted_ohlc_mismatch_count,
        "unisolated_ohlc_violation_count": unisolated_violation_count,
        "invalid_row_used_in_opcl_count": invalid_row_used_in_opcl_count,
        (
            "invalid_or_missing_previous_close_used_in_pvclcl_count"
        ): invalid_or_missing_previous_close_used_in_pvclcl_count,
        "hard_contract_pass": not hard_failure_reasons,
        "qualified": qualified,
        "qualification_status": qualification_status,
        "qualification_reason": (
            "qualified" if qualified else "|".join(failure_reasons)
        ),
        "failure_reasons": json.dumps(
            failure_reasons,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    row.update(
        {
            f"{column}_non_null_ratio": float(non_null_rates[column])
            for column in _US_RAW_OHLCV_COLUMNS
        }
    )
    row.update(
        {
            f"{column}_mismatch_count": mismatch_count
            for column, mismatch_count in adjusted_mismatch_counts.items()
        }
    )

    exceptions = contract.loc[violation_mask].copy()
    if exceptions.empty:
        exception_audit = pd.DataFrame()
    else:
        exception_audit = pd.DataFrame(
            {
                "audit_record_type": "exception_row",
                "market": "US",
                "stock_code": exceptions["stock_code"].astype(str),
                "date": exceptions["date"],
                **{
                    column: exceptions[column]
                    for column in _US_RAW_OHLCV_COLUMNS
                },
                "adj_close": exceptions["adj_close"],
                "adj_factor_expected": exceptions["adj_factor_expected"],
                "ohlc_logic_valid_expected": exceptions[
                    "ohlc_logic_valid_expected"
                ],
                "ohlc_logic_valid_stored": exceptions["ohlc_logic_valid"],
                **{
                    adjusted: exceptions[adjusted]
                    for _, adjusted in _US_ADJUSTED_OHLC_MAPPING
                },
                **{
                    f"{adjusted}_expected": exceptions[
                        f"{adjusted}_expected"
                    ]
                    for _, adjusted in _US_ADJUSTED_OHLC_MAPPING
                },
                "return_eligible_stored": exceptions["return_eligible"],
                "return_eligible_expected": exceptions[
                    "return_eligible_expected"
                ],
                "isolation_complete": isolation_complete.loc[
                    exceptions.index
                ],
                "security_qualified": qualified,
                "exception_status": np.where(
                    isolation_complete.loc[exceptions.index] & qualified,
                    "identified_isolated_security_qualified",
                    "contract_failure",
                ),
            }
        ).reset_index(drop=True)
    return row, exception_audit


def _us_batch_qualification_summary(
    security_audit: pd.DataFrame,
    *,
    requested_count: int,
    manifest_success_count: int,
    observed_count: int,
    sets_consistent: bool,
    config: M1Config,
) -> dict[str, Any]:
    """汇总固定 501 候选、500/1 资格门槛及行级硬合同。"""
    _require_frame_columns(
        security_audit,
        ("qualified", "hard_contract_pass"),
        "美股逐证券资格审计",
    )
    qualified_count = int(security_audit["qualified"].fillna(False).sum())
    failed_count = len(security_audit) - qualified_count
    hard_contract_pass = bool(
        security_audit["hard_contract_pass"].fillna(False).all()
    )
    fixed_candidate_count_pass = (
        requested_count == config.us_yahoo.expected_constituents
        and manifest_success_count == config.us_yahoo.expected_constituents
        and observed_count == config.us_yahoo.expected_constituents
    )
    coverage_gate_pass = (
        qualified_count >= config.us_yahoo.minimum_successful_securities
        and failed_count <= config.us_yahoo.maximum_failed_securities
        and observed_count >= config.sample.stocks_per_market
    )
    batch_gate_pass = (
        fixed_candidate_count_pass
        and sets_consistent
        and hard_contract_pass
        and coverage_gate_pass
    )
    return {
        "audit_record_type": "batch_summary",
        "market": "US",
        "requested_count": requested_count,
        "manifest_success_count": manifest_success_count,
        "observed_count": observed_count,
        "qualified_count": qualified_count,
        "failed_count": failed_count,
        "expected_constituents": config.us_yahoo.expected_constituents,
        "minimum_successful_securities": (
            config.us_yahoo.minimum_successful_securities
        ),
        "maximum_failed_securities": (
            config.us_yahoo.maximum_failed_securities
        ),
        "sets_consistent": sets_consistent,
        "fixed_candidate_count_pass": fixed_candidate_count_pass,
        "independent_flags_consistent": bool(
            security_audit["flag_mismatch_count"].fillna(0).eq(0).all()
        )
        if "flag_mismatch_count" in security_audit
        else hard_contract_pass,
        "isolation_complete": bool(
            security_audit["unisolated_ohlc_violation_count"]
            .fillna(0)
            .eq(0)
            .all()
        )
        if "unisolated_ohlc_violation_count" in security_audit
        else hard_contract_pass,
        "hard_contract_pass": hard_contract_pass,
        "coverage_gate_pass": coverage_gate_pass,
        "batch_gate_pass": batch_gate_pass,
        "invalid_row_used_in_opcl_count": int(
            security_audit["invalid_row_used_in_opcl_count"].fillna(0).sum()
        )
        if "invalid_row_used_in_opcl_count" in security_audit
        else 0,
        "invalid_or_missing_previous_close_used_in_pvclcl_count": int(
            security_audit[
                "invalid_or_missing_previous_close_used_in_pvclcl_count"
            ].fillna(0).sum()
        )
        if (
            "invalid_or_missing_previous_close_used_in_pvclcl_count"
            in security_audit
        )
        else 0,
    }


def _assert_us_batch_qualification_gate(summary: Mapping[str, Any]) -> None:
    """硬合同或固定 500/1 门槛不满足时停止 M1。"""
    if not bool(summary.get("fixed_candidate_count_pass")):
        raise ValueError(
            "美股固定候选集合数量门禁失败: "
            f"requested={summary.get('requested_count')}, "
            f"manifest_success={summary.get('manifest_success_count')}, "
            f"observed={summary.get('observed_count')}, "
            f"expected={summary.get('expected_constituents')}"
        )
    if not bool(summary.get("sets_consistent")):
        raise ValueError("美股请求、manifest success 与合并面板集合不一致")
    if not bool(summary.get("hard_contract_pass")):
        raise ValueError("美股独立标志、复权衍生或收益隔离硬合同失败")
    if not bool(summary.get("coverage_gate_pass")):
        raise ValueError(
            "美股正式合并面板覆盖门禁失败: "
            f"qualified={summary.get('qualified_count')}, "
            f"failed={summary.get('failed_count')}, "
            f"observed={summary.get('observed_count')}"
        )


def audit_us_merged_panel_contract(
    panel: pd.DataFrame,
    requested_stock_codes: Sequence[str],
    *,
    config: M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """闭环核验 AS24–AS26 的请求集、逐证券缓存、manifest 与合并面板。

    正式 M1 不采信下载时写入的摘要：这里重新计算正文哈希、逐证券
    OHLCV 合格性，并把每个逐证券缓存与合并面板对应切片做精确内容比较。
    任一集合、请求参数、内容或数量合同不一致时直接失败。
    """
    _require_frame_columns(panel, US_SOURCE_REQUIRED_COLUMNS, "美股合并面板")
    _assert_unique_keys(panel, ("stock_code", "date"), "美股合并面板")
    manifest_path = _require_file(config.us_yahoo.manifest_path)
    merged_path = _require_file(config.us_yahoo.merged_panel_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_request = {
        "start": config.sample.start_date,
        "end_exclusive": config.sample.end_exclusive,
        "interval": config.us_yahoo.interval,
        "auto_adjust": config.us_yahoo.auto_adjust,
        "actions": config.us_yahoo.actions,
        "repair": config.us_yahoo.repair,
        "keepna": config.us_yahoo.keepna,
        "threads": config.us_yahoo.threads,
        "timeout_seconds": config.us_yahoo.timeout_seconds,
    }
    if manifest.get("request") != expected_request:
        raise ValueError(
            "Yahoo manifest 请求参数与正式配置不一致: "
            f"actual={manifest.get('request')}, expected={expected_request}"
        )
    merged_manifest = manifest.get("merged_panel", {})
    actual_merged_hash = _file_sha256(merged_path)
    merged_schema = pq.ParquetFile(merged_path).schema_arrow
    merged_relative = merged_path.relative_to(
        config.us_yahoo.cache_dir.resolve()
    ).as_posix()
    if (
        merged_manifest.get("file")
        != merged_relative
        or merged_manifest.get("sha256") != actual_merged_hash
        or int(merged_manifest.get("rows", -1)) != len(panel)
        or int(merged_manifest.get("qualified_security_count", -1))
        != panel["stock_code"].astype(str).nunique()
    ):
        raise ValueError(
            "Yahoo 合并面板文件、正文 SHA256、行数或证券数与 manifest 不一致"
        )

    requested = tuple(dict.fromkeys(str(code) for code in requested_stock_codes))
    if len(requested) != len(requested_stock_codes):
        raise ValueError("美股请求代码集合含重复证券")
    if len(requested) != config.us_yahoo.expected_constituents:
        raise ValueError(
            "美股固定候选集合数量门禁失败: "
            f"requested={len(requested)}, "
            f"expected={config.us_yahoo.expected_constituents}"
        )
    entries = manifest.get("entries", {})
    successful = {
        str(code)
        for code, entry in entries.items()
        if entry.get("status") == "success"
    }
    requested_set = set(requested)
    observed_set = set(panel["stock_code"].astype(str))
    if requested_set != successful or requested_set != observed_set:
        raise ValueError(
            "美股请求集合、manifest success 集合与合并面板集合不一致: "
            f"requested_only={sorted(requested_set - observed_set)[:20]}, "
            f"panel_only={sorted(observed_set - requested_set)[:20]}, "
            f"manifest_only={sorted(successful - requested_set)[:20]}"
        )

    rows: list[dict[str, Any]] = []
    exception_frames: list[pd.DataFrame] = []
    compare_columns = list(US_SOURCE_REQUIRED_COLUMNS)
    for stock_code in requested:
        entry = entries[stock_code]
        relative = entry.get("file")
        expected_hash = entry.get("file_sha256")
        if not relative or not expected_hash:
            raise ValueError(f"{stock_code} success 条目缺少文件或 SHA256")
        security_path = _require_file(
            config.us_yahoo.cache_dir / str(relative)
        )
        if _file_sha256(security_path) != expected_hash:
            raise ValueError(f"{stock_code} 逐证券缓存正文 SHA256 不一致")
        security_schema = pq.ParquetFile(security_path).schema_arrow
        _assert_semantic_arrow_schema_equal(
            security_schema,
            merged_schema,
            context=f"{stock_code} 逐证券缓存与合并面板",
        )
        security = pd.read_parquet(security_path, columns=compare_columns)
        manifest_rows = int(entry.get("rows", -1))
        if manifest_rows != len(security):
            raise ValueError(
                f"{stock_code} 逐证券缓存行数与 manifest 不一致: "
                f"actual={len(security)}, expected={manifest_rows}"
            )
        security = _normalize_keys(security, "stock_code").sort_values(
            ["stock_code", "date"]
        ).reset_index(drop=True)
        merged_security = panel.loc[
            panel["stock_code"].astype(str).eq(stock_code),
            compare_columns,
        ].sort_values(["stock_code", "date"]).reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(
                merged_security,
                security,
                check_dtype=False,
                check_like=False,
            )
        except AssertionError as exc:
            raise ValueError(
                f"{stock_code} 合并面板切片与逐证券 manifest 缓存内容不一致"
            ) from exc
        qualification, exceptions = _audit_us_security_qualification(
            security,
            stock_code=stock_code,
            minimum_rate=config.us_yahoo.minimum_ohlcv_non_null_rate,
        )
        qualification.update(
            {
                "requested": True,
                "manifest_success": True,
                "present_in_merged_panel": True,
                "individual_file": str(relative),
                "manifest_rows": manifest_rows,
                "row_count_matches_manifest": True,
                "first_date": security["date"].min(),
                "last_date": security["date"].max(),
                "individual_file_sha256": expected_hash,
                "merged_panel_sha256": actual_merged_hash,
                "individual_semantic_schema_sha256": (
                    _semantic_arrow_schema_sha256(security_schema)
                ),
                "merged_semantic_schema_sha256": (
                    _semantic_arrow_schema_sha256(merged_schema)
                ),
                "semantic_schema_identical": True,
                "content_identical_to_individual_cache": True,
            }
        )
        rows.append(qualification)
        if not exceptions.empty:
            exceptions["individual_file"] = str(relative)
            exceptions["individual_file_sha256"] = expected_hash
            exception_frames.append(exceptions)
    security_audit = pd.DataFrame(rows)
    batch_summary = _us_batch_qualification_summary(
        security_audit,
        requested_count=len(requested),
        manifest_success_count=len(successful),
        observed_count=len(observed_set),
        sets_consistent=(
            requested_set == successful == observed_set
        ),
        config=config,
    )
    try:
        _assert_us_batch_qualification_gate(batch_summary)
    except ValueError as exc:
        failures = security_audit.loc[
            ~security_audit["qualified"].fillna(False),
            ["stock_code", "qualification_status", "failure_reasons"],
        ]
        raise ValueError(
            f"{exc}; failing_securities="
            f"{failures.head(20).to_dict(orient='records')}"
        ) from exc
    output_frames = [security_audit]
    if exception_frames:
        output_frames.append(
            pd.concat(exception_frames, ignore_index=True, sort=False)
        )
    output_frames.append(pd.DataFrame([batch_summary]))
    return pd.concat(
        output_frames,
        ignore_index=True,
        sort=False,
    ).reset_index(drop=True)


def audit_security_calendar_coverage(
    panel: pd.DataFrame,
    universe: pd.DataFrame,
    calendar: pd.DataFrame,
    *,
    market: str,
) -> pd.DataFrame:
    """逐证券登记实际日期覆盖、收益缺失和股票池集合闭环。"""
    _require_frame_columns(
        panel,
        (
            "stock_code",
            "date",
            "pvclcl_raw",
            "opcl_raw",
            "pvclcl_excess",
            "opcl_excess",
        ),
        f"{market} 收益面板",
    )
    _require_frame_columns(universe, ("stock_code",), f"{market} 股票池")
    _require_frame_columns(calendar, ("date",), f"{market} 交易日历")
    expected_codes = set(universe["stock_code"].astype(str))
    observed_codes = set(panel["stock_code"].astype(str))
    universe_only = expected_codes - observed_codes
    panel_only = observed_codes - expected_codes
    allowed_universe_only = (
        DEFAULT_CONFIG.us_yahoo.maximum_failed_securities
        if market == "US"
        else 0
    )
    minimum_observed = (
        DEFAULT_CONFIG.us_yahoo.minimum_successful_securities
        if market == "US"
        else len(expected_codes)
    )
    if (
        panel_only
        or len(universe_only) > allowed_universe_only
        or len(observed_codes) < minimum_observed
    ):
        raise ValueError(
            f"{market} 股票池与收益面板集合不一致: "
            f"universe_only={sorted(universe_only)[:20]}, "
            f"panel_only={sorted(panel_only)[:20]}, "
            f"allowed_universe_only={allowed_universe_only}, "
            f"minimum_observed={minimum_observed}"
        )
    expected_dates = pd.DatetimeIndex(
        pd.to_datetime(calendar["date"], errors="raise").dt.normalize()
    ).unique()
    grouped = panel.assign(
        stock_code=panel["stock_code"].astype(str),
        date=pd.to_datetime(panel["date"], errors="raise").dt.normalize(),
    ).groupby("stock_code", observed=True, sort=True)
    rows = []
    for stock_code, frame in grouped:
        observed_dates = pd.DatetimeIndex(frame["date"].drop_duplicates())
        rows.append(
            {
                "market": market,
                "stock_code": stock_code,
                "expected_calendar_days": len(expected_dates),
                "observed_calendar_days": int(
                    expected_dates.isin(observed_dates).sum()
                ),
                "calendar_coverage_ratio": (
                    float(expected_dates.isin(observed_dates).mean())
                    if len(expected_dates)
                    else np.nan
                ),
                "first_date": frame["date"].min(),
                "last_date": frame["date"].max(),
                "pvclcl_raw_missing_ratio": float(
                    frame["pvclcl_raw"].isna().mean()
                ),
                "opcl_raw_missing_ratio": float(
                    frame["opcl_raw"].isna().mean()
                ),
                "pvclcl_excess_missing_ratio": float(
                    frame["pvclcl_excess"].isna().mean()
                ),
                "opcl_excess_missing_ratio": float(
                    frame["opcl_excess"].isna().mean()
                ),
                "universe_membership_confirmed": True,
            }
        )
    return pd.DataFrame(rows)


def audit_return_distributions(
    panels: DualMarketReturnPanels,
) -> pd.DataFrame:
    """输出双市场四类收益的分布与缺失率底表。"""
    rows = []
    for market, frame in (("US", panels.us), ("CN", panels.cn)):
        for column in (
            "pvclcl_raw",
            "opcl_raw",
            "pvclcl_excess",
            "opcl_excess",
        ):
            values = pd.to_numeric(frame[column], errors="coerce")
            finite = values[np.isfinite(values)]
            rows.append(
                {
                    "market": market,
                    "return_column": column,
                    "row_count": len(values),
                    "finite_count": len(finite),
                    "missing_ratio": float(values.isna().mean()),
                    "mean": float(finite.mean()) if len(finite) else np.nan,
                    "std": float(finite.std(ddof=1)) if len(finite) > 1 else np.nan,
                    "q01": float(finite.quantile(0.01)) if len(finite) else np.nan,
                    "q25": float(finite.quantile(0.25)) if len(finite) else np.nan,
                    "q50": float(finite.quantile(0.50)) if len(finite) else np.nan,
                    "q75": float(finite.quantile(0.75)) if len(finite) else np.nan,
                    "q99": float(finite.quantile(0.99)) if len(finite) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def audit_loaded_market_panel(
    frame: pd.DataFrame,
    *,
    dataset_name: str,
    key_columns: Sequence[str],
    required_columns: Sequence[str],
    unit_contract: Mapping[str, str],
    expected_calendar: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """审计已裁剪面板的键、缺失、覆盖、单位与 OHLC 逻辑。"""
    rows: list[dict[str, Any]] = []
    actual_columns = set(frame.columns)
    for column in required_columns:
        present = column in actual_columns
        rows.append(
            {
                "dataset": dataset_name,
                "audit_type": "field_presence",
                "item": column,
                "actual": present,
                "expected": True,
                "status": "pass" if present else "fail",
                "detail": None,
            }
        )
        if present:
            missing_rate = float(frame[column].isna().mean()) if len(frame) else np.nan
            rows.append(
                {
                    "dataset": dataset_name,
                    "audit_type": "missing_rate",
                    "item": column,
                    "actual": missing_rate,
                    "expected": "仅审计，不填补（AS2）",
                    "status": "observed",
                    "detail": None,
                }
            )
        if column in unit_contract:
            rows.append(
                {
                    "dataset": dataset_name,
                    "audit_type": "unit_contract",
                    "item": column,
                    "actual": unit_contract[column],
                    "expected": "AS9–AS11",
                    "status": "declared_not_source_certified",
                    "detail": None,
                }
            )
    if set(key_columns).issubset(actual_columns):
        duplicate_count = int(frame.duplicated(list(key_columns)).sum())
        rows.append(
            {
                "dataset": dataset_name,
                "audit_type": "duplicate_key_count",
                "item": "+".join(key_columns),
                "actual": duplicate_count,
                "expected": 0,
                "status": "pass" if duplicate_count == 0 else "fail",
                "detail": None,
            }
        )
    if "date" in frame and len(frame):
        observed_dates = pd.DatetimeIndex(
            pd.to_datetime(frame["date"], errors="raise").dt.normalize()
        ).unique()
        rows.extend(
            [
                {
                    "dataset": dataset_name,
                    "audit_type": "coverage",
                    "item": "observed_start",
                    "actual": observed_dates.min(),
                    "expected": None,
                    "status": "observed",
                    "detail": None,
                },
                {
                    "dataset": dataset_name,
                    "audit_type": "coverage",
                    "item": "observed_end",
                    "actual": observed_dates.max(),
                    "expected": None,
                    "status": "observed",
                    "detail": None,
                },
            ]
        )
        if expected_calendar is not None:
            _require_frame_columns(expected_calendar, ("date",), "预期交易日历")
            expected_dates = pd.DatetimeIndex(
                pd.to_datetime(expected_calendar["date"], errors="raise").dt.normalize()
            ).unique()
            coverage = (
                float(expected_dates.isin(observed_dates).mean())
                if len(expected_dates)
                else np.nan
            )
            rows.append(
                {
                    "dataset": dataset_name,
                    "audit_type": "calendar_coverage",
                    "item": "2014_2021",
                    "actual": coverage,
                    "expected": "按对应目标交易日历审计",
                    "status": "observed",
                    "detail": f"expected_days={len(expected_dates)}",
                }
            )
    ohlc_columns = {"open", "high", "low", "close"}
    if ohlc_columns.issubset(actual_columns):
        ohlc = frame[list(ohlc_columns)].apply(pd.to_numeric, errors="coerce")
        valid = ohlc.notna().all(axis=1)
        violations = (
            ohlc["open"].le(0)
            | ohlc["close"].le(0)
            | ohlc["high"].lt(ohlc[["open", "close"]].max(axis=1))
            | ohlc["low"].gt(ohlc[["open", "close"]].min(axis=1))
            | ohlc["high"].lt(ohlc["low"])
        ) & valid
        rows.append(
            {
                "dataset": dataset_name,
                "audit_type": "ohlc_logic",
                "item": "violation_count",
                "actual": int(violations.sum()),
                "expected": 0,
                "status": "pass" if not violations.any() else "fail",
                "detail": f"complete_ohlc_rows={int(valid.sum())}",
            }
        )
    return pd.DataFrame(rows)


def audit_dual_market_return_panels(
    panels: DualMarketReturnPanels,
    *,
    us_calendar: pd.DataFrame,
    cn_calendar: pd.DataFrame,
) -> pd.DataFrame:
    """汇总 D1–D8 对应的双市场标准面板审计接口。"""
    common_required = (
        "market",
        "stock_code",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "traded_amount",
        "pvclcl_raw",
        "opcl_raw",
        "pvclcl_market",
        "opcl_market",
        "pvclcl_excess",
        "opcl_excess",
        "traded_amount_median_21d",
    )
    us_required = (
        *common_required,
        "source_symbol",
        "yahoo_symbol",
        "open_raw",
        "high_raw",
        "low_raw",
        "close_raw",
        "adj_close",
        "dividends",
        "stock_splits",
        "adj_factor",
        "ohlc_logic_valid",
        "return_eligible",
    )
    cn_required = (*common_required, "market_cap")
    us = audit_loaded_market_panel(
        panels.us,
        dataset_name="US_return_panel",
        key_columns=("stock_code", "date"),
        required_columns=us_required,
        unit_contract=US_UNIT_CONTRACT,
        expected_calendar=us_calendar,
    )
    cn = audit_loaded_market_panel(
        panels.cn,
        dataset_name="CN_return_panel",
        key_columns=("stock_code", "date"),
        required_columns=cn_required,
        unit_contract=CN_UNIT_CONTRACT,
        expected_calendar=cn_calendar,
    )
    return pd.concat([us, cn], ignore_index=True)
