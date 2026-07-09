# stage: verify（quant-verifier，opus）

亲自运行 main.py、逐项对数、产 comparison.json 与图表、随跑随记证据链（E1–E6），触发时跑扰动测试。**达标判定唯一出自 check_gates 按 standards.json 重算。**

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage code_audit --assert-done` 必须 PASS。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> verify running`
2. **派 `quant-verifier`**（subagent_type=`quant-verifier`）。输入合同（逐字）：
   - `src/<id>/` 全部
   - `workspace/<id>/spec/spec.md` 的 R 类基准表（验证基准唯一真相源）
   - `templates/standards.json`（容差 + required_charts + required_excels）。**用户偏差容忍**：cwd `.reproduce.json` 的 `default_max_rel_dev` 非空时（主会话读后转述数值），comparison.json 的 pass 字段按「所有相对偏差判定统一用该容忍度、abs_eps/同号/量级语义不变」填写，与 check_gates 的重算口径一致（check_gates 已自动读该配置）；为空则按 standards.json 原值。
   - `templates/<type>.md`
   - `templates/audit/evidence_manifest.md`
   - `workspace/<id>/spec/coverage_matrix.md`（回填「验证结果」列）
   - `workspace/<id>/assumptions.md`（回填「验证后回看」字段，见输出合同 7）
   - 触发条件说明：`difficulty`=hard **必做一次扰动测试**；或全部指标偏差同时 <0.5%（K2）时任何难度都做。
3. **点收输出合同**（逐一 `ls -la`，图表 >15KB / Excel 非零由门禁兜底）：
   - `output/<id>/results/`：required_charts 的 PNG、`backtest_summary.xlsx` 等 Excel、`metrics.json`、`run_log.md`（含命令/退出码/起止时间戳）
   - `output/<id>/results/comparison.json`
   - `output/<id>/verify_report.md`（**不含归因结论**；**medium/hard** 含各 milestone 的验证小节；**difficulty=easy 时须含「实现忠实性抽查」小节**：2 条 core 要素的实现位置真实性核对结论——该难度下 `auditor(code)` 并入 verify，见 SKILL.md 第六节裁剪矩阵）
   - `workspace/<id>/audit/evidence_manifest.md`（E1–E6 + 触发的扰动测试记录）
   - 回填后的 `coverage_matrix.md`「验证结果」列
   - `assumptions.md` 的「验证后回看」字段（占位符 `[verify 后填]` 必须全部替换）
   - 若调 codex 辅助：`workspace/<id>/audit/verify_assist_codex_NN.md`

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage verify --record
```
原样贴输出。G-VF：G-VF-1 run_log 含 exit=0 / G-VF-2 comparison.json 可解析 / **G-VF-3 按 standards.json 重算每条 metric 的 rel_dev 与 pass（不信任文件内 pass）** / G-VF-4 required_charts 全存在且 >15KB / G-VF-5 required_excels 全存在且非零 / G-VF-6 产物 mtime 晚于 src（E2 新鲜度）/ G-VF-7 矩阵验证结果列对**非 skipped/infeasible** 的 core/support 行无空。

## 达标分支（读 G-VF 逐条结果决定走向）

- **VERDICT PASS（含 G-VF-3 达标）** → 达标：
  ```
  uv run python tools/state.py set <id> verdict.result pass
  uv run python tools/state.py set <id> verdict.comparison_file output/<id>/results/comparison.json
  uv run python tools/state.py set <id> verdict.metrics_pass <pass_count>   # 按 G-VF-3 重算结果统计（recalc_metric 判 True 的条数），非 comparison.json 自述的 pass_count 字段
  uv run python tools/state.py set <id> verdict.metrics_total <total>       # 同上，取 G-VF-3 重算覆盖的指标总数
  uv run python tools/state.py set-stage <id> verify done
  uv run python tools/state.py set-stage <id> iterate skipped    # 首轮即达标，整段迭代不发生
  ```
  → 进 result_audit。
- **仅 G-VF-3 FAIL（指标超容差），G-VF-1/2/4/5/6/7 结构项全 PASS** → 验证结构完整、仅未达标 → **进 iterate**（iterate 是「指标超容差」的既定补救路径，非硬规则1 意义上的越门；先记结构完整再进补救）：
  ```
  uv run python tools/state.py set <id> verdict.result partial    # 暂定，迭代收敛后由 G-VF 重算改写
  uv run python tools/state.py set-stage <id> verify done         # 验证已如实产出对比，结构完整
  ```
  → 进 iterate（见 `stages/iterate.md`）。
- **结构项 FAIL**（G-VF-1 run_log 无 exit=0 / G-VF-2 comparison 不可解析 / G-VF-4/5 图表 Excel 缺 / G-VF-6 新鲜度倒挂 / G-VF-7 矩阵未回填）→ **verify 未 done，禁止推进**（硬规则1）：
  - 运行报错（G-VF-1/2）→ 回 `quant-coder` 修复（`uv run python tools/state.py record-event <id> verify_run_error_fix --json '{"attempt": N}'` 记第 N 次重试，**不改 `iteration.current`、不占迭代轮**——迭代轮计数完全交给 `iterate.md` 的 `iter_NN` 机制），修好回本 stage 重跑 verifier；重试上限见下方「失败处理」同一 gate 连续 3 次 FAIL 的兜圈断路器。
  - 新鲜度/图表/矩阵问题 → 回 `quant-verifier` 重跑补齐（拿旧结果冒充 = E2 失败，必须重跑）。

## 失败处理

- 同一 gate 连续 3 次 FAIL → `paused_blocked` + `pending_question`。
- 扰动测试完全不变（核心指标相对变化 ≤0.1%）→ 输出与输入解耦、硬编码实锤，verifier 记 critical 进 evidence_manifest → 回 code_audit/coder 修复，**计入迭代轮**（由 `iterate.md` 的 `iter_NN` 机制正式计数；触发源见 `iterate.md` 入口条件的「code_audit critical 修复」一项）。
- **运行报错修复不占迭代轮**：上文「运行报错（G-VF-1/2）」分支的 coder 修复只用 `record-event` 记重试次数，不推进 `iteration.current`、不建 `iter_NN` 目录；只有指标超容差正式进入 `iterate` 阶段后的诊断-修正-重跑，才按 `iterate.md` 的 `iter_NN` 机制计为一次正式迭代轮。
