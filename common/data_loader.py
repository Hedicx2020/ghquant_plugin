"""
Common data loading utilities.

Provides functions to load market data, construct stock universes,
and filter ST / suspended stocks from local parquet files.

v3 新增（文件末尾一节）：统一取数入口 ``data_path()`` / ``read_table()``、结果目录
``results_dir()`` 与运行期数据清单 ``write_data_manifest()``。新案例的代码一律经它们
取数和落盘，试跑模式（mock）下自动改读本案例的覆盖目录、改写试跑结果目录，
策略代码不用为 mock 写分支。上面的 ``load_*`` 函数保持旧行为。
"""

from __future__ import annotations

import atexit
import functools
import json
import operator
import os
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd


def get_data_root() -> Path:
    """解析本地数据根目录。

    优先级：从当前工作目录向上就近查找 `.reproduce.json` 的 `data_root` 字段
    （插件形态下由 /reproduce setup 生成）；未找到或字段缺失时回退
    `~/local_data`（与历史行为一致）。
    """
    for directory in [Path.cwd(), *Path.cwd().parents]:
        cfg = directory / ".reproduce.json"
        if cfg.is_file():
            try:
                raw_config = cfg.read_text(encoding="utf-8")
            except OSError as exc:
                raise RuntimeError(f"无法读取复现配置文件: {cfg.resolve()}") from exc
            try:
                config = json.loads(raw_config)
            except json.JSONDecodeError as exc:
                raise ValueError(f"复现配置JSON格式损坏: {cfg.resolve()}") from exc
            if not isinstance(config, dict):
                raise ValueError(f"复现配置顶层必须为JSON对象: {cfg.resolve()}")
            data_root = config.get("data_root")
            if data_root:
                if not isinstance(data_root, str):
                    raise ValueError(
                        f"复现配置data_root必须为非空字符串: {cfg.resolve()}"
                    )
                return Path(data_root).expanduser()
            # 为保持 /reproduce setup 既有兼容性：最近配置合法但字段缺失/空值时
            # 直接采用历史默认目录，不继续向上搜索另一份配置。
            return Path.home() / "local_data"
    # 只有从 cwd 向上完全找不到配置文件时才走默认目录。
    return Path.home() / "local_data"


# Default local data directory（模块加载时解析一次；函数默认参数在 def 时绑定，
# 行为与旧版模块级常量一致）
LOCAL_DATA_DIR = get_data_root()


# ---------------------------------------------------------------------------
# Core loaders
# ---------------------------------------------------------------------------

