# iter_01 合并改动记录

## 范围与详细记录

- 锁定修改点一（数据、严格 PIT、风格、组合及中国市场证券生命周期）：见 `changes_data.md`。
- 锁定修改点二（正式证据、reporting、工作簿最终化及扰动合同）：见 `changes_reporting.md`。
- 未修改 spec、plan、coverage matrix、state 或正式 results；本轮 coder 均未运行正式 `main.py`。

## 合并改动文件

- 数据与组合：`src/r004_all_a_style_box/config.py`、`data_pipeline.py`、`strategy.py`、`portfolio.py`。
- 正式输出与重建入口：`src/r004_all_a_style_box/reporting.py`、`main.py`、`workbook_builder.mjs`。
- 测试：`tests/test_r004_all_a_style_box_data.py`、`test_r004_all_a_style_box_portfolio.py`、`test_r004_all_a_style_box_reporting.py`。
- 迭代明细：`workspace/r004_all_a_style_box/iterations/iter_01/changes_data.md`、`changes_reporting.md`、本文件。

## 合并结果摘要

- Value 改为 B/P、严格 PIT TTM E/P、严格 PIT TTM S/P 三核心至少2项，股息率仅为不超过5个交易日的可选项；保留完整来源与公式。
- 正式 OOS 33个月从 `NAV=1` 全现金开始；Size/Value/Growth 与四箱不变，33/33月 Style 覆盖不低于97%，PIT未来披露为0。
- 组合区分目标参考、实际成本前、实际成本后三层收益；证券风险退出只在真实可卖日按可重算VWAP成交，主动退市与换股按有正式来源的公司行动结算。
- 最终全量生命周期 blocker 为0，超过20交易日无事件残仓为0；现金选择权、换股比例、后继代码与真实退出均进入 `security_event_audit`。
- reporting 正式证据扩为12张全量明细表；工作簿只能在 verifier 给出绑定当前 Assumptions 与7项PASS检查的正式上下文后重建为 `verified/PASS`；hard扰动必须在独立目录运行且不得改变正式目录。

## 合并自检

- 数据/组合完整测试：`4 passed in 142.11s`，exit 0。
- reporting 有界测试：`5 passed in 28.58s`，exit 0（详细命令与范围见 `changes_reporting.md`）。
- `python -m compileall -q src/r004_all_a_style_box`：exit 0。
- 上述均为 coder 自检，不构成 verifier 的正式验证结论。

## 正式验证前置要求

1. assumptions 授权维护者须先登记 `changes_data.md` 中列出的三类主动简化：全额行使合资格现金选择权、账户特定税费未模拟、换股零碎股按连续份额近似。
2. verifier 必须使用修改后的代码重新运行正式 `main.py`，重建输出 Excel、PNG、12张明细 Parquet、metrics/comparison、run log、verify report、evidence manifest 与 hard 扰动证据。
3. 正式验证必须比较新生成文件，不得复用或引用 iter_01 修改前的工作簿、图表、指标或哈希；只有 verifier/check_gates 拥有最终裁判权。

## code audit 最小修复（IA-01--IA-05）

### 允许范围内改动文件

- `src/r004_all_a_style_box/portfolio.py`
- `src/r004_all_a_style_box/reporting.py`
- `tests/test_r004_all_a_style_box_portfolio.py`
- `tests/test_r004_all_a_style_box_reporting.py`
- `workspace/r004_all_a_style_box/iterations/iter_01/changes.md`

`main.py` 未修改；未修改 assumptions/spec/plan/state 或正式 `output/`，未运行正式 `main.py`。

### 审计问题逐项修复

