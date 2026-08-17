# 提取完整性审计

- report_id: `r006_macro_regime_factor_allocation`
- mode: `spec`
- 审计日期: 2026-07-26
- 原始 PDF: `/Users/hedi/Downloads/ssrn-6962678.pdf`
- 审计原则: 仅对照 PDF、提取文本、spec 三件套与 plan；未读取被审者完成汇报、`audit_responses.md` 或 `state.json`；所有页数、编号、计数和数值均独立重算。

## C1 图表编号连续性

### 独立重算记录

| 命名空间 | PDF 实际编号集合 | 最大编号 | 连续性 | spec 登记 |
| --- | --- | --- | --- | --- |
| 主文 Figure | Figure 1–8 | 8 | 连续 | 8 行，完整 |
| 附录 Figure | Figure IA.1–IA.11 | 11 | 连续 | 11 行，完整 |
| 主文 Table | Table 1–15 | 15 | 连续 | 15 行，完整 |
| 附录 Table | Table IA.1–IA.34；其中 IA.17A/17B、IA.20A/20B 为分表 | 34 | 连续 | 36 个物理表行，完整 |

- PDF 物理页数独立重算为 104，与 `spec.md:8` 的 `pdf_pages: 104` 一致。
- 按编号数字后缀独立重算 `fig_max=11`、`tbl_max=34`，与 `spec.md:9` 的 `exhibit_declared` 一致。
- 图登记总数为 8+11=19；表登记总数为 15+34+2 个 A/B 增量=51，与 `spec.md:10` 的 `FIG_registered=19`、`TBL_registered=51` 一致。
- `report_text.md` 与 PDF 文本层检出的编号集合一致，未发现缺号或未登记编号。

结论: `no_findings`。

## C2 逐页覆盖扫描

- `report_text.md` 独立计得 104 个 `===== PAGE n =====` 标记，范围 p1–p104，无缺页、重页。
- `spec.md:26-131` 的页面覆盖表独立计得 104 行，所有物理页均有内容类型；参考文献、披露页、附录说明页也均有显式类型。
- 每页均对照 PDF 文本层扫描。未发现整页未登记；但 p65、p68-p73 的 R 关联指向了其他附录表，详见 `SA-A03`。

结论: `findings`，1 条 major。

## C3 触发词检查

英文原文中对 sensitivity/robustness/parameter/group/subsample/market-cap/holdout/placebo/permutation/appendix/further/additional/drop/ablation/crisis/decade 等同义触发词逐页检索，并核对如下映射：

| 触发主题 | PDF 主要页码 | spec 关联 |
| --- | --- | --- |
| 配置规则与约束变体 | p28, p61 | SA1 |
| 权重时间分布 | p30, p43, p62-p64 | SA2 |
| 家族组合与 drop-one | p41, p79-p81 | SA3 |
| 完整状态收益面 | p34, p46, p75-p76 | SA4 |
| 横截面构造 | p35, p47, p77-p78 | SA5 |
| 危机与分年代 | p77-p78 | SA6 |
| 市值/容量分组 | p36, p48-p49, p84-p86 | SA7 |
| 形成期/确认期 holdout | p39, p91 | SA8 |
| 日历、随机、移位、标签 placebo | p37, p88, p92-p93 | SA9 |
| 宏观块剔除 | p37, p89 | SA10 |
| 发布滞后与信息时点 | p55, p90 | SA11 |
| 模型类别与高计算量基准 | p38, p45, p71-p73, p94-p97 | SA12 |
| 发表年份覆盖 | p102-p103 | SA13 |
| 逐市场事件剔除 | p104 | SA14 |

未发现命中页缺少 SA/F/R 关联且无排除说明的情形。A1/A2/A3/A6 的 experimental 方法级降级只出现在 `ambiguities.md` 与 `plan.md`，并明确标注“不是原文事实”；`spec.md` 对应 F3/F5/F10 仍只陈述论文披露的概念和歧义，没有把 AS24–AS27 参数冒充论文参数。

