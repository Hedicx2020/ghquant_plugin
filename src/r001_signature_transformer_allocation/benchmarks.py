"""r001 · SIT 复现——原文研报 R4 基准锚（reference-only，非复现计算结果）。

本模块只承载**原文研报 Table 7 Panel A（CSI300-50 universe，page 20）**已发表的基准数值，
供 main.py 主绩效表 / backtest_summary.xlsx 生成「研报值 vs 复现值 vs 偏差」对照列。

严格边界（CDX-C-02）：
  - 这些数字**不是本项目复现计算的产物**，而是原文作者发表的参考值，仅作对照锚——
    不参与任何复现计算、不作达标判据（实验模式数值豁免，AS12/AS16）。
  - 复现自身结果全部由 main.run_pipeline **实测**产生，绝不以本文件的锚值顶替。
  - 计算模块（main/backtest/train/…）只以 ``R4_ANCHOR_CSI300_50[name]`` 读取对照锚，
    禁止把锚值回灌进任何实测路径。

数值来源：spec §R4 / 原文 Table 7 Panel A，逐格转录（略去 ± 标准差、只取对照所需的点估计），
四指标顺序 Sharpe(↑) / Sortino(↑) / MaxDrawdown(↓) / FinalWealth(↑)。
"""

from __future__ import annotations

# 原文 Table 7 Panel A · Asset 50 Universe (CSI300) —— reference-only 基准锚。
# value 形状对齐 main.py 用法（``a['Sharpe']`` / ``a['MaxDrawdown']`` / ``a['FinalWealth']``）：
# 每个模型 → {"Sharpe","Sortino","MaxDrawdown","FinalWealth"} 字典。
R4_ANCHOR_CSI300_50: dict[str, dict[str, float]] = {
    "SIT":     {"Sharpe": 1.9373, "Sortino": 2.3399, "MaxDrawdown": 0.0964, "FinalWealth": 1.2804},
    "EW":      {"Sharpe": 1.1695, "Sortino": 1.3671, "MaxDrawdown": 0.1263, "FinalWealth": 1.1413},
    "GMV":     {"Sharpe": 1.6717, "Sortino": 2.1255, "MaxDrawdown": 0.0942, "FinalWealth": 1.1766},
    "HRP":     {"Sharpe": 1.7428, "Sortino": 2.0183, "MaxDrawdown": 0.1136, "FinalWealth": 1.1825},
    "CVaR":    {"Sharpe": 0.8292, "Sortino": 1.0038, "MaxDrawdown": 0.1220, "FinalWealth": 1.0971},
    "DLinear": {"Sharpe": 0.5122, "Sortino": 0.6819, "MaxDrawdown": 0.2032, "FinalWealth": 1.1252},
}
