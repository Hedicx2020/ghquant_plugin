# r006 m2 实现忠实性审计

- mode: `code`
- milestone: `m2`
- 审计对象: `F1, F2, F12, F13, F14, B9, B10, B11, B12, B13, R16, R25`
- 审读分离: 未读取 coder 完成汇报；未采信既有审计结论；未读取或修改 `state.json`
- 审计基准: `spec.md`、`plan.md`、`assumptions.md`、`coverage_matrix.md` 与指定源码/测试

## 审计结论

本轮发现 9 项问题：critical 5 项、major 2 项、minor 2 项。m1 的 `window_id` 选择、方向训练标签截止、跨年 12 月冻结及月度 Period 边界委托真实有效；EW/VW 腿权重、Pearson/Rank IC、八容量区、单边换手与 10/30 bps 成本公式也可独立复算。失败主要来自 T+1 可交易收益口径、FMB/六因子/NW/R16 的正式调用链不完整，以及 R25 信号计数母集不一致。

## issues

### CA-A01

- severity: critical
- 要素: F14, B10
- 证据定位: `workspace/r006_macro_regime_factor_allocation/assumptions.md:133`、`workspace/r006_macro_regime_factor_allocation/assumptions.md:136`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:1072`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:1180`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1152`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1235`
- 一句依据: AS11 要求 T 月末算信号、T+1 首个可交易日建仓，但 m1 标签是 T 月收盘到下一月收盘的 close-to-close 收益，m2 只检查 `forward_return_date > signal_date` 后直接乘权重，既包含执行前不可交易区间，也会接受 T+2 标签；独立反例中 2024-01/02 信号的 2024-03/04 收益标签均被正常计算。
- 建议: 从实际 `execution_date` 的可成交价格起算至下一次调仓成交价格，并按月 Period 断言收益标签恰为下一持有期；禁止仅以“日期更晚”替代 T+1 合同。

### CA-A02

- severity: major
- 要素: F13
- 证据定位: `workspace/r006_macro_regime_factor_allocation/assumptions.md:159`、`workspace/r006_macro_regime_factor_allocation/assumptions.md:162`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:1456`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:721`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:760`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1605`
- 一句依据: FMB 函数本身实现了逐月 OLS 和 lag=3/6/12 汇总，但正式 m1 数据给出的是 `historical_market_beta`，接口默认要求 `historical_beta`，且没有从 m1 财务/容量面板构造 `book_to_market`、`momentum_12_1` 并调用 `prepare_fama_macbeth_controls`/`fama_macbeth_regression` 的路径，测试仅手工注入了成品控制列。
- 建议: 增加从 m1 PIT 财务面板与容量控制面板到四个 FMB 控制列的唯一构造器，统一 beta 字段名，并把 FMB 结果纳入正式窗口分析返回值。

### CA-A03

- severity: critical
- 要素: B9, R16
- 证据定位: `workspace/r006_macro_regime_factor_allocation/assumptions.md:162`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:701`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1440`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1532`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1618`
- 一句依据: AS13 明定月度均值与斜率主报 lag=6 并报告 lag=3/12，代码虽有 `newey_west_mean_sensitivity`，但正式构建链未调用；R25 与 R16 汇总均只接收单一 `nw_lag=6`，R16 的收益和 alpha 没有 3/12 敏感性输出。
- 建议: 让正式汇总按 `(3,6,12)` 输出明确 lag 维度，至少覆盖家族收益均值、R25 IC 均值与六因子 alpha，并将 lag=6 标识为主结果。

### CA-A04

