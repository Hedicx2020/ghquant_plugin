# r007 verify 运行错误修复 02

## 范围与裁决

本次属于 verify attempt=2 的运行修复，不占 iteration。实现唯一口径来源为：

- `workspace/r007_cross_market_return_forecasting/audit/verify_run_error_fix_02_planning.md`

只处理 M1 的 AS19/AS24–AS26 美股数据资格与隔离审计，不修改 M2–M5。

未修改：

- `state.json`；
- spec、plan、assumptions；
- 正式 results、`verify_report.md`、run log、evidence；
- 下载缓存、合并面板或 manifest。

未运行正式无参 `main.py`，未写入 M1 检查点，本文不宣布 verify 通过。

## 原运行阻塞

attempt=2 的旧实现将 `ohlc_logic_violation_count == 0` 作为整只证券合格条件，
同时只要求 `return_eligible_rows > 0`。这同时造成：

1. HUBB、UA 各一个已独立识别且完整隔离的异常行被错误提升为整证券失败；
2. 对一只证券的大面积收益不可用缺少比例约束。

规划裁决要求以同一个 95% 含边界门槛同时约束：

- 有效区间五个原始 OHLCV 字段的最低非空率；
- 仅由原始字段独立重算的 `return_eligible` 行率。

少量已识别、已隔离的异常行只计审计；缓存标志、复权衍生值或收益隔离与独立
重算不一致时，仍属于批次硬失败。

## 生产代码变更

修改文件：

- `src/r007_cross_market_return_forecasting/data_pipeline.py`

### 独立行级重算

新增 `_independent_us_row_contract()`，不采信缓存布尔标志或派生复权列，独立计算：

1. `effective_row_expected`；
2. `ohlc_logic_valid_expected`；
3. `adj_factor_expected=adj_close/close_raw`，仅保留有限正数；
4. 四个 `*_adj_expected`；
5. `return_eligible_expected`。

完整 OHLC 行按以下原始值规则重算：

- `open_raw > 0`；
- `close_raw > 0`；
- `high_raw >= max(open_raw, close_raw)`；
- `low_raw <= min(open_raw, close_raw)`；
- `high_raw >= low_raw`。

已识别逻辑异常行的四个预期复权 OHLC 均为 NaN，且独立
`return_eligible_expected=false`。

### 单证券资格与硬合同

新增 `_audit_us_security_qualification()`：

- 有效区间为空：失败；
- 原始 OHLCV 最低非空率小于 95%：失败；
- 独立 `return_eligible` 行率小于 95%：失败；
- 两项恰好 95% 均通过；
- OHLC 异常数量仅作为审计统计，不单独使证券失败；
- 存储/独立 OHLC 标志不一致：硬失败；
- 存储/独立 eligible 标志不一致：硬失败；
- `adj_factor` 或四个复权 OHLC 与独立预期不一致：硬失败；
- 异常行任一复权 OHLC 非空或存储 eligible 为真：硬失败；
- 无效行产生 OPCL，或 pvCLCL 使用无效/缺失的直接前收：硬失败。

逐证券审计字段包括：

- `effective_rows`；
- `open_raw/high_raw/low_raw/close_raw/volume_non_null_ratio`；
- `non_null_ratio`、`minimum_ohlcv_non_null_rate`；
- `ohlc_logic_violation_count_independent`；
- `return_eligible_rows_independent`；
- `return_eligible_rate_independent`；
- 两类标志 mismatch、复权因子及四个复权 OHLC mismatch；
- `invalid_row_used_in_opcl_count`；
- `invalid_or_missing_previous_close_used_in_pvclcl_count`；
- `qualified`、`qualification_status`、`qualification_reason`、
  `failure_reasons`。

### 异常行与批次摘要

`audit_us_merged_panel_contract()` 返回的既定 M1 审计表增加
`audit_record_type`：

- `security`：501 条逐证券资格记录；
- `exception_row`：原始异常行明细；
- `batch_summary`：固定候选池、集合、500/1 门槛、硬合同及收益隔离汇总。

异常行记录保留证券、日期、原始 OHLCV、`adj_close`、独立复权因子、存储/独立
OHLC 标志、存储/独立四个复权 OHLC、存储/独立 eligible 和隔离状态。

批次摘要记录：

- `requested_count`、`manifest_success_count`、`observed_count`；
- `qualified_count`、`failed_count`；
- `minimum_successful_securities=500`；
- `maximum_failed_securities=1`；
- 集合一致性、独立标志一致性、隔离完整性、最终门禁；
- 两个收益层隔离误用计数。

