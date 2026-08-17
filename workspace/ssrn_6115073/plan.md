---
report_name: ssrn_6115073
title: Online Portfolio Selection Using Macroeconomic Pattern Matching
institution: University of Southampton / University of Adelaide
date: 2025-01-01
type: allocation
tags: [ml, factor]
difficulty: hard
feasibility: degraded
template: templates/allocation.md
spec_ref: workspace/ssrn_6115073/spec/spec.md
reproduction_mode: experimental   # 市场迁移复现：原文美股+日股+FRED 全不可得 → 迁移中国 A 股；成功判据=方法是否成立，非数值对齐
data_requirements:
  - name: 三宽基时点成分股清单（沪深300/上证50/中证500）
    source: ashare_index_components
    status: substitute   # 原文 S&P500/DJI/N225 成分股(Refinitiv) → A股三宽基成分股
  - name: 成分股前复权日行情（聚合月频收益）
    source: ashare_stock_price_forward
    status: substitute   # 原文三海外指数成分股日频行情(Refinitiv) → A股前复权行情
  - name: 状态过滤（ST/停牌/涨跌停/上市日）
    source: ashare_stock_st / ashare_stock_suspend / ashare_stock_limit / ashare_stock
    status: available    # A股迁移新增，防未来函数与不可交易样本（原文无此层）
  - name: 三宽基指数点位序列（Index 基准 + Modigliani σ_b）
    source: ashare_csiindex_trade
    status: substitute   # 原文三海外指数点位 → A股三宽基指数点位
  - name: 宏观 CPI（居民消费价格）
    source: macro_cpi / macro_cache(cpi_yoy)
    status: substitute   # 原文 FRED CPI → 中国 CPI
  - name: 宏观 PPI（工业品出厂价格）
    source: macro_ppi / macro_cache(ppi_yoy)
    status: substitute   # 原文 FRED PPI → 中国 PPI
  - name: 宏观 GDP
    source: macro_gdp / macro_cache(gdp_real_yoy)
    status: substitute   # 原文 FRED GDP → 中国 GDP（季频插值到月频）
  - name: 宏观 IP（工业生产/规上工业增加值）
    source: macro_industrial_production
    status: substitute   # 原文 FRED Industrial Production → 中国规上工业增加值
  - name: 宏观 IR（利率）
    source: macro_cache(bond_yield_10y) / macro_lpr / bond_shibor
    status: substitute   # 原文 FRED Interest Rate → 中国 10Y 国债收益率（备 LPR/SHIBOR）
  - name: 宏观候选池补充（M2 / PMI / 社融）
    source: macro_money_supply / macro_pmi / macro_social_financing
    status: substitute   # 迁移用中国可得宏观候选池重跑 BorutaShap（原文 18 候选 → 中国约 9 候选，降维）
  - name: 宏观 DGDP（债务/GDP）
    source: macro_social_financing + macro_gdp（社融存量/GDP 杠杆率代理）
    status: substitute   # 原文 FRED Debt-to-GDP 无直接等价 → 宏观杠杆率代理（口径差异，AS31）
  - name: 宏观 UR（失业率）
    source: 无本地等价
    status: missing      # 中国城镇调查失业率本地不可得；不强代理，据实降维（AS30），是判 degraded 的直接依据
  - name: 无风险利率 rf（SR/Sortino/Modigliani 用）
    source: bond_shibor(3M) / bond_yield_curve
    status: substitute   # 原文各市场短端利率 → 中国 3M SHIBOR（月频折算，AS19/AS32）
  - name: 交易日历/月末标记
    source: ashare_tradeday
    status: available
