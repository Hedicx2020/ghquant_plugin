# 实现忠实性审计 · test_v2 · milestone m6（复合跷跷板 + 隔日反转）

- 审计模式: code（实现忠实性，hard 逐条核对）
- 审计对象: coverage_matrix m6 done 行——F4（复合信号 seesaw，build_composite_seesaw_signal）、F7（三步决策树，build_composite_reversal_position + assemble_signals）、R9（表9 业绩，build_r9_table + run_composite_strategy）、R10（表10 分年业绩，build_r10_yearly_table）
- 审计原则: 只读不改产物；数值一律独立重算，不采信 coder 自述与冒烟结论；与 coder 无交流
- 独立重算依据: 源码逐行反查（combo_composite.py / reversal.py / strategy.py / config.py / common）；独立重建 F4/F7 决策树信号与 CSV 逐日比对；独立重算决策树三步分支计数与 R2 交叉验证；独立回测复现 combo_composite_stats.csv、逐年切片复现 yearly_stats.csv；内部自洽核验

---

## 一、逐要素核对表（§9.3 五维度 × F4/F7/R9/R10 四要素）

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| F4 复合信号<br>build_composite_seesaw_signal<br>combo_composite.py:106-125 | 一致：`signed_signal(lower + ls)`（:125）= sign(signal_daily_lower + signal_l_s)，与 spec p13 F4 逐字一致 | 一致：daily_lower=±3% 由 assemble 传入（:190，config.py:45） | 真实：完整函数体，非空壳 | 一致：独立重算 vs CSV signal_seesaw 0 不一致（§四） | 一致：AS1（±3%）已登记 | 忠实 |
| F7 决策树<br>build_composite_reversal_position<br>+ assemble_signals<br>combo_composite.py:128-158,165-218 | 一致：`np.select([du≠0, ra],[du, rs], default=ss)`（:157）优先级严格对应 spec p13 三步（见 §二） | 一致：upper=±5%/reversal_lag_days=2/signal_lag=1 全反查 config | 真实：两函数均完整体，非空壳 | 一致：AS9 时点对齐独立推演无前视（§三）；分支计数独立复现（§二） | 一致：AS3（>2% 由 step3 兜底）、AS4、AS9 登记 | 忠实 |
| R9 回测<br>build_r9_table / run_composite_strategy<br>combo_composite.py:256-278,327-360 | 一致：多空原始决策树信号、仅做多 to_long_only（:237，AS2）；lag=signal_lag=1（:236）；B1 第二段主区间 2037 日（build_main_panel） | 一致：区间/lag/cost=0/periods=252 反查 config | 真实：完整函数体，产 3 个 CSV | 一致：K1 无 R9 硬编码 + 独立回测逐位复现 + 内部自洽（§五） | 瑕疵：盈亏比 per-day 口径缺口（继承 CA-C01，CA-E01） | 忠实（盈亏比缺口继承 B1） |
| R10 分年<br>build_r10_yearly_table / _yearly_stats<br>combo_composite.py:285-320 | 一致：整段连续回测日收益按自然年 groupby 切片（:294），区间收益/最大回撤/年化波动率逐年算，非逐年重建仓 | 一致：periods=252 反查 config | 真实：完整函数体，产 yearly_stats.csv | 一致：独立逐年切片复现 2015/2020/2023（§五） | — | 忠实 |

---

## 二、F7 三步决策树逐条对照代码（spec p13）+ 分支计数独立复现

spec F7：`step1 若 signal_daily_upper≠0 → 用之; step2 否则 若 |chg_t|∈[0.03%,0.5%] → 隔日反转(chg_t>0空/chg_t<0多); step3 否则 → signal_seesaw(=1多/=-1空/否则平仓)`。

| # | spec 口径 | 代码实现（np.select 取首个命中条件） | 定位 | 判定 |
| --- | --- | --- | --- | --- |
| step1 | signal_daily_upper±5%≠0 → 用之（最高优先级） | `np.select([du != 0, ...], [du, ...], ...)`——第一条件 du≠0 取 du | combo_composite.py:157；du=signal_daily_upper（:152,189） | 一致 |
| step2 | 否则 \|chg_t\|∈[0.03%,0.5%] → 隔日反转 | 第二条件 ra（reversal_active）取 rs（reversal_signal）；np.select 仅在 du==0 时评估第二条件 | combo_composite.py:157；ra/rs 前移决策日（:153-154,198-199） | 一致 |
| step3 | 否则 → signal_seesaw（=1多/=-1空/0平仓） | default=ss（signal_seesaw，本身 -1/0/+1，取值即看多/看空/平仓） | combo_composite.py:157；ss=signal_seesaw（:155,193） | 一致 |
| AS3 | \|chg_t\|>2% 延用跷跷板 | >2% 属「非激活」，du==0 时落 default=signal_seesaw（复合跷跷板），无需显式判断 | combo_composite.py:157（step3 默认分支承载） | 一致 |

