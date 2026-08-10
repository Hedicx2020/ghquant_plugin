---
report_name: r007_cross_market_return_forecasting
title: A Bipartite Graph Approach to U.S.-China Cross-Market Return Forecasting
institution: University of Oxford、Neoma Business School、University of California Los Angeles
report_date: 2026-04-14
authors: Jing Liu、Maria Grith、Xiaowen Dong、Mihai Cucuringu
market: 多资产
pdf_pages: 40
exhibit_declared: {fig_max: 19, tbl_max: 1}
element_counts: {D: 9, F: 24, B: 11, R: 4, SA: 7, FIG_registered: 19, TBL_registered: 1}
type_hint: ml
tags_hint: [cross_market, graph]
extraction_date: 2026-07-26
---

# A Bipartite Graph Approach to U.S.-China Cross-Market Return Forecasting 复现规格书

## 一、研报元信息与结构地图

- 标题：A Bipartite Graph Approach to U.S.-China Cross-Market Return Forecasting。
- 作者：Jing Liu、Maria Grith、Xiaowen Dong、Mihai Cucuringu。
- 机构：University of Oxford、Neoma Business School、University of California Los Angeles。
- 发布日：正文未印刷发布日期；frontmatter 暂登记 PDF 元数据日期 2026-04-14，见 A1。
- 章节目录抄录：1 Introduction（p2-p4）；2 Related Literature（p4-p8）；3 Data（p8-p9）；4 Methodology（p9-p20）；5 Experiments（p20-p28）；6 Conclusion and Future Research（p28-p29）；References（p29-p35）；Appendix A–E（p35-p40）。
- 页面覆盖表：

  | 页码 | 内容类型 | 关联要素 |
  | --- | --- | --- |
  | p1 | 封面、摘要 | R1 |
  | p2 | 关键词、JEL、引言与文献背景 | - |
  | p3 | 研究贡献、方向性结论、局限、结构 | B9, B11, R1 |
  | p4 | 引言结尾、相关文献 | - |
  | p5 | 相关文献：跨市场、图方法 | - |
  | p6 | 相关文献：图神经网络 | - |
  | p7 | 相关文献：金融机器学习 | - |
  | p8 | 相关文献结尾、数据来源、样本期、收益定义 | D1, D2, F1 |
  | p9 | 收益公式、ETF、股票池、缩尾、方法概览 | D3-D6, F2-F3, B1-B3 |
  | p10 | 有向二部图、滚动窗口与交易日历 | D8, F4 |
  | p11 | Figure 1、回归 t 统计量与筛选局限 | F4-F5 |
  | p12 | Figure 2、阈值 τ=2、边筛选 | F5, B4 |
  | p13 | Figure 3、行业分组热图 | D9, F4 |
  | p14 | Figure 4、入度分位数、机器学习预测窗口 | F6-F8 |
  | p15 | Figure 5、市场时段、滞后方向、预测方程 | D8, F8-F9, B4 |
  | p16 | Figure 6、Figure 7 | F4, F9, B4, B8 |
  | p17 | 十种模型概览、OLS、LASSO | F9-F11, B11 |
  | p18 | LASSO、RIDGE、SVM、XGBoost | F11-F14 |
  | p19 | XGBoost、LGBM、RF、AdaBoost、ensemble-avg | F14-F18 |
  | p20 | ensemble-med、评估指标、PnL 与流动性上限 | D7, F18-F20, B9-B10 |
  | p21 | Sharpe 公式、局限、训练窗、更新频率、预测期 | F21, B5-B9 |
  | p22 | 两个预测方向、两个同市场基线、分位组合开头 | F22-F24, B4 |
  | p23 | 分位组合、Figure 8、主结果叙述 | F24, R1 |
  | p24 | Figure 9、Figure 11-13 的比较结论 | R3-R4 |
  | p25 | Figure 10 | F20, F24 |
  | p26 | Figure 11、Figure 12 | F22-F24 |
  | p27 | Figure 13、图结构随机替换敏感性 | SA1 |
  | p28 | 时间滞后敏感性、Figure 14、结论开头 | SA1-SA2 |
  | p29 | 结论、未来研究、利益冲突、参考文献 | R1 |
  | p30 | 参考文献 | - |
  | p31 | 参考文献 | - |
  | p32 | 参考文献 | - |
  | p33 | 参考文献 | - |
  | p34 | 参考文献 | - |
  | p35 | 参考文献结尾、Appendix A–C 说明 | SA3-SA5 |
  | p36 | Table A.1 超参数敏感性数值 | R2, SA3 |
  | p37 | Figure B.1、Figure B.2 | SA4 |
  | p38 | SPY 冲击条件分析、Figure C.1、Appendix D | SA5-SA6 |
  | p39 | Figure D.1、Appendix E | SA6-SA7 |
  | p40 | Figure E.1 | SA7 |

