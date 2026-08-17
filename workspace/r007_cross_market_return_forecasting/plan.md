---
report_name: r007_cross_market_return_forecasting
title: A Bipartite Graph Approach to U.S.-China Cross-Market Return Forecasting
institution: University of Oxford、Neoma Business School、University of California Los Angeles
date: 2026-04-14
type: ml
tags: [cross_market, graph, rolling_ml, market_transplant]
difficulty: hard
feasibility: degraded
template: templates/ml.md
spec_ref: workspace/r007_cross_market_return_forecasting/spec/spec.md
data_requirements:
  - name: D1 美国个股日频数据
    source: "原文 CRSP 美国个股日频 → 两份固定 S&P 500 修订构造的 Yahoo 可查询联合代理候选池：2026 当前快照预检通过 462 只 + 2021 年末差集按原表顺序补充 39 只，共 501；正式下载全部501且至少500成功；见 AS24"
    status: substitute
  - name: D2 中国个股日频数据
    source: "原文 Wind 中国个股日频 → ashare_stock_price_forward.parquet + ashare_stock_trade.parquet；同为 A 股日频价量市值数据，且目录声明覆盖 2000-01 至今，可覆盖研究期；见 AS11"
    status: substitute
  - name: D3 个股日开盘价与收盘价
    source: "Yahoo/yfinance 缓存的美国原始及派生复权 open、close + ashare_stock_price_forward.parquet 的 open、close"
    status: available
  - name: D4 美国市场 ETF SPY
    source: "原文 SPY ETF → osshare_index_price.parquet 中经元数据及 2014–2021 覆盖审计确认的美国宽基指数；同为美国市场日频 OHLC 基准，具体代码须由数据审计确认而不预设；见 AS12"
    status: substitute
  - name: D5 中国市场 ETF 513500.SH
    source: "原文 513500.SH → ashare_csiindex_trade.parquet 的沪深 300 宽基指数（000300）；本地目录明确支持中证宽基日频 OHLC，作为迁移后 A 股市场收益基准；见 AS13"
    status: substitute
  - name: D6 个股平均市值与股票池替代
    source: "美国侧无历史 shares/market_cap，以固定双快照联合池的501个Yahoo预检通过候选、正式成功至少500个替代市值前500；A股仍由ashare_stock_trade.parquet.market_value计算全样本平均市值；见AS25"
    status: substitute
  - name: D7 个股日成交量及 21 日成交金额中位数
    source: "美股由 Yahoo 原始 Close×Volume 衍生成交金额，A 股直接使用 ashare_stock_trade.parquet.turn_value，再滚动取 21 日中位数；见 AS9/AS19"
    status: derive
  - name: D8 两国交易日历与交易时段
    source: "A 股使用 ashare_tradeday.parquet，美股由固定联合候选池501只中正式成功证券的Yahoo实际行情日期并集衍生；见AS3/AS24"
    status: derive
  - name: D9 美国与中国个股行业分类
    source: "A 股可用 ashare_stock_industry.parquet；data_catalog 未提供美股行业字段，无法形成双市场统一行业映射"
    status: missing
milestones:
  - id: m1
    name: 实验市场数据迁移与收益面板
    desc: "交付固定双快照联合候选池501只的Yahoo正式下载结果与本地A股双市场面板；最终至少500只成功并产出manifest/hash证据。"
    deps: []
    elements: [D1, D2, D3, D4, D5, D6, D7, D8, F1, F2, F3, B1, B2, B3, B4]
  - id: m2
    name: 滚动二部图与预测变量
    desc: "在 250 日历史窗构建两方向二部图、按 t 统计量筛边、输出入度分位数并形成逐目标股票预测变量；按 A2 人工裁决使用全部 |tβ|>2 的源节点，不再截取固定 top-n，无节点时跳过该目标当期预测；另按 AS27 为 FIG3 在 2021-10-21 单独构图并以全量 B1 代理图降级交付。"
    deps: [m1]
    elements: [F4, F5, F7, F8, B5, B6, B8]
  - id: m3
    name: 十模型滚动样本外预测
    desc: "复用或按需扩展 common/ml_pipeline.py，按 A6/A7 人工裁决的显式默认参数快照完成八个基础回归器及均值/中位数集成预测；依赖版本、全量 get_params 和随机种子必须固化，禁止运行时隐式漂移。"
    deps: [m2]
    elements: [F9, F10, F11, F12, F13, F14, F15, F16, F17, F18, F19, B7, B11]
  - id: m4
    name: 组合回测、基线与核心对照
    desc: "按预测绝对值构造六个嵌套组合，计算成本前日度 PnL 与年化 Sharpe，完成双向跨市场、同市场图和非图基线，并对照 R1、R3、R4 的方向、量级与相对排序。"
    deps: [m3]
    elements: [F20, F21, F22, F23, F24, B9, B10, R1, R3, R4]
  - id: m5
    name: 敏感性分析与证据输出
    desc: "在 m4 固定口径上执行边随机化、信息滞后、超参数、OPCL、市场冲击、A 股目标行业及联合预测变量分析，生成 R2 与 SA 证据；双市场行业块聚合因美股行业数据缺失不纳入。"
    deps: [m4]
    elements: [R2, SA1, SA2, SA3, SA4, SA5, SA6, SA7]
