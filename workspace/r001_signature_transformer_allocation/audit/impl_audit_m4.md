# 实现忠实性审计 · milestone m4（impl_audit_m4）

- 案例: r001_signature_transformer_allocation（allocation / ml / hard / experimental）
- milestone: m4「CVaR 端到端训练、基线与主绩效表」
- 审计对象: src/{train.py, baselines.py, backtest.py, main.py, config.py(m4 段)} + 复用件 common/{allocation_backtest.py, utils.py}
- 审计模式: code（对照审计，只拿文件、独立重算，不采信 coder 自述）
- 被核 done 行（coverage_matrix m4）: F7 F8 B1 B2 B3 B5 B6 B7 R1 R2 R3 R4（共 12 行）
- 结论摘要: **critical=0，major=0，minor=3**。ml 三大红线（未来函数 / 训练泄漏 / CVaR 数学）独立核实全部通过；CA-A01 死票屏蔽逻辑正确；GMV 修复（AS25）数学真实有效。verdict=pass_with_issues。
- 说明: templates/audit/impl_audit.md 缺失（templates/audit/ 仅有 extract_audit/evidence_manifest 等），本文按设计 §9.3 五维度自组织，不因模板缺失停止。

---

## 一、五维度逐条核对（12 个 done 行）

维度：①公式一致 ②参数一致 ③实现位置真实 ④代码反查（无夹带私货） ⑤简化声明完备

| 行 | ①公式 | ②参数 | ③位置真实 | ④反查 | ⑤简化声明 | 判定 |
|----|------|------|---------|------|---------|------|
| F7 CVaR 目标 | ✓ RU 经验式精确落地(见二) | ✓ α=0.80/K=12/(1-α)K=2.4 | ✓ train.cvar_from_losses/cvar_portfolio_loss | ✓ | AS1/AS24 已登记 | pass（1 minor） |
| F8 端到端 | ✓ 唯一 CVaR、无 µ̂ 监督(见三) | — | ✓ train.train_sit/cvar_portfolio_loss | ✓ | AS24 | pass |
| B1 训练超参 | ✓ Adam+早停+best-val 回载 | ✓ lr1e-3/bs64/dropout0.1/ep100/pat10 | ✓ train.train_sit + config | ✓ | AS5/AS14/AS18 | pass |
| B2 网格 | ✓ val CVaR 选优、test 封存 | ✓ 8 组=d_model{16,32}×d_ff{16,32}×heads{2,4} | ✓ main.hyperparameter_grid/select_hyperparams | ✓ | AS14 | pass |
| B3 月度调仓 | ✓ receding-horizon w^(1)、T+1 | ✓ backtest_decision_step=0/月度 | ✓ backtest.sit_weight_panel/build_monthly_returns/run_portfolio | ✓ | AS24 | pass |
| B5 基线 | ✓ EW/GMV/HRP 复用+CVaR RU-LP(见五) | ✓ α=0.80/窗口120·60/min12 | ✓ baselines.* + backtest.baseline_weight_panel | ✓ | AS15/AS25 | pass |
| B6 指标 | ✓ Sharpe/Sortino/MaxDD/Wealth | ✓ 零 rf/年化基数 12 | ✓ backtest.performance_metrics 复用 common.utils | ✓ | — | pass |
| B7 两阶段 | ✓ DLinear MSE + min-CVaR 加 wᵀr̂≥µtarget | ✓ kernel25/lr1e-3/ep60/pat8/µtarget=mean(r̂) | ✓ baselines.DLinear/train_dlinear/dlinear_predict/min_cvar_weights | ✓ | AS15/AS26 | pass |
| R1 Table1 40&50 | ✓ 同管线 --top-n | ✓ 迁移豁免 | ✓ main.run_pipeline/_print_performance_table | ✓ | AS12/AS16 | pass |
| R2 Table5 30 | ✓ 同上 | ✓ | ✓ main.run_pipeline | ✓ | AS16 | pass |
| R3 Table6 10&20 | ✓ 同上 | ✓ | ✓ main.run_pipeline | ✓ | AS16 | pass |
| R4 Table7 50&100 | ✓ CSI300-50 锚趋同 | ✓ R4 锚 6 值逐位=spec | ✓ main.run_pipeline/export_results | ✓ | AS12/AS16 | pass |

