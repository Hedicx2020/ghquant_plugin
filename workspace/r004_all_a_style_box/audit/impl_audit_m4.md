# r004_all_a_style_box 实现复审（m4，shared common 与输出链定向复核）

## 范围与冻结点

- mode：`code`；milestone：`m4`；逐条覆盖 `R4 / R7 / R10 / SA4` 及其 PNG、Parquet、XLSX 输出链。
- 审读分离：未读取 coder 完成汇报；仅独立读取当前源码、spec/plan/assumptions/coverage 和实际临时产物。
- 有界执行：未运行正式全区间；用连续33个月（2023-04至2025-12）确定性夹具真实生成8 PNG、10 Parquet、5 XLSX，并实施大明细、warning、限额和 chart 缺口注入。
- 当前冻结 SHA-256：
  - `common/utils.py=534ae84994248655501012d9dac50391a5b5fab10739acf7066f072b4c4e6c6d`
  - `src/r004_all_a_style_box/reporting.py=878b33c3f3b2871841c11410876e45f6fdcba0c1389894ed32d0fc6a50b12ef3`
  - `src/r004_all_a_style_box/main.py=7bf8db15ea83ea9f62fb2e207f8f529862201485e905d818c3c02e78f3741221`
  - `src/r004_all_a_style_box/workbook_builder.mjs=331c549cd8b467d22f63f7a30384930e557d18a882ed4b7632b39312273567c2`
  - `src/r004_all_a_style_box/__init__.py=8ecc995d653490f84af5c33918b20af8c33744401830f61db78bab3af924f455`

## R4 / R7 / R10 / SA4 逐项复核

| 要素 | 状态 | 独立动态证据 | 真实实现位置 | 结论 |
| --- | --- | --- | --- | --- |
| R4 | found | 33个月BV/BG/SV/SG及SMB/HML/GML的7×7 Pearson矩阵，49单元独立重算最大绝对误差0 | `reporting.py:360-381,973-1047`；coverage `:76` | 中国正式OOS相关矩阵实算，美国原值未注入 |
| R7 | found | 逐月胜者标签、胜者数、并列等分credit及四箱频率与独立重算全一致；频率最大误差0，空标签0；单胜/双并列/四并列反例通过 | `reporting.py:384-474,973-1047`；coverage `:79` | 逐月追溯与汇总频率闭环 |
| R10 | found | 18行绩效；CAGR、年化波动、期初1.0最大回撤及零现金收益Sharpe独立重算最大绝对误差 `4.85722573273506e-17` | `reporting.py:226-357,973-1047,1263-1291`；coverage `:82` | shared common 复用正确；负首期回撤不会漏计 |
| SA4 | found | 相对ALL_A与STYLE_1N的16行年化超额、跟踪误差、信息比率独立重算最大绝对误差0 | `reporting.py:891-926,973-1047`；coverage `:86` | 双基准稳健比较实算且口径一致 |

## shared common 数值迁移与最大回撤

- R10 年化收益、年化波动、最大回撤、胜率直接复用 `common.utils`；Pearson IC/RankIC复用 `common.backtest`，见 `reporting.py:22-28,226-262,646-741`。
- 33个月独立基线共6项，common迁移最大绝对误差 `4.5102810375396984e-17`，低于 `1e-12`。
- 最大回撤定义已在常量、参数合同和实现docstring透明声明：显式包含调仓前期初净值1.0，见 `reporting.py:50-60,81,117-118,230-235`。
- 负首期 `[-10%,+2%,+3%]`、首峰后下跌、空序列三类独立基线全部通过，MDD最大误差0；负首期正确值 `-0.1`，旧漏计值0，修正差0.1，见 `reporting.py:646-741`。
- 33个月R10全实体再按上述标准口径独立重算，最大误差 `4.85722573273506e-17`，未见其他绩效漂移。

## RankIC、8 PNG 与比较状态

- Size与Style按各自有效样本计算；33个月截面Size样本12、Style样本9，1/2/3月Pearson IC、RankIC及样本数独立重算最大误差0；五分组严格Q1-Q5。
- `ic_distribution.png` 以 `density=True` 生成概率密度直方图；非恒定RankIC夹具实际进入两条正态拟合曲线：`Size μ=0.966, σ=0.026`、`Style μ=-0.945, σ=0.045`，见 `reporting.py:1100-1142`。
- 8/8 PNG均由实际代码生成、Pillow回读成功、DPI=`299.9994`（300 DPI元数据）：`ic_series`、`ic_distribution`、`group_cumulative_returns`、`group_returns_bar`、`net_value_comparison`、`style_box_heatmap`、`factor_cumulative_returns`、`turnover_cost`。
- comparison保持 `experimental / pending_verifier / not_comparable`；所有美国 `report_value` 与 `pass` 为空，不冒充数值可比或验证结论。

