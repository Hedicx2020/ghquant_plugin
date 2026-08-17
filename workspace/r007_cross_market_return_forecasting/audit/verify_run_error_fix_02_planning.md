# r007 verify attempt=2 M1/AS26 口径裁决

## 一、裁决范围与既有事实

本裁决只处理 `m1` 中 D1、D3、B1 的 AS19/AS24–AS26 数据资格口径，不改变 attempt=2 的正式验证事实、`verify_report.md`、`run_log.md`、`evidence_manifest.md` 或 coverage 既有结论，也不涉及 M2–M5。

既有门槛保持原值：

- 固定候选池必须为 501 只，不增补、不换股。
- 单证券必须在研究区间有数据。
- 有效区间原始 OHLCV 各字段非空率的最小值必须不低于 95%。
- 最终合格证券至少 500 只，正式失败证券至多 1 只；否则 M1 停止。
- manifest `status=success` 仅表示下载、缓存和文件完整性成功，不单独等价于 AS26 的证券合格。

attempt=2 的只读事实为：manifest success=501，合并面板证券数=501；HUBB 为 2015 行，UA 为 1456 行，两者原始 OHLCV 最低非空率均为 1.0，均只有 1 行 `low_raw > open_raw`；异常行原始值保留，四个复权 OHLC 均为 NaN，`ohlc_logic_valid=false`，`return_eligible=false`。HUBB/UA 的独立 `return_eligible` 行数分别为 2014/1455，对应比例分别为 2014/2015=99.9504% 和 1455/1456=99.9313%。缓存标志与按原始字段独立重算一致。

## 二、裁决结论

单个已经被原始字段独立识别并按 AS19 正确隔离的异常行，不使整只证券直接失败。证券资格应按逐行数据可用率判断：原始 OHLCV 最低非空率与独立重算的 `return_eligible` 率都必须不低于 95%。

因此，HUBB 和 UA 在当前只读数据下均应保留为合格证券；这两行异常必须保留在原始层供审计，但不得进入复权价格或任何收益计算。按本裁决公式重算，当前面板为 501 只合格、0 只失败，满足“至少 500、至多 1 失败”，但这只是修复后的预期门禁结果，不替代 coder 实现和 verifier 重新正式运行。

当前 `audit_us_merged_panel_contract()` 以 `ohlc_violations == 0` 判证券合格，同时只要求 `return_eligible_rows > 0`。前者把一个已隔离行级异常错误上升为整证券失败，后者又不足以约束一只证券的大面积不可用；两者都应由下述同一套 95% 行级资格公式替代。

## 三、单证券资格公式

对证券 \(s\)，在研究区间内定义：

