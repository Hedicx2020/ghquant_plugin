# 提取完整性审计

- report_id: `r006_macro_regime_factor_allocation`
- mode: `spec`
- 审计轮次: 修复轮 1 独立复核
- 审计日期: 2026-07-26
- 原始 PDF: `/Users/hedi/Downloads/ssrn-6962678.pdf`
- 审计边界: 仅使用任务指定的 PDF、`report_text.md`、`tables_extracted.md`、`spec.md`、`coverage_matrix.md`、`plan.md`、`extract_diff.md` 及两份原审计文件；未读取 extractor/planner 完成汇报、主会话叙事、`audit_responses.md` 或 `state.json`。
- 审计方法: 页数、图表编号、表格行列、要素计数、矩阵行和 plan 要素并集均独立重算；数值以 PDF 原文为终审。

## C1 图表编号连续性

### 独立重算记录

| 命名空间 | PDF / report_text.md 实际编号集合 | 最大编号 | 连续性 | spec 登记结果 |
| --- | --- | ---: | --- | --- |
| 主文 Figure | Figure 1–8 | 8 | 连续 | 8 个，完整 |
| 附录 Figure | Figure IA.1–IA.11 | 11 | 连续 | 11 个，完整 |
| 主文 Table | Table 1–15 | 15 | 连续 | 15 个，完整 |
| 附录 Table | Table IA.1–IA.34；IA.17A/17B、IA.20A/20B 各为两个物理表 | 34 | 连续 | 36 个物理表，完整 |

- PDF 独立读取为 104 个物理页；`report_text.md` 独立检出 104 个页标记，范围 p1–p104，无缺页、重页。
- 独立正则重算得到 `fig_max=11`、`tbl_max=34`，与 `spec.md:8-10` 的声明一致。
- 图物理数为 8+11=19；表物理数为主文 15+附录 36=51，与 `spec.md:10` 的 `FIG_registered=19`、`TBL_registered=51` 一致。
- `spec.md:1206-1275` 的登记清单逐项覆盖上述编号；IA.17A/B、IA.20A/B 的物理拆分也均有独立登记行。

结论: `no_findings`。

## C2 逐页覆盖扫描

- `spec.md:26-131` 独立计得 104 个页面覆盖行，p1–p104 各一行，无遗漏、重复或越界。
- p25、p26 为参考文献，p50 为披露页，p98 为附录说明页；均有显式内容类型。
- p40 Table 14 与 p99 Table IA.31 是解释性证据地图，不含新增结果数值，登记为 `reference_only` 合理。
- p63 Table IA.10 仅有 `Family` 表头且表体为空，页面覆盖表明确写明空表并关联 A9，没有推算数据。
- 修复涉及的 p65、p68、p70、p71-p72 已分别关联 R25、R26、R27、R28；p75-p76、p77、p80、p82 仍保留对 R19–R22 的真实内容关联。
- 未发现含三个以上百分数或公式符号的实证页既无 D/F/B/R/SA 关联又无类型/排除说明。

结论: `no_findings`。

## C3 触发词检查

对 sensitivity、robustness、parameter、group、subsample、market-cap、holdout、placebo、permutation、appendix、further、additional、drop-one、ablation、crisis、decade、capacity、state-specificity 等原文同义词逐页检索，结果如下。

| 触发主题 | PDF 主要页码 | spec 关联 |
| --- | --- | --- |
| 配置规则与约束变体 | p28, p61 | SA1, R1, R17 |
| 权重时间分布 | p15, p30, p43, p62-p64 | SA2, R3, R18 |
| 家族组合与 drop-one | p16, p41, p79-p81 | SA3, R13, R21 |
| 完整状态收益面 | p34, p46, p75-p76 | SA4, R7, R19 |
| 横截面构造、危机、分年代 | p17-p18, p35, p47, p77-p78 | SA5-SA6, R8, R20 |
| 市值与容量分组 | p36, p48-p49, p84-p86 | SA7, R9 |
| 形成期与确认期 holdout | p39, p91 | SA8, R12 |
| 随机、日历、移位、标签 placebo | p20, p37, p88, p92-p93 | SA9, R10 |
| 宏观块逐个剔除 | p20, p37, p89 | SA10, R10 |
| 发布滞后与信息时点 | p55, p90 | SA11, R14 |
| 模型类别与高计算量基准 | p20, p38, p45, p71-p73, p94-p97 | SA12, R11, R28 |
| 发表年份覆盖 | p102-p103 | SA13, R23 |
| 逐市场事件剔除 | p104 | SA14, R24 |

未发现触发词命中页缺少 SA/F/R 关联且无排除说明的情形。

结论: `no_findings`。

## C4 计数交叉

### 独立计数

