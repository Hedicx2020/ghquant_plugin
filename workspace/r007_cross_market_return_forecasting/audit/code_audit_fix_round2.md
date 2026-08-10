# r007 code_audit 第 2 轮定点修复记录

- 修复范围：`impl_audit_mall.md` 的 `CA-ALL-R1-01`、`CA-ALL-R1-02`、`CA-ALL-R1-03`。
- 规划依据：`audit/code_audit_round2_planning.md`；FIG3 降级口径使用 planner 已登记的 `AS27`。
- 边界：本文件只记录实现合同与冒烟证据，不给出 code_audit、复现结果或门禁通过判定。
- 正式运行边界：未运行无参正式流水线，未生成或改写 `output/r007_cross_market_return_forecasting/results/`、`verify_report.md` 或正式比较结果。

## CA-ALL-R1-01：按 AS2/AS14 生成动态可预测键

### 修改位置

- `src/r007_cross_market_return_forecasting/model_pipeline.py:_graph_target_eligibility/predict_graph_snapshot`
- `src/r007_cross_market_return_forecasting/backtest_pipeline.py:_build_autoregressive_feature_panel/iter_non_graph_autoregressive_predictions`
- `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:audit_formal_prediction_coverage/run_m4_portfolios`
- `src/r007_cross_market_return_forecasting/main.py:_stage_m2_m3/_prepare_cross_predictions/_collect_same_market_predictions/_collect_non_graph_predictions/_stage_m4/_run_sa3`

### 实现合同

- 图规格按每个快照、预测日和目标股票独立生成机会键，不从模型实际输出反推资格。
- 非图 25 日自回归规格按每个更新块、预测日和目标股票生成同结构机会键。
- 逐键资格表包含：
  - `direction`
  - `prediction_date`
  - `snapshot_date`
  - `target_code`
  - `specification`
  - `graph_has_in_edges`
  - `feature_count`
  - `complete_case_nobs`
  - `min_required_nobs`
  - `eligibility_status`
  - `exclusion_reason`
- `eligibility_status` 仅允许 `predictable` 或 `legally_excluded`；合法排除原因仅允许：
  - `no_in_edges`
  - `complete_case_insufficient`
  - `required_observation_missing`
- 必要观测同时核对预测特征、实现收益和预测日前历史流动性；完整样本数与最小样本数独立于模型成功与否计算。
- 全 B1 目标股票池仍逐日进入机会全集并作为缺失率分母，不再要求每只股票每日必须预测。
- 对每个动态 `predictable` 基础键，M4 强制模型集合精确等于八个基础模型加两个集成模型：
  - 不得缺模型；
  - 不得重复模型键；
  - 不得出现未知模型；
  - 三个组合输入数值必须有限。
- 模型若在已登记的合法排除键上仍产生预测，组合出口仅按资格审计移除该输出，同时在逐键审计中保留原始输出行数和 `output_removed_by_legal_exclusion`；资格机会全集之外的输出仍硬失败。
- 逐日及全样本审计均输出：
  - 机会数；
  - 无入边数/率；
  - complete-case 样本不足数/率；
  - 必要观测缺失数/率；
  - 动态可预测数/率；
  - 实际十模型完整键数/率。
- 任一整日动态可预测键为零、机会全集逐日不完整、未登记排除原因、动态可预测键与十模型输出集合不相等时抛出 `FormalCoverageError`。
- 三规格先分别完成资格和十模型审计，再以三个已审计集合显式求交；逐键披露各规格资格、排除原因、是否进入共同集合以及共同键收缩原因。
- 未新增覆盖率容忍参数；所有比例仅作诊断，集合精确相等才是门禁。
- SA3 复用 M3 的 `US_TO_CN` 动态资格审计：
  - 111 个配置分别要求实际预测键精确等于动态可预测键；
  - 合法排除键输出只在保留计数后移出组合出口；
  - 资格全集外输出、缺少动态键、额外动态键、配置间键不一致均在组合计算前停止；
  - 取消“每日全 500 股票零缺口”的过严门禁。
- M3 动态资格表、M4 正式覆盖审计和 SA3 网格审计均进入既有检查点/正式证据接口。

### 隔离冒烟证据

- 图规格：
  - 用 270 个合成交易日生成一个 `US_TO_CN` 快照；
  - 训练 complete-case 为 250 行；
  - 单个动态可预测键产生且仅产生十模型输出。
- 非图规格：
  - 两只股票、280 个交易日、25 日滞后、250 日训练；
  - 20 个机会键全部判为动态可预测；
  - 每键均产生十模型输出。
- M4 动态资格：
  - 合成三规格、两市场、两日期、四股票、十模型面板；
  - 显式共同键与组合输入一致，生成 480 行可比预测；
  - 删除一个动态可预测键的模型输出后触发 `FormalCoverageError`；
  - `required_observation_missing` 键上的原始模型输出被记录为合法排除输出，不会被误判为未登记缩水。

## CA-ALL-R1-02：FIG3 精确日期全量 B1 代理图

### 修改位置

- `src/r007_cross_market_return_forecasting/config.py:ReportingConfig`
- `src/r007_cross_market_return_forecasting/main.py:_build_fig03_graph_evidence/_build_chart_tables/run_formal_pipeline`
- `src/r007_cross_market_return_forecasting/reporting.py:create_result_charts/write_formal_outputs`

### 实现合同

