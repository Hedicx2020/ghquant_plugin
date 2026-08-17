---
report_name: ssrn_6115073
title: Online Portfolio Selection Using Macroeconomic Pattern Matching
institution: University of Southampton (Southampton Business School) / University of Adelaide
report_date: 2025-01-01
authors: Seyed Mehrzad Asaad Sajadi、Sasan Barak、Ali Fereydooni
market: 美股
pdf_pages: 50
exhibit_declared: {fig_max: 18, tbl_max: 8}
element_counts: {D: 4, F: 12, B: 8, R: 5, SA: 6, FIG_registered: 18, TBL_registered: 8}
type_hint: allocation
tags_hint: [ml, factor]
extraction_date: 2026-07-11
---

# Online Portfolio Selection Using Macroeconomic Pattern Matching 复现规格书

> 本文为 SSRN 预印本（abstract=6115073），未经同行评审。原文市场为美股（S&P 500、Dow Jones）+ 日股（Nikkei 225），宏观数据取自 FRED，行情取自 Refinitiv。本规格书忠实记录原文，不做市场迁移与数据映射（迁移为 planner 职责）。
> 说明：frontmatter `report_date` 原文封面未印刷发表日期，2025-01-01 为据「引用文献含 2025 年论文 + 样本外数据延伸至 2025」推断的占位值（见 A18）；`market` 枚举无「多市场股票」选项，取「美股」并在 B1/D1 注明日股 N225。

## 一、研报元信息与结构地图

- 标题：Online Portfolio Selection Using Macroeconomic Pattern Matching
- 作者：Seyed Mehrzad Asaad Sajadi¹、Sasan Barak¹（通讯作者，S.Barak@soton.ac.uk）、Ali Fereydooni²（¹南安普顿大学 Southampton Business School；²阿德莱德大学 Adelaide Business School）
- 关键词：Finance, Pattern Matching, OnLine Portfolio Selection, Macroeconomic Factors, Clustering；JEL：C38, C58, D40
- 章节目录（据正文抄录）：
  - 1. Introduction（p2-p4）
  - 2. Literature Review（2.1 OLPS；2.2 Macroeconomic importance）（p4-p7）
  - 3. Problem formulation（3.1 OLPS formulation）（p7-p8）
  - 4. Methodology（4.1 Asset Selection / 4.2 Assets Clustering / 4.3 Return prediction / 4.4 Joint effect & portfolio construction）（p8-p19）
  - 5. Data explanation and experimental results（5.1 Data；5.2 Experimental results：5.2.1 Scenarios、5.2.2 Return prediction & economic cycles）（p19-p30）
  - 6. Discussion on macroeconomic factors（6.1 Topological Data Analysis）（p30-p35）
  - 7. Conclusion（p36-p37）
  - References（p37-p43）
  - Appendix A–H（p43-p50）

- 页面覆盖表（逐页标注内容类型，供审计 C2 逐页扫描核对）:

  | 页码 | 内容类型 | 关联要素 |
  | --- | --- | --- |
  | p1 | 封面（标题/作者/机构/通讯方式） | - |
  | p2 | 摘要 + 关键词 + JEL + 引言开始 | F1(背景), F2(背景) |
  | p3 | 引言（OLPS、pattern matching、Δβ 引入、三阶段概述） | F2, F3, F4 |
  | p4 | 引言（四步法概述、贡献列表、论文结构）+ 2.1 OLPS 综述开始 | F7, F10, F11, B8 |
  | p5 | 2.1 OLPS 综述（benchmark/CRP/FTW/FTL/pattern-matching 文献） | B8 |
  | p6 | 2.1 综述结尾 / 2.2 宏观重要性综述开始 | - |
  | p7 | 2.2 宏观重要性综述 | - |
  | p8 | 3. 问题形式化 3.1（式1-4 价格相对/组合/财富）+ 两条市场假设 | F1, B6 |
  | p9 | Algorithm 1（OLPS）；4. Methodology + Algorithm 2；4.1 资产选择开始 | F1, F2 |
  | p10 | 4.1 Δβ（式5-8 双区制回归）；Remark 1（18 宏观变量 + BorutaShap） | F2, F12, D2 |
  | p11 | Remark 1（选出 7 因子 IR/UR/GDP/IP/DGDP/CPI/PPI）；4.2 聚类 + MI 引入；图1 | F12, D2, F3, F4, FIG1 |
  | p12 | MI 式9-13；SU 式14；四种聚类模型；Remark 2 最优窗口开始 | F3, F4, F5 |
  | p13 | Remark 2（式15-17 相关性预测/MSE）；Algorithm 3；聚类模型清单；SR 式18/MDD 式19 | F5, F4, B7 |
  | p14 | MDD 式19；VaR（历史模拟最低5%）；分散化指数（Frobenius）；Remark 3 Silhouette；4.3 收益预测开始 | B7, F4, F7 |
  | p15 | 4.3 Matrix profile 定义（Di/MP/MP-index）；Motifs（式20-21） | F6 |
  | p16 | Remark 4（IL/IR 式22-23）；两级流程；图2；MSP 式24-25 | F6, F7, FIG2 |
  | p17 | 信号提取式27；图3；4.4 联合效应开始；Remark 5 溢出引入 | F8, F9, FIG3 |
  | p18 | 溢出指数 VAR（式28-31 方差分解） | F9 |
  | p19 | 溢出方向/净额（式32-35）；归一化式36；5. 数据 5.1（三指数/Refinitiv/FRED） | F9, F10, D1, D2, B1 |
  | p20 | 5.2.1 情景分析（Δβ 双步 OLS/仅取显著系数）；图4（S&P500 收益对 CPI 回归散点） | F2, SA4, FIG4 |
  | p21 | 表1（聚类模型对比 SU/相关性×4指标）；图5（K-Means vs Hierarchical 内部指标） | R2, F4, FIG5 |
  | p22 | 图6（行业资产在各簇分布 SU/相关性） | F4, FIG6 |
  | p23 | 5.2.2 收益预测与经济周期；图7（7 宏观因子相似模式） | F7, FIG7 |
  | p24 | 图8（S&P500 上寻相似期）；六个对比模型/情景定义（CPMM-EW/MV、CPM-EW/MV、PMM、EWMFM） | F7, B8, FIG8 |
  | p25 | 累计收益文字结论（CPMM-EW≈110%/CPMM-MV≈75%/CPM≈25%,5%）；表2/表3 引出；ES 分析引出 | R5, SA5 |
  | p26 | 图9（S&P500 累计收益）；图10（DJ/N225 累计收益） | R5, FIG9, FIG10 |
  | p27 | 表2（6 比率×11 方法×3 市场，主结果） | R1 |
  | p28 | 表3（4 比率×10 方法×3 市场，滚动 3 期 2016-2020/2017-2021/2018-2023） | SA1 |
  | p29 | 表4（β+/β-/Δβ×11 方法×3 市场）+ 下行保护文字 | R3 |
  | p30 | 表5（4 比率×6 设置×3 市场，样本外 2023-2025） | SA2 |
  | p31 | 6. 宏观因子讨论；图11（因子影响排名 2013-2023）；图12（平均排名） | F12, FIG11, FIG12 |
  | p32 | CPI/UR 对不同股票影响讨论；图13（联合效应对比） | F10, FIG13 |
  | p33 | 溢出指数实现（式34）；图14（宏观因子对三指数波动溢出） | F9, FIG14 |
  | p34 | 表6（各宏观因子溢出强度均值×3 指数）；CPI/IR 最强文字结论 | R4 |
  | p35 | 图15（纳入/剔除单一宏观因子对表现影响）；参数评估引出（nc/w/λ） | SA4, SA3, FIG15 |
  | p36 | 表7（CPMM-EW/CPMM-MV 参数敏感性 nc/w/λ，S&P500）；6.1 TDA 开始 | SA3, SA6 |
  | p37 | 6.1 TDA（异常与危机对齐）；图16（IR/CPI/UR 异常）；7. 结论开始 | SA6, FIG16 |
  | p38 | 7. 结论（宏观因子价值、Δβ、未来工作 TE/ESG） | R3(背景), R5(背景) |
  | p39-p43 | References（含 Appendix A 表A.1 于 p43） | TBL8 |
  | p43 | Appendix A（表A.1 18 宏观因子全称/缩写）；Appendix B Boruta 算法开始 | D2, F12, TBL8 |
  | p44 | Appendix B（Boruta 式B.1；SHAP 式B.2；BorutaShap 式B.3） | F12 |
  | p45 | Appendix C（理想相关矩阵 Om 式C.1-C.3 分散化） | B7 |
  | p46 | Appendix D（Hopkins/Calinski-Harabasz 式D.1） | F4 |
  | p47 | Appendix D 续（Davies-Bouldin 式D.2/Dunn 式D.3/Silhouette 式D.4）；Appendix E 图E.1 | F4, SA4, FIG17 |
  | p48 | Appendix F（PSR 式F.1-F.2/Sortino 式F.3/Modigliani 式F.4） | B7 |
  | p49 | Appendix G（扩展相似性 ES 模型定义 ESCPMM-EW/MV）；图G.1 | SA5, FIG18 |
  | p50 | Appendix H（TDA 数学框架：单纯复形/持续同调/异常检测） | SA6 |

