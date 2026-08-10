# r004_all_a_style_box iter_02 正式验证阻断记录

## 结论

iter_02正式入口由verifier亲自运行后以`exit=1`硬阻断。阻断是预期的证券生命周期真实性门禁：600466的最后本地点价超过20个交易日寿命，且当前本地数据和配置中没有可审计的转板行情或现金/换股结算路径。完整NAV、单点收益、R4、R7、R10和SA4均不得生成。

本轮不得读取05:21遗留的iter_01 `metrics.json`、`comparison.json`或Excel/PNG冒充新结果；hard扰动与工作簿finalizer亦未执行。

## 正式运行

```text
.venv/bin/python -m src.r004_all_a_style_box.main
```

- started_at：`2026-07-19T06:50:29.350784+08:00`
- ended_at：`2026-07-19T06:56:45.479745+08:00`
- exit：`1`
- fresh run log：`output/r004_all_a_style_box/results/run_log.md`，mtime `2026-07-19 06:56:45`
- 旧metrics/comparison mtime：`2026-07-19 05:21:16`，早于本轮运行，明确不计入iter_02证据。

完整异常：

```text
Traceback (most recent call last):
  File "/Users/hedi/report_reproduce/src/r004_all_a_style_box/main.py", line 995, in main
    artifacts = run_formal_pipeline(config=config, output_dir=output_dir)
  File "/Users/hedi/report_reproduce/src/r004_all_a_style_box/main.py", line 606, in run_formal_pipeline
    m3_full = build_m3_dataset(m1, m2, config)
  File "/Users/hedi/report_reproduce/src/r004_all_a_style_box/portfolio.py", line 2761, in build_m3_dataset
    return run_china_market_backtest(
  File "/Users/hedi/report_reproduce/src/r004_all_a_style_box/portfolio.py", line 2478, in run_china_market_backtest
    raise RuntimeError(
RuntimeError: 正式OOS存在超出历史点价寿命且无可审计估值路径的资产；资产数量继续保留，但完整NAV、单点收益及R4/R7/R10/SA4已硬阻断，不得以risk_exit永久豁免: ['600466']
```

## 异常现场只读重放

为取得异常未打印的首日和持仓细节，verifier再次只读调用相同m1→m2→m3路径，并从异常栈中读取`run_china_market_backtest`局部变量；该诊断不写output、不改变参数或代码。

全部受影响代码：`['600466']`。首个blocking键只有1个：

| 字段 | 值 |
| --- | --- |
| date / processing_date | 2023-07-06 |
| holding_month / phase | 2023-07 / formal_oos |
| portfolio | ALL_A |
| stock_code | 600466 |
| shares | 0.00004288027739673176 |
| current target weight | 0 |
| last price / source date | 0.40 / 2023-06-05 |
| price age | 21个交易日 |
| configured threshold | 20个交易日 |
| executed VWAP | 无 |
| active suspension flag at trigger | false（本地日状态在2023-06-05后无记录） |
| risk event | 2023-04-28公告，2023-05-04生效 |
| rule | `risk_exit_behavior_not_valuation_source` |
| stale / blocking | true / true |

状态对象在阻断时仍保留600466份额和最后价；没有虚构卖出、未来点价或零值核销。该旧mark一旦超过阈值就不能继续生成“完整可实现NAV”。

## 事件链

- 配置中600466只有`announced_security_lifecycle_risk_exit`：公告日2023-04-28、生效日2023-05-04、动作`risk_exit_on_next_trade`；没有现金结算、换股比例或后继代码参数。
- 现场累计68条600466行为/估值候选记录。ALL_A有44条`risk_exit_waiting_daily_can_sell`和21条`risk_exit_behavior_not_valuation_source`；从未出现有效执行VWAP。
- 2023-07-05价格年龄恰为20，仍在阈值内；2023-07-06变为21，首度满足`age > 20`并硬阻断。
- `risk_exit`只证明退出意图，不提供可交易价格或结算金额，因此不能永久豁免估值真实性门禁。

## 本地数据可用性检查

verifier只读检查`/Users/hedi/local_data`：

| 文件 | 600466 | 400165 |
| --- | --- | --- |
| `ashare_stock_price.parquet` | 5,417行，末日2023-06-05；末价0.40、VWAP 0 | 0行 |
| `ashare_stock_price_forward.parquet` | 5,417行，末日2023-06-05；末价0.40 | 0行 |
| `ashare_stock_trade.parquet` | 5,417行，末日2023-06-05；末期volume/turn_value均0 | 0行 |
| `ashare_stock_suspend.parquet` | 末日至2023-06-05且`if_suspend=1` | 0行 |
| `ashare_stock.parquet` | 当前主表无600466 | 当前主表无400165 |

主会话的额外只读外部核实表明：官方NEEQ将600466转板为400165（蓝光3），约2023-07-26挂牌；公开行情接口存在自2023-07-26起的400165行情。由此判断，**外部数据存在可补齐路径，但当前本地A股数据层和策略配置未纳入该代码映射/行情**。本verifier未下载数据、未补映射、未修改实现。

## 本轮未执行

- 六个长组合198实体月的四点桥接和3个合成因子99实体月复算；
- R4/R7/SA4及27项R10、48项SA4 comparison逐键核对；
- metrics/comparison/五工作簿边界一致性；
- `oos_end=2025-11-30` hard扰动；
- verified context、工作簿finalizer、Excel/PNG终验；
- iter_02 comparison复制。

这些项目均依赖完整可估值NAV；在生命周期门禁失败后继续会制造伪绿。

## 冻结代码SHA-256

- `config.py`：`b4e34d355f571ff0f9549cc032ca966d30180c0ef959fdd1e8134480612574b3`
- `main.py`：`01fb6b7bb0382f55e01579c805b04eefa8c2d07bb420b69eaa464ff8a18709bd`
- `portfolio.py`：`6f2e3285c682918d14dd66138dc0b055c6bb626909660073036374d59fea041f`
- `reporting.py`：`6638cf62ad778b604489a671fd2fec7f3ea5763dcd52f15a4db4b7f6596aafe3`
- `strategy.py`：`f484e7c1ab58f041183ac1570c1ec526d0872ad50ad8bd003c3b48a8b65bc8c2`
- `workbook_builder.mjs`：`6e1b6a987714cd231d7968148de5bf681a567ea320753a09351bf262e63a80d6`
- `iter_02/changes.md`：`12b1a620cbe4cd8619b1c5fb160a71a0f1db047ba194130e7b592c39a05936dd`

本verifier未修改`src/`、`tests/`或`state.json`，也未修复或撤销coder改动。

verdict: fail
