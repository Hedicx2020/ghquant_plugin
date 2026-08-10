# ssrn_6115073 最终复现报告

**研报**：Online Portfolio Selection Using Macroeconomic Pattern Matching（SSRN 预印本 abstract=6115073，University of Southampton / University of Adelaide，未经同行评审）
**报告类型**：allocation（资产配置） | **难度**：hard | **复现模式**：experimental（市场迁移复现）
**复现区间**：训练 2007-01~2018-12，测试 2019-01~2024-12（A股） | **样本外延伸**：2025-01~2026-06（18 个月）
**汇总日期**：2026-07-11 | **汇总者**：quant-reporter（只汇总、不新增结论、不重算指标，一切数值引自既有产物）

---

## 一、复现结论

### 1.1 达标判定

- **verdict.result：pass**（`comparison.json` `overall_pass=true`）
- **指标通过数：98/98**（81 项定量指标 + 17 项定性指标，全部 `pass=true`）
- **判定口径（experimental 专属，非数值追平）**：原文美股 S&P500/Dow Jones + 日股 Nikkei225 + FRED 美国宏观本地全不可得，本案 `pass` 按"迁移市场产出完整 + 计算可信"填写，**不是**"复现值与原文值在容差内对齐"。`comparison.json` 中 `rel_dev`（相对偏差）区间跨度 1.5%～868%，`tolerance_key` 统一标注 `allocation.default(experimental豁免)`——数值对齐在本案属设计内豁免项，判定依据详见 §九。

### 1.2 可信度评级：**A**

评级含义详见 1.3 的边界澄清；先给出判据核对：

| 判据（设计 §十二 + 硬约束细化 rubric） | 本案实测 | 达标 |
| --- | --- | --- |
| 覆盖率 ≥90%（core 100%） | 35 要素中 33 done / 2 skipped（SA5/SA6，均 optional），覆盖率 **94.3%**；core 21 项、support 12 项**均 100% 完成**，仅 optional 层 2 项如实 skip | 是 |
| 实跑的外审全部通过且无失败性降级 | spec/code/result 三审查点**全部 engine=codex 真实执行**（无 `claude_fallback`、无因 codex 不可用而 `skipped`）；三者均完成审→修→复审闭环：spec `pass_with_issues`（3 major 全 accepted 修复）、code `fail`（2 major 全 accepted 修复）、result `pass`（0 finding） | 是 |
| 零 critical 遗留 | 外部 codex 审计（spec/code/result）+ 内部逐里程碑 `impl_audit_m1-m7` + `result_audit` 反虚报复核三层核查，**全流程 0 条 critical**；仅有的遗留项（SA-A03 rejected、RA-01）均为 minor 且已给理由 | 是 |

三项判据全部满足 A 级门槛（详细依据见附录 A.3/A.6）。

### 1.3 评级含义边界（必读，不因 A 级而弱化如实汇总）

**本评级衡量的是"复现/迁移过程执行的完整性与严谨性"**——要素覆盖是否完整、审计意见是否闭环无偷懒、独立复算与扰动测试是否证实计算可信、未来函数红线是否守住——**不代表"该策略在 A 股可稳定盈利"或"迁移市场数值验证通过"**。综合本次复现的正反两方面证据：

- **支持高评级的一面**：实现忠实完整（35 要素 33 done、0 pending/infeasible）；三审查点闭环无降级（codex 全程可用，2 处 major bug 均被抓出并修复：建仓漏 member 时点成分过滤、F12 裸 except 静默吞错）；未来函数验证严格（m1-m7 每阶段均有独立重算坐实"训练期数据确未参与测试期估计"，含 4 次扰动测试全部 PASS）。
- **拉低"策略有效性"（非"过程质量"）的一面**：因本地环境缺 sklearn/stumpy/statsmodels/shap，聚类四模型、Matrix Profile、VAR/GFEVD、BorutaShap 四处核心方法均为**自实现退化**（AS38/AS45/AS49/AS52，均经合成数据/独立复算验证数学健全，非野路子实现，但终究非官方库背书）；UR（失业率）**据实降维剔除**、DGDP 用社融/M2 粗代理（AS30/AS31/AS35）；**样本外（2025-01~2026-06）主市场沪深300 conclusion=失效**——夏普由样本内 +0.7168 反号至 **-0.1209**，跑输被动指数（详见 §十）。

**结论：可信度评级 A 与"方法在 A 股长期有效"是两个不同维度的判断，不应混淆。** 本报告后续各节将如实呈现"部分迁移成立、样本外失效"的实证发现，不因过程评级高而美化结果评级。

### 1.4 一句话摘要

本次复现在 A股三宽基（沪深300/上证50/中证500）上完整实现原文"Δβ 敏感选股 → SU 聚类 → 两阶段宏观/价格模式匹配 → Diebold-Yilmaz 溢出加权 → EW/MV 组合"全链方法，35 个复现要素中 33 个 done（0 pending/infeasible，2 个 optional 项如实 skip），三处 codex 外部审查（spec/code/result）全部真实执行并闭环修复 2 处 major 代码缺陷（member 时点成分过滤缺失、异常吞错），comparison.json 98/98 指标通过（experimental 口径：产出完整+计算可信，非数值追平）。**核心实证发现**：样本内（2019-2024）方法**部分迁移成立**——去宏观（CPM）、去溢出加权（EWMFM）两个消融环节验证有增量价值，但去聚类（PMM）环节增量存疑（hs300/zz500 未降反升，呼应 SU 结构弱的迁移发现）；关键宏观因子从原文 CPI/IR 迁移为 A股 PMI；对参数窗口 w 高度脆弱。**样本外（2025-01~2026-06，18 月）conclusion=失效**：主市场沪深300 CPMM-EW 夏普由 +0.7168 反号至 -0.1209，消融增量三项全部转负，跑输被动指数（沪深300指数样本外 SR 达 1.135）；上证50 逆势强化、中证500 温和衰减，市场分化明显。

---

## 二、指标对比总表

> 数值全部引自 `output/ssrn_6115073/results/comparison.json` 与 `verify_report.md`"最终验证（member 过滤后权威版）"小节（权威口径，**取代**上文各里程碑段落中基于旧 tradeable-only 口径的数字，详见 §八注意事项）。原文列=S&P500/DowJones/Nikkei225，复现列=沪深300/上证50/中证500（市场映射见 §九）。

### 2.1 R1/表2 核心比率（CPMM-EW 主模型，member 过滤后权威值）

| 指标 | 沪深300(复现) / S&P500(原文) | 上证50(复现) / DowJones(原文) | 中证500(复现) / Nikkei225(原文) |
| --- | --- | --- | --- |
| AR（算术年化收益） | 0.2259 / 0.269 | 0.1795 / 0.262 | 0.2104 / 0.300 |
| AStd（年化波动） | 0.2764 / 0.205 | 0.2534 / 0.241 | 0.3064 / 0.160 |
| SR（夏普） | 0.7168 / 1.317 | 0.5982 / 1.091 | 0.5946 / 1.875 |
| PSR（概率夏普） | 0.9595 / 0.836 | 0.9511 / 0.723 | 0.9174 / 0.715 |
| SOR（Sortino） | 1.2862 / 1.306 | 1.3291 / 0.821 | 1.0272 / 1.002 |
| MR（Modigliani） | 0.1683 / 1.313 | 0.1406 / 1.088 | 0.1592 / 1.870 |

CPMM-MV（MV 变体）SR：沪深300 **0.9297** / 上证50 **0.6509** / 中证500 **0.6587**。全 6 比率 × 11 方法 × 3 市场完整数据见 `backtest_summary.xlsx`。

### 2.2 R3/表4 下行保护（组合层 β，双区制回归组合收益 vs 指数）

| 指标 | 沪深300 CPMM-EW（复现/原文） | 上证50 CPMM-EW（复现/原文） | 中证500 CPMM-EW（复现/原文） |
| --- | --- | --- | --- |
| β⁺ | 1.1649 / 0.9（match） | 1.6658 / 0.9（match） | 0.7875 / 0.85（match） |
| β⁻ | 0.9469 / -0.2（**不匹配**） | -0.0221 / -0.3（match，≈0强保护） | 1.0294 / -0.2（**不匹配**） |
| Δβ | 0.2180 / 0.7（match） | 1.6878 / 0.6（match） | -0.2419 / 0.65（**不匹配**） |

**关键区分（勿混淆两个层级）**：候选**个股级** Δβ 符号分布（下行保护选股逻辑）在三市场均以正为主导（hs300 32+/8−、sz50 43+/7−、zz500 37+/13−）——**迁移成立**；但**组合层**（CPMM-EW 整体收益 vs 指数回归）β⁻ 仅 **sz50** 呈现原文式的"接近 0/强保护"特征，hs300/zz500 组合层 β⁻ 为正，未呈原文全负的下行保护特征。

### 2.3 R4/表6 宏观溢出强度（to_index 口径，7 因子 × 3 市场）

| 宏观因子 | 沪深300 | 上证50 | 中证500 | 原文（S&P500/DJ/N225） |
| --- | --- | --- | --- | --- |
| CPI | 4.986（#1） | 4.923（#1） | 4.932（#2） | 102.5 / 302.7 / 319.3（原文最强） |
| PPI | 4.494 | 4.040 | 5.067（#1） | 3.012 / 8.888 / 9.611 |
| GDP | 1.844 | 1.626 | 1.781 | 0.318 / 0.941 / 1.053 |
| IP | 2.559 | 3.134 | 1.049 | 3.988 / 11.78 / 12.82 |
| M2（新增候选） | 2.224 | 3.151 | 1.069 | n/a |
| PMI（新增候选） | 3.510 | 3.030 | 3.515 | n/a |
| IR | 1.374（#7垫底） | 1.959（#6） | 0.746（#7垫底） | 58.37 / 173.6 / 172.7（原文次强） |

**CPI 溢出最强的原文核心结论迁移成立**（三市场 to_index 均居前二）；**IR 溢出方向相反**（原文次强，A股三市场垫底/近垫底）——口径为月频收益/变化广义溢出（AS53），非原文波动率溢出，量级不可比只比排名。

### 2.4 R5/图9-10 累计收益（自产曲线，与原文近似值定性对照，数值豁免）

| 模型 | 沪深300(复现/原文≈) | 上证50(复现/原文) | 中证500(复现/原文) |
| --- | --- | --- | --- |
| CPMM-EW | 194.4% / ≈110% | 139.1% / ≈105% | 140.1% / ≈110% |
| CPMM-MV | 560.3%（集中度畸高，见 AS56/AS11） / ≈75% | 188.6% / n/a | 187.6% / n/a |

### 2.5 定性判据全量（17 项，全部 pass，直引 `comparison.json` `qualitative`）

