# 实现忠实性审计 · r001_signature_transformer_allocation · milestone m2（路径签名与交叉签名特征工程）

- 模式: code（对照审计，审读分离）
- 审读分离: 只读 signatures.py / test_signatures.py / config.py + spec.md / plan.md / coverage_matrix.md / assumptions.md + data.py（上游接口，只读理解不审）；**不采信 coder 冒烟自述与变更日志声明**。签名 level-0/1/2、Chen 增量、交叉 signed-area、时间增广维度、点时红线一律独立手算/合成数据重算，另独立运行单测。
- 本案性质: experimental 市场迁移，tags 含 ml，未来函数（签名/交叉是否只用 [t−H,t] 窗口）为最高优先级审计对象（无视难度必跑）。
- 审查范围: coverage_matrix 中 m2 全部 `done` 行 = D4 / D5 / F1 / F2 / B8。

---

## 一、逐 element 忠实性核对（D4 / D5 / F1 / F2 / B8，独立重算）

| 要素 | spec + assumptions 口径 | 独立重算/推导结论 | 判定 |
| --- | --- | --- | --- |
| **F1** 路径签名 M=2（p2,p16，core，AS17/AS20/AS22） | SigM=(1,∫dX,∫∫dX⊗dX)；level-1=净增量、level-2=二阶迭代积分（含对角+signed-area）；Chen relation 增量避免全历史重算；逐资产 H 切片 | `signature_m2_parts` 逐段递推 `level2 += outer(level1,δ) + ½outer(δ,δ)` 再 `level1 += δ`（用旧 level1，顺序正确）——独立推导：分段线性单段贡献 ∫(level1+sδ)dX·δ = level1·δ+½δ·δ，**与代码逐项相符**；level2[a,b]=∫(X^a−X0^a)dX^b=S^{(a,b)}（内层a外层b，方向正确）。独立手算 2 维 3 点路径 level2=[[.00125,.0175],[−.0025,.045]]、A=0.02 与代码**逐位一致**。`asset_signature_sequence` 返 (H,d,d_sig=7) 逐切片 running 签名（时间增广，AS21），level0=1、S_XX=½X²、S_tX=Σ(m−0.5)/H·r 独立核对一致。Chen 增量真实（`signature_m2_sequence` 逐步不重算全历史）。 | consistent（路径母源=对数收益累积，AS22 deviation_declared） |
| **F2** 成对交叉签名 signed-area（p2,p12 Eq.21，core，AS7） | A(X^i,X^j)=∫X^i dX^j−∫X^j dX^i；反对称、对角=0；d_cross-sig=2 | `signed_area_matrix=S−S^T`（S=`cross_signature_matrix`），独立 einsum 按定义 S[i,j]=Σ X_{k-1}^i·δ^j+½δ^i δ^j 重算**逐元素一致**；A=S−S^T **反对称 A=−Aᵀ、对角=0** 独立验证 True。`levy_area=level2[0,1]−level2[1,0]`=S^{(0,1)}−S^{(1,0)}（列0=i、列1=j）**严格对应 Eq.21**。signed-area 语义：独立跑正弦 lead-lag（i 领先 j，φ=π/4）A=4.442876 vs 解析 2π·sinφ=4.442883（相对误差<2e-6）、离散阶跃 A=+1/反向−1——**Proposition 2.1「严格 lead-lag⇒A>0」成立**。`cross_signature_pairs` C[i,j]=(∫X^i dX^j,∫X^j dX^i) 即 AS7 的 d_cross-sig=2。 | consistent |
| **D4** F_ti 组装（p2，core，AS21） | 三部分：(i)每资产H切片签名 (ii)全对交叉签名 (iii)H 个日历 v_t；维度自洽 | `SignatureFeatures` 三部分齐：asset_signatures(H,d,7)=(i)✓、cross_signatures(d,d,2)=(ii)✓、calendar(H,F=8)=(iii)✓；另派生 signed_area(d,d)=(ii)的反对称部分供 m3 β/诊断（非私货，属交叉签名派生）。合成数据实测形状 (5,3,7)/(3,3,2)/(3,3)/(5,8) 维度自洽。`build_feature_tensors` 堆叠 (T,H,d,7)/(T,d,d,2)/(T,H,F)。 | consistent |
| **D5** 路径重建+实现收益（p2，core，AS20/AS22） | (i)线性插值重建连续路径 (ii)实现收益 r_t 作标签，与特征时点严格分离（T算T+1） | (i) 插值口径=`config.signature_interpolation="linear"`，实现为**分段线性闭式签名**（无显式 interpolate 函数，数学等价「先线性插值再算签名」，AS20），忠实。(ii) `realized_forward_returns` 取决策日后 K 个月度区间 (t_{i+k},t_{i+k+1}] 简单收益复利，独立合成验证：**改决策日之前 simple return→标签不变（标签纯未来）**、区间开于决策日不含当日收益、未来<K 返 None。docstring 明标「标签/未来数据，绝不回流模型输入」。特征时点与标签严格分离。 | consistent（母源对数收益 AS22 已登记） |
| **B8** 窗口 H=60/K=12（p2，core，AS2） | H=60 回看、K=12 多步（原文 n/a，AS2 裁决）；config 带 AS 引用 | `config.lookback_h=60`（build_signature_features 窗口）、`decision_steps_k=12`（realized_forward_returns K），字段注释引用 B8/AS2；`__post_init__` 校验 (1−α)K=2.4≥1 非退化。合成数据实测窗口长度==H、标签步数==K。参数忠实。 | consistent（变更日志措辞瑕疵见 CA-A02） |

