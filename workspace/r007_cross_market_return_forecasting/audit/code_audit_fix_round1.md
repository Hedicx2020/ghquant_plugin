# r007 code_audit 第 1 轮定点修复记录

- 修复范围：`impl_audit_mall.md` 的 CA-ALL-01 至 CA-ALL-09。
- 边界：本文件只记录实现合同与冒烟证据，不给出 code_audit 或复现结果的 pass/fail verdict。
- 正式运行边界：未运行无参正式流水线，未生成或改写 `output/r007_cross_market_return_forecasting/results/` 与 `verify_report.md`。

## CA-ALL-01：美股逐证券缓存、manifest 与合并面板闭环

- 修改位置：
  - `src/r007_cross_market_return_forecasting/data_pipeline.py:audit_us_merged_panel_contract`
  - `src/r007_cross_market_return_forecasting/data_pipeline.py:audit_security_calendar_coverage`
  - `src/r007_cross_market_return_forecasting/main.py:_stage_m1`
- 实现合同：
  - 正式 M1 重新核对配置请求参数与 manifest 请求参数。
  - 强制 `请求代码集合 == manifest success 集合 == 合并面板实际代码集合`。
  - 重新计算合并面板与逐证券文件的完整正文 SHA256；核对 manifest 文件、行数、证券数和 schema。
  - 对每只请求证券将逐证券缓存与合并面板切片做精确内容比较。
  - 逐证券重新计算有效区间 OHLCV 最低非空率、OHLC 逻辑与可计算收益行数。
  - 实际合格证券少于 500、失败超过 1、合并面板实际证券少于 500 或任一集合/内容不一致时直接失败。
- 冒烟证据：
  - 临时双证券逐文件、manifest、合并面板完整合同生成 2 行合格审计。
  - 删除合并面板中的一只请求证券后触发 `ValueError`，未降级为警告。

## CA-ALL-02：2016–2021 正式覆盖门禁

- 修改位置：
  - `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:FormalCoverageError`
  - `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:audit_formal_prediction_coverage`
  - `src/r007_cross_market_return_forecasting/portfolio_pipeline.py:run_m4_portfolios`
  - `src/r007_cross_market_return_forecasting/main.py:_stage_m4`
- 实现合同：
  - 从 CN/US 各自目标市场交易日历独立生成 2016–2021 预期预测日。
  - 从各目标日历首日按配置的 10 个交易日步长生成两方向预期图更新锚点。
  - 对两目标市场、三规格、十模型逐组核对起止日期、日期缺失率、股票缺失率、逐日股票覆盖率、预测键数量与键集合 SHA256。
  - 强制两个方向的实际锚点集合等于预期锚点集合。
  - 强制同一目标市场的三规格×十模型使用完全相同的日期/股票键。
  - assumptions 未登记可接受的正式缩水比例，因此门禁采用零静默缩水合同；任一日期、逐日股票、全期股票、模型、规格、方向或锚点缺口均抛出 `FormalCoverageError`。
  - 覆盖审计写入 M4 检查点与正式 `evidence_tables.xlsx`。
- 冒烟证据：
  - 合成两市场×三规格×十模型完整面板生成 62 行覆盖审计。
  - 删除一个逐日股票键后触发 `FormalCoverageError`。

## CA-ALL-03：M1 审计接入正式证据链

- 修改位置：
  - `src/r007_cross_market_return_forecasting/data_pipeline.py:audit_us_merged_panel_contract`
  - `src/r007_cross_market_return_forecasting/data_pipeline.py:audit_security_calendar_coverage`
  - `src/r007_cross_market_return_forecasting/data_pipeline.py:audit_return_distributions`
  - `src/r007_cross_market_return_forecasting/main.py:M1Tables`
  - `src/r007_cross_market_return_forecasting/main.py:_stage_m1`
  - `src/r007_cross_market_return_forecasting/main.py:run_formal_pipeline`
- 实现合同：
  - `_stage_m1` 正式调用源 schema、加载后面板、双市场收益面板、逐证券覆盖、股票池集合、收益分布与缺失率审计。
  - schema/字段、重复键或 OHLC 逻辑出现 `status=fail` 时 M1 直接失败。
  - 五张 M1 审计表进入原子检查点；正式 reporting 将其加入 evidence tables。