- IA-01：公告风险退出不再覆盖交易所方向限制；只有同日 `daily_can_sell=True` 且真实 VWAP/成交量有效时才退出。跌停、停牌或无成交日保留仓位并写 `risk_exit_waiting_daily_can_sell`，解除限制后的首个真实可卖日按当日 VWAP、佣金、滑点和印花税成交。
- IA-02：连续两次零目标检查改为从全部持仓向量筛选，不再依赖“当日缺 close”子集；只有明确停牌、待结算公司行动或已公告且仍等待真实可卖日的退出事件可解释残仓。普通零目标残仓恢复可卖时，按首个同日真实 VWAP 强制退出并写入 trades/costs/security_event_audit；超过20交易日缺价且无理由的残仓仍阻断。600466 等已公告但始终不可卖证券不按零、不伪造 VWAP，继续用陈旧已观察价格估值并保留等待/缺价审计行。
- IA-03：`validate_pit_style_inputs()` 不再信任交付表的 rank/score；从财务三段、财政期键和披露日独立重建 TTM 与公式，再重算 Growth、B/P/E/P/S/P、股息新鲜度、1%/99% 缩尾、百分位秩、有效分量数、Value/Growth/Style、Size 及四箱标签。任一层 NaN 模式或数值不一致均失败。
- IA-04：最终化前严格要求假设登记精确且唯一覆盖 AS1--AS24，12个必需字段逐行非空，`验证后回看` 不含 `verify 后填`、pending、待填等占位；合格后才核对 verifier context 的整表 SHA。pending payload 生成路径未增加该最终化门禁。
- IA-05：目标参考收益统一定义为“月度目标组合参考收益可用；日频目标参考收益不可用”；`build_return_series()` 强制月频逐行 available、日频逐行 NaN/unavailable，并输出频率合同字段，禁止用实际成本前收益代替日频目标层。

### 新增故障注入与自检

- 风险退出：跌停但有成交量仍不得卖；解除跌停的首个 `daily_can_sell=True` 日才按真实 VWAP 和成本退出。
- 残仓：正常 close 的两次零目标残仓也会被全部持仓扫描捕获；停牌/待结算事件不误报；恢复可卖后首日真实退出；缺价超过20日且无理由仍判为阻断。
- PIT：分别篡改 raw ratio、TTM 原始腿、winsorised、rank、score、style_box 均被拒绝；未篡改 fixture 的全部数值层最大误差 `<=1e-12`。
- 假设最终化：缺 ID、重复 ID、必需字段为空、任一占位回看四类输入均被拒绝；只有完整 AS1--AS24 可最终化。
- 收益语义：月频 availability 与 `monthly_available`、日频 unavailability 与 `daily_unavailable` 逐行一致，公开语义文本同时明确两种频率。
- 新增故障注入小集：`13 passed, 2 deselected in 13.13s`。
- 完整定向套件：`26 passed in 213.45s`，命令为 `uv run python -m pytest -q tests/test_r004_all_a_style_box_data.py tests/test_r004_all_a_style_box_portfolio.py tests/test_r004_all_a_style_box_reporting.py tests/test_r004_workbook_freeze.py`。
- `uv run python -m compileall -q src/r004_all_a_style_box tests/test_r004_all_a_style_box_portfolio.py tests/test_r004_all_a_style_box_reporting.py`：exit 0。
- `node --check src/r004_all_a_style_box/workbook_builder.mjs`：exit 0。

以上仅为 coder 冒烟与定向自检，不构成 verifier 的正式验证结论。

## verifier 首次正式运行错误修复（目标参考收益）

### 失败与根因

- 只读检查 `output/r004_all_a_style_box/results/run_log.md`：verifier 正式命令 exit=1，首先在 `build_return_series()` 的频率合同阻断；2023-05-04、2023-06-01 的多个月频实体 `target_reference_return=NaN`。
- 根因不是首期缺前值，也不是月频日期 merge 错位。旧实现用目标权重乘 m1 的逐股 `gross_holding_return`，但只要目标组合中任一证券 T+1 执行 VWAP 或月末收益 VWAP 无效，就把整个组合参考收益置 NaN。真实数据中，2023-04目标的 ALL_A 有42只缺完整双端点，2023-05有30只；错误日志只展示 mismatch 前10行。
- 目标参考合同被修复后，真实回归继续暴露同月调仓成本和事件退出成本形成重复 `(holding_month, portfolio)` 键；旧 reporting 直接 set_index 无法勾稽。该问题一并按运行错误最小修复。

### 修复内容

- `portfolio.py` 新增独立月度目标参考估值链，仅消费冻结目标权重、T+1价格、截至月末历史可见价格与显式公司行动，不读取 actual shares、actual gross 或实际组合净值。
- T+1有效执行 VWAP 才建立目标参考成分；无法形成真实起始价格的目标额度保留为目标参考现金、收益为0，不伪造价格。
- 月末优先使用同日有效 `return_vwap`；缺失时只使用截至月末最后一个已观察的前复权 close，且来源日不得早于T+1。整月没有更新价格时沿用已知T+1 VWAP作陈旧估值，禁止未来价格、零价和后值回填。
- 区间内公告已知且已生效、参数完整的现金/换股事件按登记的每股现金或换股比例乘截至月末后继证券历史价格结算。公告或风险标签本身不当成交价；无真实可卖/结算价格时继续历史估值。
- 目标参考逐股估值来源登记为 `return_vwap`、`historical_close_at_or_before_end`、`execution_vwap_carry`、`cash_unexecuted_at_t_plus_1` 或显式公司行动；组合层保留现金起始、陈旧估值、公司行动和未闭环计数，未闭环必须为0。
- `reporting.py` 仍严格要求月频目标参考有限且 available、日频 NaN 且 unavailable；没有放宽标志，也没有用 actual gross 填充目标层。
- 月度成本勾稽先按 `(holding_month, portfolio)` 汇总调仓与事件驱动成本，再按组合累计，确保索引唯一。

