# Quant Report Reproduction Project

量化研报复现项目，使用三个专业agent协作完成研报分析、代码实现和结果验证，所有回复和思考过程必须使用中文。

## Project Structure

```
.
├── CLAUDE.md                 # 项目配置文件
├── reports/                  # 原始研报PDF存放目录
│   └── {report_name}.pdf
├── plan/                     # 研报分析计划目录
│   └── {report_name}/
│       └── plan.md           # 由quant-pdf-reader生成的开发计划
├── common/                   # 公共模块目录（所有策略复用）
│   ├── __init__.py
│   ├── utils.py              # 通用工具函数
│   │                         # - 因子标准化/中性化
│   │                         # - Winsorize/标准化
│   │                         # - 绩效指标计算
│   ├── backtest.py           # 通用回测框架
│   │                         # - IC/ICIR计算
│   │                         # - 分组回测
│   │                         # - 多空组合回测
│   │                         # - 绩效分析
│   └── data_loader.py        # 通用数据加载
│                             # - 行情数据加载
│                             # - 股票池筛选
│                             # - ST/停牌过滤
├── src/                      # 源代码目录
│   └── {report_name}/
│       ├── __init__.py
│       ├── strategy.py       # 核心策略/因子实现（策略特定）
│       ├── config.py         # 策略配置参数（可选）
│       └── main.py           # 主执行脚本（可选）
├── output/                   # 输出结果目录
│   └── {report_name}/
│       ├── results/          # 回测结果
│       │   ├── *.xlsx        # Excel数据文件
│       │   └── *.png         # 图表文件（蓝红配色）
│       └── verify_report.md  # 验证报告
└── data/                     # 本地数据目录 (如需要)
```

## Naming Convention

- `report_name`: 使用小写字母和下划线，例如 `treasury_futures_timing`
- 文件名使用 snake_case
- 类名使用 PascalCase
- 函数名使用 snake_case

## Workflow

### Step 1: PDF Analysis (@quant-pdf-reader)

```bash
# 输入: reports/{report_name}.pdf
# 输出: plan/{report_name}/plan.md
```

分析研报后，在 `plan/{report_name}/` 下生成 `plan.md`，包含：
- 核心策略和创新点
- 回测参数详情
- 数据需求清单
- 分步实现任务

### Step 2: Code Implementation (@quant-coder)

```bash
# 输入: plan/{report_name}/plan.md
# 输出: src/{report_name}/*.py, common/*.py (如果不存在)
```

根据plan.md生成代码：

1. **首次运行**: 如果 `common/` 不存在，先创建公共模块：
   - `common/utils.py` - 通用工具函数
   - `common/backtest.py` - 回测框架
   - `common/data_loader.py` - 数据加载

2. **策略实现**: 在 `src/{report_name}/` 下生成策略特定代码：
   - `strategy.py` - 核心因子/策略实现
   - `config.py` - 参数配置
   - `main.py` - 调用公共模块的主脚本

3. **代码要求**：
   - 遵循Python最佳实践
   - 优先复用 `common/` 中的公共函数
   - 避免重复实现已有功能
   - 代码可执行、可测试

### Step 3: Verification (@quant-verify)

```bash
# 输入: src/{report_name}/, plan/{report_name}/plan.md
# 输出: output/{report_name}/verify_report.md
```

验证实现结果，在 `output/{report_name}/` 下生成验证报告。

## Data Access

- 本地数据路径: `~/local_data/`
- JyPy API文档: https://hedicxl.cn/docs/juyuan/index.html
- 优先使用本地数据，其次使用API

## Output Requirements

### Excel 文件输出

所有回测结果必须导出为 `.xlsx` 格式，保存至 `output/{report_name}/results/`：

- `backtest_summary.xlsx` - 关键指标汇总表
- `ic_series.xlsx` - IC时间序列
- `group_performance.xlsx` - 分组表现明细
- `factor_statistics.xlsx` - 因子统计数据

**格式要求**：
- 使用多sheet存储不同类型数据
- 第一行为表头（加粗）
- 冻结首行
- 自动调整列宽
— 确保中文能够正确显示而不会变成乱码

### 可视化输出

所有图表必须保存为 `.png` 格式（300 DPI），保存至 `output/{report_name}/results/`：

**必需图表**：
1. `ic_series.png` - IC时间序列图
2. `ic_distribution.png` - IC分布直方图
3. `group_cumulative_returns.png` - 分组累计收益曲线
4. `group_returns_bar.png` - 分组收益条形图
5. `net_value_comparison.png` - 净值对比图

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

## Code Standards

- Python 3.10+
- Type hints required
- Pandas/NumPy for data processing
- 函数式编程优先，减少for循环
- 使用method chaining和groupby

## Code Reuse Guidelines

### 使用公共模块（common/）

所有策略应优先使用 `common/` 目录下的公共模块，避免重复实现：

1. **通用工具函数** (`common/utils.py`)：
   - 因子标准化: `standardize_factor()`
   - 因子中性化: `neutralize_factor()`
   - 缩尾处理: `winsorize()`
   - 绩效指标: `calculate_sharpe()`, `calculate_max_drawdown()` 等

2. **回测框架** (`common/backtest.py`)：
   - IC计算: `calculate_ic()`, `calculate_rank_ic()`
   - 分组回测: `quantile_backtest()`
   - 多空组合: `long_short_backtest()`
   - 绩效分析: `performance_analysis()`

3. **数据加载** (`common/data_loader.py`)：
   - 行情数据: `load_market_data()`
   - 股票池: `get_stock_universe()`
   - 过滤器: `filter_st_stocks()`, `filter_suspended()`

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
   - ✅ 使用 `from common.utils import ...`
   - ✅ 使用 `from common.backtest import ...`

