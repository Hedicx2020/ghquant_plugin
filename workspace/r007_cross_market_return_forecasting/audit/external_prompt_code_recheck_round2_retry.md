# r007 code round2 外审缩减重试

首次 round2 增量审计超时。本次严格只读以下函数及其所在文件中必要的直接上下文，不读取任何其他文件：

- `src/r007_cross_market_return_forecasting/model_pipeline.py:_graph_target_eligibility`
- `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:audit_formal_prediction_coverage`
- `src/r007_cross_market_return_forecasting/main.py:_build_fig03_graph_evidence`
- `src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:summarize_hyperparameter_sharpe`
- `src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:build_r2_comparison`

只检查：

1. 动态 eligibility 是否把合法排除原因所需原始字段逐键落盘，第三方能否仅凭落盘字段重算 `no_in_edges`、`complete_case_insufficient`、`required_observation_missing`；若缺原始布尔/计数字段，标 major。
2. FIG3 是否不仅检查训练日期 `< 2021-10-21`，还逐条核验 250 个映射的 `source_close_ts < target_open_ts` 或调用等价因果审计；若只检查日期，标 major。
3. R2 是否在聚合前硬核对 111×6=666、唯一、模型归属、status=ok、有限值，且 42 格完整与 reference merge 全 both。

不要修改仓库。只输出 JSON：

```json
{
  "checkpoint": "code_recheck_round2",
  "verdict": "pass | pass_with_issues | fail",
  "dimensions_checked": [
    {"dimension": "eligibility逐键可重算", "result": "no_findings 或 finding id"},
    {"dimension": "FIG3逐条因果映射", "result": "no_findings 或 finding id"},
    {"dimension": "R2完整出口", "result": "no_findings 或 finding id"}
  ],
  "findings": [
    {
      "id": "CDX-C-R2-01",
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
