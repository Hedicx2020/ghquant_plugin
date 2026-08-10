"""r001 · SIT 端到端复现主装配（milestone m4：数据→特征→训练→回测→基线→绩效表）。

串联：
  m1 data.load_data_bundle → m2 signatures.build_feature_tensors/realized_forward_returns
  → m4 train.train_sit（F7 CVaR/F8 端到端/B1）→ backtest.sit_weight_panel（B3 月度、CA-A01 死票屏蔽）
  → baselines（B5 EW/GMV/CVaR/HRP + B7 DLinear 两阶段）→ performance_metrics（B6 四指标）
  → R1-R4 主绩效表（CSI300-50 R4 锚，数值豁免趋同比较）。

运行：
  完整档  ``uv run python -m src.r001_signature_transformer_allocation.main --export``（verify 阶段跑，产 output/）
  冒烟档  ``uv run python -m src.r001_signature_transformer_allocation.main --smoke``（缩减模型/epoch，
          保留 top-50 以真实演练 CA-A01 死票屏蔽；不产 output/ 正式产物）

未来函数红线：训练/验证只用 splits[train]/splits[val] 决策日，test 封存不参与选优；信号 T 算、
T+1 执行由 common.portfolio_backtest 保证；死票/停牌点时屏蔽（backtest.tradable_mask_at）。
超参一律引用 config，缩减档偏移经 replace 显式登记（AS14/AS18 缩减 + AS5 单种子冒烟）。
"""

from __future__ import annotations

import argparse
import itertools
from dataclasses import replace
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .backtest import (
    baseline_weight_panel,
    build_test_monthly,
    clip_test_backtest,
    performance_metrics,
    run_portfolio,
    sit_weight_panel,
    test_coverage_decision_dates,
    tradable_mask_at,
)
from .baselines import train_dlinear
from .benchmarks import R4_ANCHOR_CSI300_50  # CDX-C-02：原文 R4 参考锚（reference-only，独立于实测）
from .config import DEFAULT_CONFIG, SITConfig
from .data import load_data_bundle
from .signatures import build_feature_tensors, realized_forward_returns
from .train import train_multi_seed, train_sit

BASELINE_NAMES = ("EW", "GMV", "CVaR", "HRP", "DLinear")

# CDX-C-02：原文 R4 基准锚（CSI300-50，Table7 Panel A）已抽离到独立参考模块 benchmarks.py
# （reference-only，非复现计算产物），本计算模块只产**实测**结果、绝不以锚值顶替；主绩效表 /
# backtest_summary.xlsx 的「研报值 vs 复现值 vs 偏差」对照列引用 R4_ANCHOR_CSI300_50，
# 数值豁免、仅作趋同参考，非达标判据（AS12/AS16）。


# =====================================================================
# 缩减档配置（冒烟）
# =====================================================================

def make_smoke_config(base: SITConfig = DEFAULT_CONFIG) -> SITConfig:
    """冒烟缩减配置：小模型/少 epoch/单种子（AS14 网格缩减 + AS18 降规 + AS5 单种子）。

    保留 universe_primary_n=50 以真实演练 CA-A01 死票屏蔽（train 起点 top-50 含退市死票），
    仅缩小 d_model/层/头与 epoch 保 CPU 可跑通；不改 α/K/H 等方法性参数。
    """
    return replace(
        base,
        sit_d_model=16, sit_d_ff=16, sit_n_heads=2, sit_n_layers=1, sit_hidden_c=8,
        max_epoch=5, early_stop_patience=4,
        dlinear_max_epoch=8, dlinear_patience=3,
        seeds=(0, 1),  # 冒烟保 2 种子以真实演练 AS5 多种子 mean±std 聚合（CDX-C-07）
    )  # 仅缩模型/epoch/种子；cov/CVaR 窗口沿用修正后默认（120/60，保 GMV 满秩）


# =====================================================================
# 监督集构造（特征 + K 步标签 + DLinear 日频回看窗口）
# =====================================================================

