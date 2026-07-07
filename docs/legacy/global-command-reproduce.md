---
name: reproduce
description: Guide for reproducing quantitative research report from PDF - step by step workflow with task tracking
---

# Quant Report Reproduction Guide

分阶段复现量化研报的工作流指南。使用 Task 系统跟踪进度，严格串行执行避免 API 400 错误。

## Usage:

```
/reproduce <pdf_file_path>
```

## Example:

```
/reproduce reports/treasury_futures_timing.pdf
```

---

## IMPORTANT: 执行前必读

收到 `/reproduce` 命令后，**必须按以下顺序执行**：

### Phase 0: 初始化任务列表

**首先**，使用 TaskCreate 工具创建以下 4 个任务（按顺序创建）：

1. **Task: 确认PDF路径和report_name**
   - subject: "Step 0: 确认PDF路径和report_name"
   - description: "验证PDF存在，提取report_name，创建目录结构"
   - activeForm: "确认PDF路径"

2. **Task: PDF分析**
   - subject: "Step 1: PDF分析 (quant-pdf-reader)"
   - description: "使用 @quant-pdf-reader 分析研报，输出 plan/{report_name}/plan.md"
   - activeForm: "分析PDF生成计划"

3. **Task: 代码实现**
   - subject: "Step 2: 代码实现 (quant-coder)"
   - description: "使用 @quant-coder 根据 plan.md 实现代码到 src/{report_name}/"
   - activeForm: "实现策略代码"

4. **Task: 验证结果**
   - subject: "Step 3: 验证结果 (quant-verify)"
   - description: "使用 @quant-verify 验证实现，输出 verify_report.md"
   - activeForm: "验证回测结果"

**然后**，使用 TaskUpdate 设置依赖关系：
- Step 1 blockedBy Step 0
- Step 2 blockedBy Step 1
- Step 3 blockedBy Step 2

---

## Phase 1: 执行工作流

任务创建完成后，按顺序执行：

### Step 0: 确认PDF路径和report_name

1. 验证 `$ARGUMENTS` 指定的 PDF 文件存在
2. 从文件名提取 report_name：
   ```
   reports/treasury_futures_timing.pdf → treasury_futures_timing
   ```
3. 创建目录结构：
   ```bash
   mkdir -p plan/{report_name}
   mkdir -p src/{report_name}
   mkdir -p output/{report_name}/results
   ```
4. 检查 `common/` 是否存在
5. **完成后**: TaskUpdate 标记 Step 0 为 completed

---

### Step 1: PDF Analysis (@quant-pdf-reader)

**前置条件**: Step 0 已完成

1. TaskUpdate 标记 Step 1 为 in_progress
2. 使用 @quant-pdf-reader agent 分析 PDF
3. 等待输出: `plan/{report_name}/plan.md`
4. 验证 plan.md 内容完整
5. **完成后**: TaskUpdate 标记 Step 1 为 completed

**避免 API 400**:
- 单独调用此 agent
- 等待完全结束后再继续

---

### Step 2: Code Implementation (@quant-coder)

**前置条件**: Step 1 已完成，plan.md 存在

1. TaskUpdate 标记 Step 2 为 in_progress
2. 使用 @quant-coder agent 实现代码
3. 等待输出:
   - `src/{report_name}/__init__.py`
   - `src/{report_name}/strategy.py`
   - `src/{report_name}/config.py` (可选)
   - `src/{report_name}/main.py` (可选)
4. 验证代码文件存在且可执行
5. **完成后**: TaskUpdate 标记 Step 2 为 completed

**避免 API 400**:
- 单独调用此 agent
- 不要同时创建多个文件的 agent

---

### Step 3: Verification (@quant-verify)

**前置条件**: Step 2 已完成，代码文件存在

1. TaskUpdate 标记 Step 3 为 in_progress
2. 使用 @quant-verify agent 验证
3. 等待输出: `output/{report_name}/verify_report.md`
4. 检查验证结果是否通过（偏差 < 5%）
5. **完成后**: TaskUpdate 标记 Step 3 为 completed

---

## API 400 错误预防清单

| 规则 | 说明 |
|------|------|
| 严格串行 | 一个 agent 完成后再启动下一个 |
| 禁止并行 | 不要同时调用多个 Task tool |
| 禁止嵌套 | agent 内部不要调用其他 agent |
| 状态检查 | 每步完成后用 TaskList 确认状态 |
| 文件验证 | 确认输出文件存在后再继续 |

---

- 

## Directory Structure

```
.
├── reports/
│   └── {report_name}.pdf           # 原始 PDF
├── plan/
│   └── {report_name}/
│       └── plan.md                 # Step 1 输出
├── src/
│   └── {report_name}/
│       ├── __init__.py
│       ├── strategy.py             # Step 2 输出
│       ├── config.py
│       └── main.py
├── common/                         # 公共模块（复用）
│   ├── utils.py
│   ├── backtest.py
│   └── data_loader.py
└── output/
    └── {report_name}/
        ├── results/                # 回测结果
        └── verify_report.md        # Step 3 输出
```

## Quality Standards

- 偏差容忍度: < 5%
- 代码规范: Type hints + PEP 8
- 函数式编程优先
