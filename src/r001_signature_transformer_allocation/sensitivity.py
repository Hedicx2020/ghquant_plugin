"""r001 · SIT 敏感性/机制分析（milestone m5：SA2 / SA3 / SA4）。

职责（严格对 spec，页码引用制，对应 coverage_matrix milestone=m5 的 SA2/SA3/SA4/B4）：
- SA2 (Figure 3, p7) 签名强度-注意力相关分布：在每决策时刻 t，逐资产 j 计算
  签名强度 s_{t,j}=[1/(H·N_H·d)]·Σ_{k,h,m}(B_{k,h})_{m,j}（对签名偏置矩阵 B 沿切片 k、头 h、
  来源资产 m 求和归一）与入向注意力份额 a_{t,j}=[1/(H·N_H·d)]·Σ_{k,h,m}α_{k,h,m→j}
  （指向 j 的注意力权重同样求和归一），对 {s_{t,j}}、{a_{t,j}} 求横截面 Pearson 相关，
  考察其在测试期的分布（原文右偏、均值 0.540/0.611，印证 Theorem 2.2 单调性）。
- SA3 (Figure 5, p8) + B4 交易成本×τ 敏感性：sweep τ × 单边成本 c∈{0,5,10}bps（B4），
  其余同主评估（long-only/fully-invested/月度调仓），产每 (τ,c) 的 Sharpe 网格（AS10 自生成、
  定性对比：峰值近 τ≈1.3、成本近似线性压缩 Sharpe）。
- SA4 (Figure 6, p8) τ 多样化影响：变动 τ，观察集中度 HHI(w)=Σ_j w_j² 与 Shannon 熵
  H(w)=−Σ_j w_j·log w_j 的单调关系（τ↑ ⇒ HHI↓、熵↑）。

复用 m4 基础设施（backtest.sit_weight_panel/run_portfolio/performance_metrics），不重复实现
回测引擎。SA2 用 model 前向 return_aux 暴露的偏置 B 与注意力 α（model.SignatureAssetAttention），
SA3/SA4 用同一已训练 SIT 模型在不同 τ 前向（无需重训，只前向）。数值豁免（experimental）。

未来函数红线：均在 test 段决策日上评估（点时特征，m2 保证只用 [t−H,t] 历史）；SA3 成本经
换手扣减（common.portfolio_backtest），不引入未来信息。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np
import pandas as pd
import torch

from .backtest import performance_metrics, run_portfolio, sit_weight_panel
from .config import DEFAULT_CONFIG, SITConfig


# =====================================================================
# SA2 · 签名强度 s_{t,j} 与入向注意力份额 a_{t,j} 横截面相关（Figure 3）
# =====================================================================

def _cross_sectional_pearson(s: np.ndarray, a: np.ndarray) -> float:
    """两向量的 Pearson 相关（横截面，资产维）；任一方零方差返回 nan（不计入分布）。"""
    if s.std() < 1e-12 or a.std() < 1e-12:
        return float("nan")
    return float(np.corrcoef(s, a)[0, 1])


@torch.no_grad()
def signature_attention_scores(
    model, feat: dict, block: int = -1
) -> tuple[np.ndarray, np.ndarray]:
    """逐决策时刻 t、逐资产 j 的签名强度 s_{t,j} 与入向注意力份额 a_{t,j}（SA2 定义式）。

    从 SIT 前向 return_aux 暴露的指定 block 的偏置 B（aux["bias"]）与注意力 α（aux["attn"]，
    形状 (N,H,N_H,d_query,d_key)）计算。约定 tensor[...,q,l]=query q→key l；spec 的 m→j
    （来源 m→目标 j）即 query=m、key=j，故对 j 的求和 = 沿 (切片 H、头 N_H、来源 query) 求和、
    保留 key 轴（目标 j），再除 H·N_H·d 归一。

    Returns:
        (s, a) 各 (N, d)：N=测试期决策日数，d=资产数；行 t 为该时刻横截面 {·_{t,j}}。
    """
    model.eval()
    _, aux = model.forward_from_features(feat, return_aux=True)
    blk = aux["attns"][block]
    if blk is None or "bias" not in blk or "attn" not in blk:
        raise RuntimeError("SA2 需 return_aux 的 attn/bias（该 block 或被消融跳过）")
    attn = blk["attn"]                       # (N,H,N_H,d,d)
    bias = blk["bias"]                       # (N,H,N_H,d,d)
    _, h, nh, d, _ = attn.shape
    norm = float(h * nh * d)                 # 1/(H·N_H·d)
    # 沿 H(dim1)、N_H(dim2)、来源 query(dim3) 求和，保留 key 轴=目标 j(dim4)
    s = bias.sum(dim=(1, 2, 3)).cpu().numpy() / norm   # (N,d) 签名强度
    a = attn.sum(dim=(1, 2, 3)).cpu().numpy() / norm   # (N,d) 入向注意力份额
    return s, a


def signature_attention_correlation(model, feat: dict, block: int = -1) -> np.ndarray:
    """逐决策时刻 t 的横截面 Pearson 相关序列 {ρ_t}（SA2，Figure 3 分布母源）。"""
    s, a = signature_attention_scores(model, feat, block=block)
    return np.array([_cross_sectional_pearson(s[t], a[t]) for t in range(s.shape[0])], dtype=float)


def run_sa2(model, feat: dict, config: SITConfig = DEFAULT_CONFIG, log=print) -> dict:
    """SA2：相关分布统计（均值/中位/std/正相关占比；右偏＝均值>中位）。"""
    rho = signature_attention_correlation(model, feat)
    valid = rho[~np.isnan(rho)]
    if valid.size == 0:
        log("[SA2] 相关序列全 nan（横截面零方差，通常因欠训练/单资产）")
        return {"n": 0, "mean": float("nan"), "median": float("nan"),
                "std": float("nan"), "pos_share": float("nan")}
    stats = {
        "n": int(valid.size),
        "mean": float(valid.mean()),
        "median": float(np.median(valid)),
        "std": float(valid.std()),
        "pos_share": float((valid > 0).mean()),
        "right_skew": bool(valid.mean() > np.median(valid)),
    }
    log(f"[SA2] 签名强度-注意力横截面 Pearson：n={stats['n']} 均值={stats['mean']:.4f} "
        f"中位={stats['median']:.4f} std={stats['std']:.4f} 正相关占比={stats['pos_share']:.2%} "
        f"右偏(均值>中位)={stats['right_skew']}（原文均值 0.540/0.611，印证 Thm2.2）")
    return stats


# =====================================================================
# SA3 + B4 · 交易成本 × 温度 τ 的 Sharpe 敏感性网格（Figure 5）
# =====================================================================

def sharpe_tau_cost_grid(
    model,
    feat: dict,
    bundle,
    monthly: pd.DataFrame,
    config: SITConfig = DEFAULT_CONFIG,
    *,
    taus: Optional[tuple] = None,
    costs_bps: Optional[tuple] = None,
    log=print,
) -> pd.DataFrame:
    """(τ, c) → Sharpe 网格（SA3/B4）。权重面板只依赖 τ（每 τ 算一次），成本仅在回测扣减。

    Args:
        model: 已训练 SIT（复用，不重训）。
        feat: test 段 F_ti 特征（build_test_inputs）。
        bundle/monthly: m1 数据底座 + 月度收益面板（结算母源）。
        taus: τ 网格（默认 config.sit_tau_grid，SA3 sweep τ∈{0.8,…,1.4}）；冒烟可传子集。
        costs_bps: 单边成本档 c∈{0,5,10}bps（B4）。

    Returns:
        DataFrame index=τ、columns=f"{c}bps"、值=Sharpe（数值豁免，定性峰值/成本斜率）。
    """
    taus = tuple(taus) if taus is not None else tuple(config.sit_tau_grid)     # SA3 τ sweep 复用 sit_tau_grid（AS6/AS10）
    costs = tuple(costs_bps) if costs_bps is not None else tuple(config.sa3_cost_grid_bps)  # B4 c∈{0,5,10}bps
    rows: dict[float, dict[str, float]] = {}
    for tau in taus:
        panel = sit_weight_panel(model, feat, bundle, config, tau=float(tau))  # 只依赖 τ
        row: dict[str, float] = {}
        for c in costs:
            bt = run_portfolio(panel, monthly, replace(config, cost_bps=float(c)))  # 成本经换手扣减
            row[f"{c:g}bps"] = float(performance_metrics(bt, config)["Sharpe"])
        rows[float(tau)] = row
        log(f"[SA3] τ={tau:<4} " + " ".join(f"{k}={v:+.4f}" for k, v in row.items()))
    grid = pd.DataFrame(rows).T
    grid.index.name = "tau"
    return grid


def run_sa3(
    model, feat: dict, bundle, monthly: pd.DataFrame, config: SITConfig = DEFAULT_CONFIG,
    *, taus: Optional[tuple] = None, costs_bps: Optional[tuple] = None, log=print,
) -> dict:
    """SA3：产 (τ,c) Sharpe 网格 + 提炼要点（最优 τ、0→10bps 成本压缩幅度）。"""
    grid = sharpe_tau_cost_grid(model, feat, bundle, monthly, config,
                                taus=taus, costs_bps=costs_bps, log=log)
    zero_col = grid.columns[0]
    best_tau = float(grid[zero_col].idxmax())
    cost_cols = list(grid.columns)
    drop = float(grid.loc[best_tau, cost_cols[0]] - grid.loc[best_tau, cost_cols[-1]])
    log(f"[SA3] 0bps 最优 τ={best_tau}（Sharpe={grid.loc[best_tau, cost_cols[0]]:.4f}）；"
        f"该 τ 下 {cost_cols[0]}→{cost_cols[-1]} 成本压缩 ΔSharpe={drop:+.4f}"
        f"（原文最优点降约 0.03–0.04，AS10 定性对比）")
    return {"grid": grid, "best_tau": best_tau, "cost_drop_at_best": drop}


# =====================================================================
# SA4 · 温度 τ 对组合多样化（HHI / Shannon 熵）的单调影响（Figure 6）
# =====================================================================

@torch.no_grad()
def diversification_vs_tau(
    model,
    feat: dict,
    config: SITConfig = DEFAULT_CONFIG,
    *,
    taus: Optional[tuple] = None,
) -> pd.DataFrame:
    """τ → (HHI, Shannon 熵)（SA4，Figure 6）。用原始 softmax 分配权重 w^(step) 度量纯 τ 集中度效应。

    HHI(w)=Σ_j w_j²（∈(0,1]，越大越集中）；H(w)=−Σ_j w_j·log w_j（越大越分散）。
    对测试期各决策日的横截面权重求指标后取均值（τ↑ ⇒ HHI↓、熵↑，spec Fig6）。
    """
    taus = tuple(taus) if taus is not None else tuple(config.sa4_tau_grid)   # SA4 Fig6 τ 轴范围（config）
    step = config.backtest_decision_step
    rows: dict[float, dict[str, float]] = {}
    for tau in taus:
        w_all = model.forward_from_features(feat, tau=float(tau))   # (N,K,d) softmax(µ̂/τ)
        w = w_all[:, step, :].clamp_min(0.0)                        # (N,d) 各决策日横截面权重
        hhi = (w * w).sum(dim=-1)                                   # (N,) Σw²
        entropy = -(w * torch.log(w.clamp_min(1e-12))).sum(dim=-1)  # (N,) −Σw·log w
        rows[float(tau)] = {"HHI": float(hhi.mean()), "Entropy": float(entropy.mean())}
    df = pd.DataFrame(rows).T
    df.index.name = "tau"
    return df


def run_sa4(
    model, feat: dict, config: SITConfig = DEFAULT_CONFIG,
    *, taus: Optional[tuple] = None, log=print,
) -> dict:
    """SA4：产 τ→HHI/熵 表 + 单调性判定（τ↑ 期望 HHI 单调降、熵单调升）。"""
    df = diversification_vs_tau(model, feat, config, taus=taus)
    hhi_mono_down = bool((df["HHI"].diff().dropna() < 0).all())
    ent_mono_up = bool((df["Entropy"].diff().dropna() > 0).all())
    for tau, r in df.iterrows():
        log(f"[SA4] τ={tau:<5} HHI={r['HHI']:.4f} 熵={r['Entropy']:.4f}")
    log(f"[SA4] τ↑ ⇒ HHI 单调降={hhi_mono_down}、熵单调升={ent_mono_up}（spec Fig6 定性）")
    return {"table": df, "hhi_monotone_down": hhi_mono_down, "entropy_monotone_up": ent_mono_up}
