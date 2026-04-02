"""
Common utility functions for factor processing and performance calculation.

Provides:
- Factor standardization and neutralization
- Winsorize / MAD treatment
- Performance metrics (Sharpe, max drawdown, etc.)
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Factor pre-processing
# ---------------------------------------------------------------------------

def winsorize(
    series: pd.Series,
    method: str = "mad",
    n_sigma: float = 3.0,
    mad_multiplier: float = 1.4826,
) -> pd.Series:
    """Winsorize a cross-sectional factor series.

    Args:
        series: Raw factor values (one cross-section).
        method: 'std' for mean +/- n*std, 'mad' for median +/- n*MAD.
        n_sigma: Number of standard deviations / MAD multiples.
        mad_multiplier: Scale factor to convert MAD to std-equivalent
            (1.4826 for normal distribution).

    Returns:
        Winsorized series with outliers clipped.
    """
    s = series.dropna()
    if s.empty:
        return series

    if method == "mad":
        median = s.median()
        mad = (s - median).abs().median() * mad_multiplier
        lower, upper = median - n_sigma * mad, median + n_sigma * mad
    else:
        mean, std = s.mean(), s.std()
        lower, upper = mean - n_sigma * std, mean + n_sigma * std

    return series.clip(lower=lower, upper=upper)


def standardize(series: pd.Series) -> pd.Series:
    """Z-score standardize a cross-sectional factor series.

    Args:
        series: Factor values (one cross-section).

    Returns:
        Standardized series (mean=0, std=1).
    """
    s = series.dropna()
    if s.empty or s.std() == 0:
        return series * 0.0
    return (series - s.mean()) / s.std()


def neutralize_factor(
    factor: pd.Series,
    *,
    market_cap: Optional[pd.Series] = None,
    industry: Optional[pd.Series] = None,
) -> pd.Series:
    """Market-cap and/or industry neutralization via cross-sectional OLS.

    Regresses *factor* on ln(market_cap) and industry dummies,
    returns the residual.

    Args:
        factor: Raw factor values indexed by stock_code.
        market_cap: Market capitalization (same index as factor).
        industry: Industry labels (same index as factor).

    Returns:
        Neutralized factor (OLS residuals).
    """
    valid = factor.dropna()
    if valid.empty:
        return factor

    X_parts: list[pd.DataFrame] = []

    if market_cap is not None:
        ln_cap = np.log(market_cap.reindex(valid.index).clip(lower=1))
        X_parts.append(ln_cap.to_frame("ln_cap"))

    if industry is not None:
        ind = industry.reindex(valid.index)
        dummies = pd.get_dummies(ind, drop_first=True, dtype=float)
        X_parts.append(dummies)

    if not X_parts:
        return factor

    X = pd.concat(X_parts, axis=1).reindex(valid.index)
    # Add constant
    X.insert(0, "_const", 1.0)

    # Drop rows with any NaN in X or y
    mask = X.notna().all(axis=1) & valid.notna()
    X_clean, y_clean = X.loc[mask], valid.loc[mask]

    if X_clean.shape[0] <= X_clean.shape[1]:
        return factor

    # OLS via normal equations
    try:
        beta = np.linalg.lstsq(X_clean.values, y_clean.values, rcond=None)[0]
        residual = y_clean - X_clean.values @ beta
    except np.linalg.LinAlgError:
        return factor

    return residual.reindex(factor.index)


def standardize_factor(
    factor_df: pd.DataFrame,
    factor_col: str = "factor",
    date_col: str = "date",
    market_cap_col: Optional[str] = None,
    industry_col: Optional[str] = None,
    winsorize_method: str = "mad",
) -> pd.DataFrame:
    """Full factor pre-processing pipeline per cross-section.

    Pipeline: winsorize -> neutralize -> z-score standardize.

    Args:
        factor_df: Panel data with at least [date_col, factor_col].
        factor_col: Column name of the raw factor.
        date_col: Column name of the date.
        market_cap_col: Column name of market cap (optional).
        industry_col: Column name of industry label (optional).
        winsorize_method: 'mad' or 'std'.

    Returns:
        DataFrame with additional column ``factor_std``.
    """
    result_parts: list[pd.DataFrame] = []

    for dt, grp in factor_df.groupby(date_col):
        f = grp[factor_col].copy()
        # Step 1: winsorize
        f = winsorize(f, method=winsorize_method)
        # Step 2: neutralize
        mc = grp[market_cap_col] if market_cap_col and market_cap_col in grp.columns else None
        ind = grp[industry_col] if industry_col and industry_col in grp.columns else None
        f = neutralize_factor(f, market_cap=mc, industry=ind)
        # Step 3: z-score
        f = standardize(f)
        result_parts.append(grp.assign(factor_std=f))

    return pd.concat(result_parts, ignore_index=True) if result_parts else factor_df.assign(factor_std=np.nan)


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------

def calculate_sharpe(
    returns: pd.Series,
    rf: float = 0.0,
    periods_per_year: int = 12,
) -> float:
    """Annualized Sharpe ratio.

    Args:
        returns: Period returns (e.g. monthly).
        rf: Risk-free rate per period.
        periods_per_year: Periods in one year (12 for monthly, 252 for daily).

    Returns:
        Annualized Sharpe ratio.
    """
    excess = returns - rf
    if excess.std() == 0:
        return 0.0
    return float(excess.mean() / excess.std() * np.sqrt(periods_per_year))


def calculate_annualized_return(
    returns: pd.Series,
    periods_per_year: int = 12,
) -> float:
    """Annualized return from period returns.

    Args:
        returns: Period returns.
        periods_per_year: Periods per year.

    Returns:
        Annualized return.
    """
    cum = (1 + returns).prod()
    n_years = len(returns) / periods_per_year
    if n_years <= 0:
        return 0.0
    return float(cum ** (1 / n_years) - 1)


def calculate_annualized_volatility(
    returns: pd.Series,
    periods_per_year: int = 12,
) -> float:
    """Annualized volatility.

    Args:
        returns: Period returns.
        periods_per_year: Periods per year.

    Returns:
        Annualized volatility.
    """
    return float(returns.std() * np.sqrt(periods_per_year))


def calculate_max_drawdown(nav: pd.Series) -> float:
    """Maximum drawdown from a net-value (cumulative return) series.

    Args:
        nav: Cumulative net value series (starting from 1.0).

    Returns:
        Maximum drawdown as a positive fraction (e.g. 0.15 = 15%).
    """
    running_max = nav.cummax()
    drawdown = (nav - running_max) / running_max
    return float(-drawdown.min()) if len(drawdown) > 0 else 0.0


def calculate_win_rate(returns: pd.Series) -> float:
    """Win rate: fraction of periods with positive return.

    Args:
        returns: Period returns.

    Returns:
        Win rate as a fraction.
    """
    if returns.empty:
        return 0.0
    return float((returns > 0).sum() / len(returns))


def calculate_calmar(
    returns: pd.Series,
    periods_per_year: int = 12,
) -> float:
    """Calmar ratio = annualized return / max drawdown.

    Args:
        returns: Period returns.
        periods_per_year: Periods per year.

    Returns:
        Calmar ratio.
    """
    ann_ret = calculate_annualized_return(returns, periods_per_year)
    nav = (1 + returns).cumprod()
    mdd = calculate_max_drawdown(nav)
    return float(ann_ret / mdd) if mdd > 0 else 0.0


def performance_summary(
    returns: pd.Series,
    periods_per_year: int = 12,
    name: str = "",
) -> dict:
    """Comprehensive performance summary.

    Args:
        returns: Period returns.
        periods_per_year: Periods per year.
        name: Optional label.

    Returns:
        Dictionary of performance metrics.
    """
    nav = (1 + returns).cumprod()
    return {
        "name": name,
        "ann_return": calculate_annualized_return(returns, periods_per_year),
        "ann_volatility": calculate_annualized_volatility(returns, periods_per_year),
        "sharpe": calculate_sharpe(returns, periods_per_year=periods_per_year),
        "max_drawdown": calculate_max_drawdown(nav),
        "win_rate": calculate_win_rate(returns),
        "calmar": calculate_calmar(returns, periods_per_year),
        "cumulative_return": float(nav.iloc[-1] - 1) if len(nav) > 0 else 0.0,
        "n_periods": len(returns),
    }
