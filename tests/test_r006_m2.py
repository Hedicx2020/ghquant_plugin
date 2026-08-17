"""r006 m2 的纯内存方法与时点烟雾。"""

from __future__ import annotations

import sys
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.r006_macro_regime_factor_allocation.data_pipeline import (
    FormalDataUnavailableError,
)
from src.r006_macro_regime_factor_allocation.family_sleeves import (
    M2ContractError,
    aggregate_family_sleeve_layer,
    apply_frozen_factor_directions,
    assert_formal_m1_dataset,
    assign_capacity_regions,
    build_factor_decile_layer,
    calculate_monthly_factor_ic,
    estimate_six_factor_alpha,
    fama_macbeth_regression,
    fit_frozen_factor_directions,
    newey_west_mean_sensitivity,
)


def test_formal_mode_rejects_dry_run_without_synthetic() -> None:
    """m1 dry-run 不能进入 m2 正式路径。"""
    with pytest.raises(FormalDataUnavailableError, match="禁止 synthetic"):
        assert_formal_m1_dataset(SimpleNamespace(dry_run=True))  # type: ignore[arg-type]


def test_direction_uses_month_period_boundaries_and_training_labels_only() -> None:
    """2010-01-29 必须落入日历边界为 2010-01-31 的预测首月。"""
    dates = pd.to_datetime(
        [
            "2009-10-30",
            "2009-11-30",
            "2009-12-31",
            "2010-01-29",
            "2010-02-26",
        ]
    )
    realization_dates = pd.to_datetime(
        [
            "2009-11-30",
            "2009-12-31",
            "2010-01-29",
            "2010-02-26",
            "2010-03-31",
        ]
    )
    stocks = [f"{index:06d}" for index in range(12)]
    rows: list[dict[str, object]] = []
    for date, realization_date in zip(dates, realization_dates, strict=True):
        base = np.linspace(-1.0, 1.0, len(stocks))
        for factor_id, family, sign in (
            ("positive", "Valuation", 1.0),
            ("negative", "Continuation", -1.0),
        ):
            for stock, score, forward_return in zip(
                stocks, base, sign * base, strict=True
            ):
                rows.append(
                    {
                        "signal_date": date,
                        "forward_return_date": realization_date,
                        "stock_code": stock,
                        "factor_id": factor_id,
                        "family": family,
                        "factor_score": score,
                        "forward_return": forward_return,
                    }
                )
    panel = pd.DataFrame(rows)
    windows = pd.DataFrame(
        {
            "window_id": ["wf_201001_201002"],
            "prediction_year": [2010],
            "train_start": [pd.Timestamp("2009-10-31")],
            "train_end": [pd.Timestamp("2009-12-31")],
            "validation_start": [pd.Timestamp("2009-12-31")],
            "validation_end": [pd.Timestamp("2009-12-31")],
            "prediction_start": [pd.Timestamp("2010-01-31")],
            "prediction_end": [pd.Timestamp("2010-02-28")],
        }
    )
    frozen = fit_frozen_factor_directions(
        panel,
        windows,
        window_id="wf_201001_201002",
        crosswalk_sha256="fixed-crosswalk",
    )
    directions = frozen.table.set_index("factor_id")["direction"]

    assert directions.to_dict() == {"negative": -1, "positive": 1}
    assert frozen.table["train_ic_months"].eq(2).all()

    applied = apply_frozen_factor_directions(
        panel,
        frozen,
        start_date=pd.Timestamp("2010-01-31"),
        end_date=pd.Timestamp("2010-02-28"),
    )
    assert applied["signal_date"].tolist() == [
        pd.Timestamp("2010-01-29")
    ] * 24 + [pd.Timestamp("2010-02-26")] * 24
    assert (applied["directed_score"] * applied["forward_return"] >= 0.0).all()
    assert applied["direction_sha256"].eq(frozen.sha256).all()


