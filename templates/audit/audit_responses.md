# 审计回应总表 audit_responses.md 骨架

> 落盘于 `workspace/{report_id}/audit/audit_responses.md`；收录三道异构外审（spec/code/result）全部意见的逐条回应。意见 ID 的 `CDX-` 前缀为历史稳定合同，不代表实际引擎；同一张表跨检查点累计追加。

---

## 表头（列名逐字固定；「处置」「复核」两列门禁按模糊匹配取值，含括注也能命中，但不要改列名本身）

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | major | Fig12 未登记 | accepted | 已补入 spec.md 图表登记清单第六节 | pass |
| CDX-C-01 | critical | strategy.py:42 存在未来函数（用了 T 日收盘价做 T 日信号） | accepted | 已改为 T-1 日收盘价，src/demo/strategy.py:42-45 | pass |
| CDX-R-01 | minor | 归因措辞可以更精确 | rejected | 现有措辞已给出量级推算，认为无需修改 | - |

**意见ID 格式要求**：必须匹配 `CDX-{S|C|R}-数字`（如 `CDX-S-01`），门禁靠此模式在行内任意单元格定位意见归属，格式走样会导致该行无法被正确计入对应审查点的回应计数。

---

## 协议规则

- **severity 判据总纲**：`critical` = 阻断；`major` = 必须回应；`minor` = 登记即可，计数进 final_report。
- **critical**：门禁 FAIL；必须修复并复审（复审输入 = 修复 diff + 原意见 + 定位文件，缩减 prompt 成本）；「复核」列未写 `pass` 视为未清零，不得推进下一 stage。
- **major**：必须逐条回应（处置=`accepted` 需给修复位置；处置=`rejected` 需给技术理由）；「处置」列为空视同 critical。
- **minor**：登记即可，不阻断门禁，计数进 final_report。
- **升级人工**：同一意见连续两轮 `rejected` 且 codex 复审仍坚持 → 升级人工裁决；同一审查点「审 → 修 → 复审」最多 3 轮，仍有 critical → `paused_blocked`。
- **accepted 的复核要求**：「复核」列必须最终写 `pass`（配合反虚报 K8——`accepted` 项必须对应文件 mtime 变化/diff 非空，由复核人核对后才可写 pass；无变更痕迹则该 coder 输出全部降信）。
- **rejected 的下游义务**：`rejected` 的意见ID自动汇入 final_report「遗留清单」——`tools/check_gates.py` G-FN-5 会核验本表中处置=`rejected` 的每个意见ID是否原样出现在 `final_report.md` 全文中，缺失即 FAIL。

---

## 行数门禁提示（三审查点共用同一契约）

`tools/check_gates.py` 要求回应行数恰好等于对应 `{point}_audit_external.md`（历史案例回退 `{point}_audit_codex.md`）解析出的 issues 数。一条外审意见对应一条回应行，不允许合并或省略。
