# r007 code audit 第 3 轮修复后最终正式 verify 前预检

- 本报告覆盖并作废第 2 轮预检，只认当前 round3 源码与本次亲自运行结果。
- 执行日期：2026-07-27（Asia/Shanghai）。
- 当前 r007 源码：13 个 Python 文件、14,660 行。
- 当前源码聚合 SHA256：`5192e500448649c813af87acf9c59b5de8a29ebebf0e3611d331f6e74fbc8c18`。
- 临时根：`/tmp/r007_preverify_round3.HRkKHg/`；各负例另使用动态创建的 `/tmp/r007_*_round3_*`。
- 执行边界：未运行完整 formal；未修改 `src/`、`state.json`、`coverage_matrix.md`、正式 `output/.../results/` 或正式 `verify_report.md`。
- 判定范围：只判断当前代码是否具备进入正式 verify 的集成条件，不给出正式复现结论。

## 总表

| 检查项 | 判定 | 本次亲自执行证据 |
|---|---|---|
| compile/import | PASS | 13 个当前 Python 文件编译成功；11 个业务模块逐个导入成功 |
| 隔离 `--smoke` | PASS | 临时副本运行 exit=0；27 个登记产物的大小与 SHA256 全部复核一致 |
| 无参 formal 分派与范围 | PASS | 无参只分派 formal；正式阶段链完整；样本范围、500 股与十模型未缩减 |
| checkpoint 六类失效 | PASS | 代码/配置/输入/上游/输出/schema 分别命中预期失效原因 |
| 资格事实正例 | PASS | 七个原始资格字段重算为 `predictable`，落盘状态与原因一致 |
| 三类资格伪标 | PASS | 假 `no_in_edges`、actual 不可得却 predictable、liquidity 不可得却 predictable 均硬失败 |
| 三规格 M4 消费端 | PASS | 任一规格的落盘状态与事实矛盾时抛 `FormalCoverageError` |
| SA3 消费端 | PASS | 资格矛盾时抛 `EligibilityDecisionError`，下游组合调用数为 0 |
| FIG3 正常 250 行 | PASS | 250 行因果可得、UTC 完整、两类严格时序均通过后才调用构图一次 |
| FIG3 五类负例 | PASS | 缺 UTC、causal=false、source_date 空、两类时序倒置均在构图调用数为 0 时失败 |
| R2 666/42 正例 | PASS | 111×6=666 行全部 complete，42 格与参考表全部 `both` |
| R2 七类负例回归 | PASS | 缺行/重复/非有限/坏状态/错误模型归属/参考表不足/合并非 both 均硬失败 |
| 正式 results 无污染 | PASS | 预检前后正式结果文件数均为 0 |

## 1. compile、import 与隔离 smoke

### 1.1 命令

```bash
PYTHONPYCACHEPREFIX=/tmp/r007_preverify_round3.HRkKHg/pycache \
uv run python -m compileall -q \
  src/r007_cross_market_return_forecasting

# 对每个当前业务模块逐个执行：
PYTHONPYCACHEPREFIX=/tmp/r007_preverify_round3.HRkKHg/pycache \
uv run python -c \
  'import src.r007_cross_market_return_forecasting.<module>'

cd /tmp/r007_preverify_round3.HRkKHg
PYTHONPATH=/tmp/r007_preverify_round3.HRkKHg \
PYTHONPYCACHEPREFIX=/tmp/r007_preverify_round3.HRkKHg/pycache \
uv run --project /Users/hedi/report_reproduce \
  python -m src.r007_cross_market_return_forecasting.main --smoke
```

隔离 smoke 使用当前 `src/r007_cross_market_return_forecasting/`、`common/`、`pyproject.toml` 与 `uv.lock` 的临时副本。临时副本的 `__file__` 根目录位于 `/tmp`，不会把 smoke 产物写回仓库。

### 1.2 结果

- `compile_exit=0`。
- 逐个导入成功的 11 个业务模块：
  `backtest_pipeline`、`config`、`data_pipeline`、`download_us_data`、
  `graph_pipeline`、`main`、`model_pipeline`、`portfolio_pipeline`、
  `reporting`、`sensitivity_pipeline`、`strategy`。
- `import_all_exit=0`。
- `smoke_exit=0`。
- smoke 输出的 `CA-A01`、`SA4-DTYPE`、`CA-A02` 至 `CA-A08`、`CLI` 均为 `passed`。
- `artifact_manifest.json` 登记 27 个文件；本次独立重算后，存在性、字节数、SHA256 全部相等。顶层实际 28 个文件，差额为 manifest 自身。
- stderr 仅有 matplotlib 字体权重回退 warning：`findfont: Failed to find font weight bold, now using 400.`；未导致进程或产物失败。
- 隔离 smoke 根：
  `/tmp/r007_preverify_round3.HRkKHg/workspace/r007_cross_market_return_forecasting/smoke/`。

### 1.3 关键源码指纹