def build_supervised_set(bundle, decision_dates, config: SITConfig, split_end, next_split_start, log=None):
    """组装训练/验证监督集：F_ti 特征 + K 步实现收益标签 + 逐资产日频回看窗口（DLinear）。

    仅保留同时满足 H 历史（特征可算）与 K 未来（标签可得）的决策日。

    **split 边界 purge（CDX-C-01，源头硬闭环）**：``split_end`` 与 ``next_split_start`` 均为
    **必填参数**，函数入口先于任何特征构造校验——None/NaT 立即 raise ValueError（非 -O 可移除
    的 assert），已去除 split_end=None 非 purge 旁路。标签第 K 个未来锚点越过 ``split_end``
    的样本一律 purge（训练/验证尾部各剔约 K 个标签越界决策点），确保下一 split（尤其 test
    区间）的实现收益绝不进入本 split 的训练/早停/选优。双重边界断言：保留样本标签终点
    ≤ split_end **且严格 < next_split_start**（val split 即断言标签终点 < test_start，test
    区间对早停/网格/τ 选优完全封存）。全部调用入口（run_pipeline / SITStrategy.fit）强制 purge。
    """
    # CDX-C-01 源头硬闭环：split_end/next_split_start 为必填时点边界，先于任何特征构造校验——
    # None/NaT 立即 raise ValueError（非 -O 可移除的 assert），杜绝无边界旁路生成越界标签。
    if split_end is None or pd.isna(split_end):
        raise ValueError(
            "build_supervised_set 的 split_end 为必填时点边界，收到 None/NaT（CDX-C-01 源头闭环）"
        )
    if next_split_start is None or pd.isna(next_split_start):
        raise ValueError(
            "build_supervised_set 的 next_split_start 为必填时点边界，收到 None/NaT（CDX-C-01 源头闭环）"
        )
    split_end_ts = pd.Timestamp(split_end)
    next_start_ts = pd.Timestamp(next_split_start)
    feat = build_feature_tensors(bundle, decision_dates, config)
    used = pd.DatetimeIndex(feat["decision_dates"])
    H = config.lookback_h
    K = config.decision_steps_k
    dlr = bundle.daily_log_returns
    rb = pd.DatetimeIndex(bundle.rebalance_dates)
    labels, hist, keep, term_anchors = [], [], [], []
    n_short, n_purged = 0, 0
    for i, d in enumerate(used):
        r = realized_forward_returns(bundle, d, config, split_end=split_end_ts)  # (K,d) 或 None
        if r is None:
            later = rb[rb >= pd.Timestamp(d)]
            if len(later) < K + 1:
                n_short += 1                                     # 未来调仓不足 K（全局末端）
            else:
                n_purged += 1                                    # 标签越过 split 边界被 purge（CDX-C-01）
            continue
        pos = dlr.index.get_loc(d)
        win = dlr.iloc[pos - H + 1: pos + 1].to_numpy(dtype=float)  # (H,d) 点时窗口
        labels.append(r)
        hist.append(win.T)                                        # (d,H)
        keep.append(i)
        term_anchors.append(rb[rb >= pd.Timestamp(d)][K])         # 标签终点 t_{i+K}
    if not keep:
        raise RuntimeError("监督集为空（无同时满足 H 历史与 K 未来的决策日）")
    # 双重边界校验（CDX-C-01，ValueError 非 -O 可移除 assert）：保留样本标签终点 ≤ split_end
    # 且严格 < 下一 split 起点（val→标签终点 < test_start，test 区间对早停/网格/τ 选优完全封存）
    max_term = max(term_anchors)
    if max_term > split_end_ts:
        raise ValueError(
            f"标签边界泄漏：保留样本最大标签终点 {max_term.date()} > split_end {split_end_ts.date()}（CDX-C-01）"
        )
    if max_term >= next_start_ts:
        raise ValueError(
            f"标签跨界泄漏：保留样本最大标签终点 {max_term.date()} ≥ 下一split起点 {next_start_ts.date()}（CDX-C-01）"
        )
    if log is not None:
        log(f"[监督集purge] split_end={split_end_ts.date()} next_start={next_start_ts.date()} "
            f"输入决策日={len(used)} 保留={len(keep)} 边界purge={n_purged} "
            f"未来不足K={n_short} 标签终点max={max_term.date()}")
    keep_arr = np.array(keep, dtype=int)
    sub = {
        "asset_signatures": np.asarray(feat["asset_signatures"])[keep_arr],
        "cross_signatures": np.asarray(feat["cross_signatures"])[keep_arr],
        "calendar": np.asarray(feat["calendar"])[keep_arr],
        "decision_dates": used[keep_arr],
        "codes": feat["codes"],
    }
    return sub, np.stack(labels), np.stack(hist)