milestones:
  - id: m1
    name: 市场迁移数据映射与宏观因子准备
    desc: 建立 A股股票池（时点成分股）、中国宏观因子候选池与 BorutaShap 重选、rf/指数基准，划定 A股训练/测试区间；产出对齐面板供下游全链复用
    deps: []
    elements: [D1, D2, D3, D4, B1, B2, F12]
  - id: m2
    name: Δβ 双区制 OLS 宏观敏感选股
    desc: 对每只候选股票、每个宏观因子做 X>0/X<0 双区制 OLS 估 β+/β−，算 Δβ=β+−β−，按 |Δβ| 排序取显著头部股票入候选集；产出 β 表（对齐 R3）
    deps: [m1]
    elements: [F2, R3]
  - id: m3
    name: 资产聚类分组（SU + 层次聚类 + Silhouette）
    desc: 用对称不确定性 SU（含 MI）度量资产关系，凝聚层次聚类分组，Silhouette 定簇数 nc；对比四聚类模型×两度量选 hierarchical+SU（对齐 R2/表1）
    deps: [m2]
    elements: [F3, F4, R2]
  - id: m4
    name: 两阶段 Matrix Profile 模式匹配与信号
    desc: 训练期用相关性+MSE 定最优窗口 w/nc；测试期两阶段 Matrix Profile——先在宏观因子上找相似经济周期，再在匹配周期内找相似价格窗口，产 ±1 二值信号
    deps: [m2]
    elements: [F5, F6, F7, F8]
  - id: m5
    name: Diebold-Yilmaz 溢出加权与每簇选股
    desc: VAR 广义方差分解算宏观→资产净波动溢出，min-max 归一化为权重；FS_j=Σγ̃·signal 聚合各宏观因子信号，每簇选 FS 最高资产入最终组合（对齐 R4/表6）
    deps: [m3, m4]
    elements: [F9, F10, R4]
  - id: m6
    name: 组合构建（EW/MV）与回测评估
    desc: 每簇选出的资产按等权 EW 与均值方差 MV 建仓，OLPS 序贯月度调仓；算 AR/AStd/SR/PSR/SOR/MR/MDD/VaR，与 A股宽基基准及 HRP/HERC/OLMAR/NCO 对比（对齐 R1/R5）
    deps: [m5]
    elements: [F1, F11, B5, B6, B7, B8, R1, R5]
  - id: m7
    name: 稳健性与敏感性分析
    desc: 滚动 4 年子区间稳健性、样本外区间、参数敏感性（nc/w/λ）、单宏观因子纳入/剔除敏感性（对齐 SA1/SA2/SA3/SA4）
    deps: [m6]
    elements: [B3, B4, SA1, SA2, SA3, SA4]
---

# Online Portfolio Selection Using Macroeconomic Pattern Matching 复现开发计划

> 本计划为**实验模式（experimental / 市场迁移复现）**：原文美股 S&P500/DJI + 日股 N225 + FRED 美国宏观不可本地获取，用 A股宽基 + 中国宏观等价替代。复现目标是**方法在迁移市场（A股）是否成立**（效应延续/衰减/失效），**数值对齐原文整体豁免**，不追平原文 Sharpe。所有研报要素权威来源为 spec.md，本文件不重复抄录 R 类数值。

## 研报信息
- 标题：Online Portfolio Selection Using Macroeconomic Pattern Matching（SSRN 预印本 abstract=6115073，未经同行评审）
- 来源机构：University of Southampton（Southampton Business School）/ University of Adelaide
- 发布日期：2025-01-01（封面无日期，据 2025 引文与样本外区间推断，见 AS18）
- 作者：Seyed Mehrzad Asaad Sajadi、Sasan Barak（通讯）、Ali Fereydooni
- 适用市场：原文=美股 S&P500/DJI + 日股 N225（多市场股票）；**迁移目标=A股（沪深300 主 + 上证50 + 中证500）**

## 〇、复现模式声明（experimental / 市场迁移）

原文三个股票市场成分股行情（Refinitiv）与 18 个宏观候选因子（FRED）本地**全部不可得**（data_catalog 明列海外个股财务/宏观为缺口）。因此：
1. **复现目标从「数值对齐原文」改为「方法在 A 股是否成立」**：R 类基准表（表2/表4/表6）与 SA 类改作**定性方法验证**参照，不追平数字。
2. 原文不可得数据一律 `status: substitute` 等价替代，每个替代登记一条 `market-transplant` 假设（AS28–AS34，rf 另见 AS19）。
3. 歧义裁决时「能否对上原文数值」权重降低，优先「方法论最标准 + 迁移 A 股最可落地」。
4. A 股无卖空 + 单纯形约束 b_t≥0（F1）→ A17 长仓解释天然成立，方法与 A 股实操契合。

