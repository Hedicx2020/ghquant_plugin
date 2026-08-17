# 歧义清单

### [A1] Mixture-of-experts 计算公式与候选专家未给出
- 页码: p12-p13
- 原文: > "The main allocation rule is a mixture-of-experts design."
- 关联要素: F4, F5, F8
- 等级: blocking
- 候选解释: 1. 仅按正文概念描述，无法确定公式 2. 公式、候选专家及超参数存在于未附 empirical package
- 裁决方式: 人工（用户于 2026-07-26 授权公开检索与方法级降级）
- 裁决结果: 采用用户授权的方法级降级：固定 E0 等权、E1 训练历史收益 Sharpe、E2 训练历史 IC、E3 宏观状态条件收益四专家；专家分数与 144 月验证 Sharpe 均截断到 \([-3,3]\)，温度 1 softmax 门控，预测年前冻结 12 个月；登记 AS24。该规则不得写成原文事实。
- 裁决依据: Jacobs et al. (1991) 原始论文 DOI `10.1162/neco.1991.3.1.79` 与 Hinton 作者页 `https://www.cs.toronto.edu/~hinton/mixex.html`（访问日期 2026-07-26）支持“专家+门控”方法类别；截至访问日未找到作者实现或 empirical package，四专家和门控参数是用户授权的透明固定基准。
- 状态: resolved

### [A2] 宏观状态的变换、聚合与 high/low 切分未说明
- 页码: p11-p13, p34-p35, p53
- 原文: > "Each macro block is used to form state histories"
- 关联要素: F3-F7, F15, R7-R8, R19, SA4
- 等级: blocking
- 候选解释: 1. 按块内变量聚合后分位切分 2. 每个变量先形成状态再由规则组合；PDF 未给占优解释
- 裁决方式: 人工（用户于 2026-07-26 授权公开检索与方法级降级）
- 裁决结果: 采用用户授权的方法级降级：变量用 `ddof=1, min_periods=36` 的 expanding z-score 并截断 \([-3,3]\)，块内等权，pandas `ewm(halflife=12, adjust=False, min_periods=12)`，high/low 以截至 \(t-1\) 的 expanding median 切分；登记 AS25，并保留 AS5、AS7 的市场迁移数据假设。该规则不得写成原文事实。
- 裁决依据: pandas 3.0.5 官方 `DataFrame.ewm` 文档 `https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.ewm.html`（访问日期 2026-07-26）固定 EWMA API 语义；截至访问日未找到作者实现或 empirical package，36 月暖启动、块内等权、12 月半衰与历史中位数是用户授权的透明固定基准。
- 状态: resolved

### [A3] 212 个信号逐一对应家族的映射缺失
- 页码: p10-p11, p54
- 原文: > "The family mapping is fixed before the allocation tests."
- 关联要素: D4, F2, F9
- 等级: blocking
- 候选解释: 1. 采用未附 empirical package 中的固定映射 2. 仅凭表 IA.3 的家族计数无法恢复逐信号映射
- 裁决方式: 人工（用户于 2026-07-26 授权公开检索与方法级降级）
- 裁决结果: 采用用户授权的方法级降级：对本地 `level1/level2/factor_id_cn/factor_id` 按 AS26 的冻结关键词字典、字段优先级、最长词与固定家族顺序生成一对一映射，未命中因子排除，交叉表及配置冻结 SHA-256；同时保留 AS1、AS2、AS3 的市场迁移假设。该映射不得写成原文 212 信号映射事实。
- 裁决依据: Open Source Asset Pricing 官网 `https://www.openassetpricing.com/` 与官方仓库 commit `8db892442c2c3a3779b0f1eac4370d3655be15a1` 的 `SignalDoc.csv`（访问日期 2026-07-26）提供 `Cat.Economic`/`Sign` 分类锚点；截至访问日未找到作者实现或 empirical package，本地关键词交叉表是用户授权的透明固定基准。
- 状态: resolved

### [A4] 特征预处理与十分位组合形成细节未说明
- 页码: p10, p12, p29
- 原文: > "Long-short columns use decile portfolios"
- 关联要素: F1, F14, B10, B12
- 等级: major
- 候选解释: 1. 每月按信号横截面直接十分位排序 2. 先标准化或聚合后排序；PDF 未说明
- 裁决方式: auto
- 裁决结果: 采用每月因子横截面 1%/99% 缩尾、z-score、缺失样本剔除、当月有效样本十分位排序；高组减低组，T 月末计算、T+1 首个可交易日建仓并持有一月，同时报告 EW/VW；登记 AS11。
- 裁决依据: 直接月度横截面排序最贴近 spec 的 decile portfolios，且是缺少额外断点说明时可复算、无未来函数的常见口径。
- 状态: resolved

