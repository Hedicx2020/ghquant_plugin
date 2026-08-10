# 全局代码审计第2轮修复记录

- 修复依据: `audit/code_audit_reaudit_round1.md` 的 critical `CDX-C-R1-01`
- 修改范围: `src/r003_equity_factor_timing_cn/factor_model.py`
- 证据更新: `audit/m3_label_availability_adaptation.md`第2轮
- 未修改: m1、m2、m4、m5、`main.py`、`config.py`、`state.json`、`results/`、`common/`

## 一、问题回应

审计指出第1轮以目标月末`prediction_date`作为标签截止，晚于真实决策特征日`predictor_date`。因此一条标签若在特征形成之后、目标月末之前才实现，仍会被旧条件纳入，存在决策时点前视。

本轮将正式RF、诊断训练和诊断验证的共同资格改为：

`winner_available AND label_available_date <= predictor_date`

采用`<=`的冻结解释是：`label_available_date`表示当日已经实现，同一特征日收盘时已实现的标签可用；晚于该日才实现的标签不可用。固定84月仅作为候选窗，不替补被排除行，不改变RF参数。

## 二、代码证据

| 修复点 | 实现位置 |
| --- | --- |
| 决策日标签资格 | `factor_model.py:623-630` |
| 正式模型与诊断共用过滤后状态窗 | `factor_model.py:634-698` |
| 审计截止写真实`predictor_date` | `factor_model.py:717-746` |
| 最终断言最晚可得日不晚于截止 | `factor_model.py:835-851` |

`training_audit`继续输出候选月、完整标签、训练可用标签、因可得性排除标签、缺失可得日、实际最晚使用日与来源，可独立重算过滤结果。

## 三、冒烟证据

### 决策时点边界

- `predictor_date=2023-03-31`，`prediction_date=2023-04-30`。
- 构造一条`label_available_date=2023-04-10`的完整历史标签：其位于特征日之后、目标月末之前，84个完整标签中仅83个进入训练。
- 把该被排除行的胜出因子从Value改为Small-Cap，两次正式六因子预测权重逐位完全一致。
- 最新被使用标签的可得日恰为`2023-03-31`，证明截止日同日已实现标签按`<=`纳入。

### 正常无延迟链路

- 显式`label_available_date=return_date`：84/84标签进入训练，排除0。
- 移除新字段并走`return_date`兼容回退：六因子预测权重与显式输入逐位完全一致。
- m3两类运行均保持正式500棵RF参数。
- `python3 -m compileall -q src/r003_equity_factor_timing_cn/factor_model.py`退出码0。

## 四、边界声明

本记录不修改审计文件、不写正式结果，只证明已按`CDX-C-R1-01`建议实施定向代码修复并完成合成冒烟；是否关闭该finding及门禁是否通过仍由后续独立审计决定。
