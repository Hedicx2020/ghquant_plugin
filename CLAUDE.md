# Quant Report Reproduction Project（研报复现系统 v3）

量化研报复现项目：给定一份量化研报 PDF，按报告类型（选股因子 factor / 择时 timing / 资产配置 allocation / 固收 fixed_income / 机器学习 ml）与难度差异化复现，产出与原文逐项对齐的策略代码、回测结果，以及带可信度评级的最终报告。所有回复和思考过程必须使用中文。

> **工作流入口**：`/reproduce`（`skills/reproduce/SKILL.md`）。流程由确定性内核 `tools/flow.py` 推进，十二个阶段（init → extract → plan → spec_audit → implement → code_audit → verify → iterate → result_audit → oos → report → review）的调度、门禁、熔断、检查点都在代码里；主会话只做「取工单（`flow next`）→ 照单派发 → 点收（`flow done`）」的循环，不亲自撰写 spec / 代码 / 结论，不直接写 `state.json`。v3 的设计与实施记录见 `docs/specs/2026-11-21-reproduce-v3-design.md`；门禁定义、agent 契约、审计体系 K1–K8 以 `docs/specs/2026-07-07-reproduce-v2-design.md` 为准。本文件（CLAUDE.md）只收录编码与产出格式相关的落地约定。

## 快速开始

```bash
/reproduce reports/test.pdf --mode auto      # 新起一份复现
/reproduce continue <report_id>              # 断点续跑
/reproduce status [report_id]                # 状态摘要（无参列出全部案例）

# 内核命令（只读的几条随时可跑）
uv run python tools/flow.py status [id]      # 进度
uv run python tools/flow.py explain <键>     # 某个阶段、门禁检查项或检查点怎么处理（explain index 看目录）
uv run python tools/flow.py cost <id>        # 用量汇总
uv run python tools/flow.py data probe       # 体检数据目录，生成数据实况表
```

进度看板是静态页：`workspace/<id>/board.html`，全部案例 `workspace/board.html`。

## 目录

| 路径 | 内容 |
|---|---|
| `skills/reproduce/` | `/reproduce` 技能：`SKILL.md`、宿主适配卡 `adapters/`、按需取的处理说明 `explain/`、`stages/`（setup 与旧执行卡） |
| `agents/quant-*.md` | 8 个角色合同正本（`.codex/agents/*.toml` 由 `tools/sync_codex_agents.py` 生成） |
| `templates/` | 类型模板 `{type}.md`、达标标准 `standards.json`、spec / plan 骨架、审计模板、外审 prompt |
| `tools/` | 内核与管线工具（`flow.py`、`flowlib/`、`state.py`、`check_gates.py` 等），**仅供主会话与内核调用，子 agent 不得导入** |
| `reports/{id}.pdf` | PDF 收件箱 |
| `workspace/{id}/` | 管线文书：`state.json`（唯一状态源）、`events.jsonl`、`flow/`（任务文件与回执，内核写）、`reviews/`、`spec/`、`plan.md`、`assumptions.md`、`audit/`、`iterations/`、`final_report.md` |
| `common/` | 公共模块：`utils` / `backtest` / `data_loader` + 按需 `{type}_*.py` |
| `src/{id}/` | 策略代码：`strategy.py` / `config.py` / `main.py` |
| `output/{id}/` | `results/`（xlsx、png、`metrics.json`、`comparison.json`、`data_manifest.json`、`run_log.md`）、`results_mock/`（mock 试跑的结果，与真实结果隔离）、`verify_report.md` |

## 角色与纪律

8 个角色：quant-extractor（研报说了什么，产 spec，页码引用制）、quant-planner（只读 spec 做分诊、数据映射与 milestone 拆分）、quant-auditor（spec / code / result 对照审计）、quant-coder（按 plan 实现，只许冒烟运行）、quant-verifier（亲自跑 main.py，出对比与证据链）、quant-diagnoser（迭代归因）、quant-oos-analyst（样本外延伸，严禁改策略与参数）、quant-reporter（汇总报告，sonnet；其余 opus）。职责契约见 v2 设计文档 §六。

- 内核派发的任务以任务文件为准（`workspace/<id>/flow/tasks/`）：只读里面给的内容，缺什么用 `flow get` 取；对矩阵、假设登记簿的回填写进回执，由内核核对后合并。
- 子 agent 不嵌套派发、不启动 Task tool；并行只由主会话发起。
- 子 agent 一律不碰 `state.json`、`events.jsonl` 与 `workspace/<id>/flow/` 下内核写的文件。
- 经济模式（`.reproduce.json` 的 `economy`）下 extractor / verifier / oos-analyst 改用经济档模型。

## Naming Convention

- `report_id`：小写字母 + 下划线（snake_case），新案例自动编号为 `rNNN_<slug>`，例如 `r011_treasury_futures_timing`
- 文件名 snake_case；类名 PascalCase；函数名 snake_case

