"""构建 AS24–AS26 固定双快照联合候选池 / Yahoo 日频缓存。

下载器是单线程、幂等且可续跑的：逐证券写入 ``.part``，回读校验后才
原子改名；manifest 也逐证券原子更新。只有 ``success`` 且文件哈希一致
的证券会在重跑时跳过。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import shutil
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

import numpy as np
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from yfinance import shared as yf_shared

from .config import DEFAULT_CONFIG, M1Config, USYahooConfig


PRICE_COLUMNS = (
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
YAHOO_REQUIRED_COLUMNS = (
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Volume",
    "Dividends",
    "Stock Splits",
)

PRIMARY_PRECHECK_EXCLUDED = (
    "ACN", "AMD", "ARE", "BAX", "BDX", "BKNG", "CDNS", "CBRE", "CNP", "CEG",
    "CPAY", "CCI", "DELL", "FDXF", "GEHC", "GEV", "HONA", "INTC", "IP", "KVUE",
    "KEY", "KHC", "LRCX", "L", "MSCI", "ORLY", "PFE", "PLD", "DGX", "Q",
    "RVTY", "SNDK", "SOLV", "TGT", "TEL", "TYL", "VLTO", "VICI", "WEC", "WSM",
    "ZTS",
)
SUPPLEMENT_PRECHECK_PASSED = (
    "AAP", "ALK", "AAL", "BBWI", "BIO", "BWA", "CZR", "CPB", "KMX", "CE",
    "CAG", "XRAY", "ENPH", "EPAM", "ETSY", "FMC", "ILMN", "IPGP", "LW", "LNC",
    "LUMN", "MKTX", "MTCH", "MHK", "NWL", "OGN", "PENN", "POOL", "PVH", "QRVO",
    "RHI", "SEDG", "TFX", "UAA", "UA", "VFC", "VNO", "WHR", "ZION",
)


class DownloadPaused(RuntimeError):
    """连续限流/认证错误达到 AS26 阈值。"""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_utc(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    """分块计算文件 SHA256。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(part, path)


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_bytes(payload)
    os.replace(part, path)


def _fetch_source_html(url: str, config: USYahooConfig) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": config.user_agent},
    )
    with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
        return response.read()


def _symbol_mapping(source_symbol: str) -> tuple[str, str]:
    yahoo_symbol = source_symbol.replace(".", "-")
    reason = "dot_to_dash" if yahoo_symbol != source_symbol else "identity"
    return yahoo_symbol, reason


def _parse_snapshot(
    html: bytes,
    *,
    label: str,
    url: str,
    oldid: str,
    revision_timestamp: str,
    expected_html_sha256: str,
    expected_symbol_sha256: str,
    expected_count: int,
) -> tuple[pd.DataFrame, str, str]:
    html_hash = hashlib.sha256(html).hexdigest()
    if html_hash != expected_html_sha256:
        raise ValueError(
            f"{label} HTML 哈希不一致: expected={expected_html_sha256}, "
            f"actual={html_hash}"
        )
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="constituents")
    if table is None:
        raise ValueError(f"{label} 未找到 id=constituents 的成分表")
    rows = table.find_all("tr")
    headers = [cell.get_text(" ", strip=True) for cell in rows[0].find_all("th")]
    records = [
        [cell.get_text(" ", strip=True) for cell in row.find_all("td")]
        for row in rows[1:]
        if row.find_all("td")
    ]
    raw = pd.DataFrame(records, columns=headers)
    symbols = raw["Symbol"].astype("string").str.strip()
    symbol_payload = ("\n".join(symbols.tolist()) + "\n").encode("utf-8")
    symbol_hash = hashlib.sha256(symbol_payload).hexdigest()
    if (
        len(raw) != expected_count
        or symbols.nunique() != expected_count
        or symbol_hash != expected_symbol_sha256
    ):
        raise ValueError(
            f"{label} 清单合同不一致: rows={len(raw)}, "
            f"unique={symbols.nunique()}, symbol_sha256={symbol_hash}"
        )
    result = raw.rename(
        columns={
            "Symbol": "source_symbol",
            "Security": "security",
            "SEC filings": "sec_filings",
            "GICS Sector": "gics_sector",
            "GICS Sub-Industry": "gics_sub_industry",
            "Headquarters Location": "headquarters_location",
            "Date first added": "date_first_added",
            "CIK": "cik",
            "Founded": "founded",
        }
    )
    result["source_symbol"] = symbols
    result["snapshot_label"] = label
    result["snapshot_oldid"] = oldid
    result["snapshot_timestamp_utc"] = revision_timestamp
    result["source_url"] = url
    result["source_html_sha256"] = html_hash
    result["symbol_list_sha256"] = symbol_hash
    return result, html_hash, symbol_hash


