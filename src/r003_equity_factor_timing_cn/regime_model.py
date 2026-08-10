"""m2 第一阶段市场风险状态识别与滚动预测。

每个预测月只使用该月之前的 84 个完整目标月：K-Means 在这些月的
三个月回撤上重估三类状态，分类器使用 ``X_t -> regime_{t+1}`` 样本。
缺失值处理、标准化和过采样均只在相应训练集内拟合，验证月和预测月
从不参与这些步骤。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Final, Sequence

import numpy as np
import pandas as pd
import sklearn
from sklearn.base import ClassifierMixin
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_score,
    recall_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from .config import ChinaFactorTimingConfig

try:
    from imblearn.over_sampling import SMOTE as ImbalancedLearnSMOTE
except ImportError:  # 当前项目未声明 imbalanced-learn，使用已登记的确定性近似。
    ImbalancedLearnSMOTE = None


REGIME_ORDER: Final[tuple[str, ...]] = ("Normal", "Correction", "Bear")
FEATURE_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "Equity Valuation": (
        "equity_ep_percentile",
        "equity_pb_percentile",
    ),
    "Financial Turbulence": ("financial_turbulence",),
    "Financial Conditions": (
        "financial_risk",
        "credit_conditions",
        "leverage_conditions",
    ),
    "Monetary Policy Expectation": (
        "monetary_policy_expectations",
        "short_rate_proxy",
        "short_rate_change",
    ),
}
MODEL_FEATURES: Final[tuple[str, ...]] = tuple(
    feature for features in FEATURE_GROUPS.values() for feature in features
)


@dataclass(frozen=True)
class RegimeModelSettings:
    """第一阶段集中参数；默认值均来自 plan/spec 或 AS38。"""

    train_window_months: int = 84
    n_clusters: int = 3
    elbow_k_min: int = 2
    elbow_k_max: int = 6
    kmeans_n_init: int = 20
    cv_splits: int = 5
    seed: int = 42
    smote_k_neighbors: int = 5
    rf_estimators: int = 500
    rf_max_depth: int = 4
    rf_min_samples_leaf: int = 3
    svc_c: float = 1.0
    logistic_c: float = 1.0
    logistic_max_iter: int = 2_000


@dataclass(frozen=True)
class RegimeClustering:
    """单个滚动窗的聚类器及稳定状态映射。"""

    model: KMeans
    cluster_to_regime: dict[int, str]
    centers: pd.DataFrame

    def predict(self, drawdown: pd.Series) -> pd.Series:
        """按已拟合中心给新回撤标注状态，不重估聚类器。"""
        numeric = pd.to_numeric(drawdown, errors="coerce")
        result = pd.Series(pd.NA, index=drawdown.index, dtype="string")
        valid = numeric.notna()
        if valid.any():
            cluster = self.model.predict(numeric.loc[valid].to_numpy(dtype=float).reshape(-1, 1))
            result.loc[valid] = pd.Series(cluster, index=numeric.loc[valid].index).map(
                self.cluster_to_regime
            )
        return result


@dataclass
class FittedStackingClassifier:
    """预处理器、三类一级模型与二级逻辑回归的组合。"""

    preprocessor: Pipeline
    base_models: tuple[ClassifierMixin, ...]
    meta_model: LogisticRegression | None
    constant_regime: str | None
    resampled_rows: int
    oversampling_method: str
    rf_feature_importance: np.ndarray
    meta_oof_rows: int
    meta_oof_total_rows: int
    meta_oof_coverage: float
    meta_oof_first_position: int | None

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        """按固定状态顺序返回三列概率。"""
        transformed = self.preprocessor.transform(features.loc[:, MODEL_FEATURES])
        if self.constant_regime is not None:
            probabilities = np.zeros((len(features), len(REGIME_ORDER)), dtype=float)
            probabilities[:, REGIME_ORDER.index(self.constant_regime)] = 1.0
            return probabilities
        meta_features = _base_probability_features(self.base_models, transformed)
        assert self.meta_model is not None
        return _aligned_probabilities(self.meta_model, meta_features)

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """返回固定状态名称。"""
        probability = self.predict_proba(features)
        return np.asarray(REGIME_ORDER, dtype=object)[probability.argmax(axis=1)]


@dataclass
class StageOneRegimeResult:
    """m2 后续阶段和报告层可直接消费的完整结果合同。"""

    rolling_predictions: pd.DataFrame
    regime_labels: pd.DataFrame
    fold_metrics: pd.DataFrame
    cv_predictions: pd.DataFrame
    confusion_matrix: pd.DataFrame
    regime_distribution: pd.DataFrame
    elbow_diagnostics: pd.DataFrame
    feature_importance: pd.DataFrame
    training_audit: pd.DataFrame
    parameter_hash: str


def _validate_settings(settings: RegimeModelSettings) -> None:
    if settings.train_window_months <= 0:
        raise ValueError("train_window_months 必须为正整数")
    if settings.n_clusters != len(REGIME_ORDER):
        raise ValueError("第一阶段必须固定为 Normal/Correction/Bear 三状态")
    if not 2 <= settings.elbow_k_min <= settings.n_clusters <= settings.elbow_k_max:
        raise ValueError("肘部法候选K必须覆盖固定选择K=3，且最小K不得小于2")
    if settings.cv_splits != 5:
        raise ValueError("spec B8/SA1 要求固定五折 TimeSeriesSplit")
    if settings.smote_k_neighbors <= 0:
        raise ValueError("smote_k_neighbors 必须为正整数")


def build_stage_one_features(monthly_features: pd.DataFrame) -> pd.DataFrame:
    """从 m1 月频公开面板提取四类中国特征组的底层变量。"""
    required = ("signal_date", "drawdown_3m", *MODEL_FEATURES)
    missing = [column for column in required if column not in monthly_features.columns]
    if missing:
        raise KeyError(f"m1 monthly_features 缺少第一阶段字段: {missing}")
    result = monthly_features.loc[:, required].copy()
    result["signal_date"] = pd.to_datetime(result["signal_date"]).dt.normalize()
    if result["signal_date"].duplicated().any():
        raise ValueError("monthly_features 存在重复 signal_date")
    result = result.sort_values("signal_date").reset_index(drop=True)
    periods = result["signal_date"].dt.to_period("M")
    if periods.duplicated().any():
        raise ValueError("monthly_features 同一月份存在多条记录")
    month_number = periods.astype("int64")
    if len(month_number) > 1 and not np.equal(np.diff(month_number), 1).all():
        raise ValueError("monthly_features 月份不连续，无法构造固定完整月窗口")
    result.loc[:, ("drawdown_3m", *MODEL_FEATURES)] = result.loc[
        :, ("drawdown_3m", *MODEL_FEATURES)
    ].apply(pd.to_numeric, errors="coerce")
    return result


def fit_market_regimes(
    drawdown: pd.Series,
    settings: RegimeModelSettings,
) -> RegimeClustering:
    """在单个历史窗内拟合 K=3，并按回撤中心从高到低稳定命名。"""
    _validate_settings(settings)
    values = pd.to_numeric(drawdown, errors="coerce")
    if len(values) != settings.train_window_months or values.isna().any():
        raise ValueError("K-Means 必须收到84个无缺失的完整历史回撤月")
    model = KMeans(
        n_clusters=settings.n_clusters,
        random_state=settings.seed,
        n_init=settings.kmeans_n_init,
    ).fit(values.to_numpy(dtype=float).reshape(-1, 1))
    centers = pd.Series(model.cluster_centers_.ravel(), index=np.arange(settings.n_clusters))
    ordered_clusters = centers.sort_values(ascending=False).index.tolist()
    mapping = dict(zip(ordered_clusters, REGIME_ORDER, strict=True))
    center_table = pd.DataFrame(
        {
            "cluster": centers.index.astype(int),
            "drawdown_center": centers.to_numpy(dtype=float),
        }
    )
    center_table["regime"] = center_table["cluster"].map(mapping)
    center_table["regime_order"] = center_table["regime"].map(
        {name: index for index, name in enumerate(REGIME_ORDER)}
    )
    center_table = center_table.sort_values("regime_order").drop(columns="regime_order")
    return RegimeClustering(model=model, cluster_to_regime=mapping, centers=center_table)


def calculate_elbow_diagnostics(
    drawdown: pd.Series,
    settings: RegimeModelSettings,
    *,
    prediction_date: pd.Timestamp,
) -> pd.DataFrame:
    """计算每个滚动训练窗 K=2..6 的 inertia，供肘部图直接消费。"""
    _validate_settings(settings)
    values = pd.to_numeric(drawdown, errors="coerce")
    if len(values) != settings.train_window_months or values.isna().any():
        raise ValueError("肘部诊断必须收到84个无缺失的完整历史回撤月")
    if not isinstance(drawdown.index, pd.DatetimeIndex):
        raise TypeError("肘部诊断drawdown必须以目标月DatetimeIndex索引")
    array = values.to_numpy(dtype=float).reshape(-1, 1)
    rows: list[dict[str, object]] = []
    previous_inertia: float | None = None
    for candidate_k in range(settings.elbow_k_min, settings.elbow_k_max + 1):
        model = KMeans(
            n_clusters=candidate_k,
            random_state=settings.seed,
            n_init=settings.kmeans_n_init,
        ).fit(array)
        inertia = float(model.inertia_)
        reduction = (
            np.nan
            if previous_inertia is None or previous_inertia == 0.0
            else (previous_inertia - inertia) / previous_inertia
        )
        rows.append(
            {
                "prediction_date": pd.Timestamp(prediction_date),
                "train_start": pd.to_datetime(drawdown.index).min(),
                "train_end": pd.to_datetime(drawdown.index).max(),
                "k": candidate_k,
                "inertia": inertia,
                "inertia_reduction_from_previous_k": reduction,
                "selected_k": candidate_k == settings.n_clusters,
            }
        )
        previous_inertia = inertia
    return pd.DataFrame(rows)


def _make_preprocessor() -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("standardizer", StandardScaler()),
        ]
    )


def _deterministic_neighbor_resample(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    seed: int,
    k_neighbors: int,
) -> tuple[np.ndarray, np.ndarray]:
    """以固定随机种子的类内近邻插值平衡训练集。"""
    rng = np.random.default_rng(seed)
    classes, counts = np.unique(labels, return_counts=True)
    target_count = int(counts.max())
    synthetic_features: list[np.ndarray] = [features]
    synthetic_labels: list[np.ndarray] = [labels]
    for class_name, class_count in zip(classes, counts, strict=True):
        needed = target_count - int(class_count)
        if needed <= 0:
            continue
        class_features = features[labels == class_name]
        if class_count == 1:
            generated = np.repeat(class_features, repeats=needed, axis=0)
        else:
            neighbors = min(k_neighbors + 1, int(class_count))
            model = NearestNeighbors(n_neighbors=neighbors).fit(class_features)
            neighbor_index = model.kneighbors(
                class_features,
                n_neighbors=neighbors,
                return_distance=False,
            )
            base_index = np.arange(needed, dtype=int) % int(class_count)
            candidate_columns = rng.integers(1, neighbors, size=needed)
            paired_index = neighbor_index[base_index, candidate_columns]
            alpha = rng.random(needed)[:, None]
            generated = class_features[base_index] + alpha * (
                class_features[paired_index] - class_features[base_index]
            )
        synthetic_features.append(generated)
        synthetic_labels.append(np.repeat(class_name, needed))
    return np.vstack(synthetic_features), np.concatenate(synthetic_labels)


def _resample_training_fold(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    settings: RegimeModelSettings,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, str]:
    """只对调用方明确传入的训练折执行 SMOTE 或其确定性近似。"""
    _, counts = np.unique(labels, return_counts=True)
    if len(counts) <= 1 or counts.min() == counts.max():
        return features, labels, "not_required"
    minimum_count = int(counts.min())
    if ImbalancedLearnSMOTE is not None and minimum_count > 1:
        neighbors = min(settings.smote_k_neighbors, minimum_count - 1)
        sampler = ImbalancedLearnSMOTE(random_state=seed, k_neighbors=neighbors)
        sampled_features, sampled_labels = sampler.fit_resample(features, labels)
        return sampled_features, sampled_labels, "imbalanced_learn_smote"
    sampled_features, sampled_labels = _deterministic_neighbor_resample(
        features,
        labels,
        seed=seed,
        k_neighbors=settings.smote_k_neighbors,
    )
    return sampled_features, sampled_labels, "deterministic_neighbor_interpolation"


def _make_base_models(
    settings: RegimeModelSettings,
    *,
    seed: int,
) -> tuple[ClassifierMixin, ...]:
    return (
        RandomForestClassifier(
            n_estimators=settings.rf_estimators,
            max_depth=settings.rf_max_depth,
            min_samples_leaf=settings.rf_min_samples_leaf,
            max_features="sqrt",
            class_weight="balanced",
            random_state=seed,
            n_jobs=1,
        ),
        SVC(
            C=settings.svc_c,
            probability=True,
            class_weight="balanced",
            random_state=seed,
        ),
        GaussianNB(),
    )


def _aligned_probabilities(model: ClassifierMixin, features: np.ndarray) -> np.ndarray:
    raw = model.predict_proba(features)
    aligned = np.zeros((len(features), len(REGIME_ORDER)), dtype=float)
    classes = [str(value) for value in model.classes_]
    for source_index, class_name in enumerate(classes):
        if class_name in REGIME_ORDER:
            aligned[:, REGIME_ORDER.index(class_name)] = raw[:, source_index]
    row_sum = aligned.sum(axis=1, keepdims=True)
    return np.divide(aligned, row_sum, out=np.zeros_like(aligned), where=row_sum > 0)


def _base_probability_features(
    models: Sequence[ClassifierMixin],
    features: np.ndarray,
) -> np.ndarray:
    return np.hstack([_aligned_probabilities(model, features) for model in models])


def _constant_base_probability_features(regime: str, row_count: int) -> np.ndarray:
    probabilities = np.zeros((row_count, len(REGIME_ORDER)), dtype=float)
    probabilities[:, REGIME_ORDER.index(regime)] = 1.0
    return np.hstack([probabilities for _ in range(3)])


def _fit_base_layer(
    features: pd.DataFrame,
    labels: pd.Series,
    settings: RegimeModelSettings,
    *,
    seed: int,
) -> tuple[
    Pipeline,
    tuple[ClassifierMixin, ...],
    str | None,
    int,
    str,
    np.ndarray,
]:
    """仅用给定训练子折拟合预处理、采样器和三个一级模型。"""
    preprocessor = _make_preprocessor()
    transformed = preprocessor.fit_transform(features.loc[:, MODEL_FEATURES])
    label_values = labels.astype(str).to_numpy()
    sampled_x, sampled_y, method = _resample_training_fold(
        transformed,
        label_values,
        settings=settings,
        seed=seed,
    )
    unique_labels = np.unique(sampled_y)
    if len(unique_labels) == 1:
        return (
            preprocessor,
            (),
            str(unique_labels[0]),
            len(sampled_y),
            method,
            np.zeros(len(MODEL_FEATURES), dtype=float),
        )
    base_models = _make_base_models(settings, seed=seed)
    for model in base_models:
        model.fit(sampled_x, sampled_y)
    importance = np.asarray(base_models[0].feature_importances_, dtype=float)
    return preprocessor, base_models, None, len(sampled_y), method, importance


def _predict_base_layer(
    preprocessor: Pipeline,
    models: Sequence[ClassifierMixin],
    constant_regime: str | None,
    features: pd.DataFrame,
) -> np.ndarray:
    """为未参与该一级模型拟合的行生成三模型概率元特征。"""
    if constant_regime is not None:
        return _constant_base_probability_features(constant_regime, len(features))
    transformed = preprocessor.transform(features.loc[:, MODEL_FEATURES])
    return _base_probability_features(models, transformed)


def fit_stacking_classifier(
    features: pd.DataFrame,
    labels: pd.Series,
    settings: RegimeModelSettings,
    *,
    seed_offset: int = 0,
) -> FittedStackingClassifier:
    """用严格时序OOF一级概率训练元学习器，再重训完整窗一级模型。"""
    _validate_settings(settings)
    if len(features) != len(labels) or len(features) <= settings.cv_splits:
        raise ValueError("Stacking训练特征与标签必须等长且足以执行五折时序OOF")
    features = features.reset_index(drop=True)
    labels = labels.astype("string").reset_index(drop=True)
    seed = settings.seed + seed_offset

    meta_width = len(REGIME_ORDER) * 3
    oof_meta = np.full((len(features), meta_width), np.nan, dtype=float)
    oof_mask = np.zeros(len(features), dtype=bool)
    splitter = TimeSeriesSplit(n_splits=settings.cv_splits)
    for inner_fold, (train_index, validation_index) in enumerate(
        splitter.split(features), start=1
    ):
        (
            inner_preprocessor,
            inner_models,
            inner_constant,
            _,
            _,
            _,
        ) = _fit_base_layer(
            features.iloc[train_index],
            labels.iloc[train_index],
            settings,
            seed=seed + inner_fold,
        )
        oof_meta[validation_index] = _predict_base_layer(
            inner_preprocessor,
            inner_models,
            inner_constant,
            features.iloc[validation_index],
        )
        oof_mask[validation_index] = True
    if not oof_mask.any() or np.isnan(oof_meta[oof_mask]).any():
        raise AssertionError("时序OOF元特征生成不完整")
    first_oof_position = int(np.flatnonzero(oof_mask)[0])
    if oof_mask[:first_oof_position].any() or not oof_mask[first_oof_position:].all():
        raise AssertionError("TimeSeriesSplit OOF必须排除无前史首段并连续覆盖后续样本")
    meta_labels = labels.loc[oof_mask].astype(str).to_numpy()
    unique_meta_labels = np.unique(meta_labels)
    if len(unique_meta_labels) == 1:
        meta_model = None
        meta_constant = str(unique_meta_labels[0])
    else:
        meta_model = LogisticRegression(
            C=settings.logistic_c,
            max_iter=settings.logistic_max_iter,
            class_weight="balanced",
            random_state=seed,
        ).fit(oof_meta[oof_mask], meta_labels)
        meta_constant = None

    (
        preprocessor,
        base_models,
        full_base_constant,
        resampled_rows,
        method,
        rf_importance,
    ) = _fit_base_layer(features, labels, settings, seed=seed)
    return FittedStackingClassifier(
        preprocessor=preprocessor,
        base_models=base_models,
        meta_model=meta_model,
        constant_regime=full_base_constant or meta_constant,
        resampled_rows=resampled_rows,
        oversampling_method=method,
        rf_feature_importance=rf_importance,
        meta_oof_rows=int(oof_mask.sum()),
        meta_oof_total_rows=len(features),
        meta_oof_coverage=float(oof_mask.mean()),
        meta_oof_first_position=first_oof_position,
    )


def time_series_cross_validate(
    features: pd.DataFrame,
    labels: pd.Series,
    dates: pd.Series,
    settings: RegimeModelSettings,
    *,
    prediction_date: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """执行五折 TimeSeriesSplit；验证折不拟合预处理且绝不采样。"""
    splitter = TimeSeriesSplit(n_splits=settings.cv_splits)
    metric_rows: list[dict[str, object]] = []
    prediction_rows: list[pd.DataFrame] = []
    dates = pd.to_datetime(dates).reset_index(drop=True)
    features = features.reset_index(drop=True)
    labels = labels.astype("string").reset_index(drop=True)
    for fold, (train_index, validation_index) in enumerate(splitter.split(features), start=1):
        fitted = fit_stacking_classifier(
            features.iloc[train_index],
            labels.iloc[train_index],
            settings,
            seed_offset=fold,
        )
        actual = labels.iloc[validation_index].astype(str).to_numpy()
        probability = fitted.predict_proba(features.iloc[validation_index])
        predicted = np.asarray(REGIME_ORDER, dtype=object)[probability.argmax(axis=1)]
        metric_rows.append(
            {
                "prediction_date": pd.Timestamp(prediction_date),
                "fold": fold,
                "train_start": dates.iloc[train_index].min(),
                "train_end": dates.iloc[train_index].max(),
                "validation_start": dates.iloc[validation_index].min(),
                "validation_end": dates.iloc[validation_index].max(),
                "train_rows": len(train_index),
                "train_rows_after_sampling": fitted.resampled_rows,
                "validation_rows": len(validation_index),
                "oversampling_method": fitted.oversampling_method,
                "meta_oof_rows": fitted.meta_oof_rows,
                "meta_oof_total_rows": fitted.meta_oof_total_rows,
                "meta_oof_coverage": fitted.meta_oof_coverage,
                "meta_oof_first_position": fitted.meta_oof_first_position,
                "accuracy": accuracy_score(actual, predicted),
                "precision_weighted": precision_score(
                    actual, predicted, labels=REGIME_ORDER, average="weighted", zero_division=0
                ),
                "recall_weighted": recall_score(
                    actual, predicted, labels=REGIME_ORDER, average="weighted", zero_division=0
                ),
                "precision_macro": precision_score(
                    actual, predicted, labels=REGIME_ORDER, average="macro", zero_division=0
                ),
                "recall_macro": recall_score(
                    actual, predicted, labels=REGIME_ORDER, average="macro", zero_division=0
                ),
            }
        )
        detail = pd.DataFrame(
            {
                "prediction_date": pd.Timestamp(prediction_date),
                "fold": fold,
                "regime_date": dates.iloc[validation_index].to_numpy(),
                "actual_regime": actual,
                "predicted_regime": predicted,
            }
        )
        for index, regime in enumerate(REGIME_ORDER):
            detail[f"probability_{regime}"] = probability[:, index]
        prediction_rows.append(detail)
    return pd.DataFrame(metric_rows), pd.concat(prediction_rows, ignore_index=True)


def calculate_feature_importance(
    raw_importance: np.ndarray,
    *,
    prediction_date: pd.Timestamp,
) -> pd.DataFrame:
    """把RF底层变量重要性汇总为R3要求的四类中国特征组。"""
    if raw_importance.shape != (len(MODEL_FEATURES),):
        raise ValueError("RF特征重要性维度与MODEL_FEATURES不一致")
    feature_importance = dict(zip(MODEL_FEATURES, raw_importance, strict=True))
    rows = [
        {
            "prediction_date": pd.Timestamp(prediction_date),
            "feature_group": group,
            "importance": float(sum(feature_importance[name] for name in names)),
        }
        for group, names in FEATURE_GROUPS.items()
    ]
    result = pd.DataFrame(rows)
    total = result["importance"].sum()
    if total > 0:
        result["importance"] = result["importance"] / total
    result["rank"] = result["importance"].rank(method="dense", ascending=False).astype(int)
    return result


def summarize_regime_distribution(
    regime_labels: pd.DataFrame,
    rolling_predictions: pd.DataFrame,
    *,
    expected_window_rows: int,
) -> pd.DataFrame:
    """输出最新滚动窗历史标注与滚动预测实际状态的数量/占比。"""
    latest_prediction_date = pd.to_datetime(regime_labels["prediction_date"]).max()
    latest_window = regime_labels.loc[
        pd.to_datetime(regime_labels["prediction_date"]).eq(latest_prediction_date)
    ]
    latest = latest_window["regime"]
    if (
        len(latest) != expected_window_rows
        or latest_window["regime_date"].nunique() != expected_window_rows
    ):
        raise AssertionError("latest_training_assignment必须严格来自最新预测月的84个目标月")
    scopes = {
        "latest_training_assignment": latest,
        "rolling_prediction_actual": rolling_predictions["actual_regime"].dropna(),
    }
    rows: list[dict[str, object]] = []
    for scope, values in scopes.items():
        count = values.value_counts().reindex(REGIME_ORDER, fill_value=0)
        total = int(count.sum())
        rows.extend(
            {
                "scope": scope,
                "regime": regime,
                "count": int(count.loc[regime]),
                "share": float(count.loc[regime] / total) if total else np.nan,
            }
            for regime in REGIME_ORDER
        )
    return pd.DataFrame(rows)


def _parameter_hash(settings: RegimeModelSettings) -> str:
    payload = {
        "settings": asdict(settings),
        "regime_order": REGIME_ORDER,
        "feature_groups": FEATURE_GROUPS,
        "sklearn_version": sklearn.__version__,
        "oversampling_backend": (
            "imbalanced_learn" if ImbalancedLearnSMOTE is not None else "deterministic_fallback"
        ),
        "stacking_meta_source": "strict_time_series_oof",
        "elbow_contract": "rolling_window_k_2_to_6",
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _prediction_positions(
    panel: pd.DataFrame,
    settings: RegimeModelSettings,
    prediction_start: str | pd.Timestamp,
) -> list[int]:
    start_period = pd.Timestamp(prediction_start).to_period("M")
    periods = panel["signal_date"].dt.to_period("M")
    positions = np.flatnonzero((periods >= start_period).to_numpy()).tolist()
    minimum_position = settings.train_window_months + 1
    invalid = [position for position in positions if position < minimum_position]
    if invalid:
        first_date = panel.iloc[invalid[0]]["signal_date"]
        raise ValueError(f"预测月 {first_date:%Y-%m} 之前不足84个完整目标月及其前置特征月")
    return positions


def run_stage_one_regime_model(
    monthly_features: pd.DataFrame,
    config: ChinaFactorTimingConfig | None = None,
    settings: RegimeModelSettings | None = None,
    *,
    prediction_start: str | pd.Timestamp | None = None,
) -> StageOneRegimeResult:
    """滚动重估第一阶段模型；默认从中国迁移版OOS首月开始预测。"""
    cfg = config or ChinaFactorTimingConfig()
    model_settings = settings or RegimeModelSettings(
        train_window_months=cfg.turbulence_window_months,
        seed=cfg.seed,
    )
    _validate_settings(model_settings)
    panel = build_stage_one_features(monthly_features)
    start = prediction_start or cfg.oos_start
    positions = _prediction_positions(panel, model_settings, start)
    if not positions:
        raise ValueError("指定区间没有可预测月份")

    rolling_rows: list[dict[str, object]] = []
    label_parts: list[pd.DataFrame] = []
    metric_parts: list[pd.DataFrame] = []
    cv_prediction_parts: list[pd.DataFrame] = []
    elbow_parts: list[pd.DataFrame] = []
    importance_parts: list[pd.DataFrame] = []
    audit_rows: list[dict[str, object]] = []
    parameter_hash = _parameter_hash(model_settings)

    for prediction_number, position in enumerate(positions):
        prediction_row = panel.iloc[position]
        prediction_date = pd.Timestamp(prediction_row["signal_date"])
        target_start = position - model_settings.train_window_months
        target_stop = position
        feature_start = target_start - 1
        feature_stop = target_stop - 1
        target_window = panel.iloc[target_start:target_stop].reset_index(drop=True)
        feature_window = panel.iloc[feature_start:feature_stop].reset_index(drop=True)
        if len(target_window) != model_settings.train_window_months:
            raise AssertionError("滚动目标窗并非固定84个月")
        expected_target_periods = feature_window["signal_date"].dt.to_period("M") + 1
        actual_target_periods = target_window["signal_date"].dt.to_period("M")
        if not expected_target_periods.equals(actual_target_periods):
            raise AssertionError("训练标签未严格按 X_t -> regime_{t+1} 对齐")
        if target_window["signal_date"].max() >= prediction_date:
            raise AssertionError("训练目标月必须严格早于预测月")

        clustering = fit_market_regimes(target_window["drawdown_3m"], model_settings)
        elbow_drawdown = pd.Series(
            target_window["drawdown_3m"].to_numpy(),
            index=pd.DatetimeIndex(target_window["signal_date"]),
            name="drawdown_3m",
        )
        elbow_parts.append(
            calculate_elbow_diagnostics(
                elbow_drawdown,
                model_settings,
                prediction_date=prediction_date,
            )
        )
        training_labels = clustering.predict(target_window["drawdown_3m"]).reset_index(drop=True)
        training_features = feature_window.loc[:, MODEL_FEATURES]
        training_dates = target_window["signal_date"].reset_index(drop=True)

        fold_metrics, cv_predictions = time_series_cross_validate(
            training_features,
            training_labels,
            training_dates,
            model_settings,
            prediction_date=prediction_date,
        )
        fitted = fit_stacking_classifier(
            training_features,
            training_labels,
            model_settings,
            seed_offset=model_settings.cv_splits + prediction_number + 1,
        )
        predictor = panel.iloc[[position - 1]].loc[:, MODEL_FEATURES]
        probability = fitted.predict_proba(predictor)[0]
        predicted_regime = REGIME_ORDER[int(np.argmax(probability))]
        actual_regime = clustering.predict(
            pd.Series([prediction_row["drawdown_3m"]], index=[position])
        ).iloc[0]
        rolling_row: dict[str, object] = {
            "predictor_date": panel.iloc[position - 1]["signal_date"],
            "prediction_date": prediction_date,
            "predicted_regime": predicted_regime,
            "actual_regime": actual_regime,
            "meta_oof_rows": fitted.meta_oof_rows,
            "meta_oof_total_rows": fitted.meta_oof_total_rows,
            "meta_oof_coverage": fitted.meta_oof_coverage,
            "parameter_hash": parameter_hash,
        }
        rolling_row.update(
            {f"probability_{regime}": probability[index] for index, regime in enumerate(REGIME_ORDER)}
        )
        rolling_rows.append(rolling_row)

        labels = pd.DataFrame(
            {
                "prediction_date": prediction_date,
                "regime_date": training_dates,
                "regime": training_labels,
            }
        )
        label_parts.append(labels)
        metric_parts.append(fold_metrics)
        cv_prediction_parts.append(cv_predictions)
        importance_parts.append(
            calculate_feature_importance(
                fitted.rf_feature_importance,
                prediction_date=prediction_date,
            )
        )
        center_payload = {
            row.regime: float(row.drawdown_center)
            for row in clustering.centers.itertuples(index=False)
        }
        audit_rows.append(
            {
                "prediction_date": prediction_date,
                "predictor_date": panel.iloc[position - 1]["signal_date"],
                "train_target_start": training_dates.min(),
                "train_target_end": training_dates.max(),
                "train_feature_start": feature_window["signal_date"].min(),
                "train_feature_end": feature_window["signal_date"].max(),
                "train_rows": len(training_features),
                "train_rows_after_sampling": fitted.resampled_rows,
                "oversampling_method": fitted.oversampling_method,
                "meta_oof_rows": fitted.meta_oof_rows,
                "meta_oof_total_rows": fitted.meta_oof_total_rows,
                "meta_oof_coverage": fitted.meta_oof_coverage,
                "meta_oof_first_position": fitted.meta_oof_first_position,
                "normal_drawdown_center": center_payload["Normal"],
                "correction_drawdown_center": center_payload["Correction"],
                "bear_drawdown_center": center_payload["Bear"],
                "parameter_hash": parameter_hash,
            }
        )

    rolling_predictions = pd.DataFrame(rolling_rows)
    regime_labels = pd.concat(label_parts, ignore_index=True)
    fold_metrics = pd.concat(metric_parts, ignore_index=True)
    cv_predictions = pd.concat(cv_prediction_parts, ignore_index=True)
    matrix = confusion_matrix(
        cv_predictions["actual_regime"],
        cv_predictions["predicted_regime"],
        labels=REGIME_ORDER,
    )
    confusion = pd.DataFrame(
        matrix,
        index=pd.Index(REGIME_ORDER, name="actual_regime"),
        columns=pd.Index(REGIME_ORDER, name="predicted_regime"),
    ).reset_index()
    feature_importance = pd.concat(importance_parts, ignore_index=True)
    mean_importance = (
        feature_importance.groupby("feature_group", as_index=False)["importance"].mean()
    )
    mean_importance["prediction_date"] = pd.NaT
    mean_importance["rank"] = mean_importance["importance"].rank(
        method="dense", ascending=False
    ).astype(int)
    feature_importance = pd.concat([feature_importance, mean_importance], ignore_index=True)
    regime_distribution = summarize_regime_distribution(
        regime_labels,
        rolling_predictions,
        expected_window_rows=model_settings.train_window_months,
    )
    elbow_diagnostics = pd.concat(elbow_parts, ignore_index=True)
    training_audit = pd.DataFrame(audit_rows)
    if not (
        (training_audit["train_target_end"] < training_audit["prediction_date"])
        & (training_audit["train_feature_end"] < training_audit["prediction_date"])
        & training_audit["train_rows"].eq(model_settings.train_window_months)
    ).all():
        raise AssertionError("滚动训练审计未满足严格过去与固定84月约束")
    return StageOneRegimeResult(
        rolling_predictions=rolling_predictions,
        regime_labels=regime_labels,
        fold_metrics=fold_metrics,
        cv_predictions=cv_predictions,
        confusion_matrix=confusion,
        regime_distribution=regime_distribution,
        elbow_diagnostics=elbow_diagnostics,
        feature_importance=feature_importance,
        training_audit=training_audit,
        parameter_hash=parameter_hash,
    )
