{
  "excluded_hypotheses_confirmed": [
    "已读过 iter_01 diagnosis.md：该文件说明 iter=1 为首轮，无历史轮次，不含正式「已排除假设」节。",
    "已读过 iter_01 diagnosis.md 的显式[已排除]：盈亏比残差不是策略信号实现错误，因为无策略逻辑的 T 买入持有基准盈亏比也同步偏低。",
    "已读过 iter_01 diagnosis.md 的显式[已排除]：v1 旧系统的「盈亏比研报口径不可推断」结论已被 R3 sum 总额比逐格对齐证据推翻，不应重提。",
    "已读过 iter_01 changes.md / comparison_after.json：M1 已只改盈亏比为 sum 总额比，当前 22 项残差不应再围绕盈亏比均值比兜圈。",
    "已确认 workspace/test_v2/iterations/iter_02/diagnosis.md 与 workspace/test_v2/iterations/iteration_log.md 当前不存在，因此没有额外历史「已排除假设」节可读取。"
  ],
  "hypotheses": [
    {
      "id": "CDX-SO-01",
      "rank": 1,
      "family": "参数类",
      "relation_to_history": "历史假设变体：主诊断把年化/夏普残差归为数据源，并用波动率已对齐来排除年化天数；本假设不是泛泛改自然年，而是固定 240 交易日年化，波动率仅下降约2.4%，仍可能留在容差内。",
      "description": "当前 src/test_v2/config.py:75 使用 periods_per_year=252。当前 R8/R9/R11 年化收益普遍高 5%~6.7%，而把年化基准改为 240 的只读探针显示：R1-T 年化 0.02417 -> 0.02300（研报0.023），R8 多空年化 0.06135 -> 0.05835（研报0.0577），R9 多空年化 0.06737 -> 0.06406（研报0.064），R11 仅做多年化 0.05375 -> 0.05112（研报0.051）。夏普同步下降约2.4%，多数组合列会从超差边缘回到容差内。",
      "verification_method": "小改动：将 src/test_v2/config.py:75 的 periods_per_year 从 252 改为 240；重跑 comparison。观察 common/timing_backtest.py:142-145 派生的 annual_return/sharpe：R8/R9/R11 年化与夏普应整体下降，年化下降约4.8%，夏普下降约2.4%；R10/R12 区间收益和 R11 下跌胜率不应变化。",
      "expected_impact": "critical",
      "confidence": "high"
    },
    {
      "id": "CDX-SO-02",
      "rank": 2,
      "family": "方法论类",
      "relation_to_history": "历史假设变体：AS7 只登记「上涨/下跌胜率定义不可推断」，主诊断未给可执行替代定义；本假设给出具体分子分母，不是重提不可推断。",
      "description": "src/test_v2/reversal.py:146-151 当前把上涨/下跌胜率定义为「有持仓且标的上涨/下跌日中 strategy_ret>0」。但只读复算显示，研报更像使用方向命中/不亏口径：上涨日要求 strategy_ret>0，下跌日要求 strategy_ret>=0，且分母包含所有标的上涨/下跌日。该口径下 R7 上涨/下跌为 0.4443/0.6504，贴近研报 0.4448/0.6528；R11 下跌胜率为 0.490135，几乎等于研报 0.4902。",
      "verification_method": "小改动：在 src/test_v2/reversal.py:146-151 单独改 up_win_rate/down_win_rate 计算，up = (strategy_ret[asset_ret > 0] > 0).mean()，down = (strategy_ret[asset_ret < 0] >= 0).mean()。预期 R11_多空_win_rate_下跌胜率从 0.462212 上升到约 0.4901，直接命中研报；R7/R8/R9/R11 的上涨/下跌胜率中间产物也应更贴近研报。",
      "expected_impact": "minor",
      "confidence": "high"
    },
    {
      "id": "CDX-SO-03",
      "rank": 3,
      "family": "参数类",
      "relation_to_history": "历史假设变体：主诊断提到 R1 单腿可能是基日、min_periods、含当日值等分位轨细节；本假设改查 N_l/N_s 的交易日折算，机制不同。",
      "description": "R1 长端偏低、短端偏高且长短端合成主列已过，说明单腿更像窗口参数或标签口径问题。只读探针显示，把 src/test_v2/config.py:37 的 long_window 120 改为 126 后，R1 长端年化 0.01864 -> 0.02205（研报0.0217），夏普 0.6958 -> 0.8092（研报0.81）；但长端回撤仍不理想、短端不变。短端若把 short_window 20 改为 15，短端年化 0.01920 -> 0.01793（研报0.0173），夏普 0.663 -> 0.584（研报0.60），但会破坏长短端合成列。",
      "verification_method": "先只做一个探针：src/test_v2/config.py:37 long_window=126，保持 short_window=20，重跑 R1。预期 R1_长端_annual_return 和 R1_长端_sharpe 大幅上升并接近研报，R1_长短端_max_drawdown 从 0.05495 向 0.063 附近移动；若验证方向成立，再单独测试 src/test_v2/config.py:38 short_window=15，不要一次合并两个窗口修改。",
      "expected_impact": "major",
      "confidence": "low"
    },
    {
      "id": "CDX-SO-04",
      "rank": 4,
      "family": "数据口径类",
      "relation_to_history": "历史假设变体：主诊断认为 Wind 连续合约口径不可得；本假设只测试本地已有字段 close_return 与 settle_return / pct_of_sett_price 的差异，属于可证伪的本地数据口径探针。",
      "description": "src/test_v2/data_prep.py:70-72 当前策略 PnL 用 pct_of_close_price 作为 close_return。只读探针把 close_return 临时替换为 pct_of_sett_price 后，R8 多空年化从 0.06135 降到 0.05761（几乎等于研报0.0577），R10 2016 从 0.10979 降到 0.09261（接近研报0.0944）。但它会使部分夏普和 T 基准变差，因此更适合作为证伪数据源族的探针，而不是直接全局采用。",
      "verification_method": "小改动：在 src/test_v2/data_prep.py:71 临时令 frame[\"close_return\"] = (frame[\"pct_of_sett_price\"] / 100.0).fillna(frame[\"settle\"].pct_change())，保持其它信号不变。预期 R8 年化、R10 2016 往研报方向下降；若 R1-T 夏普、R9/R11 夏普明显恶化，则应拒绝该全局切换，只保留为数据源解释证据。",
      "expected_impact": "major",
      "confidence": "low"
    }
  ]
}