## 二、数据要求（D 类）

### [D1] 三大股指成分股日频行情（Refinitiv）
- 页码: p19
- 原文: > "This study gathers data from three stock indices: the S&P 500, Nikkei 225 (N225), and Dow Jones Industrial Average (DJI) ... with market data obtained from Refinitiv"
- 数据状态: derive
- 说明: 原文用美股 S&P 500、道琼斯工业 + 日股 Nikkei 225 的成分股日频收盘价，来源 Refinitiv，区间 1995-01-01 至 2023-01-02（样本外延伸至 2025）。本地 A股无此数据；本地有 usshare_stock_quote（美股 2000-01 起，无 1995-2000、无成分股进出历史）与 A股 ashare_index_components + ashare_stock_price_forward。市场迁移/数据映射由 planner 决定，故标 derive。
- 关联要素: F1, F2, B1, B2 / 关联歧义: A8（市场迁移属 planner 决策，见上说明，非 report 歧义）

### [D2] 宏观经济指标（FRED，18 候选→7 选用）
- 页码: p10-p11, p19, p43
- 原文: > "macroeconomic indicators sourced from the Federal Reserve Economic Data (FRED) database"；> "We study 18 macroeconomic variables ... It selects seven features as the most impactful ones, including: Interest Rate (IR), Unemployment Rate (UR), Gross Domestic Product (GDP), Industrial Production (IP), Debt-to-GDP (DGDP), Consumer Price Index (CPI), and Producer Price Index (PPI)."
- 数据状态: derive
- 说明: 18 候选见表A.1（附录A，p43），逐条为：Consumer Price Index(CPI)、Interest Rate(IR)、Gross Domestic Product(GDP)、Debt to GDP(DGDP)、Industrial Production(IP)、Unemployment Rate(UR)、Producer Price Index(PPI)、Saving Rate(SR)、Balance Trade(BT)、Price To Rent(PTR)、Corporate Profit(CP)、Wage Growth(WG)、Currency Transaction Report(CTR)、Money Supply M2(M2)、Gold Reserve(GR)、Carbon Dioxide Emission(CE)、Consumer Credit(CC)、Household Debt(HHD)（注：Saving Rate 缩写 SR 与本文夏普比率 SR 同形，系原表记法）；BorutaShap 从该 18 项选出 7 个：IR、UR、GDP、IP、DGDP、CPI、PPI。来源 FRED（美国）。本地 A股宏观（macro_cpi/ppi/gdp/industrial_production/money_supply 等）可映射 CPI/PPI/GDP/IP/M2，但 UR（失业率）、DGDP（债务/GDP）无直接本地对应，IR 需以 LPR/国债收益率替代。原文"daily basis"收集但宏观多为月/季频（见 A1）。
- 关联要素: F2, F7, F9, F12, B1 / 关联歧义: A1（市场迁移见上说明）

### [D3] 无风险利率 rf（SR/Sortino/Modigliani 用）
- 页码: p13, p48
- 原文: > "SR = (R − rf)/σ ... rf signifies the risk-free return within the market"
- 数据状态: derive
- 说明: SR（式18）、Sortino（式F.3）、Modigliani（式F.4）均需 rf，原文未指明具体无风险利率序列/来源/频率。本地可用 bond_shibor 或 bond_yield_curve 衍生。
- 关联要素: B7, R1, SA1, SA2 / 关联歧义: A19

### [D4] 股指指数点位序列（Index 基准与 Modigliani 基准 σ_b）
- 页码: p19, p27, p48
- 原文: > "σb is the standard deviation of the benchmark, which is S&P 500, Dow Jones, and Nikkei 225, in this study."
- 数据状态: derive
- 说明: 表2/表4 中的 "Index" 列为三大指数本身作 buy-and-hold 基准；Modigliani 比率用指数收益标准差 σ_b。本地 A股 ashare_csiindex_trade / 美股 osshare_index_price 可映射。
- 关联要素: B7, B8, R1, R3 / 关联歧义: -（市场迁移见上说明）

## 三、因子/策略定义（F 类）

