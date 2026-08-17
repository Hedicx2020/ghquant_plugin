# 假设登记簿

### [AS1] 以A股本地宽因子面板替代 OpenAP 212 特征面板
- 来源: A3（市场迁移数据替代；方法裁决见 AS26）
- 性质: market-transplant
- 假设内容: 原 OpenAP 212 特征面板替换为 `factor_factor_info.parquet`、实际存在的 `factors/` 数据以及可由本地行情、估值和财报明确衍生的A股因子；只使用 m1 清单确认存在的因子，不强求数量等于 212。
- 行业惯例依据: 市场迁移实验通常保留宽截面信号集合的研究角色，而不把不同市场的因子身份强行视为相同。
- 影响面: data
- 影响 milestone: m1, m2, m5
- 影响指标: R4-R6、R11、R21-R23；数值不可与原美股基准直接对齐。
- 预期影响: 本地因子覆盖、共线性和起始日期变化会改变 IC、alpha 与模型排序。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS2] 以训练窗内方向替代原逐信号方向元数据
- 来源: A3（市场迁移数据替代；方法裁决见 AS26）
- 性质: market-transplant
- 假设内容: 每个本地因子的预期收益方向只在训练窗内用下一月收益关系估计，预测年度开始前冻结；验证期和预测期不回看更新方向。
- 行业惯例依据: 在缺失外部方向字典时，训练样本内定向并在样本外冻结可同时满足方向统一与无未来函数要求。
- 影响面: method
- 影响 milestone: m1, m2, m5
- 影响指标: R4-R6、R16、R21-R22 的 IC、多空收益与 alpha。
- 预期影响: 弱因子的方向估计可能不稳定，导致家族收益和层级排序衰减。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS3] 以本地因子分类作为八家族交叉表的数据来源
- 来源: A3（市场迁移数据替代；用户授权的方法级降级见 AS26）
- 性质: market-transplant
- 假设内容: 本地 `factor_id/factor_id_cn/level1/level2` 作为八个经济家族交叉表的数据来源；具体逐因子归属由 AS26 的固定关键词、字段优先级、冲突顺序和 SHA-256 冻结规则确定。
- 行业惯例依据: 市场迁移应先保留本地分类语义，再由研究者确认跨市场经济家族对应关系。
- 影响面: data
- 影响 milestone: m1, m2, m4, m5
- 影响指标: R1-R7、R13、R15-R22 的全部家族级与层级结果。
- 预期影响: 固定交叉表选择可能改变家族袖套构成、配置权重和机制结论；其影响由映射覆盖、冲突日志和哈希审计暴露。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS4] 以本地可用期A股股票月面板替代原美股长样本
- 来源: A17（市场迁移数据替代）
- 性质: market-transplant
- 假设内容: 由A股前复权日行情、交易数据、股票状态和交易日历构造本地股票月面板，样本起止取因子与滞后宏观数据的共同覆盖；不补齐 1963 年以前或本地不存在的历史。
- 行业惯例依据: 市场迁移的样本期应由目标市场可交易数据覆盖决定，不能拼接异市场历史。
- 影响面: data
- 影响 milestone: m1, m2, m3, m4, m5
- 影响指标: B1-B6 及所有样本期、显著性、回撤和稳定性指标。
- 预期影响: 样本外月份显著少于 479，统计功效和市场周期覆盖下降。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS5] 以中国宏观和A股市场变量替代美国 23 个条件变量
- 来源: A2（市场迁移数据替代；方法裁决见 AS25）
- 性质: market-transplant
- 假设内容: 用 data_catalog 明示的中国通胀、增长、利率、信用、流动性数据以及A股风险、估值、趋势变量保留八块经济角色；不要求变量数量恰为 23，也不宣称变量身份等同。
- 行业惯例依据: 宏观状态迁移以经济角色同构优先于代码或数据供应商同一。
- 影响面: data
- 影响 milestone: m1, m3, m4
- 影响指标: R1-R3、R7-R10、R12、R14-R15、R17-R20、R24。
- 预期影响: 中国宏观制度、频率和市场传导不同，状态持续性与家族 payoff surface 可能显著改变。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS6] 以固定保守滞后替代 ALFRED vintage 历史
- 来源: A10（市场迁移数据替代）
- 性质: market-transplant
- 假设内容: 在本地缺少逐期发布日期和 vintage 时，月度宏观值至少滞后一个月、季度值滞后四个月后才可进入信号；市场派生变量使用截至 T 收盘的数据并在 T+1 执行。
- 行业惯例依据: 固定保守滞后是无法取得实时 vintage 时可审计的防未来函数降级方案。
- 影响面: data
- 影响 milestone: m1, m3, m4
- 影响指标: R1-R3、R7-R10、R12、R14-R15、R17-R20、R24。
- 预期影响: 相比实际发布日期会额外损失时效，状态信号和配置收益可能减弱。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS7] 以A股指数派生状态替代原美股面板衍生状态
- 来源: A2（市场迁移数据替代；方法裁决见 AS25）
- 性质: market-transplant
- 假设内容: 使用 `ashare_csiindex_trade`、`ashare_index_value`、`ashare_index_trade` 和 `ashare_stock_trade` 构造A股趋势、风险、估值与市场流动性状态原料；精确状态函数按 AS25 固定。
- 行业惯例依据: 趋势、风险、估值和流动性可由目标市场指数与成交截面构造经济角色等价变量。
- 影响面: data
- 影响 milestone: m1, m3
- 影响指标: R7-R10、R12、R19-R20、R24。
- 预期影响: 指数结构与市场微观制度不同会改变状态阈值、持续期和容量机制。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS8] 以A股本地六控制组合替代美国 FF5 加动量
- 来源: A7（市场迁移数据替代）
- 性质: market-transplant
- 假设内容: 用A股本地股票月数据构造市场、规模、价值、盈利、投资和动量控制组合；价值/盈利/投资所需财务信息只在 `info_publ_date` 后可用。
- 行业惯例依据: 因子 alpha 的市场迁移应使用目标市场可投资风险因子，而不是把异市场收益序列直接作为控制。
- 影响面: method
- 影响 milestone: m1, m2, m5
- 影响指标: R2、R4、R6、R11、R16、R21-R22 的 alpha 与受控斜率。
- 预期影响: 本地因子定义与美国 FF5+MOM 不同，alpha 只能解释为A股本地风险调整后收益。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS9] 以A股流通市值、行业、历史 beta 和成交换手替代原容量控制
- 来源: A5（市场迁移数据替代）
- 性质: market-transplant
- 假设内容: 使用 T 时点 `negotiable_market_value`、申万一级行业（`standard_code=38`）、只含历史数据的市场 beta，以及 `turn_value/turnover_rate_free` 作为容量和流动性原料。
- 行业惯例依据: 流通市值、行业暴露、历史 beta 与成交换手是本地可交易容量检验的常用可观测代理。
- 影响面: data
- 影响 milestone: m1, m2, m3
- 影响指标: R8-R9、R20、R24 及 SA5-SA7。
- 预期影响: 原文 liquid proxy 未给，目标市场代理可能改变容量衰减的边界位置。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS10] 以本地因子首次可用月替代原信号发表年份
- 来源: A14（市场迁移数据替代）
- 性质: market-transplant
- 假设内容: 从 m1 构造的本地因子面板统计每个因子的首次非缺失月份，作为“本地可用性覆盖”审计；不把该日期解释为学术发表年份。
- 行业惯例依据: 缺失 publication year 时只能审计数据可用边界，不能反推知识发现时间。
- 影响面: data
- 影响 milestone: m1
- 影响指标: R23、SA13；不影响主测试固定因子集。
- 预期影响: 只能回答本地数据何时可用，不能复现原文发表覆盖曲线。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS11] 月度直接排序并形成下一月十分位组合
- 来源: A4（auto 裁决）
- 性质: auto-resolution
- 假设内容: 每月对合格股票的单因子横截面做 1%/99% 缩尾和 z-score；缺失观测不参与当月该因子排序；按当月有效样本分成十组，高组减低组，T 月末算信号、T+1 首个可交易日建仓、持有一个月，同时报告 EW 与按 T 时点流通市值的 VW。
- 行业惯例依据: 月度截面因子研究通常按当月横截面排序、下一期持有，并通过缩尾与标准化降低极端值影响。
- 影响面: method
- 影响 milestone: m2
- 影响指标: R2、R4、R6、R16 的 IC、EW/VW 多空收益、alpha 与换手。
- 预期影响: 若原文使用交易所断点、不同缺失处理或多月持有，组合收益与换手将系统性不同。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS12] 容量区间采用每月流通市值分位并定义本地流动性代理
- 来源: A5（auto 裁决）
- 性质: auto-resolution
- 假设内容: 每月在合格A股母样本内按 T 时点 `negotiable_market_value` 排分位：bottom 20%、middle 60%、upper half、upper third、top 20%、top 10% 按名称直接取对应区间；outside microcaps 排除 bottom 20%。Liquid proxy 采用 `turn_value` 与 `turnover_rate_free` 横截面分位秩的等权平均，并取上半样本。
- 行业惯例依据: 缺少固定交易所断点时，目标市场当期横截面分位能保持容量排序且避免跨市场规模水平不可比。
- 影响面: method
- 影响 milestone: m2, m3
- 影响指标: R8-R9、R20、R24 及 SA5-SA7。
- 预期影响: 分位断点与 liquid proxy 定义会显著改变容量前沿，若归因指向该歧义应切换固定断点或单一成交额代理重测。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS13] IC 采用 Pearson，FMB 使用本地控制，NW 主滞后为 6 月
- 来源: A7（auto 裁决）
- 性质: auto-resolution
- 假设内容: 主 IC 为每月预测分数与下一月收益的 Pearson 横截面相关，并附 Spearman Rank IC 敏感性；Fama–MacBeth 每月控制 log 流通市值、log 账面市值比、12-1 动量和历史 beta；月度均值与斜率使用 Newey–West HAC lag=6，并报告 lag=3/12 敏感性。
- 行业惯例依据: 原文把 IC 与 rank IC 区分不清时 Pearson 可作为标准线性预测口径；月度因子研究常用多月 HAC 并做滞后敏感性。
- 影响面: method
- 影响 milestone: m2, m5
- 影响指标: R2、R4-R7、R11、R16、R19、R21-R22 的 IC、FMB t 和 NW t。
- 预期影响: IC 类型、控制变量和 HAC 滞后主要改变显著性与增量证据，点估计排序可能相对稳定。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS14] 权重相关系数空列按 n/a 保留
- 来源: A8（auto 裁决）
- 性质: auto-resolution
- 假设内容: R3 的 `Trend corr.` 与 `Valuation corr.` 不推算补值，验证表写 `n/a`；本地可另算相关系数，但明确标为实验复现新增指标，不作为原文对数基准。
- 行业惯例依据: 原始表格空值不得从其他统计量逆推，新增分析应与原文基准隔离。
- 影响面: output
- 影响 milestone: m4
- 影响指标: R3 两列相关系数。
- 预期影响: 不影响权重路径、均值和组合表现，只减少两项原文可对齐指标。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS15] 空表 IA.10 作为 method_underspecified 跳过
- 来源: A9（auto 裁决）
- 性质: auto-resolution
- 假设内容: Table IA.10 不复算或填补原文表体，登记 `skip: method_underspecified`；SA2 仍由主表 4、年度权重热图、Table IA.9 与箱线图完成。
- 行业惯例依据: 原稿无数据行且无可唯一恢复规则时应跳过单一展品，同时保留其他可验证证据。
- 影响面: output
- 影响 milestone: m4
- 影响指标: SA2 的“按宏观状态分家族权重”单表，其他权重分布指标不受影响。
- 预期影响: 无法逐格对齐 IA.10，但不妨碍本地权重时间分布与状态相关性的新增分析。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS16] 采用固定保守宏观滞后与 T/T+1 执行
- 来源: A10（auto 裁决）
- 性质: auto-resolution
- 假设内容: 月度宏观值在标记月份后至少一个完整月可用，季度值在期末后四个月可用；缺失时只向后沿用最近已发布值，禁止回填未来值。T 月末状态和权重在 T+1 首个可交易日执行。
- 行业惯例依据: 无逐系列发布日期时，统一保守滞后比“0 months 当月使用”更能控制未来函数风险。
- 影响面: trading
- 影响 milestone: m1, m3, m4
- 影响指标: R1-R3、R7-R10、R12、R14-R20、R24。
- 预期影响: 额外滞后可能削弱状态及时性；若结果衰减，应先做更长滞后敏感性，不能改为同月使用。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS17] 形成期冻结状态阈值与方向后进入确认期
- 来源: A11（auto 裁决）
- 性质: auto-resolution
- 假设内容: 形成期内估计每个状态的 high/low 阈值和收益差方向，确认期完全冻结阈值与方向，不为平衡状态月数而重估；本地形成/确认切点按共同样本的前后时序划分并在 m3 固化。
- 行业惯例依据: 预设 holdout 的核心是把状态定义与方向冻结，确认期不允许为样本平衡回看调参。
- 影响面: method
- 影响 milestone: m3
- 影响指标: R12、SA8 的状态月数、收益差和显著性。
- 预期影响: 确认期可能出现极不平衡状态，导致统计功效下降但保持真正样本外含义。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS18] 命名事件按完整自然年或明确季度剔除
- 来源: A12（auto 裁决）
- 性质: auto-resolution
- 假设内容: 事件窗口固定为 1987 全年、1998 全年、2000–2002、2007–2009、2011 全年、2018Q4、2020 全年、2021 全年、2022 全年；本地共同样本前的事件自动无可剔除观测且不替换为未在 spec 命名的中国事件。
- 行业惯例依据: 只有年份范围而无月份时，完整自然年是最透明、可复算且不依赖事后市场路径的解释；明确 Q4 的事件按季度。
- 影响面: param
- 影响 milestone: m3
- 影响指标: R20、R24、SA6、SA14 的事件剔除样本数和收益差。
- 预期影响: 宽事件窗可能比作者预设窗口剔除更多月份；若结论敏感，应在迭代中切换为事件核心月重测。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS19] 正文精确 IC 为主、表格两位小数为展示值
- 来源: A13（auto 裁决）
- 性质: auto-resolution
- 假设内容: R4/R5 对数时以正文 0.0508、0.0197、0.0725、0.0727、0.0002 为精确基准，表格 0.05/0.07 仅视为两位小数展示。
- 行业惯例依据: 同一文稿中正文给出更多有效位时，通常是表格格式化后的精确底稿值。
- 影响面: output
- 影响 milestone: m5
- 影响指标: R4/R5 的 Mean IC 与 incremental IC。
- 预期影响: 只影响对数精度与偏差计算，不影响模型排序和实验市场结论。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS20] 固定因子集用于主测试，首次可用月只做覆盖审计
- 来源: A14（auto 裁决）
- 性质: auto-resolution
- 假设内容: 本地主测试在共同起点前冻结一套固定因子集并贯穿样本外；按首次非缺失月形成的“当时可用因子集”只用于 R23/SA13 覆盖审计，不参与主配置结果。
- 行业惯例依据: spec 强调 fixed input set，发表年份表更符合独立的数据可用性审计而非主策略动态筛选。
- 影响面: method
- 影响 milestone: m1, m5
- 影响指标: R4-R6、R11、R21-R23、SA12-SA13。
- 预期影响: 固定因子集保留原研究结构，但在本地早期月份可能减少共同有效因子或缩短共同样本。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS21] 元数据采用主文作者且机构写未注明
- 来源: A15（auto 裁决）
- 性质: auto-resolution
- 假设内容: plan frontmatter 与最终报告使用主文作者 Nima Taheri Hosseinkhani；附录 Anonymous Author(s) 视为盲审遗留；institution 保持“未注明”。
- 行业惯例依据: 正式主文封面署名优先于附录匿名模板，缺失机构不得猜测。
- 影响面: output
- 影响 milestone: 无（frontmatter 元数据）
- 影响指标: 无，仅影响文档元数据。
- 预期影响: 不影响任何策略、回测或验证结论。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: -

