# 外审意见逐条回应总表

> 协议：critical 必须 fix 并复审通过；major 必须回应（accepted 修 / rejected 说理）；minor 登记即可。
> 同一意见连续两轮 rejected 且外审坚持 → 升级人工；同一审查点审→修→复审最多 3 轮。

## checkpoint=spec · engine=codex · 2026-07-08

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
|--------|----------|------|----------------------------------|---------------------------------------|------|
| CDX-S-01 | major | B1 将隔日反转系列表7-13 整体登记为 2015-03-24 起，表7/图14 原文实为 2015-03-20 起 | accepted | quant-extractor 定向修复：spec.md 第四节 B1（页码/原文/参数三行拆分登记两段区间）+ 第五节 R7 原文行对齐 + 矩阵变更日志留痕；原文证据 report_text.md p11:645、p12:674 逐字核实 | pass |

（内审 extract_audit.md：C1–C6 全 PASS、15 条幻觉抽查零命中、verdict pass，无需回应条目。）

## 内审意见处置（extract_audit.md 对抗性复核轮）

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
|--------|----------|------|----------------------------------|---------------------------------------|------|
| SA-A01 | major | R2/R3/R4（p8 表2/3/4）数值视觉可读却被误判 data_missing 全表 n/a，三整表基准系统性漏提 | accepted | quant-extractor 视觉补录（270 格零模糊，锚点 3/3 匹配，spec.md 第五/六/八节同步修正）+ 矩阵三行复归并由 quant-planner 归属 m2 + A2/AS1 依据复评更新（去失效前提）；渲染图留存 /tmp/test_v2_p8*.png | pass |

## milestone 级内审（impl_audit_m1，verdict pass_with_issues）

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
|--------|----------|------|----------------------------------|---------------------------------------|------|
| CA-A01 | minor | build_main_panel 注释称保留前置历史实际截断主区间，m2 的 F1 扩窗若直接消费有落窗风险 | accepted | 路由为 m2 实现约束：F1 扩窗分位必须消费 load_hs300 全历史源（已写入 m2 coder 派发合同）；注释矛盾留 code_audit 阶段统一修正 | 待code_audit |
| CA-A02 | minor | timing_metrics 内联 sharpe/win_rate/calmar 未复用 common.utils 助手 | deferred | 合理偏离已在 docstring 声明（win_rate 持仓日口径为正确所需），登记备查不改码 | - |

## milestone 级内审（impl_audit_m2 / impl_audit_m4，均 pass_with_issues）

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
|--------|----------|------|----------------------------------|---------------------------------------|------|
| CA-B01 | minor | strategy.py:209/config.py:50 注释误写 AS6 应为 AS8 | accepted | 留 code_audit 阶段统一修正（注释级，不影响计算） | 待code_audit |
| CA-B02 | minor | strategy.py:288 build_reversal_signal 死代码占位 | accepted | 留 code_audit 阶段清理（F3 实际在 reversal.py，无矩阵行指向，非虚报） | 待code_audit |
| CA-C01 | minor | 盈亏比多空 1.05 vs R7 1.31（-20%），疑 B1 引擎按日口径 vs 研报按笔口径 | accepted | 路由 final verify 逐格对比与 diagnoser 归因（B1 引擎口径问题跨 R 表一致存在，非 m4 私自偏离） | 待verify |

## milestone 级内审（impl_audit_m5 / impl_audit_m6，均 pass_with_issues）

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
|--------|----------|------|----------------------------------|---------------------------------------|------|
| CA-D01 | minor | R8 盈亏比 1.085 vs 1.33（-18%），忠实沿用 B1 per-day 口径 | accepted | 与 CA-C01 同源（common/timing_backtest.py:150-156 引擎口径），跨 R1/R7/R8/R9 一致存在；路由 final verify 统一对数与 diagnoser 归因 | 待verify |
| CA-E01 | minor | R9 盈亏比 1.103 vs 1.36（-19%），同一根因 | accepted | 同上，合并处置 | 待verify |

