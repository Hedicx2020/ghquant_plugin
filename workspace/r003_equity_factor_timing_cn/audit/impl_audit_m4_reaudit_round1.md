# m4 第1轮修复后独立代码复审

- 审计模式: code
- 案例: `r003_equity_factor_timing_cn`
- milestone: `m4`
- 复审轮次: round 1
- 复审目标: CA-A01（CSI800误收中国股票交易成本）及m4全项回归
- 独立性: 未读取或采信coder完成汇报；静态反查正式代码，并以独立合成三月和真实中国市场两月链路重算
- 写入边界: 仅新增本复审文件并更新原m4审计文件；未改代码、`state.json`或`results/`

## 一、复审结论

CA-A01已修复。正式成本链路仍计算各袖套的诊断性换手，但对中证800指数基准明确将买入、卖出和总交易成本归零；指数所有月份均满足`net_return=gross_return`，gross/net NAV也完全相同。三个中国股票因子组合没有被连带免除成本，仍按买入10bp、卖出10bp另加5bp印花税计费。

合成三月和真实中国市场两月独立运行均通过。原审计已经通过的四组合定义、R9方向、商业周期15%倾斜、ML概率权重、非负满仓、日期纪律、000906精确价格收益、因子毛收益、AS41袖套换手、gross主结果及累计收益均无回归。本轮未发现新增issue，m4代码门禁通过。

## 二、CA-A01静态代码反查

正式实现位于`src/r003_equity_factor_timing_cn/portfolio.py:441-484`：

1. `portfolio×factor`权重变化仍在正式链路计算买卖换手；首期从现金到目标权重，因此诊断性`buy_turnover=1`仍被保留。
2. `portfolio.py:461-465`仍以`buy_turnover×buy_cost_rate`和`sell_turnover×(sell_cost_rate+sell_stamp_tax_rate)`计算股票袖套成本。
3. `portfolio.py:472-473`只识别`PORTFOLIO_CSI800`，将该指数基准的`buy_cost`、`sell_cost`、`transaction_cost`固定为0。
4. `portfolio.py:474`统一计算`net_return=gross_return-transaction_cost`，故CSI800自然满足净毛收益相等。
5. `portfolio.py:475-479`逐行写明指数为`index_benchmark_no_stock_cost`，股票因子组合为`factor_sleeve_stock_cost`，明确了中国指数基准的成本例外。
6. `portfolio.py:480-481`继续以gross作为`main_result_return`，修复没有改变正式主结果口径。

修复位于正式m4输出链路，不是测试专用旁路；筛选条件仅命中CSI800，不会把股票组合成本一并归零。

## 三、独立合成三月回归

审计者构造三个月、六因子、四商业周期状态及三类股票权重场景，独立调用正式m4接口并逐行复算。

### 3.1 CSI800零成本

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| 诊断性buy turnover | `[1, 0, 0]` | 可保留，不构成指数实际股票成本 |
| buy cost | `[0, 0, 0]` | pass |
| sell cost | `[0, 0, 0]` | pass |
| transaction cost | `[0, 0, 0]` | pass |
| `max(abs(net_return-gross_return))` | 0 | pass |
| gross/net NAV最大差 | 0 | pass |
| cost basis | `index_benchmark_no_stock_cost` | pass |

### 3.2 三个股票组合成本未回归

- 股票成本逐行独立复算式为`buy_turnover×0.001 + sell_turnover×0.0015`，与代码结果最大绝对误差为0。
- 商业周期15%倾斜、ML概率和六因子1/N三个组合首期成本均为0.001。
- 六因子1/N连续三期权重不变，成本为`[0.001, 0, 0]`，符合“首期从现金建仓、连续持有不重复收费、样本末不强制平仓”。
- 所有股票组合的`cost_basis`均为`factor_sleeve_stock_cost`。

### 3.3 其他m4合同

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| 四组合 | CSI800、1/N、商业周期、ML齐全 | pass |
| R9方向数据 | 24行 | pass |
| 四周期主动权重L1 | 均为0.15 | pass |
| 权重和 | 全部1 | pass |
| 最小权重 | 0.047619… | 非负 |
| 日期顺序 | 全部严格`signal<execution<return` | pass |
| 股票成本公式最大误差 | 0 | pass |
| net恒等式最大误差 | 0 | pass |
| `main_result_return-gross_return`最大误差 | 0 | pass |