---

# A Bipartite Graph Approach to U.S.-China Cross-Market Return Forecasting 复现开发计划

## 研报信息

- 标题：A Bipartite Graph Approach to U.S.-China Cross-Market Return Forecasting
- 来源机构：University of Oxford、Neoma Business School、University of California Los Angeles
- 发布日期：2026-04-14（按 A1/AS1 的元数据日期暂登记）
- 作者：Jing Liu、Maria Grith、Xiaowen Dong、Mihai Cucuringu
- 适用市场：多资产；实验模式下落地为固定双快照联合 Yahoo 美股代理池与本地 A 股跨市场结构
- 主类型：`ml`。研究核心是滚动二部图驱动的多模型收益预测方法及模型间比较，预测质量与策略 PnL/SR 共同评价。

## 一、核心策略与创新点

### 1.1 研究背景与核心思想

先在两个非重叠交易时段的股票市场间构建有向二部图，以滚动回归的斜率 t 统计量筛选跨市场信息边；再把与每只目标股票相连的源市场收益作为机器学习特征，逐股滚动训练并严格样本外预测目标市场 OPCL 超额收益。实验迁移把美国侧替换为两个固定 S&P 500 快照经 Yahoo 稀疏 OHLCV 预检形成的501只联合候选池，正式下载后保留至少500只合格证券。

### 1.2 特征工程、标签与策略构造

1. 收益特征：
   \[
   R_{i,pvCLCL}^{(t)}=\log\frac{p_{i,cl}^{(t)}}{p_{i,cl}^{(t-1)}},\quad
   R_{i,OPCL}^{(t)}=\log\frac{p_{i,cl}^{(t)}}{p_{i,op}^{(t)}}
   \]
   再减去迁移后对应市场宽基的同口径收益，得到 \(r_i^{(t)}\)。
2. 数据预处理：每次模型/图更新时，仅在当时可见的 250 日训练窗内逐股按 0.5%/99.5% 分位缩尾；窗口内缺失采用逐目标—特征完整样本删除，不跨期填补。
3. 图特征：对源股票 \(X_j\) 与目标股票 \(Y_i\) 在历史窗内做一元回归，计算
   \[
   \beta=\frac{cov(x,y)}{var(x)},\quad
   t_\beta=\frac{\beta}{se/\sqrt{\sum(x-\bar{x})^2}}
   \]
   并以 \(|t_\beta|>2\) 保留边。US→A 股采用 \(l=1\)，A 股→US 采用 \(l=0\)，均按目标开盘前实际可得的最近源市场交易日对齐。
4. 标签：目标股票当日 OPCL 市场超额收益。预测变量使用滚动图中全部满足 \(|t_\beta|>2\) 的源股票滞后收益，不再固定 top-n；若目标股票当期没有满足阈值的源节点，则该目标当期不产生预测并退出当日组合候选，见 A2/AS14。
5. 模型：OLS、LASSO、RIDGE、RBF ε-SVR、XGBoost、LGBM、Random Forest、AdaBoost，以及八模型预测均值和中位数。主结果采用 A6/AS15 固化的库默认参数快照，SVM 采用 A7/AS16 固定口径；这是实验性降级配置，不冒充原文主结果参数。
6. 组合：按每日 \(|\hat r_i|\) 从高到低形成全部、前 80%、60%、40%、20%、10% 六个嵌套股票集合；方向取 `sign(预测收益)`，日度 PnL 为
   \[
   PnL(t)=\sum_i sign(s_i^{(t)})\,r_i^{(t)}\,b_i^{(t)}
   \]
   其中 \(b_i^{(t)}=\min(0.001\times mdv_i^{(21)},L)\)，`mdv` 按 AS9 统一为成交金额。