1. 有效区间行集 \(E_s\)：原始 `open_raw/high_raw/low_raw/close_raw/volume` 至少一个字段非空的行。若 \(E_s\) 为空，证券失败。
2. 原始字段覆盖率：
   \[
   C_{s,k}=\frac{\#\{t\in E_s:x_{s,t,k}\text{ 非空}\}}{|E_s|},
   \quad
   C_s=\min_{k\in OHLCV} C_{s,k}
   \]
3. 原始 OHLC 逻辑按原始数值独立重算，不读取缓存标志：完整 OHLC 行须满足 `open_raw>0`、`close_raw>0`、`high_raw>=max(open_raw,close_raw)`、`low_raw<=min(open_raw,close_raw)`、`high_raw>=low_raw`。
4. `adj_factor_expected=adj_close/close_raw`，仅当其有限且大于 0 时有效。四个 `*_adj_expected` 由对应原始价乘该因子得到；已识别的完整 OHLC 逻辑异常行，四个预期复权 OHLC 必须全部为 NaN。
5. `return_eligible_expected` 必须完全由原始字段、独立 OHLC 逻辑和有效复权因子重算，不以存储的 `ohlc_logic_valid`、`return_eligible` 或已派生复权列作为真值。其语义与 AS19 一致：该行独立 OHLC 逻辑允许，且预期复权开盘价、收盘价均为有限正数。
6. 行级收益可用率：
   \[
   R_s=\frac{\sum_{t\in E_s}1(\text{return\_eligible\_expected}_{s,t})}{|E_s|}
   \]
7. 在文件/集合/字段完整性硬检查全部通过的前提下：
   \[
   qualified_s=
   (|E_s|>0)\land(C_s\ge 0.95)\land(R_s\ge 0.95)
   \]

95% 为含边界门槛：恰好 95% 通过，低于 95% 失败。`ohlc_logic_violation_count` 是必须输出的审计统计，不再单独作为 `qualified_s=false` 的充分条件。该处理不是放宽 AS26：它保留原始 OHLCV 的 95% 门槛，并将原先过松的“至少一行 return eligible”收紧为 `return_eligible` 率至少 95%。

## 四、不得由标志掩盖的批次硬失败条件

以下情况不受 95% 容忍度保护，应直接使 M1 硬失败，而不是靠缓存标志判通过：

1. 请求集合、manifest success 集合、逐证券缓存集合、合并面板集合不一致；候选不是固定 501 只；出现运行时补股或现场替换。
2. 请求参数、唯一键、日期范围、逐证券行数、文件 SHA256、语义 schema、逐证券内容与合并面板切片任一不一致。
3. 独立重算的 `ohlc_logic_valid_expected` 与存储标志不一致。
4. 独立重算的 `return_eligible_expected` 与存储标志不一致。
5. 原始 OHLC 逻辑异常行仍有任一复权 OHLC 非空，或其 `return_eligible=true`；这是异常未隔离，不得因证券总体可用率高而放行。
6. 任一复权 OHLC 与“原始价×独立有效复权因子”的预期值不一致，或应为 NaN 的位置被填入数值。
7. 下游收益使用了 `return_eligible_expected=false` 的当日开盘/收盘；pvCLCL 也不得跨过无有效前收的行而跳接更早收盘价。
8. 按资格公式合格少于 500 只，或失败多于 1 只。失败证券可以保留在审计明细，但不得进入 B1 正式代理池；不得用新增证券补足。

其中第 3–7 项必须由原始字段独立重算后比对，不能把 manifest 或面板中已有布尔标志作为自证。

## 五、必须落盘的审计输出

coder 应使 M1 在抛门禁异常前生成或向既定 M1 审计产物提供以下可由 verifier 独立重算的字段；不得只在异常字符串中给合计数。

逐证券明细至少包含：

- `stock_code`、manifest 状态、逐证券文件及 SHA256、行数、首末日期；
- `effective_rows`；
- 五个原始 OHLCV 字段各自非空率及 `minimum_ohlcv_non_null_rate`；
- `ohlc_logic_violation_count_independent`；
- `return_eligible_rows_independent`、`return_eligible_rate_independent`；
- 存储/独立 `ohlc_logic_valid` 不一致数、存储/独立 `return_eligible` 不一致数；
- 四个复权 OHLC 与独立预期值不一致数、异常行未隔离数；
- `qualified` 与机器可读 `failure_reasons`。

异常行明细至少包含证券、日期、原始 OHLCV、`adj_close`、独立复权因子、独立 OHLC 判定、存储 OHLC 判定、四个复权 OHLC、存储/独立 `return_eligible` 及隔离是否通过。HUBB、UA 的 2021-05-05 两行必须出现在该表中，并明确为“已识别、已隔离、证券仍满足 95%”。

批次摘要至少包含 `requested=501`、`manifest_success`、`observed`、`qualified`、`failed`，以及 `minimum_successful_securities=500`、`maximum_failed_securities=1`、集合一致性、独立标志一致性、隔离完整性和最终门禁布尔值。异常行不应从原始面板物理删除。

收益层另需输出 `invalid_row_used_in_opcl_count`、`invalid_or_missing_previous_close_used_in_pvclcl_count`，两者必须为 0，证明隔离标志没有只停留在缓存层。

## 六、coder 必须覆盖的负例与边界测试

1. 单证券仅 1 行 `low_raw>open_raw`，该行复权 OHLC 全 NaN、两类标志与独立重算一致，且 \(C_s,R_s\ge95\%\)：证券应合格。
2. 与负例 1 数据相同，但伪造 `ohlc_logic_valid=true` 或 `return_eligible=true`：即使总体比例高也必须批次硬失败。
3. 与负例 1 数据相同，但任一异常行复权 OHLC 非空：必须批次硬失败。
4. 把全部布尔标志写成 true，同时原始数据含 `low>open`、`high<close`、非正开收盘或 `high<low`：独立重算必须识别并拒绝标志掩盖。
5. `return_eligible` 独立可用率恰好 95%：证券合格；低于 95%（例如 100 行中仅 94 行可用）：证券失败。
6. 原始 OHLCV 最低非空率恰好 95%：证券合格；任一字段低于 95%：证券失败。
7. 501 只中 500 合格、1 失败：批次通过；499 合格、2 失败：批次停止。不得改变 500/1 阈值。
8. 请求集合少于或多于 501、静默新增替代证券、manifest/面板集合不等：直接硬失败。
9. SHA256、schema、唯一键、逐证券行数或缓存—合并面板内容任一不一致：直接硬失败。
10. 异常当日 OPCL 必须为空；异常当日 pvCLCL 必须为空；异常后的首个有效交易日不得跳过异常行连接到更早收盘价计算 pvCLCL。
11. 无效或非有限 `adj_factor` 必须独立识别，使对应行不可用于收益；若独立可用率低于 95%，证券失败。
12. HUBB/UA 真实切片回归：分别得到 2015/1456 行、1/1 个独立 OHLC 异常、2014/1455 个独立 eligible 行，且两只均合格。

## 七、假设登记判断与既有验证边界

无需修改 `assumptions.md`。AS19 已给出异常行保留、派生复权 OHLC 隔离和收益不可用的处理；AS26 已给出有效区间 OHLCV 95%、至少 500 证券、最多 1 失败及不扩源的门槛。本裁决只是把两条既有假设合成为可执行、可独立重算的证券资格公式，没有改变事实、市场迁移范围或任何数量阈值。

attempt=2 的 `qualified=499, failed=2, exit=1` 仍是旧实现下的真实验证结论，不得回写或改称通过。只有 coder 按本裁决修正实现、补齐负例后，由 verifier 重新正式运行，才能产生新的 M1 与全流程验证结论。

planning decision: ready
