# 定向重跑、回退、复制与其他出口

## revise

`flow revise <id> --assumption AS7 --new-text "<新口径>"`，或 `--from-excel`（读回 `assumptions.xlsx`）。先加 `--dry-run` 看计划，确认后带 `--quote` 执行。重跑范围按假设的「影响面」取：

| 影响面 | 重跑 |
|---|---|
| data / method | 受影响 milestone 的编码与内审 → 代码外审（差量）→ 验证 → 结果审计 → 样本外 → 报告 |
| param / trading | 改参数（config 级）→ 验证 → 结果外审 → 样本外 → 报告 |
| output | 验证（重出图表与表格）→ 报告 |

多条取最重一档；影响面写得不规范按最重处理。不占迭代轮数。逐条敏感性（`--each`）仍按执行卡做。

## reopen

`flow reopen <id> --from <阶段|mN> --reason "…"`，先 `--dry-run` 看过期范围。重开代次加一，旧产物归档到 `flow/archive/`，不删除。结果总是整批重出：省的是编码与内审，不省验证。

## stale

`flow stale <id>`：哪些已完成步骤消费过的内容后来变了。只报告，`reopen_from` 是建议的重开起点；标了 `context_only` 的只是背景变化，不必为它重做。

## fork

`flow fork <id> <新编号> --from <阶段>`：复制成新案例并回退到该阶段起点，原案例不动。用于对照回归。

## pin

`flow pin <id> <阶段> --mode card --reason "…"`：把这个阶段退回执行卡驱动（`stages/legacy/`），内核判断不了时的出路。`--mode kernel` 交还内核。等待态与流转守卫照旧生效。

## adhoc

`flow adhoc <id> --role <角色> --reason "…" --instruction <文件> --writes <路径…>`：步骤表之外的临时派发，返回一张普通工单。有限额并入账。先想清楚是不是该用 `reopen` 或 `pin`。

## rerun

`flow rerun <id> <implement.mN.verify> --false-fail --reason "…"`：milestone 级验证失败是因为验证期间别的 milestone 正在改代码。内核核对事件顺序确有重叠才允许，每个 milestone 限一次。
