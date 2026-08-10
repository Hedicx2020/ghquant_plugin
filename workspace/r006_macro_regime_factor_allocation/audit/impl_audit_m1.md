# r006_macro_regime_factor_allocation m1 第四轮定向实现审计

## 审计范围与口径

- mode：code
- milestone：m1
- 本轮定向对象：D6、R14；复核 M1-E6 的日期精度修复及新增测试。
- 只读基准：`spec/spec.md`、`plan.md`、`assumptions.md`、`spec/coverage_matrix.md`、`output/r006_macro_regime_factor_allocation/verify_report.md` 的 M1-E6。
- 被审实现：`src/r006_macro_regime_factor_allocation/data_pipeline.py`、`tests/test_r006_m1.py`。
- 未读取或采信 coder 完成汇报；下列运行结果与反例均由本次审计独立执行。

## 独立运行记录

| 检查 | 独立结果 | 结论 |
| --- | --- | --- |
| `uv run python -m compileall -q src/r006_macro_regime_factor_allocation/data_pipeline.py tests/test_r006_m1.py`（pycache 写入临时目录） | exit 0 | 通过 |
| `uv run pytest -q -p no:cacheprovider tests/test_r006_m1.py` | `18 passed in 0.58s`，exit 0 | 通过 |
| 真实 M1-E6 路径：2005-01-01 至 2025-12-31 交易日历、显式 `000300`、真实外部宏观与 Trend | 输入 `signal_date=datetime64[us]`、`available_date=datetime64[ns]`；251 个信号日、4,466 行宏观输入、16 个序列，成功生成 4,016 行；`available_date > signal_date` 为 0，`observation_date > signal_date` 为 0，信号日×序列重复为 0 | 原 M1-E6 精度异常已修复 |
| 月末边界 | 2024-03-29 信号不会取得 2024-03-31 才可用的值；2024-04-30 可精确匹配当日值 | backward as-of 与 exact-match 语义正确 |
| 时区键反例 | UTC-aware `signal_date` 明确抛出 `DataContractError: signal_date 必须是无时区日期` | 安全拒绝，未静默移除时区或改变自然日 |
| 重复可用日反例 | 同一序列、同一 `available_date` 的两行，输入顺序翻转后命中值由 2.0 变为 1.0 | 未满足确定性去重合同 |
| 未来源日反例 | `observation_date=2024-12-31`、`available_date=2024-01-31`、`signal_date=2024-02-29` 被接受并返回值 999.0 | 函数自身未阻断未来源数据 |

## m1 全部 done 行逐条核对

| 要素 | 矩阵实现位置反查 | 公式/参数/时点核对 | 判定 |
| --- | --- | --- | --- |
| D1 | `align_factor_panel_to_schedule()` 存在，非空壳 | 普通观测映射同月正式交易月末；显式信号日要求精确相等；按股票、信号月、因子唯一化 | 通过 |
| D2 | `build_monthly_stock_panel()` 存在，非空壳 | 日行情形成月观察，T 日信号资格与 T+1 执行可买卖状态分离，前向收益不反向改变信号池 | 通过 |
| D3 | `fit_annual_frozen_factor_directions()` 存在，非空壳 | 方向仅用 expanding 训练窗、标签实现日不穿越训练截止，并按预测窗口冻结 | 通过 |
| D4 | `build_factor_crosswalk()` 存在，非空壳 | AS26 字段优先级、最长关键词、固定家族顺序、一对一及 SHA-256 均有实现 | 通过 |
| D5 | `ensure_macro_block_coverage()` 存在，非空壳 | 正式入口要求八个配置宏观块均有实际非缺失值 | 通过 |
| D6 | `apply_conservative_publication_lag()`、`align_macro_asof()` 均存在，非空壳 | 滞后与真实 M1-E6 精度路径通过；但来源日保护和重复可用日去重不完整 | 失败，见 CA-A01、CA-A02 |
| D7 | `load_index_state_inputs()` 存在，非空壳 | 要求调用方显式指定指数，不静默猜测；市场状态源日不得晚于信号日 | 通过 |
| D8 | `load_financial_pit_panel()` 存在，非空壳 | 财报以披露日 as-of 连接，`end_date` 仅作报告期标签 | 通过 |
| D9 | `build_capacity_control_panel()` 存在，非空壳 | 市值、行业 PIT、历史 beta、成交和换手进入容量控制；测试覆盖历史 beta 与行业 PIT | 通过 |
| D10 | `compute_factor_availability()` 存在，非空壳 | 只统计本地首次/末次非缺失月，不冒充学术发表年 | 通过 |
| F16 | `build_publication_year_coverage()` 存在，非空壳 | 使用“首次本地可用年不晚于预测年前一年”的透明替代口径 | 通过 |
| B1 | `build_common_month_index()` 存在，非空壳 | 因子、股票、指数实际非缺失月份取交集，并逐月要求八宏观块完整 | 通过 |
| B2 | `build_walk_forward_windows()` 存在，非空壳 | 首个预测块从 120 月训练与 144 月验证之后开始 | 通过 |
| B3 | `build_walk_forward_windows()` 存在，非空壳 | 初始训练窗口固定 120 月 | 通过 |
| B4 | `build_walk_forward_windows()` 存在，非空壳 | 验证窗口固定 144 月 | 通过 |
| B5 | `build_walk_forward_windows()` 存在，非空壳 | 每 12 月向前推进，训练历史扩展 | 通过 |
| B6 | `build_walk_forward_windows()` 存在，非空壳 | 本地共同样本按完整 12 月预测块生成，不伪造原文 479 个月；真实缺月或尾部不足会失败 | 通过 |
| B7 | `build_execution_schedule()` 存在，非空壳 | T 月末信号，`searchsorted(..., side="right")` 取得严格晚于 T 的首个交易日 | 通过 |
| R14 | `align_macro_asof()` 存在，非空壳 | 真实路径零时点违规；函数级来源日与重复键合同仍失败 | 失败，见 CA-A01、CA-A02 |
| R23 | `build_publication_year_coverage()` 存在，非空壳 | 输出本地信号可用性覆盖，不声称复现原发表年份 | 通过 |
| SA11 | `run_sa11_sensitivity()` 存在，非空壳 | 同一有效月份生成基准、额外滞后、市场残差、正交化、等权五条路径；beta 严格滞后一期 | 通过 |
| SA13 | `build_publication_year_coverage()` 存在，非空壳 | 与 D10/F16 共用已声明的本地可用性替代 | 通过 |

