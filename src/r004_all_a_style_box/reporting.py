"""m4：正式 OOS 统计、图表和可追溯工作簿数据合同。

本模块只消费 m1--m3 已冻结的结构化结果，不改变股票池、因子、组合、交易成本
或样本边界。所有统计限定 ``sample_phase=formal_oos``；原研报美国数值只作为
背景登记，绝不参与中国市场实验的通过/失败判断。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from common.backtest import calculate_ic, calculate_rank_ic
from common.utils import (
    calculate_annualized_return,
    calculate_annualized_volatility,
    calculate_max_drawdown,
    calculate_win_rate,
)

from .config import AllAStyleBoxConfig, DEFAULT_CONFIG
from .data_pipeline import M1Dataset
from .portfolio import FACTOR_NAMES, LONG_PORTFOLIOS, STYLE_BOXES, M3Dataset
from .strategy import (
    CORE_VALUE_COMPONENTS,
    GROWTH_COMPONENTS,
    STYLE_BOX_SPEC,
    VALUE_COMPONENTS,
    M2Dataset,
)


REPORT_ID: Final[str] = "r004_all_a_style_box"
PRIMARY_BLUE: Final[str] = "#1f77b4"
PRIMARY_RED: Final[str] = "#d62728"
HEATMAP_PALETTE: Final[str] = "RdBu_r"
ENTITY_ORDER: Final[tuple[str, ...]] = (*STYLE_BOXES, "SMB", "HML", "GML", "ALL_A", "STYLE_1N")
FORBIDDEN_SCOPE_TOKENS: Final[tuple[str, ...]] = (
    "momentum",
    "quality",
    "macro",
    "kmeans",
    "stacking",
    "smote",
    "random_forest",
)
MAX_DRAWDOWN_AUDIT_DEFINITION: Final[str] = (
    "最大回撤显式包含调仓前期初净值1.0作为首个峰值；负首期不能被遗漏"
)
PIT_STYLE_INPUTS_TABLE: Final[str] = "pit_style_inputs"
SECURITY_EVENT_AUDIT_TABLE: Final[str] = "security_event_audit"
WORKBOOK_DETAIL_VIEW_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "trades": (
        "date",
        "signal_date",
        "holding_month",
        "portfolio",
        "stock_code",
        "side",
        "shares",
        "vwap",
        "gross_notional",
        "commission_cost",
        "slippage_cost",
        "stamp_tax",
        "total_cost",
    ),
    "unfilled_orders": (
        "date",
        "signal_date",
        "holding_month",
        "portfolio",
        "stock_code",
        "side",
        "requested_shares",
        "filled_shares",
        "unfilled_shares",
        "reference_price",
        "unfilled_notional",
        "reason",
    ),
}
WORKBOOK_SHEET_PROJECTION_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "TradesTop200": WORKBOOK_DETAIL_VIEW_COLUMNS["trades"],
    "UnfilledTop200": WORKBOOK_DETAIL_VIEW_COLUMNS["unfilled_orders"],
}
EXPECTED_DETAIL_TABLE_COUNT: Final[int] = 12
EXPECTED_ASSUMPTION_COUNT: Final[int] = 24
EXPECTED_CHECK_COUNT: Final[int] = 7
EXPECTED_ASSUMPTION_IDS: Final[tuple[str, ...]] = tuple(
    f"AS{index}" for index in range(1, EXPECTED_ASSUMPTION_COUNT + 1)
)
REQUIRED_ASSUMPTION_FIELDS: Final[tuple[str, ...]] = (
    "assumption_id",
    "title",
    "来源",
    "假设内容",
    "行业惯例依据",
    "影响面",
    "影响 milestone",
    "影响指标",
    "预期影响",
    "验证后回看",
    "状态",
    "高亮等级",
)
ASSUMPTION_PLACEHOLDER_TOKENS: Final[tuple[str, ...]] = (
    "verify 后填",
    "pending",
    "待填",
    "待补",
    "todo",
    "tbd",
    "占位",
    "未填写",
)
RETURN_LAYER_SEMANTICS: Final[dict[str, str]] = {
    "target_reference_return": (
        "月度目标组合参考收益可用；日频目标参考收益不可用，不能用实际成本前收益代替"
    ),
    "actual_before_cost_return": "受中国可交易约束后的实际持仓成本前收益",
    "actual_after_cost_net_return": "同一实际持仓扣除交易成本后的净收益",
}
def build_boundary_disclosures(
    config: AllAStyleBoxConfig,
    terminal_accounting_date: pd.Timestamp,
) -> tuple[tuple[str, str], ...]:
    """由本次运行配置与实际末期记账日生成唯一边界披露。"""
    start = pd.Period(config.oos_start, freq="M")
    end = pd.Period(config.oos_end, freq="M")
    if end < start:
        raise ValueError("OOS截止月不得早于起始月")
    terminal = pd.Timestamp(terminal_accounting_date).normalize()
    if pd.isna(terminal):
        raise ValueError("末期记账日不能为空")
    n_months = len(pd.period_range(start, end, freq="M"))
    return (
        ("experimental_china_transplant", "实验性中国市场迁移，不与美国原值作数值等价比较"),
        (
            "oos_months",
            f"样本外仅{start}至{end}共{n_months}个持有月，不代表长期稳定性",
        ),
        ("beijing_exchange_included", "动态全A包含当期可交易北交所证券"),
        (
            "security_lifecycle_boundary",
            "证券生命周期只按当日及此前可核对证据估值；risk_exit只触发退出行为，"
            "退市转板仅允许在官方45交易日窗口内沿用旧mark，并在映射公开生效日按冻结真实行情退出；"
            "无可审计估值路径的超期资产进入unpriced并阻断完整NAV结论",
        ),
        ("trading_constraints_and_costs", "结果包含涨跌停、停牌、成交约束及中国市场交易成本"),
        (
            "terminal_accounting_date",
            f"{end}持有期记账至{terminal.date()}，仅为收益端点，不扩展OOS信号信息集",
        ),
        ("not_investment_advice", "本实验不构成投资建议"),
    )


BOUNDARY_DISCLOSURE_IDS: Final[tuple[str, ...]] = (
    "experimental_china_transplant",
    "oos_months",
    "beijing_exchange_included",
    "security_lifecycle_boundary",
    "trading_constraints_and_costs",
    "terminal_accounting_date",
    "not_investment_advice",
)


@dataclass(frozen=True)
class ReportingSpecification:
    """m4 输出与统计口径；不承载或覆盖任何策略参数。

    ``performance_initial_nav=1.0`` 是净值审计语义：最大回撤必须包含调仓前
    的期初财富1.0，避免负首期被从峰值序列中遗漏。
    """

    daily_periods_per_year: int = 252
    monthly_periods_per_year: int = 12
    quantile_count: int = 5
    decay_horizons: tuple[int, ...] = (1, 2, 3)
    rolling_ic_months: int = 6
    minimum_ic_observations: int = 5
    holdings_view_rows_per_group: int = 100
    trading_view_rows_per_group: int = 200
    ic_observations_view_rows_per_group: int = 100
    workbook_payload_max_bytes: int = 128 * 1024 * 1024
    detail_parquet_compression: str = "zstd"
    ic_histogram_min_bins: int = 5
    ic_histogram_max_bins: int = 12
    ic_histogram_observations_per_bin: int = 2
    normal_fit_minimum_observations: int = 2
    normal_fit_grid_points: int = 200
    normal_fit_std_tolerance: float = 1e-12
    common_regression_tolerance: float = 1e-12
    performance_initial_nav: float = 1.0
    chart_dpi: int = 300
    time_series_figure_size: tuple[float, float] = (12.0, 6.0)
    bar_figure_size: tuple[float, float] = (10.0, 6.0)

    def __post_init__(self) -> None:
        if self.daily_periods_per_year <= 0 or self.monthly_periods_per_year <= 0:
            raise ValueError("年化期数必须为正整数")
        if self.quantile_count < 2:
            raise ValueError("分组诊断至少需要两个分位组")
        if not self.decay_horizons or min(self.decay_horizons) <= 0:
            raise ValueError("衰减期数必须为正整数")
        if tuple(sorted(set(self.decay_horizons))) != self.decay_horizons:
            raise ValueError("衰减期数必须严格递增且不重复")
        if self.minimum_ic_observations != 5:
            raise ValueError("截面IC最少观测数须与common.backtest统一为5")
        if min(
            self.holdings_view_rows_per_group,
            self.trading_view_rows_per_group,
            self.ic_observations_view_rows_per_group,
            self.workbook_payload_max_bytes,
        ) <= 0:
            raise ValueError("明细视图行数与工作簿payload上限必须为正")
        if not self.detail_parquet_compression:
            raise ValueError("Parquet压缩算法不能为空")
        if not (
            1 <= self.ic_histogram_min_bins <= self.ic_histogram_max_bins
            and self.ic_histogram_observations_per_bin > 0
            and self.normal_fit_minimum_observations >= 2
            and self.normal_fit_grid_points >= 2
            and self.normal_fit_std_tolerance > 0
            and self.common_regression_tolerance > 0
        ):
            raise ValueError("IC分布图参数无效")
        if self.chart_dpi != 300:
            raise ValueError("AGENTS.md 要求正式 PNG 固定为 300 DPI")
        if self.performance_initial_nav != 1.0:
            raise ValueError("最大回撤审计要求调仓前期初净值固定为1.0")


DEFAULT_REPORTING_SPEC: Final[ReportingSpecification] = ReportingSpecification()


@dataclass(frozen=True)
class M4Dataset:
    """R4/R7/R10/SA4 的纯数据结果合同。"""

    return_series: pd.DataFrame
    performance_summary: pd.DataFrame
    correlation_matrix: pd.DataFrame
    winner_months: pd.DataFrame
    winner_frequency: pd.DataFrame
    ic_observations: pd.DataFrame
    ic_series: pd.DataFrame
    ic_summary: pd.DataFrame
    quantile_returns: pd.DataFrame
    monotonicity: pd.DataFrame
    decay_analysis: pd.DataFrame
    turnover_cost: pd.DataFrame
    coverage_summary: pd.DataFrame
    benchmark_comparison: pd.DataFrame
    checks: pd.DataFrame
    sources: pd.DataFrame


def _require_columns(frame: pd.DataFrame, columns: Iterable[str], source: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{source} 缺少 m4 必需字段: {missing}")


def _finite_numeric(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").astype(float)
    return numeric.where(np.isfinite(numeric))


def _formal(frame: pd.DataFrame, source: str) -> pd.DataFrame:
    if "sample_phase" not in frame:
        raise ValueError(f"{source} 缺少 sample_phase，不能证明正式 OOS 边界")
    result = frame.loc[frame["sample_phase"].eq("formal_oos")].copy()
    if result.empty:
        raise ValueError(f"{source} 没有 formal_oos 记录")
    return result.reset_index(drop=True)


def _normalised_nav(returns: pd.Series) -> pd.Series:
    values = _finite_numeric(returns)
    if values.isna().any():
        raise ValueError("收益序列包含缺失或非有限值，不能构造净值")
    if values.le(-1.0).any():
        raise ValueError("收益小于等于 -100%，不能按复利构造净值")
    return (1.0 + values).cumprod()


def build_return_series(
    m3: M3Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """汇总三层收益语义，并保留旧字段作为可追溯原始输入。

    m3 的 ``gross_return`` 是受约束实际持仓的成本前收益，不是理想目标组合。
    月频执行链单独输出目标组合参考收益；日频没有独立目标参考层，必须保持
    unavailable/NaN，绝不用实际 gross 冒充。成本前后净值均从正式 OOS
    期初1.0独立归一。
    """
    long_frames: list[pd.DataFrame] = []
    for frequency, source, date_column in (
        ("daily", m3.daily_portfolio, "date"),
        ("monthly", m3.monthly_portfolio, "end_date"),
    ):
        frame = _formal(source, f"m3.{frequency}_portfolio")
        _require_columns(
            frame,
            {
                date_column,
                "holding_month",
                "portfolio",
                "target_reference_return",
                "actual_gross_before_cost_return",
                "actual_net_return",
            },
            f"m3.{frequency}_portfolio",
        )
        optional_columns = [
            column
            for column in (
                "gross_nav",
                "net_nav",
                "gross_cash",
                "net_cash",
                "target_reference_return",
                "valuation_phase",
                "ledger_component",
                *tuple(name for name in frame.columns if name.startswith("ledger_")),
            )
            if column in frame.columns
        ]
        optional_columns = list(dict.fromkeys(optional_columns))
        part = frame[
            [
                date_column,
                "holding_month",
                "portfolio",
                "actual_gross_before_cost_return",
                "actual_net_return",
                *optional_columns,
            ]
        ].rename(columns={date_column: "date", "portfolio": "entity"})
        if "gross_return" in frame:
            if not np.allclose(
                _finite_numeric(frame["gross_return"]),
                _finite_numeric(frame["actual_gross_before_cost_return"]),
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
                equal_nan=True,
            ):
                raise AssertionError(f"m3.{frequency}_portfolio旧gross与实际成本前字段不一致")
        if "net_return" in frame:
            if not np.allclose(
                _finite_numeric(frame["net_return"]),
                _finite_numeric(frame["actual_net_return"]),
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
                equal_nan=True,
            ):
                raise AssertionError(f"m3.{frequency}_portfolio旧net与实际净收益字段不一致")
        part["frequency"] = frequency
        part["entity_type"] = "long_portfolio"
        long_frames.append(part)

    factors = _formal(m3.factor_returns, "m3.factor_returns")
    _require_columns(
        factors,
        {
            "frequency",
            "date",
            "holding_month",
            "factor",
            "target_reference_return",
            "actual_gross_before_cost_return",
            "actual_net_return",
        },
        "m3.factor_returns",
    )
    factor_optional = [
        column
        for column in (
            "gross_nav",
            "net_nav",
            "target_reference_return",
            "factor_aggregation_contract",
            "factor_ledger_status",
        )
        if column in factors.columns
    ]
    factor_part = factors[
        [
            "frequency",
            "date",
            "holding_month",
            "factor",
            "actual_gross_before_cost_return",
            "actual_net_return",
            *factor_optional,
        ]
    ].rename(columns={"factor": "entity"})
    factor_part["entity_type"] = "style_factor"
    result = pd.concat([*long_frames, factor_part], ignore_index=True, sort=False)
    result["date"] = pd.to_datetime(result["date"], errors="coerce").dt.normalize()
    result["actual_before_cost_return"] = _finite_numeric(
        result["actual_gross_before_cost_return"]
    )
    result["actual_after_cost_net_return"] = _finite_numeric(result["actual_net_return"])
    result["gross_return"] = result["actual_before_cost_return"]
    result["net_return"] = result["actual_after_cost_net_return"]
    result["target_reference_return"] = _finite_numeric(result["target_reference_return"])
    result["target_reference_available"] = result["target_reference_return"].notna()
    expected_target_availability = result["frequency"].eq("monthly")
    if not result["target_reference_available"].eq(expected_target_availability).all():
        mismatches = result.loc[
            result["target_reference_available"].ne(expected_target_availability),
            ["frequency", "entity", "date", "target_reference_return"],
        ]
        raise AssertionError(
            "目标参考收益频率合同不一致：月频必须可用、日频必须不可用；"
            f"mismatches={mismatches.head(10).to_dict('records')}"
        )
    result["target_reference_frequency_contract"] = np.where(
        expected_target_availability,
        "monthly_available",
        "daily_unavailable",
    )
    result["target_reference_semantics"] = RETURN_LAYER_SEMANTICS[
        "target_reference_return"
    ]
    result["actual_before_cost_semantics"] = RETURN_LAYER_SEMANTICS[
        "actual_before_cost_return"
    ]
    result["actual_after_cost_net_semantics"] = RETURN_LAYER_SEMANTICS[
        "actual_after_cost_net_return"
    ]
    result = result.loc[result["entity"].isin(ENTITY_ORDER)].copy()
    result["entity"] = pd.Categorical(result["entity"], ENTITY_ORDER, ordered=True)
    result = result.sort_values(["frequency", "entity", "date"], kind="mergesort")
    result["actual_before_cost_nav"] = result.groupby(
        ["frequency", "entity"], observed=True, sort=False
    )["actual_before_cost_return"].transform(_normalised_nav)
    result["actual_after_cost_net_nav"] = result.groupby(
        ["frequency", "entity"], observed=True, sort=False
    )["actual_after_cost_net_return"].transform(_normalised_nav)
    # 旧字段仅作向后兼容；所有标题/定义使用三层新名称。
    result["gross_nav"] = result["actual_before_cost_nav"]
    result["net_nav"] = result["actual_after_cost_net_nav"]
    result["cumulative_cost_nav_drag"] = (
        result["actual_before_cost_nav"] - result["actual_after_cost_net_nav"]
    )
    result["cumulative_cost_cash_flow"] = np.nan
    result["cost_cash_reconciliation_error"] = np.nan

    long_mask = result["entity_type"].eq("long_portfolio")
    daily_cash_mask = (
        long_mask
        & result["frequency"].eq("daily")
        & result.get("gross_cash", pd.Series(index=result.index, dtype=float)).notna()
        & result.get("net_cash", pd.Series(index=result.index, dtype=float)).notna()
    )
    if daily_cash_mask.any():
        cash_flow = _finite_numeric(result.loc[daily_cash_mask, "gross_cash"]) - _finite_numeric(
            result.loc[daily_cash_mask, "net_cash"]
        )
        # 原始NAV与现金差均以正式OOS期初1.0计价；归一净值差须与其一致。
        result.loc[daily_cash_mask, "cumulative_cost_cash_flow"] = cash_flow.to_numpy()
        result.loc[daily_cash_mask, "cost_cash_reconciliation_error"] = (
            result.loc[daily_cash_mask, "cumulative_cost_nav_drag"].to_numpy()
            - cash_flow.to_numpy()
        )

    costs = _formal(m3.costs, "m3.costs")
    _require_columns(costs, {"holding_month", "portfolio", "total_cost"}, "m3.costs")
    monthly_cost = costs.loc[costs["portfolio"].isin(LONG_PORTFOLIOS)].copy()
    monthly_cost["total_cost"] = _finite_numeric(monthly_cost["total_cost"])
    # 月内可能同时有调仓与事件驱动退出，必须先汇总为唯一月度成本键再累计。
    monthly_cost = monthly_cost.groupby(
        ["holding_month", "portfolio"], as_index=False, sort=False
    )["total_cost"].sum(min_count=1).sort_values(
        ["portfolio", "holding_month"], kind="mergesort"
    )
    monthly_cost["cumulative_cost_cash_flow"] = monthly_cost.groupby(
        "portfolio", sort=False
    )["total_cost"].cumsum()
    monthly_lookup = monthly_cost.set_index(["holding_month", "portfolio"])[
        "cumulative_cost_cash_flow"
    ]
    monthly_mask = long_mask & result["frequency"].eq("monthly")
    if monthly_mask.any():
        monthly_index = pd.MultiIndex.from_frame(
            result.loc[monthly_mask, ["holding_month", "entity"]].rename(
                columns={"entity": "portfolio"}
            )
        )
        cash_flow = monthly_lookup.reindex(monthly_index).to_numpy(dtype=float)
        result.loc[monthly_mask, "cumulative_cost_cash_flow"] = cash_flow
        result.loc[monthly_mask, "cost_cash_reconciliation_error"] = (
            result.loc[monthly_mask, "cumulative_cost_nav_drag"].to_numpy() - cash_flow
        )

    terminal_long = (
        result.loc[long_mask]
        .sort_values(["frequency", "entity", "date"], kind="mergesort")
        .groupby(["frequency", "entity"], observed=True, sort=False)
        .tail(1)
    )
    if terminal_long["cumulative_cost_nav_drag"].lt(-config.numeric_tolerance).any():
        offenders = terminal_long.loc[
            terminal_long["cumulative_cost_nav_drag"].lt(-config.numeric_tolerance),
            ["frequency", "entity", "cumulative_cost_nav_drag"],
        ].to_dict("records")
        raise AssertionError(f"同一实际持仓期末成本前NAV低于成本后NAV: {offenders}")
    reconciled = result.loc[long_mask & result["cost_cash_reconciliation_error"].notna()]
    if reconciled["cost_cash_reconciliation_error"].abs().gt(config.numeric_tolerance).any():
        maximum = float(reconciled["cost_cash_reconciliation_error"].abs().max())
        raise AssertionError(f"累计成本现金流与成本前后NAV差不勾稽: max_error={maximum}")
    result["oos_start"] = pd.Timestamp(config.oos_start)
    result["oos_end"] = pd.Timestamp(config.oos_end)
    return result.reset_index(drop=True)


def _series_metrics(
    frame: pd.DataFrame,
    periods_per_year: int,
) -> dict[str, Any]:
    """按冻结R10口径汇总绩效。

    年化收益、波动、最大回撤和胜率直接复用 ``common``。最大回撤显式包含
    调仓前期初净值1.0作为峰值，故负首期回撤不会遗漏；这修复了旧src只从首个
    期末净值起算的缺陷。R10 的 Sharpe 冻结为几何年化收益/CAGR除以年化波动，
    与 ``common.calculate_sharpe`` 的算术均值口径不等价，因此只保留这一项定制计算。
    """
    net = _finite_numeric(frame["actual_after_cost_net_return"]).dropna()
    gross = _finite_numeric(frame["actual_before_cost_return"]).dropna()
    if len(net) != len(frame) or len(gross) != len(frame):
        raise ValueError("绩效输入含缺失收益")
    n_periods = len(net)
    annual_net = calculate_annualized_return(net, periods_per_year)
    annual_gross = calculate_annualized_return(gross, periods_per_year)
    net_vol = calculate_annualized_volatility(net, periods_per_year)
    gross_vol = calculate_annualized_volatility(gross, periods_per_year)
    target = _finite_numeric(frame["target_reference_return"])
    target_available = bool(target.notna().all())
    target_values = target.dropna()
    target_annualized = (
        calculate_annualized_return(target_values, periods_per_year)
        if target_available and len(target_values) == len(frame)
        else np.nan
    )
    terminal = frame.sort_values("date", kind="mergesort").iloc[-1]
    return {
        "n_periods": n_periods,
        "start_date": pd.Timestamp(frame["date"].min()),
        "end_date": pd.Timestamp(frame["date"].max()),
        "target_reference_available": target_available,
        "target_reference_cumulative_return": (
            float((1.0 + target_values).prod() - 1.0) if target_available else np.nan
        ),
        "target_reference_annualized_return": target_annualized,
        "actual_after_cost_cumulative_net_return": float((1.0 + net).prod() - 1.0),
        "actual_before_cost_cumulative_return": float((1.0 + gross).prod() - 1.0),
        "actual_after_cost_annualized_net_return": annual_net,
        "actual_before_cost_annualized_return": annual_gross,
        "cumulative_cost_nav_drag": float(terminal["cumulative_cost_nav_drag"]),
        "cumulative_cost_cash_flow": (
            float(terminal["cumulative_cost_cash_flow"])
            if pd.notna(terminal["cumulative_cost_cash_flow"])
            else np.nan
        ),
        "cost_cash_reconciliation_error": (
            float(terminal["cost_cash_reconciliation_error"])
            if pd.notna(terminal["cost_cash_reconciliation_error"])
            else np.nan
        ),
        "cumulative_net_return": float((1.0 + net).prod() - 1.0),
        "cumulative_gross_return": float((1.0 + gross).prod() - 1.0),
        "annualized_net_return": annual_net,
        "annualized_gross_return": annual_gross,
        "annualized_net_volatility": net_vol,
        "annualized_gross_volatility": gross_vol,
        "net_sharpe_zero_cash": annual_net / net_vol if net_vol > 0 else np.nan,
        "gross_sharpe_zero_cash": annual_gross / gross_vol if gross_vol > 0 else np.nan,
        "net_max_drawdown": -calculate_max_drawdown(_normalised_nav(net)),
        "gross_max_drawdown": -calculate_max_drawdown(_normalised_nav(gross)),
        "net_win_rate": calculate_win_rate(net),
        "gross_win_rate": calculate_win_rate(gross),
        "return_layer_semantics": json.dumps(
            RETURN_LAYER_SEMANTICS, ensure_ascii=False, sort_keys=True
        ),
    }


def _build_entity_audit(m3: M3Dataset) -> pd.DataFrame:
    """形成长组合精确审计及风格因子四腿均值审计，后者不冒充独立成交组合。"""
    turnover = _formal(m3.turnover, "m3.turnover")
    costs = _formal(m3.costs, "m3.costs")
    coverage = _formal(m3.coverage, "m3.coverage")
    monthly = _formal(m3.monthly_portfolio, "m3.monthly_portfolio")
    execution_keys = ["signal_date", "holding_month", "sample_phase", "portfolio"]
    nav_keys = ["holding_month", "sample_phase", "portfolio"]
    _require_columns(
        turnover,
        {
            "date",
            *execution_keys,
            "buy_notional",
            "sell_notional",
            "gross_traded_notional",
        },
        "m3.turnover",
    )
    _require_columns(
        costs,
        {
            "date",
            *execution_keys,
            "commission_cost",
            "slippage_cost",
            "stamp_tax",
            "total_cost",
        },
        "m3.costs",
    )
    _require_columns(coverage, {"date", *execution_keys}, "m3.coverage")
    _require_columns(
        monthly,
        {"start_date", *nav_keys, "start_net_nav"},
        "m3.monthly_portfolio",
    )
    if coverage.duplicated(execution_keys).any():
        duplicates = coverage.loc[
            coverage.duplicated(execution_keys, keep=False), execution_keys
        ].head(10)
        raise AssertionError(
            "m3.coverage月度执行键不唯一: "
            f"{duplicates.to_dict('records')}"
        )
    monthly_nav = monthly[["start_date", *nav_keys, "start_net_nav"]].copy()
    if monthly_nav.duplicated(nav_keys).any():
        raise AssertionError("m3.monthly_portfolio月度NAV分母键不唯一")
    monthly_nav["start_net_nav"] = _finite_numeric(monthly_nav["start_net_nav"])
    if monthly_nav["start_net_nav"].isna().any() or monthly_nav["start_net_nav"].le(0).any():
        raise AssertionError("m3.monthly_portfolio含无效月初NAV分母")

    turnover_aggregated = turnover.groupby(
        execution_keys, as_index=False, sort=False
    ).agg(
        buy_notional=("buy_notional", "sum"),
        sell_notional=("sell_notional", "sum"),
        gross_traded_notional=("gross_traded_notional", "sum"),
        turnover_first_date=("date", "min"),
        turnover_last_date=("date", "max"),
        turnover_record_count=("date", "size"),
    )
    costs_aggregated = costs.groupby(
        execution_keys, as_index=False, sort=False
    ).agg(
        commission_cost=("commission_cost", "sum"),
        slippage_cost=("slippage_cost", "sum"),
        stamp_tax=("stamp_tax", "sum"),
        total_cost=("total_cost", "sum"),
        cost_first_date=("date", "min"),
        cost_last_date=("date", "max"),
        cost_record_count=("date", "size"),
    )
    audit = coverage.merge(
        turnover_aggregated,
        on=execution_keys,
        how="left",
        validate="one_to_one",
    ).merge(
        costs_aggregated,
        on=execution_keys,
        how="left",
        validate="one_to_one",
    ).merge(
        monthly_nav,
        on=nav_keys,
        how="left",
        validate="one_to_one",
    )
    if audit["start_net_nav"].isna().any():
        raise AssertionError("月度执行审计缺少唯一月初NAV分母")
    audit["date"] = pd.to_datetime(audit["date"], errors="coerce").dt.normalize()
    audit["start_date"] = pd.to_datetime(
        audit["start_date"], errors="coerce"
    ).dt.normalize()
    if not audit["date"].eq(audit["start_date"]).all():
        raise AssertionError("coverage.date必须等于monthly_portfolio.start_date")
    audit["two_sided_turnover"] = (
        _finite_numeric(audit["gross_traded_notional"])
        / _finite_numeric(audit["start_net_nav"])
    )
    audit["one_way_turnover"] = audit["two_sided_turnover"] / 2.0
    audit["cost_rate_on_pretrade_nav"] = (
        _finite_numeric(audit["total_cost"])
        / _finite_numeric(audit["start_net_nav"])
    )
    keys = ["holding_month", "portfolio"]
    value_columns = [
        "two_sided_turnover",
        "one_way_turnover",
        "commission_cost",
        "slippage_cost",
        "stamp_tax",
        "total_cost",
        "cost_rate_on_pretrade_nav",
        "execution_price_coverage",
        "buy_tradable_coverage",
        "cash_weight",
        "unfilled_order_count",
        "unfilled_notional",
    ]
    _require_columns(audit, {*keys, *value_columns}, "m3 turnover/cost/coverage")
    trace_columns = [
        "date",
        "signal_date",
        "buy_notional",
        "sell_notional",
        "gross_traded_notional",
        "start_net_nav",
        "turnover_first_date",
        "turnover_last_date",
        "turnover_record_count",
        "cost_first_date",
        "cost_last_date",
        "cost_record_count",
    ]
    long_audit = audit.loc[
        audit["portfolio"].isin(LONG_PORTFOLIOS),
        [*keys, *trace_columns, *value_columns],
    ].rename(
        columns={"portfolio": "entity"}
    )
    long_audit["audit_definition"] = (
        "组合自身月度成交与成本；date为coverage/月初唯一执行日，"
        "first/last_date覆盖月内调仓及事件记录，turnover和cost_rate只除一次start_net_nav"
    )
    box_mean = audit.loc[audit["portfolio"].isin(STYLE_BOXES)].groupby(
        "holding_month", sort=True
    )[value_columns].mean().reset_index()
    synthetic = pd.concat(
        [box_mean.assign(entity=factor) for factor in FACTOR_NAMES], ignore_index=True
    )
    synthetic["audit_definition"] = "合成多空因子无独立成交簿；换手、成本和覆盖率为四腿简单均值"
    return pd.concat([long_audit, synthetic], ignore_index=True, sort=False)


def calculate_performance_summary(
    return_series: pd.DataFrame,
    m3: M3Dataset,
    specification: ReportingSpecification = DEFAULT_REPORTING_SPEC,
) -> pd.DataFrame:
    """R10：计算所有中国 OOS 组合/因子的日月绩效、换手、成本和覆盖率。"""
    audit = _build_entity_audit(m3)
    audit_summary = audit.groupby("entity", sort=False).agg(
        mean_monthly_two_sided_turnover=("two_sided_turnover", "mean"),
        mean_monthly_one_way_turnover=("one_way_turnover", "mean"),
        annualized_two_sided_turnover=("two_sided_turnover", lambda x: float(x.mean() * specification.monthly_periods_per_year)),
        total_commission_cost=("commission_cost", "sum"),
        total_slippage_cost=("slippage_cost", "sum"),
        total_stamp_tax=("stamp_tax", "sum"),
        total_cost=("total_cost", "sum"),
        cumulative_cost_rate=("cost_rate_on_pretrade_nav", "sum"),
        mean_execution_price_coverage=("execution_price_coverage", "mean"),
        mean_buy_tradable_coverage=("buy_tradable_coverage", "mean"),
        mean_cash_weight=("cash_weight", "mean"),
        total_unfilled_order_count=("unfilled_order_count", "sum"),
        total_unfilled_notional=("unfilled_notional", "sum"),
        audit_definition=("audit_definition", "first"),
    ).reset_index()
    records: list[dict[str, Any]] = []
    annualization = {
        "daily": specification.daily_periods_per_year,
        "monthly": specification.monthly_periods_per_year,
    }
    for (frequency, entity), part in return_series.groupby(
        ["frequency", "entity"], observed=True, sort=False
    ):
        records.append(
            {
                "frequency": str(frequency),
                "entity": str(entity),
                "entity_type": str(part["entity_type"].iloc[0]),
                "periods_per_year": annualization[str(frequency)],
                **_series_metrics(part, annualization[str(frequency)]),
            }
        )
    summary = pd.DataFrame(records).merge(audit_summary, on="entity", how="left", validate="many_to_one")
    summary["美国原值（背景/不可比）"] = "不适用：中国全A实验与美国两阶段ML方法不可数值等价比较"
    summary["comparison_semantics"] = "experimental_market_transplant_not_comparable"
    summary["max_drawdown_audit_definition"] = MAX_DRAWDOWN_AUDIT_DEFINITION
    return summary.sort_values(["frequency", "entity"], kind="mergesort").reset_index(drop=True)


def build_return_correlation(return_series: pd.DataFrame) -> pd.DataFrame:
    """R4：复用相关矩阵结构，输出中国四箱及SMB/HML/GML月度净收益相关性。"""
    monthly = return_series.loc[
        return_series["frequency"].eq("monthly")
        & return_series["entity"].astype(str).isin((*STYLE_BOXES, *FACTOR_NAMES))
    ]
    wide = monthly.pivot(index="holding_month", columns="entity", values="net_return")
    wide = wide.reindex(columns=[*STYLE_BOXES, *FACTOR_NAMES])
    if wide.isna().any(axis=None):
        raise ValueError("R4 月度四箱/因子收益不完整")
    matrix = wide.corr(method="pearson")
    # 相关矩阵对角线按定义固定为1；零方差序列与其他序列的相关仍保留NaN，
    # 不用0或其他数值掩盖“不可定义”。
    matrix = matrix.copy()
    for entity in matrix.columns:
        matrix.loc[entity, entity] = 1.0
    result = matrix.rename_axis("row_entity").reset_index().melt(
        id_vars="row_entity", var_name="column_entity", value_name="correlation"
    )
    result["n_months"] = len(wide)
    result["scope"] = "中国全A正式OOS月度扣费后收益；美国R4原值背景不可比"
    return result


def calculate_style_box_winner_frequency(
    return_series: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """R7：按四箱月度净收益计算胜出频率；精确并列时等分一个月胜场。"""
    monthly = return_series.loc[
        return_series["frequency"].eq("monthly")
        & return_series["entity"].astype(str).isin(STYLE_BOXES)
    ]
    wide = monthly.pivot(index="holding_month", columns="entity", values="net_return").reindex(
        columns=STYLE_BOXES
    )
    if wide.isna().any(axis=None):
        raise ValueError("R7 四箱月度扣费后收益不完整")
    maxima = wide.max(axis=1)
    flags = wide.eq(maxima, axis=0)
    tie_counts = flags.sum(axis=1)
    credits = flags.div(tie_counts, axis=0)
    winner_months = wide.reset_index().copy()
    winner_months["winner_boxes"] = flags.apply(
        lambda row: ",".join(row.index[row].astype(str)), axis=1
    ).to_numpy()
    winner_months["winner_count"] = tie_counts.to_numpy()
    winner_months["fractional_credit_per_winner"] = (1.0 / tie_counts).to_numpy()
    winner_months["tie_policy"] = "精确并列最高者等分一个月胜场"
    frequency = credits.sum().rename("fractional_win_count").reset_index().rename(
        columns={"entity": "style_box"}
    )
    frequency["winner_frequency"] = frequency["fractional_win_count"] / len(wide)
    frequency["n_months"] = len(wide)
    frequency["美国原值（背景/不可比）"] = "原六因子美国胜出频率仅背景；不构造F9标签"
    return winner_months, frequency


def run_r7_synthetic_regression_checks() -> dict[str, Any]:
    """覆盖单胜、双并列和四并列，逐月标签与分数必须可独立重算。"""
    cases = {
        "2024-01": {"BV": 0.04, "BG": 0.01, "SV": 0.02, "SG": 0.03},
        "2024-02": {"BV": 0.04, "BG": 0.04, "SV": 0.02, "SG": 0.01},
        "2024-03": {"BV": 0.01, "BG": 0.01, "SV": 0.01, "SG": 0.01},
    }
    rows = [
        {
            "frequency": "monthly",
            "holding_month": holding_month,
            "entity": style_box,
            "net_return": net_return,
        }
        for holding_month, returns in cases.items()
        for style_box, net_return in returns.items()
    ]
    winner_months, frequency = calculate_style_box_winner_frequency(pd.DataFrame(rows))
    expected = {
        "2024-01": ("BV", 1, 1.0),
        "2024-02": ("BV,BG", 2, 0.5),
        "2024-03": ("BV,BG,SV,SG", 4, 0.25),
    }
    for row in winner_months.itertuples(index=False):
        expected_boxes, expected_count, expected_credit = expected[row.holding_month]
        if (
            row.winner_boxes != expected_boxes
            or row.winner_count != expected_count
            or not np.isclose(row.fractional_credit_per_winner, expected_credit)
        ):
            raise AssertionError(
                f"R7并列反例不一致: month={row.holding_month}, "
                f"actual={(row.winner_boxes, row.winner_count, row.fractional_credit_per_winner)}, "
                f"expected={expected[row.holding_month]}"
            )
    expected_fractional_counts = {"BV": 1.75, "BG": 0.75, "SV": 0.25, "SG": 0.25}
    actual_counts = frequency.set_index("style_box")["fractional_win_count"]
    for style_box, expected_count in expected_fractional_counts.items():
        if not np.isclose(actual_counts[style_box], expected_count):
            raise AssertionError(f"R7 {style_box} fractional credit不一致")
    frequency_sum = float(frequency["winner_frequency"].sum())
    if not np.isclose(frequency_sum, 1.0):
        raise AssertionError(f"R7胜出频率合计不为1: {frequency_sum}")
    if winner_months["winner_boxes"].isna().any() or winner_months["winner_boxes"].eq("").any():
        raise AssertionError("R7逐月winner_boxes存在空值")
    return {
        "case_count": len(cases),
        "single_winner_labels": 1,
        "double_tie_labels": 1,
        "four_way_tie_labels": 1,
        "empty_winner_labels": 0,
        "fractional_win_counts": expected_fractional_counts,
        "winner_frequency_sum": frequency_sum,
    }


def _build_forward_returns(
    m1: M1Dataset,
    config: AllAStyleBoxConfig,
    horizons: Sequence[int],
) -> pd.DataFrame:
    """由连续月执行VWAP持有期收益复合成1..N月个股结果标签。"""
    panel = m1.monthly_panel.copy()
    _require_columns(
        panel,
        {"signal_date", "holding_month", "sample_phase", "stock_code", "gross_holding_return"},
        "m1.monthly_panel",
    )
    panel["signal_date"] = pd.to_datetime(panel["signal_date"], errors="coerce").dt.normalize()
    panel["stock_code"] = panel["stock_code"].astype(str).str.zfill(6)
    panel["gross_holding_return"] = _finite_numeric(panel["gross_holding_return"])
    panel = panel.sort_values(["stock_code", "signal_date"], kind="mergesort")
    signal_order = (
        m1.schedule[["signal_date", "holding_month", "sample_phase"]]
        .drop_duplicates("signal_date")
        .sort_values("signal_date", kind="mergesort")
        .reset_index(drop=True)
    )
    signal_order["signal_ordinal"] = np.arange(len(signal_order), dtype=int)
    panel = panel.merge(
        signal_order[["signal_date", "signal_ordinal"]], on="signal_date", how="inner", validate="many_to_one"
    )
    outputs: list[pd.DataFrame] = []
    indexed = panel.set_index(["signal_ordinal", "stock_code"])["gross_holding_return"]
    max_ordinal = int(signal_order["signal_ordinal"].max())
    for horizon in horizons:
        base = panel[["signal_date", "holding_month", "sample_phase", "signal_ordinal", "stock_code"]].copy()
        cumulative = pd.Series(1.0, index=base.index, dtype=float)
        complete = pd.Series(True, index=base.index)
        for lag in range(horizon):
            keys = pd.MultiIndex.from_arrays(
                [base["signal_ordinal"] + lag, base["stock_code"]],
                names=indexed.index.names,
            )
            leg = pd.Series(indexed.reindex(keys).to_numpy(), index=base.index, dtype=float)
            cumulative = cumulative * (1.0 + leg.fillna(0.0))
            complete &= leg.notna()
        base["horizon_months"] = horizon
        base["future_holding_return"] = (cumulative - 1.0).where(complete)
        base["endpoint_signal_ordinal"] = base["signal_ordinal"] + horizon - 1
        base["endpoint_within_formal_oos"] = base["endpoint_signal_ordinal"].le(max_ordinal)
        endpoint_phase = signal_order.set_index("signal_ordinal")["sample_phase"]
        base["endpoint_within_formal_oos"] &= base["endpoint_signal_ordinal"].map(endpoint_phase).eq(
            "formal_oos"
        )
        base = base.loc[
            base["sample_phase"].eq("formal_oos") & base["endpoint_within_formal_oos"]
        ]
        outputs.append(base)
    result = pd.concat(outputs, ignore_index=True)
    periods = pd.PeriodIndex(result["holding_month"], freq="M")
    if periods.min() < pd.Period(config.oos_start, freq="M") or periods.max() > pd.Period(
        config.oos_end, freq="M"
    ):
        raise AssertionError("IC 起始持有月超出正式 OOS")
    return result


def _build_factor_observations(
    forward_returns: pd.DataFrame,
    factor_long: pd.DataFrame,
) -> pd.DataFrame:
    """按因子独立形成结果样本，禁止用Style有效性缩小Size截面。

    ``m2.factor_long`` 的每一行已经来自 m1 合格池，因此 Size 只要求有限的
    ``size_signal`` 与对应未来收益；Style 另行要求 ``is_style_valid`` 和有限
    ``style_score``。两个样本先分开过滤，再合并成长表。
    """
    merged = forward_returns.merge(
        factor_long[
            ["signal_date", "stock_code", "size_signal", "style_score", "is_style_valid"]
        ],
        on=["signal_date", "stock_code"],
        how="inner",
        validate="many_to_one",
    )
    merged["future_holding_return"] = _finite_numeric(merged["future_holding_return"])
    merged["size_signal"] = _finite_numeric(merged["size_signal"])
    merged["style_score"] = _finite_numeric(merged["style_score"])
    identifier_columns = [
        "signal_date",
        "holding_month",
        "stock_code",
        "horizon_months",
        "future_holding_return",
        "is_style_valid",
    ]
    size = (
        merged.loc[
            merged["size_signal"].notna() & merged["future_holding_return"].notna(),
            [*identifier_columns, "size_signal"],
        ]
        .rename(columns={"size_signal": "factor_value"})
        .assign(
            factor="Size",
            factor_sample_rule="m1合格池且size_signal/对应未来收益有限；不要求Style有效",
        )
    )
    style = (
        merged.loc[
            merged["is_style_valid"].fillna(False)
            & merged["style_score"].notna()
            & merged["future_holding_return"].notna(),
            [*identifier_columns, "style_score"],
        ]
        .rename(columns={"style_score": "factor_value"})
        .assign(
            factor="Style",
            factor_sample_rule="m1合格池且is_style_valid、style_score/对应未来收益有限",
        )
    )
    result = pd.concat([size, style], ignore_index=True, sort=False)
    result["outcome_definition"] = (
        "T日冻结信号对应T+1 VWAP起始，连续月持有期毛收益复合；仅作为结果标签"
    )
    return result.sort_values(
        ["horizon_months", "signal_date", "factor", "stock_code"], kind="mergesort"
    ).reset_index(drop=True)


def run_m4_synthetic_regression_checks(
    specification: ReportingSpecification = DEFAULT_REPORTING_SPEC,
) -> dict[str, float | int]:
    """反例：Style缺失不得减少Size样本，也不得把Size IC变成Style子样本结果。"""
    signal_date = pd.Timestamp("2024-03-29")
    stock_codes = [f"{index:06d}" for index in range(1, 6)]
    forward = pd.DataFrame(
        {
            "signal_date": signal_date,
            "holding_month": "2024-04",
            "stock_code": stock_codes,
            "horizon_months": 1,
            "future_holding_return": [0.01, 0.02, 0.03, -0.04, -0.05],
        }
    )
    factors = pd.DataFrame(
        {
            "signal_date": signal_date,
            "stock_code": stock_codes,
            "size_signal": [1.0, 2.0, 3.0, 4.0, 5.0],
            "style_score": [-0.3, 0.0, 0.3, np.nan, np.nan],
            "is_style_valid": [True, True, True, False, False],
        }
    )
    observations = _build_factor_observations(forward, factors)
    size = observations.loc[observations["factor"].eq("Size")]
    style = observations.loc[observations["factor"].eq("Style")]
    if len(size) != len(stock_codes) or len(style) != 3:
        raise AssertionError(
            f"因子独立样本反例失败: Size={len(size)}, Style={len(style)}"
        )
    if len(size) < specification.minimum_ic_observations:
        raise AssertionError("反例Size样本不足以计算配置要求的最小截面IC")
    size_ic = calculate_ic(size["factor_value"], size["future_holding_return"])
    incorrectly_style_filtered_ic = float(
        size.loc[size["is_style_valid"], "factor_value"].corr(
            size.loc[size["is_style_valid"], "future_holding_return"], method="pearson"
        )
    )
    if np.isclose(size_ic, incorrectly_style_filtered_ic):
        raise AssertionError("反例未能区分完整Size样本与错误的Style子样本Size IC")
    return {
        "size_sample_count": len(size),
        "style_sample_count": len(style),
        "size_pearson_ic": size_ic,
        "incorrect_style_filtered_size_pearson_ic": incorrectly_style_filtered_ic,
    }


def run_common_statistics_regression_checks(
    specification: ReportingSpecification = DEFAULT_REPORTING_SPEC,
) -> dict[str, Any]:
    """以独立正确基线核对common，并覆盖旧src遗漏负首期回撤的反例。"""
    def independent_max_drawdown(period_returns: pd.Series) -> float:
        if period_returns.empty:
            return 0.0
        wealth = pd.concat(
            [
                pd.Series([specification.performance_initial_nav], dtype=float),
                specification.performance_initial_nav
                * (1.0 + period_returns.reset_index(drop=True)).cumprod(),
            ],
            ignore_index=True,
        )
        return float((wealth / wealth.cummax() - 1.0).min())

    n_months = len(pd.period_range(DEFAULT_CONFIG.oos_start, DEFAULT_CONFIG.oos_end, freq="M"))
    ordinal = np.arange(n_months, dtype=float)
    returns = pd.Series(0.008 + 0.015 * np.sin(ordinal / 2.0), dtype=float)
    factor = pd.Series(np.cos(ordinal / 4.0) + ordinal / n_months, dtype=float)
    outcome = pd.Series(np.sin(ordinal / 5.0) - ordinal / (2.0 * n_months), dtype=float)
    nav = (1.0 + returns).cumprod()
    independent_baseline = {
        "annualized_return": float(
            (1.0 + returns).prod()
            ** (specification.monthly_periods_per_year / len(returns))
            - 1.0
        ),
        "annualized_volatility": float(
            returns.std(ddof=1) * np.sqrt(specification.monthly_periods_per_year)
        ),
        "max_drawdown": independent_max_drawdown(returns),
        "win_rate": float(returns.gt(0).mean()),
        "pearson_ic": float(factor.corr(outcome, method="pearson")),
        "rank_ic": float(factor.corr(outcome, method="spearman")),
    }
    common = {
        "annualized_return": calculate_annualized_return(
            returns, specification.monthly_periods_per_year
        ),
        "annualized_volatility": calculate_annualized_volatility(
            returns, specification.monthly_periods_per_year
        ),
        "max_drawdown": -calculate_max_drawdown(nav),
        "win_rate": calculate_win_rate(returns),
        "pearson_ic": calculate_ic(factor, outcome),
        "rank_ic": calculate_rank_ic(factor, outcome),
    }
    errors = {
        key: abs(float(common[key]) - float(independent_baseline[key]))
        for key in independent_baseline
    }
    mdd_cases = {
        "negative_first_period": pd.Series([-0.10, 0.02, 0.03], dtype=float),
        "decline_after_first_peak": pd.Series([0.10, -0.20, 0.05], dtype=float),
        "empty_series": pd.Series(dtype=float),
    }
    mdd_case_errors: dict[str, float] = {}
    mdd_case_values: dict[str, float] = {}
    for case_name, case_returns in mdd_cases.items():
        case_nav = (
            specification.performance_initial_nav * (1.0 + case_returns).cumprod()
        )
        common_value = -calculate_max_drawdown(case_nav)
        baseline_value = independent_max_drawdown(case_returns)
        mdd_case_values[case_name] = common_value
        mdd_case_errors[case_name] = abs(common_value - baseline_value)
    negative_first = mdd_cases["negative_first_period"]
    negative_first_nav = (1.0 + negative_first).cumprod()
    old_src_negative_first = float(
        (negative_first_nav / negative_first_nav.cummax() - 1.0).min()
    )
    corrected_negative_first = mdd_case_values["negative_first_period"]
    max_error = max(errors.values())
    mdd_case_max_error = max(mdd_case_errors.values())
    if max(max_error, mdd_case_max_error) > specification.common_regression_tolerance:
        raise AssertionError(
            f"common统计与独立正确基线误差超限: metrics={errors}, mdd_cases={mdd_case_errors}"
        )
    return {
        "month_count": n_months,
        "metric_count": len(errors),
        "maximum_absolute_error": max_error,
        "mdd_case_count": len(mdd_cases),
        "mdd_case_maximum_absolute_error": mdd_case_max_error,
        "negative_first_old_src_value": old_src_negative_first,
        "negative_first_corrected_value": corrected_negative_first,
        "negative_first_bug_correction_absolute": abs(
            corrected_negative_first - old_src_negative_first
        ),
        "max_drawdown_audit_definition": MAX_DRAWDOWN_AUDIT_DEFINITION,
        "tolerance": specification.common_regression_tolerance,
        "within_tolerance": max(max_error, mdd_case_max_error)
        <= specification.common_regression_tolerance,
    }


def build_ic_diagnostics(
    m1: M1Dataset,
    m2: M2Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
    specification: ReportingSpecification = DEFAULT_REPORTING_SPEC,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """计算Size/Style的Pearson IC、RankIC、ICIR、五分位单调性和衰减。"""
    factors = m2.factor_long.copy()
    _require_columns(
        factors,
        {"signal_date", "stock_code", "size_signal", "style_score", "is_style_valid"},
        "m2.factor_long",
    )
    factors["signal_date"] = pd.to_datetime(factors["signal_date"], errors="coerce").dt.normalize()
    factors["stock_code"] = factors["stock_code"].astype(str).str.zfill(6)
    forward = _build_forward_returns(m1, config, specification.decay_horizons)
    long = _build_factor_observations(forward, factors)

    def correlations(group: pd.DataFrame) -> pd.Series:
        n_obs = len(group)
        if n_obs < specification.minimum_ic_observations:
            return pd.Series(
                {
                    "sample_count": n_obs,
                    "n_obs": n_obs,
                    "pearson_ic": np.nan,
                    "rank_ic": np.nan,
                }
            )
        return pd.Series(
            {
                "sample_count": n_obs,
                "n_obs": n_obs,
                "pearson_ic": calculate_ic(
                    group["factor_value"], group["future_holding_return"]
                ),
                "rank_ic": calculate_rank_ic(
                    group["factor_value"], group["future_holding_return"]
                ),
            }
        )

    series = (
        long.groupby(["horizon_months", "holding_month", "signal_date", "factor"], sort=True)
        .apply(correlations, include_groups=False)
        .reset_index()
    )
    one_month = series.loc[series["horizon_months"].eq(1)].copy()
    summary = one_month.groupby("factor", sort=True).agg(
        n_months=("holding_month", "nunique"),
        mean_cross_section_n=("n_obs", "mean"),
        pearson_ic_mean=("pearson_ic", "mean"),
        pearson_ic_std=("pearson_ic", "std"),
        rank_ic_mean=("rank_ic", "mean"),
        rank_ic_std=("rank_ic", "std"),
        pearson_positive_rate=("pearson_ic", calculate_win_rate),
        rank_positive_rate=("rank_ic", calculate_win_rate),
    ).reset_index()
    summary["pearson_icir_monthly"] = summary["pearson_ic_mean"] / summary["pearson_ic_std"]
    summary["rank_icir_monthly"] = summary["rank_ic_mean"] / summary["rank_ic_std"]
    summary["pearson_icir_annualized"] = summary["pearson_icir_monthly"] * np.sqrt(
        specification.monthly_periods_per_year
    )
    summary["rank_icir_annualized"] = summary["rank_icir_monthly"] * np.sqrt(
        specification.monthly_periods_per_year
    )
    summary["icir_definition"] = "月度IC均值/标准差；annualized列再乘sqrt(12)"

    decay = series.groupby(["horizon_months", "factor"], sort=True).agg(
        n_months=("holding_month", "nunique"),
        mean_cross_section_n=("n_obs", "mean"),
        pearson_ic_mean=("pearson_ic", "mean"),
        rank_ic_mean=("rank_ic", "mean"),
    ).reset_index()
    decay["decay_definition"] = "从同一T日信号起算的1/2/3月累计个股持有期毛收益IC"

    quantile_source = long.loc[long["horizon_months"].eq(1)].copy()
    grouped = quantile_source.groupby(["signal_date", "factor"], sort=False)
    quantile_source["stable_rank"] = grouped["factor_value"].rank(method="first")
    quantile_source["cross_section_n"] = grouped["factor_value"].transform("count")
    quantile_source["quantile"] = (
        np.floor(
            (quantile_source["stable_rank"] - 1.0)
            * specification.quantile_count
            / quantile_source["cross_section_n"]
        )
        .astype(int)
        .add(1)
        .clip(upper=specification.quantile_count)
    )
    quantile_returns = quantile_source.groupby(
        ["holding_month", "signal_date", "factor", "quantile"], sort=True
    ).agg(
        mean_future_return=("future_holding_return", "mean"),
        member_count=("stock_code", "nunique"),
    ).reset_index()
    quantile_returns["quantile_label"] = "Q" + quantile_returns["quantile"].astype(str)
    quantile_returns["cumulative_return"] = quantile_returns.sort_values("signal_date").groupby(
        ["factor", "quantile"], sort=False
    )["mean_future_return"].transform(_normalised_nav) - 1.0

    average_groups = quantile_returns.groupby(["factor", "quantile"], sort=True)[
        "mean_future_return"
    ].mean().reset_index()
    monotonic_records: list[dict[str, Any]] = []
    for factor, part in average_groups.groupby("factor", sort=True):
        part = part.sort_values("quantile")
        adjacent = part["mean_future_return"].diff().dropna()
        monotonic_records.append(
            {
                "factor": factor,
                "quantile_count": specification.quantile_count,
                "q_high_minus_q_low": float(part["mean_future_return"].iloc[-1] - part["mean_future_return"].iloc[0]),
                "group_spearman": calculate_rank_ic(
                    part["quantile"], part["mean_future_return"]
                ),
                "adjacent_increase_ratio": float(adjacent.gt(0).mean()),
                "strictly_monotonic_increasing": bool(adjacent.gt(0).all()),
                "definition": "高分组减低分组；Size高分代表小盘，Style高分代表成长",
            }
        )
    monotonicity = pd.DataFrame(monotonic_records)
    return long, one_month, summary, quantile_returns, monotonicity, decay


def build_turnover_cost_table(m3: M3Dataset) -> pd.DataFrame:
    """输出逐月长组合精确审计与合成因子四腿均值审计。"""
    return _build_entity_audit(m3).sort_values(["holding_month", "entity"], kind="mergesort")


def build_coverage_summary(m3: M3Dataset) -> pd.DataFrame:
    """汇总执行价格、方向可交易、现金与未成交覆盖率。"""
    audit = _build_entity_audit(m3)
    return audit.groupby("entity", sort=False).agg(
        n_months=("holding_month", "nunique"),
        mean_execution_price_coverage=("execution_price_coverage", "mean"),
        minimum_execution_price_coverage=("execution_price_coverage", "min"),
        mean_buy_tradable_coverage=("buy_tradable_coverage", "mean"),
        minimum_buy_tradable_coverage=("buy_tradable_coverage", "min"),
        mean_cash_weight=("cash_weight", "mean"),
        max_cash_weight=("cash_weight", "max"),
        total_unfilled_order_count=("unfilled_order_count", "sum"),
        total_unfilled_notional=("unfilled_notional", "sum"),
        audit_definition=("audit_definition", "first"),
    ).reset_index()


def build_benchmark_comparison(
    return_series: pd.DataFrame,
    specification: ReportingSpecification = DEFAULT_REPORTING_SPEC,
) -> pd.DataFrame:
    """SA4：相对同池全A和四箱1/N两套中国结构基准计算超额表现。"""
    monthly = return_series.loc[return_series["frequency"].eq("monthly")].copy()
    wide = monthly.pivot(index="holding_month", columns="entity", values="net_return")
    candidates = [entity for entity in ENTITY_ORDER if entity in wide.columns]
    records: list[dict[str, Any]] = []
    for benchmark in ("ALL_A", "STYLE_1N"):
        benchmark_returns = wide[benchmark]
        for entity in candidates:
            if entity == benchmark:
                continue
            excess = wide[entity] - benchmark_returns
            annual_excess = float(excess.mean() * specification.monthly_periods_per_year)
            tracking_error = float(excess.std(ddof=1) * np.sqrt(specification.monthly_periods_per_year))
            records.append(
                {
                    "entity": entity,
                    "benchmark": benchmark,
                    "n_months": len(excess),
                    "annualized_excess_return": annual_excess,
                    "annualized_tracking_error": tracking_error,
                    "information_ratio": annual_excess / tracking_error if tracking_error > 0 else np.nan,
                    "comparison_semantics": "中国同池结构稳健比较；美国商业周期/ML基准不在范围",
                }
            )
    return pd.DataFrame(records)


def _build_checks(
    dataset: M4Dataset | None,
    *,
    return_series: pd.DataFrame,
    correlation: pd.DataFrame,
    winner_frequency: pd.DataFrame,
    config: AllAStyleBoxConfig,
) -> pd.DataFrame:
    monthly = return_series.loc[return_series["frequency"].eq("monthly")]
    months = sorted(monthly["holding_month"].unique())
    expected_months = len(pd.period_range(config.oos_start, config.oos_end, freq="M"))
    hml = monthly.loc[monthly["entity"].astype(str).eq("HML")].set_index("holding_month")["net_return"]
    gml = monthly.loc[monthly["entity"].astype(str).eq("GML")].set_index("holding_month")["net_return"]
    diagonal = correlation.loc[correlation["row_entity"].eq(correlation["column_entity"]), "correlation"]
    checks = [
        ("formal_oos_month_count", expected_months, len(months), len(months) == expected_months),
        ("formal_oos_start", str(pd.Period(config.oos_start, freq="M")), str(min(months)), str(min(months)) == str(pd.Period(config.oos_start, freq="M"))),
        ("formal_oos_end", str(pd.Period(config.oos_end, freq="M")), str(max(months)), str(max(months)) == str(pd.Period(config.oos_end, freq="M"))),
        ("hml_gml_opposite", True, bool(np.allclose(hml, -gml, rtol=config.numeric_tolerance, atol=config.numeric_tolerance)), bool(np.allclose(hml, -gml, rtol=config.numeric_tolerance, atol=config.numeric_tolerance))),
        ("winner_frequency_sum", 1.0, float(winner_frequency["winner_frequency"].sum()), bool(np.isclose(winner_frequency["winner_frequency"].sum(), 1.0))),
        ("correlation_diagonal", 1.0, float(diagonal.min()), bool(np.allclose(diagonal, 1.0))),
        ("forbidden_scope_entities_absent", True, not any(token in " ".join(return_series.columns).casefold() for token in FORBIDDEN_SCOPE_TOKENS), not any(token in " ".join(return_series.columns).casefold() for token in FORBIDDEN_SCOPE_TOKENS)),
    ]
    return pd.DataFrame(
        checks,
        columns=["check_id", "expected", "observed", "implementation_observation_matches"],
    ).assign(
        check_scope="coder结构自检；正式验证结论留给verifier/check_gates",
        verifier_result=pd.NA,
    )


def _build_sources(m1: M1Dataset, m3: M3Dataset) -> pd.DataFrame:
    sources = pd.concat(
        [
            m1.source_catalog.assign(stage="m1"),
            m3.source_catalog.assign(stage="m3"),
            pd.DataFrame(
                [
                    {"stage": "m4", "purpose": "specification", "source": "workspace/r004_all_a_style_box/spec/spec.md", "future_fill": False},
                    {"stage": "m4", "purpose": "implementation_plan", "source": "workspace/r004_all_a_style_box/plan.md", "future_fill": False},
                    {"stage": "m4", "purpose": "assumption_registry", "source": "workspace/r004_all_a_style_box/assumptions.md", "future_fill": False},
                ]
            ),
        ],
        ignore_index=True,
        sort=False,
    )
    return sources


def build_m4_dataset(
    m1: M1Dataset,
    m2: M2Dataset,
    m3: M3Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
    specification: ReportingSpecification = DEFAULT_REPORTING_SPEC,
) -> M4Dataset:
    """m4统一稳定入口：构造R4/R7/R10/SA4与截面诊断的全部纯数据表。"""
    return_series = build_return_series(m3, config)
    performance = calculate_performance_summary(return_series, m3, specification)
    correlation = build_return_correlation(return_series)
    winner_months, winner_frequency = calculate_style_box_winner_frequency(return_series)
    observations, ic_series, ic_summary, quantiles, monotonicity, decay = build_ic_diagnostics(
        m1, m2, config, specification
    )
    turnover_cost = build_turnover_cost_table(m3)
    coverage = build_coverage_summary(m3)
    benchmarks = build_benchmark_comparison(return_series, specification)
    checks = _build_checks(
        None,
        return_series=return_series,
        correlation=correlation,
        winner_frequency=winner_frequency,
        config=config,
    )
    dataset = M4Dataset(
        return_series=return_series,
        performance_summary=performance,
        correlation_matrix=correlation,
        winner_months=winner_months,
        winner_frequency=winner_frequency,
        ic_observations=observations,
        ic_series=ic_series,
        ic_summary=ic_summary,
        quantile_returns=quantiles,
        monotonicity=monotonicity,
        decay_analysis=decay,
        turnover_cost=turnover_cost,
        coverage_summary=coverage,
        benchmark_comparison=benchmarks,
        checks=checks,
        sources=_build_sources(m1, m3),
    )
    assert_m4_invariants(dataset, config)
    return dataset


def assert_m4_invariants(
    dataset: M4Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> None:
    """检查m4边界、唯一键、指标完备性与实验语义，不给出验证通过结论。"""
    if not dataset.checks["implementation_observation_matches"].fillna(False).all():
        failed = dataset.checks.loc[
            ~dataset.checks["implementation_observation_matches"].fillna(False), "check_id"
        ].tolist()
        raise AssertionError(f"m4结构自检不一致: {failed}")
    expected_entities = set(ENTITY_ORDER)
    for frequency in ("daily", "monthly"):
        actual = set(
            dataset.return_series.loc[dataset.return_series["frequency"].eq(frequency), "entity"]
            .astype(str)
            .unique()
        )
        if actual != expected_entities:
            raise AssertionError(f"{frequency} 实体不完整: expected={expected_entities}, actual={actual}")
    if dataset.performance_summary.duplicated(["frequency", "entity"]).any():
        raise AssertionError("绩效表 frequency/entity 键不唯一")
    if not dataset.performance_summary["comparison_semantics"].eq(
        "experimental_market_transplant_not_comparable"
    ).all():
        raise AssertionError("R10未保持experimental不可比语义")
    ic_months = pd.PeriodIndex(dataset.ic_series["holding_month"], freq="M")
    if ic_months.min() < pd.Period(config.oos_start, freq="M") or ic_months.max() > pd.Period(
        config.oos_end, freq="M"
    ):
        raise AssertionError("IC序列越过正式OOS边界")
    sample_counts = dataset.ic_series.pivot(
        index=["horizon_months", "holding_month"], columns="factor", values="sample_count"
    )
    if sample_counts["Size"].lt(sample_counts["Style"]).any():
        raise AssertionError("Size独立样本不应小于要求is_style_valid的Style样本")


def _configure_plot_style() -> None:
    sns.set_theme(style="whitegrid")
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Arial Unicode MS", "Heiti TC", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _configure_date_axis(
    axis: plt.Axes,
    dates: Sequence[pd.Timestamp] | pd.Series | pd.DatetimeIndex,
    *,
    maximum_major_ticks: int = 12,
) -> None:
    """固定最多12个可辨年月主刻度，避免33个月标签堆叠。"""
    values = pd.DatetimeIndex(pd.to_datetime(pd.Series(dates), errors="coerce").dropna())
    values = values.sort_values().unique()
    if len(values) == 0:
        return
    tick_count = min(maximum_major_ticks, len(values))
    positions = np.linspace(0, len(values) - 1, num=tick_count, dtype=int)
    positions = np.unique(positions)
    ticks = values[positions]
    axis.set_xticks(ticks)
    axis.set_xticklabels(
        [pd.Timestamp(value).strftime("%Y-%m") for value in ticks],
        rotation=35,
        ha="right",
        rotation_mode="anchor",
    )


def _save_figure(fig: plt.Figure, path: Path, dpi: int) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_png_charts(
    dataset: M4Dataset,
    output_dir: Path,
    specification: ReportingSpecification = DEFAULT_REPORTING_SPEC,
) -> dict[str, Path]:
    """生成factor模板五图及风格箱三张追加图；只由正式main调用。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    _configure_plot_style()
    paths: dict[str, Path] = {}

    ic = dataset.ic_series.copy()
    ic["signal_date"] = pd.to_datetime(ic["signal_date"])
    factors = ["Size", "Style"]
    fig, axes = plt.subplots(2, 1, figsize=specification.time_series_figure_size, sharex=True)
    for axis, factor in zip(axes, factors):
        part = ic.loc[ic["factor"].eq(factor)].sort_values("signal_date")
        colors = np.where(part["rank_ic"].ge(0), PRIMARY_BLUE, PRIMARY_RED)
        axis.bar(part["signal_date"], part["rank_ic"], color=colors, width=20, label="月度RankIC")
        axis.plot(
            part["signal_date"],
            part["rank_ic"].rolling(specification.rolling_ic_months, min_periods=1).mean(),
            color="#333333",
            linewidth=1.5,
            label=f"{specification.rolling_ic_months}月滚动均值",
        )
        axis.set_title(f"{factor} 月度RankIC", fontsize=14)
        axis.set_ylabel("RankIC", fontsize=12)
        axis.legend(fontsize=10)
    paths["ic_series.png"] = output_dir / "ic_series.png"
    _save_figure(fig, paths["ic_series.png"], specification.chart_dpi)

    fig, axes = plt.subplots(1, 2, figsize=specification.time_series_figure_size)
    for axis, factor in zip(axes, factors):
        values = ic.loc[ic["factor"].eq(factor), "rank_ic"].dropna()
        bin_count = max(
            specification.ic_histogram_min_bins,
            min(
                specification.ic_histogram_max_bins,
                len(values) // specification.ic_histogram_observations_per_bin,
            ),
        )
        if not values.empty:
            axis.hist(
                values,
                bins=bin_count,
                density=True,
                color=PRIMARY_BLUE,
                alpha=0.75,
                edgecolor="white",
                label="RankIC密度直方图",
            )
            mean = float(values.mean())
            axis.axvline(mean, color=PRIMARY_RED, linestyle="--", label=f"均值 {mean:.3f}")
            standard_deviation = float(values.std(ddof=1)) if len(values) > 1 else np.nan
            if (
                len(values) >= specification.normal_fit_minimum_observations
                and np.isfinite(standard_deviation)
                and standard_deviation > specification.normal_fit_std_tolerance
            ):
                grid = np.linspace(
                    float(values.min()),
                    float(values.max()),
                    specification.normal_fit_grid_points,
                )
                density = np.exp(-0.5 * ((grid - mean) / standard_deviation) ** 2) / (
                    standard_deviation * np.sqrt(2.0 * np.pi)
                )
                axis.plot(
                    grid,
                    density,
                    color=PRIMARY_RED,
                    linewidth=2.0,
                    label=f"正态拟合 μ={mean:.3f}, σ={standard_deviation:.3f}",
                )
            else:
                axis.text(
                    0.5,
                    0.92,
                    "样本不足或标准差为0，正态曲线不可拟合",
                    transform=axis.transAxes,
                    ha="center",
                    va="top",
                    color=PRIMARY_RED,
                )
        else:
            axis.text(
                0.5,
                0.5,
                "无有效RankIC样本，正态曲线不可拟合",
                transform=axis.transAxes,
                ha="center",
                va="center",
                color=PRIMARY_RED,
            )
        axis.set_title(f"{factor} RankIC分布", fontsize=14)
        axis.set_xlabel("RankIC", fontsize=12)
        axis.set_ylabel("概率密度", fontsize=12)
        handles, labels = axis.get_legend_handles_labels()
        if handles:
            axis.legend(handles, labels, fontsize=10)
    paths["ic_distribution.png"] = output_dir / "ic_distribution.png"
    _save_figure(fig, paths["ic_distribution.png"], specification.chart_dpi)

    palette = sns.color_palette("RdBu", specification.quantile_count)
    fig, axes = plt.subplots(1, 2, figsize=specification.time_series_figure_size)
    for axis, factor in zip(axes, factors):
        part = dataset.quantile_returns.loc[dataset.quantile_returns["factor"].eq(factor)]
        for index, (quantile, group) in enumerate(part.groupby("quantile", sort=True)):
            axis.plot(
                pd.to_datetime(group["signal_date"]),
                1.0 + group["cumulative_return"],
                label=f"Q{quantile}",
                color=palette[index],
            )
        axis.set_title(f"{factor}五分组目标参考累计净值", fontsize=14)
        axis.set_xlabel("信号月", fontsize=12)
        axis.set_ylabel("目标参考累计净值（不含交易约束/成本，初始1）", fontsize=12)
        axis.legend(fontsize=10, ncol=2)
        _configure_date_axis(
            axis,
            part["signal_date"],
            maximum_major_ticks=12,
        )
    paths["group_cumulative_returns.png"] = output_dir / "group_cumulative_returns.png"
    _save_figure(fig, paths["group_cumulative_returns.png"], specification.chart_dpi)

    group_mean = dataset.quantile_returns.groupby(["factor", "quantile"], sort=True)[
        "mean_future_return"
    ].mean().mul(specification.monthly_periods_per_year).reset_index()
    fig, axes = plt.subplots(1, 2, figsize=specification.bar_figure_size)
    for axis, factor in zip(axes, factors):
        part = group_mean.loc[group_mean["factor"].eq(factor)]
        axis.bar(part["quantile"].astype(str), part["mean_future_return"], color=palette)
        axis.set_title(f"{factor}五分组年化平均收益", fontsize=14)
        axis.set_xlabel("分位组（Q1低→Q5高）", fontsize=12)
        axis.set_ylabel("年化平均收益率", fontsize=12)
    paths["group_returns_bar.png"] = output_dir / "group_returns_bar.png"
    _save_figure(fig, paths["group_returns_bar.png"], specification.chart_dpi)

    monthly = dataset.return_series.loc[dataset.return_series["frequency"].eq("monthly")]
    fig, axis = plt.subplots(figsize=specification.time_series_figure_size)
    for entity, color in zip(("ALL_A", "STYLE_1N", *STYLE_BOXES), ("#333333", "#9467bd", PRIMARY_RED, "#ff9896", PRIMARY_BLUE, "#9ecae1")):
        part = monthly.loc[monthly["entity"].astype(str).eq(entity)]
        axis.plot(pd.to_datetime(part["date"]), part["net_nav"], label=entity, color=color)
    axis.set_title("正式OOS净值比较（扣费后）", fontsize=14)
    axis.set_xlabel("持有期端点", fontsize=12)
    axis.set_ylabel("归一净值（初始1）", fontsize=12)
    axis.legend(fontsize=10, ncol=3)
    paths["net_value_comparison.png"] = output_dir / "net_value_comparison.png"
    _save_figure(fig, paths["net_value_comparison.png"], specification.chart_dpi)

    box_perf = dataset.performance_summary.loc[
        dataset.performance_summary["frequency"].eq("monthly")
        & dataset.performance_summary["entity"].isin(STYLE_BOXES)
    ].set_index("entity")["annualized_net_return"]
    heatmap = pd.DataFrame(
        [[box_perf["BV"], box_perf["BG"]], [box_perf["SV"], box_perf["SG"]]],
        index=["Big", "Small"],
        columns=["Value", "Growth"],
    )
    fig, axis = plt.subplots(figsize=specification.bar_figure_size)
    sns.heatmap(heatmap, annot=True, fmt=".2%", cmap=HEATMAP_PALETTE, center=0.0, ax=axis)
    axis.set_title("四风格箱OOS年化扣费后收益", fontsize=14)
    paths["style_box_heatmap.png"] = output_dir / "style_box_heatmap.png"
    _save_figure(fig, paths["style_box_heatmap.png"], specification.chart_dpi)

    fig, axis = plt.subplots(figsize=specification.time_series_figure_size)
    for factor, color in zip(FACTOR_NAMES, (PRIMARY_BLUE, PRIMARY_RED, "#2ca02c")):
        part = monthly.loc[monthly["entity"].astype(str).eq(factor)]
        axis.plot(pd.to_datetime(part["date"]), part["net_nav"], label=factor, color=color)
    axis.set_title("风格因子累计净值（四箱扣费后收益合成）", fontsize=14)
    axis.set_xlabel("持有期端点", fontsize=12)
    axis.set_ylabel("归一净值（初始1）", fontsize=12)
    axis.legend(fontsize=10)
    paths["factor_cumulative_returns.png"] = output_dir / "factor_cumulative_returns.png"
    _save_figure(fig, paths["factor_cumulative_returns.png"], specification.chart_dpi)

    audit = dataset.turnover_cost.loc[dataset.turnover_cost["entity"].isin(LONG_PORTFOLIOS)].copy()
    audit["date"] = pd.PeriodIndex(audit["holding_month"], freq="M").to_timestamp("M")
    totals = audit.groupby("date", sort=True).agg(
        mean_one_way_turnover=("one_way_turnover", "mean"),
        total_cost_rate=("cost_rate_on_pretrade_nav", "sum"),
    ).reset_index()
    fig, axis = plt.subplots(figsize=specification.time_series_figure_size)
    axis.bar(totals["date"], totals["mean_one_way_turnover"], width=20, color=PRIMARY_BLUE, alpha=0.7, label="组合平均单边换手")
    second = axis.twinx()
    second.plot(totals["date"], totals["total_cost_rate"], color=PRIMARY_RED, linewidth=1.8, label="组合成本率合计")
    axis.set_title("月度换手与交易成本", fontsize=14)
    axis.set_xlabel("持有月", fontsize=12)
    axis.set_ylabel("单边换手率", fontsize=12)
    second.set_ylabel("成本率", fontsize=12)
    handles, labels = axis.get_legend_handles_labels()
    handles2, labels2 = second.get_legend_handles_labels()
    axis.legend(handles + handles2, labels + labels2, fontsize=10)
    paths["turnover_cost.png"] = output_dir / "turnover_cost.png"
    _save_figure(fig, paths["turnover_cost.png"], specification.chart_dpi)
    return paths


