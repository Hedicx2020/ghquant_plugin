# 实现忠实性审计 · ssrn_6115073 · milestone m2（Δβ 双区制 OLS 宏观敏感选股）

- 模式: code（对照审计，审读分离）
- 审读分离: 只读 `src/ssrn_6115073/selection.py` / `common/utils.py`(ols_univariate) / `config.py` + spec.md(F2/R3) / plan.md(m2) / assumptions.md(AS9/AS15/AS41/AS42/AS43/AS44) / coverage_matrix.md(F2/R3 回填行) + 直读 `~/local_data/*.parquet`。**不采信 coder 自述 / 变更日志声明**；Δβ 数值、显著性判定、tier 落点、训练期切分一律独立重算 / 独立读数据核对。
- 本案性质: experimental 市场迁移（美股+日股+FRED → A股三宽基+中国宏观），tags 含 **ml**，未来函数为最高优先级审计对象。
- 独立验证方法: `uv run python` 下 (a) 调用 `prepare_all()`+`run_selection()` 得生产产出；(b) 用**完全独立**的 `scipy.stats.linregress` 重算 β⁺/β⁻/Δβ/p⁺/p⁻，逐位对照；(c) 只喂训练期数据自建 beta 长表对照生产表；(d) 独立数 tier 候选、对比训练期/全样本 pool。上游 m1 接口（PreparedData）已过审，只读不重审。

---

## 一、逐 element 核对表（coverage_matrix 全部 done 行：F2 / R3）

| 要素 | 操作规程（spec + assumption 口径） | 独立重算 / 读数据结论 | 判定 |
| --- | --- | --- | --- |
| **F2** 式5-8 双区制 OLS 选股 | 对每(股票,因子)按 X>0 估 β⁺(式6)、X<0 估 β⁻(式7)、Δβ=β⁺−β⁻(式8)；仅保留统计显著者，按 \|Δβ\| 取头部(AS9)；显著性 α=0.10 三层梯度(AS15)；min_regime_obs=24/top_n=50(AS41)；训练期一次性估(AS42) | 区制方向正确(`selection.py:226-227` pos_sel=xj>0→β⁺、neg_sel=xj<0→β⁻)；Δβ 定义正确(`:135` fit_pos.beta−fit_neg.beta)。**hs300 抽 10 对(股票,因子)，生产 β⁺/β⁻/Δβ/p⁺/p⁻ 与独立 scipy.linregress 逐位一致(atol=1e-6，全 match=True)**，见二。三市场独立 beta_table 行数(4337/848/8540)、pool(709/138/1350)与生产完全一致。min_obs=24、top_n=50 cap 独立复现生效(见三、四)。 | no_findings |
| **R3** 表4 β⁺/β⁻/Δβ×11方法 | m2 产**个股级** Δβ 机制(β 长表 + 候选集)；表4「11方法×β」组合层结果依赖 m6 组合构建后回归，非本模块；下行保护 Δβ>0 应占多数 | R3 实现位置如实注明「方法层表4聚合在m6」(`selection.py:7-8` docstring + coverage_matrix R3 行)，非空壳、非虚报。下行保护方向独立核对：最终口径显著对 Δβ>0/<0 = hs300 **39/5**、zz500 **91/3**、sz50 **214/38**，**以正为主**，支持 R3 下行保护迁移方向。 | no_findings |

### 五维度小结（设计 §9.3）

| 维度 | 独立核结论 |
| --- | --- |
| 1 公式一致 | F2 式5-8 + `ols_univariate`(闭式 OLS + 双侧 t(n-2)) + `significance_mask`(dual=&/single=\|) 逐位对齐独立 scipy，无偏差。no_findings |
| 2 参数一致 | α=0.10(AS15)、MIN_REGIME_OBS=24(AS41)、TOP_N=50(AS9/AS41)、VIABILITY_FLOOR=15/EXCLUSION_FLOOR=6(AS15)、ROBUSTNESS_ALPHA=0.05、DELTA_BETA_WINDOW='train'(AS42) 常量(`selection.py:51-69`)与 assumptions 逐条一致。no_findings |
| 3 实现位置真实 | coverage_matrix F2/R3 实现位置函数全部真实存在、名副其实、实际运行验证有实体逻辑。**空壳核查结论：无空壳**（无 pass/TODO 占位；7 个函数均经实际执行产出与独立重算一致的结果）。no_findings |
| 4 代码反查（私货） | selection.py 全部 7 个公开函数(compute_beta_table/dual_regime_beta/run_market_selection/run_selection/select_candidates/select_with_tier/significance_mask)均映射回 F2/R3/AS9/AS15/AS42，**无游离于要素之外的私货**。no_findings |
| 5 简化声明 | min_obs/top_n(AS41)、训练期一次性估(AS42)、月频功效不足裁决(AS43)、sz50 窄池降级(AS44)均已登记；改动边界经独立重现原口径佐证(见五)。**无未登记简化**。no_findings |

---

## 二、未来函数专项核验（ml tag 最高优先级，独立重算）

### 2.1 Δβ 双区制 (股票,因子) β/p 逐位对照（生产 vs 独立 scipy.linregress）

