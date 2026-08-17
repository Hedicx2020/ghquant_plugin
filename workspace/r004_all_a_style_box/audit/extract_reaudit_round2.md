# 提取完整性复审（Round 2）

- mode：`spec`
- 审计对象：`r004_all_a_style_box`
- PDF 终审源：`reports/r003_equity_factor_timing_cn.pdf`（18 页）
- 审读分离：仅依据当前 PDF、提取/spec/coverage/ambiguities/assumptions/plan 与 Round 1 复审文件独立核验；未读取 `audit_responses`、agent 完成汇报或 `state.json`，未修改任何输入。

## 一、Round 1 findings 核销

### SA-A03：A23 将通用来源行具体分配给变量

**核销结果：cleared**

| 核查对象 | 当前内容 | 独立判断 |
| --- | --- | --- |
| PDF / report_text p5 | `report_text.md:282-285` 明示 equity/Treasury return variables 来自 Refinitiv Eikon Datastream | 第一侧证据保留 |
| PDF / report_text p7 | `report_text.md:443` 仅写 “Authors’ calculations based on data from FRED database and Factset.” | 第二侧是通用 FRED/Factset 来源行，不支持逐变量归属 |
| A23 | `ambiguities.md:231-238` 明确写出通用来源行无法分配到具体变量，并禁止把 FRED 分给 Treasury、把 Factset 分给行业收益；两侧证据并列，原美股冲突仅作 reference_only | 已删除 Round 1 所指的具体化幻觉分配 |
| AS22 | `assumptions.md:262-270` 明确“不把通用来源行中的两个供应商分配给任何具体变量”，两组证据均保留 | cleared |
| plan | `plan.md:88,201,222,243,256` 明确通用来源行不能分配到具体变量，实际实现只认本地 A 股源，冲突不参与达标 | cleared |

全量检索 `ambiguities.md`、`assumptions.md`、`plan.md`、`spec.md`，已不存在 “Treasury yield data sourced from FRED and S&P 500 sector return data sourced from Factset” 或同义的逐变量归属断言。A23 中的简写 “Source: FRED, Factset” 仅保留 PDF 通用来源集合，没有新增字段级含义。

### SA-A04：coverage 的 F9 / B1 页码未同步

**核销结果：cleared**

- `coverage_matrix.md:46`：F9 页码现为 `p4-p5`，覆盖 Exhibit 1 daily return 与 p5 monthly performance 冲突证据。
- `coverage_matrix.md:59`：B1 页码现为 `p5, p12`，覆盖正文 Mar-23 与 Exhibit 16 横轴 May-23 冲突证据。
- 两行状态、milestone 与理由未因页码修复发生越权变化。

## 二、既有问题不退化检查

### SA-A01 / SA-A02

| 项目 | 独立重算结果 | 结论 |
| --- | --- | --- |
| R1–R10 连续性 | `tables_extracted.md` 含 R1、R2、R3、R4、R5、R6、R7、R8、R9、R10，连续无缺号 | pass |
| R1 | 表头+4 项，共 5×2；与 spec 同表逐格相等 | pass |
| R2 | 表头+3 项，共 4×2；与 spec 同表逐格相等 | pass |
| R3 | 表头+4 项，共 5×2；与 spec 同表逐格相等 | pass |
| R4 | 表头+6 行，共 7×7；含 6 列名、6 行名与 Value 首行；与 PDF/spec 21 个数值一致 | pass |
| R5 | 表头+6 行，共 7×7；含 6 列名、6 行名与 Value 首行；与 PDF/spec 21 个数值一致 | pass |
| R6 | 表头+6 行，共 7×7；含 6 列名、6 行名与 Value 首行；与 PDF/spec 21 个数值一致 | pass |
| R7 | 表头+6 项，共 7×2；六项合计 100.0%，与 PDF/spec 一致 | pass |
| R8 | 表头+6 项，共 7×3；两列各合计 100.0%，与 PDF/spec 一致 | pass |
| R9 | 表头+6 项，共 7×5；24 个方向/空白格与 PDF/spec 一致 | pass |
| R10 | 表头+4 方法，共 5×7；24 个数值/空白格与 PDF/spec 一致 | pass |

