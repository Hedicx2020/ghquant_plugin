# m5 严格样本外结果包独立代码审计

- 审计模式: code
- 案例: `r003_equity_factor_timing_cn`
- milestone: `m5`
- 审计输入: plan m5、spec、assumptions、coverage matrix m5全部done行、`reporting.py`、`main.py`及m1-m4公开接口
- 独立性: 未读取或采信coder完成汇报；默认路径、指标公式、结构断言、临时目录真实单月运行及合成门禁均由审计者独立检查
- 写入边界: 仅写本审计文件；未改代码、`state.json`或`results/`

## 一、结论

m5正式默认入口的核心数据链路真实存在：CLI默认值严格为2023-04至2025-12，共33个月，以2023-03为冻结切点；`main.py`从本地真实数据执行m1，再把真实m1对象依次传给m2、m3、m4和m5，不存在正式路径内的合成数据或伪造图表回退。m5对概率和四组合逐月覆盖、首月2016-04至2023-03训练窗、全部m2/m3训练行84个月及严格过去关系设有硬断言。毛收益为正式主结果，净收益仅作成本补充；R10美国原值与中国OOS结果分栏，并明确中国偏差不是复现误差。绩效、分类、因子预测、Excel、五张PNG、JSON、run log及OOS证据文件均有真实实现，2025-12真实中国市场单月诊断运行成功。

但当前m5代码门禁不通过。plan m5明确要求“累计收益/回撤/胜出概率/特征重要性PNG”，实现只生成ml模板五图，其中没有任何组合回撤PNG；最大回撤虽在JSON/Excel指标中计算，但缺失的图形合同不能由一个标量替代，构成CA-A01 major。另有显式诊断`--end`边界错误：2025-11单月运行在m1构造退出日时失败，构成CA-A02 minor。配置和两阶段参数哈希真实可复算，但配置哈希未纳入实际CLI窗口及m4组合参数，构成CA-A03 minor。

## 二、默认CLI、冻结切点与33个月

### 2.1 默认值和参数边界

- `ChinaFactorTimingConfig`固定`oos_cutoff=2023-03-31`、`oos_start=2023-04-01`、`sample_end=2025-12-31`。
- `_parse_args([])`独立结果为`prediction_start=2023-04-01`、`end=2025-12-31`；月序列严格为33个月。
- `_validate_window`拒绝起点不晚于2023-03、终点早于起点及终点晚于2025-12。
- 显式缩短运行会在run log记录`formal_default_window: False`，coverage也记录`is_formal_default_window=false`，没有把诊断窗口静默标成33月正式窗口。
- 正式默认窗口在`_coverage_and_training_evidence`再次断言必须恰为33个月，概率和组合结果缺月、多月或区间外月份均直接失败。

结论：正式默认区间、冻结切点和33月覆盖门禁通过。

### 2.2 固定84个月及严格过去

审计者构造2023-04至2025-12的33月结构化对象，独立调用正式coverage函数：

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| 目标OOS月份 | 33 | pass |
| 首月预期训练窗 | 2016-04至2023-03 | pass |
| m2首窗 | 2016-04至2023-03 | pass |
| m3首窗 | 2016-04至2023-03 | pass |
| m2全部训练行 | 全部84 | pass |
| m3全部候选月 | 全部84 | pass |
| m2/m3训练结束早于预测月 | 全部true | pass |
| 概率/四组合覆盖率 | 均100% | pass |

把任一m2训练行数改为83后，正式函数抛出`AssertionError`，未静默接受缩短窗口。m2和m3公开实现还分别断言月频输入连续及每个训练窗为连续84个日历月，因此m5不是只信任一个未核对的声明字段。

## 三、m1→m4真实对象接线

`main.run_pipeline`的正式路径依次调用：

1. `build_m1_dataset(run_config)`从`/Users/hedi/local_data`配置的真实Parquet构造m1；
2. `run_stage_one_regime_model(dataset.monthly_features, ...)`消费真实m1月频特征；
3. `run_stage_two_factor_model(dataset.monthly_features, dataset.factor_returns, stage_one, ...)`消费真实m1和m2对象；
4. `run_portfolio_construction(dataset.monthly_features, dataset.factor_returns, stage_two, ...)`消费真实m1和m3对象；
5. `write_result_package(stage_one, stage_two, portfolio, ...)`只消费上述真实结构化结果。

