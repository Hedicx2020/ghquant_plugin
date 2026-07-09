# 实现忠实性审计 · test_v2 · milestone m1（数据准备与公共择时回测框架）

- 审计模式: code（hard 难度，逐条核对 m1 全部要素）
- 审读分离: 仅依据文件独立判断，未采信 coder 任何完成汇报；矩阵内一切事实性声明（交易日数/缺失/周四数/覆盖/T 基准量级）均已亲自重算比对。
- 被审对象: coverage_matrix.md 中 milestone=m1 且状态=done 的 5 行 —— D1 / D2 / D3 / D4 / B1。
- 审计日期: 2026-07-08

---

## 一、逐要素核对表

| 要素ID | 实现位置（独立核验） | 核对结论 | 说明 |
| --- | --- | --- | --- |
| D1 | src/test_v2/data_prep.py:load_treasury_future_main（52-73） | consistent | 真实非空壳（源码17行、无 NotImplementedError）。数据源 financial_future_price.parquet 与 spec D1 一致；7 字段全部命中。主力隔离 `^T\d{4}$ & main_contract==1` 独立验证仅命中前缀 'T'（数据中共存 IC/IF/IH/IM/T/TF/TL/TS，正则正确排除 TF 5Y/TS 2Y/TL 30Y 及股指期货）。收益口径 close_return/settle_return 分别取 pct_of_close_price、pct_of_sett_price（同合约日涨跌幅，规避换月跳空），与 spec「隔日反转基于 settle、成交按 close」一致。独立重算主区间 2037 交易日、close/settle 缺失 0/0（矩阵称「2037交易日0缺失」——吻合）。 |
| D2 | src/test_v2/data_prep.py:load_hs300（80-93） | consistent | 真实非空壳（11行）。数据源 ashare_csiindex_trade.parquet、index_code=000300、字段全命中，与 spec D2 一致。保留全历史（为 m2 基日以来扩窗分位预留），hs300_return=change_pct/100 回退 close.pct_change()。独立重算：对齐国债期货主区间后 hs300_close 缺失 0，2037/2037 一比一对齐（矩阵称「1:1对齐(2037/2037)」——吻合）。 |
| D3 | src/test_v2/data_prep.py:load_bond_index（100-138） | deviation_declared | 真实非空壳（34行）。4 个 CBA 代码与研报名称逐字一致（CBA00102/00602/00902/07702），loader 逻辑正确并如实产出 coverage 表。独立重算 bond_index_quote.parquet 覆盖 available=0/4（矩阵称「0/4」——吻合）。数据缺口已登记 AS5（major-auto），矩阵状态理由标注影响 m3(R5/R6)、验证列=implement。偏差点：D3 作为 core 数据要素实际无本地行情可提供，"done" 语义=loader 已实现且缺口已声明，非"数据可用"——属已声明偏差，非静默简化；下游 R5/R6 复现受阻已透明转交 m3。 |
| D4 | src/test_v2/data_prep.py:load_calendar（145-161） | consistent | 真实非空壳（13行）。复用 common.data_loader.load_trade_calendar（已过滤 IfTradingDay==1），数据源 ashare_tradeday.parquet 与 spec D4 一致。weekday==calendar_weekday(3) 判周四；独立重算主区间周四 412 个（矩阵称「412个周四」——吻合）。F5 周内效应参数就绪，衍生 is_thursday/IfWeekEnd/IfMonthEnd。 |
| B1 | common/timing_backtest.py:signal_backtest（33-80）, timing_metrics（91-181） | consistent | 均真实非空壳（38/78行）。lag 语义：position=sig.shift(lag)、默认 lag=1、首日 fillna(0)，即 T 日信号 T+1 生效并赚取 [T,T+1] 收盘价到收盘价收益——无未来函数，与 spec B1「T 日收盘执行」+ templates/timing.md「T 信号 T+1 执行」一致。cost_bps 默认 0.0（B2 不计费）、periods_per_year=252（templates/timing.md 日频约定 + 参考实现 src/test）。接口签名与 templates/timing.md §4 约定一致（timing_metrics 增补 periods_per_year 关键字默认值，向后兼容）。独立重算 T 基准（signal≡1）量级 vs R1-T 列：年化 2.42%|2.30%、最大回撤 7.57%|7.46%、年化波动 3.90%|3.89%、夏普 0.62|0.59、卡玛 0.32|0.31——量级吻合（年化波动近乎精确，佐证收益序列 scale 正确、换月跳空已规避）。 |

空壳核查结论：D1/D2/D3/D4/B1 五处实现位置经 import + 源码反查均为真实可调用非空壳函数（无 pass 空体、无 NotImplementedError），无空壳；本 milestone 不含 not_found 要素，无需在 coverage_matrix 变更日志登记回退。strategy.py 中 build_interval_seesaw_signal/build_daily_signal/build_reversal_signal 三处 NotImplementedError 均对应 pending 要素（F1/F2=m2、F3=m4），无任何 done 行指向该三处 stub，不构成虚报。

---

## 二、issue 清单

