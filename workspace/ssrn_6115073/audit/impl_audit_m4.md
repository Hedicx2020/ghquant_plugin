# 实现忠实性审计 · m4 两阶段 Matrix Profile 模式匹配与信号（ssrn_6115073）

- 模式: code（对照审计，只拿文件不采信 coder 自述，索引/匹配/信号一律独立追索重算）
- 被审: `src/ssrn_6115073/pattern_matching.py`（F5/F6/F7/F8）
- 上游只读不审: `data_prep.py`(level_panel/stock_returns 构造)、`selection.py`(候选集)
- 规格: spec.md 三、F 类 F5(式15-17)/F6(式20-23)/F7(式24-26)/F8(式27)；plan m4；AS7/AS10/AS49/AS50/AS51
- 审计日期: 2026-07-11
- 独立重算脚本: 30 项断言全 PASS（scratchpad/verify_m4.py，纯 numpy 构造直调纯函数）

---

## 一、逐 element 五维度核对表（设计 §9.3：公式一致 / 参数一致 / 实现位置真实 / 代码反查 / 简化声明）

### F5 最优窗口 w（相关性预测 + MSE，式15-17）

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 公式一致 | 基本一致（一处归一化未登记，见 CA-A01） | `_window_prediction_sse`(232) 末窗与各前窗 Pearson 相关→rescale (ρ+1)/2 到[0,1]（式15 权重，277 行 `weight=(corr+1)/2`）→相关加权预测 next→累加 SSE(式16)；`search_optimal_window`(284) 平均 MSE=ΣSSE/Σpts 取最小者(式17，320/324-325) |
| 参数一致 | 一致 | w∈{2..10}(WINDOW_GRID,78, AS7)；月频步长(AS7/AS10)；MIN_TRAIN_PRED_POINTS=12 小样本噪声门槛(88, AS50 登记 w=7/9/9) |
| 实现位置真实 | 真实 | search_optimal_window(284)/_window_prediction_sse(232)/_pearson_corr_to_windows(210) 均有实体，非空壳 |
| 代码反查 | 无越权 | 仅消费训练切片 `R.loc[train_sel]`(482-483)；投毒测试期→optimal_w 与各 w MSE 逐值不变（独立验证 PASS）；无对测试期/未来的隐性引用 |
| 简化声明 | 大体已登记 | w/nc 解耦(w→m4、聚类 nc→m3 Silhouette)声明 AS7+AS50；stumpy 退化 AS49。**归一化除 Σweight 未登记→CA-A01** |

### F6 Matrix Profile（Z-归一化欧氏距离剖面 / 矩阵剖面，式20-23）

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 公式一致 | 一致（独立重算坐实） | `znorm_distance_profile`(135) 总体 std Z-归一化欧氏距离，独立验证 d²=2m(1−ρ) 最大误差 **2.132e-14**；`causal_matrix_profile`(168) M=[min(D_i)]+最近邻索引，且为 **left-MP**（历史邻居 j≤i−m，不重叠且严格更早，193 行 `hi=i−m`，独立核对 nn 索引全满足 j≤i−m）|
| 参数一致 | 一致 | 子序列长 m（宏观 stage=12、资产 stage=w，AS10）；ZNORM_STD_EPS=1e-8 常数窗口(无形状信息)→+inf 合理(91/154/160) |
| 实现位置真实 | 真实 | znorm_distance_profile(135)/causal_matrix_profile(168) 均有实体 |
| 代码反查 | 无越权 | 常数窗口/含 NaN 窗口→inf 不参与匹配(163-164)，符合定义；causal_matrix_profile 供诊断，signal 路径用 znorm_distance_profile 精确控历史区间(F7)，二者一致无冲突 |
| 简化声明 | 已登记 | stumpy 缺→自实现声明 AS49；SignalResult.matrix_profile_impl 记 'self_znorm'/'stumpy'(474/128) |

### F7 两阶段 pattern matching（宏观 MSP + 资产窗口预测，式24-26）

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 公式一致 | 一致 | 阶段1 MSP'=min[SP]（式24，`stage1_macro_period` argmin 距离,380）；EP 结束于 h*、跨度 ep_span（式25,415）；阶段2 r̂=最相似**单**窗口之后一期实际收益（式26，argmin 后 `return next_vals[k]`,434-437；独立追索源位置逐值一致），单窗口对齐 AS51「最相似单窗口」非加权 |
| 参数一致 | 一致 | macro_m=12(AS10,81)/ep_span=12(AS51,85)；阶段1 窗口=12月、阶段2 窗口=w(F5)；EP_SPAN 派生自 AS10 经济周期=一年 |
| 实现位置真实 | 真实 | stage1_macro_period(339)/stage2_asset_forecast(383)/run_market_pattern_matching(451)/run_pattern_matching(529) 均有实体 |
| 代码反查 | 无越权 | 阶段1 per 因子算 h* 后缓存复用给该月全资产(507)；阶段2 per 资产(513-516)；信号矩阵 index=资产/columns=因子(508)对齐 F8/F10 消费口径；excluded_narrow_pool→空信号保结构(490-496)，sz50 落 Tier2_degraded 仍产信号(对齐 AS44)。**未来函数专项见 §二，全部 PASS** |
| 简化声明 | 已登记 | 两阶段历史区间口径 + 未来函数硬约束声明 AS51；EP_SPAN=12 声明 AS51 |

