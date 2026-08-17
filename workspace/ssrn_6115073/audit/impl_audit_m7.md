# 实现忠实性审计 · m7 稳健性与敏感性分析 · ssrn_6115073

- 审计模式: code（对照审计，只拿文件不采信 coder 自述；数值独立重算）
- milestone: m7（B3/B4/SA1/SA2/SA3/SA4，experimental 市场迁移，tags 含 ml → 未来函数必查）
- 被审文件: `src/ssrn_6115073/robustness.py`（33564 B）
- 上游只读参照（不审）: m1-m6 全部模块 + common/allocation_backtest.py
- 独立重算脚本: 仓库根跑 `build_and_run()`（m1-m6 全链）+ `build_sa1/2/3/4`（纯计算，**不写任何产物**，未触碰 output/ 下 coder 产出）

---

## 已检查维度清单（设计 §9.3 五维度，无遗漏）

1. **公式一致**：SA1/SA2 子窗指标（B7 全套 via `compute_metrics`）、SA3 强制 nc 层次切割（D=1−SU→ward）、强制 w 两阶段匹配（式26 stage2）、FS 溢出聚合（式37）、每簇选一（式36/AS17）、EW/MV 建仓——逐一比对上游 m2-m6 引擎函数，均忠实复用。
2. **参数一致**：`ROLLING_SUBPERIODS` / `OOS_TAIL` / `PARAM_OFFSETS` / `LAMBDA_GRID` / `SA1_METHODS`(10) / `SA2_SETTINGS`(6) / `SA3_RATIO_MAP` 与 spec 表3/5/7 + AS3/AS14/AS59/AS60/AS61 逐值核对。
3. **实现位置真实**：coverage_matrix B3/B4/SA1-4 六行登记的函数全部存在且名副其实（无 pass/TODO/占位/stub）。
4. **代码反查（独立重算）**：base 三路径 Δ 独立复算=0；w=base 逐月 selected 0/72 差异；`_forced_nc_labels(base_nc)` 与 canonical 簇标签 0/40 差异；SA1-4 独立重建逐格复现 coder Excel。
5. **简化声明**：AS59（SA1 切已实现收益子窗）/AS60（SA2 尾窗与 oos 区分）/AS61（SA3 三路径 base 复现校验）/AS62（SA4 γ̃≡1 隔离）四条主动简化均已登记；未发现未登记偏差。

---

## 逐 element 核对表（B3/B4/SA1/SA2/SA3/SA4）

| 要素 | 登记实现位置 | 存在性 | 公式/参数忠实性 | 独立重算结论 |
| --- | --- | --- | --- | --- |
| **B3** 滚动子区间 | `robustness.py:85 ROLLING_SUBPERIODS`, `:257 build_sa1` | 真实 | 2019-2022/2020-2023/2021-2024 三个等长 4 年、1 年滚动窗（AS21/AS59）；切 base 已实现收益日期子窗、窗内 nav 重定基（`_window_metrics` nav=None） | 3 窗×4 比率×3 市场=36 行，与 Excel `SA1_滚动子区间`(36,13) 逐格一致 |
| **B4** 样本外区间 | `robustness.py:99 OOS_TAIL`, `:306 build_sa2` | 真实 | 尾窗 2023-01..2024-12（24 月，AS34/AS60），与 oos 阶段（>2024）区分；同为切已实现收益子窗 | 4 比率×3 市场=12 行，与 Excel `SA2_样本外尾窗`(12,8) 一致；hs300 CPMM-EW SR=−0.1029 独立复算一致 |
| **SA1** 表3 滚动稳健 | `build_sa1`, `_window_metrics`, `SA1_METHODS` | 真实 | 10 方法（6 内部消融+HRP/HERC/OLMAR/NCO，**无 Index**）×AR/AStd/SR/PSR；领先性按 SR 排名 | 领先性 9 行独立重建逐格复现（hs300 2021-2024=5/10、sz50/zz500 2020-2023=1/10 等）；口径匹配 spec 表3 |
| **SA2** 表5 样本外稳健 | `build_sa2`, `_window_metrics`, `SA2_SETTINGS` | 真实 | 仅 6 内部设置（无外部基准，spec「six settings」）×4 比率×3 市场 | 独立重建 SR 行逐格一致；口径匹配 spec 表5；AS13 表5 SR 笔误按自算处理（不采信原表异常值）落地 |
| **SA3** 表7 参数敏感 | `build_sa3`, `_forced_nc_labels`, `_signals_forced_w`, `_backtest_selected` | 真实 | 主市场 hs300；nc{8,9,10,11,12}/w{5,6,7,8,9}/λ{0.25,0.5,1,2,4}，base 于列3（AS14 nc+1 修正对称、AS3 λ 网格）；Return=AR/Std=AStd/SR/PSR | 12 行独立重建逐格复现 Excel；三路径 base 列均 Δ=0（见下专项） |
| **SA4** 图15 单因子 | `build_sa4`, `_fs_from_signals`, `_select_from_fs` | 真实 | hs300 CPMM-EW，仅用 f（γ̃≡1 隔离信号/AS62）/剔除 f（base γ̃ 其余 6）；baseline 全 7 因子 | 7 因子行独立重建逐格复现；baseline_SR=0.6042 复现 base CPMM-EW；PMI 唯一剔除ΔSR<0、GDP ΔSR=0 自洽 |