### 1.3 创新点

- 用跨市场有向二部图把预测变量筛选与信息传导结构结合，而非直接把全市场高维收益输入模型。
- 同时比较跨市场图、同市场图和非图自回归特征，分离图结构与跨市场信息的增量。
- 通过边随机替换、信息滞后、市场冲击与联合预测变量等测试检验信息边的结构含义。

## 二、回测参数

- 数据观察期：2014–2021；样本外预测期：2016 年首个目标市场交易日至 2021 年最后一个目标市场交易日。
- 标的池：美国侧固定501只联合候选。先按当前快照`oldid=1365256480`原表顺序保留稀疏季度OHLCV预检通过的462只，再按2021年末快照`oldid=1062834329`原表顺序加入差集中全部39只预检通过者；正式日频下载全部501只，保留至少500只合格证券。A股仍取全样本平均市值最高500只。
- 收益：预测目标为 OPCL 市场超额收益；源特征按实验规格分别使用 pvCLCL/OPCL。
- 图与训练窗口：250 个目标预测时点对应的历史样本；图和模型每 10 个目标市场交易日更新一次，区间内沿用最近一次已训练对象。FIG3 证据例外地在 2021-10-21 单独构图，不从十日更新序列选择最近锚点。
- 方向滞后：美股→A 股 `l=1`；A 股→美股 `l=0`；节假日按最近已完成且目标开盘前可得的源市场交易日配对。
- 筛边与特征数：\(|t_\beta|>2\)；使用全部过阈值源节点，不固定 `n` 或 top-n；无过阈值节点时该目标当期预测为空。
- 缩尾：训练窗内逐股 0.5%/99.5%；每个 10 日更新锚点重算。
- 模型：十种预测输出；主结果使用下节显式参数快照，Appendix A 网格仅用于 SA3，不参与主结果选参。
- 仓位上限：预测美国市场沿用 100,000 USD；预测 A 股市场沿用 1,500,000 CNY；21 日流动性按成交金额中位数。
- 交易约束：信号只用当时可得数据，按 T 日信号、T+1 可执行口径审计；不计交易成本、冲击、卖空约束与其他摩擦。
- 年化：日度 PnL 均值/标准差乘 \(\sqrt{252}\)。
- 框架：无外部 backtest framework 配置；优先复用 `common/utils.py`、`common/data_loader.py`、`common/backtest.py`，机器学习滚动训练接口按需放入 `common/ml_pipeline.py`，报告专属图筛选与预测规则放入 `src/r007_cross_market_return_forecasting/`。

### 2.1 主结果依赖与参数快照

以下配置来自 2026-07-26 人工授权，是实验性降级复现口径，不代表原文实际主参数：

