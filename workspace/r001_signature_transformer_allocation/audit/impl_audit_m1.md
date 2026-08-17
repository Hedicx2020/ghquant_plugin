# 实现忠实性审计 · r001_signature_transformer_allocation · milestone m1（数据层与 A股迁移 universe 构建）

- 模式: code（对照审计，审读分离）
- 审读分离: 只读 config.py / data.py / main.py / common/data_loader.py + spec.md / plan.md / coverage_matrix.md / assumptions.md + 本地 parquet；**不采信 coder 冒烟自述与变更日志声明**，anchor 日期、划分计数、universe 点时性、退市洞、收益口径一律独立运行 `uv run python` 重算。
- 本案性质: experimental 市场迁移（美股 WRDS → A股 CSI300），tags 含 ml，未来函数为最高优先级审计对象（无视难度必跑）。
- 审查范围: coverage_matrix 中 m1 全部 `done` 行 = D1 / D2 / D3。

---

## 一、逐 element 忠实性核对（D1 / D2 / D3，独立重算）

| 要素 | 操作规程（spec + assumptions 口径） | 独立重算/读数据结论 | 判定 |
| --- | --- | --- | --- |
| **D1** 实验股票池 universe（p5，core，AS3/AS12/AS16/AS19） | CSI300 成分按市值 top-N 点时快照，剔 ST/停牌；固定资产集 anchor=train 起点（AS19） | 独立运行：`resolve_anchor_date`=**2007-01-31**（train 段首月末，与 AS19 一致）；`select_universe_at` 选出 50 只，独立用 `get_index_members_on_date(anchor)` 反查——**50/50 全部 ∈ anchor 点时在册 CSI300 成分**（`sel-members=∅`），选样只用 ≤anchor 的在册成分+当日市值，**零未来函数**。ST/停牌/市值窗口均 `≤anchor` 半开区间，忠实。 | 忠实（退市洞风险见 CA-A01） |
| **D2** WRDS 日频价格 → A股前复权（p5，core，AS11） | 前复权 close 日收益母源 | `load_stock_price_forward`（common，filters 下推）+ `load_forward_close_panel` pivot 成 wide 面板（4510×50 独立复算一致）；`compute_log_returns`=`ln(close_t)−ln(close_{t-1})`，抽查 601398 某日 code=0.053308 vs 手工 0.053308 **一致**。另产 `daily_simple_returns=pct_change` 供 m4 回测。log 口径未落 assumption（见 CA-A02）。 | 忠实（口径登记瑕疵 CA-A02） |
| **D3** train/val/test 划分（p5，core，AS13） | 固定、不重叠、按时间顺序；train 起点迁移 2007 | config 字段 train 2007-01-01~2016-12-31 / val 2017-2019 / test 2020-01-01~2024-12-27 与 plan/AS13 一致；独立运行 `split_dates`：调仓日 **120/36/59（sum=215）**，train/val 与 val/test **重叠均为 0**，按时间顺序无泄漏。anchor(2007-01-31) 落 train 段内，选样不引入 test 信息。 | 忠实 |

**空壳核查（实现位置真实性，G-CA-3）**：coverage_matrix m1 三个 done 行的实现位置函数——`select_universe_at` / `build_pit_universe` / `load_data_bundle`（D1）、`load_stock_price_forward` / `load_forward_close_panel` / `compute_log_returns`（D2）、`SITConfig` 字段 / `split_ranges` / `split_dates`（D3）——**逐一经实际 `uv run python` 调用执行、返回真实数据结构**，均为名副其实、含实体逻辑的函数/字段，**无 pass/TODO 空壳、无名不符实、无空壳、无 not_found 情形**。故 m1 无需回退、无 critical。

---

## 二、未来函数专项核验（ml tag 最高优先级，独立读 parquet 重算）

| 核验点 | 方法 | 结论 |
| --- | --- | --- |
| universe 点时选样无前视 | 独立用 `get_index_members_on_date(comp, 2007-01-31)` 反查 50 只归属 | **50/50 全部 anchor 点时在册**，`select_universe_at` 内成分/ST/停牌/市值全部 `≤anchor` 半开 [in,out) 区间——零未来函数 |
| 收益仅用历史 | `compute_log_returns=np.log(close).diff()`，逐日 t 只用 close_t / close_{t-1} | 无前视 |
| train/val/test 不重叠无泄漏 | 独立 `split_dates` 求交集 | train∩val=0、val∩test=0；anchor 在 train 段，选样不看 test |
| 固定资产集不含未来在册信息 | anchor=train 起点 vs test 起点对比 | train 起点严于 test 起点（后者用未来在册→回溯幸存偏差），AS19 取严者，方向正确 |
| 日历特征 v_t | `build_calendar_features` 纯 date 的 sin/cos | 确定性、无前视；shape 独立复算 (4510,**8**)，F=8 与 AS4 一致 |

