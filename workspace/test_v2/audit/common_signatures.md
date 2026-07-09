# common/ 函数签名摘要（code_audit 备料）

## common/utils.py
23: def winsorize(
56: def standardize(series: pd.Series) -> pd.Series:
71: def neutralize_factor(
129: def standardize_factor(
173: def calculate_sharpe(
194: def calculate_annualized_return(
214: def calculate_annualized_volatility(
230: def calculate_max_drawdown(nav: pd.Series) -> float:
244: def calculate_win_rate(returns: pd.Series) -> float:
258: def calculate_calmar(
277: def performance_summary(

## common/backtest.py
54: def calculate_ic(
73: def calculate_rank_ic(
93: def calculate_ic_series(
124: def ic_summary(ic_series: pd.Series, periods_per_year: int = 12) -> dict:
154: def assign_quantile_groups(
190: def quantile_backtest(
278: def long_short_backtest(
328: def performance_analysis(
412: def _save_charts(
535: def _save_excel(

## common/data_loader.py
24: def load_stock_price(
44: def load_stock_trade(
64: def load_suspend(data_dir: Path = LOCAL_DATA_DIR) -> pd.DataFrame:
76: def load_st_data(data_dir: Path = LOCAL_DATA_DIR) -> pd.DataFrame:
89: def load_industry(
108: def load_trade_calendar(
135: def load_index_components(
160: def get_month_end_trading_days(
180: def filter_st_stocks(
203: def filter_suspended(
228: def get_stock_universe(
271: def load_market_data(

## common/timing_backtest.py
33: def signal_backtest(
83: def _reconstruct_returns(nav: pd.Series) -> pd.Series:
91: def timing_metrics(

