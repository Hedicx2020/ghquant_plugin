# r007 code_audit 外审结果合并

你只做只读、机械合并，不新增审计结论，不读取其他文件。

读取：

- `workspace/r007_cross_market_return_forecasting/audit/code_audit_external.md`
- `workspace/r007_cross_market_return_forecasting/audit/code_audit_external_recheck_round1.md`

输出一个 JSON 对象，作为 code checkpoint 的完整历史发现集合：

- 保留首次审计的 `CDX-C-01` 原文；
- 保留复审的 `CDX-C-R1-01` 原文；
- `checkpoint` 固定为 `code`；
- `verdict` 固定为两份原始 verdict 的合并口径；两份均无 critical/major 时应为 `pass_with_issues`；
- `dimensions_checked` 归并两份已检查维度，不能遗漏；
- `findings` 恰好两条，ID 与内容不得改写；
- 额外加入 `review_chain`，列出两份原始文件路径及 checkpoint/verdict。

只输出 JSON，可包裹在单个 `json` fenced block。
