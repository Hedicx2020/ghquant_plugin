# r007 m5 实现对照审计

- mode: `code`
- milestone: `m5`
- 审计日期: 2026-07-27
- 审计边界: 只读核对 `spec.md`、`plan.md`、`assumptions.md`、`coverage_matrix.md`、`templates/ml.md`、m1–m4 既有接口与 m5/main/reporting 实现；未读取 coder 完成汇报，未运行正式全期，未读取或写入 `state.json`，未修改任何实现或结果产物。
- 代码快照:
  - `sensitivity_pipeline.py`: `bd72e804e6786349be328cd27c451db3d35da58765cb3cf88df70ac8b31ef87b`
  - `reporting.py`: `c69c19d7f8a238c0691d9001382b605526a864b1d5a2c1f3b5f67e388501e392`
  - `main.py`: `b6345ba5f5a43955bc127c49c201714c64fcd87930e19644a0251098331bdaa2`
  - `__main__.py`: `3987f6870d17836014edd0703e0a200bcf7dc20bd06b476a22830946010ed3db`
  - `config.py`: `9bfb0265c83c158689fd200c4ba7516941c0a3c518b4a65883f639c4f9586b9d`
  - `common/ml_reporting.py`: `c542252ecf03e846e4898042337f1bd714304266fee4ccb4fe4d7274b12c5bdb`

## 一、当前 milestone 全部 done 行逐条核对

| 要素 | 公式/口径核对 | 参数核对 | 实现位置真实性与代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- |
| R2 | `summarize_hyperparameter_sharpe` 按模型×qr 对有效配置 Sharpe 求 mean/std；独立合成 111×6 行重算，42 个汇总格与 pandas 独立 groupby 的 mean/std 最大绝对差均为 0 | 七模型配置数独立重算为 LASSO 8、RIDGE 8、SVM 5、XGBoost 27、LGBM 27、RF 9、AdaBoost 27，总计 111；参考表七模型×六组合为 42 格，逐项与 spec R2 数值一致 | `sensitivity_pipeline.py:93-370` 存在真实实现，无 pass/TODO 空壳 | AS7/AS8/AS15/AS16 已登记；R2 保留逐格精确对照，不从图估读 | pass |
| SA1 | 每个目标单独抽取删除位置，只从原先未连接源节点无放回换边；动态重算确认替换前后 4 条边、逐目标入度守恒、替换源均来自原未连接集合 | 比例固定 0/20/40/60/80/100%，稳定哈希种子从全局 seed、方向、锚点、比例、目标代码派生；相同输入两次输出逐行一致 | `sensitivity_pipeline.py:373-527` 与 `main.py:549-611` 存在真实实现 | 未登记新增简化；但十模型中位数门槛不完整，见 CA-A04 | fail |
| SA2 | 基准因果映射后按 `lag-1` 个源市场交易日回移；对 l=1–5 的合成日历独立重算，源日位置均严格等于 l=1 位置减 `lag-1`，源收盘均早于目标开盘 | l 固定为 1/2/3/4/5，覆盖 spec 的 l=2,3,…及 Lag 4 后观察 | `sensitivity_pipeline.py:530-590` 与 `main.py:614-700` 存在真实实现 | 未登记新增简化；但十模型中位数门槛不完整，见 CA-A04 | fail |
| SA3 | 冻结图、标签仍为目标日 `opcl_excess`，单模型配置逐个运行；完整笛卡尔积与 AS7 一致 | 只 clone AS15 主参数原型并覆盖当前网格字段，不回写主配置；SVM 只改变 C，保留 AS16 的 RBF/epsilon/gamma | `sensitivity_pipeline.py:93-370` 与 `main.py:703-786` 存在真实实现 | 主结果不调参，Appendix A 网格只用于 SA3/R2，声明一致 | pass |
| SA4 | 应以 OPCL 特征比较跨市场图、同市场图、非图三规格；当前调用在进入组合前违反严格双方向合同 | 只局部 replace `source_value_column="opcl_excess"`，未改主参数 | `main.py:789-861` 不是空壳，但真实链稳定抛错，见 CA-A01 | AS8 只授权方向性核对，未授权放松 m4 双方向合同 | fail |
| SA5 | 用预测行的 `source_date` 连接美国绝对 pvCLCL 冲击；扩展历史分位仅用当时及此前冲击，目标日严格晚于源日；子样本按 qr1–qr6 嵌套 | 冲击字段固定 `pvclcl_market`，组合层只取各冲击日集的全股票组合 | `sensitivity_pipeline.py:658-734` 与 `main.py:864-892` 存在真实实现 | 使用 AS12 的美国宽基替代口径，已登记；未冒充 SPY 原样本 | pass |
| SA6 | 仅消费 US→CN 固定组合历史并附加目标 A 股行业，不构造缺失的美股行业块 | `standard_code=37` 与 AS4 的中信一级一致 | `sensitivity_pipeline.py:737-807` 与 `main.py:895-921` 不是空壳，但实际数据入口稳定抛错，见 CA-A02 | F6 `data_missing` 与 SA6 仅目标 A 股行业的边界已登记 | fail |
| SA7 | 两个同锚点图的 US 与 CN 特征在目标日内连接，训练期严格早于锚点，两个源日均要求早于目标日；标签保持 CN `opcl_excess` | 四种 pvCLCL/OPCL 联合组合完整，模型工厂仍为 AS15/AS16 固定主参数 | `sensitivity_pipeline.py:810-1026` 与 `main.py:924-1045` 存在真实预测与组合实现 | 原文无逐格数值，方向性边界已登记；但未实现对“仅美国预测变量”基线的实际比较，见 CA-A05 | fail |
| TBL1 / FIG3–FIG19 / ml 模板图 | R2/TBL1 底表可追溯；PNG 保存函数固定 300 DPI；但正式 Figure 13 会因字段合同错误中断，部分图与底表未同 sheet，Figure 10 曲线维度被错误折叠 | 配色、尺寸、字号与 300 DPI 配置符合项目合同 | `reporting.py:377-652,778-912` 为真实实现；受控 smoke 在临时目录生成 20 张 PNG、4 个 xlsx、JSON/日志/manifest 共 28 文件，所有 PNG 元数据约 300 DPI，正式 results 前后快照一致 | `train_val_loss` 明确 N/A；FIG4 有 AS4/data_missing 理由；其余问题见 CA-A03、CA-A07、CA-A08 | fail |

