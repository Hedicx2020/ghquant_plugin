# 实现忠实性审计 · ssrn_6115073 · milestone m1（市场迁移数据映射与宏观因子准备）

- 模式: code
- 审读分离: 只读 config.py / data_prep.py / common/data_loader.py + spec.md / plan.md / assumptions.md / coverage_matrix.md + 本地 parquet；**不采信 coder 自述 / 变更日志声明**，全部数值/对齐/时点独立读数据重算。
- 本案性质: experimental 市场迁移（美股+日股+FRED → A股三宽基+中国宏观），tags 含 ml，未来函数为最高优先级审计对象。
- 独立验证脚本: 均在 `uv run python` 下直读 `~/local_data/*.parquet` 与实际调用 `src.ssrn_6115073.data_prep` 函数重算。

---

## 一、逐 element 核对表（coverage_matrix 全部 done 行：D1/D2/D3/D4/B1/B2/F12）

| 要素 | 操作规程（spec+assumption 口径） | 独立重算/读数据结论 | 判定 |
| --- | --- | --- | --- |
| **D1** | 三宽基时点成分股前复权月收益 + 时点成分掩码 + 可交易掩码（AS28/AS8） | 月收益=前复权 close 的 pct_change 逐值核对：股票 000001@2020-06-30 code=-0.01538，手工(10.385→10.226)=-0.01538 一致；首月全 NaN 正确。时点成分半开 [in_date,out_date)：hs300=300/sz50=50/zz500=500（3 个历史月末各核对），out_date 当日已剔除（600880/600547/002049 三例验证）防幸存者偏差。可交易掩码剔除 ST（000408✓）/次新（300832 first_trade 2020-05-12<6 月✓）/停牌（000029@2020-06-30✓）。月均可建仓 296≈300。 | no_findings |
| **D2** | 中国宏观候选池月频「同比/水平 → AS1 月度一阶差分」，披露日 asof（AS29/AS1/AS37）；UR 降维(AS30)、DGDP→社融(AS35) | indicator_name 8 项全命中原始表；asof 逐月末零泄漏（见二）；change_panel=level.diff() 独立核对一致（CPI/M2 三期 np.allclose True）；候选池确无 UR（AS30 降维落地✓），SF=直接融资累计同比（AS35✓）。**但发现当期同比/累计同比口径混用未登记（CA-A01）**。 | CA-A01(major), CA-A03(minor) |
| **D3** | rf = 10Y 国债年化 → 月度几何折算（AS19/AS32/AS36） | (1+y/100)^(1/12)-1 逐值核对：2020-06-30 code=0.002326，手工(y=2.827%)=0.002326 一致；228 期全覆盖；bond_yield_10y 源覆盖 2002-2026。 | no_findings |
| **D4** | 宽基指数月频收益 + 月末点位（Index 基准 / Modigliani σ_b，AS33） | level=月末 close 逐值核对（000300@2020-05=3867.02、06=4163.96 均一致）；月收益=level.pct_change 一致(0.07679)；227 期非空。 | no_findings |
| **B1** | 三市场池映射 hs300/sz50/zz500 ← S&P500/DJI/N225（AS28） | config.MARKETS 映射与 AS28 一致；PRIMARY=hs300 对标 S&P500 主分析；prepare_all 端到端构建三市场，月均成分 300/50/500 正确。 | no_findings |
| **B2** | 训练 2007-2018 定 w/nc、测试 2019-2024 评估（AS6/AS34） | config TRAIN 2007-01-01~2018-12-31 / TEST 2019-01-01~2024-12-31，与 AS34 完全一致；PANEL_LOAD_START=2006-01 作 pct_change/asof 缓冲合理。 | no_findings（F12 训练下界见 CA-A04 minor） |
| **F12** | BorutaShap 在中国候选池重选，只用 ≤TRAIN_END 训练期；依赖不可用退化直采（AS16/AS38） | 训练 X 实际 2006-01~2018-12，`index<=TRAIN_END` 无测试期泄漏（>TRAIN_END 进入 X = False✓）；训练有效样本 155≥60 门槛；sklearn/shap/BorutaShap 经 import 确认均 ModuleNotFoundError → selection_mode=degraded_all，返回全 8 候选，与 AS38 一致；退化返回仅列名无数据泄漏。 | no_findings（训练下界 minor CA-A04） |

