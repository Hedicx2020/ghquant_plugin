# Quant Report Reproduction Project

量化研报复现项目，使用专业 agent 协作完成研报分析、代码实现和结果验证；支持多种报告类型（选股因子 / 择时 / 资产配置 / 固收 / 机器学习），**按类型与难度差异化处理**。所有回复和思考过程必须使用中文。

> 工作流入口 `Command/reproduce.md`；分诊与类型模板见 `templates/`。

## Project Structure

```
.
├── CLAUDE.md                 # 项目配置文件
├── templates/                # 分诊与类型模板（工作流配置）
│   ├── data_catalog.md       # 本地数据目录（分诊对照数据可用性）
│   ├── _plan_template.md     # 通用 plan 骨架（frontmatter + 正文章节）
│   └── {type}.md             # factor/timing/allocation/fixed_income/ml 类型模板
│                             #   （数据清单 / common 接口规范 / 图表清单 / 验证标准）
├── reports/                  # 原始研报PDF存放目录
│   └── {report_name}.pdf
├── plan/                     # 研报分析计划目录
│   └── {report_name}/
│       └── plan.md           # quant-pdf-reader 生成；顶部含分诊 frontmatter
│                             #   （type/difficulty/feasibility/data_requirements/milestones）
├── common/                   # 公共模块目录（所有策略复用）
│   ├── __init__.py
│   ├── utils.py              # 通用工具函数（标准化/中性化/Winsorize/绩效指标）
│   ├── backtest.py           # 因子回测框架（IC/ICIR、分组、多空、绩效）
│   ├── data_loader.py        # 通用数据加载（行情/股票池/ST停牌过滤）
│   └── {type}_*.py           # 按类型扩展的回测引擎，遇到对应类型报告时按需创建：
│                             #   timing_backtest.py / allocation_backtest.py
│                             #   fixed_income.py / ml_pipeline.py（接口规范见 templates/{type}.md）
├── src/                      # 源代码目录
│   └── {report_name}/
│       ├── __init__.py
│       ├── strategy.py       # 核心策略/因子实现（策略特定）
│       ├── config.py         # 策略配置参数（可选）
│       └── main.py           # 主执行脚本（可选）
├── output/                   # 输出结果目录
│   └── {report_name}/
│       ├── results/          # 回测结果（xlsx + png，图表清单按类型见 templates/）
│       └── verify_report.md  # 验证报告
└── data/                     # 本地数据目录 (如需要)
```

## Naming Convention

- `report_name`: 使用小写字母和下划线，例如 `treasury_futures_timing`
- 文件名使用 snake_case
- 类名使用 PascalCase
- 函数名使用 snake_case

## Output Requirements

### Excel 文件输出

所有回测结果必须导出为 `.xlsx` 格式，保存至 `output/{report_name}/results/`。

**具体表格清单按报告类型不同** —— 见 `templates/{type}.md`。通用基线（各类型都应有）：
- `backtest_summary.xlsx` - 关键指标汇总表（研报值 vs 复现值 vs 偏差）
- 各类型核心数据表（因子类：IC序列/分组表现；择时类：净值/仓位/分年度；等）

**格式要求**：
- 使用多sheet存储不同类型数据
- 第一行为表头（加粗），冻结首行，自动调整列宽， 确保中文能够正确显示而不会变成乱码

### 可视化输出

所有图表必须保存为 `.png` 格式（300 DPI），保存至 `output/{report_name}/results/`：

**必需图表清单按报告类型不同** —— 见 `templates/{type}.md` 的「必需输出图表」节。例：
- `factor` 类：ic_series / ic_distribution / group_cumulative_returns / group_returns_bar / net_value_comparison
- `timing` 类：net_value / drawdown / position_signal / yearly_returns / rolling_sharpe
- `allocation` / `fixed_income` / `ml` 类：见各自模板

以下**配色与规范对所有类型通用**：

**配色标准**：
- 主色调：蓝色 (#1f77b4) 和 红色 (#d62728)
- 蓝色：多头、正收益、高因子组
- 红色：空头、负收益、低因子组
- 使用 matplotlib 的 'RdBu_r' colormap
- 背景样式：seaborn 'whitegrid'

**图表规范**：
- 中文标题（字号14）
- 坐标轴标签带单位（字号12）
- 图例（字号10）
- 网格线辅助阅读
- 时间序列图尺寸：(12, 6)
- 条形图尺寸：(10, 6)

### 将所有结果图标和数据放置在一个excel中，数据对应的图放同一个sheet

## Code Reuse Guidelines

### 使用公共模块（common/）

所有策略应优先使用 `common/` 目录下的公共模块，避免重复实现：

1. **通用工具函数** (`common/utils.py`)：
   - 因子标准化: `standardize_factor()`
   - 因子中性化: `neutralize_factor()`
   - 缩尾处理: `winsorize()`
   - 绩效指标: `calculate_sharpe()`, `calculate_max_drawdown()` 等

2. **因子回测框架** (`common/backtest.py`，factor 类专用)：
   - IC计算: `calculate_ic()`, `calculate_rank_ic()`
   - 分组回测: `quantile_backtest()`
   - 多空组合: `long_short_backtest()`
   - 绩效分析: `performance_analysis()`

3. **数据加载** (`common/data_loader.py`)：
   - 行情数据: `load_market_data()`
   - 股票池: `get_stock_universe()`
   - 过滤器: `filter_st_stocks()`, `filter_suspended()`

4. **按类型扩展的回测引擎**（择时/配置/固收/ML）：
   - 接口规范见 `templates/{type}.md` 的「common 接口规范」节。
   - 首次遇到对应类型报告时，由 quant-coder **创建到 `common/`**（如 `common/timing_backtest.py`），之后所有同类报告复用，**不要写进 `src/`**。

### 策略特定代码（src/{report_name}/）

每个策略目录只包含该策略特有的实现：

- `strategy.py`: 核心因子计算逻辑
- `config.py`: 策略参数配置
- `main.py`: 调用公共模块进行回测的主脚本

**示例导入**：
```python
# 在 src/{report_name}/main.py 中
from common.utils import standardize_factor, winsorize
from common.backtest import calculate_ic, quantile_backtest
from common.data_loader import load_market_data
from .strategy import calculate_factor
```

## File Creation Rules

### 首次创建项目时

如果 `common/` 目录不存在，首先创建公共模块：

```bash
mkdir -p common
# 创建公共模块文件
touch common/__init__.py
touch common/utils.py
touch common/backtest.py
touch common/data_loader.py
```

### 创建新研报项目

每个新研报必须：

1. 创建目录结构:
   ```bash
   mkdir -p plan/{report_name}
   mkdir -p src/{report_name}
   mkdir -p output/{report_name}/results
   ```

2. 在 `src/{report_name}/` 下创建基础文件:
   ```bash
   touch src/{report_name}/__init__.py
   touch src/{report_name}/strategy.py
   touch src/{report_name}/config.py    # 可选
   touch src/{report_name}/main.py      # 可选
   ```

3. 所有相关文件必须放在对应的 `{report_name}` 子目录下

4. **禁止在策略目录重复实现公共功能**：
   - ❌ 不要创建 `src/{report_name}/utils.py`
   - ❌ 不要创建 `src/{report_name}/backtest.py`
   - ❌ 不要把按类型回测引擎（择时/配置/固收/ML）写进 `src/`
   - ✅ 使用 `from common.utils import ...`
   - ✅ 使用 `from common.backtest import ...`
   - ✅ 类型引擎首次创建到 `common/{type}_*.py`，按 `templates/{type}.md` 规范，之后复用