## 二、issue

### CA-A01

- severity: major
- location: `src/r007_cross_market_return_forecasting/main.py:789-846`；`src/r007_cross_market_return_forecasting/portfolio_pipeline.py:587-631`；`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:60`
- evidence: 承接 m4 移交 CA-A03，以真实 `_run_sa4` 调用真实 `run_m4_portfolios`，仅将昂贵上游图/预测替换为两日、完整十模型的受控 CN 三规格输入；稳定抛 `DirectionContractError`。异常 audit 六行中 CN 的 cross/same-graph/non-graph 均为 `complete`，对应 US 三腿均为 `missing_expected_direction`。因此 SA4 在 `m5_sa4_sharpe` 写出前终止，而矩阵仍标 `done`。
- suggestion: SA4 应使用不会形成 R3/R4 的底层单方向组合接口，或在 m5 调用层补齐严格入口所需的 US 三腿；不得放松 m4 核心双方向合同，并将 SA4 状态回退为 `in_progress` 直至动态回归通过。

### CA-A02

- severity: major
- location: `src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:737-757`；`src/r007_cross_market_return_forecasting/main.py:895-920`；`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:62`
- evidence: 对实际 `/Users/hedi/local_data/ashare_stock_industry.parquet` 独立读取重算，`standard_code=37` 有 6505 行、6501 个唯一股票，4 个股票形成 8 个重复行；真实调用 `load_citic_level_one_industry()` 稳定抛 `ValueError: 中信一级行业映射存在重复股票`。因此正式链即使越过 SA4，也会在 SA6 加载阶段中止，coverage 的 `done` 不真实。
- suggestion: 在不改变 AS4 中信一级口径的前提下，制定并登记可审计的确定性去重规则，同时输出原始重复键、选择依据与映射覆盖审计；将 SA6 状态回退为 `in_progress`。

