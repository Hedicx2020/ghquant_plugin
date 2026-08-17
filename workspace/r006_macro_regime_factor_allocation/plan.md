---
report_name: r006_macro_regime_factor_allocation
title: "When Do Anomalies Deserve Capital? Macro-Regime Memory and Dynamic Cross-Sectional Factor Allocation"
institution: 未注明
date: "2026-06-17"
type: allocation
tags: [factor, ml, macro_regime, market_transplant]
difficulty: hard
feasibility: degraded
reproduction_mode: experimental
template: templates/allocation.md
spec_ref: workspace/r006_macro_regime_factor_allocation/spec/spec.md
data_requirements:
  - name: "D1 Chen–Zimmermann/OpenAP 212 特征面板 → A股本地因子候选面板；以本地因子元数据、实际预计算因子及可由行情/估值/财报衍生的因子替代，原因是原美股 OpenAP 面板本地不可得"
    source: "factor_factor_info.parquet; factors/; ashare_stock_price_forward.parquet; ashare_stock_trade.parquet; ashare_stock_value.parquet; ashare_stock_balance.parquet; ashare_stock_income.parquet; ashare_stock_cashflow.parquet"
    status: substitute
  - name: "D2 1963–2024 美股股票月面板 → 本地可用期 A股股票月面板；由日行情、交易状态和交易日历按月汇总，原因是本地美股数据只能自 2000 年起且无法覆盖原样本"
    source: "ashare_stock_price_forward.parquet; ashare_stock_trade.parquet; ashare_stock.parquet; ashare_stock_st.parquet; ashare_stock_suspend.parquet; ashare_stock_limit.parquet; ashare_tradeday.parquet"
    status: substitute
  - name: "D3 OpenAP 逐信号方向元数据 → 本地因子训练窗内方向；只用训练样本估计并在后续验证/预测期冻结，原因是本地目录没有原 212 信号方向表"
    source: "factor_factor_info.parquet; factors/; m1 构造的本地因子面板"
    status: substitute
  - name: "D4 原 212 信号的八家族固定映射 → 本地 factor_id/factor_id_cn/level1/level2 与 AS26 固定关键词生成的一对一交叉表；原因是原逐信号映射与 empirical package 均不可得"
    source: "factor_factor_info.parquet（factor_id, factor_id_cn, level1, level2）"
    status: substitute
  - name: "D5 美国 23 个宏观条件变量 → 中国宏观与A股市场状态变量；保留 Inflation/Growth/Rates/Credit/Liquidity/Risk/Valuation/Trend 八块经济角色，原因是 FRED/ALFRED 原序列不可得"
    source: "macro_cache.parquet; macro_cpi.parquet; macro_ppi.parquet; macro_pmi.parquet; macro_money_supply.parquet; macro_social_financing.parquet; macro_lpr.parquet; macro_industrial_production.parquet; bond_yield_curve.parquet; bond_shibor.parquet; ashare_csiindex_trade.parquet; ashare_index_value.parquet"
    status: substitute
  - name: "D6 ALFRED 实时/保守 vintage → 本地发布日期缺失条件下的固定保守滞后快照；原因是本地目录无 vintage 历史"
    source: "macro_cache.parquet 及 D5 所列宏观文件的 date/indicator_name/data_value；ashare_tradeday.parquet"
    status: substitute
  - name: "D7 原美股面板衍生市场状态 → A股指数趋势、估值、风险和市场流动性状态；原因是 1963–2024 美股底层面板不可得"
    source: "ashare_csiindex_trade.parquet; ashare_index_value.parquet; ashare_index_trade.parquet; ashare_stock_trade.parquet"
    status: substitute
  - name: "D8 美国 FF5 加动量 → A股本地市场、规模、价值、盈利、投资和动量控制组合；原因是本地目录没有美国 FF5+MOM 收益序列"
    source: "ashare_stock_price_forward.parquet; ashare_stock_trade.parquet; ashare_stock_value.parquet; ashare_stock_balance.parquet; ashare_stock_income.parquet; ashare_csiindex_trade.parquet"
    status: substitute
  - name: "D9 原美股市值/行业/beta/流动性代理 → A股流通市值、申万一级行业、历史 beta 与成交/换手代理；原因是原口径和历史覆盖不可得"
    source: "ashare_stock_trade.parquet（market_value, negotiable_market_value, turn_value, turnover_rate_free）; ashare_stock_industry.parquet（standard_code=38）; ashare_csiindex_trade.parquet"
    status: substitute
  - name: "D10 原 212 信号发表年份 → 本地因子面板首次非缺失月份；作为本地可用性审计而非学术发表年份，原因是本地目录无 publication year 元数据"
    source: "factors/; m1 构造的本地因子面板"
    status: substitute
