"""m4 隔日反转因子 chg_t 与前作策略回顾（要素 F3 / 基准 R7）。

自包含模块：从 AS4（human 裁决 A1）公式**独立**实现隔日反转因子与信号，
复用 common 择时回测引擎，在 B1 第一段区间（2015-03-20 ~ 2023-08-02）
回测「多空」与「仅做多」两套策略，产出与研报表7逐格对照的中间产物 CSV，
供 final verify 反向校验前作公式复原是否被数据支持。

严禁引用 legacy `src/test/` 任何代码——AS4 材料仅是公式定义来源，
本实现从公式独立写起（防锚定审计要求）。

————————————————————————————————————————————————————————————
AS4 实现口径（本模块唯一权威）：
  chg_t = 国债期货主力合约 T-2 日结算价涨跌幅 = settle_{T-2}/settle_{T-3} - 1
  当 |chg_t| ∈ [0.03%, 0.5%]（含边界）时反转信号激活：
      chg_t > 0 → 做空（-1）
      chg_t < 0 → 做多（+1）
  信号在 T 日执行；区间外（|chg_t| < 0.03% 或 > 0.5%）信号为 0。

lag 语义与「T 日执行」的对齐（推演，务必读——本实现的关键）：
  记 chg[d] = settle_d/settle_{d-1} - 1（d 日结算价隔日涨跌幅），d 日收盘公布
  结算价后即完全已知。AS4 的 chg_t = settle_{T-2}/settle_{T-3}-1 = chg[T-2]，
  即「T-2 日算出的隔日涨跌」，用于判断「T 日」国债期货涨跌方向（spec F3 原文）。

  故本实现将信号构造在「因子算出日 d」上：signal[d] = 反转方向(chg[d])；
  回测时经 signal_backtest 滞后 ``reversal_lag_days`` (=2) 个交易日生效——
  使 T 日的实际持仓 position[T] = signal[T-2] = 反转方向(chg[T-2])，
  该仓位赚取 close_{T-1} → close_T 的收盘价单日收益（「T 日当天」涨跌）。
  链路：因子(T-2 收盘算出) → 至迟 T-1 收盘建仓 → 收益兑现于 T 日当天。

  与 spec B1「T 日收盘执行」的对齐：反转因子判断的是 T 日方向，持仓在 T 日兑现；
  因子仅依赖 ≤ T-2 的结算价，且执行仓位在 T-1 收盘即完全确定，彻底杜绝前视/未来函数。
  参数 ``reversal_lag_days=2`` 单一承载「因子算出日 → 收益兑现日」的 T-2→T 间隔
  （AS4 的 T-2 语义），不与跷跷板类的 signal_lag=1 混用。
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
from src.test_v2.data_prep import load_treasury_future_main  # noqa: E402

# R7 对照的指标行顺序（与 spec.md 表7 逐行对齐；供 CSV 行索引与 verifier 逐格比对）。
_STAT_ROWS: tuple[str, ...] = (
    "区间收益",
    "年化收益",
    "最大回撤",
    "年化波动率",
    "卡玛比率",
    "夏普比率",
    "胜率",
    "看多胜率",
    "看空胜率",
    "上涨胜率",
    "下跌胜率",
    "盈亏比",
    "年择时次数",
    "交易日数",
)


# ---------------------------------------------------------------------------
# F3 隔日反转因子与信号（AS4，从公式独立实现）
# ---------------------------------------------------------------------------

def calculate_reversal_signal(
    futures_frame: pd.DataFrame,
    config: Config = CONFIG,
) -> pd.DataFrame:
    """由国债期货主力结算价构造隔日反转因子 chg_t 与择时信号（AS4）。

    Args:
        futures_frame: date 索引的国债期货主力日行情，至少含 ``settle``（结算价）
            与 ``close_return``（收盘价日收益，decimal）两列；一般由
            :func:`src.test_v2.data_prep.load_treasury_future_main` 返回。
            **须传入全历史**（不要预先截区间），以保证回测区间起点仍有 T-2/T-3 结算价。
        config: 参数集中配置（reversal_lag_days / reversal_min_abs / reversal_max_abs）。

    Returns:
        date 索引 DataFrame，列：
        ``chg_t``（当日隔日结算价涨跌幅 settle_d/settle_{d-1}-1，即以本日为 T-2 时的 chg_t）、
        ``abs_chg_t``（其绝对值）、``active``（是否落入 [0.03%,0.5%] 激活区间）、
        ``signal``（因子算出日形成的反转仓位：做空 -1 / 做多 +1 / 不操作 0，
        回测时滞后 reversal_lag_days 日兑现，见 :func:`run_reversal_baseline`）、
        ``close_return``（透传的收盘价日收益，供回测）。

    实现口径与防未来函数：见模块 docstring。因子严格取 AS4 字面
    ``settle.pct_change()``（主力连续结算价的隔日涨跌），换月跳空口径见 assumptions。
    """
    frame = futures_frame.sort_index()

    # chg[d] = settle_d / settle_{d-1} - 1（d 日结算价隔日涨跌幅，严格 AS4 字面）。
    # d 日收盘公布结算价后即完全已知；回测时该信号滞后 reversal_lag_days 日兑现，
    # 使 T 日持仓由 chg[T-2] 决定（见模块 docstring 与 run_reversal_baseline）。
    chg_t = frame["settle"].astype(float).pct_change()
    abs_chg = chg_t.abs()

    # 激活区间 |chg_t| ∈ [0.03%, 0.5%]，含边界（>= 下界 且 <= 上界）。
    active = (abs_chg >= config.reversal_min_abs) & (abs_chg <= config.reversal_max_abs)

    # 反转方向：chg_t>0→做空(-1)、chg_t<0→做多(+1)，即 -sign(chg_t)；区间外置 0。
    signal = (-np.sign(chg_t)).where(active, 0.0).fillna(0.0)

    return pd.DataFrame(
        {
            "chg_t": chg_t,
            "abs_chg_t": abs_chg,
            "active": active,
            "signal": signal.astype(float),
            "close_return": frame["close_return"].astype(float),
        },
        index=frame.index,
    )


# ---------------------------------------------------------------------------
# R7 细分胜率（增强中间产物，口径见 assumptions 补登）
# ---------------------------------------------------------------------------

def _directional_win_rates(
    position: pd.Series,
    strategy_ret: pd.Series,
    asset_ret: pd.Series,
) -> dict[str, float]:
    """计算 R7 的看多/看空/上涨/下跌胜率（timing_metrics 未覆盖的细分列）。

    口径（coder 推断，见 assumptions 补登条目）：
    - 看多胜率 = 实际持多仓日（position>0）中策略日收益为正的占比；
    - 看空胜率 = 实际持空仓日（position<0）中策略日收益为正的占比；
    - 上涨胜率 = 标的当日上涨（asset_ret>0，全标的上涨日为分母）中策略日收益为正（strat>0）的占比；
    - 下跌胜率 = 标的当日下跌（asset_ret<0，全标的下跌日为分母）中策略日「不亏」（strat>=0，含0）的占比。
      （iter_02 M3/SO-02 校准：去 held 交集、下跌用不亏口径；探针 R11 下跌 0.4901 vs 研报 0.4902）
    """
    def _rate(mask: pd.Series) -> float:
        sub = strategy_ret[mask]
        return float((sub > 0).mean()) if len(sub) else float("nan")

    # 上涨/下跌胜率分母改为全标的涨/跌日（去 held 交集）；下跌用「不亏」口径 strat>=0（含 0）。
    up_sub = strategy_ret[asset_ret > 0]
    down_sub = strategy_ret[asset_ret < 0]
    return {
        "long_win_rate": _rate(position > 0),
        "short_win_rate": _rate(position < 0),
        # iter_02 M3/SO-02：分母=全标的上涨日，命中=strat>0（探针 R7 上涨 0.4443 vs 研报 0.4448）
        "up_win_rate": float((up_sub > 0).mean()) if len(up_sub) else float("nan"),
        # iter_02 M3/SO-02：分母=全标的下跌日，不亏=strat>=0（含0）（探针 R11 下跌 0.4901 vs 研报 0.4902）
        "down_win_rate": float((down_sub >= 0).mean()) if len(down_sub) else float("nan"),
    }


def _stats_column(metrics: dict, extra: dict[str, float]) -> dict[str, float]:
    """把 timing_metrics 输出 + 细分胜率映射为 R7 对照列（行顺序见 _STAT_ROWS）。

    最大回撤转为负值展示以对齐研报表7（timing_metrics 内部以正值参与卡玛计算）。
    """
    return {
        "区间收益": metrics["cumulative_return"],
        "年化收益": metrics["annual_return"],
        "最大回撤": -metrics["max_drawdown"],
        "年化波动率": metrics["annual_volatility"],
        "卡玛比率": metrics["calmar"],
        "夏普比率": metrics["sharpe"],
        "胜率": metrics["win_rate"],
        "看多胜率": extra["long_win_rate"],
        "看空胜率": extra["short_win_rate"],
        "上涨胜率": extra["up_win_rate"],
        "下跌胜率": extra["down_win_rate"],
        "盈亏比": metrics["profit_loss_ratio"],
        "年择时次数": metrics["annual_trade_count"],
        "交易日数": float(metrics["n_periods"]),
    }


# ---------------------------------------------------------------------------
# 前作策略回顾：B1 第一段区间回测多空 / 仅做多，产 R7 对照中间产物
# ---------------------------------------------------------------------------

def run_reversal_baseline(config: Config = CONFIG, write_csv: bool = True) -> pd.DataFrame:
    """在 B1 第一段区间回测隔日反转多空/仅做多策略，产出 R7 对照 CSV。

    步骤：
    1. 加载国债期货主力全历史；由 AS4 构造隔日反转信号（含 T-2/T-3 因子）；
    2. 截取回测区间 [reversal_start, reversal_end]=[2015-03-20, 2023-08-02]（B1 第一段）；
    3. 多空：直接用信号（-1/0/+1）；仅做多：剔除做空腿（信号 clip 下界 0，AS2 口径）；
    4. 回测滞后 lag=reversal_lag_days=2（因子 T-2 判 T 日、吃 T 日单日收益，见模块 docstring）；
    5. T 基准：国债期货买入持有（signal_backtest 的 benchmark_nav 全程持有净值）；
    6. 三列各出 timing_metrics + 细分胜率，组装 R7 对照表并写
       ``output/test_v2/results/reversal_baseline_stats.csv``。

    Returns:
        指标行 × [隔日反转(多空)/隔日反转(仅做多)/T] 的对照 DataFrame。
    """
    futures = load_treasury_future_main(config)
    sig_frame = calculate_reversal_signal(futures, config)

    # 截取 B1 第一段区间（因子已在全历史上算好，区间起点仍有 T-2 因子，无边界缺失）。
    start, end = pd.Timestamp(config.reversal_start), pd.Timestamp(config.reversal_end)
    window = sig_frame.loc[(sig_frame.index >= start) & (sig_frame.index <= end)].copy()
    close_ret = window["close_return"]

    # 多空信号（AS4 原始 -1/0/+1）。
    ls_signal = window["signal"]
    # 仅做多（AS2：剔除做空腿，看空→空仓）。
    lo_signal = ls_signal.clip(lower=0.0)

    # 隔日反转执行滞后：reversal_lag_days=2（因子 T-2 → T 日兑现，见模块 docstring）。
    ls_bt = signal_backtest(ls_signal, close_ret, cost_bps=config.cost_bps, lag=config.reversal_lag_days)
    lo_bt = signal_backtest(lo_signal, close_ret, cost_bps=config.cost_bps, lag=config.reversal_lag_days)

    ls_metrics = timing_metrics(ls_bt["nav"], ls_bt["position"], ls_bt["benchmark_nav"], config.periods_per_year)
    lo_metrics = timing_metrics(lo_bt["nav"], lo_bt["position"], lo_bt["benchmark_nav"], config.periods_per_year)

    # T 基准：全程买入持有（benchmark_nav 已是 cumprod(1+ret)，无建仓滞后损耗）。
    bench_nav = ls_bt["benchmark_nav"]
    bench_pos = pd.Series(1.0, index=bench_nav.index)
    bench_metrics = timing_metrics(bench_nav, bench_pos, bench_nav, config.periods_per_year)

    ls_extra = _directional_win_rates(ls_bt["position"], ls_bt["strategy_ret"], close_ret)
    lo_extra = _directional_win_rates(lo_bt["position"], lo_bt["strategy_ret"], close_ret)
    bench_extra = _directional_win_rates(bench_pos, close_ret, close_ret)

    stats = pd.DataFrame(
        {
            "隔日反转(多空)": _stats_column(ls_metrics, ls_extra),
            "隔日反转(仅做多)": _stats_column(lo_metrics, lo_extra),
            "T": _stats_column(bench_metrics, bench_extra),
        }
    ).reindex(_STAT_ROWS)
    stats.index.name = "指标"

    if write_csv:
        results_dir = config.output_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        out_path = results_dir / "reversal_baseline_stats.csv"
        stats.to_csv(out_path, encoding="utf-8-sig", float_format="%.6f")

    return stats


def _smoke_report(config: Config = CONFIG) -> None:
    """冒烟自检：打印 R7 五指标量级值（不下通过判定，判定归 verifier）。"""
    stats = run_reversal_baseline(config, write_csv=True)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 160)
    print("=== 隔日反转前作策略回顾（B1 第一段区间 "
          f"{config.reversal_start}~{config.reversal_end}）R7 对照量级自检 ===")
    print(stats.to_string(float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    _smoke_report()