def hyperparameter_grid(config: SITConfig) -> list[SITConfig]:
    """B2 缩减网格搜索空间（Table4 Panel E → AS14 缩减 ≤8 组）。

    d_model∈{16,32} × d_ff∈{16,32} × heads∈{2,4}，layers=1、hidden_c=16 固定（AS14）。
    共 8 组，val CVaR 选优（原文 288 组不可行于 CPU）。
    """
    grid = []
    for d_model, d_ff, n_heads in itertools.product((16, 32), (16, 32), (2, 4)):
        grid.append(replace(config, sit_d_model=d_model, sit_d_ff=d_ff,
                            sit_n_heads=n_heads, sit_n_layers=1, sit_hidden_c=16))
    return grid


def select_hyperparams(train_set, y_train, val_set, y_val, n_assets, config: SITConfig, log) -> SITConfig:
    """B2 网格 val 选优：逐配置单种子训练、取 best val CVaR 的配置（test 封存不参与）。"""
    best_cfg, best_val = config, float("inf")
    for i, gc in enumerate(hyperparameter_grid(config)):
        res = train_sit(train_set, y_train, val_set, y_val, n_assets, gc, seed=gc.seeds[0], log_fn=None)
        log(f"[grid {i}] d_model={gc.sit_d_model} d_ff={gc.sit_d_ff} heads={gc.sit_n_heads} "
            f"val_cvar={res.best_val:.6f}")
        if res.best_val < best_val:
            best_val, best_cfg = res.best_val, gc
    log(f"[grid] 选优 d_model={best_cfg.sit_d_model} d_ff={best_cfg.sit_d_ff} "
        f"heads={best_cfg.sit_n_heads} best_val_cvar={best_val:.6f}")
    return best_cfg


def select_tau(train_set, y_train, val_set, y_val, n_assets, config: SITConfig,
               tau_grid, log) -> float:
    """AS6 温度 τ 验证集选优（CDX-C-06）：逐 τ 训练（seed 0）取 best val CVaR 最小的 τ。

    τ 是分配头 softmax(µ̂/τ) 的集中度温度、随前向进入训练与回测；此处把 τ 纳入验证搜索，
    选中值在**最终多种子训练**与**测试权重生成**中一致使用（替代此前固定 config.sit_tau=1.0）。
    test 封存：选优只用 train/val，不碰 test。
    """
    best_tau, best_val = config.sit_tau, float("inf")
    for tau in tau_grid:
        res = train_sit(train_set, y_train, val_set, y_val, n_assets, config,
                        seed=config.seeds[0], tau=float(tau), log_fn=None)
        log(f"[tau {float(tau):.2f}] val_cvar={res.best_val:.6f}")
        if res.best_val < best_val:
            best_val, best_tau = res.best_val, float(tau)
    log(f"[tau] 选中 τ={best_tau:.2f}（AS6 val 选优）best_val_cvar={best_val:.6f}")
    return best_tau


def _aggregate_metrics(metric_dicts: list[dict]) -> dict:
    """多种子四指标聚合 mean±std（AS5/CDX-C-07）；单元素（确定性基线）→ std=0。"""
    keys = ("Sharpe", "Sortino", "MaxDrawdown", "FinalWealth")
    out: dict = {"n_seeds": len(metric_dicts),
                 "n_periods": int(metric_dicts[0]["n_periods"]) if metric_dicts else 0}
    for k in keys:
        vals = np.array([float(m[k]) for m in metric_dicts], dtype=float)
        out[k] = float(np.nanmean(vals))
        out[f"{k}_std"] = float(np.nanstd(vals)) if len(vals) > 1 else 0.0
    return out


def build_test_inputs(bundle, decision_dates, config: SITConfig):
    """test 段推断输入：F_ti 特征（无需标签）+ 各决策日日频回看窗口（供 DLinear 预测）。"""
    feat = build_feature_tensors(bundle, decision_dates, config)
    used = pd.DatetimeIndex(feat["decision_dates"])
    H = config.lookback_h
    dlr = bundle.daily_log_returns
    hist_windows = {}
    for d in used:
        pos = dlr.index.get_loc(d)
        hist_windows[d] = dlr.iloc[pos - H + 1: pos + 1].to_numpy(dtype=float).T  # (d,H)
    return feat, used, hist_windows


# =====================================================================
# 主管线
# =====================================================================