### CA-A03

- severity: major
- location: `src/r007_cross_market_return_forecasting/main.py:1139-1140`；`src/r007_cross_market_return_forecasting/portfolio_pipeline.py:1014-1025`；`src/r007_cross_market_return_forecasting/reporting.py:534-560`
- evidence: `_build_chart_tables` 把 R3/R4 拼接后的 `core_paired_comparisons` 直接交给 FIG13；该表包含 `difference_cn_to_us_minus_us_to_cn`、`same_graph_minus_non_graph`、`cross_minus_same_graph`，不含 reporting 选择的 `sharpe_delta` 或回退字段 `annualized_sharpe`。用一行真实 R4 schema 受控调用 `create_result_charts`，稳定抛 `KeyError: Figure 13 相对非图基线 Sharpe 差 缺少字段: ['annualized_sharpe']`。smoke 因 `core_comparison` 为空只生成 N/A 图，未覆盖该正式非空分支。
- suggestion: 为 FIG13 明确只选择 R4 行及正确的 delta 字段/长表结构，并新增非空正式 schema 的 reporting 回归测试；在修复前 m5 正式输出链不可视为完成。

### CA-A04

- severity: major
- location: `src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:624-655`；`src/r007_cross_market_return_forecasting/main.py:601-605,690-694`；`workspace/r007_cross_market_return_forecasting/spec/spec.md:464-480`
- evidence: spec 要求 SA1/SA2 “各分位取十种模型结果的中位数”，实现先过滤 `sharpe_status=="ok"` 后直接对剩余模型求中位数，只记录 `model_count` 而不要求其等于 10，也不核模型集合。独立传入缺少 `ensemble-med` 的九模型完整有限 Sharpe 后，函数正常返回 `model_count=9, median_sharpe=4.0`，未失败或标 N/A。
- suggestion: 对每个敏感性值×qr 强制核对完整十模型集合；任一模型 Sharpe 不可用时不得把九模型或更少的中位数冒充原文十模型中位数，应保留原因并输出 N/A/不完整审计。

### CA-A05

- severity: major
- location: `src/r007_cross_market_return_forecasting/main.py:980-1045,1062-1071`；`src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:1029-1069`；`workspace/r007_cross_market_return_forecasting/spec/spec.md:517-522`
- evidence: SA7 只输出四种联合特征的绝对 Sharpe；`_run_sa7` 未接收 m4 的“仅美国预测变量”基线，`build_directional_sensitivity_comparison` 也只写入参考结论、行数和全表数值 min/max，未形成同模型×qr 配对差值或“部分规格超过 Figure 8”的可检验观测。因此现有证据无法支撑 SA7 的原文比较结论，coverage 却标 `done`。
- suggestion: 将固定样本/标签/组合口径的 US-only m4 基线按模型×qr 与四种联合规格严格配对，输出差值、配对完整性及方向性观测；不填 verifier verdict。

### CA-A06

- severity: major
- location: `src/r007_cross_market_return_forecasting/main.py:145-169,208-223,270-290,465-466,709-729`
- evidence: 通用阶段续跑只检查 marker 的 `status=="complete"` 与文件存在；marker 不记录或校验代码哈希、config/参数哈希、输入清单哈希或 schema。SA3 单配置更是仅凭 `configuration_id.parquet` 存在即复用，且 configuration checkpoint 直接写最终文件、无 `.part` 原子替换。代码、股票池、标签或组合历史口径变化后，正式无参入口可静默混用陈旧检查点，不能证明“固定样本/标签/组合历史口径”。
- suggestion: 每阶段 marker 固化并校验代码、config、输入 manifest、schema 与上游 checkpoint 哈希；SA3 单配置文件使用临时文件校验后原子替换，不匹配时明确失效重算。

### CA-A07