### [F1] OLPS 在线组合框架（价格相对/组合/财富累乘）
- 页码: p6-p8, p9
- 原文: > "vt,i = pt,i / pt−1,i"；> "bt = (bt1,...,btm)⊺, ∆m = {bt : bt ≥ 0, Σ bti = 1}"；> "Sn(bn1 V1n) = S0 · Π_{t=1}^n b⊺t Vt"
- 公式（转写）: 价格相对 v_{t,i}=p_{t,i}/p_{t-1,i}（式1）；期收益 s_t=b⊺_t V_t=Σ_i b_{ti} v_{ti}（式3）；累计财富 S_n=S0·Π_t b⊺_t V_t（式4）；初始 b_1=(1/m,...,1/m）
- 参数: 组合权重非负且和为1（单纯形 ∆m，即长仓、满仓、无杠杆）；T 日用 V_1^{t-1} 决定 b_t
- 依赖数据: D1 / 关联要素: F11 / 关联歧义: A17（±1 信号与权重关系）

### [F2] Delta Beta（Δβ）宏观敏感资产选择（双区制 OLS）
- 页码: p9-p10, p20
- 原文: > "y = α + β+ x + ϵ"（x>0）；> "y = α + β− x + ϵ"（x<0）；> "∆β = β+ − β−"；> "stocks with the highest absolute values of ∆β can be identified"
- 公式（转写）: 标准式 y=α+βX+ε（式5）；按宏观变量变动符号拆两区制：X>0 估 β+（式6），X<0 估 β−（式7）；Δβ=β+−β−（式8）；按 |Δβ| 从大到小选股
- 参数: 用 OLS 分别估 β+/β−；> "only assets with statistically significant coefficients in the OLS method are selected"（仅保留两系数均统计显著者，p20）；> "the use of a threshold for ∆β values can filter out stocks with negligible asymmetric sensitivity"（Δβ 阈值过滤，阈值数值未给）
- 依赖数据: D1, D2 / 关联基准: R3(表4) / 关联歧义: A1(频率对齐), A9(Δβ 阈值), A15(显著性水平)

### [F3] 对称不确定性 SU（含互信息 MI）用于资产关系度量
- 页码: p11-p12
- 原文: > "M I[X, Y ] = H[X] + H[Y ] − H[X, Y ]"（式9）；> "SU[X,Y] = 2 × M I[X,Y] / (H[X]+H[Y])"（式14）
- 公式（转写）: 连续变量 MI 由熵定义（式9-13，H(X)=∫p(x)log(1/p(x))dx 等）；SU=2·MI/(H[X]+H[Y])，归一化到 [0,1]（式14）。用资产收益间 SU 衡量信息相似度
- 参数: > "the evaluation of MI and SU is conducted using in-sample data"（用样本内数据计算，p12）
- 依赖数据: D1 / 关联要素: F4 / 关联歧义: A20

### [F4] 凝聚层次聚类 + Silhouette 定簇数（含四模型对比）
- 页码: p12-p14, p20-p22, p46-p47
- 原文: > "four distinct clustering models are applied ... The most suitable combination—hierarchical clustering with SU—is selected as the final model"；> "we adopt the Silhouette approach ... to identify the most suitable number of clusters"
- 公式（转写）: 候选四模型 = agglomerative hierarchical clustering、K-means、GMM、DBSCAN（p13）；关系度量 = SU 或 correlation；最终选 hierarchical + SU；簇数由 Silhouette（式D.4）确定；每簇选一只资产
- 参数: 内部评价指标 = Hopkins、Silhouette、Calinski-Harabasz（式D.1）、Davies-Bouldin（式D.2）、Dunn（式D.3）（附录D）；组合级评价 = SR/MDD/VaR/Frobenius（见 R2 表1）；> "within each cluster, the asset nearest to the cluster's center is chosen"（选簇中心最近资产，用于聚类模型对比阶段，p14）
- 依赖数据: D1 / 关联基准: R2(表1) / 关联歧义: A2(簇数 nc 具体值未给)

### [F5] 最优窗口长度 w（相关性预测 + MSE，含子簇数 nc）
- 页码: p11-p13
- 原文: > "steps 1 to 5 are implemented for other values of w ∈ {2, . . . , 10}, and the repetition with the least M SE indicates the optimal value of w"；> "rbn′+1,j = Σ_ι (rWι,j × Cm−1,ι)"（式15）
- 公式（转写）: 滚动窗口长度 w；对同簇内窗口计算末窗与各前窗的 Pearson 相关（因簇内 SU 接近故改用相关），rescale 到 [0,1]，预测下一期收益（式15）；MSE（式16）、平均 MSE（式17）；w∈{2,...,10} 取最小平均 MSE 者为最优；Algorithm 3 同时搜 w 与子簇数 nc
- 参数: w∈{2,...,10}（单位为收益序列步长，即日）；窗口滑动直到训练集末，末窗 W_{m-1} 含最近两值（w=2 示例）
- 依赖数据: D1 / 关联要素: F4, F7 / 关联歧义: A2(nc), A7(与 F6 matrix profile 关系)

### [F6] Matrix profile（Z-归一化欧氏距离 + motifs/左右 MP）
- 页码: p14-p15, p16
- 原文: > "M = [min(D1), min(D2), . . . , min(Dn−m+1)], with each min(Di) indicating the smallest Z-normalized Euclidean distance within Di"
- 公式（转写）: 子序列 T_{i,m}（长度 m）；距离剖面 D_i（与全部其他子序列的 Z-归一化欧氏距离）；矩阵剖面 M=各 min(D_i)；矩阵剖面索引 I 记最近邻位置；左/右矩阵剖面 ML/MR（式20-21）与索引 IL/IR（式22-23）；时序链 TSC 定义（motifs）
- 参数: 子序列长度 m（宏观 stage 用"最近一年"；资产 stage 用最优窗口 w，见 F5/F7）
- 依赖数据: D1, D2 / 关联要素: F7 / 关联歧义: A7, A10(m 具体天数)

### [F7] 两阶段 pattern matching（宏观 MSP + 资产窗口预测）
- 页码: p13-p16
- 原文: > "M SP′_CPj = min[SPCPj]"（式24）；> "EP_{i,j} = M SP′_CPj, CPj"（式25）；> "The recent year of each macroeconomic factor is compared to its previous data, and the most similar year in the past to the current year is found"
- 公式（转写）: 阶段1（宏观）：对 7 个宏观因子各自，将"最近一年"当前期 CP 与历史比较，取矩阵剖面最小者为最相似期 MSP（式24），得考察期 EP_{i,j}（式25）；阶段2（资产）：在匹配到的经济周期内，对每只资产用最优窗口（F5）找与当前窗口最相似的历史窗口，预测 n+1 期收益 = 该最相似历史窗口之后一期的实际收益（式26 r̂_{n+1,i,j}=r_{n+1,i,j}）
- 参数: 阶段1 窗口=1 年；阶段2 窗口=w（F5）；每对（资产 i，宏观 j）产一信号
- 依赖数据: D1, D2 / 关联要素: F5, F6, F8 / 关联歧义: A7, A10

### [F8] 信号提取与二值化（±1）
- 页码: p16-p17
- 原文: > "signali,j = { 1, if r̂n+1,i,j|wi,j > 0 ; −1, if r̂n+1,i,j|wi,j ≤ 0 }"（式27）
- 公式（转写）: 对每（资产 i，宏观 j），若预测下一期收益 r̂>0 则 signal=+1，若 ≤0 则 signal=−1（式27）
- 参数: 二值信号 ∈ {+1,−1}
- 依赖数据: - / 关联要素: F7, F10 / 关联歧义: A17(±1 如何进入建仓)

### [F9] 波动率溢出指数（Diebold-Yilmaz VAR）作因子权重
- 页码: p17-p19, p33
- 原文: > "κt = Σ_{i=1}^p Φi κt−i + εt"（式28）；> "S^g_i(U) = S^g_{.i}(U) − S^g_{i.}(U)"（式35 净溢出）；> "γi,j = S^g_i(U) denotes the net spillover value between asset j and macroeconomic factor i"
- 公式（转写）: VAR(p)（式28）→移动平均表示（式29）→广义方差分解 θ̃^g_{ij}(U)（式30-31）→总/方向/净溢出（式32-35）；式34 中 i=宏观因子、j=三大股指；γ_{i,j}=净溢出 S^g_i(U)（资产 j 与宏观 i 之间）
- 参数: VAR 阶数 p、预测步长 U、估计窗口原文未给数值（见 A12）；> "The mean volatility spillovers from CPI to the S&P 500, Dow Jones, and Nikkei 225 are 102.5, 302.7, and 319.3"（见 R4 表6）
- 依赖数据: D1, D2, D4 / 关联要素: F10 / 关联基准: R4(表6), FIG14 / 关联歧义: A12

### [F10] 信号聚合（溢出加权 FS_j）+ 每簇选最强资产
- 页码: p17-p19
- 原文: > "γ̃i,j = (γi,j − min(γj)) / (max(γj) − min(γj))"（式36）；> "F Sj = Σ_{i=1}^n γ̃i,j × signali,j"（式37）；> "one asset with the highest value of F S from each cluster is picked for the final portfolio construction"
- 公式（转写）: 净溢出矩阵按列 min-max 归一化 γ̃_{i,j}（式36）；资产 j 的最终信号 FS_j=Σ_i γ̃_{i,j}·signal_{i,j}（式37，跨 7 个宏观因子加权求和）；每簇选 FS 最高的一只资产入组合
- 参数: 权重=归一化净波动溢出；因子数 n=7
- 依赖数据: - / 关联要素: F8, F9, F11 / 关联基准: FIG13 / 关联歧义: A17

### [F11] 组合构建 EW / MV（每簇选一资产）
- 页码: p4, p19
- 原文: > "The chosen assets are combined for portfolio construction using two methods: the Mean-Variance (MV) model Markowitz (1952) and an Equally Weighted (EW) approach, where each asset carries an equal weight in the portfolio."
- 公式（转写）: 每簇选出的资产（每簇一只）用两法组合：等权 EW（各资产等权）；均值-方差 MV（Markowitz 1952）。对应主模型 CPMM-EW（等权）与 CPMM-MV（MV）
- 参数: MV 模型的目标函数/约束（是否卖空/协方差估计窗口/λ 风险厌恶）原文未详述（见 A11、A3）
- 依赖数据: D1 / 关联要素: F1, F10 / 关联基准: R1, R5 / 关联歧义: A3(λ), A11(MV 形式)

### [F12] BorutaShap 宏观因子筛选（18→7）
- 页码: p9-p11, p30-p31, p43-p44
- 原文: > "employ a feature selection method named BorutaShap Keany (2020) ... It selects seven features as the most impactful ones"；> "BorutaShap is a feature selection method that synergistically combines the Boruta algorithm with SHapley Additive exPlanations (SHAP) values"
- 公式（转写）: Boruta 造影子特征（随机置换），比较原特征与影子最大重要性 Z_i（式B.1）；SHAP 值 φ_i（式B.2）；BorutaShap 用 SHAP 差 Z_i^{SHAP}=φ_i−max(φ_j^{shadow})（式B.3）迭代判定显著特征；从 18 候选选出 7 个（IR/UR/GDP/IP/DGDP/CPI/PPI）
- 参数: 基模型 typically Random Forest 或 XGBoost（附录B）；样本区间/目标变量未完全指定（见 A16）；> "these features are evaluated over time"（随时间动态评估，图11/图12 展示 2013-2023 排名）
- 依赖数据: D2 / 关联基准: FIG11, FIG12 / 关联歧义: A16

## 四、回测设置（B 类）

### [B1] 三市场与股票池
- 页码: p19
- 原文: > "This study gathers data from three stock indices: the S&P 500, Nikkei 225 (N225), and Dow Jones Industrial Average (DJI) ... First, a comprehensive analysis is conducted on the S&P 500 index ... the system is also applied to the N225 and DJI indices."
- 参数值: 三个独立回测：S&P 500（美股，主分析）、Dow Jones Industrial Average（美股）、Nikkei 225（日股）；股票池=各指数成分股；主分析在 S&P 500
- 关联要素: D1, F2, F4 / 关联歧义: A8(成分股规模/时点/幸存者偏差)

### [B2] 数据区间与训练/测试划分
- 页码: p19
- 原文: > "The data used in this study is collected on a daily basis, spanning from 1/1/1995 to 2/1/2023. It is worth mentioning that the period from 1/1/1995 to 31/12/2018 is designated for training to find the optimal length of windows in the pattern-matching part."
- 参数值: 日频；全样本 1995-01-01 至 2023-01-02；训练 1995-01-01 至 2018-12-31（用于确定 pattern-matching 最优窗口长度）；测试区间起点未明说（推测 2019-01-01，见 A6）
- 关联要素: D1, F5 / 关联歧义: A6

### [B3] 滚动窗口子区间（表3）
- 页码: p27-p28
- 原文: > "Table 3 shows how the models performed in three different 4-year periods; from 2016 to 2020, 2017 to 2021, and 2018 to 2023."
- 参数值: 三个 4 年滚动区间：2016-2020、2017-2021、2018-2023（注：2018-2023 实为 5 年跨度，原文称 4-year，见 A21）
- 关联要素: SA1 / 关联歧义: A21

### [B4] 样本外区间 2023-2025（表5）
- 页码: p28, p30
- 原文: > "models with various settings are tested on out-of-sample data from 2023, to 2025, with the results of each model presented in Table 5."
- 参数值: 样本外 2023 至 2025，仅测 6 个内部设置（CPMM-EW/CPMM-MV/CPM-EW/CPM-MV/PMM/EWMFM），不含外部基准
- 关联要素: SA2 / 关联歧义: -（市场迁移见 B2 说明）

### [B5] 组合更新 / 在线调仓（每期滚动）
- 页码: p8, p9, p16
- 原文: > "The manager calculates portfolios sequentially, using the historical sequence of price relative vectors V1^{t−1} available up to each period t. At each period, a new portfolio bt is determined"；> "Assuming a window length of n, we extract a signal for day n+1."
- 参数值: OLPS 每个交易期用截至 t-1 的历史序贯计算 b_t；信号面向 day n+1（T 日算、T+1 执行含义）；调仓频率原文未明确逐日/其他（见 A4）
- 关联要素: F1, F7 / 关联歧义: A4(调仓频率)

### [B6] 交易成本与市场假设
- 页码: p8
- 原文: > "1. Market liquidity: It is assumed that at the last close price of any trading period, one can buy or sell any amount. 2. Market impact: The portfolio selection strategy we employ does not influence the market."
- 参数值: 两条假设=充分流动性（可按收盘价买卖任意量）+ 无市场冲击；未给显式交易成本费率（模型未计入或未说明，见 A5）
- 关联要素: F1 / 关联歧义: A5(交易成本是否计入及费率)

### [B7] 评估指标定义（SR/MDD/VaR/分散化/AR/AStd/PSR/SOR/MR）
- 页码: p13-p14, p24, p45, p48
- 原文: > "SR = (R − rf)/σ"（式18）；> "M DD = (TV − PV)/PV"（式19）；> "The VaR value is then derived by considering the lowest 5% of these historical returns."；> "M R = SR × σb + rf"（式F.4）
- 参数值: SR=（组合均值收益−rf）/σ（式18）；MDD=(谷值−峰值)/峰值（式19）；VaR=历史模拟法，取历史收益最低 5%（p14）；分散化指数=‖CM−IM‖ Frobenius 范数（越小越分散，附录C 式C.1-C.3 以理想矩阵 Om）；AR=年化收益；AStd=年化标准差；PSR=概率夏普（式F.2，Bailey & Lopez de Prado 2012，含偏度 γ3、峰度 γ4、样本长度 L）；SOR=Sortino=（R−rf)/σ−（式F.3，仅下行标准差）；MR=Modigliani=SR·σ_b+rf（式F.4，σ_b 为基准指数标准差）
- 关联要素: R1, R2, SA1, SA2 / 关联歧义: A19, A22

