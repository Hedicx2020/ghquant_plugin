# r004_all_a_style_box 结果反虚报审计

## 审计结论

本次审计不采信验证者自述，直接读取正式 JSON、XLSX、PNG 与 10 个 Parquet 明细后独立重算。核心收益、绩效、R4、R7、SA4、交易成本、权重加总及明细哈希在现有产物内部能够勾稽，但正式样本存在两项足以改变经济含义的重大数据问题：成长/价值风格覆盖在前 24 个月近乎失效且高度集中；ALL_A 持续按多年陈旧价格持有无法卖出的证券。另有 Excel 验证状态未回填、PIT/风格输入证据缺失及扰动测试不可复核。当前结果不得作为“全 A 大小盘与成长价值因子”的合格正式样本外结论，判定为 `fail`。

## 独立重算记录

| 维度 | 独立核查结果 |
| --- | --- |
| 月度绩效 | `style_box_returns.xlsx/MonthlyReturns` 为 9 实体×33 月=297 行，覆盖 2023-04 至 2025-12。由月净收益独立重算累计收益、CAGR、年化波动、Sharpe、含期初 1 的最大回撤和胜率，9 实体相对 `metrics.json` 最大绝对差为 `5.55e-17`。 |
| E4 三方数值 | `metrics.json`、`backtest_summary.xlsx/Summary`、`style_box_returns.xlsx/Performance` 的月度核心字段最大绝对差为 0；`verify_report.md` 展示值与底层值按其小数位四舍五入一致。 |
| 日度绩效 | `DailyReturns` 为 9 实体×669 日=6,021 行；独立重算 6 个核心绩效字段，相对 `Performance` 日度行最大绝对差为 `5.55e-17`。 |
| 因子恒等式 | 逐月重算 `SMB=0.5(SV+SG)-0.5(BV+BG)`、`HML=0.5(SV+BV)-0.5(SG+BG)`、`GML=-HML`，最大绝对差均为 0。 |
| R4/R7/SA4 | R4 的 7×7=49 个相关单元格最大差为 0；R7 的 BV/BG/SV/SG 胜出月数为 6/8/12/7、频率和为 1；SA4 两套基准共 16 行的年化超额、跟踪误差及信息比率最大差为 0。 |
| 权重与组合 | 198 个组合月目标权重和最大误差 `2.22e-16`；股票实际权重与 `coverage.parquet` 最大误差 `4.44e-16`，股票加现金等于 1。STYLE_1N 每月四箱各 25%，最大误差 `5.55e-17`。 |
| 交易与成本 | 277,037 笔成交的成交额、3bp 佣金、5bp 滑点、卖出印花税、总成本、净现金流逐笔最大误差均为 0；与 turnover/costs 汇总最大误差分别为 `4.44e-16`/`4.34e-19`。成交日期均晚于信号日且等于目标执行日。 |
| Parquet 合同 | 10/10 个正式 Parquet 的实际行数、列名、文件大小与 SHA-256 均与 `detail_manifest.json` 完全一致。 |
| Excel/PNG | 5 本工作簿共 51 个 sheet、51 个 inspect、51 个 render、5 个原生 chart 均存在；51/51 首行加粗且冻结到 A2。8 张主 PNG 与 51 张工作簿 render 已逐张实际查看，无空白或损坏；`group_cumulative_returns.png` 横轴日期标签局部重叠。 |

## K2、K3、E4 与理由核查

- K2：不触发。`comparison.json` 的原研报目标值均为空或 `not_comparable`，不存在“全部可比指标相对偏差同时小于 0.5%”的集合。产物另声称主动执行 hard 扰动，但该测试存在 RA-A05 所述证据缺口。
- K3：未发现以机械恒等式冒充独立复现。HML 与 GML 互为相反数、三条因子与四箱收益的等式成立，属于冻结公式本身；其余 R4、R7、SA4 已由底层月收益独立重算。
- E4：核心月度数值三方一致，但 5 本 Excel 的验证状态及 24 条假设回看文本与当前验证报告矛盾，故 E4/结果包一致性不能判为整体通过，详见 RA-A03。
- skip/infeasible 理由：coverage matrix 共 78 行，其中 14 done、49 skipped、15 infeasible；49 项 skipped 均对应用户明确排除的宏观、ML、动量、低波、质量及周期支线；D15-D29 为原报告未披露名称/定义的输入，`templates/data_catalog.md` 无法从未命名变量推导，15 项 infeasible 理由成立。
- 核验分级：`comparison.json` 未出现 `verification_level != full` 的降级指标，参数不明降级三点核查不适用。

## Issues

### RA-A01

