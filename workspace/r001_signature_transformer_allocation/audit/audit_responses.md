# audit_responses · spec_audit 审查意见逐条处置

> 主会话审计记账（非内容生产）。codex 盲提取外审 13 条（CDX-S-01..13）逐条录入并处置；内审 auditor mode=spec 的 3 条 minor（SA-A01..03）一并处置。修复类回应给 spec 修复位置，驳回类给技术理由，复核列记结果。
> 外审引擎：codex-cli 0.144.1（异构交叉验证，engine=codex）。spec 修复由 quant-extractor 定向复核落地，G-EX-4 三方一致复验 PASS（29/29/29）。

## 一、codex 外审意见（CDX-S-，共 13 条）

| 意见ID | severity | 摘要 | 处置 | 回应（修复位置 或 技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | major | F5 未转录 Theorem 2.2 完整条件（d≥2 等）与方向导数式 Eq.12-13/34-43 | deferred | F5 已登记核心机制式 Logits=QK/√d+γB、b=⟨qdyn,β⟩、β=MLPβ、qdyn=MLPq、γ=softplus(γ̂)（Eq.8-16）；Theorem 2.2 证明条件属数学论证、不影响实现，实验模式豁免原文数值对齐 | pass |
| CDX-S-02 | major | F7 未写显式经验 CVaR 式 | accepted | spec.md F7 补录 ν_i+[1/((1−α)K)]Σ(L_i^(k)−ν_i)_+、N 场景平均、ν_i 为场景内经验 α-分位（Eq.20，p4-5） | pass |
| CDX-S-03 | major | 连续路径插值 + 实现收益向量未登记 | accepted | spec.md 新增要素 D5（连续路径重建 + 实现收益 r_t），关联 F1/F2/F7/B6；element_counts D 4→5、coverage_matrix D5→m2 | pass |
| CDX-S-04 | major | F2 未转录严格 lead-lag 条件与 Eq.22-33 证明链 | rejected | signed-area 关键式 Eq.21 + Proposition 2.1 结论已在 F2；Def C.1/Eq.22-33 证明链不影响 M=2 签名实现 | pass |
| CDX-S-05 | major | B2 未转录基线 Table4 Panel A-D 网格 | rejected | 基线按 AS15 缩减为 4 传统 + 1 DLinear，深度基线网格对本次复现无用；SIT Panel E 网格已在 B2 | pass |
| CDX-S-06 | major | SA3 谎称 Figure5 无法逐格转录（实为 report_text p8 含全部 42 格） | accepted | spec.md SA3 + 第八节自检删除不实「文本提取残缺/无法逐格转录」措辞、如实登记 42 格 p8 可得（实验模式自算 τ×c 网格）；ambiguities A10 同步更正 | pass |
| CDX-S-07 | major | SA2 缺复现 Figure3 所需 s_t,j / a_t,j 定义式 | accepted | spec.md SA2 补 s_t,j=[1/(HN_H d)]ΣΣΣ(B_k,h)_m,j 与 a_t,j 入向注意力份额两定义式 | pass |
| CDX-S-08 | major | FIG4 误标「数值同 Table1 各预测基线」 | accepted | spec.md 第六节 FIG4 备注纠正为「各预测 backbone 的 DFL vs MSE/PFL 柱对，柱值原文仅图形呈现、非 Table1 数值」 | pass |
| CDX-S-09 | major | FIG7 缺高γ 聚集于高波动期定性结论 | deferred | FIG7 为诊断图（p21，reference_only），高γ-波动期为定性观察、非可复现数值，本案不复现 Fig7 | pass |
| CDX-S-10 | major | F1 缺签名维数灾难/截断偏差/kernel 成本 | deferred | 签名方法局限为讨论性内容，不影响 M=2 固定阶实现；final_report 局限节将提示 | pass |
| CDX-S-11 | major | SA4 缺 Figure6 可见 τ 轴范围 0.50-2.00 | accepted | spec.md SA4 补 τ∈{0.50,0.75,1.00,1.25,1.50,1.75,2.00}（与 Fig5 τ∈0.8-1.4 网格不同） | pass |
| CDX-S-12 | major | F7 缺附录 E Eq.44-53 CVaR 占优性证明 | rejected | CVaR 占优性纯理论证明，不影响 CVaR 训练目标实现（目标式已在 F7） | pass |
| CDX-S-13 | minor | TBL3 记号表符号/维度未转录 | deferred | 记号维度散见于 D/F/B 各要素，单独 notation 表非复现必需 | pass |

小计：accepted 5（CDX-S-02/03/06/07/08/11 中 spec 补录类）+ deferred 4（01/09/10/13）+ rejected 3（04/05/12）。**无 critical；12 major 全部有回应（accepted/rejected/deferred）**；6 条涉 spec 修复全部落地并三方一致复验通过。

