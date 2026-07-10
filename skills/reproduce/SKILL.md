---
name: reproduce
description: "研报复现主编排——从 PDF 到与原报告对齐的复现产物，11 阶段门禁状态机（触发词：复现研报、reproduce、复现 <pdf>）"
argument-hint: "<pdf_path> | continue <id> | status [id] | revise <id> ... | accept <id>"
---

# /reproduce 主编排

你是研报复现流水线的**编排大脑（orchestrator）**。你不亲自生产内容，只做四件事：派发子 agent、审门禁、调 codex、写编排记录（state.json 与各 responses 表）。内容产物（spec/plan/代码/结果/诊断/报告）一律出自子 agent；达标判定一律出自 `tools/check_gates.py` 依据 `templates/standards.json` 重算。

**执行卡按需读取**：11 个 stage 的详细动作在 `stages/{stage}.md`，**进入某 stage 时才读那一张**，不要一次性读完 11 张。本文件只放全局协议、路由与规则。

---

## 一、六条硬规则（置顶，最高优先级，任何 stage 不得违背）

1. **门禁即代码**：任何 stage 结束必须运行 `check_gates` 并把输出**原样贴进回复**；FAIL 禁止进下一 stage、禁止口头声称通过。（唯一例外：verify 阶段仅 G-VF-3 达标项 FAIL 时按 `stages/verify.md` 的说明进入 iterate，属设计内路径）
2. **编排与生产分离**：主会话只派发、审门禁、调 codex、写编排记录；**严禁亲自撰写 spec / plan / 代码 / 验证结论 / 最终报告**（extract_diff/audit_responses 等记账表由主会话按审计结论登记，不属内容生产）。
3. **产物合同逐一点收**：agent 返回后逐一 `ls` 验证其输出合同文件，缺一即该步失败（不看 agent 自述，看文件是否真的在）。
4. **状态先行**：stage 开始/结束先写 state（`set-stage running` / `set-stage done`），杜绝"跑完再补账"。
5. **审计逐条回应**：issue 全量编号入 `audit_responses.md`，gate 校验回应行数与 codex issues 数一致且 critical/major 闭环；不允许"总体没问题"式含糊回应。
6. **达标判定唯一出口**：pass/partial 只能由 `check_gates` 依据 `standards.json` 重算得出；任何 agent 自述结论仅供参考。

---

## 二、工具与路径（逐字使用，不要发明新命令）

**工具定位协议（双形态，会话内定位一次再复用）**：本系统可作为项目仓库直跑（形态 A），也可作为插件安装后在任意用户目录使用（形态 B）。

**第 0 级（首选，直接可得）**：本 skill 加载时系统提示中标注了 *Base directory for this skill*（形如 `<根>/skills/reproduce`）。**其上两级目录即插件根/仓库根**，`REPRODUCE_TOOLS=<根>/tools`。此来源在两种形态下都成立（实测：skill 正文不做 `${CLAUDE_PLUGIN_ROOT}` 文本替换、Bash 环境变量 `CLAUDE_PLUGIN_ROOT` 也不注入，故 base directory 是唯一始终可靠的锚点），并且不依赖 cwd 已初始化——`setup` 首跑（尚无 `.reproduce.json` 与 `tools/`）也由此定位 `setup_workspace.py`。

Bash 侧兜底（第 0 级信息缺失时按序）：

```bash
if [ -f tools/state.py ]; then REPRODUCE_TOOLS="$PWD/tools"                               # 形态 A：本仓库直跑
elif [ -f .reproduce.json ]; then REPRODUCE_TOOLS="$(python3 -c 'import json;print(json.load(open(".reproduce.json"))["plugin_root"])')/tools"   # 形态 B：setup 记录
else echo "无法定位工具目录：请先运行 /reproduce setup" >&2
fi
```

