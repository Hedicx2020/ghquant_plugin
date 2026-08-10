"""m5：中国市场严格样本外结果包。

本模块只消费 m1--m4 已生成的结构化对象，不参与训练、调参或组合构造。
原研报的美国市场数值始终作为迁移参照单独保存；中国结果与其差异不解释为
复现误差。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sklearn.metrics import accuracy_score, precision_score, recall_score

from common.ml_reporting import write_json
from common.utils import (
    calculate_annualized_return,
    calculate_annualized_volatility,
    calculate_max_drawdown,
    calculate_sharpe,
)

from .config import ChinaFactorTimingConfig
from .portfolio import (
    BUSINESS_CYCLE_DIRECTIONS,
    PORTFOLIO_CSI800,
    PORTFOLIO_CYCLE,
    PORTFOLIO_EQUAL,
    PORTFOLIO_ML,
    PortfolioResult,
    PortfolioSettings,
)
from .strategy import MAX_EXIT_DELAY_TRADING_DAYS


REPORT_ID = "r003_equity_factor_timing_cn"
EXPECTED_OOS_MONTHS = 33
EXCEL_MAX_DATA_ROWS = 1_048_575
AUDIT_HASH_DECIMAL_PLACES = 12
AUDIT_HASH_NULL_TOKEN = "<NA>"
AUDIT_HASH_DATE_COLUMNS = frozenset(
    {
        "signal_date", "prediction_date", "intended_execution_date", "actual_execution_date",
        "intended_return_date", "actual_return_date", "label_available_date",
        "exit_search_horizon_date",
    }
)
AUDIT_HASH_BOOLEAN_COLUMNS = frozenset(
    {
        "can_execute", "executed", "execution_is_st", "execution_no_volume",
        "execution_is_suspended", "execution_is_limit_up", "execution_is_limit_down",
        "exit_executed", "nav_marked",
    }
)
AUDIT_HASH_NUMERIC_COLUMNS = frozenset(
    {"weight", "exit_delay_days", "exit_delay_trading_days"}
)
RESULT_ARTIFACT_FILENAMES = (
    "backtest_summary.xlsx",
    "model_details.xlsx",
    "probability_details.xlsx",
    "weights_detail.xlsx",
    "returns_detail.xlsx",
    "metrics.json",
    "comparison.json",
    "oos_evidence_manifest.json",
    "oos_evidence_checklist.md",
    "run_log.md",
    "feature_importance.png",
    "ic_series.png",
    "group_cumulative_returns.png",
    "train_val_loss.png",
    "prediction_scatter.png",
    "drawdown.png",
)
PRIMARY_BLUE = "#1f77b4"
PRIMARY_RED = "#d62728"
PORTFOLIO_ORDER = (
    PORTFOLIO_CSI800,
    PORTFOLIO_EQUAL,
    PORTFOLIO_CYCLE,
    PORTFOLIO_ML,
)
PORTFOLIO_LABELS = {
    PORTFOLIO_CSI800: "中证800",
    PORTFOLIO_EQUAL: "六因子1/N",
    PORTFOLIO_CYCLE: "商业周期15%倾斜",
    PORTFOLIO_ML: "ML胜出概率",
}
REPORT_METHOD_MAP = {
    "Russell 1000": PORTFOLIO_CSI800,
    "Equal Weighted": PORTFOLIO_EQUAL,
    "Business Cycle Tilt": PORTFOLIO_CYCLE,
    "ML Approach": PORTFOLIO_ML,
}
REPORT_R10_VALUES: dict[str, dict[str, float | None]] = {
    "Russell 1000": {
        "annualized_return": 0.0840,
        "annualized_volatility": 0.1549,
        "sharpe": 0.52,
        "annualized_excess_return": None,
        "tracking_error": None,
        "information_ratio": None,
    },
    "Equal Weighted": {
        "annualized_return": 0.0863,
        "annualized_volatility": 0.1519,
        "sharpe": 0.54,
        "annualized_excess_return": 0.0018,
        "tracking_error": 0.0240,
        "information_ratio": 0.07,
    },
    "Business Cycle Tilt": {
        "annualized_return": 0.0984,
        "annualized_volatility": 0.1606,
        "sharpe": 0.59,
        "annualized_excess_return": 0.0150,
        "tracking_error": 0.0395,
        "information_ratio": 0.36,
    },
    "ML Approach": {
        "annualized_return": 0.1147,
        "annualized_volatility": 0.1681,
        "sharpe": 0.66,
        "annualized_excess_return": 0.0289,
        "tracking_error": 0.0668,
        "information_ratio": 0.45,
    },
}
METRIC_LABELS = {
    "annualized_return": "年化收益率",
    "annualized_volatility": "年化波动率",
    "sharpe": "Sharpe",
    "max_drawdown": "最大回撤",
    "annualized_excess_return": "相对基准年化超额收益",
    "tracking_error": "年化跟踪误差",
    "information_ratio": "信息比率",
    "average_monthly_turnover": "月均双向换手",
    "annualized_turnover": "年化双向换手",
}


@dataclass(frozen=True)
class ReportPackage:
    """m5 产物路径与结构化指标。"""

    paths: dict[str, Path]
    metrics: dict[str, Any]
    comparison: dict[str, Any]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_run_log(path: Path, lines: Sequence[str]) -> None:
    """追加UTF-8运行记录；由 main 在开始/失败、报告层在完成时调用。"""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        if destination.stat().st_size:
            handle.write("\n")
        handle.write("\n".join(lines).rstrip() + "\n")


def _finite_or_nan(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number if np.isfinite(number) else np.nan


def _performance_metrics(returns: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(returns, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return {
            "observations": 0,
            "annualized_return": np.nan,
            "annualized_volatility": np.nan,
            "sharpe": np.nan,
            "max_drawdown": np.nan,
        }
    nav = (1.0 + clean).cumprod()
    return {
        "observations": int(len(clean)),
        "annualized_return": calculate_annualized_return(clean, periods_per_year=12),
        "annualized_volatility": calculate_annualized_volatility(clean, periods_per_year=12),
        "sharpe": calculate_sharpe(clean, periods_per_year=12),
        "max_drawdown": calculate_max_drawdown(nav),
    }


def _portfolio_metric_table(portfolio: PortfolioResult, return_column: str) -> pd.DataFrame:
    returns = portfolio.portfolio_returns.copy()
    required = {"portfolio", "signal_period", return_column, "turnover", "transaction_cost"}
    missing = required.difference(returns.columns)
    if missing:
        raise KeyError(f"m4 portfolio_returns 缺少字段: {sorted(missing)}")
    if returns.duplicated(["portfolio", "signal_period"]).any():
        raise ValueError("m4组合收益同一组合/信号月存在重复记录")
    rows: list[dict[str, Any]] = []
    benchmark = returns.loc[returns["portfolio"].eq(PORTFOLIO_CSI800), [
        "signal_period", return_column
    ]].rename(columns={return_column: "benchmark_return"})
    for portfolio_name in PORTFOLIO_ORDER:
        frame = returns.loc[returns["portfolio"].eq(portfolio_name)].sort_values(
            "signal_period"
        )
        if frame.empty:
            raise ValueError(f"m4缺少组合: {portfolio_name}")
        metrics = _performance_metrics(frame[return_column])
        metrics.update(
            {
                "portfolio": portfolio_name,
                "portfolio_label": PORTFOLIO_LABELS[portfolio_name],
                "return_basis": "gross_primary" if return_column == "gross_return" else "net_cost_supplement",
                "average_monthly_turnover": float(frame["turnover"].mean()),
                "annualized_turnover": float(frame["turnover"].mean() * 12.0),
                "total_transaction_cost": float(frame["transaction_cost"].sum()),
            }
        )
        if portfolio_name == PORTFOLIO_CSI800:
            metrics.update(
                {
                    "annualized_excess_return": np.nan,
                    "tracking_error": np.nan,
                    "information_ratio": np.nan,
                }
            )
        else:
            aligned = frame[["signal_period", return_column]].merge(
                benchmark, on="signal_period", how="inner", validate="one_to_one"
            )
            relative = (1.0 + aligned[return_column]) / (1.0 + aligned["benchmark_return"]) - 1.0
            excess_return = calculate_annualized_return(relative, periods_per_year=12)
            tracking_error = calculate_annualized_volatility(relative, periods_per_year=12)
            metrics.update(
                {
                    "annualized_excess_return": excess_return,
                    "tracking_error": tracking_error,
                    "information_ratio": (
                        excess_return / tracking_error
                        if np.isfinite(tracking_error) and tracking_error > 0.0
                        else np.nan
                    ),
                }
            )
        rows.append(metrics)
    return pd.DataFrame(rows)


def _classification_metrics(stage_one: Any) -> dict[str, Any]:
    rolling = stage_one.rolling_predictions.copy()
    valid = rolling.dropna(subset=["actual_regime", "predicted_regime"])
    if valid.empty:
        oos = {
            "observations": 0,
            "accuracy": np.nan,
            "precision_weighted": np.nan,
            "recall_weighted": np.nan,
            "precision_macro": np.nan,
            "recall_macro": np.nan,
        }
    else:
        actual = valid["actual_regime"].astype(str)
        predicted = valid["predicted_regime"].astype(str)
        oos = {
            "observations": int(len(valid)),
            "accuracy": accuracy_score(actual, predicted),
            "precision_weighted": precision_score(
                actual, predicted, average="weighted", zero_division=0
            ),
            "recall_weighted": recall_score(
                actual, predicted, average="weighted", zero_division=0
            ),
            "precision_macro": precision_score(
                actual, predicted, average="macro", zero_division=0
            ),
            "recall_macro": recall_score(
                actual, predicted, average="macro", zero_division=0
            ),
        }
    fold = stage_one.fold_metrics
    columns = [
        "accuracy",
        "precision_weighted",
        "recall_weighted",
        "precision_macro",
        "recall_macro",
    ]
    cv_mean = {
        column: float(pd.to_numeric(fold[column], errors="coerce").mean())
        for column in columns
        if column in fold
    }
    cv_mean["fold_rows"] = int(len(fold))
    return {"oos": oos, "rolling_cv_mean": cv_mean}


def _factor_prediction_metrics(stage_two: Any) -> dict[str, Any]:
    frame = stage_two.prediction_metrics.copy()
    available = frame.loc[frame["label_available"].fillna(False)].copy()
    rank_ic = pd.to_numeric(available["rank_ic"], errors="coerce")
    top_hit = available["top_hit"].astype("boolean")
    valid_hit = top_hit.dropna()
    return {
        "label_available_months": int(len(available)),
        "rank_ic_observations": int(rank_ic.notna().sum()),
        "mean_rank_ic": float(rank_ic.mean()),
        "median_rank_ic": float(rank_ic.median()),
        "rank_ic_positive_rate": float(rank_ic.gt(0.0).mean()) if rank_ic.notna().any() else np.nan,
        "top_hit_observations": int(len(valid_hit)),
        "top_factor_hit_rate": float(valid_hit.astype(bool).mean()) if len(valid_hit) else np.nan,
    }


def _expected_periods(prediction_start: pd.Timestamp, end: pd.Timestamp) -> pd.PeriodIndex:
    return pd.period_range(prediction_start.to_period("M"), end.to_period("M"), freq="M")


def _coverage_and_training_evidence(
    stage_one: Any,
    stage_two: Any,
    portfolio: PortfolioResult,
    prediction_start: pd.Timestamp,
    end: pd.Timestamp,
    config: ChinaFactorTimingConfig,
) -> tuple[dict[str, Any], pd.DataFrame]:
    expected = _expected_periods(prediction_start, end)
    prediction_period_series = pd.to_datetime(
        stage_two.rolling_probabilities["prediction_date"]
    ).dt.to_period("M")
    if prediction_period_series.duplicated().any():
        raise AssertionError("m3同一目标月存在重复OOS概率行")
    predicted = pd.PeriodIndex(
        prediction_period_series.unique(),
        freq="M",
    ).sort_values()
    portfolio_target_period = portfolio.portfolio_returns["signal_period"] + 1
    portfolio_counts = (
        portfolio.portfolio_returns.assign(_target_period=portfolio_target_period)
        .groupby("_target_period")["portfolio"]
        .nunique()
    )
    if not portfolio_counts.eq(len(PORTFOLIO_ORDER)).all():
        bad = portfolio_counts.loc[~portfolio_counts.eq(len(PORTFOLIO_ORDER))]
        raise AssertionError(f"部分OOS月份未同时包含四类组合: {bad.to_dict()}")
    portfolio_periods = pd.PeriodIndex(
        portfolio_target_period.unique(), freq="M"
    ).sort_values()
    missing_prediction = expected.difference(predicted)
    missing_portfolio = expected.difference(portfolio_periods)
    unexpected_prediction = predicted.difference(expected)
    unexpected_portfolio = portfolio_periods.difference(expected)
    if len(missing_prediction) or len(missing_portfolio):
        raise AssertionError(
            "OOS月份覆盖不完整: "
            f"概率缺失={missing_prediction.astype(str).tolist()}, "
            f"组合缺失={missing_portfolio.astype(str).tolist()}"
        )
    if len(unexpected_prediction) or len(unexpected_portfolio):
        raise AssertionError("结果包含指定OOS区间之外的预测或组合月份")

    first_period = expected[0]
    expected_train_start = (first_period - config.turbulence_window_months).to_timestamp("M")
    expected_train_end = (first_period - 1).to_timestamp("M")
    stage_one_audit = stage_one.training_audit.copy()
    first_stage_one = stage_one_audit.loc[
        pd.to_datetime(stage_one_audit["prediction_date"]).dt.to_period("M").eq(first_period)
    ]
    stage_two_audit = stage_two.training_audit.copy()
    first_stage_two = stage_two_audit.loc[
        pd.to_datetime(stage_two_audit["prediction_date"]).dt.to_period("M").eq(first_period)
    ]
    if first_stage_one.empty or first_stage_two.empty:
        raise AssertionError("首个OOS月缺少m2或m3训练窗审计")
    first_stage_one_start = pd.to_datetime(first_stage_one["train_target_start"]).min()
    first_stage_one_end = pd.to_datetime(first_stage_one["train_target_end"]).max()
    first_stage_two_start = pd.to_datetime(first_stage_two["train_window_start"]).min()
    first_stage_two_end = pd.to_datetime(first_stage_two["train_window_end"]).max()
    checks = {
        "m2_first_window": (
            first_stage_one_start.to_period("M") == expected_train_start.to_period("M")
            and first_stage_one_end.to_period("M") == expected_train_end.to_period("M")
        ),
        "m3_first_window": (
            first_stage_two_start.to_period("M") == expected_train_start.to_period("M")
            and first_stage_two_end.to_period("M") == expected_train_end.to_period("M")
        ),
        "m2_all_84_months": bool(stage_one_audit["train_rows"].eq(84).all()),
        "m3_all_84_months": bool(stage_two_audit["train_candidate_months"].eq(84).all()),
        "m2_strict_past": bool(
            (pd.to_datetime(stage_one_audit["train_target_end"]) < pd.to_datetime(stage_one_audit["prediction_date"])).all()
        ),
        "m3_strict_past": bool(
            (pd.to_datetime(stage_two_audit["train_window_end"]) < pd.to_datetime(stage_two_audit["prediction_date"])).all()
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise AssertionError(f"滚动样本外训练窗证据不满足冻结口径: {failed}")

    is_formal_default = bool(
        first_period == pd.Timestamp(config.oos_start).to_period("M")
        and expected[-1] == pd.Timestamp(config.sample_end).to_period("M")
    )
    if is_formal_default and len(expected) != EXPECTED_OOS_MONTHS:
        raise AssertionError("正式默认OOS窗口必须严格包含33个月")
    coverage = {
        "prediction_start": first_period.to_timestamp("M"),
        "prediction_end": expected[-1].to_timestamp("M"),
        "expected_months": int(len(expected)),
        "probability_months": int(len(predicted)),
        "portfolio_months": int(len(portfolio_periods)),
        "probability_coverage_rate": float(len(predicted) / len(expected)),
        "portfolio_coverage_rate": float(len(portfolio_periods) / len(expected)),
        "formal_default_expected_months": EXPECTED_OOS_MONTHS,
        "is_formal_default_window": is_formal_default,
        "first_training_window_expected_start": expected_train_start,
        "first_training_window_expected_end": expected_train_end,
        "m2_first_training_start": first_stage_one_start,
        "m2_first_training_end": first_stage_one_end,
        "m3_first_training_start": first_stage_two_start,
        "m3_first_training_end": first_stage_two_end,
        "training_checks": checks,
    }
    evidence = pd.DataFrame(
        [
            {
                "check_id": "OOS-01",
                "check": "概率逐月完整覆盖指定OOS区间",
                "observed": f"{len(predicted)}/{len(expected)}",
                "passed": len(predicted) == len(expected),
                "evidence_source": "m3.rolling_probabilities",
            },
            {
                "check_id": "OOS-02",
                "check": "四组合逐月完整覆盖指定OOS区间",
                "observed": f"{len(portfolio_periods)}/{len(expected)}",
                "passed": len(portfolio_periods) == len(expected),
                "evidence_source": "m4.portfolio_returns",
            },
            {
                "check_id": "OOS-03",
                "check": "首月m2训练窗为此前连续84个月",
                "observed": f"{first_stage_one_start:%Y-%m}至{first_stage_one_end:%Y-%m}",
                "passed": checks["m2_first_window"],
                "evidence_source": "m2.training_audit",
            },
            {
                "check_id": "OOS-04",
                "check": "首月m3训练窗为此前连续84个月",
                "observed": f"{first_stage_two_start:%Y-%m}至{first_stage_two_end:%Y-%m}",
                "passed": checks["m3_first_window"],
                "evidence_source": "m3.training_audit",
            },
            {
                "check_id": "OOS-05",
                "check": "全部m2/m3训练窗严格早于预测月",
                "observed": "m2/m3审计逐行断言",
                "passed": all(checks.values()),
                "evidence_source": "m2/m3.training_audit",
            },
            {
                "check_id": "OOS-06",
                "check": "最后OOS月不晚于冻结样本终点",
                "observed": str(expected[-1]),
                "passed": expected[-1] <= pd.Timestamp(config.sample_end).to_period("M"),
                "evidence_source": "config.sample_end",
            },
        ]
    )
    return coverage, evidence


def _comparison_table(gross_metrics: pd.DataFrame) -> pd.DataFrame:
    china = gross_metrics.set_index("portfolio")
    rows: list[dict[str, Any]] = []
    for report_method, report_values in REPORT_R10_VALUES.items():
        portfolio_name = REPORT_METHOD_MAP[report_method]
        for metric, report_value in report_values.items():
            china_value = _finite_or_nan(china.loc[portfolio_name, metric])
            has_report_value = report_value is not None
            rows.append(
                {
                    "element_id": "R10",
                    "metric": metric,
                    "metric_label": METRIC_LABELS[metric],
                    "report_market": "美国",
                    "report_method": report_method,
                    "report_value": report_value,
                    "china_market": "中国A股",
                    "china_portfolio": portfolio_name,
                    "china_portfolio_label": PORTFOLIO_LABELS[portfolio_name],
                    "china_oos_value": china_value,
                    "difference": china_value - report_value if has_report_value else np.nan,
                    "difference_status": (
                        "market_transplant_context_only" if has_report_value else "report_value_na"
                    ),
                    "explanation": (
                        "中国市场迁移与美国原研报的数值差异仅作背景参照，不是复现误差"
                        if has_report_value
                        else "原研报该项为n/a，禁止推算差异"
                    ),
                }
            )
    return pd.DataFrame(rows)


def _build_prediction_scatter_data(stage_two: Any) -> pd.DataFrame:
    """按预测月份键连接概率与实际收益，拒绝交易月末/自然月末错配。"""
    probabilities = stage_two.rolling_probabilities.copy()
    factor_names = [
        column.removeprefix("raw_probability_")
        for column in probabilities.columns
        if column.startswith("raw_probability_")
    ]
    if len(factor_names) != 6 or len(set(factor_names)) != 6:
        raise AssertionError("预测散点必须包含唯一的六因子概率列")
    probability_long = probabilities.melt(
        id_vars=["predictor_date", "prediction_date", "model_regime"],
        value_vars=[f"raw_probability_{factor}" for factor in factor_names],
        var_name="probability_name",
        value_name="predicted_probability",
    )
    probability_long["factor"] = probability_long["probability_name"].str.removeprefix(
        "raw_probability_"
    )
    probability_long["predictor_date"] = pd.to_datetime(
        probability_long["predictor_date"]
    ).dt.normalize()
    probability_long["prediction_date"] = pd.to_datetime(
        probability_long["prediction_date"]
    ).dt.normalize()
    probability_long["predictor_period"] = probability_long["predictor_date"].dt.to_period("M")
    probability_long["prediction_period"] = probability_long["prediction_date"].dt.to_period("M")

    actual = stage_two.winner_labels.loc[
        :, ["predictor_date", "prediction_date", "factor", "factor_return", "is_winner"]
    ].copy()
    actual["label_predictor_date"] = pd.to_datetime(actual.pop("predictor_date")).dt.normalize()
    actual["label_prediction_date"] = pd.to_datetime(actual.pop("prediction_date")).dt.normalize()
    actual["predictor_period"] = actual["label_predictor_date"].dt.to_period("M")
    actual["prediction_period"] = actual["label_prediction_date"].dt.to_period("M")
    merge_keys = ["predictor_period", "prediction_period", "factor"]
    if actual.duplicated(merge_keys).any():
        raise AssertionError("胜出标签同一预测月份/因子存在重复记录")
    scatter = probability_long.merge(actual, on=merge_keys, how="left", validate="one_to_one")
    expected_rows = len(probabilities) * len(factor_names)
    if len(scatter) != expected_rows:
        raise AssertionError(
            f"预测散点行数异常: actual={len(scatter)}, expected={expected_rows}"
        )
    missing_actual = scatter[["factor_return", "is_winner"]].isna().any(axis=1)
    if missing_actual.any():
        missing_months = sorted(
            scatter.loc[missing_actual, "prediction_period"].astype(str).unique().tolist()
        )
        raise AssertionError(
            f"预测散点实际收益/赢家缺失: rows={int(missing_actual.sum())}, months={missing_months}"
        )
    per_month = scatter.groupby("prediction_period", observed=True).agg(
        factor_count=("factor", "nunique"),
        winner_count=("is_winner", "sum"),
    )
    if not (per_month["factor_count"].eq(6) & per_month["winner_count"].eq(1)).all():
        raise AssertionError("预测散点每个预测月必须包含六因子实际收益和唯一实际赢家")
    return scatter.sort_values(["prediction_period", "factor"]).reset_index(drop=True)


def _build_chart_data(stage_one: Any, stage_two: Any, portfolio: PortfolioResult) -> dict[str, pd.DataFrame]:
    stage_one_importance = stage_one.feature_importance.copy()
    if "prediction_date" in stage_one_importance:
        stage_one_importance = stage_one_importance.loc[
            stage_one_importance["prediction_date"].isna()
        ]
    stage_one_importance = (
        stage_one_importance.groupby("feature_group", as_index=False)["importance"].mean()
        if not stage_one_importance.empty
        else pd.DataFrame(columns=["feature_group", "importance"])
    )
    stage_one_importance["model_layer"] = "第一阶段市场状态"
    stage_one_importance["model_regime"] = "ALL"

    stage_two_importance = stage_two.feature_importance.copy()
    if "level" in stage_two_importance:
        stage_two_importance = stage_two_importance.loc[
            stage_two_importance["level"].eq("state_group")
        ]
    if not stage_two_importance.empty:
        stage_two_importance = stage_two_importance.groupby(
            ["model_regime", "feature_group"], as_index=False
        )["importance"].mean()
    else:
        stage_two_importance = pd.DataFrame(
            columns=["model_regime", "feature_group", "importance"]
        )
    stage_two_importance["model_layer"] = "第二阶段因子胜出"
    importance = pd.concat(
        [
            stage_one_importance[["model_layer", "model_regime", "feature_group", "importance"]],
            stage_two_importance[["model_layer", "model_regime", "feature_group", "importance"]],
        ],
        ignore_index=True,
    )
    importance["series"] = importance["model_layer"] + "-" + importance["model_regime"].astype(str)

    ic = stage_two.prediction_metrics.loc[
        :, ["prediction_date", "predicted_regime", "model_regime", "rank_ic", "top_hit"]
    ].copy()
    ic["prediction_date"] = pd.to_datetime(ic["prediction_date"])

    cumulative = portfolio.chart_data.copy()
    cumulative["portfolio_label"] = cumulative["portfolio"].map(PORTFOLIO_LABELS)
    drawdown = cumulative.loc[
        :, ["portfolio", "portfolio_label", "signal_date", "execution_date", "return_date", "gross_nav"]
    ].sort_values(["portfolio", "return_date"])
    drawdown["running_peak_including_initial_1"] = drawdown.groupby(
        "portfolio", sort=False
    )["gross_nav"].transform(lambda values: values.cummax().clip(lower=1.0))
    drawdown["gross_drawdown"] = (
        drawdown["gross_nav"] / drawdown["running_peak_including_initial_1"] - 1.0
    )
    if (drawdown["gross_drawdown"] > 1.0e-12).any():
        raise AssertionError("组合回撤时序出现正值，净值峰值计算异常")

    losses = stage_two.train_val_logloss.copy()
    losses["prediction_date"] = pd.to_datetime(losses["prediction_date"])
    loss_data = losses.groupby(
        ["prediction_date", "model_regime"], as_index=False
    )[["train_logloss", "validation_logloss"]].mean()
    loss_data = loss_data.melt(
        id_vars=["prediction_date", "model_regime"],
        value_vars=["train_logloss", "validation_logloss"],
        var_name="loss_split",
        value_name="log_loss",
    )
    loss_data["series"] = loss_data["model_regime"].astype(str) + "-" + loss_data[
        "loss_split"
    ].map({"train_logloss": "训练", "validation_logloss": "验证"})

    scatter = _build_prediction_scatter_data(stage_two)
    return {
        "feature_importance": importance.reset_index(drop=True),
        "ic_series": ic.reset_index(drop=True),
        "group_cumulative_returns": cumulative.reset_index(drop=True),
        "train_val_loss": loss_data.reset_index(drop=True),
        "prediction_scatter": scatter.reset_index(drop=True),
        "drawdown": drawdown.reset_index(drop=True),
    }


def _setup_plot_theme() -> None:
    sns.set_theme(style="whitegrid")
    plt.rcParams["font.sans-serif"] = [
        "PingFang SC",
        "Arial Unicode MS",
        "Heiti TC",
        "SimHei",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def _save_figure(figure: plt.Figure, path: Path) -> None:
    figure.tight_layout()
    figure.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(figure)


def create_charts(output_dir: Path, chart_data: Mapping[str, pd.DataFrame]) -> dict[str, Path]:
    """按 ml 模板生成五张300DPI必需图。"""
    _setup_plot_theme()
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    importance = chart_data["feature_importance"]
    figure, axis = plt.subplots(figsize=(10, 6))
    sns.barplot(data=importance, x="feature_group", y="importance", hue="series", ax=axis)
    axis.set_title("中国市场迁移：模型特征重要性", fontsize=14)
    axis.set_xlabel("特征组", fontsize=12)
    axis.set_ylabel("归一化重要性", fontsize=12)
    axis.tick_params(axis="x", rotation=25)
    axis.legend(fontsize=8)
    paths["feature_importance.png"] = destination / "feature_importance.png"
    _save_figure(figure, paths["feature_importance.png"])

    ic = chart_data["ic_series"]
    figure, axis = plt.subplots(figsize=(12, 6))
    sns.lineplot(data=ic, x="prediction_date", y="rank_ic", marker="o", color=PRIMARY_BLUE, ax=axis)
    axis.axhline(0.0, color="black", linewidth=0.8)
    axis.set_title("中国市场严格样本外月度RankIC", fontsize=14)
    axis.set_xlabel("预测月", fontsize=12)
    axis.set_ylabel("RankIC", fontsize=12)
    paths["ic_series.png"] = destination / "ic_series.png"
    _save_figure(figure, paths["ic_series.png"])

    cumulative = chart_data["group_cumulative_returns"]
    figure, axis = plt.subplots(figsize=(12, 6))
    palette = {
        "中证800": "#555555",
        "六因子1/N": "#2ca02c",
        "商业周期15%倾斜": PRIMARY_RED,
        "ML胜出概率": PRIMARY_BLUE,
    }
    sns.lineplot(
        data=cumulative,
        x="return_date",
        y="gross_cumulative_return",
        hue="portfolio_label",
        hue_order=[PORTFOLIO_LABELS[name] for name in PORTFOLIO_ORDER],
        palette=palette,
        ax=axis,
    )
    axis.axhline(0.0, color="black", linewidth=0.8)
    axis.set_title("四类组合严格样本外累计毛收益", fontsize=14)
    axis.set_xlabel("收益截止日", fontsize=12)
    axis.set_ylabel("累计收益率", fontsize=12)
    axis.legend(title="组合", fontsize=9)
    paths["group_cumulative_returns.png"] = destination / "group_cumulative_returns.png"
    _save_figure(figure, paths["group_cumulative_returns.png"])

    losses = chart_data["train_val_loss"]
    figure, axis = plt.subplots(figsize=(12, 6))
    sns.lineplot(data=losses, x="prediction_date", y="log_loss", hue="series", ax=axis)
    axis.set_title("第二阶段滚动训练与时序验证Log-loss", fontsize=14)
    axis.set_xlabel("预测月", fontsize=12)
    axis.set_ylabel("Log-loss", fontsize=12)
    axis.legend(fontsize=8)
    paths["train_val_loss.png"] = destination / "train_val_loss.png"
    _save_figure(figure, paths["train_val_loss.png"])

    scatter_source = chart_data["prediction_scatter"]
    scatter = scatter_source.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["predicted_probability", "factor_return"]
    )
    if len(scatter) != len(scatter_source):
        raise AssertionError(
            f"预测散点绘图前丢失观测: source={len(scatter_source)}, plotted={len(scatter)}"
        )
    figure, axis = plt.subplots(figsize=(10, 6))
    sns.scatterplot(
        data=scatter,
        x="predicted_probability",
        y="factor_return",
        hue="factor",
        s=28,
        alpha=0.55,
        ax=axis,
    )
    axis.axhline(0.0, color="black", linewidth=0.8)
    axis.set_title("胜出概率与下一月实际因子收益", fontsize=14)
    axis.set_xlabel("预测胜出概率", fontsize=12)
    axis.set_ylabel("实际因子收益率", fontsize=12)
    axis.legend(fontsize=8, ncol=2)
    paths["prediction_scatter.png"] = destination / "prediction_scatter.png"
    _save_figure(figure, paths["prediction_scatter.png"])

    drawdown = chart_data["drawdown"]
    figure, axis = plt.subplots(figsize=(12, 6))
    sns.lineplot(
        data=drawdown,
        x="return_date",
        y="gross_drawdown",
        hue="portfolio_label",
        hue_order=[PORTFOLIO_LABELS[name] for name in PORTFOLIO_ORDER],
        palette=palette,
        ax=axis,
    )
    axis.axhline(0.0, color="black", linewidth=0.8)
    axis.set_title("四类组合严格样本外毛收益回撤", fontsize=14)
    axis.set_xlabel("收益截止日", fontsize=12)
    axis.set_ylabel("回撤", fontsize=12)
    axis.legend(title="组合", fontsize=9)
    paths["drawdown.png"] = destination / "drawdown.png"
    _save_figure(figure, paths["drawdown.png"])
    return paths


def _excel_safe(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in result.columns:
        if pd.api.types.is_datetime64_any_dtype(result[column]):
            result[column] = pd.to_datetime(result[column]).dt.tz_localize(None)
        elif isinstance(result[column].dtype, pd.PeriodDtype):
            result[column] = result[column].astype(str)
        elif result[column].dtype == "object":
            result[column] = result[column].map(
                lambda value: str(value) if isinstance(value, pd.Period) else value
            )
    return result.replace({pd.NA: None})


def _format_workbook(path: Path, image_map: Mapping[str, Path] | None = None) -> None:
    workbook = load_workbook(path)
    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for index, column_cells in enumerate(sheet.columns, start=1):
            values = [
                str(cell.value) for cell in list(column_cells)[:300] if cell.value is not None
            ]
            width = min(max([len(value) for value in values] + [8]) + 2, 42)
            sheet.column_dimensions[get_column_letter(index)].width = width
        if image_map and sheet.title in image_map:
            image = ExcelImage(image_map[sheet.title])
            image.width = 720
            image.height = 360
            sheet.add_image(image, "J2")
    workbook.save(path)


def _write_workbook(path: Path, sheets: Mapping[str, pd.DataFrame]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(destination, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            _excel_safe(frame).to_excel(writer, sheet_name=name[:31], index=False)
    _format_workbook(destination)


def _canonical_audit_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """把内存表和Excel回读表规范成同一组稳定字符串。"""
    canonical = pd.DataFrame(index=frame.index)
    for column in frame.columns:
        values = frame[column]
        if column in AUDIT_HASH_DATE_COLUMNS:
            parsed = pd.to_datetime(values, errors="coerce")
            canonical[column] = parsed.dt.strftime("%Y-%m-%d").fillna(AUDIT_HASH_NULL_TOKEN)
        elif column in AUDIT_HASH_BOOLEAN_COLUMNS:
            def normalize_boolean(value: Any) -> str:
                if pd.isna(value):
                    return AUDIT_HASH_NULL_TOKEN
                normalized = str(value).strip().lower()
                if normalized in {"true", "1", "1.0"}:
                    return "true"
                if normalized in {"false", "0", "0.0"}:
                    return "false"
                raise ValueError(f"审计布尔字段{column}存在非法值: {value!r}")

            canonical[column] = values.map(normalize_boolean)
        elif column in AUDIT_HASH_NUMERIC_COLUMNS:
            numeric = pd.to_numeric(values, errors="coerce").round(AUDIT_HASH_DECIMAL_PLACES)
            canonical[column] = numeric.map(
                lambda value: (
                    AUDIT_HASH_NULL_TOKEN
                    if pd.isna(value)
                    else f"{float(value):.{AUDIT_HASH_DECIMAL_PLACES}f}"
                )
            )
        elif column == "stock_code":
            def normalize_stock_code(value: Any) -> str:
                if pd.isna(value):
                    return AUDIT_HASH_NULL_TOKEN
                normalized = str(value).strip()
                if normalized.endswith(".0") and normalized[:-2].isdigit():
                    normalized = normalized[:-2]
                return normalized.zfill(6) if normalized.isdigit() else normalized

            canonical[column] = values.map(normalize_stock_code)
        else:
            canonical[column] = values.astype("string").fillna(AUDIT_HASH_NULL_TOKEN)
    return canonical


def _canonical_frame_sha256(frame: pd.DataFrame) -> str:
    """生成可从Excel sheet回读复算的行序、列序绑定哈希。"""
    canonical = _canonical_audit_frame(frame)
    payload = canonical.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return sha256(payload).hexdigest()


def _build_execution_exit_audit(
    factor_constituents: pd.DataFrame,
    prediction_start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """裁出OOS逐股票成交证据，并对20交易日限制做结果层断言。"""
    required = {
        "signal_date", "factor", "stock_code", "weight", "execution_date", "can_execute",
        "executed", "execution_restriction_reason", "return_status", "intended_return_date",
        "actual_return_date", "exit_delay_days", "exit_delay_trading_days", "exit_executed",
        "restriction_reason", "label_available_date", "nav_marked", "exit_search_horizon_date",
        "execution_is_st", "execution_no_volume", "execution_is_suspended",
        "execution_is_limit_up", "execution_is_limit_down",
    }
    missing = required.difference(factor_constituents.columns)
    if missing:
        raise KeyError(f"逐股票执行/退出审计缺少字段: {sorted(missing)}")
    frame = factor_constituents.copy()
    date_columns = [
        "signal_date", "execution_date", "intended_return_date", "actual_return_date",
        "label_available_date", "exit_search_horizon_date",
    ]
    for column in date_columns:
        frame[column] = pd.to_datetime(frame[column], errors="coerce").dt.normalize()
    frame["_prediction_period"] = frame["signal_date"].dt.to_period("M") + 1
    start_period = pd.Timestamp(prediction_start).to_period("M")
    end_period = pd.Timestamp(end).to_period("M")
    frame = frame.loc[frame["_prediction_period"].between(start_period, end_period)].copy()
    if frame.empty:
        raise AssertionError("OOS逐股票执行/退出审计为空")
    expected_periods = pd.period_range(start_period, end_period, freq="M")
    observed_periods = pd.PeriodIndex(frame["_prediction_period"].unique(), freq="M").sort_values()
    if not observed_periods.equals(expected_periods):
        raise AssertionError(
            "OOS逐股票审计月份不完整: "
            f"missing={expected_periods.difference(observed_periods).astype(str).tolist()}"
        )
    if frame.duplicated(["signal_date", "factor", "stock_code"]).any():
        raise AssertionError("OOS逐股票审计同一信号月/因子/股票存在重复")

    frame["intended_execution_date"] = frame["execution_date"]
    frame["actual_execution_date"] = frame["execution_date"].where(frame["executed"].fillna(False))
    frame["prediction_date"] = frame["_prediction_period"].dt.to_timestamp("M")
    frame["prediction_month"] = frame["_prediction_period"].astype(str)
    frame["can_execute"] = frame["can_execute"].fillna(False).astype(bool)
    frame["executed"] = frame["executed"].fillna(False).astype(bool)
    frame["exit_executed"] = frame["exit_executed"].fillna(False).astype(bool)
    frame["nav_marked"] = frame["nav_marked"].fillna(False).astype(bool)
    for column in (
        "execution_is_st", "execution_no_volume", "execution_is_suspended",
        "execution_is_limit_up", "execution_is_limit_down",
    ):
        frame[column] = frame[column].fillna(False).astype(bool)
    if not (frame["signal_date"] < frame["intended_execution_date"]).all():
        raise AssertionError("逐股票审计存在非T+1计划执行日")
    if frame.loc[frame["executed"], "actual_execution_date"].isna().any():
        raise AssertionError("已入场股票缺少实际执行日")
    if frame.loc[~frame["executed"], "actual_execution_date"].notna().any():
        raise AssertionError("未入场股票不应记录实际执行日")
    exited = frame["exit_executed"]
    if frame.loc[exited, "actual_return_date"].isna().any():
        raise AssertionError("已退出股票缺少实际退出日")
    if (frame.loc[exited, "actual_return_date"] < frame.loc[exited, "intended_return_date"]).any():
        raise AssertionError("实际退出日早于计划退出日")
    delay = pd.to_numeric(frame["exit_delay_trading_days"], errors="coerce")
    if delay.dropna().gt(MAX_EXIT_DELAY_TRADING_DAYS).any():
        raise AssertionError("逐股票退出延迟超过固定20个额外交易日")
    unresolved = frame["executed"] & ~frame["exit_executed"]
    if not delay.loc[unresolved].eq(MAX_EXIT_DELAY_TRADING_DAYS).all():
        raise AssertionError("搜索超限仓位未留存固定20交易日窗证据")
    if (frame["label_available_date"] < frame["intended_return_date"]).any():
        raise AssertionError("逐股票标签可得日早于计划退出日")

    output_columns = [
        "signal_date", "prediction_date", "prediction_month", "factor", "stock_code", "weight",
        "intended_execution_date", "actual_execution_date", "can_execute", "executed",
        "execution_restriction_reason", "execution_is_st", "execution_no_volume",
        "execution_is_suspended", "execution_is_limit_up", "execution_is_limit_down",
        "return_status", "intended_return_date",
        "actual_return_date", "exit_delay_days", "exit_delay_trading_days", "exit_executed",
        "restriction_reason", "label_available_date", "nav_marked", "exit_search_horizon_date",
    ]
    audit = frame[output_columns].sort_values(
        ["prediction_date", "factor", "stock_code"]
    ).reset_index(drop=True)
    for column in AUDIT_HASH_NUMERIC_COLUMNS.intersection(audit.columns):
        audit[column] = pd.to_numeric(audit[column], errors="coerce").round(
            AUDIT_HASH_DECIMAL_PLACES
        )
    if len(audit) > EXCEL_MAX_DATA_ROWS:
        raise AssertionError(
            f"逐股票审计超过Excel数据行上限: rows={len(audit)}, limit={EXCEL_MAX_DATA_ROWS}"
        )
    summary = {
        "sheet": "execution_exit_audit",
        "rows": int(len(audit)),
        "sha256": _canonical_frame_sha256(audit),
        "sha256_canonicalization": {
            "version": "execution_exit_audit_v2",
            "numeric_decimal_places": AUDIT_HASH_DECIMAL_PLACES,
            "date_format": "YYYY-MM-DD",
            "boolean_format": "true|false",
            "null_token": AUDIT_HASH_NULL_TOKEN,
            "stock_code_format": "six_digit_zero_padded_when_numeric",
            "row_order": "prediction_date,factor,stock_code",
            "column_order": "worksheet_header_order",
        },
        "prediction_months": int(audit["prediction_month"].nunique()),
        "prediction_start": str(start_period),
        "prediction_end": str(end_period),
        "excel_data_row_limit": EXCEL_MAX_DATA_ROWS,
        "configured_max_exit_delay_trading_days": MAX_EXIT_DELAY_TRADING_DAYS,
        "actual_execution_count": int(audit["actual_execution_date"].notna().sum()),
        "execution_restricted_count": int((~audit["can_execute"]).sum()),
        "normal_exit_count": int(
            (audit["exit_executed"] & pd.to_numeric(audit["exit_delay_trading_days"]).eq(0)).sum()
        ),
        "delayed_exit_count": int(
            (audit["exit_executed"] & pd.to_numeric(audit["exit_delay_trading_days"]).gt(0)).sum()
        ),
        "unresolved_exit_count": int(unresolved.sum()),
        "nav_marked_count": int(audit["nav_marked"].sum()),
        "execution_restriction_counts": {
            str(key): int(value)
            for key, value in audit["execution_restriction_reason"].value_counts(dropna=False).items()
        },
        "return_status_counts": {
            str(key): int(value)
            for key, value in audit["return_status"].value_counts(dropna=False).items()
        },
    }
    return audit, summary


def _summary_workbook(
    path: Path,
    comparison: pd.DataFrame,
    gross: pd.DataFrame,
    net: pd.DataFrame,
    classification: dict[str, Any],
    factor_metrics: dict[str, Any],
    coverage: dict[str, Any],
    evidence: pd.DataFrame,
    chart_data: Mapping[str, pd.DataFrame],
    chart_paths: Mapping[str, Path],
) -> None:
    classification_table = pd.DataFrame(
        [
            {"scope": scope, "metric": metric, "value": value}
            for scope, values in classification.items()
            for metric, value in values.items()
        ]
    )
    factor_table = pd.DataFrame(
        [{"metric": metric, "value": value} for metric, value in factor_metrics.items()]
    )
    coverage_table = pd.DataFrame(
        [
            {"field": key, "value": json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value}
            for key, value in coverage.items()
        ]
    )
    report_reference = pd.DataFrame(
        [
            {"report_method": method, "metric": metric, "report_value": value}
            for method, values in REPORT_R10_VALUES.items()
            for metric, value in values.items()
        ]
    )
    notes = pd.DataFrame(
        [
            {
                "topic": "市场迁移解释",
                "note": "中国A股迁移结果与美国原研报数值的偏差仅作背景参照，不是复现误差。",
            },
            {"topic": "主结果", "note": "组合绩效主结果统一使用毛收益。"},
            {
                "topic": "成本补充",
                "note": (
                    "三个可投资因子组合按袖套权重变化代理换手并计成本；"
                    "中证800保持无成本理论指数基准。该情景不替代毛收益主结果。"
                ),
            },
            {
                "topic": "统计边界",
                "note": "正式OOS仅33个月，结果的不确定性不得解释为稳定长期领先。",
            },
        ]
    )
    chart_sheet_names = {
        "feature_importance": "图_特征重要性",
        "ic_series": "图_RankIC",
        "group_cumulative_returns": "图_组合累计收益",
        "train_val_loss": "图_训练验证损失",
        "prediction_scatter": "图_预测散点",
        "drawdown": "图_组合回撤",
    }
    sheets: dict[str, pd.DataFrame] = {
        "R10核心对照": comparison,
        "中国OOS毛收益": gross,
        "中国OOS成本补充": net,
        "美国研报R10原值": report_reference,
        "分类指标": classification_table,
        "因子预测指标": factor_table,
        "OOS覆盖与冻结": coverage_table,
        "OOS证据清单": evidence,
        "口径说明": notes,
    }
    sheets.update({chart_sheet_names[key]: frame for key, frame in chart_data.items()})
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(destination, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            _excel_safe(frame).to_excel(writer, sheet_name=name, index=False)
    image_map = {
        chart_sheet_names[key]: chart_paths[f"{key}.png"] for key in chart_sheet_names
    }
    _format_workbook(destination, image_map=image_map)


def _write_detail_workbooks(
    output_dir: Path,
    stage_one: Any,
    stage_two: Any,
    portfolio: PortfolioResult,
    execution_exit_audit: pd.DataFrame,
) -> dict[str, Path]:
    paths = {
        "model_details.xlsx": output_dir / "model_details.xlsx",
        "probability_details.xlsx": output_dir / "probability_details.xlsx",
        "weights_detail.xlsx": output_dir / "weights_detail.xlsx",
        "returns_detail.xlsx": output_dir / "returns_detail.xlsx",
    }
    _write_workbook(
        paths["model_details.xlsx"],
        {
            "m2滚动预测": stage_one.rolling_predictions,
            "m2训练窗": stage_one.training_audit,
            "m2折指标": stage_one.fold_metrics,
            "m2混淆矩阵": stage_one.confusion_matrix,
            "m2状态分布": stage_one.regime_distribution,
            "m2特征重要性": stage_one.feature_importance,
            "m2肘部诊断": stage_one.elbow_diagnostics,
            "m3训练窗": stage_two.training_audit,
            "m3滚动损失": stage_two.train_val_logloss,
            "m3特征重要性": stage_two.feature_importance,
            "m3相关矩阵": stage_two.correlation_matrices,
            "m3胜出频率": stage_two.winner_frequency,
        },
    )
    _write_workbook(
        paths["probability_details.xlsx"],
        {
            "OOS概率": stage_two.rolling_probabilities,
            "预测指标": stage_two.prediction_metrics,
            "胜出标签": stage_two.winner_labels,
            "标签审计": stage_two.label_audit,
        },
    )
    _write_workbook(
        paths["weights_detail.xlsx"],
        {
            "逐月权重": portfolio.weight_detail,
            "商业周期标签": portfolio.business_cycle_labels,
            "周期方向矩阵": portfolio.cycle_direction_matrix,
        },
    )
    _write_workbook(
        paths["returns_detail.xlsx"],
        {
            "组合收益": portfolio.portfolio_returns,
            "累计收益图数据": portfolio.chart_data,
            "T1对齐审计": portfolio.alignment_audit,
            "execution_exit_audit": execution_exit_audit,
        },
    )
    return paths


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_evidence_files(
    output_dir: Path,
    evidence: pd.DataFrame,
    coverage: dict[str, Any],
    parameter_hashes: Mapping[str, str],
    artifact_paths: Mapping[str, Path],
) -> dict[str, Path]:
    manifest_path = output_dir / "oos_evidence_manifest.json"
    checklist_path = output_dir / "oos_evidence_checklist.md"
    artifact_rows = [
        {
            "name": name,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for name, path in sorted(artifact_paths.items())
        if path.exists()
    ]
    write_json(
        manifest_path,
        {
            "report_id": REPORT_ID,
            "generated_at": _now(),
            "status": "generated_pending_independent_verifier",
            "coverage": coverage,
            "parameter_hashes": dict(parameter_hashes),
            "artifact_contract": {
                "expected_total_files": len(RESULT_ARTIFACT_FILENAMES),
                "expected_filenames": list(RESULT_ARTIFACT_FILENAMES),
                "sha256_rows_scope": "已完成且内容不再变化的核心产物；manifest自身、checklist与最终run_log不自哈希",
                "sha256_row_count": len(artifact_rows),
            },
            "checks": evidence.to_dict("records"),
            "artifacts": artifact_rows,
        },
        indent=2,
    )
    lines = [
        "# 严格样本外证据清单",
        "",
        "> 本清单记录代码生成时的结构性断言，最终复现判定由 quant-verifier 独立给出。",
        "",
        "| ID | 检查项 | 观测 | 结构断言 | 证据源 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in evidence.itertuples(index=False):
        lines.append(
            f"| {row.check_id} | {row.check} | {row.observed} | "
            f"{'满足' if row.passed else '不满足'} | `{row.evidence_source}` |"
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- 正式默认区间为2023-04至2025-12，共33个月。",
            "- 原研报为美国市场，中国A股迁移结果与原值的偏差不是复现误差。",
            "- 毛收益是主结果；成本净收益只作补充情景。",
            "- 33个月样本较短，不能据此宣称长期稳定有效。",
        ]
    )
    checklist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "oos_evidence_manifest.json": manifest_path,
        "oos_evidence_checklist.md": checklist_path,
    }


def _training_window_log_lines(
    stage_one: Any,
    stage_two: Any,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[str]:
    """把每个目标月的m2/m3冻结训练区间压成可审阅Markdown表。"""
    m2_windows = stage_one.training_audit.copy()
    m2_windows["prediction_period"] = pd.to_datetime(
        m2_windows["prediction_date"]
    ).dt.to_period("M")
    m2_windows = m2_windows.drop_duplicates("prediction_period").set_index(
        "prediction_period"
    )
    m3_windows = stage_two.training_audit.copy()
    m3_windows["prediction_period"] = pd.to_datetime(
        m3_windows["prediction_date"]
    ).dt.to_period("M")
    m3_windows = m3_windows.drop_duplicates("prediction_period").set_index(
        "prediction_period"
    )
    lines = [
        "### 每月冻结训练窗口",
        "| 目标月 | m2训练目标月 | m3训练标签月 |",
        "| --- | --- | --- |",
    ]
    for period in _expected_periods(start, end):
        if period not in m2_windows.index or period not in m3_windows.index:
            raise AssertionError(f"目标月{period}缺少m2或m3训练窗日志证据")
        m2_row = m2_windows.loc[period]
        m3_row = m3_windows.loc[period]
        lines.append(
            f"| {period} | "
            f"{pd.Timestamp(m2_row['train_target_start']):%Y-%m}.."
            f"{pd.Timestamp(m2_row['train_target_end']):%Y-%m} | "
            f"{pd.Timestamp(m3_row['train_window_start']):%Y-%m}.."
            f"{pd.Timestamp(m3_row['train_window_end']):%Y-%m} |"
        )
    return lines


def build_metrics(
    *,
    stage_one: Any,
    stage_two: Any,
    portfolio: PortfolioResult,
    prediction_start: pd.Timestamp,
    end: pd.Timestamp,
    config: ChinaFactorTimingConfig,
    execution_exit_audit_summary: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """构造 metrics/comparison 及Excel表；不作最终验证结论。"""
    coverage, evidence = _coverage_and_training_evidence(
        stage_one, stage_two, portfolio, prediction_start, end, config
    )
    gross = _portfolio_metric_table(portfolio, "gross_return")
    net = _portfolio_metric_table(portfolio, "net_return")
    classification = _classification_metrics(stage_one)
    factor_metrics = _factor_prediction_metrics(stage_two)
    comparison_table = _comparison_table(gross)
    config_payload = asdict(config)
    config_payload["data_root"] = str(config.data_root)
    base_config_hash = sha256(
        json.dumps(config_payload, ensure_ascii=False, sort_keys=True, default=str).encode(
            "utf-8"
        )
    ).hexdigest()
    portfolio_settings = asdict(PortfolioSettings())
    run_configuration = {
        "base_configuration": config_payload,
        "prediction_start": str(pd.Timestamp(prediction_start).to_period("M")),
        "prediction_end": str(pd.Timestamp(end).to_period("M")),
        "oos_cutoff": config.oos_cutoff,
        "stage_one_parameter_hash": stage_one.parameter_hash,
        "stage_two_parameter_hash": stage_two.parameter_hash,
        "portfolio_settings": portfolio_settings,
        "business_cycle_directions_R9": BUSINESS_CYCLE_DIRECTIONS,
        "portfolio_order": list(PORTFOLIO_ORDER),
        "performance_conventions": {
            "periods_per_year": 12,
            "risk_free_rate_per_period": 0.0,
            "gross_is_primary": True,
            "net_is_cost_supplement": True,
            "max_drawdown_initial_nav": 1.0,
            "active_return_formula": "(1+portfolio_return)/(1+benchmark_return)-1",
            "turnover_formula": "buy_turnover+sell_turnover",
        },
        "report_reference_R10": REPORT_R10_VALUES,
        "artifact_contract": list(RESULT_ARTIFACT_FILENAMES),
    }
    run_config_hash = sha256(
        json.dumps(
            run_configuration, ensure_ascii=False, sort_keys=True, default=str
        ).encode("utf-8")
    ).hexdigest()
    metrics = {
        "report_id": REPORT_ID,
        "generated_at": _now(),
        "status": "computed_pending_independent_verifier",
        "market": "中国A股实验性迁移",
        "report_reference_market": "美国",
        "interpretation": {
            "gross_is_primary": True,
            "net_is_cost_supplement": True,
            "us_china_deviation_is_reproduction_error": False,
            "note": "中国市场结果与原研报美国数值的差异仅作迁移背景参照。",
            "short_oos_warning": "正式OOS仅33个月，统计不确定性较高。",
        },
        "configuration": {
            **config_payload,
            "factor_names": list(config.factor_names),
        },
        "run_configuration": run_configuration,
        "parameter_hashes": {
            "configuration": run_config_hash,
            "run_configuration": run_config_hash,
            "base_configuration": base_config_hash,
            "stage_one": stage_one.parameter_hash,
            "stage_two": stage_two.parameter_hash,
        },
        "method_freeze": {
            "freeze_cutoff": config.oos_cutoff,
            "feature_definitions_frozen_pre_oos": True,
            "preprocessing_fitted_within_each_training_window": True,
            "rolling_train_months": config.turbulence_window_months,
            "oos_tuning_permitted": False,
            "portfolio_primary_basis": "gross",
            "cost_supplement_buy_rate": portfolio_settings["buy_cost_rate"],
            "cost_supplement_sell_rate": portfolio_settings["sell_cost_rate"],
            "cost_supplement_sell_stamp_tax_rate": portfolio_settings[
                "sell_stamp_tax_rate"
            ],
            "business_cycle_active_tilt_budget": portfolio_settings[
                "active_tilt_budget"
            ],
        },
        "artifact_contract": {
            "expected_total_files": len(RESULT_ARTIFACT_FILENAMES),
            "expected_filenames": list(RESULT_ARTIFACT_FILENAMES),
        },
        "coverage": coverage,
        "classification": classification,
        "factor_prediction": factor_metrics,
        "execution_exit_audit": dict(execution_exit_audit_summary),
        "portfolio_gross_primary": gross.to_dict("records"),
        "portfolio_net_cost_supplement": net.to_dict("records"),
        "transaction_cost_scope": (
            "三个可投资因子组合按袖套权重变化代理换手并计首期建仓成本；"
            "中证800为无成本理论指数基准；样本末不强制平仓"
        ),
    }
    comparison = {
        "report_id": REPORT_ID,
        "element_id": "R10",
        "status": "market_transplant_context_only_pending_verifier",
        "comparison_semantics": "us_reference_vs_china_oos_not_reproduction_error",
        "report_values_are_reference_only": True,
        "report_na_values_not_inferred": True,
        "rows": comparison_table.to_dict("records"),
    }
    return metrics, comparison, gross, net, evidence


def write_result_package(
    *,
    output_dir: Path,
    stage_one: Any,
    stage_two: Any,
    portfolio: PortfolioResult,
    factor_constituents: pd.DataFrame,
    prediction_start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    config: ChinaFactorTimingConfig | None = None,
    run_log_path: Path | None = None,
    run_started_at: str | None = None,
    run_started_monotonic: float | None = None,
    command: str | None = None,
) -> ReportPackage:
    """生成m5完整结果包；正式默认调用必须覆盖33个OOS月。"""
    effective_started_at = run_started_at or _now()
    effective_started_monotonic = (
        run_started_monotonic if run_started_monotonic is not None else perf_counter()
    )
    cfg = config or ChinaFactorTimingConfig()
    start_timestamp = pd.Timestamp(prediction_start)
    end_timestamp = pd.Timestamp(end)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    execution_exit_audit, execution_exit_audit_summary = _build_execution_exit_audit(
        factor_constituents,
        start_timestamp,
        end_timestamp,
    )
    metrics, comparison, gross, net, evidence = build_metrics(
        stage_one=stage_one,
        stage_two=stage_two,
        portfolio=portfolio,
        prediction_start=start_timestamp,
        end=end_timestamp,
        config=cfg,
        execution_exit_audit_summary=execution_exit_audit_summary,
    )
    chart_data = _build_chart_data(stage_one, stage_two, portfolio)
    chart_paths = create_charts(destination, chart_data)

    metrics_path = destination / "metrics.json"
    comparison_path = destination / "comparison.json"
    write_json(metrics_path, metrics, indent=2)
    write_json(comparison_path, comparison, indent=2)
    comparison_table = pd.DataFrame(comparison["rows"])
    workbook_path = destination / "backtest_summary.xlsx"
    _summary_workbook(
        workbook_path,
        comparison_table,
        gross,
        net,
        metrics["classification"],
        metrics["factor_prediction"],
        metrics["coverage"],
        evidence,
        chart_data,
        chart_paths,
    )
    detail_paths = _write_detail_workbooks(
        destination,
        stage_one,
        stage_two,
        portfolio,
        execution_exit_audit,
    )
    paths: dict[str, Path] = {
        "metrics.json": metrics_path,
        "comparison.json": comparison_path,
        "backtest_summary.xlsx": workbook_path,
        **chart_paths,
        **detail_paths,
    }
    evidence_paths = _write_evidence_files(
        destination,
        evidence,
        metrics["coverage"],
        metrics["parameter_hashes"],
        paths,
    )
    paths.update(evidence_paths)
    if run_log_path is not None:
        log_path = Path(run_log_path)
        if log_path.parent.resolve() != destination.resolve() or log_path.name != "run_log.md":
            raise ValueError("正式run_log必须位于结果目录根部且命名为run_log.md")
        expected_names = set(RESULT_ARTIFACT_FILENAMES)
        actual_before_log = {
            path.name for path in destination.iterdir() if path.is_file() and path.stat().st_size > 0
        }
        unexpected = actual_before_log.difference(expected_names)
        missing_core = expected_names.difference({"run_log.md"}).difference(actual_before_log)
        if unexpected or missing_core:
            raise AssertionError(
                "结果目录与16项产物合同不一致: "
                f"unexpected={sorted(unexpected)}, missing={sorted(missing_core)}"
            )
        window_lines = _training_window_log_lines(
            stage_one, stage_two, start_timestamp, end_timestamp
        )
        finished_at = _now()
        elapsed_seconds = perf_counter() - effective_started_monotonic
        append_run_log(
            log_path,
            [
                f"## m5结果包完成 {finished_at}",
                "- status: completed_pending_independent_verifier",
                f"- started_at: {effective_started_at}",
                f"- finished_at: {finished_at}",
                f"- elapsed_seconds: {elapsed_seconds:.6f}",
                f"- command: `{command or 'not_provided'}`",
                "- exit=0",
                f"- oos_window: {start_timestamp.to_period('M')}..{end_timestamp.to_period('M')}",
                f"- expected_months: {metrics['coverage']['expected_months']}",
                f"- stage_one_parameter_hash: {stage_one.parameter_hash}",
                f"- stage_two_parameter_hash: {stage_two.parameter_hash}",
                f"- configuration_hash: {metrics['parameter_hashes']['configuration']}",
                f"- base_configuration_hash: {metrics['parameter_hashes']['base_configuration']}",
                f"- execution_exit_audit_rows: {execution_exit_audit_summary['rows']}",
                f"- execution_exit_audit_sha256: {execution_exit_audit_summary['sha256']}",
                f"- execution_restricted_count: {execution_exit_audit_summary['execution_restricted_count']}",
                f"- delayed_exit_count: {execution_exit_audit_summary['delayed_exit_count']}",
                f"- unresolved_exit_count: {execution_exit_audit_summary['unresolved_exit_count']}",
                f"- nav_marked_count: {execution_exit_audit_summary['nav_marked_count']}",
                "- primary_return_basis: gross",
                "- cost_result_basis: supplemental_net",
                "- comparison_semantics: US reference vs China OOS; deviations are not reproduction errors",
                f"- artifacts: {len(RESULT_ARTIFACT_FILENAMES)}",
                f"- artifact_count: {len(RESULT_ARTIFACT_FILENAMES)}",
                "",
                *window_lines,
            ],
        )
        paths["run_log.md"] = log_path
        actual_after_log = {
            path.name for path in destination.iterdir() if path.is_file() and path.stat().st_size > 0
        }
        if actual_after_log != expected_names:
            raise AssertionError(
                "run_log落盘后目录计数与16项合同不一致: "
                f"actual={sorted(actual_after_log)}, expected={sorted(expected_names)}"
            )
    return ReportPackage(paths=paths, metrics=metrics, comparison=comparison)


__all__ = [
    "EXPECTED_OOS_MONTHS",
    "REPORT_ID",
    "REPORT_R10_VALUES",
    "RESULT_ARTIFACT_FILENAMES",
    "ReportPackage",
    "append_run_log",
    "build_metrics",
    "create_charts",
    "write_result_package",
]
