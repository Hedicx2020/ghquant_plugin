# m2 第一阶段市场风险状态模型独立代码审计

- 审计模式: code
- 案例: `r003_equity_factor_timing_cn`
- milestone: `m2`
- 审计输入: `plan.md`、`spec/spec.md`、`spec/coverage_matrix.md`、`assumptions.md` 中 AS38/AS39、`src/r003_equity_factor_timing_cn/regime_model.py` 及 m1 公开入口
- 独立性: 未读取或采信 coder 完成汇报；代码定位、依赖状态、真实 m1 面板运行和全部关键计数均由审计者独立检查

## 一、结论

m2 当前未通过代码门禁。固定84个月滚动窗、三类中心稳定命名、`X_t -> regime_{t+1}`、五折 `TimeSeriesSplit`、折内预处理/过采样、四组中国市场特征、指标表、混淆矩阵和参数哈希均有真实实现，系统 Python 下也能消费真实 m1 面板并完成33个滚动预测月。

但核心 Stacking 实现不忠实：RF/SVC/GNB 在已采样训练集上拟合后，又对同一训练集生成 in-sample 概率，Logistic 直接用这些概率和同批标签拟合，并未使用一级模型的 out-of-fold 预测。该路径使二级学习器看见一级模型对同一样本拟合后的预测，违反 F4、R2、SA1 和计划中“时序验证避免泄漏”的核心要求。另有正式项目 `uv run python` 环境缺少 `scikit-learn`，因此当前项目标准运行路径不能导入 m2；计划要求的肘部法数据/图也没有任何实现合同。

## 二、独立运行与关键数值重算

### 2.1 真实 m1 面板运行

审计者从 m1 公开入口独立构造中国市场月度面板，再用系统 Python 直接调用 `run_stage_one_regime_model`，未写入任何结果文件。重算结果如下：

| 检查项 | 独立结果 | 判定 |
| --- | ---: | --- |
| m1 `monthly_features` | 132行 × 39列 | 可被m2公开接口消费 |
| m2滚动预测 | 33行 × 8列 | 覆盖2023-04-28至2025-12-31 |
| 每月训练目标行数 | 全部84 | 通过 |
| `train_target_end < prediction_date` | 33/33 | 通过 |
| `train_feature_end < prediction_date` | 33/33 | 通过 |
| 五折指标行 | 165=33×5 | 通过 |
| CV逐月预测明细 | 2,310行 | 通过 |
| 首窗五折训练/验证行数 | 14/14、28/14、42/14、56/14、70/14 | 符合`TimeSeriesSplit(5)` |
| 三中心顺序 | 33/33均为Normal中心≥Correction中心≥Bear中心 | 通过 |
| 四组特征重要性 | 136行；四组名称完整 | 通过 |
| 概率行和最大偏差 | `2.220446049250313e-16` | 通过 |
| 参数哈希 | `46b63dd6246a1c07355a14165569193523b374cc58c93be7799415ff12d303e8` | 64位且滚动期内唯一 |

首个滚动预测严格使用2023-03-31特征预测2023-04-28状态；真实运行没有发现84月窗口长度、预测月提前进入训练集或概率不归一的问题。该成功仅证明代码在系统 Python 中可运行，不代表项目 `uv` 环境可运行，也不消除 Stacking 二级训练泄漏。

### 2.2 项目环境反查

- `UV_CACHE_DIR=/private/tmp/report_reproduce_uv_cache uv run python -c 'import sklearn'` 使用 `/Users/hedi/report_reproduce/.venv/bin/python3`，实际报 `ModuleNotFoundError: No module named 'sklearn'`。
- 系统 `/opt/homebrew/opt/python@3.13/bin/python3.13` 可导入 `scikit-learn 1.8.0`，因此上述真实运行采用系统 Python。
- `pyproject.toml:21-27` 仅在可选 extra `ml` 中声明 `scikit-learn`；当前项目环境未同步该 extra。

