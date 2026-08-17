---
report_name: r003_equity_factor_timing_cn
spec_version: 1
row_count: 78
---

| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | D | 核心CPI十年变化 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_macro_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D2 | D | 核心CPI一年变化 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_macro_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D3 | D | 美国实际GDP增长 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_macro_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D4 | D | 商业周期标签 | p6, p12 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_macro_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D5 | D | 金融状况风险 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_macro_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D6 | D | 金融状况信用 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_macro_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D7 | D | 金融状况杠杆 | p6 | core | m1 | done | AS7两个相对名义GDP缺口等权平均 | src/r003_equity_factor_timing_cn/data_pipeline.py:build_macro_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D8 | D | 有效联邦基金利率 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:_read_shibor | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D9 | D | 货币政策预期 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_macro_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D10 | D | CAPE估值 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_benchmark_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D11 | D | 标普价格与滚动回撤 | p5, p8 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_benchmark_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D12 | D | 十行业月收益 | p7 | core | m1 | done |  | src/r003_equity_factor_timing_cn/strategy.py:_calculate_industry_returns | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D13 | D | 多期限国债月收益 | p7 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_bond_return_proxies | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D14 | D | 六因子月收益 | p6, p9 | core | m1 | done | 执行及退出统一限制；固定20交易日延迟；原信号权重不重归一并输出标签可得日 | src/r003_equity_factor_timing_cn/strategy.py:_calculate_factor_returns | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| D15 | D | 未披露宏观驱动11 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D16 | D | 未披露宏观驱动12 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D17 | D | 未披露宏观驱动13 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D18 | D | 未披露宏观驱动14 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D19 | D | 未披露宏观驱动15 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D20 | D | 未披露宏观驱动16 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D21 | D | 未披露宏观驱动17 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D22 | D | 未披露宏观驱动18 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D23 | D | 未披露宏观驱动19 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D24 | D | 未披露宏观驱动20 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D25 | D | 未披露宏观驱动21 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D26 | D | 未披露宏观驱动22 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D27 | D | 未披露宏观驱动23 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D28 | D | 未披露宏观驱动24 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| D29 | D | 未披露宏观驱动25 | p5 | core |  | infeasible | data_missing: 原文未披露名称与数值，仅完整性占位（A1） |  | N/A（原文未披露且无可恢复数据，保持infeasible） | verify_attempt2 |
| F1 | F | 两阶段机器学习框架 | p1, p4-p5 | core | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:run_stage_two_factor_model | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| F2 | F | 第一阶段K-Means | p4, p7-p8, p14 | core | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:calculate_elbow_diagnostics | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| F3 | F | 三类市场风险状态 | p8 | core | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:fit_market_regimes | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| F4 | F | Stacking分类器 | p4, p15 | core | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:fit_stacking_classifier | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| F5 | F | SMOTE再平衡 | p4, p9, p16 | core | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:_resample_training_fold | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| F6 | F | 金融湍流指标 | p6-p7 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:calculate_financial_turbulence | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| F7 | F | 决策树特征重要性 | p9, p14-p15 | support | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:calculate_feature_importance | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| F8 | F | 按风险状态分割样本 | p5, p9, p11 | core | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:_training_regimes_for_window | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| F9 | F | 月度胜出因子标签 | p5, p9 | core | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:build_winner_labels | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| F10 | F | 第二阶段随机森林 | p9, p14 | core | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:run_stage_two_factor_model | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| F11 | F | Value因子 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/strategy.py:_select_factor_constituents | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| F12 | F | Growth因子 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/strategy.py:_select_factor_constituents | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| F13 | F | Momentum因子 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/strategy.py:_build_signal_panel | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| F14 | F | LowVol因子 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/strategy.py:_select_factor_constituents | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| F15 | F | Quality因子 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/strategy.py:_select_factor_constituents | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| F16 | F | SmallCap因子 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/strategy.py:_select_factor_constituents | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| F17 | F | 商业周期择时基准 | p5, p12 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:business_cycle_weights | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| F18 | F | 六因子周期方向矩阵 | p12 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:BUSINESS_CYCLE_DIRECTIONS | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| F19 | F | 1/N等权基准 | p11-p12 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:_build_weight_detail | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| F20 | F | 15%风险预算调权 | p12 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:business_cycle_weights | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| F21 | F | 胜出概率权重 | p12 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:_normalise_ml_probabilities | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| B1 | B | 全样本区间频率 | p5 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:load_month_end_calendar | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| B2 | B | 三月滚动回撤 | p5, p8 | core | m1 | done |  | src/r003_equity_factor_timing_cn/data_pipeline.py:build_benchmark_features | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| B3 | B | 滚动训练窗口 | p5 | core | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:run_stage_two_factor_model | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| B4 | B | 84月初始训练窗 | p10 | core | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:run_stage_two_factor_model | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| B5 | B | 2000年后概率预测 | p10-p11 | core | m5 | done | 中国迁移按AS25固定为2023-04至2025-12 OOS | src/r003_equity_factor_timing_cn/reporting.py:_coverage_and_training_evidence | pass（attempt2正式全量重跑：16项产物；154529行退出审计v2哈希默认Excel回读一致） | verify_attempt2 |
| B6 | B | 1987至2000训练 | p11 | core | m5 | done | 中国迁移使用每个预测月之前固定84个月训练窗 | src/r003_equity_factor_timing_cn/reporting.py:_coverage_and_training_evidence | pass（attempt2正式全量重跑：16项产物；154529行退出审计v2哈希默认Excel回读一致） | verify_attempt2 |
| B7 | B | 2002年后组合结果 | p12-p13 | core | m5 | done | 中国迁移按AS25输出2023-04至2025-12四组合结果 | src/r003_equity_factor_timing_cn/reporting.py:write_result_package | pass（attempt2正式全量重跑：16项产物；154529行退出审计v2哈希默认Excel回读一致） | verify_attempt2 |
| B8 | B | 五折时间序列验证 | p9 | support | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:time_series_cross_validate | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| B9 | B | 熊市并入调整状态 | p9 | core | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:collapse_second_stage_regime | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| B10 | B | 六因子选股股票池 | p6 | core | m1 | done |  | src/r003_equity_factor_timing_cn/strategy.py:_build_signal_panel | pass（attempt2正式全量重跑：132月特征、792行六因子收益；PIT、T+1与逐股票退出字段复核） | verify_attempt2 |
| B11 | B | 四类组合比较 | p11-p13 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:run_portfolio_construction | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| B12 | B | 商业周期信息口径 | p12 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:_build_weight_detail | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| B13 | B | 商业周期风险预算 | p12 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:business_cycle_weights | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| B14 | B | ML组合权重口径 | p12 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:_normalise_ml_probabilities | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| R1 | R | 风险状态数与占比 | p8-p9 | core | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:summarize_regime_distribution | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| R2 | R | Stacking分类指标 | p9 | core | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:time_series_cross_validate | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| R3 | R | 第一阶段特征重要性 | p9 | core | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:calculate_feature_importance | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| R4 | R | 全样本因子相关矩阵 | p10 | support | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:calculate_factor_correlations | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| R5 | R | 正常状态相关矩阵 | p10 | support | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:calculate_factor_correlations | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| R6 | R | 调整状态相关矩阵 | p10 | support | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:calculate_factor_correlations | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| R7 | R | 因子历史胜出频率 | p10 | core | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:summarize_winner_frequency | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| R8 | R | 分状态特征重要性 | p11 | core | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:_aggregate_feature_importance | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| R9 | R | 六因子四周期矩阵 | p12 | core | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:cycle_direction_matrix | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |
| R10 | R | 不同方法组合表现 | p13 | core | m5 | done | 美国原值仅作迁移参照，中国偏差不判作复现误差 | src/r003_equity_factor_timing_cn/reporting.py:_comparison_table | pass（attempt2正式全量重跑：16项产物；154529行退出审计v2哈希默认Excel回读一致） | verify_attempt2 |
| SA1 | SA | 五折时间序列验证 | p9 | support | m2 | done |  | src/r003_equity_factor_timing_cn/regime_model.py:time_series_cross_validate | pass（attempt2正式全量重跑：33月预测、84月严格历史、165折及参数哈希复核） | verify_attempt2 |
| SA2 | SA | 分风险状态相关性 | p9-p10 | support | m3 | done |  | src/r003_equity_factor_timing_cn/factor_model.py:calculate_factor_correlations | pass（attempt2正式全量重跑：33月×6因子散点198条，实际收益与赢家字段无空） | verify_attempt2 |
| SA3 | SA | 滚动样本外模拟 | p5, p10-p13 | core | m5 | done | 逐月断言固定84月训练窗、严格过去和OOS完整覆盖 | src/r003_equity_factor_timing_cn/reporting.py:_coverage_and_training_evidence | pass（attempt2正式全量重跑：16项产物；154529行退出审计v2哈希默认Excel回读一致） | verify_attempt2 |
| SA4 | SA | 双基准稳健比较 | p11-p13 | support | m4 | done |  | src/r003_equity_factor_timing_cn/portfolio.py:run_portfolio_construction | pass（attempt2正式全量重跑：132行月收益与attempt1 SHA256完全一致；成本口径复核） | verify_attempt2 |

