"""m4：四类组合权重、商业周期基准与成本补充情景。

所有组合都以 ``factor_returns.signal_date`` 为信号时点，并只在该表给出的
下一可交易日 ``execution_date`` 执行。m3 的 ``prediction_date`` 仅用于验证
它确为下一自然月，绝不替代真实交易日。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Sequence

import numpy as np
import pandas as pd

from .config import ChinaFactorTimingConfig


PORTFOLIO_CSI800: Final[str] = "CSI800"
PORTFOLIO_EQUAL: Final[str] = "Six-Factor 1/N"
PORTFOLIO_CYCLE: Final[str] = "Business-Cycle 15% Tilt"
PORTFOLIO_ML: Final[str] = "ML Probability"

BUSINESS_CYCLE_DIRECTIONS: Final[dict[str, dict[str, int]]] = {
    "Expansion": {
        "Value": 0,
        "Growth": 0,
        "Momentum": 1,
        "Low Volatility": 0,
        "Quality": 0,
        "Small-Cap": -1,
    },
    "Slowdown": {
        "Value": -1,
        "Growth": -1,
        "Momentum": 1,
        "Low Volatility": 1,
        "Quality": 1,
        "Small-Cap": -1,
    },
    "Contraction": {
        "Value": 0,
        "Growth": 1,
        "Momentum": 0,
        "Low Volatility": -1,
        "Quality": -1,
        "Small-Cap": 1,
    },
    "Recovery": {
        "Value": 1,
        "Growth": -1,
        "Momentum": 0,
        "Low Volatility": -1,
        "Quality": 0,
        "Small-Cap": 1,
    },
}


@dataclass(frozen=True)
class PortfolioSettings:
    """m4 集中参数，冻结自 R9、AS23、AS24 与 AS26。"""

    active_tilt_budget: float = 0.15
    buy_cost_rate: float = 0.001
    sell_cost_rate: float = 0.001
    sell_stamp_tax_rate: float = 0.0005


@dataclass
class PortfolioResult:
    """m5 与报告层可直接消费的 m4 结构化输出。"""

    portfolio_returns: pd.DataFrame
    weight_detail: pd.DataFrame
    business_cycle_labels: pd.DataFrame
    cycle_direction_matrix: pd.DataFrame
    chart_data: pd.DataFrame
    alignment_audit: pd.DataFrame


def _validate_settings(settings: PortfolioSettings) -> None:
    if not np.isclose(settings.active_tilt_budget, 0.15, rtol=0.0, atol=1.0e-12):
        raise ValueError("AS23要求商业周期总主动倾斜预算固定为15%")
    expected = (0.001, 0.001, 0.0005)
    actual = (
        settings.buy_cost_rate,
        settings.sell_cost_rate,
        settings.sell_stamp_tax_rate,
    )
    if not np.allclose(actual, expected, rtol=0.0, atol=1.0e-12):
        raise ValueError("AS26要求买卖各10bp且卖出另加5bp印花税")


def cycle_direction_matrix(
    factor_order: Sequence[str],
) -> pd.DataFrame:
    """以长表输出 R9 六因子四周期方向矩阵。"""
    order = tuple(factor_order)
    expected = set(next(iter(BUSINESS_CYCLE_DIRECTIONS.values())))
    if len(order) != 6 or set(order) != expected:
        raise ValueError("R9要求固定六因子，名称必须与方向矩阵完全一致")
    rows = [
        {"business_cycle": cycle, "factor": factor, "direction": directions[factor]}
        for cycle, directions in BUSINESS_CYCLE_DIRECTIONS.items()
        for factor in order
    ]
    return pd.DataFrame(rows)


def business_cycle_weights(
    business_cycle: str,
    factor_order: Sequence[str],
    active_budget: float = 0.15,
) -> pd.Series:
    """按 AS23 对 R9 方向去均值，分配总主动预算并做非负归一。"""
    if business_cycle not in BUSINESS_CYCLE_DIRECTIONS:
        raise ValueError(f"未知商业周期标签: {business_cycle!r}")
    if not np.isclose(active_budget, 0.15, rtol=0.0, atol=1.0e-12):
        raise ValueError("商业周期主动倾斜预算必须为15%")
    order = tuple(factor_order)
    cycle_direction_matrix(order)
    scores = pd.Series(BUSINESS_CYCLE_DIRECTIONS[business_cycle], dtype=float).reindex(order)
    centred = scores - scores.mean()
    denominator = float(centred.abs().sum())
    base = pd.Series(1.0 / len(order), index=order, dtype=float)
    tilted = base if denominator <= 0.0 else base + active_budget * centred / denominator
    clipped = tilted.clip(lower=0.0)
    total = float(clipped.sum())
    if not np.isfinite(total) or total <= 0.0:
        raise AssertionError("商业周期权重裁剪后无法归一化")
    result = clipped / total
    if (result < -1.0e-12).any() or not np.isclose(result.sum(), 1.0, atol=1.0e-12):
        raise AssertionError("商业周期权重未满足非负且和为1")
    return result


def _normalise_m1_inputs(
    monthly_features: pd.DataFrame,
    factor_returns: pd.DataFrame,
    factor_order: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    feature_required = {"signal_date", "business_cycle", "benchmark_return"}
    factor_required = {
        "signal_date",
        "execution_date",
        "return_date",
        "factor",
        "factor_return",
    }
    if missing := feature_required.difference(monthly_features.columns):
        raise KeyError(f"monthly_features 缺少字段: {sorted(missing)}")
    if missing := factor_required.difference(factor_returns.columns):
        raise KeyError(f"factor_returns 缺少字段: {sorted(missing)}")

    features = monthly_features.loc[:, sorted(feature_required)].copy()
    features["signal_date"] = pd.to_datetime(features["signal_date"]).dt.normalize()
    features["signal_period"] = features["signal_date"].dt.to_period("M")
    if features["signal_period"].duplicated().any():
        raise ValueError("monthly_features 同一月份存在重复记录")

    returns = factor_returns.loc[:, sorted(factor_required)].copy()
    for column in ("signal_date", "execution_date", "return_date"):
        returns[column] = pd.to_datetime(returns[column]).dt.normalize()
    returns["factor_return"] = pd.to_numeric(returns["factor_return"], errors="coerce")
    returns["signal_period"] = returns["signal_date"].dt.to_period("M")
    if returns.duplicated(["signal_period", "factor"]).any():
        raise ValueError("factor_returns 同一信号月/因子存在重复记录")
    unexpected = sorted(set(returns["factor"].dropna()) - set(factor_order))
    if unexpected:
        raise ValueError(f"factor_returns 含计划外因子: {unexpected}")

    schedule = returns.groupby("signal_period", as_index=False).agg(
        signal_date=("signal_date", "min"),
        signal_date_count=("signal_date", "nunique"),
        execution_date=("execution_date", "min"),
        execution_date_count=("execution_date", "nunique"),
        return_date=("return_date", "max"),
        return_date_count=("return_date", "nunique"),
        factor_count=("factor", "nunique"),
        available_return_count=("factor_return", "count"),
    )
    bad_schedule = schedule.loc[
        schedule[["signal_date_count", "execution_date_count", "return_date_count"]].ne(1).any(axis=1)
        | schedule["factor_count"].ne(6)
        | schedule["available_return_count"].ne(6)
        | schedule["execution_date"].le(schedule["signal_date"])
        | schedule["return_date"].le(schedule["execution_date"])
    ]
    if not bad_schedule.empty:
        raise ValueError("factor_returns 存在不完整六因子月份或非T+1交易日期")
    return features.sort_values("signal_period"), returns, schedule.sort_values("signal_period")


def _normalise_ml_probabilities(
    stage_two_probabilities: object,
    factor_order: Sequence[str],
) -> pd.DataFrame:
    if not isinstance(stage_two_probabilities, pd.DataFrame):
        stage_two_probabilities = getattr(stage_two_probabilities, "rolling_probabilities", None)
    if not isinstance(stage_two_probabilities, pd.DataFrame):
        raise TypeError("stage_two_probabilities 必须是DataFrame或StageTwoFactorResult")
    required = {"predictor_date", "prediction_date"}
    if missing := required.difference(stage_two_probabilities.columns):
        raise KeyError(f"m3概率表缺少字段: {sorted(missing)}")

    raw_columns = [f"raw_probability_{factor}" for factor in factor_order]
    weight_columns = [f"weight_{factor}" for factor in factor_order]
    has_raw = set(raw_columns).issubset(stage_two_probabilities.columns)
    has_weight = set(weight_columns).issubset(stage_two_probabilities.columns)
    if not has_raw and not has_weight:
        raise KeyError("m3概率表既无六个raw_probability列，也无六个weight列")

    keep = ["predictor_date", "prediction_date", *(raw_columns if has_raw else weight_columns)]
    probabilities = stage_two_probabilities.loc[:, keep].copy()
    probabilities["predictor_date"] = pd.to_datetime(probabilities["predictor_date"]).dt.normalize()
    probabilities["prediction_date"] = pd.to_datetime(probabilities["prediction_date"]).dt.normalize()
    probabilities["signal_period"] = probabilities["predictor_date"].dt.to_period("M")
    probabilities["prediction_period"] = probabilities["prediction_date"].dt.to_period("M")
    if probabilities["signal_period"].duplicated().any():
        raise ValueError("m3概率表同一预测信号月存在重复记录")
    if not (probabilities["prediction_period"] == probabilities["signal_period"] + 1).all():
        raise ValueError("m3 prediction_date 未严格指向 predictor_date 的下一自然月")

    source_columns = raw_columns if has_raw else weight_columns
    numeric = probabilities[source_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or (~np.isfinite(numeric.to_numpy())).any():
        raise ValueError("m3六因子概率含缺失或非有限值")
    if numeric.lt(0.0).any().any():
        raise ValueError("m3六因子概率不得为负")
    sums = numeric.sum(axis=1)
    fallback = sums.le(0.0)
    normalised = numeric.div(sums.where(~fallback, 1.0), axis=0)
    normalised.loc[fallback, :] = 1.0 / len(factor_order)
    normalised.columns = [f"ml_weight_{factor}" for factor in factor_order]
    probabilities = pd.concat([probabilities, normalised], axis=1)
    probabilities["ml_probability_sum"] = sums
    probabilities["ml_equal_weight_fallback"] = fallback
    probabilities["ml_probability_source"] = "raw_probability" if has_raw else "m3_normalized_weight"
    if not np.allclose(normalised.sum(axis=1), 1.0, rtol=0.0, atol=1.0e-12):
        raise AssertionError("ML概率归一化后权重和不为1")
    return probabilities.sort_values("signal_period").reset_index(drop=True)


def _load_benchmark_prices(
    config: ChinaFactorTimingConfig,
    start: pd.Timestamp,
    end: pd.Timestamp,
    benchmark_prices: pd.DataFrame | None,
) -> pd.DataFrame:
    if benchmark_prices is None:
        benchmark_prices = pd.read_parquet(
            config.path("index_trade"),
            columns=["index_code", "date", "close"],
            filters=[
                ("index_code", "==", config.benchmark_index_code),
                ("date", ">=", start),
                ("date", "<=", end),
            ],
        )
    required = {"date", "close"}
    if missing := required.difference(benchmark_prices.columns):
        raise KeyError(f"中证800日行情缺少字段: {sorted(missing)}")
    prices = benchmark_prices.copy()
    if "index_code" in prices:
        prices = prices.loc[prices["index_code"].astype(str).eq(config.benchmark_index_code)]
    prices["date"] = pd.to_datetime(prices["date"]).dt.normalize()
    prices["close"] = pd.to_numeric(prices["close"], errors="coerce")
    prices = prices.loc[prices["date"].between(start, end), ["date", "close"]]
    if prices["date"].duplicated().any():
        raise ValueError("中证800日行情同一交易日存在重复收盘价")
    return prices.sort_values("date").reset_index(drop=True)


def _benchmark_returns(
    schedule: pd.DataFrame,
    features: pd.DataFrame,
    config: ChinaFactorTimingConfig,
    benchmark_prices: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    prices = _load_benchmark_prices(
        config,
        schedule["execution_date"].min(),
        schedule["return_date"].max(),
        benchmark_prices,
    )
    entry = prices.rename(columns={"date": "execution_date", "close": "entry_close"})
    exit_ = prices.rename(columns={"date": "return_date", "close": "exit_close"})
    benchmark = schedule.merge(entry, on="execution_date", how="left").merge(
        exit_, on="return_date", how="left"
    )
    if benchmark[["entry_close", "exit_close"]].isna().any().any():
        raise ValueError("中证800在m1实际执行日或收益截止日缺少收盘价")
    if benchmark[["entry_close", "exit_close"]].le(0.0).any().any():
        raise ValueError("中证800执行价必须为正")
    benchmark["gross_return"] = benchmark["exit_close"] / benchmark["entry_close"] - 1.0

    reference = features.loc[:, ["signal_period", "signal_date", "benchmark_return"]].copy()
    reference["source_signal_period"] = reference["signal_period"] - 1
    reference = reference.rename(
        columns={
            "signal_period": "benchmark_reference_period",
            "signal_date": "benchmark_reference_date",
            "benchmark_return": "benchmark_monthly_reference_return",
        }
    )
    benchmark = benchmark.merge(
        reference,
        left_on="signal_period",
        right_on="source_signal_period",
        how="left",
    )
    alignment = benchmark.loc[
        :,
        [
            "signal_date",
            "execution_date",
            "return_date",
            "entry_close",
            "exit_close",
            "benchmark_reference_date",
            "benchmark_monthly_reference_return",
        ],
    ].copy()
    alignment["strict_next_trading_period"] = (
        alignment["execution_date"].gt(alignment["signal_date"])
        & alignment["return_date"].gt(alignment["execution_date"])
    )
    return benchmark, alignment


def _build_weight_detail(
    schedule: pd.DataFrame,
    features: pd.DataFrame,
    probabilities: pd.DataFrame,
    factor_order: Sequence[str],
    settings: PortfolioSettings,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cycle = schedule.merge(
        features[["signal_period", "business_cycle"]], on="signal_period", how="left"
    )
    if cycle["business_cycle"].isna().any():
        raise ValueError("入选OOS月份缺少时点商业周期标签")
    unknown = sorted(set(cycle["business_cycle"]) - set(BUSINESS_CYCLE_DIRECTIONS))
    if unknown:
        raise ValueError(f"存在R9未定义商业周期标签: {unknown}")

    rows: list[dict[str, object]] = []
    equal = pd.Series(1.0 / len(factor_order), index=factor_order)
    probability_by_period = probabilities.set_index("signal_period")
    for item in cycle.itertuples(index=False):
        common = {
            "signal_period": item.signal_period,
            "signal_date": item.signal_date,
            "execution_date": item.execution_date,
            "return_date": item.return_date,
            "business_cycle": item.business_cycle,
        }
        cycle_weight = business_cycle_weights(
            item.business_cycle, factor_order, settings.active_tilt_budget
        )
        probability_row = probability_by_period.loc[item.signal_period]
        ml_weight = pd.Series(
            {factor: probability_row[f"ml_weight_{factor}"] for factor in factor_order}
        )
        for portfolio, weights, source in (
            (PORTFOLIO_EQUAL, equal, "fixed_1_over_6"),
            (PORTFOLIO_CYCLE, cycle_weight, "point_in_time_business_cycle_R9"),
            (PORTFOLIO_ML, ml_weight, str(probability_row["ml_probability_source"])),
        ):
            for factor in factor_order:
                rows.append(
                    {
                        **common,
                        "portfolio": portfolio,
                        "factor": factor,
                        "signal_weight": float(weights[factor]),
                        "execution_weight": float(weights[factor]),
                        "weight_source": source,
                        "ml_probability_sum": (
                            float(probability_row["ml_probability_sum"])
                            if portfolio == PORTFOLIO_ML
                            else np.nan
                        ),
                        "ml_equal_weight_fallback": (
                            bool(probability_row["ml_equal_weight_fallback"])
                            if portfolio == PORTFOLIO_ML
                            else False
                        ),
                    }
                )
    weights = pd.DataFrame(rows)
    benchmark_weights = schedule.assign(
        portfolio=PORTFOLIO_CSI800,
        factor=PORTFOLIO_CSI800,
        signal_weight=1.0,
        execution_weight=1.0,
        business_cycle=pd.NA,
        weight_source="index_benchmark",
        ml_probability_sum=np.nan,
        ml_equal_weight_fallback=False,
    )
    weights = pd.concat(
        [weights, benchmark_weights.loc[:, weights.columns]], ignore_index=True
    ).sort_values(["portfolio", "execution_date", "factor"])
    sums = weights.groupby(["portfolio", "signal_period"])["execution_weight"].sum()
    if (weights["execution_weight"] < -1.0e-12).any() or not np.allclose(
        sums.to_numpy(), 1.0, rtol=0.0, atol=1.0e-12
    ):
        raise AssertionError("组合执行权重必须非负且逐月和为1")
    labels = cycle.loc[
        :, ["signal_period", "signal_date", "execution_date", "return_date", "business_cycle"]
    ].copy()
    labels["label_source"] = "m1_point_in_time"
    return weights.reset_index(drop=True), labels


def _factor_portfolio_returns(
    weights: pd.DataFrame,
    factor_returns: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_weights = weights.loc[weights["portfolio"].ne(PORTFOLIO_CSI800)].copy()
    merged = factor_weights.merge(
        factor_returns[
            ["signal_period", "signal_date", "execution_date", "return_date", "factor", "factor_return"]
        ],
        on=["signal_period", "signal_date", "execution_date", "return_date", "factor"],
        how="left",
        validate="many_to_one",
    )
    if merged["factor_return"].isna().any():
        raise ValueError("组合权重无法与六因子收益完整对齐")
    merged["weighted_return"] = merged["execution_weight"] * merged["factor_return"]
    portfolio_returns = merged.groupby(
        ["portfolio", "signal_period", "signal_date", "execution_date", "return_date"],
        as_index=False,
    ).agg(gross_return=("weighted_return", "sum"))
    return merged, portfolio_returns


def _add_turnover_and_costs(
    weights: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    settings: PortfolioSettings,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail = weights.sort_values(["portfolio", "factor", "execution_date"]).copy()
    detail["previous_execution_weight"] = detail.groupby(
        ["portfolio", "factor"], sort=False
    )["execution_weight"].shift(fill_value=0.0)
    detail["weight_change"] = detail["execution_weight"] - detail["previous_execution_weight"]
    detail["buy_turnover_contribution"] = detail["weight_change"].clip(lower=0.0)
    detail["sell_turnover_contribution"] = -detail["weight_change"].clip(upper=0.0)
    turnover = detail.groupby(
        ["portfolio", "signal_period", "signal_date", "execution_date", "return_date"],
        as_index=False,
    ).agg(
        buy_turnover=("buy_turnover_contribution", "sum"),
        sell_turnover=("sell_turnover_contribution", "sum"),
    )
    turnover["turnover"] = turnover["buy_turnover"] + turnover["sell_turnover"]
    turnover["buy_cost"] = turnover["buy_turnover"] * settings.buy_cost_rate
    turnover["sell_cost"] = turnover["sell_turnover"] * (
        settings.sell_cost_rate + settings.sell_stamp_tax_rate
    )
    turnover["transaction_cost"] = turnover["buy_cost"] + turnover["sell_cost"]
    result = portfolio_returns.merge(
        turnover,
        on=["portfolio", "signal_period", "signal_date", "execution_date", "return_date"],
        how="left",
        validate="one_to_one",
    )
    benchmark = result["portfolio"].eq(PORTFOLIO_CSI800)
    result.loc[benchmark, ["buy_cost", "sell_cost", "transaction_cost"]] = 0.0
    result["net_return"] = result["gross_return"] - result["transaction_cost"]
    result["cost_basis"] = np.where(
        benchmark,
        "index_benchmark_no_stock_cost",
        "factor_sleeve_stock_cost",
    )
    result["main_result_return"] = result["gross_return"]
    result["main_result_basis"] = "gross"
    return detail.reset_index(drop=True), result.sort_values(
        ["return_date", "portfolio"]
    ).reset_index(drop=True)


def _build_chart_data(portfolio_returns: pd.DataFrame) -> pd.DataFrame:
    chart = portfolio_returns.loc[
        :, ["portfolio", "signal_date", "execution_date", "return_date", "gross_return", "net_return"]
    ].copy()
    chart = chart.sort_values(["portfolio", "return_date"])
    chart["gross_nav"] = chart.groupby("portfolio", sort=False)["gross_return"].transform(
        lambda values: (1.0 + values).cumprod()
    )
    chart["net_nav"] = chart.groupby("portfolio", sort=False)["net_return"].transform(
        lambda values: (1.0 + values).cumprod()
    )
    chart["gross_cumulative_return"] = chart["gross_nav"] - 1.0
    chart["net_cumulative_return"] = chart["net_nav"] - 1.0
    chart["chart_name"] = "group_cumulative_returns"
    return chart.reset_index(drop=True)


def run_portfolio_construction(
    monthly_features: pd.DataFrame,
    factor_returns: pd.DataFrame,
    stage_two_probabilities: object,
    *,
    config: ChinaFactorTimingConfig | None = None,
    settings: PortfolioSettings | None = None,
    benchmark_prices: pd.DataFrame | None = None,
) -> PortfolioResult:
    """构造四类可比组合；正式主结果始终使用毛收益。"""
    cfg = config or ChinaFactorTimingConfig()
    params = settings or PortfolioSettings()
    _validate_settings(params)
    factor_order = tuple(cfg.factor_names)
    features, returns, schedule = _normalise_m1_inputs(
        monthly_features, factor_returns, factor_order
    )
    probabilities = _normalise_ml_probabilities(stage_two_probabilities, factor_order)

    common_periods = sorted(
        set(schedule["signal_period"]).intersection(probabilities["signal_period"])
    )
    if not common_periods:
        raise ValueError("m1因子收益与m3滚动概率没有共同可实现信号月")
    schedule = schedule.loc[schedule["signal_period"].isin(common_periods)].copy()
    returns = returns.loc[returns["signal_period"].isin(common_periods)].copy()
    probabilities = probabilities.loc[probabilities["signal_period"].isin(common_periods)].copy()

    weights, cycle_labels = _build_weight_detail(
        schedule, features, probabilities, factor_order, params
    )
    benchmark, alignment = _benchmark_returns(
        schedule, features, cfg, benchmark_prices
    )
    factor_detail, factor_portfolios = _factor_portfolio_returns(weights, returns)
    benchmark_portfolio = benchmark.assign(portfolio=PORTFOLIO_CSI800).loc[
        :, ["portfolio", "signal_period", "signal_date", "execution_date", "return_date", "gross_return"]
    ]
    benchmark_detail = weights.loc[weights["portfolio"].eq(PORTFOLIO_CSI800)].merge(
        benchmark_portfolio,
        on=["portfolio", "signal_period", "signal_date", "execution_date", "return_date"],
        how="left",
        validate="one_to_one",
    ).rename(columns={"gross_return": "factor_return"})
    benchmark_detail["weighted_return"] = (
        benchmark_detail["execution_weight"] * benchmark_detail["factor_return"]
    )
    return_detail = pd.concat([factor_detail, benchmark_detail], ignore_index=True)
    gross = pd.concat([factor_portfolios, benchmark_portfolio], ignore_index=True)
    weight_detail, portfolio_returns = _add_turnover_and_costs(return_detail, gross, params)
    alignment["m1_m3_common_period"] = True
    alignment["portfolio_count"] = 4
    return PortfolioResult(
        portfolio_returns=portfolio_returns,
        weight_detail=weight_detail,
        business_cycle_labels=cycle_labels.reset_index(drop=True),
        cycle_direction_matrix=cycle_direction_matrix(factor_order),
        chart_data=_build_chart_data(portfolio_returns),
        alignment_audit=alignment.reset_index(drop=True),
    )


__all__ = [
    "BUSINESS_CYCLE_DIRECTIONS",
    "PORTFOLIO_CSI800",
    "PORTFOLIO_CYCLE",
    "PORTFOLIO_EQUAL",
    "PORTFOLIO_ML",
    "PortfolioResult",
    "PortfolioSettings",
    "business_cycle_weights",
    "cycle_direction_matrix",
    "run_portfolio_construction",
]
