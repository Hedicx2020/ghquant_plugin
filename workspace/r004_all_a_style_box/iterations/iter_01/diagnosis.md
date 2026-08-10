# r004_all_a_style_box iter_01 诊断

## 诊断结论

本轮失败不是收益公式或四箱恒等式的算术错误，而是两条会改变经济含义的数据链缺陷：历史日估值表覆盖断裂导致 Style 截面失效；组合执行器对终止行情证券无限沿用最后价格。两项均有明确修复路径，且独立覆盖试算表明现有 PIT 资产负债表/利润表足以恢复全部 33 个正式信号月的高覆盖截面，因此本轮不属于数据不可得型阻塞。

基线收益、IC、胜出频率、相关矩阵和相对基准结论均受 RA-A01/RA-A02 影响，修复前的数值只能作为失败基线，不能预设修复后方向，也不能为了保留原收益而调参数。

结论: continue

## 本轮失败快照

| 问题 | 独立观察 | 影响 |
| --- | --- | --- |
| RA-A01 风格覆盖断层 | 2023-03-31 仅 17/4,779 只有效，覆盖 0.3557%；前 24 个信号月最高 19.5456%；33 月中位数 4.4410%；2025-03-31 突跳至 98.1099%；单股目标权重最高 94.5519% | 前 24 月四箱、Style IC、HML/GML、STYLE_1N 与后 9 月不是同一统计总体，经济结论无效 |
| RA-A02 陈旧持仓 | 792 条持仓价格滞后超过 365 天，涉及 49 个代码，全部位于 ALL_A；月末陈旧权重合计 1.1464%–1.6565%；601299/600832 最长 3,849 天 | ALL_A、SA4、现金及相对绩效被陈旧价格污染 |
| RA-A03 Excel 旧状态 | 5/5 Cover 仍为 `pending_verifier`，Assumptions 保留首次失败文本，Checks 的 verifier_result 为空 | 正式交付包与 verify_report/assumptions 相互矛盾 |
| RA-A04 因子底层证据 | 10 个正式 Parquet 均未保留 Value/Growth 的财务期、披露日、分量和得分 | PIT 与风格构造无法由交付包复核 |
| RA-A05 扰动证据 | 只有文字和前后汇总值，无独立配置、命令、退出码、metrics/comparison、明细哈希 | hard 扰动不可重放 |
| RA-A06 图标签 | `group_cumulative_returns.png` 日期标签重叠 | 可读性不达标 |
| CDX-R-02 gross/net 语义 | 当前 `gross_return` 与目标理想组合混用解释，AS12 用成交/未成交和成本公式直接声称方向已验证；部分实体年化 net 高于 gross | 成本拖累与交易约束暴露变化没有拆开 |
| CDX-R-01/R-03 结论边界 | 工作簿结论过期；最终 PASS 未同时带出 33 月、北交所、退市覆盖和 2025-12 持有期记至 2026-01-05 等边界 | 容易被误读为长期稳定或完整全历史证明 |

## 根因

### 根因一：Value 数据源覆盖断点，不是 Growth 或 Size 公式失效

`data_pipeline._load_market_slices()` 只读取 `ashare_stock_value.parquet` 在信号日的精确记录，`_attach_valuation_inputs()` 再由 `1/pb_lf`、`1/pe_ttm`、`1/ps_ttm` 和 `dv` 构造四个 Value 分量；`strategy.calculate_style_factors()` 要求至少 2 个 Value 分量。该估值表在早期正式 OOS 截面只有极少记录，2025-03 才接近全量，因此 Growth 虽有约 98% 覆盖，仍被 Value 的 2/4 门槛截断。

独立读取本地数据并按披露日做 PIT 试算得到：

- `ashare_stock_balance.parquet` 与 `ashare_stock_income.parquet` 均自 2000 年起，分别约 126.7 万、145.2 万行；字段含 `info_publ_date`、`end_date`、股东权益、营收和净利润。
- 用信号日总市值作分母，PIT 股东权益构造 B/P，PIT TTM 净利润/营收构造 E/P、S/P；正股东权益、正 TTM 盈利和正 TTM 营收的单项月覆盖最低分别约 97.7610%、72.2687%、97.8358%。亏损公司 E/P 缺失不妨碍 B/P+S/P 形成 2 个核心分量。
- 冻结“核心三项至少 2 项有效、Growth 两项至少 1 项有效”后，33 个信号月 Style 覆盖最低约 97.8146%，全部 33 月均高于 95%；最新财政期相对信号日的 99 分位滞后最大约 210 天。故可形成不少于 24 个月的稳定高覆盖 OOS，不应缩短到 2025 年才开始。
- 2025-03-31 横截面中，财务重建 B/P、年度近似 E/P/S/P 与直接 `1/PB/PE/PS` 的方向一致；B/P、S/P相关性约 0.91/0.99。正式实现仍须使用严格 TTM，而非年度近似。

