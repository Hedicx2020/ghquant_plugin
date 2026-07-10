# stage: implement（quant-coder，opus × milestone）

按 plan 切片实现策略代码，回填矩阵实现位置。**按难度差异化编排。**

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage spec_audit --assert-done` 必须 PASS。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> implement running`
2. **按难度编排**（见 SKILL.md 第六节裁剪矩阵）：
   - **easy**：单 `quant-coder` 一次实现全部 milestone；milestone 级 verify 跳过，并入 final verify。
   - **medium**：逐 milestone 派发 `quant-coder`；**verify(mN) 与 code(mN+1) 同批发起**（一条消息内 Agent verifier + Agent coder，滚动批次深度 1），按下方「流水线汇合协议」汇合。milestone 级验证跑通该 milestone 相关计算、写 `output/<id>/verify_report.md` 对应小节；**不加**对抗复核（不逐 milestone 插 `quant-auditor mode=code`，实现忠实性审计留到 code_audit 阶段一次性做，与 SKILL.md 第六节裁剪矩阵一致）。
   - **hard**：按 milestone 派**独立** `quant-coder`；**无依赖（deps 为空或已完成）的 milestone 可并行**（一条消息内多个 Agent 调用）；每个 milestone 完成后插 `quant-auditor mode=code`（产 `impl_audit_m{mid}.md`）+ milestone 级 `quant-verifier`。**依赖链上同样流水线重叠**：mN 的 auditor→verifier 环节与 mN+1 的编码同批（可与无依赖并行叠加）；**多个 milestone 的 verifier 不得同批**（共写 verify_report.md），多个 auditor 可同批（各写各的 impl_audit 文件）。
3. **每个 coder 的输入合同**（逐字）：`workspace/<id>/plan.md`（或单 milestone 切片 + 其 `elements` 清单）、`workspace/<id>/spec/spec.md`、`workspace/<id>/assumptions.md`、`templates/<type>.md`、`common/` 现有模块签名（`utils.py`/`backtest.py`/`data_loader.py`/已有 `{type}_*.py`）、`workspace/<id>/spec/coverage_matrix.md`。**流水线派发专用条款（medium/hard，写进 coder prompt）**：① 文件所有权——只写本 milestone 所辖文件与 coverage_matrix 中本 milestone `elements` 对应行；共享装配层（如 main.py）的改动推迟到本 milestone 汇合后或专属装配 milestone；② 上游 milestone 代码可能**已实现未验证**——接口以现状为准，发现其缺陷只在完成报告中说明、**不顺手修改**（修改权归其修复流程）。**verifier 派发 prompt 注明**：milestone 级验证产物只写 `output/<id>/verify_report.md` 对应小节，**勿在 `output/<id>/results/` 新增或覆盖正式产物**（final verify 统一产出，避免 G-VF-6 新鲜度误判）。**用户自有回测框架**：cwd `.reproduce.json` 的 `backtest_framework` 非空时，合同追加「用户回测框架位于 <路径>：先读其源码确认接口，回测执行层**优先调用该框架**（在 `src/<id>/` 内以 `sys.path` 或包名接入），`common/` 仅补其缺口；输出产物合同（comparison/图表/Excel）与门禁要求不变」；为空则不提（默认 `common/`）。
3.5 **流水线汇合协议（medium/hard）**——每个滚动批次（verify(mN) ∥ code(mN+1)）汇合时按下表分诊：
   1. **verify(mN) PASS** → 记账（见记账纪律），滚动窗口前移：下一批 = verifier(mN+1) + coder(mN+2)。
   2. **verify(mN) FAIL，报错定位在 mN 所辖范围** → 下一批派 coder-fix(mN)（计入该 milestone 重派上限）；**mN+1 已落盘代码不作废**——fix 复验通过后若改动了接口，先派 coder(mN+1) 做**增量适配复核**（输入含 fix 的 diff，指令「核对接口适配，非从头重做」）；`deps(mN+1) ∋ mN` 时 verifier(mN+1) **缓到 fix(mN) 复验 PASS 之后**（坏树上验下游白烧且连环假 FAIL），mN+1 独立时其 verifier 可与 fix(mN) 同批。
   3. **verify(mN) FAIL，报错定位文件属 mN+1 所辖且非 mN 依赖面** → **流水线干扰假 FAIL**（verifier 跑数时撞上 mN+1 半写状态的共享导入）：汇合后（树已静止）直接复跑 verifier(mN)，**不派 coder、不占重派次数**。
   4. **尾部条件**：最后一个 milestone 的 verify（hard 含 auditor）返回并记账完毕后，才允许跑 G-IM `--record`（G-IM 不核 milestone verify 子状态，此条封堵在途验证被遗忘的协议洞）。
   5. **记账纪律**：每个汇合点的全部 `state.py milestone ...` 写命令在**单个 Bash 调用内 `&&` 串联**（SKILL.md 五节并行纪律）。

4. **每完成一个 milestone 更新 state**：`uv run python tools/state.py milestone <id> <mid> implement done`（G-IM-4 逐 milestone 核对 implement=done）。**medium/hard** 的 milestone 级 verify 通过后 `milestone <id> <mid> verify done`；**hard** 的 auditor mode=code 通过后 `milestone <id> <mid> code_review done`（medium 的 auditor mode=code 在 code_audit 阶段一次性做，不逐 milestone 记）。
5. **点收输出合同**（逐一 `ls -la`）：
   - `src/<id>/strategy.py`、`src/<id>/main.py`（`config.py` 视需要）
   - 按需**首次创建**的 `common/<type>_*.py`（非 factor 类引擎，按 `templates/<type>.md` 接口签名；严禁写进 `src/`）
   - 回填后的 `workspace/<id>/spec/coverage_matrix.md`（「实现位置」列 `src文件:函数`，状态 done）
   - 若 coder 补登了简化假设 → `workspace/<id>/assumptions.md` 有新条目
   - medium/hard：`output/<id>/verify_report.md` 含每个 milestone 的验证小节
   - hard：每 milestone 一份 `workspace/<id>/audit/impl_audit_m{mid}.md`

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage implement --record
```
原样贴输出。G-IM：G-IM-1 strategy.py 存在 / G-IM-2 main.py 存在 / G-IM-3 `python -m compileall src/<id>` 通过 / G-IM-4 state.milestones 全部 implement=done / G-IM-5 矩阵「实现位置」列对非 skipped/infeasible 行非空。

VERDICT PASS → `set-stage <id> implement done` → 进 code_audit。

## 失败处理

- **流水线干扰假 FAIL**（汇合协议第 3 条）→ 树静止后复跑 verifier(mN)，不派 coder、不占重派次数。
- **mN 兜圈至 paused_blocked** → 在途/已落盘的 mN+1 产物保留原状，续跑时按 coverage_matrix 与 state 现状恢复。

- **coder 报错**（compileall 失败/import 错）→ 带报错上下文重派该 coder（**每 milestone 上限 2 次**）；超限 → paused_blocked。
- **hard 的 milestone 级复核/verify 不通过** → 回该 milestone 的 coder 重走（issue 贴给它），复核通过再 `milestone ... done`。
- **G-IM-4 有未完成 milestone** → 说明某 milestone 的 coder 未真正交付，回派补齐（不得手工把 state 标 done 蒙混）。
- **G-IM-5 实现位置缺失** → 回 coder 补填矩阵「实现位置」为真实 `文件:函数`（auditor 会核验非空壳）。
