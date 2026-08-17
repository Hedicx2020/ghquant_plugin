# m1 实现忠实性审计

## 审计范围

- mode：code
- milestone：m1
- 案例：r002_liquid_neural_networks
- 矩阵中实际 `done` 要素：D1、D2、D3、D4、D5、B1、B2、B3、B4、B5，共10项。
- 审读边界：仅对照 `spec.md`、`coverage_matrix.md`、`assumptions.md`、本案例 `src/`、`common/ml_pipeline.py` 及实际调用的 `common/data_loader.py`。静态调用链未引用 `common/utils.py`，故没有可继续反查的 utils 调用。
- 空壳检查：10项实现位置指向的 `load_m1_inputs` 与 `prepare_m1_dataset` 均存在可执行函数体，调用的公共函数也均存在；未发现 `pass`、TODO 或 `NotImplemented` 空壳。

## 五维度总体核对

| 维度 | 独立核对内容 | 结论 |
| --- | --- | --- |
| 公式一致 | 重算六通道公式、前复权VWAP推导、T+1/T+21简单收益、上市/ST资格与分段布尔条件。 | D1、D2-D4、B1-B5公式一致；D5标签公式一致，但VWAP量纲筛选含未登记数值阈值，见CA-A01。 |
| 参数一致 | 核对60日、六通道、0.5%/99.5%、上市满1年、T+1/T+21、三段起止日及VWAP校验参数。 | 报告/AS9/AS10参数均落实；VWAP校验的0.1、10.0、95%未登记于AS14，D5参数维度不通过。 |
| 实现位置真实 | 逐条打开矩阵所列函数，并沿调用链反查至公共实现。 | 10项done行位置均真实且非空壳。 |
| 代码反查 | 从 `strategy.py` 的全部公开函数反向核对矩阵要素。 | `load_m1_inputs`、`prepare_m1_dataset`可回映；`build_m1_audit_tables`没有任何矩阵行映射，见CA-A02。 |
| 简化声明 | 对照AS4、AS9、AS10、AS13、AS14检查代码主动近似及其影响披露。 | 历史上市状态近似已如实登记；VWAP推导已登记但阈值未登记，且AS7与AS14仍保留冲突的数据源陈述，见CA-A01、CA-A03。 |

