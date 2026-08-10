# m3 第1轮修复后独立代码复审

- 审计模式: code
- 案例: `r003_equity_factor_timing_cn`
- milestone: `m3`
- 复审轮次: round 1
- 复审重点: CA-A01稀有状态AS40诊断边界及正常真实链路回归
- 独立性: 未采信修复声明；当前代码、三类合法84月边界及真实中国市场m1→m2→m3链路均由审计者独立运行
- 写入边界: 只写审计文档，未改代码、`state.json`或`results/`

## 一、最终结论

CA-A01已修复。当前AS40诊断逻辑在“前72月无某状态、后12月有该状态”时不再崩溃，不拟合诊断模型、不使用验证标签估计先验概率，也不生成伪验证概率；该状态六个因子的train/validation logloss均为NaN，同时保留训练/验证行数、可用性布尔值及`no_state_samples_in_diagnostic_train`原因。诊断留空后，正式模型仍使用完整84月窗内该状态的12个历史样本训练六个RF，并成功输出目标月概率。

反向边界“训练有/验证无”和“两者均空”也按合同返回NaN及原因，不影响存在样本状态的正式模型。真实中国市场2025-12链路与修复前正常路径完全一致：固定84月、m2状态35/49、两状态各六RF、十二项正常诊断损失、概率权重、相关矩阵、频率和重要性均无回归。本轮未发现新增issue，m3可以通过代码门禁。

## 二、CA-A01源码复核

- `_safe_binary_logloss`在标签为空或概率为空时直接返回NaN，见`factor_model.py:348-356`；若两者均非空但长度不同仍抛错，避免把真正的结构错位静默吞掉。
- 每个“状态×因子”先只用前72个日历月中该状态样本拟合`diagnostic`；训练段为空时`_fit_binary_forest`返回`None`，见`factor_model.py:326-345,596-608`。
- `diagnostic=None`时train和validation概率都保持空数组，代码没有读取验证标签比例、胜出频率或其他验证信息构造常数先验，见`factor_model.py:609-618`。
- `diagnostic_available`、`train_logloss_available`、`validation_logloss_available`及`diagnostic_unavailable_reason`逐行进入损失表，见`factor_model.py:619-649`。
- 诊断记录完成后，正式模型另用完整`state_window`拟合，见`factor_model.py:651-655`；诊断训练为空不阻止该状态在完整84月窗有样本时建模。

结论：修复没有以验证标签估计先验或回填概率，而是将不可计算诊断显式留空，再与正式全窗模型解耦。

## 三、原阻断边界独立复现

构造100个连续合成月，目标月之前固定84月状态为前72月Normal、最后12月Correction；当前m2预测设为Bear且`actual_regime=Normal`，要求m3选择Correction正式模型。

### 3.1 前72月无、后12月有

| 检查项 | Correction独立结果 | 结论 |
| --- | ---: | --- |
| diagnostic train rows | 0 | 无历史训练状态样本 |
| diagnostic validation rows | 12 | 验证状态样本存在 |
| `diagnostic_available` | 6/6为false | 未拟合诊断模型 |
| `train_logloss_available` | 6/6为false | 正确 |
| `validation_logloss_available` | 6/6为false | 未用验证标签估先验 |
| train logloss | 6/6为NaN | 正确留空 |
| validation logloss | 6/6为NaN | 正确留空 |
| reason | 6/6为`no_state_samples_in_diagnostic_train` | 留痕完整 |
| 正式状态训练行 | 12 | 使用完整窗历史样本 |
| 正式模型数 | 6 | 六因子全部训练 |
| 目标月状态 | Bear→Correction | 使用修复后的正式模型 |
| 目标月权重和 | 1.0 | 成功输出 |
| 1/N fallback | false | 非诊断回退结果 |

原先的`ValueError: Found array with 0 sample(s)`不再出现。正式输出证明诊断不可计算不会阻断完整窗模型。

### 3.2 训练有、验证无

同一窗口的Normal状态在前72月有72条、最后12月为0条：

- 六个诊断模型均正常拟合；
- train logloss可计算；
- validation logloss六项均为NaN；
- reason六项均为`no_state_samples_in_validation`；
- 正式Normal模型仍为六个。

### 3.3 训练与验证均空

另构造84个月全部Normal、Correction完全不存在的合法状态窗：

- Correction六项train_rows=0、validation_rows=0；
- train/validation logloss各六项均为NaN；
- `diagnostic_available=False`，reason为`no_state_samples_in_diagnostic_train`，同时0/0行数及两个可用性字段明确验证段也为空；
- Correction正式模型数为0，Normal正式模型仍输出目标月权重且权重和为1。

三类边界与初审通过条件全部覆盖。

## 四、不得使用验证标签估计先验

静态与动态证据一致：

