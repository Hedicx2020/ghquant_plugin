# r004 code audit common signatures

## common/utils.py

- `winsorize(series, lower_quantile=..., upper_quantile=...)`
- `standardize(series)` / `standardize_factor(...)`
- `neutralize_factor(...)`
- `calculate_sharpe(...)`
- `calculate_annualized_return(...)`
- `calculate_annualized_volatility(...)`
- `calculate_max_drawdown(nav)`
- `calculate_win_rate(returns)`
- `performance_summary(...)`

## common/backtest.py

- `calculate_ic(factor, future_returns)`
- `calculate_rank_ic(factor, future_returns)`
- `calculate_ic_series(...)`
- `ic_summary(ic_series, periods_per_year=12)`
- `assign_quantile_groups(...)`
- `quantile_backtest(...)`
- `long_short_backtest(...)`
- `performance_analysis(...)`

## common/data_loader.py

- `get_data_root()`
- `load_stock_price(...)` / `load_stock_price_forward(...)`
- `load_stock_trade(...)`
- `load_suspend(...)` / `load_suspend_status(...)`
- `load_st_data(...)`
- `load_trade_calendar(...)`
- `get_month_end_trading_days(...)`
- `filter_st_stocks(...)` / `filter_suspended(...)`
- `load_limit_status(...)`

说明：审计者如需函数体，应直接只读检查 `common/` 源文件；本摘要只用于定位可复用接口。
