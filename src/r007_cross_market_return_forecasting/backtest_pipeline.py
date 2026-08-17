"""r007 m4：同市场图与 25 日非图自回归基线预测。

同市场图复用 m2 图筛边及 m3 十模型接口；非图基线只在本模块构造
F22 明确要求的逐股 25 日滞后特征，训练、缩尾和预测均严格滚动。
本模块不执行正式全期回测、不写 ``output/results``。
"""

from __future__ import annotations

from collections.abc import (
    Callable,
    Collection,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

from common.ml_pipeline import fit_regression_model_batch

from .config import (
    DEFAULT_M4_CONFIG,
    DirectionConfig,
    M3Config,
    M4Config,
)
from .data_pipeline import (
    apply_stock_winsor_limits,
    winsorize_training_window,
)
from .graph_pipeline import (
    build_update_blocks,
    iter_rolling_graph_snapshots,
    prepare_target_feature_matrices,
)
from .model_pipeline import (
    ELIGIBILITY_AUDIT_SCHEMA,
    PREDICTION_KEY_COLUMNS,
    SnapshotPredictionResult,
    _canonical_frame,
    derive_eligibility_decision,
    predict_graph_snapshot,
)
from .strategy import (
    build_base_model_factories,
    build_ensemble_predictions,
)


@dataclass
class AutoregressivePredictionResult:
    """一个十日更新块的非图预测及其训练/缩尾审计。"""

    predictions: pd.DataFrame
    training_audit: pd.DataFrame
    model_audit: pd.DataFrame
    winsor_limits: pd.DataFrame
    eligibility_audit: pd.DataFrame


@dataclass
class AutoregressivePredictionTables:
    """流式非图结果的可落盘表结构，由 m5/main 选择写出。"""

    predictions: pd.DataFrame
    training_audit: pd.DataFrame
    model_audit: pd.DataFrame
    winsor_limits: pd.DataFrame
    eligibility_audit: pd.DataFrame


def _require_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
    context: str,
) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise KeyError(f"{context} 缺少字段: {missing}")


def _market_panel(
    target_panel: pd.DataFrame,
    *,
    target_codes: Sequence[str] | None,
    config: M4Config,
) -> pd.DataFrame:
    """规范目标市场面板并可选限制为与跨市场规格一致的目标集合。"""
    returns = config.m3.pipeline.returns
    required = (
        returns.stock_column,
        returns.date_column,
        config.m3.prediction.source_value_column,
        config.m3.prediction.target_value_column,
        returns.liquidity_median_column,
    )
    _require_columns(target_panel, required, "同市场基线目标面板")
    panel = target_panel.copy()
    panel[returns.stock_column] = panel[returns.stock_column].astype(str)
    panel[returns.date_column] = pd.to_datetime(
        panel[returns.date_column], errors="raise"
    ).dt.normalize()
    if panel.duplicated([returns.stock_column, returns.date_column]).any():
        raise ValueError("同市场基线面板存在重复 stock_code/date 键")
    if target_codes is not None:
        requested = tuple(dict.fromkeys(str(value) for value in target_codes))
        observed = set(panel[returns.stock_column])
        missing_codes = sorted(set(requested) - observed)
        if missing_codes:
            raise KeyError(
                "同市场基线目标集合含面板中不存在的股票: "
                f"{missing_codes[:10]}"
            )
        panel = panel.loc[panel[returns.stock_column].isin(requested)].copy()
    if panel.empty:
        raise ValueError("同市场基线目标面板为空")
    return panel.sort_values(
        [returns.stock_column, returns.date_column]
    ).reset_index(drop=True)


def build_same_market_calendar_mapping(
    target_panel: pd.DataFrame,
    *,
    market: str,
    config: M4Config = DEFAULT_M4_CONFIG,
) -> pd.DataFrame:
    """用目标市场交易日历构造前一交易日信号到下一日 OPCL 的映射。"""
    returns = config.m3.pipeline.returns
    _require_columns(
        target_panel,
        (returns.date_column,),
        "同市场日历映射",
    )
    dates = (
        pd.to_datetime(target_panel[returns.date_column], errors="raise")
        .dt.normalize()
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )
    if len(dates) < 2:
        raise ValueError("同市场基线至少需要两个目标交易日")
    direction = config.baseline.same_market_direction(market)
    mapping = pd.DataFrame(
        {
            "direction": direction,
            "source_market": market,
            "target_market": market,
            "lag_parameter": config.baseline.same_market_lag,
            "target_date": dates,
            "source_date": dates.shift(config.baseline.same_market_lag),
        }
    )
    mapping["causal_available"] = mapping["source_date"].notna()
    available = mapping["causal_available"]
    if not mapping.loc[available, "source_date"].lt(
        mapping.loc[available, "target_date"]
    ).all():
        raise AssertionError("同市场映射未满足前一交易日信号、下一交易日执行")
    return mapping


