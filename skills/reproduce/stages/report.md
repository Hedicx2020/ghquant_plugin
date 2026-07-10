# stage: report（quant-reporter，sonnet）

汇总最终复现报告（人工 review 对象）。**只汇总，不新增结论、不重算指标。**

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage oos --assert-done` 必须 PASS（oos 为条件 stage，skipped 亦放行）。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> report running`
2. **记账写 state**（G-FN-6 依赖 coverage_stats.total > 0；reporter 不写 state，主会话据 coverage_matrix 机械计数后写）：
   ```
   uv run python tools/state.py set <id> coverage_stats '{"total":<N>,"done":<n>,"skipped":<n>,"infeasible":<n>,"pending":<n>}'
   ```
   （pending 应为 0——若非 0 说明仍有未终态要素，先回上游终态化再进报告。）确认 `verdict.result` 已在 verify/iterate 出口设好。
3. **派 `quant-reporter`**（subagent_type=`quant-reporter`）。输入合同：
   - `workspace/<id>/` 全部产物：`spec/{spec.md,coverage_matrix.md,ambiguities.md}`、`plan.md`、`assumptions.md`、`audit/`（extract_audit / impl_audit / evidence_manifest / audit_responses / 各 codex 原始输出）、`iterations/`（iteration_log.md + 全部 iter_NN/）
   - `output/<id>/results/comparison.json`、`output/<id>/verify_report.md`
   - **oos=done 时追加**：`workspace/<id>/oos_report.md`、`output/<id>/results/oos_metrics.json`（final_report 必含「样本外表现」章节——收录区间、逐指标对比、conclusion 与判读规则；G-FN 动态核验该章节。oos=skipped 时不追加，报告在复跑指引或残余章节一句话说明跳过原因）
   - state 的 `external_reviews` / `verdict` / `coverage_stats` 摘要（**由主会话在 prompt 里转述关键字段**，reporter 不直接读 state.json）
4. **点收输出合同**：`workspace/<id>/final_report.md`（8 个必需 H2 章节 + 附录 A 六小节 + 可信度评级 A/B/C）。
5. **渲染单文件展示页**（主会话跑工具，确定性渲染非内容生产）：
   ```
   uv run python tools/render_report.py <id>
   ```
   产出 `output/<id>/final_report.html`（自包含：指标对比总表可筛选、图表 base64 内嵌、样本外/审计台账/假设登记簿与报告全文折叠收录，浏览器直接打开可分享）。点收该文件存在。

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage report --record
```
原样贴输出。G-FN：G-FN-1 final_report.md 存在 / G-FN-2 必需 H2 章节齐（结论/指标对比/假设登记簿/迭代历史/审计回应/残余偏差/未复现清单/复跑指引；oos=done 时另须「样本外」章节）/ G-FN-3 coverage_matrix 无 pending/in_progress 行 / G-FN-4 假设登记簿无遗留占位符 `[verify 后填]` / G-FN-5 所有 rejected 意见出现在报告 / G-FN-6 state.coverage_stats.total > 0 / G-FN-7 final_report.html 单文件展示页存在且含指标对比总表。

VERDICT PASS → `set-stage <id> report done` → `set <id> status awaiting_review` → 进 review。

## 失败处理

- **G-FN-2 缺章节** → 把缺失章节名贴回 `quant-reporter` 补写重派。
- **G-FN-3 有 pending/in_progress 行** → 说明某要素未终态化（应 done 带实现+验证，或 skipped/infeasible 带理由）→ 回对应上游（coder/verifier/planner）终态化，不得让 reporter 代改。
- **G-FN-4 遗留占位符** → verify 阶段「验证后回看」未回填干净 → 回 `quant-verifier` 补填（reporter 不代填）。
- **G-FN-5 rejected 意见未现** → 回 reporter 把 audit_responses 中处置=rejected 的意见 ID 原样写入报告遗留清单。
- **G-FN-6 coverage_stats.total=0** → 主会话补跑步骤 2 的 `set coverage_stats`。
- **G-FN-7 缺 final_report.html** → 主会话补跑步骤 5 的 `render_report.py`（工具报错则按报错修 comparison/state 硬输入后重跑）。
