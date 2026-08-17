# result_fix_round1 独立复审

- 日期：2026-07-18
- 审计对象：RA-A01、RA-A02、CDX-R-01 的当前共享树实现
- 输入：当前代码、`audit/result_fix_round1.md`、既有正式结果只读数据
- 隔离声明：未修改代码、策略参数、正式 results 或 `state.json`；所有回归输出均写入自动清理的临时目录。
- 结论边界：以下仅给三个定向修复项的复审 verdict，不判断全局门禁。

## RA-A01：预测散点按月连接

### 静态核查

- `_build_prediction_scatter_data` 将概率侧与标签侧分别转换为 `predictor_period`、`prediction_period`，按两个 Period 月份键加 `factor` 连接（`src/r003_equity_factor_timing_cn/reporting.py:505-543`）。
- 标签侧在连接前检查月份/因子键不重复，merge 使用 `validate="one_to_one"`（`reporting.py:540-543`）。
- 连接后断言行数为预测月数×六因子，`factor_return/is_winner` 不得为空，并逐月断言六个唯一因子、唯一赢家（`reporting.py:544-562`）。
- 绘图前虽执行有限值清洗，但如果清洗导致任一点丢失会立即抛错，不会静默 drop（`reporting.py:729-736`）。

### 独立回归

- 只读现有 `probability_details.xlsx/OOS概率` 与 `胜出标签` 调用当前实现，得到33个月、198行。
- `factor_return` 非空198/198，`is_winner` 非空198/198；每月均为6个唯一因子和1个实际赢家。
- 将修复后的198点与其余五张既有图表底表交给当前 `create_charts`，六张图均在临时目录成功生成；散点绘图未触发丢点断言。
- 负测删除首个OOS月的一条标签，当前实现按预期抛出“预测散点实际收益/赢家缺失”，未静默生成不完整图。

verdict RA-A01: pass

## RA-A02：逐股票执行/退出证据链

### 端到端传递与无泄漏

- `strategy.build_equity_factor_base` 将逐股票收益审计合并回 `factor_constituents`（`strategy.py:934-958`）；`M1Dataset` 显式包含该字段，`build_m1_dataset` 原样传递（`data_pipeline.py:18-27,566-573`）。
- m2、m3、m4 完成后，`main.run_pipeline` 才把 `dataset.factor_constituents` 传给 `write_result_package`（`main.py:158-205`）。该表不进入模型训练、因子概率或组合构造，未形成结果泄漏。
- reporting 先复制成分表构造审计，再把摘要加入metrics并把明细写入 `returns_detail.xlsx/execution_exit_audit`（`reporting.py:834-947,1039-1100,1339-1405`）。独立实测构造前后输入成分表规范哈希不变。
- 组合收益在进入 reporting 前已经形成；审计摘要只增加结果证据字段，不参与 `_portfolio_metric_table` 或组合收益计算。未发现更改既有组合结果的路径。

### 字段、约束、Excel安全与计数

- 输出共26列，完整包含信号/预测月、因子/股票/原权重、计划/实际执行、执行限制总原因与ST/无量/停牌/涨跌停分项、计划/实际退出、两类延迟、退出状态、限制原因、标签可得日、NAV标记和搜索窗末日。
- 结果层断言覆盖OOS月份完整、信号月/因子/股票唯一、信号早于计划执行、入场/未入场实际执行日一致、已退出有真实日期且不早于计划日、延迟不超过20、超限必须等于20、标签可得日不早于计划退出日（`reporting.py:858-904`）。
- Excel上限按“1,048,575数据行+1表头”设置；超过上限会在写文件前失败（`reporting.py:918-922`）。
- 独立使用真实中国全市场2025-09单信号月运行m1并构造2025-10审计：4,726条数据、Excel含表头4,727行；实际入场4,634、执行受限92、正常退出4,573、延迟退出58、20日窗超限3、NAV标记3。临时 `returns_detail.xlsx` 确有 `execution_exit_audit` sheet，回读后上述计数逐项等于summary。

### 哈希复算缺陷

- 当前summary在写Excel前对内存DataFrame计算SHA-256，得到 `deab3d897b2d8923f4f6a18408f22cd2d0529a9bccef3b31ea748d81d0d3b781`。
- 从临时 `returns_detail.xlsx/execution_exit_audit` 回读同一4,726行，显式保留六位股票代码、规范日期与布尔类型，再调用同一 `_canonical_frame_sha256`，得到 `2fe72cd7d111427462452a3e5b8a3be6dd84c06fec0168fae8b329c290d47b75`，与summary不一致。
- 差异集中在1,061行 `weight` 的Excel浮点往返末位，例如内存规范串为 `0.0037593984962406013`，Excel回读规范串为 `0.0037593984962406009`。行数、字段和业务计数均一致，但交付者仅凭Excel sheet无法复算metrics中记录的表内容哈希。
- 两行简单权重的合成样本可偶然哈希一致，不能消除真实全市场等权分数触发的稳定复现缺陷。
- 建议修复方向：在哈希规范中对浮点采用Excel往返稳定精度，或在工作簿写入后从实际sheet回读并计算最终交付哈希；修复后需用真实等权分数组复测。

verdict RA-A02: fail

## CDX-R-01：AS41与中证800免成本

- AS41现明确限定首期建仓及后续袖套成本只适用于六因子1/N、商业周期倾斜、ML概率三个可投资因子组合；中证800为无成本理论指数基准，净主动收益以有成本策略对无成本基准比较（`workspace/r003_equity_factor_timing_cn/assumptions.md:527-538`）。
- `portfolio._add_turnover_and_costs` 对中证800强制 `buy_cost/sell_cost/transaction_cost=0`，令 `net_return=gross_return`，并记录 `index_benchmark_no_stock_cost`；其余组合记录 `factor_sleeve_stock_cost`（`portfolio.py:441-484`）。
- reporting 的口径说明与 `metrics.json.transaction_cost_scope` 生成文字均使用同一免成本基准描述（`reporting.py:990-1001,1319-1325`）。
- 只读既有33个月结果复算：中证800累计成本0，净/毛收益最大误差0，33行成本口径均为 `index_benchmark_no_stock_cost`；三个因子组合均为 `factor_sleeve_stock_cost`。
- 该修订只改假设和结果解释文字，未改 `portfolio.py` 计算或既有组合数值。

verdict CDX-R-01: pass

## 回归与编译

- `_build_prediction_scatter_data` 正向、负向及临时绘图回归：通过。
- 真实中国全市场单月 m1 → 审计构造 → 临时Excel回读：字段、约束、行数和计数通过；交付哈希复算失败。
- `python -m py_compile src/r003_equity_factor_timing_cn/*.py`：通过。
- PyArrow受限环境的CPU cache告警不影响退出码或断言。

## 定向复审汇总

| 修复项 | verdict | 说明 |
| --- | --- | --- |
| RA-A01 | pass | 月份键一对一、198点完整、逐月唯一赢家、绘图不静默丢点 |
| RA-A02 | fail | 证据链、字段、计数、容量保护与无泄漏通过，但Excel交付表SHA-256不可复算 |
| CDX-R-01 | pass | AS41、portfolio实现及结果口径均为中证800免成本 |

全局门禁：未判定，由主会话处理。
