# 实现忠实性审计 · m5（Diebold-Yilmaz 溢出加权与每簇选股）· ssrn_6115073

- 审计模式：code（对照审计，只拿文件不采信 coder/verifier/主会话自述，一切数值独立重算）
- 被审文件：`src/ssrn_6115073/spillover.py`（708 行）
- 规格权威：`spec/spec.md` F9（式28-35）/F10（式36-37 每簇选一）/R4（表6）
- 假设：AS12/AS17/AS51/AS52/AS53/AS54/AS55（m5 相关）
- 矩阵 done 行（本次核对对象）：F9、F10、R4
- 运行环境：`.venv`（uv，python 3.12.12，numpy 2.5.1 / scipy 1.18.0，**statsmodels 不可用**——已独立确认 `ModuleNotFoundError`，故 `var_impl='self_var'`，AS52 依赖退化前提属实）
- 独立复算脚本（scratchpad，只读被审函数）：`verify_gfevd.py`（合成 VAR GFEVD）/`verify_r4.py`（三市场溢出排序 + 变量顺序置换）/`verify_fs.py`（FS/选股逻辑）/`verify_trainonce.py`（切片日期上界）；实际冒烟 `python -m src.ssrn_6115073.spillover` 端到端通过

---

## 一、逐 element 五维度核对表

### F9 — 波动率溢出指数（Diebold-Yilmaz VAR/GFEVD，式28-35）

实现位置：`_var_ols`（139-165）/`select_var_lag`（168-193）/`ma_coefficients`（196-209）/`generalized_fevd`（212-236）/`compute_spillover_table`（266-330）

| 维度 | 核对结论 | 独立证据 |
| --- | --- | --- |
| 公式一致 | **通过**。VAR(p) 含截距多元 OLS（式28 `x_t=c+ΣΦ_l x_{t-l}+ε`）；AIC 定阶 `ln|Σ|+2n(np+1)/T`；Wold `A_0=I,A_h=ΣΦ_l A_{h-l}`（式29）；Pesaran-Shin GFEVD `θ^g_ij=[σ_jj⁻¹Σ_h(e_i'A_hΣe_j)²]/[Σ_h e_i'A_hΣA_h'e_i]` 行归一化（式30-31）；净溢出 `S^g_i=(col_sum−row_sum)/n×100`（式35） | 合成 VAR(1)：`_var_ols` 恢复 Φ_true（max|Δ|=0.021，T=4000 抽样误差内）/Σ_true（0.019）；`select_var_lag` 对真实 p=1 选 p=1；`ma_coefficients` A_h=Φ^h（误差 ≤1.4e-17）；`generalized_fevd` 被审 vs 独立暴力实现 **max|Δ|=2.8e-17**、行和=[1,1,1]、全非负、对角行内最大；系统净 **Σ system_net=4.4e-16≈0**（再分配恒等式），总连通度=平均行外和×100 |
| 参数一致 | **通过**。`VAR_MAX_LAG=4`（AS12 p≤4）、`FEVD_HORIZON=10`（AS12 U=10）、`SPILLOVER_WINDOW='train'`（AS54）、`MIN_VAR_OBS=60`、`SIGMA_RIDGE=1e-10`。实测三市场 AIC 选 p=3、n_obs=144、总连通度 41.85~43.62（与矩阵日志「p=3/144训练月/总连通度41-44」逐项吻合） | verify_r4.py |
| 实现位置真实 | **通过**。5 函数均存在、非空壳（行数 14~65，无 pass/TODO/NotImplementedError） | inspect 反查 |
| 代码反查 | **通过**。全部映射 F9 VAR/GFEVD 原语，无未登记私货 | — |
| 简化声明 | AS52（statsmodels 缺→自实现 VAR+广义 FEVD）已登记且数值与官方闭式定义唯一等价（已独立核验）；AS53（月频收益/变化代理波动率溢出）已登记，experimental 数值豁免。**遗留 issue CA-A01**（见 findings）：`var_impl` gate 仅改标签不切实现 | — |

### F10 — 信号聚合 FS_j（式37）+ min-max γ̃（式36）+ 每簇选最强（AS17）

