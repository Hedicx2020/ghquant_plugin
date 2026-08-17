"""r007 m3：显式版本约束、八基础回归器与两种集成预测。

本模块只描述报告专属的模型集合和固定参数。通用 complete-case 训练、
样本外预测、集成完整性与参数序列化均复用 ``common.ml_pipeline``。
"""

from __future__ import annotations

import platform
from collections.abc import Callable, Mapping, Sequence
from importlib import metadata
from typing import Any

import pandas as pd

from common.ml_pipeline import (
    append_prediction_ensembles,
    snapshot_estimator_params,
)

from .config import DEFAULT_M3_CONFIG, M3Config


def assert_runtime_versions(
    config: M3Config = DEFAULT_M3_CONFIG,
) -> pd.DataFrame:
    """按 AS15 逐项断言 Python 与数值/模型库版本完全一致。"""
    expected = {
        "Python": config.versions.python,
        **config.versions.as_distribution_mapping(),
    }
    observed: dict[str, str] = {"Python": platform.python_version()}
    missing: list[str] = []
    for distribution in config.versions.as_distribution_mapping():
        try:
            observed[distribution] = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            observed[distribution] = "missing"
            missing.append(distribution)
    evidence = pd.DataFrame(
        [
            {
                "dependency": dependency,
                "expected_version": expected_version,
                "observed_version": observed[dependency],
                "version_match": observed[dependency] == expected_version,
            }
            for dependency, expected_version in expected.items()
        ]
    )
    mismatch = evidence.loc[~evidence["version_match"]]
    if not mismatch.empty:
        details = ", ".join(
            f"{row.dependency}: expected={row.expected_version}, "
            f"observed={row.observed_version}"
            for row in mismatch.itertuples(index=False)
        )
        if missing:
            details = f"{details}; missing={sorted(missing)}"
        raise RuntimeError(f"AS15 依赖版本不一致: {details}")
    return evidence


def initialize_base_estimators(
    config: M3Config = DEFAULT_M3_CONFIG,
    *,
    check_versions: bool = True,
) -> dict[str, Any]:
    """按 plan 2.1 初始化八个尚未训练的基础回归器。"""
    if check_versions:
        assert_runtime_versions(config)
    from lightgbm import LGBMRegressor
    from sklearn.ensemble import AdaBoostRegressor, RandomForestRegressor
    from sklearn.linear_model import Lasso, LinearRegression, Ridge
    from sklearn.svm import SVR
    from sklearn.tree import DecisionTreeRegressor
    from xgboost import XGBRegressor

    parameters = config.models
    base_tree = DecisionTreeRegressor(**dict(parameters.adaboost_base_tree))
    estimators: dict[str, Any] = {
        "OLS": LinearRegression(**dict(parameters.ols)),
        "LASSO": Lasso(**dict(parameters.lasso)),
        "RIDGE": Ridge(**dict(parameters.ridge)),
        "SVM": SVR(**dict(parameters.svm)),
        "XGBoost": XGBRegressor(**dict(parameters.xgboost)),
        "LGBM": LGBMRegressor(**dict(parameters.lightgbm)),
        "RF": RandomForestRegressor(**dict(parameters.random_forest)),
        "AdaBoost": AdaBoostRegressor(
            estimator=base_tree,
            **dict(parameters.adaboost),
        ),
    }
    if tuple(estimators) != config.prediction.base_model_names:
        raise AssertionError("基础模型顺序或名称与 B11 配置不一致")
    return estimators


def build_base_model_factories(
    config: M3Config = DEFAULT_M3_CONFIG,
    *,
    check_versions: bool = True,
) -> dict[str, Callable[[], Any]]:
    """返回每次调用都创建全新 estimator 的八模型工厂。"""
    if check_versions:
        assert_runtime_versions(config)
    from sklearn.base import clone

    prototypes = initialize_base_estimators(config, check_versions=False)
    return {
        model_name: (lambda prototype=prototype: clone(prototype))
        for model_name, prototype in prototypes.items()
    }


def build_model_configuration_evidence(
    config: M3Config = DEFAULT_M3_CONFIG,
) -> dict[str, Any]:
    """返回 final 运行可直接写盘的版本和全量 ``get_params`` 证据。"""
    versions = assert_runtime_versions(config)
    estimators = initialize_base_estimators(config, check_versions=False)
    return {
        "dependency_versions": versions.to_dict(orient="records"),
        "base_models": {
            model_name: snapshot_estimator_params(estimator)
            for model_name, estimator in estimators.items()
        },
        "ensemble_models": {
            config.prediction.ensemble_average_name: {
                "rule": "arithmetic_mean",
                "required_base_models": list(config.prediction.base_model_names),
            },
            config.prediction.ensemble_median_name: {
                "rule": "median",
                "required_base_models": list(config.prediction.base_model_names),
            },
        },
    }


def build_ensemble_predictions(
    base_predictions: pd.DataFrame,
    *,
    group_columns: Sequence[str],
    config: M3Config = DEFAULT_M3_CONFIG,
) -> pd.DataFrame:
    """追加 F18/F19；缺任一基础模型的同日同股观测不产生集成。"""
    return append_prediction_ensembles(
        base_predictions,
        group_columns=group_columns,
        base_model_names=config.prediction.base_model_names,
        average_name=config.prediction.ensemble_average_name,
        median_name=config.prediction.ensemble_median_name,
    )


def validate_parameter_snapshot(
    snapshot: Mapping[str, Any],
    config: M3Config = DEFAULT_M3_CONFIG,
) -> None:
    """核验快照包含八基础模型和两个集成规则，供 final 写盘前调用。"""
    base_models = snapshot.get("base_models")
    ensemble_models = snapshot.get("ensemble_models")
    if not isinstance(base_models, Mapping):
        raise TypeError("参数快照缺少 base_models 映射")
    if tuple(base_models) != config.prediction.base_model_names:
        raise AssertionError("参数快照的基础模型集合或顺序不符合 B11")
    expected_ensembles = {
        config.prediction.ensemble_average_name,
        config.prediction.ensemble_median_name,
    }
    if not isinstance(ensemble_models, Mapping) or set(ensemble_models) != expected_ensembles:
        raise AssertionError("参数快照缺少 F18/F19 集成规则")
    for model_name, evidence in base_models.items():
        if not isinstance(evidence, Mapping) or "params_deep" not in evidence:
            raise AssertionError(f"{model_name} 缺少 get_params(deep=True) 快照")
