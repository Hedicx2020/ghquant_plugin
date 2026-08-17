# 提取完整性审计 extract_audit.md

- 审计模式：`spec`
- 案例：`r007_cross_market_return_forecasting`
- 审计范围：PDF、`report_text.md`、`tables_extracted.md`、`spec.md`、`coverage_matrix.md`、`ambiguities.md`、`plan.md`
- 审计原则：只读对照；图表编号、要素计数和 R 类数值均由审计者独立重算，不采信任何完成汇报。

## C1–C6 检查项

| 检查项 | 独立检查记录 | 结论 |
| --- | --- | --- |
| C1 图表编号连续性 | 原文正文 Figure 1–14 连续无缺号；附录原生编号为 Figure B.1、B.2、C.1、D.1、E.1，共 5 图；Figure 14a/14b 是 Figure 14 的两个面板，不另计图号。独立归一化后为 FIG1–FIG19，`fig_max=19`。原文仅有 Table A.1，归一化为 TBL1，`tbl_max=1`；未发现 Exhibit。与 `exhibit_declared: {fig_max: 19, tbl_max: 1}` 一致，登记 ID 连续。 | pass |
| C2 逐页覆盖扫描 | 已逐页扫描 p1–p40；公式、百分比和数值密集页 p8–p23、p27–p28、p36、p38 均有要素或内容类型标注，p30–p34 明确为参考文献。发现页面覆盖表三处核心数据关联错位、主结果定性基准缺项、FIG3 重现参数遗漏及 FIG5 趋势遗漏，见 SA-A03–SA-A06。 | fail |
| C3 触发词检查 | 独立检查 sensitivity/robustness/parameter/group/sector/year/subsample/market capitalization/Appendix/further 等英文对应词；技术性命中集中在 p8–p21、p23、p27–p29、p35–p40，均有 D/F/B/R/SA 关联，文献页 p5、p7 的 group/year 属参考文献语境。未发现 bull/bear 分析。p28 的敏感性结论只摘录主趋势，遗漏 qr6 韧性与 Lag 4 后趋稳解释，见 SA-A07；p36 参数触发词所对应的完整参数列遗漏另见 SA-A02。 | pass_with_issues |
| C4 计数交叉 | 独立复核：美国/中国各 500 只对应 B1；十种模型对应 F10–F19/B11，其中八个基础模型对应 F10–F17、两个集成对应 F18–F19；六个嵌套组合对应 F24；Appendix A 的七个有超参数模型对应 R2 七行；边替换 20%/40%/60%/80%/全部对应 SA1。独立要素计数 D=9、F=24、B=11、R=2、SA=7，合计 53，与 frontmatter 和 coverage_matrix 的 53 行一致；未发现摘要、引言或结论计数声明短缺。 | pass |
| C5 基准表完备 | 直接读取 PDF p36 重算 Table A.1：7 个方法行、8 个逻辑列（Methods、Parameters、qr1–qr6），共 42 个 SR 均值±标准差单元。R2 的 42 个 SR 单元逐格与 PDF 一致；但 `tables_extracted.md` 报告“未检测到表格”，且 R2 表缺少 Parameters 列，四个树模型的精确网格未在 SA3 补出，见 SA-A01、SA-A02。R1 为 Figure 8 正文定性数值，不适用表格行列比对，其 lower than one / exceed one / approaching two 均已直接回查 PDF p23。 | fail |
| C6 幻觉引用抽查 | 抽查 16 条，覆盖 D/F/B/R/SA 五类；全部在所标页的 `report_text.md` 找到原文或可接受的跨行近似文本。R1、R2 另直接回查 PDF 原文；R2 的 42 个数值单元均一致。 | pass |

## C2 逐页覆盖扫描记录

