# r004_all_a_style_box 实现审计（m3）

## 审计范围与冻结点

- mode：`code`
- milestone：`m3`（组合、成本与中国交易约束回测）
- 覆盖矩阵中本 milestone 的全部 `done` 行：F19、B7、B11、SA3。
- 审读分离：未读取 coder 完成汇报；仅依据 `spec.md`、`plan.md`、`assumptions.md`、`coverage_matrix.md`、`portfolio.py`、必要的m1/m2/config接口、相关common模块及 `templates/factor.md`、`templates/data_catalog.md` 独立审计。
- 代码冻结点：全部测试前后，`src/r004_all_a_style_box/portfolio.py` SHA-256 均为 `e13ce3cd626e17ee9edd610b8d1e0ff5ad79f6a816c35b03e0fa20cd58cd0ba5`。
- 方法：逐函数反查执行链；构造含方向性交易限制、无效价格、缺失日估值、税率切换和成本现金缩放的三期对抗夹具；再以本地数据运行两个真实持有月。所有数值均独立重算，不采信实现方声明。

## 当前 milestone 的 done 行逐条核对

| 要素 | 状态 | 当前严重级别 | 公式一致性 | 参数一致性 | 实现位置真实性 | 代码反查与简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F19 | found | 无 | `STYLE_1N` 将每个四箱内部权重除以4，四箱各占25%；空箱额度保留现金且不向其余箱再归一化 | 固定 `1/len(STYLE_BOXES)=1/4` 与 `plan.md:163,197` 及F19替代口径一致 | `portfolio.py:105-226` 存在且有实质逻辑，不是空壳；coverage映射见 `coverage_matrix.md:56` | 3箱边界独立得到投资权重0.75、现金目标0.25；未发现六因子或ML权重私货 | F19实现成立 |
| B7 | found | 无 | 以T信号、下一交易日VWAP调仓；月度按相邻执行VWAP结算，日度逐交易日按前复权close估值；交易、现金、持仓和成本为有状态前推 | OOS持有月2023-04至2025-12、月调仓日记账与 `plan.md:179-196,231-236`、AS11/AS12一致 | `run_china_market_backtest` 与 `select_formal_oos` 均存在并实际执行，证据见 `portfolio.py:781-1061,1138-1173`；coverage映射见 `coverage_matrix.md:65` | 无训练、拟合或调参分支；正式切片只按m1冻结的 `sample_phase`，未硬编码收益结果 | B7实现成立 |
| B11 | found | 无 | 生成BV/BG/SV/SG、同池流通市值加权ALL_A及四箱1/N；逐日、逐月分别计算 `SMB=(SV+SG-BV-BG)/2`、`HML=(SV+BV-SG-BG)/2`、`GML=-HML` | 四箱定义、全A同池口径和因子算式与 `plan.md:149-163`、AS8/AS20一致 | `build_portfolio_targets`、`calculate_style_factor_returns` 均存在且有实质逻辑，证据见 `portfolio.py:105-226,1064-1117`；coverage映射见 `coverage_matrix.md:69` | 净/毛、日/月四组因子均独立逐期重算一致；未引入宏观、质量、动量或ML组合 | B11实现成立 |
| SA3 | found | 无 | 冻结式前推只使用当期状态和已观察历史价格，正式OOS切片不重估参数、不重跑交易 | 冻结截止2023-03-31，正式OOS 2023-04-01至2025-12-31，与 `config.py:25-30`、AS11/AS24一致 | `run_china_market_backtest` 与 `select_formal_oos` 均存在且非空壳，coverage映射见 `coverage_matrix.md:85` | 静态扫描未发现负向shift、训练、优化或结果常量；真实双月切片仅保留2025-11、2025-12 | SA3实现成立 |

## m2白名单接口与T/T+1时点

