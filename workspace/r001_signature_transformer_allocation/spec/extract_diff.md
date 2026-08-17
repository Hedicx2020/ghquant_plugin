# extract_diff · spec_codex 盲提取 vs spec.md 差异裁决

> 主会话审计记账（非内容生产）。裁决照录审计结论：内审 `extract_audit.md`（auditor mode=spec）判 spec 高度忠实、无 major 遗漏（3 minor）；codex 阶段二盲提取 diff 提 13 条（12 major + 1 minor），均为 auditor 未覆盖项 → 按协议退取 codex 阶段二 diff 分析结论 + extractor 定向复核裁决。
> 来源：`spec_codex.md`（codex 阶段一盲提取）/ `spec_audit_codex.md`（codex 阶段二 finding）/ `extract_audit.md`（内审）。裁决落地位置见 `audit/audit_responses.md` 对应 CDX-S 行。

| ID | 类别 | 描述 | 页码 | 裁决 | 依据 |
| --- | --- | --- | --- | --- | --- |
| DIF-01 | 公式完整性 | F5 未转录 Theorem 2.2 完整适用条件（d≥2/‖qdyn‖>0/0<α<1）与方向导数式 Eq.12-13/34-43 | p4,p14-15 | dismissed | 依 spec_audit_codex 阶段二diff CDX-S-01 + extractor复核：F5 已含核心机制式（Logits=QK/√d+γB、β/qdyn/γ=softplus、Eq.8-16），证明条件属数学论证、不影响实现，实验模式豁免数值对齐 |
| DIF-02 | 公式完整性 | F7 未写显式经验 CVaR 式 ν+1/((1−α)K)Σ(L−ν)_+ | p4-5 | adopted | 依 CDX-S-02：F7 补录 Eq.20 经验式（对实现训练损失有直接价值） |
| DIF-03 | 数据要求遗漏 | 连续路径插值重建 + 实现收益向量 r_t 未登记 | p2 | adopted | 依 CDX-S-03：新增要素 D5（签名与组合损失的输入前置） |
| DIF-04 | 因子定义完整性 | F2 未转录严格 lead-lag 条件（Def C.1）与 Eq.22-33 证明链 | p12-14 | dismissed | 依 CDX-S-04 + 复核：signed-area 关键式 Eq.21 + Prop 2.1 结论已在 F2，证明链不影响 M=2 签名实现 |
| DIF-05 | 回测设置遗漏 | B2 未转录基线 Table4 Panel A-D 网格 | p16 | dismissed | 依 CDX-S-05 + 复核：基线已按 AS15 缩减为 4 传统 + 1 DLinear，深度基线网格对本次复现无用；SIT Panel E 网格已在 B2 |
| DIF-06 | 敏感性数值/事实纠错 | SA3 谎称 Figure5「文本提取残缺无法逐格转录」，实为 report_text p8 含全部 42 格 | p8 | corrected | 依 CDX-S-06：report_text p8 确含 42 格 (τ,c) mean±std，SA3 + 第八节自检 + ambiguities A10 已如实更正 |
| DIF-07 | 敏感性方法遗漏 | SA2 缺复现 Figure3 所需 s_t,j / a_t,j 定义式 | p7 | adopted | 依 CDX-S-07：SA2 补两定义式 |
| DIF-08 | 结果图错误关联/事实纠错 | FIG4 误标「数值同 Table1 各预测基线」 | p7 | corrected | 依 CDX-S-08：Fig4 为各 backbone 的 DFL vs MSE/PFL 柱对、Table1 无此两组柱值，第六节备注已纠正 |
| DIF-09 | 敏感性遗漏 | FIG7 缺 p7 高γ 聚集于高波动期定性结论 | p7,21 | dismissed | 依 CDX-S-09 + 复核：FIG7 为诊断图（p21，reference_only），定性观察非可复现数值，本案不复现 Fig7 |
| DIF-10 | 局限遗漏 | F1 缺签名维数灾难/截断偏差/kernel 二次成本 | p12 | dismissed | 依 CDX-S-10 + 复核：方法讨论不影响 M=2 固定阶实现，final_report 局限节可提 |
| DIF-11 | 敏感性参数遗漏 | SA4 缺 Figure6 可见 τ 轴范围 0.50-2.00 | p8 | adopted | 依 CDX-S-11：SA4 补 τ∈{0.50,0.75,1.00,1.25,1.50,1.75,2.00} |
| DIF-12 | 理论证明遗漏 | F7 缺附录 E Eq.44-53 CVaR 占优性证明 | p17-18 | dismissed | 依 CDX-S-12 + 复核：纯理论证明，不影响 CVaR 训练目标实现（目标式已在 F7） |
| DIF-13 | reference_only 缺漏 | TBL3 记号表符号/维度未转录 | p13 | dismissed | 依 CDX-S-13（minor）+ 复核：记号维度散见于 D/F/B 各要素，单独 notation 表非复现必需 |

## 汇总
- 采纳（adopted，spec 已补录）：DIF-02/03/07/11（4 条）
- 更正（corrected，事实纠错）：DIF-06/08（2 条）
- 驳回（dismissed，不影响本次复现/纯证明/已缩减）：DIF-01/04/05/09/10/12/13（7 条）
- 采纳/更正合计 6 条已落地 spec，三方一致复验 G-EX-4 = PASS（29/29/29）
