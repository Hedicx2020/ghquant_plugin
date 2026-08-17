# 反虚报复核（result_audit）· r001_signature_transformer_allocation

> quant-auditor mode=result 独立复核。只拿产物文件、不采信任何自述；三方数值一律亲自重算。
> reproduction_mode=experimental（市场迁移·数值豁免）：R4 锚偏差不作问题。审查「结论有没有编」。
> 因子 agent Edit 现有文件常不持久，本节 Write 至独立文件（evidence_manifest.md 追加失败时的授权兜底路径）。

---

## 一、E4 三方数值一致（独立重算）

抽 SIT / CVaR / GMV / DLinear / SA1 核心值，逐位比对 metrics.json ↔ backtest_summary.xlsx ↔ verify_main/ablation 源日志（`.claude/jobs/06a52d7e/tmp/*.log`，本次亲自打开）：

| 指标 | metrics.json | xlsx 主绩效表 | 源日志 | 结论 |
|------|------|------|------|------|
| SIT Sharpe/Sortino/MDD/Wealth | 0.7348/1.1879/0.1412/1.6014 | 0.734784/1.187893/0.141235/1.601368 | 0.7348/1.1879/0.1412/1.6014 | 三方逐位一致 |
| CVaR Sharpe | 0.8302 | 0.830201 | 0.8302 | 一致 |
| GMV Sharpe | 0.9401 | 0.940075 | 0.9401 | 一致 |
| DLinear Sharpe | 0.7306 | 0.730579 | 0.7306 | 一致 |
| SA1 SIT(Ours)/w-o CVaR | 0.8713 / -0.2216 | 不在 xlsx | 0.8713 / -0.2216 | metrics↔日志一致；xlsx 缺（见 RA-A01）|
| SA2 Pearson n/均值 | 59 / 0.0553 | 不在 xlsx | 59 / 0.0553 | metrics↔日志一致 |

- 主绩效表 24 项（6 模型×4 指标）metrics.json 与 xlsx 逐位一致（四位小数），并与源日志 `[SIT聚合]/[DLinear聚合]/Model表` 逐位一致，源日志 `EXIT_CODE: 0`。**主表 E4 真三方一致成立，数值非编造。**
- SA1 ΔSharpe 独立复算：w/o CVaR −1.0929、w/o AssetAttn −0.2898、w/o FinBias +0.0048、w/o Gate +0.0067，与 metrics/comparison/日志四处全一致。
- R4 锚 SIT 1.9373/0.0964/1.2804 与 xlsx `R4_*` 列一致；偏差 62.1% 已如实登记（experimental 豁免，不列问题）。

## 二、K2 触发条件判断（硬编码/过精嫌疑）

- comparison.json 24 项 rel_dev 跨度 0.0012~0.7520，**并非全部 <0.5%**，K2「全指标同时过精」**未触发**。
- 唯一近乎精确项：cvar_sharpe 报 0.8292 vs 复 0.8302（rel_dev 0.12%）。experimental 数值豁免弱化此项；且扰动测试已独立证输入-输出强耦合，判为巧合近似、非硬编码。不构成问题。

## 三、K3 扰动测试触发判断（hard 必做一次）

- evidence_manifest「扰动测试记录」+ run_log 运行3/4 + metrics.json.perturbation_test 三处一致记录：smoke 档 --top-n 20 vs 30，SIT Sharpe 0.4123→0.3151，相对变化 23.6% ≫ 0.1% 阈值，exit=0。
- hard 必做扰动**已触发、已记录、结论无硬编码**。K3 满足。
- 旁证 SA1 w/o CVaR 使 Sharpe 0.8713→−0.2216 亦证输出强耦合于训练目标。

## 四、skip/infeasible 理由核实（对 data_catalog）

- R1/R2/R3（40/30/10/20 资产 universe）完整档未跑，理由=AS16「算力缩减」，**非 data_missing**。catalog 中 `ashare_index_components.parquet`（CSI300=000300）可 derive 任意 top-N，数据本可得——被审者未谎称 data_missing，如实标为算力缩减。无违规。
- coverage_matrix R2/R3 状态 done 但 verify 列明写「完整档未跑/未覆盖」，披露透明（属完整性问题，非虚报，交 result_audit 裁达标）。
- comparison.json 各指标无 `verification_level` 字段，「核验分级合理性核查」N/A（无降级项可核）。

## 五、结论措辞是否夸大 / SA1 方向陈述是否属实

- **未夸大**：comparison.json qualitative `sit_dominates_baselines` pass=**false**，明写「SIT Sharpe 0.7348…GMV 0.9401、CVaR 0.8302 反超 SIT…未取得统治性优势」；overall_pass=true 明确限定为「验证层门禁（产出完整+可信）」，达标/评级显式让渡 result_audit/diagnoser，**未把迁移结果说成「原文复现成功/SIT 优越成立」**。assumptions AS12-16/AS26 反复承认 SIT 未碾压、DFL-vs-PFL 未显现、归因留 diagnoser。
- **SA1 方向属实**：两核心组件（CVaR ΔSharpe−1.09、资产注意力−0.29）有贡献、两细组件（Financial Bias +0.005、Gate γ +0.007）无可测贡献，与实测/日志完全一致；comparison.json `sa1_fine_components_contribute` pass=**false** 公开标注细组件无贡献，**无选择性粉饰**。
- market-transplant 用法（AS11 前复权价、AS12 CSI300 universe、AS13 起点 2007、AS19 死票 0 占位）在 assumptions 均带 `性质: market-transplant` 登记，与产物用法一致。

