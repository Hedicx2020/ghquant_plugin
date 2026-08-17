"""策略门面 · ssrn_6115073（Online Portfolio Selection Using Macroeconomic Pattern Matching）。

集中 re-export 全链（m2→m6）各 milestone 的关键策略函数，作为单一策略入口，便于
上层/审计按 ``from src.ssrn_6115073.strategy import ...`` 取用。**本文件不含新逻辑**，
只做转出——各函数的权威实现仍在其所属 milestone 模块（selection/clustering/
pattern_matching/spillover/portfolio），通用算法在 ``common/``。

四步法（plan §1.2）对应关系：
  1. Δβ 双区制宏观敏感选股（F2）        → selection
  2. SU + 层次聚类分组（F3/F4）          → clustering
  3. 两阶段 Matrix Profile 模式匹配（F5-F8）→ pattern_matching
  4. Diebold-Yilmaz 溢出加权 + 组合构建（F9-F11）→ spillover + portfolio
"""

from __future__ import annotations

# m2 Δβ 双区制选股（F2 / R3）
from src.ssrn_6115073.selection import (
    dual_regime_beta,
    compute_beta_table,
    select_candidates,
    run_selection,
)

# m3 SU + 层次聚类（F3 / F4 / R2）
from src.ssrn_6115073.clustering import (
    pairwise_su,
    run_market_clustering,
    run_clustering,
)

# m4 两阶段 pattern matching（F5-F8）
from src.ssrn_6115073.pattern_matching import (
    search_optimal_window,
    znorm_distance_profile,
    causal_matrix_profile,
    stage1_macro_period,
    stage2_asset_forecast,
    signal_from_rhat,
    run_pattern_matching,
)

# m5 Diebold-Yilmaz 溢出加权 + 每簇选股（F9 / F10 / R4）
from src.ssrn_6115073.spillover import (
    compute_spillover_table,
    aggregate_fs,
    select_per_cluster,
    run_spillover,
    spillover_table_frame,
)

# m6 组合构建 EW/MV + 消融/基准 + 回测评估（F1 / F11 / B5-B8 / R1 / R5）
from src.ssrn_6115073.portfolio import (
    cpmm_selected,
    cpm_selected,
    pmm_selected,
    ewmfm_selected,
    selected_to_weights,
    compute_metrics,
    run_market_portfolio,
    run_portfolio,
    build_r1_table,
    build_extra_table,
    cumulative_returns,
    INTERNAL_MODELS,
    EXTERNAL_MODELS,
    ALL_MODELS,
)

__all__ = [
    # m2
    "dual_regime_beta", "compute_beta_table", "select_candidates", "run_selection",
    # m3
    "pairwise_su", "run_market_clustering", "run_clustering",
    # m4
    "search_optimal_window", "znorm_distance_profile", "causal_matrix_profile",
    "stage1_macro_period", "stage2_asset_forecast", "signal_from_rhat", "run_pattern_matching",
    # m5
    "compute_spillover_table", "aggregate_fs", "select_per_cluster", "run_spillover",
    "spillover_table_frame",
    # m6
    "cpmm_selected", "cpm_selected", "pmm_selected", "ewmfm_selected",
    "selected_to_weights", "compute_metrics", "run_market_portfolio", "run_portfolio",
    "build_r1_table", "build_extra_table", "cumulative_returns",
    "INTERNAL_MODELS", "EXTERNAL_MODELS", "ALL_MODELS",
]