## 二、数据要求（D 类）

### [D1] 美国个股日频数据
- 页码: p8
- 原文: > "Daily U.S. stock data are sourced from the Center"
- 数据状态: missing
- 说明: 研报指定 CRSP，覆盖 NYSE 与 Nasdaq，样本期为 2014–2021；本地目录未声明 CRSP 来源。
- 关联要素: F1-F24, B1, B5-B7 / 关联歧义: A3

### [D2] 中国个股日频数据
- 页码: p8
- 原文: > "daily Chinese stock data are sourced from the Wind Database"
- 数据状态: missing
- 说明: 研报指定 Wind，覆盖 SSE 与 SZSE，样本期为 2014–2021；本地目录未声明 Wind 来源。
- 关联要素: F1-F24, B1, B5-B7 / 关联歧义: A3

### [D3] 个股日开盘价与收盘价
- 页码: p9
- 原文: > "Here pi,cl and pi,op denote the closing and opening price of stock i"
- 数据状态: available
- 说明: 计算个股 pvCLCL 与 OPCL 对数原始收益所需。
- 关联要素: F1-F3

### [D4] 美国市场 ETF SPY
- 页码: p9
- 原文: > "We use SPY as the market ETF in the U.S."
- 数据状态: missing
- 说明: 需要 SPY 日开收盘价以计算 pvCLCL 与 OPCL 市场收益；本地目录未单列 ETF 行情。
- 关联要素: F3, SA5

### [D5] 中国市场 ETF 513500.SH
- 页码: p9
- 原文: > "513500.SH in China."
- 数据状态: missing
- 说明: 需要 513500.SH 日开收盘价以计算 pvCLCL 与 OPCL 市场收益；本地目录仅列基金净值。
- 关联要素: F3

### [D6] 个股平均市值
- 页码: p9
- 原文: > "We select 500 stocks with the highest average market capitalizations"
- 数据状态: available
- 说明: 美国与中国各选 500 只，平均市值按 2014–2021 全样本计算。
- 关联要素: B1

### [D7] 个股日成交量
- 页码: p20
- 原文: > "the median daily traded volume of stock i over the 21-day interval"
- 数据状态: available
- 说明: 计算各股票预测日前 21 日成交量中位数，用于仓位金额。
- 关联要素: F20, B10

### [D8] 两国交易日历与交易时段
- 页码: p10, p15
- 原文: > "uses the trading calendar rather than the natural calendar."
- 数据状态: derive
- 说明: 研报按交易日而非自然日对齐；中国交易日历可直接取得，美国日历需由行情日期衍生。
- 关联要素: F4, F8-F9, B4-B8 / 关联歧义: A4

### [D9] 美国与中国个股行业分类
- 页码: p13
- 原文: > "black grid lines delineate sectoral boundaries."
- 数据状态: missing
- 说明: 中国行业分类可得，但本地目录未列美国个股行业字段；研报未说明行业分类体系。
- 关联要素: F6-F7, SA6 / 关联歧义: A5

## 三、因子/策略定义（F 类）

### [F1] pvCLCL 对数原始收益
- 页码: p8
- 原文: > "The pvCLCL logarithmic raw return for stock i on day t can be calculated by:"
- 公式（转写）: R_i,pvCLCL^(t) = log(p_i,cl^(t) / p_i,cl^(t-1))
- 参数: 当日收盘价相对上一交易日收盘价。
- 依赖数据: D3

### [F2] OPCL 对数原始收益
- 页码: p9
- 原文: > "the OPCL logarithmic raw return for stock i on day t can be calculated by:"
- 公式（转写）: R_i,OPCL^(t) = log(p_i,cl^(t) / p_i,op^(t))
- 参数: 当日收盘价相对当日开盘价。
- 依赖数据: D3

### [F3] 个股市场超额收益
- 页码: p9
- 原文: > "the market excess return of stock i on day t can be defined as:"
- 公式（转写）: r_i^(t)=R_i,pvCLCL^(t)-R_ETF,pvCLCL^(t)，或 r_i^(t)=R_i,OPCL^(t)-R_ETF,OPCL^(t)
- 参数: 美国市场 ETF=SPY；中国市场 ETF=513500.SH。
- 依赖数据: D3-D5 / 关联要素: B3

