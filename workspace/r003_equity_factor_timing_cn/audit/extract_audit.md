# 提取完整性复审

- 报告：`r003_equity_factor_timing_cn`
- 审计模式：`spec`
- 复审轮次：第1轮修复后
- 审计日期：2026-07-18
- 只读输入：原始PDF、`spec.md`、`coverage_matrix.md`、`ambiguities.md`、`tables_extracted.md`、`plan.md`、`audit/spec_fix_round1.md`
- 审读分离声明：未读取任何被审者完成汇报；Exhibit编号、要素计数、D15–D29属性、R1–R10行列与数值均由审计者直接从允许输入独立重算。

---

## 第1轮定向问题复核

| 原问题 | 独立复核证据 | 状态 |
| --- | --- | --- |
| SA-A01：原文声称25个宏观驱动，但仅登记10项 | `spec.md:149-267`新增D15–D29共15个占位；每项均只引用PDF p5“25 macro drivers”计数声明，明确标记`missing`、`nonrecoverable`和“不虚构”；`coverage_matrix.md:23-37`对应15行均为`infeasible/data_missing`。D1–D10+D15–D29恰为25个宏观驱动登记。 | cleared |
| SA-A02：R表自动提取缺失或残缺 | `tables_extracted.md:6-109`已重建R1–R10；审计者重新读取PDF p8–p13逐表核对，标题、页码、行列名、全部已给数值及原始空白均一致。 | cleared |

## C1–C6 检查项

| 检查项 | 独立检查结果 | 结论 |
| --- | --- | --- |
| C1 图表编号连续性 | 对原始PDF全文独立正则检索，唯一编号为Exhibit 1–17且连续，`fig_max=17`；没有独立编号的Figure/Table，`tbl_max=0`。与`spec.md:9-10,669-685`一致。 | pass |
| C2 逐页覆盖扫描 | PDF共18页；`spec.md:30-47`覆盖p1–p18。p1–p16研究内容均有要素或EX关联；p17参考文献、p18版权页合理排除。p5已补D15–D29计数占位。 | pass |
| C3 触发词检查 | `robust`、time-series cross-validation、sub-samples、market/business-cycle分组、Appendix、further research及different time frequencies均回查；实质测试已关联SA1–SA4/F/R，纯展望或局限陈述有合理排除。 | pass |
| C4 计数交叉 | spec实际计数D29/F21/B14/R10/SA4=78，与`element_counts`及coverage实际78行一致；25个宏观驱动由10个公开项+15个不可恢复占位闭合，无虚构。`plan.md:195`已明确78=63个可行动项+15个不可恢复占位。 | pass |
| C5 基准表完备 | R1–R10在PDF、spec、`tables_extracted.md`三方逐项一致；R4–R6矩阵表头/行名/Value首行已补全，R9方向矩阵和R10原始空白均保留。 | pass |
| C6 幻觉引用抽查 | 分层抽查20条，覆盖D/F/B/R/SA，含D15/D29及R1–R10；20/20均可在原始PDF指定页定位。D15/D29只主张“未知占位”，未把未知名称或数值包装成原文。 | pass |

## C1 独立编号重算记录

| 项目 | 独立重算 | spec声明/登记 | 比对 |
| --- | --- | --- | --- |
| Exhibit编号集合 | 1–17连续 | EX1–EX17 | 一致 |
| `fig_max` | 17 | 17 | 一致 |
| `tbl_max` | 0 | 0 | 一致 |
| 编号缺口/未登记编号 | 无/无 | 无/无 | 一致 |

## C2 逐页覆盖记录