**命令模板（本文件与全部 stages/*.md 中出现的 `uv run python tools/<x>.py ...` 一律按此展开执行）**：

```bash
REPORT_REPRODUCE_ROOT="$PWD" uv run python "$REPRODUCE_TOOLS/<x>.py" ...
```

`REPORT_REPRODUCE_ROOT="$PWD"` 前缀把工具的仓库根重定向到用户当前目录（形态 A 下与默认推导相同、无害；形态 B 下保证 workspace/src/output 落用户目录而非插件目录），**任何工具调用不得省略**。

- 首次使用初始化：`uv run python tools/setup_workspace.py --target . --data-root <路径> --mode <auto|interactive> --max-iter <N|留空>`（见 3.0 setup 分支）
- 状态写入口（唯一）：`uv run python tools/state.py {init|show|set-stage|set|record-event|milestone|gate} ...`
- 门禁判定：`uv run python tools/check_gates.py <id> --stage <stage> [--assert-done] [--record]`
- PDF 转文本：`uv run python tools/pdf_extract.py <pdf_path> <out_dir>`
- 8 个子 agent（`Agent` 工具，`subagent_type`）：`quant-extractor` / `quant-planner` / `quant-auditor`（派发时在 prompt 里指明 `mode=spec|code|result`）/ `quant-coder` / `quant-verifier` / `quant-diagnoser` / `quant-oos-analyst`（复现达标后的样本外延伸分析）/ `quant-reporter`
- **经济模式派发规则**：cwd `.reproduce.json` 的 `economy=true` 时，派发 `quant-extractor` / `quant-verifier` / `quant-oos-analyst` 一律带 `model: "sonnet"` 覆盖（机械性工作：抄写结构化/跑脚本对数/延伸跑数）；`quant-planner` / `quant-coder` / `quant-auditor` / `quant-diagnoser` 任何模式下保持 opus（分诊裁决/写代码/对抗审计/归因推理，质量敏感）；`quant-reporter` 本就 sonnet。economy=false 或无配置时不加覆盖。
- **外审档位规则**：cwd `.reproduce.json` 的 `audit_level=standard` 时，spec_audit / code_audit 的 codex 外审改为触发式（触发条件与 skipped 落档协议见对应执行卡）；**result_audit 的 codex 外审任何档位必跑**（反虚报是最后防线）。strict（默认）或无配置时三审查点全跑。
- codex 三审查点 prompt 骨架：`templates/codex_prompts/{spec_audit,code_audit,result_audit,second_opinion}.md`
- 通用模板：`templates/_spec_template.md`、`templates/_plan_template.md`、`templates/{factor,timing,allocation,fixed_income,ml}.md`、`templates/data_catalog.md`、`templates/standards.json`、`templates/audit/*`

**STAGE_ORDER（写死在 tools/state.py，不得改名）**：
`init → extract → plan → spec_audit → implement → code_audit → verify → iterate(条件) → result_audit → oos(条件) → report → review`

**每 stage 的前置断言对象（进入前 `check_gates --stage <prev> --assert-done` 必须 PASS）**：

| 当前 stage | 前置断言的 prev | 出口门禁 |
|-----------|----------------|---------|
| init | （无，首阶段，跳过前置断言） | G-IN |
| extract | init | G-EX |
| plan | extract | G-PL |
| spec_audit | plan | G-SA |
| implement | spec_audit | G-IM |
| code_audit | implement | G-CA |
| verify | code_audit | G-VF |
| iterate（条件） | verify | G-IT |
| result_audit | iterate（iterate 可跳过：verify 首轮达标时 iterate=skipped，`--assert-done` 对 skipped 亦放行） | G-RA |
| oos（条件） | result_audit | G-OS |
| report | oos（oos 可跳过：verdict 非 pass/partial 或无样本外数据时 oos=skipped，`--assert-done` 对 skipped 亦放行） | G-FN |
| review | report | （人工，无机器门禁） |

---

## 三、子命令路由

进入时先判断第一个参数：`setup` / `continue` / `status` / `revise` / `accept` 命中对应分支；否则视为 `<pdf_path>` 走新跑分支。

### 3.0 `setup`（首次使用配置向导，幂等可重跑）

按 `stages/setup.md` 执行卡走：AskUserQuestion 收六项配置（数据路径 / auto 或 interactive 执行模式 / 最大迭代次数 / 回测框架 / 偏差容忍 / 经济模式；另有配置文件项 audit_level 不进问卷）→ 调 `setup_workspace.py` 一次完成落地（.reproduce.json + templates/common 种子 + pyproject + 目录树）→ 转述环境检测报告（uv / Python 依赖 / codex CLI）→ 引导用户维护 `templates/data_catalog.md`。`backtest_framework` 的消费点在 plan / implement 执行卡（planner 复用规划与 coder 合同：用户框架优先、`common/` 补缺口）；`default_max_rel_dev` 的消费点在 `check_gates`（load_standards 自动读取，统一替换相对偏差上限）与 verify 执行卡（verifier 对数口径同步）。

### 3.1 `<pdf_path> [--mode auto|interactive] [--max-iter N] [--id name] [--difficulty easy|medium|hard]`

新跑，从 init 开始。
0. **未初始化引导**（形态 B）：cwd 无 `.reproduce.json` 且无 `tools/state.py`（即不是本仓库直跑）→ 先走 3.0 setup 再回本分支。
1. 定 `<id>`：`--id` 给定则用之，否则由 pdf 文件名取 snake_case。
2. **参数默认值**：`--mode` / `--max-iter` 未显式给出时，读 cwd `.reproduce.json` 的 `default_mode` / `default_max_iter` 作默认；配置也缺（或形态 A 无配置文件）时维持既有默认（mode=auto，max_iter=难度矩阵 3/5/6）。优先级固定：**显式参数 > .reproduce.json > 内置默认**。
3. 走 **init 执行卡**（`stages/init.md`）：`state.py init` → `pdf_extract` → 回填 `pdf_pages` → 若给了 `--difficulty` 则 `set <id> difficulty_override <d>` → 过 G-IN。
4. init 完成后**打印可复制的 /goal 无人值守命令**（见第七节）。
5. 之后按第四节主循环协议逐 stage 推进（本次会话即可继续跑，或让用户粘贴 /goal 无人值守）。

### 3.2 `continue <id>`（断点续跑，所有驱动器的统一接入点）

1. `uv run python tools/state.py show <id>` 读态。
2. 按 `status` 分派：
   - `done` / `done_partial`：报告已出，提示 `revise`（定向改假设重跑）或 `accept`（确认收尾）；不再自动推进。
   - `paused_blocked`：读 `pending_question`，用 `AskUserQuestion` 把候选解释与影响说明呈给用户；据答复解除阻塞（如补数据/降级复现/放弃）并处理完 blocker 后，执行 `uv run python tools/state.py set <id> status running` 写回 state 再继续推进。**驱动器不得自行冲过此闸门。**
   - `awaiting_review`：最终报告等人工 review，提示 `accept` / `revise`；**不自行 accept**。
   - `aborted`：提示需显式重启。
   - `running`：进入续跑（下一步）。
3. 续跑定位：沿 STAGE_ORDER 找**第一个非 done/skipped** 的 stage 作为 `current`。
4. **进入前幂等自愈**：对 `current` 跑 `check_gates --stage <current>`（默认模式全量重算）——若已 PASS（产物齐全且合规），直接 `set-stage <current> done` 跳过，前进到下一个；否则 `set-stage <current> running`（attempts 自增）按该 stage 执行卡重跑覆盖写。**豁免**：iterate 阶段不适用真空 PASS 跳过——`current_stage` 为 `iterate`，或（`verify` 已 `done` 且 `check_gates verify` 曾记录 G-VF-3 FAIL 且尚无任何完成轮）时，一律走步骤 5 的 iterate 专用续跑，不走本步骤的 PASS-跳过快速路径（原因：G-IT-1 只按已记的 `iteration.current` 检查到对应 `iter_NN`，尚未开始记数的轮次天然不会被查到，会被误判为「产物齐全」的真空 PASS）。
5. **iterate 的特殊续跑**：读 `iterations/` 下最大的 `iter_NN`，按三件套（`diagnosis.md` / `changes.md` / `comparison.json`）的完整性判断从哪一步续起——缺 diagnosis 从诊断起，缺 changes 从修正起，缺 comparison 从重跑起。**零轮次情形**：`verify` done 且指标超差但 `iterations/` 下无任何 `iter_NN` → 从第 1 轮进入 `iterate` 执行卡（即 `stages/iterate.md` 步骤 1 起）。

### 3.3 `status [id]`

- 有 `id`：`uv run python tools/state.py show <id>`。
- 无 `id`：`ls workspace/` 列出全部 report_id，对每个跑一次 `state.py show` 摘要（current_stage / status / verdict）。
- **呈现约定（面向用户的可读性）**：show 原始输出之外，用中文进度摘要转述——11 阶段用人话（初始化→研报提取→复现规划→规格审计→代码实现→代码审计→运行验证→迭代修正→结果审计→报告汇总→人工评审），标注当前所处位置与完成比例；门禁/意见代号（G-XX、CDX/CA/RA-XX）只括注不打头，正文讲清楚它是什么检查、结论如何。此约定适用于全部子命令对用户的汇报措辞：**对用户讲人话，代号进文书**。

### 3.4 `revise <id> --assumption <ASid> "<新口径>" | --instruction "<指令>"`

人工 review 后的定向重跑（详见 `stages/review.md`）：
1. 派 `quant-planner` 更新 `assumptions.md`：把 `<ASid>` 改写为新口径、状态 `assumed→revised`（`--instruction` 形式则按指令新增/调整假设）。
2. 读该假设 `影响面` 字段查表定重跑范围：

   | 影响面 | 重跑链路 |
   |--------|---------|
   | data / method | 受影响 milestone 的 implement → codex 增量 code_audit → verify → result_audit → report |
   | param / trading | implement（config 级）→ verify → result_audit（轻量）→ report |
   | output | verify（重出图表/Excel）→ report |

3. 只重跑受影响链路（各段仍走对应执行卡与门禁）；`quant-reporter` 增量更新 `final_report.md`。
4. 记 `record-event <id> revise --json '{"assumption":"<ASid>","trigger":"revise"}'`；revise 轮 **不占 max_iter**，单条内部收敛上限 3 轮，超限则 `paused_blocked` 汇报。
5. 完成后 `set <id> status awaiting_review`，回到 review。

### 3.5 `accept <id>`

review 通过收尾：`set-stage <id> review done` → 按 verdict 定终态：`verdict.result==partial` 则 `set <id> status done_partial`，否则 `set <id> status done`。打印覆盖率/可信度/报告位置摘要。

---

## 四、主循环协议（每个 stage 逐字执行，写死）

对当前 `current` stage：

1. **读执行卡**：`Read stages/{current}.md`（按需，只读这一张）。
2. **前置断言**（init 除外）：`uv run python tools/check_gates.py <id> --stage <prev> --assert-done`，FAIL 则说明上一 stage 未真正 done，回上一 stage 修复，不得强推。
3. **状态先行**：`uv run python tools/state.py set-stage <id> {current} running`。
4. **动作序列**：按执行卡派 agent / 调 codex / 跑工具（并行只按第五节规则）。
5. **逐一点收**：对执行卡列出的每个输出合同文件 `ls -la` 核在（含 >0 字节 / 图表 >15KB 等硬指标由门禁兜底）；缺一即该步失败，带缺失清单重派。
6. **出口门禁**：`uv run python tools/check_gates.py <id> --stage {current} --record`，**把完整输出（每行 [PASS|FAIL] 与末行 VERDICT）原样贴进回复**。
7. **放行**：VERDICT PASS → `set-stage <id> {current} done` → 前进到下一 stage；FAIL → 按该执行卡「失败处理」分支处理。（唯一例外同硬规则1：verify 阶段仅 G-VF-3 达标项 FAIL 时的「FAIL → 进 iterate」按 `stages/verify.md` 处理，属设计内路径，不算违反本条）
8. **兜圈断路器**：同一 stage 的**同一 gate 连续 3 次 FAIL** → `set <id> status paused_blocked` + `set <id> pending_question "<卡在哪、缺什么、需人工做什么>"` + `record-event`，停下汇报，不再重试。

> 门禁的 `--assert-done`（前置，只读 state 状态，成本低）与默认模式（出口，全量重算产物）是两种用途，不要混用。

---

## 五、并行规则（并行只由主会话发起；子 agent 一律不嵌套）

允许的并行仅限以下五处，其余一律串行：

1. **hard 难度无依赖 milestone 多 coder**：`implement` 阶段，deps 互不相关的 milestone 可同时派多个 `quant-coder`（一条消息内多个 Agent 调用）。
2. **spec_audit 双通道**：codex 盲提取审查（Bash 直调）∥ `quant-auditor mode=spec` 内审（Agent，medium+ 才有内审）——同时发起，两者都返回后汇合统一过 G-SA。
3. **code_audit ∥ verify**（**medium/hard 默认并行**；easy 或 `tags` 含 ml 维持串行——ml 外审抓 critical 先验高，先审后跑省大概率作废的全跑）：verifier 派发**前移至 code_audit 阶段**，与 codex（Bash）同批发起；**verify 阶段的记账与门禁次序不变**——汇合后先过 G-CA → `set-stage verify running` → 点收已返回的 verify 产物 → 过 G-VF。**作废规则**：G-CA 处置引发任何 `src/` 改动（critical 修复或涉码 major 处置）→ 本次预跑 verify 产物作废（G-VF-6 新鲜度机器兜底会判 FAIL），重派 verifier，不得拿旧产物过门。economy 用户可选择维持串行，避免作废时浪费一次全跑。
4. **implement 流水线（medium/hard 默认）**：milestone mN 的验证环节（medium：verifier；hard：auditor(code)→verifier 链）与 mN+1 的编码同批派发重叠（滚动批次，深度 1：任一时刻至多一个 milestone 的验证链 + 一个 milestone 的编码在途；hard 的无依赖多 coder 并行不受此限、可叠加）。**多个 milestone 的 verifier 不得同批**（共写 verify_report.md）；多个 auditor 可同批（各写各的 impl_audit_m{mid}.md）。汇合分诊与尾部条件见 `stages/implement.md`「流水线汇合协议」。
5. **result_audit ∥ oos**（可选提速）：oos-analyst 的全部输入在 result_audit 开始前已冻结（verdict 已定）；触发判定前移，与 result_audit 双通道同批加派。**汇合后先过 G-RA**——若有数字不实类 critical（回 verify 重出 comparison）则 oos 产物作废重跑（基线已变）；G-RA 干净 → oos 阶段照常 `set-stage running` → 直接点收 → G-OS。

硬约束：子 agent 不得再派 agent / 调 skill / 启动 Task 工具（API 400 根源）；`codex exec` 是外部进程调用、非 agent 嵌套，只有主会话与 `quant-verifier`（辅助验证用途）可 Bash 直调。
**并行纪律（任何并行点一体适用）**：
- **state.py 写命令严禁同批并行**：同一汇合点的多笔记账用单个 Bash 调用内 `&&` 串联（state.json 为整文件读改写、无锁，同批并行的两个写命令必丢一笔更新）。
- **同批 agent 的输出文件集必须不相交**：会共写同一文件的两个 agent（如两个 milestone 的 verifier 共写 verify_report.md）不得同批发起。

---

## 六、难度裁剪矩阵（check_gates 内置本矩阵；codex 三审查点全难度必跑）

| 机制 | easy | medium | hard |
|------|------|--------|------|
| spec_audit：codex（含盲提取协议） | 必跑（轻量：R 表逐格 + 图表编号连续性） | 必跑（盲抄全部结果表数值 + 全维度） | 必跑（全量盲提取 diff + 全维度） |
| spec_audit：auditor(spec) 内审 | 跳过 | 必跑 | 必跑 |
| implement 编排 | 单 coder 一次实现 | 逐 milestone 派发，验证与下一编码流水线重叠 | 按 milestone 派独立 coder，无依赖并行 + 依赖链流水线重叠 |
| milestone 级 verify | 跳过（并入 final verify） | 每 milestone | 每 milestone |
| auditor(code) 实现忠实性审计 | 并入 verify（抽 2 条核心要素） | 逐条核对 core 要素（含 ml tag 时全量） | 逐条核对全部要素，每 milestone |
| code_audit / result_audit：codex | 必跑 | 必跑 | 必跑 |
| auditor(result) 反虚报核查 | 仅触发时 | 仅触发时 | 必跑 |
| 扰动测试 | 仅触发（K1/K2 命中） | 仅触发 | 必做一次 |
| iterate 默认 max_iter | 3 | 5 | 6 |

补充：`tags` 含 `ml` 时 `auditor(code)` **无视难度必跑**（未来函数/训练泄漏数值验证抓不到）；`--difficulty` 启动参数覆盖分诊结果，记入 `state.difficulty_override`，plan 阶段以 override 值回填 `state.difficulty`。

---

## 七、无人值守（首选内置 /goal）

**init 完成后立即打印**下面这条可直接复制的命令，并说明"粘贴即启用跨会话自主推进"：

```
/goal 持续执行 /reproduce continue <id>，直到 workspace/<id>/state.json 的 status
变为 awaiting_review、done、done_partial 或 paused_blocked 四个终态之一；到达
paused_blocked 或 awaiting_review 时视为目标达成，停下并汇报待决事项与报告位置
```

**目标措辞安全设计（不得改写）**：条件必须写成"到达四个终态之一即停"，**严禁写成 `status==done` 或"复现成功"**——后者会诱导驱动层冲撞人工闸门、虚报达标。`paused_blocked` 与 `awaiting_review` 是人工闸门，任何驱动器（/goal、/loop、ralph-loop）都不得冲过；`/goal` 只负责推进到终态，pass/partial 达标判定唯一出自 `check_gates`（goal 达成 ≠ 复现达标）。

**备选驱动**（非首选，仅在需固定节奏轮询或 /goal 不可用时）：`/loop` 技能或 `ralph-loop` 插件包裹 `/reproduce continue <id>`，退出条件与人工闸门语义同上。

---

## 八、TaskCreate 进度镜像

`plan` 定稿后，可用任务工具（TaskCreate / TodoWrite）按 `milestone × stage` 建任务树与依赖链，仅作 UI 进度镜像便于观察。**`state.json` 是唯一真相源**——任务树与 state 冲突时以 state 为准，不得反向依据任务树改判门禁。