### [F4] 滚动窗口有向二部图
- 页码: p10-p11
- 原文: > "We represent two different markets, the source market X and target market Y"
- 定义: 源市场 X 与目标市场 Y 分属两个点集，边从 X 指向 Y；对每个有序股票对在回看窗口内做 y 对 x 的一元线性回归。
- 窗口: x=[r_Xj^(t-l-w),...,r_Xj^(t-l-1)]；y=[r_Yi^(t-w),...,r_Yi^(t-1)]。
- 图表示: 二邻接矩阵行对应 X，列对应 Y，元素为边权。
- 依赖数据: D1-D3, D8 / 关联要素: F5, B4-B8

### [F5] t 统计量筛边
- 页码: p11-p12
- 原文: > "In our experiments, we set τ = 2, and select edges whenever |tβ | > τ"
- 公式（转写）: β=cov(x,y)/var(x)；se=sqrt(SSE/(w-2))；tβ=β/[se/sqrt(Σ(x_i-x̄)^2)]。
- 参数: τ=2；当 |tβ|>τ 时，从 Xj 到 Yi 建立有向边。
- 用途: 作为稀疏化与特征筛选启发式，不作为多重检验校正或因果识别。
- 关联要素: F4, F8

### [F6] 时间平均与行业块聚合
- 页码: p13-p14
- 原文: > "we average the daily biadjacency matrices across the full sample period"
- 定义: 先将全样本日度二邻接矩阵取平均，再对行业×行业块内绝对 t 统计量取中位数。
- 输出: Figure 4 行业层面绝对中位 t 统计量热图。
- 依赖数据: D9 / 关联要素: F4-F5

### [F7] 目标节点入度分位数
- 页码: p14-p15
- 原文: > "the 25th, 50th, and 75th percentiles of the in-degree distribution"
- 定义: 每日对所有目标节点的入度分布计算 25%、50%、75% 分位数。
- 输出: Figure 5；蓝线为 US-CN，红线为 CN-US。
- 趋势原文: > "the in-degree in both directions increases"
- 趋势结论: 两个预测方向的入度均随时间上升，研报据此认为样本期内跨市场预测连接增强。
- 关联要素: F4-F5

### [F8] 二部图选出的跨市场预测变量
- 页码: p15
- 原文: > "we select n stocks, i.e., X1 , X2 , ..., Xn from market X"
- 定义: 对目标股票 Yi，选取与其跨市场预测关联最强的 n 只源市场股票，以 t-l 日收益作为预测变量。
- 参数: n 未给出；“最强”与阈值筛边的衔接未完全说明。
- 关联要素: F4-F5, F9-F19 / 关联歧义: A2

### [F9] 通用机器学习预测方程
- 页码: p15-p17
- 原文: > "Here, the function Fi represents the different machine learning methods we use"
- 公式（转写）: r_Yi^(t)=F_i(r_X1^(t-l),...,r_Xn^(t-l);θ)+ε_i^(t)
- 定义: 每个滚动训练窗口内估计模型，并做样本外预测。
- 关联要素: F8, F10-F19, B5-B8

### [F10] OLS 模型
- 页码: p17
- 原文: > "The main idea of OLS is to estimate regression coefficients"
- 公式（转写）: r_Yi^(t)=α_i+Σ_j β_ij r_Xj^(t-l)+ε_i^(t)；最小化 ||y-α_i1-Xw||_2^2。
- 参数: 无超参数。
- 关联要素: F9

### [F11] LASSO 模型
- 页码: p17-p18
- 原文: > "It uses ℓ1 -norm regularization to impose a penalty"
- 公式（转写）: 最小化 (1/(2d))||y-α_i1-Xw||_2^2+λ||w||_1。
- 参数: λ 为正则化参数；主结果所用 λ 未说明，附录网格见 SA3。
- 关联要素: F9, SA3 / 关联歧义: A6

### [F12] RIDGE 模型
- 页码: p18
- 原文: > "It adds ℓ2 -norm regularization to the linear least squares loss function."
- 公式（转写）: 最小化 ||y-α_i1-Xw||_2^2+λ||w||_2^2。
- 参数: λ 为正则化参数；主结果所用 λ 未说明，附录网格见 SA3。
- 关联要素: F9, SA3 / 关联歧义: A6

