# 类型模板 · allocation（资产配置）

## 1. 适用范围
**多资产配置**类研报：在股/债/商品/海外等多类资产间分配权重（风险平价、均值方差、风险预算、目标波动、宏观择时配置等），按组合净值、风险贡献、再平衡评估。

## 2. plan 正文结构
- 资产池定义（每类资产的代表指数/标的）
- 权重模型（公式：风险平价 / 均值方差 / 风险预算 / 战术偏离）
- 再平衡规则（频率、阈值、约束）
- 组合回测与风险归因

## 3. 所需数据（对照 data_catalog）
| 数据 | 文件 | 说明 |
|------|------|------|
| 各资产指数行情 | `ashare_csiindex_trade` / `ashare_index_value` / `bond_index_quote` / `osshare_index_price` / `hkshare_index_price` | 股/债/海外资产收益序列 |
| 国债期货（如用） | `financial_future_price.parquet` | 利率资产 |
| 宏观（战术配置） | `macro_cache.parquet` | 景气/估值/利率信号 |

## 4. common 接口规范（按需新建 `common/allocation_backtest.py`）
```python
# common/allocation_backtest.py
def risk_parity_weights(cov: pd.DataFrame) -> pd.Series:
    """风险平价权重（等风险贡献）。"""

def mean_variance_weights(exp_ret: pd.Series, cov: pd.DataFrame, bounds=None) -> pd.Series:
    """均值方差最优权重（可加约束）。"""

def risk_budget_weights(cov: pd.DataFrame, budget: pd.Series) -> pd.Series:
    """给定风险预算的权重。"""

def portfolio_backtest(
    weights_panel: pd.DataFrame,   # index=rebalance_date, columns=asset, 目标权重
    asset_returns: pd.DataFrame,   # index=date, columns=asset, 日收益
    cost_bps: float = 0.0,
) -> pd.DataFrame:
    """按再平衡权重回测，返回 [nav, asset_contribution..., turnover]。"""
```
- 绩效复用 `common/utils`；协方差估计（滚动/EWMA）写在 strategy 或此模块。

## 5. 必需输出图表
1. `weight_evolution.png` — 各资产权重堆叠面积图
2. `portfolio_nav.png` — 组合净值 vs 等权/基准
3. `asset_contribution.png` — 各资产收益/风险贡献
4. `rolling_volatility.png` — 组合滚动波动（对比目标波动）
5. `drawdown.png` — 组合回撤

## 6. 验证指标与通过标准
> 容差与必需产物清单以 templates/standards.json 为准，本节为人读说明。
| 指标 | 通过标准 |
|------|---------|
| 组合年化收益、夏普、最大回撤 | 偏差 < 10% |
| 各资产权重均值 | 量级一致，路径定性一致 |
| 再平衡换手 | 量级一致 |

> 配置类对**协方差估计窗口**、**再平衡频率/约束**敏感；权重难逐点复现属正常，重在路径与风险特征一致。
