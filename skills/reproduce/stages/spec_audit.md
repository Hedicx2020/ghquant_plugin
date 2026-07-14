# stage: spec_audit（异构外审 ∥ quant-auditor mode=spec，medium+）

外部交叉验证提取质量：异构引擎执行两阶段盲提取协议 + （medium/hard）内审 auditor。外部引擎由主技能宿主识别确定。

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage plan --assert-done` 必须 PASS。


> **外审档位触发判定（audit_level=standard 时先执行；strict 跳过本框直接全跑）**：
> 读 cwd `.reproduce.json` 的 `audit_level`。为 `standard` 时，盲提取外审仅当满足任一触发条件才跑：① `ambiguities.md` 含 blocking 或 major；② state 的 `type` 是本目录首次完成的类型；③ difficulty=hard。
> **不触发时的 skipped 落档协议**：落 `spec_audit_external.md`、`spec/spec_external.md`、`spec/extract_diff.md` 三个明示占位档；external_reviews 追加 `engine=skipped`、reason=`audit_level=standard 未触发`。内审照常执行，配置性 skipped 不封顶。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> spec_audit running`
2. **填外审 prompt**：读 `templates/codex_prompts/spec_audit.md`（目录名为历史兼容保留），填充占位符，正文落 `workspace/<id>/audit/external_prompt_spec.md`。
3. **调异构外审**（medium+ 可与第 5 步 auditor 并行）：
   ```
   REPORT_REPRODUCE_ROOT="$PWD" uv run python "$REPRODUCE_TOOLS/external_review.py" --engine <EXTERNAL_ENGINE> --prompt "workspace/<id>/audit/external_prompt_spec.md" --output "workspace/<id>/audit/spec_audit_external.md" --cwd "$PWD" --timeout 600
   ```
   解析 stdout JSON；仅 `status=success` 进入下一步，其他状态走本卡降级链。
4. **切出盲提取清单**：从 `spec_audit_external.md` 中把历史兼容标记 `=== SPEC_CODEX_BEGIN ===` / `=== SPEC_CODEX_END ===` 之间的内容原样存为 `workspace/<id>/spec/spec_external.md`。
5. **（medium+）派 `quant-auditor mode=spec`**：可与第 3 步异构外审并行，必须两者都返回再记账。输入合同不含 extractor/planner 完成汇报；产出 `extract_audit.md`（C1–C6、遗漏清单、C6 抽查 ≥10 条、末行 verdict）。easy 跳过内审。
6. **记账产 `extract_diff.md`**：逐条列出 `spec_external.md` 与 `spec.md` 差异，裁决照录 `extract_audit.md` 或 `spec_audit_external.md` 的结论；两者都未覆盖的项派 `quant-extractor` 定向复核。表头逐字：`| DIF-01 | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |`，每条 DIF 的裁决列必须非空。
   - 仅外部盲提取有 → 审计核实确有则 adopted，派回 extractor 补 spec；外审幻觉则 dismissed 留记录。
   - 仅主规格有 → 审计核实无碍则 dismissed；主规格幻觉则 critical。
   - R 类数值不一致 → 以 PDF 原文为终审（判断属异构外审/auditor 范围，主会话只登记）。
   **每条 DIF 行「裁决」列必须非空**（G-SA-3）。
7. **意见入 responses**：把 `spec_audit_external.md` 的每条 `CDX-S-` finding 逐条录入 `audit_responses.md`；一条意见一行，不合并不省略。`CDX` 前缀仅为历史稳定 ID，不代表实际引擎。
8. **记外审台账**（读改写三步；**警告**：`state.py set` 是整体覆盖字段，直接 `set` 单条数组会把此前已写入的审查记录全部抹掉，三步缺一不可）：
   1. **读**：`state.py show` 无 `--json` 参数，不能取结构化字段，故直接 `Read workspace/<id>/state.json`，取出其中 `external_reviews` 数组的现有内容。
   2. **追加**：在数组末尾追加 `{"checkpoint":"spec","engine":"<EXTERNAL_ENGINE_STATE>","verdict":"<pass|pass_with_issues|fail>","critical":<n>,"major":<n>,"minor":<n>,"raw":"workspace/<id>/audit/spec_audit_external.md"}`；降级时 engine 改 `same_host_fallback` 并写 reason。
   3. **整体写回**：`uv run python tools/state.py set <id> external_reviews '<①读出的旧数组与②新条目合并后的完整 JSON 数组>'`（reporter 的 A.3 靠它；后续 code/result 审查复用同一读改写三步各追一条）。

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage spec_audit --record
```
原样贴输出。G-SA-1 核 `spec_external.md/extract_diff.md/spec_audit_external.md`（门禁兼容历史名）；其余 G-SA-2～6 语义不变。

VERDICT PASS → `set-stage <id> spec_audit done` → 进 implement。

## 失败处理

- **critical / 未回应 major** → 回派 extractor（提取问题）或 planner（计划问题）定向修复后复审，修复意见复核列写 `pass`；**同一审查点审→修→复审最多 3 轮，仍有 critical → paused_blocked**（brief：修复轮 >2 即停）。

### 异构外审降级链（正本）

适用 `external_review.py` 返回的所有非 success 状态，外审不因此断链。

1. **重试判断**：`quota_error` / `auth_error` / `unavailable` 直接降级；`timeout` / `failed` / `empty_output` 缩减输入重试一次，再失败降级。未安装可在本案例后续检查点沿用，临时错误不得沿用。
2. **一级降级**：严格按当前宿主适配卡的“同宿主降级”执行同一份已填充 prompt。替身只读输入合同文件、禁读过程叙事、不嵌套派发，输出仍写 `*_external.md`；台账 `engine=same_host_fallback` 并记录 reason。
3. **spec 特殊合同**：替身输出必须含历史兼容 `SPEC_CODEX` 标记块，主会话切成 `spec_external.md`。
4. **二级降级：skipped**：替身也不可行（罕见）→ 按 audit_level=standard 的 skipped 占位档格式落文件（`verdict:"skipped"` + reason + `findings:[]`），`engine` 记 `skipped`，final_report 显著标注「该审查点外审缺失」。
5. **评级口径**：`same_host_fallback` 或失败性 skipped 均封顶 B；配置性 skipped 不封顶。外部 CLI 恢复后下一检查点自动回异构主路径。
