# r003 result_audit 修复后最终复审（attempt2）

- 日期：2026-07-18
- 结果源：`output/r003_equity_factor_timing_cn/results/` attempt2 正式新产物及 `verify_report.md`
- 复审边界：只读核验代码与正式结果；未修改代码、正式 `results/` 或 `state.json`
- 正式结果冻结快照指纹（文件名、文件SHA与mtime组合）：`aa2899d2e1e36ad018c9c19b14d4c8604c68941b36303b3a20a4037ce56f8238`
- findings：无；严重度：无

## 1. RA-A01：预测散点底表与正式PNG

- 默认回读 `backtest_summary.xlsx/图_预测散点` 得198行，覆盖2023-04至2025-12共33个月；每月恰有6行、6个唯一因子和1个赢家。
- `predicted_probability`、`factor_return`、`is_winner` 三列缺失数均为0，概率和实际收益无 `NaN/Inf`；每条记录均满足 `prediction_period=predictor_period+1月`。
- 独立按底表重建当前散点对象，Matplotlib `PathCollection` offsets恰为198。重建PNG与正式 `prediction_scatter.png` 尺寸同为2955×1752、像素逐点完全一致、文件SHA同为 `1147f901e2bd4ae3f8bca8403fe95919daad4b2c94a787f18e46ef271522e217`。
- 因此正式PNG确实绘制198/198个观测，不存在原问题中的11个月、66个点丢失。

verdict RA-A01: pass

## 2. RA-A02：逐股票执行/退出审计与可复算哈希

### 2.1 结构和月份

- 默认 `pd.read_excel` 回读 `returns_detail.xlsx/execution_exit_audit` 为154,529行、26列，覆盖33个连续预测月；`signal_date,factor,stock_code` 重复键为0。
- 必需字段包含信号/预测月、六位代码、权重、计划/实际执行日、执行限制五类标志、计划/实际退出日、自然日及交易日延迟、标签可得日、NAV留痕和20交易日搜索窗末日。

### 2.2 独立规范化与三方SHA

未调用被审 `reporting.py` 的哈希函数，只按 `metrics.json` 披露的 `execution_exit_audit_v2` 规则独立实现日期 `YYYY-MM-DD`、布尔小写、12位小数、`<NA>`、数字股票代码六位补零以及工作表原列序/行序规范化。复算结果为：

`c2a11549c2f6f172d3fdb376a8b279361e6754b25e23f437dd350cdf8ba88692`

该值与 `metrics.json.execution_exit_audit.sha256` 及 `run_log.md` attempt2最后一段完全一致；summary同时披露 `version=execution_exit_audit_v2` 和 `numeric_decimal_places=12`。

### 2.3 交易限制与20日退出追溯

- 实际执行151,483、执行受限3,046；`can_execute` 与 `executed` 逐行一致，实际执行日非空集合与已执行集合完全一致。所有受限行均有执行限制原因且至少一个ST、无量、停牌、涨停或跌停标志为真。
- 正常退出148,330、延迟退出2,885、20交易日搜索耗尽268、NAV留痕268。实际退出日非空集合与 `exit_executed` 完全一致，且从不早于计划退出日。
- 所有执行后未退出行的 `exit_delay_trading_days=20`、`nav_marked=true`、状态为 `exit_search_exhausted_nav_mark`；全部延迟或未解决行均有非空限制原因和搜索窗末日。实际延迟退出的自然日间隔为1至28天，符合“最多20个额外交易日”而非自然日口径。
- 标签可得日逐行不早于计划退出日；六项计数和限制/收益状态分布与metrics逐项一致。

verdict RA-A02: pass

## 3. AS41与成本口径

- AS41明确中证800是无成本理论指数基准，三个可投资因子组合按袖套换手计费，净主动收益比较有成本策略与无成本基准。
- 正式组合收益共132行、四组合各33月。中证800累计成本0，逐月 `gross_return=net_return`，口径唯一为 `index_benchmark_no_stock_cost`。
- 六因子1/N、商业周期15%倾斜、ML胜出概率的累计成本分别为 `0.001`、`0.0041875`、`0.01933195339426413`，口径均为 `factor_sleeve_stock_cost`；全部132行独立复算 `gross_return-net_return=transaction_cost` 最大误差为0。
- `metrics.json.transaction_cost_scope`、AS41、Excel正式结果与 `verify_report.md` 四处一致。

