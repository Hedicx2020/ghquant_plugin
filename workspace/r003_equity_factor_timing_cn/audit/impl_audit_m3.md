# m3 第二阶段分状态因子胜出概率模型独立代码审计

- 审计模式: code
- 案例: `r003_equity_factor_timing_cn`
- milestone: `m3`
- 审计输入: plan m3、spec、AS40、coverage m3全部done行、`factor_model.py`、m1/m2公开输出接口及`audit/m3_m2_adaptation.md`
- 独立性: 未读取或采信coder完成汇报；关键日期、窗口、状态来源、模型数、概率、指标及异常边界均由审计者独立执行和重算
- 写入边界: 仅写本审计文件，未改代码、`state.json`或`results/`

## 一、结论

m3主方法链路基本忠实：中国市场真实m1/m2接口下能够以`t`月特征预测`t+1`月六因子胜出者，固定使用严格过去84个目标月；当前目标月只按m2的`predicted_regime`选择模型，历史训练状态只取该预测月专属的m2历史标签窗，未读取目标月`actual_regime`；Bear稳定并入Correction。每状态六个一对其余RF、AS20冻结参数、概率归一、零概率1/N回退、确定性并列处理、三类相关矩阵、胜出频率、两状态重要性、RankIC与Top命中均有真实实现且独立试验通过。

但AS40诊断损失存在一个可复现的major阻断：当某状态在84月窗的前72月没有样本、仅在最后12月验证段出现时，诊断模型为`None`，代码却把空概率数组和非空验证标签交给`log_loss`，直接抛出`ValueError`。AS40已明确允许稀有状态导致验证logloss为空；当前行为不仅没有留空，反而在正式84月RF重训之前中止整个预测月。因此m3当前代码门禁不通过。

## 二、时间标签、84月窗口及同月收益防泄漏

### 2.1 标签构造

- `build_winner_labels`把`factor_returns.signal_date=t`对应的下一交易期收益标为`prediction_period=t+1`，见`factor_model.py:128-215`。
- 六因子必须全部非空才生成唯一胜出者；任一缺失时整月`winner_available=False`，不会以部分因子截面定义胜出者。
- 独立两月边界试验：2023-01信号收益被标到2023-02；Value与Growth同为10%时按配置顺序选Value，`tie_count=2`；第二月仅5个因子可用时胜出行数为0。
- 实际并列顺序固定为`Value|Growth|Momentum|Low Volatility|Quality|Small-Cap`，与配置一致。

### 2.2 滚动窗口与特征错位

- `factor_model.py:553-565`固定取当前位置之前84行，断言84个连续日历目标月、训练窗最大目标月严格早于当前预测月，并逐行断言`predictor_month+1=prediction_month`。
- 合成主链路目标月2023-05使用2016-05至2023-04共84个目标月；真实链路目标月2025-12使用2018-12至2025-11共84个目标月。
- 正式预测器只选`SECOND_STAGE_FEATURES`，见`factor_model.py:676-684`。目标月的`actual_return_*`与`winner_factor`只在概率生成之后用于RankIC、Top命中等评估，见`factor_model.py:700-738`。

### 2.3 目标收益扰动测试

对同一100月合成样本连续运行两次，仅把目标月实际胜出者从Low Volatility改为Small-Cap：

- 六因子预测权重最大绝对变化为0；
- `actual_winner`按预期从Low Volatility变为Small-Cap；
- 训练窗口、状态、模型和概率完全不变。

结论：目标月同月收益没有进入特征、状态切分或RF拟合；只在预测完成后进入评估指标。

## 三、m2状态接口与Bear合并

