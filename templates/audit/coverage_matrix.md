# 覆盖矩阵 coverage_matrix.md 骨架

> `quant-extractor` 在 `workspace/{report_id}/spec/coverage_matrix.md` 初始化本文件（每个 spec.md 要素一行），后续各阶段只改状态列、不删行。
> 与 spec.md 的要素 ID 体系一一对应；三方一致性（正文正则统计 == spec.md frontmatter `element_counts` 汇总 == 本表数据行数）由 `tools/check_gates.py` G-EX-4 机器核验。

---

## frontmatter（YAML，供人工/agent 快速核对行数，不参与门禁解析）

```yaml
---
report_name: <与 spec.md 一致>
spec_version: 1
row_count: <当前数据行数，随「只增不删」规则同步更新>
---
```

---

## 表头（11 列，列名逐字固定——`tools/check_gates.py` 按列名精确/模糊取值，改列名会导致门禁读不到数据）

| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F2 | F | 趋势动量因子MA_60 | p9 | core | m1 | pending |  |  |  | extract |

### 列说明

| 列 | 填写者 | 说明 |
|----|--------|------|
| 要素ID | extractor | 与 spec.md `### [ID]` 标题一致，D/F/B/R/SA + 数字（含 F3.1 子变体）；FIG/TBL/EX 不进本表（登记在 spec.md 第六节，不占要素守恒行） |
| 类别 | extractor | D / F / B / R / SA 单字母 |
| 描述(短) | extractor | ≤20 字摘要 |
| 页码 | extractor | 必填，PDF 物理页 |
| 优先级 | extractor 初判，spec_audit 可改 | `core`（进入研报核心结论）/ `support`（敏感性、辅助分析）/ `optional`（示意图等） |
| milestone | planner | 所有非 skipped/infeasible 行必填（G-PL-6）；对应 plan.md frontmatter 的 milestone id |
| 状态 | 各阶段 | `pending` / `in_progress` / `done` / `skipped` / `infeasible`，流转规则见下「状态机」 |
| 状态理由 | 改 skipped/infeasible 者 | 格式 `<理由码>: <一句话>`；理由码 ∈ `data_missing` / `method_underspecified` / `out_of_scope` / `cost_prohibitive` / `reference_only` |
| 实现位置 | coder | `src文件:函数`，真实存在（code_audit 核验非空壳）；done 行必填 |
| 验证结果 | verifier | `verify_report.md#锚点 偏差x% pass\|fail`；core/support 行必填（G-VF-7） |
| 最后更新 | 各阶段 | 写阶段名：extract / plan / implement / verify / iterate / result_audit / report |

---

## 状态机

```
pending → in_progress → done
pending / in_progress → skipped / infeasible   （须同时填「状态理由」列）
done → in_progress                             （仅迭代回退，变更日志须记触发意见 ID）
```

**禁止 `done → skipped`**（掩盖失败——已经做出来的东西不允许事后悄悄标为不做）。

---

## 要素守恒五规则（审计 agent 逐条执行，写死不可协商）

1. **只增不删**：任何 agent 不得删行；不需要做改状态并填理由，不是删行。行数只能因「审计补漏」增加，来源须登记进本文件尾「变更日志」节（如 `依据 CDX-S-02 追加`）。
2. **done 三件套**：改 `done` 必须同时填「实现位置」+「验证结果」，缺一门禁 FAIL（G-IM-5 / G-VF-7）。
3. **core 不许静默 skip**：`core` 级要改 `skipped`/`infeasible` 必须关联歧义（ambiguities.md）或假设登记（assumptions.md），并强制出现在 final_report「未复现清单」。
4. **合法流转**：见上「状态机」；禁止 `done → skipped`。
5. **终态检查**：进 report 阶段不允许存在 `pending`/`in_progress` 行（G-FN-3）。

---

## 变更日志（只追加，禁止修改/删除历史行）

| 时间 | 事件 | 来源 | 说明 |
| --- | --- | --- | --- |
| <YYYY-MM-DD extract> | 初始化 N 行 | quant-extractor | 首次提取建矩阵 |
| <YYYY-MM-DD spec_audit> | 追加 1 行 F13 | 依据 CDX-S-02 追加 | codex 盲提取发现遗漏因子 |
