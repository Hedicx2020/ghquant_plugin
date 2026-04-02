"""
Configuration for momentum factor strategy.

All parameters follow the Everbright Securities report:
"Re-examining Momentum Factors" (2019-06-15).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MomentumConfig:
    """Immutable configuration for momentum factor backtest."""

    # --- Time range ---
    start_date: str = "2006-01-01"
    end_date: str = "2019-05-31"

    # --- Data ---
    data_dir: Path = Path.home() / "local_data"

    # --- Stock universe ---
    min_list_days: int = 252  # At least 1 year after IPO
    industry_standard: int = 37  # CITICS level-1

    # --- Factor parameters ---
    # Raw momentum: look-back months
    momentum_months: list[int] = field(default_factory=lambda: [1, 3, 6, 12, 24])
    # Approximate trading days per month
    trading_days_per_month: int = 20

    # Trend momentum: MA windows (trading days)
    ma_windows: list[int] = field(default_factory=lambda: [20, 60, 120, 240])

    # Residual momentum: FF3 regression look-back (months)
    residual_lookback_months: int = 36

    # --- Backtest ---
    n_groups: int = 10
    transaction_cost: float = 0.003  # Round-trip
    periods_per_year: int = 12  # Monthly rebalancing

    # --- Factor pre-processing ---
    winsorize_method: str = "mad"

    # --- Output ---
    output_dir: Path = (
        Path.home() / "report_reproduce" / "output" / "momentum_factor" / "results"
    )

    # --- Data lookback buffer ---
    @property
    def buffer_start(self) -> str:
        """Extra lookback period to ensure enough history for 24M momentum and 36M regression."""
        import pandas as pd
        return str(
            (pd.Timestamp(self.start_date) - pd.DateOffset(months=40)).date()
        )


# Singleton config instance
CONFIG = MomentumConfig()
