# common 公共函数签名摘要

- `common.utils`: `winsorize`, `standardize`, `neutralize_factor`, `standardize_factor`, `calculate_sharpe`, `calculate_annualized_return`, `calculate_annualized_volatility`, `calculate_max_drawdown`, `performance_summary`
- `common.backtest`: `calculate_ic`, `calculate_rank_ic`, `calculate_ic_series`, `ic_summary`, `assign_quantile_groups`, `quantile_backtest`, `long_short_backtest`, `performance_analysis`
- `common.data_loader`: `load_stock_price_forward`, `load_stock_trade`, `load_suspend_status`, `load_limit_status`, `load_trade_calendar`, `load_index_components`, `get_month_end_trading_days`, `get_stock_universe`, `get_index_members_on_date`
- `common.ml_pipeline`: `build_features`, `build_forward_return_labels`, `build_point_in_time_universe`, `build_window_index`, `fit_feature_preprocessor`, `transform_features`, `prepare_point_in_time_ml_data`
- `common.ml_reporting`: `write_json`, `build_ml_metrics`, `build_ml_chart_data`, `create_ml_charts`, `write_backtest_workbook`, `write_detail_tables`
- `common.ml_portfolio`: `prepare_factor_panel`, `calculate_prediction_diagnostics`, `run_multi_path_factor_backtest`