- 依赖版本基线：`Python==3.13.5`、`numpy==2.5.1`、`pandas==3.0.3`、`scikit-learn==1.9.0`、`lightgbm==4.6.0`、`xgboost==3.0.3`。其中前五项按当前项目 Python≥3.12 锁文件分支固化；`xgboost==3.0.3` 为本案例新增的精确实现依赖，编码阶段须写入依赖清单并更新锁文件后才能运行。
- OLS / `LinearRegression`：`fit_intercept=True, copy_X=True, tol=1e-6, n_jobs=None, positive=False`。
- LASSO / `Lasso`：`alpha=1.0, fit_intercept=True, precompute=False, copy_X=True, max_iter=1000, tol=1e-4, warm_start=False, positive=False, random_state=None, selection="cyclic"`。
- RIDGE / `Ridge`：`alpha=1.0, fit_intercept=True, copy_X=True, max_iter=None, tol=1e-4, solver="auto", positive=False, random_state=None`。
- SVM / `SVR`：`kernel="rbf", C=1.0, epsilon=0.1, gamma="scale", degree=3, coef0=0.0, tol=1e-3, shrinking=True, cache_size=200, verbose=False, max_iter=-1`。
- XGBoost / `XGBRegressor`：`objective="reg:squarederror", booster="gbtree", n_estimators=100, max_depth=6, learning_rate=0.3, min_child_weight=1, gamma=0, subsample=1.0, colsample_bytree=1.0, reg_alpha=0, reg_lambda=1, tree_method="auto", random_state=42, n_jobs=1, verbosity=0`。
- LGBM / `LGBMRegressor`：`boosting_type="gbdt", objective="regression", num_leaves=31, max_depth=-1, learning_rate=0.1, n_estimators=100, subsample_for_bin=200000, min_split_gain=0.0, min_child_weight=0.001, min_child_samples=20, subsample=1.0, subsample_freq=0, colsample_bytree=1.0, reg_alpha=0.0, reg_lambda=0.0, random_state=42, n_jobs=1, importance_type="split", verbosity=-1`。
- Random Forest / `RandomForestRegressor`：`n_estimators=100, criterion="squared_error", max_depth=None, min_samples_split=2, min_samples_leaf=1, min_weight_fraction_leaf=0.0, max_features=1.0, max_leaf_nodes=None, min_impurity_decrease=0.0, bootstrap=True, oob_score=False, n_jobs=1, random_state=42, verbose=0, warm_start=False, ccp_alpha=0.0, max_samples=None, monotonic_cst=None`。
- AdaBoost / `AdaBoostRegressor`：`estimator=DecisionTreeRegressor(max_depth=3, random_state=42), n_estimators=50, learning_rate=1.0, loss="linear", random_state=42`。
- `ensemble-avg` / `ensemble-med`：分别对上述八个基础模型的同一股票、同一预测日有效预测取算术均值/中位数，无额外参数。

编码阶段必须在 `src/r007_cross_market_return_forecasting/config.py` 中逐项显式定义上述版本与参数；初始化每个 estimator 后将 `get_params(deep=True)` 全量序列化到结果目录的模型配置证据，并在运行前断言实际包版本等于版本基线。任何未列出的包装器参数也必须由 `get_params(deep=True)` 快照留下实际值，禁止依赖升级后静默改变。随机模型统一使用 `random_state=42`、`n_jobs=1`，这是为可重复性添加的显式覆盖，需与库默认口径区别记录。

## 三、研报核心结果（验证基准）

具体数值、原文和页码以 `spec.md` 为唯一权威来源。

| R 要素ID | 一句话摘要 | 关联 milestone |
| --- | --- | --- |
| R1 | US→CN 主结果中各模型/分位组合的 Sharpe 方向与量级 | m4 |
| R2 | 七种模型在替代超参数设置下六个组合的 Sharpe 均值与标准差 | m5 |
| R3 | CN→US 的 Sharpe 跨模型与分位显著弱于 US→CN | m4 |
| R4 | 图同市场优于非图同市场，跨市场图总体表现最强 | m4 |

## 四、复现计划

### m1: 实验市场数据迁移与收益面板

- 实现内容：读取固定联合候选池501个证券及代码映射，以`yfinance==1.2.0`正式下载全部候选的2014–2021日频数据；复用42只既有缓存中与候选池重叠且参数/schema/hash一致的文件；最终保留至少500只合格证券。
- 依赖数据：D1–D8；美国在线替代按 AS19/AS24–AS26，既有市场基准替代按 AS12–AS13。
- 产出文件：固定成分快照及哈希、逐证券原子缓存、下载 `manifest.json`、标准化双市场日频面板、数据覆盖与字段审计表、市场日历映射表、收益分布与缺失率统计。
- 验证点：联合候选池必须恰好501个唯一证券且顺序/来源可重算；预检manifest必须复现主池462、补充39；正式日频至少500/501通过覆盖与OHLCV校验，失败超过1只即停止；核验代码映射、缓存来源、请求参数、SHA256、复权、收益和时点。

### m2: 滚动二部图与预测变量