def run_pipeline(smoke: bool = False, top_n: Optional[int] = None,
                 export: bool = False, log=print) -> dict:
    """端到端跑一次复现（冒烟/完整），返回绩效/面板/数据结构。"""
    cfg = make_smoke_config() if smoke else DEFAULT_CONFIG
    if top_n is not None:
        cfg = replace(cfg, universe_primary_n=int(top_n))
    mode = "冒烟(smoke)" if smoke else "完整(full)"
    log(f"===== r001 SIT m4 主装配 · {mode} · universe=CSI300-{cfg.universe_primary_n} =====")
    log(f"配置: d_model={cfg.sit_d_model} d_ff={cfg.sit_d_ff} layers={cfg.sit_n_layers} "
        f"heads={cfg.sit_n_heads} hidden_c={cfg.sit_hidden_c} | α={cfg.cvar_alpha} K={cfg.decision_steps_k} "
        f"(1-α)K={(1 - cfg.cvar_alpha) * cfg.decision_steps_k:.1f} | "
        f"epoch≤{cfg.max_epoch} patience={cfg.early_stop_patience} seeds={cfg.seeds}")

    # ---- m1 数据底座 ----
    bundle = load_data_bundle(cfg, top_n=cfg.universe_primary_n)
    log(f"[数据] {bundle.summary()}")

    # ---- 监督集（train/val）：split_end + next_split_start 必填，强制边界 purge（CDX-C-01）----
    # train 标签终点须 ≤ train_end 且 < val_start、val 标签终点须 ≤ val_end 且 < test_start，
    # 确保 test 区间实现收益绝不进入训练/早停/选优；build_supervised_set 打印 [监督集purge]
    # 并剔除标签越界样本、双重边界断言。
    train_set, y_train, hist_train = build_supervised_set(
        bundle, bundle.splits["train"], cfg, cfg.train_end, cfg.val_start, log=log)
    val_set, y_val, hist_val = build_supervised_set(
        bundle, bundle.splits["val"], cfg, cfg.val_end, cfg.test_start, log=log)
    n_assets = len(bundle.universe_codes)
    log(f"[监督集] train 场景={y_train.shape[0]} val 场景={y_val.shape[0]} | "
        f"asset_sig{train_set['asset_signatures'].shape} labels{y_train.shape}")

    # ---- m4 SIT 端到端 CVaR 训练（F7/F8/B1）+ B2 网格选优 + AS6 τ 验证选优（CDX-C-06）----
    # τ 选优后写回 cfg（sit_tau=best_tau），最终训练与测试权重生成一致使用该 τ（替代固定 1.0）。
    if smoke:
        best_tau = select_tau(train_set, y_train, val_set, y_val, n_assets, cfg,
                              cfg.sit_tau_grid[:3], log)  # 冒烟取 τ 网格前 3 档 {0.8,1.0,1.2}
        cfg = replace(cfg, sit_tau=best_tau)
    else:
        cfg = select_hyperparams(train_set, y_train, val_set, y_val, n_assets, cfg, log)  # B2 网格 val 选优
        best_tau = select_tau(train_set, y_train, val_set, y_val, n_assets, cfg,
                              cfg.sit_tau_grid, log)  # 完整档 AS6 全网格 {0.8,1.0,1.2,1.3,1.4}
        cfg = replace(cfg, sit_tau=best_tau)
    # AS5/CDX-C-07 多种子：冒烟 seeds=(0,1)、完整 cfg.seeds=(0,1,2)，每种子后续独立生成测试权重面板+
    # 回测+四指标再 mean±std 聚合（种子非验证择优维度；best 仅取 best-val 种子面板供死票证据/导出）。
    seed_results = train_multi_seed(train_set, y_train, val_set, y_val, n_assets, cfg,
                                    tau=cfg.sit_tau, log_fn=log)  # AS5 多种子，τ=选优值
    best = min(seed_results, key=lambda r: r.best_val)
    log(f"[SIT] n_seeds={len(seed_results)} best seed={best.seed} best_epoch={best.best_epoch} "
        f"best_val_cvar={best.best_val:.6f} | loss首={best.history[0][0]:.6f}→末={best.history[-1][0]:.6f}")

    # ---- B7 DLinear 两阶段第一阶段（MSE 预测器）：AS5/CDX-C-07 多种子独立训练 ----
    # 与 SIT 同口径——每种子独立训练预测器→独立测试权重面板→回测→四指标，末端 mean±std 聚合。
    dlin_models = {sd: train_dlinear(hist_train, y_train, hist_val, y_val, cfg, seed=sd, log_fn=log)
                   for sd in cfg.seeds}

    # ---- test 推断输入（含 pre-test 预热决策日）+ 月度结算面板（含终端锚）（CDX-C-05）----
    # test 前最后一个月末（约 2019-12-31）作纯推断预热决策日，其权重承接 2020-01 首期实现收益
    # （否则 test 首月缩水，首实现日推迟到 2020-02）；build_test_monthly 传 terminal_date=test_end
    # 追加 (末月末, test_end] 终端锚，使 2024-11 末信号承接至 2024-12-27。两 helper 与 strategy/
    # ablation 共用（backtest.test_coverage_decision_dates / build_test_monthly），统一 60 期。
    decision_dates = test_coverage_decision_dates(bundle, cfg)   # 预热 + test 决策日（60 期覆盖，CDX-C-05）
    test_feat, test_dates, hist_windows = build_test_inputs(bundle, decision_dates, cfg)
    monthly = build_test_monthly(bundle, cfg)                    # 终端锚 terminal_date=test_end（CDX-C-05）
    warm_date = pd.DatetimeIndex(test_dates)[0].date() if len(test_dates) else "无"
    log(f"[test] 决策日={len(test_dates)}（含预热 {warm_date}）"
        f" 月度收益面板={monthly.shape} 终端锚={pd.Timestamp(cfg.test_end).date()}")

    # ---- 权重面板 + 回测 + B6 四指标（SIT 多种子 mean±std / 基线确定性单点；均死票屏蔽 + test 裁剪）----
    panels: dict[str, pd.DataFrame] = {}
    bts: dict[str, pd.DataFrame] = {}
    perf: dict[str, dict] = {}

    # SIT（CDX-C-07/C-05/C-06）：每个种子用选优 τ 独立生成测试权重面板 → 回测经 clip_test_backtest
    # 裁剪到 [test_start,test_end] 并硬断言 60 期/首末日 → 四指标；末端 _aggregate_metrics 聚合 mean±std。
    sit_seed_metrics: list[dict] = []
    for res in seed_results:
        panel_s = sit_weight_panel(res.model, test_feat, bundle, cfg, tau=cfg.sit_tau)
        bt_s = clip_test_backtest(run_portfolio(panel_s, monthly, cfg), cfg)
        sit_seed_metrics.append(performance_metrics(bt_s, cfg))
        if res.seed == best.seed:                        # best-val 种子面板/回测供死票证据与导出
            panels["SIT"], bts["SIT"] = panel_s, bt_s
    perf["SIT"] = _aggregate_metrics(sit_seed_metrics)
    s = perf["SIT"]
    log(f"[SIT聚合] n_seeds={s['n_seeds']} Sharpe={s['Sharpe']:.4f}±{s['Sharpe_std']:.4f} "
        f"Sortino={s['Sortino']:.4f}±{s['Sortino_std']:.4f} MaxDD={s['MaxDrawdown']:.4f}±{s['MaxDrawdown_std']:.4f} "
        f"Wealth={s['FinalWealth']:.4f}±{s['FinalWealth_std']:.4f}")
    # CDX-C-05 期数：test 2020-01~2024-12 共 5 年 × 12 月 = 60 期；每面板已在 clip_test_backtest
    # 以 ValueError（非 -O 可移除 assert）硬断言 n_periods==60 且首≈2020-01-23 / 末≈2024-12-27，
    # 故此处仅记录（覆盖异常已在裁剪时硬失败）。
    target_periods = cfg.periods_per_year * 5
    n_sit = int(s["n_periods"])
    log(f"[test期数] SIT n_periods={n_sit}（目标={target_periods}=12×5，覆盖 2020-01~2024-12；"
        f"首实现日={bts['SIT'].index.min().date() if not bts['SIT'].empty else '空'} "
        f"末实现日={bts['SIT'].index.max().date() if not bts['SIT'].empty else '空'}）")

    # 传统基线 EW/GMV/CVaR/HRP：确定性单点（_aggregate_metrics 单元素→std=0），经 clip_test_backtest
    # 裁剪+60 期/首末断言；min-CVaR LP 退化经 log_fn=log 写入运行日志（CDX-C-04，非静默 warn）。
    for name in ("EW", "GMV", "CVaR", "HRP"):
        panel = baseline_weight_panel(name, bundle, test_dates, monthly, cfg, log_fn=log)
        bt = clip_test_backtest(run_portfolio(panel, monthly, cfg), cfg)
        panels[name], bts[name] = panel, bt
        perf[name] = _aggregate_metrics([performance_metrics(bt, cfg)])

    # DLinear（CDX-C-07）：多种子独立预测→权重→回测→四指标 mean±std（与 SIT 同口径）；导出/死票
    # 证据取 seeds[0] 面板。第二阶段 min-CVaR 退化同样 log_fn=log 记录日期/上下文（CDX-C-04）。
    dlin_seed_metrics: list[dict] = []
    for sd in cfg.seeds:
        panel_d = baseline_weight_panel(
            "DLinear", bundle, test_dates, monthly, cfg,
            dlinear_model=dlin_models[sd], hist_windows=hist_windows, log_fn=log)
        bt_d = clip_test_backtest(run_portfolio(panel_d, monthly, cfg), cfg)
        dlin_seed_metrics.append(performance_metrics(bt_d, cfg))
        if sd == cfg.seeds[0]:
            panels["DLinear"], bts["DLinear"] = panel_d, bt_d
    perf["DLinear"] = _aggregate_metrics(dlin_seed_metrics)
    dl = perf["DLinear"]
    log(f"[DLinear聚合] n_seeds={dl['n_seeds']} Sharpe={dl['Sharpe']:.4f}±{dl['Sharpe_std']:.4f} "
        f"Sortino={dl['Sortino']:.4f}±{dl['Sortino_std']:.4f} MaxDD={dl['MaxDrawdown']:.4f}±{dl['MaxDrawdown_std']:.4f} "
        f"Wealth={dl['FinalWealth']:.4f}±{dl['FinalWealth_std']:.4f}")

    _print_performance_table(perf, cfg, log)
    _print_deadstock_evidence(bundle, panels, test_dates, log)

    if export and not smoke:
        out_dir = Path(__file__).resolve().parents[2] / "output" / "r001_signature_transformer_allocation" / "results"
        export_results(perf, bts, panels["SIT"], bundle, cfg, out_dir, log)

    return {"perf": perf, "panels": panels, "bts": bts, "monthly": monthly,
            "bundle": bundle, "best": best, "config": cfg}


