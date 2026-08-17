# r007 m1 实现对照审计

- mode: `code`
- milestone: `m1`
- 审计范围: `D1,D2,D3,D4,D5,D6,D7,D8,F1,F2,F3,B1,B2,B3,B4`
- 审计原则: 只读对照 `spec.md`、`plan.md`、`assumptions.md`、模板、数据目录、公共接口、实现和覆盖矩阵；不采信实现者自述。所有数据规模、公式、时点和参数结论均由本次审计独立读取或重算。

## 一、结论

m1 不通过。实现函数均真实存在且不是 `pass`、`TODO` 或 `NotImplementedError` 空壳；F1–F3、B2–B4 的核心计算在静态反查和极小样本独立重算中与 spec/assumptions 一致。但是，真实数据文件 `~/local_data/usshare_stock_quote.parquet` 在 2014–2021 年仅有 30 个股票代码，无法满足 B1 的美国市场 500 只股票要求；实现按自身保护逻辑会直接抛出 `ValueError`，所以 D1、D6、B1 的 `done` 状态及 m1 双市场面板交付不可成立。

阻断 issue 数: critical 1；major 0；minor 0。

## 二、issue

### CA-A01

- severity: critical
- location: `workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:9`、`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:14`、`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md:42`、`src/r007_cross_market_return_forecasting/data_pipeline.py:382`、`src/r007_cross_market_return_forecasting/data_pipeline.py:393`
- evidence: B1/spec 要求美、中各取 500 只股票，代码也在少于 500 时于 `data_pipeline.py:393-397` 显式失败。本次直接读取 `/Users/hedi/local_data/usshare_stock_quote.parquet` 并对 `2014-01-01 <= date <= 2021-12-31` 独立过滤重算，得到 12,902 行、2,015 个交易日、30 个股票代码、30 个具有正市值的代码，单日横截面行数中位数仅 6；直接调用实现的美国平均市值选池接口得到 `ValueError: US 仅有 30 只股票具备正市值，少于 B1 要求的 500 只`。因此 D1 的替代数据不足以承载 B1，D6 虽有平均市值算法但无法生成要求的美国 500 股池，B1 的实现链路阻断，所有依赖双市场 500 股面板的下游步骤均不能执行。
- basis: core 数据和股票池要求无法满足，且覆盖矩阵将 D1/D6/B1 标为 `done`，属于完成状态与真实可执行性冲突。
- suggestion: 更换或补全覆盖 2014–2021 且至少含 500 个合格美国股票代码的真实日频数据；在重新标记 `done` 前独立验证交易所范围、逐年股票数、逐日横截面密度、正市值代码数和最终 500 股列表。若短期无法补数，应将受影响要素回退为未完成/不可行并重新裁定 feasibility，不得继续把 30 股样本称为 B1 的 500 股复现。

## 三、coverage_matrix m1 done 行逐条核对

