{
  "excluded_hypotheses_confirmed": [
    "已排除 Growth PIT 覆盖不足、Size 排序或四箱内部算术是当前阻断主因；不得重开这些诊断或据此调因子。",
    "已排除通过缩短正式 OOS、增加 Momentum/Quality/Low Volatility/宏观/ML 输入来规避问题。",
    "已排除用未来最后报价日追溯强制卖出、退市后强制零值、虚构 VWAP/成交量/现金或换股比例，以及永久沿用陈旧 0.40 元 mark。",
    "已排除把 risk_exit 公告本身当作估值来源或永久陈旧价豁免；它只表达退出意图。",
    "已排除 iter_02 的日/月桥接、合成因子跨频口径和生命周期同键双状态仍是本次唯一阻断原因；当前唯一硬阻断是 600466 缺少可审计的 400165 转板行情链。",
    "已确认当前本地 A 股 price/trade 层没有 400165，600466 最后本地观察日为 2023-06-05，现有 20 交易日寿命门禁在 2023-07-06 正确触发，不能靠关闭门禁生成完整 NAV。"
  ],
  "hypotheses": [
    {
      "id": "CDX-SO3-01",
      "rank": 1,
      "family": "时点对齐类",
      "relation_to_history": "历史变体",
      "description": "最可能的首要风险是把 600466→400165 直接写成一个事后已知的静态代码替换，从而在映射公告尚不可得时提前知道后继代码。现有 config.py:security_share_settlement_events、portfolio.py:_normalise_security_events/_apply_effective_security_events 已能表达带 announcement_date、event_effective_date、settlement_code、settlement_ratio 的公司行动，并会为后继代码生成 target_zero_exit_on_next_trade；但转板是同一权益的代码迁移，不应在 2023-07-26 之前追溯改写持仓、价格或收益。映射必须冻结 1:1、官方文件实际公开日、首次进入退市板块日及来源，且 announcement_date 不得用文件所述业务日期代替真实公开可得日期。",
      "verification_method": "src/r004_all_a_style_box/config.py:security_share_settlement_events；src/r004_all_a_style_box/portfolio.py:_normalise_security_events/_apply_effective_security_events/run_china_market_backtest。构造仅含 2023-05-30、2023-06-06、2023-07-25、2023-07-26 四个检查点的最小事件重放：在官方映射公开日之前 state 只能持有 600466；在 event_effective_date 之前不得出现 400165、不得更改 shares/last_price；生效时仅允许 shares_400165=shares_600466×1.0，旧代码数量归零且现金不因代码迁移改变；announcement_date<=processing_date、event_effective_date<=processing_date，并逐日检查无未来价格或未来代码字段进入 selected_for_valuation。预期检查是 1:1 数量链和现金勾稽误差均<=1e-12，且首个 400165 状态只出现在合法生效日。",
      "expected_impact": "critical",
      "confidence": "high"
    },
    {
      "id": "CDX-SO3-02",
      "rank": 2,
      "family": "方法论类",
      "relation_to_history": "历史变体",
      "description": "第二个高概率风险是为了越过 2023-07-06 阻断而全局放宽 maximum_unexplained_price_age_trading_days，或把转板等待期无限标成 holding_restriction。现有 _has_auditable_valuation_path 即使存在 restriction 也只允许年龄<=20，事件结构又没有明确的携带终止日；因此仅增加后继代码仍会在 7 月 26 日之前先阻断。若采用 2023-05-30 当时已知的摘牌后 45 个交易日内转入股转系统规则，0.40 元最后 mark 只能作为事件专属 transfer_pending 的有界临时估值：从 2023-06-06 起持续到首次可观察后继行情或官方期限孰早，不得改动全局 20 日参数，也不得在期限届满后继续携带。",
      "verification_method": "src/r004_all_a_style_box/config.py:maximum_unexplained_price_age_trading_days=20/security_holding_restriction_events；src/r004_all_a_style_box/portfolio.py:_has_auditable_valuation_path/_is_unexplained_missing_price_residual/run_china_market_backtest。用真实交易日历逐日重放 2023-06-05 至 2023-07-26，并为转板事件显式提供 announcement_date、carry_start、carry_deadline/first_trade_date：预期普通无事件证券在 age=21 仍 blocking，600466 仅在公开规则覆盖的 transfer_pending 区间保留 0.40 mark 且 valuation_selection_reason 明示事件上限；2023-07-26 有后继观察后必须结束 carry；若截至官方期限仍无 400165 可观察价则转为 unpriced/blocking，不能回退到永久 last mark。",
      "expected_impact": "critical",
      "confidence": "high"
    },
    {
      "id": "CDX-SO3-03",
      "rank": 3,
      "family": "方法论类",
      "relation_to_history": "全新假设",
      "description": "首个可观察 400165 行情不必然等于首个可卖日。2023-07-26 的 0.38 元相对 600466 最后 0.40 元恰为 -5%，存在触及退市板块价格下限、集合竞价卖单排队而不能假定成交的风险；仅看到正成交量不能证明策略卖单可成交。现有 load_daily_mark_prices/daily_can_sell 依赖本地 suspend 与 decline_limit，但外部 400165 没有这两张本地状态表；_execute_delisting_risk_exit 又会在 daily_can_sell=True 时一次卖完。必须冻结退市板块交易频率、集合竞价、参考价/涨跌幅限制与交易状态，先把 7 月 26 日作为可观察 mark，再仅在真实可卖约束通过的首日退出。",
      "verification_method": "src/r004_all_a_style_box/portfolio.py:load_daily_mark_prices/_execute_delisting_risk_exit/_stamp_tax_rate；src/r004_all_a_style_box/config.py:commission_rate=0.0003/slippage_rate=0.0005/stamp_tax_before_2023_08_28=0.001。最小验证冻结 2023-07-26 及其后至少一个 400165 交易日的 prior/reference price、OHLC、成交量、成交额、交易状态和适用涨跌幅规则；先检查 0.38/0.40-1=-5% 是否构成 decline_limit。若是，则 7 月 26 日 daily_can_sell 必须为 false、只能用 0.38 估值，退出顺延到首个非停牌、非跌停、VWAP 有效且成交量为正的集合竞价日；若不是，才允许当日退出。成交日逐项检查 shares 不超过按字段单位换算的真实成交量，VWAP=turn_value/(volume×volume_unit_multiplier) 且位于 OHLC，gross_notional=shares×VWAP，成本严格沿用冻结的佣金、滑点和卖出印花税公式，不另调成本迎合收益。",
      "expected_impact": "critical",
      "confidence": "medium"
    },
    {
      "id": "CDX-SO3-04",
      "rank": 4,
      "family": "数据口径类",
      "relation_to_history": "全新假设",
      "description": "第三方行情若直接拼入 ashare_stock_price/trade 或只保存清洗后 Parquet，会把网络源伪装成本地全 A 数据且无法复核字段单位。东方财富 volume=57,537、turn_value=2,186,406 只有在 volume 单位按手并乘 100 后才得到约 0.38 元；单位误判会得到约 38 元。现有 data_pipeline.py:_source_catalog 只记录路径、行数和日期范围而无原始响应 hash，assert_m1_invariants 还要求所有来源都位于 data_root；portfolio.py:load_daily_mark_prices 只读取既有 A 股五张表，并用前复权/未复权双表校验 VWAP。若为通过校验而覆盖本地文件、伪造 adj_factor 或静默联网补数，会破坏来源边界和可重复性。",
      "verification_method": "src/r004_all_a_style_box/data_pipeline.py:_source_catalog/assert_m1_invariants/_adjusted_vwap_panel；src/r004_all_a_style_box/portfolio.py:load_daily_mark_prices；templates/data_catalog.md:A股个股行情与交易。为 400165 建独立只读 frozen_successor_quote source，而非改写三张本地 A 股 Parquet；冻结原始 HTTP 响应字节、URL/secid/请求参数、抓取时间、HTTP 状态、SHA-256、解析器版本、字段名/类型/单位、代码、行数、起止日及标准化文件 hash。最小检查要求断网重放得到完全相同的 2023-07-26 OHLC=0.38、volume=57,537、turn_value=2,186,406 和约 0.38 VWAP；source_catalog 明示 external_vendor_used=true、覆盖仅限 400165 转板链，原本地 A 股文件 hash 不变；对该独立源设置受限白名单，而不是取消 assert_m1_invariants 对任意外部路径的拒绝。",
      "expected_impact": "major",
      "confidence": "high"
    },
    {
      "id": "CDX-SO3-05",
      "rank": 5,
      "family": "其它",
      "relation_to_history": "全新假设",
      "description": "比东方财富冻结行情更可信且不牺牲可实现性的唯一候选，是取得全国股转系统或其授权行情源的同日官方成交文件，并以官方源替代第三方价格；当前必读资料没有显示本地已有该文件。仅用上交所/股转系统的转板公告只能证明代码、日期和交易制度，不能生成成交 VWAP；按 0.38 收盘价、600466 最后价、零值或假设 VWAP结算都不是可信替代。如果官方日行情无法取得，冻结第三方原始响应并与官方转板文件交叉约束是完成全 NAV 的次优可审计路径；完全不用第三方且坚持现有本地数据时，唯一诚实结果仍是从 2023-07-06 起 blocked/不可估值。",
      "verification_method": "templates/data_catalog.md:A股个股行情与交易/常见数据缺口；src/r004_all_a_style_box/data_pipeline.py:_source_catalog；src/r004_all_a_style_box/portfolio.py:load_daily_mark_prices。最小验证按来源优先级比较同一 2023-07-26 记录：若可获得官方/授权日行情，要求代码、日期、OHLC、成交量、成交额、交易状态与字段单位完整，并对原始文件做 SHA-256；与第三方冻结记录逐字段核对，金额/量重算 VWAP 误差<=1e-12 后优先官方源。若官方源缺任一成交字段，则不得用公告补造价格；保留第三方冻结源的完整 provenance，或在不接纳该源时维持 blocking，不生成完整 R4/R7/R10/SA4。",
      "expected_impact": "major",
      "confidence": "medium"
    }
  ]
}
