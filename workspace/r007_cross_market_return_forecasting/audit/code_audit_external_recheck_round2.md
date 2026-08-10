```json
{
  "checkpoint": "code_recheck_round2",
  "verdict": "fail",
  "dimensions_checked": [
    {"dimension": "eligibility逐键可重算", "result": "CDX-C-R2-01"},
    {"dimension": "FIG3逐条因果映射", "result": "no_findings"},
    {"dimension": "R2完整出口", "result": "no_findings"}
  ],
  "findings": [
    {
      "id": "CDX-C-R2-01",
      "severity": "major",
      "category": "输出合同",
      "location": "src/r007_cross_market_return_forecasting/model_pipeline.py:319",
      "description": "required_observation_missing 的判定依赖两个逐键原始输入：predictor_complete（第258-274行按 prediction_date 合并）与 _required_actual_return/_required_historical_liquidity 的有限性（第284-290行合成 required_available）。但 ELIGIBILITY_AUDIT_SCHEMA（第107-118行）仅落盘 direction/prediction_date/snapshot_date/target_code/graph_has_in_edges/feature_count/complete_case_nobs/min_required_nobs/eligibility_status/exclusion_reason 十列，第319-321行按 schema 裁剪后上述原始布尔与原始值全部丢弃。第三方仅凭落盘字段可直接重算 no_in_edges（graph_has_in_edges/feature_count）与 complete_case_insufficient（complete_case_nobs < min_required_nobs），但 required_observation_missing 只能以被审计输出 eligibility_status 作残差倒推，无独立证据：生产方将任意键标记为该原因时审计轨迹仍完全自洽，范围缩水不可检出。audit_formal_prediction_coverage（portfolio_pipeline.py:933-955）只校验原因字符串属于合法集合且与 status 一致，同样消费同一标签，不构成独立重算。",
      "suggestion": "在 ELIGIBILITY_AUDIT_SCHEMA 增加逐键布尔列 predictor_complete 与 required_observations_available（或直接落盘 _required_actual_return/_required_historical_liquidity 原始数值），使三种合法排除原因均可仅凭落盘字段由第三方独立重算，而非残差倒推。",
      "confidence": "high"
    },
    {
      "id": "CDX-C-R2-02",
      "severity": "minor",
      "category": "静默吞错",
      "location": "src/r007_cross_market_return_forecasting/graph_pipeline.py:318",
      "description": "等价因果审计确实存在且被调用：_build_fig03_graph_evidence（main.py:2392-2404）经 iter_rolling_graph_snapshots 进入 _direction_mapping，后者对 causal_available=True 的全部映射逐条断言 source_close_utc < target_open_utc（graph_pipeline.py:318-323），覆盖 250 条训练映射的超集；audit_snapshot_causality（graph_pipeline.py:753-756）另复核窗口长度与 target_date < anchor，FIG3 自身也在 main.py:2414-2420 硬核对 250 期与训练日期严格早于图日期。故主检查项无发现。但逐条时间戳核验以 {'source_close_utc','target_open_utc'}.issubset(columns) 守卫为前提，两列缺失时静默退化为纯日期级检查，且 main.py:2498 的 training_dates_strictly_before_graph_date 为硬编码 True，不会反映该退化。本次限定阅读范围无法确认 m1 日历映射必然产出这两个 UTC 列。",
      "suggestion": "将 source_close_utc/target_open_utc 纳入 _direction_mapping 的 _require_columns 强制合同，或在列缺失时显式 raise，消除因果审计的静默降级路径。",
      "confidence": "medium"
    }
  ]
}
```
