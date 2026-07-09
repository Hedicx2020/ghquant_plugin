"""m5 长短端跷跷板 + 隔日反转改进策略（要素 F6 / 基准 R8）。

独立新模块：**导入并组合** 已验证底座的信号函数——隔日反转
:func:`src.test_v2.reversal.calculate_reversal_signal`（AS4/A1 human 裁决口径）与
长短端跷跷板 :func:`src.test_v2.strategy.build_interval_seesaw_signal`（spec F1 口径），
按 spec F6 分段规则合成决策信号，复用 common 择时回测引擎，在 B1 第二段区间
（2015-03-24 ~ 2023-08-02，改进策略系列）回测「多空」与「仅做多」两套策略，
产出与研报表8（R8）逐格对照的中间产物 CSV 供 verifier 反向校验。

DRY 约束：本模块**不复制** reversal / strategy 的信号实现，只做「组合 + 分段决策 +
回测编排」。R8 与 R7 属研报同一套指标口径，故 R 表组装工具（``_STAT_ROWS`` /
``_directional_win_rates`` / ``_stats_column``）直接复用 reversal 模块，保证 R8 与 R7
逐格指标定义一致、杜绝口径漂移。

————————————————————————————————————————————————————————————
F6 分段规则（spec F6，p12 + AS3/A4 auto 裁决）：
  以隔日反转因子 chg_t（= 国债期货主力 T-2 日结算价涨跌幅 settle_{T-2}/settle_{T-3}-1，
  AS4）分段选择 T 日择时信号——
    · |chg_t| ∈ [0.03%, 0.5%]（含边界）        → 按隔日反转因子择时（reversal 分支）
    · |chg_t| ∈ [0, 0.03%) ∪ (0.5%, 2%]        → 按长短端股债跷跷板择时（seesaw 分支，spec 显式）
    · |chg_t| > 2%                              → 延用长短端跷跷板择时（AS3，视同超阈值）
  三段中仅第一段走反转、其余全部走跷跷板，故实现上以「激活区间为反转、否则跷跷板」
  的二分即可自然涵盖 AS3（>2% 落入 else=跷跷板，不引入 spec 未述的第三种处置如平仓）。

时点对齐与 lag 语义（务必读——timing 类最敏感处，本实现的关键）：
  记 T 为「持仓/收益兑现日」（strategy_ret[T] = position[T]·(close_T/close_{T-1}-1)）。
  两分支对 T 日方向的判定各有天然时点，须对齐后组合：
    · 反转分支：chg_t = chg[T-2]（T-2 日结算价涨跌幅，T-2 收盘即已知）判 T 日方向（AS4）；
      reversal.calculate_reversal_signal 输出的 signal 位于「因子算出日 d」坐标
      （signal[d]=反转方向(chg[d])），配 reversal_lag_days=2 兑现到 d+2=T。
    · 跷跷板分支：signal_ls[T-1]（T-1 收盘沪深300算出的长短端信号）判 T 日方向（spec F1
      「T 日收盘做多/做空」= T-1 收盘信号 T 日执行）；配 signal_lag=1 兑现到 (T-1)+1=T，
      与 m2 的 R1 回测口径逐日一致。
  统一坐标：把组合信号构造在「形成日 d' = T-1」上，回测用 lag=signal_lag=1 兑现到 T：
    · 跷跷板分支：signal_ls[d'] 即 signal_ls[T-1]，天然位于 d' 坐标，**不移位**。
    · 反转分支：需 combo[d']=combo[T-1] 兑现后 position[T]=反转方向(chg[T-2])=signal[T-2]，
      故把因子算出日信号额外前移 (reversal_lag_days - signal_lag)=1 个交易日到 d'
      （signal.shift(1) 在 d'=T-1 取到 signal[T-2]）；总滞后 = 额外移位 + 回测 lag
      = (reversal_lag_days - signal_lag) + signal_lag = reversal_lag_days，与 reversal.py
      的 T-2→T 兑现完全等价。
  防未来函数：所有移位均为正向（shift 正数 = 取过去信号），position[T] 在 T-1 收盘即完全
  确定（仅依赖 ≤ T-1 的沪深300信号与 ≤ T-2 的结算价因子），T 日兑现，彻底杜绝前视。
  组合口径（形成日选择、反转分支额外移位量）见 assumptions AS9（coder 实现口径推断）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from common.timing_backtest import signal_backtest, timing_metrics  # noqa: E402
from src.test_v2.config import CONFIG, Config  # noqa: E402
from src.test_v2.data_prep import load_hs300, load_treasury_future_main  # noqa: E402
from src.test_v2.reversal import (  # noqa: E402
    _STAT_ROWS,
    _directional_win_rates,
    _stats_column,
    calculate_reversal_signal,
)
from src.test_v2.strategy import build_interval_seesaw_signal, to_long_only  # noqa: E402

# F6 分支标签（审计/CSV 用；据 chg[T-2] 落段划分，seesaw_extreme 单列 AS3 极端档）。
_BRANCH_REVERSAL = "reversal"            # |chg_t| ∈ [0.03%,0.5%]，走隔日反转
_BRANCH_SEESAW_MID = "seesaw_mid"        # |chg_t| ∈ [0,0.03%)∪(0.5%,2%]，走跷跷板（spec 显式）
_BRANCH_SEESAW_EXTREME = "seesaw_extreme_AS3"  # |chg_t| > 2%，走跷跷板（AS3 延用）


# ---------------------------------------------------------------------------
# F6 组合信号（长短端跷跷板 + 隔日反转分段决策）
# ---------------------------------------------------------------------------

def build_combo_ls_signal(
    futures_frame: pd.DataFrame,
    hs300_close: pd.Series,
    config: Config = CONFIG,
) -> pd.DataFrame:
    """按 spec F6 分段规则合成「长短端跷跷板 + 隔日反转」组合择时信号。

    组合信号位于「形成日 d'=T-1」坐标，回测须用 lag=config.signal_lag 兑现到 T 日
    （见模块 docstring 的时点对齐推演）。两分支信号均由底座函数生成、本函数只做对齐
    与分段选择，不复制其实现。

    Args:
        futures_frame: 国债期货主力全历史日行情（含 ``settle``/``close_return``），
            由 :func:`src.test_v2.data_prep.load_treasury_future_main` 返回。**须全历史**，
            以保证回测区间起点仍有 T-2/T-3 结算价因子。
        hs300_close: 沪深300收盘价 **全历史** 序列（load_hs300()["close"]），供 F1
            基日以来扩窗三分位（CA-A01，不可传截断面板列）。
        config: 参数集中配置（reversal_lag_days / signal_lag / reversal_min_abs /
            reversal_max_abs / seesaw_switch_upper / F1 窗口分位等）。

    Returns:
        国债期货交易日索引 DataFrame，列：
        ``combo_signal``（组合择时信号 -1/0/+1，形成日 d'=T-1 坐标，回测 lag=signal_lag 兑现）、
        ``branch``（分段归属 reversal/seesaw_mid/seesaw_extreme_AS3，审计用）、
        ``rev_signal_form``（反转分支信号，已前移至 d' 坐标）、
        ``rev_active_form``（是否落入 [0.03%,0.5%] 激活区间，判分支依据 chg[T-2]）、
        ``abs_chg_t_form``（d' 坐标对应的 |chg[T-2]|，供审计分段边界）、
        ``seesaw_ls_form``（跷跷板分支信号 signal_ls[T-1]，天然位于 d' 坐标）、
        ``close_return``（透传国债期货收盘价日收益，供回测）。
    """
    # 1. 隔日反转因子/信号（AS4，因子算出日 d 坐标）——复用 reversal，不复制。
    rev = calculate_reversal_signal(futures_frame, config)
    # 2. 长短端跷跷板信号（spec F1，T 日收盘坐标，基日以来 index）——复用 strategy，不复制。
    seesaw = build_interval_seesaw_signal(hs300_close, config)

    idx = rev.index  # 以国债期货交易日为组合信号主索引（择时标的）。

    # 反转分支：因子算出日 d=T-2 的信号额外前移 (reversal_lag_days-signal_lag) 个交易日
    # 到形成日 d'=T-1；下方回测 lag=signal_lag 再滞后 1 日，合计 reversal_lag_days=2，
    # 与 reversal.py 的 T-2→T 兑现等价。移位为正向（取过去信号），无未来函数。
    rev_extra_shift = config.reversal_lag_days - config.signal_lag
    rev_signal_form = rev["signal"].shift(rev_extra_shift)
    rev_active_form = rev["active"].shift(rev_extra_shift).fillna(False).astype(bool)
    abs_chg_t_form = rev["abs_chg_t"].shift(rev_extra_shift)

    # 跷跷板分支：signal_ls 天然口径即「T-1 收盘信号 T 日执行」（与 R1 lag=signal_lag 一致），
    # 在 d'=T-1 坐标无需移位；reindex 到国债期货交易日，缺失日（如沪深300停牌）视作平仓 0。
    seesaw_ls_form = seesaw["signal_ls"].reindex(idx).fillna(0).astype(float)

    # F6 分段决策：仅激活区间 [0.03%,0.5%] 走反转，其余（含 <0.03%、(0.5%,2%]、
    # 及 AS3 的 >2%）全部走跷跷板 → where(active, 反转, 跷跷板) 天然涵盖 AS3。
    combo_signal = rev_signal_form.where(rev_active_form, seesaw_ls_form).fillna(0.0)

    # 分支标签（审计用）：seesaw_switch_upper=2% 区分 F6 显式超阈值档与 AS3 极端档；
    # 两者最终同走跷跷板信号，单列仅为让 AS3 边界处置在中间产物中可核查。
    branch = pd.Series(_BRANCH_SEESAW_MID, index=idx, dtype=object)
    branch[rev_active_form] = _BRANCH_REVERSAL
    branch[(~rev_active_form) & (abs_chg_t_form > config.seesaw_switch_upper)] = _BRANCH_SEESAW_EXTREME

    return pd.DataFrame(
        {
            "combo_signal": combo_signal.astype(float),
            "branch": branch,
            "rev_signal_form": rev_signal_form,
            "rev_active_form": rev_active_form,
            "abs_chg_t_form": abs_chg_t_form,
            "seesaw_ls_form": seesaw_ls_form,
            "close_return": rev["close_return"],
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# R8 对照：B1 第二段区间回测多空 / 仅做多，产中间产物
# ---------------------------------------------------------------------------

def run_combo_ls(config: Config = CONFIG, write_csv: bool = True) -> pd.DataFrame:
    """在 B1 第二段区间回测 F6 组合策略多空/仅做多，产出 R8 对照 CSV。

    步骤：
    1. 加载国债期货主力与沪深300全历史；由 F6 分段规则合成组合信号（含 T-2 因子与 F1 分位）；
    2. 截取 B1 第二段区间 [main_start, main_end]=[2015-03-24, 2023-08-02]（改进策略系列，
       spec B1 / 本任务约束「第二段区间」）；
    3. 多空：直接用组合信号（-1/0/+1）；仅做多：剔除做空腿（to_long_only，AS2 口径）；
    4. 回测 lag=signal_lag=1（组合信号形成日 d'=T-1 → T 日兑现，见模块 docstring）；
    5. T 基准：国债期货买入持有（benchmark_nav 全程持有净值），与 reversal.py 口径一致；
    6. 三列各出 timing_metrics + 细分胜率（复用 reversal 的 R 表组装口径），组装 R8 对照表
       并写 ``output/test_v2/results/combo_ls_stats.csv``。

    Returns:
        指标行 × [长短端+隔日反转(多空)/长短端+隔日反转(仅做多)/T] 的对照 DataFrame。
    """
    futures = load_treasury_future_main(config)     # 全历史（区间起点仍需 T-2 因子）。
    hs300 = load_hs300(config)                       # 全历史（基日以来扩窗分位，CA-A01）。
    combo = build_combo_ls_signal(futures, hs300["close"], config)

    # 截取 B1 第二段区间（组合信号已在全历史合成，区间起点因子/分位齐备，无边界缺失）。
    start, end = pd.Timestamp(config.main_start), pd.Timestamp(config.main_end)
    window = combo.loc[(combo.index >= start) & (combo.index <= end)].copy()
    close_ret = window["close_return"]

    # 多空信号（F6 组合 -1/0/+1）；仅做多（AS2：剔除做空腿，看空→空仓）。
    ls_signal = window["combo_signal"]
    lo_signal = to_long_only(ls_signal).astype(float)

    # 组合信号形成日 d'=T-1 → 回测滞后 lag=signal_lag=1 兑现到 T 日，防未来函数。
    ls_bt = signal_backtest(ls_signal, close_ret, cost_bps=config.cost_bps, lag=config.signal_lag)
    lo_bt = signal_backtest(lo_signal, close_ret, cost_bps=config.cost_bps, lag=config.signal_lag)

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
            "长短端+隔日反转(多空)": _stats_column(ls_metrics, ls_extra),
            "长短端+隔日反转(仅做多)": _stats_column(lo_metrics, lo_extra),
            "T": _stats_column(bench_metrics, bench_extra),
        }
    ).reindex(_STAT_ROWS)
    stats.index.name = "指标"

    if write_csv:
        results_dir = config.output_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        out_path = results_dir / "combo_ls_stats.csv"
        stats.to_csv(out_path, encoding="utf-8-sig", float_format="%.6f")

    return stats


def _smoke_report(config: Config = CONFIG) -> None:
    """冒烟自检：打印 R8 五指标量级 + F6 分支占比（不下通过判定，判定归 verifier）。"""
    futures = load_treasury_future_main(config)
    hs300 = load_hs300(config)
    combo = build_combo_ls_signal(futures, hs300["close"], config)
    start, end = pd.Timestamp(config.main_start), pd.Timestamp(config.main_end)
    window = combo.loc[(combo.index >= start) & (combo.index <= end)]

    stats = run_combo_ls(config, write_csv=True)

    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 160)
    print("=" * 64)
    print("[test_v2 · m5 冒烟] 长短端跷跷板 + 隔日反转改进策略（F6 / R8）")
    print("=" * 64)
    print(f"B1 第二段回测区间: {config.main_start} ~ {config.main_end}；交易日数: {len(window)}")

    # F6 分段占比自检（据 chg[T-2] 落段；AS3 极端档单列）。
    counts = window["branch"].value_counts()
    total = len(window)
    print("\n[F6 分支占比（形成日口径，非通过判定）]")
    for label in (_BRANCH_REVERSAL, _BRANCH_SEESAW_MID, _BRANCH_SEESAW_EXTREME):
        n = int(counts.get(label, 0))
        print(f"  {label:<22}: {n:>5} 天 ({n / total:.2%})")
    print(f"  其中 AS3(|chg_t|>2%)极端档: {int(counts.get(_BRANCH_SEESAW_EXTREME, 0))} 天"
          f"（延用跷跷板，非平仓）")

    print("\n[R8 对照量级自检（非通过判定，逐格比对归 verifier）]")
    print(stats.to_string(float_format=lambda x: f"{x:.4f}"))
    print("\n  spec R8 基准 -> 多空: 区间收益59.93%/年化5.77%/回撤-3.26%/夏普1.55/胜率54.69%/"
          "盈亏比1.33/年择时129.96")
    print("               仅做多: 区间收益38.71%/年化3.99%；  T: 区间收益20.78%/年化2.28%")
    print(f"\n中间产物已落盘: {config.output_dir / 'results' / 'combo_ls_stats.csv'}")
    print("说明: 以上为量级自检，非通过判定；R8 逐格比对归 verifier 与 check_gates。")


if __name__ == "__main__":
    _smoke_report()
