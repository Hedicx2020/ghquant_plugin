# m3 实现记录

## 范围

- milestone: `m3 组合、成本与中国交易约束回测`
- elements: `F19, B7, B11, SA3`
- 实现模块: `src/r004_all_a_style_box/portfolio.py`
- 未写入 `output/r004_all_a_style_box/results/`，未运行正式全区间，未作验证结论。

## 稳定入口与数据合同

- `build_portfolio_targets()`：四箱、同池全A、四箱1/N目标权重。
- `load_daily_mark_prices()`：只读前复权日收盘价和交易日历；仅在价格已观察后更新估值，不使用未来值回填。
- `run_china_market_backtest()`：T信号、T+1 VWAP有状态回测；输出日/月毛净收益和净值、目标/实际权重、交易流水、双边与单边换手、佣金/滑点/印花税拆分、未成交、覆盖率、因子收益和阶梯持仓。
- `build_m3_dataset()`：供后续 `main.py` 使用的统一稳定入口，参数与上述回测函数相同。
- `calculate_style_factor_returns()`：逐日/逐月从BV/BG/SV/SG重算SMB、HML、GML。
- `select_formal_oos()`：仅按m1冻结的`sample_phase=formal_oos`选择2023-04至2025-12持有月，不训练、不调参。
- `assert_m3_invariants()`：成交时点、VWAP、现金、成本、实际权重、HML/GML及OOS边界勾稽。

## 冒烟运行

命令前缀：

```bash
UV_CACHE_DIR=/tmp/r004_uv_cache uv run python -m compileall -q src/r004_all_a_style_box/portfolio.py
```

另以Python内联脚本运行：

```python
m1 = build_m1_dataset(smoke_months=2)
m2 = build_m2_dataset(m1.monthly_panel)
m3 = run_china_market_backtest(m1, m2)
```

真实数据只读冒烟统计：

| 项目 | 数值 |
| --- | ---: |
| 信号月 | 2 |
| 信号日 | 2025-10-31、2025-11-28 |
| m2四箱成员行 | 10,068 |
| 目标权重行 | 30,409 |
| 日组合行 | 264 |
| 月组合行 | 12 |
| 成交流水行 | 30,688 |
| 未成交行 | 6,537 |
| 日/月因子收益行 | 138 |
| 六个长组合合计成本（单位初始净值口径，不是单组合费率） | 0.005550833369181493 |
| HML+GML最大绝对误差 | 0 |
| 成本拆分最大绝对误差 | 0 |
| 实际权重+现金偏离1的最大绝对误差 | 1.1102230246251565e-16 |
| 最短信号至执行间隔 | 3日 |
| 最低日净值 | 0.9273619751961887 |

未成交原因计数：`execution_suspended=54`、`invalid_execution_vwap=6`、`limit_up_cannot_buy=171`、`insufficient_cash_after_costs=6306`。合成fixture另定向触发并检查了`limit_down_cannot_sell`：旧仓延续且未虚构卖出。

## 已知风险与 verifier 复核点

- 日频记账使用前复权收盘价；月度正式持有期收益使用相邻T+1 VWAP事件。执行日VWAP与收盘为两个时点，月度收益应以VWAP事件序列为准，不应由日收盘收益简单替代。
- `holdings`是每次执行后的阶梯持仓和现金快照；执行日之间份额不变，可与日频前复权收盘价逐日重算净值，避免生成超大逐股逐日持仓表。
- 成本引起的可买数量同比缩放会以`insufficient_cash_after_costs`进入未成交审计；市场不可成交原因与资金不足原因分开保留。
- 最终OOS持有月可能在下一自然月首个T+1 VWAP结算；正式区间按冻结的`holding_month`和`sample_phase`选择。
- 冒烟只确认可执行与内部勾稽，不代表正式OOS结果达标；完整运行、数值验证和门禁判定由verifier/check_gates执行。