milestones:
  - id: m1
    name: "市场迁移数据底座与时点安全"
    desc: "固化 D1–D10 的本地替代清单，构造A股月频 point-in-time 面板、保守宏观可用时点、10年训练+12年验证的滚动窗口和数据审计闭环；财务字段按 info_publ_date 对齐，所有 T 月末信号只允许 T+1 首个可交易日执行，并按 AS26 的固定公开分类交叉表生成八家族映射及哈希。"
    deps: []
    elements: [D1, D2, D3, D4, D5, D6, D7, D8, D9, D10, F16, B1, B2, B3, B4, B5, B6, B7, R14, R23, SA11, SA13]
  - id: m2
    name: "本地因子家族袖套与统计评价"
    desc: "按 AS26 的确定性家族映射完成方向统一、月度十分位 EW/VW 袖套、IC、Fama–MacBeth、Newey–West、A股六因子控制、换手与成本敏感性，并独立产出袖套收益、覆盖率和映射冲突诊断。"
    deps: [m1]
    elements: [F1, F2, F12, F13, F14, B9, B10, B11, B12, B13, R16, R25]
  - id: m3
    name: "宏观状态与容量机制验证"
    desc: "按 AS25 的 expanding z-score、块内等权、12月半衰 EWMA 和历史 expanding median 固定规则构建严格滞后的八块状态，检验状态—家族收益面、Liquidity/limits×Trend、容量边界、形成/确认期、安慰剂和事件剔除。"
    deps: [m1, m2]
    elements: [F3, F15, B14, B15, R7, R8, R9, R10, R12, R19, R20, R24, SA4, SA5, SA6, SA7, SA8, SA9, SA10, SA14]
  - id: m4
    name: "滚动家族动态配置"
    desc: "按 AS24 的四专家集合与验证窗 Sharpe softmax 门控，在固定训练/验证/预测窗口内实现方法级降级 MoE、非负且和为一的家族权重、组合回测和消融，生成 allocation 类型必需 Excel/PNG。"
    deps: [m1, m2, m3]
    elements: [F4, F5, F6, F7, F8, B8, R1, R2, R3, R13, R15, R17, R18, SA1, SA2, SA3]
  - id: m5
    name: "层级信号与股票层模型基准"
    desc: "把家族权重下传到本地因子层，按 AS27 的固定预处理、alpha 网格和两阶段宏观残差规格完成 pooled ridge、模型类别比较和局部状态可靠性，逐项验证方法方向而非原文数值。"
    deps: [m1, m2, m3, m4]
    elements: [F9, F10, F11, R4, R5, R6, R11, R21, R22, R26, R27, R28, SA12]
---

# When Do Anomalies Deserve Capital? Macro-Regime Memory and Dynamic Cross-Sectional Factor Allocation 复现开发计划

## 研报信息

- 标题：When Do Anomalies Deserve Capital? Macro-Regime Memory and Dynamic Cross-Sectional Factor Allocation
- 来源机构：未注明
- 发布日期：2026-06-17
- 作者：Nima Taheri Hosseinkhani
- 原文市场：美股
- 复现市场：A股，`reproduction_mode=experimental`
- 主类型：`allocation`。最终回测对象是在八个异常家族袖套之间形成动态、非负且和为一的资本权重；截面因子与机器学习是辅助维度，因此进入 `tags`。

## 难度判定

- 方法复杂度基准：`hard`。主线同时包含多袖套动态配置、滚动训练/验证/预测、Mixture-of-experts、层级信号下传、ridge 与宏观残差模型，触发“训练模型/优化求解/多资产联动”任一即 hard。
- 数据可得性修正：原 OpenAP 212 面板、美国宏观 vintage、FF5+MOM 与样本覆盖均不可直接取得，实验模式需十项市场迁移替代；难度已经封顶，不再上调。
- 模块数修正：八个异常家族、八个宏观块和多个模型基准显著超过八个模块；难度已经封顶。
- 最终难度：`hard`。
- 可行性：`degraded`。用户已授权检索公开资料并采用透明固定口径继续。A1、A2、A3、A6 均以 `method-degraded` 基准实现，能够编码和验证，但这些口径不是原文事实，不能用于声称精确复现。

## 公开资料检索记录

访问日期统一为 2026-07-26。技术与论文事实只采用作者/项目第一方页面、原始论文或官方文档。