- 当前目标月状态由`_normalise_stage_one_predictions`严格读取m2 `rolling_predictions[prediction_date, predicted_regime]`，见`factor_model.py:219-238`；没有选择或回退到`actual_regime`的代码路径。
- 当前预测月专属的历史84月状态由`_training_regimes_for_window`按当前`prediction_date`筛选m2 `regime_labels`，再按`regime_date`和训练目标月匹配，见`factor_model.py:261-285`。其他滚动窗的历史重标结果不会混入当前训练窗。
- 当前窗若缺任一历史状态即在`factor_model.py:577-584`报错，不用未来真实状态、相邻窗状态或静态填充补洞。
- `collapse_second_stage_regime`只接受Normal/Correction/Bear，并将Bear确定性改为Correction，未知状态立即拒绝，见`factor_model.py:119-125`。
- 合成试验故意提供`predicted_regime=Bear`、`actual_regime=Normal`，最终始终选择Correction模型，证明目标月真实状态未参与选择。
- 真实2025-12链路中m2预测Bear，m3选择Correction；当前专属84月历史标签为Normal 35月、Correction与Bear合并后49月，缺失状态月为0。

结论：当前目标状态使用m2滚动预测，训练状态使用当前m2滚动窗内已实现的历史标签；未读取目标月或未来月真实状态，通过。

## 四、每状态六RF、参数及概率合同

### 4.1 RF模型

- `FactorModelSettings`强制84月、RF 500棵、`max_depth=4`、`min_samples_leaf=3`、`max_features=sqrt`、`class_weight=balanced`、seed=42，任一偏离都会报错，见`factor_model.py:50-61,102-116`。
- 主循环对Normal和Correction分别遍历固定六因子；每个因子用`winner_factor==factor`形成一对其余二元标签，见`factor_model.py:588-656`。
- 合成正常状态窗和真实2025-12窗口均得到Normal 6个、Correction 6个正式模型；真实状态训练行分别35和49。
- 正式概率模型在AS40诊断之后重新用该状态在完整84月候选窗内的全部可用历史样本拟合，见`factor_model.py:634-639`。

### 4.2 概率归一与1/N回退

- 六个独立二分类原始概率先求和再同比例归一；最终逐行断言六权重和为1，见`factor_model.py:676-695,741-744`。
- 合成主试验原始概率和为1.6078306171，归一权重和为1；真实2025-12权重和也为1。
- 独立零状态样本试验：m2预测Bear/Correction，但84月历史全部Normal，Correction六模型均为空，原始概率和0；代码真实触发`zero_or_nonfinite_probability_sum`，六因子均为1/6，和为1。
- 预测胜出者概率并列时按固定因子顺序取首项，见`factor_model.py:696-699`，与实际标签并列规则一致。

结论：AS20独立二分类、六概率归一及1/N回退通过。

## 五、R4-R8与诊断指标核对

### 5.1 相关矩阵与胜出频率

- `calculate_factor_correlations`输出Entire Sample、Normal、Correction三个scope，每个scope为完整6×6矩阵并带`n_obs`，共108行，见`factor_model.py:371-410`。
- 审计者另构造12月已知收益与前6月Normal、后6月Bear/Correction状态，分别用pandas直接重算三个矩阵；与实现逐元素最大绝对误差均为0。
- `summarize_winner_frequency`按唯一胜出行计数并除以各scope可用目标月数，见`factor_model.py:413-446`。合成和完整主链路均输出18行；三个scope的六因子频率和各为1。

### 5.2 特征重要性

- 每个正式RF保留13项底层特征重要性；`_aggregate_feature_importance`先按六类经济组对每个因子求和，再对同状态六因子取均值并在状态内归一，见`factor_model.py:449-479`。
- 合成主链路形成12个“状态×因子”重要性合同；Normal、Correction的`state_group`重要性和分别为1和0.9999999999999999。
- 真实2025-12六类组重要性在Normal和Correction下均恰好归一为1。
- 单类二元模型可能给出全零的因子级重要性，但状态组汇总对此保持可追溯，不伪造非零贡献。

### 5.3 RankIC、Top命中与AS40 logloss

- `_rank_ic`按六因子归一概率与同目标月六因子实际收益计算Spearman相关；不足2项或任一序列无变异时返回NaN，见`factor_model.py:482-488`。
- 合成主链路RankIC实现值与独立pandas重算均为0；真实2025-12为-0.6571428571。
- Top命中严格比较确定性预测胜出者与目标月唯一实际胜出者；真实2025-12预测Small-Cap、实际Momentum，`top_hit=False`，与直接比较一致。
- AS40正常状态分布下，以`prediction_period-12`为验证起点：合成84月窗前72个日历月作为诊断训练、最后12个日历月作为验证，再在状态内形成24/4与48/8行；真实2025-12的12个“状态×因子”train/validation logloss均可计算。
- 但稀有状态边界失败，详见CA-A01。

