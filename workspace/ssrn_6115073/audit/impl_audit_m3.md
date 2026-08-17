# 实现忠实性审计 · ssrn_6115073 · milestone m3（资产聚类分组：SU + 层次聚类 + Silhouette）

- 模式: code（对照审计，审读分离）
- 审读分离: 只读 `src/ssrn_6115073/clustering.py`（被审）+ 上游只读不审 `data_prep.py`/`selection.py`/`config.py` + spec.md(F3/F4/R2/B7) / plan.md(m3) / assumptions.md(AS2/AS20/AS44/AS45/AS46/AS47/AS48) / coverage_matrix.md(F3/F4/R2 回填行) + 报告原文 report_text.md + 直读 `~/local_data/*.parquet`。**不采信 coder 自述 / 变更日志声明**；SU/MI、silhouette、nc、R2 四模型对比、hier+SU 占优一律独立重算 / 独立读数据核对。
- 本案性质: experimental 市场迁移（S&P500+DJ+Nikkei / FRED → A股三宽基 + 中国宏观），tags 含 **ml**，未来函数为最高优先级审计对象；R2 为 experimental 定性验证（不追数值）。
- 独立验证方法: `uv run python` 下 (a) 独立实现 SU/熵/silhouette 公式，对相同/独立/非线性序列与合成分离簇做健全性校验；(b) 调 `prepare_all()`+`run_selection()` 得训练期候选收益，独立切训练片核未来函数；(c) 对生产 `su_matrix` 独立构 1−SU 距离阵→独立 scipy ward→独立 silhouette 与生产逐位对照；(d) 独立扫 nc=2..10 silhouette 曲线核 nc 落点；(e) 独立读 R2 对比表核 hier+SU 占优真伪。环境实测 scipy 1.18 可用、sklearn 缺（AS45 依赖退化前提成立）。

---

## 一、逐 element 核对表（coverage_matrix 全部 done 行：F3 / F4 / R2）

| 要素 | 操作规程（spec + assumption 口径） | 独立重算 / 读数据结论 | 判定 |
| --- | --- | --- | --- |
| **F3** 式9/14 SU（含 MI） | MI=H[X]+H[Y]−H[X,Y]（式9）、SU=2·MI/(H[X]+H[Y])∈[0,1]（式14）；连续收益分箱离散化估熵（AS20，sqrt(N)∈[3,12]）；**只用 in-sample 训练期收益**（spec F3 line139「in-sample」红线）；相关双度量（AS47） | 公式逐符号一致：`_su_pair`(clustering.py:158-159) `mi=hx+hy−hxy`、`su=2*mi/denom`，`denom=hx+hy`；熵 `_entropy_from_counts`(:131-137) `H=−Σp·ln p` 正确；分箱 `_n_bins`(:124-128) sqrt(N) clip[3,12] 与 AS20 一致。**独立重算：相同序列 SU=1.0000、独立随机 SU 生产0.1429=独立0.1429(diff 0)、y=x² 非线性 SU=0.6131≫\|corr\|=0.0983**（MI 抓非线性正确，见四）。correlation_matrix(:186-191) pairwise complete、NaN→0、对角=1 正确 | no_findings |
| **F4** 层次聚类+Silhouette 定 nc | 四模型 hierarchical/K-means/GMM/DBSCAN × 两度量 SU/correlation（p13）；hierarchical=scipy ward（AS46）、其余 numpy 自实现（AS45）；nc 由 Silhouette 式D.4 `SS=(ζ−α)/max(α,ζ)` 在 2..10 搜索（AS2）；每簇取「离中心最近资产」medoid（spec p14 line146/1046） | Silhouette `silhouette_precomputed`(:221-252)=(b−a)/max(a,b)、a=同簇均距(排除自身)、b=最近异簇均距，与式D.4 逐符号一致；**合成分离3簇 silhouette=0.9712、随机噪声=−0.0464，公式无系统性压低**（见四）。`_hierarchical`(:259-263) scipy `linkage(method=ward)`+`fcluster(maxclust=nc)` 正确；`cluster_config`(:415-469) 在 2..min(10,n−1) 按 silhouette argmax 选 nc 正确；medoid `cluster_medoids`(:476-492)=簇内平均距离最小者，落地 spec「离中心最近资产」正确。四模型自实现(_kmeans Lloyd+kpp / _gmm 全协方差EM / _dbscan 邻域扩张 / _classical_mds 双心化)算法正确。**三市场 nc/silhouette 生产与独立逐位相等**（见三） | no_findings |
| **R2** 表1 4模型×2度量对比 | 每配置每簇 medoid 等权训练期组合评 SR/MDD/VaR/Frobenius；SR/MDD 复用 common.utils；VaR=历史模拟最低5%（spec B7 p14 line1035）；Frobenius=‖CM−IM‖_F，IM=**单位阵**（spec B7 line1037-1040 明示 identity matrix，越小越分散） | `evaluate_representatives`(:514-535) medoid→等权 port→SR/MDD/VaR/Frobenius；`calculate_sharpe`(utils:173-191)=(mean−rf)/std·√12（式18，rf=0 保序 AS47d）、`calculate_max_drawdown`(utils:230-241) 返回正值幅度（式19 TV/PV，与表1 正值一致）复用正确；`_historical_var`(:495-500)=−quantile(r,0.05)（历史模拟最低5% 正确）；`_frobenius_diversification`(:503-511)=`norm(cm−eye,'fro')` **IM=单位阵与 spec line1039 identity matrix 精确一致**。R2 experimental 定性：迁移下 SR/Frobenius 数值远低于原文表1（弱结构，AS48），忠实报告非追数 | no_findings（含 CA-M3-01 minor 解读注记） |

