```json
{
  "checkpoint": "code_recheck_round1",
  "verdict": "pass_with_issues",
  "closed": [
    {
      "issue": "CA-ALL-01",
      "result": "closed",
      "evidence": "data_pipeline.py:1445-1451 强制 请求集合==manifest success==合并面板集合，1469-1487 对每只证券做逐证券缓存与合并切片 assert_frame_equal 精确内容比较并重算正文 SHA256（1417/1465），1533-1542 在 qualified<500（config.py:100）、failed>1（config.py:101）或合并面板实际证券<500（config.py:43）时 raise ValueError；main.py:662-666 在 _stage_m1 实际调用，全链路无 catch 点。"
    },
    {
      "issue": "CA-ALL-02",
      "result": "closed",
      "evidence": "portfolio_pipeline.py:656-666 从 CN/US 各自日历独立生成 2016–2021 预期交易日，674-676 按 graph_update_days=10（config.py:178）生成预期锚点并与 graph_pipeline.py:351-360 的切块原点一致，780-789 要求每组起止日期、缺失日期/股票、逐日满股票覆盖全部为零缺口，842-853 强制同市场三规格×十模型键集合 SHA256 完全一致，855-861 任一 incomplete 抛 FormalCoverageError（继承 ValueError，全仓无捕获点）；run_m4_portfolios:916 在组合计算前调用，main.py:1024-1031 传入真实日历与股票池。"
    },
    {
      "issue": "CA-ALL-03",
      "result": "closed",
      "evidence": "main.py:681-731 _stage_m1 实际调用源 schema、加载面板、双市场收益面板、合并面板合同、逐证券覆盖与收益分布六类审计，732-744 对 status=fail 直接 raise；627-640 将五张审计表列入原子检查点 names 并 write_frame（759-762）；main.py:2382-2388 将五表以 _audit 结尾名注入正式 tables，经 reporting.py:901-914 进入 evidence_tables.xlsx。"
    },
    {
      "issue": "CA-ALL-04",
      "result": "closed",
      "evidence": "main.py:271-296 code_manifest 在报告目录与三个 ml 公共模块外新增 common/data_loader.py:281、common/backtest.py:282、common/utils.py:283、pyproject.toml:284、uv.lock:285，正文 SHA256 进入 aggregate_sha256；五文件经 Glob 确认均存在，且文件缺失会改变 entries 列表同样使哈希失效。"
    },
    {
      "issue": "CA-ALL-05",
      "result": "closed",
      "evidence": "main.py:605-619 _m5_input_manifest 以 _path_identity_manifest 绑定 pipeline.data.cn_stock_industry（config.py:29）的完整正文 SHA256 与 parquet schema SHA256，main.py:2079-2084 将其纳入 M5 build_context；sensitivity_pipeline.py:980-982 load_citic_level_one_industry 读取同一配置路径，行业文件变化必使 M5/SA6 检查点失效。"
    },
    {
      "issue": "CA-ALL-06",
      "result": "closed",
      "evidence": "main.py:191-222 _path_identity_manifest 已删除 32MiB 元数据分支，对所有正式原始输入以 1MiB 分块流式计算完整正文 SHA256（210）并保留 parquet schema SHA256（204-209），identity_sha256 同时绑定两者；main.py:580-602 _m1_raw_input_manifest 对全部 8 项原始输入统一走该函数。"
    },
    {
      "issue": "CA-ALL-07",
      "result": "closed",
      "evidence": "main.py:2186-2202 从正式 US_TO_CN 快照取 2021-10-21（config.py:816）或最近锚点，adjacency.to_dense_frame()（graph_pipeline.py:158-175，值即带符号 t_beta、行源列目标）转置为行 cn_target_code、列 us_source_code，无边为 0；reporting.py:530-537 消费真实矩阵，空矩阵只会显式 not_applicable 不伪造（310-323）；2203-2227 输出请求/实际锚点、距离、行列合同、形状与非零边数审计，D9 行业子集边界单独登记不可复现。"
    },
    {
      "issue": "CA-ALL-08",
      "result": "closed",
      "evidence": "main.py:2243-2269 将 q25/q50/q75 melt 成长表并强制 方向(2)×分位(3)=6 个唯一 series_label，缺一即 raise；reporting.py:546-559 按 series_label 绘制六序列；reporting.py:874-876 FIG5入度分位底表 sheet 写入六序列底表，927-929 将 fig05 png 嵌入同一 sheet（write_table_workbook 808-813）。"
    },
    {
      "issue": "CA-ALL-09",
      "result": "closed",
      "evidence": "main.py:1287-1310 每配置预测与 model_audit 分别经 write_external_frame_atomic 原子持久化并带 sidecar 上下文/哈希/schema 校验，1376-1491 在 Sharpe 计算前核对每配置起止日期、缺失日期/股票、逐日满股票覆盖、键数与键集合 SHA256，1477-1491 强制全配置样本键完全一致且覆盖正式 CN 日历/股票池，不通过在组合前 raise；sensitivity_pipeline.py:237-280 无入边目标写入 skipped_no_inbound_edges 审计行不再静默丢弃；m5_sa3_grid_audit/m5_sa3_model_audit 进入检查点（1525-1526）、敏感性工作簿（reporting.py:887-892）与 evidence tables。"
    }
  ],
  "dimensions_checked": [
    {
      "dimension": "九项原问题关闭",
      "result": "no_findings"
    },
    {
      "dimension": "未来函数与时点",
      "result": "no_findings"
    },
    {
      "dimension": "R2硬编码隔离",
      "result": "no_findings"
    },
    {
      "dimension": "静默吞错与范围缩水",
      "result": "no_findings"
    },
    {
      "dimension": "正式输出与checkpoint",
      "result": "no_findings"
    }
  ],
  "findings": [
    {
      "id": "CDX-C-R1-01",
      "severity": "minor",
      "category": "范围缩水",
      "location": "src/r007_cross_market_return_forecasting/portfolio_pipeline.py:776-789; src/r007_cross_market_return_forecasting/main.py:1424-1435",
      "description": "两处新门禁均为零容忍满覆盖合同：要求 2016–2021 每个预期交易日×每只池内股票都有预测。但 AS14 登记了『无入边节点则不预测』，且 sensitivity_pipeline.py:237-280 显示无入边是真实会发生的分支；只要任一目标股票在任一锚点无入边，M4 与 SA3 将整体硬失败。这是 assumptions 未登记容忍度时修复者明示选择的『零静默缩水』口径，方向上正确（失败是响亮的而非静默），但主会话应预期正式运行可能在此失败，届时正确处置是在 assumptions 登记可容忍缺口比例后再放宽门禁，而非削弱或绕过门禁。",
      "suggestion": "正式运行前由 quant-planner 评估是否需要在 assumptions.md 补充登记逐日股票覆盖率的可接受阈值（例如允许无入边目标按 AS14 登记性缺席），避免 verifier 阶段失败后无依据地回调门禁。",
      "confidence": "medium"
    }
  ]
}
```
