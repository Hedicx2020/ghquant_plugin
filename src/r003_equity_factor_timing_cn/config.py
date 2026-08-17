"""中国市场迁移版的集中参数。

本文件只声明口径，不读取数据。所有数值均可反查 ``plan.md``、
``spec.md`` 或 ``assumptions.md``，避免在数据函数中散落魔法数字。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ChinaFactorTimingConfig:
    """m1 数据底座及后续模型共用配置。"""

    data_root: Path = Path("/Users/hedi/local_data")
    sample_start: str = "2015-01-01"
    sample_end: str = "2025-12-31"
    factor_history_start: str = "2014-01-01"
    oos_cutoff: str = "2023-03-31"
    oos_start: str = "2023-04-01"

    benchmark_index_code: str = "000906"
    industry_standard_code: int = 37
    government_curve_code: int = 10
    government_maturities: tuple[float, ...] = (1.0, 2.0, 10.0)
    government_interpolation_target: float = 2.0
    government_interpolation_sources: tuple[float, float] = (1.0, 3.0)
    duration_by_maturity: dict[float, float] = field(
        default_factory=lambda: {1.0: 1.0, 2.0: 2.0, 10.0: 10.0}
    )

    turbulence_window_months: int = 84
    turbulence_min_history_months: int = 84
    turbulence_ridge: float = 1.0e-6
    rolling_standardization_months: int = 84
    rolling_standardization_min_months: int = 12

    drawdown_window_months: int = 3
    benchmark_volatility_window_days: int = 252
    valuation_percentile_min_months: int = 12
    policy_change_months: int = 3
    momentum_lookback_months: int = 12
    momentum_skip_months: int = 1
    low_vol_lookback_days: int = 252
    annual_trading_days: int = 252
    execution_horizon_months: int = 2
    quality_stability_min_reports: int = 2
    shibor_maturity: str = "SIBO1Y"
    missing_price_cash_return: float = 0.0

    value_fraction: float = 1.0 / 3.0
    growth_fraction: float = 1.0 / 3.0
    momentum_fraction: float = 1.0 / 3.0
    low_vol_fraction: float = 1.0 / 5.0
    quality_fraction: float = 1.0 / 3.0
    small_cap_fraction: float = 2.0 / 3.0
    pb_min_coverage: float = 0.70
    pb_min_stocks: int = 100

    macro_monthly_lag_months: int = 1
    macro_quarterly_lag_months: int = 2
    seed: int = 42

    factor_names: tuple[str, ...] = (
        "Value",
        "Growth",
        "Momentum",
        "Low Volatility",
        "Quality",
        "Small-Cap",
    )

    macro_indicator_codes: dict[str, int] = field(
        default_factory=lambda: {
            "cpi_yoy": 110255493,
            "cpi_mom": 176626030,
            "gdp_real_yoy": 110000002,
            "gdp_nominal": 110000001,
            "industrial_prod_yoy": 110000261,
            "lpr_1y": 110255796,
            "m1_yoy": 110111409,
            "m2_yoy": 110111411,
            "manufacturing_pmi": 110166523,
        }
    )

    quality_weights: dict[str, float] = field(
        default_factory=lambda: {
            "profitability": 0.20,
            "cashflow_profitability": 0.20,
            "accrual_quality": 0.20,
            "low_leverage": 0.20,
            "earnings_stability": 0.20,
        }
    )

    files: dict[str, str] = field(
        default_factory=lambda: {
            "calendar": "ashare_tradeday.parquet",
            "index_trade": "ashare_csiindex_trade.parquet",
            "index_value": "ashare_index_value.parquet",
            "index_components": "ashare_index_components.parquet",
            "stock_price_forward": "ashare_stock_price_forward.parquet",
            "stock_trade": "ashare_stock_trade.parquet",
            "stock_value": "ashare_stock_value.parquet",
            "stock_industry": "ashare_stock_industry.parquet",
            "stock_st": "ashare_stock_st.parquet",
            "stock_suspend": "ashare_stock_suspend.parquet",
            "stock_limit": "ashare_stock_limit.parquet",
            "stock_balance": "ashare_stock_balance.parquet",
            "stock_income": "ashare_stock_income.parquet",
            "stock_cashflow": "ashare_stock_cashflow.parquet",
            "yield_curve": "bond_yield_curve.parquet",
            "shibor": "bond_shibor.parquet",
            "macro_cache": "macro_cache.parquet",
            "macro_cpi": "macro_cpi.parquet",
            "macro_gdp": "macro_gdp.parquet",
            "macro_industrial": "macro_industrial_production.parquet",
            "macro_lpr": "macro_lpr.parquet",
            "macro_money": "macro_money_supply.parquet",
            "macro_pmi": "macro_pmi.parquet",
        }
    )

    def path(self, key: str) -> Path:
        """返回配置键对应的真实 Parquet 路径。"""
        return self.data_root / self.files[key]
