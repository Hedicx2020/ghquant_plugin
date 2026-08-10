# m3 第1轮定向修复记录

- 修复轮次: round 1
- 修复依据: `audit/impl_audit_m3.md` 的唯一major问题CA-A01
- 修改范围: `src/r003_equity_factor_timing_cn/factor_model.py`、本记录
- 未修改: m1、m2、m4、main、state、results、common及AS40

## 一、CA-A01逐项回应

### 问题

当84月窗的前72个诊断训练月没有某状态、该状态只在最后12个验证月出现时：

- `diagnostic_train`为空，`_fit_binary_forest`返回`None`；
- 旧实现产生空的`validation_probability`；
- 随后把非空验证标签与空概率传入`sklearn.metrics.log_loss`，预测月在正式84月模型拟合前中止。

### 修复

1. `_safe_binary_logloss`在标签为空或概率为空时直接返回`NaN`，不读取验证标签估计常数先验。
2. 标签与概率均非空但长度不一致时立即抛出明确错误，防止静默截断或错误配对。
3. `train_val_logloss`新增以下逐“预测月×状态×因子”字段：
   - `diagnostic_available`
   - `train_logloss_available`
   - `validation_logloss_available`
   - `diagnostic_unavailable_reason`
4. 训练段无该状态时，原因固定记录为`no_state_samples_in_diagnostic_train`，train/validation log-loss均为`NaN`。
5. 验证段无该状态但诊断训练可用时，原因记录为`no_state_samples_in_validation`，训练损失正常输出、验证损失为`NaN`。
6. 诊断分支之后的正式模型仍使用该状态在完整84月窗的全部可用样本重新拟合；本修复不改变正式概率、RF参数或AS40口径。

## 二、稀有状态合成回归

- 环境: `UV_CACHE_DIR=/private/tmp/report_reproduce_uv_cache uv run --extra ml`
- 构造: 单个84月训练窗，前72月全部Normal，最后12月全部Correction；目标月预测Correction。
- m3参数: 正式冻结的RF 500棵、depth=4、leaf=3、sqrt、balanced、seed=42。

结果：

| 检查项 | 实际值 |
| --- | --- |
| 运行是否中止 | 否 |
| Correction诊断训练行 | 0 |
| Correction诊断验证行 | 12 |
| Correction `diagnostic_available` | 6/6均为False |
| Correction `validation_logloss_available` | 6/6均为False |
| 不可计算原因 | 6/6均为`no_state_samples_in_diagnostic_train` |
| Correction训练损失 | 6/6为NaN |
| Correction验证损失 | 6/6为NaN |
| 完整84月正式Correction模型 | 6个 |
| 完整84月正式Normal模型 | 6个 |
| 目标月六因子权重和 | 1.0 |

该回归证明：验证标签没有被用于估计替代概率，诊断不可计算不会再阻断完整84月正式模型。

## 三、正常m2→m3链路回归

- 输入: 100个连续合成月；修复后的m2仅预测最后1个月并直接把`StageOneRegimeResult`交给m3。
- m2烟测RF缩为8棵；m3仍保持正式冻结500棵参数。

结果：

| 检查项 | 实际值 |
| --- | --- |
| m2滚动预测 / 历史状态标签 | 1行 / 84行 |
| m3滚动预测 | 1行 |
| Normal / Correction正式模型 | 各6个 |
| 六因子权重和 | 1.0 |
| 诊断损失行数 | 12 |
| 有限训练log-loss | 12/12 |
| 有限验证log-loss | 12/12 |
| 不可计算原因 | 全部为空字符串 |

正常链路未出现回归。

## 四、边界与结论

- 编译通过。
- 未运行正式中国市场33个月结果，未写任何`results/`文件。
- 本记录只证明CA-A01已定向修复并完成合成回归，不声明m3验证或整案门禁通过；结论仍由verifier与check_gates给出。