**实现位置真实性（③）总结**：train/baselines/backtest/main/config 全部 done 行的实现位置经逐一反查为真实可执行代码，无 `pass`/`TODO`/`raise NotImplementedError` 空壳，无桩函数。R4 锚字典 `R4_ANCHOR_CSI300_50`（main.py:47-54）6 个模型 24 个数值逐位比对 spec §R4 Panel A：SIT 1.9373/2.3399/0.0964/1.2804、EW 1.1695/…、GMV 1.6717/…、HRP 1.7428/…、CVaR 0.8292/…、DLinear 0.5122/… 全部一致。**本次审计未发现任何空壳，故不写 not_found 行。**

---

## 二、F7 CVaR 损失数学正确性（独立重算，重点）

实现 `cvar_from_losses`（train.py:43-64）+ `cvar_portfolio_loss`（train.py:67-91）：

```
losses = -(weights * realized_returns).sum(-1)          # (N,K)  L^(k)=-(w^k)ᵀr^k   [train.py:89-90]
tail_scale = 1/((1-α)·K)                                # K=losses.shape[1]        [train.py:60]
ν = torch.quantile(losses.detach(), α, dim=1)          # 逐场景经验 α-分位 VaR_α   [train.py:61-62]
excess = clamp(losses-ν, min=0)                        # (L-ν)_+                   [train.py:63]
CVaR_i = ν + tail_scale·Σ_k excess                     # (N,)                      [train.py:64]
loss = CVaR_i.mean()                                   # N 场景均值 E[CVaR]         [train.py:91]
```

逐项对照 spec F7 Eq.20「ν_i + [1/((1−α)K)]·Σ(L_i^(k)−ν_i)_+，再对 N 场景取均值」：
- 尾部归一 1/((1−α)K)：α=0.80、K=12 → 2.4，`tail_scale`=0.4167，**分母正确**。
- ν_i 逐场景 α-分位（`dim=1`，非跨场景）：**点内统计、无跨场景/跨时间泄漏**。
- ν 已 `detach`（`detach_nu=True`，config.cvar_detach_nu=True）：包络定理 ∂CVaR/∂ν=0，梯度只经尾部超额 (L−ν)_+ 回流——**次梯度处理正确**。
- 损失 L=−wᵀr、N 场景 `.mean()`：与 Eq.17 E[CVaR] 一致。

**独立手算核对**（单场景 K=12，L 排序 [-0.05,…,0.08]，α=0.80）：ν=quantile(0.8)=0.0480，Σexcess=0.0460，CVaR=0.0480+0.0460/2.4=**0.06717**——与公式落地逐位相符。coder「给定 ν 后 CVaR=ν+尾部超额精确一致」的手算声明**属实**。

minor（CA-M4-01）见第七节：torch.quantile 用 linear 插值分位（type-7），与 RU 精确 argmin（type-1 经验分位）差 +0.0005、尾部回流 3 点 vs 2.4——忠于 spec「经验 α-分位」字面，不影响优化方向。

**基线 min-CVaR LP**（baselines.min_cvar_weights:67-135）独立核 RU-LP：目标 ζ+1/((1−α)S)·Σu_s，约束 u_s≥−wᵀr_s−ζ（a_cvar[:, :d]=−R、[:,d]=−1、对角 −1）、Σw=1、w≥0，两阶段附加 wᵀr̂≥µtarget（−r̂ᵀw≤−µtarget）——**标准 RU min-CVaR LP，符号/约束逐行正确**；此处分母用 (1−α)·S（S=历史场景数）而非 K，与 SIT 训练的 (1−α)K 区分**正确**（场景式优化 vs K 步损失，语义不同）。

---

## 三、F8 端到端（µ̂ 仅作 logits、无辅助预测损失）

- 训练唯一 loss = `cvar_portfolio_loss(w, y, α)`（train.py:220），**全模块无任何对 µ̂ 的 MSE/预测监督**。
- 梯度路径：CVaR → w=softmax(µ̂/τ)（model.py:280）→ µ̂=proj(last_slice)（model.py:279）→ 网络。梯度仅从组合级 CVaR 经 w 回流。
- `AllocationHead.forward` 返回 (w, mu)，`SIT.forward` 默认仅返回 w（model.py:361），mu 只在 `return_aux=True` 诊断路径暴露，**不进入损失**。
- 结论：F8 忠实——DFL 决策聚焦、µ̂ 仅作可微分配层 logits，无预测损失，梯度只经 w。

