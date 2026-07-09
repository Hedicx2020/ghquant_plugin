# 实现忠实性审计 · test_v2 · milestone m7（周内效应 + 复合跷跷板 + 隔日反转最终策略 · 报告落脚点）

- 审计模式: code（实现忠实性，hard 逐条核对）
- 审计对象: m7 四要素——F5（周内信号 signal_calendar / signal_daily_upper_calendar）、F8（三步决策树，build_final_reversal_position + assemble_signals）、R11（表11 业绩，build_r11_table + run_final_strategy，报告落脚点）、R12（表12 分年业绩，build_r12_yearly_table）
- 审计原则: 只读不改产物；数值一律独立重算，不采信 coder 自述与冒烟结论；与 coder 无交流
- 独立重算依据: 源码逐行反查（combo_final.py / combo_composite.py / reversal.py / strategy.py / config.py / common）；独立装配 F5/F8 信号并与 combo_final_signals 决策树逐日比对；独立重算决策树三步分支计数（覆盖 2037）；实际切换 config.calendar_align_to_settle_day 跑口径 A/B 对比；独立回测复现 combo_final_stats.csv、逐年切片复现 yearly_stats.csv；grep 硬编码核查

> ⚠ 初审（首轮）本 milestone 的代码忠实性高（公式/参数/非空壳/无私货/无硬编码/无价格前视/复用不复制均通过），但发现两处**登记层**缺陷：核心时点对齐假设 AS10 被引用却未落入 assumptions.md 登记簿（变更日志称「新登 AS10」为不实）；coverage_matrix 四行未回填。初审 verdict=fail。详见 §七 / §八。**修复核验见下方「复核轮 1」，末行 verdict 已随复核更新。**

---

## 复核轮 1（修复核验 · 2026-07-08）

初审判 fail 的两处登记缺陷（CA-F01 / CA-F02）已由 coder 修复落盘，独立 grep/读盘核验如下：

| 缺陷 | 初审 severity | 修复核验（独立读盘） | 复核判定 |
| --- | --- | --- | --- |
| CA-F01 · AS10 未登记 | critical | assumptions.md:117 现有完整 **### [AS10]** 块：含假设内容（口径B is_thursday.shift(-1) / 备选口径A）、**防未来论证**（:119「shift(-1) 仅作用于确定性交易日历……非价格/收益前视」）、**口径A/B 核实证据**（:120「口径B 回撤-3.26%/波动3.75% 逐位对齐；口径A 区间69.31%/回撤-4.20% 明显偏离」，与我 §五 实测完全一致）、影响 milestone m7 / 影响指标 R11-R12 / 状态 assumed / 高亮 major-auto。**登记补齐、内容达标** | 已解决 |
| CA-F02 · 矩阵四行未回填 | major | coverage_matrix F5(:17)/F8(:20)/R11(:34)/R12(:35) 四行状态 pending→**done**、实现位置回填 combo_final.py 真实函数（build_calendar_signal,build_daily_upper_calendar_signal / build_final_reversal_position,assemble_signals / build_r11_table,run_final_strategy / build_r12_yearly_table）、最后更新 plan→**implement**，状态理由与 spec/AS10 一致。F6/F7/F8 行内字面 `\|chg_t\|` 已转义（主会话操作，语义零改动，已核对无内容改动）。**回填达标、与实现一致** | 已解决 |

**复核结论**：两处登记缺陷均已按初审建议修复且内容达标（AS10 块含口径A/B 证据与防未来论证、矩阵四行 done+真实实现位置）。代码忠实性首轮已确认（公式/参数/非空壳/无私货/无硬编码/无价格前视/复用不复制），本轮无新代码改动、无需重验。剩余在案项：CA-F03（盈亏比 per-day 口径继承底座，minor，归验证域，非 m7 修复对象）。**verdict 由 fail 改判 pass_with_issues。**

---

