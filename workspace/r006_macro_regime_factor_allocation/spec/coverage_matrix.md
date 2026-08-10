---
report_name: r006_macro_regime_factor_allocation
spec_version: 1
row_count: 83
---

| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | D | OpenAP 212特征面板 | p2, p10 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:align_factor_panel_to_schedule |  | implement |
| D2 | D | 股票月观察单元 | p10 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_monthly_stock_panel |  | implement |
| D3 | D | 特征方向 | p10 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:fit_annual_frozen_factor_directions |  | implement |
| D4 | D | 八家族逐信号映射 | p10-p11, p27, p54 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_factor_crosswalk |  | implement |
| D5 | D | 23个宏观条件变量 | p11, p53, p101 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:ensure_macro_block_coverage |  | implement |
| D6 | D | 实时宏观vintage | p11, p55, p101 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:apply_conservative_publication_lag; src/r006_macro_regime_factor_allocation/data_pipeline.py:align_macro_asof |  | implement |
| D7 | D | 面板衍生市场状态 | p11, p101 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:load_index_state_inputs |  | implement |
| D8 | D | FF5加动量 | p12, p29, p33 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:load_financial_pit_panel |  | implement |
| D9 | D | 容量与横截面控制 | p18-p19, p35-p36, p77 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_capacity_control_panel |  | implement |
| D10 | D | 信号发表年份 | p10, p102-p103 | support | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:compute_factor_availability |  | implement |
| F1 | F | 预期收益方向统一 | p10 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:fit_frozen_factor_directions |  | implement |
| F2 | F | 八个经济异常家族 | p10-p11 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:assert_frozen_crosswalk |  | implement |
| F3 | F | 八个宏观状态块 | p11, p28, p53 | core | m3 | pending |  |  |  | plan |
| F4 | F | 宏观状态记忆配置 | p12-p13 | core | m4 | pending |  |  |  | plan |
| F5 | F | Mixture-of-experts | p12-p13 | core | m4 | pending |  |  |  | plan |
| F6 | F | Validation ensemble | p12-p13 | core | m4 | pending |  |  |  | plan |
| F7 | F | 配置比较规则集合 | p13, p28, p61 | support | m4 | pending |  |  |  | plan |
| F8 | F | 非负和为一权重 | p12-p13 | core | m4 | pending |  |  |  | plan |
| F9 | F | 层级212信号层 | p13-p14 | core | m5 | pending |  |  |  | plan |
| F10 | F | Pooled 212 ridge | p14, p16-p17 | core | m5 | pending |  |  |  | plan |
| F11 | F | Ridge加宏观残差 | p14, p16-p17 | support | m5 | pending |  |  |  | plan |
| F12 | F | 信息系数 | p12, p16 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:calculate_monthly_factor_ic |  | implement |
| F13 | F | Fama-MacBeth斜率 | p12, p33, p70 | support | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:fama_macbeth_regression |  | implement |
| F14 | F | 十分位多空与alpha | p12, p29, p68 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:build_factor_decile_layer |  | implement |
| F15 | F | 流动性趋势容量机制 | p17-p20 | core | m3 | pending |  |  |  | plan |
| F16 | F | 发表年份可用口径 | p102 | support | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_publication_year_coverage |  | implement |
| B1 | B | 特征历史起点 | p2, p11, p27 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_common_month_index |  | implement |
| B2 | B | 首个预测年 | p2, p11, p27 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_walk_forward_windows |  | implement |
| B3 | B | 初始训练窗口 | p2, p11, p27 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_walk_forward_windows |  | implement |
| B4 | B | 固定验证窗口 | p2, p11, p27 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_walk_forward_windows |  | implement |
| B5 | B | 年度滚动扩展训练 | p2, p11, p27 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_walk_forward_windows |  | implement |
| B6 | B | 479个样本外月份 | p2, p11, p27 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_walk_forward_windows |  | implement |
| B7 | B | 组合形成信息时点 | p12 | core | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_execution_schedule |  | implement |
| B8 | B | 预测年前模型选择 | p13 | core | m4 | pending |  |  |  | plan |
| B9 | B | 月度Newey-West | p15, p29 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:newey_west_ols |  | implement |
| B10 | B | 十分位多空组合 | p29 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:build_factor_decile_layer |  | implement |
| B11 | B | FF5动量alpha | p29, p33 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:estimate_six_factor_alpha |  | implement |
| B12 | B | 等权与市值加权 | p12, p29, p35-p36 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:build_factor_decile_layer |  | implement |
| B13 | B | 容量区域 | p7, p19, p36 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:assign_capacity_regions |  | implement |
| B14 | B | 形成与确认期 | p19, p39, p91 | support | m3 | pending |  |  |  | plan |
| B15 | B | 逐事件剔除 | p17, p104 | support | m3 | pending |  |  |  | plan |
| R1 | R | 宏观块与主要规则 | p28 | core | m4 | pending |  |  |  | plan |
| R2 | R | 家族配置表现 | p29 | core | m4 | pending |  |  |  | plan |
| R3 | R | 家族配置权重 | p30 | core | m4 | pending |  |  |  | plan |
| R4 | R | 212信号层级证据 | p16, p31 | core | m5 | pending |  |  |  | plan |
| R5 | R | 股票层基准 | p16-p17, p32 | core | m5 | pending |  |  |  | plan |
| R6 | R | 受控预测与alpha | p33 | core | m5 | pending |  |  |  | plan |
| R7 | R | 状态家族收益图 | p34 | core | m3 | pending |  |  |  | plan |
| R8 | R | 流动性趋势机制 | p35 | core | m3 | pending |  |  |  | plan |
| R9 | R | 容量前沿 | p36 | core | m3 | pending |  |  |  | plan |
| R10 | R | 状态特异性 | p37 | support | m3 | pending |  |  |  | plan |
| R11 | R | 模型类别基准 | p38 | core | m5 | pending |  |  |  | plan |
| R12 | R | 形成与确认期结果 | p39, p91 | core | m3 | pending |  |  |  | spec_audit |
| R13 | R | 家族组合消融 | p41 | core | m4 | pending |  |  |  | plan |
| R14 | R | 实时宏观时点 | p55 | support | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:align_macro_asof |  | implement |
| R15 | R | 家族基线预测 | p59 | support | m4 | pending |  |  |  | plan |
| R16 | R | 袖套收益与换手 | p60 | core | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:summarize_family_sleeve_evidence |  | implement |
| R17 | R | 配置规则变体 | p61 | support | m4 | pending |  |  |  | plan |
| R18 | R | 家族权重分布 | p62 | support | m4 | pending |  |  |  | plan |
| R19 | R | 完整状态收益面 | p75-p76 | core | m3 | pending |  |  |  | plan |
| R20 | R | 机制控制与年代 | p77 | support | m3 | pending |  |  |  | plan |
| R21 | R | 逐家族剔除 | p80 | support | m5 | pending |  |  |  | plan |
| R22 | R | 局部状态可靠性 | p82 | support | m5 | pending |  |  |  | plan |
| R23 | R | 信号发表覆盖 | p102 | support | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_publication_year_coverage |  | implement |
| R24 | R | 逐事件剔除结果 | p104 | support | m3 | pending |  |  |  | plan |
| R25 | R | 家族内信号构成 | p65 | support | m2 | done |  | src/r006_macro_regime_factor_allocation/family_sleeves.py:summarize_family_signal_composition |  | implement |
| R26 | R | 层级十分位组合指标 | p68 | core | m5 | pending |  |  |  | spec_audit |
| R27 | R | 配置规则股票层IC与FMB | p70 | support | m5 | pending |  |  |  | spec_audit |
| R28 | R | Horse-race与受控结果 | p71-p72 | core | m5 | pending |  |  |  | spec_audit |
| SA1 | SA | 配置规则约束变体 | p28, p61 | support | m4 | pending |  |  |  | plan |
| SA2 | SA | 家族权重时间分布 | p15, p30, p43, p62-p64 | support | m4 | pending |  |  |  | spec_audit |
| SA3 | SA | 家族组合逐家族剔除 | p16, p41, p79-p81 | support | m4 | pending |  |  |  | spec_audit |
| SA4 | SA | 完整状态收益面 | p34, p46, p75-p76 | support | m3 | pending |  |  |  | plan |
| SA5 | SA | 机制跨横截面构造 | p18, p35, p47, p77-p78 | support | m3 | pending |  |  |  | spec_audit |
| SA6 | SA | 危机与分年代状态 | p17, p77-p78 | support | m3 | pending |  |  |  | spec_audit |
| SA7 | SA | 市值容量前沿 | p36, p48-p49, p84-p86 | support | m3 | pending |  |  |  | plan |
| SA8 | SA | 预设形成确认期 | p39, p91 | support | m3 | pending |  |  |  | plan |
| SA9 | SA | 状态安慰剂置换 | p20, p37, p88, p92-p93 | support | m3 | pending |  |  |  | spec_audit |
| SA10 | SA | 宏观块逐个剔除 | p20, p37, p89 | support | m3 | pending |  |  |  | spec_audit |
| SA11 | SA | 发布滞后与时点 | p55, p90 | support | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:run_sa11_sensitivity |  | implement |
| SA12 | SA | 模型类别基准 | p20, p38, p45, p71-p73, p94-p97 | support | m5 | pending |  |  |  | spec_audit |
| SA13 | SA | 信号发表年份覆盖 | p102-p103 | support | m1 | done |  | src/r006_macro_regime_factor_allocation/data_pipeline.py:build_publication_year_coverage |  | implement |
| SA14 | SA | 逐市场事件剔除 | p104 | support | m3 | pending |  |  |  | plan |

