# r006 m1 实现忠实性审计

- mode: `code`
- milestone: `m1`
- 审计范围：`coverage_matrix.md` 中 m1 的 22 条 `done` 行；`plan.md`、`spec.md`、`assumptions.md`、`config.py`、`data_pipeline.py`、`__init__.py`、`tests/test_r006_m1.py` 及 `common/data_loader.py` 相关签名。
- 审读分离：未读取 coder 完成汇报，未采信任何完成声明；以下代码位置、真实本地 schema、计数与运行结果均独立检查。

## 独立运行与数据合同取证

1. 编译：`uv run python -m compileall -q src/r006_macro_regime_factor_allocation tests/test_r006_m1.py`，退出码 0。
2. 测试：`uv run pytest -q tests/test_r006_m1.py`，独立得到 `8 passed in 0.37s`。
3. 真实数据根：由 `common/data_loader.py:18-49` 独立解析为 `/Users/hedi/local_data`。
4. 真实 schema 盘点：`factor_factor_info.parquet` 为 419 行且含 `factor_id/factor_id_cn/level1/level2`；行情、交易、财务三表、宏观明细、指数和债券文件的配置字段均真实存在；`factors/` 实际 parquet 数为 0。
5. 真实 AS26 重算：419 个元数据因子中 mapped=186、unmapped=233、multiple_match=6；八家族计数依次为 18、9、3、40、0、44、49、23，`Investment/issuance` 为空；独立 SHA-256 为 `e84ee034fe95f38360768f93fdd807de4a626df86c3c7ad5543ca52d58c3683b`。
6. 正式模式缺数试跑：`build_m1_dataset()` 清晰抛出 `FormalDataUnavailableError`，定位为 `factors/` 中实际 parquet 数 0，错误文本明确“禁止自动 synthetic”；未发现 synthetic 生成或研报数值硬编码绕过。
7. 真实宏观加载重算：`load_macro_conditioning_inputs()` 返回 4,216 行、15 个唯一序列、7 个块，`available_date < observation_date` 违规数为 0。

## m1 done 行逐条五维核对

