# 提取完整性审计 extract_audit.md

> 案例：r001_signature_transformer_allocation（《Signature-Informed Transformer for Asset Allocation》, arXiv:2510.03129v3）
> 模式：mode=spec（提取忠实性对照审计）；难度 hard、tags=[ml]，G-SA-2 必跑。
> 审读分离：仅依据 PDF、report_text.md、tables_extracted.md、spec.md、coverage_matrix.md、ambiguities.md 独立核验，不采信任何 extractor/planner 自述。R 类数值以 PDF 原文为终审。

---

## C1–C6 逐项结论

### C1 图表编号连续性 —— pass
- 独立重算（全文正则搜 Figure N / Table N，无 Exhibit 体例）：
  - Figure 出现集合 = {1(p1), 2(p3), 3(p7), 4(p7), 5(p8), 6(p8), 7(p7 正文引用 + p21 图注)}，**独立重算 fig_max = 7**，连续无缺号。
  - Table 出现集合 = {1(p5), 2(p6), 3(p13), 4(p16), 5(p19), 6(p19), 7(p20)}，**独立重算 tbl_max = 7**，连续无缺号。
- spec front matter `exhibit_declared: {fig_max: 7, tbl_max: 7}` 与独立重算**完全一致**，无超出声明、无幽灵编号。
- spec 第六节 FIG/TBL 全集登记 FIG1–FIG7、TBL1–TBL7（共 14 条），与出现集合逐一对应，无未登记编号。
- 结论：图表编号连续性通过，声明值经独立重算证实。

### C2 逐页覆盖扫描 —— pass
- 逐页比对 spec「页面覆盖表」（p1–p21）与 report_text.md 各页实际内容，21 页全部有类型标注与要素关联。
- 含多百分数/公式的结果页（p5/p6/p19/p20 绩效表、p8 敏感性）均已关联 R/SA/TBL 要素；纯参考文献页 p9/p10、纯数学证明页 p14/p15 标注类型且无要素（合理排除）。
- 唯一宽松处：p1 行关联 D1（见遗漏清单 SA-A02，minor），D1 已在 p5 正确登记，不构成整页漏扫。
- 结论：无整页跳过，无「含数据页却无要素且无类型标注」的遗漏嫌疑。

### C3 触发词检查 —— pass
- 敏感性/稳健性：3.6 Sensitivity Analysis（p8）→ SA3/SA4 已登记；DOW30「validate performance against a different index composition」、CSI300「evaluate robustness across different market dynamics」（p5）→ R3/R4 已登记。
- 参数：超参网格 Table 4（p16）→ B2；通用训练超参 → B1。
- 分组/子样本：7 组 universe（30/40/50 S&P100、10/20 DOW30、50/100 CSI300）→ D1 + R1/R2/R3/R4 全覆盖。
- 附录：Appendix A–H 全部落位（A→F8/F2 相关工作、B→TBL3、C→F2/F5 证明、D→B1/B2、E→F7、F→B7、G→R2/R3/R4、H→FIG7）。
- 进一步/消融：module-drop ablation（p6 Table 2）→ SA1，四变体（w/o CVaR / Asset Attn / Financial Bias / Gate γ）全登记。
- 结论：全部触发词命中页均有要素关联，无「漏掉参数敏感性/消融」的遗漏。

### C4 计数交叉 —— pass
- 「three portfolios of 30,40,50 S&P100 + two 10,20 DOW30 + two 50,100 CSI300」= 7 组 → spec D1「7 组 universe」一致。
- 「Traditional baselines ... EWP/GMV/CVaR/HRP」= 4 + 「Across all eight forecasting models」= 8 → spec B5「4 传统 + 8 预测」一致（8 个逐一列全：Autoformer/DLinear/FEDformer/PatchTST/iTransformer/NSformer/TimesNet/RFormer）。
- 「four standard financial metrics」= Sharpe/Sortino/MDD/Final Wealth → spec B6 = 4 项一致。
- 「three pillars」(路径特征/签名注意力/决策对齐) → F1/F5/F8；「three components」信息集 (i)(ii)(iii) → D4；「three distinct information sources」嵌入 → F3；均无欠计。
- Table 4 五 Panel（A–E）→ B2 引用 Panel E 并注明 A–D。
- 结论：所有计数声明对应类别要素数 ≥ 声明数，无 fail 级欠计。

