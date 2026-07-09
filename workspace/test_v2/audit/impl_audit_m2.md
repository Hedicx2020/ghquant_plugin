# 实现忠实性审计 · test_v2 · milestone m2（跷跷板与日度信号）

- 审计模式: code（实现忠实性，hard 逐条核对）
- 审计对象: coverage_matrix m2 全部 done 行（F1 / F2 / R1 / R2 / R3 / R4，共 6 行）
- 审计原则: 只读不改产物；三方数值独立重算，不采信 coder 自述与冒烟结论；与 coder 无交流
- 独立重算依据: output/test_v2/results/{strategy_perf_r1,daily_effect_stats,signals_m2}.csv、源码逐行反查

---

## 一、逐要素核对表（五维度 × 6 行）

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| F1 长短端跷跷板<br>strategy.py:90-137 | 一致：chg_T^N=close/close.shift(N)-1（:50）；扩窗 upper=q(2/3)/lower=q(1/3)（:78-79）；chg>upper→-1、chg<lower→+1、[lower,upper]→0（:81-83）；ls=sign(long+short)（:123）——对 spec F1 逐条命中 | 一致：long=120/short=20/q_lower=1/3/q_upper=2/3/base=2004-12-31 全部来自 config（config.py:37-41），对 spec N_l/N_s/上下1/3分位/基日一致 | 真实：完整函数体，含 _interval_return、_expanding_tercile_signal 两私有基元，非空壳 | 一致（含 CA-A01 核点，见 §二） | 一致：min_periods=1 早期不稳区间在主区间外，已注释（:74）；无未声明偏离 | 忠实 |
| F2 日度信号<br>strategy.py:144-164 | 一致：r≥thr→-1（大涨做空）、r≤-thr→+1（大跌做多）、否则 0（:162-163），对 spec F2 反向关系一致 | 一致：upper=0.05/lower=0.03（config.py:44-45，AS1）；T+1 执行由 signal_lag=1 承载（config.py:70） | 真实：完整函数体 | 一致：主区间触发 upper=23 天/lower=92 天（非退化，独立计数）；T 日生成经引擎 lag=1 于 T+1 执行，无前视 | 一致：±5%/±3% 由 AS1 声明 | 忠实 |
| R1 表 build_r1_table<br>main.py:102-117 | 一致：3 策略×(多空/仅做多)+T 基准，9 指标经 timing_metrics + directional_win_rates（main.py:64-99）；仅做多=clip(lower=0)（strategy.py:41，AS2） | 一致：lag=1/cost=0/periods=252 来自 config | 真实：完整函数体 | 一致：独立核对内部自洽（长短端多空年化 2.944%↔夏普 0.950=年化/波动 0.02944/0.03098）；K1：R1 基准值仅现于 print（main.py:233），未注入 CSV | 一致：AS2；盈亏比沿用 B1 按日口径（长短端 1.11 vs spec 1.23，B1 根因、跨里程碑，归 verify/m1） | 忠实 |
| R2/R3/R4 日度效应<br>strategy.py:201-281 | 一致：胜率=sign(r)·sign(f)<0 占比（:275）；赔率=sum 总额比 up/dn、pos 组取倒数 dn/up（:245-253）；均值=mean(f)（:277）——对 AS8 口径逐条命中 | 一致：15 档阈值来自 config.daily_effect_thresholds（config.py:51-54），对 spec 表头 0%~5% 15 档一致；f=future_close_return.shift(-1)（main.py:127） | 真实：完整函数体 | 一致：独立重算逐位命中 spec（见 §三） | 瑕疵：口径 AS8 已声明，但代码注释误引 AS6（CA-B01） | 忠实（注释交叉引用瑕疵） |

---

## 二、CA-A01 核点：扩窗分位是否消费全历史 hs300（非截断面板）

结论：满足。三段独立反查：

1. 数据源为全历史：`main.run_m2` 以 `hs300_full["close"]` 喂入 F1（main.py:251,255），`hs300_full = data_prep.load_hs300()`（main.py:251）；load_hs300（data_prep.py:80-93）对 index_code=000300 全表加载、**无区间截断**。而被截断到主区间的 `panel["hs300_close"]`（build_main_panel，data_prep.py:190-196 截 [2015-03-24,2023-08-02]）**未**被 F1 消费。
2. 扩窗自基日起：`_expanding_tercile_signal` 先 `chg.loc[chg.index >= base_date]`（strategy.py:77，base=2004-12-31），再 `expanding(min_periods=1).quantile()`（:78-79）——分位样本自基日累积，非截面板。
3. 输出佐证：signals_m2.csv 首行 2015-03-24 的 chg_long=63.83% 被判 signal_long=-1（高于上轨）。若分位仅取主区间（自 2015 该峰值起），首个样本不可能"高于上轨"；判为 -1 只可能因分位样本含 2004 以来全历史——反证全历史扩窗成立。

