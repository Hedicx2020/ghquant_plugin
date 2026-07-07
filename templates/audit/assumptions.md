# 假设登记簿 assumptions.md 骨架

> 落盘于 `workspace/{report_id}/assumptions.md`；是 `/reproduce revise` 的操作对象——人工 review 时只能针对本文件的条目发起定向重跑，不能凭空提修改指令。
> 与 spec.md / ambiguities.md 用同一套 `### [前缀编号]` 标题块语法，前缀固定为 `AS`（Assumption）。

---

## 条目固定格式

```markdown
### [AS4] 换手率按多头组单边口径计算
- 来源: A3（auto 裁决）
- 假设内容: 换手率统计口径采用多头组单边换手（每期买入量/组内市值）
- 行业惯例依据: 同机构系列报告惯例，多头组单边口径为业内常见默认
- 影响面: output
- 影响 milestone: m1
- 影响指标: R1.Turnover（support 级），不影响 IC/Sharpe 核心结论
- 预期影响: 若口径错误，复现值约为研报 2 倍
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto
```

**字段取值说明**（写在示例块外，示例块本身保持干净、可直接复制）：
- `来源`：`A{n}（auto 裁决）` / `coder 主动简化` / `数据限制`。
- `影响面` ∈ `{data, method, param, trading, output}` → 驱动 revise 定向重跑范围，见下表。
- `状态` ∈ `{assumed, confirmed, revised}`：`assumed` = 已裁决登记，尚未经数据验证支持/证伪；`confirmed` = verify 后数据支持该假设；`revised` = 经人工 `/reproduce revise` 或迭代诊断认定假设有误，已切换为新口径（原条目保留存档，不删除，新口径另开新 ID 或在本条目追记）。
- `高亮等级`：仅 `major-auto`（在 final_report 强制高亮）有特殊含义，其余情形留空或写 `-`。

**「验证后回看」字段书写要求（门禁强依赖，务必遵守）**：登记时先写占位符 `[verify 后填]`（如示例，不加其它文字）；verify 阶段完成后**必须**整体替换为实际回看结论（如「复现 88.85% vs 研报 82.40%，偏差 7.8%，假设获数据支持」）。`tools/check_gates.py` G-FN-4 在进入 report 门禁前会全文搜索字面量 `[verify 后填]`，只要还有一条残留未替换，门禁直接 FAIL——**不允许带着占位符进入报告阶段**，也不允许在占位符后面续写内容（必须整体替换掉，否则字面量仍会被命中）。

---

## 影响面 → revise 重跑范围对照表

| 影响面 | 重跑范围 |
|--------|---------|
| data / method | 受影响 milestone 的 implement → codex 增量 code_audit → verify → result_audit → report |
| param / trading | implement（config 级）→ verify → result_audit（轻量）→ report |
| output | verify（重出图表/Excel）→ report |

`/reproduce revise <report_id> --assumption AS3 "改用后复权口径"` 触发时，planner 按本表查影响面定重跑范围，只重跑受影响链路，reporter 增量更新报告；revise 轮计入 `iteration.history`（`trigger=revise`）但**不占 max_iter**，单条内部收敛上限 3 轮。

---

## 高亮与 final_report 收录规则

- `高亮等级: major-auto` 的条目：final_report 的「A.2 假设清单与验证后回看」章节必须显著高亮列出，不得混在普通假设中一笔带过。
- 全部假设（不论等级）都要在 final_report 全量收录，并给每条 revise 指引（人工 review 时据此决定是否发起定向重跑）。
- assumptions.md 只增不删，`revised` 的旧假设保留存档（供事后追溯"当初为什么这样假设、后来为什么改了"）。