### [B8] 基准模型与对比情景（内部子模型 + 外部基准）
- 页码: p4-p5, p24
- 原文: > "hierarchical risk parity (HRP) ... hierarchical equal risk contribution (HERC) ... online moving average reversion (OLMAR) ... and nested clustered optimization (NCO)"；> 六情景 CPMM-EW / CPMM-MV / CPM-EW / CPM-MV / PMM / EWMFM
- 参数值: 提出的主模型：CPMM-EW（聚类+宏观 pattern matching+等权）、CPMM-MV（+MV）；消融子模型：CPM-EW/CPM-MV（去宏观）、PMM（去聚类，单簇）、EWMFM（宏观等权、无溢出联合效应）；外部基准：Index（指数买入持有）、HRP、HERC、OLMAR、NCO
- 关联要素: F10, F11, R1, R3, SA1 / 关联歧义: A11(各基准实现细节未给)

## 五、研报核心数值结果基准（R 类）

### [R1] 表2 六比率×11 方法×3 市场（主结果）
- 页码: p27
- 原文: > "Table 2: Six different ratios for eleven approaches on several markets. (The bold numbers show the highest value of each ratio ...)"
- 数值表（逐格照抄自 p27 原图，**加粗**=该市场该指标原文加粗最高值；单位：AR/AStd 为比例，其余为比率）:

  | 指标 | 市场 | CPMM-EW | CPMM-MV | CPM-EW | CPM-MV | PMM | EWMFM | Index | HRP | HERC | OLMAR | NCO |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | AR | S&P500 | **0.269** | 0.203 | 0.072 | 0.011 | 0.129 | 0.117 | 0.134 | 0.091 | 0.119 | 0.039 | 0.080 |
  | AR | DowJones | **0.262** | 0.142 | 0.024 | 0.066 | 0.090 | 0.079 | 0.123 | 0.083 | 0.051 | 0.108 | 0.037 |
  | AR | Nikkei225 | **0.300** | 0.224 | 0.032 | 0.131 | 0.180 | 0.129 | 0.099 | 0.048 | 0.065 | 0.173 | 0.154 |
  | AStd | S&P500 | 0.205 | 0.208 | 0.137 | **0.219** | 0.165 | 0.089 | 0.163 | 0.131 | 0.146 | 0.123 | 0.164 |
  | AStd | DowJones | 0.241 | 0.254 | 0.114 | 0.119 | 0.096 | 0.079 | **0.218** | 0.097 | 0.132 | 0.112 | 0.132 |
  | AStd | Nikkei225 | 0.160 | 0.153 | 0.134 | 0.135 | 0.113 | 0.140 | **0.216** | 0.133 | 0.134 | 0.096 | 0.141 |
  | SR | S&P500 | **1.317** | 0.976 | 0.528 | 0.051 | 0.786 | 1.315 | 0.824 | 0.695 | 0.818 | 0.760 | 0.492 |
  | SR | DowJones | **1.091** | 0.562 | 0.215 | 0.560 | 0.941 | 0.802 | 0.566 | 0.863 | 0.385 | 0.964 | 0.284 |
  | SR | Nikkei225 | **1.875** | 1.464 | 0.237 | 0.972 | 1.584 | 1.136 | 0.459 | 0.364 | 0.492 | 1.801 | 1.094 |
  | PSR | S&P500 | **0.836** | 0.523 | 0.752 | 0.491 | 0.657 | 0.636 | 0.532 | 0.519 | 0.530 | 0.608 | 0.636 |
  | PSR | DowJones | **0.723** | 0.522 | 0.505 | 0.587 | 0.516 | 0.521 | 0.512 | 0.517 | 0.621 | 0.519 | 0.641 |
  | PSR | Nikkei225 | **0.715** | 0.643 | 0.393 | 0.394 | 0.397 | 0.400 | 0.520 | 0.379 | 0.646 | 0.400 | 0.407 |
  | SOR | S&P500 | **1.306** | 0.765 | 0.324 | 0.040 | 0.544 | 1.204 | 0.370 | 0.352 | 0.360 | 0.588 | 0.313 |
  | SOR | DowJones | **0.821** | 0.357 | 0.118 | 0.322 | 0.438 | 0.376 | 0.304 | 0.396 | 0.238 | 0.501 | 0.171 |
  | SOR | Nikkei225 | 1.002 | **1.751** | 0.156 | 0.713 | 1.362 | 0.629 | 0.264 | 0.276 | 0.372 | 1.220 | 0.600 |
  | MR | S&P500 | **1.313** | 0.973 | 0.527 | 0.051 | 0.784 | 0.869 | 0.822 | 0.693 | 0.816 | 0.758 | 0.490 |
  | MR | DowJones | **1.088** | 0.561 | 0.215 | 0.559 | 0.939 | 0.463 | 0.564 | 0.861 | 0.384 | 0.961 | 0.283 |
  | MR | Nikkei225 | **1.870** | 1.460 | 0.237 | 0.970 | 1.580 | 1.005 | 0.458 | 0.363 | 0.490 | 1.797 | 1.091 |

