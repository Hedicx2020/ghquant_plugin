---
report_name: r004_all_a_style_box
title: "Equity Factor Timing: A Two-Stage Machine Learning Approach"
institution: "The Vanguard Group, Inc."
date: 2024-01-25
type: factor
tags: [china_market, all_a, style_box, out_of_sample]
difficulty: hard
feasibility: feasible
template: templates/factor.md
spec_ref: workspace/r004_all_a_style_box/spec/spec.md
data_requirements:
  - name: "原 Russell 1000/3000 股票池 → 动态中国全A股票池（沪深北，不用 CSI 800 成分）"
    source: "ashare_stock.parquet + ashare_stock_price_forward.parquet + ashare_stock_trade.parquet；本地A股证券主表与逐日可交易记录可构造"
    status: substitute
  - name: "原文来源冲突的美股六因子月收益（Refinitiv vs FRED/Factset，仅背景）→ 中国全A个股前复权收益并自底向上聚合四个风格箱"
    source: "实际实现唯一使用data_catalog本地源：ashare_stock_price_forward.parquet + ashare_stock_trade.parquet；日频原料衍生月度组合收益，关联A23/AS22"
    status: substitute
  - name: "原美股市值/Small-Cap 输入 → 中国全A总市值与流通市值"
    source: "ashare_stock_trade.parquet 的 market_value / negotiable_market_value"
    status: substitute
  - name: "原美股低/高P/B风格输入 → 中国全A时点估值复合输入"
    source: "ashare_stock_value.parquet 的 pe_ttm / pb_lf / ps_ttm / dv"
    status: substitute
  - name: "原高P/B Growth代理 → 中国全A披露日可得的营收/净利润增长复合输入"
    source: "ashare_stock_income.parquet；只按 info_publ_date <= 信号日做PIT匹配"
    status: substitute
  - name: "原 Russell 1000 基准 → 动态中国全A流通市值加权基准"
    source: "ashare_stock_price_forward.parquet + ashare_stock_trade.parquet；与当期合格股票池同口径"
    status: substitute
  - name: "上市、退市与上市时长过滤"
    source: "ashare_stock.parquet 的 list_date / list_state，并结合逐日有效行情避免用期末状态回溯筛选"
    status: derive
  - name: "ST区间过滤"
    source: "ashare_stock_st.parquet 的 implement_date / remove_date"
    status: available
  - name: "停牌过滤与执行限制"
    source: "ashare_stock_suspend.parquet 的 date / if_suspend"
    status: available
  - name: "涨跌停过滤与执行限制"
    source: "ashare_stock_limit.parquet 的 surged_limit / decline_limit / limit_board"
    status: available
  - name: "月末信号日与T+1执行日"
    source: "ashare_tradeday.parquet 的 IfTradingDay / IfMonthEnd"
    status: derive
milestones:
  - id: m1
    name: "动态全A与PIT数据底座"
    desc: "构造沪深北动态全A月末合格池、PIT估值/财务快照、T+1可交易标记与无未来函数的数据审计表。"
    deps: []
    elements: [D14, B1, B10]
  - id: m2
    name: "2×2大小盘与成长价值风格构造"
    desc: "冻结size与growth/value复合分数，按大小盘内条件中位数生成BV/BG/SV/SG四箱及连续诊断信号。"
    deps: [m1]
    elements: [F11, F12, F16]
  - id: m3
    name: "组合、成本与中国交易约束回测"
    desc: "按月末T信号、T+1执行形成四箱、全A基准、SMB、HML与GML净收益，并处理停牌、涨跌停、换手和成本。"
    deps: [m2]
    elements: [F19, B7, B11, SA3]
  - id: m4
    name: "OOS报告与可追溯证据"
    desc: "汇总2023-04至2025-12正式OOS的相关性、四箱月度胜出频率、绩效、IC、换手、成本与图表；美国原值及原文冲突只作背景。"
    deps: [m3]
    elements: [R4, R7, R10, SA4]
---

# Equity Factor Timing: A Two-Stage Machine Learning Approach 复现开发计划

## 研报信息

