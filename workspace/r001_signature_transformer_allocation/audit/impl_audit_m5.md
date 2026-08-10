# impl_audit · m5「消融与敏感性分析」实现忠实性审计（mode=code）

- report_id: r001_signature_transformer_allocation
- milestone: m5（deps m4）
- 审计对象要素: SA1 / SA2 / SA3 / SA4 / B4（coverage_matrix 全部 done 行）
- 待审文件: `src/r001_signature_transformer_allocation/{ablation.py, sensitivity.py, model.py(m5 开关), train.py(m5 objective/ablation), config.py(m5 段)}`
- 对照基准: spec SA1/SA2/SA3/SA4/B4 + assumptions AS27（消融口径）/AS10（SA3 定性）/AS5（种子）/AS6（τ）
- 审计方式: 只读代码 + 独立合成对照重算（不采信 coder 自述）；模板 `templates/audit/impl_audit.md` 不存在，按设计 §9.3 五维度组织
- 独立执行记录: `/tmp/sa1_probe.py`（四开关合成对照）、`/tmp/sa234_probe.py`（SA2/SA4 复算）、`pytest`（20 项单测）——均由审计者亲自运行

---

## 零、结论速览

- **四消融开关语义: 逐一独立跑合成对照，全部正确**（w/o CVaR / w/o Asset Attn / w/o Financial Bias / w/o Gate γ）。
- **向后兼容成立**：默认开关 False/None，`set_ablation(None)` 前向与未调用逐位一致（maxdiff=0）；test_model + test_signatures 20 项单测全绿。
- **SA2/SA3/SA4/B4 公式与聚合口径忠实**：SA2 强度/入向注意力聚合轴与归一独立复算逐位一致；SA4 HHI/熵公式独立复算逐位一致；B4 成本口径为单边比例（cost=Σ|Δw|·c/1e4）忠于 spec。
- 未发现 critical / major；2 条 minor（SA3 无多种子 mean±std 聚合；SA3 τ 网格 5 点 vs 原文 7 档，后者已在 plan/AS 登记）。
- **空壳判定: 无**——SA1-4/B4 全部实现位置均为真实函数体，无 pass/TODO/占位；不存在 not_found 空壳。

---

## 一、四消融开关语义正确性（本次审计核心，独立合成对照）

审计者构造小型 SIT（d_model=8/heads=2/layers=1、d=5~6 资产、随机合成 F_ti），逐一驱动开关并与手工复算比对（脚本 `/tmp/sa1_probe.py`，实测输出见下）。**语义结论不采信 coder 自述，均为独立重算所得。**

### SA1-(i) w/o CVaR —— 正确
- 实现: `train.py:110-115` `portfolio_loss(objective)`；`objective="mean"` 时 `return (-step_return).mean()`（`train.py:112-114`），即最小化 `E[−(w^k)ᵀr^k]`＝风险中性最大化均值收益；`ablation.py:43` 变体登记 `("w/o CVaR", None, "mean")`（结构保 full、仅换损失层）。
- 早停一致性: `train.py:264` `evaluate_cvar(objective=objective)`，验证/早停指标随训练目标切换为 mean，非仍用 CVaR。
- 独立重算: cvar=0.012705、mean=−0.001297，**两目标确有实质差异（cvar≠mean）**；`objective="cvar"` 与 `cvar_portfolio_loss` 逐位一致，`objective="mean"` 与手算 `E[−wr]` 逐位一致。
- 判据: 真把训练目标从 CVaR 换成非尾部目标（均值），非仍用 CVaR。**语义正确**。承重墙保护：(1−α)K=2.4≥1（`config.py:118-122` 强校验），CVaR 未退化为均值，消融差非零可现。

### SA1-(ii) w/o Asset Attn —— 正确
- 实现: `model.py:252` `SITBlock.ablation_disable_asset_attn`（默认 False）；`model.py:264-268` True 时整个 F5 子层（asset_attn + 残差 + LN）跳过，块退化为「时间因果注意力(F4) + FFN」。
- 独立重算: 手工复算「temporal→ln→(跳 asset)→ffn→ln」与开关输出 **maxdiff=0 逐位一致**；且与 full 输出确有差异。
- 判据: 真跳过签名增强资产维注意力、只留时间注意力（+FFN），非仅去偏置。**语义正确**。

### SA1-(iii) w/o Financial Bias —— 正确
- 实现: `model.py:161` `SignatureAssetAttention.ablation_disable_bias`（默认 False）；`model.py:216-219` True 时 `attn=softmax(qk)`（去 γ·B、退回标准资产注意力），保留 QK 注意力结构本身。
- 独立重算: disable_bias=True 时 attn **== softmax(qk)（maxdiff=0）**；full 时 attn==softmax(qk+γ·B) 且与 no_bias 有差异。
- 判据: 真把签名偏置项 γ·B 置零/移除（β 关系嵌入不进 softmax、不作用），保留普通资产注意力。**语义正确**。

