# r007 m4 实现对照审计

- mode: `code`
- milestone: `m4`
- 审计范围: coverage matrix 中 m4 的全部 `done` 行，即 `F20–F24`、`B9–B10`、`R1`、`R3`、`R4`
- 审读边界: 只读取 plan、spec、coverage matrix、assumptions AS8/AS9/AS14/AS15、`templates/ml.md`、m1–m3 接口及 m4 实现；未读取或采信 coder 完成汇报；未运行正式全期回测
- 实现文件: `common/ml_portfolio.py`、`common/backtest.py`、`src/r007_cross_market_return_forecasting/{portfolio_pipeline.py,backtest_pipeline.py,config.py}`，并反查 `data_pipeline.py`、`graph_pipeline.py`、`model_pipeline.py`、`strategy.py`
- 审计结论: 实现位置均存在且非空壳；组合算式和两类基线的正常路径与 spec 基本一致，但空预测路径、十模型方向完整性/双方向门槛存在 major 问题，因此本 milestone 不通过。

## 一、m4 全部 done 行五维逐条核对

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| F20 日度 PnL | `common/ml_portfolio.py:1342-1348,1382-1386,1395-1419` 按 `sign(prediction) × actual_return × min(0.001×历史成交金额,L)` 逐股贡献后求和 | `0.001`、目标市场币种上限和成本前口径均由配置传入并校验 | coverage 指向的 `run_signed_liquidity_portfolios` 存在且有真实计算 | m1 的历史成交金额列经 m4 合并后进入 common 组合函数；合成重算最大差为 0 | 成交金额解释已登记 AS9；无额外成本假设 | 通过 |
| F21 年化 Sharpe | `common/ml_portfolio.py:1162-1190` 使用日度 PnL 均值、样本标准差及 `sqrt(252)` | `annualization_days=252`；不足观测与零波动分别标记状态，零波动不伪造为 0 | coverage 指向的 `_annualized_pnl_record` 存在且非空壳 | 两日合成路径逐组合独立重算，Sharpe 最大差为 0；常数 PnL 返回 `annualized_sharpe=NaN, sharpe_status=zero_volatility` | 未发现未登记绩效美化 | 通过 |
| F22 非图同市场基线 | `backtest_pipeline.py:250-310` 为每股构造 `t-1…t-25`；`313-485` 复用滚动回归批接口生成十模型预测 | 25 个滞后、250 日历史训练、10 日更新、目标 OPCL 均与 spec/plan 一致 | coverage 所列 `iter_non_graph_autoregressive_predictions` 存在且非空壳 | 训练日期严格小于锚点；合成 30 日序列在第 26 日得到 `lag_1=24, lag_25=0`，`actual_return` 为当日 OPCL | AS15 的固定模型参数由 m3 工厂复用；无新模型参数 | 通过 |
| F23 图结构同市场基线 | `backtest_pipeline.py:113-152,184-247` 以同市场前一交易日为源、下一目标交易日为响应，并复用 m2 图和 m3 十模型接口 | `same_market_lag=1`；图窗 250 日、更新 10 日继承 m2/m3 | coverage 所列 `iter_same_market_graph_predictions` 存在且非空壳 | 合成日历第 26 个目标日的 `source_date` 等于前一目标交易日；图快照训练映射严格早于锚点 | AS14/AS15 已登记；无额外 top-n 或模型调参 | 通过 |
| F24 六个绝对预测收益嵌套组合 | `common/ml_portfolio.py:1342-1386` 仅按 `abs(prediction)` 降序，股票代码只作同值确定性裁决；相邻集合包含关系有独立审计 | 六比例固定为 `1/0.8/0.6/0.4/0.2/0.1` | coverage 所列两个实现位置均真实 | 11 只合成截面得到 `11/9/7/5/3/2`，成员数、相邻嵌套和排名审计均一致 | AS14 说明无预测股票退出候选；未发现额外 top-n 或实现收益排序 | 通过 |
| B9 不计交易成本与摩擦 | PnL 字段明确为 `before_cost`，`transaction_cost_rate` 必须等于 0 | `config.py:506,526-527` 与 `common/ml_portfolio.py:1148-1149` 双重校验 | coverage 两处实现均真实 | 无成本扣减或隐式摩擦分支 | 与 spec 一致，无未登记简化 | 通过 |
| B10 仓位金额上限 | `position=min(0.001×historical_liquidity, position_cap)` | US=`100000 USD`、CN=`1500000 CNY`，按 `target_market` 映射 | coverage 指向配置与 common 计算均真实 | 合成 CN 大额流动性记录被截为 1500000；普通记录按 0.001 缩放 | AS9 已登记量纲 | 通过 |
| R1 US→CN Sharpe 量级 | `portfolio_pipeline.py:492-558` 只输出观测 Sharpe、距 1/2 的差和多数分位比例 | 强模型名单与 spec 的 RIDGE/LGBM/两个 ensemble 一致 | coverage 指向 `build_core_comparison_tables`，真实存在 | 输出明确写明不从 Figure 8 估读精确柱高；未填造研报精确值 | AS8/AS15 已登记 | 通过 |
| R3 CN→US 显著更弱 | `portfolio_pipeline.py:560-588,629-655` 只做同 feature/model/portfolio 的方向配对和差值 | 未另造“显著”数值阈值，保留方向比例与均值差 | coverage 指向真实函数 | 正常双方向输入可形成一一配对；但单方向输入静默产生 0 个配对，且方向可混拼通过十模型门槛，见 CA-A02 | AS8 已登记；双方向完整性未作为门槛 | 有问题 |
| R4 图结构与跨市场信息增量 | `portfolio_pipeline.py:590-627,656-685` 计算同市场图减非图、跨市场图减同市场图及跨市场是否总体最大 | 三规格名称固定且在共同日期/股票交集后比较 | coverage 指向真实函数 | 三规格合成输入只保留共同股票；输出仅为相对排序和差值，不伪造图中数值 | AS8 已登记 | 通过，但依赖 CA-A02 的方向完整性修复 |

