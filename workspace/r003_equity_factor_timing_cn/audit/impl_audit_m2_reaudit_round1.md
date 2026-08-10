# m2 第1轮修复后独立代码复审

- 审计模式: code
- 案例: `r003_equity_factor_timing_cn`
- milestone: `m2`
- 复审轮次: round 1
- 输入: 当前 `regime_model.py`、`audit/m2_fix_round1.md`、当前 `verify_report.md`、plan/spec/AS38/AS39及m2 coverage done行
- 独立性: 修复记录和verify报告仅用于定位待核事项；所有通过结论均由当前源码、可追踪合成面板及真实中国市场m1面板独立重算，不采信完成声明
- 写入边界: 只写审计文档，未改代码、`state.json`或`results/`

## 一、最终结论

第1轮已关闭初审的CA-A01、CA-A02、CA-A03，并修复旧verify报告指出的`latest_training_assignment`误计116个月问题。当前实现使用内层五折`TimeSeriesSplit`生成严格时序OOF一级概率，Logistic只拟合有OOF覆盖的后70行；最前14行因没有更早训练历史而明确排除。元学习器训练完成后，RF/SVC/GNB再以全部84个原始训练月及其训练折内合成样本重训，用于正式目标月预测。

项目`.venv`当前可在`uv run --extra ml --no-sync`下导入并执行scikit-learn 1.9.0。真实中国市场m1面板132×39在该环境完成2025-12完整链路：84月训练、70/84元OOF覆盖、最新状态35/37/12合计84、K=2至6惯量合同完整。此前84月窗口、`X_t -> regime_{t+1}`、外层五折、验证折不采样、四组重要性和参数哈希均无回归。

## 二、CA-A01复核：严格时序OOF与完整84月重训

### 2.1 源码反查

- `regime_model.py:461-487`初始化OOF矩阵，在内层五折`TimeSeriesSplit`中只把`train_index`交给`_fit_base_layer`，随后只对严格更晚的`validation_index`调用`_predict_base_layer`。
- `regime_model.py:488-492`要求OOF有效区无NaN，并要求首个OOF位置以前全部未覆盖、从首个OOF位置起连续覆盖到末行。
- `regime_model.py:493-504`的Logistic拟合输入严格为`oof_meta[oof_mask]`及同一掩码下的标签，源码不再存在用完整训练集in-sample一级概率拟合元学习器的路径。
- `regime_model.py:507-514`在元模型完成后再次调用`_fit_base_layer(features, labels, ...)`；此处`features/labels`是完整调用窗。正式预测使用这一完整窗的预处理器和一级模型，见`regime_model.py:125-134,766-774`。

### 2.2 84行可追踪独立试验

审计者在项目uv ML环境中对84行、9特征、三类循环标签执行带调用追踪的`fit_stacking_classifier`，RF仅在该结构试验中缩为8棵。独立记录如下：

| 内层折 | 一级拟合行号 | 一级预测行号 | 交集 | 时序关系 |
| ---: | --- | --- | --- | --- |
| 1 | 0-13，共14行 | 14-27，共14行 | 0 | 拟合末行13 < 预测首行14 |
| 2 | 0-27，共28行 | 28-41，共14行 | 0 | 拟合末行27 < 预测首行28 |
| 3 | 0-41，共42行 | 42-55，共14行 | 0 | 拟合末行41 < 预测首行42 |
| 4 | 0-55，共56行 | 56-69，共14行 | 0 | 拟合末行55 < 预测首行56 |
| 5 | 0-69，共70行 | 70-83，共14行 | 0 | 拟合末行69 < 预测首行70 |

- Logistic实际收到70行×9列元特征和70个标签。
- `meta_oof_rows=70`、`meta_oof_total_rows=84`、`meta_oof_coverage=5/6`、`meta_oof_first_position=14`。
- 五个内层拟合结束后，追踪到第六次一级拟合为0-83全部84行；这组完整窗模型保存在最终`FittedStackingClassifier`中。
- 同一uv环境再用正式默认RF 500棵执行84行模型，2.376秒完成，最终RF实际含500棵树，OOF仍为70行、首位置14，目标月概率和为1。

结论：CA-A01 resolved。一级模型对每个OOF行均未见过该行；Logistic未接触一级in-sample预测；正式预测使用完整84月重训后的一级模型。