## 变更日志

| 时间 | 事件 | 来源 | 说明 |
| --- | --- | --- | --- |
| 2026-07-26 extract | 初始化 79 行 | quant-extractor | 首次提取建矩阵 |
| 2026-07-26 plan | 里程碑、优先级与恢复核对定稿 | quant-planner | 79 行均唯一映射至 m1-m5；core/support 优先级及最后更新字段保持 plan |
| 2026-07-26 spec_audit | DIF-01 重建物理表附录 | spec_audit | tables_extracted.md 改为 51 个正式物理表，排除 17 个图形伪表 |
| 2026-07-26 spec_audit | DIF-02 补全 R1-R24 | spec_audit | R 类改为逐格完整网格，原表空白写 n/a |
| 2026-07-26 spec_audit | DIF-03 新增 R25-R28 | spec_audit | 增加 IA.11、IA.13、IA.14、IA.15/IA.16 的数值要素 |
| 2026-07-26 spec_audit | DIF-04 补 R12 遗漏行 | spec_audit | 补 Continuation × Valuation 形成期行并核对 IA.27 正负号 |
| 2026-07-26 spec_audit | DIF-05 修正 B12 页码 | spec_audit | 页码集合补 p12 |
| 2026-07-26 spec_audit | DIF-06 补结论讨论页 | spec_audit | SA2、SA3、SA5、SA6、SA9、SA10、SA12 补对应正文页 |
| 2026-07-27 implement | M1-E6 日期键精度修复 | m1 verify_report | D6/R14 的真实宏观 as-of 路径在 merge 前统一 `signal_date`、`available_date` 与审计源日为 `datetime64[ns]`；保留时间先后且验证结果仍留给 verifier |
