# m4 四类组合与中国商业周期基准独立代码审计

- 审计模式: code
- 案例: `r003_equity_factor_timing_cn`
- milestone: `m4`
- 审计输入: plan m4、spec、AS41、coverage m4全部done行、`portfolio.py`及m1/m3公开接口
- 独立性: 未读取或采信coder完成汇报；R9、权重、收益、换手、成本、日期和累计净值均由审计者用合成数据及真实中国小窗独立重算
- 写入边界: 仅写本审计文件，未改代码、`state.json`或`results/`

## 一、结论

m4四组合主链路基本正确：中证800、六因子1/N、商业周期15%倾斜、ML概率权重四类定义完整；R9四周期方向矩阵与spec逐格一致；15%被实现为相对1/N的主动权重L1总预算；ML独立概率重新归一且零和回退1/N；所有执行权重非负且逐月和为1。因子组合毛收益严格使用m1实际`signal_date/execution_date/return_date`和六因子收益，中证800严格按相同执行/退出日的000906收盘价计算；换手、买卖成本、主结果毛收益及累计净值公式均可独立复算。

但指数基准被错误纳入股票成本情景。代码把CSI800作为单一袖套送入统一换手成本函数，首期从现金建仓产生`buy_turnover=1`并收10bp买入成本，导致CSI800首期`net_return=gross_return-0.001`。本次审计要求指数基准不收股票交易成本；plan/AS26也把双边10bp和卖出5bp描述为股票成本补充。AS41末句虽然登记“中证800按单一基准袖套同口径处理”，但该简化与指数无股票成本要求冲突，并实际扭曲净口径基准。因此m4当前代码门禁不通过。

## 二、四类组合定义与权重

### 2.1 组合合同

- `PORTFOLIO_CSI800`：中证800指数基准，权重1，见`portfolio.py:19-22,393-404`。
- `PORTFOLIO_EQUAL`：六因子固定各1/6，见`portfolio.py:348-370`。
- `PORTFOLIO_CYCLE`：按时点商业周期标签应用R9方向和15%主动预算，见`portfolio.py:339-369`。
- `PORTFOLIO_ML`：直接消费m3六个raw probability或归一权重，并再次归一，见`portfolio.py:195-242,362-369`。
- `run_portfolio_construction`最终仅输出以上四类；3个月合成样本得到12条“组合-月”收益，2个月真实样本得到8条，组合名称完整无额外策略。

### 2.2 R9方向矩阵

审计者把`BUSINESS_CYCLE_DIRECTIONS`与spec R9逐格比对：

| 因子 | Expansion | Slowdown | Contraction | Recovery |
| --- | ---: | ---: | ---: | ---: |
| Value | 0 | -1 | 0 | +1 |
| Growth | 0 | -1 | +1 | -1 |
| Momentum | +1 | +1 | 0 | 0 |
| Low Volatility | 0 | +1 | -1 | -1 |
| Quality | 0 | +1 | -1 | 0 |
| Small-Cap | -1 | -1 | +1 | +1 |

`cycle_direction_matrix`输出4×6=24行，与R9全部正、负、空白方向一致。

### 2.3 15%总主动倾斜

`business_cycle_weights`先对六个方向分数去均值，再以`0.15 * centred / sum(abs(centred))`叠加到1/6，最后非负裁剪并归一，见`portfolio.py:111-135`。独立重算四周期结果：

| 周期 | 权重和 | 最小权重 | 相对1/N主动L1 | 正主动权重和 |
| --- | ---: | ---: | ---: | ---: |
| Expansion | 1.0 | 0.0916667 | 0.15 | 0.075 |
| Slowdown | 1.0 | 0.1416667 | 0.15 | 0.075 |
| Contraction | 1.0 | 0.1291667 | 0.15 | 0.075 |
| Recovery | 1.0 | 0.1291667 | 0.15 | 0.075 |

因此15%是多空主动偏离的L1总预算，不是六个因子逐个加减15个百分点；AS23口径通过。

### 2.4 ML概率、非负和1/N回退