| 页码 | PDF 内容独立识别 | spec 页面关联 | 复核结论 |
| --- | --- | --- | --- |
| p1 | 封面、摘要、方向不对称结论 | R1 | 覆盖 |
| p2 | 关键词、JEL、引言与文献 | - | 内容类型标注充分，无核心公式或精确结果 |
| p3 | 研究贡献、十模型、方向不对称、图与跨市场信息增量、局限 | B9, B11, R1 | 图与跨市场信息增量未形成可核验 R 基准，关联 SA-A04 |
| p4 | 引言结尾、相关文献 | - | 内容类型标注充分 |
| p5 | 跨市场及图方法文献 | - | 文献语境，排除 |
| p6 | 图神经网络文献 | - | 文献语境，排除 |
| p7 | 金融机器学习文献 | - | 文献语境，排除 |
| p8 | 数据源、2014–2021、pvCLCL 公式 | D1, D2, F1 | 覆盖 |
| p9 | OPCL/超额收益公式、ETF、各 500 只、平均市值、缩尾 | D3-D5, F2-F3, B1-B3 | D6 实际在本页但页面表漏关联，见 SA-A03 |
| p10 | 二部图定义、滚动向量、交易日历 | D8, F4 | 覆盖 |
| p11 | Figure 1、t 统计量公式、多重检验局限 | F4-F5 | 覆盖 |
| p12 | Figure 2、三日平滑示例、τ=2 筛边 | F5, B4 | 覆盖；示例参数已在 FIG2 登记 |
| p13 | Figure 3、行业分组、25 只/行业及 254/235 样本数 | D9, F4 | 精确选样规则和计数未提取，见 SA-A05 |
| p14 | Figure 4、行业块聚合、Figure 5 入度趋势、预测窗开头 | F6-F8 | Figure 5 的双向入度上升结论未登记，见 SA-A06 |
| p15 | Figure 5、市场时段、DST、l=1/0、预测方程 | D7, F8-F9, B4 | D7 错位，应关联 D8，见 SA-A03 |
| p16 | Figure 6、Figure 7、时点次序 | F4, F9, B4, B8 | 覆盖 |
| p17 | 十模型、OLS、LASSO | F9-F11, B11 | 覆盖 |
| p18 | LASSO、RIDGE、SVM、XGBoost 公式 | F11-F14 | 覆盖 |
| p19 | XGBoost、LGBM、RF、AdaBoost、ensemble-avg | F14-F18 | 覆盖 |
| p20 | ensemble-med、PnL、21 日流动性、仓位上限 | D6, F18-F20, B9-B10 | D6 错位，应关联 D7，见 SA-A03 |
| p21 | Sharpe、现实局限、250 日窗、10 日更新、预测期 | F21, B5-B9 | 覆盖 |
| p22 | 两方向、两类基线、六分位组合开头 | F22-F24, B4 | 覆盖 |
| p23 | 分位组合、Figure 8、US→CN 主结果 | F24, R1 | 覆盖；R1 定性数值直接回查 PDF 一致 |
| p24 | CN→US 更弱、同市场图与非图基线、跨市场图最强 | R1 | R1 仅定义 Figure 8，未承载本页三个核心比较基准，见 SA-A04 |
| p25 | Figure 10 累计 PnL | F20, F24 | 覆盖 |
| p26 | Figure 11、Figure 12 | F22-F24 | 图登记完整 |
| p27 | Figure 13、边随机替换敏感性 | SA1 | 覆盖 |
| p28 | 滞后敏感性、Figure 14、结论开头 | SA1-SA2 | 主设计覆盖，次级结论遗漏见 SA-A07 |
| p29 | 结论、未来研究、利益冲突 | R1 | 核心方向结论已覆盖；未来研究属非复现要素 |
| p30 | 参考文献 | - | 内容类型标注充分 |
| p31 | 参考文献 | - | 内容类型标注充分 |
| p32 | 参考文献 | - | 内容类型标注充分 |
| p33 | 参考文献 | - | 内容类型标注充分 |
| p34 | 参考文献 | - | 内容类型标注充分 |
| p35 | Appendix A–C 说明、超参数敏感性与 OPCL 基线结论 | SA3-SA5 | 参数精确值续至 p36；完整参数列遗漏见 SA-A02 |
| p36 | Table A.1 参数与 42 个 SR 单元 | R2, SA3 | SR 单元一致；表格抽取和 Parameters 列不完整，见 SA-A01、SA-A02 |
| p37 | Figure B.1、Figure B.2 | SA4 | 覆盖 |
| p38 | SPY 冲击条件、Figure C.1、Appendix D 开头 | SA5-SA6 | 覆盖 |
| p39 | Figure D.1、行业结论、Appendix E | SA6-SA7 | 覆盖 |
| p40 | Figure E.1 四种联合特征组合 | SA7 | 覆盖 |

