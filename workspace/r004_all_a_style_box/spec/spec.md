---
report_name: r004_all_a_style_box
title: "Equity Factor Timing: A Two-Stage Machine Learning Approach"
institution: "The Vanguard Group, Inc."
report_date: 2024-01-25
authors: "Kevin J. DiCiurcio、Boyu Wu、Fei Xu、Scott Rodemer、Qian Wang"
market: 美股
pdf_pages: 18
exhibit_declared: {fig_max: 17, tbl_max: 0}
element_counts: {D: 29, F: 21, B: 14, R: 10, SA: 4, FIG_registered: 17, TBL_registered: 0}
type_hint: ml
tags_hint: [timing, factor]
extraction_date: 2026-07-18
---

# Equity Factor Timing: A Two-Stage Machine Learning Approach 复现规格书

## 一、研报元信息与结构地图

- 标题：Equity Factor Timing: A Two-Stage Machine Learning Approach
- 作者：Kevin J. DiCiurcio、Boyu Wu、Fei Xu、Scott Rodemer、Qian Wang
- 机构：The Vanguard Group, Inc.
- 刊物：The Journal of Portfolio Management，Quantitative Special Issue 2024
- 发布日期：2024-01-25，来自 PDF 创建日期；正文仅标示 2024，见 A14。
- 章节目录：摘要与主要发现（p1）；引言（p1-p4）；Methodology（p4-p5）；Feature Selection and Feature Construction（p5-p7）；Model Results and Feature Analysis（p7-p11）；Portfolio Simulation Section（p11-p13）；Conclusion（p13）；Appendix: Machine Learning Methodologies（p14-p16）；References（p16-p17）；版权声明（p18）。

页面覆盖表：

| 页码 | 内容类型 | 关联要素 |
| --- | --- | --- |
| p1 | 封面、主要发现、摘要、引言 | F1, SA3 |
| p2 | 因子投资与宏观变量文献背景 | D1-D4 |
| p3 | 商业周期因子择时背景、本文增量 | D5-D10, F17 |
| p4 | 文章结构、两阶段方法、Exhibit 1 | F1-F5, EX1 |
| p5 | 第二阶段、滚动训练、样本与来源、Exhibit 2 | D15-D29, B1-B3, F8-F10, EX2 |
| p6 | 宏观变量、六因子定义、Exhibit 3-4 | D1-D10, D14, F11-F16, B10, EX3-EX4 |
| p7 | 金融湍流公式与输入、Exhibit 5 | D12-D13, F6, EX5 |
| p8 | K-Means 肘部法与三类风险状态、Exhibit 6-7 | F2-F3, B2, R1, EX6-EX7 |
| p9 | 第一阶段结果、第二阶段标签、Exhibit 8-9 | F4-F5, F7-F10, B4, B8-B9, R1-R3, EX8-EX9 |
| p10 | 因子相关矩阵与胜出频率、Exhibit 10-12 | R4-R7, SA2, EX10-EX12 |
| p11 | 样本外概率、分状态重要性、组合模拟、Exhibit 13-14 | B5-B6, R8, SA3, EX13-EX14 |
| p12 | 商业周期基准、风险预算、权重规则、Exhibit 15-16 | F17-F21, B11-B14, R9, SA4, EX15-EX16 |
| p13 | 样本外组合结果与结论、Exhibit 17 | B7, R10, SA3-SA4, EX17 |
| p14 | 附录：K-Means、随机森林、特征重要性 | F2, F7, F10 |
| p15 | 附录：特征重要性公式、Stacking 分类 | F4, F7 |
| p16 | 附录：SMOTE、致谢、参考文献 | F5 |
| p17 | 参考文献 | - |
| p18 | 版权声明 | - |

## 二、数据要求（D 类）

### [D1] 核心 CPI 十年年化变化
- 页码: p6
- 原文: > "Trailing ten-year annualized changes in core CPI"
- 数据状态: missing
- 说明: Exhibit 3 列示，来源为 FRED；本次输入未附原始序列。
- 关联要素: F1, F4, F10

### [D2] 核心 CPI 一年年化变化
- 页码: p6
- 原文: > "Trailing one-year annualized changes in core CPI"
- 数据状态: missing
- 说明: Exhibit 3 列示，来源为 FRED；本次输入未附原始序列。
- 关联要素: F1, F4, F10

