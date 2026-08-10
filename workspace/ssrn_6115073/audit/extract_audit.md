# 提取完整性审计 extract_audit.md（ssrn_6115073）

> 由 quant-auditor（mode=spec）产出。审读分离：只拿 PDF / report_text.md / tables_extracted.md / spec.md / coverage_matrix.md / ambiguities.md / plan.md，**不采信 extractor 自述**，图表编号、要素计数、三方数值一律独立重算。
> 页码约定：经交叉核验，spec.md 的「pN」= report_text.md 的 `===== PAGE N =====` 标记（= PDF 印刷页 N−2），全篇一致，C6 回查按此对齐。
> 审查边界：本文为 experimental 复现，原文用美股 S&P500/DJI + 日股 N225 + FRED 美国宏观；spec 忠实登记原文即合规，市场迁移/A股映射属 planner 职责，不在 spec_audit 范围（未因 spec 未写 A股而报遗漏）。SSRN 预印本每页左侧竖排水印碎片（iew/ed/ev/er/pe/ot/tn/rin/ep/Pr）已识别为版面噪声，未当作正文。

---

## C1–C6 检查项（操作规程 + 独立重算结论）

| 检查项 | 操作规程 | 独立重算结论 |
|--------|---------|-------------|
| C1 图表编号连续性 | 正文+附录逐页搜 Figure/Table 编号，独立重算 fig_max/tbl_max 与全集，对照 frontmatter exhibit_declared 及第六节登记清单 | **no_findings**。独立重算：图对象 18（正文 Figure 1–16 连续无跳缺 + 附录 Figure E.1@p47 + Figure G.1@p49），表对象 8（正文 Table 1–7 连续无跳缺 + 附录 Table A.1@p43）。spec frontmatter fig_max=18/tbl_max=8 与第六节 FIG1–18/TBL1–8 登记（附录 E.1/G.1/A.1 顺延 17/18/8，规则第六节已明示）完全吻合，无未登记编号、无幻觉图表 |
| C2 逐页覆盖扫描 | 对照 spec「页面覆盖表」逐页核对 50 页 | 基本 no_findings。50 页逐页均有内容类型+要素关联；含公式/百分数页均有要素挂钩。唯 F1 页码下界「p6」略宽（式1-4 实际落在 p8，p6 为文献综述），非遗漏非幻觉（三条引文均在 p8 命中），记 SA-A03（minor, confidence low） |
| C3 触发词检查 | 全文搜敏感性/稳健性/参数/分组/分年度/子样本/分市值/牛熊/附录/进一步 | **no_findings**。参数敏感性(Table7=SA3)、滚动分年度(Table3=SA1)、样本外(Table5=SA2)、单因子纳入/剔除(Figure15=SA4)、次相似进一步(Appendix G=SA5)、TDA(6.1=SA6)、附录 A–H 全部命中且已登记为 SA/B/D/F 要素；无漏登的敏感性/稳健性分析 |
| C4 计数交叉 | 摘要/正文/结论计数声明对照要素数 | **no_findings**。18→7 宏观因子(D2/F12)、11 方法(R1/B8 列全)、6 比率(R1 行全)、方法四步(F2→F11 全覆盖)；element_counts{D4,F12,B8,R5,SA6}=35 与 coverage_matrix row_count=35 自洽 |
| C5 基准表完备 | 每个 R/SA 数值表逐格对照 report_text.md/PDF 原表（tables_extracted.md 仅 pdfplumber 表骨架、无数值，不可用作数值源） | **2 条 findings**。R2(表1,32格)/R3(表4,33格)/R4(表6,21格)/SA2(表5,72格)/SA3(表7,60格) 逐格 100% 吻合；R1(表2,198格)194 格吻合、AStd/DowJones 基准 4 格错位(SA-A01,major)；SA1(表3)行列完整、洁净排版行逐格对得上、1 格 0.153 vs 0.154 微差(SA-A02,minor)。无少行/少列/抄一半 |
| C6 幻觉引用抽查 | 抽 17 条(D/F/B/R/SA 全类，R 类 4 条)回 report_text.md 对应页查原文 | **no_findings**。17/17 命中，无一条在所标页找不到近似文本，无幻觉引用（见下抽查表） |