- 标题：Equity Factor Timing: A Two-Stage Machine Learning Approach
- 来源机构：The Vanguard Group, Inc.
- 发布日期：2024-01-25（正文只给出2024，具体日采用spec登记的PDF元数据口径，见A14/AS13）
- 作者：Kevin J. DiCiurcio、Boyu Wu、Fei Xu、Scott Rodemer、Qian Wang
- 原文市场：美股
- 本计划适用市场：中国A股；`reproduction_mode=experimental`，按用户约束只复现大小盘与成长/价值2×2风格箱，不复现原文宏观、风险状态、ML择时或商业周期分支

## 一、核心策略与创新点

### 1.1 研究背景与核心思想

本计划的验证对象不是原研报两阶段机器学习模型，而是经用户明确授权的中国全A市场迁移实验。主线只保留两个可解释轴：市值大小与成长/价值。所有分类均由信号日可得的A股个股数据自底向上计算，固定形成大盘价值（BV）、大盘成长（BG）、小盘价值（SV）、小盘成长（SG）四个组合，以及可解释的SMB、HML与成长减价值（GML）序列。

美国原文的风险状态、宏观驱动、六因子ML胜出概率、商业周期权重和数值结果不作为中国实验的拟合目标。D15-D29仍保持不可恢复，A1仍保持blocked；该支线不进入本计划实现范围。

原文冲突不由本计划改写：A6同时保留市场风险状态与shadow rate目标表述，原ML主线继续out_of_scope；A23同时保留p5 Refinitiv表述与Exhibit通用来源行“Source: FRED, Factset”，该通用行不能分配到具体变量，实际实现只认data_catalog本地A股源；A24同时保留daily return与monthly performance标签表述，本实验只统计月度四箱收益且不构造原ML标签；A25同时保留Mar-23正文终点与May-23图轴终点，本实验仍按用户指定的2023-03冻结点前推。对应裁决与假设见A6/AS5、A23/AS22、A24/AS23、A25/AS24。

### 1.2 动态全A股票池与PIT口径

每个自然月最后一个交易日为信号日T。候选池来自`ashare_stock.parquet`所代表的沪深北A股证券主表，不使用CSI 800或任何指数历史成分；只保留在T有有效前复权行情、成交与正总市值的股票。上市时长以交易日历计算，要求自`list_date`起满120个交易日。到T已退市或T无有效行情/成交者剔除；若`list_state`不是带日期的历史字段，不使用2025-12的最终状态回溯删除早期样本，而以T日有效记录约束，避免存活偏差。

状态过滤规则冻结如下：T处于ST实施区间的股票剔除；T停牌或已触及涨/跌停的股票不进入新一期信号池。T+1执行时再次检查可交易性：停牌不得买卖，涨停不得买入，跌停不得卖出；旧仓无法卖出时继续持有，新仓无法买入时对应资金留现金，不把交易虚构为成交。

估值字段直接使用T日记录。财务字段必须先筛`info_publ_date <= T`，再为每只股票选择当时已披露的最新报告；`end_date`只用于匹配同一财政期的上年同期，不得直接作为可得日期。冻结日2023-03-31之后不得利用正式OOS数据修改字段、方向、分组、成本或过滤参数。

### 1.3 因子定义与公式

#### 1.3.1 Size轴

以T日总市值`market_value`为唯一size轴输入。设当月合格股集合为\(U_T\)，总市值为\(MV_{i,T}\)，横截面中位数为\(\widetilde{MV}_T\)：

\[
SizeGroup_{i,T}=\begin{cases}
Small,&MV_{i,T}<\widetilde{MV}_T\\
Big,&MV_{i,T}\geq\widetilde{MV}_T
\end{cases}
\]

若中位数处有并列，则按`(market_value, stock_code)`稳定排序后切成数量尽可能相等的两半，保证每只股票只进入一个size组。连续诊断信号定义为\(S_i=-rank(log(MV_i))\)，高值代表小盘。

#### 1.3.2 Value子分数

