# r006 m1 coder-fix 独立复审

- mode: `code`
- milestone: `m1`
- 审计范围：`coverage_matrix.md` 中 m1 的 22 条 `done` 行；原审计 `impl_audit_m1_round1.md` 的 CA-A01..07；`plan.md`、`spec.md`、`assumptions.md`、修复后的 `config.py`、`data_pipeline.py`、`__init__.py`、`tests/test_r006_m1.py`。`family_sleeves.py` 与 `tests/test_r006_m2.py` 仅用于 m1→m2 接口和回归风险复核，未审计 m2 结论。
- 审读分离：未读取 coder 完成汇报或主会话完成叙事，未采信完成声明；函数体、真实 parquet schema、实际加载行数、门禁、窗口和反例均独立检查或重算。

## 独立运行与数据合同取证

1. 编译：独立运行 `uv run python -m compileall -q src/r006_macro_regime_factor_allocation tests/test_r006_m1.py tests/test_r006_m2.py`，退出码为 0。
2. m1 测试：独立运行 `uv run pytest -q tests/test_r006_m1.py`，结果为 `15 passed in 0.44s`。
3. m2 回归：独立运行 `uv run pytest -q tests/test_r006_m2.py`，结果为 `4 passed in 1.27s`。
4. 正式缺数保护：独立重算 `/Users/hedi/local_data/factors/` 实际 parquet 数为 0；`audit_local_sources()` 返回 `formal_ready=False`，`build_m1_dataset()` 抛出 `FormalDataUnavailableError` 且首行明确“禁止自动 synthetic”；`build_m1_dataset(dry_run=True)` 的因子面板为 0 行。代码反查未发现随机数、mock 因子或 synthetic 生成路径。
5. 债券与 SHIBOR 实际加载：独立读取真实 parquet，`bond_yield_curve.parquet` 为 4,387,111 行，`bond_shibor.parquet` 为 2,160 行；逐个执行 fallback 转换得到 `bond_yield_10y=2,750`、`term_spread=2,750`、`credit_spread=2,750`、`lpr_1y(SHIBOR)=270` 条非缺失观测，证明修复后不是仅登记 manifest。
6. 宏观常规加载：`load_macro_conditioning_inputs()` 独立返回 4,216 行、15 个序列、7 个外部块；D7 的 `build_market_macro_inputs()` 负责补入第八个 Trend 块。常规源优先级实际选中 `macro_cache/macro_lpr/macro_pmi`，债券与 SHIBOR 当前作为可运行 fallback 而非主源。
7. 行业正式保护：真实 `ashare_stock_industry.parquet` 为 14,135 行，但仅有静态行业字段、没有 `effective_date/in_date/out_date`；独立调用 `load_industry_pit_mapping()` 明确抛出 `FormalDataUnavailableError`，没有把静态行业伪装为历史 PIT。
8. 窗口独立重算：2000-02 起 300 个连续月得到首训练 120 月、验证 144 月、预测 12 月；删除任一中间月会被连续性门禁拒绝。但 2000-01 起仅 270 个月时仍生成一个 6 月预测窗，见 CA-A09。
9. 反例重算：构造八块原料均曾非缺失、但样本信号期内 Trend 全为空的输入后，八块入口门禁通过，`build_common_month_index()` 仍返回 2 个“共同月”，见 CA-A08。
10. 接口反例重算：非一月共同起点产生 `2022-02-28` 至 `2023-01-31` 的 12 月预测块，但 m1 冻结方向以 `prediction_year=2022` 拒绝应用到块末 `2023-01-31`，见 CA-A10；另以实际交易月末 `2010-01-29` 对日历边界 `2010-01-31` 复算，m2 精确日期过滤会丢弃验证首月，见 CA-A11。

## 原 CA-A01..07 逐条复审