结论：原 SA-A01、SA-A02 继续保持 cleared，无结构或数值退化。

### CDX-S-01 至 CDX-S-04

| 审计项 | 当前证据链 | 回归结论 |
| --- | --- | --- |
| CDX-S-01：风险状态 vs shadow rate | p4 “predict these regimes”、p9 “significant shadow rate changes”、p15 “shadow rates” 均在 F4/R2/A6 并列；A6 裁决与 plan 范围说明仍保留 | pass |
| CDX-S-02：Refinitiv vs FRED/Factset | p5 Refinitiv 与 Exhibit 通用 FRED/Factset 两侧均在 D11–D14/A23/AS22/plan 保留，且不再作逐变量分配 | pass |
| CDX-S-03：daily vs monthly | p4 Exhibit 1 与 p5 正文证据在 F9/A24 并列；plan 仅对 r004 采用四箱扣费后月度胜出频率，F9 原 ML 标签仍 out_of_scope | pass |
| CDX-S-04：Mar-23 vs May-23 | p5 样本终点与 p12 Exhibit 16 横轴证据在 B1/EX16/A25 并列；不推断 May-23 是否为有效观测 | pass |

## 三、全量完整性回归

### 1. 78 要素与 coverage

- `spec.md` 独立重算：D=29、F=21、B=14、R=10、SA=4，总计 78；ID 唯一且连续。
- `coverage_matrix.md` 独立重算：78 行；状态为 pending 14、skipped 49、infeasible 15，总计 78；ID 集合与 spec 一致。
- frontmatter `element_counts`、coverage `row_count: 78` 与正文重算一致。
- 结论：pass。

### 2. Exhibit 1–17

- 对 `report_text.md` 独立正则重算，Exhibit 标题集合为 `{1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17}`，最大编号 17，连续无缺号。
- `spec.md` 登记 EX1–EX17 共 17 行；frontmatter 为 `fig_max=17`、`tbl_max=0`。
- 结论：pass。

### 3. 页码真实性抽查

| 抽样要素 | 类别 | 页码 | 回查内容 | 判定 |
| --- | --- | --- | --- | --- |
| D1 | D | p6 | 核心 CPI 十年年化变化在 Exhibit 3 可定位 | match |
| D11 | D | p5 | Refinitiv 正文与 Exhibit 2 Factset 来源均可定位 | match |
| D12 | D | p7 | 十个 S&P 500 行业月收益与 Exhibit 5 通用来源行可定位 | match |
| D15 | D | p5–p6 | 25 个宏观驱动声明与仅 10 个可识别变量均可定位 | match |
| F4 | F | p4、p9、p15 | 风险状态目标与 shadow rate 两组冲突原文均可定位 | match |
| F9 | F | p4–p5 | daily return 与 monthly performance 两侧均可定位 | match |
| B1 | B | p5、p12 | Mar-23 正文终点与 May-23 横轴均可定位 | match |
| R2 | R | p9 | Exhibit 8 的 71%、0.753、0.721 可定位 | match |
| R4 | R | p10 | Exhibit 10 完整相关矩阵可定位 | match |
| R8 | R | p11 | Exhibit 14 的 12 个特征重要性值可定位 | match |
| R10 | R | p13 | Exhibit 17 的四方法绩效表可定位 | match |
| SA1 | SA | p9 | time series split / five-fold cross-validation 可定位 | match |
| SA3 | SA | p11 | historical out-of-sample testing framework 可定位 | match |

抽查结果：13/13 match，覆盖 D/F/B/R/SA 五类，其中 R 类 3 条；无 mismatch、无页码退化。

## 四、新 findings

无新 finding。

## 五、复审结论

- SA-A03：cleared。
- SA-A04：cleared。
- SA-A01 / SA-A02：持续 cleared。
- CDX-S-01 / 02 / 03 / 04：全部 pass，无退化。
- 78 要素与 coverage：pass。
- R1–R10 表格证据层：pass。
- Exhibit 1–17：pass。
- 页码真实性抽查：13/13 match。
- 新 findings：0。

**verdict**: pass