---

## 未来函数专项（ml tag 必查）

结论：**未发现任何未来函数/跨区间泄漏/参数偷看测试**。逐条证据：

1. **SA1/SA2（B3/B4）无泄漏**：`_window_metrics`（`:119-137`）仅对 base 链**已实现的 T+1 净收益序列** `mr.port_returns` 做日期切片再 `compute_metrics`（nav=None 窗内重定基），**不重跑策略、不重估任何参数**。策略 w/nc/γ̃ 全部 train-once（≤train_end 2018），SA1/SA2 只评估 2019-2024 已实现收益 → 子区间稳健性=同一策略在不同评估窗表现，结构上不可能跨窗泄漏或偷看测试。
2. **SA3-w 保持 stage2 因果约束**：`_signals_forced_w`（`:207-250`）逐行复刻 `pattern_matching.run_market_pattern_matching` 内层循环，仅把 w 由 `search_optimal_window` 定值改为外部指定；`stage2_asset_forecast` 的未来函数红线 `g_hi=min(ep_end_pos, pos_t−2)`（历史窗口之后一期 g+1 ≤ pos_t−1 < 信号月）原样保留，w 变大不放松该约束。stage1（`stage1_macro_period`）与 w 无关，跨 w 缓存复用正确。
3. **train-once 不随子窗/网格重估**：SA3-nc 复用 base `sp.fs_panel`（FS 与 nc 无关）、SA3-λ 复用 base 选股 `sp.selected`、SA4 复用 base `sig.signals`/`gamma_weight`——受敏感性参数影响的环节才重算，训练期定参不被任何子窗/网格触碰。
4. **抽 1 子区间核对**：独立复算 w=base 路径逐测试月 selected 与 base `sp.selected` **0/72 月不一致**，证明强制-w 重跑管线未引入任何时点错位或数据借用（T+1 执行由 `portfolio_backtest` 硬保证，本模块 cost_bps=0=base）。

---

## 参数化重跑同构性独立核验（关键）

独立跑 `build_and_run()` 取 **base m6 真值**（直接读 `ports`，非 robustness 重算），再逐路径复算比对：