- m3 predictor月与prediction月必须严格相差一个自然月，负数、缺失、无穷概率均被拒绝。
- 若同时有raw与weight列，固定使用raw probability并除以六因子概率和，符合AS24。
- 合成第二个月六个raw概率全0，真实触发`ml_equal_weight_fallback=True`，六权重全部1/6。
- 合成和真实样本所有四组合逐月权重和最小/最大均为1；合成最小权重0.047619，真实最小权重0，无负权。

结论：F17-F21、B12-B14及R9权重定义通过。

## 三、信号、执行及收益日期

- m1因子收益必须每月六因子齐全，且六因子的`signal_date`、`execution_date`、`return_date`各自唯一，见`portfolio.py:138-192`。
- 明确断言`execution_date > signal_date`及`return_date > execution_date`；m3概率只用于同一signal period，`prediction_date`必须为下一自然月，不替代真实交易日。
- 因子组合权重与收益按`signal_period + signal_date + execution_date + return_date + factor`五键精确合并，见`portfolio.py:418-438`，不会把邻月收益错接。
- 真实中国小窗两期日期为：

| signal | execution | return |
| --- | --- | --- |
| 2025-10-31 | 2025-11-03 | 2025-12-01 |
| 2025-11-28 | 2025-12-01 | 2026-01-05 |

两期均严格满足`signal < execution < return`；alignment audit也全部为true。

结论：信号与真实执行严格T+1，因子收益日期对齐通过。

## 四、中证800精确执行/退出收益

- `_load_benchmark_prices`固定筛选`benchmark_index_code=000906`，见`portfolio.py:245-272`。
- `_benchmark_returns`只接受m1 schedule的精确`execution_date`和`return_date`收盘价；任一日缺价立即报错，不用最近价、月末参考收益或前后填充替代，见`portfolio.py:275-296`。
- 指数毛收益公式为`exit_close / entry_close - 1`；`benchmark_return`仅进入alignment参考列，不参与正式收益。
- 合成数据故意把参考`benchmark_return`设为9.0，正式三期指数毛收益仍按价格得到10%、-10%、10%，证明参考列不污染收益。
- 真实小窗：第一期5103.675→4998.5884，第二期4998.5884→5214.2357；审计者用原始两端价格重算，和代码指数毛收益最大绝对误差为0。

结论：CSI800精确执行/退出毛收益通过；其净成本偏差见CA-A01。

## 五、因子毛收益、换手与成本

### 5.1 毛收益

- 三个因子组合的`gross_return = Σ execution_weight × factor_return`，见`portfolio.py:418-438`。
- 合成3个月、真实2个月逐组合独立点积重算，最大绝对误差分别为`6.94e-18`和`6.94e-18`。
- 成本计算后`main_result_return`逐行严格等于`gross_return`，`main_result_basis='gross'`；合成和真实最大差均为0。

### 5.2 AS41袖套换手

- 前期权重按“portfolio×factor”分组后shift，首期从0现金开始；正变化为buy turnover、负变化绝对值为sell turnover，二者和为总turnover，见`portfolio.py:441-460`。
- 六因子1/N合成三期独立结果：首期buy=1、sell=0、turnover=1；后两期权重不变，买卖和成本均为0；样本末未强制平仓。
- 该实现按AS41只衡量六因子袖套权重变化，不虚构因子内部逐股换手；这一数据限制已登记。

### 5.3 股票成本与净收益

- 买入成本=`buy_turnover×0.001`；卖出成本=`sell_turnover×(0.001+0.0005)`，即买卖各10bp、卖出另加5bp印花税，见`portfolio.py:461-465`。
- 合成全表独立重算交易成本最大误差为0；`net_return=gross_return-transaction_cost`最大误差为0。
- 成本没有反写权重、因子收益或gross主结果，只影响补充净列。
- 但统一函数也给指数基准收费，构成CA-A01。

## 六、累计收益数据

- `gross_nav`和`net_nav`分别按组合对`1+gross_return`、`1+net_return`连乘；累计收益为NAV减1，见`portfolio.py:480-494`。
- 合成逐月手工连乘与输出`gross_nav`最大绝对误差为0；真实小窗`gross_cumulative_return = gross_nav - 1`最大误差为0。
- 真实两期毛净值终点：商业周期1.0204986063、CSI800 1.0216629586、ML 1.0114559573、1/N 1.0208665833。
- chart数据同时保留gross与net，没有用净收益替换正式毛收益主序列。