源码中没有`synthetic`、`mock`或失败后生成占位图/随机结果的正式分支；任一阶段异常只追加失败日志并重新抛出。图表全部从m2/m3/m4对象生成，不用随机数或研报R10原值冒充中国结果。

临时目录真实2025-12单月运行得到：m1月频特征132行、因子收益792行，m2/m3各1个预测月，m4为4条组合收益；概率明细目标月为2025-12，组合为CSI800、六因子1/N、商业周期15%倾斜和ML概率权重四类。正式项目`results/`未被写入。

结论：m1→m4真实对象接线及禁止伪造正式输出通过。

## 四、毛收益主结果与成本补充

- m4结果保留`gross_return`、`net_return`、`transaction_cost`、`main_result_basis`和`cost_basis`。
- m5分别调用`_portfolio_metric_table(..., 'gross_return')`与`(..., 'net_return')`，输出`portfolio_gross_primary`和`portfolio_net_cost_supplement`。
- `comparison.json`的中国R10值只取gross表；净成本结果不会替换主比较。
- metrics、Excel口径说明和run log都明确`gross_is_primary=true`、`net_is_cost_supplement=true`。
- 真实单月结果中四组合`main_result_basis`均为gross；CSI800为`index_benchmark_no_stock_cost`，三个股票因子组合为`factor_sleeve_stock_cost`。

结论：AS26的毛收益主结果和中国股票成本补充边界通过。

## 五、指标公式独立重算

审计者用四个月已知收益序列独立重算正式函数，以下最大误差均为0（年化换手仅有浮点误差`4.44e-16`）：

| 指标 | 正式公式 | 结论 |
| --- | --- | --- |
| 年化收益 | `prod(1+r)^(12/n)-1` | pass |
| 年化波动 | 月收益样本标准差`×sqrt(12)` | pass |
| Sharpe | 月均收益/月收益样本标准差`×sqrt(12)`，rf=0 | pass |
| 最大回撤 | 毛/净NAV相对含期初1.0的历史峰值最大跌幅 | pass |
| 年化超额收益 | 月度相对财富收益`(1+rp)/(1+rb)-1`几何年化 | pass |
| 跟踪误差 | 月度相对财富收益样本标准差`×sqrt(12)` | pass |
| 信息比率 | 年化超额收益/年化跟踪误差 | pass |
| 月均换手 | `mean(buy_turnover+sell_turnover)` | pass |
| 年化换手 | 月均双向换手`×12` | pass |

CSI800的超额收益、跟踪误差和信息比率固定为空；其他三组合按相同`signal_period`与CSI800一对一合并。重复组合/月会失败，不会重复计入绩效。

## 六、R10美国原值与中国迁移语义

- `REPORT_R10_VALUES`逐项保留原研报四方法×六指标原值：年化收益8.40%/8.63%/9.84%/11.47%等均与spec R10一致。
- Russell 1000三项n/a保持`null`，不推算差异。
- comparison共24行，逐行包含`report_market='美国'`、`china_market='中国A股'`、原方法、迁移组合、原值、中国OOS值和差异。
- `difference_status='market_transplant_context_only'`且顶层`comparison_semantics='us_reference_vs_china_oos_not_reproduction_error'`；metrics解释字段也明确偏差不是复现误差。
- Excel包含`R10核心对照`、`美国研报R10原值`、`中国OOS毛收益`和`中国OOS成本补充`独立sheet。

结论：R10原值忠实、美国/中国分栏和不可比标注通过。

## 七、Excel、PNG、JSON、日志与OOS证据合同

真实单月临时结果包生成15个文件：

- JSON：`metrics.json`、`comparison.json`、`oos_evidence_manifest.json`；均为严格JSON，NaN/Inf转为null。
- Excel：`backtest_summary.xlsx`及model/probability/weights/returns四份明细；所有sheet冻结首行、表头加粗并自动列宽。summary含14个sheet及5张嵌入图。
- PNG：`feature_importance.png`、`ic_series.png`、`group_cumulative_returns.png`、`train_val_loss.png`、`prediction_scatter.png`；实测均约300 DPI且尺寸非空。
- 日志：`run_log.md`逐阶段记录m1-m5行数、冻结切点、窗口、正式/诊断标志、参数哈希、gross主口径和每月m2/m3训练窗。
- OOS证据：manifest记录覆盖、六项结构断言、12个主要产物大小与SHA-256；审计者逐文件重算哈希全部一致。checklist明确33月、市场迁移、gross主结果与短样本边界。