---

## 遗漏 / 数值 findings 清单

| ID | 检查项 | 严重度 | 页码/定位 | 描述 | 处置建议 |
| --- | --- | --- | --- | --- | --- |
| SA-A01 | C5 | major | spec.md:268 vs report_text.md PAGE27(行1997-2035) | R1 表2「AStd·Dow Jones」行的 4 个基准列整体右移一列错位。PDF：Index=0.218, HRP=0.097, HERC=0.132, OLMAR=0.112, NCO=0.132；spec 抄成 Index=0.123, HRP=0.218, HERC=0.097, OLMAR=0.132, NCO=0.132（0.218/0.097/0.132 右移，Index 位误插 0.123，OLMAR 真值 0.112 丢失）。同表其余 194/198 格（含全部 CPMM-EW/MV 及 AStd·S&P500/AStd·Nikkei 基准列）均正确 | 订正该行 4 格为 0.218/0.097/0.132/0.112；因 experimental 模式数值对齐豁免，不影响下游复现目标，但应回填正确值保 spec 忠实性 |
| SA-A02 | C5 | minor | spec.md:405 vs report_text.md PAGE28(行2225) | SA1 表3「2016-2020·AStd·S&P500·EWMFM」spec=0.153，PDF=0.154，差 1 个末位。属 spec 自披露的 A25（表3 密集小字末位判读风险）范畴，support 级 | 复现自算不采信，或以 0.154 订正；不影响结论 |
| SA-A03 | C2 | minor(conf low) | spec.md:125 | F1 页码范围「p6-p8, p9」下界略宽：价格相对/组合/财富式1-4 实际全在 p8，p6 为 2.1 OLPS 文献综述。非遗漏非幻觉（F1 三条引文均在 p8 命中） | 可收窄为 p7-p9；不影响 C6 |

> 真实「遗漏」（未登记的因子/数据/回测设置/结果表/敏感性分析）：**无**。全部 7 表 16 图 + 附录 3 项、37 条正文公式 + 附录 B/C/D/F 公式、四步方法、11 方法、9 项绩效指标、5 项内部聚类指标、TDA/ES 均已登记。上列 3 条均为数值末位/页码范围/单格错位，非结构性遗漏。

---

## C6 抽查记录表（17 条，覆盖 D/F/B/R/SA，R 类 4 条）

