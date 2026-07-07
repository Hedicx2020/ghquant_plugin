# 研报复现开发计划：再论动量因子

## 研报信息

- **标题**: 再论动量因子 -- 多因子系列报告之二十二
- **机构**: 光大证券
- **日期**: 2019年6月15日
- **作者**: 周萧潇、刘均伟
- **市场**: A股市场

---

## 一、核心策略与创新点

### 1.1 研报核心发现

A股市场与海外市场不同，**反转效应远强于动量效应**。常用动量因子（Momentum_1M, 3M, 6M, 12M, 24M）在A股均表现为显著的负IC和负IC_IR，即前期涨幅越高的股票未来一个月收益越差。但常用动量因子存在**单调性不佳、多头收益不稳定**的缺陷。

### 1.2 四个改进方向

报告从四个角度对动量因子进行改造：

#### (1) 趋势动量因子（结合均线）
- **核心思路**: 传统动量因子仅使用起始/末尾节点价格，忽略了期间信息。采用移动平均线（MA）标准化后构造趋势动量因子。
- **公式**:
  - MA_{j,t,L} = (P_{j,d-L+1} + P_{j,d-L+2} + ... + P_{j,d}) / L
  - 标准化: MA_bar_{j,t,L} = MA_{j,t,L} / P_{j,d}
  - 其中 P_{j,d} 是股票j在t月最后一个交易日d的收盘价，L为窗口期
- **参数**: MA_20, MA_60, MA_120, MA_240
- **结论**: 单调性很高（得分均超过3），但IC/IC_IR弱于原始动量因子

#### (2) 提纯动量因子（剥离流动性）
- **核心思路**: 散户集中度/流动性因素影响动量因子效果。采用截面回归取残差，将流动性因子从原始动量因子中剥离。
- **方法**: 对 Momentum_1M 做截面回归，剥离 FC_MC（自由流通股占比）和 VSTD_1M（1个月波动率）的影响
- **回归模型**: Momentum_1M_Neu = residual of regressing Momentum_1M on FC_MC + VSTD_1M
- **结论**: 单调性改善显著，多空年化收益从23.9%提高到28.8%，提升4.97个百分点

#### (3) 残差动量因子（风格中性化）
- **核心思路**: 参考 Blitz D. et al. (2011) 的 residual momentum，利用Fama-French三因子模型计算特质收益，构造残差动量因子
- **方法**:
  1. 对每只股票，取过去t-35月到t月（共36个月）的月度收益率
  2. 对Fama-French三因子（MKT, SMB, HML）做时间序列回归: r_{i,t} = alpha_i + m_i*MKT_t + s_i*SMB_t + h_i*HML_t + epsilon_{i,t}
  3. 取当期残差 epsilon_{i,t} 作为特质收益动量因子，命名为 Momentum_1M_Resid
- **三因子构造**:
  - SMB: 小盘股组合减大盘股组合的收益率之差，按流通市值加权
  - HML: 高BP组合减低BP组合的收益率之差，按流通市值加权
- **结论**: IC均值略低于原始动量因子（-7.04% vs -7.85%），但IC波动率有效降低（从10%降到8%），IC_IR从-0.76提高到-0.80，稳定性提升

#### (4) 改造K线下的动量因子
- **核心思路**: 传统时间K线存在样本点信息不均、序列自相关性等缺陷。采用成交额等分K线替代传统时间K线构造动量因子
- **K线切片方式**:
  - Tick等分K线: 每根K线有相同的交易笔数
  - 成交量等分K线: 每根K线有相同的成交量
  - 成交额等分K线: 每根K线有相同的成交额
- **参数**: 固定20根K线，按K线个数匹配测试区间内的总K线数量
- **代表因子**: Value_60（成交额等分K线动量因子），多头超额收益13.53%
- **注意**: 此部分需要高频历史数据（分钟或tick级别），数据时间为2009-01-01至2017-12-31
- **结论**: 成交额等分K线动量因子多头收益较高，且多空收益贡献大部分来自多头组合