- severity: critical
- 要素: B11
- 证据定位: `workspace/r006_macro_regime_factor_allocation/plan.md:309`、`workspace/r006_macro_regime_factor_allocation/plan.md:311`、`workspace/r006_macro_regime_factor_allocation/assumptions.md:94`、`workspace/r006_macro_regime_factor_allocation/assumptions.md:97`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:852`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:882`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1605`
- 一句依据: m2 明确要求构造A股市场/规模/价值/盈利/投资/动量控制并产出 `factor_control_returns.xlsx`，实际只有“验证调用方已提供六列”和回归接口，仓库内没有六因子收益构造器，正式 `build_family_sleeves_for_window` 也不接收或生成六因子收益；测试中的六列是手工合成输入。
- 建议: 使用 m1 股票月面板与按 `info_publ_date` 对齐的财务面板构造六条本地可投资控制组合，记录分组、权重、PIT 来源和缺失覆盖；任一必要腿不可构造时正式失败，不得填零或 synthetic。

### CA-A05

- severity: critical
- 要素: B11
- 证据定位: `src/r006_macro_regime_factor_allocation/family_sleeves.py:871`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:910`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:919`
- 一句依据: 六因子 alpha 以交易月末 `forward_return_date` 和控制表 `date` 做精确日期 inner join，而非按月 Period 对齐；独立 2020-01 至 2022-12 反例中 36 个共同月份只留下 26 个精确日期相同的月份，10 个月被静默丢弃并改变 alpha 样本。
- 建议: 双方先规范为唯一月度 Period 键，验证每月一行及共同月份覆盖，再回归；任何月份缺控制需在覆盖表显式报告，不能静默 inner-drop。

### CA-A06

- severity: critical
- 要素: R16
- 证据定位: `workspace/r006_macro_regime_factor_allocation/spec/coverage_matrix.md:65`、`workspace/r006_macro_regime_factor_allocation/plan.md:311`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:78`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1532`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1605`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1691`
- 一句依据: R16 的实现函数存在且未硬编码原文数值，但标称“完整可计算结果”的 `FamilySleeveAnalysis` 没有 R16 证据字段，正式构建函数既不接收六因子收益，也从未调用 `summarize_family_sleeve_evidence`，因此 done 行在正式调用链中不能产出袖套收益/NW/alpha/换手对齐表。
- 建议: 将 R16 汇总作为正式窗口构建的必达节点和返回字段；与六因子控制、成本敏感性及覆盖诊断一起进入后续输出器。

### CA-A07

- severity: major
- 要素: R25
- 证据定位: `workspace/r006_macro_regime_factor_allocation/assumptions.md:6`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:900`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:3125`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:219`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1487`
- 一句依据: 正式因子面板先按 m1 `fixed_factor_universe` 过滤，但 R25 的 `signals` 重新从完整元数据 crosswalk 计数，会把无正式观测或不在冻结主因子集的映射因子计入；独立反例得到 Valuation `signals=2`、`signals_with_ic=1`。
- 建议: R25 计数应以当前正式冻结因子集与实际可评价 IC 因子集分别命名并输出，主 `Signals` 使用与收益/IC 同一母集，完整元数据映射数只能作为独立映射审计列。

### CA-A08

- severity: minor
- 要素: F1, F12
- 证据定位: `workspace/r006_macro_regime_factor_allocation/assumptions.md:133`、`src/r006_macro_regime_factor_allocation/config.py:740`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:320`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1613`
- 一句依据: 横截面预处理默认最少 5 只股票是未在 spec/assumptions 登记的魔法参数，且覆盖了 m1 config 中方向估计最少 2 只股票的 authoritative 设置，会无声明地改变方向与 IC 可用月份。
- 建议: 将 m2 横截面最小样本数移入 config，并在假设登记簿说明用途；方向估计若委托 m1，应只采用 m1 的同一 authoritative 参数。

### CA-A09

- severity: minor
- 要素: B10
- 证据定位: `common/backtest.py:175`、`common/backtest.py:183`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1170`
- 一句依据: 当输入恰好只有一个有效 factor-month、但该截面已有 20 只股票足以分十组时，`assign_quantile_groups` 的单组 `groupby.apply` 返回形状被 pandas 解释为 DataFrame，向单列赋值触发 `ValueError`，合法单月十分位快照无法计算。
- 建议: 用按组返回同索引 Series 的 `transform` 或显式拼接实现分组，并增加单 factor-month、交易月末非日历月末的回归测试。