只用T日可得估值，不引入动量、波动率、质量、宏观或模型输出。对正且有限的估值分母构造\(B/P=1/PB\)、\(E/P=1/PE\)、\(S/P=1/PS\)，并直接使用股息率\(D/P=dv\)。每个指标在\(U_T\)内1%/99%缩尾后转为[0,1]横截面百分位秩，方向均设为“越高越价值”：

\[
V_{i,T}=mean\{PctRank(B/P),PctRank(E/P),PctRank(S/P),PctRank(D/P)\}
\]

至少两个有效估值分量才计算\(V\)。复合价值分数比单一P/B更能降低个别会计比率失真，同时完全由可复核的日频估值字段构成。

#### 1.3.3 Growth子分数

对T时点已披露的最新财务期与上年同财政期，分别用`total_operating_revenue`和`net_profit`构造有界、能处理符号变化的同比对称增长：

\[
g(x_t,x_{t-1y})=\frac{2(x_t-x_{t-1y})}{|x_t|+|x_{t-1y}|+\epsilon}
\]

两个增长指标分别在\(U_T\)内1%/99%缩尾并转百分位秩：

\[
G_{i,T}=mean\{PctRank(g(Revenue)),PctRank(g(NetProfit))\}
\]

至少一个有效增长分量才计算\(G\)。该定义用披露日控制可得性，避免将报告期末尚未公开的财务数据提前使用；它也避免把高P/B直接等同于高成长。

#### 1.3.4 Growth/Value轴与2×2分组

综合风格分数为：

\[
Style_{i,T}=G_{i,T}-V_{i,T}
\]

高成长且昂贵的股票得分较高，低成长且便宜的股票得分较低。为避免size分布机械影响风格轴，在Big与Small组内分别按`(Style, stock_code)`稳定排序，以各组中位数二分：上半为Growth、下半为Value。由此得到BV、BG、SV、SG四个互斥组合。该条件分组可保证每个size组内部的成长/价值可比，不做行业或市值中性化，因为市值本身就是本研究的显式分组轴。

### 1.4 组合收益与因子序列

四箱在T按流通市值`negotiable_market_value`加权，缺失或非正时退回总市值；权重在箱内归一化。流通市值加权比等权更接近可交易资本分布，也降低极小市值股票对中国全A结果的支配。另构造同一合格池的流通市值加权全A基准。

以扣除交易成本后的四箱收益定义：

\[
SMB_t=\frac{SV_t+SG_t}{2}-\frac{BV_t+BG_t}{2}
\]

\[
HML_t=\frac{SV_t+BV_t}{2}-\frac{SG_t+BG_t}{2},\qquad GML_t=-HML_t
\]

同时保留四箱1/N等权聚合收益作为结构基准，但不把原研报六因子1/N数值当作中国市场验证目标。

月度胜出频率只作为解释性输出：对每个完整持有月的BV、BG、SV、SG扣费后收益进行比较，最高者记为该月胜出风格箱。该统计不生成F9所述原六因子日频或月频ML二元标签，也不进入任何模型训练。

### 1.5 类型模板要求的截面诊断

对连续size信号\(S\)和连续`Style`分别计算下一持有月收益的Pearson IC、RankIC、ICIR、月度序列、分布与衰减；另按五分位检查连续信号的收益单调性。IC仅用于解释两条风格轴，不新增动量、低波、质量、宏观或ML因子。

### 1.6 创新点

- 将原文不可得的美股成分、因子收益与基准，逐条迁移为本地可复核的中国全A底层数据，而不是拟造美国数据。
- 用总市值中位数与PIT成长减价值复合分数形成稳定2×2条件分组，风格含义比“高P/B即成长”更明确。
- 在正式OOS中显式处理T+1执行、停牌、涨跌停、非成交仓位、成本与现金残留，使结果可以落到中国交易制度。

## 二、回测参数