---

## 四、未来函数 / 训练泄漏（ml 最高优先级，逐路径独立核）

| 红线 | 实现 | 核查结论 |
|------|------|---------|
| 特征时点 ≤T | signatures.build_signature_features:261 `lo,hi=pos-H+1,pos+1`（含决策日，绝不含 t 之后） | ✓ 点时，窗口 [t−H+1, t] |
| 标签为未来 | signatures.realized_forward_returns:328-337 anchors=rb[rb≥t][:K+1]，区间 (t_{i+k−1}, t_{i+k}]（k=1..K，严格 >t） | ✓ 标签=决策日之后 K 步实现收益 |
| 特征-标签分离 | 特征 [t−H+1,t]、标签 (t,t+K]，**无重叠**；标签仅进 cvar_portfolio_loss 的 realized_returns 参数，绝不喂 model | ✓ 时点严格分离、标签不回流为特征 |
| test 封存 | main.select_hyperparams/train_sit 只用 train_set/val_set；test 仅在 build_test_inputs 推断，**不参与训练/选优/早停** | ✓ test 全程封存 |
| 超参 val 选优 | select_hyperparams:126-137 逐配置取 best **val** CVaR | ✓ 选优在验证集 |
| 协方差/CVaR 场景窗口 ≤T | backtest._history_leq:110-115 `monthly.loc[index≤date].tail(window)`；DLinear hist_windows=dlr.iloc[pos-H+1:pos+1] | ✓ 全部 ≤t 点时 |
| T 算 T+1 执行 | common.portfolio_backtest:530-534 `future=ret_index[ret_index>t]; t_next=future[0]; w_t×r_{t_next}` | ✓ 权重 T、收益严格晚于 T |
| 训练/回测口径一致 | 训练标签 w^(1)↔r^(1)=(t,t_{+1}]；回测 w^(1)×(t,t_next] 收益，同为「决策日后第 1 月」 | ✓ 一致，无错位 |

**独立结论：未发现任何未来函数 / 训练泄漏。** 这是本案 ml 最高风险维度，逐路径核实全部守住红线。

---

## 五、CA-A01 死票屏蔽 + B5 基线 / GMV 修复

### CA-A01/A03 死票·停牌屏蔽（backtest.py:48-79）
- `tradable_mask_at`：可交易 = 当日前复权 close notna（未停牌/退市）∧ t∈[first_date,last_date]（build_universe_meta:241-242 有效行情区间）。死票 last_date<test_start ⇒ within 恒 False ⇒ **权重恒 0**（逻辑保证，非依赖数值巧合）。
- `mask_renormalize`：不可交易置 0、活票 renorm 至行和=1；全不可交易回退（活票为空则 0 向量，引擎持现金）。
- sit_weight_panel（:140）与 baseline_weight_panel（:170-171,220）**均先在活票上求权重、再 mask_renormalize**，双重屏蔽。
- CA-A03 停牌：daily_simple_returns 停牌日 fillna(0)=持现金（data.py:315，AS19），决策日停牌经 px_ok=False 屏蔽。
- 结论：CA-A01 死票恒 0、活票行和=1 逻辑正确；CA-A03 停牌处理合理。

### B5 基线（baselines.py）
- EW→common.equal_weights ✓；HRP→common.hrp_weights ✓；CVaR→自实现 RU-LP（已核，见二）✓；均复用 common、未在 src 重复实现回测引擎。
- **GMV 修复（AS25）独立数学验证**：gmv_weights→`mean_variance_weights(μ=0, λ=1.0)`（baselines.py:59）。μ=0 时 max wᵀ0−λwᵀΣw = min wᵀΣw，任意 λ>0 同解，**即长仓最小方差 GMV**。独立跑验证（8 资产/150 样本良态协方差）：λ=1.0 收敛、portvar=5.31e-5 < EW 5.61e-5、max0.168/min0.085/std0.031——**产真最小方差、非退化等权，修复数学正确有效**。
- 修复方式为**改走 common 另一公开 API（mean_variance_weights），未改 common 源码**——所有权合规。

---

## 六、AS24/25/26 简化合理性 + 文件所有权