### [D3] 美国实际 GDP 增长
- 页码: p6
- 原文: > "US Real GDP Growth"
- 数据状态: missing
- 说明: Exhibit 3 列示，来源为 FRED；本次输入未附原始序列。
- 关联要素: F1, F10, F17

### [D4] Conference Board 商业周期标签
- 页码: p5-p6, p12
- 原文: > "Conference Board Business Cycle Labels"
- 数据状态: missing
- 说明: 研报以领先商业周期数据作为周期基准；本次输入未附标签序列。
- 关联要素: F17-F20, B12-B13

### [D5] 金融状况风险指标
- 页码: p6
- 原文: > "Financial Condition – Risk"
- 数据状态: missing
- 说明: Exhibit 3 列示，来源为 National Financial Conditions Index。
- 关联要素: F4, F10, R3, R8

### [D6] 金融状况信用指标
- 页码: p6
- 原文: > "Financial Condition – Credit"
- 数据状态: missing
- 说明: Exhibit 3 列示，来源为 National Financial Conditions Index。
- 关联要素: F4, F10, R3, R8

### [D7] 金融状况杠杆指标
- 页码: p6
- 原文: > "Financial Condition – Leverage"
- 数据状态: missing
- 说明: Exhibit 3 列示，来源为 National Financial Conditions Index。
- 关联要素: F4, F10, R3, R8

### [D8] 有效联邦基金利率
- 页码: p6
- 原文: > "Effective Federal Funds Rate"
- 数据状态: missing
- 说明: Exhibit 3 列示，来源为 FRED；本次输入未附原始序列。
- 关联要素: F4, F10

### [D9] 货币政策预期
- 页码: p6
- 原文: > "Monetary Policy Expectations"
- 数据状态: missing
- 说明: Exhibit 3 列示，来源为 FRED；具体序列定义未披露。
- 关联要素: F4, F10, R3, R8

### [D10] 周期调整市盈率 CAPE
- 页码: p6
- 原文: > "Cyclically Adjusted PE Ratio (CAPE Ratio)"
- 数据状态: missing
- 说明: Exhibit 3 列示，来源为 Robert Shiller 在线数据。
- 关联要素: F4, F10, R3, R8

### [D11] S&P 500 价格与三个月滚动回撤
- 页码: p4-p5, p8
- 原文: > "The market drawdown of S&P 500 is shown in Exhibit 2."
- 数据状态: missing
- 说明: 研报注明 S&P 500 价格来自 Factset；用于第一阶段风险状态。
- 来源原文（p5）: > "equity and Treasury return related variables from Refinitiv Eikon Datastream"
- 来源原文（Exhibit 2）: > "S&P 500 price data sourced from Factset."
- 来源冲突: p5 总体来源陈述与 Exhibit 2 来源行不一致；仅并列登记，不裁决，见 A23。
- 关联要素: F2-F3, B2, R1 / 关联歧义: A23

### [D12] 十个 S&P 500 行业月收益
- 页码: p7
- 原文: > "monthly returns from ten S&P 500 sectors"
- 数据状态: missing
- 说明: 行业为 info tech、energy、financials、healthcare、staples、discretionary、utilities、industrials、telecoms、materials。
- 来源原文（p5）: > "equity and Treasury return related variables from Refinitiv Eikon Datastream"
- 来源原文（Exhibit 5）: > "Authors’ calculations based on data from FRED database and Factset."
- 来源冲突: p5 总体来源陈述与 Exhibit 5 来源行不一致；仅并列登记，不裁决，见 A23。
- 关联要素: F6 / 关联歧义: A23

### [D13] 多期限美国国债月收益
- 页码: p7
- 原文: > "Treasury instruments (12 months, 2 years, and 10 years maturity)"
- 数据状态: missing
- 说明: 与十个行业月收益共同构造金融湍流。
- 来源原文（p5）: > "equity and Treasury return related variables from Refinitiv Eikon Datastream"
- 来源原文（Exhibit 5）: > "Authors’ calculations based on data from FRED database and Factset."
- 来源冲突: p5 总体来源陈述与 Exhibit 5 来源行不一致；仅并列登记，不裁决，见 A23。
- 关联要素: F6 / 关联歧义: A23

