"""研报复现系统 v2 · 多 agent 协作流程图渲染（含假设 Excel 批量 revise 回路）。

输出：docs/multi_agent_workflow.png（300 DPI）+ docs/multi_agent_workflow.mmd（mermaid 源）。
用法：uv run python docs/render_workflow_diagram.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["PingFang SC", "Songti SC", "Heiti TC", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT_DIR = Path(__file__).resolve().parent

BLUE = "#1f77b4"
RED = "#d62728"
GRAY = "#666666"
LIGHT_BLUE = "#eaf2fb"
LIGHT_YELLOW = "#fff7e0"
DARK = "#2f2f2f"


def box(ax, x, y, w, h, title, lines, *, ec=BLUE, fc="white", lw=1.6,
        dashed=False, title_color=DARK, title_size=10.5, line_size=8.6):
    bb = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.9",
        edgecolor=ec, facecolor=fc, linewidth=lw,
        linestyle=(0, (4, 2.4)) if dashed else "solid", zorder=2,
    )
    ax.add_patch(bb)
    ax.text(x + w / 2, y + h - 1.5, title, ha="center", va="center",
            fontsize=title_size, fontweight="bold", color=title_color, zorder=3)
    for i, (text, color) in enumerate(lines):
        ax.text(x + w / 2, y + h - 3.4 - i * 2.0, text, ha="center", va="center",
                fontsize=line_size, color=color, zorder=3)


def arrow(ax, x1, y1, x2, y2, *, color=DARK, lw=1.8, style="-|>", dashed=False,
          connectionstyle="arc3,rad=0"):
    arr = FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle=style, mutation_scale=13,
        color=color, linewidth=lw, linestyle=(0, (4, 2.4)) if dashed else "solid",
        connectionstyle=connectionstyle, zorder=1,
    )
    ax.add_patch(arr)


def main() -> None:
    fig, ax = plt.subplots(figsize=(18, 12))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 68)
    ax.axis("off")

    ax.text(50, 66, "研报复现系统 v2 · 多 agent 协作流程图", ha="center", va="center",
            fontsize=17, fontweight="bold", color=DARK)
    ax.text(50, 63.6, "12 阶段门禁状态机 + 假设 Excel 批量 revise 回路（本次新增，底部虚线区）",
            ha="center", va="center", fontsize=10.5, color=GRAY)

    # ---- 主会话编排条 ----
    box(ax, 6, 56.5, 88, 5, "主会话（编排大脑 Orchestrator）", [
        ("只派发子 agent / 审门禁（check_gates 重算）/ 调 codex 外审 / 写 state.json —— 不亲自生产内容", DARK),
    ], ec=DARK, fc="#f0f0f0", lw=2.2, title_size=11.5, line_size=9)

    # ---- 12 阶段（两行，均左→右）----
    W, H = 13.2, 8.2
    XS = [3.5 + i * 15.9 for i in range(6)]  # 3.5, 19.4, 35.3, 51.2, 67.1, 83.0
    Y1, Y2 = 43.5, 28.5

    row1 = [
        ("1 初始化 init", [("主会话直跑工具", BLUE), ("workspace 骨架 + PDF→文本", GRAY)]),
        ("2 研报提取 extract", [("quant-extractor (opus)", BLUE), ("spec 三件套（页码引用制）", GRAY)]),
        ("3 复现规划 plan", [("quant-planner (opus)", BLUE), ("plan.md + 假设登记簿(含参数绑定)", GRAY)]),
        ("4 规格审计 spec_audit", [("quant-auditor ∥ codex 外审", BLUE), ("盲提取对照 / 意见闭环", GRAY)]),
        ("5 代码实现 implement", [("quant-coder (opus × milestone)", BLUE), ("src/<id>/ + 校正参数绑定", GRAY)]),
        ("6 代码审计 code_audit", [("quant-auditor + codex 外审", BLUE), ("未来函数 / 硬编码 / 方向核查", GRAY)]),
    ]
    row2 = [
        ("7 运行验证 verify", [("quant-verifier (opus)", BLUE), ("comparison.json + 图表证据链", GRAY)]),
        ("8 迭代修正 iterate（条件）", [("diagnoser→coder→verifier", BLUE), ("iter_NN 三件套 / 防兜圈", GRAY)]),
        ("9 结果审计 result_audit", [("quant-auditor + codex 外审", BLUE), ("反虚报最后防线（必跑）", GRAY)]),
        ("10 样本外 oos（条件）", [("quant-oos-analyst", BLUE), ("oos_report.md（不改策略）", GRAY)]),
        ("11 报告汇总 report", [("quant-reporter (sonnet)", BLUE), ("final_report.md/html + 导出 xlsx", GRAY)]),
        ("12 人工评审 review", [("用户裁决（人工闸门）", RED), ("accept 收尾 / revise 重跑", GRAY)]),
    ]
    for i, (title, lines) in enumerate(row1):
        box(ax, XS[i], Y1, W, H, title, lines, ec=BLUE, fc=LIGHT_BLUE)
    for i, (title, lines) in enumerate(row2):
        dashed = i in (1, 3)
        ec = RED if i == 5 else BLUE
        box(ax, XS[i], Y2, W, H, title, lines, ec=ec, fc="white", dashed=dashed,
            lw=2.2 if i == 5 else 1.6)
    # 阶段间箭头
    for i in range(5):
        arrow(ax, XS[i] + W + 0.3, Y1 + H / 2, XS[i + 1] - 0.3, Y1 + H / 2)
        arrow(ax, XS[i] + W + 0.3, Y2 + H / 2, XS[i + 1] - 0.3, Y2 + H / 2)
    # 折返：code_audit → verify（两行中间水平折线，不穿框）
    ax.plot([XS[5] + W / 2, XS[5] + W / 2], [Y1 - 0.3, 40.2], color=DARK, lw=1.8, zorder=1)
    ax.plot([XS[0] + W / 2, XS[5] + W / 2], [40.2, 40.2], color=DARK, lw=1.8, zorder=1)
    arrow(ax, XS[0] + W / 2, 40.2, XS[0] + W / 2, Y2 + H + 0.3)
    # 主会话条与各阶段的驱动关系（示意两条）
    arrow(ax, 25, 56.2, 25, Y1 + H + 0.4, color=GRAY, lw=1.2, dashed=True)
    arrow(ax, 75, 56.2, 75, Y1 + H + 0.4, color=GRAY, lw=1.2, dashed=True)
    ax.text(50, 54.2, "每阶段结束必过门禁（G-XX 机器重算）：PASS 才放行；不达标进 iterate 或暂停呈报",
            ha="center", va="center", fontsize=8.6, color=GRAY)

    # ---- 底部：本次新增 Excel 批量 revise 回路 ----
    LX, LY, LW, LH = 3.5, 2.5, 92.5, 23.5
    bb = FancyBboxPatch((LX, LY), LW, LH, boxstyle="round,pad=0.3,rounding_size=1.2",
                        edgecolor=RED, facecolor=LIGHT_YELLOW, linewidth=1.8,
                        linestyle=(0, (5, 3)), zorder=1)
    ax.add_patch(bb)
    ax.text(LX + LW / 2, LY + LH - 0.9, "本次新增：假设 Excel 批量 revise（客户自助改多条，一次重跑）",
            ha="center", va="center", fontsize=11.5, fontweight="bold", color=RED, zorder=3)

    bw, bh, by = 16.5, 8.6, 12.8
    box(ax, 5.5, by, bw, bh, "① 工作表导出与编辑", [
        ("report 阶段自动导出", DARK),
        ("assumptions.xlsx", DARK),
        ("客户在 Excel 批量改多条", RED),
    ], ec=RED)
    box(ax, 25.5, by, bw, bh, "② revise --from-excel", [
        ("apply --dry-run 预演", DARK),
        ("复述计划 + 拒绝行", DARK),
        ("客户确认后正式落地", RED),
    ], ec=RED)
    box(ax, 45.5, by, bw, bh, "③ apply 工具分流", [
        ("逐行校验 / 容错", DARK),
        ("参数直改 → ④a", DARK),
        ("文本口径 → ④b", DARK),
    ], ec=BLUE, fc="white")
    box(ax, 66, by + 4.6, 27, 6.4, "④a 参数直改通道（不经过 agent）", [
        ("工具注入 config.py：备份 + diff + 实例化冒烟", DARK),
        ("登记簿追记 revised + 修订记录（确定性）", GRAY),
    ], ec=BLUE, fc="white", title_size=9.5, line_size=8.2)
    box(ax, 66, by - 2.6, 27, 6.4, "④b 文本口径通道（完整审计链）", [
        ("quant-planner 批量改写登记簿", DARK),
        ("涉 data/method → quant-coder + codex 增量审计", GRAY),
    ], ec=BLUE, fc="white", title_size=9.5, line_size=8.2)
    box(ax, 30, 3.6, 40, 6.2, "⑤ 按最重影响面合并重跑（data/method > param/trading > output）", [
        ("verify 重跑（回填验证后回看）→ result_audit（轻量）→ reporter 增量更新 → 回 review", DARK),
        ("记账 record-event（不占迭代轮次）+ 重新 export 刷新工作表", GRAY),
    ], ec=BLUE, fc="white", title_size=9.5, line_size=8.0)

    arrow(ax, 5.5 + bw + 0.3, by + bh / 2, 25.5 - 0.3, by + bh / 2)
    arrow(ax, 25.5 + bw + 0.3, by + bh / 2, 45.5 - 0.3, by + bh / 2)
    arrow(ax, 45.5 + bw + 0.3, by + bh * 0.72, 66 - 0.3, by + 4.6 + 3.2)
    arrow(ax, 45.5 + bw + 0.3, by + bh * 0.28, 66 - 0.3, by - 2.6 + 3.2)
    # ④a/④b 左缘引线汇入 x=64 竖线 → ⑤ 顶
    ax.plot([66, 64], [by + 4.6 + 3.2, by + 4.6 + 3.2], color=DARK, lw=1.8, zorder=1)
    ax.plot([66, 64], [by - 2.6 + 3.2, by - 2.6 + 3.2], color=DARK, lw=1.8, zorder=1)
    arrow(ax, 64, by + 4.6 + 3.2, 64, 3.6 + 6.2 + 0.3)

    # review → 回路（向下）
    arrow(ax, XS[5] + W / 2, Y2 - 0.3, XS[5] + W / 2, LY + LH + 0.3, color=RED, lw=2.0)
    ax.text(XS[5] + W / 2 + 1.2, Y2 - 1.6, "客户改假设", fontsize=8.6, color=RED, ha="left")
    # report → ①（导出）
    arrow(ax, XS[4] + W / 2, Y2 - 0.3, XS[4] + W / 2, LY + LH + 0.3, color=GRAY, lw=1.4, dashed=True)
    ax.text(XS[4] + W / 2 + 1.2, Y2 - 1.6, "自动导出 xlsx", fontsize=8.2, color=GRAY, ha="left")
    # ⑤ → verify（回卷：沿左缘向上进 verify 左缘）
    ax.plot([30 - 0.3, 1.5], [3.6 + 3.1, 3.6 + 3.1], color=BLUE, lw=2.0, zorder=1)
    ax.plot([1.5, 1.5], [3.6 + 3.1, Y2 + H / 2], color=BLUE, lw=2.0, zorder=1)
    arrow(ax, 1.5, Y2 + H / 2, XS[0] - 0.3, Y2 + H / 2, color=BLUE, lw=2.0)
    ax.text(2.5, 17, "回 verify 续跑", fontsize=8.6, color=BLUE, ha="left", rotation=90)

    # --each 旁注
    ax.text(LX + LW / 2, 1.2,
            "备选 --each 逐条敏感性：set-param 改单参 → verifier 重跑 → 快照 → restore 回滚 × N → assumption_sensitivity.xlsx（纯 what-if，不改登记簿）",
            ha="center", va="center", fontsize=8.4, color=GRAY)

    fig.savefig(OUT_DIR / "multi_agent_workflow.png", dpi=300, bbox_inches="tight",
                facecolor="white")
    print(f"PNG_SAVED {OUT_DIR / 'multi_agent_workflow.png'}")


MERMAID = """%% 研报复现系统 v2 · 多 agent 协作流程（与 docs/multi_agent_workflow.png 同内容）
flowchart LR
    subgraph ORCH["主会话（编排大脑）：只派发 / 审门禁 / 调 codex / 写 state，不亲自生产内容"]
        direction TB
        S1["1 init 初始化<br/>主会话直跑工具"]
        S2["2 extract 研报提取<br/>quant-extractor"]
        S3["3 plan 复现规划<br/>quant-planner<br/>plan.md + 假设登记簿(参数绑定)"]
        S4["4 spec_audit 规格审计<br/>quant-auditor ∥ codex 外审"]
        S5["5 implement 代码实现<br/>quant-coder × milestone"]
        S6["6 code_audit 代码审计<br/>quant-auditor + codex 外审"]
        S7["7 verify 运行验证<br/>quant-verifier<br/>comparison.json"]
        S8{"8 iterate 迭代修正（条件）<br/>diagnoser→coder→verifier"}
        S9["9 result_audit 结果审计<br/>codex 外审（反虚报必跑）"]
        S10{"10 oos 样本外（条件）<br/>quant-oos-analyst"}
        S11["11 report 报告汇总<br/>quant-reporter<br/>final_report + 导出 assumptions.xlsx"]
        S12[["12 review 人工评审<br/>accept / revise"]]
        S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7
        S7 -->|不达标| S8 --> S9
        S7 -->|达标| S9 --> S10 --> S11 --> S12
    end

    subgraph LOOP["本次新增：假设 Excel 批量 revise"]
        direction LR
        E1["① assumptions.xlsx<br/>客户批量编辑多条"] --> E2["② revise --from-excel<br/>dry-run 复述 → 客户确认"]
        E2 --> E3{"③ apply 工具分流"}
        E3 -->|参数直改| E4a["④a 工具注入 config.py<br/>备份+diff+冒烟+md 追记<br/>（不经过 agent）"]
        E3 -->|文本口径| E4b["④b quant-planner 批量改写<br/>涉 data/method → coder + codex 增量审计"]
        E4a --> E5["⑤ 按最重影响面合并重跑<br/>verify→result_audit→report→回 review<br/>+ 重新导出 xlsx"]
        E4b --> E5
        E6["--each 逐条敏感性（备选）<br/>set-param→verifier→快照→restore ×N<br/>→ sensitivity.xlsx（what-if 不改登记簿）"]
    end

    S11 -.自动导出.-> E1
    S12 -->|revise --from-excel| E2
    E5 -->|按影响面续跑| S7
"""


if __name__ == "__main__":
    main()
    (OUT_DIR / "multi_agent_workflow.mmd").write_text(MERMAID, encoding="utf-8")
    print(f"MMD_SAVED {OUT_DIR / 'multi_agent_workflow.mmd'}")
