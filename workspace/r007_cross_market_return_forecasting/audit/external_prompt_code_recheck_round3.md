# r007 code_audit round3 最终增量外审

你是只读量化代码审计员。只审第 3 轮两项证据闭环，不修改仓库，不读取过程叙事、`audit_responses.md` 或正式结果。

只读：

- `workspace/r007_cross_market_return_forecasting/audit/code_audit_external_recheck_round2.md`
- `workspace/r007_cross_market_return_forecasting/audit/code_audit_fix_round3.md`（仅作定位，不采信结论）
- `src/r007_cross_market_return_forecasting/model_pipeline.py` 中 eligibility schema、`derive_eligibility_decision`、`validate_eligibility_audit`、`_graph_target_eligibility`
- `src/r007_cross_market_return_forecasting/backtest_pipeline.py` 中图/非图 eligibility 生成
- `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:audit_formal_prediction_coverage`
- `src/r007_cross_market_return_forecasting/main.py:_run_sa3/_build_fig03_graph_evidence`

必须检查：

1. `predictor_complete`、`actual_return_available`、`historical_liquidity_available` 与入边/样本计数字段逐键落盘；生产、M4、SA3 使用同一固定优先级重算 expected status/reason；任一矛盾硬失败。不能只校验枚举字符串。
2. FIG3 构图前要求 250 行全部 `causal_available=True`、`source_date` 非空、UTC 列存在且每行 `source_close_utc < target_open_utc`、源信息早于 2021-10-21 图日；布尔清单由实际值重算，失败不得调用构图。
3. 本轮是否引入新的未来函数、静默 catch/continue、smoke-only 接线。

只输出 JSON：

```json
{
  "checkpoint": "code_recheck_round3",
  "verdict": "pass | pass_with_issues | fail",
  "closed": [
    {"issue": "CDX-C-R2-01", "result": "closed | open", "evidence": "文件:行号 + 证据"},
    {"issue": "CDX-C-R2-02", "result": "closed | open", "evidence": "文件:行号 + 证据"}
  ],
  "dimensions_checked": [
    {"dimension": "eligibility逐键重算", "result": "no_findings 或 finding id"},
    {"dimension": "FIG3逐条因果映射", "result": "no_findings 或 finding id"},
    {"dimension": "未来函数与静默降级", "result": "no_findings 或 finding id"}
  ],
  "findings": [
    {
      "id": "CDX-C-R3-01",
      "severity": "critical | major | minor",
      "category": "未来函数 | 静默吞错 | 范围缩水 | 输出合同",
      "location": "文件:行号",
      "description": "可复核描述",
      "suggestion": "定点建议",
      "confidence": "high | medium | low"
    }
  ]
}
```

`closed` 恰有两行；三个维度全部出现。
