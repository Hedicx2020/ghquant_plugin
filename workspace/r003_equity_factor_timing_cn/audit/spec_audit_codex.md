=== SPEC_CODEX_BEGIN ===
BL-D01 | D | p5 | 样本为1987年3月至2023年3月，共433个月度观测；股票及国债收益变量来自Refinitiv Eikon Datastream，宏观变量来自FRED。
BL-D02 | D | p5,p8 | 第一阶段市场状态输入为S&P 500价格计算的三个月滚动回撤；价格来源注明Factset（p8脚注另并列FRED与Factset）。
BL-D03 | D | p6 | 通胀输入为核心CPI过去十年年化变化、过去一年年化变化。
BL-D04 | D | p6 | 增长/周期输入为美国实际GDP增长、Conference Board商业周期标签。
BL-D05 | D | p6 | 金融状况输入为National Financial Conditions Index的Risk、Credit、Leverage三个分项。
BL-D06 | D | p6 | 货币政策输入为有效联邦基金利率、货币政策预期。
BL-D07 | D | p6 | 股票估值输入为CAPE（周期调整市盈率），来源Robert Shiller在线数据。
BL-D08 | D | p5-p6 | 正文称初选考虑25个宏观驱动；Exhibit 3可见列名仅明确列出上述10个变量，其余变量/变换未逐项披露。
BL-D09 | D | p7 | 金融湍流使用十个S&P 500行业月收益：信息技术、能源、金融、医疗、必需消费、可选消费、公用事业、工业、电信、材料。
BL-D10 | D | p7 | 金融湍流同时使用12个月、2年、10年期限美国国债工具月收益。
BL-D11 | D | p6,p9 | 六类股票因子月收益为Value、Growth、Momentum、Low Volatility、Quality、Small Size，因子数据来源Factset。
BL-F01 | F | p1,p4-p5 | 两阶段框架：第一阶段识别并预测市场风险状态，第二阶段在各风险状态子样本内预测各因子相对胜出概率。
BL-F02 | F | p4,p7-p8,p14 | 对S&P 500回撤做K-Means；肘部法选K；目标为最小化簇内平方和 min ΣiΣj||xi-μj||²。
BL-F03 | F | p8 | 三个聚类标签：0=normal market risk、1=market correction、2=bear market。
BL-F04 | F | p4,p15 | 第一阶段Stacking：第一层RF、SVC、GNB，第二层Logistic Regression；LR以交叉熵 L(w)=-Σ[y_i log(y_pred_i)+(1-y_i)log(1-y_pred_i)] 学习w1,w2,w3；y_pred=σ(w1RF(x)+w2SVC(x)+w3GNB(x))。
BL-F05 | F | p4,p9,p16 | SMOTE处理三类状态不平衡；x_new=xi+α(xj-xi)，α∈[0,1]。
BL-F06 | F | p6-p7 | 金融湍流 d_t=(y_t-μ)Σ^-1(y_t-μ)'；y_t为当期资产收益向量，μ为历史均值向量，Σ为历史协方差矩阵。
BL-F07 | F | p9,p14-p15 | 随机森林由N棵树Tn(X)产生Yn并投票/平均；报告用于第一阶段状态预测及第二阶段胜出概率预测。
BL-F08 | F | p9,p14-p15 | 决策树特征重要性以Gini不纯度下降计节点贡献：单树特征重要性为该特征分裂节点贡献占全部节点贡献之比；再树内归一化并跨森林汇总得到RF特征重要性。
BL-F09 | F | p5,p9,p11 | 第二阶段按第一阶段风险状态切成子数据框，并在各状态内分别训练模型。
BL-F10 | F | p5,p9 | 每月表现最好的因子标1，其余五个标0；在各状态内训练随机森林，输出每个因子相对胜出的概率。
BL-F11 | F | p6 | Value：Russell 1000中市净率最低1/3。
BL-F12 | F | p6 | Growth：Russell 1000中市净率最高1/3。
BL-F13 | F | p6 | Momentum：Russell 1000中过去12个月收益最高1/3。
BL-F14 | F | p6 | Low Volatility：Russell 1000中年化收益波动率最低1/5。
BL-F15 | F | p6 | Quality：Russell 1000中质量得分最高1/3，质量分具体构造未披露。
BL-F16 | F | p6 | Small-Cap：Russell 3000中市值最低2/3。
BL-F17 | F | p5,p11-p12 | 1/N基准为六因子等权；商业周期基准按各周期阶段的全样本平均表现相对1/N超配/低配。
BL-F18 | F | p12 | 商业周期阶段均值使用全样本最终宏观数据（perfect hindsight），但样本外期的周期阶段识别仅用当时可得信息。
BL-F19 | F | p12 | 商业周期组合以15% allocation/risk budget修改1/N权重；具体换算公式未披露。
BL-F20 | F | p12 | ML组合直接以每个因子的预测胜出概率作为权重，不另加实务风险预算；概率是否归一化未披露。
BL-B01 | B | p5 | 频率为月度；全样本1987-03至2023-03。
BL-B02 | B | p5,p8 | 第一阶段回撤特征为S&P 500三个月滚动回撤，K-Means选择三簇。
BL-B03 | B | p5 | 样本外采用固定长度rolling window，不采用extending window。
BL-B04 | B | p9 | 第一阶段分类五折交叉验证，并采用time-series split避免时间泄漏；SMOTE用于类不平衡。
BL-B05 | B | p9 | 三类状态样本占比失衡，第二阶段将仅占3.8%的bear合并进correction，最终按normal/correction两状态建模。
BL-B06 | B | p10 | 第二阶段初始训练窗84个月，此后滚动；胜出概率预测数据集为2000年以后。
BL-B07 | B | p11 | 组合模拟另述训练数据为1987年至2000年；每个样本外时点先预测状态，再用该状态模型预测因子胜出概率。
BL-B08 | B | p12-p13 | 组合复合收益比较自2002年开始，图示至2022年9月附近；全样本数据截至2023年3月。
BL-B09 | B | p11-p13 | 比较对象为Russell 1000、六因子等权、商业周期倾斜、ML方法。
BL-R01 | R | p8-p9 | K=3；normal 77.5%，correction 18.7%，bear 3.8%。
BL-R02 | R | p9 | Exhibit 8：五折交叉验证Accuracy 71%，Precision 0.753，Recall 0.721；相邻正文逐字称其为“predicting significant shadow rate changes”，与全文状态预测语境存在目标表述冲突。
BL-R03 | R | p9 | Exhibit 9第一阶段特征重要性：Equity Valuation 19.7%，Financial Turbulence 26.9%，Financial Conditions 34.1%，Monetary Policy Expectation 19.3%。
BL-R04 | R | p10 | Exhibit 10全样本相关矩阵下三角：Growth[0.66]；Momentum[0.68,0.93]；Low Vol[0.76,0.70,0.71]；Quality[0.85,0.86,0.83,0.87]；Small[0.86,0.76,0.77,0.64,0.80]；对角均为1，上三角空白。
BL-R05 | R | p10 | Exhibit 11 Normal下三角：Growth[0.46]；Momentum[0.46,0.89]；Low Vol[0.63,0.56,0.55]；Quality[0.73,0.79,0.75,0.80]；Small[0.77,0.63,0.64,0.43,0.66]；对角均为1，上三角空白。
BL-R06 | R | p10 | Exhibit 11 Correction下三角：Growth[0.54]；Momentum[0.61,0.86]；Low Vol[0.76,0.57,0.60]；Quality[0.86,0.70,0.68,0.88]；Small[0.88,0.64,0.69,0.67,0.81]；对角均为1，上三角空白。
BL-R07 | R | p10 | Exhibit 12胜出频率：Value 19.9%，Growth 15.9%，Momentum 14.4%，Low Volatility 21.3%，Quality 4.0%，Small Size 24.5%。
BL-R08 | R | p11 | Exhibit 14 Normal/Correction特征重要性：Equity Valuation 36.4%/42.5%；Financial Turbulence 12.4%/13.1%；Inflation 16.3%/17.9%；Financial Conditions 22.4%/15.3%；Monetary Policy Expectations 9.3%/9.9%；GDP Growth 3.2%/1.3%。
BL-R09 | R | p12 | Exhibit 15 Expansion/Slowdown/Contraction/Recovery方向：Value[空,−,空,+]；Growth[空,−,+,−]；Momentum[+,+,空,空]；Low Volatility[空,+,−,−]；Quality[空,+,−,空]；Small-Cap[−,−,+,+]。
BL-R10 | R | p13 | Exhibit 17 Russell 1000：8.40%收益、15.49%波动、0.52 Sharpe，其余三格空白；Equal Weighted：8.63%、15.19%、0.54、0.18%、2.40%、0.07；Business Cycle Tilt：9.84%、16.06%、0.59、1.50%、3.95%、0.36；ML：11.47%、16.81%、0.66、2.89%、6.68%、0.45。
BL-SA01 | SA | p9 | 五折time-series-split交叉验证及SMOTE不平衡处理；报告值为71% accuracy。
BL-SA02 | SA | p9-p10 | 全样本与normal/correction分状态相关矩阵对比，用于论证分状态后部分因子相关性降低。
BL-SA03 | SA | p5,p10-p13 | 84个月起始窗的滚动样本外胜出概率预测；组合模拟先预测状态、再预测因子概率，复合收益自2002年比较。
BL-SA04 | SA | p11-p13 | 与Russell 1000、1/N、使用全样本阶段均值的商业周期倾斜策略做样本外比较。
BL-EX01 | F | p4 | Exhibit 1 The Two-Stage Machine Learning Framework。
BL-EX02 | D | p5 | Exhibit 2 S&P 500 Three Months’ Rolling Drawdown。
BL-EX03 | D | p6 | Exhibit 3 Macroeconomic and Financial Market Factors Considered for Machine Learning Testing。
BL-EX04 | F | p6 | Exhibit 4 Selected Equity Factors’ Succinct Definition。
BL-EX05 | D | p7 | Exhibit 5 Financial Turbulence from Ten S&P 500 Sectors and Various Maturity Treasuries。
BL-EX06 | F | p8 | Exhibit 6 The Elbow Method of K-Means Clustering。
BL-EX07 | R | p8 | Exhibit 7 The S&P 500 Three Months’ Rolling Drawdown and Clustering。
BL-EX08 | R | p9 | Exhibit 8 Accuracy Rate of Stacking Classification Mode。
BL-EX09 | R | p9 | Exhibit 9 Feature Importance of Selected Variables。
BL-EX10 | R | p10 | Exhibit 10 Cross Correlation throughout the Entire Sample Period。
BL-EX11 | R | p10 | Exhibit 11 Cross Correlation throughout Each Market Risk Regime。
BL-EX12 | R | p10 | Exhibit 12 Historical Frequency Counting on Outperforming。
BL-EX13 | SA | p11 | Exhibit 13 Outperforming Probabilities of Each Factor from Out-of-Sample Prediction。
BL-EX14 | R | p11 | Exhibit 14 Feature Importance within Each Market Risk Regime。
BL-EX15 | R | p12 | Exhibit 15 Business Cycle Strategy。
BL-EX16 | SA | p12 | Exhibit 16 Business Cycle Labels。
BL-EX17 | R | p13 | Exhibit 17 Compound Return with Different Approaches。
=== SPEC_CODEX_END ===
{
  "checkpoint": "spec",
  "verdict": "pass_with_issues",
  "dimensions_checked": [
    {
      "dimension": "盲提取diff",
      "result": "CDX-S-01,CDX-S-02,CDX-S-03"
    },
    {
      "dimension": "遗漏检查",
      "result": "CDX-S-01,CDX-S-02,CDX-S-03"
    },
    {
      "dimension": "R表逐格核对",
      "result": "no_findings"
    },
    {
      "dimension": "编号完整性独立重算",
      "result": "no_findings"
    },
    {
      "dimension": "页码真实性抽查",
      "result": "no_findings"
    }
  ],
  "findings": [
    {
      "id": "CDX-S-01",
      "severity": "major",
      "category": "公式抄录不完整",
      "location": "p15；spec.md 第三节F4",
      "description": "F4抄录了Stacking的最终sigmoid组合式，但漏掉Logistic Regression用于学习w1、w2、w3的交叉熵损失 L(w)=-Σ[y_i log(y_pred_i)+(1-y_i)log(1-y_pred_i)]。hard难度要求公式全量盲提取，该目标函数是Stacking第二层的训练定义，不属于纯呈现细节。",
      "suggestion": "在F4补录交叉熵损失公式，并注明其用于训练第二层Logistic Regression的组合权重。"
    },
    {
      "id": "CDX-S-02",
      "severity": "major",
      "category": "公式抄录不完整",
      "location": "p14-p15；spec.md 第三节F7",
      "description": "F7仅用文字概述Gini不纯度下降、树内归一化和随机森林汇总，漏录附录给出的单树特征重要性、归一化特征重要性及随机森林层级汇总三组公式。研报明确用这些公式定义Exhibit 9和Exhibit 14的特征重要性口径。",
      "suggestion": "在F7逐式补录f_i、normf_i和RFf_i三层公式，保留报告中的节点贡献、特征索引与树索引定义；若OCR公式不清，应明确登记为待人工核图歧义，不能只保留定性描述。"
    },
    {
      "id": "CDX-S-03",
      "severity": "major",
      "category": "原文目标变量歧义遗漏",
      "location": "p9；spec.md 第三节F4与第五节R2",
      "description": "Exhibit 8相邻正文逐字写模型以71%交叉验证准确率预测“significant shadow rate changes”，而F4/R2直接把该组指标归入市场风险状态预测，未记录这一与全文语境冲突的原文表述。无论这是作者笔误还是复用残留，它都会影响复现时对第一阶段标签的判定，不能静默改写。",
      "suggestion": "在F4或R2增加显式歧义登记：表题与全文流程指向市场风险状态分类，但p9正文写shadow rate changes；规划阶段须裁决并保留原文证据。"
    }
  ]
}
