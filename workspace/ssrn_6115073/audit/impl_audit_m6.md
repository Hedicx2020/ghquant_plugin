# impl_audit_m6 · ssrn_6115073（mode=code · 对照审计）

- 审计对象：milestone **m6**（组合构建 EW/MV 与回测评估，含 R1 主结果）
- 被审元素（coverage_matrix done 行）：**F1 / F11 / B5 / B6 / B7 / B8 / R1 / R5**
- 被审代码：`common/allocation_backtest.py`、`common/utils.py`（新增指标）、`src/ssrn_6115073/{portfolio,main,strategy}.py`
- 审读分离声明：**不采信 coder/主会话自述**；权重/回测/指标/消融/R1 一律独立重算或独立读数据核对（脚本见下「独立验证证据」）
- 复现模式：experimental 市场迁移（A股三宽基）；数值对齐豁免，忠实性审计聚焦「回测未来函数 + 消融定义 + 指标公式」

---

## 一、逐 element 核对表（五维度：公式一致/参数一致/实现位置真实/代码反查/简化声明）

| 元素 | 实现位置（核对真实性） | 公式一致 | 参数一致 | 代码反查 | 简化声明 | 结论 |
|---|---|---|---|---|---|---|
| **F1** OLPS 式1-4 | `allocation_backtest.py:portfolio_backtest(491)`, `simplex_projection(49)`；`portfolio.py:run_market_portfolio(413)/run_portfolio(489)` 真实 | S_n=S0·Π(1+sₜ) 独立累乘核对 diff=0（式4）；单纯形长仓满仓 | b₁=1/m 等权初值、bₜ≥0/Σb=1 | nav*=(1+net) 累乘正确，权重和为1、非负 | AS56 登记 | 通过 |
| **F11** EW/MV | `allocation_backtest.py:equal_weights(101)/mean_variance_weights(117)/rolling_cov_estimate(568)`；`portfolio.py:selected_to_weights(209)` 真实 | EW=1/n；MV `max wᵀμ−λwᵀΣw` 长仓 SLSQP | λ=MV_LAMBDA=1.0(AS3)、min_obs=12、μ窗=60月(AS11) | MV 权重和1/非负/长仓核对通过 | AS56/AS11 登记 | 通过 |
| **B5** 在线调仓 | `allocation_backtest.py:portfolio_backtest`；`portfolio.py:run_market_portfolio/selected_to_weights` 真实 | 信号T定权重、**T+1实现收益**（独立小例证实，见二） | 月度调仓(AS4) | future=ret_index[>t]; t_next=future[0] 严格错位 | AS4/AS56 登记 | 通过 |
| **B6** 成本/市场假设 | `allocation_backtest.py:portfolio_backtest(cost_bps)`；`portfolio.py:COST_BPS_FRICTIONLESS(65)/COST_BPS_STRESS(66)`；`main.py:_cost_compare(129)` 真实 | 换手=Σ\|w_T−drift(w_prev)\| 双边；成本=换手×bps | 主回测0bp(AS5)、含成本档40bp | drift=prev_w(1+r_t)归一，首期=Σ\|w\| | AS5/AS56 登记 | 通过 |
| **B7** 指标式18-19/F.2-F.4 | `utils.py:calculate_psr(483)/sortino(425)/modigliani(455)/historical_var(522)/sharpe(173)/arithmetic_annual_return(382)/max_drawdown(230)`；`portfolio.py:compute_metrics(332)` 真实 | **6 指标独立重算全 diff≈0**（见四） | PSR SR*=0(AS22)、VaR 5%、算术年化使 SR=AR_excess/AStd 自洽 | 逐函数公式反查一致 | AS56/AS22 登记 | 通过 |
| **B8** 基准+消融 | `portfolio.py:cpm_selected(113)/pmm_selected(153)/ewmfm_selected(170)/hierarchical_panel(261)/olmar_panel(295)`；`allocation_backtest.py:hrp/herc/nco/olmar_weights` 真实 | 消融3模型忠实（见三）；HRP/HERC/NCO/Index 标准；**OLMAR 均值回归方向反转→动量（CA-A01 major）** | 同候选池+≤T协方差+同区间 | 见三/findings | AS57/AS58 登记（OLMAR 实际与 AS58「均值回归」声明相反） | **pass_with_issues** |
| **R1** 表2 | `portfolio.py:build_r1_table(523)/build_extra_table(536)/compute_metrics/run_portfolio`；`main.py:save_excel(152)` 真实 | 6比率×11方法×3市场=18行装配正确；加粗方向感知对 | RATIO_ORDER(6)/ALL_MODELS(11) 列序与 spec R1 逐列匹配=True | 加粗 min if AStd/MDD/VaR else max（方向对） | AS56 登记 | 通过 |
| **R5** 累计收益 | `portfolio.py:cumulative_returns(549)`；`main.py:_fig_cumulative_single(180)/_fig_cumulative_markets(206)` 真实 | nav−1 累计曲线；CPMM-EW 蓝加粗突出 | 三市场跨市场推广图 | 真实读 mr.nav 装配 | AS23 登记 | 通过 |