### C5 基准表完备 —— pass（R 类逐格经 PDF 终审）
- 说明：tables_extracted.md（pdfplumber）严重残缺，各绩效表**仅抓到 SIT(Ours) 单行**，无法用于行列完备判定；故 R 类改以 report_text.md 全表 + **PDF 原页 p5/p6/p19/p20 直读**做终审级逐格核对。
- R1（Table 1，p5）：Panel A 40 资产 + Panel B 50 资产，各 13 行 × 4 列，**逐格与 PDF 一致**（含 ± 标准差）。
- R2（Table 5，p19）：30 资产 13 行 × 4 列，逐格一致；FEDformer Wealth 原文即 "1.032"（非 1.0320）已忠实照抄并在备注说明。
- R3（Table 6，p19）：Panel A 10 资产 + Panel B 20 资产，各 13 行 × 4 列，逐格一致。
- R4（Table 7，p20）：Panel A 50 资产 + Panel B 100 资产，各 13 行 × 4 列，逐格一致；PatchTST(100 资产) MDD 标准差原文即异常值 "±0.5590" 已忠实照抄。
- SA1（Table 2，p6）：Panel A/B 各 5 行 × 4 列，逐格一致，**b/c 显著性上标位置全部正确**。
- 结论：无抄一半、无少行少列；R 类数值 100% 忠实（PDF 终审）。

### C6 幻觉引用抽查 —— pass（15/15 命中）
- 抽查 15 条覆盖 D/F/B/R/SA 五类别（R 类 3 条：R1/R3/R4），按 spec 登记页码回 report_text.md（并对 R 类回 PDF 原页）核对原文摘录，全部可定位、无幻觉。详见下方抽查记录表。

---

## 遗漏清单

| ID | 检查项 | 严重度 | 页码 | 描述 | 处置建议 |
| --- | --- | --- | --- | --- | --- |
| SA-A01 | C6/自检 | minor | spec.md:435（对应 p6） | 第八节自检叙述写「正文 3.2（p6）提及 SIT Sharpe 0.6717/0.8232」，其中 0.8232 实为 Sortino Ratio（p6 原文：「a Sharpe Ratio of 0.6717 and a Sortino Ratio of 0.8232」）。仅自检 prose 措辞将 Sortino 并入「Sharpe」标签，R1 元素本身数值与列标签正确。 | 自检句改为「Sharpe 0.6717 / Sortino 0.8232」，不影响 R1 |
| SA-A02 | C2 | minor | spec.md:43（页面覆盖表 p1 行） | 页面覆盖表 p1 行关联 D1，但 D1 规范定义页为 p5（Dataset 段），p1 仅摘要泛提「diverse equity universes」+ Figure1 示意 TSLA/NVDA/AAPL。属逐页扫描辅助表的前瞻性宽松关联；D1 已在 p5 行正确登记，非遗漏、非幻觉。 | 可将 p1 行 D1 降级为「(前瞻)」或移除，保留 p5 主登记即可 |
| SA-A03 | C5/SA | minor | spec.md:421,440 / report_text.md:589-608 | SA3/Figure5 热图在 report_text.md 文本层存在部分逐格数值（0.0/5.0/10.0 bps 三行，40 与 50 资产交错），spec 依 A10 声明「提取残缺不逐格转录」。经核实两 Panel 数字交错、无法可靠映射到 (τ,c) 单元，且实验模式数值豁免——属透明披露的判断，非隐藏遗漏。 | 维持现状；如需可补记 40 资产 0bps 峰值 τ=1.3≈0.672 作定性锚点 |

> 严重度：无 critical、无 major，3 条 minor（均为措辞/展示层，无任何数值失真、无缺号、无漏要素）。

---

## C6 抽查记录表（15 条，覆盖 D/F/B/R/SA；R 类 3 条）

