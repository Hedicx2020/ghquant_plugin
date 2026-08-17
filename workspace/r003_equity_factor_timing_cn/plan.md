---
report_name: r003_equity_factor_timing_cn
title: "Equity Factor Timing: A Two-Stage Machine Learning Approach"
institution: "The Vanguard Group, Inc."
date: 2024-01-25
type: ml
tags: [timing, factor, market_transplant, china_market, out_of_sample]
difficulty: hard
feasibility: feasible
template: templates/ml.md
spec_ref: workspace/r003_equity_factor_timing_cn/spec/spec.md
data_requirements:
  - name: "D1 核心CPI十年年化变化 -> 中国CPI十年年化变化"
    source: "macro_cpi.parquet / macro_cache.parquet；按已知发布日期滞后后滚动衍生"
    status: substitute
  - name: "D2 核心CPI一年年化变化 -> 中国CPI一年同比/年化变化"
    source: "macro_cpi.parquet / macro_cache.parquet；按已知发布日期滞后后衍生"
    status: substitute
  - name: "D3 美国实际GDP增长 -> 中国实际GDP同比增长"
    source: "macro_gdp.parquet / macro_cache.parquet；季频发布后映射至月频"
    status: substitute
  - name: "D4 Conference Board商业周期标签 -> 中国增长周期四阶段标签"
    source: "macro_pmi.parquet + macro_gdp.parquet + macro_industrial_production.parquet；按增长水平与方向衍生"
    status: substitute
  - name: "D5 美国金融状况风险指标 -> 中国市场风险代理"
    source: "macro_cache.parquet 的 credit_spread、term_spread、bond_yield_10y 与中证800波动率衍生"
    status: substitute
  - name: "D6 美国金融状况信用指标 -> 中国信用条件代理"
    source: "macro_social_financing.parquet + macro_money_supply.parquet / macro_cache.parquet 衍生"
    status: substitute
  - name: "D7 美国金融状况杠杆指标 -> 中国杠杆条件代理"
    source: "macro_money_supply.parquet + macro_social_financing.parquet，相对GDP增速衍生"
    status: substitute
  - name: "D8 有效联邦基金利率 -> 中国LPR与短端利率"
    source: "macro_lpr.parquet + bond_shibor.parquet"
    status: substitute
  - name: "D9 美国货币政策预期 -> 中国货币政策预期代理"
    source: "macro_lpr.parquet + bond_yield_curve.parquet + macro_money_supply.parquet；利率与货币增速变化衍生"
    status: substitute
  - name: "D10 美国CAPE -> 中证800估值代理"
    source: "ashare_index_value.parquet / ashare_csiindex_trade.parquet 的 000906 PE/PB、EP=1/PE及历史分位"
    status: substitute
  - name: "D11 S&P 500价格与三个月滚动回撤 -> 中证800价格与三个月滚动回撤"
    source: "ashare_csiindex_trade.parquet，index_code=000906，2004-12至2026-07"
    status: substitute
  - name: "D12 十个S&P 500行业月收益 -> 中信一级行业月收益"
    source: "ashare_stock_industry.parquet（standard_code=37）+ ashare_stock_price_forward.parquet + ashare_stock_trade.parquet"
    status: substitute
  - name: "D13 多期限美国国债月收益 -> 中国1Y/2Y/10Y国债月收益代理"
    source: "bond_yield_curve.parquet，curve_code=10，1Y/2Y/10Y，2015-01至2025-12；由收益率变化和久期近似衍生月收益"
    status: substitute
  - name: "D14 六类美股因子月收益 -> 六类A股因子月收益"
    source: "中证800历史成分 + A股前复权行情/交易/估值/财务；Small-Cap改用全A小市值股票池"
    status: substitute
