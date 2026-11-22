# Claude Code 宿主适配卡

```text
HOST=claude_code
EXTERNAL_ENGINE=codex        # 内核自动取与宿主不同家族的一方；台账里的引擎状态名是 codex_external
```

所有 flow 命令带 `--host claude_code`。

## 把工单变成派发

| 工单字段 | 用法 |
|---|---|
| `agent` | Agent 工具的 `subagent_type`。宿主注册名带插件前缀时用带前缀的那个（如 `quant-report-reproduce:quant-coder`）；宿主没有注册这个角色，或工单没有 `agent`（`role` 是 `general-purpose`），用 `general-purpose` |
| `step_id` | Agent 工具的 `description`，原样填写——内核按它对账用量 |
| `prompt_inline` | Agent 工具的 `prompt`，原样填写，不追加背景说明 |
| `model` | 有这个字段才传 `model`（经济档） |

- 同一次 `next` 返回的多张 `dispatch` 工单在一条消息里并行派出；派发一律用新的子 agent，不用带主会话历史的 fork。
- 子 agent 在后台运行，完成时宿主会通知；等通知，不轮询、不去读它的会话记录。通知里的结论只看首行是 `DONE` 还是 `BLOCKED`，其余以 `flow done` 的点收结果为准。
- 续跑时 `next` 重新列出的在途工单：对应的子 agent 还在运行就继续等；已经不在了，按原工单重派（步骤编号不变）。

## 后台外审

`exec` 工单：先执行工单里的 `command`（带 `--detach`，立即返回），再执行 `flow wait <id>`。`wait` 最多等 540 秒，没等到会如实返回在途状态，再执行一次即可；Bash 的超时设到 600000 毫秒。外审失败后内核会自己降级：先给一张 `general-purpose` 的同宿主盲审工单（台账记 `same_host_fallback`，评级封顶 B），那一步也交不出来才记为跳过。

## 向人提问与凭据

- 用 AskUserQuestion，每个检查点一题，题面以 `[<检查点 id> · <短码>]` 开头，选项用 `halt.checkpoints[].options` 的标签原文。
- 插件的钩子会记下人的回答和人直接输入的话：题面带着短码，或人输入的话里含短码或 `--quote` 引用的原话，这次放行就是钩子级凭据；否则降为自述级，看板和报告附录会标出来。
- 人久未回答时不替人选，保持停下。

## 钩子

插件根的 `hooks/hooks.json` 随插件自动加载，要求 `python3` 在 PATH 上（Windows 上没有 `python3` 命令时钩子不生效，流程照常，只是少了这层护栏）。

- 读文件前的护栏：子 agent 读自己步骤禁读清单里的路径会被拒绝，提示里写着该怎么取（上下文包或 `flow get`）。被拒不要绕路，也不要替它把内容贴进提示词。
- `state.json`、事件流、「人在场」记录不允许直接写入，改状态只经 flow 命令。