- severity: major
- location: `src/r007_cross_market_return_forecasting/main.py:1141-1160`；`src/r007_cross_market_return_forecasting/reporting.py:590-650,811-822,839-855`
- evidence: FIG16 使用 `sa4_opcl_delta` 生成 PNG，但 `sensitivity_analysis.xlsx` 未导出该 delta 表，其他工作簿也未包含它；因此 Figure B.2 没有可逐格追溯的 Excel 底表。FIG14 使用 SA1 与 SA2 拼接底表，Excel 却只把该图嵌入“SA1边替换”sheet，SA2 底表在另一个无图 sheet。临时 smoke 重开 workbook 独立检查，敏感性各 sheet 图片数中“SA1边替换”为 1、“SA2信息滞后”为 0，且没有 SA4 delta sheet。
- suggestion: 为 FIG14 导出并在同一 sheet 放置拼接后的边替换/滞后长表；为 FIG16 导出 `sa4_opcl_delta` 并把对应 PNG 嵌入同一 sheet，满足图与底层数据同 sheet 合同。

### CA-A08

- severity: major
- location: `src/r007_cross_market_return_forecasting/main.py:1106-1125,1147-1152`；`src/r007_cross_market_return_forecasting/reporting.py:430-449,564-575`
- evidence: `daily_pnl` 保留 specification、feature_set、direction、target_market、model、portfolio 七维，但 Figure 10 与模板累计图都只按 `model` 分组作线；同一模型同一日期的三规格、双方向和六组合多行被依次连接成一条曲线。Figure 10 因而不是 spec 所要求的“US pvCLCL→CN OPCL 十模型×六组合累计 PnL”，曲线条数和数据语义均与底表维度不一致。
- suggestion: Figure 10 先严格过滤 US_TO_CN/cross-market/pvCLCL，并以 `model×portfolio` 为独立 series；模板累计图也须显式选择或编码所有保留维度，禁止把重复日期的不同组合连接为一条模型曲线。

## 三、coverage 与公开接口反查

- `coverage_matrix.md:54,57-63` 的 R2、SA1–SA7 实现位置均存在，不是 pass/TODO 空壳。
- 但 SA4、SA6 真实调用会中止，SA7 缺核心基线比较，故相应 `done` 状态不真实；本审计按只写审计产物合同未修改矩阵，已在 CA-A01、CA-A02、CA-A05 明确要求回退。
- `strategy.py` 的公开模型入口继续映射 F11–F19；m5 新增公开函数均服务 R2/SA1–SA7，未发现未映射要素 ID 的策略“私货”。
- `common/ml_reporting.py` 已反查；r007 正式入口实际导入报告专属 `src/.../reporting.py`，未发现其改写 m1–m4 数值，但其正式输出合同存在 CA-A03、CA-A07、CA-A08。

## 四、已检查维度结论

- [x] 公式一致：逐条核对 R2、SA1–SA7 的算子、标签、时点、分子分母与组合历史字段；独立运行 SA1/SA2/SA3/R2/SA5 小样本。
- [x] 参数一致：独立重算 111 个 SA3 配置与 R2 42 格；核对 seed=42、SA1 六比例、SA2 l=1–5、SA4 OPCL、SA5 pvCLCL 冲击、SA6 中信一级、SA7 四组合；确认敏感性参数未回写主配置。
- [x] 实现位置真实：矩阵 m5 全部 done 行均定位到非空函数；未发现 pass/TODO 空壳，但发现三个可复现正式中断点。
- [x] 代码反查：从 main 无参正式入口、checkpoint、m1–m4 固定输入、m5 七项分析反查至 JSON/Excel/PNG；受控 smoke 仅写临时目录，未污染正式 results。
- [x] 简化声明：AS4/AS7/AS8/AS15/AS16/AS19/AS24–AS26 均核对；R2 精确表与 SA 方向性证据边界未伪造 verifier verdict，但 SA7 比较证据缺失。

verdict: fail

## 六、第 3 轮最终定点复核