milestones:
  - id: m1
    name: "中国市场时点数据、宏观特征与六因子收益底座"
    desc: "完成2015-01至2025-12联合月频数据集、发布时间对齐、金融湍流、中证800及全A六因子收益，并输出数据质量和相关性证据；所有替代均明确标为市场迁移。"
    deps: []
    elements: [D1, D2, D3, D4, D5, D6, D7, D8, D9, D10, D11, D12, D13, D14, F6, F11, F12, F13, F14, F15, F16, B1, B2, B10]
  - id: m2
    name: "第一阶段市场风险状态识别与预测"
    desc: "以固定84个月滚动窗重估三状态K-Means和Stacking分类器，采用五折时间序列验证、仅训练窗内SMOTE，并输出状态占比、分类指标和四类特征重要性。"
    deps: [m1]
    elements: [F2, F3, F4, F5, F7, B8, R1, R2, R3, SA1]
  - id: m3
    name: "第二阶段分状态因子胜出概率模型"
    desc: "将Bear并入Correction，按预测状态训练六个一对其余的随机森林；以t时点可得特征预测t+1唯一胜出因子，输出概率、相关矩阵、胜出频率与分状态特征重要性。"
    deps: [m1, m2]
    elements: [F1, F8, F9, F10, B3, B4, B9, R4, R5, R6, R7, R8, SA2]
  - id: m4
    name: "四类组合权重与中国商业周期基准"
    desc: "构造中证800、六因子1/N、中国商业周期15%倾斜和ML概率归一化四类组合；权重统一于信号后下一可交易期执行，产出可复核的权重和收益明细。"
    deps: [m1, m3]
    elements: [F17, F18, F19, F20, F21, B11, B12, B13, B14, R9, SA4]
  - id: m5
    name: "2023-04至2025-12严格样本外延伸与结果包"
    desc: "冻结m1-m4口径，以2023-03为切点，用每月向前滚动84个月训练且不调参，生成约33个月OOS预测、毛收益主结果、成本补充情景、Excel/PNG/metrics/comparison及证据链。"
    deps: [m1, m2, m3, m4]
    elements: [B5, B6, B7, R10, SA3]
---

# Equity Factor Timing: A Two-Stage Machine Learning Approach 复现开发计划

## 研报信息

- 标题：Equity Factor Timing: A Two-Stage Machine Learning Approach
- 来源机构：The Vanguard Group, Inc.
- 发布日期：2024-01-25（采用PDF元数据日期，见A14/AS28）
- 作者：Kevin J. DiCiurcio、Boyu Wu、Fei Xu、Scott Rodemer、Qian Wang
- 原研究市场：美股
- 本计划适用市场：中国A股；`reproduction_mode=experimental`，属于方法迁移，不得称为严格美股复现。
- 主类型：`ml`；最终应用为因子择时与动态因子配置。

## 一、核心策略与创新点

### 1.1 研究背景与核心思想

本计划把两阶段机器学习框架迁移到中国市场。第一阶段用宏观、估值、金融条件和金融湍流特征预测下一月市场风险状态；第二阶段在风险状态条件下预测下一月六类A股因子中唯一的胜出因子，并将六个胜出概率归一化为组合权重。主结果与中证800、六因子等权和中国商业周期倾斜组合比较。

A1已由用户作出人工裁决：本案例不补齐原文未披露的15个美国宏观变量，固定使用可追溯的中国代理特征集合。该集合覆盖权益估值（EP/PB）、金融湍流（中信一级行业与1Y/2Y/10Y国债）、金融条件（credit_spread、term_spread）、货币政策/流动性（M1/M2、社融、LPR）、通胀（CPI YoY）和增长（GDP real YoY、工业增加值）；所有原料在data_catalog中可得或可衍生，因此实验性中国市场迁移的可行性为 `feasible`。

### 1.2 特征工程、标签与策略构造

