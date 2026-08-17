# r004 m4 实现记录

## 派发范围

- milestone: `m4` OOS报告与可追溯证据
- elements: `R4`、`R7`、`R10`、`SA4`
- reproduction_mode: `experimental`
- 正式OOS: 2023-04至2025-12；方法冻结截止2023-03-31

## 实现文件

| 文件 | 实现摘要 |
| --- | --- |
| `src/r004_all_a_style_box/reporting.py` | formal_oos切片后的日/月收益与归一净值、绩效、R4相关矩阵、R7胜出频率、Size/Style IC与五分位/衰减、换手成本覆盖率、SA4双基准、8张PNG和五工作簿payload |
| `src/r004_all_a_style_box/main.py` | m1→m2→m3完整有状态回测、formal_oos选择、metrics/comparison/run_log、临时目录artifact-tool执行入口；不生成verify_report |
| `src/r004_all_a_style_box/workbook_builder.mjs` | 唯一xlsx作者；`@oai/artifact-tool`版本门槛、五工作簿、原生图表、inspect/公式扫描/逐sheet render与QA manifest |
| `src/r004_all_a_style_box/__init__.py` | 仅装配m4公开数据入口 |
| `workspace/r004_all_a_style_box/spec/coverage_matrix.md` | R4/R7/R10/SA4实现位置与done状态 |

## 透明统计口径

- IC结果标签为T日冻结信号对应T+1 VWAP起始的个股持有期毛收益；只用于结果诊断，不进入策略、成本或分组。
- 衰减为从同一T日信号起算的1/2/3月连续持有期毛收益复合IC；只有完整端点仍在formal_oos时才纳入。
- 四箱月度净收益精确并列最高时等分一个月胜场，胜出频率合计仍为100%。
- SMB/HML/GML没有独立成交簿；因子净毛收益由四箱逐期合成，换手、成本和覆盖率表明确标为四腿简单均值，不冒充独立成交组合。
- 美国R4/R7/R10原值仅在reference/background字段展示，`comparison.json`不计算偏差、不写pass，验证状态固定为`pending_verifier`。

## 冒烟证据（非正式结果）

- Python合成fixture：`/tmp/r004_m4_smoke/synthetic_smoke.py`，覆盖33个formal_oos月；成功生成18行频率/实体绩效、49个相关单元格、66行1个月IC序列、6行1/2/3月衰减及五工作簿合同。
- artifact-tool版本：2.8.24（最低要求2.8.6）。
- 微型工作簿：`/tmp/r004_m4_smoke/output/backtest_summary_smoke.xlsx`；仅为构建器冒烟，不是正式结果。
- QA清单：`/tmp/r004_m4_smoke/qa_manifest.json`；Cover/Summary/Assumptions/Checks/Sources均完成inspect和render，公式错误扫描为空，原生图表源为Summary!A6:B8。
- OOXML压缩包检查：`unzip -t`无错误；视觉预览中文、日期、百分比和原生图表正常。
- artifact-tool 2.8.24的inspect选择器已使用其支持的工作表名称；QA manifest显式记录`warning_count`/`warnings`，Python调用层另行记录成功进程的warning摘要，不静默丢弃。

本阶段未运行真实全期数据、未写`output/r004_all_a_style_box/results/`、未生成或伪造`verify_report.md`，也不声明任何验证通过结论。

## m4 定向审计修复

