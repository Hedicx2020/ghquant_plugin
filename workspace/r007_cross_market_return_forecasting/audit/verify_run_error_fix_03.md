# r007 verify 运行错误修复 03

## 范围与边界

本次处理正式 verify attempt=3 的 M1 checkpoint 写入错误，属于运行修复，不占
iteration。所有权仅包括：

- `src/r007_cross_market_return_forecasting/main.py` 的 checkpoint 审计表写读边界；
- 专用回归测试；
- 本说明文档。

未修改：

- AS26 资格公式及 501/0 结果语义；
- `state.json`；
- spec、plan、assumptions、coverage matrix；
- 正式 results、`verify_report.md`、run log、evidence；
- 正式 checkpoint、缓存或 manifest。

没有运行正式无参 `main.py`，没有进入 M2，也不宣布 verify 通过。

## 独立复现与根因

正式错误发生在：

- `CheckpointStore.write_frame("m1_loaded_panel_audit", frame)`

真实 `m1_loaded_panel_audit` 为 75 行、7 列。读取当前生产函数的只读构造结果：

- `dataset/audit_type/item/status/detail` 使用 pandas string dtype；
- `actual` 为 object：
  - bool 28 个；
  - float 30 个；
  - str 10 个；
  - `pd.Timestamp` 4 个；
  - int 3 个；
- `expected` 为 object：
  - bool 28 个；
  - str 40 个；
  - None 4 个；
  - int 3 个。

旧写入边界直接调用 `frame.to_parquet()`，要求 PyArrow 在单个 object 列中推断一个
统一物理类型。`actual` 同时含 `True` 和 `0.0` 等跨类型值，PyArrow 因而抛出
`ArrowInvalid`。这是 checkpoint 序列化边界问题，不是 M1 审计业务值错误。

attempt=3 已写出的 8 个正式 frame 和缺失的 `meta/m1.json` 均未修改。本次源码
变更会改变代码 hash，后续是否重跑及如何清理旧 checkpoint 由 verifier 正式流程
负责。

## Typed canonical JSON 协议

### 触发范围

写入前只检查 pandas object 列：

- 异构类型列触发编码；
- 含 Timestamp、datetime、list、dict、`pd.NA` 或 `NaT` 的嵌套/特殊类型列触发
  编码；
- 普通数值列和同构、可直接写入的列不触发编码。

因此大型数值面板的物理 schema、dtype 和业务值保持原样。

### 单元格编码

每个触发列的单元格编码为 canonical JSON 类型节点，使用固定：

- `sort_keys=true`；
- UTF-8；
- 紧凑分隔符；
- 显式类型 tag。

协议区分：

- bool；
- int；
- float，使用 `float.hex()` 保留精确值及 `-0.0`；
- str；
- `pd.Timestamp`；
- Python datetime；
- None；
- NaN；
- `pd.NA`；
- `pd.NaT`；
- list；
- dict，键和值均递归 typed 编码，键值对按 canonical 键排序。

因此 bool `True` 不会与 int `1` 或 float `1.0` 淆混，None 也不会与 NaN 淆混。
不支持的 Python 类型直接抛 `TypeError`，不调用 `str()` 降级。

### Parquet schema metadata

编码协议直接写入 Parquet schema metadata：

- metadata key：`r007.checkpoint.typed_json_columns`；
- protocol：`r007.checkpoint.typed-json`；
- version：1；
- columns：编码列名及解码 dtype。

没有额外 sidecar，因此 parquet 与其类型协议保持单文件原子替换。

### 写后校验

`CheckpointStore.write_frame()` 现在：

1. 识别需要编码的列；
2. 写入 `.part` parquet；
3. 从 `.part` 自动解码重开；
4. 比较解码后的 DataFrame schema；
5. 对每个编码列重新 canonical 编码并逐值比较；
6. 全部一致后才 `os.replace()`。

任一步失败都会删除 `.part`，不会替换既有 checkpoint。

### 自动解码与兼容性

`CheckpointStore.read_frame()`：

- 检测到 version 1 metadata 时自动逐单元格解码并恢复 object 列；
- 没有 typed metadata 的历史 parquet 继续通过原始 `pd.read_parquet()` 路径读取；
- metadata 非 UTF-8、JSON 损坏、协议/版本未知、列重复、列不存在、物理列不是
  Arrow string、单元格 JSON 损坏、类型 tag 未知或非 canonical 时全部明确失败；
