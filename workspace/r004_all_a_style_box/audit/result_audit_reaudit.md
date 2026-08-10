# r004_all_a_style_box result_audit 独立复审

- 复审角色：`quant-auditor`（result 模式）
- 复审日期：2026-07-19
- 证据范围：只读正式 `output/r004_all_a_style_box/results/` 中 7 份 JSON、12 张全量 Parquet、5 本 XLSX、8 张正式 PNG、51 张工作簿 QA 渲染，以及当前 `spec.md`、`plan.md`、`assumptions.md`、`coverage_matrix.md`；历史审计文件只用于取得待关闭 issue ID，不把 coder/verifier 自述当作通过证据。
- 禁止项确认：未运行或修改 `src/`、`tests/`、`state.json`、正式 `output/`；复审期间正式结果文件保持只读。

## 一、结论先行

正式产物在 PIT、风格覆盖、集中度、交易成本公式、R4/R7/SA4 的“月表内部重算”、工作簿最终化和图形可读性方面已有实质修复；但仍有两个 `major` 证据链缺口：

1. 月频实际收益无法与日频实际持仓账本逐期勾稽，直接影响 R4、R7、SA4 所依赖的月度路径。
2. 生命周期表存在 19,598 个同键互相矛盾的双记录，600466 及另外 16 只证券仍以超过 365 日的陈旧价格保留；600466 没有终止上市/转板成交/结算的闭环证据，却被标记为非阻断。

因此旧 `RA-A02` 未关闭，新增收益边界问题也不允许 result gate 通过。

## 二、正式结果集完整性

### 2.1 文件与 manifest

- 12/12 Parquet 均可读；实际行数、列数、列顺序、文件 SHA-256 与 `detail_manifest.json` 全部一致，`readback_matches_written_frame` 全为 `true`。
- 关键全量行数：`holdings` 490,725；`target_weights` 489,108；`actual_weights` 491,648；`trades` 510,462；`unfilled_orders` 192,912；`ic_observations` 947,414；`pit_style_inputs` 165,138；`security_event_audit` 42,596。
- 冻结摘要：`metrics.json=883bc470...f5a9b8bf7c`，`comparison.json=ba98f12e...e2e218`，`detail_manifest.json=85b9e283...1029b8`，`workbook_qa_manifest.json=cfb807ef...321f2f4`。

结果：`pass`。

### 2.2 OOS 时间边界

- `pit_style_inputs` 有 33 个连续持有月，`2023-04` 至 `2025-12`；信号日为 `2023-03-31` 至 `2025-11-28`。
- `target_weights` 最晚信号日为 2025-11-28，未发现 2026 年信号或目标权重；2026-01-05 只出现在末期收益记账端。
- 正式边界披露已覆盖：中国实验迁移、33 个月、北交所、生命周期、交易限制与成本、2026-01-05 会计端点、非投资建议。

结果：`pass`。

## 三、独立重算

### 3.1 PIT、风格覆盖与集中度

对 `pit_style_inputs.parquet` 全量 165,138 行重算：

- `period_available_date`、当前/同期/上年末 `info_publ_date`、资产负债表披露日、B/P、E/P、S/P、TTM、分红来源日均没有晚于信号日的记录。
- 162,198 条当前期与上年同期财政期键的月日和年度差全部正确；162,198 条 prior-FY 均为当前财政年的上一年 12-31。
- TTM 收入、TTM 净利润、对称营收增长、对称净利润增长、B/P、E/P、S/P、log(MV)、component count、Value/Growth/Style score 最大绝对误差均为 0。
- `box_membership` 与 `pit_style_inputs` 的 161,985 个有效成员键完全一一对应，标签、排序位置、桶计数、权重均一致。
- 33/33 月 Style 覆盖率均高于 97%；最低 97.8146%，最大相邻跳变 0.2394 个百分点。每月四箱齐全，单箱最少 1,057 只。
- eligible 的 Big/Small 人数差最大 1；每个 size 内 Growth/Value 人数差最大 1。
- 四箱每月权重和最大误差 `1.11e-16`；最大单股权重 9.2989%，前十大最高 30.2796%，满足 10%/50% 冻结阈值。
- 北交所证券证据为 7,262 行、266 个代码、覆盖 33 个信号月。

旧 issue：`RA-A01`、`RA-A04` 已关闭。

结果：`pass`。

### 3.2 月频绩效、R4、R7、SA4 的月表内部重算

从 `MonthlyReturns` 的 9×33=297 行独立重算：