| 文件 | SHA256 |
|---|---|
| `main.py` | `6c2503a93307ddfbbec59c85ae660ba3c45ea488327ff59fd13e21ca5845ba22` |
| `config.py` | `fd183c8917a35c089bac27c08feeeb1e646c156fe2aa692f863c109144aa448c` |
| `graph_pipeline.py` | `00f051cc1e740b4bb56e9e5616685a12b18c83d4f1ad278943fac60cd0b3ceae` |
| `model_pipeline.py` | `7971fd22fdd2ded11853d86c0306aab26018fcd3f0da0d379e24544b6012875d` |
| `portfolio_pipeline.py` | `a0eaa24e3b7bfb71527d88161a038f2d81cb16c82eabb4eefca110526b6e2dbd` |
| `sensitivity_pipeline.py` | `22c39d4558338b8f892a5a2a6971bf3a64a8a15bcbb51723baf847ee1d5f3511` |

判定：PASS。

## 2. 无参 formal 分派与正式范围

本次没有执行完整 formal。测试以无写入替身替换 `run_formal_pipeline` 与 `run_smoke`，只执行无参 `main()` 的真实参数解析与分派，并用 AST 核对正式函数的阶段调用顺序。

- 无参 `main()`：`return_code=0`。
- 调用记录严格为 `["formal"]`，未调用 smoke。
- 正式阶段顺序：
  `_stage_m1 → _stage_m2_m3 → _stage_m4 → _stage_m5 → _build_chart_tables → write_formal_outputs`。
- 样本范围：`2014-01-01` 至 `2021-12-31`。
- 正式预测范围：`2016-01-01` 至 `2021-12-31`。
- 每市场股票数：`500`。
- 正式模型数：八个基础模型加两个集成模型，共 `10`。

干净分组测试文件：
`/tmp/r007_preverify_round3.HRkKHg/core_checkpoint.json`，对应命令 exit=0。

判定：PASS。

## 3. checkpoint 六类失效

每个场景都在独立临时 `CheckpointStore` 上先创建可复用基准，再只改变指定维度并调用真实 `validate_stage()`。

- `code_manifest()` 实读 21 个文件。
- code manifest 聚合 SHA256：
  `95e55ff642689bb14c86f352961eec08f611c888251574f9df3c3e1d4b03589f`。

| 改动维度 | 预期 reason | 实际 reason | 判定 |
|---|---|---|---|
| 代码哈希 | `context_hash_mismatch` | `context_hash_mismatch` | PASS |
| 配置 | `context_hash_mismatch` | `context_hash_mismatch` | PASS |
| 输入 manifest | `context_hash_mismatch` | `context_hash_mismatch` | PASS |
| 上游 marker | `context_hash_mismatch` | `context_hash_mismatch` | PASS |
| 输出正文 | `output_hash_mismatch` | `output_hash_mismatch` | PASS |
| 输出 schema | `output_schema_mismatch` | `output_schema_mismatch` | PASS |

schema 用例在改变 Parquet schema 后，将 marker 中正文 SHA 更新为新文件 SHA、保留旧 schema SHA，定点命中 `output_schema_mismatch`，没有被正文哈希分支提前截断。

判定：PASS。

## 4. round3 资格事实重算与消费端门禁

### 4.1 正常事实正例

测试输入的原始字段：

- `graph_has_in_edges=true`
- `feature_count=1`
- `complete_case_nobs=2`
- `min_required_nobs=2`
- `predictor_complete=true`
- `actual_return_available=true`
- `historical_liquidity_available=true`

直接调用 `derive_eligibility_decision()`，实际重算为：

- `expected_eligibility_status=predictable`
- `expected_exclusion_reason=""`

再调用 `validate_eligibility_audit()`，落盘状态与原因两个 match 标志均为 true。

### 4.2 三类伪标负例

| 负例构造 | 原始事实与伪标 | 实际异常 | 判定 |
|---|---|---|---|
| 假 `no_in_edges` | `feature_count=1`、`graph_has_in_edges=true`，却落盘 `legally_excluded/no_in_edges` | `EligibilityDecisionError`：状态/原因与原始字段重算结果矛盾 | PASS |
| actual 不可得却 predictable | `actual_return_available=false`，其余充分，落盘 `predictable` | `EligibilityDecisionError`：状态/原因与原始字段重算结果矛盾 | PASS |
| liquidity 不可得却 predictable | `historical_liquidity_available=false`，其余充分，落盘 `predictable` | `EligibilityDecisionError`：状态/原因与原始字段重算结果矛盾 | PASS |

### 4.3 M4 三规格消费端

构造三个完整规格：

- `cross_market_graph`
- `same_market_graph`
- `same_market_non_graph`

每个规格均有一个机会键和完整十模型输出。只把 `same_market_graph` 的资格结论伪标为 `legally_excluded/no_in_edges`，但保留 `feature_count=1`、`graph_has_in_edges=true` 等可预测事实。

真实调用 `audit_formal_prediction_coverage()`：

- 实际异常：`FormalCoverageError`
- 消息：`M4 动态资格消费门禁 的落盘状态/原因与原始字段重算结果矛盾`

异常发生在三规格交集和组合计算之前，没有把伪标排除当作合法收缩。

### 4.4 SA3 消费端