| 判据 | 预期 | 实测（原文引述） | pass |
| --- | --- | --- | --- |
| leadership.hs300 | CPMM-EW 领先消融与外部基准 | 沪深300 CPMM-EW SR=0.7168 排名4/11，最高=CPMM-MV(0.9297) | 是 |
| leadership.sz50 | 同上 | 上证50 CPMM-EW SR=0.5982 排名2/11，最高=CPMM-MV(0.6509) | 是 |
| leadership.zz500 | 同上 | 中证500 CPMM-EW SR=0.5946 排名3/11，最高=CPMM-MV(0.6587) | 是 |
| ablation.hs300 | 去宏观/去溢出/去聚类均劣于全量 | SR CPMM-EW=0.717/CPM-EW=0.550/PMM=0.770/EWMFM=0.580（**PMM未降反升**） | 是 |
| ablation.sz50 | 同上 | SR CPMM-EW=0.598/CPM-EW=-0.015/PMM=0.370/EWMFM=0.230（全消融均劣） | 是 |
| ablation.zz500 | 同上 | SR CPMM-EW=0.595/CPM-EW=0.062/PMM=0.616/EWMFM=0.405（**PMM未降反升**） | 是 |
| R4_strength_rank.hs300 | 原文CPI最强IR次强 | CPI(5.0)>PPI(4.5)>PMI(3.5)>IP(2.6)>M2(2.2)>GDP(1.8)>IR(1.4) | 是 |
| R4_strength_rank.sz50 | 同上 | CPI(4.9)>PPI(4.0)>M2(3.2)>IP(3.1)>PMI(3.0)>IR(2.0)>GDP(1.6) | 是 |
| R4_strength_rank.zz500 | 同上 | PPI(5.1)>CPI(4.9)>PMI(3.5)>GDP(1.8)>M2(1.1)>IP(1.0)>IR(0.7) | 是 |
| R3_downside_protection.hs300 | 候选Δβ>0主导 | Δβ>0:32 / Δβ<0:8（tier=Tier1） | 是 |
| R3_downside_protection.sz50 | 同上 | Δβ>0:43 / Δβ<0:7（tier=Tier2_degraded） | 是 |
| R3_downside_protection.zz500 | 同上 | Δβ>0:37 / Δβ<0:13（tier=Tier1） | 是 |
| SA1_rolling_stability | CPMM-EW跨滚动子区间稳健领先 | 9组排名混合（详见 §六），**非稳定全胜** | 是（产出，非"稳定领先"） |
| SA2_oos_tail | 样本外尾窗表现 | 尾窗2023-2024 SR：hs300=-0.3547/sz50=0.8147/zz500=2.1332 | 是 |
| SA3_param_sensitivity | 选定参数邻域不崩 | nc/w/λ 详见 §六（**w 脆弱**） | 是（产出，非"全稳健"） |
| SA4_factor_criticality | 检验单因子价值 | 仅用PMI最强(SR1.167)；剔除任一因子ΔSR≥0（**不依赖任一单因子**）；原文CPI/IR在A股未迁移成立 | 是 |
| weight_path_similarity | 权重路径合理 | hs300 CPMM-EW月均在仓3.31只(min1/max8)，权重和=1.0000，调仓70期 | 是 |

> 注：本表 `pass=true` 一律指"该项已产出且经独立核验计算可信"，多条判据的实测文字本身即包含"未降反升""非稳定全胜""脆弱"等负面/中性发现——**pass 不等于"方法完全达标/表现优异"**，请勿脱离 observed 原文断章取义。

---

## 三、假设登记簿（全量 63 条，`assumptions.md` 全文收录）

> 每条含：假设内容摘要、依据、**验证后回看结论**（引自 assumptions.md，已按 verify 权威口径整体回填，无 `[verify 后填]` 残留）、**revise 指引**。`major-auto` 高亮的假设用 **[MAJOR-AUTO]** 标记——这些是对下游结论影响最大、最值得复核方优先复核的假设。

### 3.1 研报歧义裁决（AS1-AS27，对应 ambiguities.md A1-A27，auto 模式裁决）

**[AS1] [MAJOR-AUTO]** 宏观变量 X 取同比变化、月频对齐做双区制 OLS
- 假设内容：X=中国宏观指标同比(yoy)月度一阶差分（Δyoy），股票收益聚合到月频，按 X>0 估 β⁺、X<0 估 β⁻
- 依据：spec 自身指出"X>0/X<0 分区制暗示 X 为变化量而非水平"
- 验证后回看：月频对齐双区制 OLS 全链跑通，候选 Δβ>0 主导（hs300 32/8·sz50 43/7·zz500 37/13），下行保护选股迁移成立；口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS1 "改用宏观指标水平值而非月度变化量做双区制回归，对比候选集与Δβ分布差异"`

**[AS2] [MAJOR-AUTO]** 簇数 nc 由 Silhouette 每期自动确定
- 假设内容：候选簇数 2..10 用 Silhouette 自动选最优 nc，不设全局固定值
- 依据：spec 明示 Silhouette 定簇；表7 只给相对敏感性
- 验证后回看：三市场 Silhouette 定 nc 均触搜索上界 NC_MAX=10（SU 结构弱 silhouette≤0.065，AS48），自动确定机制运行但无清晰峰；口径获数据支持但迁移下 nc 非清晰定值
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS2 "设全局固定nc（如5）重跑，对比自动定簇与固定簇数下§九结论差异"`

**[AS3] [MAJOR-AUTO]** λ 为 MV 风险厌恶系数，基准 λ=1
- 假设内容：λ=MV优化风险厌恶系数，仅用于CPMM-MV，基准1，敏感性测{0.25,0.5,1,2,4}
- 依据：表7 仅 CPMM-MV 有 λ 组
- 验证后回看：SA3 实测 λ 稳健（SR 0.856-0.962，base λ=1 非最优反略低）；CPMM-MV hs300 SR 0.9297；假设获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS3 "MV改用协方差收缩估计替代λ风险厌恶权衡，对比集中度是否缓解"`

**[AS4] [MAJOR-AUTO]** 组合月度调仓
- 假设内容：按月度再平衡，信号 T 月末算、T+1 月执行
- 依据：宏观月频 + OLPS 序贯；无绝对占优解释
- 验证后回看：月度调仓全链运行，hs300 CPMM-EW 调仓 70 期；T 定 T+1 执行序贯自检通过；口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS4 "切换为日频调仓重测，对比换手成本与净值路径差异"`

**[AS5] [MAJOR-AUTO]** 主回测不计交易成本，另设含成本稳健性
- 假设内容：主回测无摩擦；另设A股双边成本约千2一档
- 依据：原文仅提流动性+无冲击假设，未给费率
- 验证后回看：无摩擦主回测 CPMM-EW hs300 cum 194.4%，含成本40bp档已产出对比；换手影响小的预期获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS5 "提高成本档至80bp重测，验证结论方向是否反转"`

**[AS6] [MAJOR-AUTO]** 训练定窗口/测试评估划分
- 假设内容：训练段仅定 pattern-matching 最优窗口 w 与子簇 nc；指标算在测试段
- 依据：原文明示训练段用途为定 w
- 验证后回看：训练2007-2018定w=7/nc=10、测试2019-2024评估；扰动训练截止日提前一年SR 0.7168→0.5215（27.25%）证训练段确用于定参
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS6 "把训练段一并纳入评估区间，对比指标是否被训练期虚高"`

**[AS7] [MAJOR-AUTO]** 两套 pattern-matching 分工不同阶段
- 假设内容：Remark2（相关性+MSE）训练期定 w/nc；Matrix Profile 测试期两阶段检索/生成信号
- 依据：二者用途在文本中可分
- 验证后回看：分工落地，信号覆盖86-89%（全72月口径）；分工口径获数据支持（w train-once，SA3 w脆弱）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS7 "合并两套机制为单一预测流程，对比信号质量差异"`

**[AS8] [MAJOR-AUTO]** 时点成分股防幸存者偏差
- 假设内容：股票池用指数时点成分股（in_date/out_date 动态进出）
- 依据：A股本地支持时点成分；防未来函数为项目硬约束
- 验证后回看：member 时点成分过滤生效，hs300 CPMM-EW 月均在仓 3.31 只（过滤大量训练期入选但调仓已非成分股）；时点成分口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS8 "改用当前成分股全集回溯，对比幸存者偏差对夏普的抬升幅度"`

**[AS9] [MAJOR-AUTO]** 无硬阈值，按 |Δβ| 排序取显著头部
- 假设内容：不设阈值，按 |Δβ| 从大到小取显著头部前 N=50（不足则全取）
- 依据：spec"stocks with the highest absolute values of Δβ"直接支持
- 验证后回看：候选按|Δβ|取显著头部，hs300 40只/sz50 50/zz500 50，Δβ>0主导；排序取头部口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS9 "设显式|Δβ|硬阈值（如0.1）过滤，对比候选池规模与质量变化"`

**[AS10]** Matrix profile 子序列长度
- 假设内容：宏观stage m=最近一年（=12期）；资产stage m=最优窗口w
- 依据：spec明示宏观stage"最近一年"
- 验证后回看：宏观 stage m=12月、资产stage m=w（7/9/9），信号产出正常
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS10 "宏观stage m改为6或24个月，对比经济周期匹配质量"`

**[AS11] [MAJOR-AUTO]** MV 用经典 Markowitz 长仓
- 假设内容：wᵢ≥0, Σw=1无卖空，协方差样本内滚动窗口，目标 max wᵀμ−λwᵀΣw
- 依据：与F1单纯形约束一致；A股融券受限
- 验证后回看：MV长仓满仓运行，CPMM-MV hs300 SR 0.9297/cum 560%（集中度高致累计畸高）；长仓口径获数据支持，MV累计偏高的观察见AS56
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS11 "加协方差收缩或改风险平价目标，验证集中度畸高是否可缓解"`

**[AS12] [MAJOR-AUTO]** Diebold-Yilmaz 默认设置（p 按 AIC，U=10）
- 假设内容：VAR阶数p按AIC选（上限4），U=10，滚动窗口（DY2012默认）
- 依据：原文只给公式框架，沿用DY2012通行默认
- 验证后回看：VAR p=3（AIC，144月）、U=10，溢出表train-once产出；R4 CPI三市场前二对±1年训练窗稳健
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS12 "固定p=1或改U=5重测，验证溢出排名对p/U的敏感性"`

**[AS13]** 表5 SR 笔误按自算处理
- 假设内容：表5异常SR视为小数点笔误，复现SR一律自算
- 依据：多数单元格SR≈AR/AStd可对上，唯EWMFM列异常
- 验证后回看：SA2重算SR未采信原表异常值，尾窗三市场自洽
- Revise 指引：无需修改（纯笔误判定，非方法论选择）

**[AS14]** 表7 nc+1 表头修正
- 假设内容：CPMM-EW nc组第4列表头"nc−1"应为"nc+1"，按对称结构实现
- 依据：与w组、λ组的±1/±2对称结构一致
- 验证后回看：SA3 nc按nc−2..nc+2对称实现，base nc=10复现m6基准（Δ=0）；表头修正仅表头不改方法
- Revise 指引：无需修改（纯笔误判定）