## 一、核心策略与创新点

### 1.1 研究背景与核心思想
把宏观经济状态融入在线组合选择（OLPS）：不再对全市场无差别配置，而是「先选对宏观非对称敏感的股票 → 按信息相似度聚类去冗余 → 用历史相似经济周期做模式匹配预测 → 按宏观对市场的波动溢出强度加权聚合信号 → 建仓」。核心创新是把**宏观 pattern matching**（找相似经济周期）与**价格 pattern matching**（找相似价格窗口）两级串联，并用 Diebold-Yilmaz 溢出而非简单等权来加权不同宏观因子的信号。

### 1.2 策略构造（四步，关键公式）
1. **Δβ 双区制选股（F2）**：对宏观变量 X，按 X>0 估 `y=α+β⁺x+ε`、X<0 估 `y=α+β⁻x+ε`，`Δβ=β⁺−β⁻`；仅保留两系数统计显著者，按 |Δβ| 取头部（宏观非对称敏感股票）。
2. **SU + 层次聚类分组（F3/F4）**：`MI[X,Y]=H[X]+H[Y]−H[X,Y]`，`SU=2·MI/(H[X]+H[Y])∈[0,1]`；凝聚层次聚类，Silhouette（式D.4）定簇数 nc，每簇代表一类信息相似资产。
3. **两阶段 Matrix Profile（F5/F6/F7/F8）**：训练期用相关性+MSE 在 w∈{2..10} 定最优窗口 w 与子簇 nc（Remark 2，见 AS7）；测试期先对宏观因子各自把「最近一年」与历史比 `MSP′=min[SP]`（式24）找最相似经济周期 EP，再在该周期内对每只资产用窗口 w 找最相似价格窗口，预测 `r̂_{n+1}` = 该历史窗口之后一期实际收益；`signal={+1 if r̂>0; −1 if r̂≤0}`（式27）。
4. **溢出加权聚合 + 建仓（F9/F10/F11）**：VAR(p) → 广义方差分解 → 净溢出 `S^g_i(U)=S^g_{.i}−S^g_{i.}`（式35）；min-max 归一化 `γ̃`（式36）；`FS_j=Σᵢγ̃_{i,j}·signal_{i,j}`（式37）；每簇选 FS 最高资产，EW/MV 建仓，OLPS 序贯 `S_n=S0·Πₜ bₜᵀVₜ`（式4）。

### 1.3 创新点
相对基准 OLPS（CRP/OLMAR）与聚类配置（HRP/HERC/NCO），本文引入「宏观周期匹配 → 价格窗口匹配」双级 pattern matching + 溢出加权。消融链 CPMM（全量）→ CPM（去宏观）→ PMM（去聚类）→ EWMFM（去溢出）验证各环节增量——**该相对关系是迁移复现的核心验证对象**。

## 二、回测参数（市场迁移后，复现对齐用）
- **回测区间**：A股约 2007-01 至 2024-12（沪深300 成分与宏观序列稳定后）；训练 2007-2018 定 w/nc，测试 2019-2024（AS6/AS34；coder 于 m1 据实际首末可得日微调）
- **标的池**：沪深300（000300，主分析，对标 S&P500）+ 上证50（000016，对标 DJI）+ 中证500（000905，对标 N225），**时点成分股**动态进出、前复权（AS8/AS28）
- **基准**：对应宽基指数买入持有（Index）+ HRP / HERC / OLMAR / NCO（B8）
- **宏观因子**：中国 CPI/PPI/GDP/工业增加值/利率(国债或 LPR)/M2/PMI/社融 候选池，BorutaShap 重选（AS16/AS29；UR 无干净等价物降维 AS30、DGDP→社融杠杆率代理 AS31）
- **调仓频率**：月度（AS4）；信号 T 月末算、T+1 月执行；A股需过滤停牌/涨跌停/ST（data_catalog 状态过滤表）
- **费率**：主回测无摩擦（对齐原文两条市场假设）+ 含 A股双边成本一档稳健性（AS5）
- **rf**：SHIBOR 3M 或短端国债按月折算（AS19/AS32）
> 类型特化参数清单见 templates/allocation.md。

