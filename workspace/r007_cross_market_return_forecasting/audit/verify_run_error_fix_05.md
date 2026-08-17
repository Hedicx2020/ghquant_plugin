# r007 verify 运行错误修复 05

## 范围与边界

本次处理第 5 次正式 verify 在 M4 总表 checkpoint 写入阶段的结构性错误，属于
定向运行修复，不占 iteration。修改范围仅包括：

- `src/r007_cross_market_return_forecasting/main.py` 的 checkpoint 写后校验及
  fix05 兼容读取；
- `src/r007_cross_market_return_forecasting/checkpoint_compatibility_fix05.json`；
- 本说明文档。

未修改：

- 数据、模型、策略、参数、训练/预测区间、股票池；
- T+1 执行、滚动历史窗口、缩尾或组合计算语义；
- `common/`；
- `state.json`；
- spec、plan、assumptions、coverage matrix；
- 正式 checkpoint、M4 组件、results、run log、`verify_report.md` 或 evidence。

没有运行正式无参 `main.py`，没有运行 `check_gates.py`，没有 synthetic smoke，
也不宣布 verify 通过。

## attempt5 正式证据

正式运行目录：

`/private/tmp/r007_formal_verify_attempt5.H8sRV0`

`run_meta.txt`：

- command：
  `uv run python -m src.r007_cross_market_return_forecasting.main`；
- start：2026-07-30 15:57:59 +0800；
- end：2026-07-31 15:22:45 +0800；
- exit_code：1。

stderr 共 36 行、3,023 bytes。Traceback 调用链：

`run_formal_pipeline`
→ `_stage_m4`
→ `CheckpointStore.write_frame("m4_sharpe_metrics", frame)`

异常为：

`ValueError: 检查点写后 schema 校验失败: m4_sharpe_metrics`

内存 expected schema 中：

- `observation_count`：object；
- `pnl_mean`：object；
- `pnl_std`：object；
- `annualized_sharpe`：object；
- `sharpe_status`：object；
- `total_pnl`：object。

Parquet 重开 observed schema 中对应为：

- `observation_count`：int64；
- 四个收益/Sharpe 列：float64；
- `sharpe_status`：str。

资源日志原始尾记录：

- real：84,286.32 秒；
- user：83,273.96 秒；
- sys：793.00 秒；
- maximum resident set size：39,447,560,192。

门禁原始结果由主会话记录为：

- G-VF-1、G-VF-3、G-VF-4：FAIL；
- G-VF-2、G-VF-5、G-VF-6、G-VF-7：PASS；
- 本次人工恢复后的结构性失败序列：2。

## 已形成的正式 M4 资产

attempt5 已完成并保留：

- `cross_market_graph_aggregate`：1 个聚合 bundle；
- `same_market_graph_block`：299 个锚点 bundle；
- `same_market_graph_aggregate`：1 个聚合 bundle；
- `non_graph_block`：299 个锚点 bundle；
- `non_graph_aggregate`：1 个聚合 bundle。

M4 组件目录共 2,404 个文件、约 567 MiB。每个 bundle 含 predictions 与
eligibility 两张 parquet 及两份 sidecar。

另外：

- `m4_prepared_predictions.parquet` 已形成：
  - 26,288,370 行；
  - 221,250,032 bytes；
  - 修改时间 2026-07-31 15:22:33 +0800；
- `m4.json` 尚不存在；
- `m4_sharpe_metrics.parquet.part` 已由原写入异常清理；
- M1、M2_M3 marker 仍完整；
- 299 个跨市场正式图快照仍完整。

因此失败发生在三规格预测、资格交集、组合计算均已完成之后；不是模型训练、策略
计算或 M4 组件缺失。

## 根因

`common/ml_portfolio.py:_annualized_pnl_record()` 返回一个同时包含：

- Python int；
- Python float；
- 状态字符串；

的单个 pandas Series。`run_signed_liquidity_portfolios()` 对其执行：

`groupby.apply(_annualized_pnl_record).unstack()`

由于原 Series 混合数值与字符串，展开后的六个指标列均继承 object dtype。每列
内部实际是同构值：

- observation_count 全为整数；
- pnl_mean/pnl_std/annualized_sharpe/total_pnl 全为浮点数；
- sharpe_status 全为字符串。

Parquet 按单列真实值无损写入，并在重开时恢复为更具体的
int64/float64/string dtype。数据值没有变化；旧校验器仅比较 pandas dtype 文本，
把合法、可逆的存储类型推断误判为 schema 损坏。

这与 fix03 解决的异构 object 列不同：

- 异构、缺失、嵌套或特殊值仍需 typed JSON 保留精确 Python 类型；
- 本次是单列仅含一种普通标量类型，Parquet 原生 dtype 即可无损表达。

## 修复

### 无损 object dtype 重开协议

`main.py` 新增：

`_lossless_object_dtype_roundtrip_columns()`

`CheckpointStore.write_frame()` 在 expected/observed dtype 不同后，仅在以下条件
全部成立时接受重开 schema：

1. 行数、列数、列名及列顺序完全一致；
2. 原列 dtype 必须是 object；
3. 该列没有进入 typed JSON 编码；
4. 原列所有单元格只有一个 canonical 类型 tag；
5. tag 只能是 bool、int、float、str；
6. 重开 dtype 必须分别是对应的 bool、integer、float、string；
7. 写前与重开后每个单元格重新 typed-canonical 编码，序列必须逐值完全一致。

