"""r001 · Signature-Informed Transformer (SIT) 网络架构与前向（milestone m3）。

职责（严格对 spec，页码/Eq 引用制，逐条对应 coverage_matrix milestone=m3 的 F3/F4/F5/F6）：
- F3 (p3, Eq.4) 签名嵌入 token：x_{k,j}=W_proj[e_sig,k,j ⊕ e_date,k ⊕ e_asset^j]∈R^d_model，
  三源融合——签名线性投影 e_sig + 日历嵌入 e_date（切片共享）+ 可学习资产 embedding
  e_asset^j，拼接后线性投影 W_proj；输入张量形状 H×d×d_model（本实现批量维 B×H×d×d_model）。
- F4 (p3) 时间维因果自注意力：每个 factorized 层内先沿时间维 H 做标准 causal self-attention
  （掩未来切片，N_H 头），资产维注意力把时间维当 batch 维。
- F5 (p3-p4, Eq.8-16) 签名增强资产维自注意力（核心创新）：
  Head_{k,h}=softmax(Q_{k,h}K_{k,h}^T/√d_k + γ·B_{k,h})V_{k,h}；
  偏置 b_{k,h,j,l}=⟨(q_dyn_{k,j})_h,(β_{i,j,l})_h⟩（Eq.10）；
  关系嵌入 β_{i,j,l}=MLP_β(c_{i,j,l})∈R^{N_H×d_β}（Eq.8，逐头分离，c=交叉签名）；
  动态查询 q_dyn_{k,j}=MLP_q(x'_{k,j})∈R^{N_H×d_β}（Eq.9）；
  gate γ=softplus(γ̂)>0 可学习标量（p4）；头拼接后 W_O + 残差 + LayerNorm（Eq.15-16）。
- F6 (p2,p4) 多步输出头 + softmax 分配层：last-slice（AS6）经线性头产 µ̂^{1:K}∈R^{K×d}
  （K=12 步，AS2），每步 w^{(k)}=softmax(µ̂^{(k)}/τ) 天然 long-only（非负）+ fully-invested
  （和=1）；µ̂ 仅作 allocation 层 logits、无预测损失（F8，训练在 m4）。

点时红线（code_audit/codex 逐点核查）：
- 时间维注意力**因果掩码**：切片 k 只注意 k'≤k，绝不看未来切片（causal self-attention，F4）；
- 资产维注意力把时间当 batch，逐切片独立，不跨时间混合；
- 交叉签名 c 为决策时刻 F_ti 的一部分（m2 保证只用 [t−H,t] 窗口，点时安全），全窗口共享，
  在因果意义上不构成「未来切片泄漏」（因果性针对时间 token 顺序，点时安全由 m2 保证）。

依赖 torch（m3/m4 专属；signatures.py/data.py 保持纯 numpy 可测）。所有超参引用
`config.SITConfig` 派生量或字段，函数体内不出现魔法数字（AS7/AS14/AS6/AS23）。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import DEFAULT_CONFIG, SITConfig


# =====================================================================
# F3 · 签名嵌入输入 token（三嵌入融合，Eq.4）
# =====================================================================

class SignatureEmbedding(nn.Module):
    """F3 (Eq.4) 三源嵌入融合 → 输入 token x_{k,j}∈R^d_model。

    三源（⊕ 表拼接）：
      - e_sig,k,j = W_sig·s_{k,j}（签名线性投影，s=逐资产 M=2 截断签名，维 d_sig）；
      - e_date,k = W_date·v_k（日历嵌入，切片 k 共享、跨资产广播）；
      - e_asset^j = Embedding[j]（可学习资产嵌入，逐资产身份，跨 train/val/test 固定）。
    各源投影至 d_model 后拼接（3·d_model）再经 W_proj→d_model（AS23：子维取 d_model 忠于
    Eq.4「拼接后线性投影」，位置信息由 e_date + 时间增广签名提供，不另加位置编码）。
    """

    def __init__(self, d_sig: int, calendar_dim: int, n_assets: int, d_model: int) -> None:
        super().__init__()
        self.n_assets = n_assets
        self.sig_proj = nn.Linear(d_sig, d_model)          # e_sig：签名线性投影
        self.date_proj = nn.Linear(calendar_dim, d_model)  # e_date：日历嵌入
        self.asset_emb = nn.Embedding(n_assets, d_model)   # e_asset^j：可学习资产嵌入
        self.w_proj = nn.Linear(3 * d_model, d_model)      # W_proj：拼接后线性投影（Eq.4）

    def forward(self, asset_sig: torch.Tensor, calendar: torch.Tensor) -> torch.Tensor:
        """(B,H,d,d_sig) + (B,H,F) → 输入 token (B,H,d,d_model)。"""
        b, h, d, _ = asset_sig.shape
        if d != self.n_assets:
            raise ValueError(f"资产数 d={d} 与模型 n_assets={self.n_assets} 不一致（e_asset 定维）")
        e_sig = self.sig_proj(asset_sig)                             # (B,H,d,M)
        e_date = self.date_proj(calendar).unsqueeze(2).expand(b, h, d, -1)  # 切片共享 → (B,H,d,M)
        idx = torch.arange(d, device=asset_sig.device)
        e_asset = self.asset_emb(idx).view(1, 1, d, -1).expand(b, h, d, -1)  # 逐资产 → (B,H,d,M)
        fused = torch.cat([e_sig, e_date, e_asset], dim=-1)         # ⊕ → (B,H,d,3M)
        return self.w_proj(fused)                                   # W_proj → (B,H,d,M)


# =====================================================================
# F4 · 时间维因果自注意力（standard causal self-attention）
# =====================================================================

class TemporalCausalAttention(nn.Module):
    """F4 时间维标准因果多头自注意力（掩未来切片；资产维当 batch 维处理）。

    输入泛化为 (N, L, d_model)：N=batch（此处 B×d，资产作 batch），L=时间切片 H。
    因果掩码：位置 k 只注意 k'≤k（下三角），softmax 前将未来位 logits 置 −inf，
    保证 token k 的输出不含 k>k 的任何信息（点时红线，test_model 断言）。
    """

    def __init__(self, d_model: int, n_heads: int, dropout: float) -> None:
        super().__init__()
        if d_model % n_heads != 0:
            raise ValueError(f"d_model={d_model} 不能被 n_heads={n_heads} 整除")
        self.n_heads = n_heads
        self.d_k = d_model // n_heads
        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.w_o = nn.Linear(d_model, d_model)
        self.attn_drop = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """(N, L, d_model) → (N, L, d_model)，沿 L 做因果自注意力。"""
        n, length, _ = x.shape
        qkv = self.qkv(x).view(n, length, 3, self.n_heads, self.d_k)
        q, k, v = qkv.unbind(dim=2)                                 # each (N,L,H_head,d_k)
        q = q.transpose(1, 2)                                       # (N,head,L,d_k)
        k = k.transpose(1, 2)
        v = v.transpose(1, 2)
        logits = torch.matmul(q, k.transpose(-2, -1)) / (self.d_k ** 0.5)  # (N,head,L,L)
        # 因果掩码：未来位（列 > 行）置 −inf，softmax 后权重为 0（掩未来切片）
        causal = torch.triu(
            torch.ones(length, length, dtype=torch.bool, device=x.device), diagonal=1
        )
        logits = logits.masked_fill(causal, float("-inf"))
        attn = self.attn_drop(torch.softmax(logits, dim=-1))       # (N,head,L,L)
        out = torch.matmul(attn, v)                                # (N,head,L,d_k)
        out = out.transpose(1, 2).reshape(n, length, -1)           # (N,L,d_model)
        return self.w_o(out)


# =====================================================================
# F5 · 签名增强资产维自注意力（核心创新，含 β/q_dyn/gate γ）
# =====================================================================

def _mlp2(in_dim: int, hidden: int, out_dim: int) -> nn.Sequential:
    """AS7：2 层 MLP（Linear→GELU→Linear），供 MLP_β / MLP_q。"""
    return nn.Sequential(nn.Linear(in_dim, hidden), nn.GELU(), nn.Linear(hidden, out_dim))


class SignatureAssetAttention(nn.Module):
    """F5 (Eq.8-16) 签名增强资产维自注意力：Head=softmax(QK^T/√d_k + γ·B)V。

    偏置 B 由签名诱导（Eq.8-10）：
      - β_{i,j,l}=MLP_β(c_{i,j,l})∈R^{N_H×d_β}（Eq.8，交叉签名 c→逐头关系嵌入）；
      - q_dyn_{k,j}=MLP_q(x'_{k,j})∈R^{N_H×d_β}（Eq.9，token→逐头动态查询）；
      - b_{k,h,j,l}=⟨(q_dyn_{k,j})_h,(β_{i,j,l})_h⟩（Eq.10，逐头 d_β 维内积）；
      - γ=softplus(γ̂)>0 可学习标量 gate（p4），控签名偏置整体幅度。
    头拼接后 W_O + 残差 + LayerNorm（Eq.15-16，残差/LN 在 SITBlock 外层加）。

    时间维当 batch：对 (B,H) 逐切片独立在资产维 d 上注意（不跨时间混合，F4 分工）。
    """

    def __init__(
        self, d_model: int, n_heads: int, d_beta: int, hidden_c: int, dropout: float
    ) -> None:
        super().__init__()
        if d_model % n_heads != 0:
            raise ValueError(f"d_model={d_model} 不能被 n_heads={n_heads} 整除")
        self.n_heads = n_heads
        self.d_k = d_model // n_heads
        self.d_beta = d_beta
        self.q_proj = nn.Linear(d_model, d_model)
        self.k_proj = nn.Linear(d_model, d_model)
        self.v_proj = nn.Linear(d_model, d_model)
        self.w_o = nn.Linear(d_model, d_model)
        self.attn_drop = nn.Dropout(dropout)
        # Eq.9/8：动态查询 / 关系嵌入，各输出 N_H×d_β（逐头分离）
        self.mlp_q = _mlp2(d_model, hidden_c, n_heads * d_beta)
        self.mlp_beta = _mlp2(DEFAULT_CONFIG.cross_signature_dim, hidden_c, n_heads * d_beta)
        # gate γ=softplus(γ̂)>0；γ̂ 初值 0 → γ=softplus(0)=ln2≈0.693（温和非零起点）
        self.gamma_hat = nn.Parameter(torch.zeros(()))
        # ---- SA1 模块消融开关（m5；默认 False/None 不改现行为，由 SIT.set_ablation 配置）----
        self.ablation_disable_bias: bool = False           # w/o Financial Bias：去 γ·B 退回标准注意力
        self.ablation_gamma_fixed: Optional[float] = None  # w/o Gate γ：固定 γ=常数（非可学习）

    @property
    def gamma(self) -> torch.Tensor:
        """可学习正 gate γ=softplus(γ̂)>0（p4；恒正，无论 γ̂ 取值）。

        SA1 w/o Gate γ 消融（m5）：ablation_gamma_fixed 非 None 时返回该固定常数（如 1.0），
        γ 不再可学习（gamma_hat 无梯度，等价固定 gate）。
        """
        if self.ablation_gamma_fixed is not None:
            return torch.as_tensor(
                float(self.ablation_gamma_fixed), dtype=self.gamma_hat.dtype, device=self.gamma_hat.device
            )
        return F.softplus(self.gamma_hat)

    def logit_parts(
        self, x: torch.Tensor, cross: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """返回 (QK^T/√d_k, B 偏置, V)，供 forward 与 γ 敏感性诊断（Theorem 2.2 数值验证）。

        Args:
            x: (B,H,d,d_model) 时间注意力后 token x'。
            cross: (B,d,d,d_cross) 成对交叉签名 c_{i,j,l}（j=query 资产、l=key 资产）。
        Returns:
            qk:   (B,H,N_H,d,d) 缩放点积 Q_j·K_l/√d_k；
            bias: (B,H,N_H,d,d) 签名诱导偏置 b_{k,h,j,l}=⟨q_dyn_j, β_{j,l}⟩；
            v:    (B,H,d,N_H,d_k) 值向量（供加权求和）。
        """
        b, h, d, _ = x.shape
        nh, dk, db = self.n_heads, self.d_k, self.d_beta
        q = self.q_proj(x).view(b, h, d, nh, dk)                   # (B,H,d,N_H,d_k)
        k = self.k_proj(x).view(b, h, d, nh, dk)
        v = self.v_proj(x).view(b, h, d, nh, dk)
        # 标准缩放点积（query j × key l，逐头逐切片）：(B,H,N_H,d,d)
        qk = torch.einsum("bsjnf,bslnf->bsnjl", q, k) / (dk ** 0.5)
        # 签名偏置（Eq.8-10）：q_dyn 逐切片，β 全窗口共享（不随切片变，仅 q_dyn 引入切片依赖）
        q_dyn = self.mlp_q(x).view(b, h, d, nh, db)                # (B,H,d,N_H,d_β)
        beta = self.mlp_beta(cross).view(b, d, d, nh, db)         # (B,d,d,N_H,d_β)
        bias = torch.einsum("bsjne,bjlne->bsnjl", q_dyn, beta)    # (B,H,N_H,d,d)
        return qk, bias, v

    @staticmethod
    def attn_from_parts(
        qk: torch.Tensor, bias: torch.Tensor, gamma: torch.Tensor
    ) -> torch.Tensor:
        """logits=QK^T/√d_k + γ·B → softmax(over key)（Eq.11/14；供任意 γ 的注意力权重）。"""
        return torch.softmax(qk + gamma * bias, dim=-1)

    def forward(
        self, x: torch.Tensor, cross: torch.Tensor, return_attn: bool = False
    ) -> tuple[torch.Tensor, Optional[dict]]:
        """(B,H,d,d_model) + (B,d,d,d_cross) → (B,H,d,d_model)（W_O 后，残差/LN 在外层）。"""
        b, h, d, _ = x.shape
        qk, bias, v = self.logit_parts(x, cross)
        if self.ablation_disable_bias:                             # SA1 w/o Financial Bias：softmax(QK^T/√d_k)
            attn = torch.softmax(qk, dim=-1)                       # 退回标准注意力（无 γ·B）
        else:
            attn = self.attn_from_parts(qk, bias, self.gamma)      # (B,H,N_H,d,d)
        attn = self.attn_drop(attn)
        # 加权求和：Σ_l α_{j,l} V_l（逐头）→ (B,H,d,N_H,d_k) → 拼头 (B,H,d,d_model)
        out = torch.einsum("bsnjl,bslnf->bsjnf", attn, v).reshape(b, h, d, -1)
        out = self.w_o(out)                                        # W_O（Eq.15）
        aux = None
        if return_attn:
            aux = {"attn": attn, "qk": qk, "bias": bias, "gamma": self.gamma.detach()}
        return out, aux


# =====================================================================
# factorized SIT Block（F4 时间因果 → F5 签名资产 → FFN，post-LN 残差；AS23）
# =====================================================================

class SITBlock(nn.Module):
    """单个 factorized 层：时间因果自注意力(F4) → 签名资产注意力(F5) → FFN，三子层均
    post-LN 残差（Eq.15-16「W_O + 残差 + LayerNorm」；FFN 为 Transformer 标配，AS23）。"""

    def __init__(
        self, d_model: int, d_ff: int, n_heads: int, d_beta: int, hidden_c: int, dropout: float
    ) -> None:
        super().__init__()
        self.temporal_attn = TemporalCausalAttention(d_model, n_heads, dropout)
        self.asset_attn = SignatureAssetAttention(d_model, n_heads, d_beta, hidden_c, dropout)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, d_ff), nn.GELU(), nn.Dropout(dropout), nn.Linear(d_ff, d_model)
        )
        self.ln_temporal = nn.LayerNorm(d_model)
        self.ln_asset = nn.LayerNorm(d_model)
        self.ln_ffn = nn.LayerNorm(d_model)
        self.drop = nn.Dropout(dropout)
        # SA1 w/o Asset Attn 消融（m5）：True 时整个 F5 签名资产注意力子层跳过（默认 False 不改现行为）
        self.ablation_disable_asset_attn: bool = False

    def forward(
        self, x: torch.Tensor, cross: torch.Tensor, return_attn: bool = False
    ) -> tuple[torch.Tensor, Optional[dict]]:
        """(B,H,d,d_model) → (B,H,d,d_model)。"""
        b, h, d, m = x.shape
        # --- F4 时间因果注意力（资产维当 batch：(B,d,H,M)→(B·d,H,M)）---
        xt = x.permute(0, 2, 1, 3).reshape(b * d, h, m)
        xt = self.temporal_attn(xt).reshape(b, d, h, m).permute(0, 2, 1, 3)  # (B,H,d,M)
        x = self.ln_temporal(x + self.drop(xt))                    # 残差 + LN
        # --- F5 签名资产注意力（时间维当 batch）---
        if self.ablation_disable_asset_attn:                       # SA1 w/o Asset Attn：整层跳过（保留时间注意力+FFN）
            aux = None
        else:
            xa, aux = self.asset_attn(x, cross, return_attn=return_attn)
            x = self.ln_asset(x + self.drop(xa))                   # 残差 + LN（Eq.16）
        # --- FFN ---
        x = self.ln_ffn(x + self.drop(self.ffn(x)))                # 残差 + LN
        return x, aux


# =====================================================================
# F6 · 多步输出头 + softmax 分配层（last-slice、K 步、τ、long-only、fully-invested）
# =====================================================================

class AllocationHead(nn.Module):
    """F6 多步输出头：last-slice(AS6) → 线性投影产 µ̂^{1:K}∈R^{K×d} → w=softmax(µ̂/τ)。

    每步 w^{(k)}=softmax(µ̂^{(k)}/τ) 在资产维 d 上归一，天然 long-only（非负）+
    fully-invested（Σ_j w_j=1）；µ̂ 仅作 logits，无预测损失（F8，训练在 m4）。
    """

    def __init__(self, d_model: int, n_steps_k: int, tau: float) -> None:
        super().__init__()
        self.n_steps_k = n_steps_k
        self.default_tau = tau
        self.proj = nn.Linear(d_model, n_steps_k)                  # 每资产 d_model → K 步 µ̂

    def forward(
        self, last_slice: torch.Tensor, tau: Optional[float] = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """(B,d,d_model) → w (B,K,d) 各步合法权重、µ̂ (B,K,d) logits。"""
        temp = self.default_tau if tau is None else tau
        if temp <= 0.0:
            raise ValueError(f"温度 τ={temp} 须 >0（F6 集中度温度）")
        mu = self.proj(last_slice).transpose(1, 2)                 # (B,d,K)→(B,K,d)
        w = torch.softmax(mu / temp, dim=-1)                       # 资产维 softmax → long-only+full-invested
        return w, mu


# =====================================================================
# 顶层 SIT 模型
# =====================================================================

class SIT(nn.Module):
    """Signature-Informed Transformer（端到端资产配置网络，F3-F6 前向）。

    前向：F_ti（签名/交叉签名/日历）→ 签名嵌入(F3) → N_layers×[时间因果(F4)+签名资产(F5)+FFN]
    → last-slice 输出头(F6) → 各步 long-only/fully-invested 权重 w∈R^{K×d}。
    µ̂ 仅作 allocation 层 logits（F8）；CVaR 端到端训练在 m4。
    """

    def __init__(self, n_assets: int, config: SITConfig = DEFAULT_CONFIG) -> None:
        super().__init__()
        self.config = config
        self.n_assets = n_assets
        d_model = config.sit_d_model
        if d_model % config.sit_n_heads != 0:
            raise ValueError(
                f"sit_d_model={d_model} 须被 sit_n_heads={config.sit_n_heads} 整除（AS14 缩减档需自洽）"
            )
        self.embedding = SignatureEmbedding(
            d_sig=config.asset_signature_dim,          # 7（时间增广+level0，AS21）
            calendar_dim=config.calendar_feature_dim,  # 8（AS4）
            n_assets=n_assets,
            d_model=d_model,
        )
        self.blocks = nn.ModuleList([
            SITBlock(
                d_model=d_model,
                d_ff=config.sit_d_ff,
                n_heads=config.sit_n_heads,
                d_beta=config.sit_d_beta,
                hidden_c=config.sit_hidden_c,
                dropout=config.dropout,
            )
            for _ in range(config.sit_n_layers)
        ])
        self.head = AllocationHead(
            d_model=d_model, n_steps_k=config.decision_steps_k, tau=config.sit_tau
        )

    # ---- 编码（返回全序列表征，供因果性诊断）----
    def encode(
        self, asset_sig: torch.Tensor, cross_sig: torch.Tensor, calendar: torch.Tensor,
        return_attn: bool = False,
    ) -> tuple[torch.Tensor, list]:
        """F_ti → 全序列表征 (B,H,d,d_model)（未取 last-slice）。"""
        x = self.embedding(asset_sig, calendar)
        auxes = []
        for blk in self.blocks:
            x, aux = blk(x, cross_sig, return_attn=return_attn)
            auxes.append(aux)
        return x, auxes

    def forward(
        self,
        asset_sig: torch.Tensor,
        cross_sig: torch.Tensor,
        calendar: torch.Tensor,
        tau: Optional[float] = None,
        return_aux: bool = False,
    ):
        """F_ti → 各步组合权重 w (B,K,d)（非负、逐步和=1）。

        Args:
            asset_sig: (B,H,d,d_sig) 逐资产 M=2 签名序列（F1/D4-i）。
            cross_sig: (B,d,d,d_cross) 成对交叉签名（F2/D4-ii）。
            calendar:  (B,H,F) 日历特征（D4-iii/AS4）。
            tau: 覆盖 softmax 温度（默认 config.sit_tau）。
            return_aux: 附带 µ̂ / 全序列表征 / 注意力（诊断用）。
        """
        repr_seq, auxes = self.encode(asset_sig, cross_sig, calendar, return_attn=return_aux)
        last_slice = repr_seq[:, -1, :, :]                         # last-slice（AS6）→ (B,d,d_model)
        w, mu = self.head(last_slice, tau=tau)
        if return_aux:
            return w, {"mu": mu, "repr": repr_seq, "attns": auxes}
        return w

    # ---- SA1 模块消融配置（m5）----
    def set_ablation(self, variant: Optional[str]) -> None:
        """配置 SA1 结构消融开关（在全部 SITBlock 生效；默认 full 恢复现行为）。

        variant（spec SA1，p6/Table2）：
          - None / "full"：完整 SIT（无消融）；
          - "no_asset_attn"：w/o Asset Attn，跳过整个 F5 签名增强资产注意力子层；
          - "no_financial_bias"：w/o Financial Bias，去 γ·B 退回标准注意力；
          - "no_gate"：w/o Gate γ，固定 γ=1（保留偏置 B、去可学习 gate）。
        注："no_cvar"（w/o CVaR）为损失层消融（train 层换均值目标），结构保持 full，不在此处理。
        """
        v = variant or "full"
        for blk in self.blocks:
            blk.ablation_disable_asset_attn = (v == "no_asset_attn")
            blk.asset_attn.ablation_disable_bias = (v == "no_financial_bias")
            blk.asset_attn.ablation_gamma_fixed = 1.0 if v == "no_gate" else None

    # ---- 便捷工具 ----
    def count_parameters(self) -> int:
        """可训练参数量（冒烟/审计用）。"""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    @staticmethod
    def features_to_tensors(
        feat: dict, device: Optional[torch.device] = None, dtype: torch.dtype = torch.float32
    ) -> dict[str, torch.Tensor]:
        """m2 `build_feature_tensors` 的 numpy 字典 → torch 张量字典（供前向）。"""
        keys = ("asset_signatures", "cross_signatures", "calendar")
        return {
            k: torch.as_tensor(np.asarray(feat[k]), dtype=dtype, device=device) for k in keys
        }

    def forward_from_features(
        self, feat: dict, tau: Optional[float] = None, return_aux: bool = False
    ):
        """直接吃 m2 特征字典（numpy）→ 前向（自动转张量并对齐 device）。"""
        device = next(self.parameters()).device
        t = self.features_to_tensors(feat, device=device)
        return self.forward(
            t["asset_signatures"], t["cross_signatures"], t["calendar"],
            tau=tau, return_aux=return_aux,
        )


def build_sit(n_assets: int, config: SITConfig = DEFAULT_CONFIG) -> SIT:
    """构造 SIT 模型（参数化 n_assets；d_model/d_ff/layers/heads/hidden_c 由 config 供 m4 搜索）。"""
    return SIT(n_assets=n_assets, config=config)
