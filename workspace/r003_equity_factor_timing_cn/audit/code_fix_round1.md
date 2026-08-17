# m1 全局代码审计修复记录（round 1）

- 日期：2026-07-18
- 修复范围：仅 m1 的 `data_pipeline.py`、`strategy.py`、假设登记簿及 m1 coverage 行
- 审计输入：`audit/code_audit_codex.md`
- 对应问题：CDX-C-01、CDX-C-02
- 结论边界：本记录只陈述修复与自测证据，不代表 code audit 已通过；需由审计者独立复审。

## CDX-C-01：杠杆条件公式

`leverage_conditions` 已按 AS7 改为两个相对名义 GDP 缺口的等权平均：

```text
((m2_yoy - gdp_nominal_yoy) +
 (social_financing_yoy - gdp_nominal_yoy)) / 2
```

原字段名、宏观原始证据链及下游特征名不变。AS7 与 coverage D7 已同步回填。

## CDX-C-02：中国股票真实可交易状态

### 执行日

- 信号日 ST 过滤仍保留。
- T+1 执行日重新按 `[implement_date, remove_date)` 判断新增 ST，并统一检查成交量、停牌、涨停、跌停。
- 执行失败时保留原股票权重为现金零收益；不重选股票、不重归一。
- 逐股票保留 `execution_restriction_reason` 及各限制布尔证据。

### 退出日

- `return_date` 继续作为下游兼容的计划退出日，并新增同值的 `intended_return_date`。
- 计划退出日使用与执行日相同的 ST、成交量、停牌、涨跌停限制，并额外要求退出收盘价存在。
- 若计划日不可退出，按预先冻结的交易日顺序，在其后最多 20 个额外交易日内选择该股票首个可交易日；不根据后验可交易性重选或重配权重。
- 搜索窗耗尽时，`actual_return_date=NaT`、`exit_executed=false`，仓位继续持有。计划退出日有收盘价时只做 NAV 标记；计划日也无收盘价时按现金零收益留痕。两者均不虚构成交。
- 新增逐股票及聚合证据：`intended_return_date`、`actual_return_date`、`exit_delay_days`、`exit_delay_trading_days`、`exit_executed`、`restriction_reason`、`exit_search_horizon_date`、`nav_marked`。
- 原 `return_date`、`factor`、`factor_return` 等下游必需字段保持，组合 `weight_sum` 仍由原信号权重求和。

### 标签可得日

- 正常或延迟退出：`label_available_date=actual_return_date`。
- 未入场现金权重：保守记为计划退出日。
- 搜索超限：只有到固定搜索窗末才能确认超限，因此记为 `exit_search_horizon_date`。
- 因子聚合标签取逐股票可得日最大值，供 m3 在训练截止日前过滤已实现/已知标签；本轮未改动 m3。

AS33 已修订，固定搜索窗、超限持有和标签可得日规则登记为 AS42；coverage D14 已同步回填。

## 定向测试证据

同一信号、同一因子、四只股票各 25% 原始权重的合成测试通过：

| 场景 | 结果 |
| --- | --- |
| 执行日新增 ST | `can_trade=false`，`not_executed_cash`，`restriction_reason=st` |
| 计划退出日停牌且涨停 | 顺延至下一交易日，`exit_delay_trading_days=1`，限制原因同时记录 `suspended` 与 `limit_up` |
| 21 个候选交易日持续无量（计划日 + 20 个额外交易日） | `actual_return_date=NaT`、`exit_executed=false`、`exit_search_exhausted_nav_mark`，标签可得日为搜索窗末 |
| 正常交易 | 计划退出日成交，`exit_delay_days=0` |

合成组合 `weight_sum=1.0`，未重归一；手算与实现的因子收益均为 `0.09`，超限未退出权重为 `0.25`。

## 真实数据限时 smoke

使用 2025-09 单个信号月、全市场股票（`smoke_stock_limit=None`）运行 m1 数据构建，未写正式 results：

- 六因子 6 行，逐股票成分 4,726 行；
- 六个因子的 `weight_sum` 范围为 `[0.9999999999999999, 1.0]`；
- 执行受限 97 笔，延迟退出 61 笔，固定窗口超限 3 笔；
- 聚合 `label_available_date` 缺失 0 行；
- 管线内 PIT/T+1 断言通过，计划 `return_date` 与 `intended_return_date` 保持一致。

运行环境仅出现 PyArrow 无权读取 CPU cache `sysctlbyname` 的警告，不影响退出码或数据断言。

## 静态检查

- `python3 -m py_compile`：`strategy.py`、`data_pipeline.py` 通过；
- 目标文件行尾空白扫描：通过；
- 未改动 m2-m5、`main.py`、`reporting.py`、`common/`、`state.json` 或正式 `output/.../results/`。