def _same_market_m3_config(
    *,
    market: str,
    source_value_column: str,
    config: M4Config,
) -> tuple[DirectionConfig, M3Config]:
    """为既有 m2/m3 接口注入单一同市场方向，不改变全局默认配置。"""
    direction = DirectionConfig(
        name=config.baseline.same_market_direction(market),
        source_market=market,
        target_market=market,
        lag_parameter=config.baseline.same_market_lag,
    )
    calendar = replace(
        config.m3.pipeline.calendar,
        directions=(direction,),
    )
    pipeline = replace(config.m3.pipeline, calendar=calendar)
    prediction = replace(
        config.m3.prediction,
        source_value_column=source_value_column,
    )
    return direction, replace(
        config.m3,
        pipeline=pipeline,
        prediction=prediction,
    )


def iter_same_market_graph_predictions(
    target_panel: pd.DataFrame,
    *,
    market: str,
    target_codes: Sequence[str] | None = None,
    source_value_column: str | None = None,
    model_factories: Mapping[str, Callable[[], Any]] | None = None,
    skip_anchor_dates: Collection[pd.Timestamp] = (),
    config: M4Config = DEFAULT_M4_CONFIG,
) -> Iterator[SnapshotPredictionResult]:
    """复用 m2/m3 生成 F23 同市场图的十模型滚动预测。"""
    feature_column = (
        source_value_column
        if source_value_column is not None
        else config.baseline.default_feature_set
    )
    panel_config = replace(
        config,
        m3=replace(
            config.m3,
            prediction=replace(
                config.m3.prediction,
                source_value_column=feature_column,
            ),
        ),
    )
    panel = _market_panel(
        target_panel,
        target_codes=target_codes,
        config=panel_config,
    )
    mapping = build_same_market_calendar_mapping(
        panel,
        market=market,
        config=panel_config,
    )
    direction, m3_config = _same_market_m3_config(
        market=market,
        source_value_column=feature_column,
        config=panel_config,
    )
    factories = (
        dict(model_factories)
        if model_factories is not None
        else build_base_model_factories(m3_config)
    )
    skipped = {
        pd.Timestamp(value).normalize() for value in skip_anchor_dates
    }
    prepared_matrices = prepare_target_feature_matrices(
        panel,
        panel,
        source_value_column=feature_column,
        target_value_column=m3_config.prediction.target_value_column,
    )
    snapshots = iter_rolling_graph_snapshots(
        panel,
        panel,
        mapping,
        direction=direction.name,
        prediction_start=m3_config.prediction.prediction_start,
        prediction_end=m3_config.prediction.prediction_end,
        source_value_column=feature_column,
        target_value_column=m3_config.prediction.target_value_column,
        config=m3_config.pipeline,
    )
    for snapshot in snapshots:
        if snapshot.anchor_date in skipped:
            continue
        yield predict_graph_snapshot(
            snapshot,
            panel,
            panel,
            model_factories=factories,
            prepared_feature_matrices=prepared_matrices,
            collect_feature_values=False,
            config=m3_config,
        )