- 实现内容：按两个预测方向建立 250 日滚动回归、计算 t 统计量和二邻接矩阵，每 10 个目标交易日更新；输出目标入度 25/50/75 分位数。另为 FIG3 在 2021-10-21 单独取此前 250 个历史交易配对构图，不受十日更新锚点限制。
- 依赖：m1。
- 产出文件：更新日图矩阵/稀疏边表、入度时序、预测变量映射与图诊断图；FIG3 仅输出明确标注 `degraded/substitute` 的“2021-10-21 全量 B1 代理图”及机器可读口径清单。
- 验证点：t 统计量抽样独立重算、阈值边数一致、训练窗无未来数据、依赖图无泄漏；FIG3 口径清单必须证明 requested/effective date 均为 2021-10-21、未使用最近锚点、节点数与节点顺序可重算，并声明 `industry_limit_applied=false`、`missing_dependency=D9`、`assumption=AS27`。
- 授权降级口径：全部过阈值边直接进入特征集合；必须统计每日无入边目标数、特征维度分布和因此缺失的预测比例，作为 AS14 的验证证据。
- FIG3 降级边界：D9 缺失使“每行业最多25只”的 254×235 原文子集不可构造；全量 B1 代理矩阵不得使用原 FIG3 完整复现的标题、状态或验收措辞，也不得以全量矩阵维度替代原文维度做一致性声明。

### m3: 十模型滚动样本外预测

- 实现内容：逐目标股票训练八种基础回归器，生成两种集成预测；每 10 日更新并拼接 2016–2021 样本外预测。
- 依赖：m2。
- 产出文件：逐模型预测面板、训练样本审计、依赖版本与 `get_params(deep=True)` 全量模型配置证据、特征重要性/权重、预测—实际散点与预测质量统计。
- 验证点：包版本断言成功；参数快照与 plan/config 逐项一致；固定随机种子；每一预测仅使用此前样本；标签和特征滞后正确；八模型与两种集成逐日对应。
- 授权降级口径：主结果不调参，固定使用 2.1 节参数；RBF ε-SVR 固定 `C=1, epsilon=0.1, gamma=scale`；Appendix A 网格只在 m5/SA3 单独运行。

### m4: 组合回测、基线与核心对照

- 实现内容：构造六个嵌套分位组合，按成交金额容量计算成本前 PnL/SR；完成两方向跨市场预测、同市场图及非图 25 日基线；分别形成 US→A 股、A 股→US 方向比较，以及跨市场图、同市场图、非图三规格相对排序。
- 依赖：m3。
- 产出文件：`backtest_summary.xlsx`、组合日度 PnL/累计 PnL、双方向模型×组合 Sharpe 表、三规格基线对照表与差值图，以及 `comparison.json` 中 R1/R3/R4 的方向性对照结果。
- 验证点：组合嵌套关系、排序只用预测值、仓位币种/单位、PnL 抽样重算、年化系数；核对 R1 的 US→A 股方向与量级、R3 的 A 股→US 显著更弱关系、R4 的同市场图优于非图且跨市场图总体最强排序。

### m5: 敏感性分析与证据输出

- 实现内容：完成 SA1–SA7；Table A.1 口径按 AS7 规划为附录网格配置的 Sharpe 汇总；A 股行业层面结果使用中信一级分类。
- 依赖：m4。
- 产出文件：超参数/边随机化/滞后/冲击/行业/联合特征结果表，必需 PNG 与同 sheet 数据，敏感性对照证据。
- 验证点：随机边替换保持目标入度、参数网格完整、子样本筛选只看可得信息、R2 逐格对照、图表可回溯到底层数据。
- 降级项：F6 双市场行业块聚合及其依赖的完整双市场行业排序不做，理由码 `data_missing`，关联 A5/AS4；不影响核心模型主线。

## 五、难度判定

- 方法复杂度基准：包含滚动图回归筛边、逐股机器学习训练、超参数敏感性和跨市场联动，按判定表直接为 `hard`。
- 数据可得性修正：原始 CRSP/Wind/ETF 数据不可直接取得，但实验模式已有本地日频等价替代；双市场行业分类支线缺失已单独降级，不再重复上调。
- 模块数量修正：十种预测输出、三类基线及七项敏感性，模块数超过 8；基准已为 `hard`，封顶不变。
- 结论：`difficulty: hard`，设置 5 个 milestone，满足 hard 至少 3 个的下限。

