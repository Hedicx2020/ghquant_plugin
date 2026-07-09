# 实现忠实性审计 · test_v2 · milestone m4（隔日反转因子）

- 审计模式: code（实现忠实性，hard 逐条核对）
- 审计对象: coverage_matrix m4 done 行（F3 隔日反转因子 chg_t，实现位置 reversal.py:calculate_reversal_signal, run_reversal_baseline）
- 审计原则: 只读不改产物；数值独立重算，不采信 coder 自述与冒烟结论；与 coder 无交流
- 独立重算依据: output/test_v2/results/reversal_baseline_stats.csv、源码逐行反查、与 legacy src/test/strategy.py 结构比对

---

## 一、逐要素核对表（五维度 × F3 两函数）

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| F3 因子/信号<br>calculate_reversal_signal<br>reversal.py:75-122 | 一致（AS4 六条逐条命中，见 §二） | 一致：lag=2/min=0.0003/max=0.005 来自 config（config.py:58-60），对 AS4 T-2/0.03%/0.5% 一致 | 真实：完整函数体，非空壳 | 一致：内部无 .shift() 预移位（唯一移位是回测 lag=2）；防锚定见 §四 | 一致：主力连续 settle.pct_change() 换月不复权由 AS6 声明 | 忠实 |
| F3 回测<br>run_reversal_baseline<br>reversal.py:182-241 | 一致：多空用原始 signal、仅做多 clip(lower=0)（:208，AS2）；lag=reversal_lag_days=2（:211-212）；B1 第一段区间 [2015-03-20,2023-08-02] 截取（:201-202，config.py:27-28） | 一致：区间/lag/cost/periods 来自 config | 真实：完整函数体，产 reversal_baseline_stats.csv | 一致：lag 语义独立推演无前视（§三）；K1 无 R7 数值硬编码（§五） | 瑕疵：细分胜率口径 AS7 声明；盈亏比按日口径与 spec 缺口（CA-C01） | 忠实（盈亏比/涨跌胜率缺口见 CA-C01） |

---

## 二、AS4 公式六条逐条对照代码（calculate_reversal_signal）

| # | AS4 口径 | 代码实现 | 定位 | 判定 |
| --- | --- | --- | --- | --- |
| 1 | chg_t = T-2 结算价涨跌 = settle_{T-2}/settle_{T-3}-1 | `chg_t = settle.pct_change()`（= settle_d/settle_{d-1}-1，因子置于算出日 d；经回测 lag=2 使 position[T]=signal[T-2]，即 d=T-2） | reversal.py:104 + 211 | 一致 |
| 2 | 激活 \|chg_t\| ∈ [0.03%,0.5%] 含边界 | `(abs_chg >= min) & (abs_chg <= max)`（闭区间双侧含边界） | reversal.py:108 | 一致 |
| 3 | 方向映射 chg_t>0→做空-1、chg_t<0→做多+1 | `-np.sign(chg_t)`（sign(+)=1→-1；sign(-)=-1→+1） | reversal.py:111 | 一致 |
| 4 | 区间外信号为 0 | `.where(active, 0.0).fillna(0.0)` | reversal.py:111 | 一致 |
| 5 | 仅做多 = 剔除做空腿（AS2） | `lo_signal = ls_signal.clip(lower=0.0)` | reversal.py:208 | 一致 |
| 6 | B1 第一段区间 2015-03-20 起 | `reversal_start="2015-03-20"`；`window = sig_frame.loc[(index>=start)&(index<=end)]` | config.py:27-28 + reversal.py:201-202 | 一致 |

判据：AS4 六条全部命中。因子严格取 AS4 字面 settle.pct_change()，激活区间闭区间双含边界、方向映射与区间外置零均与 AS4 逐字一致。

---

## 三、lag 语义专项：reversal_lag_days=2 推演与前视核查

独立推演（不采信 docstring，自索引重算）：
- 因子日 d：`chg[d] = settle_d/settle_{d-1}-1`，signal[d] = -sign(chg[d])·active（reversal.py:104-111），d 日收盘公布结算价后即完全已知。
- 回测滞后：signal_backtest 内 `position = sig.shift(lag)`（timing_backtest.py:61），lag=reversal_lag_days=2 → position[T] = signal[T-2]。
- 收益兑现：`strategy_ret[T] = position[T]·ret[T] = signal[T-2]·(close_T/close_{T-1}-1)`——因子 T-2 判、吃 T 日单日收益。
- 链路：因子(T-2 收盘算出) → 至迟 T-1 收盘建仓 → 收益兑现于 T 日；因子仅依赖 ≤T-2 结算价、仓位在 T-1 收盘即定，早于 T 日收益区间起点，**无前视/未来函数**。
- "隔日"语义自洽：因子 T-2 → 结果 T（跳过 T-1），恰为"隔日反转"结构。

双重叠加 bug 独立验证（coder 自述曾修正过 lag 双重叠加）：
- calculate_reversal_signal 内部**无任何 .shift()**（grep 全函数确认，唯一 pct_change 是相邻结算价比值、非移位），T-2→T 间隔**完全**由回测 lag=2 承载。
- 不存在"信号预 shift(2) + 回测再 lag" 的四日叠加残留。当前版本无 shift(2)+lag 叠加。判为无双重叠加。

---

## 四、防锚定核查：reversal.py vs legacy src/test/strategy.py:calculate_reverse_signal

