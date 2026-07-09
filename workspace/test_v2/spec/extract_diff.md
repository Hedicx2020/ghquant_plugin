# 盲提取交叉 diff 裁决（spec_codex.md vs spec.md）

> 记账来源：codex spec_audit 阶段二 diff（spec_audit_codex.md）+ 内审 extract_audit.md。
> 裁决列照录审计结论，主会话只登记与路由（编排记账，非内容生产）。

| ID | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |
|----|------|------|------|----------------------------------|------|
| DIF-01 | B类回测设置 | B1 将隔日反转系列（表7-13）整体登记为 2015-03-24 起，但表7/图14 原文区间为 2015-03-20 起（2015-03-24 仅适用图9/表1及表8-13） | p11-p12 | adopted | 依据 spec_audit_codex.md 阶段二diff（CDX-S-01，major）；extract_audit.md C1-C6 无相佐异议；已派 quant-extractor 定向修复 spec.md B1 |

## 覆盖说明

- codex 盲提取清单（spec/spec_codex.md）共 36 条；阶段二 diff 仅产出上述 1 条差异，其余条目与 spec.md 一致（维度记录：盲提取diff→CDX-S-01；遗漏检查/R表逐格核对/编号完整性独立重算/页码真实性抽查 均 no_findings）。
- 内审 extract_audit.md：C1-C6 全 PASS，15 条幻觉引用抽查零命中，verdict: pass，无独立遗漏项。