- 关联要素: F10, F11, B7, B8

### [R2] 表1 聚类模型对比（SU/相关性×四指标）
- 页码: p21
- 原文: > "Table 1: A comparison of different clustering models' performance based on SU and correlation regarding four metrics."
- 数值表（逐格照抄自 p21 原图，**加粗**=原文加粗）:

  | 关系度量 | 模型 | SR | MDD | VaR | Frobenius Norm |
  | --- | --- | --- | --- | --- | --- |
  | SU | K-Means | 1.393 | **0.369** | **0.449** | 2.124 |
  | SU | Hierarchical | **1.461** | 0.438 | 0.601 | **1.729** |
  | SU | GMM | 1.234 | 0.445 | 0.493 | 2.233 |
  | SU | DBSCAN | 1.297 | 0.471 | 0.463 | 2.233 |
  | Correlation | K-Means | 1.463 | 0.453 | **0.344** | 1.684 |
  | Correlation | Hierarchical | **2.033** | **0.246** | 0.347 | **1.258** |
  | Correlation | GMM | 1.345 | 0.344 | 0.465 | 1.945 |
  | Correlation | DBSCAN | 1.464 | 0.567 | 0.365 | 1.744 |

- 关联要素: F4

### [R3] 表4 β+/β−/Δβ×11 方法×3 市场
- 页码: p29
- 原文: > "Table 4: Different beta ratios for eleven approaches on several markets."（原表无加粗）；> "in the proposed models with β− values of -0.3 and -0.2, we demonstrate that these strategies maintain resilience during market downturns"
- 数值表（逐格照抄自 p29 原图）:

  | 指标 | 市场 | CPMM-EW | CPMM-MV | CPM-EW | CPM-MV | PMM | EWMFM | Index | HRP | HERC | OLMAR | NCO |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | β+ | S&P500 | 0.9 | 0.8 | 0.6 | 0.7 | 0.8 | 0.3 | 1 | 0.6 | 0.6 | 0.7 | 0.4 |
  | β+ | DowJones | 0.9 | 0.75 | 0.55 | 0.6 | 0.7 | 0.35 | 1 | 0.55 | 0.55 | 0.4 | 0.3 |
  | β+ | Nikkei225 | 0.85 | 0.75 | 0.55 | 0.6 | 0.6 | 0.35 | 1 | 0.5 | 0.55 | 0.4 | 0.3 |
  | β− | S&P500 | -0.2 | -0.3 | -0.5 | -0.6 | -0.4 | -0.6 | -1 | -0.4 | -0.4 | -0.8 | -0.6 |
  | β− | DowJones | -0.3 | -0.2 | -0.5 | -0.4 | 0.1 | -0.55 | -1 | -0.42 | -0.35 | -0.5 | -0.55 |
  | β− | Nikkei225 | -0.2 | -0.2 | -0.5 | -0.4 | -0.2 | -0.55 | -1 | -0.5 | -0.55 | -0.5 | -0.6 |
  | Δβ | S&P500 | 0.7 | 0.5 | 0.1 | 0.1 | 0.4 | -0.3 | 0 | 0.2 | 0.2 | -0.1 | -0.2 |
  | Δβ | DowJones | 0.6 | 0.55 | 0.05 | 0.2 | 0.6 | -0.2 | 0 | 0.13 | 0.2 | -0.1 | -0.25 |
  | Δβ | Nikkei225 | 0.65 | 0.55 | 0.05 | 0.2 | 0.3 | -0.2 | 0 | 0.1 | 0.2 | -0.1 | -0.3 |

- 关联要素: F2, B8

### [R4] 表6 各宏观因子波动溢出强度均值×3 指数
- 页码: p34
- 原文: > "Table 6: The mean of each macroeconomic factor's strength on three stock indexes."；> "the mean volatility spillovers from CPI to the S&P 500, Dow Jones, and Nikkei 225 are 102.5, 302.7, and 319.3, respectively."
- 数值表（逐格照抄自 p34 原图，**加粗**=原文加粗最高值）:

  | 宏观因子 | S&P500 | DowJones | Nikkei225 |
  | --- | --- | --- | --- |
  | IR | 58.37 | 173.6 | 172.7 |
  | UR | 16.61 | 49.04 | 53.89 |
  | GDP | 0.318 | 0.941 | 1.053 |
  | IP | 3.988 | 11.78 | 12.82 |
  | DGDP | 4.350 | 12.84 | 14.05 |
  | CPI | **102.5** | **302.7** | **319.3** |
  | PPI | 3.012 | 8.888 | 9.611 |

- 关联要素: F9, D2

### [R5] 图9-10 累计收益（文字数值，近似读图）
- 页码: p24-p25
- 原文: > "CPMM-EW and CPMM-MV had earned the highest amount of return, and they gained around 110% and 75%, respectively"；> "CPM-EW and CPM-MV exhibit the lowest profitability compared to other models, at around 25% and 5%, respectively"；> "CPMM-EW has the best performance ... with almost 105% and 110% on Dow Jones and Nikkei 225, respectively"
- 数值表（原文以"around/almost"给出的近似累计收益，非精确表格值；研报未给精确数值处写 n/a）:

  | 模型 | 市场 | 累计收益(近似) |
  | --- | --- | --- |
  | CPMM-EW | S&P500 | ≈110% |
  | CPMM-MV | S&P500 | ≈75% |
  | CPM-EW | S&P500 | ≈25% |
  | CPM-MV | S&P500 | ≈5% |
  | CPMM-EW | DowJones | ≈105% |
  | CPMM-EW | Nikkei225 | ≈110% |
  | PMM | S&P500 | ≈第三优（与 S&P500 指数相当） |
  | 其余模型/市场精确累计收益 | - | n/a（仅图9/图10 曲线，未列表） |

