# 提取完整性审计 extract_audit.md

- mode：`spec`
- 审计对象：`r004_all_a_style_box`
- PDF 终审源：`reports/r003_equity_factor_timing_cn.pdf`（18 页）
- 审计原则：仅据 PDF、`report_text.md`、`tables_extracted.md`、`spec.md`、`coverage_matrix.md`、`ambiguities.md`、`plan.md` 和审计模板独立核验；未读取完成汇报、`audit_responses` 或 `state.json`。

## C1–C6 检查项

### C1 图表编号连续性

| 独立检查 | PDF / report_text.md 重算结果 | spec.md 登记 | 结论 |
| --- | --- | --- | --- |
| Exhibit 标题编号 | 正则命中标题集合 `{1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17}`，连续无缺号，`fig_max=17` | frontmatter `fig_max: 17`；第六节 EX1–EX17 共 17 行 | match |
| Table / Figure 独立编号 | PDF 全文未出现 `Table N`、`Figure N` 或 `Fig. N` 编号，`tbl_max=0` | frontmatter `tbl_max: 0`、`TBL_registered: 0` | match |
| 登记页码 | EX1–EX17 依次位于 p4、p5、p6×2、p7、p8×2、p9×2、p10×3、p11×2、p12×2、p13 | `spec.md:651-667` 同序登记 | match |

结论：独立重算 `fig_max=17`、`tbl_max=0`，与 `exhibit_declared` 完全一致；未发现漏号、跳号或未登记 Exhibit。

### C2 逐页覆盖扫描

| 页码 | PDF 页面内容独立判读 | spec 页面覆盖关联 | 判定 |
| --- | --- | --- | --- |
| p1 | 封面、Key Findings、摘要、引言 | F1、SA3 | match |
| p2 | 因子投资、宏观变量与因子择时文献背景 | D1–D4；内容类型已标背景 | match |
| p3 | 商业周期择时文献、风险状态与本文增量 | D5–D10、F17；内容类型已标背景 | match |
| p4 | 方法总览、两阶段框架、Exhibit 1、基准说明 | F1–F5、EX1；SA4 另在要素本体登记 p4 | match |
| p5 | 第二阶段、滚动训练、1987-03 至 2023-03/433 月、25 个宏观驱动声明、Exhibit 2 | D15–D29、B1–B3、F8–F10、EX2 | match |
| p6 | Exhibit 3 的 10 个可识别宏观变量、Exhibit 4 的六因子定义 | D1–D10、D14、F11–F16、B10、EX3–EX4 | match |
| p7 | 金融湍流公式、10 个行业与 3 个国债期限、Exhibit 5 | D12–D13、F6、EX5 | match |
| p8 | 肘部法、三类风险状态、Exhibit 6–7 | F2–F3、B2、R1、EX6–EX7 | match |
| p9 | Exhibit 8–9、五折时序验证、状态占比、特征重要性、二阶段标签 | F4–F5、F7–F10、B4、B8–B9、R1–R3、EX8–EX9 | match |
| p10 | Exhibit 10–12、三张相关矩阵、六因子胜出频率、84 月训练窗 | R4–R7、SA2、EX10–EX12 | match |
| p11 | Exhibit 13–14、样本外概率、分状态特征重要性、1987–2000 训练说明 | B5–B6、R8、SA3、EX13–EX14 | match |
| p12 | 商业周期基准、15% 配置、概率权重、Exhibit 15–16 | F17–F21、B11–B14、R9、SA4、EX15–EX16 | match |
| p13 | Exhibit 17 曲线与绩效表、结论 | B7、R10、SA3–SA4、EX17 | match |
| p14 | 附录：K-Means 与随机森林方法/公式 | F2、F7、F10 | match |
| p15 | 附录：特征重要性与 Stacking 公式 | F4、F7 | match |
| p16 | 附录：SMOTE 公式、致谢、参考文献起始 | F5 | match |
| p17 | 参考文献 | 内容类型明确标为参考文献，合理无要素 | match |
| p18 | 版权声明 | 内容类型明确标为版权声明，合理无要素 | match |

结论：18/18 页均有内容类型，含密集百分数/公式的 p8–p16 均有关联要素或明确类型；无“≥3 个百分数或公式符号但无要素且无类型标注”的页面。

### C3 触发词检查

PDF 为英文，除模板中文词外同步检查英文等价词。

