# r007 m3 实现对照审计

- mode: `code`
- milestone: `m3`
- 审计范围: `F9–F19`、`B7`、`B11` 的全部 `done` 行
- 审读边界: 仅依据 plan、spec、assumptions、coverage matrix、指定实现与依赖文件；未读取或采信 coder 完成汇报
- 运行边界: 仅做隔离环境版本/参数核对、合成快照小规模训练和故障注入；未跑正式全期

## 一、当前 milestone 的 done 行逐条核对

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| F9 | `predict_graph_snapshot` 按单一目标、单一锚点冻结的源收益列拟合 `F_i(X;θ)`，预测目标为 OPCL 超额收益 | 250 日、10 日块、complete-case、严格历史训练由 m2 快照和 common 回归批接口共同约束 | `src/r007_cross_market_return_forecasting/model_pipeline.py:129` 存在且非空壳 | 训练、预测、审计、解释值均可沿调用链反查 | AS2/AS5/AS6/AS14 已登记 | 通过，但异常模型完整性见 CA-A02 |
| F10 | `LinearRegression` 对应带截距最小二乘 | plan 2.1 的 5 个显式参数逐项一致 | `src/r007_cross_market_return_forecasting/strategy.py:64` 存在且实例化真实 estimator | coverage 指向真实函数 | 无未登记简化 | 通过 |
| F11 | `Lasso` 对应 L1 正则回归 | 10 个显式参数逐项一致 | 同上 | coverage 指向真实函数 | 主参数未知的降级已登记 AS15 | 通过 |
| F12 | `Ridge` 对应 L2 正则回归 | 8 个显式参数逐项一致 | 同上 | coverage 指向真实函数 | 主参数未知的降级已登记 AS15 | 通过 |
| F13 | `SVR(kernel="rbf")` 对应 RBF ε-SVR | 11 个显式参数逐项一致，`C=1.0`、`epsilon=0.1`、`gamma="scale"` | 同上 | coverage 指向真实函数 | SVM 固定口径已登记 AS15/AS16 | 通过 |
| F14 | `XGBRegressor` 对应梯度提升树回归 | 15 个 plan 显式参数逐项一致，`random_state=42`、`n_jobs=1` | 同上 | coverage 指向真实函数 | 主参数未知的降级已登记 AS15 | 通过 |
| F15 | `LGBMRegressor` 对应 LightGBM 回归 | 20 个显式参数逐项一致，`random_state=42`、`n_jobs=1` | 同上 | coverage 指向真实函数 | 主参数未知的降级已登记 AS15 | 通过 |
| F16 | `RandomForestRegressor` 对应 bootstrap 随机森林回归 | 18 个显式参数逐项一致，`random_state=42`、`n_jobs=1` | 同上 | coverage 指向真实函数 | 主参数未知的降级已登记 AS15 | 通过 |
| F17 | `AdaBoostRegressor` 的基学习器为深度 3 的 `DecisionTreeRegressor` | AdaBoost 4 个参数及基树 2 个显式参数逐项一致，两个对象均 `random_state=42` | 同上 | coverage 指向真实函数 | 主参数未知的降级已登记 AS15 | 通过 |
| F18 | 同一日、同一股、同一方向的八模型预测取算术均值 | 无额外参数；仅八模型全齐时生成 | `src/r007_cross_market_return_forecasting/strategy.py:141` 与 `common/ml_pipeline.py:1096` 均为真实实现 | coverage 指向报告接口，通用逻辑下沉 common | 无未登记简化 | 通过 |
| F19 | 同一日、同一股、同一方向的八模型预测取中位数 | 无额外参数；仅八模型全齐时生成 | 同上 | coverage 指向报告接口，通用逻辑下沉 common | 无未登记简化 | 通过 |
| B7 | 双方向生成器把边界传给目标市场日历块，取实际首/末交易日 | 配置为 `2016-01-01` 至 `2021-12-31`，与“2016 首个交易日至 2021 最后交易日”一致 | `src/r007_cross_market_return_forecasting/model_pipeline.py:353` 存在且非空壳 | coverage 指向真实生成器 | 无未登记简化 | 通过 |
| B11 | 正常路径生成 OLS/LASSO/RIDGE/SVM/XGBoost/LGBM/RF/AdaBoost 加均值/中位数十种输出 | 八基础名称、顺序和两集成名称均集中固化 | coverage 所列两个函数均存在且可运行 | done 行可反查到初始化与集成实现 | A6/A7 降级已登记 AS15/AS16 | 正常路径通过，故障路径见 CA-A02 |