股息率没有本地现金分红事件表可自底向上完整重建，允许作为第四个可选 Value 分量，但只能使用来源日在信号日或此前不超过 5 个交易日的 `dv`，并保留来源日；超过 5 个交易日或缺失时，Value 只用 PIT 三核心分量，禁止长期前填。

### 根因二：状态回测把“无未来价格”误当成“陈旧价格可无限使用”

`portfolio._execute_rebalance()` 在执行记录缺失时产生 `missing_execution_record`，但 `state.last_prices` 不设寿命；`_update_close_marks()` 与 `_mark_terminal_event()` 又用 `combine_first(last_prices)` 永久估值。目标权重已归零也无法清仓，因而形成僵尸仓位。

49 个代码可分为两类：16 个在正式 OOS 前已终止行情且未出现在当前股票主表，例如 601299、600832、300186、000024；它们由历史预热状态跨入正式 OOS。其余代码在 OOS 内进入或持有，随后停止行情，主要为 2023–2024 年退市/终止上市证券。当前 `ashare_stock.parquet` 仅含 5,527 个 `list_state=1` 的现存证券，不能提供历史退市日期；仅凭未来“再也没有报价”反推最后交易日并在该日强制卖出会构成前视。按零减记同样没有现金补偿、换股或退市结算依据。

正确处理必须分层：正式 OOS 首个执行日从现金初始化，不继承 2015–2023 的仓位；正常停牌仅在当日可观察的停牌区间内沿用最后价格；退市整理期可依据当日已知名称/状态触发风险退出，并按下一可交易日真实价格成交；吸收合并、换股、现金选择权和主动退市必须由带公告/生效日的事件映射结算。没有事件映射时不得猜测换股比例或按零，必须把未处理事件作为正式运行阻断项。

## 锁定修改点一：重建 Value/PIT 与中国市场证券终止事件链

### 允许 coder 改动的文件范围

- `src/r004_all_a_style_box/config.py`
- `src/r004_all_a_style_box/data_pipeline.py`
- `src/r004_all_a_style_box/strategy.py`
- `src/r004_all_a_style_box/portfolio.py`
- `tests/test_r004_all_a_style_box_data.py`
- `tests/test_r004_all_a_style_box_portfolio.py`

不得修改 `spec.md`、`plan.md`、`assumptions.md`、`state.json` 或历史迭代文件；不得新增 Momentum、Quality、Low Volatility、宏观或 ML 输入。

### 给 coder 的具体指令

1. 在 m1 增加 PIT 资产负债表与利润表 TTM 构造：所有记录先筛 `info_publ_date <= signal_date`，再选当时可得版本；B/P=`positive(total_shareholder_equity)/signal_date_market_value`；年度报告直接取年度营收/净利润，非年末累计报告用“当期累计 + 上年年报 - 上年同期累计”形成 TTM；E/P 仅正 TTM 净利润有效，S/P 仅正 TTM 营收有效。保留 current/prior/FY 的 `end_date`、`info_publ_date` 和计算项。
2. Value 核心冻结为 B/P、E/P、S/P 的月度截面 1%/99% 缩尾百分位秩，至少 2/3 有效；`dv` 仅在来源日不晚于信号日且年龄不超过 5 个交易日时作为第四分量，缺失时仍按三核心可得项均值。Growth 继续只用 PIT 营收/净利润同比，Style 仍为 Growth-Value；Size 仍只用信号日总市值。不得以行业、动量、质量或 OOS 收益调节公式。
3. 正式 OOS 与历史诊断分开建仓：首个正式执行日各组合从 NAV=1、全现金开始，预热期只用于方法冻结/诊断，不携带股票、现金或累计成本进入 OOS。
4. 增加证券生命周期状态：逐日记录 `price_age_trading_days`、连续缺行情日、活跃停牌、退市整理标记、事件类型、生效日、结算代码/比例/现金和证据来源。仅用当日及此前已知事件；停牌继续持有，恢复后按原月频规则处理；退市整理期允许风险退出；换股/现金结算按显式事件生效。不得从未来最后报价日倒推事件，不得无依据减记为零。
5. 若 OOS 内存在目标为 0、非活跃停牌且连续 20 个交易日无行情的残余仓位，又无可核对的终止事件映射，正式入口必须非零退出并列出代码，不能生成 PASS 结果。

### 验收阈值

