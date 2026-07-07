# 类型模板 · fixed_income（固收）

## 1. 适用范围
**固收**类研报：利率债/信用债/可转债定价与策略、收益率曲线分析、久期/凸性管理、骑乘策略、信用利差、转债低估等，按到期收益率、久期、组合收益评估。

## 2. plan 正文结构
- 标的池/曲线定义（债券筛选、曲线类型）
- 定价计算（YTM / 久期 / 凸性 / 利差）
- 策略规则（久期择时、骑乘、信用下沉、转债双低等）
- 组合回测

## 3. 所需数据（对照 data_catalog）
| 数据 | 文件 | 说明 |
|------|------|------|
| 收益率曲线 | `bond_yield_curve.parquet` | 国债/各类曲线（期限利差、骑乘） |
| 债券行情 | `bond_exchange_quote.parquet` | 净价/全价、到期年限 |
| 债券要素 | `bond_basic_info.parquet` | 票息、期限、评级 |
| 债券现金流 | `bond_cashflow.parquet` | YTM/久期精确计算 |
| 评级/违约 | `bond_rating.parquet` / `bond_default.parquet` | 信用策略 |
| 转债 | `convertible_bond_quote` / `convertible_bond_basic` | 转债行情、转股溢价 |
| 利率/宏观 | `bond_shibor.parquet` / `macro_cache.parquet` | 资金面、利率环境 |

## 4. common 接口规范（按需新建 `common/fixed_income.py`）
```python
# common/fixed_income.py
def bond_ytm(price: float, cashflows: pd.DataFrame, settle_date) -> float:
    """由全价与现金流求到期收益率（数值解）。"""

def duration_convexity(ytm: float, cashflows: pd.DataFrame, settle_date) -> tuple[float, float]:
    """麦考利/修正久期与凸性。"""

def yield_curve_interp(curve: pd.DataFrame, target_maturity: float) -> float:
    """收益率曲线插值（线性/样条）。"""

def bond_portfolio_backtest(holdings, quotes, cost_bps: float = 0.0) -> pd.DataFrame:
    """债券组合回测，返回 [nav, duration, ...]。"""
```

## 5. 必需输出图表
1. `yield_curve.png` — 收益率曲线（多时点对比）
2. `duration_dist.png` — 组合久期分布/时序
3. `nav.png` — 策略组合净值 vs 基准（中债指数）
4. `spread_series.png` — 信用利差/期限利差时序
5. `drawdown.png` — 组合回撤

## 6. 验证指标与通过标准
> 容差与必需产物清单以 templates/standards.json 为准，本节为人读说明。
| 指标 | 通过标准 |
|------|---------|
| 到期收益率 YTM、久期、凸性 | 偏差 < 5%（纯计算类，须精确） |
| 组合收益、夏普、最大回撤 | 偏差 < 10% |
| 利差水平 | 量级与走势一致 |

> 计算类（YTM/久期）属确定性公式，必须精确；策略组合收益受标的池/成本影响，容忍稍宽。注意净价/全价、计息基准（act/365 等）口径。
