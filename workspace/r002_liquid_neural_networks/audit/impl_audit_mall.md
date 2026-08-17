# m_all 全局实现忠实性复核

## 审计范围与证据边界

- mode：`code`
- milestone：`m_all`
- 案例：`r002_liquid_neural_networks`
- 审计对象：`coverage_matrix.md` 中全部 35 个 `status=done` 要素（D1-D5、F1-F8、B1-B12、R1-R7、SA1-SA3）。
- 只读证据：`spec.md`、`plan.md`、`assumptions.md`、`coverage_matrix.md`、本案例 `src/` 全部代码、相关 `common/ml_*` 模块、既有里程碑审计和原外部审计。未把 coder/verifier 的完成自述作为通过证据，未读取或改写正式结果。
- 本次重点：CDX-C-01 至 CDX-C-05 的当前整改、AS19 分段、缺标签预测/持仓、RankIC 标签覆盖、`correlation` 公开字段、synthetic 输出隔离、Excel/Parquet/metrics/run_log 链路，以及 R2 核验等级合理性。

## 独立执行证据

| 检查 | 独立执行结果 | 判定 |
| --- | --- | --- |
| 编译与导入 | `python -m compileall -q common src/r002_liquid_neural_networks`通过；8个目标模块全部导入成功，输出`COMPILE_IMPORT_PASS 8`。 | pass |
| AS19 分段反例 | 连续构造2007-09至2024-12日历并在回测标签端点制造缺失；首个回测信号为`2020-01-01`，回测段有2个缺标签预测样本，`window_pre_split_backtest=59`，预处理拟合区间为`2007-10-10`至`2016-12-01`。训练/验证标签全部有限，三段T/T+1/T+21均未越界。 | pass |
| 标签与候选/分组解耦 | 将GRU首日最高预测股票标签改为NaN，候选仍为100行；该截面`candidate_count=10`、`valid_label_count=9`、`label_missing_count=1`，该股票仍在group1，去掉label列后的分组表逐格不变。 | pass |
| 标签与交易解耦 | 对同一组原标签/缺标签输入独立生成group1、offset0事件并运行账本；两边事件、持仓、交易和净值逐格相同，输出`events=3, trades=2, holdings=5, nav=41`。 | pass |
| 五模型结构 | 真实构造五模型，参数量分别为GRU 13,889、LTC 22,797、NCP（LTC）22,608、CFC 42,177、NCP（CFC）16,623；4行液态manifest的commit均为`695ec22...d47`，NCP两行稀疏、非NCP两行稠密。 | pass |
| 全链路合成冒烟 | 当前代码以独立目录`/tmp/r002_code_audit_smoke_mall2`运行完成并返回0；生成22个根目录Parquet、8张PNG、28个Excel sheet、严格JSON和含`exit=0`的run_log。 | pass |
| 输出同源 | 8个chart_data Parquet与Excel对应sheet的行数、列数逐一相同，每个sheet恰有1张嵌图；模型对和逐日相关表均含`correlation`且不含旧公开字段；标签覆盖满足`candidate=valid+missing`。 | pass |
| 位置真实性 | AST逐一检查35行、134个实现位置，文件和符号全部存在；`strategy.py` 17个公开类/函数中，除3个纯数据类外，全部被矩阵至少一行真实回映。 | pass |

## 五维度总核对

| 维度 | 当前证据 | 判定 |
| --- | --- | --- |
| 公式一致 | 六通道、前复权VWAP、T+1/T+21收益、GRU/液态模型、十分档、多路径、费用、RankIC、年化收益、Sharpe和Pearson均按spec或已登记假设实现。 | pass |
| 参数一致 | 60日×6通道、1/21端点、三段日期、GRU 64维、固定ncps commit、10档、20路径、20日调仓、0.3%卖费、252日年化和AS18最少30共同样本均由集中配置透传。 | pass |
| 实现位置真实 | 35行的134个位置均有真实执行体或真实配置字段，未发现pass/TODO/仅注释占位。 | pass |
| 代码反查 | `strategy.py`公开业务入口均能回映要素；相关公共函数沿实际调用链进入数据、训练、回测或输出，不存在未登记的策略层公开“私货”。 | pass |
| 简化声明 | AS9-AS19覆盖方法级降级、数据缺口、资源不可比、组合账本、展示边界、相关口径和split边界；当前代码未增加未登记的结果敏感参数或样本过滤。 | pass |