| 类别 | frontmatter 声明 | spec 标题块正则重算 | coverage_matrix 数据行 | plan 要素并集 | 判定 |
| --- | ---: | ---: | ---: | ---: | --- |
| D | 10 | 10 | 10 | 10 | 一致 |
| F | 16 | 16 | 16 | 16 | 一致 |
| B | 15 | 15 | 15 | 15 | 一致 |
| R | 28 | 28 | 28 | 28 | 一致 |
| SA | 14 | 14 | 14 | 14 | 一致 |
| 合计 | 83 | 83 | 83 | 83 | 一致 |

- `coverage_matrix.md:4` 的 `row_count=83` 与 `coverage_matrix.md:9-91` 的 83 个唯一要素行一致；无缺号、重复或额外 ID。
- `plan.md:49,54,59,64,69` 的五个 milestone 共列 83 次要素引用，独立取并集仍为 83；无重复、遗漏或额外 ID。
- PDF 的计数声明——212 个特征、8 个异常家族、23 个宏观序列、8 个宏观块、479 个样本外月、10 年初始训练窗、12 年固定验证窗——均有对应 D/F/B/R 要素，未发现 spec 数量少于原文声明。
- 图表登记独立重算为 `FIG19/TBL51`，与 frontmatter 一致。

结论: `no_findings`。

## C5 基准表完备

### tables_extracted.md 物理表复核

- 独立解析 `tables_extracted.md` 得到 51 个 `## 物理页` 表块：主文 15 个、附录 36 个。
- 51 个表块对应 PDF 中 Table 1–15、Table IA.1–IA.34，并单列 IA.17A/17B、IA.20A/20B；没有把 p42、p44、p45、p47、p49、p64、p69、p73、p86、p93、p96、p97 的 17 个图形识别对象计为表。
- 对 51 个物理表逐行核对 PDF 文本层；长文本表因 PDF 行末断词产生的 `inter-pretation`、`cap-i-talization` 等已按版面合并，未改变语义或数值。
- 百分比、正负号、列单位、Panel 标签及空白格均按 PDF 保留。Table 4 两个相关列的 16 个数据单元均为空；Table IA.10 仅有一列表头、0 个数据行。

### 指定表重点抽查

| 表 | PDF 完整网格 | tables_extracted.md 定位 | PDF 对照结果 | 判定 |
| --- | --- | --- | --- | --- |
| Table 3 p29 | 8×10 | `tables_extracted.md:64-75` | 8 条规则、10 列，含回撤负号和表头百分比单位 | pass |
| Table 4 p30 | 8×8 | `tables_extracted.md:77-90` | 8 条家族行；Trend/Valuation corr. 两列共 16 格原生空白 | pass |
| Table 13 p39 | 4×6 | `tables_extracted.md:237-244` | 四行齐全，Continuation×Valuation 形成期行存在 | pass |
| Table IA.10 p63 | 0×1 | `tables_extracted.md:457-463` | PDF 仅 `Family` 表头，无数据行、无其他列 | pass |
| Table IA.11 p65 | 8×5 | `tables_extracted.md:464-475` | 8 家族、Signals/IC/两类 t 全列齐全 | pass |
| Table IA.13 p68 | 15×8 | `tables_extracted.md:497-515` | 15 条规则，EW/VW/alpha/months 全列齐全 | pass |
| Table IA.14 p70 | 15×8 | `tables_extracted.md:517-535` | 15 条规则，IC、增量、FMB、月份全列齐全 | pass |
| Table IA.15 p71 | 18×8 | `tables_extracted.md:537-558` | 18 个模型，增量 IC 符号与 alpha 列齐全 | pass |
| Table IA.16 p72 | 33×8 | `tables_extracted.md:560-596` | 18 条股票/层级模型+15 条家族配置，共 33 行 | pass |
| Table IA.17A p75 | 32×8 | `tables_extracted.md:598-633` | Credit/Growth/Inflation/Liquidity 四块×八家族 | pass |
| Table IA.17B p76 | 32×8 | `tables_extracted.md:635-670` | Rates/Risk/Trend/Valuation 四块×八家族 | pass |
| Table IA.20A p79 | 24×9 | `tables_extracted.md:730-757` | 三组规则×八个剔除家族 | pass |
| Table IA.20B p80 | 24×9 | `tables_extracted.md:759-786` | 三组规则×八个剔除家族 | pass |
| Table IA.34 p102 | Panel A 8×3；Panel B 9×6 | `tables_extracted.md:1033-1060` | Panel、发表覆盖数量和百分比单位齐全 | pass |
| Table IA.33 p104 | 10×6 | `tables_extracted.md:1062-1075` | 全样本+九次事件剔除，百分号和负号齐全 | pass |

### R1–R28 完整网格复核

