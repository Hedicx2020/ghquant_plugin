# r007 code audit · common signatures

生成时间：2026-07-27。仅列本案例直接相关的公共接口；外审可继续只读打开对应源文件。

## common/ml_pipeline.py

- `build_features(panel, feature_cfg) -> DataFrame`
- `prepare_point_in_time_ml_data(...) -> PreparedMLData`
- `fit_regression_model_batch(...) -> RegressionBatchResult`
- `append_prediction_ensembles(...) -> DataFrame`
- `snapshot_estimator_params(estimator) -> dict`
- `extract_estimator_feature_values(...) -> DataFrame`

## common/ml_portfolio.py

- `SignedLiquidityPortfolioSettings`
- `SignedLiquidityPortfolioResult`
- `run_signed_liquidity_portfolios(...) -> SignedLiquidityPortfolioResult`
- `prepare_factor_panel(...) -> DataFrame`
- `calculate_prediction_diagnostics(...) -> tuple`
- `run_multi_path_factor_backtest(...) -> MLPortfolioResult`

## common/ml_reporting.py

- `write_json(path, payload, indent) -> None`
- `build_ml_metrics(...) -> dict`
- `build_ml_chart_data(...) -> dict[str, DataFrame]`
- `create_ml_charts(...) -> dict`
- `write_backtest_workbook(...) -> None`
- `write_detail_tables(...) -> None`

## common/data_loader.py

- `get_data_root() -> Path`
- `load_stock_price_forward(...) -> DataFrame`
- `load_stock_trade(...) -> DataFrame`
- `load_industry(...) -> DataFrame`
- `load_trade_calendar(...) -> DataFrame`
- `filter_st_stocks(...) -> DataFrame`
- `filter_suspended(...) -> DataFrame`
- `get_stock_universe(...) -> list[str]`

## common/utils.py

- `winsorize(...) -> Series`
- `standardize(...) -> Series`
- `calculate_sharpe(...) -> float`
- `ols_univariate(...) -> OLSFit`

## common/backtest.py

- `calculate_ic(...) -> float`
- `calculate_rank_ic(...) -> float`
- `quantile_backtest(...) -> tuple`
- `long_short_backtest(...) -> DataFrame`
- `performance_analysis(...) -> dict`