| 要素 | 公式/参数核对 | 实现位置真实性与代码反查 | 独立核验结论 |
| --- | --- | --- | --- |
| D1 | 路径为 `usshare_stock_quote.parquet`，与 AS10 一致 | `load_us_stock_quotes` 存在，执行列裁剪、2014–2021 日期下推、股票代码过滤和唯一键检查 | **fail**；真实研究期仅 30 个代码，不能承载 B1，见 CA-A01 |
| D2 | 路径为 `ashare_stock_price_forward.parquet` + `ashare_stock_trade.parquet`，与 AS11 一致 | `load_cn_stock_quotes` 存在；两表均按列/日期/代码裁剪，唯一键后用 `outer one_to_one` 合并，缺失不填补 | pass |
| D3 | 使用个股当日 `open`、`close` | `standardize_us_quotes` 与 `standardize_cn_quotes` 均真实输出标准 OHLC，非法数值后续收益函数转缺失 | pass |
| D4 | SPY 替代为经元数据和覆盖审计确认的美国宽基，属于 AS12 已登记迁移 | `discover_us_broad_index`/`load_us_market_index` 非空壳；本次独立重算唯一候选为 `SPX/标普500指数`，2014–2021 有效 OHLC 日期 2,015/2,015、重复键 0 | pass（market-transplant 已声明） |
| D5 | 513500.SH 替代为 `000300`，与 AS13 一致 | `load_cn_market_index` 非空壳；本次独立重算 `000300` 在 A 股交易日历的有效 OHLC 日期 1,950/1,950、重复键 0 | pass（market-transplant 已声明） |
| D6 | 2014–2021 全样本正市值记录按股票求均值 | `stream_average_market_cap` 使用列裁剪、日期谓词和分批聚合；`select_average_market_cap_universe` 排序取前 500，并明确记录全样本机械前视 | 算法 pass；美国数据可执行性 **fail**，见 CA-A01 |
| D7 | 美股 `close×volume`，A 股直接 `turn_value`，再取预测日前 21 日中位数 | 三个矩阵定位函数均存在；滚动中位数先 `shift(1)`，只用历史行 | pass；单位迁移见下文独立重算 |
| D8 | 目标开盘前最近已完成源市场交易日；US→CN `l=1`、CN→US `l=0` | `build_bidirectional_calendar_mappings` 调用双方向 `backward as-of`，使用纽约/上海时区和真实开收盘时刻，并断言源收盘早于目标开盘 | pass |
| F1 | `log(close_t/close_{t-1})` | `calculate_raw_log_returns` 逐股票排序后对 `close` 做 `shift(1)`，分子分母及时点一致 | pass |
| F2 | `log(close_t/open_t)` | 同一函数对当日 `close/open` 取对数；非正或非有限价格转缺失 | pass |
| F3 | 个股同口径原始收益减同日市场宽基收益 | `attach_market_excess_returns` 按日期 `many_to_one` 左连接，分别计算 pvCLCL/OPCL 差值 | pass |
| B1 | 两市场各 500 只、2014–2021 全样本平均市值最高 | `build_dual_market_universes` 确实请求每市场 500；前视边界以 `selection_uses_full_sample` 和 `mechanical_lookahead_acknowledged` 明示 | **fail**；美国仅 30 个正市值代码，见 CA-A01 |
| B2 | 每个更新锚点前 250 个历史日，逐股/逐收益列按 0.5%/99.5% 分位缩尾 | `winsorize_training_window` 先用 `< anchor` 的最后 250 个唯一日期拟合逐股分位，再用固定界限裁剪；`fit_end < anchor` 有断言 | pass；十日锚点调度属于后续 B6/m2，当前函数不自行重训 |
| B3 | 默认使用 pvCLCL/OPCL 市场超额收益 | `build_market_return_panel` 顺序执行原始收益、宽基收益、同日扣减，输出两类 excess 列 | pass |
| B4 | US→CN `l=1`、CN→US `l=0`；以市场时段保证信息可得 | 配置值分别为 1/0；实现按目标开盘前已完成源收盘做 as-of 映射。常规交易日上分别落到前一美国交易日/同一中国交易日，节假日自动回退到最近已完成交易日 | pass |

## 四、独立重算与证据

### 4.1 数据路径、字段、裁剪和覆盖

- `common.data_loader.get_data_root()` 本次解析为 `/Users/hedi/local_data`，与实现 `DataFiles.root` 的路径来源一致。
- 七个 m1 数据文件均真实存在；本次直接读取 Parquet schema，D1/D2/D4/D5/D8 所需字段均存在。日期字段均为 timestamp；关键字段包括美股 OHLC/`volume`/`market_cap`、A 股前复权 OHLC、A 股 `turn_value`/`market_value`、两类指数 OHLC 及 A 股 `IfTradingDay`。
- `_read_parquet_filtered` 在 `data_pipeline.py:183-221` 只读取显式列，并把日期、代码条件下推到 Parquet；代码集合为空时拒绝退化为全表读取。D1/D2 loader 随后校验 `(stock_code,date)` 唯一键。
- 阻断数字由实际文件独立计算：美股研究期 12,902 行、30 个代码、2,015 个日期；不是根据 data_catalog 的“2000-01 至今”文字推断，也不是采信实现者声明。

### 4.2 公式与市场超额收益

以单股四日合成样本独立重算：

- `close=[10,12,9,14]` 时，F1 后三日应为 `log(12/10)=0.182322`、`log(9/12)=-0.287682`、`log(14/9)=0.441833`，实现逐位一致。
- 同期 `open=[10,11,12,13]` 时，F2 为 `0`、`0.087011`、`-0.287682`、`0.074108`，实现逐位一致。
- 第二日个股 pvCLCL 为 `0.182322`、市场 pvCLCL 为 `log(1.1)=0.095310`，F3 得 `0.087011`；实现逐位一致。OPCL 同样逐日用个股值减市场值。
- 实现未对缺失、非正或无穷价格做收益填补，符合 AS2 的“不填补收益”边界。

