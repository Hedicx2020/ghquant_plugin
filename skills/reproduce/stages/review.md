# stage: review（人工闸门）

最终报告等人工裁决。**无机器门禁**；`awaiting_review` 是终态之一，任何驱动器（/goal、/loop、ralph-loop）到此**停下，不得自行 accept**。

## 入口条件

- report done，`state.status == awaiting_review`。

## 挂起说明（进入本 stage 时向用户呈现）

用 `state.py show <id>` 摘要 + 打印以下要点：
- **报告位置**：`workspace/<id>/final_report.md`
- **假设修改工作表**：`workspace/<id>/assumptions.xlsx`（report 阶段已导出；黄底三列 `新值`/`新口径`/`操作` 可编辑，供批量 revise；单条假设的「参数绑定/当前值」也在表内）
- **verdict**：`state.verdict.result`（pass / partial）与 metrics_pass/total
- **可信度评级**：final_report 附录 A.6 给出的 A / B / C（C 级须提示核心未复现或 major 遗留）
- **覆盖率**：`state.coverage_stats`（total/done/skipped/infeasible）
- **待决项**：audit_responses 中处置=rejected 的遗留意见、`major-auto` 高亮假设清单（供用户判断是否 revise）
- 若为 `partial`：残余偏差与归因摘要（final_report 附录 A.5）

## 用户三条出路（打印指引）

- **确认收尾**：
  ```
  /reproduce accept <id>
  ```
  → 见 SKILL.md 3.5：`set-stage review done` → verdict=partial 则 `status=done_partial`，否则 `status=done`。

- **批量 Excel revise（推荐，多条一次改完）**：先在 `workspace/<id>/assumptions.xlsx` 填好要改的行（黄底列 + 操作选 revise），然后：
  ```
  /reproduce revise <id> --from-excel          # 合并重跑：所有修改一次跑完，产修改前 vs 修改后对比
  /reproduce revise <id> --from-excel --each   # 逐条敏感性：每条独立重跑，产 assumption_sensitivity.xlsx
  ```
  → 见 SKILL.md 3.4 批量形式：dry-run 复述确认 → 参数直改工具注入 config.py / 文本改动派 planner → 按最重影响面跑一轮链路 → 回 `awaiting_review`。**--each 成本提示必须打印**：N 条 = N 次全量回测（N≥3 或 ml 案例须用户明确确认）；--each 仅支持纯参数直改行。工作表被改乱时 `/reproduce export-assumptions <id>` 重新导出干净表。

- **单条定向重跑**（对某假设不认同/发现口径问题）：
  ```
  /reproduce revise <id> --assumption <ASid> "<新口径>"
  /reproduce revise <id> --instruction "<自然语言指令>"
  ```
  → 见 SKILL.md 3.4：planner 更新 assumptions → 按影响面查表定重跑范围 → 只重跑受影响链路 → reporter 增量更新 → 回 `awaiting_review`。revise 不占 max_iter，单条内部上限 3 轮。

## 跨会话挂起

`awaiting_review` 可跨 session 挂起：`continue <id>` 读到该状态即重新呈现上述挂起说明并等指令，不推进、不自作主张。