## 遗漏清单

| ID | 检查项 | severity | 证据定位 | 一句依据 | 处置建议 |
| --- | --- | --- | --- | --- | --- |
| SA-A01 | C5 | critical | PDF p36；`workspace/r007_cross_market_return_forecasting/spec/tables_extracted.md:1` | PDF 明确存在 Table A.1，而 `tables_extracted.md:5` 声称未检测到表格，导致唯一数值基准表没有结构化表格提取证据。 | 重新提取或人工完整登记 Table A.1，并保留行列结构与页码。 |
| SA-A02 | C3/C5 | critical | PDF p36；`workspace/r007_cross_market_return_forecasting/spec/report_text.md:1853`；`workspace/r007_cross_market_return_forecasting/spec/spec.md:393` | PDF 表为 7×8 逻辑结构，但 R2 缩成 7×7 且 SA3 未补出 XGBoost、LGBM、RF、AdaBoost 的精确参数网格，Parameters 列不完备。 | 在 R2/SA3 完整登记四个模型的树深、叶子数、学习率和估计器数网格。 |
| SA-A03 | C2 | major | PDF p9、p15、p20；`workspace/r007_cross_market_return_forecasting/spec/spec.md:37`、`:43`、`:48` | 页面覆盖表漏掉 p9 的 D6，并把 p15 错关联 D7、p20 错关联 D6，正确关联应分别包含 p9→D6、p15→D8、p20→D7。 | 修正页面覆盖表的三个核心数据关联。 |
| SA-A04 | C2 | major | PDF p24；`workspace/r007_cross_market_return_forecasting/spec/report_text.md:1286`；`workspace/r007_cross_market_return_forecasting/spec/spec.md:376`；`workspace/r007_cross_market_return_forecasting/plan.md:146` | 原文“CN→US 显著更弱、同市场图优于非图、跨市场图总体最强”未形成独立 R 基准，现有 R1 只登记 Figure 8 的 US→CN 量级，无法逐项验证论文核心比较结论。 | 增补相应 R 要素或扩展 R1，并在 m4 验证点逐项引用。 |
| SA-A05 | C2 | major | PDF p13；`workspace/r007_cross_market_return_forecasting/spec/report_text.md:713`；`workspace/r007_cross_market_return_forecasting/spec/spec.md:416` | FIG3 标记为 reproduce，但规格仅写“代表性热图”，遗漏每行业取 25 只、不足 25 只全取及最终 254 美股/235 中股的构图规则与计数。 | 在 FIG3 关联要素中补齐选样规则、日期、行列方向和样本计数。 |
| SA-A06 | C2 | minor | PDF p14；`workspace/r007_cross_market_return_forecasting/spec/report_text.md:766`；`workspace/r007_cross_market_return_forecasting/spec/spec.md:181` | 原文指出两个方向的入度随时间上升并解释为跨市场连接增强，F7/FIG5 只登记计算定义和线色，遗漏该定性复核基准。 | 在 F7 或独立 R/图表备注中登记预期趋势。 |
| SA-A07 | C3 | minor | PDF p28；`workspace/r007_cross_market_return_forecasting/spec/report_text.md:1417`；`workspace/r007_cross_market_return_forecasting/spec/spec.md:444` | SA2 只摘录 SR 随 l 增大而下降，遗漏 qr6 降幅较小及 Lag 4 后轻微趋稳、可能与周度交易周期有关的原文结论。 | 在 SA2 补充次级形态与原文解释，验证时与主趋势分开核对。 |

## C5 独立数值复核记录

| 对象 | PDF 原始结构/数值 | spec 登记 | 独立结论 |
| --- | --- | --- | --- |
| R1 / Figure 8 正文 | SVM 多数 SR lower than one；其他方法多数 exceed one；部分 approaching two；RIDGE、LGBM、两种 ensemble 较强；U.S. pvCLCL 优于 U.S. OPCL | 三条量级及其他结论均已登记 | 与 PDF p23 一致 |
| R2 / Table A.1 SR 矩阵 | 7 方法×6 分位，共 42 个 mean±std 单元 | 42 个单元全部登记 | 逐格一致，无 R 数值差异 |
| R2 / Table A.1 Parameters | 7 方法均有参数列；四个树模型含多行网格 | 仅完整列出 LASSO/RIDGE/SVM，四个树模型只写“其余网格见 SA3”，而 SA3 无具体数值 | 不完整，见 SA-A02 |
| `tables_extracted.md` | PDF 有 1 张表 | 0 张表 | 不一致，见 SA-A01 |