| 用途 | 第一方来源与固定版本 | 检索结论 |
| --- | --- | --- |
| 同名论文身份 | SSRN `abstract_id=6962678`，论文日期 2026-06-17，DOI `10.2139/ssrn.6962678`，`https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6962678` | 确认标题、作者、摘要和论文日期；SSRN 摘要页未提供可识别的公开代码仓库链接 |
| 作者身份/项目 | 作者主页 `https://nimataherihosseink.wixsite.com/nima-taheri-hosseink`；ORCID `https://orcid.org/0009-0007-5564-7839` | 作者主页的公开 Academic Projects 页面未列出本论文实现 |
| 原作者实现 | 以论文完整标题、作者姓名、Rutgers 邮箱域和 GitHub 进行精确检索 | 未找到该论文作者公开代码或 empirical package；后续若发现作者实现，须作为新版本来源重新审计，不静默替换本口径 |
| 因子元数据基准 | Open Source Asset Pricing 官网 `https://www.openassetpricing.com/`；官方仓库固定 commit `8db892442c2c3a3779b0f1eac4370d3655be15a1`，`https://github.com/OpenSourceAP/CrossSection/tree/8db892442c2c3a3779b0f1eac4370d3655be15a1`；固定文件 `SignalDoc.csv` | 官方仓库明确提供 stock-level signals、`SignalDoc.csv` 与组合代码；`SignalDoc.csv` 含 `Cat.Economic` 和 `Sign`，只用于设计透明降级映射，不宣称等于本论文八家族表 |
| MoE 方法类别 | Jacobs、Jordan、Nowlan、Hinton（1991）原始论文，DOI `10.1162/neco.1991.3.1.79`；Hinton 作者页 `https://www.cs.toronto.edu/~hinton/mixex.html` | 原始 MoE 以专家与门控网络组合输出；AS24 采用其“专家+门控”结构思想，但四专家和验证 Sharpe 门控均为本计划固定基准 |
| Ridge/时序隔离 | scikit-learn 1.9.0 官方 `Ridge`、`StandardScaler`、`TimeSeriesSplit` 文档：`https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html`、`https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html`、`https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html` | `Ridge` 目标为平方误差加 L2 惩罚；标准化只拟合训练样本；时间序列拆分保持时间顺序 |
| 状态记忆 | pandas 3.0.5 官方 `DataFrame.ewm` 文档，`https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.ewm.html` | AS25 固定使用 `halflife=12, adjust=False, min_periods=12`；该参数是本计划选择，不是原文参数 |

## 一、核心策略与创新点

### 1.1 研究背景与核心思想

原文不是直接在传统股债商品之间分配，而是把八个经济异常家族视为八个可配置袖套。每个月利用截至当时可得的家族历史收益、家族 IC 与宏观状态记忆，决定下一期各袖套资本份额；再把家族权重向下传至个股因子层，检验排序、组合收益和容量机制。

实验复现保留“家族袖套—宏观状态—动态配置—层级股票排序”四层结构，把美国数据对象迁移为A股本地点时数据。验证目标是方法忠实性、方向性、稳定性和无未来函数，不以原文数值对齐作为通过条件。

### 1.2 因子、状态与策略构造

1. 本地因子方向统一。对本地因子 \(j\)，仅在训练窗估计方向 \(s_j\in\{-1,+1\}\)，冻结后形成
   \[
   x'_{i,j,t}=s_j x_{i,j,t}.
   \]
   横截面预处理及缺失值口径按 AS11；不得用验证期或预测期收益回看方向。

2. 家族袖套。按 AS26 的确定性关键词字典，把 `level1`、`level2`、`factor_id_cn`、`factor_id` 依次规范化并映射到八个经济家族；字段优先级依次为 `level1 > level2 > factor_id_cn > factor_id`，同字段多命中时取最长关键词，再同长时按 Valuation、Continuation、Correction、Profitability/quality、Investment/issuance、Safety/downside、Liquidity/limits、Expectations 的固定顺序裁决。未命中因子不进入家族袖套，映射表及关键词配置生成 SHA-256 后在全部预测年度冻结。每个因子月度形成十分位多空收益，家族内部等权聚合为袖套收益 \(r_{f,t}\) 与家族 IC \(IC_{f,t}\)。

3. 宏观状态。按 AS25 对每个已完成 AS16 保守时点处理的变量 \(x_{k,t}\) 做只含当期及历史的 expanding z-score：
   \[
   z_{k,t}=\operatorname{clip}\!\left(\frac{x_{k,t}-\bar x_{k,\le t}}{s_{k,\le t}},-3,3\right),
   \]
   其中 `ddof=1`、`min_periods=36`。同一经济序列优先采用 `macro_cache` 版本，缺失时才使用对应明细表，禁止重复计权；m1 将实际序列清单及哈希冻结。块内对当月有效 \(z_{k,t}\) 等权，随后使用 pandas 3.0.5 的 `ewm(halflife=12, adjust=False, min_periods=12)` 形成记忆值 \(M_{b,t}\)。状态阈值为截至 \(t-1\) 的 \(M_b\) expanding median（至少 36 个历史记忆值）；\(M_{b,t}\) 严格大于阈值记 high，否则记 low。冻结块内序列不足一半、历史不足或标准差为零时该块当月记缺失，不以未来值补齐。