# =====================================================================
# 打印：绩效表 / 死票屏蔽证据
# =====================================================================

def _print_performance_table(perf: dict, cfg: SITConfig, log) -> None:
    """打印 SIT vs 基线四指标绩效表（+ R4 锚趋同列，仅 universe=50 有锚）。"""
    log("")
    log(f"----- 主绩效表（CSI300-{cfg.universe_primary_n}，test，0bps，月度）-----")
    header = f"{'Model':<9}{'Sharpe':>10}{'Sortino':>10}{'MaxDD':>9}{'Wealth':>9}{'期数':>6}{'种子':>5}"
    has_anchor = cfg.universe_primary_n == 50
    if has_anchor:
        header += "   | R4锚 Sharpe/MDD/Wealth"
    log(header)
    order = ["SIT"] + list(BASELINE_NAMES)
    for name in order:
        m = perf[name]
        line = (f"{name:<9}{m['Sharpe']:>10.4f}{m['Sortino']:>10.4f}"
                f"{m['MaxDrawdown']:>9.4f}{m['FinalWealth']:>9.4f}{m['n_periods']:>6d}"
                f"{int(m.get('n_seeds', 1)):>5d}")
        if has_anchor and name in R4_ANCHOR_CSI300_50:
            a = R4_ANCHOR_CSI300_50[name]
            line += f"   | {a['Sharpe']:.4f}/{a['MaxDrawdown']:.4f}/{a['FinalWealth']:.4f}"
        log(line)
    # 多种子 mean±std 明细（AS5/CDX-C-07；SIT 与 DLinear 均多种子聚合，确定性基线 std=0 略）
    for mname in ("SIT", "DLinear"):
        m = perf[mname]
        if int(m.get("n_seeds", 1)) > 1:
            log(f"{mname} mean±std(n_seeds={m['n_seeds']}): "
                f"Sharpe={m['Sharpe']:.4f}±{m['Sharpe_std']:.4f} "
                f"Sortino={m['Sortino']:.4f}±{m['Sortino_std']:.4f} "
                f"MaxDD={m['MaxDrawdown']:.4f}±{m['MaxDrawdown_std']:.4f} "
                f"Wealth={m['FinalWealth']:.4f}±{m['FinalWealth_std']:.4f}")
    log("注：实验模式数值豁免——R4 锚为原文 CSI300-50 研报值，仅作趋同参考，非达标判据（AS12/AS16）。")


