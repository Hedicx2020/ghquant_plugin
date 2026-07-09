# stage: result_audit（codex read-only 必跑 ∥ quant-auditor mode=result，hard 必跑）

结果反虚报外审：核查「结论有没有编」（数字不实 / 漏对比项 / 归因造假），不重判达标。

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage iterate --assert-done` 必须 PASS（iterate done，或首轮达标时 iterate=skipped 亦放行）。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> result_audit running`
2. **填 codex prompt**：读 `templates/codex_prompts/result_audit.md`，按文件头占位符填充（`{report_id}`/`{type}`/`{difficulty}`/`{iteration_current}`/`{iteration_max}`/`{comparison_path}`=`output/<id>/results/comparison.json`/`{workspace}`=`workspace/<id>`），正文落盘 `workspace/<id>/audit/codex_prompt_result.md`。
3. **调 codex**（Bash，`timeout` 600000）：
   ```
   command codex exec -s read-only --skip-git-repo-check -C /Users/hedi/report_reproduce --color never --output-last-message "workspace/<id>/audit/result_audit_codex.md" - < "workspace/<id>/audit/codex_prompt_result.md"
   ```
4. **auditor mode=result**（**hard 必跑**；medium/easy 仅 K2 触发时）：派 `quant-auditor mode=result`。输入合同：`output/<id>/results/comparison.json`、`output/<id>/results/`（PNG 图片、metrics.json、backtest_summary.xlsx）、`workspace/<id>/audit/evidence_manifest.md`（输出对象）、`output/<id>/verify_report.md`、`assumptions.md`、`ambiguities.md`、`coverage_matrix.md`。产出：在 `evidence_manifest.md` 追加「反虚报复核」节（K2/K3/E4 复核 + skip/infeasible 理由核实 + 扰动测试触发判断 + 末行 verdict）。可与第 3 步 codex 并行。
5. **意见入 responses**：`result_audit_codex.md` 每条 `CDX-R-` finding 逐条录入 `audit_responses.md`（同表追加）。
6. **记外审台账**（读改写三步，同 `spec_audit.md` 步骤 8；**警告**：`state.py set` 是整体覆盖字段，直接 `set` 单条数组会把 spec/code 两条已有记录抹掉）：
   1. **读**：`Read workspace/<id>/state.json`，取出现有 `external_reviews` 数组。
   2. **追加**：数组末尾追加 `{"checkpoint":"result","engine":"codex","verdict":"<pass|pass_with_issues|fail>","critical":<n>,"major":<n>,"minor":<n>,"raw":"workspace/<id>/audit/result_audit_codex.md"}`。
   3. **整体写回**：`uv run python tools/state.py set <id> external_reviews '<合并后完整 JSON 数组>'`。

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage result_audit --record
```
原样贴输出。G-RA：G-RA-1 result_audit_codex.md / audit_responses.md 存在 / G-RA-2 无 open critical（数字不符/漏对比项/归因造假）/ **G-RA-3 超差指标归因状态 ∈ {accepted, assumption_linked}**（partial 时由 diagnoser 收尾模式回填 comparison.json，见 iterate 卡）/ G-RA-4 扰动测试有记录（hard 必做一次）/ G-RA-5 CDX-R- 回应行数 == result 审查 issues 数。

VERDICT PASS → `set-stage <id> result_audit done` → 进 report。

## 失败处理

- **数字不实（critical：comparison 与原始产物 xlsx/metrics.json 不符）** → 回 verify 重出（重跑 verifier 覆盖产物），本 stage 复审。
- **代码问题（超差归因指向实现缺陷）** → 计入迭代轮：回 iterate 再跑一轮（若未超 max_iter），收敛后重回本 stage。
- **G-RA-3 超差指标缺 attribution_status** → 回 `quant-diagnoser`（收尾模式）为每条 pass=false 指标补 accepted/assumption_linked。
- **G-RA-4 hard 缺扰动测试记录** → 回 `quant-verifier` 补做一次扰动测试并记入 evidence_manifest。
- **codex 调用失败** → 重试 1 次缩减输入；再失败两级降级（claude_fallback → skipped，记 external_reviews；hard 缺外审 → 报告可信度封顶 B）。
- 同一审查点审→修→复审最多 3 轮，仍有 critical → paused_blocked。
