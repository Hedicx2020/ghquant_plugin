# r007 code_audit 第 3 轮定点修复记录

- 修复范围：`impl_audit_mall.md` 的 `CA-ALL-R2-01`、`CA-ALL-R2-02`。
- 边界：只记录实现合同和隔离冒烟证据，不给出 code_audit 或结果验证判定。
- 禁止项确认：未修改 `assumptions.md`、`spec.md`、`state.json`、正式 results、`verify_report.md`、`audit_responses.md` 或 `impl_audit_mall.md`。
- 正式运行边界：未运行无参正式流水线。

## CA-ALL-R2-01：资格原始字段与消费端重算闭环

### 修改位置

- `src/r007_cross_market_return_forecasting/model_pipeline.py:ELIGIBILITY_AUDIT_SCHEMA`
- `src/r007_cross_market_return_forecasting/model_pipeline.py:derive_eligibility_decision`
- `src/r007_cross_market_return_forecasting/model_pipeline.py:validate_eligibility_audit`
- `src/r007_cross_market_return_forecasting/model_pipeline.py:_graph_target_eligibility`
- `src/r007_cross_market_return_forecasting/backtest_pipeline.py:iter_non_graph_autoregressive_predictions`
- `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:audit_formal_prediction_coverage`
- `src/r007_cross_market_return_forecasting/main.py:_run_sa3`

### 实现合同

- 唯一逐键资格表新增并持久化三个原始判定字段：
  - `predictor_complete`
  - `actual_return_available`
  - `historical_liquidity_available`
- 跨市场图与同市场图：
  - `predictor_complete` 来自当前快照实际预测特征行的有限性；
  - `actual_return_available` 由对应目标股票/预测日实现收益是否有限重算；
  - `historical_liquidity_available` 由对应目标股票/预测日前历史流动性是否有限重算。
- 非图 25 日自回归：
  - `predictor_complete` 由 25 个滞后特征逐行有限性重算；
  - 实现收益与历史流动性可得性分别计算，不再合并为一个不透明标志。
- 新增共享函数 `derive_eligibility_decision`，生产端与消费端使用同一固定优先级：
  1. `feature_count == 0`：`no_in_edges`；
  2. 否则 `complete_case_nobs < min_required_nobs`：`complete_case_insufficient`；
  3. 否则三个必要观测标志任一为假：`required_observation_missing`；
  4. 否则：`predictable`。
- 共享函数同时硬核验：
  - 特征数、完整样本数、最小样本数均非负；
  - `min_required_nobs` 必须等于 `feature_count + 1`，无特征时为 0；
  - 图规格非空 `graph_has_in_edges` 必须与 `feature_count > 0` 一致；
  - 三个必要观测标志不得为空。
- 新增共享函数 `validate_eligibility_audit`：
  - 从原始字段重新生成 `expected_eligibility_status` 和 `expected_exclusion_reason`；
  - 逐键与落盘的 `eligibility_status`、`exclusion_reason` 做严格等式核对；
  - 矛盾时抛出 `EligibilityDecisionError` 并保留失败逐键审计。
- M4 正式资格门禁调用该共享校验器；错误转换为携带失败审计的 `FormalCoverageError`。
- SA3 在生成动态 expected keys 前调用同一个共享校验器；不再只做合法字符串枚举检查。
- M4 唯一逐键证据表继续保留原始字段、重算字段和两项等式核对结果，能够独立重算每个排除原因。

### 隔离冒烟与负例

- 跨市场图正例：
  - 250 行 complete-case；
  - 有入边；
  - 三个原始可得性标志均为真；
  - 资格为 `predictable`，产生十模型输出。
- 同市场图正例：
  - AR 型合成序列形成真实同市场入边；
  - `graph_has_in_edges`、三个原始可得性标志均为真；
  - 资格为 `predictable`。
- 非图正例/缺失例：
  - 完整预测日三个标志均为真；
  - 将最后一个预测日实际收益置空后，仅 `actual_return_available=false`；
  - 重算原因为 `required_observation_missing`。
- 指定负例：
  - `graph_has_in_edges=true`、特征数 3、完整样本 250、最小样本 4、必要观测齐全，却伪标 `no_in_edges`：硬失败；
  - `actual_return_available=false` 却落盘为 `predictable`：硬失败。