## 六、真实中国市场单月运行

审计者在项目`uv run --extra ml --no-sync`环境中，不写结果文件，依次运行真实m1、受限为单目标月的m2及正式参数m3：

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| m1月度特征 | 132×39 | 可消费 |
| m1因子收益 | 792×10=132月×6因子 | 完整 |
| m2/m3目标月 | 2025-12-31 | 日期一致 |
| m3预测特征日 | 2025-11-28 | 严格早于目标月 |
| m3训练目标窗 | 2018-12至2025-11，共84月 | 通过 |
| m2历史状态来源 | `m2_window_regime_labels` | 通过 |
| 历史状态缺口 | 0 | 通过 |
| 状态训练行 | Normal 35、Correction 49 | 通过 |
| 正式模型数 | 两状态各6 | 通过 |
| m2预测/m3选择 | Bear/Correction | 通过 |
| 六因子权重和 | 1.0 | 通过 |
| 相关矩阵/频率 | 108行/18行 | 通过 |
| 两状态组重要性和 | 均为1.0 | 通过 |
| AS40损失 | 12行，train/validation各12项有限值 | 当前真实月通过 |
| 参数哈希 | `592eba222d8994aec5457fc4a2ea1881c5efd4f5f32d659bdc993c6d42455ce7` | 64位 |

该真实单月通过不能覆盖CA-A01的合法稀有状态边界，因此不据此放宽结论。

## 七、coverage_matrix m3全部done行核对

| 要素 | 实现位置 | 公式/参数结论 | 审计结论 |
| --- | --- | --- | --- |
| F1 | `run_stage_two_factor_model` | m2状态→m3分状态因子概率链路真实 | pass |
| F8 | `_training_regimes_for_window` | 当前m2窗历史状态，无目标月实际状态 | pass |
| F9 | `build_winner_labels` | `t`信号收益标到`t+1`，唯一胜出及并列顺序 | pass |
| F10 | `run_stage_two_factor_model` | 两状态×六RF及完整窗正式重训 | pass |
| B3 | `run_stage_two_factor_model` | 每月窗口右移，非扩展窗 | pass |
| B4 | `run_stage_two_factor_model` | 强制84个连续目标月 | pass |
| B9 | `collapse_second_stage_regime` | Bear→Correction，未知状态拒绝 | pass |
| R4 | `calculate_factor_correlations` | Entire Sample 6×6矩阵 | pass |
| R5 | `calculate_factor_correlations` | m2历史Normal状态6×6矩阵 | pass |
| R6 | `calculate_factor_correlations` | Bear并入后的Correction 6×6矩阵 | pass |
| R7 | `summarize_winner_frequency` | 唯一胜出频率按可用月分母 | pass |
| R8 | `_aggregate_feature_importance` | 六经济组、两状态内归一；但AS40边界可阻断产出 | major issue CA-A01 |
| SA2 | `calculate_factor_correlations` | 三scope相关矩阵及n_obs完整 | pass |

全部矩阵位置存在且非空壳，未发现`pass`/`TODO`虚报或未映射要素ID的公开策略私货函数。

## 八、issue清单

### CA-A01

- severity: major
- 证据定位: `workspace/r003_equity_factor_timing_cn/assumptions.md:513-521`；`src/r003_equity_factor_timing_cn/factor_model.py:348-353,593-630`
- 依据: AS40明确指出某状态在窗尾12个月样本稀少时验证logloss可以为空；若该状态前72月无样本、最后12月有样本，`diagnostic=None`使`validation_probability`为空，但`diagnostic_validation`标签非空，随后`_safe_binary_logloss`调用sklearn `log_loss`并抛出`ValueError: Found array with 0 sample(s)`。审计者用合法84月状态窗“前72月Normal、后12月Correction”在正式入口稳定复现，正式84月RF尚未来得及重训即被诊断分支阻断。
- 影响要素: F10、R8、AS40诊断输出及该预测月全部m3概率。
- 通过条件: 诊断训练为空时，对该状态/因子的train与validation logloss输出NaN并记录不可计算原因，不对非空验证标签传空概率；随后仍使用完整84月状态子样本拟合正式模型。需补边界测试覆盖“训练空/验证非空”“训练非空/验证空”“两者均空”。