**空壳核查（实现位置真实性，G-CA-3）**：coverage_matrix m2 五个 done 行实现位置的全部函数——`signature_m2` / `signature_m2_sequence` / `signature_m2_parts` / `levy_area` / `cross_signature_matrix` / `cross_signature_pairs` / `signed_area_matrix` / `asset_signature_sequence` / `build_signature_features` / `build_feature_tensors` / `realized_forward_returns` / `SignatureFeatures`——**逐一经独立 `uv run python` 调用执行、返回真实数组/数据结构**，均含实体数学逻辑，**无 pass/TODO 占位、无名不符实、无空壳、无 not_found 情形**。G-CA-3 通过，m2 无需回退、无虚报 critical。

---

## 二、签名数学独立验证专项（不采信被审单测，亲自手算+合成重算）

1. **解析签名手算对照**：2 维 3 点路径 [[0,0],[0.1,0.2],[0.05,0.3]]，我手算 level1=[0.05,0.3]、level2=[[0.00125,0.0175],[−0.0025,0.045]]、A=0.02，代码输出**逐位一致**；shuffle 恒等 S01+S10=0.015=l1_0·l1_1、对角 S_ii=½(ΔX_i)² 独立核实成立。
2. **交叉签名向量化 ≡ 定义**：独立 einsum `Σ X_{k-1}^i δ^j + ½δ^i δ^j` 与 `cross_signature_matrix` 逐元素一致；C[...,0]=S、C[...,1]=Sᵀ、signed_area=S−Sᵀ 反对称+对角 0 均 True。
3. **时间增广维度/开关**：d_sig 默认 7（1+2+4）、关 level0→6、关增广→3，`config.asset_signature_dim` 派生量与实测一致，函数体无硬编码维度。
4. **点时红线（ml 最高优先级，合成数据）**：`build_signature_features` 窗口 iloc[pos−H+1:pos+1]——窗口末日==决策日、长度==H、全部≤决策日、首日=第(pos−H+1)交易日；**污染决策日之后行的收益→签名张量完全不变（零未来泄漏）**；历史不足（pos<H）正确 raise。标签侧改决策日之前数据不变、临近末端未来<K 返 None。**签名/交叉/日历只用 [t−H,t] 窗口，实现收益纯未来标签，无泄漏。**
5. **独立运行单测**：`uv run python -m ...test_signatures` **11/11 全绿**，AS17 数值 A=4.442876≈2π·sinφ=4.442883、离散阶跃 A=+1.0/反向−1.0，与我手算独立结论一致。

---

## 三、AS17 单测有效性评估（是否真验证性质、断言是否有效）

AS17 要求对合成 lead-lag 路径做符号/量级单测（Proposition 2.1）。逐条核 test_signatures.py 断言实效：

- **lead-lag A>0（`test_leadlag_signed_area_positive` L119-125）**：断言 `area>0` **且** `|area−2π·sinφ|/analytic<0.02`——不止查符号，含量级容差校验，**有效**。
- **反向翻转（`test_leadlag_sign_flips_on_reverse` L128-135）**：断言 `area_fwd>0 and area_rev<0` **且** `isclose(fwd,−rev,rtol=1e-6)`——实证反对称，**有效**。
- **无 lead-lag≈0（`test_no_leadlag_area_near_zero` L138-142）**：同相路径 `|area|<1e-9`，**有效**。
- **离散阶跃 A=±1（`test_discrete_stepwise_leadlag` L145-150）**：确定性精确值断言，**有效**（不依赖随机性）。
- **向量化 ≡ 参考（L71-98）**：`cross_signature_matrix`/`asset_signature_sequence` 对逐对/逐资产参考实现 `np.allclose`，**防加速版引入 bug 的有效护栏**。
- **shuffle 恒等（L59-64）**：diag(l2)=½l1²、l2+l2ᵀ=outer(l1,l1)，**有效**。

**评估结论**：AS17 单测**真正验证了 Proposition 2.1 三性质（lead-lag A>0、反向翻转、无 lead-lag≈0）+ signed-area 量级 + 向量化一致性，断言均带明确阈值、非空跑非走过场**。覆盖 F1/F2 的核心正确性风险点（交叉签名符号），构成有效安全网。

---

## 四、findings 清单

