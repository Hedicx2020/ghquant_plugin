# 规格盲提取差异与裁决

| 差异ID | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |
| --- | --- | --- | --- | --- | --- |
| DIF-01 | 表格提取缺失 | `tables_extracted.md` 的 17 个对象均为图形误识别，主文与附录 51 个物理数值表没有形成可逐格复核的表格。 | p27-p41, p52-p104 | corrected | 修复后 `tables_extracted.md:10-1075` 含 51 个物理表；独立复核 51/51 pass。 |
| DIF-02 | R 基准不完整 | 24 个 R 要素均只选摘部分行列，未满足结果表完整网格合同；典型 Table 3 从 8×10 截为 3×9。 | p28-p104 | corrected | R1-R24 已按表源补全网格；独立复核逐行逐列核对 24/24 pass。 |
| DIF-03 | 附录结果表关联错位 | IA.11、IA.13、IA.14、IA.15 没有获得内容相符的 R 要素；原 R19-R22 实际对应其他附录表。 | p65, p68, p70-p71 | corrected | 新增 R25-R28，并同步 `coverage_matrix.md:74-77`、`plan.md:54,69`；独立复核 pass。 |
| DIF-04 | R12 漏行 | R12 漏登 Continuation × Valuation formation-period 行：0.05%、t=0.05、80/80 月。 | p39, p91 | corrected | `spec.md:682-697` 已补完整四行及主表/IA.27 符号说明；独立复核 pass。 |
| DIF-05 | 幻觉页码 | B12 的逐字摘录真实位置是 p12，但要素页码仅写 p29、p35-p36，按登记页无法定位。 | p12, p29, p35-p36 | corrected | `spec.md:392-397` 与矩阵已补 p12；`report_text.md:529-533` 可定位；独立复核 pass。 |
| DIF-06 | SA 结论定位不完整 | SA2、SA3、SA5、SA6、SA9、SA10、SA12 的结论原文位于 p15-p20，但条目只列结果表/图页。 | p15-p20 及各结果页 | corrected | `spec.md:1286-1369` 与矩阵已补讨论页；复核逐条可精确或跨页近似定位，pass。 |