## done 要素逐条核对

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | `common/ml_pipeline.py:140-170`按 `log(OHLC/prev_close)`、`log1p(volume)`、`log1p(turn_value)`构造六通道，与AS10一致。 | `config.py:34-49`固定六通道、60日、0.5%/99.5%；`ml_pipeline.py:398-442`要求连续60个全市场交易日。 | `strategy.py:207-252`真实存在并调用公共管线。 | `prepare_m1_dataset → prepare_point_in_time_ml_data → build_features/build_window_index`闭环成立。 | `assumptions.md:111-121`显著声明为用户授权降级，不冒充原研报私有输入。 | pass |
| D2 | `ml_pipeline.py:299-359`从逐日行情键与证券主表构造时点股票池，当前`list_state`不反填历史。 | 上市起点优先`list_date`，缺失回退首个观察日，参数与AS13一致。 | 矩阵指向的 `strategy.py:207-252`真实存在。 | 调用链合并 `stock_master` 并将 `list_state/effective_list_date`带入样本。 | `assumptions.md:147-157`如实披露当前快照、历史退市/摘牌缺口及潜在样本遗漏。 | pass |
| D3 | `ml_pipeline.py:336-358`按ST区间过滤信号日；`362-395`只把T+1停牌/涨跌停附为执行元数据。 | 上市满1年由 `config.py:88-93` 与 `DateOffset(years=1)`落实；T+1可交易解释与AS4一致。 | 矩阵指向的 `strategy.py:207-252`真实存在；状态数据由 `strategy.py:137-142`加载。 | ST、停牌、涨跌停、上市年限均可沿调用链定位，无虚构数据源。 | AS4与AS13已声明信号日动态池、执行日约束及历史上市状态近似。 | pass |
| D4 | 无独立公式；`strategy.py:105-140`读取完整行情、交易、状态和交易日历。 | 主数据从训练起点前1年读至2024-12-31，包含规格要求的2008-2024；额外1年是AS13登记的状态/上市缓冲。 | `strategy.py:83-187`的 `load_m1_inputs`真实存在。 | 八个必需文件先做存在性检查，再分别读取、日期过滤和一对一合并。 | 额外缓冲与用途在 `strategy.py:105-113`、AS13中均有说明。 | pass |
| D5 | `ml_pipeline.py:268-282`按全市场交易日精确核验T+1/T+21，计算 `exit_vwap/entry_vwap-1`；公式与AS9一致。 | `config.py:65-70`的1/21正确，但同处0.1、10.0、0.95三个VWAP校验阈值未写入AS14。 | `strategy.py:207-252`真实存在；VWAP先由 `83-187`推导。 | `load_m1_inputs → derive_forward_adjusted_vwap → build_forward_return_labels`完整可定位。 | AS9、AS14登记了降级公式与数据源近似，但校验阈值未登记；AS7的数据源陈述又与AS14冲突。 | fail（CA-A01、CA-A03） |
| B1 | `ml_pipeline.py:317-359`以每日实际行情键为动态全市场候选，不使用期末固定池。 | 无额外市场缩窄参数；上市满1年和ST约束来自已登记AS4/AS13。 | `strategy.py:207-252`真实存在。 | 每个信号日均重新得到 `eligible_signal`，不是一次性期末名单。 | 历史摘牌无法完整恢复的降级已在AS13披露。 | pass |
| B2 | 信号日剔除未满1年和ST；T+1停牌/涨跌停仅标记执行不可交易，符合AS4裁决。 | `minimum_listing_years=1`与规格一致；ST区间按实施日起、移除日前生效。 | `strategy.py:207-252`真实存在。 | `build_point_in_time_universe`与`attach_entry_tradability`均被主流程实际调用。 | 不完整历史上市/摘牌状态已由AS13显著披露，未假装完整恢复。 | pass |
| B3 | `strategy.py:190-204`生成训练段，`ml_pipeline.py:445-469`要求窗口、信号、买卖端点都在同一段。 | `config.py:77-80`为2008-01-01至2016-12-31，与规格一致。 | `strategy.py:207-252`真实存在。 | `assign_non_overlapping_splits`及 `strategy.py:245-251`双重检查边界；60日窗口与21日标签使边缘候选自然剔除，并计入`boundary_excluded`。 | 未跨段使用数据；边缘剔除是已配置窗口/标签端点的直接结果，不改写段起止参数。 | pass |
| B4 | 与B3相同，验证窗口、信号、T+1、T+21均不得越界。 | `config.py:80-82`为2017-02-01至2019-11-30，训练段结束后保留2017-01空档。 | `strategy.py:207-252`真实存在。 | 代码拒绝重叠分段，并逐列断言验证样本均落在验证段。 | 严格边界避免训练统计或标签进入验证段，无未声明市场迁移。 | pass |
| B5 | 与B3相同，回测窗口、信号和标签端点均在回测段。 | `config.py:83-85`为2020-01-01至2024-12-31，验证结束后保留2019-12空档。 | `strategy.py:207-252`真实存在。 | 代码逐样本检查 `window_start_date/date/entry_date/exit_date`，并排除末端缺失标签。 | 不跨越报告回测区间；无替代市场或参数改写。 | pass |

## 重点独立核验

### 1. 训练期拟合

- `ml_pipeline.py:601-619`先完成分段、股票池与标签有效性筛选，再只取 `split == train` 的样本窗口。
- `_rows_used_by_windows`只标记这些训练窗口实际覆盖的面板行；`fit_feature_preprocessor`在该掩码上计算0.5%/99.5%分位点、均值和标准差（`ml_pipeline.py:472-509`）。
- 验证与回测仅调用 `transform_features` 复用训练参数，不重新拟合（`ml_pipeline.py:512-526,620-628`）。
- `strategy.py:237-240`再次断言拟合日期不越出训练段。判定：通过。

### 2. T日信息边界

- 窗口结束行就是信号日T，起点为同一证券向前59个全市场交易日，未读取T之后特征（`ml_pipeline.py:398-442`）。
- 信号日股票池只使用T日行情存在性、上市日期、上市年限与T日ST状态（`ml_pipeline.py:299-359`）。
- T+1停牌/涨跌停在样本筛选之后才附加，并只生成 `entry_*` 元数据（`ml_pipeline.py:603-610,362-395`）；六个特征名均不含执行状态，`strategy.py:241-244`还有反向断言。判定：通过。

### 3. T+1/T+21交易日标签

