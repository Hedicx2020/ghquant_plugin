# r003_equity_factor_timing_cn 验证证据链（attempt2）

> quant-verifier在result_audit修复后亲自执行正式主程序，并从底层Excel/JSON独立重算。实现者或审计者自述不作为证据。

## E1-E6 证据条目

| 证据ID | 规则 | 声明来源 | 证据类型 | 证据 | 佐证 | 核验方式 | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EVD2-01 | E1 | attempt2正式主程序可完成 | 运行日志 | `UV_CACHE_DIR=/private/tmp/report_reproduce_uv_cache uv run --extra ml python -m src.r003_equity_factor_timing_cn.main`；2026-07-18T11:38:15+08:00至12:00:00+08:00 | exit=0；elapsed=1304.761965；33个月；16项产物 | 亲自执行统一会话并读取最新run_log段 | pass |
| EVD2-02 | E2 | 正式结果来自当前源码 | mtime与源码哈希 | 最新src为`reporting.py` 2026-07-18T11:28:29+08:00；最早result为11:58:27 | 全部16项mtime均晚于latest src；运行前后九个src SHA256一致 | 亲自逐文件stat和shasum | pass |
| EVD2-03 | E3 | 文件合同完整 | 文件/格式点收 | `results/`恰有16个非空合同文件 | 5 Excel、6 PNG、3 JSON、2 Markdown；6图>15KB且约300DPI；15 sheet、6张内嵌图 | 亲自枚举、解析、打开Excel/PIL | pass |
| EVD2-04 | E4 | 中证800年化收益 | 三方核对 | metrics=`0.05673765732343328`；verify_report同值；`中国OOS毛收益!B2`同值 | 从33条月收益独立复算同值 | 默认read_excel后亲自复算 | pass |
| EVD2-05 | E4 | 中证800观测数 | 三方核对 | metrics=33；verify_report=33；`中国OOS毛收益!A2=33` | 月份集合2023-04至2025-12无缺口 | 亲自枚举月份 | pass |
| EVD2-06 | E4 | RankIC均值 | 三方核对 | metrics=`0.129004329004329`；verify_report同值；`因子预测指标!B4`同值 | 33条RankIC均值同值 | 亲自读取和复算 | pass |
| EVD2-07 | E4 | 周期组合累计成本 | 三方核对 | metrics=`0.0041875`；verify_report同值；`中国OOS毛收益!K4`同值 | 月度成本求和同值 | 亲自读取和复算 | pass |
| EVD2-08 | E4 | ML组合累计成本 | 三方核对 | metrics=`0.01933195339426413`；verify_report同值；`中国OOS毛收益!K5`同值 | 月度成本求和同值 | 亲自读取和复算 | pass |
| EVD2-09 | E5 | 正式OOS样本量合理 | 区间推算 | 2023-04至2025-12按月应有33期 | 概率33期、组合各33期、散点33×6=198 | 独立构造期望月份并比较 | pass |
| EVD2-10 | E6 | 时间链单调 | mtime链 | spec 2026-07-18T02:00:37+08:00 → src 11:28:29 → results 11:58:27起 → verify_report在独立验证后写入 | 报告只引用attempt2正式结果 | 亲自读取mtime | pass |
| EVD2-11 | E3/E4 | 13条产物哈希有效 | SHA256 | `oos_evidence_manifest.json` 13条逐项重算一致 | verifier补充comparison后同步更新comparison行哈希 | 亲自逐文件读取字节并哈希 | pass |

## result_audit修复专项证据

| 证据ID | 核验对象 | 证据 | 独立核验 | 结果 |
| --- | --- | --- | --- | --- |
| EVD2-R01 | 预测散点底表 | `图_预测散点` 198行、33个月、每月6因子和唯一赢家 | predicted_probability/factor_return/is_winner零空值；独立重画PathCollection offsets=198 | pass |
| EVD2-R02 | 正式散点PNG | `prediction_scatter.png` 224651字节、2955×1752、约300DPI | 底表198行在绘图前无drop；正式PNG列入13条哈希 | pass |
| EVD2-R03 | 逐股票审计结构 | `execution_exit_audit` 154529行、26列、33个月 | 必需字段完整；重复键0；T+1、执行/退出条件和20交易日上限逐行断言 | pass |
| EVD2-R04 | 逐股票审计计数 | 执行151483、受限3046、正常退出148330、延迟2885、未解决268、NAV留痕268 | Excel默认回读计数与metrics/latest run_log一致 | pass |
| EVD2-R05 | canonical v2哈希 | `c2a11549c2f6f172d3fdb376a8b279361e6754b25e23f437dd350cdf8ba88692` | 未调用策略函数，按文档独立实现日期/布尔/12位小数/空值/代码归一化后从默认read_excel复算 | pass |
| EVD2-R06 | 中证800成本 | 理论指数基准累计成本0 | 33月毛=净，cost_basis唯一为index_benchmark_no_stock_cost | pass |
| EVD2-R07 | 三策略成本 | 1/N=`0.001`、周期=`0.0041875`、ML=`0.01933195339426413` | 三者均总成本>0且存在正成本月；gross-net=cost | pass |
| EVD2-R08 | 修复前后收益稳定 | attempt1与attempt2的132行组合收益SHA均为`be1d5e956514eac6a139ac794558635161edfacf499ae67cc766bc7ffed1b07d` | 四组合各33月，核心毛/净指标逐项误差≤1e-12 | pass |

