# Quant Report Reproduction Project（研报复现系统 v2）

量化研报复现项目：给定一份量化研报 PDF，按报告类型（选股因子 factor / 择时 timing / 资产配置 allocation / 固收 fixed_income / 机器学习 ml）与难度差异化复现，产出与原文逐项对齐的策略代码、回测结果，以及带可信度评级的最终报告。所有回复和思考过程必须使用中文。

> **工作流入口**：`/reproduce`（`.claude/skills/reproduce/SKILL.md`）。skill 驱动 `init → extract → plan → spec_audit → implement → code_audit → verify → iterate(条件) → result_audit → oos(条件) → report → review` 十二阶段门禁状态机，主会话遵守六条硬规则（门禁即代码 / 编排与生产分离 / 产物合同逐一点收 / 状态先行 / 审计逐条回应 / 达标判定唯一出口），只派发子 agent、审门禁、调 codex、记账，不亲自撰写 spec / 代码 / 结论。完整设计（状态机明细、门禁定义、agent 契约、防偷懒审计体系 K1–K8）见 `docs/specs/2026-07-07-reproduce-v2-design.md`；本文件只收录编码与产出格式相关的落地约定。

## 快速开始

```bash
/reproduce reports/test.pdf --mode auto      # 新起一份复现
/reproduce continue <report_id>              # 断点续跑
/reproduce status [report_id]                # 状态摘要（无参列出全部 workspace）
```

## Project Structure

```
.
├── CLAUDE.md                     # 项目配置文件（本文件）
├── docs/
│   ├── specs/2026-07-07-reproduce-v2-design.md   # v2 完整设计文档
│   └── legacy/                   # 退役资产备份（旧命令/旧 agent），仅存档不再使用
├── templates/                    # 分诊、类型、审计模板
│   ├── data_catalog.md           # 本地数据目录（分诊对照数据可用性；含 info_publ_date 用法）
│   ├── standards.json            # 分类型机器可读达标标准（check_gates 判定依据）
│   ├── _spec_template.md         # spec.md 骨架 + 要素 ID 规范（D/F/B/R/SA）
│   ├── _plan_template.md         # plan.md 骨架（frontmatter 分诊 + milestones）
│   ├── {type}.md                 # factor/timing/allocation/fixed_income/ml 类型模板
│   ├── audit/                    # 审计产物模板（coverage_matrix / ambiguities / assumptions …）
│   └── codex_prompts/            # codex 三审查点 + second_opinion 的 prompt 骨架
├── tools/                        # 管线工具，仅供主会话 / check_gates 调用，子 agent 不得导入
│   ├── state.py                  # state.json 唯一写入口
│   ├── check_gates.py            # 门禁机器判定
│   └── pdf_extract.py            # PDF → report_text.md + tables_extracted.md
├── reports/{report_id}.pdf       # PDF 收件箱
├── workspace/{report_id}/        # 每份报告的管线文书（取代旧 plan/）
│   ├── state.json                # 该案例的唯一状态源
│   ├── spec/                     # report_text.md / spec.md / coverage_matrix.md / ambiguities.md
│   ├── plan.md / assumptions.md
│   ├── audit/                    # extract_audit / impl_audit / evidence_manifest / audit_responses …
│   ├── iterations/                # iteration_log.md + iter_NN/
│   └── final_report.md
├── common/                       # 公共模块：utils / backtest / data_loader + 按需 {type}_*.py
├── src/{report_id}/              # 策略代码：strategy.py / config.py / main.py
├── output/{report_id}/
│   ├── results/                  # *.xlsx / *.png + metrics.json + comparison.json + run_log.md
│   └── verify_report.md
└── .claude/
    ├── agents/                   # 7 个子 agent 定义
    └── skills/reproduce/         # SKILL.md + stages/*.md（11 张 stage 执行卡）
```

## agent 清单（8 个，职责契约详见设计文档 §六；oos-analyst 为 2026-07-09 增补）

| agent | model | 一句话职责 |
|-------|-------|-----------|
| quant-extractor | opus | 研报说了什么：产 spec 三件套，页码引用制，只陈述不设计 |
| quant-planner | opus | 怎么复现：只读 spec 不读 PDF，做分诊 / 数据映射 / milestone 拆分 / 歧义决议 |
| quant-auditor | opus | 对照审计（spec / code / result 三模式），只拿文件不拿被审者自述 |
| quant-coder | opus | 按 plan 切片实现 + 回填矩阵实现位置，只许冒烟运行不宣布验证结论 |
| quant-verifier | opus | 亲自跑 main.py、出 comparison.json / 图表 / 证据链，触发时跑扰动测试 |
| quant-diagnoser | opus | 迭代归因 + 修正指令，防兜圈，结论三选一 continue / stop_partial / blocked |
| quant-oos-analyst | opus | 复现达标后把策略原样延伸到研报区间之后的数据，评估效应延续/衰减/失效；严禁改策略与参数 |
| quant-reporter | sonnet | 汇总 final_report.md，只汇总不新增结论 |