### 五维度小结（设计 §9.3）

| 维度 | 独立核结论 |
| --- | --- |
| 1 公式一致 | SU/MI（式9/14）、熵（AS20 分箱）、Silhouette（式D.4）、VaR（历史5%）、Frobenius（‖CM−IM‖_F, IM=单位阵，spec line1039）、SR/MDD（式18/19 复用 utils）逐符号对照 spec/原文一致；SU 与 silhouette 经独立公式重算与合成数据健全性双验证，**无公式实质错误**。no_findings |
| 2 参数一致 | 分箱 sqrt∈[3,12]/MIN_PAIR_OVERLAP=24(AS20)、NC∈[2,10](AS2)、HIERARCHICAL_LINKAGE=ward(AS46)、MDS_DIM=5/KMEANS_N_INIT=5(AS47)、DBSCAN eps 网格(2/4/6/8/10/15%)/min_samples=2(AS45)、VAR_QUANTILE=0.05(B7)、MINI_EVAL_RF=0(AS47d)、种子42(config一致)常量(clustering.py:52-91)与 assumptions 逐条一致。no_findings |
| 3 实现位置真实 | coverage_matrix F3(6函数)/F4(10函数)/R2(4项)实现位置全部真实存在、名副其实、经实际执行产出与独立重算一致的结果。**空壳核查结论：无空壳**（无 pass/TODO 占位；全部函数均有实体逻辑且端到端跑通）。no_findings |
| 4 代码反查（私货） | clustering.py 全部 9 个公开函数(pairwise_su/correlation_matrix/relation_to_distance/silhouette_precomputed/cluster_config/cluster_medoids/evaluate_representatives/run_market_clustering/run_clustering)均映射回 F3/F4/R2/AS47，**无游离于要素之外的私货**。模块名为 clustering.py（非 plan line189 设想的 strategy.py），属与 m1/m2/m4(data_prep/selection/pattern_matching) 同构的模块化拆分，矩阵实现位置记录准确、无误导。no_findings |
| 5 简化声明 | 依赖退化 sklearn 缺→四模型自实现(AS45)、ward 连接(AS46)、辅助口径 Mantegna 距离/MDS嵌入/medoid/迷你评估(AS47)、迁移发现弱结构(AS48)、分箱估熵(AS20)均已登记；环境 sklearn 缺经实测证实。**无未登记简化**。（AS2 措辞见 CA-M3-02 minor） |

---

## 二、未来函数专项核验（ml tag 最高优先级，独立重算）

红线：SU/相关/nc/模型选择/代表组合评估全部只用 [train_start, train_end] 训练期数据，测试期不进入。

**切片逻辑**（clustering.py:634-640 `run_clustering`）：`train_sel=(idx>=prep.train_start)&(idx<=prep.train_end)`；`returns_train=md.stock_returns.loc[train_sel, cands]`；候选 `cands` 来自 m2 `sel.candidates`（训练期一次性估 AS42、固定候选集）。三市场同一代码路径。

**hs300 抽查确认聚类输入日期上界**（独立切片 + 读 index）：