Table A.1 中四个未完整登记的 PDF 参数网格独立抄核如下，仅作为审计证据，不替代修复：

- XGBoost：`max depth={3,6,9}`，`learning rate={0.01,0.1,0.2}`，`n estimators={50,100,300}`。
- LGBM：`num leaves={10,31,90}`，`learning rate={0.01,0.1,0.2}`，`n estimators={50,100,300}`。
- RF：`n estimators={50,100,300}`，`max depth={5,10,50}`。
- AdaBoost：`max depth={1,5,10}`，`n estimators={50,100,300}`，`learning rate={0.01,0.1,0.2}`。

## C6 抽查记录表

| 抽样要素ID | 类别 | 页码 | spec.md 摘录原文 | 回查 report_text.md 结果 | 判定 |
| --- | --- | --- | --- | --- | --- |
| D1 | D | p8 | “Daily U.S. stock data are sourced from the Center” | p8 可定位，跨行后接 Research in Security Prices (CRSP) | match |
| D7 | D | p20 | “the median daily traded volume of stock i over the 21-day interval” | p20 原句可定位 | match |
| D8 | D | p10 | “uses the trading calendar rather than the natural calendar.” | p10 原句可定位 | match |
| F2 | F | p9 | “the OPCL logarithmic raw return for stock i on day t can be calculated by:” | p9 原句及公式（2）可定位 | match |
| F5 | F | p11-p12 | “In our experiments, we set τ = 2, and select edges whenever \|tβ \| > τ” | p12 原句及阈值可定位 | match |
| F13 | F | p18 | “We use the radial basis function kernel throughout our experiment.” | p18 原句可定位 | match |
| F20 | F | p20 | “The PnL on day t is calculated with the following equation:” | p20 原句及公式（15）可定位 | match |
| B1 | B | p9 | “We select 500 stocks with the highest average market capitalizations” | p9 原句可定位，脚注同时说明全样本前视 | match |
| B6 | B | p21 | “update both the graphs and the predictive models every 10 days.” | p21 原句可定位 | match |
| B10 | B | p20 | “L is set to 100,000 USD for the U.S. market prediction” | p20 原句可定位，并接中国市场 1,500,000 CNY | match |
| R1 | R | p23 | “its SRs are mostly lower than one.” | p23 原句可定位；另直接回查 PDF p23 一致 | match |
| R2 | R | p36 | “Values are reported as mean ± standard deviation.” | p36 Table A.1 标题原句可定位；另直接回查 PDF p36 一致 | match |
| SA1 | SA | p27-p28 | “We randomly replace 20%, 40%, 60%, 80% and all of the edges.” | p27 原句可定位 | match |
| SA2 | SA | p28 | “Here we set l = 2, 3, ... when predicting Chinese stocks.” | p28 原句可定位 | match |
| SA5 | SA | p35, p38 | “We divide the SPY absolute pvCLCL returns into nested quantiles (qr1–qr6)” | 句首跨页后在 p38 可定位 | match |
| SA7 | SA | p39-p40 | “the predictor set X to include all stocks from both the U.S. and Chinese markets” | p39 原句可定位 | match |

## 审计结论

- 遗漏清单条目数：7（critical 2 / major 3 / minor 2）。
- C6 抽查命中率：16 / 16；无 hallucinated citation。
- R 类独立复核：R1 定性量级与 PDF p23 一致；R2 的 42 个 SR mean±std 单元与 PDF p36 逐格一致；R2 的 Parameters 列不完整。
- 已检查维度：
  - C1：正文及附录图表编号、连续性、原生标签到 FIG/TBL 的归一化、`fig_max/tbl_max` 均已独立重算；结论 pass。
  - C2：p1–p40 已逐页扫描；发现页面关联错位、核心结果基准和复现细节遗漏；结论 fail。
  - C3：敏感性、稳健性、参数、分组/行业、年度/子样本、附录、进一步研究等触发词均已检查；发现参数列和 SA2 次级结论遗漏；结论 pass_with_issues。
  - C4：股票数、模型数、基础模型/集成数、分位组合数、超参数模型数、扰动比例数及 D/F/B/R/SA 总数均已交叉重算；结论 pass。
  - C5：Table A.1 行列、42 个数值单元、参数列及 `tables_extracted.md` 已三方核对；因表格提取为零且参数列不完备，结论 fail。
  - C6：覆盖 D/F/B/R/SA 的 16 条引用已逐条回查 `report_text.md`，R 条目另以 PDF 终审；16 条均 match，结论 pass。