4. 动态配置。AS24 将原文未披露的 MoE 透明降级为四个可编码专家：
   - `E0` 等权专家：八家族恒为 \(1/8\)；
   - `E1` 收益专家：用训练历史的家族年化 Sharpe，截断到 \([-3,3]\) 后做温度 \(\tau=1\) 的 family softmax；
   - `E2` IC 专家：用训练历史 \(\sqrt{12}\,\overline{IC}_f/s(IC_f)\)，截断到 \([-3,3]\) 后做同样的 family softmax；
   - `E3` 状态专家：对每个块按当前 high/low 状态读取训练历史中同状态的下一月家族平均收益，八块等权求和后除以训练期家族收益标准差，截断到 \([-3,3]\) 并做 family softmax。

   验证期内各专家必须逐月只用当月以前数据产生权重；以固定 144 月验证期的毛收益计算年化 Sharpe \(SR_e\)，截断到 \([-3,3]\)，门控权重固定为
   \[
   g_e=\frac{\exp(SR_e)}{\sum_{j=0}^{3}\exp(SR_j)},\qquad
   \mathbf w_t=\sum_{e=0}^{3}g_e\mathbf w^{(e)}_t.
   \]
   专家定义、门控权重、收益/IC统计量和 E3 状态收益表在每个预测年开始前冻结 12 个月；年内只有 E3 因当期 AS25 状态切换而改变家族权重。标准差为零或有效观察不足 24 月的专家分数记 0；验证有效月份不足 120、权重非有限、出现负权重或权重和偏离 1 超过 \(10^{-10}\) 时该预测年度判方法失败，不产生主结果。四专家和门控均是用户授权的 `method-degraded` 固定基准，不是原文实现事实。

5. T/T+1 组合收益。T 月最后一个交易日收盘后计算信号与目标权重，仅在 T+1 首个可交易日执行：
   \[
   R_{p,t+1}=\sum_f w_{f,t}r_{f,t+1}-c\cdot TO_{t+1}.
   \]
   任何需要当期实现收益、当月未发布宏观值或财报 `end_date` 才能得到的输入均禁止进入 \(w_{f,t}\)。

6. 股票层模型。AS27 固定以 T 月本地因子向量预测 T+1 月股票收益。连续特征先按训练样本中位数填充，再由 scikit-learn 1.9.0 `StandardScaler` 仅拟合训练样本；常数列删除。第一层 pooled ridge 为
   \[
   \hat\beta_\lambda=\arg\min_\beta\sum_{(i,t)\in train}(y_{i,t+1}-X_{i,t}\beta)^2+\lambda\|\beta\|_2^2,
   \]
   其中 \(y_{i,t+1}\) 为下一月个股收益减当月股票截面等权收益，先在每月截面按 1%/99% 缩尾；\(\lambda\in\{10^{-4},10^{-3},10^{-2},10^{-1},1,10,10^2,10^3,10^4\}\)。第二层以不与本观测同折训练的第一层预测残差为目标，特征固定为八个 AS25 宏观记忆值与“八个家族平均因子分数 × 八个宏观记忆值”的 64 个交互项，使用同一九档 alpha 网格的 residual ridge。先按验证期月均 Pearson IC 选择第一层 alpha，再在第一层固定后按最终组合 IC 选择第二层 alpha；并列取较大的 alpha。每个预测年前用当时全部可用的训练+验证数据重拟合填充值、缩放器和两层系数，随后冻结 12 个月。任一训练/验证穿越预测年、变换器使用预测期数据、有效验证月少于 120、两层均无有限预测或样本外 IC 无法计算时判该年度方法失败。该两层规格是用户授权的 `method-degraded` 基准，不是原文未披露 empirical package 的恢复。

### 1.2.1 AS26 固定关键词字典与方法来源

文本统一转小写、全角转半角、去空白和标点后匹配；英文短词 `pe/pb/ps/roe/roa` 只按完整 token 匹配。关键词字典固定如下，不允许由回测结果反向调整：

| 家族 | 固定关键词 |
| --- | --- |
| Valuation | 估值、价值、股息率、市盈率、市净率、市销率、value、valuation、book-to-market、earnings yield、dividend yield、pe、pb、ps |
| Continuation | 动量、趋势、延续、相对强弱、momentum、trend、continuation、relative strength |
| Correction | 反转、均值回归、超跌、过度反应、reversal、mean reversion、overreaction、short-term reversal |
| Profitability/quality | 盈利、质量、利润率、资产回报、净资产收益、应计、profitability、quality、margin、roe、roa、accrual |
| Investment/issuance | 投资、资本开支、资产增长、发行、融资、investment、capex、asset growth、issuance、financing |
| Safety/downside | 安全、下行、低波、波动、贝塔、困境、杠杆、safety、downside、low volatility、volatility、beta、distress、leverage |
| Liquidity/limits | 流动性、非流动性、换手、成交、涨跌停、liquidity、illiquidity、turnover、volume、limit |
| Expectations | 预期、预测、分析师、修正、情绪、expectations、forecast、analyst、revision、sentiment |

