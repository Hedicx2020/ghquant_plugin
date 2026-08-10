"""r001 · SIT 路径签名 / 成对交叉签名 / 决策时刻信息集 F_ti 组装（milestone m2）。

职责（严格对 spec，页码引用制）：
- D5 (p2) 连续路径重建：离散前复权价 → 线性插值 piecewise-linear 路径（AS20）；对分段
  线性路径 M=2 截断签名有精确闭式，无需 signatory/iisignature/esig（AS17）。D5-(ii)
  实现收益向量 r_t（K 步月度实现收益）为**标签/未来数据**，见 `realized_forward_returns`。
- F1 (p2,p16) 路径签名 M=2：SigM(X)=(1, ∫dX, ∫∫dX⊗dX)；level-1=净增量、level-2=二阶
  迭代积分（含对角与 signed-area 项）；逐资产在 H=60 回看窗口切片上算，Chen relation
  增量更新逐 token 避免全历史重算（p3；AS2/AS17）。
- F2 (p2,p12 Eq.21) 成对交叉签名：A(X^i,X^j)=∫X^i dX^j − ∫X^j dX^i（signed area），逐资产
  对在全窗口 [t−H,t] 算 c_{i,j,l}∈R^{d_cross-sig}（d_cross-sig=2，AS7）；编码 lead-lag
  （Proposition 2.1：严格 lead-lag ⇒ A>0）。
- D4 (p2) F_ti 组装：(i) 每资产 H 切片截断签名 + (ii) 全窗口资产对交叉签名 + (iii) H 个
  日历特征 v_t（AS4）。
- B8 (p2) 窗口：H=60 回看、K=12 多步（config.lookback_h/decision_steps_k，AS2）。

点时红线（code_audit/codex 逐点核查）：决策时刻 t 的签名/交叉签名**只用 [t−H, t] 窗口内
数据**（daily_log_returns 截至并含 t 的最后 H 行），绝不用 t 之后信息；D5-(ii) 的 K 步实现
收益是标签（未来数据），仅供 m4 组合损失 L^(k)=−wᵀr（F7）与回测结算（B6），绝不回流为
模型输入特征。

自实现说明（AS17/AS20）：本地无签名库，M=2 解析可算。分段线性路径单段签名 level-2=½Δ⊗Δ，
多段经 Chen relation 拼接（level-1 可加、level-2 累加 running_level1⊗δ + ½δ⊗δ）；对角项由
shuffle 恒等式 S_ii=½(ΔX_i)² 精确、off-diagonal signed-area 由迭代积分累加。核心 Chen 循环
（`signature_m2_parts`）为**可读参考实现**，窗口向量化版（`asset_signature_sequence` /
`cross_signature_matrix`）为其**数值等价加速**——test_signatures.py 断言两者逐元素一致。

本模块纯 numpy（不依赖 torch，torch 属 m3/m4）；通用签名多为本案特有，置 src/。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Sequence

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG, SITConfig

if TYPE_CHECKING:  # 仅类型标注，运行时不导入 data（保持核心签名数学纯 numpy 可测）
    from .data import DataBundle


# =====================================================================
# 一、核心 M=2 签名（可读参考实现，Chen relation 增量；F1 p2,p16 / AS17,AS20）
# =====================================================================

def signature_m2_parts(path: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """M=2 截断签名的 level-1 / level-2（Chen relation 逐段增量，参考实现）。

    对分段线性（线性插值，AS20）路径逐段拼接：单段增量 δ 贡献
    ``level2 += (running level-1) ⊗ δ + ½ δ ⊗ δ``，随后 ``level1 += δ``。
    该递推对 piecewise-linear 路径**精确**（等价 Chen 恒等式逐段 tensor product），
    避免对每个新观测重算全历史迭代积分（F1 p3「Chen relation ... avoids recomputation
    over the full history」）。

    Args:
        path: 形状 (L, p)，L 个观测的 p 维离散路径（L≥1）。

    Returns:
        level1: (p,) 净增量 ∫dX = X_{L-1} − X_0。
        level2: (p, p) 二阶迭代积分，level2[a,b] = ∫ (X^a − X0^a) dX^b。
    """
    arr = np.asarray(path, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"path 须为 (L, p) 二维，实际 {arr.shape}")
    _, p = arr.shape
    level1 = np.zeros(p, dtype=float)
    level2 = np.zeros((p, p), dtype=float)
    for k in range(1, arr.shape[0]):
        delta = arr[k] - arr[k - 1]
        level2 += np.outer(level1, delta) + 0.5 * np.outer(delta, delta)
        level1 += delta
    return level1, level2


def signature_m2(path: np.ndarray, include_level0: bool = True) -> np.ndarray:
    """M=2 截断签名扁平向量：[1?, level1(p), level2(p², 行主序)]（F1 SigM=(1,∫dX,∫∫dX⊗dX)）。"""
    level1, level2 = signature_m2_parts(path)
    blocks = ([np.array([1.0])] if include_level0 else []) + [level1, level2.reshape(-1)]
    return np.concatenate(blocks)


def signature_m2_sequence(path: np.ndarray, include_level0: bool = True) -> np.ndarray:
    """逐步 running 签名序列（Chen 增量；F1 p3「signature update uses Chen relation」）。

    返回 (L-1, d_sig)：第 k 行 = 子路径 [X_0 .. X_k] 的 M=2 签名（k=1..L-1），
    由前一步签名 O(p²) 增量得到，不重算全历史。
    """
    arr = np.asarray(path, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"path 须为 (L, p) 二维，实际 {arr.shape}")
    _, p = arr.shape
    level1 = np.zeros(p, dtype=float)
    level2 = np.zeros((p, p), dtype=float)
    rows: list[np.ndarray] = []
    for k in range(1, arr.shape[0]):
        delta = arr[k] - arr[k - 1]
        level2 = level2 + np.outer(level1, delta) + 0.5 * np.outer(delta, delta)
        level1 = level1 + delta
        blocks = ([np.array([1.0])] if include_level0 else []) + [level1.copy(), level2.reshape(-1)]
        rows.append(np.concatenate(blocks))
    return np.asarray(rows)


def levy_area(path2d: np.ndarray) -> float:
    """2D 路径的 signed area（Lévy area）A = ∫X^0 dX^1 − ∫X^1 dX^0 = S[0,1] − S[1,0]（Eq.21）。

    平移不变（仅依赖增量），是 lead-lag 的稳健度量（Proposition 2.1）。
    """
    arr = np.asarray(path2d, dtype=float)
    if arr.shape[1] != 2:
        raise ValueError(f"levy_area 需 2D 路径，实际列数 {arr.shape[1]}")
    _, level2 = signature_m2_parts(arr)
    return float(level2[0, 1] - level2[1, 0])


# =====================================================================
# 二、窗口向量化签名（等价上节参考实现的加速；F1/F2）
# =====================================================================
# 约定：窗口内累积对数收益路径 rebased 起点为 0（AS22）——
#   给定日增量 R∈R^{H×d}（H 个日对数收益），X_k = Σ_{m≤k} R_m（k=1..H），X_0≡0。
#   签名平移不变故 rebase 不改结果，且对数收益跨资产量纲可比、数值良态。

def cross_signature_matrix(returns_window: np.ndarray) -> np.ndarray:
    """全窗口成对二阶交叉积分矩阵 S[i,j]=∫X^i dX^j（F2，向量化，覆盖 [t−H,t] 全窗口）。

    分段线性路径闭式（等价 signature_m2_parts 逐对 level-2）：
        S = P^T · δ + ½ δ^T · δ，  其中 δ=日增量(=R)、P=前段水平 X_{k-1}。
    对角 S[i,i]=½(ΔX_i)²（shuffle 恒等），off-diagonal 编码 signed-area。

    Args:
        returns_window: (H, d) 窗口内 H 个日对数收益（路径增量）。
    Returns:
        S: (d, d)，S[i,j]=∫X^i dX^j 全窗口积分。
    """
    R = np.asarray(returns_window, dtype=float)
    if R.ndim != 2:
        raise ValueError(f"returns_window 须为 (H, d)，实际 {R.shape}")
    _, d = R.shape
    cum = np.cumsum(R, axis=0)                                   # X_1..X_H
    x_prev = np.vstack([np.zeros((1, d)), cum[:-1]])            # X_0..X_{H-1}（前段水平）
    return x_prev.T @ R + 0.5 * (R.T @ R)


def cross_signature_pairs(returns_window: np.ndarray) -> np.ndarray:
    """成对交叉签名张量 C (d, d, 2)：C[i,j]=(∫X^i dX^j, ∫X^j dX^i)（F2 / AS7 d_cross-sig=2）。

    供 m3 关系嵌入 β_{i,j,l}=MLPβ(c_{i,j,l}) 的资产对输入（Eq.8）。
    """
    S = cross_signature_matrix(returns_window)
    return np.stack([S, S.T], axis=-1)


def signed_area_matrix(returns_window: np.ndarray) -> np.ndarray:
    """成对 signed-area A[i,j]=∫X^i dX^j − ∫X^j dX^i = S − S^T（反对称，Eq.21；lead-lag）。"""
    S = cross_signature_matrix(returns_window)
    return S - S.T


def asset_signature_sequence(
    returns_window: np.ndarray,
    config: SITConfig = DEFAULT_CONFIG,
) -> np.ndarray:
    """逐资产 H 切片 running M=2 签名序列（时间增广，向量化；F1 / D4-(i) / AS21）。

    每资产路径 = 时间增广 2D 路径 (t_k=k/H, X_k=窗口累积对数收益)；第 k 切片为子路径
    [0..k] 的 M=2 签名（Chen 语义，向量化实现）。level-2 分量：
      S_tt=½t_k²、S_XX=½X_k²（shuffle 恒等，任意路径成立）；
      S_tX=∫t dX=Σ_{m≤k}(m−0.5)/H·r_m（cumsum）；S_Xt=∫X dt=t_k·X_k−S_tX（shuffle）。
    未时间增广时退化为 1D 路径 (X_k) 的签名 (1, X_k, ½X_k²)。

    Args:
        returns_window: (H, d) 窗口内 H 个日对数收益。
    Returns:
        (H, d, d_sig)，d_sig = config.asset_signature_dim（时间增广+level0 → 7）。
    """
    R = np.asarray(returns_window, dtype=float)
    if R.ndim != 2:
        raise ValueError(f"returns_window 须为 (H, d)，实际 {R.shape}")
    H, d = R.shape
    cum = np.cumsum(R, axis=0)                                   # (H,d) = X_k
    if config.signature_time_augment:
        t_k = (np.arange(1, H + 1, dtype=float) / H)[:, None]   # (H,1) 归一化时间
        seg_w = ((np.arange(H, dtype=float) + 0.5) / H)[:, None]  # (H,1) 段权重 (m−0.5)/H
        s_tx = np.cumsum(seg_w * R, axis=0)                     # (H,d) = ∫t dX
        ones = np.ones((H, d))
        t_col = np.broadcast_to(t_k, (H, d)).copy()            # level1 时间分量
        s_tt = np.broadcast_to(0.5 * t_k ** 2, (H, d)).copy()  # ½t²
        s_xx = 0.5 * cum ** 2                                  # ½X²
        s_xt = t_k * cum - s_tx                                # ∫X dt（shuffle）
        # 顺序: level0(1), level1=(t,X), level2 行主序=[S_tt,S_tX,S_Xt,S_XX]
        sig = np.stack([ones, t_col, cum, s_tt, s_tx, s_xt, s_xx], axis=-1)
    else:
        s_xx = 0.5 * cum ** 2
        sig = np.stack([np.ones((H, d)), cum, s_xx], axis=-1)   # (H,d,3)
    if not config.signature_include_level0:
        sig = sig[..., 1:]
    return sig


# =====================================================================
# 三、决策时刻信息集 F_ti 组装（D4 p2）
# =====================================================================

@dataclass
class SignatureFeatures:
    """单一决策时刻 t_i 的信息集 F_ti（D4，仅用 [t−H, t] 窗口，点时安全）。"""

    decision_date: pd.Timestamp
    codes: list[str]
    asset_signatures: np.ndarray    # (H, d, d_sig) 逐切片逐资产 M=2 签名（D4-i / F1）
    cross_signatures: np.ndarray    # (d, d, 2)     全窗口资产对交叉签名（D4-ii / F2, AS7）
    signed_area: np.ndarray         # (d, d)        成对 signed-area A=S−S^T（Eq.21，供 m3 β/诊断）
    calendar: np.ndarray            # (H, F)        H 个日历特征 v_t（D4-iii / AS4）
    window_dates: pd.DatetimeIndex  # 窗口 H 天日期（点时红线可核：末日=决策日、无未来）

    def shapes(self) -> dict:
        """关键形状摘要（冒烟/审计用）。"""
        return {
            "decision_date": str(self.decision_date.date()),
            "window_start": str(self.window_dates[0].date()),
            "window_end": str(self.window_dates[-1].date()),
            "n_assets": len(self.codes),
            "asset_signatures": tuple(self.asset_signatures.shape),
            "cross_signatures": tuple(self.cross_signatures.shape),
            "signed_area": tuple(self.signed_area.shape),
            "calendar": tuple(self.calendar.shape),
        }


def _decision_pos(bundle: "DataBundle", decision_date: pd.Timestamp) -> int:
    """决策日在日频索引中的整数位置（须为交易日/调仓日）。"""
    idx = bundle.daily_log_returns.index
    ts = pd.Timestamp(decision_date)
    if ts not in idx:
        raise KeyError(f"决策日 {ts.date()} 不在交易日索引内（应为交易日/调仓日）")
    pos = idx.get_loc(ts)
    if not isinstance(pos, (int, np.integer)):
        raise KeyError(f"决策日 {ts.date()} 非唯一定位（索引重复？）")
    return int(pos)


def build_signature_features(
    bundle: "DataBundle",
    decision_date: pd.Timestamp,
    config: SITConfig = DEFAULT_CONFIG,
) -> SignatureFeatures:
    """组装单一决策时刻 F_ti（D4）。

    点时红线：窗口 = daily_log_returns 中截至并含决策日的**最后 H 行**（H=config.lookback_h），
    绝不含决策日之后的行；日历特征取同窗 H 行。签名/交叉签名/signed-area 全在该窗口内算。
    """
    H = config.lookback_h
    pos = _decision_pos(bundle, decision_date)
    if pos < H:
        raise ValueError(
            f"决策日 {pd.Timestamp(decision_date).date()} 前仅 {pos} 个交易日 < H={H}，历史不足（B8/AS2）"
        )
    lo, hi = pos - H + 1, pos + 1              # H 行，含决策日，绝不含 t 之后（点时红线）

    ret_win = bundle.daily_log_returns.iloc[lo:hi]
    R = ret_win.to_numpy(dtype=float)          # (H, d)
    cal = bundle.calendar_features.iloc[lo:hi].to_numpy(dtype=float)  # (H, F)

    return SignatureFeatures(
        decision_date=pd.Timestamp(decision_date),
        codes=list(bundle.universe_codes),
        asset_signatures=asset_signature_sequence(R, config),   # (H, d, d_sig)
        cross_signatures=cross_signature_pairs(R),              # (d, d, 2)
        signed_area=signed_area_matrix(R),                      # (d, d)
        calendar=cal,                                           # (H, F)
        window_dates=ret_win.index,
    )


def build_feature_tensors(
    bundle: "DataBundle",
    decision_dates: Sequence[pd.Timestamp],
    config: SITConfig = DEFAULT_CONFIG,
) -> dict[str, object]:
    """堆叠多决策时刻的 F_ti 特征张量（供 m3 训练/前向）。

    跳过历史不足（前序交易日 < H）或不在交易日索引的决策日；返回实际使用的日期。
    """
    H = config.lookback_h
    idx = bundle.daily_log_returns.index
    feats: list[SignatureFeatures] = []
    used: list[pd.Timestamp] = []
    for d in pd.DatetimeIndex(decision_dates):
        pos = idx.get_indexer([d])[0]
        if pos < H:                                             # -1（不在索引）或历史不足
            continue
        feats.append(build_signature_features(bundle, d, config))
        used.append(d)
    if not feats:
        raise RuntimeError("无有效决策日（均历史不足或不在交易日索引）")
    return {
        "decision_dates": pd.DatetimeIndex(used),
        "codes": feats[0].codes,
        "asset_signatures": np.stack([f.asset_signatures for f in feats]),  # (T, H, d, d_sig)
        "cross_signatures": np.stack([f.cross_signatures for f in feats]),  # (T, d, d, 2)
        "signed_area": np.stack([f.signed_area for f in feats]),            # (T, d, d)
        "calendar": np.stack([f.calendar for f in feats]),                  # (T, H, F)
    }


# =====================================================================
# 四、D5-(ii) 实现收益向量 r_t（标签/未来数据，供 m4；非模型输入特征）
# =====================================================================

def realized_forward_returns(
    bundle: "DataBundle",
    decision_date: pd.Timestamp,
    config: SITConfig = DEFAULT_CONFIG,
    *,
    split_end: pd.Timestamp,
) -> Optional[np.ndarray]:
    """D5-(ii) 实现收益向量 r_t：决策日 t_i 之后 K 个月度区间各资产实现简单收益 (K, d)。

    **标签/未来数据**：r 覆盖 (t_{i+k−1}, t_{i+k}]（k=1..K），仅供 m4 组合损失
    L^(k)=−(w^(k))ᵀr（F7 Eq.17）与回测结算（B6），**绝不回流为模型输入特征**（点时红线）。
    月度区间实现收益 = 相邻调仓日间日简单收益复利（daily_simple_returns，停牌期 0 占位，AS19）。
    未来调仓不足 K 期（临近 test 末端）返回 None，由 m4 尾部截断（AS2）。

    **split 边界 purge（CDX-C-01 源头硬闭环，防边界标签泄漏）**：``split_end`` 为**必填关键字
    参数**（已去除 None 默认旁路）——收到 None/NaT 立即 raise ValueError，绝不静默退化为不过滤；
    仅保留第 K 个未来锚点 ``t_{i+K}`` **不晚于** ``split_end`` 的样本，否则该样本标签窗口越过 split
    边界、使用了下一 split（如验证/测试期）的实现收益。train 尾部、val 尾部各会因此 purge 掉标签
    越界的约 K 个决策点，确保 test 区间对 early stopping / 网格 / τ 选优完全封存。任何入口（含
    -O 优化模式、直调底层 API）都无法生成越界标签。
    """
    if split_end is None or pd.isna(split_end):
        raise ValueError(
            "realized_forward_returns 的 split_end 为必填时点边界，收到 None/NaT——标签必须显式"
            "封存 split 边界（CDX-C-01 源头闭环），拒绝无边界（不过滤）的未来收益标签"
        )
    K = config.decision_steps_k
    ts = pd.Timestamp(decision_date)
    split_end_ts = pd.Timestamp(split_end)
    rb = bundle.rebalance_dates
    later = rb[rb >= ts]
    if len(later) < K + 1:
        return None
    anchors = later[: K + 1]                                    # t_i, t_{i+1}, ..., t_{i+K}
    if pd.Timestamp(anchors[K]) > split_end_ts:
        return None                                            # 标签终点越过 split 边界 → purge（CDX-C-01）
    simple = bundle.daily_simple_returns
    out = np.empty((K, len(bundle.universe_codes)), dtype=float)
    for k in range(K):
        a, b = anchors[k], anchors[k + 1]
        seg = simple.loc[(simple.index > a) & (simple.index <= b)]  # (a, b] 区间日收益
        out[k] = (1.0 + seg.to_numpy(dtype=float)).prod(axis=0) - 1.0
    return out
