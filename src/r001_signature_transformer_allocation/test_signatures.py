"""r001 · m2 签名单元测试（AS17 强制安全网）。

覆盖：
1. 单段 / Chen 拼接 / shuffle 恒等 —— M=2 签名参考实现正确性；
2. 向量化版（asset_signature_sequence / cross_signature_matrix）与参考实现逐元素一致；
3. **AS17 核心**：合成 lead-lag 路径的交叉签名 signed-area 符号（Proposition 2.1）——
   i 领先 j ⇒ A(X^i,X^j)>0；反向 ⇒ 符号翻转 A<0；无 lead-lag/同一路径 ⇒ A≈0；
   并对解析可算的正弦 lead-lag 校验量级（A=2π·sinφ）。

运行：
    cd /Users/hedi/report_reproduce
    uv run python -m src.r001_signature_transformer_allocation.test_signatures
（亦可 pytest 发现 test_* 函数。）
"""

from __future__ import annotations

import numpy as np

from .config import SITConfig
from .signatures import (
    asset_signature_sequence,
    cross_signature_matrix,
    cross_signature_pairs,
    levy_area,
    signature_m2_parts,
    signature_m2_sequence,
    signed_area_matrix,
)

_RNG = np.random.default_rng(20260713)


# ---------------------------------------------------------------------------
# 1. M=2 参考实现正确性（单段 / Chen / shuffle）
# ---------------------------------------------------------------------------

def test_single_segment_closed_form() -> None:
    """单段路径 [0→(a,b)]：level1=(a,b)，level2=½[[a²,ab],[ab,b²]]（分段线性闭式）。"""
    a, b = 0.7, -0.4
    path = np.array([[0.0, 0.0], [a, b]])
    l1, l2 = signature_m2_parts(path)
    assert np.allclose(l1, [a, b])
    assert np.allclose(l2, 0.5 * np.array([[a * a, a * b], [a * b, b * b]]))


def test_chen_relation_two_segments() -> None:
    """两段拼接经 Chen relation 与手算迭代积分一致。"""
    d1 = np.array([1.0, 0.5])
    d2 = np.array([-0.3, 0.8])
    path = np.array([[0.0, 0.0], d1, d1 + d2])
    l1, l2 = signature_m2_parts(path)
    # 手算：level1=d1+d2；level2=½d1⊗d1 + d1⊗d2 + ½d2⊗d2
    exp_l2 = 0.5 * np.outer(d1, d1) + np.outer(d1, d2) + 0.5 * np.outer(d2, d2)
    assert np.allclose(l1, d1 + d2)
    assert np.allclose(l2, exp_l2)


def test_shuffle_identity() -> None:
    """shuffle 恒等：S_ii=½(ΔX_i)²；S_ij+S_ji=ΔX_i·ΔX_j（任意路径成立）。"""
    path = _RNG.standard_normal((15, 3)).cumsum(axis=0)
    l1, l2 = signature_m2_parts(path)
    assert np.allclose(np.diag(l2), 0.5 * l1 ** 2)
    assert np.allclose(l2 + l2.T, np.outer(l1, l1))


# ---------------------------------------------------------------------------
# 2. 向量化版 ≡ 参考实现（防加速版引入 bug）
# ---------------------------------------------------------------------------

def test_cross_matrix_matches_reference() -> None:
    """cross_signature_matrix(S[i,j]=∫X^i dX^j) 与逐对参考实现逐元素一致。"""
    H, d = 40, 5
    R = _RNG.standard_normal((H, d)) * 0.02
    S = cross_signature_matrix(R)
    cum = np.cumsum(R, axis=0)                       # 全窗口累积路径 X_k（rebased 起点 0）
    path = np.vstack([np.zeros((1, d)), cum])       # (H+1, d)：X_0..X_H
    _, l2 = signature_m2_parts(path)
    assert np.allclose(S, l2), np.abs(S - l2).max()
    # 交叉张量与 signed-area 派生一致
    C = cross_signature_pairs(R)
    assert np.allclose(C[..., 0], S) and np.allclose(C[..., 1], S.T)
    assert np.allclose(signed_area_matrix(R), S - S.T)


def test_asset_sequence_matches_reference() -> None:
    """asset_signature_sequence（时间增广向量化）与逐资产参考 running 签名逐元素一致。"""
    cfg = SITConfig()                               # time_augment=True, include_level0=True → d_sig=7
    H, d = 30, 4
    R = _RNG.standard_normal((H, d)) * 0.03
    seq = asset_signature_sequence(R, cfg)          # (H, d, 7)
    assert seq.shape == (H, d, cfg.asset_signature_dim) == (H, d, 7)
    t = (np.arange(H + 1, dtype=float) / H)         # 归一化时间 t_0..t_H
    for j in range(d):
        cum = np.concatenate([[0.0], np.cumsum(R[:, j])])          # X_0..X_H
        aug_path = np.column_stack([t, cum])                       # (H+1, 2) 时间增广路径
        ref = signature_m2_sequence(aug_path, include_level0=True)  # (H, 7)
        assert np.allclose(seq[:, j, :], ref), (j, np.abs(seq[:, j, :] - ref).max())


def test_config_dim_toggles() -> None:
    """d_sig 随 config 开关正确：无 level0 → 6；不增广 → 3。"""
    H, d = 12, 3
    R = _RNG.standard_normal((H, d)) * 0.02
    assert asset_signature_sequence(R, SITConfig(signature_include_level0=False)).shape[-1] == 6
    assert asset_signature_sequence(R, SITConfig(signature_time_augment=False)).shape[-1] == 3


