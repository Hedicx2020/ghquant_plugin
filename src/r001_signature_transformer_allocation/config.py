"""r001 · Signature-Informed Transformer (SIT) 集中配置。

单一参数源（dataclass）：所有数值/口径均在此登记，函数体内不得出现魔法数字。
每个字段注释其权威出处——spec 要素 ID（D/F/B/R/SA）或假设登记簿条目（AS*，见
``workspace/r001_signature_transformer_allocation/assumptions.md``）。

本案 reproduction_mode=experimental（美股→A股 CSI300 迁移，数值豁免）；m1 只用到
universe / 时间划分 / 窗口 / 日历特征 / 数据加载相关字段，其余（CVaR / 训练超参）
在此一并登记以避免后续 milestone 参数散落，由 m2-m5 引用。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class SITConfig:
    """SIT A股迁移复现的全局配置（frozen，禁改魔法数字）。"""

    # ---- universe（D1 / AS3 点时市值 top-N / AS12 美股→CSI300 迁移 / AS16 缩减）----
    index_code: str = "000300"                     # CSI300 母池（大盘蓝筹迁移锚，AS12）
    universe_primary_n: int = 50                    # 主档 top-50 资产（R4-A 锚，必跑）
    universe_reduced_n: tuple = (20, 30)            # 缩减档（AS16：R3 跨尺度 20 / R2 尺度 30）
    universe_supported_n: tuple = (10, 20, 30, 40, 50, 100)  # 全集（R1-R4 尺度，m4 按算力可扩）
    universe_anchor: str = "train_start"            # 固定资产集选样时点：train 起点点时快照
    #                                                 （防未来函数，绝不用未来在册成分；可切 "test_start"）
    market_cap_col: str = "market_value"            # 选样排序依据：总市值（AS3 top-N）

    # ---- 训练/验证/测试时间划分（D3 / AS13：train 起点 2000→2007 迁移）----
    train_start: str = "2007-01-01"                 # AS13：CSI300 成分史约束，原文 2000
    train_end: str = "2016-12-31"
    val_start: str = "2017-01-01"
    val_end: str = "2019-12-31"
    test_start: str = "2020-01-01"
    test_end: str = "2024-12-27"                    # 对齐原文 test 终点（D3）

    # ---- 回看/决策窗口（B8 / AS2）----
    lookback_h: int = 60                            # H：回看交易日（60 时间 token）
    decision_steps_k: int = 12                      # K：多步决策窗口（与 α 耦合防 CVaR 退化）
    signature_truncation_m: int = 2                 # 签名截断阶 M=2（F1，m2 用）

    # ---- CVaR 训练目标（F7 / AS1）----
    cvar_alpha: float = 0.80                        # 置信水平 α（(1-α)·K=2.4 非退化，m4 用）

    # ---- 日历特征 v_t（D4 / AS4：sin/cos 周期编码，维度 F=8）----
    calendar_feature_dim: int = 8                   # F=8（4 周期 × sin/cos）
    calendar_cycles: tuple = field(default_factory=lambda: (
        ("dow", 7.0, "dayofweek"),                  # 周内位（周期 7）
        ("month", 12.0, "month"),                   # 月（周期 12）
        ("dom", 31.0, "day"),                       # 月内日（周期 31）
        ("doy", 366.0, "dayofyear"),                # 年内位（周期 366）
    ))                                              # 每项 sin+cos → 4×2 = 8 维 = F

    # ---- 再平衡/成本（B3 月度 k-step / AS9 主表 0bps）----
    rebalance: str = "month_end"                    # 月度调仓（B3）
    cost_bps: float = 0.0                           # 主绩效表单边 0bps（AS9）；SA3 sweep 见 m5

    # ---- 数据加载 buffer ----
    price_buffer_days: int = 200                    # train 起点前多载历史（供 m2 签名 H=60 回看）

    # ---- 训练通用超参（B1，m4 用；登记于此避免散落）----
    adam_lr: float = 1e-3                           # Adam 学习率
    batch_size: int = 64
    dropout: float = 0.1
    max_epoch: int = 100
    early_stop_patience: int = 10
    seeds: tuple = (0, 1, 2)                        # AS5：固定 3 种子，报告 mean±std

    # ---- 评估口径（B6：4 指标、零无风险利率、月度）----
    periods_per_year: int = 12                      # 月度调仓 → 年化基数 12
    risk_free_rate: float = 0.0                     # 零无风险利率（B3/B6）

    # ---- m2 特征工程：路径签名 / 交叉签名（本 milestone 追加，只增不改）----
    signature_interpolation: str = "linear"         # D5「appropriate interpolation」→ 线性插值(piecewise-linear)，M=2 有精确闭式（AS20）
    signature_path_source: str = "log_return"       # 路径母源＝前复权对数收益累积＝log 价格路径(rebased)，签名平移不变+跨资产可比（D5；AS22）
    signature_time_augment: bool = True             # 逐资产路径时间增广 (t/H, 累积收益)，使单资产 M=2 signed-area 非退化（plan m2；AS21）
    signature_include_level0: bool = True           # 保留 level-0=1 常数项，忠于 F1「SigM=(1,∫dX,∫∫dX⊗dX)」（p2）
    cross_signature_dim: int = 2                    # d_cross-sig=2：每资产对存 (∫Xi dXj, ∫Xj dXi)，编码 signed-area lead-lag（F2 Eq.21；AS7）

    # ---- m3 SIT 网络架构超参（F3/F4/F5/F6；B2 网格 Table4 Panel E / AS14 缩减 / AS7 MLP / AS6 τ / AS23 结构细化）----
    sit_d_model: int = 32                           # d_model 隐维（B2 网格{8,16,32,64}→AS14 缩减取中档 32；须被 sit_n_heads 整除）
    sit_d_ff: int = 32                              # d_ff FFN 隐维（B2 D_FFS{8,16,32,64}→AS14 缩减 32）
    sit_n_layers: int = 1                           # factorized 层数 E_LAYERS（B2{1,2}→AS14 缩减 1）
    sit_n_heads: int = 4                            # N_H 注意力头数（B2 N_HEADS{2,4,8}→AS14 缩减 4；时间/资产注意力共用）
    sit_hidden_c: int = 16                          # HIDDEN C：MLPβ/MLPq 隐维（B2 HIDDEN_C{8,16,32}→AS14 缩减 16；AS7 2层MLP+GELU）
    sit_d_beta: int = 4                             # d_β 偏置嵌入维（原文未明，AS7 取小值 4；β,qdyn∈R^{N_H×d_β}）
    sit_tau: float = 1.0                            # softmax 温度 τ（F6 集中度；前向默认中性 1.0，主表由 val 选优 AS6）
    sit_tau_grid: tuple = (0.8, 1.0, 1.2, 1.3, 1.4)  # τ 验证选优/敏感性网格（AS6，与 SA3 sweep 一致，峰值近 τ≈1.3）

    # ---- m4 CVaR 训练 / 回测 / 基线超参（F7/F8/B1/B3/B5/B7；本 milestone 追加，只增不改）----
    backtest_decision_step: int = 0                 # 月度调仓取 K 步权重的第 1 步 w^(1)（receding-horizon MPC，B3；AS24）
    cvar_detach_nu: bool = True                     # CVaR 逐场景 ν_i 取经验 α-分位并 detach（RU 包络定理，梯度只经尾部超额；F7/AS24）
    cov_estimate_window: int = 120                  # GMV/HRP 基线滚动协方差窗口（月，≤T 点时；须 > 资产数保样本协方差满秩，否则 GMV 求逆退化等权；pre-test 史约 156 月支持 120；B5/AS25）
    cvar_scenario_window: int = 60                  # 传统 CVaR / 两阶段 Mean-CVaR 的历史场景窗口 S（月，RU-LP 场景式不要求满秩；B5/B7/AS25）
    cvar_min_scenarios: int = 12                    # CVaR/协方差估计最少场景数，不足则退等权（B5/AS25）
    mean_cvar_target: str = "equal_weight"          # 两阶段 µtarget 规则：等权组合预测收益（EW 天然可行、防不可解；B7/AS26）
    dlinear_kernel: int = 25                         # DLinear 序列分解移动平均核宽（日频，Zeng 2023 惯例；B7/AS15/AS26）
    dlinear_lr: float = 1e-3                         # DLinear 阶段一 MSE 训练学习率（沿用 B1；AS26）
    dlinear_max_epoch: int = 60                      # DLinear 阶段一最大 epoch（线性模型收敛快；AS26）
    dlinear_patience: int = 8                        # DLinear 阶段一早停 patience（AS26）

    # ---- m5 消融/敏感性网格（SA1/SA3/SA4/B4；本 milestone 追加，只增不改；开关映射见 AS27）----
    #  SA1 消融为运行期开关（train.py:objective / model.py:SIT.set_ablation），非 config 字段；口径 AS27
    sa3_cost_grid_bps: tuple = (0.0, 5.0, 10.0)      # SA3/B4 单边成本档 c∈{0,5,10}bps（spec B4/SA3 p8；AS10 自生成）
    #  SA3 的 τ sweep 复用 sit_tau_grid（{0.8,1.0,1.2,1.3,1.4}，与主表选优一致，AS6/AS10）
    sa4_tau_grid: tuple = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0)  # SA4 温度 τ 多样化网格（spec Fig6 p8 τ 轴范围）

    def __post_init__(self) -> None:
        # 自洽校验：日历维度须与周期数×2 一致；(1-α)K 非退化
        n_cal = 2 * len(self.calendar_cycles)
        if n_cal != self.calendar_feature_dim:
            raise ValueError(
                f"calendar_feature_dim={self.calendar_feature_dim} 与周期编码维 {n_cal} 不一致（AS4）"
            )
        tail_pts = (1.0 - self.cvar_alpha) * self.decision_steps_k
        if tail_pts < 1.0:
            raise ValueError(
                f"(1-α)·K={tail_pts:.2f}<1，CVaR 退化为均值损失（违反 AS1/AS2 耦合）"
            )

    @property
    def price_load_start(self) -> str:
        """前复权行情加载起点：train 起点回退 price_buffer_days 日（供签名回看）。"""
        return (
            pd.Timestamp(self.train_start) - pd.Timedelta(days=self.price_buffer_days)
        ).strftime("%Y-%m-%d")

    @property
    def asset_signature_dim(self) -> int:
        """逐资产 M=2 截断签名维度 d_sig = [level0?] + p + p²（p=路径维；F1/AS21）。

        时间增广路径维 p=2（时间+累积收益）→ 1+2+4=7；未增广 p=1 → 1+1+1=3；
        关闭 level-0 各减 1。函数体内引用此派生量而非硬编码，防魔法数字。
        """
        p = 2 if self.signature_time_augment else 1
        base = 1 + p + p * p                          # level0(1) + level1(p) + level2(p²)
        return base if self.signature_include_level0 else base - 1


# 模块级默认实例：全案共享此单一配置源
DEFAULT_CONFIG = SITConfig()