抽查 hs300 共 10 对，覆盖 最大/最小 \|Δβ\|、正/负 Δβ、dual@0.10 显著、dual@0.05 显著、跨 CPI/PPI/GDP/IP 四因子：

| 标签 | 股票 | 因子 | β⁺生产 | β⁺独立 | β⁻生产 | β⁻独立 | Δβ生产 | Δβ独立 | p⁺生产 | p⁺独立 | p⁻生产 | p⁻独立 | 一致 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 最大\|Δβ\| | 601360 | IR | 1.8593 | 1.8593 | -0.1654 | -0.1654 | 2.0246 | 2.0246 | 0.1982 | 0.1982 | 0.5996 | 0.5996 | ✓ |
| 最小\|Δβ\| | 000898 | PMI | 0.0092 | 0.0092 | 0.0092 | 0.0092 | -0.0000 | -0.0000 | 0.5218 | 0.5218 | 0.5027 | 0.5027 | ✓ |
| 负Δβ大 | 002625 | IR | -1.2906 | -1.2906 | -0.1817 | -0.1817 | -1.1090 | -1.1090 | 0.2401 | 0.2401 | 0.6435 | 0.6435 | ✓ |
| dual显著 | 000963 | CPI | 0.0899 | 0.0899 | -0.0523 | -0.0523 | 0.1422 | 0.1422 | 0.0212 | 0.0212 | 0.0620 | 0.0620 | ✓ |
| dual显著2 | 002271 | IP | 0.0477 | 0.0477 | -0.0931 | -0.0931 | 0.1408 | 0.1408 | 0.0850 | 0.0850 | 0.0012 | 0.0012 | ✓ |
| dual@0.05 | 002422 | CPI | 0.1324 | 0.1324 | 0.0741 | 0.0741 | 0.0583 | 0.0583 | 0.0135 | 0.0135 | 0.0349 | 0.0349 | ✓ |
| 因子CPI | 000001 | CPI | 0.0126 | 0.0126 | 0.0114 | 0.0114 | 0.0013 | 0.0013 | 0.7464 | 0.7464 | 0.7173 | 0.7173 | ✓ |
| 因子PPI | 000001 | PPI | -0.0195 | -0.0195 | -0.0313 | -0.0313 | 0.0118 | 0.0118 | 0.3414 | 0.3414 | 0.0837 | 0.0837 | ✓ |
| 因子GDP | 000001 | GDP | -0.0025 | -0.0025 | -0.0969 | -0.0969 | 0.0944 | 0.0944 | 0.9765 | 0.9765 | 0.0467 | 0.0467 | ✓ |
| 因子IP | 000001 | IP | 0.0686 | 0.0686 | 0.0198 | 0.0198 | 0.0488 | 0.0488 | 0.0073 | 0.0073 | 0.3017 | 0.3017 | ✓ |

**结论：全部 10 对生产值 == 独立 scipy 值（β⁺/β⁻/Δβ/p⁺/p⁻ 五列逐位一致）。** `ols_univariate`(`common/utils.py:325-373`) 闭式 OLS 斜率、alpha=ȳ−β·x̄、df=n−2、σ²=Σresid²/df、beta_se=√(σ²/sxx)、双侧 p=2·t.sf(\|t\|,df) 与 scipy 完全等价，公式无实质错误。

### 2.2 训练期切片 —— 测试期 2019-2024 零进入（决定性证据）

- 切片逻辑 `selection.py:211-214`：`train_sel=(idx>=train_start)&(idx<=train_end)`，`R/X/M` 三者均 `.loc[train_sel]`；train_start/train_end 由 `config.py:26-27`=2007-01-01/2018-12-31。
- **独立复算**：仅喂 [2007-01,2018-12] 训练期数据自建 beta 长表，行数(4337/848/8540)、pool(709/138/1350) 与生产 **完全一致** —— 若生产偷用测试期数据，独立表必与之不同。
- **单对最大观测**：三市场 beta_table 单对 n_pos+n_neg 最大 = **144 = 训练期月末数(144)**，未超上限，无测试期月份混入。
- **pool 排除测试期新成分**（最强证据）：

| 市场 | 训练期 pool | 全样本 pool | 生产 n_pool | 测试期新成分(被排除) |
| --- | --- | --- | --- | --- |
| hs300 | 709 | 912 | **709** | 203 |
| sz50 | 138 | 186 | **138** | 48 |
| zz500 | 1350 | 1712 | **1350** | 362 |

生产 n_pool 取训练期值(709/138/1350)，测试期新纳入成分(203/48/362 只)完全未进入选股估计。**若用全样本 member_mask 则 pool 应为 912/186/1712** —— 生产未泄漏。

### 2.3 候选集训练期一次性确定、无逐期重估
- `run_selection`(`selection.py:403-436`) 对训练期一次性算 beta_table + tier，返回固定 `candidates`，测试期无逐期重算入口（AS42「训练期一次性估、测试固定候选集」落地）。
- 全部候选股票 ∈ 训练期成分 pool（三市场独立核 True）；股票池按时点 member_mask.any() 取（`:217`），非当前成分回溯（m1 已验证半开 [in_date,out_date)）。