## 二、公式、参数与时点独立重算记录

| 检查项 | 独立输入/重算 | 实现输出 | 结论 |
| --- | --- | --- | --- |
| 六组合成员数 | 单日 11 只，独立按实现的确定性成员数规则重算 | qr1–qr6=`11/9/7/5/3/2` | 数学实现一致，六组齐全 |
| 绝对预测排序 | 预测为 `11,-10,9,-8,…,1`，实现收益刻意另设顺序 | 排名为 `S00,S01,…,S10` | 排序未使用实现收益 |
| sign 与单股贡献 | 逐行独立算 `sign(pred)×actual×min(0.001×liquidity,1500000)` | 所有日期/组合最大绝对差 `0` | 通过 |
| 日度与累计 PnL | 独立逐日求和再 `cumsum` | 最大绝对差 `0` | 通过 |
| Sharpe | 独立以 `ddof=1` 日度标准差及 `sqrt(252)` 重算 | 最大绝对差 `0` | 通过 |
| 零波动 | PnL=`[2,2,2]` | `NaN`，状态 `zero_volatility`，总 PnL=6 | 通过 |
| 十模型整组门槛 | 同一观测提供十模型；另删去第十模型 | 完整组保留 10 行；残缺组状态为 `dropped_incomplete_model_set` 且保留 0 行 | 正常单方向路径通过 |
| 三规格共同样本 | A 同时存在三规格；B 只存在两规格；每规格每观测十模型 | 仅保留 A，共 30 行 | 通过 |
| canonical 空预测 | m3 固定 schema 空表经 `prepare_portfolio_predictions` 后进入完整性筛选 | pandas 3.0.3 抛 `NotImplementedError` | 不通过，见 CA-A01 |
| 混方向十模型 | 同一 observation 的前五模型标 US→CN、后五模型标 CN→US | 10 行全部标记 `kept`，下游每方向仅五模型 | 不通过，见 CA-A02 |
| 双方向门槛 | 三规格均只给目标 CN；跨市场只有 US→CN，两日、十模型 | m4 正常运行 60 行；R3 配对数和 summary `comparison_count` 均为 0，未报错 | 不通过，见 CA-A02 |
| 25 日严格历史 | 单股 30 个目标交易日，值为 0…29 | 第 26 日 `lag_1=24, lag_25=0`，signal/source 为前一目标交易日，actual 为第 26 日 OPCL | 通过 |

## 三、T+1、actual_return 与历史流动性证据链