### [F13] SVM 模型
- 页码: p18
- 原文: > "We use the radial basis function kernel throughout our experiment."
- 定义: 研报给出带拉格朗日乘子 α_j、核 K(x_j,x_k)、约束 0≤α_j≤C 的对偶优化式。
- 参数: RBF 核；C 控制平坦性与超过 ε 的偏差容忍；主结果的 C、ε、核尺度未说明。
- 关联要素: F9, SA3 / 关联歧义: A6, A7

### [F14] XGBoost 模型
- 页码: p18-p19
- 原文: > "XGBoost is a scalable end-to-end tree boosting method"
- 公式（转写）: ŷ_j=Σ_k f_k(x_j)；目标为 Σ_j l(ŷ_j,y_j)+Σ_k Ω(f_k)，Ω(f)=γM+(1/2)λ||w||^2。
- 参数: 树深、学习率、估计器数的附录网格见 SA3；主结果取值未说明。
- 关联要素: F9, SA3 / 关联歧义: A6

### [F15] LGBM 模型
- 页码: p19
- 原文: > "Two key techniques employed by LGBM are Gradient-Based One-Side Sampling"
- 定义: 使用 Gradient-Based One-Side Sampling 与 Exclusive Feature Bundling。
- 参数: 叶子数、学习率、估计器数的附录网格见 SA3；主结果取值未说明。
- 关联要素: F9, SA3 / 关联歧义: A6

### [F16] Random Forests 模型
- 页码: p19
- 原文: > "Random forests consist of an ensemble of decision trees."
- 定义: 每棵树用 bootstrap 样本，在节点随机选取特征子集，最终预测为各树输出平均。
- 参数: 树深与估计器数的附录网格见 SA3；主结果取值未说明。
- 关联要素: F9, SA3 / 关联歧义: A6

### [F17] AdaBoost 模型
- 页码: p19
- 原文: > "We choose a decision tree regressor as the base learner in our experiment."
- 定义: 逐轮提高此前误差较大样本的权重，聚合弱学习器的概率预测。
- 参数: 基学习器为决策树回归器；树深、估计器数、学习率附录网格见 SA3。
- 关联要素: F9, SA3 / 关联歧义: A6

### [F18] ensemble-avg
- 页码: p19-p20
- 原文: > "we take the average of the prediction results from the eight methods above"
- 定义: 对每只股票、每个交易日，将前述八种模型的预测结果取平均作为最终输出。
- 关联要素: F10-F17

### [F19] ensemble-med
- 页码: p20
- 原文: > "we take the median of the prediction results from the eight methods"
- 定义: 对每只股票、每个交易日，将前述八种模型的预测结果取中位数作为最终输出。
- 关联要素: F10-F17

### [F20] 日度 PnL
- 页码: p20
- 原文: > "The PnL on day t is calculated with the following equation:"
- 公式（转写）: PnL(t)=Σ_i sign(s_i^(t))·r_i^(t)·b_i^(t)。
- 仓位: b_i^(t)=min(0.001×mdv_i^(21),L)，mdv 为预测日前 21 日成交量中位数。
- 依赖数据: D7 / 关联要素: B9-B10, F24

### [F21] 年化 Sharpe Ratio
- 页码: p20-p21
- 原文: > "The annualized SR is given by:"
- 公式（转写）: SR=(μ_PnL^(T)/σ_PnL^(T))×sqrt(252)。
- 参数: 以长度为 T 的日度 PnL 均值和标准差计算；一年按 252 个交易日。
- 关联要素: F20, R1-R2

### [F22] 非图同市场基线
- 页码: p22
- 原文: > "the previous 25 days of daily return data are used as predictive features."
- 公式（转写）: r_Yi^(t)=F_i(r_Yi^(t-25),...,r_Yi^(t-1);θ)+ε_i^(t)。
- 参数: 25 日特征可全为 pvCLCL 或全为 OPCL；训练窗 250 日；每 10 日更新。
- 关联要素: F9-F19, B5-B6

### [F23] 图结构同市场基线
- 页码: p22
- 原文: > "this baseline sets markets X and Y identical"
- 定义: X 与 Y 设为同一市场，预测变量从同市场图中选取；响应值领先预测变量一日。
- 参数: l=1。
- 关联要素: F4-F9

### [F24] 绝对预测收益嵌套分位组合
- 页码: p22-p23
- 原文: > "stocks are ranked by the absolute value of their predicted returns"
- 定义: qr1=全部；qr2=绝对预测收益前 80%；qr3=前 60%；qr4=前 40%；qr5=前 20%；qr6=前 10%。
- 关系: qr6⊂qr5⊂qr4⊂qr3⊂qr2⊂qr1；按当日可得预测排序，不使用实现收益。
- 关联要素: F20-F21, R1-R2

