"""数据加载与预处理（m1：D1–D4）。

加载四类数据并对齐主区间：
- D1 10年期国债期货主力合约（financial_future_price.parquet）
- D2 沪深300指数（ashare_csiindex_trade.parquet, index_code=000300）
- D3 4种中债净价现券指数（bond_index_quote.parquet；覆盖实测见 AS5）
- D4 交易日历（ashare_tradeday.parquet，复用 common.data_loader）

设计要点：
- 国债期货日收益采用 ``pct_of_close_price`` / ``pct_of_sett_price``（同合约日涨跌幅，
  规避主力换月跨合约跳空），缺失时回退 close/settle.pct_change()。
- 全部序列以「日期」为索引、升序、去重，供上层信号构造与回测直接使用。
- 防未来函数在回测引擎层通过 signal_lag 保证；本层只做无前视的原始数据整理。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from common.data_loader import load_trade_calendar  # noqa: E402
from src.test_v2.config import CONFIG, Config  # noqa: E402


def _require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"必需数据文件缺失: {path}")


def _date_index(frame: pd.DataFrame) -> pd.DataFrame:
    """转为按 date 升序、去重的日期索引 DataFrame。"""
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"])
    return (
        out.sort_values("date")
        .drop_duplicates("date", keep="last")
        .set_index("date")
    )


# ---------------------------------------------------------------------------
# D1 10年期国债期货主力
# ---------------------------------------------------------------------------

def load_treasury_future_main(config: Config = CONFIG) -> pd.DataFrame:
    """加载 10 年期国债期货主力合约日行情（D1）。

    Returns:
        date 索引 DataFrame，列：contract_code, close, settle,
        close_return（收盘价日收益，decimal）, settle_return（结算价日收益，decimal）。
    """
    path = config.data_dir / "financial_future_price.parquet"
    _require(path)
    cols = [
        "date", "contract_code", "close", "settle",
        "pct_of_close_price", "pct_of_sett_price", "main_contract",
    ]
    raw = pd.read_parquet(path, columns=cols)
    code = raw["contract_code"].astype(str)
    mask = code.str.match(config.future_code_regex) & raw["main_contract"].eq(config.future_main_flag)
    frame = _date_index(raw.loc[mask, cols[:-1]])

    # 同合约日涨跌幅优先（规避主力换月跨合约跳空），缺失回退价格 pct_change。
    frame["close_return"] = (frame["pct_of_close_price"] / 100.0).fillna(frame["close"].pct_change())
    frame["settle_return"] = (frame["pct_of_sett_price"] / 100.0).fillna(frame["settle"].pct_change())
    return frame[["contract_code", "close", "settle", "close_return", "settle_return"]]


# ---------------------------------------------------------------------------
# D2 沪深300指数
# ---------------------------------------------------------------------------

def load_hs300(config: Config = CONFIG) -> pd.DataFrame:
    """加载沪深300指数日行情（D2），保留全历史以支撑基日以来扩窗分位。

    Returns:
        date 索引 DataFrame，列：close, hs300_return（日收益，decimal）。
    """
    path = config.data_dir / "ashare_csiindex_trade.parquet"
    _require(path)
    cols = ["index_code", "date", "close", "change_pct"]
    raw = pd.read_parquet(path, columns=cols)
    frame = raw.loc[raw["index_code"].astype(str).eq(config.hs300_code), ["date", "close", "change_pct"]]
    frame = _date_index(frame)
    frame["hs300_return"] = (frame["change_pct"] / 100.0).fillna(frame["close"].pct_change())
    return frame[["close", "hs300_return"]]


# ---------------------------------------------------------------------------
# D3 中债净价现券指数（覆盖实测）
# ---------------------------------------------------------------------------

def load_bond_index(config: Config = CONFIG) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """加载 4 种中债净价现券指数（D3）并核实本地覆盖。

    实测：bond_index_quote.parquet 仅含中证/富时等系列，4 个中债 CBA 净价指数
    （CBA00102/00602/00902/07702）在 bond_index_info（元数据）有登记但 quote 表
    零行情覆盖 —— D3 现券行情本地缺失（见 AS5，直接影响 m3 的 R5/R6）。

    Returns:
        (data, coverage)：
        data = {code: date 索引 DataFrame[close, ret]}（仅含实际有行情的代码，通常为空）；
        coverage = DataFrame[code, name, available, n_rows, start, end]。
    """
    path = config.data_dir / "bond_index_quote.parquet"
    _require(path)
    quote = pd.read_parquet(path, columns=["index_code", "date", "close", "change_pct"])
    quote["index_code"] = quote["index_code"].astype(str)

    data: dict[str, pd.DataFrame] = {}
    rows: list[dict] = []
    for code, name in config.bond_index_codes.items():
        sub = quote.loc[quote["index_code"].eq(code), ["date", "close", "change_pct"]]
        available = not sub.empty
        if available:
            frame = _date_index(sub)
            frame["ret"] = (frame["change_pct"] / 100.0).fillna(frame["close"].pct_change())
            data[code] = frame[["close", "ret"]]
            rows.append({
                "code": code, "name": name, "available": True,
                "n_rows": len(frame),
                "start": frame.index.min().date().isoformat(),
                "end": frame.index.max().date().isoformat(),
            })
        else:
            rows.append({
                "code": code, "name": name, "available": False,
                "n_rows": 0, "start": None, "end": None,
            })
    coverage = pd.DataFrame(rows)
    return data, coverage


# ---------------------------------------------------------------------------
# D4 交易日历
# ---------------------------------------------------------------------------

def load_calendar(config: Config = CONFIG) -> pd.DataFrame:
    """加载交易日历（D4），并衍生 weekday 与周四标记（F5 用）。

    复用 common.data_loader.load_trade_calendar（已过滤 IfTradingDay==1、去重日期）。

    Returns:
        date 索引 DataFrame，列：weekday(0=周一), is_thursday, IfWeekEnd, IfMonthEnd。
    """
    cal = load_trade_calendar(config.data_dir)
    cal = cal.set_index("date").sort_index()
    out = pd.DataFrame(index=cal.index)
    out["weekday"] = cal.index.weekday
    out["is_thursday"] = (cal.index.weekday == config.calendar_weekday).astype(int)
    for col in ("IfWeekEnd", "IfMonthEnd"):
        if col in cal.columns:
            out[col] = cal[col].values
    return out


# ---------------------------------------------------------------------------
# 主区间对齐
# ---------------------------------------------------------------------------

def build_main_panel(config: Config = CONFIG) -> pd.DataFrame:
    """对齐 D1/D2/D4 到国债期货主力交易日、主区间 [main_start, main_end]。

    以国债期货主力交易日为基准索引（择时标的），左连沪深300与交易日历。
    注意（CA-A01）：本函数输出**已截断到主区间** [main_start, main_end]，不含前置历史；
    故其 hs300_close 列不可用于「基日以来扩窗分位」（样本被腰斩、上下轨错位）。需要
    全历史扩窗分位的 F1 长短端跷跷板，请直接消费 load_hs300() 的全历史序列
    （见 strategy.build_interval_seesaw_signal），勿用本面板列。

    Returns:
        date 索引 DataFrame，列：future_close, future_settle, future_close_return,
        future_settle_return, hs300_close, hs300_return, weekday, is_thursday。
    """
    fut = load_treasury_future_main(config)
    hs = load_hs300(config)
    cal = load_calendar(config)

    panel = pd.DataFrame(index=fut.index)
    panel["future_close"] = fut["close"]
    panel["future_settle"] = fut["settle"]
    panel["future_close_return"] = fut["close_return"]
    panel["future_settle_return"] = fut["settle_return"]
    panel["hs300_close"] = hs["close"].reindex(fut.index)
    panel["hs300_return"] = hs["hs300_return"].reindex(fut.index)
    panel = panel.join(cal[["weekday", "is_thursday"]], how="left")

    start = pd.Timestamp(config.main_start)
    end = pd.Timestamp(config.main_end)
    return panel.loc[(panel.index >= start) & (panel.index <= end)].copy()