## 35个 done 要素逐条复核

| 要素 | 公式/参数证据 | 实现与时点证据 | 简化与输出证据 | 判定 |
| --- | --- | --- | --- | --- |
| D1 | `common/ml_pipeline.py:140-170`计算`log(OHLC/prev_close)`和`log1p(volume/turn_value)`；`config.py:31-49`固定60日六通道。 | `strategy.py:208-268 → prepare_point_in_time_ml_data`真实构造窗口；窗口末日为T。 | AS10登记输入方法级降级、训练期缩尾和标准化。 | pass |
| D2 | `ml_pipeline.py:327-387`按上市日期、逐日行情存在性和ST区间构造动态资格。 | 当前`list_state`只留作审计字段，不反填历史。 | AS13披露历史退市状态不完整和首行情日回退风险。 | pass |
| D3 | T日上市满1年/ST过滤见`ml_pipeline.py:327-387`；T+1停牌/涨跌停见`:390-423`。 | 执行状态在样本确定后附加，不进入六通道特征。 | AS4/AS13登记信号日与执行日职责边界。 | pass |
| D4 | `config.py:74-85`固定2008-2024三段；`strategy.py:106-143`从训练起点前1年读取纯历史。 | 额外历史只用于上市缓冲和60日窗口；样本T/T+1/T+21仍按段归属。 | AS19明确训练段可读2008年前历史上下文。 | pass |
| D5 | `ml_pipeline.py:173-243`推导前复权VWAP；`:246-324`按全市场日历计算`VWAP(T+21)/VWAP(T+1)-1`。 | 端点日期先独立生成，再精确按股票/日期查价；缺价只使label缺失，不丢失端点。 | AS9/AS14登记公式、0.1/10/0.95阈值和中止语义。 | pass |
| F1 | `common/ml_liquid.py:34-93`实现`dh/dt=f(h,t,theta)`、欧拉残差步和严格递增时间网格积分。 | 独立张量反例验证`h_next=h+dt*f`及轨迹形状。 | 该可选理论实现不冒充ncps私有主干。 | pass |
| F2 | 五模型共用同一输入、标签、MSE/Adam、线性输出头、训练/验证流程。 | `common/ml_training.py:382-485`训练器签名不接收回测集；五模型仅替换主干。 | AS9/AS10/AS15登记全部非主干降级。 | pass |
| F3 | `common/ml_training.py:115-187`为单层64维GRU最后状态接线性头。 | `strategy.py:413-517`真实构造、训练、恢复最佳点后回测预测；实测参数13,889。 | AS2/AS15与配置逐项一致。 | pass |
| F4 | `common/ml_liquid.py:161-237`构造`LTC(input=6, units=64, ode_unfolds=6)`。 | `strategy.py:549-695`进入统一训练器；实测参数22,797。 | AS11和锁文件固定官方commit/version/license。 | pass |
| F5 | AutoNCP(64,1,0.5,22222)传入LTC。 | manifest实际为稀疏wiring，实测参数22,608。 | AS11登记稀疏映射和非私参边界。 | pass |
| F6 | `CfC(input=6, units=64, mode=default)`且统一布尔参数。 | manifest为稠密，实测参数42,177。 | AS11登记固定开源实现。 | pass |
| F7 | 同一AutoNCP wiring传入CfC。 | manifest为稀疏，实测参数16,623；未退化为普通CFC。 | AS11逐项登记。 | pass |
| F8 | `ml_portfolio.py:114-172`候选只要求键和prediction有效；`:175-210`按prediction降序分档。 | forward label缺失不删除候选；独立反例中最高预测缺标签股票仍在group1。 | coverage与AS19/AS16当前说明一致。 | pass |
| B1 | 每个T日按实际动态资格构造全市场候选。 | m1回测样本直接进入五模型预测与m4排序。 | 未使用期末固定股票池或指数成分缩水。 | pass |
| B2 | T日过滤上市年限/ST，T+1只约束实际成交。 | `strategy.py:795-864`构造独立市场执行面板。 | AS4明确不可成交则保留原仓/现金。 | pass |
| B3 | 训练T/T+1/T+21都在2008-01-01至2016-12-31。 | `ml_pipeline.py:473-496`不再把window_start强制在段内；独立反例的训练预处理拟合可读2007历史。 | AS19明确窗口可跨split起点、标签不得跨段。 | pass |
| B4 | 验证T/T+1/T+21都在2017-02-01至2019-11-30。 | 验证首部可读2017-02之前历史；标签全部有限；预处理未使用验证行。 | 原防暴露间隔保留。 | pass |
| B5 | 回测T/T+1/T+21都在2020-01-01至2024-12-31。 | 独立AS19反例首信号为2020-01-01，不再损失约60个交易日；回测缺标签仍预测。 | 边界缩短CLI仅为显式扰动，不改默认。 | pass |
| B6 | `floor(rank_zero_based*10/count)+1`生成10档，group1最高。 | 标签NaN前后分组逐格不变。 | AS5/AS16登记等数量和同值股票代码裁决。 | pass |
| B7 | RankIC先逐路径时序均值、再20路径等权；业绩同样先逐路径再平均；每日展示NAV直接平均活动路径。 | `ml_portfolio.py:275-417,881-984`实际实现三层聚合。 | AS3/AS16登记路径口径。 | pass |
| B8 | `ml_portfolio.py:458-512`按0-19起始偏移、每20交易日安排事件。 | 配置强制offset完整且持有期等于调仓周期。 | 无路径抽样或随机种子替代。 | pass |
| B9 | T日目标、T+1执行、最后T+21清仓。 | `ml_portfolio.py:537-804`只在执行日读价格和tradable；特征/排序不读执行状态。 | AS4/AS7/AS16一致。 | pass |
| B10 | 实际卖出名义额扣0.003，阻塞卖单费用为0。 | 费用进入现金和净值，现金不足买单按登记`buy_scale`同比缩量。 | AS16完整披露缩量、两腿费用和影响。 | pass |
| B11 | 多头为group1净收益；Top-Bottom按两腿毛收益差减两腿实际卖费。 | `ml_portfolio.py:837-878`逐日生成后再计算路径指标。 | AS5/AS16声明不是自融资融券账户。 | pass |
| B12 | 日截面Spearman RankIC仅对prediction/label成对完整；252日几何年化、rf=0 Sharpe和回撤按路径计算。 | `ml_portfolio.py:213-417,807-951`；标签覆盖计数贯穿逐日、路径摘要和总摘要。 | 缺标签只改变诊断有效数，不改变分组或交易。 | pass |
| R1 | 5%-70%只在参考配置，复现值为None。 | `build_ml_metrics`标`reference_only`。 | 未复制为本次模型表现。 | pass |
| R2 | 120/80/6GB只在参考配置；本次资源记录来自参数量、设备观测和CPU累计RSS。 | `main.py:272-316`披露baseline、增量、MPS非峰值和CPU不可作显存；不伪造可比值。 | 当前`unverifiable`对“未知原硬件/批次/dtype且本机无可比设备峰值”是合理代码层处理；最终豁免仍须verifier/diagnoser裁定。 | pass |
| R3 | `ml_reporting.py:121-224`对10个无序模型对做Pearson pairwise-complete，至少30共同样本且两侧至少2值。 | 有效对才进入0.69-0.82范围比较；矩阵、模型对和逐日公开字段统一为`correlation`。 | AS18合同完全一致。 | pass |
| R4 | 全期多头实际值来自`top_long/all`的20路径指标平均。 | 研报值与复现值分栏进入metrics/comparison/Excel。 | 研报常量不进入模型、持仓或收益计算。 | pass |
| R5 | 2024多头来自逐路径年度指标。 | 不从全期缩放或抄录。 | AS12只降级原图逐点对齐。 | pass |
| R6 | 全期多空来自实际Top-Bottom日收益和路径聚合。 | 研报值只作参考。 | 无硬编码结果路径。 | pass |
| R7 | 2024多空来自实际年度Top-Bottom路径指标。 | 与R6/全期独立计算。 | 无硬编码结果路径。 | pass |
| SA1 | 2024与全期、多头与多空并列输出。 | metrics、Excel和Parquet均消费同一`path_metric_aggregate`。 | 标明复现生成，未冒充缺失原表。 | pass |
| SA2 | 全区间矩阵、10对摘要和逐日两两诊断由实际预测计算。 | `correlation/n_common/method/sample_scope/status`进入metrics、Excel、Parquet和图。 | Pearson模型间相关与Spearman RankIC明确分离。 | pass |
| SA3 | 五模型分年度组合表现来自路径年度指标；特征重要性遍历完整回测dataset。 | `ml_reporting.py:62-118,401-405,493-594,832-881`进入图、Excel和完整Parquet。 | AS12/AS17声明自有图表和仅展示层抽样。 | pass |