## 四、回测设置（B 类）

### [B1] 美国与中国各取 500 只全样本平均市值最高股票
- 页码: p9
- 原文: > "We select 500 stocks with the highest average market capitalizations"
- 参数值: 美国 500 只；中国 500 只；平均市值区间 2014–2021。
- 局限: 研报明确承认该全样本选股引入机械前视。
- 关联要素: D1-D2, D6

### [B2] 训练样本逐股缩尾
- 页码: p9
- 原文: > "observations below the 0.5th percentile"
- 参数值: 下界=0.5th percentile；上界=99.5th percentile；对象=每只股票训练样本收益。
- 关联要素: F1-F3 / 关联歧义: A8

### [B3] 默认使用市场超额收益
- 页码: p9
- 原文: > "all returns mentioned in the following contents refer to market excess returns."
- 参数值: 除非另有说明，pvCLCL 与 OPCL 均指个股原始收益减对应 ETF 收益。
- 关联要素: F1-F3

### [B4] 两个预测方向的滞后参数
- 页码: p15
- 原文: > "We set l = 1 when predicting Chinese stocks"
- 参数值: US→CN 时 l=1；CN→US 时 l=0；预测目标均为 OPCL。
- 关联要素: D8, F4, F8-F9 / 关联歧义: A4

### [B5] 250 日滚动训练窗口
- 页码: p21
- 原文: > "We use a 250-day training window"
- 参数值: w=250 个交易日。
- 关联要素: F4-F17, F22-F23

### [B6] 图与预测模型每 10 日更新
- 页码: p21
- 原文: > "update both the graphs and the predictive models every 10 days."
- 参数值: 更新频率=每 10 个交易日。
- 关联要素: F4-F19, F22-F23 / 关联歧义: A9

### [B7] 样本外预测区间
- 页码: p21
- 原文: > "Prediction begins on the first trading day of 2016"
- 参数值: 起点=2016 年首个交易日；终点=2021 年最后一个交易日。
- 关联要素: F9-F24

### [B8] 滚动窗内筛选并严格样本外评价
- 页码: p15-p21
- 原文: > "All predictor selection is performed within the rolling training window"
- 参数值: 图筛边、预测变量选择及模型估计均只使用滚动训练窗；预测样本外评价。
- 关联要素: F4-F24

### [B9] 不计交易成本与交易摩擦
- 页码: p20-p21
- 原文: > "We abstract from liquidity-optimized portfolio construction"
- 参数值: 交易成本、市场冲击、卖空约束及其他交易摩擦均未建模；SR 为成本前预测强度。
- 关联要素: F20-F21

### [B10] 仓位金额上限
- 页码: p20
- 原文: > "L is set to 100,000 USD for the U.S. market prediction"
- 参数值: 预测美国市场 L=100,000 USD；预测中国市场 L=1,500,000 CNY。
- 关联要素: D7, F20

### [B11] 十种预测模型
- 页码: p17
- 原文: > "We applied a total of ten machine learning models to forecast returns."
- 参数值: OLS、LASSO、RIDGE、SVM、XGBoost、LGBM、RF、AdaBoost、ensemble-avg、ensemble-med。
- 关联要素: F10-F19 / 关联歧义: A6-A7

## 五、研报核心数值结果基准（R 类）

### [R1] Figure 8 的 US→CN Sharpe 量级
- 页码: p23
- 原文: > "its SRs are mostly lower than one."
- 数值表（正文叙述原样登记；图中未给精确标签的格子写 n/a）:

  | 对象 | 研报给出的数值表述 | 精确数值 |
  | --- | --- | --- |
  | SVM，多数量化组合 | lower than one | n/a |
  | 其他方法，多数分位组合 | exceed one | n/a |
  | 部分方法/分位组合 | approaching two | n/a |

- 其他结论: RIDGE、LGBM、ensemble-avg、ensemble-med 表现强；美国 pvCLCL 特征优于美国 OPCL 特征。
- 关联要素: F10-F24, B4-B11