## 三、coverage_matrix m2全部done行逐条核对

| 要素 | 矩阵实现位置 | 公式/参数核对 | 位置真实性 | 审计结论 |
| --- | --- | --- | --- | --- |
| F2 | `fit_market_regimes` | 固定K=3、欧氏K-Means、seed=42、n_init=20；但无肘部法候选K/inertia输出 | 函数存在且非空壳 | major issue CA-A03 |
| F3 | `fit_market_regimes` | 按回撤中心从高到低固定映射Normal/Correction/Bear | 函数存在且真实调用 | pass |
| F4 | `fit_stacking_classifier` | RF/SVC/GNB与Logistic均存在；Logistic收到同批训练样本的in-sample一级预测，不是OOF预测 | 函数存在但核心训练公式不忠实 | critical issue CA-A01 |
| F5 | `_resample_training_fold` | 标准SMOTE可用时调用；否则按AS39做确定性近邻插值，单样本复制 | 函数存在且只由训练数据调用 | pass |
| F7 | `calculate_feature_importance` | RF底层重要性按AS38四组求和后归一 | 函数存在且真实进入结果合同 | pass |
| B8 | `time_series_cross_validate` | 固定五折`TimeSeriesSplit`；每折只把训练索引交给拟合函数 | 函数存在且实际产生165折指标行 | pass，但折内模型继承CA-A01 |
| R1 | `summarize_regime_distribution` | 输出最新训练标签与滚动实际状态的三类数量/占比 | 函数存在且真实进入结果合同 | pass |
| R2 | `time_series_cross_validate` | accuracy、weighted/macro precision/recall和明细均生成 | 函数存在；数值受CA-A01错误Stacking架构影响 | critical issue CA-A01 |
| R3 | `calculate_feature_importance` | 四组中国市场特征重要性及均值/排名均生成 | 函数存在且组名、成员与AS38一致 | pass |
| SA1 | `time_series_cross_validate` | 外层验证索引严格晚于训练索引，验证折不采样 | 函数存在；二级模型训练仍非OOF | critical issue CA-A01 |

未发现 coverage_matrix 指向 `pass`、`TODO`、不存在函数或完全空壳；本轮不触发空壳 `not_found` 判定。矩阵中的 F4、R2、SA1 不应在核心问题修复前维持可信的 `done` 结论，F2的肘部法输出也未完成；因本审计为只读，未改矩阵。

## 四、重点纪律核对

### 4.1 固定84月及时间对齐

- `RegimeModelSettings.train_window_months=84`，`fit_market_regimes` 强制恰收84个无缺失月，见 `regime_model.py:72-75,185-198`。
- 每个预测位置用 `position-84:position` 作为目标窗，用其前移一个月的84行作为特征窗，逐月断言 `feature_period + 1 == target_period`，见 `regime_model.py:570-586`。
- 预测变量固定取 `position-1`，预测当前 `position`，见 `regime_model.py:600-620`。独立真实运行首月为2023-03特征预测2023-04状态。

结论：固定84月、训练严格早于预测及 `X_t -> regime_{t+1}` 均通过。

### 4.2 K=3及中心标签稳定

- 参数验证强制 `n_clusters == 3`，见 `regime_model.py:151-157`。
- 每月K-Means中心按回撤值降序固定映射 `Normal`、`Correction`、`Bear`，见 `regime_model.py:194-212`。
- 真实33个预测窗全部满足 `Normal >= Correction >= Bear`。

结论：三类标签在不同滚动窗之间具有确定性经济语义映射；通过。

### 4.3 五折、预处理与SMOTE边界

- `TimeSeriesSplit(n_splits=5)`，每折训练索引传入 `fit_stacking_classifier`，验证索引只用于 `predict_proba`，见 `regime_model.py:391-415`。
- 中位数插补、标准化及过采样均在每次 `fit_stacking_classifier` 内对调用方传入的训练折拟合，见 `regime_model.py:216-288,334-357`。
- 验证折未进入 `_resample_training_fold`；真实首窗每折验证行恒为14，过采样前训练行依次为14、28、42、56、70。
- AS39所述无`imbalanced-learn`时确定性近邻插值和单样本复制均有对应代码；未发现测试折、预测月或真实标签被采样。