| 要素 | 公式/口径一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | 未完成月频/PIT 对齐 | 因子文件后缀、值列候选来自 config | `load_local_factor_panel` 存在且非空 | 只统一长表，不与信号日历或股票月面板对齐 | 未登记该缺口 | `deviation_undeclared`，见 CA-A01 |
| D2 | 月末前复权收益、T/T+1 分离已实现，但 ST 时点不符 AS23 | 新股 120 交易日来自 config | `build_monthly_stock_panel` 存在且非空 | 行情、交易、日历、停牌、涨跌停均可反查 | 未登记 ST 仅在 T 日过滤 | `deviation_undeclared`，见 CA-A03 |
| D3 | 只有历史截取，没有方向符号估计与年度冻结 | 训练边界来自窗口表 | `select_training_history` 存在且非空，但不是 D3 所述算法 | 全模块无方向拟合/符号产物 | 未登记省略 | `deviation_undeclared`，见 CA-A02 |
| D4 | 字段优先级、最长词、家族顺序、一对一和 SHA-256 与 AS26 一致 | 家族/关键词/哈希算法均来自 config | `build_factor_crosswalk` 存在且非空 | strict 路径能阻断空家族、重复 ID 和哈希漂移 | AS3/AS26 已登记 | `deviation_declared`；真实数据当前会因空家族阻断 |
| D5 | 不要求恰为 23 已由 AS5 声明，但 manifest 声称的候选源未全部进入真实加载路径 | 月/季滞后为 1/4 月，来自 config | `load_macro_conditioning_inputs` 存在且非空 | 当前实际为 15 序列、7 块；债券候选无读取分支 | 市场迁移已登记，源路径失真未登记 | 见 CA-A04 |
| D6 | `available_date=max(保守下限, info_publ_date)`，as-of 只向后 | 月/季滞后 1/4 月与 AS6/AS16 一致 | `apply_conservative_publication_lag` 存在且非空 | `align_macro_asof` 与 PIT audit 均复核不晚于信号日 | AS6/AS16 已登记 | consistent |
| D7 | 要求显式 `index_code`，月末原料只读 T 及以前；状态变换留给 m3 | 未静默硬编码指数代码 | `load_index_state_inputs` 存在且非空 | 指数行情、估值、成交三源可反查 | AS7/AS25 已登记 | consistent，但真实共同覆盖计算受 CA-A06 影响 |
| D8 | 财务记录按 `info_publ_date` as-of，`end_date` 仅作标签；六控制组合计算按 plan 留在 m2 | 财务字段来自 SourceSpec | `load_financial_pit_panel` 存在且非空 | 月收益/市值、财务和指数原料由 `M1Dataset` 分别承载 | AS8 已登记 | consistent（仅就 m1 原料合同） |
| D9 | 流通市值/成交换手存在；行业和历史 beta 不存在运行路径 | `standard_code=38` 配置存在但未使用 | 指向的 `build_monthly_stock_panel` 不实现完整 D9 | 全模块无行业加载、无历史 beta | 未登记省略 | `deviation_undeclared`，见 CA-A05 |
| D10 | 首次/末次非缺失月按本地因子重算 | 月频转换使用 config 的 `M` | `compute_factor_availability` 存在且非空 | 不读取 publication year，不冒充原发表年份 | AS10/AS20 已登记 | consistent |
| F16 | 预测年 Y 使用首次可用年不晚于 Y-1 | `Y-1` 与 spec 一致 | `build_publication_year_coverage` 存在且非空 | 输出明确为 `share_of_local_universe` | AS10 已登记 | `deviation_declared` |
| B1 | 本地起点替代 1963 已声明；真实“共同月”未按有效月交集求取 | 无硬编码 1963 | `compute_factor_availability` 存在且非空 | 调用方仅取边界 | AS4 已登记市场迁移，但补月未登记 | 见 CA-A06 |
| B2 | 首预测年度动态生成 | 无硬编码 1985 | `build_walk_forward_windows` 存在且非空 | 按自然年循环 | AS4 已登记市场迁移 | 受 CA-A06 影响 |
| B3 | 目标为初始 120 月；非 1 月共同起点时独立复算得到首窗 131 月 | config=120，但函数只检查 `>=120` | `build_walk_forward_windows` 存在且非空 | 测试仅覆盖 1 月起点 | 未登记偏离 | `deviation_undeclared`，见 CA-A06 |
| B4 | 固定 144 月验证已实现并显式断言 | config=144 | `build_walk_forward_windows` 存在且非空 | 训练/验证/预测不重叠检查存在 | 无未登记简化 | consistent |
| B5 | 训练 expanding、验证 rolling、按自然年预测已实现 | freeze=12 来自 config | `build_walk_forward_windows` 存在且非空 | 训练月数单调增加检查存在 | 无未登记简化 | consistent，但首窗受 CA-A06 影响 |
| B6 | 本地样本期替代 479 月已登记 | 不硬编码 479 | `build_walk_forward_windows` 存在且非空 | 支持末年不足 12 月 | AS4 已登记 | `deviation_declared`，但月份真实性受 CA-A06 影响 |
| B7 | T 月末信号映射到严格更晚的首个市场交易日 | 月末标记来自交易日历 | `build_execution_schedule` 存在且非空 | 股票、宏观、财务 PIT audit 可反查 | AS16 已登记 | consistent；个股 ST 执行过滤受 CA-A03 影响 |
| R14 | 本地保守时点替代原 ALFRED，能够生成逐序列 as-of 行和违规计数 | 1/4 月滞后来自 config | `align_macro_asof` 存在且非空 | `build_point_in_time_audit` 形成可运行证据链 | AS5/AS6/AS16 已登记 | `deviation_declared`，非抄表 |
| R23 | 能按预测年重算本地 eligible 数、占比和家族计数 | Y-1 规则一致 | `build_publication_year_coverage` 存在且非空 | 依赖真实 first_available_month | AS10 已登记 | `deviation_declared`，非抄表 |
| SA11 | 仅实现基础保守滞后；未实现额外滞后、市场 beta 残差袖套、正交化袖套及相对等权比较 | 基础 1/4 月正确 | 指向函数存在但不覆盖 SA11 测试 | 全模块无 sensitivity 计算路径 | 未登记省略 | 见 CA-A07 |
| SA13 | 能按预测年统计本地可用数和家族覆盖 | Y-1 规则一致 | `build_publication_year_coverage` 存在且非空 | 与 R23 共用真实计算路径 | AS10 已登记 | `deviation_declared`，非抄表 |