### [R2] Table A.1 超参数设置下 SR 均值±标准差
- 页码: p36
- 原文: > "Values are reported as mean ± standard deviation."
- 数值表（逐格抄录）:

  | 方法 | Parameters | qr1 | qr2 | qr3 | qr4 | qr5 | qr6 |
  | --- | --- | --- | --- | --- | --- | --- | --- |
  | LASSO | λ={1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100, 1000} | 0.848 ± 0.222 | 0.969 ± 0.247 | 1.238 ± 0.31 | 1.65 ± 0.398 | 1.821 ± 0.433 | 1.777 ± 0.424 |
  | RIDGE | λ={1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100, 1000} | 1.238 ± 0.429 | 1.293 ± 0.43 | 1.437 ± 0.449 | 1.715 ± 0.51 | 1.668 ± 0.619 | 1.55 ± 0.461 |
  | SVM | C={0.1, 1, 10, 100, 1000} | 0.743 ± 0.194 | 0.751 ± 0.196 | 0.782 ± 0.204 | 0.719 ± 0.188 | 1.02 ± 0.267 | 0.836 ± 0.218 |
  | XGBoost | max depth={3,6,9}; learning rate={0.01, 0.1, 0.2}; n estimators={50, 100, 300} | 1.445 ± 0.224 | 1.48 ± 0.247 | 1.587 ± 0.214 | 1.539 ± 0.309 | 1.381 ± 0.401 | 0.964 ± 0.233 |
  | LGBM | num leaves={10, 31, 90}; learning rate={0.01, 0.1, 0.2}; n estimators={50, 100, 300} | 1.32 ± 0.348 | 1.457 ± 0.388 | 1.541 ± 0.422 | 1.44 ± 0.485 | 1.652 ± 0.466 | 1.424 ± 0.407 |
  | RF | n estimators={50, 100, 300}; max depth={5, 10, 50} | 1.481 ± 0.41 | 1.558 ± 0.422 | 1.639 ± 0.447 | 1.799 ± 0.486 | 1.747 ± 0.474 | 1.09 ± 0.351 |
  | AdaBoost | max depth={1, 5, 10}; n estimators={50, 100, 300}; learning rate={0.01, 0.1, 0.2} | 1.389 ± 0.358 | 1.405 ± 0.385 | 1.549 ± 0.436 | 1.548 ± 0.419 | 1.1 ± 0.305 | 0.667 ± 0.187 |

- 参数集合: 上表 Parameters 列按 PDF p36 逐行登记，未合并或推算。
- 关联要素: F11-F17, F21, F24, SA3 / 关联歧义: A10

### [R3] Figure 9 的 CN→US Sharpe 显著更弱
- 页码: p24
- 原文: > "SRs are substantially lower across methods and quantiles."
- 数值表（正文只给比较结论；图中未给精确标签的格子写 n/a）:

  | 对象 | 研报给出的比较结论 | 精确数值 |
  | --- | --- | --- |
  | 中国股票预测美国 OPCL | substantially lower across methods and quantiles | n/a |

- 其他结论: 中国市场在跨市场收益预测中的预测影响弱于美国市场。
- 关联要素: F10-F24, B4-B11 / 关联歧义: A11

### [R4] Figure 12/13 的图结构与跨市场信息增量
- 页码: p24
- 原文: > "yields the strongest overall performance"
- 补充原文: > "graph-based same-market approaches outperform non-graph-based same-market"
- 数值表（正文只给比较结论；图中未给精确标签的格子写 n/a）:

  | 比较 | 研报给出的结论 | 精确数值 |
  | --- | --- | --- |
  | 图同市场 vs 非图同市场 | 多数模型与多数分位更优，尤其 OLS、LGBM、qr5 | n/a |
  | 跨市场信息+图 vs 图同市场/非图同市场 | strongest overall performance | n/a |

- 关联要素: F22-F24, F21, B5-B9 / 关联歧义: A11

## 六、图表登记清单（FIG/TBL 全集）

> 登记规则说明：正文原生编号为 Figure 1–14；附录为 Figure B.1、B.2、C.1、D.1、E.1 与 Table A.1。因机器门禁首列只接受纯数字，附录图顺延登记为 FIG15–FIG19，附录表登记为 TBL1；原生标签完整保留在标题列。