### 回归与自检

- 新增真实33个月回归中的前两月断言：2023-05-04、2023-06-01各9个实体，共18行月频目标参考全部有限且 `target_reference_available=True`；对应2023-04、2023-05的全部日频行保持 NaN/`target_reference_available=False`。
- 首两月真实回归：`1 passed, 3 deselected in 164.73s`。
- 重复月内事件成本勾稽单测：`1 passed, 14 deselected in 1.32s`。
- 完整定向套件：`26 passed in 245.15s`，命令为 `uv run python -m pytest -q tests/test_r004_all_a_style_box_data.py tests/test_r004_all_a_style_box_portfolio.py tests/test_r004_all_a_style_box_reporting.py tests/test_r004_workbook_freeze.py`。
- `uv run python -m compileall -q src/r004_all_a_style_box tests/test_r004_all_a_style_box_portfolio.py tests/test_r004_all_a_style_box_reporting.py`：exit 0。
- 未运行正式 `main.py`，未修改 `state.json`、assumptions/spec/plan 或正式 output；没有新增需补登 AS12 的参数或主动简化。

以上仅为正式运行错误后的 coder 修复与自检，正式重跑及验证结论仍归 verifier。

## verifier attempt=4 运行错误修复（turnover/cost月度重复键）

### 失败与根因

- 只读检查最新 `output/r004_all_a_style_box/results/run_log.md`：attempt=4 exit=1，`_build_entity_audit()` 直接以 `date/signal_date/holding_month/sample_phase/portfolio` 对 turnover 与 costs 做一对一合并。
- 同一组合月内既有常规调仓又有事件驱动退出时，两张表都会出现多行；例如2024-05-08的2024-05月 SV、ALL_A、STYLE_1N。原始明细合理，但未先压成月度唯一执行审计键，导致两侧都违反 one-to-one。

### 修复内容

- turnover 先按唯一月度信号执行键 `(signal_date, holding_month, sample_phase, portfolio)` 聚合：买入额、卖出额、总交易额求和，并记录月内记录数及首末交易日期。
- costs 按同一键聚合 commission、slippage、stamp tax、total cost，并记录月内记录数及首末成本日期；调仓与事件成本均保留，不丢失、不重复。
- coverage 仍必须在该月度信号执行键上天然唯一；`coverage.date` 定义为该持有月唯一月初执行日。
- turnover 与成本的唯一 NAV 分母取 `monthly_portfolio.start_net_nav`，其唯一键为 `(holding_month, sample_phase, portfolio)`；`monthly_portfolio.start_date` 必须等于 `coverage.date`。月度双边换手重算为“月内全部交易额 / 单一月初NAV”，单边换手再除2；成本率重算为“月内全部成本 / 同一月初NAV”，不对事件行重复使用NAV分母。
- 聚合后的 turnover、costs、coverage、monthly NAV 仍全部使用 `validate=one_to_one`；没有放宽为 many-to-many。
- 全面 `rg` 审核 r004 中所有 turnover/costs 的 one-to-one merge 与 set_index：`build_return_series()` 的月度成本 set_index 已在上次修复前先按 `(holding_month, portfolio)` 汇总；其余相关点仅导出原始明细或消费 `_build_entity_audit()`。portfolio 内其他 one-to-one/set_index 均为证券、目标或因子键，与月内事件重复无关。

### 故障注入与真实路径