## 数据约定

- 财务数据一律按 `info_publ_date`（披露日）做时点对齐，**禁止用 `end_date`（报告期）直接对齐**——`end_date` 无披露滞后，会引入未来函数（code_audit 与外审会逐点核查）。
- 信号严格 **T 日算出、T+1 执行**；滚动窗口训练 / 统计只用历史数据。
- 取数一律经 `common/data_loader.py`：`data_path(name)` 取文件路径（先查本案例的覆盖目录，再查数据根），`read_table(name, columns=…, start=…, end=…)` 读表（带列裁剪与日期下推）；输出目录用 `results_dir()`。不要在 `src/` 里拼数据根路径直接 `read_parquet`，也不要为 mock 试跑写分支——试跑靠这三个函数切换目录，每次运行读了哪些文件会自动记进 `data_manifest.json`。
- 数据可得性以内核的数据体检为准：`flow data probe` 生成的数据实况表，加上 plan 阶段逐条核对数据需求的结果（`workspace/<id>/data_check.json`）。`templates/data_catalog.md` 只是说明性文字；仍由旧执行卡驱动的案例沿用它作判定依据。
- 数据有缺口时由人选处置方式（补数据 / 等价替代 / 缩小范围 / 先用 mock 试跑 / 砍掉相关要素 / 终止），agent 无权自行降级。

## Output Requirements

- **Excel**：所有回测结果导出为 `.xlsx`，存到 `output/{report_id}/results/`（代码里用 `results_dir()` 取）。表格清单按类型见 `templates/{type}.md`；通用基线是 `backtest_summary.xlsx`（研报值 vs 复现值 vs 偏差）加各类型核心数据表。多 sheet 存不同类型数据；首行表头加粗、冻结首行、自动列宽；中文不乱码；图表与对应数据放同一 sheet。
- **图表**：`.png`（300 DPI），同一目录；必需图表清单见 `templates/{type}.md`「必需输出图表」节。蓝色 `#1f77b4`（多头 / 正收益 / 高因子组）、红色 `#d62728`（空头 / 负收益 / 低因子组），矩阵类用 `RdBu_r`；seaborn `whitegrid`；中文标题（14 号）、坐标轴标签带单位（12 号）、图例（10 号）；时间序列图 `(12, 6)`，条形图 `(10, 6)`；不要生成 Emoji 表情。
- **机器生成块**：`verify_report.md` 与 `final_report.md` 里由 `<!-- flow:generated … BEGIN -->` 和 `<!-- flow:generated … END -->` 围起来的部分（指标对比总表、达标计数、产物清单、假设登记簿）由内核从 `comparison.json` 等机器产物生成，不要手改，改了会被覆盖。正文引用指标编号，不重抄数值。

## Code Reuse Guidelines（common/）

优先复用 `common/` 下的公共模块，**禁止在 `src/{report_id}/` 重复实现**：

1. **通用工具** `common/utils.py`：`standardize_factor()` / `neutralize_factor()` / `winsorize()` / `calculate_sharpe()` / `calculate_max_drawdown()` 等
2. **因子回测框架**（factor 类）`common/backtest.py`：`calculate_ic()` / `calculate_rank_ic()` / `quantile_backtest()` / `long_short_backtest()` / `performance_analysis()`
3. **数据加载** `common/data_loader.py`：`data_path()` / `read_table()` / `results_dir()`，以及 `load_market_data()` / `get_stock_universe()` / `filter_st_stocks()` / `filter_suspended()` 等现成的行情与状态函数
4. **按类型扩展引擎**（择时 / 配置 / 固收 / ML）：接口规范见 `templates/{type}.md`；首次遇到对应类型时由 quant-coder 创建到 `common/{type}_*.py`，之后所有同类报告复用，**不得写进 `src/`**

`src/{report_id}/` 只放该策略特有实现（`strategy.py` / `config.py` / `main.py`），从 `common.utils`、`common.backtest`、`common.data_loader` 导入公共函数。

## 案例骨架与旧案例

新案例由内核建立（`flow init`，平时由 `/reproduce` 代为调用）：自动编号、创建目录、把 PDF 转成文本、查同一份 PDF 是否已有案例、体检数据目录，**不需要手工 mkdir**。

v3 之前建立的案例不强制迁移：在途阶段按 `skills/reproduce/stages/legacy/` 的执行卡跑完，`flow migrate <id>` 把状态文件升级到 v2 格式后可交给内核接着推进（会留 `state.v1.json` 备份）。历史案例（`test` / `momentum_factor` / `long_term_momentum`）已用 `--legacy` 归档：stages 全为 `skipped`、`status=done`，`verdict.result` 按各自 `verify_report.md` 的结论人工录入，不回补新流程的审计产物。