## CDX-C-01至CDX-C-05定向复核

| 外部意见 | 当前证据 | 复核结论 |
| --- | --- | --- |
| CDX-C-01 | `assign_non_overlapping_splits`只检查T/T+1/T+21；AS19允许60日窗口向split前读纯历史。独立反例首回测信号恢复为2020-01-01，预处理只用最终训练窗口覆盖的唯一行。 | resolved / pass |
| CDX-C-02 | 回测split允许label缺失；预测器`_unpack_features`不读标签；候选/分组只读prediction；RankIC才成对删除标签。独立候选、分组、事件、持仓、交易、净值不变性均通过。 | resolved / pass |
| CDX-C-03 | R2原研报硬件、batch和dtype未知，本次CPU无设备显存，MPS又非真实peak，直接做方向比较会把不可比观测伪装为证据。代码诚实输出参考、本次测量和原因并暂列`unverifiable`。该等级最终是否豁免属于verify/diagnoser裁定，不由coder或本代码审计终结。 | code-level合理；阶段性deferred至verify/diagnoser，非代码缺陷 |
| CDX-C-04 | AS18公开模型对和逐日表均为`correlation`；common签名摘要已与`calculate_sharpe(..., rf=...)`一致。合成输出未见旧公开字段。 | resolved / pass |
| CDX-C-05 | `_parse_args(['--synthetic-smoke'])`实际重定向到`results/_smoke`；`run_pipeline`还有二次防护。显式独立目录冒烟的run metadata标`synthetic_smoke=true/formal_result=false`。 | resolved / pass |