- 复核日期: 2026-07-27
- 复核范围: 仅复核第 2 轮唯一未闭环 CA-A01 的 dtype 修复，并对 CA-A02–CA-A08 做防退化回归；保留前两轮历史。
- 运行边界: 真实 `_run_sa4` 使用受控上游、真实 CN 三规格组合函数与临时 checkpoint；`main --smoke` 仅写系统临时目录。未读取或写入 `state.json`，未修改代码、coverage 或正式 results。
- 第 3 轮代码快照:
  - `sensitivity_pipeline.py`: `56f5aabf3e2e71a33442a94955566bc78b159b1cc74209acdaf073dc3797f4d6`
  - `reporting.py`: `f3fb37e8cc0caa90148c4bd8f61370b731bf06f77924f7e8e56a9887d66dc676`
  - `main.py`: `6d51afbd0263456786aebb6c32a53777380cd0730e41f94d535c4333df9c2af3`
  - `__main__.py`: `3987f6870d17836014edd0703e0a200bcf7dc20bd06b476a22830946010ed3db`
  - `config.py`: `9bfb0265c83c158689fd200c4ba7516941c0a3c518b4a65883f639c4f9586b9d`
  - `common/ml_reporting.py`: `c542252ecf03e846e4898042337f1bd714304266fee4ccb4fe4d7274b12c5bdb`

### 6.1 CA-A01：通过

- location: `src/r007_cross_market_return_forecasting/main.py:1224-1409`；`src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:666-732`；`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:60`
- 真实 `_run_sa4` 受控上游采用 40 个交易日、4 只股票、完整十模型与六个 qr，真实 CN 三规格组合形成 180 行 Sharpe；`m5_sa4_sharpe` 与 `m5_sa4_delta` 均落盘 180 行，模型完整性、可比性、执行时点三张审计 checkpoint 也全部落盘，目录无 `.part`。
- 将所有 `annualized_sharpe` 强制变为 object 字符串，并在非图规格 `AdaBoost/qr1` 注入一个 `not-a-number`。真实主装配无 TypeError；Sharpe 的 `annualized_sharpe` 及 delta 的 `annualized_sharpe/non_graph_sharpe/sharpe_delta` 均为 `float64`。
- 独立重算得到直接转换失败 1 行、该非图基线向三规格传播失败 3 行、有限配对 177 行、状态完整配对 177 行。实现逐行 `finite_sharpe_pair/paired_complete/sharpe_delta` 与独立数组计算完全一致；不可转换值保留 NaN，非完整行的 delta 均为 NaN 且 `delta_status` 不为 `ok`，可比性审计中的四项计数逐行一致。
- 将相同 CN-only 三规格输入交给原 `run_m4_portfolios` 仍因缺少 US 方向而抛 `DirectionContractError`，错误证据含 `missing_expected_direction`；m4 严格双方向合同未被放松。
- 判定: 第 2 轮 CA-A01 已关闭。

### 6.2 CA-A02–CA-A08 防退化结果

- CA-A02：实读行业文件独立重算仍为 6505 行、6501 个唯一股票、4 个重复键、8 个重复行、0 个冲突键；映射键唯一。合成同股票“电子/汽车”冲突仍明确失败。定位：`sensitivity_pipeline.py:933-1022`。
- CA-A03：非空 R4 单行仍转换为两行 Figure 13 长表，差值为 0.15/-0.05；真实绘图分派生成 `fig13_sharpe_delta.png`。定位：`reporting.py:254-307,589-602`。
- CA-A04：九模型输入仍输出 `incomplete_model_set` 与 N/A；完整十模型的独立中位数 4.5 与实现一致。定位：`sensitivity_pipeline.py:735-832`。
- CA-A05：四特征组合×十模型×六 qr 的 240 对全部完整，逐行 `joint-us_only` 差值与独立重算完全一致。定位：`sensitivity_pipeline.py:1287-1394`。
- CA-A06：未变上下文可复用；分别改变 code/config/input 均得到 `context_hash_mismatch`；外部表原子 checkpoint 可复用且无 `.part`。定位：`main.py:145-290,465-496`。
- CA-A07：真实 `main --smoke` 产出的 `sensitivity_analysis.xlsx` 中，`SA4_OPCL` 与 `SA4差值` 各有 180 行数据加表头、各嵌入 1 张对应图片；FIG15/FIG16 PNG 均存在。定位：`reporting.py:877-929`。
- CA-A08：独立构造三规格×双方向×双模型×双组合×两日数据，真实 `_build_chart_tables` 保留 24 条全维 series；Figure 10 严格筛至 cross/pvCLCL/US_TO_CN/CN 后保留 4 条 `model×portfolio` series，两个输出均无 `series_label×date` 重复。定位：`main.py:1870-1949`。
- 代码快照显示 CA-A02–CA-A07 的核心 `sensitivity_pipeline.py/reporting.py/config.py/common/ml_reporting.py` 与第 2 轮一致；本轮改变的 `main.py` 已由上述真实装配、checkpoint 与图表分派动态覆盖，未发现回归。

### 6.3 main smoke 与正式目录隔离

- 通过真实 `main()` 的 `--smoke` 分派运行，退出码为 0；独立读取 manifest 确认为对象结构，临时目录共 20 张 PNG、37 个文件，无 `.part`。
- 独立重开工作簿确认 `SA4_OPCL`、`SA4差值`、`FIG14边替换与滞后` 均为非空且各嵌入 1 张图；Sharpe 与 delta 数值列重读后均为数值类型。
- 正式 `output/r007_cross_market_return_forecasting/results/` 运行前后文件哈希快照一致，本轮 smoke 未污染正式结果。

### 6.4 第 3 轮 issue

- 无新增 issue。CA-A01 已关闭，CA-A02–CA-A08 未退化。

### 6.5 第 3 轮已检查维度结论

- [x] 公式一致：独立重算 SA4 数值转换、有限配对、完整配对与 delta；复核 SA7 240 对、十模型中位数及全维累计路径。
- [x] 参数一致：十模型、六 qr、三规格、OPCL、CN-only 边界和非图基线键均与 spec/既有配置一致。
- [x] 实现位置真实：coverage 的 m5 done 行在前两轮已逐条定位；本轮命中真实 `_run_sa4`、真实 CN 三规格函数、真实 checkpoint 与真实报告装配，无 pass/TODO 空壳。
- [x] 代码反查：从 `_run_sa4` 输入、dtype 转换、合并、delta 到五张 checkpoint，再到 FIG15/FIG16、Excel 与 `main --smoke` 全链反查；CA-A02–CA-A08 均有动态防退化证据。
- [x] 简化声明：未发现新增未登记简化；m4 双方向合同保持严格，SA4 仅使用既定 CN-only 专用入口。
- [x] coverage 真实性：`coverage_matrix.md:60` 的 SA4 `done` 及实现位置与本轮真实可执行结果一致；CA-A02–CA-A08 的既有 done 状态未见退化。

verdict: pass

## 五、第 2 轮定点复核

- 复核日期: 2026-07-27
- 复核范围: 逐条复核首轮 CA-A01–CA-A08；保留首轮历史，不重写原结论。
- 运行边界: 仅使用临时目录、内存合成输入和实际只读行业文件；未运行正式全期，未读取或写入 `state.json`，未修改代码、coverage 或正式 results。
- 修复后代码快照:
  - `sensitivity_pipeline.py`: `56f5aabf3e2e71a33442a94955566bc78b159b1cc74209acdaf073dc3797f4d6`
  - `reporting.py`: `f3fb37e8cc0caa90148c4bd8f61370b731bf06f77924f7e8e56a9887d66dc676`
  - `main.py`: `2cede4bf98631b66fa1ab95cde6bef8f8443901784ed9451a5ac6cac34edba93`
  - `__main__.py`: `3987f6870d17836014edd0703e0a200bcf7dc20bd06b476a22830946010ed3db`
  - `config.py`: `9bfb0265c83c158689fd200c4ba7516941c0a3c518b4a65883f639c4f9586b9d`
  - `common/ml_reporting.py`: `c542252ecf03e846e4898042337f1bd714304266fee4ccb4fe4d7274b12c5bdb`

### 5.1 CA-A01：未关闭

- severity: major
- location: `src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:666-732`；`src/r007_cross_market_return_forecasting/main.py:1220-1308`；`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:60`
- evidence: 新增的 `run_cn_three_specification_portfolios` 已独立运行成功：40 个交易日、4 只股票、完整十模型、CN 三规格合成输入形成 180 行 Sharpe，目标市场仅为 CN、三规格齐全。把同一输入交给原 `run_m4_portfolios`，其方向 audit 仍为 CN 三腿 `complete`、US 三腿 `missing_expected_direction` 并抛 `DirectionContractError`，证明 m4 严格双方向合同未被放松。但是通过真实 `_run_sa4` 主装配调用同一成功输入时，执行到 `main.py:1291-1296` 的 `np.isfinite(delta["annualized_sharpe"])` 稳定抛 `TypeError: ufunc 'isfinite' not supported for the input types`；独立反查组合结果确认 `annualized_sharpe`、`non_graph_sharpe` 为 object dtype。SA4 因而仍在写出 delta 和检查点前中止，coverage 的 `done` 仍不真实。
- suggestion: 在 `_run_sa4` 形成 `paired_complete` 前显式将两列转换为数值 ndarray/Series，再做有限值检查；须用真实 `_run_sa4` 非空十模型 CN 三规格回归确认 Sharpe、delta 与三张审计表全部写出，同时保留 m4 单 CN 输入失败的严格门槛。

### 5.2 CA-A02：通过

- 独立实读 `/Users/hedi/local_data/ashare_stock_industry.parquet`：`standard_code=37` 为 6505 行、6501 个唯一股票、4 个重复键、8 个重复行、0 个行业/口径冲突键。
- 去重后 mapping 为 6501 个唯一 `target_code`；重复证据表保留 8 行，`has_conflict` 全为 false，并登记稳定排序保留首行。
- 在临时 parquet 构造同一股票分别属于“电子/汽车”的冲突输入，真实 `load_citic_level_one_industry` 明确抛 `ValueError: 中信一级重复股票存在行业冲突，禁止任意选取`。
- 判定: 首轮 CA-A02 已关闭。

### 5.3 CA-A03：通过

- 用非空 R4 单行输入独立调用 `build_figure13_long_table`，得到两行 `same_graph_minus_non_graph` / `cross_minus_same_graph` 长表，`sharpe_delta` 分别为 0.15/-0.05。
- 将该非空长表交给真实 `create_result_charts`，`fig13_sharpe_delta.png` 状态为 `generated` 且文件存在，不再触发首轮 `annualized_sharpe` KeyError。
- 判定: 首轮 CA-A03 已关闭。

### 5.4 CA-A04：通过

- 九模型输入缺少 `ensemble-med` 时，真实函数输出 `complete_ten_model_set=false`、`median_status=incomplete_model_set`、`median_sharpe=N/A`，audit 精确登记 `missing_models=("ensemble-med",)`。
- 完整十模型均为有效 Sharpe 时，输出 `complete_ten_model_set=true`、`median_status=ok_complete_ten_models`、`valid_model_count=10`，对 0–9 独立重算中位数为 4.5，与实现一致。
- 判定: 首轮 CA-A04 已关闭。

### 5.5 CA-A05：通过

- 独立构造四种特征组合×十模型×六 qr 的联合与 US-only 同键表，共 240 对。
- `build_sa7_us_only_comparison` 返回 240 行，全部 `paired_complete=true`；四个组合各自 `expected_pair_count=60`、`complete_pair_count=60`、`pairing_complete=true`，逐格 delta 与正负关系可重算。
- 主链 `_run_sa7` 先对 joint 与 US-only 取共同 `target_date/target_code`、检查十模型有限值与标签一致，再以相同流动性、容量和 qr 口径分别回测，输出配对表/audit/summary；未写 verifier verdict。
- 判定: 首轮 CA-A05 已关闭。

### 5.6 CA-A06：通过