**未来函数专项结论：训练期切片、时点成分、固定候选集三点全部通过，未来函数红线守住。**

---

## 三、tier 逻辑核验（AS15 频率适配三层梯度，独立重算 vs 生产 vs 变更日志声称）

| 市场 | 独立 dual@0.10 | 独立 single@0.10 | 独立 dual@0.05 | 独立推断 tier | 生产 regime_tier / sig_mode | 生产候选数 | 三方一致 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| hs300 | 40 | 50 | 10 | Tier1 (40≥15) | **Tier1 / dual** | tier1=40, robust=10, final=40 | ✓ |
| sz50 | 8 | 50 | 1 | Tier2_degraded (8<15→single, 50≥6) | **Tier2_degraded / single** | tier1=8, tier2=50, robust=1, final=50 | ✓ |
| zz500 | 50 | 50 | 21 | Tier1 (50≥15) | **Tier1 / dual** | tier1=50, robust=21, final=50 | ✓ |

- **结构自动触发核实**（`select_with_tier` `:337`/`:343`）：`n1>=viability_floor(15)`→Tier1；否则 single，`n2>=exclusion_floor(6)`→Tier2_degraded 否则 excluded。sz50 因 dual@0.10=8<15 **由候选数阈值自动回退** single（α 仍 0.10 不变），**非人工按市场写死 α**；三市场无 excluded。
- **α 全市场统一 0.10**：`run_selection` 对三市场传同一 `DELTA_BETA_ALPHA=0.10`(`selection.py:51,432`)，未逐市场差异化；回退改的是 sig_mode(dual→single)，非 α。符合 AS15/AS44。
- **显著性判定正确**（`significance_mask` `:167-170`）：dual=below_pos&below_neg、single=below_pos\|below_neg，NaN 比较恒 False（退化回归不显著，安全）。
- **排序按 \|Δβ\|**（`select_candidates` `:296-309`）：stock_score=该股显著因子上 max\|Δβ\|，降序取 min(top_n,N)。候选去重独立核：显著对/去重股票/候选数 = hs300 44/40/40、sz50 252/110/50(cap)、zz500 94/88/50(cap)，三方一致。AS9 排序准则未被改。
- **变更日志声称值(40/50/50、dual@0.10=8<15 回退、稳健侧栏 10/1/21)全部经独立重算重现，无虚报。**

---

## 四、改动边界核验（本轮口径落地是否只动显著性判定层）

- **稳健侧栏 dual@0.05 独立重现原口径**：生产 n_cand_robust=**10/1/21**，与 AS43 发现记录「原 5% 双系数候选股 hs300=10/sz50=1/zz500=21」**逐值一致**。同一 beta_table 用 α=0.05 dual 能重现口径切换前的原始候选数 → **回归本体(β/p 计算)未被改动**，本轮仅在选股判定层将 α 0.05→0.10 并新增 single 回退分支（`significance_mask`/`select_with_tier` 为新增判定层，`dual_regime_beta`/`compute_beta_table` 回归核心不变）。三档共用同一 beta_table、无重复回归（`run_market_selection:370-382`）。符合审计重点5。

---

## 五、findings 清单

**无 findings（critical / major / minor 均为 0）。**

已逐项核查以下高风险面，均未发现问题（显式声明，非省略）：
- 未来函数（测试期数据进入选股估计 / 当前成分回溯 / 候选集用未来重估）：全部排除（见二，含 pool 排除测试期新成分的决定性证据）。
- Δβ 公式实质错误（区制反接 / Δβ 定义错）：无，10 对逐位对齐独立 scipy。
- coverage_matrix 空壳：无，7 函数实际运行验证有实体逻辑。
- 显著性 tier 偏离 AS15 裁决（人工调 α / 排序准则被改）：无，α 统一 0.10、回退由池规模阈值结构触发、排序仍按 \|Δβ\|。
- min_regime_obs=24 / top_n=50 与 AS41 不符：无，独立复现行数与 cap 生效一致。

---

## 六、已检查维度清单（code 模式五维度，无遗漏）

1. **公式一致** — F2 式5-8 + ols_univariate + significance_mask 逐位对齐独立 scipy：no_findings
2. **参数一致** — α=0.10 / min_obs=24 / top_n=50 / floors 15,6 / robust 0.05 / window='train' 与 assumptions 一致：no_findings
3. **实现位置真实** — coverage_matrix F2/R3 函数全部真实、名副其实、实运行验证；空壳核查结论=无空壳：no_findings
4. **代码反查（私货）** — 7 公开函数全映射 F2/R3/AS9/AS15/AS42，无私货：no_findings
5. **简化声明** — AS41/AS42/AS43/AS44 均登记；改动边界经独立重现佐证：no_findings

附加专项：未来函数（ml tag 最高优先级，含训练期切片/时点成分/固定候选集）全部通过；tier 逻辑(AS15)与反虚报(变更日志数字)独立重算全部重现。

置信度：全部结论基于独立重算逐位对齐，高置信度，无 confidence low 项。

**verdict**: pass
