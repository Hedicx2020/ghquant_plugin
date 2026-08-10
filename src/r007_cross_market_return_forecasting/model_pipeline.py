"""r007 m3：逐目标、逐锚点的十模型滚动样本外预测编排。

图与变维特征集合完全消费 m2 当前接口；本模块不重算图、不填补缺失，
也不写 ``output/results``。正式运行方可逐快照消费返回值并落盘。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from common.ml_pipeline import (
    extract_estimator_feature_values,
    fit_regression_model_batch,
)

from .config import DEFAULT_M3_CONFIG, M3Config
from .graph_pipeline import (
    GraphSnapshot,
    TargetFeatureMatrices,
    iter_bidirectional_rolling_graphs,
    materialize_target_feature_batch,
    prepare_target_feature_matrices,
)
from .strategy import (
    build_base_model_factories,
    build_ensemble_predictions,
)


PREDICTION_KEY_COLUMNS = (
    "direction",
    "anchor_date",
    "target_code",
    "target_date",
    "source_date",
)
PREDICTION_SCHEMA = (
    ("direction", "string"),
    ("anchor_date", "datetime64[ns]"),
    ("target_code", "string"),
    ("target_date", "datetime64[ns]"),
    ("source_date", "datetime64[ns]"),
    ("model", "string"),
    ("prediction", "float64"),
    ("actual_return", "float64"),
)
FEATURE_VALUE_SCHEMA = (
    ("direction", "string"),
    ("anchor_date", "datetime64[ns]"),
    ("target_code", "string"),
    ("model", "string"),
    ("feature", "string"),
    ("value_kind", "string"),
    ("value", "float64"),
    ("absolute_value", "float64"),
    ("absolute_rank", "int64"),
    ("feature_column", "string"),
    ("source_code", "string"),
)
MODEL_AUDIT_SCHEMA = (
    ("direction", "string"),
    ("anchor_date", "datetime64[ns]"),
    ("target_code", "string"),
    ("model", "string"),
    ("feature_count", "int64"),
    ("training_input_rows", "int64"),
    ("training_complete_rows", "int64"),
    ("training_dropped_rows", "int64"),
    ("required_training_rows", "int64"),
    ("training_fit_start", "datetime64[ns]"),
    ("training_fit_end", "datetime64[ns]"),
    ("prediction_input_rows", "int64"),
    ("prediction_complete_rows", "int64"),
    ("prediction_missing_rows", "int64"),
    ("prediction_start", "datetime64[ns]"),
    ("prediction_end", "datetime64[ns]"),
    ("fit_end_strictly_before_prediction", "boolean"),
    ("estimator_class", "string"),
    ("status", "string"),
    ("error_type", "string"),
    ("error_message", "string"),
    ("transaction_status", "string"),
    ("failed_models", "string"),
)
TRAINING_AUDIT_SCHEMA = (
    ("direction", "string"),
    ("anchor_date", "datetime64[ns]"),
    ("target_code", "string"),
    ("feature_count", "int64"),
    ("no_inbound_target", "boolean"),
    ("training_input_rows", "int64"),
    ("training_complete_rows", "int64"),
    ("training_dropped_rows", "int64"),
    ("prediction_rows", "int64"),
    ("prediction_complete_rows", "int64"),
    ("prediction_missing_rows", "int64"),
    ("feature_signature", "string"),
    ("training_fit_start", "datetime64[ns]"),
    ("training_fit_end", "datetime64[ns]"),
    ("fit_end_strictly_before_anchor", "boolean"),
    ("training_status", "string"),
)
ELIGIBILITY_AUDIT_SCHEMA = (
    ("direction", "string"),
    ("prediction_date", "datetime64[ns]"),
    ("snapshot_date", "datetime64[ns]"),
    ("target_code", "string"),
    ("graph_has_in_edges", "boolean"),
    ("feature_count", "int64"),
    ("complete_case_nobs", "int64"),
    ("min_required_nobs", "int64"),
    ("predictor_complete", "boolean"),
    ("actual_return_available", "boolean"),
    ("historical_liquidity_available", "boolean"),
    ("eligibility_status", "string"),
    ("exclusion_reason", "string"),
)


@dataclass
class SnapshotPredictionResult:
    """一个图快照对应的 m3 预测、训练审计与模型解释值。"""

    predictions: pd.DataFrame
    training_audit: pd.DataFrame
    model_audit: pd.DataFrame
    feature_values: pd.DataFrame
    eligibility_audit: pd.DataFrame


class EligibilityDecisionError(ValueError):
    """资格落盘值与原始字段重算结果矛盾，并保留逐键审计。"""

    def __init__(self, message: str, audit: pd.DataFrame) -> None:
        super().__init__(message)
        self.audit = audit.reset_index(drop=True).copy()


def _canonical_frame(
    frame: pd.DataFrame,
    schema: tuple[tuple[str, str], ...],
    *,
    context: str,
) -> pd.DataFrame:
    """按固定列顺序和 dtype 规范化高层结果，空表也保留完整合同。"""
    columns = [column for column, _ in schema]
    unexpected = sorted(set(frame.columns) - set(columns))
    if unexpected:
        raise ValueError(f"{context} 含未登记字段: {unexpected}")
    result = frame.reindex(columns=columns).copy()
    for column, dtype in schema:
        if dtype == "datetime64[ns]":
            result[column] = pd.to_datetime(
                result[column],
                errors="raise",
            ).astype(dtype)
        elif dtype in {"float64", "int64"}:
            result[column] = pd.to_numeric(
                result[column],
                errors="raise",
            ).astype(dtype)
        else:
            result[column] = result[column].astype(dtype)
    return result


def _feature_signature(feature_columns: tuple[str, ...]) -> str:
    """为目标/锚点固定特征列生成顺序敏感签名。"""
    payload = "\x1f".join(feature_columns).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _actual_return_frame(
    target_panel: pd.DataFrame,
    *,
    target_value_column: str,
    prediction_dates: tuple[pd.Timestamp, ...],
) -> pd.DataFrame:
    required = {"stock_code", "date", target_value_column}
    missing = sorted(required - set(target_panel.columns))
    if missing:
        raise KeyError(f"目标收益面板缺少字段: {missing}")
    actual = target_panel.loc[
        pd.to_datetime(target_panel["date"], errors="raise")
        .dt.normalize()
        .isin(prediction_dates),
        ["stock_code", "date", target_value_column],
    ].copy()
    actual["stock_code"] = actual["stock_code"].astype("string")
    actual["date"] = pd.to_datetime(actual["date"], errors="raise").dt.normalize()
    if actual.duplicated(["stock_code", "date"]).any():
        raise ValueError("目标收益面板存在重复 stock_code/date 键")
    return actual.rename(
        columns={
            "stock_code": "target_code",
            "date": "target_date",
            target_value_column: "actual_return",
        }
    )


def _required_observation_frame(
    target_panel: pd.DataFrame,
    *,
    target_value_column: str,
    liquidity_column: str,
    prediction_dates: tuple[pd.Timestamp, ...],
) -> pd.DataFrame:
    """构造资格判定所需的目标收益与历史流动性，不消费模型输出。"""
    required = {"stock_code", "date", target_value_column, liquidity_column}
    missing = sorted(required - set(target_panel.columns))
    if missing:
        raise KeyError(f"动态可预测资格面板缺少字段: {missing}")
    frame = target_panel.loc[
        pd.to_datetime(target_panel["date"], errors="raise")
        .dt.normalize()
        .isin(prediction_dates),
        ["stock_code", "date", target_value_column, liquidity_column],
    ].copy()
    frame["stock_code"] = frame["stock_code"].astype("string")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    if frame.duplicated(["stock_code", "date"]).any():
        raise ValueError("动态可预测资格面板存在重复 stock_code/date 键")
    return frame.rename(
        columns={
            "stock_code": "target_code",
            "date": "prediction_date",
            target_value_column: "_required_actual_return",
            liquidity_column: "_required_historical_liquidity",
        }
    )


def derive_eligibility_decision(
    frame: pd.DataFrame,
    *,
    context: str,
) -> pd.DataFrame:
    """由原始资格字段按固定优先级重算唯一状态与排除原因。

    优先级固定为：无入边 → complete-case 不足 → 必要观测缺失 →
    动态可预测。生产端与 M4/SA3 消费端共同调用，避免字符串口径漂移。
    """
    required = {
        "graph_has_in_edges",
        "feature_count",
        "complete_case_nobs",
        "min_required_nobs",
        "predictor_complete",
        "actual_return_available",
        "historical_liquidity_available",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KeyError(f"{context} 缺少资格原始字段: {missing}")
    feature_count = pd.to_numeric(
        frame["feature_count"], errors="raise"
    ).astype("int64")
    complete_case_nobs = pd.to_numeric(
        frame["complete_case_nobs"], errors="raise"
    ).astype("int64")
    min_required_nobs = pd.to_numeric(
        frame["min_required_nobs"], errors="raise"
    ).astype("int64")
    if (
        feature_count.lt(0).any()
        or complete_case_nobs.lt(0).any()
        or min_required_nobs.lt(0).any()
    ):
        raise ValueError(f"{context} 的样本数或特征数不得为负")
    expected_minimum = feature_count.add(1).where(
        feature_count.gt(0),
        0,
    )
    if not min_required_nobs.eq(expected_minimum).all():
        raise ValueError(f"{context} 的 min_required_nobs 与特征数矛盾")

    graph_flag = frame["graph_has_in_edges"].astype("boolean")
    graph_flag_present = graph_flag.notna()
    if not graph_flag.loc[graph_flag_present].eq(
        feature_count.loc[graph_flag_present].gt(0)
    ).all():
        raise ValueError(f"{context} 的 graph_has_in_edges 与特征数矛盾")

    boolean_columns = (
        "predictor_complete",
        "actual_return_available",
        "historical_liquidity_available",
    )
    flags = frame.loc[:, list(boolean_columns)].astype("boolean")
    if flags.isna().any().any():
        raise ValueError(f"{context} 的必要观测可得性标志不得为空")
    no_in_edges = feature_count.eq(0)
    complete_case_insufficient = (
        ~no_in_edges & complete_case_nobs.lt(min_required_nobs)
    )
    required_observation_missing = (
        ~no_in_edges
        & ~complete_case_insufficient
        & ~flags.all(axis=1)
    )
    expected_reason = np.select(
        [
            no_in_edges,
            complete_case_insufficient,
            required_observation_missing,
        ],
        [
            "no_in_edges",
            "complete_case_insufficient",
            "required_observation_missing",
        ],
        default="",
    )
    return pd.DataFrame(
        {
            "expected_eligibility_status": np.where(
                pd.Series(expected_reason, index=frame.index).eq(""),
                "predictable",
                "legally_excluded",
            ),
            "expected_exclusion_reason": pd.Series(
                expected_reason,
                index=frame.index,
                dtype="string",
            ),
        },
        index=frame.index,
    )


def validate_eligibility_audit(
    frame: pd.DataFrame,
    *,
    context: str,
) -> pd.DataFrame:
    """重算并严格核对落盘状态/原因，供 M4 与 SA3 共用。"""
    missing = sorted(
        {"eligibility_status", "exclusion_reason"} - set(frame.columns)
    )
    if missing:
        raise KeyError(f"{context} 缺少资格结论字段: {missing}")
    decision = derive_eligibility_decision(frame, context=context)
    actual_status = frame["eligibility_status"].astype(str)
    actual_reason = frame["exclusion_reason"].fillna("").astype(str)
    status_matches = actual_status.eq(
        decision["expected_eligibility_status"].astype(str)
    )
    reason_matches = actual_reason.eq(
        decision["expected_exclusion_reason"].fillna("").astype(str)
    )
    audit = frame.copy()
    audit["expected_eligibility_status"] = decision[
        "expected_eligibility_status"
    ]
    audit["expected_exclusion_reason"] = decision[
        "expected_exclusion_reason"
    ]
    audit["eligibility_status_matches_recomputed"] = status_matches
    audit["exclusion_reason_matches_recomputed"] = reason_matches
    mismatch = ~(status_matches & reason_matches)
    if mismatch.any():
        raise EligibilityDecisionError(
            f"{context} 的落盘状态/原因与原始字段重算结果矛盾",
            audit.loc[mismatch],
        )
    return audit


def _graph_target_eligibility(
    snapshot: GraphSnapshot,
    *,
    target_code: str,
    feature_columns: tuple[str, ...],
    training_frame: pd.DataFrame,
    prediction_frame: pd.DataFrame,
    required_observations: pd.DataFrame,
    target_column: str,
) -> pd.DataFrame:
    """独立于估计器输出，逐机会判定 AS2/AS14 动态可预测资格。"""
    feature_count = len(feature_columns)
    min_required_nobs = feature_count + 1 if feature_count else 0
    if feature_count:
        complete_case_nobs = int(
            training_frame.loc[:, [*feature_columns, target_column]]
            .apply(pd.to_numeric, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .shape[0]
        )
    else:
        complete_case_nobs = 0

    opportunities = pd.DataFrame(
        {
            "prediction_date": pd.DatetimeIndex(
                snapshot.prediction_dates
            ).normalize()
        }
    )
    if feature_count and not prediction_frame.empty:
        predictor_complete = prediction_frame.loc[
            :, ["target_date", "predictor_complete"]
        ].rename(columns={"target_date": "prediction_date"})
        predictor_complete["prediction_date"] = pd.to_datetime(
            predictor_complete["prediction_date"], errors="raise"
        ).dt.normalize()
        if predictor_complete.duplicated("prediction_date").any():
            raise ValueError("图模型资格审计存在重复目标预测日")
        opportunities = opportunities.merge(
            predictor_complete,
            on="prediction_date",
            how="left",
            validate="one_to_one",
        )
    else:
        opportunities["predictor_complete"] = False
    target_required = required_observations.loc[
        required_observations["target_code"].astype(str).eq(target_code)
    ].copy()
    opportunities = opportunities.merge(
        target_required.drop(columns="target_code"),
        on="prediction_date",
        how="left",
        validate="one_to_one",
    )
    predictor_available = opportunities["predictor_complete"].fillna(False)
    actual_return_available = np.isfinite(
        pd.to_numeric(
            opportunities["_required_actual_return"], errors="coerce"
        ).to_numpy(dtype=np.float64, na_value=np.nan)
    )
    historical_liquidity_available = np.isfinite(
        pd.to_numeric(
            opportunities["_required_historical_liquidity"],
            errors="coerce",
        ).to_numpy(dtype=np.float64, na_value=np.nan)
    )
    opportunities["direction"] = snapshot.direction
    opportunities["snapshot_date"] = snapshot.anchor_date
    opportunities["target_code"] = target_code
    opportunities["graph_has_in_edges"] = feature_count > 0
    opportunities["feature_count"] = feature_count
    opportunities["complete_case_nobs"] = complete_case_nobs
    opportunities["min_required_nobs"] = min_required_nobs
    opportunities["predictor_complete"] = predictor_available.astype(
        "boolean"
    )
    opportunities["actual_return_available"] = actual_return_available
    opportunities["historical_liquidity_available"] = (
        historical_liquidity_available
    )
    decision = derive_eligibility_decision(
        opportunities,
        context="图模型动态资格生产",
    )
    opportunities["eligibility_status"] = decision[
        "expected_eligibility_status"
    ]
    opportunities["exclusion_reason"] = decision[
        "expected_exclusion_reason"
    ]
    return opportunities.loc[
        :, [column for column, _ in ELIGIBILITY_AUDIT_SCHEMA]
    ]


def _skipped_model_audit(
    *,
    snapshot: GraphSnapshot,
    target_code: str,
    feature_count: int,
    status: str,
    model_names: tuple[str, ...],
    training_input_rows: int,
    training_complete_rows: int,
    prediction_input_rows: int,
    prediction_complete_rows: int,
) -> pd.DataFrame:
    required_training_rows = feature_count + 1 if feature_count else 0
    return pd.DataFrame(
        [
            {
                "direction": snapshot.direction,
                "anchor_date": snapshot.anchor_date,
                "target_code": target_code,
                "model": model_name,
                "feature_count": feature_count,
                "training_input_rows": training_input_rows,
                "training_complete_rows": training_complete_rows,
                "training_dropped_rows": (
                    training_input_rows - training_complete_rows
                ),
                "required_training_rows": required_training_rows,
                "training_fit_start": pd.NaT,
                "training_fit_end": pd.NaT,
                "prediction_input_rows": prediction_input_rows,
                "prediction_complete_rows": prediction_complete_rows,
                "prediction_missing_rows": (
                    prediction_input_rows - prediction_complete_rows
                ),
                "prediction_start": (
                    min(snapshot.prediction_dates)
                    if snapshot.prediction_dates
                    else pd.NaT
                ),
                "prediction_end": (
                    max(snapshot.prediction_dates)
                    if snapshot.prediction_dates
                    else pd.NaT
                ),
                "fit_end_strictly_before_prediction": pd.NA,
                "estimator_class": pd.NA,
                "status": status,
                "error_type": pd.NA,
                "error_message": pd.NA,
                "transaction_status": status,
                "failed_models": pd.NA,
            }
            for model_name in model_names
        ]
    )


def predict_graph_snapshot(
    snapshot: GraphSnapshot,
    source_panel: pd.DataFrame,
    target_panel: pd.DataFrame,
    *,
    model_factories: Mapping[str, Any] | None = None,
    prepared_feature_matrices: TargetFeatureMatrices | None = None,
    collect_feature_values: bool = True,
    config: M3Config = DEFAULT_M3_CONFIG,
) -> SnapshotPredictionResult:
    """对单个 m2 图快照逐目标训练八模型并追加两种严格集成。

    每个目标股票在该锚点只使用 m2 冻结的当期特征集合；训练和预测列
    由同一个 ``TargetFeatureBatch.feature_columns`` 驱动。无入边、
    complete-case 样本不足或预测特征缺失均只跳过对应目标/锚点并落审计。
    """
    factories = (
        dict(model_factories)
        if model_factories is not None
        else build_base_model_factories(config)
    )
    expected_models = config.prediction.base_model_names
    if tuple(factories) != expected_models:
        raise ValueError("模型工厂名称或顺序与 B11 不一致")

    target_actual = _actual_return_frame(
        target_panel,
        target_value_column=config.prediction.target_value_column,
        prediction_dates=snapshot.prediction_dates,
    )
    required_observations = _required_observation_frame(
        target_panel,
        target_value_column=config.prediction.target_value_column,
        liquidity_column=config.pipeline.returns.liquidity_median_column,
        prediction_dates=snapshot.prediction_dates,
    )
    feature_matrices = (
        prepared_feature_matrices
        if prepared_feature_matrices is not None
        else prepare_target_feature_matrices(
            source_panel,
            target_panel,
            source_value_column=config.prediction.source_value_column,
            target_value_column=config.prediction.target_value_column,
        )
    )
    prediction_parts: list[pd.DataFrame] = []
    training_audits: list[pd.DataFrame] = []
    model_audits: list[pd.DataFrame] = []
    feature_value_parts: list[pd.DataFrame] = []
    eligibility_parts: list[pd.DataFrame] = []
    target_codes = (
        snapshot.feature_mapping["target_code"]
        .astype("string")
        .drop_duplicates()
        .tolist()
    )

    for target_code_value in target_codes:
        target_code = str(target_code_value)
        batch = materialize_target_feature_batch(
            snapshot,
            source_panel,
            target_panel,
            target_code=target_code,
            source_value_column=config.prediction.source_value_column,
            target_value_column=config.prediction.target_value_column,
            prepared_matrices=feature_matrices,
            config=config.pipeline,
        )
        batch_audit = batch.audit.copy()
        batch_audit["feature_signature"] = _feature_signature(
            batch.feature_columns
        )
        training_start = (
            pd.to_datetime(batch.training_frame["target_date"]).min()
            if not batch.training_frame.empty
            else pd.NaT
        )
        training_end = (
            pd.to_datetime(batch.training_frame["target_date"]).max()
            if not batch.training_frame.empty
            else pd.NaT
        )
        batch_audit["training_fit_start"] = training_start
        batch_audit["training_fit_end"] = training_end
        batch_audit["fit_end_strictly_before_anchor"] = bool(
            pd.isna(training_end) or training_end < snapshot.anchor_date
        )
        eligibility_parts.append(
            _graph_target_eligibility(
                snapshot,
                target_code=target_code,
                feature_columns=batch.feature_columns,
                training_frame=batch.training_frame,
                prediction_frame=batch.prediction_frame,
                required_observations=required_observations,
                target_column=config.prediction.target_column,
            )
        )
        if not batch.feature_columns:
            batch_audit["training_status"] = "skipped_no_inbound_edges"
            training_audits.append(batch_audit)
            model_audits.append(
                _skipped_model_audit(
                    snapshot=snapshot,
                    target_code=target_code,
                    feature_count=0,
                    status="skipped_no_inbound_edges",
                    model_names=expected_models,
                    training_input_rows=int(
                        batch_audit.iloc[0]["training_input_rows"]
                    ),
                    training_complete_rows=0,
                    prediction_input_rows=int(
                        batch_audit.iloc[0]["prediction_rows"]
                    ),
                    prediction_complete_rows=0,
                )
            )
            continue

        regression = fit_regression_model_batch(
            batch.training_frame,
            batch.prediction_frame,
            feature_columns=batch.feature_columns,
            target_column=config.prediction.target_column,
            model_factories=factories,
            prediction_key_columns=("target_date", "source_date"),
            training_date_column="target_date",
            prediction_date_column="target_date",
        )
        model_audit = regression.model_audit.copy()
        model_audit.insert(0, "target_code", target_code)
        model_audit.insert(0, "anchor_date", snapshot.anchor_date)
        model_audit.insert(0, "direction", snapshot.direction)
        model_audits.append(model_audit)
        statuses = set(model_audit["status"].astype(str))
        if statuses == {"fitted"}:
            batch_audit["training_status"] = "fitted_all_base_models"
        elif len(statuses) == 1:
            batch_audit["training_status"] = next(iter(statuses))
        else:
            batch_audit["training_status"] = "partial_model_failure"
        training_audits.append(batch_audit)

        all_base_models_fitted = (
            statuses == {"fitted"}
            and len(regression.fitted_models) == len(expected_models)
        )
        if not all_base_models_fitted:
            if not regression.predictions.empty or regression.fitted_models:
                raise AssertionError("基础模型事务失败后仍泄露预测或模型对象")
            continue
        if regression.predictions.empty:
            continue
        base_predictions = regression.predictions.copy()
        base_predictions.insert(0, "target_code", target_code)
        base_predictions.insert(0, "anchor_date", snapshot.anchor_date)
        base_predictions.insert(0, "direction", snapshot.direction)
        predictions = build_ensemble_predictions(
            base_predictions,
            group_columns=PREDICTION_KEY_COLUMNS,
            config=config,
        )
        ensemble_names = {
            config.prediction.ensemble_average_name,
            config.prediction.ensemble_median_name,
        }
        ensemble_groups = predictions.loc[
            predictions["model"].isin(ensemble_names)
        ].groupby(list(PREDICTION_KEY_COLUMNS), dropna=False, observed=True)
        if len(ensemble_groups):
            ensemble_counts = ensemble_groups["model"].nunique()
            if not ensemble_counts.eq(2).all():
                raise AssertionError("同日同股集成预测未同时包含均值和中位数")
        prediction_parts.append(predictions)

        if collect_feature_values:
            feature_lookup = batch.feature_lookup.copy()
            for model_name, estimator in regression.fitted_models.items():
                values = extract_estimator_feature_values(
                    estimator,
                    batch.feature_columns,
                    model_name=model_name,
                )
                if values.empty:
                    continue
                values = values.merge(
                    feature_lookup,
                    left_on="feature",
                    right_on="feature_column",
                    how="left",
                    validate="one_to_one",
                )
                values.insert(0, "target_code", target_code)
                values.insert(0, "anchor_date", snapshot.anchor_date)
                values.insert(0, "direction", snapshot.direction)
                feature_value_parts.append(values)

    predictions = (
        pd.concat(prediction_parts, ignore_index=True)
        if prediction_parts
        else _canonical_frame(
            pd.DataFrame(),
            PREDICTION_SCHEMA,
            context="m3 预测表",
        )
    )
    if not predictions.empty:
        predictions = predictions.merge(
            target_actual,
            on=["target_code", "target_date"],
            how="left",
            validate="many_to_one",
        )
        predictions["prediction"] = pd.to_numeric(
            predictions["prediction"],
            errors="raise",
        )
        predictions = predictions.sort_values(
            ["target_date", "target_code", "model"]
        ).reset_index(drop=True)
    predictions = _canonical_frame(
        predictions,
        PREDICTION_SCHEMA,
        context="m3 预测表",
    )
    training_audit = _canonical_frame(
        (
            pd.concat(training_audits, ignore_index=True)
            if training_audits
            else pd.DataFrame()
        ),
        TRAINING_AUDIT_SCHEMA,
        context="m3 训练审计表",
    )
    model_audit = _canonical_frame(
        (
            pd.concat(model_audits, ignore_index=True)
            if model_audits
            else pd.DataFrame()
        ),
        MODEL_AUDIT_SCHEMA,
        context="m3 模型审计表",
    )
    feature_values = _canonical_frame(
        (
            pd.concat(feature_value_parts, ignore_index=True)
            if feature_value_parts
            else pd.DataFrame()
        ),
        FEATURE_VALUE_SCHEMA,
        context="m3 模型解释值表",
    )
    eligibility_audit = _canonical_frame(
        (
            pd.concat(eligibility_parts, ignore_index=True)
            if eligibility_parts
            else pd.DataFrame()
        ),
        ELIGIBILITY_AUDIT_SCHEMA,
        context="m3 动态可预测资格审计表",
    )
    if eligibility_audit.duplicated(
        ["direction", "prediction_date", "snapshot_date", "target_code"]
    ).any():
        raise AssertionError("m3 动态可预测资格审计存在重复机会键")
    return SnapshotPredictionResult(
        predictions=predictions,
        training_audit=training_audit,
        model_audit=model_audit,
        feature_values=feature_values,
        eligibility_audit=eligibility_audit,
    )


def iter_snapshot_model_predictions(
    snapshots: Iterable[GraphSnapshot],
    *,
    market_panels: Mapping[str, pd.DataFrame],
    config: M3Config = DEFAULT_M3_CONFIG,
) -> Iterator[SnapshotPredictionResult]:
    """消费既有 m2 快照并逐块产出，避免全样本模型对象常驻内存。"""
    factories = build_base_model_factories(config)
    matrix_cache: dict[tuple[str, str], TargetFeatureMatrices] = {}
    for snapshot in snapshots:
        try:
            source_panel = market_panels[snapshot.source_market]
            target_panel = market_panels[snapshot.target_market]
        except KeyError as exc:
            raise KeyError(f"缺少市场收益面板: {exc.args[0]}") from exc
        matrix_key = (snapshot.source_market, snapshot.target_market)
        if matrix_key not in matrix_cache:
            matrix_cache[matrix_key] = prepare_target_feature_matrices(
                source_panel,
                target_panel,
                source_value_column=config.prediction.source_value_column,
                target_value_column=config.prediction.target_value_column,
            )
        yield predict_graph_snapshot(
            snapshot,
            source_panel,
            target_panel,
            model_factories=factories,
            prepared_feature_matrices=matrix_cache[matrix_key],
            config=config,
        )


def iter_bidirectional_model_predictions(
    us_panel: pd.DataFrame,
    cn_panel: pd.DataFrame,
    calendar_mapping: pd.DataFrame,
    *,
    config: M3Config = DEFAULT_M3_CONFIG,
) -> Iterator[SnapshotPredictionResult]:
    """流式完成 B7 期间双方向图快照和十模型样本外预测。"""
    snapshots = iter_bidirectional_rolling_graphs(
        us_panel,
        cn_panel,
        calendar_mapping,
        prediction_start=config.prediction.prediction_start,
        prediction_end=config.prediction.prediction_end,
        source_value_column=config.prediction.source_value_column,
        target_value_column=config.prediction.target_value_column,
        config=config.pipeline,
    )
    yield from iter_snapshot_model_predictions(
        snapshots,
        market_panels={"US": us_panel, "CN": cn_panel},
        config=config,
    )


def summarize_prediction_quality(predictions: pd.DataFrame) -> pd.DataFrame:
    """按方向和模型汇总预测—实际配对统计，不写正式结果文件。"""
    required = {"direction", "model", "prediction", "actual_return"}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise KeyError(f"预测面板缺少质量统计字段: {missing}")
    working = predictions.loc[
        np.isfinite(
            predictions[["prediction", "actual_return"]]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=np.float64, na_value=np.nan)
        ).all(axis=1)
    ].copy()
    if working.empty:
        return pd.DataFrame(
            columns=[
                "direction",
                "model",
                "observation_count",
                "mae",
                "rmse",
                "pearson_correlation",
                "spearman_correlation",
            ]
        )

    def summarize(group: pd.DataFrame) -> pd.Series:
        prediction = pd.to_numeric(group["prediction"], errors="raise")
        actual = pd.to_numeric(group["actual_return"], errors="raise")
        error = prediction - actual
        return pd.Series(
            {
                "observation_count": len(group),
                "mae": float(error.abs().mean()),
                "rmse": float(np.sqrt(np.mean(np.square(error)))),
                "pearson_correlation": float(prediction.corr(actual)),
                "spearman_correlation": float(
                    prediction.corr(actual, method="spearman")
                ),
            }
        )

    return (
        working.groupby(["direction", "model"], observed=True)
        .apply(summarize, include_groups=False)
        .reset_index()
    )
