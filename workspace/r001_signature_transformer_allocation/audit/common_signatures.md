# common 函数签名摘要（code_audit 复用核查用）
## common/__init__.py
## common/allocation_backtest.py
49:def simplex_projection(v: np.ndarray) -> np.ndarray:
74:def _normalize_long(w: np.ndarray) -> np.ndarray:
81:def cov_to_corr(cov: pd.DataFrame) -> pd.DataFrame:
90:def _ridge_cov(cov: pd.DataFrame, ridge: float = COV_RIDGE) -> np.ndarray:
101:def equal_weights(assets: Sequence[str]) -> pd.Series:
117:def mean_variance_weights(
148:    def neg_utility(w: np.ndarray) -> float:
151:    def neg_utility_grad(w: np.ndarray) -> np.ndarray:
167:def _risk_contributions(w: np.ndarray, sigma: np.ndarray) -> np.ndarray:
172:def risk_parity_weights(cov: pd.DataFrame) -> pd.Series:
208:def risk_budget_weights(cov: pd.DataFrame, budget: pd.Series) -> pd.Series:
247:def _corr_distance(corr: pd.DataFrame) -> np.ndarray:
254:def _quasi_diag(link: np.ndarray) -> list[int]:
271:def _cluster_var(cov: pd.DataFrame, items: list[str]) -> float:
279:def hrp_weights(cov: pd.DataFrame) -> pd.Series:
317:def herc_weights(cov: pd.DataFrame) -> pd.Series:
341:    def _erc_cluster_var(items: list[str]) -> float:
362:def _min_variance_weights(cov: pd.DataFrame) -> pd.Series:
385:def nco_weights(cov: pd.DataFrame, exp_ret: Optional[pd.Series] = None,
448:def olmar_weights(
494:def portfolio_backtest(
571:def rolling_cov_estimate(
595:def _smoke() -> None:
## common/backtest.py
54:def calculate_ic(
73:def calculate_rank_ic(
93:def calculate_ic_series(
124:def ic_summary(ic_series: pd.Series, periods_per_year: int = 12) -> dict:
154:def assign_quantile_groups(
175:    def _assign(g: pd.DataFrame) -> pd.Series:
190:def quantile_backtest(
278:def long_short_backtest(
328:def performance_analysis(
412:def _save_charts(
535:def _save_excel(
597:    def _embed_image(ws, img_path: Path, anchor: str = "H2") -> None:
## common/data_loader.py
18:def get_data_root() -> Path:
47:def load_stock_price(
67:def load_stock_price_forward(
104:def load_stock_trade(
124:def load_suspend(data_dir: Path = LOCAL_DATA_DIR) -> pd.DataFrame:
136:def load_st_data(data_dir: Path = LOCAL_DATA_DIR) -> pd.DataFrame:
149:def load_industry(
168:def load_trade_calendar(
195:def load_index_components(
220:def get_month_end_trading_days(
240:def filter_st_stocks(
263:def filter_suspended(
288:def get_stock_universe(
331:def load_market_data(
375:def get_index_members_on_date(
397:def _range_code_filters(
410:def load_suspend_status(
437:def load_limit_status(
## common/timing_backtest.py
33:def signal_backtest(
83:def _reconstruct_returns(nav: pd.Series) -> pd.Series:
91:def timing_metrics(
## common/utils.py
23:def winsorize(
56:def standardize(series: pd.Series) -> pd.Series:
71:def neutralize_factor(
129:def standardize_factor(
173:def calculate_sharpe(
194:def calculate_annualized_return(
214:def calculate_annualized_volatility(
230:def calculate_max_drawdown(nav: pd.Series) -> float:
244:def calculate_win_rate(returns: pd.Series) -> float:
258:def calculate_calmar(
277:def performance_summary(
310:class OLSFit(NamedTuple):
325:def ols_univariate(
382:def calculate_arithmetic_annual_return(
404:def downside_deviation(
425:def calculate_sortino(
455:def calculate_modigliani(
483:def calculate_psr(
522:def calculate_historical_var(
544:def frobenius_diversification(corr: pd.DataFrame) -> float:
