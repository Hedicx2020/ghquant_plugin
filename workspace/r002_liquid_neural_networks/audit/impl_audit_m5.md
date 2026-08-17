# M5 实现审计（code mode）

- 案例：`r002_liquid_neural_networks`
- milestone：`m5`
- 审计范围：仅审 `coverage_matrix.md` 中状态为 `done` 的 R1–R7、SA1–SA3；只依据当前文件，不采信 coder 自述
- 审计材料：`spec/spec.md`、`spec/coverage_matrix.md`、`spec/ambiguities.md`、`assumptions.md`、`src/r002_liquid_neural_networks/` 全部代码、`common/ml_reporting.py` 及其实际调用模块、`templates/ml.md`、`templates/standards.json`
- 未执行事项：未运行正式全量回测，未修改实现、覆盖矩阵、假设或 `state.json`

## 一、逐要素结论

| 要素 | 结论 | 核对结果 | 关联问题 |
|---|---|---|---|
| R1 | pass_with_issues | 研报资源区间只作为 `reference_only` 背景展示，复现侧没有把 5%–70% 复制为实测值；但 R1 未完整进入统一 comparison 合同，且公共实现回映不完整。 | CA-A02、CA-A07 |
| R2 | fail | 实际 CPU RSS、设备显存和研报资源口径被分栏展示，未硬编码复制研报值；但 GPU/MPS 测量为进程累计/顺序相关值而未按模型隔离或明确披露，R2 也未进入统一 comparison 合同。 | CA-A02、CA-A08 |
| R3 | fail | RankIC 按 20 条路径等权聚合可追溯；模型相关矩阵也由实际预测生成，但相关方法被实现为未登记的 Pearson，属于核心结果口径的未声明选择。 | CA-A01、CA-A02、CA-A07 |
| R4 | fail | 全期多头年化收益取自 20 路径逐路径指标的等权聚合，公式链路正确，且研报值与复现值分离；但 comparison 字段合同、成功运行日志门禁和配套图表/Excel 数据合同不合格。 | CA-A02、CA-A03、CA-A05、CA-A06 |
| R5 | fail | 2024 多头年化收益取自对应期间、对应组合、20 路径逐路径指标的等权聚合；失败原因同 R4。 | CA-A02、CA-A03、CA-A06 |
| R6 | fail | 全期多空年化收益取自 20 路径逐路径指标的等权聚合；失败原因同 R4。 | CA-A02、CA-A03、CA-A05、CA-A06 |
| R7 | fail | 2024 多空年化收益取自对应期间、对应组合、20 路径逐路径指标的等权聚合；失败原因同 R4。 | CA-A02、CA-A03、CA-A06 |
| SA1 | fail | 五模型全期/2024 多头、多空指标可以从完整路径聚合表追溯，但 comparison 未覆盖完整 SA1 表，Excel 内嵌图与同 sheet 数据并非实际绘图数据。 | CA-A02、CA-A06、CA-A07 |
| SA2 | fail | 五模型 20 路径 RankIC 聚合可追溯；模型间相关矩阵的 Pearson 口径未登记，且 comparison/公开函数回映不完整。 | CA-A01、CA-A02、CA-A07 |
| SA3 | fail | 五模型训练资源记录未复制研报值，CPU RSS 明示为进程累计口径；GPU/MPS 行却不具备模型隔离性，且 comparison 与 Excel 证据合同不完整。 | CA-A02、CA-A06、CA-A08 |

## 二、五维度核对

### 1. 数据流

通过项：

- `src/r002_liquid_neural_networks/main.py:84-109` 的默认 CLI 未启用合成数据，默认回测截止日由配置给出；`main.py:112-133` 将默认训练上限保持为 100 epoch。
- `src/r002_liquid_neural_networks/config.py:206-232` 默认包含 GRU、LTC、NCP（LTC）、CFC、NCP（CFC）五模型、10 分组以及 `0..19` 共 20 条路径。
- `--backtest-end`、`--seed` 等扰动通过局部 dataclass `replace` 形成运行配置，不改写源码默认值；只有显式 synthetic smoke 分支才把 epoch/device 降到冒烟口径，并标记为非正式运行。
- `common/ml_reporting.py:571-603` 输出的明细 Parquet 未套用 Excel 行数上限；AS17 的展示行数上限没有截断 Parquet 明细。

失败项：

- 特征重要性仅使用按样本排序后的前 64 个回测样本计算，且结果被写入正式 `metrics.json`，违反 AS17“抽样只用于展示”的边界，见 CA-A04。
- 资源记录在 GPU/MPS 下受同进程中此前已驻留模型影响，单行不能解释为该模型独立资源占用，见 CA-A08。

### 2. 公式与统计口径

通过项：

- R4–R7 由 `common/ml_portfolio.py` 生成逐路径、逐模型、逐期间、逐组合指标，`common/ml_reporting.py:174-197` 再选取全期/2024、多头/多空对应行；不是从研报参考值回填复现值。
- 20 路径 RankIC 来自 m4 的 `rank_ic_path_aggregate`；月度图在 `common/ml_reporting.py:362-371` 先做路径内月度聚合，再对当月有效路径等权，符合路径优先原则。
- `common/ml_reporting.py:136-149` 单独构造研报参考表，`common/ml_reporting.py:152-298` 从实际 portfolio 聚合表构造复现指标。R1 复现值显式为空；R2 标记口径不可比；R3 的研报区间与复现矩阵/范围分离；R4–R7 的研报值和复现值保持独立字段。

失败项：

- `src/r002_liquid_neural_networks/config.py:230` 将 R3/SA2 模型相关方法设为 `pearson`，并由 `common/ml_portfolio.py:219-227` 实际执行；`spec.md`、`ambiguities.md`、`assumptions.md` 均未登记 Pearson/Spearman 选择，见 CA-A01。
- 分组累计收益图在 `common/ml_reporting.py:381-389` 先平均路径日收益再复利，未按 AS3/AS16 先形成逐路径净值再聚合，见 CA-A05。

### 3. 边界条件与可复现性

通过项：

- 默认正式口径为全样本、五模型、20 路径、100 epoch 上限；CLI 扰动不会修改源码默认值。
- 预测散点图使用固定随机种子抽样；完整预测明细仍输出到 Parquet。
- 正式指标未从研报常数硬编码复制；R1 的背景值只进入 reference 区域。

失败项：

- 特征重要性取“排序后前 64 条”而不是完整样本或可复现的代表性聚合，既有时间偏置又进入正式指标，见 CA-A04。
- GPU/MPS 资源值依赖模型执行顺序和此前模型驻留状态，单模型结果不能稳定复现为独立资源口径，见 CA-A08。
- 成功 run log 写法不能通过现有机器门禁，因此即使主流程成功，验证阶段仍会被固定判失败，见 CA-A03。

### 4. 产物合同与展示真实性

通过项：

- 共生成 8 张图：特征重要性、RankIC、分组累计收益、训练/验证损失、预测散点、模型相关、年度收益、资源使用。
- 8 张图的标题统一带 `复现生成—非原图复刻`；没有把复现图命名或标注为 FIG15–24/TBL6–10 原图复刻。
- 图表使用 300 DPI、whitegrid 与中文字体；Excel 为多 sheet，首行加粗、冻结、自动列宽，并嵌入 8 张图。
- R1–R7 参考值与复现值在 metrics 中严格分栏；没有发现把研报数值硬编码为复现结果的路径。
- CPU RSS 与 GPU/设备显存没有互相冒充；CPU RSS 行明确标注为累计进程口径，CPU 模式下未伪造 GPU 显存。

失败项：

- `comparison.json` 不满足 v2 统一字段合同，且遗漏 R1–R3 与完整定性表，见 CA-A02。
- Excel 中与图表同 sheet 的表并非图表实际使用的数据，见 CA-A06。
- 分组高低组图未显式绑定高组蓝、低组红，违反项目通用配色约定，见 CA-A09。
- 成功 run log 使用 `exit_code: 0`，而门禁要求可检索的 `exit=0`，见 CA-A03。

### 5. 公开接口、覆盖矩阵与回归风险

通过项：

- 当前审计范围内未发现 `TODO`、空 `pass` 或 `NotImplementedError` 形式的未实现占位。
- m5 以新增输出配置、报告模块和主流程编排为主；未发现 m5 为通过输出而直接篡改 m1–m4 已有核心公式或默认参数。
- R4–R7 的复现值来自实际聚合对象，动态取值不会随研报参考值变化而被覆盖。

失败项：

- m5 新增的多个公开函数和 R2–R7 参考配置字段没有逐项回映 coverage matrix，见 CA-A07。
- comparison 结构与 run log 字面格式都会造成下游验证/门禁回归，见 CA-A02、CA-A03。

## 三、问题清单

### CA-A01 — critical — R3/SA2 使用未登记的 Pearson 模型相关口径

- 证据：`src/r002_liquid_neural_networks/config.py:230` 将 `factor_correlation_method` 固定为 `pearson`；`common/ml_portfolio.py:219-227` 按该方法计算模型间相关矩阵。
- 对照：`workspace/r002_liquid_neural_networks/spec/spec.md:256-266` 只要求“相关系数”；A12 未决议 Pearson/Spearman，AS8 仅登记 RankIC 使用 Spearman，未覆盖模型相关矩阵。
- 影响：R3/SA2 是核心结果，Pearson 与 Spearman 对异常值、非线性单调关系的结果可能显著不同；这是会改变结论的未声明核心口径。
- 修正要求：在歧义/假设中明确相关方法、缺失值与成对样本处理规则及影响，再由获准口径驱动实现；不得仅以代码默认值替代研究决议。

### CA-A02 — critical — `comparison.json` 未履行 v2 字段与覆盖合同

- 证据：`src/r002_liquid_neural_networks/main.py:250-281` 仅输出 `report_id/reproduction_mode/meta/metrics/overall_verdict`；单项仅含 `key/source_element/model/portfolio/period/metric/report_value/reproduced_value/absolute_deviation/verdict`。
- 对照：`docs/specs/2026-07-07-reproduce-v2-design.md:507-509` 要求每项包含 `key/name/report_value/reproduced_value/rel_dev/direction_match/tolerance_key/source_page/source_element/layer/pass`，并包含 `qualitative`、`overall_pass`、`pass_count`、`total`。
- 缺失：R1–R3 没有进入 comparison；R4–R7 单项缺 `name`、相对偏差、方向一致、容差键、页码、层级、布尔通过状态；没有完整定性表和通过计数。
- 额外错误：名为 `absolute_deviation` 的字段实际保存 `reproduced_value - report_value` 的有符号差值，而非绝对值。
- 影响：验证器无法按统一合同逐项判定、统计和追溯，且会遗漏 R 表中的关键项目。
- 修正要求：按统一合同输出 R1–R7 及适用 SA 定性项；绝对偏差与有符号偏差分名存储；所有 pass/overall 字段由标准容差计算，不得由展示 verdict 替代。

### CA-A03 — critical — 成功运行日志与硬门禁不兼容

- 证据：`src/r002_liquid_neural_networks/main.py:457-467` 成功时写 `- exit_code: 0`。
- 对照：`tools/check_gates.py:1074-1076` 对 run log 检索的是字面量 `exit=0`。
- 影响：即便正式运行完全成功，G-VF-1 仍会固定失败，导致管线无法从 verify 正常过门。
- 修正要求：成功日志必须包含门禁合同要求的精确 `exit=0`，同时保留易读说明；失败分支也应使用一致的机器可读字段。

### CA-A04 — major — AS17 展示抽样污染正式特征重要性指标

- 证据：`src/r002_liquid_neural_networks/config.py:295` 将特征重要性样本量设为 64；`main.py:242-247` 取排序后前 64 个 backtest 样本；`main.py:355-364` 计算梯度重要性；`common/ml_reporting.py:265-270` 将其写入正式 `metrics["prediction_evaluation"]["feature_importance"]`。
- 对照：`assumptions.md:195-202` 的 AS17 规定 m5 指标使用完整样本，抽样只用于展示且不得影响 metrics/comparison；`common/ml_pipeline.py:654` 的样本按 split/date/stock 排序，因此“前 64 条”存在明显时间与截面偏置。
- 影响：正式 metrics 中的特征重要性并非完整样本统计，且抽样方法/样本量未登记。
- 修正要求：以可分批累计的完整样本计算正式重要性；若计算近似确属必要，须先登记方法、随机种子、代表性与误差边界，并不得继续宣称 AS17 完整样本口径。

### CA-A05 — major — 分组累计收益图违反路径优先聚合

- 证据：`common/ml_reporting.py:381-389` 先按日对路径收益取均值，再对均值收益复利成累计收益。
- 对照：AS3/AS16 要求先在每条路径上形成组合净值/指标，再对路径直接聚合。
- 反例：路径 0 两日净值为 1.10、1.21，路径 1 仅第二日出现且净值为 1.20；当前算法第二日得到 1.265，而有效路径净值直接均值应为 1.205。
- 影响：必需的分组累计收益图可能显著高估或低估真实路径聚合表现，虽不污染 R4–R7 数值，但会形成错误视觉证据。
- 修正要求：先按模型/路径/组计算逐路径净值，再按日期对有效路径净值等权；不得先平均收益再复利。

### CA-A06 — major — Excel 嵌图与同 sheet 数据不是实际绘图数据

- 证据：`common/ml_reporting.py:509-534` 的 RankIC sheet 保存原始日度路径序列，而图使用 `create_ml_charts:362-371` 的月度路径等权聚合；十分档 sheet 保存全期组指标，而图使用 `381-390` 的日度累计序列；预测散点 sheet 使用前 50,000 行，而图使用 `413-417` 的固定种子随机样本。
- 对照：AGENTS.md 要求“结果图表与对应数据放同一 sheet”。
- 影响：审阅者无法用图所在 sheet 的数据原样复算图，图表与证据表失配。
- 修正要求：绘图数据只构造一次，并将完全相同的数据帧同时传给绘图和 Excel；原始明细可另放 sheet/Parquet，但不能冒充对应绘图数据。

### CA-A07 — major — m5 公开实现未全部回映 coverage matrix

- 证据：coverage matrix 的 m5 done 行只回映 `build_ml_metrics`、`create_ml_charts`、`write_backtest_workbook`、`_resource_row` 和 `M5ReferenceConfig` 的局部用途。
- 缺口：`src/r002_liquid_neural_networks/main.py:284` 的公开 `run_pipeline`、`main.py:480` 的公开 `main`；`common/ml_reporting.py:50` 的 `write_json`、`:62` 的 `calculate_gradient_feature_importance`、`:136` 的 `build_report_reference_tables`、`:571` 的 `write_detail_tables` 均无逐项回映；`M5ReferenceConfig` 中 R2–R7 的参考字段也未被覆盖矩阵对应行定位。
- 影响：公开入口、参考值来源和关键产物写出函数无法从要素矩阵完整反查，违反公开函数全部回映要求。
- 修正要求：对所有 m5 新增公开函数和 R1–R7 参考字段逐一补齐要素、文件、符号/行号映射；纯工具函数若不承担需求也应在矩阵中明确其支撑关系，而非省略。

### CA-A08 — major — GPU/MPS 资源行是累计且顺序相关的非隔离值

- 证据：`common/ml_training.py:375-380` 在训练当前模型前才重置 CUDA peak；主流程 `src/r002_liquid_neural_networks/main.py:312-343` 将此前所有模型继续保留在 `artifacts` 中。`ml_training.py:332-337` 记录 CUDA 最大分配或 MPS 当前分配，因而后续模型行包含此前模型的常驻显存影响。
- 对照：CPU RSS 在 `main.py:212-239` 明确标注为进程累计、非模型隔离口径；GPU/MPS 没有同等披露，资源图却按五模型并排列示。
- 影响：模型之间的资源占用比较依赖运行顺序，不能解释为各模型独立显存占用；虽未复制研报值，但实测证据具有误导性。
- 修正要求：每个模型测量前释放/迁移此前模型并同步设备，或记录模型前基线与增量；若保留累计口径，必须在 metrics、Excel、图标题和 comparison 中明确标注其进程累计和顺序依赖性质。

### CA-A09 — minor — 分组图未落实高组蓝、低组红配色

- 证据：`common/ml_reporting.py:381-400` 的分组累计收益图使用 seaborn 默认 hue 配色，没有将高因子组绑定 `#1f77b4`、低因子组绑定 `#d62728`。
- 对照：AGENTS.md 的通用配色要求高因子组用蓝色、低因子组用红色。
- 影响：不影响数值，但违反统一视觉语义，且降低跨图阅读一致性。
- 修正要求：显式传入组别到颜色的 palette 映射，确保高低组颜色固定。

## 四、结论

- critical：3
- major：5
- minor：1
- 已确认通过的核心点：正式默认五模型/20 路径/100 epoch 上限；CLI 扰动不改源码；研报值与复现值分离；R4–R7 取值来自 20 路径逐路径指标聚合；完整 Parquet 未被展示行数截断；8 图均标注“复现生成—非原图复刻”；未发现复制研报值、CPU 冒充 GPU 显存或 m5 直接篡改 m1–m4 核心参数。
- 不能通过的决定性原因：R3 核心统计口径未登记、comparison 合同不完整、成功日志无法通过硬门禁；此外 AS17、路径聚合、Excel 证据对应、公开回映和 GPU/MPS 资源隔离仍存在 major 缺陷。

verdict: fail

## 五、第 1 次定向复审（repair1）

- 复审模式：`code`
- 复审范围：修复后的 `main.py`、`config.py` m5 段、`common/ml_reporting.py`、AS17–AS18、A13、coverage matrix，以及上述 CA-A01–CA-A09 原问题
- 复审原则：保留上文原问题及首次审计结论作为历史记录；本节给出修复后当前状态
- 临时验证：执行了定向合成 smoke；仅在系统临时目录生成测试产物，运行结束后已清理；未运行正式全量回测
- 未修改事项：未修改实现、coverage matrix、assumptions、ambiguities 或 `state.json`

### 5.1 CA-A01–CA-A09 逐条复核表

| 原问题 | 复核状态 | 修复后证据与独立核对结果 |
|---|---|---|
| CA-A01 | closed | A13 已在 `ambiguities.md:123-131` 以 major-auto 方式裁决，AS18 已在 `assumptions.md:207-217` 登记 Pearson、pairwise complete、每对至少 30 个共同样本、两侧至少 2 个不同值及无效原因。`common/ml_reporting.py:121-212` 只生成 5 模型的 10 个无序对，对非有限值成对删除；常数、样本不足和非有限结果分别标记。定向 smoke 验证：10 对均唯一；GRU 缺 1 条时相关模型对 `n_common=34`、其余为 35；29 条样本全部进入 `insufficient_common_samples`；常数模型相关对全部进入 `constant_prediction`；输出含 `corr/n_common/method/sample_scope/status` 字段。R3 区间只从 `status=valid` 的无序对 `corr` 取最小/最大值（`:215-222`）。 |
| CA-A02 | closed | `src/r002_liquid_neural_networks/main.py:298-507` 现按统一合同生成 comparison。定向 smoke 验证共有 49 个唯一 metric key：R1 2 项、R2 5 项、R3 2 项、R4–R7 的 20 个模型/组合/期间行各含年化收益和夏普共 40 项；每项均含 `key/name/report_value/reproduced_value/rel_dev/direction_match/tolerance_key/source_page/source_element/layer/pass`，另保留核验分级和假设链接。4 个 qualitative 均在位；7 个 unverifiable 项计入 `waived_count`，不进入达标分母，`total=46` 与 `pass_count/overall_pass` 一致。`absolute_deviation` 已取绝对值，`signed_deviation` 单独保存。生产侧 pass 来自登记的 `verification_level`；最终仍由 `tools/check_gates.py:1105-1124` 按 standards/核验分级重算，不信任文件内 pass。 |
| CA-A03 | closed | 成功分支 `main.py:738-750` 明确写入精确字面量 `exit=0`，失败分支 `main.py:762-780` 明确写入 `exit=1`；同时保留 `exit_code: 0/1` 人读字段，已与 `tools/check_gates.py:1075-1076` 对齐。 |
| CA-A04 | closed | `common/ml_reporting.py:62-118` 按固定 `batch_size` 从 0 到 `len(dataset)` 分批遍历完整 backtest dataset，累计所有时点/样本绝对输入梯度；每行输出 `sample_count=len(dataset)`、`full_dataset=True`。`main.py:591-596` 传入完整 `prepared.dataset(backtest_split)`，不再取前 64 条。定向 smoke 用 7 条计数型 dataset、batch 3，确认索引 0–6 各访问一次且所有重要性行 `sample_count=7`。 |
| CA-A05 | closed | `common/ml_reporting.py:467-473` 直接从 m4 的逐路径 `path_nav` 对当日有效路径 NAV 算术平均，再计算 `cumulative_return=nav-1`，不再平均日收益后复利。定向反例得到第二日 `(1.21+1.20)/2=1.205`，与 AS3/AS16 路径先行口径一致。 |
| CA-A06 | closed | `common/ml_reporting.py:446-511` 一次构造唯一的 8 个 `chart_data` DataFrame；`main.py:665-693` 将同一对象传给 8 PNG 和 chart_data Parquet，`main.py:724-736` 再把同一对象传入 Excel。`write_backtest_workbook:690-727` 为每张图创建独立“图数据”sheet且禁止静默截断，`write_detail_tables:784-789` 原样写出对应 Parquet。定向 smoke 实际生成 8 PNG，并逐一验证 Excel 图数据 sheet、内存 chart_data、chart_data Parquet 的行数和列顺序一致；完整原始明细仍由 `write_detail_tables:757-783` 另存 Parquet。 |
| CA-A07 | closed | coverage matrix m5 done 行 `:34-43` 已回映 `run_pipeline`、`main`、`write_json`、`calculate_gradient_feature_importance`、`calculate_model_factor_correlation`、`build_report_reference_tables`、`build_ml_metrics`、`build_ml_chart_data`、`create_ml_charts`、`write_backtest_workbook`、`write_detail_tables` 等全部 m5 公开函数。R1 的文学范围、R2 的资源基准、R3 的范围/方法/样本范围/最小样本、R4–R7 的 `report_performance` 配置也均有要素级回映。 |
| CA-A08 | closed | `main.py:75-109` 新增设备同步、此前模型迁 CPU、清缓存及设备 baseline；`main.py:540-579` 在每个模型训练前执行该隔离步骤。`main.py:251-295` 同时记录设备 baseline、测量值、增量、测量方法与 scope；CUDA 是 baseline 之上的 max allocated 增量，MPS 明确披露为训练后 current allocated 增量而非真实 peak，CPU 明确为累计进程 `ru_maxrss`、非模型隔离峰值。图标题 `common/ml_reporting.py:630-645` 也区分设备增量与无设备值时的累计 CPU RSS，未伪造 CPU GPU 显存。 |
| CA-A09 | closed | `common/ml_reporting.py:556-568` 显式固定 `{1: #1f77b4, 5: #7f7f7f, 10: #d62728}`，高组蓝、低组红，不再依赖 seaborn 默认 hue 顺序。 |

### 5.2 其他强制复核项

| 检查项 | 结论 | 证据 |
|---|---|---|
| R1–R7/SA1–SA3 原通过项 | pass | 默认正式入口仍为完整本地样本、五模型、20 路径、100 epoch 上限；研报值与复现值继续分栏；R4–R7 仍从 m4 `path_metric_aggregate` 取全期/2024、多头/多空逐路径指标聚合；20 路径 RankIC、完整 Parquet、8 图的“复现生成—非原图复刻”边界均未回退。 |
| AS17 | pass | FI 已改为完整 backtest 分批遍历；只有预测散点和普通 Excel 原始明细执行确定性展示限制，8 个唯一 chart_data 不再二次抽样，完整明细另存 Parquet。 |
| AS18/A13 | pass | Pearson、10 个无序对、pairwise complete、min 30、常数/不足样本状态和 `corr` 字段均通过静态与动态核对。 |
| comparison 合同 | pass | 定向 smoke 得到 49 metrics、4 qualitative、`total=46`、`waived_count=7`；字段、计数、绝对/有符号偏差命名与 standards 重算来源均一致。 |
| m4 接口回归 | pass | m5 仍通过既有 `assemble_m4_prediction_panel`、`run_m4_backtest` 和 `MLPortfolioResult` 的 `factor_panel/path_nav/path_metric_aggregate/rank_ic_*` 等公开结果表组装输出；定向导入和 chart/metrics 适配未发现签名或字段回归，m4 的路径先行指标没有被 m5 重算覆盖。 |
| GPU/MPS/CPU 资源口径 | pass | 此前模型迁 CPU、同步、清缓存、baseline/观测值/增量及方法说明均在位；MPS 非真实 peak 的限制与 CPU 累计口径均透明披露。 |
| 高低组配色 | pass | 组 1 蓝、组 10 红、组 5 灰的显式 palette 已生效。 |
| `is_sparse_wiring` 稳定枚举 | fail | 液态模型行可映射为 `sparse/dense`，但 GRU 上游没有该字段，真实五模型 concat 后 GRU 为缺失；见 CA-A10。 |

### 5.3 新增问题

#### CA-A10 — minor — GRU 行的 `is_sparse_wiring` 未形成稳定 `sparse/dense` 枚举

- 证据：`src/r002_liquid_neural_networks/strategy.py:425-440` 的 GRU metadata 没有 `is_sparse_wiring`；`:490-491` 的 GRU resource summary 只含训练资源。液态模型才从 `common/ml_liquid.py:240-271` 带入布尔字段。五模型在 `main.py:581-590` concat 后，GRU 的该列为缺失。
- 触发位置：`common/ml_reporting.py:495-501` 仅把 `True` 映射为 `sparse`、`False` 映射为 `dense`，不会处理缺失值。定向验证 `[NaN, False, True]` 的实际映射结果为 `[NaN, "dense", "sparse"]`。
- 影响：资源 chart_data、Excel 图数据 sheet 和 chart_data Parquet 虽能保持同源，但 GRU 行为空值，未满足所有五模型均为稳定 `sparse/dense` 文本枚举的要求；下游仍可能将该列推断为可空/混合类型。
- 修正要求：在资源表进入 `build_ml_chart_data` 前为 GRU 明确赋予约定枚举，或在映射处对缺失值作显式、经规格认可的归类；按本次要求应确保最终五行都只出现 `sparse` 或 `dense`，并再次验证 Excel 与 Parquet 往返无类型漂移。

### 5.4 当前结论

- 原 CA-A01–CA-A09：全部关闭。
- 当前 open issue：critical 0、major 0、minor 1（CA-A10）。
- 除 `is_sparse_wiring` 的 GRU 空值外，本次要求的相关口径、comparison 合同、日志门禁、FI 全样本、路径 NAV、8 图/Excel/Parquet 单源、公开回映、设备资源口径、配色以及 m4 接口均通过复核。

verdict: fail

## 六、第 2 次定向复审（仅 CA-A10）

- 复审范围：仅核对修复后的 `common/ml_reporting.py:495-512` 资源枚举逻辑与 CA-A10；CA-A01–CA-A09 保持 `closed`，未重新打开。
- 验证方式：独立构造包含五个约定模型的最小资源表；GRU 为缺失值，LTC/CFC 为 `False`，两类 NCP 为 `True`；另分别注入液态缺失、字符串非布尔和整数非布尔值。执行最小 Excel/Parquet 往返，临时目录及脚本均已清理。
- 未修改事项：未修改实现、coverage matrix、assumptions、ambiguities 或 `state.json`。

### 6.1 CA-A10 复核表

| 检查项 | 预期 | 实际结果 | 结论 |
|---|---|---|---|
| 五模型正常枚举 | GRU/LTC/CFC=`dense`；NCP（LTC）/NCP（CFC）=`sparse` | `common/ml_reporting.py:497-512` 校验模型全集及唯一性，允许且仅允许 GRU 缺失，再填充为 `False`；定向结果严格为 `GRU=dense, LTC=dense, NCP（LTC）=sparse, CFC=dense, NCP（CFC）=sparse` | pass |
| Excel 往返 | 五行枚举值和模型映射不漂移 | 写入并重新读取 Excel 后五行映射与内存结果完全一致，只有稳定文本 `dense/sparse` | pass |
| Parquet 往返 | 五行枚举值和模型映射不漂移 | 写入并重新读取 Parquet 后五行映射与内存结果完全一致，只有稳定文本 `dense/sparse` | pass |
| 液态模型缺失 | 显式抛错，不得静默归为 dense | 将 LTC 设为缺失后抛出 `ValueError: 液态模型缺少 is_sparse_wiring: ['LTC']` | pass |
| 字符串非布尔 | 显式抛错 | 将 CFC 设为 `"not_bool"` 后抛出 `ValueError: is_sparse_wiring 只允许布尔值或 GRU 缺失值` | pass |
| 整数非布尔 | 显式抛错 | 将 CFC 设为整数 `1` 后未抛错，被接受并映射为 `sparse` | fail |

### 6.2 CA-A10 当前状态

- 状态：`open`（minor）。
- 已修复部分：GRU 缺失值已被明确限定并归为 `dense`；普通液态和两类 NCP 的正常布尔输入映射正确；Excel/Parquet 往返无文本类型漂移；液态缺失和字符串非布尔输入均会报错。
- 剩余缺陷：`common/ml_reporting.py:507-511` 使用 `sparse_wiring.isin([True, False])` 和布尔键映射。Python/Pandas 中整数 `1/0` 与 `True/False` 等值，因此整数非布尔输入不会进入 `invalid_wiring`，并会被错误映射为 `sparse/dense`。
- 修正要求：在 `isin` 前对每个非缺失值做严格类型判定，例如只接受 Python `bool` 或 `numpy.bool_`；不得接受整数、浮点数或其他与布尔值等值的对象。修复后应至少复测 `1`、`0`、`1.0`、`0.0` 和字符串输入均抛错，同时保持五模型正常枚举及 Excel/Parquet 往返一致。

### 6.3 当前结论

- CA-A01–CA-A09：保持 `closed`。
- CA-A10：仍有 1 个 open minor，未满足“液态非布尔值一律抛错”的完整要求。
- 当前 open issue：critical 0、major 0、minor 1。

verdict: fail

## 七、第 3 次定向复审（仅 CA-A10 严格类型）

- 复审范围：仅核对修复后的 `common/ml_reporting.py:495-516` 严格类型校验；CA-A01–CA-A09 保持 `closed`。
- 验证方式：独立构造五模型资源表，分别注入 Python `bool`、`numpy.bool_`、`int`、`str`、`float`、GRU 缺失值和液态模型缺失值；执行最小 Excel/Parquet 往返。临时目录及脚本均已清理。
- 未修改事项：未修改实现、coverage matrix、assumptions、ambiguities 或 `state.json`。

### 7.1 CA-A10 严格类型复核表

| 检查项 | 预期 | 独立测试结果 | 结论 |
|---|---|---|---|
| Python `bool` | 接受并按值映射 | `False→dense`、`True→sparse` | pass |
| `numpy.bool_` | 接受并按值映射 | `np.bool_(False)→dense`、`np.bool_(True)→sparse` | pass |
| 整数 `0/1` | 一律拒绝 | `0`、`1` 均抛出 `ValueError: is_sparse_wiring 只允许布尔值或 GRU 缺失值` | pass |
| 字符串 | 一律拒绝 | `"true"` 抛出相同 `ValueError` | pass |
| 浮点数 | 一律拒绝 | `0.0`、`1.0` 均抛出相同 `ValueError` | pass |
| GRU 缺失值 | 唯一允许缺失并映射为 `dense` | GRU `NaN→dense` | pass |
| 液态模型缺失值 | 显式拒绝 | LTC `NaN` 抛出 `ValueError: 液态模型缺少 is_sparse_wiring: ['LTC']` | pass |
| 五模型最终枚举 | GRU/LTC/CFC=`dense`，两类 NCP=`sparse` | 得到 `GRU=dense, LTC=dense, NCP（LTC）=sparse, CFC=dense, NCP（CFC）=sparse` | pass |
| Excel 往返 | 模型—枚举映射和文本类型稳定 | 重新读取后五行映射与内存结果完全一致 | pass |
| Parquet 往返 | 模型—枚举映射和文本类型稳定 | 重新读取后五行映射与内存结果完全一致 | pass |

### 7.2 CA-A10 关闭依据

- `common/ml_reporting.py:507-513` 现在逐值使用 `isinstance(value, (bool, np.bool_))` 做严格类型判断，不再依赖会把 `0/1` 与 `False/True` 等值处理的 `Series.isin`。
- `common/ml_reporting.py:502-506` 只允许 GRU 缺失；任何液态模型缺失均显式报错。
- `common/ml_reporting.py:514-516` 在严格校验通过后才把 GRU 缺失填为 `False` 并映射为稳定文本枚举。
- 静态实现与动态边界测试一致，上一轮发现的整数/浮点等值绕过已消失。

### 7.3 当前结论

- CA-A01–CA-A09：保持 `closed`。
- CA-A10：`closed`。
- 当前 open issue：critical 0、major 0、minor 0。
- m5 本轮 code 审计无遗留 open issue。

verdict: pass