### 4.3 成交金额单位与 21 日历史窗口

- 美股实现使用 `close×volume`。本次从真实美股研究期有效样本独立计算 `turn_value/(close×volume)`，中位数约 `9.9976e-5`，与源表 `turn_value` 以万单位存储、`close×volume` 还原为原币金额的数量级一致；代码没有误把源表的万单位 `turn_value` 当作美元直接使用。
- A 股实现直接使用 `ashare_stock_trade.turn_value`，不以受前复权因子影响的 `close×volume` 替代，符合 AS9。data_catalog 未认证币种单位，因此实现将单位状态明确记作 `declared_not_source_certified`；该限制已由 AS9 登记，不构成未声明简化。
- 三日极小样本 `traded_amount=[100,200,300,400]` 独立核验时，窗口为 3、最少观测为 1 的历史中位数依次为 `NaN,100,150,200`，证明实现先 `shift(1)`，没有把当日成交金额纳入预测日前窗口。正式默认窗口参数为 21。

### 4.4 股票池前视边界

- `SampleConfig` 固定 2014-01-01 至 2021-12-31 和每市场 500 只。
- `stream_average_market_cap` 只聚合该全样本内正且有限的市值；输出 `selection_start`、`selection_end`、`selection_uses_full_sample=True`。
- 最终选池另写 `mechanical_lookahead_acknowledged=True`。这与 spec 明确承认的全样本机械前视一致，未把它伪装成滚动可得股票池。
- 但边界声明不能消除 CA-A01 的数据数量阻断。

### 4.5 缩尾、缺失与未来函数

- B2 的下/上分位参数分别为 0.005/0.995，窗口为 250 个历史唯一日期，并按 `(stock_code,value_column)` 分组；分子、分母、窗口、算子和逐股口径均与 spec/AS5 一致。
- 拟合仅选择 `date < anchor_date`，并断言 `fit_end < anchor_date`；应用阶段复用既有界限，不重估未来分位。
- 合成窗口重算中，锚点 2020-01-06 的拟合终点为 2020-01-03，未包含锚点或未来行。
- `complete_case_training_rows` 仅删除目标与候选特征的含缺失行，不填补、不前后向借值；样本不足后是否估计模型由 m2/m3 负责。
- 十日更新锚点调度属于 B6/m2，目前 coverage 仍为 pending；m1 没有把任意每日重估冒充 AS5 的十日调度。

### 4.6 跨时区日历、信息可得性与 T+1

- 纽约时区使用 `America/New_York` 09:30–16:00，上海使用 `Asia/Shanghai` 09:30–15:00；本地时间转 UTC 后做 `merge_asof(..., direction="backward", allow_exact_matches=False)`。
- US→CN 合成核验：目标 2020-01-03 上海开盘映射到 2020-01-02 美国收盘，信息年龄 4.5 小时，对应 `l=1`；周末后的 2020-01-06 映射到 2020-01-03，信息年龄 52.5 小时。
- CN→US 在常规同日中国收盘已早于美国开盘时映射同一中国交易日，对应 `l=0`。节假日不要求自然日期相同。
- `map_signals_to_next_target_session` 使用 `searchsorted(..., side="right")`，将 T 日严格映射到晚于 T 的下一目标交易日；合成日历中 2020-01-02 信号映射 2020-01-03，2020-01-03 映射 2020-01-06。该 helper 尚未被当前 m1 面板调用，但 m1 尚不产生正式信号；后续 m3/m4 接线仍需再次审计。

## 五、公共接口复用与简化声明

- `common.data_loader.get_data_root` 被直接复用，数据根目录没有在策略目录重复硬编码。
- `common.data_loader` 的既有 CN loader 不同时支持本案例所需的双表外连接、美国数据、逐列下推和逐键审计；m1 的专用加载封装具有报告专属必要性。
- `common.utils.winsorize` 是截面 MAD/std 工具，不支持本报告的逐股、逐更新锚点、0.5%/99.5% 历史分位参数证据；m1 的专用历史窗缩尾不是同口径重复实现。
- `common.ml_pipeline` 的预处理接口面向另一种全局特征窗；m1 尚未进入模型训练。`common.backtest` 属于后续组合/验证环节，m1 不应调用。
- 已登记简化包括 CRSP→本地美股、Wind→本地 A 股、SPY→SPX、513500.SH→沪深300、成交量→成交金额解释及全样本机械前视。未发现未登记的 core 公式简化或报告专属公开函数“私货”映射。
- `src/r007_cross_market_return_forecasting/data_pipeline.py`、`config.py`、`__init__.py` 中未发现 `pass`、`TODO`、`NotImplementedError` 空壳，覆盖矩阵列出的函数名均能定位到真实函数体。

