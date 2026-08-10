"""r006 m2：本地因子家族袖套与统计评价。

本模块只实现 r006 特有的八家族研究层。通用横截面 IC、Rank IC、分位组与
标准化分别复用 :mod:`common.backtest` 和 :mod:`common.utils`；资产配置引擎
仍由 ``common/allocation_backtest.py`` 提供，未在此复制。

时点合同：

1. 因子观测必须不晚于 T 月末 ``signal_date``；
2. 因子方向只使用 expanding 训练窗内、且标签实现日不晚于 ``train_end`` 的样本；
3. 冻结方向只应用于 m1 ``window_id`` 标识的完整 12 月预测块；
4. T 月信号形成的权重只乘以 ``forward_return_date > signal_date`` 的 T+1 收益。

正式 ``factors/`` 为空、m1 为 dry-run 或 AS26 哈希漂移时直接失败，绝不生成
synthetic 因子。当前 m2 不从 raw 行情、估值或财务表另行派生候选因子。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from common.backtest import (
    assign_quantile_groups,
    calculate_ic,
    calculate_rank_ic,
)
from common.utils import standardize

from .config import DEFAULT_CONFIG, R006M1Config
from .data_pipeline import (
    DataContractError,
    FactorCrosswalkResult,
    FormalDataUnavailableError,
    FrozenFactorDirections,
    M1Dataset,
    apply_annual_frozen_factor_directions,
    fit_annual_frozen_factor_directions,
    select_walk_forward_window,
    validate_factor_crosswalk,
)


class M2ContractError(DataContractError):
    """m2 输入、冻结或统计合同不满足。"""


@dataclass(frozen=True)
class FrozenDirections:
    """m1 authoritative 预测周期方向的 m2 兼容视图。"""

    table: pd.DataFrame
    sha256: str
    crosswalk_sha256: str
    window_id: str
    prediction_year: int
    prediction_start: pd.Timestamp
    prediction_end: pd.Timestamp
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    authoritative: FrozenFactorDirections


@dataclass(frozen=True)
class PortfolioLayer:
    """一层因子/家族目标权重、收益和成本敏感性。"""

    weights: pd.DataFrame
    returns: pd.DataFrame
    cost_sensitivity: pd.DataFrame


@dataclass(frozen=True)
class FamilySleeveAnalysis:
    """m2 单个 walk-forward 窗口的完整可计算结果。"""

    directions: FrozenDirections
    directed_panel: pd.DataFrame
    factor_ic: pd.DataFrame
    family_ic: pd.DataFrame
    factor_layer: PortfolioLayer
    family_layer: PortfolioLayer
    family_composition: pd.DataFrame
    coverage: pd.DataFrame


@dataclass(frozen=True)
class NeweyWestResult:
    """Newey–West OLS 系数、协方差和样本信息。"""

    coefficients: pd.DataFrame
    covariance: pd.DataFrame
    fitted: pd.Series
    residuals: pd.Series
    lag: int
    observations: int


@dataclass(frozen=True)
class FamaMacBethResult:
    """月度横截面回归和时间序列 NW 汇总。"""

    monthly_coefficients: pd.DataFrame
    summary: pd.DataFrame


def _require_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    *,
    label: str,
) -> None:
    """统一检查 DataFrame 字段合同。"""
    missing = sorted(set(required).difference(frame.columns))
    if missing:
        raise M2ContractError(f"{label} 缺少字段: {missing}")


def _finite_numeric(series: pd.Series) -> pd.Series:
    """将非数值和正负无穷统一为缺失。"""
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.where(np.isfinite(numeric))


def assert_formal_m1_dataset(
    dataset: M1Dataset,
    *,
    config: R006M1Config = DEFAULT_CONFIG,
) -> None:
    """阻断 dry-run、空因子面板、空固定因子集和 m1 已登记问题。"""
    if dataset.dry_run:
        raise FormalDataUnavailableError(
            "r006 m2 正式模式不接受 m1 dry-run；禁止 synthetic"
        )
    if dataset.factor_panel.empty:
        raise FormalDataUnavailableError(
            f"{config.data_root / 'factors'} 没有正式因子观测；禁止 synthetic"
        )
    if not dataset.fixed_factor_universe:
        raise FormalDataUnavailableError("m1 未冻结正式固定因子集")
    if dataset.monthly_stock_panel.empty:
        raise FormalDataUnavailableError("m1 正式股票月面板为空")
    if dataset.walk_forward_windows.empty:
        raise FormalDataUnavailableError("m1 正式 walk-forward 窗口为空")
    if dataset.issues:
        details = "\n- ".join(dataset.issues)
        raise FormalDataUnavailableError(
            "m1 仍有正式数据阻断项，m2 不得继续：\n- " + details
        )


def assert_frozen_crosswalk(
    crosswalk: FactorCrosswalkResult,
    frozen_sha256: str,
    *,
    config: R006M1Config = DEFAULT_CONFIG,
) -> None:
    """复算 AS26 一对一映射并锁定 m1 交叉表哈希。"""
    validate_factor_crosswalk(crosswalk, config)
    if not frozen_sha256:
        raise M2ContractError("AS26 冻结 SHA-256 不能为空")
    if crosswalk.sha256 != frozen_sha256:
        raise M2ContractError(
            "AS26 家族映射哈希漂移："
            f"expected={frozen_sha256}, actual={crosswalk.sha256}"
        )


def assemble_m2_factor_panel(
    dataset: M1Dataset,
    *,
    config: R006M1Config = DEFAULT_CONFIG,
    factor_value_column: str = "factor_value",
) -> pd.DataFrame:
    """消费 m1 已完成 PIT 对齐的 factor_panel 并接入股票月面板与 AS26 家族。"""
    assert_formal_m1_dataset(dataset, config=config)
    assert_frozen_crosswalk(
        dataset.factor_crosswalk,
        dataset.factor_crosswalk.sha256,
        config=config,
    )
    factor_source_date_column = (
        "source_date"
        if "source_date" in dataset.factor_panel.columns
        else config.source_date_key
    )
    factor_required = {
        config.stock_key,
        factor_source_date_column,
        config.signal_date_key,
        "factor_id",
        factor_value_column,
    }
    stock_required = {
        config.stock_key,
        "signal_month",
        config.signal_date_key,
        "execution_date",
        "forward_return_date",
        "forward_return",
        "negotiable_market_value",
        "turn_value_month",
        "turnover_rate_free_month",
        "is_signal_eligible",
        "execution_buyable",
        "execution_sellable",
    }
    _require_columns(dataset.factor_panel, factor_required, label="m1 factor_panel")
    _require_columns(
        dataset.monthly_stock_panel,
        stock_required,
        label="m1 monthly_stock_panel",
    )

    factors = dataset.factor_panel.loc[
        dataset.factor_panel["factor_id"]
        .astype(str)
        .isin(dataset.fixed_factor_universe),
        list(factor_required),
    ].copy()
    factors[config.stock_key] = factors[config.stock_key].astype(str).str.zfill(6)
    factors["factor_id"] = factors["factor_id"].astype(str)
    factors["factor_source_date"] = pd.to_datetime(
        factors.pop(factor_source_date_column), errors="coerce"
    ).dt.normalize()
    factors[config.signal_date_key] = pd.to_datetime(
        factors[config.signal_date_key], errors="coerce"
    ).dt.normalize()
    factors[factor_value_column] = _finite_numeric(factors[factor_value_column])
    factors["signal_month"] = factors[config.signal_date_key].dt.to_period(
        config.schedule_month_frequency
    )
    factors = factors.dropna(
        subset=[
            config.stock_key,
            "factor_source_date",
            config.signal_date_key,
            "factor_id",
            factor_value_column,
        ]
    )

    stock_columns = list(stock_required)
    stocks = dataset.monthly_stock_panel.loc[:, stock_columns].copy()
    stocks[config.stock_key] = stocks[config.stock_key].astype(str).str.zfill(6)
    for column in (
        config.signal_date_key,
        "execution_date",
        "forward_return_date",
    ):
        stocks[column] = pd.to_datetime(stocks[column], errors="coerce").dt.normalize()
    joined = factors.merge(
        stocks.drop(columns=["signal_month"]),
        on=[config.stock_key, config.signal_date_key],
        how="inner",
        validate="many_to_one",
        suffixes=("", "_stock"),
    )
    joined["signal_month"] = joined[config.signal_date_key].dt.to_period(
        config.schedule_month_frequency
    )
    joined["factor_source_after_signal"] = joined["factor_source_date"].gt(
        joined[config.signal_date_key]
    )
    joined = joined.loc[~joined["factor_source_after_signal"]].sort_values(
        [
            config.stock_key,
            "factor_id",
            config.signal_date_key,
            "factor_source_date",
        ],
        kind="stable",
    )
    joined = joined.drop_duplicates(
        [config.stock_key, "factor_id", config.signal_date_key],
        keep="last",
    )
    mapping = dataset.factor_crosswalk.table.loc[
        dataset.factor_crosswalk.table["mapping_status"].eq("mapped"),
        ["factor_id", "family", "crosswalk_sha256"],
    ]
    joined = joined.merge(
        mapping,
        on="factor_id",
        how="inner",
        validate="many_to_one",
    )
    joined["crosswalk_sha256"] = joined["crosswalk_sha256"].fillna(
        dataset.factor_crosswalk.sha256
    )
    if joined.empty:
        raise FormalDataUnavailableError(
            "固定因子集与 AS26 映射、股票月面板没有共同正式观测"
        )
    if not joined["crosswalk_sha256"].eq(dataset.factor_crosswalk.sha256).all():
        raise M2ContractError("m2 面板出现预测期 AS26 哈希漂移")
    if (
        joined["forward_return_date"].notna()
        & joined["forward_return_date"].le(joined[config.signal_date_key])
    ).any():
        raise M2ContractError("m2 面板出现 T+1 收益实现日不晚于信号日")
    return joined.sort_values(
        [config.signal_date_key, "factor_id", config.stock_key],
        kind="stable",
    ).reset_index(drop=True)


def preprocess_factor_cross_sections(
    panel: pd.DataFrame,
    *,
    factor_value_column: str = "factor_value",
    signal_date_column: str = "signal_date",
    lower_quantile: float = 0.01,
    upper_quantile: float = 0.99,
    score_column: str = "factor_score",
    minimum_cross_section: int = 5,
) -> pd.DataFrame:
    """按 AS11 对每个 factor-month 做 1%/99% 缩尾和 z-score。"""
    if not 0.0 <= lower_quantile < upper_quantile <= 1.0:
        raise M2ContractError("缩尾分位必须满足 0 <= lower < upper <= 1")
    if minimum_cross_section < 2:
        raise M2ContractError("minimum_cross_section 必须至少为 2")
    _require_columns(
        panel,
        [
            "factor_id",
            signal_date_column,
            factor_value_column,
            "is_signal_eligible",
        ],
        label="因子预处理面板",
    )
    result = panel.loc[panel["is_signal_eligible"].fillna(False)].copy()
    result[factor_value_column] = _finite_numeric(result[factor_value_column])
    grouping = [signal_date_column, "factor_id"]
    valid_count = result.groupby(grouping, observed=True)[
        factor_value_column
    ].transform("count")
    result = result.loc[valid_count.ge(minimum_cross_section)].copy()
    grouped = result.groupby(grouping, observed=True)[factor_value_column]
    lower = grouped.transform(lambda values: values.quantile(lower_quantile))
    upper = grouped.transform(lambda values: values.quantile(upper_quantile))
    result["factor_winsorized"] = result[factor_value_column].clip(
        lower=lower, upper=upper
    )
    result[score_column] = result.groupby(grouping, observed=True)[
        "factor_winsorized"
    ].transform(standardize)
    result["cross_section_count"] = result.groupby(
        grouping, observed=True
    )[score_column].transform("count")
    return result.reset_index(drop=True)


def calculate_monthly_factor_ic(
    panel: pd.DataFrame,
    *,
    score_column: str = "directed_score",
    return_column: str = "forward_return",
    signal_date_column: str = "signal_date",
) -> pd.DataFrame:
    """复用 common 计算逐 factor-month Pearson IC 与 Rank IC。"""
    _require_columns(
        panel,
        ["factor_id", "family", signal_date_column, score_column, return_column],
        label="IC 面板",
    )

    def _one_cross_section(group: pd.DataFrame) -> pd.Series:
        return pd.Series(
            {
                "ic": calculate_ic(group[score_column], group[return_column]),
                "rank_ic": calculate_rank_ic(
                    group[score_column], group[return_column]
                ),
                "stocks": int(
                    group[[score_column, return_column]].dropna().shape[0]
                ),
            }
        )

    return (
        panel.groupby(
            [signal_date_column, "factor_id", "family"],
            observed=True,
        )
        .apply(_one_cross_section, include_groups=False)
        .reset_index()
        .sort_values([signal_date_column, "factor_id"], kind="stable")
        .reset_index(drop=True)
    )


def _adapt_direction_crosswalk(
    scored_panel: pd.DataFrame,
    crosswalk_sha256: str,
    crosswalk: FactorCrosswalkResult | None,
) -> FactorCrosswalkResult:
    """把 m2 固定因子子集适配成 m1 方向 API 所需的映射视图。"""
    if not crosswalk_sha256:
        raise M2ContractError("方向冻结必须提供 AS26 crosswalk_sha256")
    _require_columns(
        scored_panel,
        ["factor_id", "family"],
        label="方向交叉表适配面板",
    )
    observed = scored_panel[["factor_id", "family"]].drop_duplicates().copy()
    observed["factor_id"] = observed["factor_id"].astype(str)
    family_counts = observed.groupby("factor_id", observed=True)["family"].nunique()
    if family_counts.gt(1).any():
        conflicting = family_counts.index[family_counts.gt(1)].tolist()
        raise M2ContractError(f"因子出现多个家族归属: {conflicting[:10]}")
    if crosswalk is None:
        table = observed.assign(mapping_status="mapped")
    else:
        if crosswalk.sha256 != crosswalk_sha256:
            raise M2ContractError(
                "方向适配的 AS26 哈希不一致："
                f"expected={crosswalk_sha256}, actual={crosswalk.sha256}"
            )
        _require_columns(
            crosswalk.table,
            ["factor_id", "family", "mapping_status"],
            label="m1 方向交叉表",
        )
        factor_ids = set(observed["factor_id"])
        table = crosswalk.table.loc[
            crosswalk.table["factor_id"].astype(str).isin(factor_ids)
            & crosswalk.table["mapping_status"].eq("mapped")
        ].copy()
        table["factor_id"] = table["factor_id"].astype(str)
        mapped_ids = set(table["factor_id"])
        missing = sorted(factor_ids.difference(mapped_ids))
        if missing:
            raise FormalDataUnavailableError(
                f"固定因子没有 AS26 映射: {missing[:10]}"
            )
        family_check = observed.merge(
            table[["factor_id", "family"]],
            on="factor_id",
            how="left",
            suffixes=("_panel", "_crosswalk"),
            validate="one_to_one",
        )
        mismatch = family_check["family_panel"].ne(
            family_check["family_crosswalk"]
        )
        if mismatch.any():
            raise M2ContractError(
                "m2 面板家族与 AS26 交叉表不一致: "
                f"{family_check.loc[mismatch, 'factor_id'].tolist()[:10]}"
            )
    return FactorCrosswalkResult(
        table=table.sort_values("factor_id", kind="stable").reset_index(drop=True),
        summary=pd.DataFrame(),
        sha256=crosswalk_sha256,
    )


def fit_frozen_factor_directions(
    scored_panel: pd.DataFrame,
    walk_forward_windows: pd.DataFrame,
    prediction_year: int | None = None,
    *,
    crosswalk_sha256: str,
    window_id: str | None = None,
    crosswalk: FactorCrosswalkResult | None = None,
    score_column: str = "factor_score",
    return_column: str = "forward_return",
    signal_date_column: str = "signal_date",
    realization_date_column: str = "forward_return_date",
    zero_ic_direction: int | None = None,
    hash_encoding: str | None = None,
    config: R006M1Config = DEFAULT_CONFIG,
) -> FrozenDirections:
    """兼容 m2 旧函数名，内部委托 m1 authoritative 方向冻结 API。"""
    if zero_ic_direction is not None:
        raise M2ContractError(
            "zero_ic_direction 不得覆盖 m1 authoritative direction_zero_policy"
        )
    if hash_encoding is not None and hash_encoding != config.hash_encoding:
        raise M2ContractError(
            "hash_encoding 不得覆盖 m1 authoritative 哈希编码"
        )
    _require_columns(
        scored_panel,
        [
            config.stock_key,
            "factor_id",
            "family",
            score_column,
            return_column,
            signal_date_column,
            realization_date_column,
        ],
        label="方向估计面板",
    )
    window = select_walk_forward_window(
        walk_forward_windows,
        prediction_year,
        window_id=window_id,
    )
    adapted_crosswalk = _adapt_direction_crosswalk(
        scored_panel,
        crosswalk_sha256,
        crosswalk,
    )
    authoritative_panel = scored_panel.copy()
    authoritative_panel[config.signal_date_key] = pd.to_datetime(
        authoritative_panel[signal_date_column], errors="coerce"
    )
    authoritative_panel["forward_return_date"] = pd.to_datetime(
        authoritative_panel[realization_date_column], errors="coerce"
    )
    authoritative_panel["factor_value"] = _finite_numeric(
        authoritative_panel[score_column]
    )
    authoritative_panel["forward_return"] = _finite_numeric(
        authoritative_panel[return_column]
    )
    authoritative = fit_annual_frozen_factor_directions(
        authoritative_panel,
        adapted_crosswalk,
        walk_forward_windows,
        config=config,
        window_id=str(window["window_id"]),
    )
    family_map = adapted_crosswalk.table[["factor_id", "family"]]
    table = authoritative.table.merge(
        family_map,
        on="factor_id",
        how="left",
        validate="one_to_one",
    ).rename(
        columns={
            "direction_estimate": "train_mean_ic",
            "estimation_months": "train_ic_months",
        }
    )
    table["direction_sha256"] = authoritative.sha256
    return FrozenDirections(
        table=table.sort_values("factor_id", kind="stable").reset_index(drop=True),
        sha256=authoritative.sha256,
        crosswalk_sha256=authoritative.crosswalk_sha256,
        window_id=authoritative.window_id,
        prediction_year=authoritative.prediction_year,
        prediction_start=authoritative.prediction_start,
        prediction_end=authoritative.prediction_end,
        train_start=authoritative.train_start,
        train_end=authoritative.train_end,
        authoritative=authoritative,
    )


def apply_frozen_factor_directions(
    scored_panel: pd.DataFrame,
    directions: FrozenDirections,
    *,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    score_column: str = "factor_score",
    output_column: str = "directed_score",
    signal_date_column: str = "signal_date",
    config: R006M1Config = DEFAULT_CONFIG,
) -> pd.DataFrame:
    """按月度 Period 切片后委托 m1 应用完整预测块方向。"""
    start_period = pd.Timestamp(
        start_date if start_date is not None else directions.prediction_start
    ).to_period("M")
    end_period = pd.Timestamp(
        end_date if end_date is not None else directions.prediction_end
    ).to_period("M")
    if end_period < start_period:
        raise M2ContractError("方向应用 end_date 早于 start_date")
    prediction_start_period = directions.prediction_start.to_period("M")
    prediction_end_period = directions.prediction_end.to_period("M")
    if (
        start_period < prediction_start_period
        or end_period > prediction_end_period
    ):
        raise M2ContractError(
            f"方向冻结表 {directions.window_id} 不能应用于窗口外月份"
        )
    _require_columns(
        scored_panel,
        ["factor_id", "family", signal_date_column, score_column],
        label="方向应用面板",
    )
    signal_dates = pd.to_datetime(
        scored_panel[signal_date_column], errors="coerce"
    )
    signal_periods = signal_dates.dt.to_period("M")
    sample = scored_panel.loc[
        signal_periods.ge(start_period) & signal_periods.le(end_period)
    ].copy()
    if sample.empty:
        raise FormalDataUnavailableError("方向冻结区间没有可用因子观测")
    sample[config.signal_date_key] = signal_dates.loc[sample.index]
    if "factor_value" in sample.columns:
        sample["_m2_original_factor_value"] = sample["factor_value"]
    sample["factor_value"] = _finite_numeric(sample[score_column])
    output = apply_annual_frozen_factor_directions(
        sample,
        directions.authoritative,
        config,
    )
    output[output_column] = output["directed_factor_value"]
    if "_m2_original_factor_value" in output.columns:
        output["factor_value"] = output.pop("_m2_original_factor_value")
    output["crosswalk_sha256"] = directions.crosswalk_sha256
    if not output["direction_sha256"].eq(directions.sha256).all():
        raise M2ContractError("方向哈希在冻结区间漂移")
    if not output["crosswalk_sha256"].eq(directions.crosswalk_sha256).all():
        raise M2ContractError("AS26 哈希在方向冻结区间漂移")
    return output.reset_index(drop=True)


def newey_west_ols(
    dependent: pd.Series,
    regressors: pd.DataFrame,
    *,
    lag: int = 6,
    add_intercept: bool = True,
    intercept_name: str = "alpha",
) -> NeweyWestResult:
    """以 Bartlett 核计算月度 OLS 的 Newey–West HAC 协方差。"""
    if lag < 0:
        raise M2ContractError("Newey-West lag 不能为负")
    y = _finite_numeric(dependent).rename("_dependent")
    x = regressors.copy()
    x = x.apply(_finite_numeric)
    data = pd.concat([y, x], axis=1).dropna()
    if add_intercept:
        x_columns = [intercept_name, *x.columns.tolist()]
        matrix = np.column_stack(
            [np.ones(len(data), dtype=float), data[x.columns].to_numpy(dtype=float)]
        )
    else:
        x_columns = x.columns.tolist()
        matrix = data[x.columns].to_numpy(dtype=float)
    response = data["_dependent"].to_numpy(dtype=float)
    observations, parameters = matrix.shape
    if parameters == 0:
        raise M2ContractError("Newey-West 回归没有解释变量")
    if observations <= parameters:
        raise M2ContractError(
            f"Newey-West 有效样本 {observations} <= 参数数 {parameters}"
        )
    if np.linalg.matrix_rank(matrix) < parameters:
        raise M2ContractError("Newey-West 设计矩阵不满秩")
    beta = np.linalg.lstsq(matrix, response, rcond=None)[0]
    fitted_values = matrix @ beta
    residual_values = response - fitted_values
    scores = matrix * residual_values[:, None]
    meat = scores.T @ scores
    effective_lag = min(int(lag), observations - 1)
    for offset in range(1, effective_lag + 1):
        bartlett_weight = 1.0 - offset / (effective_lag + 1.0)
        cross = scores[offset:].T @ scores[:-offset]
        meat += bartlett_weight * (cross + cross.T)
    bread = np.linalg.pinv(matrix.T @ matrix)
    covariance_values = bread @ meat @ bread
    standard_errors = np.sqrt(
        np.clip(np.diag(covariance_values), a_min=0.0, a_max=None)
    )
    t_statistics = np.divide(
        beta,
        standard_errors,
        out=np.full_like(beta, np.nan),
        where=standard_errors > 0.0,
    )
    coefficient_table = pd.DataFrame(
        {
            "coefficient": x_columns,
            "estimate": beta,
            "nw_standard_error": standard_errors,
            "nw_t": t_statistics,
            "lag": effective_lag,
            "observations": observations,
        }
    )
    covariance = pd.DataFrame(
        covariance_values,
        index=x_columns,
        columns=x_columns,
    )
    return NeweyWestResult(
        coefficients=coefficient_table,
        covariance=covariance,
        fitted=pd.Series(fitted_values, index=data.index, name="fitted"),
        residuals=pd.Series(residual_values, index=data.index, name="residual"),
        lag=effective_lag,
        observations=observations,
    )


def newey_west_mean_sensitivity(
    values: pd.Series,
    *,
    lags: Sequence[int] = (3, 6, 12),
    coefficient_name: str = "mean",
) -> pd.DataFrame:
    """按 AS13 同时报 lag=3/6/12 的月度均值与 NW t。"""
    rows: list[pd.DataFrame] = []
    for lag in lags:
        result = newey_west_ols(
            values,
            pd.DataFrame(index=values.index),
            lag=int(lag),
            add_intercept=True,
            intercept_name=coefficient_name,
        )
        rows.append(result.coefficients)
    return pd.concat(rows, ignore_index=True)


def prepare_fama_macbeth_controls(
    panel: pd.DataFrame,
    *,
    market_cap_column: str = "negotiable_market_value",
    book_to_market_column: str = "book_to_market",
    momentum_column: str = "momentum_12_1",
    beta_column: str = "historical_beta",
    log_market_cap_column: str = "log_negotiable_market_value",
    log_book_to_market_column: str = "log_book_to_market",
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """构造 AS13 的本地 FMB 控制接口。

    ``book_to_market``、``momentum_12_1`` 与 ``historical_beta`` 必须由调用方
    以 T 时点可得数据提供；本函数只做固定对数变换和字段审计，不猜测缺失代理。
    """
    required = {
        market_cap_column,
        book_to_market_column,
        momentum_column,
        beta_column,
    }
    _require_columns(panel, required, label="Fama-MacBeth 控制面板")
    result = panel.copy()
    market_cap = _finite_numeric(result[market_cap_column])
    book_to_market = _finite_numeric(result[book_to_market_column])
    result[log_market_cap_column] = np.log(market_cap.where(market_cap.gt(0.0)))
    result[log_book_to_market_column] = np.log(
        book_to_market.where(book_to_market.gt(0.0))
    )
    result[momentum_column] = _finite_numeric(result[momentum_column])
    result[beta_column] = _finite_numeric(result[beta_column])
    return result, (
        log_market_cap_column,
        log_book_to_market_column,
        momentum_column,
        beta_column,
    )


def fama_macbeth_regression(
    panel: pd.DataFrame,
    *,
    signal_column: str = "directed_score",
    return_column: str = "forward_return",
    control_columns: Sequence[str] = (
        "log_negotiable_market_value",
        "log_book_to_market",
        "momentum_12_1",
        "historical_beta",
    ),
    signal_date_column: str = "signal_date",
    nw_lags: Sequence[int] = (3, 6, 12),
    intercept_name: str = "intercept",
) -> FamaMacBethResult:
    """逐月横截面 OLS 后，对月度斜率做 Newey–West 推断。"""
    regressors = [signal_column, *control_columns]
    _require_columns(
        panel,
        [signal_date_column, return_column, *regressors],
        label="Fama-MacBeth 面板",
    )

    def _monthly_ols(group: pd.DataFrame) -> pd.Series:
        data = group[[return_column, *regressors]].apply(
            _finite_numeric
        ).dropna()
        matrix = np.column_stack(
            [
                np.ones(len(data), dtype=float),
                data[regressors].to_numpy(dtype=float),
            ]
        )
        parameter_names = [intercept_name, *regressors]
        if (
            len(data) <= len(parameter_names)
            or np.linalg.matrix_rank(matrix) < len(parameter_names)
        ):
            return pd.Series(
                {**{name: np.nan for name in parameter_names}, "stocks": len(data)}
            )
        beta = np.linalg.lstsq(
            matrix,
            data[return_column].to_numpy(dtype=float),
            rcond=None,
        )[0]
        return pd.Series(
            {
                **dict(zip(parameter_names, beta, strict=True)),
                "stocks": len(data),
            }
        )

    monthly = (
        panel.groupby(signal_date_column, observed=True)
        .apply(_monthly_ols, include_groups=False)
        .reset_index()
        .sort_values(signal_date_column, kind="stable")
        .reset_index(drop=True)
    )
    summary_rows: list[pd.DataFrame] = []
    for coefficient in [intercept_name, *regressors]:
        for lag in nw_lags:
            finite = _finite_numeric(monthly[coefficient]).dropna()
            if len(finite) <= 1:
                summary_rows.append(
                    pd.DataFrame(
                        {
                            "coefficient": [coefficient],
                            "estimate": [np.nan],
                            "nw_standard_error": [np.nan],
                            "nw_t": [np.nan],
                            "lag": [int(lag)],
                            "observations": [len(finite)],
                        }
                    )
                )
                continue
            estimate = newey_west_ols(
                finite,
                pd.DataFrame(index=finite.index),
                lag=int(lag),
                add_intercept=True,
                intercept_name=coefficient,
            ).coefficients
            summary_rows.append(estimate)
    return FamaMacBethResult(
        monthly_coefficients=monthly,
        summary=pd.concat(summary_rows, ignore_index=True),
    )


def validate_ashare_six_factor_returns(
    factor_returns: pd.DataFrame,
    *,
    date_column: str = "date",
    factor_columns: Sequence[str] = (
        "MKT",
        "SMB",
        "HML",
        "RMW",
        "CMA",
        "MOM",
    ),
) -> pd.DataFrame:
    """验证 AS8 的A股市场/规模/价值/盈利/投资/动量收益接口。"""
    _require_columns(
        factor_returns,
        [date_column, *factor_columns],
        label="A股六因子收益",
    )
    result = factor_returns[[date_column, *factor_columns]].copy()
    result[date_column] = pd.to_datetime(result[date_column], errors="coerce")
    for column in factor_columns:
        result[column] = _finite_numeric(result[column])
    if result[date_column].isna().any():
        raise M2ContractError("A股六因子 date 存在不可解析值")
    if result[date_column].duplicated().any():
        raise M2ContractError("A股六因子同月存在重复记录")
    return result.sort_values(date_column, kind="stable").reset_index(drop=True)


def estimate_six_factor_alpha(
    portfolio_returns: pd.DataFrame,
    six_factor_returns: pd.DataFrame,
    *,
    portfolio_return_column: str = "gross_return",
    portfolio_date_column: str = "forward_return_date",
    factor_date_column: str = "date",
    factor_columns: Sequence[str] = (
        "MKT",
        "SMB",
        "HML",
        "RMW",
        "CMA",
        "MOM",
    ),
    nw_lag: int = 6,
) -> NeweyWestResult:
    """估计 A股本地六因子调整 alpha；控制缺失时不填零。"""
    _require_columns(
        portfolio_returns,
        [portfolio_date_column, portfolio_return_column],
        label="待控组合收益",
    )
    controls = validate_ashare_six_factor_returns(
        six_factor_returns,
        date_column=factor_date_column,
        factor_columns=factor_columns,
    )
    merged = portfolio_returns[
        [portfolio_date_column, portfolio_return_column]
    ].merge(
        controls,
        left_on=portfolio_date_column,
        right_on=factor_date_column,
        how="inner",
        validate="one_to_one",
    )
    return newey_west_ols(
        merged[portfolio_return_column],
        merged[list(factor_columns)],
        lag=nw_lag,
        add_intercept=True,
        intercept_name="alpha",
    )


def assign_capacity_regions(
    panel: pd.DataFrame,
    *,
    signal_date_column: str = "signal_date",
    stock_column: str = "stock_code",
    market_cap_column: str = "negotiable_market_value",
    micro_cutoff: float = 0.20,
    upper_half_cutoff: float = 0.50,
    upper_third_cutoff: float = 2.0 / 3.0,
    large_cutoff: float = 0.80,
    mega_cutoff: float = 0.90,
) -> pd.DataFrame:
    """按 AS12/B13 生成八个可重叠容量区域的固定月度成员表。"""
    cutoffs = (
        micro_cutoff,
        upper_half_cutoff,
        upper_third_cutoff,
        large_cutoff,
        mega_cutoff,
    )
    if tuple(sorted(cutoffs)) != cutoffs or not all(
        0.0 < cutoff < 1.0 for cutoff in cutoffs
    ):
        raise M2ContractError("容量分位断点必须严格递增且位于 (0,1)")
    _require_columns(
        panel,
        [signal_date_column, stock_column, market_cap_column],
        label="容量分区面板",
    )
    base = panel[
        [signal_date_column, stock_column, market_cap_column]
    ].drop_duplicates([signal_date_column, stock_column]).copy()
    base[market_cap_column] = _finite_numeric(base[market_cap_column])
    base = base.loc[base[market_cap_column].gt(0.0)].copy()
    base["market_cap_percentile"] = base.groupby(
        signal_date_column, observed=True
    )[market_cap_column].rank(method="average", pct=True)
    percentile = base["market_cap_percentile"]
    definitions = (
        ("All firms", pd.Series(True, index=base.index)),
        ("Micro bottom 20", percentile.le(micro_cutoff)),
        ("Outside microcaps", percentile.gt(micro_cutoff)),
        (
            "Middle 60",
            percentile.gt(micro_cutoff) & percentile.le(large_cutoff),
        ),
        ("Upper half", percentile.gt(upper_half_cutoff)),
        ("Upper third", percentile.gt(upper_third_cutoff)),
        ("Large top 20", percentile.gt(large_cutoff)),
        ("Mega top 10", percentile.gt(mega_cutoff)),
    )
    parts = [
        base.loc[mask].assign(capacity_region=region)
        for region, mask in definitions
    ]
    return pd.concat(parts, ignore_index=True).sort_values(
        [signal_date_column, "capacity_region", stock_column],
        kind="stable",
    ).reset_index(drop=True)


def _calculate_one_way_turnover(
    weights: pd.DataFrame,
    *,
    group_columns: Sequence[str],
    signal_date_column: str,
    stock_column: str,
    weight_column: str,
    return_column: str,
) -> pd.DataFrame:
    """按 AS22 在目标权重与前期漂移权重间计算 ``0.5 * L1``。"""
    rows: list[dict[str, Any]] = []
    grouper: str | list[str] = (
        group_columns[0] if len(group_columns) == 1 else list(group_columns)
    )
    for group_key, group in weights.groupby(grouper, observed=True, sort=False):
        keys = group_key if isinstance(group_key, tuple) else (group_key,)
        dates = pd.DatetimeIndex(
            pd.to_datetime(group[signal_date_column]).drop_duplicates().sort_values()
        )
        stocks = sorted(group[stock_column].astype(str).unique())
        target = (
            group.pivot_table(
                index=signal_date_column,
                columns=stock_column,
                values=weight_column,
                aggfunc="sum",
                fill_value=0.0,
            )
            .reindex(index=dates, columns=stocks, fill_value=0.0)
            .astype(float)
        )
        realized = group.pivot_table(
            index=signal_date_column,
            columns=stock_column,
            values=return_column,
            aggfunc="last",
        ).reindex(index=dates, columns=stocks)
        prior_target: pd.Series | None = None
        prior_return: pd.Series | None = None
        prior_date: pd.Timestamp | None = None
        for signal_date in dates:
            current = target.loc[signal_date]
            if prior_target is None:
                turnover = 0.5 * float(current.abs().sum())
                status = "initial_build"
            elif (
                pd.Period(signal_date, freq="M")
                != pd.Period(prior_date, freq="M") + 1
            ):
                turnover = np.nan
                status = "non_consecutive_month"
            elif (
                prior_return is None
                or prior_return.loc[prior_target.ne(0.0)].isna().any()
            ):
                turnover = np.nan
                status = "missing_prior_constituent_return"
            else:
                growth = prior_target * (1.0 + prior_return.fillna(0.0))
                long_exposure = float(prior_target.clip(lower=0.0).sum())
                short_exposure = float((-prior_target.clip(upper=0.0)).sum())
                drift_long = growth.clip(lower=0.0)
                drift_short = growth.clip(upper=0.0)
                if drift_long.sum() > 0.0:
                    drift_long *= long_exposure / drift_long.sum()
                if -drift_short.sum() > 0.0:
                    drift_short *= short_exposure / (-drift_short.sum())
                drift = drift_long + drift_short
                turnover = 0.5 * float((current - drift).abs().sum())
                status = "calculated"
            rows.append(
                {
                    **dict(zip(group_columns, keys, strict=True)),
                    signal_date_column: signal_date,
                    "turnover": turnover,
                    "turnover_status": status,
                }
            )
            prior_target = current
            prior_return = realized.loc[signal_date]
            prior_date = pd.Timestamp(signal_date)
    return pd.DataFrame(rows)


def apply_cost_sensitivity(
    returns: pd.DataFrame,
    *,
    cost_bps_values: Sequence[float] = (10.0, 30.0),
    gross_return_column: str = "gross_return",
    turnover_column: str = "turnover",
) -> pd.DataFrame:
    """按 AS22 的单边成本在实际一边换手上计提净收益。"""
    _require_columns(
        returns,
        [gross_return_column, turnover_column],
        label="成本敏感性收益",
    )
    parts: list[pd.DataFrame] = []
    for cost_bps in cost_bps_values:
        if cost_bps < 0.0:
            raise M2ContractError("交易成本 bps 不能为负")
        part = returns.copy()
        part["cost_bps"] = float(cost_bps)
        part["transaction_cost"] = (
            part[turnover_column] * float(cost_bps) / 10_000.0
        )
        part["net_return"] = (
            part[gross_return_column] - part["transaction_cost"]
        )
        parts.append(part)
    if not parts:
        return pd.DataFrame(
            columns=[
                *returns.columns,
                "cost_bps",
                "transaction_cost",
                "net_return",
            ]
        )
    return pd.concat(parts, ignore_index=True)


def build_factor_decile_layer(
    directed_panel: pd.DataFrame,
    *,
    score_column: str = "directed_score",
    return_column: str = "forward_return",
    signal_date_column: str = "signal_date",
    return_date_column: str = "forward_return_date",
    stock_column: str = "stock_code",
    market_cap_column: str = "negotiable_market_value",
    n_quantiles: int = 10,
    weighting_schemes: Sequence[str] = ("EW", "VW"),
    cost_bps_values: Sequence[float] = (10.0, 30.0),
) -> PortfolioLayer:
    """形成逐因子月度十分位 EW/VW 多空权重、收益、换手与成本。"""
    if n_quantiles < 2:
        raise M2ContractError("n_quantiles 必须至少为 2")
    if set(weighting_schemes).difference({"EW", "VW"}):
        raise M2ContractError("weighting_schemes 只支持 EW/VW")
    required = {
        signal_date_column,
        "execution_date",
        return_date_column,
        stock_column,
        "factor_id",
        "family",
        score_column,
        return_column,
        market_cap_column,
        "execution_buyable",
        "execution_sellable",
        "crosswalk_sha256",
        "direction_sha256",
    }
    _require_columns(directed_panel, required, label="十分位因子面板")
    panel = directed_panel.copy()
    panel[signal_date_column] = pd.to_datetime(
        panel[signal_date_column], errors="coerce"
    )
    panel[return_date_column] = pd.to_datetime(
        panel[return_date_column], errors="coerce"
    )
    if (
        panel[return_date_column].notna()
        & panel[return_date_column].le(panel[signal_date_column])
    ).any():
        raise M2ContractError("十分位组合出现 T+1 收益日期不晚于信号日期")
    panel["_portfolio_key"] = (
        panel[signal_date_column].astype("int64").astype(str)
        + "::"
        + panel["factor_id"].astype(str)
    )
    cross_count = panel.groupby("_portfolio_key", observed=True)[
        score_column
    ].transform("count")
    panel = panel.loc[cross_count.ge(n_quantiles)].copy()
    if panel.empty:
        raise FormalDataUnavailableError(
            f"没有横截面样本数达到 {n_quantiles} 的 factor-month"
        )
    grouped = assign_quantile_groups(
        panel,
        factor_col=score_column,
        date_col="_portfolio_key",
        n_groups=n_quantiles,
        group_col="quantile",
    )
    leg = grouped.loc[
        grouped["quantile"].isin([1, n_quantiles])
    ].copy()
    long_mask = leg["quantile"].eq(n_quantiles)
    short_mask = leg["quantile"].eq(1)
    leg["execution_eligible"] = (
        long_mask & leg["execution_buyable"].fillna(False)
    ) | (
        short_mask & leg["execution_sellable"].fillna(False)
    )
    leg = leg.loc[leg["execution_eligible"]].copy()
    leg["leg_sign"] = np.where(long_mask.loc[leg.index], 1.0, -1.0)
    leg_group = [signal_date_column, "factor_id", "quantile"]
    weight_parts: list[pd.DataFrame] = []
    if "EW" in weighting_schemes:
        equal = leg.copy()
        equal["_leg_denominator"] = equal.groupby(
            leg_group, observed=True
        )[stock_column].transform("count")
        equal["target_weight"] = (
            equal["leg_sign"] / equal["_leg_denominator"]
        )
        equal["weighting"] = "EW"
        weight_parts.append(equal)
    if "VW" in weighting_schemes:
        value = leg.loc[_finite_numeric(leg[market_cap_column]).gt(0.0)].copy()
        value["_leg_denominator"] = value.groupby(
            leg_group, observed=True
        )[market_cap_column].transform("sum")
        value["target_weight"] = (
            value["leg_sign"]
            * value[market_cap_column]
            / value["_leg_denominator"]
        )
        value["weighting"] = "VW"
        weight_parts.append(value)
    weights = pd.concat(weight_parts, ignore_index=True)
    valid_legs = (
        weights.groupby(
            [signal_date_column, "factor_id", "weighting"],
            observed=True,
        )["quantile"]
        .nunique()
        .eq(2)
        .rename("_valid_two_legs")
        .reset_index()
    )
    weights = weights.merge(
        valid_legs,
        on=[signal_date_column, "factor_id", "weighting"],
        how="left",
        validate="many_to_one",
    )
    weights = weights.loc[weights["_valid_two_legs"]].copy()
    if weights.empty:
        raise FormalDataUnavailableError(
            "执行限制后没有同时包含十分位高低两腿的因子组合"
        )
    weights["weighted_return"] = (
        weights["target_weight"] * weights[return_column]
    )
    weights["missing_return_weight"] = weights["target_weight"].abs().where(
        weights[return_column].isna(), 0.0
    )
    portfolio_group = [
        signal_date_column,
        "factor_id",
        "family",
        "weighting",
        "crosswalk_sha256",
        "direction_sha256",
    ]
    returns = (
        weights.groupby(portfolio_group, observed=True)
        .agg(
            execution_date=("execution_date", "first"),
            forward_return_date=(return_date_column, "first"),
            gross_return=("weighted_return", lambda values: values.sum(min_count=1)),
            missing_return_weight=("missing_return_weight", "sum"),
            long_stocks=("leg_sign", lambda values: int(values.gt(0.0).sum())),
            short_stocks=("leg_sign", lambda values: int(values.lt(0.0).sum())),
            target_gross_exposure=("target_weight", lambda values: values.abs().sum()),
        )
        .reset_index()
    )
    returns.loc[returns["missing_return_weight"].gt(0.0), "gross_return"] = np.nan
    turnover = _calculate_one_way_turnover(
        weights,
        group_columns=["factor_id", "weighting"],
        signal_date_column=signal_date_column,
        stock_column=stock_column,
        weight_column="target_weight",
        return_column=return_column,
    )
    returns = returns.merge(
        turnover,
        on=["factor_id", "weighting", signal_date_column],
        how="left",
        validate="one_to_one",
    )
    costs = apply_cost_sensitivity(
        returns,
        cost_bps_values=cost_bps_values,
    )
    keep = [
        signal_date_column,
        "execution_date",
        return_date_column,
        stock_column,
        "factor_id",
        "family",
        "weighting",
        "quantile",
        "target_weight",
        return_column,
        market_cap_column,
        "crosswalk_sha256",
        "direction_sha256",
    ]
    return PortfolioLayer(
        weights=weights[keep].sort_values(
            [signal_date_column, "factor_id", "weighting", stock_column],
            kind="stable",
        ).reset_index(drop=True),
        returns=returns.sort_values(
            [signal_date_column, "factor_id", "weighting"],
            kind="stable",
        ).reset_index(drop=True),
        cost_sensitivity=costs.sort_values(
            [signal_date_column, "factor_id", "weighting", "cost_bps"],
            kind="stable",
        ).reset_index(drop=True),
    )


def aggregate_family_sleeve_layer(
    factor_layer: PortfolioLayer,
    *,
    signal_date_column: str = "signal_date",
    return_date_column: str = "forward_return_date",
    stock_column: str = "stock_code",
    return_column: str = "forward_return",
    cost_bps_values: Sequence[float] = (10.0, 30.0),
) -> PortfolioLayer:
    """家族内等权聚合底层因子目标权重并重算收益和实际换手。"""
    weights = factor_layer.weights.copy()
    _require_columns(
        weights,
        [
            signal_date_column,
            return_date_column,
            stock_column,
            "factor_id",
            "family",
            "weighting",
            "target_weight",
            return_column,
            "crosswalk_sha256",
            "direction_sha256",
        ],
        label="因子层权重",
    )
    factor_counts = (
        weights.groupby(
            [signal_date_column, "family", "weighting"],
            observed=True,
        )["factor_id"]
        .nunique()
        .rename("signals")
        .reset_index()
    )
    weights = weights.merge(
        factor_counts,
        on=[signal_date_column, "family", "weighting"],
        how="left",
        validate="many_to_one",
    )
    weights["_family_factor_weight"] = (
        weights["target_weight"] / weights["signals"]
    )
    family_weight_group = [
        signal_date_column,
        "execution_date",
        return_date_column,
        stock_column,
        "family",
        "weighting",
        "crosswalk_sha256",
        "direction_sha256",
        "signals",
    ]
    family_weights = (
        weights.groupby(family_weight_group, observed=True)
        .agg(
            target_weight=("_family_factor_weight", "sum"),
            forward_return=(return_column, "last"),
            contributing_factor_rows=("factor_id", "size"),
        )
        .reset_index()
    )
    family_weights["weighted_return"] = (
        family_weights["target_weight"] * family_weights["forward_return"]
    )
    family_weights["missing_return_weight"] = family_weights[
        "target_weight"
    ].abs().where(family_weights["forward_return"].isna(), 0.0)
    family_return_group = [
        signal_date_column,
        "family",
        "weighting",
        "crosswalk_sha256",
        "direction_sha256",
        "signals",
    ]
    family_returns = (
        family_weights.groupby(family_return_group, observed=True)
        .agg(
            execution_date=("execution_date", "first"),
            forward_return_date=(return_date_column, "first"),
            gross_return=("weighted_return", lambda values: values.sum(min_count=1)),
            missing_return_weight=("missing_return_weight", "sum"),
            target_gross_exposure=("target_weight", lambda values: values.abs().sum()),
            stocks=(stock_column, "nunique"),
        )
        .reset_index()
    )
    family_returns.loc[
        family_returns["missing_return_weight"].gt(0.0), "gross_return"
    ] = np.nan
    turnover = _calculate_one_way_turnover(
        family_weights,
        group_columns=["family", "weighting"],
        signal_date_column=signal_date_column,
        stock_column=stock_column,
        weight_column="target_weight",
        return_column="forward_return",
    )
    family_returns = family_returns.merge(
        turnover,
        on=["family", "weighting", signal_date_column],
        how="left",
        validate="one_to_one",
    )
    costs = apply_cost_sensitivity(
        family_returns,
        cost_bps_values=cost_bps_values,
    )
    return PortfolioLayer(
        weights=family_weights.sort_values(
            [signal_date_column, "family", "weighting", stock_column],
            kind="stable",
        ).reset_index(drop=True),
        returns=family_returns.sort_values(
            [signal_date_column, "family", "weighting"],
            kind="stable",
        ).reset_index(drop=True),
        cost_sensitivity=costs.sort_values(
            [signal_date_column, "family", "weighting", "cost_bps"],
            kind="stable",
        ).reset_index(drop=True),
    )


def summarize_family_signal_composition(
    factor_ic: pd.DataFrame,
    crosswalk: FactorCrosswalkResult,
    *,
    nw_lag: int = 6,
) -> pd.DataFrame:
    """生成 R25/IA.11 的本地可计算对齐表，不硬编码原文数值。"""
    _require_columns(
        factor_ic,
        ["signal_date", "factor_id", "family", "ic"],
        label="R25 因子 IC",
    )
    assert_frozen_crosswalk(crosswalk, crosswalk.sha256)
    factor_rows: list[dict[str, Any]] = []
    for (factor_id, family), group in factor_ic.groupby(
        ["factor_id", "family"], observed=True
    ):
        finite = _finite_numeric(group["ic"]).dropna()
        if len(finite) <= 1:
            nw_t = np.nan
            mean_ic = finite.mean() if not finite.empty else np.nan
        else:
            estimate = newey_west_ols(
                finite,
                pd.DataFrame(index=finite.index),
                lag=nw_lag,
                add_intercept=True,
                intercept_name="mean_ic",
            ).coefficients.iloc[0]
            mean_ic = float(estimate["estimate"])
            nw_t = float(estimate["nw_t"])
        factor_rows.append(
            {
                "factor_id": factor_id,
                "family": family,
                "factor_mean_ic": mean_ic,
                "factor_ic_nw_t": nw_t,
                "ic_months": len(finite),
            }
        )
    factor_summary = pd.DataFrame(factor_rows)
    family_monthly = (
        factor_ic.groupby(["signal_date", "family"], observed=True)["ic"]
        .mean()
        .reset_index()
    )
    rows: list[dict[str, Any]] = []
    mapped_counts = (
        crosswalk.table.loc[crosswalk.table["mapping_status"].eq("mapped")]
        .groupby("family", observed=True)["factor_id"]
        .nunique()
    )
    for family in DEFAULT_CONFIG.family_order:
        signal_stats = factor_summary.loc[factor_summary["family"].eq(family)]
        monthly = _finite_numeric(
            family_monthly.loc[
                family_monthly["family"].eq(family), "ic"
            ]
        ).dropna()
        if len(monthly) <= 1:
            average_ic = monthly.mean() if not monthly.empty else np.nan
            average_ic_t = np.nan
        else:
            estimate = newey_west_ols(
                monthly,
                pd.DataFrame(index=monthly.index),
                lag=nw_lag,
                add_intercept=True,
                intercept_name="average_ic",
            ).coefficients.iloc[0]
            average_ic = float(estimate["estimate"])
            average_ic_t = float(estimate["nw_t"])
        rows.append(
            {
                "family": family,
                "signals": int(mapped_counts.get(family, 0)),
                "signals_with_ic": int(signal_stats["factor_id"].nunique()),
                "average_ic": average_ic,
                "average_ic_nw_t": average_ic_t,
                "max_signal_nw_t": (
                    signal_stats["factor_ic_nw_t"].max()
                    if not signal_stats.empty
                    else np.nan
                ),
                "ic_months": len(monthly),
                "crosswalk_sha256": crosswalk.sha256,
                "alignment_scope": "A股本地方法对齐，非原文数值对齐",
            }
        )
    return pd.DataFrame(rows)


def summarize_family_sleeve_evidence(
    family_returns: pd.DataFrame,
    six_factor_returns: pd.DataFrame,
    *,
    nw_lag: int = 6,
    factor_columns: Sequence[str] = (
        "MKT",
        "SMB",
        "HML",
        "RMW",
        "CMA",
        "MOM",
    ),
) -> pd.DataFrame:
    """生成 R16/IA.7 的本地收益、NW、六因子 alpha 与换手对齐表。"""
    _require_columns(
        family_returns,
        [
            "family",
            "weighting",
            "forward_return_date",
            "gross_return",
            "turnover",
        ],
        label="R16 家族袖套收益",
    )
    controls = validate_ashare_six_factor_returns(
        six_factor_returns,
        factor_columns=factor_columns,
    )
    rows: list[dict[str, Any]] = []
    for (family, weighting), group in family_returns.groupby(
        ["family", "weighting"], observed=True
    ):
        monthly = group[
            ["forward_return_date", "gross_return", "turnover"]
        ].dropna(subset=["gross_return"])
        if len(monthly) <= len(factor_columns) + 1:
            raise FormalDataUnavailableError(
                f"{family}/{weighting} 有效月份不足以估计六因子 alpha"
            )
        mean_result = newey_west_ols(
            monthly["gross_return"],
            pd.DataFrame(index=monthly.index),
            lag=nw_lag,
            add_intercept=True,
            intercept_name="mean_return",
        ).coefficients.iloc[0]
        alpha_result = estimate_six_factor_alpha(
            monthly,
            controls,
            factor_columns=factor_columns,
            nw_lag=nw_lag,
        ).coefficients
        alpha = alpha_result.loc[
            alpha_result["coefficient"].eq("alpha")
        ].iloc[0]
        rows.append(
            {
                "family": family,
                "weighting": weighting,
                "mean_return": float(mean_result["estimate"]),
                "mean_return_nw_t": float(mean_result["nw_t"]),
                "six_factor_alpha": float(alpha["estimate"]),
                "six_factor_alpha_nw_t": float(alpha["nw_t"]),
                "average_one_way_turnover": float(monthly["turnover"].mean()),
                "months": len(monthly),
                "alignment_scope": "A股本地方法对齐，非原文数值对齐",
            }
        )
    return pd.DataFrame(rows)


def build_family_sleeves_for_window(
    dataset: M1Dataset,
    prediction_year: int | None = None,
    *,
    window_id: str | None = None,
    config: R006M1Config = DEFAULT_CONFIG,
    lower_quantile: float = 0.01,
    upper_quantile: float = 0.99,
    minimum_cross_section: int = 5,
    n_quantiles: int = 10,
    weighting_schemes: Sequence[str] = ("EW", "VW"),
    cost_bps_values: Sequence[float] = (10.0, 30.0),
    zero_ic_direction: int | None = None,
    nw_lag: int = 6,
) -> FamilySleeveAnalysis:
    """从正式 m1 合同构建一个 authoritative 12 月预测块的 m2 家族袖套。"""
    assembled = assemble_m2_factor_panel(dataset, config=config)
    scored = preprocess_factor_cross_sections(
        assembled,
        lower_quantile=lower_quantile,
        upper_quantile=upper_quantile,
        minimum_cross_section=minimum_cross_section,
    )
    directions = fit_frozen_factor_directions(
        scored,
        dataset.walk_forward_windows,
        prediction_year,
        crosswalk_sha256=dataset.factor_crosswalk.sha256,
        window_id=window_id,
        crosswalk=dataset.factor_crosswalk,
        zero_ic_direction=zero_ic_direction,
        config=config,
    )
    window = select_walk_forward_window(
        dataset.walk_forward_windows,
        window_id=directions.window_id,
    )
    directed = apply_frozen_factor_directions(
        scored,
        directions,
        start_date=pd.Timestamp(window["prediction_start"]),
        end_date=pd.Timestamp(window["prediction_end"]),
        config=config,
    )
    factor_ic = calculate_monthly_factor_ic(directed)
    family_ic = (
        factor_ic.groupby(["signal_date", "family"], observed=True)
        .agg(
            ic=("ic", "mean"),
            rank_ic=("rank_ic", "mean"),
            signals=("factor_id", "nunique"),
            stocks_min=("stocks", "min"),
        )
        .reset_index()
    )
    factor_layer = build_factor_decile_layer(
        directed,
        n_quantiles=n_quantiles,
        weighting_schemes=weighting_schemes,
        cost_bps_values=cost_bps_values,
    )
    family_layer = aggregate_family_sleeve_layer(
        factor_layer,
        cost_bps_values=cost_bps_values,
    )
    composition = summarize_family_signal_composition(
        factor_ic,
        dataset.factor_crosswalk,
        nw_lag=nw_lag,
    )
    coverage = (
        directed.groupby(["signal_date", "family"], observed=True)
        .agg(
            signals=("factor_id", "nunique"),
            stocks=("stock_code", "nunique"),
            observations=("factor_id", "size"),
            factor_source_max_date=("factor_source_date", "max"),
            signal_date_max=("signal_date", "max"),
            crosswalk_sha256=("crosswalk_sha256", "first"),
            direction_sha256=("direction_sha256", "first"),
        )
        .reset_index()
    )
    coverage["source_date_violation"] = coverage[
        "factor_source_max_date"
    ].gt(coverage["signal_date_max"])
    return FamilySleeveAnalysis(
        directions=directions,
        directed_panel=directed,
        factor_ic=factor_ic,
        family_ic=family_ic,
        factor_layer=factor_layer,
        family_layer=family_layer,
        family_composition=composition,
        coverage=coverage,
    )
