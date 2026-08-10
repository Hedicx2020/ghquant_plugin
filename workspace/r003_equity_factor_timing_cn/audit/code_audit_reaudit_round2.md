{
  "checkpoint": "code_reaudit",
  "verdict": "pass",
  "summary": "CDX-C-R1-01 已清零，CDX-C-01 与 CDX-C-02 未见回归。m3 的正式训练、72/12 诊断训练和诊断验证统一来自 label_available_date <= predictor_date 的 state_window；独立合成边界复算确认决策日后的标签被排除、决策日同日标签按冻结口径纳入，且修改被排除标签不改变正式预测权重。",
  "checks": [
    {
      "finding_id": "CDX-C-R1-01",
      "status": "cleared",
      "evidence": [
        "src/r003_equity_factor_timing_cn/factor_model.py:540-542",
        "src/r003_equity_factor_timing_cn/factor_model.py:581-630",
        "src/r003_equity_factor_timing_cn/factor_model.py:634-698",
        "src/r003_equity_factor_timing_cn/factor_model.py:717-763",
        "src/r003_equity_factor_timing_cn/factor_model.py:835-851",
        "workspace/r003_equity_factor_timing_cn/audit/m3_label_availability_adaptation.md:55-80"
      ],
      "conclusion": "标签资格已改为 winner_available AND label_available_date <= predictor_date。正式模型和诊断两段均从同一过滤后的 state_window 取样，training_audit 的截止日为 predictor_date，末端断言也使用 <= 同日口径。"
    },
    {
      "finding_id": "CDX-C-R1-01-boundary",
      "status": "passed",
      "evidence": {
        "predictor_date": "2023-03-31",
        "prediction_date": "2023-04-30",
        "train_candidate_months": 84,
        "train_eligible_label_months": 83,
        "labels_excluded_by_availability": 1,
        "excluded_label_available_date": "2023-04-10",
        "latest_training_label_available_date": "2023-03-31",
        "excluded_label_mutation_invariant": true
      },
      "conclusion": "独立合成复算中，决策日后的完整标签被排除，决策日同日标签被纳入；把被排除行胜出因子从 Value 改为 Growth 后，正式六因子预测权重逐位完全一致。"
    },
    {
      "finding_id": "CDX-C-01",
      "status": "no_regression",
      "evidence": [
        "src/r003_equity_factor_timing_cn/data_pipeline.py:226-229"
      ],
      "conclusion": "杠杆条件仍为 M2 与社融各自相对名义 GDP 同比缺口的算术平均。"
    },
    {
      "finding_id": "CDX-C-02",
      "status": "no_regression",
      "evidence": [
        "src/r003_equity_factor_timing_cn/strategy.py:55-163",
        "src/r003_equity_factor_timing_cn/strategy.py:268-321",
        "src/r003_equity_factor_timing_cn/strategy.py:620-855",
        "src/r003_equity_factor_timing_cn/data_pipeline.py:492-527"
      ],
      "conclusion": "执行与退出仍统一检查 ST、停牌、无成交量及涨跌停；退出固定搜索 20 个额外交易日，组合标签可得日继续取成分标签最晚日期并保留时点断言。"
    }
  ],
  "findings": []
}
