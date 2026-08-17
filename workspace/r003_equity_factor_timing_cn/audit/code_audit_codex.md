{
  "checkpoint": "code",
  "verdict": "fail",
  "dimensions_checked": [
    {
      "dimension": "公式逐要素对照",
      "result": "CDX-C-01"
    },
    {
      "dimension": "未来函数/前视检查",
      "result": "CDX-C-R1-01"
    },
    {
      "dimension": "数据对齐检查",
      "result": "CDX-C-02"
    },
    {
      "dimension": "config vs B类核对",
      "result": "no_findings"
    },
    {
      "dimension": "作弊模式排查(K1/K5/K6)",
      "result": "no_findings"
    }
  ],
  "findings": [
    {
      "id": "CDX-C-01",
      "severity": "major",
      "category": "代理公式与已登记假设不一致",
      "location": "src/r003_equity_factor_timing_cn/data_pipeline.py:226",
      "description": "AS7把杠杆条件定义为M2及社融增速各自相对名义GDP增速的缺口，但实现为 m2_yoy + social_financing_yoy - gdp_nominal_yoy，只扣除一次GDP增速。该式既不等于两个缺口的等权平均，也不等于两个缺口之和，导致GDP项权重相对M2和社融少一半；这一具体公式未在assumptions中另行登记，会改变第一、二阶段的金融条件特征与模型结果。",
      "suggestion": "按AS7明确冻结口径，例如使用 ((m2_yoy-gdp_nominal_yoy)+(social_financing_yoy-gdp_nominal_yoy))/2；若确实要使用当前公式，应先在assumptions中登记其经济含义、权重与影响，再保持代码和假设一致。",
      "confidence": "high"
    },
    {
      "id": "CDX-C-02",
      "severity": "major",
      "category": "可交易状态对齐不完整",
      "location": "src/r003_equity_factor_timing_cn/strategy.py:145-178,311-317,406-424",
      "description": "ST仅在信号日过滤；下一交易日执行检查只覆盖成交量、停牌和涨跌停，没有复核执行日ST状态。收益截止日则直接按exit_close计价，只要价格存在便视为可实现收益，未检查该日停牌或涨跌停导致的无法退出。AS33只登记了未执行和缺价转现金，并未覆盖“有收盘价但实际无法交易”的情形。月度因子袖套每期独立重建，因此该缺口会把执行日新增ST或退出日受限头寸静默当成可正常成交，影响六因子收益及四组合结果。",
      "suggestion": "在执行日重新按ST生效区间过滤，并为return_date读取停牌、涨跌停和成交量状态；对无法退出的头寸制定并登记可复核的延迟退出或继续持有规则，不能仅凭存在exit_close认定成交完成。",
      "confidence": "high"
    },
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
