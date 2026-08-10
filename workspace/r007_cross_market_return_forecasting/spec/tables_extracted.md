# 表格提取（pdfplumber）

文档共 40 页。

自动检测未识别出表格；依据 PDF p36 人工逐格补录唯一编号表 Table A.1。

## Table A.1（p36）

- 原生标题: Summary of SR results across different hyperparameter settings (using the most recent U.S. pvCLCL returns to predict Chinese OPCL returns).
- 数值口径: Values are reported as mean ± standard deviation.
- 结构: 7 个方法数据行 × 8 个逻辑列（Methods、Parameters、qr1、qr2、qr3、qr4、qr5、qr6）。

| Methods | Parameters | qr1 | qr2 | qr3 | qr4 | qr5 | qr6 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LASSO | λ={1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100, 1000} | 0.848 ± 0.222 | 0.969 ± 0.247 | 1.238 ± 0.31 | 1.65 ± 0.398 | 1.821 ± 0.433 | 1.777 ± 0.424 |
| RIDGE | λ={1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100, 1000} | 1.238 ± 0.429 | 1.293 ± 0.43 | 1.437 ± 0.449 | 1.715 ± 0.51 | 1.668 ± 0.619 | 1.55 ± 0.461 |
| SVM | C={0.1, 1, 10, 100, 1000} | 0.743 ± 0.194 | 0.751 ± 0.196 | 0.782 ± 0.204 | 0.719 ± 0.188 | 1.02 ± 0.267 | 0.836 ± 0.218 |
| XGBoost | max depth={3,6,9}; learning rate={0.01, 0.1, 0.2}; n estimators={50, 100, 300} | 1.445 ± 0.224 | 1.48 ± 0.247 | 1.587 ± 0.214 | 1.539 ± 0.309 | 1.381 ± 0.401 | 0.964 ± 0.233 |
| LGBM | num leaves={10, 31, 90}; learning rate={0.01, 0.1, 0.2}; n estimators={50, 100, 300} | 1.32 ± 0.348 | 1.457 ± 0.388 | 1.541 ± 0.422 | 1.44 ± 0.485 | 1.652 ± 0.466 | 1.424 ± 0.407 |
| RF | n estimators={50, 100, 300}; max depth={5, 10, 50} | 1.481 ± 0.41 | 1.558 ± 0.422 | 1.639 ± 0.447 | 1.799 ± 0.486 | 1.747 ± 0.474 | 1.09 ± 0.351 |
| AdaBoost | max depth={1, 5, 10}; n estimators={50, 100, 300}; learning rate={0.01, 0.1, 0.2} | 1.389 ± 0.358 | 1.405 ± 0.385 | 1.549 ± 0.436 | 1.548 ± 0.419 | 1.1 ± 0.305 | 0.667 ± 0.187 |

- 注释原文: max depth is the maximum depth of a tree. learning rate is the learning rate. n estimators is the maximum number of estimators at which boosting is terminated. num leaves is maximum tree leaves for base learners in an LGBM model.