### [D14] 六类美股因子月收益
- 页码: p6, p9-p13
- 原文: > "value, growth, momentum, low volatility, quality, and small size"
- 数据状态: missing
- 说明: 因子定义和股票池见 Exhibit 4；来源标为 Factset。
- 来源原文（p5）: > "equity and Treasury return related variables from Refinitiv Eikon Datastream"
- 来源原文（Exhibits）: > "Authors’ calculations based on data from FRED database and Factset."
- 来源冲突: p5 总体来源陈述与 Exhibit 4、10-17 来源行不一致；仅并列登记，不裁决，见 A23。
- 关联要素: F8-F21, R4-R10 / 关联歧义: A23

### [D15] 未披露宏观驱动第 11 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文仅列出 10 项可识别变量，第 11 项名称、数值和变换未披露。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D16] 未披露宏观驱动第 12 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D17] 未披露宏观驱动第 13 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D18] 未披露宏观驱动第 14 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D19] 未披露宏观驱动第 15 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D20] 未披露宏观驱动第 16 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D21] 未披露宏观驱动第 17 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D22] 未披露宏观驱动第 18 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D23] 未披露宏观驱动第 19 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D24] 未披露宏观驱动第 20 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D25] 未披露宏观驱动第 21 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D26] 未披露宏观驱动第 22 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D27] 未披露宏观驱动第 23 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D28] 未披露宏观驱动第 24 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

### [D29] 未披露宏观驱动第 25 项
- 页码: p5-p6
- 原文: > "Details of the 25 macro drivers considered for"
- 数据状态: missing
- 可恢复性: nonrecoverable
- 说明: 原文未披露该项名称、数值和变换；仅作完整性占位。
- 关联要素: F1, F4, F10 / 关联歧义: A1

## 三、因子/策略定义（F 类）

### [F1] 两阶段机器学习因子择时框架
- 页码: p1, p4-p5
- 原文: > "the authors propose a two-stage machine model for dynamic factor rotation"
- 定义: 第一阶段识别并预测市场风险状态；第二阶段在各状态内预测因子相对表现。
- 依赖数据: D1-D29
- 关联基准: R1-R10

### [F2] 第一阶段 K-Means 聚类
- 页码: p4, p7-p8, p14
- 原文: > "we use K-means clustering to categorize market risk regimes"
- 公式（转写）: minimize Σi Σj ||xi - μj||²
- 输入: S&P 500 回撤数据；K 由肘部法选择。
- 关联基准: R1 / 关联歧义: A3

### [F3] 三类市场风险状态
- 页码: p8
- 原文: > "cluster 0 shows “normal market risk regime,”"
- 定义: cluster 0=normal；cluster 1=market correction；cluster 2=bear market。
- 关联基准: R1

### [F4] 第一阶段 Stacking 分类器
- 页码: p4, p9, p15
- 原文: > "Random Forest (RF), Support Vector Classifier (SVC), and Gaussian Naive Bayes"
- 定义: 第一层 RF、SVC、GNB；第二层 Logistic Regression 学习三者权重。
- 交叉熵损失（转写）: L(w) = -Σ[y_i log(y_pred_i) + (1-y_i) log(1-y_pred_i)]
- 输出公式（转写）: y_pred = σ(w1 RF(x) + w2 SVC(x) + w3 GNB(x))
- 目标原文（p4）: > "classification techniques to predict these regimes"
- 冲突原文（p9）: > "predicting significant shadow rate changes"
- 冲突原文（p15）: > "predicting shadow rates"
- 原文冲突: 方法主线与 Exhibit 8 指向市场风险状态，p9/p15 却写 shadow rate；仅并列登记，不在 spec 裁决，见 A6。
- 关联基准: R2 / 关联歧义: A5, A6

### [F5] SMOTE 类别再平衡
- 页码: p4, p9, p16
- 原文: > "we adopted the synthetic minority oversampling technique (SMOTE)"
- 公式（转写）: x_new = xi + α(xj - xi)，α∈[0,1]
- 用途: 对少数市场风险状态生成合成样本以平衡数据集。
- 关联基准: R1-R2