## 一、逐要素核对表（设计 §9.3 五维度 × F5/F8/R11/R12）

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| F5 周内信号<br>build_calendar_signal<br>build_daily_upper_calendar_signal<br>combo_final.py:127-180 | 一致：`(weekday==3)` = 周四=1 否则 0（:153）严格对应 spec p15 signal_calendar；`signed_signal(du+cal)`（:180）= sign(signal_daily_upper+signal_calendar) 逐字一致（§二） | 一致：calendar_weekday=3（config.py:65，周四 Mon=0→3） | 真实：完整函数体，非 pass/TODO | 一致：signal_calendar 与 signal_daily_upper_calendar 独立重算 vs CSV **0 不一致**（§二/§四） | **缺陷**：shift(-1) 口径B 属核心时点对齐假设，被引用为 AS10 却未登记（CA-F01） | 公式忠实；AS10 登记缺失 |
| F8 决策树<br>build_final_reversal_position<br>+ assemble_signals<br>combo_final.py:187-308 | 一致：`np.select([du_cal≠0,(du==0)&ra],[du_cal,rs],default=ss)`（:229）优先级严格对应 spec p15 三步；**step2 判据显式 (du==0) 而非照搬 F7 省略式，回 spec p15 核实正确**（§三） | 一致：upper=±5%/lower=±3%/reversal 区间[0.03%,0.5%]/lag=2/signal_lag=1 全反查 config | 真实：两函数均完整体，非空壳 | 一致：AS9 时点对齐独立推演无前视（§五）；三步分支 435/1340/262 独立复现覆盖 2037（§三） | 一致：AS3（>2% 由 step3 兜底）/AS4/AS9 已登记；F5 分支依赖 AS10（同 CA-F01） | 逻辑忠实；依赖未登记 AS10 |
| R11 回测<br>build_r11_table / run_final_strategy<br>combo_final.py:346-372,403-436 | 一致：多空原始决策树信号、仅做多 to_long_only（:327，AS2）；lag=signal_lag=1（:326）；B1 第二段主区间 2037 日 | 一致：区间/lag/cost=0/periods=252 反查 config | 真实：完整函数体，产 3 个 CSV | 一致：K1 无 R11 硬编码 + 独立回测逐位复现 + 内部自洽（§六） | 瑕疵：盈亏比 per-day 口径缺口（继承底座 CA-C01/CA-E01，CA-F03） | 忠实（盈亏比缺口继承底座） |
| R12 分年<br>build_r12_yearly_table<br>combo_final.py:379-396 | 一致：复用 combo_composite._yearly_stats 整段连续回测日收益自然年切片（非逐年重建仓）；列名「复合多空/复合仅做多/T」与 spec 表12 表头逐字一致 | 一致：periods=252 反查 config | 真实：完整函数体，产 yearly_stats.csv | 一致：独立逐年切片复现 2015/2020/2023（§六） | — | 忠实 |

---

## 二、F5 周内信号逐字对照代码（spec p15）+ 独立复验

spec F5 原文：`signal_calendar = 1 if day t is Thursday, 0 else`；`signal_daily_upper_calendar = sign(signal_daily_upper + signal_calendar)`。

| # | spec 口径 | 代码实现 | 定位 | 判定 |
| --- | --- | --- | --- | --- |
| signal_calendar | 周四=1，否则=0（取值 {0,1}） | `pd.Series((idx.weekday == config.calendar_weekday).astype(int))`，calendar_weekday=3=周四 | combo_final.py:153；config.py:65 | 一致（基础式） |
| — 时点对齐 | spec 未指定 signal_calendar 相对回测执行的坐标 | 口径B `is_thursday.shift(-1)`：决策日 d 标记「兑现日 d+1 是否周四」 | combo_final.py:154-156 | 属 AS10 解释选择（登记缺失，CA-F01） |
| signal_daily_upper_calendar | sign(signal_daily_upper + signal_calendar) | `signed_signal(du + cal)`（reindex 并集 fillna(0) 后相加取符号） | combo_final.py:177-180 | 一致 |

**独立复验**（不采信 coder 自述，自算比对 combo_final_signals.csv）：
- `signal_daily_upper_calendar` 手工 `np.sign(du+cal)` vs 代码列 → **0 不一致**；周四(cal=1)时 upper=0→+1、upper=-1→0、upper=+1→+1 三分支均成立。
- `signal_calendar` 口径B 手工 `is_thursday(全历史).shift(-1).reindex(主区间)` vs 代码列 → **0 不一致**。
- 计数：决策日自身为周四 = **412**（= 矩阵 D4「主区间 412 个周四」）；口径B signal_calendar==1（下一交易日为周四）= **413**（差 1 属区间边界效应，非缺陷）。

