{
  "excluded_hypotheses_confirmed": [
    "已读过 iter_01 diagnosis.md：iter_01 为首轮，文件明示无正式「已排除假设」节；但家族一内部已显式排除「盈亏比偏差来自策略信号实现错误」。",
    "已读过 iter_01 diagnosis.md：已显式推翻 v1 旧系统「盈亏比研报口径不可推断」结论，理由是 R3 的 sum 总额比逐格对齐研报。",
    "已读过 iter_01 changes.md：M1 已将 common/timing_backtest.py 的盈亏比从 mean/mean 改为 sum/sum，当前残差不应再围绕盈亏比口径兜圈。",
    "已读过 iter_02 diagnosis.md 的「已排除假设」节：禁止重提盈亏比均值比、策略信号整体错误、v1 盈亏比不可推断；iter_01 家族二「纯数据源且完全不可修」已被 240 年化基准部分改判。",
    "已读过 iter_02 diagnosis.md：SO-01 年化基准 240 与 SO-02 上涨/下跌胜率口径已采纳；SO-04 全局 close_return 切 settle_return 因回归副作用被排除；SO-03 long_window=126 已延后且要求护住长短端主列。",
    "已读过 iter_02 changes.md 与 iter_02/comparison_after.json 摘要：M2/M3 后 pass=81/91，残余 10 项正是 R1 单腿/回撤 6 项与 R10/R12 2016/2023 分年区间收益 4 项。",
    "已检查 workspace/test_v2/iterations/iteration_log.md：该文件在当前工作区不存在，因此没有额外总账可读取；以上历史边界来自实际存在的 iter_01/iter_02 文件。"
  ],
  "hypotheses": [
    {
      "id": "CDX-SO-01",
      "rank": 1,
      "family": "参数类",
      "relation_to_history": "历史假设变体，但机制不同于 SO-03。SO-03 是 long_window=126 的窗口长度探针；本假设改的是 F1 上下三分位触发带宽/分位阈值，不重提 126 日窗口。",
      "description": "R1 长端偏低、短端略高，且长短端主列收益/夏普已基本对齐，说明问题更像单腿触发频率边界，而不是收益源或总信号方向。当前 src/test_v2/config.py:39-40 固定 1/3、2/3，strategy.py:78-79 用 pandas expanding quantile。只读探针显示把分位带从 1/3-2/3 轻微放宽到 0.345/0.655 时，R1 长端年化 0.017744 -> 0.022357，夏普 0.678708 -> 0.827384，接近研报 0.0217/0.81；若放到 0.35/0.65，短端年化 0.017291、夏普 0.590506 接近研报 0.0173/0.60，长短端最大回撤也到 0.06097 接近研报 0.06。风险是长短端主列年化可能被推高，必须护主列。",
      "verification_method": "一次小改动先只改 src/test_v2/config.py:39-40：quantile_lower=0.345、quantile_upper=0.655，保持 long_window=120、short_window=20 不变，重跑 R1。预期 R1_长端_annual_return 从 0.017744 上升到约 0.02236，R1_长端_sharpe 从 0.6787 上升到约 0.827；同时监控 R1_长短端_annual_return 可能从 0.02802 升到约 0.03161，若主列翻 fail 则证实该族有效但不能直接采纳。",
      "expected_impact": "major",
      "confidence": "low"
    },
    {
      "id": "CDX-SO-02",
      "rank": 2,
      "family": "数据口径类",
      "relation_to_history": "历史假设变体，但不是 SO-04 的全局结算价源切换。SO-04 是把整个收益序列 close_return 改为 settle_return；本假设只在隔日反转分支实际决定仓位的交易日使用结算价收益，其余分支仍用收盘价收益。",
      "description": "F7/F8 中隔日反转因子本身由结算价构造，但当前 combo_composite.py:215、combo_final.py:305 统一把 close_return 作为 PnL 收益源。只读探针中，若仅在 reversal 分支 payoff 日改用 future_settle_return，R12_2016 从 0.125084 降到约 0.112643，接近研报 0.1141；R10_2016 从 0.109792 降到约 0.09983，也向研报 0.0944 靠近。副作用是 2023 会被推高，且 R11/R9 核心收益可能下降，因此它更适合作为数据源族诊断探针，而非默认全局修正。",
      "verification_method": "小改动位置：在 src/test_v2/combo_composite.py:206-216 和 src/test_v2/combo_final.py:294-306 的 signals 中增加 settle_return；在 combo_composite.py:231-237、combo_final.py:321-327 构造 ret_for_pnl，当上一交易日被 reversal 分支选中时用 settle_return，否则用 close_return。预期 R12_2016_interval_ls 下降约 1.24pp 到 0.1126 附近，R10_2016_interval_ls 下降约 1.0pp 到 0.0998 附近；若 R11/R9 主表核心项翻 fail或 2023 过冲，则拒绝采纳但保留为残差归因证据。",
      "expected_impact": "major",
      "confidence": "medium"
    },
    {
      "id": "CDX-SO-03",
      "rank": 3,
      "family": "时点对齐类",
      "relation_to_history": "全新假设。历史 AS9/AS10 讨论的是信号形成日与持仓兑现日对齐；本假设讨论的是分年统计时把收益归到「收益兑现日」还是「信号/建仓日」，不改变策略仓位本身。",
      "description": "R10/R12 的失败只出现在分年区间收益，主表 R9/R11 核心指标已过。当前 combo_composite.py:285-301 的 _yearly_stats 直接按 strategy_ret.index.year 分组，也就是按收益兑现日归年。若研报制表按信号日/建仓日归属，则只改变年末年初边界，正好主要影响 2016 和不完整的 2023。只读探针把收益索引回移一个交易日后，R12_2016 从 0.12508 降到约 0.11972，R10_2016 从 0.10979 降到约 0.10450，方向正确但不足以单独解释全部残差；2023 会继续降低，方向不理想。",
      "verification_method": "小改动：在 src/test_v2/combo_composite.py:292-295 的 _yearly_stats 内，分组前将 daily_ret 的 index 回移一个交易日用于 groupby，但收益值不变；R12 复用同一函数，combo_final.py:386 会自动受影响。预期 R10/R12 的 2016 区间收益下降 0.5-0.6pp，2023 也下降约 0.1pp；若只改善 2016、劣化 2023，则判定为次要边界归因，不作为主修。",
      "expected_impact": "minor",
      "confidence": "low"
    }
  ]
}