用一个临时配置检查点让 `_run_sa3()` 直接抵达真实资格消费门禁；资格行设置 `actual_return_available=false`，却落盘 `predictable`。

- 实际异常：`EligibilityDecisionError`
- 消息：`SA3 动态资格消费门禁 的落盘状态/原因与原始字段重算结果矛盾`
- 下游 `run_sensitivity_portfolios()` 调用数：`0`

干净分组测试文件：
`/tmp/r007_preverify_round3.HRkKHg/eligibility_round3.json`，对应命令 exit=0。

判定：PASS。

## 5. round3 FIG3 构图前逐行因果门禁

### 5.1 正常 250 行正例

构造 `2021-10-21` 精确图日及此前 250 个目标交易日，每条历史配对均包含：

- `target_date`
- `source_date`
- `causal_available=true`
- 非空 `target_open_utc`
- 非空 `source_close_utc`
- `source_close_utc < target_open_utc`
- `source_close_utc < 2021-10-21` 图日目标开盘 UTC

真实调用 `_build_fig03_graph_evidence()` 的观测：

- `training_pair_count=250`
- `training_causal_available_count=250`
- `training_source_date_missing_count=0`
- `training_causal_available_all=true`
- `training_source_date_complete=true`
- `training_source_timestamp_complete=true`
- `training_target_timestamp_complete=true`
- 历史目标日和源日均严格早于图日期
- `source_close_strictly_before_target_open_all=true`
- `source_close_strictly_before_graph_open_all=true`
- 因果预检通过后，`iter_rolling_graph_snapshots()` 调用数恰为 `1`

### 5.2 五类构图前负例

每个负例都给 `iter_rolling_graph_snapshots()` 安装禁止调用替身；最终五例的图构建调用数均为 `0`。

| 负例 | 实际异常 | 关键观测 | 构图调用数 | 判定 |
|---|---|---|---:|---|
| 缺 UTC 列 | `KeyError` | 缺少 `source_close_utc` | 0 | PASS |
| `causal_available=false` | `AssertionError` | `legal_pair_count=249` | 0 | PASS |
| `source_date` 为空 | `AssertionError` | `legal_pair_count=249` | 0 | PASS |
| `source_close_utc >= target_open_utc` | `AssertionError` | 相等行被判非法，`legal_pair_count=249` | 0 | PASS |
| `source_close_utc >=` 图日目标开盘 UTC | `AssertionError` | 即使仍早于该行目标开盘，也因不早于图日开盘被判非法 | 0 | PASS |

干净分组测试文件：
`/tmp/r007_preverify_round3.HRkKHg/fig03_round3.json`，对应命令 exit=0。

判定：PASS。

## 6. round2 R2 合同回归

### 6.1 111×6 正例

直接调用 `build_hyperparameter_grid()` 得到真实配置 ID 和模型归属，为每个配置展开六个组合并输入有限 Sharpe：

- 超参数配置：111。
- 组合数：6。
- 输入行：666。
- `summarize_hyperparameter_sharpe()` 行级审计：`666/666 complete`。
- 汇总格：七模型×六组合=`42`。
- `build_r2_comparison()`：`42/42 reference_merge_status=both`。

### 6.2 七类负例

| 负例 | 实际异常 | 判定 |
|---|---|---|
| 缺 1 行 | `R2ConfigurationCoverageError` | PASS |
| 重复 1 行 | `R2ConfigurationCoverageError` | PASS |
| Sharpe 非有限 | `R2ConfigurationCoverageError` | PASS |
| `sharpe_status` 非 `ok` | `R2ConfigurationCoverageError` | PASS |
| 配置归属错误模型 | `R2ConfigurationCoverageError` | PASS |
| 精确参考表不足 42 格 | `AssertionError` | PASS |
| 汇总缺格导致参考合并非 `both` | `ValueError` | PASS |

干净分组测试文件：
`/tmp/r007_preverify_round3.HRkKHg/r2_round3.json`，对应命令 exit=0。

判定：PASS。

## 7. 正式结果与受保护文件无污染

- 预检开始时正式 `output/r007_cross_market_return_forecasting/results/` 文件数：0。
- 预检结束时正式结果文件数：0。
- 空文件集 SHA256：
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- 未执行完整 `run_formal_pipeline()`；无参分派测试中的 formal 函数为无写入替身。
- 隔离 smoke、checkpoint、资格、FIG3 与 R2 产物均位于 `/tmp`。
- 结束时 r007 源码聚合 SHA256：
  `5192e500448649c813af87acf9c59b5de8a29ebebf0e3611d331f6e74fbc8c18`，与开始冻结值一致。
- `workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md` 开始与结束 SHA256 均为：
  `ab0ca57fd3259360cd977f4516f18b3d8e37afb3eece6c98db50734eaa0c270c`。
- `output/r007_cross_market_return_forecasting/verify_report.md` 开始与结束 SHA256 均为：
  `b3c633e47b73b52b168205092ff7d35e812bd176a98156107ca3d957dce6499d`。

本轮唯一覆盖写入：
`workspace/r007_cross_market_return_forecasting/audit/code_audit_preverify.md`。

preverify verdict: PASS
