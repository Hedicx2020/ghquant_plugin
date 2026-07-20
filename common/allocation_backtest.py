"""通用资产配置回测引擎（allocation 类首个案例 ssrn_6115073 沉淀）。

按 ``templates/allocation.md`` 接口规范提供权重模型与序贯回测原语，供后续所有
allocation 类研报复用，**不得写进 src/**：

权重模型
  - :func:`equal_weights`            等权（EW）
  - :func:`mean_variance_weights`    Markowitz 均值方差（长仓 λ，含约束）
  - :func:`risk_parity_weights`      风险平价（等风险贡献）
  - :func:`risk_budget_weights`      给定风险预算权重
  - :func:`hrp_weights`              Hierarchical Risk Parity（López de Prado 2016）
  - :func:`herc_weights`             Hierarchical Equal Risk Contribution
  - :func:`nco_weights`              Nested Clustered Optimization
  - :func:`olmar_weights`            On-Line Moving Average Reversion 单步更新

回测
  - :func:`portfolio_backtest`       目标权重面板 → 序贯净值/换手/成本/资产贡献
    （信号 T 定权重、T+1 实现收益——未来函数红线由 T→T_next 对齐硬保证）

依赖：numpy + scipy（本环境无 sklearn/statsmodels/cvxpy；层次聚类用
``scipy.cluster.hierarchy``，MV/风险平价优化用 ``scipy.optimize``）。绩效指标复用
``common.utils``（Sharpe/Sortino/PSR/Modigliani/VaR/MDD）。
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage
from scipy.optimize import minimize
from scipy.spatial.distance import squareform

# ---------------------------------------------------------------------------
# 引擎级常量（通用默认；策略特有取值由调用方 src 传入，可反查各案例 assumptions）
# ---------------------------------------------------------------------------
COV_RIDGE: float = 1e-8          # 协方差正则（防近奇异，MV/HRP/NCO 求解稳定）
RP_MAX_ITER: int = 500           # 风险平价迭代上限
RP_TOL: float = 1e-9             # 风险平价收敛容差
OLMAR_EPSILON: float = 10.0      # OLMAR 均值回归阈值 ε（Li & Hoi 2012 默认区间）
OLMAR_WINDOW: int = 5            # OLMAR SMA 窗口（月频下取 5）


# ---------------------------------------------------------------------------
# 基础：单纯形投影 / 协方差→相关 / 权重规整
# ---------------------------------------------------------------------------

def simplex_projection(v: np.ndarray) -> np.ndarray:
    """欧氏投影到概率单纯形 ``{w : w>=0, sum(w)=1}``（Duchi 2008）。

    OLPS 长仓满仓约束（spec F1 单纯形 ∆m）与 OLMAR 更新后的可行化都用它。

    Args:
        v: 任意实向量。

    Returns:
        投影后的权重向量（非负、和为 1）。
    """
    n = v.size
    if n == 0:
        return v
    u = np.sort(v)[::-1]
    cssv = np.cumsum(u) - 1.0
    ind = np.arange(1, n + 1)
    cond = u - cssv / ind > 0
    if not cond.any():
        return np.ones(n) / n
    rho = ind[cond][-1]
    theta = cssv[cond][-1] / rho
    return np.maximum(v - theta, 0.0)


def _normalize_long(w: np.ndarray) -> np.ndarray:
    """裁负 + 归一化为长仓满仓权重（数值兜底）。"""
    w = np.clip(np.asarray(w, dtype=float), 0.0, None)
    s = w.sum()
    return w / s if s > 0 else np.ones(w.size) / max(w.size, 1)


def cov_to_corr(cov: pd.DataFrame) -> pd.DataFrame:
    """协方差矩阵 → 相关矩阵（对角标准差归一）。"""
    std = np.sqrt(np.clip(np.diag(cov.to_numpy(dtype=float)), 1e-16, None))
    corr = cov.to_numpy(dtype=float) / np.outer(std, std)
    corr = np.clip(corr, -1.0, 1.0)
    np.fill_diagonal(corr, 1.0)
    return pd.DataFrame(corr, index=cov.index, columns=cov.columns)


def _ridge_cov(cov: pd.DataFrame, ridge: float = COV_RIDGE) -> np.ndarray:
    """协方差加对角正则，返回 numpy（防奇异）。"""
    m = cov.to_numpy(dtype=float).copy()
    m += np.eye(m.shape[0]) * ridge
    return m


# ---------------------------------------------------------------------------
# EW / MV / 风险平价 / 风险预算
# ---------------------------------------------------------------------------

def equal_weights(assets: Sequence[str]) -> pd.Series:
    """等权组合（EW）：每资产 1/n。

    Args:
        assets: 资产代码列表。

    Returns:
        权重 Series（index=asset，和为 1）。空池返回空 Series。
    """
    assets = list(assets)
    n = len(assets)
    if n == 0:
        return pd.Series(dtype=float)
    return pd.Series(np.ones(n) / n, index=assets)


def mean_variance_weights(
    exp_ret: pd.Series,
    cov: pd.DataFrame,
    bounds: Optional[Sequence[tuple[float, float]]] = None,
    risk_aversion: float = 1.0,
) -> pd.Series:
    """Markowitz 均值方差最优权重：``max wᵀμ − λ·wᵀΣw``，长仓满仓（spec F11 / AS11）。

    约束 ``Σw=1`` + ``bounds``（默认 ``[0,1]`` 长仓、无卖空，与 F1 单纯形一致）。
    用 SLSQP 数值求解；退化（不收敛/奇异）时回退等权。

    Args:
        exp_ret: 各资产期望收益 μ（index=asset）。
        cov: 资产协方差矩阵 Σ（index/columns=asset，与 exp_ret 对齐）。
        bounds: 各资产权重上下界；None → 全部 (0,1)。
        risk_aversion: 风险厌恶系数 λ（AS3 基准 1.0）。

    Returns:
        权重 Series（index=asset，非负、和为 1）。
    """
    assets = list(exp_ret.index)
    n = len(assets)
    if n == 0:
        return pd.Series(dtype=float)
    if n == 1:
        return pd.Series([1.0], index=assets)

    mu = exp_ret.to_numpy(dtype=float)
    sigma = _ridge_cov(cov.loc[assets, assets])
    bnds = list(bounds) if bounds is not None else [(0.0, 1.0)] * n

    def neg_utility(w: np.ndarray) -> float:
        return float(-(w @ mu - risk_aversion * (w @ sigma @ w)))

    def neg_utility_grad(w: np.ndarray) -> np.ndarray:
        return -(mu - 2.0 * risk_aversion * (sigma @ w))

    cons = ({"type": "eq", "fun": lambda w: w.sum() - 1.0,
             "jac": lambda w: np.ones(n)},)
    w0 = np.ones(n) / n
    try:
        res = minimize(neg_utility, w0, jac=neg_utility_grad, method="SLSQP",
                       bounds=bnds, constraints=cons,
                       options={"maxiter": 300, "ftol": 1e-10})
        w = res.x if res.success else w0
    except (ValueError, np.linalg.LinAlgError):
        w = w0
    return pd.Series(_normalize_long(w), index=assets)


def _risk_contributions(w: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """各资产对组合方差的边际风险贡献 ``w_i·(Σw)_i``。"""
    return w * (sigma @ w)


def risk_parity_weights(cov: pd.DataFrame) -> pd.Series:
    """风险平价（等风险贡献 ERC）权重：各资产风险贡献相等，长仓满仓。

    循环坐标下降迭代（对数障碍不用，直接归一化更新），奇异时回退逆波动率。

    Args:
        cov: 资产协方差矩阵。

    Returns:
        权重 Series（非负、和为 1）。
    """
    assets = list(cov.index)
    n = len(assets)
    if n == 0:
        return pd.Series(dtype=float)
    if n == 1:
        return pd.Series([1.0], index=assets)

    sigma = _ridge_cov(cov)
    vol = np.sqrt(np.clip(np.diag(sigma), 1e-16, None))
    w = (1.0 / vol) / (1.0 / vol).sum()          # 逆波动率初值
    target = 1.0 / n
    for _ in range(RP_MAX_ITER):
        rc = _risk_contributions(w, sigma)
        port_var = w @ sigma @ w
        if port_var <= 0:
            break
        rc_norm = rc / port_var
        if np.max(np.abs(rc_norm - target)) < RP_TOL:
            break
        # 乘性更新：欠配（rc 小）资产加权
        w = w * (target / np.clip(rc_norm, 1e-16, None)) ** 0.5
        w = _normalize_long(w)
    return pd.Series(_normalize_long(w), index=assets)


def risk_budget_weights(cov: pd.DataFrame, budget: pd.Series) -> pd.Series:
    """给定风险预算 b_i（Σb=1）的权重：各资产风险贡献占比匹配预算。

    Args:
        cov: 资产协方差矩阵。
        budget: 目标风险贡献占比（index=asset，和为 1）。

    Returns:
        权重 Series（非负、和为 1）。
    """
    assets = list(cov.index)
    n = len(assets)
    if n == 0:
        return pd.Series(dtype=float)
    if n == 1:
        return pd.Series([1.0], index=assets)

    sigma = _ridge_cov(cov)
    b = budget.reindex(assets).fillna(1.0 / n).to_numpy(dtype=float)
    b = b / b.sum()
    vol = np.sqrt(np.clip(np.diag(sigma), 1e-16, None))
    w = (1.0 / vol) / (1.0 / vol).sum()
    for _ in range(RP_MAX_ITER):
        rc = _risk_contributions(w, sigma)
        port_var = w @ sigma @ w
        if port_var <= 0:
            break
        rc_norm = rc / port_var
        if np.max(np.abs(rc_norm - b)) < RP_TOL:
            break
        w = w * (b / np.clip(rc_norm, 1e-16, None)) ** 0.5
        w = _normalize_long(w)
    return pd.Series(_normalize_long(w), index=assets)


# ---------------------------------------------------------------------------
# 层次配置基准：HRP / HERC / NCO（López de Prado）
# ---------------------------------------------------------------------------

def _corr_distance(corr: pd.DataFrame) -> np.ndarray:
    """相关矩阵 → 距离阵 d=sqrt(0.5(1−corr))（López de Prado），返回压缩形。"""
    d = np.sqrt(np.clip(0.5 * (1.0 - corr.to_numpy(dtype=float)), 0.0, None))
    np.fill_diagonal(d, 0.0)
    return squareform(d, checks=False)


def _quasi_diag(link: np.ndarray) -> list[int]:
    """层次树 → 准对角叶子顺序（HRP 步骤 2）。"""
    link = link.astype(int)
    n = link.shape[0] + 1
    order = [link[-1, 0], link[-1, 1]]
    while max(order) >= n:
        new: list[int] = []
        for item in order:
            if item < n:
                new.append(item)
            else:
                merged = link[item - n]
                new.extend([int(merged[0]), int(merged[1])])
        order = new
    return order


def _cluster_var(cov: pd.DataFrame, items: list[str]) -> float:
    """子簇逆方差组合的方差（HRP recursive bisection 用）。"""
    sub = cov.loc[items, items].to_numpy(dtype=float)
    ivp = 1.0 / np.clip(np.diag(sub), 1e-16, None)
    ivp /= ivp.sum()
    return float(ivp @ sub @ ivp)


def hrp_weights(cov: pd.DataFrame) -> pd.Series:
    """Hierarchical Risk Parity（López de Prado 2016）：树聚类 + 准对角 + 递归二分。

    single-linkage 于相关距离聚类，准对角排序后自顶向下按逆簇方差递归分配权重。

    Args:
        cov: 资产协方差矩阵。

    Returns:
        权重 Series（非负、和为 1）。
    """
    assets = list(cov.index)
    n = len(assets)
    if n == 0:
        return pd.Series(dtype=float)
    if n <= 2:
        return risk_parity_weights(cov)

    corr = cov_to_corr(cov)
    link = linkage(_corr_distance(corr), method="single")
    order_idx = _quasi_diag(link)
    sorted_assets = [assets[i] for i in order_idx]

    w = pd.Series(1.0, index=sorted_assets)
    clusters = [sorted_assets]
    while clusters:
        clusters = [c[j:k] for c in clusters
                    for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i + 1]
            v0, v1 = _cluster_var(cov, c0), _cluster_var(cov, c1)
            alpha = 1.0 - v0 / (v0 + v1) if (v0 + v1) > 0 else 0.5
            w[c0] *= alpha
            w[c1] *= 1.0 - alpha
    return w.reindex(assets).pipe(lambda s: s / s.sum())


def herc_weights(cov: pd.DataFrame) -> pd.Series:
    """Hierarchical Equal Risk Contribution：HRP 树结构 + 簇内等风险贡献。

    与 HRP 同用相关距离层次树、准对角与递归二分，差异在**簇内**用等风险贡献
    （风险平价）而非逆方差分配（Raffinot 2018）；弱结构下与 HRP 接近，作对比基准。

    Args:
        cov: 资产协方差矩阵。

    Returns:
        权重 Series（非负、和为 1）。
    """
    assets = list(cov.index)
    n = len(assets)
    if n == 0:
        return pd.Series(dtype=float)
    if n <= 2:
        return risk_parity_weights(cov)

    corr = cov_to_corr(cov)
    link = linkage(_corr_distance(corr), method="single")
    order_idx = _quasi_diag(link)
    sorted_assets = [assets[i] for i in order_idx]

    def _erc_cluster_var(items: list[str]) -> float:
        w_in = risk_parity_weights(cov.loc[items, items]).reindex(items).to_numpy()
        sub = cov.loc[items, items].to_numpy(dtype=float)
        return float(w_in @ sub @ w_in)

    w = pd.Series(1.0, index=sorted_assets)
    clusters = [sorted_assets]
    while clusters:
        clusters = [c[j:k] for c in clusters
                    for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i + 1]
            v0, v1 = _erc_cluster_var(c0), _erc_cluster_var(c1)
            alpha = 1.0 - v0 / (v0 + v1) if (v0 + v1) > 0 else 0.5
            w[c0] *= alpha
            w[c1] *= 1.0 - alpha
    # 簇内再按 ERC 细分（叶子层）
    return w.reindex(assets).pipe(lambda s: s / s.sum())


def _min_variance_weights(cov: pd.DataFrame) -> pd.Series:
    """长仓最小方差权重（NCO 簇内/簇间子问题；退化回退等权）。"""
    assets = list(cov.index)
    n = len(assets)
    if n == 0:
        return pd.Series(dtype=float)
    if n == 1:
        return pd.Series([1.0], index=assets)
    sigma = _ridge_cov(cov)
    try:
        inv = np.linalg.inv(sigma)
        ones = np.ones(n)
        w = inv @ ones
        if w.sum() != 0:
            w = w / w.sum()
        if (w < 0).any():                       # 有卖空 → SLSQP 长仓
            return mean_variance_weights(
                pd.Series(np.zeros(n), index=assets), cov, risk_aversion=1e6)
        return pd.Series(w, index=assets)
    except np.linalg.LinAlgError:
        return equal_weights(assets)


def nco_weights(cov: pd.DataFrame, exp_ret: Optional[pd.Series] = None,
                max_clusters: Optional[int] = None) -> pd.Series:
    """Nested Clustered Optimization（López de Prado 2019）：簇内 + 簇间两层最小方差。

    相关距离层次聚类切成若干簇（默认 sqrt(n) 簇），簇内做长仓最小方差得簇组合，
    簇间用簇组合的降维协方差再做最小方差，最后合并为资产级权重。exp_ret 保留
    接口（本迁移用最小方差口径，故未消费）。

    Args:
        cov: 资产协方差矩阵。
        exp_ret: 期望收益（可选，当前实现用最小方差不消费）。
        max_clusters: 簇数上限；None → round(sqrt(n))。

    Returns:
        权重 Series（非负、和为 1）。
    """
    from scipy.cluster.hierarchy import fcluster

    assets = list(cov.index)
    n = len(assets)
    if n == 0:
        return pd.Series(dtype=float)
    if n <= 2:
        return _min_variance_weights(cov)

    corr = cov_to_corr(cov)
    link = linkage(_corr_distance(corr), method="ward")
    k = max_clusters if max_clusters else max(2, int(round(np.sqrt(n))))
    labels = fcluster(link, t=k, criterion="maxclust")

    intra = pd.Series(0.0, index=assets)
    cluster_rets = {}                            # 簇 → 簇内组合的"收益代表"（用于簇间协方差）
    cluster_members: dict[int, list[str]] = {}
    for cid in np.unique(labels):
        members = [assets[i] for i in range(n) if labels[i] == cid]
        cluster_members[cid] = members
        w_in = _min_variance_weights(cov.loc[members, members]).reindex(members)
        intra.loc[members] = w_in.to_numpy()
        cluster_rets[cid] = (members, w_in)

    # 簇间协方差：Σ_cluster[a,b] = w_a^T Σ[members_a, members_b] w_b
    cids = list(cluster_members.keys())
    kc = len(cids)
    reduced = np.zeros((kc, kc))
    for a in range(kc):
        ma, wa = cluster_rets[cids[a]]
        for b in range(kc):
            mb, wb = cluster_rets[cids[b]]
            reduced[a, b] = wa.to_numpy() @ cov.loc[ma, mb].to_numpy(dtype=float) @ wb.to_numpy()
    inter = _min_variance_weights(
        pd.DataFrame(reduced, index=cids, columns=cids))

    w = pd.Series(0.0, index=assets)
    for a, cid in enumerate(cids):
        members = cluster_members[cid]
        w.loc[members] = intra.loc[members].to_numpy() * float(inter.iloc[a])
    return w.pipe(lambda s: s / s.sum() if s.sum() > 0 else equal_weights(assets))


# ---------------------------------------------------------------------------
# OLPS 基准：OLMAR（On-Line Moving Average Reversion，Li & Hoi 2012）
# ---------------------------------------------------------------------------

def olmar_weights(
    price_relative_window: np.ndarray,
    prev_weights: np.ndarray,
    epsilon: float = OLMAR_EPSILON,
) -> np.ndarray:
    """OLMAR-1 单步更新（SMA 均值回归预测 + 被动激进单纯形投影更新）。

    预测下期价格相对 ``x̃ = SMA(w)/p_t = (1/w)·Σ_i p_{t-i}/p_t``（**past/current**）：持续上涨
    标的过去均价 < 当前价 → x̃<1 → **减仓涨方**，是标准 On-Line Moving Average **Reversion**
    （均值回归），而非加仓涨方的动量。据回归幅度被动激进更新组合再投影到单纯形。

    Args:
        price_relative_window: 最近若干期价格相对矩阵，shape=(win, n_assets)，
            行=期、列=资产；末行为最近一期（用于估计 x̃）。
        prev_weights: 上期组合权重（长度 n_assets，和为 1）。
        epsilon: 均值回归阈值 ε（默认 10）。

    Returns:
        更新后的权重向量（非负、和为 1）。
    """
    pr = np.asarray(price_relative_window, dtype=float)
    if pr.ndim != 2 or pr.shape[0] == 0:
        return _normalize_long(prev_weights)
    pr = np.where(np.isfinite(pr) & (pr > 0), pr, 1.0)   # 防 0/负/nan（cumprod 与倒数稳定）
    # OLMAR 均值回归（CA-A01 订正）：cumprod(pr[::-1]) = p_t/p_{t-i}（current/past），取倒数
    # 得 p_{t-i}/p_t（past/current），均值即 SMA(w)/p_t。持续上涨标的 x̃<1 → 减仓（回归），
    # 修正原实现（未取倒数=current/past）方向写反成动量的 bug。
    inv_ratios = 1.0 / np.cumprod(pr[::-1], axis=0)      # p_{t-i}/p_t（past/current）
    x_tilde = inv_ratios.mean(axis=0)
    x_tilde = np.where(np.isfinite(x_tilde) & (x_tilde > 0), x_tilde, 1.0)

    x_bar = x_tilde.mean()
    diff = x_tilde - x_bar
    denom = float(diff @ diff)
    prev = _normalize_long(prev_weights)
    if denom <= 1e-16:
        return prev
    lam = max(0.0, (epsilon - float(prev @ x_tilde)) / denom)
    w_new = prev + lam * diff
    return simplex_projection(w_new)


# ---------------------------------------------------------------------------
# 序贯组合回测（信号 T 定权重、T+1 实现收益——未来函数红线）
# ---------------------------------------------------------------------------

def portfolio_backtest(
    weights_panel: pd.DataFrame,
    asset_returns: pd.DataFrame,
    cost_bps: float = 0.0,
) -> pd.DataFrame:
    """按再平衡权重面板序贯回测（OLPS 式3-4），返回净值/期收益/换手/成本/资产贡献。

    **未来函数红线**：``weights_panel`` 第 t 行（index=调仓月末 T，T 日收盘确定的目标
    权重）只与 ``asset_returns`` 中**严格晚于 T 的下一月**收益相乘，即「信号 T 算、
    T+1 执行」（spec B5 / AS4）。换手在 T 时点计（对比上期权重经 T 月收益漂移后的权重），
    成本从 T+1 期收益扣除。

    Args:
        weights_panel: index=调仓日（月末 T，升序），columns=asset，目标权重
            （每行不必和为 1；空仓行=全 0）。各期资产不同已 reindex 到并集、缺失 0。
        asset_returns: index=月末，columns=asset（含 weights_panel 全部列），月收益。
        cost_bps: 每单位换手（Σ|Δw| 双边）的成本，单位 bps（AS5 无摩擦=0）。

    Returns:
        DataFrame（index=收益实现月 T_next）列：
        ``port_return``（净期收益，已扣成本）/ ``gross_return`` / ``turnover`` /
        ``cost`` / ``nav``（净值，起点 1.0）/ ``contrib_<asset>``（各资产收益贡献）。
    """
    assets = list(weights_panel.columns)
    ret = asset_returns.reindex(columns=assets)
    rebalance_dates = list(weights_panel.index)
    ret_index = asset_returns.index

    records: list[dict] = []
    prev_w: Optional[pd.Series] = None
    nav = 1.0
    cost_rate = cost_bps / 1e4

    for t in rebalance_dates:
        w_t = weights_panel.loc[t].fillna(0.0)
        # T+1：严格晚于 T 的下一个月末收益（未来函数红线）
        future = ret_index[ret_index > t]
        if len(future) == 0:
            break
        t_next = future[0]
        r_next = ret.loc[t_next].reindex(assets)

        # 换手：对比上期权重经 T 月收益漂移后的权重
        if prev_w is None:
            turnover = float(w_t.abs().sum())     # 建仓
        else:
            r_t = ret.loc[t].reindex(assets).fillna(0.0) if t in ret_index else pd.Series(0.0, index=assets)
            drift = prev_w * (1.0 + r_t)
            drift = drift / drift.sum() if drift.sum() > 0 else prev_w
            turnover = float((w_t - drift).abs().sum())

        # T+1 期收益：只对权重非零且收益非缺失的资产计
        contrib = (w_t * r_next).where(r_next.notna(), 0.0)
        gross = float(contrib.sum())
        cost = turnover * cost_rate
        net = gross - cost
        nav *= (1.0 + net)

        rec = {"date": t_next, "gross_return": gross, "cost": cost,
               "port_return": net, "turnover": turnover, "nav": nav}
        for a in assets:
            rec[f"contrib_{a}"] = float(contrib.get(a, 0.0))
        records.append(rec)
        prev_w = w_t

    if not records:
        cols = ["gross_return", "cost", "port_return", "turnover", "nav"]
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame(records).set_index("date")
    out.index.name = "date"
    return out


# ---------------------------------------------------------------------------
# 便捷：滚动协方差 / 期望收益估计（≤T 历史，防未来函数）
# ---------------------------------------------------------------------------

def rolling_cov_estimate(
    returns_history: pd.DataFrame,
    min_obs: int = 12,
) -> pd.DataFrame:
    """用给定历史收益（调用方保证 ≤T）估样本协方差；不足 min_obs 用对角方差兜底。

    Args:
        returns_history: 截至 T（含）的资产月收益（index=月末，columns=asset）。
        min_obs: 估计所需最少观测；不足则退化为对角（各资产独立方差）。

    Returns:
        协方差矩阵（index/columns=asset，剔除全缺资产）。
    """
    hist = returns_history.dropna(axis=1, how="all")
    valid = hist.columns[hist.notna().sum() >= 2]
    hist = hist[valid]
    if hist.shape[1] == 0:
        return pd.DataFrame(dtype=float)
    if hist.shape[0] < min_obs:
        var = hist.var(ddof=1).fillna(hist.var(ddof=1).median() if hist.shape[1] else 0.0)
        return pd.DataFrame(np.diag(var.to_numpy()), index=valid, columns=valid)
    return hist.cov()


def _smoke() -> None:
    """引擎冒烟：合成资产，跑 EW/MV/HRP/HERC/NCO/RP + 回测（不做结论判定）。"""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2019-01-31", periods=36, freq="ME")
    assets = [f"A{i}" for i in range(6)]
    rets = pd.DataFrame(rng.normal(0.01, 0.05, size=(36, 6)), index=dates, columns=assets)
    cov = rets.cov()
    mu = rets.mean()
    print("EW  :", equal_weights(assets).round(3).to_dict())
    print("MV  :", mean_variance_weights(mu, cov).round(3).to_dict())
    print("RP  :", risk_parity_weights(cov).round(3).to_dict())
    print("HRP :", hrp_weights(cov).round(3).to_dict())
    print("HERC:", herc_weights(cov).round(3).to_dict())
    print("NCO :", nco_weights(cov).round(3).to_dict())
    wp = pd.DataFrame(
        [equal_weights(assets)] * 12,
        index=dates[:12],
    )
    bt = portfolio_backtest(wp, rets, cost_bps=0.0)
    print("回测 nav 末值:", round(float(bt["nav"].iloc[-1]), 4), "期数:", len(bt))


if __name__ == "__main__":
    _smoke()