- severity: critical
- 证据定位：`output/r004_all_a_style_box/results/detail_tables/box_membership.parquet`（`signal_date/stock_code/size_bucket_count/target_weight/style_box`）；`workspace/r004_all_a_style_box/plan.md:258`、`workspace/r004_all_a_style_box/plan.md:259`；`output/r004_all_a_style_box/verify_report.md:24`、`output/r004_all_a_style_box/verify_report.md:27`
- 依据：独立按月重算发现，2023-03-31 信号截面只有 17/4,779 只股票具备 Style 分组，覆盖率仅 `0.3557%`，BV/BG/SV/SG 分别只有 3/3/5/6 只；2023-03 至 2025-02 的 24 个信号月覆盖率均不超过 `19.5456%`，直到 2025-03-31 才从 998/5,106（`19.5456%`）突跳为 5,035/5,132（`98.1099%`）。33 月覆盖率中位数仅 `4.4410%`，而 `target_weight` 的单股最大值达到 `94.5519%`。这意味着前 24 个月所谓四风格箱主要是极少数股票的集中组合，与后 9 个月接近全 A 的截面不是同一统计总体；报告仅披露均值 1,558.52/1,554.55，掩盖了断点和集中度，并违反计划要求披露每月覆盖/排除比例、回看大权重驱动的约束。现有四箱、Style IC、HML/GML 及 STYLE_1N 的正式样本外经济结论因此不成立。
- 修复出口：先定位历史估值/财务覆盖断点，按中国市场 PIT 口径补齐可得的 B/P、E/P、S/P、股息率及营收/利润同比；逐月输出覆盖率、排除率、四箱数量和最大/前十大权重。若历史数据无法补齐，应把有效起点冻结为稳定覆盖开始日并明确缩短 OOS，不能把两种截面拼成一条结果；完成后全量重跑并对覆盖阈值和集中度设置阻断门禁。

### RA-A02

- severity: critical
- 证据定位：`output/r004_all_a_style_box/results/detail_tables/holdings.parquet`（`effective_date/stock_code/mark_price/price_source_date/actual_weight`）；`output/r004_all_a_style_box/results/detail_tables/actual_weights.parquet`（`target_weight/actual_weight`）；`output/r004_all_a_style_box/results/detail_tables/unfilled_orders.parquet`（`reason`）；`workspace/r004_all_a_style_box/plan.md:92`、`workspace/r004_all_a_style_box/plan.md:94`；`output/r004_all_a_style_box/verify_report.md:19`
- 依据：虽然不存在未来价格，但 ALL_A 中存在 792 条价格来源滞后超过 365 天的持仓，涉及 49 个代码；每月陈旧持仓权重合计为 `1.1464%` 至 `1.6565%`。最严重的 `601299` 和 `600832` 在 2025-12-01 仍分别按 2015-05-19 的 29.98 元和 23.18 元估值，价格滞后 3,849 天；`actual_weights` 中目标权重均为 0，却因每月 `missing_execution_record` 卖出失败而长期留存。`601299` 单股实际权重最高 `0.9090%`。这不是“无未来价格”即可判定通过的问题：多年不变的陈旧价格既未按退市/换股/现金补偿处理，也未减记，直接污染 ALL_A 净值、现金与相对基准结果，并违反 T 日有效行情和到期退市剔除的冻结规则。
- 修复出口：建立中国市场退市、吸收合并、换股和终止上市事件处理；对无执行记录且已退市的旧仓按真实最后可交易日、换股比例或现金补偿结算，无法恢复时至少按审慎减记规则处理并登记假设。新增阻断检查：持仓价格滞后上限、连续未成交月数、目标为 0 的残余仓位、退市公司处置勾稽；之后重跑 ALL_A、SA4 及全部相对绩效。

### RA-A03

- severity: major
- 证据定位：`output/r004_all_a_style_box/results/{backtest_summary,factor_analysis,style_box_returns,portfolio_holdings,trading_audit}.xlsx/Cover!B7`、各工作簿 `Assumptions!J2:J25`、`Checks!F2:F8`；`workspace/r004_all_a_style_box/assumptions.md:11`；`output/r004_all_a_style_box/verify_report.md:5`、`output/r004_all_a_style_box/verify_report.md:12`；`workspace/r004_all_a_style_box/audit/evidence_manifest.md:12`、`workspace/r004_all_a_style_box/audit/evidence_manifest.md:30`
- 依据：5 本正式工作簿的 Cover 均仍写 `pending_verifier`，每本 Assumptions 的 24/24 行仍写“Excel首行冻结门禁失败”或“整体验证不通过”，Checks 的 7 个 `verifier_result` 全为空；而当前 assumptions、verify_report 和 evidence_manifest 声称 attempt=2 已修复且整体 PASS。核心数字虽一致，用户实际拿到的结果包却同时包含相反验证结论，E4/证据链并未闭环。
- 修复出口：在最终 verifier 回填后重新生成全部 5 本工作簿及 51 张 QA render；逐本校验 Cover 状态、24 条假设回看和 Checks 结果与当前 assumptions/verify_report 一致，再更新 detail/QA manifest 与证据清单哈希。