- 源码没有`diagnostic_validation`标签均值、类别频率或winner比例进入概率的路径；验证标签只作为有真实诊断概率时的logloss对照标签。
- 训练为空时`validation_probability`固定为空，`_safe_binary_logloss`因概率size=0直接返回NaN。
- 原阻断边界中Correction最后12月包含真实胜出标签，但六个validation logloss全部NaN、`validation_logloss_available=False`，没有任何由验证标签生成的先验概率或损失值。
- 随后正式RF使用完整历史状态样本是AS40明确允许的正式84月重训，不属于诊断验证泄漏；目标月本身仍未进入该`state_window`。

结论：验证标签未参与诊断模型、先验估计或正式目标月之前的伪预测。

## 五、真实中国市场正常链路回归

审计者在项目`uv run --extra ml --no-sync`环境中重新运行真实m1、单目标月m2及正式参数m3，全程内存执行：

| 检查项 | 独立结果 | 回归结论 |
| --- | ---: | --- |
| m1月度特征 | 132×39 | no_regression |
| m1因子收益 | 792×10 | no_regression |
| 目标月/特征日 | 2025-12-31 / 2025-11-28 | no_regression |
| m2预测/m3选择 | Bear / Correction | no_regression |
| 训练候选月 | 84 | no_regression |
| 历史状态来源 | `m2_window_regime_labels` | no_regression |
| 状态缺口 | 0 | no_regression |
| Normal/Correction训练行 | 35 / 49 | no_regression |
| 正式模型数 | 两状态各6 | no_regression |
| 六因子权重和 | 1.0 | no_regression |
| 正常诊断损失 | 12行；train/validation各12项有限 | no_regression |
| 正常诊断可用性 | 12/12为true；非空reason为0 | no_regression |
| 相关矩阵/频率 | 108行 / 18行 | no_regression |
| 两状态组重要性和 | 均为1.0 | no_regression |
| RankIC | -0.6571428571 | no_regression |
| Top命中 | Small-Cap预测、Momentum实际，false | no_regression |
| 参数哈希 | `592eba222d8994aec5457fc4a2ea1881c5efd4f5f32d659bdc993c6d42455ce7` | no_regression |

修复只改变诊断不可计算时的输出契约，正常数据路径的模型、概率和指标未被改写。

## 六、此前通过项回归检查

| 维度 | 复审结果 |
| --- | --- |
| `t`特征→`t+1`收益标签 | no_regression |
| 固定84个连续目标月、训练严格早于目标月 | no_regression |
| 当前状态取m2预测、历史状态取当前m2窗口 | no_regression |
| 目标月`actual_regime`及同月实际收益不参与拟合 | no_regression |
| Bear→Correction | no_regression |
| 两状态×六RF及500/4/3/sqrt/balanced/seed42 | no_regression |
| 概率归一、1/N回退及tie-break | no_regression |
| 三scope相关矩阵与胜出频率 | no_regression |
| 两状态特征重要性、RankIC及Top命中 | no_regression |
| AS40前72/后12日历月划分 | no_regression |

## 七、m3 coverage done行复审

F1、F8-F10、B3-B4、B9、R4-R8、SA2全部实现位置仍存在且非空壳。CA-A01修复后F10正式模型与R8/AS40诊断不再被稀有状态边界阻断；其余done行无回归。未发现公开策略函数缺少要素ID映射或未登记核心简化。

## 八、issue清单

本轮未发现新的critical、major或minor issue。CA-A01已关闭。

## 九、五维度结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | pass | AS40不可计算诊断返回NaN，正式84月模型独立重训；其余m3公式无回归 |
| 参数一致 | pass | 84/12月及RF 500/4/3/sqrt/balanced/seed42保持冻结 |
| 实现位置真实 | pass | m3全部done位置存在、非空壳且真实进入结果合同 |
| 代码反查 | pass | 三类稀有状态边界与真实中国2025-12链路全部独立运行通过 |
| 简化声明 | pass | AS40“稀有状态损失可为空”现与NaN、可用性及reason合同一致 |

## 十、已检查维度清单

- [x] CA-A01原阻断窗：前72月无、后12月有
- [x] 诊断模型不拟合、验证标签不估先验、train/validation损失均NaN
- [x] `diagnostic_available`、两类loss可用性、行数及reason留痕
- [x] 正式完整84月状态样本仍训练六RF并输出目标月概率
- [x] 反向边界：训练有、验证无
- [x] 双空边界：训练与验证均无状态样本
- [x] `_safe_binary_logloss`空输入留NaN、非空长度错位仍报错
- [x] 真实中国m1 132×39、m2状态及2025-12 m3正常链路
- [x] 标签、窗口、状态、参数、概率、相关性、频率、重要性、RankIC、Top命中无回归
- [x] m3全部done行与五维度逐项复审

verdict: pass