- 历史 21 日成交金额：`data_pipeline.py:882-909` 先 `shift(1)` 再做 21 日滚动中位数，明确排除预测/执行当日；US 金额来自原始 `close×volume`（`714-745`），CN 来自 `turn_value`（`774-798`）。
- 同市场 T+1：`backtest_pipeline.py:127-151` 将目标交易日映射到前一目标交易日，`250-304` 的非图特征只取目标日前 1–25 日；同市场图复用相同映射。
- 跨市场可执行性：m1 因果映射以源市场收盘 UTC 严格早于目标市场开盘 UTC 为门槛（`data_pipeline.py:1143-1206`），m3 预测保留该 `source_date`；m4 将目标日登记为 `execution_date`，源日登记为 `signal_date`（`portfolio_pipeline.py:162-169`）。
- `actual_return`：m3 从目标股票同一 `target_date` 的 `opcl_excess` 取得（`model_pipeline.py:153-178,262-266,416-433`）；m4 再与目标面板同日 OPCL 超额收益逐行比对（`portfolio_pipeline.py:135-158`）。组合使用的是执行目标日开盘到收盘的市场超额收益，不是源日收益或未来收盘后信号。
- m4 的 `audit_execution_timing` 对同市场记录强制 `signal_date < target_date`；跨市场的 UTC 因果判定由上述 m1/m2 映射接口保证。按当前 m1→m3 正常调用链，未发现 actual_return 错位或当日流动性泄漏。

## 四、common 复用与实现位置核验

- 通用的绝对预测排序、六组合成员、方向仓位、成本前 PnL、累计 PnL、Sharpe 和嵌套审计均位于 `common/ml_portfolio.py`；报告专属模块只装配 r007 字段、三规格和 R1/R3/R4 对照，符合 common 复用约定。
- `common/backtest.py` 已反查：m4 的金额 PnL 不是普通等权分组收益，未错误调用其中的 `quantile_backtest`；`common/ml_portfolio.py` 对 `common.backtest.calculate_rank_ic` 的引用属于该文件既有预测诊断路径，不进入本次 signed-liquidity PnL 公式。
- coverage matrix 所列 m4 实现位置全部存在，未发现 `pass`、TODO、空函数或不存在位置。
- `strategy.py` 的公开函数均回映 m3 的 F10–F19/B11；m4 未向 `strategy.py` 添加无法回映要素 ID 的额外策略逻辑。

## 五、issues

### CA-A01

- severity: major
- location: `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:219-230,287-301`
- evidence: m3 canonical 空预测表经 `prepare_portfolio_predictions` 后，空聚合列 `model_set` 为 pandas `StringDtype`；pandas 3.0.3 在第 230 行执行 `Series.eq(frozenset)` 时稳定抛出 `NotImplementedError: eq not implemented for <class 'frozenset'>`。非空但全部被十模型门槛剔除时，后续第 300 行对空 `specification_set` 做相同比较也会抛同类异常。
- 依据: AS14 明确允许无入边目标不产生预测，m3 也以固定 schema 空表表示无入边、样本不足或事务回滚等正常结果；m4 对正常空结果崩溃，未履行下游可消费合同。
- suggestion: 在两个完整性函数入口或空 audit 形成后返回固定 schema 的空结果，或把集合列显式保持为可比较的 object dtype并采用逐元素集合比较；增加 canonical 空预测、全部残缺组、三规格空交集三条回归测试。

### CA-A02

- severity: major
- location: `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:25-31,205-230,398-425,560-588,629-655`
- evidence: `OBSERVATION_KEY_COLUMNS` 不含 `direction`，合成输入把十模型拆为五个 US→CN 与五个 CN→US 后仍得到 `status=kept`；另以仅 US→CN、仅目标 CN 的三规格完整输入调用 m4，函数正常输出 60 行，而 R3 配对数与 summary `comparison_count` 均为 0，未拒绝缺失 CN→US。
- 依据: B11 的十模型必须属于同一预测方向，m4 计划明确要求双方向跨市场并完成 R3；当前实现可把混方向模型拼成伪完整十模型，也可把单方向结果静默交给核心对照。
- suggestion: 将 `direction` 纳入十模型完整性键并校验 `specification + target_market → expected direction`；在运行组合和构建 R3 前强制存在 US→CN/CN→US 两方向、CN/US 两目标市场及可配对的 feature/model/portfolio，缺失时显式失败。

