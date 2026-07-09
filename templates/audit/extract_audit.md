# 提取完整性审计 extract_audit.md 骨架

> 落盘于 `workspace/{report_id}/audit/extract_audit.md`；由 `quant-auditor`（mode=spec）产出，medium/hard 难度必跑（easy 允许跳过，见 `tools/check_gates.py` G-SA-2）。
> **审读分离**：本审计只给 PDF、`report_text.md`、`spec.md`、`coverage_matrix.md` 四个文件路径，**不给 extractor 的完成汇报**——审计者不采信被审者自述，只对照原始材料独立核验。

---

## C1–C6 检查项（操作规程 + 遗漏判定信号）

| 检查项 | 操作规程 | 遗漏判定信号 |
|--------|---------|-------------|
| C1 图表编号连续性 | 全文正则搜「图N/表N/图表N/Exhibit N」，取最大编号与全部编号集合，对照 spec 第六节登记清单 | 出现过的编号未登记 → 每缺 1 号一条遗漏（含页码）；声明 `exhibit_declared` 与独立重算不一致 → fail |
| C2 逐页覆盖扫描 | 对照 spec「一、页面覆盖表」逐页核对 | 含 ≥3 个百分数或公式符号的页无要素关联且无类型标注 → 遗漏嫌疑 |
| C3 触发词检查 | 全文搜：敏感性、稳健性、参数、分组、分年度、子样本、分市值、牛熊、附录、进一步 | 命中页无 SA/F/R 关联且无排除说明 → 遗漏嫌疑（防「漏掉参数敏感性分析」的直接防线） |
| C4 计数交叉 | 摘要/引言/结论中的计数声明（如「我们测试了 12 个因子」「从四个角度改造」） | spec 对应类别要素数 < 声明数 → fail 级遗漏 |
| C5 基准表完备 | 每个 R 要素行列数与 `tables_extracted.md` 对应表比对 | 少行/少列（抄一半）→ fail |
| C6 幻觉引用抽查 | 随机抽 10 条要素（覆盖各类别），按页码回 `report_text.md` 查原文摘录（允许 OCR 级模糊匹配） | 摘录在该页找不到近似文本 → 幻觉引用，critical |

---

## 遗漏清单

| ID | 检查项 | 严重度 | 页码 | 描述 | 处置建议 |
| --- | --- | --- | --- | --- | --- |
| GAP-01 | C1 | major | p14 | 图14 出现在正文但未在图表登记清单登记 | 补入 spec.md 第六节，标复现意图 |

> 严重度取值统一用 `critical` / `major` / `minor`（与 codex 审查意见同一词表）：C1/C4/C5/C6 判定为「fail」信号的一律 `critical`；C2/C3 的「遗漏嫌疑」默认 `major`，经核实确属次要展示内容可降 `minor`。

---

## C6 抽查记录表（至少抽 10 条，覆盖 D/F/B/R/SA 各类别）

| 抽样要素ID | 类别 | 页码 | spec.md 摘录原文 | 回查 report_text.md 结果 | 判定 |
| --- | --- | --- | --- | --- | --- |
| R1 | R | p12 | "RankIC均值0.052……" | 该页原文核对一致（含 OCR 级模糊匹配） | match |

`判定` 取值：`match`（原文可定位，属实）/ `mismatch`（该页找不到近似文本，判幻觉引用 critical）。

---

## 审计结论

- 遗漏清单条目数：<N>（critical <n> / major <n> / minor <n>）
- C6 抽查命中率：<match 数> / <抽查总数>
- 已检查维度：C1 / C2 / C3 / C4 / C5 / C6（逐项列出结论，不得空泛写"整体没问题"）

**verdict**: pass | pass_with_issues | fail
