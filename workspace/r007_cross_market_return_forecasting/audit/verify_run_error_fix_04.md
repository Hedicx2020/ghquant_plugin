# r007 verify 运行错误修复 04

## 范围与边界

本次处理用户人工恢复后的第 4 次正式 verify 在 M4 后处理阶段无 Traceback
退出的问题，属于结构性运行修复，不占 iteration。修改范围仅包括：

- `src/r007_cross_market_return_forecasting/graph_pipeline.py`；
- `src/r007_cross_market_return_forecasting/model_pipeline.py`；
- `src/r007_cross_market_return_forecasting/backtest_pipeline.py`；
- `src/r007_cross_market_return_forecasting/main.py`；
- `src/r007_cross_market_return_forecasting/checkpoint_compatibility_fix04.json`；
- 本说明文档。

未修改：

- 研报方法、模型、参数、训练/预测区间、股票池、交易时序或资格判定；
- `common/`；
- `state.json`；
- spec、plan、assumptions、coverage matrix；
- 正式 results、`verify_report.md`、run log、evidence；
- 既有正式 checkpoint、299 个图快照、缓存或数据 manifest。

没有运行正式无参 `main.py`，没有写入 M4 正式组件检查点，也不宣布 verify
通过。正式运行与判定仍归 quant-verifier 和 `check_gates.py`。

## 正式运行证据

第 4 次正式运行的只读证据如下：

- `workspace/r007_cross_market_return_forecasting/checkpoints/meta/m2_m3.json`
  为 `complete`：
  - `snapshot_count=299`；
  - `prediction_rows=10,695,970`；
- 正式快照共 299 个；
- M3 已完整落盘：

| frame | shape | 文件大小 |
|---|---:|---:|
| `m3_predictions` | 10,695,970×8 | 96,479,447 bytes |
| `m3_training_audit` | 149,652×16 | 9,329,618 bytes |
| `m3_model_audit` | 1,197,216×23 | 1,431,028 bytes |
| `m3_feature_values` | 18,628,519×11 | 310,213,932 bytes |
| `m3_eligibility_audit` | 1,487,511×13 | 1,150,769 bytes |

- `m4.json` 不存在，M4 正式组件文件数为 0；
- attempt=4 的 stderr/resource 日志：
  - 247,366 行；
  - 27,128,559 bytes；
  - 最后修改时间为 2026-07-30 14:54:43 +0800；
  - stdout 为 0 bytes；
  - `LGBMRegressor` feature-name UserWarning 共 120,119 条；
  - pandas DataFrame fragmentation PerformanceWarning 共 3,564 条；
  - 无 Traceback、Killed、Command terminated、Maximum resident 或 Exit status
    尾记录。

因此可以确认 M1、M2/M3 已完成，而进程消失发生在 M4 长时后处理期间；日志
没有提供可归因于 Python 异常的终止栈。

## 根因定位

正式调用链为：

`main.py:_stage_m4`
→ `main.py:_collect_same_market_predictions`
→ `backtest_pipeline.py:iter_same_market_graph_predictions`
→ `model_pipeline.py:predict_graph_snapshot`
→ `graph_pipeline.py:materialize_target_feature_batch`

存在四个相互叠加的结构性问题：

1. `materialize_target_feature_batch()` 在每个目标股票循环内，都重新规范化并
   pivot 完整源市场和目标市场面板。同市场基线每个快照约 500 个目标，因此同一
   快照的相同全市场矩阵被重复构造约 500 次。
2. `_collect_same_market_predictions()` 将生成器整体 `list(...)`，在 M4 仅需要
   predictions 与 eligibility 时，仍同时常驻 training audit、model audit 和
   feature values。M3 现有 feature-values 表已达 18,628,519 行，证明该类中间表
   的内存量级不可忽略。
3. M4 只有整阶段 marker，没有按规格/锚点原子检查点。长时同市场或非图基线在
   任一时点退出后，已完成计算全部丢失，恢复时只能从 M4 起点重算。
4. 修复源码会改变全局 code hash；若严格按旧逻辑处理，完整的 M1/M2_M3 marker
   会失效，且旧 M2/M3 分支会删除 299 个正式图快照后重建。

