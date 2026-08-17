=== SPEC_CODEX_BEGIN ===
两阶段机器学习动态因子轮动 | F | p1,p4-p5 | 第一阶段识别/预测市场风险状态，第二阶段按状态预测因子相对表现
25项宏观驱动声明 | D | p5-p6 | 原文声称25项，Exhibit 3仅可识别10项，其余15项名称/数值/变换未披露
核心CPI十年年化变化 | D | p6 | FRED
核心CPI一年年化变化 | D | p6 | FRED
美国实际GDP增长 | D | p6 | FRED
Conference Board商业周期标签 | D | p5-p6,p12 | 领先周期数据、时点周期识别
金融状况风险/信用/杠杆 | D | p6 | National Financial Conditions Index三项
有效联邦基金利率 | D | p6 | FRED
货币政策预期 | D | p6 | 具体序列定义未披露
CAPE | D | p6 | Robert Shiller在线数据
S&P 500价格与三个月滚动回撤 | D | p4-p5,p8 | 第一阶段聚类输入
十个S&P 500行业月收益 | D | p7 | info tech、energy、financials、healthcare、staples、discretionary、utilities、industrials、telecoms、materials
12个月/2年/10年美国国债收益 | D | p7 | 与十行业共同构造金融湍流
六类美股因子收益 | D | p6,p9-p13 | value、growth、momentum、low volatility、quality、small size
股债收益数据来源陈述 | D | p5及各Exhibit来源行 | p5称Refinitiv Eikon Datastream；多张Exhibit称FRED/Factset
K-Means市场风险聚类 | F | p4,p7-p8,p14 | K由肘部法选取，附录给出簇内平方和目标函数
三类市场风险状态 | F | p8-p9 | cluster 0 normal、cluster 1 correction、cluster 2 bear
Stacking分类器 | F | p4,p9,p15 | RF/SVC/GNB为第一层，Logistic Regression为第二层
Stacking损失与输出 | F | p15 | 交叉熵损失；sigmoid加权输出
SMOTE类别平衡 | F | p4,p9,p16 | x_new=xi+α(xj-xi)，α在0与1之间
金融湍流 | F | p6-p7 | d_t=(y_t-μ)Σ^(-1)(y_t-μ)′
决策树/随机森林特征重要性 | F | p9,p14-p15 | Gini不纯度下降、树内归一化、跨树汇总
第二阶段按风险状态切分样本 | F | p5,p9,p11 | 每个状态分别训练模型
胜出因子标签 | F | p4-p5,p9-p10 | Exhibit 1写比较因子daily return；正文写monthly performance，最佳为1其余为0
第二阶段随机森林胜出概率 | F | p9-p11,p14 | 按状态预测各因子相对胜出概率
Value因子 | F | p6 | Russell 1000中P/B最低1/3
Growth因子 | F | p6 | Russell 1000中P/B最高1/3
Momentum因子 | F | p6 | Russell 1000中过去12个月收益最高1/3
Low Volatility因子 | F | p6 | Russell 1000中年化收益波动最低1/5
Quality因子 | F | p6 | Russell 1000中质量得分最高1/3，质量得分定义未披露
Small-Cap因子 | F | p6 | Russell 3000中市值最低2/3
商业周期因子择时基准 | F | p5,p11-p12 | 按各周期阶段全样本平均表现超配/低配
商业周期方向矩阵 | F | p12 | Expansion/Slowdown/Contraction/Recovery四阶段
1/N等权基准 | F | p11-p12 | 六因子等权
商业周期15%调权 | F | p12 | 以15% allocation修改1/N权重，映射公式未披露
机器学习概率权重 | F | p12 | 直接以winning probability作为各因子权重
全样本区间与频率 | B | p5 | 1987-03至2023-03，433个月度观测
三个月滚动回撤 | B | p5,p8 | S&P 500 Three Months’ Rolling Drawdown
滚动训练而非扩展训练 | B | p5 | rolling window，不使用extending windows
初始训练窗 | B | p10 | 84个月
胜出概率样本外预测 | B | p10-p11 | post-2000 prediction data set，Exhibit 13至2022-09
组合模拟训练区间 | B | p11 | 1987至2000
组合复合收益区间 | B | p12-p13 | since 2002，Exhibit 17至2022-09
五折时间序列交叉验证 | B | p9 | five folds、time series split
第二阶段状态合并 | B | p9 | bear的3.8%并入correction
六因子股票池 | B | p6 | 五因子Russell 1000，Small-Cap为Russell 3000
组合比较对象 | B | p11-p13 | Russell 1000、1/N、商业周期倾斜、ML
商业周期信息口径 | B | p12 | 全样本最终宏观数据计算阶段均值；OOS阶段识别只用当时信息
商业周期风险预算 | B | p12 | 15%
ML组合权重口径 | B | p12 | 胜出概率直接作为权重，归一化和风险预算未披露
交易执行与成本 | B | p12-p13 | 信号执行时点、调仓细节、交易成本和换手未披露
风险状态数量与占比 | R | p8-p9 | K=3；Normal 77.5%、Correction 18.7%、Bear 3.8%
Stacking分类指标 | R | p9 | Accuracy 71%、Precision 0.753、Recall 0.721
第一阶段特征重要性 | R | p9 | Equity Valuation 19.7%、Financial Turbulence 26.9%、Financial Conditions 34.1%、Monetary Policy Expectation 19.3%
六因子全样本相关矩阵 | R | p10 | 下三角：0.66/0.68/0.93/0.76/0.70/0.71/0.85/0.86/0.83/0.87/0.86/0.76/0.77/0.64/0.80
Normal状态相关矩阵 | R | p10 | 下三角：0.46/0.46/0.89/0.63/0.56/0.55/0.73/0.79/0.75/0.80/0.77/0.63/0.64/0.43/0.66
Correction状态相关矩阵 | R | p10 | 下三角：0.54/0.61/0.86/0.76/0.57/0.60/0.86/0.70/0.68/0.88/0.88/0.64/0.69/0.67/0.81
六因子历史胜出频率 | R | p10 | Value 19.9%、Growth 15.9%、Momentum 14.4%、Low Volatility 21.3%、Quality 4.0%、Small Size 24.5%
分状态第二阶段特征重要性 | R | p11 | Normal/Correction：估值36.4/42.5、湍流12.4/13.1、通胀16.3/17.9、金融条件22.4/15.3、政策预期9.3/9.9、GDP 3.2/1.3，单位均为%
商业周期方向矩阵 | R | p12 | Value n/a,-,n/a,+；Growth n/a,-,+,-；Momentum +,+,n/a,n/a；LowVol n/a,+,-,-；Quality n/a,+,-,n/a；Small-Cap -,-,+,+
四方法组合表现 | R | p13 | Russell 1000：8.40%/15.49%/0.52，其余n/a
Equal Weighted组合表现 | R | p13 | 8.63%/15.19%/0.54/0.18%/2.40%/0.07
Business Cycle Tilt组合表现 | R | p13 | 9.84%/16.06%/0.59/1.50%/3.95%/0.36
ML Approach组合表现 | R | p13 | 11.47%/16.81%/0.66/2.89%/6.68%/0.45
五折时序交叉验证 | SA | p9 | 防时间序列数据泄漏；报告71%准确率
分风险状态相关性分析 | SA | p9-p10 | 全样本、Normal、Correction三组矩阵
滚动样本外预测与组合模拟 | SA | p5,p10-p13 | 初始训练后滚动预测风险状态和因子概率
等权与商业周期双基准 | SA | p4,p11-p13 | 与Russell 1000、1/N、商业周期方法比较
Exhibit 1 | EX | p4 | The Two-Stage Machine Learning Framework
Exhibit 2 | EX | p5 | S&P 500 Three Months’ Rolling Drawdown
Exhibit 3 | EX | p6 | Macroeconomic and Financial Market Factors Considered for Machine Learning Testing
Exhibit 4 | EX | p6 | Selected Equity Factors’ Succinct Definition
Exhibit 5 | EX | p7 | Financial Turbulence from Ten S&P 500 Sectors and Various Maturity Treasuries
Exhibit 6 | EX | p8 | The Elbow Method of K-Means Clustering
Exhibit 7 | EX | p8 | The S&P 500 Three Months’ Rolling Drawdown and Clustering
Exhibit 8 | EX | p9 | Accuracy Rate of Stacking Classification Mode
Exhibit 9 | EX | p9 | Feature Importance of Selected Variables
Exhibit 10 | EX | p10 | Cross Correlation throughout the Entire Sample Period
Exhibit 11 | EX | p10 | Cross Correlation throughout Each Market Risk Regime
Exhibit 12 | EX | p10 | Historical Frequency Counting on Outperforming
Exhibit 13 | EX | p11 | Outperforming Probabilities of Each Factor from Out-of-Sample Prediction
Exhibit 14 | EX | p11 | Feature Importance within Each Market Risk Regime
Exhibit 15 | EX | p12 | Business Cycle Strategy
Exhibit 16 | EX | p12 | Business Cycle Labels，横轴可见May-23
Exhibit 17 | EX | p13 | Compound Return with Different Approaches
=== SPEC_CODEX_END ===
{
  "checkpoint": "spec",
  "verdict": "pass_with_issues",
  "dimensions_checked": [
    {"dimension":"盲提取diff","result":"CDX-S-01,CDX-S-02,CDX-S-03,CDX-S-04"},
    {"dimension":"遗漏检查","result":"CDX-S-01,CDX-S-02,CDX-S-03,CDX-S-04"},
    {"dimension":"R表逐格核对","result":"no_findings"},
    {"dimension":"编号完整性独立重算","result":"no_findings"},
    {"dimension":"页码真实性抽查","result":"no_findings"}
  ],
  "findings": [
    {
      "id": "CDX-S-01",
      "severity": "major",
      "category": "遗漏",
      "location": "report_text.md:p9,p15；spec.md:F4,F7,R2",
      "description": "原文方法主线和Exhibit 8指向市场风险状态分类，但p9写预测significant shadow rate changes，p15又写predicting shadow rates；spec仅挂接歧义编号，未在正文显式抄录这两处核心目标冲突。",
      "suggestion": "在F4或R2中并列抄录市场风险状态目标与两处shadow rate原文，明确标为原文内部冲突，不替原文裁决。",
      "confidence": "high"
    },
    {
      "id": "CDX-S-02",
      "severity": "major",
      "category": "遗漏",
      "location": "report_text.md:p5及Exhibit 2,5-17来源行；spec.md:D11-D14",
      "description": "p5称equity and Treasury return related variables来自Refinitiv Eikon Datastream，多张Exhibit来源行却写FRED/Factset；spec未并列登记这一底层来源口径冲突，D14还只写Factset。",
      "suggestion": "在D11-D14的数据来源说明中同时保留p5与Exhibit来源陈述，并标记为来源口径不一致；不得自行选择其一覆盖另一项。",
      "confidence": "high"
    },
    {
      "id": "CDX-S-03",
      "severity": "major",
      "category": "遗漏",
      "location": "report_text.md:p4 Exhibit 1,p5；spec.md:F9",
      "description": "Exhibit 1写Label by comparing factors daily return，p5正文却以monthly performance定义最佳因子；spec只登记月度标签，未显式保留日频与月频冲突。",
      "suggestion": "在F9中并列抄录Exhibit 1的daily return和p5的monthly performance，登记为标签频率未决歧义。",
      "confidence": "high"
    },
    {
      "id": "CDX-S-04",
      "severity": "major",
      "category": "遗漏",
      "location": "report_text.md:p5,p12 Exhibit 16；spec.md:B1,EX16",
      "description": "p5明确样本结束于March 2023，但Exhibit 16横轴可见May-23；spec登记了B1的March 2023和EX16标题，却未显式记录该终点不一致。",
      "suggestion": "在B1或EX16说明中保留March 2023与May-23两项原文证据并登记终点歧义，不从图轴自行推断新增观测。",
      "confidence": "high"
    }
  ]
}