实现位置：`_minmax_weights`（243-248）/`aggregate_fs`（337-353）/`select_per_cluster`（356-395）/`run_market_spillover`（402-485）/`run_spillover`（488-540）

| 维度 | 核对结论 | 独立证据 |
| --- | --- | --- |
| 公式一致 | **通过**。式36 `γ̃_i=(γ_i−minγ)/(maxγ−minγ)∈[0,1]`，退化→1；式37 `FS_j=Σ_i γ̃_i·signal_{i,j}`；NaN 按缺失从求和剔除（贡献 0，AS51 非 −1）；全 NaN 资产→FS=NaN；每簇 argmax FS、仅 FS>0（含 FS=0 剔除）选入（AS17 纯长仓 FS≤0 剔除） | verify_fs.py：受控矩阵 A=1.5/B=0.1/**C=−0.1（M2 的 NaN 剔除，非朴素 −1 填充的 −1.1）**/**D 全 NaN→FS=NaN（非 −2.5）**/E=−0.2；`select_per_cluster` 簇0 取 A(1.5>0)、簇1 全 FS≤0/NaN 不选；FS 恰=0 资产不入选（floor 严格 >0）——全部断言通过 |
| 参数一致 | **通过**。`FS_LONG_ONLY_FLOOR=0`（AS17 FS≤0 剔除）、`MINMAX_EPS=1e-12`（退化判定）。gamma 按 signal 列 label 对齐 reindex（非位置对齐），因子顺序错位不致权重错配 | 代码 347 行 |
| 实现位置真实 | **通过**。4 函数存在、非空壳（17~84 行） | inspect 反查 |
| 代码反查 | **通过**。映射 F10，无私货 | — |
| 简化声明 | AS55（FS 权重基取 net_pairwise、R4 强度取 to_index、三测度并存）已登记。**遗留 observation CA-A02**（见 findings）：月频代理下 net_pairwise 几乎全负、min-max 使权重直觉倒置 | — |

### R4 — 表6 各宏观因子溢出强度均值（迁移检验）

实现位置：`compute_spillover_table`（to_index/net_spillover/system_net 列，310-325）/`spillover_table_frame`（547-560）

| 维度 | 核对结论 | 独立证据 |
| --- | --- | --- |
| 公式一致 | **通过**。R4 强度用 `to_index=θ̃[index←factor]×100`（非负方向份额，贴合表6 全正值与「from factor to index」语义）；独立重算三市场 to_index 与被审 **max|Δ|≤6e-8**（lstsq/ridge 级差） | verify_r4.py |
| 参数一致 | **通过**。同 F9（p=3,U=10,train-once） | — |
| 实现位置真实 | **通过**。`spillover_table_frame` 存在（14 行）、产 market/factor/to_index_share/net_spillover/gamma_weight 长表 shape=(21,5) | 冒烟输出 |
| 代码反查 | **通过**。R4 强度排名严格用 to_index 单列（smoke 654 行 `strength=pd.Series(r.to_index)`），与 FS 权重 net 分列**不混用**，无「net/to_index 口径混用致 R4 错」 | — |
| 简化声明 | R4 定性（数值对齐豁免 AS53）；「CPI 三市场最强/次强、IR 垫底、与原文 IR 次强相反」为**真实溢出计算结果非 bug**（下节独立证明），已登记、判定归 verifier | — |

---

## 二、未来函数专项（ml tag / train-once 切片证据，AS54）

抽 hs300 直查 `compute_spillover_table` 的 VAR 输入切片（verify_trainonce.py，独立复算切片逻辑）：

- VAR 输入样本 **n=144**，首日 **2007-01-31**、末日 **2018-12-28**
- 末日 ≤ train_end（2018-12-31）：**True**
- 任何 ≥ test_start（2019-01-01）的行进入 VAR：**False**
- 任何 > train_end 的行进入 VAR：**False**