另外，120,119 条已知 LightGBM/sklearn feature-name warning 和 3,564 条
fragmentation warning 将 stderr 放大到 26 MiB，既增加日志 I/O，也遮蔽有效进度；
它们不是业务错误，但会加剧长时运行的可观测性问题。

## 修复内容

### 1. 全市场矩阵只构造一次

`graph_pipeline.py` 新增：

- `TargetFeatureMatrices`；
- `prepare_target_feature_matrices()`。

`materialize_target_feature_batch()` 新增只读 `prepared_matrices` 参数。未提供时
仍走原有构造语义；提供时只按目标及其入边选列，不再逐目标重复规范化和 pivot。

`model_pipeline.py:predict_graph_snapshot()` 在单快照入口统一准备矩阵，并透传给
每个目标。`iter_snapshot_model_predictions()` 再按
`(source_market, target_market)` 缓存矩阵。

真实正式面板切片等价性检查：

- 使用既有第一个 `US_TO_CN` 正式快照及真实 M1 面板；
- 旧手工 pivot 与新预备矩阵完全一致；
- 同一目标 `600754` 的隐式构造与显式复用结果完全一致；
- 特征数 5，训练表 250×8，预测表 10×8。

真实完整面板、5 个目标的只读微基准：

- 旧逐目标重复准备：1.309 秒；
- 新矩阵准备一次：0.247 秒；
- 5 个目标复用：0.047 秒；
- 按 500 个目标外推，仅重复 pivot 准备工作约减少 530.5 倍。

该数字只描述矩阵准备环节，不代表完整 M4 总运行时间预测。

### 2. M4 不再保留无用中间表

`model_pipeline.py:predict_graph_snapshot()` 新增
`collect_feature_values` 开关，默认 `True`，保持 M2/M3 正式输出不变。

`backtest_pipeline.py:iter_same_market_graph_predictions()` 在 M4 基线专用路径传入
`collect_feature_values=False`。M4 原合同只消费 predictions 与 eligibility，
因此不再构造和保留被丢弃的 feature values；训练/模型审计仍由单块结果内部完成
必要的事务判定，但不在聚合器跨锚点常驻。

`main.py:_collect_same_market_predictions()` 与
`_collect_non_graph_predictions()` 改为流式消费单块结果，不再整体
`list(...)`。

### 3. M4 规格级与锚点级原子恢复

`main.py` 新增：

- `_m4_component_context()`；
- `_m4_component_paths()`；
- `_read_m4_component()`；
- `_write_m4_component()`；
- `_m4_expected_anchor_dates()`；
- `_m4_result_anchor()`；
- `_m4_block_key()`。

下一次正式运行会在
`workspace/r007_cross_market_return_forecasting/checkpoints/components/m4/`
下写入：

- 跨市场规格聚合；
- 同市场图逐市场、逐锚点块及聚合；
- 非图自回归逐市场、逐锚点块及聚合。

每个 predictions/eligibility parquet 均通过现有
`.part → 写后 schema 校验 → os.replace → sidecar` 协议落盘。sidecar 绑定当前
M4 parent context，校验正文 SHA 与 schema。只有两张表均存在且各自验证通过时，
该块才算完成；半写、损坏或上下文不一致的块会被拒绝并单块重算。

两个迭代器均新增 `skip_anchor_dates`，在模型拟合前跳过已完成锚点。恢复时先验证
所有既有块，再仅计算缺失锚点。

使用既有 M3 正式 predictions/eligibility 的真实 20 行切片，在系统临时目录完成
组件原子写读检查：

- 正常写入后两表逐值一致；
- 手工破坏 prediction parquet 后，组件整体被拒绝；
- 未触碰正式 checkpoint 目录。

### 4. 降低 M3 常驻内存

`_stage_m2_m3(load_reporting_frames=False)` 在正式 M1/M2_M3 复用路径只加载 M4
立即需要的：

- `m3_predictions`；
- `m2_indegree_quantiles`；
- `m3_eligibility_audit`。

training audit、model audit、18.6M 行 feature values 和 graph audit 延后到 M5
完成后的正式报告构造阶段再从已验证 marker 绑定的 parquet 载入。

M4 跨市场规格原子落盘后，会释放内存中的 M3 predictions 与 eligibility；
M4 后续使用组件表。正式报告前重新从完整 M2_M3 checkpoint 载入，因此报告表值
和输出合同不变。

