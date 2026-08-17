# result_audit 定向复审（round 2）

- 日期：2026-07-18
- 复审输入：`audit/result_fix_round2.md`、当前共享树实现及只读既有结果
- 权限边界：只读复审；未修改代码、正式 `results/` 或 `state.json`
- 判定边界：仅逐项给出 RA-A02、RA-A01、CDX-R-01 verdict，不判全局门禁

## 逐项结论

| 修复项 | verdict | 独立复审结论 |
| --- | --- | --- |
| RA-A02 | pass | 真实中国全市场单月中，内存审计表与临时Excel默认回读表的v2哈希完全一致；规范化不进入组合计算且未丢失关键审计信息 |
| RA-A01 | pass | 198个散点完整、33个月均为六因子且唯一赢家，临时绘图未丢点 |
| CDX-R-01 | pass | AS41、组合实现和既有结果仍保持中证800免成本基准口径 |

## RA-A02：execution_exit_audit v2 可复算哈希

### 静态链路

- v2常量把审计数值精度固定为12位小数，并明确日期、布尔、空值及数值字段范围（`reporting.py:49-69`）。
- `_canonical_audit_frame` 逐列执行以下稳定化：日期统一为 `YYYY-MM-DD`，布尔兼容 `True/False` 与 `1/0` 后统一为小写，数值round 12并固定输出12位小数，空值统一为 `<NA>`，纯数字股票代码左补零为六位（`reporting.py:838-879`）。哈希直接绑定当前表头列序与当前行序（`reporting.py:882-886`）。
- `_build_execution_exit_audit` 首先对输入成分表 `.copy()`，只在审计副本上增加字段、裁剪OOS区间及round 12；返回表固定为26列并按 `prediction_date,factor,stock_code` 排序（`reporting.py:889-977`）。该步骤不回写m1成分表。
- summary同时交付 `version=execution_exit_audit_v2`、`numeric_decimal_places=12`、日期/布尔/空值/股票代码格式、行序和列序（`reporting.py:982-995`），满足外部复算口径披露要求。
- m4组合对象在调用 `write_result_package` 前已经形成；m5仅把 `dataset.factor_constituents` 作为额外参数传入（`main.py:192-205`）。`write_result_package` 先构造审计副本，再把既有 `portfolio` 交给指标和工作簿输出（`reporting.py:1433-1474`）。round 12没有进入模型、因子收益、组合权重或组合收益计算。
- `returns_detail.xlsx` 的前三个原有sheet仍直接来自既有 `portfolio`，审计表仅作为第四个独立sheet追加（`reporting.py:1156-1163`）。

### 真实中国全市场单月独立复算

独立取中国数据日历 `2025-09-30` 信号月，`smoke_stock_limit=None` 构造全市场m1成分及2025-10执行/退出审计，再通过当前 `_write_detail_workbooks` 写入临时目录，随后使用不指定任何dtype参数的常规 `pd.read_excel(..., sheet_name="execution_exit_audit")` 回读：

- 内存审计：4,726行、26列；临时Excel：4,727行（含表头），且存在 `execution_exit_audit` sheet。
- 内存/summary SHA-256：`93563cd6e6301b32f2c1e828e299832db664ed484fd54b8fcf7233ec2d8d7e3c`。
- Excel默认回读后复算 SHA-256：`93563cd6e6301b32f2c1e828e299832db664ed484fd54b8fcf7233ec2d8d7e3c`。
- `hash_equal=true`；内存表与回读表经过v2 canonicalization后的26列内容逐单元完全相等，表头列序、行数和排序键均一致。
- 默认回读把 `stock_code` 推断为 `int64`；v2规范化后所有代码均恢复成六位纯数字，且与内存代码序列逐项一致。
- 日期列、布尔列、三个数值列的canonical值逐项一致；26列的 `<NA>` 数量也逐列一致。未发生空日期、布尔状态、退出延迟或限制原因的丢失。
- 从回读sheet独立复算：实际入场4,634、执行受限92、正常退出4,573、延迟退出58、20日窗超限3、NAV标记3，逐项等于内存summary。

round 12确实改变了审计展示表的4,726个等权 `weight` 的浮点尾数，但最大单行绝对变化仅 `2.406013756284242e-13`，六因子中最大权重合计变化为 `6.400002749984424e-11`。输入 `factor_constituents` 在函数调用前后经严格frame比较完全一致，既有 `portfolio_returns` 对象也完全一致。因此该精度处理只稳定审计证据的Excel往返表达，不改变组合计算；12位小数仍完整保留股票、权重、成交限制、退出状态、日期和延迟等关键审计信息。

正式 `returns_detail.xlsx` 在复审前后文件SHA-256均为 `575838f5030b495fe181c5d6d81b15435188ddc9ebc2c8907368887868987279`，mtime亦未变化，确认本次复审未覆盖正式结果。

### coder记录差异

`result_fix_round2.md` 自述的哈希为 `1ecaacad...d7ee2`、执行受限97；当前共享树在上述独立固定口径下得到 `93563cd6...d7e3c`、执行受限92。故 coder 记录中的这两个绝对数不能作为当前树的可重复证据。本 verdict 不采信该自述，而依据独立复算的“内存hash=summary hash=Excel默认回读hash”及业务计数一致性判定；该证据记录差异不改变当前实现的功能性通过结论。

verdict RA-A02: pass

## RA-A01：预测散点回归

- 当前实现仍按 `predictor_period,prediction_period,factor` 三键作 `validate="one_to_one"` 连接，并断言期望行数、实际收益/赢家无空值、逐月六因子及唯一赢家（`reporting.py:524-581`）。
- 只读既有33个月结果独立调用当前函数得到198行、33个月；每月均6行/6个唯一因子且赢家数为1，概率、实际因子收益及赢家字段缺失总数为0。
- 以当前 `_build_chart_data` 和 `create_charts` 写入临时目录，六张图均成功生成；`prediction_scatter.png` 为 `2955×1752`。绘图前“不允许drop后行数变化”的断言仍在（`reporting.py:748-755`），本次未触发。

verdict RA-A01: pass

## CDX-R-01：中证800免成本回归

- AS41仍明确中证800是无成本理论指数基准，净主动收益比较有成本策略与无成本指数（`assumptions.md:527-538`）。
- 组合实现仍把中证800的买入、卖出及总交易成本强制为0，并设置 `index_benchmark_no_stock_cost`；三个主动因子组合设置 `factor_sleeve_stock_cost`（`portfolio.py:472-481`）。
- 既有结果复算：中证800 33行，交易成本合计0，净/毛收益最大绝对误差0，33行口径均为 `index_benchmark_no_stock_cost`；三个主动组合共99行，口径均为 `factor_sleeve_stock_cost`。

verdict CDX-R-01: pass

## 编译与边界

- `.venv/bin/python -m py_compile src/r003_equity_factor_timing_cn/*.py`：通过。
- 真实数据运行仅出现PyArrow读取CPU cache受限的环境警告，不影响退出码、哈希或断言。
- 所有新工作簿和图片均写入 `/private/tmp` 临时目录并自动清理；未写正式结果。

全局门禁：未判定，由主会话处理。
