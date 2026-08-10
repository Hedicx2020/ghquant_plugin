# result_audit 定向修复记录（round 1）

- 日期：2026-07-18
- 修复身份：quant-coder
- 输入问题：RA-A01、RA-A02、外部审查 CDX-R-01
- 结论边界：本轮只修复结果生成链并执行定向测试；未覆盖正式 results，不代表 result audit 或外部审查已经通过。

## RA-A01：预测散点按月份键连接

问题根因是概率表的 `prediction_date` 使用当月最后交易日，而胜出标签使用自然月末。原实现按精确 `predictor_date + prediction_date + factor` 连接，使11个月、66个因子的实际收益和赢家标记为空。

修复内容：

- 新增 `_build_prediction_scatter_data`，将概率和标签两侧分别规范为 `predictor_period`、`prediction_period` 后，再按两个 Period 月份键及 `factor` 一对一连接；原始交易月末与标签自然月末日期分别保留。
- 断言六个唯一因子、连接后行数等于 `预测月份数 × 6`、`factor_return/is_winner` 全部非空、每个预测月恰有六因子和一个实际赢家。
- 绘图前再次断言有限值清洗不会丢失任何散点；否则中止结果包生成。

使用现有正式 `probability_details.xlsx` 的 `OOS概率`、`胜出标签` 做只读回归：

- 预测月份：33；
- 连接行数：198；
- 非空实际收益：198/198；
- 非空赢家标记：198/198；
- 每月唯一实际赢家：33/33。

另用交易月末 `2023-04-28` 对自然月末 `2023-04-30` 的合成数据验证按月连接得到6行；主动删除一条标签后，断言按预期报错：`预测散点实际收益/赢家缺失: rows=1, months=['2023-04']`。

## RA-A02：逐股票执行/退出证据进入既有结果包

对象链已显式改为：

```text
main.dataset.factor_constituents
  -> write_result_package(factor_constituents=...)
  -> _build_execution_exit_audit
  -> returns_detail.xlsx / execution_exit_audit
```

未新增独立 artifact，16项文件名合同不变。新增 sheet 至少包含：

- `signal_date`、`prediction_date`、`prediction_month`；
- `intended_execution_date`、`actual_execution_date`、`can_execute`、`executed`；
- 执行限制总原因及 ST、无量、停牌、涨停、跌停分项；
- `intended_return_date`、`actual_return_date`、`exit_delay_days`、`exit_delay_trading_days`、`exit_executed`、`restriction_reason`；
- `label_available_date`、`nav_marked`、`exit_search_horizon_date`；
- 因子、股票代码、原信号权重与收益状态。

结果层新增断言：OOS月份完整、信号月/因子/股票唯一、T+1执行、未入场不得有实际执行日、已退出必须有实际退出日、退出不得早于计划日、延迟不得超过20个额外交易日、超限仓位必须保留20日窗证据、标签可得日不得早于计划退出日、数据行不得超过Excel的1,048,575行上限。

`metrics.json.execution_exit_audit` 与 `run_log.md` 写入行数、表内容 SHA-256、月份范围、执行受限/正常退出/延迟退出/超限/NAV标记计数和限制状态分布。

单信号月、全市场 m1 限时 smoke 在临时目录写入工作簿，结果如下：

- `execution_exit_audit` 数据行4,726，含表头工作表行数4,727；
- 内容哈希重复构造一致：`a5767ff24ff0a39fd48f3c88a036bb102b1975e26453f7a69e60f81b273d1b48`；
- 实际入场4,629，执行受限97；
- 正常退出4,568，延迟退出58，20日窗超限3，NAV标记3；
- 限制计数：`limit_up=74`、`limit_down=12`、`no_volume|suspended=11`；
- 工作簿确有 `execution_exit_audit` sheet，行数及必需字段断言通过。

## CDX-R-01：中证800成本口径文字修订

AS41 及结果层口径文字已修订为：首期建仓和后续袖套成本只适用于六因子1/N、商业周期倾斜、ML胜出概率三个可投资因子组合；中证800保持无成本理论指数基准，净主动收益以有成本策略对无成本基准比较。

未修改 `portfolio.py`、交易成本参数、组合收益或任何既有数值，也未给指数基准补构股票袖套成本。

## 执行命令与结果

```bash
MPLCONFIGDIR=/private/tmp/r003-mpl-cache .venv/bin/python - <<'PY'
# 读取现有 OOS概率/胜出标签，调用 _build_prediction_scatter_data
# 断言33月、198行、实际收益及赢家标记全非空、每月唯一赢家
PY
```

结果：通过，输出 `rows=198`、`prediction_months=33`、两个非空计数均为198。

```bash
MPLCONFIGDIR=/private/tmp/r003-mpl-cache .venv/bin/python - <<'PY'
# 构造2025-09单信号月全市场m1；调用 _build_execution_exit_audit
# 在 TemporaryDirectory 调用 _write_detail_workbooks 并回读sheet
PY
```

结果：通过，输出上述4,726行、限制/退出计数及稳定哈希；临时目录自动清理，正式 results 未写入。

```bash
python3 -m py_compile src/r003_equity_factor_timing_cn/*.py
```

结果：通过。PyArrow 仅报告受限环境无法读取 CPU cache 的 `sysctlbyname` 警告，不影响退出码或断言。

## 影响文件

- `src/r003_equity_factor_timing_cn/reporting.py`
- `src/r003_equity_factor_timing_cn/main.py`
- `workspace/r003_equity_factor_timing_cn/assumptions.md`（仅 AS41）
- `workspace/r003_equity_factor_timing_cn/audit/result_fix_round1.md`

未改动 `state.json`、策略参数、`portfolio.py`、`common/` 或正式 `output/r003_equity_factor_timing_cn/results/`。正式33个月结果包需由后续运行重新生成并由 quant-verifier / result_audit 独立核验。
