{
  "excluded_hypotheses_confirmed": [
    "已读过 iter_01/diagnosis.md 的「已排除假设」节：已排除“Growth PIT 覆盖不足是主因”，两项 Growth 至少一项有效的月覆盖最低约 98.11%。",
    "已读过 iter_01/diagnosis.md 的「已排除假设」节：已排除“Size 轴或稳定排序造成 2025-03 断点”，断点只出现在估值分量。",
    "已读过 iter_01/diagnosis.md 的「已排除假设」节：已排除“必须缩短 OOS 到 2025-03 以后”，PIT 财务重建可覆盖全部 33 个月。",
    "已读过 iter_01/diagnosis.md 的「已排除假设」节：已排除“增加 Momentum、Quality、Low Volatility、宏观或 ML 才能补覆盖”。",
    "已读过 iter_01/diagnosis.md 的「已排除假设」节：已排除“以未来最后报价日强制卖出”和“退市后一律按零核销”。",
    "已读过 iter_01/diagnosis.md 的「已排除假设」节：已排除“内部算术误差导致 RA-A01/RA-A02”；本轮日月断裂是估值时点和持有期标签不一致，不是旧假设所指的月表内部算术错误。",
    "已读过 iter_01/diagnosis.md 的「已排除假设」节：已排除“RA-A03 只是展示问题”，正式工作簿状态必须与验证结论一致。"
  ],
  "hypotheses": [
    {
      "id": "CDX-SO-01",
      "rank": 1,
      "family": "时点对齐类",
      "relation_to_history": "全新假设（区别于已排除的月表内部算术错误：这里是执行日 VWAP 月界与收盘日收益标签错位）",
      "description": "月收益从本月调仓前 VWAP NAV 开始，并在下次调仓前 VWAP NAV 结束：src/r004_all_a_style_box/portfolio.py:1849-1866、1931-1936。日收益却在调仓完成后以当日收盘 NAV 记入新 holding_month，而分母仍是上一交易日收盘 NAV：portfolio.py:625-627、2213-2235。因此新月第一条日收益混入“上一收盘至本次 VWAP”的旧持仓跨界收益，并包含“本次 VWAP至当日收盘”的新持仓收益；新月日表又不包含月表末端“最后收盘至下次执行 VWAP”的桥接收益。SG/2024-10 的首条日记录正好跨越国庆休市，从而放大为约 9.84%，足以解释该月 11.1855 个百分点的净收益差。reporting.py:411-419 还分别对日频和月频重新累计 NAV，并覆盖原始账本 NAV，使边界差异无法从交付表直接桥接。",
      "verification_method": "在 src/r004_all_a_style_box/portfolio.py:1752-2235 的执行日分支只做一次局部诊断改动：为每个实体保存“本月起始调仓前VWAP NAV、调仓后当日收盘NAV、月内最后收盘NAV、下次调仓前VWAP NAV”四个账本点，并在 reporting.py:271-419 保留为 ledger_net_nav 而不被归一 NAV 覆盖。按“首日收盘/起始VWAP × 月内收盘链 × 末端VWAP/最后收盘”重算每月收益。若假设成立，6个有实际持仓账本的组合共198个实体月与 MonthlyReturns 的误差应降至不超过1e-12，SG/2024-10的11.1855个百分点差异应被两个边界桥接项完整解释；受影响产物为 DailyReturns、MonthlyReturns、新增日月reconciliation证据以及据此重建的R4/R7/SA4。",
      "expected_impact": "major",
      "confidence": "high"
    },
    {
      "id": "CDX-SO-02",
      "rank": 2,
      "family": "方法论类",
      "relation_to_history": "全新假设（不是四箱或因子公式单期算错，而是线性合成与跨期复合不交换）",
      "description": "SMB、HML、GML在 src/r004_all_a_style_box/portfolio.py:2322-2379 中分别从日频四箱收益和月频四箱收益独立做算术组合。一般情况下，逐日计算线性多空收益后再复合，不等于先把四条腿分别复合成月收益后再做线性组合。因此即使六个long portfolio完成日月边界桥接，三个合成因子的日频复合仍不会自然等于月频因子；这解释了审计所见三个因子月末路径也不完全一致。",
      "verification_method": "在 src/r004_all_a_style_box/portfolio.py:2358-2379 做一次诊断性小改动：月频SMB/HML/GML暂时改为按同holding_month复合现有日频因子收益，而四箱和long portfolio保持不变。若假设成立，三个因子共99个实体月的日月差异将机械降至不超过1e-12，而四箱差异不变，R4中的因子相关项和SA4中的因子比较行会改变。该试验只用于确认非交换机制；正式口径应进一步选择“有独立多空资金账本的自融资因子”或“仅发布由月度四腿构造的月因子，并将日因子标为不可复合比较”。",
      "expected_impact": "major",
      "confidence": "high"
    },
    {
      "id": "CDX-SO-03",
      "rank": 3,
      "family": "数据口径类",
      "relation_to_history": "全新假设（历史只诊断陈旧价格无限沿用，本假设解释修正后审计表为何同键出现两套互斥状态）",
      "description": "同键双记录来自两个并行审计生产器。_execute_delisting_risk_exit 在不可卖时写入 age=0、delisting_board_flag=True、risk_exit_waiting_daily_can_sell：src/r004_all_a_style_box/portfolio.py:993-1027；同一天的缺价扫描又写入真实price_source_date、age>0、通常flag=False、risk_exit_known_event_missing_price_observation：portfolio.py:1989-2094。两者随后无角色区分地进入同一security_event_records：portfolio.py:1782、2094、2293。实际估值不由任一审计行直接驱动，而由state.last_prices驱动：调仓估值使用execution_price.combine_first(last_prices)，见portfolio.py:427-445；日频估值使用_update_close_marks后仍保留的last_prices，见portfolio.py:797-813、1983、2213-2216。当前validate_security_event_audit只检查future/stale/blocking标志和结算误差，没有检查状态键唯一性或哪行被选作估值依据：reporting.py:2472-2523。",
      "verification_method": "在 src/r004_all_a_style_box/portfolio.py:997-1027 与2040-2093 各增加record_role和selected_for_valuation两个字段：等待卖出行为记为exit_attempt，缺价/估值观察记为valuation_state，且每个(date,portfolio,stock_code)只允许一条selected_for_valuation=true；在 reporting.py:2472-2523 增加唯一性断言。预期19,598个矛盾状态键降为0，退出尝试仍完整保留，selected估值行的price_source_date/mark应与holdings及state.last_prices一致；该改动本身不应改变收益，若收益变化则说明审计表此前意外参与了估值。",
      "expected_impact": "major",
      "confidence": "high"
    },
    {
      "id": "CDX-SO-04",
      "rank": 4,
      "family": "方法论类",
      "relation_to_history": "历史假设变体（iter_01处理的是无生命周期状态时永久沿用last_price；本机制是新增一个risk-exit事件后，事件存在本身反而永久豁免陈旧估值阻断）",
      "description": "pending_market_exits把所有已生效risk_exit事件永久列入生命周期豁免集合：src/r004_all_a_style_box/portfolio.py:1969-1978。_is_unexplained_missing_price_residual只要has_lifecycle_reason=true，就算目标为0且价格已陈旧数百日也返回false：portfolio.py:1231-1245；零目标强制退出扫描也排除这些代码：portfolio.py:1099-1129。600466在config.py:85-93只有risk_exit_on_next_trade公告，没有终止上市、转板代码、转板报价、现金或换股结算，却因此持续blocking=false。适用于中国市场的可审计处理应是显式生命周期状态机：公告风险、退市整理、终止上市、转板登记、转板可交易、现金/换股结算分别带公告日、生效日、市场代码、价格来源和执行资格。停牌期间可按已披露估值政策携带最后观察价但必须有状态及期限；终止后若没有当时可得的转板行情或明确结算，不得虚构VWAP、未来回看或强制归零，应保留证券数量并将其列为unpriced_asset，market_value和完整NAV设为不可确定，从该日暂停单点收益、R4/R7/SA4，或单列“可估值部分NAV+不可估值份额”。后续真实结算只能从首次可观察日向前生效，不得追溯改写历史。",
      "verification_method": "在 src/r004_all_a_style_box/portfolio.py:1231-1245 做一次小改动，把has_lifecycle_reason改为has_auditable_valuation_path；只有有效停牌状态、尚未生效但参数完整的现金/换股结算，或具备转板代码及当日可观察报价的数据链才为true，单独的risk_exit_on_next_trade不得永久豁免。保持config.py:59的20交易日阈值不变重跑。若假设成立，600466及同类未闭环代码会在超过期限时进入unpriced/blocking清单，而不是继续以2023-06-05价格生成2025年点NAV；补入真实转板/结算映射后才应从对应可观察日解除。受影响产物为security_event_audit、holdings、估值状态表以及该日期后的全部收益与比较指标。",
      "expected_impact": "major",
      "confidence": "high"
    },
    {
      "id": "CDX-SO-05",
      "rank": 5,
      "family": "其它",
      "relation_to_history": "全新假设",
      "description": "CDX-R-01不是底层指标未生成，而是comparison生成器只枚举了每实体annualized_net_return：src/r004_all_a_style_box/reporting.py:1738-1753；SA4只输出benchmark_comparison行数：reporting.py:1774-1781。逐实体annualized_net_volatility和net_sharpe_zero_cash已经由_series_metrics生成，见reporting.py:494-554；16组基准的annualized_excess_return、annualized_tracking_error、information_ratio也已由build_benchmark_comparison生成，见reporting.py:1299-1327。main.py:613-616只是序列化payload，不应承担指标枚举。assert_m4_invariants目前只检查实体集合及键唯一性，没有检查comparison核心键覆盖：reporting.py:1428-1452。",
      "verification_method": "在 src/r004_all_a_style_box/reporting.py:1738-1784 做一次数据驱动扩展：每个monthly performance实体枚举annualized_net_return、annualized_net_volatility、net_sharpe_zero_cash三项，每个benchmark_comparison行枚举annualized_excess_return、annualized_tracking_error、information_ratio三项；同时对required key集合做精确断言。预期comparison新增并完整覆盖27项R10核心值和48项SA4核心值，现有R4/R7及SA4结构记录可另行保留。生成责任应位于m4/reporting层；verifier应从MonthlyReturns独立重算75项核心值并逐键核对至不超过1e-12，再写verification_status/calculation_verified，verify_report的计数随实际键集合更新。美国值继续保持reference_only/not_comparable。",
      "expected_impact": "critical",
      "confidence": "high"
    },
    {
      "id": "CDX-SO-06",
      "rank": 6,
      "family": "参数类",
      "relation_to_history": "全新假设",
      "description": "RA-R03来自披露文字被定义成与运行config无关的静态常量。src/r004_all_a_style_box/reporting.py:134-148把33个月、2025-12和2026-01-05写死；build_metrics_payload虽接收config，却仍直接复制该常量：reporting.py:1700-1727；build_comparison_payload也复制同一常量：reporting.py:1788-1795。hard扰动只在main.py:926-950替换oos_end，因此数值变为32个月而披露不会变化。",
      "verification_method": "将 src/r004_all_a_style_box/reporting.py:134-148 的静态元组替换为build_final_boundary_disclosures(config, terminal_accounting_date)，并让build_comparison_payload在reporting.py:1738接收config；其余逻辑不动。用现有--perturbation-oos-end 2025-11-30重跑后，metrics、comparison及五本工作簿应披露2023-04至2025-11共32个月、末期记账至2025-12-01；正式基线仍应生成33个月和2026-01-05端点。",
      "expected_impact": "minor",
      "confidence": "high"
    }
  ]
}