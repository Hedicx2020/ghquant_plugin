# 审计意见处置台账 audit_responses.md（ssrn_6115073）

> spec_audit 审查点：codex 盲提取外审（CDX-S-）+ 内审 quant-auditor mode=spec（SA-A）意见全量逐条处置。一条意见一行，不合并不省略。
> 门禁校验：CDX-S- 回应行数（3）== spec_audit_codex.md findings 数（3，G-SA-4）；无 open critical（G-SA-5）；全部 major 有回应（G-SA-6）。

## spec_audit（spec 审查点）

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | major | 表2(R1) PSR·DowJones·EWMFM 抄为 0.512，应为 0.521（列间错位） | accepted | spec.md:274 已订正 EWMFM 0.512→0.521；PDF p27 400dpi 图像终审确认判读正确，相邻 Index 列维持 0.512 | pass |
| CDX-S-02 | major | 表3(SA1) 约 15 格数值错录（多行右移错位 + 个别单格） | accepted | spec.md:405/423/439/440/441/443/445 逐格订正共 16 格；PDF p28 图像终审确认 codex 判读正确，另新捕 AR·DowJones·PMM 0.123→0.073（比 codex 概述多 1 格） | pass |
| CDX-S-03 | major | D2/TBL8 遗漏 BorutaShap 候选池完整 18 项宏观因子逐条登记 | accepted | spec.md:102（D2 说明）已补录完整 18 项全称+缩写；PDF p43 Table A.1 逐字核对；要素 ID/计数不变 | pass |
| SA-A01 | major | 表2(R1) AStd·DowJones 末列错位（内审独立重算） | accepted | spec.md:268 已订正 Index/HRP/HERC/OLMAR 4 格（0.218/0.097/0.132/0.112），NCO 维持 0.132；PDF p27 终审确认内审判读正确（codex 盲提取此行漏捕） | pass |
| SA-A02 | minor | 表3(SA1) 2016-2020 AStd·S&P500·EWMFM 0.153 应为 0.154（内审） | accepted | spec.md:405 已订正 0.153→0.154（含在 CDX-S-02 的 16 格订正内）；内审此项方向对但严重低估表3整体错误范围 | pass |
| SA-A03 | minor(conf low) | F1 页码范围 p6-p8 下界略宽（内审） | rejected | 技术理由：非遗漏非幻觉，F1 三条引文均在 p8 命中，C6 页码抽查不受影响；p6 下界为提示性范围，维持原登记不订正 | pass |

## 处置汇总

- CDX-S- 意见 3 条（全 major）：全部 accepted 并回 PDF 图像终审订正落地，复核 pass。
- 内审 SA-A 意见 3 条（1 major / 2 minor）：SA-A01/SA-A02 accepted 订正，SA-A03 rejected（immaterial，给技术理由）。
- open critical：0；未回应 major：0。审→修→复审 1 轮闭环，无需二轮。
- 说明：本案例 reproduction_mode=experimental，数值对齐在 verify/result 阶段整体豁免；但 spec 忠实性订正独立于该豁免，本轮已将原文参考数值全部回填至 PDF 终审值。

## code_audit（code 审查点）

> codex 全代码外审（read-only）+ 逐里程碑 impl_audit_m1-m7（implement 阶段已产、无空壳）。codex 5 维度：公式对照/未来函数/数据对齐/config vs B类/作弊排查(K1/K5/K6)。verdict=fail（2 major，无 critical）。

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-C-01 | major | 建仓仅用 tradeable_mask 未合并 member_mask，训练期入选但调仓月已调出指数的股票仍进组合，违 B1 时点成分股 + 与 AS56 声称「建仓前过滤非成分股」不符且未登记 | accepted | portfolio.py 所有建仓入口（CPMM/CPM/PMM/EWMFM + HRP/HERC/NCO/OLMAR，`_buildable_at`）已叠加 `selected ∩ member_mask[t] ∩ tradeable_mask[t]` 时点过滤、剩余资产重归一化；robustness.py（SA1-4，`_backtest_selected`:201）同口径补齐；Index 买入持有不受影响；member_mask 时点≤t 无未来函数；AS56 订正；main.py+robustness.py 重跑 exit=0。**副产真实迁移事实（交 verify/result_audit 记录）**：持仓 ~9→~3 只（揭示大量训练期入选但调仓已非成分股票被误纳，现按 B1 剔除，组合趋集中）；§九.2 消融方向定性不变（去宏观/去溢出仍劣于 CPMM）；SA4 关键因子结论翻转（PMI 由「最关键」改为「最强单因子但组合不依赖任一因子」） | pass |
| CDX-C-02 | major | data_prep.py:436 F12 选因子用裸 except Exception→degraded_all，会把算法/数据/实现错误静默伪装成已登记依赖退化（K5 核心路径） | accepted | data_prep.py:436 except 收窄为**仅 `(ModuleNotFoundError, ImportError)`** 走 AS16/AS38 授权的 degraded_all；其它异常 `traceback.print_exc()`+`raise RuntimeError` 不静默；当前环境确缺 shap→仍走 ModuleNotFound 降级、`selection_mode='degraded_all'` 逐值不变，仅错误处理显式化；AS38 订正；exit=0 | pass |

## code_audit 处置汇总
- CDX-C- 意见 2 条（全 major）：全部 accepted 并修复落地，复核 pass。open critical：0；未回应 major：0。审→修 1 轮闭环。
- impl_audit_m1-m7 无 `判定: not_found`（无空壳虚报）。
- **member 过滤（CDX-C-01）连锁改变 R1/SA 数值与 SA4 结论**——最终 verify 阶段将在修正后代码上重跑权威 R1/SA/comparison/证据链，刷新过时的里程碑级验证结论。