- 关联要素: F11, B8 / 关联歧义: A23

## 六、图表登记清单（FIG/TBL 全集）

> 登记规则说明：正文编号图/表 = Figure 1–16、Table 1–7；附录含 Figure E.1（附录E）、Figure G.1（附录G）、Table A.1（附录A）。附录图表原生编号为字母+序号（E.1/G.1/A.1），机器门禁首列要求纯数字前缀，故将附录三项按顺延编号登记为 **FIG17=Figure E.1、FIG18=Figure G.1、TBL8=Table A.1**（原生标签见"标题"列，不改变其归属），据此 fig_max=18、tbl_max=8。

| ID | 标题 | 页码 | 摘要 | 复现意图 | 理由/关联要素 |
| --- | --- | --- | --- | --- | --- |
| FIG1 | An illustration of MI and other information metric | p11 | 互信息/联合熵/条件熵关系示意 | reference_only | 概念示意图，无数值；关联 F3 |
| FIG2 | A general schematic of the pattern-matching steps | p16 | 两阶段 pattern matching 流程示意 | reference_only | 流程示意；关联 F7 |
| FIG3 | Signal extraction based on asset i and macroeconomic factor j | p17 | 信号提取示意 | reference_only | 示意图；关联 F8 |
| FIG4 | Regression of S&P 500 stocks' return on CPI | p20 | β+ vs β− 散点，色标 Δβ(-1.5~1.0) | reproduce | 关联 F2；可由 Δβ 计算复现散点 |
| FIG5 | Comparison between K-Means and Hierarchical clustering based on SU and correlation | p21 | Hopkins/Silhouette/CH/DB/Dunn 内部指标平行坐标 | reproduce | 关联 F4, R2 |
| FIG6 | Distribution of the industries' assets into different clusters based on SU and correlation | p22 | 行业资产在各簇分布圆图 | reference_only | 可视化呈现，无独立数值表；关联 F4 |
| FIG7 | Similar patterns in seven different macroeconomic factors to their current windows | p23 | 7 宏观因子相似模式（黑线=当前） | reference_only | pattern matching 示意；关联 F7 |
| FIG8 | A sample of finding similar periods to the current one on S&P 500 index | p24 | S&P500 上 7 段相似期 | reference_only | 示意图；关联 F7 |
| FIG9 | Cumulative return of the proposed approaches and benchmarks on S&P 500 | p26 | 各模型 S&P500 累计收益曲线 | reproduce | 关联 R5, R1；底层数值仅曲线（见 A23） |
| FIG10 | Cumulative return of the proposed approaches and benchmarks on Dow Jones and Nikkei 225 | p26 | DJ/N225 累计收益曲线 | reproduce | 关联 R5, R1 |
| FIG11 | Rank of macroeconomic factors' effects on S&P 500 between 2013 to 2023 | p31 | 因子影响排名时序 | reference_only | 关联 F12；底层排名未表格化 |
| FIG12 | Average of each macroeconomic factor's rank on S&P 500 from 2013 to 2023 | p31 | 各因子平均排名条形 | reference_only | 关联 F12 |
| FIG13 | Comparison of proposed models based on joint effects of macroeconomic factors | p32 | 联合效应对比 | reference_only | 关联 F10；数值见 R1/R3 |
| FIG14 | Volatility spillover from macroeconomic factors to three indexes | p33 | 溢出时序（均值/标准差） | reproduce | 关联 F9, R4；均值见表6 |
| FIG15 | Impact of considering and not considering each macroeconomic factor on the portfolio performance | p35 | 单因子纳入/剔除对 return-SR 影响 | reproduce | 关联 SA4；关键数值见 SA4 文字 |
| FIG16 | Times that experienced anomalies on IR, CPI, and UR and their corresponding on markets' time series | p37 | TDA 异常点与市场时序对齐 | reference_only | 关联 SA6；补充分析 |
| FIG17 | Figure E.1（附录E）: The comparison of different Δβ on six other macroeconomic factors | p47 | 6 个其他宏观因子的 Δβ 散点 | reference_only | 关联 F2, SA4；附录 |
| FIG18 | Figure G.1（附录G）: Comparison of proposed models based on joint effects (Extended Similarity) | p49 | ES 模型（次相似）对比 | reference_only | 关联 SA5；附录 |
| TBL1 | A comparison of different clustering models' performance | p21 | 见 R2 | reproduce | 关联 R2 |
| TBL2 | Six different ratios for eleven approaches on several markets | p27 | 见 R1（主结果） | reproduce | 关联 R1 |
| TBL3 | Four different ratios for ten approaches (rolling 3 periods) | p28 | 见 SA1 | reproduce | 关联 SA1 |
| TBL4 | Different beta ratios for eleven approaches | p29 | 见 R3 | reproduce | 关联 R3 |
| TBL5 | Four different ratios for six settings (OOS 2023-2025) | p30 | 见 SA2 | reproduce | 关联 SA2 |
| TBL6 | Mean of each macroeconomic factor's strength on three indexes | p34 | 见 R4 | reproduce | 关联 R4 |
| TBL7 | Parameter setting of CPMM-EW and CPMM-MV | p36 | 见 SA3 | reproduce | 关联 SA3 |
| TBL8 | Table A.1（附录A）: Full names and abbreviations of 18 examined macroeconomic factors | p43 | 18 宏观因子全称/缩写 | reproduce | 关联 D2, F12 |

## 七、敏感性/稳健性分析（SA 类）