## CA-ALL-04：检查点代码闭包与依赖锁

- 修改位置：
  - `src/r007_cross_market_return_forecasting/main.py:CheckpointStore.code_manifest`
- 实现合同：
  - 在原报告目录与 ML 公共模块基础上加入直接依赖 `common/data_loader.py`。
  - 加入传递依赖 `common/backtest.py`、`common/utils.py`。
  - 加入依赖声明与锁文件 `pyproject.toml`、`uv.lock`。
  - 上述任一文件正文变化均改变聚合代码哈希并使既有检查点上下文失效。
- 冒烟证据：
  - 隔离检查点清单中确认存在 `common/data_loader.py`、`common/backtest.py`、`common/utils.py`、`pyproject.toml`、`uv.lock`。
  - 项目既有 checkpoint smoke 确认 code/config/input 任一上下文变化会失效。

## CA-ALL-05：SA6 行业输入绑定 M5 上下文

- 修改位置：
  - `src/r007_cross_market_return_forecasting/config.py:DataFiles`
  - `src/r007_cross_market_return_forecasting/main.py:_m5_input_manifest`
  - `src/r007_cross_market_return_forecasting/main.py:_stage_m5`
  - `src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:load_citic_level_one_industry`
- 实现合同：
  - `ashare_stock_industry.parquet` 成为集中配置字段。
  - M5 上下文同时绑定上游 marker 与行业文件的完整正文 SHA256、schema SHA256。
  - 行业文件内容或 schema 变化会改变 M5 输入上下文，不能复用旧 SA6/M5 检查点。
- 冒烟证据：
  - 临时行业 parquet 的 M5 input manifest 同时产生非空 `content_sha256` 与 `schema_sha256`。

## CA-ALL-06：正式原始文件完整内容哈希

- 修改位置：
  - `src/r007_cross_market_return_forecasting/main.py:_path_identity_manifest`
- 实现合同：
  - 取消 32 MiB 以上文件只使用路径、大小和 mtime 的分支。
  - 所有正式原始文件均通过 1 MiB 分块流式读取完整正文并计算 SHA256。
  - parquet 仍额外保留 schema SHA256；`identity_sha256` 同时绑定完整正文与 schema。

## CA-ALL-07：FIG3 真实二邻接矩阵

- 修改位置：
  - `src/r007_cross_market_return_forecasting/config.py:ReportingConfig`
  - `src/r007_cross_market_return_forecasting/main.py:_build_fig03_graph_evidence`
  - `src/r007_cross_market_return_forecasting/main.py:_build_chart_tables`
  - `src/r007_cross_market_return_forecasting/reporting.py:create_result_charts`
  - `src/r007_cross_market_return_forecasting/reporting.py:write_formal_outputs`
- 实现合同：
  - 请求锚点集中配置为 spec 的 `2021-10-21`。
  - 从正式 `US_TO_CN` 快照中选择该日或日历距离最近的可审计锚点。
  - 将稀疏带符号 `t_beta` 二邻接矩阵转为行=CN 目标股票、列=US 源股票；无边单元为 0。
  - D9 行业字段缺失时保留全量 B1 图节点，并在锚点审计中明确登记原图 254×235 行业限额子集不可取得；不再把整张 FIG3 置空。
  - 正式热图消费真实数值矩阵；Excel 底表显式保留 CN 行股票代码与全部 US 列股票代码。
  - 另输出请求锚点、实际锚点、距离、方向、行列合同、形状与非零边数审计表。
- 冒烟证据：
  - 隔离 2×2 稀疏快照选择最近锚点 `2021-10-22`，转置后行列名称分别为 `cn_target_code`、`us_source_code`。
  - 隔离 reporting smoke 的 `fig03_biadjacency_heatmap.png` 状态为 `generated`。

## CA-ALL-08：FIG5 六序列与同 sheet 底表