def build_metrics_payload(
    dataset: M4Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """生成metrics.json可序列化语义；不含verifier结论。"""
    monthly_performance = dataset.performance_summary.loc[
        dataset.performance_summary["frequency"].eq("monthly")
    ]
    terminal_accounting_date = pd.Timestamp(
        dataset.return_series.loc[
            dataset.return_series["frequency"].eq("monthly"), "date"
        ].max()
    )
    boundary_disclosures = build_boundary_disclosures(
        config, terminal_accounting_date
    )
    return {
        "report_id": REPORT_ID,
        "reproduction_mode": "experimental",
        "verification_status": "pending_verifier",
        "audit_definition": {
            "max_drawdown": MAX_DRAWDOWN_AUDIT_DEFINITION,
            "return_layers": RETURN_LAYER_SEMANTICS,
            "cumulative_cost_reconciliation": (
                "同一实际持仓的成本前NAV-成本后NAV=累计成本现金流；允许单月净收益高于成本前收益"
            ),
        },
        "final_boundary_disclosures": [
            {"disclosure_id": key, "text": text}
            for key, text in boundary_disclosures
        ],
        "oos": {
            "freeze_cutoff": config.freeze_end,
            "start": config.oos_start,
            "end": config.oos_end,
            "n_months": int(monthly_performance["n_periods"].min()),
        },
        "performance": monthly_performance.to_dict("records"),
        "ic_summary": dataset.ic_summary.to_dict("records"),
        "winner_frequency": dataset.winner_frequency.to_dict("records"),
        "benchmark_comparison": dataset.benchmark_comparison.to_dict("records"),
        "coverage": dataset.coverage_summary.to_dict("records"),
        "implementation_checks": dataset.checks.to_dict("records"),
    }


def build_comparison_payload(
    dataset: M4Dataset,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """生成experimental comparison.json；美国原值只背景，不计算偏差或pass。"""
    monthly = dataset.performance_summary.loc[dataset.performance_summary["frequency"].eq("monthly")]
    terminal_accounting_date = pd.Timestamp(
        dataset.return_series.loc[
            dataset.return_series["frequency"].eq("monthly"), "date"
        ].max()
    )
    boundary_disclosures = build_boundary_disclosures(
        config, terminal_accounting_date
    )
    if set(monthly["entity"].astype(str)) != set(ENTITY_ORDER):
        raise AssertionError("R10月频绩效实体不是冻结的9个中国实体")
    r10_fields = {
        "annualized_net_return": "annualized_net_return",
        "annualized_net_volatility": "annualized_net_volatility",
        "net_sharpe_zero_cash": "net_sharpe_zero_cash",
    }
    metrics = [
        {
            "key": f"R10_{str(row.entity)}_{key_suffix}",
            "element_id": "R10",
            "report_value": None,
            "reproduced_value": float(getattr(row, source_column)),
            "verification_level": "market_transplant_output",
            "comparison_status": "not_comparable",
            "pass": None,
            "note": "中国全A实验产出；美国原值仅背景",
        }
        for row in monthly.itertuples(index=False)
        for source_column, key_suffix in r10_fields.items()
    ]
    sa4_fields = {
        "annualized_excess_return": "annualized_excess_return",
        "annualized_tracking_error": "annualized_tracking_error",
        "information_ratio": "information_ratio",
    }
    metrics.extend(
        {
            "key": (
                f"SA4_{row.entity}_vs_{row.benchmark}_{key_suffix}"
            ),
            "element_id": "SA4",
            "report_value": None,
            "reproduced_value": float(getattr(row, source_column)),
            "verification_level": "china_structural_benchmark_output",
            "comparison_status": "not_comparable",
            "pass": None,
            "note": "中国同池双基准逐项输出；美国商业周期/ML基准仅背景",
        }
        for row in dataset.benchmark_comparison.itertuples(index=False)
        for source_column, key_suffix in sa4_fields.items()
    )
    metrics.extend(
        [
            {
                "key": "R4_china_oos_correlation_cells",
                "element_id": "R4",
                "report_value": None,
                "reproduced_value": int(len(dataset.correlation_matrix)),
                "verification_level": "structure",
                "comparison_status": "not_comparable",
                "pass": None,
            },
            {
                "key": "R7_china_style_box_winner_frequency_sum",
                "element_id": "R7",
                "report_value": None,
                "reproduced_value": float(dataset.winner_frequency["winner_frequency"].sum()),
                "verification_level": "structure",
                "comparison_status": "not_comparable",
                "pass": None,
            },
        ]
    )
    expected_r10_keys = {
        f"R10_{entity}_{suffix}"
        for entity in ENTITY_ORDER
        for suffix in r10_fields.values()
    }
    expected_sa4_keys = {
        f"SA4_{row.entity}_vs_{row.benchmark}_{suffix}"
        for row in dataset.benchmark_comparison.itertuples(index=False)
        for suffix in sa4_fields.values()
    }
    actual_r10_keys = [
        str(record["key"]) for record in metrics if record["element_id"] == "R10"
    ]
    actual_sa4_keys = [
        str(record["key"]) for record in metrics if record["element_id"] == "SA4"
    ]
    if len(dataset.benchmark_comparison) != 16:
        raise AssertionError(
            f"SA4必须严格16个实体-基准组合，实际{len(dataset.benchmark_comparison)}"
        )
    if (
        len(actual_r10_keys) != 27
        or len(actual_r10_keys) != len(set(actual_r10_keys))
        or set(actual_r10_keys) != expected_r10_keys
    ):
        raise AssertionError("R10 comparison required-key必须精确覆盖9实体×3指标")
    if (
        len(actual_sa4_keys) != 48
        or len(actual_sa4_keys) != len(set(actual_sa4_keys))
        or set(actual_sa4_keys) != expected_sa4_keys
    ):
        raise AssertionError("SA4 comparison required-key必须精确覆盖16组合×3指标")
    return {
        "report_id": REPORT_ID,
        "reproduction_mode": "experimental",
        "comparison_semantics": "us_reference_background_vs_china_oos_not_reproduction_error",
        "report_values_are_reference_only": True,
        "verification_status": "pending_verifier",
        "return_layer_semantics": RETURN_LAYER_SEMANTICS,
        "required_key_contract": {
            "R10": sorted(expected_r10_keys),
            "SA4": sorted(expected_sa4_keys),
            "R10_count": len(expected_r10_keys),
            "SA4_count": len(expected_sa4_keys),
        },
        "final_boundary_disclosures": [
            {"disclosure_id": key, "text": text}
            for key, text in boundary_disclosures
        ],
        "metrics": metrics,
        "qualitative": [
            {
                "key": "R4_structure_transplant",
                "expect": "中国四箱及SMB/HML/GML相关矩阵",
                "observed": f"{len(dataset.correlation_matrix)}个相关单元格",
            },
            {
                "key": "R7_monthly_net_winner_frequency",
                "expect": "四箱扣费后月度胜出频率且无F9标签",
                "observed": f"{int(dataset.winner_frequency['n_months'].iloc[0])}个正式OOS月",
            },
            {
                "key": "SA4_dual_benchmark",
                "expect": "全A与四箱1/N双基准",
                "observed": "ALL_A与STYLE_1N两套中国结构基准均已输出",
            },
        ],
        "us_reference_background": {
            "R7": {
                "Value": 0.199,
                "Growth": 0.159,
                "Momentum": 0.144,
                "Low Volatility": 0.213,
                "Quality": 0.040,
                "Small Size": 0.245,
            },
            "R10": {
                "Russell 1000": {"annualized_return": 0.0840, "annualized_volatility": 0.1549, "sharpe": 0.52},
                "Equal Weighted": {"annualized_return": 0.0863, "annualized_volatility": 0.1519, "sharpe": 0.54},
                "Business Cycle Tilt": {"annualized_return": 0.0984, "annualized_volatility": 0.1606, "sharpe": 0.59},
                "ML Approach": {"annualized_return": 0.1147, "annualized_volatility": 0.1681, "sharpe": 0.66},
            },
            "note": (
                "仅背景/不可比；Momentum、Low Volatility、Quality、商业周期与ML未进入实现；"
                f"PASS若由verifier给出，也只代表本{len(pd.period_range(config.oos_start, config.oos_end, freq='M'))}个月"
                "实验合同通过，不证明长期稳定"
            ),
        },
    }


def parse_assumption_registry(path: Path) -> pd.DataFrame:
    """把assumptions.md解析为工作簿可读表；不修改登记簿。"""
    text = path.read_text(encoding="utf-8")
    records: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        if line.startswith("### [AS") and "]" in line:
            if current is not None:
                records.append(current)
            assumption_id, title = line.removeprefix("### [").split("]", maxsplit=1)
            current = {"assumption_id": assumption_id, "title": title.strip()}
        elif current is not None and line.startswith("- ") and ":" in line:
            key, value = line.removeprefix("- ").split(":", maxsplit=1)
            current[key.strip()] = value.strip()
    if current is not None:
        records.append(current)
    if not records:
        raise ValueError(f"未能从假设登记簿解析条目: {path}")
    return pd.DataFrame(records)


def assumption_frame_sha256(assumptions: pd.DataFrame) -> str:
    """对登记簿解析结果做列序、行序稳定的UTF-8摘要，供verifier上下文绑定。"""
    canonical = assumptions.copy()
    canonical.columns = canonical.columns.astype(str)
    if "assumption_id" not in canonical:
        raise ValueError("Assumptions缺少assumption_id")
    canonical = canonical.sort_values("assumption_id", kind="mergesort").fillna("")
    payload = canonical.to_json(
        orient="records", force_ascii=False, date_format="iso", double_precision=15
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_assumption_registry_for_finalization(
    assumptions: pd.DataFrame,
) -> pd.DataFrame:
    """阻断缺项、重复、占位回看的登记簿进入verified/PASS最终化。"""
    missing_columns = sorted(set(REQUIRED_ASSUMPTION_FIELDS).difference(assumptions.columns))
    if missing_columns:
        raise ValueError(f"Assumptions缺少最终化必需字段: {missing_columns}")
    canonical = assumptions.loc[:, list(REQUIRED_ASSUMPTION_FIELDS)].copy()
    for column in REQUIRED_ASSUMPTION_FIELDS:
        canonical[column] = canonical[column].fillna("").astype(str).str.strip()
    identifiers = canonical["assumption_id"]
    duplicated = sorted(identifiers.loc[identifiers.duplicated(keep=False)].unique())
    if duplicated:
        raise ValueError(f"Assumptions存在重复ID: {duplicated}")
    actual_ids = set(identifiers)
    expected_ids = set(EXPECTED_ASSUMPTION_IDS)
    if len(canonical) != EXPECTED_ASSUMPTION_COUNT or actual_ids != expected_ids:
        raise ValueError(
            "Assumptions必须精确覆盖AS1--AS24；"
            f"missing={sorted(expected_ids - actual_ids)}, "
            f"unexpected={sorted(actual_ids - expected_ids)}, rows={len(canonical)}"
        )
    empty_fields = {
        column: canonical.index[canonical[column].eq("")].tolist()
        for column in REQUIRED_ASSUMPTION_FIELDS
        if canonical[column].eq("").any()
    }
    if empty_fields:
        raise ValueError(f"Assumptions存在空白必需字段: {empty_fields}")
    review = canonical["验证后回看"].str.casefold()
    placeholder_rows = canonical.loc[
        review.map(
            lambda value: any(
                token.casefold() in value for token in ASSUMPTION_PLACEHOLDER_TOKENS
            )
        ),
        "assumption_id",
    ].tolist()
    if placeholder_rows:
        raise ValueError(f"Assumptions验证后回看仍含占位或pending文本: {placeholder_rows}")
    return canonical.sort_values(
        "assumption_id",
        key=lambda values: values.str.removeprefix("AS").astype(int),
        kind="mergesort",
    ).reset_index(drop=True)


def boundary_disclosure_frame(
    config: AllAStyleBoxConfig,
    terminal_accounting_date: pd.Timestamp,
) -> pd.DataFrame:
    disclosures = build_boundary_disclosures(config, terminal_accounting_date)
    return pd.DataFrame(
        [
            {
                "stage": "m4",
                "purpose": "final_boundary_disclosure",
                "source": disclosure_id,
                "boundary_disclosure": text,
                "future_fill": False,
            }
            for disclosure_id, text in disclosures
        ]
    )


def validate_verification_context(
    context: Mapping[str, Any],
    assumptions: pd.DataFrame,
    checks: pd.DataFrame,
) -> dict[str, Any]:
    """验证只读verifier上下文；仅该上下文可把工作簿最终化为verified/PASS。"""
    validate_assumption_registry_for_finalization(assumptions)
    if context.get("schema_version") != 1:
        raise ValueError("verification context schema_version必须为1")
    if context.get("verification_status") != "verified" or context.get("verdict") != "PASS":
        raise ValueError("最终化上下文必须由verifier明确给出verified/PASS")
    expected_assumption_hash = assumption_frame_sha256(assumptions)
    if context.get("assumptions_sha256") != expected_assumption_hash:
        raise ValueError("verification context未绑定当前Assumptions解析内容")
    if len(checks) != EXPECTED_CHECK_COUNT or "check_id" not in checks:
        raise ValueError(f"最终化要求Checks严格{EXPECTED_CHECK_COUNT}项")
    expected_check_ids = checks["check_id"].astype(str).tolist()
    check_results = context.get("check_results")
    if not isinstance(check_results, Mapping) or set(check_results) != set(expected_check_ids):
        raise ValueError("verification context check_results未精确覆盖7项Checks")
    if any(str(check_results[check_id]).strip().upper() != "PASS" for check_id in expected_check_ids):
        raise ValueError("verification context存在非PASS或空的check result")
    acknowledged = context.get("boundary_disclosures_acknowledged")
    expected_disclosures = list(BOUNDARY_DISCLOSURE_IDS)
    if acknowledged != expected_disclosures:
        raise ValueError("verification context未逐项确认全部最终结论边界")
    for key in ("verified_at", "verify_report", "evidence_manifest"):
        if not str(context.get(key, "")).strip():
            raise ValueError(f"verification context缺少{key}")
    canonical = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        **dict(context),
        "context_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


def _chart_block(
    frame: pd.DataFrame,
    columns: Sequence[str],
    *,
    chart_type: str,
    title: str,
) -> dict[str, Any]:
    selected = frame.loc[:, list(columns)].copy()
    return {
        "type": chart_type,
        "title": title,
        "columns": list(selected.columns),
        "rows": selected.to_dict("records"),
    }


def validate_pit_style_inputs(
    frame: pd.DataFrame,
    *,
    tolerance: float = 1e-12,
) -> dict[str, Any]:
    """从原始PIT腿逐层独立重算TTM、估值、秩、得分与2×2标签。"""
    value_winsor_columns = tuple(f"{name}_winsorised" for name in VALUE_COMPONENTS)
    value_rank_columns = tuple(f"{name}_rank" for name in VALUE_COMPONENTS)
    growth_winsor_columns = tuple(f"{name}_winsorised" for name in GROWTH_COMPONENTS)
    growth_rank_columns = tuple(f"{name}_rank" for name in GROWTH_COMPONENTS)
    required = {
        "signal_date",
        "stock_code",
        "eligible",
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
        "market_value",
        "negotiable_market_value",
        *VALUE_COMPONENTS,
        *GROWTH_COMPONENTS,
        "log_market_value",
        "size_rank",
        "size_signal",
        *value_winsor_columns,
        *value_rank_columns,
        *growth_winsor_columns,
        *growth_rank_columns,
        "value_core_component_count",
        "value_component_count",
        "growth_component_count",
        "value_score",
        "growth_score",
        "style_score",
        "is_style_valid",
        "size_group",
        "style_group",
        "style_box",
    }
    _require_columns(frame, required, PIT_STYLE_INPUTS_TABLE)
    if frame.empty:
        raise ValueError("pit_style_inputs不得为空")
    eligible_input = (
        frame["eligible"].astype("boolean").fillna(False).to_numpy(dtype=bool)
    )
    if not eligible_input.all():
        raise AssertionError("pit_style_inputs必须逐行覆盖eligible池，不得混入非eligible行")

    pit = frame.copy()
    date_columns = {
        "signal_date",
        "financial_end_date",
        "period_available_date",
        "current_info_publ_date",
        "prior_financial_end_date",
        "prior_info_publ_date",
        "prior_fy_financial_end_date",
        "prior_fy_info_publ_date",
        "balance_end_date",
        "balance_period_available_date",
        "balance_info_publ_date",
        "book_to_price_source_date",
        "earnings_to_price_source_date",
        "sales_to_price_source_date",
        "ttm_income_source_date",
        "dividend_source_date",
    }
    for column in date_columns:
        pit[column] = pd.to_datetime(pit[column], errors="coerce").dt.normalize()
    pit["stock_code"] = pit["stock_code"].astype(str).str.zfill(6)
    if pit[["signal_date", "stock_code"]].isna().any(axis=None):
        raise AssertionError("pit_style_inputs(signal_date,stock_code)键不得为空")
    if pit[["signal_date", "stock_code"]].duplicated().any():
        raise AssertionError("pit_style_inputs(signal_date,stock_code)键不唯一")

    disclosure_columns = [
        column
        for column in pit.columns
        if column.endswith("_info_publ_date")
        or column.endswith("_source_date")
        or column.endswith("_available_date")
    ]
    future_disclosure_count = sum(
        int(pd.to_datetime(pit[column], errors="coerce").dt.normalize().gt(pit["signal_date"]).sum())
        for column in disclosure_columns
    )
    if future_disclosure_count:
        raise AssertionError(f"PIT证据含未来披露/来源日: {future_disclosure_count}")

    def numeric(values: pd.Series) -> pd.Series:
        converted = pd.to_numeric(values, errors="coerce")
        return _finite_numeric(converted)

    def false_if_missing(values: pd.Series) -> pd.Series:
        """将pandas nullable布尔条件按冻结缺失语义显式解释为False。"""
        return values.astype("boolean").fillna(False).astype(bool)

    def boolean_array(values: pd.Series) -> np.ndarray:
        return false_if_missing(values).to_numpy(dtype=bool)

    def maximum_error(actual: pd.Series, expected: pd.Series) -> float:
        actual_num = numeric(actual)
        expected_num = numeric(expected)
        if actual_num.isna().ne(expected_num.isna()).any():
            return float("inf")
        valid = actual_num.notna()
        if not valid.any():
            return 0.0
        return float((actual_num.loc[valid] - expected_num.loc[valid]).abs().max())

    def date_mismatch_count(actual: pd.Series, expected: pd.Series) -> int:
        return int(actual.fillna(pd.Timestamp.min).ne(expected.fillna(pd.Timestamp.min)).sum())

    errors: dict[str, float] = {}
    mismatch_counts: dict[str, int] = {}

    financial_end = pit["financial_end_date"]
    expected_prior_end = financial_end - pd.DateOffset(years=1)
    expected_prior_fy_end = pd.to_datetime(
        (financial_end.dt.year - 1).astype("Int64").astype("string") + "-12-31",
        errors="coerce",
    )
    mismatch_counts["prior_financial_end_date"] = date_mismatch_count(
        pit["prior_financial_end_date"], expected_prior_end
    )
    mismatch_counts["prior_fy_financial_end_date"] = date_mismatch_count(
        pit["prior_fy_financial_end_date"], expected_prior_fy_end
    )

    annual = false_if_missing(
        financial_end.dt.month.eq(12) & financial_end.dt.day.eq(31)
    )
    expected_formula = pd.Series(
        np.where(
            boolean_array(annual),
            "annual_current",
            "current_ytd+prior_fy-prior_ytd",
        ),
        index=pit.index,
        dtype="string",
    )
    for source, output_column in (
        ("total_operating_revenue", "ttm_revenue"),
        ("net_profit", "ttm_net_profit"),
    ):
        current = numeric(pit[f"current_{source}"])
        prior = numeric(pit[f"prior_{source}"])
        prior_fy = numeric(pit[f"prior_fy_{source}"])
        reconstructed = current + prior_fy - prior
        complete_three_legs = false_if_missing(
            current.notna() & prior.notna() & prior_fy.notna()
        )
        expected_ttm = current.where(
            annual,
            reconstructed.where(complete_three_legs),
        )
        errors[f"{output_column}_max_abs_error"] = maximum_error(
            pit[output_column], expected_ttm
        )
        mismatch_counts[f"{output_column}_formula"] = int(
            pit[f"{output_column}_formula"].astype("string").ne(expected_formula).fillna(True).sum()
        )

    eps = np.finfo(np.float64).eps
    for current_column, prior_column, output_column in (
        (
            "current_total_operating_revenue",
            "prior_total_operating_revenue",
            "revenue_growth_symmetric",
        ),
        ("current_net_profit", "prior_net_profit", "net_profit_growth_symmetric"),
    ):
        current = numeric(pit[current_column])
        prior = numeric(pit[prior_column])
        growth_valid = false_if_missing(current.notna() & prior.notna())
        expected_growth = (
            2.0 * (current - prior) / (current.abs() + prior.abs() + eps)
        ).where(growth_valid)
        errors[f"{output_column}_raw_max_abs_error"] = maximum_error(
            pit[output_column], expected_growth
        )

    market_value = numeric(pit["market_value"])
    equity = numeric(pit["balance_total_shareholder_equity"])
    ttm_profit = numeric(pit["ttm_net_profit"])
    ttm_revenue = numeric(pit["ttm_revenue"])
    positive_market_value = false_if_missing(market_value.gt(0))
    expected_ratios = {
        "book_to_price": (equity / market_value).where(
            false_if_missing(equity.gt(0)) & positive_market_value
        ),
        "earnings_to_price": (ttm_profit / market_value).where(
            false_if_missing(ttm_profit.gt(0)) & positive_market_value
        ),
        "sales_to_price": (ttm_revenue / market_value).where(
            false_if_missing(ttm_revenue.gt(0)) & positive_market_value
        ),
    }
    for column, expected_ratio in expected_ratios.items():
        errors[f"{column}_raw_max_abs_error"] = maximum_error(pit[column], expected_ratio)

    expected_ttm_source = pit[
        ["current_info_publ_date", "prior_info_publ_date", "prior_fy_info_publ_date"]
    ].max(axis=1)
    source_date_expectations = {
        "book_to_price_source_date": pit["balance_info_publ_date"],
        "ttm_income_source_date": expected_ttm_source,
        "earnings_to_price_source_date": expected_ttm_source,
        "sales_to_price_source_date": expected_ttm_source,
    }
    for column, expected_date in source_date_expectations.items():
        mismatch_counts[column] = date_mismatch_count(pit[column], expected_date)

    dividend_age = numeric(pit["dividend_age_trading_days"])
    dividend_source = pit["dividend_source_date"]
    expected_dividend_fresh = false_if_missing(
        false_if_missing(dividend_source.notna())
        & false_if_missing(dividend_source.le(pit["signal_date"]))
        & false_if_missing(
            dividend_age.between(0, DEFAULT_CONFIG.dividend_max_age_trading_days)
        )
    )
    mismatch_counts["dividend_is_fresh"] = int(
        false_if_missing(pit["dividend_is_fresh"]).ne(expected_dividend_fresh).sum()
    )
    dividend_yield = numeric(pit["dividend_yield"])
    invalid_dividend = false_if_missing(dividend_yield.notna()) & (
        ~expected_dividend_fresh | false_if_missing(dividend_yield.lt(0))
    )
    missing_age = false_if_missing(dividend_source.notna() & dividend_age.isna())
    orphan_age = false_if_missing(dividend_source.isna() & dividend_age.notna())
    mismatch_counts["dividend_value_or_age"] = int(
        invalid_dividend.sum() + missing_age.sum() + orphan_age.sum()
    )

    recomputed_raw = {
        **expected_ratios,
        "dividend_yield": dividend_yield.where(
            expected_dividend_fresh & false_if_missing(dividend_yield.ge(0))
        ),
    }
    for growth_column in GROWTH_COMPONENTS:
        current_name = (
            "current_total_operating_revenue"
            if growth_column.startswith("revenue")
            else "current_net_profit"
        )
        prior_name = (
            "prior_total_operating_revenue"
            if growth_column.startswith("revenue")
            else "prior_net_profit"
        )
        current = numeric(pit[current_name])
        prior = numeric(pit[prior_name])
        growth_valid = false_if_missing(current.notna() & prior.notna())
        recomputed_raw[growth_column] = (
            2.0 * (current - prior) / (current.abs() + prior.abs() + eps)
        ).where(growth_valid)

    def winsorised_rank(values: pd.Series) -> tuple[pd.Series, pd.Series]:
        grouped = values.groupby(pit["signal_date"], sort=False)
        lower = grouped.transform(
            "quantile", q=STYLE_BOX_SPEC.winsor_lower_quantile
        )
        upper = grouped.transform(
            "quantile", q=STYLE_BOX_SPEC.winsor_upper_quantile
        )
        winsorised = values.clip(lower=lower, upper=upper)
        rank = winsorised.groupby(pit["signal_date"], sort=False).rank(method="average")
        count = winsorised.groupby(pit["signal_date"], sort=False).transform("count")
        percentile = (rank - 1.0).div(count - 1.0)
        percentile = percentile.where(
            false_if_missing(count.ne(1)), STYLE_BOX_SPEC.singleton_percentile_rank
        ).where(false_if_missing(winsorised.notna()))
        return winsorised, percentile

    recomputed_ranks: dict[str, pd.Series] = {}
    for component in (*VALUE_COMPONENTS, *GROWTH_COMPONENTS):
        winsorised, ranked = winsorised_rank(recomputed_raw[component])
        errors[f"{component}_winsorised_max_abs_error"] = maximum_error(
            pit[f"{component}_winsorised"], winsorised
        )
        errors[f"{component}_rank_max_abs_error"] = maximum_error(
            pit[f"{component}_rank"], ranked
        )
        recomputed_ranks[component] = ranked

    expected_core_count = pd.DataFrame(
        {name: recomputed_raw[name] for name in CORE_VALUE_COMPONENTS}
    ).notna().sum(axis=1)
    expected_value_count = pd.DataFrame(
        {name: recomputed_raw[name] for name in VALUE_COMPONENTS}
    ).notna().sum(axis=1)
    expected_growth_count = pd.DataFrame(
        {name: recomputed_raw[name] for name in GROWTH_COMPONENTS}
    ).notna().sum(axis=1)
    for column, expected_count in (
        ("value_core_component_count", expected_core_count),
        ("value_component_count", expected_value_count),
        ("growth_component_count", expected_growth_count),
    ):
        errors[f"{column}_max_abs_error"] = maximum_error(pit[column], expected_count)

    expected_value = pd.DataFrame(
        {name: recomputed_ranks[name] for name in VALUE_COMPONENTS}
    ).mean(axis=1, skipna=True).where(
        false_if_missing(
            expected_core_count.ge(STYLE_BOX_SPEC.minimum_value_components)
        )
    )
    expected_growth = pd.DataFrame(
        {name: recomputed_ranks[name] for name in GROWTH_COMPONENTS}
    ).mean(axis=1, skipna=True).where(
        false_if_missing(
            expected_growth_count.ge(STYLE_BOX_SPEC.minimum_growth_components)
        )
    )
    expected_style = expected_growth - expected_value
    expected_log_market_value = np.log(market_value).where(positive_market_value)
    _, expected_size_rank = winsorised_rank(expected_log_market_value)
    # Size不缩尾；上一步仅复用秩实现，秩对单调clip在正常正市值截面保持一致。
    size_rank = expected_log_market_value.groupby(pit["signal_date"], sort=False).rank(
        method="average"
    )
    size_count = expected_log_market_value.groupby(
        pit["signal_date"], sort=False
    ).transform("count")
    expected_size_rank = (size_rank - 1.0).div(size_count - 1.0).where(
        false_if_missing(size_count.ne(1)), STYLE_BOX_SPEC.singleton_percentile_rank
    ).where(false_if_missing(expected_log_market_value.notna()))
    errors.update(
        {
            "log_market_value_max_abs_error": maximum_error(
                pit["log_market_value"], expected_log_market_value
            ),
            "size_rank_max_abs_error": maximum_error(pit["size_rank"], expected_size_rank),
            "size_signal_max_abs_error": maximum_error(
                pit["size_signal"], -expected_size_rank
            ),
            "value_score_max_abs_error": maximum_error(pit["value_score"], expected_value),
            "growth_score_max_abs_error": maximum_error(
                pit["growth_score"], expected_growth
            ),
            "style_score_max_abs_error": maximum_error(pit["style_score"], expected_style),
        }
    )
    mismatch_counts["is_style_valid"] = int(
        false_if_missing(pit["is_style_valid"]).ne(
            false_if_missing(expected_style.notna())
        ).sum()
    )

    expected = pit[["signal_date", "stock_code"]].copy()
    expected["market_value_expected"] = market_value
    expected["style_score_expected"] = expected_style
    expected = expected.sort_values(
        ["signal_date", "market_value_expected", "stock_code"], kind="mergesort"
    )
    expected["size_position"] = expected.groupby("signal_date", sort=False).cumcount()
    expected["size_count"] = expected.groupby("signal_date", sort=False)[
        "stock_code"
    ].transform("size")
    expected["size_group_expected"] = np.where(
        boolean_array(expected["size_position"].lt(expected["size_count"] // 2)),
        "Small",
        "Big",
    )
    expected["style_group_expected"] = pd.Series(
        pd.NA, index=expected.index, dtype="string"
    )
    style_sorted = expected.loc[
        false_if_missing(expected["style_score_expected"].notna())
    ].sort_values(
        [
            "signal_date",
            "size_group_expected",
            "style_score_expected",
            "stock_code",
        ],
        kind="mergesort",
    )
    style_sorted["style_position"] = style_sorted.groupby(
        ["signal_date", "size_group_expected"], sort=False
    ).cumcount()
    style_sorted["style_count"] = style_sorted.groupby(
        ["signal_date", "size_group_expected"], sort=False
    )["stock_code"].transform("size")
    style_sorted["style_group_expected"] = np.where(
        boolean_array(
            style_sorted["style_position"].lt(style_sorted["style_count"] // 2)
        ),
        "Value",
        "Growth",
    )
    expected.loc[style_sorted.index, "style_group_expected"] = style_sorted[
        "style_group_expected"
    ]
    expected["style_box_expected"] = np.select(
        [
            boolean_array(
                expected["size_group_expected"].eq("Big")
                & expected["style_group_expected"].eq("Value")
            ),
            boolean_array(
                expected["size_group_expected"].eq("Big")
                & expected["style_group_expected"].eq("Growth")
            ),
            boolean_array(
                expected["size_group_expected"].eq("Small")
                & expected["style_group_expected"].eq("Value")
            ),
            boolean_array(
                expected["size_group_expected"].eq("Small")
                & expected["style_group_expected"].eq("Growth")
            ),
        ],
        ["BV", "BG", "SV", "SG"],
        default=None,
    )
    labels = expected.merge(
        pit[["signal_date", "stock_code", "size_group", "style_group", "style_box"]],
        on=["signal_date", "stock_code"],
        how="left",
        validate="one_to_one",
    )
    label_mismatches = {
        "size_group": int(labels["size_group_expected"].ne(labels["size_group"]).sum()),
        "style_group": int(
            labels["style_group_expected"].fillna("<NA>").ne(
                labels["style_group"].fillna("<NA>")
            ).sum()
        ),
        "style_box": int(
            labels["style_box_expected"].fillna("<NA>").ne(
                labels["style_box"].fillna("<NA>")
            ).sum()
        ),
    }
    mismatch_counts.update(label_mismatches)

    failed_errors = {
        key: value
        for key, value in errors.items()
        if not np.isfinite(value) or value > tolerance
    }
    failed_counts = {key: value for key, value in mismatch_counts.items() if value}
    if failed_errors or failed_counts:
        raise AssertionError(
            "PIT逐层独立重算不一致: "
            f"errors={failed_errors}, mismatch_counts={failed_counts}"
        )
    return {
        "row_count": int(len(pit)),
        "eligible_row_count": int(
            pit["eligible"].astype("boolean").fillna(False).to_numpy(dtype=bool).sum()
        ),
        "future_disclosure_count": future_disclosure_count,
        **errors,
        **{f"{key}_mismatch_count": value for key, value in mismatch_counts.items()},
    }


def validate_security_event_audit(
    frame: pd.DataFrame,
    *,
    tolerance: float = 1e-12,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """验证生命周期唯一估值状态、转板时点与退出现金勾稽。"""
    required = {
        "date",
        "portfolio",
        "stock_code",
        "price_source_date",
        "price_age_trading_days",
        "event_type",
        "event_effective_date",
        "event_source",
        "selected_for_valuation",
        "valuation_source_priority",
        "valuation_status",
        "valuation_selection_reason",
        "valuation_candidate_count",
        "valuation_candidate_sources",
        "valuation_conflict_resolved",
        "has_auditable_valuation_path",
        "mark_reconciliation_error",
        "unexplained_stale_residual",
        "blocking",
        "settlement_holding_error",
        "settlement_cash_error",
        "settlement_return_error",
    }
    _require_columns(frame, required, SECURITY_EVENT_AUDIT_TABLE)
    if frame.empty:
        raise ValueError("security_event_audit不得为空")
    audit = frame.copy()
    audit["date"] = pd.to_datetime(audit["date"], errors="coerce").dt.normalize()
    effective = pd.to_datetime(audit["event_effective_date"], errors="coerce").dt.normalize()
    future_event_count = int(
        (
            audit["valuation_status"].eq("explicit_settlement")
            & effective.gt(audit["date"])
        ).sum()
    )
    key = ["date", "portfolio", "stock_code"]
    duplicate_key_count = int(audit.duplicated(key, keep=False).sum())
    invalid_selected_count = int(
        (~audit["selected_for_valuation"].fillna(False).astype(bool)).sum()
    )
    unresolved_conflict_count = int(
        (
            pd.to_numeric(audit["valuation_candidate_count"], errors="coerce").fillna(0).gt(1)
            & ~audit["valuation_conflict_resolved"].fillna(False).astype(bool)
        ).sum()
    )
    stale_count = int(audit["unexplained_stale_residual"].fillna(False).sum())
    blocking_count = int(audit["blocking"].fillna(False).sum())
    unpriced_count = int(audit["valuation_status"].eq("unpriced_asset").sum())
    risk_exit_permanent_exemption_count = int(
        (
            audit["event_type"].astype(str).str.contains("risk_exit|risk_warning")
            & pd.to_numeric(audit["price_age_trading_days"], errors="coerce").gt(
                config.maximum_unexplained_price_age_trading_days
            )
            & audit["has_auditable_valuation_path"].fillna(False).astype(bool)
        ).sum()
    )
    mapping_public_date = pd.Timestamp(config.security_transfer_mapping_public_date)
    effective_date = pd.Timestamp(config.security_transfer_effective_date)
    new_code = config.security_transfer_new_code
    new_code_values = audit.get(
        "new_stock_code", pd.Series(pd.NA, index=audit.index, dtype="object")
    ).astype("string")
    pre_mapping_successor_count = int(
        (
            audit["date"].lt(mapping_public_date)
            & (
                audit["stock_code"].astype(str).str.zfill(6).eq(new_code)
                | new_code_values.eq(new_code).fillna(False)
            )
        ).sum()
    )

    pending_transfer = audit["valuation_status"].eq("pending_transfer")
    pending_transfer_count = int(pending_transfer.sum())
    invalid_pending_transfer_count = 0
    if pending_transfer_count:
        pending_required = {
            "asof",
            "old_stock_code",
            "new_stock_code",
            "transfer_window_age_trading_days",
            "old_mark",
            "amount_available",
            "amount_status",
        }
        _require_columns(audit, pending_required, SECURITY_EVENT_AUDIT_TABLE)
        pending = audit.loc[pending_transfer]
        pending_age = pd.to_numeric(
            pending["transfer_window_age_trading_days"], errors="coerce"
        )
        pending_old_mark = pd.to_numeric(pending["old_mark"], errors="coerce")
        pending_asof = pd.to_datetime(
            pending["asof"], errors="coerce"
        ).dt.normalize()
        pending_new = pending["new_stock_code"].astype("string")
        invalid_pending = (
            ~pending["stock_code"].astype(str).str.zfill(6).eq(
                config.security_transfer_old_code
            )
            | ~pending["old_stock_code"].astype(str).str.zfill(6).eq(
                config.security_transfer_old_code
            )
            | pending_new.notna()
            | pending["date"].ge(mapping_public_date)
            | pending_asof.ne(pending["date"])
            | ~pending_age.between(1, config.security_transfer_max_wait_trading_days)
            | ~np.isclose(
                pending_old_mark,
                config.security_transfer_old_mark,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | pending["amount_available"].fillna(True).astype(bool)
            | ~pending["amount_status"].astype(str).eq(
                "not_yet_available_before_mapping_public_date"
            )
        )
        invalid_pending_transfer_count = int(invalid_pending.sum())

    transfer_exit = audit["event_type"].eq("delisted_security_transfer_market_exit")
    transfer_exit_count = int(transfer_exit.sum())
    invalid_transfer_exit_count = 0
    missing_transfer_exit_count = 0
    if pending_transfer_count:
        pending_portfolios = set(audit.loc[pending_transfer, "portfolio"].astype(str))
        exit_portfolios = set(audit.loc[transfer_exit, "portfolio"].astype(str))
        missing_transfer_exit_count = len(pending_portfolios - exit_portfolios)
    if transfer_exit_count:
        transfer_required = {
            "asof",
            "old_stock_code",
            "new_stock_code",
            "old_shares_before",
            "mapped_shares",
            "exit_shares",
            "old_shares_after",
            "new_shares_after",
            "mapping_public_date",
            "mapping_effective_date",
            "settlement_ratio",
            "old_mark",
            "new_quote",
            "open",
            "high",
            "low",
            "close",
            "volumn",
            "volume_unit",
            "amount",
            "amount_available",
            "amount_status",
            "recomputed_vwap",
            "vwap_proof_method",
            "gross_notional",
            "commission_cost",
            "slippage_cost",
            "stamp_tax_rate",
            "stamp_tax",
            "total_cost",
            "net_cash_flow",
            "net_cash_before",
            "net_cash_after",
            "gross_cash_before",
            "gross_cash_after",
            "source_sha256",
            "manifest_sha256",
            "sse_source_sha256",
            "neeq_source_sha256",
        }
        _require_columns(audit, transfer_required, SECURITY_EVENT_AUDIT_TABLE)
        transfer = audit.loc[transfer_exit]

        def numeric(column: str) -> pd.Series:
            return pd.to_numeric(transfer[column], errors="coerce")

        old_shares = numeric("old_shares_before")
        mapped_shares = numeric("mapped_shares")
        exit_shares = numeric("exit_shares")
        vwap = numeric("recomputed_vwap")
        volume = numeric("volumn")
        gross = numeric("gross_notional")
        commission = numeric("commission_cost")
        slippage = numeric("slippage_cost")
        stamp_rate = numeric("stamp_tax_rate")
        stamp_tax = numeric("stamp_tax")
        total_cost = numeric("total_cost")
        net_flow = numeric("net_cash_flow")
        transfer_asof = pd.to_datetime(
            transfer["asof"], errors="coerce"
        ).dt.normalize()
        transfer_public = pd.to_datetime(
            transfer["mapping_public_date"], errors="coerce"
        ).dt.normalize()
        transfer_effective = pd.to_datetime(
            transfer["mapping_effective_date"], errors="coerce"
        ).dt.normalize()
        official_hashes = dict(config.security_transfer_frozen_sha256)
        ohlc_invalid = pd.Series(False, index=transfer.index)
        for column in ("open", "high", "low", "close", "new_quote"):
            ohlc_invalid |= ~np.isclose(
                numeric(column),
                config.security_transfer_expected_exit_vwap,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
        invalid_transfer = (
            transfer["date"].ne(effective_date)
            | transfer_asof.ne(transfer["date"])
            | transfer_public.ne(mapping_public_date)
            | transfer_effective.ne(effective_date)
            | ~transfer["stock_code"].astype(str).str.zfill(6).eq(
                config.security_transfer_old_code
            )
            | ~transfer["old_stock_code"].astype(str).str.zfill(6).eq(
                config.security_transfer_old_code
            )
            | ~transfer["new_stock_code"].astype(str).str.zfill(6).eq(new_code)
            | ~np.isclose(
                numeric("settlement_ratio"),
                config.security_transfer_ratio,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                mapped_shares,
                old_shares * config.security_transfer_ratio,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                exit_shares,
                mapped_shares,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | exit_shares.gt(volume + config.numeric_tolerance)
            | ~np.isclose(
                numeric("old_shares_after"),
                0.0,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                numeric("new_shares_after"),
                0.0,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                numeric("old_mark"),
                config.security_transfer_old_mark,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ohlc_invalid
            | ~np.isclose(
                volume,
                config.security_transfer_expected_first_volume_shares,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~transfer["volume_unit"].astype(str).eq(
                config.security_transfer_market_volume_unit
            )
            | numeric("amount").notna()
            | transfer["amount_available"].fillna(True).astype(bool)
            | ~transfer["amount_status"].astype(str).eq(
                config.security_transfer_market_amount_status
            )
            | ~transfer["vwap_proof_method"].astype(str).eq(
                "positive_volume_and_identical_ohlc_single_price"
            )
            | ~np.isclose(
                vwap,
                config.security_transfer_expected_exit_vwap,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                gross,
                exit_shares * vwap,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                commission,
                gross * config.commission_rate,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                slippage,
                gross * config.slippage_rate,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                stamp_tax,
                gross * stamp_rate,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                total_cost,
                commission + slippage + stamp_tax,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                net_flow,
                gross - total_cost,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                numeric("net_cash_after") - numeric("net_cash_before"),
                net_flow,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~np.isclose(
                numeric("gross_cash_after") - numeric("gross_cash_before"),
                gross,
                rtol=config.numeric_tolerance,
                atol=config.numeric_tolerance,
            )
            | ~transfer["source_sha256"].astype(str).eq(
                official_hashes[config.security_transfer_market_raw_filename]
            )
            | ~transfer["manifest_sha256"].astype(str).eq(
                config.security_transfer_manifest_sha256
            )
            | ~transfer["sse_source_sha256"].astype(str).eq(
                official_hashes[config.security_transfer_sse_raw_filename]
            )
            | ~transfer["neeq_source_sha256"].astype(str).eq(
                official_hashes[config.security_transfer_neeq_raw_filename]
            )
        )
        invalid_transfer_exit_count = int(invalid_transfer.sum())
    errors = {
        column: float(_finite_numeric(audit[column]).fillna(0.0).abs().max())
        for column in (
            "settlement_holding_error",
            "settlement_cash_error",
            "settlement_return_error",
            "mark_reconciliation_error",
        )
    }
    if (
        future_event_count
        or duplicate_key_count
        or invalid_selected_count
        or unresolved_conflict_count
        or stale_count
        or blocking_count
        or unpriced_count
        or risk_exit_permanent_exemption_count
        or pre_mapping_successor_count
        or invalid_pending_transfer_count
        or invalid_transfer_exit_count
        or missing_transfer_exit_count
    ):
        raise AssertionError(
            "证券事件证据未闭环: "
            f"future={future_event_count}, duplicate={duplicate_key_count}, "
            f"selected={invalid_selected_count}, conflict={unresolved_conflict_count}, "
            f"stale={stale_count}, blocking={blocking_count}, unpriced={unpriced_count}, "
            f"risk_exit_exemption={risk_exit_permanent_exemption_count}, "
            f"pre_mapping_successor={pre_mapping_successor_count}, "
            f"invalid_pending_transfer={invalid_pending_transfer_count}, "
            f"invalid_transfer_exit={invalid_transfer_exit_count}, "
            f"missing_transfer_exit={missing_transfer_exit_count}"
        )
    if any(value > tolerance for value in errors.values()):
        raise AssertionError(f"证券事件结算勾稽超差: {errors}")
    return {
        "row_count": int(len(audit)),
        "future_event_count": future_event_count,
        "duplicate_valuation_key_count": duplicate_key_count,
        "invalid_selected_count": invalid_selected_count,
        "unresolved_conflict_count": unresolved_conflict_count,
        "unexplained_stale_residual_count": stale_count,
        "blocking_count": blocking_count,
        "unpriced_asset_count": unpriced_count,
        "risk_exit_permanent_exemption_count": risk_exit_permanent_exemption_count,
        "pre_mapping_successor_count": pre_mapping_successor_count,
        "pending_transfer_count": pending_transfer_count,
        "invalid_pending_transfer_count": invalid_pending_transfer_count,
        "transfer_exit_count": transfer_exit_count,
        "invalid_transfer_exit_count": invalid_transfer_exit_count,
        "missing_transfer_exit_count": missing_transfer_exit_count,
        **{f"{key}_max_abs": value for key, value in errors.items()},
    }


def _collect_detail_tables(
    dataset: M4Dataset,
    m2: M2Dataset,
    m3: M3Dataset,
) -> dict[str, pd.DataFrame]:
    """收集正式OOS逐行明细；工作簿只展示其确定性有界视图。"""
    formal_signal_dates = pd.DatetimeIndex(
        pd.to_datetime(m3.target_weights["signal_date"], errors="coerce").dropna().unique()
    )
    memberships = m2.box_memberships.loc[
        pd.to_datetime(m2.box_memberships["signal_date"], errors="coerce").isin(
            formal_signal_dates
        )
    ].copy()
    pit_style_inputs = getattr(m2, "pit_style_inputs", None)
    if pit_style_inputs is None:
        raise ValueError("m2缺少pit_style_inputs正式证据接口")
    pit_style_inputs = pit_style_inputs.loc[
        pd.to_datetime(pit_style_inputs["signal_date"], errors="coerce").isin(
            formal_signal_dates
        )
    ].copy()
    formal_factor_long = m2.factor_long.loc[
        pd.to_datetime(m2.factor_long["signal_date"], errors="coerce").isin(
            formal_signal_dates
        )
    ].copy()
    pit_keys = set(
        map(
            tuple,
            pit_style_inputs[["signal_date", "stock_code"]]
            .assign(stock_code=lambda frame: frame["stock_code"].astype(str).str.zfill(6))
            .to_numpy(),
        )
    )
    factor_keys = set(
        map(
            tuple,
            formal_factor_long[["signal_date", "stock_code"]]
            .assign(stock_code=lambda frame: frame["stock_code"].astype(str).str.zfill(6))
            .to_numpy(),
        )
    )
    if pit_keys != factor_keys or len(pit_style_inputs) != len(formal_factor_long):
        raise AssertionError("pit_style_inputs未100%覆盖m2正式eligible行")
    if "eligible" not in pit_style_inputs:
        pit_style_inputs["eligible"] = True
        pit_style_inputs["eligible_source"] = "m2.factor_long全eligible公开合同"
    security_event_audit = getattr(m3, "security_event_audit", None)
    if security_event_audit is None:
        raise ValueError("m3缺少security_event_audit正式证据接口")
    security_event_audit = security_event_audit.copy()
    if "sample_phase" in security_event_audit:
        security_event_audit = security_event_audit.loc[
            security_event_audit["sample_phase"].eq("formal_oos")
        ].copy()
    validate_pit_style_inputs(pit_style_inputs)
    validate_security_event_audit(security_event_audit)
    tables = {
        "holdings": m3.holdings.copy(),
        "target_weights": m3.target_weights.copy(),
        "actual_weights": m3.actual_weights.copy(),
        "box_membership": memberships,
        "trades": m3.trades.copy(),
        "unfilled_orders": m3.unfilled_orders.copy(),
        "turnover": m3.turnover.copy(),
        "costs": m3.costs.copy(),
        "coverage": m3.coverage.copy(),
        "ic_observations": dataset.ic_observations.copy(),
        PIT_STYLE_INPUTS_TABLE: pit_style_inputs,
        SECURITY_EVENT_AUDIT_TABLE: security_event_audit,
    }
    if len(tables) != EXPECTED_DETAIL_TABLE_COUNT:
        raise AssertionError(
            f"正式逐行证据表必须为{EXPECTED_DETAIL_TABLE_COUNT}张，实际{len(tables)}"
        )
    return tables


def _detail_view_parameters(
    table_name: str,
    specification: ReportingSpecification,
) -> tuple[tuple[str, ...], str | None, int | None, str]:
    top_n_parameters = {
        "holdings": (
            ("holding_month", "portfolio"),
            "actual_weight",
            specification.holdings_view_rows_per_group,
            "每持有月、每组合按abs(actual_weight)降序取Top-N；stock_code/side/全行稳定哈希破同分",
        ),
        "target_weights": (
            ("holding_month", "portfolio"),
            "target_weight",
            specification.holdings_view_rows_per_group,
            "每持有月、每组合按abs(target_weight)降序取Top-N；stock_code/side/全行稳定哈希破同分",
        ),
        "actual_weights": (
            ("holding_month", "portfolio"),
            "actual_weight",
            specification.holdings_view_rows_per_group,
            "每持有月、每组合按abs(actual_weight)降序取Top-N；stock_code/side/全行稳定哈希破同分",
        ),
        "box_membership": (
            ("signal_date", "style_box"),
            "target_weight",
            specification.holdings_view_rows_per_group,
            "每信号日、每风格箱按abs(target_weight)降序取Top-N；stock_code/全行稳定哈希破同分",
        ),
        "trades": (
            ("holding_month", "portfolio"),
            "gross_notional",
            specification.trading_view_rows_per_group,
            "每持有月、每组合按abs(gross_notional)降序取Top-N；stock_code/side/全行稳定哈希破同分",
        ),
        "unfilled_orders": (
            ("holding_month", "portfolio"),
            "unfilled_notional",
            specification.trading_view_rows_per_group,
            "每持有月、每组合按abs(unfilled_notional)降序取Top-N；stock_code/side/全行稳定哈希破同分",
        ),
        "ic_observations": (
            ("horizon_months", "holding_month", "factor"),
            "factor_value",
            specification.ic_observations_view_rows_per_group,
            "每期限、持有月、因子按abs(factor_value)降序取Top-N；stock_code/全行稳定哈希破同分",
        ),
        PIT_STYLE_INPUTS_TABLE: (
            ("signal_date",),
            "style_score",
            specification.holdings_view_rows_per_group,
            "每信号日按abs(style_score)降序取Top-N；stock_code/全行稳定哈希破同分；Parquet保留全量eligible",
        ),
        SECURITY_EVENT_AUDIT_TABLE: (
            ("holding_month", "portfolio"),
            "price_age_trading_days",
            specification.trading_view_rows_per_group,
            "每持有月、每组合按price_age_trading_days降序取Top-N；stock_code/全行稳定哈希破同分；Parquet保留全量事件链",
        ),
    }
    if table_name in top_n_parameters:
        return top_n_parameters[table_name]
    return (
        tuple(),
        None,
        None,
        "全量逐行同时展示于工作簿并保存Parquet；按全行稳定哈希确定顺序",
    )


def _stable_detail_view(
    frame: pd.DataFrame,
    table_name: str,
    specification: ReportingSpecification,
) -> tuple[pd.DataFrame, str, int | None]:
    """构造与输入行顺序无关的Top-N或全量视图。"""
    group_columns, score_column, top_n, rule = _detail_view_parameters(
        table_name, specification
    )
    missing_groups = sorted(set(group_columns).difference(frame.columns))
    if missing_groups:
        if frame.empty:
            return frame.copy(), rule, top_n
        raise ValueError(f"{table_name}缺少视图分组字段: {missing_groups}")
    if score_column is not None and score_column not in frame.columns:
        if frame.empty:
            return frame.copy(), rule, top_n
        raise ValueError(f"{table_name}缺少视图排序字段: {score_column}")
    if frame.empty:
        return frame.copy(), rule, top_n

    ranked = frame.copy()
    stable_columns = sorted(ranked.columns.astype(str))
    stable_frame = ranked.loc[:, stable_columns].astype(str)
    ranked["_view_stable_hash"] = pd.util.hash_pandas_object(
        stable_frame, index=False, categorize=True
    ).astype("uint64")
    tie_columns = [
        column for column in ("stock_code", "side", "reason") if column in ranked.columns
    ]
    if score_column is None:
        ordered = ranked.sort_values(
            [*tie_columns, "_view_stable_hash"], kind="mergesort"
        )
        return ordered.drop(columns="_view_stable_hash").reset_index(drop=True), rule, top_n

    ranked["_view_selection_magnitude"] = _finite_numeric(ranked[score_column]).abs()
    ordered = ranked.sort_values(
        [*group_columns, "_view_selection_magnitude", *tie_columns, "_view_stable_hash"],
        ascending=[*[True] * len(group_columns), False, *[True] * len(tie_columns), True],
        kind="mergesort",
        na_position="last",
    )
    ordered["view_rank_within_group"] = (
        ordered.groupby(list(group_columns), sort=False, dropna=False).cumcount() + 1
    )
    selected = ordered.loc[ordered["view_rank_within_group"].le(int(top_n))].drop(
        columns=["_view_stable_hash", "_view_selection_magnitude"]
    )
    return selected.reset_index(drop=True), rule, top_n


def _stable_full_detail(frame: pd.DataFrame) -> pd.DataFrame:
    """按全行内容哈希稳定排序，不改变行列或数值。"""
    if frame.empty:
        return frame.reset_index(drop=True).copy()
    result = frame.copy()
    stable_columns = sorted(result.columns.astype(str))
    result["_detail_stable_hash"] = pd.util.hash_pandas_object(
        result.loc[:, stable_columns].astype(str), index=False, categorize=True
    ).astype("uint64")
    return result.sort_values("_detail_stable_hash", kind="mergesort").drop(
        columns="_detail_stable_hash"
    ).reset_index(drop=True)


def write_detail_tables(
    dataset: M4Dataset,
    m2: M2Dataset,
    m3: M3Dataset,
    output_dir: Path,
    specification: ReportingSpecification = DEFAULT_REPORTING_SPEC,
) -> dict[str, Any]:
    """写出全量逐行Parquet，并返回带hash和有界视图规模的manifest。"""
    detail_dir = output_dir / "detail_tables"
    detail_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for table_name, original in _collect_detail_tables(dataset, m2, m3).items():
        view, rule, top_n = _stable_detail_view(original, table_name, specification)
        full = _stable_full_detail(original)
        path = detail_dir / f"{table_name}.parquet"
        full.to_parquet(
            path,
            index=False,
            compression=specification.detail_parquet_compression,
        )
        round_trip = pd.read_parquet(path)
        if len(round_trip) != len(full) or list(round_trip.columns) != list(full.columns):
            raise AssertionError(
                f"{table_name} Parquet回读行列不一致: "
                f"rows={len(round_trip)}/{len(full)}, "
                f"columns={list(round_trip.columns)}/{list(full.columns)}"
            )
        expected_content_hash = hashlib.sha256(
            pd.util.hash_pandas_object(
                full.astype(str), index=False, categorize=True
            ).to_numpy(dtype="uint64").tobytes()
        ).hexdigest()
        actual_content_hash = hashlib.sha256(
            pd.util.hash_pandas_object(
                round_trip.astype(str), index=False, categorize=True
            ).to_numpy(dtype="uint64").tobytes()
        ).hexdigest()
        if expected_content_hash != actual_content_hash:
            raise AssertionError(f"{table_name} Parquet回读内容哈希不一致")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        records.append(
            {
                "table_name": table_name,
                "file": f"detail_tables/{path.name}",
                "full_row_count": int(len(original)),
                "displayed_row_count": int(len(view)),
                "columns": list(original.columns.astype(str)),
                "column_count": int(len(original.columns)),
                "size_bytes": int(path.stat().st_size),
                "sha256": digest.hexdigest(),
                "readback_row_count": int(len(round_trip)),
                "readback_column_count": int(len(round_trip.columns)),
                "readback_content_sha256": actual_content_hash,
                "readback_matches_written_frame": True,
                "view_limit_per_group": top_n,
                "view_rule": rule,
                "full_detail_semantics": "Parquet为全量逐行证据；XLSX视图不得冒充全量",
            }
        )
    if len(records) != EXPECTED_DETAIL_TABLE_COUNT:
        raise AssertionError(
            f"detail manifest必须登记{EXPECTED_DETAIL_TABLE_COUNT}张表，实际{len(records)}"
        )
    return {
        "report_id": REPORT_ID,
        "manifest_version": 2,
        "detail_root": "detail_tables",
        "parquet_compression": specification.detail_parquet_compression,
        "tables": records,
    }


def _workbook_detail_views(
    dataset: M4Dataset,
    m2: M2Dataset,
    m3: M3Dataset,
    detail_manifest: Mapping[str, Any],
    specification: ReportingSpecification,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    tables = _collect_detail_tables(dataset, m2, m3)
    manifest_records = {
        str(record["table_name"]): record for record in detail_manifest.get("tables", [])
    }
    if set(manifest_records) != set(tables):
        raise ValueError("detail_manifest与正式逐行明细表集合不一致")
    views: dict[str, pd.DataFrame] = {}
    for table_name, frame in tables.items():
        view, rule, top_n = _stable_detail_view(frame, table_name, specification)
        record = manifest_records[table_name]
        if (
            int(record["full_row_count"]) != len(frame)
            or int(record["displayed_row_count"]) != len(view)
            or record["view_rule"] != rule
            or record.get("view_limit_per_group") != top_n
        ):
            raise AssertionError(f"{table_name}明细manifest与工作簿视图不一致")
        projected_columns = WORKBOOK_DETAIL_VIEW_COLUMNS.get(table_name)
        if projected_columns is not None:
            missing_projection = sorted(set(projected_columns).difference(view.columns))
            if missing_projection:
                raise ValueError(
                    f"{table_name}工作簿审计视图缺少冻结列: {missing_projection}"
                )
            view = view.loc[:, list(projected_columns)]
        views[table_name] = view.copy()
    manifest_frame = pd.DataFrame(detail_manifest["tables"]).copy()
    manifest_frame["columns"] = manifest_frame["columns"].map(lambda value: "|".join(value))
    return views, manifest_frame


def _frame_payload(frame: pd.DataFrame) -> dict[str, Any]:
    clean = frame.copy()
    clean.columns = clean.columns.astype(str)
    for column in clean.columns:
        if pd.api.types.is_datetime64_any_dtype(clean[column]):
            clean[column] = clean[column].dt.strftime("%Y-%m-%d")
        elif isinstance(clean[column].dtype, pd.PeriodDtype):
            clean[column] = clean[column].astype(str)
        elif isinstance(clean[column].dtype, pd.CategoricalDtype):
            clean[column] = clean[column].astype(str)
    clean = clean.astype(object).where(pd.notna(clean), None)
    return {"columns": list(clean.columns), "rows": clean.values.tolist()}


def _payload_frame(sheet: Mapping[str, Any]) -> pd.DataFrame:
    columns = list(sheet.get("columns", []))
    rows = list(sheet.get("rows", []))
    if any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
        raise ValueError(f"工作表payload行列宽异常: {sheet.get('name')}")
    return pd.DataFrame(rows, columns=columns)


def build_workbook_payload(
    dataset: M4Dataset,
    m2: M2Dataset,
    m3: M3Dataset,
    assumptions: pd.DataFrame,
    detail_manifest: Mapping[str, Any],
    specification: ReportingSpecification = DEFAULT_REPORTING_SPEC,
    config: AllAStyleBoxConfig = DEFAULT_CONFIG,
    *,
    verification_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """生成五工作簿有界审计视图；全量逐行证据只保存在manifest指向的Parquet。"""
    detail_views, detail_manifest_frame = _workbook_detail_views(
        dataset, m2, m3, detail_manifest, specification
    )
    monthly_perf = dataset.performance_summary.loc[
        dataset.performance_summary["frequency"].eq("monthly")
    ].copy()
    terminal_accounting_date = pd.Timestamp(
        dataset.return_series.loc[
            dataset.return_series["frequency"].eq("monthly"), "date"
        ].max()
    )
    boundary_disclosures = build_boundary_disclosures(
        config, terminal_accounting_date
    )
    oos_period_count = len(pd.period_range(config.oos_start, config.oos_end, freq="M"))
    oos_period_label = (
        f"{pd.Period(config.oos_start, freq='M')}至"
        f"{pd.Period(config.oos_end, freq='M')}共{oos_period_count}个月"
    )
    summary_chart = _chart_block(
        monthly_perf,
        ["entity", "actual_after_cost_annualized_net_return"],
        chart_type="ColumnClustered",
        title="中国全A正式OOS实际持仓年化成本后净收益",
    )
    ic_chart_data = dataset.ic_series.pivot(
        index="signal_date", columns="factor", values="rank_ic"
    ).reset_index()
    group_chart_data = dataset.quantile_returns.groupby(["factor", "quantile"], sort=True)[
        "mean_future_return"
    ].mean().reset_index()
    group_chart_data["factor_quantile"] = (
        group_chart_data["factor"].astype(str) + "_Q" + group_chart_data["quantile"].astype(str)
    )
    group_chart_data = group_chart_data[["factor_quantile", "mean_future_return"]]
    monthly_returns = dataset.return_series.loc[
        dataset.return_series["frequency"].eq("monthly")
    ].pivot(
        index="date", columns="entity", values="actual_after_cost_net_return"
    ).reset_index()
    audit_chart = dataset.turnover_cost.loc[
        dataset.turnover_cost["entity"].eq("STYLE_1N"),
        ["holding_month", "one_way_turnover", "cost_rate_on_pretrade_nav"],
    ]

    if len(detail_manifest.get("tables", [])) != EXPECTED_DETAIL_TABLE_COUNT:
        raise ValueError(
            f"工作簿只接受{EXPECTED_DETAIL_TABLE_COUNT}表detail manifest"
        )
    checks = dataset.checks.copy()
    verified_context: dict[str, Any] | None = None
    if verification_context is not None:
        verified_context = validate_verification_context(
            verification_context, assumptions, checks
        )
        checks["verifier_result"] = checks["check_id"].astype(str).map(
            verified_context["check_results"]
        )
    if len(checks) != EXPECTED_CHECK_COUNT:
        raise ValueError(f"Checks必须严格{EXPECTED_CHECK_COUNT}行")
    if verified_context is not None and checks["verifier_result"].isna().any():
        raise AssertionError("verified/PASS工作簿不允许Checks.verifier_result为空")
    detail_records = {
        str(record["table_name"]): record for record in detail_manifest["tables"]
    }
    checks["detail_table_count"] = EXPECTED_DETAIL_TABLE_COUNT
    checks["pit_style_inputs_evidence"] = detail_records[PIT_STYLE_INPUTS_TABLE]["file"]
    checks["security_event_audit_evidence"] = detail_records[
        SECURITY_EVENT_AUDIT_TABLE
    ]["file"]
    checks["return_layer_semantics"] = json.dumps(
        RETURN_LAYER_SEMANTICS, ensure_ascii=False, sort_keys=True
    )
    checks["final_boundary_disclosures"] = " | ".join(
        text for _, text in boundary_disclosures
    )
    evidence_sources = pd.DataFrame(
        [
            {
                "stage": "m4",
                "purpose": "formal_detail_evidence",
                "source": record["file"],
                "future_fill": False,
                "table_name": table_name,
                "row_count": record["full_row_count"],
                "sha256": record["sha256"],
            }
            for table_name, record in detail_records.items()
        ]
    )
    sources = pd.concat(
        [
            dataset.sources.copy(),
            evidence_sources,
            boundary_disclosure_frame(config, terminal_accounting_date),
        ],
        ignore_index=True,
        sort=False,
    )
    us_reference = pd.DataFrame(
        [
            {"element_id": "R4", "美国原值（背景/不可比）": "六因子相关矩阵见spec R4", "china_output": "四箱及SMB/HML/GML相关矩阵", "comparison": "不可比"},
            {"element_id": "R7", "美国原值（背景/不可比）": "Value19.9%; Growth15.9%; Momentum14.4%; LowVol21.3%; Quality4.0%; Small24.5%", "china_output": "四箱扣费后月度胜出频率", "comparison": "不可比"},
            {"element_id": "R10", "美国原值（背景/不可比）": "Russell1000/Equal/BusinessCycle/ML组合表现见spec R10", "china_output": "全A、四箱、1/N、SMB/HML/GML绩效", "comparison": "不可比"},
        ]
    )

    workbook_status = "verified/PASS" if verified_context is not None else "pending_verifier"
    status_subtitle = (
        f"verified/PASS；结论仅限{oos_period_label}实验性中国市场迁移；不构成投资建议"
        if verified_context is not None
        else "pending_verifier；本工作簿不构成验证通过结论"
    )
    common_tail = [
        {"name": "Assumptions", "frame": assumptions},
        {"name": "Checks", "frame": checks},
        {"name": "Sources", "frame": sources},
        {"name": "DetailManifest", "frame": detail_manifest_frame},
    ]
    workbook_specs: list[dict[str, Any]] = [
        {
            "filename": "backtest_summary.xlsx",
            "title": "r004 中国全A风格箱正式OOS汇总",
            "subtitle": f"experimental；美国原值仅背景/不可比；{status_subtitle}",
            "sheets": [
                {"name": "Summary", "frame": monthly_perf, "chart": summary_chart},
                {"name": "Correlations", "frame": dataset.correlation_matrix},
                {"name": "Winners", "frame": dataset.winner_frequency},
                {"name": "WinnerMonths", "frame": dataset.winner_months},
                {"name": "Benchmarks", "frame": dataset.benchmark_comparison},
                {"name": "USReference", "frame": us_reference},
                *common_tail,
            ],
        },
        {
            "filename": "factor_analysis.xlsx",
            "title": "Size与Style截面诊断",
            "subtitle": f"个股未来持有期收益仅为目标参考标签；不进入策略或调参；{status_subtitle}",
            "sheets": [
                {"name": "ICSummary", "frame": dataset.ic_summary},
                {"name": "ICSeries", "frame": dataset.ic_series, "chart": _chart_block(ic_chart_data, list(ic_chart_data.columns), chart_type="Line", title="月度RankIC")},
                {"name": "Decay", "frame": dataset.decay_analysis},
                {"name": "Monotonicity", "frame": dataset.monotonicity},
                {"name": "GroupReturns", "frame": dataset.quantile_returns, "chart": _chart_block(group_chart_data, list(group_chart_data.columns), chart_type="ColumnClustered", title="五分组平均持有期收益")},
                {"name": "ICObservationsTop100", "frame": detail_views["ic_observations"]},
                *common_tail,
            ],
        },
        {
            "filename": "style_box_returns.xlsx",
            "title": "四箱、风格因子与基准收益",
            "subtitle": f"正式OOS {oos_period_label}；三层收益语义已拆分；{status_subtitle}",
            "sheets": [
                {"name": "MonthlyReturns", "frame": dataset.return_series.loc[dataset.return_series["frequency"].eq("monthly")], "chart": _chart_block(monthly_returns, list(monthly_returns.columns), chart_type="Line", title="实际持仓月度成本后净收益")},
                {"name": "DailyReturns", "frame": dataset.return_series.loc[dataset.return_series["frequency"].eq("daily")]},
                {"name": "Performance", "frame": dataset.performance_summary},
                {"name": "TurnoverCost", "frame": dataset.turnover_cost, "chart": _chart_block(audit_chart, list(audit_chart.columns), chart_type="Line", title="STYLE_1N换手与成本")},
                {"name": "Coverage", "frame": dataset.coverage_summary},
                *common_tail,
            ],
        },
        {
            "filename": "portfolio_holdings.xlsx",
            "title": "组合持仓与权重审计",
            "subtitle": f"含现金、目标权重、实际权重和偏差；均为T+1执行后状态；{status_subtitle}",
            "sheets": [
                {"name": "HoldingsTop100", "frame": detail_views["holdings"]},
                {"name": "TargetWeightsTop100", "frame": detail_views["target_weights"]},
                {"name": "ActualWeightsTop100", "frame": detail_views["actual_weights"]},
                {"name": "BoxMembershipTop100", "frame": detail_views["box_membership"]},
                *common_tail,
            ],
        },
        {
            "filename": "trading_audit.xlsx",
            "title": "交易、成本与不可成交审计",
            "subtitle": f"成交价、生命周期、未成交、换手和成本可逐行追溯；{status_subtitle}",
            "sheets": [
                {"name": "TradesTop200", "frame": detail_views["trades"]},
                {"name": "UnfilledTop200", "frame": detail_views["unfilled_orders"]},
                {"name": "Turnover", "frame": detail_views["turnover"]},
                {"name": "Costs", "frame": detail_views["costs"]},
                {"name": "Coverage", "frame": detail_views["coverage"]},
                *common_tail,
            ],
        },
    ]

    workbooks: list[dict[str, Any]] = []
    for workbook in workbook_specs:
        sheets: list[dict[str, Any]] = []
        for sheet in workbook["sheets"]:
            item = {"name": sheet["name"], **_frame_payload(sheet["frame"])}
            if "chart" in sheet:
                chart = dict(sheet["chart"])
                chart_frame = pd.DataFrame(chart.pop("rows"))
                item["chart"] = {**chart, **_frame_payload(chart_frame)}
            sheets.append(item)
        workbooks.append(
            {
                "filename": workbook["filename"],
                "title": workbook["title"],
                "subtitle": workbook["subtitle"],
                "sheets": sheets,
            }
        )
    return {
        "report_id": REPORT_ID,
        "reproduction_mode": "experimental",
        "verification_status": workbook_status,
        "verification_state": (
            "verified" if verified_context is not None else "pending_verifier"
        ),
        "verdict": verified_context["verdict"] if verified_context is not None else None,
        "verification_context": verified_context,
        "final_boundary_disclosures": [
            {"disclosure_id": key, "text": text}
            for key, text in boundary_disclosures
        ],
        "return_layer_semantics": RETURN_LAYER_SEMANTICS,
        "detail_manifest": {
            "path": "detail_manifest.json",
            "table_count": len(detail_manifest["tables"]),
            "workbook_views_are_full_detail": False,
        },
        "workbooks": workbooks,
    }


def finalize_workbook_payload(
    pending_payload: Mapping[str, Any],
    assumptions: pd.DataFrame,
    verification_context: Mapping[str, Any],
) -> dict[str, Any]:
    """只消费verifier上下文，把既有pending payload最终化；不重算策略或指标。"""
    payload = json.loads(json.dumps(pending_payload, ensure_ascii=False))
    boundary_disclosures = payload.get("final_boundary_disclosures")
    if (
        not isinstance(boundary_disclosures, list)
        or [item.get("disclosure_id") for item in boundary_disclosures]
        != list(BOUNDARY_DISCLOSURE_IDS)
    ):
        raise ValueError("pending payload缺少由运行config生成的完整边界披露")
    workbooks = payload.get("workbooks", [])
    filenames = [workbook.get("filename") for workbook in workbooks]
    expected_filenames = [
        "backtest_summary.xlsx",
        "factor_analysis.xlsx",
        "style_box_returns.xlsx",
        "portfolio_holdings.xlsx",
        "trading_audit.xlsx",
    ]
    if filenames != expected_filenames:
        raise ValueError(f"pending payload五工作簿不完整: {filenames}")
    first_sheets = {sheet["name"]: sheet for sheet in workbooks[0].get("sheets", [])}
    if "Checks" not in first_sheets:
        raise ValueError("pending payload缺少Checks工作表")
    checks = _payload_frame(first_sheets["Checks"])
    context = validate_verification_context(verification_context, assumptions, checks)
    check_results = context["check_results"]
    context_source = pd.DataFrame(
        [
            {
                "stage": "verify",
                "purpose": "verified_workbook_finalization_context",
                "source": context["verify_report"],
                "future_fill": False,
                "verification_status": "verified/PASS",
                "context_sha256": context["context_sha256"],
                "evidence_manifest": context["evidence_manifest"],
            }
        ]
    )
    for workbook in workbooks:
        sheets = {sheet["name"]: sheet for sheet in workbook.get("sheets", [])}
        missing = sorted({"Assumptions", "Checks", "Sources"}.difference(sheets))
        if missing:
            raise ValueError(f"{workbook['filename']}最终化缺少工作表: {missing}")
        sheet_checks = _payload_frame(sheets["Checks"])
        if len(sheet_checks) != EXPECTED_CHECK_COUNT:
            raise ValueError(f"{workbook['filename']} Checks不是7行")
        sheet_checks["verifier_result"] = sheet_checks["check_id"].astype(str).map(
            check_results
        )
        if sheet_checks["verifier_result"].isna().any():
            raise AssertionError(f"{workbook['filename']}最终化Checks仍有空结果")
        sheets["Checks"].update(_frame_payload(sheet_checks))
        sheets["Assumptions"].update(_frame_payload(assumptions))
        sources = _payload_frame(sheets["Sources"])
        sources = pd.concat([sources, context_source], ignore_index=True, sort=False)
        sheets["Sources"].update(_frame_payload(sources))
        workbook["subtitle"] = (
            str(workbook.get("subtitle", ""))
            .replace("pending_verifier；本工作簿不构成验证通过结论", "verified/PASS")
            .replace("验证结论待verifier", "verified/PASS")
        )
        if "verified/PASS" not in workbook["subtitle"]:
            workbook["subtitle"] = f"{workbook['subtitle']}；verified/PASS"
        workbook["subtitle"] = (
            f"{workbook['subtitle']}；仅适用工作簿动态边界披露；不构成投资建议"
        )
    payload["verification_status"] = "verified/PASS"
    payload["verification_state"] = "verified"
    payload["verdict"] = "PASS"
    payload["verification_context"] = context
    payload["final_boundary_disclosures"] = boundary_disclosures
    return payload


__all__ = [
    "ReportingSpecification",
    "DEFAULT_REPORTING_SPEC",
    "M4Dataset",
    "build_return_series",
    "calculate_performance_summary",
    "build_return_correlation",
    "calculate_style_box_winner_frequency",
    "run_r7_synthetic_regression_checks",
    "run_m4_synthetic_regression_checks",
    "run_common_statistics_regression_checks",
    "build_ic_diagnostics",
    "build_turnover_cost_table",
    "build_coverage_summary",
    "build_benchmark_comparison",
    "build_m4_dataset",
    "assert_m4_invariants",
    "write_png_charts",
    "build_metrics_payload",
    "build_comparison_payload",
    "build_boundary_disclosures",
    "parse_assumption_registry",
    "assumption_frame_sha256",
    "validate_verification_context",
    "validate_pit_style_inputs",
    "validate_security_event_audit",
    "write_detail_tables",
    "build_workbook_payload",
    "finalize_workbook_payload",
]