> 空壳核查：对 m6 全部文件 grep `pass$/TODO/NotImplementedError/...`，**未发现空壳**（所有 coverage_matrix 实现位置均指向有实体的函数）。无 not_found 情形。
> 复用合规：allocation 引擎落 `common/allocation_backtest.py`（非 src）、通用指标落 `common/utils.py`，`src/ssrn_6115073/portfolio.py` 仅放策略特有装配（消融选股/权重面板/R1表）；`strategy.py` 纯 re-export 全映射到元素 ID，无「私货」。合规。

---

## 二、未来函数专项（ml tag + 回测，最高优先级，独立验证）

独立脚本 `scratchpad/verify_m6.py`（合成数据，不依赖被审声明）：

1. **T+1 执行（B5/AS4）** — PASS
   - 构造：t0 全仓 A，A 仅在 t1（严格晚于 t0 的下一月）收益+50%，t0 当月收益=0。
   - 结果：`portfolio_backtest` 输出 index=[t1]，port_return=**0.5000**（=t1 月收益）。若前视纳入当月则应=0 → 实测 0.50 **排除前视**。
   - 代码定位：`allocation_backtest.py:527` `future = ret_index[ret_index > t]`；`531` `r_next = ret.loc[t_next]`——权重 w_t 只与严格晚于 T 的 t_next 收益相乘。红线守住。

2. **MV 协方差/μ 只用 ≤T（AS11/AS56）** — PASS
   - 构造：60 期收益，T=第41期定 MV 权重 w1；**篡改 T 之后全部数据（×10+5）**再算 w2。
   - 结果：w1 与 w2 **最大权重差=0.00e+00** → 证明 MV 只用 ≤T 历史，无未来函数。
   - 代码定位：`portfolio.py:243` `hist = stock_returns.loc[stock_returns.index <= t, assets]`；`244` cov、`249` `mu=hist.tail(60).mean()`——协方差扩展窗 ≤T、μ 最近60月 ≤T。

3. **建仓前 tradeable 过滤（AS5/AS8）** — PASS（过滤非空操作）
   - 独立读 m1 `tradeable_mask`：shape=(228,947)，True 占比71.3%，含 False 的(月,股)对=**62023** → 过滤实际生效（非全 True 虚设）。
   - 代码定位：`portfolio.py:237` `selected_to_weights` 与 `279` `hierarchical_panel` 建仓前均调 `_tradeable_at(tradeable_mask, t, assets)`；测试月均在 mask index（覆盖至2024-12月末）。

> 上游 CPM 选股 stage2 未来函数：`stage2_asset_forecast` 内 `g_hi=min(ep_end_pos,pos_t-2)`，预测 r̂=ret_arr[g*+1] 满足 g*+1≤pos_t-1<pos_t（严格早于信号月）——CPM `ep_end_pos=pos_t-2` 令历史窗覆盖全程但红线不变。核对通过。

---

## 三、消融定义忠实性逐一核对（AS57 · 直接决定 §九 有效性）

对照原文 p24 定义（`report_text.md:1772-1795`）+ spec B8 + plan §1.3，逐一核 **各消融只关掉对应环节、其余不变**：

