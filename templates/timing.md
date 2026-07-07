# 类型模板 · timing（时序择时）

## 1. 适用范围
**时序择时**类研报：基于宏观/量价/估值/资金等信号，对单一标的（指数、国债期货、大类资产）做多/空/空仓的仓位决策，按净值、回撤、胜率评估。参考已完成案例 `src/test/`（股债跷跷板隔日反转，复现精度 < 2.5%）。

## 2. plan 正文结构
- 信号构造（指标定义、阈值/分位、择时规则）
- 仓位映射（信号 → 目标仓位，含多空/仅多/杠杆）
- 回测（逐日持仓收益、交易成本、调仓）
- 绩效（净值、回撤、胜率、盈亏比）

## 3. 所需数据（对照 data_catalog）
| 数据 | 文件 | 说明 |
|------|------|------|
| 指数日行情 | `ashare_csiindex_trade.parquet` / `ashare_index_value.parquet` | 标的与基准（含 OHLC/估值） |
| 国债期货 | `financial_future_price.parquet` | 利率择时、股债组合 |
| 宏观信号 | `macro_cache.parquet`（宽表）/ 各 `macro_*` | PMI/社融/利率/利差等 |
| 交易日历 | `ashare_tradeday.parquet` | 调仓频率 |

## 4. common 接口规范（按需新建 `common/timing_backtest.py`）
首次遇 timing 报告时创建，之后复用：
```python
# common/timing_backtest.py
def signal_backtest(
    signal: pd.Series,          # index=date, 目标仓位或打分（-1~1 或 0/1）
    asset_returns: pd.Series,   # index=date, 标的日收益
    cost_bps: float = 0.0,      # 单边交易成本(bp)
    lag: int = 1,               # 信号滞后天数，防未来函数
) -> pd.DataFrame:
    """逐日回测，返回 [position, strategy_ret, nav, benchmark_nav]。"""

def timing_metrics(nav: pd.Series, position: pd.Series, benchmark_nav: pd.Series) -> dict:
    """年化收益/最大回撤/夏普/胜率/盈亏比/调仓次数/超额年化。"""
```
- 绩效指标复用 `common/utils`：`calculate_sharpe / calculate_annualized_return / calculate_max_drawdown / calculate_win_rate / calculate_calmar`。
- 信号计算写到 `src/{report_name}/strategy.py`。

## 5. 必需输出图表
1. `net_value.png` — 策略 vs 基准净值（策略蓝/基准灰）
2. `drawdown.png` — 回撤曲线（红色填充）
3. `position_signal.png` — 仓位/信号时序（叠加标的价格）
4. `yearly_returns.png` — 分年度收益条形（策略 vs 基准）
5. `rolling_sharpe.png` — 滚动夏普（或滚动超额）

## 6. 验证指标与通过标准
| 指标 | 通过标准 |
|------|---------|
| 年化收益、最大回撤、夏普 | 偏差 < 5% |
| 胜率、盈亏比 | 偏差 < 5% |
| 调仓次数/换手 | 量级一致 |

> 择时类对**信号时点对齐**与**交易成本口径**敏感，偏差大优先查 lag、成本、调仓时点（T 信号 T+1 执行）。