| 触发词 | 命中页 | 对应登记或排除说明 | 判定 |
| --- | --- | --- | --- |
| 敏感性 / sensitivity / sensitive | 无 | 无需登记 | match |
| 稳健性 / robust / robustness | p1、p2、p11、p13–p14 | F1、SA3、SA4；p2/p14 为背景/方法描述 | match |
| 参数 / parameter | 无实质参数敏感性命中 | 具体参数由 B1–B14 登记 | match |
| 分组 / group / grouping / regime | p4–p5、p7–p11、p14 | F2–F3、F8–F10、R1、R5–R8、SA2 | match |
| 分年度 / by year / yearly | 无 | 无需登记 | match |
| 子样本 / subsample / sub-sample | p11 | F8、SA3 | match |
| 分市值 / size | p1–p3、p6、p9–p13 | D14、F16、R4–R10；背景段已标类型 | match |
| 牛熊 / bull / bear | p8–p9 | F3、B9、R1、R5–R8 | match |
| 附录 / appendix | p9、p14–p16 | F2、F4–F5、F7、F10 | match |
| 进一步 / further | p2–p4 | 背景/未来研究表述；p4 关联 F1 | match |
| 滚动 / rolling、样本外 / out-of-sample | p4–p5、p9–p13 | B3–B7、SA3 | match |
| 交叉验证 / cross-validation / five folds | p9 | B8、R2、SA1 | match |

结论：未发现命中页缺少 SA/F/R 关联且无排除说明的触发词遗漏。

### C4 计数交叉

| PDF 计数声明 / 可独立重算项 | 独立重算 | spec / coverage 登记 | 判定 |
| --- | ---: | --- | --- |
| 两阶段框架 | 2 阶段 | F1 完整登记两阶段 | match |
| 样本月数 | 1987-03 至 2023-03 含首尾，共 `36×12+1=433` 月 | B1=433 | match |
| 宏观驱动总数 | p5 明称 25；p6 Exhibit 3 逐项仅列出 10 个变量，差额 `25-10=15` | D1–D10 + D15–D29 = 25；15 项未披露占位 | match |
| 风险状态数 | 3 个 cluster | F3、R1=3 | match |
| 风险状态占比 | `77.5%+18.7%+3.8%=100.0%` | R1 三项完整 | match |
| 入选权益因子 | 6 个 | F11–F16 共 6 项 | match |
| Stacking 第一层分类器 | 3 个：RF、SVC、GNB | F4 | match |
| 交叉验证折数 | 5 折 | B8、SA1、R2 | match |
| 第一阶段特征重要性类别 | 4 类，且 `19.7%+26.9%+34.1%+19.3%=100.0%` | R3 四行 | match |
| 第二阶段风险状态 | bear 合并后 2 类：normal、correction | B9、R5–R6、R8 | match |
| 历史胜出频率因子 | 6 项，合计 `100.0%` | R7 六行 | match |
| Exhibit 14 特征 | 6 项；两列分别合计 `100.0%`、`100.0%` | R8 六行两列 | match |
| 商业周期阶段 | 4 个 | R9 四列 | match |
| 组合比较方法 | 4 种 | R10 四行 | match |
| spec 要素数 | D=29、F=21、B=14、R=10、SA=4，总计 78 | frontmatter 与 coverage_matrix 78 行均一致 | match |

#### 15 个未披露宏观驱动专项核查

- PDF p5 明确写有 “Details of the 25 macro drivers considered for”，见 `report_text.md:282-288`；PDF p6 Exhibit 3 逐项只能识别 10 个变量，见 `report_text.md:325-350`。
- `spec.md` 将可识别 10 项登记为 D1–D10，将差额 15 项逐一登记为 D15–D29，均为 `missing/nonrecoverable`，见 `spec.md:150-268`；未猜测名称、数值或变换。
- `coverage_matrix.md:23-37` 将 D15–D29 逐项标为 `infeasible`，理由均回指 A1；`ambiguities.md:3-11` 保持 A1=`blocking`、状态=`blocked`，没有为过门禁伪降级。
- `plan.md:78-86` 明确说明本计划是中国全 A 2×2 风格箱实验、不是原文两阶段 ML 复现，并明确写出 “D15-D29 仍保持不可恢复，A1 仍保持 blocked；该支线不进入本计划实现范围”。因此 A1 被排除出全 A 主线的范围边界透明，没有把 blocked 冒充 resolved；本项不评价中国全 A 策略优劣。

