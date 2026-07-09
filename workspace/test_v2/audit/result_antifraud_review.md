# 最终结果反虚报复核 result_antifraud_review.md

> 落盘于 `workspace/test_v2/audit/result_antifraud_review.md`；由 `quant-auditor`（mode=result，hard 必跑）产出。
> 审读分离：只拿产物文件、不拿 verifier/diagnoser 完成汇报；所有数值一律独立重算，不采信任何声明。
> 对象：`output/test_v2/results/`（comparison.json 81/91 + metrics.json + backtest_summary.xlsx + 5 PNG）、verify_report.md、evidence_manifest.md、assumptions.md、iterations/ 三轮、spec.md。
> 独立重算脚本：`/tmp/ra_verify2.py`（pass_count/E4/rel_dev/K2）+ 若干临时核验脚本；PNG 用 Read 逐张实际查看；parquet 直读坐实 infeasible。

---

## 一、核查项逐条记录（RA-A# 编号 / severity / 证据定位）

### RA-A01 · rolling_sharpe.png 年化基准与 headline 指标不一致 · severity: minor
- 证据定位：`output/test_v2/results/build_final_artifacts.py:281`
  `rs = strategy_ret_ls.rolling(252).mean() / strategy_ret_ls.rolling(252).std() * np.sqrt(252)`，标题 `F8 最终策略(多空)滚动夏普（252 日窗口）`。
- 依据：iter_02 M2（AS13）已将 `config.periods_per_year` 252→240，headline R11 多空夏普按 240 年化算得 2.077298（comparison/metrics 一致）；但滚动夏普图仍用 √252 年化，且标题写「252 日窗口」。滚动回看窗口取 252（一年）本属惯例、可接受，但 √252 年化系数与 M2 后全表 240 基准不一致，图面绝对水平较 240 口径偏高约 2.5%（√252/√240=1.0247）。
- 影响：仅 support 级可视化图，非计分 R 指标，不影响 pass_count 与报告落脚点 R11 结论；属 M2 迭代后未同步更新的口径遗留。建议最终报告注明或以 240 重生成。

### RA-A02 · comparison.json `iteration` 元数据字段恒为 0 · severity: minor
- 证据定位：`output/test_v2/results/comparison.json:5` `"iteration": 0`；与 `iterations/iter_02/comparison_after.json` 同值 0（均 generated_at=23:26:18、pass=81）。
- 依据：当前 comparison.json 实为 iter_02 后（81/91）产物，但 iteration 字段未随迭代递增、恒为 0。属 build 脚本静态默认字段。
- 影响：generated_at 时间戳与 pass_count=81 均正确反映 iter_02 后状态，三方数值一致性不受影响；仅元数据字段未维护，无数据完整性风险。

### RA-A03 · 精确命中项属迭代口径对齐、可信度已如实披露（透明性确认，非缺陷） · severity: minor
- 证据定位：`comparison.json` R1_T_annual_return rel_dev=0.0001（0.023002 vs 0.023）、R11_多空_下跌胜率 rel_dev=0.0001（0.490135 vs 0.4902）；`assumptions.md#AS13 可信度注记`、`#AS7 iter_02 校准`。
- 独立判断：两处近乎精确命中均为迭代口径对齐（AS13 单点 240 常数 / AS7 M3 胜率口径）之果，非逐项拟合——(a) 240 为全局单常数、同时驱动 11 项 fail→pass，非针对单指标调参；(b) M3 同一非对称口径施于 R7 得下跌 0.6504 vs 研报 0.6528（未精确命中），反证非逐项拟合。AS13 可信度注记已主动标注「中等——240 是惯例层代理，代理了残余方向性数据源漂移（本地 pct_of_close_price vs 研报 Wind 连续合约），非纯机制修正」，并举证 R11 年化波动率在 252 下反而精确对齐、改 240 反劣化。披露充分、非隐瞒。
- 提示：非虚报问题；但最终报告须保留 AS13「可信度中等·惯例层代理残余数据漂移」标注，禁止将精确命中包装为强复现证据。

---

## 二、已检查维度清单（result mode 全维度，逐维结论）