## 六、数据映射与实验迁移边界

| 要素 | 原文数据 | 本地映射 | 状态 | 边界 |
| --- | --- | --- | --- | --- |
| D1 | CRSP 美股 | 双固定快照构造的Yahoo可查询联合候选池501证券，正式成功至少500 | substitute | 免密、可缓存；不宣称CRSP或股票池一致 |
| D2 | Wind 中国股票 | `ashare_stock_price_forward` + `ashare_stock_trade` | substitute | 保留 A 股市场，不宣称 Wind 复权/字段口径一致 |
| D4 | SPY | `osshare_index_price` 中覆盖审计确认的美国宽基 | substitute | 不虚构未由目录确认的具体代码 |
| D5 | 513500.SH | `ashare_csiindex_trade` 中沪深 300 | substitute | 转为迁移后的 A 股宽基市场收益 |
| D6 | 两国各按全样本平均市值取500 | 美国使用501候选中至少500个正式合格证券；A股仍按平均市值取500 | substitute | 美国侧不再冒充市值筛选 |
| D9 | 双市场行业分类 | 仅 A 股中信/申万分类可得 | missing | F6 不可复现；FIG3 的行业限额 254×235 子集不可构造，仅按 AS27 交付精确日期的全量 B1 代理图；SA6 仅需目标 A 股行业，可继续 |

市场迁移后的结果只能评价“二部图跨市场预测机制在固定双快照联合Yahoo代理池—A股数据上的方向性复现”，不能作为原文样本的精确数值复现；AS27 的 FIG3 代理图也只能验证精确日期下的构图实现，不能作为原文行业限额矩阵的完整复现。

### 6.1 美国在线数据精确合同