| 原 issue | 修复语义与测试独立核对 | 当前状态 |
| --- | --- | --- |
| CA-A01 | `load_local_factor_panel` 保留 `source_date/source_date_semantics`；`align_factor_panel_to_schedule` 校验源日不晚于正式信号日、显式信号日精确匹配，并将键收敛为唯一 `stock_code-signal_date-factor_id`；对应单测通过。 | pass |
| CA-A02 | `select_training_history` 同时限制观察月与标签实现月不晚于 `train_end`；`fit_annual_frozen_factor_directions` 只用训练期下一月收益关系估方向并形成冻结哈希；验证/预测收益扰动测试通过。原“完全未实现方向”已修复，跨年应用另见 CA-A10。 | pass |
| CA-A03 | `build_monthly_stock_panel` 分别计算 `is_st_on_signal` 与 `is_st_on_execution`，执行日 ST 同时进入买入/卖出门禁；跨 T/T+1 状态单测通过。 | pass |
| CA-A04 | 债券曲线与 SHIBOR 已进入 `MACRO_SERIES_SPECS` 和真实转换分支；四个 fallback 用真实文件均能产生非缺失观测。原“manifest 有源、加载无分支”已修复；样本期八块完整性另见 CA-A08。 | pass |
| CA-A05 | 行业连接要求历史生效区间，实际缺字段时正式失败；历史 beta 的滚动窗口最大源月为 T，未使用 T 后收益；容量控制面板同时承载市值、行业、beta、成交和换手。 | pass |
| CA-A06 | 共同月已改为因子、股票、逐宏观序列和指数真实非缺失月份的集合交集，并拒绝中间缺月；首训练窗精确为 120 月、验证窗精确为 144 月。预测窗仍可短于 12 月，故原 issue 仅部分修复，见 CA-A09；非一月接口另见 CA-A10/CA-A11。 | fail |
| CA-A07 | `run_sa11_sensitivity` 产生 base、extra_lag、market_beta_residualized、orthogonalized、equal_weight 五条路径，先取五方共同非缺失月份，再统一计算相对等权差；滚动 beta 严格 `shift(1)`，对应同样本测试通过。 | pass |

