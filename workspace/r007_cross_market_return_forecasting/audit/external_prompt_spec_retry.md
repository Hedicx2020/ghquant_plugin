# spec_audit 独立盲审（缩减重试）

你是独立研报复现审稿人，只读文件，不修改仓库。

案例：
- report_id: `r007_cross_market_return_forecasting`
- type: `ml`
- difficulty: `hard`
- market: `多资产`

输入：
- `workspace/r007_cross_market_return_forecasting/spec/report_text.md`
- `workspace/r007_cross_market_return_forecasting/spec/tables_extracted.md`
- `workspace/r007_cross_market_return_forecasting/spec/spec.md`
- `workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md`

严格分两阶段执行：

1. 先只读 `report_text.md` 与 `tables_extracted.md`，不得读取 `spec.md`。对 40 页全文做 hard 级盲提取，逐条登记 D/F/B/R/SA 要素、页码、关键参数或数值，并独立统计正文及附录全部 FIG/TBL 编号。用以下标记包裹：

```text
=== SPEC_CODEX_BEGIN ===
要素名 | 类别 | 页码 | 关键参数/数值
...
=== SPEC_CODEX_END ===
```

2. 完成标记块后才读取 `spec.md` 与 `coverage_matrix.md`，核对：
   - 盲提取要素是否被 spec 遗漏；
   - R 类数值是否与原文一致；
   - 图表编号及附录登记是否完整；
   - 至少抽查 8 条页码原文真实性，覆盖 D/F/B/R/SA，R 类尽可能全查。

只报告有定位证据的问题，不评价文风，不提出超出论文范围的增强需求。

严重度：
- critical：遗漏核心 F/R，或页码原文属于幻觉；
- major：R 数值错误、遗漏 SA、非参考图表缺失；
- minor：参考性图表或呈现细节。

最终一条消息必须同时包含上面的 `SPEC_CODEX` 标记块，以及紧随其后的一个 JSON 对象：

```json
{
  "checkpoint": "spec",
  "verdict": "pass | pass_with_issues | fail",
  "dimensions_checked": [
    {"dimension": "盲提取diff", "result": "no_findings 或 finding id"},
    {"dimension": "遗漏检查", "result": "no_findings 或 finding id"},
    {"dimension": "R表逐格核对", "result": "no_findings 或 finding id"},
    {"dimension": "编号完整性独立重算", "result": "no_findings 或 finding id"},
    {"dimension": "页码真实性抽查", "result": "no_findings 或 finding id"}
  ],
  "findings": [
    {
      "id": "CDX-S-01",
      "severity": "critical | major | minor",
      "category": "遗漏 | 数值抄错 | 编号缺口 | 幻觉引用",
      "location": "页码或 spec 章节",
      "description": "问题与证据",
      "suggestion": "定向修复建议",
      "confidence": "high | medium | low"
    }
  ]
}
```

没有问题时 `findings` 必须是空数组，五个维度仍逐项写 `no_findings`。