| 参数 | 冻结口径 |
| --- | --- |
| 复现模式 | experimental；中国全A风格箱，不做原文美国ML择时 |
| 方法冻结截止 | 2023-03-31；含当日及此前可得信息 |
| 正式OOS | 2023-04-01至2025-12-31 |
| 频率 | 月频调仓；日频记账 |
| 信号/执行 | 月末最后交易日T计算，下一交易日T+1按VWAP执行；T+1无有效VWAP则视为不可成交，不用未来价格替代 |
| 股票池 | 沪深北动态全A；不用CSI 800；上市满120个交易日；有效行情、成交和正市值 |
| 状态过滤 | T剔除ST、停牌、涨跌停；T+1按方向实施停牌/涨跌停成交约束 |
| Size分组 | T日总市值横截面中位数，稳定排序二分Big/Small |
| Style分组 | `Style=Growth-Value`；在Big/Small内部各自中位数稳定排序二分Growth/Value |
| 组合权重 | 四箱与全A基准均按流通市值加权，流通市值无效时回退总市值 |
| 复权/收益 | `ashare_stock_price_forward.parquet`；执行价和持有期收益保持同一复权口径 |
| 佣金 | 买卖双边各3bp；单位净值回测不模拟单笔最低5元 |
| 滑点 | 买卖双边各5bp |
| 印花税 | 仅卖出收取：2023-08-28前10bp，自2023-08-28起5bp |
| 不可成交 | 旧仓卖不出则延续；新仓买不入则资金留现金；不得强制成交或用后续可交易日回填T+1价格 |
| 现金收益 | 0；不引入额外无风险利率数据 |
| 基准 | 同一动态全A合格池的流通市值加权组合 |
| 预处理 | 单指标月度横截面1%/99%缩尾、百分位秩；不做行业/市值中性化 |
| 缺失规则 | Value至少2/4有效、Growth至少1/2有效；否则当月不参与style分组 |
| 验证主线 | 四箱、SMB/HML/GML、全A基准、IC/RankIC、换手、成本、可交易覆盖率；美国原值只作背景 |
| 原文来源冲突 | p5 Refinitiv与Exhibit通用“Source: FRED, Factset”均保留为reference_only，不作逐变量归属；实际实现只使用data_catalog本地A股源，见A23/AS22 |
| 胜出频率 | 按完整持有月比较BV/BG/SV/SG扣费后月收益；不实现原ML标签，见A24/AS23 |
| 时间终点冲突 | 原Mar-23正文终点与May-23图轴终点均保留为背景；实验冻结2023-03-31、OOS至2025-12-31，见A25/AS24 |

## 三、研报核心结果（验证基准）

本实验不以美国原值为数值达标基准。下列R要素仅复用可解释的输出结构，具体美国数值、原文与页码仍以`spec.md`为唯一来源；其余R1-R3、R5-R6、R8-R9均标记`reference_only`。

| R 要素ID | 一句话摘要 | 关联 milestone |
| --- | --- | --- |
| R4 | 将原六因子相关矩阵结构迁移为四箱及SMB/HML/GML相关性证据；不比较美国数值 | m4 |
| R7 | 将原胜出频率结构迁移为四个中国风格箱扣费后月度胜出频率；不实现F9原ML标签、不比较美国数值，见A24/AS23 | m4 |
| R10 | 将原组合表现表结构迁移为全A、四箱、四箱1/N、SMB/HML/GML的OOS绩效表；不比较美国数值 | m4 |

## 四、复现计划

### m1：动态全A与PIT数据底座

- 实现内容：加载A股证券主表、前复权行情、成交/市值、估值、利润表、ST、停牌、涨跌停和交易日历；生成每月T与T+1；完成上市120交易日、退市/有效记录、状态与交易约束过滤。
- PIT处理：所有财务记录先按`info_publ_date <= T`过滤，再匹配最新财政期及上年同期；禁止以`end_date`直接对齐信号日。
- 产出：月末合格池、估值/财务快照、T/T+1可交易标记、数据覆盖与排除原因表，以及声明实际文件名/字段/区间的本地来源清单。
- 验证点：抽查信号日后披露数据未进入截面；同月股票唯一；交易日与T+1无错位；不存在用最终`list_state`回溯制造存活偏差；实现未调用Refinitiv、FRED或Factset等原美股来源。

### m2：2×2大小盘与成长价值风格构造