## milestone 级内审（impl_audit_m7 复核轮 / impl_audit_m8）

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
|--------|----------|------|----------------------------------|---------------------------------------|------|
| CA-F01 | critical | AS10 未落盘却被全局引用（登记动作不实声明） | accepted | m7 coder 补登 assumptions.md:117 完整 AS10 块（含口径A/B证据）；审计复核轮确认达标 | pass |
| CA-F02 | major | 矩阵 F5/F8/R11/R12 四行未回填与变更日志矛盾 | accepted | m7 coder 回填 done+真实实现位置+implement；审计复核确认 | pass |
| CA-F03 | minor | R11 盈亏比 1.116 vs 1.44 底座口径 | accepted | 与 CA-C01/D01/E01 同源，路由 final verify | 待verify |
| CA-G01 | minor | _monthly_stats 对 _yearly_stats 薄复制（DRY） | deferred | 不影响正确性，登记备查 | - |
| CA-G02 | minor | R13/SA3 年化与盈亏比继承底座 offset | accepted | 同 CA-F03 合并处置 | 待verify |

## checkpoint=code · engine=codex · 2026-07-08

codex 代码外审 verdict=pass，findings=0（五维度显式 no_findings：公式逐要素对照/未来函数前视/数据对齐/config vs B类/作弊模式 K1/K5/K6）。无意见需回应；内审 CA-* 系列处置见前文各节。

## checkpoint=result · engine=codex · 2026-07-09

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
|--------|----------|------|----------------------------------|---------------------------------------|------|
| CDX-R-01 | critical | verify_report final 段仍写 56/91（35 项 fail）且现在时指向 comparison.json，与现行 81/91 矛盾，易致 final_report 采信过期数字 | accepted | quant-verifier 两轮定向修正：verify_report.md L711【快照说明】（final 段标为 iteration=0 快照，指 iter_01/comparison.json 留档）+ L838（iter1 指 iter_01/comparison_after.json）+ L904（iter2 指 iter_02/comparison_after.json）+ L910-919 新增「终态汇总」（81/91、fail 10=accepted 8/assumption_linked 2、轨迹 56→69→81，指现行 comparison.json）；codex 缩减复审 resolved=true、residuals=[]（留档 result_audit_codex_reaudit.md） | pass |

## 内审意见处置（result_antifraud_review.md，verdict pass_with_issues）

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
|--------|----------|------|----------------------------------|---------------------------------------|------|
| RA-A01 | minor | build_final_artifacts.py:281 rolling_sharpe 年化因子仍 √252，M2 改 240 后未同步，图面偏高约 2.5% | accepted | quant-verifier 定向修复：L281 年化因子 √252→√240（rolling(252) 窗口长度非年化口径、保持不变），重出 rolling_sharpe.png（00:21，266031B）；计分产物经 md5 深比对逐位不变并还原基线保住 attribution_status（accepted 8/assumption_linked 2 完好），留痕 run_log.md「result_audit 定向修复记录（RA-A01）」 | pass |
| RA-A02 | minor | comparison.json `iteration` 字段恒为 0 未随迭代递增（元数据，不影响计分数据） | deferred | 历史轮次已由 iterations/iter_NN/comparison_after.json 留档快照完整承载，元数据字段修复收益低；列入 final_report 系统改进建议（build_final_artifacts.py 生成时应从 state.json 读 iteration.current 回填） | - |
| RA-A03 | minor | 透明性确认：T 年化 0.023002 与 R11 下跌胜率 0.4901 精确命中属口径对齐非拟合；AS13 已如实标注「可信度中等·惯例层代理残余数据漂移」 | accepted | 非缺陷，为披露保全要求：已写入 report 阶段 quant-reporter 派发合同——final_report.md 必须保留 AS13 可信度中等标注，不得在汇总中弱化或省略 | 待report点收 |