| 项 | 独立复算值 | 对照 base m6 真值 | Δ |
| --- | --- | --- | --- |
| base CPMM-EW SR（hs300，取自 ports） | 0.604190 | — | 基准 |
| base CPMM-MV SR（hs300，取自 ports） | 0.792874 | — | 基准 |
| **nc=base** 路径（`_forced_nc_labels`+`_select_from_fs`+`_backtest_selected` ew） | 0.604190 | 0.604190 | **+0.000000e+00** |
| **w=base** 路径（`_signals_forced_w`+`_fs_from_signals`+`_select_from_fs`+ ew） | 0.604190 | 0.604190 | **+0.000000e+00** |
| **λ=base** 路径（base_selected + `_backtest_selected` mv, lam=1） | 0.792874 | 0.792874 | **+0.000000e+00** |

- coder 称「CPMM-EW SR=0.6042 Δ=0 / CPMM-MV 0.7929 Δ=0」——**独立核对属实，非虚报**。
- **边界情形排除**：`_forced_nc_labels(su, base_nc=10)` vs canonical `cluster_labels`——键集合一致、**标签逐股票 0/40 不一致**。即 `fcluster(maxclust)` 在 nc=10 处恰好产出 10 个有效簇（未出现 n_eff<nc 的退化），故 SA3-nc 基准列忠实复现 base，无隐患。
- **同构性结构证据**：`_backtest_selected`（`:185-204`）与 `portfolio._run_one_model` 的 CPMM 路径逐段等价——同 `selected_to_weights`（同 stock_returns/tradeable/build/lam）、同 `portfolio_backtest(cost_bps=0.0=COST_BPS_FRICTIONLESS)`、同 `compute_metrics(index_returns, rf, nav)`。

**SA3 单参数隔离证据（非混合扰动）**：三条网格各自只变一个参数、其余 hold 在 base——

- **nc 组**：复用 base `sp[m].fs_panel`（w/γ̃ 冻结在 base）+ 仅 `_forced_nc_labels` 改簇数 → 仅 nc 变。
- **w 组**：复用 base `gamma`（`sp.gamma_weight`）+ base `cluster_labels`（nc 冻结）+ 仅 `_signals_forced_w` 改窗口 → 仅 w 变。
- **λ 组**：复用 base `sp.selected`（选股冻结）+ 仅 `selected_to_weights(build='mv', lam=λ)` 改风险厌恶 → 仅 λ 变。
- 验证：nc 列3 == w 列3 == base_ew（0.6042）、λ 列3 == base_mv（0.7929），各基准列均 Δ=0，佐证「holding others at base」的单参数隔离成立，SA3 敏感性结论口径有效。

---

## SA4 单因子隔离忠实性核验

- **仅用 f（`_fs_from_signals(signals, ones, [f])`，γ̃≡1）**：单因子 FS_j=signal_{f,j}，符号=信号符号；对 γ̃_f>0 因子与用 base γ̃ 选股等价（单因子正权量级不改 argmax），对 min-max γ̃=0 因子（hs300 GDP）避免 FS≡0 空仓退化——AS62 口径落地正确。
- **剔除 f（`_fs_from_signals(signals, gamma, others)`，base γ̃ 其余 6）**：FS_j=Σ_{i≠f}γ̃_i·signal，即 CPMM-EW 去一因子，无退化。
- **GDP 自洽性独立确认**：剔除 GDP 后 ΔSR=**0.0000**（剔除==baseline），证 γ̃_GDP=0、从不进 base FS，内部自洽；「仅用 GDP」因 γ̃≡1 得 SR=0.3860 非退化。
- 独立重建 7 因子行逐格复现 Excel：仅 PMI 剔除ΔSR<0（−0.0610）、PPI 仅用_SR=0.5155 最高——A股迁移下 PMI（非原文 CPI/IR）最关键，coder 如实报数、判定归 verify（AS24 描述矛盾按自算落地）。

---

## SA 表口径核对（对照 spec 表3/5/7）

