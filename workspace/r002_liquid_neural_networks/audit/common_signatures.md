# common 公共入口签名实证摘要

## 生成口径

- 范围：案例实际引用的 `common/utils.py`、`common/ml_pipeline.py`、`common/ml_training.py`、`common/ml_liquid.py`、`common/ml_portfolio.py`、`common/ml_reporting.py`。
- 方法：运行时导入当前工作区模块，仅收录 `__module__` 等于目标模块、名称不以下划线开头的顶层函数和类；签名取 `inspect.signature(obj, eval_str=False)` 原值。以下引号来自 `from __future__ import annotations` 的字符串化注解，不代表推测。
- 默认值和返回类型均按当前源代码实证；没有以调用方常用值替代函数默认值。例如 `calculate_sharpe` 与 `calculate_annualized_return` 的真实默认年化周期是12，本案例回测调用方另行显式传入252。
- 源文件 SHA-256：
  - `common/utils.py`：`534ae84994248655501012d9dac50391a5b5fab10739acf7066f072b4c4e6c6d`
  - `common/ml_pipeline.py`：`6d9085abee65bccd6b9d0613ee90fae6ebe23be4e0fb0722c9a6e0ac1e9573a3`
  - `common/ml_training.py`：`955c4e546a69fe24a9eb713a5f7c7eeae1f5649a95fdc992fc1094d0f2206b6a`
  - `common/ml_liquid.py`：`ecf4f03501cd626738d43ba5ad251a833f4cfd03a28f218fdc21cbcbda703851`
  - `common/ml_portfolio.py`：`d0a9207534e90f0a2eec82f9429e6eaa6a3c6b66410552e47c4b0a1045b04dc0`
  - `common/ml_reporting.py`：`c542252ecf03e846e4898042337f1bd714304266fee4ccb4fe4d7274b12c5bdb`

## common/utils.py

### 公共函数

- `winsorize(series: 'pd.Series', method: 'str' = 'mad', n_sigma: 'float' = 3.0, mad_multiplier: 'float' = 1.4826) -> 'pd.Series'`
- `standardize(series: 'pd.Series') -> 'pd.Series'`
- `neutralize_factor(factor: 'pd.Series', *, market_cap: 'Optional[pd.Series]' = None, industry: 'Optional[pd.Series]' = None) -> 'pd.Series'`
- `standardize_factor(factor_df: 'pd.DataFrame', factor_col: 'str' = 'factor', date_col: 'str' = 'date', market_cap_col: 'Optional[str]' = None, industry_col: 'Optional[str]' = None, winsorize_method: 'str' = 'mad') -> 'pd.DataFrame'`
- `calculate_sharpe(returns: 'pd.Series', rf: 'float' = 0.0, periods_per_year: 'int' = 12) -> 'float'`
- `calculate_annualized_return(returns: 'pd.Series', periods_per_year: 'int' = 12) -> 'float'`
- `calculate_annualized_volatility(returns: 'pd.Series', periods_per_year: 'int' = 12) -> 'float'`
- `calculate_max_drawdown(nav: 'pd.Series') -> 'float'`
- `calculate_win_rate(returns: 'pd.Series') -> 'float'`
- `calculate_calmar(returns: 'pd.Series', periods_per_year: 'int' = 12) -> 'float'`
- `performance_summary(returns: 'pd.Series', periods_per_year: 'int' = 12, name: 'str' = '') -> 'dict'`
- `ols_univariate(x: 'Union[Sequence[float], NDArray]', y: 'Union[Sequence[float], NDArray]', min_obs: 'int' = 3) -> 'OLSFit'`
- `calculate_arithmetic_annual_return(returns: 'pd.Series', periods_per_year: 'int' = 12) -> 'float'`
- `downside_deviation(returns: 'pd.Series', target: 'float' = 0.0) -> 'float'`
- `calculate_sortino(returns: 'pd.Series', rf: 'float' = 0.0, periods_per_year: 'int' = 12, target: 'Optional[float]' = None) -> 'float'`
- `calculate_modigliani(returns: 'pd.Series', benchmark_returns: 'pd.Series', rf: 'float' = 0.0, periods_per_year: 'int' = 12) -> 'float'`
- `calculate_psr(returns: 'pd.Series', rf: 'float' = 0.0, sr_benchmark: 'float' = 0.0) -> 'float'`
- `calculate_historical_var(returns: 'pd.Series', level: 'float' = 0.05) -> 'float'`
- `frobenius_diversification(corr: 'pd.DataFrame') -> 'float'`

### 公共类

