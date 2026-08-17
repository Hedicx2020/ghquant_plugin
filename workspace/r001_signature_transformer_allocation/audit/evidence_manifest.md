# 证据链清单 evidence_manifest.md · r001_signature_transformer_allocation

> quant-verifier 随跑随记，全难度必做。核验方式为「亲自执行」——转述 coder 自述不算证据。reproduction_mode=experimental。完整训练档因超子 agent Bash 时限由主会话后台执行、verifier 逐行核对其日志与产物；扰动测试为 verifier 本会话亲跑。

---

## E1–E6 规则（断言）

| 规则 | 断言 |
|------|------|
| E1 运行证据 | 亲自执行 main.py；run_log.md 记完整命令/退出码/起止时间戳；exit≠0 一律 fail，禁「部分成功」 |
| E2 新鲜度 | results/ 产物 mtime 晚于 src/ 最近修改 |
| E3 文件完备 | metrics.json 可解析且 comparison 非空；必需图表全存在且 >15KB；Excel 非零字节 |
| E4 三方数值一致 | 抽核心指标逐位核对 metrics.json == verify_report.md == backtest_summary.xlsx（仅核实际存在的对象） |
| E5 样本量合理 | n_periods 与 spec 区间推算比对 |
| E6 时间链 | spec → src → results → verify_report 的 mtime 单调递增 |

---

## 证据条目（E1–E6 逐条落盘）

| 证据ID | 规则 | 声明来源 | 证据类型 | 证据（文件+行号/命令+时间戳） | 佐证 | 核验方式 | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EVD-01 | E1 | 称"主表全档运行成功" | 运行日志 | verify_main_full.log:1-2,175-176 命令 `uv run python -m src.r001_...main --export`，START 2026-07-14 11:05:02 / END 11:20:34 | EXIT_CODE 0 (exit=0) | 逐行读取日志确认命令与退出码 | pass |
| EVD-02 | E1 | 称"消融全档运行成功" | 运行日志 | verify_ablation_full.log:1-2,44-45 命令 `run_ablation_full.py`，START 11:23:14 / END 11:29:59 总耗时 403.5s | EXIT_CODE 0 (exit=0) | 逐行读取日志确认退出码 | pass |
| EVD-03 | E1 | verifier 亲跑扰动 | 亲自执行 | `main --smoke --top-n 20` 15s、`--top-n 30` 21s，2026-07-14 | 两跑 exit=0 | 本会话 Bash 亲自执行并读退出码 | pass |
| EVD-04 | E2 | 产物新鲜度 | mtime 比对 | results/*.png,xlsx = 2026-07-14T11:20:32~33；src/main.py = 2026-07-14T10:53:37 | 产物晚于源码约27min | 亲自 `stat -f %Sm` 比对 | pass |
| EVD-05 | E3 | 图表/Excel 完备 | 文件属性 | weight_evolution.png 800645B / portfolio_nav 488821B / drawdown 352124B / rolling_volatility 209334B / asset_contribution 130266B；backtest_summary.xlsx 11637B（**实际 2 sheet：主绩效表(6,10) + 净值序列(60,7)**）；metrics.json/comparison.json 可解析 | 5 PNG 均 >15KB、xlsx 非零 | 亲自 `ls -la` + pandas 读 xlsx sheet_names（免回显污染：python 写文件后 Read） | pass |
| EVD-06 | E4 | 主表数值真实 | 三方核对 | **主表 24 值三方一致**：metrics.json.main_performance == xlsx『主绩效表』sheet（SIT 0.734784/1.187893/0.141235/1.601368、EW 0.404956、GMV 0.940075、CVaR 0.830201、HRP 0.594495、DLinear 0.730579）== verify_main_full.log 逐位相同 | 24 项逐位相同、0 不一致 | 亲自 pandas 读 xlsx 主绩效表 sheet（写文件后 Read）逐位比对日志与 metrics.json | pass |
| EVD-07 | E4 | SA1-4 数值真实 | 两方核对 | **SA1/SA2/SA3/SA4 数据不在 xlsx**（xlsx 仅 2 sheet），故核 metrics.json == verify_ablation_full.log：SA1 SIT(Ours)0.8713/w/o CVaR-0.2216/w/o AssetAttn0.5815/w/o FinBias0.8761/w/o Gate0.8780、SA2 Pearson0.0553、SA3/SA4 网格 | metrics.json 与日志逐位相同 | 亲自读 metrics.json 与消融日志逐位比对 | pass |
| EVD-08 | E5 | 样本量合理 | 区间推算 | 日志 `n_periods=60（目标=60=12×5，覆盖 2020-01~2024-12）` | 与 spec test 区间一致，偏差 0% | 读日志 L148 核对 | pass |
| EVD-09 | E6 | 无先写结论后跑数 | mtime 链 | spec.md 2026-07-13T02:41 → src/main.py 2026-07-14T10:53 → results 11:20 → verify_report.md(本次写) | 单调递增 | 亲自 `stat` 收集四段 mtime | pass |

> 口径纠正（result_audit CDX-R-02）：先前一版 EVD 误称 xlsx 含多个 sheet（如主绩效表_对照/SA1_模块消融 等），系 Bash 回显被占位污染导致的误读；经免污染核验（python 写 sheet 名到文件后 Read），xlsx 实际仅两个 sheet（主绩效表 + 净值序列）。E4/E6 声明已改为只记实际核到的对象：主表 24 值三方一致（含 xlsx），SA1-4 为 metrics.json 与日志两方一致。
> 净值序列 sheet 说明（CDX-R-05）：其 SIT 列末值 1.7546 = best-config **seed=0 单种子代表路径**（非主表 3 种子聚合 FinalWealth 1.6014），portfolio_nav.png 同源；两者口径不同、勿混用。

---

## 扰动测试记录

- **触发原因**: hard 难度必做一次。
- **扰动参数**: 以 `--top-n` 覆盖 universe 资产数改变输入（等效换资产池扰动；main.py 无 test_end 参数，故取 top-n 路径，不改源码）。
- **执行方式**: smoke 缩减档分别 `--top-n 20`、`--top-n 30` 各跑一次，stdout 重定向至 `results/perturb_check/pk_top{20,30}.log`（临时目录，跑完已 `rm -rf` 删除，仅登记本记录）。
- **核心指标相对变化**:
  - SIT Sharpe: top-20=0.4123 → top-30=0.3151，相对变化 |0.3151−0.4123|/0.4123 = **23.6%**（断言 >0.1%，通过）。
  - SIT Wealth: 1.3288 → 1.2196，相对变化 8.2%；Sortino: 0.7375 → 0.5411，26.6%。
- **旁证（同类耦合）**: SA1「w/o CVaR」使 SIT Sharpe 0.8713→-0.2216（ΔSharpe -1.0929），输出亦强耦合于训练目标。
- **结论**: 通过。核心指标随输入 universe 显著变化，远超 0.1% 阈值，**无硬编码嫌疑**（非「输出与输入解耦」）。

---

## 审计结论

- E1–E6 全部规则均有至少一条「亲自执行」证据落盘: **是**（EVD-01~09 覆盖 E1×3/E2/E3/E4×2/E5/E6）。
- 三方数值核对（E4）不一致条数: **0**（主表 24 值三方一致；SA1-4 两方一致）。
- 时间链（E6）是否单调递增: **是**。
- 扰动测试（hard 必做）: 已执行、已记录、临时输出已删除，结论通过。