## 变更日志

| 时间 | 事件 | 来源 | 说明 |
| --- | --- | --- | --- |
| 2026-07-18 extract | 初始化63行 | quant-extractor | 首次提取建矩阵 |
| 2026-07-18 plan | 定稿优先级并回填全部milestone | quant-planner | 实验性中国市场迁移；63个要素唯一映射至m1-m5 |
| 2026-07-18 extract | 追加15行D15-D29 | 依据SA-A01追加 | 原文25项仅公开10项；未知15项作不可恢复占位 |
| 2026-07-18 implement | m1第1轮修复 | quant-coder | 按CA-A01至CA-A11修复时点、数据映射、因子收益与证据链；m1状态保持done，验证结果留空 |
| 2026-07-18 implement | m1第2轮修复 | quant-coder | CA-A03新增同月1Y/3Y曲线插值2Y并保留标记；CA-A12新增PIT派生PB、70%/100只门槛与逐月覆盖审计；m1验证结果仍留空 |
| 2026-07-18 implement | m3首次实现 | quant-coder | 固定84月、预测状态选择、Bear合并Correction、六个一对其余RF、t+1唯一胜出标签及R4-R8/SA2结构化输出；验证结果留空 |
| 2026-07-18 implement | m4首次实现 | quant-coder | 四类组合、R9周期方向矩阵、15%总主动倾斜、ML概率归一、下一交易期执行、成本补充情景及累计收益图表数据；验证结果留空 |
| 2026-07-18 implement | m5首次实现 | quant-coder | 2023-04至2025-12严格OOS结果包、33月覆盖/84月训练窗断言、R10美中分栏参照、毛收益主结果与成本补充、五图和模型/概率/权重/收益Excel明细；验证结果留空 |
| 2026-07-18 code_fix_round1 | m1全局代码审计定向修复 | quant-coder | CDX-C-01按AS7改为两个名义GDP缺口等权平均；CDX-C-02统一执行/退出限制、固定20交易日延迟、超限NAV/现金留痕及label_available_date；未声明审计通过。 |
| 2026-07-18 verify | 正式33月独立验证 | quant-verifier | 回填78行验证结果；63个done要素均有正式证据，15个未披露D类保持infeasible |

| 2026-07-18 verify_attempt2 | result_audit修复后正式重跑 | quant-verifier | 33月正式结果、198点散点、154529行退出审计、v2哈希与成本口径独立复核 |