- `OLSFit(alpha: ForwardRef('float'), beta: ForwardRef('float'), beta_se: ForwardRef('float'), beta_t: ForwardRef('float'), beta_pvalue: ForwardRef('float'), n_obs: ForwardRef('int'))`

## common/ml_pipeline.py

### 公共函数

- `build_features(panel: 'pd.DataFrame', feature_cfg: 'Mapping[str, Any]') -> 'pd.DataFrame'`
- `derive_forward_adjusted_vwap(panel: 'pd.DataFrame', *, forward_close_col: 'str', raw_close_col: 'str', raw_low_col: 'str', raw_high_col: 'str', volume_col: 'str', turn_value_col: 'str', output_col: 'str', sanity_min_price_ratio: 'float', sanity_max_price_ratio: 'float', sanity_min_fraction: 'float') -> 'tuple[pd.DataFrame, dict[str, float]]'`
- `build_forward_return_labels(panel: 'pd.DataFrame', trade_calendar: 'pd.DataFrame', *, vwap_col: 'str', entry_offset: 'int', exit_offset: 'int', label_col: 'str' = 'label') -> 'pd.DataFrame'`
- `build_point_in_time_universe(panel: 'pd.DataFrame', stock_master: 'pd.DataFrame', st_intervals: 'pd.DataFrame', *, minimum_listing_years: 'int') -> 'pd.DataFrame'`
- `attach_entry_tradability(samples: 'pd.DataFrame', suspend_status: 'pd.DataFrame', limit_status: 'pd.DataFrame') -> 'pd.DataFrame'`
- `build_window_index(features: 'pd.DataFrame', trade_calendar: 'pd.DataFrame', *, feature_columns: 'Sequence[str]', window_length: 'int') -> 'tuple[pd.DataFrame, pd.DataFrame]'`
- `assign_non_overlapping_splits(samples: 'pd.DataFrame', segments: 'Sequence[DateSegment]') -> 'pd.DataFrame'`
- `fit_feature_preprocessor(feature_panel: 'pd.DataFrame', *, feature_columns: 'Sequence[str]', fit_mask: 'pd.Series | np.ndarray', lower_quantile: 'float', upper_quantile: 'float', std_epsilon: 'float') -> 'FeaturePreprocessor'`
- `transform_features(feature_panel: 'pd.DataFrame', preprocessor: 'FeaturePreprocessor') -> 'pd.DataFrame'`
- `prepare_point_in_time_ml_data(panel: 'pd.DataFrame', stock_master: 'pd.DataFrame', st_intervals: 'pd.DataFrame', suspend_status: 'pd.DataFrame', limit_status: 'pd.DataFrame', trade_calendar: 'pd.DataFrame', *, feature_cfg: 'Mapping[str, Any]', vwap_col: 'str', entry_offset: 'int', exit_offset: 'int', window_length: 'int', minimum_listing_years: 'int', segments: 'Sequence[DateSegment]', train_split_name: 'str', label_required_splits: 'Sequence[str] | None' = None, allow_missing_label_splits: 'Sequence[str]' = (), lower_quantile: 'float', upper_quantile: 'float', std_epsilon: 'float') -> 'PreparedMLData'`

### 公共类

- `DateSegment(name: 'str', start: 'pd.Timestamp', end: 'pd.Timestamp') -> None`
- `FeaturePreprocessor(feature_columns: 'tuple[str, ...]', lower: 'pd.Series', upper: 'pd.Series', mean: 'pd.Series', std: 'pd.Series', fit_row_count: 'int', fit_start: 'pd.Timestamp', fit_end: 'pd.Timestamp', lower_quantile: 'float', upper_quantile: 'float') -> None`
- `PreparedMLData(feature_panel: 'pd.DataFrame', samples: 'pd.DataFrame', feature_columns: 'tuple[str, ...]', preprocessor: 'FeaturePreprocessor', quality_summary: 'dict[str, Any]') -> None`
- `PanelWindowDataset(feature_panel: 'pd.DataFrame', samples: 'pd.DataFrame', feature_columns: 'Sequence[str]') -> 'None'`

## common/ml_training.py

### 公共函数

- `build_gru_regressor(*, input_size: 'int', hidden_size: 'int', num_layers: 'int', dropout: 'float', output_size: 'int') -> 'SequenceRegressor'`
- `set_reproducible_seed(seed: 'int', *, deterministic_warn_only: 'bool') -> 'None'`
- `resolve_device(requested: 'str') -> 'torch.device'`
- `summarize_model_resources(model: 'nn.Module', *, device: 'torch.device') -> 'dict[str, Any]'`
- `train_sequence_regressor(model_factory: 'Callable[[], nn.Module]', *, train_dataset: 'SequenceRegressionDataset', validation_dataset: 'SequenceRegressionDataset', settings: 'TrainingSettings', checkpoint_path: 'Path', model_metadata: 'dict[str, Any] | None' = None) -> 'TrainingResult'`
- `predict_sequence_regressor(model: 'nn.Module', *, dataset: 'SequenceRegressionDataset', batch_size: 'int', seed: 'int', num_workers: 'int', device: 'str') -> 'np.ndarray'`
- `load_model_checkpoint(model: 'nn.Module', checkpoint_path: 'Path', *, map_location: 'str' = 'cpu') -> 'dict[str, Any]'`

