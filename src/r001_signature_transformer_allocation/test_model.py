"""r001 · m3 SIT 网络单元测试（强制安全网）。

覆盖（对 spec F3/F4/F5/F6 与 plan m3 验证点）：
1. 前向输出 shape==(B,K=12,d)、每步权重非负且逐步和≈1（单纯形有效性，F6 long-only+fully-invested）；
2. gate γ=softplus(γ̂)>0 恒成立（F5，随机初值多次校验）；
3. 因果性：时间维注意力不泄漏未来切片（TemporalCausalAttention 掩码 + 全编码器切片扰动，F4）；
4. Theorem 2.2 定性（加分）：增大 γ 使与签名偏置对齐的资产注意力份额单调上升（数值方向验证）；
5. 辅助：三嵌入融合形状、梯度端到端可回流（m4 训练前置）、config 缩减档自洽。

运行（单元测试，合成数据，快、确定、无数据依赖）：
    cd /Users/hedi/report_reproduce
    uv run python -m src.r001_signature_transformer_allocation.test_model

真实 m2 F_ti 冒烟（单独调用，需本地行情数据）：
    uv run python -c "from src.r001_signature_transformer_allocation.test_model import smoke_real_forward; smoke_real_forward()"
（亦可 pytest 发现 test_* 函数。）
"""

from __future__ import annotations

import numpy as np
import torch

from .config import SITConfig
from .model import (
    SIT,
    SignatureAssetAttention,
    SignatureEmbedding,
    TemporalCausalAttention,
    build_sit,
)

_SEED = 20260713


def _cfg(**kw) -> SITConfig:
    """小规模缩减档 config（AS14；默认 d_model=16/heads=2/layers=1 保测试快）。"""
    base = dict(sit_d_model=16, sit_n_heads=2, sit_n_layers=1, sit_d_ff=16, sit_hidden_c=8, sit_d_beta=4)
    base.update(kw)
    return SITConfig(**base)


def _rand_features(cfg: SITConfig, b: int, d: int, seed: int = _SEED):
    """合成 F_ti 张量（维度严格取自 config 派生量，非魔法数字）。"""
    g = torch.Generator().manual_seed(seed)
    h = cfg.lookback_h
    asset_sig = torch.randn(b, h, d, cfg.asset_signature_dim, generator=g) * 0.1
    cross_sig = torch.randn(b, d, d, cfg.cross_signature_dim, generator=g) * 0.1
    calendar = torch.randn(b, h, cfg.calendar_feature_dim, generator=g) * 0.1
    return asset_sig, cross_sig, calendar


# ---------------------------------------------------------------------------
# 1. 单纯形有效性（F6：shape / 非负 / 逐步和=1）
# ---------------------------------------------------------------------------

def test_forward_shape_and_simplex() -> None:
    """前向输出 (B,K,d)，K=config.decision_steps_k=12；每步非负、逐步和≈1。"""
    torch.manual_seed(_SEED)
    cfg = _cfg()
    b, d = 4, 8
    model = build_sit(n_assets=d, config=cfg).eval()
    asset_sig, cross_sig, calendar = _rand_features(cfg, b, d)
    with torch.no_grad():
        w = model(asset_sig, cross_sig, calendar)
    assert w.shape == (b, cfg.decision_steps_k, d) == (b, 12, d), w.shape
    assert torch.all(w >= 0.0), f"存在负权重，min={w.min().item()}"
    step_sums = w.sum(dim=-1)                                     # (B,K)
    assert torch.allclose(step_sums, torch.ones_like(step_sums), atol=1e-5), \
        f"逐步和偏离 1，max|sum−1|={(step_sums - 1).abs().max().item():.2e}"


def test_tau_controls_concentration() -> None:
    """F6：τ 增大 → 权重更均匀（HHI 下降），验证温度语义（SA4 前置）。"""
    torch.manual_seed(_SEED)
    cfg = _cfg()
    b, d = 2, 10
    model = build_sit(n_assets=d, config=cfg).eval()
    asset_sig, cross_sig, calendar = _rand_features(cfg, b, d)
    with torch.no_grad():
        w_lo = model(asset_sig, cross_sig, calendar, tau=0.5)
        w_hi = model(asset_sig, cross_sig, calendar, tau=2.0)
    hhi_lo = (w_lo ** 2).sum(dim=-1).mean().item()
    hhi_hi = (w_hi ** 2).sum(dim=-1).mean().item()
    assert hhi_hi < hhi_lo, f"τ↑ 应降 HHI（更分散），实测 hhi(τ=2)={hhi_hi:.4f} !< hhi(τ=0.5)={hhi_lo:.4f}"


