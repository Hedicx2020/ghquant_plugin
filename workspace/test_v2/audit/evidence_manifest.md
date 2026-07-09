# 证据链清单 evidence_manifest.md

> 落盘于 `workspace/test_v2/audit/evidence_manifest.md`；由 `quant-verifier` 随跑随记，全难度必做。核验方式均为「亲自执行」，转述被审者自我陈述不算证据。
> 本文件对应 final verify（2026-07-08，hard 难度）；里程碑级中间证据见 `output/test_v2/results/run_log.md` 各 m1–m8 小节。

---

## E1–E6 规则（断言）

| 规则 | 断言 |
|------|------|
| E1 运行证据 | verifier 亲自执行入口；`run_log.md` 记完整命令、退出码、起止时间戳；exit≠0 一律 fail，禁止「部分成功」 |
| E2 新鲜度 | `results/` 产物 mtime 晚于 `src/` 最近修改；否则判「拿旧结果冒充」 |
| E3 文件完备 | `metrics.json`/`comparison.json` 可解析且非空；必需图表全存在且 >15KB；Excel 非零字节 |
| E4 三方数值一致 | 抽 3–5 核心指标逐位核对 `metrics.json` == `comparison.json`(=verify_report 引用值) == `backtest_summary.xlsx` |
| E5 样本量合理 | `n_periods`/`n_months` 与 spec 区间推算比对，偏差 >10% 报截断嫌疑 |
| E6 时间链 | spec → src → results → verify 的 mtime 单调递增；乱序报先写结论后跑数嫌疑 |

---

## 证据条目（E1–E6 逐条落盘）

固定字段：声明来源 / 证据类型 / 证据（文件+命令+时间戳）/ 佐证 / 核验方式（亲自执行）/ 结果。

| 证据ID | 规则 | 声明来源 | 证据类型 | 证据（命令+时间戳+落盘位置） | 佐证 | 核验方式 | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EVD-01 | E1 | 声称六入口可运行 | 运行日志 | `run_log.md#final 验证运行记录`；`uv run python -m src.test_v2.main` 21:55:18→20；combo_final 21:55:20→22；combo_composite 21:55:22→23；combo_ls 21:55:23→25；`reversal.py` 21:55:25；`robustness.py` 21:55:25→29 | 六入口全 exit=0，各日志 traceback/error 命中 0 行，冒烟摘要打印主区间 2037 交易日 | 亲自逐条执行并捕获退出码与 stdout | pass |
| EVD-02 | E1/E3 | 声称 comparison 可复现 56/91 | 运行日志 | `uv run python output/test_v2/results/build_final_artifacts.py` 21:55:29→30，输出 `[comparison] 定量覆盖=91 pass=56 fail=35 定性=4/4 overall=False` | 六入口重跑 CSV 后 build 复现 pass_count=56/91，与既有 comparison.json 完全一致 | 亲自重跑构建脚本并读退出码/stdout | pass |
| EVD-03 | E2 | 声称产物为本次新跑 | 文件 mtime | src 最新 `src/test_v2/robustness.py`=2026-07-08 18:50:34；产物 `comparison.json`/`metrics.json`/5 PNG=21:55:29~30、`backtest_summary.xlsx`=21:55:30 | 全部产物 mtime 晚于 src 最新约 3 小时 | 亲自 `stat` 逐一读取 mtime 比对 | pass |
| EVD-04 | E3 | 声称图表/Excel 完备 | 文件体积 | `stat` 实测：net_value 289715B/drawdown 383300B/position_signal 581155B/yearly_returns 97901B/rolling_sharpe 268366B（均 >15KB）；`backtest_summary.xlsx`=17305B（非零）；comparison.json 29955B 可 json.load | 5 张必需 PNG 全 >15KB、xlsx 非零、comparison 可解析非空 | 亲自 `stat` 读体积 + `json.load` 解析 | pass |
| EVD-05 | E4 | 声称 comparison 值来自本次 metrics | 三方核对 | 抽 3 指标逐位：R11 多空年化 comparison 0.080066 == metrics(6f) 0.080066 == xlsx对比总表 0.080066；R7 多空夏普 1.465127 三处同；R8 多空区间收益 0.618176 三处同 | 三处磁盘产物逐位相同，0 不一致 | 亲自脚本读三文件同键比对 | pass |
| EVD-06 | E5 | 声称样本区间完整 | 样本量 | `combo_final_signals.csv` 行数=2037（主区间 B1 第二段 2015-03-24~2023-08-02 交易日）；comparison `R14_n_months` 复现 100（研报附录窗口 2015-04~2023-07 正好 100 月） | 主区间 2037 日、R14 窗口 100 月与 spec 推算逐位吻合，无截断 | 亲自读 CSV 行数 + comparison 值 | pass |
| EVD-07 | E6 | 声称非先写结论后跑数 | 时间链 | src(≤18:50:34) < 六入口重跑(21:55:18→21:55:29) < build(21:55:29→21:55:30) < 扰动(21:56:23→21:56:25) | mtime 与执行时间戳单调递增 | 亲自比对 stat mtime 与 run_log 时间戳 | pass |
| EVD-08 | E1/K1 | 声称输出非硬编码 | 扰动测试 | `uv run python /tmp/perturb_check_final.py` 21:56:23→25：main_end 2023-08-02→2022-08-02，R11 年化 rel_change 9.9646%>0.1% | 区间收益4.67%/年化9.96%/夏普6.24% 显著变动 → 输出耦合输入 | 亲自重跑核心入口扰动版并读相对变化 | pass |

