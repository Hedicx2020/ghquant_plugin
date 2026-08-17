"""Vanguard 两阶段因子择时方法的中国 A 股实验性迁移。"""

from .config import ChinaFactorTimingConfig
from .data_pipeline import M1Dataset, build_m1_dataset

__all__ = ["ChinaFactorTimingConfig", "M1Dataset", "build_m1_dataset"]