- M4 合成三规格消费测试确认上述两类矛盾均触发 `FormalCoverageError`。
- SA3 与 M4 共享同一 `validate_eligibility_audit` 调用路径，固定优先级没有第二份可漂移实现。

## CA-ALL-R2-02：FIG3 构图前 250 条因果配对硬门禁

### 修改位置

- `src/r007_cross_market_return_forecasting/main.py:_validate_fig03_training_mapping`
- `src/r007_cross_market_return_forecasting/main.py:_build_fig03_graph_evidence`
- 复用 `src/r007_cross_market_return_forecasting/graph_pipeline.py:audit_snapshot_causality`
- 复用 `src/r007_cross_market_return_forecasting/graph_pipeline.py:select_training_mapping`

### 实现合同

- FIG3 专用入口在调用 `iter_rolling_graph_snapshots` 之前：
  1. 从 `US_TO_CN` 方向映射选择精确图日；
  2. 使用 `select_training_mapping` 取此前 250 行；
  3. 调用现有 `audit_snapshot_causality`；
  4. 再由 `_validate_fig03_training_mapping` 逐行补齐通用审计未覆盖的因果检查。
- 250 行逐条要求：
  - `causal_available == true`；
  - `source_date` 非空；
  - `target_open_utc` 非空；
  - `source_close_utc` 非空；
  - `target_date < 2021-10-21`；
  - `source_date < 2021-10-21`；
  - `source_close_utc < 对应 target_open_utc`；
  - `source_close_utc < 2021-10-21 图日目标开盘时间戳`。
- 通用 `audit_snapshot_causality` 的：
  - `training_causal_available_rows` 必须为 250；
  - `training_source_date_missing_rows` 必须为 0。
- 任一条件失败会在图迭代器调用前抛出异常，不构图、不选择邻近日期。
- 构图完成后，再把快照训练映射与预验证映射逐值比较，防止预检查对象和实际构图对象漂移。
- FIG3 机器可读口径清单改为实际重算：
  - `training_pair_count` 为逐行合法配对数；
  - causal 可用数/全真标志；
  - source_date 缺失数/完整标志；
  - 源/目标时间戳完整标志；
  - 目标日、源日严格早于图日标志；
  - 源收盘严格早于对应目标开盘及图日开盘标志；
  - 训练源/目标日期范围；
  - 训练源收盘/目标开盘 UTC 范围；
  - 精确图日目标开盘 UTC。
- 不再把训练因果布尔结论写成常量 `True`。

### 隔离冒烟与负例

- 正例：
  - 270 个合成交易日；
  - 精确选出 250 条合法历史配对；
  - causal 可用数为 250，source_date 缺失数为 0；
  - 源收盘严格早于逐行目标开盘及图日开盘；
  - FIG3 精确日代理矩阵成功生成。
- 指定负例：
  - 任意一行 `causal_available=false`：构图前硬失败；
  - 任意一行 `source_date=NaT`：构图前硬失败；
  - 任意一行 `source_close_utc >= target_open_utc`：构图前硬失败。
- 通过运行时哨兵替换构图迭代器确认：坏 causal flag 触发失败时，构图函数未被调用。

## 覆盖矩阵回填

- 修改位置：`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md`
- 必要补充要素：F4、F5、F8、F9、B5、B7、B11、SA3。
- 仅补充真实存在的 `文件:函数`；状态保持 `done`、最后更新保持 `implement`、验证结果列保持空白。

## 冒烟命令与结果

1. `uv run python -m compileall -q src/r007_cross_market_return_forecasting`
   - 结果：退出码 0。
2. `uv run python -m src.r007_cross_market_return_forecasting.main --smoke`
   - 结果：退出码 0；既有 CA-A01–CA-A08、SA4-DTYPE 与 CLI 动态检查完成。
3. 新增隔离 smoke：
   - 图、同市场图、非图三个资格生产路径完成；
   - 资格重算两类指定矛盾负例完成；
   - FIG3 合法250对正例、三类指定因果负例及构图前哨兵测试完成。

## 裁决边界

- 本轮两项范围内没有已知遗留实现项。
- 未运行正式全量回测，未修改正式结果，未形成任何 code_audit 或结果验证结论；裁判权留给 auditor、verifier 与 check_gates。
