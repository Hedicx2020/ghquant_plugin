# 规格修复第1轮变更说明

修复日期：2026-07-18。范围仅限提取层文档，未修改`plan.md`或`state.json`。

| 审计意见 | 定向修复 | 产物定位 |
| --- | --- | --- |
| CDX-S-01 | 补录Stacking第二层Logistic Regression的交叉熵损失，并保留最终sigmoid组合式 | `spec/spec.md` F4 |
| CDX-S-02 | 逐式补录单树特征重要性、树内归一化、随机森林汇总三层公式与符号定义 | `spec/spec.md` F7 |
| CDX-S-03 | 在F4、R2逐字保留`predicting significant shadow rate changes`，并双向关联A6 | `spec/spec.md` F4/R2；`spec/ambiguities.md` A6 |
| SA-A01 | 对未公开的宏观驱动第11–25项新增D15–D29占位；均标记`missing`、`nonrecoverable`，不虚构名称或数值 | `spec/spec.md` D15–D29；`spec/coverage_matrix.md` D15–D29 |
| SA-A02 | 从PDF p8–p13人工重建R1–R10，补全标题、页码、行列名、全部数值及原始空白 | `spec/tables_extracted.md` R1–R10 |

计数同步：D由14增至29；F21、B14、R10、SA4不变；要素总数由63增至78；EX1–EX17不变。