- IC样本已改为逐因子独立过滤：Size使用m1合格池中`size_signal`与对应未来收益均有限的股票，不再要求`is_style_valid`；Style单独要求`is_style_valid`及有限`style_score`。`ic_series`逐因子逐期新增`sample_count`。
- 反例回归中5只股票均有Size、仅3只有效Style：Size样本数5、Style样本数3；正确Size Pearson IC为`-0.7803989726`，错误套用Style过滤会得到`1.0000000000`，证明Style缺失不再污染Size样本或结果。
- 33月合成合同中，每个1个月截面的Size样本为12、Style样本为9，m4完整合同仍生成18组日/月绩效、49个相关矩阵单元、66行IC及6行1/2/3月衰减。
- matplotlib在导入`pyplot`和`seaborn`前固定为无GUI `Agg`后端；`style_box_heatmap.png`的seaborn参数已由错误的`axis=axis`改为`ax=axis`。
- `/tmp/r004_m4_smoke/charts/`已生成并成功读取8张PNG：`ic_series.png` 142401字节、修复后的`ic_distribution.png` 136947字节、`group_cumulative_returns.png` 318027字节、`group_returns_bar.png` 123329字节、`net_value_comparison.png` 291819字节、`style_box_heatmap.png` 101784字节、`factor_cumulative_returns.png` 186485字节、`turnover_cost.png` 161105字节。
- 五工作簿有界QA位于`/tmp/r004_m4_smoke/five_xlsx/`：五个xlsx均完成关键sheet inspect、逐工作簿公式错误扫描及Cover+代表布局render；本轮文件大小依次为7024、7011、7054、4765、4846字节，五个OOXML均通过`unzip -t`；Node manifest为`warning_count=0`、`warnings=[]`。

## CA-A01 / CA-A02 审计问题修复

- CA-A01：R7的`winner_boxes`、`winner_count`和`fractional_credit_per_winner`在`wide.reset_index()`后均改为按位置赋值，消除`holding_month`索引与RangeIndex对齐导致的空标签。
- R7边界回归共3例：单赢家`BV`得1分、双并列`BV,BG`各得0.5分、四并列`BV,BG,SV,SG`各得0.25分；聚合胜场分别为1.75、0.75、0.25、0.25，胜出频率合计1.0，空标签0。
- 33个月合成formal_oos合同逐月独立由四箱净收益重算：33/33个月标签非空，赢家标签不一致0、赢家数不一致0、并列分值不一致0，胜出频率合计1.0。
- CA-A02：`workbook.inspect()`改用artifact-tool 2.8.24实测支持的`sheetId: sheet.name`；Node层将console warning写入QA manifest，Python层将成功子进程stdout/stderr中的warning摘要回写同一manifest。
- Python调用封装的五工作簿临时QA位于`/tmp/r004_m4_smoke/wrapper_xlsx/`：Node warning数0、Python捕获warning数0、工作簿数5。

## 正式FAIL与CDX-C-02/03/04一次性修复