### [SA1] 表3 滚动窗口稳健性（三个 4 年期）
- 页码: p28
- 原文: > "Table 3: Four different ratios for ten approaches on several markets."；> "over the period spanning from 2016 to 2020 ... CPMM-EW consistently surpassed other models"
- 测试设计: 三个滚动区间 2016-2020 / 2017-2021 / 2018-2023，各算 AR/AStd/SR/PSR × 3 市场 × 10 方法（无 Index 列）
- 数值表（逐格转写自 p28 原图，密集小字；**加粗**=该市场该指标原文加粗最高值。注：Tables 3 单元格密集，个别小数位如需逐格核对以原 PDF p28 为准，见 A25）:

  **2016 - 2020**

  | 指标 | 市场 | CPMM-EW | CPMM-MV | CPM-EW | CPM-MV | PMM | EWMFM | HRP | HERC | OLMAR | NCO |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | AR | S&P500 | **0.286** | 0.224 | 0.082 | 0.011 | 0.136 | 0.133 | 0.075 | 0.126 | 0.106 | 0.115 |
  | AR | DowJones | **0.245** | 0.153 | 0.067 | 0.100 | 0.074 | 0.034 | 0.074 | 0.086 | 0.138 | 0.043 |
  | AR | Nikkei225 | **0.333** | 0.253 | 0.053 | 0.173 | 0.163 | 0.076 | 0.093 | 0.094 | 0.234 | 0.153 |
  | AStd | S&P500 | 0.186 | **0.214** | 0.157 | 0.199 | 0.173 | 0.154 | 0.153 | 0.114 | 0.138 | 0.157 |
  | AStd | DowJones | 0.224 | **0.263** | 0.143 | 0.104 | 0.114 | 0.144 | 0.095 | 0.152 | 0.173 | 0.114 |
  | AStd | Nikkei225 | **0.154** | 0.134 | 0.124 | 0.153 | 0.134 | 0.129 | 0.124 | 0.143 | 0.113 | 0.123 |
  | SR | S&P500 | **1.537** | 1.045 | 0.523 | 0.056 | 0.788 | 0.863 | 0.491 | 1.105 | 0.766 | 0.733 |
  | SR | DowJones | **1.093** | 0.582 | 0.473 | 0.966 | 0.650 | 0.236 | 0.780 | 0.569 | 0.797 | 0.378 |
  | SR | Nikkei225 | **2.161** | 1.883 | 0.429 | 1.130 | 1.213 | 0.592 | 0.750 | 0.659 | 2.065 | 1.242 |
  | PSR | S&P500 | **0.803** | 0.515 | 0.763 | 0.485 | 0.663 | 0.431 | 0.526 | 0.546 | 0.635 | 0.625 |
  | PSR | DowJones | **0.697** | 0.484 | 0.484 | 0.556 | 0.494 | 0.442 | 0.535 | 0.645 | 0.467 | 0.554 |
  | PSR | Nikkei225 | **0.823** | 0.624 | 0.313 | 0.364 | 0.353 | 0.638 | 0.363 | 0.615 | 0.445 | 0.464 |

  **2017 - 2021**

  | 指标 | 市场 | CPMM-EW | CPMM-MV | CPM-EW | CPM-MV | PMM | EWMFM | HRP | HERC | OLMAR | NCO |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | AR | S&P500 | **0.204** | 0.195 | 0.093 | 0.035 | 0.114 | 0.087 | 0.115 | 0.107 | 0.061 | 0.095 |
  | AR | DowJones | **0.234** | 0.174 | 0.047 | 0.094 | 0.124 | 0.046 | 0.114 | 0.084 | 0.094 | 0.055 |
  | AR | Nikkei225 | **0.354** | 0.234 | 0.053 | 0.113 | 0.153 | 0.110 | 0.053 | 0.075 | 0.155 | 0.145 |
  | AStd | S&P500 | **0.276** | 0.223 | 0.153 | 0.237 | 0.173 | 0.163 | 0.184 | 0.142 | 0.155 | 0.174 |
  | AStd | DowJones | 0.195 | **0.232** | 0.123 | 0.164 | 0.095 | 0.135 | 0.084 | 0.153 | 0.125 | 0.114 |
  | AStd | Nikkei225 | 0.153 | 0.145 | 0.153 | **0.158** | 0.145 | 0.115 | 0.112 | 0.143 | 0.113 | 0.135 |
  | SR | S&P500 | 0.741 | **0.875** | 0.608 | 0.149 | 0.661 | 0.532 | 0.628 | 0.753 | 0.396 | 0.547 |
  | SR | DowJones | 1.198 | 0.750 | 0.286 | 0.765 | 1.304 | 0.343 | **1.354** | 0.550 | 0.752 | 0.485 |
  | SR | Nikkei225 | **2.309** | 1.608 | 0.348 | 0.714 | 1.055 | 0.951 | 0.475 | 0.526 | 1.370 | 1.073 |
  | PSR | S&P500 | **0.643** | 0.467 | 0.576 | 0.457 | 0.523 | 0.331 | 0.503 | 0.553 | 0.573 | 0.602 |
  | PSR | DowJones | **0.785** | 0.543 | 0.514 | 0.556 | 0.434 | 0.253 | 0.456 | 0.565 | 0.534 | 0.514 |
  | PSR | Nikkei225 | **0.784** | 0.575 | 0.415 | 0.425 | 0.356 | 0.546 | 0.338 | 0.663 | 0.467 | 0.435 |

  **2018 - 2023**

  | 指标 | 市场 | CPMM-EW | CPMM-MV | CPM-EW | CPM-MV | PMM | EWMFM | HRP | HERC | OLMAR | NCO |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | AR | S&P500 | **0.284** | 0.225 | 0.088 | 0.071 | 0.149 | 0.099 | 0.084 | 0.134 | 0.093 | 0.081 |
  | AR | DowJones | **0.274** | 0.136 | 0.046 | 0.104 | 0.073 | 0.143 | 0.103 | 0.045 | 0.123 | 0.104 |
  | AR | Nikkei225 | **0.284** | 0.204 | 0.083 | 0.123 | 0.153 | 0.174 | 0.087 | 0.093 | 0.152 | 0.113 |
  | AStd | S&P500 | 0.195 | 0.197 | 0.145 | **0.225** | 0.156 | 0.173 | 0.125 | 0.167 | 0.115 | 0.124 |
  | AStd | DowJones | 0.223 | **0.224** | 0.134 | 0.124 | 0.103 | 0.165 | 0.134 | 0.145 | 0.174 | 0.156 |
  | AStd | Nikkei225 | 0.173 | 0.143 | **0.174** | 0.153 | 0.125 | 0.178 | 0.153 | 0.142 | 0.114 | 0.163 |
  | SR | S&P500 | 0.741 | **0.875** | 0.608 | 0.149 | 0.661 | 0.570 | 0.628 | 0.753 | 0.396 | 0.547 |
  | SR | DowJones | **1.222** | 0.731 | 0.345 | 0.838 | 0.709 | 0.864 | 0.769 | 0.312 | 0.707 | 0.665 |
  | SR | Nikkei225 | **1.454** | 1.140 | 0.606 | 0.316 | 0.956 | 0.974 | 0.672 | 0.802 | 0.808 | 0.652 |
  | PSR | S&P500 | **0.643** | 0.467 | 0.576 | 0.457 | 0.523 | 0.253 | 0.503 | 0.553 | 0.573 | 0.602 |
  | PSR | DowJones | **0.834** | 0.613 | 0.523 | 0.614 | 0.554 | 0.277 | 0.485 | 0.621 | 0.553 | 0.604 |
  | PSR | Nikkei225 | **0.863** | 0.622 | 0.713 | 0.512 | 0.645 | 0.473 | 0.523 | 0.578 | 0.668 | 0.577 |

- 关联要素: R1, B3 / 关联歧义: A25, A26

### [SA2] 表5 样本外稳健性（2023-2025，6 设置）
- 页码: p30
- 原文: > "Table 5: Four different ratios for six different settings on several markets."；> "models with various settings are tested on out-of-sample data from 2023, to 2025"
- 测试设计: 样本外 2023-2025，仅 6 内部设置，AR/AStd/SR/PSR × 3 市场
- 数值表（逐格照抄自 p30 原图，**加粗**=原文加粗最高值）:

  | 指标 | 市场 | CPMM-EW | CPMM-MV | CPM-EW | CPM-MV | PMM | EWMFM |
  | --- | --- | --- | --- | --- | --- | --- | --- |
  | AR | S&P500 | **0.082** | 0.042 | 0.009 | 0.011 | 0.012 | 0.0347 |
  | AR | DowJones | **0.091** | 0.0873 | 0.043 | 0.051 | 0.0634 | 0.077 |
  | AR | Nikkei225 | **0.0925** | 0.0824 | 0.047 | 0.0563 | 0.0564 | 0.0754 |
  | AStd | S&P500 | 0.352 | 0.328 | **0.366** | 0.253 | 0.321 | 0.364 |
  | AStd | DowJones | 0.272 | 0.264 | **0.301** | 0.233 | 0.188 | 0.204 |
  | AStd | Nikkei225 | 0.201 | 0.202 | **0.295** | 0.255 | 0.233 | 0.199 |
  | SR | S&P500 | 0.2324 | 0.1280 | 0.0246 | 0.0435 | 0.0374 | 0.9533 |
  | SR | DowJones | 0.3346 | 0.3307 | 0.1429 | 0.2189 | 0.3372 | 0.3775 |
  | SR | Nikkei225 | 0.4602 | 0.4079 | 0.1593 | 0.2208 | 0.2421 | 0.3789 |
  | PSR | S&P500 | **0.635** | 0.553 | 0.452 | 0.047 | 0.527 | 0.513 |
  | PSR | DowJones | **0.532** | 0.512 | 0.445 | 0.418 | 0.496 | 0.504 |
  | PSR | Nikkei225 | **0.671** | 0.634 | 0.373 | 0.294 | 0.533 | 0.611 |

