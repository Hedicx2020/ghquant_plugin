"""r001 · Signature-Informed Transformer (SIT) 策略门面（项目约定 strategy.py）。

本模块**不重复实现任何策略逻辑**，只把已模块化的 m1-m4 组件（data / signatures /
model / train / backtest / main）收拢为项目约定的统一门面类 ``SITStrategy``，供门禁
G-IM-1 与外部调用以「加载数据 → 训练 → 产权重面板 → 回测」的单一入口驱动。

真实复用链（无空壳，逐方法委托既有实现）：
- ``fit(...)``          → main.build_supervised_set 组监督集（F_ti 特征 + K 步实现收益标签）
                          + train.train_sit / train.train_multi_seed 端到端 CVaR 训练（F7/F8/B1）；
- ``weight_panel(...)`` → signatures.build_feature_tensors 组 F_ti（D4/F1/F2）
                          + backtest.sit_weight_panel（model.forward_from_features 前向 F3-F6
                          取 K 步第 1 步 w^(1) + CA-A01 死票屏蔽 / renorm）；
- ``backtest(...)``     → backtest.build_test_monthly + run_portfolio + clip_test_backtest
                          （B3，common 引擎，默认 60 期覆盖）+ performance_metrics（B6 四指标）；
- ``run(smoke=...)``    → 薄封装 main.run_pipeline（端到端，含 5 基线与绩效表）。

点时红线由被复用组件自身保证（m2 只用 [t−H, t] 窗口、T→T+1 由 common.portfolio_backtest
对齐、死票 / 停牌点时屏蔽 backtest.tradable_mask_at）；本门面不新增任何数据对齐逻辑，
故不引入新的未来函数风险。超参一律取自 ``SITConfig`` 或调用方显式覆盖，函数体内无魔法数字。
"""

from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from .backtest import (
    build_test_monthly,
    clip_test_backtest,
    performance_metrics,
    run_portfolio,
    sit_weight_panel,
    test_coverage_decision_dates,
)
from .config import DEFAULT_CONFIG, SITConfig
from .data import DataBundle, load_data_bundle
from .main import build_supervised_set, run_pipeline
from .model import SIT
from .signatures import build_feature_tensors
from .train import TrainResult, train_multi_seed, train_sit

Logger = Optional[Callable[[str], None]]