def build_constituents_snapshot(
    *,
    config: USYahooConfig = DEFAULT_CONFIG.us_yahoo,
    force_fetch: bool = False,
) -> pd.DataFrame:
    """核验两份固定修订并按 AS24 固定清单构造 462+39=501 候选。"""
    if config.source_html_path.is_file() and not force_fetch:
        primary_html = config.source_html_path.read_bytes()
    else:
        primary_html = _fetch_source_html(config.primary_constituents_url, config)
    if config.supplement_source_html_path.is_file() and not force_fetch:
        supplement_html = config.supplement_source_html_path.read_bytes()
    else:
        legacy_source = config.legacy_cache_dir / "source_page.html"
        if legacy_source.is_file() and sha256_file(legacy_source) == (
            config.supplement_expected_html_sha256
        ):
            supplement_html = legacy_source.read_bytes()
        else:
            supplement_html = _fetch_source_html(
                config.supplement_constituents_url, config
            )

    primary, primary_html_hash, primary_symbol_hash = _parse_snapshot(
        primary_html,
        label="primary_20260721",
        url=config.primary_constituents_url,
        oldid=config.primary_revision_oldid,
        revision_timestamp=config.primary_revision_timestamp,
        expected_html_sha256=config.primary_expected_html_sha256,
        expected_symbol_sha256=config.primary_expected_symbol_sha256,
        expected_count=config.primary_expected_constituents,
    )
    supplement, supplement_html_hash, supplement_symbol_hash = _parse_snapshot(
        supplement_html,
        label="supplement_20211230",
        url=config.supplement_constituents_url,
        oldid=config.supplement_revision_oldid,
        revision_timestamp=config.supplement_revision_timestamp,
        expected_html_sha256=config.supplement_expected_html_sha256,
        expected_symbol_sha256=config.supplement_expected_symbol_sha256,
        expected_count=config.supplement_expected_constituents,
    )
    primary_symbols = primary["source_symbol"].astype(str)
    missing_excluded = sorted(set(PRIMARY_PRECHECK_EXCLUDED) - set(primary_symbols))
    if missing_excluded:
        raise ValueError(f"主池固定预检排除清单不在主快照: {missing_excluded}")
    primary_pass = primary.loc[
        ~primary["source_symbol"].astype(str).isin(PRIMARY_PRECHECK_EXCLUDED)
    ].copy()
    if len(primary_pass) != 462:
        raise ValueError(f"主池固定预检通过数应为 462，实际 {len(primary_pass)}")

    difference = supplement.loc[
        ~supplement["source_symbol"].astype(str).isin(set(primary_symbols))
    ].copy()
    if len(difference) != 90:
        raise ValueError(f"2021 对主池差集应为 90，实际 {len(difference)}")
    difference_symbols = difference["source_symbol"].astype(str).tolist()
    missing_supplement = sorted(set(SUPPLEMENT_PRECHECK_PASSED) - set(difference_symbols))
    if missing_supplement:
        raise ValueError(f"补充固定通过清单不在 2021 差集: {missing_supplement}")
    supplement_pass = difference.loc[
        difference["source_symbol"].astype(str).isin(SUPPLEMENT_PRECHECK_PASSED)
    ].copy()
    if supplement_pass["source_symbol"].astype(str).tolist() != list(
        SUPPLEMENT_PRECHECK_PASSED
    ):
        raise ValueError("补充39只顺序与 plan 固定原表顺序不一致")

    primary_pass.insert(0, "pool_source", "primary_precheck_pass")
    supplement_pass.insert(0, "pool_source", "supplement_precheck_pass")
    result = pd.concat([primary_pass, supplement_pass], ignore_index=True)
    if (
        len(result) != config.expected_constituents
        or result["source_symbol"].nunique() != config.expected_constituents
    ):
        raise ValueError("AS24 联合候选池不是 501 个唯一证券")
    mappings = [_symbol_mapping(str(symbol)) for symbol in result["source_symbol"]]
    result.insert(1, "yahoo_symbol", [item[0] for item in mappings])
    result.insert(2, "mapping_reason", [item[1] for item in mappings])
    if result["yahoo_symbol"].duplicated().any():
        duplicates = result.loc[
            result["yahoo_symbol"].duplicated(keep=False),
            ["source_symbol", "yahoo_symbol"],
        ].to_dict("records")
        raise ValueError(f"Yahoo 查询代码映射不唯一: {duplicates}")

    config.cache_dir.mkdir(parents=True, exist_ok=True)
    _atomic_bytes(config.source_html_path, primary_html)
    _atomic_bytes(config.supplement_source_html_path, supplement_html)
    csv_payload = result.to_csv(index=False, lineterminator="\n").encode("utf-8")
    _atomic_bytes(config.constituents_path, csv_payload)
    union_symbols = result["source_symbol"].astype(str).tolist()
    union_hash = hashlib.sha256(
        ("\n".join(union_symbols) + "\n").encode("utf-8")
    ).hexdigest()
    precheck_manifest = {
        "schema_version": 1,
        "selection_contract": "AS24_fixed_sparse_quarterly_precheck",
        "precheck_request": {
            "period1": DEFAULT_CONFIG.sample.start_date,
            "period2_exclusive": DEFAULT_CONFIG.sample.end_exclusive,
            "interval": "3mo",
            "criterion": "研究期至少一条完整OHLCV",
        },
        "primary": {
            "url": config.primary_constituents_url,
            "oldid": config.primary_revision_oldid,
            "html_sha256": primary_html_hash,
            "symbol_list_sha256": primary_symbol_hash,
            "snapshot_count": len(primary),
            "passed_count": len(primary_pass),
            "excluded_count": len(PRIMARY_PRECHECK_EXCLUDED),
            "excluded_symbols": list(PRIMARY_PRECHECK_EXCLUDED),
            "passed_symbols": primary_pass["source_symbol"].astype(str).tolist(),
        },
        "supplement": {
            "url": config.supplement_constituents_url,
            "oldid": config.supplement_revision_oldid,
            "html_sha256": supplement_html_hash,
            "symbol_list_sha256": supplement_symbol_hash,
            "snapshot_count": len(supplement),
            "difference_count": len(difference),
            "passed_count": len(supplement_pass),
            "passed_symbols": list(SUPPLEMENT_PRECHECK_PASSED),
        },
        "union": {
            "candidate_count": len(result),
            "symbol_list_sha256": union_hash,
            "symbols": union_symbols,
        },
    }
    _atomic_json(config.precheck_manifest_path, precheck_manifest)
    return result


