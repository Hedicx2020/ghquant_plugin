# stage: result_audit（异构只读外审必跑 ∥ quant-auditor mode=result，hard 必跑）

结果反虚报外审：核查「结论有没有编」（数字不实 / 漏对比项 / 归因造假），不重判达标。

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage iterate --assert-done` 必须 PASS（iterate done，或首轮达标时 iterate=skipped 亦放行）。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> result_audit running`
2. **实验模式 prompt 附加段**：state.reproduction_mode=experimental 时，在外审与 auditor prompt 末尾附加市场迁移审查边界：偏差本身不算问题，重点核数字真实性、替代数据登记和结论不过度。
3. **填外审 prompt**：读 `templates/codex_prompts/result_audit.md`，填充占位符，正文落 `workspace/<id>/audit/external_prompt_result.md`。
4. **调异构外审**：
   ```
   REPORT_REPRODUCE_ROOT="$PWD" uv run python "$REPRODUCE_TOOLS/external_review.py" --engine <EXTERNAL_ENGINE> --prompt "workspace/<id>/audit/external_prompt_result.md" --output "workspace/<id>/audit/result_audit_external.md" --cwd "$PWD" --timeout 600
   ```
   仅 status=success 进入意见处置；失败必须先走同宿主独立盲审，不得直接 skipped。
5. **auditor mode=result**（hard 必跑；medium/easy 仅 K2 触发）：按原输入合同派发并追加 evidence_manifest，可与第 4 步异构外审并行。
6. **并行加派 oos-analyst（可选提速，SKILL.md 五.5）**：`stages/oos.md` 的触发判定前移到本阶段执行——verdict ∈ {pass, partial} 时与第 4/5 步同批加派 `quant-oos-analyst`（输入合同逐字取 `stages/oos.md` 步骤 2，含 economy sonnet 覆盖）；其产物在 oos 阶段点收，本阶段不点收、不写 oos 相关 state。**若本阶段发现数字不实 critical 回 verify 重出 comparison → oos 产物作废**（基线已变），oos 阶段重派。verdict 不满足时不加派，oos 阶段照常走 skipped 分支。
7. **意见入 responses**：`result_audit_external.md` 每条 `CDX-R-` finding 逐条录入 `audit_responses.md`。
8. **记外审台账**（读改写三步，同 `spec_audit.md` 步骤 8；**警告**：`state.py set` 是整体覆盖字段，直接 `set` 单条数组会把 spec/code 两条已有记录抹掉）：
   1. **读**：`Read workspace/<id>/state.json`，取出现有 `external_reviews` 数组。
   2. **追加**：数组末尾追加 `{"checkpoint":"result","engine":"<EXTERNAL_ENGINE_STATE>","verdict":"<pass|pass_with_issues|fail>","critical":<n>,"major":<n>,"minor":<n>,"raw":"workspace/<id>/audit/result_audit_external.md"}`；降级时 engine=`same_host_fallback` 并写 reason。
   3. **整体写回**：`uv run python tools/state.py set <id> external_reviews '<合并后完整 JSON 数组>'`。

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage result_audit --record
```
原样贴输出。G-RA-1 使用 `result_audit_external.md`（兼容历史名），G-RA-2～5 语义不变。

VERDICT PASS → `set-stage <id> result_audit done` → 进 report。

## 失败处理

- **数字不实（critical：comparison 与原始产物 xlsx/metrics.json 不符）** → 回 verify 重出（重跑 verifier 覆盖产物），本 stage 复审。
- **代码问题（超差归因指向实现缺陷）** → 计入迭代轮：回 iterate 再跑一轮（若未超 max_iter），收敛后重回本 stage。
- **G-RA-3 超差指标缺 attribution_status** → 回 `quant-diagnoser`（收尾模式）为每条 pass=false 指标补 accepted/assumption_linked。
- **G-RA-4 hard 缺扰动测试记录** → 回 `quant-verifier` 补做一次扰动测试并记入 evidence_manifest。
- **外部 CLI 失败** → 走 spec_audit 卡「异构外审降级链」。缩减重试只喂 `comparison.json`、`verify_report.md`、`evidence_manifest.md`，替身输出 `result_audit_external.md`。result 是反虚报最后防线，必须先试一级替身。
- 同一审查点审→修→复审最多 3 轮，仍有 critical → paused_blocked。
