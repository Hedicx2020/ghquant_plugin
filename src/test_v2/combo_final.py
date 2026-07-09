"""m7 周内效应 + 复合跷跷板 + 隔日反转最终策略（要素 F5/F8，基准 R11 表11 / R12 分年）。

**本模块是全报告落脚点**：F8 最终三步决策树的多空策略即研报核心结论
（R11 区间收益 85.22% / 年化 7.65% / 最大回撤 -3.26% / 夏普 2.04 / 卡玛 2.35）。

独立自包含模块：**不复制任何已落地信号/回测实现**，只 import 组合 m2/m4/m6 的信号
函数与 common 择时回测引擎，构造 F5 周内信号与 F8 决策树，在 B1 第二段主区间
[main_start, main_end] = [2015-03-24, 2023-08-02] 回测「多空」与「仅做多」两套策略，
产出与研报表11逐格对照的中间产物 CSV，及表12分年业绩对照 CSV，供 verifier 逐格比对。

DRY 约束：F4 复合信号复用 combo_composite.build_composite_seesaw_signal；R11 指标口径
复用 reversal 的 _STAT_ROWS/_directional_win_rates/_stats_column（与 R7/R9 逐格同口径）；
R12 分年计算复用 combo_composite._yearly_stats（与 R10 同口径，spec 表12 列结构=表10）；
底座信号复用 strategy（F1/F2/AS2）与 reversal（AS4）。本模块只新写 F5/F8 特定逻辑。

————————————————————————————————————————————————————————————
要素口径（本模块唯一权威，取值均反查 spec.md / assumptions.md，无魔法数字）：

[F5] 周内日历效应信号（spec p15 原文）：
    signal_calendar = 1 if day t is Thursday, else 0            （周四=1，取值 {0,1} 非 ±1）
    signal_daily_upper_calendar = sign(signal_daily_upper + signal_calendar)
    - signal_daily_upper：日度高阈值信号（±5%，AS1；strategy.build_daily_signal）
    - sign             ：符号函数（strategy.signed_signal）
    周内效应含义=「周四国债期货偏多」：周四(cal=1)时 sign 把 upper=0→+1（看多）、
    upper=-1(大涨本应做空)→sign(0)=0（周四多头抵消做空）、upper=+1→+1。

    signal_calendar 时点对齐（AS10，coder 推断）：偏多的是「持仓/收益兑现日为周四」那天。
    combo 决策日坐标下 combined[d] 经 signal_lag 兑现到下一交易日 d+1，故决策日 d 的
    signal_calendar 标记「兑现日 d+1 是否周四」= is_thursday.shift(-1)（config.
    calendar_align_to_settle_day=True 默认口径B）。日历前移是**确定性时间信息**——「d+1
    是否周四」在 d 日（乃至任意历史时点）完全可知，交易日排期提前确定，非价格/收益前视，
    不构成未来函数（口径 A/B 与防未来论证见 AS10）。

[F8] 周内 + 复合跷跷板 + 隔日反转三步决策树（spec p15，逐日、优先级由高到低）：
    step1  若 signal_daily_upper_calendar ≠ 0（F5 含周四效应）→ 用 signal_daily_upper_calendar
    step2  否则 若 signal_daily_upper = 0 且 |chg_t| ∈ [0.03%,0.5%]（AS4 激活）→ 用隔日反转
    step3  否则 → 用复合信号 signal_seesaw（=1 看多 / =-1 看空 / 0 平仓）
    AS3 对齐：|chg_t| 超出 [0.03%,0.5%] 一律落 step3 复合跷跷板（同 F7），「>2% 延用跷跷板」
    由 step3 默认分支天然承载。

    ★ F8 与 F7（combo_composite）的唯一结构差异，且 step2 判据不可照搬 F7 ★：
    F7 中 step1 触发条件是 signal_daily_upper≠0，故「step1 不触发 ⟺ signal_daily_upper=0」，
    combo_composite 的 np.select step2 条件因此省略 (du==0)、只写 reversal_active。
    但 F8 的 step1 触发条件是 signal_daily_upper_calendar≠0，「step1 不触发 ⟺
    signal_daily_upper_calendar=0」，此时 signal_daily_upper **未必=0**——周四(cal=1)且日度
    大涨(upper=-1)时 signal_daily_upper_calendar=sign(-1+1)=0 但 signal_daily_upper=-1。
    spec F8 原文 step2 明写「signal_daily_upper=0」（非 signal_daily_upper_calendar=0），
    故本模块 step2 **必须显式**判 (signal_daily_upper==0)：该「周四大涨」样本 du_cal=0 却
    du≠0，既不走 step1 也不满足 step2，直落 step3 复合跷跷板（与 spec 逐字一致）。

[R11] 表11 周内+复合+隔日反转业绩（多空/仅做多/T 三列，13 指标行；报告落脚点）。
[R12] 表12 周内+复合分年业绩（2015–2023 × 列组 区间收益/最大回撤/年化波动率 × 复合多空/
      复合仅做多/T；spec 表12 列名沿用「复合多空」，列结构与表10 完全一致）。分年基于整段
      连续回测的日收益按自然年切片（非逐年重建仓），复用 combo_composite._yearly_stats。

————————————————————————————————————————————————————————————
三/四信号 lag 语义统一（沿用 m6 combo_composite 的 AS9 框架，本模块最易错处）：

决策树在「决策日 d」逐日选一个目标仓位 combined[d]，随后整个 combined 序列经
common.signal_backtest 统一滞后 signal_lag(=1) 日生效，使 position[T]=combined[T-1]，
赚取标的 T 日单日收盘价收益 close_return[T]。四来源信号在决策日坐标下的对齐：

  - signal_daily_upper / signal_seesaw（跷跷板系）：spec 口径本即「T 日单日涨跌生成、
    下一交易日执行」，与 m2 R1 的 lag=1 一致，直接落决策日 d，无需前移。
  - signal_calendar（F5 周内，AS10）：决策日 d 标记兑现日 d+1 是否周四（is_thursday.shift(-1)），
    与 signal_daily_upper 同在决策日 d 坐标相加取 sign → signal_daily_upper_calendar[d]，
    经 lag=1 使 position[T]=…[T-1]，兑现日 T 为周四时偏多（周内效应经济语义）。
  - 隔日反转（AS4）：因子算出日信号前移 (reversal_lag_days − signal_lag)=1 天到决策日坐标，
    统一 lag=1 后 position[T]=反转方向(chg[T-2])，与 R7 逐日一致（同 combo_composite）。

  防未来函数：决策日 d 的判断依据（d 日沪深300单日涨跌、d 日跷跷板、d+1 是否周四【确定性
  日历】、chg[d-1]=settle_{d-1}/settle_{d-2}-1）在 d 日收盘全部已知，combined[d] 经 lag=1
  于 d+1 执行；隔日反转因子仅依赖 ≤ d-1 结算价，日历仅依赖确定性交易日排期，杜绝前视。

边界：与 m2/m4/m6 一致，回测传主区间 index、lag 使区间首日 position=0（损失微小，口径统一
优先）。仅做多口径 AS2：对决策树最终多空信号剔除做空腿（strategy.to_long_only，看空→空仓）。
细分胜率（看多/看空/上涨/下跌）复用 reversal 的 AS7 口径，R11 指标行/列结构复用 R7 的
_STAT_ROWS/_stats_column，保证 R11 与 R7/R9 逐格同口径。
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
from src.test_v2.combo_composite import (  # noqa: E402  复用 F4 复合信号与 R10/R12 分年口径（不复制）
    _YEARLY_ROWS,
    _yearly_stats,
    build_composite_seesaw_signal,
)
from src.test_v2.config import CONFIG, Config  # noqa: E402
from src.test_v2.data_prep import (  # noqa: E402
    build_main_panel,
    load_hs300,
    load_treasury_future_main,
)
from src.test_v2.reversal import (  # noqa: E402  复用 AS7 细分胜率与 R7 表结构 + AS4 反转信号（不复制）
    _STAT_ROWS,
    _directional_win_rates,
    _stats_column,
    calculate_reversal_signal,
)
from src.test_v2.strategy import (  # noqa: E402  组合 m2 已落地信号函数（不复制实现）
    build_daily_signal,
    build_interval_seesaw_signal,
    signed_signal,
    to_long_only,
)

# R11 / R12 策略列名（多空为主口径=报告落脚点，仅做多为 AS2 次要口径）。
_LS_NAME = "周内+复合跷跷板+隔日反转(多空)"
_LO_NAME = "周内+复合跷跷板+隔日反转(仅做多)"


# ---------------------------------------------------------------------------
# F5 周内信号（signal_calendar / signal_daily_upper_calendar，决策日坐标）
# ---------------------------------------------------------------------------

def build_calendar_signal(
    trading_days: pd.DatetimeIndex,
    config: Config = CONFIG,
) -> pd.Series:
    """F5：周内日历效应信号 signal_calendar（决策日坐标，取值 {0,1}）。

    spec p15：signal_calendar = 1 if day t is Thursday else 0。周内效应「周四国债期货偏多」
    偏多的是持仓/收益兑现日为周四那天（AS10）。combo 决策日坐标框架下 combined[d] 经
    signal_lag 兑现到下一交易日 d+1，故：
      - config.calendar_align_to_settle_day=True（口径B，默认）：决策日 d 的信号标记「兑现日
        d+1 是否周四」= is_thursday.shift(-1)，使周四持仓偏多，与经济语义一致；
      - False（口径A，备选）：signal_calendar 标记决策日 d 自身是否周四（不前移）。

    防未来函数：shift(-1) 仅作用于**确定性交易日历**——「下一交易日是否周四」在决策日 d
    收盘（乃至任意历史时点）完全已知，交易日排期提前确定，非价格/收益前视，不构成未来函数
    （见 AS10 论证）。返回全历史序列（末端 shift 后为 NaN），由调用方 reindex 主区间 + fillna(0)。

    Args:
        trading_days: 国债期货主力**全历史**交易日 index（load_treasury_future_main().index），
            用于以真实交易日序列判定周四与「下一交易日」，边界（主区间末日）不失真。
        config: 参数（calendar_weekday=3 周四 / calendar_align_to_settle_day 口径开关）。

    Returns:
        index=trading_days 的 signal_calendar（int {0,1}；口径B 末端为 NaN 待 fillna）。
    """
    idx = pd.DatetimeIndex(trading_days).sort_values()
    is_thursday = pd.Series((idx.weekday == config.calendar_weekday).astype(int), index=idx)
    if config.calendar_align_to_settle_day:
        # 决策日 d → 兑现日(下一交易日 d+1)是否周四；正向语义上的「向后看日历」，非价格前视。
        return is_thursday.shift(-1)
    return is_thursday


def build_daily_upper_calendar_signal(
    signal_daily_upper: pd.Series,
    signal_calendar: pd.Series,
) -> pd.Series:
    """F5：signal_daily_upper_calendar = sign(signal_daily_upper + signal_calendar)。

    两输入在决策日坐标叠加取符号（strategy.signed_signal 基元，与 F1 的 sign(长+短)、F4 的
    sign(daily_lower+ls) 同范式）。signal_daily_upper ∈ {-1,0,+1}（±5%，AS1），
    signal_calendar ∈ {0,1}（周四=1）。周四偏多：cal=1 时 upper=0→+1、upper=-1→0、upper=+1→+1。

    Args:
        signal_daily_upper: 日度高阈值(±5%,AS1)信号，决策日坐标。
        signal_calendar: F5 周内信号（决策日坐标，见 build_calendar_signal）。

    Returns:
        index 为两输入并集的 signal_daily_upper_calendar（int -1/0/+1）。
    """
    idx = pd.Index(signal_daily_upper.index).union(signal_calendar.index)
    du = pd.Series(signal_daily_upper).reindex(idx).fillna(0)
    cal = pd.Series(signal_calendar).reindex(idx).fillna(0)
    return signed_signal(du + cal)


# ---------------------------------------------------------------------------
# F8 三步决策树（纯函数，决策日坐标；便于单元复用与审计）
# ---------------------------------------------------------------------------

def build_final_reversal_position(
    signal_daily_upper_calendar: pd.Series,
    signal_daily_upper: pd.Series,
    reversal_signal_decide: pd.Series,
    reversal_active_decide: pd.Series,
    signal_seesaw: pd.Series,
) -> pd.Series:
    """F8：周内+复合跷跷板+隔日反转三步决策树 → 决策日坐标复合多空信号（向量化）。

    优先级由高到低（spec p15 三步，np.select 取第一个命中条件）：
      step1  signal_daily_upper_calendar ≠ 0 → signal_daily_upper_calendar（F5 含周四效应）
      step2  否则 signal_daily_upper == 0 且 reversal_active_decide 为真（|chg_t|∈[0.03%,0.5%]，
             AS4）→ reversal_signal_decide
      step3  否则 → signal_seesaw（复合跷跷板；AS3 的 >2% 由此默认分支承载，同 F7）

    ★ 与 F7（combo_composite.build_composite_reversal_position）的差异，且 step2 不可省略判据 ★：
    F7 step1 触发条件是 signal_daily_upper≠0 ⇒ 不触发即 signal_daily_upper=0，故其 np.select
    step2 只写 reversal_active（(du==0) 冗余省略）。F8 step1 触发条件换成
    signal_daily_upper_calendar≠0 ⇒ 不触发即 signal_daily_upper_calendar=0，此时
    signal_daily_upper **未必=0**（周四+日度大涨：du_cal=sign(-1+1)=0 而 du=-1）。spec F8
    原文 step2 明写「signal_daily_upper=0」，故本函数 step2 条件 **显式** 写 (du==0) & ra——
    上述「周四大涨」样本既不入 step1（du_cal=0）也不满足 step2（du=-1≠0），落 step3 复合跷跷板，
    与 spec 逐字一致。所有输入须已对齐到同一决策日 index（见 assemble_signals）。

    Args:
        signal_daily_upper_calendar: F5 周内叠加信号，决策日坐标（step1 触发信号）。
        signal_daily_upper: 日度高阈值(±5%)信号，决策日坐标（step2 判据，原始 upper 非 calendar）。
        reversal_signal_decide: 隔日反转信号，已前移到决策日坐标。
        reversal_active_decide: 隔日反转激活标记(bool)，已前移到决策日坐标。
        signal_seesaw: F4 复合信号，决策日坐标。

    Returns:
        决策日坐标复合多空信号 Series（int -1/0/+1）。
    """
    idx = signal_seesaw.index
    du_cal = pd.Series(signal_daily_upper_calendar).reindex(idx).fillna(0).to_numpy()
    du = pd.Series(signal_daily_upper).reindex(idx).fillna(0).to_numpy()
    rs = pd.Series(reversal_signal_decide).reindex(idx).fillna(0).to_numpy()
    ra = pd.Series(reversal_active_decide).reindex(idx).fillna(False).astype(bool).to_numpy()
    ss = pd.Series(signal_seesaw).reindex(idx).fillna(0).to_numpy()

    # step1: du_cal≠0 → du_cal；step2: du==0 且反转激活 → rs；step3(default): ss。
    combined = np.select([du_cal != 0, (du == 0) & ra], [du_cal, rs], default=ss)
    return pd.Series(combined, index=idx).round().astype(int)


# ---------------------------------------------------------------------------
# 信号装配（决策日坐标，主区间对齐）
# ---------------------------------------------------------------------------

def assemble_signals(config: Config = CONFIG) -> pd.DataFrame:
    """装配 F5/F8 所需的全部决策日坐标信号，对齐到主区间国债期货交易日。

    数据源须全历史（不预先截区间），以保证扩窗分位样本完整（F1，CA-A01）、区间起点仍有
    隔日反转 T-2/T-3 结算价前移值、及周内信号以真实全历史交易日判「下一交易日周四」（边界
    不失真）；仅在最后 reindex 到主区间面板 index。

    Returns:
        主区间 date 索引 DataFrame，列：
        signal_daily_upper / signal_daily_lower（F2 日度 ±5%/±3% 信号）、
        signal_ls（F1 长短端跷跷板信号）、signal_seesaw（F4 复合信号）、
        signal_calendar（F5 周内信号，决策日坐标 0/1）、
        signal_daily_upper_calendar（F5 叠加信号 -1/0/+1）、
        reversal_signal_decide（隔日反转信号，已前移决策日坐标）、
        reversal_active_decide（隔日反转激活标记 0/1，决策日坐标）、
        combined_ls（F8 决策树复合多空信号）、close_return（国债期货收盘价日收益，回测标的）。
    """
    futures = load_treasury_future_main(config)   # 全历史（隔日反转结算价 + close_return + 交易日历）
    hs = load_hs300(config)                        # 全历史（扩窗分位，CA-A01）
    panel = build_main_panel(config)               # 主区间对齐面板
    idx = panel.index

    # F1 长短端跷跷板：全历史扩窗三分位算 signal_ls，再对齐主区间。
    seesaw = build_interval_seesaw_signal(hs["close"], config)
    signal_ls = seesaw["signal_ls"].reindex(idx).fillna(0).astype(int)

    # F2 日度信号：逐日单日涨跌触发，主区间 hs300_return 直接生成（无历史窗口）。
    signal_daily_upper = build_daily_signal(panel["hs300_return"], config.daily_upper_threshold)
    signal_daily_lower = build_daily_signal(panel["hs300_return"], config.daily_lower_threshold)
    signal_daily_upper = signal_daily_upper.reindex(idx).fillna(0).astype(int)
    signal_daily_lower = signal_daily_lower.reindex(idx).fillna(0).astype(int)

    # F4 复合信号 signal_seesaw = sign(daily_lower + ls)（复用 combo_composite，不复制）。
    signal_seesaw = build_composite_seesaw_signal(signal_daily_lower, signal_ls).reindex(idx).fillna(0).astype(int)

    # F5 周内信号：全历史交易日判「兑现日(下一交易日)周四」→ 决策日坐标 signal_calendar；
    # 与 signal_daily_upper 叠加取 sign → signal_daily_upper_calendar（AS10 时点对齐）。
    signal_calendar = build_calendar_signal(futures.index, config).reindex(idx).fillna(0).astype(int)
    signal_daily_upper_calendar = build_daily_upper_calendar_signal(
        signal_daily_upper, signal_calendar
    ).reindex(idx).fillna(0).astype(int)

    # F3/AS4 隔日反转：全历史因子日坐标 → 前移 (reversal_lag_days − signal_lag) 天到决策日坐标。
    rev = calculate_reversal_signal(futures, config)
    shift_to_decide = config.reversal_lag_days - config.signal_lag  # =1，见模块 docstring lag 推演
    rev_signal_decide = rev["signal"].shift(shift_to_decide).reindex(idx).fillna(0.0)
    rev_active_decide = rev["active"].shift(shift_to_decide).reindex(idx).fillna(False)

    # F8 三步决策树 → 复合多空信号（决策日坐标）。
    combined_ls = build_final_reversal_position(
        signal_daily_upper_calendar,
        signal_daily_upper,
        rev_signal_decide,
        rev_active_decide,
        signal_seesaw,
    )

    return pd.DataFrame(
        {
            "signal_daily_upper": signal_daily_upper,
            "signal_daily_lower": signal_daily_lower,
            "signal_ls": signal_ls,
            "signal_seesaw": signal_seesaw,
            "signal_calendar": signal_calendar,
            "signal_daily_upper_calendar": signal_daily_upper_calendar,
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

def build_final_backtest(config: Config = CONFIG) -> dict:
    """装配信号并回测最终多空 / 仅做多 / T 基准，返回供 R11/R12 共用的中间结果束。

    多空、仅做多均以 F8 决策树复合信号经 signal_backtest 统一滞后 signal_lag(=1) 回测；
    T 基准取 signal_backtest 的 benchmark_nav（国债期货买入持有，无建仓滞后损耗）。
    """
    signals = assemble_signals(config)
    combined = signals["combined_ls"]
    close_ret = signals["close_return"]

    # 多空：F8 决策树原始 -1/0/+1；仅做多：剔除做空腿（AS2）。
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
# R11 表11：周内+复合+隔日反转业绩（多空/仅做多/T）
# ---------------------------------------------------------------------------

def build_r11_table(bundle: dict, config: Config = CONFIG) -> pd.DataFrame:
    """R11 表11：周内+复合跷跷板+隔日反转（多空/仅做多）+ T 基准，行=指标（复用 R7 结构）。

    多空列即报告落脚点（区间收益/年化/回撤/夏普/卡玛为核心五指标）。指标口径复用 reversal
    的 _directional_win_rates（AS7）与 _stats_column，保证与 R7/R9 逐格同口径。
    """
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
# R12 表12：周内+复合策略分年业绩（区间收益/最大回撤/年化波动率）
# ---------------------------------------------------------------------------

def build_r12_yearly_table(bundle: dict, config: Config = CONFIG) -> pd.DataFrame:
    """R12 表12：周内+复合策略分年业绩（列组 区间收益/最大回撤/年化波动率 × 复合多空/复合仅做多/T）。

    列名与列结构和 spec.md 表12 一致（沿用「复合多空/复合仅做多/T」，与表10 相同）；分年计算
    复用 combo_composite._yearly_stats（整段连续回测日收益按自然年切片，非逐年重建仓），仅表格
    列拼装为本模块布局代码，核心口径不复制。
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
# 运行入口：产 R11 / R12 对照中间产物
# ---------------------------------------------------------------------------