结论：外层五折和折内预处理/采样边界通过；但这不等于内部Stacking的元特征生成合格，后者见CA-A01。

### 4.4 特征组、参数、指标与哈希

- `MODEL_FEATURES`共9项，按权益估值2项、金融湍流1项、金融条件3项、货币政策预期3项分组，与AS38逐项一致，见 `regime_model.py:45-65`。
- RF 500棵、深度4、叶节点最少3、`sqrt`；SVC C=1；Logistic C=1；seed=42，与AS38一致，见 `regime_model.py:68-83,291-313,373-378`。
- 五折指标包含accuracy、weighted/macro precision与recall；另有CV逐行预测和聚合混淆矩阵，见 `regime_model.py:416-455,662-675`。
- 参数哈希纳入设置、状态顺序、特征组、sklearn版本及采样后端，真实运行得到稳定64位SHA-256，见 `regime_model.py:512-523`。

结论：AS38参数和中国市场四组映射一致，指标/哈希合同存在；R2指标因CA-A01而不能作为忠实Stacking结果接受。

## 五、issue清单

### CA-A01

- severity: critical
- 证据定位: `src/r003_equity_factor_timing_cn/regime_model.py:369-378`；`workspace/r003_equity_factor_timing_cn/spec/spec.md:291-299,465-469,689-694`
- 依据: 一级RF/SVC/GNB先在`sampled_x, sampled_y`上拟合，随后立即对同一个`sampled_x`生成`meta_features`并以同一个`sampled_y`拟合Logistic；没有内部时序切分或OOF概率收集。二级学习器看见同样本的in-sample一级预测，违反正确Stacking训练方式和SA1防泄漏目的，R2分类指标也因此不可信。
- 影响要素: F4、R2、SA1；m2核心结果。
- 通过条件: 在每个外层训练折内部再用时序切分生成覆盖该训练集的一级模型OOF概率，Logistic只拟合OOF元特征；最终预测模型可在全部外层训练数据上重训一级模型。所有插补、标准化和过采样仍须限制在各内部训练子折。

### CA-A02

- severity: critical
- 证据定位: `pyproject.toml:21-27`；项目命令 `uv run python -c 'import sklearn'` 实际输出 `ModuleNotFoundError: No module named 'sklearn'`
- 依据: m2模块在导入阶段依赖sklearn，但当前项目`.venv`未安装可选`ml`依赖；标准项目运行路径无法导入实现。系统Python可运行不能替代项目锁定环境的可复现执行。
- 影响要素: m2全部要素及后续调用m2的m3-m5。
- 通过条件: 让项目正式执行/验证命令明确同步并使用ML extra，随后在同一`uv`环境中完成真实m1面板的全量m2运行和重跑一致性检查。

### CA-A03

- severity: major
- 证据定位: `workspace/r003_equity_factor_timing_cn/spec/spec.md:278-283,511-523,674`；`workspace/r003_equity_factor_timing_cn/plan.md:166-170`；`src/r003_equity_factor_timing_cn/regime_model.py:137-148,185-213,542-703`
- 依据: spec要求K由肘部法选择，plan明确要求产出肘部法图；当前实现只固定K=3并返回该次聚类中心，结果合同没有候选K、inertia或肘部曲线数据，源码也没有elbow/inertia计算路径。因此F2实现位置非空，但产出合同不完整。
- 影响要素: F2、R1、EX6。
- 通过条件: 以每个已定义评估口径或明确登记的代表窗口计算候选K的inertia并输出可追溯数据，供肘部法图生成；K=3仍须保持与spec基准一致。

