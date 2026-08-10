```json
{
  "checkpoint": "code_recheck_round3",
  "verdict": "pass_with_issues",
  "closed": [
    {"issue": "CDX-C-R2-01", "result": "closed", "evidence": "model_pipeline.py:116-118 ELIGIBILITY_AUDIT_SCHEMA 新增 predictor_complete/actual_return_available/historical_liquidity_available 三个逐键布尔列，图路径 _graph_target_eligibility(:431-468)与非图路径 backtest_pipeline.py:431-459,552-555 均从原始值（特征行有限性 / _required_actual_return / _required_historical_liquidity 的 np.isfinite）计算并随 schema 落盘；共享函数 derive_eligibility_decision(model_pipeline.py:238-333) 实现唯一固定优先级 no_in_edges→complete_case_insufficient→required_observation_missing→predictable，并硬核验非负、min_required_nobs==feature_count+1、graph_has_in_edges 与 feature_count>0 一致、三布尔非空；validate_eligibility_audit(:336-371) 从原始字段重算 expected status/reason 并逐键严格等式核对，矛盾抛 EligibilityDecisionError 且保留失败逐键；M4 消费端 portfolio_pipeline.py:940-948 调用同一校验器并转 FormalCoverageError 硬失败，SA3 消费端 main.py:1480-1483 在生成 expected keys 前调用同一校验器；生产端图(:457-466)/非图(backtest_pipeline.py:462-471)亦调用同一 derive 函数写入结论，无第二份实现；三种排除原因均可仅凭落盘字段独立重算，不再残差倒推"},
    {"issue": "CDX-C-R2-02", "result": "closed", "evidence": "main.py:_validate_fig03_training_mapping(:2388-2397) 对 causal_available/source_date/target_open_utc/source_close_utc 做硬 KeyError 列合同，不再有 issubset 静默降级；:2441-2460 全部布尔（causal_available 全真、source_date 非空、两 UTC 列非空、target_date/source_date 严格早于图日、逐行 source_close_utc<target_open_utc、source_close_utc<图日开盘）由实际值重算；:2462-2465 交叉核对 audit_snapshot_causality 的 250/0 计数；:2466-2484 任一条件不满足即在构图前抛 AssertionError，iter_rolling_graph_snapshots(:2550) 在其后才会被调用；:2571-2594 以 check_exact=True 断言快照实际构图训练映射与预验证映射五列（含两 UTC 列）逐值相等，防漂移；FIG3 审计负载 :2485-2517 全部由重算值填充，原 main.py:2498 的硬编码 True 已替换为 target_dates_strict 实算值"}
  ],
  "dimensions_checked": [
    {"dimension": "eligibility逐键重算", "result": "no_findings"},
    {"dimension": "FIG3逐条因果映射", "result": "no_findings"},
    {"dimension": "未来函数与静默降级", "result": "CDX-C-R3-01"}
  ],
  "findings": [
    {
      "id": "CDX-C-R3-01",
      "severity": "minor",
      "category": "静默吞错",
      "location": "src/r007_cross_market_return_forecasting/graph_pipeline.py:318",
      "description": "第 3 轮修复选择不改 _direction_mapping，改用 FIG3 专用预验证(main.py:2388-2484)+构图后逐值断言(:2571-2594)闭环，FIG3 暴露面已闭合；但通用生产路径（m2_m3 全部滚动快照）的逐条时间戳核验仍以 {'source_close_utc','target_open_utc'}.issubset(columns) 守卫为前提，两列缺失时静默退化为纯日期级检查，且该路径无等价硬门禁兜底。此为 R2-02 原建议（纳入 _require_columns 或显式 raise）未实施的残留项，非本轮新引入，不影响 FIG3 证据可信度，故仅作 minor 记录。",
      "suggestion": "在 graph_pipeline.py:_direction_mapping 将 source_close_utc/target_open_utc 纳入强制列合同（缺失即 raise），或对生产滚动快照路径复用与 FIG3 相同的预验证函数。",
      "confidence": "medium"
    }
  ]
}
```