| ID | 标题 | 页码 | 摘要 | 复现意图 | 理由/关联要素 |
| --- | --- | --- | --- | --- | --- |
| FIG1 | Figure 1: Schematic illustration of the directed bipartite graph | p11 | 源市场股票到目标市场股票的有向二部图示意 | reference_only | 示意图；关联 F4-F5 |
| FIG2 | Figure 2: Example time series of CDNS and 002410.XSHE | p12 | 三日移动平均后的示例收益序列，l=1、w=250 | reference_only | 示例图；关联 F4-F5, B4-B5 |
| FIG3 | Figure 3: Heatmap of the directed biadjacency matrix | p13 | 2021-10-21；每行业最多25只、不足全取；254美股/235 A股；行=中国、列=美国，颜色=t统计量 | reproduce | 关联 D9, F4-F5 |
| FIG4 | Figure 4: Sector-level heatmap of the absolute median t-statistic | p14 | 时间平均矩阵的行业块绝对 t 中位数 | reproduce | 关联 D9, F6 |
| FIG5 | Figure 5: In-degree distribution percentiles by day | p15 | US-CN 与 CN-US 入度25/50/75分位；两个方向均随时间上升，跨市场连接增强 | reproduce | 关联 F7 |
| FIG6 | Figure 6: Rolling training and prediction framework | p16 | 训练窗、滞后源市场与样本外预测示意 | reference_only | 示意图；关联 F4, F8-F9, B5-B8 |
| FIG7 | Figure 7: Timeline of U.S. and Chinese market hours | p16 | 非重叠交易时段与信息先后关系 | reference_only | 示意图；关联 D8, B4 |
| FIG8 | Figure 8: SRs for forecasting Chinese OPCL returns using U.S. returns | p23 | 美国 pvCLCL/OPCL 预测中国 OPCL 的 SR | reproduce | 关联 R1 |
| FIG9 | Figure 9: SRs for forecasting U.S. OPCL returns using Chinese returns | p24 | 中国 pvCLCL/OPCL 预测美国 OPCL 的 SR | reproduce | 关联 R3 |
| FIG10 | Figure 10: Cumulative daily PnL for US pvCLCL to Chinese OPCL | p25 | 十种模型、六个嵌套组合的累计 PnL | reproduce | 关联 F20, F24 |
| FIG11 | Figure 11: SRs for forecasting Chinese OPCL using Chinese returns | p26 | 图结构同市场预测的 SR | reproduce | 关联 F23 |
| FIG12 | Figure 12: SR comparison across three specifications | p26 | 跨市场图、同市场图、非图基线比较 | reproduce | 关联 R4, F22-F23 |
| FIG13 | Figure 13: SR deltas relative to non-graph baseline | p27 | US-CN/CN-CN 相对非图基线的 SR 差 | reproduce | 关联 R4, F22-F23 |
| FIG14 | Figure 14: Graph randomization and temporal lag sensitivity | p28 | 边替换比例与时间滞后敏感性 | reproduce | 关联 SA1-SA2 |
| FIG15 | Figure B.1: SR comparison using OPCL predictors | p37 | OPCL 特征下三种规格 SR 比较 | reproduce | 原生编号 B.1；关联 SA4 |
| FIG16 | Figure B.2: SR deltas using OPCL predictors | p37 | OPCL 特征下相对非图基线的 SR 差 | reproduce | 原生编号 B.2；关联 SA4 |
| FIG17 | Figure C.1: SRs conditional on SPY shock quantiles | p38 | 按 SPY 绝对 pvCLCL 分位条件化的 SR | reproduce | 原生编号 C.1；关联 SA5 |
| FIG18 | Figure D.1: Sector-level SRs | p39 | US pvCLCL 预测中国 OPCL 的行业 SR | reproduce | 原生编号 D.1；关联 SA6 |
| FIG19 | Figure E.1: SRs using both U.S. and Chinese predictors | p40 | 四种美中 pvCLCL/OPCL 特征组合 | reproduce | 原生编号 E.1；关联 SA7 |
| TBL1 | Table A.1: SR results across hyperparameter settings | p36 | 七种模型在 qr1–qr6 的均值±标准差 | reproduce | 原生编号 A.1；关联 R2, SA3 |

## 七、敏感性/稳健性分析（SA 类）

### [SA1] 图边随机替换
- 页码: p27-p28
- 原文: > "We randomly replace 20%, 40%, 60%, 80% and all of the edges."
- 测试设计: 保持每个目标节点入度不变，仅以此前未连接节点替换原边；各分位取十种模型结果的中位数。
- 结论: > "SRs generally decline as a larger fraction of edges is replaced"
- 次级结论: > "the highest quantile (qr6) exhibits comparatively greater resilience."
- 关联要素: F4-F5, F21, F24

