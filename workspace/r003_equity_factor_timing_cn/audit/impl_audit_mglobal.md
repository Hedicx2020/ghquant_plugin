# r003 中国市场迁移版全局实现忠实性内审

- mode: `code`
- milestone: `global`（m1–m5）
- 审计输入：`spec/spec.md`、`spec/coverage_matrix.md`、`assumptions.md`、`src/r003_equity_factor_timing_cn/` 全部模块及相关 `common/` 模块
- 隔离声明：未读取 coder 完成汇报、`verify_report.md`、`audit_responses.md`，未采信被审者自述；未修改代码、状态或结果文件。
- 审计范围：矩阵全部 63 条 `done` 要素；本文件仅判定实现忠实性，不替代 verifier 的正式全量结果验证。

## 结论

本轮未发现 critical、major 或 minor issue。round1 的 CDX-C-01/CDX-C-02 及 round2 的 m3 标签截止边界均已在当前代码中形成可执行约束；m1 新增交易限制与标签字段为下游增量合同，m2→m3→m4→m5 的正式接口未被破坏。

## 定向独立复核

### 1. CDX-C-01 杠杆公式

- AS7 规定 `((M2同比-名义GDP同比)+(社融同比-名义GDP同比))/2`；实现先以名义 GDP 水平计算 12 月同比，再对两个缺口等权平均，符号、分母和时点一致（`src/r003_equity_factor_timing_cn/data_pipeline.py:210,226-229`）。
- 用真实中国宏观数据独立重算：132 个月中 120 个月公式可比，`max_abs_error=0.0`；首个可比月为 2016-01。
- 杠杆派生字段的证据依赖显式登记为 M2、社融和名义 GDP（`data_pipeline.py:267-281`）。对应 132 条可得日证据中，`available_date > signal_date` 为 0 条。

### 2. 中国市场执行日限制与退出限制

- ST 区间严格采用 `[implement_date, remove_date)`；`remove_date` 当日不再视为 ST（`strategy.py:46-73`）。信号日先做 ST 过滤，执行日重新读取 ST 区间，并与成交量、停牌、涨停、跌停共同判断（`strategy.py:76-118,268-321`），因此信号后新增 ST 不会穿透执行检查。
- 计划退出日复用同一交易限制；候选日历冻结为计划日加 20 个额外交易日，共 21 个候选日（`strategy.py:121-163`）。逐股票只选首个真实可交易日；实际退出日、交易日/自然日延迟、限制原因及搜索窗末日均保留。
- 信号权重在检查执行状态前按原入选数量确定（`strategy.py:516-545`）。收益计算始终使用原权重；执行失败或入口价缺失记现金，超限但计划日有价格记 NAV，计划日无价格才记现金，不做事后重选或重归一（`strategy.py:776-848`）。
- 标签可得日：正常/延迟退出取实际退出日；入口现金取计划退出日；20 日搜索窗耗尽取搜索窗末日，组合取成分最大值（`strategy.py:811-845`）。逐股票证据字段完整输出（`strategy.py:849-855`）。
- 独立构造五股票交易情景复算：立即退出、延迟 2 个交易日退出、20 日超限 NAV、执行日 ST 现金、20 日超限且计划价缺失现金各一只，原始权重均为 0.2。程序结果 `factor_return=0.040000000000000015`，手算为 `0.04`；`weight_sum=1.0`、`priced_weight=0.6`、`cash_weight=0.4`、`unresolved_weight=0.4`、`nav_marked_weight=0.2`，最大延迟为 20 个交易日。ST 撤销日样本被正确判为可交易。
- 真实中国数据全区间 5 股票烟测：132 个月、444 条因子收益、708 条成分记录；执行/退出/标签证据字段无缺列，`signal < execution < return` 违规 0 条，标签早于计划退出日 0 条，最大退出延迟 20，最大权重和误差 0，`cash_weight = weight_sum - priced_weight` 最大误差 0。

### 3. 字段证据与时点

- 宏观输入按 `available_date` 向后 as-of 匹配，派生字段传播最晚依赖日期，历史标准化使用 `shift(1)`（`data_pipeline.py:108-169`）。
- 财务数据以 `info_publ_date` 生成可得日并按股票向后 as-of，不以报告期直接对齐（`strategy.py:324-392`）。动量和低波只使用当时及此前价格（`strategy.py:395-424`）。
- `assert_point_in_time` 对宏观可得日、信号/执行/退出顺序、财务/权益可得日、真实退出日和标签可得日设置硬断言（`data_pipeline.py:492-527`）。

