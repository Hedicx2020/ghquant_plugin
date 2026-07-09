# 类型模板 · factor（截面选股因子）

## 1. 适用范围
A 股（或港美股）**截面选股因子**类研报：构造一个因子，按截面排序分组/多空，用 IC、分组收益、多空组合评估。最成熟、现有 common 直接支持。

## 2. plan 正文结构（在通用骨架上特化）
- 因子定义与公式（逐步骤）
- 预处理：缩尾 → 标准化 →（行业/市值）中性化
- IC 分析（IC / RankIC / ICIR）
- 分组回测（默认 5 或 10 组）+ 多空组合
- 换手率与衰减

## 3. 所需数据（对照 data_catalog）
| 数据 | 文件 | 必需 |
|------|------|------|
| 日行情（复权） | `ashare_stock_price_forward.parquet` | 是 |
| 涨跌幅/市值/换手 | `ashare_stock_trade.parquet` | 是 |
| 估值（如因子涉及） | `ashare_stock_value.parquet` | 视因子 |
| 行业（中性化） | `ashare_stock_industry.parquet` | 视因子 |
| ST/停牌过滤 | `ashare_stock_st.parquet` / `ashare_stock_suspend.parquet` | 是 |
| 股票池（指数成分） | `ashare_index_components.parquet` | 视报告 |
| 调仓日 | `ashare_tradeday.parquet` | 是 |

## 4. common 接口规范（**复用现有，无需新建**）
直接 import：
```python
from common.utils import winsorize, standardize_factor, neutralize_factor
from common.backtest import (
    calculate_ic, calculate_rank_ic, calculate_ic_series, ic_summary,
    quantile_backtest, long_short_backtest, performance_analysis,
)
from common.data_loader import load_market_data, load_industry, get_stock_universe
```
- 因子面板约定：长表 `[stock_code, date, factor]` 或宽表（按现有函数签名）。
- 新因子计算逻辑写到 `src/{report_name}/strategy.py`，回测调用 common。

## 5. 必需输出图表（保存 `output/{report_name}/results/`，300 DPI，蓝红配色）
1. `ic_series.png` — 月度 IC 柱状（正蓝/负红）+ 滚动均值
2. `ic_distribution.png` — IC 分布直方 + 正态拟合
3. `group_cumulative_returns.png` — 分组累计收益（低组红→高组蓝）
4. `group_returns_bar.png` — 分组年化收益条形
5. `net_value_comparison.png` — 多空/多头 vs 基准净值

## 6. 验证指标与通过标准
> 容差与必需产物清单以 templates/standards.json 为准，本节为人读说明。
| 指标 | 通过标准 |
|------|---------|
| RankIC 均值、ICIR | 方向一致，偏差 < 20%（Pearson/Rank、中性化口径差异容忍） |
| 多空年化收益、夏普 | 偏差 < 15% |
| 分组单调性 | 与研报方向一致（高组优于低组或反之） |
| 月均换手率 | 量级一致 |

> 偏差源常见：RankIC vs Pearson、中性化细节、股票池口径、调仓时点。verify 报告须说明。