## 五维度逐项核对

### 1. 公式一致

- `pd.merge_asof(..., direction="backward", allow_exact_matches=True)` 与 AS16 的“只向后沿用最近已发布值”一致。
- merge 后检查 `available_date <= signal_date`，真实路径独立复算为零违规。
- 不一致：函数没有同时约束 `observation_date <= available_date` 与 `observation_date <= signal_date`；构造反例可把未来观测值伪装成较早可用值后进入信号。

### 2. 参数一致

- 月度至少滞后一月、季度滞后四月由 `apply_conservative_publication_lag()` 承担；`align_macro_asof()` 保持 backward 连接，没有改为同月前向取值。
- `allow_exact_matches=True` 符合“当日已经可用即可使用”的时点语义。
- `datetime64[us]`、`datetime64[ns]` 均在 merge 前显式转成 `datetime64[ns]`；timezone-aware 键被明确拒绝，避免无规则时区剥离。

### 3. 实现位置真实

- coverage matrix 的 D6、R14 均指向实际存在且有实现体的 `align_macro_asof()`；函数不是 `pass`、TODO 或空壳。
- D6 同时映射到实际存在的 `apply_conservative_publication_lag()`。
- 未发现实现位置虚报；无需写 `判定: not_found`。

### 4. 代码反查

- 本轮反查 `align_macro_asof()` 的公开行为均可回映 D6/R14、B7、AS6、AS16。
- 未发现 `strategy.py` 新增公开函数私货。
- 新增测试确实构造了原失败组合：`signal_date=datetime64[us]`、`available_date=datetime64[ns]`，并断言输出统一为 ns。
- 新增测试真实覆盖月末边界：2024-03-29 不取得 2024-03-31 值，2024-04-30 允许精确命中。
- 测试未覆盖同序列重复 `available_date` 和伪造未来 `observation_date` 两个失败合同。

### 5. 简化声明

- 以固定保守滞后替代 ALFRED vintage 已在 AS6、AS16 登记；本轮未发现新的未登记方法简化。
- timezone-aware 日期采用显式拒绝而非隐式换算，属于输入合同保护，不构成未登记策略简化。

## Issues

### CA-A01

- severity: critical
- 定位：`src/r006_macro_regime_factor_allocation/data_pipeline.py:1975-1996`；基准 `workspace/r006_macro_regime_factor_allocation/plan.md:296-299`
- 依据：D6 是 m1 core 要素，计划要求任意预测行最大源日期不晚于信号时点；但函数只检查 `available_date > signal_date`。独立反例中 `observation_date=2024-12-31`、`available_date=2024-01-31` 被 2024-02-29 信号成功取得，说明调用方只要传入不一致日期即可产生未来数据，且当前 point-in-time 审计也只复核 `available_date`。
- 建议：在逐序列 merge 前强制验证 `observation_date <= available_date`，在 merge 后同时验证 `observation_date <= signal_date`；异常应抛 `DataContractError`，并增加对应负向测试。

### CA-A02

- severity: major
- 定位：`src/r006_macro_regime_factor_allocation/data_pipeline.py:1973-1988`；`tests/test_r006_m1.py:139-178`
- 依据：实现仅按 `available_date` 稳定排序，没有在 `align_macro_asof()` 内按 `series_id, available_date` 明确去重或拒绝冲突。独立反例中同一序列同一可用日的两条记录仅翻转输入顺序，命中值即由 2.0 变为 1.0；结果依赖上游行序，无法形成确定性 R14 时点证据。新增测试只覆盖 dtype 与月末边界，未覆盖该冲突。
- 建议：在每个序列内按明确的二级排序键（至少 `available_date, observation_date`）排序，再按固定规则去重；若同键存在不同值或来源，优先抛出 `DataContractError`，并增加输入顺序翻转后结果不变的测试。

## 已检查维度清单

- [x] 公式一致
- [x] 参数一致
- [x] 实现位置真实
- [x] 代码反查
- [x] 简化声明
- [x] D6/R14 的 `datetime64[us]`/`datetime64[ns]` 真实集成路径
- [x] timezone-aware 日期键处理
- [x] backward as-of、`available_date <= signal_date` 与月末边界
- [x] 逐序列排序/去重
- [x] 无未来数据反例
- [x] 新增测试对原失败与月末边界的真实覆盖

verdict: fail
