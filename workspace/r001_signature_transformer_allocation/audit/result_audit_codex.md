{
  "checkpoint": "result",
  "verdict": "fail",
  "dimensions_checked": [
    {
      "dimension": "归因量级推算",
      "result": "CDX-R-02,CDX-R-04"
    },
    {
      "dimension": "假设方向一致性",
      "result": "CDX-R-04"
    },
    {
      "dimension": "过于精确嫌疑(K2)",
      "result": "no_findings"
    },
    {
      "dimension": "skip理由核实",
      "result": "CDX-R-03"
    },
    {
      "dimension": "结论措辞相符性",
      "result": "CDX-R-01,CDX-R-02,CDX-R-05"
    }
  ],
  "findings": [
    {
      "id": "CDX-R-01",
      "severity": "critical",
      "category": "数字不符",
      "location": "output/r001_signature_transformer_allocation/results/comparison.json:44；output/r001_signature_transformer_allocation/results/metrics.json:22-28；workspace/r001_signature_transformer_allocation/state.json:1008-1013；workspace/r001_signature_transformer_allocation/assumptions.md:163,187；output/r001_signature_transformer_allocation/results/backtest_summary.xlsx『主绩效表』!B2,B4:B5,B7",
      "description": "comparison、state 与 assumptions 将 SIT Sharpe 0.7348 写成“居第4”，且 assumptions 另把 SIT Sharpe 误写为 0.7306。原始主表排序为 GMV 0.9401、CVaR 0.8302、SIT 0.7348、DLinear 0.7306、HRP 0.5945、EW 0.4050；在已比较的六个模型中 SIT 是第3，第4是 DLinear。GMV/CVaR 反超与“SIT 未碾压基线”属实，但名次数字不实。",
      "suggestion": "从原始 Sharpe 列程序化重算排名，将所有“第4”改为“第3”，并将 AS15 的 SIT 0.7306 改为 0.7348；若要给全基线排名，须先补齐缺失基线。"
    },
    {
      "id": "CDX-R-02",
      "severity": "critical",
      "category": "数字不符 / 证据链失实",
      "location": "workspace/r001_signature_transformer_allocation/audit/evidence_manifest.md:28-31,50-52；output/r001_signature_transformer_allocation/verify_report.md:3-4,47-50,125-128,207；src/r001_signature_transformer_allocation/main.py:453-457；output/r001_signature_transformer_allocation/results/backtest_summary.xlsx#workbook-sheets",
      "description": "evidence_manifest 声称 Excel 有 7 个 sheet、含“主绩效表_对照”和“SA1_模块消融”，并声称 metrics、verify_report、xlsx 三方一致且 verify_report 在结果之后“本次写”。实际工作簿只有“主绩效表”“净值序列”两张，导出代码也只创建这两张；verify_report 仍是旧的 milestone/smoke 报告，明确写着等待 final verify，未包含全档 SIT 0.7348 与最终 SA1 结论。因此 E4/E6 的通过声明与原始产物不符。",
      "suggestion": "打回 verify：以当前 metrics、xlsx 与两份完整日志重写 final verify 章节；删除不存在的 sheet 声明或真实补齐对应 sheet；随后重新执行 E4/E6，并让 evidence_manifest 只记录实际核到的对象。"
    },
    {
      "id": "CDX-R-03",
      "severity": "critical",
      "category": "漏对比项",
      "location": "workspace/r001_signature_transformer_allocation/spec/coverage_matrix.md:26,30-33；workspace/r001_signature_transformer_allocation/spec/spec.md:185-195,211-366；output/r001_signature_transformer_allocation/results/comparison.json:6,11-40；workspace/r001_signature_transformer_allocation/assumptions.md:179-200",
      "description": "B5、R1-R4 均登记为 core 且在覆盖矩阵标为 done，但 comparison 只有 R4 Panel A 的 CSI300-50 与 5 个基线。缺失 7 个预测基线、R1 的 40 资产完整档、R2 的 30 资产完整档、R3 的 10/20 资产完整档及 R4 Panel B 的 100 资产档。AS15/AS16 虽披露算力缩减，矩阵却仍把“未跑/未覆盖”行标 done，comparison 也没有显式 scoped-out 条目，构成 core 漏对比。",
      "suggestion": "要么补跑并纳入 comparison，要么把未跑项改为 skipped/partial，并以 compute_budget/AS15/AS16（不是 data_missing）写明理由；comparison 同步加入显式未覆盖条目，禁止用 done 掩盖。"
    },
    {
      "id": "CDX-R-04",
      "severity": "major",
      "category": "方向不一致 / 归因证据薄弱",
      "location": "workspace/r001_signature_transformer_allocation/assumptions.md:331-348；output/r001_signature_transformer_allocation/results/metrics.json:54-63；output/r001_signature_transformer_allocation/results/comparison.json:45-46；output/r001_signature_transformer_allocation/verify_report.md:142-165,203-207",
      "description": "AS27 预期四个组件移除后均退化；完整档只支持 CVaR 与 Asset Attention（ΔSharpe -1.0929/-0.2898），Financial Bias 与 Gate γ 反而为 +0.0048/+0.0067。方向相反虽已披露，但产物仍以“噪声/欠训练级”解释；SA1 是 best-config 单种子点估计，没有配对多种子误差、置信区间或训练预算反事实，无法把反向结果归因为噪声或欠训练。",
      "suggestion": "将 AS27 标为部分支持，并把结论限定为“本次迁移设定下两细组件无可测贡献，原因未定”；若坚持噪声/欠训练归因，补做配对多种子消融及误差区间，或给出扩大训练预算的量级反事实。"
    },
    {
      "id": "CDX-R-05",
      "severity": "minor",
      "category": "展示口径未标注",
      "location": "output/r001_signature_transformer_allocation/results/backtest_summary.xlsx『净值序列』#SIT末值 与 『主绩效表』#SIT-FinalWealth；output/r001_signature_transformer_allocation/results/metrics.json:22,30-33；src/r001_signature_transformer_allocation/main.py:269-307,451-457",
      "description": "净值序列和 NAV/回撤图使用 SIT、DLinear 的代表性单种子路径，而主绩效表报告三种子均值；例如 SIT 路径末值约 1.7546，而主表 FinalWealth 为 1.6014。数值各自可追溯，但图题和 sheet 未标“单种子”，容易被读成与主表同一聚合口径。",
      "suggestion": "在净值 sheet 与相关图题明确标注 seed=0 representative path，或改为与主表一致的多种子聚合展示。"
    }
  ]
}