"""m6 全链装配主程序 · ssrn_6115073（市场迁移复现 experimental）。

串起 m1→m6 端到端：数据准备 → Δβ 选股 → 聚类 → 两阶段 pattern matching → DY 溢出加权
每簇选股 → 组合构建（EW/MV）与 11 方法回测，产出：
  - ``output/ssrn_6115073/results/r1_main_results.xlsx``  R1/表2 六比率×11方法×3市场 + 补充表
  - ``output/ssrn_6115073/results/cumulative_returns_*.png``  R5/图9-10 累计收益
  - allocation 必需 5 图（weight_evolution/portfolio_nav/asset_contribution/rolling_volatility/drawdown）

运行：``uv run python -m src.ssrn_6115073.main``（端到端；不宣布验证/达标结论——归 verify）。

市场迁移下数值对齐豁免，R1/R5 作 CPMM 系列 vs 消融/基准的**定性**领先性对照（plan §九）。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from src.ssrn_6115073.config import MARKET_NAMES_CN, PRIMARY_MARKET
from src.ssrn_6115073.data_prep import prepare_all
from src.ssrn_6115073.selection import run_selection
from src.ssrn_6115073.clustering import run_clustering
from src.ssrn_6115073.pattern_matching import run_pattern_matching
from src.ssrn_6115073.spillover import run_spillover, spillover_table_frame
from src.ssrn_6115073.portfolio import (
    ALL_MODELS,
    COST_BPS_FRICTIONLESS,
    COST_BPS_STRESS,
    build_extra_table,
    build_r1_table,
    cumulative_returns,
    portfolio_backtest,
    run_portfolio,
)

# 配色与样式（CLAUDE.md：蓝#1f77b4=主模型/正收益，红#d62728=对比/负收益，whitegrid，中文）
BLUE = "#1f77b4"
RED = "#d62728"
sns.set_style("whitegrid")
plt.rcParams["font.sans-serif"] = ["Songti SC", "Heiti TC", "STHeiti", "PingFang SC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 300

RESULTS_DIR = Path("output/ssrn_6115073/results")
# 每行最优方向：越大越优 / 越小越优（AStd/MDD/VaR）——R1 加粗最优（对齐原文"加粗最高"语义，
# 但对风险类指标方向感知取最小，避免误导；登记 AS56）
LOWER_BETTER = {"AStd", "MDD", "VaR"}


# ---------------------------------------------------------------------------
# 全链装配
# ---------------------------------------------------------------------------

def build_and_run(cost_bps: float = COST_BPS_FRICTIONLESS):
    """端到端跑 m1→m6，返回 (prep, sel, clus, sig, sp, ports)。"""
    prep = prepare_all()
    sel = run_selection(prep)
    clus = run_clustering(prep, sel)
    sig = run_pattern_matching(prep, sel)
    sp = run_spillover(prep, sel, clus, sig)
    ports = run_portfolio(prep, sel, clus, sig, sp, cost_bps=cost_bps)
    return prep, sel, clus, sig, sp, ports


# ---------------------------------------------------------------------------
# Excel（R1 主结果 + 补充 + 明细 + R4 溢出 + 含成本对比）
# ---------------------------------------------------------------------------

def _format_ws(ws, bold_optima: bool = False, ratio_col: str = "指标") -> None:
    """冻结首行 + 表头加粗 + 自动列宽（中文按 2 宽计）；可选按行加粗最优值。"""
    ws.freeze_panes = "A2"
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        width = 0
        for cell in col:
            v = "" if cell.value is None else str(cell.value)
            w = sum(2 if ord(ch) > 127 else 1 for ch in v)
            width = max(width, w)
        ws.column_dimensions[letter].width = min(width + 3, 40)
    if bold_optima:                    # 每行在模型列间加粗最优（方向感知）
        headers = [c.value for c in ws[1]]
        model_cols = [i for i, h in enumerate(headers) if h in ALL_MODELS]
        ridx = headers.index(ratio_col) if ratio_col in headers else None
        for row in ws.iter_rows(min_row=2):
            ratio = row[ridx].value if ridx is not None else ""
            vals = [(i, row[i].value) for i in model_cols
                    if isinstance(row[i].value, (int, float)) and not pd.isna(row[i].value)]
            if not vals:
                continue
            best = min(vals, key=lambda kv: kv[1]) if ratio in LOWER_BETTER else max(vals, key=lambda kv: kv[1])
            row[best[0]].font = Font(bold=True)


def _detail_table(ports) -> pd.DataFrame:
    """各市场 × 各模型的全指标明细（AR/AStd/SR/PSR/SOR/MR/MDD/VaR/累计/换手）。"""
    rows = []
    for market, mp in ports.items():
        for model in ALL_MODELS:
            mr = mp.models.get(model)
            if mr is None:
                continue
            m = mr.metrics
            rows.append({
                "市场": MARKET_NAMES_CN.get(market, market), "方法": model,
                "tier": mp.regime_tier,
                "AR": round(m.get("AR", np.nan), 4), "AStd": round(m.get("AStd", np.nan), 4),
                "SR": round(m.get("SR", np.nan), 4), "PSR": round(m.get("PSR", np.nan), 4),
                "SOR": round(m.get("SOR", np.nan), 4), "MR": round(m.get("MR", np.nan), 4),
                "MDD": round(m.get("MDD", np.nan), 4), "VaR": round(m.get("VaR", np.nan), 4),
                "累计收益": round(m.get("cum_return", np.nan), 4),
                "平均换手": round(m.get("avg_turnover", np.nan), 4) if not pd.isna(m.get("avg_turnover", np.nan)) else np.nan,
                "调仓次数": mr.n_rebalance,
            })
    return pd.DataFrame(rows)


def _cost_compare(prep, ports) -> pd.DataFrame:
    """含成本档对比（AS5）：主模型 CPMM-EW/MV 用已选权重重回测 cost_bps=40，对比无摩擦 SR/累计。"""
    rows = []
    for market, mp in ports.items():
        md = prep.markets[market]
        for model in ("CPMM-EW", "CPMM-MV"):
            mr = mp.models.get(model)
            if mr is None or mr.weights_panel.empty:
                continue
            bt_c = portfolio_backtest(mr.weights_panel, md.stock_returns, cost_bps=COST_BPS_STRESS)
            pr_c = bt_c["port_return"]
            nav_c = bt_c["nav"]
            rows.append({
                "市场": MARKET_NAMES_CN.get(market, market), "方法": model,
                "无摩擦_累计": round(mr.metrics.get("cum_return", np.nan), 4),
                "含成本40bp_累计": round(float(nav_c.iloc[-1] - 1.0) if len(nav_c) else np.nan, 4),
                "无摩擦_年化": round(mr.metrics.get("AR", np.nan), 4),
                "含成本40bp_年化": round(float(pr_c.mean() * 12) if len(pr_c) else np.nan, 4),
                "平均换手": round(mr.metrics.get("avg_turnover", np.nan), 4),
            })
    return pd.DataFrame(rows)


def _mode_note() -> pd.DataFrame:
    """复现模式说明（实验模式：迁移市场定性验证，偏差列豁免）。"""
    return pd.DataFrame({
        "项目": ["复现模式", "原文市场", "迁移目标", "回测区间", "数值对齐",
                 "成功判据", "本表性质", "偏差列说明"],
        "说明": [
            "experimental（市场迁移复现）",
            "美股 S&P500/DJI + 日股 N225 + FRED 美国宏观（本地全不可得）",
            "A股 沪深300/上证50/中证500 + 中国宏观等价替代",
            "训练 2007-2018 定窗口 w/簇数 nc；测试 2019-2024 评估",
            "豁免——实验模式：迁移市场定性验证，不追平原文数值",
            "方法是否成立（CPMM-EW 是否领先消融 CPM/PMM/EWMFM 与外部基准），非数值对齐",
            "coder 冒烟端到端产出；达标/领先判定归 verify/diagnoser，本表不含结论",
            "实验模式无「研报值 vs 复现值 vs 偏差」偏差列（原文数值对齐整体豁免）",
        ],
    })


def save_excel(prep, ports, sp, path: Path) -> None:
    """写主工作簿 backtest_summary.xlsx：说明 / R1 主结果 / 补充 / 明细 / R4 溢出 / 含成本对比。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    note = _mode_note()
    r1 = build_r1_table(ports)
    extra = build_extra_table(ports)
    detail = _detail_table(ports)
    factors = list(prep.macro.selected_factors)
    r4 = spillover_table_frame(sp, factors)
    cost = _cost_compare(prep, ports)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        note.to_excel(writer, sheet_name="复现模式说明", index=False)
        r1.to_excel(writer, sheet_name="R1_表2主结果", index=False)
        extra.to_excel(writer, sheet_name="补充_累计收益风险", index=False)
        detail.to_excel(writer, sheet_name="各市场模型明细", index=False)
        r4.to_excel(writer, sheet_name="R4_宏观溢出强度", index=False)
        cost.to_excel(writer, sheet_name="含成本档对比", index=False)
        _format_ws(writer.sheets["复现模式说明"])
        _format_ws(writer.sheets["R1_表2主结果"], bold_optima=True)
        _format_ws(writer.sheets["补充_累计收益风险"], bold_optima=True)
        _format_ws(writer.sheets["各市场模型明细"])
        _format_ws(writer.sheets["R4_宏观溢出强度"])
        _format_ws(writer.sheets["含成本档对比"])
    print(f"[Excel] 已写 {path}")