### 5. 保护既有 M1/M2_M3 正式检查点

新增 `checkpoint_compatibility_fix04.json` 及
`CheckpointStore.validate_stage_fix04_compatible()`。兼容放行仅限：

- stage 为 `m1` 或 `m2_m3`；
- 旧 marker code aggregate 必须精确等于 attempt=4 的既有值；
- config、输入 manifest、上游 checkpoint hash 必须与当前真实上下文完全一致；
- marker 中每个输出文件必须继续通过正文 SHA 与 schema 校验；
- 未在 allowlist 的源码必须逐文件与旧 marker 完全一致；
- allowlist 中 4 个本次修改源码必须精确匹配清单登记的当前 SHA。

任一后续源码编辑都会使该窄兼容路径失效。使用当前配置与真实原始输入 manifest
重建上下文后的只读验证结果：

- `m1=True, reusable_fix04_execution_compatible`；
- `m2_m3=True, reusable_fix04_execution_compatible`。

`_stage_m2_m3()` 仅以文件存在性检查快照，不再为真值判断反序列化全部 299 个
快照。若 marker 不可复用而快照仍存在，会 fail-fast，拒绝静默删除。

### 6. 控制已知 warning 与碎片化构造

正式入口仅精确过滤 sklearn 发出的已知
`LGBMRegressor` feature-name UserWarning；没有按类别全局吞掉其他 warning。

`materialize_target_feature_batch()` 的训练/预测列构造改为单次 `pd.concat`，
消除逐列插入触发的 DataFrame fragmentation warning。列名、顺序、值和
complete-case 语义保持不变。

## 方法与参数不变性

本次没有改变：

- 图构建、边筛选、入度和方向；
- 源/目标收益字段；
- 250 日训练窗、10 日更新块和 25 阶自回归特征；
- 缩尾分位数或训练窗拟合边界；
- 八个基础模型及两种集成；
- 模型超参数、随机种子；
- 预测日期、交易执行时序；
- 动态资格、组合构造、收益与 Sharpe 公式。

新增缓存仅复用同一输入面板的确定性 pivot；新增组件仅保存原本已在内存中生成的
predictions 与 eligibility。没有简化、近似或替代口径，因此无需向
`assumptions.md` 新增假设。

## 自检与回归

执行：

```bash
uv run python -m compileall -q \
  src/r007_cross_market_return_forecasting

uv run python -m unittest discover \
  -s tests \
  -p 'test_r007_*.py' \
  -v
```

结果：

- compileall 退出码 0；
- 当前全部 r007 定向回归 26/26 `ok`；
- 当前 4 个 allowlist 源码 SHA 与
  `checkpoint_compatibility_fix04.json` 完全一致；
- 真实正式上下文下 M1、M2_M3 兼容验证均通过；
- 未运行正式无参 `main.py`；
- 未修改正式 checkpoint。

## 下一步正式命令

由 quant-verifier 在项目根目录运行：

```bash
uv run python -m src.r007_cross_market_return_forecasting.main
```

预期执行路径：

1. 复用既有 M1 与 M2_M3 完整 checkpoint；
2. 不删除、不重建 299 个正式图快照；
3. 从 M4 开始，先原子落盘跨市场聚合；
4. 同市场图和非图基线逐锚点落盘，可在中断后续跑；
5. 只有完整 M4/M5 及结果合同产出后，才由 verifier 和 gate 判定。

## 自检 checklist

- [x] 仅修改派发范围内文件
- [x] 未修改 common/，src/ 未新增重复回测引擎
- [x] 未来函数三查：披露日口径未涉及 / T+1 执行未变 / 滚动窗口只用历史未变
- [x] 没有简化或近似处理，无需追加 assumptions.md
- [x] config.py 与全部策略参数未修改
- [x] 冒烟运行通过（compileall、26 项定向回归），未执行完整回测
- [x] coverage matrix 的既有实现映射未改变，无需回填
- [x] 正式 checkpoint、results、run log、verify_report、state.json 均未改动
- [x] M1/M2_M3 真实上下文兼容验证通过，299 个快照受 fail-fast 保护
- [x] 未声称 verify 通过
