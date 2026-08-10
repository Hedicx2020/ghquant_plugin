# m4 第1轮定向修复记录

- 修复对象: CA-A01（CSI800指数基准被错误收取股票袖套成本）
- 修复边界: 仅修改 `src/r003_equity_factor_timing_cn/portfolio.py`；未修改m1-m3、m5、`main.py`、`state.json`、`results/`或`common/`
- 依据: `audit/impl_audit_m4.md`及当前`verify_report.md`

## 代码修复

在 `_add_turnover_and_costs` 完成换手汇总后，按 `portfolio == CSI800` 明确区分成本范围：

- CSI800保留 `buy_turnover`、`sell_turnover` 和 `turnover`，仅作组合换手展示；
- CSI800的 `buy_cost`、`sell_cost`、`transaction_cost` 固定为0；
- 因此CSI800逐月 `net_return == gross_return`；
- 六因子1/N、商业周期15%倾斜和ML概率组合继续使用因子袖套权重变化，并按买入10bp、卖出10bp加5bp印花税计费；
- 新增 `cost_basis` 字段，指数标记为 `index_benchmark_no_stock_cost`，三类因子组合标记为 `factor_sleeve_stock_cost`；
- `gross_return`、`main_result_return`、权重、收益日期及累计收益公式未改动。

## coder回归检查

### 内存编译

使用项目uv环境对当前 `portfolio.py` 做内存编译，输出 `COMPILE_OK`。

### 两月合成回归

合成两个月、六因子及三端中证800收盘价，覆盖四类组合首期建仓和次期连续持有：

| 检查项 | 结果 |
| --- | ---: |
| 四组合收益行 | 8 |
| CSI800首期展示turnover | 1.0 |
| CSI800两期transaction_cost | 0, 0 |
| CSI800两期net-gross | 0, 0 |
| 三类股票因子组合首期transaction_cost | 均为0.001 |
| 六因子1/N次期transaction_cost | 0 |
| 周期及ML次期成本 | 继续按实际权重变化计费 |

### 两月真实中国小窗回归

使用真实m1月度特征、真实m1交易日程和真实000906执行/退出日收盘价，取最后两个可实现信号月；六因子概率仅作小窗接口烟测，不生成正式结果：

| 检查项 | 结果 |
| --- | ---: |
| m1月度特征行 | 132 |
| 四组合收益行 | 8 |
| CSI800成本合计 | 0.0 |
| CSI800 `abs(net-gross)` 最大值 | 0.0 |
| 三类股票组合正成本行 | 4 |
| 日期纪律 | 两期均 `signal < execution < return` |

运行期间PyArrow仅打印受限环境下CPU cache `sysctlbyname`探测告警，不影响数据读取、断言或退出码；两次回归退出码均为0。

## 边界说明

本文件只记录quant-coder的定向修复及有限回归，不替代quant-auditor或quant-verifier的独立复审，不宣布m4验证通过。