映射验证固定报告：总因子数、八家族计数、未命中数、多命中数、字段/关键词命中轨迹及映射 SHA-256。任一家族为零、同一 `factor_id` 产生多行归属、哈希在预测期变化或人工修改未形成新假设版本时，m1/m2/m5 判方法失败。公开方法锚点为 Open Source Asset Pricing `SignalDoc.csv` 的 `Cat.Economic`/`Sign` 设计，固定仓库 commit `8db892442c2c3a3779b0f1eac4370d3655be15a1`，访问日期 2026-07-26；本地关键词字典与原 OpenAP 分类均不被表述为原文 212 信号映射。

### 1.2.2 四项方法级降级的来源、验证与边界

| 歧义/假设 | 用户授权与公开来源 | 固定验证 | 失败条件 |
| --- | --- | --- | --- |
| A1 / AS24 | 用户于 2026-07-26 授权公开检索和透明固定口径；Jacobs et al. (1991)，DOI `10.1162/neco.1991.3.1.79`，Hinton 作者页 `https://www.cs.toronto.edu/~hinton/mixex.html`，访问日期 2026-07-26 | 逐月重放验证期，确认每个专家只读当时历史；复算 Sharpe softmax、年度冻结、非负与和为一 | 验证有效月不足 120、时间穿越、非有限/负权重或权重和误差超过 \(10^{-10}\) |
| A2 / AS25 | 同上用户授权；pandas 3.0.5 官方 `DataFrame.ewm`，`https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.ewm.html`，访问日期 2026-07-26 | 独立复算 expanding z-score、块内等权、`halflife=12` EWMA 与 \(t-1\) expanding median；审计最大源日期 | 冻结块内有效序列不足一半、历史不足、零方差或任一预测月不能形成八块完整状态 |
| A3 / AS26 | 同上用户授权；Open Source Asset Pricing 官网 `https://www.openassetpricing.com/` 与固定 commit/`SignalDoc.csv`，访问日期 2026-07-26 | 以同一配置重复生成交叉表并比较逐行结果及 SHA-256 | 空家族、多重归属、预测期哈希漂移或回看收益后改词典 |
| A6 / AS27 | 同上用户授权；scikit-learn 1.9.0 官方 `Ridge`、`StandardScaler`、`TimeSeriesSplit` 文档，URL 见“公开资料检索记录”，访问日期 2026-07-26 | 复算九档 alpha 选择、训练期缩放器、两层残差与年度系数冻结；用时间移位测试排查泄漏 | 有效验证月不足 120、预测期进入拟合/变换、两层无有限预测或样本外 IC 无法计算 |

四项均只验证透明固定基准是否按计划实现及其在A股的方向性结果；公开来源仅支持方法类别和 API 语义，不证明这些参数来自原文。

### 1.3 创新点

- 把宏观状态用作异常家族收益“记忆”，动态决定资本配置，而不是只做静态等权。
- 先配置八个经济家族，再向下传到完整因子层，兼顾经济解释与截面覆盖。
- 以滚动训练、固定验证窗和年度样本外预测隔离模型选择与测试。
- 把 Liquidity/limits × Trend 的收益状态差与市值容量区域联结，检验经济机制而非只看组合均值。

## 二、资产池、数据映射与回测参数

### 2.1 资产池定义

- 配置资产：八个本地A股异常家族袖套，名称沿用 Valuation、Continuation、Correction、Profitability/quality、Investment/issuance、Safety/downside、Liquidity/limits、Expectations。
- 股票母样本：本地A股历史股票月观察，过滤规则见 AS23；不使用当前成分反推历史股票池。
- 市场基准：由 `ashare_csiindex_trade.parquet` 中实际可用的宽基指数代码在 m1 数据清单中固化；spec 未指定A股代码，planner 不臆测。
- 因子控制：以A股本地市场、规模、价值、盈利、投资和动量控制组合替代美国 FF5+MOM；财务分组只允许使用 `info_publ_date <= signal_date` 的记录。

### 2.2 原文数据到本地等价替代

