# r004 spec修复后plan增量同步记录

## 一、同步范围

- 触发原因：spec审计补充并强化四组原文冲突证据，其中A23-A25新增为`major/open`。
- 读取范围：更新后的`spec/spec.md`、`spec/ambiguities.md`，以及现有`plan.md`、`assumptions.md`；仅为回填追溯关系核对`spec/coverage_matrix.md`相关行。
- 禁止范围：未读取PDF、report_text、旧案例、代码、results或state；未调用skill或其他agent。
- 输出范围：增量修改`plan.md`、`assumptions.md`、`spec/ambiguities.md`、`spec/coverage_matrix.md`，新增本记录。

## 二、增量裁决

| 歧义 | 原文冲突证据的保留方式 | r004裁决 | 假设 |
| --- | --- | --- | --- |
| A6 | p4市场风险状态目标与p9/p15 shadow rate表述并列保留 | 原既有裁决不变：风险状态解释占优，但原ML主线整体out_of_scope | AS5 |
| A23 | p5 Refinitiv与Exhibit的FRED/Factset来源行并列保留，不判断哪一方是原文唯一正确来源 | 原美股来源冲突对r004为reference_only；实际实现唯一使用data_catalog本地A股源 | AS22 |
| A24 | Exhibit 1的daily return与正文monthly performance并列保留 | 采用四风格箱扣费后月收益做月度胜出频率；不实现F9原ML标签 | AS23 |
| A25 | 正文Mar-23样本终点与Exhibit 16横轴May-23并列保留 | 不推断May-23是否为有效观测；r004冻结2023-03-31，OOS为2023-04-01至2025-12-31 | AS24 |

A23-A25均由`open`更新为`resolved`，且各自裁决结果写明对应假设ID。没有删除冲突证据，也没有把原文任一侧改写为“正确版本”。

## 三、plan同步

- `type=factor`、`difficulty=hard`、`feasibility=feasible`与四个milestone保持不变。
- D14替代映射明确注明原美股来源存在Refinitiv与FRED/Factset冲突；实际实现只使用本地A股行情/交易数据。
- m4胜出频率冻结为BV/BG/SV/SG扣费后月收益比较；该统计不是原F9机器学习标签。
- 回测参数新增原文来源冲突、标签频率冲突和时间终点冲突三项处理边界。
- m1增加本地来源清单验证，m4增加胜出频率可重算与“冲突不参与达标判定”的验证要求。
- A6、A23-A25及AS5、AS22-AS24在plan正文形成双向引用。

## 四、assumptions同步

- 原有AS1-AS21保留，不删除、不改号。
- 新增AS22（A23来源冲突）、AS23（A24月度胜出频率）、AS24（A25样本终点冲突）。
- 假设总数由21增至24；新增三条均为`major-auto`，`验证后回看`使用占位符`[verify 后填]`。
- 六条`market-transplant`假设AS15-AS20保持不变；AS22补充来源冲突处理，不重复计作新的市场数据替代。

## 五、coverage同步

- D11-D13追加A23/AS22引用，继续`skipped`且理由为`out_of_scope/reference_only`。
- D14追加A23/AS22引用，继续由m1覆盖且状态为`pending`。
- F9追加A24/AS23引用，继续`skipped`；R7追加A24/AS23引用，继续由m4覆盖。
- B1追加A25/AS24引用，继续由m1覆盖。
- 要素状态和milestone映射数量不变：14项`pending`、49项`skipped`、15项`infeasible`。

## 六、阻塞与边界

- 本轮A23-A25没有新增阻塞，所有`major`歧义均无`open`残留。
- A1仍是既有`blocking/blocked`资料缺口；D15-D29继续`nonrecoverable/infeasible`，没有猜测缺失宏观驱动。该支线已被用户排除，不改变中国2×2风格箱的`feasibility: feasible`。
- 本记录只说明planner同步结果，不自行运行或判定主流程门禁。
