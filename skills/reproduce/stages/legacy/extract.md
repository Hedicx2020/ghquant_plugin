# stage: extract（quant-extractor，opus）

忠实提取研报要素，产 spec 三件套（页码引用制，不做复现设计）。

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage init --assert-done` 必须 PASS。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> extract running`
2. **派 `quant-extractor`**（`Agent`，subagent_type=`quant-extractor`）。prompt 里给全其**输入合同**（逐字，缺一 agent 会停）：
   - PDF 路径：`reports/<id>.pdf`（若 PDF 不在此名下，给 state.pdf_path 的实际路径）
   - `workspace/<id>/spec/report_text.md`
   - `workspace/<id>/spec/tables_extracted.md`
   - `templates/_spec_template.md`
   - `templates/audit/coverage_matrix.md`
   - `templates/audit/ambiguities.md`
   - `pdf_pages`：`<n_pages>`（state.pdf_pages 的值）
3. **点收输出合同**（逐一 `ls -la`，缺一即失败）：
   - `workspace/<id>/spec/spec.md`
   - `workspace/<id>/spec/coverage_matrix.md`
   - `workspace/<id>/spec/ambiguities.md`

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage extract --record
```
原样贴输出。G-EX 逐条：
- G-EX-1 spec.md 存在
- G-EX-2 frontmatter 可解析（yaml）
- G-EX-3 frontmatter 必填字段齐全非空
- G-EX-4 **三方一致**：正文正则计数 == frontmatter element_counts 汇总 == coverage_matrix 数据行数
- G-EX-5 每条要素块含「- 页码:」与「- 原文:」行
- G-EX-6 R 类要素 ≥ 1
- G-EX-7 ambiguities.md 存在
- G-EX-8 图表登记清单：FIG+EX/TBL 行数与 element_counts 一致，最大编号不超过 exhibit_declared

VERDICT PASS → `set-stage <id> extract done` → 进 plan。

## 失败处理

- 任一 FAIL → **带缺失项重派 1 次**：把 gate 的 FAIL 原文（含具体缺失 ID/计数不符）贴给 `quant-extractor` 让其定向补齐（如三方计数不符补对齐 element_counts、缺页码原文回原页补摘录）。
- 重派后仍 FAIL → `set <id> status paused_blocked` + `set <id> pending_question "extract 门禁两次未过：<FAIL 摘要>"`，停下汇报。
- 注意：`stages.extract.attempts` 由 `set-stage running` 自增，可据此判断已重派几次。