逐项比对 v2 `calculate_reversal_signal`（reversal.py:75-122）与 legacy `calculate_reverse_signal`（test/strategy.py:187-209）：

| 维度 | legacy | v2 | 差异 |
| --- | --- | --- | --- |
| 因子源 | `settle_return`（同合约 pct_of_sett_price/100，规避换月跳空） | `settle.pct_change()`（主力连续价、含换月跳空、AS4 字面） | 语义选择不同（v2 独立选 AS4 字面口径，AS6 声明） |
| 移位位置 | `settle_return.shift(2)` 内置信号函数、回测不再 lag | 信号不预移，回测 lag=2 承载 T-2→T | 实现路径不同 |
| 激活判定 | `.between(min,max, inclusive="both")` | `(abs>=min) & (abs<=max)` | idiom 不同 |
| 方向编码 | `.mask(active & lagged>0, -1)`；`.mask(active & lagged<0, 1)` 双次 | `-np.sign(chg_t).where(active, 0)` | idiom 不同 |
| 函数/列名 | calculate_reverse_signal；reverse_signal / reverse_chg_t_minus_2 / reverse_active | calculate_reversal_signal；signal / chg_t / abs_chg_t / active | 命名不同 |

结论：结构 / 命名 / 实现路径显著差异，且 v2 在因子源上做了**不同于 legacy** 的独立选择（settle.pct_change 主力连续 vs legacy settle_return 同合约）——两者甚至会在换月日产生不同信号，绝非复制粘贴。防锚定通过；公式语义一致属应然（同实现 AS4/同一前作公式）。AS6 明确声明 v2 采字面口径并留 settle_return 作备选，独立性有据。

---

## 五、K1 抽查：R7 基准数值硬编码核查

grep reversal.py 全文搜 R7 基准值（4.78% / 1.40 / 54.34% / 55.68% / 65.28% / 44.48% / 147.29 等）：
- 命中 0 处硬编码进数据流。"R7" 仅出现在注释/docstring（reversal.py:52,156,179,183,191,250）作行序说明与量级参照描述，无数值注入。
- reversal_baseline_stats.csv 全部数值为 timing_metrics 计算产出（全精度浮点，如区间收益 0.482414），非硬编码圆整值。
- 独立自洽核验：多空区间收益 0.482414 → 年化 (1.482414)^(252/2039)-1 = 0.04986 = CSV 年化 0.049857；夏普 = 0.049857/0.034029 = 1.4652 = CSV 1.465127；卡玛 = 0.049857/0.034326 = 1.4524 = CSV 1.452432。三处内部自洽，确系计算产出。

判据：K1 通过，无 R7 数值硬编码虚报。

---

## 六、空壳核验（G-CA-3）

F3 实现位置逐一打开核验：`calculate_reversal_signal`（reversal.py:75-122）与 `run_reversal_baseline`（reversal.py:182-241）均为完整函数体、有真实算子链与回测调用，非 pass / TODO / 空返回 占位。m4 done 行不存在空壳，无需在变更日志记状态回退。

---

## 七、issue 清单

### CA-C01 · minor · 盈亏比与上涨/下跌胜率量级缺口（验证域，非 m4 私自偏离）
- 定位: output/test_v2/results/reversal_baseline_stats.csv（盈亏比行、上涨/下跌胜率行）；口径实现 reversal.py:172（映射 metrics["profit_loss_ratio"]）、common/timing_backtest.py:150-156
- 依据: 独立读数——多空盈亏比 1.05 / 仅做多 1.04 vs R7 spec 1.31 / 1.47（-20% / -29%）；多空上涨胜率 53.04% vs 44.48%、下跌胜率 58.08% vs 65.28%。细分胜率偏差 AS7 已声明"口径存疑"；盈亏比忠实沿用 B1 common 按日口径 mean(+日收益)/mean(\|−日收益\|)，疑与研报按笔（per-trade）口径不同、对多日持仓策略系统性压向 1.0。属实现忠实（忠实调用既定 B1 引擎、非 m4 私自偏离），但缺口需 verify/diagnose 复核 B1 盈亏比口径。附：coder 冒烟自检"核心五指标≈5% 容差内"恰回避了盈亏比这一第六指标，审读分离下不采信、独立记录之。

（说明：无 core 要素的未声明偏离、无虚报、无空壳，故无 critical/major。）

---

## 八、已检查维度清单（code 五维度，无遗漏）

- [x] 公式一致：AS4 六条逐条对照代码（§二）——chg_t=T-2 结算价涨跌、[0.03%,0.5%] 含边界、方向映射、区间外 0、仅做多 clip、B1 第一段区间 2015-03-20，全部命中
- [x] 参数一致：lag=2 / min=0.0003 / max=0.005 / reversal_start=2015-03-20 / cost=0 / periods=252 全部反查 config，无魔法数字
- [x] 实现位置真实：calculate_reversal_signal 与 run_reversal_baseline 均完整函数体，无空壳（§六）
- [x] 代码反查：lag 语义独立推演无前视 + 无 shift(2)+lag 双重叠加（§三）；防锚定 diff 确认独立于 legacy（§四）；K1 无 R7 硬编码 + 三处内部自洽（§五）
- [x] 简化声明：AS4（公式）、AS6（主力连续换月不复权）、AS7（细分胜率口径）、AS2（仅做多）均已登记；盈亏比缺口归 B1/verify（CA-C01）

---

verdict: pass_with_issues