### [F6] 金融湍流指标
- 页码: p6-p7
- 原文: > "They measure financial turbulence as:"
- 公式（转写）: d_t = (y_t-μ) Σ^(-1) (y_t-μ)′
- 输入: D12 十个行业月收益、D13 三种期限国债月收益。
- 关联基准: R3, R8 / 关联歧义: A4

### [F7] 决策树特征重要性
- 页码: p9, p14-p15
- 原文: > "employing the Gini index as a measure of impurity"
- 单树公式（转写）: fi_i = Σ_{j:node j splits on feature i} ni_j / Σ_{k∈all nodes} ni_k
- 树内归一化（转写）: normfi_i = fi_i / Σ_j fi_j
- 森林汇总（转写）: RFfi_i = Σ_j normfi_ij / Σ_{j,m} normfi_jm
- 关联基准: R3, R8

### [F8] 第二阶段按风险状态分割样本
- 页码: p5, p9, p11
- 原文: > "The entire dataset is segmented into sub-dataframes"
- 定义: 第一阶段风险状态分别形成子数据框，并在各状态内训练模型。
- 关联基准: R4-R8

### [F9] 月度胜出因子二元标签
- 页码: p4-p5, p9-p10
- 原文: > "designating the best-performing factor as ‘1’ and the others as ‘0’"
- 定义: 每月最佳因子标 1，其余五个因子标 0。
- 图示原文（p4 Exhibit 1）: > "Label by comparing factors daily return"
- 正文原文（p5）: > "evaluate the monthly performance of each factor"
- 原文冲突: Exhibit 1 写 daily return，p5 正文写 monthly performance；仅并列登记，不在 spec 裁决，见 A24。
- 关联基准: R7 / 关联歧义: A13, A24

### [F10] 第二阶段随机森林胜出概率模型
- 页码: p9-p11, p14
- 原文: > "training our random forest model to distinguish the outperforming factor"
- 定义: 在各风险状态内预测每个因子胜出其他因子的概率。
- 依赖数据: D1-D10, D14
- 关联基准: R7-R8 / 关联歧义: A7

### [F11] Value 因子
- 页码: p6
- 原文: > "1/3 of stocks with the lowest price-to-book ratio"
- 定义: Russell 1000 Index 中市净率最低的 1/3 股票。
- 关联要素: B10

### [F12] Growth 因子
- 页码: p6
- 原文: > "1/3 of stocks with the highest price-to-book ratio"
- 定义: Russell 1000 Index 中市净率最高的 1/3 股票。
- 关联要素: B10

### [F13] Momentum 因子
- 页码: p6
- 原文: > "1/3 of stocks with the highest 12-month trailing returns"
- 定义: Russell 1000 Index 中过去 12 个月收益最高的 1/3 股票。
- 关联要素: B10

### [F14] Low Volatility 因子
- 页码: p6
- 原文: > "1/5 of stocks with the lowest annualized return volatility"
- 定义: Russell 1000 Index 中年化收益波动率最低的 1/5 股票。
- 关联要素: B10

### [F15] Quality 因子
- 页码: p6
- 原文: > "1/3 of stocks with the highest quality score"
- 定义: Russell 1000 Index 中质量得分最高的 1/3 股票。
- 关联要素: B10 / 关联歧义: A8

### [F16] Small-Cap 因子
- 页码: p6
- 原文: > "2/3 of stocks with the lowest market capitalization"
- 定义: Russell 3000 Index 中市值最低的 2/3 股票。
- 关联要素: B10

### [F17] 商业周期因子择时基准
- 页码: p5, p11-p12
- 原文: > "based on their full sample historical average performance"
- 定义: 按各商业周期阶段的全样本历史平均表现超配或低配因子。
- 依赖数据: D4, D14
- 关联基准: R9-R10

### [F18] 商业周期六因子方向矩阵
- 页码: p12
- 原文: > "weights for each factor within specific business cycle regimes"
- 定义: Expansion、Slowdown、Contraction、Recovery 四阶段方向见 R9。
- 关联基准: R9

### [F19] 1/N 等权因子基准
- 页码: p11-p12
- 原文: > "an equal allocation is made to each factor"
- 定义: 六因子等权配置，作为第一项因子投资基准。
- 关联基准: R10