- 修改位置：
  - `src/r007_cross_market_return_forecasting/main.py:_build_fig05_long_table`
  - `src/r007_cross_market_return_forecasting/reporting.py:create_result_charts`
  - `src/r007_cross_market_return_forecasting/reporting.py:write_formal_outputs`
- 实现合同：
  - 将入度 q25/q50/q75 展开为 `direction/percentile` 长表。
  - 正式图按 `US_TO_CN/CN_TO_US × q25/q50/q75` 绘制六条可辨识曲线。
  - `ml_core_results.xlsx` 的 `FIG5入度分位底表` sheet 保存六序列底表并嵌入对应 FIG5 图片。
- 冒烟证据：
  - 双方向合成入度表展开为 6 行、6 个唯一 `series_label`。
  - 回读隔离工作簿确认 FIG5 sheet 为 7 行（表头+6 行底表）、冻结 `A2` 且嵌入 1 张对应图片。

## CA-ALL-09：SA3 逐配置审计与共同样本门禁

- 修改位置：
  - `src/r007_cross_market_return_forecasting/sensitivity_pipeline.py:predict_snapshot_single_model`
  - `src/r007_cross_market_return_forecasting/main.py:_sa3_sample_key_sha256`
  - `src/r007_cross_market_return_forecasting/main.py:_run_sa3`
  - `src/r007_cross_market_return_forecasting/main.py:_stage_m5`
  - `src/r007_cross_market_return_forecasting/reporting.py:write_formal_outputs`
- 实现合同：
  - 无入边目标也写逐配置 `model_audit`，不再静默跳过。
  - 每个配置分别原子持久化准备后预测面板和 `model_audit`，两者都有独立 sidecar、上下文、schema 与正文哈希校验。
  - 在计算 Sharpe 前核对每个配置的日期范围、日期数、股票数、逐日最小股票数、预测行数、预测键数、键集合 SHA256、模型审计行数、跳过行数与跳过率。
  - 强制所有配置的日期/股票样本键 SHA256 完全一致，并强制完整覆盖正式 CN 预测日历及目标股票池；不通过时在组合计算前停止。
  - 汇总 `m5_sa3_model_audit` 与 `m5_sa3_grid_audit` 进入检查点、敏感性工作簿和 evidence tables。
- 冒烟证据：
  - 两配置隔离端到端 smoke 生成 12 行 Sharpe、2 行配置模型审计、4 个逐配置 parquet，配置键完全一致。
  - 第二配置删除一个样本键后，在组合计算前触发“SA3 逐配置共同样本/覆盖门禁失败”。
  - 单快照无入边目标产生 `skipped_no_inbound_edges` 审计行。

## 覆盖矩阵回填

- 修改位置：`workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md`
- 回填要素：D1、D6、F4、F5、F7、F8、F9、F18、F19、B1、B7、B11、R2、SA3、SA6。
- 回填规则：只补充本轮新增且真实存在的 `文件:函数`；验证结果列保持空白，状态仍为 `done`，最后更新仍为 `implement`。

## 冒烟命令与结果

1. `uv run python -m compileall -q src/r007_cross_market_return_forecasting common/data_loader.py common/ml_pipeline.py common/ml_portfolio.py common/ml_reporting.py common/backtest.py common/utils.py`
   - 结果：退出码 0。
2. `uv run python -m src.r007_cross_market_return_forecasting.main --smoke`
   - 结果：退出码 0；既有 CA-A01–CA-A08、SA4-DTYPE 与 CLI 动态检查均完成。
   - 隔离产物：`workspace/r007_cross_market_return_forecasting/smoke/artifact_manifest.json`。
3. 新增合同隔离 smoke：
   - CA-ALL-01/02/04/05/06/07/08 合成与临时文件测试完成；对应刻意缺口均触发硬失败。
   - CA-ALL-09 两配置端到端、配置键不一致与无入边审计测试完成。
4. `uv run ruff check ...`
   - 环境未安装 `ruff`，命令无法启动；未把该工具缺失解释为代码审计结论。

## 未解决项

- 本轮九项修复范围内没有已知遗留实现项。
- 按 quant-coder 边界未运行正式全量回测，未形成验证结论；正式运行对数、结果偏差与门禁裁决留给 verifier 与 check_gates。