## 空壳判定

矩阵所列函数名均真实存在，未发现 `pass`、`TODO` 或 `NotImplemented` 空函数；下列判定只表示“函数实体存在”，不表示其语义完整，D1/D3/D9/SA11 的错配已分别列为 issue。

判定: found

## issues

### CA-A01

- severity: critical
- 要素: D1、B7
- 证据定位: `workspace/r006_macro_regime_factor_allocation/plan.md:287-299`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:513-621`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:1820-1825`
- 依据: `load_local_factor_panel` 仅把任意 `date/signal_date` 因子文件整理成长表，既不强制股票月频、不对齐交易月末信号日，也不记录/检查因子最大源日期；因此一个日频、月中或时点含义不明的文件可通过正式布局检查并进入 `M1Dataset`，不满足 m1 的月频 point-in-time 因子面板合同。
- 建议: 将因子观测显式映射到 `execution_schedule.signal_date`，验证原始源日期不晚于信号日、键为唯一 stock-month-factor；对无法证明时点语义的布局正式失败，并把源日违规计入 PIT audit。

### CA-A02

- severity: critical
- 要素: D3
- 证据定位: `workspace/r006_macro_regime_factor_allocation/spec/coverage_matrix.md:11`；`workspace/r006_macro_regime_factor_allocation/assumptions.md:16-24`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:1615-1679`
- 依据: 矩阵把 D3 标为 `done` 并指向 `select_training_history`，但该函数只筛选日期，完全没有按训练期下一月收益估计 \(s_j\in\{-1,+1\}\)、处理零/缺失相关、生成方向表或在验证/预测年度冻结；实现位置与核心要素语义不相符。
- 建议: 增加可独立调用的方向拟合与冻结函数，输入必须先经过 `select_training_history(..., realization_date_column=...)`，输出 factor_id、训练窗、方向、估计量和冻结哈希，并添加验证/预测收益扰动不改变已冻结方向的测试。

### CA-A03

- severity: critical
- 要素: D2、B7
- 证据定位: `workspace/r006_macro_regime_factor_allocation/assumptions.md:289-297`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:926-984`
- 依据: AS23 要求在执行日剔除 ST、停牌和不可成交涨跌停，代码却只在 `signal_date` 计算 `is_st_on_signal`，`execution_buyable/execution_sellable` 仅检查执行日停牌和涨跌停；T 日非 ST、T+1 变为 ST 的股票仍被标为可执行。
- 建议: 对 ST 区间同时以 `execution_date` 计算 `is_st_on_execution`，将其纳入买入/卖出可执行标记，并补充跨月 ST 状态变化的单元测试。

### CA-A04