- FIG3 专用入口固定 `prediction_start=prediction_end=2021-10-21`，单独调用滚动图构造，不读取正式十日更新快照，也不执行最近锚点选择。
- 必须且只能生成一个 `anchor_date=2021-10-21` 的快照。
- 训练映射必须恰好包含 250 个历史交易配对，且所有训练目标日严格早于 `2021-10-21`；否则硬失败，不回退邻近日期。
- 内部稀疏矩阵为源 US ×目标 CN；输出前显式转置为行 CN、列 US。
- 依照 AS27，仅输出精确日期的全量 B1 代理图，不伪造 D9 缺失的双市场行业限额子集。
- 机器可读口径表包含：
  - `paper_requested_date`
  - `effective_graph_date`
  - `used_nearest_update_anchor=false`
  - `paper_universe=industry_capped_254_us_x_235_cn`
  - `implemented_universe=full_b1_proxy`
  - `industry_limit_applied=false`
  - `missing_dependency=D9`
  - `reproduction_status=degraded/substitute`
  - `assumption_id=AS27`
  - 内部/输出行列方向；
  - 论文行列数与实际代理节点数；
  - 行列节点有序 JSON 清单及各自 SHA256；
  - 训练源/目标日期范围、250 配对数和严格历史标志；
  - 带有序行列标签的矩阵数据 SHA256。
- 热图标题改为“2021-10-21 全量 B1 代理图（degraded/substitute, AS27）”。
- `ml_core_results.xlsx` 的矩阵 sheet 改为 `FIG3全量B1代理_degraded`，另写 `FIG3代理口径_degraded` 口径 sheet。
- 正式 `metrics.json` 与 `run_log.md` 接口增加 FIG3 的精确日期、非邻近锚点、D9、AS27 和 `degraded/substitute` 字段/文本。
- 论文 254×235 仅作为事实写入口径清单，不作为代理矩阵实际维度门禁。

### 隔离冒烟证据

- 使用 270 个合成交易日、2 个 US 节点、3 个 CN 节点运行专用入口：
  - `paper_requested_date=effective_graph_date=2021-10-21`；
  - `used_nearest_update_anchor=false`；
  - 训练目标日为 `2020-11-05` 至 `2021-10-20`；
  - 训练配对数为 250；
  - 输出矩阵为 3 行 CN × 2 列 US；
  - `D9`、`AS27`、`degraded/substitute` 与全部哈希字段存在。

## CA-ALL-R1-03：R2 聚合前完整 666 行门禁

### 修改位置

- `src/r007_cross_market_return_forecasting/config.py:SensitivityConfig`
- `src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:R2ConfigurationCoverageError/build_hyperparameter_grid/summarize_hyperparameter_sharpe/build_r2_comparison`
- `src/r007_cross_market_return_forecasting/main.py:_run_sa3`

### 实现合同

- 集中配置记录 111 个超参数配置与 42 个 R2 参考格。
- R2 聚合前先构造 111 配置 × qr1–qr6 的 666 行先验表，附期望模型与 `parameters_json`。
- 实际出口必须：
  - 恰好 666 行；
  - `configuration_id × portfolio` 唯一；
  - 配置属于登记网格；
  - 每行模型归属正确；
  - `sharpe_status == ok`；
  - `annualized_sharpe` 为有限值。
- 不再过滤无效 Sharpe 后聚合；任一失败行通过 `R2ConfigurationCoverageError.audit` 保留在未过滤逐行审计表并立即停止。
- 只有完整 666 行通过后才计算模型×组合均值、标准差、最小值和最大值。
- 42 个模型×组合格的 `configuration_set_complete` 必须全部为真。
- R2 参考表使用 outer merge；必须恰好 42 行且 `reference_merge_status` 全部为 `both`，复现均值/标准差全部有限，否则停止生成 R2 比较。

### 隔离冒烟证据

- 111×6 合成正例生成：
  - 666 行逐配置审计；
  - 42 行模型×组合汇总；
  - 42 行参考逐格合并；
  - `reference_merge_status` 全部为 `both`。
- 以下五类负例均在聚合前硬失败：
  - 缺少一行；
  - 重复一行；
  - Sharpe 非有限；
  - `sharpe_status != ok`；
  - 模型归属错误。
- 缺一行负例的 `R2ConfigurationCoverageError.audit` 仍保留完整 666 个先验格及失败行状态。

## 覆盖矩阵回填

- 修改位置：`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md`
- 更新要素：F8、F9、F22。
- 已存在且继续有效的真实位置：F4、F5、B7、B11、R2、SA3。
- 回填规则：只补充真实存在的 `文件:函数`；状态保持 `done`，最后更新保持 `implement`，验证结果列保持空白。

## 冒烟命令与结果

1. `uv run python -m compileall -q src/r007_cross_market_return_forecasting common/data_loader.py common/ml_pipeline.py common/ml_portfolio.py common/ml_reporting.py common/backtest.py common/utils.py`
   - 结果：退出码 0。
2. `uv run python -m src.r007_cross_market_return_forecasting.main --smoke`
   - 结果：退出码 0；既有 CA-A01–CA-A08、SA4-DTYPE 与 CLI 动态检查均完成。
   - 隔离产物：`workspace/r007_cross_market_return_forecasting/smoke/artifact_manifest.json`。
3. 新增合同隔离 smoke：
   - 图/非图动态资格、M4 三规格显式交集、合法排除输出、缺模型负例完成；
   - FIG3 精确日期、250 期历史、行列方向与降级口径完成；
   - R2 666 行正例及五类负例完成。
4. `uv run ruff check ...`
   - 环境未安装 `ruff`，命令无法启动；未把工具缺失解释为代码审计结论。

## 未解决项与裁决边界

- 本轮三项修复范围内没有已知遗留实现项。
- FIG3 的原论文行业限额 254×235 对象仍因 D9 缺失不可忠实重建；本轮只按 AS27 交付精确日期的全量 B1 代理图，并明确标记降级。
- 按 quant-coder 边界未运行正式全量回测，未形成任何验证结论；正式运行对数、结果偏差与门禁裁决留给 verifier 与 check_gates。