结论：γ̃/GFEVD 估计输入严格 ⊆ [train_start, train_end]，测试期 2019-2024 **零进入估计**（对所有测试月 T 满足「估计 ⊆ ≤T」且更强）。逐测试月 `run_market_spillover` 内 `gamma_series` 仅从训练期溢出表算一次（447 行），测试循环 `aggregate_fs(sig, gamma_series)`（455 行）用**当月 m4 信号（已 T 定时）× 固定训练期 γ̃**，无测试期泄漏。与 AS42（Δβ）/AS50（窗口 w）/m3（nc）全链 train-once 一致。**未来函数：无。**

---

## 三、GFEVD 独立数值核验（合成 VAR 对照，不采信 coder 自检声明）

构造已知 VAR(1)（Φ_true 与残差协方差 Σ_true 指定，T=4000 模拟），用被审函数与**独立逐元素暴力实现**（不共享代码路径）对照：

| 检查项 | 结果 | 判定 |
| --- | --- | --- |
| Φ 恢复 max|Φ_hat−Φ_true| | 0.0211（抽样误差内） | 通过 |
| Σ 恢复 max|Σ_hat−Σ_true| | 0.0190 | 通过 |
| AIC 定阶（真实 p=1） | 选 p=1 | 通过 |
| A_h vs Φ_hat^h（h=0..3） | max 误差 1.39e-17 | 通过 |
| **GFEVD 被审 vs 独立暴力** | **max|Δ|=2.78e-17** | 通过 |
| GFEVD 行和 | [1,1,1] | 通过 |
| GFEVD 全非负 | True | 通过 |
| 对角是否行内最大（自身份额最大） | [True,True,True] | 通过 |
| **系统净 Σ system_net（应=0）** | **4.44e-16** | 通过 |
| 总连通度 = (n−trace)/n×100 = 平均行外和×100 | 18.929=18.929 | 通过 |
| min-max γ̃ 边界（min→0,max→1,退化→全1） | [−2,0,3,1]→[0,0.4,1,0.6]；全等→[1,1,1] | 通过 |

GFEVD 公式实现**实质正确**，与 Pesaran-Shin 广义方差分解闭式逐位一致；净溢出式35 符号/公式正确。coder 声称的「合成 VAR 数值自检一致」经独立复算**证实**。

---

## 四、R4 迁移真伪独立重算（CPI 领先是否 bug）

verify_r4.py：跑 m1 `prepare_all()` 取真实 change_panel + 三市场 index_returns，用**独立 fresh OLS + 暴力 GFEVD** 重算 to_index，并**随机置换 7 因子的变量顺序**再算，验证排序不依赖变量顺序/归一化：

| 市场 | 被审 to_index 排名 | 独立重算排名 | **变量顺序置换后排名** | CPI 位次 | IR 位次 |
| --- | --- | --- | --- | --- | --- |
| hs300 | CPI>PPI>PMI>IP>M2>GDP>IR | 同（max|Δ|=6.0e-8） | **完全相同** | 1 | 7（垫底） |
| sz50 | CPI>PPI>M2>IP>PMI>IR>GDP | 同（5.6e-8） | **完全相同** | 1 | 6 |
| zz500 | PPI>CPI>PMI>GDP>M2>IP>IR | 同（5.0e-8） | **完全相同** | 2 | 7（垫底） |

结论：CPI 在 hs300/sz50 居首、zz500 居次，IR 三市场垫底/近垫底——**排序对变量顺序置换完全不变、且被审值与独立重算机器精度一致**，证明「CPI 最强、IR 垫底」是溢出计算的**真实结果**，**非** VAR 变量顺序错置或归一化 bug 造成的人为排序。与原文表6「IR 次强」相反属月频收益/变化代理（AS53）下的迁移发现，代码已透明报告、判定归 verifier，符合实验模式「只记事实」。矩阵 R4 note「CPI 三市场均最强/次强、IR 垫底」经独立复算**属实**。

---

## 五、findings（id | severity | 文件:行号 | 描述 | 建议）