## 六、已检查维度清单

- [x] 公式一致：F1/F2 分子分母、对数算子、t 与 t-1；F3 同口径市场扣减；21 日历史中位数。
- [x] 参数一致：2014–2021、500/市场、0.5%/99.5%、250 日、US→CN l=1、CN→US l=0、T+1。
- [x] 实现位置真实：m1 全部 15 条 `done` 行逐条定位，未发现空壳或不存在位置。
- [x] 代码反查：从 loader、选池、标准化、收益、流动性、缩尾、因果日历和执行日映射逆向核对 spec/assumptions。
- [x] 简化声明：逐项检查 AS2/AS3/AS5/AS9/AS10–AS13，未发现 `deviation_undeclared`；发现的真实数据数量阻断单列 CA-A01。

verdict: fail

---

## 七、第 2 轮修复复核

- mode: `code`
- milestone: `m1`
- 复核对象: 首轮 `CA-A01`、`plan.md` §6.1、AS19/AS24–AS26、更新后的 D1/D3/D6/D7/D8/B1 实现位置、Yahoo 固定联合池全量本地证据、m2 消费接口和依赖锁。
- 复核边界: 不访问网络，不运行正式回测；全部数量、哈希、Parquet 约束和接口结果由本轮本地独立重算，不采信 manifest、audit_summary 或实现者的完成陈述。

### 7.1 第 2 轮结论

首轮 `CA-A01` 已解决，未发现新的 critical、major 或 minor issue。

旧的 `/Users/hedi/local_data/usshare_stock_quote.parquet` 仍只有 30 个研究期代码；该首轮失败证据保留有效，但最新 plan/AS24–AS26 已明确撤销把它作为美国 B1 数据源的做法。当前实现使用固定双快照 Yahoo 联合池，真实缓存为 501 个合格证券；`build_dual_market_universes()` 本轮实跑返回美国 501 个唯一证券、A 股平均市值前 500 个唯一证券，不再触发首轮“美国少于 500 只”的异常。

第 2 轮 issue: 无。

### 7.2 固定网页、oldid 与候选池独立重算

本轮直接读取两份落盘 HTML，用独立 BeautifulSoup 解析 `table#constituents`，按页面原始顺序以 `Symbol + "\n"` 重算清单哈希：

| 项目 | 主池 | 补充池 | 结论 |
| --- | --- | --- | --- |
| 固定 oldid | `1365256480` | `1062834329` | 两份 HTML 内分别只能检出对应 oldid；URL、config、precheck_manifest 一致 |
| 页面行数/唯一 Symbol | 503/503 | 505/505 | 与 plan §6.1、AS24 一致 |
| HTML SHA256 | `bce53c14645cc6dbcd667abce5f9f7b2987e89daa167241eb1671ea4a22d33be` | `4ed0df8fd6909d15393d507f3c52bfd0fde7a75b939ced14e0b19758b11c93ac` | 独立逐字节重算一致 |
| Symbol SHA256 | `6d4f0619598357c95da15ae5115789bf2d55065f5bf1da50e4a7bbcbfafe08d1` | `d970ebb5508e556a95665731cb20d70b18b8bf2207d44f6a146a329f7a94209d` | 独立按原表顺序重算一致 |

- 直接从主池 503 个 Symbol 排除固定 41 只，得到 462 只；补充页面相对主池的差集为 90 只，其中固定通过名单为 39 只。
- plan §6.1 的 41 只排除名单与 `precheck_manifest.json` 逐项、逐序一致；plan 的 39 只补充名单与 precheck_manifest 逐项、逐序一致。
- 重新拼接 `462+39` 得 501 个候选、501 个唯一原始代码和 501 个唯一 Yahoo 代码；顺序与 `constituents.csv`、precheck_manifest union 完全相同。
- 联合池 Symbol SHA256 独立重算为 `30540e06a36f6852684ac2145adf2de464651ed56a0e4a12e0bb5f7c02a2d9c9`，与 precheck_manifest 一致。
- 实现位置真实：`download_us_data.py:134-195` 校验 HTML/Symbol 哈希和数量；`download_us_data.py:198-331` 按原表顺序构造 462+39、检查两类代码唯一性并落 precheck 证据，不是空壳。