---

## 扰动测试记录

> hard 难度必做一次。本 final verify 于核心入口 combo_final 执行一次正式扰动，输出 `results/perturb_check/` 后清理。

- 触发原因: hard 难度必做（K2 未命中——35 项超差、偏差远超 0.5%，非「结果过于完美」；K1 硬编码嫌疑以本测证伪）。
- 扰动参数: 回测截止日 `main_end` 提前一年（2023-08-02 → 2022-08-02）。
- 执行方式: 一次性临时脚本 `/tmp/perturb_check_final.py` 以 `dataclasses.replace(CONFIG, main_end='2022-08-02', output_dir=results/perturb_check)` 重跑 combo_final，写 `output/test_v2/results/perturb_check/results/`（不改源文件；基线 `write_csv=False` 内存运行不覆盖磁盘产物）。build 脚本内置 `--perturb` 因调用不存在的 `combo_final.run` 不可用，故按 m4/m7/m8 里程碑先例另起临时脚本。
- 核心指标相对变化: R11 多空 区间收益 4.6693% / 年化收益 9.9646% / 夏普比率 6.2407% / 最大回撤 0.0000%；max_rel_change=9.9646% > 0.1%（最大回撤 0.00% 因该回撤发生于 2022-08 之前、截尾不改，其余三指标显著变动足以证伪硬编码）。
- 临时输出清理: perturb_check/ 生成 combo_final_{stats,yearly_stats,signals}.csv 后 `rmtree` 删除，`ls -d perturb_check` 复核=不存在（无残留）。
- 结论: 通过（输出随输入变化、非硬编码）。

---

## 主会话脚本修补透明披露

- `output/test_v2/results/build_final_artifacts.py`（final 产物统一脚本，此前 verifier 编写）经主会话 6 轮机械性键名/列名对齐修补——对齐 CSV 列名与 spec 表头解析键名，使逐项对数不因键名错位漏配。
- 无任何数值编造：研报基准值一律经 `spec.md` 第五节表格解析（`parse_spec`/`report_val`），复现值一律经本次运行 CSV 读取（`build_metrics`），二者在脚本内 `judge` 逐项对数生成 comparison.json；本次 verifier 亲自重跑六入口后 build 复现 pass_count=56/91 与既有一致，佐证修补属口径对齐而非结果注水。

---

## 审计结论

- E1–E6 全部规则均有至少一条「亲自执行」证据落盘：是（EVD-01~08）。
- 三方数值核对（E4）不一致条数：0（抽 3 指标逐位一致）。
- 时间链（E6）是否单调递增：是。
- 扰动测试（hard 必做）：已执行、已记录、已清理临时输出，结论通过。
- 总判定口径：本文件仅记录证据链完备性与真跑性，不下研报复现「通过/不通过」结论（overall_pass=false 由 comparison.json 呈现，归因归 diagnoser）。

---

## iter2 复验增量证据（2026-07-08，M2 年化基准 252→240 + M3 上涨/下跌胜率口径落地重跑）

> 迭代重跑增量证据，与 final verify 主证据链（EVD-01~08）互补；详细命令/时间戳见 `output/test_v2/results/run_log.md#iter2重跑记录`。