| D 要素 | 原文数据 | 本地等价替代 | 选择理由 | 假设 |
| --- | --- | --- | --- | --- |
| D1 | OpenAP 212 特征面板 | 本地因子元数据、实际 `factors/` 与行情/估值/财报衍生因子 | 保留“宽因子面板”研究对象，不宣称等同 212 | AS1 |
| D2 | 1963–2024 美股股票月 | 本地可用期A股日数据重采样股票月 | 本地可构造可交易股票月，但历史区间不同 | AS4 |
| D3 | 原逐信号方向 | 训练窗内估计并冻结的本地方向 | 避免使用未来期收益，同时保持高值对应高预期收益 | AS2 |
| D4 | 原八家族逐信号表 | `factor_id_cn/level1/level2` 加 AS26 固定关键词的一对一交叉表 | 用户授权方法级降级；映射可复算并冻结哈希，但不冒充原映射 | AS3、AS26 |
| D5 | 美国 23 宏观变量 | 中国宏观、利率和A股市场变量组成八块 | 保留经济角色，不追求变量身份相同 | AS5 |
| D6 | ALFRED vintage | 固定保守滞后的本地宏观快照 | 本地无 vintage，固定滞后可审计且防未来函数 | AS6 |
| D7 | 美股面板衍生状态 | A股指数趋势/风险/估值/流动性状态 | 保留市场状态含义 | AS7 |
| D8 | 美国 FF5+MOM | A股本地六控制组合 | 保留风险调整角色 | AS8 |
| D9 | 美股容量与控制 | A股流通市值、行业、历史 beta、成交与换手 | 字段均由 data_catalog 明示 | AS9 |
| D10 | 信号发表年份 | 本地因子首次非缺失月份 | 只能解释为本地可用性审计，不冒充发表年份 | AS10 |

### 2.3 宏观八块的本地候选原料

本表确定 data_catalog 明示的输入原料；变换、块内聚合、记忆与 high/low 统一按 AS25 的固定规则执行。同一经济序列优先采用 `macro_cache`，缺失时才使用对应明细表，避免重复计权。

| 宏观块 | 本地候选原料 |
| --- | --- |
| Inflation | `macro_cache.cpi_yoy`、`macro_cache.ppi_yoy`，以及 `macro_cpi`/`macro_ppi` |
| Growth | `macro_cache.gdp_real_yoy`、`macro_pmi`、`macro_industrial_production` |
| Rates | `macro_cache.bond_yield_10y`、`macro_lpr`、`bond_yield_curve`、`bond_shibor` |
| Credit | `macro_cache.credit_spread`、`macro_cache.social_financing_yoy` |
| Liquidity | `macro_cache.m1_yoy`、`macro_cache.m2_yoy`、`macro_money_supply`、`macro_social_financing` |
| Risk | `ashare_csiindex_trade` 收益衍生的历史波动与回撤 |
| Valuation | `ashare_index_value` 的 `pe_ttm/pb_lf/ps_ttm/dv` |
| Trend | `ashare_csiindex_trade` 的历史收益与价格趋势 |

### 2.4 回测参数

| 参数 | 原文规格 | 实验复现口径 |
| --- | --- | --- |
| 历史起点 | 1963 | 取本地因子面板与滞后宏观数据的共同首月 \(t_0\)，由 m1 实测固化 |
| 初始训练窗 | 10 年 | 从 \(t_0\) 起 120 个月 |
| 固定验证窗 | 12 年 | 紧接训练窗的 144 个月，之后年度滚动且固定长度 |
| 样本外 | 1985-01 至 2024-11，479 月 | 从本地首个完整预测年度至本地共同末月；不要求月份数对齐 |
| 模型选择 | 预测年前完成 | 每年只使用前一验证窗评价候选规则 |
| 调仓 | 月度 | T 月末收盘后计算，T+1 首个可交易日执行 |
| 持有期 | 未明确 | 一个月，下一次调仓替换，见 AS11 |
| 组合权重 | 非负、和为一 | 按 AS24 四专家与验证 Sharpe softmax 门控；温度 1、分数截断 \([-3,3]\)、预测年前冻结 12 个月 |
| 十分位 | 十分位多空 | 本地月度合格股票横截面 10 组，高减低 |
| EW/VW | 均报告 | EW 与按 T 时点 `negotiable_market_value` 的 VW 均报告 |
| 成本/换手 | 费率与口径未给 | 毛收益为主；单边换手并给 10/30 bps 净收益敏感性，见 AS22 |
| NW | 月度，滞后未给 | HAC lag=6 为主并报告 3/12 月敏感性，见 AS13 |
| 财务时点 | 预测期前可用 | 所有资产负债表、利润表、现金流字段按 `info_publ_date` 做 as-of join；禁止按 `end_date` 直接对齐 |

## 三、研报核心结果（验证基准）

下表只列覆盖关系。数值、原文与页码以 `spec.md` 的 R 类条目为唯一权威来源；实验市场迁移不以数值一致为验收条件。

