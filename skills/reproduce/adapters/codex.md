# Codex 宿主适配卡

进入 `/reproduce` 时若 Codex 协作代理能力可用，设置：

```text
HOST=codex
EXTERNAL_ENGINE=claude
EXTERNAL_ENGINE_STATE=claude_external
```

## 角色派发

- 优先使用项目 `.codex/agents/*.toml` 中的同名量化角色。
- 当前任务尚未加载 setup 新安装的命名角色时，派通用子代理并在任务消息中附对应 `agents/quant-*.md` 的完整正文；盲审任务必须使用无历史上下文的新子代理。
- 子代理不嵌套派发、不调用 skill、不修改 `state.json`。并行只由主会话发起。

## 异构外审

正式外审通过 `tools/external_review.py --engine claude` 调用 Claude Code CLI。执行器把工具面限制为 `Read,Glob,Grep`，不允许外部审查修改仓库。

## 同宿主降级

Claude CLI 不可用时，派无历史上下文的 Codex 通用子代理执行已经填充的外审 prompt：只读输入合同文件，禁读主会话叙事、agent 完成汇报和 `audit_responses.md`。主会话把其完整结果写入原 `*_external.md` 路径，台账记 `engine=same_host_fallback` 和失败原因，可信度评级封顶 B。

## 并行

使用 Codex 协作代理并遵守共享文件隔离；同批输出文件集不得相交。等待全部任务返回后才进行门禁和状态写入。