## 二、独立重算与小规模运行记录

### 2.1 依赖版本与锁文件

在不改仓库环境的隔离 Python 3.13.5 进程中，逐包调用运行时断言，独立观测如下：

| 依赖 | plan/config 期望 | 隔离运行观测 | 是否一致 |
| --- | ---: | ---: | --- |
| Python | 3.13.5 | 3.13.5 | 是 |
| numpy | 2.5.1 | 2.5.1 | 是 |
| pandas | 3.0.3 | 3.0.3 | 是 |
| scikit-learn | 1.9.0 | 1.9.0 | 是 |
| lightgbm | 4.6.0 | 4.6.0 | 是 |
| xgboost | 3.0.3 | 3.0.3 | 是 |

`uv.lock` 对 Python≥3.12 分支解析出 numpy 2.5.1、pandas 3.0.3、scikit-learn 1.9.0，并固定 lightgbm 4.6.0、xgboost 3.0.3。运行时逐项精确断言本身有效；默认项目 Python 选择未固化的问题另见 CA-A01。

### 2.2 八模型显式参数与全量快照

独立实例化八个 estimator，把 plan 2.1 的每个显式键逐项对比 `get_params(deep=True)`，差异数为 0。全量参数键计数为：

| 模型 | `get_params(deep=True)` 键数 | plan 显式键核对 |
| --- | ---: | --- |
| OLS | 5 | 0 差异 |
| LASSO | 10 | 0 差异 |
| RIDGE | 8 | 0 差异 |
| SVM | 11 | 0 差异 |
| XGBoost | 40 | 0 差异 |
| LGBM | 20 | 0 差异 |
| RF | 18 | 0 差异 |
| AdaBoost | 17 | 0 差异，含 `estimator__max_depth=3`、`estimator__random_state=42` |

`build_model_configuration_evidence` 生成的版本、八模型 `params_deep` 及两个集成规则可被标准 JSON 严格序列化；AdaBoost 的嵌套基树参数由 deep snapshot 保留。

### 2.3 滚动、缺失、样本阈值与十模型完整性

独立构造 250 个训练交易日、10 个预测交易日、2 个固定特征、1 个有入边目标和 1 个无入边目标：

- 有入边目标训练输入/complete-case 均为 250，训练终点严格早于锚点；10 日共得到 100 行预测，每个日股恰好 8 个基础模型加 2 个集成模型。
- 同一锚点内的 10 个预测日共用相同两个特征，`feature_signature` 固定；模型只拟合一次后沿用至本块全部预测日。
- 无入边目标不产生预测，并为八个基础模型各记录一条 `skipped_no_inbound_edges`。
- 线性、树模型均返回系数或特征重要性；RBF SVM 无原生 `coef_`/`feature_importances_`，接口按约定返回空解释表，不伪造权重。
- 另构造 4 行训练数据，其中 1 行含缺失：complete-case 为 3，`required_training_rows=特征数+1=3`，可拟合；缩成 3 行输入后 complete-case 为 2，明确记录 `skipped_insufficient_training_samples`。
- 2 行预测中 1 行特征缺失时仅产生 1 行预测，审计记录 1 行缺失，不执行填补。
- 把预测日期移入训练期，接口抛出 `AssertionError: 滚动模型训练日期未严格早于预测日期`。
- 删除同一日股的任一基础模型预测后，均值和中位数均不生成，证明集成不会吞掉缺失模型。
- 注入单模型工厂失败后，每个日股仍输出其余 7 个基础模型，且没有两种集成；该完整性缺口见 CA-A02。

## 三、issues

### CA-A01

- severity: major
- location: `pyproject.toml:5`；`src/r007_cross_market_return_forecasting/config.py:276-295`；`workspace/r007_cross_market_return_forecasting/plan.md:129-144`
- evidence: plan/config 把 Python 固定为 3.13.5，但项目只声明 `requires-python = ">=3.10"`，仓库没有 Python 版本选择文件；当前仓库默认执行 `uv run --frozen --extra ml python` 实际选择 Python 3.12.12，运行时断言立即报出 `expected=3.13.5, observed=3.12.12`。只有显式指定隔离 Python 3.13.5 后六项版本断言才全部通过。
- 依据: 精确断言能发现漂移，但当前默认运行入口不能自动取得 plan 固定环境，m3 在标准 `uv run` 路径下不可执行，属于依赖参数落地不完整。
- suggestion: 在仓库级 Python 选择文件或等效项目约束中固定 3.13.5，并以 `uv run --frozen --extra ml` 复测六项断言；保留现有运行时 fail-fast。