verdict CDX-R-01: pass

## 4. comparison、四组合指标与15项infeasible

### 4.1 comparison和四组合指标

- `comparison.json` 有21个唯一数值项，`metric_count=metric_pass_count=21`，另有3个原文N/A定性项；所有pass基础均明确为实验性市场迁移“输出完整并独立复算”，不是数值接近美国原值。
- 从 `returns_detail.xlsx/组合收益` 的132行月收益独立复算四组合年化收益、年化波动、Sharpe、相对收益、跟踪误差和信息比率，共21项，与metrics及comparison最大绝对差仅 `2.3314683517128287e-15`，属于浮点运算顺序尾差。
- K2未触发：21项美中相对差中低于0.5%的数量为0；最小值1.7489%，中位数36.3069%，最大值2856.68%，不存在“结果过于完美”。

### 4.2 15项infeasible

- `coverage_matrix.md` 恰有D15–D29共15行 `infeasible`，实现位置为空，理由均为“原文未披露名称与数值，仅完整性占位”。
- 原文p5声称考虑25个宏观驱动，但p6 Exhibit 3实际只列出10个可识别变量：核心CPI两项、GDP/周期两项、金融条件三项、货币政策两项、CAPE一项；其余15项没有名称、数值或变换，无法从 `data_catalog` 映射未知变量。
- `spec.md` 对D15–D29逐项标记 `missing/nonrecoverable`，A1/AS29记录用户确认实验性中国迁移不补写这15个美国未知变量。因此skip理由真实，不是把可derive数据伪报为缺失。

verdict comparison_and_infeasible: pass

## 5. K3、E4与hard扰动

### 5.1 K3图表真实性

- 六张正式PNG均大于15KB、约300 DPI，逐张视觉检查均非空白/占位。
- 结构复核：特征重要性有有效非负柱形；RankIC有33个时点；累计收益和回撤各有四组合×33月；训练/验证损失有4条序列、132行；预测散点为六因子198点。
- 累计收益图的132行底表逐点等于月收益复利累计；回撤图四条序列的最深回撤逐项等于metrics最大回撤。正式散点PNG还通过了前述像素级重建比对。

verdict K3: pass

### 5.2 E4三方数值一致

以下五项均满足 `metrics.json == verify_report.md == backtest_summary.xlsx`，且能从底层月收益/明细独立复算：

| 抽查项 | 三方共同值 |
| --- | ---: |
| 中证800毛收益年化收益 | 0.05673765732343328 |
| 中证800观测数 | 33 |
| RankIC均值 | 0.129004329004329 |
| 周期组合累计成本 | 0.0041875 |
| ML组合累计成本 | 0.01933195339426413 |

此外，`oos_evidence_manifest.json` 的13条产物字节SHA和文件大小全部独立重算一致。

verdict E4: pass

### 5.3 hard扰动与反硬编码

- attempt1已执行截止日提前至2024-12的完整策略级扰动；其策略核心与attempt2一致，且attempt1/attempt2的132行组合收益哈希相同。本轮result修复只涉及报告连接和审计证据输出，不改变模型/组合计算。
- 对attempt2正式底层数据再次独立做内存扰动：首个ML月毛收益增加0.01后，年化收益由 `0.09714499114320896` 变为 `0.10111901391347411`，相对变化4.0908%，高于0.1%阈值。
- 首条散点概率增加0.05后，198点offset哈希改变；审计首行权重增加0.000001后，完整v2审计哈希改变。三类输出均随对应输入变化，未见解耦或硬编码。

verdict hard_perturbation: pass

## 6. 结论措辞

- metrics、comparison、清单和验证报告均明确这是中国A股 `experimental` 市场迁移，美中差异只作背景，不是严格美股复现误差。
- 正式OOS仅33个月、状态分类准确率约30.30%；验证报告明确写明“不支持长期稳定领先或充分泛化的外推”，没有把短样本相对领先夸大为长期稳定有效。
- `comparison.json` 的21个pass表示迁移输出完整且可复算，不表示21项均达到美国原值。

verdict conclusion_wording: pass

## 最终结论

原两项RA已由attempt2正式新产物闭环；AS41、21项comparison、四组合指标、15项infeasible、K2/K3/E4、hard扰动及谨慎结论措辞均通过独立复核。未发现critical、major或minor问题。

verdict: pass