| 消融 | 原文定义 | 应关环节 | 实现（portfolio.py） | 独立核对 | 忠实性 |
|---|---|---|---|---|---|
| **CPM-EW/MV**（去宏观） | "without considering macroeconomic data, namely clustered pattern-matching approach" | 去掉 stage1 宏观经济周期筛选（+宏观因子/溢出维度），**保留聚类+价格匹配** | `cpm_selected(113)`：`stage2_asset_forecast(...,ep_end_pos=pos_t-2,ep_span=pos_t+1)` 令价格窗**全历史**匹配得单一 r̂_j；`groupby("cluster")` 每簇选 r̂ 最高>0（保留 m3 簇标签） | 首测试月 CPM 选10只、与 CPMM 完全不同标的（用 r̂ 而非 FS）；聚类保留✓ | **忠实** |
| **PMM**（去聚类） | "treats the data as a single cluster, without involving any clustering... pattern-matching approach based on macroeconomic factors" | 去掉聚类分组，**保留宏观 pattern matching + 溢出加权 FS** | `pmm_selected(153)`：用 `sp_result.fs_panel[t]`（**真实 γ̃ 加权 FS**）全候选降序选 top-nc(FS>0)，不分簇 | 首测试月 PMM 选10只(=nc)、用与 CPMM 同一 FS 但全局 top-nc；宏观+溢出保留✓ | **忠实**（top-nc 而非单簇选1，AS57 明确登记为「与 CPMM 选等量、唯一差别是否聚类」的干净隔离，方法学正确——若取1只则混淆持仓数与聚类两个变量） |
| **EWMFM**（去溢出加权） | "equal weights for macroeconomic factors, without considering joint effects" | 溢出权重 γ̃→1（等权），**保留聚类+宏观 pattern matching+每簇选一** | `ewmfm_selected(170)`：`gamma_eq=pd.Series(1.0)`；`aggregate_fs(sig, gamma_eq)`=Σsignal；`select_per_cluster(...,fs_floor=0.0)` 每簇选一 | γ̃≡1 独立核对=Σsignal(diff=0)；与全量 CPMM 唯一差异是 γ̃；实测 CPMM∩EWMFM=5/CPMM\EWMFM=5、EWMFM 选8只（部分簇 Σsignal≤0）✓ | **忠实** |

**关键交叉验证**：全量 CPMM 本体（`spillover.py:447` `gamma_series=table.gamma_weight` 真实溢出权重 + `select_per_cluster` fs_floor=FS_LONG_ONLY_FLOOR=0.0）与 EWMFM（γ̃≡1，fs_floor=0.0）**除 γ̃ 外全部一致**——单变量隔离干净。CPM 用同一 m3 簇标签，PMM 用同一 fs_panel，均只改一个环节。**三消融定义均忠实，§九.2 消融对比的定义基础成立**（消融结果本身 PMM>CPMM 是 A股月频聚类弱的迁移发现，属 verify/diagnose 判定范畴，非定义错误）。

> 注：`run_market_spillover` 存在 VAR 样本不足时 γ̃ 退化等权的 fallback（`spillover.py:460`），届时 CPMM=EWMFM。实测 hs300 VAR p=3/144训练月成功、table.ok=True → γ̃ 为真实值，隔离成立（非退化态）。

---

## 四、指标独立重算对照（B7 · 不采信声明）

**（a）合成数据公式核对**（`verify_m6.py`，60期）：SR/PSR/SOR/MR/VaR/MDD 手算 vs 代码 **全部 diff≈0（≤8e-17）**；SR=AR_excess/AStd 自洽（式18）diff=8e-17。PSR 按 Bailey-LdP 2012（月度 ŜR+偏度γ3+峰度γ4+√(n-1)）逐项手算吻合。

**（b）真实管线 CPMM-EW hs300 抽查**（`recompute_r1.py`，跑全链 m1→m6，独立重算 vs mr.metrics）：

| 模型(hs300) | SR(metrics) | SR(独立重算) | SR(AR_excess/AStd) | PSR(metrics) | PSR(独立重算) | 对照 |
|---|---|---|---|---|---|---|
| CPMM-EW | 0.60419 | 0.60419 | 0.60419 | 0.94225 | 0.94225 | 逐位一致 |
| CPMM-MV | 0.79287 | 0.79287 | 0.79287 | 0.98858 | 0.98858 | 逐位一致 |
| CPM-EW | 0.42823 | 0.42823 | 0.42823 | 0.87494 | 0.87494 | 逐位一致 |
| PMM | 0.72868 | 0.72868 | 0.72868 | 0.96946 | 0.96946 | 逐位一致 |
| EWMFM | 0.51017 | 0.51017 | 0.51017 | 0.90113 | 0.90113 | 逐位一致 |

R1 表内自洽核对：SR=(AR−rf_ann)/AStd 全表成立，rf_ann≈2.79%（rf_mean 月=0.00232×12），与 A股 SHIBOR 量级一致。指标公式**无实质错误，R1 未因指标失真**。
> MR 量级说明：实现严格按式F.4 `MR=SR·σ_b+rf_ann`（σ_b=指数月收益年化波动），故本迁移 MR≠SR（原文表 MR≈SR 属原文口径/尺度特性）；experimental 数值豁免，公式忠实，非 finding。

---

## 五、Findings（id | severity | 文件:行号 | 描述 | 建议）

