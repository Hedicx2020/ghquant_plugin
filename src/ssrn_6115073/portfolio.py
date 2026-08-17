"""m6 组合构建（EW/MV）与回测评估 · ssrn_6115073（策略特有实现）。

把 m5 每簇选出的资产（``sp[m].selected[t]``）按等权 EW 与均值方差 MV 建仓，OLPS 序贯
月度调仓（式1-4，spec F1/F11/B5），无摩擦主回测（AS5），产 11 方法 × 6 比率 × 3 市场
主结果表（R1/表2）与累计收益（R5/图9-10）。通用配置算法/回测/绩效指标一律复用
``common/allocation_backtest.py`` 与 ``common/utils.py``，本文件只放策略特有的模型装配：

消融链（plan §1.3，读 spec B8/plan §1.3 语义落地，各消融关掉对应环节重跑）
  - CPMM-EW / CPMM-MV  全量主模型：聚类 + 宏观 pattern matching + 溢出加权 FS + 每簇选一
  - CPM-EW / CPM-MV    去宏观：不用宏观选经济周期，价格窗口在全历史匹配（复用 m4 stage2）
  - PMM                去聚类：CPMM 的 FS 全候选不分簇选 top-nc 只等权
  - EWMFM              去溢出加权：FS 等权 Σsignal（γ̃≡1）而非 Σγ̃·signal，每簇选一等权
外部基准（spec B8）
  - Index              对应宽基指数买入持有
  - HRP / HERC / NCO   层次配置（common 引擎，同候选池 + 滚动 ≤T 协方差）
  - OLMAR              在线移动均值回归（common 引擎，同候选池）

未来函数红线（全链一致）：MV/HRP/NCO 协方差与期望收益只用 ≤T 历史（扩展窗）；OLPS 信号
T 月末算、T+1 月执行（由 :func:`common.allocation_backtest.portfolio_backtest` 的 T→T_next
对齐硬保证）；建仓前用 m1 ``tradeable_mask`` 过滤停牌/涨跌停/ST/次新（AS5/AS8）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from common.allocation_backtest import (
    equal_weights,
    herc_weights,
    hrp_weights,
    mean_variance_weights,
    nco_weights,
    olmar_weights,
    portfolio_backtest,
    rolling_cov_estimate,
)
from common.utils import (
    calculate_annualized_volatility,
    calculate_arithmetic_annual_return,
    calculate_historical_var,
    calculate_max_drawdown,
    calculate_modigliani,
    calculate_psr,
    calculate_sharpe,
    calculate_sortino,
)
from src.ssrn_6115073.config import (
    MARKET_NAMES_CN,
    PERIODS_PER_YEAR,
)
from src.ssrn_6115073.pattern_matching import stage2_asset_forecast
from src.ssrn_6115073.spillover import aggregate_fs, select_per_cluster

# ---------------------------------------------------------------------------
# m6 参数常量（集中于本模块顶部；均可反查 spec/assumptions，杜绝魔法数字。
# 严守文件所有权——不改 m1 建的 config.py，沿 m2/m4/m5 惯例参数落各自模块顶部）
# ---------------------------------------------------------------------------
MV_LAMBDA: float = 1.0                 # MV 风险厌恶 λ 基准（AS3；敏感性 m7）
MV_COV_MIN_OBS: int = 12               # MV/基准协方差估计最少 ≤T 历史月（AS11 样本内估计）
MV_MU_WINDOW: int = 60                 # MV 期望收益 μ 的 ≤T 滚动窗口（月；5 年，稳健均值）
COST_BPS_FRICTIONLESS: float = 0.0     # 主回测无摩擦（AS5，对齐原文两条市场假设）
COST_BPS_STRESS: float = 40.0          # 含成本档：A股双边约千4=40bps（佣金万3+印花千1，AS5）
PSR_SR_BENCHMARK: float = 0.0          # PSR 基准 SR*=0（AS22）
VAR_LEVEL: float = 0.05                # 历史模拟 VaR 最低 5%（spec B7）
OLMAR_WINDOW_M: int = 5                # OLMAR SMA 窗口（月频，Li & Hoi 2012 默认区间）
OLMAR_EPSILON_M: float = 10.0          # OLMAR 均值回归阈值 ε

# 11 方法（R1/表2 列顺序，与 spec R1 表一致）
INTERNAL_MODELS: tuple[str, ...] = ("CPMM-EW", "CPMM-MV", "CPM-EW", "CPM-MV", "PMM", "EWMFM")
EXTERNAL_MODELS: tuple[str, ...] = ("Index", "HRP", "HERC", "OLMAR", "NCO")
ALL_MODELS: tuple[str, ...] = INTERNAL_MODELS + EXTERNAL_MODELS
RATIO_ORDER: tuple[str, ...] = ("AR", "AStd", "SR", "PSR", "SOR", "MR")


@dataclass
class ModelResult:
    """单市场单模型回测产出。"""
    market: str
    model: str
    port_returns: pd.Series               # 净期收益（index=收益实现月 T_next）
    nav: pd.Series                        # 净值（起点 1.0）
    weights_panel: pd.DataFrame           # 目标权重面板（index=调仓月 T）
    backtest: pd.DataFrame                # portfolio_backtest 全量输出（含 turnover/cost/contrib）
    metrics: dict[str, float]             # AR/AStd/SR/PSR/SOR/MR/MDD/VaR/cum_return/avg_turnover
    n_rebalance: int
    notes: str = ""


@dataclass
class MarketPortfolio:
    """单市场 11 方法回测汇总。"""
    market: str
    index_code: str
    regime_tier: str
    nc: int
    models: dict[str, ModelResult] = field(default_factory=dict)
    notes: str = ""


# ---------------------------------------------------------------------------
# 选股：四个内部模型的每月资产集（消融语义落地）
# ---------------------------------------------------------------------------

def cpmm_selected(sp_result) -> dict[pd.Timestamp, list[str]]:
    """CPMM（全量）：直接取 m5 每簇 argmax(FS>0) 的最终资产集（透传，无改动）。"""
    return {t: list(v) for t, v in sp_result.selected.items()}


def cpm_selected(
    stock_returns: pd.DataFrame,
    candidates: list[str],
    cluster_labels: dict[str, int],
    optimal_w: int,
    test_months: list[pd.Timestamp],
    month_ends: pd.DatetimeIndex,
) -> dict[pd.Timestamp, list[str]]:
    """CPM（去宏观）：不经宏观经济周期筛选，价格窗口在**全历史**匹配预测 r̂_j，每簇选 r̂ 最高 >0。

    复用 m4 :func:`stage2_asset_forecast`，令经济周期区间退化为全部历史（ep_end=pos_t−2、
    ep_span 覆盖全程），即「关掉宏观 pattern matching 那一级重跑」（plan §1.3 去宏观）。
    每簇（m3 canonical 簇标签）取 r̂ 最高且 >0（纯长仓，AS17）的资产 → ≈nc 只，供 EW/MV 建仓。

    未来函数：stage2 内部约束历史窗口之后一期 g+1 ≤ pos_t−1 < pos_t，严格早于信号月。
    """
    R = stock_returns.reindex(month_ends)
    cands = [c for c in candidates if c in R.columns]
    ret_arrs = {c: R[c].to_numpy(dtype=float) for c in cands}
    pos_of = {ts: i for i, ts in enumerate(month_ends)}

    selected: dict[pd.Timestamp, list[str]] = {}
    for t in test_months:
        pos_t = pos_of[t]
        rhat = {c: stage2_asset_forecast(ret_arrs[c], pos_t, optimal_w,
                                         ep_end_pos=pos_t - 2, ep_span=pos_t + 1)
                for c in cands}
        df = pd.DataFrame({"asset": list(rhat), "rhat": list(rhat.values())})
        df["cluster"] = df["asset"].map(cluster_labels)
        df = df[df["cluster"].notna()].dropna(subset=["rhat"])
        picks: list[str] = []
        for _cid, grp in df.groupby("cluster"):
            pos = grp[grp["rhat"] > 0.0]           # 长仓：仅 r̂>0
            if pos.empty:
                continue
            picks.append(str(pos.loc[pos["rhat"].idxmax(), "asset"]))
        selected[t] = picks
    return selected


def pmm_selected(
    sp_result,
    nc: int,
) -> dict[pd.Timestamp, list[str]]:
    """PMM（去聚类）：CPMM 的 FS（溢出加权）**不分簇**，全候选选 FS 最高 top-nc 只（>0）。

    与 CPMM-EW 选出等量（≈nc）资产、唯一差别是不经聚类分组去冗余——隔离「聚类」这一环节
    （plan §1.3 去聚类=全候选一组）。等权建仓，故 R1 单列 PMM（无 EW/MV 之分）。
    """
    selected: dict[pd.Timestamp, list[str]] = {}
    for t, fs in sp_result.fs_panel.items():
        pos = fs.dropna()
        pos = pos[pos > 0.0].sort_values(ascending=False)
        selected[t] = list(pos.index[:max(nc, 1)])
    return selected


def ewmfm_selected(
    signals: dict[pd.Timestamp, pd.DataFrame],
    cluster_labels: dict[str, int],
    factors: list[str],
    test_months: list[pd.Timestamp],
) -> dict[pd.Timestamp, list[str]]:
    """EWMFM（去溢出加权）：FS 等权 Σsignal（γ̃≡1）而非 Σγ̃·signal，每簇选一。

    复用 m5 :func:`aggregate_fs`/:func:`select_per_cluster`，仅把溢出权重 γ̃ 换成全 1
    （宏观因子等权），隔离「溢出加权」这一环节（plan §1.3 去溢出）。等权建仓，R1 单列。
    """
    gamma_eq = pd.Series(1.0, index=factors)
    selected: dict[pd.Timestamp, list[str]] = {}
    for t in test_months:
        sig = signals.get(t)
        if sig is None or sig.empty:
            selected[t] = []
            continue
        fs = aggregate_fs(sig, gamma_eq)
        picks, _detail = select_per_cluster(fs, cluster_labels, fs_floor=0.0)
        selected[t] = picks
    return selected


# ---------------------------------------------------------------------------
# 建仓：每月资产集 → 目标权重面板（EW / MV；建仓前 tradeable 过滤）
# ---------------------------------------------------------------------------

def _buildable_at(
    member_mask: Optional[pd.DataFrame],
    tradeable_mask: pd.DataFrame,
    t: pd.Timestamp,
    assets: list[str],
) -> list[str]:
    """建仓前过滤：``assets ∩ tradeable_mask[t]``，member_mask 非 None 时再 ``∩ member_mask[t]``。

    - ``tradeable_mask[t]=True``：非 ST/停牌/涨跌停/次新（AS5/AS8）；
    - ``member_mask[t]=True``：t 月末为**时点指数成分股**（B1，防训练期入选但调仓月 t 已调出
      对应指数的股票仍进组合，CA-CDX-C-01）；member_mask=None 时仅 tradeable 过滤（向后兼容
      m7 robustness 旧调用，其成分过滤由 m7 自理）。
    掩码均为时点 ≤t、无未来函数。任一相关 mask 无该 t 行、或无该 asset 列/值 False → 保守剔除
    （不可建仓）；测试月均在 mask index 内。被过滤后由各建仓逻辑对剩余资产重新归一化。
    """
    if t not in tradeable_mask.index:
        return []
    trow = tradeable_mask.loc[t]
    out = [a for a in assets if a in trow.index and bool(trow[a])]
    if member_mask is not None:
        if t not in member_mask.index:
            return []
        mrow = member_mask.loc[t]
        out = [a for a in out if a in mrow.index and bool(mrow[a])]
    return out


def selected_to_weights(
    selected: dict[pd.Timestamp, list[str]],
    stock_returns: pd.DataFrame,
    tradeable_mask: pd.DataFrame,
    build: str = "ew",
    *,
    member_mask: Optional[pd.DataFrame] = None,
    lam: float = MV_LAMBDA,
    cov_min_obs: int = MV_COV_MIN_OBS,
    mu_window: int = MV_MU_WINDOW,
) -> pd.DataFrame:
    """每月资产集 → 目标权重面板（EW 等权 / MV 均值方差；建仓前 tradeable[+member] 过滤）。

    每调仓月 T 的可建仓集 = ``selected[T] ∩ tradeable_mask[T]``，传入 member_mask 时再
    ``∩ member_mask[T]``（时点成分，B1/CA-CDX-C-01；m6 主链显式传 member 使其生效）；某簇被
    清空则该月不贡献、组合对剩余资产自适应归一化。MV 的协方差与期望收益只用 ``≤T`` 历史
    （stock_returns 至 T 月末，含已实现的 T 月），扩展窗估计（防未来函数，AS11）；空池行留空。

    Args:
        selected: T → 资产集（各模型选股产出）。
        stock_returns: 市场月收益面板（index=月末，columns=股票）。
        tradeable_mask: 可交易掩码（同 index/columns，AS5/AS8）。
        build: 'ew' 等权 / 'mv' 均值方差。
        member_mask: 时点指数成分掩码（B1）；None 时仅 tradeable 过滤（向后兼容）。
        lam/cov_min_obs/mu_window: MV 参数（AS3/AS11）。

    Returns:
        weights_panel（index=调仓月 T 升序，columns=出现过的资产并集，缺失 0）。
    """
    rows: dict[pd.Timestamp, pd.Series] = {}
    for t in sorted(selected.keys()):
        assets = [a for a in selected[t] if a in stock_returns.columns]
        assets = _buildable_at(member_mask, tradeable_mask, t, assets)
        if not assets:
            continue
        if build == "ew":
            rows[t] = equal_weights(assets)
        else:  # mv
            hist = stock_returns.loc[stock_returns.index <= t, assets]
            cov = rolling_cov_estimate(hist, min_obs=cov_min_obs)
            if cov.shape[0] == 0:
                rows[t] = equal_weights(assets)
                continue
            va = list(cov.columns)
            mu = hist[va].tail(mu_window).mean()
            rows[t] = mean_variance_weights(mu, cov, risk_aversion=lam)
    if not rows:
        return pd.DataFrame(dtype=float)
    panel = pd.DataFrame(rows).T.sort_index()
    return panel.fillna(0.0)


# ---------------------------------------------------------------------------
# 外部基准权重面板（同候选池 + 滚动 ≤T 协方差 / OLMAR 在线）
# ---------------------------------------------------------------------------

def hierarchical_panel(
    candidates: list[str],
    stock_returns: pd.DataFrame,
    member_mask: pd.DataFrame,
    tradeable_mask: pd.DataFrame,
    test_months: list[pd.Timestamp],
    method: str,
    *,
    cov_min_obs: int = MV_COV_MIN_OBS,
) -> pd.DataFrame:
    """HRP/HERC/NCO 在候选池上逐月建仓：member∩tradeable 过滤 → ≤T 历史滚动协方差 → 层次配置权重。

    每月可建仓集 = ``candidates ∩ member_mask[t] ∩ tradeable_mask[t]``（CA-CDX-C-01），
    协方差与权重在过滤后的资产上估计/分配。

    Args:
        method: 'hrp' | 'herc' | 'nco'。
    """
    fn = {"hrp": hrp_weights, "herc": herc_weights, "nco": nco_weights}[method]
    rows: dict[pd.Timestamp, pd.Series] = {}
    for t in test_months:
        assets = [c for c in candidates if c in stock_returns.columns]
        assets = _buildable_at(member_mask, tradeable_mask, t, assets)
        if len(assets) < 2:
            if assets:
                rows[t] = equal_weights(assets)
            continue
        hist = stock_returns.loc[stock_returns.index <= t, assets]
        cov = rolling_cov_estimate(hist, min_obs=cov_min_obs)
        if cov.shape[0] < 2:
            rows[t] = equal_weights(assets)
            continue
        rows[t] = fn(cov)
    if not rows:
        return pd.DataFrame(dtype=float)
    return pd.DataFrame(rows).T.sort_index().fillna(0.0)


def olmar_panel(
    candidates: list[str],
    stock_returns: pd.DataFrame,
    member_mask: pd.DataFrame,
    tradeable_mask: pd.DataFrame,
    test_months: list[pd.Timestamp],
    month_ends: pd.DatetimeIndex,
    *,
    window: int = OLMAR_WINDOW_M,
    epsilon: float = OLMAR_EPSILON_M,
) -> pd.DataFrame:
    """OLMAR 在候选池上在线建仓：用 ≤T 最近 window 期价格相对做均值回归更新，权重跨期传递。

    在线学习需固定资产集以传递权重，故**在线状态 prev_w 在候选全集上更新**（收益缺失月价格
    相对置 1=不变，保持连续性）；但**每月输出建仓权重按 member∩tradeable 掩码 + 重新归一化**
    （CA-CDX-C-01：仅在时点成分且可交易资产上实际建仓），在线连续性与成分过滤两不误。
    """
    R = stock_returns.reindex(month_ends)
    assets = [c for c in candidates if c in R.columns]
    if not assets:
        return pd.DataFrame(dtype=float)
    pos_of = {ts: i for i, ts in enumerate(month_ends)}
    prev_w = np.ones(len(assets)) / len(assets)
    rows: dict[pd.Timestamp, pd.Series] = {}
    for t in test_months:
        pos_t = pos_of[t]
        lo = max(0, pos_t - window + 1)
        win = R[assets].iloc[lo: pos_t + 1]
        pr = (1.0 + win).to_numpy(dtype=float)
        pr = np.where(np.isfinite(pr) & (pr > 0), pr, 1.0)      # 缺失/非法→价格相对 1
        w_new = olmar_weights(pr, prev_w, epsilon=epsilon)
        prev_w = w_new                                          # 在线状态：候选全集传递（连续性）
        # 建仓权重：member∩tradeable 掩码 + 归一化（CA-CDX-C-01）
        buildable = _buildable_at(member_mask, tradeable_mask, t, assets)
        if not buildable:
            continue
        w_series = pd.Series(w_new, index=assets).reindex(buildable)
        s = float(w_series.sum())
        rows[t] = w_series / s if s > 0 else equal_weights(buildable)
    if not rows:
        return pd.DataFrame(dtype=float)
    return pd.DataFrame(rows).T.sort_index().fillna(0.0)


# ---------------------------------------------------------------------------
# 指标（B7）：AR/AStd/SR/PSR/SOR/MR/MDD/VaR/累计收益（复用 common.utils）
# ---------------------------------------------------------------------------

def compute_metrics(
    port_returns: pd.Series,
    benchmark_returns: pd.Series,
    rf: pd.Series,
    *,
    periods_per_year: int = PERIODS_PER_YEAR,
    nav: Optional[pd.Series] = None,
) -> dict[str, float]:
    """组合月收益 → B7 全套指标（算术年化，使表内 SR=AR_excess/AStd 自洽，对齐 spec 式18）。

    Args:
        port_returns: 组合净期收益（index=收益实现月）。
        benchmark_returns: 基准（指数）月收益（Modigliani σ_b 用；自动对齐 index）。
        rf: 月度无风险利率（自动对齐；SR/SOR/MR 用其区间均值作 per-period rf）。
        nav: 组合净值（回撤/累计用；None 时由 port_returns 累乘）。
    """
    r = port_returns.dropna()
    empty = {k: float("nan") for k in
             ("AR", "AStd", "SR", "PSR", "SOR", "MR", "MDD", "VaR", "cum_return", "n_periods")}
    if r.empty:
        return empty
    rf_aligned = rf.reindex(r.index).ffill().fillna(0.0)
    rf_mean = float(rf_aligned.mean())
    bench = benchmark_returns.reindex(r.index).dropna()
    if nav is None:
        nav = (1.0 + r).cumprod()
    return {
        "AR": calculate_arithmetic_annual_return(r, periods_per_year),
        "AStd": calculate_annualized_volatility(r, periods_per_year),
        "SR": calculate_sharpe(r, rf=rf_mean, periods_per_year=periods_per_year),
        "PSR": calculate_psr(r, rf=rf_mean, sr_benchmark=PSR_SR_BENCHMARK),
        "SOR": calculate_sortino(r, rf=rf_mean, periods_per_year=periods_per_year),
        "MR": calculate_modigliani(r, bench if not bench.empty else r,
                                   rf=rf_mean, periods_per_year=periods_per_year),
        "MDD": calculate_max_drawdown(nav),
        "VaR": calculate_historical_var(r, level=VAR_LEVEL),
        "cum_return": float(nav.iloc[-1] - 1.0) if len(nav) else float("nan"),
        "n_periods": int(len(r)),
    }


# ---------------------------------------------------------------------------
# 单模型回测装配
# ---------------------------------------------------------------------------

def _run_one_model(
    market: str,
    model: str,
    weights_panel: pd.DataFrame,
    stock_returns: pd.DataFrame,
    benchmark_returns: pd.Series,
    rf: pd.Series,
    cost_bps: float,
) -> ModelResult:
    """权重面板 → 序贯回测 + 指标（Index 模型走 buy-and-hold 直连）。"""
    if model == "Index":
        # 买入持有：组合收益=指数月收益（对齐到内部模型的收益实现区间在装配处 reindex）
        pr = benchmark_returns.dropna()
        nav = (1.0 + pr).cumprod()
        bt = pd.DataFrame({"port_return": pr, "gross_return": pr,
                           "turnover": 0.0, "cost": 0.0, "nav": nav})
        metrics = compute_metrics(pr, benchmark_returns, rf, nav=nav)
        return ModelResult(market=market, model=model, port_returns=pr, nav=nav,
                           weights_panel=pd.DataFrame(dtype=float), backtest=bt,
                           metrics=metrics, n_rebalance=0, notes="buy-and-hold 指数")
    if weights_panel.empty:
        return ModelResult(market=market, model=model, port_returns=pd.Series(dtype=float),
                           nav=pd.Series(dtype=float), weights_panel=weights_panel,
                           backtest=pd.DataFrame(), metrics=compute_metrics(
                               pd.Series(dtype=float), benchmark_returns, rf),
                           n_rebalance=0, notes="空权重面板（无选股）")
    bt = portfolio_backtest(weights_panel, stock_returns, cost_bps=cost_bps)
    pr = bt["port_return"] if "port_return" in bt.columns else pd.Series(dtype=float)
    nav = bt["nav"] if "nav" in bt.columns else pd.Series(dtype=float)
    metrics = compute_metrics(pr, benchmark_returns, rf, nav=nav)
    metrics["avg_turnover"] = float(bt["turnover"].mean()) if "turnover" in bt.columns else float("nan")
    return ModelResult(market=market, model=model, port_returns=pr, nav=nav,
                       weights_panel=weights_panel, backtest=bt, metrics=metrics,
                       n_rebalance=int(len(weights_panel)))


def run_market_portfolio(
    prep,
    market: str,
    sel_result,
    clus_result,
    sig_result,
    sp_result,
    *,
    cost_bps: float = COST_BPS_FRICTIONLESS,
) -> MarketPortfolio:
    """单市场 11 方法端到端回测（6 内部消融 + 5 外部基准）。"""
    md = prep.markets[market]
    stock_returns = md.stock_returns
    member = md.member_mask                 # 时点指数成分掩码（B1，建仓前叠加过滤，CA-CDX-C-01）
    tradeable = md.tradeable_mask
    index_returns = md.index_returns
    rf = prep.rf
    month_ends = prep.month_ends
    test_months = list(sig_result.test_months)
    factors = list(sig_result.factors)
    candidates = list(sel_result.candidates)
    cluster_labels = dict(clus_result.cluster_labels)
    nc = int(clus_result.nc)
    w = int(sig_result.optimal_w)

    mp = MarketPortfolio(market=market, index_code=md.code,
                         regime_tier=sp_result.regime_tier, nc=nc)

    # excluded 市场：无选股，仅跑外部基准 + Index（如实报告，plan §九 主轴仍在 hs300）
    excluded = (sp_result.regime_tier == "excluded_narrow_pool" or sp_result.status == "excluded")

    # ---- 选股（四个内部模型的每月资产集）----
    sel_cpmm = {} if excluded else cpmm_selected(sp_result)
    sel_cpm = {} if excluded else cpm_selected(
        stock_returns, candidates, cluster_labels, w, test_months, month_ends)
    sel_pmm = {} if excluded else pmm_selected(sp_result, nc)
    sel_ewmfm = {} if excluded else ewmfm_selected(
        sig_result.signals, cluster_labels, factors, test_months)

    # ---- 权重面板 ----
    panels: dict[str, pd.DataFrame] = {
        "CPMM-EW": selected_to_weights(sel_cpmm, stock_returns, tradeable, "ew", member_mask=member),
        "CPMM-MV": selected_to_weights(sel_cpmm, stock_returns, tradeable, "mv", member_mask=member),
        "CPM-EW": selected_to_weights(sel_cpm, stock_returns, tradeable, "ew", member_mask=member),
        "CPM-MV": selected_to_weights(sel_cpm, stock_returns, tradeable, "mv", member_mask=member),
        "PMM": selected_to_weights(sel_pmm, stock_returns, tradeable, "ew", member_mask=member),
        "EWMFM": selected_to_weights(sel_ewmfm, stock_returns, tradeable, "ew", member_mask=member),
        "HRP": hierarchical_panel(candidates, stock_returns, member, tradeable, test_months, "hrp"),
        "HERC": hierarchical_panel(candidates, stock_returns, member, tradeable, test_months, "herc"),
        "NCO": hierarchical_panel(candidates, stock_returns, member, tradeable, test_months, "nco"),
        "OLMAR": olmar_panel(candidates, stock_returns, member, tradeable, test_months, month_ends),
    }

    # ---- 回测（内部模型先跑以确定收益实现区间，Index 对齐到该区间）----
    for model in INTERNAL_MODELS + ("HRP", "HERC", "NCO", "OLMAR"):
        mp.models[model] = _run_one_model(
            market, model, panels[model], stock_returns, index_returns, rf, cost_bps)

    # Index：对齐到内部模型收益实现区间（用 CPMM-EW 的 port_returns.index；退化用 test 区间）
    ref = mp.models["CPMM-EW"].port_returns
    eval_index = ref.index if len(ref) else index_returns.reindex(month_ends).loc[
        month_ends > (test_months[0] if test_months else prep.test_start)].dropna().index
    idx_pr = index_returns.reindex(eval_index).dropna()
    mp.models["Index"] = _run_one_model(
        market, "Index", pd.DataFrame(), stock_returns, idx_pr, rf, cost_bps)

    if excluded:
        mp.notes = "excluded_narrow_pool：内部消融模型无选股（窄池月频功效不足，AS44）"
    elif sp_result.regime_tier == "Tier2_degraded":
        mp.notes = "Tier2_degraded：选股过滤放宽一档（窄基月频降级，AS44），结果可信度低于主市场"
    return mp


# ---------------------------------------------------------------------------
# 多市场装配 + R1 表 + 累计收益
# ---------------------------------------------------------------------------

def run_portfolio(
    prep,
    selection: Optional[dict] = None,
    clustering: Optional[dict] = None,
    signals: Optional[dict] = None,
    spillover: Optional[dict] = None,
    *,
    cost_bps: float = COST_BPS_FRICTIONLESS,
) -> dict[str, MarketPortfolio]:
    """m6 主入口：三宽基各自 11 方法回测，返回 {市场名: MarketPortfolio}。

    None 的上游按 m2→m5 顺序内部串跑（便于单独冒烟 m6）；main.py 传入已算好的上游避免重复。
    """
    if selection is None:
        from src.ssrn_6115073.selection import run_selection
        selection = run_selection(prep)
    if clustering is None:
        from src.ssrn_6115073.clustering import run_clustering
        clustering = run_clustering(prep, selection)
    if signals is None:
        from src.ssrn_6115073.pattern_matching import run_pattern_matching
        signals = run_pattern_matching(prep, selection)
    if spillover is None:
        from src.ssrn_6115073.spillover import run_spillover
        spillover = run_spillover(prep, selection, clustering, signals)

    results: dict[str, MarketPortfolio] = {}
    for name in prep.markets:
        results[name] = run_market_portfolio(
            prep, name, selection[name], clustering[name], signals[name], spillover[name],
            cost_bps=cost_bps)
    return results


def build_r1_table(portfolios: dict[str, MarketPortfolio]) -> pd.DataFrame:
    """R1/表2：6 比率 × 11 方法 × 3 市场（长表：指标, 市场, 各方法列）。"""
    rows: list[dict] = []
    for ratio in RATIO_ORDER:
        for market, mp in portfolios.items():
            rec: dict = {"指标": ratio, "市场": MARKET_NAMES_CN.get(market, market)}
            for model in ALL_MODELS:
                mr = mp.models.get(model)
                rec[model] = round(mr.metrics.get(ratio, float("nan")), 4) if mr else float("nan")
            rows.append(rec)
    return pd.DataFrame(rows, columns=["指标", "市场", *ALL_MODELS])


def build_extra_table(portfolios: dict[str, MarketPortfolio]) -> pd.DataFrame:
    """补充表：MDD/VaR/累计收益/平均换手 × 11 方法 × 3 市场（R5 累计 + 风险特征）。"""
    rows: list[dict] = []
    for metric in ("cum_return", "MDD", "VaR"):
        for market, mp in portfolios.items():
            rec: dict = {"指标": metric, "市场": MARKET_NAMES_CN.get(market, market)}
            for model in ALL_MODELS:
                mr = mp.models.get(model)
                rec[model] = round(mr.metrics.get(metric, float("nan")), 4) if mr else float("nan")
            rows.append(rec)
    return pd.DataFrame(rows, columns=["指标", "市场", *ALL_MODELS])


def cumulative_returns(mp: MarketPortfolio) -> pd.DataFrame:
    """单市场各模型累计收益曲线（R5/图9-10）：index=月末，columns=模型，值=nav−1（%）。"""
    series: dict[str, pd.Series] = {}
    for model in ALL_MODELS:
        mr = mp.models.get(model)
        if mr is None or mr.nav.empty:
            continue
        series[model] = (mr.nav - 1.0) * 100.0
    if not series:
        return pd.DataFrame(dtype=float)
    return pd.DataFrame(series).sort_index()


# ---------------------------------------------------------------------------
# 冒烟（仅确认可执行 + 打印核心行；不宣布验证/达标结论——归 verify/diagnoser）
# ---------------------------------------------------------------------------

def _smoke() -> None:
    from src.ssrn_6115073.data_prep import prepare_all
    from src.ssrn_6115073.selection import run_selection
    from src.ssrn_6115073.clustering import run_clustering
    from src.ssrn_6115073.pattern_matching import run_pattern_matching
    from src.ssrn_6115073.spillover import run_spillover

    print("=" * 84)
    print("m6 组合构建与回测冒烟 · ssrn_6115073（市场迁移复现；只报数不下结论）")
    print("=" * 84)
    prep = prepare_all()
    sel = run_selection(prep)
    clus = run_clustering(prep, sel)
    sig = run_pattern_matching(prep, sel)
    sp = run_spillover(prep, sel, clus, sig)
    ports = run_portfolio(prep, sel, clus, sig, sp)

    r1 = build_r1_table(ports)
    print("\n[R1/表2 核心行] SR / AR（6比率完整表见 Excel）：")
    for ratio in ("SR", "AR"):
        print(f"\n-- {ratio} --")
        print(r1[r1["指标"] == ratio].to_string(index=False))
    print("\n[累计收益 cum_return（%）]")
    extra = build_extra_table(ports)
    cum = extra[extra["指标"] == "cum_return"].copy()
    for c in ALL_MODELS:
        cum[c] = (cum[c] * 100).round(1)
    print(cum.to_string(index=False))


if __name__ == "__main__":
    _smoke()
