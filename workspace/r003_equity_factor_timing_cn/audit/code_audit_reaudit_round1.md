{
  "checkpoint": "code_reaudit",
  "verdict": "fail",
  "summary": "CDX-C-01 与 CDX-C-02 已清零；新增发现 1 个 critical 级标签时点前视问题：m3 虽按 label_available_date < prediction_date 过滤，但 prediction_date 被定义为目标月月末，晚于实际形成预测特征与权重的 predictor_date，可能纳入决策时尚不可得的标签。",
  "checks": [
    {
      "finding_id": "CDX-C-01",
      "status": "cleared",
      "evidence": [
        "src/r003_equity_factor_timing_cn/data_pipeline.py:226-229",
        "workspace/r003_equity_factor_timing_cn/assumptions.md:83-94"
      ],
      "conclusion": "杠杆条件已改为两个相对名义 GDP 同比缺口的算术平均，与 AS7 一致。"
    },
    {
      "finding_id": "CDX-C-02",
      "status": "cleared",
      "evidence": [
        "src/r003_equity_factor_timing_cn/strategy.py:55-163",
        "src/r003_equity_factor_timing_cn/strategy.py:268-321",
        "src/r003_equity_factor_timing_cn/strategy.py:620-855",
        "src/r003_equity_factor_timing_cn/data_pipeline.py:492-527",
        "workspace/r003_equity_factor_timing_cn/assumptions.md:422-434",
        "workspace/r003_equity_factor_timing_cn/assumptions.md:540-550"
      ],
      "conclusion": "执行日与退出日均统一核验 ST、停牌、无成交量和涨跌停；退出最多顺延 20 个交易日，未解决时按冻结窗口末日估值，并生成标签可得日。"
    },
    {
      "finding_id": "m3_label_availability",
      "status": "failed",
      "evidence": [
        "src/r003_equity_factor_timing_cn/factor_model.py:201-203",
        "src/r003_equity_factor_timing_cn/factor_model.py:330-335",
        "src/r003_equity_factor_timing_cn/factor_model.py:582-587",
        "src/r003_equity_factor_timing_cn/factor_model.py:623-627"
      ],
      "conclusion": "代码形式上执行 label_available_date < prediction_date，但该 prediction_date 是目标月月末，而 predictor_date 才是预测特征对应的上月月末；因此不能证明决策时点无前视。"
    }
  ],
  "findings": [
    {
      "id": "CDX-C-R1-01",
      "severity": "critical",
      "category": "标签可得日截止时点前视",
      "location": "src/r003_equity_factor_timing_cn/factor_model.py:201-203,330-335,582-587,623-627",
      "description": "m3 的训练样本用 label_available_date < prediction_date 过滤，但 prediction_date 被构造为 prediction_period（目标月）的月末；同一流程同时保留了更早的 predictor_date（特征月月末）。这会允许标签在 predictor_date 之后、目标月月末之前才变得可得，却仍进入该次预测的训练窗口，属于决策时点未来标签泄漏。",
      "suggestion": "将标签可得性截止日改为真实决策时点 predictor_date（按冻结口径选择 <= predictor_date 或 < 下一交易日执行时点），并同步修改审计字段与最终断言。增加边界回归测试：构造 label_available_date 落在 predictor_date 之后但 prediction_date 之前的标签，断言其不得进入 state_window 或正式 RF 训练集。",
      "confidence": "high"
    }
  ]
}
