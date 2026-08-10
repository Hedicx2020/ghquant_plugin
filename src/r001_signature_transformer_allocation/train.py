"""r001 · SIT 端到端 CVaR 训练（milestone m4：F7 目标 + F8 范式 + B1 训练循环）。

职责（严格对 spec，页码/Eq 引用制，对应 coverage_matrix milestone=m4 的 F7/F8/B1）：
- F7 (p2,p4-p5 Eq.17-20) CVaR 训练目标：逐场景 i 对 K 步组合损失序列
  ``L_i^(k) = −(w_i^(k))ᵀ r_{i,t+k}``（k=1..K）取经验 α-分位 ν_i（VaR_α），组合 CVaR
  经验式 ``CVaR_i = ν_i + [1/((1−α)K)]·Σ_k (L_i^(k) − ν_i)_+``，再对 N 场景取均值
  作训练损失（α=0.80、K=12，(1−α)K=2.4 非退化，AS1/AS2）。
- F8 (p4,p11) 端到端范式：µ̂ 仅作 allocation 层 logits，**无辅助预测损失**——梯度只从
  CVaR 目标经 w（softmax(µ̂/τ)）回流，本模块只对 SIT 输出的权重 w 计 CVaR，绝不对 µ̂
  施加 MSE/预测监督。
- B1 (p16) 训练：Adam(lr=1e-3)、mini-batch(64)、dropout(0.1，含于模型)、max_epoch=100、
  early stopping patience=10；验证集选优（best val CVaR 存档回载）。缩减档少 epoch 保冒烟。

未来函数红线（code_audit/codex 核查）：
- 训练/验证损失只用各自区间的场景（决策日 ∈ splits[train]/splits[val]），test 封存不参与
  选优（选优在 main 装配层保证）；
- 场景标签 r_{i,t+k} 为决策日之后的 K 步实现收益（m2 realized_forward_returns，标签/未来
  数据），仅进损失、绝不回流为模型输入特征（m2 已隔离）；
- ν_i 为逐场景 K 个损失的经验 α-分位（点内统计，非跨场景/跨时间泄漏）。

依赖 torch（m4 专属）。超参一律引用 config.SITConfig，函数体内不出现魔法数字。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import torch

from .config import DEFAULT_CONFIG, SITConfig
from .model import SIT, build_sit

FeatDict = dict  # {"asset_signatures":(N,H,d,d_sig), "cross_signatures":(N,d,d,2), "calendar":(N,H,F)}


# =====================================================================
# F7 · CVaR 组合损失（经验式 Eq.20，逐场景 α-分位 + 尾部超额）
# =====================================================================

def cvar_from_losses(
    losses: torch.Tensor, alpha: float, detach_nu: bool = True
) -> torch.Tensor:
    """逐场景 CVaR_α（Rockafellar-Uryasev 经验式，Eq.20）。

    Args:
        losses: (N, K) 每场景 K 步组合损失 L_i^(k)=−(w^(k))ᵀr^(k)。
        alpha: 置信水平 α（尾部质量 1−α；F7/AS1）。
        detach_nu: ν_i 取经验 α-分位（VaR_α）并 detach——包络定理下 ∂CVaR/∂ν=0，
            梯度只经尾部超额项 (L−ν)_+ 回流（避免分位插值梯度噪声，AS24）。

    Returns:
        (N,) 每场景 CVaR_α = ν_i + [1/((1−α)K)]·Σ_k (L_i^(k) − ν_i)_+。
    """
    if losses.ndim != 2:
        raise ValueError(f"losses 须为 (N, K)，实际 {tuple(losses.shape)}")
    k_steps = losses.shape[1]
    tail_scale = 1.0 / ((1.0 - alpha) * k_steps)                 # 1/((1−α)K)（F7 尾部归一）
    ref = losses.detach() if detach_nu else losses
    nu = torch.quantile(ref, alpha, dim=1, keepdim=True)        # (N,1) 经验 α-分位 VaR_α
    excess = torch.clamp(losses - nu, min=0.0)                  # (L−ν)_+，超 VaR 尾部
    return nu.squeeze(1) + tail_scale * excess.sum(dim=1)       # (N,) CVaR_α


def cvar_portfolio_loss(
    weights: torch.Tensor,
    realized_returns: torch.Tensor,
    alpha: float,
    detach_nu: bool = True,
) -> torch.Tensor:
    """F7 端到端 CVaR 训练损失：对 N 场景的 CVaR_α 取均值（Eq.17 E[CVaR]）。

    Args:
        weights: (N, K, d) SIT 各步组合权重 w^(1:K)（softmax(µ̂/τ)，long-only）。
        realized_returns: (N, K, d) K 步实现收益标签 r_{t+k}（m2 标签，未来数据）。
        alpha: 置信水平 α（F7/AS1）。
        detach_nu: 见 :func:`cvar_from_losses`。

    Returns:
        标量损失 E_i[CVaR_α]（F8：唯一训练信号，梯度只经 w，不碰 µ̂ 预测监督）。
    """
    if weights.shape != realized_returns.shape:
        raise ValueError(
            f"weights {tuple(weights.shape)} 与 realized_returns "
            f"{tuple(realized_returns.shape)} 形状不一致（须 (N,K,d)）"
        )
    step_return = (weights * realized_returns).sum(dim=-1)      # (N,K) 各步组合收益 (w^k)ᵀr^k
    losses = -step_return                                       # (N,K) L^(k)=−(w^k)ᵀr^k（F7）
    return cvar_from_losses(losses, alpha, detach_nu=detach_nu).mean()


def portfolio_loss(
    weights: torch.Tensor,
    realized_returns: torch.Tensor,
    alpha: float,
    *,
    objective: str = "cvar",
    detach_nu: bool = True,
) -> torch.Tensor:
    """训练损失分派（m5 SA1 模块消融）：

    - objective="cvar"（默认）：F7 端到端 CVaR 目标（现行为，见 :func:`cvar_portfolio_loss`）；
    - objective="mean"：SA1「w/o CVaR」——换风险中性最大化均值收益，损失 = E[−(w^k)ᵀr^k]
      （对 N 场景 × K 步组合收益取均值的相反数；spec SA1「换为风险中性最大化均值收益」，p6）。

    仅 objective 分派、不改 CVaR 路径，向后兼容（默认与原 cvar_portfolio_loss 逐位一致）。
    """
    if objective == "cvar":
        return cvar_portfolio_loss(weights, realized_returns, alpha, detach_nu=detach_nu)
    if objective == "mean":
        step_return = (weights * realized_returns).sum(dim=-1)  # (N,K) (w^k)ᵀr^k
        return (-step_return).mean()                            # 最大化均值收益（风险中性）
    raise ValueError(f"未知 objective={objective!r}（'cvar'|'mean'）")


# =====================================================================
# 训练结果容器
# =====================================================================

@dataclass
class TrainResult:
    """单次训练（单种子/单配置）结果（供 main 装配选优 / 多种子聚合）。"""

    model: SIT
    seed: int
    best_val: float
    best_epoch: int
    history: list = field(default_factory=list)     # 逐 epoch (train_cvar, val_cvar)


# =====================================================================
# 张量准备 / 验证集评估
# =====================================================================

def _to_tensors(feat: FeatDict, device: torch.device) -> dict[str, torch.Tensor]:
    """m2 numpy 特征字典 → torch 张量（只取模型前向三键，忽略 signed_area/codes 等）。"""
    keys = ("asset_signatures", "cross_signatures", "calendar")
    return {k: torch.as_tensor(np.asarray(feat[k]), dtype=torch.float32, device=device) for k in keys}


def _forward_batch(model: SIT, tensors: dict[str, torch.Tensor],
                   idx: torch.Tensor, tau: Optional[float]) -> torch.Tensor:
    """按索引取 mini-batch 前向 → w (B,K,d)。"""
    return model(
        tensors["asset_signatures"][idx],
        tensors["cross_signatures"][idx],
        tensors["calendar"][idx],
        tau=tau,
    )


@torch.no_grad()
def evaluate_cvar(
    model: SIT,
    tensors: dict[str, torch.Tensor],
    labels: torch.Tensor,
    config: SITConfig,
    tau: Optional[float] = None,
    batch_size: Optional[int] = None,
    objective: str = "cvar",
) -> float:
    """在给定场景集上算平均损失（验证/早停用，不回流梯度）。

    objective="cvar"（默认，F7）或 "mean"（SA1 w/o CVaR）；早停指标须与训练目标一致（m5）。
    """
    model.eval()
    n = labels.shape[0]
    bs = batch_size or config.batch_size
    total, count = 0.0, 0
    all_idx = torch.arange(n, device=labels.device)
    for s in range(0, n, bs):
        idx = all_idx[s:s + bs]
        w = _forward_batch(model, tensors, idx, tau)
        loss = portfolio_loss(w, labels[idx], config.cvar_alpha,
                              objective=objective, detach_nu=config.cvar_detach_nu)
        total += float(loss) * len(idx)
        count += len(idx)
    return total / max(count, 1)


# =====================================================================
# B1 · 训练循环（Adam + mini-batch + early stopping + val 选优）
# =====================================================================

def train_sit(
    train_feat: FeatDict,
    train_labels: np.ndarray,
    val_feat: FeatDict,
    val_labels: np.ndarray,
    n_assets: int,
    config: SITConfig = DEFAULT_CONFIG,
    *,
    seed: int = 0,
    tau: Optional[float] = None,
    max_epoch: Optional[int] = None,
    patience: Optional[int] = None,
    log_fn: Optional[Callable[[str], None]] = None,
    device: Optional[torch.device] = None,
    objective: str = "cvar",
    ablation: Optional[str] = None,
) -> TrainResult:
    """端到端训练 SIT（F7 CVaR 目标 / F8 无预测损失 / B1 Adam+早停）。

    m5 SA1 消融（默认 objective="cvar"/ablation=None 完全等价现行为，向后兼容）：
      - objective="mean"：w/o CVaR，换风险中性最大化均值收益（见 :func:`portfolio_loss`）；
      - ablation∈{"no_asset_attn","no_financial_bias","no_gate"}：结构消融，训练前经
        model.set_ablation 在全部 SITBlock 生效（w/o CVaR 用 ablation=None 保 full 结构）。

    Args:
        train_feat/val_feat: m2 特征字典（asset_signatures/cross_signatures/calendar）。
        train_labels/val_labels: (N,K,d) K 步实现收益标签。
        n_assets: 资产数 d（=universe 大小，e_asset 定维）。
        config: 全局配置（adam_lr/batch_size/max_epoch/early_stop_patience/cvar_alpha 等）。
        seed: 随机种子（AS5 多种子在 main 层循环调用本函数）。
        tau: softmax 温度覆盖（默认 config.sit_tau；τ 选优在 main 层）。
        max_epoch/patience: 覆盖 config（缩减档冒烟传小值）。
        log_fn: 日志回调（如 print）。

    Returns:
        TrainResult（best-val 权重已回载）。
    """
    device = device or torch.device("cpu")
    max_epoch = int(max_epoch if max_epoch is not None else config.max_epoch)
    patience = int(patience if patience is not None else config.early_stop_patience)

    torch.manual_seed(seed)
    np.random.seed(seed)

    model = build_sit(n_assets, config).to(device)
    model.set_ablation(ablation)                                          # SA1 结构消融（默认 None=full，m5）
    optimizer = torch.optim.Adam(model.parameters(), lr=config.adam_lr)   # B1 Adam lr=1e-3

    tr = _to_tensors(train_feat, device)
    va = _to_tensors(val_feat, device)
    y_tr = torch.as_tensor(np.asarray(train_labels), dtype=torch.float32, device=device)
    y_va = torch.as_tensor(np.asarray(val_labels), dtype=torch.float32, device=device)

    n_train = y_tr.shape[0]
    bs = config.batch_size
    gen = torch.Generator(device="cpu").manual_seed(seed)

    best_val = float("inf")
    best_state = copy.deepcopy(model.state_dict())
    best_epoch = -1
    no_improve = 0
    history: list = []

    for epoch in range(max_epoch):
        model.train()
        perm = torch.randperm(n_train, generator=gen).to(device)
        epoch_loss = 0.0
        for s in range(0, n_train, bs):
            idx = perm[s:s + bs]
            w = _forward_batch(model, tr, idx, tau)
            loss = portfolio_loss(w, y_tr[idx], config.cvar_alpha,
                                 objective=objective, detach_nu=config.cvar_detach_nu)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.detach()) * len(idx)
        train_cvar = epoch_loss / max(n_train, 1)
        val_cvar = evaluate_cvar(model, va, y_va, config, tau=tau, objective=objective)
        history.append((train_cvar, val_cvar))
        if log_fn is not None:
            log_fn(f"  epoch {epoch:03d}  train_cvar={train_cvar:.6f}  val_cvar={val_cvar:.6f}")

        if val_cvar < best_val - 1e-7:                          # val 选优（best-val 存档）
            best_val, best_epoch, no_improve = val_cvar, epoch, 0
            best_state = copy.deepcopy(model.state_dict())
        else:
            no_improve += 1
            if no_improve >= patience:                         # early stopping（B1 patience）
                if log_fn is not None:
                    log_fn(f"  early stop @ epoch {epoch}（best_epoch={best_epoch} best_val={best_val:.6f}）")
                break

    model.load_state_dict(best_state)                          # 回载 best-val 权重
    return TrainResult(model=model, seed=seed, best_val=best_val, best_epoch=best_epoch, history=history)


def train_multi_seed(
    train_feat: FeatDict,
    train_labels: np.ndarray,
    val_feat: FeatDict,
    val_labels: np.ndarray,
    n_assets: int,
    config: SITConfig = DEFAULT_CONFIG,
    *,
    seeds: Optional[tuple] = None,
    tau: Optional[float] = None,
    max_epoch: Optional[int] = None,
    patience: Optional[int] = None,
    log_fn: Optional[Callable[[str], None]] = None,
) -> list[TrainResult]:
    """多种子训练（AS5：报告 mean±std）；返回各种子 TrainResult。"""
    seeds = seeds if seeds is not None else config.seeds
    results: list[TrainResult] = []
    for sd in seeds:
        if log_fn is not None:
            log_fn(f"[train] seed={sd}")
        results.append(train_sit(
            train_feat, train_labels, val_feat, val_labels, n_assets, config,
            seed=sd, tau=tau, max_epoch=max_epoch, patience=patience, log_fn=log_fn,
        ))
    return results
