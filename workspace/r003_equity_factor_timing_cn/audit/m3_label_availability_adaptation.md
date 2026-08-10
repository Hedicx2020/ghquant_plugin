# m3 对标签可得日与延迟退出的增量适配

- 适配范围: `src/r003_equity_factor_timing_cn/factor_model.py`
- 上游合同: m1 `factor_returns.label_available_date` 与 AS42 中国股票固定20交易日延迟退出窗
- 修改边界: 未修改m1、m2、m4、m5、`main.py`、`config.py`、`state.json`、`results/`或`common/`
- 参数边界: m3正式RF仍为500棵、`max_depth=4`、`min_samples_leaf=3`、`max_features=sqrt`、`class_weight=balanced`、`seed=42`

## 一、发现的问题

旧m3只要求历史行的目标月早于当前预测月，并以`winner_available`判断六因子收益是否齐全；它没有读取m1新增的`label_available_date`。中国股票计划退出日遇到停牌、ST、涨跌停时可能延迟退出，因此一条收益即使事后已经完整写入`factor_returns`，在当时预测日仍可能尚未实现。仅按`target_month`或`signal_date`过滤会把这类事后标签提前放进RF训练，构成标签可得性前视。

## 二、适配实现

1. `build_winner_labels`逐信号月汇总六个因子的标签可得日，取最晚日期，确保胜出标签只有在六个因子收益均已实现后才可进入训练。
2. m1新字段存在时，来源固定记为`factor_returns.label_available_date`。为保持既有无延迟输入接口不变，字段缺失时依次回退到`return_date`和`t+1`目标月末，并在`label_availability_source`中显式标出兼容来源。
3. `winner_available`继续只表示六因子事后收益完整，供相关矩阵、胜出频率和结果评价使用；它不再单独决定正式训练资格。
4. 每个滚动预测月先保留固定84个连续候选目标月，再生成严格条件：

   `winner_available AND label_available_date < prediction_date`

   正式RF、72/12月诊断训练与验证切分都只消费满足该条件的行。候选窗长度仍固定84个月，不因标签延迟而向更早月份扩窗或替补。
5. 相关矩阵和胜出频率仍可使用事后完整历史标签，未改变报告统计口径；仅正式滚动预测训练和对应诊断损失过滤当时尚不可得的标签。
6. `training_audit`新增`train_eligible_label_months`、`labels_excluded_by_availability`、`missing_label_available_date_months`、`label_cutoff_date`、`latest_training_label_available_date`和来源字段。函数末尾硬断言每个状态实际使用标签的最晚可得日严格早于预测日。

## 三、合成长延迟跨预测日回归

- 输入: 85个连续月、固定六因子、一个2023-04-30预测月；候选训练窗84个月。
- 延迟构造: 2023-01信号对应的六因子收益目标月为2023-02，但`label_available_date`统一设为2023-05-10，跨过2023-04-30预测日。
- 对照扰动: 两次运行只把该延迟月份的胜出因子由Value改为Small-Cap；m3保持正式冻结的500棵RF参数。

| 检查项 | 实际值 |
| --- | ---: |
| 固定候选月 | 84 |
| 事后完整标签 | 84 |
| 当时可训练标签 | 83 |
| 因可得日晚于预测日而排除 | 1 |
| Normal与Correction实际训练行合计 | 83 |
| 实际使用标签最晚可得日 | 2023-03-31 |
| 当前预测日/截止日 | 2023-04-30 |
| 延迟标签胜出因子扰动后六因子预测权重 | 逐位完全不变 |

该回归同时证明两点：延迟行仍保留在事后标签表中，但不会进入当期正式RF或诊断切分；正常已实现标签的训练接口和固定84月候选窗均未改变。

## 四、兼容与编译检查

- `python3 -m compileall -q src/r003_equity_factor_timing_cn/factor_model.py`: 退出码0。
- 无`label_available_date`的既有输入仍可构造标签；若有`return_date`则按该日回退，否则按目标月末回退，来源均在审计字段留痕。
- 本轮尝试限时重跑真实中国m1→m2→m3单月链路。全股票m1在新增逐股票延迟退出检查处运行时间超过本轮冒烟预算；`smoke_months`截断方式又会使上游交易日历不足以构造末月T+1，均未产生m3结果。为避免越界修改m1或写入正式结果，本轮终止该项；既有`impl_audit_m3.md`中的2025-12真实链路仅作为旧接口基线，不冒充本次新字段验证。
- 所有回归均未写`output/r003_equity_factor_timing_cn/results/`，本记录只报告定向适配与冒烟事实，不声明m3或整案门禁通过。

## 五、第2轮：决策特征日冻结修正

### 5.1 触发问题

`audit/code_audit_reaudit_round1.md`新增critical `CDX-C-R1-01`：第1轮虽然过滤了`label_available_date < prediction_date`，但`prediction_date`是目标月月末，真实形成当月预测的`predictor_date`更早。位于两者之间才实现的延迟退出标签仍可能进入模型。上文第2、3节记录的是第1轮历史行为，本节起的规则取代其中“以目标月末为截止”的描述。

### 5.2 冻结规则

- 正式训练和72/12诊断切分统一使用：`winner_available AND label_available_date <= predictor_date`。
- 采用`<=`而不是`<`：`label_available_date`表示该交易日已经实现；若退出与标签在特征日当日收盘时已完成，则冻结样本时可用。特征日次日及之后才实现的标签一律排除。
- `training_audit.label_cutoff_date`改为当前预测行的真实`predictor_date`，不再记录目标月末。
- 最终硬断言改为`latest_training_label_available_date <= label_cutoff_date`；错误信息明确指向“决策特征日”。
- 固定84个月仍是候选窗，不对排除的延迟标签向前替补；相关矩阵和胜出频率仍使用事后完整历史标签。

### 5.3 边界合成回归

同一预测行中：`predictor_date=2023-03-31`、`prediction_date=2023-04-30`。

| 边界 | 构造与结果 |
| --- | --- |
| 特征日后、目标月末前 | 一条历史标签设为`2023-04-10`，满足`2023-03-31 < 2023-04-10 < 2023-04-30`，被排除 |
| 截止日同日 | 最新正常标签可得日为`2023-03-31`，与`predictor_date`相等，按`<=`纳入 |
| 候选/完整/训练可用 | 84 / 84 / 83个月 |
| 状态训练行合计 | 83，与训练可用标签数一致 |
| 延迟标签扰动 | 只把被排除行的胜出因子由Value改为Small-Cap，两次六因子预测权重逐位完全一致 |
| 审计截止 | `label_cutoff_date=2023-03-31`；实际使用标签最晚可得日同为`2023-03-31` |

### 5.4 正常无延迟回归

- 显式提供`label_available_date=return_date`时，84个完整候选标签全部可训练，排除数为0。
- 删除新字段、由兼容路径回退到`return_date`后，正式六因子预测权重与显式输入逐位完全一致。
- m3仍使用正式冻结500棵RF参数；`python3 -m compileall -q src/r003_equity_factor_timing_cn/factor_model.py`退出码0。
- 本节只记录第2轮定向修复和冒烟事实，不声明critical已由审计方关闭，也不声明整案门禁通过。