## 六、已检查维度结论

- [x] 公式一致：逐条核对 F20–F24、B9–B10、R1/R3/R4；独立重算 sign、仓位、贡献、日度/累计 PnL、Sharpe 和零波动。
- [x] 参数一致：核对六比例、0.001、US/CN 上限、252、25 日、250 日、10 日、同市场 lag=1、十模型名称及 AS8/AS9/AS14/AS15。
- [x] 实现位置真实：coverage matrix 的 m4 全部 `done` 行均反查到真实函数，无空壳或不存在位置。
- [x] 代码反查：追溯 m1 历史成交金额、m2 因果日历/图、m3 actual_return/十模型到 m4 common 组合和核心对照；发现 CA-A01、CA-A02。
- [x] 简化声明：AS8/AS9/AS14/AS15 均可定位；R1/R3/R4 未估读或伪造精确研报值。

verdict: fail

## 七、第 2 轮定点复核

- 复核日期: 2026-07-27
- 复核范围: 只核 CA-A01、CA-A02、正常六组合及 m4 对 m5 的接口回归；不重开首轮其他已通过维度。
- 代码快照:
  - `src/r007_cross_market_return_forecasting/portfolio_pipeline.py`: `162ce061fcb86318895545f9cfd3d9a76a68cca14e52e478a267e1b709bb49b6`
  - `src/r007_cross_market_return_forecasting/backtest_pipeline.py`: `5a3d364e44a6e46cae1e97fe91c3a1ce74e0905424680d8f4894adb2f59d6fc0`
  - `src/r007_cross_market_return_forecasting/config.py`: `9bfb0265c83c158689fd200c4ba7516941c0a3c518b4a65883f639c4f9586b9d`
- 运行边界: 全部为内存合成输入；未运行正式全期、未读取或写入 `state.json`、未修改代码或 m5 审计文件。官方 smoke 通过替换 `smoke_dir` 在临时目录运行，退出后临时目录自动清理。

### 7.1 CA-A01 定点复核

| 回归 | 最新实现定位 | 独立运行结果 | 判定 |
| --- | --- | --- | --- |
| canonical 空 predictions | `portfolio_pipeline.py:34-65,125-132,247-274,356-370` | m3 固定 schema 空表经 `prepare_portfolio_predictions` 后，完整性筛选返回 `(0,14)` predictions 与 `(0,16)` 固定 dtype audit；三规格对齐返回 `(0,11)` 固定 dtype audit；全程无异常 | pass |
| 全部十模型残缺 | `portfolio_pipeline.py:291-353,356-370` | 三规格×CN/US 共 6 个观测组均仅给 9 模型；输出 predictions 为 0 行，6 行 audit 全部为 `dropped_incomplete_model_set`，继续对齐得到固定 schema 空表，无 `frozenset` 比较异常 | pass |
| 空表 schema | `MODEL_COMPLETENESS_AUDIT_DTYPES`、`COMPARABILITY_AUDIT_DTYPES` | 列顺序与逐列 dtype 均和常量定义完全相等；集合列固定为 `object` | pass |

结论: CA-A01 已解决。空输入和门槛剔除后的空输入都走显式早返回，不再触发 pandas 3.0.3 的 `Series.eq(frozenset)`。

### 7.2 CA-A02 定点复核

