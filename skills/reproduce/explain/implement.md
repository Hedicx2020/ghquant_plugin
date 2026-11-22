# implement（代码实现）

入口先重查一次数据需求。然后按难度：

- **easy**：一个 coder 一次做完全部 milestone，不做 milestone 级验证。
- **medium**：按顺序逐个 milestone 编码；上一个在验证时下一个可以开始编码（深度 1）。
- **hard**：依赖已就绪的 milestone 并行编码；每个 milestone 编码后同批派验证与实现内审。

子 agent 的输入是内核切好的任务文件（本步要素全文、相关假设口径卡、矩阵本步行、上游签名）；矩阵与假设登记簿的回填写在回执里，由内核核对后合并，所以多个验证可以同批。

## milestone 验证没过

`implement.mN.verify` 的回执写 `verify.verdict: fail`：内核带着失败清单重派该 milestone 的编码，再重新验证。若失败只是因为验证期间别的 milestone 正在改代码，用 `flow rerun … --false-fail`（见 `flow explain revise`）。

## 内审发现 critical 或 not_found

`implement.mN.audit` 回执里的 critical 或「判定: not_found」：内核带着审计文件重派该 milestone 的编码并重审。

## G-IM-1、G-IM-2、G-IM-3

`src/<id>/strategy.py`、`main.py` 不存在，或编译不过。派 `implement.gatefix`（coder）修。

## G-IM-4

状态里还有 milestone 没做完。内核按步骤表继续派；它也派不出来时开 `stuck` 检查点（依赖成环，或上一步结论没记下来）。

## G-IM-5

矩阵里有该实现的行没有「实现位置」。派 `implement.gatefix`（coder）在回执里补齐。

## milestone_done

interactive 模式下 medium / hard 每个 milestone 做完停一次。
