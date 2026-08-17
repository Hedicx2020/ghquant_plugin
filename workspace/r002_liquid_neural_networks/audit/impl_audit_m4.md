# m4 实现忠实性审计

## 审计范围

- mode：code
- milestone：m4
- 案例：r002_liquid_neural_networks
- 本次仅审 `coverage_matrix.md` 中 milestone=m4 且 status=done 的 F8、B6、B7、B8、B9、B10、B11、B12，共8项；不读取 coder 完成汇报，不提前裁决 m5 的 R/SA 要素。
- 证据范围：`spec.md`、`coverage_matrix.md`、`assumptions.md`、本案例 `src/`、`common/ml_portfolio.py` 及其实际调用的 `common/backtest.py`、`common/utils.py`。
- 空壳检查：8个 done 要素所列实现函数均真实存在并有可执行函数体；相关 m4 调用链未发现 `pass`、TODO、FIXME、`NotImplemented` 或 `raise NotImplementedError` 空壳。

## 五维度总体核对

| 维度 | 独立核对内容 | 结论 |
| --- | --- | --- |
| 公式一致 | 独立重算降序十分档、20偏移事件索引、T/T+1/T+21端点、逐笔费用、Top与Top-Bottom、逐路径年化/夏普/年度统计及路径聚合。 | 分组、端点、成交账本、Top/Top-Bottom及收益指标主公式正确；RankIC缺少AS8规定的逐路径与20路径汇总，逐日路径平均净值公式与AS16不一致，见CA-A01、CA-A03。 |
| 参数一致 | 核对10档、20日周期、offset=0…19、entry=1、exit=21、卖出费0.003、初始资金1、年化252、rf=0及Pearson相关配置。 | F8/B6-B12所需参数均由集中配置完整透传，`MLPortfolioSettings.validate`强制20偏移恰好各一次及持有期=21-1=20。通过。 |
| 实现位置真实 | 逐一打开矩阵列出的预测面板、分组、事件、执行、组合、指标与单调性函数，并沿实际调用反查公共指标实现。 | 所列位置全部真实且可执行；无空壳或不存在位置。通过。 |
| 代码反查 | 从 `strategy.py` m4公开函数及 `common/ml_portfolio.py` 公共入口反向核对F8/B6-B12矩阵映射。 | 公共模块4个公开函数均有回映；策略层公开总入口 `run_m4_backtest` 未回映任何要素，见CA-A04。 |
| 简化声明 | 对照AS3-AS8、AS16检查路径、不可成交、估值、目标权重、费用和聚合口径。 | 大部分结果敏感口径已登记；但现金不足时按全部可成交买单同比例缩量的规则未登记，且与AS16写明的单股目标市值口径不完全一致，见CA-A02。 |

