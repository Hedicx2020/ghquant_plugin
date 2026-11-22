# iterate（迭代修正）

验证首轮全部达标时跳过。否则每一轮：

1. 内核开轮：存一份修改前的对比结果；第 2 轮起生成诊断摘要 `iterations/iter_NN/digest.md`（未达标指标的偏差趋势、连续两轮改善不到一成的预警、历史诊断里「已排除假设」的原文摘录）。
2. 第 2 轮起先跑一次异构第二意见（后台外审），供诊断者参考，不必采纳。
3. `iterate.rN.diagnose`：诊断者锁定不超过两个修改点，结论三选一。
4. `continue` → `iterate.rN.fix`（coder 只改锁定的点）→ `iterate.rN.verify`（整批重出）→ 内核重算：全部达标即结束；否则下一轮。
5. `stop_partial` → 不改代码，按部分达标结束，诊断者为每条未达标指标回填归因状态。
6. `blocked` → 开 `iterate_blocked` 检查点交给人。

到轮数上限仍有超差：派一次收尾归因（`iterate.final.attribution`），结论记为部分达标。部分达标是合法结论，不要为了达标继续加轮。

## 诊断没有结论行

`diagnosis.md` 里找不到「结论: continue / stop_partial / blocked」：重派诊断（计入重派次数）。

## G-IT-1

某一轮目录下三件套不齐（`diagnosis.md`、`changes.md`、`comparison.json`；结论是 stop_partial 或 blocked 的那一轮可以没有 `changes.md`）。派 `iterate.gatefix`（诊断者）补。

## G-IT-2

轮数超过上限。正常流程不会出现，出现说明状态被改过。内核照常派 `iterate.gatefix`，修不了会停在检查点交给人。

## G-IT-3

第 2 轮起的诊断没有「已排除假设」一节。派 `iterate.gatefix`（诊断者）补写：这是防止兜圈的硬要求。

## iterate_round

interactive 模式下，一轮结束且还要继续下一轮时停一次；单步模式每轮都停。