**verdict**: fail

## 第1轮修复复核

- 复核范围：原审计 SA-A01–SA-A07、外部审计 CDX-S-01–CDX-S-04，以及 `extract_diff.md` 中 DIF-01–DIF-07 的定向修复。
- 复核原则：只读取修复后产物并独立重算，不采信修复者完成声明；原审计记录及其 `fail` 结论作为历史记录保留。

### 独立重算记录

| 复核对象 | 独立重算结果 | 结论 |
| --- | --- | --- |
| Table A.1 结构 | `spec.md:397-405` 与 `tables_extracted.md:13-21` 均为 7 个方法数据行×8 个逻辑列（Methods、Parameters、qr1–qr6），每一数据行均为 8 列。 | pass |
| Table A.1 数值 | 从 `report_text.md:1853-1872` 独立提取 42 个 mean±std 单元；与 `spec.md:399-405`、`tables_extracted.md:15-21` 按行序逐格比较，42/42 一致，差异 0。 | pass |
| Table A.1 参数 | LASSO/RIDGE 的 λ、SVM 的 C，以及 XGBoost/LGBM/RF/AdaBoost 的 max depth、num leaves、learning rate、n estimators 均与 `report_text.md:1856-1872` 一致；`spec.md:483-487` 亦完整登记。 | pass |
| 55 条三方一致 | 独立提取 `spec.md` 的 D/F/B/R/SA 标题集合为 55 个、`coverage_matrix.md` 要素行集合为 55 个、`plan.md` 唯一要素引用集合为 55 个；三集合完全相同，无缺失、无多余。分类计数 D=9、F=24、B=11、R=4、SA=7，合计 55，与 `spec.md:10` 和 `coverage_matrix.md:4` 一致。 | pass |
| R3/R4 规划闭环 | R3/R4 已进入 spec 正文、图表关联、coverage_matrix、plan frontmatter milestone m4、核心结果表及 m4 验证点。 | pass |

### 原 issue 逐条复核