- 9 个实体的累计收益、年化收益、月频波动率、Sharpe、含期初 NAV=1 的最大回撤、胜率与 `metrics.json` 最大误差为 0（最大回撤浮点误差 `5.55e-17`）。
- SMB/HML/GML 每月均可由四箱月收益按冻结公式重建，gross/net 最大误差均为 0；HML 与 GML 逐月互为相反数。
- R4 的 7×7=49 个相关单元格与月表重算最大误差 0，对角线及对称性误差 0。
- R7 的 33 月胜者为 BV 8、BG 4、SV 10、SG 11，频率合计 1；逐月标签误差 0。
- SA4 为两个基准各 8 行，共 16 行；年化算术超额、年化跟踪误差、信息比率最大误差均为 0。
- `ic_observations` 的 1 个月 Size/Style Pearson IC、RankIC 共 66 个序列值与工作簿最大误差分别 `3.89e-16`、`5.55e-17`。

但这些只证明“月表内部自洽”，不能覆盖下节的月/日账本断裂。因此 R4/R7/SA4 为 `conditional_pass`，不是 result gate 的最终通过依据。

### 3.3 交易与成本

- 510,462 笔交易均晚于信号日，最小日历滞后 1 天；同日或前置信号成交为 0。
- `gross_notional=abs(shares×VWAP)`、双边佣金 3bp、双边滑点 5bp、卖出印花税（2023-08-28 前 10bp、之后 5bp）、逐笔总成本、买卖净现金流最大误差均为 0。
- 交易按日期/信号/月/组合聚合后，与 356 行 `costs` 和 356 行 `turnover` 的买入、卖出、总成交、成本分项最大误差不超过 `1.11e-16`。
- 全部实际交易成本为 `0.048195379289349145`。六个有独立持仓账本的 long portfolio，期末 gross NAV－net NAV 与各自成本现金流误差均不超过 `3.28e-15`。
- HML 的 net 累计收益高于 gross，但该实体被明确标为合成多空因子，`cumulative_cost_cash_flow=null`，成本字段只是四腿均值而非独立成交簿；没有再把它归因为可实现的“纯成本拖累”。

旧 issue：`CDX-R-02` 已关闭。

结果：`pass`。

## 四、未关闭与新增 issue

### [RA-R01] 月频与日频实际收益账本不能逐期勾稽

- 严重度：`major`
- 影响：R4、R7、SA4、月频波动/回撤/胜率以及所有声称来自实际持仓的月度路径。

独立检查发现：

1. 对 `DailyReturns` 按同一 `entity + holding_month` 复合，297/297 个实体月均不等于 `MonthlyReturns` 的 `actual_before_cost_return` 和 `actual_after_cost_net_return`。
2. 最大净收益差为 11.1855 个百分点：SG/2024-10 的月表净收益为 1.4304%，日表同 `holding_month` 复合为 12.6159%。
3. 将 `MonthlyReturns.date` 与 `DailyReturns.date` 同日连接，291/297 个累计 gross/net NAV 不相等；最大净值绝对差为 0.022794：SG/2024-10 月表为 1.043724，日表同日为 1.020930。
4. 六个 long portfolio 的最终累计 NAV 可与日表末值对上，说明这不是简单终值错误，而是月度收益/成本/事件归属边界发生了未披露的重分配。三个合成因子的月/日末值也不完全一致，进一步表明两套频率采用了不同的合成或再平衡口径。
5. 正式 JSON、XLSX、假设登记簿没有给出能把这两条路径逐期桥接的边界表或 reconciliation 字段。

判定：月表虽能重算自身的 R4/R7/SA4，但尚不能证明这些月度结论来自同一套日频实际持仓账本。必须统一持有期边界，或提供逐实体逐月的日表起止 NAV、事件/成本归属桥接并将误差压到机器精度，再重建 R4/R7/SA4。

状态：`open`。

### [RA-R02 / RA-A02] 生命周期审计存在同键矛盾记录，600466 终止链未闭环

- 严重度：`major`
- 影响：实际持仓估值、全A与部分风格箱收益、退市/转板中国市场适配可信度。

独立检查发现：

1. `security_event_audit` 有 42,596 行，但 `(date, portfolio, stock_code)` 只有 22,998 个唯一键；19,598 个键各有两条记录，且两条在 `price_age_trading_days`、`consecutive_missing_price_days`、`delisting_board_flag`、`rule_label` 上互相矛盾。一条常为 `age=0 / delisting_board_flag=True / waiting_daily_can_sell`，另一条为 `age>0 / flag=False / known_event_missing_price_observation`。表内没有来源层级或有效记录选择字段，无法判断哪条状态驱动了估值与执行。
2. `holdings` 仍有 373 条月度持仓记录、17 个代码的价格来源早于有效日超过 365 个日历日；最大单个“月×组合”陈旧权重合计为 0.1473%。该量级较旧结果下降，但并未消失。
3. 600466 在 ALL_A 中有 33 条月度持仓；除首月外 32 个月目标权重均为 0，仍有 32 次卖出未成交（`missing_execution_record` 30、停牌 1、跌停 1）。
4. 600466 的最后价格来源日为 2023-06-05、价格 0.40 元，仍被用于 2025-12-01 持仓估值；末期已陈旧 910 个日历日/627 个交易日。事件表为 1,277 行但只有 650 个日期，同样存在双记录。
5. 600466 的正式事件只有 `announced_security_lifecycle_risk_exit`，结算代码为空、比例/现金为 0、VWAP 为空；没有终止上市、转板可交易行情、现金结算或换股的闭环行，却全部标记 `blocking=False`、`unexplained_stale_residual=False`。