### SA1-(iv) w/o Gate γ —— 正确
- 实现: `model.py:397` `set_ablation` 令 `ablation_gamma_fixed=1.0`；`model.py:171-175` gamma property 命中固定分支返回常数 1.0（不再 softplus、gamma_hat 无梯度＝固定 gate、保留偏置 B）。
- 独立重算（「logits 差异是否恰为 γ 因子」专项）: 同输入下 full 用 γ=softplus(γ̂)=0.693147、w/o Gate 用 γ=1.0，二者 logits 之差 =(1−0.693147)·bias=0.306853·bias；实测非零 bias 位置的差/bias 比例区间 [0.306777, 0.307220]≈0.306853（float32 噪声），**差异恰为 γ 因子对 bias 的缩放**。property 复核 no_gate γ=1.000000、full γ=0.693147。
- 判据: 真固定 γ=1（非仍 softplus 可学习）。**语义正确**。

四开关小结：**w/o CVaR 正确 / w/o Asset Attn 正确 / w/o Financial Bias 正确 / w/o Gate γ 正确**，四者相互隔离（各只改单组件、其余不变，忠于 spec SA1「其余超参不变」）。

---

## 二、五维度逐条核对（设计 §9.3）

### 维度 1 · 公式一致
| 要素 | spec 公式 | 实现 | 判定 |
| --- | --- | --- | --- |
| SA1 w/o CVaR | 换风险中性最大化均值收益（p6） | `E[−(w^k)ᵀr^k]`（train.py:112-114） | 一致 |
| SA2 s_{t,j} | `1/(H·N_H·d)·Σ_{k,h,m}(B_{k,h})_{m,j}`（p7） | bias 沿 (H,N_H,query=m) 求和保留 key=j、除 H·N_H·d（sensitivity.py:69-72） | 一致（独立复算逐位相等） |
| SA2 a_{t,j} | `1/(H·N_H·d)·Σ_{k,h,m}α_{k,h,m→j}`（p7） | attn 同轴求和、入向份额=key 列和（softmax over key，行和=1 已佐证） | 一致 |
| SA3/B4 成本 | 单边比例 c∈{0,5,10}bps/每美元成交（p8） | cost=turnover(Σ|Δw|)·c/1e4（allocation_backtest.py:525,548） | 一致（单边=每美元成交计一次） |
| SA4 HHI | `HHI(w)=Σ_j w_j²`（p8） | `(w*w).sum(-1)`（sensitivity.py:187） | 一致（独立复算逐位相等） |
| SA4 Shannon 熵 | `H(w)=−Σ_j w_j·log w_j`（p8） | `-(w*log(w)).sum(-1)`（sensitivity.py:188） | 一致 |

独立复算证据: SA2 s/a 独立复算 == 函数输出（allclose True）、norm=H·N_H·d=720、α 总和=2880=N·H·N_H·d 佐证入向列和口径；SA4 三档 τ 手算 HHI/熵与函数逐位一致、权重和=1.000000。

### 维度 2 · 参数一致
- α=0.80（config.py:46）、K=12（config.py:42）→ (1−α)K=2.4，消融方向性所依赖的 CVaR 非退化承重墙成立（config.py:118-122 强校验）。
- B4 成本档 c∈{0,5,10}bps（config.py:107 `sa3_cost_grid_bps`）＝spec B4/SA3 三档，一致。
- w/o Gate 固定值 γ=1.0（model.py:397）＝spec/AS27「固定 γ=1」，一致。
- SA4 τ 轴 {0.5,0.75,1.0,1.25,1.5,1.75,2.0}（config.py:109）＝spec Fig6 p8 τ 轴范围，一致。
- 消融「其余超参（d_model/H/K/α/lr）不变」：变体仅改 objective 或 set_ablation 单组件、共用同一 config（ablation.py:85-91），一致。

### 维度 3 · 实现位置真实（反查 coverage_matrix done 行）
逐条打开对应函数体，均为真实实现、非 pass/TODO/空壳：
- SA1: `ablation.py:run_sa1(66)/SA1_VARIANTS(41)/variant_backtest_metrics(56)/print_sa1_table(103)` + `model.py:SIT.set_ablation(383)/disable_bias(161)/gamma_fixed(162)/disable_asset_attn(252)` + `train.py:portfolio_loss(94)` —— 全真实。
- SA2: `sensitivity.py:signature_attention_scores(47)/signature_attention_correlation(76)/run_sa2(82)` —— 全真实。
- SA3/B4: `sensitivity.py:sharpe_tau_cost_grid(108)/run_sa3(147)` —— 全真实。
- SA4: `sensitivity.py:diversification_vs_tau(168)/run_sa4(195)` —— 全真实。
- **空壳判定: 无**（不存在指向 pass/TODO/占位或不存在符号的实现位置；无 not_found）。