1. 时点对齐：月频宏观值先映射到保守可得日，再允许进入特征集。月频宏观至少滞后一个月，季度GDP至少滞后两个月；市场价格、估值和收益率仅使用月末当时已观测值。只允许在“已发布后”向前填充，禁止 `bfill`，禁止用最终修订值倒填历史。
2. 中国市场三个月回撤：对月末 (t)，使用过去三个月窗口内中证800收盘价峰值 (P^{max}_{t,3m})，计算 (DD_t=P_t/P^{max}_{t,3m}-1)。
3. 金融湍流：使用中信一级行业等权月收益与中国1Y/2Y/10Y国债久期近似月收益组成向量 (y_t)，以此前84个月估计均值和协方差，计算 (d_t=(y_t-\mu_t)'(\Sigma_t+\lambda I)^{-1}(y_t-\mu_t))。当协方差病态时只使用训练窗内确定的微小岭项。
4. 六因子：Value、Growth、Momentum、Low Volatility、Quality在月末时点的中证800历史成分内选股；Small-Cap在可交易全A中按总市值选择最低2/3。Value为PB最低1/3，Growth为PB最高1/3，Momentum为过去12个月（跳过最近1个月）收益最高1/3，Low Volatility为过去12个月日收益年化波动率最低1/5，Quality为点时财务质量综合分最高1/3。入选股票等权，月频调仓，财务数据必须按 `info_publ_date` 对齐。
5. 第一阶段：每个预测月仅使用此前固定84个月样本重估K-Means（(K=3)，seed=42），按聚类中心从高到低对齐Normal、Correction、Bear；训练RF、SVC、GNB并由Logistic Regression做Stacking。所有标准化、缺失值处理和SMOTE只在相应训练折内拟合。训练样本使用 (X_t\rightarrow regime_{t+1})。
6. 第二阶段：Bear合并到Correction。每个月 (t+1) 的六因子实现收益中，只允许一个最大值对应因子记为1；若并列，按固定顺序 Value、Growth、Momentum、Low Volatility、Quality、Small-Cap 决胜。对每个状态和每个因子分别训练一个一对其余随机森林，输入为 (t) 时点可得特征，标签为 (t+1) 是否唯一胜出。
7. ML权重：六个预测概率 (p_{i,t}) 归一化为 (w_{i,t}=p_{i,t}/\sum_j p_{j,t})。若概率和异常为0，则回退至1/N，并记录异常。权重从下一可交易期开始生效。
8. 商业周期基准：用按发布日期可得的中国PMI、实际GDP与工业增加值构造增长水平和方向，划分Expansion、Slowdown、Contraction、Recovery；按R9方向矩阵生成 (s_i\in\{-1,0,1\})，并用 (w_i=1/6+0.15(s_i-\bar{s})/\sum_j|s_j-\bar{s}|) 分配总主动倾斜预算，最后非负裁剪并归一化。

### 1.3 创新点

- 把市场风险状态预测与条件因子胜出预测分开，允许相同宏观信号在不同风险状态下产生不同的因子配置。
- 用滚动84个月而非扩展窗口，明确保持训练样本长度固定，使模型随中国市场结构变化更新而不让远古样本权重持续累积。
- 以2023-03为冻结切点，将2023-04至2025-12作为完全不调参的核心样本外区间；这部分是本次交付的主结论来源。

## 二、回测参数

| 参数 | 中国市场实验口径 |
| --- | --- |
| 联合样本 | 2015-01至2025-12（中证800、宏观、1Y/2Y/10Y国债数据交集） |
| 样本外切点 | 2023-03；OOS为2023-04至2025-12，约33个月 |
| 数据频率 | 日频原料，月末取样，月度调仓 |
| 股票池 | 五个风格因子用中证800当时历史成分；Small-Cap用当时可交易全A |
| 市场基准 | 中证800（000906） |
| 训练窗口 | 固定84个月滚动窗，不使用扩展窗 |
| 第一阶段状态 | 3类：Normal、Correction、Bear；第二阶段Bear并入Correction |
| 交叉验证 | 五折 `TimeSeriesSplit`；预处理及SMOTE只在训练折内拟合 |
| 第二阶段模型 | 每状态×每因子一个RF二分类器；500棵树、max_depth=4、min_samples_leaf=3、max_features=sqrt、class_weight=balanced、seed=42 |
| 标签 | (t) 特征预测 (t+1) 六因子中唯一胜出者 |
| 调仓执行 | 月末信号后下一可交易期执行；停牌、涨跌停股票延迟至可交易日，未执行部分维持原持仓/现金并留痕 |
| 主收益口径 | 毛收益，不扣交易成本 |
| 成本补充 | 仅作敏感性场景：股票双边各10bp，并在卖出端另加5bp印花税；不改变主结论口径 |
| 随机性 | K-Means、SMOTE、RF及Stacking统一seed=42；记录软件版本和参数哈希 |

## 三、研报核心结果（验证基准）

原研报数值仅用于结构与方向参照。由于本计划是中国市场迁移，不能把中国结果与美股数值偏差解释为“严格复现误差”。具体原值、页码和原文以 `spec.md` 为唯一真相源。

| R 要素ID | 一句话摘要 | 关联 milestone |
| --- | --- | --- |
| R1 | 三风险状态数量与样本占比 | m2 |
| R2 | Stacking五折分类指标 | m2 |
| R3 | 第一阶段四类特征重要性 | m2 |
| R4 | 六因子全样本相关矩阵 | m3 |
| R5 | Normal状态相关矩阵 | m3 |
| R6 | Correction状态相关矩阵 | m3 |
| R7 | 六因子历史胜出频率 | m3 |
| R8 | 分状态第二阶段特征重要性 | m3 |
| R9 | 六因子四商业周期方向矩阵 | m4 |
| R10 | 四种方法组合表现 | m5 |

## 四、复现计划

### m1：中国市场时点数据、宏观特征与六因子收益底座

- 实现内容：统一交易日/月末日历；构造全部中国宏观代理、估值、回撤、中信行业与国债收益代理；按历史成分和时点财务数据生成六因子月收益。
- 数据纪律：每个字段保留 `source_date`、`release_date`、`available_date`；季度/月度数据未到保守发布日期前必须为空，之后才可前向持有，禁止反向填充。
- 公共复用：数据加载和通用收益/指标计算复用 `common/`；ML特有特征管线按需进入 `common/ml_pipeline.py`，`src/r003_equity_factor_timing_cn/` 只保留本策略配置与特有逻辑。
- 产出：月度特征面板、六因子成分/权重/收益、金融湍流、缺失率与发布日期审计表、全样本和分状态所需基础统计。
- 验证点：随机抽取至少12个宏观观测核对首次可用月；断言无 `bfill`；股票成分、ST/停牌/涨跌停过滤和财务披露日无未来穿越；六因子每月权重和为1。

### m2：第一阶段市场风险状态识别与预测

- 实现内容：滚动84个月K-Means、三类标签对齐、训练折内SMOTE、RF/SVC/GNB+Logistic Stacking、五折时序验证。
- 产出：肘部法图、回撤与风险状态图、分类混淆矩阵、accuracy/precision/recall、四类特征重要性、每月模型训练区间与参数记录。
- 验证点：每个预测月训练集严格早于预测月；聚类标签按中心稳定对齐；测试折无SMOTE合成样本；重新运行得到相同结果。

### m3：第二阶段分状态因子胜出概率模型

- 实现内容：Bear并入Correction；构造唯一胜出标签；每个滚动窗、状态和因子分别训练RF；按第一阶段预测状态选择概率；生成六因子概率并归一化。
- 产出：OOS胜出概率底表、`feature_importance.png`、`prediction_scatter.png`、`ic_series.png`、`train_val_loss.png`（滚动训练与时序验证log-loss）、相关矩阵和胜出频率图表。
- 验证点：标签严格来自下一月收益；并列处理确定性；每行六概率可复算；概率特征、标签与状态切分不存在同月收益泄漏。

### m4：四类组合权重与中国商业周期基准

- 实现内容：中证800、1/N、中国商业周期15%倾斜和ML概率权重四类组合；统一月度T+1执行规则；输出毛收益和成本情景的独立序列。
- 产出：逐月信号权重、实际执行权重、换手、毛收益、成本及净收益；商业周期标签与权重图；`group_cumulative_returns.png`。
- 验证点：四类组合权重和为1、无负权；信号日期早于执行/收益日期；成本只影响补充列，主结果始终为毛收益。

### m5：2023-04至2025-12严格样本外延伸与结果包

- 实现内容：在2023-03前冻结全部定义、参数和预处理；逐月仅用前84个月重训并预测下一月；不得因看到OOS结果调整特征、阈值、模型或成本。
- 产出：`backtest_summary.xlsx`、模型层/组合层多sheet明细、`metrics.json`、`comparison.json`、累计收益/回撤/胜出概率/特征重要性PNG、`run_log.md`、样本外证据清单。
- 核心指标：33个月覆盖率、分类accuracy/precision/recall、月度横截面RankIC、Top因子命中率、年化收益/波动/Sharpe、最大回撤、相对中证800超额收益/跟踪误差/信息比率、换手率。
- 验证点：独立核对首月训练窗为2016-04至2023-03；最后一个OOS月不晚于1Y/2Y/10Y国债共同最新月2025-12；报告明确区分中国市场结果和原研报美股基准。

## 五、难度判定

- 方法复杂度基准：两阶段滚动训练、K-Means、Stacking、SMOTE、分状态多RF模型和动态组合属于“训练模型/多模块联动”，基准即 `hard`。
- 数据可得性修正：核心美股数据均需中国市场替代且包含时点宏观、历史成分、财务质量和国债收益近似等复杂衍生；已到 `hard`，不再上调。
- 模块数量修正：规格共78个要素，其中63个为可行动项，另有D15-D29共15个原文未披露且不可恢复的占位项；m1-m5覆盖全部63个可行动项，D15-D29标记为`infeasible`且不进入里程碑。模型与组合模块显著超过8个；已到 `hard`，不再上调。
- 结论：`difficulty: hard`，拆为5个可独立实现与验证的闭环里程碑，依赖图为 `m1 -> m2 -> m3 -> m4 -> m5`，无环。

## 六、改进建议与潜在问题

- A1已由用户人工解除：实现必须冻结AS29所列中国代理集合，不得自行补写原文未披露的15个美国变量，也不得在看到OOS结果后增删代理特征。
- 中国CPI十年变化虽可由更长历史宏观数据计算，但主回测仍受国债1Y/2Y/10Y共同覆盖限制，从2015-01起；样本外只有约33个月，统计置信区间必须报告，避免把偶然领先解释成稳定有效。
- 用收益率变化和久期近似国债月收益不等于可交易国债指数收益；金融湍流应同时报告不含债券代理的敏感性结果，但不得据此改动主模型。
- Growth采用高PB完全遵循spec中的相对定义，却可能在中国市场更接近“昂贵”而非基本面成长；应在最终报告中作为迁移局限，而不是事后改名或换因子。
- 质量得分、金融条件代理和商业周期划分均为重要实验假设；verify若发现结论高度依赖这些口径，应交诊断阶段选择替代解释重测，不能在OOS期内调参。
- 原研报R1-R10只用于结构/方向参照；中国市场的核心判定是数据无泄漏、模型预测方向、相对中国基准的OOS表现及稳定性，不能以“接近原美股数值”作为成功标准。
