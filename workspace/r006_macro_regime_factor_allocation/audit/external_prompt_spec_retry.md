# spec_audit 精简重试

你是独立的研报复现规格审稿人。工作目录为
`/Users/hedi/report_reproduce`，report_id 为
`r006_macro_regime_factor_allocation`，难度为 `hard`。

只读输入：

- `workspace/r006_macro_regime_factor_allocation/spec/report_text.md`
- `workspace/r006_macro_regime_factor_allocation/spec/tables_extracted.md`
- `workspace/r006_macro_regime_factor_allocation/spec/spec.md`
- `workspace/r006_macro_regime_factor_allocation/spec/coverage_matrix.md`

严格执行两阶段协议：

1. 先禁止读取 `spec.md`，仅依据 `report_text.md` 与
   `tables_extracted.md` 独立列出 D/F/B/R/SA 要素、页码、关键参数和数值，
   并登记全部主文及附录图表编号。该清单必须包在：

```text
=== SPEC_CODEX_BEGIN ===
...
=== SPEC_CODEX_END ===
```

2. 然后读取 `spec.md` 与 `coverage_matrix.md`，核对：
   - 盲提取清单与 spec 的遗漏/多出项；
   - R 类结果表数值、符号、单位和 n/a；
   - 主文及 Internet Appendix 图表编号完整性；
   - 至少 10 条页码原文真实性，覆盖 D/F/B/R/SA，R 至少 3 条。

仅输出上述标记块，紧接一个合法 JSON：

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
      "location": "页码或文件位置",
      "description": "问题与可定位证据",
      "suggestion": "修复建议",
      "confidence": "high | medium | low"
    }
  ]
}
```

critical：遗漏核心 F/R 或幻觉引用。major：R 数值错误、遗漏 SA、重要图表缺口。
minor：reference_only 图表或呈现问题。不要复述正确内容，不要提出论文范围外增强。
找不到定位证据的怀疑不得列为 finding；未发现问题的维度必须写
`no_findings`。最终消息必须同时包含完整标记块和 JSON，不要输出其他叙述。
