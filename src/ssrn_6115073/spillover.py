"""m5: Diebold-Yilmaz 溢出加权与每簇选股 · ssrn_6115073（市场迁移复现）

汇合点（deps m3 簇标签 + m4 ±1 信号）：把 m4 逐月产的 (资产×宏观因子) ±1 信号，按各宏观
因子对市场的 Diebold-Yilmaz 净波动溢出强度加权聚合为 FS_j，再在 m3 的每个簇内选 FS 最高
资产（纯长仓、FS≤0 剔除），产出每市场逐测试月的最终资产集，供 m6 组合构建（EW/MV）。

对齐要素（spec 三、F 类为权威）：
  - F9（式28-35，Diebold-Yilmaz 溢出）：对 [宏观因子变化 + 市场指数] 建 VAR(p)（式28），
    Wold 移动平均表示（式29），Pesaran-Shin 广义方差分解 GFEVD θ̃^g_{ij}(U)（式30-31），
    总/方向/净溢出（式32-35）；净溢出 S^g_i(U)=S^g_{.i}(U)−S^g_{i.}(U)（式35）。
    statsmodels 不可用 → 自实现 VAR（含截距多元 OLS）+ 广义 FEVD（AS52 退化，同 AS38/AS45/AS49）。
  - F10（式36-37 + 每簇选一）：min-max 归一化 γ̃_i=(γ_i−min γ)/(max γ−min γ)（式36）；
    FS_j=Σ_i γ̃_i·signal_{i,j}（式37，跨 7 宏观因子加权）；每簇选 FS 最高资产入组合（AS17
    纯长仓、FS≤0 剔除；AS51 信号 NaN 按缺失从求和剔除，不当 −1）。
  - R4（表6）：各宏观因子对指数的溢出强度（迁移验证——CPI/利率是否为 A股最强溢出因子；
    实验模式只记事实，数值对齐豁免）。

溢出的两个测度（解决 spec「净溢出（式35）」与表6「from CPI to index 强度」的口径并存，AS54）：
  - to_index（表6/R4 主强度）：θ̃[index←factor]×100，指数 U 步预测误差方差中归因于该因子冲击
    的份额（非负、[0,100]%，直读「from factor to index」，表6 语义与全正值一致）；
  - net_pairwise（FS 权重基）：(θ̃[index←factor]−θ̃[factor←index])×100，因子↔指数的成对净溢出
    （honors F10「净溢出」；min-max 归一化为 γ̃ 作 FS 权重）；
  - system_net（式35 逐变量系统净，审计留档）：(Σ_{k≠i}θ̃[k,i]−Σ_{k≠i}θ̃[i,k])/n×100。

估计窗口口径（未来函数红线，AS54）：**训练期一次性估**（DELTA 与 m2 AS42 / m4 AS50 train-once
同构）——VAR/GFEVD 只用 [train_start, train_end] 历史月度数据估 γ̃，测试期 2019-2024 完全不进入
估计（γ̃ 估计 ⊆ ≤train_end，对所有测试 T 均满足「≤T」且更强，零测试泄漏）。逐测试月 FS 用当月
m4 信号（已 T 定时）× 固定训练期 γ̃。AS12 的「滚动窗口」为可选口径（FIG14 时序），因月频历史
有限、且与全链 train-once 一致性优先，本模块取 train-once，滚动留 m7 敏感性（AS54 登记）。

溢出输入序列（AS53）：宏观用 change_panel（AS1 月度变化 X，平稳，与 Δβ 同源）、指数用月度收益
（平稳）——即**月频收益/变化的广义（DY）溢出**，是原文「波动率溢出」在月频下的迁移（严格实现
需月内日频算已实现波动，m1 冻结接口只暴露月频，故用收益/变化代理，登记退化）。

数据对接（m1 prepare_all + m2 selection + m3 clustering + m4 signals，接口现状为准，不改上游）：
  prep.macro.change_panel / .selected_factors ；prep.markets[m].index_returns ；prep.month_ends/区间；
  selection[m].regime_tier（excluded 跳过）；clustering[m].cluster_labels（每簇选一分组基）/.nc ；
  signals[m].signals[t]（[资产×因子]±1 矩阵）/.factors/.candidates/.test_months。

只许冒烟运行：uv run python -m src.ssrn_6115073.spillover
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Optional

import numpy as np
import pandas as pd

from .config import MARKET_NAMES_CN

# ---------------------------------------------------------------------------
# statsmodels 依赖 gate（AS52）：可用则可切换官方 VAR/FEVD；本环境不可用 → 自实现。
# 与 m1 F12 BorutaShap（AS38）、m3 sklearn（AS45）、m4 stumpy（AS49）feature-gate 风格一致。
# ---------------------------------------------------------------------------
try:  # pragma: no cover - 环境相关
    import statsmodels.api as _sm  # noqa: F401
    from statsmodels.tsa.api import VAR as _SM_VAR  # noqa: F401

    _HAS_STATSMODELS = True
except Exception:  # noqa: BLE001
    _sm = None
    _SM_VAR = None
    _HAS_STATSMODELS = False


# ---------------------------------------------------------------------------
# m5 参数（集中常量，杜绝魔法数字，均可反查 spec/assumptions；严守文件所有权，
# 不写入 m1 建的 config.py，参数集中于本模块顶部，与 m2/m3/m4 同构）
# ---------------------------------------------------------------------------

# F9 / AS12：VAR 阶数 p 上限（AIC 选）；预测步长 U=10（GFEVD 截断视界）
VAR_MAX_LAG: Final[int] = 4
FEVD_HORIZON: Final[int] = 10

# AS54：溢出估计窗口口径——'train' = 训练期一次性估、测试固定 γ̃（train-once，最防泄漏）
SPILLOVER_WINDOW: Final[str] = "train"

# VAR 估计最少完整月数（防 8 变量 VAR 过参数化；不足则退化等权 γ̃，登记 AS52 fallback）
MIN_VAR_OBS: Final[int] = 60

# 溢出指数百分数标度（DY 惯例 ×100）
SPILLOVER_SCALE: Final[float] = 100.0

# min-max 退化判定（式36 分母 max−min < 此值 → 视为各因子溢出等强 → γ̃ 一律 1（等权 fallback））
MINMAX_EPS: Final[float] = 1e-12

# Σ 数值正则（残差协方差近奇异时的对角 ridge，保 slogdet 有效）
SIGMA_RIDGE: Final[float] = 1e-10

# AS17：纯长仓——每簇选 FS 最高资产，仅当其 FS > 此下限方选入（FS≤0 剔除）
FS_LONG_ONLY_FLOOR: Final[float] = 0.0


# ---------------------------------------------------------------------------
# 返回结构（供 m6 组合构建 EW/MV 直接对接）
# ---------------------------------------------------------------------------

@dataclass
class SpilloverResult:
    """单市场 Diebold-Yilmaz 溢出加权 + 每簇选股产出（供 m6 EW/MV 序贯回测复用）。

    溢出表（train-once，per 因子）——net_spillover/to_index_share/system_net/gamma_weight；
    逐测试月选股——fs_panel[t]（每资产 FS）/ selected[t]（每簇 argmax FS>0 的最终资产集）/
    selection_detail[t]（[asset,cluster,FS,selected] 明细）。excluded/退化市场返回空选股、
    等权 γ̃ 兜底并置 status。
    """
    market: str                              # 内部市场名（hs300/sz50/zz500）
    index_code: str                          # 指数代码
    regime_tier: str                         # 透传 m2 tier（excluded_narrow_pool 跳过选股）
    status: str                              # 'ok' | 'degraded_var' | 'excluded' | 'no_clusters'
    var_impl: str                            # 'self_var'（AS52 退化）| 'statsmodels'
    var_lag: int                             # AIC 选定的 VAR 阶数 p
    horizon: int                             # GFEVD 预测步长 U
    n_var_obs: int                           # VAR 训练完整月数
    factors: list[str]                       # 参与的宏观因子（VAR 变量顺序，末位为指数）
    # --- 溢出表（train-once；供 R4/表6 与 FS 权重）---
    to_index: dict[str, float]               # 表6 主强度：θ̃[index←i]×100（非负份额）
    net_spillover: dict[str, float]          # γ_i：成对净溢出 (θ̃[idx←i]−θ̃[i←idx])×100（FS 权重基）
    system_net: dict[str, float]             # 式35 逐变量系统净溢出（含指数，审计留档）
    gamma_weight: dict[str, float]           # γ̃_i：min-max(net_spillover)∈[0,1]（式36，FS 权重）
    total_spillover: float                   # DY 总连通度指数（(n−trace)/n×100）
    fevd: pd.DataFrame                       # 归一化 θ̃（变量×变量，train-once；审计/FIG14）
    # --- 每簇选一（m3 簇标签 × 逐测试月 FS）---
    nc: int                                  # canonical 簇数（透传 m3）
    cluster_labels: dict[str, int]           # {股票→簇id}（透传 m3，每簇选一分组基）
    test_months: list[pd.Timestamp]          # 测试月末序列
    fs_panel: dict[pd.Timestamp, pd.Series]  # t → 每资产 FS_j（NaN=该月无任何非 NaN 信号）
    selected: dict[pd.Timestamp, list[str]]  # t → 每簇 argmax(FS>0) 最终资产集（≈nc 只或更少）
    selection_detail: dict[pd.Timestamp, pd.DataFrame]  # t → [asset,cluster,FS,selected]
    notes: str = ""


# ---------------------------------------------------------------------------
# F9 核心原语：自实现 VAR（含截距多元 OLS）+ AIC 定阶（statsmodels 不可用，AS52）
# ---------------------------------------------------------------------------

def _var_ols(data: np.ndarray, p: int) -> tuple[list[np.ndarray], np.ndarray, np.ndarray, int]:
    """VAR(p) 含截距多元 OLS（式28）：x_t = c + Σ_{l=1}^p Φ_l x_{t−l} + ε_t。

    Args:
        data: (T, n) 平稳多元序列（行=时间、列=变量；NaN-free，调用方 dropna）。
        p:    VAR 阶数。

    Returns:
        Phi:       list[(n,n)]，Φ_1..Φ_p（Φ_l[eq,k]=变量 k 滞后 l 对方程 eq 的系数）。
        intercept: (n,) 截距。
        sigma:     (n,n) 残差协方差 Σ（ML 口径 resid'resid/T_eff，供 GFEVD/AIC）。
        t_eff:     有效样本 T−p。
    """
    T, n = data.shape
    Yt = data[p:]                                    # (T−p, n)
    cols = [np.ones((T - p, 1))]
    for lag in range(1, p + 1):
        cols.append(data[p - lag: T - lag])          # 滞后 lag 块
    Xt = np.hstack(cols)                             # (T−p, 1 + n·p)
    B, *_ = np.linalg.lstsq(Xt, Yt, rcond=None)      # (1 + n·p, n)
    resid = Yt - Xt @ B
    t_eff = T - p
    sigma = (resid.T @ resid) / t_eff
    sigma = sigma + SIGMA_RIDGE * np.eye(n)          # 数值正则（近奇异保护）
    intercept = B[0]
    phi = [B[1 + (lag - 1) * n: 1 + lag * n].T.copy() for lag in range(1, p + 1)]
    return phi, intercept, sigma, t_eff


def select_var_lag(data: np.ndarray, max_lag: int = VAR_MAX_LAG) -> int:
    """AIC 定 VAR 阶数 p（AS12，上限 max_lag）；公共样本比较（同起点 data[max_lag:]）。

    AIC(p)=ln|Σ_p| + 2·n·(n·p+1)/T_eff（含截距参数）。自由度不足的 p 跳过；均不可行则 p=1。
    """
    T, n = data.shape
    usable = T - max_lag
    best_p, best_aic = 1, float("inf")
    for p in range(1, max_lag + 1):
        if usable < n * p + 1 + 5:                   # 自由度不足（留 5 冗余）→ 跳过
            continue
        Yt = data[max_lag:]
        cols = [np.ones((usable, 1))]
        for lag in range(1, p + 1):
            cols.append(data[max_lag - lag: T - lag])
        Xt = np.hstack(cols)
        B, *_ = np.linalg.lstsq(Xt, Yt, rcond=None)
        resid = Yt - Xt @ B
        sigma = (resid.T @ resid) / usable + SIGMA_RIDGE * np.eye(n)
        sign, logdet = np.linalg.slogdet(sigma)
        if sign <= 0:
            continue
        aic = logdet + 2.0 * n * (n * p + 1) / usable
        if aic < best_aic:
            best_aic, best_p = aic, p
    return best_p


def ma_coefficients(phi: list[np.ndarray], horizon: int = FEVD_HORIZON) -> list[np.ndarray]:
    """Wold 移动平均系数 A_h（式29）：A_0=I，A_h=Σ_{l=1}^{min(h,p)} Φ_l·A_{h−l}。

    返回 A_0..A_{horizon−1} 共 horizon 个（GFEVD 视界 U=horizon）。
    """
    n = phi[0].shape[0]
    p = len(phi)
    A = [np.eye(n)]
    for h in range(1, horizon):
        Ah = np.zeros((n, n))
        for lag in range(1, min(h, p) + 1):
            Ah += phi[lag - 1] @ A[h - lag]
        A.append(Ah)
    return A


def generalized_fevd(A: list[np.ndarray], sigma: np.ndarray) -> np.ndarray:
    """Pesaran-Shin 广义方差分解 GFEVD（式30-31），行归一化到和为 1。

    θ^g_{ij}(U)=[σ_jj^{-1} Σ_h (e_i'A_hΣe_j)²] / [Σ_h e_i'A_hΣA_h'e_i]；因广义（未正交化）行和≠1，
    再按行归一化 θ̃_{ij}=θ_{ij}/Σ_k θ_{ik}（Σ_j θ̃_{ij}=1）。θ̃_{ij}=变量 i 的 U 步预测误差方差中
    归因于变量 j 冲击的份额。

    Args:
        A:     Wold 系数 A_0..A_{U−1}。
        sigma: 残差协方差 Σ（含对角）。

    Returns:
        (n,n) 归一化广义 FEVD θ̃（行=被分解变量 i、列=冲击来源 j；行和=1）。
    """
    n = sigma.shape[0]
    sig_diag = np.diag(sigma)
    num = np.zeros((n, n))
    denom = np.zeros(n)
    for Ah in A:
        AhS = Ah @ sigma
        num += AhS ** 2                              # 累加 (A_hΣ)_{ij}²
        denom += np.einsum("ik,ik->i", AhS, Ah)      # (A_hΣA_h')_{ii}
    theta = (num / sig_diag[None, :]) / denom[:, None]
    row_sums = theta.sum(axis=1, keepdims=True)
    return theta / row_sums


# ---------------------------------------------------------------------------
# 单市场溢出表（train-once）：VAR → GFEVD → 净/方向/系统溢出 + γ̃ 权重（式35-36）
# ---------------------------------------------------------------------------

def _minmax_weights(values: np.ndarray) -> np.ndarray:
    """式36：γ̃_i=(γ_i−min γ)/(max γ−min γ)∈[0,1]；退化（max≈min）→ 一律 1（等权 fallback）。"""
    lo, hi = float(np.min(values)), float(np.max(values))
    if (hi - lo) < MINMAX_EPS:
        return np.ones_like(values, dtype=float)
    return (values - lo) / (hi - lo)


@dataclass
class _SpilloverTable:
    """单市场溢出表中间产物（train-once）。"""
    var_lag: int
    n_obs: int
    factors: list[str]
    to_index: dict[str, float]
    net_pairwise: dict[str, float]
    system_net: dict[str, float]      # 含指数键（式35 逐变量）
    gamma_weight: dict[str, float]
    total_spillover: float
    fevd: pd.DataFrame
    ok: bool


def compute_spillover_table(
    change_panel: pd.DataFrame,
    index_returns: pd.Series,
    factors: list[str],
    month_ends: pd.DatetimeIndex,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    *,
    max_lag: int = VAR_MAX_LAG,
    horizon: int = FEVD_HORIZON,
) -> _SpilloverTable:
    """单市场 train-once 溢出表：VAR(p)→GFEVD→to_index/net_pairwise/system_net/γ̃（F9/式35-36）。

    未来函数：仅用 [train_start, train_end] 的宏观变化 X（change_panel）+ 指数月收益，listwise
    dropna 成完整样本估 VAR，测试期完全不进入（AS54 train-once）。变量顺序 = factors + [指数]。
    """
    idx = pd.DatetimeIndex(month_ends)
    train_sel = (idx >= train_start) & (idx <= train_end)
    X = change_panel.reindex(idx).loc[train_sel, factors]
    y = index_returns.reindex(idx).loc[train_sel].rename("__index__")
    mat = pd.concat([X, y], axis=1).dropna()
    var_names = list(mat.columns)                    # factors + ['__index__']
    n = len(var_names)
    idx_pos = n - 1

    empty = {f: float("nan") for f in factors}
    if mat.shape[0] < MIN_VAR_OBS:                   # 样本不足 → 退化等权 γ̃（AS52 fallback）
        return _SpilloverTable(
            var_lag=0, n_obs=int(mat.shape[0]), factors=factors,
            to_index=dict(empty), net_pairwise=dict(empty),
            system_net={v: float("nan") for v in var_names},
            gamma_weight={f: 1.0 for f in factors},  # 等权兜底（信号等权聚合）
            total_spillover=float("nan"),
            fevd=pd.DataFrame(index=var_names, columns=var_names, dtype=float),
            ok=False,
        )

    data = mat.to_numpy(dtype=float)
    p = select_var_lag(data, max_lag)
    phi, _, sigma, _ = _var_ols(data, p)
    A = ma_coefficients(phi, horizon)
    theta = generalized_fevd(A, sigma)               # 归一化 θ̃

    diag = np.diag(theta)
    to_index_vec = theta[idx_pos, :] * SPILLOVER_SCALE           # θ̃[index←j]×100
    from_index_vec = theta[:, idx_pos] * SPILLOVER_SCALE         # θ̃[j←index]×100
    net_pairwise_vec = to_index_vec - from_index_vec            # 成对净 j→index
    col_sum = theta.sum(axis=0) - diag                          # TO others from v（列和去对角）
    row_sum = theta.sum(axis=1) - diag                          # FROM others to v（行和去对角）
    system_net_vec = (col_sum - row_sum) / n * SPILLOVER_SCALE  # 式35 逐变量系统净
    total = float((n - np.trace(theta)) / n * SPILLOVER_SCALE)

    fac_pos = list(range(len(factors)))                         # 因子在变量序列的位置（前段）
    gamma_tilde = _minmax_weights(net_pairwise_vec[fac_pos])

    return _SpilloverTable(
        var_lag=int(p), n_obs=int(mat.shape[0]), factors=factors,
        to_index={f: float(to_index_vec[k]) for k, f in enumerate(factors)},
        net_pairwise={f: float(net_pairwise_vec[k]) for k, f in enumerate(factors)},
        system_net={var_names[v]: float(system_net_vec[v]) for v in range(n)},
        gamma_weight={f: float(gamma_tilde[k]) for k, f in enumerate(factors)},
        total_spillover=total,
        fevd=pd.DataFrame(theta, index=var_names, columns=var_names),
        ok=True,
    )


# ---------------------------------------------------------------------------
# F10：FS 溢出加权聚合（式37）+ 每簇选一（AS17 纯长仓 / AS51 NaN 剔除）
# ---------------------------------------------------------------------------

def aggregate_fs(signal_mat: pd.DataFrame, gamma_weight: pd.Series) -> pd.Series:
    """式37：FS_j=Σ_i γ̃_i·signal_{i,j}，信号 NaN 按缺失从求和剔除（AS51，不当 −1）。

    Args:
        signal_mat:   [资产 × 宏观因子] ∈{+1,−1,NaN}（m4 signals[t]）。
        gamma_weight: 各宏观因子 γ̃∈[0,1]（train-once）；按 signal_mat.columns 对齐。

    Returns:
        Series[资产 → FS_j]；某资产全部因子信号 NaN → FS=NaN（无信号，不可选）。
    """
    w = gamma_weight.reindex(signal_mat.columns).to_numpy(dtype=float)
    S = signal_mat.to_numpy(dtype=float)                        # (n_asset, n_factor)
    valid = ~np.isnan(S)
    contrib = np.where(valid, S * w[None, :], 0.0)              # NaN 信号贡献 0（剔除，AS51）
    fs = contrib.sum(axis=1)
    fs = np.where(valid.any(axis=1), fs, np.nan)               # 全 NaN → NaN（区分无信号 vs 净零）
    return pd.Series(fs, index=signal_mat.index, name="FS")


def select_per_cluster(
    fs: pd.Series,
    cluster_labels: dict[str, int],
    *,
    fs_floor: float = FS_LONG_ONLY_FLOOR,
) -> tuple[list[str], pd.DataFrame]:
    """每簇选 FS 最高资产（F10 / AS17）：簇内取 argmax FS，仅当 FS>fs_floor 方选入（纯长仓）。

    Args:
        fs:             aggregate_fs 产出（资产→FS_j，可含 NaN）。
        cluster_labels: {股票→簇id}（m3 canonical hierarchical+SU）。
        fs_floor:       FS 下限（AS17，>此值方选入；默认 0）。

    Returns:
        selected:  最终资产集（每簇一只或更少；≈nc 只，FS≤0 的簇不贡献）。
        detail:    DataFrame[asset, cluster, FS, selected]（该月全资产明细，供审计/m6）。
    """
    rows = []
    for asset, fs_val in fs.items():
        rows.append({
            "asset": asset,
            "cluster": cluster_labels.get(asset, -1),
            "FS": float(fs_val),
            "selected": False,
        })
    detail = pd.DataFrame(rows, columns=["asset", "cluster", "FS", "selected"])
    if detail.empty:
        return [], detail

    selected: list[str] = []
    valid = detail[detail["cluster"] >= 0].dropna(subset=["FS"])
    for cid, grp in valid.groupby("cluster"):
        pos = grp[grp["FS"] > fs_floor]
        if pos.empty:                                          # 该簇最优 FS≤0 → 不选（AS17）
            continue
        pick_idx = pos["FS"].idxmax()
        pick_asset = detail.at[pick_idx, "asset"]
        detail.at[pick_idx, "selected"] = True
        selected.append(pick_asset)
    return selected, detail


# ---------------------------------------------------------------------------
# 单市场端到端：溢出表（train-once）→ 逐测试月 FS + 每簇选一
# ---------------------------------------------------------------------------

def run_market_spillover(
    market: str,
    index_code: str,
    regime_tier: str,
    change_panel: pd.DataFrame,
    index_returns: pd.Series,
    factors: list[str],
    month_ends: pd.DatetimeIndex,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    cluster_labels: dict[str, int],
    nc: int,
    signals: dict[pd.Timestamp, pd.DataFrame],
    test_months: list[pd.Timestamp],
    *,
    max_lag: int = VAR_MAX_LAG,
    horizon: int = FEVD_HORIZON,
    fs_floor: float = FS_LONG_ONLY_FLOOR,
) -> SpilloverResult:
    """单市场：train-once 溢出表 + 逐测试月 FS 溢出加权聚合 + 每簇选一（F9/F10/式35-37）。"""
    var_impl = "statsmodels" if _HAS_STATSMODELS else "self_var"

    def _empty(status: str, note: str) -> SpilloverResult:
        return SpilloverResult(
            market=market, index_code=index_code, regime_tier=regime_tier, status=status,
            var_impl=var_impl, var_lag=0, horizon=horizon, n_var_obs=0, factors=list(factors),
            to_index={}, net_spillover={}, system_net={}, gamma_weight={},
            total_spillover=float("nan"),
            fevd=pd.DataFrame(dtype=float), nc=nc, cluster_labels=dict(cluster_labels),
            test_months=list(test_months), fs_panel={}, selected={}, selection_detail={},
            notes=note,
        )

    # 溢出表（train-once，即使 excluded 也算——供 R4/表6 展示；选股才受 tier/簇约束）
    table = compute_spillover_table(
        change_panel, index_returns, factors, month_ends, train_start, train_end,
        max_lag=max_lag, horizon=horizon,
    )

    # excluded 市场 / 无簇 → 不选股（下游 m6 据 regime_tier 决定纳入）
    if regime_tier == "excluded_narrow_pool":
        res = _empty("excluded", "excluded_narrow_pool 市场：不产选股（溢出表仍留档）")
    elif not cluster_labels or nc <= 0:
        res = _empty("no_clusters", "无簇标签（m3 退化/排除）：不产选股")
    else:
        gamma_series = pd.Series(table.gamma_weight, dtype=float)
        fs_panel: dict[pd.Timestamp, pd.Series] = {}
        selected: dict[pd.Timestamp, list[str]] = {}
        detail: dict[pd.Timestamp, pd.DataFrame] = {}
        for t in test_months:
            sig = signals.get(t)
            if sig is None or sig.empty:
                continue
            fs = aggregate_fs(sig, gamma_series)
            picks, det = select_per_cluster(fs, cluster_labels, fs_floor=fs_floor)
            fs_panel[t] = fs
            selected[t] = picks
            detail[t] = det
        status = "ok" if table.ok else "degraded_var"
        note = ("" if table.ok else
                f"VAR 完整样本 {table.n_obs} < {MIN_VAR_OBS} → γ̃ 退化等权（信号等权聚合，AS52 fallback）")
        res = SpilloverResult(
            market=market, index_code=index_code, regime_tier=regime_tier, status=status,
            var_impl=var_impl, var_lag=table.var_lag, horizon=horizon, n_var_obs=table.n_obs,
            factors=list(factors),
            to_index=table.to_index, net_spillover=table.net_pairwise,
            system_net=table.system_net, gamma_weight=table.gamma_weight,
            total_spillover=table.total_spillover, fevd=table.fevd,
            nc=nc, cluster_labels=dict(cluster_labels),
            test_months=list(test_months), fs_panel=fs_panel, selected=selected,
            selection_detail=detail, notes=note,
        )

    # excluded/no_clusters 也回填溢出表（供 R4 展示）
    if res.status in ("excluded", "no_clusters"):
        res.var_lag = table.var_lag
        res.n_var_obs = table.n_obs
        res.to_index = table.to_index
        res.net_spillover = table.net_pairwise
        res.system_net = table.system_net
        res.gamma_weight = table.gamma_weight
        res.total_spillover = table.total_spillover
        res.fevd = table.fevd
    return res


def run_spillover(
    prep,
    selection: Optional[dict] = None,
    clustering: Optional[dict] = None,
    signals: Optional[dict] = None,
    factors: Optional[list[str]] = None,
    *,
    max_lag: int = VAR_MAX_LAG,
    horizon: int = FEVD_HORIZON,
    fs_floor: float = FS_LONG_ONLY_FLOOR,
) -> dict[str, SpilloverResult]:
    """m5 主入口：三宽基各自 DY 溢出加权 + 每簇选一，返回 {市场名: SpilloverResult}。

    Args:
        prep:       m1 prepare_all() 产出（用 .macro.change_panel/.selected_factors、
                    .markets[m].index_returns、.month_ends/区间）。
        selection:  m2 run_selection(prep)（None 时内部调，取 .regime_tier）。
        clustering: m3 run_clustering(prep, selection)（None 时内部调，取 .cluster_labels/.nc）。
        signals:    m4 run_pattern_matching(prep, selection)（None 时内部调，取 .signals/.test_months）。
        factors:    参与溢出/FS 的宏观因子（默认 prep.macro.selected_factors，7 因子）。

    Returns:
        dict[市场名 → SpilloverResult]；下游 m6 按市场取 .selected[t]（每测试月最终资产集）+
        .cluster_labels 建 EW/MV，据 .regime_tier/.status 决定是否纳入；R4/表6 见 .to_index/.net_spillover。
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

    factors = list(factors) if factors is not None else list(prep.macro.selected_factors)
    change_panel = prep.macro.change_panel
    month_ends = prep.month_ends

    results: dict[str, SpilloverResult] = {}
    for name, md in prep.markets.items():
        sel = selection[name]
        clus = clustering[name]
        sig = signals[name]
        results[name] = run_market_spillover(
            market=name, index_code=md.code, regime_tier=sel.regime_tier,
            change_panel=change_panel, index_returns=md.index_returns, factors=factors,
            month_ends=month_ends, train_start=prep.train_start, train_end=prep.train_end,
            cluster_labels=clus.cluster_labels, nc=clus.nc,
            signals=sig.signals, test_months=sig.test_months,
            max_lag=max_lag, horizon=horizon, fs_floor=fs_floor,
        )
    return results


# ---------------------------------------------------------------------------
# 便捷：R4/表6 溢出表（供 verifier / m6 消费）
# ---------------------------------------------------------------------------

def spillover_table_frame(results: dict[str, SpilloverResult], factors: list[str]) -> pd.DataFrame:
    """R4/表6 长表：market/factor/to_index_share/net_spillover/gamma_weight（各市场逐因子）。"""
    rows = []
    for name, r in results.items():
        for f in factors:
            rows.append({
                "market": name,
                "factor": f,
                "to_index_share": r.to_index.get(f, float("nan")),
                "net_spillover": r.net_spillover.get(f, float("nan")),
                "gamma_weight": r.gamma_weight.get(f, float("nan")),
            })
    return pd.DataFrame(rows, columns=["market", "factor", "to_index_share",
                                       "net_spillover", "gamma_weight"])


# ---------------------------------------------------------------------------
# 冒烟运行（仅确认可执行 + 打印溢出表/FS 分布/每簇选出数 + 依赖状态；验证结论归 verifier）
# ---------------------------------------------------------------------------

def _selected_stats(res: SpilloverResult) -> tuple[float, int, int, int]:
    """逐测试月选出资产数统计：均值 / 最小 / 最大 / 有选股的月数。"""
    counts = [len(res.selected.get(t, [])) for t in res.test_months if t in res.selected]
    if not counts:
        return 0.0, 0, 0, 0
    return float(np.mean(counts)), int(min(counts)), int(max(counts)), len(counts)


def _fs_stats(res: SpilloverResult) -> tuple[int, int, int]:
    """FS 面板统计：>0 / ≤0 / NaN 的 (资产,月) 格数。"""
    pos = nonpos = nan = 0
    for t, fs in res.fs_panel.items():
        v = fs.to_numpy(dtype=float)
        nan += int(np.isnan(v).sum())
        pos += int(np.nansum(v > 0.0))
        nonpos += int(np.nansum(v <= 0.0))
    return pos, nonpos, nan


def _smoke(smoke_test_months: int = 6) -> None:
    """冒烟：溢出表 train-once 全跑；FS/选股仅前 smoke_test_months 个测试月控速。"""
    from src.ssrn_6115073.data_prep import prepare_all
    from src.ssrn_6115073.selection import run_selection
    from src.ssrn_6115073.clustering import run_clustering
    from src.ssrn_6115073.pattern_matching import run_market_pattern_matching

    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 24)
    print("=" * 92)
    print("m5 Diebold-Yilmaz 溢出加权与每簇选股冒烟 · ssrn_6115073（F9/F10/R4）")
    print("=" * 92)
    print(f"[依赖] statsmodels 可用={_HAS_STATSMODELS} → VAR/FEVD 实现="
          f"{'statsmodels' if _HAS_STATSMODELS else 'self_var(自实现 VAR 多元 OLS + 广义 FEVD, AS52 退化)'}")
    print(f"[参数] VAR 阶上限 p≤{VAR_MAX_LAG}(AIC 选/AS12) 预测步长 U={FEVD_HORIZON} "
          f"估计窗={SPILLOVER_WINDOW}(train-once/AS54) VAR 最少月={MIN_VAR_OBS}")
    print(f"[口径] 溢出输入=宏观 change_panel + 指数月收益（月频收益/变化广义溢出, AS53）| "
          f"FS 权重 γ̃=min-max(净溢出)（式36/AS54）| 每簇选 FS 最高、FS≤{FS_LONG_ONLY_FLOOR} 剔除（AS17）")

    prep = prepare_all()
    selection = run_selection(prep)
    clustering = run_clustering(prep, selection)
    factors = list(prep.macro.selected_factors)
    print(f"[宏观因子] ({len(factors)}) {factors}")
    print(f"[区间] 训练 {prep.train_start.date()}~{prep.train_end.date()} 估溢出；"
          f"测试 {prep.test_start.date()}~{prep.test_end.date()}（冒烟仅前 {smoke_test_months} 月产 FS/选股）")

    # 冒烟截断测试轴（只跑前 smoke_test_months 月的信号，避免全量 m4 耗时；溢出表 train-once 全跑）
    full_test = prep.month_ends[(prep.month_ends >= prep.test_start)
                                & (prep.month_ends <= prep.test_end)]
    smoke_end = full_test[min(smoke_test_months, len(full_test)) - 1]

    results: dict[str, SpilloverResult] = {}
    for name, md in prep.markets.items():
        sel = selection[name]
        clus = clustering[name]
        sig = run_market_pattern_matching(
            market=name, index_code=md.code, regime_tier=sel.regime_tier,
            stock_returns=md.stock_returns, level_panel=prep.macro.level_panel,
            candidates=list(sel.candidates), factors=factors,
            month_ends=prep.month_ends,
            train_start=prep.train_start, train_end=prep.train_end,
            test_start=prep.test_start, test_end=smoke_end,     # 冒烟截断
        )
        results[name] = run_market_spillover(
            market=name, index_code=md.code, regime_tier=sel.regime_tier,
            change_panel=prep.macro.change_panel, index_returns=md.index_returns, factors=factors,
            month_ends=prep.month_ends, train_start=prep.train_start, train_end=prep.train_end,
            cluster_labels=clus.cluster_labels, nc=clus.nc,
            signals=sig.signals, test_months=sig.test_months,
        )

    print("\n" + "-" * 92)
    print("① 三宽基 Diebold-Yilmaz 溢出表（train-once）+ R4 迁移检验（表6：CPI/利率是否最强）：")
    print("-" * 92)
    for name, r in results.items():
        cn = MARKET_NAMES_CN.get(name, name)
        print(f"\n[{cn} / {name} / {r.index_code}]  tier={r.regime_tier}  status={r.status}  "
              f"VAR p={r.var_lag}(样本 {r.n_var_obs} 月)  总连通度={r.total_spillover:.2f}")
        if r.notes:
            print(f"   注：{r.notes}")
        tab = pd.DataFrame({
            "to_index_share(表6强度)": pd.Series(r.to_index),
            "net_spillover(FS权重基)": pd.Series(r.net_spillover),
            "gamma_weight(γ̃∈[0,1])": pd.Series(r.gamma_weight),
        }).reindex(factors)
        print(tab.round(3).to_string())
        # R4 迁移检验：按表6 强度(to_index)排名，看 CPI/IR 是否居前
        strength = pd.Series(r.to_index).reindex(factors).dropna()
        if not strength.empty:
            rank = strength.sort_values(ascending=False)
            top2 = list(rank.index[:2])
            hit = [f for f in ("CPI", "IR") if f in top2]
            print(f"   → R4 迁移：表6 强度排名 {list(rank.index)}；最强前二={top2}；"
                  f"CPI/IR 命中前二={hit if hit else '否（迁移下非最强，实验模式如实记录）'}")
        net = pd.Series(r.net_spillover).reindex(factors).dropna()
        if not net.empty:
            net_rank = net.sort_values(ascending=False)
            print(f"   （净溢出口径排名 {list(net_rank.index)}；式35 系统净见 result.system_net）")

    print("\n" + "-" * 92)
    print(f"② FS 溢出加权聚合分布 + 每簇选出最终资产数（前 {smoke_test_months} 测试月）：")
    print("-" * 92)
    for name, r in results.items():
        cn = MARKET_NAMES_CN.get(name, name)
        if r.status not in ("ok", "degraded_var"):
            print(f"\n[{cn}/{name}] status={r.status} → 无选股（{r.notes}）")
            continue
        pos, nonpos, nan = _fs_stats(r)
        mean_sel, min_sel, max_sel, n_mon = _selected_stats(r)
        tot = pos + nonpos + nan
        print(f"\n[{cn}/{name}]  nc={r.nc}  候选资产={len(r.cluster_labels)}")
        print(f"   FS 分布（{n_mon} 月×资产 共 {tot} 格）：FS>0={pos} FS≤0={nonpos} NaN(无信号)={nan}")
        print(f"   每簇选出最终资产数：均值={mean_sel:.1f} 区间[{min_sel},{max_sel}]（≈nc={r.nc} 或更少，FS≤0 簇不贡献）")
        # 样例：首测试月选股明细
        t0 = r.test_months[0] if r.test_months else None
        if t0 is not None and t0 in r.selection_detail:
            det = r.selection_detail[t0].sort_values(["selected", "FS"], ascending=[False, False])
            print(f"   [样例] 首测试月 {t0.date()} 选出 {len(r.selected.get(t0, []))} 只（每簇 argmax FS>0）：")
            print("     选中=" + str(r.selected.get(t0, [])))
            print(det.head(8).round(3).to_string(index=False))

    print("\n" + "-" * 92)
    print("③ 未来函数自检（结构性约束，非数值结论）：")
    print("-" * 92)
    print(f"  1. 溢出 γ̃ train-once：仅用训练段 [{prep.train_start.date()}, {prep.train_end.date()}] 估 VAR，"
          f"测试期 {prep.test_start.date()}+ 完全不进入（AS54，⊆≤T 且更强）。")
    print("  2. 逐测试月 FS=Σγ̃·signal(t) 用当月 m4 信号（已 T 定时）× 固定训练期 γ̃，无测试期泄漏。")
    print("  3. 信号 NaN 按缺失从 FS 求和剔除（不当 −1，AS51）；FS≤0 资产不选入（纯长仓 AS17）。")

    # 下游 m6 接口示例
    frame = spillover_table_frame(results, factors)
    print("\n" + "-" * 92)
    print("[下游 m6 接口] run_spillover(prep, selection, clustering, signals) → dict[市场 → SpilloverResult]；")
    print("  每市场 .selected[t]=该测试月最终资产集（每簇选一）供 EW/MV 序贯建仓、.cluster_labels 分组、")
    print("  .gamma_weight/.net_spillover/.to_index 供 R4/表6；.selection_detail[t] 明细供审计。")
    print(f"  R4 长表 spillover_table_frame shape={frame.shape} 列={list(frame.columns)}")
    print("\n冒烟完成：溢出加权 + 每簇选一可端到端构造（可执行性确认；验证结论由 verifier 判定）。")


if __name__ == "__main__":
    _smoke()