| 回归 | 最新实现定位 | 独立运行结果 | 判定 |
| --- | --- | --- | --- |
| direction 纳入十模型键 | `portfolio_pipeline.py:25-32,247-315` | `OBSERVATION_KEY_COLUMNS` 已包含 `direction` | pass |
| 5+5 混方向 | `portfolio_pipeline.py:291-330` | 同一规格/市场/日期/股票的五个 US→CN 模型与五个 CN→US 模型被拆为两个组；前者为 `dropped_incomplete_model_set`，后者为 `dropped_direction_contract_mismatch`，保留 0 行 | pass |
| 三规格按方向对齐 | `config.py:576-606`；`portfolio_pipeline.py:356-450` | 双方向、三规格、两日合成输入共 120 行全部保留；对齐 audit 共 4 行，逻辑方向恰为 US→CN/CN→US，每行三规格齐全且 `model_row_count=30` | pass |
| 仅单方向组合入口 | `portfolio_pipeline.py:454-522,587-631` | 仅目标 CN 的三规格输入被 `DirectionContractError` 阻止；异常携带 6 行 audit，其中 CN 三腿为 `complete`、US 三腿为 `missing_expected_direction` | pass |
| 仅单方向 R3/R4 入口 | `portfolio_pipeline.py:673-765` | 从完整结果中过滤为仅目标 CN 的 Sharpe 后，`build_core_comparison_tables` 被 `DirectionContractError` 阻止并携带同结构 6 行 audit | pass |
| 完整双方向 R3/R4 | `portfolio_pipeline.py:835-1027` | 三规格×CN/US 双方向完整输入正常产出；R3 一一配对 60 行、R4 分方向三规格配对 120 行，两个 summary 的 `comparison_count` 分别为 60、120；方向合同 6 行均为 `complete` | pass |

结论: CA-A02 已解决。十模型完整性在实际方向内判定，三规格按跨市场逻辑方向分腿取共同样本；核心 m4 对单方向输入显式失败并保留 audit，对完整双方向正常形成 R3/R4。

### 7.3 正常六组合回归

- 合成 11 只股票、2 个交易日，qr1–qr6 成员数为 `11/9/7/5/3/2`。
- 相邻集合 `is_nested` 与 `member_count_matches_expected` 全部为真。
- 独立逐股重算 `sign(prediction) × actual_return × min(0.001×historical_liquidity, 1500000)`，与日度 PnL 最大绝对差为 0。
- 六条 Sharpe 均为 `sharpe_status=ok`。

结论: CA-A01/CA-A02 修复未破坏正常六组合、成本前 PnL 或 Sharpe 接口。

### 7.4 m5 接口与 smoke

- 官方 `run_smoke` 使用临时目录运行成功，产出 28 个文件，`artifact_manifest.json`、`metrics.json`、`comparison.json`、`backtest_summary.xlsx` 均存在；未写正式结果目录。
- 定点调用发现 m5 SA4 的既有单方向调用与 m4 新严格双方向入口冲突，证据如下。该问题所有权位于 m5 `main.py:_run_sa4`，按 milestone scope 不计入本次 m4 verdict，移交 m5 审计处理。

### CA-A03（scope 移交 m5）

- severity: major
- location: `src/r007_cross_market_return_forecasting/main.py:789-846`；`src/r007_cross_market_return_forecasting/portfolio_pipeline.py:587-631`
- evidence: `_run_sa4` 在第 819–838 行只准备/保留目标 CN 的 cross、same-market graph、non-graph 三规格，再调用严格要求 CN/US 双腿的 `run_m4_portfolios`。以两日、十模型的 m5 SA4 形状合成输入亲自调用真实 `_run_sa4`→真实 `run_m4_portfolios`，稳定抛 `DirectionContractError`；异常 audit 为 CN 三腿 `complete`、US 三腿 `missing_expected_direction`，在 SA4 写出前终止。
- 依据: CA-A02 要求 m4 核心 R3/R4 必须严格双方向，该默认门槛本身正确；SA4 是 m5 的单方向 OPCL 特征基线比较调用，适配严格入口的责任属于 m5 调用层，不应回退 m4 核心门槛。
- suggestion: m5 SA4 改用不形成 R3/R4 的底层组合接口，或在 m5 内补齐其规格要求的双方向输入；不得放松 m4 核心入口的默认双方向合同。
- scope_disposition: `handoff_to_m5`，不计入 m4 verdict。

### 7.5 第 2 轮已检查维度结论

- [x] CA-A01：canonical 空表、全残缺、固定 schema/dtype 均亲自运行。
- [x] CA-A02：direction 入键、混方向、单方向阻止、双方向完整、三规格分方向对齐、R3/R4 均亲自运行。
- [x] 正常回归：六组合成员、嵌套、PnL 与 Sharpe 未被修复破坏。
- [x] 接口回归：官方临时目录 smoke 通过；m5 SA4 冲突已保留证据并按 scope 移交。
- [x] 首轮五维度结论继续有效；本轮未发现新的 m4 范围内 issue。

verdict: pass