---

## 二、回测参数详情

### 2.1 主回测参数（因子1-3）

| 设定项 | 设定值 |
|--------|--------|
| 测试区间 | 2006/01/01 - 2019/05/31 |
| 股票池 | 全部A股（剔除选股日ST/PT股票；剔除上市不满一年的股票；剔除选股日由于停牌等因素无法买入的股票） |
| 因子预处理 | 截面标准化处理 |
| 因子中性化 | 市值、中信一级行业 |
| 因子分组 | 降序分10组 |
| 统计频率 | 月频 |
| 调仓日 | 每月末最后一个交易日 |

### 2.2 K线动量因子回测参数（因子4）

| 设定项 | 设定值 |
|--------|--------|
| 测试区间 | 2009/01/01 - 2017/12/31 |
| K线个数 | 固定20根 |
| K线切片方式 | 成交额等分、成交量等分、Tick等分 |
| 对标因子 | time_60, time_120, time_D (传统时间K线) |

### 2.3 关键评价指标

| 指标 | 说明 |
|------|------|
| IC | Pearson相关系数 (因子值 vs 下期收益) |
| IC_IR | IC均值 / IC标准差 |
| LongShort_Sharpe | 多空组合的夏普比率 |
| Mono_Score | 单调性得分 = (第10组年化收益 - 第1组年化收益) / (第8组年化收益 - 第3组年化收益) |
| Turnover | 换手率 |

### 2.4 研报核心结果（用于验证对照）

#### 表3: 常用动量因子测试结果（全市场）

| 因子 | IC | IC_IR | LongShort_Sharpe | Mono_Score | Turnover |
|------|------|-------|------------------|------------|----------|
| Momentum_1M_Max | -6.94% | -0.87 | 0.63 | 1.46 | 67.28% |
| Momentum_1M | -7.85% | -0.76 | 1.44 | 2.55 | 82.40% |
| Momentum_3M | -6.81% | -0.60 | 1.22 | 2.97 | 46.41% |
| Momentum_6M | -5.46% | -0.49 | 0.96 | 2.31 | 37.38% |
| Momentum_12M | -4.33% | -0.37 | 0.75 | 1.80 | 26.82% |
| Momentum_24M | -4.53% | -0.41 | 0.77 | 1.72 | 20.09% |

#### 表4: 趋势动量因子测试结果

| 因子 | IC | IC_IR | LongShort_Sharpe | Mono_Score | Turnover |
|------|------|-------|------------------|------------|----------|
| MA_20 | 2.11% | 0.32 | 0.97 | 4.64 | 83.12% |
| MA_60 | 2.56% | 0.41 | 0.83 | 3.75 | 68.43% |
| MA_120 | 2.74% | 0.39 | 0.93 | 5.23 | 47.34% |
| MA_240 | 2.41% | 0.32 | 1.23 | 4.14 | 23.14% |

#### 表6: 提纯动量因子测试结果

| 因子 | IC | IC_IR | LongShort_Sharpe | Mono_Score | Turnover |
|------|------|-------|------------------|------------|----------|
| Momentum_1M | -7.85% | -0.76 | 1.44 | 2.55 | 82.40% |
| Momentum_1M_Neu | -7.59% | -0.79 | 2.29 | 2.44 | 84.34% |

#### 表7: 残差动量因子测试结果

| 因子 | IC | IC_IR | LongShort_Sharpe | Mono_Score | Turnover |
|------|------|-------|------------------|------------|----------|
| Momentum_1M | -7.85% | -0.76 | 1.44 | 2.55 | 82.40% |
| Momentum_1M_Resid | -7.04% | -0.80 | 1.96 | 3.03 | 84.02% |

---

## 三、因子计算公式与逻辑

### 3.1 常用动量因子

```
Momentum_NM(stock, t) = close(t) / close(t-N) - 1
```

