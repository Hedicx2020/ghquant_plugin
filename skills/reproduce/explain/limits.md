# 上限与配置键

| 上限 | 默认 | 到了之后 | 怎么改 |
|---|---|---|---|
| 同一步骤重派（首派之外） | 2 次 | 开 `redispatch_exhausted` 检查点 | `.reproduce.json` 的 `flow.redispatch_limit`，按步骤名写，如 `{"verify.main": 3}` |
| 同一阶段门禁修复 | 2 轮 | 同上 | 同上，键写 `gate:<阶段>` |
| 同一检查项连续不过 | 3 次 | 开 `circuit_breaker` 检查点 | 不可配。G-VF-3 单独不过是进入迭代的正常路径，不计 |
| 外审复审 | 3 轮 | 开 `review_rounds_exhausted` 检查点 | 不可配；人在检查点上选「再试一轮」后重新计 |
| 检查点上「修改后继续」 | 3 轮 | 只剩通过、回退、终止 | 不可配 |
| 一次定向重跑内部的收敛 | 3 轮 | 停下交给人 | 不可配 |
| 迭代轮数 | easy 3 / medium 5 / hard 6 | 进入收尾归因，结论记为部分达标 | 建案时 `--max-iter`，或 `default_max_iter` |
| 表外派发（`flow adhoc`） | 5 次 | 命令被拒 | `flow.adhoc_limit` |
| 在途步骤无新进展 | 3 小时 | 开 `stall` 检查点（外审在后台跑时不算） | 建案时 `--stall-hours`，或 `flow.stall_hours` |
| 预算 | 不设 | 开 `budget` 检查点 | 建案时 `--budget-tokens` / `--budget-hours` |

其他配置键：`audit_level`（strict 三道外审都跑，standard 下 spec、code 两道按条件触发，结果外审必跑）、`economy`（提取、验证、样本外分析三个角色用经济档模型）、`flow.iterate_digest`（`shadow` 摘要与全部历史一起给，`on` 第 2 轮只给摘要与上一轮诊断，`off` 不生成）、`external_review.engine`（通用宿主上指定外审引擎）。