### RA-A04

- severity: major
- 证据定位：`workspace/r004_all_a_style_box/audit/evidence_manifest.md:34`；`output/r004_all_a_style_box/verify_report.md:9`、`output/r004_all_a_style_box/verify_report.md:18`；`output/r004_all_a_style_box/results/detail_tables/box_membership.parquet`（全部 13 列）；`output/r004_all_a_style_box/results/detail_tables/ic_observations.parquet`（全部 10 列）
- 依据：正式证据声称 current/prior 披露日晚于信号日为 0 且 Value/Growth/PIT 已独立重算，但 10 个交付 Parquet 均未保留 `info_publ_date`、`end_date`、当期/上年同期报告标识、B/P/E/P/S/P/股息率、营收/利润同比、Value/Growth 分数及有效分量数。现有 box membership 只有最终箱标签和排序位置，无法由结果包独立复核 PIT 无未来、复合价值以及成长轴构造；这是核心因子的证据缺口。
- 修复出口：新增带 SHA-256 的全量 `pit_style_inputs.parquet`（或等价拆表），至少保留 signal_date、stock_code、每个源字段值、info_publ_date、end_date、prior end/info date、有效分量数、各分量方向/标准化值、Value/Growth/Style 分数及最终箱标签；由审计者直接验证 `info_publ_date <= signal_date` 和同比财政期匹配后再声明 PIT 通过。

### RA-A05

- severity: major
- 证据定位：`workspace/r004_all_a_style_box/audit/evidence_manifest.md:62` 至 `workspace/r004_all_a_style_box/audit/evidence_manifest.md:69`；`output/r004_all_a_style_box/verify_report.md:111` 至 `output/r004_all_a_style_box/verify_report.md:116`；`output/r004_all_a_style_box/results/metrics.json`（`verifier_addendum`）
- 依据：hard 扰动只以文字和前后两个汇总数存在，没有持久化的扰动配置差异、执行命令/退出码、独立 metrics/comparison、明细 manifest/哈希或可重算输出。结果审计无法证明测试实际执行、仅修改 `oos_end`，也无法验证声称保持的 R4/R7/PIT 约束；“复用 attempt=1”不是独立证据。
- 修复出口：将扰动作为独立只读审计产物落盘，保存精确配置 diff、命令、时间、退出码、扰动 metrics/comparison、R4/R7/PIT 明细检查和关键 Parquet 哈希；禁止覆盖正式结果，证据清单只引用可读回的文件。

### RA-A06

- severity: minor
- 证据定位：`output/r004_all_a_style_box/results/group_cumulative_returns.png`；`output/r004_all_a_style_box/verify_report.md:109`
- 依据：实际查看发现双子图横轴日期标签密集重叠，影响读取月份，但未改变曲线或数值。
- 修复出口：减少刻度密度或旋转标签，重出该 PNG 并更新 QA render/清单。

## 已检查且未发现问题的维度

- K2 触发条件、K3 机械恒等式风险、核心数值 E4 三方勾稽、verification_level 降级、skip/infeasible 理由。
- 9 实体月度绩效、9 实体日度绩效、R4、R7、R10、SA4、SMB/HML/GML 公式、STYLE_1N 四箱 1/N 权重。
- 成交额、佣金、滑点、印花税、净现金流、turnover/costs 汇总、目标/实际/现金权重加总。
- 10 个 Parquet 的行列/大小/SHA-256、5 本 Excel 的 sheet/chart/冻结/加粗、8 张主 PNG 与 51 张工作簿 render 的实际可视检查。
- 信号日到执行日严格为正且成交日在目标执行日；持仓不存在 `price_source_date > effective_date` 的未来价格。注意：陈旧价格问题另见 RA-A02。

## 最终判定

独立重算证明现有文件内部多数算术链一致，但 RA-A01 与 RA-A02 直接破坏“全 A 成长价值/大小盘因子”的样本外经济有效性；RA-A03 至 RA-A05 又使交付包及关键证据不可闭环。必须按修复出口重建数据、组合和证据后重新执行 result audit。

verdict: fail