- 新增同一月常规调仓+事件退出的 turnover/costs 双行故障注入：聚合后仅1行；总交易额、commission、slippage、stamp tax、total cost与原始明细求和误差均 `<=1e-12`；双边/单边换手和成本率只使用一次月初NAV；唯一执行日、月内首末事件日与记录数均可核对。
- 最小测试：`2 passed, 14 deselected in 1.83s`。
- 真实33个月路径已执行至 `build_return_series → _build_entity_audit → calculate_performance_summary`：return series 6318行、entity audit 297行（9实体×33月）、performance summary 18行，月度 `(holding_month, entity)` 无重复。
- 真实长组合原始成本合计 `0.04819537928934914`，entity audit聚合成本同为 `0.04819537928934914`，误差 `0.0`。
- 完整定向套件：`27 passed in 216.24s`，命令为 `uv run python -m pytest -q tests/test_r004_all_a_style_box_data.py tests/test_r004_all_a_style_box_portfolio.py tests/test_r004_all_a_style_box_reporting.py tests/test_r004_workbook_freeze.py`。
- `uv run python -m compileall -q src/r004_all_a_style_box tests/test_r004_all_a_style_box_reporting.py`：exit 0；`git diff --check`：exit 0。
- 未运行正式 `main.py`，未修改 output/state/assumptions/spec/plan，也未新增假设或参数。

以上仅为 attempt=4 运行错误后的 coder 修复与自检，attempt=5 正式重跑及验证结论仍归 verifier。

## verifier attempt=5 前置错误修复（nullable PIT 布尔条件）

### 失败与根因

- attempt=5 preflight 在 `validate_pit_style_inputs()` 内退出，错误为 `np.select` 的 `condlist` 含 pandas nullable Boolean/`pd.NA`，NumPy 不接受非原生 `bool` 条件数组。
- 问题不只存在于最终四箱标签分支；年度/TTM、Growth、正值约束、股息新鲜度、缩尾/排名有效性、Value/Growth 分量数、Style 有效性与大小盘标签等条件均可能随 `Float64`、`boolean`、`string` 扩展类型传播缺失布尔值。

### 修复内容

- `reporting.py` 的 PIT 验证器统一先用 `pd.to_numeric(errors="coerce")` 规范数值输入；所有用于 `np.where`、`np.select`、行筛选和有效性判定的 nullable 条件都执行 `astype("boolean").fillna(False)`，传入 NumPy 前再显式转为原生 `bool` 数组。
- 缺失值的合同统一为“不有效”，不能因 pandas 扩展类型而被误计入 annual/TTM 腿、Growth 腿、正值比率、股息新鲜、有效分量数、Style 分数或四箱标签。
- 重算链仍独立核对 TTM、Growth、B/P、E/P、S/P、股息、缩尾、百分位秩、Value/Growth 分量数、Style 有效性、Size 与四箱标签；未放宽任何误差阈值或 PIT 未来披露门禁。

### 故障注入、真实路径与自检

- 新增 `Float64` 数值列、pandas `boolean` 条件列、`string` 标签列与 `pd.NA` 故障注入：干净数据通过；缺失条件明确判为无效；缺失行不产生 Style Box；随后篡改原始 `book_to_price` 仍被验证器拒绝。
- reporting 小集：`8 passed, 9 deselected in 2.54s`。
- 真实33个月内存链路执行 `m1 → m2 → m3 → m4 → _collect_detail_tables → validate_pit_style_inputs`：PIT 明细165,138行、逐行证据表12张、`future_disclosure_count=0`、全部 `*_max_abs_error` 最大值 `0.0`。
- 完整定向套件：`28 passed in 217.75s`，命令为 `uv run python -m pytest -q tests/test_r004_all_a_style_box_data.py tests/test_r004_all_a_style_box_portfolio.py tests/test_r004_all_a_style_box_reporting.py tests/test_r004_workbook_freeze.py`。
- `uv run python -m compileall -q src/r004_all_a_style_box tests/test_r004_all_a_style_box_reporting.py`：exit 0；`git diff --check`：exit 0。
- 未运行正式 `main.py`，未修改正式 output/state/assumptions/spec/plan，也未新增假设或参数。上述仅为 coder 自检，attempt=5 正式重跑及验证结论仍归 verifier。

## verifier attempt=5 preflight2错误修复（artifact-tool工作簿OOM）

### 失败、实测规模与根因

