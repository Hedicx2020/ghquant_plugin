# 提取差异记账 extract_diff.md（ssrn_6115073）

> spec_audit 阶段主会话记账（非内容生产）。逐条登记 codex 盲提取清单 `spec_codex.md` / 内审 `extract_audit.md` 与 `spec.md` 的差异项，裁决列照录审计结论（R 类数值以 PDF 原文为终审），并注明依据来源。
> 双通道互补记录：codex 盲提取捕获了表3（SA1）16 格错录与表2 PSR 单格错位；内审 auditor 独立重算捕获了表2 AStd·DowJones 行错位（该行 codex 盲提取与旧 spec 同错、未捕获）。两通道各补对方盲区，全部经 extractor 回 PDF 400dpi 图像逐格终审后订正。

| DIF-ID | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |
| --- | --- | --- | --- | --- | --- |
| DIF-01 | 数值(R/表2) | 表2(R1) `AStd·DowJones` 行末列错位：Index/HRP/HERC/OLMAR 4 格错、NCO 正确。订正为 Index=0.218(加粗)/HRP=0.097/HERC=0.132/OLMAR=0.112/NCO=0.132 | p27 | corrected | extract_audit.md SA-A01（内审独立重算捕获；codex 盲提取此行与旧 spec 同错未捕获）+ extractor PDF p27 图像终审确认判读正确 |
| DIF-02 | 数值(R/表2) | 表2(R1) `PSR·DowJones·EWMFM` 0.512→0.521（与相邻 Index 列 0.512 列间错位） | p27 | corrected | spec_audit_codex 阶段二 CDX-S-01 + extractor PDF p27 终审确认判读正确 |
| DIF-03 | 数值(SA/表3) | 表3(SA1) 共 16 格数值错录：2016-2020 AStd·S&P500·EWMFM 0.153→0.154；2017-2021 AStd·DowJones 自 EWMFM 起整段右移一列（5 格）；2018-2023 AStd 三市场多格 + SR·DowJones·NCO 0.547→0.665 + PSR·S&P500·EWMFM 0.503→0.253 + AR·DowJones·PMM 0.123→0.073 | p28 | corrected | spec_audit_codex 阶段二 CDX-S-02（判读正确，实际比概述多 1 格）+ extractor PDF p28 逐格图像终审；内审 SA-A02 仅认 1 格，严重低估错误范围 |
| DIF-04 | 遗漏(D) | D2/TBL8 未逐条登记 BorutaShap 候选池完整 18 项宏观因子（原仅列选出的 7 项），缺候选明细致 18→7 特征筛选无法按原文定义复现 | p43(表A.1) | adopted | spec_audit_codex 阶段二 CDX-S-03（仅 codex 盲提取有完整 18 项 → Claude 遗漏）；已补录 spec.md:102（D2 说明）全 18 项全称+缩写 |
| DIF-05 | 页码(F) | F1 页码范围「p6-p8, p9」下界略宽：价格相对/组合/财富式 1-4 实落 p8，p6 为 2.1 OLPS 文献综述 | p6-p8 | dismissed | extract_audit.md SA-A03（minor/conf low，非遗漏非幻觉，F1 三条引文均 p8 命中、C6 不受影响，为提示性下界，不订正） |

裁决口径：DIF-01/02/03 为 R/SA 类数值，以 PDF 原文为终审（extractor 400dpi 图像逐格核对）→ corrected；DIF-04 为结构性遗漏、审计结论确有 → adopted 并补录；DIF-05 为 minor 呈现细节、不碍复现 → dismissed。所有 DIF 行裁决列非空（G-SA-3）。