def _new_manifest(config: USYahooConfig) -> dict[str, Any]:
    precheck = json.loads(config.precheck_manifest_path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "dataset": "r007_us_yahoo_union500_v1",
        "created_at_utc": _iso_utc(),
        "updated_at_utc": _iso_utc(),
        "source": {
            "primary": {
                "constituents_url": config.primary_constituents_url,
                "revision_oldid": config.primary_revision_oldid,
                "revision_timestamp_utc": config.primary_revision_timestamp,
                "html_sha256": config.primary_expected_html_sha256,
                "symbol_list_sha256": config.primary_expected_symbol_sha256,
                "precheck_passed": 462,
            },
            "supplement": {
                "constituents_url": config.supplement_constituents_url,
                "revision_oldid": config.supplement_revision_oldid,
                "revision_timestamp_utc": config.supplement_revision_timestamp,
                "html_sha256": config.supplement_expected_html_sha256,
                "symbol_list_sha256": config.supplement_expected_symbol_sha256,
                "precheck_passed": 39,
            },
            "union_symbol_list_sha256": precheck["union"]["symbol_list_sha256"],
            "expected_constituents": config.expected_constituents,
        },
        "client": {"name": "yfinance", "version": yf.__version__},
        "request": {
            "start": DEFAULT_CONFIG.sample.start_date,
            "end_exclusive": DEFAULT_CONFIG.sample.end_exclusive,
            "interval": config.interval,
            "auto_adjust": config.auto_adjust,
            "actions": config.actions,
            "repair": config.repair,
            "keepna": config.keepna,
            "threads": config.threads,
            "timeout_seconds": config.timeout_seconds,
        },
        "acceptance": {
            "minimum_ohlcv_non_null_rate": config.minimum_ohlcv_non_null_rate,
            "minimum_successful_securities": config.minimum_successful_securities,
            "maximum_failed_securities": config.maximum_failed_securities,
        },
        "status": "in_progress",
        "paused_until_utc": None,
        "pause_reason": None,
        "consecutive_rate_auth_errors": 0,
        "entries": {},
        "summary": {},
    }


def load_manifest(config: USYahooConfig = DEFAULT_CONFIG.us_yahoo) -> dict[str, Any]:
    """加载既有 manifest；不存在时返回精确合同的新 manifest。"""
    if not config.manifest_path.is_file():
        return _new_manifest(config)
    manifest = json.loads(config.manifest_path.read_text(encoding="utf-8"))
    client = manifest.get("client", {})
    if client.get("version") != yf.__version__ or yf.__version__ != "1.2.0":
        raise RuntimeError(
            f"缓存客户端版本不一致: manifest={client.get('version')}, "
            f"runtime={yf.__version__}, required=1.2.0"
        )
    source = manifest.get("source", {})
    primary = source.get("primary", {})
    supplement = source.get("supplement", {})
    if (
        manifest.get("dataset") != "r007_us_yahoo_union500_v1"
        or primary.get("revision_oldid") != config.primary_revision_oldid
        or primary.get("html_sha256") != config.primary_expected_html_sha256
        or supplement.get("revision_oldid") != config.supplement_revision_oldid
        or supplement.get("html_sha256") != config.supplement_expected_html_sha256
    ):
        raise RuntimeError("既有 manifest 不属于 AS24 固定联合候选池，拒绝混用")
    return manifest


