# iter_01 锁定修改点二：reporting 改动记录

## 修改边界

- 仅修改 `src/r004_all_a_style_box/reporting.py`、`src/r004_all_a_style_box/main.py`、`src/r004_all_a_style_box/workbook_builder.mjs`、`tests/test_r004_all_a_style_box_reporting.py`。
- 本文件只记录锁定修改点二，供主会话合并进 `changes.md`。
- 未修改 config/data_pipeline/strategy/portfolio、spec/plan/assumptions/coverage/state、正式 results 或审计结论。
- 未运行正式 main；所有生成/重建验证均在 pytest 的 `/tmp` 临时目录。

## 实现摘要

### 1. PIT 与证券生命周期正式证据

- `reporting._collect_detail_tables()` 新增 `pit_style_inputs`、`security_event_audit`，正式证据由10表增至12表。
- `pit_style_inputs` 直接消费 `m2.pit_style_inputs` 全 eligible 合同，不从收益反推或补造财务字段。
- `validate_pit_style_inputs()` 独立重算：三核心加可选股息的 Value、Growth、Style=Growth-Value、Size/Style稳定二分和四箱标签；所有披露日/来源日必须不晚于 signal date，容差 `1e-12`。
- `validate_security_event_audit()` 阻断未来事件、未解释陈旧残余、blocking 行及持仓/现金/收益结算误差超 `1e-12`。
- Parquet 写出后立即读回，逐表核验行数、列序与稳定内容 SHA；manifest v2 记录文件 SHA、行列数、readback SHA 和视图规则。
- Excel 维持5本/51个sheet合同；两张新增全量表通过 DetailManifest、Sources 和7行 Checks 的证据列呈现，不增加sheet数量，也不把Top-N视图冒充全量。

### 2. 三层收益与累计成本勾稽

- reporting 正式要求 `target_reference_return`、`actual_gross_before_cost_return`、`actual_net_return`；旧 `gross_return/net_return` 仅用于兼容一致性审计。
- 输出字段明确为目标组合参考收益、受约束实际持仓成本前收益、同一实际持仓成本后净收益；目标层缺失保持 NaN/不可用，禁止用实际gross冒充理想组合。
- 日/月成本前后NAV均从正式OOS期初1.0归一；长组合期末成本前NAV不得低于成本后NAV。
- `gross_cash-net_cash` 或累计 `total_cost` 与成本前后NAV差逐期勾稽，最大允许误差 `1e-12`；不再以“每月net必须低于gross”作错误方向断言。
- metrics、comparison、Excel标题同步记录三层语义与累计成本定义。

### 3. verifier 最终化入口

- 正式初跑仍只生成 `pending_verifier`，并持久化 `workbook_payload.pending.json`。
- `finalize_workbooks_from_verifier_context()` 不重跑策略，只读取 verifier JSON 和当前 Assumptions，重建5本工作簿。
- 最终上下文必须为 schema v1、`verified/PASS`，绑定24条Assumptions内容SHA、精确覆盖7项Checks且全PASS、逐项确认7条结论边界，并给出 verify report/evidence manifest；否则硬失败。
- 最终5/5 Cover显示 `verified/PASS`、context SHA、报告与证据路径；Assumptions为当前24条，Checks为7/7非空PASS。Node inspect 与Python manifest门禁继续检查Cover实际内容、51/51 render/inspect/A2冻结和原生图表。
- 每本Cover与Sources紧邻披露：实验性中国迁移、仅33个月、包含北交所、证券生命周期数据边界、成本与可交易约束、2025-12记账至2026-01-05、不构成投资建议；PASS不表述为长期稳定。

### 4. hard扰动可重放合同

- CLI支持 `--perturbation-oos-end`，输出目录与正式结果目录必须完全独立且不得父子嵌套。
- 运行前后对正式目录全文件取SHA，任何变化立即失败。
- 独立目录持久化 config diff、完整命令、时间、退出码、metrics、comparison、12表detail manifest及Parquet、PIT/R4/R7/事件检查和全部实际文件SHA。
- 只有 exit=0、R4=49、R7频率和误差不超过 `1e-12`、PIT未来披露为0、事件链闭环时才写成功的 `perturbation_replay_contract.json`。

### 5. 累计图标签

- `group_cumulative_returns.png` 标题改为“目标参考累计净值”，明确不含交易约束/成本。
- 33个月日期轴最多12个主刻度，统一 `YYYY-MM`、旋转35度并右对齐，避免月份重叠。

## 有界测试与退出码

1. `UV_CACHE_DIR=/tmp/r004_uv_cache uv run pytest -q tests/test_r004_all_a_style_box_reporting.py -x`
   - exit: 0
   - 结果：`5 passed in 28.58s`
   - 覆盖：12表写出/回读/哈希、PIT/事件独立重算、三层gross/net与累计成本、5本51-sheet verified/PASS最终化及A2、扰动合同/正式目录SHA不变、33月日期轴。
2. `UV_CACHE_DIR=/tmp/r004_uv_cache uv run pytest -q tests/test_r004_all_a_style_box_data.py tests/test_r004_all_a_style_box_portfolio.py -x`
   - exit: 0
   - 结果：`4 passed in 48.93s`
   - 用途：确认与并行锁定修改点一新增 `pit_style_inputs`、`security_event_audit`、三层收益字段接口兼容。
3. `UV_CACHE_DIR=/tmp/r004_uv_cache uv run python -m compileall -q src/r004_all_a_style_box tests/test_r004_all_a_style_box_reporting.py`
   - exit: 0
4. `node --check src/r004_all_a_style_box/workbook_builder.mjs`
   - exit: 0

## 未由 coder 宣布的事项

- 上述均为实现自检/有界 fixture，不是正式回测验证结论。
- 正式33个月数据、12张正式Parquet、5本最终Excel、8张PNG与hard扰动必须由 verifier 在后续全量运行中生成和裁判。