| id | severity | 文件:行号 | 描述 | 建议 | confidence |
| --- | --- | --- | --- | --- | --- |
| CA-A01 | minor | src/r001_signature_transformer_allocation/config.py:90-94 | `__post_init__` 退化校验 `(1−α)·K<1` 在**恰好=1** 时因浮点误判：α=0.80、K=5 时 `(1.0−0.80)*5=0.9999999998<1.0` 触发 ValueError（本审计验证时实测触发）。默认 α=0.80/K=12→2.4 远离边界、**不受影响**，仅在下游以边界参数（如 K=5）构造 config 时误报。 | 校验改 `< 1.0 − 1e-9` 容差，或 `round(tail_pts,6)<1`，避免边界浮点误判。 | high（实测触发） |
| CA-A02 | minor | coverage_matrix.md 变更日志 L47；spec.md B8 L206 | 变更日志称「B8 订正 K=1→12（原 K=1 笔误订正）」，但 spec B8 明确「K 具体数值原文正文与 Table4 搜索空间均未给出（n/a）」——原文并非写了 K=1，而是未给；「原 K=1 笔误」措辞与 spec 登记的 n/a 不符（K=1 是 AS2 论证退化时的假想基线，非原文值）。config `decision_steps_k=12` 带 AS2 引用、实现忠实，**仅表述瑕疵**。 | 变更日志/AS2 表述改为「原文 K 未给（n/a），AS2 裁决 K=12」，与 spec B8 口径一致。 | medium |

（说明：D5-i「连续路径重建」无显式 interpolate 函数，因分段线性路径 M=2 签名有精确闭式、直接算闭式等价「先线性插值再算签名」，AS20 已登记，属正确实现选择，不列为 issue；cross_signatures 对角项 C[i,i]=(S_ii,S_ii)≠0 是自身路径 ½(ΔX)²、供 m3 MLPβ，signed_area 对角已=0，语义正确，不列为 issue。）

---

## 五、已检查维度清单（code 五维度，无遗漏）

1. **公式一致**：F1 Chen 增量 `level2+=outer(level1,δ)+½outer(δ,δ)`（独立推导+2维手算逐位一致）、level2 方向 S^{(a,b)} 内a外b；F2 A=S−Sᵀ=Eq.21（反对称/对角0/正弦 A=2π·sinφ 独立核）；时间增广 S_tX=Σ(m−0.5)/H·r、S_Xt=t·X−S_tX（shuffle）；D5 标签区间 (t_{i+k},t_{i+k+1}] 简单收益复利——算子/分子分母/时点（t vs t−1、决策日切分）均独立重算一致，无 deviation_undeclared。
2. **参数一致**：H=60（lookback_h）、K=12（decision_steps_k）、M=2（signature_truncation_m）、d_cross-sig=2（cross_signature_dim）、d_sig=7（asset_signature_dim 派生）、时间增广/level0 开关、插值 linear、母源 log_return——与 spec B8/F1/F2/AS2/AS7/AS20/AS21/AS22 逐条核对一致；config frozen、无魔法数字散落（函数体引用 config 派生量）。
3. **实现位置真实**：m2 五个 done 行（D4/D5/F1/F2/B8）实现位置全部函数经独立调用执行验证为真实非空、含实体逻辑，无空壳、无名不符实、无 not_found 情形（G-CA-3 通过）。
4. **代码反查**：signatures.py 每个公开函数均映射回要素 ID——参考/向量化签名(F1)、交叉/signed-area(F2)、F_ti 组装(D4)、实现收益标签(D5-ii)、窗口取 config H/K(B8)；signed_area 额外派生项经核为交叉签名反对称部分（供 m3，非私自替换研报方法的私货）。无映射不上的逻辑块。
5. **简化声明**：代码注释/docstring 承认的简化（自实现无签名库、分段线性闭式、时间增广、对数收益母源）**逐条对应 AS17/AS20/AS21/AS22 已登记**；config m2 追加 5 字段均带 spec/AS 引用注释。未发现「注释承认简化但未登记」或未登记的 core 要素偏差。

**复用核查**：signatures.py 纯 numpy 自实现签名/交叉签名，为本案特有（common 无签名模块），置于 src 合理，未在 src 重复 common 通用逻辑；上游经 TYPE_CHECKING 仅类型引 data.DataBundle、运行时不导入（保核心数学可测），符合复用与分层约束。

**独立重算 vs coder 声明比对**：变更日志称「AS17 单测 11 项全绿、lead-lag A=4.4429≈2π sinφ」→ 独立运行**11/11 全绿、A=4.442876 逐项复算一致**；称「F_ti 维度 (60,8,7)/(8,8,2)/(60,8)」→ 合成数据独立实测 (H,d,7)/(d,d,2)/(H,F) 维度规律一致（d_sig=7/d_cross=2/F=8）；称「点时无未来」→ 独立污染测试确认零泄漏；均未直接采信自述。

**verdict**: pass_with_issues