## 逐要素五维度核对

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查/调用链 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | 方向为训练窗月度 IC 均值取符号，预测块乘以冻结方向；与计划公式一致 | 1%/99% 一致；最小截面 5 未登记 | `fit_frozen_factor_directions` 存在且委托 m1 | `select_walk_forward_window` → m1 `fit_annual_frozen_factor_directions` → m1 apply，跨年可达 | AS2/AS11 已登记；最小截面见 CA-A08 | pass_with_issues |
| F2 | 八家族、字段优先级、最长词及固定冲突序与 AS26 一致 | `family_order/keywords/field_priority` 均来自 m1 config | `assert_frozen_crosswalk` 存在且非空 | 正式入口复算 SHA-256，映射因子才进入袖套 | AS3/AS26 已登记 | pass |
| F12 | 逐 factor-month Pearson IC，并附 Spearman Rank IC | common 两种 IC 均要求至少 5 个有效样本；m2 的 5 未在本案例登记 | `calculate_monthly_factor_ic` 存在且非空 | 正式窗口直接调用并聚合家族 IC | AS13 登记 Pearson 主、Rank 敏感性；见 CA-A08 | pass_with_issues |
| F13 | 逐月含截距横截面 OLS，斜率再做 NW，数学实现一致 | 默认控制列和 lag=3/6/12 与 AS13 一致 | `fama_macbeth_regression` 存在且非空 | 正式 m1→m2 控制构造和调用链缺失 | AS13 已登记，但实现未接上，见 CA-A02 | fail |
| F14 | 高十分位减低十分位、六因子 alpha 接口均存在 | 十组、EW/VW 与 AS11 一致 | `build_factor_decile_layer` 存在且非空 | 排序链可达；收益起点及 T+1 约束错误，alpha 正式链缺失 | 市场迁移/成本已登记；CA-A01/CA-A04 | fail |
| B9 | Bartlett HAC 公式与月度 NW 一致 | 主 lag=6、敏感性 3/12 的函数参数存在 | `newey_west_ols` 存在且非空 | FMB 内可达三档，但 R16/R25 正式输出只到 lag=6 | AS13 已登记；调用链漏报见 CA-A03 | fail |
| B10 | 十分位 10 高减低权重公式正确 | `n_quantiles=10` 一致 | `build_factor_decile_layer` 存在且非空 | 正式多月路径可达；T+2 可被接受，单 factor-month 崩溃 | AS11 已登记；CA-A01/CA-A09 | fail |
| B11 | 六列控制 OLS alpha 公式正确，缺列/缺值不填造 | MKT/SMB/HML/RMW/CMA/MOM 与 AS8 一致，主 NW=6 | `estimate_six_factor_alpha` 存在且非空 | 只有验证/回归接口，无六因子构造；月键 exact join 错误 | AS8 已登记；CA-A04/CA-A05 | fail |
| B12 | EW 每腿和为 ±1；VW 以 T 时点流通市值每腿归一 | `("EW","VW")` 与 spec 一致 | `build_factor_decile_layer` 存在且非空 | 因子层及家族等权聚合可达 | AS11 已登记 | pass |
| B13 | 八个重叠容量区间按月流通市值百分位实现 | 20/50/2/3/80/90% 与 AS12/B13 一致 | `assign_capacity_regions` 存在且非空 | 独立 API 可直接消费 T 时点面板，八区计数复算通过 | AS12 已登记 | pass |
| R16 | 代码不含原文 2.51、9.71 等基准硬编码，均从输入重算 | 收益/alpha 主 lag=6、换手口径正确；缺 3/12 输出 | `summarize_family_sleeve_evidence` 存在且非空 | 正式窗口结果不调用、不返回 R16 | “A股本地方法对齐，非原文数值对齐”已声明；CA-A03/CA-A06 | fail |
| R25 | 家族月度 IC 均值、NW t、最大单因子 NW t 从输入重算，无原文硬编码 | 主 lag=6 一致，但未报 3/12 | `summarize_family_signal_composition` 存在且非空 | 正式窗口可达；Signals 母集错误 | 本地方法对齐已声明；CA-A07 | fail |

## 空壳与虚报检查

coverage_matrix 的 12 个实现位置均真实存在，未发现 `pass`、`TODO`、`NotImplemented` 或只返回常量的空壳；R16/F13/B11 的问题是正式调用链不完整，不是函数位置不存在。

判定: found

## 独立运行与反例记录

| 检查 | 独立结果 |
| --- | --- |
| `uv run python -m compileall -q src/r006_macro_regime_factor_allocation common` | exit 0 |
| `uv run pytest -q tests/test_r006_m1.py` | 17 passed |
| `uv run pytest -q tests/test_r006_m2.py` | 6 passed |
| 跨年冻结反例 | `wf_202202_202301` 正确接纳 2022-02、2022-12、2023-01 交易月末，拒绝 2023-02；方向 hash/window_id 未漂移 |
| 训练标签截止 | m1 `select_training_history` 同时限制 signal Period 与 realization Period 不晚于 train_end；现有测试复算 3 个信号月只用 2 个已实现标签月 |
| T+1/T+2 反例 | 两个 20 股票 factor-month 的 T+2 标签被 `build_factor_decile_layer` 接受并计算 EW/VW 收益，触发 CA-A01 |
| 六因子月边界反例 | 36 个共同月份因交易月末/日历月末日期不同只回归 26 月，10 月静默丢失，触发 CA-A05 |
| 空 factors | `FormalDataUnavailableError`，明确写“禁止 synthetic” |
| 六因子缺列 | `M2ContractError`，缺少六列时不填零、不生成 alpha |
| EW/VW | 独立复算每个 EW/VW 高腿为 +1、低腿为 -1；首建单边换手为 1，10 bps 成本为 0.001 |
| 八容量区 | 100 股票反例得到 100/20/80/60/50/34/20/10，与 All/Micro/Outside/Middle/Upper half/Upper third/Large/Mega 定义一致 |
| R25 计数反例 | 完整 crosswalk 中 Valuation 2 个映射、正式 IC 仅 1 个时输出 `signals=2, signals_with_ic=1` |
| R16/R25 硬编码搜索 | 未发现原文 R16/R25 基准数值常量；输出值由输入重算 |

## 已检查维度清单

- [x] 公式一致：逐要素核对窗口、算子、分子分母、时点与 T/T+1。
- [x] 参数一致：核对 1%/99%、10 组、EW/VW、NW 3/6/12、六控制、容量断点、10/30 bps。
- [x] 实现位置真实：12 个 done 行的文件/函数均存在且非空壳。
- [x] 代码反查：核对 m2 正式入口、m1 authoritative 委托、公开统计函数与返回对象调用链。
- [x] 简化声明：核对 AS1-AS4、AS6、AS8、AS11-AS13、AS16-AS18、AS22-AS23、AS26；未发现 synthetic 或原文数值硬编码，发现未登记最小截面参数。

verdict: fail
