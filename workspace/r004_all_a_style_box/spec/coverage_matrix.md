---
report_name: r004_all_a_style_box
spec_version: 1
row_count: 78
---

| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | D | 核心CPI十年变化 | p6 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不使用宏观，关联A22/AS21 |  |  | plan |
| D2 | D | 核心CPI一年变化 | p6 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不使用宏观，关联A22/AS21 |  |  | plan |
| D3 | D | 美国实际GDP增长 | p6 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不使用宏观，关联A22/AS21 |  |  | plan |
| D4 | D | 商业周期标签 | p5-p6, p12 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不做商业周期，关联A22/AS21 |  |  | plan |
| D5 | D | 金融状况风险 | p6 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不使用宏观，关联A22/AS21 |  |  | plan |
| D6 | D | 金融状况信用 | p6 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不使用宏观，关联A22/AS21 |  |  | plan |
| D7 | D | 金融状况杠杆 | p6 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不使用宏观，关联A22/AS21 |  |  | plan |
| D8 | D | 有效联邦基金利率 | p6 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不使用宏观，关联A22/AS21 |  |  | plan |
| D9 | D | 货币政策预期 | p6 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不使用宏观，关联A22/AS21 |  |  | plan |
| D10 | D | CAPE估值 | p6 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不使用宏观，关联A22/AS21 |  |  | plan |
| D11 | D | 标普价格与滚动回撤 | p4-p5, p8 | core |  | skipped | out_of_scope/reference_only: 风险状态支线排除，原来源冲突保留，关联A2/AS1、A23/AS22、A22 |  |  | plan |
| D12 | D | 十行业月收益 | p7 | core |  | skipped | out_of_scope/reference_only: 金融湍流支线排除，原来源冲突保留，关联A4/AS3、A23/AS22、A22 |  |  | plan |
| D13 | D | 多期限国债月收益 | p7 | core |  | skipped | out_of_scope/reference_only: 金融湍流支线排除，原来源冲突保留，关联A4/AS3、A23/AS22、A22 |  |  | plan |
| D14 | D | 六类美股因子月收益 | p6, p9-p13 | core | m1 | done | experimental substitute: 原美股来源冲突仅背景，实际用本地A股个股收益自底向上四箱，关联A17/AS16、A23/AS22 | src/r004_all_a_style_box/data_pipeline.py:build_dynamic_all_a_panel | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| D15 | D | 未披露驱动第11项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D16 | D | 未披露驱动第12项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D17 | D | 未披露驱动第13项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D18 | D | 未披露驱动第14项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D19 | D | 未披露驱动第15项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D20 | D | 未披露驱动第16项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D21 | D | 未披露驱动第17项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D22 | D | 未披露驱动第18项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D23 | D | 未披露驱动第19项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D24 | D | 未披露驱动第20项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D25 | D | 未披露驱动第21项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D26 | D | 未披露驱动第22项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D27 | D | 未披露驱动第23项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D28 | D | 未披露驱动第24项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| D29 | D | 未披露驱动第25项 | p5-p6 | core |  | infeasible | data_missing: 原文未披露名称、数值和变换，nonrecoverable，关联A1 |  |  | plan |
| F1 | F | 两阶段择时框架 | p1, p4-p5 | core |  | skipped | out_of_scope: 用户限定2×2风格箱，不做两阶段ML，关联A22/AS21 |  |  | plan |
| F2 | F | K-Means聚类 | p4, p7-p8, p14 | core |  | skipped | out_of_scope: 风险状态支线排除，关联A3/AS2、A22 |  |  | plan |
| F3 | F | 三风险状态 | p8 | core |  | skipped | out_of_scope: 风险状态支线排除，关联A3/AS2、A22 |  |  | plan |
| F4 | F | Stacking分类器 | p4, p9, p15 | core |  | skipped | out_of_scope: 用户禁止ML，关联A5-A6/AS4-AS5、A22 |  |  | plan |
| F5 | F | SMOTE再平衡 | p4, p9, p16 | support |  | skipped | out_of_scope: 用户禁止ML，关联A22/AS21 |  |  | plan |
| F6 | F | 金融湍流 | p6-p7 | core |  | skipped | out_of_scope: 风险状态支线排除，关联A4/AS3、A22 |  |  | plan |
| F7 | F | 特征重要性 | p9, p14-p15 | support |  | skipped | out_of_scope: 用户禁止ML，关联A22/AS21 |  |  | plan |
| F8 | F | 分风险状态切样本 | p5, p9, p11 | core |  | skipped | out_of_scope: 用户禁止ML和风险状态，关联A7/AS6、A22 |  |  | plan |
| F9 | F | 月度唯一胜出标签 | p4-p5 | core |  | skipped | out_of_scope/reference_only: 原ML标签不实现，daily/monthly冲突保留；m4仅统计四箱月收益胜出频率，关联A7/AS6、A24/AS23、A22 |  |  | plan |
| F10 | F | 随机森林胜出概率 | p9-p11, p14 | core |  | skipped | out_of_scope: 用户禁止ML，关联A7/AS6、A22 |  |  | plan |
| F11 | F | Value因子 | p6 | core | m2 | done | experimental substitute: 低P/B→PIT复合价值，关联A19/AS18 | src/r004_all_a_style_box/strategy.py:calculate_style_factors; src/r004_all_a_style_box/strategy.py:assign_style_boxes; src/r004_all_a_style_box/strategy.py:build_m2_dataset; src/r004_all_a_style_box/strategy.py:assert_m2_invariants | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| F12 | F | Growth因子 | p6 | core | m2 | done | experimental substitute: 高P/B→PIT财务成长减价值，关联A20/AS19 | src/r004_all_a_style_box/strategy.py:calculate_style_factors; src/r004_all_a_style_box/strategy.py:assign_style_boxes; src/r004_all_a_style_box/strategy.py:build_m2_dataset; src/r004_all_a_style_box/strategy.py:assert_m2_invariants | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| F13 | F | Momentum因子 | p6 | core |  | skipped | out_of_scope: 用户明确禁止动量，关联A22/AS21 |  |  | plan |
| F14 | F | LowVol因子 | p6 | core |  | skipped | out_of_scope: 用户明确禁止低波，关联A22/AS21 |  |  | plan |
| F15 | F | Quality因子 | p6 | core |  | skipped | out_of_scope: 用户明确禁止质量，关联A8/AS7、A22 |  |  | plan |
| F16 | F | SmallCap因子 | p6 | core | m2 | done | experimental substitute: Russell小盘→全A总市值中位数Big/Small，关联A16/A18、AS15/AS17 | src/r004_all_a_style_box/strategy.py:calculate_style_factors; src/r004_all_a_style_box/strategy.py:assign_style_boxes; src/r004_all_a_style_box/strategy.py:build_m2_dataset; src/r004_all_a_style_box/strategy.py:assert_m2_invariants | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| F17 | F | 商业周期择时基准 | p5, p11-p12 | core |  | skipped | out_of_scope: 用户禁止宏观状态，关联A10/AS9、A22 |  |  | plan |
| F18 | F | 周期方向矩阵 | p12 | core |  | skipped | out_of_scope: 用户禁止宏观状态，关联A10/AS9、A22 |  |  | plan |
| F19 | F | 1/N等权基准 | p11-p12 | core | m3 | done | experimental substitute: 六因子1/N→四风格箱1/N结构基准，关联A22/AS21 | src/r004_all_a_style_box/portfolio.py:build_portfolio_targets | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| F20 | F | 15%风险预算调权 | p12 | core |  | skipped | out_of_scope: 商业周期支线排除，关联A10/AS9、A22 |  |  | plan |
| F21 | F | 胜出概率权重 | p12 | core |  | skipped | out_of_scope: 用户禁止ML，关联A11/AS10、A22 |  |  | plan |
| B1 | B | 全样本区间频率 | p5, p12 | core | m1 | done | experimental substitute: 原Mar-23/May-23冲突仅背景，冻结截止2023-03，正式OOS 2023-04至2025-12，关联A12/AS11、A25/AS24 | src/r004_all_a_style_box/data_pipeline.py:load_rebalance_schedule | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| B2 | B | 三月滚动回撤 | p5, p8 | core |  | skipped | out_of_scope: 风险状态支线排除，关联A2/AS1、A22 |  |  | plan |
| B3 | B | 滚动训练窗口 | p5 | core |  | skipped | out_of_scope: 不训练ML，关联A3/A7、AS2/AS6、A22 |  |  | plan |
| B4 | B | 84月初始训练窗 | p10 | core |  | skipped | out_of_scope: 不训练ML，关联A7/AS6、A22 |  |  | plan |
| B5 | B | 2000年后概率预测 | p10-p11 | core |  | skipped | reference_only: 美国ML起点仅背景，关联A12/AS11、A22 |  |  | plan |
| B6 | B | 1987至2000训练 | p11 | core |  | skipped | reference_only: 美国ML训练期仅背景，关联A12/AS11、A22 |  |  | plan |
| B7 | B | 2002年后组合结果 | p12-p13 | core | m3 | done | experimental substitute: 中国正式OOS改为2023-04至2025-12，关联A12/AS11 | src/r004_all_a_style_box/portfolio.py:run_china_market_backtest; src/r004_all_a_style_box/portfolio.py:select_formal_oos | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| B8 | B | 五折时间序列验证 | p9 | support |  | skipped | out_of_scope: 不训练ML，关联A22/AS21 |  |  | plan |
| B9 | B | 熊市并入调整状态 | p9 | core |  | skipped | out_of_scope: 不构造风险状态，关联A3/AS2、A22 |  |  | plan |
| B10 | B | 六因子选股股票池 | p6 | core | m1 | done | experimental substitute: Russell池→沪深北动态全A，关联A16/AS15 | src/r004_all_a_style_box/data_pipeline.py:build_dynamic_all_a_panel | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| B11 | B | 四类组合比较 | p11-p13 | core | m3 | done | experimental substitute: 全A基准、四箱、四箱1/N及SMB/HML/GML，关联A21/AS20 | src/r004_all_a_style_box/portfolio.py:build_portfolio_targets; src/r004_all_a_style_box/portfolio.py:calculate_style_factor_returns | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| B12 | B | 周期基准信息口径 | p12 | core |  | skipped | out_of_scope: 不做商业周期，关联A10/AS9、A22 |  |  | plan |
| B13 | B | 周期风险预算 | p12 | core |  | skipped | out_of_scope: 不做商业周期，关联A10/AS9、A22 |  |  | plan |
| B14 | B | ML组合权重口径 | p12 | core |  | skipped | out_of_scope: 不做ML概率组合，关联A11/AS10、A22 |  |  | plan |
| R1 | R | 风险状态数与占比 | p8-p9 | core |  | skipped | reference_only: 美国风险状态原值仅背景，关联A22/AS21 |  |  | plan |
| R2 | R | Stacking分类指标 | p9 | core |  | skipped | reference_only: 美国ML原值仅背景，关联A22/AS21 |  |  | plan |
| R3 | R | 一级特征重要性 | p9 | core |  | skipped | reference_only: 美国ML原值仅背景，关联A22/AS21 |  |  | plan |
| R4 | R | 全样本因子相关 | p10 | support | m4 | done | experimental substitute: 复用相关矩阵结构输出中国四箱及SMB/HML/GML，不比较美国数值 | src/r004_all_a_style_box/reporting.py:build_return_correlation; src/r004_all_a_style_box/reporting.py:build_m4_dataset | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| R5 | R | 正常状态因子相关 | p10 | support |  | skipped | reference_only: 不构造风险状态，美国原值仅背景，关联A22/AS21 |  |  | plan |
| R6 | R | 调整状态因子相关 | p10 | support |  | skipped | reference_only: 不构造风险状态，美国原值仅背景，关联A22/AS21 |  |  | plan |
| R7 | R | 因子胜出频率 | p10 | core | m4 | done | experimental substitute: 输出中国四箱扣费后月度胜出频率，不实现原ML标签、不比较美国数值，关联A24/AS23 | src/r004_all_a_style_box/reporting.py:calculate_style_box_winner_frequency; src/r004_all_a_style_box/reporting.py:build_m4_dataset | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| R8 | R | 分状态特征重要性 | p11 | core |  | skipped | reference_only: 不训练ML、不构造风险状态，关联A22/AS21 |  |  | plan |
| R9 | R | 四周期方向矩阵 | p12 | core |  | skipped | reference_only: 不做商业周期，美国原值仅背景，关联A22/AS21 |  |  | plan |
| R10 | R | 四方法组合表现 | p13 | core | m4 | done | experimental substitute: 输出中国全A、四箱、1/N、SMB/HML/GML OOS绩效，美国数值仅背景 | src/r004_all_a_style_box/reporting.py:calculate_performance_summary; src/r004_all_a_style_box/reporting.py:build_metrics_payload; src/r004_all_a_style_box/main.py:run_formal_pipeline | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| SA1 | SA | 五折时序交叉验证 | p9 | support |  | skipped | out_of_scope: 不训练ML，关联A22/AS21 |  |  | plan |
| SA2 | SA | 分风险状态相关性 | p9-p10 | support |  | skipped | out_of_scope: 不构造风险状态，关联A3/AS2、A22 |  |  | plan |
| SA3 | SA | 滚动样本外模拟 | p5, p10-p13 | core | m3 | done | experimental substitute: 无训练的冻结式前推OOS 2023-04至2025-12，关联A12/AS11 | src/r004_all_a_style_box/portfolio.py:run_china_market_backtest; src/r004_all_a_style_box/portfolio.py:select_formal_oos | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |
| SA4 | SA | 双基准稳健比较 | p4, p11-p13 | support | m4 | done | experimental substitute: 同池全A与四箱1/N两基准，关联A21/AS20 | src/r004_all_a_style_box/reporting.py:build_benchmark_comparison; src/r004_all_a_style_box/reporting.py:build_m4_dataset | verify_report.md#结论 attempt=5独立重算pass；formal exit=0；PIT/收益/交易/生命周期/R4/R7/SA4 pass；verified Excel 5/5、51/51 | verify |

## 变更日志

| 时间 | 事件 | 来源 | 说明 |
| --- | --- | --- | --- |
| 2026-07-18 extract | 初始化78行 | quant-extractor | 首次提取建矩阵；63项待规划，D15-D29共15项为原文未披露且不可恢复 |
| 2026-07-18 plan | 实验范围与milestone定稿 | quant-planner | 14项进入m1-m4；49项按out_of_scope/reference_only跳过；15项nonrecoverable保持infeasible |
| 2026-07-18 plan | spec冲突增量同步 | quant-planner | A23-A25终态化并补齐AS22-AS24；milestone、状态计数和feasibility不变 |
| 2026-07-18 verify | 正式验证回填 | quant-verifier | attempt=1冻结失败结论由attempt=2取代；14个done要素数值勾稽通过，5本XLSX共51个sheet三层A2冻结检查通过，整体PASS |
| 2026-07-19 verify | attempt=5正式终验回填 | quant-verifier | 默认正式入口exit=0；14个done要素由当前12张全量明细独立重算通过；hard扰动与正式SHA不变合同通过；5本XLSX最终化为verified/PASS，51/51 inspect、render及A2冻结通过。 |