## 全链路与反作弊专项

### 未来函数和范围

- 特征窗口仅止于T日；T+1/T+21只作为训练/验证目标和回测事后诊断。
- 预处理拟合mask来自最终合格训练样本窗口覆盖行；验证/回测及未来标签不参与拟合。
- 训练函数只接收train/validation，回测段只在最佳验证检查点恢复后预测；预测可接受NaN标签但拒绝非有限特征。
- m4候选、分组和交易链不读取label；执行状态只在T+1账本读取。
- 默认仍为五模型、10档、20路径、2020-2024回测；仅图/普通Excel明细采用AS17登记展示上限，完整指标与Parquet不抽样。
- 结论：pass。

### 研报数字与异常处理

- R1-R7字面量只出现在`M5ReferenceConfig`，随后进入`report_*`参考列；代码检索未发现它们进入标签、训练、预测、分组、交易或复现指标。
- 没有`except: pass`或失败后返回成功；main失败时写`exit=1`后重新抛出，成功`exit=0`只在JSON、Parquet、PNG和Excel全部写完后记录。
- 未发现空壳、pass/TODO占位、研报值替代复现值、吞错或静默范围缩水。
- 结论：pass。

### metrics / Excel / Parquet / run_log合同

- 标签覆盖摘要和逐日表同时进入metrics、Excel与Parquet；每行满足`candidate=valid+missing`。
- 8个唯一chart_data对象同时供PNG、Excel对应sheet和chart_data Parquet使用；独立冒烟逐一核对行列和嵌图数量通过。
- 相关矩阵、10个无序模型对、逐日诊断均统一`correlation`字段；旧m4相关表单独标legacy，不覆盖R3主证据。
- comparison的R2五项均明确`pass=null`和不可比原因；R3-R7使用实际复现指标；研报参考与复现值分栏。
- run_log含方法、标签覆盖、输出路径和精确`exit=0`；合成运行显式标非正式结果。
- 结论：pass。

## issue清单

当前 open issue：0项（critical 0 / major 0 / minor 0）。未发现实现空壳或需要回退coverage状态的要素。

## 已检查维度清单

- [x] 公式一致
- [x] 参数一致
- [x] 实现位置真实
- [x] 代码反查
- [x] 简化声明
- [x] 35个done行逐条核对
- [x] CDX-C-01至CDX-C-05定向复核
- [x] 未来函数、硬编码、吞错和范围缩水
- [x] compile/import、AS19、缺标签不变性和全链路合成冒烟
- [x] metrics/Excel/Parquet/run_log同源合同

verdict: pass
