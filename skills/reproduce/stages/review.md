# stage: review（人工闸门）

最终报告等人工裁决。**无机器门禁**；`awaiting_review` 是终态之一，任何驱动器（/goal、/loop、ralph-loop）到此**停下，不得自行 accept**。

## 入口条件

- report done，`state.status == awaiting_review`。

## 挂起说明（进入本 stage 时向用户呈现）

用 `state.py show <id>` 摘要 + 打印以下要点：
- **报告位置**：`workspace/<id>/final_report.md`
- **verdict**：`state.verdict.result`（pass / partial）与 metrics_pass/total
- **可信度评级**：final_report 附录 A.6 给出的 A / B / C（C 级须提示核心未复现或 major 遗留）
- **覆盖率**：`state.coverage_stats`（total/done/skipped/infeasible）
- **待决项**：audit_responses 中处置=rejected 的遗留意见、`major-auto` 高亮假设清单（供用户判断是否 revise）
- 若为 `partial`：残余偏差与归因摘要（final_report 附录 A.5）

## 用户两条出路（打印指引）

- **确认收尾**：
  ```
  /reproduce accept <id>
  ```
  → 见 SKILL.md 3.5：`set-stage review done` → verdict=partial 则 `status=done_partial`，否则 `status=done`。

- **定向重跑**（对某假设不认同/发现口径问题）：
  ```
  /reproduce revise <id> --assumption <ASid> "<新口径>"
  /reproduce revise <id> --instruction "<自然语言指令>"
  ```
  → 见 SKILL.md 3.4：planner 更新 assumptions → 按影响面查表定重跑范围 → 只重跑受影响链路 → reporter 增量更新 → 回 `awaiting_review`。revise 不占 max_iter，单条内部上限 3 轮。

## 跨会话挂起

`awaiting_review` 可跨 session 挂起：`continue <id>` 读到该状态即重新呈现上述挂起说明并等指令，不推进、不自作主张。
