# 实现忠实性审计 · test_v2 · milestone m8（稳健性 / 成交价敏感性 / 费用 / 附录）

- 审计模式: code（实现忠实性，hard 逐条核对）
- 审计对象: m8 六要素——B2（成交价格与交易费用设置）、R13（表13 成交价影响，降级）、R14（表14 月度业绩附录，100 月）、SA1（分年子样本稳健性）、SA2（成交价敏感性 vwap，降级）、SA3（交易费用影响）
- 审计原则: 只读不改产物；数值一律独立重算，不采信 coder 自述与冒烟结论；与 coder 无交流
- 独立重算依据: 源码逐行反查（robustness.py / combo_final.py / combo_composite.py / config.py / common）；独立抽算 R14 三个月（从 F8 日收益自写月切片口径，不调用 _monthly_stats）与 CSV 逐位对照；独立复算 SA3 bp 换算与四档年化；核对 R13/SA1 复用链等值；grep K1 硬编码；读盘核 vwap 降级如实性

---

## 一、逐要素核对表（设计 §9.3 五维度 × B2/R13/R14/SA1/SA2/SA3）

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| B2 成交/费用设置<br>build_cost_sensitivity<br>build_r13_close_only<br>robustness.py:120-201 | 一致：基准收盘价成交+不计费=common.signal_backtest(cost_bps=0)；spec B2 p16「收盘价成交、不计费、不加杠杆」 | 一致：cost_bps=0 基准 / fee=3元/手 / face=100万 / stress(0,1,10,100) 全反查 config | 真实：两函数完整体，非空壳 | 一致：费用敏感性仅改 cost_bps 不改信号（:180），无新前视 | 一致：AS11（vwap 降级）/AS12（费用 bp 换算+全额计费）已登记 | 忠实 |
| R13 成交价影响<br>build_r13_close_only<br>robustness.py:120-144 | 一致（降级）：收盘价行=R11 多空（复用 build_r11_table）、T 行=买入持有；vwap 四档留 NaN。spec R13 p16 | 一致：reproducible/missing_exec_prices 反查 config | 真实：完整函数体，产 r13_close_only.csv | 一致：收盘价/T 独立核=R11 多空/T **逐位**（§四）；vwap 行 NaN+复现状态标注 | 一致：AS11 降级、vwap 档如实标注「数据缺失不可复现」不假装全复现（§三） | 忠实（降级如实） |
| R14 月度附录<br>build_r14_monthly<br>_monthly_stats<br>robustness.py:208-246 | 一致：F8 日收益按自然月切片（区间收益/最大回撤/年化波动率），口径同 _yearly_stats 换月分组。spec R14 p20-21 | 一致：periods_per_year=252 反查 config | 真实：两函数完整体，产 monthly_returns_r14.csv | 一致：独立抽算 3 月 vs CSV 差 <5e-7（§二）；102 月=100 窗口+2 边缘透明输出 | 微瑕：_monthly_stats 系 _yearly_stats 薄 wrapper 复制（CA-G01） | 忠实 |
| SA1 分年稳健性<br>build_sa1_yearly_comparison<br>robustness.py:94-113 | 一致：汇总 R10（复合 F7）vs R12（周内+复合 F8）分年并列。spec SA1 p14/p16 | 一致：复用两表无新参数 | 真实：完整函数体，产 robustness_yearly.csv | 一致：复用 build_r10/r12_yearly_table 不重算口径；2017/2019 复合→周内复合独立核=CSV（§四） | — | 忠实 |
| SA2 成交价敏感性 vwap<br>build_r13_close_only<br>robustness.py:120-144 | 一致（降级）：vwap_1/3/5/10 依赖分钟数据本地无→降级。spec SA2 p16-17 | 一致：missing_exec_prices 反查 config | 真实：同 R13（build_r13_close_only） | 一致：vwap 档 NaN+标注，矩阵/CSV 不假装全复现（§三） | 一致：AS11 confirmed（列扫描坐实 vwap 字段 0 命中） | 忠实（降级如实） |
| SA3 交易费用影响<br>build_cost_sensitivity<br>_estimated_cost_bps<br>robustness.py:151-201 | 一致（定量补充）：3元/手÷面值100万=0.03bp，stress{0,0.03,0.30,3.00}bp。spec SA3 p16（研报仅定性无对照表） | 一致：fee=3 / face=100万 / stress(0,1,10,100) 反查 config，AS12 | 真实：两函数完整体，产 cost_sensitivity.csv | 一致：独立复算 0.03bp=3/1e6×1e4；年化 8.01→7.93→7.21→0.30 与 CSV/AS12 逐档吻合（§五）；全额计费保守高估 | 一致：AS12 登记（bp 换算+全额计费简化+面值口径） | 忠实 |