### [F20] 商业周期 15% 风险预算调权
- 页码: p12
- 原文: > "employing a 15% allocation, to modify the weights"
- 定义: 在 1/N 权重基础上，以 15% 配置调整各因子权重。
- 关联基准: R9-R10 / 关联歧义: A10

### [F21] 机器学习胜出概率权重
- 页码: p12
- 原文: > "the “winning” probability of each factor as its weighting"
- 定义: 每个因子的预测胜出概率直接作为其组合权重。
- 关联基准: R10 / 关联歧义: A11

## 四、回测设置（B 类）

### [B1] 全样本区间与频率
- 页码: p5, p12
- 原文: > "starts on March 1987 and ends in March 2023"
- 参数值: 1987 年 3 月至 2023 年 3 月；433 个月度观测。
- 图轴原文（p12 Exhibit 16）: > "May-23"
- 原文冲突: p5 明示样本截止 March 2023，Exhibit 16 横轴可见 May-23；仅并列登记，不推断新增观测，见 A25。
- 关联要素: D1-D14, F1 / 关联歧义: A25

### [B2] 三个月滚动回撤聚类输入
- 页码: p5, p8
- 原文: > "S&P 500 Three Months’ Rolling Drawdown"
- 参数值: 指数=S&P 500；回撤窗口=3 个月滚动。
- 关联要素: D11, F2-F3 / 关联歧义: A2

### [B3] 滚动窗口而非扩展窗口
- 页码: p5
- 原文: > "a rolling window model training approach"
- 参数值: 训练方式=rolling window；不是 extending windows。
- 关联要素: F1, F8-F10

### [B4] 第二阶段初始训练窗
- 页码: p10
- 原文: > "an initial training window of 84 months"
- 参数值: 初始训练窗=84 个月。
- 关联要素: F8-F10 / 关联歧义: A12

### [B5] 胜出概率样本外预测起点
- 页码: p10-p11
- 原文: > "rolling this training period in the post-2000 prediction data set"
- 参数值: 预测数据集=2000 年以后；Exhibit 13 图示至 2022 年 9 月。
- 关联要素: F10, SA3 / 关联歧义: A12

### [B6] 组合模拟指定训练区间
- 页码: p11
- 原文: > "training data between 1987 and 2000"
- 参数值: 组合模拟模型训练数据=1987 年至 2000 年。
- 关联要素: F8-F10, SA3 / 关联歧义: A12

### [B7] 组合复合收益样本外区间
- 页码: p12-p13
- 原文: > "the compound returns since 2002"
- 参数值: 复合收益自 2002 年开始；Exhibit 17 图示至 2022 年 9 月。
- 关联要素: F19-F21, R10, SA3-SA4 / 关联歧义: A12

### [B8] 五折时间序列交叉验证
- 页码: p9
- 原文: > "Accuracy (cross-validation five folds)"
- 参数值: 交叉验证=五折；切分方式=time series split。
- 关联要素: F4, R2, SA1

### [B9] 第二阶段合并熊市与调整状态
- 页码: p9
- 原文: > "we combined the bear market regime"
- 参数值: 第二阶段使用 normal 与 correction 两种状态；bear 并入 correction。
- 关联要素: F8-F10, R5-R8

### [B10] 六因子选股股票池
- 页码: p6
- 原文: > "Selection Universe"
- 参数值: Value/Growth/Momentum/Low Volatility/Quality 用 Russell 1000；Small-Cap 用 Russell 3000。
- 关联要素: F11-F16

### [B11] 组合比较基准
- 页码: p11-p13
- 原文: > "the 1/N benchmark, and the business cycle approach"
- 参数值: 比较 Russell 1000、六因子等权、商业周期倾斜和 ML 方法。
- 关联要素: F17-F21, R10

### [B12] 商业周期基准的信息口径
- 页码: p12
- 原文: > "using perfect hindsight of the macro-economic data"
- 参数值: 因子阶段均值用最终宏观数据与全样本；样本外周期识别只用当时可得信息。
- 关联要素: F17-F20 / 关联歧义: A15