# ---------------------------------------------------------------------------
# 2. gate γ=softplus(γ̂)>0 恒成立（F5）
# ---------------------------------------------------------------------------

def test_gamma_strictly_positive() -> None:
    """F5：γ=softplus(γ̂)>0 恒成立（多随机初值 + 极端 γ̂ 均校验）。"""
    for seed in range(5):
        torch.manual_seed(seed)
        cfg = _cfg()
        model = build_sit(n_assets=6, config=cfg)
        for blk in model.blocks:
            g = blk.asset_attn.gamma
            assert g.item() > 0.0, f"seed={seed} γ={g.item()} 非正"
    # 极端 γ̂：softplus 对任意实数恒正
    attn = SignatureAssetAttention(d_model=16, n_heads=2, d_beta=4, hidden_c=8, dropout=0.0)
    for val in (-50.0, -1.0, 0.0, 1.0, 50.0):
        with torch.no_grad():
            attn.gamma_hat.fill_(val)
        assert attn.gamma.item() > 0.0, f"γ̂={val} → γ={attn.gamma.item()} 非正"


# ---------------------------------------------------------------------------
# 3. 因果性：时间维注意力不看未来切片（F4）
# ---------------------------------------------------------------------------

def test_temporal_attention_is_causal() -> None:
    """TemporalCausalAttention：扰动未来位 t'>t，位置 t 输出不变（掩码正确）。"""
    torch.manual_seed(_SEED)
    attn = TemporalCausalAttention(d_model=16, n_heads=4, dropout=0.0).eval()
    n, length, m = 3, 12, 16
    x = torch.randn(n, length, m)
    with torch.no_grad():
        out = attn(x)
        t_cut = 5                                                # 扰动 t>=6 的所有未来位
        x_pert = x.clone()
        x_pert[:, t_cut + 1:, :] += torch.randn(n, length - t_cut - 1, m) * 5.0
        out_pert = attn(x_pert)
    # 位置 0..t_cut 的输出必须逐元素不变（因果：不看未来）
    assert torch.allclose(out[:, : t_cut + 1], out_pert[:, : t_cut + 1], atol=1e-6), \
        "因果掩码失效：扰动未来位改变了历史位输出"
    # 位置 t_cut+1.. 的输出应改变（确认扰动确实生效、非平凡通过）
    assert not torch.allclose(out[:, t_cut + 1:], out_pert[:, t_cut + 1:], atol=1e-6), \
        "扰动未生效（测试无效）"


def test_encoder_causal_over_slices() -> None:
    """全编码器：扰动 asset_sig 未来切片，历史切片表征不变（cross 全窗口固定，F4 因果）。"""
    torch.manual_seed(_SEED)
    cfg = _cfg()
    b, d = 2, 7
    model = build_sit(n_assets=d, config=cfg).eval()
    asset_sig, cross_sig, calendar = _rand_features(cfg, b, d)
    with torch.no_grad():
        repr0, _ = model.encode(asset_sig, cross_sig, calendar)
        cut = 30
        a_pert = asset_sig.clone()
        a_pert[:, cut + 1:] += torch.randn_like(a_pert[:, cut + 1:]) * 3.0
        repr1, _ = model.encode(a_pert, cross_sig, calendar)
    assert torch.allclose(repr0[:, : cut + 1], repr1[:, : cut + 1], atol=1e-5), \
        "编码器非因果：未来切片扰动影响了历史切片表征"
    assert not torch.allclose(repr0[:, cut + 1:], repr1[:, cut + 1:], atol=1e-5), \
        "未来切片扰动未生效（测试无效）"


# ---------------------------------------------------------------------------
# 4. Theorem 2.2 定性（加分）：γ↑ ⇒ 对齐签名偏置的注意力份额单调上升
# ---------------------------------------------------------------------------