**空壳核查（实现位置真实性）**：coverage_matrix 中 m1 全部 done 行的实现位置函数（get_index_members_on_date / load_stock_monthly_returns / load_tradeable_mask / load_macro_candidate_panel / _macro_level_publ / _asof_to_month_ends / select_macro_factors / load_rf_series / load_index_benchmark / prepare_market / prepare_all + config 常量 MARKETS/MACRO_CANDIDATES/RF_CACHE_COLUMN/BORUTA_*/TRAIN_*/TEST_*）逐一经实际调用执行验证，**均为真实、名副其实、有实体逻辑的函数/常量，无 pass/TODO 空壳，无名不符实**。故本 milestone 无空壳、无需回退、无 critical。

---

## 二、未来函数专项核验记录（ml tag 最高优先级，独立读原始 parquet）

### 2.1 宏观 asof 披露日对齐 —— 逐月末全扫描零泄漏
- 方法：228 个月末交易日历 × 7 个非市场利率因子（CPI/PPI/GDP/IP/M2/PMI/SF），对每月末取 code 逻辑选中的报告期行，用**严格可得下界**判泄漏：真实 info_publ_date（若存在且 >报告期）为准，缺失时用 `报告期 + 严格下界`（月频 +8 天、GDP +15 天、PMI +0 天，故意取偏早值宁误报勿漏报）。
- 结果：**CPI/PPI/GDP/IP/M2/PMI/SF 全部 0 泄漏**（每个因子 228 月末逐个比对 true_avail ≤ 月末）。IR 为市场即时利率（is_market_rate）无统计披露滞后，用报告期月末本身。

### 2.2 手工抽查月末明细（读原始宏观 parquet 逐格核对）
**抽查月末 2020-06-30**（code 选中报告期 / code 披露 / 真实披露 / 下一期是否被泄漏）：

| 因子 | code 用报告期 | code 值 | 披露对齐 | 下一报告期(应被排除) | 泄漏 |
| --- | --- | --- | --- | --- | --- |
| CPI | 2020-05-31 | 2.44 | 真实 publ 2020-06-10 ≤ 月末 | 2020-06-30 值 2.48 publ 2020-07-09 > 月末 | 无 |
| M2 | 2020-05-31 | 11.1 | 真实 publ 2020-06-10 ≤ 月末 | 2020-06-30 publ 2020-07-10 > 月末 | 无 |
| SF | 2020-05-31 | 88.70 | info_publ 被回填 2024-06-03(异常>90)→fallback 报告期+20=2020-06-20 ≤ 月末 | 2020-06-30 fallback 2020-07-20 > 月末 | 无 |
| IP | 2020-05-31 | -2.80 | info_publ 回填 2021-05-18(异常)→fallback +18=2020-06-18 ≤ 月末 | 2020-06-30 fallback 2020-07-18 > 月末 | 无 |
| GDP | 2020-03-31(Q1) | -6.80 | 真实 publ 2020-04-17 ≤ 月末，季频 asof 前填 | Q2 2020-06-30 publ 2020-07-16 > 月末 | 无 |

**抽查月末 2019-12-31**：CPI 取 2019-11 报告期(publ 2019-12-10)，Dec CPI(publ 2020-01-09)正确排除；GDP 取 Q3 2019(publ 2019-10-18)，Q4(publ 2020-01-17)排除；PMI 取 Nov 2019(50.2)，Dec(fallback 2020-01-01)排除。均无泄漏。（注：脚本"对应报告期"栏在相邻期数值相同时会出现数值匹配假象，asof 实按 publ_date 正确选取，已独立复核。）