**未来函数专项结论：universe 选样、收益、划分、日历特征均无未来函数。**（唯一残留风险不在"看未来"，而在"退市洞 0 占位"的绩效失真，见三。）

---

## 三、AS19 固定资产集合理性评估（核心专项）

**AS19 内容**：universe 取 anchor=2007-01-31（train 起点）点时快照的固定 top-50 资产集，全程固定；3 只 test 期退市/长停致行情洞，不可交易期日收益置 0 占位；universe_meta 标注有效区间供 m4 屏蔽。

**逐条独立核验与评估：**

1. **前视偏差（look-ahead）——通过**。独立反查 50/50 全部 anchor 点时在册，选样只用 ≤2007-01-31 信息，无未来函数。
2. **幸存偏差（survivorship）——方向正确，train 起点优于 test 起点**。train 起点固定集**包含**后续退市者（实测确有 3 只退市），不是"只选活到最后的"，故相对 test 起点锚**降低**幸存偏差。AS19"train 起点较 test 起点更严"成立。
3. **退市洞 0 占位系统性偏差——AS19 严重低估（CA-A01）**。独立实测 4 只 `full_test=False`，其中 **3 只 test_coverage=0.0000**（600005 末交易 2017-02-13、600832 末 2015-05-19、000562 末 2015-01-23，**均早于 test 起点 2020-01**），其 **test 期全部 1210 日收益被 `fillna(0)` 伪造为 0**（实测 600005 test 期非零日=0/1210、sum=0）；而这 3 只在 **train 期有真实收益**（600005 训练期 2131 个非零日）——即模型训练见真实大盘股、测试见幻影 0 资产。第 4 只 000792 test_coverage=0.75（长停）。AS19 称"退市洞仅占 3/50…影响有限""等价持现金无损益"**低估**：这不是部分洞而是**整段 test 窗全幻影**，3/50=**6% 资产恒 0**；若 m4 不屏蔽/重分配，~6% 恒 0 资产将系统性拖拽 SIT 与全部基线绩效向 0（虚增或虚减依权重方向，退市多因经营恶化，"无损益"框定不当）。
4. **陈旧 universe（stale composition）**——2007 top-50 持有至 2024，test 期成分未必代表当期大盘，属固定集设计固有代价，实验模式数值豁免下可接受，但保真度成本真实存在。

**AS19 评估结论**：核心**防未来函数逻辑正确且已忠实实现**（独立验证零前视、幸存偏差方向正确）；但"影响有限"的乐观判断**不成立**——3 只全 test 窗幻影 0 资产是**major 级系统性偏差风险**。universe_meta 已正确标注 full_test=False（提供 m4 屏蔽依据），但**收益面板本身已被 0 污染**，屏蔽责任全压 m4。**记风险点交 verify/result_audit：必须核实 m4 确实屏蔽/重分配这 3 只 test_coverage=0 资产，否则全部 R/SA 绩效被幻影 0 资产系统性扭曲。**

---

## 四、findings 清单

