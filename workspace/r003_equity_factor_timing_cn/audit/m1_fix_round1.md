# m1 第1轮实现修复记录

- 案例: `r003_equity_factor_timing_cn`
- milestone: `m1`
- 修复输入: `audit/impl_audit_m1.md`、`output/r003_equity_factor_timing_cn/verify_report.md`
- 修复范围: `config.py`、`data_pipeline.py`、`strategy.py`、`assumptions.md`、`coverage_matrix.md`
- 边界: 仅执行编译和受限冒烟；未运行完整回测，未形成验证通过结论。

## CA-A01 至 CA-A11 修复映射

| issue | 修复位置 | 修复摘要 |
| --- | --- | --- |
| CA-A01 | `strategy.py:_execution_schedule`；`data_pipeline.py:assert_point_in_time` | 退出日改为下一交易月末后的首个交易日；日程及PIT断言均严格要求 `signal_date < execution_date < return_date`。 |
| CA-A02 | `data_pipeline.py:build_bond_return_proxies` | 国债日值先按月份关联当月交易月末，仅取信号日及之前最后观测；1Y/2Y/10Y收益映射到真实交易月末，2Y原始缺月保持缺失，并输出 `bond_common_available`。 |
| CA-A03 | `data_pipeline.py:calculate_financial_turbulence`；`config.py:ChinaFactorTimingConfig` | 仅当前向量完整且此前连续84行全部完整时计算马氏距离；不再以12个月放行。 |
| CA-A04 | `data_pipeline.py:build_benchmark_features`；`data_pipeline.py:build_macro_features` | 新增截至信号日的中证800 252日年化历史波动率，并与信用利差、期限利差、10年国债收益率共同合成 `financial_risk`。 |
| CA-A05 | `data_pipeline.py:_read_shibor`；`data_pipeline.py:build_macro_features`；`assumptions.md:AS31` | 接入 `bond_shibor.parquet` 的 `SIBO1Y`；三个月变化以SHIBOR优先、PIT LPR回退，两者不可得期保持缺失且不倒填。 |
| CA-A06 | `data_pipeline.py:build_benchmark_features` | 新增中证800 EP/PB扩展历史分位，至少12个月历史后出值，仅使用截至当月的数据。 |
| CA-A07 | `data_pipeline.py:build_benchmark_features` | 三月回撤峰值改为过去三个日历月全部日度收盘价的最高值，不再只比较三个自然月末。 |
| CA-A08 | `strategy.py:_build_signal_panel` | 先在 `factor_history_start` 起的完整月末价格序列上计算12-1 Momentum，再截取正式信号月。 |
| CA-A09 | `strategy.py:_select_factor_constituents`；`strategy.py:_calculate_factor_returns`；`assumptions.md:AS33` | 因子信号先定权，执行状态随后左连接；未执行、入口缺价或退出缺价均保留原权重并按现金0收益处理，逐股票记录状态，不按未来可得价格重归一。 |
| CA-A10 | `config.py:quality_weights`；`strategy.py:_point_in_time_financials`；`strategy.py:_select_factor_constituents` | Quality固定为盈利能力、经营现金流、应计质量、低杠杆、盈利稳定性五项，各20%；仅在当月中证800截面标准化后选最高1/3。 |
| CA-A11 | `data_pipeline.py:_derived_feature_audit`；`data_pipeline.py:build_macro_features` | 为GDP名义同比、短端利率衍生项、金融风险、信用、杠杆、货币政策预期、增长水平/方向和商业周期逐月传播 `source_date/release_date/available_date`。 |

## 新增假设与数据限制

- `AS31`: SHIBOR优先、PIT LPR回退；2015-01至2021-02短端利率代理保持缺失。
- `AS32`: 2015年前六个月852只实际中证800成分中，仅2只在个股估值表有记录；Value/Growth不伪造。
- `AS33`: 未执行或缺价权重按现金0收益留存，信号权重不变。
- `AS34`: 中证800历史波动率采用252日年化口径。
- `AS35`: 中证800 EP/PB采用至少12个月历史的扩展窗口分位。

## 冒烟证据

| 检查 | 结果 |
| --- | --- |
| Python compileall | `src/r003_equity_factor_timing_cn` 编译退出码0。 |
| 全日历日程 | 132个信号月；`execution_date == return_date` 为0；132个月全部严格满足 `signal < execution < return`。 |
| 真实国债共同有效月 | 1Y/2Y/10Y月收益共同非空95个月，首月2015-02、末月2025-12；2Y原始缺月未填充。 |
| 合成金融湍流 | 90个月合成序列的首个非空位置为索引84，即第85个月。 |
| 合成退出缺价 | 两只股票各0.5权重，一只收益10%、一只退出缺价；组合收益为5%、现金权重0.5，未重归一。 |
| 2015受限烟测 | 2015-01至2015-06、80只当期成分：Momentum已形成；Value/Growth因原始PB缺口未形成，其余因子可执行；PIT断言通过。 |
| 2025受限烟测 | 2025-01至2025-06、100只当期成分：每月六因子均形成，共36行因子收益；权重和均为1；严格日程与PIT断言通过。 |
| 衍生字段证据链 | 六个核心衍生字段各有132条逐月审计记录，非空记录中 `available_date > signal_date` 为0。 |

以上均为实现阶段冒烟证据，后续结论由 verifier 与门禁工具独立给出。
