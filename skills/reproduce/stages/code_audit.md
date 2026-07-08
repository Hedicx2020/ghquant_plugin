# stage: code_audit（codex read-only 必跑；+ auditor mode=code 按难度）

实现忠实性外审：codex 逐点查未来函数/硬编码/方向反；medium 及 ml 标签补内审 auditor mode=code。**在 verify 之前拦截数值验证抓不到的作弊。**

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage implement --assert-done` 必须 PASS。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> code_audit running`
2. **备料**：
   - 生成 common 函数签名摘要落盘（供占位符 `{common_signatures_path}`），如 `workspace/<id>/audit/common_signatures.md`（`grep '^def ' common/*.py` 汇总即可）。
   - 从 spec.md 第五节抽全部 R 类基准数值字面量清单（供占位符 `{r_class_values_list}`，让 codex grep 硬编码 K1）。
3. **填 codex prompt**：读 `templates/codex_prompts/code_audit.md`，按文件头占位符清单填充（`{report_id}`/`{type}`/`{tags}`/`{difficulty}`/`{workspace}`/`{common_signatures_path}`/`{r_class_values_list}`），正文落盘 `workspace/<id>/audit/codex_prompt_code.md`。
4. **调 codex**（Bash，`timeout` 设 `600000`）：
   ```
   command codex exec -s read-only --skip-git-repo-check -C /Users/hedi/report_reproduce --color never --output-last-message "workspace/<id>/audit/code_audit_codex.md" - < "workspace/<id>/audit/codex_prompt_code.md"
   ```
5. **auditor mode=code**（补内审）：
   - **hard**：impl_audit 已在 implement 阶段逐 milestone 产出，无需重派（若缺则补派）。
   - **medium，或任何难度含 `ml` 标签**：派一次 `quant-auditor mode=code`（输入合同**不含 coder 完成汇报**：`spec.md`、`coverage_matrix.md`、`assumptions.md`、`src/<id>/` 全部、`common/` 相关模块、当前/全部 milestone id），产 `workspace/<id>/audit/impl_audit_m{X}.md`。
   - **easy 非 ml**：auditor(code) 并入 verify（抽 2 条核心要素），本 stage 不单独产 impl_audit。
   - 提速可选：本步 auditor 与第 4 步 codex 并行发起。
6. **意见入 responses**：`code_audit_codex.md` 每条 `CDX-C-` finding 逐条录入 `workspace/<id>/audit/audit_responses.md`（同一张表追加）。impl_audit 若出现 `not_found`（空壳虚报）→ auditor 已在 coverage_matrix 变更日志记回退（状态打回 in_progress），主会话据此回 coder 重做该要素。
7. **记外审台账**（读改写三步，同 `spec_audit.md` 步骤 8；**警告**：`state.py set` 是整体覆盖字段，直接 `set` 单条数组会把 spec 审查已写入的记录抹掉）：
   1. **读**：`Read workspace/<id>/state.json`，取出现有 `external_reviews` 数组。
   2. **追加**：数组末尾追加 `{"checkpoint":"code","engine":"codex","verdict":"<pass|pass_with_issues|fail>","critical":<n>,"major":<n>,"minor":<n>,"raw":"workspace/<id>/audit/code_audit_codex.md"}`。
   3. **整体写回**：`uv run python tools/state.py set <id> external_reviews '<合并后完整 JSON 数组>'`。

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage code_audit --record
```
原样贴输出。G-CA：G-CA-1 code_audit_codex.md / audit_responses.md 存在 / G-CA-2 impl_audit_m{X}.md 存在（按难度/ml 要求，easy 非 ml 免）/ G-CA-3 impl_audit 文件中**无 not_found** / G-CA-4 CDX-C- 回应行数 == code 审查 issues 数 / G-CA-5 无 open critical（未来函数/硬编码/方向反）/ G-CA-6 无 open major 未回应。

VERDICT PASS → `set-stage <id> code_audit done` → 进 verify。

## 失败处理

- **critical**（未来函数/硬编码/方向反/空壳 not_found）→ 回 `quant-coder` 修复（只改问题文件）→ codex 复审（复审输入=修复 diff + 原意见 + 定位文件，缩减 prompt）→ 复核列写 `pass`。**同一审查点审→修→复审最多 3 轮，仍有 critical → paused_blocked**。修复计入迭代账（若已进 verify 后回来，见 iterate）。
- **G-CA-3 命中 not_found** → 对应实现是空壳，回 coder 真正实现该要素，矩阵状态回 in_progress → done；**coder 补实现后必须重派 `quant-auditor mode=code` 覆盖重写对应的 `impl_audit_m{X}.md`（不是在旧文件上增补一行了事）**，复审干净（不再命中「判定: not_found」）才能重过 G-CA 门禁——否则旧文件里残留的 `判定: not_found` 行会让门禁永远 FAIL，即便实现已经修好（陈旧文件死锁）。
- **codex 调用失败** → 重试 1 次缩减输入（代码审只喂 `strategy.py`）；再失败两级降级（claude_fallback → skipped，同 spec_audit 失败处理，engine 记入 external_reviews）。