def _price_path(config: USYahooConfig, yahoo_symbol: str) -> Path:
    safe_name = quote(yahoo_symbol, safe="-_")
    return config.prices_dir / f"{safe_name}.parquet"


def _valid_cached_success(
    entry: dict[str, Any] | None,
    *,
    config: USYahooConfig,
) -> bool:
    if not entry or entry.get("status") != "success":
        return False
    relative = entry.get("file")
    expected_hash = entry.get("file_sha256")
    if not relative or not expected_hash:
        return False
    path = config.cache_dir / str(relative)
    if not path.is_file() or sha256_file(path) != expected_hash:
        return False
    try:
        cached = pd.read_parquet(path, columns=list(PRICE_COLUMNS))
    except Exception:
        return False
    return (
        len(cached) == int(entry.get("rows", -1))
        and not cached.duplicated(["stock_code", "date"]).any()
    )


def _download_one_yahoo(yahoo_symbol: str, config: USYahooConfig) -> pd.DataFrame:
    yf_shared._ERRORS = {}
    data = yf.download(
        yahoo_symbol,
        start=DEFAULT_CONFIG.sample.start_date,
        end=DEFAULT_CONFIG.sample.end_exclusive,
        actions=config.actions,
        threads=config.threads,
        interval=config.interval,
        auto_adjust=config.auto_adjust,
        repair=config.repair,
        keepna=config.keepna,
        progress=False,
        timeout=config.timeout_seconds,
        multi_level_index=False,
    )
    error = str(yf_shared._ERRORS.get(yahoo_symbol.upper(), ""))
    if data is None or data.empty:
        raise RuntimeError(error or "Yahoo 返回空数据")
    missing = sorted(set(YAHOO_REQUIRED_COLUMNS) - set(data.columns))
    if missing:
        raise KeyError(f"Yahoo 返回缺少字段 {missing}")
    return data