判定：披露“保留陈旧估值”只能说明边界，不能替代可重算的中国退市/转板生命周期映射；而同键矛盾记录使该边界本身也无法独立判定。当前证据不满足 AS15/AS20 所写的“事件缺失或不可重算即阻断”。

修复要求：生命周期证据必须归一为一条有效日状态记录，保留来源优先级和选择理由；对 600466 及 16 个其他超 365 日代码补齐终止上市/转板/结算节点、可交易价格与成交量来源、估值政策和实际退出规则。无法补齐者应阻断正式运行或从该日开始单列不可估值资产及区间，而不是继续给出 `PASS`。

状态：`open`；旧 `RA-A02` 未关闭。

### [RA-R03] hard 扰动的边界披露仍引用正式基线

- 严重度：`minor`
- 影响：扰动证据的自包含性，不直接改变正式 output 数值。

扰动目录已持久化完整的 12 Parquet、5 Excel、8 PNG、JSON、51 QA，`config_diff.json` 只改变 `oos_end: 2025-12-31 → 2025-11-30`。除 `ic_observations` 的自然可观察期限外，11 张表的正式公共前缀与扰动全表逐行多重集哈希一致；IC 按 1/2/3 个月各自公共可观察末月比较也完全一致。因此旧 `RA-A05` 的“没有耐久证据”问题实质关闭。

但扰动 `metrics.json` 明确是 32 个月、截至 2025-11，而其中 `final_boundary_disclosures` 仍写“33个月、截至2025-12、2026-01-05端点”。扰动工作簿也沿用这组基线披露。应按扰动配置生成自洽的边界文字。

状态：`open_minor`；不单独决定 gate，但需修正。

## 五、工作簿与图形

- 5/5 XLSX Cover 均为 `verified/PASS`，验证上下文 SHA 一致；每本均有 24 条 Assumptions、7 条 Checks 且 Checks 全为 PASS，未发现旧的 `pending_verifier` 或失败占位文本。
- 5 本共 51 个 sheet；51/51 QA PNG 与 sheet 名一一对应、非空。OOXML CRC 正常、公式错误扫描为 0、所有 sheet 均冻结 A2、隐藏网格、首行加粗；图表数为 5。
- 已目视检查 51 张渲染（长表另检查顶部/中段/尾部）及 8 张正式图。8 张正式图均可读、约 300 DPI；`group_cumulative_returns.png` 的日期标签已旋转并可辨认，旧重叠问题关闭。

旧 issue：`RA-A03`、`RA-A06`、`CDX-R-01` 已关闭。`CDX-R-03` 的正式边界披露已关闭，但扰动副本仍有 `RA-R03`。

结果：`pass`（仅指包装与视觉，不覆盖 RA-R01/RA-R02）。

## 六、旧 issue 关闭矩阵

| issue | 复审状态 | 独立依据 |
| --- | --- | --- |
| RA-A01 覆盖/集中度 | closed | 33/33 月覆盖>=97%；最低97.8146%；单股9.2989%；Top10 30.2796% |
| RA-A02 陈旧持仓/生命周期 | open | 19,598个同键矛盾双记录；17代码仍>365日；600466终止链未闭环 |
| RA-A03 工作簿 pending/Checks | closed | 5/5 verified/PASS，24条假设，7/7 Checks |
| RA-A04 PIT证据缺失 | closed | 165,138行、77列；披露日与全部公式可重算 |
| RA-A05 hard扰动无耐久产物 | closed_with_minor | 完整目录与12表公共前缀一致；边界文字仍有RA-R03 |
| RA-A06 日期标签重叠 | closed | 正式PNG目视可读 |
| CDX-R-01 工作簿状态 | closed | 与RA-A03同证据 |
| CDX-R-02 成本方向误归因 | closed | long portfolio成本现金闭环；合成因子无独立现金账本已明确 |
| CDX-R-03 结论边界缺失 | closed_formal | 正式7项披露齐全；扰动副本另见RA-R03 |

## 七、最终判定

- `critical`: 0
- `major`: 2（RA-R01、RA-R02/RA-A02）
- `minor`: 1（RA-R03）
- result gate：不得通过。

verdict: fail