## 三、外层五折、覆盖首行及采样隔离

用88个连续合成月运行3个滚动预测月，每个预测月的外层折合同一致：

| 外层折 | 外层训练行 | 外层验证行 | 内层OOF行 | 内层首个OOF位置 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 14 | 14 | 10 | 4 |
| 2 | 28 | 14 | 20 | 8 |
| 3 | 42 | 14 | 35 | 7 |
| 4 | 56 | 14 | 45 | 11 |
| 5 | 70 | 14 | 55 | 15 |

- 3个预测月合计15个外层折、210条验证明细，逐折验证行始终14。
- 外层验证索引只进入`predict_proba`；每个外层模型的插补、标准化、近邻过采样和内层OOF均只接收外层训练索引。
- `_fit_base_layer`内部先对传入训练子折拟合中位数插补和标准化，再调用`_resample_training_fold`；验证折、预测月和真实标签无采样入口。
- 合成历史中特意放入特征缺失值，完整链路仍只由训练折中位数处理并顺利运行。

结论：外层五折、内层五折和AS39采样边界均通过，无时间泄漏回归。

## 四、真实中国市场uv链路

执行环境为：

- 命令口径: `UV_CACHE_DIR=/private/tmp/report_reproduce_uv_cache uv run --extra ml --no-sync python`
- Python: 项目`.venv/bin/python3`
- scikit-learn: 1.9.0
- pandas: 3.0.3
- numpy: 2.5.1

审计者在该环境用m1公开入口无股票限制重建真实面板，再以RF 8棵运行2025-12单月完整m2；减树仅用于控制代码审计时长，另有前述默认500棵结构试验。

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| m1月度面板 | 132×39，19.672秒 | 真实中国数据可消费 |
| m2目标月 | 2025-12-31 | 通过 |
| 预测特征月 | 2025-11-28 | 严格早于目标月 |
| 训练目标窗 | 2018-12-28至2025-11-28，共84月 | 通过 |
| 训练特征窗 | 2018-11-30至2025-10-31，共84月 | `X_t -> regime_{t+1}`通过 |
| 正式元OOF | 70/84，首位置14 | 通过 |
| 外层折 | 1-5齐全；验证行均14 | 通过 |
| 最新84月状态 | Normal 35、Correction 37、Bear 12 | 合计84、占比和1 |
| 目标月概率和 | 1.0 | 通过 |
| 四组重要性和 | 1.0 | 通过 |
| 参数哈希 | `2c750bc3d4a5f4c82358249be7e4e376748f31683625d05b52385c8763bf37b2` | 64位SHA-256 |

真实状态计数与旧verify报告独立复算的应有值35/37/12完全一致，原116个月滚动并集错误已消除。

## 五、CA-A03及肘部合同复核

- 设置固定`elbow_k_min=2`、`elbow_k_max=6`且强制覆盖选定K=3，见`regime_model.py:72-85,158-168`。
- `calculate_elbow_diagnostics`对每个严格过去84月窗口分别拟合K=2、3、4、5、6，返回训练起止月、inertia、相对下降和`selected_k`，见`regime_model.py:225-265`。
- 3个合成滚动月共得到15行；每月K序列均为`[2,3,4,5,6]`，仅K=3为选中值，inertia随K不增加。
- 真实2025-12窗口的inertia依次为0.0421298384、0.0186023372、0.0084279506、0.0057076911、0.0043755728；仅K=3的`selected_k=True`。
- `StageOneRegimeResult.elbow_diagnostics`及主循环拼接路径真实存在，coverage F2已指向该实现。

结论：CA-A03 resolved。代码已提供肘部图所需逐月底表，固定执行K仍为3，未根据样本外结果改参。

## 六、CA-A02及依赖环境复核

- `uv run --extra ml --no-sync`在当前项目`.venv`实际导入scikit-learn 1.9.0，退出码0。
- 同一环境完成：默认500棵RF的84行OOF模型、3个月合成完整链路、真实m1 132×39面板及真实2025-12 m2完整链路。
- 本复审使用`--no-sync`，没有在审计过程中修改依赖环境；成功来自复审开始前已存在的项目ML环境。

结论：CA-A02 resolved。项目正式ML extra路径当前可执行。