def test_cross_year_window_reuses_hash_and_rejects_next_window() -> None:
    """2022-02..2023-01 共用 window_id/哈希，2023-02 必须拒绝。"""
    months = pd.date_range("2000-02-29", periods=300, freq="ME")
    rows: list[dict[str, object]] = []
    for signal_date, realization_date in pairwise(months):
        for stock_code, score in (("000001", -1.0), ("000002", 1.0)):
            rows.append(
                {
                    "stock_code": stock_code,
                    "signal_date": signal_date,
                    "forward_return_date": realization_date,
                    "factor_id": "momentum",
                    "family": "Continuation",
                    "factor_score": score,
                    "forward_return": score * 0.01,
                }
            )
    windows = pd.DataFrame(
        {
            "window_id": ["wf_202202_202301"],
            "prediction_year": [2022],
            "train_start": [pd.Timestamp("2000-02-29")],
            "train_end": [pd.Timestamp("2009-12-31")],
            "prediction_start": [pd.Timestamp("2022-02-28")],
            "prediction_end": [pd.Timestamp("2023-01-31")],
        }
    )
    frozen = fit_frozen_factor_directions(
        pd.DataFrame(rows),
        windows,
        window_id="wf_202202_202301",
        crosswalk_sha256="fixed-crosswalk",
    )
    prediction = pd.DataFrame(
        {
            "stock_code": ["000001", "000001"],
            "signal_date": pd.to_datetime(["2022-02-25", "2023-01-31"]),
            "factor_id": ["momentum", "momentum"],
            "family": ["Continuation", "Continuation"],
            "factor_score": [1.0, 2.0],
        }
    )
    applied = apply_frozen_factor_directions(
        prediction,
        frozen,
        start_date=pd.Timestamp("2022-02-28"),
        end_date=pd.Timestamp("2023-01-31"),
    )

    assert frozen.window_id == "wf_202202_202301"
    assert applied["direction_window_id"].eq(frozen.window_id).all()
    assert applied["direction_sha256"].nunique() == 1
    outside = prediction.iloc[[0]].assign(
        signal_date=pd.Timestamp("2023-02-28")
    )
    with pytest.raises(M2ContractError, match="窗口外月份"):
        apply_frozen_factor_directions(
            outside,
            frozen,
            start_date=pd.Timestamp("2023-02-28"),
            end_date=pd.Timestamp("2023-02-28"),
        )


def _directed_decile_panel() -> pd.DataFrame:
    dates = pd.date_range("2024-01-31", periods=3, freq="ME")
    stocks = [f"{index:06d}" for index in range(20)]
    rows: list[dict[str, object]] = []
    for month_index, date in enumerate(dates):
        scores = np.linspace(-1.0, 1.0, len(stocks))
        for stock_index, (stock, score) in enumerate(
            zip(stocks, scores, strict=True)
        ):
            rows.append(
                {
                    "signal_date": date,
                    "execution_date": date + pd.Timedelta(days=1),
                    "forward_return_date": date + pd.offsets.MonthEnd(1),
                    "stock_code": stock,
                    "factor_id": "value",
                    "family": "Valuation",
                    "directed_score": score,
                    "forward_return": 0.01 * score + 0.0001 * month_index,
                    "negotiable_market_value": float(stock_index + 1),
                    "execution_buyable": True,
                    "execution_sellable": True,
                    "crosswalk_sha256": "fixed-crosswalk",
                    "direction_sha256": "fixed-direction",
                }
            )
    return pd.DataFrame(rows)


def test_decile_ew_vw_family_turnover_and_cost_are_auditable() -> None:
    """十分位两腿、家族聚合、单边换手与 bps 成本均可复算。"""
    factor_layer = build_factor_decile_layer(_directed_decile_panel())
    family_layer = aggregate_family_sleeve_layer(factor_layer)
    first_weights = factor_layer.weights.loc[
        factor_layer.weights["signal_date"].eq(pd.Timestamp("2024-01-31"))
    ]
    leg_sums = first_weights.groupby(
        ["weighting", "quantile"], observed=True
    )["target_weight"].sum()

    assert np.isclose(leg_sums.loc[("EW", 10.0)], 1.0)
    assert np.isclose(leg_sums.loc[("EW", 1.0)], -1.0)
    assert set(factor_layer.returns["weighting"]) == {"EW", "VW"}
    assert factor_layer.returns["forward_return_date"].gt(
        factor_layer.returns["signal_date"]
    ).all()
    assert np.isclose(factor_layer.returns.iloc[0]["turnover"], 1.0)
    first_cost = factor_layer.cost_sensitivity.loc[
        factor_layer.cost_sensitivity["cost_bps"].eq(10.0)
    ].iloc[0]
    assert np.isclose(first_cost["transaction_cost"], 0.001)
    assert family_layer.returns["family"].eq("Valuation").all()


