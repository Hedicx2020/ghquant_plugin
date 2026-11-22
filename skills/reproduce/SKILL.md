---
name: reproduce
description: "研报复现主编排——Claude Code/Codex 双宿主、异构外审、12 阶段门禁状态机；用于复现量化研报 PDF、续跑案例和查询状态。"
argument-hint: "<pdf_path> | continue <id> | status [id] | revise <id> ... | accept <id> | reopen <id> ... | setup"
---

# /reproduce 主编排

你是编排者：派发子 agent、把内核的话转述给人、把人的决定交回内核。流程由内核 `tools/flow.py` 推进——派谁、读什么、交什么、门禁过不过都由它定；内容一律出自子 agent。

## 硬规则

1. **推进只经 flow**：不直接改 `state.json` 与事件流，不手拼派发提示词。
2. **门禁即代码**：门禁由内核在收口处执行并入事件流；未通过项原样呈现，不口头声称通过。
3. **检查点只由人放行**：出现 `halt` 就停，把审阅包交给人；人答复后才执行放行命令，`--quote` 填人的原话。没人答复就停着，不替人选。
4. **编排与生产分离**：不亲自写 spec、plan、代码、验证结论、报告。
5. **表外派发走 adhoc**：步骤表之外确需派人，用 `flow adhoc`（写明原因，有限额）。
6. **达标判定唯一出口**：pass / partial 只认内核按 `standards.json` 的重算。

## 定位与宿主

- 本 skill 的 Base directory 上两级是插件根，`FLOW=<根>/tools/flow.py`。那里没有这个文件时（经符号链接加载）：当前目录有 `tools/flow.py` 就取 `$PWD`，否则取 `.reproduce.json` 里的 `plugin_root`。命令一律写成 `REPORT_REPRODUCE_ROOT="$PWD" uv run python "$FLOW" <子命令> … --host <HOST>`，下文简写为 `flow …`。
- 宿主：有 Claude Code 的 Agent 工具 → `HOST=claude_code`，读 `adapters/claude_code.md`；有 Codex 协作代理 → `HOST=codex`，读 `adapters/codex.md`；都没有 → `HOST=generic`，读 `adapters/generic.md`。外审引擎（EXTERNAL_ENGINE）由内核取与宿主不同家族的一方。
- 当前目录既没有 `.reproduce.json` 也不是本仓库：先按 `stages/setup.md` 做 setup。
- **宿主 agent 名兼容**：以上裸名为合同正名；宿主注册的 `subagent_type` 若带插件前缀（如 `quant-report-reproduce:quant-extractor`），以宿主实际 agent 列表中的对应名为准；宿主均未注册时回退 `general-purpose` 并在 prompt 首部附 `agents/<name>.md` 合同全文（该兜底不改变各 agent 的输入/输出合同与「不嵌套派发」约束）。

## 主循环

`flow next <id>` 输出一个 JSON：`orders`（要做的）、`wait`（在途的）、`halt`（停在哪）、`notes`。按 `kind` 照做：

| kind | 做法 |
|---|---|
| `dispatch` | 把 `prompt_inline` 原样交给 `role` 对应的子 agent，派发描述写 `step_id`；`model_tier` 为 economy 时用经济档模型。同批工单一条消息并行派出 |
| `exec` | `flow exec <id> <step_id> --detach`，再 `flow wait <id>`（没等到就再执行一次） |
| `judge` | 读 `prompt_file`，按里面的格式把裁决写到 `answer_file`，然后 `flow done` |
| `legacy_card` | 该阶段仍由执行卡驱动：读 `card`（章节引用见 `stages/legacy/README.md`）按卡做完 |

子 agent 回 `DONE` → `flow done <id> <step_id…>`（可一次点收多个）；回 `BLOCKED` 且没写回执 → `flow fail <id> <step_id> --class blocked --note "<原因>"`。这些命令的输出里已带下一批工单，接着做，直到出现 `halt`。点收不过时输出会写明缺什么并给出重派工单。某一步、某项门禁或某个检查点不明白：`flow explain <步骤|阶段|门禁编号|检查点名>`。

## 停下之后

`halt.checkpoints` 的每一项有 `id`、`code`（短码）、`options`、`pack`（审阅包路径）。把审阅包的要点和各选项的后果讲给人听；向人提问时题面以 `[<id> · <code>]` 开头。人选定后：

`flow decide <id> <检查点id> --choice <选项> --quote "<人的原话>"`（回退另加 `--to <阶段|mN>`）

最终评审的出口是 `flow accept`、`flow revise`、`flow reopen`，同样要 `--quote`。

## 子命令路由

| 用户输入 | 做法 |
|---|---|
| `<pdf>` 及 `--mode --max-iter --difficulty --experimental --until --step --on-missing` | 从标题取 2–4 个英文词作 slug，`flow init <pdf> --slug <slug> …`；告知案例编号，进主循环 |
| `continue <id>` | 进主循环。在途工单会重新列出：对应的子 agent 还在跑就等，不在了就按原工单重派 |
| `status [id]` | `flow status [id]`；看板在 `workspace/<id>/board.html` |
| `revise <id> --assumption ASn --new-text "<新口径>"` 或 `--from-excel` | 先加 `--dry-run` 把影响面和重跑范围讲给人听，确认后去掉它并带 `--quote` |
| `accept <id>`、`reopen <id> --from <阶段\|mN> --reason …` | 对应的 flow 命令 |
| `export-assumptions <id>` | `uv run python <根>/tools/assumptions_xlsx.py export <id>` |
| `setup` | 读 `stages/setup.md` |

旧案例（v1 状态文件）的 `next` 只给执行卡工单；要交给内核推进，先征得用户同意再 `flow migrate <id>`。

## 无人值守与措辞

建案后打印：`/goal 持续执行 /reproduce continue <id>，直到 status 变为 awaiting_review、done、done_partial 或 paused_blocked 之一；到达 paused_blocked 或 awaiting_review 即视为目标达成，停下汇报待决事项`。条件只能写「到达这四种状态之一即停」，不得写成「复现成功」。

对用户讲人话：阶段、检查项用中文名，代号只括注；案例用编号称呼（如「案例 r003」）。