---

## 三、F8 step2 判据专项（回 spec p15 核实）+ 三步分支计数独立复现

**专项核实**：coder 声称 spec p15 F8 step2 判据是 `signal_daily_upper=0`（非 calendar 版），与 F7 不同。回 spec.md F8 原文（p15）逐字核对：

> 「1) 若 signal_daily_upper_calendar 被触发（≠0），按其择时……2) **若 signal_daily_upper=0** 且 |chg_t|∈[0.03%,0.5%]，按隔日反转……3) 若 signal_seesaw=1 看多；=−1 看空；否则平仓」

- spec F8 **step1** 触发信号 = `signal_daily_upper_calendar`（含周四效应）；**step2** 判据白纸黑字 = `signal_daily_upper=0`（原始 upper，**非** calendar 版）。coder 判读**正确**。
- 与 F7 对比（spec p13）：F7 step1 = signal_daily_upper≠0 ⟹「step1 不触发 ⟺ signal_daily_upper=0」，故 combo_composite step2 省略 (du==0) 合法；F8 step1 换成 signal_daily_upper_calendar≠0，「不触发 ⟺ du_cal=0」时 du **未必=0**（周四+日度大涨：du_cal=sign(-1+1)=0 而 du=-1），故 F8 **必须显式**判 (du==0)。

| # | spec p15 口径 | 代码实现（np.select 首命中） | 定位 | 判定 |
| --- | --- | --- | --- | --- |
| step1 | signal_daily_upper_calendar≠0 → 用之 | 第一条件 `du_cal != 0` 取 `du_cal` | combo_final.py:229 | 一致 |
| step2 | 否则 **signal_daily_upper=0** 且 \|chg_t\|∈[0.03%,0.5%] → 隔日反转 | 第二条件 `(du == 0) & ra` 取 `rs`——**显式 du==0**，非照搬 F7 | combo_final.py:229 | 一致（正确区分 F7/F8） |
| step3 | 否则 → signal_seesaw（=1多/=-1空/0平仓） | default=ss | combo_final.py:229 | 一致 |
| AS3 | \|chg_t\|>2% 延用跷跷板 | 非激活 → 落 default=signal_seesaw | combo_final.py:229 | 一致 |

**三步分支计数独立复现**（自建 F5/F8 信号重算，主区间 2037 日，不采信 coder 自述）：
- step1（du_cal≠0）：**435**
- step2（du==0 且 反转激活）：**1340**
- step3（default 复合兜底）：**262**
- 合计 435+1340+262 = **2037** ✓；三步两两重叠 = **0**（互斥）；手工决策树 vs combined_ls 列 **0 不一致**。

**F8/F7 结构差异实际影响量化**：「du_cal=0 且 反转激活 且 du≠0」样本 = **0**；「周四(cal=1) 且日度大涨(du=-1)→du_cal=0」样本 = **0**。即在本主区间，F8 的显式 (du==0) 与照搬 F7 省略式**数值等价（0 样本触发差异）**。结论：coder 的 step2 显式判据是 spec 忠实实现（读对了 p15），但其在 docstring / 变更日志中强调的「周四大涨落 step3」情形在本数据从未发生，实际为 no-op——判读正确、影响为零，不构成 issue，仅记实。

---

## 四、复用不复制核查 + 信号独立复验

- import 复用（combo_final.py:93-116）：combo_composite.{_YEARLY_ROWS,_yearly_stats,build_composite_seesaw_signal(F4)}、reversal.{_STAT_ROWS,_directional_win_rates,_stats_column,calculate_reversal_signal(AS4)}、strategy.{build_daily_signal,build_interval_seesaw_signal,signed_signal,to_long_only}、common 回测引擎——**均 import 调用非复制**。模块内无 chg_t 因子重算、无三分位重算、无复合信号重写、无细分胜率重写、无分年口径重写。
- 本模块**仅新写** F5（build_calendar_signal / build_daily_upper_calendar_signal）与 F8（build_final_reversal_position），属 m7 特有逻辑，合理。
- build_final_reversal_position **不是** build_composite_reversal_position 的复制：新增 signal_daily_upper 入参与 (du==0) 条件，反映 spec F8 与 F7 的真实差异（§三），非复制粘贴。
- 无「私货」：combo_final.py 全部公开函数（build_calendar_signal/build_daily_upper_calendar_signal→F5、build_final_reversal_position/assemble_signals→F8、build_final_backtest/build_r11_table/run_final_strategy→R11、build_r12_yearly_table→R12）均可映射回 m7 要素 ID，无未登记的私自替换逻辑块。

