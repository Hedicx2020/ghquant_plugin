# 审计回应总表

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | major | shadow-rate目标与市场状态分类目标冲突未显式抄录 | accepted | 已在spec.md:311-314及542-543并列补录原文冲突，A6保留裁决边界 | pass |
| CDX-S-02 | major | Refinitiv与FRED/Factset数据来源陈述冲突未登记 | accepted | 已在spec.md:127-160并列补录两组来源陈述，A23/AS22明确不作逐变量归属 | pass |
| CDX-S-03 | major | Exhibit 1日频标签与正文月频标签冲突未登记 | accepted | 已在spec.md:348-351并列补录daily/monthly冲突，A24裁决r004不实现原ML标签 | pass |
| CDX-S-04 | major | 样本截止Mar-23与Exhibit 16横轴May-23冲突未登记 | accepted | 已在spec.md:431-434及EX16登记终点冲突，A25保持两侧证据 | pass |
| SA-A01 | critical | tables_extracted整表遗漏R2、R3、R7、R8、R9、R10 | accepted | 已重建tables_extracted.md:8-136的R1-R10完整证据层 | pass |
| SA-A02 | critical | R4-R6相关矩阵缺表头、行名和Value首行 | accepted | 已在tables_extracted.md:40-84补齐三个6×6矩阵的表头、行名、Value首行与全部值 | pass |
| SA-A03 | critical | A23把通用FRED/Factset来源行推断为具体变量归属 | accepted | 已在ambiguities.md:235-237、assumptions.md:265删除推断性归属，仅保留通用来源冲突 | pass |
| SA-A04 | minor | coverage的F9、B1页码未同步冲突证据页 | accepted | 已将coverage_matrix.md:46的F9更新为p4-p5、:59的B1更新为p5,p12 | pass |
| CDX-C-01 | major | 损坏或不可读的.reproduce.json被静默回退到默认数据根目录 | accepted | `common/data_loader.py:18-53` 已改为发现配置后读取或解析失败即携带路径抛错；`tests/test_data_loader_config.py:1-85` 覆盖缺失配置回退、损坏JSON和不可读文件，4项测试通过 | pass |
| CDX-C-02 | major | 工作簿QA warning与inspect/render缺口未阻断正式产出 | accepted | `src/r004_all_a_style_box/main.py:49-172` 与 `workbook_builder.mjs:28-45,298-508` 已将warning、inspect/preview缺口、公式错误、OOXML错误和图表计数错配全部升级为硬失败；故障注入6/6拒绝，正常五工作簿warning=0 | pass |
| CDX-C-03 | minor | src重复实现common已有统计接口 | accepted | `src/r004_all_a_style_box/reporting.py:22-27,248-259,630,690-710,777-780` 已复用common的最大回撤、收益波动胜率及IC/RankIC接口；仅保留不等价的CAGR/Sharpe编排并显式披露，迁移回归最大误差4.51e-17 | pass |
| CDX-C-04 | minor | IC分布图缺少正态拟合曲线 | accepted | `src/r004_all_a_style_box/reporting.py:1104-1146` 已按同一RankIC样本叠加正态密度拟合，并对样本不足/零方差显式标注；两条可拟合曲线动态复核通过 | pass |
| CDX-R-01 | critical | R10/SA4 核心表现对比仅覆盖年化收益和行数，遗漏波动率、Sharpe、超额收益、跟踪误差、信息比率 | accepted | 回 verify 补齐 `comparison.json` 的逐实体及逐基准核心指标，并同步修订 `verify_report.md` 的指标总数；当前正式结果在复核完成前不对外交付为最终版 | open |

附加复审发现 `CDX-C-05`（声明图表为空时可能静默降为零张）已在
`src/r004_all_a_style_box/workbook_builder.mjs:186-221,458-549` 修复：空列、空行、
行宽不等及仅类别无有限数值四类反例均非零退出；最终外部复审
`code_audit_codex_reaudit_round2.md` 的 `findings=[]`、`verdict=pass`。
