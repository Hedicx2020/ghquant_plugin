# 点收不过

`flow done` 的输出里 `collected[].ok` 为 false 时，看 `class`。输出里已经带着重派工单的，照工单重派即可。

## incomplete

交回的文件不全、是空文件，或要求回执而没有写。内核把缺的清单写进重派工单的「重派原因」，同一步骤重派，计入重派次数。不要替子 agent 补文件，也不要手工改步骤状态。

## receipt_rejected

回执被拒收：格式读不出来；回填了不属于这一步的矩阵行或假设；状态流转不合法（比如把 pending 直接写成 done 却没给实现位置）；用了预留区间之外的新假设编号；影响面或参数绑定的写法不对。拒收理由逐条写在 `reasons` 里并进入重派工单。重派的任务文件会点名上一次的回执、沿用上一次预留的假设编号：活不用重做，只改回执。

## answer_rejected

裁决答卷不合格（缺条目、处置取值不对、accepted 没写 owner、critical 或 major 没写回应）。这一步是你自己的：按 `reasons` 改答卷文件，再 `flow done` 同一个步骤。格式见 `flow explain review_cycle`。

## blocked

子 agent 在回执里写了 `status: blocked`，或你用 `flow fail --class blocked` 记的。内核开 `step_blocked` 检查点交给人，不自动重派。外审替身受阻不惊动人，那一轮外审记为不可用。

## crashed

子 agent 中途中断（会话断了、被取消），用 `flow fail <id> <步骤> --class crashed --note "<现象>"` 记一笔，内核按重派处理。续跑时发现在途工单对应的子 agent 已经不在了，直接按原工单重派，不用记失败。

## degraded

外审替身重派一次仍交不出审查结果：这一轮外审记为不可用（台账记 skipped，评级封顶 B），流程继续。

## 两条提示

- `读了不该读的路径`：点收时扫描会话记录发现子 agent 的工具调用碰过禁读清单。只留痕并在看板标出，不影响点收。
- `做的时候依据的内容在途中变了`：这一步在途期间它消费的片被改过。用 `flow stale <id>` 看过期范围，是否重做由人决定。