## done 要素逐条核对

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| F8 | `assemble_m4_prediction_panel`先保证五模型证券/日期/标签逐行一致；`prepare_factor_panel`只保留有限预测与标签；排序仅使用T日预测。 | 五模型集合被双重校验；预测方向为降序。 | 矩阵所列3处均真实存在。 | 预测组装、校验、排序公共入口均已回映。 | 同值按stock_code升序裁决已在AS16登记。 | pass |
| B6 | `floor(rank_zero_based×10/count)+1`使最高预测进入group1、最低进入group10，组间数量最多差1。 | `n_groups=10`，且最小截面不得小于10。 | `assign_descending_quantile_groups`真实可执行。 | 公开分组函数直接回映B6。 | 等数量与同值裁决已登记。 | pass |
| B7 | 20个路径分别计算全期与年度指标后，`_build_metrics`按模型/组合/期间对路径算术平均且以`nunique(path_offset)`计数，没有重复计权；但辅助路径净值聚合错误，见CA-A03。 | `path_offsets=tuple(range(20))`，校验拒绝缺失、重复或乱序偏移。 | 两个矩阵位置真实。 | B7主入口和辅助聚合函数均已回映。 | 主指标口径与AS3/AS16一致；辅助净值实现偏离已登记口径。 | fail（CA-A03） |
| B8 | offset=k路径以可交易日历第k日为首个信号，之后每20日取一次；相邻执行日也相差20日。 | 周期20；20个offset覆盖一个完整周期且各一次。 | `_build_path_events`与总入口真实。 | 两处均已回映。 | 未发现新增结果敏感简化。 | pass |
| B9 | 信号日T只从分组表读取目标；执行日索引为T+1；下次调仓执行日及末次退出为T+21，持有端点差20个交易日。T+1可成交面板只在执行器读取，不回流预测。 | `entry_offset=1`、`exit_offset=21`且差值强制等于20；成交价为执行日日VWAP。 | 市场面板、事件和模拟函数均真实。 | 3处均已回映。 | 不可成交新目标留现金、旧仓保留股数、缺价只以最近历史价估值且不成交，均已登记并与实现一致。 | pass |
| B10 | 卖单费用=`实际卖出股数绝对值×执行价×0.003`；blocked卖单费用0；买单费用恒为0；净收益由权益变化计算，毛收益用当日实际费用还原。 | 费率0.003，仅卖出收取。 | 执行与组合构造函数真实。 | 两处均已回映。 | 费用本身一致；费用或被阻塞旧仓导致现金不足时的买单同比例缩量未登记，见CA-A02。 | fail（CA-A02） |
| B11 | Top为group1计费后长组合；Top-Bottom=`group1毛收益-group10毛收益-group1实际卖费-group10实际卖费`，两腿各用独立1.0资金，不把底组卖费反向加回。 | 第一档/第十档和双腿费用参数一致。 | 组合构造与总入口真实。 | 公共入口已回映；策略总入口缺口见CA-A04。 | AS5/AS16已登记非自融资的一单位长腿减一单位底组腿；买单缩放口径仍缺失，见CA-A02。 | fail（CA-A02、CA-A04） |
| B12 | 逐日截面RankIC确为Spearman；年化收益为日收益几何年化，夏普为日均超额收益/样本标准差×sqrt(252)，年度表按自然年先逐路径计算再平均。RankIC却未按路径取时序均值再对20路径平均，见CA-A01。 | 年化252、rf=0；相关与收益字段均使用集中配置。 | 3个矩阵位置及实际调用的公共指标函数均真实。 | B12列出的公共函数有回映；总入口仍有CA-A04。 | AS8明确规定RankIC路径口径，当前实现不是已登记的替代口径。 | fail（CA-A01、CA-A04） |

## 重点独立核验

### 1. 预测降序与十分档

- `common/ml_portfolio.py:170-187`按模型/日期、预测降序、股票代码升序稳定排序，再以 `floor(rank×10/N)+1`分组。
- 以11只股票、预测值11至1做内存重算：group1含11、10两个最高值，group2至group10各1只，group10为最低值1；最大组2只、最小组1只，差值为1。
- `strategy.py:743-755`还要求五模型的股票、日期及真实标签完全相同，避免模型之间因样本键不同造成伪比较。F8/B6通过。

### 2. 20偏移路径与T/T+1/T+21端点

- `MLPortfolioSettings.validate`在`common/ml_portfolio.py:59-66`强制offset严格等于 `(0,…,19)`、entry=1小于exit=21，且 `21-1=20`。
- `_build_path_events`在`287-305`对offset=k取 `calendar[k::20]`，执行日取每个信号日后第1个交易日；在`315-325`将末次退出放到最后信号日后第21个交易日。
- 对连续70个交易日重算：offset0的信号索引为0/20/40、买入索引为1/21/41、末次退出为61；offset19的信号索引为19/39、买入索引为20/40、末次退出为60。每笔从买入到下一调仓卖出或最终卖出均跨20个交易日。
- 若某个预定信号日没有有效目标，空目标调仓会在前一组合应到的T+21端点卖出，并非提前清仓；因此该行为本身未记issue。

### 3. 信号与执行信息隔离

- `strategy.py:708-757`的预测面板只含模型、股票、T日日期、预测和标签；`760-829`另行构造执行日VWAP/可成交面板，两者物理分离。
- `_build_path_events`只用T日分组确定目标，`_simulate_group_path`直到执行日才读取当日价格及tradable状态（`common/ml_portfolio.py:381-405,413-478`）。
- 未发现用T+1停牌/涨跌停状态回筛T日模型或排序的路径。B9的时点隔离通过。

### 4. 成交、不可成交与估值账本

