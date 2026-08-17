# 提取完整性复审（Round 1）

- mode：`spec`
- 审计对象：`r004_all_a_style_box`
- PDF 终审源：`reports/r003_equity_factor_timing_cn.pdf`（18 页）
- 复审范围：当前 PDF、`report_text.md`、`tables_extracted.md`、`spec.md`、`coverage_matrix.md`、`ambiguities.md`、`plan.md`、`audit/spec_fix_round1.md`、`audit/plan_sync_after_spec_fix.md`。
- 审读分离：未读取 `audit_responses`、agent 完成汇报或 `state.json`；修复记录中的完成声明均未直接采信，以下结论来自当前文件与 PDF 的独立复核。

## 一、原 SA-A01 / SA-A02 核销

### SA-A01：R2、R3、R7–R10 整表缺失

**核销结果：clear**

独立解析 `tables_extracted.md` 得到连续标题 R1–R10，逐表结构如下：

| R | 当前表结构（不含分隔行） | 与 spec 同 R 表逐格比较 | PDF 终审 | 结论 |
| --- | --- | --- | --- | --- |
| R1 | 5 行×2 列（表头+4 项） | equal | p8–p9 的 K=3、77.5%、18.7%、3.8% 一致 | clear |
| R2 | 4 行×2 列（表头+3 项） | equal | p9 的 71%、0.753、0.721 一致 | clear |
| R3 | 5 行×2 列（表头+4 项） | equal | p9 的四个特征重要性值一致 | clear |
| R4 | 7 行×7 列（表头+6 行） | equal | p10 Exhibit 10 的 21 个下三角/对角数值一致 | clear |
| R5 | 7 行×7 列（表头+6 行） | equal | p10 Exhibit 11 Normal 的 21 个数值一致 | clear |
| R6 | 7 行×7 列（表头+6 行） | equal | p10 Exhibit 11 Correction 的 21 个数值一致 | clear |
| R7 | 7 行×2 列（表头+6 项） | equal | p10 六项胜出频率一致，合计 100.0% | clear |
| R8 | 7 行×3 列（表头+6 项） | equal | p11 两列各 6 个值一致，各列合计 100.0% | clear |
| R9 | 7 行×5 列（表头+6 项） | equal | p12 的 24 个正负号/空白格一致 | clear |
| R10 | 5 行×7 列（表头+4 方法） | equal | p13 的 24 个数值/空白格一致 | clear |

证据定位：`tables_extracted.md:8-133`；`spec.md:517-668`；PDF p8–p13。

### SA-A02：R4–R6 矩阵缺表头、行名与 Value 首行

**核销结果：clear**

- R4 位于 `tables_extracted.md:40-53`，列头为 Value/Growth/Momentum/Low Vol/Quality/Small，行名同序，Value 首行为 `1,n/a,n/a,n/a,n/a,n/a`。
- R5 位于 `tables_extracted.md:55-68`，具备相同 6 个列头、6 个行名与 Value 首行。
- R6 位于 `tables_extracted.md:70-83`，具备相同 6 个列头、6 个行名与 Value 首行。
- 独立解析确认三张矩阵每行连同行名均为 7 列，每张均为表头+6 数据行；上三角空白统一记 `n/a`，与 PDF 空白格规则一致。

## 二、CDX-S-01 至 CDX-S-04 冲突复核

| 审计项 | PDF / report_text 独立证据 | 当前 spec / ambiguity / plan 表达 | 复审结论 |
| --- | --- | --- | --- |
| CDX-S-01：市场风险状态目标 vs shadow rate 目标 | p4 写分类器 “predict these regimes”；p9 写 “predicting significant shadow rate changes”；p15 写 “predicting shadow rates” | `spec.md:304-314,531-544` 三处并列；`ambiguities.md:53-65` 的 A6 保留两种解释并说明解释1占优、原模型 out_of_scope；`plan.md:88,243,256` 保留冲突且不用于中国主线达标 | pass |
| CDX-S-02：Refinitiv vs FRED/Factset 来源 | p5 写 equity/Treasury return variables from Refinitiv；Exhibit 2 写 S&P 500 price from Factset；Exhibit 5 与 10–17 来源行写 FRED database and Factset | `spec.md:122-160` 并列两套来源；A23 和 plan 均保留冲突，并将原美股来源判为 reference_only、实现限定本地 A 股源 | 冲突显式化 pass；A23 有新证据引用问题，见 SA-A03 |
| CDX-S-03：daily return vs monthly performance 标签频率 | p4 Exhibit 1 写 “Label by comparing factors daily return”；p5 写 “evaluate the monthly performance of each factor” | `spec.md:344-351` 并列；`ambiguities.md:241-252` 的 A24 明确只对 r004 采用四箱扣费后月收益统计，F9 原 ML 标签仍 out_of_scope；`plan.md:88,201-203,212,240-243` 同步 | pass |
| CDX-S-04：Mar-23 样本截止 vs May-23 横轴 | p5 写样本 starts March 1987 and ends March 2023；p12 Exhibit 16 最右横轴刻度可见 May-23 | `spec.md:429-435,689` 并列；`ambiguities.md:254-265` 的 A25 明确不推断 May-23 是否为有效观测，只对 r004 采用用户指定冻结/OOS；`plan.md:88,201-203,243` 同步 | pass |

### A6 / A23–A25 裁决透明性

