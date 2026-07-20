"""
Common utility functions for factor processing and performance calculation.

Provides:
- Factor standardization and neutralization
- Winsorize / MAD treatment
- Performance metrics (Sharpe, max drawdown, etc.)
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Sequence, Union

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

    期初财富固定为 1.0（本项目净值约定），故 running peak 初值须至少为 1.0：许多
    调用方传入的 ``nav`` 首元素已含首期收益（如 ``(1+returns).cumprod()`` 或
    ``portfolio_backtest`` 的 nav，其首元素=1·(1+r0)），若直接从首元素起算 cummax
    会漏计「期初 1.0 → 首期」的回撤（例：首期跌 10% 后持平，nav=[0.9,0.9] 应得
    MDD=10%，旧式 cummax 得 0）。``clip(lower=1.0)`` 把期初财富 1.0 纳入峰值，对首元素
    本就=1.0 的序列是恒等（no-op），故对所有「起点 1.0」约定的调用方均正确。

    Args:
        nav: Cumulative net value series (initial wealth = 1.0).

    Returns:
        Maximum drawdown as a positive fraction (e.g. 0.15 = 15%).
    """
    if len(nav) == 0:
        return 0.0
    running_max = nav.cummax().clip(lower=1.0)          # 峰值含期初财富 1.0（CDX-C-08）
    drawdown = (nav - running_max) / running_max
    return float(-drawdown.min())


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


# ---------------------------------------------------------------------------
# Univariate OLS with slope significance (通用回归工具)
# ---------------------------------------------------------------------------

class OLSFit(NamedTuple):
    """Result of a single-regressor OLS ``y = alpha + beta * x + eps``.

    ``beta_pvalue`` is the two-sided t-test p-value for the slope (H0: beta = 0)
    under the Student-t(n-2) distribution. Degenerate cases (too few
    observations, no variance in x, zero residual scale) carry nan statistics.
    """
    alpha: float
    beta: float
    beta_se: float
    beta_t: float
    beta_pvalue: float
    n_obs: int


def ols_univariate(
    x: Union[Sequence[float], NDArray],
    y: Union[Sequence[float], NDArray],
    min_obs: int = 3,
) -> OLSFit:
    """Closed-form single-regressor OLS with a t-test on the slope.

    Fits ``y = alpha + beta * x + eps`` and reports the slope's standard error,
    t-statistic and two-sided p-value from the Student-t(n-2) distribution.
    Implemented with pure numpy plus ``scipy.stats.t`` (imported lazily) so the
    module carries no statsmodels dependency.

    The caller is responsible for removing NaNs and aligning ``x`` and ``y``.

    Args:
        x: Regressor values (1-D), NaN-free and aligned with y.
        y: Response values (1-D), NaN-free and aligned with x.
        min_obs: Minimum observations required; at least 3 so df = n-2 >= 1.

    Returns:
        OLSFit. Degenerate inputs return nan statistics with the observed n_obs.
    """
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    n = int(xa.size)
    nan = float("nan")
    if n != ya.size or n < max(min_obs, 3):
        return OLSFit(nan, nan, nan, nan, nan, n)

    x_bar = float(xa.mean())
    y_bar = float(ya.mean())
    sxx = float(((xa - x_bar) ** 2).sum())
    if sxx <= 0.0:  # x 无变异 → 斜率不可识别
        return OLSFit(nan, nan, nan, nan, nan, n)

    beta = float(((xa - x_bar) * (ya - y_bar)).sum() / sxx)
    alpha = float(y_bar - beta * x_bar)
    resid = ya - alpha - beta * xa
    df = n - 2
    sigma2 = float((resid ** 2).sum()) / df
    if sigma2 <= 0.0:  # 完美拟合 / y 近常数 → 无法做 t 检验
        return OLSFit(alpha, beta, 0.0, nan, nan, n)

    beta_se = float(np.sqrt(sigma2 / sxx))
    beta_t = beta / beta_se
    from scipy import stats  # 惰性依赖：仅斜率显著性检验需要 scipy

    beta_pvalue = float(2.0 * stats.t.sf(abs(beta_t), df))
    return OLSFit(alpha, beta, beta_se, beta_t, beta_pvalue, n)


# ---------------------------------------------------------------------------
# Allocation / portfolio performance metrics（配置类通用绩效指标，跨类型复用）
#   PSR / Sortino / Modigliani / 历史模拟 VaR / Frobenius 分散化
#   —— 由 allocation 首个案例 ssrn_6115073 (m6) 沉淀，公式见其 spec B7（式18-19/F.2-F.4）
# ---------------------------------------------------------------------------

def calculate_arithmetic_annual_return(
    returns: pd.Series,
    periods_per_year: int = 12,
) -> float:
    """Arithmetic annualized return = mean(period return) * periods_per_year.

    与几何 :func:`calculate_annualized_return` 并存：配置类主结果表（如 spec 式18
    ``SR=(R-rf)/σ``）需要 ``AR/AStd`` 与年化 Sharpe 表内自洽（``mean*P`` 与
    ``std*sqrt(P)`` 使 ``SR = AR_excess / AStd``），故单列算术年化收益。

    Args:
        returns: Period returns (e.g. monthly).
        periods_per_year: Periods per year.

    Returns:
        Arithmetic annualized return.
    """
    if returns.empty:
        return 0.0
    return float(returns.mean() * periods_per_year)