| 项 | 独立读数 |
| --- | --- |
| 训练区间(config) | TRAIN_START=2007-01-01 / TRAIN_END=2018-12-31 / TEST_START=2019-01-01 |
| hs300 训练切片行数 | 144 |
| 训练切片日期范围 | [2007-01-31 .. **2018-12-28**] |
| 切片最大日期 ≤ train_end(2018-12-31)? | **True** |
| 切片含 test_start(2019-01-01) 及之后? | **False** |

结论：聚类输入严格封顶于 train_end，测试期不进入；候选集来自 m2 训练期固定集，本模块不引入测试期泄漏。**未来函数无违规。** 其余两市场为同一 `run_clustering` 切片路径，等同守卫。

---

## 三、AS48 真伪独立重算证据（关键 · §九消融逻辑输入）

AS48 声明：三市场 canonical hier+SU silhouette 全 ≤0.065（hs300 0.034/sz50 0.050/zz500 0.028）、nc 触搜索上界=10、hier+SU 非 SR 占优；根因=频率迁移（美股日频结构强→A股月频结构弱）。**独立重算逐条坐实为数据事实，非聚类实现 bug：**

### 3.1 canonical silhouette：生产 vs 独立（对生产 su_matrix 自建距离阵+独立 scipy ward+独立 silhouette）

| 市场 | tier | n_cand | 生产 nc | 生产 silhouette | 独立 silhouette(同 nc) | \|生产−独立\| | 1−SU 距离 CV |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hs300 | Tier1 | 40 | 10 | 0.034438 | 0.034438 | 0.00e+00 | 0.0542 |
| sz50 | Tier2_degraded | 50 | 10 | 0.050432 | 0.050432 | 0.00e+00 | 0.0686 |
| zz500 | Tier1 | 50 | 10 | 0.027746 | 0.027746 | 0.00e+00 | 0.0500 |

- silhouette 生产与独立**逐位相等**，且与 AS48 声明值一致（0.034/0.050/0.028）。三市场均 ≤0.0505，远低于「有实质结构」0.25 门槛。
- 距离阵(1−SU)非对角 CV 全 <0.07（近等长）→ 结构弱是**数据事实**。成因之一：分箱 MI 有限样本正偏（独立随机对 SU≈0.14，见四），抬升 SU 下限、压缩距离，为 AS20 分箱估计固有性质（美股日频样本多偏小/A股月频 144 月偏大），非 bug。

### 3.2 nc 落搜索上界：独立 silhouette(nc) 曲线（argmax）

| 市场 | 独立 silhouette(nc=2..10) | 独立 argmax nc | 生产 nc |
| --- | --- | --- | --- |
| hs300 | 2:.031 3:.017 4:.021 5:.024 6:.027 7:.030 8:.032 9:.034 **10:.034** | **10** | 10 |
| sz50 | 2:.036 3:.029 4:.034 5:.032 6:.033 7:.037 8:.044 9:.047 **10:.050** | **10** | 10 |
| zz500 | 2:.021 3:.017 4:.018 5:.020 6:.019 7:.020 8:.024 9:.025 **10:.028** | **10** | 10 |

silhouette 无内部峰、随 nc 弱单增，独立 argmax=10=生产 nc（触 NC_MAX 上界）。印证 AS48「nc 非清晰定值」。

### 3.3 hier+SU 非占优：独立读 R2 对比表 SR 最高配置

| 市场 | hier+su SR | SR 最高配置(独立) | hier+SU SR 占优? |
| --- | --- | --- | --- |
| hs300 | 0.5978 | **dbscan+su**(0.6972) | 否 |
| sz50 | 0.4610 | **gmm+su**(0.5693) | 否 |
| zz500 | 0.7559 | **dbscan+su**(0.7617) | 否 |

三市场 hier+SU 均非 SR 占优，与 AS48 一致；差异（zz500 仅差 0.006）落在弱结构噪声内。

**综合**：AS48「A股月频 SU 聚类结构极弱、nc 触上界、hier+SU 非占优」经独立重算**全部坐实为真数据发现**，非距离阵构造错 / silhouette 公式错致的人为压低。§九「去聚类 PMM 对比」的关键回看点成立。

---

## 四、公式健全性独立校验（审计者自写实现，反 bug 假象）

