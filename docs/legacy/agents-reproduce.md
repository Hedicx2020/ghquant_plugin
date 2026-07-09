---
name: reproduce
description: Guide for reproducing quantitative research report from PDF - triage by type/difficulty, milestone-driven, type-aware verification
---

# 量化研报复现工作流

按**报告类型 + 难度**差异化复现研报：分诊 → 按 milestone 迭代「实现→验证」→（可选）可视化。
主流程（你）负责编排；子 agent 自身不并行、不嵌套调用其它 agent，**并行只由主流程发起**。

## Usage

```
/reproduce <pdf_file_path>
```
示例：`/reproduce reports/treasury_futures_timing.pdf`

---

## Phase 0：初始化

1. 验证 `$ARGUMENTS` 指定的 PDF 存在；从文件名提取 `report_name`（snake_case）。
2. 建目录：`plan/{report_name}`、`src/{report_name}`、`output/{report_name}/results`。
3. 确认 `common/` 与 `templates/` 存在。
4. TaskCreate 创建初始两步：`Step0 确认PDF`（标 completed）、`Step1 分诊+生成plan`。

---

## Phase 1：分诊 + 生成 plan（@quant-pdf-reader）

1. 单独调用 `@quant-pdf-reader` 分析 PDF。
2. 等待输出 `plan/{report_name}/plan.md`（**顶部含 frontmatter**：type/tags/difficulty/feasibility/data_requirements/milestones/template）。
3. 标记 Step1 completed。

---

## Phase 1.5：读 frontmatter 决策（主流程，核心新增）

读取 plan.md 的 frontmatter：

1. **可行性闸门**：若 `feasibility: blocked`（核心数据 missing / 核心方法无法确定），用 **AskUserQuestion** 停下问用户：
   提供外部数据 / 简化复现（降级方案）/ 跳过该报告。其余情况（ok / partial）**自动继续**。
2. **选类型模板**：据 `type` 取 `templates/{type}.md`，作为后续 coder/verify 的规范输入。
3. **选编排策略**：据 `difficulty` 查下表。
4. **动态建任务**：按 `milestones` 用 TaskCreate 创建任务并设依赖链（见下）。

### 编排策略表（difficulty → 编排）

| difficulty | 编排 |
|------------|------|
| **easy** | 1 个 milestone。主流程串行：`@quant-coder` 实现 → `@quant-verify` 验证。 |
| **medium** | 2~3 个 milestone。**单个 coder** 逐 milestone 迭代实现，每 milestone 后 `@quant-verify` 验证。 |
| **hard** | ≥3 个 milestone。主流程**按 milestone 派发独立 coder 子实例**（每个传入该 milestone 的 plan 切片 + `templates/{type}.md`，上下文隔离）；某 milestone 内若含多个**独立**模块（如多因子）可**并行派发**多个 coder；每 milestone verify 通过后**再派一个独立 `@quant-verify` 实例做对抗式复核**（模式 B）。 |

### 动态建任务规则

- 每个 milestone：`mX-实现`（coder）+ `mX-验证`（verify）。hard 额外加 `mX-复核`（verify 模式B）。
- easy 可把实现+验证合并为一个执行单元。
- 依赖链：`mX-实现` blockedBy 上一 milestone 完成；`mX-验证` blockedBy `mX-实现`；`mX-复核` blockedBy `mX-验证`。
- 末尾可选 `可视化`（visualizer）。

---

## Phase 2..N：按 milestone 循环

对每个 milestone（按依赖顺序）：

1. TaskUpdate 标 `mX-实现` in_progress；调 `@quant-coder`（hard 为独立子实例，传 plan 切片 + 类型模板）。
   - 首次遇到非 factor 类型时，coder 会按 `templates/{type}.md` 把回测引擎创建到 `common/{type}_*.py`。
2. 实现完成 → 调 `@quant-verify`（模式 A）跑回测、按**类型验证标准矩阵**对数，写入 `verify_report.md` 对应小节。
   - 指标超标：先 `/codex:rescue` 调试；多次不收敛才停下问用户。
3. hard / 含 ml 标签：verify 通过后再派**独立 `@quant-verify`（模式 B 对抗复核）**——查公式符合性、未来函数、数据对齐、滚动训练泄漏。
   - 复核**不通过** → 回 `@quant-coder` 修正，重走该 milestone。
4. 各步完成后 TaskUpdate 标 completed，TaskList 确认状态。

---

## Phase final：可视化（可选，@quant-visualizer）

全部 milestone 通过后，可调 `@quant-visualizer` 扫描 `plan/`、`output/` 生成 `output/dashboard.html`。

---

## API 行为约束（重要）

| 规则 | 说明 |
|------|------|
| 子 agent 不嵌套 | pdf-reader/coder/verify/visualizer **自身不调用或派发任何其它 agent**，不启动 Task tool（API 400 根源） |
| 并行只由主流程发起 | 仅主流程可同时派发多个 coder 子实例处理**独立**模块；有依赖的步骤串行 |
| 状态/文件校验 | 每步完成后 TaskList 确认状态、确认输出文件存在再继续 |

---

## 目录结构

```
templates/{data_catalog,_plan_template,factor,timing,allocation,fixed_income,ml}.md  # 分诊与类型模板
reports/{report_name}.pdf                  # 原始 PDF
plan/{report_name}/plan.md                 # Phase 1 输出（含 frontmatter）
src/{report_name}/{strategy,config,main}.py  # 各 milestone 实现
common/{utils,backtest,data_loader}.py + {type}_*.py  # 公共层（类型引擎按需沉淀）
output/{report_name}/results/*.{xlsx,png}  # 结果（图表清单按类型）
output/{report_name}/verify_report.md      # 验证报告（按 milestone 分节）
```

## 质量标准

- 通过标准**按类型**见 `templates/{type}.md`（不再是统一 5%）。
- 代码：Type hints + PEP 8，函数式/向量化优先。
- ML 类分层验证：数据/特征层 <5%（精确），模型层方向性一致。