- attempt=5 preflight2 已成功生成数据、12张全量Parquet和8张PNG，但单一Node进程在第4本工作簿QA阶段达到约4,079--4,086MB V8 heap并OOM；正式output未触碰。
- 失败目录的 `workbook_payload.pending.json` 为94MB pretty JSON，46个用户sheet共168,991行。PIT 165,138行和security event 42,424行全量没有直接进入Node，仍只保存在Parquet并由DetailManifest/Sources登记路径、行数、列清单和hash。
- Node紧凑序列化的原始五分片合计49,304,539B；主要负担是按月/组合冻结Top-N视图：IC 19,200行、三张持仓各19,800行、箱成员13,200行、Trades 39,600行、Unfilled 29,129行。未把这些行缩成全样本100/200行。
- 根因有三层：旧Node进程连续持有五本artifact workbook；工作簿级 `kind=formula` inspect会在artifact内部对整本先JSON stringify，`maxChars`和sheet/range分块不能降低峰值；每个明细行还重复附加四列DetailManifest元数据，且Trades/Unfilled把只需在Parquet保留的全部宽列送入工作簿。单工作簿进程隔离解决跨书累积，但第4/5本的单书宽表仍会在inspect/export时触发4GB heap上限。

### 修复内容

- `main.py` 把五本工作簿拆成五个顺序Node worker，每个worker只接收一本、完成后退出并释放；Python增量合并五份真实QA manifest，再执行统一二次门禁。未设置或提高 `NODE_OPTIONS`/heap。
- manifest新增每个worker的输入字节、用户sheet/行数、maxRSS、结束时heap/external内存，以及总payload、最大单片、5 worker隔离、51 sheet预期和8GiB RSS硬上限；任一worker缺内存记录、顺序不符、不是单工作簿进程或超过硬上限均失败。
- `reporting.py` 不再把 `detail_full_row_count/detail_displayed_row_count/detail_parquet_path/detail_view_rule` 四项逐行复制到Top-N工作表；这些全量语义继续完整保存在DetailManifest/Sources。兼容旧pending payload的Python入口会在送Node前移除同样四列。
- 按月/组合Top-N行数保持不变。Trades 39,600行冻结展示13个审计核心列：`date/signal_date/holding_month/portfolio/stock_code/side/shares/vwap/gross_notional/commission_cost/slippage_cost/stamp_tax/total_cost`；Unfilled 29,129行冻结展示12列：`date/signal_date/holding_month/portfolio/stock_code/side/requested_shares/filled_shares/unfilled_shares/reference_price/unfilled_notional/reason`。完整宽列仍在Parquet和DetailManifest列清单中，工作簿明确不是全量逐行证据。
- 公式门禁改为导出前对实际送入artifact的Cover、全部表格与原生chart源网格按500行分块逐cell扫描，禁止未授权 `=` 公式表达式并扫描错误token；manifest登记method、chunk、覆盖行数/单元格数。导出后再解包全部worksheet OOXML，全扫公式单元格与错误单元格，形成前后双门禁。51个sheet仍逐一实际调用artifact-tool table inspect和render。
- 写入artifact后立即释放输入sheet rows/chart rows引用，`tableInfo`不再重复持有转换后的全行数组；五本、51 sheet、A2冻结、inspect/render、原生图表和verified最终化重建合同均未减少。

### 真实pending复跑与内存证据

- 同一attempt5失败pending最终内存复跑exit=0：5/5工作簿、51/51 sheet、51/51 inspect、51/51 render、51/51 A2，5个必要原生chart全部存在。
- 旧pending原始五分片49,304,539B；Node实际五分片33,394,868B，最大单片13,738,282B；共移除862,414个逐行重复/非工作簿核心单元格，但Top-N总行数168,991不变。
- 公式源网格共442块，扫描169,265行、2,104,140个单元格，公式表达式0、错误token 0；导出OOXML公式单元格0、错误token 0。
- 五worker maxRSS依次为1,277,362,176、2,255,831,040、2,269,380,608、5,845,860,352、5,598,625,792B，均低于8GiB硬上限；结束时heap used依次约0.076、0.969、0.755、3.129、3.301GB。相较旧单进程第4本约4.08GB heap fatal，最重worker成功完成并退出释放。

### 故障注入与自检

- 新增1200期大规模synthetic实际artifact-tool测试：保持5本、51 sheet、逐sheet inspect/render/A2、公式双扫与单worker RSS硬边界，不以mock或跳过artifact-tool伪造成功。
- 新增旧pending精简测试：Top-N行数不变、Trades/Unfilled核心列精确冻结、DetailManifest/Sources逐项不变，并核对移除单元格计数。
- reporting/workbook完整定向测试：`23 passed in 285.99s`，覆盖pending分片构建与verified/PASS最终化后的再次分片重建。
- 未运行正式 `main.py`，未写正式output/state/assumptions/spec/plan，未修改策略参数或新增主动简化；正式attempt5重跑与验证结论仍归verifier。
