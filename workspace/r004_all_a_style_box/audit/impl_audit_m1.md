# r004_all_a_style_box 实现复审（m1，shared common 定向复核）

## 范围与冻结点

- mode：`code`；milestone：`m1`；逐条覆盖 `D14 / B1 / B10`。
- 审读分离：未读取 coder 完成汇报；仅独立读取当前源码、配置回归测试、spec/plan/assumptions/coverage 与既有审计证据。
- 有界执行：只运行 `tests/test_data_loader_config.py` 和 `run_m1_synthetic_regression_checks()`；未运行正式全区间、未写正式 results、未触碰 state。
- 当前冻结 SHA-256：
  - `common/data_loader.py=d18d46173ebea55615615f45114de6c9c9a4b697fff0637740b03005ffb31ed2`
  - `src/r004_all_a_style_box/config.py=42ec417efdf811752a20e28ac9dd6ac44d2276044cdfdc7113808e634dcfc235`
  - `src/r004_all_a_style_box/data_pipeline.py=e6f19a02693448c4ac57c84bd45fb482c2bbdd7f89837fd9250b8307f50df0ba`
  - `src/r004_all_a_style_box/__init__.py=8ecc995d653490f84af5c33918b20af8c33744401830f61db78bab3af924f455`

## shared common 配置解析回归

- `get_data_root()` 从 cwd 向上取最近 `.reproduce.json`；有效 `data_root` 展开 `~`，不存在配置或最近合法配置缺字段时回退 `~/local_data`，见 `common/data_loader.py:18-49`。
- 损坏 JSON 不再静默回退：显式抛出带解析路径的 `ValueError`，保留 `JSONDecodeError` cause，见 `common/data_loader.py:28-35`。
- 不可读配置不再静默回退：显式抛出带解析路径的 `RuntimeError`，保留 `OSError` cause，见 `common/data_loader.py:28-31`。
- `uv run pytest tests/test_data_loader_config.py -q`：4 passed；覆盖无配置、最近合法配置、损坏 JSON、不可读配置，见 `tests/test_data_loader_config.py:17-71`。
- r004 的 `data_root` 通过 `default_factory=get_data_root` 复用 shared common；策略日期、交易成本、120 交易日上市龄和十个本地文件映射未被配置解析修复改变，见 `config.py:23-76`。

## D14 / B1 / B10 逐项复核

| 要素 | 状态 | 独立核对 | 真实实现位置 | 结论 |
| --- | --- | --- | --- | --- |
| D14 | found | T 日信号、T+1 前复权 VWAP 执行、下一执行端点收益；`gross_holding_return=return_vwap/execution_vwap-1`，无效双端点不产生收益 | `data_pipeline.py:74-128,866-984`；coverage `:22` | shared common 变更未触及收益端点、复权或可执行性口径 |
| B1 | found | 2015-01至2025-12；冻结截止2023-03-31；正式 OOS 2023-04至2025-12；月末 T、下一交易日执行 | `config.py:25-30`、`data_pipeline.py:74-128`；coverage `:59` | 日期、频率、T/T+1 合同无回归 |
| B10 | found | 沪深北动态全A；120交易日上市龄；北交所2021-11-15生效；T日ST/停牌/涨跌停/无成交过滤；当前 `list_state` 仅审计；T+1涨停禁买、跌停禁卖 | `config.py:45-75`、`data_pipeline.py:742-860,866-920,1005-1060`；coverage `:68` | 股票池与时点过滤无回归 |

## 有界动态证据

- `run_m1_synthetic_regression_checks()` 返回：PIT 3 行、未来披露 0、开市前北交所号段=`PRE_BSE_NEEQ`、有效前复权 VWAP=4.9、上市龄边界=`[119,120]`。
- 合成回归同时核对乱序多版本财务披露、同财政期 T 日前最新版本、北交所开市边界、非正 VWAP 拒绝和第119/120交易日边界，见 `data_pipeline.py:1125-1171`。
- `assert_m1_invariants()` 继续硬校验 T+1、收益端点、PIT 披露日、精确 T 日估值、十个数据源位于 data_root 且存在、动态池不使用指数成分、资格只由 T 日字段形成，见 `data_pipeline.py:1005-1060`。
- `build_m1_dataset()` 仍在组装后立即执行不变量检查，见 `data_pipeline.py:1175-1197`。

## Issues

本轮未发现当前 issue。shared common 的配置发现修复满足“损坏/不可读必须显式报错”，且未改变 D14、B1、B10 的策略参数、时点或数据链。

verdict: pass