- m2输入边界：`build_portfolio_targets` 只从 `m2.box_memberships` 取 `signal_date`、`stock_code`、`style_box`、`target_weight`；执行日、持有月、样本阶段、全A资格及市值全部由m1显式取得，证据见 `portfolio.py:116-194`。
- 最新白名单适配：对抗测试传入的m2成员表刻意不含 `execution_date`，仍成功从m1回接并形成全部六组合；未发现依赖旧m2透传字段。
- 信号滞后：合成成交最短为信号后1个自然日；真实两期分别为2025-10-31→2025-11-03、2025-11-28→2025-12-01，独立以交易日历确认执行日均为T后的首个交易日。所有真实及合成交日期均严格晚于信号日。
- VWAP来源：成交价只取m1的 `execution_vwap` 且要求 `execution_vwap_valid`，证据见 `portfolio.py:351-353,388-399,458-478`；真实30,688笔成交均满足 `shares × vwap = gross_notional`。

## 日频估值与无前视复核

- `load_daily_mark_prices` 只读 `common.data_loader.load_stock_price_forward` 的前复权close与交易日历，读取范围为首个执行日至最终收益端点，证据见 `portfolio.py:229-269`、`common/data_loader.py:67-101,168-192`。
- 状态仅在当前循环日期观察到正价格后更新；缺价时沿用 `last_prices`，代码没有 `bfill/backfill` 或负向shift，证据见 `portfolio.py:706-722,840-850,866-868,979-1005`。
- 合成反例：BV持仓000001在2023-08-24缺价，但2023-08-25存在未来价格100；8月23和24净值均为0.9992006394884094，8月25才变为9.992006394884093，证明未来价格未被回填到缺失日。
- 真实双月：44个实际交易日、6个长组合，共264条日频记录，每个交易日恰有6行；估值阶段同时包含每日前复权close和最终return VWAP，不是月端点重复伪装。真实持仓 `price_source_date > effective_date` 为0条。

## 交易约束、旧仓与现金

| 对抗场景 | 独立结果 | 证据定位 | 判定 |
| --- | --- | --- | --- |
| 涨停买入 | 目标订单完全未成交，原因 `limit_up_cannot_buy`，同键无虚构成交 | `portfolio.py:295-311,457-529` | 通过 |
| 跌停卖出 | 旧仓000001在2023-08-25卖出受阻，未成交原因为 `limit_down_cannot_sell`，调仓后持仓仍为正；2023-08-28恢复后才卖出 | `portfolio.py:382-450,532-540` | 通过 |
| 停牌 | 买入完全未成交，原因 `execution_suspended` | `portfolio.py:299-306,457-529` | 通过 |
| 无量 | 买入完全未成交，原因 `execution_no_volume` | `portfolio.py:301-306,457-529` | 通过 |
| VWAP无效 | 不使用信号收盘价替代成交，完全未成交并记 `invalid_execution_vwap` | `portfolio.py:305-306,351-360,457-529` | 通过 |
| 现金残留 | 首期BG有50%目标因涨停买不进，调仓后现金权重为0.4997999199679872；实际股票权重与现金权重逐事件合计均为1 | `portfolio.py:612-640,671-691` | 通过 |

- 合成测试共41笔成交、40条未成交；六类原因 `execution_no_volume`、`execution_suspended`、`insufficient_cash_after_costs`、`invalid_execution_vwap`、`limit_down_cannot_sell`、`limit_up_cannot_buy` 均由对应事实触发。
- 每条未成交均满足 `requested_shares - filled_shares = unfilled_shares > 0`；完全未成交订单与成交表不存在同日期、组合、股票、方向的伪造成交键。
- `coverage.unfilled_order_count` 和 `unfilled_notional` 与未成交明细按日期/组合独立汇总完全一致；真实双月6,537条未成交的覆盖汇总亦逐组一致。

## 成交、成本、现金和权重逐笔勾稽