> 注（处置口径）：accepted=已补录 spec；deferred=证明/局限/minor 类，实验模式非阻断、不改本次实现，如实驳回入档；rejected=纯证明或已缩减项对本案无用。所有 major 均给具体技术理由，非「总体没问题」式含糊回应。

## 二、内审 auditor(mode=spec) 意见（SA-A，3 条 minor）

| 意见ID | severity | 摘要 | 处置 | 回应 | 复核 |
| --- | --- | --- | --- | --- | --- |
| SA-A01 | minor | 第八节自检把 Sortino 0.8232 并入「SIT Sharpe」标签 | deferred | R1 要素本身数值与列标签正确（Sharpe 0.6717 / Sortino 0.8232 分列）；仅自检 prose 措辞，不影响实现，非阻断 | pass |
| SA-A02 | minor | 页面覆盖表 p1 行关联 D1（D1 规范页 p5） | rejected | p1 摘要泛提 universe + Figure1 示意 ticker 属前瞻性宽松关联，D1 已在 p5 正确登记，非遗漏 | pass |
| SA-A03 | minor | SA3/Figure5 逐格未转录（A10） | accepted | 与 CDX-S-06 同源，已随 CDX-S-06 更正为「report_text p8 可得、实验模式自算网格」 | pass |

## 三、闭环声明
- critical：0（内审 + 外审均无）。
- major：12（全 codex）——全部逐条回应，无 open。
- minor：codex 1 + 内审 3 = 4——全部处置。
- spec 修复项（6 条）全部落地，`check_gates extract` G-EX-4 三方一致 = PASS（正则=29 / frontmatter=29 / 矩阵=29）。

## 四、code_audit codex 外审意见（CDX-C-，8 条：初审 2 critical + 6 major，经 3 轮 audit→修→复审全部 resolved）

| 意见ID | severity | 摘要 | 处置 | 回应（修复位置 或 技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-C-01 | critical | 标签取未来 K=12 期未按 split 边界 purge → 验证/测试期泄漏、test 未封存 | accepted | 源头硬闭：signatures.py `realized_forward_returns` 与 main.py `build_supervised_set` 的 split_end 改必填、None/NaT→ValueError（关键路径零 assert，防 -O 移除）；run_pipeline/strategy.fit/ablation 全入口传界 purge；实测 val 36→24、标签终点 2019-12-31<test_start；主会话 -O 优化模式实测传 None→ValueError 双证闭环 | pass |
| CDX-C-02 | critical | R4 原文绩效值硬编码在 main.py 计算路径（K1） | accepted | R4 锚移到 benchmarks.py（reference-only 原文研报值），main.py 仅 import 作对照/偏差列、复现结果全实测；codex 复审确认 R4 字面量仅存 benchmarks.py | pass |
| CDX-C-03 | major | 持有期 ST/停牌未点时屏蔽 | accepted | backtest.py `tradable_mask_at` 点时查 ST/停牌表（非仅 price.notna）；codex 复审 resolved | pass |
| CDX-C-04 | major | min_cvar 求解失败静默退等权把基线伪装成 EW | accepted | baselines.py warn+log+显式 fallback，main.py 全基线（含 DLinear）传 log_fn=log 透传至失败点；codex 复审 resolved | pass |
| CDX-C-05 | major | test 回测缩水 58 期（2020-02~2024-11）vs 声明 60 期 | accepted | 抽共享 helper（预热 2019-12-31 + 终端 test_end），run_pipeline/strategy/ablation 统一 60 期（首 2020-01-23 末 2024-12-27），ValueError 硬断言 n_periods==60+首末日 | pass |
| CDX-C-06 | major | τ 未按 AS6 验证选优（固定 sit_tau=1.0） | accepted | main.py `select_tau` 验证集选优 + 写回 cfg + 最终多种子训练/测试权重一致用；codex 复审 resolved | pass |
| CDX-C-07 | major | 种子按 best-val 择单点非 AS5 mean±std；DLinear 仅 seed 0 | accepted | SIT + DLinear 均按 cfg.seeds 多种子独立回测 + `_aggregate_metrics` 出 mean±std；codex 复审 resolved | pass |
| CDX-C-08 | major | MDD 漏计期初回撤（peak 未含初始财富 1） | accepted | common/utils.py `calculate_max_drawdown` 用 `cummax().clip(lower=1.0)` 含期初财富；合成断言 [0.9,0.9]→0.10、向后兼容全库；codex 复审 resolved | pass |