### [B13] 商业周期风险预算
- 页码: p12
- 原文: > "employing a 15% allocation"
- 参数值: 风险预算配置=15%；用于修改 1/N 因子权重。
- 关联要素: F20, R9-R10 / 关联歧义: A10

### [B14] ML 组合权重口径
- 页码: p12
- 原文: > "the probability of outperforming to weight each factor"
- 参数值: 权重=各因子胜出概率；研报未另述风险预算。
- 关联要素: F21, R10 / 关联歧义: A11, A13

## 五、研报核心数值结果基准（R 类）

### [R1] 风险状态数目与样本占比
- 页码: p8-p9
- 原文: > "most our data (77.5%) falls under the normal market risk regime"
- 数值表:

  | 项目 | 数值 |
  | --- | --- |
  | 肘部法选择的聚类数 | 3 |
  | Normal market risk regime | 77.5% |
  | Market correction regime | 18.7% |
  | Bear market regime | 3.8% |

- 关联要素: F2-F5, B9

### [R2] Exhibit 8 Stacking 分类指标
- 页码: p9
- 原文: > "Accuracy Rate of Stacking Classification Mode"
- 数值表:

  | 指标 | 数值 |
  | --- | --- |
  | Accuracy (cross-validation five folds) | 71% |
  | Precision | 0.753 |
  | Recall | 0.721 |

- 相邻正文原文: > "predicting significant shadow rate changes"
- 原文冲突: Exhibit 8 与方法主线指向市场风险状态分类，相邻正文却写 shadow rate changes；未裁决，见 A6。
- 关联要素: F4-F5, B8 / 关联歧义: A6

### [R3] Exhibit 9 第一阶段特征重要性
- 页码: p9
- 原文: > "Feature Importance of Selected Variables"
- 数值表:

  | 特征 | Feature Importance |
  | --- | ---: |
  | Equity Valuation | 19.7% |
  | Financial Turbulence | 26.9% |
  | Financial Conditions | 34.1% |
  | Monetary Policy Expectation | 19.3% |

- 关联要素: F6-F7

### [R4] Exhibit 10 六因子全样本相关矩阵
- 页码: p10
- 原文: > "Cross Correlation throughout the Entire Sample Period"
- 数值表（上三角原表空白写为 n/a）:

  | 行/列 | Value | Growth | Momentum | Low Vol | Quality | Small |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | Value | 1 | n/a | n/a | n/a | n/a | n/a |
  | Growth | 0.66 | 1 | n/a | n/a | n/a | n/a |
  | Momentum | 0.68 | 0.93 | 1 | n/a | n/a | n/a |
  | Low Vol | 0.76 | 0.70 | 0.71 | 1 | n/a | n/a |
  | Quality | 0.85 | 0.86 | 0.83 | 0.87 | 1 | n/a |
  | Small | 0.86 | 0.76 | 0.77 | 0.64 | 0.80 | 1 |

- 关联要素: F11-F16, SA2

### [R5] Exhibit 11 Normal Risk 相关矩阵
- 页码: p10
- 原文: > "Cross Correlation throughout Each Market Risk Regime"
- 数值表（上三角原表空白写为 n/a）:

  | 行/列 | Value | Growth | Momentum | Low Vol | Quality | Small |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | Value | 1 | n/a | n/a | n/a | n/a | n/a |
  | Growth | 0.46 | 1 | n/a | n/a | n/a | n/a |
  | Momentum | 0.46 | 0.89 | 1 | n/a | n/a | n/a |
  | Low Vol | 0.63 | 0.56 | 0.55 | 1 | n/a | n/a |
  | Quality | 0.73 | 0.79 | 0.75 | 0.80 | 1 | n/a |
  | Small | 0.77 | 0.63 | 0.64 | 0.43 | 0.66 | 1 |

- 关联要素: F3, F8-F16, B9, SA2

### [R6] Exhibit 11 Correction 相关矩阵
- 页码: p10
- 原文: > "(Correction)"
- 数值表（上三角原表空白写为 n/a）:

  | 行/列 | Value | Growth | Momentum | Low Vol | Quality | Small |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | Value | 1 | n/a | n/a | n/a | n/a | n/a |
  | Growth | 0.54 | 1 | n/a | n/a | n/a | n/a |
  | Momentum | 0.61 | 0.86 | 1 | n/a | n/a | n/a |
  | Low Vol | 0.76 | 0.57 | 0.60 | 1 | n/a | n/a |
  | Quality | 0.86 | 0.70 | 0.68 | 0.88 | 1 | n/a |
  | Small | 0.88 | 0.64 | 0.69 | 0.67 | 0.81 | 1 |