### [A5] 容量区域与 liquid proxy 的精确定义缺失
- 页码: p7, p19, p35-p36, p77
- 原文: > "middle-cap regions"
- 关联要素: D9, F15, B13, R8-R9, SA5, SA7
- 等级: major
- 候选解释: 1. 按当月全样本市值分位划区 2. 使用固定交易所断点；PDF 未说明
- 裁决方式: auto
- 裁决结果: 市场迁移数据采用A股流通市值/行业/beta/成交换手，登记 AS9；容量区域按每月合格样本的 T 时点流通市值分位，outside microcaps 排除 bottom 20%，liquid proxy 为成交额与自由流通换手率分位秩均值的上半样本，登记 AS12。
- 裁决依据: 当期横截面分位可直接对应 spec 的 bottom 20/middle 60/top 20/top 10 名称，且比把美国固定断点搬到A股更适合实验市场迁移。
- 状态: resolved

### [A6] Pooled ridge 与残差模型规格未给出
- 页码: p14, p16-p17, p32, p38
- 原文: > "allows shrinkage"
- 关联要素: F10, F11, R5, R11, SA12
- 等级: blocking
- 候选解释: 1. 线性 ridge 以验证窗选惩罚项 2. 其他标准化、目标与正则网格来自未附 empirical package
- 裁决方式: 人工（用户于 2026-07-26 授权公开检索与方法级降级）
- 裁决结果: 采用用户授权的方法级降级：训练期中位数填充与 `StandardScaler`，第一层 pooled ridge 和第二层宏观残差 ridge 均用 \(\{10^{-4},\ldots,10^4\}\) 九档 decade alpha，按验证 IC 依次选择并列取较大 alpha，预测年前重拟合并冻结 12 个月；登记 AS27。该规格不得写成原文事实。
- 裁决依据: scikit-learn 1.9.0 官方 `Ridge`、`StandardScaler`、`TimeSeriesSplit` 文档（`https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html`、`https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.StandardScaler.html`、`https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html`，访问日期 2026-07-26）固定模型与时序隔离 API 语义；截至访问日未找到作者实现或 empirical package，目标、网格与残差层结构是用户授权的透明固定基准。
- 状态: resolved

### [A7] IC、Fama–MacBeth 与 Newey–West 的统计口径不全
- 页码: p12, p29, p31-p33, p70
- 原文: > "Newey–West inference is monthly."
- 关联要素: F12, F13, B9, R4-R6
- 等级: major
- 候选解释: 1. IC 为月度 Pearson 相关 2. IC 为月度 rank IC；PDF 没有明确区分
- 裁决方式: auto
- 裁决结果: 美国 FF5+MOM 替换为A股本地六控制组合并登记 AS8；主 IC 采用 Pearson、附 Spearman 敏感性，FMB 控制 log 流通市值/log 账面市值比/12-1 动量/历史 beta，NW 主滞后 6 月并报告 3/12 月敏感性，登记 AS13。
- 裁决依据: IC 的线性预测语境支持 Pearson 主口径；显式给出本地控制与多组 HAC 滞后可使不完整统计口径可复算、可扰动验证。
- 状态: resolved

### [A8] 主表 4 两列相关系数在 PDF 中为空
- 页码: p30
- 原文: > "Trend corr. Valuation corr."
- 关联要素: R3, SA2
- 等级: minor
- 候选解释: 1. 原稿排版漏值 2. 作者有意不报告；PDF 无法区分
- 裁决方式: auto
- 裁决结果: 原文两列保持 `n/a`，不从其他统计量推算；本地若另算相关系数须标为实验复现新增指标，登记 AS14。
- 裁决依据: spec 已将空列登记为 n/a；保留空值比无依据补数更忠实。
- 状态: resolved

### [A9] 表 IA.10 在 PDF 中没有表体
- 页码: p63
- 原文: > "Table IA.10. Family Weight Distribution by Macro State"
- 关联要素: SA2
- 等级: major
- 候选解释: 1. 原稿生成时漏出数据 2. 数据仅存在于未附 empirical package
- 裁决方式: auto
- 裁决结果: Table IA.10 单表标为 `skip: method_underspecified`，不推算表体；SA2 由其他已登记权重表和图完成，登记 AS15。
- 裁决依据: spec 明确表体为空，无法唯一恢复；跳过单表不等于跳过 SA2 的其他可验证内容。
- 状态: resolved

### [A10] “0 months”与保守 vintage 的具体发布时间处理不明
- 页码: p11-p12, p28, p53, p55
- 原文: > "Max timing lag Economic role"
- 关联要素: D5-D7, B7, R14, SA11
- 等级: major
- 候选解释: 1. 月末可观察即当月使用 2. 以实际发布日期或保守 vintage 对齐；各系列可能不同
- 裁决方式: auto
- 裁决结果: ALFRED vintage 替换为固定保守滞后并登记 AS6；月度宏观值至少滞后一个月、季度值滞后四个月，缺失只向后沿用最近已发布值，T 信号在 T+1 执行，登记 AS16。
- 裁决依据: 本地目录无逐期发布日期/vintage；统一保守滞后可审计并优先防止未来函数，优于把“0 months”解释为同月可用。
- 状态: resolved

