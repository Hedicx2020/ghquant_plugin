"""m6 复合跷跷板 + 隔日反转策略（要素 F4/F7，基准 R9 表9 / R10 表10 分年业绩）。

独立自包含模块：**不复制任何已落地信号实现**，只 import 组合 m2/m4 的信号函数与
common 择时回测引擎，构造复合信号与三步决策树，在 B1 第二段主区间
[main_start, main_end] = [2015-03-24, 2023-08-02] 回测「多空」与「仅做多」两套策略，
产出与研报表9逐格对照的中间产物 CSV，及表10分年业绩对照 CSV，供 verifier 逐格比对。

————————————————————————————————————————————————————————————
要素口径（本模块唯一权威，取值均反查 spec.md / assumptions.md，无魔法数字）：

[F4] 复合股债跷跷板信号 signal_seesaw（spec p13 原文）：
    signal_seesaw = sign(signal_daily_lower + signal_l_s)
    - signal_daily_lower：日度低阈值信号（±3%，AS1；strategy.build_daily_signal）
    - signal_l_s       ：长短端跷跷板信号（strategy.build_interval_seesaw_signal 的 signal_ls）
    - sign             ：符号函数（strategy.signed_signal）

[F7] 复合跷跷板 + 隔日反转三步决策树（spec p13，逐日、优先级由高到低）：
    step1  若 signal_daily_upper ≠ 0（±5% 高阈值触发，AS1）→ 用 signal_daily_upper 择时
    step2  否则 若 |chg_t| ∈ [0.03%, 0.5%]（隔日反转激活区间，AS4）→ 用隔日反转信号
           （chg_t>0 做空 -1 / chg_t<0 做多 +1）
    step3  否则 → 用复合信号 signal_seesaw（=1 看多 / =-1 看空 / 0 平仓）
    AS3 对齐：|chg_t| 超出 [0.03%,0.5%]（含 [0,0.03%)、(0.5%,2%]、>2%）一律落 step3
    复合跷跷板；「>2% 延用跷跷板」即由 step3 默认分支天然承载，无需显式判断（见 AS3）。

[R9]  表9 复合+隔日反转业绩（多空/仅做多/T 三列，13 指标行）。
[R10] 表10 复合策略分年业绩（2015–2023 × 列组 区间收益/最大回撤/年化波动率 × 复合多空/
      复合仅做多/T）。分年基于整段连续回测的日收益按自然年切片（非逐年重建仓）。

————————————————————————————————————————————————————————————
三信号 lag 语义统一（务必读——本模块最易错处）：

决策树在「决策日 d」逐日选一个目标仓位 combined[d]，随后整个 combined 序列经
common.signal_backtest 统一滞后 signal_lag(=1) 日生效，使 position[T]=combined[T-1]，
赚取标的 T 日单日收盘价收益 close_return[T]。三来源信号在决策日坐标下的对齐：

  - signal_daily_upper / signal_seesaw（跷跷板系）：spec 口径本就是「T 日收盘/单日涨跌
    生成、下一交易日执行」，与 m2 R1 的 lag=1 完全一致，直接落决策日 d，无需前移。
  - 隔日反转（AS4）：m4 R7 单独回测时信号在「因子算出日 e」坐标、经 reversal_lag_days(=2)
    生效使 position[T]=反转方向(chg[T-2])。本模块为与跷跷板统一到 signal_lag(=1) 回测，
    将隔日反转信号在决策日坐标 **前移** (reversal_lag_days − signal_lag) = 1 天：
        reversal_decide[d] = reversal_signal[d-1] = 反转方向(settle_{d-1}/settle_{d-2}-1)
    统一 lag=1 后 position[T]=reversal_decide[T-1]=反转方向(chg[T-2])，与 R7 逐日一致。
    前移量严格由 config.reversal_lag_days − config.signal_lag 反查（非魔法数字），
    该差值单一承载「隔日反转 T-2→T 兑现」与「统一回测 lag=1」之间的坐标换算。

  防未来函数：决策日 d 的三个判断依据（d 日沪深300单日涨跌、d 日跷跷板、
  chg[d-1]=settle_{d-1}/settle_{d-2}-1）均在 d 日收盘完全已知，combined[d] 经 lag=1
  于 d+1 执行；隔日反转因子仅依赖 ≤ d-1 结算价，彻底杜绝前视/未来函数。

边界：与 m2/m4 一致，回测传主区间 index、lag 使区间首日 position=0（损失微小，
口径统一优先于多算一天）。仅做多口径 AS2：对决策树最终多空信号剔除做空腿
（strategy.to_long_only，看空→空仓）。

细分胜率（看多/看空/上涨/下跌）复用 m4 reversal 的 AS7 口径（import 复用、不复制），
保证 R9 与 R7 同口径；R9 指标行顺序与列结构复用 R7 的 _STAT_ROWS/_stats_column。
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
from common.utils import (  # noqa: E402
    calculate_annualized_volatility,
    calculate_max_drawdown,
)
from src.test_v2.config import CONFIG, Config  # noqa: E402
from src.test_v2.data_prep import (  # noqa: E402
    build_main_panel,
    load_hs300,
    load_treasury_future_main,
)
from src.test_v2.reversal import (  # noqa: E402  复用 AS7 细分胜率口径与 R7 表结构（不复制）
    _STAT_ROWS,
    _directional_win_rates,
    _stats_column,
)
from src.test_v2.strategy import (  # noqa: E402  组合 m2/m4 已落地信号函数（不复制实现）
    build_daily_signal,
    build_interval_seesaw_signal,
    signed_signal,
    to_long_only,
)
from src.test_v2.reversal import calculate_reversal_signal  # noqa: E402

# R10 分年对照的指标列组（与 spec.md 表10 表头一致：区间收益/最大回撤/年化波动率）。
_YEARLY_ROWS: tuple[str, ...] = ("区间收益", "最大回撤", "年化波动率")

# R9 / R10 策略列名（多空为主口径、仅做多为 AS2 次要口径）。
_LS_NAME = "复合跷跷板+隔日反转(多空)"
_LO_NAME = "复合跷跷板+隔日反转(仅做多)"


# ---------------------------------------------------------------------------
# F4 复合信号 / F7 三步决策树（纯函数，决策日坐标；便于单元复用与审计）
# ---------------------------------------------------------------------------

def build_composite_seesaw_signal(
    signal_daily_lower: pd.Series,
    signal_ls: pd.Series,
) -> pd.Series:
    """F4：复合股债跷跷板信号 signal_seesaw = sign(signal_daily_lower + signal_l_s)。

    两输入均为决策日 T 坐标的 -1/0/+1 择时信号，按 spec p13 简单叠加取符号。
    pandas 按 index 对齐后相加，未对齐位置经 signed_signal 内部 fillna(0) 视作 0。

    Args:
        signal_daily_lower: 日度低阈值(±3%, AS1)信号（strategy.build_daily_signal 输出）。
        signal_ls: 长短端跷跷板信号（strategy.build_interval_seesaw_signal 的 signal_ls）。

    Returns:
        index 为两输入并集的复合信号 Series（int -1/0/+1）。
    """
    idx = pd.Index(signal_daily_lower.index).union(signal_ls.index)
    lower = pd.Series(signal_daily_lower).reindex(idx).fillna(0)
    ls = pd.Series(signal_ls).reindex(idx).fillna(0)
    return signed_signal(lower + ls)


def build_composite_reversal_position(
    signal_daily_upper: pd.Series,
    reversal_signal_decide: pd.Series,
    reversal_active_decide: pd.Series,
    signal_seesaw: pd.Series,
) -> pd.Series:
    """F7：复合跷跷板 + 隔日反转三步决策树 → 决策日坐标复合多空信号（向量化）。

    优先级由高到低（spec p13 三步，np.select 取第一个命中条件）：
      step1  signal_daily_upper ≠ 0 → signal_daily_upper（日度高阈值±5% 触发）
      step2  否则 reversal_active_decide 为真（|chg_t|∈[0.03%,0.5%]，AS4）→ reversal_signal_decide
      step3  否则 → signal_seesaw（复合跷跷板；AS3 的 >2% 延用跷跷板由此默认分支承载）
    所有输入须已对齐到同一决策日 index（见 assemble_signals）。

    Args:
        signal_daily_upper: 日度高阈值(±5%, AS1)信号，决策日坐标。
        reversal_signal_decide: 隔日反转信号，已前移到决策日坐标（见模块 docstring）。
        reversal_active_decide: 隔日反转激活标记(bool)，已前移到决策日坐标。
        signal_seesaw: F4 复合信号，决策日坐标。

    Returns:
        决策日坐标复合多空信号 Series（int -1/0/+1）。
    """
    idx = signal_seesaw.index
    du = pd.Series(signal_daily_upper).reindex(idx).fillna(0).to_numpy()
    rs = pd.Series(reversal_signal_decide).reindex(idx).fillna(0).to_numpy()
    ra = pd.Series(reversal_active_decide).reindex(idx).fillna(False).astype(bool).to_numpy()
    ss = pd.Series(signal_seesaw).reindex(idx).fillna(0).to_numpy()

    combined = np.select([du != 0, ra], [du, rs], default=ss)
    return pd.Series(combined, index=idx).round().astype(int)


# ---------------------------------------------------------------------------
# 信号装配（决策日坐标，主区间对齐）
# ---------------------------------------------------------------------------

def assemble_signals(config: Config = CONFIG) -> pd.DataFrame:
    """装配 F4/F7 所需的全部决策日坐标信号，对齐到主区间国债期货交易日。

    数据源须全历史（不预先截区间），以保证扩窗分位样本完整（F1，CA-A01）与区间起点
    仍有隔日反转 T-2/T-3 结算价前移值；仅在最后 reindex 到主区间面板 index。

    Returns:
        主区间 date 索引 DataFrame，列：
        signal_daily_upper / signal_daily_lower（F2 日度 ±5%/±3% 信号）、
        signal_ls（F1 长短端跷跷板信号）、signal_seesaw（F4 复合信号）、
        reversal_signal_decide（隔日反转信号，已前移决策日坐标）、
        reversal_active_decide（隔日反转激活标记 0/1，决策日坐标）、
        combined_ls（F7 决策树复合多空信号）、close_return（国债期货收盘价日收益，回测标的）。
    """
    futures = load_treasury_future_main(config)   # 全历史（隔日反转结算价 + close_return）
    hs = load_hs300(config)                        # 全历史（扩窗分位，CA-A01）
    panel = build_main_panel(config)               # 主区间对齐面板
    idx = panel.index

    # F1 长短端跷跷板：全历史扩窗三分位算 signal_ls，再对齐主区间。
    seesaw = build_interval_seesaw_signal(hs["close"], config)
    signal_ls = seesaw["signal_ls"].reindex(idx).fillna(0).astype(int)

    # F2 日度信号：逐日单日涨跌触发，主区间 hs300_return 直接生成（无历史窗口）。
    signal_daily_upper = build_daily_signal(panel["hs300_return"], config.daily_upper_threshold)
    signal_daily_lower = build_daily_signal(panel["hs300_return"], config.daily_lower_threshold)

    # F4 复合信号 signal_seesaw = sign(daily_lower + ls)，对齐主区间。
    signal_seesaw = build_composite_seesaw_signal(signal_daily_lower, signal_ls).reindex(idx).fillna(0).astype(int)

    # F3/AS4 隔日反转：全历史因子日坐标 → 前移 (reversal_lag_days − signal_lag) 天到决策日坐标。
    rev = calculate_reversal_signal(futures, config)
    shift_to_decide = config.reversal_lag_days - config.signal_lag  # =1，见模块 docstring lag 推演
    rev_signal_decide = rev["signal"].shift(shift_to_decide).reindex(idx).fillna(0.0)
    rev_active_decide = rev["active"].shift(shift_to_decide).reindex(idx).fillna(False)

    # F7 三步决策树 → 复合多空信号（决策日坐标）。
    combined_ls = build_composite_reversal_position(
        signal_daily_upper, rev_signal_decide, rev_active_decide, signal_seesaw
    )

    return pd.DataFrame(
        {
            "signal_daily_upper": signal_daily_upper.reindex(idx).astype(int),
            "signal_daily_lower": signal_daily_lower.reindex(idx).astype(int),
            "signal_ls": signal_ls,
            "signal_seesaw": signal_seesaw,
            "reversal_signal_decide": rev_signal_decide.astype(float),
            "reversal_active_decide": rev_active_decide.astype(int),
            "combined_ls": combined_ls,
            "close_return": panel["future_close_return"].astype(float),
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# 回测（多空 / 仅做多 / T 基准，统一 signal_lag=1）
# ---------------------------------------------------------------------------

def build_composite_backtest(config: Config = CONFIG) -> dict:
    """装配信号并回测复合多空 / 仅做多 / T 基准，返回供 R9/R10 共用的中间结果束。

    多空、仅做多均以 F7 决策树复合信号经 signal_backtest 统一滞后 signal_lag(=1) 回测；
    T 基准取 signal_backtest 的 benchmark_nav（国债期货买入持有，无建仓滞后损耗）。
    """
    signals = assemble_signals(config)
    combined = signals["combined_ls"]
    close_ret = signals["close_return"]

    # 多空：F7 决策树原始 -1/0/+1；仅做多：剔除做空腿（AS2）。
    ls_bt = signal_backtest(combined, close_ret, cost_bps=config.cost_bps, lag=config.signal_lag)
    lo_bt = signal_backtest(to_long_only(combined), close_ret, cost_bps=config.cost_bps, lag=config.signal_lag)

    bench_nav = ls_bt["benchmark_nav"]
    bench_pos = pd.Series(1.0, index=bench_nav.index)

    return {
        "signals": signals,
        "close_ret": close_ret,
        "ls_bt": ls_bt,
        "lo_bt": lo_bt,
        "bench_nav": bench_nav,
        "bench_pos": bench_pos,
    }


# ---------------------------------------------------------------------------
# R9 表9：复合+隔日反转业绩（多空/仅做多/T）
# ---------------------------------------------------------------------------

def build_r9_table(bundle: dict, config: Config = CONFIG) -> pd.DataFrame:
    """R9 表9：复合跷跷板+隔日反转（多空/仅做多）+ T 基准，行=指标（复用 R7 结构）。"""
    ls_bt, lo_bt = bundle["ls_bt"], bundle["lo_bt"]
    close_ret = bundle["close_ret"]
    bench_nav, bench_pos = bundle["bench_nav"], bundle["bench_pos"]

    ls_m = timing_metrics(ls_bt["nav"], ls_bt["position"], ls_bt["benchmark_nav"], config.periods_per_year)
    lo_m = timing_metrics(lo_bt["nav"], lo_bt["position"], lo_bt["benchmark_nav"], config.periods_per_year)
    bench_m = timing_metrics(bench_nav, bench_pos, bench_nav, config.periods_per_year)

    ls_extra = _directional_win_rates(ls_bt["position"], ls_bt["strategy_ret"], close_ret)
    lo_extra = _directional_win_rates(lo_bt["position"], lo_bt["strategy_ret"], close_ret)
    bench_extra = _directional_win_rates(bench_pos, close_ret, close_ret)

    stats = pd.DataFrame(
        {
            _LS_NAME: _stats_column(ls_m, ls_extra),
            _LO_NAME: _stats_column(lo_m, lo_extra),
            "T": _stats_column(bench_m, bench_extra),
        }
    ).reindex(_STAT_ROWS)
    stats.index.name = "指标"
    return stats


# ---------------------------------------------------------------------------
# R10 表10：复合策略分年业绩（区间收益/最大回撤/年化波动率）
# ---------------------------------------------------------------------------

def _yearly_stats(daily_ret: pd.Series, config: Config = CONFIG) -> pd.DataFrame:
    """把整段连续回测日收益按自然年切片，算 区间收益/最大回撤/年化波动率。

    - 区间收益 = 该年 nav 累计 (1+ret).prod()-1（部分年如 2015/2023 取其实际交易日）
    - 最大回撤 = 该年内 nav 最大回撤（转负值展示，对齐研报表10 符号）
    - 年化波动率 = 该年日收益 std × sqrt(periods_per_year)（复用 common.utils 口径）
    """
    ret = pd.Series(daily_ret).dropna()
    rows: dict[str, dict[str, float]] = {}
    for year, grp in ret.groupby(ret.index.year):
        nav = (1.0 + grp).cumprod()
        rows[f"{year}年"] = {
            "区间收益": float(nav.iloc[-1] - 1.0),
            "最大回撤": -calculate_max_drawdown(nav),
            "年化波动率": calculate_annualized_volatility(grp, config.periods_per_year),
        }
    return pd.DataFrame(rows).T.reindex(columns=list(_YEARLY_ROWS))


def build_r10_yearly_table(bundle: dict, config: Config = CONFIG) -> pd.DataFrame:
    """R10 表10：复合策略分年业绩（列组 区间收益/最大回撤/年化波动率 × 复合多空/复合仅做多/T）。

    列顺序与 spec.md 表10 一致：先按指标分组，每组三列（复合多空/复合仅做多/T）。
    T 基准分年基于国债期货买入持有日收益（close_return），策略分年基于扣费后 strategy_ret。
    """
    ls_yr = _yearly_stats(bundle["ls_bt"]["strategy_ret"], config)
    lo_yr = _yearly_stats(bundle["lo_bt"]["strategy_ret"], config)
    t_yr = _yearly_stats(bundle["close_ret"], config)

    out = pd.DataFrame(index=ls_yr.index)
    for metric in _YEARLY_ROWS:
        out[f"{metric}·复合多空"] = ls_yr[metric]
        out[f"{metric}·复合仅做多"] = lo_yr[metric]
        out[f"{metric}·T"] = t_yr[metric]
    out.index.name = "年份"
    return out


# ---------------------------------------------------------------------------
# 运行入口：产 R9 / R10 对照中间产物
# ---------------------------------------------------------------------------

def run_composite_strategy(
    config: Config = CONFIG, write_csv: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """回测复合跷跷板+隔日反转策略，产 R9 五指标对照表与 R10 分年业绩表。

    落盘（output/test_v2/results/）：
    - combo_composite_stats.csv         R9 对照表（多空/仅做多/T，13 指标行 + 交易日数）
    - combo_composite_yearly_stats.csv  R10 分年对照表（9 年 × 9 列）
    - combo_composite_signals.csv       决策日信号 + 回测明细（position/nav），供 verifier 画图/审计

    Returns:
        (r9, r10)：R9 对照 DataFrame 与 R10 分年 DataFrame。
    """
    bundle = build_composite_backtest(config)
    r9 = build_r9_table(bundle, config)
    r10 = build_r10_yearly_table(bundle, config)

    if write_csv:
        results_dir = config.output_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        r9.to_csv(results_dir / "combo_composite_stats.csv", encoding="utf-8-sig", float_format="%.6f")
        r10.to_csv(results_dir / "combo_composite_yearly_stats.csv", encoding="utf-8-sig", float_format="%.6f")

        detail = bundle["signals"].copy()
        detail["position_ls"] = bundle["ls_bt"]["position"]
        detail["strategy_ret_ls"] = bundle["ls_bt"]["strategy_ret"]
        detail["nav_ls"] = bundle["ls_bt"]["nav"]
        detail["position_lo"] = bundle["lo_bt"]["position"]
        detail["nav_lo"] = bundle["lo_bt"]["nav"]
        detail["benchmark_nav"] = bundle["bench_nav"]
        detail.to_csv(results_dir / "combo_composite_signals.csv", encoding="utf-8-sig", float_format="%.6f")

    return r9, r10


def _smoke_report(config: Config = CONFIG) -> None:
    """冒烟自检：打印 R9 五指标 + R10 抽样年份量级（不下通过判定，判定归 verifier）。"""
    r9, r10 = run_composite_strategy(config, write_csv=True)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 200)

    print("=" * 68)
    print(f"[test_v2 · m6 冒烟] 复合跷跷板+隔日反转 R9/R10 量级自检")
    print(f"主区间(B1第二段): {config.main_start} ~ {config.main_end}")
    print("=" * 68)

    print("\n[R9 复合+隔日反转业绩 · 量级自检（非通过判定）]")
    print(r9.to_string(float_format=lambda x: f"{x:.4f}"))
    print(
        "\n  (spec R9 基准: 多空 区间收益67.99%/年化6.40%/回撤-3.24%/波动3.74%/卡玛1.98/"
        "夏普1.71/胜率54.93%/盈亏1.36/年择时128.88;"
        "\n                仅做多 区间收益43.38%/年化4.40%/夏普1.58/盈亏1.52;"
        " T 区间收益20.78%/年化2.28%/夏普0.59)"
    )

    print("\n[R10 分年业绩 · 抽样量级自检（非通过判定）]")
    print(r10.to_string(float_format=lambda x: f"{x:.4f}"))
    print(
        "\n  (spec R10 复合多空: 2015 区间8.58%/回撤-3.24%/波动5.13%;"
        " 2020 区间10.42%/回撤-2.42%/波动4.22%;"
        "\n                     2023 区间0.51%/回撤-1.61%/波动2.11%;"
        " T 2015 区间3.06%/波动5.33%)"
    )
    print(
        "\n说明: 以上为量级自检，非通过判定；R9/R10 逐格比对归 verifier 与 check_gates。"
    )


if __name__ == "__main__":
    _smoke_report()
