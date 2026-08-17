"""r007 m4：十模型完整面板、三规格对齐与方向容量组合。

本模块只装配 m1/m3 已生成的目标收益、历史成交金额中位数和样本外预测；
通用的嵌套组合、成本前 PnL 与 Sharpe 计算复用 ``common.ml_portfolio``。
不写正式结果文件，也不据此宣布 R1/R3/R4 是否通过。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from common.ml_portfolio import (
    SignedLiquidityPortfolioResult,
    SignedLiquidityPortfolioSettings,
    run_signed_liquidity_portfolios,
)

from .config import DEFAULT_M4_CONFIG, M4Config
from .model_pipeline import (
    EligibilityDecisionError,
    validate_eligibility_audit,
)


OBSERVATION_KEY_COLUMNS = (
    "specification",
    "target_market",
    "direction",
    "feature_set",
    "target_date",
    "target_code",
)

MODEL_COMPLETENESS_AUDIT_DTYPES = {
    "specification": "string",
    "target_market": "string",
    "direction": "string",
    "feature_set": "string",
    "target_date": "datetime64[ns]",
    "target_code": "string",
    "model_count": "Int64",
    "model_set": "object",
    "finite_row_count": "Int64",
    "row_count": "Int64",
    "expected_model_count": "Int64",
    "expected_direction": "string",
    "direction_contract_valid": "boolean",
    "complete_model_set": "boolean",
    "all_rows_finite": "boolean",
    "status": "string",
}

COMPARABILITY_AUDIT_DTYPES = {
    "comparison_direction": "string",
    "target_market": "string",
    "feature_set": "string",
    "target_date": "datetime64[ns]",
    "target_code": "string",
    "specification_count": "Int64",
    "specification_set": "object",
    "model_row_count": "Int64",
    "expected_specification_count": "Int64",
    "all_specifications_present": "boolean",
    "status": "string",
}

DIRECTION_CONTRACT_AUDIT_DTYPES = {
    "specification": "string",
    "target_market": "string",
    "expected_direction": "string",
    "comparison_direction": "string",
    "observation_group_count": "Int64",
    "prediction_row_count": "Int64",
    "unexpected_direction_row_count": "Int64",
    "status": "string",
}


@dataclass
class CompletePredictionPanel:
    """十模型完整性筛选结果与逐观测审计。"""

    predictions: pd.DataFrame
    audit: pd.DataFrame


@dataclass
class ComparablePredictionPanel:
    """三规格共同日期、股票与模型面板及交集审计。"""

    predictions: pd.DataFrame
    audit: pd.DataFrame


@dataclass
class M4PortfolioResult:
    """组合结果及进入组合前的完整性、可比性和时点审计。"""

    predictions: pd.DataFrame
    model_completeness_audit: pd.DataFrame
    comparability_audit: pd.DataFrame
    execution_timing_audit: pd.DataFrame
    direction_contract_audit: pd.DataFrame
    formal_coverage_audit: pd.DataFrame
    portfolios: SignedLiquidityPortfolioResult


@dataclass
class CoreComparisonTables:
    """R1/R3/R4 的观测量、配对明细与汇总接口。"""

    observations: pd.DataFrame
    paired_comparisons: pd.DataFrame
    summary: pd.DataFrame
    direction_contract_audit: pd.DataFrame


class DirectionContractError(ValueError):
    """双方向或三规格方向合同不完整，携带逐项审计表。"""

    def __init__(self, message: str, audit: pd.DataFrame) -> None:
        super().__init__(message)
        self.audit = audit.reset_index(drop=True).copy()


class FormalCoverageError(ValueError):
    """2016–2021 正式覆盖合同不完整，携带逐层覆盖审计表。"""

    def __init__(self, message: str, audit: pd.DataFrame) -> None:
        super().__init__(message)
        self.audit = audit.reset_index(drop=True).copy()


def _empty_typed_frame(dtypes: Mapping[str, str]) -> pd.DataFrame:
    """构造列顺序与 dtype 稳定的 0 行审计表。"""
    return pd.DataFrame(
        {
            column: pd.Series(dtype=dtype)
            for column, dtype in dtypes.items()
        }
    )


def _require_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
    context: str,
) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise KeyError(f"{context} 缺少字段: {missing}")


def prepare_portfolio_predictions(
    predictions: pd.DataFrame,
    target_panel: pd.DataFrame,
    *,
    target_market: str,
    specification: str,
    feature_set: str,
    config: M4Config = DEFAULT_M4_CONFIG,
) -> pd.DataFrame:
    """附加实现收益与预测日前 21 日成交金额中位数。

    历史流动性直接消费 m1 中已经 ``shift(1)`` 的字段，不读取或回退到
    预测当日成交金额。若 m3 已带 ``actual_return``，会与目标面板逐行核对。
    """
    prediction_required = (
        "direction",
        "target_code",
        "target_date",
        "model",
        "prediction",
    )
    _require_columns(predictions, prediction_required, "m4 样本外预测")
    returns = config.m3.pipeline.returns
    target_required = (
        returns.stock_column,
        returns.date_column,
        returns.opcl_excess_column,
        returns.liquidity_median_column,
    )
    _require_columns(target_panel, target_required, "m4 目标市场面板")
    if target_market not in config.portfolio.position_caps():
        raise KeyError(f"未知目标市场: {target_market}")
    if specification not in config.baseline.specifications:
        raise KeyError(f"未知 m4 规格: {specification}")

    result = predictions.copy()
    result["target_code"] = result["target_code"].astype(str)
    result["target_date"] = pd.to_datetime(
        result["target_date"], errors="raise"
    ).dt.normalize()
    liquidity = target_panel.loc[:, list(target_required)].copy()
    liquidity[returns.stock_column] = liquidity[returns.stock_column].astype(str)
    liquidity[returns.date_column] = pd.to_datetime(
        liquidity[returns.date_column], errors="raise"
    ).dt.normalize()
    if liquidity.duplicated([returns.stock_column, returns.date_column]).any():
        raise ValueError("目标市场面板存在重复 stock_code/date 键")
    liquidity = liquidity.rename(
        columns={
            returns.stock_column: "target_code",
            returns.date_column: "target_date",
            returns.opcl_excess_column: "_panel_actual_return",
            returns.liquidity_median_column: "historical_liquidity",
        }
    )
    result = result.merge(
        liquidity,
        on=["target_code", "target_date"],
        how="left",
        validate="many_to_one",
    )
    if "actual_return" in result.columns:
        upstream = pd.to_numeric(result["actual_return"], errors="coerce")
        panel_actual = pd.to_numeric(
            result["_panel_actual_return"], errors="coerce"
        )
        comparable = upstream.notna() & panel_actual.notna()
        mismatch = comparable & upstream.sub(panel_actual).abs().gt(
            config.portfolio.actual_return_match_tolerance
        )
        if mismatch.any():
            raise ValueError(
                "m3 actual_return 与目标面板 OPCL 超额收益存在 "
                f"{int(mismatch.sum())} 行不一致"
            )
        result["actual_return"] = upstream.fillna(panel_actual)
    else:
        result["actual_return"] = result["_panel_actual_return"]
    result = result.drop(columns="_panel_actual_return")
    result["target_market"] = target_market
    result["specification"] = specification
    result["feature_set"] = feature_set
    result["execution_date"] = result["target_date"]
    if "source_date" in result.columns:
        result["source_date"] = pd.to_datetime(
            result["source_date"], errors="coerce"
        ).dt.normalize()
        result["signal_date"] = result["source_date"]
    else:
        result["signal_date"] = pd.NaT
    return result.sort_values(
        [
            "specification",
            "target_market",
            "feature_set",
            "target_date",
            "target_code",
            "model",
        ]
    ).reset_index(drop=True)


def enforce_complete_ten_model_groups(
    predictions: pd.DataFrame,
    *,
    config: M4Config = DEFAULT_M4_CONFIG,
) -> CompletePredictionPanel:
    """只保留同一规格、方向、市场、日期、股票下十模型全部有效的观测。

    任一基础模型失败时，集成预测即使存在也不能让残缺截面进入回测。
    """
    required = (
        *OBSERVATION_KEY_COLUMNS,
        "model",
        "prediction",
        "actual_return",
        "historical_liquidity",
    )
    _require_columns(predictions, required, "十模型完整性检查")
    expected_models = config.m3.prediction.all_model_names
    expected_set = frozenset(expected_models)
    result = predictions.copy()
    result["target_date"] = pd.to_datetime(
        result["target_date"], errors="raise"
    ).dt.normalize()
    if result.empty:
        return CompletePredictionPanel(
            predictions=result.reset_index(drop=True),
            audit=_empty_typed_frame(MODEL_COMPLETENESS_AUDIT_DTYPES),
        )
    duplicate_keys = [*OBSERVATION_KEY_COLUMNS, "model"]
    if result.duplicated(duplicate_keys).any():
        raise ValueError(
            "预测面板存在重复规格/市场/方向/日期/股票/模型键"
        )
    unknown = set(result["model"].dropna().astype(str)) - expected_set
    if unknown:
        raise ValueError(f"预测面板含未登记模型: {sorted(unknown)}")
    result["model"] = result["model"].astype(str)
    numeric = result.loc[
        :, ["prediction", "actual_return", "historical_liquidity"]
    ].apply(pd.to_numeric, errors="coerce")
    result["_row_finite"] = np.isfinite(
        numeric.to_numpy(dtype=np.float64, na_value=np.nan)
    ).all(axis=1)

    audit = (
        result.groupby(list(OBSERVATION_KEY_COLUMNS), observed=True, sort=False)
        .agg(
            model_count=("model", "nunique"),
            model_set=("model", lambda values: frozenset(values.astype(str))),
            finite_row_count=("_row_finite", "sum"),
            row_count=("model", "size"),
        )
        .reset_index()
    )
    audit["expected_model_count"] = len(expected_models)
    audit["expected_direction"] = [
        config.baseline.expected_direction(specification, target_market)
        for specification, target_market in zip(
            audit["specification"],
            audit["target_market"],
            strict=True,
        )
    ]
    audit["direction_contract_valid"] = audit["direction"].astype(str).eq(
        audit["expected_direction"].astype(str)
    )
    audit["complete_model_set"] = audit["model_set"].map(
        lambda values: values == expected_set
    )
    audit["all_rows_finite"] = audit["finite_row_count"].eq(
        audit["expected_model_count"]
    )
    audit["status"] = np.select(
        [
            ~audit["direction_contract_valid"],
            ~audit["complete_model_set"],
            ~audit["all_rows_finite"],
        ],
        [
            "dropped_direction_contract_mismatch",
            "dropped_incomplete_model_set",
            "dropped_nonfinite_portfolio_input",
        ],
        default="kept",
    )
    kept_keys = audit.loc[
        audit["status"].eq("kept"),
        list(OBSERVATION_KEY_COLUMNS),
    ]
    kept = result.merge(
        kept_keys,
        on=list(OBSERVATION_KEY_COLUMNS),
        how="inner",
        validate="many_to_one",
    ).drop(columns="_row_finite")
    audit["model_set"] = audit["model_set"].map(
        lambda values: tuple(
            model for model in expected_models if model in values
        )
    )
    return CompletePredictionPanel(
        predictions=kept.reset_index(drop=True),
        audit=audit.loc[:, list(MODEL_COMPLETENESS_AUDIT_DTYPES)]
        .astype(MODEL_COMPLETENESS_AUDIT_DTYPES)
        .sort_values(list(OBSERVATION_KEY_COLUMNS))
        .reset_index(drop=True),
    )


def align_three_specifications(
    predictions: pd.DataFrame,
    *,
    config: M4Config = DEFAULT_M4_CONFIG,
) -> ComparablePredictionPanel:
    """按双向逻辑分腿，对三规格取共同日期与目标股票交集。"""
    required = (*OBSERVATION_KEY_COLUMNS, "model")
    _require_columns(predictions, required, "三规格可比性检查")
    expected_specs = config.baseline.specifications
    expected_set = frozenset(expected_specs)
    if predictions.empty:
        return ComparablePredictionPanel(
            predictions=predictions.copy().reset_index(drop=True),
            audit=_empty_typed_frame(COMPARABILITY_AUDIT_DTYPES),
        )
    unknown = set(predictions["specification"].astype(str)) - expected_set
    if unknown:
        raise ValueError(f"三规格面板含未登记规格: {sorted(unknown)}")
    working = predictions.copy()
    working["_comparison_direction"] = working["target_market"].map(
        config.baseline.comparison_direction
    )
    observation_keys = [
        "_comparison_direction",
        "target_market",
        "feature_set",
        "target_date",
        "target_code",
    ]
    audit = (
        working.groupby(observation_keys, observed=True, sort=False)
        .agg(
            specification_count=("specification", "nunique"),
            specification_set=(
                "specification",
                lambda values: frozenset(values.astype(str)),
            ),
            model_row_count=("model", "size"),
        )
        .reset_index()
        .rename(
            columns={"_comparison_direction": "comparison_direction"}
        )
    )
    audit["expected_specification_count"] = len(expected_specs)
    audit["all_specifications_present"] = audit["specification_set"].map(
        lambda values: values == expected_set
    )
    audit["status"] = np.where(
        audit["all_specifications_present"],
        "kept_common_observation",
        "dropped_not_common_to_all_specifications",
    )
    common_keys = audit.loc[
        audit["all_specifications_present"],
        [
            "comparison_direction",
            "target_market",
            "feature_set",
            "target_date",
            "target_code",
        ],
    ].rename(columns={"comparison_direction": "_comparison_direction"})
    aligned = working.merge(
        common_keys,
        on=observation_keys,
        how="inner",
        validate="many_to_one",
    ).drop(columns="_comparison_direction")
    audit["specification_set"] = audit["specification_set"].map(
        lambda values: tuple(spec for spec in expected_specs if spec in values)
    )
    return ComparablePredictionPanel(
        predictions=aligned.sort_values(
            [
                "target_market",
                "feature_set",
                "target_date",
                "target_code",
                "specification",
                "model",
            ]
        ).reset_index(drop=True),
        audit=audit.loc[:, list(COMPARABILITY_AUDIT_DTYPES)]
        .astype(COMPARABILITY_AUDIT_DTYPES)
        .sort_values(
            [
                "comparison_direction",
                "target_market",
                "feature_set",
                "target_date",
                "target_code",
            ]
        )
        .reset_index(drop=True),
    )


def audit_direction_contract(
    predictions: pd.DataFrame,
    *,
    config: M4Config = DEFAULT_M4_CONFIG,
) -> pd.DataFrame:
    """逐规格核验 CN/US 两个目标腿及各自唯一实际方向。"""
    required = (
        "specification",
        "target_market",
        "direction",
        "feature_set",
        "target_date",
        "target_code",
    )
    _require_columns(predictions, required, "双方向合同审计")
    rows: list[dict[str, object]] = []
    for specification in config.baseline.specifications:
        for target_market in ("CN", "US"):
            expected_direction = config.baseline.expected_direction(
                specification,
                target_market,
            )
            scope = predictions.loc[
                predictions["specification"].astype(str).eq(specification)
                & predictions["target_market"].astype(str).eq(target_market)
            ]
            matched = scope.loc[
                scope["direction"].astype(str).eq(expected_direction)
            ]
            unexpected_count = int(
                (~scope["direction"].astype(str).eq(expected_direction)).sum()
            )
            observation_count = int(
                matched.loc[
                    :,
                    [
                        "feature_set",
                        "target_date",
                        "target_code",
                    ],
                ]
                .drop_duplicates()
                .shape[0]
            )
            if unexpected_count:
                status = "unexpected_direction_present"
            elif observation_count == 0:
                status = "missing_expected_direction"
            else:
                status = "complete"
            rows.append(
                {
                    "specification": specification,
                    "target_market": target_market,
                    "expected_direction": expected_direction,
                    "comparison_direction": (
                        config.baseline.comparison_direction(target_market)
                    ),
                    "observation_group_count": observation_count,
                    "prediction_row_count": len(matched),
                    "unexpected_direction_row_count": unexpected_count,
                    "status": status,
                }
            )
    return (
        pd.DataFrame(rows)
        .loc[:, list(DIRECTION_CONTRACT_AUDIT_DTYPES)]
        .astype(DIRECTION_CONTRACT_AUDIT_DTYPES)
    )


def audit_execution_timing(
    predictions: pd.DataFrame,
    *,
    config: M4Config = DEFAULT_M4_CONFIG,
) -> pd.DataFrame:
    """核验同市场基线为前一交易日信号，并登记跨市场因果接口来源。"""
    required = (
        "specification",
        "direction",
        "target_market",
        "target_date",
        "signal_date",
    )
    _require_columns(predictions, required, "执行时点审计")
    working = predictions.copy()
    working["target_date"] = pd.to_datetime(
        working["target_date"], errors="raise"
    ).dt.normalize()
    working["signal_date"] = pd.to_datetime(
        working["signal_date"], errors="coerce"
    ).dt.normalize()
    same_market_specs = {
        config.baseline.same_market_graph_specification,
        config.baseline.non_graph_specification,
    }
    same_market = working["specification"].isin(same_market_specs)
    same_market_violation = same_market & (
        working["signal_date"].isna()
        | working["signal_date"].ge(working["target_date"])
    )
    if same_market_violation.any():
        raise AssertionError(
            "同市场图/非图基线存在 "
            f"{int(same_market_violation.sum())} 行非 T+1 执行记录"
        )
    working["_signal_before_target"] = working["signal_date"].lt(
        working["target_date"]
    )
    working["_same_calendar_date"] = working["signal_date"].eq(
        working["target_date"]
    )
    audit = (
        working.groupby(
            ["specification", "direction", "target_market"],
            observed=True,
        )
        .agg(
            prediction_rows=("model", "size"),
            signal_date_available_rows=("signal_date", "count"),
            signal_before_target_rows=("_signal_before_target", "sum"),
            same_calendar_date_rows=("_same_calendar_date", "sum"),
        )
        .reset_index()
    )
    audit["timing_contract"] = np.where(
        audit["specification"].isin(same_market_specs),
        "previous_target_session_signal_then_target_opcl_execution",
        "upstream_cross_market_session_mapping_before_target_open",
    )
    return audit


def _key_set_sha256(frame: pd.DataFrame) -> str:
    keys = (
        frame.loc[:, ["target_date", "target_code"]]
        .assign(
            target_date=lambda value: pd.to_datetime(
                value["target_date"], errors="raise"
            ).dt.strftime("%Y-%m-%d"),
            target_code=lambda value: value["target_code"].astype(str),
        )
        .drop_duplicates()
        .sort_values(["target_date", "target_code"])
    )
    payload = "\n".join(
        f"{row.target_date}\x1f{row.target_code}"
        for row in keys.itertuples(index=False)
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _legacy_audit_formal_prediction_coverage(
    predictions: pd.DataFrame,
    graph_audit: pd.DataFrame,
    *,
    expected_calendars: Mapping[str, pd.DataFrame],
    expected_universes: Mapping[str, Iterable[str]],
    config: M4Config = DEFAULT_M4_CONFIG,
) -> pd.DataFrame:
    """硬核验两方向、三规格、十模型的完整日期/股票/锚点覆盖。

    AS2/AS14 允许逐目标估计阶段跳过不合格样本，但未登记可接受的正式
    缩样本比例。因此正式结果采用零静默缩水合同：预测期目标交易日、
    全期目标股票集合、十模型与三规格共同键必须完整，图更新锚点必须
    等于各目标日历从 2016 年首日起每十日生成的预期集合。
    """
    _require_columns(
        predictions,
        (
            "specification",
            "target_market",
            "direction",
            "target_date",
            "target_code",
            "model",
        ),
        "正式预测覆盖门禁",
    )
    _require_columns(graph_audit, ("direction", "anchor_date"), "图锚点审计")
    start = pd.Timestamp(config.m3.prediction.prediction_start).normalize()
    end = pd.Timestamp(config.m3.prediction.prediction_end).normalize()
    rows: list[dict[str, object]] = []
    expected_dates_by_market: dict[str, pd.DatetimeIndex] = {}
    expected_codes_by_market: dict[str, set[str]] = {}
    for market in ("CN", "US"):
        try:
            calendar = expected_calendars[market]
            universe = expected_universes[market]
        except KeyError as exc:
            raise KeyError(f"正式覆盖门禁缺少 {market} 日历或股票池") from exc
        _require_columns(calendar, ("date",), f"{market} 正式目标日历")
        expected_dates = pd.DatetimeIndex(
            pd.to_datetime(calendar["date"], errors="raise").dt.normalize()
        )
        expected_dates = expected_dates[
            (expected_dates >= start) & (expected_dates <= end)
        ].drop_duplicates().sort_values()
        expected_codes = {str(code) for code in universe}
        if expected_dates.empty or not expected_codes:
            raise ValueError(f"{market} 正式目标日历或股票池为空")
        expected_dates_by_market[market] = expected_dates
        expected_codes_by_market[market] = expected_codes

    graph_working = graph_audit.assign(
        anchor_date=pd.to_datetime(
            graph_audit["anchor_date"], errors="raise"
        ).dt.normalize()
    )
    for direction, target_market in (("US_TO_CN", "CN"), ("CN_TO_US", "US")):
        expected_anchors = expected_dates_by_market[target_market][
            :: config.m3.pipeline.returns.graph_update_days
        ]
        observed_anchors = pd.DatetimeIndex(
            graph_working.loc[
                graph_working["direction"].astype(str).eq(direction),
                "anchor_date",
            ]
        ).drop_duplicates().sort_values()
        missing = expected_anchors.difference(observed_anchors)
        unexpected = observed_anchors.difference(expected_anchors)
        rows.append(
            {
                "audit_level": "graph_anchor",
                "target_market": target_market,
                "direction": direction,
                "specification": pd.NA,
                "model": pd.NA,
                "expected_start": expected_anchors.min(),
                "observed_start": (
                    observed_anchors.min() if len(observed_anchors) else pd.NaT
                ),
                "expected_end": expected_anchors.max(),
                "observed_end": (
                    observed_anchors.max() if len(observed_anchors) else pd.NaT
                ),
                "expected_date_count": len(expected_anchors),
                "observed_date_count": len(observed_anchors),
                "missing_date_count": len(missing),
                "missing_date_ratio": (
                    len(missing) / len(expected_anchors)
                    if len(expected_anchors)
                    else np.nan
                ),
                "unexpected_date_count": len(unexpected),
                "expected_stock_count": pd.NA,
                "observed_stock_count": pd.NA,
                "missing_stock_count": pd.NA,
                "missing_stock_ratio": pd.NA,
                "minimum_daily_stock_count": pd.NA,
                "maximum_daily_stock_count": pd.NA,
                "minimum_daily_stock_coverage_ratio": pd.NA,
                "prediction_key_count": pd.NA,
                "prediction_key_sha256": pd.NA,
                "keys_identical_across_specifications_and_models": pd.NA,
                "status": (
                    "complete"
                    if not len(missing)
                    and not len(unexpected)
                    and len(observed_anchors) == len(expected_anchors)
                    else "incomplete"
                ),
            }
        )

    prediction_rows: list[dict[str, object]] = []
    for target_market in ("CN", "US"):
        expected_dates = expected_dates_by_market[target_market]
        expected_codes = expected_codes_by_market[target_market]
        for specification in config.baseline.specifications:
            expected_direction = config.baseline.expected_direction(
                specification,
                target_market,
            )
            for model in config.m3.prediction.all_model_names:
                scope = predictions.loc[
                    predictions["target_market"].astype(str).eq(target_market)
                    & predictions["specification"].astype(str).eq(specification)
                    & predictions["direction"].astype(str).eq(expected_direction)
                    & predictions["model"].astype(str).eq(model)
                ].copy()
                scope["target_date"] = pd.to_datetime(
                    scope["target_date"], errors="raise"
                ).dt.normalize()
                if scope.duplicated(["target_date", "target_code"]).any():
                    raise FormalCoverageError(
                        "正式预测覆盖门禁发现重复日期/股票键",
                        pd.DataFrame(prediction_rows),
                    )
                observed_dates = pd.DatetimeIndex(
                    scope["target_date"].drop_duplicates()
                ).sort_values()
                observed_codes = set(scope["target_code"].astype(str))
                missing_dates = expected_dates.difference(observed_dates)
                unexpected_dates = observed_dates.difference(expected_dates)
                missing_codes = expected_codes - observed_codes
                unexpected_codes = observed_codes - expected_codes
                daily_stock_counts = (
                    scope.groupby("target_date", observed=True)[
                        "target_code"
                    ].nunique()
                )
                minimum_daily_stock_count = (
                    int(daily_stock_counts.min())
                    if len(daily_stock_counts)
                    else 0
                )
                maximum_daily_stock_count = (
                    int(daily_stock_counts.max())
                    if len(daily_stock_counts)
                    else 0
                )
                daily_stock_coverage_complete = (
                    len(daily_stock_counts) == len(expected_dates)
                    and daily_stock_counts.eq(len(expected_codes)).all()
                )
                complete = (
                    not len(missing_dates)
                    and not len(unexpected_dates)
                    and not missing_codes
                    and not unexpected_codes
                    and len(observed_dates) == len(expected_dates)
                    and observed_dates.min() == expected_dates.min()
                    and observed_dates.max() == expected_dates.max()
                    and daily_stock_coverage_complete
                )
                prediction_rows.append(
                    {
                        "audit_level": "prediction_group",
                        "target_market": target_market,
                        "direction": expected_direction,
                        "specification": specification,
                        "model": model,
                        "expected_start": expected_dates.min(),
                        "observed_start": (
                            observed_dates.min()
                            if len(observed_dates)
                            else pd.NaT
                        ),
                        "expected_end": expected_dates.max(),
                        "observed_end": (
                            observed_dates.max()
                            if len(observed_dates)
                            else pd.NaT
                        ),
                        "expected_date_count": len(expected_dates),
                        "observed_date_count": len(observed_dates),
                        "missing_date_count": len(missing_dates),
                        "missing_date_ratio": (
                            len(missing_dates) / len(expected_dates)
                        ),
                        "unexpected_date_count": len(unexpected_dates),
                        "expected_stock_count": len(expected_codes),
                        "observed_stock_count": len(observed_codes),
                        "missing_stock_count": len(missing_codes),
                        "missing_stock_ratio": (
                            len(missing_codes) / len(expected_codes)
                        ),
                        "minimum_daily_stock_count": (
                            minimum_daily_stock_count
                        ),
                        "maximum_daily_stock_count": (
                            maximum_daily_stock_count
                        ),
                        "minimum_daily_stock_coverage_ratio": (
                            minimum_daily_stock_count / len(expected_codes)
                        ),
                        "prediction_key_count": int(
                            scope[["target_date", "target_code"]]
                            .drop_duplicates()
                            .shape[0]
                        ),
                        "prediction_key_sha256": _key_set_sha256(scope),
                        "keys_identical_across_specifications_and_models": pd.NA,
                        "status": "complete" if complete else "incomplete",
                    }
                )
    prediction_audit = pd.DataFrame(prediction_rows)
    for target_market in ("CN", "US"):
        mask = prediction_audit["target_market"].eq(target_market)
        hashes = set(
            prediction_audit.loc[mask, "prediction_key_sha256"].astype(str)
        )
        identical = len(hashes) == 1
        prediction_audit.loc[
            mask,
            "keys_identical_across_specifications_and_models",
        ] = identical
        if not identical:
            prediction_audit.loc[mask, "status"] = "incomplete"
    audit = pd.concat([pd.DataFrame(rows), prediction_audit], ignore_index=True)
    failed = audit.loc[~audit["status"].eq("complete")]
    if not failed.empty:
        raise FormalCoverageError(
            "2016–2021 两方向/三规格/十模型正式覆盖门禁失败: "
            f"{failed.head(20).to_dict(orient='records')}",
            audit,
        )
    return audit


def audit_formal_prediction_coverage(
    predictions: pd.DataFrame,
    *,
    eligibility_frames: Mapping[str, pd.DataFrame],
    config: M4Config = DEFAULT_M4_CONFIG,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """按 AS2/AS14 动态资格集合做键级等式门禁并显式求三规格交集。

    全股票池逐日机会仅作为分母；是否必须产出预测由图/特征及
    complete-case 审计独立决定。禁止用模型实际输出反推动资格。
    """
    required_eligibility = (
        "direction",
        "prediction_date",
        "snapshot_date",
        "target_code",
        "specification",
        "target_market",
        "feature_set",
        "graph_has_in_edges",
        "feature_count",
        "complete_case_nobs",
        "min_required_nobs",
        "predictor_complete",
        "actual_return_available",
        "historical_liquidity_available",
        "eligibility_status",
        "exclusion_reason",
    )
    expected_specs = config.baseline.specifications
    if set(eligibility_frames) != set(expected_specs):
        raise ValueError("动态资格审计未覆盖全部三规格")
    eligibility_parts: list[pd.DataFrame] = []
    for specification in expected_specs:
        frame = eligibility_frames[specification].copy()
        _require_columns(
            frame,
            required_eligibility,
            f"{specification} 动态资格审计",
        )
        observed_specs = set(frame["specification"].astype(str))
        if observed_specs != {specification}:
            raise FormalCoverageError(
                f"{specification} 动态资格审计规格标签不一致",
                frame,
            )
        eligibility_parts.append(frame)
    eligibility = pd.concat(eligibility_parts, ignore_index=True)
    eligibility["prediction_date"] = pd.to_datetime(
        eligibility["prediction_date"], errors="raise"
    ).dt.normalize()
    eligibility["snapshot_date"] = pd.to_datetime(
        eligibility["snapshot_date"], errors="raise"
    ).dt.normalize()
    opportunity_keys = [
        "specification",
        "target_market",
        "direction",
        "feature_set",
        "prediction_date",
        "target_code",
    ]
    if eligibility.duplicated(opportunity_keys).any():
        duplicates = eligibility.loc[
            eligibility.duplicated(opportunity_keys, keep=False),
            opportunity_keys,
        ]
        raise FormalCoverageError(
            "动态资格审计存在重复机会键",
            duplicates,
        )
    try:
        eligibility = validate_eligibility_audit(
            eligibility,
            context="M4 动态资格消费门禁",
        )
    except EligibilityDecisionError as exc:
        raise FormalCoverageError(str(exc), exc.audit) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise FormalCoverageError(str(exc), eligibility) from exc
    reasons = eligibility["exclusion_reason"].fillna("").astype(str)
    predictable = eligibility["expected_eligibility_status"].astype(str).eq(
        "predictable"
    )
    excluded = ~predictable

    daily_group = [
        "specification",
        "target_market",
        "direction",
        "feature_set",
        "prediction_date",
    ]
    daily = (
        eligibility.assign(
            _no_in_edges=reasons.eq("no_in_edges"),
            _complete_case_insufficient=reasons.eq(
                "complete_case_insufficient"
            ),
            _required_observation_missing=reasons.eq(
                "required_observation_missing"
            ),
            _predictable=predictable,
        )
        .groupby(daily_group, observed=True, sort=False)
        .agg(
            opportunity_count=("target_code", "size"),
            no_in_edges_count=("_no_in_edges", "sum"),
            complete_case_insufficient_count=(
                "_complete_case_insufficient",
                "sum",
            ),
            required_observation_missing_count=(
                "_required_observation_missing",
                "sum",
            ),
            predictable_count=("_predictable", "sum"),
        )
        .reset_index()
    )
    universe_size = (
        eligibility.groupby(
            ["specification", "target_market", "direction", "feature_set"],
            observed=True,
        )["target_code"]
        .nunique()
        .rename("audited_universe_count")
        .reset_index()
    )
    daily = daily.merge(
        universe_size,
        on=["specification", "target_market", "direction", "feature_set"],
        how="left",
        validate="many_to_one",
    )
    incomplete_opportunity_days = ~daily["opportunity_count"].eq(
        daily["audited_universe_count"]
    )
    zero_predictable_days = daily["predictable_count"].eq(0)
    if incomplete_opportunity_days.any() or zero_predictable_days.any():
        raise FormalCoverageError(
            "机会全集不完整或出现整日动态可预测键为零",
            daily.loc[incomplete_opportunity_days | zero_predictable_days],
        )

    _require_columns(
        predictions,
        (
            "specification",
            "target_market",
            "direction",
            "feature_set",
            "target_date",
            "target_code",
            "model",
            "prediction",
            "actual_return",
            "historical_liquidity",
        ),
        "动态预测输出门禁",
    )
    actual = predictions.copy()
    actual["target_date"] = pd.to_datetime(
        actual["target_date"], errors="raise"
    ).dt.normalize()
    actual_base_keys = [
        "specification",
        "target_market",
        "direction",
        "feature_set",
        "target_date",
        "target_code",
    ]
    if actual.duplicated([*actual_base_keys, "model"]).any():
        raise FormalCoverageError(
            "动态可预测输出存在重复基础键/模型",
            actual.loc[
                actual.duplicated([*actual_base_keys, "model"], keep=False)
            ],
        )
    expected_models = frozenset(config.m3.prediction.all_model_names)
    unknown_models = set(actual["model"].astype(str)) - expected_models
    if unknown_models:
        raise FormalCoverageError(
            f"动态预测输出含未登记模型: {sorted(unknown_models)}",
            actual,
        )
    eligibility_for_output = eligibility.loc[
        :,
        [*opportunity_keys, "eligibility_status", "exclusion_reason"],
    ].rename(columns={"prediction_date": "target_date"})
    actual = actual.merge(
        eligibility_for_output,
        on=actual_base_keys,
        how="left",
        validate="many_to_one",
        indicator="_eligibility_key_merge",
    )
    unregistered_output = ~actual["_eligibility_key_merge"].astype(str).eq(
        "both"
    )
    if unregistered_output.any():
        raise FormalCoverageError(
            "模型输出存在资格机会全集之外的未登记键",
            actual.loc[unregistered_output],
        )
    raw_output_counts = (
        actual.groupby(actual_base_keys, observed=True, sort=False)
        .agg(raw_model_output_row_count=("model", "size"))
        .reset_index()
        .rename(columns={"target_date": "prediction_date"})
    )
    actual = actual.loc[
        actual["eligibility_status"].astype(str).eq("predictable")
    ].copy()
    numeric = actual.loc[
        :, ["prediction", "actual_return", "historical_liquidity"]
    ].apply(pd.to_numeric, errors="coerce")
    actual["_row_finite"] = np.isfinite(
        numeric.to_numpy(dtype=np.float64, na_value=np.nan)
    ).all(axis=1)
    actual_groups = (
        actual.groupby(actual_base_keys, observed=True, sort=False)
        .agg(
            observed_model_count=("model", "nunique"),
            observed_model_set=(
                "model",
                lambda values: frozenset(values.astype(str)),
            ),
            finite_model_row_count=("_row_finite", "sum"),
        )
        .reset_index()
        .rename(columns={"target_date": "prediction_date"})
    )
    expected_keys = eligibility.loc[
        predictable,
        opportunity_keys,
    ].copy()
    key_merge_columns = opportunity_keys
    output_check = expected_keys.merge(
        actual_groups,
        on=key_merge_columns,
        how="outer",
        validate="one_to_one",
        indicator="prediction_key_merge",
    )
    output_check["model_set_complete"] = (
        output_check["observed_model_set"].map(
            lambda value: value == expected_models
            if isinstance(value, frozenset)
            else False
        )
    )
    output_check["finite_ten_model_rows"] = output_check[
        "finite_model_row_count"
    ].eq(len(expected_models))
    output_check["status"] = np.where(
        output_check["prediction_key_merge"].astype(str).eq("both")
        & output_check["model_set_complete"]
        & output_check["finite_ten_model_rows"],
        "complete",
        "incomplete",
    )
    failed_output = output_check.loc[~output_check["status"].eq("complete")]
    if not failed_output.empty:
        raise FormalCoverageError(
            "动态可预测基础键与十模型输出集合不完全相等",
            output_check,
        )

    daily_actual = (
        output_check.groupby(daily_group, observed=True, sort=False)
        .agg(actual_complete_key_count=("status", "size"))
        .reset_index()
    )
    daily = daily.merge(
        daily_actual,
        on=daily_group,
        how="left",
        validate="one_to_one",
    )
    daily["actual_complete_key_count"] = (
        daily["actual_complete_key_count"].fillna(0).astype(int)
    )
    for count_column in (
        "no_in_edges_count",
        "complete_case_insufficient_count",
        "required_observation_missing_count",
        "predictable_count",
        "actual_complete_key_count",
    ):
        daily[count_column.replace("_count", "_rate")] = (
            daily[count_column] / daily["opportunity_count"]
        )
    if not daily["actual_complete_key_count"].eq(
        daily["predictable_count"]
    ).all():
        raise FormalCoverageError(
            "逐日动态可预测键与实际十模型完整键计数不相等",
            daily,
        )
    overall_group = [
        "specification",
        "target_market",
        "direction",
        "feature_set",
    ]
    overall = (
        daily.groupby(overall_group, observed=True, sort=False)
        .agg(
            opportunity_count=("opportunity_count", "sum"),
            no_in_edges_count=("no_in_edges_count", "sum"),
            complete_case_insufficient_count=(
                "complete_case_insufficient_count",
                "sum",
            ),
            required_observation_missing_count=(
                "required_observation_missing_count",
                "sum",
            ),
            predictable_count=("predictable_count", "sum"),
            actual_complete_key_count=("actual_complete_key_count", "sum"),
        )
        .reset_index()
    )
    for count_column in (
        "no_in_edges_count",
        "complete_case_insufficient_count",
        "required_observation_missing_count",
        "predictable_count",
        "actual_complete_key_count",
    ):
        overall[count_column.replace("_count", "_rate")] = (
            overall[count_column] / overall["opportunity_count"]
        )

    normalized_key_columns = [
        "target_market",
        "feature_set",
        "prediction_date",
        "target_code",
    ]
    common_parts: list[pd.DataFrame] = []
    intersection_key_parts: list[pd.DataFrame] = []
    intersection_audits: list[dict[str, object]] = []
    for (target_market, feature_set), market_scope in expected_keys.groupby(
        ["target_market", "feature_set"],
        observed=True,
        sort=False,
    ):
        sets: dict[str, set[tuple[object, ...]]] = {}
        opportunity_sets: dict[str, set[tuple[object, ...]]] = {}
        for specification in expected_specs:
            scope = market_scope.loc[
                market_scope["specification"].astype(str).eq(specification),
                normalized_key_columns,
            ]
            sets[specification] = set(
                scope.itertuples(index=False, name=None)
            )
            opportunity_scope = eligibility.loc[
                eligibility["target_market"].astype(str).eq(
                    str(target_market)
                )
                & eligibility["feature_set"].astype(str).eq(str(feature_set))
                & eligibility["specification"].astype(str).eq(specification),
                normalized_key_columns,
            ]
            opportunity_sets[specification] = set(
                opportunity_scope.itertuples(index=False, name=None)
            )
        if any(
            opportunity_sets[specification]
            != opportunity_sets[expected_specs[0]]
            for specification in expected_specs[1:]
        ):
            raise FormalCoverageError(
                f"{target_market}/{feature_set} 三规格机会全集不一致",
                eligibility.loc[
                    eligibility["target_market"].astype(str).eq(
                        str(target_market)
                    )
                    & eligibility["feature_set"].astype(str).eq(
                        str(feature_set)
                    )
                ],
            )
        common = set.intersection(*(sets[spec] for spec in expected_specs))
        if not common:
            raise FormalCoverageError(
                f"{target_market}/{feature_set} 三规格动态共同键为空",
                market_scope,
            )
        common_frame = pd.DataFrame(common, columns=normalized_key_columns)
        common_parts.append(common_frame)
        intersection_keys = (
            eligibility.loc[
                eligibility["target_market"].astype(str).eq(str(target_market))
                & eligibility["feature_set"].astype(str).eq(str(feature_set)),
                normalized_key_columns,
            ]
            .drop_duplicates()
            .reset_index(drop=True)
        )
        for specification in expected_specs:
            specification_status = eligibility.loc[
                eligibility["target_market"].astype(str).eq(
                    str(target_market)
                )
                & eligibility["feature_set"].astype(str).eq(str(feature_set))
                & eligibility["specification"].astype(str).eq(specification),
                [
                    *normalized_key_columns,
                    "eligibility_status",
                    "exclusion_reason",
                ],
            ].rename(
                columns={
                    "eligibility_status": (
                        f"{specification}_eligibility_status"
                    ),
                    "exclusion_reason": (
                        f"{specification}_exclusion_reason"
                    ),
                }
            )
            intersection_keys = intersection_keys.merge(
                specification_status,
                on=normalized_key_columns,
                how="left",
                validate="one_to_one",
            )
        status_columns = [
            f"{specification}_eligibility_status"
            for specification in expected_specs
        ]
        intersection_keys["in_explicit_common_set"] = (
            intersection_keys[status_columns]
            .eq("predictable")
            .all(axis=1)
        )

        def contraction_reason(row: pd.Series) -> str:
            reasons_for_key = [
                f"{specification}:{row[f'{specification}_exclusion_reason']}"
                for specification in expected_specs
                if row[f"{specification}_eligibility_status"]
                != "predictable"
            ]
            return "|".join(reasons_for_key)

        intersection_keys["common_set_contraction_reason"] = (
            intersection_keys.apply(contraction_reason, axis=1)
        )
        intersection_keys["audit_level"] = "three_spec_intersection_key"
        intersection_keys["status"] = "complete"
        intersection_key_parts.append(intersection_keys)
        common_daily = common_frame.groupby("prediction_date")[
            "target_code"
        ].nunique()
        audited_dates = pd.DatetimeIndex(
            market_scope["prediction_date"].drop_duplicates()
        )
        missing_common_dates = audited_dates.difference(
            pd.DatetimeIndex(common_daily.index)
        )
        if common_daily.eq(0).any() or len(missing_common_dates):
            raise FormalCoverageError("三规格共同键出现空日", common_frame)
        intersection_audits.append(
            {
                "audit_level": "explicit_three_spec_intersection",
                "target_market": target_market,
                "feature_set": feature_set,
                "cross_market_predictable_count": len(
                    sets[expected_specs[0]]
                ),
                "same_market_graph_predictable_count": len(
                    sets[expected_specs[1]]
                ),
                "non_graph_predictable_count": len(
                    sets[expected_specs[2]]
                ),
                "common_key_count": len(common),
                "cross_market_contraction_count": (
                    len(sets[expected_specs[0]]) - len(common)
                ),
                "same_market_graph_contraction_count": (
                    len(sets[expected_specs[1]]) - len(common)
                ),
                "non_graph_contraction_count": (
                    len(sets[expected_specs[2]]) - len(common)
                ),
                "intersection_constructed_from_audited_sets": True,
                "status": "complete",
            }
        )
    common_keys = (
        pd.concat(common_parts, ignore_index=True)
        .drop_duplicates()
        .sort_values(normalized_key_columns)
        .reset_index(drop=True)
    )
    key_audit = eligibility.copy()
    key_audit = key_audit.merge(
        raw_output_counts,
        on=opportunity_keys,
        how="left",
        validate="one_to_one",
    )
    key_audit["raw_model_output_row_count"] = (
        key_audit["raw_model_output_row_count"].fillna(0).astype(int)
    )
    key_audit["output_removed_by_legal_exclusion"] = (
        key_audit["eligibility_status"].astype(str).eq("legally_excluded")
        & key_audit["raw_model_output_row_count"].gt(0)
    )
    output_evidence = output_check.loc[
        :,
        [
            *opportunity_keys,
            "observed_model_count",
            "observed_model_set",
            "finite_model_row_count",
            "prediction_key_merge",
            "model_set_complete",
            "finite_ten_model_rows",
            "status",
        ],
    ].rename(columns={"status": "ten_model_output_status"})
    key_audit = key_audit.merge(
        output_evidence,
        on=opportunity_keys,
        how="left",
        validate="one_to_one",
    )
    key_audit["ten_model_output_status"] = key_audit[
        "ten_model_output_status"
    ].fillna("not_applicable_legal_exclusion")
    intersection_key_audit = pd.concat(
        intersection_key_parts,
        ignore_index=True,
        sort=False,
    )
    key_audit = key_audit.merge(
        intersection_key_audit.drop(
            columns=["audit_level", "status"],
        ),
        on=normalized_key_columns,
        how="left",
        validate="many_to_one",
    )
    if key_audit["in_explicit_common_set"].isna().any():
        raise AssertionError("逐键资格审计未完整绑定三规格显式交集证据")
    key_audit.insert(0, "audit_level", "eligibility_key")
    daily.insert(0, "audit_level", "daily_opportunity_summary")
    overall.insert(0, "audit_level", "full_sample_opportunity_summary")
    audit = pd.concat(
        [
            key_audit,
            daily,
            overall,
            pd.DataFrame(intersection_audits),
        ],
        ignore_index=True,
        sort=False,
    )
    return audit, common_keys


def run_m4_portfolios(
    specification_frames: Mapping[str, pd.DataFrame],
    *,
    eligibility_frames: Mapping[str, pd.DataFrame],
    config: M4Config = DEFAULT_M4_CONFIG,
) -> M4PortfolioResult:
    """合并三规格、执行完整性/交集门槛并运行六个嵌套组合。"""
    expected_specs = config.baseline.specifications
    if set(specification_frames) != set(expected_specs):
        raise ValueError(
            "三规格输入名称不符: "
            f"actual={sorted(specification_frames)}, "
            f"expected={sorted(expected_specs)}"
        )
    combined_parts: list[pd.DataFrame] = []
    for specification in expected_specs:
        frame = specification_frames[specification].copy()
        _require_columns(frame, ("specification",), f"{specification} 预测面板")
        observed = set(frame["specification"].astype(str))
        if observed and observed != {specification}:
            raise ValueError(
                f"{specification} 输入中的 specification 实际为 {sorted(observed)}"
            )
        combined_parts.append(frame)
    combined = pd.concat(combined_parts, ignore_index=True)
    formal_coverage_audit, common_keys = audit_formal_prediction_coverage(
        combined,
        eligibility_frames=eligibility_frames,
        config=config,
    )
    complete = enforce_complete_ten_model_groups(combined, config=config)
    direction_contract_audit = audit_direction_contract(
        complete.predictions,
        config=config,
    )
    incomplete_direction = ~direction_contract_audit["status"].eq("complete")
    if incomplete_direction.any():
        failed = direction_contract_audit.loc[
            incomplete_direction,
            [
                "specification",
                "target_market",
                "expected_direction",
                "status",
            ],
        ]
        raise DirectionContractError(
            "m4 双方向合同不完整，不能运行组合或形成 R3/R4："
            f"{failed.to_dict(orient='records')}",
            direction_contract_audit,
        )
    comparable = align_three_specifications(complete.predictions, config=config)
    if comparable.predictions.empty:
        raise ValueError("三规格无共同日期/股票可进入组合")
    comparable_keys = comparable.predictions.loc[
        :,
        ["target_market", "feature_set", "target_date", "target_code"],
    ].drop_duplicates().rename(columns={"target_date": "prediction_date"})
    common_check = common_keys.merge(
        comparable_keys,
        on=["target_market", "feature_set", "prediction_date", "target_code"],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    if not common_check["_merge"].astype(str).eq("both").all():
        raise FormalCoverageError(
            "三规格对齐结果不是已审计动态集合的显式交集",
            common_check,
        )
    timing_audit = audit_execution_timing(comparable.predictions, config=config)
    settings = SignedLiquidityPortfolioSettings(
        group_columns=(
            "specification",
            "feature_set",
            "direction",
            "target_market",
            "model",
        ),
        date_column="target_date",
        stock_column="target_code",
        prediction_column="prediction",
        realized_return_column="actual_return",
        liquidity_column="historical_liquidity",
        market_column="target_market",
        portfolio_fractions=config.portfolio.portfolio_fractions,
        participation_rate=config.portfolio.liquidity_participation_rate,
        market_position_caps=config.portfolio.position_caps(),
        periods_per_year=config.portfolio.annualization_days,
        minimum_sharpe_observations=(
            config.portfolio.minimum_sharpe_observations
        ),
        transaction_cost_rate=config.portfolio.transaction_cost_rate,
    )
    portfolios = run_signed_liquidity_portfolios(
        comparable.predictions,
        settings,
    )
    return M4PortfolioResult(
        predictions=comparable.predictions,
        model_completeness_audit=complete.audit,
        comparability_audit=comparable.audit,
        execution_timing_audit=timing_audit,
        direction_contract_audit=direction_contract_audit,
        formal_coverage_audit=formal_coverage_audit,
        portfolios=portfolios,
    )


def _audit_sharpe_direction_contract(
    sharpe_metrics: pd.DataFrame,
    *,
    config: M4Config,
) -> pd.DataFrame:
    """以可计算 Sharpe 核验核心对照所需的六个规格方向腿。"""
    rows: list[dict[str, object]] = []
    for specification in config.baseline.specifications:
        for target_market in ("CN", "US"):
            expected_direction = config.baseline.expected_direction(
                specification,
                target_market,
            )
            scope = sharpe_metrics.loc[
                sharpe_metrics["specification"].astype(str).eq(specification)
                & sharpe_metrics["target_market"].astype(str).eq(target_market)
            ]
            matched = scope.loc[
                scope["direction"].astype(str).eq(expected_direction)
            ]
            unexpected_count = int(
                (~scope["direction"].astype(str).eq(expected_direction)).sum()
            )
            observation_count = int(
                matched.loc[
                    :, ["feature_set", "model", "portfolio"]
                ].drop_duplicates().shape[0]
            )
            if unexpected_count:
                status = "unexpected_direction_present"
            elif observation_count == 0:
                status = "missing_expected_direction"
            else:
                status = "complete"
            rows.append(
                {
                    "specification": specification,
                    "target_market": target_market,
                    "expected_direction": expected_direction,
                    "comparison_direction": (
                        config.baseline.comparison_direction(target_market)
                    ),
                    "observation_group_count": observation_count,
                    "prediction_row_count": len(matched),
                    "unexpected_direction_row_count": unexpected_count,
                    "status": status,
                }
            )
    return (
        pd.DataFrame(rows)
        .loc[:, list(DIRECTION_CONTRACT_AUDIT_DTYPES)]
        .astype(DIRECTION_CONTRACT_AUDIT_DTYPES)
    )


def build_core_comparison_tables(
    sharpe_metrics: pd.DataFrame,
    *,
    config: M4Config = DEFAULT_M4_CONFIG,
) -> CoreComparisonTables:
    """形成 R1/R3/R4 的方向、量级与相对排序观测接口。

    输出不含 ``pass``/``fail`` 字段；原图无精确标签，因此只登记观测值、
    与 1/2 的距离以及配对次序，最终判定留给 verifier/check_gates。
    """
    required = (
        "specification",
        "feature_set",
        "direction",
        "target_market",
        "model",
        "portfolio",
        "annualized_sharpe",
        "sharpe_status",
    )
    _require_columns(sharpe_metrics, required, "核心结果对照")
    valid = sharpe_metrics.loc[
        sharpe_metrics["sharpe_status"].eq("ok")
    ].copy()
    valid["annualized_sharpe"] = pd.to_numeric(
        valid["annualized_sharpe"], errors="raise"
    )
    direction_contract_audit = _audit_sharpe_direction_contract(
        valid,
        config=config,
    )
    incomplete_direction = ~direction_contract_audit["status"].eq("complete")
    if incomplete_direction.any():
        raise DirectionContractError(
            "R3/R4 缺少可计算的双方向 Sharpe，禁止形成核心对照",
            direction_contract_audit,
        )
    cross_spec = config.baseline.cross_market_specification

    r1 = valid.loc[
        valid["specification"].eq(cross_spec)
        & valid["direction"].eq("US_TO_CN")
        & valid["target_market"].eq("CN")
    ].copy()
    r1["element_id"] = "R1"
    r1["observed_value"] = r1["annualized_sharpe"]
    r1["gap_to_one"] = (
        r1["observed_value"] - config.comparison.r1_one_level
    )
    r1["gap_to_two"] = (
        r1["observed_value"] - config.comparison.r1_two_level
    )
    r1["reference_expectation"] = np.where(
        r1["model"].eq("SVM"),
        "SVM 多数量化组合 Sharpe 低于1",
        "其他方法多数分位 Sharpe 高于1，部分接近2",
    )
    r1["evidence_boundary"] = (
        "方向与量级；不从 Figure 8 估读精确柱高"
    )
    r1_observations = r1.loc[
        :,
        [
            "element_id",
            "feature_set",
            "model",
            "portfolio",
            "observed_value",
            "gap_to_one",
            "gap_to_two",
            "reference_expectation",
            "evidence_boundary",
        ],
    ]

    r1_summary = (
        r1.groupby(["feature_set", "model"], observed=True)
        .agg(
            comparison_count=("annualized_sharpe", "size"),
            median_sharpe=("annualized_sharpe", "median"),
            minimum_sharpe=("annualized_sharpe", "min"),
            maximum_sharpe=("annualized_sharpe", "max"),
            fraction_below_one=(
                "annualized_sharpe",
                lambda values: float(
                    values.lt(config.comparison.r1_one_level).mean()
                ),
            ),
            fraction_above_one=(
                "annualized_sharpe",
                lambda values: float(
                    values.gt(config.comparison.r1_one_level).mean()
                ),
            ),
        )
        .reset_index()
    )
    r1_summary.insert(0, "element_id", "R1")
    r1_summary["reference_expectation"] = np.where(
        r1_summary["model"].eq("SVM"),
        "多数分位低于1",
        "多数分位高于1，部分接近2",
    )
    r1_summary["strong_model_reference"] = r1_summary["model"].isin(
        config.comparison.r1_strong_models
    )

    cross = valid.loc[valid["specification"].eq(cross_spec)].copy()
    pair_keys = ["feature_set", "model", "portfolio"]
    us_to_cn = cross.loc[
        cross["direction"].eq("US_TO_CN"),
        [*pair_keys, "annualized_sharpe"],
    ].rename(columns={"annualized_sharpe": "us_to_cn_sharpe"})
    cn_to_us = cross.loc[
        cross["direction"].eq("CN_TO_US"),
        [*pair_keys, "annualized_sharpe"],
    ].rename(columns={"annualized_sharpe": "cn_to_us_sharpe"})
    r3 = us_to_cn.merge(
        cn_to_us,
        on=pair_keys,
        how="outer",
        validate="one_to_one",
        indicator="_pair_status",
    )
    incomplete_r3 = ~r3["_pair_status"].eq("both")
    if incomplete_r3.any():
        r3_audit = r3.loc[
            incomplete_r3,
            [*pair_keys, "_pair_status"],
        ].rename(columns={"_pair_status": "status"})
        raise DirectionContractError(
            "R3 双方向 Sharpe 键不成对，禁止形成 R3 判定",
            r3_audit,
        )
    r3 = r3.drop(columns="_pair_status")
    r3.insert(0, "element_id", "R3")
    r3["difference_cn_to_us_minus_us_to_cn"] = (
        r3["cn_to_us_sharpe"] - r3["us_to_cn_sharpe"]
    )
    r3["observed_order"] = np.where(
        r3["difference_cn_to_us_minus_us_to_cn"].lt(0),
        "CN_TO_US_lower",
        "CN_TO_US_not_lower",
    )
    r3["reference_expectation"] = (
        "CN_TO_US 在各模型与分位上显著弱于 US_TO_CN"
    )
    r3["evidence_boundary"] = "方向比较；不从 Figure 9 估读精确柱高"

    specification_keys = [
        "target_market",
        "feature_set",
        "model",
        "portfolio",
    ]
    r4_working = valid.copy()
    r4_working["comparison_direction"] = r4_working["target_market"].map(
        config.baseline.comparison_direction
    )
    r4_pair_keys = [
        "comparison_direction",
        "target_market",
        "feature_set",
        "model",
        "portfolio",
    ]
    expected_specs = frozenset(config.baseline.specifications)
    r4_pair_audit = (
        r4_working.groupby(r4_pair_keys, observed=True)
        .agg(
            specification_set=(
                "specification",
                lambda values: frozenset(values.astype(str)),
            )
        )
        .reset_index()
    )
    r4_pair_audit["status"] = r4_pair_audit["specification_set"].map(
        lambda values: (
            "complete"
            if values == expected_specs
            else "missing_specification"
        )
    )
    incomplete_r4 = ~r4_pair_audit["status"].eq("complete")
    if incomplete_r4.any():
        raise DirectionContractError(
            "R4 三规格在双方向分腿后存在不可配对 Sharpe，禁止形成 R4 判定",
            r4_pair_audit.loc[incomplete_r4].reset_index(drop=True),
        )
    specification_sharpe = (
        r4_working.groupby(
            [*specification_keys, "specification"],
            observed=True,
        )["annualized_sharpe"]
        .first()
        .unstack("specification")
        .reset_index()
    )
    required_specs = config.baseline.specifications
    for specification in required_specs:
        if specification not in specification_sharpe.columns:
            specification_sharpe[specification] = np.nan
    r4 = specification_sharpe.dropna(subset=list(required_specs)).copy()
    r4.insert(0, "element_id", "R4")
    r4["same_graph_minus_non_graph"] = (
        r4[config.baseline.same_market_graph_specification]
        - r4[config.baseline.non_graph_specification]
    )
    r4["cross_minus_same_graph"] = (
        r4[config.baseline.cross_market_specification]
        - r4[config.baseline.same_market_graph_specification]
    )
    r4["cross_is_strongest"] = r4[
        config.baseline.cross_market_specification
    ].eq(r4.loc[:, list(required_specs)].max(axis=1))
    r4["reference_expectation"] = (
        "图同市场优于非图同市场，跨市场图总体最强"
    )
    r4["evidence_boundary"] = (
        "相对排序；不从 Figure 12/13 估读精确柱高"
    )

    r3_summary = pd.DataFrame(
        [
            {
                "element_id": "R3",
                "comparison_count": len(r3),
                "fraction_cn_to_us_lower": (
                    float(
                        r3["difference_cn_to_us_minus_us_to_cn"].lt(0).mean()
                    )
                    if len(r3)
                    else np.nan
                ),
                "mean_difference": (
                    float(
                        r3[
                            "difference_cn_to_us_minus_us_to_cn"
                        ].mean()
                    )
                    if len(r3)
                    else np.nan
                ),
                "reference_expectation": (
                    "CN_TO_US 在各模型与分位上显著弱于 US_TO_CN"
                ),
            }
        ]
    )
    r4_summary = pd.DataFrame(
        [
            {
                "element_id": "R4",
                "comparison_count": len(r4),
                "fraction_same_graph_above_non_graph": (
                    float(r4["same_graph_minus_non_graph"].gt(0).mean())
                    if len(r4)
                    else np.nan
                ),
                "fraction_cross_is_strongest": (
                    float(r4["cross_is_strongest"].mean())
                    if len(r4)
                    else np.nan
                ),
                "mean_same_graph_minus_non_graph": (
                    float(r4["same_graph_minus_non_graph"].mean())
                    if len(r4)
                    else np.nan
                ),
                "mean_cross_minus_same_graph": (
                    float(r4["cross_minus_same_graph"].mean())
                    if len(r4)
                    else np.nan
                ),
                "reference_expectation": (
                    "图同市场优于非图同市场，跨市场图总体最强"
                ),
            }
        ]
    )
    summary = pd.concat(
        [r1_summary, r3_summary, r4_summary],
        ignore_index=True,
        sort=False,
    )
    paired = pd.concat(
        [
            r3,
            r4,
        ],
        ignore_index=True,
        sort=False,
    )
    return CoreComparisonTables(
        observations=r1_observations.reset_index(drop=True),
        paired_comparisons=paired.reset_index(drop=True),
        summary=summary.reset_index(drop=True),
        direction_contract_audit=direction_contract_audit,
    )