### K3 图表真实性（5 张 PNG 均用 Read 实际查看 + 数值级交叉核对）
| PNG | 实际所见 | 参照 metrics/CSV | 结论 |
| --- | --- | --- | --- |
| net_value.png | 三线：蓝(多空)终点≈1.86 / 红(仅做多)≈1.52 / 灰虚(T)≈1.21；起点 1.0、区间 2015-2023 | 净值终点 1.8638/1.5268/1.2117；`combo_final_signals.csv` 复利终点 strategy_ret_ls=1.8637=1+86.38%、close_return=1.2116 | 吻合（数值级） |
| drawdown.png | 全负、最深≈-0.0326（2015 初）、次深≈-0.025（2018） | R11 多空 max_drawdown -0.03256 | 吻合 |
| yearly_returns.png | 9 年蓝柱：2016 最高≈0.125、2023 最低≈0.013；灰柱 T 2017 负≈-0.021 | `combo_final_yearly_stats.csv` 区间收益·复合多空逐年（2016=0.125084 … 2023=0.012631）、T 2017=-0.021662 | 逐年吻合 |
| rolling_sharpe.png | 围绕 2-2.5 波动、峰≈3.4、谷≈0.7 | R11 多空整体夏普 2.077 | 一致（水平相符；basis 见 RA-A01） |
| position_signal.png | 仓位柱∈[-1,+1]、密集换手；灰线(国债期货归一化)终点≈1.21 | 仓位口径±1；T 净值终点 1.2117 | 吻合 |
- 结论：5 张图均为真实产物序列的忠实渲染，曲线条数=分组数（净值三线=多空/仅做多/T）、坐标范围与 metrics 吻合、净值终点≈1+区间收益 86.38% 数值级坐实。无「假图/占位图/曲线与数不符」。唯 rolling_sharpe 年化基准遗留见 RA-A01。

### E4 三方数值一致（comparison.json == metrics.json == backtest_summary.xlsx）
- pass_count 独立重数：comparison metrics 数组 pass=True 计数=81、pass=False=10、total=91；与声明 pass_count=81/total=91 及 xlsx『汇总』通过数 81/未通过 10 三方一致。
- 5 抽样逐位（含迭代后新值）：R7 盈亏比 1.310884 / R1_T 年化 0.023002 / R11 下跌胜率 0.490135 / R9 多空夏普 1.755453 / R11 区间收益 0.863758——comparison == metrics（6 位四舍五入）== xlsx，5/5 三方逐位一致。metrics.json 为全精度（如 R1_T 年化 0.0230018224747676）、comparison/xlsx 为 6 位，round 关系成立，非篡改。
- 全 91 项 comparison vs xlsx 逐位比对（复现值/研报值/pass 三列）：不一致点 = 0。
- 全 91 项 rel_dev 独立重算 abs(|repro|-|report|)/|report|：与声明 rel_dev 不符项 = 0。
- 结论：E4 三方一致，0 处矛盾。

### K2 过于完美检查（反拟合聚集）
- 触发条件「全部对比指标相对偏差同时 <0.5%」：不成立——87 有效判分项中 56 项 rel_dev≥0.5%，最大 72.98%（R10_2023）。
- 近乎精确命中（rel_dev<0.05%）仅 5 项且机制分散：R1_T 年化(0.0001,AS13/240)、R11 下跌胜率(0.0001,AS7/M3)、R2 abs5% 胜率(0.0,小样本 6 天)、R14_n_months(0.0,月份计数=100)、R14 2015年4月(0.0002)。
- 偏差分布健康（非零值聚集）：<0.05%(5) / 0.05-0.5%(26) / 0.5-2%(26) / 2-5%(20) / >5%(10)。
- 结论：K2 未触发，无「过于完美」虚报特征；精确命中项属口径对齐且已披露（RA-A03）。

### 归因真实性（10 项 attribution_status 与证据链自洽）
- 10/10 fail 项均带 attribution_status（8 accepted + 2 assumption_linked），无缺项。
- accepted 8 项论证代码级坐实：`strategy.py:123 signal_ls=signed_signal(signal_long+signal_short)` 且长/短端在 `build_interval_seesaw_signal` 共享同一 `quantile_lower/upper`（行 111-117）→「拉单腿必传导主列、零和不可修」成立；`templates/standards.json` timing.metrics.default={max_rel_dev:0.05} 确无 abs_eps、factor.rank_ic_mean 有 abs_eps:0.005 → R10/R12_2023 近零「容差层空档」accepted 成立。
- assumption_linked 2 项（R10/R12_2016→AS6）：2016 绝对差 1.10/1.54pp（非近零）、归 close/settle 数据源族，与 2023 近零 accepted 分层区分合理、有 iter_03 CDX-SO-02 探针佐证。
- iter_03 三探针（CDX-SO-01 分位带宽 / CDX-SO-02 局部 settle / CDX-SO-03 分年归属日）均代码机制级否决（护主列破产/主表回归/引入制表口径新假设），非空泛拒绝。
- 结论：归因真实、可追溯、与证据链自洽。