## 十表全量Parquet、Top视图与DetailManifest

- `write_detail_tables()` 固定收集10表、全量稳定排序、zstd Parquet落盘并记录行数、列名、列数、字节数、SHA-256、显示行数、视图上限、规则与路径，见 `reporting.py:1421-1446,1507-1618`。
- 临时真实回读10/10成功；每个文件的实际SHA-256、行数、列顺序均与manifest完全一致：

| 表 | 全量行×列 | XLSX显示行 | 上限/规则摘要 |
| --- | ---: | ---: | --- |
| holdings | 300×10 | 200 | 每月每组合Top100 abs(actual_weight) |
| target_weights | 300×7 | 200 | 每月每组合Top100 abs(target_weight) |
| actual_weights | 300×8 | 200 | 每月每组合Top100 abs(actual_weight) |
| box_membership | 318×4 | 213 | 每信号日每箱Top100 |
| trades | 500×8 | 400 | 每月每组合Top200 abs(gross_notional) |
| unfilled_orders | 500×9 | 400 | 每月每组合Top200 abs(unfilled_notional) |
| turnover | 198×7 | 198 | 全量稳定视图 |
| costs | 198×10 | 198 | 全量稳定视图 |
| coverage | 198×10 | 198 | 全量稳定视图 |
| ic_observations | 2016×10 | 2016 | 每期限/月/因子Top100；本夹具各组未超限 |

- 对每表将输入行随机打乱后重建视图，10/10与原视图逐值、逐序一致；Top100/200均未越限，稳定破同分规则包含stock_code/side/reason/全行哈希，见 `reporting.py:1449-1556`。
- 五个工作簿均带 `DetailManifest`；Top视图每行显式带全量行数、显示行数、Parquet路径和规则引用。manifest集合、行数、规则、上限任一不一致都会硬拒绝，见 `reporting.py:1621-1653,1705-1777`。
- 全量十表共4828行仅存Parquet；工作簿payload明确 `workbook_views_are_full_detail=false`，序列化大小1,374,885字节，没有把全量逐行明细单体塞给Node，见 `reporting.py:1656-1666,1811-1820`。

## 128MB预检与五工作簿QA

- Python在启动Node前先序列化并检查 `128*1024*1024=134,217,728` 字节硬上限；超限错误明确要求检查Top-N，见 `main.py:175-205`。将限额注入为1字节时在Node前被硬拒绝。
- 临时实际生成且非空的5本XLSX：`backtest_summary.xlsx` 34,179字节、`factor_analysis.xlsx` 182,183字节、`style_box_returns.xlsx` 97,445字节、`portfolio_holdings.xlsx` 63,790字节、`trading_audit.xlsx` 95,230字节；文件名和顺序与Python固定合同一致，见 `main.py:50-63,105-108`。
- 五本合计51张sheet：51/51 inspect NDJSON非空、51/51 preview PNG非空；公式扫描5/5=`no_formula_errors`；OOXML CRC 5/5=`ok`；声明图表5、内存实际图表5、OOXML chart part 5，逐本闭环；Node与Python wrapper warning均为0。
- Python二次门禁分别注入 warning、inspect缺口、preview空文件、formula错误、OOXML CRC错误、chart计数错配，6/6硬拒绝，见 `main.py:91-172`。
- Node端对每个payload中的声明chart先验校验列数、非空行、行宽、有效类别与有限数值，再记录独立declared chart并与内存/OOXML计数闭环，见 `workbook_builder.mjs:186-221,458-508,525-549`。
- 对 CDX-C-05 反例真实注入：`rows=[]`、`columns=[]`、行宽不等、无数值列四类均在builder内硬拒绝，不再把声明chart降为0后假绿。
- Node在inspect/render后、export/OOXML后均对warning硬门禁；Python还核对文件全集、sheet/inspect/preview、公式、声明/实际/OOXML图表与实际preview路径，见 `workbook_builder.mjs:28-45,298-405,406-455,483-508` 与 `main.py:91-172`。

## 正式结果保护与Issues

- 本轮所有新增产物只写 `/tmp`。正式目录 `output/r004_all_a_style_box/results/` 前后均为11个既有文件；按相对路径+原始字节聚合SHA-256始终为 `22b029a84ff9b3fbfeb0aa5c1e7bb7d0bf606994a1e987815c29e04fbe95b078`，最新mtime_ns始终为 `1784372494970769648`；未新增XLSX/Parquet，未覆盖既有正式证据。
- 本轮未发现当前issue。CDX-C-05已由四类实际反例核销；shared common MDD迁移已按期初财富1.0标准口径补齐负首期、首峰后下跌和空序列独立回归并透明披露。

verdict: pass
