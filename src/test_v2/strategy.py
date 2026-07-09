"""策略/信号构造（test_v2）。

本文件承载研报特定的信号逻辑（F1–F8）。通用回测内核在 common/timing_backtest.py，
不在此重复实现。

里程碑边界：
- m2（本文件已落地）: F1 长短端跷跷板 build_interval_seesaw_signal、F2 日度
  build_daily_signal；R1 细分胜率 directional_win_rates；R2/R3/R4 日度效应统计
  daily_seesaw_effect_stats；AS2 仅做多口径 to_long_only。
- m4: F3 隔日反转 build_reversal_signal（chg_t 口径 AS4，T-2 结算价涨跌幅）——
  占位保留，由 m4 在独立 reversal 文件从公式独立编写（禁引用旧代码路径）。
- m5/m6/m7: F6/F4/F7/F5/F8 决策树与复合/周内信号。

跨里程碑复用基元 signed_signal。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.test_v2.config import CONFIG, Config


def signed_signal(values: pd.Series | np.ndarray) -> pd.Series:
    """符号函数：返回整数 -1/0/+1（NaN 视作 0）。

    多处信号合成（F1 的 sign(长+短)、F4 的 sign(daily_lower+ls)、F5 的
    sign(daily_upper+calendar)）均以此为基元。
    """
    series = pd.Series(values)
    return np.sign(series.fillna(0.0)).astype(int)


def to_long_only(signal: pd.Series) -> pd.Series:
    """AS2：仅做多 = 剔除做空腿（看空 -1 → 空仓 0），保留看多 +1。

    各业绩表「仅做多」列口径（A3 auto 裁决 AS2）：long-only 即剔除做空腿，
    看空信号时持币空仓，仅看多时持多仓。
    """
    return pd.Series(signal).clip(lower=0).astype(int)


# ---------------------------------------------------------------------------
# F1 长短端股债跷跷板国债期货择时（消费全历史沪深300序列，CA-A01）
# ---------------------------------------------------------------------------

def _interval_return(close: pd.Series, window: int) -> pd.Series:
    """过去 window 个交易日区间涨跌幅 chg_T^N = close_T / close_{T-N} − 1。"""
    return close / close.shift(window) - 1.0


def _expanding_tercile_signal(
    chg: pd.Series,
    base_date: str,
    q_lower: float,
    q_upper: float,
) -> pd.DataFrame:
    """单窗口：基日以来扩窗三分位 → 择时信号。

    CA-A01：``chg`` 必须来自 **全历史** 沪深300序列，不得用被截断到主区间的面板列，
    否则扩窗分位样本被腰斩、上下轨位置错位。

    口径（spec F1，「沪深300 基日以来至 T 日 chg_t^N 的上/下三分之一分位点」）：
    - upper_bound = 基日以来（含当日 T）chg 的上 1/3 分位（q_upper=2/3 分位点）
    - lower_bound = 下 1/3 分位（q_lower=1/3 分位点）
    - chg > upper_bound（股市偏牛）→ T 日收盘做空国债期货，信号 −1
    - chg < lower_bound（股市偏熊）→ T 日收盘做多国债期货，信号 +1
    - chg ∈ [lower_bound, upper_bound]（含边界）→ 平仓，信号 0

    分位含当日值系 spec「至 T 日」明确口径（当日区间涨跌幅在当日收盘即可知）；信号
    在 T 日收盘生成、经回测引擎 lag=1 于 T+1 执行，无未来函数。min_periods=1 对应
    spec「基日以来」的全量扩窗语义（主区间 2015 起已累积逾十年样本，早期不稳区间
    远在主区间之前）。
    """
    chg = pd.Series(chg)
    chg = chg.loc[chg.index >= pd.Timestamp(base_date)].dropna()
    upper = chg.expanding(min_periods=1).quantile(q_upper)
    lower = chg.expanding(min_periods=1).quantile(q_lower)

    signal = pd.Series(0, index=chg.index, dtype=int)
    signal[chg > upper] = -1
    signal[chg < lower] = 1

    return pd.DataFrame(
        {"chg": chg, "lower_bound": lower, "upper_bound": upper, "signal": signal}
    )


def build_interval_seesaw_signal(
    hs300_close: pd.Series,
    config: Config = CONFIG,
) -> pd.DataFrame:
    """F1：长短端股债跷跷板国债期货择时信号（长端 N_l=120 / 短端 N_s=20）。

    Args:
        hs300_close: index=date 的沪深300收盘价 **全历史** 序列（load_hs300()["close"]），
            用于「基日以来扩窗三分位」（CA-A01）；严禁传入被截断到主区间的面板列。
        config: 参数（long_window / short_window / quantile_lower / quantile_upper /
            seesaw_base_date）。

    Returns:
        index=date（基日以来）DataFrame，列：
        signal_long / signal_short（长/短端信号 −1/0/1）、
        signal_ls（长短端合成信号 sign(长+短)，spec F1 主策略）、
        chg_long / chg_short（长/短端区间涨跌幅）、
        long_lower / long_upper / short_lower / short_upper（各扩窗上下轨，供画图/审计）。
    """
    close = pd.Series(hs300_close).sort_index()

    long = _expanding_tercile_signal(
        _interval_return(close, config.long_window),
        config.seesaw_base_date, config.quantile_lower, config.quantile_upper,
    )
    short = _expanding_tercile_signal(
        _interval_return(close, config.short_window),
        config.seesaw_base_date, config.quantile_lower, config.quantile_upper,
    )

    idx = long.index.union(short.index)
    signal_long = long["signal"].reindex(idx).fillna(0).astype(int)
    signal_short = short["signal"].reindex(idx).fillna(0).astype(int)
    signal_ls = signed_signal(signal_long + signal_short)

    return pd.DataFrame(
        {
            "signal_long": signal_long,
            "signal_short": signal_short,
            "signal_ls": signal_ls,
            "chg_long": long["chg"].reindex(idx),
            "chg_short": short["chg"].reindex(idx),
            "long_lower": long["lower_bound"].reindex(idx),
            "long_upper": long["upper_bound"].reindex(idx),
            "short_lower": short["lower_bound"].reindex(idx),
            "short_upper": short["upper_bound"].reindex(idx),
        }
    )


# ---------------------------------------------------------------------------
# F2 日度级别股债跷跷板信号（signal_daily）
# ---------------------------------------------------------------------------

def build_daily_signal(hs300_return: pd.Series, threshold: float) -> pd.Series:
    """F2：日度级别股债跷跷板信号（单阈值）。

    口径（spec F2）：股市单日涨跌幅绝对值触发阈值 → 下一交易日反方向操作国债期货：
    - r ≥ +threshold（大涨）→ 下一交易日做空国债期货，信号 −1
    - r ≤ −threshold（大跌）→ 下一交易日做多国债期货，信号 +1
    - 否则 → 0（不操作）

    信号在 T 日（沪深300 单日涨跌确定）生成，经回测引擎 lag=1 于「下一交易日」T+1
    执行，无未来函数。signal_daily_upper 取 threshold=daily_upper_threshold(±5%)、
    signal_daily_lower 取 daily_lower_threshold(±3%)（AS1）。

    Args:
        hs300_return: index=date 沪深300单日涨跌幅（decimal，如 0.05=5%）。
        threshold: 触发阈值（decimal 正数）。
    """
    r = pd.Series(hs300_return)
    signal = pd.Series(0, index=r.index, dtype=int)
    signal[r >= threshold] = -1
    signal[r <= -threshold] = 1
    return signal


# ---------------------------------------------------------------------------
# R1 细分胜率（持仓日 / 看多 / 看空口径）
# ---------------------------------------------------------------------------

def directional_win_rates(position: pd.Series, strategy_ret: pd.Series) -> dict:
    """R 表细分胜率：持仓日总胜率 / 看多胜率 / 看空胜率。

    以回测引擎输出的实际生效仓位 position 与扣费后策略收益 strategy_ret 为准：
    - 看多胜率 = 持多仓日（position > 0）中 strategy_ret > 0 的占比（多头方向对=标的涨）
    - 看空胜率 = 持空仓日（position < 0）中 strategy_ret > 0 的占比（空头方向对=标的跌，
      此时 strategy_ret = −标的收益 > 0）
    - 胜率 = 持仓日（position ≠ 0）中 strategy_ret > 0 的占比，与 timing_metrics.win_rate 同义

    Returns:
        dict：win_rate / long_win_rate / short_win_rate（无对应持仓日则为 np.nan）。
    """
    pos = pd.Series(position)
    ret = pd.Series(strategy_ret).reindex(pos.index)

    def _wr(mask: pd.Series) -> float:
        sub = ret[mask]
        return float((sub > 0).mean()) if len(sub) else float("nan")

    return {
        "win_rate": _wr(pos.ne(0)),
        "long_win_rate": _wr(pos.gt(0)),
        "short_win_rate": _wr(pos.lt(0)),
    }


# ---------------------------------------------------------------------------
# R2/R3/R4 日度级别股债跷跷板效应统计（效应存在性证据表，非策略回测）
# ---------------------------------------------------------------------------

def daily_seesaw_effect_stats(
    hs300_return: pd.Series,
    future_next_return: pd.Series,
    thresholds: tuple[float, ...] = CONFIG.daily_effect_thresholds,
) -> pd.DataFrame:
    """R2/R3/R4：15 档阈值 × 3 组的胜率/赔率/平均涨跌幅/天数比例效应统计。

    对每档阈值 t 与每组分桶（沪深300 单日涨跌幅 r 落桶），统计其「下一交易日」国债
    期货涨跌幅 f 的分布。口径重建见 AS6（spec 仅给结果表、未逐字给统计式，经 spec
    表格 0%档=100%、5%档天数比例交叉验证反推）：

    分组与桶定义：
    - 绝对值组: |r| ≥ t；天数比例分母 = 全样本天数 N_total
    - 正(涨)组: r ≥ t；天数比例分母 = 上涨样本天数 count(r ≥ 0)
    - 负(跌)组: r ≤ −t；天数比例分母 = 下跌样本天数 count(r ≤ 0)

    每桶统计（桶内 next-day 国债期货涨跌幅 f）：
    - win_rate（R2 胜率）= sign(r)·sign(f) < 0（股债符号相反=跷跷板方向对）的桶内占比
    - odds（R3 赔率）= 国债期货 sum 口径盈亏比（spec「国债期货上涨/下跌的盈亏比」，经 spec
      表格逐格反推为 sum 总额比、非均值比）：绝对值组/负(跌)组 = sum(f>0)/|sum(f<0)|（上涨
      总额/下跌总额）；正(涨)组 = |sum(f<0)|/sum(f>0)（股市涨、跷跷板利在债跌，取下跌/上涨）
    - avg_chg（R4 平均涨跌幅）= mean(f)（原始 next-day 带符号平均，不施加操作方向）
    - day_ratio（天数比例）= 桶内天数 / 该组分母

    Args:
        hs300_return: index=date 沪深300单日涨跌幅（T 日，decimal）。
        future_next_return: index=date 国债期货 **下一交易日** 涨跌幅（已 shift(-1) 对齐到 T，
            收盘价口径 decimal）。
        thresholds: 阈值档位（decimal），默认 config.daily_effect_thresholds（15 档）。

    Returns:
        长表 DataFrame，列：threshold, group(abs/pos/neg), win_rate, odds, avg_chg,
        day_ratio, n（桶内样本数）。供 final verify pivot 后逐格对照 spec R2/R3/R4。
    """
    paired = pd.concat(
        {"r": pd.Series(hs300_return), "f": pd.Series(future_next_return)}, axis=1
    ).dropna()
    r = paired["r"].to_numpy()
    f = paired["f"].to_numpy()

    n_total = len(paired)
    n_pos = int((r >= 0).sum())
    n_neg = int((r <= 0).sum())

    def _odds(fb: np.ndarray, group: str) -> float:
        # 赔率=国债期货 sum 口径盈亏比（spec「国债期货上涨/下跌的盈亏比」，经 spec 表格
        # 逐格反推为 sum 总额比、非均值比）：绝对值/负(跌)组=上涨总额/下跌总额；正(涨)组
        # 股市涨、跷跷板利在债跌 → 取下跌总额/上涨总额（即 abs/neg 公式的倒数）。
        up = fb[fb > 0].sum()
        dn = -fb[fb < 0].sum()
        if up <= 0 or dn <= 0:
            return float("nan")
        return float(dn / up) if group == "pos" else float(up / dn)

    rows: list[dict] = []
    for t in thresholds:
        for group, mask, denom in (
            ("abs", np.abs(r) >= t, n_total),
            ("pos", r >= t, n_pos),
            ("neg", r <= -t, n_neg),
        ):
            fb = f[mask]
            rb = r[mask]
            k = int(mask.sum())
            if k == 0:
                rows.append({
                    "threshold": t, "group": group, "win_rate": float("nan"),
                    "odds": float("nan"), "avg_chg": float("nan"),
                    "day_ratio": 0.0, "n": 0,
                })
                continue
            rows.append({
                "threshold": t,
                "group": group,
                "win_rate": float((np.sign(rb) * np.sign(fb) < 0).mean()),
                "odds": _odds(fb, group),
                "avg_chg": float(fb.mean()),
                "day_ratio": float(k / denom) if denom else float("nan"),
                "n": k,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 后续里程碑入口（本轮不实现，立骨架防越界；reversal 由 m4 在独立文件落地）
# ---------------------------------------------------------------------------

def build_reversal_signal(*args, **kwargs):  # noqa: D401
    """F3 隔日反转因子 chg_t 信号（口径 AS4，T-2 结算价涨跌幅）。TODO(m4)。"""
    raise NotImplementedError("F3 隔日反转信号在 m4 实现（从 AS4 公式独立编写）")
