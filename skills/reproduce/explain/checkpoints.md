# 检查点

停在检查点时 `flow next` 只返回 `halt`，门禁转绿也不会自动放行。放行命令：

`flow decide <id> <检查点 id> --choice <选项> --quote "<人的原话>"`

凭据分三级：钩子记到了人的输入（Claude Code）、人在自己的终端输入了短码、自述。自述级会在看板和报告附录里标出来。下面只说每个选项选了之后发生什么。

## spec_final / plan_final / milestone_done / verify_done / iterate_round / pre_report / until / step

评审类检查点，选项相同：

- `approve`：通过，继续。
- `modify`：把人说要改的原话交给负责的角色去改，改完重跑所属阶段的门禁，回到同一个检查点。最多 3 轮。
- `edited`：人已经直接改了文件。内核重新核对（milestone 重新验证，验证阶段整批重出），过门禁后回到同一个检查点。
- `rollback`：回退重做，必须加 `--to <阶段|mN>`。
- `abort`：终止案例。

`spec_final`、`plan_final`、`milestone_done`、`verify_done` 只在 interactive 模式出现（`plan_final` 在规格审计之后；`milestone_done` 在该 milestone 验证通过、hard 难度还要等内审有结论之后）。`until` 是建案时 `--until <阶段>` 指定的一次性停点，`step` 是 `--step` 的每步停点。

## data_gap / data_wait / mock_spec / trial_done

数据缺口的四个检查点，见 `flow explain data`。

## feasibility_blocked

planner 判定做不了。`supply`：人补了数据，重新分诊；`experimental`：切到实验模式，用本地等价数据做市场迁移复现（数值不与原文对齐，报告显著声明）；`degrade`：接受降级，原话里要写明接受哪些降级；`abort`。前三种都回派 planner 重写 plan。

## blocking_ambiguity

有阻断级歧义。`answer`：原话里写明每条歧义怎么定，内核回派 planner 落实并登记为「人工裁决」的假设。不要替人裁决。

## iterate_blocked

诊断结论是缺外部输入。`continue`：人已补齐，进入下一轮；`stop_partial`：接受现状，补完归因后按部分达标收尾；`abort`。

## critical_dispute

你在裁决答卷里把一条 critical 写成了拒绝或搁置。`uphold`：意见成立，交给属主角色修复并复审；`waive`：人裁定不成立，原话里写理由，回应表记为 rejected 并在报告的遗留清单里列出。

## circuit_breaker / redispatch_exhausted / review_rounds_exhausted / step_blocked / stuck

流程自己走不下去了：同一检查项连续 3 次不过、重派或门禁修复次数用完、复审 3 轮仍有 critical、子 agent 报告受阻、步骤表派不出下一步。审阅包里有门禁原文或受阻原因。

- `retry`：相关计数清零，卡住的那一步带着原因重派（复审超限则从当前轮起再给 3 轮）。
- `pin_card`：这个阶段退回执行卡驱动（`stages/legacy/`），由你按卡处理；做完用 `flow pin … --mode kernel` 交还。
- `abort`：终止。

先把卡住的原因讲清楚再让人选；同样的原因再试一轮多半还是不过。

## final_review

最终评审，见 `flow explain review`。四个选项对应 `flow accept`、`flow revise`、`flow reopen` 三条命令和 `abort`。

## pdf_duplicate

同一份 PDF 已有案例。`continue`：仍然新建；`abort`：终止这个新案例，去续跑已有的。

## tamper

事件流的哈希链对不上：`state.json` 或 `events.jsonl` 被内核之外的东西改过。`acknowledge`：人知悉并说明原因后继续，这次确认记入事件流；`abort`。不要自己去修那两个文件。

## stall

在途步骤超过阈值没有新进展。先确认子 agent 是否还在运行：不在了就 `continue` 后按 `flow next` 重新列出的工单重派；还在就 `continue` 接着等。

## budget

用量或耗时超过建案时给的预算。`raise`：加 `--budget-tokens` 或 `--budget-hours` 给新预算；`continue`：不再设预算；`abort`。

## legacy_pause / manual_pause

迁移前就处于暂停的旧案例，或人工暂停。`continue`：已处理，继续；`abort`。

## external_degraded / false_fail_rerun / redispatch

这三种不停下，只在事件流和看板里留痕：外审降级（替身或跳过）、按假 FAIL 重跑了一次 milestone 验证、限额内的重派。