def run_final_strategy(
    config: Config = CONFIG, write_csv: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """回测周内+复合+隔日反转最终策略，产 R11 对照表与 R12 分年业绩表。

    落盘（output/test_v2/results/）：
    - combo_final_stats.csv         R11 对照表（多空/仅做多/T，13 指标行 + 交易日数）
    - combo_final_yearly_stats.csv  R12 分年对照表（9 年 × 9 列）
    - combo_final_signals.csv       决策日信号 + 回测明细（position/nav），供 verifier 画图/审计

    Returns:
        (r11, r12)：R11 对照 DataFrame 与 R12 分年 DataFrame。
    """
    bundle = build_final_backtest(config)
    r11 = build_r11_table(bundle, config)
    r12 = build_r12_yearly_table(bundle, config)

    if write_csv:
        results_dir = config.output_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)

        r11.to_csv(results_dir / "combo_final_stats.csv", encoding="utf-8-sig", float_format="%.6f")
        r12.to_csv(results_dir / "combo_final_yearly_stats.csv", encoding="utf-8-sig", float_format="%.6f")

        detail = bundle["signals"].copy()
        detail["position_ls"] = bundle["ls_bt"]["position"]
        detail["strategy_ret_ls"] = bundle["ls_bt"]["strategy_ret"]
        detail["nav_ls"] = bundle["ls_bt"]["nav"]
        detail["position_lo"] = bundle["lo_bt"]["position"]
        detail["nav_lo"] = bundle["lo_bt"]["nav"]
        detail["benchmark_nav"] = bundle["bench_nav"]
        detail.to_csv(results_dir / "combo_final_signals.csv", encoding="utf-8-sig", float_format="%.6f")

    return r11, r12


