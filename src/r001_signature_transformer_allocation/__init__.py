"""r001 · Signature-Informed Transformer for Asset Allocation（SIT，A股迁移复现）。

milestone 进度：
- m1（本次）：数据层与 A股迁移 universe 构建 —— config / data。
- m2-m5：签名特征、SIT 架构、CVaR 训练与回测、消融敏感性（后续）。
"""

from __future__ import annotations

from .config import DEFAULT_CONFIG, SITConfig

__all__ = ["SITConfig", "DEFAULT_CONFIG"]