---

## 五、AS10 时点对齐专项 + 未来函数独立推演 + 口径 A/B 证据核实

**shift(-1) 是否前视——独立推演**：
- signal_calendar 仅依赖 `futures.index`（交易日日期及其 weekday），**不含任何价格/收益**。shift(-1) 令 signal_calendar[d]=is_thursday[d+1]=「下一交易日是否周四」。
- 链路：combined[d] 含 signal_calendar[d]，经 lag=1 → position[T]=combined[T-1] 含 signal_calendar[T-1]=is_thursday[T]=「T 是否周四」。即 T 日仓位在 T-1 收盘确定时，仅用到「T 是否周四」这一**确定性日历信息**（交易日排期提前固定，任意历史时点已知）与 ≤T-1 价格。
- 判定：shift(-1) 作用于确定性日历、非价格前移，**不构成未来函数**。coder 论证（日历确定性非价格）**成立**。（对照：combo_final.py 反转分支 shift(+1) 正向、日度/跷跷板分支自然坐标，全链路无价格类 shift(-N)。）

**口径 A/B 证据核实**（实际切换 config.calendar_align_to_settle_day 各跑一次，独立重算）：

| R11 多空指标 | 口径B(默认 True) | 口径A(False) | spec R11 |
| --- | --- | --- | --- |
| 区间收益 | 0.8638 | 0.6931 | 0.8522 |
| 年化收益 | 0.0801 | 0.0673 | 0.0765 |
| 最大回撤 | **-0.0326** | -0.0420 | **-0.0326** |
| 年化波动率 | **0.0375** | 0.0376 | **0.0375** |
| 卡玛比率 | 2.4590 | 1.6008 | 2.35 |
| 夏普比率 | 2.1326 | 1.7891 | 2.04 |

- 口径B 最大回撤 -3.26% / 年化波动率 3.75% 与 spec R11 **逐位对齐**；口径A 回撤劣化至 -4.20%、区间收益跌至 69.31%。coder 称「口径B 回撤/波动逐位对齐、口径A 明显劣化（区间69.31%/回撤-4.20%）」——**属实**（数值与自述完全一致）。
- 说明：口径B 的选择有充分经济语义（周内效应「周四偏多」应兑现于持仓日周四）且非前视，是可辩护的建模选择——但正因其对落脚点 R11 有材料性影响（86% vs 69%），**必须**在 assumptions.md 正式登记以供人工 revise，此即 CA-F01 的严重性所在。

---

## 六、K1 硬编码核查 + CSV 复现 + 内部自洽

**K1 硬编码**：grep src/test_v2 全域搜 R11 基准值（0.0765/7.65/85.22/2.04/2.35/-3.26/129.48/56.31 等）——命中仅在 combo_final.py 模块 docstring（:4）与 `_smoke_report` print 参照文本（:462-463,471），均标注「spec R11 基准 / spec R12 复合多空」供冒烟人工对照，**未注入 build_r11_table / build_r12_yearly_table 数据流**。反证：computed 区间收益 86.38% ≠ spec 85.22%、年化 8.01% ≠ 7.65%，若硬编码则应完全等于 spec——**数值分歧本身即证明结果系真实计算、非虚报**。

**独立回测复现**：自建 F5/F8 决策树信号 + signal_backtest，R11 多空区间收益 = **0.863758** = CSV 逐位一致；最大回撤 -0.03256 = CSV；夏普 2.132553 = CSV。R12 逐年切片 2015/2023 复合多空回撤 = -0.032560/-0.018052 = CSV（且逐位对齐 spec R12 -3.26%/-1.81%）。