- 正式 33 个信号月每月 `Style有效数/eligible数 >= 95%`，且至少 24 个连续月 `>= 97%`；月度覆盖最大跳变不超过 5 个百分点。
- 每月四箱均非空；每箱成员不少于 `max(100, eligible_count×10%)`；Big/Small 和各自 Growth/Value 的数量差仍不超过 1。
- 任一四箱单股目标权重 `<= 10%`，前十大目标权重合计 `<= 50%`；逐月披露最大权重和前十大权重。
- PIT 违规必须为 0：所有 balance/income/dividend 来源日 `<= signal_date`；TTM 三段财政期键逐行匹配；不允许 bfill。
- 正式 OOS 首日股票持仓数为 0、现金权重为 1；预 OOS 证券进入正式 OOS 的行数为 0。
- 非活跃停牌、无事件映射的持仓 `price_age_trading_days > 20` 行数为 0；目标为 0 且连续两次调仓仍残留、又无停牌/事件理由的行数为 0；未来事件或未来价格使用为 0。
- 每条换股/现金/退市结算均可由 `event_effective_date <= processing_date`、比例/现金和来源重算；无法重算即阻断，不得按零通过。

### 预期变化

- Style 月覆盖从最低 0.36%、中位 4.44% 提升至约 97.8%–98.3%，提升约 78–98 个百分点；2025-03 的机械断点消失。
- 最大单股权重从 94.55% 降至 10%以内，通常应明显低于该上限。
- 792 条超过 365 天的陈旧持仓和 49 个未解释代码应降为 0；16 个 OOS 前遗留代码由现金初始化直接消除，其余必须由当期交易/事件链处理。
- 四箱、HML/GML、STYLE_1N、IC 和 ALL_A 的收益方向与量级均可能实质改变，不设保留原值目标；ALL_A 仅当前陈旧权重就约 1.15%–1.66%，变化不能预先视为可忽略。

## 锁定修改点二：把底层证据、gross/net 语义与最终交付闭环

### 允许 coder 改动的文件范围

- `src/r004_all_a_style_box/reporting.py`
- `src/r004_all_a_style_box/main.py`
- `src/r004_all_a_style_box/workbook_builder.mjs`
- `tests/test_r004_all_a_style_box_reporting.py`

正式 `output/r004_all_a_style_box/` 只能由后续 verifier 全量重跑/最终化，不允许 coder 手工改 JSON、Excel、PNG 或 Parquet。

### 逐 issue 修复指令

- RA-A03/CDX-R-01：把“生成待验证结果”和“verifier 最终化”拆开。最终化入口必须消费 verifier 写入的只读验证上下文，再重建 5 本工作簿；Cover 为 `verified/PASS`，24 条 Assumptions 使用当前回看，Checks 的 7/7 `verifier_result` 非空。无验证上下文时只能输出 `pending_verifier`，不得自称 PASS。
- RA-A04：新增全量 `pit_style_inputs.parquet`，至少含 signal_date、stock_code、eligible、总/流通市值、B/P/E/P/S/P/dv及来源日、各 PIT 财务期/披露日、TTM三段值、有效分量数、Growth两项、各缩尾/秩值、Value/Growth/Style、Size/Style箱标签。新增 `security_event_audit.parquet`（或等价拆表），保留陈旧价格与事件结算链。二者写入 detail manifest、Excel来源/检查页和证据清单。
- RA-A05：扰动输出放入独立目录，不覆盖正式结果；持久化精确配置 diff、命令、开始/结束时间、退出码、metrics、comparison、关键明细、PIT/R4/R7检查和 SHA-256。正式 evidence manifest 只引用实际可读文件。
- RA-A06：日期轴最多显示 12 个主刻度并旋转/错行，重出 `group_cumulative_returns.png`；QA render 中不得出现重叠到无法辨识的月份。
- CDX-R-02：明确三层语义：目标组合参考收益、受约束实际持仓成本前收益、同一实际持仓成本后净收益。若不输出第一层，不得把实际 gross 称为“理想组合”。从同一 OOS 初始 NAV=1 出发，期末累计成本前 NAV 不低于成本后 NAV；允许单月净收益因分母/现金暴露不同而高于毛收益，但 AS12 不得据此声称每月方向。
- CDX-R-03：所有最终结论紧邻披露：实验性中国市场迁移、仅 33 个月、含北交所、证券生命周期数据边界、交易成本/可交易约束、2025-12 持有期记账到 2026-01-05、不构成投资建议；禁止将 PASS 表述为长期稳定性证明。

### 验收阈值

