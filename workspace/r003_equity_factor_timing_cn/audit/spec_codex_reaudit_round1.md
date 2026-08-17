# Spec Audit 第1轮缩减复审

复审范围仅限 `CDX-S-01`、`CDX-S-02`、`CDX-S-03`。证据来源限定为原PDF、更新后的 `spec/spec.md`、`spec/ambiguities.md` 与 `audit/spec_fix_round1.md`。

| 审计意见 | 结论 | 证据定位 | 复审说明 |
| --- | --- | --- | --- |
| CDX-S-01 | pass | 原PDF p15；`spec/spec.md:291-300`；`audit/spec_fix_round1.md:7` | PDF p15明确给出Stacking第二层Logistic Regression的交叉熵损失与最终sigmoid组合式。更新后的F4在第295行补录交叉熵公式，在第296行保留输出公式，并于第294行说明第二层LR学习三类基模型权重；与原文一致，原意见已关闭。 |
| CDX-S-02 | pass | 原PDF p14-p15，公式集中于p15；`spec/spec.md:317-325`；`audit/spec_fix_round1.md:8` | PDF p15依次给出单树特征重要性、树内归一化、随机森林汇总三层公式。更新后的F7第320-322行逐式补录三式，第323-324行补充符号与节点不纯度下降口径；公式结构、求和范围及跨树汇总关系与PDF一致，原意见已关闭。 |
| CDX-S-03 | pass | 原PDF p9、p15；`spec/spec.md:291-300`；`spec/spec.md:525-539`；`spec/ambiguities.md:53-61`；`audit/spec_fix_round1.md:9` | PDF p9确实写有“predicting significant shadow rate changes”，且p15特征重要性段落再次出现“predicting shadow rates”。更新后的F4与R2均逐字保留该冲突表述并双向关联A6；A6列出两种解释、裁决结果和依据，不再静默改写，原意见已关闭。 |

复审结论：三条定向修复均通过，未发现与这三条意见直接相关的新问题。

{
  "checkpoint": "spec_reaudit",
  "verdict": "pass",
  "findings": []
}