**内部自洽**：区间收益 0.863758 → 年化 (1.863758)^(252/2037)−1 ≈ 0.0801 = CSV；卡玛 = 0.0801/0.03256 ≈ 2.459 = CSV；夏普 = 0.0801/0.037545 ≈ 2.133 = CSV。自洽，确系计算产出。

**量级归因（归验证域，非 m7 代码 issue）**：年化 8.01% vs spec 7.65%（偏高约 5%）、年择时次数 134.10 vs 129.48（偏高约 3.6%）——与 T 基准同步偏高（2.40% vs spec 2.28%）、根因底座 AS6 换月 / AS9 对齐，非 m7 引入；回撤/波动逐位对齐佐证持仓形状正确。

---

## 七、issue 清单

### CA-F01 · critical · 核心时点对齐假设 AS10 被全局引用却未落入 assumptions.md 登记簿（变更日志「新登 AS10」不实）　【复核轮1：已解决——assumptions.md:117 补齐 [AS10] 完整块】
- 定位: 缺失于 workspace/test_v2/assumptions.md（仅含 AS1–AS9，末行 115）；被引用于 src/test_v2/config.py:66-72、src/test_v2/combo_final.py:27-32/57-73/136-142、coverage_matrix.md 变更日志 :58（「**新登 AS10**」「**新增 AS10**」）
- 依据: assumptions.md 是 `/reproduce revise` 的唯一操作对象（其自述），人工 review 只能针对本文件条目发起定向重跑。AS10（周内信号 shift(-1) 口径B）是 **core 要素 F5/F8** 的时点对齐假设，对**报告落脚点 R11** 有材料性影响（口径B 区间收益 86.38% vs 口径A 69.31%，§五实测）。该假设仅存在于代码注释/config，**未进入登记簿**——属 core 要素未登记的简化（deviation_undeclared）；且变更日志明文声称已「新登/新增 AS10」，与登记簿实际缺失矛盾，构成对登记动作的不实声明。后果：quant-reporter 汇总「全量假设登记簿」将遗漏 AS10，最终报告读者无法获知 R11 落脚点依赖该口径选择；人工 revise 无法定向该假设。
- 处置建议（非 m7 代码修复）: 在 assumptions.md 补登 ### [AS10] 块（周内信号时点对齐口径B / 口径A、shift(-1) 确定性日历非前视论证、影响 milestone m7、影响指标 R11/R12、状态 assumed、高亮等级建议 major-auto，与 AS9 同级），并将 AS10 纳入登记簿计数。

### CA-F02 · major · coverage_matrix F5/F8/R11/R12 四行未回填（状态仍 pending / 实现位置空 / 最后更新 plan），与变更日志「done」claim 矛盾　【复核轮1：已解决——四行回填 done+真实实现位置+implement】
- 定位: workspace/test_v2/spec/coverage_matrix.md:17（F5）、:20（F8）、:34（R11）、:35（R12）四行 状态=pending、实现位置=空、最后更新=plan；变更日志 :58 却 claim「quant-coder 落地 m7 F5/F8……done、R11 表11……done」
- 依据: 同批 m6 done 行（F4:16/F7:19/R9:32/R10:33）均已回填（done / 实现位置=combo_final… / implement），独 m7 四行未同步——coder 仅追加变更日志、遗漏回填矩阵表体。实现代码真实存在于 combo_final.py（§一/§八，非空壳），故**非空壳虚报**；但状态机 tracking 破损：矩阵表体显示 m7 未完成，下游 check_gates / quant-reporter 读矩阵将误判 m7 状态。
- 处置建议: 将四行 状态 pending→done、实现位置填 combo_final.py 对应函数、最后更新 plan→implement，与变更日志 :58 对齐。

### CA-F03 · minor · 盈亏比按底座 per-day 口径，与 spec per-trade 存在系统性缺口（继承 CA-C01/CA-E01）
- 定位: output/test_v2/results/combo_final_stats.csv 盈亏比行（多空 1.115972 / 仅做多 1.110406）；口径实现 reversal.py:172（复用映射 metrics["profit_loss_ratio"]）→ common/timing_backtest.py:150-156
- 依据: 独立读数——多空盈亏比 1.116 vs spec R11 1.44（−22%），且 R7/R8/R9 同口径均 ~1.10-1.11 vs spec 1.31/1.33/1.36，系统性压向 1.0，疑与研报按笔（per-trade）口径不同。**属实现忠实**（m7 忠实复用既定底座引擎，非私自偏离），根因与 m4 CA-C01 同源；缺口需 verify/diagnose 复核底座盈亏比口径，非 m7 代码修复对象。