结论: `no_findings`。

## C4 计数交叉

### 独立计数

| 类别 | frontmatter | spec 标题块正则重算 | coverage_matrix 数据行 | 结果 |
| --- | ---: | ---: | ---: | --- |
| D | 10 | 10 | 10 | 一致 |
| F | 16 | 16 | 16 | 一致 |
| B | 15 | 15 | 15 | 一致 |
| R | 24 | 24 | 24 | 一致 |
| SA | 14 | 14 | 14 | 一致 |
| 合计 | 79 | 79 | 79 | 一致 |

- `coverage_matrix.md:1-94` 的 `row_count=79` 与矩阵 79 个要素行一致。
- `plan.md:44-69` 的五个 milestone 独立解析得到 79 个 `elements`，79 个唯一，无遗漏、无重复、无额外 ID。
- PDF 摘要、引言、结论所述 212 个特征、8 个异常家族、23 个宏观序列、8 个宏观块、479 个样本外月、10 年训练窗和 12 年验证窗均有对应 D/F/B/R 要素。

结论: `no_findings`。

## C5 基准表完备

### tables_extracted.md 完备性

- `tables_extracted.md:1-4` 声称仅 12 页、17 个“表格”；其实际内容位于 p42、p44、p45、p47、p49、p64、p69、p73、p86、p93、p96、p97，均为图形元素被 pdfplumber 误识别为表。
- PDF 中真正的主表 p27-p41，以及附录数值表 p52-p63、p65、p67-p68、p70-p72、p75-p80、p82、p84-p85、p88-p92、p94-p95、p99、p101-p102、p104，均未形成对应行列表格。
- 因此 24 个 R 要素均无法与 `tables_extracted.md` 做三方逐格比对，详见 `SA-A01`。

### 24 个 R 要素与 PDF 独立行列复核

下表中的“PDF 行×列”为数据行数×含标签列在内的列数；分面表另作说明。

| R ID | PDF 基准 | PDF 完整网格 | spec 已录网格 | 判定 |
| --- | --- | --- | --- | --- |
| R1 | Table 2 p28 | Panel A 8 行；Panel B 8×6 | 仅 Panel B 3×5 | 少面板、少行、少列 |
| R2 | Table 3 p29 | 8×10 | 3×9 | 少 5 行，漏 EW t-statistic 列 |
| R3 | Table 4 p30 | 8×8 | 4×8 | 少 4 行 |
| R4 | Table 5 p31 | 8×9 | 仅 Mixture of experts 的 6 个指标 | 少 7 行及若干列 |
| R5 | Table 6 p32 | 10×9 | 2×4 | 少 8 行及 5 列 |
| R6 | Table 7 p33 | 9×8 | 3×8 | 少 6 行 |
| R7 | Table 8 p34 | 14×8 | 3×8 | 少 11 行 |
| R8 | Table 9 p35 | 6×7 | 5×7 | 少 Liquid-proxy universe 行 |
| R9 | Table 10 p36 | 8×7 | 5×7 | 少 3 行 |
| R10 | Table 11 p37 | Panel A/B/C 共 26 行 | 4 个选摘行 | 三面板严重截断 |
| R11 | Table 12 p38 | 12×8 | 4×7 | 少 8 行，漏 Benchmark role 列 |
| R12 | Table 13 p39 | 4×6 | 3×6 | 少 1 行 |
| R13 | Table 15 p41 | 5×7 | 4×6 | 少 1 行，漏 All-family mean 列 |
| R14 | Table IA.4 p55 | 16×9 | 4×9 | 少 12 行 |
| R15 | Table IA.6 p59 | 12×6 | 3×6 | 少 9 行 |
| R16 | Table IA.7 p60 | 12×8 | 3×8 | 少 9 行 |
| R17 | Table IA.8 p61 | 18×7 | 3×7 | 少 15 行 |
| R18 | Table IA.9 p62 | 8×8 | 3×8 | 少 5 行 |
| R19 | Table IA.17A/17B p75-p76 | 64×8 | 4×8 | 少 60 行 |
| R20 | Table IA.18 p77 | 16×8 | 5×7 | 少 11 行，漏 Test group 列 |
| R21 | Table IA.20B p80 | 24×10 | 3×9 | 少 21 行，漏 Allocation rule 列 |
| R22 | Table IA.21 p82 | 40×9 | 3×9 | 少 37 行 |
| R23 | Table IA.34 p102 | Panel A 8 行；Panel B 9×6 | 仅 Panel B 5×6 | 漏 Panel A，Panel B 少 4 行 |
| R24 | Table IA.33 p104 | 10×6 | 4×6 | 少 6 行 |