| 检查项 | 独立结果 | 证据定位 |
| --- | --- | --- |
| 佣金 | 每笔买卖 `commission_cost/gross_notional=0.0003` | `config.py:32-37`；`portfolio.py:397-420,476-498` |
| 滑点 | 每笔买卖 `slippage_cost/gross_notional=0.0005` | `config.py:32-37`；`portfolio.py:397-420,476-498` |
| 印花税 | 买入均为0；2023-08-25卖出为0.001，2023-08-28卖出为0.0005；真实2025卖出均为0.0005 | `portfolio.py:98-102,378-420` |
| 成本拆分 | 每笔及逐事件均满足 `total_cost=commission+slippage+stamp_tax`，成本表与成交表按日期/组合汇总全等 | `portfolio.py:560-570,657-665,1181-1210` |
| 现金流 | 买入 `net_cash_flow=-(notional+cost)`，卖出 `net_cash_flow=notional-cost`；合成及真实成交逐笔全等 | `portfolio.py:401-420,479-498` |
| 权重 | 每个调仓事件股票实际权重与现金权重之和均为1；合成及真实日频净现金均不低于容差下限 | `portfolio.py:572-640,1202-1220` |

- 成本现金缩放专项：单位净值、单股100%目标、价格10时，请求名义额1；实际成交0.9992006394884094，佣金与滑点合计0.0007993605115907275，成本缩放残余名义额0.0007993605115906577，净现金为0。残余被记为部分成交且原因为 `insufficient_cash_after_costs`，数量和金额均真实，不与停牌/涨跌停等市场不可交易原因混淆。
- 真实双月：30,688笔成交，其中买入22,906笔、卖出7,782笔；成交成本总额0.005550833369181493，日频最小净现金为0，所有逐笔及汇总等式通过。

## 组合与因子恒等式

- 目标组合完整：BV、BG、SV、SG、ALL_A、STYLE_1N六个长组合均由同一有状态执行器处理，证据见 `portfolio.py:28-30,854-914`。
- 全A使用m1同一eligible池的流通市值权重，非正或缺失流通市值退回总市值，证据见 `portfolio.py:158-183`。
- 合成对抗得到5个交易日×6组合=30条日频记录、3期×6组合=18条月频记录；日/月、净/毛四种口径的SMB/HML/GML均由四箱独立重算一致，且GML逐期严格等于-HML。
- 真实双月得到12条月频组合记录和138条因子记录；138=`44日×3因子 + 2月×3因子`，逐期独立重算无差异。

## OOS冻结、common复用与硬编码反查

- 配置集中冻结 `freeze_end=2023-03-31`、`oos_start=2023-04-01`、`oos_end=2025-12-31`，交易成本亦只来自config，未在回测函数散落第二套参数，证据见 `config.py:25-43`。
- `select_formal_oos` 只切片所有带 `sample_phase` 的m3表，不重新估计或重跑；真实双月切片只含2025-11和2025-12且所有相关行均为 `formal_oos`。
- m3复用common的前复权行情和交易日历加载器；common现有因子回测只提供简化分组收益/平均换手，不具备方向性涨跌停、旧仓延续、现金和逐笔税费状态机，因此本策略专属执行器未重复实现可直接复用的同等common能力。
- 静态反查未发现 `bfill/backfill` 调用、负向shift、训练/拟合/优化、未来收益输入、硬编码净值或结果常量；模块不写 `output/`。

## Issues

本次审计未发现当前 issue。

## 五维度已检查清单与结论

- 公式一致：已核对四箱、全A、四箱1/N、SMB/HML/GML、交易数量、现金、净毛收益和逐日/逐月净值链；合成与真实数据均独立重算通过。
- 参数一致：已核对T+1 VWAP、月调仓日记账、佣金3bp、滑点5bp、印花税切换日与10bp/5bp、现金收益0及OOS区间；均与plan、assumptions和config一致。
- 实现位置真实：F19、B7、B11、SA3的coverage位置全部存在且不是 `pass`/`TODO` 空壳，并在真实入口执行。
- 代码反查：已从m2信号键回接m1、日频价格状态、方向性交易限制、未成交、成本/现金、因子合成、OOS切片及common复用逐层反查；未发现未来填充、禁用分支、重复common实现或硬编码结果。
- 简化声明：单位净值、连续份额、无最低5元佣金、现金收益0、空箱额度留现金及成本缩放均与冻结计划或代码合同一致；未发现新增且未登记的核心简化。

verdict: pass