### [CA-A01] build_main_panel 文档与行为自相矛盾，且截断前置历史，m2 滚动/扩窗有落窗风险
- severity: minor
- 证据: src/test_v2/data_prep.py:174-176（docstring）与 :191-193（`return panel.loc[(idx>=main_start)&(idx<=main_end)]` 截断）
- 依据: 注释称"保留主区间外的少量前置历史交给上层做滚动窗口/扩窗分位"，但函数实际只返回 [main_start, main_end] 区间行、丢弃前置历史（末句"本函数只截主区间输出"自我矛盾）。若 m2 的 F1（N_l=120 滚动 + 基日 2004-12-31 以来扩窗分位）直接消费本 panel 的 hs300_return，主区间起点前约 120 日窗口将全 NaN、基日扩窗分位无法回溯。缓解项：load_hs300（80-81）保留全历史，m2 应改从该 loader 取历史重建窗口。非 m1 done 要素缺陷（build_main_panel 为粘合函数、F1 属 m2/pending），登记以警示 m2。

### [CA-A02] timing_metrics 内联 sharpe/win_rate/calmar/盈亏比，未复用 templates §4 点名的 common.utils 助手（已声明、合理）
- severity: minor
- 证据: common/timing_backtest.py:140（sharpe 内联=ann_return/ann_vol）, :149（win_rate 持仓日口径）, :141（calmar 内联）, :150-156（盈亏比内联）；对照 templates/timing.md:35
- 依据: templates/timing.md §4 建议"绩效指标复用 common/utils: calculate_sharpe/calculate_win_rate/calculate_calmar"，实现仅复用 calculate_annualized_return/volatility/max_drawdown，其余内联。三处内联均有正当理由且已在 docstring（91-113 及模块头 9-13）声明：win_rate 采「持仓日(position!=0)」口径——符合 spec R1 择时胜率语义（calculate_win_rate 的全周期口径在此为错，内联为正确所需）；sharpe 用几何年化收益/年化波动（rf=0，与 R1-T 夏普 0.59 独立重算 0.62 相符）；calmar 复用已算 nav/max_dd。属对模板建议的合理偏离、已声明，登记备查，非缺陷。

---

## 三、已检查维度清单（code 五维度，逐项留证）

1. 公式一致 / 未来函数三查：
   - lag 语义：signal_backtest position=sig.shift(1)、首日 0，T 信号 T+1 生效赚 [T,T+1] 收益——无前视（timing_backtest.py:61）。
   - 国债期货收益口径：close_return/settle_return 优先取同合约 pct_of_close/sett_price 规避换月跳空，close.pct_change() 仅作回退；独立核验主区间 pct 字段缺失 0/0，回退分支不触发——换月跳空规避真实有效（data_prep.py:71-72）。
   - 扩窗/滚动只用历史：m1 无信号窗口计算（F1 属 m2）；load_hs300 保留全历史支撑后续扩窗；但见 CA-A01（build_main_panel 截断前置历史，m2 需注意）。
2. 参数一致：config.py 全部 21 项数值/区间逐条反查 spec/assumptions——main 区间 2015-03-24~2023-08-02 与 reversal 区间 2015-03-20~2023-08-02（B1 双区间正确分列落 config）、hs300_code=000300(D2)、future_code_regex 与 main_flag(D1)、long/short_window=120/20 与分位 1/3–2/3 与基日 2004-12-31(F1)、daily 阈值 0.05/0.03(AS1)、reversal_lag/min/max=2/0.0003/0.005(AS4)、seesaw_switch_upper=0.02(AS3)、calendar_weekday=3(F5)、cost_bps=0(B2)、signal_lag=1(B1)、periods_per_year=252(templates/timing.md)、bond_index_codes 四码名(D3)。无孤立魔法数字。
3. 实现位置真实：5 处 done 实现位置经 py_compile + import + inspect.getsource 核验，全部真实可调用、非空壳、无 NotImplementedError（详见第一节与空壳核查结论）。
4. 代码反查（独立重算 vs 声明）：合约前缀隔离仅命中 'T'；主区间 2037 交易日、缺失 0/0、对齐 2037/2037、周四 412、D3 覆盖 0/4——四项矩阵事实声明全部独立复算吻合；T 基准量级五指标与 R1-T 列吻合（波动近精确）。K1 抽查：grep src/test_v2 与 common/ 未命中 R1-T（2.30/7.46/3.89/0.59/0.31）任何硬编码，亦未命中 R7/R11（4.78/54.34/147.29/7.65/2.35/2.04 等）硬编码——T 列由 signal_backtest 实时算出，无预置答案。
5. 简化声明核对：AS5 如实反映 D3 现券行情缺口（0/4，loader 诚实产出 coverage、下游 R5/R6 转交 m3）；strategy.py 三 stub 明确标注 m2/m4、仅对应 pending 要素，无 done 行虚报；data_prep 换月跳空回退分支已注释且实测不触发；未发现未登记的静默简化。软偏离两处（CA-A01/CA-A02）均已在上文登记。

---

verdict: pass_with_issues