## hard难度扰动测试

### attempt1策略级扰动的适用边界

attempt1完整执行过将截止日提前至2024-12的21个月重跑，四组合年化收益相对变化89.75%至186.85%。由于该测试早于本轮reporting修复，只保留为策略核心不硬编码的旁证，不用于证明attempt2报告层新鲜性。

### attempt2新鲜定向扰动

- 执行时间：2026-07-18T12:01:47+08:00。
- 输入新鲜性：输入`metrics.json` mtime 2026-07-18T11:58:28+08:00，晚于最新src 11:28:29。
- 方法：直接从attempt2正式Excel默认回读，在内存中改变一个散点概率、一个审计权重和一个ML月收益；不修改正式结果文件。

| 扰动对象 | 基准 | 扰动 | 输出变化 | 结果 |
| --- | --- | --- | --- | --- |
| 198点散点 | 首条概率0.2561118136791068；offset SHA=`a3a673...a6e7` | 概率+0.05；offset SHA=`2424da...27c4` | 198点坐标哈希改变 | pass |
| 154529行审计 | 选定列SHA=`75dc02...f63a5` | 首行weight +0.000001；SHA=`e89ff4...d641` | 审计输出哈希改变 | pass |
| ML核心绩效 | 年化收益0.09714499114320896 | 首月收益+0.01后年化0.10111901391347411 | 相对变化4.0908159273% > 0.1% | pass |

扰动测试未见输出与输入解耦或硬编码。定向扰动全在内存完成，无临时正式产物需要保留。

## 审计结论

- E1-E6全部有至少一条亲自执行证据：是。
- 三方数值不一致条数：0。
- 正式文件缺失数：0；manifest哈希不一致数：0。
- 散点缺实际收益/赢家行数：0；绘图缺点数：0。
- 逐股票审计行数、v2哈希或计数不一致数：0。
- 修复前后四组合月收益不一致数：0。
- 运行失败数：0。非阻断警告为Matplotlib/Fontconfig缓存、Arrow sysctl、joblib核探测及SVC未来弃用。
- 门禁结论由主会话统一判定。

## result_audit最终反虚报复审

> 复审者只读取attempt2正式Excel/JSON/PNG和当前文档，未采信producer/verifier自述；完整过程见 `audit/result_reaudit_round1.md`。

- RA-A01：`图_预测散点` 198行/33月/逐月6因子1赢家；独立重建得到198个offset，重建PNG与正式PNG像素及SHA完全一致，无11个月丢失。
- RA-A02：默认 `read_excel` 得154,529行×26列×33月；独立实现v2 canonicalization得到 `c2a11549c2f6f172d3fdb376a8b279361e6754b25e23f437dd350cdf8ba88692`，与metrics及latest run_log一致；交易限制、延迟退出和20交易日耗尽链逐行可追溯。
- AS41：中证80033月成本为0且毛=净；三个可投资策略成本分别为0.001、0.0041875、0.01933195339426413，文字与正式结果一致。
- comparison/K2：21个数值项全部从132行月收益复算；低于0.5%相对差的项目为0，未见过于完美。
- infeasible：D15–D29恰15项；原文声称25个宏观驱动但仅公开10个，其余无名称、数值或变换，且有A1/AS29人工裁决，skip理由成立。
- K3：六图逐张视觉检查非空白，序列/点数与底表一致；累计收益与回撤逐点/逐组合对上metrics。
- E4：中证800年化收益、观测数、RankIC均值、周期成本、ML成本五项三方逐值一致；13条manifest文件哈希全部复算一致。
- hard扰动：attempt1完整截止日扰动证据仍适用于未变的策略核心；attempt2正式底表的ML收益、散点概率和审计权重内存扰动均引起对应输出变化，其中ML年化收益相对变化4.0908% > 0.1%。
- 结论措辞：明确experimental中国迁移、33月短样本和30.30%分类准确率边界，不宣称长期稳定领先或充分泛化。
- findings：0（critical=0，major=0，minor=0）。

verdict: pass
