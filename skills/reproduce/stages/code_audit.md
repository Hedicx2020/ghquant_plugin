# stage: code_audit（异构只读外审；+ auditor mode=code 按难度）

实现忠实性外审：异构引擎逐点查未来函数/硬编码/方向反；medium 及 ml 标签补内审 auditor mode=code。

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage implement --assert-done` 必须 PASS。


> **外审档位触发判定（audit_level=standard 时先执行；strict 跳过本框直接全跑）**：
> `audit_level=standard` 时，仅在 `tags` 含 ml、difficulty=hard 或内审抓到 critical 时运行外审。不触发则写 `code_audit_external.md` skipped 占位并记配置性 skipped。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> code_audit running`
2. **备料**：
   - 生成 common 函数签名摘要落盘（供占位符 `{common_signatures_path}`），如 `workspace/<id>/audit/common_signatures.md`（`grep '^def ' common/*.py` 汇总即可）。
   - 从 spec.md 第五节抽全部 R 类基准数值字面量清单（供外审 grep 硬编码 K1）。
3. **填外审 prompt**：读 `templates/codex_prompts/code_audit.md`，填充全部占位符，正文落 `workspace/<id>/audit/external_prompt_code.md`。
4. **调异构外审**：
   ```
   REPORT_REPRODUCE_ROOT="$PWD" uv run python "$REPRODUCE_TOOLS/external_review.py" --engine <EXTERNAL_ENGINE> --prompt "workspace/<id>/audit/external_prompt_code.md" --output "workspace/<id>/audit/code_audit_external.md" --cwd "$PWD" --timeout 600
   ```
   仅 stdout JSON 的 `status=success` 进入意见处置；否则走 spec_audit 卡的异构外审降级链。
5. **auditor mode=code**（补内审）：
   - **hard**：impl_audit 已在 implement 阶段逐 milestone 产出，无需重派（若缺则补派）。
   - **medium，或任何难度含 `ml` 标签**：派一次 `quant-auditor mode=code`（输入合同**不含 coder 完成汇报**：`spec.md`、`coverage_matrix.md`、`assumptions.md`、`src/<id>/` 全部、`common/` 相关模块、当前/全部 milestone id），产 `workspace/<id>/audit/impl_audit_m{X}.md`。
   - **easy 非 ml**：auditor(code) 并入 verify（抽 2 条核心要素），本 stage 不单独产 impl_audit。
   - 本步 auditor 与第 4 步异构外审默认同批并行。
   - **并行加派 verifier**：medium/hard 默认与外审同批，easy 或 ml 串行；本阶段不点收、不写 verify state。
6. **意见入 responses**：`code_audit_external.md` 每条 `CDX-C-` finding 逐条录入 `audit_responses.md`。impl_audit 命中 `not_found` 则回 coder 真正实现。
7. **记外审台账**（读改写三步，同 `spec_audit.md` 步骤 8；**警告**：`state.py set` 是整体覆盖字段，直接 `set` 单条数组会把 spec 审查已写入的记录抹掉）：
   1. **读**：`Read workspace/<id>/state.json`，取出现有 `external_reviews` 数组。
   2. **追加**：数组末尾追加 `{"checkpoint":"code","engine":"<EXTERNAL_ENGINE_STATE>","verdict":"<pass|pass_with_issues|fail>","critical":<n>,"major":<n>,"minor":<n>,"raw":"workspace/<id>/audit/code_audit_external.md"}`；降级时 engine=`same_host_fallback` 并写 reason。
   3. **整体写回**：`uv run python tools/state.py set <id> external_reviews '<合并后完整 JSON 数组>'`。

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage code_audit --record
```
原样贴输出。G-CA-1 使用 `code_audit_external.md`（兼容历史名），G-CA-2～6 语义不变。

VERDICT PASS → `set-stage <id> code_audit done` → 进 verify。

## 失败处理

- **并行模式下 critical 修复涉及 `src/` 改动** → 本次预跑 verify 产物作废（G-VF-6 新鲜度机器判 FAIL 兜底），进 verify 阶段时重派 verifier。

- **critical**（未来函数/硬编码/方向反/空壳）→ 回 `quant-coder` 定向修复 → 用同一异构引擎复审修复 diff；最多 3 轮，仍有 critical 则 paused_blocked。
- **G-CA-3 命中 not_found** → 对应实现是空壳，回 coder 真正实现该要素，矩阵状态回 in_progress → done；**coder 补实现后必须重派 `quant-auditor mode=code` 覆盖重写对应的 `impl_audit_m{X}.md`（不是在旧文件上增补一行了事）**，复审干净（不再命中「判定: not_found」）才能重过 G-CA 门禁——否则旧文件里残留的 `判定: not_found` 行会让门禁永远 FAIL，即便实现已经修好（陈旧文件死锁）。
- **外部 CLI 失败** → 走 `stages/spec_audit.md`「异构外审降级链」。本卡缩减重试只喂 `strategy.py`，替身输出 `code_audit_external.md`，无标记块要求。