| 歧义 | 候选解释是否保留 | 裁决是否限定 r004 范围 | 是否保留原文冲突 | 结论 |
| --- | --- | --- | --- | --- |
| A6 | 是；风险状态与 shadow rate 两种解释并列 | 是；解释1占优且原 ML 整体 out_of_scope，登记 AS5 | 是 | pass |
| A23 | 是；Refinitiv、Exhibit 来源、分层来源三种解释并列 | 是；不裁定原文唯一来源，仅限定实现用本地源，登记 AS22 | 是 | 透明性 pass；一条“Exhibit原文”不属实，见 SA-A03 |
| A24 | 是；日频、月频、日聚合月三种解释并列 | 是；仅 r004 月度四箱胜出频率，F9 继续 out_of_scope，登记 AS23 | 是 | pass |
| A25 | 是；Mar-23、May-23 有效观测、May-23 仅刻度三种解释并列 | 是；不推断原文端点，只采用 r004 冻结/OOS，登记 AS24 | 是 | pass |

## 三、完整性回归检查

### 1. 要素与 coverage 计数

- 独立重算 `spec.md`：D=29、F=21、B=14、R=10、SA=4，总数 `29+21+14+10+4=78`；ID 连续且无重复。
- `coverage_matrix.md` 独立重算为 78 行，ID 集合与 spec 一致；状态计数为 pending 14、skipped 49、infeasible 15，总数 78。
- frontmatter `element_counts` 与 `coverage_matrix.md` 的 `row_count: 78` 均一致。
- 计数结论：pass；未退化。

### 2. Exhibit 1–17

- 对 `report_text.md` 独立正则重算，Exhibit 标题集合为 `{1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17}`，最大编号 17，连续无缺号。
- `spec.md:674-690` 登记 EX1–EX17 共 17 行；frontmatter 为 `fig_max=17`、`tbl_max=0`。
- Exhibit 结论：pass；未退化。

### 3. 页码真实性抽查

| 抽样要素 | 类别 | 页码 | 当前摘录/关键证据 | PDF / report_text 回查 | 判定 |
| --- | --- | --- | --- | --- | --- |
| D1 | D | p6 | “Trailing ten-year annualized changes in core CPI” | p6 Exhibit 3 可逐字定位 | match |
| D12 | D | p7 | “monthly returns from ten S&P 500 sectors” | p7 正文可定位，10 个行业逐项列示 | match |
| D15 | D | p5–p6 | “Details of the 25 macro drivers considered for” | p5 可定位；p6 仅列 10 项，15 项未披露差额仍属实 | match |
| F4 | F | p4、p9、p15 | 风险状态目标与 shadow rate 两组表述 | 三页均可定位 | match |
| F9 | F | p4–p5 | daily return / monthly performance | p4 Exhibit 1 与 p5 正文均可定位 | match |
| B1 | B | p5、p12 | March 2023 / May-23 | p5 正文与 p12 Exhibit 16 横轴均可定位 | match |
| R2 | R | p9 | “Accuracy Rate of Stacking Classification Mode” | p9 Exhibit 8 及 71%/0.753/0.721 可定位 | match |
| R4 | R | p10 | “Cross Correlation throughout the Entire Sample Period” | p10 Exhibit 10 完整矩阵可定位 | match |
| R8 | R | p11 | “Feature Importance within Each Market Risk Regime” | p11 Exhibit 14 的 12 个值可定位 | match |
| R10 | R | p13 | “Compound Return with Different Approaches” | p13 Exhibit 17 的 4×7 表可定位 | match |
| SA1 | SA | p9 | “time series split approach during cross-validation” | p9 正文可定位 | match |
| SA3 | SA | p11 | “a robust historical out-of-sample testing framework” | p11 Portfolio Simulation Section 可定位 | match |

抽查结论：12/12 match，覆盖 D/F/B/R/SA 五类，其中 R 类 3 条；未发现 spec 要素页码引用退化。

## 四、新 findings

| ID | severity | 证据定位 | 一句依据 | 处置建议 |
| --- | --- | --- | --- | --- |
| SA-A03 | critical | `workspace/r004_all_a_style_box/spec/ambiguities.md:233-237`；PDF p7；`workspace/r004_all_a_style_box/spec/report_text.md:400-443` | A23 将 “Treasury yield data sourced from FRED and S&P 500 sector return data sourced from Factset.” 标成 Exhibit 5 原文，但 PDF Exhibit 5 实际只写 “Authors’ calculations based on data from FRED database and Factset.”，没有把 Treasury 与 sector 分别归属两来源；这是新增的具体化幻觉引用。 | 将 A23 的 Exhibit 5 引文改回 PDF 原句；冲突仍可据 p5 Refinitiv 与 Exhibit 通用 FRED/Factset 来源行保留，禁止补推具体字段归属。 |
| SA-A04 | minor | `workspace/r004_all_a_style_box/spec/spec.md:344-351,429-435`；`workspace/r004_all_a_style_box/spec/coverage_matrix.md:46,59` | spec 已把 F9 页码扩为 p4–p5/p9–p10、B1 扩为 p5/p12，但 coverage 页码仍分别缺 p4、p12，新增冲突证据虽在理由中引用，页码定位未同步。 | coverage 的 F9 补 p4、B1 补 p12；不改变状态或 milestone。 |

## 五、复审结论

- 原 SA-A01：clear。
- 原 SA-A02：clear。
- CDX-S-01：pass。
- CDX-S-02：冲突显式化 pass，但新增具体化幻觉引用 SA-A03。
- CDX-S-03：pass。
- CDX-S-04：pass。
- A6/A23–A25 裁决边界：均显式且限定 r004；A23 的单条证据引文需修正。
- 78 要素计数：pass。
- Exhibit 1–17：pass。
- 页码真实性抽查：12/12 match，未退化。
- 新 findings：2（critical 1 / major 0 / minor 1）。

**verdict**: fail