def test_gamma_monotone_attention_alignment() -> None:
    """Theorem 2.2 数值方向：固定 QK 与 B，增大 γ ⇒ 每 query 对其最大偏置 key 的注意力份额单调不降。

    softmax 单调性：p_{j,l}(γ)=softmax(qk+γ·B)，对 l*=argmax_l B_{j,l}，dp/dγ=p·(B−E[B])>0（严格）。
    """
    torch.manual_seed(_SEED)
    cfg = _cfg()
    d_model = cfg.sit_d_model
    attn = SignatureAssetAttention(d_model=d_model, n_heads=2, d_beta=4, hidden_c=8, dropout=0.0).eval()
    b, d, hh = 1, 8, cfg.lookback_h
    g = torch.Generator().manual_seed(_SEED)
    x = torch.randn(b, hh, d, d_model, generator=g) * 0.1        # token（末维 d_model，非原始签名）
    cross_sig = torch.randn(b, d, d, cfg.cross_signature_dim, generator=g) * 0.1
    with torch.no_grad():
        qk, bias, _ = attn.logit_parts(x, cross_sig)             # (B,H,N_H,d,d)
        # 取首切片首头一组 logits，考察每 query 行对其最大偏置 key 的份额随 γ 变化
        qk0, b0 = qk[0, 0, 0], bias[0, 0, 0]                      # (d,d)
        star = b0.argmax(dim=-1)                                  # 每 query j 的 max-bias key l*
        gammas = torch.linspace(0.0, 5.0, 11)
        shares = []
        for g in gammas:
            alpha = torch.softmax(qk0 + g * b0, dim=-1)           # (d,d)
            shares.append(alpha[torch.arange(d), star])           # 每 query 对 l* 的份额
        shares = torch.stack(shares)                              # (11, d)
    diffs = shares[1:] - shares[:-1]                              # 相邻 γ 差分
    assert torch.all(diffs >= -1e-6), \
        f"存在 γ↑ 使 max-bias 份额下降（违反 Theorem 2.2），min diff={diffs.min().item():.2e}"
    assert (shares[-1] - shares[0]).min().item() > 0.0, \
        "γ 由 0→5 未整体抬升 max-bias 份额（方向性未体现）"


# ---------------------------------------------------------------------------
# 5. 辅助：嵌入形状 / 端到端梯度 / config 自洽
# ---------------------------------------------------------------------------

def test_embedding_shape() -> None:
    """F3：三嵌入融合输出 (B,H,d,d_model)。"""
    torch.manual_seed(_SEED)
    cfg = _cfg()
    emb = SignatureEmbedding(cfg.asset_signature_dim, cfg.calendar_feature_dim, n_assets=5, d_model=cfg.sit_d_model)
    b, d = 2, 5
    asset_sig, _, calendar = _rand_features(cfg, b, d)
    x = emb(asset_sig, calendar)
    assert x.shape == (b, cfg.lookback_h, d, cfg.sit_d_model), x.shape


def test_end_to_end_gradient() -> None:
    """F8 前置：CVaR 端到端可训练——损失对全部参数（含 γ̂）梯度可回流。"""
    torch.manual_seed(_SEED)
    cfg = _cfg()
    b, d = 3, 6
    model = build_sit(n_assets=d, config=cfg).train()
    asset_sig, cross_sig, calendar = _rand_features(cfg, b, d)
    w = model(asset_sig, cross_sig, calendar)
    # 占位组合损失（m4 换 CVaR）：−平均权重·随机收益
    r = torch.randn(b, cfg.decision_steps_k, d) * 0.02
    loss = -(w * r).sum(dim=-1).mean()
    loss.backward()
    n_with_grad = sum(1 for p in model.parameters() if p.grad is not None and p.grad.abs().sum() > 0)
    n_total = sum(1 for _ in model.parameters())
    assert n_with_grad >= n_total - 1, f"仅 {n_with_grad}/{n_total} 参数有梯度（端到端回流不完整）"
    gamma_grad = model.blocks[0].asset_attn.gamma_hat.grad
    assert gamma_grad is not None, "gate γ̂ 无梯度（不可端到端学习）"


def test_config_reduced_heads_divide() -> None:
    """AS14 缩减档自洽：d_model 须被 n_heads 整除，否则构造报错。"""
    ok = SITConfig(sit_d_model=32, sit_n_heads=4)
    build_sit(n_assets=4, config=ok)                             # 32/4=8 OK
    try:
        build_sit(n_assets=4, config=SITConfig(sit_d_model=30, sit_n_heads=4))
        raise AssertionError("d_model=30 不整除 heads=4 却未报错")
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# 真实 m2 F_ti 冒烟（单独调用，需本地行情数据）
# ---------------------------------------------------------------------------