## 六、五维度审计结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | fail | K-Means、状态映射、时间对齐、SMOTE近似通过；Stacking二级训练使用in-sample一级预测，不符合OOF训练 |
| 参数一致 | pass | 84月、K=3、五折、RF/SVC/Logistic参数、seed=42均与plan/AS38一致 |
| 实现位置真实 | pass_with_issues | m2全部done位置存在且非空壳；F2缺肘部法数据合同，F4核心算法虽然存在但不忠实 |
| 代码反查 | fail | 系统Python真实面板可运行33个月；项目`uv`环境缺sklearn，且输出指标继承Stacking泄漏 |
| 简化声明 | pass | AS38四组映射/超参数和AS39确定性近邻插值均有对应实现，未发现未登记的额外核心简化 |

## 七、已检查维度清单

- [x] m2全部done行F2、F3、F4、F5、F7、B8、R1、R2、R3、SA1逐条核对
- [x] 固定84月、训练目标与训练特征严格早于预测月
- [x] K=3及Normal/Correction/Bear按中心稳定对齐
- [x] `X_t -> regime_{t+1}`及最终`X_t -> prediction_{t+1}`无错位
- [x] 五折`TimeSeriesSplit`折序和真实首窗行数独立重算
- [x] 每折插补、标准化和SMOTE近似仅拟合训练折；验证折未采样
- [x] RF/SVC/GNB到Logistic的元特征来源逐行反查，确认不是OOF
- [x] 中国市场四组特征、AS38超参数、AS39近邻插值逐项核对
- [x] accuracy/precision/recall、混淆矩阵、特征重要性与参数哈希合同核对
- [x] 真实m1面板在系统Python独立全量运行；项目`uv`依赖路径独立复核
- [x] 五维度：公式一致、参数一致、实现位置真实、代码反查、简化声明

初审结论: fail

## 八、第1轮修复后复审更新

详细独立证据见`audit/impl_audit_m2_reaudit_round1.md`。本轮未采信coder或verifier通过声明，已在项目`uv run --extra ml --no-sync`环境独立执行可追踪合成试验、默认RF 500棵模型及真实中国市场m1面板。

| 初审问题 | 当前状态 | 独立证据摘要 |
| --- | --- | --- |
| CA-A01 critical：Logistic使用一级in-sample概率 | resolved | 内层五折拟合行14/28/42/56/70分别只预测其后14行；Logistic实际只收70×9 OOF元特征；最后单独用完整84月重训一级模型 |
| CA-A02 critical：项目uv缺sklearn | resolved | 项目`.venv`通过`uv --extra ml --no-sync`导入scikit-learn 1.9.0，并完成默认500棵与真实面板运行 |
| CA-A03 major：缺肘部合同 | resolved | 每个84月窗真实输出K=2至6 inertia、相对下降、训练区间和selected_k；仅K=3选中 |
| 旧verify残留：最新状态误计116月 | resolved | 真实2025-12最新窗Normal 35、Correction 37、Bear 12，合计84、占比和1 |

此前固定84月、训练早于预测、`X_t -> regime_{t+1}`、三中心稳定命名、外层五折、验证折不采样、AS38四组重要性和参数哈希均无回归。m2全部done位置存在且非空壳，本轮无新增issue。

### 第1轮复审五维度

| 维度 | 结论 |
| --- | --- |
| 公式一致 | pass |
| 参数一致 | pass |
| 实现位置真实 | pass |
| 代码反查 | pass |
| 简化声明 | pass |

### 第1轮复审已检查维度

- [x] 严格内层TimeSeriesSplit OOF、覆盖/首行及Logistic输入
- [x] 一级模型完整84月重训并用于目标月
- [x] 最新状态严格84月
- [x] K=2至6 inertia合同
- [x] 项目uv ML环境及真实中国市场m1面板
- [x] 窗口、对齐、采样、重要性、指标和哈希无回归
- [x] m2全部done行与五维度

verdict: pass
