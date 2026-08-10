# r007 code_audit round2 增量外审

你是只读量化代码审计员。只审 round2 的三个问题是否关闭，不修改仓库，不读取 `audit_responses.md`、agent 消息或正式结果，不采信修复报告的通过声明。

先读合同：

- `workspace/r007_cross_market_return_forecasting/audit/impl_audit_mall.md` 中 CA-ALL-R1-01～03
- `workspace/r007_cross_market_return_forecasting/audit/code_audit_round2_planning.md`
- `workspace/r007_cross_market_return_forecasting/assumptions.md` 的 AS2、AS14、AS27
- `workspace/r007_cross_market_return_forecasting/audit/code_audit_fix_round2.md`（仅作函数定位）

再只读相关实现及直接调用上下文：

- `model_pipeline.py:_graph_target_eligibility/predict_graph_snapshot`
- `backtest_pipeline.py:_build_autoregressive_feature_panel/iter_non_graph_autoregressive_predictions`
- `portfolio_pipeline.py:audit_formal_prediction_coverage/run_m4_portfolios`
- `main.py:_stage_m2_m3/_prepare_cross_predictions/_collect_same_market_predictions/_collect_non_graph_predictions/_stage_m4/_run_sa3`
- `main.py:_build_fig03_graph_evidence/_build_chart_tables/run_formal_pipeline`
- `reporting.py:create_result_charts/write_formal_outputs`
- `sensitivity_pipeline.py:summarize_hyperparameter_sharpe/build_r2_comparison`

必须逐项裁决：

1. 动态可预测键独立来自图/训练与必要观测审计，合法排除仅 `no_in_edges`、`complete_case_insufficient`、`required_observation_missing`；无任意覆盖率门槛。`predictable` 键严格十模型齐全，三规格交集显式，合法排除原始输出可记账剔除，但资格全集外输出、缺模型、未登记原因、整日零 predictable 必须失败。
2. FIG3 在 2021-10-21 单独构图，不取最近 10 日锚点；恰好 250 个全部早于图日的历史配对；输出行 CN 列 US，并在图、sheet、机器口径、metrics/run_log 明示 `degraded/substitute`、D9、AS27、全量 B1 代理及节点/矩阵哈希。
3. R2 聚合前要求 111×6=666 唯一行、模型归属正确、`sharpe_status=ok`、Sharpe 有限；禁止过滤失败行后继续；42 格 `configuration_set_complete` 全真且 reference outer merge 全 `both`。

同时检查本轮是否引入未来函数、R2 参考值进入训练/选参、静默 `except/pass/continue` 或 smoke-only 修复。

只输出 JSON：

```json
{
  "checkpoint": "code_recheck_round2",
  "verdict": "pass | pass_with_issues | fail",
  "closed": [
    {"issue": "CA-ALL-R1-01", "result": "closed | open", "evidence": "文件:行号 + 证据"},
    {"issue": "CA-ALL-R1-02", "result": "closed | open", "evidence": "文件:行号 + 证据"},
    {"issue": "CA-ALL-R1-03", "result": "closed | open", "evidence": "文件:行号 + 证据"}
  ],
  "dimensions_checked": [
    {"dimension": "动态资格与十模型完整性", "result": "no_findings 或 finding id"},
    {"dimension": "FIG3精确日与降级证据", "result": "no_findings 或 finding id"},
    {"dimension": "R2完整666行与42格", "result": "no_findings 或 finding id"},
    {"dimension": "未来函数与R2硬编码", "result": "no_findings 或 finding id"},
    {"dimension": "静默吞错与正式接线", "result": "no_findings 或 finding id"}
  ],
  "findings": [
    {
      "id": "CDX-C-R2-01",
      "severity": "critical | major | minor",
      "category": "未来函数 | 硬编码 | 参数不符 | 静默吞错 | 范围缩水 | 输出合同",
      "location": "文件:行号",
      "description": "可复核描述",
      "suggestion": "定点建议",
      "confidence": "high | medium | low"
    }
  ]
}
```

`closed` 恰有三行；五维度全部出现；finding 必须有精确行号。