## 七、此前通过项回归检查

| 检查项 | 独立结果 | 结论 |
| --- | --- | --- |
| 固定84月 | 合成3/3、真实1/1训练窗均为84 | no_regression |
| 训练严格早于预测 | 目标窗及特征窗均早于预测月 | no_regression |
| `X_t -> regime_{t+1}` | 特征月始终比目标标签月提前1个月 | no_regression |
| K=3与中心命名 | 固定三类并按中心降序映射Normal/Correction/Bear | no_regression |
| 外层五折 | 折1-5齐全，验证段严格在训练段之后 | no_regression |
| 训练折内采样 | 插补、标准化、SMOTE近似均封装在训练子折 | no_regression |
| 四组中国特征 | 四组名称及9项底层变量与AS38一致 | no_regression |
| 特征重要性 | 合成与真实逐月四组非负、归一化和为1 | no_regression |
| 分类指标/混淆矩阵 | accuracy及weighted/macro precision/recall、明细和矩阵路径仍存在 | no_regression |
| 参数哈希 | 新增OOF与肘部合同标识，真实运行返回稳定64位值 | no_regression |

## 八、m2 coverage done行复审

| 要素 | 实现位置 | 复审结论 |
| --- | --- | --- |
| F2 | `calculate_elbow_diagnostics`、`fit_market_regimes` | K=2至6肘部底表及固定K=3聚类真实实现 |
| F3 | `fit_market_regimes` | 三中心稳定标签映射真实实现 |
| F4 | `fit_stacking_classifier` | RF/SVC/GNB严格OOF概率训练Logistic，完整84月重训一级模型 |
| F5 | `_resample_training_fold` | 仅训练子折SMOTE或AS39近邻插值 |
| F7 | `calculate_feature_importance` | RF底层重要性按四组汇总归一 |
| B8 | `time_series_cross_validate` | 外层固定五折，内层固定五折OOF |
| R1 | `summarize_regime_distribution` | 最新预测月单窗严格84行；滚动OOS另行统计 |
| R2 | `time_series_cross_validate` | OOF架构修复后输出accuracy/precision/recall及明细 |
| R3 | `calculate_feature_importance` | 四组重要性合同完整 |
| SA1 | `time_series_cross_validate` | 双层时序切分、验证折隔离，无同样本in-sample元特征 |

全部位置存在且非空壳，无`pass`/`TODO`虚报或策略公开私货函数。

## 九、issue清单

本轮未发现新的critical、major或minor issue。CA-A01、CA-A02、CA-A03均关闭；旧verify报告的最新状态116月错误也已关闭。

## 十、五维度结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | pass | 内层严格时序OOF、Logistic元学习、完整84月一级重训、K-Means与肘部合同均正确 |
| 参数一致 | pass | 84月、K=3、肘部K=2至6、双层五折、RF/SVC/Logistic参数及seed=42一致 |
| 实现位置真实 | pass | m2全部done位置存在、非空壳且进入主结果合同 |
| 代码反查 | pass | 可追踪合成试验、默认500棵模型及真实中国m1面板均在项目uv ML环境运行通过 |
| 简化声明 | pass | AS38四组映射与超参数、AS39确定性近邻插值均忠实实现，无未登记核心简化 |

## 十一、已检查维度清单

- [x] CA-A01：内层OOF拟合/预测行逐折追踪，交集为0且训练严格早于验证
- [x] OOF覆盖70/84、首个位置14、最前14行未进入Logistic
- [x] Logistic实际拟合70×9 OOF元特征，不接触同样本in-sample一级概率
- [x] 元模型完成后RF/SVC/GNB在完整84月重训并用于正式目标月
- [x] 外层五折各自的内层OOF行数、首位置和验证行数
- [x] 最新训练状态严格来自最大prediction_date对应84行，真实计数35/37/12
- [x] K=2、3、4、5、6 inertia逐月合同与仅K=3选中
- [x] 项目`uv --extra ml --no-sync`导入及默认RF500真实执行
- [x] 真实中国市场m1 132×39面板至2025-12 m2完整链路
- [x] 此前窗口、时点对齐、训练折采样、四组重要性、指标和哈希无回归
- [x] m2全部done行及五维度逐项核对

verdict: pass