### 公共类

- `SequenceRegressionDataset(*args, **kwargs)`
- `TrainingSettings(batch_size: 'int', learning_rate: 'float', max_epochs: 'int', patience: 'int', seed: 'int', loss_name: 'str', optimizer_name: 'str', weight_decay: 'float', min_delta: 'float', num_workers: 'int', shuffle_training: 'bool', device: 'str', deterministic_warn_only: 'bool') -> None`
- `TrainingHistory(train_loss: 'tuple[float, ...]', validation_loss: 'tuple[float, ...]', best_epoch: 'int', best_validation_loss: 'float', stopped_early: 'bool', epochs_completed: 'int') -> None`
- `TrainingResult(model: 'nn.Module', history: 'TrainingHistory', resource_summary: 'dict[str, Any]', checkpoint_path: 'Path') -> None`
- `GRUBackbone(*, input_size: 'int', hidden_size: 'int', num_layers: 'int', dropout: 'float') -> 'None'`
- `SequenceRegressor(backbone: 'nn.Module', *, backbone_output_size: 'int', output_size: 'int') -> 'None'`

## common/ml_liquid.py

### 公共函数

- `neural_ode_derivative(hidden: 'torch.Tensor', time: 'torch.Tensor', vector_field: 'VectorField') -> 'torch.Tensor'`
- `euler_residual_step(hidden: 'torch.Tensor', time: 'torch.Tensor', step_size: 'torch.Tensor', vector_field: 'VectorField') -> 'torch.Tensor'`
- `integrate_neural_ode_euler(initial_hidden: 'torch.Tensor', time_points: 'torch.Tensor', vector_field: 'VectorField') -> 'torch.Tensor'`
- `build_liquid_regressor(model_kind: 'LiquidModelKind', *, input_size: 'int', units: 'int', output_size: 'int', wiring_output_size: 'int', sparsity_level: 'float', wiring_seed: 'int', batch_first: 'bool', return_sequences: 'bool', mixed_memory: 'bool', ode_unfolds: 'int', cfc_mode: 'str') -> 'SequenceRegressor'`
- `summarize_liquid_wiring(model: 'nn.Module') -> 'dict[str, Any]'`
- `assert_ncps_version(expected_version: 'str') -> 'str'`
- `build_liquid_model_manifest(models: 'Mapping[str, SequenceRegressor]', *, expected_version: 'str', source_url: 'str', source_commit: 'str', source_license: 'str', method_scope: 'str') -> 'list[dict[str, Any]]'`

### 公共类

- `NcpsSequenceBackbone(*, model_kind: 'LiquidModelKind', recurrent_layer: 'nn.Module', output_size: 'int', wiring: 'Wiring | None', batch_first: 'bool', return_sequences: 'bool', mixed_memory: 'bool') -> 'None'`

## common/ml_portfolio.py

### 公共函数

- `prepare_factor_panel(predictions: 'pd.DataFrame', settings: 'MLPortfolioSettings') -> 'pd.DataFrame'`
- `assign_descending_quantile_groups(factor_panel: 'pd.DataFrame', settings: 'MLPortfolioSettings') -> 'pd.DataFrame'`
- `calculate_prediction_diagnostics(factor_panel: 'pd.DataFrame', settings: 'MLPortfolioSettings') -> 'tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]'`
- `build_rank_ic_path_aggregates(rank_ic: 'pd.DataFrame', trade_calendar: 'pd.DataFrame', settings: 'MLPortfolioSettings') -> 'tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]'`
- `run_multi_path_factor_backtest(predictions: 'pd.DataFrame', market_panel: 'pd.DataFrame', trade_calendar: 'pd.DataFrame', settings: 'MLPortfolioSettings') -> 'MLPortfolioResult'`

### 公共类