结论：累计收益底表通过。

## 七、真实中国市场小窗

审计者在项目uv ML环境以真实m1→m2→m3→m4链路运行2025-11和2025-12两个目标月：

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| m1月度特征 | 132×39 | 通过 |
| m2/m3预测月 | 2 | 通过 |
| m4收益行 | 8=2月×4组合 | 通过 |
| m4权重明细 | 38=2×(3×6+1) | 通过 |
| 四组合权重和 | 全部1 | 通过 |
| 最小权重 | 0 | 非负 |
| 日期纪律 | 两期全部严格`signal<execution<return` | 通过 |
| 因子组合毛收益重算误差 | `6.94e-18` | 通过 |
| CSI800精确价格收益误差 | 0 | 通过 |
| gross主结果误差 | 0 | 通过 |
| net恒等式误差 | 0 | 通过 |
| CSI800交易成本 | 首期0.001、次期0 | fail，CA-A01 |
| R9方向矩阵 | 24行 | 通过 |
| 商业周期标签 | 两期均Recovery | 时点接口完整 |

真实运行确认指数成本问题不是合成测试特例。

## 八、coverage_matrix m4全部done行核对

| 要素 | 实现位置 | 审计结论 |
| --- | --- | --- |
| F17 | `business_cycle_weights` | 时点商业周期标签驱动六因子倾斜，pass |
| F18 | `BUSINESS_CYCLE_DIRECTIONS` | R9四周期×六因子逐格一致，pass |
| F19 | `_build_weight_detail` | 六因子固定1/6，pass |
| F20 | `business_cycle_weights` | 相对1/N主动L1总预算15%，pass |
| F21 | `_normalise_ml_probabilities` | raw概率归一、零和1/N回退，pass |
| B11 | `run_portfolio_construction` | 四组合完整；指数净成本错误，major issue CA-A01 |
| B12 | `_build_weight_detail` | m1时点商业周期标签，pass |
| B13 | `business_cycle_weights` | 15%参数冻结，pass |
| B14 | `_normalise_ml_probabilities` | ML权重满仓、非负、和1，pass |
| R9 | `cycle_direction_matrix` | 24行方向矩阵，pass |
| SA4 | `run_portfolio_construction` | 双基准及毛/净列存在；指数净基准受CA-A01影响 |

全部位置存在且非空壳，未发现`pass`/`TODO`虚报或未映射要素ID的公开策略私货函数。

## 九、issue清单

### CA-A01

- severity: major
- 证据定位: `workspace/r003_equity_factor_timing_cn/plan.md:128,135-136,178-182`；`workspace/r003_equity_factor_timing_cn/assumptions.md:330-338,526-534`；`src/r003_equity_factor_timing_cn/portfolio.py:393-410,441-474,535-546`
- 依据: 双边10bp及卖出5bp是股票成本补充，CSI800是指数基准且本次审计要求不收股票成本；当前代码却把CSI800权重明细与三个股票因子组合一起传入`_add_turnover_and_costs`，首期固定产生buy turnover 1和10bp成本。合成与真实小窗均得到CSI800首期`transaction_cost=0.001`、`net_return-gross_return=-0.001`。AS41末句虽登记同袖套处理，但该简化与指数无股票成本要求冲突并使净口径基准失真。
- 影响要素: B11、SA4、R10后续净收益比较；不影响CSI800 gross主结果。
- 通过条件: CSI800可保留精确执行/退出毛收益及诊断性权重，但股票交易成本必须固定为0，使其所有月份`transaction_cost=0`且`net_return=gross_return`；仅三个股票因子组合按AS41袖套变化应用买10bp、卖10bp+5bp。同步修正AS41末句或明确指数成本例外，并补首期与连续持有测试。

## 十、五维度审计结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | pass_with_issues | 四组合、R9、15%倾斜、ML、毛收益、换手、成本和NAV公式通过；指数成本范围错误 |
| 参数一致 | pass | 15%、买10bp、卖10bp+5bp及各权重参数冻结一致 |
| 实现位置真实 | pass | m4全部done位置存在、非空壳且进入结果合同 |
| 代码反查 | fail | 合成和真实小窗均复现CSI800首期被收10bp股票成本 |
| 简化声明 | pass_with_issues | AS41已声明袖套换手代理，但其指数同口径末句与本次指数零股票成本要求冲突 |