上述主体合同通过，但未生成plan m5要求的回撤PNG，见CA-A01。

## 八、配置与参数哈希

- metrics中的configuration hash为64位SHA-256；审计者按`asdict(ChinaFactorTimingConfig)`、规范化`data_root`、中文不转义和键排序独立重算，结果完全一致。
- m2/m3各自64位参数哈希同时进入metrics和run log；真实单月两处记录一致。
- 但configuration hash只覆盖基础config，不覆盖CLI实际`prediction_start/end`；m4的15%倾斜和买卖成本虽被代码硬校验并明文写入metrics，也没有进入单独参数哈希。该限制见CA-A03。

## 九、coverage_matrix m5全部done行核对

| 要素 | 实现位置 | 审计结论 |
| --- | --- | --- |
| B5 | `_coverage_and_training_evidence` | 中国迁移OOS概率完整覆盖指定窗口，默认33月，pass |
| B6 | `_coverage_and_training_evidence` | 首月2016-04至2023-03、每月固定84月且严格过去，pass |
| B7 | `write_result_package` | 四组合OOS结果和结果包存在；回撤PNG合同缺失，CA-A01 |
| R10 | `_comparison_table` | 美国原值、中国gross OOS、n/a及不可比语义完整，pass |
| SA3 | `_coverage_and_training_evidence` | 概率/组合逐月覆盖、84月和严格过去均设硬断言，pass |

全部done位置均存在且进入正式调用链；未发现`pass`、`TODO`或完全空壳位置。

## 十、issue清单

### CA-A01

- severity: major
- 证据定位: `workspace/r003_equity_factor_timing_cn/plan.md:184-189`；`src/r003_equity_factor_timing_cn/reporting.py:594-678,1077-1105`
- 依据: plan m5明确要求累计收益、回撤、胜出概率和特征重要性PNG；`create_charts`只生成特征重要性、RankIC、组合累计收益、训练验证损失和预测散点五图，没有组合回撤时序数据或PNG。真实单月结果包也确认不存在任何drawdown/回撤图。JSON中的最大回撤标量不能替代要求的时序图形产物。
- 影响要素: B7及m5完整结果包。
- 通过条件: 从m4 gross主结果逐组合构造含期初1.0的逐月drawdown时序，生成300 DPI中国OOS回撤PNG，并将对应数据和图写入summary workbook、paths及证据manifest；不得用R10原值或合成数据造图。

### CA-A02

- severity: minor
- 证据定位: `src/r003_equity_factor_timing_cn/main.py:104-106`；`src/r003_equity_factor_timing_cn/strategy.py:48-79`
- 依据: CLI公开允许显式缩短为诊断窗口，但`run_config.sample_end`被改为`--end`。当末月最后交易日早于自然月末（实测2025-11-28）时，`signals.max()+MonthEnd(2)`只读到下一自然月末2025-12-31，缺少该日后的退出交易日，真实`2025-11..2025-11`运行报“交易日历不足以构造下一月T+1收益”。默认2025-12因信号日恰为自然月末而可生成至2026-02-02，不受此特例影响。
- 影响要素: 显式缩短的诊断CLI；不影响正式默认33月端点。
- 通过条件: 交易日历读取上界必须覆盖“下一交易月末之后首个交易日”，并为最后交易日早于自然月末的月份增加回归测试。

### CA-A03

- severity: minor
- 证据定位: `src/r003_equity_factor_timing_cn/reporting.py:990-1019`；`src/r003_equity_factor_timing_cn/portfolio.py:60-67`
- 依据: configuration hash真实且可复算，但只哈希`ChinaFactorTimingConfig`；实际CLI窗口和m4 `PortfolioSettings`不在该哈希内，所以不同诊断窗口可共享同一configuration hash，15%倾斜/成本参数也只能靠明文字段和运行时校验追踪。
- 影响要素: 精确运行身份与冻结证据；不改变当前默认结果数值。
- 通过条件: 增加包含基础config、实际prediction_start/end、m4设置及报告层关键常量的run configuration hash，并在metrics、run log和证据manifest一致记录。