def _normalize_price_frame(
    raw: pd.DataFrame,
    *,
    source_symbol: str,
    yahoo_symbol: str,
    config: USYahooConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = raw.loc[:, list(YAHOO_REQUIRED_COLUMNS)].copy()
    dates = pd.DatetimeIndex(pd.to_datetime(frame.index, errors="raise"))
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    frame.insert(0, "date", dates.normalize())
    start = pd.Timestamp(DEFAULT_CONFIG.sample.start_date)
    end = pd.Timestamp(DEFAULT_CONFIG.sample.end_exclusive)
    frame = frame.loc[frame["date"].ge(start) & frame["date"].lt(end)].copy()
    if frame.empty:
        raise ValueError("研究区间内没有数据")
    frame = frame.rename(
        columns={
            "Open": "open_raw",
            "High": "high_raw",
            "Low": "low_raw",
            "Close": "close_raw",
            "Adj Close": "adj_close",
            "Volume": "volume",
            "Dividends": "dividends",
            "Stock Splits": "stock_splits",
        }
    )
    numeric = [
        "open_raw",
        "high_raw",
        "low_raw",
        "close_raw",
        "adj_close",
        "volume",
        "dividends",
        "stock_splits",
    ]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame.insert(0, "yahoo_symbol", yahoo_symbol)
    frame.insert(0, "source_symbol", source_symbol)
    frame.insert(0, "stock_code", source_symbol)
    frame = frame.sort_values("date")
    if frame.empty:
        raise ValueError("标准化后无数据")
    if frame.duplicated(["stock_code", "date"]).any():
        raise ValueError("标准化后存在重复 stock_code/date 键")

    ohlcv = ["open_raw", "high_raw", "low_raw", "close_raw", "volume"]
    effective = frame.loc[frame[ohlcv].notna().any(axis=1)].copy()
    if effective.empty:
        raise ValueError("有效区间没有 OHLCV 数据")
    non_null_rates = effective[ohlcv].notna().mean()
    minimum_rate = float(non_null_rates.min())
    if minimum_rate < config.minimum_ohlcv_non_null_rate:
        raise ValueError(
            f"OHLCV 最低非空率 {minimum_rate:.6f} "
            f"< {config.minimum_ohlcv_non_null_rate:.6f}"
        )

    complete = frame[["open_raw", "high_raw", "low_raw", "close_raw"]].notna().all(
        axis=1
    )
    ohlc_valid = (
        frame["open_raw"].gt(0)
        & frame["close_raw"].gt(0)
        & frame["high_raw"].ge(frame[["open_raw", "close_raw"]].max(axis=1))
        & frame["low_raw"].le(frame[["open_raw", "close_raw"]].min(axis=1))
        & frame["high_raw"].ge(frame["low_raw"])
    )
    frame["ohlc_logic_valid"] = (~complete) | ohlc_valid
    factor = frame["adj_close"] / frame["close_raw"]
    factor_valid = factor.gt(0) & np.isfinite(factor)
    frame["adj_factor"] = factor.where(factor_valid)
    for raw_column, adjusted_column in (
        ("open_raw", "open_adj"),
        ("high_raw", "high_adj"),
        ("low_raw", "low_adj"),
        ("close_raw", "close_adj"),
    ):
        adjusted = frame[raw_column] * frame["adj_factor"]
        frame[adjusted_column] = adjusted.where(
            frame["ohlc_logic_valid"] & np.isfinite(adjusted)
        )
    frame["return_eligible"] = (
        frame["ohlc_logic_valid"]
        & frame["open_adj"].gt(0)
        & frame["close_adj"].gt(0)
    )
    frame = frame.loc[:, list(PRICE_COLUMNS)].reset_index(drop=True)
    audit = {
        "rows": len(frame),
        "first_date": frame["date"].min().date().isoformat(),
        "last_date": frame["date"].max().date().isoformat(),
        "ohlcv_non_null_rate": {
            column: float(non_null_rates[column]) for column in ohlcv
        },
        "minimum_ohlcv_non_null_rate": minimum_rate,
        "ohlc_logic_violation_count": int((~frame["ohlc_logic_valid"]).sum()),
        "return_ineligible_count": int((~frame["return_eligible"]).sum()),
        "missing_count": {
            column: int(frame[column].isna().sum()) for column in PRICE_COLUMNS
        },
        "dividend_event_count": int(frame["dividends"].fillna(0).ne(0).sum()),
        "split_event_count": int(frame["stock_splits"].fillna(0).ne(0).sum()),
    }
    return frame, audit


def _classify_error(message: str) -> str:
    lowered = message.lower()
    if any(token in lowered for token in ("429", "too many requests", "rate limit")):
        return "rate_limit"
    if any(
        token in lowered
        for token in ("401", "403", "unauthorized", "forbidden", "invalid crumb")
    ):
        return "authentication"
    if any(token in lowered for token in ("500", "502", "503", "504", "timeout")):
        return "temporary"
    return "other"


def _update_summary(
    manifest: dict[str, Any],
    constituents: pd.DataFrame,
) -> dict[str, int]:
    entries = manifest.setdefault("entries", {})
    statuses = {
        symbol: str(entries.get(symbol, {}).get("status", "pending"))
        for symbol in constituents["source_symbol"].astype(str)
    }
    summary = {
        "candidate_count": len(statuses),
        "success_count": sum(status == "success" for status in statuses.values()),
        "failed_count": sum(status == "failed" for status in statuses.values()),
        "pending_count": sum(
            status not in {"success", "failed"} for status in statuses.values()
        ),
    }
    manifest["summary"] = summary
    manifest["updated_at_utc"] = _iso_utc()
    return summary


def _save_manifest(
    manifest: dict[str, Any],
    constituents: pd.DataFrame,
    config: USYahooConfig,
) -> dict[str, int]:
    summary = _update_summary(manifest, constituents)
    _atomic_json(config.manifest_path, manifest)
    return summary


def migrate_legacy_cache(
    constituents: pd.DataFrame,
    manifest: dict[str, Any],
    *,
    config: USYahooConfig = DEFAULT_CONFIG.us_yahoo,
) -> dict[str, int]:
    """按 AS26 将旧目录中合同完全一致的候选缓存复制到新缓存。"""
    legacy_manifest_path = config.legacy_cache_dir / "manifest.json"
    migration = {
        "legacy_total_success_entries": 0,
        "legacy_success_entries": 0,
        "candidate_overlap": 0,
        "migrated_count": 0,
        "rejected_count": 0,
    }
    if not legacy_manifest_path.is_file():
        manifest["legacy_cache_migration"] = migration
        return migration
    legacy = json.loads(legacy_manifest_path.read_text(encoding="utf-8"))
    expected_request = manifest["request"]
    if legacy.get("request") != expected_request:
        migration["rejected_count"] = min(
            config.legacy_authorized_success_count,
            sum(
                entry.get("status") == "success"
                for entry in legacy.get("entries", {}).values()
            ),
        )
        manifest["legacy_cache_migration"] = {
            **migration,
            "rejection_reason": "request_parameters_mismatch",
            "legacy_manifest": str(legacy_manifest_path),
        }
        return migration

    candidate_lookup = constituents.set_index("source_symbol")
    legacy_success = [
        (source_symbol, entry)
        for source_symbol, entry in legacy.get("entries", {}).items()
        if entry.get("status") == "success"
    ]
    legacy_success.sort(key=lambda item: str(item[1].get("downloaded_at_utc", "")))
    migration["legacy_total_success_entries"] = len(legacy_success)
    authorized = legacy_success[: config.legacy_authorized_success_count]
    for source_symbol, entry in authorized:
        migration["legacy_success_entries"] += 1
        if source_symbol not in candidate_lookup.index:
            continue
        migration["candidate_overlap"] += 1
        existing = manifest.get("entries", {}).get(source_symbol)
        if _valid_cached_success(existing, config=config):
            if existing.get("cache_origin", {}).get("type") == "migrated_legacy_cache":
                migration["migrated_count"] += 1
            continue
        row = candidate_lookup.loc[source_symbol]
        if str(entry.get("yahoo_symbol")) != str(row["yahoo_symbol"]):
            migration["rejected_count"] += 1
            continue
        relative = entry.get("file")
        expected_hash = entry.get("file_sha256")
        if not relative or not expected_hash:
            migration["rejected_count"] += 1
            continue
        source_path = config.legacy_cache_dir / str(relative)
        try:
            if not source_path.is_file() or sha256_file(source_path) != expected_hash:
                raise ValueError("旧缓存文件不存在或 SHA256 不一致")
            cached = pd.read_parquet(source_path)
            if set(cached.columns) != set(PRICE_COLUMNS):
                raise ValueError("旧缓存 schema 不一致")
            if (
                cached.empty
                or cached.duplicated(["stock_code", "date"]).any()
                or set(cached["stock_code"].astype(str)) != {source_symbol}
            ):
                raise ValueError("旧缓存空表、重复键或证券键不一致")
            dates = pd.to_datetime(cached["date"], errors="raise").dt.normalize()
            if not (
                dates.ge(pd.Timestamp(DEFAULT_CONFIG.sample.start_date))
                & dates.lt(pd.Timestamp(DEFAULT_CONFIG.sample.end_exclusive))
            ).all():
                raise ValueError("旧缓存日期超出正式请求区间")
            target_path = _price_path(config, str(row["yahoo_symbol"]))
            target_path.parent.mkdir(parents=True, exist_ok=True)
            part_path = target_path.with_suffix(target_path.suffix + ".part")
            shutil.copyfile(source_path, part_path)
            copied_hash = sha256_file(part_path)
            if copied_hash != expected_hash:
                raise ValueError("复制后 SHA256 不一致")
            os.replace(part_path, target_path)
        except Exception:
            migration["rejected_count"] += 1
            continue
        migrated = dict(entry)
        migrated["file"] = target_path.relative_to(config.cache_dir).as_posix()
        migrated["cache_origin"] = {
            "type": "migrated_legacy_cache",
            "source_manifest": str(legacy_manifest_path),
            "source_file": str(source_path),
            "source_file_sha256": expected_hash,
            "migrated_at_utc": _iso_utc(),
        }
        manifest.setdefault("entries", {})[source_symbol] = migrated
        migration["migrated_count"] += 1
    manifest["legacy_cache_migration"] = {
        **migration,
        "legacy_manifest": str(legacy_manifest_path),
    }
    return migration


def _download_security(
    row: Any,
    *,
    manifest: dict[str, Any],
    constituents: pd.DataFrame,
    config: USYahooConfig,
    random_generator: random.Random,
) -> bool:
    source_symbol = str(row.source_symbol)
    yahoo_symbol = str(row.yahoo_symbol)
    mapping_reason = str(row.mapping_reason)
    previous = manifest.setdefault("entries", {}).get(source_symbol, {})
    if _valid_cached_success(previous, config=config):
        return False

    errors: list[dict[str, Any]] = list(previous.get("errors", []))
    total_attempts = int(previous.get("attempts", 0))
    final_entry: dict[str, Any] | None = None
    for retry_index in range(config.maximum_retries + 1):
        total_attempts += 1
        try:
            raw = _download_one_yahoo(yahoo_symbol, config)
            normalized, audit = _normalize_price_frame(
                raw,
                source_symbol=source_symbol,
                yahoo_symbol=yahoo_symbol,
                config=config,
            )
            final_path = _price_path(config, yahoo_symbol)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            part_path = final_path.with_suffix(final_path.suffix + ".part")
            normalized.to_parquet(part_path, index=False)
            roundtrip = pd.read_parquet(part_path, columns=list(PRICE_COLUMNS))
            if (
                len(roundtrip) != len(normalized)
                or roundtrip.duplicated(["stock_code", "date"]).any()
            ):
                raise ValueError("Parquet .part 回读校验失败")
            os.replace(part_path, final_path)
            file_hash = sha256_file(final_path)
            final_entry = {
                "source_symbol": source_symbol,
                "yahoo_symbol": yahoo_symbol,
                "mapping_reason": mapping_reason,
                "status": "success",
                "attempts": total_attempts,
                "errors": errors,
                "file": final_path.relative_to(config.cache_dir).as_posix(),
                "file_sha256": file_hash,
                "cache_origin": {"type": "downloaded_yfinance_1.2.0"},
                "downloaded_at_utc": _iso_utc(),
                **audit,
            }
            manifest["consecutive_rate_auth_errors"] = 0
            break
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            category = _classify_error(message)
            errors.append(
                {
                    "attempt": total_attempts,
                    "at_utc": _iso_utc(),
                    "category": category,
                    "message": message,
                }
            )
            if category in {"rate_limit", "authentication"}:
                consecutive = int(manifest.get("consecutive_rate_auth_errors", 0)) + 1
                manifest["consecutive_rate_auth_errors"] = consecutive
                if consecutive >= config.consecutive_rate_auth_limit:
                    paused_until = _utc_now() + timedelta(seconds=config.pause_seconds)
                    manifest["status"] = "paused"
                    manifest["paused_until_utc"] = _iso_utc(paused_until)
                    manifest["pause_reason"] = message
                    manifest["entries"][source_symbol] = {
                        "source_symbol": source_symbol,
                        "yahoo_symbol": yahoo_symbol,
                        "mapping_reason": mapping_reason,
                        "status": "pending",
                        "attempts": total_attempts,
                        "errors": errors,
                    }
                    _save_manifest(manifest, constituents, config)
                    raise DownloadPaused(
                        f"连续 {consecutive} 次限流/认证错误，暂停至 "
                        f"{manifest['paused_until_utc']}"
                    ) from exc
            else:
                manifest["consecutive_rate_auth_errors"] = 0
            if retry_index < config.maximum_retries:
                delay = config.retry_backoff_seconds[retry_index]
                delay += random_generator.uniform(0, config.retry_jitter_seconds)
                time.sleep(delay)
    if final_entry is None:
        final_entry = {
            "source_symbol": source_symbol,
            "yahoo_symbol": yahoo_symbol,
            "mapping_reason": mapping_reason,
            "status": "failed",
            "attempts": total_attempts,
            "errors": errors,
            "failed_at_utc": _iso_utc(),
        }
    manifest["entries"][source_symbol] = final_entry
    _save_manifest(manifest, constituents, config)
    return final_entry["status"] == "success"


def build_merged_panel(
    constituents: pd.DataFrame,
    manifest: dict[str, Any],
    *,
    config: USYahooConfig = DEFAULT_CONFIG.us_yahoo,
) -> dict[str, Any]:
    """合并全部哈希合格 success 缓存并生成审计摘要。"""
    frames: list[pd.DataFrame] = []
    for row in constituents.itertuples(index=False):
        entry = manifest.get("entries", {}).get(str(row.source_symbol))
        if not _valid_cached_success(entry, config=config):
            continue
        frames.append(pd.read_parquet(config.cache_dir / entry["file"]))
    if not frames:
        raise ValueError("没有可合并的合格美股缓存")
    panel = pd.concat(frames, ignore_index=True).sort_values(
        ["stock_code", "date"]
    )
    if panel.duplicated(["stock_code", "date"]).any():
        raise ValueError("合并美股面板存在重复 stock_code/date 键")
    part = config.merged_panel_path.with_suffix(".parquet.part")
    panel.to_parquet(part, index=False)
    roundtrip = pd.read_parquet(part)
    if len(roundtrip) != len(panel):
        raise ValueError("合并面板 .part 回读行数不一致")
    os.replace(part, config.merged_panel_path)
    panel_hash = sha256_file(config.merged_panel_path)
    summary = {
        "generated_at_utc": _iso_utc(),
        "qualified_security_count": int(panel["stock_code"].nunique()),
        "rows": len(panel),
        "first_date": panel["date"].min().date().isoformat(),
        "last_date": panel["date"].max().date().isoformat(),
        "missing_count": {
            column: int(panel[column].isna().sum()) for column in PRICE_COLUMNS
        },
        "ohlc_logic_violation_count": int((~panel["ohlc_logic_valid"]).sum()),
        "return_ineligible_count": int((~panel["return_eligible"]).sum()),
        "merged_panel_file": config.merged_panel_path.name,
        "merged_panel_sha256": panel_hash,
    }
    _atomic_json(config.audit_summary_path, summary)
    manifest["merged_panel"] = {
        "file": config.merged_panel_path.relative_to(config.cache_dir).as_posix(),
        "sha256": panel_hash,
        "rows": len(panel),
        "qualified_security_count": int(panel["stock_code"].nunique()),
    }
    _save_manifest(manifest, constituents, config)
    return summary


def run_download(
    *,
    symbols: Sequence[str] | None = None,
    batch_size: int | None = None,
    force_constituents: bool = False,
    config: M1Config = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """执行选定小样本或完整 501 证券下载，并返回本轮摘要。"""
    if yf.__version__ != "1.2.0":
        raise RuntimeError(f"必须使用 yfinance==1.2.0，实际为 {yf.__version__}")
    yahoo = config.us_yahoo
    yf.cache.set_cache_location(str(yahoo.cache_dir / "yfinance_runtime_cache"))
    constituents = build_constituents_snapshot(
        config=yahoo,
        force_fetch=force_constituents,
    )
    manifest = load_manifest(yahoo)
    manifest["status"] = "in_progress"
    if not manifest.get("paused_until_utc"):
        manifest["pause_reason"] = None
    migration = migrate_legacy_cache(
        constituents,
        manifest,
        config=yahoo,
    )
    _save_manifest(manifest, constituents, yahoo)
    paused_until_text = manifest.get("paused_until_utc")
    if paused_until_text:
        paused_until = datetime.fromisoformat(
            str(paused_until_text).replace("Z", "+00:00")
        )
        if _utc_now() < paused_until:
            raise DownloadPaused(f"AS26 冷却期未结束: {paused_until_text}")
        manifest["paused_until_utc"] = None
        manifest["pause_reason"] = None
        manifest["status"] = "in_progress"

    selected = constituents
    if symbols is not None:
        requested = list(dict.fromkeys(str(symbol).strip() for symbol in symbols))
        selected = constituents.loc[constituents["source_symbol"].isin(requested)]
        missing = sorted(set(requested) - set(selected["source_symbol"].astype(str)))
        if missing:
            raise KeyError(f"固定成分清单不含证券: {missing}")
    elif batch_size is not None:
        if batch_size <= 0:
            raise ValueError("batch_size 必须为正整数")
        pending_mask = [
            not _valid_cached_success(
                manifest.get("entries", {}).get(str(row.source_symbol)),
                config=yahoo,
            )
            for row in constituents.itertuples(index=False)
        ]
        selected = constituents.loc[pending_mask].head(batch_size)

    random_generator = random.Random(42)
    for position, row in enumerate(selected.itertuples(index=False)):
        downloaded = _download_security(
            row,
            manifest=manifest,
            constituents=constituents,
            config=yahoo,
            random_generator=random_generator,
        )
        entry = manifest["entries"].get(str(row.source_symbol), {})
        if (
            downloaded
            and entry.get("status") == "success"
            and position < len(selected) - 1
        ):
            time.sleep(yahoo.success_wait_seconds)
        summary = _update_summary(manifest, constituents)
        if summary["failed_count"] > yahoo.maximum_failed_securities:
            manifest["status"] = "failed"
            manifest["pause_reason"] = (
                f"失败证券 {summary['failed_count']} > "
                f"{yahoo.maximum_failed_securities}"
            )
            _save_manifest(manifest, constituents, yahoo)
            break

    summary = _save_manifest(manifest, constituents, yahoo)
    full_run = symbols is None and batch_size is None
    panel_summary: dict[str, Any] | None = None
    if (
        full_run
        and summary["success_count"] >= yahoo.minimum_successful_securities
        and summary["failed_count"] <= yahoo.maximum_failed_securities
    ):
        panel_summary = build_merged_panel(constituents, manifest, config=yahoo)
        manifest["status"] = "complete"
        _save_manifest(manifest, constituents, yahoo)
    elif full_run and summary["pending_count"] == 0:
        manifest["status"] = "failed"
        _save_manifest(manifest, constituents, yahoo)
    return {
        **summary,
        "manifest": str(yahoo.manifest_path),
        "cache_dir": str(yahoo.cache_dir),
        "legacy_cache_migration": migration,
        "panel_summary": panel_summary,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载 r007 固定双快照联合候选池 / Yahoo 数据缓存"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="仅下载指定 Wikipedia 原始代码；省略时续跑全部 501 证券",
    )
    parser.add_argument(
        "--force-constituents",
        action="store_true",
        help="重新联网取得固定修订并再次核验 HTML/Symbol 哈希",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="仅续跑前 N 个尚未合格的证券；用于约两分钟一批的运行",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    args = _parse_args(argv)
    try:
        result = run_download(
            symbols=args.symbols,
            batch_size=args.batch_size,
            force_constituents=args.force_constituents,
        )
    except DownloadPaused as exc:
        print(f"下载暂停: {exc}", file=sys.stderr)
        return 75
    except Exception as exc:
        print(f"下载失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