- 卖单先于买单；实际卖出名义金额为 `-executed_shares×price`，费用为该金额×0.003（`common/ml_portfolio.py:407-463`）。买单`fee=0`（`465-524`）。
- 合成账本重算：初始权益1.0、A/B各目标0.5，A可买而B不可买时，A实际买0.5、B成交0、现金保留0.5；下次A缺价且不可卖时仍持有0.5股，并沿用最近价格1估值；最终A/C各卖0.5时，每腿费用0.0015，总费用0.003，末值0.997，净日收益-0.003而毛收益约0。
- 这验证了不可成交新目标不重分配、旧仓不虚假卖出、最近历史价只用于估值以及费用只来自实际卖出。相关实现与AS4/AS16一致。
- 但在正常全换仓中，旧仓卖出1.0后现金仅为0.997，而代码对目标买入1.0应用 `buy_scale=0.997`；该缩量规则未在AS16登记，见CA-A02。

### 5. Top、Top-Bottom与路径独立

- `run_multi_path_factor_backtest`在`common/ml_portfolio.py:821-846`按模型×offset×group逐一调用模拟器；每次调用都在`_simulate_group_path:370-373`新建空持仓、空历史价格、现金1.0，路径和分组之间不共享账户状态。
- Top直接取group1净收益。Top-Bottom先还原两腿毛收益，再扣两腿各自实际卖费（`642-676`），与AS16的一单位长腿减一单位底组腿定义一致。
- `_build_metrics`先以model/path/group或model/path/portfolio为键计算，之后只按model/portfolio/period聚合并以`nunique(path_offset)`计数（`686-756`）；主指标无重复路径计权。
- 辅助 `path_daily_aggregate`并非“当日活动路径NAV均值”：它先平均日收益再复利，见CA-A03。

### 6. RankIC、年化、夏普与年度统计

- `common/backtest.py:73-90`对有效截面调用Spearman相关，日度RankIC公式正确。
- `common/utils.py:194-211`使用 `prod(1+r)^(252/N)-1`几何年化；`173-191`使用日超额收益均值/样本标准差×sqrt(252)；`common/ml_portfolio.py:612-639`以逐路径日收益调用这些函数。
- `_build_metrics`先按自然年拆分每条路径，再产生年度累计收益、年化收益、夏普和最大回撤；最后对20路径同口径指标算术平均，收益风险统计公式成立。
- `calculate_prediction_diagnostics`仅返回 `[model, signal_date, rank_ic]`逐日表；返回对象也没有逐路径RankIC或20路径RankIC均值字段。该缺失不能由收益指标聚合器补足，详见CA-A01。

### 7. AS16简化登记完整性

- 已登记且实现一致：独立1.0资金、降序等数量分组、同值裁决、先卖后买、按完整目标数计算目标市值、不可成交新目标留现金、不可成交旧仓保留股数、缺价历史估值、单边卖费、双腿费用、路径先算后平均及活动路径计数。
- 未完整登记：`common/ml_portfolio.py:473-505`在现金不足时对所有可成交买单统一乘 `buy_scale`。现金不足既可能来自卖出费用，也可能来自无法卖出的旧仓；这一规则改变实际目标权重，且AS16写明的“每只目标股票市值=执行前权益/完整目标数”没有说明该后续同比例压缩。CA-A02据此成立。
- `path_daily_aggregate`的实现不是AS16已登记口径，而是直接与其冲突，单列CA-A03。

### 8. 公开函数回映与空壳

- `common/ml_portfolio.py`的4个公开函数 `prepare_factor_panel`、`assign_descending_quantile_groups`、`calculate_prediction_diagnostics`、`run_multi_path_factor_backtest`均至少回映F8/B6-B12之一。
- `strategy.py`的m4公开函数中，`assemble_m4_prediction_panel`已回映F8，`build_m4_market_panel`已回映B9；总入口`run_m4_backtest`未出现在任何矩阵实现位置，见CA-A04。
- 所有矩阵位置均有真实函数体；不存在空壳虚报。

## issue 清单