### 2.3 AS37 fallback 合理性检验（防未来函数验证）
- 逻辑（data_prep.py:310-315）：`reasonable = publ_raw.notna() & (publ_raw>报告期) & (publ_raw<=报告期+90)`；真实披露不合理时回退 `报告期 + publ_lag_days`。
- 独立核验：CPI/M2/PPI 真实滞后中位 9.5~12 天，fallback 用 15~18 天 ≥ 真实；IP/SF/GDP 被批量回填(滞后数千天)正确判为异常→用 fallback；在**月末粒度**下 fallback(报告期+15~20 天)与真实披露(次月上中旬)同落次月，asof 到月末结果一致。**fallback 一律「宁晚不早」，无前视**。

### 2.4 时点成分股防幸存者偏差
- get_index_members_on_date 半开 [in_date,out_date)（common/data_loader.py:353-356）独立验证：out_date 前一日在册、out_date 当日剔除；out_date 为空=当前在册。三市场历史月末成分数恒等于指数目标数。**用时点名单非当前名单回溯，无幸存者偏差**。

### 2.5 F12 训练期切分防泄漏
- select_macro_factors（data_prep.py:377-378）`train_mask = index<=train_end`；独立验证测试期(>2018-12-31)不进入 X；y 按 X.index reindex，测试期不参与选择。**无训练泄漏**（当前 degraded_all 退化，代码 gate 路径正确，依赖装上后仍只用训练期）。

**未来函数专项结论：全部通过，m1 面板无未来函数。**

---

## 三、findings 清单

| id | severity | 文件:行号 | 描述 | 建议 | confidence |
| --- | --- | --- | --- | --- | --- |
| CA-A01 | major | src/ssrn_6115073/config.py:88,90,96 | 宏观同比口径混用且未登记假设：CPI/PPI 用「当期同比」(单月 yoy)，GDP/IP/SF 用「累计同比」(累计 yoy)。AS1/AS29 仅泛称「同比」未区分当期/累计。累计同比的月度一阶差分(change_panel)在年初有机械重置跳变；GDP 季频 asof 后季内 change 恒为 0（仅季度披露月非 0，下游 Δβ 的 X>0/X<0 观测稀疏，约 4 月/年）；IP 另有「规模以上工业增加值(1-2月累计填充):当期同比:月」可得（更贴近原文 FRED Industrial Production 单期口径、避免累计锯齿）却未采用。此口径经 change_panel 扩散至 Δβ(m2)/pattern matching(m4)/溢出(m5)全链。 | 补一条 assumption 明确各因子当期/累计选择理由；IP 建议改用当期同比或显式登记累计同比的年初跳变处理；GDP 季频稀疏在 m2 需登记对 Δβ 样本量的影响。实验模式数值豁免软化实际影响，但口径选择应登记可追溯。 | — |
| CA-A02 | minor | src/ssrn_6115073/data_prep.py:37,39 / :238,252 | 复用半落地：data_prep 导入 common 的 load_suspend_status/load_limit_status（对旧 load_suspend 读不存在文件 ashare_suspend.parquet/字段 ifsuspend 的 bug 修正，已核对新函数读 ashare_stock_suspend.parquet + if_suspend 正确），但 load_tradeable_mask 内实为内联 pd.read_parquet（为 filters 下推 date/stock_code 性能）未调用二者，产生未用导入，且停牌/涨跌停加载逻辑事实上未复用 common 修正函数（虽内联读同一正确文件/字段，数据正确）。 | 或改调 common 加载器（如需下推可给加载器加 filters 参数），或删除未用导入并注释说明内联原因。 | — |
| CA-A03 | minor | src/ssrn_6115073/data_prep.py:314 | PMI 披露日合理性检验用严格 `publ_raw > 报告期`，PMI 真实同日披露(lag=0)被判不合理→回退 fallback=报告期+1，使 PMI 系统性延后 1 个月进面板（2020-06 月末用 5 月 PMI 而非当日已发布的 6 月 PMI）。为安全侧（无未来函数、更保守），但 PMI 信号偏陈旧、损失同月已公开信息。 | 对 PMI 等月末当日披露指标，将合理性检验放宽为 `publ_raw >= 报告期`，或对其标 is_market_rate/同日可得口径。 | low（取决于 PMI 是否盘后发布，若盘后则当前保守做法反而正确） |
| CA-A04 | minor | src/ssrn_6115073/data_prep.py:377 | F12 训练窗 `index<=TRAIN_END` 无 TRAIN_START(2007) 下界，实际含 2006 缓冲期 12 个月进入 BorutaShap 训练样本。非未来函数(2006<2018)、当前 degraded_all 退化下无影响，但与声明 TRAIN_START=2007 的训练区间不一致。 | select_macro_factors 加 `index>=TRAIN_START` 下界，使训练窗与 B2/AS34 声明一致。 | — |
| CA-A05 | minor | src/ssrn_6115073/config.py:23 / src/ssrn_6115073/data_prep.py:523 | 文档瑕疵：config.py:23 注释「沪深300 成分 in_date 起于 2006-07」与实际(最早 2005-04-08)不符；PreparedData.meta 声称载「实际首末日/披露日覆盖等诊断信息」实为空 dict {}（prepare_all 传 meta={}）。不碍复现。 | 更正注释为实际起始；meta 若规划填诊断信息则落地，否则删除误导性 docstring。 | — |