### [AS22] 毛收益为主并采用单边换手与成本敏感性
- 来源: A16（auto 裁决）
- 性质: auto-resolution
- 假设内容: 原文未说明成本，主表先报告毛收益；换手定义为 \(0.5\sum_i|w_{i,t}-w_{i,t-1}^{drift}|\) 的单边口径，并额外报告 10 bps 与 30 bps 单边成本后的净收益，成本只在 T+1 实际成交权重上计提。
- 行业惯例依据: 未披露费率的学术组合通常以毛收益为基准；半周转是可与买入规模对应的常用单边换手定义。
- 影响面: trading
- 影响 milestone: m2, m4
- 影响指标: R2、R16-R17 的收益、alpha、换手、Sharpe 与回撤。
- 预期影响: 若原文 Turnover 为双边口径，本地数值约为其一半；净收益会随集中权重变化显著。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS23] A股样本采用历史可交易性过滤且不填造退市收益
- 来源: A17（auto 裁决）
- 性质: auto-resolution
- 假设内容: 母样本按当时已有行情和 `list_date` 构造，要求上市至少 120 个交易日、价格与流通市值为正；执行日剔除 ST、停牌和无法买入/卖出的涨跌停股票。数据目录没有退市收益字段时，不填造退市收益，最后可得价后停止并单列覆盖风险。
- 行业惯例依据: A股因子回测需按时点过滤 ST、停牌、涨跌停和新股；缺失退市收益时应披露限制而非假定为零或任意损失。
- 影响面: trading
- 影响 milestone: m1, m2, m3
- 影响指标: R2、R4-R9、R12、R16、R19-R24 的样本数、收益、容量和换手。
- 预期影响: 与原美股 common-stock 样本不同；过滤规则和退市覆盖可能造成微盘与流动性机制偏差。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS24] 四专家与验证 Sharpe softmax 作为 MoE 方法级降级基准
- 来源: A1（用户于 2026-07-26 授权检索公开资料并采用透明固定口径的方法级降级）
- 性质: method-degraded
- 假设内容: 本地 MoE 固定为四专家：E0 八家族等权；E1 用训练历史家族年化 Sharpe；E2 用训练历史 \(\sqrt{12}\overline{IC}/s(IC)\)；E3 用当前八块 high/low 状态对应的训练历史下一月家族平均收益等权汇总后除以家族收益标准差。E1-E3 分数均截断到 \([-3,3]\) 并以温度 1 做 family softmax。四专家在固定 144 月验证期逐月只读历史产生收益，验证年化 Sharpe 截断到 \([-3,3]\) 后再以温度 1 softmax 得门控权重；预测年前冻结门控、历史统计量和状态收益表 12 个月，年内仅 E3 随当期状态切换。标准差为零或有效观察不足 24 月的专家分数记 0。
- 行业惯例依据: Jacobs、Jordan、Nowlan、Hinton（1991）原始 MoE 论文 DOI `10.1162/neco.1991.3.1.79` 与 Hinton 作者页 `https://www.cs.toronto.edu/~hinton/mixex.html`（访问日期 2026-07-26）支持“专家输出加门控组合”的方法类别；四专家、截断、温度和验证 Sharpe 门控均为本计划固定选择，不是原文事实。截至访问日未找到作者实现或 empirical package。
- 影响面: method
- 影响 milestone: m4
- 影响指标: F4-F8、R1-R3、R13、R15、R17-R18、SA1-SA3 的家族权重、配置收益、消融与分布。
- 预期影响: 专家集合与门控口径会直接改变权重路径和配置收益；验证月不足 120、时间穿越、非有限/负权重或权重和误差超过 \(10^{-10}\) 时该预测年度判方法失败。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS25] Expanding z-score、块内等权、12 月半衰 EWMA 与 expanding median 作为宏观状态方法级降级基准
- 来源: A2（用户于 2026-07-26 授权检索公开资料并采用透明固定口径的方法级降级）
- 性质: method-degraded
- 假设内容: 对完成 AS16 时点处理的每个宏观变量使用 `ddof=1, min_periods=36` 的 expanding z-score 并截断至 \([-3,3]\)；同一经济序列优先 `macro_cache`、缺失才取明细表且不重复计权。每块对当月有效 z-score 等权，随后固定用 `ewm(halflife=12, adjust=False, min_periods=12)`；high/low 阈值取截至 \(t-1\) 的记忆值 expanding median（至少 36 个历史记忆值），严格大于阈值为 high，否则为 low。块内有效冻结序列少于一半、历史不足或零方差时该块当月缺失，不用未来值补齐。
- 行业惯例依据: pandas 3.0.5 官方 `DataFrame.ewm` 文档 `https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.ewm.html`（访问日期 2026-07-26）固定 EWMA API 语义；36 月暖启动、块内等权、12 月半衰和历史中位数均为透明基准，不是原文参数。截至访问日未找到作者实现或 empirical package。
- 影响面: method
- 影响 milestone: m1, m3, m4, m5
- 影响指标: F3-F7、F11、F15、R1-R3、R7-R10、R12、R14-R15、R17-R20、R22、R24 及相关 SA。
- 预期影响: 变换、记忆速度和阈值会改变状态持续性与 payoff surface；任一预测月不能形成八块完整状态时该月主配置结果不生成并计入覆盖失败。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS26] 固定关键词一对一映射作为八家族交叉表的方法级降级基准
- 来源: A3（用户于 2026-07-26 授权检索公开资料并采用透明固定口径的方法级降级）
- 性质: method-degraded
- 假设内容: 将 `level1`、`level2`、`factor_id_cn`、`factor_id` 规范化后依次匹配 plan.md §1.2.1 的冻结关键词字典，字段优先级为 `level1 > level2 > factor_id_cn > factor_id`；同字段多命中取最长关键词，再同长时按 Valuation、Continuation、Correction、Profitability/quality、Investment/issuance、Safety/downside、Liquidity/limits、Expectations 固定顺序裁决。未命中因子不进入袖套；交叉表、关键词配置、命中轨迹和 SHA-256 在全部预测年度冻结，禁止依据收益回看改词典。
- 行业惯例依据: Open Source Asset Pricing 官网 `https://www.openassetpricing.com/` 与官方仓库 commit `8db892442c2c3a3779b0f1eac4370d3655be15a1` 的 `SignalDoc.csv`（访问日期 2026-07-26）以 `Cat.Economic`/`Sign` 提供透明经济分类和方向元数据锚点；本地关键词及归属不等于原文 212 信号固定映射。截至访问日未找到作者实现或 empirical package。
- 影响面: method
- 影响 milestone: m1, m2, m4, m5
- 影响指标: D4、F2、F9 以及全部家族袖套、配置权重、层级信号与家族机制结果。
- 预期影响: 本地元数据文本会使家族数量与原文不同；任一家族为零、一个 `factor_id` 多重归属、哈希在预测期变化或映射无法重复生成时判方法失败。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto

### [AS27] 标准化 pooled ridge、九档 alpha 与第二层残差 ridge 作为股票模型方法级降级基准
- 来源: A6（用户于 2026-07-26 授权检索公开资料并采用透明固定口径的方法级降级）
- 性质: method-degraded
- 假设内容: 目标为 T+1 个股收益减当月截面等权收益并按月 1%/99% 缩尾；连续特征以训练样本中位数填充、用训练期 `StandardScaler` 标准化并删除常数列。第一层 pooled ridge 和第二层 residual ridge 均使用 \(\{10^{-4},10^{-3},10^{-2},10^{-1},1,10,10^2,10^3,10^4\}\) 九档 alpha。第二层目标是不与本观测同折训练的第一层残差，特征为八个 AS25 宏观记忆值及“八家族平均因子分数 × 八宏观记忆值”的 64 个交互项。先以验证期月均 Pearson IC 选第一层 alpha，再以最终组合 IC 选第二层 alpha，并列取较大 alpha；预测年前用当时训练+验证数据重拟合全部变换器和系数并冻结 12 个月。
- 行业惯例依据: scikit-learn 1.9.0 官方 `Ridge`、`StandardScaler`、`TimeSeriesSplit` 文档 `https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html`、`https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html`、`https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html`（访问日期 2026-07-26）固定 L2 目标、训练期缩放与时序隔离的 API 语义；目标、网格与第二层结构为本计划选择，不是原文事实。截至访问日未找到作者实现或 empirical package。
- 影响面: method
- 影响 milestone: m5
- 影响指标: F10-F11、R5-R6、R11、R21-R22、SA12 的 IC、alpha、模型排名和局部可靠性。
- 预期影响: 目标变换、alpha 网格和两层交互结构会改变股票层预测；有效验证月不足 120、预测期进入拟合/变换、两层均无有限预测或样本外 IC 无法计算时该预测年度判方法失败。
- 验证后回看: [verify 后填]
- 状态: assumed
- 高亮等级: major-auto