**[AS15] [MAJOR-AUTO]** Δβ 双区制显著性口径：频率适配 α=0.10 + 窄池回退梯度（planner 定向裁决修订版）
- 假设内容：主口径（Tier1）α=0.10双系数；窄池回退（Tier2，候选<15触发）α=0.10单系数；仍<6则诚实排除该市场
- 依据：原文5%@日频（约6000观测）与本案月频（约144观测）应求统计行为等价而非阈值数值等价；实测单系数显著率≈8.9%/9.4%（>随机5%）证明月频下确有真实信号被5%双系数过度剔除；拒绝"宏观前填到日频"的伪复制捷径
- 验证后回看：α=0.10候选恢复可聚类规模（hs300 40/sz50 50/zz500 50，非退化）；tier落点hs300/zz500=Tier1、sz50=Tier2_degraded；候选Δβ>0主导支持R3下行保护；α=0.10使方法在A股可落地（§九是否依赖α放宽归diagnoser，本次结论已在§六交代）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS15 "改回全市场统一5%双系数显著性，对比候选池坍缩（hs300 10/sz50 1/zz500 21）对§九消融与基准结论的影响"`

**[AS16]** BorutaShap 在中国宏观候选池重选
- 假设内容：用BorutaShap（RandomForest基模型，训练段样本）在中国候选池重选；依赖不可用退化为直接采用可得对应集
- 依据：已选7因子是美国BorutaShap结果，不可直接迁移
- 验证后回看：shap不可用退化直采7因子（CPI/PPI/GDP/IP/M2/PMI/IR），因子集稳定全链参与；退化直采口径获数据支持（溢出加权自动弱化低溢出因子）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS16 "环境装shap后切换BorutaShap主路径重跑，对比因子集是否与直采7因子一致"`

**[AS17] [MAJOR-AUTO]** 纯长仓，FS 用于选股不做空
- 假设内容：FS_j仅用于每簇选FS最高资产排序；选中资产EW/MV长仓建仓；FS≤0不选入
- 依据：F1单纯形约束bₜ≥0；A股融券做空受限
- 验证后回看：纯长仓每簇选FS>0，建仓权重和=1.0000满仓；FS≤0剔除守卫违例=0；纯长仓口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS17 "改为多空口径（signal=-1做空），对比风险收益特征与原文长仓版本差异"`

**[AS18]** 发表日期 2025 占位
- 假设内容：report_date=2025-01-01占位，据引文年份推断
- 依据：封面无日期
- 验证后回看：仅frontmatter元信息，不影响任何复现产物
- Revise 指引：无需修改（不影响复现结果）

**[AS19]** rf 用短端市场利率按频率折算
- 假设内容：rf用A股市场短端利率，按调仓频率折算，非rf=0
- 依据：原文"risk-free return within the market"
- 验证后回看：rf非0（具体源见AS32/AS36落地），SR/SOR/MR excess口径生效
- Revise 指引：无需修改（口径落地细节见AS36）

**[AS20]** MI/SU 中连续变量熵的估计方法
- 假设内容：分箱离散化估熵/MI，分箱数sqrt(N)或10箱
- 依据：分箱估计实现简单稳定，常见默认
- 验证后回看：SU分箱估熵产出供聚类；但迁移下SU结构弱（silhouette≤0.065，AS48），分箱口径运行正常、结构信号微弱为迁移事实
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS20 "改用核密度或最近邻(Kraskov)估计器，验证是否能改善SU结构强度"`

**[AS21]** 滚动第三区间取满 4 年
- 假设内容：三滚动区间取等长4年，A股下按测试段平移
- 依据：原文明说"4-year periods"
- 验证后回看：SA1三窗2019-2022/2020-2023/2021-2024等长4年、1年滚动；第三区间取满4年口径获数据支持
- Revise 指引：无需修改（纯笔误对齐判定）

**[AS22]** PSR 基准 SR*=0
- 假设内容：PSR检验基准SR*=0
- 依据：SR*=0为PSR最常见默认
- 验证后回看：PSR用SR*=0，hs300 CPMM-EW PSR 0.9595；默认口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS22 "试非零SR*基准，对比PSR整体压低幅度"`

**[AS23]** 累计收益自产曲线，R5 近似定性对齐
- 假设内容：复现自产累计收益曲线，R5用文中近似值定性对照，不追平数值
- 依据：属"研报未提供表格值"而非解析失败
- 验证后回看：CPMM-EW hs300 194%/CPMM-MV 560% 对照原文≈110%/75%；近似定性对照口径获数据支持
- Revise 指引：无需修改（数值豁免范围内）

**[AS24]** 图15 描述笔误按自算
- 假设内容：图15单因子敏感性SR描述矛盾视为笔误，SA4复现自算
- 依据："largest losses"却给更高SR，自相矛盾
- 验证后回看：SA4自算（member过滤后）：仅用PMI SR 1.167最强单因子，剔除任一因子SR均不降；自算口径获数据支持
- Revise 指引：无需修改（纯笔误判定）

**[AS25]** 表3 判读精度不逐格对齐
- 假设内容：接受spec表3转写值作参考，市场迁移下重算不逐格对齐
- 依据：表3密集小字存图像判读风险
- 验证后回看：SA1重算未采信原表尾数；判读精度不影响结论
- Revise 指引：无需修改（数值对齐豁免范围内）

**[AS26]** 表3 重复值视为录入误差
- 假设内容：表3多格重复数值视为研报可能录入错误，复现自算不采信
- 依据：不同4年期出现多处相同数值，疑复制粘贴错误
- 验证后回看：SA1自算未采信原表重复值
- Revise 指引：无需修改

**[AS27]** SA6 TDA 略过复现
- 假设内容：TDA参数（ε/持续同调维度/异常阈值）原文未给且optional，判skip
- 依据：仅定性结论无量化基准，SA6为optional
- 验证后回看：SA6 skip未复现，TDA参数原文未给；optional略过确认
- Revise 指引：若需复现，须自行设定ε阈值与持续同调维度（原文未给，需自定），非本次范围

### 3.2 市场迁移替代（AS28-AS34，性质 market-transplant）

**[AS28] [MAJOR-AUTO]** 股票池市场迁移映射
- 假设内容：S&P500→沪深300（主分析）；DowJones→上证50；Nikkei225→中证500，均用时点成分股前复权行情
- 依据：沪深300=A股最具代表性大盘宽基对标S&P500主分析地位；上证50对标DJI；中证500对标N225
- 验证后回看：三独立市场全跑通、R全产出；A股结构不同致效应变化（CPMM-EW SR 0.72/0.60/0.59 vs 原文1.32/1.09/1.88），迁移底座成立、数值豁免
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS28 "改用沪深300全A股或中证800作单一映射市场，去掉三宽基对标结构做单市场深度验证"`

**[AS29] [MAJOR-AUTO]** 宏观因子集市场迁移映射
- 假设内容：FRED美国宏观→中国等价（CPI/PPI/GDP/IP/IR + 补充M2/PMI），BorutaShap从此候选池重选
- 依据：这些指标在中国有直接可得的官方月频对应
- 验证后回看：中国7因子全链参与，R4溢出/选股产出；选出因子集与溢出排序确与原文不同（IR三市场垫底 vs 原文次强）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS29 "补充社融/信贷脉冲等候选因子扩大候选池，重跑BorutaShap对比因子集是否改变"`

**[AS30] [MAJOR-AUTO]** UR 失业率据实降维剔除（不强代理）
- 假设内容：美国UR本地无任何干净月频等价物，据实从候选池降维剔除，不用PMI等强行代理
- 依据：实验模式规则"本地完全无等价物的因子据实登记降维、不得虚构数据"；中国城镇调查失业率历史短（2018后才公布）
- 验证后回看：UR降维未代理，因子集较原文少一维（7因子）；据实降维口径获数据支持（方法仍成立，未因缺UR失效）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS30 "若城镇调查失业率序列后续可得，纳入重跑验证R4/SA4关键因子结论是否改变"`

**[AS31] [MAJOR-AUTO]** DGDP 债务/GDP 替代（社融/M2 代理）
- 假设内容：本地无直接对应，用社融存量同比或M2/GDP比率作宏观杠杆代理，或从候选池剔除
- 依据：中国政府债务/GDP月频序列本地缺失；社融/M2反映宏观杠杆与信用扩张
- 验证后回看：DGDP维度经AS35据实剔除社融、由M2承载信用维度（γ̃ hs300 M2=0.935平稳）；剔除口径落地，迁移等价性风险记录在案
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS31 "用社融存量/GDP比率重新纳入DGDP维度（做winsorize处理波动），对比信用维度是否更完整"`

**[AS32]** rf 无风险利率市场迁移映射
- 假设内容：美国T-bill→中国SHIBOR 3M或短端国债，按调仓频率折算
- 依据：A股无风险利率惯用SHIBOR/短端国债
- 验证后回看：SHIBOR/短端国债不可得，改10Y国债（见AS36）月均0.002315；rf水平影响绝对值不改排序获数据支持
- Revise 指引：无需修改（口径落地细节见AS36）

**[AS33]** 指数基准市场迁移映射
- 假设内容：三大指数买入持有基准+Modigliani σ_b → 对应A股宽基指数点位
- 依据：与股票池映射（AS28）一一对应
- 验证后回看：A股宽基点位作Index基准，hs300 Index买入持有SR 0.132产出；基准与股票池一致口径获数据支持
- Revise 指引：无需修改

**[AS34] [MAJOR-AUTO]** 回测区间市场迁移调整
- 假设内容：原文1995-2023（训练至2018）→A股全样本约2007-2024，训练2007-2018定w/nc，测试2019-2024
- 依据：A股个股行情2000起、沪深300成分2005后趋稳
- 验证后回看：测试段CPMM-EW hs300 69期（预热损~3）；SA1滚动4年窗/SA2尾窗2023-2024平移、扰动训练截止提前一年止2017；A股区间划分获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS34 "训练窗改为2010起（更短历史但避开2007-08金融危机异常波动），对比结论稳健性"`

### 3.3 m1 落地补登（AS35-AS40）

**[AS35] [MAJOR-AUTO]** DGDP 维度降维（社融各口径不平稳，剔除 SF）
- 假设内容：社融各可得口径月度同比因早期小基数剧烈波动（直接融资累计同比|Δ|达926），据实剔除，货币信用维度由M2承载
- 依据：AS31明示社融代理或剔除二选一；不平稳因子入Δβ会扭曲区制回归
- 验证后回看：社融剔除、候选池7因子，M2承载信用维度（γ̃ hs300 M2=0.935平稳）；据实剔除口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS35 "对社融总量同比做winsorize后重新纳入候选池，对比是否改善DGDP维度表达"`

**[AS36]** rf 与 IR 因子改用 10Y 国债收益率
- 假设内容：bond_shibor/bond_yield_curve历史覆盖不足回测区间，rf与宏观IR因子统一改10年期国债收益率
- 依据：10Y国债是覆盖最长的市场基准利率
- 验证后回看：rf/IR用10Y国债，rf月均0.002315；IR因子溢出三市场垫底——长端替代短端致IR溢出弱，与原文短端IR次强口径有别属迁移必然
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS36 "若SHIBOR/短端国债历史数据补齐，切回短端重测IR溢出排名是否改变"`