### [A11] 留出期状态月数极不平衡且选择规则未说明
- 页码: p39, p91
- 原文: > "Confirmation period, 2005 onward"
- 关联要素: B14, R12, SA8
- 等级: major
- 候选解释: 1. 按形成期冻结阈值导致确认期状态不平衡 2. 状态筛选另有规则；PDF 未说明
- 裁决方式: auto
- 裁决结果: 采用候选 1：在形成期估计并冻结状态阈值与收益差方向，确认期不为平衡月数而重估；本地切点由共同样本前后时序固化，登记 AS17。
- 裁决依据: 该解释直接符合 spec“沿用形成期所学方向”和预设 holdout 的定义，也能解释确认期状态数不平衡。
- 状态: resolved

### [A12] Crisis 与命名事件的精确起止月份未列出
- 页码: p77-p78, p104
- 原文: > "excluding named market episodes one at a time"
- 关联要素: B15, R20, R24, SA6, SA14
- 等级: major
- 候选解释: 1. 使用事件名称对应自然月 2. 使用 empirical package 中预设窗口；PDF 未给日期
- 裁决方式: auto
- 裁决结果: 按透明自然窗口剔除：1987 全年、1998 全年、2000–2002、2007–2009、2011 全年、2018Q4、2020 全年、2021 全年、2022 全年；本地样本前事件不替换为未命名中国事件，登记 AS18。
- 裁决依据: spec 只稳定给出年份/年份范围，完整自然年或明确季度无需依据事后价格路径选窗口；若迭代归因指向该项再切核心月口径。
- 状态: resolved

### [A13] 正文精确 IC 与主表两位小数展示不一致
- 页码: p16-p17, p31-p32
- 原文: > "mean hierarchical IC of 0.0508"
- 关联要素: R4, R5
- 等级: minor
- 候选解释: 1. 主表仅展示两位小数、正文为精确值 2. 表与正文来自不同输出精度
- 裁决方式: auto
- 裁决结果: 对数以正文更多有效位数为精确基准，表格两位小数视为展示舍入，登记 AS19。
- 裁决依据: 同一规格中正文值与表格值在四舍五入后相容，正文提供的有效位更多。
- 状态: resolved

### [A14] 全 212 固定面板与发表年份可用面板的用途边界
- 页码: p10, p102-p103
- 原文: > "publication-year coverage audit for the fixed 212-signal input set"
- 关联要素: D10, F16, R23, SA13
- 等级: major
- 候选解释: 1. 主测试始终使用固定 212，发表覆盖仅审计 2. 某些附加测试按发表年份筛选
- 裁决方式: auto
- 裁决结果: 本地发表年份替代为因子首次非缺失月并仅作覆盖审计，登记 AS10；主测试始终使用共同起点前冻结的固定本地因子集，登记 AS20。
- 裁决依据: spec 明确称 fixed input set 和 publication-year coverage audit，候选 1 为占优解释。
- 状态: resolved

### [A15] 主文与附录作者署名不一致，机构未注明
- 页码: p1, p51
- 原文: > "Anonymous Author(s)"
- 关联要素: 无
- 等级: minor
- 候选解释: 1. 主文作者名为最终署名 2. 附录匿名页为盲审版遗留
- 裁决方式: auto
- 裁决结果: frontmatter 采用主文作者 Nima Taheri Hosseinkhani，附录匿名署名视为盲审遗留；institution 保持“未注明”，登记 AS21。
- 裁决依据: 主文正式封面署名优先于附录匿名模板；spec 没有机构信息，禁止猜测。
- 状态: resolved

### [A16] 交易成本与 Turnover 定义未说明
- 页码: p19, p60
- 原文: > "the average monthly turnover is 0.610"
- 关联要素: F14, R16
- 等级: major
- 候选解释: 1. 收益未扣交易成本 2. 成本处理存在于 empirical package；PDF 未说明
- 裁决方式: auto
- 裁决结果: 主结果报告毛收益；Turnover 采用 \(0.5\sum|w_t-w_{t-1}^{drift}|\) 单边口径，并补充 10/30 bps 单边成本净收益敏感性，登记 AS22。
- 裁决依据: 未披露成本的学术组合通常以毛收益呈现，半周转是可复算的常见单边定义；成本敏感性暴露口径影响而不改写原文。
- 状态: resolved

### [A17] 股票样本过滤、退市收益与微盘定义未说明
- 页码: p10-p12, p18-p19
- 原文: > "The unit of observation is the stock-month."
- 关联要素: D2, D9, B10-B13
- 等级: major
- 候选解释: 1. 沿用 Chen–Zimmermann/OpenAP 项目样本 2. empirical package 另有筛选
- 裁决方式: auto
- 裁决结果: 原美股股票月替换为本地可用期A股历史面板，登记 AS4；按当时行情/list_date 构造母样本，上市满 120 个交易日、价格和流通市值为正，执行日剔除 ST/停牌/无法交易涨跌停；无退市收益字段时不填造并披露覆盖风险，登记 AS23。
- 裁决依据: 所用字段与状态事件均由 data_catalog 明示，且按历史时点过滤可降低幸存者偏差和不可交易偏差。
- 状态: resolved
