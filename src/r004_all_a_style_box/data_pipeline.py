"""m1：沪深北动态全 A 与 PIT 月度数据底座。

数据合同按完整持有月组织：前一自然月最后交易日为 ``signal_date``，其后
第一个交易日为 ``execution_date``，下一持有月执行日为 ``return_date``。
信号池只由 T 日信息决定；T+1 状态仅形成方向性可成交标记，不反向影响信号池。
估值只接受 T 日原始记录，财务只接受 ``info_publ_date <= signal_date`` 的披露。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Final, Iterable

import numpy as np
import pandas as pd

from common.data_loader import load_trade_calendar

from .config import AllAStyleBoxConfig, DEFAULT_CONFIG


KEYS: Final[list[str]] = ["signal_date", "stock_code"]


@dataclass(frozen=True)
class M1Dataset:
    """m2/m3 可稳定消费的 m1 数据合同。"""

    schedule: pd.DataFrame
    monthly_panel: pd.DataFrame
    exclusion_audit: pd.DataFrame
    availability_audit: pd.DataFrame
    source_catalog: pd.DataFrame
    exchange_code_audit: pd.DataFrame


def _sha256_file(path: Path) -> str:
    """流式计算冻结文件哈希，避免把大型 PDF 一次性读入内存。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_transfer_source_manifest(
    config: AllAStyleBoxConfig,
    *,
    data_root: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """校验 600466→400165 冻结包，不发起任何网络请求。"""
    root = Path(data_root or config.security_transfer_data_root).resolve()
    manifest_path = root / config.security_transfer_manifest_filename
    if not manifest_path.is_file():
        raise FileNotFoundError(f"退市转板冻结源缺 source_manifest: {manifest_path}")
    manifest_hash = _sha256_file(manifest_path)
    if manifest_hash != config.security_transfer_manifest_sha256:
        raise ValueError(
            "退市转板source_manifest SHA-256不符: "
            f"expected={config.security_transfer_manifest_sha256} actual={manifest_hash}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("offline_runtime_only") is not True:
        raise ValueError("退市转板冻结源必须声明 offline_runtime_only=true")
    if manifest.get("successor_whitelist") != [config.security_transfer_new_code]:
        raise ValueError("退市转板第三方源白名单必须且只能包含400165")
    if manifest.get("lifecycle_scope") != {
        config.security_transfer_old_code: config.security_transfer_new_code
    }:
        raise ValueError("退市转板冻结源不得扩展到600466→400165之外")

    expected = dict(config.security_transfer_frozen_sha256)
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != config.security_transfer_source_count:
        raise ValueError("退市转板 source_manifest 源数量不符合冻结合同")
    manifest_hashes: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("退市转板 source_manifest.sources 必须为对象列表")
        for artifact_key in ("raw", "parsed"):
            artifact = source.get(artifact_key)
            if not isinstance(artifact, dict):
                raise ValueError(f"退市转板源缺{artifact_key}产物登记")
            filename = str(artifact.get("file", ""))
            sha256 = str(artifact.get("sha256", ""))
            if not filename or len(sha256) != config.sha256_hex_length:
                raise ValueError(f"退市转板{artifact_key}产物缺文件名或SHA-256")
            manifest_hashes[filename] = sha256
        required_source_fields = {
            "source_id", "url", "downloaded_at_utc", "http_request",
            "code_range", "date_range", "fields_and_units",
        }
        if not required_source_fields.issubset(source):
            missing = sorted(required_source_fields.difference(source))
            raise ValueError(f"退市转板源清单字段不完整: {missing}")
    if manifest_hashes != expected:
        raise ValueError("source_manifest登记文件或哈希与config冻结值不一致")
    for filename, expected_hash in expected.items():
        path = root / filename
        if not path.is_file():
            raise FileNotFoundError(f"退市转板冻结文件缺失: {path}")
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"退市转板冻结文件SHA-256不符: {filename} "
                f"expected={expected_hash} actual={actual_hash}"
            )
    return root, manifest


def load_frozen_transfer_market_data(
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
    *,
    data_root: Path | None = None,
) -> pd.DataFrame:
    """断网读取并校验400165同花顺原始日线，仅服务600466生命周期退出。

    替代裁决只允许在首日OHLC四价完全相同且``volumn``正时，把退化为单点
    的价格作为数学确定VWAP。源没有成交额，``amount``始终保留为空，绝不
    反推后冒充源字段。
    """
    root, manifest = _load_transfer_source_manifest(config, data_root=data_root)
    source_by_id = {str(source["source_id"]): source for source in manifest["sources"]}
    source = source_by_id.get(config.security_transfer_market_source_id)
    if source is None:
        raise ValueError("source_manifest缺同花顺400165冻结源")
    params = source["http_request"].get("params", {})
    expected_params = dict(config.security_transfer_market_http_params)
    if params != expected_params:
        raise ValueError("同花顺冻结源HTTP参数漂移")

    raw_path = root / config.security_transfer_market_raw_filename
    raw_hash = dict(config.security_transfer_frozen_sha256)[raw_path.name]
    wrapped = raw_path.read_text(encoding="utf-8")
    callback_prefix = f"{config.security_transfer_market_callback}("
    if not wrapped.startswith(callback_prefix) or not wrapped.endswith(")"):
        raise ValueError("同花顺all.js callback包装不符合冻结合同")
    payload = json.loads(wrapped[len(callback_prefix):-1])
    if int(payload.get("total", -1)) != config.security_transfer_market_row_count:
        raise ValueError("同花顺all.js total不等于429")
    if str(payload.get("start", "")) != config.security_transfer_market_start_yyyymmdd:
        raise ValueError("同花顺all.js start不等于20230726")
    if str(payload.get("name", "")) != config.security_transfer_new_name:
        raise ValueError("同花顺all.js证券名称不等于蓝光3")
    price_factor = int(payload.get("priceFactor", 0))
    if price_factor != config.security_transfer_price_factor:
        raise ValueError("同花顺all.js priceFactor不符合未复权价格合同")
    if str(payload.get("issuePrice", "")) != config.security_transfer_issue_price_text:
        raise ValueError("同花顺all.js issuePrice不等于0.40")

    total = config.security_transfer_market_row_count
    price_values = pd.to_numeric(
        pd.Series(str(payload.get("price", "")).split(",")), errors="coerce"
    )
    if len(price_values) != total * config.security_transfer_ohlc_field_count:
        raise ValueError("同花顺all.js price压缩字段数量不等于429×4")
    price_matrix = price_values.to_numpy(dtype=float).reshape(
        total, config.security_transfer_ohlc_field_count
    )
    if not np.isfinite(price_matrix).all() or not np.allclose(
        price_matrix[:, 1:],
        np.zeros_like(price_matrix[:, 1:]),
        rtol=config.numeric_tolerance,
        atol=config.numeric_tolerance,
    ):
        raise ValueError("同花顺all.js OHLC压缩差分非零，不能按单一成交价解析")
    single_price = price_matrix[:, 0] / price_factor

    date_tokens = str(payload.get("dates", "")).split(",")
    volume_shares = pd.to_numeric(
        pd.Series(str(payload.get("volumn", "")).split(",")), errors="coerce"
    ).to_numpy(dtype=float)
    if len(date_tokens) != total or len(volume_shares) != total:
        raise ValueError("同花顺all.js dates/volumn行数不等于429")
    year_counts = payload.get("sortYear")
    if not isinstance(year_counts, list) or sum(int(item[1]) for item in year_counts) != total:
        raise ValueError("同花顺all.js sortYear不能覆盖429行")
    years = np.concatenate(
        [np.repeat(int(year), int(count)) for year, count in year_counts]
    )
    full_dates = pd.to_datetime(
        pd.Series(years.astype(str)) + pd.Series(date_tokens),
        format="%Y%m%d",
        errors="coerce",
    ).dt.normalize()
    market = pd.DataFrame(
        {
            "stock_code": config.security_transfer_new_code,
            "date": full_dates,
            "open": single_price,
            "close": single_price,
            "high": single_price,
            "low": single_price,
            "volumn": volume_shares,
            "volume_unit": config.security_transfer_market_volume_unit,
            "volume_shares": volume_shares,
            "amount": np.nan,
            "amount_status": config.security_transfer_market_amount_status,
            "daily_vwap": single_price,
            "vwap_proof_method": "positive_volume_and_identical_ohlc_single_price",
        }
    )
    if market[["date", "open", "close", "high", "low", "volumn"]].isna().any(axis=None):
        raise ValueError("同花顺all.js含不可解析日期、价格或成交量")
    if market["date"].duplicated().any() or not market["date"].is_monotonic_increasing:
        raise ValueError("同花顺冻结行情日期必须严格递增且唯一")
    if market["date"].min() != pd.Timestamp(config.security_transfer_effective_date):
        raise ValueError("同花顺冻结行情首日不是400165进入退市板块日")
    if market["date"].max() != pd.Timestamp(config.security_transfer_market_end_date):
        raise ValueError("同花顺冻结行情末日与sortYear/dates不一致")

    positive_trade = market["volumn"].gt(0)
    first = market.iloc[0]
    if not positive_trade.iloc[0]:
        raise ValueError("400165首个真实成交日volumn不为正")
    if float(first["volumn"]) != config.security_transfer_expected_first_volume_shares:
        raise ValueError("400165首日volumn不等于5,753,700股")
    first_ohlc = first[["open", "high", "low", "close"]].to_numpy(dtype=float)
    if not np.allclose(
        first_ohlc,
        np.full(len(first_ohlc), config.security_transfer_expected_exit_vwap),
        rtol=config.numeric_tolerance,
        atol=config.numeric_tolerance,
    ):
        raise ValueError("400165首日OHLC并非全部0.38元")

    parsed_path = root / config.security_transfer_market_parsed_filename
    parsed = pd.read_csv(parsed_path, dtype={"stock_code": str})
    parsed["stock_code"] = parsed["stock_code"].str.zfill(6)
    parsed["date"] = pd.to_datetime(parsed["date"], errors="coerce").dt.normalize()
    compare_columns = [
        "stock_code", "date", "open", "close", "high", "low",
        "volumn", "volume_unit", "amount_status", "vwap", "vwap_proof_method",
    ]
    if list(parsed.columns) != compare_columns or len(parsed) != len(market):
        raise ValueError("同花顺解析CSV字段或行数与冻结合同不一致")
    if not parsed[["stock_code", "date"]].equals(market[["stock_code", "date"]]):
        raise ValueError("同花顺解析CSV代码/日期与原始all.js不一致")
    numeric_compare = ("open", "close", "high", "low", "volumn", "vwap")
    expected_numeric = market.assign(vwap=market["daily_vwap"])
    for column in numeric_compare:
        if not np.allclose(
            pd.to_numeric(parsed[column], errors="coerce"),
            pd.to_numeric(expected_numeric[column], errors="coerce"),
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
            equal_nan=True,
        ):
            raise ValueError(f"同花顺解析CSV字段{column}与原始all.js不一致")
    for column in ("volume_unit", "amount_status", "vwap_proof_method"):
        if not parsed[column].astype(str).equals(expected_numeric[column].astype(str)):
            raise ValueError(f"同花顺解析CSV字段{column}与原始all.js不一致")

    market["daily_vwap_valid"] = (
        positive_trade
        & market[["open", "high", "low", "close"]].nunique(axis=1).eq(1)
        & market["daily_vwap"].gt(0)
    )
    market["daily_no_volume"] = ~positive_trade
    market["daily_can_sell"] = market["daily_vwap_valid"]
    market["active_suspension"] = False
    market["daily_limit_down"] = False
    market["delisting_board_flag"] = True
    market["external_transfer_exit_only"] = True
    market["external_source_sha256"] = raw_hash
    market["external_source_file"] = raw_path.name
    market["external_source_id"] = config.security_transfer_market_source_id
    market["amount_available"] = False
    market["source_price_basis"] = config.security_transfer_market_price_basis
    return market.sort_values("date", kind="mergesort").reset_index(drop=True)


def _normalise_date(frame: pd.DataFrame, column: str = "date") -> pd.DataFrame:
    result = frame.copy()
    result[column] = pd.to_datetime(result[column], errors="coerce").dt.normalize()
    return result


def _read_dates(
    path: object,
    columns: Iterable[str],
    dates: pd.Series | pd.DatetimeIndex,
) -> pd.DataFrame:
    """用 Parquet 下推只读取指定交易日。"""
    unique_dates = pd.DatetimeIndex(pd.to_datetime(dates).dropna().unique()).sort_values()
    if unique_dates.empty:
        return pd.DataFrame(columns=list(columns))
    frame = pd.read_parquet(
        path,
        columns=list(columns),
        filters=[("date", "in", unique_dates.to_pydatetime().tolist())],
    )
    frame = _normalise_date(frame)
    frame["stock_code"] = frame["stock_code"].astype(str)
    return frame


def _deduplicate_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """同一证券日只保留文件中的最后一条，保持后续 one-to-one 连接。"""
    if frame.empty:
        return frame
    return (
        frame.sort_values(["date", "stock_code"])
        .drop_duplicates(["stock_code", "date"], keep="last")
        .reset_index(drop=True)
    )


def load_rebalance_schedule(
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
    *,
    smoke_months: int | None = None,
) -> pd.DataFrame:
    """生成 2015-01 至 2025-12 的信号、执行、收益端点日历。

    ``holding_month=2015-01`` 的信号日位于 2014-12 月末；这一前置月末只为
    实现 T 日信号、下一交易日执行，不扩展绩效样本。
    """
    calendar = load_trade_calendar(
        config.data_root,
        start_date=config.calendar_start,
        end_date=config.calendar_end,
    )
    calendar = (
        calendar[["date", "IfMonthEnd"]]
        .drop_duplicates("date")
        .sort_values("date")
        .reset_index(drop=True)
    )
    trading_days = pd.DatetimeIndex(calendar["date"])
    month_ends = pd.DatetimeIndex(calendar.loc[calendar["IfMonthEnd"].eq(1), "date"])
    positions = trading_days.searchsorted(month_ends, side="right")
    valid = positions < len(trading_days)
    schedule = pd.DataFrame(
        {
            "signal_date": month_ends[valid],
            "execution_date": trading_days[positions[valid]],
        }
    )
    schedule["return_date"] = schedule["execution_date"].shift(-1)
    start = pd.Timestamp(config.history_start)
    end = pd.Timestamp(config.history_end)
    schedule = schedule.loc[schedule["execution_date"].between(start, end)].copy()
    schedule["holding_month"] = schedule["execution_date"].dt.to_period("M").astype(str)
    schedule["sample_phase"] = np.select(
        [
            schedule["execution_date"].le(pd.Timestamp(config.freeze_end)),
            schedule["execution_date"].between(
                pd.Timestamp(config.oos_start), pd.Timestamp(config.oos_end)
            ),
        ],
        ["frozen_history", "formal_oos"],
        default="outside_scope",
    )
    schedule["signal_within_freeze_period"] = schedule["signal_date"].le(
        pd.Timestamp(config.freeze_end)
    )
    schedule = schedule.reset_index(drop=True)
    if smoke_months is not None:
        if smoke_months <= 0:
            raise ValueError("smoke_months 必须为正整数")
        schedule = schedule.tail(smoke_months).reset_index(drop=True)
    return schedule


def classify_exchange(
    stock_codes: pd.Series,
    signal_dates: pd.Series,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """按代码与信号日透明识别沪深北，原代码不改写。

    北交所号段在 2021-11-15 前标为 ``PRE_BSE_NEEQ``，不会伪装成 BJ。
    """
    codes = stock_codes.astype(str).str.zfill(6)
    dates = pd.to_datetime(signal_dates, errors="coerce").dt.normalize()
    prefix = codes.str[:2]
    is_bse_prefix = prefix.isin(config.beijing_prefixes)
    bse_active = is_bse_prefix & dates.ge(pd.Timestamp(config.beijing_exchange_start))
    exchange = np.select(
        [
            prefix.isin(config.shanghai_prefixes),
            prefix.isin(config.shenzhen_prefixes),
            bse_active,
            is_bse_prefix,
        ],
        ["SH", "SZ", "BJ", "PRE_BSE_NEEQ"],
        default="UNKNOWN",
    )
    board = np.select(
        [
            prefix.eq("68"),
            prefix.eq("30"),
            bse_active,
            is_bse_prefix,
            prefix.eq("60"),
            prefix.eq("00"),
        ],
        ["STAR", "CHINEXT", "BSE", "NEEQ", "SH_MAIN", "SZ_MAIN"],
        default="UNKNOWN",
    )
    return pd.DataFrame(
        {
            "stock_code": codes,
            "code_prefix": prefix,
            "exchange": exchange,
            "board": board,
            "is_bse_code_prefix": is_bse_prefix,
            "bse_effective_date": pd.Timestamp(config.beijing_exchange_start),
            "exchange_active_on_signal": np.isin(exchange, ["SH", "SZ", "BJ"]),
            "code_mapping_applied": False,
        },
        index=stock_codes.index,
    )


def _load_market_slices(
    config: AllAStyleBoxConfig,
    schedule: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    dates = pd.concat(
        [schedule["signal_date"], schedule["execution_date"], schedule["return_date"]],
        ignore_index=True,
    )
    price = _deduplicate_daily(
        _read_dates(
            config.path("price_forward"),
            [
                "stock_code", "stock_name", "date", "adj_factor", "prev_close",
                "open", "high", "low", "close",
            ],
            dates,
        )
    )
    raw_price = _deduplicate_daily(
        _read_dates(
            config.path("price_raw"),
            ["stock_code", "date", "vwap", "close", "low", "high"],
            dates,
        )
    )
    trade = _deduplicate_daily(
        _read_dates(
            config.path("trade"),
            [
                "stock_code", "stock_name", "date", "volume", "turn_value",
                "market_value", "negotiable_market_value", "change_pct",
            ],
            dates,
        )
    )
    suspend = _deduplicate_daily(
        _read_dates(config.path("suspend"), ["stock_code", "date", "if_suspend"], dates)
    )
    limit_status = _deduplicate_daily(
        _read_dates(
            config.path("limit"),
            ["stock_code", "date", "stock_board", "limit_board", "surged_limit", "decline_limit"],
            dates,
        )
    )
    # dv 仅允许使用 T 日及之前 5 个交易日内的真实来源记录。
    # 这里多读一个交易日用于计算年龄，不读 PE/PB/PS 也不前填。
    dividend_calendar = load_trade_calendar(
        config.data_root,
        start_date=str((schedule["signal_date"].min() - pd.Timedelta(days=15)).date()),
        end_date=str(schedule["signal_date"].max().date()),
    )
    dividend_dates = (
        schedule[["signal_date"]]
        .drop_duplicates()
        .assign(_join_key=1)
        .merge(dividend_calendar[["date"]].assign(_join_key=1), on="_join_key")
        .loc[lambda frame: frame["date"].le(frame["signal_date"])]
        .sort_values(["signal_date", "date"], ascending=[True, False])
        .groupby("signal_date", sort=False)
        .head(config.dividend_max_age_trading_days + 1)["date"]
        .drop_duplicates()
    )
    value = _deduplicate_daily(
        _read_dates(config.path("value"), ["stock_code", "date", "dv"], dividend_dates)
    )
    return price, raw_price, trade, suspend, limit_status, value


def _adjusted_vwap_panel(
    forward_price: pd.DataFrame,
    raw_price: pd.DataFrame,
) -> pd.DataFrame:
    """把未复权VWAP转换为与前复权OHLC一致的当日价格口径。

    本地 ``adj_factor`` 是累计复权因子，前复权序列另含证券级归一化常数，故
    先由 ``raw_close * adj_factor / forward_close`` 反推出该常数，再计算
    ``forward_vwap = raw_vwap * adj_factor / normalizer``。转换后的原始收盘价
    必须精确重构前复权收盘价；原始VWAP还必须为正、有限且落在当日原始
    low/high 内，否则标记为不可用，不以 close 或后续日期替代。
    """
    forward = forward_price[
        ["stock_code", "date", "adj_factor", "close"]
    ].rename(columns={"close": "forward_close"})
    raw = raw_price.rename(
        columns={"vwap": "raw_vwap", "close": "raw_close", "low": "raw_low", "high": "raw_high"}
    )
    result = forward.merge(raw, on=["stock_code", "date"], how="outer", validate="one_to_one")
    numeric_columns = [
        "adj_factor", "forward_close", "raw_vwap", "raw_close", "raw_low", "raw_high",
    ]
    finite = pd.DataFrame(
        {column: np.isfinite(pd.to_numeric(result[column], errors="coerce")) for column in numeric_columns}
    ).all(axis=1)
    positive_scale = (
        result["adj_factor"].gt(0)
        & result["forward_close"].gt(0)
        & result["raw_close"].gt(0)
    )
    result["forward_adjustment_normalizer"] = (
        result["raw_close"] * result["adj_factor"] / result["forward_close"]
    ).where(finite & positive_scale)
    result["forward_vwap"] = (
        result["raw_vwap"]
        * result["adj_factor"]
        / result["forward_adjustment_normalizer"]
    )
    result["converted_close"] = (
        result["raw_close"]
        * result["adj_factor"]
        / result["forward_adjustment_normalizer"]
    )
    result["close_scale_sanity"] = np.isclose(
        result["converted_close"], result["forward_close"], rtol=1.0e-12, atol=1.0e-12,
        equal_nan=False,
    )
    result["raw_vwap_unit_sanity"] = (
        result["raw_vwap"].gt(0)
        & result["raw_vwap"].ge(result["raw_low"])
        & result["raw_vwap"].le(result["raw_high"])
    )
    result["forward_vwap_valid"] = (
        finite
        & positive_scale
        & result["forward_vwap"].gt(0)
        & np.isfinite(result["forward_vwap"])
        & result["close_scale_sanity"]
        & result["raw_vwap_unit_sanity"]
    )
    return result.sort_values(["date", "stock_code"]).reset_index(drop=True)


def _daily_slice(
    frame: pd.DataFrame,
    schedule: pd.DataFrame,
    date_role: str,
    prefixes: dict[str, str],
) -> pd.DataFrame:
    date_column = f"{date_role}_date"
    sliced = schedule.drop_duplicates("signal_date").merge(
        frame,
        left_on=date_column,
        right_on="date",
        how="left",
    ).drop(columns="date")
    return sliced.rename(columns=prefixes)


def _active_st_flags(keys: pd.DataFrame, st: pd.DataFrame) -> pd.Series:
    """向量化判断信号日是否落在任一 ST 半开区间。"""
    if keys.empty or st.empty:
        return pd.Series(False, index=keys.index, dtype=bool)
    intervals = st.copy()
    intervals["stock_code"] = intervals["stock_code"].astype(str)
    intervals["implement_date"] = pd.to_datetime(
        intervals["implement_date"], errors="coerce"
    ).dt.normalize()
    intervals["remove_date"] = pd.to_datetime(
        intervals["remove_date"], errors="coerce"
    ).dt.normalize()
    left = keys[["stock_code", "signal_date"]].assign(_row_id=keys.index)
    joined = left.merge(intervals, on="stock_code", how="left")
    joined["_active"] = joined["implement_date"].le(joined["signal_date"]) & (
        joined["remove_date"].gt(joined["signal_date"]) | joined["remove_date"].isna()
    )
    return (
        joined.groupby("_row_id", sort=False)["_active"]
        .any()
        .reindex(keys.index, fill_value=False)
        .astype(bool)
    )


def _first_observed_dates(
    config: AllAStyleBoxConfig,
    stock_codes: pd.Index,
    upper_date: pd.Timestamp,
) -> pd.Series:
    """为不在当前主表的历史证券取首个真实行情/成交日，避免最终状态回溯。"""
    codes = stock_codes.astype(str).drop_duplicates().tolist()
    if not codes:
        return pd.Series(dtype="datetime64[ns]", name="first_observed_date")
    filters = [("stock_code", "in", codes), ("date", "<=", upper_date)]
    price = pd.read_parquet(
        config.path("price_forward"), columns=["stock_code", "date"], filters=filters
    )
    trade = pd.read_parquet(config.path("trade"), columns=["stock_code", "date"], filters=filters)
    observed = pd.concat([price, trade], ignore_index=True)
    observed["stock_code"] = observed["stock_code"].astype(str)
    observed["date"] = pd.to_datetime(observed["date"]).dt.normalize()
    return observed.groupby("stock_code")["date"].min().rename("first_observed_date")


def _listing_age(
    listing_dates: pd.Series,
    signal_dates: pd.Series,
    trading_days: pd.DatetimeIndex,
) -> pd.Series:
    valid = listing_dates.notna() & signal_dates.notna()
    result = pd.Series(pd.NA, index=listing_dates.index, dtype="Int64")
    if valid.any():
        starts = trading_days.searchsorted(pd.DatetimeIndex(listing_dates.loc[valid]), side="left")
        ends = trading_days.searchsorted(pd.DatetimeIndex(signal_dates.loc[valid]), side="right")
        result.loc[valid] = ends - starts
    return result


def _reason_column(frame: pd.DataFrame, definitions: tuple[tuple[str, str], ...]) -> pd.Series:
    reasons = pd.Series("", index=frame.index, dtype="string")
    for column, label in definitions:
        mask = frame[column].fillna(False).astype(bool)
        reasons.loc[mask] = reasons.loc[mask] + np.where(reasons.loc[mask].eq(""), "", "|") + label
    return reasons


def _prepare_income_vintages(
    config: AllAStyleBoxConfig,
    stock_codes: pd.Index,
    upper_date: pd.Timestamp,
) -> pd.DataFrame:
    """读取利润表披露版本；同日优先合并、完整、调整后口径。"""
    codes = stock_codes.astype(str).drop_duplicates().tolist()
    columns = [
        "stock_code", "end_date", "info_publ_date", "if_merged", "if_adjusted",
        "if_complete", "total_operating_revenue", "net_profit",
    ]
    if not codes:
        return pd.DataFrame(columns=columns)
    raw = pd.read_parquet(
        config.path("income"),
        columns=columns,
        filters=[("stock_code", "in", codes), ("info_publ_date", "<=", upper_date)],
    )
    raw["stock_code"] = raw["stock_code"].astype(str)
    for column in ("end_date", "info_publ_date"):
        raw[column] = pd.to_datetime(raw[column], errors="coerce").dt.normalize()
    raw = raw.dropna(subset=["end_date", "info_publ_date"])
    raw["_merged_priority"] = raw["if_merged"].ne(config.financial_merged_flag)
    raw["_complete_priority"] = raw["if_complete"].ne(config.financial_complete_flag)
    raw["_adjusted_priority"] = raw["if_adjusted"].ne(config.financial_adjusted_flag)
    return (
        raw.sort_values(
            [
                "stock_code", "end_date", "info_publ_date", "_merged_priority",
                "_complete_priority", "_adjusted_priority",
            ]
        )
        .drop_duplicates(["stock_code", "end_date", "info_publ_date"], keep="first")
        .drop(columns=["_merged_priority", "_complete_priority", "_adjusted_priority"])
        .reset_index(drop=True)
    )


def _prepare_balance_vintages(
    config: AllAStyleBoxConfig,
    stock_codes: pd.Index,
    upper_date: pd.Timestamp,
) -> pd.DataFrame:
    """读取资产负债表披露版本；选版优先级与利润表一致。"""
    codes = stock_codes.astype(str).drop_duplicates().tolist()
    columns = [
        "stock_code", "end_date", "info_publ_date", "if_merged", "if_adjusted",
        "if_complete", "total_shareholder_equity",
    ]
    if not codes:
        return pd.DataFrame(columns=columns)
    raw = pd.read_parquet(
        config.path("balance"),
        columns=columns,
        filters=[("stock_code", "in", codes), ("info_publ_date", "<=", upper_date)],
    )
    raw["stock_code"] = raw["stock_code"].astype(str)
    for column in ("end_date", "info_publ_date"):
        raw[column] = pd.to_datetime(raw[column], errors="coerce").dt.normalize()
    raw = raw.dropna(subset=["end_date", "info_publ_date"])
    raw["_merged_priority"] = raw["if_merged"].ne(config.financial_merged_flag)
    raw["_complete_priority"] = raw["if_complete"].ne(config.financial_complete_flag)
    raw["_adjusted_priority"] = raw["if_adjusted"].ne(config.financial_adjusted_flag)
    return (
        raw.sort_values(
            [
                "stock_code", "end_date", "info_publ_date", "_merged_priority",
                "_complete_priority", "_adjusted_priority",
            ]
        )
        .drop_duplicates(["stock_code", "end_date", "info_publ_date"], keep="first")
        .drop(columns=["_merged_priority", "_complete_priority", "_adjusted_priority"])
        .reset_index(drop=True)
    )


def _latest_available_periods(vintages: pd.DataFrame) -> pd.DataFrame:
    """形成“某披露日起可用的最新财政期”事件表。"""
    if vintages.empty:
        return pd.DataFrame(columns=["stock_code", "period_available_date", "financial_end_date"])
    periods = (
        vintages.groupby(["stock_code", "end_date"], as_index=False)["info_publ_date"]
        .min()
        .rename(columns={"info_publ_date": "period_available_date"})
        .sort_values(["stock_code", "period_available_date", "end_date"])
    )
    periods["financial_end_date"] = periods.groupby("stock_code")["end_date"].cummax()
    return (
        periods.sort_values(["period_available_date", "financial_end_date", "stock_code"])
        .drop_duplicates(["stock_code", "period_available_date"], keep="last")
        .drop_duplicates(["stock_code", "financial_end_date"], keep="first")
        [["stock_code", "period_available_date", "financial_end_date"]]
        .sort_values(["period_available_date", "stock_code"])
        .reset_index(drop=True)
    )


def _merge_statement_vintage(
    left: pd.DataFrame,
    vintages: pd.DataFrame,
    *,
    end_column: str,
    prefix: str,
    value_columns: tuple[str, ...],
) -> pd.DataFrame:
    """对指定财政期按披露日 backward as-of 取 T 日可见版本。

    回写只通过不可变 ``_row_id`` 一对一 merge，绝不把 ``_row_id`` 当作当前
    DataFrame 的位置索引。
    """
    valid = left[end_column].notna()
    base = left.copy()
    output_columns = {"info_publ_date": f"{prefix}_info_publ_date"}
    output_columns.update({column: f"{prefix}_{column}" for column in value_columns})
    for output in output_columns.values():
        base[output] = pd.NaT if output.endswith("date") else np.nan
    if not valid.any() or vintages.empty:
        return base
    query = base.loc[valid, ["_row_id", "stock_code", "signal_date", end_column]].copy()
    query = query.sort_values(["signal_date", "stock_code", end_column])
    right = vintages.rename(columns={"end_date": end_column}).sort_values(
        ["info_publ_date", "stock_code", end_column]
    )
    joined = pd.merge_asof(
        query,
        right[
            [
                "stock_code", end_column, "info_publ_date", *value_columns,
            ]
        ],
        left_on="signal_date",
        right_on="info_publ_date",
        by=["stock_code", end_column],
        direction="backward",
        allow_exact_matches=True,
    ).rename(columns=output_columns)
    publ_column = output_columns["info_publ_date"]
    if (joined[publ_column].dropna() > joined.loc[joined[publ_column].notna(), "signal_date"]).any():
        raise AssertionError(f"{prefix} 财务版本披露日晚于信号日")
    updates = joined[["_row_id", *output_columns.values()]]
    base = base.drop(columns=list(output_columns.values()))
    return (
        base.merge(updates, on="_row_id", how="left", validate="one_to_one")
        .sort_values("_row_id")
        .reset_index(drop=True)
    )


def _merge_financial_vintage(
    left: pd.DataFrame,
    vintages: pd.DataFrame,
    *,
    end_column: str,
    prefix: str,
) -> pd.DataFrame:
    """兼容入口：回写利润表累计营收与净利润。"""
    return _merge_statement_vintage(
        left,
        vintages,
        end_column=end_column,
        prefix=prefix,
        value_columns=("total_operating_revenue", "net_profit"),
    )


def _build_pit_snapshot_from_vintages(
    keys: pd.DataFrame,
    vintages: pd.DataFrame,
) -> pd.DataFrame:
    """使用已标准化披露版本构造PIT快照，供真实数据与合成回归共用。"""
    output = (
        keys[KEYS]
        .drop_duplicates()
        .reset_index(drop=True)
        .assign(_row_id=lambda frame: frame.index)
    )
    if output.empty:
        return output.drop(columns="_row_id")
    periods = _latest_available_periods(vintages)
    if periods.empty:
        output["period_available_date"] = pd.NaT
        output["financial_end_date"] = pd.NaT
    else:
        query = output[["_row_id", "stock_code", "signal_date"]].sort_values(
            ["signal_date", "stock_code"]
        )
        selected = pd.merge_asof(
            query,
            periods.sort_values(["period_available_date", "stock_code"]),
            left_on="signal_date",
            right_on="period_available_date",
            by="stock_code",
            direction="backward",
            allow_exact_matches=True,
        )
        if (selected["period_available_date"].dropna() > selected.loc[selected["period_available_date"].notna(), "signal_date"]).any():
            raise AssertionError("财政期首次可得日晚于信号日")
        period_updates = selected[
            ["_row_id", "period_available_date", "financial_end_date"]
        ]
        output = (
            output.merge(period_updates, on="_row_id", how="left", validate="one_to_one")
            .sort_values("_row_id")
            .reset_index(drop=True)
        )
    output = _merge_financial_vintage(
        output, vintages, end_column="financial_end_date", prefix="current"
    )
    output["prior_financial_end_date"] = output["financial_end_date"] - pd.DateOffset(years=1)
    output = _merge_financial_vintage(
        output, vintages, end_column="prior_financial_end_date", prefix="prior"
    )
    years = pd.to_datetime(output["financial_end_date"], errors="coerce").dt.year - 1
    output["prior_fy_financial_end_date"] = pd.to_datetime(
        years.astype("Int64").astype("string") + "-12-31", errors="coerce"
    )
    output = _merge_financial_vintage(
        output, vintages, end_column="prior_fy_financial_end_date", prefix="prior_fy"
    )

    annual = (
        output["financial_end_date"].dt.month.eq(12)
        & output["financial_end_date"].dt.day.eq(31)
    )
    for source, output_column in (
        ("total_operating_revenue", "ttm_revenue"),
        ("net_profit", "ttm_net_profit"),
    ):
        current = pd.to_numeric(output[f"current_{source}"], errors="coerce")
        prior = pd.to_numeric(output[f"prior_{source}"], errors="coerce")
        prior_fy = pd.to_numeric(output[f"prior_fy_{source}"], errors="coerce")
        reconstructed = current + prior_fy - prior
        output[output_column] = current.where(annual, reconstructed.where(
            current.notna() & prior.notna() & prior_fy.notna()
        ))
        output[f"{output_column}_formula"] = np.where(
            annual,
            "annual_current",
            "current_ytd+prior_fy-prior_ytd",
        )

    def symmetric(current: pd.Series, previous: pd.Series) -> pd.Series:
        current_num = pd.to_numeric(current, errors="coerce")
        previous_num = pd.to_numeric(previous, errors="coerce")
        denominator = current_num.abs() + previous_num.abs() + np.finfo(np.float64).eps
        return (2.0 * (current_num - previous_num) / denominator).where(
            current_num.notna() & previous_num.notna()
        )

    output["revenue_growth_symmetric"] = symmetric(
        output["current_total_operating_revenue"], output["prior_total_operating_revenue"]
    )
    output["net_profit_growth_symmetric"] = symmetric(
        output["current_net_profit"], output["prior_net_profit"]
    )
    output["financial_current_available"] = output["current_info_publ_date"].notna()
    output["revenue_yoy_available"] = output["revenue_growth_symmetric"].notna()
    output["net_profit_yoy_available"] = output["net_profit_growth_symmetric"].notna()
    return output.sort_values("_row_id").drop(columns="_row_id").reset_index(drop=True)


def _build_pit_balance_snapshot_from_vintages(
    keys: pd.DataFrame,
    vintages: pd.DataFrame,
) -> pd.DataFrame:
    """按 T 日可见最新财政期取正股东权益，不使用最终版本。"""
    output = (
        keys[KEYS].drop_duplicates().reset_index(drop=True).assign(
            _row_id=lambda frame: frame.index
        )
    )
    periods = _latest_available_periods(vintages)
    if output.empty:
        return output.drop(columns="_row_id")
    if periods.empty:
        output["balance_period_available_date"] = pd.NaT
        output["balance_end_date"] = pd.NaT
    else:
        query = output[["_row_id", "stock_code", "signal_date"]].sort_values(
            ["signal_date", "stock_code"]
        )
        selected = pd.merge_asof(
            query,
            periods.sort_values(["period_available_date", "stock_code"]),
            left_on="signal_date",
            right_on="period_available_date",
            by="stock_code",
            direction="backward",
            allow_exact_matches=True,
        ).rename(
            columns={
                "period_available_date": "balance_period_available_date",
                "financial_end_date": "balance_end_date",
            }
        )
        output = output.merge(
            selected[["_row_id", "balance_period_available_date", "balance_end_date"]],
            on="_row_id",
            how="left",
            validate="one_to_one",
        ).sort_values("_row_id")
    output = _merge_statement_vintage(
        output,
        vintages,
        end_column="balance_end_date",
        prefix="balance",
        value_columns=("total_shareholder_equity",),
    )
    return output.sort_values("_row_id").drop(columns="_row_id").reset_index(drop=True)


def build_pit_financial_snapshot(
    keys: pd.DataFrame,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """按披露日选择最新财政期与同财政期上年同期，计算对称同比原料。

    选择顺序严格为：先 ``info_publ_date <= T``，再取当时可用的最大
    ``end_date``；上年同期只由已选财政期减一年得到，绝不把 ``end_date`` 当
    可得日，也不进行 bfill。
    """
    output = keys[KEYS].drop_duplicates().reset_index(drop=True)
    if output.empty:
        return output
    income_vintages = _prepare_income_vintages(
        config, pd.Index(output["stock_code"].unique()), output["signal_date"].max()
    )
    balance_vintages = _prepare_balance_vintages(
        config, pd.Index(output["stock_code"].unique()), output["signal_date"].max()
    )
    income = _build_pit_snapshot_from_vintages(output, income_vintages)
    balance = _build_pit_balance_snapshot_from_vintages(output, balance_vintages)
    return income.merge(balance, on=KEYS, how="left", validate="one_to_one")


def _attach_valuation_inputs(
    panel: pd.DataFrame,
    value: pd.DataFrame,
    trading_days: pd.DatetimeIndex,
    config: AllAStyleBoxConfig,
) -> pd.DataFrame:
    """用 PIT 财报重建 B/P、E/P、S/P，dv 只允许 5 个交易日内的旧值。"""
    left = panel.sort_values(["signal_date", "stock_code"], kind="mergesort").copy()
    valuation = value.rename(columns={"date": "dividend_source_date"}).copy()
    valuation["stock_code"] = valuation["stock_code"].astype(str).str.zfill(6)
    valuation = valuation.sort_values(["dividend_source_date", "stock_code"])
    if valuation.empty:
        result = left.copy()
        result["dividend_source_date"] = pd.NaT
        result["dv"] = np.nan
    else:
        result = pd.merge_asof(
            left.sort_values(["signal_date", "stock_code"]),
            valuation[["stock_code", "dividend_source_date", "dv"]],
            left_on="signal_date",
            right_on="dividend_source_date",
            by="stock_code",
            direction="backward",
            allow_exact_matches=True,
        )
    source_position = trading_days.searchsorted(
        pd.DatetimeIndex(result["dividend_source_date"].fillna(trading_days[0])), side="left"
    )
    signal_position = trading_days.searchsorted(
        pd.DatetimeIndex(result["signal_date"]), side="left"
    )
    result["dividend_age_trading_days"] = pd.Series(
        signal_position - source_position, index=result.index, dtype="Int64"
    ).where(result["dividend_source_date"].notna())
    result["dividend_is_fresh"] = (
        result["dividend_source_date"].notna()
        & result["dividend_source_date"].le(result["signal_date"])
        & result["dividend_age_trading_days"].between(
            0, config.dividend_max_age_trading_days
        )
    )
    result["dividend_yield"] = pd.to_numeric(result["dv"], errors="coerce").where(
        result["dividend_is_fresh"] & pd.to_numeric(result["dv"], errors="coerce").ge(0)
    )
    market_value = pd.to_numeric(result["market_value"], errors="coerce")
    equity = pd.to_numeric(result["balance_total_shareholder_equity"], errors="coerce")
    ttm_profit = pd.to_numeric(result["ttm_net_profit"], errors="coerce")
    ttm_revenue = pd.to_numeric(result["ttm_revenue"], errors="coerce")
    result["book_to_price"] = (equity / market_value).where(
        equity.gt(0) & market_value.gt(0)
    )
    result["earnings_to_price"] = (ttm_profit / market_value).where(
        ttm_profit.gt(0) & market_value.gt(0)
    )
    result["sales_to_price"] = (ttm_revenue / market_value).where(
        ttm_revenue.gt(0) & market_value.gt(0)
    )
    result["book_to_price_source_date"] = result["balance_info_publ_date"]
    income_source_columns = [
        "current_info_publ_date", "prior_info_publ_date", "prior_fy_info_publ_date"
    ]
    result["ttm_income_source_date"] = result[income_source_columns].max(axis=1)
    result["earnings_to_price_source_date"] = result["ttm_income_source_date"]
    result["sales_to_price_source_date"] = result["ttm_income_source_date"]
    result["value_core_component_count"] = result[
        ["book_to_price", "earnings_to_price", "sales_to_price"]
    ].notna().sum(axis=1)
    result["valuation_component_count"] = result[
        ["book_to_price", "earnings_to_price", "sales_to_price", "dividend_yield"]
    ].notna().sum(axis=1)
    return result.sort_values(KEYS, kind="mergesort").reset_index(drop=True)


def _source_catalog(
    config: AllAStyleBoxConfig,
    loaded: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    roles = {
        "stock_master": "list_date与当前状态仅审计；当前list_state不参与历史筛选",
        "calendar": "月末T、下一交易日T+1、下一持有月收益端点",
        "price_raw": "T+1与收益端点未复权VWAP及同日OHLC单位核对",
        "price_forward": "当日adj_factor与前复权OHLC；用于把原始VWAP转换到同一复权口径",
        "trade": "成交量、成交额、总市值、流通市值",
        "value": "仅作为fresh<=5交易日dv可选来源，PE/PB/PS不参与",
        "balance": "info_publ_date<=T后取当时可得最新期正股东权益构造B/P",
        "income": "info_publ_date<=T；年报直取，非年报用当期累计+上年年报-上年同期重建TTM",
        "st": "T日[implement_date,remove_date)区间过滤",
        "suspend": "T过滤与T+1方向性可交易约束",
        "limit": "T过滤与T+1涨停禁买/跌停禁卖",
    }
    records: list[dict[str, object]] = []
    root = config.data_root.resolve()
    for key, role in roles.items():
        frame = loaded.get(key, pd.DataFrame())
        resolved_path = config.path(key).resolve()
        date_columns = [c for c in ("date", "signal_date", "info_publ_date") if c in frame]
        source_dates = pd.to_datetime(frame[date_columns[0]], errors="coerce") if date_columns else pd.Series(dtype="datetime64[ns]")
        records.append(
            {
                "source_key": key,
                "file_name": config.files[key],
                "resolved_path": str(resolved_path),
                "loaded_rows": len(frame),
                "loaded_date_min": source_dates.min() if not source_dates.empty else pd.NaT,
                "loaded_date_max": source_dates.max() if not source_dates.empty else pd.NaT,
                "role_and_pit_rule": role,
                "uses_index_components": "index_components" in resolved_path.name.lower(),
                "external_vendor_used": not resolved_path.is_relative_to(root),
            }
        )
    return pd.DataFrame(records)


def _build_exclusion_audit(panel: pd.DataFrame) -> pd.DataFrame:
    flags = [
        "unsupported_exchange", "exchange_not_active", "possible_code_transition_duplicate",
        "listing_age_unavailable", "listing_age_too_short",
        "missing_signal_price", "missing_signal_trade", "nonpositive_market_value",
        "signal_no_volume", "signal_is_st", "signal_is_suspended",
        "signal_is_limit_up", "signal_is_limit_down",
    ]
    summary = (
        panel.groupby(["signal_date", "holding_month", "sample_phase"], as_index=False)
        .agg(candidate_count=("stock_code", "size"), eligible_count=("is_eligible", "sum"))
    )
    counts = (
        panel.melt(
            id_vars=["signal_date", "holding_month", "sample_phase"],
            value_vars=flags,
            var_name="exclusion_flag",
            value_name="excluded",
        )
        .loc[lambda x: x["excluded"]]
        .groupby(["signal_date", "holding_month", "sample_phase", "exclusion_flag"], as_index=False)
        .size()
        .rename(columns={"size": "excluded_count"})
    )
    return counts.merge(summary, on=["signal_date", "holding_month", "sample_phase"], how="right")


def build_availability_audit(panel: pd.DataFrame) -> pd.DataFrame:
    """按月统计 m2 必需原料覆盖率；仅以 m1 合格池为分母。"""
    fields = {
        "market_value": "总市值",
        "negotiable_market_value": "流通市值",
        "book_to_price": "B/P",
        "earnings_to_price": "E/P",
        "sales_to_price": "S/P",
        "dividend_yield": "股息率",
        "current_total_operating_revenue": "当期营收",
        "prior_total_operating_revenue": "上年同期营收",
        "current_net_profit": "当期净利润",
        "prior_net_profit": "上年同期净利润",
        "revenue_growth_symmetric": "营收同比对称增长",
        "net_profit_growth_symmetric": "净利润同比对称增长",
        "execution_vwap": "T+1前复权VWAP",
        "return_vwap": "收益端点前复权VWAP",
        "gross_holding_return": "个股持有期毛收益",
    }
    eligible = panel.loc[panel["is_eligible"], ["signal_date", "holding_month", *fields]].copy()
    if eligible.empty:
        return pd.DataFrame(
            columns=["signal_date", "holding_month", "field", "field_cn", "available_count", "eligible_count", "coverage_rate"]
        )
    present = eligible[list(fields)].notna()
    present = pd.concat([eligible[["signal_date", "holding_month"]], present], axis=1)
    long = present.melt(
        id_vars=["signal_date", "holding_month"],
        var_name="field",
        value_name="available",
    )
    audit = (
        long.groupby(["signal_date", "holding_month", "field"], as_index=False)
        .agg(available_count=("available", "sum"), eligible_count=("available", "size"))
    )
    audit["field_cn"] = audit["field"].map(fields)
    audit["coverage_rate"] = audit["available_count"] / audit["eligible_count"]
    audit["missing_policy"] = "no_bfill"
    return audit[
        ["signal_date", "holding_month", "field", "field_cn", "available_count", "eligible_count", "coverage_rate", "missing_policy"]
    ]


def _build_exchange_code_audit(panel: pd.DataFrame) -> pd.DataFrame:
    """输出逐信号日原始代码号段、生效状态和疑似代码沿革重复审计。"""
    return (
        panel.groupby(
            [
                "signal_date", "holding_month", "code_prefix", "exchange", "board",
                "bse_effective_date", "code_mapping_applied",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            candidate_rows=("stock_code", "size"),
            unique_stock_codes=("stock_code", "nunique"),
            eligible_rows=("is_eligible", "sum"),
            possible_transition_duplicates=("possible_code_transition_duplicate", "sum"),
        )
        .sort_values(["signal_date", "code_prefix"])
        .reset_index(drop=True)
    )


def build_dynamic_all_a_panel(
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
    *,
    smoke_months: int | None = None,
    smoke_stock_limit: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """构造动态全 A 月末池、T+1标记与 PIT 原料面板。"""
    schedule = load_rebalance_schedule(config, smoke_months=smoke_months)
    price, raw_price, trade, suspend, limit_status, value = _load_market_slices(config, schedule)
    adjusted_vwap = _adjusted_vwap_panel(price, raw_price)

    signals = schedule[["signal_date", "execution_date", "return_date", "holding_month", "sample_phase", "signal_within_freeze_period"]]
    signal_price = _daily_slice(
        price,
        signals,
        "signal",
        {
            "stock_name": "price_stock_name", "prev_close": "signal_prev_close",
            "open": "signal_open", "high": "signal_high", "low": "signal_low",
            "close": "signal_close",
        },
    )
    signal_trade = _daily_slice(
        trade,
        signals,
        "signal",
        {
            "stock_name": "trade_stock_name", "volume": "signal_volume",
            "turn_value": "signal_turn_value", "change_pct": "signal_change_pct",
        },
    )
    panel = signal_price.merge(
        signal_trade,
        on=["signal_date", "execution_date", "return_date", "holding_month", "sample_phase", "signal_within_freeze_period", "stock_code"],
        how="outer",
        validate="one_to_one",
    )
    panel["stock_code"] = panel["stock_code"].astype(str).str.zfill(6)
    if smoke_stock_limit is not None:
        codes = sorted(panel["stock_code"].unique())[:smoke_stock_limit]
        panel = panel.loc[panel["stock_code"].isin(codes)].copy()

    exchange = classify_exchange(
        panel["stock_code"], panel["signal_date"], config
    ).drop(columns="stock_code")
    panel = pd.concat([panel.reset_index(drop=True), exchange.reset_index(drop=True)], axis=1)
    panel["stock_name"] = panel["price_stock_name"].combine_first(panel["trade_stock_name"])

    master = pd.read_parquet(
        config.path("stock_master"),
        columns=["stock_code", "stock_name", "list_date", "list_state"],
    )
    master["stock_code"] = master["stock_code"].astype(str).str.zfill(6)
    master["list_date"] = pd.to_datetime(master["list_date"], errors="coerce").dt.normalize()
    master = master.drop_duplicates("stock_code", keep="last").rename(
        columns={"stock_name": "master_stock_name", "list_state": "current_list_state_audit"}
    )
    panel = panel.merge(master, on="stock_code", how="left", validate="many_to_one")
    panel["stock_name"] = panel["stock_name"].combine_first(panel["master_stock_name"])
    # stock_name 在本地表中存在静态回填，不得作为历史 ST/退市事件。
    # 风险退出只由 portfolio 中带公告日与生效日的显式映射驱动。
    panel["delisting_board_flag"] = False
    name_code_count = panel.groupby(["signal_date", "stock_name"], dropna=False)[
        "stock_code"
    ].transform("nunique")
    panel["possible_code_transition_duplicate"] = (
        panel["is_bse_code_prefix"] & panel["stock_name"].notna() & name_code_count.gt(1)
    )
    missing_master_codes = pd.Index(panel.loc[panel["list_date"].isna(), "stock_code"].unique())
    first_observed = _first_observed_dates(config, missing_master_codes, panel["signal_date"].max())
    panel["first_observed_date"] = panel["stock_code"].map(first_observed)
    panel["listing_reference_date"] = panel["list_date"].combine_first(panel["first_observed_date"])
    panel["listing_date_source"] = np.select(
        [panel["list_date"].notna(), panel["first_observed_date"].notna()],
        ["stock_master.list_date", "first_observed_market_record"],
        default="unavailable",
    )
    full_calendar = load_trade_calendar(
        config.data_root, start_date="2000-01-01", end_date=config.history_end
    )
    trading_days = pd.DatetimeIndex(full_calendar["date"].drop_duplicates().sort_values())
    panel["listing_age_trading_days"] = _listing_age(
        panel["listing_reference_date"], panel["signal_date"], trading_days
    )

    signal_status = signals[["signal_date"]].drop_duplicates().merge(
        suspend.rename(columns={"date": "signal_date"}), on="signal_date", how="left"
    )[["signal_date", "stock_code", "if_suspend"]]
    signal_limit = signals[["signal_date"]].drop_duplicates().merge(
        limit_status.rename(columns={"date": "signal_date"}), on="signal_date", how="left"
    )[["signal_date", "stock_code", "surged_limit", "decline_limit"]]
    panel = panel.merge(signal_status, on=KEYS, how="left", validate="one_to_one")
    panel = panel.merge(signal_limit, on=KEYS, how="left", validate="one_to_one")
    st = pd.read_parquet(
        config.path("st"),
        columns=["stock_code", "implement_date", "remove_date"],
        filters=[("stock_code", "in", panel["stock_code"].unique().tolist())],
    )
    panel["signal_is_st"] = _active_st_flags(panel, st)
    panel["signal_is_suspended"] = panel["if_suspend"].fillna(0).eq(1)
    panel["signal_is_limit_up"] = panel["surged_limit"].fillna(0).eq(1)
    panel["signal_is_limit_down"] = panel["decline_limit"].fillna(0).eq(1)
    panel["unsupported_exchange"] = panel["exchange"].eq("UNKNOWN")
    panel["exchange_not_active"] = ~panel["exchange_active_on_signal"]
    panel["listing_age_unavailable"] = panel["listing_age_trading_days"].isna()
    panel["listing_age_too_short"] = panel["listing_age_trading_days"].lt(
        config.minimum_listing_trading_days
    ).fillna(False)
    panel["missing_signal_price"] = panel["signal_close"].isna() | panel["signal_close"].le(0)
    panel["missing_signal_trade"] = panel["signal_volume"].isna()
    panel["nonpositive_market_value"] = panel["market_value"].isna() | panel["market_value"].le(0)
    panel["signal_no_volume"] = (
        panel["signal_volume"].fillna(0).le(0) | panel["signal_turn_value"].fillna(0).le(0)
    )
    exclusion_flags = [
        "unsupported_exchange", "exchange_not_active", "possible_code_transition_duplicate",
        "listing_age_unavailable", "listing_age_too_short",
        "missing_signal_price", "missing_signal_trade", "nonpositive_market_value",
        "signal_no_volume", "signal_is_st", "signal_is_suspended",
        "signal_is_limit_up", "signal_is_limit_down",
    ]
    panel["is_eligible"] = ~panel[exclusion_flags].any(axis=1)
    panel["exclusion_reason"] = _reason_column(
        panel,
        tuple((column, column) for column in exclusion_flags),
    ).mask(panel["is_eligible"], "eligible")

    execution_price = _daily_slice(
        adjusted_vwap,
        signals,
        "execution",
        {
            "forward_vwap": "execution_vwap",
            "forward_vwap_valid": "execution_vwap_valid",
            "forward_close": "execution_forward_close",
            "raw_vwap": "execution_raw_vwap",
            "raw_close": "execution_raw_close",
            "adj_factor": "execution_adj_factor",
            "forward_adjustment_normalizer": "execution_adjustment_normalizer",
            "close_scale_sanity": "execution_close_scale_sanity",
            "raw_vwap_unit_sanity": "execution_vwap_unit_sanity",
        },
    )[
        [
            "signal_date", "stock_code", "execution_vwap", "execution_vwap_valid",
            "execution_forward_close", "execution_raw_vwap", "execution_raw_close",
            "execution_adj_factor", "execution_adjustment_normalizer",
            "execution_close_scale_sanity", "execution_vwap_unit_sanity",
        ]
    ]
    execution_trade = _daily_slice(
        trade,
        signals,
        "execution",
        {"volume": "execution_volume", "turn_value": "execution_turn_value"},
    )[["signal_date", "stock_code", "execution_volume", "execution_turn_value"]]
    execution_suspend = signals[["signal_date", "execution_date"]].merge(
        suspend, left_on="execution_date", right_on="date", how="left"
    )[["signal_date", "stock_code", "if_suspend"]].rename(
        columns={"if_suspend": "execution_if_suspend"}
    )
    execution_limit = signals[["signal_date", "execution_date"]].merge(
        limit_status, left_on="execution_date", right_on="date", how="left"
    )[["signal_date", "stock_code", "surged_limit", "decline_limit"]].rename(
        columns={"surged_limit": "execution_limit_up", "decline_limit": "execution_limit_down"}
    )
    for frame in (execution_price, execution_trade, execution_suspend, execution_limit):
        panel = panel.merge(frame, on=KEYS, how="left", validate="one_to_one")
    panel["execution_is_suspended"] = panel["execution_if_suspend"].fillna(0).eq(1)
    panel["execution_is_limit_up"] = panel["execution_limit_up"].fillna(0).eq(1)
    panel["execution_is_limit_down"] = panel["execution_limit_down"].fillna(0).eq(1)
    panel["execution_no_volume"] = (
        panel["execution_volume"].fillna(0).le(0)
        | panel["execution_turn_value"].fillna(0).le(0)
    )
    panel["execution_base_tradable"] = (
        panel["execution_vwap_valid"].fillna(False)
        & ~panel["execution_no_volume"]
        & ~panel["execution_is_suspended"]
    )
    panel["can_buy_t1"] = panel["execution_base_tradable"] & ~panel["execution_is_limit_up"]
    panel["can_sell_t1"] = panel["execution_base_tradable"] & ~panel["execution_is_limit_down"]

    return_price = _daily_slice(
        adjusted_vwap,
        signals,
        "return",
        {
            "forward_vwap": "return_vwap",
            "forward_vwap_valid": "return_vwap_valid",
            "forward_close": "return_forward_close",
            "raw_vwap": "return_raw_vwap",
            "raw_close": "return_raw_close",
            "adj_factor": "return_adj_factor",
            "forward_adjustment_normalizer": "return_adjustment_normalizer",
            "close_scale_sanity": "return_close_scale_sanity",
            "raw_vwap_unit_sanity": "return_vwap_unit_sanity",
        },
    )[
        [
            "signal_date", "stock_code", "return_vwap", "return_vwap_valid",
            "return_forward_close", "return_raw_vwap", "return_raw_close",
            "return_adj_factor", "return_adjustment_normalizer",
            "return_close_scale_sanity", "return_vwap_unit_sanity",
        ]
    ]
    return_trade = _daily_slice(
        trade,
        signals,
        "return",
        {"volume": "return_volume", "turn_value": "return_turn_value"},
    )[["signal_date", "stock_code", "return_volume", "return_turn_value"]]
    return_suspend = signals[["signal_date", "return_date"]].merge(
        suspend, left_on="return_date", right_on="date", how="left"
    )[["signal_date", "stock_code", "if_suspend"]].rename(
        columns={"if_suspend": "return_if_suspend"}
    )
    return_limit = signals[["signal_date", "return_date"]].merge(
        limit_status, left_on="return_date", right_on="date", how="left"
    )[["signal_date", "stock_code", "surged_limit", "decline_limit"]].rename(
        columns={"surged_limit": "return_limit_up", "decline_limit": "return_limit_down"}
    )
    for frame in (return_price, return_trade, return_suspend, return_limit):
        panel = panel.merge(frame, on=KEYS, how="left", validate="one_to_one")
    panel["return_is_suspended"] = panel["return_if_suspend"].fillna(0).eq(1)
    panel["return_is_limit_up"] = panel["return_limit_up"].fillna(0).eq(1)
    panel["return_is_limit_down"] = panel["return_limit_down"].fillna(0).eq(1)
    panel["return_no_volume"] = (
        panel["return_volume"].fillna(0).le(0) | panel["return_turn_value"].fillna(0).le(0)
    )
    panel["return_base_tradable"] = (
        panel["return_vwap_valid"].fillna(False)
        & ~panel["return_no_volume"]
        & ~panel["return_is_suspended"]
    )
    panel["can_sell_at_return"] = panel["return_base_tradable"] & ~panel["return_is_limit_down"]
    endpoint_valid = (
        panel["execution_vwap_valid"].fillna(False)
        & panel["return_vwap_valid"].fillna(False)
    )
    panel["gross_holding_return"] = (
        panel["return_vwap"] / panel["execution_vwap"] - 1.0
    ).where(endpoint_valid)
    panel["gross_holding_return_executable"] = panel["gross_holding_return"].where(
        panel["can_buy_t1"] & panel["can_sell_at_return"]
    )
    financial = build_pit_financial_snapshot(panel.loc[panel["is_eligible"], KEYS], config)
    panel = panel.merge(financial, on=KEYS, how="left", validate="one_to_one")
    panel = _attach_valuation_inputs(panel, value, trading_days, config)
    panel = panel.sort_values(KEYS).reset_index(drop=True)

    loaded = {
        "stock_master": master, "calendar": full_calendar, "price_raw": raw_price,
        "price_forward": price,
        "trade": trade, "value": value, "balance": financial, "income": financial, "st": st,
        "suspend": suspend, "limit": limit_status,
    }
    return (
        panel,
        schedule,
        _build_exclusion_audit(panel),
        _source_catalog(config, loaded),
        _build_exchange_code_audit(panel),
    )


def assert_m1_invariants(dataset: M1Dataset, config: AllAStyleBoxConfig = DEFAULT_CONFIG) -> None:
    """基于可观察键、价格和实际路径验证 m1 防线。"""
    schedule = dataset.schedule
    panel = dataset.monthly_panel
    if schedule.empty or panel.empty:
        raise AssertionError("m1 日历或月度面板为空")
    if schedule["holding_month"].duplicated().any():
        raise AssertionError("持有月份不唯一")
    if not (schedule["execution_date"] > schedule["signal_date"]).all():
        raise AssertionError("存在不晚于信号日的执行日")
    if not (schedule["return_date"] > schedule["execution_date"]).all():
        raise AssertionError("存在不晚于执行日的收益端点")
    if panel.duplicated(KEYS).any():
        raise AssertionError("同月同股票出现重复记录")
    for column in (
        "current_info_publ_date",
        "prior_info_publ_date",
        "prior_fy_info_publ_date",
        "balance_info_publ_date",
        "book_to_price_source_date",
        "earnings_to_price_source_date",
        "sales_to_price_source_date",
        "dividend_source_date",
    ):
        known = panel[column].notna()
        if (panel.loc[known, column] > panel.loc[known, "signal_date"]).any():
            raise AssertionError(f"{column} 晚于信号日，存在财务前视")
    known_period = panel["financial_end_date"].notna()
    if (panel.loc[known_period, "period_available_date"] > panel.loc[known_period, "signal_date"]).any():
        raise AssertionError("财政期首次可得日晚于信号日")
    known_prior = panel["prior_financial_end_date"].notna()
    expected_prior = panel.loc[known_prior, "financial_end_date"] - pd.DateOffset(years=1)
    if not panel.loc[known_prior, "prior_financial_end_date"].eq(expected_prior).all():
        raise AssertionError("上年同期财政期键错配")
    known_prior_fy = panel["prior_fy_financial_end_date"].notna()
    expected_prior_fy = pd.to_datetime(
        (panel.loc[known_prior_fy, "financial_end_date"].dt.year - 1).astype(str)
        + "-12-31"
    )
    if not panel.loc[known_prior_fy, "prior_fy_financial_end_date"].eq(
        expected_prior_fy
    ).all():
        raise AssertionError("TTM上年年报财政期键错配")
    non_annual = known_period & ~(
        panel["financial_end_date"].dt.month.eq(12)
        & panel["financial_end_date"].dt.day.eq(31)
    )
    for source, ttm_column in (
        ("total_operating_revenue", "ttm_revenue"),
        ("net_profit", "ttm_net_profit"),
    ):
        complete = non_annual & panel[
            [f"current_{source}", f"prior_{source}", f"prior_fy_{source}"]
        ].notna().all(axis=1)
        expected_ttm = (
            panel.loc[complete, f"current_{source}"]
            + panel.loc[complete, f"prior_fy_{source}"]
            - panel.loc[complete, f"prior_{source}"]
        )
        if not np.allclose(
            panel.loc[complete, ttm_column],
            expected_ttm,
            rtol=config.numeric_tolerance,
            atol=config.numeric_tolerance,
            equal_nan=False,
        ):
            raise AssertionError(f"{ttm_column} 不等于三段重建式")
    fresh_dividend = panel["dividend_yield"].notna()
    if not panel.loc[fresh_dividend, "dividend_is_fresh"].all():
        raise AssertionError("股息率使用了超过5个交易日或未来来源")
    source_paths = dataset.source_catalog["resolved_path"].map(Path)
    if dataset.source_catalog["uses_index_components"].any():
        raise AssertionError("动态全A底座不得使用任何指数成分")
    root = config.data_root.resolve()
    for source_path in source_paths:
        resolved = source_path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise AssertionError(f"数据源不是已存在的本地data_root文件: {resolved}")
    expected_eligibility = ~panel[
        [
            "unsupported_exchange", "exchange_not_active", "possible_code_transition_duplicate",
            "listing_age_unavailable", "listing_age_too_short",
            "missing_signal_price", "missing_signal_trade", "nonpositive_market_value",
            "signal_no_volume", "signal_is_st", "signal_is_suspended",
            "signal_is_limit_up", "signal_is_limit_down",
        ]
    ].any(axis=1)
    if not panel["is_eligible"].eq(expected_eligibility).all():
        raise AssertionError("T+1或其他未来信息污染了T日合格池")
    if panel.loc[panel["is_eligible"], "listing_age_trading_days"].lt(
        config.minimum_listing_trading_days
    ).any():
        raise AssertionError("合格池含上市龄不足120交易日的股票")
    before_bse = panel["signal_date"].lt(pd.Timestamp(config.beijing_exchange_start))
    if panel.loc[before_bse, "exchange"].eq("BJ").any():
        raise AssertionError("北交所开市前出现BJ分类")
    if panel.loc[before_bse & panel["is_bse_code_prefix"], "is_eligible"].any():
        raise AssertionError("北交所开市前的股转系统号段进入合格池")
    if not dataset.exchange_code_audit["candidate_rows"].eq(
        dataset.exchange_code_audit["unique_stock_codes"]
    ).all():
        raise AssertionError("同一信号日同一原始代码重复")
    required = {
        "execution_vwap", "return_vwap", "execution_vwap_valid", "return_vwap_valid",
        "gross_holding_return", "gross_holding_return_executable",
    }
    missing = sorted(required - set(panel.columns))
    if missing:
        raise AssertionError(f"m1缺少冻结价格/收益字段: {missing}")
    for role in ("execution", "return"):
        valid_vwap = panel[f"{role}_vwap_valid"].fillna(False)
        if not (
            panel.loc[valid_vwap, f"{role}_vwap"].gt(0)
            & np.isfinite(panel.loc[valid_vwap, f"{role}_vwap"])
            & panel.loc[valid_vwap, f"{role}_close_scale_sanity"]
            & panel.loc[valid_vwap, f"{role}_vwap_unit_sanity"]
        ).all():
            raise AssertionError(f"{role} VWAP有效标记与可观察价格事实不一致")
    if panel.loc[panel["execution_base_tradable"], "execution_vwap_valid"].ne(True).any():
        raise AssertionError("执行可交易记录缺少有效VWAP")
    gross_known = panel["gross_holding_return"].notna()
    recomputed = (
        panel.loc[gross_known, "return_vwap"]
        / panel.loc[gross_known, "execution_vwap"]
        - 1.0
    )
    if not np.allclose(
        panel.loc[gross_known, "gross_holding_return"], recomputed,
        rtol=1.0e-12, atol=1.0e-12, equal_nan=True,
    ):
        raise AssertionError("个股持有期毛收益无法由冻结VWAP端点重算")


def run_m1_synthetic_regression_checks(
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> dict[str, object]:
    """覆盖PIT乱序、多版本、北交所边界、VWAP单位与上市龄边界。"""
    keys = pd.DataFrame(
        {
            "stock_code": ["B", "A", "A"],
            "signal_date": pd.to_datetime(["2024-04-30", "2023-04-30", "2024-04-30"]),
        }
    )
    vintages = pd.DataFrame(
        {
            "stock_code": ["A", "A", "A", "A", "B", "B"],
            "end_date": pd.to_datetime(
                ["2022-03-31", "2023-03-31", "2023-03-31", "2024-03-31", "2022-03-31", "2023-03-31"]
            ),
            "info_publ_date": pd.to_datetime(
                ["2022-04-20", "2023-04-20", "2023-05-10", "2024-04-20", "2022-04-15", "2024-03-01"]
            ),
            "total_operating_revenue": [50.0, 100.0, 110.0, 130.0, 80.0, 200.0],
            "net_profit": [5.0, 10.0, 11.0, 13.0, 8.0, 20.0],
        }
    )
    pit = _build_pit_snapshot_from_vintages(keys, vintages)
    if pit[["stock_code", "signal_date"]].to_records(index=False).tolist() != keys.to_records(index=False).tolist():
        raise AssertionError("PIT合成回归未保持输入键顺序")
    expected = [200.0, 100.0, 130.0]
    if not np.allclose(pit["current_total_operating_revenue"], expected):
        raise AssertionError("PIT乱序/多股票回写发生跨行错配")
    if pit.loc[2, "prior_total_operating_revenue"] != 110.0:
        raise AssertionError("PIT同财政期多版本未选择T日前最新披露")
    for column in ("current_info_publ_date", "prior_info_publ_date"):
        known = pit[column].notna()
        if (pit.loc[known, column] > pit.loc[known, "signal_date"]).any():
            raise AssertionError("PIT合成回归出现未来披露")

    exchange = classify_exchange(
        pd.Series(["920001", "830001", "600000", "920001"]),
        pd.Series(pd.to_datetime(["2021-09-30", "2021-09-30", "2021-09-30", "2021-11-30"])),
        config,
    )
    if exchange["exchange"].tolist() != ["PRE_BSE_NEEQ", "PRE_BSE_NEEQ", "SH", "BJ"]:
        raise AssertionError("北交所开市时点边界错误")

    forward = pd.DataFrame(
        {
            "stock_code": ["X", "Y"], "date": pd.to_datetime(["2025-01-02"] * 2),
            "adj_factor": [10.0, 10.0], "close": [5.0, 5.0],
        }
    )
    raw = pd.DataFrame(
        {
            "stock_code": ["X", "Y"], "date": pd.to_datetime(["2025-01-02"] * 2),
            "vwap": [9.8, 0.0], "close": [10.0, 10.0], "low": [9.0, 9.0], "high": [11.0, 11.0],
        }
    )
    converted = _adjusted_vwap_panel(forward, raw)
    if not np.isclose(converted.loc[0, "forward_vwap"], 4.9) or not bool(converted.loc[0, "forward_vwap_valid"]):
        raise AssertionError("VWAP前复权转换或单位sanity错误")
    if bool(converted.loc[1, "forward_vwap_valid"]):
        raise AssertionError("非正VWAP未被判为不可用")

    trading_days = pd.date_range("2024-01-02", periods=config.minimum_listing_trading_days, freq="B")
    ages = _listing_age(
        pd.Series([trading_days[0], trading_days[0]]),
        pd.Series([trading_days[-2], trading_days[-1]]),
        pd.DatetimeIndex(trading_days),
    )
    if ages.tolist() != [config.minimum_listing_trading_days - 1, config.minimum_listing_trading_days]:
        raise AssertionError("上市龄第119/120交易日边界错误")
    return {
        "pit_rows": len(pit),
        "pit_future_disclosures": 0,
        "pre_bse_exchange": exchange.loc[0, "exchange"],
        "valid_forward_vwap": float(converted.loc[0, "forward_vwap"]),
        "listing_age_boundary": ages.tolist(),
    }


def build_m1_dataset(
    config: AllAStyleBoxConfig | None = None,
    *,
    smoke_months: int | None = None,
    smoke_stock_limit: int | None = None,
) -> M1Dataset:
    """构造 m1 完整数据合同；不写正式结果、不运行回测。"""
    cfg = config or DEFAULT_CONFIG
    panel, schedule, exclusion, sources, exchange_audit = build_dynamic_all_a_panel(
        cfg,
        smoke_months=smoke_months,
        smoke_stock_limit=smoke_stock_limit,
    )
    dataset = M1Dataset(
        schedule=schedule,
        monthly_panel=panel,
        exclusion_audit=exclusion,
        availability_audit=build_availability_audit(panel),
        source_catalog=sources,
        exchange_code_audit=exchange_audit,
    )
    assert_m1_invariants(dataset, cfg)
    return dataset


__all__ = [
    "M1Dataset",
    "build_m1_dataset",
    "load_frozen_transfer_market_data",
    "load_rebalance_schedule",
    "classify_exchange",
    "build_dynamic_all_a_panel",
    "build_pit_financial_snapshot",
    "build_availability_audit",
    "assert_m1_invariants",
    "run_m1_synthetic_regression_checks",
]