## m1 全部 done 行五维核对

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | 源观测映射同月正式交易月末且 `source_date <= signal_date` | 日期语义、月频和唯一键由 config/日历驱动 | `align_factor_panel_to_schedule` 存在且非空 | 正式构建实际调用并把因子 PIT 检查写入 audit | AS1 已登记市场替代 | consistent |
| D2 | 月末前复权收益、T 信号与 T+1 执行状态分离 | 新股 120 交易日；执行日 ST/停牌/涨跌停均入门禁 | `build_monthly_stock_panel` 存在且非空 | 正式股票加载链实际调用 | AS4/AS23 已登记 | consistent |
| D3 | 训练期逐月横截面 IC 均值定向，标签实现日不越过训练末月 | 方向最少横截面 2、零/缺失方向正式失败 | `fit_annual_frozen_factor_directions` 存在且非空 | 估计函数和应用函数可反查，但非一月预测块无法完整应用 | AS2 未登记跨年块被拒绝 | `deviation_undeclared`，见 CA-A10 |
| D4 | 字段优先级、最长词、家族顺序、一对一与哈希符合 AS26 | 八家族顺序和 SHA-256 固定 | `build_factor_crosswalk` 存在且非空 | strict 路径阻断空家族、重复 ID 和哈希漂移 | AS3/AS26 已登记 | consistent |
| D5 | 债券/SHIBOR fallback 可真实转换，D7 补 Trend 后构成八块角色 | 债券曲线代码、期限、SHIBOR 期限和源优先级均集中配置 | `ensure_macro_block_coverage` 存在且非空 | raw 全局门禁与共同月门禁可反查，但样本期整块全缺仍可漏过 | AS5/AS25 不允许缺块月份生成主结果 | `deviation_undeclared`，见 CA-A08 |
| D6 | `available_date=max(保守下限, info_publ_date)`，as-of 只向后 | 月度 1 月、季度 4 月 | `apply_conservative_publication_lag` 存在且非空 | `align_macro_asof` 和 PIT audit 可反查 | AS6/AS16 已登记 | consistent |
| D7 | 明确 `index_code`，指数各源最大日期不晚于 T | 不静默硬编码基准指数 | `load_index_state_inputs` 存在且非空 | D7 输出实际进入 Trend 与历史 beta | AS7/AS25 已登记 | consistent |
| D8 | 财务按 `info_publ_date` as-of，`end_date` 只作报告期标签 | 三表字段由 SourceSpec 固定 | `load_financial_pit_panel` 存在且非空 | 正式构建实际调用；六控制组合留在 m2 | AS8 已登记 | consistent（m1 原料合同） |
| D9 | 行业按历史生效区间；beta 只用 T 及以前；市值/成交/换手同时输出 | `standard_code=38`、beta 60 月且至少 36 月 | `build_capacity_control_panel` 存在且非空 | 正式构建实际调用；真实静态行业源会明确失败 | AS9 已登记；没有伪造历史行业 | consistent（当前正式数据 infeasible） |
| D10 | 首次/末次非缺失月按实际因子面板计算 | 月频转换固定 | `compute_factor_availability` 存在且非空 | 不读取或冒充 publication year | AS10/AS20 已登记 | consistent |
| F16 | 预测标签 Y 统计首次可用年不晚于 Y-1 | `Y-1` 与 spec 一致 | `build_publication_year_coverage` 存在且非空 | 输出明确为本地可用覆盖 | AS10 已登记 | `deviation_declared` |
| B1 | 四类数据按实际非缺失月交集，不再用边界补洞 | 共同月按月期去重 | `build_common_month_index` 存在且非空 | 因宏观全缺列被 pivot 丢弃，交集仍有漏检 | AS4/AS25 不支持该漏检 | 见 CA-A08 |
| B2 | 首预测周期由共同样本前 264 月之后开始 | 无硬编码 1985 | `build_walk_forward_windows` 存在且非空 | 非一月起点按 12 月块推进，但“年份”与块边界不一致 | AS4 仅登记市场迁移 | 见 CA-A10 |
| B3 | 首训练块严格取最前 120 个连续实际月份 | config=120 且显式断言相等 | `build_walk_forward_windows` 存在且非空 | 非一月起点反例仍为精确 120 月 | 无未登记简化 | consistent |
| B4 | 验证块严格固定 144 个连续月份 | config=144 且逐窗断言 | `build_walk_forward_windows` 存在且非空 | m1 月边界传给 m2 精确日过滤会丢首月 | 未登记接口边界损失 | 见 CA-A11 |
| B5 | 训练 expanding、验证 rolling、预测每次推进 12 月 | config 目标为 12，但最后一块允许任意非空长度 | `build_walk_forward_windows` 存在且非空 | 270 月反例只生成 6 月预测块；跨年块方向应用不完整 | 未登记不足 12 月与跨年行为 | 见 CA-A09、CA-A10 |
| B6 | 本地样本期替代原 479 月 | 不硬编码原 479 | `build_walk_forward_windows` 存在且非空 | 样本末段会作为不足 12 月的独立预测块输出 | AS4 只登记样本缩短，未登记短冻结块 | 见 CA-A09 |
| B7 | T 月末信号映射到严格更晚的首个交易日 | T/T+1 规则固定 | `build_execution_schedule` 存在且非空 | 股票、因子、财务、宏观 PIT audit 均可反查 | AS16/AS23 已登记 | consistent |
| R14 | 本地保守时点输出逐序列 as-of 记录与违规计数 | 1/4 月滞后来自 config | `align_macro_asof` 存在且非空 | `build_point_in_time_audit` 形成证据链 | AS5/AS6/AS16 已登记 | `deviation_declared` |
| R23 | 按预测标签重算本地 eligible 数、占比和家族计数 | Y-1 规则一致 | `build_publication_year_coverage` 存在且非空 | 依赖实际 first_available_month | AS10 已登记 | `deviation_declared` |
| SA11 | 五条路径在统一共同样本上比较，滚动暴露严格滞后一期 | 额外滞后 1 月、beta 60 月且至少 24 月 | `run_sa11_sensitivity` 存在且非空 | 五路径、相对等权差与暴露审计均可反查 | 未发现额外未登记简化 | consistent |
| SA13 | 按预测标签统计本地可用数和家族覆盖 | Y-1 规则一致 | `build_publication_year_coverage` 存在且非空 | 与 R23 共用实际计算路径 | AS10 已登记 | `deviation_declared` |