| R 要素ID | 一句话摘要 | 关联 milestone |
| --- | --- | --- |
| R1 | 宏观块与主要配置规则 | m4 |
| R2 | 家族配置表现 | m4 |
| R3 | Mixture-of-experts 家族权重 | m4 |
| R4 | 完整信号层级证据 | m5 |
| R5 | 股票层 pooled ridge 基准 | m5 |
| R6 | 受控横截面预测与 alpha | m5 |
| R7 | 状态—家族收益图 | m3 |
| R8 | Liquidity/limits × Trend 跨样本机制 | m3 |
| R9 | 容量前沿 | m3 |
| R10 | 状态特异性 | m3 |
| R11 | 模型类别基准 | m5 |
| R12 | 形成期与确认期 | m3 |
| R13 | 家族组合消融 | m4 |
| R14 | 实时宏观信息时点 | m1 |
| R15 | 家族基线预测 | m4 |
| R16 | 家族袖套收益与换手 | m2 |
| R17 | 配置规则变体 | m4 |
| R18 | 家族权重分布 | m4 |
| R19 | 完整状态—家族收益面 | m3 |
| R20 | 机制控制与年代 | m3 |
| R21 | 逐家族剔除 | m5 |
| R22 | 局部状态可靠性 | m5 |
| R23 | 信号发表/可用性覆盖 | m1 |
| R24 | 逐事件剔除 | m3 |
| R25 | 家族内信号构成 | m2 |
| R26 | 层级十分位组合指标 | m5 |
| R27 | 配置规则股票层 IC 与 Fama–MacBeth | m5 |
| R28 | Horse-race 与受控结果 | m5 |

## 四、复现计划

### m1：市场迁移数据底座与时点安全

- 依赖：无。
- 固定口径：D1–D10 按 frontmatter 的 substitute 清单迁移；因子家族交叉表严格按 AS26 的字段优先级、关键词、冲突顺序和哈希冻结规则生成。
- 实现内容：
  - 只从 frontmatter 列出的本地 parquet 加载字段，形成源文件、字段、覆盖、缺失率和共同起止月清单。
  - 将日行情重采样为月频；收益优先使用前复权价格或 `change_pct`，禁止混用未复权价格计算跨期收益。
  - 财务数据以 `info_publ_date <= signal_date` 选最新已披露记录，保留 `end_date` 仅作报告期标签。
  - 宏观月频固定至少滞后一个月，季度数据固定滞后四个月；市场派生状态只用 T 日及以前数据。
  - 建立 120 月训练、144 月验证、年度滚动预测索引；共同历史不足 264 月时触发 m1 数据失败条件，输出不足证据且不生成后续模型主结果。
  - 统计本地因子首次非缺失月，只作为 D10 的本地可用性审计。
- 产出文件：`data_manifest.xlsx`、`point_in_time_audit.xlsx`、`walk_forward_windows.xlsx`、`local_factor_crosswalk_draft.xlsx`。
- 验证点：
  - 任意财务观测满足 `info_publ_date <= signal_date`。
  - 任意预测行的最大源日期不晚于信号时点；T 信号对应执行日严格大于 T。
  - 原始日频到月频的复算样本一致，训练/验证/预测无重叠。
  - 十项 substitute 均在结果元数据中保留原数据、替代数据、理由和 AS 编号。

### m2：本地因子家族袖套与统计评价

- 依赖：m1。
- 固定口径：只接收 m1 生成且 SHA-256 已冻结的 AS26 一对一交叉表；未命中因子留在映射审计表，不进入任何袖套。
- 实现内容：
  - 训练窗内确定方向，1%/99% 缩尾并标准化；验证和预测期冻结方向。
  - 每月在合格股票横截面形成十分位高减低组合，同时计算 EW、VW、Pearson IC 和 Fama–MacBeth。
  - 构造A股本地市场、规模、价值、盈利、投资、动量控制；财务腿仍按 `info_publ_date`。
  - 报告月度 HAC、单边换手、毛收益及 10/30 bps 净收益敏感性。
- 产出文件：`family_sleeve_results.xlsx`、`factor_control_returns.xlsx`、`family_sleeve_nav.png`、`family_turnover.png`。
- 验证点：
  - 因子方向与家族映射在每个预测年度开始前冻结。
  - 任一 T 月排序仅使用 T 及以前字段，收益标签始于 T+1。
  - EW/VW 权重和、十分位样本数、换手恒等式和 HAC 复算通过。
  - R16 只做方法/方向对照，不声称与美股数值一致。

### m3：宏观状态与容量机制验证

- 依赖：m1、m2。
- 固定口径：按 AS25 使用 `min_periods=36` 的 expanding z-score、块内等权、pandas 3.0.5 `ewm(halflife=12, adjust=False, min_periods=12)` 和截至 \(t-1\) 的 expanding median。
- 实现内容：
  - 构建八块状态，完整记录每个 z-score、块均值、EWMA、阈值和状态值的源数据截止日。
  - 计算八状态×八家族 payoff surface、IC surface 和 state-specificity。
  - 以 T 时点流通市值分位形成八个容量区域；构造行业中性、beta 中性和流动性代理。
  - 冻结形成期方向后进入确认期；执行日历/随机/移位/标签安慰剂、宏观块剔除、年代和事件剔除。