def smoke_real_forward(top_n: int = 8, n_dates: int = 6) -> None:
    """用 m2 真实 F_ti 喂 SIT 前向，打印 w 的 shape/非负/逐步和≈1/参数量（冒烟，非验证结论）。"""
    from .data import load_data_bundle
    from .signatures import build_feature_tensors
    from .config import DEFAULT_CONFIG

    print("=" * 64)
    print(f"r001 SIT · m3 真实 F_ti 前向冒烟（top_n={top_n}）")
    print("=" * 64)
    bundle = load_data_bundle(DEFAULT_CONFIG, top_n=top_n)
    train_dates = bundle.splits["train"]
    # 取训练段中历史充足（前序交易日≥H）的前 n_dates 个决策点
    idx = bundle.daily_log_returns.index
    usable = [d for d in train_dates if idx.get_indexer([d])[0] >= DEFAULT_CONFIG.lookback_h][:n_dates]
    feat = build_feature_tensors(bundle, usable, DEFAULT_CONFIG)
    d = len(feat["codes"])
    print(f"  决策点 B={len(feat['decision_dates'])}  资产 d={d}  H={DEFAULT_CONFIG.lookback_h}  K={DEFAULT_CONFIG.decision_steps_k}")
    print(f"  asset_signatures {feat['asset_signatures'].shape}  cross {feat['cross_signatures'].shape}  calendar {feat['calendar'].shape}")

    torch.manual_seed(_SEED)
    model = build_sit(n_assets=d, config=DEFAULT_CONFIG).eval()
    with torch.no_grad():
        w, aux = model.forward_from_features(feat, return_aux=True)
    step_sums = w.sum(dim=-1)
    print("-" * 64)
    print(f"  输出 w shape        : {tuple(w.shape)}  (期望 (B,K={DEFAULT_CONFIG.decision_steps_k},d={d}))")
    print(f"  µ̂ logits shape      : {tuple(aux['mu'].shape)}")
    print(f"  非负性 min(w)        : {w.min().item():.3e}  (≥0)")
    print(f"  逐步和 max|Σw−1|     : {(step_sums - 1).abs().max().item():.3e}  (≈0)")
    print(f"  gate γ（各层）        : {[round(blk.asset_attn.gamma.item(), 4) for blk in model.blocks]}  (>0)")
    print(f"  可训练参数量          : {model.count_parameters():,}")
    print(f"  首决策点 step-1 权重  : {np.round(w[0, 0].numpy(), 4).tolist()}")
    assert w.shape == (len(feat["decision_dates"]), DEFAULT_CONFIG.decision_steps_k, d)
    assert torch.all(w >= 0) and torch.allclose(step_sums, torch.ones_like(step_sums), atol=1e-5)
    print("=" * 64)
    print("真实 F_ti 前向冒烟通过（合法单纯形权重、γ>0、K=12 多步）。")


# ---------------------------------------------------------------------------
# 脚本运行入口（逐项打印真实断言结果）
# ---------------------------------------------------------------------------

def _run_all() -> None:
    tests = [
        ("前向 shape+单纯形有效性(F6)", test_forward_shape_and_simplex),
        ("τ 控集中度(HHI↓)", test_tau_controls_concentration),
        ("[F5]gate γ=softplus>0 恒成立", test_gamma_strictly_positive),
        ("[F4]时间注意力因果(掩未来)", test_temporal_attention_is_causal),
        ("[F4]编码器切片因果", test_encoder_causal_over_slices),
        ("[Thm2.2]γ↑ 对齐份额单调升", test_gamma_monotone_attention_alignment),
        ("[F3]三嵌入融合形状", test_embedding_shape),
        ("[F8前置]端到端梯度回流", test_end_to_end_gradient),
        ("[AS14]缩减档 heads 整除自洽", test_config_reduced_heads_divide),
    ]
    print("=" * 64)
    print("r001 SIT · m3 模型单元测试（合成数据安全网）")
    print("=" * 64)
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")

    # 关键数值展示（单纯形 / γ / Theorem 2.2 方向）
    torch.manual_seed(_SEED)
    cfg = _cfg()
    model = build_sit(n_assets=8, config=cfg).eval()
    asset_sig, cross_sig, calendar = _rand_features(cfg, 4, 8)
    with torch.no_grad():
        w = model(asset_sig, cross_sig, calendar)
    print("-" * 64)
    print("关键数值：")
    print(f"  输出 w shape={tuple(w.shape)}（B,K=12,d=8）；min(w)={w.min().item():.3e}≥0；"
          f"max|Σw−1|={(w.sum(-1) - 1).abs().max().item():.2e}")
    print(f"  gate γ={model.blocks[0].asset_attn.gamma.item():.4f}>0（softplus(0)=ln2）")
    print(f"  可训练参数量={model.count_parameters():,}（AS14 缩减档 d_model={cfg.sit_d_model}）")
    print("=" * 64)
    print("全部单元测试通过。")


if __name__ == "__main__":
    _run_all()