### CA-A01 | **major** | `common/allocation_backtest.py:472-473`（`olmar_weights`）
- **描述**：OLMAR 的 SMA 预测方向**反转**。代码 `ratios=np.cumprod(pr[::-1]); x_tilde=ratios.mean(axis=0)` 计算的是 `mean(p_t/p_{t-i})`（current/past），对上涨资产 x_tilde>1 → `diff=x_tilde−x_bar>0` → **加仓涨方（动量）**。而标准 OLMAR（On-Line Moving Average **Reversion**，Li & Hoi 2012）预测 `x̃=SMA/p_t=mean(p_{t-i}/p_t)`（past/current），对上涨资产 x̃<1 → 减仓涨方（**均值回归/contrarian**）。代码注释自称「近似 SMA/p_t」但实际算的是其**倒数方向**，与 spec B8 命名及 AS58「SMA 均值回归」声明**语义相反**，实为动量策略（未登记的方向偏离）。
- **独立证据**：`verify_olmar.py` 构造 A 持续涨/B 持续跌，OLMAR 更新后权重 A=1.0/B=0.0（加仓涨方=动量）；标准 x̃ 应 A=0.83/B=1.24（减仓涨方）。数值佐证：R1 中 OLMAR AStd=0.61(hs300)/0.50(sz50)/1.02(zz500)，为其它基准的 3-5 倍，与「反转成动量致极端集中高波动」一致。
- **影响面**：仅波及 R1 中 OLMAR 一列与 §九.3「CPMM vs 外部基准」的 OLMAR 对照；**不触及主模型 CPMM、消融链 CPM/PMM/EWMFM（§九.2 核心有效性不受影响）**，且 OLMAR 系 5 外部基准之一，故定 **major** 非 critical（若 verify 认为 §九.3 基准忠实性为达标硬条件可上调）。
- **建议**：`x_tilde` 改为 `(1.0/np.cumprod(pr[::-1], axis=0)).mean(axis=0)`（或直接用价格序列 SMA(w)/p_t），使预测为 past/current 的均值回归方向；修复后 OLMAR 列需重跑，AStd 应回落至基准量级。coverage_matrix B8 行状态建议回退 in_progress 并在变更日志记 OLMAR 方向修正。

### CA-A02 | **minor** | `src/ssrn_6115073/portfolio.py:203-204`（`_tradeable_at`）
- **描述**：文档-代码不一致。docstring（200-201）称「tradeable_mask 无该记录时**保守视为不可交易**」，但当调仓月 t 不在 mask.index 时代码 `return [a for a in assets if a in tradeable_mask.columns] or list(assets)` 实为**允许全部资产**（permissive），与「保守」相反。
- **影响**：实测测试月（2019-2024）**均在 mask.index**（228 期月末覆盖至 2024-12），该边界分支不触发，故对 m6 结果无实际影响 → minor。
- **建议**：订正 docstring，或将 t 缺失分支改为返回空列表（真正保守），与逐资产分支（206 行仅保留 True）口径统一。

---

## 六、已检查维度清单（五维度全覆盖，无遗漏）

- [x] **公式一致**：F1 OLPS 累乘、F11 EW/MV、B7 六指标（SR/PSR/SOR/MR/VaR/MDD）独立重算全 diff≈0；OLMAR 方向反转已记 CA-A01。
- [x] **参数一致**：λ=1(AS3)、cov min_obs=12/μ窗60月(AS11)、PSR SR*=0(AS22)、cost 0/40bp(AS5)、VaR 5%、RATIO/MODEL 列序与 spec R1 匹配——逐项对齐假设。
- [x] **实现位置真实**：coverage_matrix F1/F11/B5-B8/R1/R5 全部实现位置指向有实体函数；grep 无 pass/TODO/空壳；无 not_found 情形。
- [x] **代码反查**：T+1 对齐、MV≤T（篡改未来测试）、tradeable 过滤、消融隔离、指标——逐条反查；发现 OLMAR 语义反转(CA-A01)、tradeable 文档不符(CA-A02)。
- [x] **简化声明**：AS56（EW/MV/回测/指标口径）、AS57（消融三模型）、AS58（五基准）均登记；OLMAR 实现与其 AS58 声明相反（未登记方向偏离，已计 CA-A01）。
- [x] **未来函数专项**：T+1 执行 ✓、MV 协方差/μ ≤T（篡改核对权重不变）✓、建仓前 tradeable 过滤 ✓——三项独立验证全 PASS。
- [x] **消融定义忠实性**：CPM 去宏观 ✓、PMM 去聚类 ✓、EWMFM 去溢出 ✓——三消融均单变量隔离，§九 对比定义基础成立。
- [x] **指标独立重算**：CPMM-EW hs300 等 5 模型 SR/PSR 真实管线重算逐位吻合。

---

**verdict**: pass_with_issues
