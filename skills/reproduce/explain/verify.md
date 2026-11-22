# verify（运行验证）

一步：`verify.main`，验证者亲自运行 `main.py`，整批重出结果目录，逐项对数写 `comparison.json`、`verify_report.md` 与证据清单。对比总表与产物清单由内核从机器产物生成后嵌入文书，不手抄。达标与否由内核按 `templates/standards.json` 重算，不采信文件里自述的 pass。

## G-VF-1、G-VF-2

程序没跑通（`run_log.md` 没有 exit=0），或 `comparison.json` 没有、解析不了。先派 `verify.gatefix`（coder）修代码，再重派 `verify.main`。

## G-VF-3

有指标超出容差。**只有这一项不过不算失败**：验证阶段照常收口，结论先记为部分达标，下一步进入迭代。不要重派验证，也不要让任何人去「调到达标」。

## G-VF-4、G-VF-5

模板要求的图表或 Excel 不齐（图表要大于 15KB）。重派 `verify.main` 补齐。

## G-VF-6

结果比代码旧：`src/` 在结果产出之后又被改过。结果必须整批重出，重派 `verify.main`；不要只补跑一部分，也不要改文件时间。

## G-VF-7

矩阵里 core / support 行的「验证结果」还有空的。重派 `verify.main` 在回执里补齐。

## G-VF-8

真实结果的数据清单里出现了 mock 文件，或试跑标记（`data_mock/ACTIVE`）还在：试跑没有收干净。内核重派 `verify.main` 整批重出；覆盖目录里还留着模拟文件时会连续不过并熔断，交给人确认真实数据是否到位（`flow explain data`）。

## verify_done

interactive 模式下验证收口后停一次。