- 关联要素: R1, B4 / 关联歧义: A13(SR 列 EWMFM 值如 S&P500 0.9533 与 AR/AStd 不自洽，疑小数点笔误)

### [SA3] 表7 参数敏感性（nc/w/λ，S&P500）
- 页码: p35-p36
- 原文: > "Table 7: Parameter setting of CPMM-EW and CPMM-MV."；> "the number of clusters (nc), length of windows (w), and the number of considered macroeconomic factors (7), lambda (λ), are assigned different values"
- 测试设计: 在 S&P500 上对 CPMM-EW 变 nc（nc-2..nc+2）、变 w（w-2..w+2），对 CPMM-MV 变 λ（λ-2..λ+2），各看 Return/Std/SR/PSR；证明选定参数稳健
- 数值表（逐格照抄自 p36 原图，**加粗**=原文加粗最优列。注：CPMM-EW nc 组表头第 4 列原文印作"nc−1"（与第 2 列重复），疑应为"nc+1"，见 A14）:

  | 模型/组 | 指标 | 列1 | 列2 | 列3(基准) | 列4 | 列5 |
  | --- | --- | --- | --- | --- | --- | --- |
  | CPMM-EW (nc: nc−2/nc−1/nc/nc−1/nc+2) | Return | 0.201 | 0.214 | **0.269** | 0.235 | 0.198 |
  | CPMM-EW (nc) | Std | 0.224 | 0.234 | **0.205** | 0.215 | 0.225 |
  | CPMM-EW (nc) | SR | 0.898 | 0.914 | **1.317** | 1.092 | 0.881 |
  | CPMM-EW (nc) | PSR | 0.774 | 0.795 | **0.836** | 0.743 | 0.694 |
  | CPMM-EW (w: w−2/w−1/w/w+1/w+2) | Return | 0.215 | 0.226 | **0.269** | 0.253 | 0.243 |
  | CPMM-EW (w) | Std | 0.249 | 0.214 | **0.205** | 0.221 | 0.237 |
  | CPMM-EW (w) | SR | 0.836 | 1.056 | **1.317** | 1.146 | 0.985 |
  | CPMM-EW (w) | PSR | 0.673 | 0.778 | **0.836** | 0.801 | 0.753 |
  | CPMM-MV (λ: λ−2/λ−1/λ/λ+1/λ+2) | Return | **0.236** | 0.214 | 0.203 | 0.185 | 0.172 |
  | CPMM-MV (λ) | Std | 0.262 | 0.243 | 0.208 | 0.200 | **0.197** |
  | CPMM-MV (λ) | SR | 0.900 | 0.881 | **0.976** | 0.926 | 0.873 |
  | CPMM-MV (λ) | PSR | 0.502 | 0.514 | **0.523** | 0.491 | 0.489 |

- 关联要素: F4, F5, F11 / 关联歧义: A2(nc 基准值), A3(λ 定义), A14(表头笔误)

### [SA4] 图15 单因子纳入/剔除敏感性（CPI/IR 最关键）
- 页码: p32, p35, p47
- 原文: > "using only CPI and IR results in the highest Sharpe Ratios, approximately 0.5 and 0.41, respectively. Moreover, excluding CPI and IR from the analysis results in the largest losses for the system, with Sharpe Ratios (SRs) approximately 0.9 and 1.1, respectively."
- 测试设计: 对 CPMM-EW，分别"仅用单个宏观因子"（圆点）与"剔除单个因子用其余六个"（三角）看 return-SR 变化；CPI/IR 为最关键因子
- 结论: > "The system performs best when considering only one macroeconomic factor, with peak performance observed for CPI and IR"；仅 CPI/IR 时 SR≈0.5/0.41；剔除 CPI/IR 时 SR≈0.9/1.1（原文"largest losses"却给出更高 SR 值，表述存疑，见 A24）；另附录E 图E.1 给出其他六因子 Δβ 散点
- 关联要素: F10, F12, D2 / 关联歧义: A24

### [SA5] 附录G 扩展相似性（ES，次相似模式）
- 页码: p25, p49
- 原文: > "This approach is referred to as Extended Similarity (ES) ... The results show that while secondary similarity patterns still hold predictive power, their response for shifting dynamics of economic conditions exhibits higher variability and decreases the cumulative return in general."
- 测试设计: 用"第二相似"模式替代"最相似"模式，构造 ESCPMM-EW、ESCPMM-MV，与主模型对比（图G.1）
- 结论: > "secondary similarity patterns still hold predictive value, their influence on portfolio behavior may exhibit higher variability"（次相似仍有预测力但波动更大、累计收益总体下降）；具体数值仅图G.1，未表格化
- 关联要素: F7, R1 / 关联歧义: A23

### [SA6] 6.1 节 TDA 拓扑异常分析（补充验证）
- 页码: p35-p37, p50
- 原文: > "we employ Topological Data Analysis (TDA) to detect structural anomalies within key economic indicators ... utilize the three most influential macroeconomic factors identified in Table 6"；> "anomalies in IR and CPI in 2009 and 2020 align with known economic crises"
- 测试设计: 对三个最强宏观因子（CPI/IR/UR）用 TDA（单纯复形+持续同调+异常检测，附录H）检测异常时窗，验证与市场结构断点/危机（2009/2020/2023）对齐；追溯至 1997
- 结论: > "the integration of TDA into our analysis highlights the complex interplay between macroeconomic patterns and financial market dynamics"（补充定性验证，非主回测指标）
- 关联要素: F9, R4 / 关联歧义: A27

## 八、提取自检声明
- [x] 逐页扫描确认：report_text.md 全部 `===== PAGE 1 =====` 至 `===== PAGE 50 =====` 已逐页过目，无整页跳过；版面竖排水印碎片（iew/ed/ev/er/pe/ot/tn/rin/ep/Pr = "Preprint not peer reviewed / Electronic copy available at ssrn.com"）已识别为噪声、未当作要素。
- [x] 图表编号全登记：正文编号图 1-16、表 1-7 已全登记（FIG1-16、TBL1-7）；附录 Figure E.1/Figure G.1/Table A.1 顺延登记为 FIG17/FIG18/TBL8（原生标签保留在标题列）；无编号跳缺。
- [x] 摘要/结论提及数值均可定位：摘要"superior probabilistic Sharpe ratios""negative β / positive β"→ R1(PSR)、R3(表4 β+/β−)；结论"CPI and IR most influential"→ R4/SA4；"twice/one-and-a-half profitable"→ R5。
- [x] 无法提取内容清单：
  1. 多数图（Figure 6/7/8/9/10/11/12/13/14/15/16、E.1、G.1）为图像绘制，其底层逐点数值原文未表格化——累计收益/排名/溢出时序仅曲线可读，本 spec 已就 R5/R4 抄录文中给出的近似或均值数值，曲线级精确序列无法提取（属研报未提供，非解析失败）。
  2. 部分公式在 pdftotext 提取中出现符号错位/乱码（式2、式13、式30-34 上下标/求和号），已回原 PDF 逐式核对转写；无残留无法识别公式。
  3. 预印本封面未印刷发表日期，report_date=2025-01-01 为据 2025 年引文与样本外区间推断的占位值（见 A18）。
  4. 以下参数原文确未给出具体数值（登记于 ambiguities，非解析失败）：聚类簇数 nc 的取值（A2）、λ 定义与取值（A3）、Δβ 阈值（A9）、交易成本费率（A5）、无风险利率序列（A19）、VAR 阶数 p/步长 U（A12）、OLS 显著性水平（A15）、PSR 基准 SR*（A22）、BorutaShap 基模型/样本设定（A16）。
  5. Table 3（p28）单元格密集小字，逐格转写已完成但个别小数位存在图像判读风险，已标注以原 PDF 为准（A25）。