class SITStrategy:
    """SIT 资产配置策略统一门面（复用 m1-m4 组件，不重复实现回测 / 训练引擎）。

    典型用法::

        strat = SITStrategy()                 # 持默认 SITConfig
        strat.load_data(top_n=50)             # m1 数据底座
        strat.fit(max_epoch=5)                # m4 端到端 CVaR 训练
        panel = strat.weight_panel()          # test 段 SIT 月度权重面板（死票屏蔽）
        result = strat.backtest(panel)        # B3/B6 回测 + 四指标

    或一步到位便捷端到端::

        SITStrategy().run(smoke=True)         # 薄封装 main.run_pipeline
    """

    def __init__(self, config: SITConfig = DEFAULT_CONFIG) -> None:
        self.config = config
        self.bundle: Optional[DataBundle] = None
        self.train_result: Optional[TrainResult] = None
        self.seed_results: list[TrainResult] = []

    # ---------- 便捷只读属性 ----------
    @property
    def model(self) -> Optional[SIT]:
        """当前 best-val SIT 模型（未 fit 前为 None）。"""
        return None if self.train_result is None else self.train_result.model

    @property
    def n_assets(self) -> Optional[int]:
        """资产数 d（=universe 大小；未加载数据前为 None）。"""
        return None if self.bundle is None else len(self.bundle.universe_codes)

    # ---------- 数据（复用 data.load_data_bundle） ----------
    def load_data(
        self,
        top_n: Optional[int] = None,
        anchor_date: Optional[pd.Timestamp] = None,
    ) -> DataBundle:
        """装配并缓存 m1 数据底座（固定资产集点时选样，防未来函数）。"""
        self.bundle = load_data_bundle(self.config, top_n=top_n, anchor_date=anchor_date)
        return self.bundle

    def _ensure_bundle(
        self, bundle: Optional[DataBundle], top_n: Optional[int]
    ) -> DataBundle:
        """保证有可用数据底座：显式传入优先，其次缓存，末则按 top_n 加载。"""
        if bundle is not None:
            self.bundle = bundle
        if self.bundle is None:
            self.load_data(top_n=top_n)
        return self.bundle

    # ---------- 训练（薄封装 train.train_sit / train_multi_seed） ----------
    def fit(
        self,
        bundle: Optional[DataBundle] = None,
        *,
        seed: Optional[int] = None,
        tau: Optional[float] = None,
        max_epoch: Optional[int] = None,
        patience: Optional[int] = None,
        multi_seed: bool = False,
        objective: str = "cvar",
        ablation: Optional[str] = None,
        top_n: Optional[int] = None,
        log_fn: Logger = None,
    ) -> TrainResult:
        """端到端训练 SIT（F7 CVaR 目标 / F8 端到端范式 / B1 Adam+早停）。

        监督集经 ``main.build_supervised_set`` 组装（F_ti 特征 + K 步实现收益标签，仅保留
        同时满足 H 历史与 K 未来的决策日；split_end/next_split_start 必填、强制边界 purge，
        train→(train_end,val_start)、val→(val_end,test_start)，test 区间封存 CDX-C-01）；
        训练体薄封装 ``train.train_sit``（单种子）或
        ``train.train_multi_seed``（AS5 多种子，取 best-val 模型）。缺省 objective="cvar"/
        ablation=None 即主表口径；m5 消融由这两参数透传（train_multi_seed 不支持消融，
        故仅单种子路径接受 objective/ablation）。

        Returns:
            best-val ``TrainResult``（权重已回载），并缓存至 ``self.train_result``。
        """
        cfg = self.config
        b = self._ensure_bundle(bundle, top_n)
        # CDX-C-01：build_supervised_set 的 split_end/next_split_start 必填、强制边界 purge——
        # train 传 (train_end, val_start)、val 传 (val_end, test_start)，与 run_pipeline 同口径，
        # 使本公开门面入口与主管线一样封存 test 区间实现收益，泄漏路径从源头闭环。
        train_set, y_train, _ = build_supervised_set(
            b, b.splits["train"], cfg, cfg.train_end, cfg.val_start)
        val_set, y_val, _ = build_supervised_set(
            b, b.splits["val"], cfg, cfg.val_end, cfg.test_start)
        n_assets = len(b.universe_codes)

        if multi_seed:
            self.seed_results = train_multi_seed(
                train_set, y_train, val_set, y_val, n_assets, cfg,
                tau=tau, max_epoch=max_epoch, patience=patience, log_fn=log_fn,
            )
            self.train_result = min(self.seed_results, key=lambda r: r.best_val)
        else:
            sd = cfg.seeds[0] if seed is None else seed
            self.train_result = train_sit(
                train_set, y_train, val_set, y_val, n_assets, cfg,
                seed=sd, tau=tau, max_epoch=max_epoch, patience=patience,
                log_fn=log_fn, objective=objective, ablation=ablation,
            )
            self.seed_results = [self.train_result]
        return self.train_result

    # ---------- 权重面板（复用 signatures + model 前向 + backtest 死票屏蔽） ----------
    def weight_panel(
        self,
        decision_dates: Optional[pd.DatetimeIndex] = None,
        *,
        bundle: Optional[DataBundle] = None,
        model: Optional[SIT] = None,
        tau: Optional[float] = None,
    ) -> pd.DataFrame:
        """产 SIT 月度组合权重面板（默认 test 段调仓日）。

        链路：``signatures.build_feature_tensors`` 组 F_ti（D4：逐资产 M=2 签名 F1 + 成对
        交叉签名 F2 + 日历特征，点时仅用 [t−H, t] 窗口）→ ``backtest.sit_weight_panel``
        （``model.forward_from_features`` 前向 F3-F6 → 取 K 步第 1 步 w^(1) → CA-A01 死票
        屏蔽 + 活票 renormalize）。

        Args:
            decision_dates: 决策日；缺省取 test 60 期覆盖决策日（预热+test，
                ``backtest.test_coverage_decision_dates``，CDX-C-05 与主管线同口径）。
            bundle: 数据底座；缺省用 ``self.bundle``。
            model: SIT 模型；缺省用已 fit 的 ``self.model``。
            tau: softmax 温度覆盖（缺省 ``config.sit_tau``）。
        """
        b = bundle if bundle is not None else self.bundle
        if b is None:
            raise RuntimeError("weight_panel 需先 load_data / fit 装配数据底座")
        m = model if model is not None else self.model
        if m is None:
            raise RuntimeError("weight_panel 需已 fit 的模型（或显式传入 model=）")
        dates = (test_coverage_decision_dates(b, self.config)
                 if decision_dates is None else pd.DatetimeIndex(decision_dates))
        feat = build_feature_tensors(b, dates, self.config)
        return sit_weight_panel(m, feat, b, self.config, tau=tau)

    # 项目约定别名：predict_weights 与 weight_panel 等价（同一委托链）
    predict_weights = weight_panel

    # ---------- 回测（复用 backtest 引擎，B3/B6） ----------
    def backtest(
        self,
        weights_panel: Optional[pd.DataFrame] = None,
        *,
        bundle: Optional[DataBundle] = None,
        tau: Optional[float] = None,
    ) -> dict:
        """对权重面板做月度序贯回测 + B6 四指标（复用 common 引擎，0bps 主表；默认 60 期覆盖）。

        weights_panel 缺省时先由 ``weight_panel`` 产 SIT 面板（含预热决策日）；月度收益面板由
        ``backtest.build_test_monthly`` 组装（相邻调仓日区间日简单收益复利 + 终端锚，≤t 点时安全），
        默认路径经 ``clip_test_backtest`` 裁剪到 [test_start,test_end] 并硬断言 60 期覆盖（CDX-C-05，
        与 run_pipeline / ablation 统一口径；首≈2020-01-23、末≈2024-12-27）。显式传入自定义
        ``weights_panel`` 时按其覆盖回测、不强制 60 期断言（调用方自负覆盖）。
        """
        b = bundle if bundle is not None else self.bundle
        if b is None:
            raise RuntimeError("backtest 需先 load_data / fit 装配数据底座")
        panel = (
            self.weight_panel(bundle=b, tau=tau) if weights_panel is None else weights_panel
        )
        monthly = build_test_monthly(b, self.config)          # 终端锚（CDX-C-05）
        bt = run_portfolio(panel, monthly, self.config)
        if weights_panel is None:                             # 默认路径硬断言 60 期覆盖（CDX-C-05）
            bt = clip_test_backtest(bt, self.config)
        return {
            "weights_panel": panel,
            "monthly": monthly,
            "backtest": bt,
            "metrics": performance_metrics(bt, self.config),
        }

    # ---------- 端到端便捷入口（薄封装 main.run_pipeline） ----------
    def run(
        self,
        smoke: bool = False,
        *,
        top_n: Optional[int] = None,
        export: bool = False,
        log_fn: Callable[[str], None] = print,
    ) -> dict:
        """端到端跑一次完整复现（SIT + 5 基线 + 绩效表），薄封装 ``main.run_pipeline``。

        smoke=True 走缩减档（小模型 / 少 epoch / 单种子，CPU 可跑通）。注：run_pipeline 内部
        自装配 config（``make_smoke_config`` 或 ``DEFAULT_CONFIG``）与数据底座；如需以本门面
        的自定义 ``self.config`` 训练，请改用 ``load_data`` + ``fit`` + ``backtest`` 组件路径。

        Returns:
            ``run_pipeline`` 的结果字典（perf / panels / bts / monthly / bundle / best / config）。
        """
        return run_pipeline(smoke=smoke, top_n=top_n, export=export, log=log_fn)


def build_strategy(config: SITConfig = DEFAULT_CONFIG) -> SITStrategy:
    """构造策略门面（与 model.build_sit / data.load_data_bundle 命名风格一致）。"""
    return SITStrategy(config)
