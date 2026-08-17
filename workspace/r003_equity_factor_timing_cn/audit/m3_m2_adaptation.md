# m3 对 m2 第1轮修复的增量接口适配复核

- 复核范围: `audit/m2_fix_round1.md`、修复后的 `regime_model.py`、现有 `factor_model.py`
- 复核结论: **接口兼容，无需修改 `factor_model.py`**
- 边界: 未修改m1、m2、main、state、results或common；未运行正式回测。

## 一、结果合同复核

| m3消费项 | m2修复后字段 | 兼容结论 |
| --- | --- | --- |
| 目标月预测状态 | `StageOneRegimeResult.rolling_predictions[prediction_date, predicted_regime]` | 字段名与语义未变，兼容 |
| 目标月前一月特征日 | `rolling_predictions.predictor_date` | 仍满足predictor_date早于prediction_date，兼容 |
| 当前预测月专属84月历史状态 | `StageOneRegimeResult.regime_labels[prediction_date, regime_date, regime]` | 每个预测月保持84个唯一regime_date，兼容 |
| Bear合并Correction | m2仍输出Normal/Correction/Bear | m3的`collapse_second_stage_regime`继续适用 |
| m2新增输出 | `elbow_diagnostics`、`meta_oof_*` | m3不依赖这些字段，新增字段不破坏旧合同 |

m3接收完整`StageOneRegimeResult`时，当前目标月用`rolling_predictions.predicted_regime`选择Normal或Correction模型；历史84月切分使用同一目标月对应的`regime_labels`，不会误用其他滚动窗或目标月实际状态。

## 二、uv ML环境端到端小型冒烟

- 环境: `UV_CACHE_DIR=/private/tmp/report_reproduce_uv_cache uv run --extra ml`
- 版本: `scikit-learn 1.9.0`
- 输入: 100个连续合成月；m2只预测最后1个月；m2烟测RF缩为8棵，m3保持正式冻结的500棵参数。
- 链路: `run_stage_one_regime_model(...) -> StageOneRegimeResult -> run_stage_two_factor_model(...)`

结果：

| 检查项 | 实际值 |
| --- | --- |
| m2滚动预测行数 | 1 |
| m2当前预测窗历史标签 | 84行、84个唯一月份 |
| m2肘部K合同 | `[2, 3, 4, 5, 6]` |
| m3滚动预测行数 | 1 |
| m3历史状态来源 | `m2_window_regime_labels` |
| m3训练候选窗 | 84个月 |
| m3历史状态缺口 | 0 |
| m3每状态模型数 | 6 |
| m3六因子归一化权重和 | 1.0 |
| m2 predictor / prediction | 2023-03-31 / 2023-04-30 |
| m3 predictor / prediction | 2023-03-31 / 2023-04-30 |

日期逐项一致，证明m2修复没有改变m3依赖的t特征到t+1目标月语义。

## 三、非阻断观察

uv环境的scikit-learn 1.9对m2使用的`SVC(probability=True)`发出未来弃用警告；本次运行未失败，该警告不属于m2→m3字段或日期接口不兼容，且本任务禁止修改m2，因此仅记录不处理。

## 四、改动结论

- `factor_model.py`: 无改动。
- 新增本适配记录，供后续code audit与verifier核对。
- 本记录仅证明增量接口兼容和小型链路可执行，不代表正式m3或整案验证通过。
