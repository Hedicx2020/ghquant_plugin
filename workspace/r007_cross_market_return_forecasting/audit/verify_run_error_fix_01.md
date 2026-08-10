# r007 verify 运行错误修复 01

## 范围与边界

- 现场错误：正式运行 attempt=1 在 M1 的 `audit_us_merged_panel_contract` 停止，异常为 `ValueError: MMM 逐证券缓存与合并面板 schema 不一致`。
- 证据来源：
  - `output/r007_cross_market_return_forecasting/results/run_log.md` 的完整 traceback；
  - `output/r007_cross_market_return_forecasting/verify_report.md` 的失败现场记录；
  - 当前正式 manifest、MMM 单证券 parquet、merged panel parquet 和当前源码。
- 未修改：
  - `state.json`；
  - spec、plan、assumptions；
  - 正式 results、`verify_report.md`、evidence；
  - 下载缓存、merged panel 或 manifest。
- 未运行正式无参 `main`，本记录不宣布 verify 通过。

## 独立复现与根因

原实现位置：

- `src/r007_cross_market_return_forecasting/data_pipeline.py:audit_us_merged_panel_contract`

原实现把以下两个值直接转成完整字符串后做等式比较：

- `pq.ParquetFile(MMM.parquet).schema_arrow`
- `pq.ParquetFile(us_panel.parquet).schema_arrow`

现场独立读取结果：

- MMM 正文 SHA256 与 manifest 相等；
- merged panel 正文 SHA256 与 manifest 相等；
- 列名及顺序完全相同；
- 每个 Arrow field 的类型、nullability 和 field metadata 完全相同；
- 两个 schema 的 schema 级 metadata 都只有 `b"pandas"`；
- MMM 的 pandas metadata 长度为 2412 字节，merged 为 2413 字节；
- 实际差异位于 pandas 容器描述中 `date` 列的 `numpy_type`：
  - MMM：`datetime64[s]`
  - merged：`datetime64[ms]`
- 两者真实 Arrow field 类型相同，因此上述 pandas metadata 差异不改变 parquet 字段合同或读取后的数据语义。

根因是原比较把 DataFrame/Parquet writer 产生的 schema 级 pandas 容器 metadata 一并纳入完整字符串等式，导致字段合同完全相同的 MMM 被误判为 schema 不一致。

## 变更

### 生产代码

修改：

- `src/r007_cross_market_return_forecasting/data_pipeline.py`

新增函数：

- `_semantic_arrow_schema_metadata`
- `_semantic_arrow_schema_sha256`
- `_semantic_arrow_schema_differences`
- `_assert_semantic_arrow_schema_equal`

新合同：

1. 严格比较字段数量。
2. 严格比较列名与顺序。
3. 严格比较每个字段的 Arrow 类型。
4. 严格比较每个字段的 nullability。
5. 严格比较每个字段的全部 field metadata。
6. schema 级 metadata 只忽略 `b"pandas"` 容器描述；其他 schema metadata 仍严格比较。
7. 不关闭 schema 审计，也不把所有 metadata 一概忽略。

`audit_us_merged_panel_contract` 现在：

- 继续逐文件重算正文 SHA256；
- 继续核对 manifest 文件名、逐证券行数、证券集合、merged 行数和正文 SHA256；
- 使用上述严格语义 schema 合同比较逐证券缓存与 merged panel；
- 继续读取逐证券正文并与 merged 精确切片比较；
- 继续执行 OHLCV 非空率、OHLC 逻辑、收益可计算行数和正式覆盖门禁；
- 审计行新增：
  - `individual_semantic_schema_sha256`
  - `merged_semantic_schema_sha256`
  - `semantic_schema_identical`
  - `manifest_rows`
  - `row_count_matches_manifest`

### 定向回归

新增：

- `tests/test_r007_us_schema_contract.py`

包含七项回归：

1. 仅 schema 级 pandas metadata 不同：通过。
2. 缺少列：失败。
3. 列顺序变化：失败。
4. Arrow 类型变化：失败。
5. nullability 变化：失败。
6. field metadata 变化：失败。
7. 真实 MMM：
   - 正文 SHA256 与 manifest 相等；
   - 逐证券正文行数与 manifest 相等；
   - 与 merged panel 通过严格语义 schema 比较；
   - 逐证券正文与 merged MMM 切片内容一致。

## 测试证据

### 编译

命令：

```bash
uv run python -m compileall -q \
  src/r007_cross_market_return_forecasting/data_pipeline.py
```

结果：退出码 0。

### 定向回归

命令：

```bash
uv run python -m unittest discover \
  -s tests \
  -p 'test_r007_us_schema_contract.py' \
  -v
```

结果：7 项全部 `ok`，退出码 0。

### 真实文件只读审计

真实 MMM 结果：

- `semantic_schema_identical=true`
- `content_identical_to_individual_cache=true`
- `qualified=true`
- OHLCV 最低非空率：1.0
- OHLC 逻辑违规数：0
- 可计算收益行数：2015

未改写任何正式缓存、manifest 或 results。

## 未解决项

使用正式默认门禁对完整实际面板做只读调用时，schema 检查已经越过 MMM，但随后既有 OHLC 逻辑覆盖门禁停止：

- `qualified=499`
- `failed=2`
- `observed=501`

用仅内存的诊断配置取得失败明细：

- HUBB：OHLC 逻辑违规 1 行；
- UA：OHLC 逻辑违规 1 行。

两者 OHLCV 最低非空率均为 1.0，分别有 2014 和 1455 行可计算收益。本次没有修改或放宽该门禁，也没有改动缓存数据。该后续阻塞不属于 attempt=1 的 MMM schema 误报修复范围，需由主流程后续独立处理。

## 裁决边界

- 本次只确认 MMM schema 误报的代码路径已按定向合同修复并完成隔离回归。
- 未运行正式无参入口，未确认 M1 或完整流水线能够完成。
- 不宣布 verify 或任何结果门禁通过。
