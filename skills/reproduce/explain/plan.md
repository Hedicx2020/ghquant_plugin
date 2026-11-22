# plan（复现规划）

顺序：`plan.main`（planner 只读 spec，写 `plan.md` 与 `assumptions.md`）→ 内核从 plan 播种 milestone 与难度 → 数据需求体检 →（试跑时）`plan.mock_spec` 与生成模拟数据 → 过门禁。

## G-PL-2、G-PL-3、G-PL-4、G-PL-5、G-PL-6、G-PL-7

plan 的结构性问题：frontmatter 解析不了、枚举值不合法、milestone 数低于难度下限、依赖成环、矩阵里有行没归属 milestone、歧义没有裁决完。重派 `plan.main`，门禁原文在重派原因里。

## G-PL-8

还有 blocking 级歧义没有裁决。不重派，开 `blocking_ambiguity` 检查点：把 `spec/ambiguities.md` 里的候选解释和各自的影响讲给人，人裁决后 planner 落实。不要替人选，也不要让 planner 自行降级。

## G-PL-9

planner 判定可行性为 blocked（核心数据缺失或核心方法无法确定）。开 `feasibility_blocked` 检查点，由人选补数据、切实验模式、降级复现或放弃。

## G-PL-10

有数据需求还没有体检结论，或体检之后 `data_requirements` 又被改过。内核自己重做体检，不用派人。

## G-PL-11

还有数据缺口没有处置决定（选了「补数据」而数据还没补齐也算）。内核重做体检后回到 `data_gap` 或 `data_wait` 检查点。见 `flow explain data`。

## plan_final

interactive 模式下，plan 的确认放在规格审计之后（规格审计还会改 plan）。见 `flow explain plan_final`。