| id | severity | 文件:行号 | 描述 | 建议 | confidence |
| --- | --- | --- | --- | --- | --- |
| CA-A01 | major | src/r001_signature_transformer_allocation/data.py:314-315（fillna(0.0)）；assumptions.md AS19 | 退市洞 0 占位系统性偏差，AS19 低估。独立实测 3/50（6%）资产 test_coverage=0.0（600005/600832/000562 于 2015-2017 退市，早于 test 起点），test 期 1210 日收益全被伪造为 0；这 3 只 train 期有真实收益（600005 训练 2131 非零日），模型训练见真实、测试见幻影。AS19"影响有限""无损益"低估：整段 test 窗全幻影而非部分洞，若 m4 不屏蔽将系统性拖拽 SIT 与全部基线绩效。 | 交 verify/result_audit：强制核实 m4 屏蔽/权重重分配这 3 只 test_coverage=0 资产；报告须标注 6% 幻影资产对绩效的方向性影响；或改 universe_anchor 策略（代价为幸存偏差）。 | high（独立运行确认 test 期全 0） |
| CA-A02 | minor | src/r001_signature_transformer_allocation/data.py:173-175 | 对数收益口径未落 assumption。`compute_log_returns=ln(close).diff()`，与 AS11/plan 声明的"close/prev_close−1（简单收益）"字面不一致；代码实际双口径（log 特征母源 + simple 回测），log 更贴合签名连续路径（D5）、设计合理且 docstring 已注明，但未登记为假设。 | 补一条 assumption 明确 log（特征/签名）+ simple（回测 nav）双口径及理由，使 AS11 口径可追溯。 | — |
| CA-A03 | minor | src/r001_signature_transformer_allocation/data.py:314；select_universe_at:98-126 | 固定资产集下 ST/停牌仅在 anchor（2007-01-31）过滤一次，持有期新增 ST/停牌不再剔除；停牌 NaN→fillna(0) 使复牌首日跳变被抹为 0（000792 test_coverage 0.75 即长停）。universe_meta 仅按价格洞标注、不含持有期 ST 状态，m4 屏蔽依据对"仍交易但转 ST"类不完整。 | m4 回测须补持有期 ST/停牌点时屏蔽，不能仅依赖价格洞；或在 universe_meta 增持有期 tradability 标注。 | medium |
| CA-A04 | minor | src/r001_signature_transformer_allocation/data.py:129-147 | `build_pit_universe`（逐调仓日浮动 universe）在 m1 固定资产集主链未被调用（`load_data_bundle` 走 `select_universe_at` 直选固定集），当前为 m1 未用函数（docstring 声明为 m4 浮动备选/数据探查）。非违规，记录以免误认为主链在用浮动 universe。 | 保留则注释标注"非主链、m4 备选"；或延后至实际使用的 milestone 引入。 | — |

---

## 五、已检查维度清单（code 五维度，无遗漏）

1. **公式一致**：对数收益 `ln(close_t)−ln(close_{t-1})`（抽查 601398 code 0.053308 vs 手工 0.053308 一致）；日历特征 `sin/cos(2π·val/period)` 4 周期×2=F=8（config `__post_init__` 自校验 2×len(cycles)==8）；市值窗口取 ≤anchor 最近值——均独立重算一致。
2. **参数一致**：anchor=2007-01-31（AS19）、top_n=50（AS16 主档）、train/val/test 端点（AS13）、H=60/K=12（B8/AS2，config 已登记 m2+ 用）、cvar_alpha=0.80（AS1）、cost_bps=0（AS9）、market_value 选样列（AS3）——与 spec/assumptions 逐条核对一致；config `frozen`、无魔法数字散落。
3. **实现位置真实**：m1 三个 done 行（D1/D2/D3）实现位置函数/字段经实际调用执行验证为真实非空，**无空壳、无名不符实、无 not_found**。
4. **代码反查**：独立读 ~/local_data parquet 反查——50/50 anchor 点时在册（零未来函数）、划分 120/36/59 无重叠、退市股 test 期全 0（3 只 test_coverage=0）、面板 4510×50 / 日历 4510×8——均与代码行为一致，退市洞暴露 CA-A01。
5. **简化声明**：AS11（市场迁移）/AS13（区间迁移）/AS16（缩减）/AS19（固定资产集+0 占位）均已登记；未发现未登记的 core 要素简化（log 口径为 AS11 之下子选择，记 CA-A02 建议补登记；非 core 违规）。

**复用核查**：data.py 从 common/data_loader 复用 9 个加载/过滤函数（load_stock_price_forward / get_index_members_on_date / filter_st_stocks / get_month_end_trading_days / load_index_components / load_st_data / load_stock_trade / load_suspend_status / load_trade_calendar），SIT 特有装配（固定集选样/收益面板/日历特征/划分）未在 src 重复通用逻辑，符合复用约束。

**独立重算 vs coder 声明比对**：变更日志称"top-50 面板 4510×50、月末 215、划分 120/36/59"→ 独立运行**逐项复算一致**；AS19 称"46/50 满 test 覆盖"→ 独立实测 full_test_assets=46 属实，但进一步查明 4 只不满足中 3 只为 test_coverage=0.0 的**整段幻影**（AS19 未点明"整段 vs 部分"，据此上报 CA-A01）；均未直接采信自述。

**verdict**: pass_with_issues
