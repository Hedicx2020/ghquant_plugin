```json
{
  "checkpoint": "code",
  "verdict": "pass_with_issues",
  "dimensions_checked": [
    {"dimension": "模型构造与参数来源", "result": "CDX-C-01", "source": "code_audit_external.md"},
    {"dimension": "八模型事务与集成完整性", "result": "no_findings", "source": "code_audit_external.md"},
    {"dimension": "未来标签与方向", "result": "no_findings", "source": "code_audit_external.md"},
    {"dimension": "R2结果硬编码", "result": "no_findings（题述 42 个 R2 参考数值在本文件完全不存在，未进入模型构造、预测、选参、组合或 PnL 计算；本文件亦无任何 PnL/选参逻辑）", "source": "code_audit_external.md"},
    {"dimension": "静默吞错与降级", "result": "no_findings", "source": "code_audit_external.md"},
    {"dimension": "九项原问题关闭", "result": "no_findings", "source": "code_audit_external_recheck_round1.md"},
    {"dimension": "未来函数与时点", "result": "no_findings", "source": "code_audit_external_recheck_round1.md"},
    {"dimension": "R2硬编码隔离", "result": "no_findings", "source": "code_audit_external_recheck_round1.md"},
    {"dimension": "静默吞错与范围缩水", "result": "no_findings", "source": "code_audit_external_recheck_round1.md"},
    {"dimension": "正式输出与checkpoint", "result": "no_findings", "source": "code_audit_external_recheck_round1.md"},
    {"dimension": "eligibility逐键可重算", "result": "CDX-C-R2-01", "source": "code_audit_external_recheck_round2.md"},
    {"dimension": "FIG3逐条因果映射", "result": "no_findings", "source": "code_audit_external_recheck_round2.md"},
    {"dimension": "R2完整出口", "result": "no_findings", "source": "code_audit_external_recheck_round2.md"},
    {"dimension": "eligibility逐键重算", "result": "no_findings", "source": "code_audit_external_recheck_round3.md"},
    {"dimension": "FIG3逐条因果映射", "result": "no_findings", "source": "code_audit_external_recheck_round3.md"},
    {"dimension": "未来函数与静默降级", "result": "CDX-C-R3-01", "source": "code_audit_external_recheck_round3.md"}
  ],
  "findings": [
    {
      "id": "CDX-C-01",
      "severity": "minor",
      "category": "参数不符",
      "location": "src/r007_cross_market_return_forecasting/strategy.py:81-93",
      "description": "审计边界说明而非确认缺陷：八个基础回归器（OLS/LASSO/RIDGE/SVR/XGBoost/LGBM/RF/AdaBoost，含 AdaBoost 的 DecisionTreeRegressor 基学习器）构造真实，全部参数均经 **dict(parameters.*) 来自 config.models，本文件内无任何硬编码参数；但 random_state 是否固定写在 config 中，本次降级合同未授权读取 config.py，故随机性固定无法在本文件内确认。若 config 未为 SVM/XGBoost/LGBM/RF/AdaBoost 显式设定 random_state，滚动重训将不可复现。其余维度结论：本文件不含训练/预测/数据对齐逻辑（训练、样本外预测、集成实现均在 common.ml_pipeline），故无未来标签与方向反转的引入点；集成仅委托 append_prediction_ensembles 并传入全部八个基础模型名，本文件内无部分失败继续、填零、复用旧预测路径；唯一的异常捕获（PackageNotFoundError, :35-39）会汇入 RuntimeError 显式抛出（:60），版本断言为严格相等、失败即中断，validate_parameter_snapshot 对缺模型/缺快照均 raise，无静默吞错。",
      "suggestion": "在对 config.py 的审计中确认 models 段为 SVM/XGBoost/LGBM/RF/AdaBoost/adaboost_base_tree 显式设置 random_state（或固定种子），并确认 SVR 的 kernel='rbf'；strategy.py 本身无需改动。",
      "confidence": "low"
    },
    {
      "id": "CDX-C-R1-01",
      "severity": "minor",
      "category": "范围缩水",
      "location": "src/r007_cross_market_return_forecasting/portfolio_pipeline.py:776-789; src/r007_cross_market_return_forecasting/main.py:1424-1435",
      "description": "两处新门禁均为零容忍满覆盖合同：要求 2016–2021 每个预期交易日×每只池内股票都有预测。但 AS14 登记了『无入边节点则不预测』，且 sensitivity_pipeline.py:237-280 显示无入边是真实会发生的分支；只要任一目标股票在任一锚点无入边，M4 与 SA3 将整体硬失败。这是 assumptions 未登记容忍度时修复者明示选择的『零静默缩水』口径，方向上正确（失败是响亮的而非静默），但主会话应预期正式运行可能在此失败，届时正确处置是在 assumptions 登记可容忍缺口比例后再放宽门禁，而非削弱或绕过门禁。",
      "suggestion": "正式运行前由 quant-planner 评估是否需要在 assumptions.md 补充登记逐日股票覆盖率的可接受阈值（例如允许无入边目标按 AS14 登记性缺席），避免 verifier 阶段失败后无依据地回调门禁。",
      "confidence": "medium"
    },
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
    },
    {
      "id": "CDX-C-R3-01",
      "severity": "minor",
      "category": "静默吞错",
      "location": "src/r007_cross_market_return_forecasting/graph_pipeline.py:318",
      "description": "第 3 轮修复选择不改 _direction_mapping，改用 FIG3 专用预验证(main.py:2388-2484)+构图后逐值断言(:2571-2594)闭环，FIG3 暴露面已闭合；但通用生产路径（m2_m3 全部滚动快照）的逐条时间戳核验仍以 {'source_close_utc','target_open_utc'}.issubset(columns) 守卫为前提，两列缺失时静默退化为纯日期级检查，且该路径无等价硬门禁兜底。此为 R2-02 原建议（纳入 _require_columns 或显式 raise）未实施的残留项，非本轮新引入，不影响 FIG3 证据可信度，故仅作 minor 记录。",
      "suggestion": "在 graph_pipeline.py:_direction_mapping 将 source_close_utc/target_open_utc 纳入强制列合同（缺失即 raise），或对生产滚动快照路径复用与 FIG3 相同的预验证函数。",
      "confidence": "medium"
    }
  ],
  "review_chain": [
    {
      "path": "workspace/r007_cross_market_return_forecasting/audit/code_audit_external.md",
      "checkpoint": "code",
      "verdict": "pass_with_issues"
    },
    {
      "path": "workspace/r007_cross_market_return_forecasting/audit/code_audit_external_recheck_round2.md",
      "checkpoint": "code_recheck_round2",
      "verdict": "fail"
    },
    {
      "path": "workspace/r007_cross_market_return_forecasting/audit/code_audit_external_recheck_round3.md",
      "checkpoint": "code_recheck_round3",
      "verdict": "pass_with_issues"
    }
  ],
  "final_closures": [
    {"issue": "CDX-C-R2-01", "result": "closed", "evidence": "model_pipeline.py:116-118 ELIGIBILITY_AUDIT_SCHEMA 新增 predictor_complete/actual_return_available/historical_liquidity_available 三个逐键布尔列，图路径 _graph_target_eligibility(:431-468)与非图路径 backtest_pipeline.py:431-459,552-555 均从原始值（特征行有限性 / _required_actual_return / _required_historical_liquidity 的 np.isfinite）计算并随 schema 落盘；共享函数 derive_eligibility_decision(model_pipeline.py:238-333) 实现唯一固定优先级 no_in_edges→complete_case_insufficient→required_observation_missing→predictable，并硬核验非负、min_required_nobs==feature_count+1、graph_has_in_edges 与 feature_count>0 一致、三布尔非空；validate_eligibility_audit(:336-371) 从原始字段重算 expected status/reason 并逐键严格等式核对，矛盾抛 EligibilityDecisionError 且保留失败逐键；M4 消费端 portfolio_pipeline.py:940-948 调用同一校验器并转 FormalCoverageError 硬失败，SA3 消费端 main.py:1480-1483 在生成 expected keys 前调用同一校验器；生产端图(:457-466)/非图(backtest_pipeline.py:462-471)亦调用同一 derive 函数写入结论，无第二份实现；三种排除原因均可仅凭落盘字段独立重算，不再残差倒推"},
    {"issue": "CDX-C-R2-02", "result": "closed", "evidence": "main.py:_validate_fig03_training_mapping(:2388-2397) 对 causal_available/source_date/target_open_utc/source_close_utc 做硬 KeyError 列合同，不再有 issubset 静默降级；:2441-2460 全部布尔（causal_available 全真、source_date 非空、两 UTC 列非空、target_date/source_date 严格早于图日、逐行 source_close_utc<target_open_utc、source_close_utc<图日开盘）由实际值重算；:2462-2465 交叉核对 audit_snapshot_causality 的 250/0 计数；:2466-2484 任一条件不满足即在构图前抛 AssertionError，iter_rolling_graph_snapshots(:2550) 在其后才会被调用；:2571-2594 以 check_exact=True 断言快照实际构图训练映射与预验证映射五列（含两 UTC 列）逐值相等，防漂移；FIG3 审计负载 :2485-2517 全部由重算值填充，原 main.py:2498 的硬编码 True 已替换为 target_dates_strict 实算值"}
  ]
}
```
