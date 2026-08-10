"""r001 · 对比基线（milestone m4：B5 传统 4 基线 + B7 两阶段预测类 DLinear）。

职责（严格对 spec，页码引用制，对应 coverage_matrix milestone=m4 的 B5/B7）：
- B5 (p5) 传统基线 4 个：
    · EW（等权 EWP）        → 复用 common.allocation_backtest.equal_weights
    · GMV（全局最小方差）    → 复用 common.allocation_backtest._min_variance_weights（plan m4 明列）
    · HRP（层次风险平价）    → 复用 common.allocation_backtest.hrp_weights
    · CVaR（最小 CVaR 组合） → 本模块新增（common 无此权重模型，Rockafellar-Uryasev LP）
- B7 (p18) 两阶段 Predict-then-Optimize 基线（缩减仅 DLinear，AS15）：
    · 阶段一：DLinear（Zeng et al. 2023 序列分解线性）以 MSE 训练预测下期收益 r̂（F8 对照的 PFL）；
    · 阶段二：冻结预测器，min-CVaR 组合优化，加目标收益约束 wᵀr̂ ≥ µtarget（Eq. p18）。

未来函数红线：CVaR/GMV/HRP 的历史场景/协方差与 DLinear 输入窗口均只用决策日 ≤T 的数据
（调用方 backtest 层保证点时切片）；DLinear 阶段一在 train 区间训练、test 封存。

CVaR 传统基线不在 common 重复实现回测引擎——它是**新的权重模型**（common 无 cvar_weights），
组合回测仍复用 common.portfolio_backtest。求解用 scipy.optimize.linprog（HiGHS），无 cvxpy 依赖。

超参一律引用 config.SITConfig（cvar_alpha/cvar_scenario_window/dlinear_* 等），无魔法数字。
"""

from __future__ import annotations

import copy
import warnings
from typing import Callable, Optional

import numpy as np
import pandas as pd
import torch
from torch import nn
from scipy.optimize import linprog

from common.allocation_backtest import (
    equal_weights,
    hrp_weights,
    mean_variance_weights,
)

from .config import DEFAULT_CONFIG, SITConfig


# =====================================================================
# B5 · 传统基线权重（EW/GMV/HRP 复用 common；CVaR 新增 RU-LP）
# =====================================================================

def ew_weights(assets: list[str]) -> pd.Series:
    """等权 EWP（B5）——复用 common.equal_weights。"""
    return equal_weights(assets)


def gmv_weights(cov: pd.DataFrame) -> pd.Series:
    """全局最小方差 GMV（B5）——复用 common.mean_variance_weights，期望收益取 0（长仓满仓）。

    GMV = 长仓最小方差 = ``max wᵀ0 − λ·wᵀΣw`` = min wᵀΣw（λ>0 任意，取 1.0 良性缩放）。
    改走 common 公开 API mean_variance_weights(μ=0)：plan m4 原列 _min_variance_weights，但其
    负权时回退的 SLSQP 用 λ=1e6 数值病态，>40 资产满秩协方差下不收敛、逐位退化为等权（隔离验证
    max=min=1/n）；mean_variance_weights(μ=0,λ=1) 同一最小方差目标、良性缩放，产真 GMV（AS25）。
    """
    return mean_variance_weights(pd.Series(0.0, index=cov.index), cov, risk_aversion=1.0)


def hrp_baseline_weights(cov: pd.DataFrame) -> pd.Series:
    """层次风险平价 HRP（B5）——复用 common.hrp_weights。"""
    return hrp_weights(cov)


def _cvar_fallback_ew(d: int, reason: str, context: str, log_fn: Optional[Callable[[str], None]]) -> np.ndarray:
    """min-CVaR LP 失败/退化时的**显式**等权回退（CDX-C-04：不得静默把基线伪装成 EW）。

    记录退化原因 + 日期/universe 上下文（context），经 ``warnings.warn`` 上抛（正式运行可见），
    并回调 log_fn（若提供）写入 run_log；返回等权并明确标注为 fallback（非正常求解结果）。
    """
    msg = (f"[min_cvar_weights] LP 退化→等权 FALLBACK（非静默）| reason={reason} | {context}")
    warnings.warn(msg, RuntimeWarning, stacklevel=2)
    if log_fn is not None:
        log_fn(msg)
    return np.ones(d) / d