### CA-A02

- severity: major
- location: `common/ml_pipeline.py:1036-1093`；`src/r007_cross_market_return_forecasting/model_pipeline.py:235-266`；`workspace/r007_cross_market_return_forecasting/spec/spec.md:370-374`
- evidence: common 接口捕获单模型的任意异常后继续拼接其余模型；snapshot 层仅把状态记为 `partial_model_failure`，随后仍把残缺基础预测追加到输出。独立注入 SVM 工厂失败后，每个合格日股实际留下 7 个基础模型，均值/中位数被正确抑制，但输出仍进入最终预测表。
- 依据: B11 要求逐日逐股十种预测输出；当前代码虽不伪造集成且保留失败审计，却未阻止 7 模型残缺截面流向下游，coverage 的 core `done` 承诺在故障路径不成立。
- suggestion: 对任一基础模型失败的目标/锚点，原子性地删除该目标/锚点全部基础预测，或在 snapshot/正式写盘边界硬断言每个合格日股模型集合恰为八基础加两集成；失败审计继续保留。

## 四、空壳与实现位置核验

- coverage 的 M3 全部 13 条 `done` 行均已逐条定位到真实函数。
- 指定实现内未发现 `pass`、`TODO`、`FIXME`、`NotImplemented` 或省略号空壳。
- 因不存在空壳/不存在的实现位置，本次没有覆盖矩阵状态回退事项。

## 五、已检查维度结论

- [x] 公式一致：F9–F19 与 B7/B11 逐条对照 spec 和调用链。
- [x] 参数一致：六项版本、八模型全部显式参数、SVM 口径、随机种子与 `n_jobs` 独立核对。
- [x] 实现位置真实：M3 全部 `done` 行逐条定位，未发现空壳。
- [x] 代码反查：报告专属与 common 通用接口均反查；`strategy.py` 的版本断言、模型工厂和参数证据接口可回映 plan 2.1、AS15 及 F10–F19/B11，不构成未登记策略逻辑。
- [x] 简化声明：AS2/AS5/AS6/AS14/AS15/AS16 均核对；未发现未登记的模型口径简化。
- [x] 滚动因果性：250 日、严格早于预测、10 日重训/沿用、2016–2021 边界均核对。
- [x] 缺失与审计：complete-case、不填补、无入边、样本不足、预测行缺失均核对。
- [x] 输出完整性：正常路径十模型、集成缺失防吞、权重/重要性接口均核对；发现 CA-A02。

verdict: fail

## 六、第二轮定点复核（2026-07-27）

- 复核范围：仅复核历史 CA-A01、CA-A02 及其相邻回归风险。
- 审读边界：读取最新 `.python-version`、`pyproject.toml`、`uv.lock`、`common/ml_pipeline.py`、m3 的 `model_pipeline.py` / `strategy.py` / `config.py` 及本审计文件；未读取或采信修复者汇报。
- 运行边界：亲自运行两个标准 uv 入口，并以 250 日训练、10 日预测的合成快照执行正常组与单模型失败注入；未运行正式全期。
- 历史保留：上方 `verdict: fail` 为第一轮审计结论，本节给出修复后的独立复核结论。

### 6.1 CA-A01 定点复核

- 修复定位：`.python-version:1` 固定为 `3.13.5`；精确依赖基线仍由 `src/r007_cross_market_return_forecasting/config.py:276-295` 声明，锁文件的 Python≥3.12 分支仍解析为 numpy 2.5.1、pandas 3.0.3、scikit-learn 1.9.0、lightgbm 4.6.0、xgboost 3.0.3。
- 标准入口一：亲自运行 `uv run --no-sync python`，实际 Python 为 3.13.5；`assert_runtime_versions()` 的 Python、numpy、pandas、scikit-learn、lightgbm、xgboost 六行 `version_match` 全为 `True`。
- 标准入口二：亲自运行 `uv run python`，实际 Python 为 3.13.5；同一六项精确版本断言全为 `True`。
- 回归核验：两个入口均直接使用仓库默认 Python 选择，无需 `--python`、隔离环境或手工覆盖；未出现第一轮的 Python 3.12.12 漂移。
- 复核结论：CA-A01 已修复。

### 6.2 CA-A02 定点复核