- severity: major
- 要素: D5
- 证据定位: `src/r006_macro_regime_factor_allocation/config.py:452-471`；`src/r006_macro_regime_factor_allocation/config.py:532-634`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:1350-1376`
- 依据: D5 substitute manifest 声称 `bond_yield_curve`、`bond_shibor`、`csiindex_trade`、`index_value` 均属于本地候选源，但 `MACRO_SERIES_SPECS` 没有任何债券曲线/SHIBOR 候选，`load_macro_conditioning_inputs` 只能遍历该配置；独立实跑只得到 15 序列、7 块，故 manifest 中至少两类“明细 fallback”并无真实加载路径。
- 建议: 为利率/期限结构补齐债券曲线和 SHIBOR 的明确筛选及 fallback 规格，或从 D5 manifest 删除未消费源并说明指数原料只由 D7 提供；manifest 应区分“实际消费”“可选候选”“仅审计存在”。

### CA-A05

- severity: critical
- 要素: D9
- 证据定位: `workspace/r006_macro_regime_factor_allocation/spec/coverage_matrix.md:17`；`src/r006_macro_regime_factor_allocation/config.py:513-519`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:812-1004`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:1905-1920`
- 依据: D9 的替代合同包含申万一级行业和只用历史数据的 beta，但矩阵所指函数只产生市值、成交和换手；`industry_standard_code=38` 从未使用，`stock_industry` 未加载，模块中也没有历史 beta 计算或输出字段，`M1Dataset` 不承载二者。
- 建议: 在 m1 明确产出行业映射及历史 beta 原料/估计值，beta 窗口只读 T 及以前市场与个股收益；若决定留到 m3，则 D9 不应在 m1 标 `done`，实现位置应回填真实函数。

### CA-A06

- severity: critical
- 要素: B1、B2、B3、B5、B6
- 证据定位: `workspace/r006_macro_regime_factor_allocation/plan.md:229-238`；`workspace/r006_macro_regime_factor_allocation/plan.md:292-299`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:1537-1612`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:1852-1879`
- 依据: 正式调用方只根据各源的最小/最大边界生成 `pd.period_range(common_start, common_end)`，会把任一源实际缺失的中间月份补进“共同历史”，使函数内部连续性检查失效；同时窗口函数只要求首个训练窗 `>=120`，独立用 2000-02 起的 300 月重算得到首预测年 2023、首训练窗 131 月，而非计划/config 的初始 120 月。
- 建议: 以因子有效月、股票有效月、每个宏观序列已可用月和指数非缺失月的真实交集构造月索引，禁止从边界补月；明确非 1 月共同起点的年度对齐规则，并断言首窗恰为 120 月、验证恰为 144 月、预测年冻结不超过且对应实际 12 个月。

### CA-A07

- severity: major
- 要素: SA11
- 证据定位: `workspace/r006_macro_regime_factor_allocation/spec/spec.md:1355-1361`；`workspace/r006_macro_regime_factor_allocation/spec/coverage_matrix.md:88`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:1238-1270`；`src/r006_macro_regime_factor_allocation/data_pipeline.py:1747-1753`
- 依据: SA11 要求发布滞后与时点比较，测试设计包含市场 beta 残差袖套、正交化袖套、额外滞后相对等权配置；当前实现只有基础 `available_date` 和零违规计数，没有任何额外滞后变体、袖套重算或比较统计，不能把 SA11 标为已完成。
- 建议: 增加独立 sensitivity 入口，固定额外滞后规则并重新形成状态/袖套/配置，与等权及基础滞后输出同样本差异；在该路径实现前将 SA11 保持未完成。

## 已检查维度结论

- [x] 公式一致：逐一核对 D1-D10、F16、B1-B7、R14、R23、SA11、SA13 的窗口、算子、时点、替代语义和实际函数体。
- [x] 参数一致：反查 120/144/12 月、1/4 月宏观滞后、120 交易日、`standard_code=38`、SHA-256、T/T+1；发现首训练窗非 1 月起点可变为 131 月。
- [x] 实现位置真实：22 条 `done` 行全部打开定位；函数实体均存在且非 pass/TODO，但 D1、D3、D9、SA11 存在语义错配。
- [x] 代码反查：反查 `data_pipeline.py` 全部公开函数、`__init__.py` 导出与 `common/data_loader.py` 签名；未发现 m1 外私货，发现调用链以边界制造共同月份。
- [x] 简化声明：对照 assumptions；市场迁移、宏观保守滞后、publication-year 替代均有登记，D1/D3/D9/SA11 缺失及月份补齐未登记。

VERDICT: fail
