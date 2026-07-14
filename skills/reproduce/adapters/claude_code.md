# Claude Code 宿主适配卡

进入 `/reproduce` 时若 Claude Code 的 Agent/Task 能力可用，设置：

```text
HOST=claude_code
EXTERNAL_ENGINE=codex
EXTERNAL_ENGINE_STATE=codex_external
```

## 角色派发

- 使用 Claude Code Agent 工具，`subagent_type` 取 `quant-extractor`、`quant-planner`、`quant-auditor`、`quant-coder`、`quant-verifier`、`quant-diagnoser`、`quant-oos-analyst`、`quant-reporter`。
- economy 模式的模型覆盖继续按主技能执行。
- 子 agent 不得再派 agent、调用 skill 或修改 `state.json`。

## 异构外审

正式外审通过 `tools/external_review.py --engine codex` 调用 Codex CLI。执行器返回 `success` 才可读取目标审查文件；其他状态按阶段卡降级链处理。

## 同宿主降级

Codex CLI 不可用时，派 `general-purpose` Claude 独立任务执行已经填充的外审 prompt：只读输入合同文件，禁读主会话叙事、agent 完成汇报和 `audit_responses.md`，不派发 agent、不调 skill。输出写入原 `*_external.md` 路径，台账记 `engine=same_host_fallback` 和失败原因，可信度评级封顶 B。

## 并行

只执行主技能列出的五个并行点；会写同一文件的 Agent 不得同批，所有 `state.py` 写操作串行。