- 修复定位：`common/ml_pipeline.py:1086-1102` 在任一基础模型失败时把成功同伴改记为 `discarded_peer_model_failure`，统一写入 `transaction_status=rolled_back_model_failure` 与 `failed_models`，并返回 0 预测和空 `fitted_models`；`src/r007_cross_market_return_forecasting/model_pipeline.py:244-251` 再次阻断任何事务失败后的预测或模型对象泄露。
- 独立故障注入：在八模型工厂中仅把 SVM 替换为抛出 `RuntimeError` 的工厂，其余七模型保持正常。
- common 层结果：预测行数为 0；预测接口列保持 `target_date/source_date/model/prediction`；`fitted_models={}`；审计状态恰为 7 条 `discarded_peer_model_failure` 加 1 条 `failed`。
- 事务证据：八条审计记录的 `transaction_status` 均为 `rolled_back_model_failure`，`failed_models` 均为 `SVM`；失败行保留 `model=SVM`、`error_type=RuntimeError`。
- snapshot 层结果：预测行数为 0，`feature_values` 行数为 0，训练状态为 `partial_model_failure`；审计仍恰为 7 条 discarded 加 1 条 failed，事务和失败模型字段未丢失。
- 回归核验：相同合成快照的正常组产生 100 行预测，10 个预测日的每个日股均恰有 8 个基础模型加 2 个集成模型；八条基础模型审计均为 `fitted` 和 `committed_all_base_models`。
- 接口核验：正常组预测列仍为 `direction/anchor_date/target_code/target_date/source_date/model/prediction/actual_return`，与第一轮正常路径一致；两种集成、模型顺序、训练审计和特征解释值均未因事务修复丢失。
- 复核结论：CA-A02 已修复。

### 6.3 第二轮 issues 与已检查维度

- 本轮未发现新增 critical、major 或 minor issue。
- [x] CA-A01：默认 Python 选择、两个标准 uv 入口、六项精确版本断言。
- [x] CA-A02：单模型失败原子回滚、0 预测、空模型对象、0 解释值、7 discarded + 1 failed。
- [x] 事务证据：`transaction_status` 与 `failed_models` 字段及失败模型定位。
- [x] 正常路径回归：八基础加两集成、每个日股 10 模型、预测接口列保持不变。
- [x] 五维度回归：公式一致、参数一致、实现位置真实、代码反查、简化声明均未因本轮修复退化。

verdict: pass

## 七、第三轮 schema 定点复核（2026-07-27）

- 复核范围：仅核新增高层结果 schema、正常/空结果路径一致性及 m4 空表消费回归。
- 审读边界：以最新 `src/r007_cross_market_return_forecasting/model_pipeline.py` 和本审计历史为主；为执行真实下游消费，定点调用 m4 的预测准备与十模型完整性筛选接口。
- 运行边界：亲自构造 250 日训练、10 日预测的正常、无入边、样本不足、SVM 回滚、空预测日期五条路径；未运行正式全期，未修改代码。
- 历史保留：上方第一轮 `fail` 和第二轮 `pass` 均为当时结论，本节给出 schema 修复后的最新独立结论。

### 7.1 四张表统一 schema 与 dtype

五条路径均逐列、逐 dtype 对照 `model_pipeline.py:41-106` 的常量合同，结果完全一致：

| 表 | 固定列数 | 五条路径共同 dtype 结论 | 必需字段 |
| --- | ---: | --- | --- |
| `predictions` | 8 | `direction/target_code/model=string`；三日期列为 `datetime64[ns]`；`prediction/actual_return=float64` | `actual_return` 在全部空表路径也存在 |
| `feature_values` | 11 | 标识列为 `string`，日期为 `datetime64[ns]`，数值为 `float64`，`absolute_rank=int64` | 空解释值仍保留完整 11 列 |
| `model_audit` | 23 | 计数为 `int64`，日期为 `datetime64[ns]`，因果标志为 `boolean`，其余审计字段为 `string` | `transaction_status`、`failed_models` 在全部路径存在 |
| `training_audit` | 16 | 计数为 `int64`，日期为 `datetime64[ns]`，布尔字段为 `boolean`，状态/签名为 `string` | 空预测和跳过路径仍保留完整 16 列 |

`_canonical_frame` 在正常表与空表上均保持固定列顺序；五条路径没有出现 object dtype 漂移、缺列或多余列。

### 7.2 五条独立运行路径

| 路径 | predictions | feature_values | model_audit | training_audit | 关键状态 |
| --- | ---: | ---: | ---: | ---: | --- |
| 正常 | 100 | 14 | 8 | 1 | 每个日股 8 基础+2 集成；8 条 `fitted/committed_all_base_models` |
| 无入边 | 0 | 0 | 8 | 1 | 全部 `skipped_no_inbound_edges` |
| 样本不足 | 0 | 0 | 8 | 1 | 全部 `skipped_insufficient_training_samples` |
| SVM 回滚 | 0 | 0 | 8 | 1 | 7 discarded + 1 failed；全部 `rolled_back_model_failure`、`failed_models=SVM` |
| 空预测日期 | 0 | 0 | 8 | 1 | 全部 `skipped_no_complete_prediction_rows` |