- 对真实 `CheckpointStore` 独立建立 upstream/downstream marker 与 parquet：上下文未变时 `reusable=true`。
- 分别改变 code、config、input manifest、upstream marker 后均 `reusable=false/context_hash_mismatch`。
- 改写输出内容后 `reusable=false/output_hash_mismatch`；改写输出 schema 后同样明确失效，不会复用。
- `write_external_frame_atomic` 写出 SA3 单配置 parquet 与 JSON sidecar 后，hash/schema 校验可复用，目录中无 `.part` 残留。
- 判定: 首轮 CA-A06 已关闭。

### 5.7 CA-A07：通过

- 独立用临时目录调用 `write_formal_outputs`，重开 `sensitivity_analysis.xlsx`。
- `FIG14边替换与滞后` sheet 有 4 行底层数据加表头并嵌入 1 张对应图；`SA4差值` sheet 有 1 行底层数据加表头并嵌入 1 张 FIG16。
- 判定: 首轮 CA-A07 已关闭。

### 5.8 CA-A08：通过

- 构造三规格×双方向×双模型×双组合×两日的非空日度 PnL，真实 `_build_chart_tables` 为模板累计图生成 24 个全维 series，等于 `3×2×2×2`，且 `series_label×target_date` 无重复。
- Figure 10 严格筛为 `cross_market_graph/pvclcl_excess/US_TO_CN/CN`，保留 4 个 `model×portfolio` series，等于 `2×2`，且逐 series/date 唯一。
- 正式十模型×六组合口径对应 60 条 Figure 10 独立路径；模板累计图不再把规格、方向、市场或组合折叠到 model。
- 判定: 首轮 CA-A08 已关闭。

### 5.9 main smoke、正式分派与 coverage

- 通过真实 `main()` 的 `--smoke` 分派在临时 smoke_dir 运行：退出码 0，产出 manifest，结束后无 `.part`；正式 results 运行前后文件快照一致。
- 独立替换两个入口为只记录调用的无副作用探针：无参 `main()` 只调用 `run_formal_pipeline`，`--smoke` 只调用 `run_smoke`，两者分派互斥。
- `coverage_matrix.md:60` 已把 SA4 位置更新为 `run_cn_three_specification_portfolios` 与 `_run_sa4`，但仍标 `done`；因真实 `_run_sa4` 尚有 CA-A01 的 dtype 中断，该状态不能通过本轮审计。SA7 位置已更新为 `predict_joint_graph_snapshots/build_sa7_us_only_comparison` 与 `_run_sa7`，与实现一致。
- smoke 内置回归显示 CA-A01 passed 的依据只覆盖 CN-only 底层函数，没有调用会失败的真实 `_run_sa4`，故不能替代本轮独立主装配复核。

### 5.10 第 2 轮已检查维度结论

- [x] 公式一致：复核 CN 三规格组合、SA7 240 对 delta、十模型中位数、全维累计路径。
- [x] 参数一致：十模型、六 qr、四种联合特征、OPCL、CN-only 与 m4 双方向边界均未被放松或改写。
- [x] 实现位置真实：CA-A02–CA-A08 当前位置均动态命中；CA-A01 新底层函数真实，但 main 装配仍运行失败。
- [x] 代码反查：真实行业文件、非空 Figure 13、checkpoint 六类变化、Excel 图表同 sheet、main 分派及临时 smoke 均独立运行。
- [x] 简化声明：未发现本轮新增未登记简化；SA4 失败属于实现 dtype 错误，不是允许的降级。
- [x] coverage 真实性：SA7 的更新位置真实；SA4 因 CA-A01 未关闭而不应保持 `done`。

verdict: fail

## 七、第 3 轮文末裁决

- 第 2 轮历史结论保留如上；其唯一未闭环项 CA-A01 已由第六节的独立动态复核关闭。
- CA-A02–CA-A08 防退化回归均通过，无新增 issue。
- 已检查维度：公式一致、参数一致、实现位置真实、代码反查、简化声明，五维度均已完成。

verdict: pass