判据：CA-A01 通过，未来函数防护有效（信号 T 日生成、引擎 lag=1 于 T+1 执行）。

---

## 三、R2/R3/R4 独立重算（AS8 口径核对，逐格对照 spec）

以 daily_effect_stats.csv 独立重算关键格，对照 spec R2/R3/R4：

| 项 | 档/组 | 独立重算 | spec | 判定 |
| --- | --- | --- | --- | --- |
| R2 胜率 | abs 0% | 50.25% | 50.12% | 近似（0.13pp 数据差异） |
| R2 胜率 | abs 5% | 56.52% | 56.52% | 逐位命中 |
| R2 胜率 | pos 5% | 83.33% | 83.33% | 逐位命中 |
| R2 胜率 | neg 5% | 47.06% | 47.06% | 逐位命中 |
| R3 赔率 | abs 0% | 1.116 | 1.11 | 命中 |
| R3 赔率 | pos 5% | 28.33 | 28.33 | 逐位命中（极端值） |
| R4 均值 | pos 5% | -0.16% | -0.16% | 逐位命中 |
| R4 均值 | neg 5% | +0.08% | +0.08% | 逐位命中 |

判据：
- 赔率取 sum 总额比（up/dn）且 pos 组取倒数（dn/up）——pos5% 极端值 28.33 逐位命中，只有 sum 口径 + 分组方向正确才可能命中，AS8 登记的"赔率=sum 总额比 + 分组方向"与实现（strategy.py:245-253）一致。
- 15 档阈值源自 config，无魔法数字。
- 高档位逐位命中、0% 档 0.1pp 级偏差属数据天数差异（归 verify 逐格），机制忠实。

---

## 四、空壳核验（G-CA-3）

m2 六行实现位置逐一打开核验，均为具备完整函数体的真实实现（见 §一"实现位置真实"列）：F1/F2 在 strategy.py 有完整算子链、R1 在 main.py:102-117、R2/R3/R4 在 strategy.py:201-281。无 pass / TODO / 空返回 占位。本里程碑不存在空壳，无需在变更日志记状态回退。

补充（非空壳、非虚报）：strategy.py:288-291 的 `build_reversal_signal` 为 raise NotImplementedError 占位，但 F3 实际实现在 reversal.py，无任何矩阵行指向此占位（见 CA-B02），属残留死代码，不构成 F3 虚报。

---

## 五、issue 清单

### CA-B01 · minor · AS 交叉引用错误（代码反查维度）
- 定位: src/test_v2/strategy.py:209、src/test_v2/config.py:50
- 依据: 两处注释均写"口径重建见 AS6"，但 R2/R3/R4 日度效应统计口径实际登记于 **AS8**；AS6 为"chg_t 换月跳空口径"（属 m4 反转因子），与日度效应无关。从代码反查口径来源会被误导至错误假设条目。计算不受影响（AS8 内容与实现逐条一致），故 minor。

### CA-B02 · minor · 残留死代码占位
- 定位: src/test_v2/strategy.py:288-291
- 依据: `build_reversal_signal` 为 raise NotImplementedError 空壳；F3 已在 reversal.py 独立实现（矩阵 F3 行指向 reversal.py），无矩阵行指向此占位。故非虚报（F3 有真实实现），但死代码残留于 m2 独占文件，宜清理以免后续维护误引。

（说明：R1/R2 盈亏比按 B1 common 按日口径与 spec 存在温和缺口，根因在 B1/m1，已归 m1 审计与 verify，本里程碑不另记 issue，仅于 §一 R1 行备注。）

---

## 六、已检查维度清单（code 五维度，无遗漏）

- [x] 公式一致：F1（区间涨跌/扩窗三分位/看多看空/长短合成）、F2（双阈值反向）、R1（9 指标口径）、R2/R3/R4（胜率/赔率/均值/天数比例）逐条对 spec/AS8
- [x] 参数一致：120/20、1/3·2/3、base 2004-12-31、±5%/±3%、15 档阈值、lag=1、cost=0、periods=252 全部反查 config，无魔法数字
- [x] 实现位置真实：6 行全部为完整函数体（含私有基元），无空壳（§四）
- [x] 代码反查：CA-A01 全历史分位三段反查（§二）；F2 触发计数非退化；K1 无 R1 基准值注入 CSV（仅 print）；R2/R3/R4 独立重算逐格命中（§三）
- [x] 简化声明：AS1（±5%/±3%）、AS2（仅做多 clip）、AS8（R2/R3/R4 口径）均已登记；瑕疵为注释误引 AS6（CA-B01）

---

verdict: pass_with_issues