## 三、研报核心结果（验证基准）
> 数值/原文/页码以 spec.md「五、R 类」为唯一真相源，本节只列覆盖关系。**市场迁移下数值对齐豁免**，R 表用于对照方法的定性表现（排序、正负、量级），非追平数字。

| R 要素ID | 一句话摘要 | 关联 milestone | 迁移验证方式 |
|----------|-----------|---------------|-------------|
| R1 | 表2 六比率×11 方法×3 市场（主结果，CPMM-EW 领先） | m6 | 定性：CPMM-EW 是否领先基准与消融模型 |
| R2 | 表1 聚类模型对比（hierarchical+SU/correlation 占优） | m3 | 定性：hierarchical+SU 是否在 SR/分散化占优 |
| R3 | 表4 β+/β−/Δβ×11 方法（提出模型 Δβ 更大、下行更抗跌） | m2 | 定性：CPMM 系列 Δβ 是否为正（下行保护） |
| R4 | 表6 各宏观因子波动溢出强度均值（CPI 最强） | m5 | 定性：CPI/利率是否为 A股最强溢出因子 |
| R5 | 图9-10 累计收益（CPMM-EW≈110%，近似定性） | m6 | 定性：CPMM-EW/MV 累计收益是否领先 |

## 四、市场迁移数据映射（experimental 专节）

> 原文数据整体不可本地获取，逐项用 A股/中国宏观等价替代，每项登记一条 assumptions（性质 market-transplant）。

| 原文数据 | 本地等价替代 | 状态 | 关联 AS |
|---------|-------------|------|--------|
| S&P500 成分股（Refinitiv，主分析） | 沪深300（000300）时点成分股，前复权 | substitute | AS28 |
| Dow Jones 成分股（大盘蓝筹） | 上证50（000016）时点成分股 | substitute | AS28 |
| Nikkei225 成分股（日股，第三市场） | 中证500（000905）时点成分股 | substitute | AS28 |
| FRED CPI | macro_cpi（cpi_yoy 月度同比） | substitute | AS29 |
| FRED PPI | macro_ppi（ppi_yoy 月度同比） | substitute | AS29 |
| FRED GDP | macro_gdp（季频，插值/前值对齐到月频） | substitute | AS29 |
| FRED IP（工业生产） | macro_industrial_production（工业增加值） | substitute | AS29 |
| FRED IR（利率） | macro_cache.bond_yield_10y（备 LPR/SHIBOR） | substitute | AS29 |
| （候选池补充） | macro_money_supply(m2_yoy)、macro_pmi、macro_social_financing 入候选池 | substitute | AS29 |
| FRED UR（失业率） | **本地无干净等价物 → 据实降维剔除**（不用 PMI 强代理，避免虚构方向） | **missing** | AS30 |
| FRED DGDP（债务/GDP） | 社融存量/GDP 杠杆率代理（口径差异，登记风险） | substitute | AS31 |
| 美国 T-bill（rf） | bond_shibor 3M 或 bond_yield_curve 短端 | substitute | AS32 |
| 三大指数点位（Index 基准/σ_b） | ashare_csiindex_trade（对应宽基指数） | substitute | AS33 |
| 1995-2023（训练至 2018） | A股 2007-2024（训练 2007-2018/测试 2019-2024） | substitute | AS34 |

**迁移要点**：① 宏观因子集不套用原文美国 7 因子，用 BorutaShap 从**中国可得候选池**重选（AS16/AS29），忠实迁移「特征选择→宏观 pattern matching」方法而非因子名单——原文 18 候选在中国仅约 9 个可得，候选池本身已降维；② UR（失业率）中国本地无任何干净月频等价物，**据实降维剔除**（PMI 是景气指标，代理失业率口径差异过大，近似虚构方向，故不代理），DGDP 用社融存量/GDP 作宏观杠杆率代理（方向站得住但口径有别）——这两项是本迁移的实质降级点，verify 后需回看是否被数据支持；③ A股股票池用时点成分股防幸存者偏差，优于原文可能的当前成分回溯。