- 正式FAIL根因`workbooks.json`全量逐行展开导致Node `RangeError: Invalid string length`已改为两层输出：`results/detail_tables/`保存10类全量Parquet（持仓、目标权重、实际权重、风格箱成员、成交、未成交、换手、成本、覆盖率、IC原始观测），`detail_manifest.json`逐表记录列、全量/展示行数、相对路径、字节数和SHA-256；工作簿只保留确定性Top-N视图且不冒充全量。
- Top-N参数集中在`ReportingSpecification`：持仓/目标权重/实际权重按每持有月每组合Top100，风格箱成员按每信号日每箱Top100，成交/未成交按每持有月每组合绝对名义金额Top200，IC原始观测按每期限/月份/因子绝对因子值Top100。所有视图用业务排序键、stock/side及全行稳定hash破同分；每个工作簿均含`DetailManifest`，视图表重复全量行数、展示行数和Parquet路径并指向完整规则。
- 10类Parquet大载荷回归位于`/tmp/r004_m4_smoke/large_detail_a/`：全量210510行、压缩后合计1025958字节，逐表重读行数/列均一致；打乱全部输入行后，各Parquet SHA-256与工作簿payload逐字节一致。全量/展示行数依次为：holdings 29700/19800、target_weights 29700/19800、actual_weights 29700/19800、box_membership 19800/13200、trades 49500/39600、unfilled_orders 49500/39600、turnover/costs/coverage各198/198、ic_observations 2016/2016。
- 同一大载荷的有界工作簿payload为27158478字节，占128MB硬上限约20%；另以2059字节payload配1024字节测试上限，确认在Node启动前明确失败且错误要求检查Top-N，不允许提高内存。
- CDX-C-02：Node端warning、空inspect、空preview、公式错误、OOXML CRC/必需关系、sheet计数或chart part不完整均抛错并非零退出；Python端读取manifest后二次断言Node/Python warning为0、每本sheet/inspect/preview计数相等、预览文件非空、公式/OOXML/chart闭环。临时注入`QA_WARNING_INJECTION`后在初始化即`exit=1`，未生成成功manifest。
- 完整33月五工作簿QA位于`/tmp/r004_m4_smoke/full_33m_five/`：payload 1255352字节/134217728字节上限；5本共51张sheet，51/51 inspect非空、51/51 preview非空、5/5公式扫描无错误、5/5 OOXML CRC与sheet/chart计数闭环，Node warning=0、Python wrapper warning=0；五本大小为23139、169497、118161、51761、43496字节。
- CDX-C-03：几何年化收益、年化波动、最大回撤、胜率改调`common.utils`，最大回撤由common正数转回报告负号；Pearson IC、RankIC及五分组Spearman改调`common.backtest`。R10 Sharpe仍按冻结的CAGR/年化波动口径，因与common算术均值Sharpe不等价而保留并在docstring说明。33月非退化序列的6项common值对独立正确基线最大绝对差为`4.5102810375396984e-17`，低于集中参数容差`1e-12`；该结果不再表述为对旧src缺陷口径的逐值等价。
- MDD迁移反例确认旧src只从首个期末净值起算，负首月时会遗漏“调仓前期初财富1.0→首期净值”的回撤；现保留common的标准正确口径，显式把期初净值1.0作为首个峰值。这是指标bug修复，不是参数修改。`run_common_statistics_regression_checks()`新增负首期、首个峰值后下跌和空序列3例，以显式prepend 1.0的独立财富序列为基线；负首期合成反例从旧值0修正为-0.1，3例与common误差为0。内部正式结果审计所见GML最大回撤绝对影响为`0.001123`，属于该缺陷修正的真实数值影响。
- `ReportingSpecification.performance_initial_nav`固定为1.0；`_series_metrics` docstring、绩效表`max_drawdown_audit_definition`及`metrics.json.audit_definition.max_drawdown`均透明写明“最大回撤包含调仓前期初净值1.0，负首期不能遗漏”。
- CDX-C-04：`ic_distribution.png`改为对同一RankIC样本绘制`density=True`直方图并叠加同样本均值/样本标准差的正态密度曲线；样本不足或标准差不大于集中容差时在图内明确标注不可拟合。
- 本轮只在`/tmp`执行合成/构建器冒烟；未重跑或覆盖`output/r004_all_a_style_box/results/`中verifier保留的正式FAIL证据，不声明正式验证结论。

## CDX-C-05 chart声明门禁修复

- `workbook_builder.mjs`现将sheet中存在`chart`字段视为required chart声明；声明为空对象、columns少于类别+数值两列、rows为空、行宽与columns不一致、类别为空或不存在有限数值列时，均在建图前抛错并非零退出，不再由`addTraceableChart()`静默返回null。
- `expected_chart_count`只来自声明chart的sheet数，不再来自成功创建的chart记录；每本manifest同时记录`declared_chart_count`、`expected_chart_count`、`actual_chart_count`和逐sheet的`declared_charts`。Node逐声明核对`source_sheet`、`source_rows`、title，并要求声明数、实际记录数与OOXML chart part数一致。
- `main.py`二次门禁独立断言declared=expected=actual=`len(charts)`=OOXML expected/actual；逐声明再次匹配`source_sheet`、`source_rows`和title，任一不一致均拒绝返回工作簿路径。
- 三个最小失败探针均为`exit=1`：空columns报“类别/数值列不足”，空rows报“源行数为0”，只有类别无数值报“类别/数值列不足”。探针文件与输出位于`/tmp/r004_m4_smoke/chart_probe_*`。
- 正常完整fixture位于`/tmp/r004_m4_smoke/full_33m_five_c05/`：payload 1255352字节；5本、51张sheet、51次非空inspect、51张非空preview、5次公式扫描和5次OOXML检查均闭环，Node/Python warning均为0；chart计数为declared=expected=actual=manifest=OOXML=`5`。
- 本次仍未触碰或覆盖正式`results`失败证据，不给出verifier结论。
