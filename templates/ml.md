# 类型模板 · ml（机器学习 / 深度学习）

## 1. 适用范围
**需要训练模型**的研报：机器学习/深度学习选股、ML 择时、特征合成、多因子非线性合成等。

**type 归属规则**：
- 报告核心是「**用 ML 实现选股/择时**」（模型是手段，最终仍是截面分组或时序仓位）→ `type: factor`（或 `timing`）+ `tags: [ml]`，**最终回测用基础类型的标准**，训练环节套用本模板的分层验证。
- 报告核心是「**模型方法论本身**」（如新网络结构、训练范式对比）→ `type: ml`，以预测质量为主要评估对象。

## 2. plan 正文结构
- 特征工程（输入因子/量价/基本面，预处理、标准化）
- 标签定义（未来 N 日收益/排序/分类）
- 模型与训练（结构、超参、损失、**滚动训练窗口**）
- 预测评估（IC、分组）→ 接入基础类型回测
> ml 报告**默认 ≥ medium**，含端到端深度网络多为 hard，按特征/训练/评估拆 milestone。

## 3. 所需数据（对照 data_catalog）
| 数据 | 文件 | 说明 |
|------|------|------|
| 量价特征 | `ashare_stock_price_forward` / `ashare_stock_trade` | 价量类输入 |
| 基本面特征 | `ashare_stock_income` / `_balance` / `_cashflow`（用 `info_publ_date` 对齐） | 财务因子，**防未来函数** |
| 预置因子 | `factor_factor_info.parquet` / `factors/` | 现成因子作输入 |
| 标签收益 | 由复权行情衍生 | 未来收益 |

## 4. common 接口规范（按需新建 `common/ml_pipeline.py`）
```python
# common/ml_pipeline.py
def build_features(panel: pd.DataFrame, feature_cfg: dict) -> pd.DataFrame:
    """构造特征矩阵 [stock_code, date, f1..fn]，含预处理（缩尾/标准化/缺失处理）。"""

def rolling_train_predict(
    features: pd.DataFrame, labels: pd.Series,
    model_factory,              # 返回未训练模型的可调用对象
    train_window: int, test_window: int, step: int,
    seed: int = 42,             # 固定随机种子
) -> pd.Series:
    """滚动窗口训练→样本外预测，拼接全样本预测值。**严格防未来函数**：只用 t 之前数据训练。"""

def evaluate_predictions(pred: pd.Series, forward_return: pd.Series) -> dict:
    """预测值评估：IC/RankIC、分组单调性、Top-Bottom 价差。"""
```
- 模型库：`scikit-learn` / `lightgbm` / `torch`（见 pyproject `[ml]` 可选组）。
- 最终回测：拿 `pred` 当因子，调 `common/backtest.py`（type=factor）或 `common/timing_backtest.py`（type=timing）。

## 5. 必需输出图表
1. `feature_importance.png` — 特征重要性（树模型）/ 首层权重
2. `ic_series.png` — 预测值月度 IC 时序
3. `group_cumulative_returns.png` — 按预测值分组累计收益
4. `train_val_loss.png` — 训练/验证损失曲线（深度模型）
5. `prediction_scatter.png` — 预测 vs 实际收益散点

## 6. 验证指标与通过标准（**分层**）
| 层 | 指标 | 通过标准 |
|----|------|---------|
| **数据/特征层** | 样本数、特征均值/分位、标签分布、缺失率 | 偏差 < 5%（精确复现） |
| **模型层** | 预测 IC、分组单调性、Top 组相对排序 | **方向性一致**：IC 同号且量级接近；分组单调性一致；Top 组排序一致。**不强求逐点** |

> 模型层不要求逐点复现：神经网络训练有随机性，固定 `seed` 后只要结论方向、IC 量级、单调性与研报一致即通过。
> 复核重点（独立复核 agent）：滚动训练是否**只用历史**（无未来函数泄漏）、标签是否对齐 T+1、特征是否含前视信息。
