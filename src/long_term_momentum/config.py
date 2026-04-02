"""
Configuration parameters for Long-Term Momentum 2.0 factor strategy.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Factor construction parameters
# ---------------------------------------------------------------------------
LOOKBACK_DAYS: int = 160          # Rolling lookback window (trading days)
LOW_AMPLITUDE_RATIO: float = 0.70  # Fraction of low-amplitude days to keep
REVERSE_DAYS: int = 20            # Lookback for the reversal factor

# ---------------------------------------------------------------------------
# Backtest parameters
# ---------------------------------------------------------------------------
START_DATE: str = "2013-01-01"
END_DATE: str = "2022-10-31"
REBALANCE_FREQ: str = "M"        # Month-end rebalancing
TRANSACTION_COST: float = 0.003   # Round-trip cost (0.3%)
N_GROUPS: int = 5                 # Number of quantile groups

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DATA_DIR: Path = Path.home() / "local_data"

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
OUTPUT_DIR: Path = PROJECT_ROOT / "output" / "long_term_momentum" / "results"

# ---------------------------------------------------------------------------
# Limit-up / limit-down thresholds
# ---------------------------------------------------------------------------
LIMIT_TOLERANCE: float = 0.001    # 0.1% tolerance
LIMIT_RATIO_MAIN: float = 0.10   # Main board
LIMIT_RATIO_GEM: float = 0.20    # GEM (ChiNext) after 2020-08-24
LIMIT_RATIO_STAR: float = 0.20   # STAR Market (688xxx)
LIMIT_RATIO_ST: float = 0.05     # ST stocks
GEM_REFORM_DATE: str = "2020-08-24"  # ChiNext registration reform

# ---------------------------------------------------------------------------
# Index codes for sub-universe testing
# ---------------------------------------------------------------------------
INDEX_CODES: dict[str, str] = {
    "hs300": "000300",    # CSI 300
    "zz500": "000905",    # CSI 500
    "zz1000": "399311",   # CSI 1000 (National Securities, closest proxy)
}

# ---------------------------------------------------------------------------
# Industry classification
# ---------------------------------------------------------------------------
INDUSTRY_STANDARD_CODE: int = 37  # CITICS level-1 (中信一级)