- 明细至少由 10 表增至 12 表，新增 PIT/事件表均有行列数、文件大小和 SHA-256，实际读回 100% 匹配 manifest。
- PIT 表覆盖全部 eligible 行；由该表独立重算 Value/Growth/Style/箱标签最大绝对误差 `<=1e-12`，PIT未来披露 0 条。
- 事件审计中未解释陈旧仓位 0 条；全部事件结算的持仓、现金和收益勾稽误差 `<=1e-12`。
- 5/5 Cover=`verified/PASS`，`pending_verifier` 为 0；Assumptions 24/24 与最终登记簿一致；Checks verifier_result 7/7 非空；51/51 inspect、51/51 render、51/51 A2 冻结和所有原生图表继续通过。
- 扰动目录包含完整可重放合同，命令 exit=0；扰动前后正式结果目录 SHA 不被覆盖；R4=49、R7频率和误差 `<=1e-12`、PIT违规=0。
- gross/net 三层字段名、Excel标题、metrics定义和报告措辞一致；同一实际持仓期末 `gross_before_cost_nav >= net_nav`，累计差与成本现金流勾稽误差 `<=1e-12`。
- 8/8 PNG 可辨；累计收益图日期标签目视无重叠。

### 预期变化

- 证据表由 10 个增至至少 12 个，RA-A04/RA-A05 从文字声明变为可重算证据。
- 5 本工作簿的旧验证状态全部清零，Excel、metrics、verify_report 和 assumptions 只保留一个最终结论。
- 成本纯拖累与交易约束暴露变化可分离；不保证每月净收益低于毛收益，但同一起点累计净值应不高于成本前净值。

## 需由主会话修订的假设登记项

本 agent 不修改 `assumptions.md`。实现前/后应由有权限的对应角色更新以下条目，且不得把本轮 OOS 结果用于选择阈值：

- AS12：补充三层 gross/net 语义、正式 OOS 现金初始化、证券终止事件和“单月净收益不必逐月低于毛收益”的边界。
- AS14：由“Growth 利润表 PIT”扩展为 balance/income 全部 Value/Growth 输入的 PIT 与 TTM 三段规则。
- AS15：明确当前主表只有现存证券、不得回溯筛选，同时正式 OOS 不继承历史仓位；退市/合并事件缺失时阻断。
- AS18：改为 PIT B/P、E/P、S/P 三核心至少 2 项，fresh `dv` 为可选第四项；登记 5 交易日 freshness、95%覆盖和集中度门槛。
- AS20：同池 ALL_A 必须应用与四箱一致的 OOS 初始化、停牌和证券终止事件处理。
- AS24：明确 2025-12 持有期在 2026-01-05 结算只是月度记账端点，不是扩展 OOS 信号信息集。

## 已排除假设

- 已排除“Growth PIT 覆盖不足是主因”：两项 Growth 至少一项有效的月覆盖最低约 98.11%。
- 已排除“Size 轴或稳定排序造成 2025-03 断点”：Size 使用约 4,357–5,147 只月度 eligible 股票，断点只出现在估值分量。
- 已排除“必须缩短 OOS 到 2025-03以后”：财务重建试算全部 33 月 Style 覆盖最低约 97.81%，可保留用户指定正式区间。
- 已排除“增加 Momentum/Quality/Low Volatility/宏观/ML 才能补覆盖”：缺口可由同一 Value/Growth 范围内的 PIT 会计数据修复，新增因子会违反用户范围。
- 已排除“以未来最后报价日强制卖出”与“退市后一律按零”：前者有前视，后者缺现金/换股结算依据。
- 已排除“内部算术误差导致 RA-A01/RA-A02”：现有月收益、因子恒等式、交易成本和权重勾稽均能重算；失败在数据总体与状态语义。
- 已排除“RA-A03 只是展示问题”：Excel 是正式交付物，过期验证状态会直接误导使用者，必须最终化重建。

## 风险与回滚

- TTM 三段必须处理同日多版本、合并/单体、调整前后口径；任何财政期键错配会同时改变 Value 和 Growth，应以合成乱序/多版本回归测试及全量 PIT 证据阻断。
- 事件映射是当前最大剩余外部风险。若无法得到带有效日的吸收合并/现金选择权/换股信息，正式运行必须 blocked，不能用当前主表或未来行情缺失反推。
- 覆盖与集中度阈值一经登记不得依据新收益修改；若重建后达不到阈值，应报告数据不可用，不得回退到旧估值表、缩短为 2025 后样本或放宽门槛。
- 修改前保留 iter_01 基线 comparison 与当前结果哈希；新正式结果只能由 verifier 全量重建。若测试失败，只回退本轮允许范围内的实现变更，不覆盖历史审计与迭代证据。
- 任何收益方向变化都视为修复后的真实传导；不得以“接近旧结果”为验收条件。

## 防兜圈自检

- 本轮锁定修改点：2 个；未超过上限。
- 假设族：数据覆盖/PIT 重建；证券生命周期/证据最终化。此前无 no_improve 历史。
- iter_01 无连续两轮无改善与同指标三轮失败情形。
- 允许改动文件范围已逐项列明；预期变化方向与量级已给出。

