# r007 证据链清单 evidence_manifest.md

> 严格按 `templates/audit/evidence_manifest.md` 落盘。以下均为 quant-verifier
> 对第六次正式运行原始日志与正式 checkpoints 的亲自点收证据。

## E1–E6 规则（断言）

| 规则 | 断言 |
|---|---|
| E1 运行证据 | verifier 亲自执行 main.py；run_log 记录完整命令、退出码、起止时间；exit≠0 一律 fail |
| E2 新鲜度 | 本轮 results 产物 mtime 晚于 src 最近修改 |
| E3 文件完备 | metrics/comparison 可解析且非空；必需图表存在且 >15KB；Excel 非零字节 |
| E4 三方数值一致 | 核心指标核对 metrics、verify_report、Excel |
| E5 样本量合理 | `n_periods` 与 spec 预测区间比对，偏差不超过 10% |
| E6 时间链 | spec → src → results → verify_report mtime 单调递增 |

## 证据条目（E1–E6 逐条落盘，同一规则可有多条）

| 证据ID | 规则(E1-E6) | 声明来源 | 证据类型 | 证据（文件+行号/命令+时间戳） | 佐证 | 核验方式 | 结果(pass/fail) |
|---|---|---|---|---|---|---|---|
| EVD-01 | E1 | 第六次正式 main | 运行日志 | `results/run_log.md#正式无参运行`；`uv run python -m src.r007_cross_market_return_forecasting.main`；2026-07-31T15:45:27–16:00:50+08:00 | `exit=1` | 亲自读取本次原始日志与退出状态 | fail |
| EVD-02 | E1 | 原始 stderr | traceback | `/private/tmp/r007_formal_verify_attempt6.Fpw7D3/stderr_and_resource.log`；SHA256=`befbb41cceecc1b7f801acf241eb1bfc1ac7c14cb63c62d46b0966fdc22be2ad` | `model_set` 行0为 `builtins.tuple`；typed JSON 不支持 | 亲自读取完整 stderr | fail |
| EVD-03 | E1 | 资源记录 | `/usr/bin/time -l` | real/user/sys=`922.15/835.90/86.64s`；max RSS=`44762988544` | 资源尾完整 | 亲自读取 time 尾记录 | pass |
| EVD-04 | E1 | M4 frame 进展 | Parquet 元数据 | prepared=26288370行、Sharpe=360行、daily PnL=534960行、members=81670590行、nested=445800行 | 五张 frame 已落盘 | 亲自读取正式 Parquet 元数据 | pass |
| EVD-05 | E1 | M4/M5 marker | 文件盘点 | `meta/m4.json`、`meta/m5.json` | 两者均缺失 | 亲自逐文件检查 | fail |
| EVD-06 | E1 | M4 组件 | 文件盘点 | `checkpoints/components/m4/` | 601 keys；1202 Parquet；1202 complete sidecar | 亲自逐目录计数并解析 sidecar | pass |
| EVD-07 | E2 | 正式中间产物新鲜度 | mtime | 最新 src=`main.py` 2026-07-31T15:40:13+08:00；五张 M4 frame=15:59:48–16:00:38+08:00 | M4 frame 晚于源码 | 亲自执行 stat | pass |
| EVD-08 | E2 | verifier 失败态产物 | mtime | metrics/comparison/Excel/run_log 均在 attempt6 退出后更新 | 失败态证据晚于正式运行 | 亲自执行 stat | pass |
| EVD-09 | E3 | JSON 结构 | 解析与字段检查 | `metrics.json`、`comparison.json` | 可解析；84 数值项、3 定性项、total=87 | 亲自解析并核计数 | pass |
| EVD-10 | E3 | 必需 PNG | 文件盘点 | `verify_report.md#图表与-Excel-点收` | standards.json 的5张 PNG 全部 missing | 亲自逐文件检查 | fail |
| EVD-11 | E3 | 必需 Excel | 工作簿复核 | `backtest_summary.xlsx` | 5 sheets；冻结首行；R2共84项；复现值为空 | 亲自重开工作簿 | pass |
| EVD-12 | E4 | R2 LASSO qr1 mean | 三方核对 | metrics=null；comparison=null；Excel为空 | 三处一致记录不可用，无正式数值 | 亲自读取三处 | fail |
| EVD-13 | E4 | R2 RIDGE qr4 std | 三方核对 | metrics=null；comparison=null；Excel为空 | 三处一致记录不可用，无正式数值 | 亲自读取三处 | fail |
| EVD-14 | E4 | R2 AdaBoost qr6 mean | 三方核对 | metrics=null；comparison=null；Excel为空 | 三处一致记录不可用，无正式数值 | 亲自读取三处 | fail |
| EVD-15 | E5 | 2016–2021 预测期 | 样本量 | M4 中间 frame 存在；metrics 无 finalized `n_periods` | 正式绩效样本量未形成 | 亲自读取 checkpoints 与 metrics | fail |
| EVD-16 | E6 | spec→src→results→report | mtime | spec=2026-07-26；src最新=2026-07-31T15:40:13；M4/results/report=attempt6退出后 | 时间单调递增 | 亲自执行 stat | pass |

## 扰动测试记录

- 触发原因：hard 难度必做。
- 触发判断：已完成。
- 执行状态：未启动。
- 原因：正式基准运行 `exit=1`，未形成可引用的正式核心指标；本轮派发明确要求
  不得启动扰动运行。
- 扰动参数：未设置。
- 核心指标相对变化：不可计算。
- 临时产物：未创建或删除。
- 结论：fail/not run；没有取得 `>0.1%` 变化断言。

## 审计结论

- E1–E6 全部规则均有至少一条“亲自执行”证据：是。
- 三方数值核对（E4）不一致条数：0；但抽查值均不可用，E4 仍 fail。
- 时间链（E6）是否单调递增：是。
- E1：fail。
- E2：pass。
- E3：fail。
- E4：fail。
- E5：fail。
- E6：pass。
- 本文件不宣布最终门禁结论。