---

## 四、市场迁移合规核查（substitute → 假设登记）

| substitute | 登记假设 | 核查 |
| --- | --- | --- |
| hs300/sz50/zz500 ← S&P500/DJI/N225 | AS28 | 已登记，config.MARKETS 一致 |
| CPI/PPI/GDP/IP/IR ← FRED；M2/PMI/SF 候选补充 | AS29 | 已登记 |
| UR 降维剔除 | AS30 | 已登记，候选池确无 UR |
| DGDP → 社融直接融资累计同比 | AS31→AS35 | 已登记，SF 命名与实现一致 |
| rf/IR → 10Y 国债（短端序列本地不足） | AS19/AS32→AS36 | 已登记，bond_yield_10y 折算核对一致 |
| 指数基准 → A股宽基点位 | AS33 | 已登记 |
| 区间 → A股 2007-2024 | AS34 | 已登记，config 一致 |
| 披露日合理性检验 fallback | AS37 | 已登记，逻辑经泄漏扫描确认防未来函数 |
| BorutaShap 退化直采 | AS38 | 已登记，依赖确不可用 |

**结论：全部 substitute 均有对应 market-transplant 假设登记，无未登记的隐性替代。**（当期/累计同比口径混用属 AS29 之下的子口径细节，AS1「同比」措辞宽泛未违反其字面，但建议按 CA-A01 补登记。）

---

## 五、已检查维度清单（code 五维度，无遗漏）

1. **公式一致**：pct_change 月收益 / (1+y/100)^(1/12)-1 rf 折算 / level.diff() AS1 差分 / asof merge_asof backward — 均独立重算逐值一致。
2. **参数一致**：TRAIN/TEST 区间(AS34)、MARKETS 映射(AS28)、PUBL_LAG_CAP_DAYS=90、publ_lag_days、LISTING_MIN_MONTHS=6、BORUTA_MIN_TRAIN_SAMPLES=60 — 与 spec/assumption 核对一致；MACRO_CANDIDATES indicator_name 8 项全命中原始表。
3. **实现位置真实**：coverage_matrix m1 全部 done 行实现位置经实际调用执行验证为真实非空函数，无空壳、无名不符实。
4. **代码反查**：独立读 ~/local_data parquet 反查——asof 逐月末零泄漏、时点成分半开区间、掩码剔除 ST/次新/停牌、F12 训练期切分，均与代码行为一致，无未来函数。
5. **简化声明**：AS35(SF代理)/AS36(rf-IR 10Y)/AS37(披露日 fallback)/AS38(BorutaShap 退化) 四条实现期简化均已登记；未发现未登记的 core 要素简化（当期/累计口径为 AS1 之下子选择，记 CA-A01 建议补登记）。

关键数值均独立重算并与 coverage_matrix 变更日志声明比对：日志称「8 因子披露日 asof 对齐全 228 期覆盖」→ 独立复核 228/228 属实；称「未来函数自检通过」→ 独立扫描确认零泄漏，未直接采信。

**verdict**: pass_with_issues
