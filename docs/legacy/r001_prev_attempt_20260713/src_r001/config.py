"""SIT（Signature-Informed Transformer）A股移植复现 —— 全局配置与假设锚点。

原文：Signature-Informed Transformer for Asset Allocation (arXiv 2510.03129v3)。
本文件集中登记所有可复现参数与「美股→A股」移植裁决，每条 AS-* 与
workspace/r001_signature_transformer_allocation/assumptions.md 对应。

数据红线（CLAUDE.md）：
  - 成分股按 ashare_index_components 的 in_date/out_date 时点对齐，无未来函数。
  - 收益率取 ashare_stock_price_forward（前复权 close）的对数差分。
  - 信号 T 日算、T+1 执行（回测走 common.allocation_backtest.portfolio_backtest）。
  - 全程禁用任何模拟/随机行情数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


# ---------------------------------------------------------------------------
# Universe 移植映射（AS-01/02/03/15）
#   原文四组 → A股对标；index_code 取自 ashare_index_components。
#   为对齐原文「~100 资产」且控制 CPU 计算量，超过 100 只的指数按样本期前
#   流动性（区间均成交额 amount）取前 top_n，登记为 AS-16。
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Universe:
    key: str
    index_code: str
    label: str
    analog: str           # 原文对标
    top_n: int            # 资产数上限（流动性截断）


UNIVERSES: Dict[str, Universe] = {
    "hs300":   Universe("hs300",   "399300.SZ", "沪深300",  "S&P100",    100),
    "chinext": Universe("chinext", "399006.SZ", "创业板指", "Nasdaq100", 100),
    "sse50":   Universe("sse50",   "000016.SH", "上证50",   "DJIA",       50),
    "csi800":  Universe("csi800",  "000906.SH", "中证800",  "宽基",      100),
}


# ---------------------------------------------------------------------------
# 时间窗（AS-04）：原文回测区间移植到 A 股。
#   样本内训练+回测 2016-01..2023-12；样本外 OOS 2024-01..最新。
#   信号用 lookback 天路径算签名；monthly（21 交易日）调仓。
# ---------------------------------------------------------------------------
TRAIN_START = "2016-01-01"
TRAIN_END   = "2023-12-31"
OOS_START   = "2024-01-01"
OOS_END     = "2025-12-31"

LOOKBACK = 60          # 每次调仓回看的路径长度（交易日）——签名输入 (AS-05)
REBALANCE = 21         # 调仓周期（交易日，≈月频）(AS-06)


# ---------------------------------------------------------------------------
# 签名参数（AS-07）：截断深度 N=3；lead-lag + time-augmentation。
#   通道数 d：对每只资产的 1 维对数收益路径做 time-augmentation(+1) 与
#   lead-lag(×2) → d=4；截断签名长度 sum_{k=1..3} d^k = 4+16+64 = 84。
#   （原文 siglength(4,3)=340 含更宽增强，此处取最小可复现增强，登记 AS-07。）
# ---------------------------------------------------------------------------
SIG_DEPTH = 3
SIG_CHANNELS = 4       # time-aug(1)+lead-lag 后维度
# 截断签名长度 = d + d^2 + d^3
SIG_LEN = SIG_CHANNELS + SIG_CHANNELS**2 + SIG_CHANNELS**3   # = 84


# ---------------------------------------------------------------------------
# 模型 / 几何注意力（AS-08/09）
#   B_ij = <S_i, S_j> * exp(-λ * d_ij)，λ 可学习（softplus 保正）；
#   d_ij 取签名向量欧氏距离。注意力 logits = QK^T/√dk + γ*B。
# ---------------------------------------------------------------------------
D_MODEL = 64
N_HEADS = 4
N_LAYERS = 2
DROPOUT = 0.1
LAMBDA_INIT = 1.0      # 几何衰减 λ 初值（经 softplus）
GAMMA_INIT = 1.0       # 几何 bias 融合系数初值


# ---------------------------------------------------------------------------
# 可微 CVaR-95 损失（AS-10）：Rockafellar-Uryasev + softplus 平滑。
#   min_w,ζ  ζ + 1/(α) * E[softplus(-r_p - ζ)] - κ*E[r_p]
#   α=0.05（CVaR-95）；κ 为收益项权重。
# ---------------------------------------------------------------------------
CVAR_ALPHA = 0.05
CVAR_KAPPA = 1.0       # 期望收益激励权重 (AS-11)
SOFTPLUS_BETA = 20.0   # softplus 近似 hinge 的锐度


# ---------------------------------------------------------------------------
# 训练（AS-12）：Adam lr=1e-4；CPU 下 epoch 压缩。
# ---------------------------------------------------------------------------
LR = 1e-4
EPOCHS = 40            # 原文 100，CPU 压缩至 40 (AS-12)
WEIGHT_DECAY = 1e-5
SEED = 42              # 固定随机种子，保证可复现


# ---------------------------------------------------------------------------
# 权重约束（AS-13）：长仓、满仓、单资产上限。
# ---------------------------------------------------------------------------
LONG_ONLY = True
MAX_WEIGHT = 0.10      # 单资产权重上限，防集中 (AS-13)

# 交易成本（AS-14）：双边 bps，回测换手计费。
COST_BPS = 10.0


# 缺失处理（AS-17）：样本期内缺失率 > 该阈值的股票剔除；其余停牌日收益率填 0。
MAX_MISSING_RATIO = 0.05
