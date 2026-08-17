# 独立盲提取差异裁决

| ID | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |
| --- | --- | --- | --- | --- | --- |
| DIF-01 | 目标冲突 | shadow-rate变化与市场风险状态分类目标并存，规格正文未显式并列 | p9,p15 | adopted | 依据 spec_audit_codex.md CDX-S-01 |
| DIF-02 | 来源冲突 | p5 Refinitiv与多张Exhibit的FRED/Factset来源陈述并存 | p5及Exhibit来源行 | adopted | 依据 spec_audit_codex.md CDX-S-02 |
| DIF-03 | 标签频率冲突 | Exhibit 1写daily return，正文p5写monthly performance | p4-p5 | adopted | 依据 spec_audit_codex.md CDX-S-03 |
| DIF-04 | 样本终点冲突 | 正文样本截止Mar-23，Exhibit 16横轴可见May-23 | p5,p12 | adopted | 依据 spec_audit_codex.md CDX-S-04 |
| DIF-05 | 表格证据遗漏 | tables_extracted缺R2、R3、R7-R10整表 | p8-p13 | corrected | 依据 extract_audit.md SA-A01，PDF终审数值 |
| DIF-06 | 矩阵结构遗漏 | R4-R6缺表头、行名及Value首行 | p10 | corrected | 依据 extract_audit.md SA-A02，PDF终审数值 |