### 7.3 501 个逐股文件全量独立复核

本轮没有使用 manifest 的 summary 代替文件审计，而是按 `constituents.csv` 顺序对 501 个候选逐文件执行 SHA256、schema、键、证券代码、日期、覆盖和审计字段重算：

- `prices/` 实际有 501 个 `.parquet`、0 个 `.part`；与 manifest 所引用的 501 个文件集合完全相同，无多余或缺失文件。
- manifest 实际有 501 个候选 entry；逐项状态为 501 `success`、0 `failed`、0 `pending`。
- 501/501 文件存在，逐文件 SHA256 全部与 entry 一致。
- 501/501 schema 顺序均严格等于 19 列 `PRICE_COLUMNS`；无缺列、增列或顺序漂移。
- 501/501 文件的 `(stock_code,date)` 唯一键无重复；文件内 `stock_code/source_symbol/yahoo_symbol` 与 constituents 映射一致。
- 501/501 文件的行数、首日、末日与 manifest entry 一致；所有日期均满足 `2014-01-01 <= date < 2022-01-01`。
- 501/501 文件有效区间 OHLCV 最低非空率的全局最小值为 1.0，高于 AS26 的 0.95；逐文件重新计算的非空率字典、缺失数字典、OHLC 逻辑异常数、return 不可用数、分红事件数和拆股事件数均与 entry 一致，差异数为 0。
- 逐文件累计得到 969,899 行、501 个证券，首日 2014-01-02、末日 2021-12-31。
- 缓存来源独立计数为 38 个 `migrated_legacy_cache`、463 个 `downloaded_yfinance_1.2.0`。对 38 个迁移项重新读取旧 manifest 和旧文件，确认旧/新请求参数一致、来源文件存在、来源 SHA、迁移后 SHA 和记录 SHA 三者一致；38 个均属于按下载时间排序的首批 42 个授权旧成功项，未发现越权复用。
- 实现位置真实：`download_us_data.py:418-439` 执行缓存哈希/回读/唯一键校验；`download_us_data.py:734-839` 执行逐股下载、`.part` 回读、原子替换和逐项 manifest；不存在 `pass`/`TODO`/`NotImplementedError` 空壳。

### 7.4 合并面板独立复核

- `/workspace/r007_cross_market_return_forecasting/data_cache/us_yahoo_union500_v1/us_panel.parquet` 的 Parquet 元数据行数和实际读取行数均为 969,899。
- 独立重算证券数 501、日期范围 2014-01-02 至 2021-12-31、重复 `(stock_code,date)` 键 0；证券集合与 501 候选集合完全一致。
- 独立逐字节 SHA256 为 `0f0cd46f8a66e1df4cb996174e4f1176b3e589f9bedac379f086960a0a953f3a`，与 manifest `merged_panel.sha256`、`audit_summary.json` 均一致。
- 逐股文件行数累计值等于合并面板行数；合并面板 OHLC 逻辑异常 2 行、return 不可用 2 行，与逐股重算和 audit_summary 一致。
- `download_us_data.py:842-891` 的合并、唯一键、`.part` 回读、原子替换、SHA 和摘要逻辑均为真实实现。

### 7.5 AS19 复权、成交金额及 HUBB/UA 异常

- 对 501 文件逐行重算 `adj_factor=adj_close/close_raw`，有限正值处全部一致。
- 对 AAPL/HUBB/UA 实际数据逐行重算四个派生字段，`open/high/low/close_adj = raw × adj_factor` 的最大绝对差均为 0；有效行 `close_adj` 与 `adj_close` 最大浮点差约 `1.42e-14`。
- `standardize_us_quotes` 输出的收益用 `open_adj/close_adj`，成交金额用原始 `close_raw×volume`；实际抽查的成交金额差为 0，未误用复权收盘价计算金额。
- 全量异常仅两行：HUBB 2021-05-05 和 UA 2021-05-05。两行原始 OHLCV 均完整保留；因 `low_raw > min(open_raw,close_raw)`，四个派生复权 OHLC 全部置空，`return_eligible=False`。原始 `close_raw×volume` 成交金额仍保留，符合“原始证据不改写、异常不进入收益”的合同。
- `download_us_data.py:467-574` 与 `data_pipeline.py:714-771` 的 AS19 双轨实现位置真实；coverage D3/D7/F1/F2 定位成立。