## 九、五维度审计结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | pass_with_issues | `t→t+1`标签、分状态RF、概率归一、相关性和指标公式通过；AS40空诊断边界实现不完整 |
| 参数一致 | pass | 84月、12月验证、RF 500/4/3/sqrt/balanced/seed42均被强制冻结 |
| 实现位置真实 | pass | m3全部done位置存在、非空壳且进入主结果合同 |
| 代码反查 | fail | 正常合成和真实单月通过，但合法稀有状态84月窗稳定触发ValueError |
| 简化声明 | fail | AS40声明稀有状态logloss可为空，实际却中止正式模型，声明与实现边界不一致 |

## 十、已检查维度清单

- [x] m3全部done行F1、F8-F10、B3-B4、B9、R4-R8、SA2逐条核对
- [x] `t`月特征到`t+1`六因子收益标签、六因子完整性与确定性tie-break
- [x] 固定84个连续目标月及训练窗严格早于预测月
- [x] 当前状态来自m2 `predicted_regime`，目标月`actual_regime`未使用
- [x] 当前预测月专属m2历史状态窗、无未来目标状态补洞及Bear→Correction
- [x] 两状态×六RF及500/4/3/sqrt/balanced/seed42参数
- [x] 原始概率归一、权重和断言及零概率1/N回退
- [x] 目标月收益扰动不改变预测概率，排除同月收益泄漏
- [x] R4-R6三scope 6×6相关矩阵逐元素独立重算
- [x] R7频率分母、频率和、R8两状态六组重要性归一
- [x] RankIC独立复算、Top命中直接比对
- [x] AS40前72/后12日历月口径、正常窗和稀有状态边界
- [x] 真实中国m1 132×39、792条因子收益及2025-12 m2→m3单月链路
- [x] 五维度：公式一致、参数一致、实现位置真实、代码反查、简化声明

初审结论: fail

## 十一、第1轮修复后复审更新

详细独立证据见`audit/impl_audit_m3_reaudit_round1.md`。本轮在项目uv ML环境重新执行原阻断84月状态窗、反向边界、双空边界及真实中国市场2025-12链路。

| 初审问题 | 当前状态 | 独立证据摘要 |
| --- | --- | --- |
| CA-A01 major：诊断训练空、验证非空时logloss崩溃 | resolved | Correction前72月0行、后12月12行时六项train/validation损失均NaN，reason完整；正式全窗仍以12条历史训练6个RF并输出Bear→Correction目标概率 |

当前实现没有用验证标签估计先验：诊断为空时验证概率保持空，`validation_logloss_available=False`；验证标签不生成常数概率。训练有/验证无及训练验证均空也均返回NaN、行数、可用性和reason，不再阻断正式模型。

真实m1 132×39、792条因子收益及2025-12 m2→m3链路无回归：固定84月、Normal/Correction为35/49行、两状态各6模型、12项正常训练/验证loss均有限、权重和1、相关矩阵108行、频率18行、两状态重要性和均为1。

### 第1轮复审五维度

| 维度 | 结论 |
| --- | --- |
| 公式一致 | pass |
| 参数一致 | pass |
| 实现位置真实 | pass |
| 代码反查 | pass |
| 简化声明 | pass |

### 第1轮复审已检查维度

- [x] 前72无/后12有、前72有/后12无、两者均空三类边界
- [x] NaN、可用性、行数与reason留痕
- [x] 不使用验证标签估先验，正式84月模型继续输出
- [x] 真实中国2025-12正常链路及全部此前通过项无回归
- [x] m3全部done行与五维度

verdict: pass