| 因子代码 | N（月份） | 说明 |
|---------|----------|------|
| Momentum_1M | 1 | 过去1个月涨跌幅 |
| Momentum_3M | 3 | 过去3个月涨跌幅 |
| Momentum_6M | 6 | 过去6个月涨跌幅 |
| Momentum_12M | 12 | 过去12个月涨跌幅 |
| Momentum_24M | 24 | 过去24个月涨跌幅 |
| Momentum_1M_Max | 1 | 过去1个月最高收益率（日级别） |

**注意**: Momentum_1M_Max 是过去一个月内日收益率的最大值。

### 3.2 趋势动量因子

```
# L期移动平均
MA_{j,t,L} = mean(P_{j,d-L+1}, ..., P_{j,d})

# 标准化
MA_bar_{j,t,L} = MA_{j,t,L} / P_{j,d}

# 其中:
#   P_{j,d} = 股票j在月末最后一个交易日d的收盘价
#   L = 移动平均窗口期（20, 60, 120, 240 个交易日）
```

因子值 > 1 表示当前价格高于均线（上升趋势），< 1 表示低于均线（下降趋势）。

### 3.3 提纯动量因子（流动性剥离）

```
# 截面回归（每个月末截面独立回归）:
Momentum_1M = beta_0 + beta_1 * FC_MC + beta_2 * VSTD_1M + epsilon

# 提纯动量因子:
Momentum_1M_Neu = epsilon（残差项）

# 其中:
#   FC_MC = 自由流通市值 / 总市值
#   VSTD_1M = 过去一个月日收益率的标准差
```

### 3.4 残差动量因子（Fama-French风格中性化）

```
# Step 1: 构造Fama-French三因子
#   MKT = 市场因子（全市场流通市值加权收益率 - 无风险利率）
#   SMB = 小盘因子（小盘股组合 - 大盘股组合，流通市值加权）
#   HML = 价值因子（高BP组合 - 低BP组合，流通市值加权）

# Step 2: 时间序列回归（每只股票独立）
#   对过去36个月（t-35到t月）的月度收益率:
#   r_{i,t} = alpha_i + m_i * MKT_t + s_i * SMB_t + h_i * HML_t + epsilon_{i,t}

# Step 3: 取当期残差
#   Momentum_1M_Resid = epsilon_{i,t}（即最近一期的残差）
```

### 3.5 改造K线动量因子（可选实现，需要高频数据）

```
# 成交额等分K线构造:
# 1. 将月内日频/分钟频数据按成交额等分为N根K线
# 2. 每根K线记录OHLC
# 3. 动量因子 = 最后一根K线close / 第一根K线open - 1

# Value_60: 成交额等分，60根K线，取最近20根的动量
# Value_120: 成交额等分，120根K线，取最近20根的动量
# Value_D: 成交额等分，日频级别K线数，取最近20根的动量
```

---

## 四、数据需求清单

### 4.1 必需数据（本地已有）

| 数据文件 | 用途 | 关键字段 |
|---------|------|---------|
| `ashare_stock_price.parquet` | 日频价格数据 | stock_code, date, close, open, high, low, prev_close |
| `ashare_stock_trade.parquet` | 日频交易数据 | stock_code, date, change_pct, market_value, negotiable_market_value, turnover_rate, turn_value, volume |
| `ashare_stock_st.parquet` | ST标记 | stock_code, implement_date, remove_date |
| `ashare_suspend.parquet` | 停牌数据 | stock_code, date, ifsuspend |
| `ashare_stock_industry.parquet` | 行业分类 | stock_code, first_industry_name (standard_code=37为中信一级) |
| `ashare_tradeday.parquet` | 交易日历 | date, IfTradingDay, IfMonthEnd |
| `ashare_stock.parquet` | 股票基本信息 | stock_code, list_date (用于剔除上市不满一年) |
| `ashare_stock_value.parquet` | 估值数据 | stock_code, date, pb_lf (用于构造HML因子) |