### 7.6 CA-A01、A 股 500 与 m2 接口

- `load_us_fixed_constituent_universe()` 本轮实际校验 501 个候选、462+39 来源计数、501 success 文件及逐文件哈希，返回 501 个唯一证券。
- `build_dual_market_universes()` 本轮实跑返回美国 501、A 股 500；A 股 `market_cap_rank` 为 1–500，`selection_uses_full_sample=True`、`mechanical_lookahead_acknowledged=True`。美国明确使用 `sp500_yahoo_union500_v1`，没有冒充历史平均市值。
- 因此首轮 CA-A01 的阻断条件已被真实新数据链解除；覆盖矩阵 D1/D6/B1 的最新 AS24–AS26 实现位置成立。
- 用真实 AAPL/HUBB/UA 与 A 股市值池前三只执行极小接口集成：m1 成功生成 `pvclcl_excess`、`opcl_excess`、`traded_amount_median_21d`；m2 成功生成 US_TO_CN、CN_TO_US 两方向 3×3 图快照。两方向训练映射均为严格早于 2016-01-04 锚点的 250 日，训练终点均为 2015-12-31。
- `graph_pipeline.py:228-324` 只要求 `stock_code/date/收益列` 和 m1 因果映射字段；`graph_pipeline.py:894-971` 能直接消费更新后的 m1 面板，未发现字段改名或类型破坏。

### 7.7 未来函数、T+1、21 日流动性与缩尾

- Yahoo 固定双快照/可查询性筛选带有 AS24/AS25 已声明的幸存者、当前成分和预检偏差；没有把它伪装成时点可得市值池，故不构成未登记简化。
- m1 因果日历仍按目标开盘前已完成的源市场收盘做 backward as-of；m2 实数小样本的两个 250 日训练窗均不含锚点当日或未来日期。
- 实际日历上 2016-01-04 的美股和 A 股信号均映射到各自 2016-01-05 的下一交易日，T+1 helper 保持严格晚于信号日。
- AAPL 实际数据在第 22 个观测日独立用前 21 行 `close_raw×volume` 计算中位数为 `7,582,754,626.931`，与实现输出逐位相等；当日成交金额未进入窗口。
- B2 参数仍为锚点前 250 个历史目标日、逐股 0.5%/99.5% 分位；`fit_end < anchor` 断言和 m2 训练映射审计均存在。未发现新数据接线绕开历史缩尾或缺失处理。

### 7.8 依赖与实现位置

- `pyproject.toml:19` 直接固定 `yfinance==1.2.0`；运行环境实测 `yfinance=1.2.0`、`beautifulsoup4=4.15.0`。
- `uv.lock:2806-2828` 锁定 yfinance 1.2.0 及其 wheel/sdist 哈希；BeautifulSoup 依赖也已进入锁文件。
- `uv lock --check --offline` 成功，离线解析 95 个包；未修改 lock，未发现依赖声明与锁文件不一致。
- `config.py:65-146` 集中声明两份 oldid、网页/Symbol 哈希、501/500/1 数量门槛、请求参数和缓存路径；`__init__.py` 导出 `USYahooConfig`，接口真实。
- coverage_matrix 的 m1 15 条 `done` 行已按最新文件重新逐条反查。旧路径已经在 D1/D3/D6/D7/D8/B1 的状态理由和实现位置中更新；其余 F1–F3/B2–B4 公式与首轮审计结论未被修复破坏。

### 7.9 第 2 轮已检查维度清单

- [x] 公式一致：AS19 复权因子/派生 OHLC、F1/F2、F3、原始成交金额、21 日历史中位数。
- [x] 参数一致：双 oldid/哈希、462+39=501、至少500成功/最多1失败、请求参数、250 日、0.5%/99.5%、T+1。
- [x] 实现位置真实：最新 m1 全部 15 条 `done` 行、下载器、固定池、合并面板及 m2 消费接口均反查到非空函数体。
- [x] 代码反查：逐网页、逐候选、逐 manifest entry、逐 501 Parquet、合并面板、双市场股票池和双方向 m2 小样本均独立执行或重算。
- [x] 简化声明：AS19/AS24–AS26 与 coverage 状态理由完整披露 Yahoo、固定快照、幸存者/可查询性、美国非市值池和双市场不对称；未发现 `deviation_undeclared`。

verdict: pass