**[AS37] [MAJOR-AUTO]** 宏观披露日"合理性检验 + 保守滞后 fallback"对齐
- 假设内容：真实披露日质量参差时，仅当 date<info_publ_date≤date+90天 时采信真实披露日，否则回退到典型滞后估计
- 依据：防未来函数硬约束要求宁可保守延后
- 验证后回看：宏观按披露日asof对齐，全链无未来函数（扰动端点错位正确）；保守滞后口径获数据支持（安全侧无前视）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS37 "若确认某指标真实披露日更可靠，放宽PUBL_LAG_CAP_DAYS重测信号时点提前量"`

**[AS38]** F12 BorutaShap 依赖不可用 → 退化直采候选全集
- 假设内容：shap不可用致BorutaShap不可用，退化为直接采用7个候选因子全集
- 依据：AS16明示依赖不可用则退化直采
- 验证后回看：shap缺退化直采7因子（CA-CDX-C-02订正后仅ImportError走降级），因子集稳定
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS38 "环境装shap后切换BorutaShap主路径，对比是否从7因子中筛出更小子集"`

**[AS39] [MAJOR-AUTO]** 宏观因子逐口径登记与 change_panel 口径感知构造（落地 CA-A01）
- 假设内容：7因子逐一登记同比口径（当期/累计/水平/市场即时），change_panel在报告期层面口径感知构造，避免累计跳变/季内恒0污染
- 依据：累计同比年初口径切换是机械跳变而非真实经济加速度，剔除断点是宏观时序处理惯例
- 验证后回看：7因子口径感知change落地，Δβ分区未被累计跳变污染，候选Δβ>0主导；口径统一获数据支持（GDP月度信号稀疏为已知限制）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS39 "IP改用累计同比口径而非当期填充版，对比change断点处理差异对Δβ的影响"`

**[AS40]** PMI 保守延后 1 月与 F12 训练窗对齐登记
- 假设内容：PMI披露日与报告期同为月末，合理性检验拒绝同日披露，保守延后约1月；F12训练窗显式加下界2007-01
- 依据：未来函数硬约束下宁可保守延后
- 验证后回看：PMI保守延后安全侧，F12训练窗下界2007；不改数值结果，PMI延后不引入前视
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS40 "若确认PMI月末当日可用，放宽为同月对齐，对比信号时点提前的影响"`

### 3.4 m2 落地补登（AS41-AS44）

**[AS41]** Δβ 双区制每区制最小观测门槛 24 月 + 头部规模 N=50 落地
- 假设内容：X>0/X<0各设MIN_REGIME_OBS=24月最小观测门槛，头部规模N=50（不足全取）
- 依据：plan预警月频双区制自由度可能不足
- 验证后回看：min_obs=24/N=50落地，候选hs300 40/sz50 50/zz500 50；门槛参数获数据支持（未因门槛致候选退化）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS41 "min_obs改为12或36重测，对比候选池规模与统计有效性权衡"`

**[AS42] [MAJOR-AUTO]** Δβ 训练期一次性估、测试固定候选集
- 假设内容：仅用[2007-01,2018-12]估双区制β⁺/β⁻，测试期完全不进入估计，候选集固定供下游复用
- 依据：原文明示训练段用于定pattern-matching窗口、样本外评估
- 验证后回看：Δβ train-once仅用2007-2018，测试不进入估计；扰动训练截止提前一年SR变27.25%证train-once耦合训练输入
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS42 "改滚动/扩展窗口重估Δβ，对比候选集稳定性与是否纳入更多样本外新股"`

**[AS43] [MAJOR-AUTO]** 月频迁移 5% 双系数功效不足 → 已裁决频率适配 α=0.10 + 窄池回退（发现升级为已裁决）
- 假设内容：忠实实现5%双系数后发现候选极稀少（hs300 10/sz50 1/zz500 23对），根因为月频观测数暴跌致OLS检验功效下降；裁决为AS15的频率适配方案
- 依据：频率迁移必然统计后果，正确响应是频率适配α（原则性），非放宽阈值掩盖也非前填灌n
- 验证后回看：α=0.10候选恢复可聚类（hs300 40/sz50 50/zz500 50），m3-m6全链非退化；频率适配裁决使方法在A股落地获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS43 "对比α=0.05/0.10/0.20三档下游§九结论一致性，形成正式敏感性表判断结论稳健区间"`

**[AS44] [MAJOR-AUTO]** sz50 窄基指数在月频迁移下选股降级（market-transplant 结果）
- 假设内容：上证50为窄基指数（约50成分），月频Δβ双区制功效尤其不足，标注为degraded市场（Tier2单系数回退）
- 依据：窄基指数成分少→显著性筛选后可选样本天然稀薄，是市场结构导致的迁移降级
- 验证后回看：sz50实际落Tier2_degraded（单系数α=0.10），候选50只未退出主分析；CPMM-EW sz50 SR 0.5982排名2/11，degraded不动摇hs300主轴
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS44 "将sz50换为更宽基准（如中证100）重测，验证窄基降级现象是否消失"`

### 3.5 m3/m4 落地补登（AS45-AS51）

**[AS45]** sklearn 依赖不可用 → 聚类四模型全 numpy 自实现
- 假设内容：sklearn缺，hierarchical用scipy、其余（Silhouette/K-means/GMM/DBSCAN）全numpy自实现，固定种子42
- 依据：任务明示依赖退化授权；标准算法可numpy复现
- 验证后回看：聚类四模型numpy自实现，三市场8配置全ok无limited；自实现口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS45 "环境装sklearn后交叉验证自实现与官方数值一致性"`

**[AS46] [MAJOR-AUTO]** 层次聚类连接法取 ward（spec 未指定 linkage）
- 假设内容：取ward（sklearn默认），因average连接在弱结构下退化为逐点剥离离群点
- 依据：ward为凝聚聚类通行默认；average-linkage单点剥离是弱/噪声数据已知病态
- 验证后回看：ward产平衡簇（nc=10各簇非单点），供m5每簇选一；ward口径获数据支持（避average单点剥离）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS46 "切换average或complete连接法对比，验证是否产生单点簇退化"`

**[AS47]** 聚类辅助口径：相关→距离/kmeans·gmm MDS 嵌入/medoid 代表/R2 迷你评估
- 假设内容：Mantegna相关距离、MDS_DIM=5嵌入、medoid簇代表、R2用rf=0统一评估
- 依据：Mantegna相关距离为资产聚类标准；MDS嵌入让kmeans/gmm良态
- 验证后回看：相关距离/MDS嵌入/medoid/R2迷你评估落地，R2四模型×两度量产出
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS47 "调整MDS_DIM或改用其他嵌入方法，对比R2数值稳定性"`

**[AS48] [MAJOR-AUTO]** 迁移发现：SU 聚类结构在 A股月频极弱、nc 触搜索上界、hier+SU 非占优
- 假设内容：三市场canonical silhouette全≤0.065，远低于0.25"有实质结构"门槛；SU在A股月频信号微弱
- 依据：实验模式要求如实报告方法可迁移性；silhouette<0.1是"无实质簇结构"通行判读
- 验证后回看：三市场silhouette≤0.065弱结构证实，nc触上界10；§九.2消融hs300/zz500去聚类PMM未劣于CPMM-EW——聚类环节在A股月频增量存疑获数据支持（如实报告）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS48 "改用相关系数替代SU作为聚类关系度量，验证聚类结构强度是否改善"`

**[AS49]** stumpy 依赖不可用 → 自实现 Z-归一化欧氏 matrix profile（退化）
- 假设内容：stumpy不可用，F6按定义自实现（d²=2m(1−ρ)与Pearson严格对应）
- 依据：Z-归一化欧氏MP定义唯一、可numpy精确复现
- 验证后回看：Z-归一化MP自实现，信号产出；退化只改实现来源不改方法本质
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS49 "环境装stumpy后交叉核对自实现数值一致性"`

**[AS50]** F5 定窗口 w；聚类簇数 nc 归 m3 权威，m4 不重复搜聚类 nc
- 假设内容：并行分工——m3 Silhouette权威定聚类nc，m4 F5专注定pattern-matching窗口w
- 依据：nc与w为不同参数，权威定义分工避免重复搜索
- 验证后回看：w=7/9/9定值，SA3 w脆弱（w=8骤降）；nc归m3不重搜；分工口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS50 "让m4也独立搜索nc，对比是否与m3结果一致"`

**[AS51] [MAJOR-AUTO]** 两阶段匹配历史区间口径 + 未来函数硬约束
- 假设内容：阶段1宏观周期候选窗口严格更早不重叠；阶段2历史价格窗口之后一期严格早于信号月；NaN不强制−1
- 依据：未来函数硬约束要求历史匹配窗口严格早于信号月
- 验证后回看：两阶段EP不重叠、之后一期严格早于信号月，信号NaN按缺失剔除；未来函数整数位置索引硬约束获数据支持（独立核验来源严格早于信号月）
- Revise 指引：无需修改（未来函数红线约束，建议只做更大规模抽查扩展验证而非改动逻辑）

### 3.6 m5 落地补登（AS52-AS55）

**[AS52]** statsmodels 依赖不可用 → 自实现 VAR（多元 OLS）+ 广义 FEVD（退化）
- 假设内容：statsmodels不可用，VAR/AIC定阶/Wold系数/Pesaran-Shin GFEVD全部numpy自实现
- 依据：依赖退化授权同AS38/45/49；VAR多元OLS与Pesaran-Shin GFEVD定义唯一
- 验证后回看：自实现VAR多元OLS+广义FEVD，合成VAR核对健全、GFEVD行和=1非负对角最大；退化闭式解口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS52 "环境装statsmodels后切换官方VAR实现对比数值"`

**[AS53] [MAJOR-AUTO]** 溢出输入序列迁移：宏观 change_panel + 指数月收益（月频收益/变化广义溢出）
- 假设内容：原文波动率溢出因缺日频接口无法算，改用月频宏观变化+指数月收益的广义（Diebold-Yilmaz）溢出代理
- 依据：DY框架对收益/波动率均适用；月频无日内RV时用收益/变化序列是标准降级
- 验证后回看：月频change+指数收益广义溢出，R4 to_index CPI三市场前二，量级0.75-5.1远小于原文0.3-319（仅比较相对排名）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS53 "补充日频接口算月内已实现波动率RV，改用真正波动率溢出口径重跑R4"`

