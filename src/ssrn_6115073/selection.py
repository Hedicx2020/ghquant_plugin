"""m2: Δβ 双区制 OLS 宏观敏感选股 · ssrn_6115073（市场迁移复现）

对齐要素：
  - F2（原文式5-8）：对每（股票 i，宏观因子 j），按宏观变化量 X 的符号分区制做单变量 OLS——
    X>0 子样本估 r_i=α+β⁺·X_j+ε（式6）、X<0 子样本估 β⁻（式7），Δβ=β⁺−β⁻（式8）；
    按 |Δβ| 取头部（AS9，无硬阈值）；显著性口径见下「三层梯度」。
  - R3（表4 β+/β−/Δβ）：本模块产出 **个股级** Δβ 机制（β 长表 + 候选集）。表4 是「11 方法 ×
    β」的**组合层**结果，方法层聚合依赖 m6 组合构建后对组合收益回归——在 m6 装配，非本模块。

显著性口径（AS15 经 planner 频率适配裁决为三层梯度，AS44 落地）：
  原文美股日频约 6000 观测、双区制各 3000，OLS 极易显著；本案月频（AS1/AS4）仅约 144 观测、
  双区制各 60-70，固定 α=0.05 双系数的统计行为与原文不等价（联合显著率≈0.28% 逼近随机）。
  planner 裁决改「频率适配三层梯度」（非放水，是求统计行为等价）：
    · 显著性水平全市场统一上调至 α=0.10（DELTA_BETA_ALPHA）；min_regime_obs / top_n 不变；
    · 按市场池规模**结构自动**落 tier（非人工按市场指定）：
        Tier-1 先跑 dual（β⁺、β⁻ 均 p<0.10）；
        某市场候选数 < VIABILITY_FLOOR(15) → 回退 single（至少一系数 p<0.10，Tier2_degraded）；
        single 后仍 < EXCLUSION_FLOOR(6) → excluded_narrow_pool，退出主分析（不用无显著性纯 |Δβ| 凑数）；
    · α 不逐市场差异化，仅 tier（双/单系数）由池规模阈值触发；排序始终按 |Δβ| 取头部（AS9）；
    · 另算 α=0.05-双系数一档（ROBUSTNESS_ALPHA）作稳健性侧栏供 verify 对比。
  回归 β/p 与显著性检验本身不变——口径变化只在选股判定层；三档共用同一 beta_table，无重复回归。

Δβ 估计窗口口径（未来函数红线，AS42）：
  采「训练期一次性估、测试期固定候选集」（原文风格）——只用 [train_start, train_end] 的历史
  月度数据估 Δβ 并选候选集，测试期（2019-2024）完全不进入估计。选股寻优不看测试期，候选集
  固定供下游 m3 聚类 / m4 模式匹配复用，无未来泄漏；信号 T 算 T+1 执行的错位由 m4/m6 承接。

数据对接（m1 prepare_all，接口以现状为准，不改 m1）：
  prep.markets[m].stock_returns / .member_mask ；prep.macro.change_panel / .selected_factors ；
  prep.train_start / .train_end。

只许冒烟运行：uv run python -m src.ssrn_6115073.selection
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, NamedTuple, Optional, Union

import numpy as np
import pandas as pd

from common.utils import ols_univariate

# ---------------------------------------------------------------------------
# m2 选股参数（集中常量，杜绝魔法数字，均可反查 spec/assumptions；严守文件所有权，
# 不写入 m1 建的 config.py，参数集中于本模块顶部，AS9/AS15/AS41/AS42/AS44）
# ---------------------------------------------------------------------------

# 主口径显著性水平（AS15 经 planner 频率适配裁决由 0.05 上调，全市场统一，AS44）
DELTA_BETA_ALPHA: Final[float] = 0.10

# 稳健性侧栏显著性水平（原 AS15 的 5% 双系数一档，仅回报候选数供 verify 对比，AS44）
ROBUSTNESS_ALPHA: Final[float] = 0.05

# tier 回退阈：Tier-1(dual) 候选 < 此值 → 该市场回退 Tier-2(single)（planner 指令，AS44）
VIABILITY_FLOOR: Final[int] = 15

# 排除阈：Tier-2(single) 候选仍 < 此值 → 该市场 excluded_narrow_pool 退出主分析（AS44）
EXCLUSION_FLOOR: Final[int] = 6

# 每个区制（X>0 与 X<0）的最小观测数门槛（AS41）：防自由度不足伪回归；不下调（非绑定约束）
MIN_REGIME_OBS: Final[int] = 24

# 每市场候选头部规模 N（AS9）：显著股按 |Δβ| 取前 N，不足则全取；全市场统一 cap
TOP_N_PER_MARKET: Final[int] = 50

# Δβ 估计窗口口径（AS42）：'train' = 训练期一次性估、测试固定候选集（原文风格，最防未来函数）
DELTA_BETA_WINDOW: Final[str] = "train"


# ---------------------------------------------------------------------------
# 返回结构（供 m3/m4 直接对接）
# ---------------------------------------------------------------------------

class DualRegimeBeta(NamedTuple):
    """单（股票, 因子）对的双区制回归结果（F2 式5-8）。"""
    beta_pos: float      # β⁺（X>0 子样本斜率）
    beta_neg: float      # β⁻（X<0 子样本斜率）
    delta_beta: float    # Δβ = β⁺ − β⁻
    p_pos: float         # β⁺ 双侧 t 检验 p 值
    p_neg: float         # β⁻ 双侧 t 检验 p 值
    n_pos: int           # X>0 子样本观测数
    n_neg: int           # X<0 子样本观测数
    significant: bool     # dual 口径：β⁺、β⁻ 是否均在 alpha_level 显著（便捷默认列）


@dataclass
class SelectionResult:
    """单市场 Δβ 选股产出（供 m3/m4 复用；接口向后兼容，下游仍按 .candidates 取）。"""
    market: str                 # 内部市场名（hs300/sz50/zz500）
    index_code: str             # 指数代码（000300/000016/000905）
    regime_tier: str            # 'Tier1'（dual）/ 'Tier2_degraded'（single 回退）/ 'excluded_narrow_pool'
    alpha_level: float          # 主口径显著性水平（0.10）
    sig_mode: str               # 最终采用的显著性模式（'dual' / 'single'）
    beta_table: pd.DataFrame    # 长表：stock×factor 的 β⁺/β⁻/Δβ/p/n（仅样本达标对；含 dual 便捷 significant 列）
    stock_scores: pd.DataFrame  # 最终 tier 下每显著股票的敏感度评分（stock_score=max|Δβ|、主导因子…）
    candidates: list[str]       # 最终采用候选股票集（按 max|Δβ| 取 top-N，供 m3 聚类 / m4 匹配）
    n_pool: int                 # 训练期曾为成分的股票池规模
    n_pairs_tested: int         # 通过样本门槛、进入回归的 (股票,因子) 对数
    n_cand_tier1: int           # Tier-1（dual@alpha）候选股票数
    n_cand_tier2: Optional[int]  # Tier-2（single@alpha）候选股票数（仅回退时非 None）
    n_cand_robust: int          # 稳健性侧栏（dual@ROBUSTNESS_ALPHA=0.05）候选股票数


# ---------------------------------------------------------------------------
# 双区制回归（一对；纯计算，输入已切分/对齐的 numpy 数组）
# ---------------------------------------------------------------------------

def dual_regime_beta(
    x_pos: np.ndarray,
    y_pos: np.ndarray,
    x_neg: np.ndarray,
    y_neg: np.ndarray,
    *,
    alpha_level: float = DELTA_BETA_ALPHA,
) -> DualRegimeBeta:
    """双区制 OLS（F2 式5-8）：X>0 估 β⁺、X<0 估 β⁻、Δβ=β⁺−β⁻。

    输入为已按 X 符号分区制、且已 dropna 对齐的 numpy 数组（配对与样本门槛由
    compute_beta_table 负责）。β⁺/β⁻ 各自用 common.utils.ols_univariate 估计并做双侧 t
    检验；significant 为 dual 便捷默认（两者均在 alpha_level 显著）——选股的 tier 口径在
    select 层按 p 值重判（dual/single），本字段不参与 tier 决策，仅便捷/诊断兼容。

    Args:
        x_pos, y_pos: X>0 子样本的（宏观变化量, 股票收益）。
        x_neg, y_neg: X<0 子样本的（宏观变化量, 股票收益）。
        alpha_level: 显著性水平（默认 0.10，AS44）。

    Returns:
        DualRegimeBeta。样本不足 / 无变异时相应 β/p 为 nan、significant=False。
    """
    fit_pos = ols_univariate(x_pos, y_pos)
    fit_neg = ols_univariate(x_neg, y_neg)
    delta = fit_pos.beta - fit_neg.beta
    significant = bool(
        (fit_pos.beta_pvalue < alpha_level) and (fit_neg.beta_pvalue < alpha_level)
    )
    return DualRegimeBeta(
        beta_pos=fit_pos.beta,
        beta_neg=fit_neg.beta,
        delta_beta=delta,
        p_pos=fit_pos.beta_pvalue,
        p_neg=fit_neg.beta_pvalue,
        n_pos=fit_pos.n_obs,
        n_neg=fit_neg.n_obs,
        significant=significant,
    )


def significance_mask(
    p_pos: Union[pd.Series, float],
    p_neg: Union[pd.Series, float],
    *,
    alpha_level: float,
    sig_mode: str,
):
    """显著性判定（向量化，支持 Series 或标量）。

    sig_mode='dual'   → β⁺ 与 β⁻ 均 p<alpha_level（Tier-1 主口径）；
    sig_mode='single' → 至少一个系数 p<alpha_level（Tier-2 频率适配回退，AS44）。
    NaN p 值（退化回归）比较恒为 False，故不显著（安全）。回归 p 值与 alpha 无关，故同一
    beta_table 可对不同 alpha/mode 反复判定，无需重跑回归。
    """
    below_pos = p_pos < alpha_level
    below_neg = p_neg < alpha_level
    if sig_mode == "dual":
        return below_pos & below_neg
    if sig_mode == "single":
        return below_pos | below_neg
    raise ValueError(f"unknown sig_mode: {sig_mode!r}（应为 'dual' 或 'single'）")


# ---------------------------------------------------------------------------
# β 长表：市场内所有 (股票,因子) 对（只用训练期数据，防未来函数）
# ---------------------------------------------------------------------------

def compute_beta_table(
    stock_returns: pd.DataFrame,
    member_mask: pd.DataFrame,
    change_panel: pd.DataFrame,
    factors: list[str],
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    *,
    min_regime_obs: int = MIN_REGIME_OBS,
    alpha_level: float = DELTA_BETA_ALPHA,
) -> pd.DataFrame:
    """市场内所有（股票, 因子）对的双区制 β 长表（F2）。

    未来函数红线：仅用 [train_start, train_end] 的历史月度数据（DELTA_BETA_WINDOW='train'）。
    股票池 = 训练期内曾为时点成分的股票（member_mask 训练切片 any=True），回归样本用其训练期
    全部非 NaN 月收益与对应宏观变化量 X 配对（X>0 / X<0 分区制；X==0 或 NaN 两区制均不纳入）。
    仅纳入两区制样本均 ≥ min_regime_obs 的对（样本门槛），逐对调 dual_regime_beta。

    significant 列为 dual@alpha_level 便捷默认（供诊断/快捷路径）；选股 tier 口径在 select 层
    按 p_pos/p_neg 重判（dual/single），不依赖此列。

    Returns:
        DataFrame，每行一（股票,因子）对，列：stock/factor/beta_pos/beta_neg/delta_beta/
        abs_delta_beta/p_pos/p_neg/n_pos/n_neg/significant。无达标对时返回空表（列齐全）。
    """
    cols = ["stock", "factor", "beta_pos", "beta_neg", "delta_beta", "abs_delta_beta",
            "p_pos", "p_neg", "n_pos", "n_neg", "significant"]

    idx = stock_returns.index
    factors = [f for f in factors if f in change_panel.columns]
    if not factors:
        return pd.DataFrame(columns=cols)

    train_sel = (idx >= train_start) & (idx <= train_end)
    R = stock_returns.loc[train_sel]                              # [训练月末 × 股票]
    X = change_panel.reindex(idx).loc[train_sel, factors]        # [训练月末 × 因子]，对齐到收益日历
    M = member_mask.reindex(idx).loc[train_sel]                  # [训练月末 × 股票]

    # 股票池：训练期内曾为时点成分（选股基数按时点成分，AS8/AS28）
    pool = [c for c in M.columns if bool(M[c].any())]
    if not pool:
        return pd.DataFrame(columns=cols)
    R = R[pool]
    R_arr = R.to_numpy()                                          # (n_month, n_pool)

    rows: list[dict] = []
    for j in factors:
        xj = X[j].to_numpy()
        pos_sel = xj > 0                                          # NaN>0 → False，自动排除缺失月
        neg_sel = xj < 0
        xp_full = xj[pos_sel]                                     # X>0 区制的 X（无 NaN）
        xn_full = xj[neg_sel]
        Rp = R_arr[pos_sel]                                       # (n_pos_month, n_pool)
        Rn = R_arr[neg_sel]
        for k, stock in enumerate(pool):
            yp = Rp[:, k]
            mp = ~np.isnan(yp)
            n_pos = int(mp.sum())
            if n_pos < min_regime_obs:
                continue
            yn = Rn[:, k]
            mn = ~np.isnan(yn)
            n_neg = int(mn.sum())
            if n_neg < min_regime_obs:
                continue
            res = dual_regime_beta(
                xp_full[mp], yp[mp], xn_full[mn], yn[mn], alpha_level=alpha_level
            )
            rows.append({
                "stock": stock, "factor": j,
                "beta_pos": res.beta_pos, "beta_neg": res.beta_neg,
                "delta_beta": res.delta_beta, "abs_delta_beta": abs(res.delta_beta),
                "p_pos": res.p_pos, "p_neg": res.p_neg,
                "n_pos": res.n_pos, "n_neg": res.n_neg,
                "significant": res.significant,
            })

    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# 候选集选择：显著性过滤（dual/single）+ 按 |Δβ| 取头部（AS9/AS15/AS44）
# ---------------------------------------------------------------------------

_SCORE_COLS: Final[list[str]] = ["stock", "stock_score", "n_sig_factors", "mean_delta_beta",
                                 "top_factor", "top_delta_beta", "selected"]


def select_candidates(
    beta_table: pd.DataFrame,
    *,
    top_n: int = TOP_N_PER_MARKET,
    alpha_level: float = DELTA_BETA_ALPHA,
    sig_mode: str = "dual",
) -> tuple[list[str], pd.DataFrame]:
    """按显著性过滤（sig_mode 口径）后取 |Δβ| 头部股票为候选集（F2 / AS9 / AS44）。

    先按 sig_mode（dual=两系数均显著 / single=至少一系数显著）在 alpha_level 下保留显著
    (股票,因子) 对；每只股票以其显著因子上的 max|Δβ| 作为宏观非对称敏感度评分，按评分降序取
    前 top_n（不足则全取）为候选集。排序准则始终为 |Δβ|（AS9 不变）。

    Returns:
        candidates: 候选股票代码列表（按敏感度降序）。
        stock_scores: 每显著股票一行——stock/stock_score(max|Δβ|)/n_sig_factors/
                      mean_delta_beta/top_factor/top_delta_beta(主导因子带符号 Δβ)/selected。
    """
    if beta_table.empty:
        return [], pd.DataFrame(columns=_SCORE_COLS)

    mask = significance_mask(
        beta_table["p_pos"], beta_table["p_neg"], alpha_level=alpha_level, sig_mode=sig_mode
    )
    sig = beta_table[mask].reset_index(drop=True)
    if sig.empty:
        return [], pd.DataFrame(columns=_SCORE_COLS)

    grp = sig.groupby("stock")
    scores = pd.DataFrame({
        "stock_score": grp["abs_delta_beta"].max(),
        "n_sig_factors": grp["factor"].size(),
        "mean_delta_beta": grp["delta_beta"].mean(),
    })
    # 主导因子 = 该股 |Δβ| 最大的因子（带符号 Δβ 供下行保护符号分布）
    idxmax = grp["abs_delta_beta"].idxmax().reindex(scores.index)
    scores["top_factor"] = sig.loc[idxmax.to_numpy(), "factor"].to_numpy()
    scores["top_delta_beta"] = sig.loc[idxmax.to_numpy(), "delta_beta"].to_numpy()

    scores = scores.sort_values("stock_score", ascending=False)
    n_pick = min(int(top_n), len(scores))
    candidates = list(scores.index[:n_pick])
    scores["selected"] = False
    scores.loc[candidates, "selected"] = True
    scores = scores.reset_index().rename(columns={"index": "stock"})
    return candidates, scores[_SCORE_COLS]


def select_with_tier(
    beta_table: pd.DataFrame,
    *,
    alpha_level: float = DELTA_BETA_ALPHA,
    top_n: int = TOP_N_PER_MARKET,
    viability_floor: int = VIABILITY_FLOOR,
    exclusion_floor: int = EXCLUSION_FLOOR,
) -> dict:
    """频率适配三层梯度选股（planner 裁决 AS44）：dual → single 回退 → excluded。

    结构自动落 tier（非人工按市场指定）：
      Tier-1  先跑 dual（β⁺、β⁻ 均 p<alpha_level）；候选数 ≥ viability_floor 即定案；
      Tier-2  否则回退 single（至少一系数 p<alpha_level）；候选数 ≥ exclusion_floor → degraded；
      excluded single 后仍 < exclusion_floor → excluded_narrow_pool，退出主分析
              （candidates 仍给出 single 结果供记录，但下游据 regime_tier 决定是否纳入）。

    Returns:
        dict(candidates, scores, regime_tier, sig_mode, n_tier1, n_tier2)。
    """
    cand1, scores1 = select_candidates(beta_table, top_n=top_n, alpha_level=alpha_level, sig_mode="dual")
    n1 = len(cand1)
    if n1 >= viability_floor:
        return dict(candidates=cand1, scores=scores1, regime_tier="Tier1",
                    sig_mode="dual", n_tier1=n1, n_tier2=None)

    cand2, scores2 = select_candidates(beta_table, top_n=top_n, alpha_level=alpha_level, sig_mode="single")
    n2 = len(cand2)
    tier = "Tier2_degraded" if n2 >= exclusion_floor else "excluded_narrow_pool"
    return dict(candidates=cand2, scores=scores2, regime_tier=tier,
                sig_mode="single", n_tier1=n1, n_tier2=n2)


# ---------------------------------------------------------------------------
# 单市场 / 三宽基端到端
# ---------------------------------------------------------------------------

def run_market_selection(
    name: str,
    index_code: str,
    stock_returns: pd.DataFrame,
    member_mask: pd.DataFrame,
    change_panel: pd.DataFrame,
    factors: list[str],
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    *,
    alpha_level: float = DELTA_BETA_ALPHA,
    top_n: int = TOP_N_PER_MARKET,
    min_regime_obs: int = MIN_REGIME_OBS,
    viability_floor: int = VIABILITY_FLOOR,
    exclusion_floor: int = EXCLUSION_FLOOR,
    robustness_alpha: float = ROBUSTNESS_ALPHA,
) -> SelectionResult:
    """单市场 Δβ 选股：β 长表 → 三层梯度显著过滤 → |Δβ| 头部候选集（AS44）。"""
    beta_table = compute_beta_table(
        stock_returns, member_mask, change_panel, factors,
        train_start, train_end,
        min_regime_obs=min_regime_obs, alpha_level=alpha_level,
    )
    tier = select_with_tier(
        beta_table, alpha_level=alpha_level, top_n=top_n,
        viability_floor=viability_floor, exclusion_floor=exclusion_floor,
    )
    # 稳健性侧栏：α=0.05 双系数一档候选数（同一 beta_table，无重复回归，AS44）
    robust_cands, _ = select_candidates(
        beta_table, top_n=top_n, alpha_level=robustness_alpha, sig_mode="dual"
    )

    train_sel = (member_mask.index >= train_start) & (member_mask.index <= train_end)
    n_pool = int(member_mask.loc[train_sel].any(axis=0).sum())
    return SelectionResult(
        market=name,
        index_code=index_code,
        regime_tier=tier["regime_tier"],
        alpha_level=alpha_level,
        sig_mode=tier["sig_mode"],
        beta_table=beta_table,
        stock_scores=tier["scores"],
        candidates=tier["candidates"],
        n_pool=n_pool,
        n_pairs_tested=int(len(beta_table)),
        n_cand_tier1=int(tier["n_tier1"]),
        n_cand_tier2=(None if tier["n_tier2"] is None else int(tier["n_tier2"])),
        n_cand_robust=int(len(robust_cands)),
    )


def run_selection(
    prep,
    factors: Optional[list[str]] = None,
    *,
    alpha_level: float = DELTA_BETA_ALPHA,
    top_n: int = TOP_N_PER_MARKET,
    min_regime_obs: int = MIN_REGIME_OBS,
    viability_floor: int = VIABILITY_FLOOR,
    exclusion_floor: int = EXCLUSION_FLOOR,
    robustness_alpha: float = ROBUSTNESS_ALPHA,
) -> dict[str, SelectionResult]:
    """m2 主入口：三宽基各自 Δβ 双区制选股（三层梯度口径），返回 {市场名: SelectionResult}。

    Args:
        prep: m1 prepare_all() 产出的 PreparedData。
        factors: 参与 Δβ 的宏观因子（默认 prep.macro.selected_factors，7 因子）。
        alpha_level: 主口径显著性水平（0.10，AS44）；其余为 tier 阈 / 门槛 / 头部规模。

    Returns:
        dict[市场名 → SelectionResult]；下游按市场取 .candidates（m3 聚类基）与 .beta_table（R3 机制），
        .regime_tier 告知该市场是 Tier1/Tier2_degraded/excluded_narrow_pool。
    """
    factors = list(factors) if factors is not None else list(prep.macro.selected_factors)
    change_panel = prep.macro.change_panel
    results: dict[str, SelectionResult] = {}
    for name, md in prep.markets.items():
        results[name] = run_market_selection(
            name, md.code, md.stock_returns, md.member_mask, change_panel, factors,
            prep.train_start, prep.train_end,
            alpha_level=alpha_level, top_n=top_n, min_regime_obs=min_regime_obs,
            viability_floor=viability_floor, exclusion_floor=exclusion_floor,
            robustness_alpha=robustness_alpha,
        )
    return results


# ---------------------------------------------------------------------------
# 冒烟运行（仅确认可执行 + 打印候选集规模/tier/β 表形状；验证结论归 verifier）
# ---------------------------------------------------------------------------

def _sign_split(scores: pd.DataFrame) -> tuple[int, int]:
    """候选集内主导因子 Δβ 的符号分布（>0 / <0）。"""
    if scores.empty:
        return 0, 0
    sel = scores[scores["selected"]]
    return int((sel["top_delta_beta"] > 0).sum()), int((sel["top_delta_beta"] < 0).sum())


def _smoke() -> None:
    from src.ssrn_6115073.data_prep import prepare_all

    pd.set_option("display.width", 170)
    pd.set_option("display.max_columns", 20)
    print("=" * 84)
    print("m2 Δβ 双区制 OLS 宏观敏感选股冒烟 · ssrn_6115073（频率适配三层梯度口径 AS44）")
    print("=" * 84)

    prep = prepare_all()
    factors = list(prep.macro.selected_factors)
    print(f"\n[口径] 主 α={DELTA_BETA_ALPHA}(统一) 每区制最小观测={MIN_REGIME_OBS} 头部 N={TOP_N_PER_MARKET} "
          f"估计窗={DELTA_BETA_WINDOW}")
    print(f"[tier] Tier-1 dual@{DELTA_BETA_ALPHA} → <{VIABILITY_FLOOR} 回退 Tier-2 single@{DELTA_BETA_ALPHA} "
          f"→ <{EXCLUSION_FLOOR} 记 excluded；稳健侧栏 dual@{ROBUSTNESS_ALPHA}")
    print(f"[估计窗] 训练 {prep.train_start.date()}~{prep.train_end.date()}"
          f"（测试 {prep.test_start.date()}~{prep.test_end.date()} 不进入估计，防未来函数）")
    print(f"[宏观因子] ({len(factors)}) {factors}")

    results = run_selection(prep, factors)

    print("\n" + "-" * 84)
    print("三宽基 tier 落位与候选规模：")
    print("-" * 84)
    for name, r in results.items():
        pos, neg = _sign_split(r.stock_scores)
        t2 = "-" if r.n_cand_tier2 is None else str(r.n_cand_tier2)
        excl = "  <<< EXCLUDED 退出主分析" if r.regime_tier == "excluded_narrow_pool" else ""
        print(f"\n[{name} / {r.index_code}]  regime_tier={r.regime_tier}  最终 sig_mode={r.sig_mode}{excl}")
        print(f"   训练期曾成分股票池 n_pool={r.n_pool} | 通过样本门槛(两区制均≥{MIN_REGIME_OBS})对={r.n_pairs_tested}")
        print(f"   Tier-1 dual@{DELTA_BETA_ALPHA} 候选={r.n_cand_tier1}"
              f"（阈 {VIABILITY_FLOOR}）| Tier-2 single@{DELTA_BETA_ALPHA} 候选={t2}"
              f"（阈 {EXCLUSION_FLOOR}）")
        print(f"   → 最终候选股票数={len(r.candidates)}（候选内主导Δβ>0:{pos} / <0:{neg}，下行保护对齐 R3）")
        print(f"   [稳健侧栏] dual@{ROBUSTNESS_ALPHA} 候选={r.n_cand_robust}（供 verify 稳健性对比）")

    print("\n" + "-" * 84)
    print("主市场（沪深300）β 长表形状与最终候选口径显著对示例（按 |Δβ| 降序 top 8）：")
    print("-" * 84)
    r = results["hs300"]
    bt = r.beta_table
    print(f"beta_table shape = {bt.shape}  columns = {list(bt.columns)}")
    if not bt.empty:
        mask = significance_mask(bt["p_pos"], bt["p_neg"],
                                 alpha_level=r.alpha_level, sig_mode=r.sig_mode)
        sig = bt[mask].sort_values("abs_delta_beta", ascending=False)
        show = sig.head(8)[["stock", "factor", "beta_pos", "beta_neg", "delta_beta",
                            "p_pos", "p_neg", "n_pos", "n_neg"]]
        print(f"（最终口径 sig_mode={r.sig_mode}@{r.alpha_level} 显著对数={len(sig)}）")
        print(show.round(4).to_string(index=False))

        by_factor = (bt[mask].groupby("factor").size().reindex(factors).fillna(0).astype(int))
        print("\n各宏观因子的最终口径显著 (股票,因子) 对数（hs300）：")
        print("   " + ", ".join(f"{f}={n}" for f, n in by_factor.items()))

        dpos = int((sig["delta_beta"] > 0).sum())
        dneg = int((sig["delta_beta"] < 0).sum())
        print(f"\n最终口径显著对 Δβ 符号分布（hs300）：Δβ>0:{dpos} / Δβ<0:{dneg} "
              f"（Δβ>0=下行保护，对齐 R3 迁移验证方向）")

    print("\n[候选集示例] 主市场前 10 只候选（供 m3 聚类 / m4 匹配）：")
    sc = r.stock_scores
    if not sc.empty:
        print(sc[sc["selected"]].head(10)[
            ["stock", "stock_score", "n_sig_factors", "top_factor", "top_delta_beta"]
        ].round(4).to_string(index=False))

    print("\n[下游接口] run_selection(prep) → dict[市场名 → SelectionResult]；"
          ".candidates(list[str]) 供 m3/m4、.regime_tier 告知 tier、.beta_table 供 R3 机制核对。")
    print("\n冒烟完成：三层梯度 Δβ 选股可端到端构造（可执行性确认；验证结论由 verifier 判定）。")


if __name__ == "__main__":
    _smoke()