对 spec 已列出的 R 数值逐位回查 PDF 原文，未发现已录单元格的数字、正负号或百分号冲突；但 R 表普遍只选摘部分行列，不满足“逐格一致、缺格写 n/a”的完备性要求，详见 `SA-A02`。

结论: `findings`，2 条 critical。

## C6 幻觉引用抽查

### 抽查记录表

共抽查 17 条，覆盖 D/F/B/R/SA，R 类 5 条；另扩查 SA 的结论引用定位。

| 抽样要素ID | 类别 | 页码 | spec.md 摘录原文 | 回查 report_text.md 结果 | 判定 |
| --- | --- | --- | --- | --- | --- |
| D1 | D | p2, p10 | "The panel contains 212 characteristics" | p10，`report_text.md:450` 原文可定位 | match |
| D5 | D | p11, p53, p101 | "The empirical package contains 23 macro series." | p11，`report_text.md:497` 原文可定位 | match |
| D10 | D | p10, p102-p103 | "its publication year is no later than" | p102，`report_text.md:3427` 原文可定位 | match |
| F5 | F | p12-p13 | "The main allocation rule is a mixture-of-experts design." | p13，`report_text.md:560` 原文可定位 | match |
| F8 | F | p12-p13 | "The allocation weights are constrained to be nonnegative and to sum to one." | p13，`report_text.md:578` 原文可定位 | match |
| F9 | F | p13-p14 | "The hierarchical 212-signal layer converts family allocation" | p13，`report_text.md:600` 原文可定位 | match |
| B4 | B | p2, p11, p27 | "a fixed 12-year validation window" | p2，`report_text.md:69-70` 跨行可定位 | match |
| B9 | B | p15, p29 | "Newey–West inference is monthly." | p29，`report_text.md:1269` 原文可定位 | match |
| B12 | B | p29, p35-p36 | "equal-weight and value-weight long-short returns" | 精确原文位于 p12 `report_text.md:532`；所引 p29、p35-p36 无该摘录 | mismatch |
| R2 | R | p29 | "Table 3: Anomaly-Family Allocation Performance" | p29，`report_text.md:1255` 原文可定位 | match |
| R4 | R | p16, p31 | "mean hierarchical IC of 0.0508" | p16，`report_text.md:735` 原文可定位 | match |
| R5 | R | p16-p17, p32 | "mean IC of 0.0725" | p16，`report_text.md:751` 原文可定位 | match |
| R21 | R | p80 | "Mixture of experts    Continuation    2.13" | p80，`report_text.md:2761` 表格行可定位 | match |
| R24 | R | p104 | "Table IA.33. Liquidity/Limits Trend Reversal by Episode Exclusion" | p104，`report_text.md:3453` 原文可定位 | match |
| SA2 | SA | p30, p43, p62-p64 | "showing that macro-regime memory reallocates capital" | p43，`report_text.md:1576` 原文可定位 | match |
| SA9 | SA | p37, p88, p92-p93 | "shifted, calendar, and relabeled alternatives" | p92，`report_text.md:3164` 原文可定位 | match |
| SA14 | SA | p104 | "excluding named market episodes one at a time" | p104，`report_text.md:3451` 原文可定位 | match |

