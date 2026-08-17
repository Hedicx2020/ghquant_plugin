"""r007 的集中数据、滚动预测、依赖版本与模型参数配置。

本文件只声明 ``plan.md``、``spec.md`` 与 ``assumptions.md`` 已确定的
数据迁移、预处理、模型、m4 组合/基线及 m5 敏感性口径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from common.data_loader import get_data_root


@dataclass(frozen=True)
class DataFiles:
    """AS11–AS13 对应的本地替代数据文件。"""

    root: Path = field(default_factory=get_data_root)
    us_stock_quote: str = "usshare_stock_quote.parquet"
    us_index_metadata: str = "usshare_index.parquet"
    overseas_index_price: str = "osshare_index_price.parquet"
    cn_stock_price_forward: str = "ashare_stock_price_forward.parquet"
    cn_stock_trade: str = "ashare_stock_trade.parquet"
    cn_index_trade: str = "ashare_csiindex_trade.parquet"
    cn_trade_calendar: str = "ashare_tradeday.parquet"
    cn_stock_industry: str = "ashare_stock_industry.parquet"

    def path(self, file_name: str) -> Path:
        """返回数据文件绝对路径，实际存在性由加载器审计。"""
        return self.root / file_name


@dataclass(frozen=True)
class SampleConfig:
    """D1/D2/B1 的实验样本与全样本选池口径。"""

    start_date: str = "2014-01-01"
    end_date: str = "2021-12-31"
    end_exclusive: str = "2022-01-01"
    stocks_per_market: int = 500
    market_cap_batch_rows: int = 250_000


def _default_us_cache_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "workspace"
        / "r007_cross_market_return_forecasting"
        / "data_cache"
        / "us_yahoo_union500_v1"
    )


def _default_legacy_us_cache_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "workspace"
        / "r007_cross_market_return_forecasting"
        / "data_cache"
        / "us_yahoo_sp500_20211230"
    )


@dataclass(frozen=True)
class USYahooConfig:
    """AS19/AS24–AS26 的固定联合候选池、下载与缓存合同。"""

    cache_dir: Path = field(default_factory=_default_us_cache_dir)
    legacy_cache_dir: Path = field(default_factory=_default_legacy_us_cache_dir)
    primary_constituents_url: str = (
        "https://en.wikipedia.org/w/index.php?"
        "title=List_of_S%26P_500_companies&oldid=1365256480"
    )
    primary_revision_oldid: str = "1365256480"
    primary_revision_timestamp: str = "2026-07-21T06:56:32Z"
    primary_expected_html_sha256: str = (
        "bce53c14645cc6dbcd667abce5f9f7b2987e89daa167241eb1671ea4a22d33be"
    )
    primary_expected_symbol_sha256: str = (
        "6d4f0619598357c95da15ae5115789bf2d55065f5bf1da50e4a7bbcbfafe08d1"
    )
    primary_expected_constituents: int = 503
    supplement_constituents_url: str = (
        "https://en.wikipedia.org/w/index.php?"
        "title=List_of_S%26P_500_companies&oldid=1062834329"
    )
    supplement_revision_oldid: str = "1062834329"
    supplement_revision_timestamp: str = "2021-12-30T20:37:08Z"
    supplement_expected_html_sha256: str = (
        "4ed0df8fd6909d15393d507f3c52bfd0fde7a75b939ced14e0b19758b11c93ac"
    )
    supplement_expected_symbol_sha256: str = (
        "d970ebb5508e556a95665731cb20d70b18b8bf2207d44f6a146a329f7a94209d"
    )
    supplement_expected_constituents: int = 505
    expected_constituents: int = 501
    minimum_successful_securities: int = 500
    maximum_failed_securities: int = 1
    legacy_authorized_success_count: int = 42
    interval: str = "1d"
    auto_adjust: bool = False
    actions: bool = True
    repair: bool = False
    keepna: bool = True
    threads: bool = False
    timeout_seconds: int = 30
    minimum_ohlcv_non_null_rate: float = 0.95
    maximum_retries: int = 5
    retry_backoff_seconds: tuple[int, ...] = (2, 4, 8, 16, 32)
    retry_jitter_seconds: float = 0.5
    success_wait_seconds: float = 2.0
    consecutive_rate_auth_limit: int = 3
    pause_seconds: int = 15 * 60
    user_agent: str = "r007-research-reproduction/1.0"

    @property
    def prices_dir(self) -> Path:
        return self.cache_dir / "prices"

    @property
    def manifest_path(self) -> Path:
        return self.cache_dir / "manifest.json"

    @property
    def constituents_path(self) -> Path:
        return self.cache_dir / "constituents.csv"

    @property
    def source_html_path(self) -> Path:
        return self.cache_dir / "source_primary_page.html"

    @property
    def supplement_source_html_path(self) -> Path:
        return self.cache_dir / "source_supplement_page.html"

    @property
    def precheck_manifest_path(self) -> Path:
        return self.cache_dir / "precheck_manifest.json"

    @property
    def merged_panel_path(self) -> Path:
        return self.cache_dir / "us_panel.parquet"

    @property
    def audit_summary_path(self) -> Path:
        return self.cache_dir / "audit_summary.json"


@dataclass(frozen=True)
class ReturnConfig:
    """F1–F3、B2/B3 与 AS5/AS9 的收益和流动性口径。"""

    stock_column: str = "stock_code"
    date_column: str = "date"
    open_column: str = "open"
    high_column: str = "high"
    low_column: str = "low"
    close_column: str = "close"
    volume_column: str = "volume"
    market_cap_column: str = "market_cap"
    traded_amount_column: str = "traded_amount"

    pvclcl_raw_column: str = "pvclcl_raw"
    opcl_raw_column: str = "opcl_raw"
    pvclcl_market_column: str = "pvclcl_market"
    opcl_market_column: str = "opcl_market"
    pvclcl_excess_column: str = "pvclcl_excess"
    opcl_excess_column: str = "opcl_excess"
    liquidity_median_column: str = "traded_amount_median_21d"

    liquidity_window_days: int = 21
    training_window_days: int = 250
    winsor_lower_quantile: float = 0.005
    winsor_upper_quantile: float = 0.995
    graph_update_days: int = 10


@dataclass(frozen=True)
class MarketSession:
    """交易所本地时区下的开收盘时刻。"""

    market: str
    timezone: str
    open_time: str
    close_time: str


@dataclass(frozen=True)
class DirectionConfig:
    """B4/AS3 的跨市场预测方向和研报滞后参数。"""

    name: str
    source_market: str
    target_market: str
    lag_parameter: int


@dataclass(frozen=True)
class CalendarConfig:
    """D8/AS3 的时段、市场基准与因果映射配置。"""

    us_session: MarketSession = field(
        default_factory=lambda: MarketSession(
            market="US",
            timezone="America/New_York",
            open_time="09:30:00",
            close_time="16:00:00",
        )
    )
    cn_session: MarketSession = field(
        default_factory=lambda: MarketSession(
            market="CN",
            timezone="Asia/Shanghai",
            open_time="09:30:00",
            close_time="15:00:00",
        )
    )
    directions: tuple[DirectionConfig, ...] = field(
        default_factory=lambda: (
            DirectionConfig(
                name="US_TO_CN",
                source_market="US",
                target_market="CN",
                lag_parameter=1,
            ),
            DirectionConfig(
                name="CN_TO_US",
                source_market="CN",
                target_market="US",
                lag_parameter=0,
            ),
        )
    )
    cn_market_index_code: str = "000300"
    us_broad_index_exact_names: tuple[str, ...] = (
        "标普500指数",
        "S&P 500 Index",
    )
    required_index_calendar_coverage: float = 1.0

    def session(self, market: str) -> MarketSession:
        """按市场代码返回交易时段，未知市场显式失败。"""
        sessions = {
            self.us_session.market: self.us_session,
            self.cn_session.market: self.cn_session,
        }
        try:
            return sessions[market]
        except KeyError as exc:
            raise KeyError(f"未知市场代码: {market}") from exc

    def direction(self, name: str) -> DirectionConfig:
        """按方向名返回 B4 配置，未知方向显式失败。"""
        matches = [item for item in self.directions if item.name == name]
        if len(matches) != 1:
            raise KeyError(f"方向配置不存在或不唯一: {name}")
        return matches[0]


@dataclass(frozen=True)
class M1Config:
    """m1 数据迁移、收益面板与审计接口的完整集中配置。"""

    data: DataFiles = field(default_factory=DataFiles)
    us_yahoo: USYahooConfig = field(default_factory=USYahooConfig)
    sample: SampleConfig = field(default_factory=SampleConfig)
    returns: ReturnConfig = field(default_factory=ReturnConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)


DEFAULT_CONFIG = M1Config()


@dataclass(frozen=True)
class DependencyVersionConfig:
    """AS15 固定的主结果运行时版本基线。"""

    python: str = "3.13.5"
    numpy: str = "2.5.1"
    pandas: str = "3.0.3"
    scikit_learn: str = "1.9.0"
    lightgbm: str = "4.6.0"
    xgboost: str = "3.0.3"

    def as_distribution_mapping(self) -> dict[str, str]:
        """返回 importlib.metadata 可直接核验的发行包名与版本。"""
        return {
            "numpy": self.numpy,
            "pandas": self.pandas,
            "scikit-learn": self.scikit_learn,
            "lightgbm": self.lightgbm,
            "xgboost": self.xgboost,
        }


@dataclass(frozen=True)
class ModelParameterConfig:
    """plan 2.1 逐项显式冻结的八个基础回归器参数。"""

    ols: dict[str, Any] = field(
        default_factory=lambda: {
            "fit_intercept": True,
            "copy_X": True,
            "tol": 1e-6,
            "n_jobs": None,
            "positive": False,
        }
    )
    lasso: dict[str, Any] = field(
        default_factory=lambda: {
            "alpha": 1.0,
            "fit_intercept": True,
            "precompute": False,
            "copy_X": True,
            "max_iter": 1000,
            "tol": 1e-4,
            "warm_start": False,
            "positive": False,
            "random_state": None,
            "selection": "cyclic",
        }
    )
    ridge: dict[str, Any] = field(
        default_factory=lambda: {
            "alpha": 1.0,
            "fit_intercept": True,
            "copy_X": True,
            "max_iter": None,
            "tol": 1e-4,
            "solver": "auto",
            "positive": False,
            "random_state": None,
        }
    )
    svm: dict[str, Any] = field(
        default_factory=lambda: {
            "kernel": "rbf",
            "C": 1.0,
            "epsilon": 0.1,
            "gamma": "scale",
            "degree": 3,
            "coef0": 0.0,
            "tol": 1e-3,
            "shrinking": True,
            "cache_size": 200,
            "verbose": False,
            "max_iter": -1,
        }
    )
    xgboost: dict[str, Any] = field(
        default_factory=lambda: {
            "objective": "reg:squarederror",
            "booster": "gbtree",
            "n_estimators": 100,
            "max_depth": 6,
            "learning_rate": 0.3,
            "min_child_weight": 1,
            "gamma": 0,
            "subsample": 1.0,
            "colsample_bytree": 1.0,
            "reg_alpha": 0,
            "reg_lambda": 1,
            "tree_method": "auto",
            "random_state": 42,
            "n_jobs": 1,
            "verbosity": 0,
        }
    )
    lightgbm: dict[str, Any] = field(
        default_factory=lambda: {
            "boosting_type": "gbdt",
            "objective": "regression",
            "num_leaves": 31,
            "max_depth": -1,
            "learning_rate": 0.1,
            "n_estimators": 100,
            "subsample_for_bin": 200000,
            "min_split_gain": 0.0,
            "min_child_weight": 0.001,
            "min_child_samples": 20,
            "subsample": 1.0,
            "subsample_freq": 0,
            "colsample_bytree": 1.0,
            "reg_alpha": 0.0,
            "reg_lambda": 0.0,
            "random_state": 42,
            "n_jobs": 1,
            "importance_type": "split",
            "verbosity": -1,
        }
    )
    random_forest: dict[str, Any] = field(
        default_factory=lambda: {
            "n_estimators": 100,
            "criterion": "squared_error",
            "max_depth": None,
            "min_samples_split": 2,
            "min_samples_leaf": 1,
            "min_weight_fraction_leaf": 0.0,
            "max_features": 1.0,
            "max_leaf_nodes": None,
            "min_impurity_decrease": 0.0,
            "bootstrap": True,
            "oob_score": False,
            "n_jobs": 1,
            "random_state": 42,
            "verbose": 0,
            "warm_start": False,
            "ccp_alpha": 0.0,
            "max_samples": None,
            "monotonic_cst": None,
        }
    )
    adaboost: dict[str, Any] = field(
        default_factory=lambda: {
            "n_estimators": 50,
            "learning_rate": 1.0,
            "loss": "linear",
            "random_state": 42,
        }
    )
    adaboost_base_tree: dict[str, Any] = field(
        default_factory=lambda: {
            "max_depth": 3,
            "random_state": 42,
        }
    )


@dataclass(frozen=True)
class RollingPredictionConfig:
    """B7、B11 与十模型输出字段的集中配置。"""

    prediction_start: str = "2016-01-01"
    prediction_end: str = "2021-12-31"
    target_column: str = "target_value"
    source_value_column: str = "pvclcl_excess"
    target_value_column: str = "opcl_excess"
    base_model_names: tuple[str, ...] = (
        "OLS",
        "LASSO",
        "RIDGE",
        "SVM",
        "XGBoost",
        "LGBM",
        "RF",
        "AdaBoost",
    )
    ensemble_average_name: str = "ensemble-avg"
    ensemble_median_name: str = "ensemble-med"

    def __post_init__(self) -> None:
        if date.fromisoformat(self.prediction_start) > date.fromisoformat(
            self.prediction_end
        ):
            raise ValueError("prediction_start 晚于 prediction_end")
        if len(self.base_model_names) != 8:
            raise ValueError("B11 要求恰好八个基础模型")
        if len(set(self.base_model_names)) != len(self.base_model_names):
            raise ValueError("基础模型名称不得重复")

    @property
    def all_model_names(self) -> tuple[str, ...]:
        """按 B11 返回八个基础模型与两个集成模型的固定顺序。"""
        return (
            *self.base_model_names,
            self.ensemble_average_name,
            self.ensemble_median_name,
        )


@dataclass(frozen=True)
class M3Config:
    """m3 依赖、模型和滚动区间的统一配置。"""

    pipeline: M1Config = field(default_factory=M1Config)
    versions: DependencyVersionConfig = field(default_factory=DependencyVersionConfig)
    models: ModelParameterConfig = field(default_factory=ModelParameterConfig)
    prediction: RollingPredictionConfig = field(
        default_factory=RollingPredictionConfig
    )


DEFAULT_M3_CONFIG = M3Config()


@dataclass(frozen=True)
class PortfolioBacktestConfig:
    """F20/F21/F24、B9/B10 的集中组合参数。"""

    portfolio_fractions: tuple[tuple[str, float], ...] = (
        ("qr1", 1.0),
        ("qr2", 0.8),
        ("qr3", 0.6),
        ("qr4", 0.4),
        ("qr5", 0.2),
        ("qr6", 0.1),
    )
    liquidity_participation_rate: float = 0.001
    us_position_cap: float = 100_000.0
    cn_position_cap: float = 1_500_000.0
    annualization_days: int = 252
    minimum_sharpe_observations: int = 2
    transaction_cost_rate: float = 0.0
    actual_return_match_tolerance: float = 1e-12

    def __post_init__(self) -> None:
        names = tuple(name for name, _ in self.portfolio_fractions)
        fractions = tuple(value for _, value in self.portfolio_fractions)
        if names != ("qr1", "qr2", "qr3", "qr4", "qr5", "qr6"):
            raise ValueError("F24 要求组合名严格为 qr1–qr6")
        if fractions != (1.0, 0.8, 0.6, 0.4, 0.2, 0.1):
            raise ValueError("F24 要求保留比例严格为全部/80/60/40/20/10%")
        if self.liquidity_participation_rate != 0.001:
            raise ValueError("F20/AS9 要求容量比例为0.001")
        if self.us_position_cap != 100_000.0:
            raise ValueError("B10 要求美国市场仓位上限为100000 USD")
        if self.cn_position_cap != 1_500_000.0:
            raise ValueError("B10 要求中国市场仓位上限为1500000 CNY")
        if self.annualization_days != 252:
            raise ValueError("F21 要求按252个交易日年化")
        if self.minimum_sharpe_observations < 2:
            raise ValueError("Sharpe 至少需要两个日度观测")
        if self.transaction_cost_rate != 0.0:
            raise ValueError("B9 要求主结果不计交易成本")
        if self.actual_return_match_tolerance < 0:
            raise ValueError("实现收益核对容差不得为负")

    def position_caps(self) -> dict[str, float]:
        """返回目标市场到本币仓位上限的映射。"""
        return {
            "US": self.us_position_cap,
            "CN": self.cn_position_cap,
        }


@dataclass(frozen=True)
class BaselineConfig:
    """F22/F23 的同市场图与 25 日非图自回归基线参数。"""

    autoregressive_lags: int = 25
    same_market_lag: int = 1
    cross_market_specification: str = "cross_market_graph"
    same_market_graph_specification: str = "same_market_graph"
    non_graph_specification: str = "same_market_non_graph"
    us_same_market_direction: str = "US_SAME_GRAPH"
    cn_same_market_direction: str = "CN_SAME_GRAPH"
    default_feature_set: str = "pvclcl_excess"

    def __post_init__(self) -> None:
        if self.autoregressive_lags != 25:
            raise ValueError("F22 要求非图基线使用此前25日收益")
        if self.same_market_lag != 1:
            raise ValueError("F23 要求同市场图响应领先预测变量一日")
        specifications = (
            self.cross_market_specification,
            self.same_market_graph_specification,
            self.non_graph_specification,
        )
        if len(set(specifications)) != 3:
            raise ValueError("三种主规格名称不得重复")

    def same_market_direction(self, market: str) -> str:
        """返回同市场图的固定方向名。"""
        directions = {
            "US": self.us_same_market_direction,
            "CN": self.cn_same_market_direction,
        }
        try:
            return directions[market]
        except KeyError as exc:
            raise KeyError(f"未知目标市场: {market}") from exc

    def non_graph_direction(self, market: str) -> str:
        """返回同市场非图基线的固定方向名。"""
        return self.same_market_direction(market).replace(
            "_GRAPH",
            "_NON_GRAPH",
        )

    def comparison_direction(self, target_market: str) -> str:
        """把三规格映射到 R3/R4 共用的跨市场逻辑方向。"""
        directions = {
            "CN": "US_TO_CN",
            "US": "CN_TO_US",
        }
        try:
            return directions[target_market]
        except KeyError as exc:
            raise KeyError(f"未知目标市场: {target_market}") from exc

    def expected_direction(
        self,
        specification: str,
        target_market: str,
    ) -> str:
        """返回每个规格与目标市场唯一允许的实际方向。"""
        if specification == self.cross_market_specification:
            return self.comparison_direction(target_market)
        if specification == self.same_market_graph_specification:
            return self.same_market_direction(target_market)
        if specification == self.non_graph_specification:
            return self.non_graph_direction(target_market)
        raise KeyError(f"未知 m4 规格: {specification}")

    @property
    def specifications(self) -> tuple[str, str, str]:
        """返回 R4 三规格固定顺序。"""
        return (
            self.cross_market_specification,
            self.same_market_graph_specification,
            self.non_graph_specification,
        )


@dataclass(frozen=True)
class CoreComparisonConfig:
    """R1/R3/R4 的文本基准与可计算参照值，不估读图中柱高。"""

    r1_one_level: float = 1.0
    r1_two_level: float = 2.0
    r1_strong_models: tuple[str, ...] = (
        "RIDGE",
        "LGBM",
        "ensemble-avg",
        "ensemble-med",
    )


@dataclass(frozen=True)
class M4Config:
    """m4 组合、两类基线和定性核心对照的完整配置。"""

    m3: M3Config = field(default_factory=M3Config)
    portfolio: PortfolioBacktestConfig = field(
        default_factory=PortfolioBacktestConfig
    )
    baseline: BaselineConfig = field(default_factory=BaselineConfig)
    comparison: CoreComparisonConfig = field(
        default_factory=CoreComparisonConfig
    )


DEFAULT_M4_CONFIG = M4Config()


@dataclass(frozen=True)
class SensitivityConfig:
    """R2、SA1–SA7 的集中参数，不把附录网格用于主结果选参。"""

    seed: int = 42
    hyperparameter_configuration_count: int = 111
    r2_reference_cell_count: int = 42
    edge_replacement_fractions: tuple[float, ...] = (
        0.0,
        0.2,
        0.4,
        0.6,
        0.8,
        1.0,
    )
    information_lags: tuple[int, ...] = (1, 2, 3, 4, 5)
    citic_standard_code: int = 37
    shock_feature_column: str = "pvclcl_market"
    feature_combinations: tuple[tuple[str, str, str], ...] = (
        ("US_pvCLCL_CN_pvCLCL", "pvclcl_excess", "pvclcl_excess"),
        ("US_pvCLCL_CN_OPCL", "pvclcl_excess", "opcl_excess"),
        ("US_OPCL_CN_pvCLCL", "opcl_excess", "pvclcl_excess"),
        ("US_OPCL_CN_OPCL", "opcl_excess", "opcl_excess"),
    )
    hyperparameter_grid: tuple[
        tuple[str, tuple[tuple[str, tuple[Any, ...]], ...]], ...
    ] = (
        (
            "LASSO",
            (("alpha", (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0, 1000.0)),),
        ),
        (
            "RIDGE",
            (("alpha", (1e-4, 1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0, 1000.0)),),
        ),
        ("SVM", (("C", (0.1, 1.0, 10.0, 100.0, 1000.0)),)),
        (
            "XGBoost",
            (
                ("max_depth", (3, 6, 9)),
                ("learning_rate", (0.01, 0.1, 0.2)),
                ("n_estimators", (50, 100, 300)),
            ),
        ),
        (
            "LGBM",
            (
                ("num_leaves", (10, 31, 90)),
                ("learning_rate", (0.01, 0.1, 0.2)),
                ("n_estimators", (50, 100, 300)),
            ),
        ),
        (
            "RF",
            (
                ("n_estimators", (50, 100, 300)),
                ("max_depth", (5, 10, 50)),
            ),
        ),
        (
            "AdaBoost",
            (
                ("estimator__max_depth", (1, 5, 10)),
                ("n_estimators", (50, 100, 300)),
                ("learning_rate", (0.01, 0.1, 0.2)),
            ),
        ),
    )
    r2_reference: tuple[
        tuple[str, tuple[float, ...], tuple[float, ...]], ...
    ] = (
        (
            "LASSO",
            (0.848, 0.969, 1.238, 1.650, 1.821, 1.777),
            (0.222, 0.247, 0.310, 0.398, 0.433, 0.424),
        ),
        (
            "RIDGE",
            (1.238, 1.293, 1.437, 1.715, 1.668, 1.550),
            (0.429, 0.430, 0.449, 0.510, 0.619, 0.461),
        ),
        (
            "SVM",
            (0.743, 0.751, 0.782, 0.719, 1.020, 0.836),
            (0.194, 0.196, 0.204, 0.188, 0.267, 0.218),
        ),
        (
            "XGBoost",
            (1.445, 1.480, 1.587, 1.539, 1.381, 0.964),
            (0.224, 0.247, 0.214, 0.309, 0.401, 0.233),
        ),
        (
            "LGBM",
            (1.320, 1.457, 1.541, 1.440, 1.652, 1.424),
            (0.348, 0.388, 0.422, 0.485, 0.466, 0.407),
        ),
        (
            "RF",
            (1.481, 1.558, 1.639, 1.799, 1.747, 1.090),
            (0.410, 0.422, 0.447, 0.486, 0.474, 0.351),
        ),
        (
            "AdaBoost",
            (1.389, 1.405, 1.549, 1.548, 1.100, 0.667),
            (0.358, 0.385, 0.436, 0.419, 0.305, 0.187),
        ),
    )

    def __post_init__(self) -> None:
        if self.seed < 0:
            raise ValueError("敏感性随机种子不得为负")
        if (
            self.hyperparameter_configuration_count != 111
            or self.r2_reference_cell_count != 42
        ):
            raise ValueError("SA3/R2 合同必须为111个配置与42个参考格")
        if self.edge_replacement_fractions != (
            0.0,
            0.2,
            0.4,
            0.6,
            0.8,
            1.0,
        ):
            raise ValueError("SA1 要求边替换比例为 0/20/40/60/80/100%")
        if self.information_lags != (1, 2, 3, 4, 5):
            raise ValueError("SA2 需覆盖主口径 l=1、l=2–4 及 Lag 4 后的 l=5")
        grid_models = tuple(model for model, _ in self.hyperparameter_grid)
        reference_models = tuple(model for model, _, _ in self.r2_reference)
        if grid_models != reference_models:
            raise ValueError("SA3 网格模型与 R2 七模型顺序不一致")
        if len(self.feature_combinations) != 4:
            raise ValueError("SA7 必须包含四种美中 pvCLCL/OPCL 联合特征组合")


@dataclass(frozen=True)
class ReportingConfig:
    """正式结果目录、图表与 Excel 的输出合同。"""

    output_dir: Path = field(
        default_factory=lambda: (
            Path(__file__).resolve().parents[2]
            / "output"
            / "r007_cross_market_return_forecasting"
            / "results"
        )
    )
    checkpoint_dir: Path = field(
        default_factory=lambda: (
            Path(__file__).resolve().parents[2]
            / "workspace"
            / "r007_cross_market_return_forecasting"
            / "checkpoints"
        )
    )
    smoke_dir: Path = field(
        default_factory=lambda: (
            Path(__file__).resolve().parents[2]
            / "workspace"
            / "r007_cross_market_return_forecasting"
            / "smoke"
        )
    )
    dpi: int = 300
    primary_blue: str = "#1f77b4"
    primary_red: str = "#d62728"
    matrix_cmap: str = "RdBu_r"
    time_series_size: tuple[float, float] = (12.0, 6.0)
    bar_size: tuple[float, float] = (10.0, 6.0)
    title_fontsize: int = 14
    axis_fontsize: int = 12
    legend_fontsize: int = 10
    excel_max_rows_per_sheet: int = 1_000_000
    fig03_requested_anchor_date: str = "2021-10-21"
    fig03_paper_universe: str = "industry_capped_254_us_x_235_cn"
    fig03_implemented_universe: str = "full_b1_proxy"
    fig03_reproduction_status: str = "degraded/substitute"
    fig03_missing_dependency: str = "D9"
    fig03_assumption_id: str = "AS27"
    fig03_paper_cn_row_count: int = 235
    fig03_paper_us_column_count: int = 254

    def __post_init__(self) -> None:
        if self.dpi != 300:
            raise ValueError("图表输出必须为 300 DPI")
        if self.primary_blue != "#1f77b4" or self.primary_red != "#d62728":
            raise ValueError("输出配色必须符合项目蓝红规范")
        date.fromisoformat(self.fig03_requested_anchor_date)
        if self.fig03_reproduction_status != "degraded/substitute":
            raise ValueError("FIG3 D9 缺失时只能标记 degraded/substitute")
        if (
            self.fig03_paper_cn_row_count != 235
            or self.fig03_paper_us_column_count != 254
        ):
            raise ValueError("FIG3 论文行业限额对象必须记录为 CN235×US254")


@dataclass(frozen=True)
class M5Config:
    """m5 敏感性、R2 精确对照与报告输出的完整配置。"""

    m4: M4Config = field(default_factory=M4Config)
    sensitivity: SensitivityConfig = field(default_factory=SensitivityConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)


DEFAULT_M5_CONFIG = M5Config()