任一条件不满足，仍抛出原有 schema 校验错误。以下情况不会被宽松放行：

- 非 object 原生 dtype 变化；
- bool/int 或 int/float 混合；
- None、NaN 与有效值混合；
- Timestamp、datetime、list、dict、`pd.NA`、`NaT`；
- 列缺失、列重排、shape 变化；
- 任一数值或类型发生变化。

typed JSON 的异构列协议、写后逐值校验、`.part + os.replace` 原子替换均未改变。

### fix05 检查点兼容

新增：

`checkpoint_compatibility_fix05.json`

M1/M2_M3 兼容仍要求：

- config、输入 manifest、上游 marker hash 完全一致；
- 旧 marker code aggregate 完全匹配；
- 所有正式输出正文 SHA 与 schema 完整；
- 未列入 allowlist 的源码逐文件不变；
- allowlist 中 fix04 延续文件及当前 `main.py` SHA 精确匹配。

真实当前上下文验证：

- M1：`reusable_fix05_execution_compatible`；
- M2_M3：`reusable_fix05_execution_compatible`。

M4 组件兼容仅允许 attempt5 的旧 parent context：

`f27872a53ad84d99633e49336ffd0792e2f75e9a6cb1cd33aa48fb28bc9ded17`

映射到 fix05 当前 parent context：

`059051e861fc254f8ca7463670884919c88b52c6c7b4ef93e7906730ef2f780f`

兼容清单同时精确绑定：

- 当前完整 code aggregate；
- M4 config SHA；
- M4 input manifest SHA；
- M1、M2_M3 上游 marker SHA；
- 五种允许复用的 M4 component 名称。

任一代码、配置、输入、上游 marker 或组件名称变化，兼容路径立即失效。读取仍逐
文件验证 sidecar context、parquet 正文 SHA 与 schema。

真实 attempt5 块只读验证：

- component：`same_market_graph_block/CN_20160104`；
- predictions：24,500×8；
- eligibility：5,000×13；
- fix05 当前上下文成功通过旧 context 验证并读取。

下一次 verifier 可直接复用两类各 299 个锚点块和三个聚合，无需重跑约 23 小时的
M4 模型基线计算。

## 真实数据写读核验

从 attempt5 已落盘的真实
`m4_prepared_predictions.parquet` 只读筛选：

- specification：cross_market_graph；
- target_market：CN；
- direction：US_TO_CN；
- model：LGBM；
- 日期：2016-01-04 至 2017-03-31；
- 72,320 行、303 个交易日。

用正式配置运行现有组合函数，得到真实 Sharpe 表 6×13。写入前 dtype 与正式
Traceback 完全一致：

- observation_count/pnl_mean/pnl_std/annualized_sharpe/sharpe_status/
  total_pnl 均为 object。

仅在系统临时目录调用修复后的 `CheckpointStore.write_frame()`：

- 写入成功；
- 重开 dtype 为 int64/float64/str；
- `pd.testing.assert_frame_equal(..., check_dtype=False)` 逐值通过；
- 临时目录退出后自动清理；
- 未读取后写回任何正式 checkpoint。

该检查使用正式数据和正式参数的真实切片，不是 synthetic smoke。

## 方法与参数不变性

本次只改变 checkpoint 写后校验对“同构 object → 对应 Parquet 原生 dtype”的
识别，不改变 DataFrame 内存值或任何业务计算。以下均未变化：

- 原始数据和股票池；
- 图、特征、模型与超参数；
- 250 日训练窗、10 日更新块、25 阶自回归；
- T 日信号、T+1 执行；
- 缩尾、资格交集、组合与 Sharpe 公式；
- M4 输出行、列和值。

没有简化、近似或替代口径，因此无需追加 `assumptions.md`。

## 自检

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
- fix03 的 typed JSON 异构值、损坏值、未知类型、旧 parquet 和普通数值表回归
  全部保持通过；
- 真实 Sharpe 切片写读通过；
- M1/M2_M3 真实上下文兼容通过；
- attempt5 真实 M4 块兼容读取通过；
- 未运行完整 `main.py`；
- 未运行 gate；
- 未修改正式 checkpoint。

## 下一步正式命令

由 quant-verifier 在项目根目录运行：

```bash
uv run python -m src.r007_cross_market_return_forecasting.main
```

预期恢复路径：

1. 复用 M1、M2_M3；
2. 复用 attempt5 的 598 个 M4 锚点块及三个聚合；
3. 重新形成 M4 总表；
4. `m4_sharpe_metrics` 允许经逐值证明无损的 object→原生 dtype 重开；
5. 只有完整产物生成后，才由 verifier 和 `check_gates.py` 判定。

## 自检 checklist

- [x] 仅修改派发范围内的 `main.py`、fix05 兼容清单和本说明
- [x] 未修改 common/，未复制通用回测引擎
- [x] T+1、滚动历史、披露日相关口径均未改变
- [x] 无简化或近似，无需追加 assumptions.md
- [x] config.py、模型和策略参数未修改
- [x] compileall、26 项定向回归和真实数据临时写读通过
- [x] M1/M2_M3 与 attempt5 M4 组件可窄范围复用
- [x] 正式 checkpoint、results、run log、verify_report、state.json 均未改动
- [x] 未运行完整回测、synthetic smoke 或 gate
- [x] 未声称 verify 通过