下表的行×列均为数据行×含标签列在内的列数；每个 R 网格均先与 `tables_extracted.md` 比较，再回 PDF 核定。

| R | 对应 PDF 表 | 独立重算完整网格 | 判定 |
| --- | --- | --- | --- |
| R1 | Table 2 | Panel A 8×4；Panel B 8×6 | pass |
| R2 | Table 3 | 8×10 | pass |
| R3 | Table 4 | 8×8；两相关列原生空白，spec 记 n/a | pass |
| R4 | Table 5 | 8×9 | pass |
| R5 | Table 6 | 10×9 | pass |
| R6 | Table 7 | 9×8 | pass |
| R7 | Table 8 | 14×8 | pass |
| R8 | Table 9 | 6×7 | pass |
| R9 | Table 10 | 8×7 | pass |
| R10 | Table 11 | Panel A 10×5；Panel B 8×4；Panel C 8×6 | pass |
| R11 | Table 12 | 12×8 | pass |
| R12 | Table 13 | 4×6 | pass |
| R13 | Table 15 | 5×7 | pass |
| R14 | Table IA.4 | 16×9 | pass |
| R15 | Table IA.6 | 12×6 | pass |
| R16 | Table IA.7 | 12×8 | pass |
| R17 | Table IA.8 | 18×7 | pass |
| R18 | Table IA.9 | 8×8 | pass |
| R19 | Table IA.17A/17B | 32×8+32×8=64×8 | pass |
| R20 | Table IA.18 | 16×8 | pass |
| R21 | Table IA.20B | 24×9 | pass |
| R22 | Table IA.21 | 40×9 | pass |
| R23 | Table IA.34 | Panel A 8×3；Panel B 9×6 | pass |
| R24 | Table IA.33 | 10×6 | pass |
| R25 | Table IA.11 | 8×5 | pass |
| R26 | Table IA.13 | 15×8 | pass |
| R27 | Table IA.14 | 15×8 | pass |
| R28 | Table IA.15 18×8；Table IA.16 33×8 | 两个完整网格均齐全 | pass |

- R12 的 Continuation×Valuation formation 行为 `0.05%、t=0.05、80/80 月`；confirmation 行为 `0.00%、t=0.00、223/2 月`。
- R12 主表采用 predicted-direction，Liquidity/limits×Trend 为 `+4.26%、+1.86%`；Table IA.27 原始 high-minus-low 为 `-4.26%、-1.86%`，t 值同步为负。`spec.md:682-697` 与 PDF p39、p91 一致。
- R25–R28 的新增数值、页码、coverage_matrix 行和 plan milestone 引用均存在：R25 在 m2，R26–R28 在 m5；没有与旧 R19–R22 错位。

结论: `no_findings`。

## C6 幻觉引用抽查

### 抽查记录表

共抽查 14 条，覆盖 D/F/B/R/SA 五类，R 类 4 条。

| 抽样要素ID | 类别 | spec 页码 | spec.md 摘录原文 | report_text.md 回查证据 | 判定 |
| --- | --- | --- | --- | --- | --- |
| D1 | D | p2, p10 | “The panel contains 212 characteristics” | p10，`report_text.md:448-453` 可定位 | match |
| D5 | D | p11, p53, p101 | “The empirical package contains 23 macro series.” | p11，`report_text.md:496-501` 可定位 | match |
| F5 | F | p12-p13 | “The main allocation rule is a mixture-of-experts design.” | p12，`report_text.md:555-562` 可定位 | match |
| F8 | F | p12-p13 | “The allocation weights are constrained to be nonnegative and to sum to one.” | p13，`report_text.md:572-582` 可定位 | match |
| B4 | B | p2, p11, p27 | “a fixed 12-year validation window” | p2，`report_text.md:68-72` 跨行可定位 | match |
| B12 | B | p12, p29, p35-p36 | “equal-weight and value-weight long-short returns” | p12，`report_text.md:527-533` 可定位；修复后的页码包含真实原文页 | match |
| R2 | R | p29 | “Table 3: Anomaly-Family Allocation Performance” | p29，`report_text.md:1253-1260` 可定位，数值网格一致 | match |
| R12 | R | p39, p91 | “Table 13: Holdout and Mechanism Persistence Evidence” | p39，`report_text.md:1467-1477` 可定位，四行和符号另经 PDF p91 复核 | match |
| R25 | R | p65 | “Table IA.11. Signal Composition Within Anomaly Families” | p65，`report_text.md:2263-2272` 可定位 | match |
| R28 | R | p71-p72 | “Table IA.15. Stock-Level Horse-Race Detail” | p71，`report_text.md:2425-2433` 可定位；IA.16 在 p72 连续登记 | match |
| SA2 | SA | p15, p30, p43, p62-p64 | “showing that macro-regime memory reallocates capital” | p43，`report_text.md:1573-1577` 可定位；结论讨论在 p15 `:684-691` | match |
| SA10 | SA | p20, p37, p89 | “how performance changes when individual macro blocks are removed” | p89，`report_text.md:3094-3099` 可定位；结论讨论在 p20 `:908-914` | match |
| SA12 | SA | p20, p38, p45, p71-p73, p94-p97 | “model complexity is a benchmark object” | p38，`report_text.md:1462-1465` 可定位；结论讨论在 p20 `:932-936` | match |
| SA14 | SA | p104 | “excluding named market episodes one at a time” | p104，`report_text.md:3449-3453` 可定位 | match |