正常组的 `actual_return` 与目标面板逐行完全一致；`ensemble-avg`、`ensemble-med` 分别独立按八基础预测重算均值和中位数，数值逐行一致。因而 schema 规范化没有改变正常预测数值或集成算法。

### 7.3 参数、公开签名与接口回归

- 八模型顺序仍为 OLS/LASSO/RIDGE/SVM/XGBoost/LGBM/RF/AdaBoost。
- `get_params(deep=True)` 键数仍分别为 5/10/8/11/40/20/18/17，与前两轮一致；未发现参数增删或随机性口径变化。
- `predict_graph_snapshot` 的公开参数仍为 `snapshot/source_panel/target_panel/model_factories/config`。
- `iter_snapshot_model_predictions`、`iter_bidirectional_model_predictions`、`summarize_prediction_quality` 的公开参数名和顺序均未变化。
- `SnapshotPredictionResult` 字段仍为 `predictions/training_audit/model_audit/feature_values`。
- `summarize_prediction_quality` 可消费 canonical 空预测表并返回空质量表。

### 7.4 issue

#### CA-A03

- severity: major
- location: `src/r007_cross_market_return_forecasting/model_pipeline.py:407-466`；`src/r007_cross_market_return_forecasting/portfolio_pipeline.py:182-265`
- evidence: 五种 m3 路径均已产出 8 列、含 `actual_return` 的 canonical 空预测表；`prepare_portfolio_predictions` 能把该空表转换为 14 列 m4 空输入，但 `enforce_complete_ten_model_groups` 在空分组结果的 `model_set` 列执行 `audit["model_set"].eq(frozenset(...))` 时，锁定的 pandas 3.0.3 抛出 `NotImplementedError: eq not implemented for <class 'frozenset'>`。
- 依据: 无入边、样本不足、模型事务回滚和空预测日期均是已设计的正常空结果路径；新增 schema 虽修复 m3 四表合同，却未满足本轮明确要求的 m4 空表无异常消费，属于下游集成回归。
- suggestion: 在 m4 十模型完整性筛选中对空输入/空 audit 先返回带固定 schema 的空结果，或确保空 `model_set` 为可与 frozenset 比较的 object dtype；增加五条 m3 空路径到 m4 的集成回归测试。

### 7.5 第三轮已检查维度

- [x] 正常、无入边、样本不足、SVM 回滚、空预测日期五条路径。
- [x] `predictions` 8 列、`feature_values` 11 列、`model_audit` 23 列、`training_audit` 16 列。
- [x] 每条路径的列顺序、dtype、`actual_return`、`transaction_status`、`failed_models`。
- [x] 正常模型数量、实际收益、均值/中位数集成数值。
- [x] 八模型参数快照键数、模型顺序、公开函数签名、结果 dataclass 字段。
- [x] m3 空表质量统计与 m4 真实空表消费；发现 CA-A03。
- [x] 公式、参数、实现位置、代码反查、简化声明未因 schema 修复发生意外变化。

verdict: fail

## 八、scope 纠正附录（2026-07-27）

- 纠正依据：implement 流水线按 milestone 归属审计；issue 应归属于发生缺陷的实现模块和对应下游 milestone，不能因上游产物触发了调用就反记到上游。
- m3 结论：第三轮已独立确认正常、无入边、样本不足、SVM 回滚、空预测日期五条路径的四张表均满足固定 8/11/23/16 列及 dtype 合同；`actual_return`、`transaction_status`、`failed_models` 完整，正常数值、模型参数、模型顺序和公开签名均无意外变化。
- CA-A03 归属纠正：异常实际发生于 m4 的 `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:182-265`，具体为 `enforce_complete_ten_model_groups` 对空 `model_set` 执行 pandas 比较；该问题不是 m3 `model_pipeline.py` 的实现缺陷，不计入 m3 issue 或 m3 verdict。
- 移交：保留第三轮 CA-A03 的原始复核记录作为证据链，issue 移交后续独立 m4 code audit 承接；本附录不修改代码、不写 m4 审计文件。
- m3 最终结论：CA-A01、CA-A02 均已修复，新增 schema 修复及 m3 本体回归全部通过。

verdict: pass
