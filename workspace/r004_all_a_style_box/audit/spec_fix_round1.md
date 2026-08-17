# Spec 定向修复记录（Round 1）

## 一、修复范围

- 输入审计：`audit/spec_audit_codex.md` 的 `CDX-S-01` 至 `CDX-S-04`，以及 `audit/extract_audit.md` 的 `SA-A01`、`SA-A02`。
- 本轮仅修复提取层产物：`spec/tables_extracted.md`、`spec/spec.md`、`spec/ambiguities.md`、`spec/spec_codex.md`，并新增本记录。
- 未修改 `state.json`、`plan.md`、`assumptions.md`、`spec/coverage_matrix.md` 或任何审计输入。
- 本轮未创建或修改 `spec/extract_diff.md` 与 `audit/audit_responses.md`；这两个文件在本轮开始检查时已经存在。
- 未新增中国全A设计，也未改写既有planner裁决。

## 二、审计意见与修复映射

| 审计ID | 问题 | 修复位置 | 处理结果 |
| --- | --- | --- | --- |
| SA-A01 | R2、R3、R7-R10整表未进入表格证据层 | `spec/tables_extracted.md` | 已逐表补齐表头、全部行列、数值/方向/空白格及PDF页码来源 |
| SA-A02 | R4-R6相关矩阵缺列头、行名与Value首行 | `spec/tables_extracted.md` | 已重建为完整6×6矩阵；加行名后每行7列，上三角空白统一记为`n/a` |
| CDX-S-01 | 市场风险状态目标与shadow-rate目标冲突未显式并列 | `spec/spec.md` 的F4、R2；`spec/ambiguities.md` 的A6 | 已并列抄录p4、p9、p15原文；A6仅强化证据，保留其既有裁决与状态 |
| CDX-S-02 | p5 Refinitiv与Exhibit FRED/Factset来源冲突未显式并列 | `spec/spec.md` 的D11-D14；`spec/ambiguities.md` 的A23 | 已保留两套来源陈述；新增A23为major/open，未选择或覆盖任一来源 |
| CDX-S-03 | Exhibit 1 daily return与p5 monthly performance标签频率冲突 | `spec/spec.md` 的F9；`spec/ambiguities.md` 的A24 | 已并列原文；新增A24为major/open，未推断聚合频率或标签步骤 |
| CDX-S-04 | p5样本截止March 2023与Exhibit 16横轴May-23冲突 | `spec/spec.md` 的B1、EX16；`spec/ambiguities.md` 的A25 | 已并列图文证据；新增A25为major/open，未推断May-23是否为有效观测 |

## 三、Codex盲提取片段

- 已从 `audit/spec_audit_codex.md` 原样截取 `=== SPEC_CODEX_BEGIN ===` 至 `=== SPEC_CODEX_END ===`（含首尾标记），写入 `spec/spec_codex.md`。
- 逐字比对通过：marker正文长度5313字符，目标文件仅在末尾保留一个换行。

## 四、自检结果

| 检查项 | 结果 |
| --- | --- |
| `spec.md` 要素独立重算 | D29 + F21 + B14 + R10 + SA4 = 78；ID无重复 |
| frontmatter计数 | D29 / F21 / B14 / R10 / SA4，与正文一致 |
| `coverage_matrix.md` | 78行；ID集合与spec正文一一对应；本轮未修改 |
| R1-R10证据层 | R1至R10连续、完整 |
| R4-R6矩阵形状 | 每张6个列名、6个行名；Value为首行；每行含行名共7列 |
| R2/R3/R7-R10整表 | 行数、列数、数值、方向与`n/a`空白规则检查通过 |
| 四组原文冲突 | 已在现有要素中并列登记；未在提取阶段新增裁决 |
| 新增歧义 | A23-A25均为major/open；A6保持major/resolved及既有裁决 |
| `spec_codex.md` | 与审计marker逐字一致 |
| 文本格式 | 针对本轮五个产物执行行尾空白扫描，无空白错误 |

## 五、边界声明

本记录只证明上述定向修复和结构自检已完成，不替代后续门禁判定，不修改任何状态或规划结论。