def _print_deadstock_evidence(bundle, panels: dict, test_dates, log) -> None:
    """打印 CA-A01 死票屏蔽证据：死票清单 + 各面板死票权重≈0 + 活票 renorm 行和≈1。"""
    meta = bundle.universe_meta
    codes = list(bundle.universe_codes)
    cov = meta["test_coverage"]
    hard_dead = [c for c in codes if float(cov.loc[c]) <= 1e-9]           # test 期 0 覆盖真死票（退市）
    partial = [c for c in codes if not bool(meta.loc[c, "full_test"]) and float(cov.loc[c]) > 1e-9]
    log("")
    log("----- CA-A01 死票屏蔽证据 -----")
    log(f"universe={len(codes)} 只；真死票(test_coverage=0，退市)={len(hard_dead)} 只；"
        f"部分覆盖(0<cov<0.9)={len(partial)} 只：")
    for c in hard_dead:
        log(f"   [真死] {c} cov={cov.loc[c]:.3f} first={meta.loc[c,'first_date'].date()} last={meta.loc[c,'last_date'].date()}")
    for c in partial:
        log(f"   [部分] {c} cov={cov.loc[c]:.3f} last={meta.loc[c,'last_date'].date()}（可交易期合法持有）")
    sit_panel = panels["SIT"]
    if hard_dead:
        hard_w = float(np.nanmax(np.abs(sit_panel[hard_dead].to_numpy())))
        log(f"SIT 面板真死票权重 max={hard_w:.2e}（须恒=0，已屏蔽）")
    if partial:
        part_w = float(np.nanmax(np.abs(sit_panel[partial].to_numpy())))
        log(f"SIT 面板部分覆盖票权重 max={part_w:.2e}（可交易日合法>0，退市/停牌日置0）")
    row_sums = sit_panel.sum(axis=1)
    log(f"SIT 面板行和（活票 renorm 后应≈1）: min={float(row_sums.min()):.6f} "
        f"max={float(row_sums.max()):.6f} mean={float(row_sums.mean()):.6f}")
    d0 = pd.DatetimeIndex(test_dates)[0]
    m0 = tradable_mask_at(bundle, d0)
    log(f"决策日 {pd.Timestamp(d0).date()} 活票={int(m0.sum())}/{len(codes)}（不可交易={len(codes)-int(m0.sum())}）")


