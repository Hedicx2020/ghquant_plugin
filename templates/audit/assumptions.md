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
- `参数绑定`（可选）：纯参数型假设（落地为 `src/{id}/config.py` dataclass 字段单行字面量者）登记目标字段名，如 `- 参数绑定: cost_bps`。仅「值是类体单行字面量」的字段可绑；`field(default_factory=...)`、跨行字面量、运行期开关（代码内开关而非 config 字段）不可绑，此类条目不要填本字段。plan 阶段可预填意向字段名，implement 阶段由 coder 校正为定名后的真实字段名。本字段是 Excel 批量 revise 参数直改通道的机器入口（见下节），注释里的 AS 锚定照旧保留供人读。

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

## Excel 批量 revise 工作流

单条 revise 之外，review 阶段支持 Excel 批量修改（客户自助，免逐条走对话流程）：

1. **导出**：report 阶段收尾自动跑 `tools/assumptions_xlsx.py export <id>` 生成 `workspace/<id>/assumptions.xlsx`（全部假设 + 只读信息列 + 黄底可编辑三列：`新值` / `新口径（文本说明）` / `操作`）；`/reproduce export-assumptions <id>` 可随时重新导出干净表。
2. **填写**：有 `参数绑定` 的行在「新值」列直接填新值（参数直改通道，工具注入 config.py，不经过 agent）；无绑定或改口径叙述的行填「新口径」列（文本通道，planner/coder 落实走完整审计链）；两列可同填；「操作」列必须选 `revise` 才生效。
3. **提交**：`/reproduce revise <id> --from-excel`（合并重跑，默认）或 `--each`（逐条独立重跑产敏感性对比表，仅支持纯参数行）。主会话先 `apply --dry-run` 向用户复述计划再落地。
4. **追记格式**（参数直改由工具确定性写入，文本通道由 planner 同款补写）：`状态` → `revised`、`验证后回看` 重置为占位符 `[verify 后填]`（由重跑的 verify 重新回填），并在回看行前插入：
   `- 修订记录: <ISO时间> 批量 Excel revise（批次 <batch_id>）：<field> <旧值> → <新值>；工具直接注入 config.py，未经过 agent`
   （文本通道条目把末句改为「人工 revise 新口径」；一条目可累积多条修订记录行。）
5. **存档语义重申**：登记簿只增不删，revised 条目的原口径保留在条目内（`假设内容` 原文不动，修改历史体现在修订记录行）；文本通道若口径变化大到应另立条目，由 planner 判断另开新 ID。

---

## 高亮与 final_report 收录规则

- `高亮等级: major-auto` 的条目：final_report 的「A.2 假设清单与验证后回看」章节必须显著高亮列出，不得混在普通假设中一笔带过。
- 全部假设（不论等级）都要在 final_report 全量收录，并给每条 revise 指引（人工 review 时据此决定是否发起定向重跑）。
- assumptions.md 只增不删，`revised` 的旧假设保留存档（供事后追溯"当初为什么这样假设、后来为什么改了"）。