**[AS54] [MAJOR-AUTO]** 溢出 γ̃ 估计窗口口径：训练期一次性估（train-once，最防泄漏）
- 假设内容：γ̃只用[2007-01,2018-12]估VAR/GFEVD，测试期完全不进入估计，全链train-once哲学一致
- 依据：估计窗⊆训练期是防未来函数最保守选择
- 验证后回看：γ̃ train-once仅用≤2018，零测试泄漏；扰动训练截止提前一年SR变27.25%证train-once耦合训练；最防泄漏口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS54 "切换滚动窗口估计γ̃，对比R4排序时变稳定性"`

**[AS55] [MAJOR-AUTO]** 溢出测度选择（net vs 方向）+ γ̃ 归一化退化 + FS 聚合/每簇选一落地
- 假设内容：三测度并存解决spec口径矛盾——to_index（表6/R4主强度）、net_spillover（FS权重基）、system_net（审计留档）
- 依据：表6全正值+"from factor to index"指向方向份额，F10又明写"净溢出"权重，二者并存是对spec内部矛盾最忠实的处理
- 验证后回看：to_index（R4强度）与net（FS权重）并存，R4用to_index CPI前二、FS权重net下PMI权重最大；每簇选一守卫违例=0；测度并存口径获数据支持
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS55 "FS权重改用to_index非负份额而非net，对比选股集与§九消融结论变化"`

### 3.7 m6 落地补登（AS56-AS58）

**[AS56] [MAJOR-AUTO]** EW/MV 建仓 + 回测/换手/成本 + 指标算术年化口径 + R1 加粗方向
- 假设内容：EW等权、MV长仓λ=1协方差≤T扩展窗；建仓前member∩tradeable过滤；T定T+1执行；算术年化使SR自洽；R1加粗按方向感知（风险类取最小）
- 依据：≤T扩展窗协方差/期望是防未来函数最保守选择；算术年化使风险比率表内自洽是绩效评估惯例
- 验证后回看：MV λ=1集中度致CPMM-MV hs300累计560%畸高（SA3λ稳健）；独立复算SR/AR/累计三路径abs_diff=0；MR系统性偏低（0.168 vs SR 0.717，A股基准σ_b量级不同，已知口径差异非计算错误）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS56 "MV协方差窗口改用固定60月滚动而非扩展窗，验证集中度畸高是否缓解"`

**[AS57] [MAJOR-AUTO]** 消融链三模型确切实现（CPM 去宏观 / PMM 去聚类 / EWMFM 去溢出加权）
- 假设内容：CPM关掉阶段1宏观周期筛选（全历史匹配）；PMM保留宏观+溢出但不分簇（全候选top-nc）；EWMFM保留聚类+宏观但FS等权聚合
- 依据：消融实验的方法论纯粹性要求每模型只改一个环节、其余复用
- 验证后回看：CPM去宏观/PMM去聚类/EWMFM去溢出单变量隔离落地；hs300 CPMM-EW(0.717)>CPM-EW(0.550)/EWMFM(0.580)方向对齐，但PMM(0.770)未降反升（对齐AS48）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS57 "PMM改为单簇选1只而非top-nc只，重测去聚类环节的隔离效果"`

**[AS58] [MAJOR-AUTO]** 外部基准五模型实现（Index / HRP / HERC / NCO / OLMAR）
- 假设内容：同候选池同区间下各基准标准实现；OLMAR均值回归x̃=SMA(w)/p_t，含code_audit修正方向反转bug
- 依据：HRP/HERC/NCO/OLMAR均有标准算法定义；同候选池对比才公平隔离"配置方法"变量
- 验证后回看：Index/HRP/HERC/NCO/OLMAR同候选池运行，hs300 CPMM-EW(0.717)>Index(0.132)/HRP(0.611)/HERC(0.620)/NCO(0.550)；OLMAR修均值回归后0.746局部高于CPMM-EW
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS58 "调整OLMAR窗口/ε或NCO簇数，对比基准表现敏感性"`

### 3.8 m7 落地补登（AS59-AS63）

**[AS59]** SA1 滚动 4 年子区间市场迁移平移（切已实现收益子窗重定基）
- 假设内容：三滚动区间平移为2019-2022/2020-2023/2021-2024（等长4年、1年滚动），切base已实现收益重定基而非重跑全链
- 依据：策略参数全部train-once不随评估子窗重估，子区间稳健性=同一策略在不同评估窗表现
- 验证后回看：三窗切base已实现收益、窗内重定基；CPMM-EW非稳定全胜（hs300逐窗2/10→3/10→7/10）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS59 "改用不同滚动步长（如2年）重测子区间稳健性"`

**[AS60] [MAJOR-AUTO]** SA2 样本外尾窗 2023-2024（与后续 oos 阶段区分）
- 假设内容：测试段尾窗2023-2024（24月）作研报内样本外稳健性表，与后续oos阶段（2024之后延伸）明确区分
- 依据：原文OOS为主测试之后尾段；A股测试段仅至2024
- 验证后回看：尾窗hs300 CPMM-EW SR转负−0.3547，样本外衰减征兆与后续oos阶段结论一致（详见§十）
- Revise 指引：无需修改（已被oos阶段承接验证，结论方向一致）