## 十一、已检查维度清单

- [x] m4全部done行F17-F21、B11-B14、R9、SA4逐条核对
- [x] 四组合定义与R9四周期×六因子方向矩阵
- [x] 15%总主动L1倾斜公式、权重非负及逐月和1
- [x] m3 raw概率归一、零和1/N回退及ML日期
- [x] m1信号、真实execution、return日期严格顺序及六因子日期精确合并
- [x] CSI800 000906精确执行/退出收盘价收益
- [x] 因子组合毛收益逐月独立点积复算
- [x] AS41首期、连续持有、买卖和总换手
- [x] 买10bp、卖10bp+5bp成本公式及net恒等式
- [x] 成本不改变gross与`main_result_return`
- [x] 指数基准股票成本范围，确认合成与真实均错误收费
- [x] gross/net NAV及累计收益逐月连乘
- [x] 真实中国m1→m2→m3→m4两月小窗
- [x] 五维度：公式一致、参数一致、实现位置真实、代码反查、简化声明

初审结论: fail

## 十二、第1轮修复后复审更新

- 复审范围：仅核验CA-A01修复及m4既有合同回归；未读取或采信coder完成汇报。
- 静态证据：`portfolio.py:472-479`在统一袖套换手诊断之后，明确把`CSI800`的`buy_cost`、`sell_cost`和`transaction_cost`固定为0，并用`cost_basis='index_benchmark_no_stock_cost'`声明中国指数基准不适用个股交易成本；三个股票因子组合仍为`factor_sleeve_stock_cost`。`net_return`继续由`gross_return-transaction_cost`统一生成，正式主结果仍为gross。
- 独立合成回归（三个月）：CSI800诊断性首期`buy_turnover=1`可保留，但三期买入、卖出和总成本均为0，`max(abs(net_return-gross_return))=0`，gross/net NAV最大差为0；三个股票组合成本公式`buy_turnover×0.001 + sell_turnover×0.0015`最大误差为0，首期成本均为0.001，六因子1/N三期成本为`[0.001, 0, 0]`。
- 独立真实中国市场两月链路（2025-11、2025-12目标月）：m1为132×39，m2/m3各2期，m4为8行、权重明细38行；CSI800两期总成本、买入成本、卖出成本均为`[0, 0]`，净毛收益最大差0、净毛NAV最大差0；三个股票组合首期成本均为0.001，股票成本公式最大误差0，共4条股票组合月度记录产生非零成本。
- 无回归：四组合名称和行数完整；R9方向矩阵24行；商业周期四状态主动权重相对1/N的L1均为15%；ML概率权重和零和1/N回退不变；全部权重非负且逐期和为1；真实两期均严格`signal_date < execution_date < return_date`；中证800继续使用000906精确执行/退出价；因子毛收益、换手、gross主结果、net恒等式及gross累计收益独立重算误差均为0。

### CA-A01复审状态

| issue | 初审 | 第1轮复审 | 证据 |
| --- | --- | --- | --- |
| CA-A01 CSI800误收股票交易成本 | major / open | resolved | 合成与真实两月均满足指数成本恒0、net=gross；三个中国股票因子组合成本仍按买10bp、卖15bp正确计算 |

### 五维度复审结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | pass | 指数零股票成本例外、股票袖套成本、毛净收益与NAV公式均通过 |
| 参数一致 | pass | 15%主动预算、买10bp、卖10bp+5bp及指数0成本口径一致 |
| 实现位置真实 | pass | 修复位于正式m4成本链路并进入结果合同，非测试旁路 |
| 代码反查 | pass | 合成三月及真实中国两月独立运行均通过 |
| 简化声明 | pass | `cost_basis`逐行明确区分指数基准与股票因子袖套 |

本轮未发现新增问题，CA-A01已关闭，m4代码门禁通过。完整复审证据见`impl_audit_m4_reaudit_round1.md`。

verdict: pass
