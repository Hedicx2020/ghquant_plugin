"""r001 · 组合回测装配与死票屏蔽（milestone m4：B3 月度调仓 + B6 四指标 + CA-A01/A03）。

职责（严格对 spec/审计前推，页码引用制，对应 coverage_matrix milestone=m4 的 B3/B6）：
- B3 (p8) 月度 k-step 调仓：SIT 每决策日产 K 步权重 w^(1:K)，回测按 receding-horizon 取第 1 步
  w^(1)（config.backtest_decision_step，AS24）作当月目标权重，月度滚动结算实现收益；组合回测
  引擎复用 common.allocation_backtest.portfolio_backtest（信号 T 定权重、T+1 实现收益，未来函数
  红线由该引擎 T→T_next 对齐硬保证）。
- B6 (p5-p6) 四指标零无风险利率：Sharpe/Sortino（复用 common.utils）+ MaxDrawdown（峰谷）+
  Final Wealth（终值净值因子）。
- CA-A01（m1 审计前推，强制）：固定资产集含 test 期 0 覆盖死票（train 起点选样、2015-2017
  退市，AS19）。回测对**不可交易资产权重置 0 并对活票 renormalize**，否则系统性扭曲全部 R/SA。
- CA-A03：持有期 ST/停牌点时屏蔽——不可交易日不将收益抹 0 而作不可交易处理（决策日屏蔽 +
  引擎对 NaN 收益不计贡献；停牌日日收益 m1 已按 0 占位=持现金无损益）。

未来函数红线：可交易掩码只用决策日 t 当日价格 notna 与有效行情区间 [first_date,last_date]
（点时，无未来）；月度收益面板由日频简单收益逐 (t_{prev},t] 区间复利（≤t 实现），portfolio_backtest
只把 t 权重乘 t 之后的下一月收益。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import torch

from common.allocation_backtest import portfolio_backtest, rolling_cov_estimate
from common.data_loader import filter_st_stocks, load_st_data, load_suspend_status
from common.utils import (
    calculate_max_drawdown,
    calculate_sharpe,
    calculate_sortino,
)

from .baselines import (
    dlinear_predict,
    gmv_weights,
    hrp_baseline_weights,
    min_cvar_weights,
)
from .config import DEFAULT_CONFIG, SITConfig


# =====================================================================
# 死票 / 停牌屏蔽（CA-A01 / CA-A03）
# =====================================================================

def _get_status_tables(bundle) -> tuple[pd.DataFrame, dict]:
    """点时 ST / 停牌状态表（CDX-C-03），一次加载缓存到 bundle 实例，避免逐决策日重读盘。

    - ST：``ashare_stock_st``（stock_code, implement_date, remove_date），点时判定用
      ``filter_st_stocks``（implement_date≤t<remove_date 即 ST）。
    - 停牌：``ashare_stock_suspend``（stock_code, date, if_suspend），预分组为
      ``{date: set(当日停牌代码)}`` 供 O(1) 点时查询。
    仅加载本 universe 代码、price_load_start 起的记录（filters 下推，减少读盘）。
    """
    cache = getattr(bundle, "_status_cache", None)
    if cache is None:
        codes = list(bundle.universe_codes)
        st_data = load_st_data()
        susp = load_suspend_status(stock_codes=codes, start_date=bundle.config.price_load_start)
        susp_on = susp[susp["if_suspend"] == 1]
        susp_by_date: dict = susp_on.groupby("date")["stock_code"].agg(set).to_dict()
        cache = (st_data, susp_by_date)
        bundle._status_cache = cache          # 缓存（DataBundle 非 frozen，可挂实例属性）
    return cache


def tradable_mask_at(bundle, date: pd.Timestamp) -> pd.Series:
    """决策日 t 各资产是否可交易（CA-A01/A03，点时，无未来；CDX-C-03 点时查 ST/停牌表）。

    可交易 = 当日前复权 close notna（未退市/有行情）∧ t∈[first_date,last_date]（有效行情区间）
             ∧ **当日非 ST**（点时查 ashare_stock_st）∧ **当日未停牌**（点时查 ashare_stock_suspend）。
    死票（test 期退市、price 全 NaN）、当日 ST、当日停牌均判不可交易——不再以「close 非空」
    替代 ST/停牌状态（旧实现漏判持有期内转 ST 或停牌但仍有非空价的股票）。
    """
    codes = list(bundle.universe_codes)
    ts = pd.Timestamp(date)
    if ts in bundle.daily_prices.index:
        px_ok = bundle.daily_prices.loc[ts].reindex(codes).notna()
    else:
        px_ok = pd.Series(False, index=codes)
    meta = bundle.universe_meta.reindex(codes)
    within = (ts >= meta["first_date"]) & (ts <= meta["last_date"])   # NaT 比较→False（无效区间即不可交易）

    st_data, susp_by_date = _get_status_tables(bundle)
    non_st = filter_st_stocks(pd.Series(codes), ts, st_data)          # 点时非 ST 代码集（Index）
    st_ok = pd.Series(codes, index=codes).isin(non_st)               # True=当日非 ST
    suspended_today = susp_by_date.get(ts, set())                    # 当日停牌代码集（点时）
    susp_ok = ~pd.Series(codes, index=codes).isin(suspended_today)   # True=当日未停牌

    return (px_ok & within.fillna(False) & st_ok & susp_ok).astype(bool)


def mask_renormalize(weights: pd.Series, mask: pd.Series) -> pd.Series:
    """不可交易资产权重置 0，对活票 renormalize 至和为 1（CA-A01）。

    全不可交易的极端情形回退活票等权（此处活票为空→保留 0 向量，由引擎跳过）。
    """
    w = weights.copy().astype(float)
    w[~mask.reindex(w.index).fillna(False)] = 0.0
    total = w.sum()
    if total > 0:
        return w / total
    active = mask.reindex(w.index).fillna(False)
    n_active = int(active.sum())
    if n_active > 0:
        return active.astype(float) / n_active
    return w * 0.0


# =====================================================================
# 月度收益面板（B3 结算母源）
# =====================================================================

def build_monthly_returns(
    bundle,
    config: SITConfig = DEFAULT_CONFIG,
    terminal_date: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """月度简单收益面板（index=月末调仓日, columns=资产），供 portfolio_backtest 结算。

    每行 = 相邻调仓日 (t_prev, t] 区间日简单收益复利（daily_simple_returns，停牌期 0 占位，AS19）。
    该行收益在 t 已实现（≤t，点时安全）；portfolio_backtest 会把 t_prev 的权重乘该行（t>t_prev），
    实现「信号 T 算、T+1 执行」。

    **终端结算（CDX-C-05）**：``terminal_date`` 晚于最后调仓日时（如 test_end=2024-12-27 非
    月末、其后无月末调仓收益），追加一条终端锚 = (最后调仓日, terminal_date] 的部分月区间收益，
    使最后一个月末信号（如 2024-11-29 权重）能承接至 test_end 的实现收益、不被丢弃。
    """
    rb = pd.DatetimeIndex(bundle.rebalance_dates)
    if terminal_date is not None:
        td = pd.Timestamp(terminal_date)
        if len(rb) > 0 and td > rb[-1]:
            rb = rb.append(pd.DatetimeIndex([td]))              # 追加终端结算锚（部分月）
    simple = bundle.daily_simple_returns
    codes = list(bundle.universe_codes)
    rows: dict[pd.Timestamp, pd.Series] = {}
    prev: Optional[pd.Timestamp] = None
    for t in rb:
        if prev is not None:
            seg = simple.loc[(simple.index > prev) & (simple.index <= t)]
            if len(seg) > 0:
                comp = (1.0 + seg.reindex(columns=codes)).prod(axis=0) - 1.0
                rows[t] = comp
        prev = t
    if not rows:
        return pd.DataFrame(columns=codes)
    return pd.DataFrame(rows).T.reindex(columns=codes).sort_index()


def _history_leq(monthly: pd.DataFrame, date: pd.Timestamp, window: int) -> pd.DataFrame:
    """决策日 t 之前（含 t）最近 window 期月度收益（≤t 点时；剔全缺资产列）。"""
    hist = monthly.loc[monthly.index <= pd.Timestamp(date)]
    if window > 0:
        hist = hist.tail(window)
    return hist.dropna(axis=1, how="all")


# =====================================================================
# test 覆盖构造 helper（CDX-C-05：run_pipeline / strategy / ablation 统一 60 期口径）
# =====================================================================

def test_coverage_decision_dates(bundle, config: SITConfig = DEFAULT_CONFIG) -> pd.DatetimeIndex:
    """60 期覆盖的 test 决策日：test 前最后一个调仓日（预热，约 2019-12-31）+ test 调仓日。

    预热决策日权重承接 test 首月（2020-01）实现收益，否则首月缩水（首实现日推迟到 2020-02）；
    与 build_test_monthly 的终端锚配套，使回测覆盖统一为 60 期（首≈2020-01-23、末≈2024-12-27）。
    run_pipeline / SITStrategy / ablation 三入口共用本 helper，消除 58/60 期口径分叉（CDX-C-05）。
    """
    rb_all = pd.DatetimeIndex(bundle.rebalance_dates)
    pre_test = rb_all[rb_all < pd.Timestamp(config.test_start)]
    warm = pd.DatetimeIndex([pre_test[-1]]) if len(pre_test) else pd.DatetimeIndex([])
    test_dates = pd.DatetimeIndex(bundle.splits["test"])
    return warm.append(test_dates).unique().sort_values()


def build_test_monthly(bundle, config: SITConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """test 段月度收益面板（含终端锚 terminal_date=test_end，末端不缩水，CDX-C-05）。"""
    return build_monthly_returns(bundle, config, terminal_date=config.test_end)


def clip_test_backtest(bt: pd.DataFrame, config: SITConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    """裁剪回测到 [test_start, test_end] + 60 期覆盖/首末日硬断言（ValueError，非 -O 可移除 assert）。

    统一 run_pipeline / strategy / ablation 三入口的 test 回测覆盖：裁剪后应恰为
    periods_per_year×5=60 期，首实现日落 test 首月（承接 2020-01，预热生效）、末实现日落
    test 末月（承接至 test_end，终端锚生效）。断言用 ValueError 而非 assert——python -O 优化
    模式会移除 assert，覆盖异常须在任何运行模式下都硬失败（CDX-C-05）。
    """
    lo, hi = pd.Timestamp(config.test_start), pd.Timestamp(config.test_end)
    if bt.empty:
        return bt
    bt = bt.loc[(bt.index >= lo) & (bt.index <= hi)]
    if bt.empty:
        return bt
    n_periods = len(bt)
    target = config.periods_per_year * 5
    first, last = bt.index.min(), bt.index.max()
    if n_periods != target:
        raise ValueError(
            f"test 回测期数 {n_periods} ≠ 目标 {target}（60 期覆盖异常，CDX-C-05）；"
            f"首实现日={first.date()} 末实现日={last.date()}"
        )
    if first >= lo + pd.offsets.MonthEnd(2):
        raise ValueError(
            f"回测首实现日 {first.date()} 晚于 test 首月，前端缩水（预热未生效，CDX-C-05）"
        )
    if last <= hi - pd.offsets.MonthEnd(2):
        raise ValueError(
            f"回测末实现日 {last.date()} 早于 test 末月，末端缩水（终端锚未生效，CDX-C-05）"
        )
    return bt


# =====================================================================
# SIT 权重面板（月度 w^(1)，死票屏蔽）
# =====================================================================

@torch.no_grad()
def sit_weight_panel(
    model,
    feat: dict,
    bundle,
    config: SITConfig = DEFAULT_CONFIG,
    tau: Optional[float] = None,
) -> pd.DataFrame:
    """SIT 各决策日 → 月度目标权重面板（取 K 步第 1 步 w^(1)，死票屏蔽 renorm）。"""
    model.eval()
    dates = pd.DatetimeIndex(feat["decision_dates"])
    codes = list(bundle.universe_codes)
    w_all = model.forward_from_features(feat, tau=tau)          # (N,K,d)
    step = config.backtest_decision_step
    w_step = w_all[:, step, :].cpu().numpy()                    # (N,d) w^(1)
    rows = {}
    for i, d in enumerate(dates):
        raw = pd.Series(w_step[i], index=codes)
        rows[d] = mask_renormalize(raw, tradable_mask_at(bundle, d))
    return pd.DataFrame(rows).T.reindex(columns=codes)


# =====================================================================
# 基线权重面板（EW/GMV/CVaR/HRP + DLinear 两阶段，均死票屏蔽）
# =====================================================================

def baseline_weight_panel(
    name: str,
    bundle,
    decision_dates: pd.DatetimeIndex,
    monthly: pd.DataFrame,
    config: SITConfig = DEFAULT_CONFIG,
    *,
    dlinear_model=None,
    hist_windows: Optional[dict] = None,
    log_fn=None,
) -> pd.DataFrame:
    """构造某基线在各决策日的月度权重面板（活票上求权重，天然死票屏蔽）。

    Args:
        name: "EW"/"GMV"/"CVaR"/"HRP"/"DLinear"。
        bundle: m1 数据底座。
        decision_dates: 决策日（test 调仓日）。
        monthly: 月度收益面板（build_monthly_returns，供协方差/场景估计）。
        dlinear_model/hist_windows: 仅 DLinear 需要（预测器 + 各决策日日频回看窗口 {date:(d,H)}）。
    """
    codes = list(bundle.universe_codes)
    rows: dict[pd.Timestamp, pd.Series] = {}
    for d in pd.DatetimeIndex(decision_dates):
        mask = tradable_mask_at(bundle, d)
        active = [c for c in codes if bool(mask.get(c, False))]
        if not active:
            rows[d] = pd.Series(0.0, index=codes)
            continue
        w = pd.Series(0.0, index=codes)

        if name == "EW":
            w[active] = 1.0 / len(active)
        elif name in ("GMV", "HRP", "CVaR"):
            hist = _history_leq(monthly, d, config.cvar_scenario_window if name == "CVaR"
                                else config.cov_estimate_window)
            hist = hist.reindex(columns=[c for c in active if c in hist.columns]).dropna(axis=1, how="all")
            cols = list(hist.columns)
            if len(cols) < 2 or hist.shape[0] < config.cvar_min_scenarios:
                w[active] = 1.0 / len(active)                   # 历史不足回退等权
            elif name == "GMV":
                cov = rolling_cov_estimate(hist, min_obs=config.cvar_min_scenarios)
                sol = gmv_weights(cov)
                w.loc[sol.index] = sol.to_numpy()
            elif name == "HRP":
                cov = rolling_cov_estimate(hist, min_obs=config.cvar_min_scenarios)
                sol = hrp_baseline_weights(cov)
                w.loc[sol.index] = sol.to_numpy()
            else:  # CVaR：Rockafellar-Uryasev min-CVaR（历史月度场景）
                scen = hist.fillna(0.0).to_numpy(dtype=float)
                sol = min_cvar_weights(
                    scen, config.cvar_alpha,
                    context=f"CVaR@{pd.Timestamp(d).date()} n_active={len(active)} S={scen.shape[0]}",
                    log_fn=log_fn,
                )
                w.loc[cols] = sol
        elif name == "DLinear":
            if dlinear_model is None or hist_windows is None or d not in hist_windows:
                w[active] = 1.0 / len(active)
            else:
                pred = dlinear_predict(dlinear_model, hist_windows[d][None, ...])[0]  # (K,d)
                r_hat_all = pred[config.backtest_decision_step]                        # 下期预测收益 (d,)
                idx_active = [codes.index(c) for c in active]
                r_hat = r_hat_all[idx_active]
                scen_hist = _history_leq(monthly, d, config.cvar_scenario_window)
                scen_hist = scen_hist.reindex(columns=active).fillna(0.0)
                if scen_hist.shape[0] < config.cvar_min_scenarios:
                    w[active] = 1.0 / len(active)
                else:
                    mu_target = float(np.mean(r_hat))          # 等权组合预测收益（EW 可行，AS26）
                    sol = min_cvar_weights(
                        scen_hist.to_numpy(dtype=float), config.cvar_alpha,
                        exp_ret=r_hat, mu_target=mu_target,
                        context=f"DLinear@{pd.Timestamp(d).date()} n_active={len(active)} S={scen_hist.shape[0]}",
                        log_fn=log_fn,
                    )
                    w.loc[active] = sol
        else:
            raise ValueError(f"未知基线 name={name!r}")

        rows[d] = mask_renormalize(w, mask)
    return pd.DataFrame(rows).T.reindex(columns=codes)


# =====================================================================
# 回测执行 + 四指标（B3/B6，复用 common）
# =====================================================================

def run_portfolio(
    weights_panel: pd.DataFrame,
    monthly: pd.DataFrame,
    config: SITConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """复用 common.portfolio_backtest 序贯回测（月度、cost=config.cost_bps=0bps 主表）。"""
    return portfolio_backtest(weights_panel, monthly, cost_bps=config.cost_bps)


def performance_metrics(bt: pd.DataFrame, config: SITConfig = DEFAULT_CONFIG) -> dict:
    """B6 四指标：Sharpe/Sortino（年化、零 rf）+ MaxDrawdown + Final Wealth（终值净值）。"""
    if bt.empty or "port_return" not in bt.columns:
        return {"Sharpe": float("nan"), "Sortino": float("nan"),
                "MaxDrawdown": float("nan"), "FinalWealth": float("nan"), "n_periods": 0}
    r = bt["port_return"].astype(float)
    nav = bt["nav"].astype(float)
    return {
        "Sharpe": calculate_sharpe(r, rf=config.risk_free_rate, periods_per_year=config.periods_per_year),
        "Sortino": calculate_sortino(r, rf=config.risk_free_rate, periods_per_year=config.periods_per_year),
        "MaxDrawdown": calculate_max_drawdown(nav),
        "FinalWealth": float(nav.iloc[-1]) if len(nav) else float("nan"),
        "n_periods": int(len(r)),
    }