- 产出文件：`macro_state_panel.xlsx`、`regime_family_surface.xlsx`、`capacity_frontier.xlsx`、`holdout_placebo.xlsx`、`regime_family_heatmap.png`、`asset_contribution.png`。
- 验证点：
  - 宏观输入的可用日期审计零违规；所有状态在 T 时点可复算。
  - high/low 阈值只从规定历史窗估计，确认期不重估方向。
  - 行业/市值/beta/流动性构造均只用 catalog 明示字段。
  - 随机和置换测试固定随机种子并保留样本月集合。

### m4：滚动家族动态配置

- 依赖：m1、m2、m3。
- 固定口径：按 AS24 的 E0 等权、E1 收益、E2 IC、E3 状态四专家及 144 月验证 Sharpe softmax 门控实现；温度 1、专家和门控分数截断 \([-3,3]\)，预测年前冻结 12 个月。
- 实现内容：
  - 严格按年度 walk-forward 在训练窗拟合、验证窗选择、下一预测年度锁定。
  - 实现 AS24 固定的四专家 Mixture-of-experts、验证 Sharpe 门控与 spec 列示比较规则；权重非负且和为一。
  - 回测家族配置、等权基准、约束变体、家族组合和逐家族消融。
  - 生成 allocation 模板要求的权重、净值、贡献、波动与回撤结果。
- 产出文件：`backtest_summary.xlsx`、`allocation_weights.xlsx`、`allocation_ablations.xlsx`、`weight_evolution.png`、`portfolio_nav.png`、`rolling_volatility.png`、`drawdown.png`。
- 验证点：
  - 任何预测年度的规则选择不接触该年度收益。
  - 每期权重最小值不低于 0，权重和误差不超过 \(10^{-10}\)。
  - T 目标权重只在 T+1 执行；换手和成本从实际执行权重计算。
  - 仅比较A股本地策略与本地等权/静态基准，不把原文数值容差作为 experimental 结论。

### m5：层级信号与股票层模型基准

- 依赖：m1、m2、m3、m4。
- 固定口径：家族映射只用 AS26 冻结哈希；股票模型按 AS27 的训练期中位数填充、`StandardScaler`、九档 alpha、第一层 pooled ridge 与第二层宏观残差 ridge 实现，并在预测年前冻结 12 个月。
- 实现内容：
  - 将家族权重下传到 AS26 映射的本地因子层，形成层级股票预期收益和十分位组合。
  - 按 AS27 实现 pooled ridge、ridge 加宏观残差、SGD/神经网络等比较；所有超参数只用训练/验证窗。
  - 计算 IC、增量 IC、Fama–MacBeth、A股六因子 alpha、模型消融和局部状态可靠性。
- 产出文件：`hierarchical_signal_results.xlsx`、`stock_model_benchmarks.xlsx`、`local_reliability.xlsx`、`hierarchical_nav.png`、`stock_model_ic.png`。
- 验证点：
  - 训练特征、标签、超参数选择与样本外预测严格时间隔离。
  - 财务输入继续按 `info_publ_date`；标准化参数只来自训练窗。
  - 层级权重从 m4 已冻结权重下传，不在股票层反向使用未来表现。
  - 对 R4–R6/R11/R21/R22 只做方法、排序能力和方向性比较。

## 五、改进建议与潜在问题

- A1、A2、A3、A6 已按用户授权裁决为透明的 `method-degraded` 固定基准；不得通过参数搜索反推原文，也不得把这些口径改写为原文事实。
- `factors/` 的实际文件和日期字段未在 data_catalog 展开，m1 只能做目录内实际可见内容的清单；任何未列示因子不得臆造。
- 本地共同样本远短于原文 1963–2024；应报告有效训练、验证和样本外月数，并避免把少量样本外年份解释成长期证据。
- 宏观固定滞后只是无 vintage 条件下的保守替代，需将额外滞后敏感性作为时点审计，而非宣称等同 ALFRED。
- 本地首次可用月不是学术发表年份，R23/SA13 只能作为数据覆盖审计。
- `ashare_stock.parquet` 的 `list_state` 不应作为历史股票池的唯一条件；应基于当时已有行情、上市日期与状态事件构造，避免幸存者偏差。
- 交易成本、停牌与涨跌停会导致目标权重和实际权重偏离；必须同时保存目标权重、实际执行权重和未成交原因。
- feasibility 保持 `degraded`；是否满足 plan 门禁由主流程和后续审计独立判定，本计划不作通过声明。