请求不是固定 501、集合不等、重复键、schema、SHA、manifest 行数、逐证券正文与
merged 精确切片任一不一致，仍直接停止。

### 正式收益代理池

`standardize_us_quotes()` 使用同一独立资格函数：

- 硬合同不一致直接停止；
- 仅通过双 95% 资格的证券进入正式收益代理池；
- 失败证券仍可保留在原始合同审计中，不会进入 B1 收益面板；
- 收益面板集合审计只允许美国固定池少至多 1 个已被资格公式排除的证券，
  仍要求至少 500 只且禁止任何池外证券；
- 当前真实数据 501 只全部合格，因此没有删除任何真实候选。

## 十二类定向回归

新增：

- `tests/test_r007_us_qualification_contract.py`

覆盖规划要求的十二类正负例：

1. 一个已识别、已隔离异常行且双比例不低于 95%：证券合格。
2. 伪造 `ohlc_logic_valid=true` 或 `return_eligible=true`：批次硬失败。
3. 异常行任一复权 OHLC 非空：硬失败。
4. 全部标志为真时，独立识别 `low>open`、`high<close`、非正开盘及
   `high<low`。
5. 独立 eligible 率恰好 95% 通过，94% 失败。
6. 原始 OHLCV 最低非空率恰好 95% 通过，94% 失败。
7. 500 合格、1 失败通过；499 合格、2 失败停止。
8. 请求少于/多于 501 或集合不一致：停止。
9. SHA、schema、重复键、manifest 行数或缓存—merged 内容不一致：停止。
10. 异常日 OPCL、pvCLCL 为空，异常后首个有效日不跳接更早收盘。
11. 无效/非有限复权因子使对应行不可用；eligible 率 94% 时失败。
12. 真实 HUBB、UA 行数、异常数、eligible 行数、日期及资格与规划事实一致。

同时保留 attempt=1 的 7 项严格 schema 回归。

执行命令：

```bash
uv run python -m compileall -q \
  src/r007_cross_market_return_forecasting/data_pipeline.py \
  tests/test_r007_us_schema_contract.py \
  tests/test_r007_us_qualification_contract.py

uv run python -m unittest discover \
  -s tests \
  -p 'test_r007_us_*contract.py' \
  -v
```

结果：

- compileall 退出码 0；
- attempt=2 十二类回归全部 `ok`；
- 连同 schema 回归共 19 项全部 `ok`，退出码 0。

## 真实 501 只读合同审计

使用正式 manifest、501 个逐证券 parquet 和 merged panel 执行只读调用，
未改写缓存或正式结果。

记录类型：

- `security=501`；
- `exception_row=2`；
- `batch_summary=1`。

批次结果：

- requested=501；
- manifest success=501；
- observed=501；
- qualified=501；
- failed=0；
- `batch_gate_pass=true`；
- `invalid_row_used_in_opcl_count=0`；
- `invalid_or_missing_previous_close_used_in_pvclcl_count=0`。

真实异常：

- HUBB：2015 行，独立异常 1 行，独立 eligible 2014 行，
  eligible 率 99.9504%，合格；
- UA：1456 行，独立异常 1 行，独立 eligible 1455 行，
  eligible 率 99.9313%，合格；
- 两个异常日期均为 2021-05-05；
- 两行均为 `identified_isolated_security_qualified`。

## 完整 M1 内存只读预检

按正式 M1 顺序在内存中执行：

1. 构造固定美股池与 A 股市值池；
2. 加载双市场原料、日历与市场指数；
3. 构造双市场收益面板；
4. 执行 501 美股合同审计；
5. 构造双向日历映射与市场收益；
6. 执行 source schema、loaded panel、return panel、security coverage、
   return distribution 审计。

只读结果：

- universe：US 501、CN 500；
- return panel：US 501 只/969899 行，CN 500 只/716539 行；
- calendar mapping：3965 行；
- US market returns：2015 行；
- source schema audit：68 行；
- loaded panel audit：75 行；
- return panel audit：117 行；
- security coverage audit：1505 行；
- return distribution audit：8 行；
- `failed_m1_checks=0`。

本预检没有调用正式入口、没有创建或更新检查点、没有落盘正式 M1 表，也没有
进入 M2。

## 未解决项与裁决边界

- 本次定向实现与只读预检未发现新的 M1 运行阻塞。
- attempt=2 的旧 `qualified=499, failed=2` 仍是旧实现下的历史验证事实，未修改
  `verify_report.md` 或正式 run log。
- 只有 verifier 重新执行正式流水线后才能形成新的验证事实。
- 本文不宣布 M1、verify 或完整复现通过。