### SA 结论引用扩查

SA2、SA3、SA5、SA6、SA9、SA10、SA12 的 `- 结论: >` 内容确能在论文讨论段找到，但不在各自 `- 页码:` 所列结果页内；实际讨论位置分别在 p15、p16、p18、p17、p20、p20、p20。它们不是凭空捏造，但页码定位不完整，详见 `SA-A05`。

结论: 16/17 match；1 条 mismatch，对应 1 条 critical；另有 1 条 major 的系统性结论页码问题。

## 遗漏清单

| ID | 检查项 | severity | 证据定位 | 一句依据 | 修复建议 |
| --- | --- | --- | --- | --- | --- |
| SA-A01 | C5 | critical | `tables_extracted.md:1-4,7-223`；PDF p27-p41、p52-p104 | 文件声称的 17 个表均为图形误识别，51 个实际数值表没有可逐格复核的行列提取。 | 重新按 PDF 表格区域提取主文与附录全部 51 个物理表，保留标题、面板、行列、正负号、单位和空白格；提取失败须逐表登记，不得用图形伪表充数。 |
| SA-A02 | C5 | critical | PDF p29 对照 `spec.md:435-446`；其余 23 个 R 见本审计 C5 表 | 24 个 R 均为选摘，典型如 Table 3 从 8×10 截为 3×9，违反 R 基准“逐格一致、未给写 n/a”的合同。 | 将每个 R 对应表补成完整网格，或用稳定的行级 R 子 ID 覆盖全部行列；同步 `element_counts`、coverage_matrix 和 plan 引用。 |
| SA-A03 | C2 | major | `spec.md:92,95-100` 对照 `spec.md:675-729` | p65 的 IA.11 被关联到 R19（实际是 IA.17），p68-p73 的 IA.13–IA.16/图 IA.3–IA.4 被关联到 R20-R22（实际分别是 IA.18、IA.20B、IA.21），导致页面覆盖关系失真。 | 为 IA.11、IA.13–IA.16 建立正确 R/SA 关联或专门 R 条目，并把 R19-R22 保留给其真实附录表。 |
| SA-A04 | C6 | critical | `spec.md:392-397`；`report_text.md:532`（PDF p12） | B12 把 p12 的逐字摘录标到 p29、p35-p36；按所列页码无法找到该引用。 | 将 B12 页码补为 p12（可同时保留含 EW/VW 表头的结果页），并重新执行页码真实性抽查。 |
| SA-A05 | C6 | major | `spec.md:846-928`；`report_text.md:687,702,799,834,925,912,933` | 7 个 SA 结论引用的真实讨论位置在 p15-p20，但条目只列结果表/图页，引用本身真实、定位不完整。 | 在各 SA 的页码中加入真实讨论页，或将 `结论` 改为不带引号的审慎概括并单列“结论原文页码”。 |

## 审计结论

- 遗漏清单条目数：5（critical 3 / major 2 / minor 0）。
- C6 抽查命中率：16 / 17；覆盖 D/F/B/R/SA，R 类 5 条。
- 已检查维度:
  - C1：已独立重算 PDF 页数、主文/附录图表编号集合、fig_max/tbl_max、FIG/TBL 登记数；`no_findings`。
  - C2：已逐页扫描 p1-p104 并核页面覆盖表；发现附录 R 关联错位 1 条 major。
  - C3：已检查稳健性、参数、分组、子样本、市值、危机、附录、进一步等中英文触发词及 SA 映射；`no_findings`。
  - C4：已交叉核对 frontmatter、79 个标题块、79 个矩阵行和 plan 的 79 个唯一 milestone 映射；`no_findings`。
  - C5：已对 24 个 R 与 PDF 原表逐一独立核行列和已录数值；发现 tables_extracted 缺失与 R 网格截断 2 条 critical。
  - C6：已完成 17 条页码真实性抽查并扩查 SA 结论引用；发现 1 条 critical、1 条 major。

VERDICT: fail
