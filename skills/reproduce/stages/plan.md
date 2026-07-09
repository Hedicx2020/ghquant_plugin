# stage: plan（quant-planner，opus）

复现设计：分诊（type/tags/difficulty/feasibility）、数据映射、milestone 拆分、歧义裁决与假设登记。**planner 只读 spec 不读 PDF**。

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage extract --assert-done` 必须 PASS。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> plan running`
2. **派 `quant-planner`**（subagent_type=`quant-planner`）。输入合同（逐字）：
   - `workspace/<id>/spec/spec.md`
   - `workspace/<id>/spec/coverage_matrix.md`
   - `workspace/<id>/spec/ambiguities.md`
   - `templates/data_catalog.md`
   - `templates/_plan_template.md`
   - `templates/<type>.md`（按 spec.md frontmatter 的 `type_hint`）
   - `templates/audit/assumptions.md`
   - `mode`：state.mode 的值（`auto` | `interactive`）
   - `backtest_framework`：cwd `.reproduce.json` 的该字段（主会话读后转述）。非空 → 在 prompt 中告知「用户自有回测框架位于 <路径>，复用规划时回测执行层优先盘点该框架的能力，`common/` 仅作缺口补充」；为空/无配置 → 不提，维持内置 `common/` 复用规划。
3. **点收输出合同**：
   - `workspace/<id>/plan.md`（frontmatter 分诊 + 正文）
   - `workspace/<id>/assumptions.md`（每条 auto 假设，`验证后回看` 写占位符 `[verify 后填]`）
   - 回填后的 `workspace/<id>/spec/coverage_matrix.md`（milestone 列 + 优先级定稿，最后更新=plan）
   - 回填后的 `workspace/<id>/spec/ambiguities.md`（各条裁决方式/结果/依据/状态）
4. **回填分诊到 state**（关键：下游裁剪矩阵与 standards 重算全靠这些字段）：
   ```
   uv run python tools/state.py set <id> type <plan.type>
   uv run python tools/state.py set <id> tags '<plan.tags 的 JSON 数组，如 ["ml"]>'
   uv run python tools/state.py set <id> difficulty <difficulty_override 若非空则用它，否则 plan.difficulty>
   uv run python tools/state.py set <id> feasibility <plan.feasibility>
   ```
5. **播种 milestones 到 state**（G-IM-4 逐 milestone 核对 implement=done 靠它）：读 plan.md frontmatter 的 milestones，转成 state 需要的形状（每条含 `id/name/deps/implement/code_review/verify`，三个子状态初始 `pending`）：
   ```
   uv run python tools/state.py set <id> milestones '[{"id":"m1","name":"...","deps":[],"implement":"pending","code_review":"pending","verify":"pending"}, ...]'
   ```
6. **回填 iteration.max**（若启动未给 `--max-iter`，state.iteration.max 为 null）：按难度默认（easy=3 / medium=5 / hard=6）：
   ```
   uv run python tools/state.py set <id> iteration.max <3|5|6>
   uv run python tools/state.py set <id> max_iter <同值>
   ```
7. 可选：按 milestone×stage 建 TaskCreate 进度镜像（见 SKILL.md 第八节）。

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage plan --record
```
原样贴输出。G-PL 逐条：G-PL-1 plan.md 存在 / G-PL-2 frontmatter 可解析 / G-PL-3 枚举合法（type/difficulty/feasibility）/ G-PL-4 milestone 数 ≥ 难度下限 / G-PL-5 deps 无环 / G-PL-6 矩阵非 skipped/infeasible 行 milestone 列非空 / G-PL-7 ambiguities 每条 status ∈ resolved/blocked / G-PL-8 无 blocking 级 open 歧义 / G-PL-9 feasibility != blocked。

VERDICT PASS → `set-stage <id> plan done` → 进 spec_audit。

## 失败处理（含人工闸门）

- **feasibility=blocked（G-PL-9 FAIL）或存在 blocking 级歧义**（G-PL-8 FAIL）→ **两种模式都暂停**：`set <id> status paused_blocked` + `set <id> pending_question "..."`，用 `AskUserQuestion` 给出三选一（**补数据 / 降级复现 / 放弃**）与影响说明；据答复让 `quant-planner` 更新 plan/ambiguities/feasibility 后复跑本 stage。
- **interactive 模式的 major 歧义**：planner 会把 major 歧义列为「待问清单」返回。主会话用 `AskUserQuestion` **分批提问（每批 ≤ 4 个）**，把答复回填后重派 planner 定稿。
- 其它 gate FAIL（枚举非法/成环/milestone 缺失/歧义未决议）→ 把 FAIL 原文贴回 planner 定向修复重派（上限 2 次，超限 paused_blocked）。
