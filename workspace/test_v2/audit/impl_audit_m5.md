# 实现忠实性审计 · test_v2 · milestone m5（长短端跷跷板 + 隔日反转改进）

- 审计模式: code（实现忠实性，hard 逐条核对）
- 审计对象: coverage_matrix m5 done 行——F6（长短端+隔日反转策略，实现位置 combo_ls.py:build_combo_ls_signal）、R8（表8 业绩，实现位置 combo_ls.py:run_combo_ls）
- 审计原则: 只读不改产物；数值一律独立重算，不采信 coder 自述与冒烟结论；与 coder 无交流
- 独立重算依据: 源码逐行反查（combo_ls.py / reversal.py / strategy.py / config.py / common/timing_backtest.py）；独立重建 F6 组合信号与 m4 隔日反转 position 逐日比对；独立回测复现 combo_ls_stats.csv；内部自洽核验

---

## 一、逐要素核对表（§9.3 五维度 × F6/R8 两函数）

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| F6 分段决策<br>build_combo_ls_signal<br>combo_ls.py:78-148 | 一致：`.where(rev_active, 反转, 跷跷板)` 二分（:129）逐条命中 spec F6 三段规则（见 §二） | 一致：reversal_lag_days=2/min=0.0003/max=0.005/seesaw_switch_upper=0.02/signal_lag=1 全反查 config（config.py:58-62,70），无魔法数字 | 真实：完整函数体（71 行），非 pass/TODO 空壳 | 一致：AS9 时点对齐独立推演，反转分支 position[T] 与 m4 逐日 0 不一致（§三）；无负向 shift、无前视（§三） | 一致：AS9（时点对齐）、AS3（>2% 延用跷跷板）、AS4（反转公式）均登记 | 忠实 |
| R8 回测<br>run_combo_ls<br>combo_ls.py:155-215 | 一致：多空用原始组合信号、仅做多 to_long_only（:182，AS2）；lag=signal_lag=1（:185-186）；B1 第二段区间 [2015-03-24,2023-08-02] 截取（:176-177，config.py:24-25） | 一致：区间/lag/cost=0/periods=252 全反查 config | 真实：完整函数体，产 combo_ls_stats.csv（§六） | 一致：K1 无 R8 数值硬编码进数据流（§五）；独立回测逐位复现（§五） | 瑕疵：盈亏比按 B1 per-day 口径，与 spec per-trade 缺口（继承 CA-C01，CA-D01） | 忠实（盈亏比缺口继承自 B1，非 m5 私自偏离） |

---

## 二、F6 分段规则逐条对照代码（spec p12 + AS3）

spec F6：`if |chg_t|∈[0.03%,0.5%] → F3 隔日反转信号; elif |chg_t|∈[0,0.03%)∪(0.5%,2%] → F1 长短端跷跷板信号`；AS3：`|chg_t|>2% → 延用跷跷板`。

| # | spec/AS3 口径 | 代码实现 | 定位 | 判定 |
| --- | --- | --- | --- | --- |
| 1 | 激活区间 \|chg_t\|∈[0.03%,0.5%] 走隔日反转 | `combo_signal = rev_signal_form.where(rev_active_form, seesaw_ls_form)`——active 为真取反转信号 | combo_ls.py:129；active 判定复用 reversal.py:108（闭区间双含边界） | 一致 |
| 2 | [0,0.03%)∪(0.5%,2%] 走长短端跷跷板 | `.where(active, ...)` 的 else 分支 → seesaw_ls_form（非激活即跷跷板） | combo_ls.py:129 | 一致 |
| 3 | AS3：\|chg_t\|>2% 延用跷跷板（非平仓） | >2% 属「非激活」子集，天然落 else=跷跷板；二分不引入第三种处置 | combo_ls.py:129；边界标签 seesaw_switch_upper=2% 仅审计标注（:135） | 一致（AS3 由二分天然承载） |
| 4 | 隔日反转信号方向（AS4）chg_t>0 空/chg_t<0 多 | 复用 reversal.calculate_reversal_signal 的 `-np.sign(chg_t).where(active,0)` | reversal.py:111（import combo_ls.py:60-65） | 一致 |
| 5 | 跷跷板信号 = F1 sign(长+短) | 复用 strategy.build_interval_seesaw_signal 的 signal_ls | strategy.py:123（import combo_ls.py:66） | 一致 |
| 6 | 仅做多 = 剔除做空腿（AS2） | `lo_signal = to_long_only(ls_signal)` | combo_ls.py:182；strategy.py:35-41 | 一致 |