### 4. m3 round2 标签截止边界

- `build_winner_labels` 优先消费 m1 的 `factor_returns.label_available_date`，六因子日期齐备后取最大值，并保留来源字段（`factor_model.py:157-187,203-227`）。正式 m1 合同存在该字段；兼容分支不会在正式入口被采用。
- 每个目标月候选窗仍是此前连续 84 个日历月，历史特征与 t+1 标签严格错开一月（`factor_model.py:591-603`）。训练标签只在 `winner_available` 且 `label_available_date <= predictor_date` 时纳入（`factor_model.py:623-638`）；同日已实现标签允许进入，晚于 predictor date 的标签排除。与此同时 `predictor_date < prediction_date`，所以不会使用实际预测日或未来标签（`factor_model.py:839-851`）。
- 动态边界测试直接调用当前 m3 主函数，并仅在进程内把森林拟合替换为空模型以隔离日期门禁：84 个候选标签中，一个标签日期等于 `predictor_date=2022-02-28`、一个晚 1 天。结果为可训练 83、按可得性排除 1；`latest_training_label_available_date=label_cutoff_date=2022-02-28`，且 `prediction_date=2022-03-31`。边界行为与 round2 口径一致。

### 5. m2–m5 接口与全局抽查

- 正式入口仍依次传递 `M1Dataset → StageOneRegimeResult → StageTwoFactorResult → PortfolioResult → ReportPackage`（`main.py:125-204`）；m1 新字段在 m3 被显式消费，在 m4/m5 为增量列，没有删除既有字段或改变调用参数。
- `src/r003_equity_factor_timing_cn/*.py` 与相关 `common/*.py` 已通过 `py_compile`。未发现 `TODO`、`FIXME`、`NotImplemented`、空 `pass`、`bfill` 或 `backfill`。
- 区间仍由 config 固定为 2015-01 至 2025-12，OOS 冻结点为 2023-03、正式 OOS 为 2023-04 至 2025-12；84 月窗、500 棵树、seed=42、15% 主动倾斜和 20 交易日退出窗均可反查 spec/AS 或集中配置。
- 研报 R10 数值字面量只存在于报告层的原研报参照表，用于中国结果与美国原文分栏比较；未进入 m1–m4 计算路径。未发现以研报目标数值硬编码回测结果的路径。

## 五维度逐项结论

| 维度 | 覆盖与证据 | 判定 |
|---|---|---|
| 公式一致 | 逐条打开矩阵实现位置，对窗口、算子、分子分母及 t/t-1 核对；重点独立重算 AS7、交易权重/NAV 与 m3 日期边界 | consistent |
| 参数一致 | B 类取值及函数数字反查 config、spec、AS；84/500/42/15%/20 日/OOS 区间均有出处 | consistent |
| 实现位置真实 | 63 条 `done` 行的 `文件:函数` 全部存在，符号可定位，未发现 pass/TODO 空壳 | consistent |
| 代码反查 | 公开入口均可映射回矩阵要素或纯编排/输出职责；未发现替换研报方法的未登记“私货” | consistent |
| 简化声明 | 扫描“近似/简化/替代/fallback/兜底”；国债久期近似、2Y 插值、SMOTE 依赖回退、概率归一/1N 回退、成本补充等均可反查 AS 登记 | consistent |

## done 行与 not_found 检查

- m1（24）：D1–D14、F6、F11–F16、B1、B2、B10。
- m2（10）：F2–F5、F7、B8、R1–R3、SA1。
- m3（13）：F1、F8–F10、B3、B4、B9、R4–R8、SA2。
- m4（11）：F17–F21、B11–B14、R9、SA4。
- m5（5）：B5–B7、R10、SA3。
- 合计：63/63 条 `done` 行已核对；实现位置缺失 0，空壳 0，未产生 not_found 判定。

## issue 清单

无。

## 已检查维度清单

- [x] 公式一致
- [x] 参数一致
- [x] 实现位置真实
- [x] 代码反查
- [x] 简化声明
- [x] 所有 63 条 done 行及 not_found/空壳检查
- [x] CDX-C-01、执行日 ST/交易状态、固定 20 交易日退出、超限 NAV/现金、不重归一、字段证据、m3 round2 日期边界、m2–m5 接口、全局前视/硬编码/区间抽查

verdict: pass
