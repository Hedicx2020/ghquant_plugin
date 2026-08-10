# r007 spec_audit 增量复核

你是只读独立复核人。不要修改任何文件，也不要重新做全文摘要。

请读取：

- `workspace/r007_cross_market_return_forecasting/audit/spec_audit_external.md`
- `workspace/r007_cross_market_return_forecasting/audit/extract_audit.md`
- `workspace/r007_cross_market_return_forecasting/spec/extract_diff.md`
- 修复后的 `workspace/r007_cross_market_return_forecasting/spec/spec.md`
- 修复后的 `workspace/r007_cross_market_return_forecasting/spec/tables_extracted.md`
- 修复后的 `workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md`
- 修复后的 `workspace/r007_cross_market_return_forecasting/plan.md`
- 原始证据 `workspace/r007_cross_market_return_forecasting/spec/report_text.md`

只复核原意见 `CDX-S-01..04` 与 `SA-A01..07` 是否真实修复：

- R3/R4 是否补入正文、覆盖矩阵与 m4；
- 页面覆盖表 D6/D7/D8 是否修正；
- FIG3 的 25只/行业、254/235 口径是否补齐；
- SA1/SA2/SA5 次级结论是否补齐；
- Table A.1 是否按 7行×8逻辑列补入 tables_extracted.md，42 个数值格及 Parameters 列是否完整；
- FIG5 双向入度上升趋势是否补齐；
- spec/frontmatter/coverage_matrix 是否保持 55 条三方一致。

输出一个 JSON 对象：

```json
{
  "checkpoint": "spec_recheck",
  "verdict": "pass | pass_with_issues | fail",
  "original_findings": [
    {"id": "CDX-S-01", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "CDX-S-02", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "CDX-S-03", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "CDX-S-04", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "SA-A01", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "SA-A02", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "SA-A03", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "SA-A04", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "SA-A05", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "SA-A06", "result": "pass | fail", "evidence": "文件:行号"},
    {"id": "SA-A07", "result": "pass | fail", "evidence": "文件:行号"}
  ],
  "new_findings": []
}
```

任何 `fail` 必须给出可定位证据并进入 `new_findings`；全部修复时 `new_findings` 为空且 verdict=`pass`。