## 五、难度判定（据 _plan_template 难度判定表）
- **基准档 = hard**：方法链含训练模型（BorutaShap 的 RF/SHAP、四种聚类）+ 优化求解（MV Markowitz）+ 多资产联动（每簇选一构组合）+ VAR 广义方差分解（溢出）+ Matrix Profile —— 命中「训练模型/优化求解/多资产联动」hard 基准。
- **修正项**：（a）数据可得性：复现主线需**市场整体迁移 + 复杂衍生**（宏观映射/时点成分股重构/月频聚合）→ 本应上调，已 hard 封顶；（b）模块/因子数：F 类要素 12 个（≥8）且基准 ≥medium → 本应上调，已 hard 封顶。
- **easy 收口**：多修正项触发，非 easy。
- **结论：difficulty = hard**（含模型训练自动 ≥medium，此处直接 hard）。milestone 数 7（≥hard 下限 3）。

## 六、可行性判定（feasibility = degraded）
- 核心 data_requirement 替代后**主数据链完整可跑**：三宽基时点成分股行情（substitute）+ 主要宏观因子 CPI/PPI/IR/GDP/IP（substitute）+ rf（substitute）+ 指数序列（substitute），主方法链（Δβ→聚类→pattern matching→溢出加权→组合→OLPS）可完整复现，**故不判 blocked**。
- **降级点（判 degraded 而非 feasible 的理由）**：
  1. **宏观因子集降维**：原文 18 宏观候选在中国仅约 9 个可得；UR（失业率）本地完全无干净等价物 → `missing` 降维剔除；DGDP 用社融/GDP 粗代理（口径差异大）。核心因子 CPI/IR 可得，故降维不动摇主链，但属实质降级。
  2. **数值对齐整体豁免**（实验模式），R/SA 类改定性验证。
  3. SA5（ES）、SA6（TDA）迁移下意义降低 → skip（optional）。
- 以上均为「部分非核心数据 missing + 降级复现」，判 **degraded**，不触发主流程暂停。