### C5 基准表完备与 R1–R10 逐格复核

以下数值均直接以 PDF 原页终审，并与 `spec.md:496-643` 逐格比对；`tables_extracted.md` 仅作为辅助，不采信其完整性声明。

| R 要素 | PDF 结构与逐格独立读数 | spec 对照 | 判定 |
| --- | --- | --- | --- |
| R1 | p8–p9：K=3；Normal=77.5%、Correction=18.7%、Bear=3.8%，占比和=100.0% | 4/4 项一致 | match |
| R2 | p9 Exhibit 8，3×2：Accuracy=71%、Precision=0.753、Recall=0.721 | 3/3 数值一致 | match |
| R3 | p9 Exhibit 9，4×2：Equity Valuation=19.7%、Financial Turbulence=26.9%、Financial Conditions=34.1%、Monetary Policy Expectation=19.3% | 4/4 数值一致 | match |
| R4 | p10 Exhibit 10，6×6 下三角含对角线 21 格：`[1] / [0.66,1] / [0.68,0.93,1] / [0.76,0.70,0.71,1] / [0.85,0.86,0.83,0.87,1] / [0.86,0.76,0.77,0.64,0.80,1]` | 21/21 数值一致；上三角空白均记 n/a | match |
| R5 | p10 Exhibit 11 Normal，6×6 下三角含对角线 21 格：`[1] / [0.46,1] / [0.46,0.89,1] / [0.63,0.56,0.55,1] / [0.73,0.79,0.75,0.80,1] / [0.77,0.63,0.64,0.43,0.66,1]` | 21/21 数值一致；上三角空白均记 n/a | match |
| R6 | p10 Exhibit 11 Correction，6×6 下三角含对角线 21 格：`[1] / [0.54,1] / [0.61,0.86,1] / [0.76,0.57,0.60,1] / [0.86,0.70,0.68,0.88,1] / [0.88,0.64,0.69,0.67,0.81,1]` | 21/21 数值一致；上三角空白均记 n/a | match |
| R7 | p10 Exhibit 12，6×2：Value=19.9%、Growth=15.9%、Momentum=14.4%、Low Volatility=21.3%、Quality=4.0%、Small Size=24.5%，合计=100.0% | 6/6 数值一致 | match |
| R8 | p11 Exhibit 14，6×3：Equity Valuation=(36.4%,42.5%)、Financial Turbulence=(12.4%,13.1%)、Inflation=(16.3%,17.9%)、Financial Conditions=(22.4%,15.3%)、Monetary Policy Expectations=(9.3%,9.9%)、GDP Growth=(3.2%,1.3%) | 12/12 数值一致 | match |
| R9 | p12 Exhibit 15，6×5；按 Expansion/Slowdown/Contraction/Recovery：Value=`n/a,−,n/a,+`；Growth=`n/a,−,+,−`；Momentum=`+,+,n/a,n/a`；Low Volatility=`n/a,+,−,−`；Quality=`n/a,+,−,n/a`；Small-Cap=`−,−,+,+` | 24/24 方向或空白格一致 | match |
| R10 | p13 Exhibit 17，4×7：Russell 1000=`8.40%,15.49%,0.52,n/a,n/a,n/a`；Equal Weighted=`8.63%,15.19%,0.54,0.18%,2.40%,0.07`；Business Cycle Tilt=`9.84%,16.06%,0.59,1.50%,3.95%,0.36`；ML Approach=`11.47%,16.81%,0.66,2.89%,6.68%,0.45` | 24/24 数值或空白格一致 | match |

PDF 终审结论：R1–R10 在 `spec.md` 中没有少行、少列或数值错抄。但 `tables_extracted.md` 本身不完备，具体见 SA-A01、SA-A02；不能仅凭该文件复核 R 表。

### C6 幻觉引用抽查