| 校验 | 期望 | 被审值 | 独立值 | 结论 |
| --- | --- | --- | --- | --- |
| SU 相同序列 | ≈1 | 1.0000 | — | SU 上界正确 |
| SU 独立随机 | ≈0（分箱正偏） | 0.1429 | 0.1429 | 同公式同分箱，diff=0 |
| SU 非线性 y=x² | ≫\|corr\| | 0.6131 | — | MI 抓非线性正确(corr=0.098) |
| Silhouette 分离3簇 | ≈0.8-0.9 | 0.9712 | 0.9712 | 分离结构给高分，公式无系统压低 |
| Silhouette 随机噪声 | ≈0 或负 | −0.0464 | −0.0464 | 无结构给≈0，方向正确 |

SU 与 Silhouette 公式实现均正确；结合三，A股真实数据的低 silhouette 是弱结构数据事实，**排除公式 bug 假象**。

---

## 五、findings

| id | severity | 定位 | 描述 | 建议 |
| --- | --- | --- | --- | --- |
| CA-M3-01 | minor | clustering.py:503-511, 653-664 | R2 跨配置 Frobenius（及部分 SR）对比受各配置 nc 差异混淆：‖CM−IM‖_F 随代表资产数(nc)单调增（hs300 实测 nc2→0.42/nc4→1.21/nc5→1.96/nc8→2.87/nc10→4.09），`_dominance` 的「Frobenius(低)=最分散」实为「nc 最小」，非真分散度。Frobenius 公式本身忠实 spec（未归一化，spec 亦未定归一化），问题在跨不同 nc 配置的比较解读。R2 support 级+定性、m5 恒用 hier+su canonical（不据 R2 排名选模型）、AS48 已「差异落弱结构噪声内」适度对冲，故不误导下游决策 | 在 R2 表/AS48 注记「Frobenius/SR 跨配置排名受 nc 混淆，不作绝对分散度结论」，供 reporter/m5 解读；如需可比可对同 nc 或按 √(nc(nc−1)) 归一化（属敏感性，非必改） |
| CA-M3-02 | minor | clustering.py:546-615 / assumptions.md AS2(line23) | AS2 文本称 nc「每个市场/每个再平衡期」确定，代码实为训练期一次性(in-sample once)定 nc 供 m5 固定簇标签。代码与 **spec F3「in-sample」(line887-888)** 一致（原文聚类为 in-sample 一次性选资产，非逐期重聚），与 AS2 措辞不符 | 订正 AS2 措辞为「训练期 in-sample 一次性定 nc、固定簇标签供 m5」，与 spec/代码对齐（代码无需改） |
| CA-M3-03 | minor | clustering.py:527 | `evaluate_representatives` 的 `nav=(1+port).cumprod()` 未前置 1.0 基点，若组合首期即最大回撤则 MDD 略被低估；迷你评估保序、各配置一致，影响可忽略 | 如需精确 MDD 可 `nav=pd.concat([pd.Series([1.0]), (1+port).cumprod()])`（非必改，不影响占优排序） |

无 critical、无 major。未来函数无违规；SU/silhouette 公式无实质错误（AS48 弱结构结论坐实为数据事实，非 bug 假象）；实现位置无空壳、无虚报；无未登记简化、无私货。

---

## 已检查五维度清单（对应设计 §9.3，无遗漏）

1. **公式一致**：F3 式9/14 SU/MI + 熵 + F4 式D.4 Silhouette + R2 SR式18/MDD式19/VaR历史5%/Frobenius‖CM−IM‖_F(IM=单位阵) 逐符号对照 spec/原文 — 一致，且经独立公式重算 + 合成数据健全性双验证。
2. **参数一致**：分箱/NC/ward/MDS/DBSCAN eps 网格/VaR分位/rf/种子常量逐条对 assumptions — 一致。
3. **实现位置真实**：F3/F4/R2 共 20 项实现位置函数全部真实存在、名副其实、端到端跑通 — 空壳核查结论：无空壳。
4. **代码反查（私货）**：clustering.py 9 个公开函数全映射回 F3/F4/R2/AS47 — 无私货。
5. **简化声明**：AS20/AS45/AS46/AS47/AS48 依赖退化与辅助口径均登记、sklearn 缺经实测证实 — 无未登记简化。

（专项加验）未来函数：hs300 训练切片封顶 2018-12-28 ≤ train_end、无测试期，三市场同路径 — 无违规。AS48 真伪：silhouette 生产=独立(diff 0)、CV<0.07、nc 独立 argmax=10、hier+SU 非占优 — 全坐实为数据事实。

**verdict**: pass_with_issues
