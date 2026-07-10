# stage: oos（样本外表现分析，条件 stage：复现达标才跑）

回答「研报效应在作者没见过的样本上还成立吗」：把复现好的策略**原样**延伸到研报回测区间之后的数据上运行。条件 stage——verdict 不满足触发条件、或无样本外数据时整段 skipped（`--assert-done` 对 skipped 放行，不阻塞 report）。

## 入口条件

- 前置断言：`uv run python tools/check_gates.py <id> --stage result_audit --assert-done` 必须 PASS。

> **并发模式（SKILL.md 五.5）**：oos-analyst 已在 result_audit 阶段同批派发并返回——本阶段照常 `set-stage oos running`，跳过步骤 2 的派发，直接从点收开始；若 result_audit 曾回 verify 重出 comparison，预跑产物作废、重派。

## 触发判定（主会话执行，写死）

读 state 的 `verdict.result`（实验模式同样适用——样本外验证的是迁移市场上该方法的持续性，价值不减）：
- `pass` 或 `partial` → 进入动作序列（partial 时在派发 prompt 里注明基线达标水平 N/M，agent 会在报告标注）。
- 其他（null / fail）→ `uv run python tools/state.py set-stage <id> oos skipped` + `record-event <id> oos_skipped --json '{"reason":"verdict 不满足触发条件"}'`，直接进 report。

## 动作序列

1. **状态先行**：`uv run python tools/state.py set-stage <id> oos running`
2. **派 `quant-oos-analyst`**（subagent_type=`quant-oos-analyst`）。输入合同：
   - `src/<id>/` 全部代码与 `config.py`（样本内区间）
   - `workspace/<id>/spec/spec.md`、`workspace/<id>/assumptions.md`
   - `output/<id>/results/comparison.json`（复现基线，转述 verdict.result 与 metrics_pass/total）
   - 数据根路径（读 cwd `.reproduce.json` 的 `data_root` 转述；无配置文件则 `~/local_data`）与 `templates/data_catalog.md`
3. **无样本外数据分支**：agent 返回「无样本外数据可用」声明（本地数据未超出研报区间）→ `set-stage <id> oos skipped` + `record-event <id> oos_skipped --json '{"reason":"本地数据未超出研报回测区间"}'`，进 report，**不算失败**。
4. **点收输出合同**（逐一 `ls -la`）：
   - `output/<id>/results/oos_metrics.json`
   - `output/<id>/results/oos_nav.png`（>15KB）
   - `output/<id>/results/oos_summary.xlsx`
   - `workspace/<id>/oos_report.md`

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage oos --record
```
原样贴输出。G-OS：G-OS-1 oos_metrics.json 存在且含区间/指标/结论字段 / **G-OS-2 样本外区间与样本内零重叠且非空（oos_start > in_sample_end，防区间造假）** / G-OS-3 结论 ∈ {延续, 衰减, 失效, 样本不足} / G-OS-4 oos_report.md 存在（oos_days<60 须带「样本外过短」警示）/ G-OS-5 oos_nav.png 存在且 >15KB。

VERDICT PASS → `set-stage <id> oos done` → 进 report（reporter 输入合同追加 oos 产物，final_report 必含「样本外表现」章节，G-FN 动态核验）。

## 失败处理

- **G-OS-2 区间重叠** → 疑似样本内数据冒充样本外，带门禁输出原样重派 quant-oos-analyst 修正，复审。
- **G-OS-4 短样本缺警示** → 定向补 oos_report.md 警示后重跑门禁。
- **策略代码被改动**（点收时 `git diff src/<id>/` 发现非日期改动）→ 作废本次产物，重派并在 prompt 强调硬约束 5。
- 同一 gate 连续 3 次 FAIL → 兜圈断路器（SKILL.md 第四节第 8 条）。