| 证据ID | 规则 | 声明来源 | 证据类型 | 证据（命令+时间戳+落盘位置） | 佐证 | 核验方式 | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EVD-09 | E1 | 声称 M2/M3 后六入口可运行 | 运行日志 | `run_log.md#iter2重跑记录`；main 23:25:50→51 / combo_final→54 / combo_composite→55 / combo_ls→56 / reversal→57 / robustness→23:26:01 | 六入口全 exit=0，各日志 traceback/error 命中 0 行 | 亲自逐条执行并捕获退出码与 stdout | pass |
| EVD-10 | E1/E3 | 声称 comparison 复现 81/91 | 运行日志 | `uv run python output/test_v2/results/build_final_artifacts.py` 23:26:17→19，输出 `[comparison] 定量覆盖=91 pass=81 fail=10 定性=4/4 overall=False` | pass 69→81 与 diagnosis 预期逐位一致；5 图 >15KB、xlsx 16.9KB | 亲自重跑构建脚本并读退出码/stdout | pass |
| EVD-11 | E2 | 声称产物为本次新跑 | 文件 mtime | src 最新 `reversal.py`=23:10:35（M3）/`config.py`=23:10:20（M2）；产物 comparison/metrics/5PNG=23:26:18、xlsx=23:26:19 | 全部产物 mtime 晚于最新 src（改前 22:30 产物不新鲜已作废） | 亲自 `stat` 逐一读取 mtime 比对 | pass |
| EVD-12 | E4 | 声称 comparison 值来自本次 metrics | 三方核对 | 抽 9 项逐位：R1_T 年化 metrics 0.0230018==comparison 0.023002；R8 多空年化 0.058346；R9 多空夏普 1.755453；R11 多空下跌胜率 0.490135；R11 多空上涨胜率 0.627358 等 | metrics.json(generated_at 23:26:17) 与 comparison 逐位相同，0 不一致 | 亲自脚本读双文件同键比对 | pass |
| EVD-13 | E6 | 声称非先写结论后跑数 | 时间链 | src(≤23:10:35) < 六入口重跑(23:25:50→23:26:01) < build(23:26:17→23:26:19) | mtime 与执行时间戳单调递增 | 亲自比对 stat mtime 与 run_log 时间戳 | pass |
| EVD-14 | E1/K1 | 声称 M2/M3 无副作用翻 fail | 全量 diff | 改前 `iter_02/comparison.json`(69/91) vs 改后 `comparison_after.json`(81/91)：pass 状态变化收敛 F→T 12 项、翻 fail T→F **0 项**；边界项 R1 长短端年化 4.37%/R7 仅做多年化 4.47%/R11 波动率 2.29% 仍 pass | 无任何已过项被 M2/M3 翻 fail，与 diagnosis 副作用预测逐位吻合 | 亲自脚本逐项对比双 comparison pass 状态 | pass |

### 扰动测试触发判断（iter2）

- K2 触发条件「全部指标偏差同时 <0.5%」未命中（overall_pass=False，仍 10 项 FAIL，rel_dev 最大 72.98% 家族四 R10_2023）→ 不触发。
- hard 难度强制扰动已于 final verify 执行并记录（EVD-08，R11 核心指标最大相对变化 9.96%>0.1%、非硬编码）；本轮 M2 仅改年化基准常数（252→240，年化/夏普仍为算出值、本身即证非硬编码）、M3 仅改胜率口径，二者与扰动断言的「输出随输入变化」性质正交、未引入硬编码 → 无需 iter2 重跑扰动，沿用 final 扰动结论。
- 结论：iter2 不触发扰动重跑（判断依据留痕，与 iter1 判断逻辑一致）。

---

## 反虚报复核（result_audit，2026-07-09）

> 由 quant-auditor（mode=result，hard 必跑）追加；审读分离、数值独立重算不采信声明。逐条详情见 `workspace/test_v2/audit/result_antifraud_review.md`。

1. K3 五图逐张 Read 实际查看 + 数值级核验：net_value 三线终点 1.86/1.52/1.21 吻合 `combo_final_signals.csv` 复利终点 strategy_ret_ls=1.8637=1+86.38%/close_return(T)=1.2116，drawdown 最深 -0.0326、yearly_returns 九年柱逐年对齐 CSV（2016最高/2023最低/T2017负）、rolling_sharpe~2.08、position_signal 仓位±1 均吻合——五图为真实序列忠实渲染。
2. E4 三方一致：pass_count 独立重数=81（pass=True 计数）/fail=10/total=91，与 comparison 声明及 xlsx『汇总』三方一致；全 91 项 comparison vs xlsx 逐位 **0 矛盾**、rel_dev 全量独立重算 **0 项不符**；5 抽样（R7盈亏比1.310884/R1_T年化0.023002/R11下跌胜率0.490135/R9多空夏普1.755453/R11区间收益0.863758）comparison==metrics(6位)==xlsx 逐位一致。
3. K2 未触发：87 判分项中 56 项 rel_dev≥0.5%、最大 72.98%（R10_2023），近零命中仅 5 项且机制分散，偏差分布健康（非零值聚集）——无「过于完美」特征。
4. skip/infeasible 理由核实：直读 `~/local_data` parquet 坐实——AS5 中债四码 CBA00102/00602/00902/07702 在 bond_index_quote 各 0 行（CBA 前缀唯一码=0）、AS11 financial_future_price 无 vwap/均价列（正则 0 命中），data_catalog 未声称可 derive、无矛盾。
5. 扰动测试触发判断：K2 未触发→非因过于完美；hard 必做已于 final 执行（EVD-08，R11 年化 rel_change 9.96%>0.1%）；「max_dd 0% 变化因回撤在 2022-08 前」与 drawdown.png 最深回撤位于 2015 初互证、自洽；iter2 M2/M3 与硬编码正交、沿用 final 扰动结论成立。
6. minor 意见三条（详情见 `result_antifraud_review.md`）：RA-A01 rolling_sharpe.png 年化 √252 与 M2 后 240 基准不一致（support 图非计分项）；RA-A02 comparison.json `iteration` 字段恒为 0（元数据未递增）；RA-A03 T年化/R11下跌胜率精确命中属口径对齐、AS13 可信度中等已如实披露（最终报告须保留标注）。

verdict: pass_with_issues