### F8 信号提取二值化 ±1（式27）

| 维度 | 结论 | 证据 |
| --- | --- | --- |
| 公式一致 | 一致 | `signal_from_rhat`(440)：r̂>0→+1、r̂≤0→−1（444 `1.0 if r_hat>0.0 else -1.0`，else 覆盖 ≤0 含 0）、NaN→NaN(442-443)；独立验证四分支全 PASS |
| 参数一致 | 一致 | 二值 {+1,−1,NaN}；NaN 不强制 −1（AS51），inf 经 isfinite 拦截为 NaN |
| 实现位置真实 | 真实 | signal_from_rhat(440) 有实体 |
| 代码反查 | 无越权 | `rhat_mat.map(signal_from_rhat)` 逐格映射(517)，无对 r̂ 的隐性改写 |
| 简化声明 | 已登记 | NaN→NaN 口径声明 AS51；m5 按缺失处理 |

**空壳核查结论**：F5/F6/F7/F8 在 coverage_matrix 声明的 10 个实现函数逐一 grep 确认真实 `def` 存在且函数体非空（无 `pass`/`...`/`TODO`/`FIXME`/`NotImplementedError`）；本 milestone 无空壳、无实现位置回退项。

---

## 二、未来函数专项（最高优先级：逐行索引边界分析 + 反例验证）

> 本 milestone 为全案最高未来函数风险点（历史窗口模式匹配）。以下**不采信 coder 自述**，逐行读代码追索整数位置索引边界，并用扰动/投毒反例坐实「pos_t 时刻取不到未来数据」。

### 上游前提（只读核对，成立）
- `stock_returns`：前复权 close 的 `pct_change`，index=月末，首月 NaN（data_prep:75）→ ret_arr[pos_t] 为月 t 已实现收益，t 时点已知。
- `level_panel`：披露日 `merge_asof(direction="backward")` asof 对齐（data_prep:88/349-356）→ level_arr[pos_t] 为月末 t 已披露的最新宏观值，非未来函数。stage1 用 pos_t 端点 query 依赖此前提成立。

### 阶段1 `stage1_macro_period`（358-380）逐行索引边界
- 358-361：`lo_q=pos_t−macro_m+1`；`query=level_arr[lo_q:pos_t+1]` → 闭区间 [pos_t−m+1, pos_t]，长度 m，**结束于 pos_t**（当前已披露，允许）。
- 365-366：`h_lo=macro_m−1`；`h_hi=pos_t−macro_m` → 历史候选窗口结束 **h ∈ [m−1, pos_t−m]**。
- 边界证明：max h = pos_t−m。对应窗口 level_arr[h−m+1:h+1] = [pos_t−2m+1, pos_t−m]，结束位置 pos_t−m **< pos_t**（严格早于信号月），且与 query [pos_t−m+1, pos_t] **无交叠**（历史窗口结束 pos_t−m，query 起于 pos_t−m+1）。阶段1 触及的最大位置 = pos_t（query 端点）与 pos_t−m（匹配靶），**无 ≥pos_t+1 未来数据**。
- 反例验证（pos_t=150, m=12）：① 扰动 level[151:] 任意值 → h* 不变（PASS，无未来依赖）；② h* 实测 ≤ pos_t−m=138（PASS，边界）；③ 投毒：把未来某窗口做成 query 完美复制 → h* 仍 ≤138 不落未来（PASS，未来完美匹配也取不到）。