### 维度 4 · 代码反查（独立重算，见第一节 + 维度1 独立复算）
关键数值/语义一律审计者亲自跑合成对照重算，未引用 coder「冒烟实测」自述。四开关语义、SA2 聚合、SA4 公式、向后兼容均通过独立重算比对。

### 维度 5 · 简化声明
- AS27（消融口径/SA2 索引/SA3-SA4 权重来源）：w/o CVaR=换 mean、w/o Asset Attn=跳整层、w/o Financial Bias=去 γ·B、w/o Gate=固定 1、SA2 query=源/key=目标、SA4 用原始 softmax 权重 —— 与实现逐条对齐，**声明属实**。
- SA3 τ 网格取 5 点 {0.8,1.0,1.2,1.3,1.4}（config.py:91）：plan m5（第 229 行）与 AS6/AS10 已登记的缩减，**已声明**（非隐藏偏离）。
- AS10（SA3 自生成、定性对比）、AS5（3 种子 mean±std）：均登记。
- 未发现「未登记的简化」（deviation_undeclared）。向后兼容开关默认关闭、不改 m3/m4 现行为，无 core 要素隐藏偏离。

---

## 三、向后兼容 / 未来函数 / 文件所有权

- **向后兼容**: `SignatureAssetAttention` 默认 disable_bias=False、gamma_fixed=None（model.py:161-162）；`SITBlock` 默认 disable_asset_attn=False（model.py:252）；`portfolio_loss` 默认 objective="cvar"（train.py:99）；`train_sit` 默认 ablation=None（train.py:202）。独立实测：同种子两模型（一个 set_ablation(None)、一个未调用）前向 **maxdiff=0 逐位一致**；`pytest test_model.py test_signatures.py` **20 passed**。m1-m4 行为未变，结论成立。
- **未来函数**: SA1 变体经 train/val 训练、val 选优、test 评估（复用 m4 train_sit 基础设施，test 封存）；SA2/SA3/SA4 全在 test 段决策日以点时 F_ti 评估，τ sweep 只改推断期 softmax 温度、不重训、不引未来信息；SA3 成本经 T+1 换手扣减（portfolio_backtest 未来函数红线）。**无泄漏**。
- **文件所有权**: ablation.py/sensitivity.py 位于 src/{id}/，仅从 common 复用（backtest/allocation_backtest）不写回 common；m5 新增开关（model.py/train.py）均在 src/{id}/。m5 公开函数全部映射 SA1-4/B4，无未登记「私货」。
- **AS27 合理性**: 各口径（跳整层 vs 置零、γ 固定取 1、B/α 的 query-key 朝向、HHI 用原始权重）均为 spec 未钉死的实现自由度，取法忠于 spec 措辞与通行做法，合理。

---

## 四、issue 清单

| 编号 | severity | 证据定位 | 依据 |
| --- | --- | --- | --- |
| CA-A01 | minor | `sensitivity.py:108-144`（sharpe_tau_cost_grid） | SA3 (τ,c) 网格为单模型点估计，未做多种子 mean±std 聚合；spec SA3「报告每 (τ,c) 对均值±std Sharpe」+AS5「3 种子 mean±std」。方向（成本↑⇒Sharpe↓）不受影响，实验模式数值豁免（AS10），完整档可补种子聚合，留 verify。 |
| CA-A02 | minor | `config.py:91` / `sensitivity.py:131` | SA3 τ 网格 5 点 {0.8,1.0,1.2,1.3,1.4} vs 原文 Fig5 7 档 τ（spec SA3 measurement「7 档 τ」）；范围 [0.8,1.4] 与峰值 τ≈1.3 均保留，属 plan m5/AS6/AS10 已登记缩减（已声明），仅覆盖粒度略降，数值豁免。 |

无 critical、无 major。

---

## 五、已检查维度清单（对应 code 五维度 + 本次重点，无遗漏）

- [x] 维度1 公式一致：SA1(mean)/SA2(s,a)/SA3-B4(成本)/SA4(HHI,熵) 逐式核对 + 独立复算
- [x] 维度2 参数一致：α=0.80/K=12/(1−α)K=2.4、c∈{0,5,10}bps、γ固定=1、τ 轴
- [x] 维度3 实现位置真实：coverage_matrix m5 全 done 行反查，均真实函数体，无空壳/not_found
- [x] 维度4 代码反查：四开关合成对照 + SA2/SA4 独立复算（不采信自述）
- [x] 维度5 简化声明：AS27/AS10/AS5/AS6 逐条对齐，无未登记简化
- [x] 重点·四消融开关语义：w/o CVaR / Asset Attn / Financial Bias / Gate γ 各正确（独立跑合成对照，含 w/o Gate 的「差异恰为 γ 因子」专项）
- [x] 重点·向后兼容：默认开关 + set_ablation(None) 前向逐位一致 + 20 项单测全绿
- [x] 未来函数：SA1-4 均 test 点时评估、无泄漏；文件所有权、AS27 合理性

---

verdict: pass_with_issues