## 四、真实中国市场两月复审

审计者在项目uv ML环境独立运行2025-11、2025-12两个目标月的真实m1→m2→m3→m4链路；Arrow对受限环境的CPU cache探测警告不影响运行，进程退出码为0。

### 4.1 链路规模与日期

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| m1月度特征 | 132×39 | pass |
| m2预测期 | 2 | pass |
| m3预测期 | 2 | pass |
| m4组合收益 | 8=2月×4组合 | pass |
| m4权重明细 | 38 | pass |
| signal periods | 2025-10-31、2025-11-28 | pass |
| 日期纪律 | 两期均严格`signal<execution<return` | pass |
| 组合权重和范围 | `[1.0, 1.0]` | pass |
| 最小权重 | 0 | 非负 |

### 4.2 CSI800成本与净毛收益

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| transaction cost | `[0, 0]` | pass |
| buy cost | `[0, 0]` | pass |
| sell cost | `[0, 0]` | pass |
| `max(abs(net_return-gross_return))` | 0 | pass |
| gross/net NAV最大差 | 0 | pass |
| cost basis | `index_benchmark_no_stock_cost` | pass |

CSI800仍从000906取相同真实`execution_date/return_date`的精确收盘价；本轮仅改变指数股票成本适用范围，没有改变指数毛收益来源和日期纪律。

### 4.3 中国股票组合成本

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| 商业周期15%倾斜首期成本 | 0.001 | pass |
| ML概率组合首期成本 | 0.001 | pass |
| 六因子1/N首期成本 | 0.001 | pass |
| 股票成本公式最大误差 | 0 | pass |
| 股票非零成本记录 | 4 | 与两期真实权重变化一致 |
| cost basis | `factor_sleeve_stock_cost` | pass |

股票组合没有因CSI800例外而被免除成本；买入10bp、卖出15bp的中国市场口径保持正确。

### 4.4 其余m4无回归

- `main_result_return=gross_return`最大误差0。
- `net_return=gross_return-transaction_cost`最大误差0。
- R9方向矩阵仍为24行。
- `gross_cumulative_return=gross_nav-1`最大误差0。
- 四组合、15%主动预算、ML概率/1N回退、权重非负满仓、六因子收益精确合并和000906精确执行/退出合同均保持初审已验证状态。

## 五、issue闭环

### CA-A01

- 初审严重度: major
- 本轮状态: resolved
- 通过条件1“CSI800所有月份transaction_cost=0”: 合成三月与真实两月均通过。
- 通过条件2“CSI800 net_return=gross_return”: 最大差均为0。
- 通过条件3“仅三个股票因子组合继续计费”: 三组合首期成本均0.001，买卖成本公式误差0。
- 通过条件4“明确指数成本例外”: `cost_basis`已区分指数无股票成本与因子袖套股票成本。

本轮没有发现新增issue。

## 六、五维度复审结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | pass | CSI800零成本及净毛相等；股票成本、净收益和NAV公式正确 |
| 参数一致 | pass | 中国股票买10bp、卖10bp+5bp，商业周期15%预算不变 |
| 实现位置真实 | pass | 修复进入正式m4成本及结果合同 |
| 代码反查 | pass | 合成三月与真实中国两月均独立验证通过 |
| 简化声明 | pass | `cost_basis`明确指数基准不适用股票成本 |

## 七、复审检查清单

- [x] CA-A01正式代码静态反查
- [x] 合成CSI800成本恒0、net=gross及gross/net NAV相同
- [x] 真实中国市场两月CSI800成本恒0、net=gross
- [x] 三个股票组合买10bp、卖10bp+5bp成本公式
- [x] 首期建仓、连续持有及样本末不平仓口径
- [x] 四组合、R9、15%主动L1、ML概率及1/N回退
- [x] 权重非负、逐期和1
- [x] `signal_date < execution_date < return_date`
- [x] CSI800 000906精确执行/退出收益
- [x] 因子gross、AS41换手、gross主结果、net恒等式及累计收益
- [x] 五维度：公式一致、参数一致、实现位置真实、代码反查、简化声明

verdict: pass