判据：F7 优先级 step1>step2>step3 与 np.select 首命中语义严格对应，方向映射逐字一致。

**分支计数独立复现**（不采信 coder「step1 23/step2 82.72%/step3 16.15%」自述，自建 F4/F7 信号重算，主区间 2037 日）：
- step1（du≠0）：**23**（1.13%）
- step2（du==0 且 反转激活）：**1685**（82.72%）
- step3（du==0 且 非激活兜底）：**329**（16.15%）
- 合计 23+1685+329 = 2037 ✓；且与 combo_composite_signals.csv 反查（signal_daily_upper≠0 / reversal_active_decide）**逐位一致**。coder 分支计数自述**成立**。

---

## 三、AS9 时点对齐专项 + 未来函数独立推演

**独立推演三来源信号在决策日 d 坐标的对齐**（回测统一 lag=signal_lag=1，position[T]=combined[T−1]）：
- signal_daily_upper（F2）：`du[d]` 基于 hs300_return[d]，position[T]=du[T−1]——股市 T−1 大涨/跌 → 国债期货 T 反向，符合 spec「下一交易日」。**独立核验方向**：大涨日(≥+5%)信号唯一值 = −1（做空）、大跌日(≤−5%) = +1（做多），与 F2 一致。
- 隔日反转（AS4）：`shift_to_decide = reversal_lag_days − signal_lag = 1`（combo_composite.py:197，反查 config），`rev_signal_decide[d]=signal[d−1]`（:198），position[T]=rev_signal_decide[T−1]=signal[T−2]=反转方向(chg[T−2])——与 m4/R7 逐日一致（该等价已在 m5 审计中以 1704 激活日 0 不一致独立坐实，m6 沿用同一前移量）。
- 复合信号 signal_seesaw（F4）：`ss[d]=sign(dl[d]+ls[d])`，均决策日坐标，position[T]=ss[T−1]。

**未来函数核查**：combo_composite.py 全部 shift 均为正向（:198-199 shift(shift_to_decide=1)），无 shift(-N)。决策日 d 三判据（d 日沪深300单日涨跌、d 日复合跷跷板、chg[d−1]=settle_{d−1}/settle_{d−2}−1）均在 d 日收盘完全已知，combined[d] 经 lag=1 于 d+1 执行——**无前视/未来函数**。（注：strategy.py:227 与 main.py:127 的 shift(-1) 属 R2/R3/R4 日度效应统计，非 m6 交易信号路径。）

---

## 四、复用不复制核查 + F4/F7 信号独立复验

- import 复用（combo_composite.py:70-92）：strategy.{build_daily_signal, build_interval_seesaw_signal, signed_signal, to_long_only} 与 reversal.{calculate_reversal_signal, _STAT_ROWS, _directional_win_rates, _stats_column} + common 回测引擎，**均 import 调用非复制**。模块内无 chg_t 因子重算、无三分位重算、无细分胜率重写。
- **独立复验**：自建 F4（sign(dl+ls)）与 F7（np.select 决策树）信号，与 combo_composite_signals.csv 的 signal_seesaw、combined_ls 逐日比对——**0 不一致**。coder「决策树分支取值一致性校验全通过」自述**成立**。
- 无「私货」：所有决策日信号均可映射回 F2/F1/F4/F3 要素 ID，无未登记的私自替换逻辑块。
- 微观察（非 issue）：reversal 模块被拆成两条 import 语句（:81-85 与 :92），功能无碍，仅风格冗余。

---

## 五、K1 抽查：R9/R10 基准数值硬编码核查 + 内部自洽 + 交叉验证

**K1 硬编码**：grep combo_composite.py 全文搜 R9/R10 基准值（67.99 / 6.40 / 4.40 / 3.24 / 1.71 / 1.58 / 54.93 / 128.88 / 43.38 / 8.58 / 10.42 / 5.13 等）——命中仅在 `_smoke_report` 的 print 参照文本（:377-390），标注「spec R9 基准 / spec R10 复合多空」供冒烟人工对照，**未注入 build_r9_table / build_r10_yearly_table 数据流**。CSV 全部为全精度浮点（区间收益 0.693822 等），非圆整值。

**独立回测复现**：自建决策树信号 + signal_backtest，R9 多空区间收益 = 0.693822 = CSV 逐位一致；逐年切片 2015/2020/2023 复合多空区间收益 = 0.083985/0.105120/0.001382 ≈ CSV 0.083989/0.105117/0.001378（差 <5e-6，%.6f 舍入）。

