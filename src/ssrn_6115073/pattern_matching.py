"""m4: 两阶段 Matrix Profile 模式匹配与信号 · ssrn_6115073（市场迁移复现）

对齐要素（spec F5/F6/F7/F8，权威见 spec.md 三、F 类）：
  - F5（Remark 2 / 式15-17）：训练期用「相关性预测 + MSE」在 w∈{2..10}（月频步长，AS7）
    定 pattern-matching 最优窗口 w。对每只候选资产训练收益序列，用窗口 w 做「历史窗口
    相关加权预测」下一期收益，聚合平均 MSE 最小者为最优 w（每市场一个）。
  - F6（式20-23）：Z-归一化欧氏距离剖面 / 矩阵剖面 M=[min(D_i)] / 最近邻索引（motifs）。
    stumpy 可用则用其 Z-归一化 MP，本环境不可用 → 自实现（定义明确，AS45 退化登记）。
  - F7（式24-26）：两阶段匹配——
      阶段1（宏观）：对每个宏观因子，把「最近一年」窗口（m=12 月，AS10）与历史比较，取
        Z-归一化距离最小的历史经济周期结束月 MSP'=min[SP]（式24），得考察期 EP（式25）。
      阶段2（资产）：在匹配到的经济周期内，对每只资产用最优窗口 w 找与当前窗口最相似的
        历史价格窗口，预测 r̂ = 该最相似历史窗口「之后一期」的实际收益（式26）。
  - F8（式27）：signal = +1 if r̂>0 else −1；产 (资产 × 宏观因子) × 测试月的 ±1 信号矩阵。

窗口搜索定 w 与 nc 的分工（AS7 / 呼应 spec Algorithm 3「同时搜 w 与 nc」，SA3 印证 nc/w
独立）：本模块 F5 专注定窗口 w（阶段2 唯一消费的参数）；Algorithm 3 的「子簇数 nc」=资产
聚类簇数，由并行的 m3（Silhouette，AS2）权威确定，m4 不重复搜聚类 nc（避免与 m3 越界/冲突）。
search_optimal_window 附带报告各 w 的 MSE 表供诊断，不做资产聚类。

未来函数红线（code_audit / codex 逐点核查；本模块以「整数位置索引 + 严格早于 pos_t」硬约束）：
  1. 训练期定 w：只用 [train_start, train_end] 的历史月度收益（DELTA 与 m2 一致 AS6/AS42），
     测试期完全不进入窗口搜索。训练期内用相邻点算 MSE 属超参搜索、非策略信号，无泄漏。
  2. T 月末算信号、T+1 月执行（AS4）：本模块产 T 月末信号；执行错位由 m6 承接。
  3. 匹配的历史窗口「之后一期」严格早于当前信号月 t——
     阶段1 历史经济周期窗口结束 h ≤ pos_t − macro_m（与 query 完全不重叠的过去周期）；
     阶段2 历史价格窗口结束 g ≤ min(h, pos_t − 2)，其之后一期 g+1 ≤ pos_t − 1 < pos_t。
     query 窗口结束于 pos_t（用截至 t 已实现的收益 / 已披露的宏观 level，属 T 时点可知信息）。

数据对接（m1 prepare_all + m2 run_selection，接口以现状为准，不改上游）：
  prep.macro.level_panel（月末×因子 宏观水平值，阶段1 找相似经济周期）；
  prep.markets[m].stock_returns（月末×股票 收益，阶段2 价格窗口匹配 / F5 训练定 w）；
  prep.month_ends / .train_start / .train_end / .test_start / .test_end（统一时间轴与区间）；
  selection[m].candidates（m2 候选资产）/ .regime_tier（excluded_narrow_pool 市场跳过）。

只许冒烟运行：uv run python -m src.ssrn_6115073.pattern_matching
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Optional

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .config import (
    MACRO_STAGE_MONTHS,
    MARKET_NAMES_CN,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
)

# ---------------------------------------------------------------------------
# stumpy 依赖 gate（AS45）：可用则可切换 Z-归一化 MP 官方实现；本环境不可用 → 自实现。
# 与 m1 F12 BorutaShap 的 feature-gate 风格一致（依赖装上后无缝启用，不改调用方）。
# ---------------------------------------------------------------------------
try:  # pragma: no cover - 环境相关
    import stumpy as _stumpy  # noqa: F401

    _HAS_STUMPY = True
except Exception:  # noqa: BLE001
    _stumpy = None
    _HAS_STUMPY = False


# ---------------------------------------------------------------------------
# m4 参数（集中常量，杜绝魔法数字，均可反查 spec/assumptions；严守文件所有权，
# 不写入 m1 建的 config.py，参数集中于本模块顶部）
# ---------------------------------------------------------------------------

# F5 / AS7：pattern-matching 窗口候选网格 w∈{2..10}（月频步长）
WINDOW_MIN: Final[int] = 2
WINDOW_MAX: Final[int] = 10
WINDOW_GRID: Final[tuple[int, ...]] = tuple(range(WINDOW_MIN, WINDOW_MAX + 1))

# AS10：宏观 stage「最近一年」子序列长度（月频=12），从 config 复用（m1 已为 m4 预留）
MACRO_WINDOW_MONTHS: Final[int] = MACRO_STAGE_MONTHS

# 阶段2 经济周期搜索跨度（结束于 h* 的历史区间长度）；EP 由 12 月经济周期定义，
# 派生自 AS10「经济周期=最近一年」，故取同宏观窗口长度
EP_SPAN_MONTHS: Final[int] = MACRO_STAGE_MONTHS

# F5 单序列最少可预测点：训练期有效预测点不足此数则该序列不计入 w 的 MSE（防小样本噪声）
MIN_TRAIN_PRED_POINTS: Final[int] = 12

# Z-归一化标准差下限：窗口标准差低于此值判为常数窗口（无形状信息），距离置 inf 不匹配
ZNORM_STD_EPS: Final[float] = 1e-8


# ---------------------------------------------------------------------------
# 返回结构（供 m5 溢出加权聚合直接对接）
# ---------------------------------------------------------------------------

@dataclass
class WindowSearchResult:
    """F5 训练期窗口搜索产出（单市场）。"""
    market: str
    optimal_w: int                     # 最优窗口（阶段2 用）
    mse_by_w: dict[int, float]         # 各 w 的训练期平均 MSE（诊断；min 者即 optimal_w）
    n_series_used: int                 # 参与搜索的候选资产序列数（达最少预测点门槛）
    n_pred_points_total: int           # 最优 w 下的总有效预测点数


@dataclass
class SignalResult:
    """单市场两阶段 pattern-matching 信号产出（供 m5 FS 溢出加权聚合复用）。

    signals[t]：DataFrame，index=候选资产、columns=宏观因子，值 ∈ {+1.0, −1.0, NaN}
      （NaN=该月该 (资产,因子) 数据不足无法产信号）。m5 对每测试月 t 取 signals[t]，用溢出
      权重 γ̃[因子, 资产] 聚合 FS_j = Σ_i γ̃[i,j]·signal[j,i]（式37，i=因子、j=资产）。
    """
    market: str
    index_code: str
    regime_tier: str                        # 透传 m2 tier（Tier1/Tier2_degraded/excluded_narrow_pool）
    optimal_w: int                          # F5 定的最优窗口
    macro_window: int                       # 阶段1 宏观窗口（=12）
    ep_span: int                            # 阶段2 经济周期搜索跨度（=12）
    factors: list[str]                      # 参与的宏观因子（阶段1 逐因子）
    candidates: list[str]                   # 候选资产（阶段2 逐资产）
    test_months: list[pd.Timestamp]         # 测试月末序列
    signals: dict[pd.Timestamp, pd.DataFrame]   # 测试月 → [资产×因子] ±1 矩阵
    r_hat: dict[pd.Timestamp, pd.DataFrame]     # 测试月 → [资产×因子] 预测收益 r̂（诊断/可选）
    window_search: Optional[WindowSearchResult]  # 该市场 F5 窗口搜索详情
    matrix_profile_impl: str                # 'stumpy' | 'self_znorm'（AS45 退化标记）


# ---------------------------------------------------------------------------
# F6 核心原语：Z-归一化欧氏距离剖面 / 矩阵剖面（自实现，stumpy 不可用时；AS45）
# ---------------------------------------------------------------------------

def znorm_distance_profile(query: np.ndarray, windows: np.ndarray) -> np.ndarray:
    """query 与一组等长候选窗口的 Z-归一化欧氏距离剖面（F6 核心）。

    Z-归一化：每个长度 m 子序列减均值除（总体）标准差，消除水平与幅度，只比形状；
    Z-归一化欧氏距离 d = ‖ẑ_query − ẑ_win‖₂，与 Pearson 相关一一对应（d²=2m(1−ρ)）。
    常数窗口（std<eps，无形状信息）距离置 +inf，不参与匹配。

    Args:
        query:   长度 m 的 query 子序列（应已 NaN-free；含 NaN 时结果为 nan 由调用方过滤）。
        windows: (k, m) 候选窗口矩阵，每行一个与 query 等长的子序列。

    Returns:
        (k,) 距离数组；query 退化（std<eps）时全 +inf。
    """
    q = np.asarray(query, dtype=float)
    W = np.asarray(windows, dtype=float)
    if W.ndim != 2 or W.shape[1] != q.size:
        raise ValueError(f"windows 形状 {W.shape} 与 query 长度 {q.size} 不匹配")
    q_sd = q.std()
    if not np.isfinite(q_sd) or q_sd < ZNORM_STD_EPS:
        return np.full(W.shape[0], np.inf)
    qz = (q - q.mean()) / q_sd

    w_mu = W.mean(axis=1, keepdims=True)
    w_sd = W.std(axis=1, keepdims=True)
    safe_sd = np.where(w_sd < ZNORM_STD_EPS, np.nan, w_sd)
    wz = (W - w_mu) / safe_sd
    dist = np.sqrt(((wz - qz) ** 2).sum(axis=1))
    # 常数窗口 / 含 NaN 窗口 → inf（不匹配）
    dist = np.where(np.isfinite(dist), dist, np.inf)
    return dist


def causal_matrix_profile(series: np.ndarray, m: int) -> tuple[np.ndarray, np.ndarray]:
    """因果（left）矩阵剖面：M=[min(D_i)]，每个子序列只与「更早且不重叠」的子序列比（F6）。

    金融时序的因果版矩阵剖面（left MP）——子序列 i（结束于 i+m−1）的距离剖面只对结束位置
    ≤ (i−1) 且与之不重叠（结束 ≤ i+m−1−m）的历史子序列取，避免用未来子序列。返回 M 与最
    近邻索引（motif：M 全局最小处的一对最相似子序列）。本函数满足 spec F6 的 M=[min(D_i)] +
    最近邻索引定义，主要供诊断/审计核对；F7 两阶段实际用 znorm_distance_profile 精确控制历史区间。

    Args:
        series: 1-D 序列（NaN-free；含 NaN 段建议调用方先截取连续段）。
        m:      子序列长度。

    Returns:
        mp:       (n−m+1,) 因果矩阵剖面（无合法历史邻居处为 +inf）。
        nn_index: (n−m+1,) 最近邻子序列起始索引（无邻居处为 −1）。
    """
    x = np.asarray(series, dtype=float)
    n = x.size
    n_sub = n - m + 1
    if n_sub <= 1:
        return np.full(max(n_sub, 0), np.inf), np.full(max(n_sub, 0), -1, dtype=int)
    subs = sliding_window_view(x, m)  # (n_sub, m)，第 i 行起于 i、结束于 i+m−1
    mp = np.full(n_sub, np.inf)
    nn = np.full(n_sub, -1, dtype=int)
    for i in range(1, n_sub):
        # 历史邻居 = 起始 j 使窗口结束 j+m−1 < i（与 i 窗口不重叠且更早）→ j ≤ i−m
        hi = i - m
        if hi < 0:
            continue
        cand = subs[: hi + 1]                      # (hi+1, m)
        dist = znorm_distance_profile(subs[i], cand)
        k = int(np.argmin(dist))
        if np.isfinite(dist[k]):
            mp[i] = dist[k]
            nn[i] = k
    return mp, nn


# ---------------------------------------------------------------------------
# F5：相关性预测 + MSE 训练期窗口搜索（式15-17，Remark 2）
# ---------------------------------------------------------------------------

def _pearson_corr_to_windows(query: np.ndarray, windows: np.ndarray) -> np.ndarray:
    """query 与一组候选窗口的 Pearson 相关（F5 簇内用相关，式15 的相似度）。

    Args:
        query:   长度 m 的 query 窗口（NaN-free）。
        windows: (k, m) 候选窗口。

    Returns:
        (k,) 相关系数；常数窗口 → nan（由调用方过滤）。
    """
    q = np.asarray(query, dtype=float)
    W = np.asarray(windows, dtype=float)
    qc = q - q.mean()
    q_ss = float((qc ** 2).sum())
    Wc = W - W.mean(axis=1, keepdims=True)
    W_ss = (Wc ** 2).sum(axis=1)
    denom = np.sqrt(W_ss * q_ss)
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = (Wc @ qc) / denom
    return corr


def _window_prediction_sse(series: np.ndarray, w: int) -> tuple[float, int]:
    """单序列、单窗口长度 w 的训练期相关加权预测 SSE 与有效预测点数（式15-16）。

    对每个可预测点 t（窗口结束于 t，预测 series[t+1]）：取末窗 W_t=series[t−w+1:t+1]，与所有
    「结束早于 t 且之后一期存在」的历史窗口 W_ι 算 Pearson 相关，rescale (ρ+1)/2 到 [0,1] 归一
    化为权重（式15），预测 r̂_{t+1}=Σ_ι weight_ι·series[ι+1]（历史各窗之后一期收益的相关加权
    平均）；累加 (r̂−实际)²。含 NaN 的窗口/之后一期自动跳过。

    Args:
        series: 1-D 训练期收益（可含 NaN）。
        w:      窗口长度。

    Returns:
        (sse, n_points)；无有效点时 (0.0, 0)。
    """
    x = np.asarray(series, dtype=float)
    n = x.size
    if n < w + 2:
        return 0.0, 0
    subs = sliding_window_view(x, w)          # (n−w+1, w)，行 i 结束于 i+w−1
    end_pos = np.arange(w - 1, n)             # 窗口 i 的结束位置
    next_pos = end_pos + 1                    # 之后一期位置
    win_ok = np.isfinite(subs).all(axis=1)    # 窗口完整非 NaN
    has_next = next_pos < n
    next_val = np.full(subs.shape[0], np.nan)
    next_val[has_next] = x[next_pos[has_next]]
    next_ok = np.isfinite(next_val)
    hist_ok = win_ok & next_ok                # 可作历史邻居（窗口全 + 之后一期全）

    sse = 0.0
    n_pts = 0
    idx_all = np.arange(subs.shape[0])
    for i in idx_all:
        if not win_ok[i] or not has_next[i] or not next_ok[i]:
            continue  # 该预测点末窗或真实下一期缺失，无法评估
        hist_sel = hist_ok & (idx_all < i)    # 历史邻居：结束早于 t 且之后一期已实现
        if hist_sel.sum() < 1:
            continue
        H = subs[hist_sel]
        corr = _pearson_corr_to_windows(subs[i], H)
        weight = (corr + 1.0) / 2.0           # rescale [-1,1] → [0,1]（式15）
        weight = np.where(np.isfinite(weight), weight, 0.0)
        wsum = weight.sum()
        if wsum <= 0.0:
            continue
        pred = float((weight * next_val[hist_sel]).sum() / wsum)
        actual = float(next_val[i])
        sse += (pred - actual) ** 2
        n_pts += 1
    return sse, n_pts


def search_optimal_window(
    returns_train: pd.DataFrame,
    candidates: list[str],
    *,
    grid: tuple[int, ...] = WINDOW_GRID,
    min_points: int = MIN_TRAIN_PRED_POINTS,
) -> WindowSearchResult:
    """F5：训练期用相关性预测 + MSE 在 w∈grid 定最优窗口 w（式15-17，AS7）。

    未来函数：returns_train 应已是训练段切片（≤ train_end），测试期不进入。对每只候选资产序列、
    每个 w 累加相关加权预测 SSE 与点数，w 的平均 MSE = ΣSSE / Σpoints；取最小平均 MSE 者为 w。

    Args:
        returns_train: 训练段月收益（index=训练月末, columns=股票；仅含 [train_start, train_end]）。
        candidates:    候选资产代码（m2 选出）。
        grid:          窗口候选网格（默认 {2..10}）。
        min_points:    单序列计入 MSE 的最少有效预测点数门槛。

    Returns:
        WindowSearchResult（optimal_w / mse_by_w / n_series_used / n_pred_points_total）。
    """
    cols = [c for c in candidates if c in returns_train.columns]
    mse_by_w: dict[int, float] = {}
    points_by_w: dict[int, int] = {}
    series_by_w: dict[int, int] = {}
    for w in grid:
        total_sse = 0.0
        total_pts = 0
        n_series = 0
        for c in cols:
            arr = returns_train[c].to_numpy(dtype=float)
            sse, pts = _window_prediction_sse(arr, w)
            if pts >= min_points:
                total_sse += sse
                total_pts += pts
                n_series += 1
        mse_by_w[w] = (total_sse / total_pts) if total_pts > 0 else float("inf")
        points_by_w[w] = total_pts
        series_by_w[w] = n_series

    finite = {w: v for w, v in mse_by_w.items() if np.isfinite(v)}
    optimal_w = min(finite, key=finite.get) if finite else grid[0]
    return WindowSearchResult(
        market="",
        optimal_w=int(optimal_w),
        mse_by_w=mse_by_w,
        n_series_used=series_by_w.get(optimal_w, 0),
        n_pred_points_total=points_by_w.get(optimal_w, 0),
    )


# ---------------------------------------------------------------------------
# F7：两阶段匹配（阶段1 宏观相似经济周期 + 阶段2 资产价格窗口预测）
# ---------------------------------------------------------------------------

def stage1_macro_period(
    level_arr: np.ndarray,
    pos_t: int,
    macro_m: int = MACRO_WINDOW_MONTHS,
) -> Optional[int]:
    """阶段1（式24-25）：宏观因子「最近一年」窗口在历史找最相似经济周期结束月 h*=MSP'。

    query = level_arr[pos_t−macro_m+1 : pos_t+1]（截至 t 的最近 macro_m 月宏观水平，已披露）；
    历史候选窗口结束 h ∈ [macro_m−1, pos_t−macro_m]（与 query 完全不重叠的过去经济周期，
    杜绝未来函数且符合「most similar year in the past」）；取 Z-归一化距离最小者 h*（式24）。

    Args:
        level_arr: 单宏观因子的月末水平序列（1-D，NaN 表示该月未对齐/无值）。
        pos_t:     当前信号月在时间轴上的整数位置。
        macro_m:   宏观窗口（最近一年=12，AS10）。

    Returns:
        h*（相似经济周期结束月的整数位置）；query 缺失或无合法历史窗口时 None。
    """
    lo_q = pos_t - macro_m + 1
    if lo_q < 0:
        return None
    query = level_arr[lo_q: pos_t + 1]
    if query.size != macro_m or not np.isfinite(query).all():
        return None

    h_lo = macro_m - 1
    h_hi = pos_t - macro_m          # 历史窗口结束 ≤ pos_t−macro_m → 与 query 不重叠、严格更早
    if h_hi < h_lo:
        return None
    h_positions = np.arange(h_lo, h_hi + 1)
    # 候选窗口矩阵（结束于 h → 起于 h−macro_m+1）
    starts = h_positions - macro_m + 1
    windows = np.stack([level_arr[s: s + macro_m] for s in starts])
    finite_rows = np.isfinite(windows).all(axis=1)
    if not finite_rows.any():
        return None
    dist = np.full(windows.shape[0], np.inf)
    dist[finite_rows] = znorm_distance_profile(query, windows[finite_rows])
    if not np.isfinite(dist).any():
        return None
    return int(h_positions[int(np.argmin(dist))])


def stage2_asset_forecast(
    ret_arr: np.ndarray,
    pos_t: int,
    w: int,
    ep_end_pos: int,
    *,
    ep_span: int = EP_SPAN_MONTHS,
) -> float:
    """阶段2（式26）：在匹配经济周期内，资产当前 w 窗口找最相似历史价格窗口，预测 r̂。

    query = ret_arr[pos_t−w+1 : pos_t+1]（截至 t 的最近 w 月收益，已实现）；EP 经济周期区间
    = 结束于 ep_end_pos 的 ep_span 月；候选历史价格窗口结束 g ∈ [EP起+w−1, min(ep_end, pos_t−2)]
    （g+1 ≤ pos_t−1 < pos_t，历史窗口之后一期严格早于当前信号月，杜绝未来函数）；取 Z-归一化距
    离最小窗口 g*，r̂ = ret_arr[g*+1]（该最相似历史窗口之后一期的实际收益，式26）。

    Args:
        ret_arr:    单资产月收益序列（1-D，NaN 表示该月无收益）。
        pos_t:      当前信号月整数位置。
        w:          最优窗口（F5）。
        ep_end_pos: 阶段1 匹配到的经济周期结束月位置 h*。
        ep_span:    经济周期搜索跨度（=12）。

    Returns:
        r̂（预测下一期收益）；query 缺失 / 无合法历史窗口时 nan。
    """
    lo_q = pos_t - w + 1
    if lo_q < 0:
        return float("nan")
    query = ret_arr[lo_q: pos_t + 1]
    if query.size != w or not np.isfinite(query).all():
        return float("nan")

    ep_start = ep_end_pos - ep_span + 1
    g_lo = max(ep_start + w - 1, w - 1)        # 窗口需完整且落在 EP 区间内
    g_hi = min(ep_end_pos, pos_t - 2)          # 未来函数红线：之后一期 g+1 ≤ pos_t−1 < pos_t
    if g_hi < g_lo:
        return float("nan")

    g_positions = np.arange(g_lo, g_hi + 1)
    windows = []
    next_vals = []
    for g in g_positions:
        win = ret_arr[g - w + 1: g + 1]
        nxt = ret_arr[g + 1]
        if win.size == w and np.isfinite(win).all() and np.isfinite(nxt):
            windows.append(win)
            next_vals.append(float(nxt))
    if not windows:
        return float("nan")

    dist = znorm_distance_profile(query, np.stack(windows))
    k = int(np.argmin(dist))
    if not np.isfinite(dist[k]):
        return float("nan")
    return next_vals[k]


def signal_from_rhat(r_hat: float) -> float:
    """F8（式27）：r̂>0 → +1；r̂≤0 → −1；r̂ 为 nan（无预测）→ nan（不强制 −1）。"""
    if not np.isfinite(r_hat):
        return float("nan")
    return 1.0 if r_hat > 0.0 else -1.0


# ---------------------------------------------------------------------------
# 单市场端到端：F5 定 w → 逐测试月两阶段匹配 → ±1 信号矩阵
# ---------------------------------------------------------------------------

def run_market_pattern_matching(
    market: str,
    index_code: str,
    regime_tier: str,
    stock_returns: pd.DataFrame,
    level_panel: pd.DataFrame,
    candidates: list[str],
    factors: list[str],
    month_ends: pd.DatetimeIndex,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    *,
    grid: tuple[int, ...] = WINDOW_GRID,
    macro_m: int = MACRO_WINDOW_MONTHS,
    ep_span: int = EP_SPAN_MONTHS,
) -> SignalResult:
    """单市场两阶段 pattern-matching：F5 训练定 w → 测试期逐月产 (资产×因子) ±1 信号。

    时间轴统一到 month_ends（stock_returns/level_panel 均 reindex 到该轴使整数位置一致，
    缺失为 NaN 由各阶段非 NaN 检查处理），阶段1 结果 h*_{因子,月} 缓存复用给该月所有资产。
    """
    macro_impl = "stumpy" if _HAS_STUMPY else "self_znorm"
    # 统一时间轴（位置索引对齐；缺失月 NaN）
    R = stock_returns.reindex(month_ends)
    L = level_panel.reindex(month_ends)
    factors = [f for f in factors if f in L.columns]
    cands = [c for c in candidates if c in R.columns]

    # F5：训练段窗口搜索定 w（仅用训练期，防未来函数）
    train_sel = (month_ends >= train_start) & (month_ends <= train_end)
    ws = search_optimal_window(R.loc[train_sel], cands, grid=grid)
    ws.market = market
    w = ws.optimal_w

    test_months = list(month_ends[(month_ends >= test_start) & (month_ends <= test_end)])

    # excluded_narrow_pool 或空候选 → 不产信号（下游据 regime_tier 决定纳入），保留结构
    if regime_tier == "excluded_narrow_pool" or not cands or not factors:
        return SignalResult(
            market=market, index_code=index_code, regime_tier=regime_tier,
            optimal_w=w, macro_window=macro_m, ep_span=ep_span,
            factors=factors, candidates=cands, test_months=test_months,
            signals={}, r_hat={}, window_search=ws, matrix_profile_impl=macro_impl,
        )

    level_arrs = {j: L[j].to_numpy(dtype=float) for j in factors}
    ret_arrs = {c: R[c].to_numpy(dtype=float) for c in cands}
    pos_of = {ts: i for i, ts in enumerate(month_ends)}

    signals: dict[pd.Timestamp, pd.DataFrame] = {}
    r_hats: dict[pd.Timestamp, pd.DataFrame] = {}
    for t in test_months:
        pos_t = pos_of[t]
        # 阶段1：逐因子相似经济周期（缓存复用给所有资产）
        ep_end = {j: stage1_macro_period(level_arrs[j], pos_t, macro_m) for j in factors}
        rhat_mat = pd.DataFrame(np.nan, index=cands, columns=factors, dtype=float)
        for j in factors:
            h = ep_end[j]
            if h is None:
                continue
            for c in cands:
                rhat_mat.at[c, j] = stage2_asset_forecast(
                    ret_arrs[c], pos_t, w, h, ep_span=ep_span
                )
        sig_mat = rhat_mat.map(signal_from_rhat)
        r_hats[t] = rhat_mat
        signals[t] = sig_mat

    return SignalResult(
        market=market, index_code=index_code, regime_tier=regime_tier,
        optimal_w=w, macro_window=macro_m, ep_span=ep_span,
        factors=factors, candidates=cands, test_months=test_months,
        signals=signals, r_hat=r_hats, window_search=ws, matrix_profile_impl=macro_impl,
    )


def run_pattern_matching(
    prep,
    selection: dict,
    factors: Optional[list[str]] = None,
    *,
    grid: tuple[int, ...] = WINDOW_GRID,
    macro_m: int = MACRO_WINDOW_MONTHS,
    ep_span: int = EP_SPAN_MONTHS,
) -> dict[str, SignalResult]:
    """m4 主入口：三宽基各自两阶段 pattern-matching，返回 {市场名: SignalResult}。

    Args:
        prep:      m1 prepare_all() 产出（用 .markets/.macro.level_panel/.month_ends/区间）。
        selection: m2 run_selection(prep) 产出 {市场名: SelectionResult}（用 .candidates/.regime_tier）。
        factors:   参与阶段1 的宏观因子（默认 prep.macro.selected_factors，7 因子）。
        grid:      F5 窗口候选网格（默认 {2..10}）。
        macro_m:   阶段1 宏观窗口（=12，AS10）；ep_span：阶段2 经济周期跨度（=12）。

    Returns:
        dict[市场名 → SignalResult]；下游 m5 按市场取 .signals[t]（[资产×因子] ±1 矩阵）做
        FS 溢出加权聚合，据 .regime_tier 决定是否纳入（excluded_narrow_pool 无信号）。
    """
    factors = list(factors) if factors is not None else list(prep.macro.selected_factors)
    level_panel = prep.macro.level_panel
    month_ends = prep.month_ends
    results: dict[str, SignalResult] = {}
    for name, md in prep.markets.items():
        sel = selection[name]
        results[name] = run_market_pattern_matching(
            market=name,
            index_code=md.code,
            regime_tier=sel.regime_tier,
            stock_returns=md.stock_returns,
            level_panel=level_panel,
            candidates=list(sel.candidates),
            factors=factors,
            month_ends=month_ends,
            train_start=prep.train_start,
            train_end=prep.train_end,
            test_start=prep.test_start,
            test_end=prep.test_end,
            grid=grid, macro_m=macro_m, ep_span=ep_span,
        )
    return results


# ---------------------------------------------------------------------------
# 便捷：信号长表（供 m5 / verifier 方便消费）
# ---------------------------------------------------------------------------

def stack_signals(result: SignalResult) -> pd.DataFrame:
    """把单市场 signals 摊平为长表：month/asset/factor/signal/r_hat（供 m5/verifier）。"""
    rows = []
    for t in result.test_months:
        sig = result.signals.get(t)
        rh = result.r_hat.get(t)
        if sig is None:
            continue
        for c in result.candidates:
            for j in result.factors:
                rows.append({
                    "month": t, "asset": c, "factor": j,
                    "signal": sig.at[c, j],
                    "r_hat": (np.nan if rh is None else rh.at[c, j]),
                })
    return pd.DataFrame(rows, columns=["month", "asset", "factor", "signal", "r_hat"])


# ---------------------------------------------------------------------------
# 冒烟运行（仅确认可执行 + 打印选定 w / 信号形状 / 样例 / 依赖状态；验证结论归 verifier）
# ---------------------------------------------------------------------------

def _sig_stats(result: SignalResult) -> tuple[int, int, int, int]:
    """信号矩阵统计：+1 数 / −1 数 / NaN 数 / 总格。"""
    pos = neg = nan = tot = 0
    for t in result.test_months:
        sig = result.signals.get(t)
        if sig is None:
            continue
        v = sig.to_numpy()
        tot += v.size
        pos += int(np.nansum(v == 1.0))
        neg += int(np.nansum(v == -1.0))
        nan += int(np.isnan(v).sum())
    return pos, neg, nan, tot


def _smoke(smoke_test_months: int = 6) -> None:
    """冒烟：全跑 F5 定 w（真实候选集），信号仅跑前 smoke_test_months 个测试月控速。"""
    from src.ssrn_6115073.data_prep import prepare_all
    from src.ssrn_6115073.selection import run_selection

    pd.set_option("display.width", 170)
    pd.set_option("display.max_columns", 20)
    print("=" * 88)
    print("m4 两阶段 Matrix Profile 模式匹配与信号冒烟 · ssrn_6115073（F5/F6/F7/F8）")
    print("=" * 88)
    print(f"[依赖] stumpy 可用={_HAS_STUMPY} → matrix profile 实现="
          f"{'stumpy(Z-归一化MP)' if _HAS_STUMPY else 'self_znorm(自实现Z-归一化欧氏, AS45退化)'}")
    print(f"[参数] 窗口网格 w∈{WINDOW_GRID}（F5/AS7） 宏观窗口={MACRO_WINDOW_MONTHS}月(AS10) "
          f"EP跨度={EP_SPAN_MONTHS}月 最少训练预测点={MIN_TRAIN_PRED_POINTS}")

    prep = prepare_all()
    selection = run_selection(prep)
    factors = list(prep.macro.selected_factors)
    print(f"[宏观因子] ({len(factors)}) {factors}")
    print(f"[区间] 训练 {prep.train_start.date()}~{prep.train_end.date()} 定 w；"
          f"测试 {prep.test_start.date()}~{prep.test_end.date()}（冒烟仅前 {smoke_test_months} 月产信号）")

    # 冒烟截断：只跑前 smoke_test_months 个测试月，避免全量耗时（不改方法，仅缩测试轴）
    full_test = prep.month_ends[(prep.month_ends >= prep.test_start)
                                & (prep.month_ends <= prep.test_end)]
    smoke_end = full_test[min(smoke_test_months, len(full_test)) - 1]

    print("\n" + "-" * 88)
    print("三宽基 F5 窗口搜索（全训练集定 w）+ 前若干测试月信号：")
    print("-" * 88)
    for name, md in prep.markets.items():
        sel = selection[name]
        res = run_market_pattern_matching(
            market=name, index_code=md.code, regime_tier=sel.regime_tier,
            stock_returns=md.stock_returns, level_panel=prep.macro.level_panel,
            candidates=list(sel.candidates), factors=factors,
            month_ends=prep.month_ends,
            train_start=prep.train_start, train_end=prep.train_end,
            test_start=prep.test_start, test_end=smoke_end,   # 冒烟截断测试轴
        )
        ws = res.window_search
        mse_str = ", ".join(f"w{w}={ws.mse_by_w[w]:.5f}" for w in WINDOW_GRID)
        print(f"\n[{name} / {md.code}]  tier={res.regime_tier}  候选资产={len(res.candidates)}  "
              f"最优 w={res.optimal_w}（训练序列={ws.n_series_used} 预测点={ws.n_pred_points_total}）")
        print(f"   各 w 平均 MSE: {mse_str}")
        if res.regime_tier == "excluded_narrow_pool" or not res.candidates:
            print("   → 该市场 excluded/空候选，跳过信号生成（下游据 tier 处理）")
            continue
        pos, neg, nan, tot = _sig_stats(res)
        cov = 100.0 * (pos + neg) / tot if tot else 0.0
        print(f"   信号: 测试月={len(res.test_months)} 每月矩阵={len(res.candidates)}资产×{len(res.factors)}因子"
              f" | +1={pos} −1={neg} NaN={nan} 覆盖率={cov:.1f}%")
        # 样例：首个测试月的信号矩阵片段（前 6 资产 × 全因子）
        t0 = res.test_months[0]
        sig0 = res.signals[t0]
        print(f"   [样例] 首测试月 {t0.date()} 信号矩阵（前 6 资产 × {len(res.factors)} 因子）：")
        print(sig0.head(6).to_string())

    print("\n" + "-" * 88)
    print("未来函数自检（结构性约束，非数值结论）：")
    print("-" * 88)
    print(f"  1. F5 定 w 仅用训练段 [{prep.train_start.date()}, {prep.train_end.date()}]，测试期不进入。")
    print("  2. 阶段1 历史经济周期窗口结束 h ≤ pos_t − 宏观窗口(与 query 不重叠、严格更早)。")
    print("  3. 阶段2 历史价格窗口结束 g ≤ min(h, pos_t − 2) → 之后一期 g+1 ≤ pos_t − 1 < pos_t。")
    print("  4. query 窗口结束于 pos_t（截至 t 已实现收益/已披露宏观），信号 T 算、T+1 执行由 m6 承接。")

    # 长表接口示例
    demo = run_market_pattern_matching(
        market="hs300", index_code=prep.markets["hs300"].code,
        regime_tier=selection["hs300"].regime_tier,
        stock_returns=prep.markets["hs300"].stock_returns,
        level_panel=prep.macro.level_panel,
        candidates=list(selection["hs300"].candidates), factors=factors,
        month_ends=prep.month_ends,
        train_start=prep.train_start, train_end=prep.train_end,
        test_start=prep.test_start, test_end=smoke_end,
    )
    long = stack_signals(demo)
    print(f"\n[下游 m5 接口] run_pattern_matching(prep, selection) → dict[市场 → SignalResult]；"
          f"每月 .signals[t]=[资产×因子]±1；stack_signals 长表 shape={long.shape} "
          f"列={list(long.columns)}")
    print("\n冒烟完成：两阶段 pattern-matching 可端到端构造（可执行性确认；验证结论由 verifier 判定）。")


if __name__ == "__main__":
    _smoke()
