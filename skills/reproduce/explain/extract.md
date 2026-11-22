# extract（研报提取）

一步：`extract.main`，提取者读 PDF 与转写文本，产出 `spec/spec.md`、`spec/coverage_matrix.md`、`spec/ambiguities.md`。只有这一步和规格内审可以读研报原文转写。

任何检查项不过，内核把门禁原文写进重派原因，重派 `extract.main`；修了 2 轮仍不过开检查点。

## G-EX-2、G-EX-3

spec 的 frontmatter 解析不了或必填字段空。重派提取者按模板补。

## G-EX-4

三处计数对不上：正文里的要素标题块、frontmatter 的 `element_counts`、覆盖矩阵的数据行。通常是加了要素没同步矩阵。重派时门禁原文会列出各自的数。

## G-EX-5

有要素块缺「页码」或「原文」行。页码引用制是提取的底线，缺了就重派。

## G-EX-6

没有任何 R 类要素（研报的结果数值）。没有可对齐的结果就无从验证：重派后仍然没有，说明这份研报不给数值结果，修复轮数用完后停在检查点，由人决定是否用实验模式或放弃。

## G-EX-8

图表登记清单与要素计数对不上，或最大编号超过研报声明的图表数。重派提取者核对图表编号连续性。

## spec_final

interactive 模式下 spec 收口后停一次，见 `flow explain spec_final`。