### 4.2 需要计算的中间数据

| 数据项 | 计算方式 |
|--------|---------|
| 月度收益率 | 每月末收盘价相对上月末收盘价的涨跌幅 |
| 日收益率标准差(VSTD_1M) | 过去20个交易日日收益率的标准差 |
| 自由流通比(FC_MC) | negotiable_market_value / market_value |
| MKT因子 | 全市场流通市值加权月度收益率 |
| SMB因子 | 按市值分两组，小盘组-大盘组流通市值加权收益 |
| HML因子 | 按BP分两组，高BP组-低BP组流通市值加权收益 |
| 移动平均价格(MA) | 过去L个交易日收盘价均值 |

### 4.3 可选数据（K线动量因子）

| 数据文件 | 用途 | 备注 |
|---------|------|------|
| 日内分钟级数据 | 构造成交额等分K线 | 本地 `minute.parquet` 仅有期货数据，无A股分钟数据 |

**注意**: 本地无A股分钟频数据，K线动量因子（第四部分）暂不实现，或使用日频数据近似。

---

## 五、分步实现任务

### 文件结构

```
report_reproduce/
├── src/
│   └── momentum_factor/
│       ├── __init__.py
│       ├── config.py          # 配置参数
│       ├── strategy.py        # 核心因子计算（6个因子）
│       └── main.py            # 主执行脚本
├── common/                    # 已有，直接复用
│   ├── utils.py
│   ├── backtest.py
│   └── data_loader.py
└── output/
    └── momentum_factor/
        └── results/
```

---

### Step 1: 配置文件 (`config.py`)

**目标**: 定义所有回测参数和因子参数。

**内容**:
- 回测时间区间: start_date = "2006-01-01", end_date = "2019-05-31"
- 股票池筛选规则: 全A股，剔除ST/PT，剔除上市不满1年，剔除停牌
- 分组数: n_groups = 10
- 调仓频率: 月频
- 因子中性化: 市值 + 中信一级行业
- 因子预处理: MAD缩尾 + Z-score标准化
- 动量因子窗口参数: [1, 3, 6, 12, 24] 个月
- 趋势动量因子窗口参数: [20, 60, 120, 240] 交易日
- 残差动量回归窗口: 36个月
- Mono_Score 计算方式: (G10年化收益 - G1年化收益) / (G8年化收益 - G3年化收益)

---

### Step 2: 数据准备模块 (在 `strategy.py` 中实现)

**目标**: 加载并准备因子计算所需的全部基础数据。

**子任务**:

2.1 **加载基础数据**
- 使用 `common.data_loader` 加载价格、交易、ST、停牌、行业、交易日历、上市日期数据
- 合并价格和交易数据为日频面板

2.2 **构建月度面板**
- 获取月末交易日序列
- 提取每月末截面数据
- 计算月度收益率: close(t) / close(t-1) - 1

2.3 **股票池筛选**
- 每个月末截面: 剔除ST/PT股票
- 剔除上市不满1年的股票
- 剔除当日停牌的股票

**验证点**: 检查月度面板的股票数量级（全A股应有3000-4000只/月）

---

### Step 3: 常用动量因子计算 (在 `strategy.py` 中实现)

**目标**: 计算6个常用动量因子。

**函数签名**:
```python
def calculate_momentum_factors(
    daily_panel: pd.DataFrame,
    month_end_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """
    计算常用动量因子。

    返回: DataFrame with columns [stock_code, date, Momentum_1M, Momentum_3M,
           Momentum_6M, Momentum_12M, Momentum_24M, Momentum_1M_Max]
    """
```

**计算逻辑**:
- Momentum_NM: 取月末收盘价，计算N个月前收盘价到当前的涨跌幅
  - 需要将"N个月"转换为交易日数: 1M~20日, 3M~60日, 6M~120日, 12M~240日, 24M~480日
  - 或直接使用月末收盘价序列，按月份回溯