| 抽样要素ID | 类别 | 页码 | spec.md 摘录原文（节选） | 回查 report_text.md 结果 | 判定 |
| --- | --- | --- | --- | --- | --- |
| D1 | D | p19 | "three stock indices: the S&P 500, Nikkei 225 (N225), and Dow Jones ... market data obtained from Refinitiv" | PAGE19 行1494-1498 原文一致 | match |
| D2 | D | p10-11 | "We study 18 macroeconomic variables ... selects seven features ... IR, UR, GDP, IP, DGDP, CPI, PPI" | PAGE10-11 行760-774 一致 | match |
| D4 | D | p48 | "σb is the standard deviation of the benchmark, which is S&P 500, Dow Jones, and Nikkei 225" | PAGE48 行4171-4172 一致 | match |
| F2 | F | p9-10 | "∆β = β+ − β−"；"stocks with the highest absolute values of ∆β can be identified" | PAGE10 行743-745 一致（式8） | match |
| F6 | F | p14-15 | "M = [min(D1),...,min(Dn−m+1)], with each min(Di) indicating the smallest Z-normalized Euclidean distance" | PAGE15 行1103-1104 一致 | match |
| F8 | F | p16-17 | "signali,j = {1 if r̂n+1,i,j|wi,j > 0; −1 if ...≤0}"（式27） | PAGE17 行1262-1265 一致 | match |
| F10 | F | p17-19 | "FSj = Σ γ̃i,j × signali,j"（式37）；"one asset with the highest value of FS from each cluster is picked" | PAGE19 行1465-1482 一致 | match |
| F12 | F | p30/p43-44 | "BorutaShap ... synergistically combines the Boruta algorithm with SHapley Additive exPlanations (SHAP)" | PAGE30 行2854-2855 一致；式B.1-B.3 在 PAGE43-44 | match |
| B2 | B | p19 | "collected on a daily basis, spanning from 1/1/1995 to 2/1/2023 ... 1/1/1995 to 31/12/2018 ... for training" | PAGE19 行1506-1508 一致 | match |
| B6 | B | p8 | "1. Market liquidity ... buy or sell any amount. 2. Market impact ... does not influence the market." | PAGE8 行599-603 一致 | match |
| R1 | R | p27 | "Table 2: Six different ratios for eleven approaches ... bold numbers show the highest value" | PAGE27 行1915-1921 标题一致；数值 194/198 一致（4 格见 SA-A01） | match |
| R3 | R | p29 | "in the proposed models with β− values of -0.3 and -0.2 ... maintain resilience during market downturns" | PAGE29 行2687-2688 一致；表4 33 格全一致 | match |
| R4 | R | p34 | "mean volatility spillovers from CPI to the S&P 500, Dow Jones, and Nikkei 225 are 102.5, 302.7, and 319.3" | PAGE34 行3046-3047 一致；表6 21 格全一致 | match |
| R5 | R | p24-25 | "CPMM-EW and CPMM-MV ... around 110% and 75%"；"CPM-EW and CPM-MV ... around 25% and 5%" | PAGE24 行1806-1807 / PAGE25 行1829-1830 一致 | match |
| SA3 | SA | p35-36 | "the number of clusters (nc), length of windows (w) ... lambda (λ), are assigned different values" | PAGE35 行3120-3121 一致；表7 60 格全一致 | match |
| SA4 | SA | p35 | "using only CPI and IR results in the highest Sharpe Ratios, approximately 0.5 and 0.41 ... excluding ... 0.9 and 1.1" | PAGE35 行3094-3099 一致（A24 矛盾表述系原文自身，spec 已如实录并标注） | match |
| SA5 | SA | p25/p49 | "Extended Similarity (ES) ... secondary similarity patterns still hold predictive power ... higher variability ... decreases the cumulative return" | PAGE25 行1872-1877 一致 | match |

C6 命中率：17 / 17 = 100%。

---

## 审计结论

- 遗漏 / 数值 findings 条目数：3（critical 0 / major 1 / minor 2）；其中真实结构性遗漏 0 条。
- C6 抽查命中率：17 / 17（100%），R 类 4 条（R1/R3/R4/R5）全部命中，无幻觉引用。
- 数值忠实度（独立逐格重算）：R2 32/32、R3 33/33、R4 21/21、SA2 72/72、SA3 60/60 全对；R1 194/198（AStd·DowJones 基准 4 格错位=SA-A01）；SA1 结构完整、洁净行逐格对得上、1 格末位微差=SA-A02。
- 已检查维度逐项结论：
  - C1 图表编号连续性：no_findings（独立重算图 18/表 8，与 exhibit_declared 及第六节登记完全一致，无跳缺无幻觉）
  - C2 逐页覆盖：基本 no_findings（50 页全覆盖；仅 F1 页码下界略宽 SA-A03 minor/low）
  - C3 触发词：no_findings（参数/稳健性/滚动/样本外/单因子/附录/次相似/TDA 全登记）
  - C4 计数交叉：no_findings（18→7、11 方法、6 比率、四步、行数 35 自洽）
  - C5 基准表完备：2 条 findings（SA-A01 major R1 四格错位、SA-A02 minor SA1 单格末位；无少行少列）
  - C6 幻觉引用：no_findings（17/17 命中）

整体判定：提取忠实度高（公式 1-37 及附录式、四步方法、11 方法、7 表 16 图 + 附录 3 项零遗漏，R2/R3/R4/SA2/SA3 逐格 100% 吻合，无幻觉引用）；唯 R1 主结果表存在 1 处 4 格基准列错位（major）+ 1 处 support 表末位微差（minor），需回填订正但不改变任何定性结论，且 experimental 模式已豁免数值对齐。据此判 pass_with_issues（非 fail：无幻觉、无结构遗漏、无缺行缺列；非 clean pass：核心 R1 表有真实 4 格数值错位）。

**verdict**: pass_with_issues