| 抽样要素ID | 类别 | 页码 | spec.md 摘录原文 | 回查 report_text.md / PDF 结果 | 判定 |
| --- | --- | --- | --- | --- | --- |
| D1 | D | p6 | “Trailing ten-year annualized changes in core CPI” | p6 Exhibit 3 可逐字定位 | match |
| D15 | D | p5–p6 | “Details of the 25 macro drivers considered for” | p5 可逐字定位；p6 仅列 10 项，差额 15 项属实 | match |
| F2 | F | p4、p14 | “we use K-means clustering to categorize market risk regimes” | p4 可定位；p14 有 K-Means 最小化公式 | match |
| F6 | F | p6–p7 | “They measure financial turbulence as:” | p7 可定位，随后为逆协方差二次型 | match |
| F11 | F | p6 | “1/3 of stocks with the lowest price-to-book ratio” | p6 Exhibit 4 可逐字定位 | match |
| B1 | B | p5 | “starts on March 1987 and ends in March 2023” | p5 可定位，紧随 433 monthly observations | match |
| B8 | B | p9 | “Accuracy (cross-validation five folds)” | p9 Exhibit 8 可逐字定位，正文另有 time series split | match |
| R1 | R | p8–p9 | “most our data (77.5%) falls under the normal market risk regime” | p9 可定位，18.7% 与 3.8% 同段出现 | match |
| R2 | R | p9 | “Accuracy Rate of Stacking Classification Mode” | p9 Exhibit 8 标题可逐字定位 | match |
| R4 | R | p10 | “Cross Correlation throughout the Entire Sample Period” | p10 Exhibit 10 标题及 6×6 矩阵可定位 | match |
| R8 | R | p11 | “Feature Importance within Each Market Risk Regime” | p11 Exhibit 14 标题及 12 个数值可定位 | match |
| R10 | R | p13 | “Compound Return with Different Approaches” | p13 Exhibit 17 标题、曲线及 4×7 表可定位 | match |
| SA1 | SA | p9 | “we applied the time series split approach during cross-validation” | p9 正文可逐字定位 | match |
| SA3 | SA | p11 | “a robust historical out-of-sample testing framework” | p11 Portfolio Simulation Section 可逐字定位 | match |
| SA4 | SA | p4 | “using equally weighted factors and a business cycle-only approach as benchmarks” | p4 文章结构段可逐字定位 | match |

结论：抽查 15 条，覆盖 D/F/B/R/SA 五类，其中 R 类 5 条；`match=15`、`mismatch=0`，未发现幻觉引用。

## 遗漏清单

| ID | 检查项 | severity | 证据定位 | 一句依据 | 处置建议 |
| --- | --- | --- | --- | --- | --- |
| SA-A01 | C5 | critical | `workspace/r004_all_a_style_box/spec/tables_extracted.md:3-4,22-47`；PDF p9–p13 | 文件声称仅 2 页含 4 表，R2、R3、R7、R8、R9、R10 六张 PDF 数值表整表未提取，属于 C5 基准表缺失。 | 重新提取或人工补齐六张表，并保留 PDF 页码与行列。 |
| SA-A02 | C5 | critical | `workspace/r004_all_a_style_box/spec/tables_extracted.md:22-47`；PDF p10 Exhibit 10–11 | R4–R6 三个 6×6 相关矩阵在表格提取文件中均无列名/行名且缺 Value 首行，只保留 5 个数据行，属于少行少列。 | 补齐三张矩阵的 6 个列名、6 个行名、Value 首行及空白上三角。 |

## 审计结论

- 遗漏清单条目数：2（critical 2 / major 0 / minor 0）。
- C6 抽查命中率：15 / 15。
- 已检查维度：
  - C1：PDF Exhibit 1–17 连续，独立重算 `fig_max=17`、`tbl_max=0`，与声明一致。
  - C2：18/18 页逐页扫描完成，密集数值/公式页均有要素或内容类型覆盖。
  - C3：中文触发词与英文等价词均已检索，命中均有 SA/F/R 关联或背景/排除说明。
  - C4：两阶段、433 月、25=10+15 宏观驱动、3 状态、6 因子、5 折、4 周期、4 方法及 D/F/B/R/SA 计数均独立重算一致。
  - C5：R1–R10 已按 PDF 逐格终审，spec 数值全部一致；`tables_extracted.md` 存在六张 R 表整表缺失及三张矩阵少行少列，构成 critical。
  - C6：15 条跨 D/F/B/R/SA 引用回查全部 match，R 类 5 条，无幻觉引用。
- A1 / 全 A 主线透明性：15 个未披露宏观驱动保持 `infeasible`，A1 保持 `blocked`；plan 明示该未消除缺口不进入中国全 A 2×2 实验主线，范围边界透明。

**verdict**: fail
