# review（最终评审）

没有机器门禁。报告门禁通过后停在 `final_review` 检查点，等人给结论。**不要替人收尾。**

把这些讲给人：结论（达标 / 部分达标）、覆盖率、可信度评级及封顶原因、报告与结果页的位置、被数据否定的假设、未复现清单。

人的四种决定：

| 决定 | 命令 |
|---|---|
| 通过 | `flow accept <id> --quote "<原话>"`。结论为部分达标时案例状态记为 `done_partial` |
| 改假设后重跑 | `flow revise <id> --assumption ASn --new-text "…"` 或 `--from-excel`，见 `flow explain revise` |
| 回退 | `flow reopen <id> --from <阶段\|mN> --reason "…"` |
| 终止 | `flow decide <id> <检查点> --choice abort --quote "<原话>"` |

批量改假设：`uv run python <插件根>/tools/assumptions_xlsx.py export <id>` 导出工作表，人在黄底的三列里填（新值、新口径、操作），填完用 `flow revise <id> --from-excel --dry-run` 看计划。