- 配置为 `entry_offset=1`、`exit_offset=21`（`config.py:62-70`）。
- 代码先按证券向后移位，再要求对应行的全市场 `trade_index` 恰为T+1与T+21；证券中间缺行情时不会把“下一条记录”误当成下一交易日（`ml_pipeline.py:254-282`）。
- 任一端点或正价格条件失败即令标签缺失并在主流程剔除。判定：通过。

### 4. 切分边界

- 训练、验证、回测配置日期逐项与B3-B5一致（`config.py:73-85`）。
- `assign_non_overlapping_splits`要求60日窗口起点、T日、T+1、T+21均在同一分段，并拒绝重叠分段（`ml_pipeline.py:445-469`）。
- 因此每段首部不足60日、末部不足21日的候选不会成为样本；这是严格不跨段策略，`boundary_excluded`对数量留痕（`ml_pipeline.py:632-643`）。判定：通过。

### 5. VWAP量纲推导

- 公式为 `raw_vwap=turn_value/volume`，再乘 `forward_close/raw_close` 得到前复权VWAP（`ml_pipeline.py:202-226`），与AS14公式一致。
- `volume<=0`、非正价格、数量级不符的记录不会产生标签，并输出诊断统计（`ml_pipeline.py:209-234`）。
- 但代码用 `sanity_min_price_ratio=0.1`、`sanity_max_price_ratio=10.0`、`sanity_min_fraction=0.95`决定逐行保留及是否中止整个流程（`config.py:68-70`、`ml_pipeline.py:212-223`），AS14只写“同一价格数量级”，没有登记这三个参数。判定：不通过，见CA-A01。

### 6. 历史上市状态近似

- 实现不把当前 `list_state` 回填历史，只将其保留为审计字段；资格起点优先 `list_date`，缺失时回退加载区间内首个行情日（`ml_pipeline.py:306-334`）。
- 加载从训练起点前额外保留1年，正好为缺失上市日的满1年资格提供缓冲（`strategy.py:105-113`）。
- AS13明确披露当前证券主表快照、历史退市/摘牌无法完整恢复、首个行情日回退可能遗漏最早一年样本（`assumptions.md:147-157`）；代码还把策略名写入质量摘要（`strategy.py:232-235`）。判定：通过，属于已登记降级。

## issue 清单

| 编号 | severity | 证据定位 | 一句依据 | 处置要求 |
| --- | --- | --- | --- | --- |
| CA-A01 | critical | `src/r002_liquid_neural_networks/config.py:68-70`；`common/ml_pipeline.py:212-226`；`workspace/r002_liquid_neural_networks/assumptions.md:159-167` | D5实际以0.1/10.0价格比和95%合格率控制标签行保留及流程中止，而AS14未登记任何阈值，属于core要素的 `deviation_undeclared`。 | 在AS14明确登记三个阈值、逐行筛选和全局中止语义及预期影响，或删除未获裁决的参数化简化后重新审计。 |
| CA-A02 | major | `src/r002_liquid_neural_networks/strategy.py:255-323`；`workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:9-13,22-26` | 公开函数 `build_m1_audit_tables` 生成m1数据审计产物，但10个done行无一将实现位置回映到该函数，构成未映射公开“私货”。 | 将该函数按实际覆盖关系回填到相应D/B要素实现位置，或改为明确私有辅助函数并由已映射入口封装。 |
| CA-A03 | minor | `workspace/r002_liquid_neural_networks/assumptions.md:75-85,159-169`；`src/r002_liquid_neural_networks/strategy.py:83-89` | AS7仍称前复权文件“直接提供VWAP字段”，AS14与代码则确认该字段不存在并自行推导，两条均处于assumed状态，数据源口径存在未消解冲突。 | 标明AS14仅在数据源实现上取代AS7的“直接字段”表述，同时保留AS7对成交均价语义的裁决。 |

## 审计结论

- issue：3项（critical 1 / major 1 / minor 1）。
- 已检查维度：公式一致 / 参数一致 / 实现位置真实 / 代码反查 / 简化声明。
- 10个done行已逐条核对；实现位置均真实且非空壳。
- 训练期拟合、T日信息边界、T+1/T+21交易日标签、切分边界均通过。
- 历史上市状态近似与影响已由AS13如实登记。
- 前复权VWAP公式与AS14一致，但控制标签有效性和中止条件的三个数值阈值未登记；因此当前不能通过m1 code门禁。

## 第1次定向复核

