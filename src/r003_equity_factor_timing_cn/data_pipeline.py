"""m1：中国市场时点数据、宏观特征和金融湍流数据管线。

宏观变量统一通过 ``available_date`` 与月末信号日做 backward as-of join；
代码中没有反向填充。市场数据仅使用信号日及之前的观测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .config import ChinaFactorTimingConfig


@dataclass
class M1Dataset:
    """m1 后续模型可直接消费的数据合同。"""

    monthly_features: pd.DataFrame
    factor_returns: pd.DataFrame
    factor_constituents: pd.DataFrame
    financial_turbulence: pd.DataFrame
    availability_audit: pd.DataFrame
    data_quality: pd.DataFrame


def load_month_end_calendar(config: ChinaFactorTimingConfig) -> pd.DataFrame:
    """加载中国交易月末；同日多市场记录去重。"""
    cal = pd.read_parquet(
        config.path("calendar"),
        columns=["date", "IfTradingDay", "IfMonthEnd"],
        filters=[
            ("date", ">=", pd.Timestamp(config.sample_start)),
            ("date", "<=", pd.Timestamp(config.sample_end)),
        ],
    )
    cal["date"] = pd.to_datetime(cal["date"]).astype("datetime64[ns]").dt.normalize()
    cal = cal.loc[(cal["IfTradingDay"] == 1) & (cal["IfMonthEnd"] == 1), ["date"]]
    return cal.drop_duplicates().sort_values("date").rename(columns={"date": "signal_date"}).reset_index(drop=True)


def _conservative_available_date(
    source_date: pd.Series,
    release_date: pd.Series,
    lag_months: int,
) -> pd.Series:
    source_month_end = pd.to_datetime(source_date).dt.to_period("M").dt.to_timestamp("M")
    conservative = source_month_end + pd.offsets.MonthEnd(lag_months)
    release = pd.to_datetime(release_date, errors="coerce").dt.normalize()
    return pd.concat([conservative.rename("lag"), release.rename("release")], axis=1).max(axis=1)


def _read_macro_indicator(
    config: ChinaFactorTimingConfig,
    file_key: str,
    feature: str,
    code: int,
    lag_months: int,
) -> pd.DataFrame:
    raw = pd.read_parquet(
        config.path(file_key),
        columns=["date", "info_publ_date", "indicator_code", "data_value"],
        filters=[("indicator_code", "==", code)],
    ).rename(columns={"date": "source_date", "info_publ_date": "release_date", "data_value": "value"})
    raw["source_date"] = pd.to_datetime(raw["source_date"]).astype("datetime64[ns]").dt.normalize()
    raw["release_date"] = pd.to_datetime(raw["release_date"], errors="coerce").astype("datetime64[ns]")
    raw["available_date"] = _conservative_available_date(raw["source_date"], raw["release_date"], lag_months)
    raw["feature"] = feature
    raw["data_source"] = config.files[file_key]
    return raw[["feature", "value", "source_date", "release_date", "available_date", "data_source"]]


def _read_macro_cache(config: ChinaFactorTimingConfig, columns: tuple[str, ...]) -> pd.DataFrame:
    raw = pd.read_parquet(config.path("macro_cache"), columns=list(columns)).reset_index()
    raw = raw.rename(columns={raw.columns[0]: "source_date"})
    raw["source_date"] = pd.to_datetime(raw["source_date"]).astype("datetime64[ns]").dt.normalize()
    records: list[pd.DataFrame] = []
    for feature in columns:
        item = raw[["source_date", feature]].rename(columns={feature: "value"}).dropna(subset=["value"])
        item["release_date"] = pd.NaT
        item["available_date"] = _conservative_available_date(
            item["source_date"], item["release_date"], config.macro_monthly_lag_months
        )
        item["feature"] = feature
        item["data_source"] = config.files["macro_cache"]
        records.append(item[["feature", "value", "source_date", "release_date", "available_date", "data_source"]])
    return pd.concat(records, ignore_index=True)


def _read_shibor(config: ChinaFactorTimingConfig) -> pd.DataFrame:
    """读取同期限SHIBOR；市场日值在观测当日可得，不向过去回填。"""
    raw = pd.read_parquet(
        config.path("shibor"),
        columns=["date", "maturity_raw", "rate"],
        filters=[("maturity_raw", "==", config.shibor_maturity)],
    ).rename(columns={"date": "source_date", "rate": "value"})
    raw["source_date"] = pd.to_datetime(raw["source_date"]).astype("datetime64[ns]").dt.normalize()
    raw["release_date"] = raw["source_date"]
    raw["available_date"] = raw["source_date"]
    raw["feature"] = "shibor_1y"
    raw["data_source"] = config.files["shibor"]
    return raw[["feature", "value", "source_date", "release_date", "available_date", "data_source"]]


def _derived_feature_audit(
    base_audit: pd.DataFrame,
    feature_frame: pd.DataFrame,
    definitions: dict[str, tuple[str, ...]],
) -> pd.DataFrame:
    """为衍生字段传播最晚依赖日期，形成逐月可复核证据链。"""
    parts: list[pd.DataFrame] = []
    for feature, dependencies in definitions.items():
        provenance = (
            base_audit.loc[base_audit["feature"].isin(dependencies)]
            .groupby("signal_date", as_index=False)
            .agg(
                source_date=("source_date", "max"),
                release_date=("release_date", "max"),
                available_date=("available_date", "max"),
            )
        )
        item = feature_frame[["signal_date", feature]].rename(columns={feature: "value"}).merge(
            provenance,
            on="signal_date",
            how="left",
        )
        item["feature"] = feature
        item["data_source"] = "derived:" + "+".join(dependencies)
        parts.append(
            item[["signal_date", "feature", "value", "source_date", "release_date", "available_date", "data_source"]]
        )
    return pd.concat(parts, ignore_index=True)


def _asof_features(calendar: pd.DataFrame, events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    left = calendar.copy()
    left["signal_date"] = pd.to_datetime(left["signal_date"]).astype("datetime64[ns]")
    wide = left.copy()
    audit_parts: list[pd.DataFrame] = []
    for feature, group in events.groupby("feature", sort=False):
        right = (
            group.sort_values(["available_date", "source_date"])
            .drop_duplicates("available_date", keep="last")
        )
        right["available_date"] = pd.to_datetime(right["available_date"]).astype("datetime64[ns]")
        joined = pd.merge_asof(
            left.sort_values("signal_date"),
            right,
            left_on="signal_date",
            right_on="available_date",
            direction="backward",
        )
        wide[feature] = joined["value"].to_numpy()
        joined["feature"] = feature
        audit_parts.append(joined[["signal_date", "feature", "value", "source_date", "release_date", "available_date", "data_source"]])
    return wide, pd.concat(audit_parts, ignore_index=True)


def _historical_zscore(series: pd.Series, config: ChinaFactorTimingConfig) -> pd.Series:
    history = series.shift(1).rolling(
        config.rolling_standardization_months,
        min_periods=config.rolling_standardization_min_months,
    )
    mean = history.mean()
    std = history.std().replace(0.0, np.nan)
    return (series - mean) / std


def build_macro_features(
    config: ChinaFactorTimingConfig,
    calendar: pd.DataFrame,
    benchmark_features: pd.DataFrame | None = None,
    benchmark_audit: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """构造固定中国代理集合及发布日证据。"""
    if benchmark_features is None or benchmark_audit is None:
        benchmark_features, benchmark_audit = build_benchmark_features(config, calendar)
    c = config.macro_indicator_codes
    event_parts = [
        _read_macro_indicator(config, "macro_cpi", "cpi_yoy", c["cpi_yoy"], 1),
        _read_macro_indicator(config, "macro_cpi", "cpi_mom", c["cpi_mom"], 1),
        _read_macro_indicator(config, "macro_gdp", "gdp_real_yoy", c["gdp_real_yoy"], 2),
        _read_macro_indicator(config, "macro_gdp", "gdp_nominal", c["gdp_nominal"], 2),
        _read_macro_indicator(config, "macro_industrial", "industrial_prod_yoy", c["industrial_prod_yoy"], 1),
        _read_macro_indicator(config, "macro_lpr", "lpr_1y", c["lpr_1y"], 1),
        _read_macro_indicator(config, "macro_money", "m1_yoy", c["m1_yoy"], 1),
        _read_macro_indicator(config, "macro_money", "m2_yoy", c["m2_yoy"], 1),
        _read_macro_indicator(config, "macro_pmi", "manufacturing_pmi", c["manufacturing_pmi"], 1),
        _read_macro_cache(config, ("social_financing_yoy", "credit_spread", "term_spread", "bond_yield_10y")),
        _read_shibor(config),
    ]
    events = pd.concat(event_parts, ignore_index=True)

    # 用环比链成价格指数，再计算十年年化变化；可得日仍取本期CPI的保守可得日。
    mom = events.loc[events["feature"] == "cpi_mom"].sort_values("source_date").copy()
    mom["price_index"] = (1.0 + pd.to_numeric(mom["value"], errors="coerce") / 100.0).cumprod()
    mom["value"] = (mom["price_index"] / mom["price_index"].shift(120)).pow(0.1) - 1.0
    mom["feature"] = "cpi_10y_annualized"
    events = pd.concat([events, mom[events.columns]], ignore_index=True)

    macro, raw_audit = _asof_features(calendar, events)
    macro = macro.merge(
        benchmark_features[["signal_date", "equity_volatility"]],
        on="signal_date",
        how="left",
    )
    macro["gdp_nominal_yoy"] = macro["gdp_nominal"].pct_change(12) * 100.0
    macro["shibor_1y_change"] = macro["shibor_1y"].diff(config.policy_change_months)
    macro["lpr_1y_change"] = macro["lpr_1y"].diff(config.policy_change_months)
    macro["short_rate_proxy"] = macro["shibor_1y"].combine_first(macro["lpr_1y"])
    macro["short_rate_change"] = macro["shibor_1y_change"].combine_first(macro["lpr_1y_change"])
    z = {name: _historical_zscore(macro[name], config) for name in (
        "credit_spread", "term_spread", "bond_yield_10y", "m1_yoy", "m2_yoy",
        "social_financing_yoy", "gdp_nominal_yoy", "manufacturing_pmi",
        "gdp_real_yoy", "industrial_prod_yoy", "equity_volatility",
    )}
    macro["financial_risk"] = pd.concat(
        [z["credit_spread"], -z["term_spread"], z["bond_yield_10y"], z["equity_volatility"]], axis=1
    ).mean(axis=1, skipna=False)
    macro["credit_conditions"] = pd.concat(
        [-z["credit_spread"], z["m2_yoy"], z["social_financing_yoy"]], axis=1
    ).mean(axis=1, skipna=False)
    macro["leverage_conditions"] = (
        (macro["m2_yoy"] - macro["gdp_nominal_yoy"])
        + (macro["social_financing_yoy"] - macro["gdp_nominal_yoy"])
    ) / 2.0
    policy_parts = pd.concat(
        [
            -_historical_zscore(macro["short_rate_change"], config),
            -_historical_zscore(macro["term_spread"].diff(config.policy_change_months), config),
            _historical_zscore(macro["m1_yoy"].diff(config.policy_change_months), config),
            _historical_zscore(macro["m2_yoy"].diff(config.policy_change_months), config),
        ],
        axis=1,
    )
    macro["monetary_policy_expectations"] = policy_parts.mean(axis=1, skipna=False)
    growth_level = pd.concat(
        [
            _historical_zscore(macro["manufacturing_pmi"] - 50.0, config),
            z["gdp_real_yoy"],
            z["industrial_prod_yoy"],
        ],
        axis=1,
    ).mean(axis=1, skipna=False)
    macro["growth_level"] = growth_level
    macro["growth_direction"] = growth_level.diff(config.policy_change_months)
    macro["business_cycle"] = np.select(
        [
            (growth_level >= 0) & (macro["growth_direction"] >= 0),
            (growth_level >= 0) & (macro["growth_direction"] < 0),
            (growth_level < 0) & (macro["growth_direction"] < 0),
            (growth_level < 0) & (macro["growth_direction"] >= 0),
        ],
        ["Expansion", "Slowdown", "Contraction", "Recovery"],
        default=None,
    )
    base_audit = pd.concat(
        [
            raw_audit,
            benchmark_audit.loc[benchmark_audit["feature"] == "equity_volatility"],
        ],
        ignore_index=True,
    )
    definitions = {
        "gdp_nominal_yoy": ("gdp_nominal",),
        "shibor_1y_change": ("shibor_1y",),
        "lpr_1y_change": ("lpr_1y",),
        "short_rate_proxy": ("shibor_1y", "lpr_1y"),
        "short_rate_change": ("shibor_1y", "lpr_1y"),
        "financial_risk": ("credit_spread", "term_spread", "bond_yield_10y", "equity_volatility"),
        "credit_conditions": ("credit_spread", "m2_yoy", "social_financing_yoy"),
        "leverage_conditions": ("m2_yoy", "social_financing_yoy", "gdp_nominal"),
        "monetary_policy_expectations": ("shibor_1y", "lpr_1y", "term_spread", "m1_yoy", "m2_yoy"),
        "growth_level": ("manufacturing_pmi", "gdp_real_yoy", "industrial_prod_yoy"),
        "growth_direction": ("manufacturing_pmi", "gdp_real_yoy", "industrial_prod_yoy"),
        "business_cycle": ("manufacturing_pmi", "gdp_real_yoy", "industrial_prod_yoy"),
    }
    derived_audit = _derived_feature_audit(base_audit, macro, definitions)
    audit = pd.concat([raw_audit, derived_audit], ignore_index=True)
    return macro, audit


def build_benchmark_features(
    config: ChinaFactorTimingConfig,
    calendar: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """构造中证800价格、日度三月峰值回撤、波动率与估值历史分位。"""
    trade = pd.read_parquet(
        config.path("index_trade"),
        columns=["index_code", "date", "close", "pe"],
        filters=[("index_code", "==", config.benchmark_index_code), ("date", "<=", pd.Timestamp(config.sample_end))],
    )
    trade["date"] = pd.to_datetime(trade["date"]).astype("datetime64[ns]").dt.normalize()
    trade = trade.sort_values("date").drop_duplicates("date", keep="last")
    trade["daily_return"] = trade["close"].pct_change(fill_method=None)
    trade["equity_volatility"] = (
        trade["daily_return"]
        .rolling(
            config.benchmark_volatility_window_days,
            min_periods=config.benchmark_volatility_window_days,
        )
        .std()
        * np.sqrt(config.annual_trading_days)
    )
    monthly = trade.groupby(trade["date"].dt.to_period("M"), as_index=False).tail(1)
    monthly["benchmark_return"] = monthly["close"].pct_change()
    monthly["drawdown_3m"] = [
        row.close
        / trade.loc[
            trade["date"].between(
                row.date - pd.DateOffset(months=config.drawdown_window_months),
                row.date,
                inclusive="both",
            ),
            "close",
        ].max()
        - 1.0
        for row in monthly.itertuples(index=False)
    ]
    monthly["equity_ep"] = 1.0 / monthly["pe"].where(monthly["pe"] > 0)

    value = pd.read_parquet(
        config.path("index_value"),
        columns=["index_code", "date", "pb_lf"],
        filters=[("index_code", "==", config.benchmark_index_code), ("date", "<=", pd.Timestamp(config.sample_end))],
    )
    value["date"] = pd.to_datetime(value["date"]).astype("datetime64[ns]").dt.normalize()
    value = value.sort_values("date").groupby(value["date"].dt.to_period("M"), as_index=False).tail(1)
    monthly = pd.merge_asof(monthly.sort_values("date"), value[["date", "pb_lf"]].sort_values("date"), on="date", direction="backward")
    monthly["equity_ep_percentile"] = monthly["equity_ep"].expanding(
        config.valuation_percentile_min_months
    ).apply(lambda window: window.rank(pct=True).iloc[-1])
    monthly["equity_pb_percentile"] = monthly["pb_lf"].expanding(
        config.valuation_percentile_min_months
    ).apply(lambda window: window.rank(pct=True).iloc[-1])
    result = pd.merge_asof(calendar, monthly.sort_values("date"), left_on="signal_date", right_on="date", direction="backward")
    result = result[
        [
            "signal_date", "date", "close", "benchmark_return", "drawdown_3m",
            "equity_volatility", "equity_ep", "pb_lf", "equity_ep_percentile",
            "equity_pb_percentile",
        ]
    ].rename(columns={"close": "benchmark_close", "pb_lf": "equity_pb"})
    audit = result.melt(id_vars=["signal_date", "date"], var_name="feature", value_name="value")
    audit["source_date"] = audit["date"]
    audit["release_date"] = audit["date"]
    audit["available_date"] = audit["date"]
    audit["data_source"] = config.files["index_trade"] + "+" + config.files["index_value"]
    return result.drop(columns="date"), audit.drop(columns="date")


def build_bond_return_proxies(
    config: ChinaFactorTimingConfig,
    calendar: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """由国债收益率变化和久期一阶近似生成1Y/2Y/10Y月收益。"""
    interpolation_maturities = set(config.government_interpolation_sources)
    curve_maturities = sorted(set(config.government_maturities) | interpolation_maturities)
    curve = pd.read_parquet(
        config.path("yield_curve"),
        columns=["date", "curve_code", "years_to_maturity", "yield_type", "yield_value"],
        filters=[
            ("curve_code", "==", config.government_curve_code),
            ("years_to_maturity", "in", curve_maturities),
            ("date", "<=", pd.Timestamp(config.sample_end)),
        ],
    )
    curve["date"] = pd.to_datetime(curve["date"]).astype("datetime64[ns]").dt.normalize()
    curve = curve.loc[curve["yield_type"].astype(str).str.strip() == "到期"].copy()
    curve = curve.groupby(["date", "years_to_maturity"], as_index=False)["yield_value"].mean()
    curve["month"] = curve["date"].dt.to_period("M")
    calendar_map = calendar[["signal_date"]].copy()
    calendar_map["month"] = calendar_map["signal_date"].dt.to_period("M")
    curve = curve.merge(calendar_map, on="month", how="inner")
    curve = curve.loc[curve["date"] <= curve["signal_date"]]
    last = curve.sort_values("date").groupby(["signal_date", "years_to_maturity"], as_index=False).tail(1)
    levels = last.pivot(index="signal_date", columns="years_to_maturity", values="yield_value").sort_index()
    source_dates = last.pivot(index="signal_date", columns="years_to_maturity", values="date").sort_index()
    returns = pd.DataFrame(index=calendar["signal_date"])
    target = config.government_interpolation_target
    lower, upper = config.government_interpolation_sources
    target_level = levels[target].reindex(returns.index)
    lower_level = levels[lower].reindex(returns.index)
    upper_level = levels[upper].reindex(returns.index)
    interpolate_level = target_level.isna() & lower_level.notna() & upper_level.notna()
    interpolated_target = lower_level + (
        (target - lower) / (upper - lower)
    ) * (upper_level - lower_level)
    levels[target] = target_level.where(~interpolate_level, interpolated_target)
    lower_dates = source_dates[lower].reindex(returns.index)
    upper_dates = source_dates[upper].reindex(returns.index)
    interpolation_dates = pd.concat([lower_dates, upper_dates], axis=1).max(axis=1)
    source_dates[target] = source_dates[target].reindex(returns.index).where(
        ~interpolate_level,
        interpolation_dates,
    )
    for maturity in config.government_maturities:
        level = levels[maturity].reindex(returns.index) if maturity in levels else pd.Series(index=returns.index, dtype=float)
        returns[f"gov_bond_{int(maturity)}y_return"] = (
            -config.duration_by_maturity[maturity] * level.diff() / 100.0
        )
    return_columns = [f"gov_bond_{int(maturity)}y_return" for maturity in config.government_maturities]
    returns["is_interpolated_2y"] = interpolate_level | interpolate_level.shift(1, fill_value=False)
    returns["interpolated_2y_source_maturities"] = np.where(
        returns["is_interpolated_2y"],
        f"{int(lower)}Y|{int(upper)}Y",
        "",
    )
    returns["bond_common_available"] = returns[return_columns].notna().all(axis=1)
    result = calendar.merge(returns.reset_index(), on="signal_date", how="left")
    audit_parts: list[pd.DataFrame] = []
    for maturity in config.government_maturities:
        feature = f"gov_bond_{int(maturity)}y_return"
        item = result[["signal_date", feature]].rename(columns={feature: "value"})
        dates = source_dates[maturity].reindex(item["signal_date"]) if maturity in source_dates else pd.Series(pd.NaT, index=item["signal_date"])
        item["source_date"] = dates.to_numpy()
        item["release_date"] = item["source_date"]
        item["available_date"] = item["source_date"]
        item["feature"] = feature
        if maturity == target:
            item["data_source"] = np.where(
                result["is_interpolated_2y"],
                config.files["yield_curve"] + f":interpolated_{int(lower)}Y_{int(upper)}Y",
                config.files["yield_curve"],
            )
        else:
            item["data_source"] = config.files["yield_curve"]
        audit_parts.append(item)
    common = result[["signal_date", "bond_common_available"]].rename(columns={"bond_common_available": "value"})
    common["source_date"] = common["signal_date"]
    common["release_date"] = common["signal_date"]
    common["available_date"] = common["signal_date"]
    common["feature"] = "bond_common_available"
    common["data_source"] = config.files["yield_curve"]
    audit_parts.append(common)
    audit = pd.concat(audit_parts, ignore_index=True)[
        ["signal_date", "feature", "value", "source_date", "release_date", "available_date", "data_source"]
    ]
    return result, audit


def calculate_financial_turbulence(
    industry_returns: pd.DataFrame,
    bond_returns: pd.DataFrame,
    config: ChinaFactorTimingConfig,
) -> pd.DataFrame:
    """用严格过去窗口计算带岭项的马氏距离。"""
    industries = industry_returns.pivot(index="signal_date", columns="industry", values="industry_return")
    bonds = bond_returns.set_index("signal_date").filter(like="gov_bond_")
    vectors = industries.join(bonds, how="inner").sort_index()
    values: list[dict[str, Any]] = []
    for i, (date, row) in enumerate(vectors.iterrows()):
        window = vectors.iloc[max(0, i - config.turbulence_window_months):i]
        history = window.dropna()
        full_window = len(window) == config.turbulence_window_months
        complete_history = len(history) == config.turbulence_window_months
        complete_current = row.notna().all()
        if not (full_window and complete_history and complete_current):
            value = np.nan
        else:
            hist = history.to_numpy(dtype=float)
            delta = row.to_numpy(dtype=float) - hist.mean(axis=0)
            covariance = np.atleast_2d(np.cov(hist, rowvar=False))
            scale = float(np.trace(covariance) / max(len(row), 1))
            covariance = covariance + np.eye(len(row)) * config.turbulence_ridge * max(scale, 1.0e-12)
            value = float(delta @ np.linalg.pinv(covariance) @ delta)
        values.append(
            {
                "signal_date": date,
                "financial_turbulence": value,
                "history_months": len(history),
            }
        )
    return pd.DataFrame(
        values,
        columns=["signal_date", "financial_turbulence", "history_months"],
    )


def _quality_table(name: str, frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in frame.columns:
        if column == "signal_date":
            continue
        rows.append({"table": name, "field": column, "rows": len(frame), "missing_rate": float(frame[column].isna().mean())})
    return pd.DataFrame(rows)


def assert_point_in_time(dataset: M1Dataset) -> None:
    """阻断反向填充、发布日期穿越和同月执行。"""
    audit = dataset.availability_audit.dropna(subset=["value"])
    bad = audit["available_date"].notna() & (audit["available_date"] > audit["signal_date"])
    if bad.any():
        raise AssertionError(f"发现 {int(bad.sum())} 条可得日晚于信号日的特征")
    if not dataset.factor_returns.empty:
        fr = dataset.factor_returns
        if not ((fr["signal_date"] < fr["execution_date"]) & (fr["execution_date"] < fr["return_date"])).all():
            raise AssertionError("六因子收益存在非T+1执行日期")
        if "intended_return_date" in fr and not fr["intended_return_date"].eq(fr["return_date"]).all():
            raise AssertionError("计划退出日与下游兼容return_date不一致")
        if "label_available_date" in fr:
            label_dates = pd.to_datetime(fr["label_available_date"], errors="coerce")
            if label_dates.isna().any() or (label_dates < fr["return_date"]).any():
                raise AssertionError("六因子标签可得日早于计划退出日或缺失")
    if "financial_available_date" in dataset.factor_constituents:
        fin = dataset.factor_constituents.dropna(subset=["financial_available_date"])
        if (fin["financial_available_date"] > fin["signal_date"]).any():
            raise AssertionError("Quality财务数据晚于信号日")
    if "equity_available_date" in dataset.factor_constituents:
        equity = dataset.factor_constituents.dropna(subset=["equity_available_date"])
        if (equity["equity_available_date"] > equity["signal_date"]).any():
            raise AssertionError("派生PB使用了信号日后披露的股东权益")
    constituents = dataset.factor_constituents
    if {"intended_return_date", "actual_return_date", "exit_executed"}.issubset(constituents):
        actual = constituents.dropna(subset=["actual_return_date"])
        if (actual["actual_return_date"] < actual["intended_return_date"]).any():
            raise AssertionError("实际退出日早于计划退出日")
        executed_exit = constituents["exit_executed"].fillna(False)
        if constituents.loc[executed_exit, "actual_return_date"].isna().any():
            raise AssertionError("已执行退出缺少实际退出日")
    if "label_available_date" in constituents:
        labels = constituents.dropna(subset=["label_available_date"])
        if (labels["label_available_date"] < labels["intended_return_date"]).any():
            raise AssertionError("逐股票标签可得日早于计划退出日")


def build_m1_dataset(
    config: ChinaFactorTimingConfig | None = None,
    *,
    smoke_months: int | None = None,
    smoke_stock_limit: int | None = None,
) -> M1Dataset:
    """构造m1全套底座；smoke参数只缩小运行规模，不改变正式默认口径。"""
    from .strategy import build_equity_factor_base

    cfg = config or ChinaFactorTimingConfig()
    calendar = load_month_end_calendar(cfg)
    if smoke_months is not None:
        calendar = calendar.head(smoke_months).copy()
    benchmark, benchmark_audit = build_benchmark_features(cfg, calendar)
    macro, macro_audit = build_macro_features(cfg, calendar, benchmark, benchmark_audit)
    bonds, bond_audit = build_bond_return_proxies(cfg, calendar)
    equity = build_equity_factor_base(cfg, calendar, smoke_stock_limit=smoke_stock_limit)
    turbulence = calculate_financial_turbulence(equity.industry_returns, bonds, cfg)
    features = macro.merge(benchmark, on="signal_date", how="left").merge(turbulence, on="signal_date", how="left")
    availability = pd.concat([macro_audit, benchmark_audit, bond_audit], ignore_index=True)
    turb_audit = turbulence[["signal_date", "financial_turbulence"]].rename(columns={"financial_turbulence": "value"})
    turb_audit["feature"] = "financial_turbulence"
    turb_audit["source_date"] = turb_audit["signal_date"]
    turb_audit["release_date"] = turb_audit["signal_date"]
    turb_audit["available_date"] = turb_audit["signal_date"]
    turb_audit["data_source"] = "中信一级行业收益+中国国债久期近似"
    availability = pd.concat([availability, turb_audit[availability.columns]], ignore_index=True)
    quality = pd.concat(
        [
            _quality_table("monthly_features", features),
            _quality_table("factor_returns", equity.factor_returns),
            _quality_table("bond_return_proxies", bonds),
            equity.data_quality,
        ],
        ignore_index=True,
    )
    result = M1Dataset(
        monthly_features=features,
        factor_returns=equity.factor_returns,
        factor_constituents=equity.factor_constituents,
        financial_turbulence=turbulence,
        availability_audit=availability,
        data_quality=quality,
    )
    assert_point_in_time(result)
    return result