- `MLPortfolioSettings(model_col: 'str', stock_col: 'str', signal_date_col: 'str', prediction_col: 'str', forward_return_col: 'str', market_date_col: 'str', market_price_col: 'str', market_tradable_col: 'str', n_groups: 'int', expected_model_count: 'int', path_offsets: 'tuple[int, ...]', rebalance_interval: 'int', entry_offset: 'int', exit_offset: 'int', sell_fee_rate: 'float', initial_capital: 'float', periods_per_year: 'int', risk_free_rate_per_day: 'float', factor_correlation_method: 'str', min_cross_section_size: 'int', share_epsilon: 'float') -> None`
- `MLPortfolioResult(factor_panel: 'pd.DataFrame', factor_correlation: 'pd.DataFrame', factor_correlation_by_date: 'pd.DataFrame', rank_ic: 'pd.DataFrame', rank_ic_path_series: 'pd.DataFrame', rank_ic_path_summary: 'pd.DataFrame', rank_ic_path_aggregate: 'pd.DataFrame', group_assignments: 'pd.DataFrame', path_holdings: 'pd.DataFrame', path_trades: 'pd.DataFrame', path_nav: 'pd.DataFrame', portfolio_returns: 'pd.DataFrame', path_metrics: 'pd.DataFrame', annual_metrics: 'pd.DataFrame', path_metric_aggregate: 'pd.DataFrame', path_daily_aggregate: 'pd.DataFrame', monotonicity: 'pd.DataFrame') -> None`

## common/ml_reporting.py

### 公共函数

- `write_json(path: 'Path', payload: 'Any', *, indent: 'int') -> 'None'`
- `calculate_gradient_feature_importance(models: 'Mapping[str, Any]', dataset: 'Sequence[Any]', feature_names: 'Sequence[str]', *, batch_size: 'int') -> 'pd.DataFrame'`
- `calculate_model_factor_correlation(factor_panel: 'pd.DataFrame', *, model_names: 'Sequence[str]', method: 'str', min_common: 'int', min_unique_values: 'int', sample_scope: 'str') -> 'tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]'`
- `build_report_reference_tables(*, report_gpu_memory_gb: 'Sequence[tuple[str, float]]', report_performance: 'Sequence[tuple[str, str, str, float, float]]') -> 'tuple[pd.DataFrame, pd.DataFrame]'`
- `build_ml_metrics(*, run_metadata: 'Mapping[str, Any]', sample_coverage: 'pd.DataFrame', resource_summary: 'pd.DataFrame', loss_curves: 'pd.DataFrame', portfolio: 'MLPortfolioResult', factor_correlation: 'pd.DataFrame', factor_correlation_pairs: 'pd.DataFrame', factor_correlation_by_date: 'pd.DataFrame', feature_importance: 'pd.DataFrame', report_ltc_improvement_range: 'tuple[float, float]', report_factor_correlation_range: 'tuple[float, float]', report_resource_reference: 'pd.DataFrame', report_performance_reference: 'pd.DataFrame', output_boundaries: 'Mapping[str, Any]') -> 'tuple[dict[str, Any], pd.DataFrame]'`
- `build_ml_chart_data(*, portfolio: 'MLPortfolioResult', factor_correlation: 'pd.DataFrame', loss_curves: 'pd.DataFrame', resource_summary: 'pd.DataFrame', feature_importance: 'pd.DataFrame', plot_point_limit: 'int', seed: 'int') -> 'dict[str, pd.DataFrame]'`
- `create_ml_charts(*, output_dir: 'Path', chart_data: 'Mapping[str, pd.DataFrame]', title_prefix: 'str', dpi: 'int', time_series_size: 'tuple[float, float]', standard_size: 'tuple[float, float]', primary_blue: 'str', primary_red: 'str', neutral_gray: 'str') -> 'dict[str, Path]'`
- `write_backtest_workbook(*, path: 'Path', comparison: 'pd.DataFrame', rank_ic_summary: 'pd.DataFrame', portfolio: 'MLPortfolioResult', factor_correlation_pairs: 'pd.DataFrame', label_coverage_summary: 'pd.DataFrame', label_coverage_by_date: 'pd.DataFrame', report_resource_reference: 'pd.DataFrame', report_performance_reference: 'pd.DataFrame', data_audit_tables: 'Mapping[str, pd.DataFrame]', chart_data: 'Mapping[str, pd.DataFrame]', chart_paths: 'Mapping[str, Path]', row_limit: 'int') -> 'None'`
- `write_detail_tables(*, output_dir: 'Path', predictions: 'pd.DataFrame', portfolio: 'MLPortfolioResult', factor_correlation: 'pd.DataFrame', factor_correlation_pairs: 'pd.DataFrame', factor_correlation_by_date: 'pd.DataFrame', label_coverage_summary: 'pd.DataFrame', label_coverage_by_date: 'pd.DataFrame', chart_data: 'Mapping[str, pd.DataFrame]') -> 'dict[str, Path]'`
