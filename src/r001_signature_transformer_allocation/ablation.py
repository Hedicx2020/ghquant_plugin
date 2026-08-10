"""r001 · SIT 模块消融研究（milestone m5：SA1 / Table2 + m5 冒烟驱动）。

职责（严格对 spec SA1，p6/Table2，对应 coverage_matrix milestone=m5 的 SA1）：
逐一移除单个核心组件、其余超参不变，各在主 universe 复训后比 SIT 完整版的四指标
（Sharpe/Sortino/MDD/Wealth），示各组件移除⟹性能下降方向（原文各消融均显著退化，
最关键为 w/o CVaR 决策聚焦目标）：
  - w/o CVaR：CVaR 目标换风险中性最大化均值收益（损失层消融，train.portfolio_loss objective="mean"）；
  - w/o Asset Attn：禁用整个签名增强资产维自注意力 F5（结构消融，model.set_ablation）；
  - w/o Financial Bias：去签名偏置 γ·B、退回标准注意力（结构消融）；
  - w/o Gate γ：固定 γ=1（去可学习 gate、保留偏置 B，结构消融）。

复用 m4 基础设施：main.build_supervised_set/build_test_inputs（监督集/推断输入）、
train.train_sit（加 objective/ablation 可选参数，默认等价现行为）、backtest.sit_weight_panel/
run_portfolio/performance_metrics（月度回测四指标，0bps 主表）。不重复实现回测引擎。

消融仅改单组件、其余超参（d_model/H/K/α/lr/…）不变（spec SA1「其余超参不变」；验证点①）。
数值豁免（experimental，A股迁移）：结论为「各组件移除⟹方向性退化」而非逐格对齐原文 Table2。

冒烟（m5 极短档，防 stall）：top-20 universe + d_model=8/layers=1/heads=2，每变体仅 1 epoch，
SA2/SA3/SA4 各取极小样例，复用同一 SIT 完整模型（欠训练、数值不完美，如实标注；完整档留 verify）。
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Optional

import numpy as np
import pandas as pd

from . import sensitivity
from .backtest import (
    build_test_monthly,
    clip_test_backtest,
    performance_metrics,
    run_portfolio,
    sit_weight_panel,
    test_coverage_decision_dates,
)
from .config import DEFAULT_CONFIG, SITConfig
from .data import load_data_bundle
from .main import build_supervised_set, build_test_inputs
from .train import train_sit

# SA1 变体：(展示名, 结构消融 model.set_ablation 参数, 训练目标 objective)
#   "SIT (Ours)" 与 "w/o CVaR" 结构均为 full（ablation=None）；w/o CVaR 仅换损失目标。
SA1_VARIANTS: tuple[tuple[str, Optional[str], str], ...] = (
    ("SIT (Ours)",         None,                "cvar"),
    ("w/o CVaR",           None,                "mean"),   # 损失层消融：换风险中性均值目标
    ("w/o Asset Attn",     "no_asset_attn",     "cvar"),   # 结构：跳过 F5 签名资产注意力
    ("w/o Financial Bias", "no_financial_bias", "cvar"),   # 结构：去 γ·B 退标准注意力
    ("w/o Gate γ",         "no_gate",           "cvar"),   # 结构：固定 γ=1
)

_METRIC_KEYS = ("Sharpe", "Sortino", "MaxDrawdown", "FinalWealth")


# =====================================================================
# 单变体：训练 + 回测四指标
# =====================================================================

def variant_backtest_metrics(
    model, test_feat: dict, bundle, monthly: pd.DataFrame,
    config: SITConfig = DEFAULT_CONFIG, tau: Optional[float] = None,
) -> dict:
    """已训练模型 → 月度回测四指标（复用 m4：sit_weight_panel→run_portfolio→performance_metrics）。

    test_feat 须为 60 期覆盖输入（预热+test，prepare_m5_data 的 test_feat_cov）；回测经
    clip_test_backtest 裁剪并硬断言 n_periods==60、首末日正确（CDX-C-05，与主管线同口径）。
    """
    panel = sit_weight_panel(model, test_feat, bundle, config, tau=tau)
    # CDX-C-05：与 run_pipeline / strategy 统一 60 期覆盖——裁剪到 [test_start,test_end] 并硬断言
    # n_periods==60、首末日正确（ValueError，非 -O 可移除 assert）。
    bt = clip_test_backtest(run_portfolio(panel, monthly, config), config)  # 0bps 主表（config.cost_bps）
    return performance_metrics(bt, config)


def run_sa1(
    train_set: dict, y_train: np.ndarray, val_set: dict, y_val: np.ndarray,
    test_feat: dict, bundle, monthly: pd.DataFrame, n_assets: int,
    config: SITConfig = DEFAULT_CONFIG,
    *,
    seed: int = 0,
    max_epoch: Optional[int] = None,
    patience: Optional[int] = None,
    tau: Optional[float] = None,
    log=print,
) -> tuple[dict, object]:
    """SA1 五变体训练 + 四指标对比表。

    Returns:
        (table, full_model)：table[展示名]={Sharpe/Sortino/MaxDrawdown/FinalWealth}；
        full_model 为「SIT (Ours)」完整模型（供 SA2/SA3/SA4 复用，免重训）。
    """
    table: dict[str, dict] = {}
    full_model = None
    for label, ablation, objective in SA1_VARIANTS:
        t0 = time.perf_counter()
        res = train_sit(
            train_set, y_train, val_set, y_val, n_assets, config,
            seed=seed, tau=tau, max_epoch=max_epoch, patience=patience,
            objective=objective, ablation=ablation, log_fn=None,
        )
        metrics = variant_backtest_metrics(res.model, test_feat, bundle, monthly, config, tau=tau)
        table[label] = metrics
        if label == "SIT (Ours)":
            full_model = res.model
        log(f"[SA1] {label:<20} train_obj={objective:<4} best_val={res.best_val:.6f} "
            f"Sharpe={metrics['Sharpe']:+.4f} Sortino={metrics['Sortino']:+.4f} "
            f"MDD={metrics['MaxDrawdown']:.4f} Wealth={metrics['FinalWealth']:.4f} "
            f"[{time.perf_counter() - t0:.1f}s]")
    return table, full_model


def print_sa1_table(table: dict, log=print) -> None:
    """打印 SA1 四指标对比表 + w/o CVaR 方向性（vs SIT 完整版）。"""
    log("")
    log("----- SA1 模块消融四指标表（数值豁免，看方向性）-----")
    log(f"{'Model':<20}{'Sharpe':>10}{'Sortino':>10}{'MaxDD':>9}{'Wealth':>9}")
    for label, _, _ in SA1_VARIANTS:
        m = table[label]
        log(f"{label:<20}{m['Sharpe']:>10.4f}{m['Sortino']:>10.4f}"
            f"{m['MaxDrawdown']:>9.4f}{m['FinalWealth']:>9.4f}")
    base = table.get("SIT (Ours)")
    if base is not None:
        log("方向性（消融 Sharpe − SIT 完整 Sharpe，负=退化，spec 期望全部退化）：")
        for label, _, _ in SA1_VARIANTS:
            if label == "SIT (Ours)":
                continue
            d = table[label]["Sharpe"] - base["Sharpe"]
            flag = "退化↓" if d < 0 else "未退化↑(欠训练/噪声)"
            log(f"   {label:<20} ΔSharpe={d:+.4f}  {flag}")


# =====================================================================
# 数据准备 / 冒烟配置（m5 极短档）
# =====================================================================

def make_m5_smoke_config(base: SITConfig = DEFAULT_CONFIG) -> SITConfig:
    """m5 冒烟缩减配置（防 stall，<2min）：top-20 + d_model=8/layers=1/heads=2 + 1 epoch/变体。

    仅缩 universe/模型/epoch/种子；不改方法性参数 α/K/H（消融方向性依赖 CVaR 非退化）。
    d_model=8 须被 heads=2 整除（自洽）。
    """
    return replace(
        base,
        universe_primary_n=20,
        sit_d_model=8, sit_d_ff=8, sit_n_heads=2, sit_n_layers=1, sit_hidden_c=8,
        max_epoch=1, early_stop_patience=1,
        seeds=(0,),
    )


def prepare_m5_data(config: SITConfig, top_n: Optional[int] = None, log=print) -> dict:
    """装配 m5 所需数据：监督集(train/val) + test 推断输入 + 月度收益面板（复用 m1/m2/m4）。"""
    n = int(top_n if top_n is not None else config.universe_primary_n)
    t0 = time.perf_counter()
    bundle = load_data_bundle(config, top_n=n)
    log(f"[m5-data] {bundle.summary()} [{time.perf_counter() - t0:.1f}s]")
    t1 = time.perf_counter()
    # CDX-C-01：build_supervised_set 的 split_end/next_split_start 已必填、强制边界 purge——
    # 消融训练同样传 train→(train_end,val_start)、val→(val_end,test_start)，与主管线同口径，
    # 消融变体训练/早停亦封存 test 区间实现收益，杜绝该入口的标签泄漏。
    train_set, y_train, _ = build_supervised_set(
        bundle, bundle.splits["train"], config, config.train_end, config.val_start)
    val_set, y_val, _ = build_supervised_set(
        bundle, bundle.splits["val"], config, config.val_end, config.test_start)
    # CDX-C-05：回测路径（SA1/SA3）用 60 期覆盖决策日（预热+test）+ 终端锚月度面板，与主管线同口径；
    # 非回测分析（SA2/SA4）保留 test-only 决策日、不引入预热点，其相关/多样化分布口径不受影响。
    cov_dates = test_coverage_decision_dates(bundle, config)
    test_feat_cov, test_dates_cov, _ = build_test_inputs(bundle, cov_dates, config)      # 回测 60 期覆盖
    test_feat, test_dates, _ = build_test_inputs(bundle, bundle.splits["test"], config)  # SA2/SA4 test-only
    monthly = build_test_monthly(bundle, config)
    log(f"[m5-data] train 场景={y_train.shape[0]} val={y_val.shape[0]} "
        f"test 决策日 回测覆盖={len(test_dates_cov)} / SA2·SA4 test-only={len(test_dates)} "
        f"月度面板={monthly.shape} [{time.perf_counter() - t1:.1f}s]")
    return {
        "bundle": bundle, "train_set": train_set, "y_train": y_train,
        "val_set": val_set, "y_val": y_val,
        "test_feat_cov": test_feat_cov, "test_dates_cov": test_dates_cov,   # 回测 60 期覆盖（SA1/SA3）
        "test_feat": test_feat, "test_dates": test_dates,                   # SA2/SA4 test-only
        "monthly": monthly,
        "n_assets": len(bundle.universe_codes),
    }


# =====================================================================
# m5 冒烟驱动（SA1 五变体 + SA2/SA3/SA4 各一小样例；极短，防 stall）
# =====================================================================

def smoke_m5() -> None:
    """m5 全要素超缩减冒烟：真实 CSI300 top-20 数据、每变体 1 epoch，验证 SA1-4 跑通。"""
    t_start = time.perf_counter()
    cfg = make_m5_smoke_config()
    print("===== r001 SIT m5 消融/敏感性 · 冒烟(smoke) · "
          f"CSI300-{cfg.universe_primary_n} · d_model={cfg.sit_d_model}/layers={cfg.sit_n_layers}/"
          f"heads={cfg.sit_n_heads} · 每变体 {cfg.max_epoch}epoch =====")

    data = prepare_m5_data(cfg, log=print)

    # ---- SA1 五变体消融（核心；回测走 60 期覆盖 feat，CDX-C-05）----
    table, full_model = run_sa1(
        data["train_set"], data["y_train"], data["val_set"], data["y_val"],
        data["test_feat_cov"], data["bundle"], data["monthly"], data["n_assets"],
        cfg, seed=cfg.seeds[0], max_epoch=cfg.max_epoch, patience=cfg.early_stop_patience,
        log=print,
    )
    print_sa1_table(table, log=print)

    # ---- SA2 签名强度-注意力相关（复用 SIT 完整模型）----
    print("")
    sensitivity.run_sa2(full_model, data["test_feat"], cfg, log=print)

    # ---- SA3 τ×成本 Sharpe 网格（回测走 60 期覆盖 feat，CDX-C-05；τ 取两端子集提速、成本 config 全档）----
    print("")
    sensitivity.run_sa3(full_model, data["test_feat_cov"], data["bundle"], data["monthly"], cfg,
                        taus=(0.8, 1.3), costs_bps=cfg.sa3_cost_grid_bps, log=print)

    # ---- SA4 τ 多样化 HHI/熵（冒烟 τ 取 sa4_tau_grid 三点子集看单调趋势）----
    print("")
    sensitivity.run_sa4(full_model, data["test_feat"], cfg, taus=(0.5, 1.0, 2.0), log=print)

    print(f"\n===== m5 冒烟完成，总耗时 {time.perf_counter() - t_start:.1f}s =====")


if __name__ == "__main__":
    smoke_m5()