| 编号 | severity | 证据定位 | 一句依据 | 处置要求 |
| --- | --- | --- | --- | --- |
| CA-A01 | critical | `workspace/r002_liquid_neural_networks/assumptions.md:87-97`；`common/ml_portfolio.py:193-233,686-756,803-873` | B12已标done且AS8要求“每条offset路径的信号日RankIC先做时序均值、再对20路径算术平均”，当前只输出逐模型逐日Spearman值，既无path_offset也无任何RankIC时序/路径汇总，核心指标公式未完成。 | 按与调仓事件完全相同的20个offset给RankIC分配路径，先逐路径对信号日RankIC取时序均值，再对20路径等权平均，并输出可复算的逐路径与聚合表；不得用全日期简单均值替代路径等权。 |
| CA-A02 | critical | `workspace/r002_liquid_neural_networks/assumptions.md:183-193`；`common/ml_portfolio.py:395-405,465-505` | 代码在卖费或阻塞旧仓造成现金不足时，以 `buy_scale=cash/requested_cash` 对全部可成交买单同比例缩量；该结果敏感资金规则未在AS16登记，且实际买入市值会偏离AS16写明的“执行前权益/完整目标数”，属于core B10/B11的 `deviation_undeclared`。 | 要么在AS16明确登记现金约束、同比例缩量公式、触发条件及对目标权重/收益的影响并保持实现一致，要么按获批口径修改账本；修复后重算全换仓与阻塞旧仓两类样例。 |
| CA-A03 | major | `workspace/r002_liquid_neural_networks/assumptions.md:183-193`；`common/ml_portfolio.py:759-772` | AS16声明辅助曲线为“当日已启动路径NAV等权均值”，实现却先平均路径日收益再复利；例如第二日活动路径NAV为1.21和1.20时应为1.205，代码会由首日1.10乘平均收益1.15得到1.265。 | 直接按model/portfolio/date对活动路径的`nav`算术平均并保留active_path_count，或修改经授权的假设名称与用途；不得把复利后的平均收益曲线标成平均净值。 |
| CA-A04 | major | `workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:21,27-33`；`src/r002_liquid_neural_networks/strategy.py:860-889` | m4策略层公开总入口 `run_m4_backtest`负责五模型校验、预测对齐、市场面板构造及完整回测调用，但未直接回映F8/B6-B12任何要素，构成公开实现“私货”。 | 按真实覆盖关系把该公开入口回填至F8/B6-B12相应行，或改为明确私有辅助且继续由已映射公开入口封装；修复后定向复审代码反查。 |

## 审计结论

- 已逐条审计m4全部8个done要素：F8、B6-B12；完成公式一致、参数一致、实现位置真实、代码反查、简化声明五维核对。
- 降序十分档、20偏移索引、T/T+1/T+21分离、20日持有端点、实际卖费、不可成交与历史估值、Top/Top-Bottom主公式、逐路径收益风险指标及年度统计均通过独立重算。
- 当前open issue：4项（critical 2 / major 2 / minor 0）。CA-A01使B12核心RankIC路径口径未完成；CA-A02为core资金执行规则未登记，因此当前门禁不能通过。

verdict: fail

## 第1次定向复核

- 复核模式：code。
- 复核边界：仅复核CA-A01至CA-A04，并对F8/B6-B12原通过的降序分组、T/T+1/T+21、20日持有、单边卖费、不可成交估值、Top/Top-Bottom及路径独立性做回归检查。
- 上文保留初审问题、严重度与当时结论；以下定向复核状态取代初审最终门禁判定。

### 修复复核表