| 抽样要素ID | 类别 | 页码 | spec.md 摘录原文（节选） | 回查结果 | 判定 |
| --- | --- | --- | --- | --- | --- |
| D1 | D | p5 | "Experiments used three portfolios of 30, 40, and 50 S&P 100 companies ... 50 and 100 assets from the CSI 300 index." | report_text.md p5(396-403) 逐字可定位 | match |
| D3 | D | p5 | "training set spans from January 1, 2000, to December 31, 2016 ... test set from January 1, 2020, to December 27, 2024." | report_text.md p5(406-409) 逐字一致 | match |
| F1 | F | p2,p16 | "SigM(X[s,t]) = (1, ∫dXu, ∫∫dXr⊗dXu, …)" / (Table4 Panel E) "Sig Level 2" | report_text.md p2(74-76) + p16(1191) 均可定位 | match |
| F5 | F | p3-4 | "Headk,h = softmax(Qk,h Kk,h^T/√dk + γBk,h)Vk,h" / "γ = softplus(γ̂)" | report_text.md p4(254-263) Eq14 + gate 定义一致 | match |
| F7 | F | p2,p4,p17 | "min_θ E[CVaRα({L^(k)}_{k=1}^K)]" / α∈(0,1) 数值未给 | report_text.md p2(146) Eq3、p4(295) Eq17；全文无 α 赋值，确认 | match |
| F8 | F | p4,p11 | "No auxiliary prediction losses are used. Eq.(17) is the sole training signal" | report_text.md p4(298-299) 逐字一致 | match |
| B1 | B | p16 | "Adam optimizer with a learning rate of 10−3, a batch size of 64, a dropout rate of 0.1 ... 100 epochs ... patience of 10" | report_text.md p16(1150-1152) 逐字一致 | match |
| B2 | B | p16 | "(Table4 Panel E, SIT) D MODELS 8,16,32,64；D FFS 8,16,32,64；E LAYERS 1,2；N HEADS 2,4,8；Sig Level 2；HIDDEN C 8,16,32" | report_text.md p16(1185-1192) + PDF p16 逐项一致 | match |
| B5 | B | p5 | 传统 4（EWP/GMV/CVaR/HRP）+ 预测 8（Autoformer…RFormer） | report_text.md p5(386-402) 全部可定位 | match |
| B7 | B | p18 | "(Stage2) minimize ζ + 1/((1−α)S)Σ(−(w^T r_s)−ζ)^+ subject to w^T r̂≥µtarget" | report_text.md p18(1315-1319) Eq55 一致 | match |
| R1 | R | p5 | SIT 40 资产 "0.6717±0.0628 / 0.8232±0.0792 / 0.3611±0.0037 / 1.7903±0.1023" | **PDF p5 直读逐格一致** | match |
| R3 | R | p19 | SIT 10 资产 DOW30 "1.0312±0.0671 / 1.3798±0.1049 / 0.2766±0.0413 / 2.8674±0.2263" | **PDF p19 直读逐格一致** | match |
| R4 | R | p20 | SIT 50 资产 CSI300 "1.9373±0.0091 / 2.3399±0.1711 / 0.0964±0.0046 / 1.2804±0.0105" | **PDF p20 直读逐格一致** | match |
| SA1 | SA | p6 | "(w/o CVaR) the Sharpe Ratio on the 40-asset universe falls from 0.6717 to 0.5691" | report_text.md p6(456-457) + PDF p6 Table2 一致 | match |
| SA2 | SA | p7 | "means of 0.540 for the 40-asset universe and 0.611 for the 50-asset universe" | report_text.md p7(548-549) 逐字一致 | match |

抽查命中率：**15 / 15 = 100%**（无 mismatch，无幻觉引用）。

---

## 专项焦点核查（本次任务指定）

- R 类逐格忠实性：R1/R2/R3/R4 四表全部经 PDF（p5/p19/p20）终审级逐格核对，**无一格正负号/小数位/百分号/量级不符**；原文瑕疵（"1.032"、"±0.5590"）均忠实照抄且加备注。SA1 消融含 b/c 显著性上标全部正确。
- 遗漏项核查：M=2 截断阶（F1）✓、CVaR 置信水平 α（F7 + A1）✓、签名增强注意力（F5）✓、7 组 universe 40/50/30 S&P100 + 10/20 DOW30 + 50/100 CSI300（D1）✓、基线 4 传统+8 预测（B5）✓、消融与敏感性 Table2/Fig3/Fig5/Fig6（SA1/SA2/SA3/SA4）✓，全部在 spec 登记，无缺项。
- 编号完整性：Figure 1–7、Table 1–7 全登记，独立重算 fig_max=tbl_max=7 与声明一致，无缺号/无超出。
- 歧义登记忠实性：A1（α 未给）、A2（H/K 未给）、A8（Table7 题注误写「10 and 20-asset from CSI300」）等经 PDF 核对均属实，非虚构。

---

## 审计结论

- 遗漏清单条目数：3（critical 0 / major 0 / minor 3）
- C6 抽查命中率：15 / 15（100%）
- 已检查维度：
  - C1 图表编号连续性 —— pass（独立重算 fig_max=7、tbl_max=7，与声明一致，无缺号无超出）
  - C2 逐页覆盖扫描 —— pass（21 页全覆盖，仅 p1→D1 宽松关联记 minor）
  - C3 触发词检查 —— pass（敏感性/稳健性/参数/分组/附录/消融命中页均有要素关联）
  - C4 计数交叉 —— pass（7 universe、4+8 基线、4 指标、three pillars 等均无欠计）
  - C5 基准表完备 —— pass（R1–R4 + SA1 逐格经 PDF 终审，无缺行缺列）
  - C6 幻觉引用抽查 —— pass（15/15 命中，含 R 类 3 条 PDF 直核）
- 总评：spec 三件套对研报原文高度忠实，全部核心数值经 PDF 终审无失真；仅 3 条 minor 措辞/展示层瑕疵，无 critical/major，不影响复现口径。

**verdict**: pass_with_issues