- 复核模式：code。
- 复核边界：逐条复核 CA-A01、CA-A02、CA-A03；回归核对原先通过的训练期拟合、T日信息边界、T+1/T+21标签、切分边界与AS13历史上市状态近似；仅判定当前快照并发出现m2产物是否构成m1作用域问题，不审查m2实现内容。
- 本节为定向复核增量；上文初审问题证据与当时结论原样保留，以下状态取代初审的最终门禁判定。

### 原问题定向复核表

| 编号 | 初审级别 | 修复后证据 | 复核判定 |
| --- | --- | --- | --- |
| CA-A01 | critical | `config.py:61-70`已把0.1、10.0、0.95明确标注为AS14参数；`assumptions.md:159-169`登记了逐行OHLC/收盘价数量级筛选、最多5%无效行容忍、低于95%全局中止及样本减少影响；`ml_pipeline.py:173-243`按相同公式与阈值执行，`strategy.py:151-164`由集中配置透传。 | **resolved / pass**：公式、参数、中止语义与影响声明现已一致。 |
| CA-A02 | major | `coverage_matrix.md:9-13,22-26`已在全部10个m1 done要素的实现位置回填 `strategy.py:build_m1_audit_tables`；公开函数仍真实存在于`strategy.py:256-324`。 | **resolved / pass**：公开m1审计函数已完成双向映射。 |
| CA-A03 | minor | `assumptions.md:75-85`已明确AS7只保留“成交均价”语义，直接字段来源陈述由AS14替代；`assumptions.md:159-169`与`strategy.py:83-90`均说明文件无VWAP字段、需从成交额/成交量推导。 | **resolved / pass**：AS7与AS14不再冲突。 |

### 回归与范围复核

| 检查项 | 证据与判断 | 结论 |
| --- | --- | --- |
| 训练期拟合 | `ml_pipeline.py:480-527,620-636`仍只用训练样本窗口覆盖行拟合预处理器，验证/回测只变换；修复未改变该路径。 | pass |
| T日信息边界 | `ml_pipeline.py:406-450`窗口仍止于信号日T；执行日状态仍只作为后附元数据，未进入六通道特征。 | pass |
| T+1/T+21标签 | `config.py:65-66`仍固定1/21；`ml_pipeline.py:246-294`仍按全市场交易日索引精确核验买卖端点。 | pass |
| 切分边界 | `ml_pipeline.py:453-477`仍要求窗口起点、T、T+1、T+21落在同一不重叠分段；`strategy.py:238-252`保留二次断言。 | pass |
| AS13历史上市状态近似 | `assumptions.md:147-157`仍如实登记当前快照与首行情日回退近似；m1修复未扩大该简化。 | pass |
| m2并发产物观察 | 当前快照在`config.py:109-151`出现GRU/M2配置，在`strategy.py:327-498`出现m2数据切分、GRU构建和训练预测包装，且`coverage_matrix.md:15-16`的F2/F3已为m2 done。主编排确认implement stage的hard模式明确允许m1 auditor→verifier与m2 coder同批流水线重叠；因此这些内容是预期并发产物，不是m1修复越界证据。本次仅审m1 elements及其函数，m2由独立code审计处理。 | **dismissed / procedural_not_issue（CA-A04）** |

### 定向复核观察记录

| 编号 | 初始观察 | 证据定位 | 复核裁决 | 依据 |
| --- | --- | --- | --- | --- |
| CA-A04 | m1复核快照同时观察到m2配置、训练/预测实现及F2/F3状态推进。 | `src/r002_liquid_neural_networks/config.py:109-151`；`src/r002_liquid_neural_networks/strategy.py:327-498`；`workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:15-16` | **dismissed / procedural_not_issue**；不计open issue，也不表示m2实现已通过本次审计。 | implement stage hard模式采用m1 auditor→verifier与m2 coder同批重叠流水线；观察到m2并发产物符合协议，m2另行独立code审计。 |

## 第1次定向复核结论

- CA-A01、CA-A02、CA-A03全部修复通过；初审critical问题已清零。
- 原先通过的m1公式、时点、标签、分段和已登记近似未见回归。
- CA-A04保留为程序性观察记录，但按hard模式流水线重叠协议裁决为`dismissed / procedural_not_issue`；本次未审查、也未裁决m2实现。
- 当前open issue：0项（critical 0 / major 0 / minor 0）。

verdict: pass
