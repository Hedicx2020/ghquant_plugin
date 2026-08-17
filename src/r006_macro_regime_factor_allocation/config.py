"""r006 m1 集中配置。

本模块只登记 plan/assumptions 已裁决的参数、真实本地文件合同与 D1-D10
替代关系。函数体不得另写不可反查的策略参数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from common.data_loader import get_data_root


@dataclass(frozen=True)
class SourceSpec:
    """一个本地数据源的字段与覆盖审计合同。"""

    key: str
    relative_path: str
    required_columns: tuple[str, ...] = ()
    coverage_columns: tuple[str, ...] = ()
    kind: str = "parquet"
    required_for_formal: bool = True


@dataclass(frozen=True)
class SubstituteSpec:
    """一个原文数据对象到 A 股本地对象的透明替代。"""

    element_id: str
    original_data: str
    local_substitute: str
    reason: str
    assumptions: tuple[str, ...]
    source_keys: tuple[str, ...]
    source_usage: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MacroSeriesSpec:
    """宏观候选序列及其保守可用时点规则。"""

    block: str
    series_id: str
    source_key: str
    value_column: str
    frequency: str
    lag_months: int
    priority: int
    indicator_code: str | None = None
    transform: str = "direct"
    selectors: tuple[tuple[str, object], ...] = ()


FAMILY_ORDER: Final[tuple[str, ...]] = (
    "Valuation",
    "Continuation",
    "Correction",
    "Profitability/quality",
    "Investment/issuance",
    "Safety/downside",
    "Liquidity/limits",
    "Expectations",
)

FAMILY_KEYWORDS: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    (
        "Valuation",
        (
            "估值",
            "价值",
            "股息率",
            "市盈率",
            "市净率",
            "市销率",
            "value",
            "valuation",
            "book-to-market",
            "earnings yield",
            "dividend yield",
            "pe",
            "pb",
            "ps",
        ),
    ),
    (
        "Continuation",
        (
            "动量",
            "趋势",
            "延续",
            "相对强弱",
            "momentum",
            "trend",
            "continuation",
            "relative strength",
        ),
    ),
    (
        "Correction",
        (
            "反转",
            "均值回归",
            "超跌",
            "过度反应",
            "reversal",
            "mean reversion",
            "overreaction",
            "short-term reversal",
        ),
    ),
    (
        "Profitability/quality",
        (
            "盈利",
            "质量",
            "利润率",
            "资产回报",
            "净资产收益",
            "应计",
            "profitability",
            "quality",
            "margin",
            "roe",
            "roa",
            "accrual",
        ),
    ),
    (
        "Investment/issuance",
        (
            "投资",
            "资本开支",
            "资产增长",
            "发行",
            "融资",
            "investment",
            "capex",
            "asset growth",
            "issuance",
            "financing",
        ),
    ),
    (
        "Safety/downside",
        (
            "安全",
            "下行",
            "低波",
            "波动",
            "贝塔",
            "困境",
            "杠杆",
            "safety",
            "downside",
            "low volatility",
            "volatility",
            "beta",
            "distress",
            "leverage",
        ),
    ),
    (
        "Liquidity/limits",
        (
            "流动性",
            "非流动性",
            "换手",
            "成交",
            "涨跌停",
            "liquidity",
            "illiquidity",
            "turnover",
            "volume",
            "limit",
        ),
    ),
    (
        "Expectations",
        (
            "预期",
            "预测",
            "分析师",
            "修正",
            "情绪",
            "expectations",
            "forecast",
            "analyst",
            "revision",
            "sentiment",
        ),
    ),
)


SOURCE_SPECS: Final[tuple[SourceSpec, ...]] = (
    SourceSpec(
        "factor_metadata",
        "factor_factor_info.parquet",
        ("factor_id", "factor_id_cn", "level1", "level2"),
    ),
    SourceSpec("factor_panel_dir", "factors", kind="directory"),
    SourceSpec(
        "stock_price_forward",
        "ashare_stock_price_forward.parquet",
        ("stock_code", "date", "close", "open", "adj_factor"),
        ("date",),
    ),
    SourceSpec(
        "stock_trade",
        "ashare_stock_trade.parquet",
        (
            "stock_code",
            "date",
            "market_value",
            "negotiable_market_value",
            "turn_value",
            "turnover_rate_free",
            "change_pct",
        ),
        ("date",),
    ),
    SourceSpec(
        "stock_value",
        "ashare_stock_value.parquet",
        ("stock_code", "date", "pe_ttm", "pb_lf", "ps_ttm", "dv"),
        ("date",),
    ),
    SourceSpec(
        "stock_master",
        "ashare_stock.parquet",
        ("stock_code", "list_date", "list_state"),
        ("list_date",),
    ),
    SourceSpec(
        "stock_st",
        "ashare_stock_st.parquet",
        ("stock_code", "implement_date", "remove_date"),
        ("implement_date", "remove_date"),
    ),
    SourceSpec(
        "stock_suspend",
        "ashare_stock_suspend.parquet",
        ("stock_code", "date", "if_suspend"),
        ("date",),
    ),
    SourceSpec(
        "stock_limit",
        "ashare_stock_limit.parquet",
        ("stock_code", "date", "surged_limit", "decline_limit"),
        ("date",),
    ),
    SourceSpec(
        "trade_calendar",
        "ashare_tradeday.parquet",
        ("date", "IfTradingDay", "IfMonthEnd"),
        ("date",),
    ),
    SourceSpec(
        "stock_industry",
        "ashare_stock_industry.parquet",
        ("stock_code", "first_industry_name", "standard_code"),
    ),
    SourceSpec(
        "stock_balance",
        "ashare_stock_balance.parquet",
        (
            "stock_code",
            "end_date",
            "info_publ_date",
            "total_assets",
            "total_liability",
            "total_shareholder_equity",
        ),
        ("end_date", "info_publ_date"),
    ),
    SourceSpec(
        "stock_income",
        "ashare_stock_income.parquet",
        (
            "stock_code",
            "end_date",
            "info_publ_date",
            "total_operating_revenue",
            "operating_profit",
            "net_profit",
        ),
        ("end_date", "info_publ_date"),
    ),
    SourceSpec(
        "stock_cashflow",
        "ashare_stock_cashflow.parquet",
        ("stock_code", "end_date", "info_publ_date", "net_operate_cash_flow"),
        ("end_date", "info_publ_date"),
    ),
    SourceSpec(
        "macro_cache",
        "macro_cache.parquet",
        (
            "__index_level_0__",
            "cpi_yoy",
            "ppi_yoy",
            "bond_yield_10y",
            "credit_spread",
            "term_spread",
            "m1_yoy",
            "m2_yoy",
            "social_financing_yoy",
            "gdp_real_yoy",
            "industrial_prod_yoy",
            "sh_volatility",
            "ep",
            "dp",
        ),
        ("__index_level_0__",),
    ),
    *tuple(
        SourceSpec(
            key,
            filename,
            (
                "date",
                "info_publ_date",
                "indicator_code",
                "indicator_name",
                "data_value",
                "disclosure_frequency",
            ),
            ("date", "info_publ_date"),
        )
        for key, filename in (
            ("macro_cpi", "macro_cpi.parquet"),
            ("macro_ppi", "macro_ppi.parquet"),
            ("macro_pmi", "macro_pmi.parquet"),
            ("macro_money_supply", "macro_money_supply.parquet"),
            ("macro_social_financing", "macro_social_financing.parquet"),
            ("macro_lpr", "macro_lpr.parquet"),
            ("macro_industrial_production", "macro_industrial_production.parquet"),
        )
    ),
    SourceSpec(
        "bond_yield_curve",
        "bond_yield_curve.parquet",
        (
            "date",
            "curve_code",
            "curve_name",
            "years_to_maturity",
            "yield_type",
            "yield_value",
        ),
        ("date",),
    ),
    SourceSpec(
        "bond_shibor",
        "bond_shibor.parquet",
        ("date", "maturity_raw", "rate"),
        ("date",),
    ),
    SourceSpec(
        "csiindex_trade",
        "ashare_csiindex_trade.parquet",
        (
            "index_code",
            "date",
            "close",
            "change_pct",
            "turnover_value",
            "total_mv",
            "pe",
            "dv",
        ),
        ("date",),
    ),
    SourceSpec(
        "index_value",
        "ashare_index_value.parquet",
        (
            "index_code",
            "date",
            "pe_ttm",
            "pb_lf",
            "ps_ttm",
            "dv",
        ),
        ("date",),
    ),
    SourceSpec(
        "index_trade",
        "ashare_index_trade.parquet",
        (
            "index_code",
            "date",
            "turnover_value",
            "change_pct",
            "negotiable_market_value",
        ),
        ("date",),
    ),
)


SUBSTITUTE_SPECS: Final[tuple[SubstituteSpec, ...]] = (
    SubstituteSpec(
        "D1",
        "Chen-Zimmermann/OpenAP 212 特征面板",
        "本地因子元数据、实际 factors/ 与可由行情、估值、财报衍生的 A 股因子",
        "原美股 OpenAP 面板本地不可得；只接收实际存在且审计过的本地因子",
        ("AS1",),
        (
            "factor_metadata",
            "factor_panel_dir",
            "stock_price_forward",
            "stock_trade",
            "stock_value",
            "stock_balance",
            "stock_income",
            "stock_cashflow",
        ),
    ),
    SubstituteSpec(
        "D2",
        "1963-2024 美股股票月面板",
        "本地可用期 A 股前复权股票月面板与历史可交易性状态",
        "本地美股覆盖不足，A 股日频数据可严格重采样为目标市场股票月",
        ("AS4", "AS23"),
        (
            "stock_price_forward",
            "stock_trade",
            "stock_master",
            "stock_st",
            "stock_suspend",
            "stock_limit",
            "trade_calendar",
        ),
    ),
    SubstituteSpec(
        "D3",
        "OpenAP 逐信号方向元数据",
        "训练窗内估计并在验证/预测期冻结的本地方向",
        "本地没有原 212 信号方向表，且方向估计不得读取未来期收益",
        ("AS2",),
        ("factor_metadata", "factor_panel_dir"),
    ),
    SubstituteSpec(
        "D4",
        "原 212 信号八家族固定映射",
        "本地四字段按 AS26 固定关键词生成的一对一交叉表及 SHA-256",
        "原逐信号映射与 empirical package 不可得",
        ("AS3", "AS26"),
        ("factor_metadata",),
    ),
    SubstituteSpec(
        "D5",
        "美国 23 个宏观条件变量",
        "七个外部宏观块加 D7 明确指数输入形成 Trend，共同覆盖八块经济角色",
        "本地无原 FRED/ALFRED 序列，不强求变量身份或数量相同",
        ("AS5", "AS25"),
        (
            "macro_cache",
            "macro_cpi",
            "macro_ppi",
            "macro_pmi",
            "macro_money_supply",
            "macro_social_financing",
            "macro_lpr",
            "macro_industrial_production",
            "bond_yield_curve",
            "bond_shibor",
            "csiindex_trade",
            "index_value",
        ),
        (
            ("macro_cache", "primary_consumed"),
            ("macro_cpi", "detail_fallback"),
            ("macro_ppi", "detail_fallback"),
            ("macro_pmi", "primary_consumed"),
            ("macro_money_supply", "detail_fallback"),
            ("macro_social_financing", "detail_fallback"),
            ("macro_lpr", "primary_consumed"),
            ("macro_industrial_production", "detail_fallback"),
            ("bond_yield_curve", "rates_credit_fallback"),
            ("bond_shibor", "rates_fallback"),
            ("csiindex_trade", "D7_market_trend_input"),
            ("index_value", "D7_market_valuation_input"),
        ),
    ),
    SubstituteSpec(
        "D6",
        "ALFRED 实时与保守 vintage",
        "真实 info_publ_date 与固定保守滞后中较晚的本地可用日",
        "本地无 vintage 修订历史；实际披露字段存在时仍不得早于保守下限",
        ("AS6", "AS16"),
        (
            "macro_cache",
            "macro_cpi",
            "macro_ppi",
            "macro_pmi",
            "macro_money_supply",
            "macro_social_financing",
            "macro_lpr",
            "macro_industrial_production",
        ),
    ),
    SubstituteSpec(
        "D7",
        "原美股面板衍生市场状态",
        "调用方明确指定宽基指数代码后的 A 股指数趋势、风险、估值与流动性原料",
        "原美股底层面板不可得；spec 未指定 A 股基准代码，禁止静默猜测",
        ("AS7", "AS25"),
        ("csiindex_trade", "index_value", "index_trade", "stock_trade"),
    ),
    SubstituteSpec(
        "D8",
        "美国 FF5 加动量",
        "A 股本地市场、规模、价值、盈利、投资与动量控制组合原料",
        "本地没有美国 FF5+MOM 收益序列",
        ("AS8",),
        (
            "stock_price_forward",
            "stock_trade",
            "stock_value",
            "stock_balance",
            "stock_income",
            "csiindex_trade",
        ),
    ),
    SubstituteSpec(
        "D9",
        "原美股容量与横截面控制",
        "T 时点流通市值、申万一级行业、历史 beta 与成交换手代理",
        "使用 data_catalog 明示、可按时点观测的 A 股字段",
        ("AS9",),
        ("stock_trade", "stock_industry", "csiindex_trade"),
    ),
    SubstituteSpec(
        "D10",
        "原 212 信号发表年份",
        "本地因子面板首次非缺失月份",
        "本地没有 publication year；该替代只用于数据可用性覆盖审计",
        ("AS10", "AS20"),
        ("factor_panel_dir",),
    ),
)


MACRO_SERIES_SPECS: Final[tuple[MacroSeriesSpec, ...]] = (
    MacroSeriesSpec("Inflation", "cpi_yoy", "macro_cache", "cpi_yoy", "monthly", 1, 0),
    MacroSeriesSpec(
        "Inflation",
        "cpi_yoy",
        "macro_cpi",
        "data_value",
        "monthly",
        1,
        1,
        "110255493",
    ),
    MacroSeriesSpec("Inflation", "ppi_yoy", "macro_cache", "ppi_yoy", "monthly", 1, 0),
    MacroSeriesSpec(
        "Inflation",
        "ppi_yoy",
        "macro_ppi",
        "data_value",
        "monthly",
        1,
        1,
        "110002867",
    ),
    MacroSeriesSpec("Growth", "gdp_real_yoy", "macro_cache", "gdp_real_yoy", "quarterly", 4, 0),
    MacroSeriesSpec("Growth", "industrial_prod_yoy", "macro_cache", "industrial_prod_yoy", "monthly", 1, 0),
    MacroSeriesSpec(
        "Growth",
        "industrial_prod_yoy",
        "macro_industrial_production",
        "data_value",
        "monthly",
        1,
        1,
        "110000261",
    ),
    MacroSeriesSpec(
        "Growth",
        "manufacturing_pmi",
        "macro_pmi",
        "data_value",
        "monthly",
        1,
        0,
        "110166523",
    ),
    MacroSeriesSpec("Rates", "bond_yield_10y", "macro_cache", "bond_yield_10y", "monthly", 1, 0),
    MacroSeriesSpec(
        "Rates",
        "bond_yield_10y",
        "bond_yield_curve",
        "yield_value",
        "daily_market",
        0,
        1,
        transform="direct",
        selectors=(
            ("curve_code", 10),
            ("years_to_maturity", 10.0),
            ("yield_type", "到期"),
        ),
    ),
    MacroSeriesSpec("Rates", "term_spread", "macro_cache", "term_spread", "monthly", 1, 0),
    MacroSeriesSpec(
        "Rates",
        "term_spread",
        "bond_yield_curve",
        "yield_value",
        "daily_market",
        0,
        1,
        transform="government_term_spread_10y_1y",
        selectors=(("curve_code", 10), ("yield_type", "到期")),
    ),
    MacroSeriesSpec(
        "Rates",
        "lpr_1y",
        "macro_lpr",
        "data_value",
        "monthly",
        1,
        0,
        "110255796",
    ),
    MacroSeriesSpec(
        "Rates",
        "lpr_1y",
        "bond_shibor",
        "rate",
        "daily_market",
        0,
        1,
        transform="direct",
        selectors=(("maturity_raw", "SIBO1Y"),),
    ),
    MacroSeriesSpec("Credit", "credit_spread", "macro_cache", "credit_spread", "monthly", 1, 0),
    MacroSeriesSpec(
        "Credit",
        "credit_spread",
        "bond_yield_curve",
        "yield_value",
        "daily_market",
        0,
        1,
        transform="corporate_aaa_minus_government_10y",
        selectors=(("years_to_maturity", 10.0), ("yield_type", "到期")),
    ),
    MacroSeriesSpec(
        "Credit",
        "social_financing_yoy",
        "macro_cache",
        "social_financing_yoy",
        "monthly",
        1,
        0,
    ),
    MacroSeriesSpec(
        "Credit",
        "social_financing_yoy",
        "macro_social_financing",
        "data_value",
        "monthly",
        1,
        1,
        "110010352",
    ),
    MacroSeriesSpec("Liquidity", "m1_yoy", "macro_cache", "m1_yoy", "monthly", 1, 0),
    MacroSeriesSpec(
        "Liquidity",
        "m1_yoy",
        "macro_money_supply",
        "data_value",
        "monthly",
        1,
        1,
        "110111409",
    ),
    MacroSeriesSpec("Liquidity", "m2_yoy", "macro_cache", "m2_yoy", "monthly", 1, 0),
    MacroSeriesSpec(
        "Liquidity",
        "m2_yoy",
        "macro_money_supply",
        "data_value",
        "monthly",
        1,
        1,
        "110111411",
    ),
    MacroSeriesSpec("Risk", "sh_volatility", "macro_cache", "sh_volatility", "monthly", 1, 0),
    MacroSeriesSpec("Valuation", "earnings_yield", "macro_cache", "ep", "monthly", 1, 0),
    MacroSeriesSpec("Valuation", "dividend_yield", "macro_cache", "dp", "monthly", 1, 0),
)


@dataclass(frozen=True)
class R006M1Config:
    """m1 的路径、时点、窗口、映射和审计参数。"""

    data_root: Path = field(default_factory=get_data_root)
    source_specs: tuple[SourceSpec, ...] = SOURCE_SPECS
    substitutes: tuple[SubstituteSpec, ...] = SUBSTITUTE_SPECS
    macro_series_specs: tuple[MacroSeriesSpec, ...] = MACRO_SERIES_SPECS
    family_order: tuple[str, ...] = FAMILY_ORDER
    family_keywords: tuple[tuple[str, tuple[str, ...]], ...] = FAMILY_KEYWORDS
    family_field_priority: tuple[str, ...] = (
        "level1",
        "level2",
        "factor_id_cn",
        "factor_id",
    )
    short_english_keywords: tuple[str, ...] = ("pe", "pb", "ps", "roe", "roa")
    training_months: int = 120
    validation_months: int = 144
    prediction_freeze_months: int = 12
    minimum_total_history_months: int = 264
    monthly_macro_lag_months: int = 1
    quarterly_macro_lag_months: int = 4
    minimum_listing_trading_days: int = 120
    industry_standard_code: int = 38
    industry_start_date_candidates: tuple[str, ...] = (
        "effective_date",
        "in_date",
    )
    industry_end_date_candidates: tuple[str, ...] = ("out_date",)
    market_beta_window_months: int = 60
    market_beta_min_observations: int = 36
    market_beta_variance_floor: float = 1e-12
    government_curve_code: int = 10
    corporate_aaa_curve_code: int = 44
    short_maturity_years: float = 1.0
    long_maturity_years: float = 10.0
    bond_yield_type: str = "到期"
    direction_min_cross_section: int = 2
    direction_zero_policy: str = "fail"
    direction_missing_policy: str = "fail"
    direction_hash_algorithm: str = "sha256"
    required_macro_blocks: tuple[str, ...] = (
        "Inflation",
        "Growth",
        "Rates",
        "Credit",
        "Liquidity",
        "Risk",
        "Valuation",
        "Trend",
    )
    sa11_extra_lag_months: int = 1
    sa11_beta_window_months: int = 60
    sa11_beta_min_observations: int = 24
    sa11_variance_floor: float = 1e-12
    crosswalk_hash_algorithm: str = "sha256"
    factor_file_suffix: str = ".parquet"
    factor_value_candidates: tuple[str, ...] = ("factor_value", "value")
    stock_key: str = "stock_code"
    source_date_key: str = "date"
    signal_date_key: str = "signal_date"
    financial_publication_key: str = "info_publ_date"
    financial_period_key: str = "end_date"
    formal_factor_min_files: int = 1
    schedule_month_frequency: str = "M"
    coverage_date_format: str = "%Y-%m-%d"
    hash_encoding: str = "utf-8"
    benchmark_index_code: str | None = None


DEFAULT_CONFIG: Final[R006M1Config] = R006M1Config()