**[AS61] [MAJOR-AUTO]** SA3 参数敏感性实现（nc/w/λ 各 ±2；base 三路径逐值复现校验）
- 假设内容：主市场hs300对nc/w/λ各±2共5点敏感性；base参数下三路径须逐值复现m6基准作正确性校验
- 依据：复用不受某参数影响的上游产物+只重算受影响环节是敏感性分析标准做法
- 验证后回看：base三路径Δ=0；w脆弱（w=7→8 SR 0.7168→0.4492，−37%）、λ稳健（0.856-0.962）、nc中等（nc=8反高0.9486）
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS61 "扩大w网格至±4，验证w=8骤降是局部异常点还是趋势性拐点"`

**[AS62] [MAJOR-AUTO]** SA4 单因子纳入/剔除实现（因子子集 FS 重聚合；仅用因子 γ̃≡1 隔离信号）
- 假设内容："仅用f"用γ̃≡1隔离信号价值（避免min-max γ̃=0退化）；"剔除f"用base γ̃其余6个
- 依据：单因子下FS符号=signal符号（γ̃_f>0时），仅用因子取等权更贴"using only one factor"语义
- 验证后回看：member过滤后baseline_SR=0.7168：仅用PMI SR 1.167最强单因子，剔除任一因子SR均不降（组合不依赖任一单因子），原文CPI/IR在A股未迁移成立
- Revise 指引：`/reproduce revise ssrn_6115073 --assumption AS62 "剔除因子场景也改用等权而非base γ̃，对比归因结论是否稳健"`

**[AS63] [MAJOR-AUTO]** SA 建仓与 R1 同口径 member∩tradeable 时点过滤（承接 m6 CA-CDX-C-01）
- 假设内容：m7 robustness的建仓补传member_mask，使SA1-4与R1主结果同口径（member∩tradeable），非仅tradeable
- 依据：code_audit发现m6建仓漏member时点过滤（CDX-C-01），m7须同步修正保持口径一致
- 验证后回看：member∩tradeable过滤使月均建仓~3只，SA与R1同口径；base三路径逐值复现member过滤后m6新基准（Δ=0），证补口径重跑同构无偏
- Revise 指引：无需修改（这是code_audit修复后的权威口径，是本报告全部结论的基线，不应回退到修复前的tradeable-only口径）

---

## 四、迭代历史摘要

**本案无迭代循环。** `workspace/ssrn_6115073/iterations/` 目录存在但为空（无 `iteration_log.md`、无 `iter_NN/` 子目录），确认 quant-diagnoser 驱动的"迭代（iterate）"条件阶段从未被触发。

**流程实际路径**：init → extract → plan → spec_audit（codex `pass_with_issues` → 3 major 修复闭环）→ implement（m1-m7 逐里程碑，含 2 轮"code_audit-fix"内部修正周期，详见附录 A.4）→ code_audit（codex `fail` → 2 major 修复闭环）→ verify（`comparison.json` 直接 98/98 pass，无需 diagnoser 介入）→ result_audit（`pass_with_issues`，1 条 minor 文书卫生项）→ oos → report。

**为何未触发迭代**：迭代阶段的入口条件是 verify 后 `comparison.json` 存在未达标指标需要 quant-diagnoser 归因决策（continue/stop_partial/blocked 三选一）。本案 verify 阶段一次性产出 98/98 pass（experimental 口径），未出现任何 fail 指标，因此直接进入 result_audit，无需诊断循环。

**需与"迭代"区分的两类修正周期**（均发生在各自阶段内部，非独立 iterate 阶段，详见附录 A.4）：
1. **spec_audit 内部修复周期**：codex 盲提取外审 + 内审共 6 条意见（3 major + 3 内审），审→修→复审 1 轮闭环。
2. **implement 阶段的持续内部质量审计**（`impl_audit_m1-m7`）：quant-auditor 逐里程碑同步审计，发现的 major 问题（m1 宏观口径混用 CA-A01、m6 OLMAR 方向反转 bug CA-A01）均在实现阶段内近实时修复，未流入独立 iterate 循环。
3. **code_audit 内部修复周期**：codex 全代码外审发现 2 条 major（CDX-C-01/02），审→修→复审 1 轮闭环。

---

## 五、审计回应汇总（外部审查结论）

> 引自 `audit/audit_responses.md`（全量意见处置总表）。三个外部审查点（spec/code/result）**全部 engine=codex 真实执行**，无 `claude_fallback`、无因 codex 不可用而 `skipped` 的降级情形。

### 5.1 spec_audit（spec 审查点）

**codex 外部盲提取审查**（`spec_audit_codex.md`）：`checkpoint=spec`，`verdict=pass_with_issues`，3 条意见（全 major）。
**内审**（quant-auditor mode=spec，独立重算）：3 条意见（1 major / 2 minor）。

| 意见ID | severity | 摘要 | 处置 | 回应 | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | major | 表2(R1) PSR·DowJones·EWMFM 抄为 0.512，应为 0.521（列间错位） | accepted | spec.md:274 已订正 0.512→0.521；PDF p27 400dpi 图像终审确认判读正确 | pass |
| CDX-S-02 | major | 表3(SA1) 约 15 格数值错录（多行右移错位 + 个别单格） | accepted | spec.md 逐格订正共 16 格；PDF p28 图像终审确认，另新捕 1 格 codex 概述未及 | pass |
| CDX-S-03 | major | D2/TBL8 遗漏 BorutaShap 候选池完整 18 项宏观因子逐条登记 | accepted | spec.md:102（D2 说明）已补录完整 18 项全称+缩写；PDF p43 Table A.1 逐字核对 | pass |
| SA-A01 | major | 表2(R1) AStd·DowJones 末列错位（内审独立重算） | accepted | spec.md:268 已订正 4 格；PDF p27 终审确认内审判读正确（codex 盲提取此行漏捕） | pass |
| SA-A02 | minor | 表3(SA1) 2016-2020 AStd·S&P500·EWMFM 0.153 应为 0.154（内审） | accepted | spec.md:405 已订正（含在 CDX-S-02 的 16 格订正内） | pass |
| **SA-A03** | minor(confidence low) | F1 页码范围 p6-p8 下界略宽（内审） | **rejected** | 技术理由：非遗漏非幻觉，F1 三条引文均在 p8 命中，C6 页码抽查不受影响；p6 下界为提示性范围，维持原登记不订正 | pass |

**处置汇总**：CDX-S- 意见 3 条全 accepted 并回 PDF 图像终审订正落地；内审 3 条中 2 条 accepted、1 条（SA-A03）**rejected**（已给技术理由，见上表加粗行）；open critical=0，未回应 major=0，审→修→复审 1 轮闭环。

### 5.2 code_audit（code 审查点）

**codex 全代码外部审查**（`code_audit_codex.md`，read-only）：`checkpoint=code`，`verdict=fail`，2 条意见（全 major，无 critical）；5 维度覆盖（公式对照/未来函数/数据对齐/config vs B类/作弊排查K1/K5/K6）。

| 意见ID | severity | 摘要 | 处置 | 回应 | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-C-01 | major | 建仓仅用 tradeable_mask 未合并 member_mask，训练期入选但调仓月已调出指数的股票仍进组合，违 B1 时点成分股要求且与 AS56 声称不符 | accepted | `portfolio.py` 所有建仓入口（CPMM/CPM/PMM/EWMFM + HRP/HERC/NCO/OLMAR）已叠加 `selected ∩ member_mask[t] ∩ tradeable_mask[t]` 时点过滤；`robustness.py` 同口径补齐；**副产真实迁移事实**：持仓 ~9→~3 只 | pass |
| CDX-C-02 | major | `data_prep.py:436` F12 选因子用裸 `except Exception`→`degraded_all`，会把算法/数据/实现错误静默伪装成已登记依赖退化（K5 核心路径） | accepted | 收窄为仅 `(ModuleNotFoundError, ImportError)` 走授权降级；其它异常打印堆栈后 `RuntimeError` 重抛、不静默吞；结果 `degraded_all` 逐值不变，仅错误处理显式化 | pass |

**处置汇总**：2 条 major 全 accepted 并修复落地，open critical=0，未回应 major=0，审→修 1 轮闭环。`impl_audit_m1-m7` 无 `判定: not_found`（无空壳虚报）。**CDX-C-01 修复连锁改变 R1/SA 全部数值与 SA4 结论**——最终 verify 阶段已在修正后代码上重跑权威 R1/SA/comparison/证据链（即本报告全部引用数据的来源）。

### 5.3 result_audit（result 审查点）

**codex 外部审查**（`result_audit_codex.md`）：`checkpoint=result`，`verdict=pass`，**0 finding**（5 维度：归因量级推算/假设方向一致性/过于精确嫌疑K2/skip理由核实/结论措辞相符性，全部 `no_findings`）。

**内审反虚报复核**（quant-auditor mode=result，见 `evidence_manifest.md`）：`verdict=pass_with_issues`，1 条 finding（见 §六）。

### 5.4 遗留 rejected 意见闭环声明

`audit_responses.md` 中处置为 `rejected` 的意见共 **1 条**：**SA-A03**（F1 页码范围 p6-p8 下界略宽，内审 minor、confidence low）。该意见已在 5.1 表格中原样列出，拒绝理由为"非遗漏非幻觉，三条引文均在 p8 命中，C6 页码抽查不受影响"，经复核 pass，不构成遗留风险。

---

## 六、残余偏差与归因

> 措辞与数值严格引自 `verify_report.md`"最终验证（member 过滤后权威版）"小节"已知口径差异（不归因，仅陈述）"与 `comparison.json`，不新增判断、不重算。

### 6.1 已知口径差异（experimental 豁免范围内，非计算错误）

| 差异项 | 现象 | 说明 |
| --- | --- | --- |
| MR（Modigliani）系统性偏低 | 复现 MR（hs300 CPMM-EW 0.1683）远低于 SR（0.7168），原文 MR≈SR（1.313 vs 1.317） | MR=SR·σ_b+rf，A股基准指数月度 σ_b 与美/日市场量级不同致 MR 口径下压，属基准 σ_b 迁移差异，非计算错误（值确从净值算得，独立复算 abs_diff=0） |
| 累计收益量级差异 | CPMM-MV hs300 累计 560%（原文 S&P500 75%）；CPMM-EW hs300 194%（原文 110%） | A股测试期 2019-2024 与原文 2019-2023、市场 β 及集中度差异所致，experimental 豁免 |
| R4 溢出量级 | 复现 to_index 份额（0.7-5.1）远小于原文（0.3-319） | 口径 AS53（月频收益/变化广义 FEVD 份额）与原文波动率溢出绝对强度不同量级，仅比较相对排名 |
| 组合持仓集中（~3 只） | member 时点成分过滤后月均在仓大幅收窄（原每簇选一 ~9 只） | code_audit CDX-C-01 修复的必然结果（B1 时点成分股要求），非 bug |
| R3 组合层下行保护部分未显现 | hs300/zz500 组合层 β⁻ 为正（未呈原文全负特征），仅 sz50 呈现 | 候选个股级 Δβ>0 主导（下行保护选股逻辑迁移成立）与组合层收益回归结果为两个不同层级的观测，详见 §二.2 |

### 6.2 关键迁移发现（§九 判据输入，据实记录）

- **消融逻辑部分成立**：去宏观（CPM）、去溢出加权（EWMFM）两个环节增量方向三市场一致为正（CPMM-EW 优于二者）；**去聚类（PMM）环节增量在 hs300/sz50 未降反升**，仅 zz500 成立——聚类环节在 A股月频的增量价值存疑，呼应 AS48 的 SU 结构弱发现。
- **相对外部基准**：CPMM-EW 三市场 SR 全面领先 5 个外部基准（Index/HRP/HERC/NCO，OLMAR 除外——hs300 OLMAR 修复方向反转 bug 后 0.746 局部高于 CPMM-EW 0.717）。
- **参数敏感性**：**w（pattern-matching 窗口）脆弱**（base w=7→8 邻域 SR 骤降 37%）；**λ（MV 风险厌恶）稳健**（0.856-0.962 窄幅波动）；**nc（聚类簇数）中等敏感**（nc=8 反高于 base nc=10）。
- **SA1 滚动子区间**：CPMM-EW **非跨子区间稳定全胜**——hs300 排名逐窗走弱（2/10→3/10→7/10，2021-2024 掉队被 OLMAR/PMM 反超）；zz500 首窗垫底（9/10）后中后段升至第 1。
- **SA2 样本外尾窗（2023-2024，研报区间内）**：hs300 CPMM-EW SR 转负（-0.3547，6 内部设置多数为负=市场级弱）；sz50/zz500 CPMM 优势保持；**该尾窗衰减征兆与 §十样本外真实延伸（2025-2026）的失效结论方向一致，非孤立噪声**。
- **关键宏观因子迁移**：A股迁移下唯一"剔除后 SR 下降"的因子是 **PMI**（最强单因子）；原文核心结论"CPI/IR 最关键"在 A 股月频**未迁移成立**（CPI/IR 剔除后 SR 均升，非关键）；多数因子剔除后 SR 反升，宏观信号整体增量有限（组合不依赖任一单因子）。

### 6.3 反虚报复核发现（唯一 1 条，minor，已披露不构成阻断）

**RA-01**（minor，`output/ssrn_6115073/verify_report.md:515-565` vs `:644`）：verify_report 里程碑 m6/m7 段落保留旧 tradeable-only 口径数字（如 m7 段 SA4"PMI 剔除后 ΔSR −0.0610→最关键"），与最终权威段（"PMI 剔除 +0.099、剔除任一 SR 不降=不依赖单因子"）及全部权威产物结论相反乃至翻转。已由权威段表头"以下数字取代上文里程碑旧口径"及 coverage_matrix 变更日志显式披露，权威产物内部自洽零偏差，**非数字不实/非造假，属文书卫生**——下游若误引 m7 旧段落可能传播相反结论，不阻断。**本报告全文口径统一以"最终验证（member 过滤后权威版）"小节与 comparison.json 为准，不引用里程碑旧段落数字**，已规避该风险。

---

## 七、未复现清单

> `coverage_matrix.md` 中 skipped/infeasible 要素全量列出（无 pending/in_progress 残留）。

| 要素ID | 类别 | 描述 | 优先级 | 状态 | 理由 |
| --- | --- | --- | --- | --- | --- |
| SA5 | SA | 附录G 扩展相似性 ES（次相似模式对比 ESCPMM-EW/MV） | optional | skipped | `out_of_scope`——optional 次相似变体，非主结论，市场迁移聚焦主方法是否成立 |
| SA6 | SA | 6.1节 TDA 拓扑异常分析（IR/CPI/UR 异常与危机对齐） | optional | skipped | `method_underspecified`——TDA ε 阈值/持续同调维度/异常判定阈值原文未给，optional 补充定性分析，关联歧义 A27/假设 AS27 |

**skip 理由核实结论**（引自 `evidence_manifest.md` 反虚报复核）：核对 `data_catalog` 与 spec 原文，"无 skip/infeasible 理由不成立（非'本可衍生却偷懒'）"——SA5 属研报本身的次要变体，SA6 的 TDA 参数原文确未给出量化基准，均为设计内合理裁剪。**本案 0 项 core/support 要素 skip，2 项 skip 全部落在 optional 层**，不触发覆盖率评级降档（详见附录 A.1）。

---

## 八、复跑指引

### 8.1 环境

- `uv run python`（`.venv` 虚拟环境），项目根 `/Users/hedi/report_reproduce`
- 已知依赖降级（均已登记且经独立复算验证数学健全，非缺陷）：本地环境缺 `sklearn`（聚类四模型自实现，AS45）、`stumpy`（Matrix Profile 自实现，AS49）、`statsmodels`（VAR/GFEVD 自实现，AS52）、`shap`（BorutaShap 退化为直采候选全集，AS38）。若后续环境补齐这些包，代码保留 feature-gate 可无缝切换官方实现，但预期数值可能有微小差异（自实现均为闭式解精确复现，非近似）。

### 8.2 复现主链命令（按顺序）

```bash
# m1→m6 全链：数据准备 → Δβ选股 → 聚类 → 两阶段pattern matching → DY溢出加权 → EW/MV组合回测
uv run python -m src.ssrn_6115073.main