**内部自洽**：区间收益 0.693822 → 年化 (1.693822)^(252/2037)−1 = 0.067366 = CSV；夏普 = 0.067366/0.037392 = 1.8016 = CSV 1.801628；卡玛 = 0.067366/0.032369 = 2.0812 = CSV 2.081215。自洽，确系计算产出。

**交叉验证复核（独立重算，不采信 coder 声明）**：coder 称「step1 触发 23 天(1.13%) == R2 表 5% 档天数比例」。独立以 strategy.daily_seesaw_effect_stats 重算 R2 表 abs 5% 档：桶内天数 n=**23**、day_ratio=**1.1297%**（≈1.13% = spec R2 abs 5%档）；step1 触发（\|hs300_return\|≥5%，主面板 2037 日）= **23**，与 R2 5% 桶 **差 = 0**。交叉验证**成立**——±5% 高阈值恰触发 R2 表 5% 档所计的 23 天，且复现 R2 频率(1.13%)与研报 spec 一致。

---

## 六、空壳核验（G-CA-3）

F4/F7/R9/R10 实现位置逐一打开核验：build_composite_seesaw_signal（:106-125）、build_composite_reversal_position（:128-158）、assemble_signals（:165-218）、build_r9_table（:256-278）、build_r10_yearly_table（:304-320）、run_composite_strategy（:327-360）均为完整函数体、有真实算子链（sign 合成 / np.select 决策树 / 前移对齐 / 三列回测 / 逐年切片 / CSV 落盘），**非** pass / TODO / 空返回 占位。

实现位置真实性判定: 非空壳（六函数均真实）。m6 done 行不存在空壳，无需在 coverage_matrix 变更日志记状态回退（未改动矩阵）。

---

## 七、issue 清单

### CA-E01 · minor · 盈亏比按 B1 per-day 口径，与 spec per-trade 存在系统性缺口（继承 CA-C01）
- 定位: output/test_v2/results/combo_composite_stats.csv 盈亏比行；口径实现 reversal.py:172（复用映射 metrics["profit_loss_ratio"]）→ common/timing_backtest.py:150-156
- 依据: 独立读数——多空盈亏比 1.103337 / 仅做多 1.112135 vs R9 spec 1.36 / 1.52（−19% / −27%）。忠实沿用 B1 common 引擎按日口径，对多日持仓策略系统性压向 1.0，疑与研报按笔（per-trade）口径不同。**属实现忠实**（m6 忠实复用既定引擎，非私自偏离），根因与 m4 CA-C01 同源；缺口需 verify/diagnose 复核 B1 盈亏比口径，非 m6 代码修复对象。

（说明：无 core 要素未声明偏离、无虚报、无空壳、无未来函数、无硬编码；F4/F7/R9/R10 公式与决策树优先级逐条命中、分支计数与交叉验证独立复现全部成立。上涨/下跌胜率量级差异已由 AS7 声明口径存疑，归验证域。年化/夏普系统性略高约 5% 与 R7 AS6 换月同源、T 基准 2.40% vs 2.28% 源自底座/数据，均非 m6 组合口径引入，归验证域。）

---

## 八、已检查维度清单（code 五维度，无遗漏）

- [x] 公式一致：F4 = sign(daily_lower+ls) 逐字命中；F7 np.select 三步优先级 step1>step2>step3 逐条对照 spec p13（含 AS3 由 step3 兜底）；R10 自然年 groupby 切片非逐年重建仓；F2 方向独立核验（大涨→−1/大跌→+1）
- [x] 参数一致：daily_upper=±5% / daily_lower=±3% / reversal_lag_days=2 / signal_lag=1 / main 区间 2015-03-24~2023-08-02 / cost=0 / periods=252 全反查 config，无魔法数字
- [x] 实现位置真实：F4/F7/R9/R10 六函数均完整函数体，非空壳（§六）
- [x] 代码反查：AS9 时点对齐独立推演无前视 + 无负向 shift（§三）；决策树分支计数 23/1685/329 独立复现且 CSV 逐位一致（§二）；F4/F7 信号独立重算 0 不一致（§四）；step1=23==R2 5%档 23 交叉验证独立成立（§五）；K1 无硬编码 + 独立回测复现 + 内部自洽（§五）
- [x] 简化声明：AS1（±5%/±3%）、AS3（>2% 由 step3 兜底）、AS4（反转公式）、AS9（时点对齐）、AS2（仅做多）均已登记；盈亏比缺口归 B1/CA-C01（CA-E01）

---

verdict: pass_with_issues