- **AS24**（ν detach + w^(1) 月度调仓）：detach 符包络定理次梯度；w^(1) receding-horizon/MPC 与月度调仓自洽。合理，已落地 train/backtest。
- **AS25**（GMV 走 mean_variance_weights + 窗口 cov120/CVaR60/min12）：GMV 修复已验证真实；窗口均 ≤T 点时（_history_leq）。合理。
- **AS26**（DLinear kernel25/µtarget=等权预测收益 mean(r̂)）：µtarget 取 EW 预测收益保 LP 恒可行（EW 天然满足），核实 baseline_weight_panel:211 `mu_target=float(np.mean(r_hat))`。合理。
- **文件所有权**：本次仅改 src/{train,baselines,backtest,main}.py（新建）与 config.py m4 段（:93-103「只增不改」追加）；**未改 m1/data.py、m2/signatures.py、m3/model.py、common 源码**。git status 中 common/utils.py(M)/data_loader.py(M) 及 allocation_backtest.py(新增)均由 allocation 首案 ssrn_6115073 沉淀（文件内注释自证），非本案 m4 改动，属「待审复用」件——本次已核其 GMV/portfolio_backtest/指标忠实性通过。合规。

---

## 七、Issue 清单

**CA-M4-01（minor，train.py:62）** — F7 的 ν 用 `torch.quantile(losses, α)` 默认 linear 插值分位（type-7）。独立手算：α=0.80/K=12 下其与 RU 精确 argmin（type-1 经验分位，第 ⌈αK⌉=10 位）偏差 +0.0005、尾部回流 3 点而非理论 (1−α)K=2.4 点。**依据**：spec F7 Eq.20 仅要求「经验 α-分位（VaR_α）」，torch.quantile(α) 是其合法实现且 ν 已 detach（偏差不入梯度、不改优化方向），故**忠于 spec、不阻断达标**；但 coder 在 AS24/矩阵称「plug-in α-分位即该逐场景 min 的解」措辞偏强（插值分位 ≠ RU argmin）。提示 verify：若关注 CVaR 绝对值精度可改 type-1 分位或对 ν 显式取 min。

**CA-M4-02（minor，baselines.py:59 / common/allocation_backtest.py:362-382）** — GMV 修复绕过而非修复 common `_min_variance_weights` 的 SLSQP λ=1e6 病态路径；该缺陷仍留 common，且 `nco_weights` 内部（:408,421,434）大量依赖 `_min_variance_weights`。本案 B5 不用 NCO，**不影响 m4**；属通用件遗留技术债。另：coder 关于「原路径 >40 资产退化等权」的诊断，本审计在低维（8 资产）未复现（λ=1e6 亦收敛），提示 verify 在 50 资产实测两路径确认诊断成立。

**CA-M4-03（minor，templates/audit/）** — templates/audit/impl_audit.md 模板缺失，code_audit 无骨架可依（本文按设计 §9.3 五维度自组织）。非 m4 代码问题，提示补模板。

---

## 八、已检查维度清单（code 五维度，无省略）

- [x] **①公式一致**：F7 RU 经验式（含独立手算）、F8 梯度路径、B5 min-CVaR LP、B6 四指标、B7 两阶段 LP 逐一对照 spec/Eq，符号/分子分母/算子一致。
- [x] **②参数一致**：α=0.80/K=12/(1−α)K=2.4、Adam lr1e-3/bs64/dropout0.1/ep100/pat10、seeds(0,1,2)、网格 8 组、cov120/CVaR60/min12、DLinear kernel25/lr1e-3/ep60/pat8、cost0bps、rf0/年化12 逐一比对 config vs spec B1-B8/AS，全部一致。
- [x] **③实现位置真实**：12 done 行实现位置逐一反查为真实代码，无空壳/TODO/pass；R4 锚 24 数值逐位=spec。未发现空壳。
- [x] **④代码反查（无私货）**：strategy/backtest 公开函数均映射 spec 要素 ID，未见未登记的额外机制/夹带逻辑。
- [x] **⑤简化声明完备**：AS1/AS5/AS14/AS15/AS18/AS24/AS25/AS26 覆盖全部 m4 简化，无未登记 deviation。
- [x] **ml 专项**：未来函数 8 条红线路径 + 训练泄漏（test 封存/val 选优/特征-标签分离）+ CVaR 数学 + CA-A01 死票 + GMV 修复，全部独立重算核实。

---

verdict: pass_with_issues