（说明：细分上涨/下跌胜率量级差异已由 AS7 声明口径存疑，归验证域；仅做多/T 列上涨胜率=1.0/下跌胜率=0.0 为 AS7 细分口径对单向持仓的退化产物，非 m7 引入。年化/夏普/年择时系统性略高与底座 AS6 换月同源，归验证域。）

---

## 八、空壳核验（G-CA-3）与矩阵回填状态

F5/F8/R11/R12 变更日志所指实现位置（combo_final.py）逐一打开核验：build_calendar_signal（:127-157）、build_daily_upper_calendar_signal（:160-180）、build_final_reversal_position（:187-230）、assemble_signals（:237-308）、build_final_backtest（:315-339）、build_r11_table（:346-372）、build_r12_yearly_table（:379-396）、run_final_strategy（:403-436）——均为完整函数体、有真实算子链（周四判定 / sign 合成 / np.select 三步决策树 / 前移对齐 / 三列回测 / 逐年切片 / CSV 落盘），且经 §三/§六 独立运行复现产出正确 R11/R12 数值。

实现代码真实性判定: 四要素实现均为真实代码、非 pass/TODO 空壳，本 milestone 不存在空壳（故不触发 G-CA-3 空壳判定）。

矩阵回填状态: coverage_matrix 四行（:17/:20/:34/:35）状态列**未回填**（仍 pending / 实现位置空 / plan），与代码真实完成状态不符——见 CA-F02（属状态机 tracking 未同步，非空壳）。因代码非空壳、无需按「空壳打回 in_progress」流程处理；正确处置是**前推回填**四行至 done（CA-F02 建议），而非回退。

---

## 九、已检查维度清单（code 五维度，无遗漏）

- [x] **公式一致**：F5 signal_calendar=(周四=1) 与 signal_daily_upper_calendar=sign(du+cal) 逐字命中；F8 np.select 三步优先级 step1>step2>step3 逐条对照 spec p15，**step2 显式 (du==0) 经回 spec 原文核实正确区分 F7**（§二/§三）；R12 复用自然年切片、列名与 spec 表12 一致
- [x] **参数一致**：calendar_weekday=3（周四）/ daily_upper=±5% / daily_lower=±3% / reversal 区间[0.03%,0.5%] / reversal_lag_days=2 / signal_lag=1 / main 区间 2015-03-24~2023-08-02 / cost=0 / periods=252 全反查 config，无魔法数字
- [x] **实现位置真实**：F5/F8/R11/R12 对应 8 函数均完整函数体、非空壳，且独立运行复现正确数值（§八）；但矩阵四行实现位置列未回填（CA-F02）
- [x] **代码反查**：AS10 shift(-1) 独立推演系确定性日历非价格前视、无价格类 shift(-N)（§五）；三步分支 435/1340/262 独立复现、互斥、覆盖 2037、与 CSV 逐位一致（§三）；F5 两信号独立重算 0 不一致（§二）；口径 A/B 实测证据核实属实（§五）；K1 无硬编码 + 独立回测复现 + 内部自洽（§六）；复用不复制、无私货（§四）
- [x] **简化声明**：AS1（±5%/±3%）/AS2（仅做多）/AS3（>2% 由 step3 兜底）/AS4（反转公式）/AS9（时点对齐）均已登记；**AS10（周内 shift(-1) 口径B，core 要素 F5/F8、材料性影响落脚点 R11）被引用却未登记 = CA-F01 critical**；盈亏比缺口继承底座（CA-F03）

---

> 复核轮 1 改判说明：初审 verdict=fail 由 CA-F01（critical，AS10 未登记）+ CA-F02（major，矩阵未回填）驱动；两者经复核已修复达标（见文首「复核轮 1」）。代码忠实性首轮已确认。剩 CA-F03（minor，盈亏比底座口径，归验证域）在案，故复核后改判如下末行。

verdict: pass_with_issues