## 五、code_audit 闭环声明
- codex 初审 verdict=fail（2 critical + 6 major）——这正是 code_audit 拦截内审（impl_audit 多 pass）漏掉的真问题的价值。
- 经 3 轮 audit→修→复审：**2 critical 全闭环**（C-01 边界泄漏经主会话 -O 优化模式实测「split_end 必填 + None→ValueError + 关键路径零可移除 assert」双证，C-02 硬编码 codex 复审确认 R4 字面量仅存 benchmarks.py）；**6 major 全部 accepted/fixed，无 open**。
- 内审 impl_audit m1-m5 五份齐全、无 `判定: not_found` 空壳。
- 修复过程中多次子 agent API 掉线/回显损坏，均经主会话独立 -O 测试/冒烟重跑核验落地，未凭自述放行。

## 六、result_audit codex 反虚报外审意见（CDX-R-，5 条：初审 3 critical + 1 major + 1 minor，经 2 轮修复全 resolved）

> reproduction_mode=experimental（数值豁免）。codex 反虚报 + 内审 auditor(result) 双通道。**E4 三方一致（comparison.json↔metrics.json↔backtest_summary.xlsx↔日志逐位）确认核心数值真实非编造**；本组意见全属文档/范围诚实性（非数字造假），已据实修正。

| 意见ID | severity | 摘要 | 处置 | 回应（修复位置 或 技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-R-01 | critical | SIT 名次误写「第4」（实为第3）；AS15 把 SIT Sharpe 误写 0.7306 | accepted | verify_report/comparison/assumptions 全处「第4」改「第3」（GMV>CVaR>SIT>DLinear>HRP>EW）；AS15 SIT 0.7306→0.7348（0.7306 系 DLinear 真值保留）；主会话 grep 验证 SIT『第4』残留=0 | pass |
| CDX-R-02 | critical | verify_report 主表停留冒烟值 SIT 0.3836；evidence 谎称 xlsx 7 sheet 含 SA1 表 | accepted | verify_report 主表/结论整体重写为全档实测（SIT 0.7348±0.2659 等，删「等待 final verify」）；evidence 改实际 2 sheet（主绩效表/净值序列），SA1-4 数据在 metrics.json/日志；grep 验证冒烟 0.3836 残留=0、7 sheet 残留=0 | pass |
| CDX-R-03 | critical | 矩阵将 R1/R2/R3/R4-PanelB 标 done 但仅实跑 R4-PanelA CSI300-50（漏对比项） | accepted | comparison.json 补 4 项 scoped_out（R1-40/R2-30/R3-10·20/R4-B-100，理由 AS16 算力缩减非 data_missing）；coverage_matrix 状态列 R2/R3=scoped-out、R1/R4=partial（仅 R4-A CSI300-50 真 done），R1 注明迁移归并入 R4-A | pass |
| CDX-R-04 | major | AS27 预期四组件全退化，实测仅 CVaR/资产注意力两核心支持；细组件被归因「噪声/欠训练」无据 | accepted | AS27 验证后回看标「部分支持」；metrics.json/verify_report/comparison 细组件（Financial Bias/Gate γ）改「无可测贡献·原因未定（单种子点估计，无配对多种子误差区间，不归因噪声/欠训练）」；grep 验证旧归因残留=0 | pass |
| CDX-R-05 | minor | 净值 sheet/NAV 图用单种子代表路径（1.7546）未标 seed=0，主表为聚合（1.6014） | accepted | verify_report + evidence_manifest 标注净值序列/portfolio_nav 为 seed=0 单种子代表路径；xlsx/PNG 本身不重导出（deferred-minor，外围文档已明示口径差异） | pass |

## 七、result_audit 闭环声明
- codex 反虚报初审 verdict=fail（3 critical + 1 major + 1 minor）——反虚报防线抓出**文档与范围诚实性**问题（数字本身经 E4 三方一致证真实，无编造/无夸大结论）。
- 内审 auditor(result) verdict=pass_with_issues（0 critical / 2 major，与 codex 重叠），确认结论措辞未夸大、SA1 消融方向属实、扰动测试触发已记录。
- 经 2 轮 audit→修→复审：3 critical + 1 major 全 resolved（主会话 grep 逐处定证），1 minor deferred（外围已标注）。**无 open critical/major**。
- 关键诚实结论固化：**verdict=pass 是「验证达标/管线可信」，非「SIT 在 A股优越」**；SIT Sharpe 0.7348 居第3、GMV/CVaR 反超；SA1 仅 CVaR 目标 + 资产注意力两核心机制在 A股有贡献，Financial Bias/Gate γ 无可测贡献；复现范围为 CSI300-50（R4-A），其余 universe 按 AS16 scoped-out。
