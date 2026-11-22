"""研报复现 v3 内核的库模块（宿主无关、确定性）。

只供主会话经 tools/flow.py 调用；子 agent 不得导入。除数据体检需要 pyarrow 之外，
只依赖标准库与 pyyaml。
"""
