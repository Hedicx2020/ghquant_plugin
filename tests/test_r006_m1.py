"""r006 m1 的纯内存时点安全烟雾。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.r006_macro_regime_factor_allocation.config import DEFAULT_CONFIG
from src.r006_macro_regime_factor_allocation.data_pipeline import (
    CommonMonthResult,
    DataContractError,
    FactorCrosswalkResult,
    FormalDataUnavailableError,
    align_factor_panel_to_schedule,
    align_macro_asof,
    apply_annual_frozen_factor_directions,
    apply_conservative_publication_lag,
    build_capacity_control_panel,
    build_common_month_index,
    build_execution_schedule,
    build_factor_crosswalk,
    build_financial_asof,
    build_industry_pit_mapping,
    build_monthly_stock_panel,
    build_publication_year_coverage,
    build_walk_forward_windows,
    calculate_historical_market_beta,
    compute_factor_availability,
    ensure_macro_block_coverage,
    fit_annual_frozen_factor_directions,
    run_sa11_sensitivity,
    select_training_history,
)


def _eight_family_metadata() -> pd.DataFrame:
    """构造只含固定文本标签的八家族元数据，不含收益或随机数据。"""
    rows = (
        ("PE_ttm", "市盈率", "基本面", "估值"),
        ("mom12", "动量", "基础", "动量"),
        ("rev", "反转", "基础", "反转"),
        ("roe", "净资产收益", "基本面", "盈利能力"),
        ("asset_growth", "资产增长", "基本面", "成长"),
        ("beta", "贝塔", "基础", "波动"),
        ("turn", "换手", "基础", "流动性"),
        ("forecast", "分析师预测", "基本面", "分析师"),
    )
    return pd.DataFrame(
        rows,
        columns=["factor_id", "factor_id_cn", "level1", "level2"],
    )


def test_crosswalk_is_one_to_one_and_hash_is_reproducible() -> None:
    """AS26 字段优先级和固定哈希在重复生成时保持一致。"""
    metadata = _eight_family_metadata()
    first = build_factor_crosswalk(metadata)
    second = build_factor_crosswalk(metadata.sample(frac=1.0, random_state=7))

    assert first.sha256 == second.sha256
    assert first.table["factor_id"].is_unique
    assert set(first.table["family"]) == set(DEFAULT_CONFIG.family_order)
    valuation = first.table.set_index("factor_id").loc["PE_ttm"]
    assert valuation["matched_field"] == "level2"
    assert valuation["matched_keyword"] == "估值"


def test_financial_asof_ignores_future_disclosure() -> None:
    """报告期可更早，但披露日晚于信号日的记录不得进入信号。"""
    signals = pd.DataFrame(
        {
            "stock_code": ["000001", "000001"],
            "signal_date": pd.to_datetime(["2024-04-30", "2024-05-31"]),
        }
    )
    financial = pd.DataFrame(
        {
            "stock_code": ["000001", "000001", "000001"],
            "end_date": pd.to_datetime(
                ["2023-12-31", "2024-03-31", "2024-03-31"]
            ),
            "info_publ_date": pd.to_datetime(
                ["2024-03-20", "2024-05-10", "2024-06-10"]
            ),
            "net_profit": [10.0, 12.0, 999.0],
        }
    )
    result = build_financial_asof(
        signals,
        financial,
        ["net_profit"],
        source_key="income",
    )

    assert result["income_net_profit"].tolist() == [10.0, 12.0]
    assert (
        result["income_info_publ_date"] <= result["signal_date"]
    ).all()


def test_macro_available_date_uses_later_of_release_and_floor() -> None:
    """宏观可用日不得早于固定一月滞后，也不得早于真实披露日。"""
    raw = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(["2024-01-31", "2024-02-29"]),
            "info_publ_date": pd.to_datetime(["2024-02-05", "2024-04-10"]),
            "value": [1.0, 2.0],
        }
    )
    timed = apply_conservative_publication_lag(
        raw,
        frequency="monthly",
        lag_months=DEFAULT_CONFIG.monthly_macro_lag_months,
    ).assign(
        block="Inflation",
        series_id="cpi_yoy",
        source_key="macro_cpi",
    )
    assert timed["available_date"].tolist() == [
        pd.Timestamp("2024-02-29"),
        pd.Timestamp("2024-04-10"),
    ]

    aligned = align_macro_asof(
        pd.to_datetime(["2024-03-29", "2024-04-30"]),
        timed,
    )
    assert aligned["value"].tolist() == [1.0, 2.0]
    assert (aligned["available_date"] <= aligned["signal_date"]).all()


def test_macro_asof_normalizes_datetime_units_without_crossing_month_boundary() -> None:
    """真实日历与宏观键精度不同时仍只向后连接，不跨月偷看未来值。"""
    signal_dates = pd.Series(
        np.array(
            ["2024-02-29", "2024-03-29", "2024-04-30"],
            dtype="datetime64[us]",
        )
    )
    macro_inputs = pd.DataFrame(
        {
            "block": ["Inflation"] * 3,
            "series_id": ["cpi_yoy"] * 3,
            "observation_date": pd.Series(
                np.array(
                    ["2024-01-31", "2024-02-29", "2024-03-31"],
                    dtype="datetime64[us]",
                )
            ),
            "available_date": pd.Series(
                np.array(
                    ["2024-02-29", "2024-03-31", "2024-04-30"],
                    dtype="datetime64[ns]",
                )
            ),
            "value": [1.0, 2.0, 3.0],
            "source_key": ["macro_cpi"] * 3,
        }
    )
    assert str(signal_dates.dtype) == "datetime64[us]"
    assert str(macro_inputs["available_date"].dtype) == "datetime64[ns]"

    aligned = align_macro_asof(signal_dates, macro_inputs)

    assert str(aligned["signal_date"].dtype) == "datetime64[ns]"
    assert str(aligned["available_date"].dtype) == "datetime64[ns]"
    assert aligned["value"].tolist() == [1.0, 1.0, 3.0]
    assert aligned["available_date"].tolist() == pd.to_datetime(
        ["2024-02-29", "2024-02-29", "2024-04-30"]
    ).tolist()
    assert (aligned["available_date"] <= aligned["signal_date"]).all()


def test_execution_schedule_is_strict_t_plus_one() -> None:
    """每个 T 月末信号只映射到严格晚于 T 的首个交易日。"""
    calendar = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2024-01-31",
                    "2024-02-01",
                    "2024-02-29",
                    "2024-03-01",
                    "2024-03-29",
                    "2024-04-01",
                ]
            ),
            "IfTradingDay": 1,
            "IfMonthEnd": [1, 0, 1, 0, 1, 0],
        }
    )
    schedule = build_execution_schedule(calendar)

    assert schedule["execution_date"].tolist() == pd.to_datetime(
        ["2024-02-01", "2024-03-01", "2024-04-01"]
    ).tolist()
    assert (schedule["execution_date"] > schedule["signal_date"]).all()


def test_factor_observations_are_mapped_to_official_signal_dates() -> None:
    """普通源观测按同月最后可用值映射，显式信号日必须精确匹配交易月末。"""
    calendar = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-15", "2024-01-30", "2024-02-01", "2024-02-29", "2024-03-01"]
            ),
            "IfTradingDay": 1,
            "IfMonthEnd": [0, 1, 0, 1, 0],
        }
    )
    schedule = build_execution_schedule(calendar)
    observations = pd.DataFrame(
        {
            "stock_code": ["000001", "000001", "000001"],
            "source_date": pd.to_datetime(
                ["2024-01-15", "2024-01-29", "2024-02-29"]
            ),
            "source_date_semantics": [
                "observation_date",
                "observation_date",
                "explicit_signal_date",
            ],
            "factor_id": ["mom", "mom", "mom"],
            "factor_value": [1.0, 2.0, 3.0],
        }
    )
    aligned = align_factor_panel_to_schedule(observations, schedule)

    assert aligned.table["signal_date"].tolist() == pd.to_datetime(
        ["2024-01-30", "2024-02-29"]
    ).tolist()
    assert aligned.table["factor_value"].tolist() == [2.0, 3.0]
    assert (aligned.table["source_date"] <= aligned.table["signal_date"]).all()
    assert aligned.table[
        ["stock_code", "signal_date", "factor_id"]
    ].duplicated().sum() == 0
    assert aligned.audit["violations"].sum() == 0

    future_declared = observations.iloc[[0]].assign(
        source_date=pd.Timestamp("2024-01-31"),
        source_date_semantics="explicit_signal_date",
    )
    with pytest.raises(DataContractError, match="时点语义"):
        align_factor_panel_to_schedule(future_declared, schedule)


def test_monthly_panel_keeps_signal_and_execution_status_separate() -> None:
    """T+1 停牌只标记执行可买性，不反向删除 T 日信号池。"""
    config = replace(DEFAULT_CONFIG, minimum_listing_trading_days=1)
    calendar = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2024-01-31",
                    "2024-02-01",
                    "2024-02-29",
                    "2024-03-01",
                    "2024-03-29",
                    "2024-04-01",
                ]
            ),
            "IfTradingDay": 1,
            "IfMonthEnd": [1, 0, 1, 0, 1, 0],
        }
    )
    price = pd.DataFrame(
        {
            "stock_code": ["000001"] * 3,
            "date": pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-29"]),
            "open": [10.0, 11.0, 12.0],
            "close": [10.0, 11.0, 12.0],
        }
    )
    trade = pd.DataFrame(
        {
            "stock_code": ["000001"] * 3,
            "date": price["date"],
            "market_value": [100.0, 110.0, 120.0],
            "negotiable_market_value": [80.0, 88.0, 96.0],
            "turn_value": [5.0, 6.0, 7.0],
            "turnover_rate_free": [1.0, 1.1, 1.2],
        }
    )
    master = pd.DataFrame(
        {
            "stock_code": ["000001"],
            "list_date": pd.to_datetime(["2020-01-01"]),
        }
    )
    suspend = pd.DataFrame(
        {
            "stock_code": ["000001"],
            "date": pd.to_datetime(["2024-02-01"]),
            "if_suspend": [1],
        }
    )
    limits = pd.DataFrame(
        columns=["stock_code", "date", "surged_limit", "decline_limit"]
    )
    st = pd.DataFrame(
        {
            "stock_code": ["000001"],
            "implement_date": pd.to_datetime(["2024-02-01"]),
            "remove_date": pd.to_datetime(["2024-02-02"]),
        }
    )
    result = build_monthly_stock_panel(
        price,
        trade,
        master,
        calendar,
        st_data=st,
        suspend_status=suspend,
        limit_status=limits,
        config=config,
    )
    january = result.loc[result["signal_month"].eq(pd.Period("2024-01"))].iloc[0]

    assert bool(january["is_signal_eligible"])
    assert not bool(january["is_st_on_signal"])
    assert bool(january["is_st_on_execution"])
    assert not bool(january["execution_buyable"])
    assert not bool(january["execution_sellable"])
    assert january["execution_date"] == pd.Timestamp("2024-02-01")
    assert np.isclose(january["forward_return"], 0.1)


def test_walk_forward_is_expanding_fixed_validation_and_annual() -> None:
    """10 年初始训练、12 年固定验证和年度预测彼此不重叠。"""
    months = pd.date_range("2000-01-31", periods=300, freq="ME")
    windows = build_walk_forward_windows(months)
    first = windows.iloc[0]

    assert first["prediction_year"] == 2022
    assert first["train_months"] == DEFAULT_CONFIG.training_months
    assert (
        windows["validation_months"] == DEFAULT_CONFIG.validation_months
    ).all()
    assert windows["train_months"].is_monotonic_increasing
    assert (windows["train_end"] < windows["validation_start"]).all()
    assert (windows["validation_end"] < windows["prediction_start"]).all()


def test_walk_forward_is_first_month_anchored_and_rejects_real_gaps() -> None:
    """非一月起点也严格取前 120 月，真实交集中的中间缺月不得被补齐。"""
    months = pd.date_range("2000-02-29", periods=300, freq="ME")
    windows = build_walk_forward_windows(months)
    first = windows.iloc[0]

    assert first["train_start"] == pd.Timestamp("2000-02-29")
    assert first["train_end"] == pd.Timestamp("2010-01-31")
    assert first["train_months"] == 120
    assert first["prediction_start"] == pd.Timestamp("2022-02-28")
    with pytest.raises(DataContractError, match="不连续"):
        build_walk_forward_windows(months.delete(150))
    incomplete = build_walk_forward_windows(
        pd.date_range("2000-01-31", periods=270, freq="ME"),
        strict=False,
    )
    assert incomplete.empty
    assert incomplete.attrs["dropped_tail_months"] == 6
    with pytest.raises(DataContractError, match="6 个尾部预测月"):
        build_walk_forward_windows(
            pd.date_range("2000-01-31", periods=270, freq="ME")
        )


def test_training_history_excludes_label_realized_in_validation() -> None:
    """方向估计的 T+1 标签若跨入验证窗，必须从训练样本剔除。"""
    months = pd.date_range("2000-01-31", periods=300, freq="ME")
    windows = build_walk_forward_windows(months)
    data = pd.DataFrame(
        {
            "signal_date": pd.to_datetime(["2009-11-27", "2009-12-31"]),
            "forward_return_date": pd.to_datetime(
                ["2009-12-31", "2010-01-31"]
            ),
            "factor_value": [1.0, 2.0],
        }
    )
    selected = select_training_history(
        data,
        windows,
        2022,
        observation_date_column="signal_date",
        realization_date_column="forward_return_date",
    )

    assert selected["signal_date"].tolist() == [pd.Timestamp("2009-11-27")]


def test_direction_fit_is_training_only_and_frozen_against_later_perturbation() -> None:
    """验证/预测收益扰动不得改变由 expanding 训练窗估计的方向及哈希。"""
    months = pd.date_range("2000-01-31", periods=300, freq="ME")
    windows = build_walk_forward_windows(months)
    rows = []
    for signal_date, realization_date in zip(months[:-1], months[1:]):
        for stock_code, factor_value in (("000001", -1.0), ("000002", 1.0)):
            rows.append(
                {
                    "stock_code": stock_code,
                    "signal_date": signal_date,
                    "forward_return_date": realization_date,
                    "factor_id": "mom",
                    "factor_value": factor_value,
                    "forward_return": factor_value * 0.01,
                }
            )
    scored = pd.DataFrame(rows)
    crosswalk = FactorCrosswalkResult(
        table=pd.DataFrame(
            {
                "factor_id": ["mom"],
                "mapping_status": ["mapped"],
                "family": ["Continuation"],
            }
        ),
        summary=pd.DataFrame(),
        sha256="fixed_crosswalk",
    )
    first = fit_annual_frozen_factor_directions(
        scored, crosswalk, windows, 2022
    )
    perturbed = scored.copy()
    perturbed.loc[
        perturbed["signal_date"].ge(pd.Timestamp("2010-01-31")),
        "forward_return",
    ] *= -100.0
    second = fit_annual_frozen_factor_directions(
        perturbed, crosswalk, windows, 2022
    )

    assert first.sha256 == second.sha256
    assert first.table["direction"].tolist() == [1]
    assert first.train_end == pd.Timestamp("2009-12-31")
    assert first.table["estimation_months"].tolist() == [119]


def test_frozen_direction_uses_cross_year_window_id_and_rejects_other_window() -> None:
    """2022-02 至 2023-01 必须共用同一冻结对象，窗口外月份必须拒绝。"""
    months = pd.date_range("2000-02-29", periods=300, freq="ME")
    windows = build_walk_forward_windows(months)
    window = windows.iloc[0]
    rows = []
    for signal_date, realization_date in zip(months[:-1], months[1:]):
        for stock_code, factor_value in (("000001", -1.0), ("000002", 1.0)):
            rows.append(
                {
                    "stock_code": stock_code,
                    "signal_date": signal_date,
                    "forward_return_date": realization_date,
                    "factor_id": "mom",
                    "factor_value": factor_value,
                    "forward_return": factor_value * 0.01,
                }
            )
    crosswalk = FactorCrosswalkResult(
        table=pd.DataFrame(
            {
                "factor_id": ["mom"],
                "mapping_status": ["mapped"],
                "family": ["Continuation"],
            }
        ),
        summary=pd.DataFrame(),
        sha256="fixed_crosswalk",
    )
    frozen = fit_annual_frozen_factor_directions(
        pd.DataFrame(rows),
        crosswalk,
        windows,
        window_id=window["window_id"],
    )
    cross_year_panel = pd.DataFrame(
        {
            "stock_code": ["000001", "000001"],
            "signal_date": [
                window["prediction_start"],
                window["prediction_end"],
            ],
            "factor_id": ["mom", "mom"],
            "factor_value": [1.0, 2.0],
        }
    )
    applied = apply_annual_frozen_factor_directions(
        cross_year_panel, frozen
    )

    assert frozen.window_id == window["window_id"]
    assert frozen.prediction_start == pd.Timestamp("2022-02-28")
    assert frozen.prediction_end == pd.Timestamp("2023-01-31")
    assert applied["direction_window_id"].eq(frozen.window_id).all()
    outside = cross_year_panel.iloc[[0]].assign(
        signal_date=pd.Timestamp("2023-02-28")
    )
    with pytest.raises(DataContractError, match="窗口外月份"):
        apply_annual_frozen_factor_directions(outside, frozen)


def test_macro_eight_block_gate_and_source_roles_are_explicit() -> None:
    """七块输入必须阻断；补入 D7 Trend 后才满足八块角色合同。"""
    seven = pd.DataFrame(
        {
            "block": list(DEFAULT_CONFIG.required_macro_blocks[:-1]),
            "series_id": [f"s{index}" for index in range(7)],
            "value": 1.0,
        }
    )
    with pytest.raises(FormalDataUnavailableError, match="Trend"):
        ensure_macro_block_coverage(seven)
    eight = pd.concat(
        [
            seven,
            pd.DataFrame(
                {"block": ["Trend"], "series_id": ["market"], "value": [0.1]}
            ),
        ],
        ignore_index=True,
    )
    ensure_macro_block_coverage(eight)
    d5 = next(item for item in DEFAULT_CONFIG.substitutes if item.element_id == "D5")
    usage = dict(d5.source_usage)
    assert usage["bond_yield_curve"] == "rates_credit_fallback"
    assert usage["csiindex_trade"] == "D7_market_trend_input"


def test_industry_pit_and_historical_beta_feed_capacity_controls() -> None:
    """D9 行业按生效日连接，beta 只由截至 T 的滚动月收益估计。"""
    config = replace(
        DEFAULT_CONFIG,
        market_beta_window_months=3,
        market_beta_min_observations=2,
    )
    months = pd.date_range("2024-01-31", periods=4, freq="ME")
    monthly = pd.DataFrame(
        {
            "stock_code": ["000001"] * 4,
            "signal_date": months,
            "month_return": [0.02, 0.04, -0.02, 0.06],
            "negotiable_market_value": [100.0, 101.0, 99.0, 102.0],
            "turn_value_month": [10.0, 11.0, 9.0, 12.0],
            "turnover_rate_free_month": [1.0, 1.1, 0.9, 1.2],
        }
    )
    index = pd.DataFrame(
        {
            "signal_date": months,
            "market_return": [0.01, 0.02, -0.01, 0.03],
        }
    )
    signals = monthly[["stock_code", "signal_date"]]
    industry_records = pd.DataFrame(
        {
            "stock_code": ["000001"],
            "first_industry_name": ["银行"],
            "standard_code": [38],
            "effective_date": pd.to_datetime(["2020-01-01"]),
            "out_date": [pd.NaT],
        }
    )
    industry = build_industry_pit_mapping(
        signals, industry_records, config
    )
    beta = calculate_historical_market_beta(monthly, index, config)
    controls = build_capacity_control_panel(
        monthly, index, industry, config
    )

    assert industry["industry_name"].eq("银行").all()
    assert np.isclose(beta.iloc[-1]["historical_market_beta"], 2.0)
    assert (
        beta["beta_source_max_date"] <= beta["signal_date"]
    ).all()
    assert controls["industry_name"].eq("银行").all()
    with pytest.raises(FormalDataUnavailableError, match="生效日"):
        build_industry_pit_mapping(
            signals,
            industry_records.drop(columns=["effective_date", "out_date"]),
            config,
        )


def test_common_month_index_is_actual_four_way_nonmissing_intersection() -> None:
    """共同月份只保留四类数据都真实非缺失的月份，不用首末日期补中间洞。"""
    months = pd.date_range("2020-01-31", periods=4, freq="ME")
    factor = pd.DataFrame(
        {
            "signal_date": months.delete(2),
            "factor_id": "f1",
            "factor_value": 1.0,
        }
    )
    stock = pd.DataFrame(
        {
            "signal_date": months,
            "is_signal_eligible": True,
            "month_return": 0.01,
        }
    )
    macro = pd.DataFrame(
        [
            {
                "signal_date": signal_date,
                "block": block,
                "series_id": f"{block}_series",
                "value": 1.0,
            }
            for signal_date in months
            for block in DEFAULT_CONFIG.required_macro_blocks
        ]
    )
    index = pd.DataFrame(
        {
            "signal_date": months,
            "source_max_date": months,
            "market_return": 0.01,
        }
    )
    common = build_common_month_index(factor, stock, macro, index)

    assert common.tolist() == months.delete(2).tolist()


def test_common_month_rejects_trend_that_is_only_nonmissing_outside_signal_sample() -> None:
    """Trend 全样本曾有值，但候选信号期全空时不得绕过逐月八块门禁。"""
    months = pd.date_range("2020-01-31", periods=2, freq="ME")
    factor = pd.DataFrame(
        {
            "signal_date": months,
            "factor_id": "f1",
            "factor_value": 1.0,
        }
    )
    stock = pd.DataFrame(
        {
            "signal_date": months,
            "is_signal_eligible": True,
            "month_return": 0.01,
        }
    )
    index = pd.DataFrame(
        {
            "signal_date": months,
            "source_max_date": months,
            "market_return": 0.01,
        }
    )
    rows = [
        {
            "signal_date": signal_date,
            "block": block,
            "series_id": f"{block}_series",
            "value": np.nan if block == "Trend" else 1.0,
        }
        for signal_date in months
        for block in DEFAULT_CONFIG.required_macro_blocks
    ]
    rows.append(
        {
            "signal_date": pd.Timestamp("2019-12-31"),
            "block": "Trend",
            "series_id": "Trend_series",
            "value": 1.0,
        }
    )
    macro = pd.DataFrame(rows)
    ensure_macro_block_coverage(macro)
    with pytest.raises(FormalDataUnavailableError, match="同时具备八个宏观块"):
        build_common_month_index(factor, stock, macro, index)

    macro.loc[
        macro["signal_date"].eq(months[0]) & macro["block"].eq("Trend"),
        "value",
    ] = 1.0
    diagnosed = build_common_month_index(
        factor,
        stock,
        macro,
        index,
        return_diagnostics=True,
    )
    assert isinstance(diagnosed, CommonMonthResult)
    assert diagnosed.month_index.tolist() == [months[0]]
    february = diagnosed.diagnostics.loc[
        diagnosed.diagnostics["signal_month"].eq(pd.Period("2020-02"))
    ].iloc[0]
    assert not bool(february["macro_block::Trend"])
    assert february["missing_macro_blocks"] == "Trend"


def test_sa11_produces_five_paths_on_identical_months_with_past_betas() -> None:
    """SA11 五路径必须落在同一月份，滚动暴露截止日严格早于收益月。"""
    months = pd.date_range("2010-01-31", periods=80, freq="ME")
    market = pd.Series(
        np.sin(np.arange(80) / 5.0) * 0.02,
        index=months,
        name="market_return",
    )
    sleeves = pd.DataFrame(
        {
            "Valuation": market.to_numpy() * 0.8
            + np.cos(np.arange(80) / 7.0) * 0.005,
            "Continuation": market.to_numpy() * -0.3
            + np.sin(np.arange(80) / 9.0) * 0.004,
        },
        index=months,
    )
    weights = pd.DataFrame(
        {
            "Valuation": np.linspace(0.4, 0.6, 80),
            "Continuation": np.linspace(0.6, 0.4, 80),
        },
        index=months,
    )
    result = run_sa11_sensitivity(sleeves, weights, market)

    assert set(result.returns.columns) == {
        "base",
        "extra_lag",
        "market_beta_residualized",
        "orthogonalized",
        "equal_weight",
    }
    assert result.returns.notna().all(axis=None)
    assert result.summary["observations"].nunique() == 1
    valid_exposure = result.exposure_audit["rolling_beta"].notna()
    assert (
        result.exposure_audit.loc[valid_exposure, "beta_source_max_date"]
        < result.exposure_audit.loc[valid_exposure, "signal_date"]
    ).all()


def test_local_availability_replaces_publication_year_only_for_audit() -> None:
    """预测年 Y 只统计首次可用年不晚于 Y-1 的本地因子。"""
    crosswalk = build_factor_crosswalk(_eight_family_metadata())
    dates = pd.to_datetime(
        [
            "2020-01-31",
            "2020-02-29",
            "2021-01-31",
            "2021-02-28",
            "2022-01-31",
            "2022-02-28",
            "2023-01-31",
            "2023-02-28",
        ]
    )
    factor_panel = pd.DataFrame(
        {
            "stock_code": ["000001"] * len(dates),
            "date": dates,
            "factor_id": _eight_family_metadata()["factor_id"],
            "factor_value": 1.0,
        }
    )
    availability = compute_factor_availability(
        factor_panel,
        FactorCrosswalkResult(
            table=crosswalk.table,
            summary=crosswalk.summary,
            sha256=crosswalk.sha256,
        ),
    )
    coverage = build_publication_year_coverage(
        availability,
        [2021, 2022, 2023, 2024],
    ).set_index("prediction_year")

    assert coverage.loc[2021, "eligible_signals"] == 2
    assert coverage.loc[2022, "eligible_signals"] == 4
    assert coverage.loc[2023, "eligible_signals"] == 6
    assert coverage.loc[2024, "eligible_signals"] == 8