def min_cvar_weights(
    scenarios: np.ndarray,
    alpha: float,
    exp_ret: Optional[np.ndarray] = None,
    mu_target: Optional[float] = None,
    *,
    context: str = "",
    log_fn: Optional[Callable[[str], None]] = None,
) -> np.ndarray:
    """最小 CVaR 组合（Rockafellar-Uryasev 线性规划；B5 传统 CVaR / B7 两阶段第二阶段）。

    求解（w∈单纯形，ζ=VaR 辅助变量，u=尾部松弛）::

        min_{w,ζ,u}  ζ + 1/((1−α)S)·Σ_s u_s
        s.t.  u_s ≥ −wᵀr_s − ζ,  u_s ≥ 0,  Σw=1,  w≥0
              [两阶段附加] wᵀr̂ ≥ µtarget

    这是标准 CVaR 组合优化的 LP 形式（loss_s=−wᵀr_s，CVaR=ζ+尾部均值超额）。传 exp_ret
    与 mu_target 时加目标收益约束，退化为 B7 两阶段第二阶段；不传则为纯 min-CVaR（B5 CVaR）。

    Args:
        scenarios: (S, d) 历史场景收益（每行一期、列=资产；调用方保证 ≤T 点时）。
        alpha: CVaR 置信水平 α（F7/AS1，全 CVaR 类方法统一 0.80）。
        exp_ret: (d,) 预测预期收益 r̂（两阶段用；None=纯 min-CVaR）。
        mu_target: 目标收益下界 µtarget（两阶段用；None=不加约束）。
        context: 调用上下文（日期/universe/基线名），失败日志用（CDX-C-04）。
        log_fn: 可选日志回调；LP 失败/退化时记录，正式运行不静默回退（CDX-C-04）。

    Returns:
        (d,) 权重（非负、和为 1）；LP 失败/退化经 ``_cvar_fallback_ew`` **显式告警**后回退等权。
    """
    R = np.asarray(scenarios, dtype=float)
    if R.ndim != 2 or R.shape[0] == 0 or R.shape[1] == 0:
        d = R.shape[1] if R.ndim == 2 and R.shape[1] > 0 else 1
        return _cvar_fallback_ew(d, "场景矩阵为空/维度非法", context, log_fn)
    R = np.where(np.isfinite(R), R, 0.0)
    s_num, d = R.shape
    n_var = d + 1 + s_num                                        # x = [w(d), ζ(1), u(S)]

    c = np.zeros(n_var)
    c[d] = 1.0                                                   # ζ
    c[d + 1:] = 1.0 / ((1.0 - alpha) * s_num)                    # u 系数 1/((1−α)S)

    # u_s ≥ −wᵀr_s − ζ  ⇔  −r_sᵀw − ζ − u_s ≤ 0
    a_cvar = np.zeros((s_num, n_var))
    a_cvar[:, :d] = -R
    a_cvar[:, d] = -1.0
    a_cvar[np.arange(s_num), d + 1 + np.arange(s_num)] = -1.0
    ub_rows = [a_cvar]
    ub_b = [np.zeros(s_num)]

    if exp_ret is not None and mu_target is not None:           # 两阶段目标收益：wᵀr̂ ≥ µtarget ⇔ −r̂ᵀw ≤ −µtarget
        r_hat = np.where(np.isfinite(np.asarray(exp_ret, dtype=float)), np.asarray(exp_ret, dtype=float), 0.0)
        con = np.zeros((1, n_var))
        con[0, :d] = -r_hat
        ub_rows.append(con)
        ub_b.append(np.array([-float(mu_target)]))

    a_ub = np.vstack(ub_rows)
    b_ub = np.concatenate(ub_b)
    a_eq = np.zeros((1, n_var))
    a_eq[0, :d] = 1.0                                           # Σw=1
    b_eq = np.array([1.0])
    bounds = [(0.0, 1.0)] * d + [(None, None)] + [(0.0, None)] * s_num

    try:
        res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    except (ValueError, np.linalg.LinAlgError) as e:            # 求解器异常（CDX-C-04：记录+显式 fallback，不静默）
        return _cvar_fallback_ew(d, f"linprog 抛错 {type(e).__name__}: {e}", context, log_fn)
    if not res.success or res.x is None:                        # 求解未成功（CDX-C-04）
        status = getattr(res, "status", None)
        message = getattr(res, "message", "")
        return _cvar_fallback_ew(
            d, f"res.success={res.success} status={status} msg={message}", context, log_fn
        )
    w = np.clip(np.asarray(res.x[:d], dtype=float), 0.0, None)
    total = w.sum()
    if total > 0:
        return w / total
    return _cvar_fallback_ew(d, "解权重和≤0（数值退化）", context, log_fn)


# =====================================================================
# B7 · 两阶段第一阶段：DLinear 预测器（序列分解线性，Zeng 2023；AS15）
# =====================================================================

