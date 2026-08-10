"""m1 数据、特征、标签与样本切分配置。

六通道、60日窗口和 T+1 至 T+21 标签均来自用户授权的 AS9/AS10
降级口径，不代表原研报私有参数。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from common.data_loader import LOCAL_DATA_DIR


@dataclass(frozen=True)
class DataFiles:
    """m1 所需本地数据文件。"""

    root: Path = LOCAL_DATA_DIR
    forward_price: str = "ashare_stock_price_forward.parquet"
    raw_price: str = "ashare_stock_price.parquet"
    trade: str = "ashare_stock_trade.parquet"
    stock_master: str = "ashare_stock.parquet"
    st_status: str = "ashare_stock_st.parquet"
    suspend_status: str = "ashare_stock_suspend.parquet"
    limit_status: str = "ashare_stock_limit.parquet"
    trade_calendar: str = "ashare_tradeday.parquet"


@dataclass(frozen=True)
class FeatureConfig:
    """AS10 六通道价量输入与训练期预处理配置。"""

    price_columns: tuple[str, ...] = ("open", "high", "low", "close")
    previous_close_column: str = "prev_close"
    volume_column: str = "volume"
    turn_value_column: str = "turn_value"
    output_columns: tuple[str, ...] = (
        "open_rel_prev_close",
        "high_rel_prev_close",
        "low_rel_prev_close",
        "close_rel_prev_close",
        "volume_log1p",
        "turn_value_log1p",
    )
    window_length: int = 60
    winsor_lower_quantile: float = 0.005
    winsor_upper_quantile: float = 0.995
    std_epsilon: float = 1e-12

    def as_mapping(self) -> dict[str, object]:
        return {
            "price_columns": self.price_columns,
            "previous_close_column": self.previous_close_column,
            "volume_column": self.volume_column,
            "turn_value_column": self.turn_value_column,
            "output_columns": self.output_columns,
        }


@dataclass(frozen=True)
class LabelConfig:
    """AS9 标签与 AS14 前复权VWAP推导/全局中止阈值。"""

    entry_offset: int = 1
    exit_offset: int = 21
    output_column: str = "forward_adjusted_vwap"
    sanity_min_price_ratio: float = 0.1  # AS14：逐行价格比下界
    sanity_max_price_ratio: float = 10.0  # AS14：逐行价格比上界
    sanity_min_fraction: float = 0.95  # AS14：低于该全局合格率即中止m1


@dataclass(frozen=True)
class SplitConfig:
    """报告披露的训练、验证、回测区间及显式防暴露间隔。"""

    train_name: str = "train"
    train_start: str = "2008-01-01"
    train_end: str = "2016-12-31"
    validation_name: str = "validation"
    validation_start: str = "2017-02-01"
    validation_end: str = "2019-11-30"
    backtest_name: str = "backtest"
    backtest_start: str = "2020-01-01"
    backtest_end: str = "2024-12-31"


@dataclass(frozen=True)
class UniverseConfig:
    """AS4 的信号日动态股票池配置。"""

    minimum_listing_years: int = 1


@dataclass(frozen=True)
class M1Config:
    """m1 完整配置；不包含任何模型或组合回测参数。"""

    data: DataFiles = field(default_factory=DataFiles)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    labels: LabelConfig = field(default_factory=LabelConfig)
    splits: SplitConfig = field(default_factory=SplitConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)


DEFAULT_CONFIG = M1Config()


@dataclass(frozen=True)
class GRUModelConfig:
    """AS2 的单层64维 GRU 回归基准。"""

    input_size: int = 6
    hidden_size: int = 64
    num_layers: int = 1
    dropout: float = 0.0
    output_size: int = 1


@dataclass(frozen=True)
class M2TrainingConfig:
    """AS2/AS9 的统一训练、早停和样本外预测配置。"""

    train_split: str = "train"
    validation_split: str = "validation"
    backtest_split: str = "backtest"
    loss_name: str = "mse"
    optimizer_name: str = "adam"
    learning_rate: float = 1e-3
    batch_size: int = 512
    max_epochs: int = 100
    early_stopping_patience: int = 10
    early_stopping_min_delta: float = 0.0
    weight_decay: float = 0.0
    seed: int = 42
    shuffle_training: bool = True
    num_workers: int = 0
    device: str = "auto"
    deterministic_warn_only: bool = True
    prediction_column: str = "prediction"


@dataclass(frozen=True)
class M2Config:
    """m2 受控比较框架与 GRU 基准的完整集中配置。"""

    model: GRUModelConfig = field(default_factory=GRUModelConfig)
    training: M2TrainingConfig = field(default_factory=M2TrainingConfig)


M2_DEFAULT_CONFIG = M2Config()


# m3 仅追加 AS11 液态网络配置，不修改上方 m1/m2 参数。
@dataclass(frozen=True)
class LiquidDependencyConfig:
    """固定 ``ncps`` 来源与方法级降级边界。"""

    source_url: str = "https://github.com/mlech26l/ncps"
    source_commit: str = "695ec22d7d1831f2ced67346ef7d2f08c525bd47"
    package_version: str = "1.0.1"
    source_license: str = "Apache-2.0"
    method_scope: str = "方法级降级复现：固定开源标准实现，非原研报私有参数"


@dataclass(frozen=True)
class LiquidModelConfig:
    """AS11 的四类液态网络共同参数与一一映射。"""

    input_size: int = 6
    units: int = 64
    output_size: int = 1
    wiring_output_size: int = 1
    autoncp_sparsity_level: float = 0.5
    autoncp_seed: int = 22222
    batch_first: bool = True
    return_sequences: bool = False
    mixed_memory: bool = False
    ltc_ode_unfolds: int = 6
    cfc_mode: str = "default"
    model_specs: tuple[tuple[str, str, str], ...] = (
        ("LTC", "ltc", "ltc"),
        ("NCP（LTC）", "ncp_ltc", "ncp_ltc"),
        ("CFC", "cfc", "cfc"),
        ("NCP（CFC）", "ncp_cfc", "ncp_cfc"),
    )


@dataclass(frozen=True)
class M3Config:
    """m3 液态网络族与 m2 共享训练设置的完整集中配置。"""

    dependency: LiquidDependencyConfig = field(default_factory=LiquidDependencyConfig)
    model: LiquidModelConfig = field(default_factory=LiquidModelConfig)
    training: M2TrainingConfig = field(default_factory=M2TrainingConfig)


M3_DEFAULT_CONFIG = M3Config()


# m4 仅追加预测因子与组合回测配置，不修改上方 m1-m3 参数。
@dataclass(frozen=True)
class M4PortfolioConfig:
    """F8/B6-B12 与 AS3-AS8 的集中组合回测参数。"""

    model_names: tuple[str, ...] = (
        "GRU",
        "LTC",
        "NCP（LTC）",
        "CFC",
        "NCP（CFC）",
    )
    model_column: str = "model"
    stock_column: str = "stock_code"
    signal_date_column: str = "date"
    prediction_column: str = "prediction"
    forward_return_column: str = "label"
    market_date_column: str = "date"
    market_price_column: str = "forward_adjusted_vwap"
    market_tradable_column: str = "tradable"
    n_groups: int = 10
    rebalance_interval: int = 20
    path_offsets: tuple[int, ...] = tuple(range(20))
    entry_offset: int = 1
    exit_offset: int = 21
    sell_fee_rate: float = 0.003
    initial_capital: float = 1.0
    periods_per_year: int = 252
    risk_free_rate_per_day: float = 0.0
    factor_correlation_method: str = "pearson"
    min_cross_section_size: int = 10
    share_epsilon: float = 1e-12


@dataclass(frozen=True)
class M4Config:
    """m4 五模型预测因子、十档与20路径回测配置。"""

    portfolio: M4PortfolioConfig = field(default_factory=M4PortfolioConfig)


M4_DEFAULT_CONFIG = M4Config()


# m5 仅追加结果对齐与输出配置，不修改上方 m1-m4 参数。
@dataclass(frozen=True)
class M5ReferenceConfig:
    """R1-R7 正文摘要基准；与复现计算结果分栏保存，禁止混用。"""

    ltc_literature_improvement_range: tuple[float, float] = (0.05, 0.70)
    report_factor_correlation_range: tuple[float, float] = (0.69, 0.82)
    factor_correlation_method: str = "pearson"
    factor_correlation_sample_scope: str = "pairwise_complete_signal_date_stock_code"
    factor_correlation_min_common: int = 30
    factor_correlation_min_unique_values: int = 2
    comparison_layer: str = "model"
    comparison_verification_level: str = "directional"
    comparison_attribution_status: str = "assumption_linked"
    comparison_assumption_links: tuple[str, ...] = (
        "AS9",
        "AS10",
        "AS11",
        "AS12",
        "AS18",
    )
    report_gpu_memory_gb: tuple[tuple[str, float], ...] = (
        ("GRU", 120.0),
        ("LTC", 80.0),
        ("NCP（LTC）", 80.0),
        ("CFC", 6.0),
        ("NCP（CFC）", 6.0),
    )
    report_performance: tuple[tuple[str, str, str, float, float], ...] = (
        ("GRU", "top_long", "all", 0.2421, 0.88),
        ("LTC", "top_long", "all", 0.2221, 0.87),
        ("NCP（LTC）", "top_long", "all", 0.2438, 0.95),
        ("CFC", "top_long", "all", 0.2323, 0.93),
        ("NCP（CFC）", "top_long", "all", 0.2365, 0.91),
        ("GRU", "top_long", "2024", 0.1343, 0.28),
        ("LTC", "top_long", "2024", 0.0953, 0.20),
        ("NCP（LTC）", "top_long", "2024", 0.1350, 0.30),
        ("CFC", "top_long", "2024", 0.1005, 0.21),
        ("NCP（CFC）", "top_long", "2024", 0.1136, 0.24),
        ("GRU", "top_bottom", "all", 0.6557, 5.22),
        ("LTC", "top_bottom", "all", 0.5889, 5.66),
        ("NCP（LTC）", "top_bottom", "all", 0.6241, 5.26),
        ("CFC", "top_bottom", "all", 0.6080, 5.53),
        ("NCP（CFC）", "top_bottom", "all", 0.6269, 5.50),
        ("GRU", "top_bottom", "2024", 0.5150, 2.58),
        ("LTC", "top_bottom", "2024", 0.3936, 2.48),
        ("NCP（LTC）", "top_bottom", "2024", 0.4660, 2.82),
        ("CFC", "top_bottom", "2024", 0.4264, 2.69),
        ("NCP（CFC）", "top_bottom", "2024", 0.4125, 2.23),
    )


@dataclass(frozen=True)
class M5OutputConfig:
    """m5 文件、图表与可审计抽样上限。"""

    figure_title_prefix: str = "复现生成—非原图复刻"
    figure_dpi: int = 300
    time_series_figure_size: tuple[float, float] = (12.0, 6.0)
    standard_figure_size: tuple[float, float] = (10.0, 6.0)
    primary_blue: str = "#1f77b4"
    primary_red: str = "#d62728"
    neutral_gray: str = "#7f7f7f"
    excel_detail_row_limit: int = 50_000
    plot_point_limit: int = 50_000
    feature_importance_batch_size: int = 512
    json_indent: int = 2
    metrics_filename: str = "metrics.json"
    comparison_filename: str = "comparison.json"
    workbook_filename: str = "backtest_summary.xlsx"


@dataclass(frozen=True)
class M5Config:
    """m5 结果对齐、稳健性与完整输出的集中配置。"""

    reference: M5ReferenceConfig = field(default_factory=M5ReferenceConfig)
    output: M5OutputConfig = field(default_factory=M5OutputConfig)


M5_DEFAULT_CONFIG = M5Config()