| PDF页 | 内容与关联 | 结论 |
| --- | --- | --- |
| p1 | 主要发现、摘要、引言；F1、SA3 | 已覆盖 |
| p2 | 因子投资与宏观背景；D1–D4 | 已覆盖 |
| p3 | 商业周期与额外风险特征背景；D5–D10、F17 | 已覆盖 |
| p4 | 两阶段方法、EX1；F1–F5 | 已覆盖 |
| p5 | 第二阶段、滚动窗、433个月样本、25驱动计数声明、EX2；D15–D29、B1–B3、F8–F10 | 已覆盖 |
| p6 | EX3十个公开宏观变量、EX4六因子；D1–D10、D14、F11–F16、B10 | 已覆盖 |
| p7 | 金融湍流公式和输入、EX5；D12–D13、F2、F6 | 已覆盖 |
| p8 | 肘部法、三风险状态、EX6–EX7；F2–F3、B2、R1 | 已覆盖 |
| p9 | EX8–EX9、SMOTE、时序交叉验证、第二阶段标签；F4–F10、B4/B8/B9、R1–R3 | 已覆盖 |
| p10 | EX10–EX12、84月窗、胜出频率；R4–R7、SA2 | 已覆盖 |
| p11 | EX13–EX14、样本外框架；B5–B6、R8、SA3 | 已覆盖 |
| p12 | EX15–EX16、商业周期、15%配置、概率权重；F17–F21、B11–B14、R9、SA4 | 已覆盖 |
| p13 | EX17、R10与结论；B7、R10、SA3–SA4 | 已覆盖 |
| p14 | K-Means、RF、特征重要性附录；F2、F7、F10 | 已覆盖 |
| p15 | 特征重要性与Stacking公式；F4、F7 | 已覆盖 |
| p16 | SMOTE公式；F5 | 已覆盖 |
| p17 | 参考文献 | 合理排除 |
| p18 | 版权声明 | 合理排除 |

## C3 触发词记录

| 触发语义 | PDF命中页 | spec处理 | 结论 |
| --- | --- | --- | --- |
| robust / robustness | p1、p11–p13 | SA3、SA4 | 已覆盖 |
| time series split / cross-validation | p9 | B8、R2、SA1 | 已覆盖 |
| sub-samples / market-risk regimes | p9–p11 | F8、B9、R4–R8、SA2–SA3 | 已覆盖 |
| business-cycle stages | p3、p5、p11–p12 | F17–F20、B12–B13、R9、SA4 | 已覆盖 |
| Appendix | p9、p14–p16 | F2、F4、F5、F7、F10 | 已覆盖 |
| further research | p4 | 未实施的后续研究展望 | 合理排除 |
| different time frequencies / expanded factors | p13 | 潜在适用范围，不是已执行敏感性测试 | 合理排除 |

## C4 计数交叉记录

| 对象 | 独立计数 | 文件声明/映射 | 判定 |
| --- | --- | --- | --- |
| 原文宏观驱动 | PDF p5声明25；p6仅公开10项 | D1–D10为10个公开项，D15–D29为15个未知占位，共25；A1保留不可恢复说明 | 一致，SA-A01清零 |
| D | 29 | `element_counts.D=29`；coverage 29行 | 一致 |
| F | 21 | `element_counts.F=21`；coverage 21行 | 一致 |
| B | 14 | `element_counts.B=14`；coverage 14行 | 一致 |
| R | 10 | `element_counts.R=10`；coverage 10行 | 一致 |
| SA | 4 | `element_counts.SA=4`；coverage 4行 | 一致 |
| 总要素 | 29+21+14+10+4=78 | coverage frontmatter `row_count: 78`且实际78行 | 一致 |
| plan可行动要素 | 里程碑列表63个唯一ID | `plan.md:195`明确D15–D29为15个不可恢复占位、不进入milestone | 一致 |
| plan总数口径 | `plan.md:195`明确78=63个可行动项+15个不可恢复占位 | spec与coverage总数78 | 一致 |

## C5 R1–R10三方复核

