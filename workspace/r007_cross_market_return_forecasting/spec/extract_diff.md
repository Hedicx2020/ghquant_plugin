# 规格提取差异登记

| 差异ID | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |
| --- | --- | --- | --- | --- | --- |
| DIF-01 | R 类遗漏 | 增补反向中→美预测显著更弱，以及同市场图优于非图、跨市场图总体最强的正文结果锚点 | p24 | adopted | CDX-S-01、SA-A04 一致确认属于核心比较结论 |
| DIF-02 | 页面关联错位 | 页面覆盖表修正为 p9→D6、p15→D8、p20→D7，并补 D8 的 p15 市场时段页码 | p9、p15、p20 | corrected | CDX-S-02、SA-A03 独立复核一致 |
| DIF-03 | 图表参数遗漏 | FIG3 补每行业最多 25 只、不足则全取、最终 254 美股与 235 A 股的构图口径 | p13 | adopted | CDX-S-03、SA-A05 均定位到原文明确参数 |
| DIF-04 | 敏感性结论遗漏 | SA1 补 qr6 韧性；SA2 补 Lag 4 后趋稳及周度周期解释；SA5 补 RIDGE 不稳定 | p27、p28、p38 | adopted | CDX-S-04、SA-A07；均为原文明确次级结论 |
| DIF-05 | 表格结构遗漏 | tables_extracted.md 补录 PDF 中 Table A.1 的 7 行×8 逻辑列结构及页码 | p36 | adopted | SA-A01；PDF 存在唯一数值表而自动抽取为 0 |
| DIF-06 | 参数列遗漏 | R2/SA3 补 Table A.1 Parameters 列及 XGBoost、LGBM、RF、AdaBoost 精确参数网格 | p35-p36 | adopted | SA-A02；42 个 SR 数值正确但参数列不完整 |
| DIF-07 | 趋势基准遗漏 | F7 或 FIG5 备注补两个方向入度随时间上升、跨市场连接增强的定性复核锚点 | p14-p15 | adopted | SA-A06；原文有明确趋势陈述 |
| DIF-08 | 滞后敏感性次级结论遗漏 | SA2 补 qr6 随信息滞后增加时降幅较小、较大幅度信号可能更持久的原文锚点 | p28 | adopted | 外部增量复核 RC-S-01；对应原审计 SA-A07 的残余项 |