- 关联要素: F3, F8-F16, B9, SA2

### [R7] Exhibit 12 因子历史胜出频率
- 页码: p10
- 原文: > "Historical Frequency Counting on Outperforming"
- 数值表:

  | 因子 | 胜出频率 |
  | --- | ---: |
  | Value | 19.9% |
  | Growth | 15.9% |
  | Momentum | 14.4% |
  | Low Volatility | 21.3% |
  | Quality | 4.0% |
  | Small Size | 24.5% |

- 关联要素: F9-F16

### [R8] Exhibit 14 分市场风险状态特征重要性
- 页码: p11
- 原文: > "Feature Importance within Each Market Risk Regime"
- 数值表:

  | 特征 | Normal Risk Regime | Market Correction Regime |
  | --- | ---: | ---: |
  | Equity Valuation | 36.4% | 42.5% |
  | Financial Turbulence | 12.4% | 13.1% |
  | Inflation | 16.3% | 17.9% |
  | Financial Conditions | 22.4% | 15.3% |
  | Monetary Policy Expectations | 9.3% | 9.9% |
  | GDP Growth | 3.2% | 1.3% |

- 关联要素: F6-F10, B9

### [R9] Exhibit 15 六因子四周期方向矩阵
- 页码: p12
- 原文: > "Business Cycle Strategy"
- 数值表（原表空白写为 n/a）:

  | 因子 | Expansion | Slowdown | Contraction | Recovery |
  | --- | --- | --- | --- | --- |
  | Value | n/a | – | n/a | + |
  | Growth | n/a | – | + | – |
  | Momentum | + | + | n/a | n/a |
  | Low Volatility | n/a | + | – | – |
  | Quality | n/a | + | – | n/a |
  | Small-Cap | – | – | + | + |

- 关联要素: F17-F20, B12-B13

### [R10] Exhibit 17 不同方法组合表现
- 页码: p13
- 原文: > "Compound Return with Different Approaches"
- 数值表（原表空白写为 n/a，未推算）:

  | 方法 | Annualized Return | Annualized Volatility | Sharpe Ratio | Annualized Excess Return | Annualized Tracking Error | Information Ratio |
  | --- | ---: | ---: | ---: | ---: | ---: | ---: |
  | Russell 1000 | 8.40% | 15.49% | 0.52 | n/a | n/a | n/a |
  | Equal Weighted | 8.63% | 15.19% | 0.54 | 0.18% | 2.40% | 0.07 |
  | Business Cycle Tilt | 9.84% | 16.06% | 0.59 | 1.50% | 3.95% | 0.36 |
  | ML Approach | 11.47% | 16.81% | 0.66 | 2.89% | 6.68% | 0.45 |

- 关联要素: F17-F21, B7, B11-B14, SA3-SA4

## 六、图表登记清单（EX 全集）