---

## 二、R14 月度表独立抽算（3 月）+ 首末窗口月对 spec

**独立抽算**（从 build_final_backtest 的 F8 多空日收益，自写月切片口径 nav 累计/回撤/波动，**不调用** _monthly_stats，主区间 F8）：

| 月份 | 独立重算 复合多空(区间/回撤/波动) | CSV 复合多空 | 差(重算−CSV) | spec R14 区间 | CSV−spec |
| --- | --- | --- | --- | --- | --- |
| 2015年4月(21日) | -0.006201 / -0.030464 / 0.065212 | -0.006201 / -0.030464 / 0.065212 | -4.9e-7 / -3.3e-7 / +4.0e-7 | -0.62% | 0.00pp |
| 2016年12月(22日) | +0.044455 / -0.019389 / 0.115161 | +0.044455 / -0.019389 / 0.115161 | +4.5e-7 / -6.5e-8 / -4.8e-7 | +4.45% | 0.00pp |
| 2023年7月(21日) | +0.014568 / -0.002548 / 0.022237 | +0.014568 / -0.002548 / 0.022237 | -2.1e-7 / -1.4e-7 / -3.4e-7 | +1.46% | 0.00pp |

- 独立重算与 CSV **逐位一致**（差 <5e-7=%.6f 舍入残差）——CSV 系真实计算、非虚报。
- **coder 声称「首末月 0.00pp」独立核实成立**：报告窗口首月 2015年4月 复合多空区间收益 CSV -0.62% vs spec -0.62%（0.00pp）；末月 2023年7月 CSV 1.46% vs spec 1.46%（差 -0.003pp，2dp 舍入 0.00pp）。
- 月度数量：monthly_returns_r14.csv 共 **102** 自然月 = 研报附录窗口 **100** 月（2015-04~2023-07）+ 边缘部分月 **2015年3月**（03-24 起，不满月）/ **2023年8月**（仅 2 交易日）。边缘月按自然口径计算并**透明输出**（不隐藏、供 verifier 按月标签对齐时忽略），非虚报。

（注：年化波动率个别月对 spec 有小差，如 2016年12月 CSV 11.52% vs spec 11.26%（0.26pp），性质同 R11/R12 底座 offset（AS6 换月等），非 m8 引入；抽样月区间收益/最大回撤对 spec 均 ≤0.01pp。）

---

## 三、SA2 / R13 vwap 降级如实性核查（不得假装全复现）

**三处一致如实标注降级**（读盘核，无一处假装全复现）：
- **CSV**（r13_close_only.csv）：vwap_1/vwap_3/vwap_5/vwap_10 四行 6 指标列**全 NaN**，「复现状态」列=「数据缺失不可复现(本地无分钟vwap_X, AS11)」；收盘价行「复现状态」=「可复现(=R11最终策略多空/收盘价成交)」；T 行=「可复现(国债期货买入持有基准)」。
- **矩阵 R13(:36)**：「vwap_1/3/5/10 行本地无分钟数据留 NaN + 复现状态列标注数据缺失不可复现，如实暴露部分复现范围**不假装全复现**」。
- **矩阵 SA2(:39)**：「vwap 档如实标注不可复现……研报结论"成交价格影响不大"**无法用本地数据定量印证 vwap 档**」；矩阵 B2(:22) 亦标「成交价 vwap 档分钟数据 missing 降级」。

判定：vwap 降级在 CSV/矩阵/AS11 三处一致如实披露、暴露部分复现范围，**未假装全复现**。R13/SA2/B2 状态列虽标 done，但 done 的语义被状态理由与 CSV「复现状态」列限定为「收盘价/T 可复现 + vwap 降级」，非全表复现声明——属如实的部分复现，非虚报。

---

