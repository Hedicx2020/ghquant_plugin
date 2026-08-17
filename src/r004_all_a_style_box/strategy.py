"""m2：2×2 大小盘与成长价值风格箱构造。

本模块只消费 m1 在信号日 T 形成的月末面板，不读取价格收益，也不计算组合
回报。完整合格池先按 ``(market_value, stock_code)`` 稳定切分 Size；价值和
成长分量在当月合格池内完成 1%/99% 缩尾与百分位秩后，只在既定 Size 桶内
筛选有效 Style 并按 ``(style_score, stock_code)`` 稳定二分，最后在箱内形成
流通市值目标权重。Style 缺失不会反向移动 Size 边界。

五类公开输出均采用固定白名单 schema；m1 中的执行、收益端点、未来字段和
额外因子不会被携带。m3 如需行情或交易状态，必须按
``(signal_date, stock_code)`` 回接 m1 数据合同。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Iterable

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG


KEYS: Final[list[str]] = ["signal_date", "stock_code"]
VALUE_COMPONENTS: Final[tuple[str, ...]] = (
    "book_to_price",
    "earnings_to_price",
    "sales_to_price",
    "dividend_yield",
)
GROWTH_COMPONENTS: Final[tuple[str, ...]] = (
    "revenue_growth_symmetric",
    "net_profit_growth_symmetric",
)
CORE_VALUE_COMPONENTS: Final[tuple[str, ...]] = VALUE_COMPONENTS[:3]
PIT_EVIDENCE_COLUMNS: Final[tuple[str, ...]] = (
    "holding_month",
    "sample_phase",
    "is_eligible",
    "financial_end_date",
    "period_available_date",
    "current_info_publ_date",
    "current_total_operating_revenue",
    "current_net_profit",
    "prior_financial_end_date",
    "prior_info_publ_date",
    "prior_total_operating_revenue",
    "prior_net_profit",
    "prior_fy_financial_end_date",
    "prior_fy_info_publ_date",
    "prior_fy_total_operating_revenue",
    "prior_fy_net_profit",
    "ttm_revenue",
    "ttm_revenue_formula",
    "ttm_net_profit",
    "ttm_net_profit_formula",
    "balance_end_date",
    "balance_period_available_date",
    "balance_info_publ_date",
    "balance_total_shareholder_equity",
    "book_to_price_source_date",
    "earnings_to_price_source_date",
    "sales_to_price_source_date",
    "ttm_income_source_date",
    "dividend_source_date",
    "dividend_age_trading_days",
    "dividend_is_fresh",
    "value_core_component_count",
)
BOX_DEFINITIONS: Final[tuple[tuple[str, str, str], ...]] = (
    ("BV", "Big", "Value"),
    ("BG", "Big", "Growth"),
    ("SV", "Small", "Value"),
    ("SG", "Small", "Growth"),
)
VALUE_WINSORISED_COLUMNS: Final[tuple[str, ...]] = tuple(
    f"{component}_winsorised" for component in VALUE_COMPONENTS
)
VALUE_RANK_COLUMNS: Final[tuple[str, ...]] = tuple(
    f"{component}_rank" for component in VALUE_COMPONENTS
)
GROWTH_WINSORISED_COLUMNS: Final[tuple[str, ...]] = tuple(
    f"{component}_winsorised" for component in GROWTH_COMPONENTS
)
GROWTH_RANK_COLUMNS: Final[tuple[str, ...]] = tuple(
    f"{component}_rank" for component in GROWTH_COMPONENTS
)
FACTOR_BASE_COLUMNS: Final[tuple[str, ...]] = (
    "signal_date",
    "stock_code",
    *PIT_EVIDENCE_COLUMNS,
    "market_value",
    "negotiable_market_value",
    *VALUE_COMPONENTS,
    *GROWTH_COMPONENTS,
    "log_market_value",
    "size_rank",
    "size_signal",
    *VALUE_WINSORISED_COLUMNS,
    *VALUE_RANK_COLUMNS,
    *GROWTH_WINSORISED_COLUMNS,
    *GROWTH_RANK_COLUMNS,
    "value_component_count",
    "growth_component_count",
    "value_score",
    "growth_score",
    "style_score",
    "is_style_valid",
    "weight_market_value",
    "weight_source",
)
FACTOR_GROUP_COLUMNS: Final[tuple[str, ...]] = (
    "size_group",
    "style_group",
    "style_box",
    "size_sort_position",
    "size_bucket_count",
    "small_bucket_count",
    "style_sort_position",
    "style_bucket_count",
    "value_bucket_count",
    "target_weight",
)
FACTOR_OUTPUT_COLUMNS: Final[tuple[str, ...]] = (
    *FACTOR_BASE_COLUMNS,
    *FACTOR_GROUP_COLUMNS,
)
MEMBERSHIP_COLUMNS: Final[tuple[str, ...]] = (
    "signal_date",
    "stock_code",
    "size_group",
    "style_group",
    "style_box",
    "weight_source",
    "target_weight",
    "size_sort_position",
    "size_bucket_count",
    "small_bucket_count",
    "style_sort_position",
    "style_bucket_count",
    "value_bucket_count",
)
MONTHLY_STAT_VALUE_COLUMNS: Final[tuple[str, ...]] = (
    "member_count",
    "weight_sum",
    "weight_hhi",
    "fallback_weight_count",
    "total_weight_market_value",
    "median_market_value",
    "mean_value_score",
    "mean_growth_score",
    "mean_style_score",
    "maximum_target_weight",
    "top_ten_target_weight",
)
MONTHLY_STAT_COLUMNS: Final[tuple[str, ...]] = (
    "signal_date",
    "style_box",
    "size_group",
    "style_group",
    *MONTHLY_STAT_VALUE_COLUMNS,
    "valid_style_size_count",
    "eligible_size_count",
    "size_count_difference",
    "style_count_difference",
)
MISSING_FLAG_COLUMNS: Final[tuple[str, ...]] = (
    *(f"missing_{component}" for component in (*VALUE_COMPONENTS, *GROWTH_COMPONENTS)),
    "insufficient_value_components",
    "insufficient_growth_components",
    "invalid_style",
    "valid_style",
)
MISSINGNESS_COLUMNS: Final[tuple[str, ...]] = (
    "signal_date",
    "eligible_count",
    *MISSING_FLAG_COLUMNS,
    *(f"{column}_rate" for column in MISSING_FLAG_COLUMNS),
)
BOUNDARY_COLUMNS: Final[tuple[str, ...]] = (
    "signal_date",
    "boundary_type",
    "parent_size_group",
    "assigned_side",
    "style_box",
    "stock_code",
    "metric_name",
    "metric_value",
    "sort_position",
    "bucket_count",
    "lower_bucket_count",
    "distance_to_cut",
    "metric_tie_count",
    "stable_rule",
)
FORBIDDEN_OUTPUT_TOKENS: Final[tuple[str, ...]] = (
    "return",
    "future",
    "forward",
    "lead",
    "target",
    "label",
    "momentum",
    "quality",
    "macro",
    "ml",
)
ALLOWED_COMPUTED_TOKEN_COLUMNS: Final[frozenset[str]] = frozenset(
    {"target_weight", "maximum_target_weight", "top_ten_target_weight"}
)


@dataclass(frozen=True)
class StyleBoxSpecification:
    """F11/F12/F16：plan/assumptions 冻结的 m2 参数。"""

    winsor_lower_quantile: float = 0.01
    winsor_upper_quantile: float = 0.99
    minimum_value_components: int = 2
    minimum_growth_components: int = 1
    singleton_percentile_rank: float = 0.5
    invariant_tolerance: float = 1e-12


STYLE_BOX_SPEC: Final[StyleBoxSpecification] = StyleBoxSpecification()


@dataclass(frozen=True)
class M2Dataset:
    """F11/F12/F16：m2 五类信号日产物，不含未来收益。"""

    factor_long: pd.DataFrame
    box_memberships: pd.DataFrame
    monthly_statistics: pd.DataFrame
    missingness_audit: pd.DataFrame
    boundary_audit: pd.DataFrame

    @property
    def pit_style_inputs(self) -> pd.DataFrame:
        """返回全部 eligible 行的 PIT/风格证据契约，不添补行。"""
        return self.factor_long.copy()


def _require_columns(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"m1 月末面板缺少 m2 必需字段: {missing}")


def _assert_exact_schema(
    frame: pd.DataFrame,
    expected_columns: tuple[str, ...],
    output_name: str,
) -> None:
    if list(frame.columns) != list(expected_columns):
        raise AssertionError(
            f"{output_name} 未遵守显式白名单 schema: "
            f"expected={list(expected_columns)}, actual={list(frame.columns)}"
        )
    forbidden = [
        column
        for column in frame.columns
        if column not in ALLOWED_COMPUTED_TOKEN_COLUMNS
        and any(token in column.casefold() for token in FORBIDDEN_OUTPUT_TOKENS)
    ]
    if forbidden:
        raise AssertionError(f"{output_name} 含禁用名称或语义字段: {forbidden}")


def _assert_public_output_schemas(dataset: M2Dataset) -> None:
    """强制五类公开输出只能采用固定白名单，不允许 m1 额外列透传。"""
    schemas = (
        (dataset.factor_long, FACTOR_OUTPUT_COLUMNS, "factor_long"),
        (dataset.box_memberships, MEMBERSHIP_COLUMNS, "box_memberships"),
        (dataset.monthly_statistics, MONTHLY_STAT_COLUMNS, "monthly_statistics"),
        (dataset.missingness_audit, MISSINGNESS_COLUMNS, "missingness_audit"),
        (dataset.boundary_audit, BOUNDARY_COLUMNS, "boundary_audit"),
    )
    for frame, expected_columns, output_name in schemas:
        _assert_exact_schema(frame, expected_columns, output_name)


def _finite_numeric(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    return numeric.where(np.isfinite(numeric))


def _normalised_rank(
    values: pd.Series,
    groups: pd.Series,
    *,
    singleton_rank: float,
) -> pd.Series:
    """按月生成 [0, 1] 平均百分位秩；单股票截面记为中点。"""
    ranked = values.groupby(groups, sort=False).rank(method="average")
    counts = values.groupby(groups, sort=False).transform("count")
    result = (ranked - 1.0).div(counts - 1.0)
    result = result.where(counts.ne(1), singleton_rank)
    return result.where(values.notna())


def _winsorised_rank(
    values: pd.Series,
    groups: pd.Series,
    specification: StyleBoxSpecification,
) -> tuple[pd.Series, pd.Series]:
    """按月 1%/99% 缩尾后生成 [0, 1] 横截面秩。"""
    grouped = values.groupby(groups, sort=False)
    lower = grouped.transform("quantile", q=specification.winsor_lower_quantile)
    upper = grouped.transform("quantile", q=specification.winsor_upper_quantile)
    winsorised = values.clip(lower=lower, upper=upper)
    ranked = _normalised_rank(
        winsorised,
        groups,
        singleton_rank=specification.singleton_percentile_rank,
    )
    return winsorised, ranked


def calculate_style_factors(
    monthly_panel: pd.DataFrame,
    specification: StyleBoxSpecification = STYLE_BOX_SPEC,
) -> pd.DataFrame:
    """F11/F12/F16：计算 Size、Value、Growth、Style 月度因子长表。

    返回 m1 合格池中的全部股票；``is_style_valid`` 标记能进入四箱的有效
    样本。因子计算仅引用 T 日总市值、T 日估值和 m1 的 PIT 增长率；输入中
    任何非白名单列均不会进入返回值。
    """
    required = {
        *KEYS,
        "is_eligible",
        "market_value",
        "negotiable_market_value",
        *VALUE_COMPONENTS,
        *GROWTH_COMPONENTS,
    }
    _require_columns(monthly_panel, required)
    if not 0.0 <= specification.winsor_lower_quantile < specification.winsor_upper_quantile <= 1.0:
        raise ValueError("缩尾分位点必须满足 0 <= lower < upper <= 1")

    factor = monthly_panel.loc[monthly_panel["is_eligible"].fillna(False)].copy()
    if factor.empty:
        raise ValueError("m1 月末面板没有合格股票，无法构造 m2 风格箱")
    factor["signal_date"] = pd.to_datetime(factor["signal_date"], errors="coerce").dt.normalize()
    factor["stock_code"] = factor["stock_code"].astype(str).str.zfill(6)
    if factor[KEYS].isna().any(axis=None) or factor.duplicated(KEYS).any():
        raise ValueError("m1 合格池的 signal_date/stock_code 必须非空且唯一")

    numeric_columns = ["market_value", "negotiable_market_value", *VALUE_COMPONENTS, *GROWTH_COMPONENTS]
    factor[numeric_columns] = factor[numeric_columns].apply(_finite_numeric)
    if factor["market_value"].le(0).any() or factor["market_value"].isna().any():
        raise ValueError("m1 合格池含无效总市值，无法执行 Size 稳定切分")

    factor["log_market_value"] = np.log(factor["market_value"])
    factor["size_rank"] = _normalised_rank(
        factor["log_market_value"],
        factor["signal_date"],
        singleton_rank=specification.singleton_percentile_rank,
    )
    factor["size_signal"] = -factor["size_rank"]

    value_rank_columns: list[str] = []
    for component in VALUE_COMPONENTS:
        winsorised, ranked = _winsorised_rank(
            factor[component], factor["signal_date"], specification
        )
        winsorised_column = f"{component}_winsorised"
        rank_column = f"{component}_rank"
        factor[winsorised_column] = winsorised
        factor[rank_column] = ranked
        value_rank_columns.append(rank_column)

    growth_rank_columns: list[str] = []
    for component in GROWTH_COMPONENTS:
        winsorised, ranked = _winsorised_rank(
            factor[component], factor["signal_date"], specification
        )
        winsorised_column = f"{component}_winsorised"
        rank_column = f"{component}_rank"
        factor[winsorised_column] = winsorised
        factor[rank_column] = ranked
        growth_rank_columns.append(rank_column)

    factor["value_core_component_count"] = factor[list(CORE_VALUE_COMPONENTS)].notna().sum(axis=1)
    factor["value_component_count"] = factor[list(VALUE_COMPONENTS)].notna().sum(axis=1)
    factor["growth_component_count"] = factor[list(GROWTH_COMPONENTS)].notna().sum(axis=1)
    factor["value_score"] = factor[value_rank_columns].mean(axis=1, skipna=True).where(
        factor["value_core_component_count"].ge(specification.minimum_value_components)
    )
    factor["growth_score"] = factor[growth_rank_columns].mean(axis=1, skipna=True).where(
        factor["growth_component_count"].ge(specification.minimum_growth_components)
    )
    factor["style_score"] = factor["growth_score"] - factor["value_score"]
    factor["is_style_valid"] = factor["style_score"].notna()
    factor["weight_market_value"] = factor["negotiable_market_value"].where(
        factor["negotiable_market_value"].gt(0), factor["market_value"]
    )
    factor["weight_source"] = np.where(
        factor["negotiable_market_value"].gt(0),
        "negotiable_market_value",
        "market_value_fallback",
    )
    date_tokens = ("date", "financial_end")
    for column in PIT_EVIDENCE_COLUMNS:
        if column not in factor:
            if column == "is_eligible":
                factor[column] = True
            elif column in ("holding_month", "sample_phase") or column.endswith("formula"):
                factor[column] = pd.NA
            elif any(token in column for token in date_tokens):
                factor[column] = pd.NaT
            elif column == "dividend_is_fresh":
                factor[column] = False
            else:
                factor[column] = np.nan
    # 显式白名单投影是数据隔离边界；禁止把 m1 的收益、端点或额外因子透传。
    return factor.loc[:, list(FACTOR_BASE_COLUMNS)].sort_values(
        KEYS, kind="mergesort"
    ).reset_index(drop=True)


def assign_style_boxes(factor_long: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """F11/F12/F16：先切完整池 Size，再在桶内切 Style 并计算权重。"""
    _require_columns(
        factor_long,
        {
            *KEYS,
            "market_value",
            "weight_market_value",
            "weight_source",
            "value_score",
            "growth_score",
            "style_score",
            "size_signal",
            "is_style_valid",
        },
    )
    # F16 的 Size 边界必须先由完整 eligible 池冻结；Style 缺失不得改变边界。
    factor = factor_long.sort_values(
        ["signal_date", "market_value", "stock_code"], kind="mergesort"
    ).copy()
    factor["size_sort_position"] = factor.groupby("signal_date", sort=False).cumcount()
    factor["size_bucket_count"] = factor.groupby("signal_date", sort=False)[
        "stock_code"
    ].transform("size")
    factor["small_bucket_count"] = factor["size_bucket_count"] // 2
    factor["size_group"] = np.where(
        factor["size_sort_position"].lt(factor["small_bucket_count"]), "Small", "Big"
    )

    factor["style_group"] = pd.Series(pd.NA, index=factor.index, dtype="string")
    factor["style_box"] = pd.Series(pd.NA, index=factor.index, dtype="string")
    for column in ("style_sort_position", "style_bucket_count", "value_bucket_count"):
        factor[column] = pd.Series(pd.NA, index=factor.index, dtype="Int64")
    factor["target_weight"] = np.nan

    valid = factor.loc[factor["is_style_valid"]].copy()
    style_assignment_columns = [
        "style_group",
        "style_box",
        "style_sort_position",
        "style_bucket_count",
        "value_bucket_count",
        "target_weight",
    ]
    if valid.empty:
        factor = factor.loc[:, list(FACTOR_OUTPUT_COLUMNS)].sort_values(
            KEYS, kind="mergesort"
        ).reset_index(drop=True)
        memberships = factor.loc[
            factor["is_style_valid"], list(MEMBERSHIP_COLUMNS)
        ].copy()
        return factor, memberships

    valid = valid.sort_values(
        ["signal_date", "size_group", "style_score", "stock_code"], kind="mergesort"
    )
    style_keys = ["signal_date", "size_group"]
    valid["style_sort_position"] = valid.groupby(style_keys, sort=False).cumcount()
    valid["style_bucket_count"] = valid.groupby(style_keys, sort=False)["stock_code"].transform("size")
    valid["value_bucket_count"] = valid["style_bucket_count"] // 2
    valid["style_group"] = np.where(
        valid["style_sort_position"].lt(valid["value_bucket_count"]), "Value", "Growth"
    )
    valid["style_box"] = valid["size_group"].str[0] + valid["style_group"].str[0]
    weight_keys = ["signal_date", "style_box"]
    weight_totals = valid.groupby(weight_keys, sort=False)["weight_market_value"].transform("sum")
    valid["target_weight"] = valid["weight_market_value"] / weight_totals

    factor = factor.drop(columns=style_assignment_columns).merge(
        valid[[*KEYS, *style_assignment_columns]],
        on=KEYS,
        how="left",
        validate="one_to_one",
    )
    factor = factor.loc[:, list(FACTOR_OUTPUT_COLUMNS)]
    memberships = factor.loc[factor["is_style_valid"], list(MEMBERSHIP_COLUMNS)].sort_values(
        ["signal_date", "style_box", "target_weight", "stock_code"],
        ascending=[True, True, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return factor.sort_values(KEYS, kind="mergesort").reset_index(drop=True), memberships


def _build_monthly_statistics(
    factor_long: pd.DataFrame,
    box_memberships: pd.DataFrame,
) -> pd.DataFrame:
    """F11/F12/F16 内部产物：四箱逐月统计与完整池 Size 计数。"""
    month_meta = factor_long[["signal_date"]].drop_duplicates("signal_date")
    box_meta = pd.DataFrame(
        BOX_DEFINITIONS, columns=["style_box", "size_group", "style_group"]
    )
    grid = month_meta.assign(_join_key=1).merge(
        box_meta.assign(_join_key=1), on="_join_key", how="inner"
    ).drop(columns="_join_key")

    if box_memberships.empty:
        statistics = pd.DataFrame(
            columns=["signal_date", "style_box", *MONTHLY_STAT_VALUE_COLUMNS]
        )
    else:
        members = factor_long.loc[factor_long["is_style_valid"]].assign(
            weight_squared=lambda x: x["target_weight"].pow(2),
            uses_market_value_fallback=lambda x: x["weight_source"].eq(
                "market_value_fallback"
            ),
        )
        statistics = (
            members.groupby(["signal_date", "style_box"], as_index=False, sort=False)
            .agg(
                member_count=("stock_code", "size"),
                weight_sum=("target_weight", "sum"),
                weight_hhi=("weight_squared", "sum"),
                fallback_weight_count=("uses_market_value_fallback", "sum"),
                total_weight_market_value=("weight_market_value", "sum"),
                median_market_value=("market_value", "median"),
                mean_value_score=("value_score", "mean"),
                mean_growth_score=("growth_score", "mean"),
                mean_style_score=("style_score", "mean"),
                maximum_target_weight=("target_weight", "max"),
            )
        )
        top_ten = (
            members.sort_values(
                ["signal_date", "style_box", "target_weight", "stock_code"],
                ascending=[True, True, False, True],
                kind="mergesort",
            )
            .groupby(["signal_date", "style_box"], sort=False)
            .head(10)
            .groupby(["signal_date", "style_box"], as_index=False)["target_weight"]
            .sum()
            .rename(columns={"target_weight": "top_ten_target_weight"})
        )
        statistics = statistics.merge(
            top_ten,
            on=["signal_date", "style_box"],
            how="left",
            validate="one_to_one",
        )
    result = grid.merge(statistics, on=["signal_date", "style_box"], how="left")
    zero_columns = [
        "member_count",
        "weight_sum",
        "weight_hhi",
        "fallback_weight_count",
        "total_weight_market_value",
    ]
    result[zero_columns] = result[zero_columns].fillna(0)
    result[["member_count", "fallback_weight_count"]] = result[
        ["member_count", "fallback_weight_count"]
    ].astype(int)
    result["valid_style_size_count"] = result.groupby(
        ["signal_date", "size_group"], sort=False
    )["member_count"].transform("sum")
    eligible_size = (
        factor_long.groupby(["signal_date", "size_group"], as_index=False, sort=False)
        .size()
        .rename(columns={"size": "eligible_size_count"})
    )
    result = result.merge(eligible_size, on=["signal_date", "size_group"], how="left")
    result["eligible_size_count"] = result["eligible_size_count"].fillna(0).astype(int)
    size_counts = factor_long.pivot_table(
        index="signal_date",
        columns="size_group",
        values="stock_code",
        aggfunc="size",
        fill_value=0,
    )
    result = result.merge(
        size_counts.reindex(columns=["Big", "Small"], fill_value=0)
        .assign(size_count_difference=lambda x: (x["Big"] - x["Small"]).abs())
        [["size_count_difference"]]
        .reset_index(),
        on="signal_date",
        how="left",
    )
    result["style_count_difference"] = result.groupby(
        ["signal_date", "size_group"], sort=False
    )["member_count"].transform(lambda x: x.max() - x.min())
    return result.loc[:, list(MONTHLY_STAT_COLUMNS)].sort_values(
        ["signal_date", "style_box"], kind="mergesort"
    ).reset_index(drop=True)


def _build_missingness_audit(factor_long: pd.DataFrame) -> pd.DataFrame:
    """F11/F12 内部产物：六分量缺失、阈值不足和有效样本比例。"""
    metadata = ["signal_date"]
    flags = pd.DataFrame(index=factor_long.index)
    for component in (*VALUE_COMPONENTS, *GROWTH_COMPONENTS):
        flags[f"missing_{component}"] = factor_long[component].isna()
    flags["insufficient_value_components"] = factor_long["value_score"].isna()
    flags["insufficient_growth_components"] = factor_long["growth_score"].isna()
    flags["invalid_style"] = ~factor_long["is_style_valid"]
    flags["valid_style"] = factor_long["is_style_valid"]

    audit_base = pd.concat([factor_long[metadata], flags], axis=1)
    flag_columns = list(flags.columns)
    counts = audit_base.groupby(metadata, as_index=False, sort=False)[flag_columns].sum()
    eligible = (
        audit_base.groupby(metadata, as_index=False, sort=False)
        .size()
        .rename(columns={"size": "eligible_count"})
    )
    result = eligible.merge(counts, on=metadata, how="left", validate="one_to_one")
    rates = result[flag_columns].div(result["eligible_count"], axis=0).add_suffix("_rate")
    return pd.concat([result, rates], axis=1).loc[
        :, list(MISSINGNESS_COLUMNS)
    ].sort_values("signal_date").reset_index(drop=True)


def _build_boundary_audit(
    factor_long: pd.DataFrame,
    box_memberships: pd.DataFrame,
) -> pd.DataFrame:
    """F11/F12/F16 内部产物：完整池 Size 与桶内 Style 边界样本。"""
    columns = list(BOUNDARY_COLUMNS)
    if factor_long.empty:
        return pd.DataFrame(columns=columns)

    factors = factor_long.copy()
    size_tie_count = factors.groupby(
        ["signal_date", "market_value"], sort=False
    )["stock_code"].transform("size")
    size_mask = factors["size_sort_position"].eq(factors["small_bucket_count"] - 1) | factors[
        "size_sort_position"
    ].eq(factors["small_bucket_count"])
    size_boundary = factors.loc[size_mask].assign(
        boundary_type="size_split",
        parent_size_group=pd.NA,
        assigned_side=lambda x: x["size_group"],
        metric_name="market_value",
        metric_value=lambda x: x["market_value"],
        sort_position=lambda x: x["size_sort_position"],
        bucket_count=lambda x: x["size_bucket_count"],
        lower_bucket_count=lambda x: x["small_bucket_count"],
        distance_to_cut=lambda x: x["size_sort_position"] - x["small_bucket_count"] + 0.5,
        metric_tie_count=size_tie_count.loc[size_mask].to_numpy(),
        stable_rule="ascending(market_value,stock_code); lower=Small",
    )

    style_members = factor_long.loc[factor_long["is_style_valid"]]
    if box_memberships.empty:
        style_boundary = pd.DataFrame(columns=columns)
    else:
        members = style_members.copy()
        style_tie_count = members.groupby(
            ["signal_date", "size_group", "style_score"], sort=False
        )["stock_code"].transform("size")
        style_mask = members["style_sort_position"].eq(
            members["value_bucket_count"] - 1
        ) | members["style_sort_position"].eq(members["value_bucket_count"])
        style_boundary = members.loc[style_mask].assign(
            boundary_type="style_split",
            parent_size_group=lambda x: x["size_group"],
            assigned_side=lambda x: x["style_group"],
            metric_name="style_score",
            metric_value=lambda x: x["style_score"],
            sort_position=lambda x: x["style_sort_position"],
            bucket_count=lambda x: x["style_bucket_count"],
            lower_bucket_count=lambda x: x["value_bucket_count"],
            distance_to_cut=lambda x: x["style_sort_position"]
            - x["value_bucket_count"]
            + 0.5,
            metric_tie_count=style_tie_count.loc[style_mask].to_numpy(),
            stable_rule="ascending(style_score,stock_code); lower=Value",
        )
    return pd.concat([size_boundary[columns], style_boundary[columns]], ignore_index=True).sort_values(
        ["signal_date", "boundary_type", "parent_size_group", "sort_position", "stock_code"],
        kind="mergesort",
        na_position="first",
    ).reset_index(drop=True)


def _assert_direction_contract(factor_long: pd.DataFrame) -> None:
    """F11/F12/F16 内部断言：连续 Size 与 Style 方向。"""
    expected_style = factor_long["growth_score"] - factor_long["value_score"]
    valid_style = factor_long["is_style_valid"]
    if not np.allclose(
        factor_long.loc[valid_style, "style_score"],
        expected_style.loc[valid_style],
        equal_nan=False,
    ):
        raise AssertionError("Style 必须严格等于 Growth-Value")

    ordered = factor_long.sort_values(
        ["signal_date", "market_value", "stock_code"], kind="mergesort"
    )
    size_diff = ordered.groupby("signal_date", sort=False)["size_signal"].diff()
    market_diff = ordered.groupby("signal_date", sort=False)["market_value"].diff()
    if size_diff.loc[market_diff.gt(0)].gt(0).any():
        raise AssertionError("连续 Size 信号方向错误：市值变大时信号不得上升")


def assert_m2_invariants(
    dataset: M2Dataset,
    specification: StyleBoxSpecification = STYLE_BOX_SPEC,
) -> None:
    """F11/F12/F16：独立重算分数语义、稳定分箱与流通市值权重。"""
    factors = dataset.factor_long
    members = dataset.box_memberships
    _assert_public_output_schemas(dataset)
    if factors.empty:
        raise AssertionError("m2 因子长表为空")
    _require_columns(
        factors,
        {
            *KEYS,
            "market_value",
            "negotiable_market_value",
            "size_group",
            "style_group",
            "style_box",
            "size_sort_position",
            "size_bucket_count",
            "small_bucket_count",
            "style_sort_position",
            "style_bucket_count",
            "value_bucket_count",
            "weight_market_value",
            "weight_source",
            "target_weight",
            "value_score",
            "growth_score",
            "style_score",
            "is_style_valid",
        },
    )
    if list(members.columns) != list(MEMBERSHIP_COLUMNS):
        raise AssertionError("四箱成员表未使用统一 MEMBERSHIP_COLUMNS schema")
    if factors.duplicated(KEYS).any() or members.duplicated(KEYS).any():
        raise AssertionError("每只股票每月最多只能出现一次并进入一个风格箱")

    # 独立重算 F16：完整 eligible 池先按 (market_value, stock_code) 切 Size。
    expected_size = factors[[*KEYS, "market_value"]].sort_values(
        ["signal_date", "market_value", "stock_code"], kind="mergesort"
    )
    expected_size["size_sort_position"] = expected_size.groupby(
        "signal_date", sort=False
    ).cumcount()
    expected_size["size_bucket_count"] = expected_size.groupby(
        "signal_date", sort=False
    )["stock_code"].transform("size")
    expected_size["small_bucket_count"] = expected_size["size_bucket_count"] // 2
    expected_size["size_group"] = np.where(
        expected_size["size_sort_position"].lt(expected_size["small_bucket_count"]),
        "Small",
        "Big",
    )
    size_comparison = expected_size.merge(
        factors[
            [
                *KEYS,
                "size_group",
                "size_sort_position",
                "size_bucket_count",
                "small_bucket_count",
            ]
        ],
        on=KEYS,
        how="left",
        validate="one_to_one",
        suffixes=("_expected", "_actual"),
    )
    if not size_comparison["size_group_expected"].eq(
        size_comparison["size_group_actual"]
    ).all():
        raise AssertionError("Size 标签不是由完整 eligible 池稳定切分得到")
    for column in ("size_sort_position", "size_bucket_count", "small_bucket_count"):
        expected_values = pd.to_numeric(
            size_comparison[f"{column}_expected"], errors="coerce"
        ).to_numpy(dtype=float)
        actual_values = pd.to_numeric(
            size_comparison[f"{column}_actual"], errors="coerce"
        ).to_numpy(dtype=float)
        if not np.array_equal(expected_values, actual_values):
            raise AssertionError(f"{column} 与稳定 Size 重算不一致")
    size_counts = expected_size.pivot_table(
        index="signal_date",
        columns="size_group",
        values="stock_code",
        aggfunc="size",
        fill_value=0,
    ).reindex(columns=["Big", "Small"], fill_value=0)
    if (size_counts["Big"] - size_counts["Small"]).abs().gt(1).any():
        raise AssertionError("完整 eligible 池的 Big/Small 数量差超过 1")

    # 独立重算 F11/F12：Style=Growth-Value，缺失只影响桶内 Style，不动 Size。
    expected_style_score = factors["growth_score"] - factors["value_score"]
    expected_valid = expected_style_score.notna()
    if not factors["is_style_valid"].eq(expected_valid).all():
        raise AssertionError("is_style_valid 与 Growth/Value 有效性不一致")
    if not np.allclose(
        pd.to_numeric(factors["style_score"], errors="coerce").to_numpy(dtype=float),
        expected_style_score.to_numpy(dtype=float),
        rtol=specification.invariant_tolerance,
        atol=specification.invariant_tolerance,
        equal_nan=True,
    ):
        raise AssertionError("Style 必须逐行严格等于 Growth-Value")

    expected_members = (
        factors.loc[
            expected_valid,
            [
                *KEYS,
                "market_value",
                "negotiable_market_value",
                "value_score",
                "growth_score",
                "style_score",
            ],
        ]
        .merge(expected_size[[*KEYS, "size_group"]], on=KEYS, validate="one_to_one")
        .sort_values(
            ["signal_date", "size_group", "style_score", "stock_code"],
            kind="mergesort",
        )
    )
    style_keys = ["signal_date", "size_group"]
    expected_members["style_sort_position"] = expected_members.groupby(
        style_keys, sort=False
    ).cumcount()
    expected_members["style_bucket_count"] = expected_members.groupby(
        style_keys, sort=False
    )["stock_code"].transform("size")
    expected_members["value_bucket_count"] = expected_members["style_bucket_count"] // 2
    expected_members["style_group"] = np.where(
        expected_members["style_sort_position"].lt(
            expected_members["value_bucket_count"]
        ),
        "Value",
        "Growth",
    )
    expected_members = expected_members.merge(
        pd.DataFrame(
            BOX_DEFINITIONS, columns=["style_box", "size_group", "style_group"]
        ),
        on=["size_group", "style_group"],
        how="left",
        validate="many_to_one",
    )
    expected_members["weight_market_value"] = expected_members[
        "negotiable_market_value"
    ].where(
        expected_members["negotiable_market_value"].gt(0),
        expected_members["market_value"],
    )
    expected_members["weight_source"] = np.where(
        expected_members["negotiable_market_value"].gt(0),
        "negotiable_market_value",
        "market_value_fallback",
    )
    expected_weight_total = expected_members.groupby(
        ["signal_date", "style_box"], sort=False
    )["weight_market_value"].transform("sum")
    expected_members["target_weight"] = (
        expected_members["weight_market_value"] / expected_weight_total
    )

    expected_keys = expected_members[KEYS].sort_values(KEYS).reset_index(drop=True)
    actual_keys = members[KEYS].sort_values(KEYS).reset_index(drop=True)
    if not expected_keys.equals(actual_keys):
        raise AssertionError("四箱并集不等于既定 Size 桶内的有效 Style 样本")

    membership_semantic_columns = [
        "size_group",
        "style_group",
        "style_box",
        "style_sort_position",
        "style_bucket_count",
        "value_bucket_count",
        "weight_source",
        "target_weight",
    ]
    if expected_members.empty:
        invalid = ~expected_valid
        nullable_columns = [
            "style_group",
            "style_box",
            "style_sort_position",
            "style_bucket_count",
            "value_bucket_count",
            "target_weight",
        ]
        if factors.loc[invalid, nullable_columns].notna().any(axis=None):
            raise AssertionError("Style 无效股票不应带 Style 标签、位置或目标权重")
    else:
        member_comparison = expected_members[
            [*KEYS, *membership_semantic_columns]
        ].merge(
            members[[*KEYS, *membership_semantic_columns]],
            on=KEYS,
            how="left",
            validate="one_to_one",
            suffixes=("_expected", "_actual"),
        )
        factor_semantic_columns = [*membership_semantic_columns, "weight_market_value"]
        factor_comparison = expected_members[[*KEYS, *factor_semantic_columns]].merge(
            factors.loc[expected_valid, [*KEYS, *factor_semantic_columns]],
            on=KEYS,
            how="left",
            validate="one_to_one",
            suffixes=("_expected", "_actual"),
        )
        for comparison, source_name, numeric_columns in (
            (
                member_comparison,
                "四箱成员表",
                (
                    "style_sort_position",
                    "style_bucket_count",
                    "value_bucket_count",
                    "target_weight",
                ),
            ),
            (
                factor_comparison,
                "因子长表",
                (
                    "style_sort_position",
                    "style_bucket_count",
                    "value_bucket_count",
                    "weight_market_value",
                    "target_weight",
                ),
            ),
        ):
            for column in ("size_group", "style_group", "style_box", "weight_source"):
                if not comparison[f"{column}_expected"].eq(
                    comparison[f"{column}_actual"]
                ).all():
                    raise AssertionError(f"{source_name}的 {column} 语义重算不一致")
            for column in numeric_columns:
                expected_values = pd.to_numeric(
                    comparison[f"{column}_expected"], errors="coerce"
                ).to_numpy(dtype=float)
                actual_values = pd.to_numeric(
                    comparison[f"{column}_actual"], errors="coerce"
                ).to_numpy(dtype=float)
                if not np.allclose(
                    expected_values,
                    actual_values,
                    rtol=specification.invariant_tolerance,
                    atol=specification.invariant_tolerance,
                    equal_nan=False,
                ):
                    raise AssertionError(f"{source_name}的 {column} 独立重算不一致")

        invalid = ~expected_valid
        if factors.loc[
            invalid,
            [
                "style_group",
                "style_box",
                "style_sort_position",
                "style_bucket_count",
                "value_bucket_count",
                "target_weight",
            ],
        ].notna().any(axis=None):
            raise AssertionError("Style 无效股票不应带 Style 标签、位置或目标权重")

    style_counts = expected_members.pivot_table(
        index=["signal_date", "size_group"],
        columns="style_group",
        values="stock_code",
        aggfunc="size",
        fill_value=0,
    ).reindex(columns=["Growth", "Value"], fill_value=0)
    if not style_counts.empty and (
        style_counts["Growth"] - style_counts["Value"]
    ).abs().gt(1).any():
        raise AssertionError("既定 Size 桶内 Growth/Value 数量差超过 1")

    statistics = dataset.monthly_statistics
    _require_columns(
        statistics,
        {
            "signal_date",
            "style_box",
            "member_count",
            "eligible_size_count",
            "valid_style_size_count",
        },
    )
    expected_stat_rows = factors["signal_date"].nunique() * len(BOX_DEFINITIONS)
    if len(statistics) != expected_stat_rows or statistics.duplicated(
        ["signal_date", "style_box"]
    ).any():
        raise AssertionError("月度统计必须为每月固定四箱 schema")
    statistic_member_count = statistics.groupby("signal_date")["member_count"].sum()
    expected_member_count = factors.groupby("signal_date")["is_style_valid"].sum()
    if not statistic_member_count.reindex(expected_member_count.index).eq(
        expected_member_count
    ).all():
        raise AssertionError("月度统计成员数与有效 Style 样本不一致")

    missingness = dataset.missingness_audit
    _require_columns(
        missingness,
        {"signal_date", "eligible_count", "valid_style", "invalid_style"},
    )
    if len(missingness) != factors["signal_date"].nunique():
        raise AssertionError("缺失审计必须每月恰有一行")

    for column in (
        "current_info_publ_date",
        "prior_info_publ_date",
        "prior_fy_info_publ_date",
        "balance_info_publ_date",
        "book_to_price_source_date",
        "earnings_to_price_source_date",
        "sales_to_price_source_date",
        "dividend_source_date",
    ):
        if column in factors:
            publication_dates = pd.to_datetime(factors[column], errors="coerce")
            known = publication_dates.notna()
            if publication_dates.loc[known].gt(factors.loc[known, "signal_date"]).any():
                raise AssertionError(f"{column} 晚于信号日，存在财务前视")
    if not factors["value_score"].notna().le(
        factors["value_core_component_count"].ge(
            DEFAULT_CONFIG.minimum_core_value_components
        )
    ).all():
        raise AssertionError("Value 不得在 B/P、E/P、S/P 核心项少于2项时有效")

    # 只在正式 33 月完整出现时启动不可放宽的覆盖/集中度门禁；
    # 有界 smoke fixture 仍执行上述逐行公式与前视检查。
    formal = factors.loc[factors["sample_phase"].eq("formal_oos")].copy()
    expected_formal_months = len(
        pd.period_range(DEFAULT_CONFIG.oos_start, DEFAULT_CONFIG.oos_end, freq="M")
    )
    if formal["signal_date"].nunique() == expected_formal_months:
        coverage = formal.groupby("signal_date", sort=True)["is_style_valid"].mean()
        if coverage.lt(DEFAULT_CONFIG.minimum_style_coverage).any():
            failed = coverage.loc[coverage.lt(DEFAULT_CONFIG.minimum_style_coverage)]
            raise AssertionError(f"正式OOS Style覆盖低于95%: {failed.to_dict()}")
        if coverage.diff().abs().dropna().gt(
            DEFAULT_CONFIG.maximum_style_coverage_jump + DEFAULT_CONFIG.numeric_tolerance
        ).any():
            raise AssertionError("正式OOS Style月覆盖跳变超过5个百分点")
        stable = coverage.ge(DEFAULT_CONFIG.stable_style_coverage)
        stable_runs = stable.groupby(stable.ne(stable.shift()).cumsum()).sum()
        if stable_runs.max() < DEFAULT_CONFIG.minimum_stable_style_months:
            raise AssertionError("正式OOS没有连续24月Style覆盖达到97%")
        formal_dates = set(formal["signal_date"])
        formal_stats = statistics.loc[statistics["signal_date"].isin(formal_dates)].copy()
        eligible_counts = formal.groupby("signal_date")["stock_code"].size()
        required_members = (
            eligible_counts.mul(DEFAULT_CONFIG.minimum_box_share_of_eligible)
            .map(np.ceil)
            .clip(lower=DEFAULT_CONFIG.minimum_box_members)
            .astype(int)
        )
        formal_stats["required_member_count"] = formal_stats["signal_date"].map(
            required_members
        )
        if formal_stats["member_count"].lt(formal_stats["required_member_count"]).any():
            raise AssertionError("正式OOS四箱成员数低于max(100,eligible×10%)")
        if formal_stats["maximum_target_weight"].gt(
            DEFAULT_CONFIG.maximum_single_stock_weight + DEFAULT_CONFIG.weight_tolerance
        ).any():
            raise AssertionError("正式OOS四箱单股目标权重超过10%")
        if formal_stats["top_ten_target_weight"].gt(
            DEFAULT_CONFIG.maximum_top_ten_weight + DEFAULT_CONFIG.weight_tolerance
        ).any():
            raise AssertionError("正式OOS四箱前十大目标权重超过50%")
    _assert_direction_contract(factors)


def build_m2_dataset(
    monthly_panel: pd.DataFrame,
    specification: StyleBoxSpecification = STYLE_BOX_SPEC,
) -> M2Dataset:
    """F11/F12/F16：构造完整 m2 合同；不读未来收益、不运行回测。"""
    factors = calculate_style_factors(monthly_panel, specification)
    factors, memberships = assign_style_boxes(factors)
    dataset = M2Dataset(
        factor_long=factors,
        box_memberships=memberships,
        monthly_statistics=_build_monthly_statistics(factors, memberships),
        missingness_audit=_build_missingness_audit(factors),
        boundary_audit=_build_boundary_audit(factors, memberships),
    )
    assert_m2_invariants(dataset)
    return dataset


__all__ = [
    "StyleBoxSpecification",
    "STYLE_BOX_SPEC",
    "M2Dataset",
    "calculate_style_factors",
    "assign_style_boxes",
    "assert_m2_invariants",
    "build_m2_dataset",
]