def _build_autoregressive_feature_panel(
    target_panel: pd.DataFrame,
    *,
    market_mapping: pd.DataFrame,
    source_value_column: str,
    target_value_column: str,
    lag_count: int,
    config: M4Config,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """按完整目标市场日历构造逐股 t-25…t-1 特征，不跨缺口借值。"""
    returns = config.m3.pipeline.returns
    required = (
        returns.stock_column,
        returns.date_column,
        source_value_column,
        target_value_column,
        returns.liquidity_median_column,
    )
    _require_columns(target_panel, required, "非图自回归特征面板")
    dates = pd.DatetimeIndex(
        market_mapping["target_date"].drop_duplicates().sort_values()
    )
    source_dates = market_mapping.set_index("target_date")["source_date"]
    feature_columns = tuple(
        f"lag_{lag:02d}" for lag in range(1, lag_count + 1)
    )
    parts: list[pd.DataFrame] = []
    for stock_code, stock_frame in target_panel.groupby(
        returns.stock_column,
        observed=True,
        sort=False,
    ):
        indexed = (
            stock_frame.set_index(returns.date_column)
            .loc[
                :,
                [
                    source_value_column,
                    target_value_column,
                    returns.liquidity_median_column,
                ],
            ]
            .reindex(dates)
        )
        values = pd.to_numeric(
            indexed[source_value_column], errors="coerce"
        )
        part = pd.DataFrame(
            {
                "stock_code": str(stock_code),
                "target_date": dates,
                "source_date": source_dates.reindex(dates).to_numpy(),
                "target_value": pd.to_numeric(
                    indexed[target_value_column], errors="coerce"
                ).to_numpy(),
                "actual_return": pd.to_numeric(
                    indexed[target_value_column], errors="coerce"
                ).to_numpy(),
                "historical_liquidity": pd.to_numeric(
                    indexed[returns.liquidity_median_column], errors="coerce"
                ).to_numpy(),
            }
        )
        for lag, column in enumerate(feature_columns, start=1):
            part[column] = values.shift(lag).to_numpy()
        parts.append(part)
    return (
        pd.concat(parts, ignore_index=True).sort_values(
            ["stock_code", "target_date"]
        ).reset_index(drop=True),
        feature_columns,
    )


def iter_non_graph_autoregressive_predictions(
    target_panel: pd.DataFrame,
    *,
    market: str,
    target_codes: Sequence[str] | None = None,
    source_value_column: str | None = None,
    model_factories: Mapping[str, Callable[[], Any]] | None = None,
    skip_anchor_dates: Collection[pd.Timestamp] = (),
    config: M4Config = DEFAULT_M4_CONFIG,
) -> Iterator[AutoregressivePredictionResult]:
    """生成 F22 的 25 日非图、250 日训练、10 日更新十模型预测。"""
    feature_column = (
        source_value_column
        if source_value_column is not None
        else config.baseline.default_feature_set
    )
    local_config = replace(
        config,
        m3=replace(
            config.m3,
            prediction=replace(
                config.m3.prediction,
                source_value_column=feature_column,
            ),
        ),
    )
    panel = _market_panel(
        target_panel,
        target_codes=target_codes,
        config=local_config,
    )
    mapping = build_same_market_calendar_mapping(
        panel,
        market=market,
        config=local_config,
    )
    lagged, feature_columns = _build_autoregressive_feature_panel(
        panel,
        market_mapping=mapping,
        source_value_column=feature_column,
        target_value_column=local_config.m3.prediction.target_value_column,
        lag_count=local_config.baseline.autoregressive_lags,
        config=local_config,
    )
    blocks = build_update_blocks(
        mapping,
        prediction_start=local_config.m3.prediction.prediction_start,
        prediction_end=local_config.m3.prediction.prediction_end,
        update_days=local_config.m3.pipeline.returns.graph_update_days,
    )
    factories = (
        dict(model_factories)
        if model_factories is not None
        else build_base_model_factories(local_config.m3)
    )
    expected_base_models = local_config.m3.prediction.base_model_names
    if tuple(factories) != expected_base_models:
        raise ValueError("非图基线模型工厂名称或顺序与 B11 不一致")
    direction_name = local_config.baseline.non_graph_direction(market)
    value_columns = (*feature_columns, "target_value")
    skipped = {
        pd.Timestamp(value).normalize() for value in skip_anchor_dates
    }
    for block in blocks:
        if block.anchor_date in skipped:
            continue
        training, limits = winsorize_training_window(
            lagged,
            anchor_date=block.anchor_date,
            value_columns=value_columns,
            config=local_config.m3.pipeline,
            stock_column="stock_code",
            date_column="target_date",
        )
        prediction = lagged.loc[
            lagged["target_date"].isin(block.prediction_dates)
        ].copy()
        prediction = apply_stock_winsor_limits(
            prediction,
            limits,
            value_columns=value_columns,
            stock_column="stock_code",
        )
        prediction_parts: list[pd.DataFrame] = []
        training_audits: list[dict[str, Any]] = []
        model_audits: list[pd.DataFrame] = []
        eligibility_parts: list[pd.DataFrame] = []
        stock_codes = tuple(panel["stock_code"].drop_duplicates().astype(str))
        for target_code in stock_codes:
            stock_training = training.loc[
                training["stock_code"].eq(target_code)
            ].copy()
            stock_prediction = prediction.loc[
                prediction["stock_code"].eq(target_code)
            ].copy()
            training_numeric = (
                stock_training.loc[:, [*feature_columns, "target_value"]]
                .apply(pd.to_numeric, errors="coerce")
                .replace([np.inf, -np.inf], np.nan)
            )
            complete_case_nobs = int(training_numeric.dropna().shape[0])
            min_required_nobs = len(feature_columns) + 1
            predictor_numeric = (
                stock_prediction.loc[:, list(feature_columns)]
                .apply(pd.to_numeric, errors="coerce")
                .replace([np.inf, -np.inf], np.nan)
            )
            predictor_complete = predictor_numeric.notna().all(axis=1)
            actual_return_available = np.isfinite(
                pd.to_numeric(
                    stock_prediction["actual_return"], errors="coerce"
                ).to_numpy(dtype=np.float64, na_value=np.nan)
            )
            historical_liquidity_available = np.isfinite(
                pd.to_numeric(
                    stock_prediction["historical_liquidity"],
                    errors="coerce",
                ).to_numpy(dtype=np.float64, na_value=np.nan)
            )
            eligibility = pd.DataFrame(
                {
                    "direction": direction_name,
                    "prediction_date": pd.to_datetime(
                        stock_prediction["target_date"], errors="raise"
                    ).dt.normalize(),
                    "snapshot_date": block.anchor_date,
                    "target_code": target_code,
                    "graph_has_in_edges": pd.NA,
                    "feature_count": len(feature_columns),
                    "complete_case_nobs": complete_case_nobs,
                    "min_required_nobs": min_required_nobs,
                    "predictor_complete": predictor_complete,
                    "actual_return_available": actual_return_available,
                    "historical_liquidity_available": (
                        historical_liquidity_available
                    ),
                }
            )
            decision = derive_eligibility_decision(
                eligibility,
                context="非图动态资格生产",
            )
            eligibility["eligibility_status"] = decision[
                "expected_eligibility_status"
            ]
            eligibility["exclusion_reason"] = decision[
                "expected_exclusion_reason"
            ]
            eligibility_parts.append(eligibility)
            regression = fit_regression_model_batch(
                stock_training,
                stock_prediction,
                feature_columns=feature_columns,
                target_column="target_value",
                model_factories=factories,
                prediction_key_columns=("target_date", "source_date"),
                training_date_column="target_date",
                prediction_date_column="target_date",
            )
            model_audit = regression.model_audit.copy()
            model_audit.insert(0, "target_code", target_code)
            model_audit.insert(0, "anchor_date", block.anchor_date)
            model_audit.insert(0, "direction", direction_name)
            model_audits.append(model_audit)
            statuses = tuple(model_audit["status"].astype(str))
            training_audits.append(
                {
                    "direction": direction_name,
                    "anchor_date": block.anchor_date,
                    "target_code": target_code,
                    "feature_count": len(feature_columns),
                    "training_input_rows": len(stock_training),
                    "prediction_input_rows": len(stock_prediction),
                    "fitted_model_count": sum(
                        status == "fitted" for status in statuses
                    ),
                    "failed_or_skipped_model_count": sum(
                        status != "fitted" for status in statuses
                    ),
                    "fit_end_strictly_before_anchor": bool(
                        stock_training["target_date"].max()
                        < block.anchor_date
                    ),
                }
            )
            if regression.predictions.empty:
                continue
            base = regression.predictions.copy()
            base.insert(0, "target_code", target_code)
            base.insert(0, "anchor_date", block.anchor_date)
            base.insert(0, "direction", direction_name)
            predictions = build_ensemble_predictions(
                base,
                group_columns=PREDICTION_KEY_COLUMNS,
                config=local_config.m3,
            )
            actual = stock_prediction.loc[
                :, ["target_date", "actual_return"]
            ]
            predictions = predictions.merge(
                actual,
                on="target_date",
                how="left",
                validate="many_to_one",
            )
            prediction_parts.append(predictions)
        limits = limits.copy()
        limits.insert(0, "direction", direction_name)
        yield AutoregressivePredictionResult(
            predictions=(
                pd.concat(prediction_parts, ignore_index=True)
                if prediction_parts
                else pd.DataFrame(
                    columns=[
                        *PREDICTION_KEY_COLUMNS,
                        "model",
                        "prediction",
                        "actual_return",
                    ]
                )
            ),
            training_audit=pd.DataFrame(training_audits),
            model_audit=(
                pd.concat(model_audits, ignore_index=True)
                if model_audits
                else pd.DataFrame()
            ),
            winsor_limits=limits,
            eligibility_audit=_canonical_frame(
                (
                    pd.concat(eligibility_parts, ignore_index=True)
                    if eligibility_parts
                    else pd.DataFrame()
                ),
                ELIGIBILITY_AUDIT_SCHEMA,
                context="非图动态可预测资格审计表",
            ),
        )


def collect_autoregressive_prediction_tables(
    results: Iterable[AutoregressivePredictionResult],
) -> AutoregressivePredictionTables:
    """合并流式非图结果，保留 m5/main 正式落盘所需四张表。"""
    materialized = list(results)

    def concatenate(attribute: str) -> pd.DataFrame:
        frames = [
            getattr(result, attribute)
            for result in materialized
            if not getattr(result, attribute).empty
        ]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    return AutoregressivePredictionTables(
        predictions=concatenate("predictions"),
        training_audit=concatenate("training_audit"),
        model_audit=concatenate("model_audit"),
        winsor_limits=concatenate("winsor_limits"),
        eligibility_audit=concatenate("eligibility_audit"),
    )
