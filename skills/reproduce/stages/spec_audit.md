# stage: spec_audit（codex 必跑 ∥ quant-auditor mode=spec，medium+）

外部交叉验证提取质量：codex 单会话两阶段盲提取协议 + （medium/hard）内审 auditor。**codex 三审查点对所有难度必跑。**

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage plan --assert-done` 必须 PASS。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> spec_audit running`
2. **填 codex prompt**：读 `templates/codex_prompts/spec_audit.md`，按其文件头占位符清单填充（`{report_id}`=<id>、`{market}`、`{type_hint}`、`{difficulty}` 取自 state/spec.md，`{workspace}`=`workspace/<id>`），把「传给 codex 的正文开始」之后的正文落盘为 `workspace/<id>/audit/codex_prompt_spec.md`。
3. **调 codex**（Bash，`timeout` 设 `600000`；medium+ 可与第 5 步 auditor **并行**同一消息发起）：
   ```
   command codex exec -s read-only --skip-git-repo-check -C /Users/hedi/report_reproduce --color never --output-last-message "workspace/<id>/audit/spec_audit_codex.md" - < "workspace/<id>/audit/codex_prompt_spec.md"
   ```
4. **切出盲提取清单**：从 `spec_audit_codex.md` 中把 `=== SPEC_CODEX_BEGIN ===` 与 `=== SPEC_CODEX_END ===` 之间的内容原样存为 `workspace/<id>/spec/spec_codex.md`。
5. **（medium+）派 `quant-auditor mode=spec`**（subagent_type=`quant-auditor`，prompt 里写明 `mode=spec`；可与第 3 步 codex 同一消息并行发起，**两者都返回后**再做第 6 步记账）。输入合同（**不含 extractor/planner 的完成汇报**）：PDF `reports/<id>.pdf`、`report_text.md`、`tables_extracted.md`、`spec.md`、`coverage_matrix.md`、`ambiguities.md`、`plan.md`、`templates/audit/extract_audit.md`。产出 `workspace/<id>/audit/extract_audit.md`（C1–C6 + 遗漏清单 + C6 抽查 ≥10 条 + 末行 verdict）。**easy 跳过内审。**
6. **记账产 `extract_diff.md`**（主会话审计记账登记，**不属内容生产**——裁决结论取自 codex/auditor 的审计产物，主会话只登记与路由；落盘 `workspace/<id>/spec/extract_diff.md`）：逐条列出 spec_codex.md 与 spec.md 的差异项，「裁决」列**照录审计结论**，来源按难度区分：
   - **medium/hard**：优先取第 5 步 `quant-auditor mode=spec` 产出的 `extract_audit.md`「遗漏清单」/findings 结论（该项已由 auditor 独立核实）；`extract_audit.md` 未覆盖到的 DIF 项，退而取 `spec_audit_codex.md` 阶段二「盲提取 diff」分析结论（codex 自审的诊断，见 `templates/codex_prompts/spec_audit.md` 阶段二步骤 1）。两者都未覆盖的极少数剩余 DIF 项 → 派回 `quant-extractor` 定向复核，不由主会话自行判定。
   - **easy**（无 auditor mode=spec 内审，不适用上述区分）：裁决直接取 `spec_audit_codex.md` 阶段二「盲提取 diff」分析结论。
   表头逐字：`| DIF-01 | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |`（「依据」列注明结论来源，如「依据 extract_audit.md GAP-03」/「依据 spec_audit_codex.md 阶段二diff」）。
   - 仅 codex 有 → 审计结论确有 = Claude 遗漏（adopted，派回 extractor 补 spec，日志记来源）；审计结论系 codex 幻觉（dismissed 留记录）。
   - 仅 Claude 有 → 审计结论对 spec 无碍（dismissed，可提示补 tables_extracted）；审计结论系 Claude 幻觉（critical）。
   - R 类数值不一致 → 以 PDF 原文为终审（corrected，该终审判断属 codex/auditor 审计范围，主会话只登记）。
   **每条 DIF 行「裁决」列必须非空**（G-SA-3）。
7. **意见入 responses**：把 `spec_audit_codex.md` 的每条 `CDX-S-` finding 逐条录入 `workspace/<id>/audit/audit_responses.md`（表头：`意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核`）。一条意见一行，不合并不省略；adopted 遗漏 → 派回 `quant-extractor`（或 planner）定向修复，复核列写 `pass`；rejected 给技术理由。extract_audit 的内审 issue 一并处置。
8. **记外审台账**（读改写三步；**警告**：`state.py set` 是整体覆盖字段，直接 `set` 单条数组会把此前已写入的审查记录全部抹掉，三步缺一不可）：
   1. **读**：`state.py show` 无 `--json` 参数，不能取结构化字段，故直接 `Read workspace/<id>/state.json`，取出其中 `external_reviews` 数组的现有内容。
   2. **追加**：在该数组**末尾**追加本 checkpoint 一条：`{"checkpoint":"spec","engine":"codex","verdict":"<pass|pass_with_issues|fail>","critical":<n>,"major":<n>,"minor":<n>,"raw":"workspace/<id>/audit/spec_audit_codex.md"}`。
   3. **整体写回**：`uv run python tools/state.py set <id> external_reviews '<①读出的旧数组与②新条目合并后的完整 JSON 数组>'`（reporter 的 A.3 靠它；后续 code/result 审查复用同一读改写三步各追一条）。

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage spec_audit --record
```
原样贴输出。G-SA：G-SA-1 codex 盲提取/diff/审查产物齐（spec_codex.md/extract_diff.md/spec_audit_codex.md）/ G-SA-2 extract_audit.md（medium/hard 必跑，easy 跳过）/ G-SA-3 extract_diff 所有 DIF 行裁决列非空 / G-SA-4 audit_responses 中 CDX-S- 回应行数 == spec 审查 issues 数 / G-SA-5 无 open critical / G-SA-6 major 全部有回应。

VERDICT PASS → `set-stage <id> spec_audit done` → 进 implement。

## 失败处理

- **critical / 未回应 major** → 回派 extractor（提取问题）或 planner（计划问题）定向修复后复审，修复意见复核列写 `pass`；**同一审查点审→修→复审最多 3 轮，仍有 critical → paused_blocked**（brief：修复轮 >2 即停）。
- **codex 调用失败**（非零退出/超时/输出为空）→ **重试 1 次并缩减输入**（spec 审只喂 R 类章节 + 图表清单）。
- **重试仍失败 → 两级降级**：
  1. 一级：派**全新 Claude 子 agent 作外审替身**（同材料同 prompt，禁止读任何过程性文件），把结论写入 `spec_audit_codex.md`，`external_reviews` 该条 `engine` 记 `claude_fallback`。**替身输出同样必须包含 `=== SPEC_CODEX_BEGIN ===` / `=== SPEC_CODEX_END ===` 标记块**（G-SA-1 需要靠它切出 `spec_codex.md`，替身若漏写此标记则本步骤第 4 步无法切出盲提取清单，直接导致 G-SA-1 FAIL）。
  2. 二级：替身也不可行 → `engine` 记 `skipped`，final_report 显著标注「该审查点外审缺失」，**hard 报告可信度评级封顶 B**。
