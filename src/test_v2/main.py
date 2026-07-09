"""运行入口（test_v2）。

m1 阶段：打通「数据加载/对齐 -> 公共择时回测引擎」全链路并做冒烟自检。
m2 阶段：长短端股债跷跷板国债期货择时（F1）+ 日度信号（F2），复现 R1（表1 长短端/
长端/短端 × 多空/仅做多 + T 基准），并复现 R2/R3/R4 日度效应统计（15 档阈值×3 组的
胜率/赔率/平均涨跌幅），产出中间产物到 output/test_v2/results/ 供 verifier 逐格比对。

注意：本文件只做冒烟运行与量级自检打印，不产生「通过/验证结论」——完整回测比对与
通过判定归 verifier 与 check_gates。m3+ 策略信号尚未接入，占位跳过。

用法:
    python3 -m src.test_v2.main
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from common.timing_backtest import signal_backtest, timing_metrics  # noqa: E402
from src.test_v2.config import CONFIG, Config  # noqa: E402
from src.test_v2 import data_prep  # noqa: E402
from src.test_v2 import strategy  # noqa: E402

# R1 表指标行（顺序与命名对齐 spec R1 表；数值以 decimal 存盘，格式化交给 verifier）。
R1_METRIC_ROWS = [
    "年化收益", "最大回撤", "年化波动率", "卡玛比率", "夏普比率",
    "胜率", "看多胜率", "看空胜率", "盈亏比",
]
# 百分比口径的指标行（打印/存盘时区别于比率行）。
_PCT_ROWS = {"年化收益", "最大回撤", "年化波动率", "胜率", "看多胜率", "看空胜率"}


# ---------------------------------------------------------------------------
# T 基准（m1 冒烟自检复用）
# ---------------------------------------------------------------------------

def run_benchmark(panel: pd.DataFrame, config: Config = CONFIG) -> dict:
    """以 T 基准（恒定持有国债期货主力多头）跑通回测引擎，返回绩效指标。"""
    signal = pd.Series(1.0, index=panel.index)
    bt = signal_backtest(
        signal=signal,
        asset_returns=panel["future_close_return"],
        cost_bps=config.cost_bps,
        lag=config.signal_lag,
    )
    return timing_metrics(
        bt["nav"], bt["position"], bt["benchmark_nav"],
        periods_per_year=config.periods_per_year,
    )


# ---------------------------------------------------------------------------
# R1 表：F1 三策略（长短端/长端/短端）× (多空/仅做多) + T 基准
# ---------------------------------------------------------------------------

def _strategy_column(signal: pd.Series, asset_ret: pd.Series, config: Config) -> dict:
    """单策略单口径 → R1 指标列（多空或仅做多信号已在外部映射）。"""
    bt = signal_backtest(signal, asset_ret, cost_bps=config.cost_bps, lag=config.signal_lag)
    m = timing_metrics(bt["nav"], bt["position"], bt["benchmark_nav"],
                       periods_per_year=config.periods_per_year)
    wr = strategy.directional_win_rates(bt["position"], bt["strategy_ret"])
    return {
        "年化收益": m["annual_return"],
        "最大回撤": m["max_drawdown"],
        "年化波动率": m["annual_volatility"],
        "卡玛比率": m["calmar"],
        "夏普比率": m["sharpe"],
        "胜率": wr["win_rate"],
        "看多胜率": wr["long_win_rate"],
        "看空胜率": wr["short_win_rate"],
        "盈亏比": m["profit_loss_ratio"],
    }


def _benchmark_column(asset_ret: pd.Series, config: Config) -> dict:
    """T 基准列（持有国债期货多头）；胜率类置 NaN（spec R1 T 列以 -- 表示）。"""
    bt = signal_backtest(pd.Series(1.0, index=asset_ret.index), asset_ret,
                         cost_bps=config.cost_bps, lag=config.signal_lag)
    m = timing_metrics(bt["nav"], bt["position"], bt["benchmark_nav"],
                       periods_per_year=config.periods_per_year)
    return {
        "年化收益": m["annual_return"],
        "最大回撤": m["max_drawdown"],
        "年化波动率": m["annual_volatility"],
        "卡玛比率": m["calmar"],
        "夏普比率": m["sharpe"],
        "胜率": np.nan,
        "看多胜率": np.nan,
        "看空胜率": np.nan,
        "盈亏比": m["profit_loss_ratio"],
    }


def build_r1_table(panel: pd.DataFrame, seesaw: pd.DataFrame, config: Config = CONFIG) -> pd.DataFrame:
    """R1 表：长短端/长端/短端策略（多空+仅做多，AS2）+ T 基准，行=指标。

    信号来自 F1（seesaw，基日以来全历史 index），reindex 到主区间面板交易日。
    """
    asset_ret = panel["future_close_return"]
    strategies = {"长短端": "signal_ls", "长端": "signal_long", "短端": "signal_short"}

    cols: dict[str, dict] = {}
    for name, key in strategies.items():
        sig = seesaw[key].reindex(panel.index).fillna(0).astype(int)
        cols[f"{name}_多空"] = _strategy_column(sig, asset_ret, config)
        cols[f"{name}_仅做多"] = _strategy_column(strategy.to_long_only(sig), asset_ret, config)
    cols["T"] = _benchmark_column(asset_ret, config)

    return pd.DataFrame(cols).reindex(R1_METRIC_ROWS)


# ---------------------------------------------------------------------------
# R2/R3/R4 日度效应统计 + F1/F2 信号序列
# ---------------------------------------------------------------------------

def build_daily_effect_table(panel: pd.DataFrame, config: Config = CONFIG) -> pd.DataFrame:
    """R2/R3/R4：沪深300 T 日单日涨跌 vs 国债期货 T+1 涨跌 的 15 档×3 组效应统计。"""
    r = panel["hs300_return"]
    f_next = panel["future_close_return"].shift(-1)  # 下一交易日国债期货涨跌幅
    return strategy.daily_seesaw_effect_stats(r, f_next, config.daily_effect_thresholds)


def build_m2_signals(panel: pd.DataFrame, seesaw: pd.DataFrame, config: Config = CONFIG) -> pd.DataFrame:
    """主区间 F1/F2 信号序列（供审计/后续里程碑复用/verifier 画图）。"""
    idx = panel.index
    return pd.DataFrame(
        {
            "signal_long": seesaw["signal_long"].reindex(idx).fillna(0).astype(int),
            "signal_short": seesaw["signal_short"].reindex(idx).fillna(0).astype(int),
            "signal_ls": seesaw["signal_ls"].reindex(idx).fillna(0).astype(int),
            "signal_daily_upper": strategy.build_daily_signal(
                panel["hs300_return"], config.daily_upper_threshold),
            "signal_daily_lower": strategy.build_daily_signal(
                panel["hs300_return"], config.daily_lower_threshold),
            "chg_long": seesaw["chg_long"].reindex(idx),
            "chg_short": seesaw["chg_short"].reindex(idx),
            "hs300_return": panel["hs300_return"],
            "future_close_return": panel["future_close_return"],
        },
        index=idx,
    )


def _format_r1(r1: pd.DataFrame) -> pd.DataFrame:
    """将 R1 decimal 表格式化为百分比/比率字符串（打印/审阅用）。"""
    fmt = r1.astype(object).copy()
    for row in r1.index:
        for col in r1.columns:
            v = r1.loc[row, col]
            if pd.isna(v):
                fmt.loc[row, col] = "--"
            elif row in _PCT_ROWS:
                fmt.loc[row, col] = f"{v:.2%}"
            else:
                fmt.loc[row, col] = f"{v:.2f}"
    return fmt


# ---------------------------------------------------------------------------
# 流程
# ---------------------------------------------------------------------------

def run_m1_smoke(panel: pd.DataFrame, coverage: pd.DataFrame, config: Config = CONFIG) -> None:
    """m1 冒烟：数据对齐概览 + D3 覆盖核实 + T 基准量级自检。"""
    print("=" * 60)
    print("[test_v2 · m1 冒烟] 数据准备与公共择时回测框架")
    print("=" * 60)
    print(f"主区间: {config.main_start} ~ {config.main_end}")
    print(f"对齐面板天数: {len(panel)}")
    print(f"国债期货收盘/结算缺失: "
          f"{int(panel['future_close'].isna().sum())}/{int(panel['future_settle'].isna().sum())}")
    print(f"沪深300 收盘缺失: {int(panel['hs300_close'].isna().sum())}")
    print(f"周四天数(F5预留): {int(panel['is_thursday'].sum())}")

    print("\n[D3 中债净价现券指数覆盖核实]")
    print(coverage.to_string(index=False))
    n_avail = int(coverage["available"].sum())
    print(f"覆盖: {n_avail}/{len(coverage)} 有本地行情"
          + ("" if n_avail else "  -> 现券行情本地缺失，见 AS5（影响 m3 的 R5/R6）"))

    print("\n[T 基准量级自检（非通过判定，仅供 verifier 参考）]")
    m = run_benchmark(panel, config)
    print(f"  年化收益 annual_return : {m['annual_return']:.4%}  (R1-T 基准 2.30%)")
    print(f"  最大回撤 max_drawdown  : {m['max_drawdown']:.4%}  (R1-T 7.46%)")
    print(f"  夏普     sharpe        : {m['sharpe']:.4f}  (R1-T 0.59)")
    print(f"  盈亏比   profit_loss   : {m['profit_loss_ratio']:.4f}  (R1-T 1.11)")


def run_m2(panel: pd.DataFrame, hs300_close_full: pd.Series,
           config: Config = CONFIG) -> tuple[pd.DataFrame, pd.DataFrame]:
    """m2 流程：F1 长短端跷跷板 R1 复现 + R2/R3/R4 日度效应统计 + 中间产物落盘。

    Args:
        panel: 主区间对齐面板（build_main_panel）。
        hs300_close_full: 沪深300收盘价 **全历史** 序列（load_hs300()["close"]），CA-A01。
    """
    results_dir = config.output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # F1：基日以来全历史扩窗三分位（消费全历史 close，CA-A01），再 reindex 主区间。
    seesaw = strategy.build_interval_seesaw_signal(hs300_close_full, config)

    r1 = build_r1_table(panel, seesaw, config)
    effect = build_daily_effect_table(panel, config)
    signals = build_m2_signals(panel, seesaw, config)

    r1_path = results_dir / "strategy_perf_r1.csv"
    effect_path = results_dir / "daily_effect_stats.csv"
    signals_path = results_dir / "signals_m2.csv"
    r1.to_csv(r1_path, encoding="utf-8-sig")
    effect.to_csv(effect_path, index=False, encoding="utf-8-sig")
    signals.to_csv(signals_path, encoding="utf-8-sig")

    print("\n" + "=" * 60)
    print("[test_v2 · m2 冒烟] 长短端股债跷跷板择时 R1 + 日度效应 R2/R3/R4")
    print("=" * 60)
    print(f"F1 信号覆盖(基日以来)天数: {len(seesaw)}；主区间信号天数: {len(signals)}")
    up = int((signals["signal_daily_upper"] != 0).sum())
    lo = int((signals["signal_daily_lower"] != 0).sum())
    print(f"F2 日度触发天数: ±5% upper={up} / ±3% lower={lo}（主区间内）")

    print("\n[R1 长短端择时业绩 · 多空口径量级自检（非通过判定）]")
    fmt = _format_r1(r1)
    print(fmt[["长短端_多空", "长端_多空", "短端_多空", "T"]].to_string())
    print("  (spec R1 基准: 长短端/长端/短端/T 年化 2.93%/2.17%/1.73%/2.30%;"
          " 夏普 0.95/0.81/0.60/0.59)")

    print("\n[R2 日度效应 · 绝对值组胜率量级自检（非通过判定）]")
    abs_grp = effect[effect["group"] == "abs"].set_index("threshold")
    for t, ref in [(0.0, "50.12%/100.00%"), (0.01, "48.45%/33.24%"), (0.05, "56.52%/1.13%")]:
        row = abs_grp.loc[t]
        print(f"  阈值 {t:.2%}: 胜率={row['win_rate']:.2%} 天数比例={row['day_ratio']:.2%}"
              f"  (spec 胜率/天数比例 {ref})")

    print(f"\n中间产物已落盘:\n  {r1_path}\n  {effect_path}\n  {signals_path}")
    print("说明: 以上为量级自检，非通过判定；R1/R2/R3/R4 逐格比对归 verifier 与 check_gates。")
    return r1, effect


def main(config: Config = CONFIG) -> None:
    """冒烟运行：m1 数据/引擎链路自检 + m2 F1/F2 信号与 R1/R2/R3/R4 中间产物。"""
    panel = data_prep.build_main_panel(config)
    hs300_full = data_prep.load_hs300(config)            # 全历史（CA-A01 扩窗分位用）
    _, coverage = data_prep.load_bond_index(config)

    run_m1_smoke(panel, coverage, config)
    run_m2(panel, hs300_full["close"], config)


if __name__ == "__main__":
    main()