- 主池源：`oldid=1365256480`，URL=`https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid=1365256480`，修订时间`2026-07-21T06:56:32Z`，503个唯一证券；HTML SHA256=`bce53c14645cc6dbcd667abce5f9f7b2987e89daa167241eb1671ea4a22d33be`，Symbol清单SHA256=`6d4f0619598357c95da15ae5115789bf2d55065f5bf1da50e4a7bbcbfafe08d1`。
- 补充源：`oldid=1062834329`，URL=`https://en.wikipedia.org/w/index.php?title=List_of_S%26P_500_companies&oldid=1062834329`，修订时间`2021-12-30T20:37:08Z`，505个唯一证券；HTML SHA256=`4ed0df8fd6909d15393d507f3c52bfd0fde7a75b939ced14e0b19758b11c93ac`，Symbol清单SHA256=`d970ebb5508e556a95665731cb20d70b18b8bf2207d44f6a146a329f7a94209d`。
- 行情源：Yahoo Chart `https://query1.finance.yahoo.com/v8/finance/chart/{symbol}`，客户端固定 `yfinance==1.2.0`；研究/教育用途，Yahoo 未提供可据以承诺的公开数值配额，因此按保守限流执行。
- 确定性选择：按主池原表顺序，以`period1=2014-01-01, period2=2022-01-01, interval=3mo`检查研究期至少一条完整OHLCV，固定本轮通过的462只；再对2021年末表中不在主池的90只按原表顺序同样预检，固定全部39只通过者。候选池=462+39=501，不根据收益或后续回测挑选。
- 主池固定预检未通过41只：ACN、AMD、ARE、BAX、BDX、BKNG、CDNS、CBRE、CNP、CEG、CPAY、CCI、DELL、FDXF、GEHC、GEV、HONA、INTC、IP、KVUE、KEY、KHC、LRCX、L、MSCI、ORLY、PFE、PLD、DGX、Q、RVTY、SNDK、SOLV、TGT、TEL、TYL、VLTO、VICI、WEC、WSM、ZTS。该标签只表示本次预检未通过，包含研究期无数据与瞬时网络失败，不一概声称为退市。
- 补充池固定39只：AAP、ALK、AAL、BBWI、BIO、BWA、CZR、CPB、KMX、CE、CAG、XRAY、ENPH、EPAM、ETSY、FMC、ILMN、IPGP、LW、LNC、LUMN、MKTX、MTCH、MHK、NWL、OGN、PENN、POOL、PVH、QRVO、RHI、SEDG、TFX、UAA、UA、VFC、VNO、WHR、ZION。
- 请求参数：`start="2014-01-01"`（含）、`end="2022-01-01"`（不含）、`interval="1d"`、`auto_adjust=False`、`actions=True`、`repair=False`、`keepna=True`、`threads=False`、`timeout=30`。成分代码仅执行确定性 `.`→`-` 转换，并保存原始代码与 Yahoo 代码双列。
- 小样本证据：AAPL、MSFT、NVDA、BRK-B、BF-B 均返回 2015 行，首日 2014-01-02、末日 2021-12-31，OHLCV 全部 2015 行完整；五只均返回 `Adj Close/Dividends/Stock Splits`，其中 AAPL/MSFT/NVDA/BF-B 的 Adj Close 与 Close 存在差异，BRK-B 无差异。直接 Chart API 对 AAPL 同期也返回 HTTP 200、2015 个时间戳、OHLCV、adjclose、dividends、splits。
- 复权口径：缓存同时保留原始 `Open/High/Low/Close/Volume`、`Adj Close` 和公司行动。构造 `adj_factor=Adj Close/Close`，派生 `Open_adj/High_adj/Low_adj/Close_adj`；F1/F2 使用派生复权 OHLC，成交金额使用原始 `Close×Volume`。该口径登记 AS19，不把 Yahoo 调整口径冒充 CRSP。
- 正式股票池：下载固定501候选；单证券成功要求研究区间有数据且其有效区间OHLCV非空率≥95%；最终至少500成功，只容忍1个正式失败。少于500即停止，不再扩源或现场替补。
- 缓存位置：`workspace/r007_cross_market_return_forecasting/data_cache/us_yahoo_union500_v1/`。保留既有`workspace/r007_cross_market_return_forecasting/data_cache/us_yahoo_sp500_20211230/`的42只缓存；仅对候选池内且请求参数、schema、唯一键和SHA256一致者复用，并在新manifest记录`cache_origin`，不删除旧缓存。
- 断点续传：每只证券独立下载到 `.part`，完成 schema/唯一键/OHLC/日期校验并计算 SHA256 后原子改名；重跑时只有 manifest=`success`、文件存在且哈希一致才跳过，失败/损坏项单独续跑，不重下合格缓存。
- 限流与失败阈值：单线程逐证券请求，每次成功后等待2秒；超时、429/5xx最多重试5次并指数退避；连续3次429/认证错误暂停至少15分钟。累计正式失败超过1只或最终成功少于500时整批失败。
- 备选源结论：Stooq 免密 CSV 对五只样本均返回反自动化 HTML 而非 CSV，当前不可作为稳定 fallback；直接 Yahoo Chart 仅作为同源诊断备用，不是独立备源。

## 七、歧义裁决与潜在问题

- A2、A6、A7 已于 2026-07-26 获人工授权并改为 resolved；因此 `feasibility` 从 `blocked` 调整为 `degraded`。降级原因是全部阈值边、固定库默认参数及 ε-SVR 参数均属实验性实现假设，无法宣称与原文主配置一致。
- A11 决议为只使用 spec 中 R1/R3/R4 的定性方向与量级以及 R2 数值表核对，不从图像近似读数。
- 美国侧不再执行平均市值筛选；联合池以2026当前成分为主、以2021年末仍可查询的差集补充，并按一次网络预检结果排除证券，存在强幸存者偏差、当前成分偏差、Yahoo可查询性选择偏差和预检网络状态偏差。A股侧仍按平均市值筛选，两侧构造不对称。
- 原文未计交易摩擦，容量缩放后的 Sharpe 是成本前预测强度，不等同于可交易净收益。
- 美股与 A 股节假日和时区错位必须保存逐日源—目标日期映射，不能按自然日期盲目内连接。
- 市场基准替代会改变超额收益，因此 R1/R3/R4 只作方向、量级和相对排序参照，R2 数值也只能在降级口径下对照；若用户要求严格数值复现，应另行提供原始数据或切回 strict 并重新分诊。
- 新美国股票池与 Yahoo 复权口径会同时影响 US→A 股的 R1、A 股→US 的 R3 以及三规格相对排序 R4；任何方向不一致都需先检查股票池/复权/缺失覆盖，不可直接归因于二部图方法失效。