class _MovingAvg(nn.Module):
    """移动平均趋势提取（DLinear 序列分解）；两端 padding 保持长度。"""

    def __init__(self, kernel: int) -> None:
        super().__init__()
        self.kernel = kernel
        self.pool = nn.AvgPool1d(kernel_size=kernel, stride=1, padding=0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """(B, L) → (B, L) 趋势分量（边界重复填充）。"""
        left = (self.kernel - 1) // 2
        right = self.kernel - 1 - left
        front = x[:, :1].repeat(1, left)
        back = x[:, -1:].repeat(1, right)
        xp = torch.cat([front, x, back], dim=1).unsqueeze(1)     # (B,1,L+kernel-1)
        return self.pool(xp).squeeze(1)                          # (B,L)


class DLinear(nn.Module):
    """DLinear 预测器（B7 阶段一 PFL 代表；通道独立，趋势/季节两分支各一线性层，AS15）。

    输入 = 逐资产 H 长回看序列（日频收益，通道独立共享权重），输出 = K 步预测收益。
    """

    def __init__(self, in_len: int, out_len: int, kernel: int) -> None:
        super().__init__()
        self.decomp = _MovingAvg(kernel)
        self.linear_trend = nn.Linear(in_len, out_len)
        self.linear_season = nn.Linear(in_len, out_len)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """(B, H) → (B, K)（趋势+季节两分支线性相加）。"""
        trend = self.decomp(x)
        season = x - trend
        return self.linear_trend(trend) + self.linear_season(season)


def _flatten_channels(hist: np.ndarray) -> torch.Tensor:
    """(N, d, H) → (N·d, H) 通道独立铺平（DLinear 逐资产共享权重）。"""
    arr = np.asarray(hist, dtype=float)
    n, d, h = arr.shape
    return torch.as_tensor(arr.reshape(n * d, h), dtype=torch.float32)


def train_dlinear(
    hist_train: np.ndarray,
    y_train: np.ndarray,
    hist_val: np.ndarray,
    y_val: np.ndarray,
    config: SITConfig = DEFAULT_CONFIG,
    *,
    seed: int = 0,
    log_fn=None,
) -> DLinear:
    """B7 阶段一：DLinear 以 MSE 训练预测 K 步收益（仅追求预测精度，非决策目标，F8 对照）。

    Args:
        hist_train/hist_val: (N, d, H) 逐资产日频回看序列（决策日 ≤T 窗口）。
        y_train/y_val: (N, K, d) K 步实现收益标签。
        config: dlinear_kernel/dlinear_lr/dlinear_max_epoch/dlinear_patience。

    Returns:
        best-val 的 DLinear（已回载）。
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    _, d, h = np.asarray(hist_train).shape
    k = np.asarray(y_train).shape[1]

    model = DLinear(in_len=h, out_len=k, kernel=config.dlinear_kernel)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.dlinear_lr)
    loss_fn = nn.MSELoss()

    x_tr = _flatten_channels(hist_train)                        # (N·d, H)
    x_va = _flatten_channels(hist_val)
    # 标签 (N,K,d) → 逐资产 (N·d, K)：先 (N,d,K) 再铺平
    y_tr = torch.as_tensor(np.asarray(y_train).transpose(0, 2, 1).reshape(-1, k), dtype=torch.float32)
    y_va = torch.as_tensor(np.asarray(y_val).transpose(0, 2, 1).reshape(-1, k), dtype=torch.float32)

    n = x_tr.shape[0]
    bs = config.batch_size
    gen = torch.Generator().manual_seed(seed)
    best_val = float("inf")
    best_state = copy.deepcopy(model.state_dict())
    no_improve = 0
    for epoch in range(config.dlinear_max_epoch):
        model.train()
        perm = torch.randperm(n, generator=gen)
        for s in range(0, n, bs):
            idx = perm[s:s + bs]
            pred = model(x_tr[idx])
            loss = loss_fn(pred, y_tr[idx])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val_loss = float(loss_fn(model(x_va), y_va))
        if val_loss < best_val - 1e-9:
            best_val, no_improve = val_loss, 0
            best_state = copy.deepcopy(model.state_dict())
        else:
            no_improve += 1
            if no_improve >= config.dlinear_patience:
                break
    if log_fn is not None:
        log_fn(f"[dlinear] best_val_mse={best_val:.6e}")
    model.load_state_dict(best_state)
    return model


@torch.no_grad()
def dlinear_predict(model: DLinear, hist: np.ndarray) -> np.ndarray:
    """DLinear 预测 (M, d, H) → (M, K, d) K 步预测收益。"""
    model.eval()
    arr = np.asarray(hist, dtype=float)
    m, d, h = arr.shape
    pred = model(_flatten_channels(arr)).cpu().numpy()          # (M·d, K)
    k = pred.shape[1]
    return pred.reshape(m, d, k).transpose(0, 2, 1)             # (M, K, d)
