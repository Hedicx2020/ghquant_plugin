"""r004：中国沪深北动态全 A 大小盘与成长价值风格箱。"""

from .config import AllAStyleBoxConfig, DEFAULT_CONFIG
from .data_pipeline import M1Dataset, build_m1_dataset, run_m1_synthetic_regression_checks
from .reporting import (
    M4Dataset,
    ReportingSpecification,
    build_m4_dataset,
    run_common_statistics_regression_checks,
    run_r7_synthetic_regression_checks,
    run_m4_synthetic_regression_checks,
)

__all__ = [
    "AllAStyleBoxConfig",
    "DEFAULT_CONFIG",
    "M1Dataset",
    "build_m1_dataset",
    "run_m1_synthetic_regression_checks",
    "M4Dataset",
    "ReportingSpecification",
    "build_m4_dataset",
    "run_common_statistics_regression_checks",
    "run_r7_synthetic_regression_checks",
    "run_m4_synthetic_regression_checks",
]