- 实现内容：按冻结公式计算Size、Value、Growth、Style；稳定中位数切分BV/BG/SV/SG；保留连续Size与Style用于IC诊断。
- 依赖数据：m1的PIT月末面板。
- 产出：因子长表、四箱成员与权重表、每月组内统计、缺失率和边界股票审计样本。
- 验证点：每只股票每月最多一个箱；四箱并集等于有效风格样本；Big/Small及各自Growth/Value数量差不超过1（缺失剔除前提下）；方向测试满足“更小市值的Size信号更高、越成长且越不便宜的Style更高”。

### m3：组合、成本与中国交易约束回测

- 实现内容：T信号、T+1 VWAP执行，日频记账；处理方向性涨跌停、停牌、旧仓延续、现金残留、佣金、滑点和分段印花税；生成四箱、全A、四箱1/N、SMB、HML、GML。
- 依赖数据：m2成员与目标权重、m1执行状态。
- 产出：逐日/逐月净收益与净值、目标/实际权重、交易流水、换手、成本拆分、不可成交记录。
- 验证点：信号至少滞后一个交易日；成本前后收益可勾稽；HML与GML逐期互为相反数；SMB/HML由四箱收益逐期重算一致；不可成交资产没有虚构成交。

### m4：OOS报告与可追溯证据

- 实现内容：只汇总2023-04至2025-12正式OOS；输出四箱/因子绩效、相关性、按四箱扣费后月收益计算的胜出频率、IC/RankIC/ICIR、分组单调性、衰减、换手、成本、覆盖率与交易约束影响。
- 必需Excel：`backtest_summary.xlsx`（美国原值列明确标“背景/不可比”）、`factor_analysis.xlsx`、`style_box_returns.xlsx`、`portfolio_holdings.xlsx`、`trading_audit.xlsx`；均按多sheet、首行加粗、冻结首行、自动列宽并将图表数据放同sheet。
- 必需PNG（300 DPI）：`ic_series.png`、`ic_distribution.png`、`group_cumulative_returns.png`、`group_returns_bar.png`、`net_value_comparison.png`；追加`style_box_heatmap.png`、`factor_cumulative_returns.png`、`turnover_cost.png`。
- 验证点：结果区间无冻结日后的调参；指标可由逐期数据独立重算；胜出频率可由四箱月收益重算且没有F9标签表；美国数值及A6/A23-A25冲突均未参与通过/失败判定；所有图表与Excel底表一致。

## 五、难度判定

- 方法复杂度基准：`medium`。虽然不训练模型，但本计划不是单一标准因子公式；它包含PIT复合成长/价值、条件2×2分组、四组合权重联动和SMB/HML/GML逐期合成。
- 数据可得性修正：触发上调。主线需跨证券主表、前复权行情、日市值、日估值、披露日财务、状态事件和交易日历做复杂时点拼接，并维护T/T+1两套可交易状态，因此由medium上调为`hard`。
- 模块/因子数修正：实现模块超过8个（股票池、PIT财务、估值、size、style、四箱、执行约束、成本、因子合成、证据输出），且基准已为medium；该项同样指向hard，但难度封顶hard。
- 模型训练修正：不触发；用户明确排除宏观和ML。
- 结论：`difficulty: hard`，配置4个串行无环milestone，满足hard至少3个的下限。

## 六、改进建议与潜在问题（AI视角）

- 本结果是市场迁移实验，不是原研报两阶段ML的数值复现；任何与美国R值的差异都不能归因为实现错误。
- 原文来源、标签频率、样本终点和shadow-rate冲突必须在证据清单并列保留；实现选择只约束r004，不得在最终报告中宣称已判定原文哪一侧正确。
- `ashare_stock.parquet`的`list_state`未在目录中声明为历史时点字段，必须以逐日行情/成交存在性约束，不能用期末状态回溯筛选。
- 估值字段对亏损公司可能缺失，Value的“至少2/4有效”规则会改变行业构成；报告必须披露每月覆盖率和排除比例。
- 流通市值加权、120交易日上市门槛与成本参数都是可审计假设；若结果由极少数大权重股驱动，应在verify后回看而不是临时改参。
- 不建议在正式OOS内试验新的成长字段、分位点、行业中性化或权重上限；如需改动，应登记新假设并从受影响milestone重跑。