| 口径项 | spec 要求 | robustness 实现 | 结论 |
| --- | --- | --- | --- |
| SA1 方法集 | 10 approaches 无 Index（表3） | `SA1_METHODS` 10 个、无 Index（`:91-93`） | 一致 |
| SA2 设置集 | 6 settings 无外部基准（表5） | `SA2_SETTINGS` 6 内部（`:101`） | 一致 |
| SA1/SA2 比率 | AR/AStd/SR/PSR | `SA_RATIOS` 四比率（`:95`） | 一致 |
| SA3 表头对称 | nc+1 修正、base 于列3（AS14） | `PARAM_OFFSETS=(-2..2)`、列3 标「(基准)」（`:381`） | 一致 |
| SA3 λ 网格 | λ−2..λ+2（AS3） | `LAMBDA_GRID={0.25,0.5,1,2,4}`（`:107`） | 一致 |
| SA3 指标口径 | Return/Std/SR/PSR | `SA3_RATIO_MAP` Return→AR/Std→AStd（`:109`） | 一致 |
| 领先性口径 | 表3 CPMM「consistently surpassed」 | SA1 提供 CPMM-EW SR 排名摘要（`:278-286`），SR 越大越优、方向正确 | 一致（见 CA-A01 minor 说明） |

---

## 空壳核查

robustness.py 全文无 `pass`/`TODO`/`FIXME`/`NotImplementedError`/`...`/占位/stub；coverage_matrix B3/B4/SA1-4 登记的 `ROLLING_SUBPERIODS`/`build_sa1`/`OOS_TAIL`/`build_sa2`/`build_sa3`/`_forced_nc_labels`/`_signals_forced_w`/`_backtest_selected`/`build_sa4`/`_fs_from_signals`/`_select_from_fs` 全部为实体函数（`_signals_forced_w` 50 行、`build_sa3` 93 行、`build_sa4` 53 行等），逐一经独立重算产出真实数值。**六 element 实现位置均真实存在且名副其实，无一为空壳**。

---

## findings

| id | severity | 证据定位 | 描述 | 建议 |
| --- | --- | --- | --- | --- |
| CA-A01 | minor | `robustness.py:473-486`（`_format_ws` 仅表头加粗）；对照 spec 表3/5/7 加粗最优列 | SA1/SA2/SA3 Excel 未在数据单元格复制原文「加粗最优」标注；SA1 以 SR 领先性摘要替代、SA2/SA3 无最优列标注。属实验模式「本表只报数、判定归 verify」的一致设计（`_mode_note`），原始值齐全且正确、方向口径无误，**不影响忠实性**。 | 非阻断；如 report/verify 阶段需与原表逐格视觉对照，可据值方向感知补标（SR/AR/PSR 取最大、AStd 取最小） |
| CA-A02 | minor | `robustness.py:278-286`（`order=sorted(...); rank=order.index("CPMM-EW")+1`） | SA1 领先性排名在 SR **完全相等**时按 `SA1_METHODS` 插入序稳定排序，CPMM-EW 居前（略利于自身）。4 位小数 SR 相等在真实数据近乎不可能，独立重建 9 行未见并列。 | 非阻断；若追求严谨可对并列 SR 采用「并列同名次」或加极小抖动，当前无实质影响 |

> 两条均为 minor 级非阻断观察，不涉及公式/参数/位置/同构/未来函数任何忠实性或正确性缺陷。

---

## 防幻觉三约束声明

1. **只读不采信自述**：全程只读 robustness.py 与上游模块、spec/assumptions/coverage_matrix；未读取、未引用 coder 的完成汇报；Δ=0、base 真值、簇标签一致性、SA 表数值一律亲自重算，不引用 coder 自述结论。
2. **数值独立重算**：仓库根独立跑 `build_and_run()` 取 base m6 真值（0.604190/0.792874）+ `build_sa1/2/3/4` 逐格复现，比对 coder Excel；三路径 Δ、逐月 selected 0/72、簇标签 0/40 均为独立复算所得（脚本 `scratchpad/verify_m7.py`，未写任何产物、未触碰 output/）。
3. **证据定位**：每条核对与 finding 均给 `文件:行号` 或 spec 要素/AS 编号定位，可回溯。

**verdict**: pass