- Momentum_1M_Max: 过去20个交易日中日收益率(change_pct)的最大值

**验证点**:
- IC应为负值（反转效应）
- Momentum_1M 的IC约为-7.85%，IC_IR约为-0.76

---

### Step 4: 趋势动量因子计算 (在 `strategy.py` 中实现)

**目标**: 计算4个趋势动量因子。

**函数签名**:
```python
def calculate_trend_momentum_factors(
    daily_panel: pd.DataFrame,
    month_end_dates: pd.DatetimeIndex,
    windows: list[int] = [20, 60, 120, 240],
) -> pd.DataFrame:
    """
    计算趋势动量因子 MA_L。

    返回: DataFrame with columns [stock_code, date, MA_20, MA_60, MA_120, MA_240]
    """
```

**计算逻辑**:
- 对每只股票，计算过去L个交易日的收盘价移动平均
- 标准化: MA_bar = MA / 当日收盘价
- 因子值 > 1: 股价在均线上方（上升趋势）
- 因子值 < 1: 股价在均线下方（下降趋势）

**验证点**:
- IC应为正值（趋势效应）
- MA_60的IC约为2.56%，IC_IR约为0.41

---

### Step 5: 提纯动量因子计算 (在 `strategy.py` 中实现)

**目标**: 计算流动性剥离后的提纯动量因子。

**函数签名**:
```python
def calculate_purified_momentum(
    momentum_1m: pd.Series,
    fc_mc: pd.Series,
    vstd_1m: pd.Series,
    date_col: str = "date",
) -> pd.Series:
    """
    截面回归剥离流动性因素后的提纯动量因子。

    返回: 提纯后的动量因子值
    """
```

**计算逻辑**:
1. 计算FC_MC = negotiable_market_value / market_value（每个截面）
2. 计算VSTD_1M = 过去20个交易日日收益率的标准差（每个截面）
3. 每月末截面: 对 Momentum_1M 做 OLS 回归
   - Momentum_1M = beta_0 + beta_1 * FC_MC + beta_2 * VSTD_1M + epsilon
4. 取残差 epsilon 作为 Momentum_1M_Neu

**验证点**:
- IC约为-7.59%，IC_IR约为-0.79
- 多空Sharpe从1.44提高到2.29

---

### Step 6: 残差动量因子计算 (在 `strategy.py` 中实现)

**目标**: 计算Fama-French风格中性化后的残差动量因子。

**函数签名**:
```python
def construct_fama_french_factors(
    monthly_returns: pd.DataFrame,
    market_cap: pd.DataFrame,
    bp_ratio: pd.DataFrame,
) -> pd.DataFrame:
    """
    构造Fama-French三因子（MKT, SMB, HML）月度序列。
    """

def calculate_residual_momentum(
    monthly_returns: pd.DataFrame,
    ff_factors: pd.DataFrame,
    lookback: int = 36,
) -> pd.DataFrame:
    """
    计算残差动量因子。
    对每只股票，用过去36个月收益率对FF三因子回归，取最近一期残差。
    """
```

**计算逻辑**:
1. **构造FF三因子**:
   - MKT: 全市场流通市值加权月度收益率（可直接用万得全A收益率近似，或自行计算）
   - SMB: 按月末流通市值中位数分大小盘两组，分别计算流通市值加权收益率，SMB = 小盘组 - 大盘组
   - HML: 按月末BP（Book-to-Price = 1/PB）分高低两组，分别计算流通市值加权收益率，HML = 高BP组 - 低BP组

2. **滚动回归**:
   - 对每只股票，每个月末截面:
     - 取过去36个月（t-35到t月）的月度收益率
     - 对MKT, SMB, HML做OLS时间序列回归
     - 取第t期的残差 epsilon_{i,t} 作为 Momentum_1M_Resid

**验证点**:
- IC约为-7.04%，IC_IR约为-0.80
- 多空Sharpe从1.44提高到1.96

