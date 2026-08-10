"""m1 数据映射与宏观因子准备 · ssrn_6115073（市场迁移复现）

产出对齐面板供 m2-m7 全链复用：
  - 三宽基（沪深300/上证50/中证500）时点成分股月频收益面板 + 时点成分掩码 + 可交易掩码
  - 中国宏观候选池月频面板（同比水平 level + AS1 月度一阶差分 change）
  - F12 BorutaShap 重选（依赖不可用时退化直采全集，AS16/AS38）
  - rf 月频序列（10Y 国债折算，AS36）
  - 三宽基指数月频收益 + 点位序列（Index 基准 / Modigliani σ_b，AS33）

未来函数红线（code_audit/codex 逐点核查）：
  1. 宏观按 info_publ_date（披露日）asof 对齐，缺失时用报告期 + 保守滞后（AS37）；
     利率为市场即时数据（is_market_rate）无披露滞后。
  2. 股票池用时点成分（in_date/out_date 半开区间），防幸存者偏差（AS8/AS28）。
  3. BorutaShap 重选只用训练期（<= TRAIN_END）数据，防泄漏（AS16）。
  4. 月收益面板 index 为月末交易日、值为该月已实现收益；掩码为月末已知状态——
     面板本身无未来函数。信号 T 月末算、T+1 月执行的错位由下游 m2/m6 承接。

数据结构约定见各 dataclass 与函数 docstring 的 Returns 段。
运行冒烟：uv run python -m src.ssrn_6115073.data_prep
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from common.data_loader import (
    LOCAL_DATA_DIR,
    filter_st_stocks,
    get_index_members_on_date,
    get_month_end_trading_days,
    load_index_components,
    load_limit_status,
    load_st_data,
    load_suspend_status,
)

from .config import (
    BORUTA_MIN_TRAIN_SAMPLES,
    BORUTA_N_TRIALS,
    BORUTA_RF_N_ESTIMATORS,
    BORUTA_TARGET_MARKET,
    LISTING_MIN_MONTHS,
    MACRO_CANDIDATES,
    MARKETS,
    PANEL_LOAD_START,
    PERIODS_PER_YEAR,
    PUBL_LAG_CAP_DAYS,
    RANDOM_SEED,
    RF_CACHE_COLUMN,
    STOCK_CODE_WIDTH,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
)

# ---------------------------------------------------------------------------
# 返回结构（供 m2-m7 直接对接）
# ---------------------------------------------------------------------------

@dataclass
class MarketData:
    """单个宽基市场的对齐面板。

    所有 DataFrame 的 index = 月末交易日（pd.DatetimeIndex），columns = 6 位股票代码，
    三张表 index/columns 完全对齐。
    """
    code: str                          # 指数代码（如 '000300'）
    name: str                          # 内部市场名（如 'hs300'）
    stock_returns: pd.DataFrame        # 月收益（首月为 NaN；前复权 close 的 pct_change）
    member_mask: pd.DataFrame          # bool；True=该月末为时点成分股
    tradeable_mask: pd.DataFrame       # bool；True=该月末非ST/非停牌/非涨跌停/非次新
    index_returns: pd.Series           # 指数月收益（Index 基准）
    index_level: pd.Series             # 指数月末点位（Modigliani σ_b 用）


@dataclass
class MacroData:
    """中国宏观候选池面板与 BorutaShap 重选结果。

    level_panel/change_panel 的 index = 月末交易日，columns = 因子名（CPI/PPI/.../IR）。
    """
    level_panel: pd.DataFrame          # 同比水平（PMI/IR 为水平值），披露日 asof 对齐
    change_panel: pd.DataFrame         # AS1 月度一阶差分 Δ（level.diff()），供 Δβ 的 X>0/X<0
    candidate_factors: list[str]       # 可得候选全集（UR/DGDP 已据实降维）
    selected_factors: list[str]        # BorutaShap 重选（或退化直采）后的最终因子集
    selection_mode: str                # 'borutashap' | 'degraded_all' | 'degraded_insufficient'


@dataclass
class PreparedData:
    """m1 全部产出打包。"""
    markets: dict[str, MarketData]     # key = 内部市场名（hs300/sz50/zz500）
    macro: MacroData
    rf: pd.Series                      # 月度无风险利率（index=月末交易日）
    month_ends: pd.DatetimeIndex       # 全样本月末交易日历
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    meta: dict = field(default_factory=dict)   # 诊断信息（实际首末日、披露日覆盖等）


# ---------------------------------------------------------------------------
# 通用 helper
# ---------------------------------------------------------------------------

def _norm_code(s: pd.Series) -> pd.Series:
    """规整 A股股票代码为 6 位字符串（去交易所后缀、补零）。"""
    return s.astype(str).str.split(".").str[0].str.zfill(STOCK_CODE_WIDTH)


def _month_end_index(
    start: str,
    end: str,
    data_dir: Path = LOCAL_DATA_DIR,
) -> pd.DatetimeIndex:
    """全样本月末交易日历（升序，统一 datetime64[ns]）。"""
    idx = pd.DatetimeIndex(sorted(get_month_end_trading_days(start, end, data_dir)))
    return idx.astype("datetime64[ns]")


# ---------------------------------------------------------------------------
# 股票池：时点成分股月频收益 + 时点成分掩码
# ---------------------------------------------------------------------------

def _load_forward_prices(
    universe_raw: list[str],
    data_dir: Path,
) -> pd.DataFrame:
    """读取给定成分股并集的前复权日行情（filters 下推 date/stock_code）。

    Returns:
        DataFrame[stock_code(规整), date, close]（前复权 close，可直接 pct_change 算复权收益）。
    """
    path = data_dir / "ashare_stock_price_forward.parquet"
    px = pd.read_parquet(
        path,
        columns=["stock_code", "date", "close"],
        filters=[
            ("date", ">=", pd.Timestamp(PANEL_LOAD_START)),
            ("stock_code", "in", universe_raw),
        ],
    )
    px["date"] = pd.to_datetime(px["date"])
    px["stock_code"] = _norm_code(px["stock_code"])
    return px


def _monthly_close_wide(px: pd.DataFrame, month_ends: pd.DatetimeIndex) -> pd.DataFrame:
    """把日频前复权 close 聚合为月末宽表（index=月末交易日, columns=股票）。"""
    px = px.sort_values("date")
    px = px.assign(ym=px["date"].dt.to_period("M"))
    # 每股每月最后一个交易日的前复权 close
    monthly = px.groupby(["stock_code", "ym"], as_index=False).agg(close=("close", "last"))
    wide = monthly.pivot(index="ym", columns="stock_code", values="close")
    # period(月) → 对应月末交易日（一一对应）
    ym_to_me = {me.to_period("M"): me for me in month_ends}
    wide = wide[wide.index.isin(ym_to_me)]
    wide.index = pd.DatetimeIndex([ym_to_me[p] for p in wide.index])
    return wide.sort_index()


def load_stock_monthly_returns(
    index_code: str,
    month_ends: pd.DatetimeIndex,
    data_dir: Path = LOCAL_DATA_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series]:
    """某宽基时点成分股的月频收益面板与时点成分掩码。

    Args:
        index_code: 指数代码（如 '000300'）。
        month_ends: 全样本月末交易日历。
        data_dir: 数据根目录。

    Returns:
        returns:      DataFrame[月末交易日 × 股票]，月收益（首月 NaN，前复权 pct_change）。
        member_mask:  DataFrame[月末交易日 × 股票]，bool，True=该月末为时点成分股。
        px:           日频前复权行情（复用给 first_trade 计算，避免重复读盘）。
        first_trade:  Series[股票 → 首个行情日]（次新过滤用）。
    """
    comp = load_index_components(index_code, data_dir)
    comp = comp.assign(stock_code=_norm_code(comp["stock_code"]))
    universe_raw = list(pd.Index(comp["stock_code"].unique()))

    px = _load_forward_prices(universe_raw, data_dir)
    wide = _monthly_close_wide(px, month_ends)
    returns = wide.pct_change(fill_method=None)

    # 时点成分掩码（逐月末按 in_date/out_date 半开区间）
    stocks = returns.columns
    member_mask = pd.DataFrame(False, index=returns.index, columns=stocks)
    for me in returns.index:
        members = get_index_members_on_date(comp, me)
        cols = stocks.intersection(members)
        member_mask.loc[me, cols] = True

    first_trade = px.groupby("stock_code")["date"].min()
    return returns, member_mask, px, first_trade


# ---------------------------------------------------------------------------
# 可交易掩码：非ST / 非停牌 / 非涨跌停 / 非次新（信号日月末状态）
# ---------------------------------------------------------------------------

def load_tradeable_mask(
    returns: pd.DataFrame,
    first_trade: pd.Series,
    data_dir: Path = LOCAL_DATA_DIR,
) -> pd.DataFrame:
    """构造建仓信号日（月末）的可交易掩码。

    过滤四类不可交易/不宜纳入样本：ST、停牌、涨跌停、次新（上市不足 LISTING_MIN_MONTHS）。
    口径：基于信号日 t（月末）及之前已知状态，无未来函数；严格到 T+1 执行日的过滤
    留给 m6 建仓阶段细化。

    Args:
        returns: load_stock_monthly_returns 产出的月收益面板（定义 index/columns）。
        first_trade: 每股首个行情日（次新过滤基准）。
        data_dir: 数据根目录。

    Returns:
        DataFrame[月末交易日 × 股票]，bool，True=该月末可交易。
    """
    month_ends = returns.index
    stocks = returns.columns
    universe_raw = list(stocks)

    st = load_st_data(data_dir)
    st = st.assign(stock_code=_norm_code(st["stock_code"]))

    # 停牌 / 涨跌停：复用 common 加载器（filters 下推本 universe + 起始日，CA-A02）
    susp = load_suspend_status(
        data_dir, stock_codes=universe_raw, start_date=PANEL_LOAD_START
    )
    susp["date"] = susp["date"].astype("datetime64[ns]")
    susp["stock_code"] = _norm_code(susp["stock_code"])
    susp_set = set(
        map(tuple, susp.loc[
            susp["if_suspend"] == 1, ["stock_code", "date"]
        ].itertuples(index=False, name=None))
    )

    limit = load_limit_status(
        data_dir, stock_codes=universe_raw, start_date=PANEL_LOAD_START
    )
    limit["date"] = limit["date"].astype("datetime64[ns]")
    limit["stock_code"] = _norm_code(limit["stock_code"])
    limit_hit = limit[(limit["surged_limit"] == 1) | (limit["decline_limit"] == 1)]
    limit_set = set(
        map(tuple, limit_hit[["stock_code", "date"]].itertuples(index=False, name=None))
    )

    listing_cutoff = pd.DateOffset(months=LISTING_MIN_MONTHS)
    mask = pd.DataFrame(False, index=month_ends, columns=stocks)
    for me in month_ends:
        # 有当月行情（收益非 NaN）才是候选
        has_px = returns.loc[me].notna()
        candidates = stocks[has_px]
        # 非 ST
        candidates = filter_st_stocks(pd.Series(candidates), me, st)
        # 非次新：首个行情日 + 门槛 <= 当前
        old_enough = first_trade.reindex(candidates)
        candidates = candidates[(old_enough + listing_cutoff <= me).to_numpy()]
        # 非停牌、非涨跌停（月末当日）
        survivors = [
            c for c in candidates
            if (c, me) not in susp_set and (c, me) not in limit_set
        ]
        mask.loc[me, survivors] = True
    return mask


# ---------------------------------------------------------------------------
# 宏观候选池：披露日 asof 对齐 → 月频 level + AS1 差分 change
# ---------------------------------------------------------------------------

def _macro_level_publ(spec: dict, data_dir: Path) -> pd.DataFrame:
    """加载单个宏观因子的 (披露日, 值) 序列。

    普通统计指标：publ = info_publ_date，缺失时 = 报告期末 + 保守滞后（AS37）。
    市场利率（is_market_rate）：来自 macro_cache 宽表，publ = 报告期末本身（即时无滞后）。

    Returns:
        DataFrame[publ_date, value, report_date]（升序，publ_date 唯一取最后一条）；
        report_date=报告期末，供报告期层面构造 change（口径感知，AS39）。
    """
    if spec["file"] == "macro_cache":
        cache = pd.read_parquet(data_dir / "macro_cache.parquet", columns=[spec["indicator"]])
        s = cache[spec["indicator"]].dropna()
        rd = pd.to_datetime(s.index)
        out = pd.DataFrame({"publ_date": rd, "value": s.to_numpy(), "report_date": rd})
    else:
        df = pd.read_parquet(
            data_dir / f"{spec['file']}.parquet",
            columns=["date", "info_publ_date", "indicator_name", "data_value"],
        )
        df = df[df["indicator_name"] == spec["indicator"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        publ_raw = pd.to_datetime(df["info_publ_date"])
        fallback = df["date"] + pd.to_timedelta(spec["publ_lag_days"], unit="D")
        cap = df["date"] + pd.to_timedelta(PUBL_LAG_CAP_DAYS, unit="D")
        # 披露日合理性检验（AS37）：仅采信 date < publ <= date+上限 的真实披露日，
        # 否则（缺失 / 被批量回填为近期入库日）回退保守滞后，防未来函数且保覆盖。
        reasonable = publ_raw.notna() & (publ_raw > df["date"]) & (publ_raw <= cap)
        df["publ_date"] = publ_raw.where(reasonable, fallback)
        df["report_date"] = df["date"]
        out = df.rename(columns={"data_value": "value"})[["publ_date", "value", "report_date"]]

    out = out.dropna(subset=["publ_date", "value"]).sort_values("publ_date")
    # 同一披露日多条取最后（如修订）
    out = out.drop_duplicates(subset="publ_date", keep="last").reset_index(drop=True)
    return out


def _report_change(level_publ: pd.DataFrame, yoy_type: str) -> pd.DataFrame:
    """在报告期层面构造因子变化 Δ（口径感知，落地 CA-A01 / AS39）。

    - yoy_current / level：报告期序列的一阶差分（月度/季度期间变化），无累计跳变。
    - yoy_cumulative：报告期一阶差分，且跨年（累计重置：月频 1 月 / 季频 Q1）断点置 NaN，
      剔除累计口径切换的机械跳变；季频差分经后续 asof 前填自然摊到季内月份（非季内恒 0）。

    Args:
        level_publ: _macro_level_publ 输出 [publ_date, value, report_date]。
        yoy_type: 'yoy_current' | 'yoy_cumulative' | 'level'。

    Returns:
        DataFrame[publ_date, value]，value=报告期期间变化（供 asof；已剔 NaN/重置断点）。
    """
    df = level_publ.sort_values("report_date").copy()
    chg = df["value"].diff()
    if yoy_type == "yoy_cumulative":
        yr = df["report_date"].dt.year
        reset = yr != yr.shift(1)   # 跨年 = 累计口径重置断点，置 NaN
        chg = chg.mask(reset)
    elif yoy_type == "yoy_current_filled":
        # 工业增加值 1-2 月为累计填充、3 月切回真实当月同比：每年 1-3 月 diff 为口径切换
        # 机械跳变（|Δ| 可达 39），置 NaN（CA-A01/AS39）
        chg = chg.mask(df["report_date"].dt.month.isin([1, 2, 3]))
    df = df.assign(value=chg)
    return df[["publ_date", "value"]].dropna(subset=["value"]).sort_values("publ_date")


def _asof_to_month_ends(level_publ: pd.DataFrame, month_ends: pd.DatetimeIndex) -> pd.Series:
    """按披露日把宏观序列 asof 对齐到月末交易日（每个月末取已披露的最新值）。"""
    me_ns = pd.DatetimeIndex(month_ends).astype("datetime64[ns]")
    left = pd.DataFrame({"me": me_ns}).sort_values("me")
    right = level_publ.rename(columns={"publ_date": "me"}).copy()
    right["me"] = pd.to_datetime(right["me"]).astype("datetime64[ns]")
    right = right.sort_values("me")
    merged = pd.merge_asof(left, right, on="me", direction="backward")
    return pd.Series(merged["value"].to_numpy(), index=me_ns, name="value")


def load_macro_candidate_panel(
    month_ends: pd.DatetimeIndex,
    data_dir: Path = LOCAL_DATA_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """中国宏观候选池月频面板（披露日对齐）。

    change_panel 为 AS1 变化量 X，但在报告期层面口径感知构造（CA-A01/AS39）而非
    机械 level.diff()：当期同比/水平直接差分；累计同比剔年初重置；季频累计经 asof 前填
    使季内月份共享季度变化（非季内恒 0）。

    Returns:
        level_panel:  DataFrame[月末交易日 × 因子]，同比水平（PMI/IR 为水平值），披露日 asof。
        change_panel: DataFrame[月末交易日 × 因子]，因子月度变化 Δ（口径感知，披露日 asof）。
    """
    levels: dict[str, pd.Series] = {}
    changes: dict[str, pd.Series] = {}
    for name, spec in MACRO_CANDIDATES.items():
        level_publ = _macro_level_publ(spec, data_dir)
        levels[name] = _asof_to_month_ends(level_publ[["publ_date", "value"]], month_ends)
        change_publ = _report_change(level_publ, spec["yoy_type"])
        changes[name] = _asof_to_month_ends(change_publ, month_ends)
    level_panel = pd.DataFrame(levels, index=month_ends)
    change_panel = pd.DataFrame(changes, index=month_ends)
    return level_panel, change_panel


# ---------------------------------------------------------------------------
# F12 BorutaShap 宏观因子重选（AS16；依赖不可用/样本不足则退化）
# ---------------------------------------------------------------------------

def select_macro_factors(
    change_panel: pd.DataFrame,
    target_returns: pd.Series,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
) -> tuple[list[str], str]:
    """用 BorutaShap 在训练期从候选池重选宏观因子集（防泄漏，只用 [train_start, train_end]）。

    主路径：BorutaShap（RandomForest 基模型）；依赖（shap→BorutaShap 不可用）或训练样本
    不足时，按 AS16 授权退化为「直接采用可得候选全集」（AS38 补记退化事实）。

    Args:
        change_panel: 宏观 Δ 面板（月频，含 2006 缓冲期）。
        target_returns: 目标变量（主市场指数月收益）。
        train_start: 训练期起（含）；显式下界排除 2006 缓冲，对齐「2007 起训练」（CA-A04）。
        train_end: 训练期截止（含）。

    Returns:
        (selected_factors, mode)；mode ∈ {'borutashap','degraded_all','degraded_insufficient'}。
    """
    candidates = list(change_panel.columns)
    train_mask = (change_panel.index >= train_start) & (change_panel.index <= train_end)
    X = change_panel.loc[train_mask]
    y = target_returns.reindex(X.index)
    data = pd.concat([X, y.rename("_target")], axis=1).dropna()

    if len(data) < BORUTA_MIN_TRAIN_SAMPLES:
        return candidates, "degraded_insufficient"

    try:
        from sklearn.ensemble import RandomForestRegressor  # noqa: F401
        from BorutaShap import BorutaShap

        model = RandomForestRegressor(
            n_estimators=BORUTA_RF_N_ESTIMATORS, random_state=RANDOM_SEED, n_jobs=-1
        )
        selector = BorutaShap(model=model, importance_measure="shap", classification=False)
        selector.fit(
            X=data[candidates], y=data["_target"],
            n_trials=BORUTA_N_TRIALS, random_state=RANDOM_SEED, verbose=False,
        )
        accepted = list(selector.accepted)
        # 若 Boruta 判定全为 tentative/rejected，退化为全采用以保证下游可跑
        if not accepted:
            return candidates, "degraded_all"
        return accepted, "borutashap"
    except (ModuleNotFoundError, ImportError):
        # 仅**依赖不可用**（shap→BorutaShap 缺）按 AS16/AS38 授权退化直采候选全集
        return candidates, "degraded_all"
    except Exception as exc:
        # 非依赖异常（算法/数据/实现错误）不静默吞成已登记的 degraded：打印类型+堆栈后重抛，
        # 防把真 bug 伪装成依赖退化（CA-CDX-C-02）。当前环境确缺 shap→走上面 ImportError 分支不受影响
        import traceback
        traceback.print_exc()
        raise RuntimeError(
            f"select_macro_factors BorutaShap 非依赖异常 {type(exc).__name__}: {exc}"
            f"——不静默退化为 degraded_all，请排查（堆栈见上）"
        ) from exc


# ---------------------------------------------------------------------------
# rf 无风险利率（10Y 国债折算，AS36）
# ---------------------------------------------------------------------------

def load_rf_series(
    month_ends: pd.DatetimeIndex,
    data_dir: Path = LOCAL_DATA_DIR,
) -> pd.Series:
    """月度无风险利率序列（10Y 国债年化收益率 → 月度几何折算）。

    Returns:
        Series[月末交易日 → 月度 rf]（(1 + y/100)^(1/12) - 1）。
    """
    cache = pd.read_parquet(data_dir / "macro_cache.parquet", columns=[RF_CACHE_COLUMN])
    s = cache[RF_CACHE_COLUMN].dropna()
    level_publ = pd.DataFrame(
        {"publ_date": pd.to_datetime(s.index), "value": s.to_numpy()}
    ).sort_values("publ_date")
    annual = _asof_to_month_ends(level_publ, month_ends)
    monthly_rf = (1.0 + annual / 100.0) ** (1.0 / PERIODS_PER_YEAR) - 1.0
    return monthly_rf.rename("rf")


# ---------------------------------------------------------------------------
# 指数基准（Index 基准 + Modigliani σ_b，AS33）
# ---------------------------------------------------------------------------

def load_index_benchmark(
    index_code: str,
    month_ends: pd.DatetimeIndex,
    data_dir: Path = LOCAL_DATA_DIR,
) -> tuple[pd.Series, pd.Series]:
    """宽基指数月频收益与月末点位。

    Returns:
        index_returns: Series[月末交易日 → 指数月收益]（首月 NaN）。
        index_level:   Series[月末交易日 → 指数月末点位]。
    """
    cit = pd.read_parquet(
        data_dir / "ashare_csiindex_trade.parquet",
        columns=["index_code", "date", "close"],
        filters=[("index_code", "==", index_code)],
    )
    cit["date"] = pd.to_datetime(cit["date"])
    cit = cit.sort_values("date").assign(ym=lambda d: d["date"].dt.to_period("M"))
    monthly = cit.groupby("ym").agg(close=("close", "last"))
    ym_to_me = {me.to_period("M"): me for me in month_ends}
    monthly = monthly[monthly.index.isin(ym_to_me)]
    monthly.index = pd.DatetimeIndex([ym_to_me[p] for p in monthly.index])
    level = monthly["close"].reindex(month_ends).sort_index()
    returns = level.pct_change(fill_method=None)
    return returns.rename(f"{index_code}_ret"), level.rename(f"{index_code}_level")


# ---------------------------------------------------------------------------
# 单市场 / 全量打包
# ---------------------------------------------------------------------------

def prepare_market(
    name: str,
    index_code: str,
    month_ends: pd.DatetimeIndex,
    data_dir: Path = LOCAL_DATA_DIR,
) -> MarketData:
    """打包单个宽基市场的全部对齐面板。"""
    returns, member_mask, _, first_trade = load_stock_monthly_returns(
        index_code, month_ends, data_dir
    )
    tradeable_mask = load_tradeable_mask(returns, first_trade, data_dir)
    index_returns, index_level = load_index_benchmark(index_code, month_ends, data_dir)
    return MarketData(
        code=index_code,
        name=name,
        stock_returns=returns,
        member_mask=member_mask,
        tradeable_mask=tradeable_mask,
        index_returns=index_returns,
        index_level=index_level,
    )


def prepare_all(data_dir: Path = LOCAL_DATA_DIR) -> PreparedData:
    """m1 主入口：产出三宽基面板 + 宏观候选池/重选 + rf + 区间，供 m2-m7 复用。"""
    month_ends = _month_end_index(PANEL_LOAD_START, TEST_END, data_dir)

    # 宏观候选池 + BorutaShap 重选（目标=主市场指数月收益）
    level_panel, change_panel = load_macro_candidate_panel(month_ends, data_dir)
    primary_code = MARKETS[BORUTA_TARGET_MARKET]
    primary_ret, _ = load_index_benchmark(primary_code, month_ends, data_dir)
    selected, mode = select_macro_factors(
        change_panel, primary_ret, pd.Timestamp(TRAIN_START), pd.Timestamp(TRAIN_END)
    )
    macro = MacroData(
        level_panel=level_panel,
        change_panel=change_panel,
        candidate_factors=list(change_panel.columns),
        selected_factors=selected,
        selection_mode=mode,
    )

    # 各宽基市场
    markets = {
        name: prepare_market(name, code, month_ends, data_dir)
        for name, code in MARKETS.items()
    }

    rf = load_rf_series(month_ends, data_dir)

    # 诊断信息（CA-A05：meta 名副其实，供下游/verifier 快速核查）
    train_valid = month_ends >= pd.Timestamp(TRAIN_START)
    meta = {
        "n_months": int(len(month_ends)),
        "panel_load_start": PANEL_LOAD_START,
        "rf_source": RF_CACHE_COLUMN,
        "macro_selection_mode": mode,
        "macro_yoy_types": {k: v["yoy_type"] for k, v in MACRO_CANDIDATES.items()},
        "market_avg_members": {
            name: round(float(md.member_mask.loc[train_valid].sum(axis=1).mean()), 1)
            for name, md in markets.items()
        },
    }

    return PreparedData(
        markets=markets,
        macro=macro,
        rf=rf,
        month_ends=month_ends,
        train_start=pd.Timestamp(TRAIN_START),
        train_end=pd.Timestamp(TRAIN_END),
        test_start=pd.Timestamp(TEST_START),
        test_end=pd.Timestamp(TEST_END),
        meta=meta,
    )


# ---------------------------------------------------------------------------
# 冒烟运行（仅确认可执行 + 打印面板形状；验证结论归 verifier）
# ---------------------------------------------------------------------------

def _smoke() -> None:
    pd.set_option("display.width", 160)
    print("=" * 78)
    print("m1 数据准备冒烟 · ssrn_6115073（市场迁移复现）")
    print("=" * 78)
    prep = prepare_all()

    me = prep.month_ends
    print(f"\n[区间] 月末日历 {me.min().date()} ~ {me.max().date()}，共 {len(me)} 个月")
    print(f"       训练 {prep.train_start.date()} ~ {prep.train_end.date()}；"
          f"测试 {prep.test_start.date()} ~ {prep.test_end.date()}")

    print("\n[股票池] 各宽基时点成分（TRAIN_START 之后有效区间）：")
    for name, md in prep.markets.items():
        valid = md.stock_returns.index >= prep.train_start
        avg_member = md.member_mask.loc[valid].sum(axis=1).mean()
        avg_buildable = (md.member_mask & md.tradeable_mask).loc[valid].sum(axis=1).mean()
        first_ret = md.stock_returns.dropna(how="all").index.min()
        print(f"   {name}({md.code}) 列(历史成分)={md.stock_returns.shape[1]:>4} "
              f"月均成分={avg_member:6.1f} 月均可建仓(成分∩可交易)={avg_buildable:6.1f} "
              f"收益起={first_ret.date()} 指数收益非空={md.index_returns.notna().sum()}")

    print("\n[宏观候选池] 因子 / 披露日 asof 后有效期数（level 非空）：")
    lp = prep.macro.level_panel
    for c in lp.columns:
        s = lp[c].dropna()
        print(f"   {c:<4} 有效={s.notna().sum():>3} 区间 {s.index.min().date()}~{s.index.max().date()} "
              f"近值={s.iloc[-1]:.3f}")
    print(f"\n[F12 BorutaShap] 模式={prep.macro.selection_mode}")
    print(f"   候选全集({len(prep.macro.candidate_factors)}): {prep.macro.candidate_factors}")
    print(f"   最终选定({len(prep.macro.selected_factors)}): {prep.macro.selected_factors}")

    print("\n[rf] 10Y国债月度折算 "
          f"非空={prep.rf.notna().sum()} 近值(月){prep.rf.dropna().iloc[-1]:.5f} "
          f"年化≈{((1+prep.rf.dropna().iloc[-1])**12-1)*100:.2f}%")

    print("\n[change_panel 头尾示例（主市场对齐）] 训练首期与测试末期：")
    cp = prep.macro.change_panel
    train_first = me[me >= prep.train_start][0]
    show_rows = [train_first, me[-1]]
    print(cp.loc[show_rows].round(3).to_string())

    print("\n[CA-A01 口径自检] 2018 全年 IP(当期同比)/GDP(季频累计)/M2(当期同比) 月度 Δ：")
    probe = cp.loc[cp.index.year == 2018, ["IP", "GDP", "M2"]]
    print(probe.round(3).to_string())
    gdp_seasonal = probe["GDP"]
    print(f"   GDP 2018 季内非空月数={int(gdp_seasonal.notna().sum())}/12"
          f"（旧机械 diff 季内恒 0；新口径经 asof 前填季度变化至季内月份）")
    print("   各因子 |Δ| 上限（累计口径机械跳变/不平稳因子会暴露为异常大值）：")
    print("   " + ", ".join(f"{c}={cp[c].abs().max():.2f}" for c in cp.columns))

    print(f"\n[meta 诊断] {prep.meta}")

    print("\n冒烟完成：面板可端到端构造（可执行性确认；验证结论由 verifier 判定）。")


if __name__ == "__main__":
    _smoke()