### [SA2] 源市场信息时间滞后
- 页码: p28
- 原文: > "Here we set l = 2, 3, ... when predicting Chinese stocks."
- 测试设计: US pvCLCL 预测中国 OPCL，逐步增大 l；各分位取十种模型结果中位数。
- 结论: > "SRs generally decline as l increases"
- qr6 结论原文（1/3）: > "The decline is again less pronounced for qr6,"
- qr6 结论原文（2/3）: > "suggesting that large-magnitude signals may capture"
- qr6 结论原文（3/3）: > "more persistent cross-market effects."
- qr6 结论释义: qr6 的下降再次较不明显，表明大幅度信号可能捕捉到更持久的跨市场效应。
- 次级结论: > "A mild stabilization beyond Lag 4 likely reflects weekly trading-cycle effects."
- 关联要素: F8-F9, F21, F24, B4

### [SA3] 机器学习超参数敏感性
- 页码: p35-p36
- 原文: > "under alternative hyperparameter configurations."
- 参数网格: LASSO/RIDGE λ={1e-4,1e-3,1e-2,1e-1,1,10,100,1000}；SVM C={0.1,1,10,100,1000}。
- 参数网格: XGBoost max depth={3,6,9}，learning rate={0.01,0.1,0.2}，n estimators={50,100,300}。
- 参数网格: LGBM num leaves={10,31,90}，learning rate={0.01,0.1,0.2}，n estimators={50,100,300}。
- 参数网格: RF n estimators={50,100,300}，max depth={5,10,50}。
- 参数网格: AdaBoost max depth={1,5,10}，n estimators={50,100,300}，learning rate={0.01,0.1,0.2}。
- 结论: > "the cross-market forecasting framework delivers robust risk-adjusted performance"
- 关联要素: F11-F17, R2 / 关联歧义: A6, A10

### [SA4] OPCL 特征下的基线比较
- 页码: p35-p37
- 原文: > "the incremental contribution of cross-market information is substantially weaker"
- 测试设计: 以 OPCL 而非 pvCLCL 为预测变量，对比跨市场图、同市场图与非图同市场基线。
- 结论: 图结构通常提高多数分位与模型的表现，但跨市场信息增量更弱。
- 关联要素: F22-F24

### [SA5] 美国市场冲击条件分析
- 页码: p35, p38
- 原文: > "We divide the SPY absolute pvCLCL returns into nested quantiles (qr1–qr6)"
- 测试设计: 按 SPY 绝对 pvCLCL 将冲击日分为嵌套分位，对每个 ti 取中国市场下一交易日 ti+1 的 OPCL 预测并计算子样本 SR。
- 结论: 非线性集成模型在 qr4–qr6 的 SR 较高；OLS 在 qr6 最高；LASSO/SVM 部分分位为负。
- 次级结论: > "RIDGE shows comparatively unstable performance."
- 关联要素: D4, F21, F24

### [SA6] 行业层面 Sharpe Ratio
- 页码: p38-p39
- 原文: > "technology and consumer defensive sectors exhibit relatively higher SRs"
- 测试设计: US pvCLCL 预测中国 OPCL，按目标股票行业报告 SR。
- 结论: 科技与必需消费行业 SR 相对较高；研报提示行业股票数不同，应谨慎解释。
- 关联要素: D9, F21 / 关联歧义: A5

### [SA7] 同时使用美国与中国股票预测中国股票
- 页码: p39-p40
- 原文: > "the predictor set X to include all stocks from both the U.S. and Chinese markets"
- 测试设计: Y 仍为中国股票；X 同时含美国和中国股票；比较四种 pvCLCL/OPCL 特征组合。
- 结论: 部分规格的 SR 超过仅使用美国收益作为预测变量的 Figure 8 结果。
- 关联要素: F4-F24

## 八、提取自检声明

- [x] 逐页扫描确认：report_text.md 的 p1–p40 全部 `===== PAGE n =====` 已过目，无整页跳过。
- [x] 图表编号全登记：正文 Figure 1–14 已登记为 FIG1–FIG14；附录 Figure B.1/B.2/C.1/D.1/E.1 按机器格式顺延为 FIG15–FIG19；Table A.1 登记为 TBL1，原生标签均保留。
- [x] 摘要/结论提及的数值均可在正文定位到页码：摘要与结论未给出需逐格抄录的精确绩效数值；正文主结果量级与比较结论见 R1、R3、R4，附录唯一数值表见 R2。
- [x] 无法提取内容清单：p23–p28、p37–p40 的 Figure 8–14、B.1、B.2、C.1、D.1、E.1 未附底层数值表，无法从图形无损抄录精确柱高/曲线值；除正文明确量级与 Table A.1 外均未推算，见 A11。