# ---------------------------------------------------------------------------
# 3. AS17 核心：lead-lag signed-area 符号（Proposition 2.1）
# ---------------------------------------------------------------------------

def _sin_leadlag_path(phi: float, n: int = 2000) -> np.ndarray:
    """2D 路径 (X^i, X^j)：X^i=sin(t)，X^j=sin(t−phi)（phi>0 ⇒ j 滞后 i ⇒ i 领先 j）。"""
    t = np.linspace(0.0, 2.0 * np.pi, n)
    return np.column_stack([np.sin(t), np.sin(t - phi)])


def test_leadlag_signed_area_positive() -> None:
    """AS17：i 严格领先 j ⇒ A(X^i,X^j)>0（Proposition 2.1），且量级 ≈ 2π·sinφ。"""
    phi = np.pi / 4
    area = levy_area(_sin_leadlag_path(phi))
    analytic = 2.0 * np.pi * np.sin(phi)            # ∮ 解析值（见 signatures 推导）
    assert area > 0.0, f"lead-lag signed-area 应 >0，实际 {area}"
    assert abs(area - analytic) / analytic < 0.02, (area, analytic)


def test_leadlag_sign_flips_on_reverse() -> None:
    """AS17：交换领先/滞后角色 ⇒ signed-area 符号翻转（反对称 A_ji=−A_ij）。"""
    phi = np.pi / 4
    path = _sin_leadlag_path(phi)                   # (X^i, X^j)，i 领先
    area_fwd = levy_area(path)
    area_rev = levy_area(path[:, ::-1])             # (X^j, X^i)，角色互换
    assert area_fwd > 0.0 and area_rev < 0.0
    assert np.isclose(area_fwd, -area_rev, rtol=1e-6)


def test_no_leadlag_area_near_zero() -> None:
    """AS17：无 lead-lag（两路径同相/同一）⇒ signed-area ≈ 0。"""
    t = np.linspace(0.0, 2.0 * np.pi, 2000)
    same = np.column_stack([np.sin(t), np.sin(t)])  # 完全同相
    assert abs(levy_area(same)) < 1e-9


def test_discrete_stepwise_leadlag() -> None:
    """AS17（确定性）：离散阶跃 lead-lag，i 先动 j 后一步跟随 ⇒ A=+1（精确）；反向 ⇒ −1。"""
    # X^i: 0→1→1→1（第 1 步上跳）；X^j: 0→0→1→1（第 2 步上跳，滞后 i 一步）
    path = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [1.0, 1.0]])
    assert np.isclose(levy_area(path), 1.0), levy_area(path)
    assert np.isclose(levy_area(path[:, ::-1]), -1.0)


def test_cross_matrix_leadlag_consistency() -> None:
    """窗口向量化交叉签名的 signed-area 与逐对 levy_area 对 lead-lag 符号一致。"""
    H = 500
    t = np.linspace(0.0, 2.0 * np.pi, H + 1)
    xi = np.sin(t)
    xj = np.sin(t - np.pi / 3)                       # i 领先 j
    R = np.column_stack([np.diff(xi), np.diff(xj)])  # (H, 2) 增量
    A = signed_area_matrix(R)
    assert A[0, 1] > 0.0 and A[1, 0] < 0.0
    assert np.isclose(A[0, 1], -A[1, 0])


# ---------------------------------------------------------------------------
# 脚本运行入口（逐项打印真实数值，AS17 断言可见）
# ---------------------------------------------------------------------------

def _run_all() -> None:
    tests = [
        ("单段闭式", test_single_segment_closed_form),
        ("Chen两段拼接", test_chen_relation_two_segments),
        ("shuffle恒等", test_shuffle_identity),
        ("交叉矩阵≡参考", test_cross_matrix_matches_reference),
        ("逐资产序列≡参考", test_asset_sequence_matches_reference),
        ("config维度开关", test_config_dim_toggles),
        ("[AS17]lead-lag A>0", test_leadlag_signed_area_positive),
        ("[AS17]反向符号翻转", test_leadlag_sign_flips_on_reverse),
        ("[AS17]无lead-lag≈0", test_no_leadlag_area_near_zero),
        ("[AS17]离散阶跃A=±1", test_discrete_stepwise_leadlag),
        ("[AS17]窗口交叉一致", test_cross_matrix_leadlag_consistency),
    ]
    print("=" * 60)
    print("r001 SIT · m2 签名单元测试（AS17 安全网）")
    print("=" * 60)
    for name, fn in tests:
        fn()
        print(f"  [PASS] {name}")

    # AS17 关键数值展示
    phi = np.pi / 4
    area = levy_area(_sin_leadlag_path(phi))
    analytic = 2.0 * np.pi * np.sin(phi)
    print("-" * 60)
    print("AS17 lead-lag 数值：")
    print(f"  正弦 φ=π/4：signed-area A(X^i,X^j) = {area:.6f}  (解析 2π·sinφ = {analytic:.6f})")
    print(f"  离散阶跃 i 领先 j：A = {levy_area(np.array([[0,0],[1,0],[1,1],[1,1]], float)):+.1f}  "
          f"反向：{levy_area(np.array([[0,0],[1,0],[1,1],[1,1]], float)[:, ::-1]):+.1f}")
    print("  → i 领先 j ⇒ A>0（Proposition 2.1）成立；反向翻转、同相≈0。")
    print("=" * 60)
    print("全部单元测试通过。")


if __name__ == "__main__":
    _run_all()