| R ID | PDF独立复核 | spec vs tables_extracted | 判定 |
| --- | --- | --- | --- |
| R1 | K=3；77.5%/18.7%/3.8%，占比和100.0% | 4×2完整一致 | match |
| R2 | 71%、0.753、0.721 | 3×2完整一致；shadow-rate原文冲突亦保留 | match |
| R3 | 19.7%/26.9%/34.1%/19.3%，和100.0% | 4×2完整一致 | match |
| R4 | EX10下三角21个已给值 | 6×6表头、行名、空白完整一致 | match |
| R5 | EX11 Normal下三角21个已给值 | 6×6表头、行名、空白完整一致 | match |
| R6 | EX11 Correction下三角21个已给值 | 6×6表头、行名、空白完整一致 | match |
| R7 | 19.9%/15.9%/14.4%/21.3%/4.0%/24.5%，和100.0% | 6×2完整一致 | match |
| R8 | 六特征×两状态共12值，两列各和100.0% | 6×3完整一致 | match |
| R9 | p12 EX15共16个正负号、8个原始空白 | 6×5方向矩阵逐格一致 | match |
| R10 | 四方法共21个已给值，Russell 1000三格原始空白 | 4×7逐格一致 | match |

## 遗漏清单

无。SA-A01、SA-A02及复审中发现的SA-A03均已清零。

## C6 抽查记录表

| 抽样要素ID | 类别 | 页码 | spec主张 | 直接回查原始PDF | 判定 |
| --- | --- | --- | --- | --- | --- |
| D1 | D | p6 | 核心CPI十年年化变化 | EX3原文可定位 | match |
| D15 | D | p5 | 第11个未知占位，名称/数值未披露 | p5只给25项总数；未发现该项名称或数值，正符合占位声明 | match |
| D29 | D | p5 | 第25个未知占位，名称/数值未披露 | p5只给25项总数；未发现该项名称或数值，正符合占位声明 | match |
| F4 | F | p9、p15 | RF/SVC/GNB+LR及交叉熵、sigmoid公式；p9 shadow-rate冲突 | p9与p15均可定位 | match |
| F7 | F | p14–p15 | 单树、归一化、RF汇总特征重要性 | p14–p15三层公式与符号可定位 | match |
| B1 | B | p5 | 1987-03至2023-03，433个月 | p5原文可定位 | match |
| B4 | B | p10 | 84个月初始训练窗 | p10原文可定位 | match |
| R1 | R | p8–p9 | K=3及三状态占比 | PDF逐值一致 | match |
| R2 | R | p9 | 71%、0.753、0.721 | PDF逐值一致 | match |
| R3 | R | p9 | 四类特征重要性 | PDF逐值一致 | match |
| R4 | R | p10 | 全样本相关矩阵 | PDF逐格一致 | match |
| R5 | R | p10 | Normal相关矩阵 | PDF逐格一致 | match |
| R6 | R | p10 | Correction相关矩阵 | PDF逐格一致 | match |
| R7 | R | p10 | 六因子胜出频率 | PDF逐值一致 | match |
| R8 | R | p11 | 分状态特征重要性 | PDF逐值一致 | match |
| R9 | R | p12 | EX15方向矩阵 | PDF原表逐格一致 | match |
| R10 | R | p13 | 四方法绩效表 | PDF逐值及空白一致 | match |
| SA1 | SA | p9 | 五折时序交叉验证 | PDF原文可定位 | match |
| SA3 | SA | p5、p10–p13 | 滚动样本外框架 | PDF原文可定位 | match |
| SA4 | SA | p11–p13 | 等权与商业周期双基准 | PDF原文及绩效表可定位 | match |

## 审计结论

- SA-A01：cleared；25项宏观驱动已按10项公开内容+15项不可恢复占位完成计数闭合，D15–D29无名称、数值、公式或变换虚构。
- SA-A02：cleared；R1–R10已在`tables_extracted.md`完整重建，与PDF和spec三方一致。
- SA-A03：cleared；`plan.md:195`已明确78个登记要素由63个可行动项和15个不可恢复占位组成。
- 遗漏清单：0项（critical 0 / major 0 / minor 0）。
- C6抽查：20/20 match。
- 已检查维度：C1通过 / C2通过 / C3通过 / C4通过 / C5通过 / C6通过。

verdict: pass