# ---------------------------------------------------------------------------
# 图表（R5 累计收益 + allocation 必需 5 图）
# ---------------------------------------------------------------------------

def _fig_cumulative_single(mp, market: str, path: Path) -> None:
    """R5/图9：单市场各模型累计收益曲线（CPMM-EW 蓝色加粗突出）。"""
    cum = cumulative_returns(mp)
    if cum.empty:
        return
    fig, ax = plt.subplots(figsize=(12, 6))
    palette = plt.cm.tab20(np.linspace(0, 1, len(ALL_MODELS)))
    for i, model in enumerate(ALL_MODELS):
        if model not in cum.columns:
            continue
        if model == "CPMM-EW":
            ax.plot(cum.index, cum[model], color=BLUE, lw=2.6, label=model, zorder=5)
        elif model == "CPMM-MV":
            ax.plot(cum.index, cum[model], color=RED, lw=2.2, label=model, zorder=4)
        else:
            ax.plot(cum.index, cum[model], color=palette[i], lw=1.1, alpha=0.8, label=model)
    ax.set_title(f"各模型累计收益（{MARKET_NAMES_CN.get(market, market)}，测试期）", fontsize=14)
    ax.set_xlabel("时间", fontsize=12)
    ax.set_ylabel("累计收益（%）", fontsize=12)
    ax.legend(fontsize=9, ncol=3, loc="upper left")
    ax.axhline(0, color="gray", lw=0.8, ls="--")
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _fig_cumulative_markets(ports, path: Path) -> None:
    """R5/图10：三市场 CPMM-EW/MV vs Index 累计收益（跨市场推广）。"""
    fig, axes = plt.subplots(1, len(ports), figsize=(15, 5), sharey=False)
    if len(ports) == 1:
        axes = [axes]
    for ax, (market, mp) in zip(axes, ports.items()):
        cum = cumulative_returns(mp)
        for model, color, lw in (("CPMM-EW", BLUE, 2.4), ("CPMM-MV", RED, 2.0)):
            if model in cum.columns:
                ax.plot(cum.index, cum[model], color=color, lw=lw, label=model)
        if "Index" in cum.columns:
            ax.plot(cum.index, cum["Index"], color="gray", lw=1.4, ls="--", label="Index")
        ax.set_title(MARKET_NAMES_CN.get(market, market), fontsize=13)
        ax.set_xlabel("时间", fontsize=11)
        ax.axhline(0, color="gray", lw=0.7, ls=":")
        ax.legend(fontsize=9)
    axes[0].set_ylabel("累计收益（%）", fontsize=12)
    fig.suptitle("CPMM-EW/MV vs Index 累计收益（三宽基跨市场）", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _fig_weight_evolution(mp, market: str, path: Path) -> None:
    """必需图1：CPMM-EW 各持仓资产权重堆叠面积图。"""
    mr = mp.models.get("CPMM-EW")
    if mr is None or mr.weights_panel.empty:
        return
    wp = mr.weights_panel.copy()
    wp = wp.loc[:, (wp.abs().sum() > 0)]
    fig, ax = plt.subplots(figsize=(12, 6))
    colors = plt.cm.tab20b(np.linspace(0, 1, wp.shape[1]))
    ax.stackplot(wp.index, wp.T.values, colors=colors, alpha=0.85)
    ax.set_title(f"CPMM-EW 持仓权重演化（{MARKET_NAMES_CN.get(market, market)}）", fontsize=14)
    ax.set_xlabel("调仓时间", fontsize=12)
    ax.set_ylabel("组合权重", fontsize=12)
    ax.set_ylim(0, 1)
    ax.text(0.01, 0.97, f"资产池 {wp.shape[1]} 只（每月约 {int((wp > 0).sum(axis=1).mean())} 只在仓）",
            transform=ax.transAxes, fontsize=10, va="top")
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _fig_portfolio_nav(mp, market: str, path: Path) -> None:
    """必需图2：CPMM-EW 组合净值 vs Index / 等权消融基准（EWMFM）。"""
    fig, ax = plt.subplots(figsize=(12, 6))
    for model, color, lw, ls in (("CPMM-EW", BLUE, 2.6, "-"),
                                 ("EWMFM", "#2ca02c", 1.6, "--"),
                                 ("Index", RED, 1.8, "-.")):
        mr = mp.models.get(model)
        if mr is None or mr.nav.empty:
            continue
        ax.plot(mr.nav.index, mr.nav.values, color=color, lw=lw, ls=ls, label=model)
    ax.set_title(f"组合净值 CPMM-EW vs 消融/基准（{MARKET_NAMES_CN.get(market, market)}）", fontsize=14)
    ax.set_xlabel("时间", fontsize=12)
    ax.set_ylabel("净值（起点 1.0）", fontsize=12)
    ax.legend(fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _fig_asset_contribution(mp, market: str, path: Path) -> None:
    """必需图3：CPMM-EW 各资产累计收益贡献（top-15，正蓝负红）。"""
    mr = mp.models.get("CPMM-EW")
    if mr is None or mr.backtest.empty:
        return
    contrib_cols = [c for c in mr.backtest.columns if c.startswith("contrib_")]
    if not contrib_cols:
        return
    total = mr.backtest[contrib_cols].sum().rename(lambda c: c.replace("contrib_", ""))
    total = total[total.abs() > 1e-9].sort_values()
    top = pd.concat([total.head(8), total.tail(8)]).drop_duplicates()
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = [BLUE if v >= 0 else RED for v in top.values]
    ax.barh(top.index.astype(str), top.values, color=colors)
    ax.set_title(f"CPMM-EW 各资产累计收益贡献 top（{MARKET_NAMES_CN.get(market, market)}）", fontsize=14)
    ax.set_xlabel("累计收益贡献（Σ w·r）", fontsize=12)
    ax.axvline(0, color="gray", lw=0.8)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _fig_rolling_volatility(mp, market: str, path: Path) -> None:
    """必需图4：CPMM-EW 组合滚动年化波动（12 月窗）vs Index。"""
    fig, ax = plt.subplots(figsize=(12, 6))
    for model, color in (("CPMM-EW", BLUE), ("Index", RED)):
        mr = mp.models.get(model)
        if mr is None or mr.port_returns.empty:
            continue
        rv = mr.port_returns.rolling(12).std() * np.sqrt(12)
        ax.plot(rv.index, rv.values, color=color, lw=2.0, label=model)
    ax.set_title(f"CPMM-EW 组合滚动年化波动（12 月窗，{MARKET_NAMES_CN.get(market, market)}）", fontsize=14)
    ax.set_xlabel("时间", fontsize=12)
    ax.set_ylabel("年化波动率", fontsize=12)
    ax.legend(fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _fig_drawdown(mp, market: str, path: Path) -> None:
    """必需图5：CPMM-EW 组合回撤曲线 vs Index。"""
    fig, ax = plt.subplots(figsize=(12, 6))
    for model, color in (("CPMM-EW", BLUE), ("Index", RED)):
        mr = mp.models.get(model)
        if mr is None or mr.nav.empty:
            continue
        dd = (mr.nav / mr.nav.cummax() - 1.0) * 100.0
        ax.fill_between(dd.index, dd.values, 0, color=color, alpha=0.35, label=model)
        ax.plot(dd.index, dd.values, color=color, lw=1.2)
    ax.set_title(f"CPMM-EW 组合回撤（{MARKET_NAMES_CN.get(market, market)}）", fontsize=14)
    ax.set_xlabel("时间", fontsize=12)
    ax.set_ylabel("回撤（%）", fontsize=12)
    ax.legend(fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def save_charts(ports, primary: str = PRIMARY_MARKET) -> None:
    """产 R5 累计收益 + allocation 必需 5 图（主图针对主市场 CPMM-EW）。"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    mp = ports[primary]
    _fig_cumulative_single(mp, primary, RESULTS_DIR / f"cumulative_returns_{primary}.png")
    _fig_cumulative_markets(ports, RESULTS_DIR / "cumulative_returns_all_markets.png")
    _fig_weight_evolution(mp, primary, RESULTS_DIR / "weight_evolution.png")
    _fig_portfolio_nav(mp, primary, RESULTS_DIR / "portfolio_nav.png")
    _fig_asset_contribution(mp, primary, RESULTS_DIR / "asset_contribution.png")
    _fig_rolling_volatility(mp, primary, RESULTS_DIR / "rolling_volatility.png")
    _fig_drawdown(mp, primary, RESULTS_DIR / "drawdown.png")
    print(f"[图表] 已写 7 张 PNG 到 {RESULTS_DIR}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 84)
    print("ssrn_6115073 · m6 全链装配（m1→m6 端到端；市场迁移复现 experimental）")
    print("=" * 84)
    prep, sel, clus, sig, sp, ports = build_and_run(cost_bps=COST_BPS_FRICTIONLESS)

    # R1 表核心行打印（只报数）
    r1 = build_r1_table(ports)
    print("\n[R1/表2] 六比率×11方法×3市场（SR 行示例；完整见 Excel）：")
    print(r1[r1["指标"] == "SR"].to_string(index=False))

    save_excel(prep, ports, sp, RESULTS_DIR / "backtest_summary.xlsx")
    save_charts(ports)

    # CPMM-EW 相对领先性速览（只报数，不下结论）
    print("\n[CPMM-EW 领先性速览] 各市场 CPMM-EW 的 SR 排名 / 11 方法：")
    for market, mp in ports.items():
        sr = {m: mp.models[m].metrics.get("SR", np.nan) for m in ALL_MODELS if m in mp.models}
        order = sorted(sr, key=lambda k: (np.nan_to_num(sr[k], nan=-1e9)), reverse=True)
        rank = order.index("CPMM-EW") + 1 if "CPMM-EW" in order else -1
        print(f"  {MARKET_NAMES_CN.get(market, market)}（{mp.regime_tier}）："
              f"CPMM-EW SR={sr.get('CPMM-EW', float('nan')):.3f}，"
              f"11 方法中排名第 {rank}；最高={order[0]}({sr[order[0]]:.3f})")
    print("\n[完成] m6 端到端产物已落盘（R1 表 + 累计净值 + 图表）。判定归 verify/diagnoser。")


if __name__ == "__main__":
    main()