# m7 稳健性与敏感性分析（滚动子区间/样本外尾窗/参数敏感性/单因子敏感性）
uv run python -m src.ssrn_6115073.robustness
```

两条命令 exit=0 即产出 `output/ssrn_6115073/results/` 下全部权威产物（`backtest_summary.xlsx`、`robustness_summary.xlsx`、12 张 PNG 图表）。`comparison.json`/`metrics.json`/`verify_report.md` 由 verifier 的一次性提取脚本产出（非常驻仓库文件，逻辑已固化在 `verify_report.md` 记录的运行步骤中，如需复现需按报告记录的独立复算方式重新编写提取脚本）。

### 8.3 样本外延伸复现（如需重跑 §十）

唯一改动：`src/ssrn_6115073/config.py` 的 `TEST_END` 由 `2024-12-31` 改为需要的样本外截止日（如 `2026-06-30`），其余信号/组合/参数**零改动**，重跑 `main.py`。任何为改善样本外表现的调整均属数据窥探，不应做。

### 8.4 扰动测试复现（hard 难度必做）

将 `data_prep.TRAIN_END` 由 `2018-12-31` monkeypatch 为 `2017-12-31`（`TEST_START` 保持不变），同进程先跑 base 再跑 perturbed 对比核心指标相对变化（权威版预期：CPMM-EW hs300 SR 相对变化 27.25%）。

### 8.5 注意事项

- **`verify_report.md` 的 m1-m7 里程碑级小节使用的是 code_audit 修复前的旧 tradeable-only 口径数字**（如 CPMM-EW hs300 SR=0.6042），已被"最终验证（member 过滤后权威版）"小节（SR=0.7168）取代——**复现结果核对一律以该小节与 `comparison.json` 为准**，勿引用里程碑旧段落。
- `templates/standards.json` 要求的 Excel 文件名为 `backtest_summary.xlsx`，早期里程碑产物一度命名 `r1_main_results.xlsx`，最终版已对齐为 `backtest_summary.xlsx`。

---

## 九、市场迁移声明（experimental 专属）

### 9.1 迁移性质声明

本次复现属于**方法迁移复现（market-transplant）**，非数值对齐复现。原文《Online Portfolio Selection Using Macroeconomic Pattern Matching》的三个股票市场（S&P 500、Dow Jones Industrial Average、Nikkei 225，行情来源 Refinitiv）与 18 个宏观候选因子（来源 FRED 美国宏观数据库）在本地环境**全部不可获取**（`templates/data_catalog.md` 明列海外个股行情与美国宏观为缺口）。因此：

1. **复现目标从"数值对齐原文"改为"方法在 A 股是否成立"**：spec.md 中的 R1（表2）/R3（表4）/R4（表6）/R5（图9-10）等原文数值基准，在本次复现中改作**定性方法验证参照**，不追平数字。
2. 原文全部不可得数据用 A 股等价物 `status: substitute` 替代，每项登记一条 `market-transplant` 性质假设。
3. 歧义裁决时"能否对上原文数值"权重降低，优先"方法论最标准 + 迁移 A 股最可落地"。

### 9.2 替代数据清单（核心 7 项映射，AS28-AS34）

| 原文数据 | 本地等价替代 | 状态 | 关联假设 |
| --- | --- | --- | --- |
| S&P500 成分股（Refinitiv，主分析） | 沪深300（000300）时点成分股，前复权 | substitute | AS28 |
| Dow Jones 成分股 | 上证50（000016）时点成分股 | substitute | AS28 |
| Nikkei225 成分股（日股） | 中证500（000905）时点成分股 | substitute | AS28 |
| FRED 18 宏观候选 → 7 选用（CPI/IR/GDP/DGDP/IP/UR/PPI） | 中国宏观候选池（CPI/PPI/GDP/IP/IR/M2/PMI），BorutaShap 重选 | substitute | AS29 |
| FRED UR（失业率） | **本地无干净等价物 → 据实降维剔除**（不用 PMI 等强行代理） | **missing** | AS30 |
| FRED DGDP（债务/GDP） | 社融存量/GDP 杠杆率代理（后据实剔除社融，见 AS35） | substitute→剔除 | AS31/AS35 |
| 美国 T-bill（rf） | 10Y 国债收益率折算（SHIBOR/短端国债历史不足） | substitute | AS32/AS36 |
| 三大指数点位（Index 基准/σ_b） | 对应 A股宽基指数点位 | substitute | AS33 |
| 1995-2023（训练至2018） | A股 2007-2024（训练2007-2018/测试2019-2024） | substitute | AS34 |

**衍生市场迁移事实**（AS35/36/44/48/49/53/59/60，全文见 §三对应条目）：DGDP 因社融口径不平稳据实剔除（AS35）；rf/IR 改用长端国债替代短端（AS36）；上证50 窄基指数触发选股降级（AS44）；SU 聚类结构在 A股月频极弱（AS48）；Matrix Profile/VAR 因依赖缺失自实现（AS49/52，属依赖退化非市场迁移本身但由市场迁移环境触发）；溢出口径从波动率降级为收益/变化广义溢出（AS53）；SA1/SA2 稳健性区间相应平移（AS59/60）。

### 9.3 数值不对齐的语义

`comparison.json` 中 `pass=true` **不代表复现值与原文值在容差内对齐**。`mode_note` 字段明确写明："pass 按'迁移市场产出完整且计算可信'填写，原文数值容差整体豁免"。81 项定量指标的 `rel_dev`（相对偏差）区间跨度 1.5%~868%，`R3` 中多项 `direction_match=false`（组合层 β⁻/Δβ 符号与原文相反）——这些均**不构成"复现失败"**，而是市场迁移后 A 股与美/日股票市场结构性差异的真实反映，已在 §六如实陈述。判定"是否达标"的实际依据是 17 项定性判据（消融逻辑方向、相对基准排名、关键因子迁移等），而非数值容差。

### 9.4 方法在迁移市场（A 股）成立与否的结论

**样本内（2019-2024）：部分迁移成立。**
- 成立的部分：去宏观（CPM）、去溢出加权（EWMFM）两个消融环节验证有增量价值（CPMM-EW 优于二者，三市场一致）；CPI 溢出最强的原文核心结论迁移成立；候选个股级 Δβ>0 主导，下行保护选股逻辑迁移成立；CPMM-EW 相对 5 个外部基准中的 4 个（Index/HRP/HERC/NCO）三市场全面领先。
- 不成立/存疑的部分：去聚类（PMM）环节在 hs300/zz500 未降反升，聚类去冗余在 A股月频的增量价值存疑（呼应 SU 结构弱发现）；IR 溢出强度方向与原文相反（三市场垫底，非次强）；关键宏观因子从原文 CPI/IR 迁移为 A股 PMI；组合层下行保护仅在 sz50 显现；方法对参数窗口 w 高度脆弱（邻域 SR 骤降 37%）；CPMM-EW 非跨滚动子区间稳定领先。

**样本外（2025-01~2026-06，18 个月新数据）：失效。** 详见 §十，此处不重复——主市场沪深300 CPMM-EW 夏普由样本内 +0.7168 反号至 -0.1209，消融增量三项全部转负，跑输被动指数。

**综合结论**：原文提出的"宏观模式匹配 + 溢出加权组合选股"方法，在 A 股迁移下**方法链可完整运行、部分机制（去宏观/去溢出加权环节、CPI 溢出强度、个股级下行保护选股）的增量价值在样本内得到验证，但聚类环节增量存疑、对参数窗口脆弱，且样本外主市场表现失效**——不构成对该方法在 A 股长期稳健有效的支持性证据。

---

## 十、样本外表现（oos=done）

> 引自 `workspace/ssrn_6115073/oos_report.md` 与 `output/ssrn_6115073/results/oos_metrics.json`。策略逻辑与参数**全部冻结**（训练2007-2018、w=7/9/9、nc=10、宏观7因子、Δβ训练期双区制、聚类、DY溢出、member∩tradeable过滤、消融定义、指标口径均与复现基线一致），**唯一改动=`config.TEST_END` 由 `2024-12-31` 延伸到 `2026-06-30` 单行日期**，无任何为改善样本外表现的调参（数据窥探）。

### 10.1 样本外区间

| 字段 | 取值 |
| --- | --- |
| 样本内（复现基线）区间 | 2019-02-28 ~ 2024-12-31（69 月，与 `comparison.json` 同口径） |
| 样本外区间 | 2025-01-27（首个已实现收益）~ 2026-06-30 |
| 样本外月度观测数 | 18 个月 |
| 样本外交易日数 | 359（>60，不触发"样本不足"） |

延伸零污染样本内自洽校验：hs300/sz50/zz500 CPMM-EW/CPMM-MV 延伸后样本内切片 SR 与复现基线逐位一致（abs_diff=0），坐实这是一次干净的样本外延伸，非重算污染。

### 10.2 逐指标对比（样本内 → 样本外）

**主市场沪深300（对标原文 S&P500 主分析地位）**：

| 方法 | 指标 | 样本内 | 样本外 | 变化 |
| --- | --- | --- | --- | --- |
| CPMM-EW | SR | 0.717 | **-0.121** | -0.838（反号） |
| CPMM-EW | AR | 0.226 | -0.008 | -0.234 |
| CPMM-EW | 累计收益 | 1.944 | -0.044 | -1.988 |
| CPMM-EW | MDD | 0.416 | 0.252 | -0.164 |
| CPMM-MV | SR | 0.930 | 0.087 | -0.843 |
| CPMM-MV | 累计收益 | 5.603 | 0.0005 | -5.602 |

**三宽基 CPMM-EW 横向（跨市场推广）**：

| 市场 | tier | 样本内 SR | 样本外 SR | 样本外排名/11 | 单市场判读 |
| --- | --- | --- | --- | --- | --- |
| 沪深300 | Tier1 | 0.717 | **-0.121** | 9/11（近垫底） | 失效（反号） |
| 上证50 | Tier2_degraded | 0.598 | **0.771** | 2/11 | 逆势延续/强化 |
| 中证500 | Tier1 | 0.595 | 0.204 | 4/11 | 衰减（正号但缩至34%） |

**§九.2 消融增量核查（沪深300，CPMM-EW 减各消融，正=全模型更优）**：

| 市场 | −去宏观(CPM-EW) | −去聚类(PMM) | −去溢出(EWMFM) |
| --- | --- | --- | --- |
| 沪深300 | -0.117 | **-0.992** | **-1.060** |
| 上证50 | +2.008 | +0.536 | +0.293 |
| 中证500 | +1.126 | +0.032 | -0.460 |

主市场三条增量**全部转负**——聚类与溢出加权在样本外**反成拖累**（去掉它们的 PMM/EWMFM 反而大幅领先全模型）；机制增量仅在上证50 全部为正，在 2/3 市场不稳健。

**§九.3 相对基准（沪深300）**：CPMM-EW 样本外 -0.121，Index（指数买入持有）样本外达 **1.135**（中证500指数达2.058，两宽基 2025-2026 强势 beta 行情）——**主动选股在样本外大幅跑输被动指数**，样本内领先 Index/HRP/NCO 的优势在样本外主市场全数反转。

### 10.3 判读规则与结论

**判读规则**（以主市场沪深300 CPMM-EW 夏普为核心判据）：
- 延续：样本外 SR ≥ 样本内 SR×50%（=0.358）且同号且>0
- 衰减：方向保持但量级显著缩水（0<样本外SR<0.358）
- 失效：方向反转（正→负）或收益不再显著
- 样本不足：oos_days<60 或无样本外数据

**判定：主市场沪深300 CPMM-EW 样本外 SR = -0.121 < 0，由样本内 +0.717 方向反转，命中"失效"。**

跨市场如实并记（不美化不隐藏）：上证50 逆势强化（0.598→0.771）、中证500 衰减（0.595→0.204）。单一 conclusion 以主市场+核心机制为准判为"失效"；机制层面（消融增量）在 2/3 市场反转或不全正、主市场三负，支持"效应未在样本外稳健延续"。

### 10.4 统计意义提示

样本外仅 18 个月度观测，夏普等年化指标估计置信区间较宽；叠加样本外持仓高度集中（member 过滤后中证500 月均在仓降至 1.53 只），个别标的对结果影响被放大——"上证50 逆势强化"应视为方向性证据而非精确定论。**主市场"失效"结论由"方向反转+增量三负+跑输被动指数"多重一致证据支撑，稳健性高于单点夏普**。

**最终 conclusion 字段（`oos_metrics.json`）：失效**

---

## 附录 A：审计与可信度详表

### A.1 覆盖率统计

| 类别 | total | done | skipped | infeasible | pending/in_progress |
| --- | --- | --- | --- | --- | --- |
| 全部要素 | 35 | 33 | 2 | 0 | 0 |
| core 优先级 | 21 | 21（100%） | 0 | 0 | 0 |
| support 优先级 | 12 | 12（100%） | 0 | 0 | 0 |
| optional 优先级 | 2 | 0 | 2（100%） | 0 | 0 |

**整体覆盖率 = 33/35 = 94.3%**（core 100%、support 100%，仅 optional 层 2 项 skip）。**未复现要素逐条**（skipped 全量，无 infeasible）：

| 要素ID | 类别 | 描述 | 优先级 | 理由 |
| --- | --- | --- | --- | --- |
| SA5 | SA | 附录G 扩展相似性 ES | optional | `out_of_scope`——次相似变体非主结论，市场迁移聚焦主方法验证 |
| SA6 | SA | 6.1节 TDA 拓扑异常分析 | optional | `method_underspecified`——TDA 参数（ε/持续同调阈值）原文未给，optional 补充分析 |

coverage_matrix.md 中**无残留 pending/in_progress 行**（自检确认）。

### A.2 假设清单与验证后回看（索引，全文见正文 §三）

> 全部 63 条假设的完整内容（含依据、验证后回看结论、revise 指引）已在正文 §三 逐条全文收录。本表为 **major-auto 高亮的 37 条**的快速索引（占全部 63 条的 58.7%），供审阅者优先复核。

| 组别 | major-auto 假设 ID | 验证后回看一句话判定 |
| --- | --- | --- |
| 歧义裁决 | AS1, AS2, AS3, AS4, AS5, AS6, AS7, AS8, AS9, AS11, AS12, AS15, AS17 | 均获数据支持；AS15（显著性口径）§九结论对 α 放宽的依赖度归 diagnoser 层面已在 §六 交代 |
| 市场迁移 | AS28, AS29, AS30, AS31, AS34 | 迁移底座成立，效应强弱随市场结构改变（数值豁免） |
| m1 落地 | AS35, AS37, AS39 | 口径修正均获数据支持 |
| m2 落地 | AS42, AS43, AS44 | Δβ train-once 获扰动坐实；频率适配裁决使方法可落地；sz50 窄基降级为真实迁移发现 |
| m3/m4 落地 | AS46, AS48, AS51 | AS48 为核心迁移发现（SU结构弱、聚类增量存疑），未来函数硬约束坐实 |
| m5 落地 | AS53, AS54, AS55 | 溢出口径迁移代理、train-once 零泄漏、三测度并存解 spec 矛盾，均获数据支持 |
| m6 落地 | AS56, AS57, AS58 | 建仓/回测口径自洽（独立复算 abs_diff=0）；消融/基准实现忠实 |
| m7 落地 | AS60, AS61, AS62, AS63 | SA2 尾窗衰减与 oos 一致；SA3 w 脆弱是关键发现；SA4 关键因子=PMI；member 口径是本报告全部结论基线 |

其余 33 条（非 major-auto，多为参数细节/笔误订正/依赖退化实现细节）验证后回看均为"获数据支持"或"不影响结论"，全文见正文 §三 对应小节。

### A.3 外部审查结论

| 审查点 | engine | verdict | critical | major | minor | accepted | rejected | deferred |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| spec | codex（真实执行，无降级） | pass_with_issues | 0 | 4（CDX-S-01/02/03 + SA-A01） | 2（SA-A02/03） | 5 | 1（SA-A03） | 0 |
| code | codex（真实执行，无降级） | fail→修复后闭环 | 0 | 2（CDX-C-01/02） | 0 | 2 | 0 | 0 |
| result | codex（真实执行，无降级） | pass | 0 | 0 | 0 | 0 | 0 | 0 |

**无降级情形**：三审查点均为 `engine=codex` 真实调用完成，**无一处 `claude_fallback` 或因 codex 不可用而 `skipped`**——不适用 B 级"外审有失败性降级或缺失"判据。

**遗留 rejected 清单**（全量，1 条）：SA-A03（F1 页码范围下界略宽，minor confidence low，理由：非遗漏非幻觉、C6 页码抽查不受影响）。

**补充：内部逐里程碑质量审计**（`impl_audit_m1-m7`，quant-auditor 在 implement 阶段同步执行，非独立 iterate 循环）：共发现 major 2 项（m1 宏观口径混用 CA-A01、m6 OLMAR 方向反转 CA-A01），均在实现阶段内近实时修复并留痕于 assumptions.md（AS39/AS58）与 coverage_matrix 变更日志；minor 若干项（m1 CA-A03/A04/A05、m3 CA-M3-01、m5 CA-A01/A02、m7 CA-A01），均无现行数值影响或已登记为设计内选择，无 critical。

### A.4 迭代历史摘要

**轮次：0（无独立 iterate 阶段被触发）**。详见正文 §四。触发/改动/关键指标变化不适用于本案；实现阶段内的 3 类修正周期（spec_audit 修复、implement 内部审计修复、code_audit 修复）汇总如下：

| 修正周期 | 触发 | 改动 | 关键影响 |
| --- | --- | --- | --- |
| spec_audit 修复 | codex+内审共 6 条意见（3major+3内审） | spec.md 逐格数值订正（表2/表3/D2 候选池） | 不影响复现代码，仅规格文本忠实性提升 |
| implement 内部审计修复（m1） | impl_audit_m1 CA-A01（major，宏观口径混用） | change_panel 口径感知重构（AS39） | Δβ 分区未被累计跳变污染 |
| implement 内部审计修复（m6） | impl_audit_m6 CA-A01（major，OLMAR方向反转bug） | OLMAR 均值回归公式修正（AS58） | OLMAR 波动回落至正常量级，不再是动量策略 |
| code_audit 修复 | codex CDX-C-01/02（2 major） | member_mask 时点成分过滤补全；F12 异常处理收窄 | **连锁改变 R1/SA 全部数值与 SA4 结论**（本报告全部数字均基于修复后的权威版） |

### A.5 遗留偏差与归因（全量 81 项定量指标，`comparison.json`）

> 完整 81 项定量指标详见 `output/ssrn_6115073/results/comparison.json`；下表按类别汇总统计（数值区间引自源文件，未重算）。

| 类别 | 指标数 | rel_dev 区间 | direction_match=false 数 | 归因（引自 §六已知口径差异） | 归因状态 |
| --- | --- | --- | --- | --- | --- |
| R1（表2 6比率×2模型×3市场） | 36 | 1.5%~238.2% | 0 | 市场β/波动结构差异、MV集中度效应（AS11/AS56） | 已知口径差异，非计算错误 |
| R3（表4 β⁺/β⁻/Δβ×2模型×3市场） | 18 | 2.8%~868.2% | 7 | 组合层β⁻符号与原文相反（A股仅sz50显现下行保护，个股级Δβ方向仍支持，见§二.2） | 已知口径差异，属市场结构迁移差异 |
| R4（表6 7因子×3市场溢出强度） | 21（含6项原文无对应值：M2/PMI 为新增候选因子） | 35.8%~480.0% | 0（另 6 项 M2/PMI 无原文对照，direction_match 字段为 null 不适用） | 溢出口径迁移代理（AS53，量级不可比仅比排名） | 已知口径差异，非计算错误 |
| R5（图9-10 累计收益×2模型×3市场） | 6（含2项原文无对应值） | 27.3%~647.0% | 0 | A股测试期/市场β/集中度差异（AS23豁免） | 已知口径差异，非计算错误 |

**容差**：全部 81 项 `tolerance_key=allocation.default(experimental豁免)`，即数值对齐容差在本案整体豁免，`pass` 判定不依赖 `rel_dev` 是否在容差内，而依赖"产出完整+计算可信"（详见 §九.3）。

### A.6 反虚报核查记录与总体可信度

**扰动测试结果**（hard 难度必做，本案共执行 3 轮，互相印证）：

| 轮次 | 扰动参数 | 核心指标变化 | 结论 |
| --- | --- | --- | --- |
| m5 级（轻量） | 溢出估计训练截止提前1年 | to_index 变化 25%-38% | R4 定性（CPI前二/IR垫底）对训练窗稳健 |
| m6/m7 级 | `TEST_END` 提前1年（2023-12-31） | CPMM-EW hs300 SR 0.6042→0.7730（27.95%） | PASS，输出随输入变化 |
| **最终权威版**（`evidence_manifest.md` EVD-03） | `TRAIN_END` 提前1年（2017-12-31） | CPMM-EW hs300 SR 0.716811→0.521495（**27.25%**），全核心指标最大变化 75.91%（PMM累计） | **PASS**——远超 0.1% 阈值，输出随训练输入真实变动，无硬编码/输入解耦嫌疑 |

**证据链条数**：`evidence_manifest.md` E1-E6 六项规则共 **11 条**"亲自执行"证据（EVD-01~EVD-11），六项规则每项至少 1 条证据落盘，全部结果 `pass`。

**幻觉抽查命中率**：`result_audit`（quant-auditor mode=result）K3/E4 三方数值核对（`comparison.json` == `metrics.json` == `backtest_summary.xlsx`/`robustness_summary.xlsx`）抽查 **17 格**（R1核心6格+R4溢出4格+R5累计1格+R3β值1格+robustness 4项SA1-4+权重路径），**一致率 100%（0 处偏差）**；10 张 PNG 图表全部亲自 Read 核对与 metrics 吻合，**无图表造假**；唯一发现 1 条 minor（RA-01，文书卫生项，已披露不构成阻断，详见 §六.3）。K2 过于完美/硬编码复核：98 项指标无一"复现值==原文值"（最小 rel_dev 仍 1.52%），扰动测试证实输出随输入变化，**无硬编码嫌疑**。

**总体可信度评级：A**

评级依据三项判据（覆盖率≥90%含core 100%、外审全部闭环无降级、零critical遗留）**全部满足**（详见正文 §一.2），且反虚报核查（扰动/证据链/三方一致/图表核对）全部通过，**评级衡量复现过程的完整性与严谨性，不代表方法在 A 股长期有效性判断**（详见正文 §一.3 边界澄清，样本外主市场结论为"失效"）。

---

*本报告由 quant-reporter 汇总生成，全部数值引自 `workspace/ssrn_6115073/` 与 `output/ssrn_6115073/` 既有产物，未新增结论、未重算指标。*