| 编号 | 初审级别 | 修复后证据 | 独立复算 | 复核判定 |
| --- | --- | --- | --- | --- |
| CA-A01 | critical | `common/ml_portfolio.py:87-89,239-347`新增逐信号路径表、逐路径摘要和20路径聚合表；`295-307`按model/path_offset计算RankIC时序均值并保留信号数量与日期端点；`309-346`断言0至19路径齐全后对20个路径均值直接 `np.mean`；`959-961,1003-1010`将三张表接入实际总流程和结构化结果。`coverage_matrix.md:33`也已直接回映 `build_rank_ic_path_aggregates`。 | 以21个连续交易日构造不等长路径：offset0有2个RankIC（0、1），其时序均值0.5；offset1至19各1个0，20路径等权结果为0.025。代码返回path_count=20、signal_count=21、min/max count=1/2和最终0.025；全日期简单均值为0.047619，证明未退化为观察数加权。 | **resolved / pass**：路径分配与调仓同样以模型有效区间首日为offset0并按交易日位置mod20；先逐路径时序均值、再20路径等权，三层表可逐行复算。 |
| CA-A02 | critical | `assumptions.md:183-193`现明确登记 `requested_cash`、`buy_scale=min(1,cash/requested_cash)`、requested_cash=0分支、卖费/阻塞旧仓两类触发、实际新增市值公式、现金与实际权重影响及替代口径风险；`common/ml_portfolio.py:587-647`按同一公式执行，并在每条买单留存 `cash_before_buys`、`requested_cash`、`buy_scale`、requested/executed shares及partial原因。 | 全换仓合成账本中，A卖出名义金额1.0、费用0.003、买前现金0.997；B初始请求金额1.0，代码返回buy_scale=0.997、实际买入0.997、买费0、状态partial。三个缩量字段和请求/成交差异均进入交易明细，可复算公式与影响。 | **resolved / pass**：原未登记的core资金执行规则已完整入AS16并与代码、逐笔证据一致。 |
| CA-A03 | major | `common/ml_portfolio.py:884-914`现直接按model/portfolio/date对活动路径的 `nav` 求算术平均，并保留 `active_path_count`；平均路径日收益另存 `mean_active_path_daily_return`，不再用于重建nav。AS16在`assumptions.md:185-190`同步明确“直接平均、不得用平均收益复利替代”。 | 复用初审反例：首日path0 NAV=1.10；第二日path0 NAV=1.21、path1 NAV=1.20。代码第二日返回nav=(1.21+1.20)/2=**1.205**、active_path_count=2，而不是旧值1.265；mean_active_path_daily_return=0.15被单独披露。 | **resolved / pass**：辅助曲线已成为名实一致的当日活动路径净值等权均值。 |
| CA-A04 | major | `coverage_matrix.md:21,27-33`的F8及B6-B12每一行现均直接列入 `src/r002_liquid_neural_networks/strategy.py:run_m4_backtest`；`strategy.py:860-889`真实执行五模型校验、预测对齐、市场面板构造、交易日历传入及公共回测总调用。 | 逐行反查8个done要素，`run_m4_backtest`出现8次且其调用链实际覆盖预测排序、分组、路径、执行、费用、组合和指标，不是为补矩阵而填写的无关位置。新增公共函数 `build_rank_ic_path_aggregates`也已回映B12。 | **resolved / pass**：策略层公开总入口及本次新增公共RankIC入口均完成真实回映，无公开实现私货。 |

### 原通过项回归检查

| 要素/风险点 | 当前证据与独立复算 | 结论 |
| --- | --- | --- |
| F8/B6降序十分档 | `common/ml_portfolio.py:158-193`仍按预测降序、stock_code升序裁决及 `floor(rank×10/N)+1`分组；修复未触及排序公式。 | pass |
| B8/B9路径时点 | `common/ml_portfolio.py:388-442`仍以 `eligible_calendar[offset::20]`取信号、T+1执行、末次T+21退出。连续日历复算offset0为信号0/20/40、执行1/21/41、退出61；offset19为信号19/39、执行20/40、退出60，相邻执行及末次持有均20日。 | pass |
| B10费用与不可成交 | `common/ml_portfolio.py:521-577`仍只对实际卖出名义金额乘0.003；`598-648`买单费仍为0。旧仓不可成交分支保持0成交、0费用，最近有效价估值链`496-519,651-725`未改变。 | pass |
| B11 Top/Top-Bottom | `common/ml_portfolio.py:767-808`仍以group1净收益构造Top，并按“两腿毛收益差减两腿实际卖费”构造Top-Bottom；修复未改变资金或费用符号。 | pass |
| 路径独立与收益指标 | `_simulate_group_path:484-490`每次调用仍独立初始化持仓、历史价和资金1.0；`run_multi_path_factor_backtest:966-985`仍逐model/offset/group单独模拟；`_build_metrics:811-881`仍先逐路径计算后按路径算术平均，无重复计权。 | pass |
| 空壳与公开函数 | 当前相关函数均有完整可执行体；未发现新增 `pass`、TODO、FIXME、`NotImplemented` 或 `raise NotImplementedError`。 | pass |

## 第1次定向复核结论

- CA-A01、CA-A02、CA-A03、CA-A04均已修复并关闭。
- RankIC三层证据表、现金缩量逐笔证据和活动路径平均净值均通过不等长路径/成交账本合成复算；公开入口完成全矩阵回映。
- F8/B6-B12原通过的排序、20偏移、T/T+1/T+21、20日持有、单边卖费、不可成交估值、Top/Top-Bottom、路径独立及收益风险统计未见回归。
- 当前open issue：0项（critical 0 / major 0 / minor 0）。

verdict: pass