| ID | 标题 | 页码 | 摘要 | 复现意图 | 理由/关联要素 |
| --- | --- | --- | --- | --- | --- |
| EX1 | The Two-Stage Machine Learning Framework | p4 | 两阶段框架流程图 | reproduce | F1, F8-F10 |
| EX2 | S&P 500 Three Months’ Rolling Drawdown | p5 | 三个月滚动回撤时序 | reproduce | D11, B2 |
| EX3 | Macroeconomic and Financial Market Factors Considered for Machine Learning Testing | p6 | 宏观与金融变量及理由 | reproduce | D1-D10 |
| EX4 | Selected Equity Factors’ Succinct Definition | p6 | 六因子定义与股票池 | reproduce | F11-F16, B10 |
| EX5 | Financial Turbulence from Ten S&P 500 Sectors and Various Maturity Treasuries | p7 | 金融湍流时序 | reproduce | F6 |
| EX6 | The Elbow Method of K-Means Clustering | p8 | K-Means 肘部法 | reproduce | F2, R1 |
| EX7 | The S&P 500 Three Months’ Rolling Drawdown and Clustering | p8 | 回撤与三风险状态 | reproduce | F3, R1 |
| EX8 | Accuracy Rate of Stacking Classification Mode | p9 | 分类准确率、精确率、召回率 | reproduce | R2 |
| EX9 | Feature Importance of Selected Variables | p9 | 第一阶段四类特征重要性 | reproduce | R3 |
| EX10 | Cross Correlation throughout the Entire Sample Period | p10 | 六因子全样本相关矩阵 | reproduce | R4 |
| EX11 | Cross Correlation throughout Each Market Risk Regime | p10 | Normal 与 Correction 相关矩阵 | reproduce | R5-R6 |
| EX12 | Historical Frequency Counting on Outperforming | p10 | 六因子历史胜出频率 | reproduce | R7 |
| EX13 | Outperforming Probabilities of Each Factor from Out-of-Sample Prediction | p11 | 2000 年后样本外胜出概率 | reproduce | F10, SA3 |
| EX14 | Feature Importance within Each Market Risk Regime | p11 | 两风险状态特征重要性 | reproduce | R8 |
| EX15 | Business Cycle Strategy | p12 | 六因子四商业周期方向矩阵 | reproduce | R9 |
| EX16 | Business Cycle Labels | p12 | 商业周期标签与因子权重时序；横轴可见 May-23 | reproduce | 与 B1 的 March 2023 截止陈述冲突，见 A25；不推断新增观测 |
| EX17 | Compound Return with Different Approaches | p13 | 四种方法累计增长与表现表 | reproduce | R10 |

## 七、敏感性/稳健性分析（SA 类）

### [SA1] 五折时间序列交叉验证
- 页码: p9
- 原文: > "we applied the time series split approach during cross-validation"
- 测试设计: 五折交叉验证采用时间序列切分，以避免数据泄漏。
- 结论: > "achieved an impressive 71% cross-validation accuracy rate"
- 关联要素: F4-F5, B8, R2

### [SA2] 按市场风险状态的因子相关性分组分析
- 页码: p9-p10
- 原文: > "the cross-correlation in the normal market and correction market regimes"
- 测试设计: 对全样本、normal 状态、correction 状态分别计算六因子相关矩阵。
- 结论: > "becomes relatively lower"
- 关联要素: F3, F8, R4-R6

### [SA3] 滚动样本外预测与组合模拟
- 页码: p5, p10-p13
- 原文: > "a robust historical out-of-sample testing framework"
- 测试设计: 初始训练后滚动预测风险状态与各因子胜出概率，并形成组合。
- 结论: > "during most of the out-of-sample period, our strategy consistently delivers positive results"
- 关联要素: F1, F8-F10, F21, B3-B7, R10 / 关联歧义: A12-A13

### [SA4] 等权与商业周期双基准比较
- 页码: p4, p11-p13
- 原文: > "using equally weighted factors and a business cycle-only approach as benchmarks"
- 测试设计: 将 ML 方法与 Russell 1000、1/N 等权、商业周期倾斜组合比较。
- 结论: > "metrics underscore the robustness and efficacy of our approach"
- 关联要素: F17-F21, B11-B14, R10

## 八、提取自检声明

- [x] 逐页扫描确认：report_text.md 的 `===== PAGE 1 =====` 至 `===== PAGE 18 =====` 已全部过目，无整页跳过。
- [x] 图表编号全登记：Exhibit 1 至 Exhibit 17 连续登记，无缺号；研报统一使用 Exhibit 编号，未单列 Table 编号。
- [x] 摘要和结论提及的数值均已定位到 R1-R10；未将背景文献数值混入复现基准。
- [x] 无法提取内容清单：Exhibit 3 声称考虑 25 个宏观驱动，但表内仅能识别 10 个变量；其余 15 项已按 D15-D29 登记为 missing/nonrecoverable，见 A1。Exhibit 2、5、6、7、13、16、17 的曲线未给逐期底层数值，未从图像反推。shadow-rate/市场状态、Refinitiv/FRED-Factset、daily/monthly、March-23/May-23 四组原文冲突均已并列登记，未在提取阶段裁决。