- 子 agent 不嵌套派发、不启动 Task tool；并行只由主会话发起。
- 子 agent 一律不碰 `state.json`（`tools/state.py` 是唯一写入口，主会话专用）。

## Naming Convention

- `report_id`：小写字母 + 下划线（snake_case），例如 `treasury_futures_timing`
- 文件名 snake_case；类名 PascalCase；函数名 snake_case

## 数据约定

- 财务数据一律按 `info_publ_date`（披露日）做时点对齐，**禁止用 `end_date`（报告期）直接对齐**——`end_date` 无披露滞后，会引入未来函数（code_audit / codex 会逐点核查）。
- 信号严格 **T 日算出、T+1 执行**；滚动窗口训练 / 统计只用历史数据。
- 数据可用性以 `templates/data_catalog.md` 为唯一判定依据（分诊 `feasibility` 字段据此打 available / derive / missing）。

## Output Requirements

### Excel 文件输出

所有回测结果导出为 `.xlsx`，保存至 `output/{report_id}/results/`。具体表格清单按报告类型见 `templates/{type}.md`；通用基线：`backtest_summary.xlsx`（研报值 vs 复现值 vs 偏差）+ 各类型核心数据表。

**格式要求**：多 sheet 存储不同类型数据；第一行表头加粗、冻结首行、自动调整列宽；确保中文正确显示不乱码；结果图表与对应数据放同一 sheet。

### 可视化输出

所有图表 `.png`（300 DPI），保存至 `output/{report_id}/results/`。必需图表清单按类型见 `templates/{type}.md`「必需输出图表」节。

**通用配色与规范**（对所有类型通用）：
- 主色调：蓝色 `#1f77b4`（多头 / 正收益 / 高因子组）、红色 `#d62728`（空头 / 负收益 / 低因子组）；矩阵类用 `RdBu_r`
- 背景样式：seaborn `whitegrid`；中文标题（14 号）、坐标轴标签带单位（12 号）、图例（10 号）、网格线辅助阅读
- 尺寸：时间序列图 `(12, 6)`，条形图 `(10, 6)`
- 不要生成 Emoji 表情

## Code Reuse Guidelines（common/）

优先复用 `common/` 下的公共模块，**禁止在 `src/{report_id}/` 重复实现**：

1. **通用工具** `common/utils.py`：`standardize_factor()` / `neutralize_factor()` / `winsorize()` / `calculate_sharpe()` / `calculate_max_drawdown()` 等
2. **因子回测框架**（factor 类）`common/backtest.py`：`calculate_ic()` / `calculate_rank_ic()` / `quantile_backtest()` / `long_short_backtest()` / `performance_analysis()`
3. **数据加载** `common/data_loader.py`：`load_market_data()` / `get_stock_universe()` / `filter_st_stocks()` / `filter_suspended()`
4. **按类型扩展引擎**（择时 / 配置 / 固收 / ML）：接口规范见 `templates/{type}.md`；首次遇到对应类型时由 quant-coder 创建到 `common/{type}_*.py`，之后所有同类报告复用，**不得写进 `src/`**

`src/{report_id}/` 只放该策略特有实现（`strategy.py` / `config.py` / `main.py`）：

```python
# src/{report_id}/main.py
from common.utils import standardize_factor, winsorize
from common.backtest import calculate_ic, quantile_backtest
from common.data_loader import load_market_data
from .strategy import calculate_factor
```

## 案例目录骨架

新案例由 `uv run python tools/state.py init {report_id} --pdf reports/{report_id}.pdf` 自动创建 `workspace/{id}/{spec,audit,iterations}`、`src/{id}`、`output/{id}/results`，**不需要手工 mkdir**。历史案例（`test` / `momentum_factor` / `long_term_momentum`）已用 `--legacy` 归档：`state.json` 中 stages 全为 `skipped`、`status=done`，`verdict.result` 按各自 `output/{id}/verify_report.md` 的结论人工录入，不回补新流程的审计产物。