判据：F6 三段规则全部命中。**独立重建分支占比**（不采信 docstring，自算 chg[T-2] 落段，主区间 2037 交易日）：reversal 1705（83.70%）/ seesaw_mid 332（16.30%）/ seesaw_extreme_AS3 **0**（0.00%）——与 AS9 核实依据「reversal 83.70%/seesaw_mid 16.30%/AS3 极端档 0 天」逐位吻合；主区间内 \|chg[T-2]\|>2% 从未发生，AS3 实际不触发，二分实现对 R8 无量级影响。

---

## 三、AS9 时点对齐专项 + 未来函数独立推演（timing 类最敏感处）

**关键声明复核**：coder 称「反转分支前移 reversal_lag_days−signal_lag，统一 lag=1，使 position[T] 恰等于 m4 语义、与 R7 逐日等价」。**独立推演 + 抽样验证**：

- 反转分支：`rev_extra_shift = reversal_lag_days − signal_lag = 2−1 = 1`（combo_ls.py:118，反查 config）。`rev_signal_form[d'] = signal[d'−1]`（:119）。组合信号经回测 `position[T] = combo[T−1]`（lag=signal_lag=1，:185）。代入激活分支：`position[T] = rev_signal_form[T−1] = signal[T−2] = 反转方向(chg[T−2])`。总滞后 = 额外移位 1 + 回测 lag 1 = 2 = reversal_lag_days，与 m4 reversal.py 的 T−2→T 兑现完全等价。
- 跷跷板分支：`seesaw_ls_form[d'] = signal_ls[d']`（不移位，:125），`position[T] = signal_ls[T−1]`——即 T−1 收盘沪深300信号 T 日执行，与 R1（m2）lag=1 口径一致。
- 分段判据同坐标：`rev_active_form[d'] = active[d'−1]`（:120），d'=T−1 时 = active[T−2]，即以 chg[T−2] 判段，与反转信号取值 signal[T−2] 同源同坐标，一致无错位。

**独立抽样验证（python）**：分别独立重建 m4 隔日反转 position（rev.signal.shift(reversal_lag_days=2)）与 m5 组合 reversal 分支 position（自建 where + shift(signal_lag)），在主区间 reversal 激活日逐日比对——**1704 个激活日，position 不一致日数 = 0**（抽样 2015-03-25~03-31 五日 m4/m5 均 +1.0）。R7 逐日等价声明**成立**。

**未来函数核查**：combo_ls.py 全部 shift 均为正向（:119-121 shift(rev_extra_shift=1)），无 shift(-N)；reversal.py 因子为 pct_change（相邻结算价比值，非移位）。position[T] 仅依赖 ≤T−1 沪深300信号与 ≤T−2 结算价因子，在 T−1 收盘即完全确定，T 日兑现——**无前视/未来函数**。

---

## 四、复用不复制核查（DRY / 防复制粘贴）

- 反转信号：`from src.test_v2.reversal import calculate_reversal_signal`（combo_ls.py:60-65），信号由 `rev = calculate_reversal_signal(...)`（:109）import 调用，**非复制**。
- 跷跷板信号：`from src.test_v2.strategy import build_interval_seesaw_signal, to_long_only`（:66），`seesaw = build_interval_seesaw_signal(...)`（:111），**非复制**。
- R 表组装口径：`_STAT_ROWS / _directional_win_rates / _stats_column` 直接 import 复用 reversal 模块（:60-65），保 R8 与 R7 逐格指标定义一致。
- combo_ls.py 内**无** chg_t 因子重算、**无** 三分位分位重算、**无** 细分胜率重写——仅做「组合 + 分段 where + 回测编排」。判为忠实复用，无「私货」。

---

## 五、K1 抽查：R8 基准数值硬编码核查 + 内部自洽

grep combo_ls.py 全文搜 R8 基准值（59.93 / 5.77 / 3.99 / 3.26 / 1.55 / 1.45 / 54.69 / 129.96 / 38.71 等）：

