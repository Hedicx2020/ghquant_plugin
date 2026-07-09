# stage: implement（quant-coder，opus × milestone）

按 plan 切片实现策略代码，回填矩阵实现位置。**按难度差异化编排。**

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage spec_audit --assert-done` 必须 PASS。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> implement running`
2. **按难度编排**（见 SKILL.md 第六节裁剪矩阵）：
   - **easy**：单 `quant-coder` 一次实现全部 milestone；milestone 级 verify 跳过，并入 final verify。
   - **medium**：单 `quant-coder` 逐 milestone **串行**；**每个 milestone 完成后派 `quant-verifier` 做 milestone 级验证**（跑通该 milestone 相关计算，写 `output/<id>/verify_report.md` 对应小节；与 hard 的 milestone 级验证同构，但**不加**对抗复核——即本阶段不逐 milestone 插 `quant-auditor mode=code`，实现忠实性审计留到 code_audit 阶段一次性做「逐条核对 core 要素」，与 SKILL.md 第六节裁剪矩阵一致）。
   - **hard**：按 milestone 派**独立** `quant-coder`；**无依赖（deps 为空或已完成）的 milestone 可并行**（一条消息内多个 Agent 调用）；每个 milestone 完成后插 `quant-auditor mode=code`（产 `impl_audit_m{mid}.md`）+ milestone 级 `quant-verifier`。
3. **每个 coder 的输入合同**（逐字）：`workspace/<id>/plan.md`（或单 milestone 切片 + 其 `elements` 清单）、`workspace/<id>/spec/spec.md`、`workspace/<id>/assumptions.md`、`templates/<type>.md`、`common/` 现有模块签名（`utils.py`/`backtest.py`/`data_loader.py`/已有 `{type}_*.py`）、`workspace/<id>/spec/coverage_matrix.md`。
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

- **coder 报错**（compileall 失败/import 错）→ 带报错上下文重派该 coder（**每 milestone 上限 2 次**）；超限 → paused_blocked。
- **hard 的 milestone 级复核/verify 不通过** → 回该 milestone 的 coder 重走（issue 贴给它），复核通过再 `milestone ... done`。
- **G-IM-4 有未完成 milestone** → 说明某 milestone 的 coder 未真正交付，回派补齐（不得手工把 state 标 done 蒙混）。
- **G-IM-5 实现位置缺失** → 回 coder 补填矩阵「实现位置」为真实 `文件:函数`（auditor 会核验非空壳）。
