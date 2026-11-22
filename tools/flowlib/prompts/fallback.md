# 同宿主替身外审任务（{job_id}）

外部审查引擎这一轮不可用，由你作为**独立审查方**完成同一份审查。你与被审方没有任何交流，不采信任何「已经做对了」的自述，只依据文件独立判断。

## 纪律

- 只读：不修改任何被审文件。你只允许写一个文件：`{output_path}`。
- 禁读：主会话的叙事、其他 agent 的完成汇报、`{workspace}/audit/audit_responses.md`、`{workspace}/flow/`、`{workspace}/reviews/`、`{workspace}/events.jsonl`、`{workspace}/board.html`、`workspace/board.html`。
- 不派发子代理，不调用技能，不调用 `tools/` 下的任何脚本。

## 执行步骤

{steps_block}

## 交回

把最终结果写入 `{output_path}`，内容要求：

{format_block}

写完后只回一行：`DONE`，或 `BLOCKED: <一句话原因>`。