def test_ic_and_newey_west_interfaces_do_not_regress() -> None:
    """Pearson/Rank IC 与三档 NW 月度推断保持可计算。"""
    panel = _directed_decile_panel()
    factor_ic = calculate_monthly_factor_ic(panel)
    sensitivity = newey_west_mean_sensitivity(
        pd.Series(
            np.sin(np.arange(24, dtype=float) / 3.0) * 0.01 + 0.002
        )
    )

    assert factor_ic["ic"].gt(0.99).all()
    assert factor_ic["rank_ic"].gt(0.99).all()
    assert sensitivity["lag"].tolist() == [3, 6, 12]
    assert sensitivity["estimate"].notna().all()


def test_fmb_six_factor_alpha_and_capacity_regions_are_computable() -> None:
    """FMB、A股六因子 alpha 与八容量区域仅依赖显式输入。"""
    dates = pd.date_range("2020-01-31", periods=18, freq="ME")
    stock_index = np.arange(20, dtype=float)
    rows: list[dict[str, float | pd.Timestamp]] = []
    for month_index, date in enumerate(dates):
        signal = np.linspace(-1.0, 1.0, len(stock_index))
        controls = np.column_stack(
            [
                signal**2,
                np.sin(stock_index),
                np.cos(stock_index),
                stock_index % 3.0,
            ]
        )
        returns = (
            0.01
            + 0.03 * signal
            + controls @ np.array([0.002, -0.001, 0.0015, 0.0005])
            + 0.00001 * month_index
        )
        for row_index in range(len(stock_index)):
            rows.append(
                {
                    "signal_date": date,
                    "directed_score": signal[row_index],
                    "forward_return": returns[row_index],
                    "log_negotiable_market_value": controls[row_index, 0],
                    "log_book_to_market": controls[row_index, 1],
                    "momentum_12_1": controls[row_index, 2],
                    "historical_beta": controls[row_index, 3],
                }
            )
    fmb = fama_macbeth_regression(pd.DataFrame(rows))
    main_slope = fmb.summary.loc[
        fmb.summary["coefficient"].eq("directed_score")
        & fmb.summary["lag"].eq(6),
        "estimate",
    ].iloc[0]
    assert np.isclose(main_slope, 0.03)

    factor_values = pd.DataFrame(
        {
            "date": dates,
            **{
                name: 0.01 * np.sin(
                    np.arange(len(dates), dtype=float) * frequency
                )
                for name, frequency in zip(
                    ("MKT", "SMB", "HML", "RMW", "CMA", "MOM"),
                    (0.2, 0.3, 0.5, 0.7, 0.9, 1.1),
                    strict=True,
                )
            },
        }
    )
    factor_matrix = factor_values[
        ["MKT", "SMB", "HML", "RMW", "CMA", "MOM"]
    ].to_numpy()
    portfolio = pd.DataFrame(
        {
            "forward_return_date": dates,
            "gross_return": (
                0.004
                + factor_matrix
                @ np.array([0.2, -0.1, 0.05, 0.03, -0.02, 0.04])
                + 0.00001 * np.cos(np.arange(len(dates), dtype=float) * 1.3)
            ),
        }
    )
    alpha = estimate_six_factor_alpha(portfolio, factor_values)
    alpha_estimate = alpha.coefficients.loc[
        alpha.coefficients["coefficient"].eq("alpha"), "estimate"
    ].iloc[0]
    assert np.isclose(alpha_estimate, 0.004, atol=0.0001)

    capacity = assign_capacity_regions(
        pd.DataFrame(
            {
                "signal_date": pd.Timestamp("2024-01-31"),
                "stock_code": [f"{index:06d}" for index in range(100)],
                "negotiable_market_value": np.arange(1.0, 101.0),
            }
        )
    )
    region_counts = capacity.groupby("capacity_region")["stock_code"].nunique()
    assert region_counts.to_dict() == {
        "All firms": 100,
        "Large top 20": 20,
        "Mega top 10": 10,
        "Micro bottom 20": 20,
        "Middle 60": 60,
        "Outside microcaps": 80,
        "Upper half": 50,
        "Upper third": 34,
    }