## 四、复用不复制核查 + R13/SA1 复用链等值核

- import 复用（robustness.py:65-84）：combo_composite.{_YEARLY_ROWS, build_composite_backtest, build_r10_yearly_table}、combo_final.{_LS_NAME, _LO_NAME, assemble_signals, build_final_backtest, build_r11_table, build_r12_yearly_table}、strategy.to_long_only、common 引擎——**均 import 调用非复制**。模块内无信号重构造、无回测引擎重写、无 F8 决策树重算。
- **R13 复用链独立核**：r13_close_only.csv 收盘价行 年化 0.080066 = build_r11_table 多空年化 0.080066、回撤 -0.03256 = R11 多空回撤 -0.03256（**逐位相等**）——收盘价行确系直接取自 R11 多空列、未重算。
- **SA1 复用链独立核**：robustness_yearly.csv 复合(R10) 2017=6.10%/2019=3.09%、周内复合(R12) 2017=10.62%/2019=5.12% 与 build_r10/r12_yearly_table 输出一致；T 列取自 R12（与 R10 同源买入持有，两表 T 相等，取一无误）。
- 微瑕（CA-G01）：`_monthly_stats`（:208-226）与 combo_composite.`_yearly_stats` 结构近乎逐行相同，仅分组键 `index.year`→`index.to_period("M")` 与行标签不同——属薄 wrapper 复制而非参数化复用。核心指标（calculate_max_drawdown/calculate_annualized_volatility）仍复用 common.utils，coder docstring(:11-13) 已透明说明「口径同 _yearly_stats 仅换分组键」；不影响正确性（§二 独立抽算逐位吻合），记 minor。

---

## 五、K1 硬编码核查 + SA3 费用换算独立复算

**K1 硬编码**：grep robustness.py 全文搜 R14 月度值（0.62/0.49/4.45/1.01/1.46）与 R13 spec 值（7.65/2.04/2.35/1.44）——命中仅在 `_smoke_report` 的 print 参照文本（:299,309-310），标注「spec R13 收盘价 / spec R14 抽样」供冒烟人工对照，**未注入 build_r13_close_only/build_r14_monthly/build_cost_sensitivity 数据流**（grep 赋值/return 行 0 命中）。反证：R13 收盘价年化 computed 8.01% ≠ spec 7.65%（继承 R11 offset），若硬编码应等于 spec——数值分歧证明系真实计算。

**SA3 费用换算独立复算**（不采信 AS12/CSV 自述）：
- 单边 bp 估算 = fee_per_lot 3 ÷ face_value 1,000,000 × 1e4 = **0.03bp**（= _estimated_cost_bps）；
- stress(0,1,10,100) → cost_bps {0, 0.03, 0.30, 3.00}bp = cost_sensitivity.csv 逐档；
- 年化：基准(0bp) 8.0066% → 0.03bp **7.9267%**（Δ-0.08pp）→ 0.30bp **7.2101%**（Δ-0.80pp）→ 3.00bp **0.2987%**（Δ-7.71pp）= CSV 逐档、与 AS12「8.01%→7.93%→7.21%→0.30%」逐档吻合；
- 全额换手计费（turnover×cost_bps，未建模平今仓免费）系**保守高估**——「现实费率档影响小」结论在高估下仍成立，更稳健。判定：SA3 换算/敏感性忠实、AS12 登记与代码/CSV 三方一致。

---

## 六、空壳核验（G-CA-3）

B2/R13/R14/SA1/SA2/SA3 实现位置逐一打开核验：build_sa1_yearly_comparison（:94-113）、build_r13_close_only（:120-144）、_estimated_cost_bps（:151-156）、build_cost_sensitivity（:159-201）、_monthly_stats（:208-226）、build_r14_monthly（:229-246）、run_robustness（:253-280）——均为完整函数体、有真实算子链（分年表并列 / R11 复用取行 + vwap NaN 标注 / bp 换算 + 多档回测 / 自然月切片 nav 聚合 / 四表落盘），且经 §二/§四/§五 独立运行复现产出正确数值。

实现代码真实性判定: 六要素实现（robustness.py 七函数）均为真实代码、非 pass/TODO 空壳，本 milestone 不存在空壳（故不触发 G-CA-3 空壳判定）。矩阵六行（B2:22/R13:36/R14:37/SA1:38/SA2:39/SA3:40）状态列均已回填 done + 真实实现位置 + implement，与代码一致。

