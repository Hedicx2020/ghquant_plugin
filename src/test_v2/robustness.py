"""m8 稳健性 / 成交价敏感性 / 费用与附录（要素 B2 / R13 / R14 / SA1 / SA2 / SA3）。

本模块是**最后一个实现里程碑**，不含新策略——只在既有已验证底座（combo_final 的 F8 最终
策略、combo_composite 的 F7 复合策略）之上做汇总/敏感性/附录，产出四张对照 CSV 供 final
verify 与 spec 逐格对比。**不复制任何信号/回测实现**，只 import 组合既有模块与 common 引擎。

DRY 约束（导入复用、不复制）：
- R13 收盘价行/T 行 直接取自 combo_final.build_r11_table（=R11 F8 最终策略指标），与 R11 同源；
- SA1 汇总 combo_composite.build_r10_yearly_table（R10 复合分年）与 combo_final.build_r12_yearly_table
  （R12 周内+复合分年）两张已落地分年表做对照，不重算分年口径；
- R14 月度 = combo_final 的多空/仅做多/T 日收益按自然月切片，口径与 combo_composite._yearly_stats
  完全一致（区间收益=月内 nav 累计、最大回撤=月内 nav 回撤、年化波动率=月内日收益 std×√252），
  仅分组键由「自然年」换成「自然月」（薄聚合，复用 common.utils 指标，非回测引擎）；
- SA3 费用敏感性在 combo_final.assemble_signals 的同一 F8 决策信号上，仅改 common.signal_backtest
  的 cost_bps 参数重跑，不改信号。

————————————————————————————————————————————————————————————
要素口径（本模块唯一权威，取值均反查 spec.md / assumptions.md，无魔法数字）：

[SA1] 分年度子样本稳健性（spec p14/p16）：把 R10（复合，F7）与 R12（周内+复合，F8）按
      2015–2023 逐年拆分对比 区间收益/最大回撤/年化波动率，佐证「引入周内效应后更稳健、
      相对未引入跷跷板前大幅提升」。本模块 build_sa1_yearly_comparison 把两表并列到同一年份轴。

[SA2] 成交价敏感性（spec p16-p17，降级）：研报以 收盘价 / vwap_1/3/5/10（收盘前 X 分钟成交
      均价）分别测算（数值见 R13/表13）。**vwap_X 依赖分钟级数据、本地无**（实测国债期货表
      最细为日频、无任何 vwap/均价列，见 AS11）→ 仅「收盘价」基准可复现，vwap 四档如实标注
      「数据缺失不可复现」，不假装全复现（plan 已裁决降级）。

[SA3] 交易费用影响（spec p16，定性）：研报仅定性「3 元/手、平今仓免费，对不加杠杆策略影响小」，
      **未给计费/不计费对照数值表**。coder 补充费用敏感性（非研报表复现）：把 3 元/手按每手面值
      约 100 万元换算为单边 ≈0.03bp，跑 {0, 0.03, 0.30, 3.00}bp（估算值及 10/100 倍压力）敏感性，
      定量佐证定性结论（口径与全额计费简化见 AS12）。

[B2] 成交价格与交易费用设置（spec p16）：基准以收盘价成交、不计费、不加杠杆。base 成交/费用
     模型即 common.timing_backtest.signal_backtest 的 cost_bps 参数（本模块 SA3 敏感性的入口）；
     成交价降级见 SA2/AS11，费用敏感性见 SA3/AS12。

[R13] 表13 不同成交时间/价格对策略表现的影响（成交时间 × 年化收益/最大回撤/夏普/卡玛/胜率/盈亏比）：
      收盘价行=F8 最终策略多空（同 R11 多空列）、T 行=国债期货买入持有（同 R11 T 列）；vwap_1/3/5/10
      行数据缺失（AS11），本模块 build_r13_close_only 只填收盘价/T 行，vwap 行留 NaN + 复现状态标注。

[R14] 表14 国债期货复合择时策略月度业绩统计（附录，100 个月 2015-04~2023-07；列组 区间收益/
      最大回撤/年化波动率 × 复合多空/复合仅做多/T）。复合策略=F8 最终策略（combo_final，关联要素 F8）。
      本模块用 combo_final 多空/仅做多/T 日收益按自然月切片复现；主区间边缘的 2015-03（03-24 起，
      部分月）与 2023-08（仅 2 交易日，部分月）为自然计算的部分月，落在研报附录 100 月窗口外，一并
      输出（透明，不隐藏数据），供 verifier 按月份标签对齐研报 100 月逐格比对。

防未来函数：本模块不新构造任何信号，全部沿用 combo_final/combo_composite 已通过审计的决策日
坐标信号与 signal_lag=1 回测（隔日反转前移 reversal_lag_days-signal_lag、周内 AS10、跷跷板自然
口径），费用敏感性只改 cost_bps 不改信号时点，无新增前视风险。
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
from src.test_v2.combo_composite import (  # noqa: E402  复用 R10 复合分年表（不重算分年口径）
    _YEARLY_ROWS,
    build_composite_backtest,
    build_r10_yearly_table,
)
from src.test_v2.combo_final import (  # noqa: E402  复用 F8 最终策略回测/信号/R11/R12（不复制）
    _LO_NAME,
    _LS_NAME,
    assemble_signals,
    build_final_backtest,
    build_r11_table,
    build_r12_yearly_table,
)
from src.test_v2.config import CONFIG, Config  # noqa: E402
from src.test_v2.strategy import to_long_only  # noqa: E402  AS2 仅做多（不复制）

# R13 表13 指标列（spec p16 表头顺序；成交时间为行索引）。
_R13_METRICS: tuple[str, ...] = ("年化收益", "最大回撤", "夏普比率", "卡玛比率", "胜率", "盈亏比")


# ---------------------------------------------------------------------------
# SA1 分年稳健性对照（汇总 R10 复合 vs R12 周内+复合）
# ---------------------------------------------------------------------------

def build_sa1_yearly_comparison(config: Config = CONFIG) -> pd.DataFrame:
    """SA1：把 R10（复合 F7）与 R12（周内+复合 F8）分年业绩并列到同一年份轴对照。

    spec SA1（p14/p16）测试设计=复合策略（R10/表10）与周内+复合策略（R12/表12）按 2015–2023
    逐年拆分，对比 区间收益/最大回撤/年化波动率，佐证引入周内效应后更稳健。本函数直接汇总两张
    已落地分年表（R10 多空列、R12 多空列，T 两表同源取其一），不重算分年口径。

    Returns:
        年份索引 DataFrame，每个指标 3 列：{metric}·复合(R10) / {metric}·周内复合(R12) / {metric}·T。
    """
    r10 = build_r10_yearly_table(build_composite_backtest(config), config)   # 复合 F7 分年（多空/仅做多/T）
    r12 = build_r12_yearly_table(build_final_backtest(config), config)       # 周内+复合 F8 分年（多空/仅做多/T）

    out = pd.DataFrame(index=r12.index)
    for metric in _YEARLY_ROWS:
        out[f"{metric}·复合(R10)"] = r10[f"{metric}·复合多空"]
        out[f"{metric}·周内复合(R12)"] = r12[f"{metric}·复合多空"]
        out[f"{metric}·T"] = r12[f"{metric}·T"]  # T 基准两表同源（同主区间买入持有）
    out.index.name = "年份"
    return out


# ---------------------------------------------------------------------------
# SA2 / R13 成交价敏感性（降级：仅收盘价基准 + T 可复现，vwap 档数据缺失）
# ---------------------------------------------------------------------------

def build_r13_close_only(config: Config = CONFIG) -> pd.DataFrame:
    """R13 表13：不同成交时间对策略表现的影响——降级为仅收盘价/T 可复现（SA2，AS11）。

    收盘价行=F8 最终策略多空（直接取自 R11 多空列，与 R11 同源，不重算）；T 行=国债期货买入
    持有（R11 的 T 列）。vwap_1/3/5/10 行依赖收盘前 X 分钟成交均价（分钟数据，本地无，AS11）→
    留 NaN，「复现状态」列标注「数据缺失不可复现」，如实暴露部分复现范围（不假装全复现）。

    Returns:
        成交时间索引 DataFrame，列=R13 指标 6 列 + 「复现状态」；
        行顺序 收盘价 / vwap_1/3/5/10 / T（与 spec 表13 一致）。
    """
    r11 = build_r11_table(build_final_backtest(config), config)   # 复用 R11（不重算 F8 最终策略指标）
    close_row = r11[_LS_NAME].reindex(_R13_METRICS)               # 收盘价=F8 多空（同 R11 多空列）
    t_row = r11["T"].reindex(_R13_METRICS)                        # T=买入持有（同 R11 T 列）

    rows: dict[str, dict] = {}
    rows["收盘价"] = {**close_row.to_dict(), "复现状态": "可复现(=R11最终策略多空/收盘价成交)"}
    for name in config.missing_exec_prices:                       # vwap_1/3/5/10：数据缺失
        rows[name] = {m: np.nan for m in _R13_METRICS}
        rows[name]["复现状态"] = "数据缺失不可复现(本地无分钟vwap_X, AS11)"
    rows["T"] = {**t_row.to_dict(), "复现状态": "可复现(国债期货买入持有基准)"}

    out = pd.DataFrame(rows).T.reindex(columns=[*_R13_METRICS, "复现状态"])
    out.index.name = "成交时间"
    return out


# ---------------------------------------------------------------------------
# SA3 交易费用敏感性（3元/手 换算 + 压力倍数，佐证「影响小」定性结论，AS12）
# ---------------------------------------------------------------------------

def _estimated_cost_bps(config: Config = CONFIG) -> float:
    """由 B2「3 元/手」÷ 每手面值(约100万元) 换算单边交易成本（bp）。

    3 元 / 1,000,000 元 = 3e-6 = 0.03bp（单边）。换算与全额计费简化见 AS12。
    """
    return config.future_fee_per_lot_yuan / config.future_contract_face_value_yuan * 1e4


def build_cost_sensitivity(config: Config = CONFIG) -> pd.DataFrame:
    """SA3：F8 最终策略在不同单边交易成本(bp)下的业绩敏感性（多空口径）。

    在 combo_final.assemble_signals 的同一 F8 决策信号上，仅改 signal_backtest 的 cost_bps
    重跑（信号时点不变）。成本档=由 3元/手 换算的单边 bp 估算值 × config.cost_bps_stress_multiples
    （0=基准不计费 / 1=估算实际≈0.03bp / 10/100=压力），定量佐证「费用对不加杠杆策略影响小」。
    平今仓免费未逐笔精确建模、按全额换手计费（保守高估费用，见 AS12）。

    Returns:
        成本档索引 DataFrame，列：cost_bps / 区间收益 / 年化收益 / Δ年化(vs基准) /
        最大回撤 / 夏普比率 / 胜率 / 盈亏比 / 年择时次数。
    """
    signals = assemble_signals(config)
    combined = signals["combined_ls"]
    close_ret = signals["close_return"]
    est_bps = _estimated_cost_bps(config)

    rows: dict[str, dict] = {}
    base_annual: float | None = None
    for mult in config.cost_bps_stress_multiples:
        cb = est_bps * mult
        bt = signal_backtest(combined, close_ret, cost_bps=cb, lag=config.signal_lag)
        m = timing_metrics(bt["nav"], bt["position"], bt["benchmark_nav"], config.periods_per_year)
        if mult == 0.0:
            base_annual = m["annual_return"]
        label = (
            "不计费(基准)" if mult == 0.0
            else f"3元/手估算×{mult:g}({cb:.3f}bp)"
        )
        rows[label] = {
            "cost_bps": cb,
            "区间收益": m["cumulative_return"],
            "年化收益": m["annual_return"],
            "Δ年化(vs基准)": m["annual_return"] - (base_annual if base_annual is not None else m["annual_return"]),
            "最大回撤": -m["max_drawdown"],
            "夏普比率": m["sharpe"],
            "胜率": m["win_rate"],
            "盈亏比": m["profit_loss_ratio"],
            "年择时次数": m["annual_trade_count"],
        }
    out = pd.DataFrame(rows).T
    out.index.name = "成本档"
    return out


# ---------------------------------------------------------------------------
# R14 月度业绩附录（combo_final 多空/仅做多/T 按自然月切片）
# ---------------------------------------------------------------------------

def _monthly_stats(daily_ret: pd.Series, config: Config = CONFIG) -> pd.DataFrame:
    """把整段连续回测日收益按自然月切片，算 区间收益/最大回撤/年化波动率。

    口径与 combo_composite._yearly_stats 完全一致（仅分组键 自然年→自然月）：
    - 区间收益 = 月内 nav 累计 (1+ret).prod()-1
    - 最大回撤 = 月内 nav 最大回撤（转负值展示，对齐研报表14 符号）
    - 年化波动率 = 月内日收益 std × √periods_per_year（复用 common.utils）
    分组用 PeriodIndex('M') 保证时间升序；月份标签「YYYY年M月」对齐 spec 表14 行名。
    """
    ret = pd.Series(daily_ret).dropna()
    rows: dict[str, dict[str, float]] = {}
    for period, grp in ret.groupby(ret.index.to_period("M")):
        nav = (1.0 + grp).cumprod()
        rows[f"{period.year}年{period.month}月"] = {
            "区间收益": float(nav.iloc[-1] - 1.0),
            "最大回撤": -calculate_max_drawdown(nav),
            "年化波动率": calculate_annualized_volatility(grp, config.periods_per_year),
        }
    return pd.DataFrame(rows).T.reindex(columns=list(_YEARLY_ROWS))


def build_r14_monthly(config: Config = CONFIG) -> pd.DataFrame:
    """R14 表14：F8 最终策略月度业绩（列组 区间收益/最大回撤/年化波动率 × 复合多空/复合仅做多/T）。

    复合策略=combo_final 的 F8 最终策略（关联要素 F8）；分年表 R12 的月度版，列结构一致（9 列）。
    输出含主区间全部自然月（含边缘部分月 2015-03/2023-08，落在研报 100 月窗口外，供对齐时忽略）。
    """
    bundle = build_final_backtest(config)
    ls_m = _monthly_stats(bundle["ls_bt"]["strategy_ret"], config)
    lo_m = _monthly_stats(bundle["lo_bt"]["strategy_ret"], config)
    t_m = _monthly_stats(bundle["close_ret"], config)

    out = pd.DataFrame(index=ls_m.index)
    for metric in _YEARLY_ROWS:
        out[f"{metric}·复合多空"] = ls_m[metric]
        out[f"{metric}·复合仅做多"] = lo_m[metric]
        out[f"{metric}·T"] = t_m[metric]
    out.index.name = "月份"
    return out


# ---------------------------------------------------------------------------
# 运行入口：产 SA1/R13/R14/SA3 四张对照中间产物
# ---------------------------------------------------------------------------

def run_robustness(
    config: Config = CONFIG, write_csv: bool = True
) -> dict[str, pd.DataFrame]:
    """跑 m8 全部稳健性/敏感性/附录，产四张对照 CSV。

    落盘（output/test_v2/results/）：
    - robustness_yearly.csv    SA1 分年稳健性对照（R10 复合 vs R12 周内+复合 vs T）
    - r13_close_only.csv       R13 成交价影响（收盘价/T 可复现 + vwap 缺失标注，SA2 降级）
    - monthly_returns_r14.csv  R14 月度业绩附录（F8 最终策略，供 R14 逐格对比）
    - cost_sensitivity.csv     SA3 交易费用敏感性（3元/手 换算 + 压力倍数）

    Returns:
        dict：{"sa1_yearly", "r13", "r14_monthly", "cost_sensitivity"} → 对应 DataFrame。
    """
    sa1 = build_sa1_yearly_comparison(config)
    r13 = build_r13_close_only(config)
    r14 = build_r14_monthly(config)
    cost = build_cost_sensitivity(config)

    if write_csv:
        results_dir = config.output_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        sa1.to_csv(results_dir / "robustness_yearly.csv", encoding="utf-8-sig", float_format="%.6f")
        r13.to_csv(results_dir / "r13_close_only.csv", encoding="utf-8-sig", float_format="%.6f")
        r14.to_csv(results_dir / "monthly_returns_r14.csv", encoding="utf-8-sig", float_format="%.6f")
        cost.to_csv(results_dir / "cost_sensitivity.csv", encoding="utf-8-sig", float_format="%.6f")

    return {"sa1_yearly": sa1, "r13": r13, "r14_monthly": r14, "cost_sensitivity": cost}


def _smoke_report(config: Config = CONFIG) -> None:
    """冒烟自检：打印 SA1/R13/R14 抽样与 SA3 敏感性量级（不下通过判定，判定归 verifier）。"""
    out = run_robustness(config, write_csv=True)
    pd.set_option("display.unicode.east_asian_width", True)
    pd.set_option("display.width", 220)

    print("=" * 76)
    print("[test_v2 · m8 冒烟] 稳健性/成交价敏感性/费用与附录（SA1/SA2/SA3/B2/R13/R14）")
    print(f"主区间(B1第二段): {config.main_start} ~ {config.main_end}")
    print("=" * 76)

    print("\n[SA1 分年稳健性对照 · R10 复合 vs R12 周内+复合（多空）· 抽样非通过判定]")
    print(out["sa1_yearly"].to_string(float_format=lambda x: f"{x:.4f}"))

    print("\n[R13 成交价影响 · SA2 降级：仅收盘价/T 可复现，vwap 档数据缺失（非通过判定）]")
    print(out["r13"].to_string(float_format=lambda x: f"{x:.4f}"))
    print("  (spec R13 收盘价: 年化7.65%/回撤-3.26%/夏普2.04/卡玛2.35/胜率56.31%/盈亏1.44;"
          " T: 2.28%/-7.46%/0.59/0.31/--/1.11; vwap_1/3/5/10 本地无分钟数据不可复现)")

    r14 = out["r14_monthly"]
    n_report_window = r14.loc[[i for i in r14.index if i not in ("2015年3月", "2023年8月")]]
    print(f"\n[R14 月度业绩附录 · 共 {len(r14)} 个自然月（研报附录窗口 2015-04~2023-07 应为 100 月）]")
    sample_idx = ["2015年4月", "2015年5月", "2018年12月", "2020年6月", "2023年7月"]
    sample = r14.reindex([i for i in sample_idx if i in r14.index])
    print("  抽样（首月/次月/中间/中间/末月）:")
    print(sample.to_string(float_format=lambda x: f"{x:.4f}"))
    print("  (spec R14 抽样 复合多空 区间收益: 2015年4月 -0.62% / 2015年5月 0.49% /"
          " 2020年6月 1.01% / 2023年7月 1.46%)")
    print(f"  研报 100 月窗口内计得 {len(n_report_window)} 月；边缘部分月 "
          f"{[i for i in r14.index if i in ('2015年3月', '2023年8月')]} 在窗口外")

    print("\n[SA3 交易费用敏感性 · 3元/手换算+压力倍数（非通过判定）]")
    print(f"  单边 bp 估算: 3元/手 ÷ 面值{config.future_contract_face_value_yuan:.0f}元 = "
          f"{_estimated_cost_bps(config):.4f}bp")
    print(out["cost_sensitivity"].to_string(float_format=lambda x: f"{x:.4f}"))

    print(
        "\n说明: 以上为量级自检，非通过判定；SA1/R13/R14 逐格比对归 verifier 与 check_gates；"
        "\nR13 vwap 档与 SA2 vwap 敏感性因分钟数据缺失降级不可复现（AS11），如实标注。"
        f"\n中间产物已落盘: {config.output_dir / 'results'} / "
        "{robustness_yearly, r13_close_only, monthly_returns_r14, cost_sensitivity}.csv"
    )


if __name__ == "__main__":
    _smoke_report()
