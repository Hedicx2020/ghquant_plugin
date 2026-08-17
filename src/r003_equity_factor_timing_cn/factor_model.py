"""m3 第二阶段分风险状态的六因子胜出概率模型。

``factor_returns`` 中信号月 ``t`` 的收益实际发生在下一交易期，因此本模块
把它明确标成 ``t+1`` 目标月标签。历史样本按第一阶段的预测状态分成
Normal/Correction（Bear 并入 Correction）两个子集；每个预测月只检查此前
固定 84 个完整目标月，并进一步要求标签可得日不晚于当前真实决策特征日，
避免中国市场长停牌导致的延迟退出收益提前进入训练。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Final, Mapping, Sequence

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import log_loss

from .config import ChinaFactorTimingConfig


SECOND_STAGE_STATES: Final[tuple[str, ...]] = ("Normal", "Correction")
SECOND_STAGE_FEATURE_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "Equity Valuation": ("equity_ep_percentile", "equity_pb_percentile"),
    "Financial Turbulence": ("financial_turbulence",),
    "Inflation": ("cpi_yoy", "cpi_10y_annualized"),
    "Financial Conditions": (
        "financial_risk",
        "credit_conditions",
        "leverage_conditions",
    ),
    "Monetary Policy Expectations": (
        "monetary_policy_expectations",
        "short_rate_proxy",
        "short_rate_change",
    ),
    "GDP Growth": ("gdp_real_yoy", "industrial_prod_yoy"),
}
SECOND_STAGE_FEATURES: Final[tuple[str, ...]] = tuple(
    feature
    for group_features in SECOND_STAGE_FEATURE_GROUPS.values()
    for feature in group_features
)


@dataclass(frozen=True)
class FactorModelSettings:
    """第二阶段集中参数；默认值来自 plan、B4、AS20 与 AS40。"""

    train_window_months: int = 84
    validation_months: int = 12
    rf_estimators: int = 500
    rf_max_depth: int = 4
    rf_min_samples_leaf: int = 3
    rf_max_features: str = "sqrt"
    rf_class_weight: str = "balanced"
    seed: int = 42


@dataclass
class WinnerLabelData:
    """严格 t+1 唯一胜出标签及其逐月证据。"""

    labels: pd.DataFrame
    audit: pd.DataFrame


@dataclass
class StageTwoFactorResult:
    """m4、m5 与报告层可直接消费的 m3 完整结果合同。"""

    rolling_probabilities: pd.DataFrame
    winner_labels: pd.DataFrame
    label_audit: pd.DataFrame
    correlation_matrices: pd.DataFrame
    winner_frequency: pd.DataFrame
    feature_importance: pd.DataFrame
    prediction_metrics: pd.DataFrame
    train_val_logloss: pd.DataFrame
    training_audit: pd.DataFrame
    parameter_hash: str


@dataclass
class _FittedBinaryForest:
    imputer: SimpleImputer
    model: RandomForestClassifier

    def positive_probability(self, features: pd.DataFrame) -> np.ndarray:
        transformed = self.imputer.transform(features.loc[:, SECOND_STAGE_FEATURES])
        probabilities = self.model.predict_proba(transformed)
        classes = [int(value) for value in self.model.classes_]
        if 1 not in classes:
            return np.zeros(len(features), dtype=float)
        return probabilities[:, classes.index(1)].astype(float)


def _validate_settings(settings: FactorModelSettings) -> None:
    if settings.train_window_months != 84:
        raise ValueError("B4要求第二阶段固定84个月滚动训练窗")
    if not 0 < settings.validation_months < settings.train_window_months:
        raise ValueError("validation_months 必须位于 (0, 84) 内")
    exact = (
        settings.rf_estimators == 500
        and settings.rf_max_depth == 4
        and settings.rf_min_samples_leaf == 3
        and settings.rf_max_features == "sqrt"
        and settings.rf_class_weight == "balanced"
        and settings.seed == 42
    )
    if not exact:
        raise ValueError("第二阶段RF参数必须保持plan/AS20冻结值")


def collapse_second_stage_regime(regime: pd.Series) -> pd.Series:
    """把 Bear 合并到 Correction，并拒绝未知状态静默进入模型。"""
    normalized = regime.astype("string").replace({"Bear": "Correction"})
    unknown = normalized.dropna().loc[~normalized.dropna().isin(SECOND_STAGE_STATES)]
    if not unknown.empty:
        raise ValueError(f"第一阶段存在未知状态: {sorted(unknown.unique().tolist())}")
    return normalized


def build_winner_labels(
    factor_returns: pd.DataFrame,
    factor_order: Sequence[str],
) -> WinnerLabelData:
    """由信号月 t 对应的下一交易期收益构造 t+1 唯一胜出标签。

    并列时严格按 ``factor_order`` 的既定顺序选择第一项，不使用随机决胜。
    六个因子任一缺失时整月标签保持不可用，禁止用部分截面定义胜出者。
    标签可得日取六个因子中最晚日期；新合同字段缺失时依次回退到计划
    ``return_date`` 和目标月末，以兼容既有无延迟调用。
    """
    required = {"signal_date", "factor", "factor_return"}
    missing = required.difference(factor_returns.columns)
    if missing:
        raise KeyError(f"factor_returns 缺少字段: {sorted(missing)}")
    order = tuple(factor_order)
    if len(order) != 6 or len(set(order)) != 6:
        raise ValueError("第二阶段必须收到固定六因子且顺序唯一")

    frame = factor_returns.copy()
    frame["signal_date"] = pd.to_datetime(frame["signal_date"]).dt.normalize()
    frame["factor_return"] = pd.to_numeric(frame["factor_return"], errors="coerce")
    if frame.duplicated(["signal_date", "factor"]).any():
        raise ValueError("factor_returns 同一信号月/因子存在重复记录")
    unexpected = sorted(set(frame["factor"].dropna()) - set(order))
    if unexpected:
        raise ValueError(f"factor_returns 含计划外因子: {unexpected}")

    if "label_available_date" in frame:
        frame["_label_available_date"] = pd.to_datetime(
            frame["label_available_date"], errors="coerce"
        ).dt.normalize()
        label_availability_source = "factor_returns.label_available_date"
    elif "return_date" in frame:
        frame["_label_available_date"] = pd.to_datetime(
            frame["return_date"], errors="coerce"
        ).dt.normalize()
        label_availability_source = "factor_returns.return_date_compatibility"
    else:
        frame["_label_available_date"] = (
            frame["signal_date"].dt.to_period("M") + 1
        ).dt.to_timestamp("M")
        label_availability_source = "derived_prediction_month_end_compatibility"

    returns = frame.pivot(index="signal_date", columns="factor", values="factor_return")
    returns = returns.reindex(columns=order).sort_index()
    execution = (
        frame.groupby("signal_date")["execution_date"].min()
        if "execution_date" in frame
        else pd.Series(pd.NaT, index=returns.index)
    )
    realized = (
        frame.groupby("signal_date")["return_date"].max()
        if "return_date" in frame
        else pd.Series(pd.NaT, index=returns.index)
    )
    availability_count = frame.groupby("signal_date")["_label_available_date"].count()
    label_available = frame.groupby("signal_date")["_label_available_date"].max()
    label_available = label_available.where(availability_count.eq(len(order)))

    label_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    for predictor_date, row in returns.iterrows():
        complete = bool(row.notna().all())
        winner: str | None = None
        tie_count = 0
        maximum = np.nan
        if complete:
            maximum = float(row.max())
            tied = [factor for factor in order if float(row[factor]) == maximum]
            winner = tied[0]
            tie_count = len(tied)
        prediction_period = pd.Timestamp(predictor_date).to_period("M") + 1
        prediction_date = prediction_period.to_timestamp("M")
        label_available_date = pd.to_datetime(label_available.get(predictor_date))
        for tie_rank, factor in enumerate(order):
            label_rows.append(
                {
                    "predictor_date": pd.Timestamp(predictor_date),
                    "prediction_date": prediction_date,
                    "prediction_period": prediction_period,
                    "factor": factor,
                    "factor_return": row[factor],
                    "is_winner": bool(complete and factor == winner),
                    "tie_break_rank": tie_rank,
                    "winner_available": complete,
                    "label_available_date": label_available_date,
                    "label_availability_source": label_availability_source,
                }
            )
        audit_rows.append(
            {
                "predictor_date": pd.Timestamp(predictor_date),
                "prediction_date": prediction_date,
                "prediction_period": prediction_period,
                "execution_date": pd.to_datetime(execution.get(predictor_date)),
                "realized_date": pd.to_datetime(realized.get(predictor_date)),
                "label_available_date": label_available_date,
                "label_availability_source": label_availability_source,
                "available_factor_count": int(row.notna().sum()),
                "winner_available": complete,
                "winner_factor": winner,
                "maximum_factor_return": maximum,
                "tie_count": tie_count,
                "tie_break_order": "|".join(order),
                "strict_t_plus_one": bool(
                    prediction_period > pd.Timestamp(predictor_date).to_period("M")
                ),
            }
        )
    labels = pd.DataFrame(label_rows)
    audit = pd.DataFrame(audit_rows)
    if not audit["strict_t_plus_one"].all():
        raise AssertionError("胜出标签并非严格来自特征月之后的t+1月")
    return WinnerLabelData(labels=labels, audit=audit)


def _normalise_stage_one_predictions(stage_one_predictions: object) -> pd.DataFrame:
    if not isinstance(stage_one_predictions, pd.DataFrame):
        stage_one_predictions = getattr(stage_one_predictions, "rolling_predictions", None)
    if not isinstance(stage_one_predictions, pd.DataFrame):
        raise TypeError("stage_one_predictions 必须是DataFrame或StageOneRegimeResult")
    required = {"prediction_date", "predicted_regime"}
    missing = required.difference(stage_one_predictions.columns)
    if missing:
        raise KeyError(f"第一阶段预测缺少字段: {sorted(missing)}")
    states = stage_one_predictions.loc[:, ["prediction_date", "predicted_regime"]].copy()
    states["prediction_date"] = pd.to_datetime(states["prediction_date"]).dt.normalize()
    states["prediction_period"] = states["prediction_date"].dt.to_period("M")
    duplicated = states.groupby("prediction_period")["predicted_regime"].nunique(dropna=False)
    if duplicated.gt(1).any():
        raise ValueError("同一目标月存在互相冲突的第一阶段预测状态")
    states = states.drop_duplicates("prediction_period", keep="last").sort_values(
        "prediction_period"
    )
    states["training_regime"] = collapse_second_stage_regime(states["predicted_regime"])
    return states.reset_index(drop=True)


def _summary_regime_history(stage_one_predictions: object) -> pd.DataFrame:
    """为相关性/频率表取得历史状态；优先使用m2滚动窗内状态标签。"""
    labels = getattr(stage_one_predictions, "regime_labels", None)
    if isinstance(labels, pd.DataFrame) and not labels.empty:
        required = {"prediction_date", "regime_date", "regime"}
        missing = required.difference(labels.columns)
        if missing:
            raise KeyError(f"m2 regime_labels 缺少字段: {sorted(missing)}")
        history = labels.loc[:, ["prediction_date", "regime_date", "regime"]].copy()
        history["prediction_date"] = pd.to_datetime(history["prediction_date"]).dt.normalize()
        history["prediction_period"] = pd.to_datetime(history["regime_date"]).dt.to_period("M")
        history = history.sort_values(["prediction_period", "prediction_date"])
        history = history.drop_duplicates("prediction_period", keep="last")
        history["training_regime"] = collapse_second_stage_regime(history["regime"])
        return history[["prediction_period", "training_regime"]].reset_index(drop=True)
    return _normalise_stage_one_predictions(stage_one_predictions)[
        ["prediction_period", "training_regime"]
    ]


def _training_regimes_for_window(
    stage_one_predictions: object,
    prediction_date: pd.Timestamp,
    window_periods: pd.Series,
) -> tuple[pd.DataFrame, str]:
    """取得当前预测月专属的历史状态切分，绝不引用目标月实际状态。"""
    labels = getattr(stage_one_predictions, "regime_labels", None)
    if isinstance(labels, pd.DataFrame) and not labels.empty:
        required = {"prediction_date", "regime_date", "regime"}
        missing = required.difference(labels.columns)
        if missing:
            raise KeyError(f"m2 regime_labels 缺少字段: {sorted(missing)}")
        prediction_period = pd.Timestamp(prediction_date).to_period("M")
        label_dates = pd.to_datetime(labels["prediction_date"]).dt.to_period("M")
        history = labels.loc[
            label_dates.eq(prediction_period), ["regime_date", "regime"]
        ].copy()
        history["prediction_period"] = pd.to_datetime(history["regime_date"]).dt.to_period("M")
        history["training_regime"] = collapse_second_stage_regime(history["regime"])
        history = history.drop_duplicates("prediction_period", keep="last")
        history = history.loc[history["prediction_period"].isin(window_periods)]
        return history[["prediction_period", "training_regime"]], "m2_window_regime_labels"
    history = _normalise_stage_one_predictions(stage_one_predictions)
    history = history.loc[history["prediction_period"].isin(window_periods)]
    return history[["prediction_period", "training_regime"]], "walk_forward_predicted_regimes"


def _prepare_stage_two_panel(
    monthly_features: pd.DataFrame,
    label_data: WinnerLabelData,
    stage_one_predictions: object,
    factor_order: Sequence[str],
) -> pd.DataFrame:
    required = {"signal_date", *SECOND_STAGE_FEATURES}
    missing = required.difference(monthly_features.columns)
    if missing:
        raise KeyError(f"monthly_features 缺少第二阶段字段: {sorted(missing)}")
    features = monthly_features.loc[:, ["signal_date", *SECOND_STAGE_FEATURES]].copy()
    features["predictor_date"] = pd.to_datetime(features.pop("signal_date")).dt.normalize()
    if features["predictor_date"].duplicated().any():
        raise ValueError("monthly_features 存在重复 signal_date")
    features = features.sort_values("predictor_date").reset_index(drop=True)
    feature_period = features["predictor_date"].dt.to_period("M")
    if feature_period.duplicated().any():
        raise ValueError("monthly_features 同一月份存在多条特征")
    if len(feature_period) > 1 and not np.equal(np.diff(feature_period.astype("int64")), 1).all():
        raise ValueError("monthly_features 月份不连续，无法证明固定84个日历月窗口")
    features["prediction_period"] = feature_period + 1

    audit = label_data.audit.loc[
        :,
        [
            "predictor_date",
            "winner_available",
            "winner_factor",
            "label_available_date",
            "label_availability_source",
        ],
    ].copy()
    return_wide = label_data.labels.pivot(
        index="predictor_date", columns="factor", values="factor_return"
    ).reindex(columns=factor_order)
    return_wide.columns = [f"actual_return_{factor}" for factor in factor_order]
    return_wide = return_wide.reset_index()
    states = _normalise_stage_one_predictions(stage_one_predictions)
    panel = features.merge(audit, on="predictor_date", how="left")
    panel = panel.merge(return_wide, on="predictor_date", how="left")
    panel = panel.merge(states, on="prediction_period", how="left")
    panel["winner_available"] = panel["winner_available"].fillna(False).astype(bool)
    return panel.sort_values("prediction_period").reset_index(drop=True)


def _fit_binary_forest(
    features: pd.DataFrame,
    labels: pd.Series,
    settings: FactorModelSettings,
) -> _FittedBinaryForest | None:
    if features.empty:
        return None
    imputer = SimpleImputer(strategy="median", keep_empty_features=True)
    transformed = imputer.fit_transform(features.loc[:, SECOND_STAGE_FEATURES])
    model = RandomForestClassifier(
        n_estimators=settings.rf_estimators,
        max_depth=settings.rf_max_depth,
        min_samples_leaf=settings.rf_min_samples_leaf,
        max_features=settings.rf_max_features,
        class_weight=settings.rf_class_weight,
        random_state=settings.seed,
        n_jobs=1,
    )
    model.fit(transformed, labels.astype(int).to_numpy())
    return _FittedBinaryForest(imputer=imputer, model=model)


def _safe_binary_logloss(labels: pd.Series, probability: np.ndarray) -> float:
    probability = np.asarray(probability, dtype=float)
    if labels.empty or probability.size == 0:
        return np.nan
    if len(labels) != len(probability):
        raise ValueError("logloss标签与概率长度不一致")
    clipped = np.clip(probability, 1.0e-12, 1.0 - 1.0e-12)
    two_class = np.column_stack([1.0 - clipped, clipped])
    return float(log_loss(labels.astype(int).to_numpy(), two_class, labels=[0, 1]))


def _parameter_hash(
    settings: FactorModelSettings,
    factor_order: Sequence[str],
) -> str:
    payload = {
        "settings": asdict(settings),
        "factor_order": list(factor_order),
        "second_stage_states": SECOND_STAGE_STATES,
        "feature_groups": SECOND_STAGE_FEATURE_GROUPS,
        "sklearn_version": sklearn.__version__,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def calculate_factor_correlations(
    winner_labels: pd.DataFrame,
    stage_one_predictions: object,
    factor_order: Sequence[str],
) -> pd.DataFrame:
    """输出全样本、预测Normal及预测Correction的六因子相关矩阵。"""
    returns = winner_labels.pivot(
        index=["prediction_period", "predictor_date"],
        columns="factor",
        values="factor_return",
    ).reindex(columns=factor_order).reset_index()
    states = _summary_regime_history(stage_one_predictions)
    returns = returns.merge(
        states[["prediction_period", "training_regime"]],
        on="prediction_period",
        how="left",
    )
    rows: list[dict[str, object]] = []
    scopes: Mapping[str, pd.DataFrame] = {
        "Entire Sample": returns,
        "Normal": returns.loc[returns["training_regime"] == "Normal"],
        "Correction": returns.loc[returns["training_regime"] == "Correction"],
    }
    for scope, subset in scopes.items():
        matrix = subset.loc[:, factor_order].corr(min_periods=2)
        for row_factor in factor_order:
            for column_factor in factor_order:
                pair_count = int(
                    subset.loc[:, [row_factor, column_factor]].dropna().shape[0]
                )
                rows.append(
                    {
                        "scope": scope,
                        "row_factor": row_factor,
                        "column_factor": column_factor,
                        "correlation": matrix.loc[row_factor, column_factor],
                        "n_obs": pair_count,
                    }
                )
    return pd.DataFrame(rows)


def summarize_winner_frequency(
    winner_labels: pd.DataFrame,
    stage_one_predictions: object,
    factor_order: Sequence[str],
) -> pd.DataFrame:
    """统计全样本及两个预测状态下的唯一胜出频率。"""
    labels = winner_labels.loc[winner_labels["winner_available"]].copy()
    states = _summary_regime_history(stage_one_predictions)
    labels = labels.merge(
        states[["prediction_period", "training_regime"]],
        on="prediction_period",
        how="left",
    )
    rows: list[dict[str, object]] = []
    scopes: Mapping[str, pd.DataFrame] = {
        "Entire Sample": labels,
        "Normal": labels.loc[labels["training_regime"] == "Normal"],
        "Correction": labels.loc[labels["training_regime"] == "Correction"],
    }
    for scope, subset in scopes.items():
        months = int(subset["prediction_period"].nunique())
        winners = subset.loc[subset["is_winner"]].groupby("factor").size()
        for factor in factor_order:
            count = int(winners.get(factor, 0))
            rows.append(
                {
                    "scope": scope,
                    "factor": factor,
                    "winner_count": count,
                    "eligible_months": months,
                    "winner_frequency": count / months if months else np.nan,
                }
            )
    return pd.DataFrame(rows)


def _aggregate_feature_importance(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw
    raw = raw.copy()
    raw["level"] = "factor_feature"
    factor_groups = (
        raw.groupby(
            ["prediction_date", "model_regime", "factor", "feature_group"],
            as_index=False,
        )["importance"]
        .sum()
    )
    grouped = (
        factor_groups.groupby(
            ["prediction_date", "model_regime", "feature_group"], as_index=False
        )["importance"]
        .mean()
    )
    totals = grouped.groupby(["prediction_date", "model_regime"])["importance"].transform(
        "sum"
    )
    grouped["importance"] = np.divide(
        grouped["importance"],
        totals,
        out=np.zeros(len(grouped), dtype=float),
        where=totals.to_numpy() > 0,
    )
    grouped["factor"] = "ALL"
    grouped["feature"] = grouped["feature_group"]
    grouped["level"] = "state_group"
    return pd.concat([raw, grouped[raw.columns]], ignore_index=True)


def _rank_ic(probabilities: Mapping[str, float], returns: Mapping[str, float]) -> float:
    probability = pd.Series(probabilities, dtype=float)
    realized = pd.Series(returns, dtype=float).reindex(probability.index)
    valid = probability.notna() & realized.notna()
    if valid.sum() < 2 or probability.loc[valid].nunique() < 2 or realized.loc[valid].nunique() < 2:
        return np.nan
    return float(probability.loc[valid].corr(realized.loc[valid], method="spearman"))


def run_stage_two_factor_model(
    monthly_features: pd.DataFrame,
    factor_returns: pd.DataFrame,
    stage_one_predictions: object,
    config: ChinaFactorTimingConfig | None = None,
    settings: FactorModelSettings | None = None,
    *,
    prediction_start: str | pd.Timestamp | None = None,
) -> StageTwoFactorResult:
    """滚动训练两个状态下的六个RF，并按目标月预测状态选择概率。

    默认只返回 2023-04 起的OOS概率；训练仍严格取每个目标月之前的84个
    日历月。候选窗中只有 ``label_available_date <= predictor_date`` 的标签
    才可进入正式模型和诊断切分；同日已实现标签按冻结口径可用。历史状态
    也必须来自调用方提供的 ``predicted_regime``，本函数不会用实际状态补洞。
    """
    cfg = config or ChinaFactorTimingConfig()
    model_settings = settings or FactorModelSettings(
        train_window_months=cfg.turbulence_window_months,
        seed=cfg.seed,
    )
    _validate_settings(model_settings)
    factor_order = tuple(cfg.factor_names)
    label_data = build_winner_labels(factor_returns, factor_order)
    panel = _prepare_stage_two_panel(
        monthly_features,
        label_data,
        stage_one_predictions,
        factor_order,
    )
    start_period = pd.Timestamp(prediction_start or cfg.oos_start).to_period("M")
    positions = np.flatnonzero(
        (
            (panel["prediction_period"] >= start_period)
            & panel["training_regime"].notna()
        ).to_numpy()
    )
    positions = [int(position) for position in positions if position >= model_settings.train_window_months]
    if not positions:
        raise ValueError("指定区间没有满足84个月前置窗口的第二阶段预测月")

    probability_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    loss_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    importance_rows: list[dict[str, object]] = []
    parameter_hash = _parameter_hash(model_settings, factor_order)
    feature_to_group = {
        feature: group
        for group, features in SECOND_STAGE_FEATURE_GROUPS.items()
        for feature in features
    }

    for position in positions:
        prediction_row = panel.iloc[position]
        prediction_period = prediction_row["prediction_period"]
        prediction_date = pd.Timestamp(prediction_row.get("prediction_date"))
        if pd.isna(prediction_date):
            prediction_date = prediction_period.to_timestamp("M")
        predictor_date = pd.Timestamp(prediction_row["predictor_date"])
        chosen_regime = prediction_row["training_regime"]
        if pd.isna(chosen_regime):
            raise ValueError(f"目标月 {prediction_period} 缺少第一阶段预测状态")
        window = panel.iloc[position - model_settings.train_window_months : position].copy()
        if len(window) != model_settings.train_window_months:
            raise AssertionError("第二阶段训练候选窗不是固定84个月")
        period_numbers = window["prediction_period"].astype("int64")
        if not np.equal(np.diff(period_numbers), 1).all():
            raise AssertionError("第二阶段训练候选窗不是84个连续日历月")
        if window["prediction_period"].max() >= prediction_period:
            raise AssertionError("第二阶段训练标签包含预测月或未来月份")
        if not (
            window["predictor_date"].dt.to_period("M") + 1
            == window["prediction_period"]
        ).all():
            raise AssertionError("历史特征与t+1胜出标签未严格错开一月")
        local_regimes, state_source = _training_regimes_for_window(
            stage_one_predictions,
            prediction_date,
            window["prediction_period"],
        )
        window = window.drop(columns="training_regime").merge(
            local_regimes,
            on="prediction_period",
            how="left",
            validate="one_to_one",
        )
        if window["training_regime"].isna().any():
            missing_periods = window.loc[
                window["training_regime"].isna(), "prediction_period"
            ].astype(str).tolist()
            raise ValueError(
                "第二阶段84月训练窗缺少第一阶段历史状态: "
                f"{missing_periods[:6]}"
            )
        window["label_known_by_decision"] = (
            window["winner_available"]
            & window["label_available_date"].notna()
            & window["label_available_date"].le(predictor_date)
        )
        eligible_window = window.loc[window["label_known_by_decision"]]
        if not eligible_window["label_available_date"].le(predictor_date).all():
            raise AssertionError("第二阶段训练包含决策特征日尚未实现的标签")
        validation_start = prediction_period - model_settings.validation_months
        state_models: dict[str, dict[str, _FittedBinaryForest | None]] = {}

        for model_regime in SECOND_STAGE_STATES:
            state_window = window.loc[
                window["label_known_by_decision"]
                & window["training_regime"].eq(model_regime)
            ].copy()
            diagnostic_train = state_window.loc[
                state_window["prediction_period"] < validation_start
            ]
            diagnostic_validation = state_window.loc[
                state_window["prediction_period"] >= validation_start
            ]
            model_by_factor: dict[str, _FittedBinaryForest | None] = {}
            for factor in factor_order:
                diagnostic = _fit_binary_forest(
                    diagnostic_train,
                    diagnostic_train["winner_factor"].eq(factor),
                    model_settings,
                )
                train_probability = (
                    diagnostic.positive_probability(diagnostic_train)
                    if diagnostic is not None
                    else np.asarray([], dtype=float)
                )
                validation_probability = (
                    diagnostic.positive_probability(diagnostic_validation)
                    if diagnostic is not None and not diagnostic_validation.empty
                    else np.asarray([], dtype=float)
                )
                diagnostic_available = diagnostic is not None
                validation_available = (
                    diagnostic_available and not diagnostic_validation.empty
                )
                if diagnostic_train.empty:
                    unavailable_reason = "no_state_samples_in_diagnostic_train"
                elif diagnostic_validation.empty:
                    unavailable_reason = "no_state_samples_in_validation"
                else:
                    unavailable_reason = ""
                loss_rows.append(
                    {
                        "prediction_date": prediction_date,
                        "model_regime": model_regime,
                        "factor": factor,
                        "train_rows": len(diagnostic_train),
                        "validation_rows": len(diagnostic_validation),
                        "diagnostic_available": diagnostic_available,
                        "train_logloss_available": diagnostic_available,
                        "validation_logloss_available": validation_available,
                        "diagnostic_unavailable_reason": unavailable_reason,
                        "train_logloss": _safe_binary_logloss(
                            diagnostic_train["winner_factor"].eq(factor),
                            train_probability,
                        ),
                        "validation_logloss": _safe_binary_logloss(
                            diagnostic_validation["winner_factor"].eq(factor),
                            validation_probability,
                        ),
                        "validation_start_period": validation_start,
                    }
                )
                fitted = _fit_binary_forest(
                    state_window,
                    state_window["winner_factor"].eq(factor),
                    model_settings,
                )
                model_by_factor[factor] = fitted
                if fitted is not None:
                    for feature, importance in zip(
                        SECOND_STAGE_FEATURES,
                        fitted.model.feature_importances_,
                        strict=True,
                    ):
                        importance_rows.append(
                            {
                                "prediction_date": prediction_date,
                                "model_regime": model_regime,
                                "factor": factor,
                                "feature": feature,
                                "feature_group": feature_to_group[feature],
                                "importance": float(importance),
                            }
                        )
            state_models[model_regime] = model_by_factor
            audit_rows.append(
                {
                    "prediction_date": prediction_date,
                    "predictor_date": predictor_date,
                    "predicted_regime": prediction_row["predicted_regime"],
                    "chosen_regime": chosen_regime,
                    "model_regime": model_regime,
                    "train_window_start": window["prediction_period"].min().to_timestamp("M"),
                    "train_window_end": window["prediction_period"].max().to_timestamp("M"),
                    "train_candidate_months": len(window),
                    "available_label_months": int(window["winner_available"].sum()),
                    "train_eligible_label_months": int(
                        window["label_known_by_decision"].sum()
                    ),
                    "labels_excluded_by_availability": int(
                        (
                            window["winner_available"]
                            & ~window["label_known_by_decision"]
                        ).sum()
                    ),
                    "missing_label_available_date_months": int(
                        (
                            window["winner_available"]
                            & window["label_available_date"].isna()
                        ).sum()
                    ),
                    "label_cutoff_date": predictor_date,
                    "latest_training_label_available_date": state_window[
                        "label_available_date"
                    ].max(),
                    "label_availability_sources": "|".join(
                        sorted(
                            window.loc[
                                window["winner_available"],
                                "label_availability_source",
                            ]
                            .dropna()
                            .astype(str)
                            .unique()
                        )
                    ),
                    "state_training_rows": len(state_window),
                    "missing_state_months": int(window["training_regime"].isna().sum()),
                    "state_source": state_source,
                    "model_count": int(sum(model is not None for model in model_by_factor.values())),
                    "parameter_hash": parameter_hash,
                }
            )

        predictor = prediction_row.to_frame().T.loc[:, SECOND_STAGE_FEATURES]
        raw_probability: dict[str, float] = {}
        for factor in factor_order:
            fitted = state_models[str(chosen_regime)][factor]
            raw_probability[factor] = (
                float(fitted.positive_probability(predictor)[0])
                if fitted is not None
                else 0.0
            )
        probability_sum = float(sum(raw_probability.values()))
        equal_weight_fallback = not np.isfinite(probability_sum) or probability_sum <= 0.0
        if equal_weight_fallback:
            normalized = {factor: 1.0 / len(factor_order) for factor in factor_order}
            fallback_reason = "zero_or_nonfinite_probability_sum"
        else:
            normalized = {
                factor: probability / probability_sum
                for factor, probability in raw_probability.items()
            }
            fallback_reason = ""
        predicted_winner = max(
            factor_order,
            key=lambda factor: (normalized[factor], -factor_order.index(factor)),
        )
        actual_returns = {
            factor: prediction_row[f"actual_return_{factor}"] for factor in factor_order
        }
        actual_winner = prediction_row["winner_factor"] if prediction_row["winner_available"] else None
        rank_ic = _rank_ic(normalized, actual_returns)
        top_hit = (
            bool(predicted_winner == actual_winner)
            if actual_winner is not None and not pd.isna(actual_winner)
            else pd.NA
        )
        probability_record: dict[str, object] = {
            "predictor_date": predictor_date,
            "prediction_date": prediction_date,
            "predicted_regime": prediction_row["predicted_regime"],
            "model_regime": chosen_regime,
            "probability_sum": probability_sum,
            "used_equal_weight_fallback": equal_weight_fallback,
            "fallback_reason": fallback_reason,
            "parameter_hash": parameter_hash,
        }
        probability_record.update(
            {f"raw_probability_{factor}": raw_probability[factor] for factor in factor_order}
        )
        probability_record.update(
            {f"weight_{factor}": normalized[factor] for factor in factor_order}
        )
        probability_rows.append(probability_record)
        metric_rows.append(
            {
                "predictor_date": predictor_date,
                "prediction_date": prediction_date,
                "predicted_regime": prediction_row["predicted_regime"],
                "model_regime": chosen_regime,
                "predicted_winner": predicted_winner,
                "actual_winner": actual_winner,
                "label_available": bool(prediction_row["winner_available"]),
                "rank_ic": rank_ic,
                "top_hit": top_hit,
            }
        )

    rolling = pd.DataFrame(probability_rows)
    weight_columns = [f"weight_{factor}" for factor in factor_order]
    if not np.allclose(rolling[weight_columns].sum(axis=1), 1.0, rtol=0.0, atol=1.0e-12):
        raise AssertionError("六因子归一化概率权重和不等于1")
    training_audit = pd.DataFrame(audit_rows)
    dated_training_rows = training_audit[
        "latest_training_label_available_date"
    ].notna()
    if not (
        training_audit["train_candidate_months"].eq(model_settings.train_window_months)
        & (training_audit["train_window_end"] < training_audit["prediction_date"])
        & (training_audit["predictor_date"] < training_audit["prediction_date"])
    ).all():
        raise AssertionError("第二阶段滚动训练审计未满足严格过去与固定84月")
    if not (
        training_audit.loc[
            dated_training_rows, "latest_training_label_available_date"
        ]
        <= training_audit.loc[dated_training_rows, "label_cutoff_date"]
    ).all():
        raise AssertionError("第二阶段训练标签可得日晚于决策特征日")

    correlations = calculate_factor_correlations(
        label_data.labels,
        stage_one_predictions,
        factor_order,
    )
    frequency = summarize_winner_frequency(
        label_data.labels,
        stage_one_predictions,
        factor_order,
    )
    importance = _aggregate_feature_importance(pd.DataFrame(importance_rows))
    return StageTwoFactorResult(
        rolling_probabilities=rolling,
        winner_labels=label_data.labels,
        label_audit=label_data.audit,
        correlation_matrices=correlations,
        winner_frequency=frequency,
        feature_importance=importance,
        prediction_metrics=pd.DataFrame(metric_rows),
        train_val_logloss=pd.DataFrame(loss_rows),
        training_audit=training_audit,
        parameter_hash=parameter_hash,
    )


__all__ = [
    "SECOND_STAGE_STATES",
    "SECOND_STAGE_FEATURE_GROUPS",
    "SECOND_STAGE_FEATURES",
    "FactorModelSettings",
    "WinnerLabelData",
    "StageTwoFactorResult",
    "collapse_second_stage_regime",
    "build_winner_labels",
    "calculate_factor_correlations",
    "summarize_winner_frequency",
    "run_stage_two_factor_model",
]