## 七、方法复用规划（common/ 优先）
- **复用 common/utils.py**：`calculate_sharpe` / `calculate_max_drawdown` / `winsorize` / `standardize_factor`；PSR（式F.2 含偏度峰度）、Sortino（式F.3）、Modigliani（式F.4）、历史模拟 VaR（最低 5%）、Frobenius 分散化若 utils 无则新增到 common/utils.py（通用绩效指标，跨类型复用）。
- **复用 common/data_loader.py**：`load_market_data` / `get_stock_universe` / `filter_st_stocks` / `filter_suspended`；扩展指数时点成分股加载（ashare_index_components 按 in_date/out_date）。
- **新建 common/allocation_backtest.py**（首个 allocation 案例，按 templates/allocation.md 接口）：`mean_variance_weights(exp_ret, cov, bounds)`（MV 长仓，AS11）、`portfolio_backtest(weights_panel, asset_returns, cost_bps)`（EW/MV 序贯回测 + 换手/成本）、外部配置基准 `hrp_weights`/`herc_weights`/`nco_weights` 与 OLPS 基准 `olmar_weights`（通用算法，供后续同类复用，不写 src）。
- **策略特有 src/ssrn_6115073/**：`strategy.py`（Δβ 双区制选股、SU/MI 分箱估熵+层次聚类、两阶段 Matrix Profile 信号、Diebold-Yilmaz 溢出、FS 聚合选股）、`config.py`（区间/池/参数默认值集中）、`main.py`（串 m1→m6 全链）。
  - Matrix Profile 建议用 `stumpy`（Z-归一化欧氏 MP，left/right MP）；VAR 溢出用 `statsmodels` VAR + 广义方差分解自实现（Diebold-Yilmaz）；BorutaShap 用 `BorutaShap`/`shap`+`sklearn.RandomForest`。均为策略特有、放 src。

## 八、复现计划（按 milestone 拆分）

DAG（无环）：
```
m1 ─→ m2 ─┬─→ m3 ─┐
          └─→ m4 ─┴─→ m5 ─→ m6 ─→ m7
```
可并行：**m3（聚类）与 m4（pattern matching）均只依赖 m2，可并行**，在 m5 汇合（用簇标签 + 信号选每簇最强）。其余链式。hard 编排：无依赖并行 + 依赖链流水线重叠。

### m1: 市场迁移数据映射与宏观因子准备（deps: []）
- 内容：加载沪深300/上证50/中证500 时点成分股前复权行情（聚合月收益，剔除 ST/停牌/涨跌停/次新）；构建中国宏观候选池（CPI/PPI/GDP/IP/利率/M2/PMI/社融），统一到月频同比/变化口径（AS1）；BorutaShap 从候选池重选宏观因子集（AS16，退化=直接采用可得对应集）；加载 rf 与指数基准；划定训练/测试区间（AS34）。
- 依赖数据：D1/D2/D3/D4（UR 缺失降维）。产出：对齐的股票月收益面板、宏观因子面板、rf/指数序列、选定宏观因子清单。
- 验证点：面板无未来函数（宏观按发布对齐、时点成分股）、区间与频率一致、选出宏观因子集可解释。

### m2: Δβ 双区制 OLS 宏观敏感选股（deps: [m1]）
- 内容：对每（股票 i，宏观因子 j），X>0/X<0 双区制 OLS 估 β⁺/β⁻，算 Δβ；5% 显著性过滤（AS15），按 |Δβ| 排序取头部（无硬阈值，AS9）；月频对齐（AS1），设最小样本门槛剔除历史过短股票。
- 产出：β⁺/β⁻/Δβ 表（对齐 R3），候选股票集。验证点：Δβ 符号与量级合理，选股数量稳定。

### m3: 资产聚类分组（SU + 层次聚类 + Silhouette）（deps: [m2]）
- 内容：最近邻/分箱估熵算 MI/SU（AS20），凝聚层次聚类，Silhouette 定 nc（AS2）；对比四聚类模型（hierarchical/K-means/GMM/DBSCAN）× 两度量（SU/correlation），用 SR/MDD/VaR/Frobenius 选最优（对齐 R2/表1）。
- 产出：簇标签、聚类模型对比表。验证点：hierarchical+SU 是否在 A股同样占优（迁移的方法学检验点之一）。

### m4: 两阶段 Matrix Profile 模式匹配与信号（deps: [m2]）
- 内容：训练期用相关性+MSE 在 w∈{2..10}（月频步长）定最优 w/nc（Remark 2，AS7）；测试期阶段1 对宏观因子（m=最近一年/12 月，AS10）找相似经济周期，阶段2 在周期内用窗口 w 找相似价格窗口预测 r̂，二值化 ±1（式27）。
- 产出：每（资产,宏观因子）的 ±1 信号矩阵。验证点：pattern matching 命中相似期合理、信号非退化。

### m5: Diebold-Yilmaz 溢出加权与每簇选股（deps: [m3, m4]）
- 内容：VAR(p) 广义方差分解算宏观→资产净溢出（p 按 AIC，U=10，AS12）；min-max 归一化权重 γ̃；FS_j=Σγ̃·signal（式37）；每簇选 FS 最高资产（AS17，纯长仓不做空，FS≤0 剔除）。
- 产出：溢出强度表（对齐 R4/表6）、每簇选出的最终资产集。验证点：CPI/利率是否为 A股最强溢出因子（迁移检验点）。

### m6: 组合构建（EW/MV）与回测评估（deps: [m5]）
- 内容：选出资产按 EW 与 MV（Markowitz 长仓，λ 见 AS3/AS11）建仓，OLPS 月度序贯调仓（AS4），无摩擦主回测（AS5）；算 AR/AStd/SR/PSR/SOR/MR/MDD/VaR（PSR SR*=0，AS22）；与 Index 及 HRP/HERC/OLMAR/NCO 对比。
- 产出：CPMM-EW/MV 及消融/基准模型绩效表（对齐 R1）、累计收益曲线（对齐 R5，AS23）、allocation 必需图表（weight_evolution/portfolio_nav/asset_contribution/rolling_volatility/drawdown）。验证点：CPMM-EW 是否领先、消融链是否单调、下行保护是否成立（方法迁移的核心结论）。

### m7: 稳健性与敏感性分析（deps: [m6]）
- 内容：滚动 4 年子区间（AS21）、样本外区间（AS34 平移）、参数敏感性 nc/w/λ（AS14 表头修正）、单宏观因子纳入/剔除敏感性（AS24 自算）。
- 产出：对齐 SA1/SA2/SA3/SA4 的稳健性表。验证点：方法在 A股不同子区间/参数下是否稳健。
- 说明：SA5（附录G 扩展相似性 ES）判 skip=out_of_scope（optional 变体，非主结论）；SA6（TDA 拓扑异常）判 skip=method_underspecified（ε/同调阈值原文未给且 optional，AS27）；样本外效应延续/衰减评估由后续 oos 阶段（quant-oos-analyst）承接。

## 九、迁移市场复现的成功判据（实验模式核心）
数值对齐豁免，成功判据改为「方法在 A 股是否成立」，按下列**定性/相对**标准判：
1. **方法链完整可跑**：全链月频端到端产出组合净值，无阻断。
2. **消融逻辑成立（最关键）**：CPMM-EW/MV 在 SR/PSR/累计收益上**领先**其去宏观（CPM）、去聚类（PMM）、去溢出加权（EWMFM）的消融版本 —— 证明「宏观模式匹配 + 聚类 + 溢出加权」各环节在 A 股有增量价值。
3. **相对外部基准优势**：CPMM 系列相对 Index/HRP/HERC/OLMAR/NCO 的相对优势方向与原文一致（领先或至少不劣）。
4. **关键宏观因子结论迁移**：R4 迁移版中 CPI/利率是否仍为溢出最强因子（原文核心结论的 A 股可迁移性）。
5. **下行保护**：CPMM 系列 Δβ 定性为正（R3 迁移）。
6. 各评估指标量级合理、净值/回撤路径定性一致（allocation 类不苛求逐点）。
> 判达标以「2 消融逻辑 + 3 相对基准优势」为主轴；若方法在 A 股整体不成立（CPMM 不领先消融/基准），如实报告「方法迁移失效」，不粉饰。

## 十、改进建议与潜在问题（AI 视角）
1. **频率错配风险**：中国宏观月频 vs 价格日频；月度调仓（AS4）缓解，但月内价格 pattern matching 与宏观信号更新节奏需在 m4/m6 明确对齐口径。verify 归因指向调仓频率时切日频重测（AS4 备选）。
2. **UR 降维 / DGDP 代理的方向性风险（最大迁移风险）**：失业率维度缺失、社融代理债务/GDP 仅方向相关；DGDP 若进入最终因子集，其溢出权重与信号可能偏离，verify 后必须回看（AS30/AS31）；可对比「含/不含 DGDP」两版。
3. **BorutaShap 重选不确定性**：中国候选池（约 9 个）重选可能得到与原文不同的因子集，这是市场迁移的预期结果（方法忠实 ≠ 因子名单一致），不应视为失败。
4. **月频样本量风险**：A股个股历史短（部分成分股 2010 后上市），月频双区制 OLS（X>0/X<0 各半样本）自由度可能不足 → m2 设最小样本门槛剔除。
5. **计算量**：Matrix Profile（stumpy）与逐期 VAR 溢出计算密集，月度调仓 + 训练期定 w 已控规模，仍需注意测试段逐期重算成本。
6. **A股市场结构**：涨跌停/停牌/ST 需在建仓前过滤（否则信号无法执行）；融券做空受限，纯长仓（AS17）符合 A股实操。
7. **未来函数红线**：宏观数据按发布日对齐（非报告期）、信号 T 算 T+1 执行、训练期定 w 不泄漏测试期、聚类/窗口寻优只用训练段——code_audit/codex 会逐点核查。