def _smoke_report(config: Config = CONFIG) -> None:
    """冒烟自检：打印 R11 五指标 + R12 抽样年份量级，并附备选口径A 的 R11 核心对比。

    仅量级自检、不下通过判定（R11/R12 逐格比对归 verifier 与 check_gates）。
    """
    r11, r12 = run_final_strategy(config, write_csv=True)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 200)

    signals = assemble_signals(config)
    n_thu = int(signals["signal_calendar"].sum())
    n_days = len(signals)

    print("=" * 72)
    print("[test_v2 · m7 冒烟] 周内+复合跷跷板+隔日反转最终策略（F5/F8 → R11/R12，报告落脚点）")
    print(f"主区间(B1第二段): {config.main_start} ~ {config.main_end}；交易日数: {n_days}")
    print(f"周内信号对齐口径: calendar_align_to_settle_day={config.calendar_align_to_settle_day}"
          f"（True=兑现日周四偏多/口径B，AS10）；决策日周内标记天数: {n_thu}")
    print("=" * 72)

    print("\n[R11 周内+复合+隔日反转业绩 · 量级自检（非通过判定）]")
    print(r11.to_string(float_format=lambda x: f"{x:.4f}"))
    print(
        "\n  (spec R11 基准: 多空 区间收益85.22%/年化7.65%/回撤-3.26%/波动3.75%/卡玛2.35/"
        "夏普2.04/胜率56.31%/盈亏1.44/年择时129.48;"
        "\n                仅做多 区间收益51.58%/年化5.10%/回撤-3.72%/夏普1.70/盈亏1.49;"
        " T 区间收益20.78%/年化2.28%/夏普0.59)"
    )

    print("\n[R12 分年业绩 · 抽样量级自检（非通过判定）]")
    print(r12.to_string(float_format=lambda x: f"{x:.4f}"))
    print(
        "\n  (spec R12 复合多空: 2015 区间6.95%/回撤-3.26%/波动5.25%;"
        " 2020 区间10.41%/回撤-2.51%/波动4.23%;"
        "\n                     2023 区间1.56%/回撤-1.81%/波动2.10%;"
        " T 2015 区间3.06%/波动5.33%)"
    )

    # 备选口径A（决策日自身周四，不前移）R11 核心五指标对比——供 verifier 参考，非通过判定。
    if config.calendar_align_to_settle_day:
        from dataclasses import replace

        cfg_a = replace(config, calendar_align_to_settle_day=False)
        bundle_a = build_final_backtest(cfg_a)
        r11_a = build_r11_table(bundle_a, cfg_a)
        core = ["区间收益", "年化收益", "最大回撤", "夏普比率", "卡玛比率"]
        print("\n[备选口径A（决策日周四, 不前移）R11 多空核心五指标对比 · 非通过判定, 供 verifier 参考]")
        print(r11_a[_LS_NAME].reindex(core).to_string(float_format=lambda x: f"{x:.4f}"))

    print(
        "\n说明: 以上为量级自检，非通过判定；R11/R12 逐格比对归 verifier 与 check_gates。"
        f"\n中间产物已落盘: {config.output_dir / 'results'} / combo_final_{{stats,yearly_stats,signals}}.csv"
    )


if __name__ == "__main__":
    _smoke_report()