def load_stock_price(
    data_dir: Path = LOCAL_DATA_DIR,
    columns: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Load daily stock price data.

    Args:
        data_dir: Root directory of parquet files.
        columns: Subset of columns to load; None for all.

    Returns:
        DataFrame with columns [stock_code, date, prev_close, close, open,
        high, low, ...].
    """
    path = data_dir / "ashare_stock_price.parquet"
    df = pd.read_parquet(path, columns=columns)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_stock_price_forward(
    data_dir: Path = LOCAL_DATA_DIR,
    columns: Optional[Sequence[str]] = None,
    stock_codes: Optional[Sequence[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Load **forward-adjusted** (前复权) daily stock price data.

    与 :func:`load_stock_price`（未复权）平行；回测算收益优先用前复权 close
    （复权因子已滚入价格序列，相邻日 close 的对数差分即连续可比的日对数收益）。
    支持 pyarrow filters 下推（按 stock_code / date）以减少读盘。

    Args:
        data_dir: Root directory of parquet files.
        columns: Subset of columns to load; None for all.
        stock_codes: 可选，仅加载这些代码（filters 下推）。
        start_date: 可选，仅加载不早于此日期的记录（filters 下推）。
        end_date: 可选，仅加载不晚于此日期的记录（filters 下推）。

    Returns:
        DataFrame with columns [stock_code, date, adj_factor, prev_close,
        close, open, high, low, ...]（依 ``columns`` 而定）。
    """
    filters: list = []
    if start_date is not None:
        filters.append(("date", ">=", pd.Timestamp(start_date)))
    if end_date is not None:
        filters.append(("date", "<=", pd.Timestamp(end_date)))
    if stock_codes is not None:
        filters.append(("stock_code", "in", list(stock_codes)))
    path = data_dir / "ashare_stock_price_forward.parquet"
    df = pd.read_parquet(path, columns=columns, filters=filters or None)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_stock_trade(
    data_dir: Path = LOCAL_DATA_DIR,
    columns: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Load daily stock trade data (returns, turnover, market cap, etc.).

    Args:
        data_dir: Root directory.
        columns: Subset of columns.

    Returns:
        DataFrame with columns [stock_code, date, change_pct, range_pct,
        market_value, negotiable_market_value, turnover_rate, ...].
    """
    path = data_dir / "ashare_stock_trade.parquet"
    df = pd.read_parquet(path, columns=columns)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_suspend(data_dir: Path = LOCAL_DATA_DIR) -> pd.DataFrame:
    """Load daily suspend status.

    Returns:
        DataFrame with [stock_code, date, ifsuspend].
    """
    path = data_dir / "ashare_suspend.parquet"
    df = pd.read_parquet(path, columns=["stock_code", "date", "ifsuspend"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_st_data(data_dir: Path = LOCAL_DATA_DIR) -> pd.DataFrame:
    """Load ST status records.

    Returns:
        DataFrame with [stock_code, implement_date, remove_date].
    """
    path = data_dir / "ashare_stock_st.parquet"
    df = pd.read_parquet(path, columns=["stock_code", "implement_date", "remove_date"])
    df["implement_date"] = pd.to_datetime(df["implement_date"])
    df["remove_date"] = pd.to_datetime(df["remove_date"])
    return df


def load_industry(
    data_dir: Path = LOCAL_DATA_DIR,
    standard_code: int = 37,
) -> pd.DataFrame:
    """Load industry classification (default: CITICS level-1, code=37).

    Args:
        data_dir: Root directory.
        standard_code: 37 for CITICS (中信一级), 38 for Shenwan (申万一级).

    Returns:
        DataFrame with [stock_code, first_industry_name].
    """
    path = data_dir / "ashare_stock_industry.parquet"
    df = pd.read_parquet(path)
    df = df.loc[df["standard_code"] == standard_code, ["stock_code", "first_industry_name"]]
    return df.drop_duplicates(subset=["stock_code"]).reset_index(drop=True)


def load_trade_calendar(
    data_dir: Path = LOCAL_DATA_DIR,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Load trade calendar.

    Args:
        data_dir: Root directory.
        start_date: Start date filter (inclusive).
        end_date: End date filter (inclusive).

    Returns:
        DataFrame with [date, IfTradingDay, IfMonthEnd, ...].
    """
    path = data_dir / "ashare_tradeday.parquet"
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"])
    # Filter to trading days in SecuMarket 83 (Shanghai) or 90 (both)
    df = df[df["IfTradingDay"] == 1]
    if start_date:
        df = df[df["date"] >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df["date"] <= pd.Timestamp(end_date)]
    return df.sort_values("date").reset_index(drop=True)


def load_index_components(
    index_code: str,
    data_dir: Path = LOCAL_DATA_DIR,
) -> pd.DataFrame:
    """Load index component history.

    Args:
        index_code: e.g. '000300' for CSI 300.
        data_dir: Root directory.

    Returns:
        DataFrame with [stock_code, in_date, out_date].
    """
    path = data_dir / "ashare_index_components.parquet"
    df = pd.read_parquet(path)
    df = df[df["index_code"] == index_code][["stock_code", "in_date", "out_date"]].copy()
    df["in_date"] = pd.to_datetime(df["in_date"])
    df["out_date"] = pd.to_datetime(df["out_date"])
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Stock universe helpers
# ---------------------------------------------------------------------------

def get_month_end_trading_days(
    start_date: str,
    end_date: str,
    data_dir: Path = LOCAL_DATA_DIR,
) -> pd.DatetimeIndex:
    """Get month-end trading days within [start_date, end_date].

    Args:
        start_date: Start date.
        end_date: End date.
        data_dir: Root directory.

    Returns:
        DatetimeIndex of month-end trading days.
    """
    cal = load_trade_calendar(data_dir, start_date, end_date)
    month_ends = cal[cal["IfMonthEnd"] == 1]["date"]
    return pd.DatetimeIndex(month_ends.values)


def filter_st_stocks(
    stock_codes: pd.Series,
    date: pd.Timestamp,
    st_data: pd.DataFrame,
) -> pd.Index:
    """Return stock codes that are NOT in ST status on the given date.

    Args:
        stock_codes: Series or Index of stock codes.
        date: Reference date.
        st_data: ST records from load_st_data().

    Returns:
        Index of non-ST stock codes.
    """
    st_on_date = st_data[
        (st_data["implement_date"] <= date)
        & ((st_data["remove_date"] > date) | st_data["remove_date"].isna())
    ]["stock_code"].unique()
    codes = pd.Index(stock_codes)
    return codes.difference(pd.Index(st_on_date))


def filter_suspended(
    panel: pd.DataFrame,
    suspend_data: pd.DataFrame,
    stock_col: str = "stock_code",
    date_col: str = "date",
) -> pd.DataFrame:
    """Remove rows where the stock is suspended on that date.

    Args:
        panel: Panel DataFrame.
        suspend_data: Suspend status data.
        stock_col: Stock code column.
        date_col: Date column.

    Returns:
        Filtered DataFrame.
    """
    merged = panel.merge(
        suspend_data[[stock_col, date_col, "ifsuspend"]],
        on=[stock_col, date_col],
        how="left",
    )
    return merged[merged["ifsuspend"] != 1].drop(columns=["ifsuspend"])


def get_stock_universe(
    date: pd.Timestamp,
    panel: pd.DataFrame,
    st_data: pd.DataFrame,
    index_code: Optional[str] = None,
    index_components: Optional[pd.DataFrame] = None,
    stock_col: str = "stock_code",
    date_col: str = "date",
) -> pd.Index:
    """Get investable stock universe on a given date.

    Filters: non-ST, non-suspended (caller should have already removed
    suspended rows from panel).  Optionally restricts to index members.

    Args:
        date: Reference date.
        panel: Panel data (already filtered for the date).
        st_data: ST records.
        index_code: Optional index code for restricting to members.
        index_components: Pre-loaded index component data.
        stock_col: Stock code column.
        date_col: Date column.

    Returns:
        Index of valid stock codes.
    """
    day_data = panel[panel[date_col] == date]
    codes = day_data[stock_col].unique()

    # Filter ST
    codes = filter_st_stocks(pd.Series(codes), date, st_data)

    # Filter to index members if requested
    if index_code and index_components is not None:
        members = index_components[
            (index_components["in_date"] <= date)
            & ((index_components["out_date"] > date) | index_components["out_date"].isna())
        ]["stock_code"].unique()
        codes = codes.intersection(pd.Index(members))

    return codes


def load_market_data(
    start_date: str,
    end_date: str,
    data_dir: Path = LOCAL_DATA_DIR,
    price_cols: Optional[Sequence[str]] = None,
    trade_cols: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """Load and merge price + trade data for the given period.

    Args:
        start_date: Start date (inclusive).
        end_date: End date (inclusive).
        data_dir: Root directory.
        price_cols: Price columns to keep.
        trade_cols: Trade columns to keep.

    Returns:
        Merged DataFrame with both price and trade fields.
    """
    # Default columns
    if price_cols is None:
        price_cols = ["stock_code", "date", "prev_close", "close", "open", "high", "low"]
    if trade_cols is None:
        trade_cols = [
            "stock_code", "date", "change_pct", "range_pct",
            "market_value", "negotiable_market_value", "turnover_rate",
        ]

    price = load_stock_price(data_dir, columns=list(price_cols))
    trade = load_stock_trade(data_dir, columns=list(trade_cols))

    # Date filter -- include extra lookback buffer (400 days before start)
    buffer_start = pd.Timestamp(start_date) - pd.DateOffset(days=400)
    price = price[(price["date"] >= buffer_start) & (price["date"] <= pd.Timestamp(end_date))]
    trade = trade[(trade["date"] >= buffer_start) & (trade["date"] <= pd.Timestamp(end_date))]

    merged = price.merge(trade, on=["stock_code", "date"], how="inner")
    return merged.sort_values(["stock_code", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Point-in-time index membership & tradability status（通用；供时点成分/状态过滤复用）
# ---------------------------------------------------------------------------

def get_index_members_on_date(
    components: pd.DataFrame,
    date: pd.Timestamp,
) -> pd.Index:
    """某一时点的指数在册成分股（时点成分，防幸存者偏差）。

    判定区间为半开 [in_date, out_date)：out_date 为空表示当前仍在册。

    Args:
        components: ``load_index_components()`` 的返回，含 [stock_code, in_date, out_date]。
        date: 参照时点（通常为再平衡月末日）。

    Returns:
        该时点在册成分股代码 Index（去重）。
    """
    on = components[
        (components["in_date"] <= date)
        & ((components["out_date"] > date) | components["out_date"].isna())
    ]
    return pd.Index(on["stock_code"].unique())


def _range_code_filters(
    stock_codes: Optional[Sequence[str]],
    start_date: Optional[str],
) -> Optional[list]:
    """构造 pyarrow read_parquet 的下推 filters（date>=start 与 stock_code in codes）。"""
    filters: list = []
    if start_date is not None:
        filters.append(("date", ">=", pd.Timestamp(start_date)))
    if stock_codes is not None:
        filters.append(("stock_code", "in", list(stock_codes)))
    return filters or None


def load_suspend_status(
    data_dir: Path = LOCAL_DATA_DIR,
    stock_codes: Optional[Sequence[str]] = None,
    start_date: Optional[str] = None,
) -> pd.DataFrame:
    """加载停牌状态（文件 ashare_stock_suspend.parquet，字段 if_suspend）。

    注：本函数为 ``load_suspend`` 的字段/文件名修正版（后者读的
    ``ashare_suspend.parquet`` / ``ifsuspend`` 与本地实际不符）。

    Args:
        data_dir: 数据根目录。
        stock_codes: 可选，仅加载这些代码（filters 下推，减少读盘）。
        start_date: 可选，仅加载不早于此日期的记录（filters 下推）。

    Returns:
        DataFrame[stock_code, date, if_suspend]；if_suspend==1 表示当日停牌。
    """
    path = data_dir / "ashare_stock_suspend.parquet"
    df = pd.read_parquet(
        path, columns=["stock_code", "date", "if_suspend"],
        filters=_range_code_filters(stock_codes, start_date),
    )
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_limit_status(
    data_dir: Path = LOCAL_DATA_DIR,
    stock_codes: Optional[Sequence[str]] = None,
    start_date: Optional[str] = None,
) -> pd.DataFrame:
    """加载个股涨跌停标记（文件 ashare_stock_limit.parquet）。

    Args:
        data_dir: 数据根目录。
        stock_codes: 可选，仅加载这些代码（filters 下推）。
        start_date: 可选，仅加载不早于此日期的记录（filters 下推）。

    Returns:
        DataFrame[stock_code, date, surged_limit, decline_limit]；
        surged_limit==1 涨停（当日难以按意愿买入）、decline_limit==1 跌停
        （当日难以按意愿卖出）。
    """
    path = data_dir / "ashare_stock_limit.parquet"
    df = pd.read_parquet(
        path, columns=["stock_code", "date", "surged_limit", "decline_limit"],
        filters=_range_code_filters(stock_codes, start_date),
    )
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# v3：试跑模式（mock 覆盖目录）、统一取数入口、结果目录与运行期数据清单
# ---------------------------------------------------------------------------
#
# 约定（方案见 docs/specs/2026-11-21-reproduce-v3-design.md 第 4.5 节）：
#   - 案例 <report_id> 下有标记文件 workspace/<report_id>/data_mock/ACTIVE 时处于「试跑
#     模式」：data_path() 先查覆盖目录 workspace/<report_id>/data_mock/files/，没有才回到
#     数据根；results_dir() 返回 output/<report_id>/results_mock/。
#   - report_id 的来源：显式参数 > 环境变量 REPRODUCE_REPORT_ID > 无。无时永远不是试跑
#     模式，行为等同直接读数据根。
#   - 环境变量 REPRODUCE_TRIAL 为 1 / 0 时覆盖标记文件的判断（测试用）。
#   - 案例根目录：环境变量 REPORT_REPRODUCE_ROOT 存在时直接用它；否则从当前工作目录向上
#     找第一个含 workspace/<report_id>/ 的目录。
#   - 经 data_path() 解析过的文件都记进进程内的登记表，进程退出时自动写成
#     data_manifest.json：读了哪些文件、各自是真实还是 mock、文件指纹、起止时间。
# 这一节不导入 tools/ 下的任何模块（common/ 会被拷到用户目录独立运行），数据根一律在
# 调用时取 get_data_root()，不用模块加载时就定死的 LOCAL_DATA_DIR。

_ROOT_ENV = "REPORT_REPRODUCE_ROOT"
_REPORT_ID_ENV = "REPRODUCE_REPORT_ID"
_TRIAL_ENV = "REPRODUCE_TRIAL"
_MOCK_DIR = "data_mock"
_MOCK_ACTIVE = "ACTIVE"
_MOCK_FILES = "files"
DATA_MANIFEST_NAME = "data_manifest.json"
_TZ_CN = timezone(timedelta(hours=8))

# 自动识别日期列时的查找顺序（排在前面的优先）。与 tools/flowlib/datacheck.py 的
# DATE_COLUMNS 保持一致；这里不能从 tools/ 导入，所以抄一份。
_DATE_COLUMN_CANDIDATES: tuple[str, ...] = (
    "date", "trade_dt", "trade_date", "trading_day", "cal_date", "TradingDay",
    "end_date", "report_date", "info_publ_date", "publ_date", "ann_date",
)
# csv / xlsx 不带列类型，这些证券代码列一律按文本读入（保住 000001 这样的前导零）
_TEXT_CODE_COLUMNS: tuple[str, ...] = (
    "stock_code", "stcode", "secu_code", "ts_code", "symbol", "ticker",
    "index_code", "fund_code", "bond_code", "contract_code", "option_code",
)
_ISO_DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_INDEX_LEVEL_RE = re.compile(r"__index_level_(\d+)__")  # pandas 把没有名字的索引存成这样的列
_COMPACT_DAY_RE = re.compile(r"\d{8}")
_YYYYMMDD_MIN, _YYYYMMDD_MAX = 19000101, 22001231

_MANIFEST_LOCK = threading.Lock()
_MANIFEST_FILES: dict[str, dict[str, Any]] = {}  # 绝对路径 → 登记项（按首次登记的先后）
_MANIFEST_STATE: dict[str, Any] = {"started_at": None, "report_id": None, "atexit": False}


def _now_iso() -> str:
    """ISO8601 时间戳，固定带 +08:00 偏移（与 tools/state.py 的写法一致）。"""
    return datetime.now(_TZ_CN).isoformat(timespec="seconds")


_LOADED_AT = _now_iso()  # 登记表为空时拿它当运行的起点


def _resolve_report_id(report_id: Optional[str]) -> Optional[str]:
    """report_id 的来源：显式参数 > 环境变量 REPRODUCE_REPORT_ID > None。"""
    rid = (report_id or os.environ.get(_REPORT_ID_ENV) or "").strip()
    if not rid:
        return None
    if rid in (".", "..") or "/" in rid or "\\" in rid:
        raise ValueError(f"report_id 不能含路径分隔符: {rid!r}")
    return rid


def _case_root(report_id: str) -> Optional[Path]:
    """案例所在的工作区根目录；定位不到返回 None。"""
    override = os.environ.get(_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    cwd = Path.cwd()
    return next((d for d in (cwd, *cwd.parents) if (d / "workspace" / report_id).is_dir()), None)


def is_trial(report_id: Optional[str] = None) -> bool:
    """这个案例是否处于试跑模式（数据里掺了 mock，这一轮只算试跑、不出结论）。

    判定：存在标记文件 ``workspace/<report_id>/data_mock/ACTIVE``；环境变量
    ``REPRODUCE_TRIAL`` 为 ``1`` / ``0`` 时以它为准（测试用）。解析不出 report_id 时
    永远返回 False。标记文件由内核创建和删除，策略代码与 mock 生成器都不碰它。

    Args:
        report_id: 案例编号；不给时取环境变量 ``REPRODUCE_REPORT_ID``。

    Returns:
        是否处于试跑模式。
    """
    rid = _resolve_report_id(report_id)
    if rid is None:
        return False
    forced = os.environ.get(_TRIAL_ENV, "").strip()
    if forced in ("0", "1"):
        return forced == "1"
    root = _case_root(rid)
    return root is not None and (root / "workspace" / rid / _MOCK_DIR / _MOCK_ACTIVE).is_file()


def _relative_name(name: Any) -> Path:
    """把 name 规整成相对数据根的路径；绝对路径和带 .. 的写法一律拒绝。"""
    text = os.fspath(name)
    rel = Path(text)
    if not text or not rel.parts or rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"name 必须是相对数据根的路径（不能是绝对路径，也不能含 ..）: {text!r}")
    return rel


def _file_stat(path: Path) -> dict[str, Any]:
    """文件大小、修改时间和指纹（<字节数>-<mtime 纳秒>）；文件不存在时三项都是 None。"""
    try:
        stat = path.stat()
    except OSError:
        return {"size": None, "mtime": None, "fingerprint": None}
    return {
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, _TZ_CN).isoformat(timespec="seconds"),
        "fingerprint": f"{stat.st_size}-{stat.st_mtime_ns}",
    }


def _register_data_file(name: str, path: Path, source: str, report_id: Optional[str]) -> None:
    """把一次解析记进登记表。同一路径只记一次；首次登记时顺带注册退出时的自动写出。"""
    key = str(path)
    with _MANIFEST_LOCK:
        entry = _MANIFEST_FILES.get(key)
        if entry is None:
            if _MANIFEST_STATE["started_at"] is None:
                _MANIFEST_STATE["started_at"] = _now_iso()
            _MANIFEST_FILES[key] = {"name": name, "path": key, "source": source, **_file_stat(path)}
        elif entry["fingerprint"] is None:
            entry.update(_file_stat(path))  # 首次登记时文件还不存在、后来才有：补上指纹
        if report_id is not None and _MANIFEST_STATE["report_id"] is None:
            _MANIFEST_STATE["report_id"] = report_id
        if not _MANIFEST_STATE["atexit"]:
            atexit.register(_write_data_manifest_at_exit)
            _MANIFEST_STATE["atexit"] = True


def data_path(name: str, report_id: Optional[str] = None) -> Path:
    """把数据根相对路径解析成实际要读的文件：试跑模式下先查本案例的覆盖目录。

    试跑模式下若 ``workspace/<report_id>/data_mock/files/<name>`` 这个文件存在就返回它
    （来源记为 mock），否则返回 ``get_data_root() / name``（来源记为 real）。覆盖按文件
    生效：name 是目录时一律回到数据根，不会因为覆盖目录里有同名子目录就整体替换。真实
    文件不存在时照样返回路径，由调用方报错。每次调用把（name、绝对路径、来源、文件大小、
    修改时间）记进进程内的登记表，同一路径只记一次；登记表见 :func:`write_data_manifest`。

    Args:
        name: 相对数据根的路径，如 ``ashare_stock_price.parquet`` 或 ``factors/x.parquet``。
        report_id: 案例编号；不给时取环境变量 ``REPRODUCE_REPORT_ID``，都没有就只读数据根。

    Returns:
        解析出的绝对路径。

    Raises:
        ValueError: name 是绝对路径或含 ``..``。
    """
    rel = _relative_name(name)
    rid = _resolve_report_id(report_id)
    source, path = "real", get_data_root() / rel
    if rid is not None and is_trial(rid):
        root = _case_root(rid)
        mock = None if root is None else root / "workspace" / rid / _MOCK_DIR / _MOCK_FILES / rel
        if mock is not None and mock.is_file():  # 覆盖按文件生效，目录不整体替换
            source, path = "mock", mock
    path = Path(os.path.abspath(path))
    _register_data_file(rel.as_posix(), path, source, rid)
    return path


def _to_timestamp(value: Any, label: str) -> Optional[pd.Timestamp]:
    """把 start / end 规整成时间戳；``20200102`` 这样的整数或文本按 YYYYMMDD 认。"""
    if value is None:
        return None
    try:
        if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
            value = str(int(value))
            if not _COMPACT_DAY_RE.fullmatch(value):
                raise ValueError("整数日期必须是 YYYYMMDD")
        if isinstance(value, str) and _COMPACT_DAY_RE.fullmatch(value.strip()):
            stamp = pd.to_datetime(value.strip(), format="%Y%m%d")
        else:
            stamp = pd.Timestamp(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{label} 不是有效日期: {value!r}") from exc
    if stamp is pd.NaT:
        raise ValueError(f"{label} 不是有效日期: {value!r}")
    return stamp


def _align_tz(stamp: pd.Timestamp, tz: Any) -> pd.Timestamp:
    """让比较值与日期列的时区一致：列不带时区就去掉时区，带时区就换算到那个时区。"""
    if tz is None:
        return stamp.tz_localize(None) if stamp.tzinfo is not None else stamp
    return stamp.tz_localize(tz) if stamp.tzinfo is None else stamp.tz_convert(tz)


def _require_columns(name: str, available: Sequence[str], wanted: Optional[Sequence[str]]) -> None:
    missing = [c for c in wanted or [] if c not in available]
    if missing:
        raise ValueError(f"表 {name} 缺少列: {missing}")


def _pick_date_col(name: str, available: Sequence[str], date_col: Optional[str]) -> str:
    """给了 date_col 就用它，没给就按常见日期列名找；找不到抛 ValueError。"""
    if date_col is not None:
        if date_col not in available:
            raise ValueError(f"表 {name} 里没有日期列 {date_col}")
        return date_col
    found = next((c for c in _DATE_COLUMN_CANDIDATES if c in available), None)
    if found is None:
        raise ValueError(
            f"表 {name} 里找不到日期列（按常见列名找过: {', '.join(_DATE_COLUMN_CANDIDATES)}），"
            "要按 start / end 过滤请用 date_col 指定"
        )
    return found


def _is_yyyymmdd(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        return False
    number = int(value)
    return _YYYYMMDD_MIN <= number <= _YYYYMMDD_MAX and 1 <= number // 100 % 100 <= 12 and 1 <= number % 100 <= 31


def _text_date_format(values: Sequence[Any]) -> Optional[str]:
    """文本日期列的写法：全是 2020-01-02 或全是 20200102 才认（字典序才等于时间序）。"""
    if not values or not all(isinstance(v, str) for v in values):
        return None
    if all(_ISO_DAY_RE.fullmatch(v) for v in values):
        return "%Y-%m-%d"
    if all(_COMPACT_DAY_RE.fullmatch(v) for v in values):
        return "%Y%m%d"
    return None


def _sample_date_values(parquet_file: Any, col: str, limit: int = 2000) -> list[Any]:
    """取各行组统计信息里的最小、最大值，外加开头的一小批值，用来判断日期的写法。

    只读元数据和第一批数据。任何一个行组没有统计信息就返回空列表（放弃下推）。
    """
    meta = parquet_file.metadata
    if not meta.num_row_groups:
        return []
    first = meta.row_group(0)
    index = next((i for i in range(first.num_columns) if first.column(i).path_in_schema == col), None)
    if index is None:
        return []
    stats = [meta.row_group(g).column(index).statistics for g in range(meta.num_row_groups)]
    if any(s is None or not s.has_min_max for s in stats):
        return []
    batch = next(parquet_file.iter_batches(batch_size=limit, columns=[col]), None)
    head = [] if batch is None else [v for v in batch.column(0).to_pylist() if v is not None]
    values = [v for s in stats for v in (s.min, s.max)] + head
    return [v.decode("utf-8", "replace") if isinstance(v, bytes) else v for v in values]


def _timestamp_bound(stamp: pd.Timestamp, arrow_type: Any, round_up: bool) -> Any:
    """把比较值换成与时间戳列同单位、同时区的 arrow 标量（下界向上取整，上界向下取整）。"""
    import pyarrow as pa

    aligned = _align_tz(stamp, arrow_type.tz)
    aligned = aligned.ceil(arrow_type.unit) if round_up else aligned.floor(arrow_type.unit)
    if arrow_type.unit == "ns":
        return pa.scalar(aligned.value, type=pa.int64()).cast(arrow_type)
    return pa.scalar(aligned.to_pydatetime(), type=arrow_type)


def _native_date_bounds(parquet_file: Any, col: str, lo: Optional[pd.Timestamp], hi: Optional[pd.Timestamp]) -> Optional[tuple[Any, Any]]:
    """按日期列的实际类型换算比较值；换算不了返回 None（读入后再过滤）。

    日期列按「当天零点」理解：下界带时分秒时向上取到下一天，上界向下取到当天。
    """
    import pyarrow as pa

    arrow_type = parquet_file.schema_arrow.field(col).type
    if pa.types.is_timestamp(arrow_type):
        return (
            None if lo is None else _timestamp_bound(lo, arrow_type, round_up=True),
            None if hi is None else _timestamp_bound(hi, arrow_type, round_up=False),
        )
    low_day = None if lo is None else _align_tz(lo, None).ceil("D")
    high_day = None if hi is None else _align_tz(hi, None).floor("D")
    if pa.types.is_date(arrow_type):
        return (
            None if low_day is None else pa.scalar(low_day.date(), type=arrow_type),
            None if high_day is None else pa.scalar(high_day.date(), type=arrow_type),
        )
    is_text = pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type)
    if not (is_text or pa.types.is_integer(arrow_type)):
        return None
    samples = _sample_date_values(parquet_file, col)
    fmt = _text_date_format(samples) if is_text else ("%Y%m%d" if samples and all(map(_is_yyyymmdd, samples)) else None)
    if fmt is None:
        return None
    convert = (lambda day: day.strftime(fmt)) if is_text else (lambda day: int(day.strftime(fmt)))
    return (None if low_day is None else convert(low_day), None if high_day is None else convert(high_day))


def _date_pushdown(parquet_file: Any, col: str, lo: Optional[pd.Timestamp], hi: Optional[pd.Timestamp]) -> Any:
    """日期范围对应的 pyarrow 过滤表达式；下推不了返回 None。"""
    import pyarrow as pa
    import pyarrow.compute as pc

    try:
        bounds = _native_date_bounds(parquet_file, col, lo, hi)
    except (ValueError, TypeError, ArithmeticError, pa.ArrowException):
        return None
    if bounds is None:
        return None
    field = pc.field(col)
    terms = ([] if bounds[0] is None else [field >= bounds[0]]) + ([] if bounds[1] is None else [field <= bounds[1]])
    return functools.reduce(operator.and_, terms)


def _parse_date_values(values: pd.Series, label: str) -> pd.Series:
    """把一组互不相同的日期值解析成时间戳；认不出来的记为 NaT。"""
    kind = pd.api.types.infer_dtype(values, skipna=True)
    if kind in ("datetime", "datetime64", "date"):
        return pd.to_datetime(values, errors="coerce")
    if kind in ("integer", "floating", "mixed-integer-float", "decimal"):
        numbers = pd.to_numeric(values, errors="coerce")
        valid = (
            numbers.notna() & (numbers % 1 == 0) & numbers.between(_YYYYMMDD_MIN, _YYYYMMDD_MAX)
            & (numbers // 100 % 100).between(1, 12) & (numbers % 100).between(1, 31)
        )
        if valid.mean() <= 0.5:
            raise ValueError(f"日期列 {label} 是数值但不是 YYYYMMDD 的写法，无法按日期过滤")
        text = numbers.where(valid).astype("Int64").astype("string")
        return pd.to_datetime(text, format="%Y%m%d", errors="coerce")
    text = values.astype(str).str.strip()
    compact = text.str.fullmatch(_COMPACT_DAY_RE.pattern).to_numpy(dtype=bool)
    parsed = pd.to_datetime(text.where(compact), format="%Y%m%d", errors="coerce")
    if compact.all():
        return parsed
    # 写法不统一时逐个解析（值已去重，量很小），认不出来的记为 NaT
    others = pd.to_datetime(text.where(~compact), format="mixed", errors="coerce")
    if not pd.api.types.is_datetime64_any_dtype(others.dtype):
        raise ValueError(f"日期列 {label} 的写法无法解析，无法按日期过滤")
    return parsed.fillna(others)


def _as_datetime(values: pd.Series, label: str) -> pd.Series:
    """把一列日期（时间戳 / 文本 / YYYYMMDD 整数 / date 对象）转成时间戳列，只解析去重后的值。"""
    if pd.api.types.is_datetime64_any_dtype(values.dtype):
        return values
    if isinstance(values.dtype, pd.CategoricalDtype):
        values = values.astype(object)
    unique = pd.Series(pd.unique(values.dropna()))
    if unique.empty:
        return pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    lookup = pd.Series(_parse_date_values(unique, label).to_numpy(), index=unique.to_numpy())
    return values.map(lookup)


def _column_values(df: pd.DataFrame, col: str) -> pd.Series:
    """按列名取一列；这一列被 pandas 存成了索引（读回来不在 columns 里）时从索引里取。"""
    if col in df.columns:
        return df[col]
    level = _INDEX_LEVEL_RE.fullmatch(col)
    return pd.Series(df.index.get_level_values(int(level.group(1)) if level else col), index=df.index)


def _filter_by_date(df: pd.DataFrame, col: str, lo: Optional[pd.Timestamp], hi: Optional[pd.Timestamp], name: str) -> pd.DataFrame:
    """读入后按日期范围过滤（含两端）；日期为空或认不出来的行不保留。"""
    when = _as_datetime(_column_values(df, col), f"{name}.{col}")
    tz = getattr(when.dt, "tz", None)
    keep = np.ones(len(df), dtype=bool)
    if lo is not None:
        keep &= (when >= _align_tz(lo, tz)).to_numpy(dtype=bool)
    if hi is not None:
        keep &= (when <= _align_tz(hi, tz)).to_numpy(dtype=bool)
    return df.loc[keep]


_FILTER_OPS: dict[str, Any] = {
    "=": operator.eq,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
    "in": lambda column, value: column.isin(list(value)),
    "not in": lambda column, value: ~column.isin(list(value)),
}


def _term_mask(df: pd.DataFrame, term: Sequence[Any]) -> np.ndarray:
    """一个 (列, 比较符, 值) 条件对应的布尔掩码；与 pyarrow 一样，空值不满足任何比较。"""
    column, op, value = term
    if column not in df.columns:
        raise ValueError(f"filters 用到的列不存在: {column}")
    if op not in _FILTER_OPS:
        raise ValueError(f"filters 不支持的比较符: {op!r}")
    matched = pd.Series(_FILTER_OPS[op](df[column], value)).fillna(False).to_numpy(dtype=bool)
    return matched if op in ("in", "not in") else matched & df[column].notna().to_numpy()


def _apply_filters(df: pd.DataFrame, filters: Any) -> pd.DataFrame:
    """对已读入的表套用 pyarrow 风格的 filters（非 parquet 文件没有下推可用）。"""
    if isinstance(filters, (list, tuple)):
        if not filters:
            return df
        groups = filters if isinstance(filters[0], list) else [filters]
        every = np.ones(len(df), dtype=bool)
        masks = (functools.reduce(np.logical_and, (_term_mask(df, term) for term in group), every) for group in groups)
        return df.loc[functools.reduce(np.logical_or, masks)]
    import pyarrow as pa

    table = pa.Table.from_pandas(df, preserve_index=False).append_column("__row__", pa.array(np.arange(len(df))))
    return df.iloc[table.filter(filters).column("__row__").to_numpy()]


def _filters_to_expression(filters: Any) -> Any:
    """把 pyarrow 风格的 filters（元组列表 / 列表的列表 / 表达式）统一成表达式；空的返回 None。"""
    if filters is None or (isinstance(filters, (list, tuple)) and not filters):
        return None
    if isinstance(filters, (list, tuple)):
        import pyarrow.parquet as pq

        return pq.filters_to_expression(filters)
    return filters


def _tidy_index(result: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    """读入后再过滤的结果：原表是默认行号时重排成 0..n-1，与下推读出来的一致。"""
    return result.reset_index(drop=True) if isinstance(source.index, pd.RangeIndex) else result


def _read_parquet_table(
    path: Path,
    name: str,
    columns: Optional[list[str]],
    lo: Optional[pd.Timestamp],
    hi: Optional[pd.Timestamp],
    date_col: Optional[str],
    filters: Any,
) -> pd.DataFrame:
    import pyarrow.parquet as pq

    user_filter = _filters_to_expression(filters)
    with pq.ParquetFile(path) as parquet_file:
        available = list(parquet_file.schema_arrow.names)
        _require_columns(name, available, columns)
        if lo is None and hi is None:
            return pd.read_parquet(path, columns=columns, filters=user_filter)
        col = _pick_date_col(name, available, date_col)
        date_filter = _date_pushdown(parquet_file, col, lo, hi)
    if date_filter is not None:
        combined = date_filter if user_filter is None else user_filter & date_filter
        return pd.read_parquet(path, columns=columns, filters=combined)
    # 日期列的类型或写法下推不了：连日期列一起读进来，过滤完再裁列
    read_cols = None if columns is None else list(dict.fromkeys([*columns, col]))
    full = pd.read_parquet(path, columns=read_cols, filters=user_filter)
    kept = _filter_by_date(full, col, lo, hi, name)
    # 被存成索引的列读回来在索引里，不在 columns 里：裁列时略过，和下推读出来的形状一致
    return _tidy_index(kept if columns is None else kept[[c for c in columns if c in kept.columns]], full)


def _read_csv(path: Path) -> pd.DataFrame:
    def read(encoding: str) -> pd.DataFrame:
        header = pd.read_csv(path, nrows=0, encoding=encoding).columns
        return pd.read_csv(path, dtype={c: str for c in header if c in _TEXT_CODE_COLUMNS}, encoding=encoding)

    try:
        return read("utf-8-sig")
    except UnicodeDecodeError:
        return read("gb18030")


def _read_excel(path: Path) -> pd.DataFrame:
    header = pd.read_excel(path, nrows=0).columns
    return pd.read_excel(path, dtype={c: str for c in header if c in _TEXT_CODE_COLUMNS})


_FLAT_READERS: dict[str, Any] = {".csv": _read_csv, ".feather": pd.read_feather, ".xlsx": _read_excel}


def _read_flat_table(
    path: Path,
    name: str,
    columns: Optional[list[str]],
    lo: Optional[pd.Timestamp],
    hi: Optional[pd.Timestamp],
    date_col: Optional[str],
    filters: Any,
) -> pd.DataFrame:
    """csv / feather / xlsx：整表读入后再过滤、裁列。"""
    full = _FLAT_READERS[path.suffix.lower()](path)
    available = list(full.columns)
    _require_columns(name, available, columns)
    kept = full
    if lo is not None or hi is not None:
        kept = _filter_by_date(kept, _pick_date_col(name, available, date_col), lo, hi, name)
    if filters is not None:
        kept = _apply_filters(kept, filters)
    return _tidy_index(kept if columns is None else kept[columns], full)


def read_table(
    name: str,
    columns: Optional[Sequence[str]] = None,
    start: Any = None,
    end: Any = None,
    date_col: Optional[str] = None,
    report_id: Optional[str] = None,
    filters: Any = None,
) -> pd.DataFrame:
    """经 :func:`data_path` 解析后读一张表，带列裁剪和日期范围过滤。

    parquet 走 ``pd.read_parquet(path, columns=..., filters=...)``，日期范围下推成 pyarrow
    过滤条件，比较值按日期列的实际类型换算（时间戳 / date / ``2020-01-02`` 或 ``20200102``
    文本 / ``YYYYMMDD`` 整数）；换算不了的（其他写法、其他类型）读入后再过滤，结果相同。
    ``.csv`` / ``.feather`` / ``.xlsx`` 整表读入后再过滤，其中 csv、xlsx 的常见证券代码列
    按文本读入以保住前导零。

    日期范围含两端；日期为空的行在给了 start / end 时不返回。除此之外不改任何列的类型，
    读出来是什么就是什么（不会替你把日期列转成时间戳）。

    Args:
        name: 相对数据根的路径，见 :func:`data_path`。
        columns: 只读这些列；None 读全部。
        start: 起始日期（含），可为字符串、时间戳、date 或 ``YYYYMMDD`` 整数；None 不限。
        end: 截止日期（含），同上。
        date_col: 日期列名；不给时按常见日期列名在文件里找。
        report_id: 案例编号，见 :func:`data_path`。
        filters: 其他过滤条件，pyarrow 的写法（元组列表、列表的列表或表达式），与日期
            范围取交集。

    Returns:
        读出的 DataFrame。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 给了 start / end 却找不到日期列；columns 里有文件中不存在的列；
            文件格式不支持。
    """
    path = data_path(name, report_id)
    label = os.fspath(name)
    if not path.is_file():
        raise FileNotFoundError(f"数据文件不存在: {path}（name={label}）")
    wanted = None if columns is None else list(dict.fromkeys([columns] if isinstance(columns, str) else columns))
    lo, hi = _to_timestamp(start, "start"), _to_timestamp(end, "end")
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return _read_parquet_table(path, label, wanted, lo, hi, date_col, filters)
    if suffix in _FLAT_READERS:
        return _read_flat_table(path, label, wanted, lo, hi, date_col, filters)
    raise ValueError(f"不支持的数据文件格式 {suffix or '（无后缀）'}: {path}（支持 .parquet / .csv / .feather / .xlsx）")


def results_dir(report_id: Optional[str] = None) -> Path:
    """本次运行的结果目录：试跑模式写 ``results_mock``，否则写 ``results``。

    返回 ``<案例根>/output/<report_id>/results_mock``（试跑模式）或
    ``<案例根>/output/<report_id>/results``，目录不存在就创建。这样真实结果目录里只会有
    真实数据算出来的东西。案例根定位不到时（既没设 ``REPORT_REPRODUCE_ROOT``，从当前目录
    往上也没有 ``workspace/<report_id>/``）退回当前工作目录。

    Args:
        report_id: 案例编号；不给时取环境变量 ``REPRODUCE_REPORT_ID``。

    Returns:
        结果目录的路径（已存在）。

    Raises:
        ValueError: 解析不出 report_id。
    """
    rid = _resolve_report_id(report_id)
    if rid is None:
        raise ValueError(f"无法确定 report_id：请显式传入，或设置环境变量 {_REPORT_ID_ENV}")
    with _MANIFEST_LOCK:
        if _MANIFEST_STATE["report_id"] is None:
            _MANIFEST_STATE["report_id"] = rid  # 退出时自动写数据清单要知道是哪个案例
    root = _case_root(rid) or Path.cwd()
    target = root / "output" / rid / ("results_mock" if is_trial(rid) else "results")
    target.mkdir(parents=True, exist_ok=True)
    return target


def reset_data_manifest() -> None:
    """清空进程内的数据登记表（同一进程里连着跑多次、或测试之间用）。"""
    with _MANIFEST_LOCK:
        _MANIFEST_FILES.clear()
        _MANIFEST_STATE.update(started_at=None, report_id=None)


def build_data_manifest(report_id: Optional[str] = None) -> dict[str, Any]:
    """把登记表整理成数据清单的内容（不写盘）。字段见 :func:`write_data_manifest`。"""
    with _MANIFEST_LOCK:
        files = [dict(entry) for entry in _MANIFEST_FILES.values()]
        started_at = _MANIFEST_STATE["started_at"]
        remembered = _MANIFEST_STATE["report_id"]
    rid = _resolve_report_id(report_id) or remembered
    return {
        "report_id": rid,
        "trial": is_trial(rid) if rid is not None else False,
        "started_at": started_at or _LOADED_AT,
        "finished_at": _now_iso(),
        "argv": list(sys.argv),
        "files": files,
    }


def write_data_manifest(report_id: Optional[str] = None, path: Optional[Path] = None) -> Path:
    """把本进程经 :func:`data_path` 读过的文件写成数据清单 ``data_manifest.json``。

    内容形如::

        {"report_id": "...", "trial": false,
         "started_at": "2026-11-22T10:00:00+08:00", "finished_at": "...", "argv": [...],
         "files": [{"name": "ashare_stock_price.parquet", "path": "/abs/...", "source": "real",
                    "size": 123, "mtime": "2026-11-20T18:00:00+08:00", "fingerprint": "<size>-<mtime_ns>"}]}

    ``source`` 为 ``real``（数据根）或 ``mock``（本案例的覆盖目录）；``started_at`` 取首次
    登记的时间；``files`` 按首次读取的先后排列，文件不存在时 size / mtime / fingerprint 为
    null。重复调用以最新的登记表覆盖写。首次登记时已用 ``atexit`` 注册了一次自动写出，
    策略代码一般不用自己调；自动写出只在主进程、且解析得出 report_id 时进行（环境变量，
    或本进程给 :func:`data_path` / :func:`results_dir` 传过的那个），子进程里读的文件不进
    清单（登记表是进程内的）。案例根定位不到、当前目录下也没有这个案例的结果目录时
    （在工作区之外跑的临时脚本）不自动写，免得凭空建出 ``output/``。

    Args:
        report_id: 案例编号；不给时取环境变量 ``REPRODUCE_REPORT_ID``，再不行取本进程
            调用 :func:`data_path` / :func:`results_dir` 时用过的那个。
        path: 写到哪里；不给时写进 ``results_dir(report_id)``。

    Returns:
        清单文件的路径。

    Raises:
        ValueError: 没给 path，又解析不出 report_id。
    """
    rid = _resolve_report_id(report_id) or _MANIFEST_STATE["report_id"]
    target = Path(path) if path is not None else results_dir(rid) / DATA_MANIFEST_NAME
    manifest = build_data_manifest(rid)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


def _in_main_process() -> bool:
    """当前是不是主进程（multiprocessing / joblib 的工作进程不自动写清单，免得盖掉主进程的）。"""
    try:
        import multiprocessing

        return multiprocessing.parent_process() is None
    except Exception:  # noqa: BLE001 - 判断不了就按主进程处理
        return True


def _write_data_manifest_at_exit() -> None:
    """进程退出时自动写一次数据清单。任何失败都不抛：不能因为记账改变策略的退出码。"""
    try:
        with _MANIFEST_LOCK:
            empty = not _MANIFEST_FILES
            remembered = _MANIFEST_STATE["report_id"]
        rid = _resolve_report_id(None) or remembered  # 与 write_data_manifest() 不带参数时的取法一致
        if empty or rid is None or not _in_main_process():
            return
        if _case_root(rid) is None and not (Path.cwd() / "output" / rid / "results").is_dir():
            return  # 定位不到案例，当前目录下也没有它的结果目录（临时脚本、notebook）：不凭空建目录
        write_data_manifest(rid)
    except Exception:  # noqa: BLE001
        pass
