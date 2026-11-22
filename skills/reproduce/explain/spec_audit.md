# spec_audit（规格审计）

同批发出：外审盲提取（`spec_audit.ext.r1`，后台）与规格内审（`spec_audit.internal`，medium / hard 才有）。都回来后进入「裁决 → 修复 → 复审」循环，见 `flow explain review_cycle`。

盲提取分两次调用：第一次只给研报原文与表格，第二次才给 spec 与第一次的产出。`audit_level=standard` 时只有命中触发条件（有 blocking / major 歧义、难度 hard、该类型的第一份案例）才跑外审。

## G-SA-1

外审产物不齐。外审失败时内核会走降级链（替身、跳过）并把结果记进台账，这一项随之满足；仍然不过说明汇总没有做成，内核会重新汇总。

## G-SA-2

medium / hard 缺内审记录 `audit/extract_audit.md`。重派 `spec_audit.internal`。

## G-SA-3

`audit/extract_diff.md` 里还有 DIF 行没有裁决。裁决工单里会列出待裁决的 DIF；答卷漏了就补。

## G-SA-4、G-SA-6

回应表的行数与外审意见数对不上，或有 major 没回应。内核重新汇总并重发裁决工单，把漏的补上。

## G-SA-5

还有 critical 没闭环。接受的 critical 修完后要经下一轮复审确认；3 轮仍未闭环开 `review_rounds_exhausted`。