## 六、5 张 PNG 亲查（Read 实际查看）

- portfolio_nav.png：6 条曲线=6 模型，尾值 SIT≈1.75/GMV≈1.74/CVaR≈1.60/DLinear≈1.57/HRP≈1.49/EW≈1.32，与净值序列吻合。
- drawdown.png：SIT/EW 2 条，SIT 触底≈−0.157（=单种子 MDD 0.1574）。
- rolling_volatility.png：SIT 单条，0.02~0.25 合理。
- asset_contribution.png：top15 真实 A股代码（600900/600519/600377/601988…），集中度符 SIT 蓝筹集中。
- weight_evolution.png：堆叠面积填满至 1.0，印证行和恒=1、平滑演化。
- 全部真实、曲线数=分组数、坐标域与 metrics 吻合，无占位/伪造迹象。

---

## 七、发现（issue）

**[RA-A01] severity=major** —— evidence_manifest EVD-05/EVD-06 对 xlsx 结构陈述失实
- 定位：evidence_manifest.md EVD-05「backtest_summary.xlsx 11637B(7 sheet)」、EVD-06「xlsx『主绩效表』/『主绩效表_对照』/『SA1_模块消融』」
- 实测（pandas 亲开）：xlsx 仅 2 个 sheet ['主绩效表','净值序列']；`主绩效表_对照`『SA1_模块消融』**不存在**，`净值序列` 未被提及。
- 依据：EVD-05 称 7 sheet 与实测 2 sheet 不符；SA1 的 E4「三方」第三方（xlsx）实为缺失却被声称在册——「亲自 pandas 读 xlsx」的证据描述与实际产物矛盾。核心 24 项数值本身真三方一致（已确认），故属证据链陈述失实而非数值编造，须订正 EVD-05/06 措辞或补齐 sheet。

**[RA-A02] severity=major** —— verify_report.md 主绩效表为 smoke 陈值，未同步全档，与权威产物冲突
- 定位：verify_report.md m4 第三节「主绩效表」SIT Sharpe **0.3836**、「58 期」 vs metrics.json/xlsx/日志 SIT **0.7348**、60 期
- 依据：E4 规则字面为「metrics.json == verify_report.md == xlsx」，但 verify_report.md 停留在缩减档 smoke 数（0.3836），全档 0.7348 只落 comparison.json/metrics.json；EVD-06 悄然以「日志」替换 verify_report.md 作第三方。权威数（metrics/xlsx/日志）真实一致、无编造，但 verify_report.md 作为具名产物仍显 smoke 值，reporter 若据此引用将得错值——须补 final 全档节或标注失效。

**[RA-A03] severity=minor** —— comparison.json「SIT…居第 4」与自身 ranking 矛盾
- 定位：comparison.json `sit_dominates_baselines.observed`「SIT Sharpe 0.7348 居第 4」 vs metrics.json `ranking_by_sharpe_reproduced` 列 SIT 于第 3 位
- 依据：独立复算 0.7348 > DLinear 0.7306，SIT 实为第 3。方向为**低估** SIT 名次（非夸大），不属虚报，但内部不一致宜订正为「第 3」。

**[RA-A04] severity=minor** —— 净值序列/NAV 图 SIT·DLinear 用单种子路径，未标注
- 定位：xlsx 净值序列 SIT 尾值 1.7546、portfolio_nav.png SIT 尾≈1.75，均为 seed0 单种子路径；而主绩效表 SIT FinalWealth 1.6014 为 3 种子均值（单种子基线 EW/GMV/CVaR/HRP 则逐位吻合）
- 依据：图/序列尾值与表内 final_wealth 相差（1.75 vs 1.60）源于 3 种子模型取 seed0 代表路径，可解释、非伪造，但图题未注「单种子」，易致读者误读，宜加注。

---

## 八、已检查维度清单（无遗漏）

- E4 三方一致：主表 24 项 metrics↔xlsx↔日志逐位重算（一致）；SA1/SA2 metrics↔日志（一致，xlsx 缺见 RA-A01）
- K2 触发条件：已判断（未触发，无硬编码嫌疑）
- K3 扰动测试：hard 必做已核（已触发/已记录/结论成立）
- skip/infeasible 理由：R1/R2/R3 算力缩减非 data_missing，对 catalog 核实成立
- 核验分级合理性：comparison.json 无 verification_level 字段，N/A
- 结论措辞夸大：已核（未夸大，SIT 未碾压如实呈现）
- SA1 方向陈述：已核（两核心有贡献/两细无贡献属实，无粉饰）
- market-transplant 登记一致性：已核（AS11/12/13/16/19 一致）
- 5 张 PNG：逐张 Read 亲查（曲线数=分组数、坐标域吻合、真实代码）

---

verdict: pass_with_issues