---

### Step 7: 因子预处理与中性化 (调用 `common.utils`)

**目标**: 对所有计算完成的因子进行统一的预处理。

**处理流程**:
1. MAD缩尾处理: 使用 `common.utils.winsorize(method="mad")`
2. 市值+行业中性化: 使用 `common.utils.neutralize_factor(market_cap=..., industry=...)`
3. Z-score标准化: 使用 `common.utils.standardize()`
4. 也可直接调用 `common.utils.standardize_factor()` 一步完成

**注意**: 报告中因子测试默认对市值和中信一级行业做了中性化处理。

---

### Step 8: 主执行脚本 (`main.py`)

**目标**: 串联所有因子计算和回测流程。

**执行顺序**:

```python
# 1. 加载配置
from .config import CONFIG

# 2. 加载数据
from common.data_loader import (
    load_market_data, load_st_data, load_industry,
    get_month_end_trading_days, load_stock_price, load_stock_trade
)

# 3. 计算因子
from .strategy import (
    calculate_momentum_factors,
    calculate_trend_momentum_factors,
    calculate_purified_momentum,
    construct_fama_french_factors,
    calculate_residual_momentum,
)

# 4. 因子预处理
from common.utils import standardize_factor

# 5. 回测分析
from common.backtest import performance_analysis

# 6. 逐因子回测，输出结果到 output/momentum_factor/results/
```

**输出内容**:
- 每个因子的IC时间序列图
- 每个因子的分组收益图
- 所有因子的汇总比较表
- 提纯前后因子对比图
- 残差动量前后因子对比图

---

## 六、改进建议与讨论

### 6.1 潜在改进方向

1. **动态窗口优化**: 报告使用固定窗口（1M, 3M等），可尝试自适应窗口长度（基于波动率调整）
2. **非线性剥离**: 提纯动量因子使用线性回归剥离流动性，可尝试非线性方法（如分段回归、GAM模型）
3. **多因子组合**: 将趋势动量、提纯动量、残差动量进行等权或IC加权组合，可能获得更稳健的复合动量因子
4. **时变IC分析**: 分析动量/反转效应在牛市/熊市/震荡市的IC差异，进行择时切换
5. **行业动量**: 除了个股动量，可研究行业层面的动量/反转效应

### 6.2 研报局限性

1. **K线动量因子数据限制**: 成交额等分K线需要高频数据，本地数据不支持，暂无法复现
2. **回测周期较短**: 测试期为2006-2019，未覆盖2020年后的市场风格变化
3. **交易成本未充分考虑**: 报告主要关注因子选股能力（IC/分组），未详细讨论交易成本对策略实际收益的影响
4. **因子衰减分析缺失**: 未提供因子在不同持仓周期下的IC衰减情况

### 6.3 相关研究参考

- Zhou, Zhu (2016): 股价变化趋势强弱的分析，趋势动量因子的理论基础
- Blitz D., et al. (2011): Residual momentum，残差动量策略的原始论文
- Fama-French (1993): 三因子模型
- 光大证券系列报告:
  - 《因子正交与择时：基于分类模型的动态权重配置》
  - 《数据纵横：探秘K线结构新维度》
  - 《以质取胜：EBQC综合质量因子详解》

---

## 七、实现优先级

| 优先级 | 任务 | 预计工作量 |
|--------|------|----------|
| P0 | Step 1-2: 配置 + 数据准备 | 0.5天 |
| P0 | Step 3: 常用动量因子 | 0.5天 |
| P1 | Step 4: 趋势动量因子 | 0.5天 |
| P1 | Step 5: 提纯动量因子 | 0.5天 |
| P1 | Step 6: 残差动量因子 | 1天 |
| P0 | Step 7-8: 预处理 + 主脚本 | 0.5天 |
| P2 | K线动量因子 | 视数据可用性 |

**总计预计工作量**: 3-4天（不含K线动量因子）
