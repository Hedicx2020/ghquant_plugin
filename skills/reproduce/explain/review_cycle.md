# 外审循环

规格审计、代码审计、结果审计三处共用同一套循环，每一轮：

1. **外审**（`<阶段>.ext.r<N>`，exec 工单）：`flow exec … --detach` 后 `flow wait`。输入包、推理强度、是否差量都由内核定。第 2 轮起默认只给差量包（上一轮的意见与回应、改动处的差异），改动面过大时自动整体重审。
2. **汇总**（内核）：解析外审输出，与内审意见合并入 `audit/audit_responses.md`；规格审计另把盲提取差异投影成 `audit/extract_diff.md`。
3. **裁决**（`<阶段>.rule.r<N>`，judge 工单）：你逐条给处置。
4. **修复**（`<阶段>.fix.<角色>.r<N>`）：按 owner 派给对应角色，回执里逐条写改了哪里；结果审计里 coder 改过代码后内核会让验证整批重出。
5. **回应表回填**（内核），有 critical 被接受时进入下一轮复审；没有就收口过门禁。

## rule

答卷写到工单的 `answer_file`：

```json
{"findings": {"CDX-C-01": {"处置": "accepted", "回应": "改用披露日对齐", "owner": "quant-coder"}},
 "diffs": {"DIF-03": {"裁决": "adopted", "依据": "原文表 4 第 2 行", "owner": "quant-extractor"}}}
```

- 处置取 `accepted` / `rejected` / `deferred`；critical、major 必须写回应。
- accepted 必须写 owner：规格审计 `quant-extractor` 或 `quant-planner`，代码审计 `quant-coder`，结果审计 `quant-coder`、`quant-verifier`（文书、图表、对比表）或 `quant-diagnoser`（归因）；不需要改任何文件写 `none`。
- **critical 不能 rejected 或 deferred**。你确实认为不成立就照实填，内核开 `critical_dispute` 检查点交给人裁决。
- DIF 的裁决取 `adopted`（采纳盲提取）/ `dismissed`（不采纳）/ `corrected`（两边都不对，另行更正）。
- 只凭工单里的意见摘要判断；需要核对细节时才打开原件。被审方与内审方的自述不作依据。

## fallback

外审自己会先重试一次，输入不缩减：超时就降一档推理强度再跑；普通失败或结论解析不出来原样再跑；额度、鉴权、引擎没装这三种不重试。仍不行就给一张同宿主替身工单（`<阶段>.ext.r<N>.fallback`，角色 `general-purpose`）。照常派发，必须是没有任何历史上下文的新子 agent。台账记 `same_host_fallback`，评级封顶 B。替身也交不出来，这一轮记为跳过（`skipped`，同样封顶 B），流程继续，不用停下问人。

外审任务连提示词都没准备出来（模板缺占位符等）时没有东西可交给替身，这一轮直接记为跳过。

提示里出现「输入包超出了外审引擎的上下文窗口」：把 `.reproduce.json` 的 `external_review.input_budget_kb` 调小（默认 codex 320、claude 200，单位 KB），放不进包的文件会改为只列路径，审查方按需自己读。这种失败不重试，直接走替身。

`audit_level=standard` 下没触发的外审记为配置性跳过，不封顶。结果外审任何档位都跑。

## 复审超限

连续 3 轮仍有 critical 没闭环，开 `review_rounds_exhausted` 检查点交给人。