# =====================================================================
# 完整档产物导出（Excel + PNG，300 DPI；verify 阶段触发，冒烟不产）
# =====================================================================

def export_results(perf, bts, sit_panel, bundle, cfg, out_dir: Path, log) -> None:
    """导出 backtest_summary.xlsx + 必需 PNG（完整档；配色/DPI 按项目规范）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Arial Unicode MS", "PingFang HK", "Heiti TC", "STHeiti", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False
    out_dir.mkdir(parents=True, exist_ok=True)
    order = ["SIT"] + list(BASELINE_NAMES)
    has_anchor = cfg.universe_primary_n == 50

    # ---- backtest_summary.xlsx ----
    rows = []
    for name in order:
        m = perf[name]
        row = {"Model": name, "Sharpe": m["Sharpe"], "Sortino": m["Sortino"],
               "MaxDrawdown": m["MaxDrawdown"], "FinalWealth": m["FinalWealth"], "n_periods": m["n_periods"]}
        if has_anchor and name in R4_ANCHOR_CSI300_50:
            a = R4_ANCHOR_CSI300_50[name]
            row.update({"R4_Sharpe": a["Sharpe"], "R4_MaxDrawdown": a["MaxDrawdown"],
                        "R4_FinalWealth": a["FinalWealth"], "Sharpe_偏差": m["Sharpe"] - a["Sharpe"]})
        rows.append(row)
    summary_df = pd.DataFrame(rows)
    nav_df = pd.DataFrame({name: bts[name]["nav"] for name in order if not bts[name].empty})

    xlsx = out_dir / "backtest_summary.xlsx"
    from openpyxl.styles import Font
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="主绩效表", index=False)
        nav_df.to_excel(writer, sheet_name="净值序列")
        for sheet in writer.sheets.values():
            sheet.freeze_panes = "A2"
            for col in sheet.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                sheet.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 40)
            for c in sheet[1]:
                c.font = Font(bold=True)
    log(f"[导出] {xlsx}")

    blue, red = "#1f77b4", "#d62728"
    # portfolio_nav.png
    fig, ax = plt.subplots(figsize=(12, 6))
    for name in order:
        if bts[name].empty:
            continue
        ax.plot(bts[name].index, bts[name]["nav"], label=name,
                linewidth=2.0 if name == "SIT" else 1.2, color=red if name == "SIT" else None)
    ax.set_title(f"组合净值 SIT vs 基线（CSI300-{cfg.universe_primary_n}, test, 0bps）", fontsize=14)
    ax.set_xlabel("日期", fontsize=12); ax.set_ylabel("净值（起点1.0）", fontsize=12)
    ax.legend(fontsize=10); ax.grid(True, alpha=0.3)
    fig.tight_layout(); fig.savefig(out_dir / "portfolio_nav.png", dpi=300); plt.close(fig)

    # weight_evolution.png（SIT 权重堆叠）
    fig, ax = plt.subplots(figsize=(12, 6))
    wp = sit_panel.fillna(0.0)
    ax.stackplot(wp.index, wp.T.to_numpy())
    ax.set_title(f"SIT 组合权重演化（CSI300-{cfg.universe_primary_n}）", fontsize=14)
    ax.set_xlabel("日期", fontsize=12); ax.set_ylabel("权重", fontsize=12)
    ax.set_ylim(0, 1); ax.grid(True, alpha=0.3)
    fig.tight_layout(); fig.savefig(out_dir / "weight_evolution.png", dpi=300); plt.close(fig)

    # drawdown.png
    fig, ax = plt.subplots(figsize=(12, 6))
    for name in ("SIT", "EW"):
        if bts[name].empty:
            continue
        nav = bts[name]["nav"]; dd = (nav - nav.cummax()) / nav.cummax()
        ax.plot(nav.index, dd, label=name, color=red if name == "SIT" else blue)
    ax.set_title(f"组合回撤（CSI300-{cfg.universe_primary_n}）", fontsize=14)
    ax.set_xlabel("日期", fontsize=12); ax.set_ylabel("回撤", fontsize=12)
    ax.legend(fontsize=10); ax.grid(True, alpha=0.3)
    fig.tight_layout(); fig.savefig(out_dir / "drawdown.png", dpi=300); plt.close(fig)

    # asset_contribution.png（SIT 各资产累计收益贡献 top15）
    fig, ax = plt.subplots(figsize=(10, 6))
    contrib_cols = [c for c in bts["SIT"].columns if c.startswith("contrib_")]
    if contrib_cols:
        contrib = bts["SIT"][contrib_cols].sum().sort_values(ascending=False).head(15)
        ax.bar([c.replace("contrib_", "") for c in contrib.index], contrib.to_numpy(), color=blue)
        ax.set_title("SIT 各资产累计收益贡献（top15）", fontsize=14)
        ax.set_xlabel("资产", fontsize=12); ax.set_ylabel("累计贡献", fontsize=12)
        plt.xticks(rotation=45, ha="right")
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout(); fig.savefig(out_dir / "asset_contribution.png", dpi=300); plt.close(fig)

    # rolling_volatility.png（SIT 滚动年化波动）
    fig, ax = plt.subplots(figsize=(12, 6))
    if not bts["SIT"].empty:
        roll = bts["SIT"]["port_return"].rolling(6).std() * np.sqrt(cfg.periods_per_year)
        ax.plot(roll.index, roll, color=red, label="SIT 滚动年化波动(6期)")
    ax.set_title(f"SIT 滚动波动（CSI300-{cfg.universe_primary_n}）", fontsize=14)
    ax.set_xlabel("日期", fontsize=12); ax.set_ylabel("年化波动", fontsize=12)
    ax.legend(fontsize=10); ax.grid(True, alpha=0.3)
    fig.tight_layout(); fig.savefig(out_dir / "rolling_volatility.png", dpi=300); plt.close(fig)
    log(f"[导出] 5 张 PNG → {out_dir}")


# =====================================================================
# CLI
# =====================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="r001 SIT m4 端到端复现主装配")
    parser.add_argument("--smoke", action="store_true", help="冒烟缩减档（小模型/少 epoch/单种子）")
    parser.add_argument("--top-n", type=int, default=None, help="覆盖 universe 资产数（默认 config 50）")
    parser.add_argument("--export", action="store_true", help="导出 Excel/PNG（完整档 verify 用；冒烟忽略）")
    args = parser.parse_args()
    run_pipeline(smoke=args.smoke, top_n=args.top_n, export=args.export)


if __name__ == "__main__":
    main()
