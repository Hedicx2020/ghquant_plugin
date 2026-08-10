"""r004 iter_01 PIT TTM 与全量正式 OOS 数据门禁。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.r004_all_a_style_box.data_pipeline import (
    _build_pit_snapshot_from_vintages,
    build_m1_dataset,
)
from src.r004_all_a_style_box.strategy import build_m2_dataset


def test_three_leg_ttm_uses_only_disclosed_matching_periods() -> None:
    keys = pd.DataFrame(
        {"stock_code": ["000001"], "signal_date": pd.to_datetime(["2024-10-31"])}
    )
    vintages = pd.DataFrame(
        {
            "stock_code": ["000001"] * 4,
            "end_date": pd.to_datetime(
                ["2023-09-30", "2023-12-31", "2024-09-30", "2024-09-30"]
            ),
            "info_publ_date": pd.to_datetime(
                ["2023-10-25", "2024-03-20", "2024-10-20", "2024-11-10"]
            ),
            "total_operating_revenue": [70.0, 100.0, 90.0, 999.0],
            "net_profit": [7.0, 10.0, 9.0, 999.0],
        }
    )
    result = _build_pit_snapshot_from_vintages(keys, vintages).iloc[0]
    assert result["current_total_operating_revenue"] == 90.0
    assert result["prior_total_operating_revenue"] == 70.0
    assert result["prior_fy_total_operating_revenue"] == 100.0
    assert result["ttm_revenue"] == 120.0
    assert result["ttm_net_profit"] == 12.0
    assert result["ttm_revenue_formula"] == "current_ytd+prior_fy-prior_ytd"
    assert result["current_info_publ_date"] <= result["signal_date"]


def test_full_33_month_oos_style_coverage_and_concentration() -> None:
    m1 = build_m1_dataset(smoke_months=33)
    m2 = build_m2_dataset(m1.monthly_panel)
    factors = m2.pit_style_inputs
    coverage = factors.groupby("signal_date", sort=True)["is_style_valid"].mean()
    stats = m2.monthly_statistics

    assert factors["signal_date"].nunique() == 33
    assert coverage.min() >= 0.95
    assert coverage.ge(0.97).all()
    assert coverage.diff().abs().dropna().max() <= 0.05
    assert stats["member_count"].min() >= 100
    assert stats["maximum_target_weight"].max() <= 0.10 + 1e-12
    assert stats["top_ten_target_weight"].max() <= 0.50 + 1e-12
    source_dates = [
        "current_info_publ_date",
        "prior_info_publ_date",
        "prior_fy_info_publ_date",
        "balance_info_publ_date",
        "dividend_source_date",
    ]
    assert sum((factors[column] > factors["signal_date"]).sum() for column in source_dates) == 0
    assert np.isfinite(factors.loc[factors["book_to_price"].notna(), "book_to_price"]).all()