## 空壳判定

22 条 m1 `done` 行登记的实现函数均真实存在；独立搜索未发现其函数体为 `pass`、`TODO`、`NotImplemented` 或仅返回占位常量。语义缺陷已单列 CA-A08..CA-A11。

判定: found

## issues

### CA-A08

- severity: critical
- 要素: D5、B1
- 证据定位: `workspace/r006_macro_regime_factor_allocation/assumptions.md:58`、`workspace/r006_macro_regime_factor_allocation/assumptions.md:318-323`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:2151-2169`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:2222-2234`
- 依据: 八块门禁只检查全样本原料中每块曾有非缺失值，而 `pivot_table` 会丢掉信号期内整列全空的序列且代码计算的 `expected_series` 未参与校验；独立反例中 Trend 在全部信号月均为空仍返回 2 个共同月，违反任一预测月必须具备八块完整状态的核心合同。

### CA-A09

- severity: critical
- 要素: B5、B6
- 证据定位: `workspace/r006_macro_regime_factor_allocation/plan.md:293`、`src/r006_macro_regime_factor_allocation/config.py:719-722`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:2303-2308`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:2321-2326`
- 依据: 预测切片只要求非空并把 `freeze_months` 设为 `min(12, 实际长度)`，独立输入 270 个连续月只生成 6 月预测窗，未满足本次复审要求的精确 120/144/12，且该核心短窗简化未在 assumptions 登记。

### CA-A10

- severity: critical
- 要素: D3、B2、B5
- 证据定位: `workspace/r006_macro_regime_factor_allocation/assumptions.md:19`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:2303-2326`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:2499-2547`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:2561-2565`
- 依据: 非一月共同起点会形成跨自然年的 12 月预测块，但冻结对象只保存起始自然年且应用函数拒绝所有不同自然年的行；独立重算的 2022-02 至 2023-01 预测块无法把同一冻结方向应用到 2023-01，核心年度冻结语义内部不一致。

### CA-A11

- severity: major
- 要素: B4、B5；m1→m2 接口
- 证据定位: `src/r006_macro_regime_factor_allocation/data_pipeline.py:2252-2255`、`src/r006_macro_regime_factor_allocation/data_pipeline.py:2312-2320`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:543-546`、`src/r006_macro_regime_factor_allocation/family_sleeves.py:1597-1605`
- 依据: m1 把实际交易月末统一改写为日历月末并输出为窗口精确日界，m2 再用该日界做 `between`；独立反例中验证起点为 2010-01-31 时实际交易信号日 2010-01-29 被排除，导致固定验证窗少一个真实月份。

## 已检查维度结论

- [x] 公式一致：逐条核对 D1-D10、F16、B1-B7、R14、R23、SA11、SA13 的公式、算子、分子分母、窗口和 T/T+1 时点；发现 CA-A08、CA-A10、CA-A11。
- [x] 参数一致：独立核对并反例重算 120/144/12、月/季 1/4 月滞后、上市 120 交易日、申万 `standard_code=38`、beta 60/36、SA11 beta 60/24、债券曲线与 SHIBOR 参数；发现 CA-A09。
- [x] 实现位置真实：22 条 m1 `done` 行逐条打开函数体，均存在且非空壳；语义缺陷不以“函数存在”代替完成判定。
- [x] 代码反查：反查正式 `build_m1_dataset` 调用链、`__init__.py` 公开导出，以及 m2 对 m1 窗口/因子合同的消费方式；未发现 strategy.py 私货，发现 CA-A08、CA-A10、CA-A11 的漏检或接口风险。
- [x] 简化声明：逐项对照 assumptions；市场迁移、保守滞后、publication-year 替代、静态行业缺时点正式失败均已声明或保守阻断，短预测窗、跨年冻结拒绝和日历月末接口损失未登记。

VERDICT: fail
