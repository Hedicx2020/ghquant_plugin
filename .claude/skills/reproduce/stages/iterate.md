# stage: iterate（条件；quant-diagnoser → quant-coder → quant-verifier）

诊断-修正-重跑循环，防兜圈，三出口。仅当 verify 未达标（G-VF-3 FAIL）时进入；首轮即达标则本 stage=skipped（在 verify 卡处理）。

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage verify --assert-done` 必须 PASS（verify 已 done，结构完整）。
- 触发源：final verify 门禁 FAIL（超差）/ code_audit critical 修复 / result_audit 发现问题 / 人工 revise（revise 不占 max_iter，见 SKILL.md 3.4）。

## 动作序列（每轮严格按序）

1. **状态先行**：`uv run python tools/state.py set-stage <id> iterate running`
2. **推进轮次计数 + 建目录**：`N = state.iteration.current + 1` → **先** `uv run python tools/state.py set <id> iteration.current <N>` **后**建 `workspace/<id>/iterations/iter_<NN>/`（两位补零，如 iter_01）——顺序不可颠倒：唯有先记数，本轮才对 `check_gates` 的 G-IT-1（按 `iteration.current` 决定检查到哪个 `iter_NN`）可见，避免中途中断续跑时被误判为「真空 PASS」（见 SKILL.md 3.2 的 iterate 豁免条款）。**全卡 N 统一定义为「自增后的 `iteration.current`」**，即本轮（进行中或已完成）的轮次号，下述步骤 3–8 均在此定义下使用 N。
3. **快照 comparison**：把当前 `output/<id>/results/comparison.json` 拷进 `iter_<NN>/comparison.json`。
4. **（N≥2）后台 codex 第二意见**：填 `templates/codex_prompts/second_opinion.md`（占位符 `{report_id}/{type}/{iteration_current}/{iteration_max}/{trigger_reason}/{comparison_path}/{failing_metrics_summary}/{iteration_history_paths}/{NN}/{workspace}`）→ 落盘 `iter_<NN>/codex_prompt_second_opinion.md` → 调 codex（Bash，`timeout` 600000，可 `run_in_background`）：
   ```
   command codex exec -s read-only --skip-git-repo-check -C /Users/hedi/report_reproduce --color never --output-last-message "workspace/<id>/iterations/iter_<NN>/codex_opinion.md" - < "workspace/<id>/iterations/iter_<NN>/codex_prompt_second_opinion.md"
   ```
5. **派 `quant-diagnoser`**（subagent_type=`quant-diagnoser`）。输入合同：`spec.md`、`plan.md`、`assumptions.md`、`src/<id>/`、`output/<id>/verify_report.md`、`output/<id>/results/comparison.json`（或本轮快照）、`iteration_log.md` + **全部历史 iter_NN/**、`iter_<NN>/codex_opinion.md`（如有）、本轮 `iter_<NN>` id。产 `iter_<NN>/diagnosis.md`（含 N≥2 的「## 已排除假设」节 + 末尾 `结论 ∈ {continue, stop_partial, blocked}`）。
6. **按结论分派**：
   - **continue** → 派 `quant-coder`（迭代轮输入含 `iter_<NN>/diagnosis.md`，**只改 diagnosis 列明的文件范围**），产 `iter_<NN>/changes.md` → 派 `quant-verifier` 重跑 → 覆盖 `output/<id>/results/comparison.json`，并把重跑后的拷进 `iter_<NN>/comparison.json`。
   - **stop_partial** → diagnoser 已为每条 pass=false 指标写入 `attribution_status`（accepted/assumption_linked），进「超限 partial 出口」。
   - **blocked** → 「blocked 出口」。
7. **追加 iteration_log 与 history**：向 `workspace/<id>/iterations/iteration_log.md` 追加本轮行（触发 / 失败指标(偏差) / 采纳假设 / 修改摘要 / 结果(偏差变化) / 状态）+ 本轮明细（history）。（`iteration.current` 已在步骤 2 记过，本步不再重复推进计数。）
8. **重算达标**（continue 重跑后）：`uv run python tools/check_gates.py <id> --stage verify --record` 原样贴出：
   - PASS → 「达标出口」。
   - FAIL 且 `N < max_iter` → 回步骤 2 下一轮。
   - FAIL 且 `N == max_iter` → 「超限 partial 出口」。

## 三出口

- **达标出口**（check_gates 重算全过）：`set <id> verdict.result pass` + metrics_pass/total → 出口门禁（下）→ result_audit。
- **超限 partial 出口**（`N == max_iter` 触发的超限，或 diagnoser 结论 stop_partial）：`set <id> verdict.result partial`。
  - **若因 `N == max_iter` 触发超限**（非 diagnoser 主动 stop_partial）→ **必须再派一次 `quant-diagnoser`（收尾模式）**：prompt 写明「收尾模式：只为残余 pass=false 指标写归因并回填 `comparison.json` 的 `attribution_status`，不给 coder 修改指令」——**否则 G-RA-3 会因超差指标无 attribution_status 卡死 partial 路径**。
  - diagnoser 主动 `stop_partial` 时，attribution_status 已由其写好，无需再派。
  - 残余偏差 + 归因 + 已试假设入报告，**照常走 result_audit → report**（partial 也出完整报告与审计）。
- **blocked 出口**（核心数据/方法缺失）：`set <id> status paused_blocked` + `set <id> pending_question "<所需外部输入>"`，停下汇报。

## 出口门禁（达标 / partial 均需过）

```
uv run python tools/check_gates.py <id> --stage iterate --record
```
G-IT：G-IT-1 每轮 iter_NN/ 三件套齐（diagnosis.md/changes.md/comparison.json）/ G-IT-2 iteration.current ≤ max_iter / G-IT-3 N≥2 时 diagnosis.md 含「已排除假设」字样。

VERDICT PASS → `set-stage <id> iterate done` → 进 result_audit。

## 失败处理

- **防兜圈**由 diagnoser（五规则：历史强制回顾 / 假设唯一性 / 连续 2 轮无改善升级调 codex / 小步修改 / 同指标 3 轮红线自动 stop_partial）+ G-IT 共同保证；主会话不得越过 diagnoser 自行改代码。
- G-IT-1 三件套缺（如 continue 轮缺 changes.md）→ 补齐对应产物（缺 changes 回 coder，缺 comparison 回 verifier）。
- 断点续跑：读最大 iter_NN 三件套完整性决定从诊断/修正/重跑续起（见 SKILL.md 3.2）。