C6 抽查命中率: 14/14。

### B12 与指定 SA 页码扩查

| 要素 | 修复后页码 | 独立回查结果 | 判定 |
| --- | --- | --- | --- |
| B12 | p12, p29, p35-p36 | 精确摘录在 p12 `report_text.md:529-533`；结果页保留 EW/VW 表头 | pass |
| SA2 | p15, p30, p43, p62-p64 | p15 有权重时变结论，p43 有原文图注 | pass |
| SA3 | p16, p41, p79-p81 | p41 有原文表注；讨论段从 p15 末延续至 p16，p16 有“dominant channels are continuation and valuation”的近似原文，满足 OCR/跨页近似定位 | pass |
| SA5 | p18, p35, p47, p77-p78 | p18 `report_text.md:828-838` 有跨构造及经济幅度结论 | pass |
| SA6 | p17, p77-p78 | p17 `report_text.md:785-799` 有 structural rather than episodic 结论 | pass |
| SA9 | p20, p37, p88, p92-p93 | p20 `report_text.md:922-926` 有 smaller patterns 结论，p92 有原文表注 | pass |
| SA10 | p20, p37, p89 | p20 `report_text.md:908-914` 有 trend block 结论，p89 有原文表注 | pass |
| SA12 | p20, p38, p45, p71-p73, p94-p97 | p20 `report_text.md:932-936` 有 pooled ridge 结论，p38 有原文表注 | pass |

结论: `no_findings`。

## DIF-01–DIF-06 修复复核

| 差异ID | 独立复核证据 | 结果 |
| --- | --- | --- |
| DIF-01 | `tables_extracted.md:10-1075` 独立解析为 51 个物理表块；主文 15、附录 36；PDF p27-p41、p52-p104 逐表核对，17 个图形识别对象未计入 | pass |
| DIF-02 | R1–R24 的 24 个完整网格与对应 tables_extracted 表逐行、逐列、逐符号比较，行数与列数全部一致，详见 C5 | pass |
| DIF-03 | R25–R28 分别覆盖 IA.11、IA.13、IA.14、IA.15/IA.16；`coverage_matrix.md:74-77` 和 `plan.md:54,69` 同步引用 | pass |
| DIF-04 | `spec.md:682-697` 已含 Continuation×Valuation formation 行；PDF p39、p91 与 `tables_extracted.md:237-244,955-962` 的正负号一致 | pass |
| DIF-05 | `spec.md:392-397`、`coverage_matrix.md:46` 已补 p12；精确摘录位于 `report_text.md:529-533` | pass |
| DIF-06 | `spec.md:1286-1369` 与 `coverage_matrix.md:79-89` 已为 SA2/3/5/6/9/10/12 补入正文讨论页；逐条回查均可精确或跨页近似定位 | pass |

## 遗漏清单

本轮未发现需要登记的遗漏或错误。

- issue 条目数: 0
- critical: 0
- major: 0
- minor: 0

## 审计结论

- 意见数: 0
- DIF-01–DIF-06: 6/6 pass
- C6 抽查命中率: 14/14
- 已检查维度:
  - C1：已独立重算 PDF 页数、主文/附录图表编号集合、`fig_max/tbl_max`、FIG/TBL 物理数和登记数；无问题。
  - C2：已逐页核对 p1–p104 页面覆盖、内容类型和修复页关联；无问题。
  - C3：已检查敏感性、稳健性、参数、分组、子样本、市值、危机、附录、进一步、安慰剂、剔除、留出等触发词及 SA/F/R 映射；无问题。
  - C4：已交叉核对 frontmatter、83 个 spec 标题块、83 个矩阵行、plan 的 83 个唯一要素并集及 FIG19/TBL51；无问题。
  - C5：已核对 51 个物理表、重点指定表及 R1–R28 完整网格，包含 Panel、单位、正负号和原生空白格；无问题。
  - C6：已完成 14 条 D/F/B/R/SA 引用抽查并扩查 B12 与 7 个指定 SA 页码；全部 match。

VERDICT: pass