| 原 issue ID | 原 severity | 修复后状态 | 修复证据定位 | 独立复核依据 |
| --- | --- | --- | --- | --- |
| SA-A01 | critical | pass | `workspace/r007_cross_market_return_forecasting/spec/tables_extracted.md:5-23` | 已补录唯一 Table A.1、原生标题、页码、7×8 结构、7 个方法行、42 个 SR 数值格及表下注释；与 `report_text.md:1853-1875` 一致。 |
| SA-A02 | critical | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:397-408`、`:480-489`；`workspace/r007_cross_market_return_forecasting/spec/tables_extracted.md:13-21` | Parameters 列及四个树模型的精确网格已补齐；spec 与 tables 两份 Markdown 表逐单元一致，且参数逐项匹配 `report_text.md:1856-1872`。 |
| SA-A03 | major | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:37`、`:43`、`:48`、`:121-126`；`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:14-16` | 页面覆盖现为 p9→D6、p15→D8、p20→D7，D8 页码扩为 p10、p15；与 report_text 对应页内容一致。 |
| SA-A04 | major | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:410-433`、`:449`、`:452-453`；`workspace/r007_cross_market_return_forecasting/plan.md:58-60`、`:152-155`、`:182-187` | R3 已登记 CN→US 显著更弱，R4 已登记图同市场优于非图及跨市场图总体最强；原文分别可定位于 `report_text.md:1286-1294` 和 `:1304-1326`，m4 已明确逐项验证。 |
| SA-A05 | major | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:443` | FIG3 已补日期、每行业最多 25 只、不足全取、254 美股/235 A 股、行列方向与颜色含义；与 `report_text.md:713-737` 一致。 |
| SA-A06 | minor | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:181-188`、`:445` | F7 与 FIG5 均补充两个方向入度随时间上升及跨市场连接增强结论；与 `report_text.md:766-778` 一致。 |
| SA-A07 | minor | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:472-478` | SA2 已补 Lag 4 后轻微趋稳及周度交易周期解释；与 `report_text.md:1417-1423` 一致。 |
| CDX-S-01 | major | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:410-433`；`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:55-56`；`workspace/r007_cross_market_return_forecasting/plan.md:152-155` | R3/R4 已分别承接反向预测与两类基线比较锚点，三份产物的页码、优先级和 milestone 一致。 |
| CDX-S-02 | minor | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:43`、`:121-126`；`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:16` | p15 已由 D7 改为 D8，D8 页码为 p10、p15；市场时段与交易日历证据均有承接。 |
| CDX-S-03 | minor | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:443` | FIG3 的每行业上限、少于上限时全取及 254/235 计数均已完整登记。 |
| CDX-S-04 | minor | pass | `workspace/r007_cross_market_return_forecasting/spec/spec.md:464-478`、`:498-504` | SA1 已补 qr6 韧性，SA2 已补 Lag 4 后趋稳与周度解释，SA5 已补 RIDGE 相对不稳定；分别匹配 `report_text.md:1391-1399`、`:1417-1423`、`:1913-1923`。 |

### 第1轮复核结论

- 原 critical：2 项，已清零。
- 原 major：3 项，已清零；外审 major 1 项亦已清零。
- 原 minor：2 项，已清零；外审 minor 3 项亦已清零。
- 新发现 issue：0。
- 已复核维度：Table A.1 7×8 结构 / 42 个数值格 / 完整参数列 / R3 / R4 / D6-D8 页面映射 / FIG3 参数 / FIG5 趋势 / SA1、SA2、SA5 次级结论 / 55 条 spec-coverage-plan 三方一致。

**verdict**: pass

## 定点复核附录：RC-S-01 / SA-A07 残余项

- 复核范围仅限外部增量复核 RC-S-01 与原 SA-A07 的未闭环部分。
- 原始复核意见定位：`workspace/r007_cross_market_return_forecasting/audit/spec_recheck_external.md:11`、`:28`、`:32-39`。

### p28 三部分逐句核验

| 核验点 | report_text.md 原文证据 | spec.md 登记证据 | 判定 |
| --- | --- | --- | --- |
| qr6 随 lag 增加时下降较不明显 | `workspace/r007_cross_market_return_forecasting/spec/report_text.md:1419`：“The decline is again less pronounced for qr6,” | `workspace/r007_cross_market_return_forecasting/spec/spec.md:477` 逐字登记，并在 `:480` 给出中文释义 | pass |
| 大幅度信号可能捕捉更持久的跨市场效应 | `workspace/r007_cross_market_return_forecasting/spec/report_text.md:1421`：“suggesting that large-magnitude signals may capture more persistent cross-market effects.” | `workspace/r007_cross_market_return_forecasting/spec/spec.md:478-480` 分三行完整登记原文并准确释义 | pass |
| Lag 4 后轻微稳定及周度交易周期解释 | `workspace/r007_cross_market_return_forecasting/spec/report_text.md:1421-1423`：“A mild stabilization beyond Lag 4 likely reflects weekly trading-cycle effects.” | `workspace/r007_cross_market_return_forecasting/spec/spec.md:481` 完整登记 | pass |

### issue 闭环判定

| issue ID | 复核状态 | 证据定位 | 结论 |
| --- | --- | --- | --- |
| SA-A07 残余项 | pass | `spec.md:472-482` 对照 `report_text.md:1417-1423` | SA2 已同时保留主趋势、qr6 跨分位形态、持久性解释和 Lag 4 后稳定结论，原残余项已闭环。 |
| RC-S-01 | pass | `spec_recheck_external.md:32-39`；`spec.md:477-481`；`report_text.md:1419-1423` | 外部增量意见要求的两句 qr6 结论及其解释已忠实登记，不再存在遗漏。 |

- 边界核验：`spec.md:469` 的 SA1 qr6 韧性仍归属于 Figure 14a 边替换分析；本次通过依据完全来自 `spec.md:477-481` 的 SA2/Figure 14b 滞后分析，二者未混用。
- 新发现 issue：0。

verdict: pass