### 迭代链完整性（三轮 changes.md vs 实际代码/快照）
- 快照链 pass 独立重数：56→69→81 逐一坐实（iter_01/after 56/69、iter_02/after 69/81、iter_03 81）。
- iter1：iter_01 改前(56) vs 改后(69) 独立算得精确 13 项 F→T、0 项 T→F，且 13 项全为 profit_loss_ratio 家族——与 M1（timing_backtest.py 盈亏比 mean→sum）打击面精确一致。
- iter2：iter_02 改前(69) vs 改后(81) 独立算得精确 12 项 F→T、0 项 T→F（11 项年化/夏普对应 M2 + 1 项 R11 下跌胜率对应 M3）——EVD-14「收敛 12/回归 0」独立复算一致。
- 当前代码三处与 changes.md 声称逐一吻合（源文件 git untracked、无代码快照，按合同用文件内容比对）：`config.py:75 periods_per_year=240`(M2)、`reversal.py:148-156 _directional_win_rates` 非对称口径 up>0/down>=0 去 held 交集(M3)、`timing_backtest.py:163-167` sum 总额比(M1)。
- `reversal_baseline_stats.csv` 落盘值逐位坐实 changes.md iter_02 冒烟值：年化 0.047427/夏普 1.428149/卡玛 1.381654/上涨 0.444340/下跌 0.650415/年择时 145.483/盈亏比 1.310884(不变)；M3 数学恒等（仅做多上涨=多空=0.4443、T 上涨=1.0/下跌=0.0）在数据中可见，非 bug。
- 结论：迭代链完整、零回归、M1/M2/M3 仅改声称位置（若越界改信号逻辑，快照会见到区间收益/胜率/回撤等翻转，实测全部锚定不动）。

### 扰动测试记录核验
- EVD-08：main_end 2023-08-02→2022-08-02，R11 年化 rel_change 9.9646%>0.1%、区间收益 4.67%/夏普 6.24%/最大回撤 0.00%。
- 自洽性核验：「max_dd 0.00% 变化因回撤发生于 2022-08 前」——drawdown.png 实见最深回撤（-0.0326）在 2015 初、位于截尾点之前，截尾不改最深回撤，逻辑自洽、与图互证。
- K2 未触发（本审独立复核一致）→扰动非因过于完美触发；hard 难度必做已于 final verify 执行并清理临时输出（EVD-08 记录透明披露 build --perturb 不可用故另起临时脚本）；iter2 未重跑扰动理由（M2 改年化常数、M3 改胜率口径均与硬编码正交）成立。
- 边界：本审为只读审计者，未独立重执行扰动（属 verifier 域）；仅核记录内部自洽性 + 与 drawdown 图互证，判为可信。

### skip / infeasible 理由核实（catalog 是否矛盾）
- AS5（m3 R5/R6 中债净价现券指数 data_missing）：独立直读 `~/local_data/bond_index_quote.parquet`——3585 唯一 index_code、CBA 前缀唯一码=0、四目标码 CBA00102/00602/00902/07702 各 0 行；`templates/data_catalog.md:73` 现已如实标注「无中债 CBA 系列行情…零行情覆盖」，未声称可 derive。理由成立、catalog 无矛盾。
- AS11（R13 vwap_1/3/5/10 分钟数据缺失）：独立直读 `~/local_data/financial_future_price.parquet` 列集，vwap/avg/mean/twap/均 正则命中=0；本地最细日频。理由成立。
- 结论：两处 infeasible/降级理由独立坐实，无「声称 missing 实则可 derive」的虚报。

---

## 三、复核结论

- 反虚报三查（K2/K3/E4）全部通过：E4 三方 0 矛盾、K3 五图数值级忠实、K2 未触发且偏差分布健康。
- 归因真实、迭代链完整零回归、扰动记录自洽、infeasible 理由独立坐实。
- 未发现 critical/major 级虚报或编造；仅 3 项 minor（rolling_sharpe 年化基准遗留 / iteration 元数据字段 / 精确命中口径对齐已披露的透明性提示）。
- 报告落脚点 R11（多空核心五指标）全 pass，主结论不受残余 10 项动摇；最终报告须保留 AS13 可信度中等标注。

verdict: pass_with_issues
