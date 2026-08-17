"""集中配置 · ssrn_6115073（Online Portfolio Selection Using Macroeconomic Pattern Matching）

市场迁移复现（experimental）：原文美股 S&P500/DJI + 日股 N225 + FRED 美国宏观本地
全不可得，迁移到 A股三宽基 + 中国宏观等价替代。本文件集中 m1（数据映射与宏观因子
准备）所需的全部区间/池代码/宏观映射/门槛参数，供 m2-m7 全链复用，杜绝魔法数字。

所有取值均可反查 spec.md / plan.md / assumptions.md：
  - 区间 TRAIN/TEST：AS6 / AS34（据本地可得性微调，见文末注释）
  - 三宽基映射：AS28（S&P500→沪深300 主 / DJI→上证50 / N225→中证500）
  - 宏观候选池映射：AS29 / AS16 / AS30(UR降维) / AS31→AS35(DGDP降维) / AS36(IR/rf源)
  - 披露滞后 fallback：AS37（info_publ_date 缺失时的保守滞后）
  - rf 来源：AS19 / AS32 / AS36
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# 一、回测区间（AS6 训练定 w/nc、测试评估；AS34 A股区间迁移）
# ---------------------------------------------------------------------------
# 原文 1995-2023（训练至 2018）→ A股按可得性：全样本约 2007-01 ~ 2024-12。
# 取 2007 起确保沪深300 成分与宏观序列稳定（沪深300 成分 in_date 最早 2005-04-08，
# 但 2007 起成分调整与宏观序列更完整）。
# 实际首末可得日在 data_prep 冒烟后可据 print 微调；此处为写死默认。
TRAIN_START: Final[str] = "2007-01-01"
TRAIN_END: Final[str] = "2018-12-31"   # 训练段仅用于定 pattern-matching 窗口 w/子簇 nc
TEST_START: Final[str] = "2019-01-01"
TEST_END: Final[str] = "2024-12-31"   # 复现基线测试末(AS34)；oos 阶段样本外延伸(2025-01~2026-06)见 output/results/oos_* 静态产物，勿据此改回

# 面板加载的最早日期（早于 TRAIN_START 以便算首月收益 pct_change 有前值 / 宏观 asof 有历史）
PANEL_LOAD_START: Final[str] = "2006-01-01"

# ---------------------------------------------------------------------------
# 二、三宽基市场映射（AS28；主分析=沪深300，对标原文 S&P500 主分析地位）
# ---------------------------------------------------------------------------
# key = 内部市场名；value = 指数代码（成分股与基准指数同码）。
MARKETS: Final[dict[str, str]] = {
    "hs300": "000300",   # 沪深300  ← S&P500（主分析）
    "sz50": "000016",    # 上证50   ← Dow Jones（大盘蓝筹）
    "zz500": "000905",   # 中证500  ← Nikkei225（第三市场，跨市场推广）
}
PRIMARY_MARKET: Final[str] = "hs300"   # 主分析市场（BorutaShap 目标指数取此）

# 市场中文名（出图/报告用）
MARKET_NAMES_CN: Final[dict[str, str]] = {
    "hs300": "沪深300",
    "sz50": "上证50",
    "zz500": "中证500",
}

# ---------------------------------------------------------------------------
# 三、股票池状态过滤门槛
# ---------------------------------------------------------------------------
# 次新过滤：建仓信号日距个股首个行情日不足此月数则剔除（月频双区制 OLS 需足够历史，
# 参见 plan 第十节风险4；6 个月为 A股次新剔除常用门槛）。
LISTING_MIN_MONTHS: Final[int] = 6

# ---------------------------------------------------------------------------
# 四、频率常量
# ---------------------------------------------------------------------------
PERIODS_PER_YEAR: Final[int] = 12   # 月频（AS4 月度调仓）
MACRO_STAGE_MONTHS: Final[int] = 12  # 宏观 pattern matching「最近一年」=12 月（AS10，供 m4）

# ---------------------------------------------------------------------------
# 五、中国宏观候选池映射（AS29；BorutaShap 重选前的可得候选全集，AS16）
# ---------------------------------------------------------------------------
# 每个候选因子 → 数据来源规格：
#   file       : ~/local_data 下 parquet 文件名（不含扩展名）；'macro_cache' 为宽表特例
#   indicator  : indicator_name 精确匹配值（macro_cache 特例时为宽表列名）
#   freq       : 'M' 月频 / 'Q' 季频（季频经披露日 asof 自然前填到月频）
#   publ_lag_days : info_publ_date 缺失时的保守披露滞后天数（自报告期末算，AS37，宁晚不早）
#   is_market_rate: True 表示市场即时利率（无统计披露滞后，用当月末值不构成未来函数）
#   yoy_type   : 'yoy_current' 当期同比 / 'yoy_current_filled' 当期同比但年初1-2月为累计填充
#                （仅工业增加值，1月不单独发布）/ 'yoy_cumulative' 累计同比（年初重置）/
#                'level' 水平值。change_panel 按此口径构造（AS39）：yoy_current/level 报告期
#                月度差分；yoy_cumulative 差分且年初重置断点(跨年)置 NaN；yoy_current_filled
#                差分且每年 1-3 月（填充月+口径切换月）置 NaN 剔机械跳变；季频累计的季度变化
#                经披露日 asof 前填至季内月份（非季内恒 0）。落地 CA-A01。
#
# 披露日策略（AS37）：宏观 info_publ_date 质量参差——部分表（如社融）被批量回填为
# 近期入库日（滞后中位达数千天，误导 asof）。采用「合理性检验 + 保守滞后 fallback」：
# 仅当 date < info_publ_date <= date + PUBL_LAG_CAP_DAYS 时采信真实披露日，否则用
# date + publ_lag_days（指标典型滞后）。既防未来函数（fallback 保守），又保覆盖完整。
#
# 已据实降维/代理：
#   UR 失业率      → 本地无干净月频等价物，据实剔除（AS30）
#   DGDP 债务/GDP → 政府债务/GDP 存量本地不可得；原拟社融代理，但社融各可得口径月度同比
#                    剧烈波动不可用（AS35 修订）→ DGDP 维度降维，货币信用维度由 M2 承载
#   SF   社融      → 各可得口径不平稳，剔除（AS35）
MACRO_CANDIDATES: Final[dict[str, dict]] = {
    "CPI": dict(file="macro_cpi", indicator="CPI:当期同比:月",
                freq="M", publ_lag_days=18, is_market_rate=False, yoy_type="yoy_current"),
    "PPI": dict(file="macro_ppi", indicator="PPI:当期同比:月",
                freq="M", publ_lag_days=18, is_market_rate=False, yoy_type="yoy_current"),
    "GDP": dict(file="macro_gdp", indicator="GDP(不变价):累计同比:季",
                freq="Q", publ_lag_days=20, is_market_rate=False, yoy_type="yoy_cumulative"),
    # IP 用「当期同比(1-2月累计填充)」而非累计同比：更贴近原文 FRED IP。填充版 1-2 月为累计
    # 值、3 月切回真实当月同比，其 change 每年 1-3 月为口径切换机械跳变(|Δ|达39)→yoy_current_filled
    # 剔除后 |Δ| 降至约 7.9（CA-A01/AS39）
    "IP": dict(file="macro_industrial_production",
               indicator="规模以上工业增加值(1-2月累计填充):当期同比:月",
               freq="M", publ_lag_days=18, is_market_rate=False, yoy_type="yoy_current_filled"),
    "M2": dict(file="macro_money_supply", indicator="货币和准货币(M2):同比:月",
               freq="M", publ_lag_days=15, is_market_rate=False, yoy_type="yoy_current"),
    "PMI": dict(file="macro_pmi", indicator="制造业PMI:季调:月",
                freq="M", publ_lag_days=1, is_market_rate=False, yoy_type="level"),
    # SF 社融已据实剔除（AS35 修订）：本地社融各可得口径（直接融资累计同比 |Δ|≈926、
    # 总量同比 |Δ|≈109）月度同比均因早期小基数剧烈波动，不适合作平稳 Δβ/pattern 因子；
    # DGDP 债务/GDP 维度降维，货币信用维度由 M2（|Δ|≈5 平稳）承载。
    "IR": dict(file="macro_cache", indicator="bond_yield_10y",
               freq="M", publ_lag_days=0, is_market_rate=True, yoy_type="level"),  # 10Y国债（AS36）
}

# info_publ_date 采信上限（天）：真实披露日超过报告期末此天数即判为异常回填，
# 回退到 date + publ_lag_days（AS37）。90 天可采信正常次月/季后披露、拒绝批量回填异常值。
PUBL_LAG_CAP_DAYS: Final[int] = 90

# ---------------------------------------------------------------------------
# 六、无风险利率 rf 来源（AS19 / AS32 / AS36）
# ---------------------------------------------------------------------------
# SHIBOR 本地仅 2025-05+、中债国债曲线仅 2015+，均不覆盖 2007-2024 回测区间，
# → rf 改用 10Y 国债收益率（macro_cache.bond_yield_10y，2002+ 覆盖全）月度折算。
# 值为年化百分数（如 3.029 表示 3.029%）。月度 rf = (1 + y/100)^(1/12) - 1。
RF_CACHE_COLUMN: Final[str] = "bond_yield_10y"

# ---------------------------------------------------------------------------
# 七、F12 BorutaShap 重选参数（AS16；主路径可用时用，不可用时退化直采全集 AS38）
# ---------------------------------------------------------------------------
BORUTA_TARGET_MARKET: Final[str] = PRIMARY_MARKET   # 目标 = 主市场指数月收益（AS16）
BORUTA_RF_N_ESTIMATORS: Final[int] = 200            # RandomForest 基模型树数
BORUTA_N_TRIALS: Final[int] = 50                    # BorutaShap 迭代轮数
RANDOM_SEED: Final[int] = 42                         # 可复现随机种子
BORUTA_MIN_TRAIN_SAMPLES: Final[int] = 60           # 训练期样本不足此数则退化（防泄漏/不稳）

# ---------------------------------------------------------------------------
# 八、股票代码规整
# ---------------------------------------------------------------------------
STOCK_CODE_WIDTH: Final[int] = 6   # A股代码 6 位（如 600000）