- 不静默字符串化或猜测损坏值。

checkpoint output manifest 仍绑定 parquet 正文 SHA 和物理 schema，既有阶段复用
门禁保持不变。

## 专用回归

新增：

- `tests/test_r007_checkpoint_typed_values.py`

7 项回归：

1. 真实 75×7 `m1_loaded_panel_audit` Parquet round-trip；
2. bool/int/float/str/Timestamp/None/NaN/`pd.NA`/list/dict 往返；
3. 未知 Python 类型在替换前失败，且不残留 `.part`；
4. 损坏 typed JSON 单元格读取失败；
5. 未知 metadata version 读取失败；
6. 无 typed metadata 的旧 parquet 保持可读；
7. 普通 int64/float64 数值表不编码，schema、dtype 和值不变。

真实 75×7 回归证据：

- 写入前后 shape 均为 75×7；
- 编码列仅为 `actual`、`expected`；
- `dataset/audit_type/item/status` 完全一致；
- `actual/expected` 逐单元格 canonical 类型和值一致；
- 原始 `True` 重开后仍为 Python bool；
- 原始 `0.0` 重开后仍为 Python float。

执行命令：

```bash
uv run python -m compileall -q \
  src/r007_cross_market_return_forecasting/main.py \
  tests/test_r007_checkpoint_typed_values.py

uv run python -m unittest discover \
  -s tests \
  -p 'test_r007_checkpoint_typed_values.py' \
  -v

uv run python -m unittest discover \
  -s tests \
  -p 'test_r007_*.py' \
  -v
```

结果：

- compileall 退出码 0；
- attempt=3 专用回归 7/7 `ok`；
- 当前全部 r007 定向回归 26/26 `ok`。

## M1 checkpoint 临时写读预检

使用生产函数只读构造完整 M1 十二张表，在系统临时目录创建独立
`CheckpointStore`，逐表执行 `write_frame()`、`read_frame()` 和 shape 对照。未使用
正式 checkpoint 路径，临时目录在退出上下文时自动清理。

结果：

| 表 | shape | typed 列 |
|---|---:|---|
| m1_us_panel | 969899×28 | 无 |
| m1_cn_panel | 716539×17 | 无 |
| m1_calendar_mapping | 3965×10 | 无 |
| m1_us_calendar | 2015×1 | 无 |
| m1_cn_calendar | 1950×1 | 无 |
| m1_us_market_returns | 2015×3 | 无 |
| m1_universe_audit | 1001×16 | 4 个跨市场拼接后的混合布尔列 |
| m1_source_schema_audit | 68×7 | 无 |
| m1_loaded_panel_audit | 75×7 | actual、expected |
| m1_return_panel_audit | 117×7 | actual、expected |
| m1_security_coverage_audit | 1505×95 | 跨审计 section 拼接后的混合布尔列 |
| m1_return_distribution_audit | 8×12 | 无 |

十二张表均保持原 shape 重开。大型 US/CN 数值面板未出现 typed metadata，证明修复
未改变大表 schema。真实 75×7 的类型探针为：

- `True`：`bool`；
- `0.0`：`float`。

## 未解决项

- 本次未执行正式 verify，因此没有生成新的正式 M1 marker 或验证结论。
- attempt=3 的 ArrowInvalid 仍是正式历史运行事实，未修改正式日志。
- 后续正式 attempt=4 应由 verifier 按新代码从失效 checkpoint 状态重新运行。

## 自检 checklist

- [x] 仅修改允许的 checkpoint 写读边界、专用测试与说明文档
- [x] 未改 AS26、spec、plan、assumptions、coverage matrix 或 state.json
- [x] 未改正式 results、verify_report、缓存、manifest 或正式 checkpoint
- [x] 没有使用简单 `astype(str)`，typed 编码稳定、可逆且无歧义
- [x] bool/int/float/str/Timestamp/None/NaN/list/dict 均有回归
- [x] 未知类型、损坏编码和未知 metadata 版本均 fail-fast
- [x] 旧无协议 parquet 保持可读，普通数值表 schema/dtype 不变
- [x] compileall、7 项专用回归、26 项 r007 回归全部通过
- [x] 完整 M1 十二表仅在自动清理的临时目录完成写读预检
- [x] 未运行正式无参 main.py，未进入 M2，未宣布 verify 通过