def downside_deviation(
    returns: pd.Series,
    target: float = 0.0,
) -> float:
    """Per-period downside deviation ``sqrt(mean(min(r - target, 0)^2))``.

    使用完整样本长度做分母（非仅下行样本数），为 Sortino 比率的标准下行风险口径。

    Args:
        returns: Period returns.
        target: Minimum acceptable return per period (e.g. rf or 0).

    Returns:
        Per-period downside deviation (>= 0).
    """
    if returns.empty:
        return 0.0
    shortfall = np.minimum(returns.to_numpy(dtype=float) - target, 0.0)
    return float(np.sqrt((shortfall ** 2).mean()))


def calculate_sortino(
    returns: pd.Series,
    rf: float = 0.0,
    periods_per_year: int = 12,
    target: Optional[float] = None,
) -> float:
    """Annualized Sortino ratio (spec 式F.3): ``(R - rf) / downside_std``.

    分子用算术年化超额收益 ``(mean(r) - rf) * P``；分母用年化下行偏差
    ``downside_deviation(r, target) * sqrt(P)``。target 默认取 rf（下行相对无风险）。

    Args:
        returns: Period returns.
        rf: Risk-free rate per period.
        periods_per_year: Periods per year.
        target: Downside target per period; defaults to ``rf``.

    Returns:
        Annualized Sortino ratio (0.0 when downside deviation is zero).
    """
    if returns.empty:
        return 0.0
    tgt = rf if target is None else target
    dd = downside_deviation(returns, target=tgt)
    if dd == 0.0:
        return 0.0
    ann_excess = (float(returns.mean()) - rf) * periods_per_year
    return float(ann_excess / (dd * np.sqrt(periods_per_year)))


def calculate_modigliani(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    rf: float = 0.0,
    periods_per_year: int = 12,
) -> float:
    """Modigliani risk-adjusted performance (spec 式F.4): ``MR = SR * σ_b + rf``.

    SR 为年化 Sharpe（:func:`calculate_sharpe`），σ_b 为基准年化波动，rf 为年化无风险。
    返回与年化收益同尺度、可直接与 AR 比较的风险调整收益。

    Args:
        returns: Portfolio period returns.
        benchmark_returns: Benchmark (index) period returns for σ_b.
        rf: Risk-free rate per period.
        periods_per_year: Periods per year.

    Returns:
        Modigliani ratio (annualized-return scale).
    """
    if returns.empty:
        return 0.0
    sr = calculate_sharpe(returns, rf=rf, periods_per_year=periods_per_year)
    sigma_b = float(benchmark_returns.std()) * np.sqrt(periods_per_year)
    rf_ann = rf * periods_per_year
    return float(sr * sigma_b + rf_ann)


def calculate_psr(
    returns: pd.Series,
    rf: float = 0.0,
    sr_benchmark: float = 0.0,
) -> float:
    """Probabilistic Sharpe Ratio (Bailey & López de Prado 2012, spec 式F.2).

    ``PSR(SR*) = Φ[ (ŜR - SR*)·√(L-1) / √(1 - γ3·ŜR + (γ4-1)/4·ŜR²) ]`` where
    ŜR is the **per-period** (non-annualized) excess Sharpe, L the sample size,
    γ3 the skewness and γ4 the (non-excess) kurtosis of excess returns. SR* is
    the benchmark Sharpe (spec AS22 uses SR*=0, testing SR significantly > 0).

    Args:
        returns: Period returns.
        rf: Risk-free rate per period (excess = returns - rf).
        sr_benchmark: Benchmark per-period Sharpe SR* (default 0.0, AS22).

    Returns:
        PSR in [0, 1]; 0.5 for degenerate inputs (too few obs / zero variance).
    """
    excess = (returns - rf).dropna()
    n = int(excess.size)
    if n < 3:
        return 0.5
    sd = float(excess.std())
    if sd == 0.0:
        return 0.5
    sr_hat = float(excess.mean()) / sd
    from scipy import stats  # 惰性依赖：偏度/峰度/正态 CDF

    gamma3 = float(stats.skew(excess.to_numpy(dtype=float), bias=False))
    gamma4 = float(stats.kurtosis(excess.to_numpy(dtype=float), fisher=False, bias=False))
    denom = 1.0 - gamma3 * sr_hat + (gamma4 - 1.0) / 4.0 * sr_hat ** 2
    if denom <= 0.0:
        return 0.5
    z = (sr_hat - sr_benchmark) * np.sqrt(n - 1) / np.sqrt(denom)
    return float(stats.norm.cdf(z))


def calculate_historical_var(
    returns: pd.Series,
    level: float = 0.05,
) -> float:
    """Historical-simulation VaR: loss at the lowest ``level`` quantile (spec B7).

    Returns a positive loss magnitude (e.g. 0.08 = 8% one-period loss at 5%).

    Args:
        returns: Period returns.
        level: Tail probability (0.05 = lowest 5%).

    Returns:
        VaR as a positive fraction (0.0 for empty input).
    """
    r = returns.dropna()
    if r.empty:
        return 0.0
    q = float(np.quantile(r.to_numpy(dtype=float), level))
    return float(-q)


def frobenius_diversification(corr: pd.DataFrame) -> float:
    """Portfolio diversification index ``‖CM − IM‖_F`` (spec B7 / 附录C).

    CM = asset correlation matrix, IM = identity (ideal fully-diversified). The
    smaller the Frobenius distance, the more diversified. Off-diagonal-only
    equivalently, since diagonals cancel.

    Args:
        corr: Asset correlation matrix (square).

    Returns:
        Frobenius norm of (corr - I); 0.0 for empty/1x1 input.
    """
    if corr is None or corr.shape[0] <= 1:
        return 0.0
    cm = corr.to_numpy(dtype=float)
    im = np.eye(cm.shape[0])
    return float(np.sqrt(np.nansum((cm - im) ** 2)))