## 十一、五维度审计结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | pass | 绩效、超额、跟踪误差、IR、换手、覆盖和训练窗公式独立重算通过 |
| 参数一致 | pass_with_issues | 默认窗口、84月、R10和成本口径一致；完整运行参数未统一入hash |
| 实现位置真实 | fail | m5 done位置主体真实，但plan要求的回撤PNG没有实现位置 |
| 代码反查 | fail | 真实2025-12单月包成功；2025-11诊断端点失败，且结果包缺回撤图 |
| 简化声明 | pass | 中国迁移不可比、33月短样本、gross主结果和袖套成本限制均有明确说明 |

## 十二、已检查维度清单

- [x] m5全部done行B5-B7、R10、SA3逐条核对
- [x] 默认CLI 2023-04至2025-12恰33个月及2023-03冻结切点
- [x] 显式窗口边界拒绝和正式/诊断标记
- [x] 首月2016-04至2023-03、全部m2/m3固定84月及严格过去
- [x] m1→m2→m3→m4→m5真实对象接线和异常不伪造输出
- [x] gross主结果与net成本补充分栏
- [x] 年化收益/波动/Sharpe/MDD/超额/TE/IR/换手独立重算
- [x] R10美国原值、中国迁移结果及不可比标注
- [x] comparison 24行结构与R10 n/a保持为空
- [x] Excel、PNG、JSON、run log及OOS manifest/checklist合同
- [x] configuration、m2、m3哈希及独立重算
- [x] 真实中国2025-12单月结果包与2025-11端点失败复现
- [x] 禁止正式路径使用合成数据或伪造图表
- [x] 五维度：公式一致、参数一致、实现位置真实、代码反查、简化声明

初审结论: fail

## 十三、第1轮修复后复审更新

- 复审范围：CA-A01至CA-A03及m5默认33月合同回归；未读取或采信coder完成汇报。
- CA-A01已关闭：正式结果包新增`drawdown.png`；回撤数据以gross NAV和含期初1.0的逐组合运行峰值计算，合成三期最大误差`5.55e-17`。真实2025-11/12结果均生成约300 DPI非空图片，`backtest_summary.xlsx`新增`图_组合回撤`sheet并各内嵌1张回撤图，summary总嵌图数由5增至6。
- CA-A02已关闭：m1始终用冻结的完整2015-01至2025-12底座构造，仅把预测特征裁到诊断`--end`；真实2025-11和2025-12单月诊断均完整通过并退出0，不再因非自然月末交易日缺少下一期退出日而失败。
- CA-A03已关闭：run configuration hash包含实际`prediction_start/end`、m2/m3参数hash、m4 15%主动倾斜与买卖成本、R9方向、绩效口径、R10原值和16项产物合同；2025-11与2025-12哈希不同，均可从冻结配置与实际运行参数独立重建，并在metrics、manifest、run log一致记录。
- 产物与日志：两个真实诊断目录均恰有16个非空文件且文件名集合精确等于合同；manifest声明16项合同并对13项已完成且内容不再变化的核心产物给出SHA-256，独立逐文件重算全部一致。成功日志包含started/finished双时间、elapsed、完整命令、`exit=0`和artifact_count=16；无效2023-03起点真实进程退出1，失败日志包含同样时间/命令/elapsed及`exit=1`。
- 默认无回归：默认CLI仍为2023-04至2025-12共33个月；合成正式覆盖门禁得到33/33概率与组合月份、首窗2016-04至2023-03、m2/m3全部84月且严格过去，六项OOS证据均通过。

### issue闭环

| issue | 初审 | 第1轮复审 | 状态 |
| --- | --- | --- | --- |
| CA-A01 缺少回撤PNG | major | 回撤数据、PNG、Excel sheet/嵌图及manifest合同全部存在并独立核算 | resolved |
| CA-A02 2025-11诊断日历边界失败 | minor | 2025-11与2025-12真实单月均退出0 | resolved |
| CA-A03 运行hash不含窗口/m4参数 | minor | 窗口、m4参数和报告口径均进入run hash，三处记录一致 | resolved |

本轮没有发现新增issue；详细证据见`impl_audit_m5_reaudit_round1.md`。

### 第1轮复审五维度

| 维度 | 结论 |
| --- | --- |
| 公式一致 | pass |
| 参数一致 | pass |
| 实现位置真实 | pass |
| 代码反查 | pass |
| 简化声明 | pass |

verdict: pass