---

## 七、issue 清单

### CA-G01 · minor · _monthly_stats 系 _yearly_stats 薄 wrapper 复制（DRY 轻微冗余）
- 定位: src/test_v2/robustness.py:208-226（_monthly_stats）vs src/test_v2/combo_composite.py:285-301（_yearly_stats）
- 依据: 两函数除分组键（index.year → index.to_period("M")）与行标签外结构逐行相同，属复制而非参数化复用（本可将 _yearly_stats 重构为接受 groupby 键参数以彻底复用）。**不影响正确性**（§二 独立抽算 3 月逐位吻合 <5e-7）、核心指标仍复用 common.utils，coder docstring 已透明说明口径一致；因 R14 为 optional 级附录、仅统计聚合无策略逻辑，记 minor。处置建议（非阻断）：如后续维护可将 _yearly_stats 参数化 freq 后 _monthly_stats 退化为一行调用。

### CA-G02 · minor · R13 收盘价 / SA3 各档年化与盈亏比继承底座 offset（非 m8 引入）
- 定位: output/test_v2/results/{r13_close_only.csv 收盘价行, cost_sensitivity.csv 各档}；根因 combo_final.build_r11_table → reversal._stats_column → common/timing_backtest.py:150-156(盈亏比 per-day) + AS6 换月
- 依据: R13 收盘价行 年化 8.01% vs spec R13 7.65%、盈亏比 1.116 vs spec 1.44（收盘价行=R11 多空、逐位继承 R11 的系统性 offset，回撤 -3.26% 仍逐位对齐 spec）。**属 m8 忠实复用 R11**（非私自偏离），根因同 m7 CA-F03/m4 CA-C01；SA3 各档同源。缺口归 verify/diagnose 复核底座（盈亏比 per-day 口径 + AS6 换月），非 m8 代码修复对象。

（说明：无 core 要素未声明偏离、无虚报、无空壳、无未来函数、无硬编码；R13/SA2 vwap 降级三处如实标注不假装全复现；R14 独立抽算逐位吻合、首末窗口月 0.00pp 独立成立；SA3 换算与 AS12 三方一致；SA1 复用汇总等值。R13/SA2/B2 状态 done 的语义被限定为「收盘价/T 可复现 + vwap 降级」，如实披露非全表复现，不构成虚报。）

---

## 八、已检查维度清单（code 五维度，无遗漏）

- [x] **公式一致**：B2 基准=signal_backtest(cost_bps=0) 逐字命中；R13 收盘价=R11 多空/T=买入持有（降级）；R14 F8 日收益自然月切片（区间/回撤/波动）口径同 _yearly_stats 换月；SA1 汇总 R10 vs R12 分年；SA3 3元/手÷面值 换算 bp + 多档；均对照 spec p16/p20-21/p14
- [x] **参数一致**：cost_bps=0 基准 / fee=3元/手 / face=100万 / stress(0,1,10,100) / reproducible_exec_prices=(收盘价) / missing_exec_prices=(vwap_1/3/5/10) / periods=252 全反查 config，无魔法数字
- [x] **实现位置真实**：robustness.py 七函数（对应六要素）均完整函数体、非空壳，独立运行复现正确数值（§六）；矩阵六行已回填 done+真实实现位置+implement
- [x] **代码反查**：R14 独立抽算 3 月 vs CSV 差 <5e-7、首末窗口月 0.00pp 独立成立（§二）；vwap 降级三处如实标注不假装全复现（§三）；R13/SA1 复用链等值逐位核（§四）；K1 无硬编码注入 + SA3 bp 换算/四档年化独立复算逐档吻合（§五）；费用敏感性只改 cost_bps 不改信号、无新前视
- [x] **简化声明**：AS11（vwap 降级，confirmed，列扫描坐实 0 命中）/ AS12（费用 bp 换算+全额计费保守高估+面值100万口径）均已登记且与代码/CSV 三方一致；_monthly_stats DRY 冗余记 CA-G01（minor）；R13/SA3 底座 offset 归验证域记 CA-G02（minor，继承非 m8 引入）

---

verdict: pass_with_issues