- 命中仅 3 处（combo_ls.py:247-249），**全部位于 `_smoke_report` 的 print 语句**，为「spec R8 基准 →」参照文本，供冒烟自检人工对照，**未注入 run_combo_ls 数据流**。R8 对照表由 `timing_metrics` 计算产出（:188-194）。
- combo_ls_stats.csv 全部数值为全精度浮点（如区间收益 0.618176、夏普 1.653776），非硬编码圆整值。
- **独立回测复现**：自建组合信号 + signal_backtest 回测，多空区间收益 = 0.618176，与 CSV **逐位一致**。
- **内部自洽**：区间收益 0.618176 → 年化 (1.618176)^(252/2037)−1 = 0.061351 = CSV；夏普 = 0.061351/0.037097 = 1.6538 = CSV 1.653776；卡玛 = 0.061351/0.032557 = 1.8844 = CSV 1.884393。三处自洽，确系计算产出。

判据：K1 通过，无 R8 数值硬编码虚报。

---

## 六、空壳核验（G-CA-3）

F6/R8 实现位置逐一打开核验：`build_combo_ls_signal`（combo_ls.py:78-148）与 `run_combo_ls`（combo_ls.py:155-215）均为完整函数体、有真实算子链（分段 where / shift 对齐 / 三列回测 / CSV 落盘），**非** pass / TODO / 空返回 占位。

实现位置真实性判定: 非空壳（两函数均真实）。m5 done 行不存在空壳，无需在 coverage_matrix 变更日志记状态回退（未改动矩阵）。

---

## 七、issue 清单

### CA-D01 · minor · 盈亏比按 B1 per-day 口径，与 spec per-trade 存在系统性缺口（继承 CA-C01）
- 定位: output/test_v2/results/combo_ls_stats.csv 盈亏比行；口径实现 reversal.py:172（复用映射 metrics["profit_loss_ratio"]）→ common/timing_backtest.py:150-156
- 依据: 独立读数——多空盈亏比 1.085278 / 仅做多 1.088647 vs R8 spec 1.33 / 1.47（−18% / −26%）。盈亏比忠实沿用 B1 common 引擎按日口径 mean(+日收益)/mean(|−日收益|)，对多日持仓策略系统性压向 1.0，疑与研报按笔（per-trade）口径不同。**属实现忠实**（m5 忠实复用既定 B1/reversal 引擎，非私自偏离），根因与 m4 CA-C01 同源；缺口需 verify/diagnose 复核 B1 盈亏比口径，非 m5 代码修复对象。

（说明：无 core 要素未声明偏离、无虚报、无空壳、无未来函数、无硬编码；上涨/下跌胜率量级差异已由 AS7 声明其口径存疑，归验证域，不另立 issue。年化系统性偏高约 6% 与 T 基准同步偏高 2.40% vs 2.28%，源自 m1/m4 底座/数据，非 m5 组合口径引入，归验证域。）

---

## 八、已检查维度清单（code 五维度，无遗漏）

- [x] 公式一致：F6 三段规则 6 条逐条对照代码（§二）——激活走反转 / 非激活走跷跷板 / AS3 二分承载 / 反转方向 AS4 / 跷跷板 F1 sign(长+短) / 仅做多 AS2，全部命中；独立重建分支占比 83.70%/16.30%/0 逐位吻合 AS9
- [x] 参数一致：reversal_lag_days=2 / min=0.0003 / max=0.005 / seesaw_switch_upper=0.02 / signal_lag=1 / main_start=2015-03-24 / cost=0 / periods=252 全反查 config，无魔法数字
- [x] 实现位置真实：build_combo_ls_signal 与 run_combo_ls 均完整函数体，非空壳（§六）
- [x] 代码反查：AS9 时点对齐独立推演 + python 抽样验证 R7 逐日等价 0 不一致（§三）；无负向 shift、无未来函数（§三）；复用 reversal/strategy 信号不复制、无私货（§四）；K1 无 R8 硬编码 + 独立回测逐位复现 + 内部自洽（§五）
- [x] 简化声明：AS9（时点对齐）、AS3（>2% 延用跷跷板）、AS4（反转公式）、AS2（仅做多）均已登记；盈亏比缺口归 B1/CA-C01（CA-D01）

---

verdict: pass_with_issues