### CA-A01 | minor | `src/ssrn_6115073/spillover.py:54-55, 57-65, 422`（另 AS52 line 678、docstring 11 行）
`_HAS_STATSMODELS` gate 仅设置 `var_impl` **标签**（422 行 `var_impl = "statsmodels" if _HAS_STATSMODELS else "self_var"`），而 `compute_spillover_table`（303-307）**无论 gate 与否恒调用自实现** `_var_ols`/`ma_coefficients`/`generalized_fevd`，不存在切换到官方 statsmodels 的计算分支。docstring 54 行「可用则可切换官方 VAR/FEVD」与 AS52「保留 feature-gate（装上后可切官方实现）/装上后无缝切换」**与代码行为不符**。当前 venv 无 statsmodels，标签 `self_var` 与实跑一致、**无现行错报、不影响任何数值**（GFEVD 已证正确）；但属潜伏错报——日后若装 statsmodels，`var_impl` 将误报 'statsmodels' 而实际仍跑 self_var，可能误导 verifier 以为经官方库校验。
建议：二选一——(a) 真正实现 `if _HAS_STATSMODELS: 用官方 VAR/FEVD` 分支；(b) 将 docstring/AS52 措辞订正为「gate 仅记录依赖可用性，计算恒用自实现 self_var」，`var_impl` 恒置 'self_var'。

### CA-A02 | minor | `src/ssrn_6115073/spillover.py:312, 318-319`
FS 权重基 `net_pairwise`（成对净 `θ̃[index←factor]−θ̃[factor←index]`）在月频收益/变化代理（AS53）下三市场**几乎全为负**（指数反向主导各宏观因子，hs300 全负、sz50 仅 M2/PMI 微正）。min-max 归一化后，「被指数主导最少」的 PMI/M2 得最高 γ̃（≈1.0），而 R4 溢出最强因子 CPI 反得低权（hs300 γ̃=0.171）——FS 权重的经济含义与「溢出强度」直觉及 R4 to_index 排名**倒置**。此为 **AS55 已登记**的设计选择（spec F10 式36-37 明写「净溢出」权重，代码取 net 属 spec-faithful；且三测度并存、to_index/system_net 均留存），**非未登记偏差、不判 fail**（experimental 数值豁免）。
建议：提示 verifier 回看 FS 权重测度（net_pairwise vs to_index vs system_net）对下游每簇选股与 §九消融结论的敏感性（AS55 已列此回看点，代码「单点改 gamma_weight 来源即可」）。

---

## 六、已检查维度清单（五维度全覆盖，无遗漏）

- **公式一致**：F9 VAR/AIC/Wold/GFEVD/净溢出（合成 VAR 逐项独立核验）、F10 min-max/FS/NaN 剔除/每簇选一（受控矩阵独立核验）、R4 to_index（独立重算 6e-8）——全通过
- **参数一致**：p≤4/U=10/train-once/floor=0/MIN_VAR_OBS=60/ridge 逐一对照 AS12/AS17/AS54——全通过
- **实现位置真实**：F9/F10/R4 全部登记函数存在且非空壳（inspect 反查，14~84 行，无 pass/TODO/NotImplementedError）；**空壳核查无命中**（不存在空壳，故不产生 not_found 判定，无需在 coverage_matrix 记回退）
- **代码反查**：spillover.py 全部公开/私有函数映射 F9/F10/R4 或 smoke 辅助，无未登记私货
- **简化声明**：AS52（自实现 VAR）/AS53（月频代理）/AS54（train-once）/AS55（三测度）均已登记且经独立复算合规；发现 2 项 minor（CA-A01 gate 标签解耦、CA-A02 net 权重倒置，均登记内/无现行数值影响）
- **未来函数专项（ml tag）**：train-once 切片日期上界 ≤2018-12 独立证实，测试期零进入估计——无未来函数
- **GFEVD 独立数值核验**：合成 VAR 行和/对角/净溢出 Σ=0 对照全通过
- **R4 迁移真伪**：变量顺序置换不变 + 独立重算一致，CPI 领先/IR 垫底为真实结果非 bug

审计结论：F9/F10/R4 三要素公式实质正确、参数与 AS 一致、实现位置真实无空壳、无未来函数、R4 迁移排序真实；仅 2 项 minor（1 项潜伏标签错报、1 项已登记的迁移产物权重倒置，均不影响现行数值正确性）。

**verdict**: pass_with_issues