### 阶段2 `stage2_asset_forecast`（408-437）逐行索引边界
- 408-411：`query=ret_arr[pos_t−w+1:pos_t+1]` → [pos_t−w+1, pos_t]，长度 w，结束 pos_t（已实现收益）。
- 415-417：`ep_start=ep_end_pos−ep_span+1`；`g_lo=max(ep_start+w−1, w−1)`；`g_hi=min(ep_end_pos, pos_t−2)`。
- 424-437：逐 g 取窗口 `ret_arr[g−w+1:g+1]`、之后一期 `ret_arr[g+1]`；argmin 距离后 `return next_vals[k]`（r̂=最相似窗口之后一期收益）。
- 边界证明（关键）：`ep_end_pos = 阶段1 的 h*`，而 h* ≤ pos_t−macro_m = pos_t−12。故 `g_hi = min(ep_end_pos, pos_t−2) = ep_end_pos ≤ pos_t−12`。**r̂ 源位置 = g*+1 ≤ g_hi+1 ≤ pos_t−11 < pos_t**。→ `pos_t−2` 冗余守卫（belt-and-suspenders，正常永不触发，实际约束由阶段1 h* 上界主导），r̂ 源恒 ≤ pos_t−11，绝无未来。
- 反例验证：① 扰动 ret[151:]=777 → r̂ 不变且绝不等于 777（PASS）；② 独立追索 g*=136、r̂源 g*+1=**137 < 150**（PASS）、r̂==ret[137] 逐值一致（PASS）；③ 投毒：未来做出 query 完美匹配窗口且其之后一期=sentinel 999 → r̂ 不取 999、与原值一致（PASS，未来完美匹配窗口被候选集排除在外）。

### F5 训练期不偷看测试期
- 482-483：`train_sel=(month_ends≥train_start)&(≤train_end)`；`ws=search_optimal_window(R.loc[train_sel], ...)` → 仅训练切片进入 w 搜索。
- 反例验证：把测试期行投毒为 1e6 重算 → optimal_w 与各 w 的 MSE **逐值不变**（PASS）→ 坐实 w 选择与测试期完全解耦。训练/测试月末集无交集、训练末<测试首（PASS）。

### 信号错位（T 算 / T+1 执行）
- m4 只产 T 月末信号：`signals[t]` 键为测试月 t、仅用 ≤pos_t 信息；执行错位（T+1）由 m6 承接（代码 24 行注释 + AS4/AS51）。核对到位，非本 milestone 职责。

**未来函数专项结论：阶段1/阶段2/F5 三处红线独立追索 + 扰动 + 投毒反例全部通过，未发现任何未来函数泄漏。**

---

## 三、MP 距离独立重算证据

| 检验 | 期望 | 实测 | 结论 |
| --- | --- | --- | --- |
| d²=2m(1−ρ) 随机 200 窗口 | max误差→0 | max\|d²−2m(1−ρ)\|=**2.132e-14** | 通过（机器精度） |
| 完全正相关 [1,2,3]vs[2,4,6] | d=0 | 0 | 通过 |
| 完全反相关 [1,2,3]vs[3,2,1] | d=√12 | √12 | 通过 |
| 常数候选窗口 | →+inf | inf | 通过 |
| causal_matrix_profile 最近邻 | j≤i−m 全满足 | 无违例 | 通过（left-MP 不重叠） |

Z-归一化欧氏 MP 与 stumpy 定义唯一等价（AS49），实现忠实。

---

## 四、findings

| id | severity | 定位 | 描述 | 建议 |
| --- | --- | --- | --- | --- |
| CA-A01 | minor | src/ssrn_6115073/pattern_matching.py:277 | F5 相关加权预测按 Σweight 归一化为加权平均（`pred=Σ(weight·next)/Σweight`,277），式15 字面 `rbn′+1,j=Σ_ι(rWι,j×Cm−1,ι)` 为未归一化和。归一化是「预测下一期收益」的合理近必需读法（spec F5 已声明 rescale[0,1] 且明示"预测下一期收益"，未归一化原始和无法作收益预测），但「除以 Σweight」这一步未在任何 AS 显式登记，属未登记的实现口径细节。 | 在 assumptions 补登该权重归一化口径以完整可追溯；因仅影响超参 w 选择、market-transplant 数值豁免，不阻断下游。 |

无 critical、无 major。未来函数、MP 公式、两阶段逻辑（式24/26）、F8 二值化、实现位置真实性、训练期隔离均无问题。

---

## 五、已检查维度清单（无遗漏声明）

- 五维度 × F5/F6/F7/F8：公式一致 / 参数一致 / 实现位置真实 / 代码反查 / 简化声明 —— 逐格核对完毕（§一）。
- 未来函数专项：阶段1 索引边界(h≤pos_t−m) + 阶段2 索引边界(g+1≤pos_t−11<pos_t) + F5 训练期隔离，各含逐行分析 + 扰动 + 投毒反例（§二）。
- MP 独立重算：d²=2m(1−ρ) + 极值 + 常数窗口 + left-MP 不重叠（§三）。
- 空壳核查：10 个声明函数真实存在、函数体非空、无 pass/TODO/NotImplemented。
- 上游前提核对：stock_returns/level_panel asof 对齐支持未来函数结论。

> 说明：w=7/9/9 具体取值、信号覆盖率 91.8%-93.7% 属数值复现，归 verify 阶段实跑核验，非本 code_audit 职责范围。

**verdict**: pass_with_issues
