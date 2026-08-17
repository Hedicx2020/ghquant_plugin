---
report_name: r001_signature_transformer_allocation
title: Signature-Informed Transformer for Asset Allocation
institution: Pusan National University; University of Oxford
report_date: 2026-01-23
authors: Yoontae Hwang、Stefan Zohren
market: 美股
pdf_pages: 21
exhibit_declared: {fig_max: 7, tbl_max: 7}
element_counts: {D: 5, F: 8, B: 8, R: 4, SA: 4, FIG_registered: 7, TBL_registered: 7}
type_hint: allocation
tags_hint: [ml]
extraction_date: 2026-07-13
---

# Signature-Informed Transformer for Asset Allocation 复现规格书

> 本文只陈述「研报说了什么」，页码引用制，不做复现设计。原文为美股（S&P100 / DOW30）为主、附中国 CSI300 的多组股票 universe；本 spec 一律按原文口径登记市场/区间/数值，不做市场迁移映射（迁移是 planner 职责）。

## 一、研报元信息与结构地图

- 论文类型：方法论论文（端到端深度学习资产配置模型 + 实证），非机构卖方研报，无传统「摘要/目录/免责声明」结构。
- 章节目录抄录（据正文标题，含页码）：
  - Abstract + 1. Introduction（p1）
  - 2. Methodology / 2.1 Preliminaries / 2.2 Signature-Informed Transformer（p2-p4）
  - 3. Experiment / 3.1 Implementation details / 3.2 风险调整绩效 / 3.3 模块贡献 / 3.4 签名驱动注意力 / 3.5 PFL 失败原因 / 3.6 Sensitivity Analysis（p5-p8）
  - 4. Conclusion（p8）
  - References（p9-p10）
  - Appendix A. Related works（p11-p12）
  - Appendix B. Notation（p12-p13）
  - Appendix C. Mathematical Proofs（p12-p15）
  - Appendix D. Implementation details（p16）
  - Appendix E. Why we choose CVaR?（p17-p18）
  - Appendix F. Details of Predict-then-Optimize Baselines（p18）
  - Appendix G. Additional Experiments（p19-p20）
  - Appendix H. Drawdown with Gamma(γ)（p21）

- 页面覆盖表（逐页标注内容类型，供审计逐页扫描核对）:

  | 页码 | 内容类型 | 关联要素 |
  | --- | --- | --- |
  | p1 | 封面/摘要/引言/Figure1 概念图 | D1, F8, FIG1 |
  | p2 | 方法-预备/路径签名/问题定义/CVaR目标式 | F1, F2, F6, F7, B8, D4 |
  | p3 | 架构图/签名嵌入/签名增强注意力(上) | F1, F3, F4, F5, FIG2 |
  | p4 | 注意力(下)/Theorem2.2/训练策略 | F5, F6, F7, F8 |
  | p5 | Table1主结果/实验设置/数据集/基线/指标 | R1, D1, D2, D3, B5, B6, TBL1 |
  | p6 | 指标续/绩效讨论/Table2消融/模块贡献 | SA1, B6, TBL2 |
  | p7 | 3.4签名注意力/Figure3/Figure4/3.5 PFL失败 | SA2, FIG3, FIG4 |
  | p8 | Figure5/Figure6/3.6敏感性/结论 | SA3, SA4, B3, B4, FIG5, FIG6 |
  | p9 | 参考文献 | - |
  | p10 | 参考文献 | - |
  | p11 | 附录A 相关工作(PFL/DFL/Transformer/签名) | F8 |
  | p12 | 附录A续/附录B符号引言/附录C 严格lead-lag定义 | F2 |
  | p13 | Table3符号表/Theorem C.2 | TBL3 |
  | p14 | Theorem C.2证明/Theorem C.3 | - |
  | p15 | Theorem C.3证明 | - |
  | p16 | 附录D 实现细节/Table4超参搜索空间 | B1, B2, TBL4 |
  | p17 | 附录E 为何选CVaR/Theorem E.1 | F7 |
  | p18 | 附录E续/附录F 两阶段基线公式 | B7 |
  | p19 | 附录G/Table5(30资产)/Table6(10&20资产) | R2, R3, TBL5, TBL6 |
  | p20 | Table7(50&100资产CSI300) | R4, TBL7 |
  | p21 | 附录H/Figure7 drawdown与γ | FIG7 |

## 二、数据要求（D 类）

### [D1] 实验股票池 universe（7 组）
- 页码: p5
- 原文: > "Experiments used three portfolios of 30, 40, and 50 S&P 100 companies. We also selected two additional portfolios of 10 and 20 assets from the DOW30 ... two portfolios consisting of 50 and 100 assets from the CSI 300 index."
- 数据状态: missing
- 说明: 共 7 组 universe——S&P100 取 30/40/50 只；DOW30 取 10/20 只；CSI300 取 50/100 只。原文未列具体成分股名单，也未说明从各指数中挑选子集的规则。Figure 1（p1）示意性出现 TSLA/NVDA/AAPL 三个标签，但原文未声明其归属于哪一组 universe。
- 关联要素: R1, R2, R3, R4 / 关联歧义: A3

### [D2] 数据来源与频率（WRDS 日频价格）
- 页码: p5
- 原文: > "The daily price data was sourced from Wharton Research Data Services (WRDS)."
- 数据状态: missing
- 说明: 日频（daily）价格数据，来源 Wharton Research Data Services (WRDS)；本地是否可得由 planner 对照 data_catalog 判定，此处按原文登记为外部来源。
- 关联要素: D1, D3

### [D3] 训练/验证/测试时间划分
- 页码: p5
- 原文: > "The training set spans from January 1, 2000, to December 31, 2016. The validation set from January 1, 2017, to December 31, 2019 and the test set from January 1, 2020, to December 27, 2024."
- 数据状态: missing
- 说明: 按时间顺序（chronologically）划分为不重叠三段——训练 2000-01-01 至 2016-12-31；验证 2017-01-01 至 2019-12-31；测试 2020-01-01 至 2024-12-27。固定划分，非滚动。
- 关联要素: D1, B1

### [D4] 模型输入信息集 F_ti 构成
- 页码: p2
- 原文: > "(i) for each asset j, a sequence of truncated path signatures ... (ii) pairwise cross-signatures ... for all asset pairs (j,l) ... (iii) a sequence of deterministic calendar feature vectors {v_ti−H+k}, where v_t ∈ R^F."
- 数据状态: derive
- 说明: 决策时刻 ti 的信息集三部分——(i) 每资产 H 个回看切片的截断路径签名；(ii) 全窗口 [ti−H, ti] 上所有资产对的成对交叉签名；(iii) H 个确定性日历特征向量 v_t ∈ R^F。日历特征的具体内容与维度 F 原文未明确。
- 关联要素: F1, F2, F3 / 关联歧义: A4

### [D5] 连续路径重建（插值）与实现收益向量构造
- 页码: p2
- 原文: > "To apply signature methods, we treat the price series as a continuous path via an appropriate interpolation. Let S_u ∈ R^d denote the price path ... We use r_{t} ∈ R^d to denote the vector of asset returns realized over the interval [t_{i+k−1}, t_{i+k}]."
- 数据状态: derive
- 说明: 两项数据构造，均为签名特征与组合损失的输入前置——(i) 连续路径重建：离散观测价格 S_t 需经「适当插值」(appropriate interpolation) 重建为连续价格路径 S_u ∈ R^d（第 i 分量为资产 i 价格），供路径签名（F1/F2）计算；具体插值方法（线性/其他）原文未披露。(ii) 实现收益向量 r_t ∈ R^d：定义为区间 [t_{i+k−1}, t_{i+k}] 上各资产的实现收益，是组合损失 L^(k)=−wᵀr（F7）与回测评估（B6）的收益输入；收益计算口径与复权方式原文均未披露。
- 关联要素: F1, F2, F7, B6 / 关联歧义: A4

## 三、因子/策略定义（F 类）

### [F1] 路径签名特征（Rough Path Signature，截断阶 M=2）
- 页码: p2, p16
- 原文: > "SigM(X[s,t]) = (1, ∫ dXu, ∫∫ dXr ⊗ dXu, . . .)." / (Table 4 Panel E) "Sig Level 2"
- 公式（转写）: 对连续路径 X:[s,t]→R^d，签名为迭代积分张量序列，截断至阶 M 得有限维向量 SigM(X)∈R^dsig；一阶项=净增量，二阶项=signed area。SIT 取 M=2（Table 4 Panel E "Sig Level 2"）。
- 参数: 截断阶 M=2；签名更新用 Chen relation 避免全历史重算（p3 "the signature update uses Chen relation ... avoids recomputation over the full history"）。
- 依赖数据: D2, D4 / 关联基准: R1

### [F2] 成对交叉签名与 signed-area lead-lag（二阶项）
- 页码: p2, p12
- 原文: > "second-order terms encode signed areas, revealing non-trivial correlations and lead-lag effects." / (Eq.21) "A(X^i, X^j) = ∫ X^i dX^j − ∫ X^j dX^i."
- 公式（转写）: 两资产路径的二阶联合签名交叉项 A(X)=∫X^1 dX^2 − ∫X^2 dX^1 编码 signed area，为 lead-lag 的稳健度量。Proposition 2.1（p2）：严格 lead-lag 结构 ⇒ A(X)>0。
- 参数: 逐资产对 (j,l) 在整个回看窗口 [ti−H, ti] 上计算交叉签名 c_i,j,l ∈ R^dcross-sig。
- 依赖数据: D4 / 关联要素: F5

### [F3] 签名嵌入输入 token（三嵌入融合，Eq.4）
- 页码: p3
- 原文: > "x_k,j = Wproj[e_sig,k,j ⊕ e_date,k ⊕ e_asset^j] ∈ R^dmodel"（⊕ 表拼接）
- 公式（转写）: 对切片 k、资产 j，融合三源——签名嵌入 e_sig（线性投影自截断签名 s_k,j）、日历嵌入 e_date（切片共享）、可学习资产嵌入 e_asset^j，拼接后经线性投影 Wproj 得输入 token；输入张量形状 H×d×dmodel。
- 参数: dmodel（隐维）∈ 搜索空间；见 B2。
- 依赖数据: D4 / 关联要素: F1, F4

### [F4] 时间维因果自注意力（temporal attention）
- 页码: p3
- 原文: > "following a standard causal self-attention pass along the temporal dimension within each factorized layer." / "The asset-wise attention treats the time dimension as a batch dimension."
- 公式（转写）: 每个 factorized 层内先沿时间维做标准因果（causal）自注意力；资产维注意力则把时间维当作 batch 维、对 H 个切片独立计算。标准多头自注意力，NH 个头。
- 参数: NH（头数）∈ 搜索空间；见 B2。
- 关联要素: F3, F5

### [F5] 签名增强资产维自注意力（核心创新，含 β/qdyn/gate γ）
- 页码: p3-p4
- 原文: > "Headk,h = softmax(Qk,h Kk,h^T/√dk + γ Bk,h) Vk,h" / "scaled by a learnable, strictly positive scalar gate, γ > 0 (parameterized as γ = softplus(γ̂))"
- 公式（转写）: 沿资产维的注意力 logits 叠加签名诱导偏置：Logits = QK^T/√dk + γ·B（Eq.11/14）。偏置项 b_k,h,j,l = ⟨(qdyn_k,j)_h, (β_i,j,l)_h⟩（Eq.10），其中关系嵌入 β_i,j,l = MLPβ(c_i,j,l) ∈ R^(NH×dβ)（Eq.8，逐头分离），动态查询 qdyn_k,j = MLPq(x'_k,j) ∈ R^(NH×dβ)（Eq.9）；gate γ=softplus(γ̂)>0 为可学习标量，控制签名偏置整体幅度。头拼接后经 WO + 残差 + LayerNorm（Eq.15-16）。Theorem 2.2（p4）：γ>0 时 αj,l 对 β 的方向导数严格为正。
- 参数: dβ（偏置嵌入维）、HIDDEN C、MLPβ/MLPq 结构原文未明确；见 B2。
- 依赖数据: F2 / 关联要素: F2, F4 / 关联歧义: A7

### [F6] 输出头与 softmax 分配层（long-only、fully-invested、温度 τ）
- 页码: p2, p4
- 原文: > "w_ti^(k)(θ) = softmax(µ̂_ti^(k)(θ)/τ) ∈ R^d, ensuring a long-only, fully invested allocation at each future step." / 输出头 "a linear projection (optionally preceded by pooling over the H slices or using the last slice) produces µ̂_ti^1:K ∈ R^K×d."
- 公式（转写）: 输出头把 Transformer 输出映射为 K 步预期收益 µ̂_ti^1:K ∈ R^(K×d)；每步 k 经 softmax 温度 τ 转为组合权重 w=softmax(µ̂/τ)，天然满足 long-only（非负）+ fully-invested（求和为1）。µ̂ 仅作 allocation 层 logits，不以预测损失训练。
- 参数: τ>0 为 softmax 温度（Allocation Concentration）；主结果表所用 τ 取值原文未明确（敏感性分析 sweep τ∈{0.8,...,1.4}，见 SA3）；pooling 与 last-slice 二选一原文未定。
- 关联要素: F7, F8 / 关联歧义: A6

### [F7] CVaR 训练目标函数（置信水平 α，对偶经验式）
- 页码: p2, p4, p17
- 原文: > "min_θ E_ω∼D [CVaRα({L_ti+k^(k)(θω)}_k=1^K)]"（Eq.3/17）；步 k 组合损失 "L_ti+k^(k)(θω) = −(w_ti^(k)(θ))^T r_ti+k(ω)"。
- 公式（转写）: 直接最小化 K 步损失序列在场景内的期望 CVaR（Eq.17-20 给出对偶式与经验式，逐场景 ν̂_i 取该场景损失的经验 α-分位）。附录 E（p17）论证在 1−α<q（尾部质量小于崩盘概率）时对冲组合在 CVaR 意义下严格占优。
- 经验式（Eq.20，p4-p5）: 逐场景 i 最小化 ν_i + [1/((1−α)K)]·Σ_{k=1}^K (L_i^(k) − ν_i)_+，再对 N 个场景取均值；ν_i 为该场景内 K 个损失的经验 α-分位（VaR_α）。
- 参数: 置信水平 α∈(0,1)——实验所用 α 具体数值原文（正文与附录）均未给出。
- 关联要素: F6, F8 / 关联歧义: A1

### [F8] 端到端决策对齐范式（µ̂ 仅作 logits，无辅助预测损失）
- 页码: p4, p11
- 原文: > "No auxiliary prediction losses are used. Eq. (17) is the sole training signal" / (p11) "the predicted returns µ̂ serve only as internal logits for a differentiable allocation layer. All parameters are trained end-to-end solely through the portfolio-level CVaR objective, not a pointwise prediction loss."
- 公式（转写）: 统一策略 gθ:F_ti↦µ̂，梯度仅从组合级 CVaR 目标回流；µ̂ 不用预测损失训练，属 Decision-Focused Learning，区别于 predict-then-optimize 两阶段（PFL）。
- 关联要素: F6, F7, B7

## 四、回测设置（B 类）

### [B1] 训练通用超参（全模型一致）
- 页码: p16
- 原文: > "the Adam optimizer with a learning rate of 10−3, a batch size of 64, a dropout rate of 0.1. We train all models for a maximum of 100 epochs, utilizing an early stopping mechanism with a patience of 10 epochs."
- 参数值: 优化器=Adam；学习率=1e-3；batch size=64；dropout=0.1；最大 epoch=100；early stopping patience=10。验证集选最优超参组合后在测试集评估。
- 关联要素: D3, B2

### [B2] SIT 超参网格搜索空间（Table 4 Panel E）
- 页码: p16
- 原文: > (Table 4 Panel E, SIT) "D MODELS 8,16,32,64；D FFS 8,16,32,64；E LAYERS LIST 1,2；N HEADS LIST 2,4,8；Sig Level 2；HIDDEN C 8,16,32"
- 参数值: d_model∈{8,16,32,64}；d_ff∈{8,16,32,64}；层数∈{1,2}；头数∈{2,4,8}；签名阶=2（固定）；HIDDEN C∈{8,16,32}。网格搜索、验证集选优。（其他基线搜索空间见 Table 4 Panel A-D。）
- 关联要素: F1, F3, F5, B1

### [B3] 组合再平衡频率（月度 k-step）
- 页码: p8
- 原文: > "long-only, fully invested, monthly (k-step) rebalancing on the 40- and 50-asset universes, and a zero risk-free rate for all risk-adjusted metrics."
- 参数值: 调仓频率=月度（monthly，即 k-step）；long-only、fully-invested；风险调整指标用零无风险利率。
- 关联要素: F6, B6

### [B4] 交易成本设定（单边 0/5/10 bps）
- 页码: p8
- 原文: > "Transaction costs are one-way proportional fees of c ∈ 0, 5, 10 basis points per dollar traded. ... We sweep τ ∈ {0.8, ..., 1.4}."
- 参数值: 单边比例费率 c∈{0, 5, 10} bps/每美元成交，用于敏感性分析（SA3）；主绩效表（Table 1 等）默认设定未显式标注成本（推断为 0 bps，见歧义 A9）。
- 关联要素: SA3 / 关联歧义: A9

### [B5] 对比基线清单（4 传统 + 8 预测类）
- 页码: p5
- 原文: > "Traditional baselines include Equally Weighted Portfolio (EWP) ... Global Minimum Variance (GMV) ... Conditional Value-at-Risk (CVaR) ... and Hierarchical Risk Parity (HRP)." / "Autoformer ... DLinear ... FEDformer ... PatchTST ... iTransformer ... Non-stationary Transformers (NSformer) ... TimesNet and RFormer."
- 参数值: 传统基线 4 个——EW(EWP 等权)、GMV(全局最小方差)、CVaR、HRP(层次风险平价)；预测-优化两阶段深度学习基线 8 个——Autoformer、DLinear、FEDformer、PatchTST、iTransformer、NSformer、TimesNet、RFormer（其预测输入接第二阶段 CVaR 优化，见 B7）。
- 关联要素: R1, B7

### [B6] 评估指标（4 项，零无风险利率）
- 页码: p5-p6
- 原文: > "four standard financial metrics, assuming a zero risk-free rate ... the Sharpe Ratio ... the Sortino Ratio ... Final Wealth Factor, while the Maximum Drawdown quantified the largest peak-to-trough percentage decline, with a lower value being preferable."
- 参数值: Sharpe Ratio（↑）、Sortino Ratio（↑，仅下行波动）、Maximum Drawdown（↓，峰谷最大跌幅）、Final Wealth Factor（↑，终值财富因子）；无风险利率=0。
- 关联要素: R1, R2, R3, R4

### [B7] 两阶段 Predict-then-Optimize 基线实现（MSE + Mean-CVaR）
- 页码: p18
- 原文: > (Stage1) "LMSE(θ) = (1/T) Σ ∥r_t+1 − r̂_t+1∥2^2" / (Stage2) "minimize ζ + 1/((1−α)S) Σ (−(w^T r_s) − ζ)^+ subject to w^T r̂_t+1 ≥ µtarget, w∈W."
- 参数值: 阶段一：预测模型 fθ 以 MSE 损失训练（仅追求预测精度）；阶段二：冻结预测器，其输出 r̂ 作预期收益，在单纯形约束下最小化 CVaR、并加目标收益约束 w^T r̂ ≥ µtarget；S 为历史场景数、ζ 为 VaR 辅助变量。α、S、µtarget 具体值原文未给。
- 关联要素: B5, F8 / 关联歧义: A1

### [B8] 回看窗口 H 与预测/决策窗口 K
- 页码: p2
- 原文: > "construct portfolios of d assets for each of the next K periods ... over a lookback window of H time steps."
- 参数值: 回看窗口长度=H（time steps）；未来构建组合的步数/预测窗口=K。H、K 的具体数值原文正文与 Table 4 搜索空间均未给出（n/a）。
- 关联要素: D4, F3, F6 / 关联歧义: A2

## 五、研报核心数值结果基准（R 类）

### [R1] Table 1 · 40 与 50 资产 S&P100 绩效（主结果表）
- 页码: p5
- 原文: > "Portfolio performance of SIT versus baselines across 40- and 50-asset universes. ... SIT (Ours) 0.6717 ± 0.0628 | 0.8232 ± 0.0792 | 0.3611 ± 0.0037 | 1.7903 ± 0.1023"（40资产行）
- 数值表（与研报 Table 1 逐格一致，原样含 ± 标准差；未给格子写 n/a）:

  Panel A · Asset 40 Universe (S&P100)

  | Models | Sharpe (↑) | Sortino (↑) | MaxDrawdown (↓) | Final Wealth (↑) |
  | --- | --- | --- | --- | --- |
  | CVaR | 0.1531 | 0.2001 | 0.3516 | 1.0569 |
  | EW | 0.5759 | 0.7153 | 0.3688 | 1.6439 |
  | GMV | 0.4148 | 0.5337 | 0.2743 | 1.3258 |
  | HRP | 0.4958 | 0.6171 | 0.3185 | 1.4561 |
  | Autoformer | 0.2499 ± 0.1405 | 0.3423 ± 0.1980 | 0.3812 ± 0.0480 | 1.1809 ± 0.2403 |
  | DLinear | 0.3167 ± 0.1326 | 0.4513 ± 0.2005 | 0.3621 ± 0.0407 | 1.2915 ± 0.2133 |
  | FEDformer | 0.4006 ± 0.2317 | 0.5540 ± 0.3192 | 0.3647 ± 0.0167 | 1.5198 ± 0.5703 |
  | iTransformer | 0.3157 ± 0.0749 | 0.4233 ± 0.0943 | 0.4136 ± 0.0326 | 1.2860 ± 0.0147 |
  | NSformer | 0.4074 ± 0.1151 | 0.5820 ± 0.1655 | 0.4475 ± 0.0672 | 1.5129 ± 0.3010 |
  | PatchTST | 0.3286 ± 0.2021 | 0.4540 ± 0.2818 | 0.4523 ± 0.0838 | 1.3409 ± 0.3886 |
  | TimesNet | 0.3568 ± 0.0782 | 0.4959 ± 0.1019 | 0.4704 ± 0.0701 | 1.3765 ± 0.1729 |
  | RFormer | 0.4901 ± 0.1437 | 0.6308 ± 0.1828 | 0.3415 ± 0.0482 | 1.5387 ± 0.2353 |
  | SIT (Ours) | 0.6717 ± 0.0628 | 0.8232 ± 0.0792 | 0.3611 ± 0.0037 | 1.7903 ± 0.1023 |

  Panel B · Asset 50 Universe (S&P100)

  | Models | Sharpe (↑) | Sortino (↑) | MaxDrawdown (↓) | Final Wealth (↑) |
  | --- | --- | --- | --- | --- |
  | CVaR | 0.2165 | 0.2858 | 0.3086 | 1.1170 |
  | EW | 0.6008 | 0.7399 | 0.3604 | 1.6683 |
  | GMV | 0.3947 | 0.4992 | 0.2678 | 1.2845 |
  | HRP | 0.4637 | 0.5620 | 0.3258 | 1.4021 |
  | Autoformer | 0.3899 ± 0.1985 | 0.5321 ± 0.2870 | 0.4356 ± 0.1256 | 1.4697 ± 0.4573 |
  | DLinear | 0.2540 ± 0.1215 | 0.3557 ± 0.1828 | 0.3716 ± 0.0193 | 1.1883 ± 0.1979 |
  | FEDformer | 0.4318 ± 0.0692 | 0.6039 ± 0.1097 | 0.4039 ± 0.1143 | 1.5286 ± 0.1508 |
  | iTransformer | 0.5162 ± 0.1367 | 0.6761 ± 0.1770 | 0.4542 ± 0.0239 | 1.7910 ± 0.3722 |
  | NSformer | 0.5238 ± 0.0694 | 0.7105 ± 0.1033 | 0.4992 ± 0.0975 | 1.8138 ± 0.1922 |
  | PatchTST | 0.3821 ± 0.1871 | 0.5134 ± 0.2635 | 0.4255 ± 0.1533 | 1.4411 ± 0.3814 |
  | TimesNet | 0.3050 ± 0.3439 | 0.4296 ± 0.4864 | 0.5181 ± 0.1404 | 1.3737 ± 0.8857 |
  | RFormer | 0.5315 ± 0.2519 | 0.6671 ± 0.3255 | 0.5202 ± 0.0555 | 1.8014 ± 0.6303 |
  | SIT (Ours) | 0.7715 ± 0.0627 | 0.9743 ± 0.0998 | 0.3271 ± 0.0094 | 1.9215 ± 0.1792 |

- 备注: 原文标注「最优/次优/第三」分别以红/蓝/加粗高亮（本处不复现配色）。
- 关联要素: D1, F5, F7, B6

### [R2] Table 5 · 30 资产 S&P100 绩效（附录）
- 页码: p19
- 原文: > "Portfolio performance of SIT versus baselines across 30-asset universes. ... SIT (Ours) 0.5496 ± 0.0552 | 0.6797 ± 0.0792 | 0.3415 ± 0.0162 | 1.5678 ± 0.0973"
- 数值表（与研报 Table 5 逐格一致）:

  Panel A · Asset 30 Universe (S&P100)

  | Model | Sharpe | Sortino | MDD | Wealth |
  | --- | --- | --- | --- | --- |
  | CVaR | 0.2883 | 0.3707 | 0.3499 | 1.1915 |
  | EW | 0.5268 | 0.6569 | 0.3724 | 1.5648 |
  | GMV | 0.1690 | 0.2177 | 0.2853 | 1.0723 |
  | HRP | 0.4609 | 0.5711 | 0.3287 | 1.4099 |
  | Autoformer | 0.3228 ± 0.0549 | 0.4500 ± 0.0840 | 0.3782 ± 0.0062 | 1.2989 ± 0.1028 |
  | DLinear | 0.3929 ± 0.1294 | 0.5399 ± 0.1758 | 0.3863 ± 0.0266 | 1.4235 ± 0.2587 |
  | FEDformer | 0.1594 ± 0.1323 | 0.2162 ± 0.1790 | 0.4345 ± 0.0319 | 1.032 ± 0.2090 |
  | iTransformer | 0.2948 ± 0.0721 | 0.3853 ± 0.0942 | 0.4169 ± 0.0118 | 1.2447 ± 0.1459 |
  | NSformer | 0.2227 ± 0.1535 | 0.3070 ± 0.2126 | 0.4422 ± 0.0535 | 1.1190 ± 0.2650 |
  | PatchTST | 0.2189 ± 0.1446 | 0.2916 ± 0.1945 | 0.5003 ± 0.0667 | 1.1238 ± 0.2287 |
  | TimesNet | 0.2192 ± 0.1520 | 0.2999 ± 0.2103 | 0.4434 ± 0.0311 | 1.1213 ± 0.2853 |
  | RFormer | 0.4631 ± 0.2771 | 0.5854 ± 0.2094 | 0.4561 ± 0.0501 | 1.5566 ± 0.2038 |
  | SIT (Ours) | 0.5496 ± 0.0552 | 0.6797 ± 0.0792 | 0.3415 ± 0.0162 | 1.5678 ± 0.0973 |

- 备注: FEDformer 的 Wealth 原文即为 "1.032"（非 1.0320），照抄。
- 关联要素: D1, B6

### [R3] Table 6 · 10 与 20 资产 DOW30 绩效（附录）
- 页码: p19
- 原文: > "Portfolio performance of SIT versus baselines across 10 and 20-asset universes from DOW30. ... SIT (Ours) 1.0312 ± 0.0671 | 1.3798 ± 0.1049 | 0.2766 ± 0.0413 | 2.8674 ± 0.2263"（10资产行）
- 数值表（与研报 Table 6 逐格一致）:

  Panel A · Asset 10 Universe (DOW30)

  | Models | Sharpe (↑) | Sortino (↑) | MaxDrawdown (↓) | Final Wealth (↑) |
  | --- | --- | --- | --- | --- |
  | CVaR | 0.4584 | 0.5617 | 0.3053 | 1.4341 |
  | EW | 0.9123 | 1.1714 | 0.3191 | 2.4551 |
  | GMV | 1.0394 | 1.3191 | 0.2467 | 2.3841 |
  | HRP | 0.8407 | 1.0332 | 0.3104 | 2.0583 |
  | Autoformer | 0.6767 ± 0.3150 | 0.9581 ± 0.4848 | 0.4655 ± 0.0265 | 2.2787 ± 1.3004 |
  | DLinear | 0.8223 ± 0.1251 | 0.9789 ± 0.1692 | 0.4240 ± 0.0414 | 2.4523 ± 0.6336 |
  | FEDformer | 0.7664 ± 0.0867 | 0.8245 ± 0.1460 | 0.4948 ± 0.0116 | 2.0578 ± 0.7550 |
  | iTransformer | 0.9458 ± 0.1279 | 1.1248 ± 0.2274 | 0.4230 ± 0.0532 | 2.4016 ± 1.7240 |
  | NSformer | 0.8863 ± 0.2525 | 0.9630 ± 0.4478 | 0.4733 ± 0.0825 | 2.1044 ± 1.1644 |
  | PatchTST | 0.7815 ± 0.1745 | 0.9712 ± 0.2462 | 0.4133 ± 0.0224 | 2.1454 ± 0.8895 |
  | TimesNet | 0.4249 ± 0.2673 | 0.5876 ± 0.3658 | 0.6326 ± 0.0967 | 1.6655 ± 0.6016 |
  | RFormer | 0.8605 ± 0.1936 | 1.1928 ± 0.2708 | 0.3615 ± 0.0407 | 2.1120 ± 0.5219 |
  | SIT (Ours) | 1.0312 ± 0.0671 | 1.3798 ± 0.1049 | 0.2766 ± 0.0413 | 2.8674 ± 0.2263 |

  Panel B · Asset 20 Universe (DOW30)

  | Models | Sharpe (↑) | Sortino (↑) | MaxDrawdown (↓) | Final Wealth (↑) |
  | --- | --- | --- | --- | --- |
  | CVaR | 0.5453 | 0.6871 | 0.3249 | 1.5166 |
  | EW | 0.8603 | 1.0472 | 0.3503 | 2.2293 |
  | GMV | 0.8618 | 1.0730 | 0.2853 | 1.9457 |
  | HRP | 0.7500 | 0.8917 | 0.3253 | 1.8443 |
  | Autoformer | 0.5688 ± 0.2224 | 0.8312 ± 0.3437 | 0.4642 ± 0.0244 | 1.8605 ± 0.9118 |
  | DLinear | 0.7969 ± 0.1057 | 0.9339 ± 0.1475 | 0.3276 ± 0.0415 | 2.1966 ± 0.4046 |
  | FEDformer | 0.3341 ± 0.5907 | 0.5471 ± 0.8805 | 0.4671 ± 0.0763 | 1.8039 ± 1.1031 |
  | iTransformer | 0.4668 ± 0.2290 | 0.6682 ± 0.3666 | 0.6001 ± 0.0208 | 1.8563 ± 0.9329 |
  | NSformer | 0.6541 ± 0.4828 | 0.9751 ± 0.7710 | 0.5620 ± 0.0778 | 2.1464 ± 1.0281 |
  | PatchTST | 0.6828 ± 0.1866 | 0.9499 ± 0.2417 | 0.5109 ± 0.0395 | 2.0649 ± 0.4307 |
  | TimesNet | 0.2381 ± 0.2584 | 0.3428 ± 0.3871 | 0.4919 ± 0.0511 | 1.2356 ± 0.5723 |
  | RFormer | 0.7055 ± 0.1568 | 0.8295 ± 0.1663 | 0.4514 ± 0.1046 | 2.0048 ± 0.6198 |
  | SIT (Ours) | 0.8861 ± 0.1243 | 1.0949 ± 0.1607 | 0.3151 ± 0.0181 | 2.2039 ± 0.2983 |

- 关联要素: D1, B6

### [R4] Table 7 · 50 与 100 资产 CSI300 绩效（附录）
- 页码: p20
- 原文: > "Portfolio performance of SIT versus baselines across ... CSI300. ... SIT (Ours) 1.9373 ± 0.0091 | 2.3399 ± 0.1711 | 0.0964 ± 0.0046 | 1.2804 ± 0.0105"（50资产行）
- 数值表（与研报 Table 7 逐格一致）:

  Panel A · Asset 50 Universe (CSI300)

  | Models | Sharpe (↑) | Sortino (↑) | MaxDrawdown (↓) | Final Wealth (↑) |
  | --- | --- | --- | --- | --- |
  | CVaR | 0.8292 | 1.0038 | 0.1220 | 1.0971 |
  | EW | 1.1695 | 1.3671 | 0.1263 | 1.1413 |
  | GMV | 1.6717 | 2.1255 | 0.0942 | 1.1766 |
  | HRP | 1.7428 | 2.0183 | 0.1136 | 1.1825 |
  | Autoformer | 0.5834 ± 0.4666 | 0.5923 ± 0.5446 | 0.2441 ± 0.0779 | 0.9079 ± 0.1257 |
  | DLinear | 0.5122 ± 0.3699 | 0.6819 ± 0.5769 | 0.2032 ± 0.0664 | 1.1252 ± 0.1615 |
  | FEDformer | 0.3267 ± 0.7165 | 0.4185 ± 0.8655 | 0.2822 ± 0.0371 | 1.0383 ± 0.2970 |
  | iTransformer | 0.6161 ± 0.1936 | 0.8566 ± 0.2296 | 0.2001 ± 0.0234 | 1.0204 ± 0.1806 |
  | NSformer | 0.3010 ± 0.1859 | 0.4132 ± 0.2395 | 0.2889 ± 0.0689 | 1.0775 ± 0.0704 |
  | PatchTST | 0.2789 ± 0.1646 | 0.3368 ± 0.2040 | 0.1913 ± 0.0124 | 1.0394 ± 0.0442 |
  | TimesNet | 0.8213 ± 0.1636 | 1.0533 ± 0.1929 | 0.2855 ± 0.0954 | 1.1700 ± 0.2386 |
  | RFormer | 0.8867 ± 0.2363 | 1.0921 ± 0.2451 | 0.2579 ± 0.0554 | 1.1665 ± 0.1245 |
  | SIT (Ours) | 1.9373 ± 0.0091 | 2.3399 ± 0.1711 | 0.0964 ± 0.0046 | 1.2804 ± 0.0105 |

  Panel B · Asset 100 Universe (CSI300)

  | Models | Sharpe (↑) | Sortino (↑) | MaxDrawdown (↓) | Final Wealth (↑) |
  | --- | --- | --- | --- | --- |
  | CVaR | 1.5199 | 2.0863 | 0.1155 | 1.2905 |
  | EW | 1.1179 | 1.2660 | 0.1302 | 1.1252 |
  | GMV | 1.5365 | 2.0612 | 0.1175 | 1.2724 |
  | HRP | 1.2424 | 1.6540 | 0.1229 | 1.2097 |
  | Autoformer | 0.5681 ± 0.3129 | 0.6014 ± 0.4024 | 0.2529 ± 0.0206 | 0.9725 ± 0.1396 |
  | DLinear | 0.7382 ± 0.4826 | 0.8309 ± 0.4303 | 0.2314 ± 0.0778 | 1.0934 ± 0.3219 |
  | FEDformer | 0.4269 ± 0.4916 | 0.5356 ± 0.6167 | 0.2831 ± 0.0344 | 1.0846 ± 0.1694 |
  | iTransformer | 0.9865 ± 0.2055 | 1.2495 ± 0.2386 | 0.2492 ± 0.0741 | 1.1169 ± 0.3491 |
  | NSformer | 0.5470 ± 0.3975 | 0.7586 ± 0.5326 | 0.2175 ± 0.0851 | 1.1560 ± 0.1387 |
  | PatchTST | 0.4650 ± 0.1313 | 0.5551 ± 0.1793 | 0.2547 ± 0.5590 | 1.0809 ± 0.1104 |
  | TimesNet | 0.7353 ± 0.1357 | 1.0598 ± 0.1992 | 0.2997 ± 0.0940 | 1.1610 ± 0.2039 |
  | RFormer | 1.0267 ± 0.2152 | 1.2359 ± 0.2599 | 0.2111 ± 0.0732 | 1.2321 ± 0.1094 |
  | SIT (Ours) | 1.8772 ± 0.0918 | 2.3637 ± 0.0936 | 0.1199 ± 0.0048 | 1.2777 ± 0.0214 |

- 备注: Table 7 题注原文误写为「across 10 and 20-asset universes from CSI300」，但两 Panel 标题分别为 50 与 100 资产（CSI300），题注与 Panel 标题不一致，照原文登记（见歧义 A8）。
- 关联要素: D1, B6

## 六、图表登记清单（FIG/TBL 全集）

| ID | 标题 | 页码 | 摘要 | 复现意图 | 理由/关联要素 |
| --- | --- | --- | --- | --- | --- |
| FIG1 | 有缺陷的资产配置策略示意（two-stage pipeline 三问题） | p1 | 概念图：缺金融归纳偏置/目标错配/误差放大 | reference_only | 概念示意图，无可验证数值；含 TSLA/NVDA/AAPL 示意标签 |
| FIG2 | SIT 架构总览图 | p3 | 签名提取→SIT Block(时间注意力/签名注意力/FFN)→分配头→CVaR | reference_only | 架构示意图，无数值 |
| FIG3 | 签名强度与注意力权重相关性分布 | p7 | 右偏分布，均值 0.540(40资产)/0.611(50资产) | reproduce | 关联 SA2 |
| FIG4 | CVaR 优化后样本外 Sharpe（DFL vs MSE） | p7 | 40/50 资产上 DFL(蓝) 一致优于 prediction-only(灰) | reproduce | 关联 B5；Fig4=各预测 backbone 的 DFL vs MSE/PFL 柱对，柱值原文仅图形呈现、文本层未给，非 Table1 数值 |
| FIG5 | Sharpe 对交易成本与配置集中度 τ 的敏感性热图 | p8 | 40/50 资产 (τ,c) 网格均值±std Sharpe | reproduce | 关联 SA3 |
| FIG6 | 温度 τ 对组合多样化(HHI/熵)的影响 | p8 | τ 增大 HHI 降、Shannon 熵升 | reproduce | 关联 SA4 |
| FIG7 | 动态 gate γ 与组合回撤关系（2020-2024） | p21 | 40/50 资产回撤曲线，颜色编码 γ 幅度 | reference_only | 可视化诊断图，无数值表 |
| TBL1 | Table1 40&50 资产 S&P100 绩效 | p5 | 见 R1 | reproduce | 关联 R1 |
| TBL2 | Table2 SIT 核心组件消融 | p6 | 见 SA1 | reproduce | 关联 SA1 |
| TBL3 | Table3 全文符号汇总表 | p13 | 符号/描述/维度对照 | reference_only | 记号表，无结果数值 |
| TBL4 | Table4 各模型超参搜索空间 | p16 | Panel A-E 各模型网格 | reference_only | 配置表，关联 B2 |
| TBL5 | Table5 30 资产 S&P100 绩效 | p19 | 见 R2 | reproduce | 关联 R2 |
| TBL6 | Table6 10&20 资产 DOW30 绩效 | p19 | 见 R3 | reproduce | 关联 R3 |
| TBL7 | Table7 50&100 资产 CSI300 绩效 | p20 | 见 R4 | reproduce | 关联 R4 |

## 七、敏感性/稳健性分析（SA 类）

### [SA1] Table 2 · 模块消融（module-drop 贡献分析）
- 页码: p6
- 原文: > "Ablation study of SIT's core components. Superscripts b and c indicate statistical significance at p < 0.05 and p < 0.001 in paired tests against SIT (Ours)."
- 测试设计: 逐一移除单个组件、其余超参不变——(i) w/o CVaR（换为风险中性最大化均值收益）；(ii) w/o Asset Attn（禁用整个签名增强资产注意力）；(iii) w/o Financial Bias（去掉签名偏置项，退回标准注意力）；(iv) w/o Gate γ（去掉可学习 gate γ）。
- 数值表（与研报 Table 2 逐格一致；上标 b=p<0.05、c=p<0.001，对 SIT 的配对检验显著性，无上标即未标注）:

  Panel A · Asset 40 Universe

  | Models | Sharpe | Sortino | MDD | Wealth |
  | --- | --- | --- | --- | --- |
  | SIT (Ours) | 0.6717 | 0.8232 | 0.3611 | 1.7903 |
  | w/o CVaR | 0.5691c | 0.7057b | 0.3695 | 1.6409b |
  | w/o Asset Attn | 0.5284c | 0.6576c | 0.3342b | 1.5381c |
  | w/o Financial Bias | 0.6045b | 0.7590b | 0.3431c | 1.6801c |
  | w/o Gate γ | 0.5251 | 0.6489c | 0.3470b | 1.5470c |

  Panel B · Asset 50 Universe

  | Models | Sharpe | Sortino | MDD | Wealth |
  | --- | --- | --- | --- | --- |
  | SIT (Ours) | 0.7715 | 0.9743 | 0.3271 | 1.9215 |
  | w/o CVaR | 0.5923c | 0.7294c | 0.3606b | 1.6622c |
  | w/o Asset Attn | 0.6268c | 0.7650b | 0.3298 | 1.6562b |
  | w/o Financial Bias | 0.6047c | 0.7545b | 0.3224 | 1.6260b |
  | w/o Gate γ | 0.5831c | 0.7138c | 0.3305 | 1.5945c |

- 结论: > "The most critical element is the decision-focused approach ... (w/o CVaR) the Sharpe Ratio on the 40-asset universe falls from 0.6717 to 0.5691." 移除各组件均导致显著退化。
- 关联要素: F5, F7

### [SA2] Figure 3 · 签名强度与注意力权重相关性分布
- 页码: p7
- 原文: > "a per-asset signature-strength score s_t,j = 1/(HN_H d) Σ_{k=1}^H Σ_{h=1}^{NH} Σ_{m=1}^d (B_k,h)_{m,j} and the corresponding inbound-attention share a_t,j = 1/(HN_H d) Σ_{k=1}^H Σ_{h=1}^{NH} Σ_{m=1}^d α_{k,h,m→j}. We then compute the Pearson correlation between {s_t,j} and {a_t,j} at each t ... the distribution is right-skewed with means of 0.540 for the 40-asset universe and 0.611 for the 50-asset universe"
- 测试设计（含复现 Figure 3 所需两定义式）: 在每决策时刻 t，逐资产 j 计算——(i) 签名强度 s_t,j = [1/(H·N_H·d)]·Σ_{k=1}^H Σ_{h=1}^{N_H} Σ_{m=1}^d (B_{k,h})_{m,j}（对签名偏置矩阵 B 沿切片 k、头 h、来源资产 m 求和后归一）；(ii) 入向注意力份额 a_t,j = [1/(H·N_H·d)]·Σ_{k=1}^H Σ_{h=1}^{N_H} Σ_{m=1}^d α_{k,h,m→j}（对指向资产 j 的注意力权重同样求和归一）。对 {s_t,j}_{j=1}^d 与 {a_t,j}_{j=1}^d 在每个 t 求横截面 Pearson 相关，考察相关系数在测试期的分布。
- 数值: 相关系数均值 40资产=0.540、50资产=0.611；分布右偏、右尾厚、负相关稀少（印证 Theorem 2.2 单调性）。
- 关联要素: F5

### [SA3] Figure 5 · 交易成本与配置集中度 τ 敏感性
- 页码: p8
- 原文: > "performance peaks at moderate dispersion, near τ ≈ 1.3. Second, frictions compress Sharpe roughly linearly ... moving from 0 to 10 bps reduces Sharpe by about 0.03–0.04 at the optimum."
- 测试设计: sweep τ∈{0.8,...,1.4} × 单边成本 c∈{0,5,10} bps；其余同主评估（long-only、fully-invested、月度调仓、40/50 资产、零无风险利率）；报告每 (τ,c) 对的均值±std Sharpe。
- 数值/结论: 峰值近 τ≈1.3；0→10 bps 使最优点 Sharpe 降约 0.03–0.04；40资产最优点降 0.034、τ∈{0.8,0.9} 降 0.039–0.041；50资产最小惩罚在 τ=0.9 降 0.027。Figure 5 热图全部 42 格 (τ,c) mean±std 在 report_text.md p8 可得（3 档成本 c∈{0,5,10}bps × 7 档 τ × 40/50 两 Panel；此处不逐格转录）；实验模式敏感性将在 A股自算 τ×c 网格、原文值作参考（见歧义 A10）。
- 关联要素: F6, B4

### [SA4] Figure 6 · 温度 τ 对组合多样化的影响
- 页码: p8
- 原文: > "increasing the softmax temperature τ monotonically reduces cross-sectional concentration and increases diversification. Herfindahl–Hirschman Index HHI(w)=Σ_j w_j^2 declines, while Shannon entropy H(w)=−Σ_j w_j log w_j rises."
- 测试设计: 变动 τ，观察集中度指标 HHI 与 Shannon 熵；任意固定 τ 下 50 资产比 40 资产 HHI 更低、熵更高。Figure 6 可见 τ 轴范围 {0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00}（p8，与 Fig5 敏感性所用 τ∈{0.8,…,1.4} 网格不同）。
- 数值: 定性单调关系（τ↑ ⇒ HHI↓、熵↑）；提供通过 τ 对集中度的一一可控。
- 关联要素: F6

## 八、提取自检声明

- [x] 逐页扫描确认：report_text.md 全部 `===== PAGE 1..21 =====` 已逐页过目，无整页跳过（p9-p10 为参考文献、p14-p15 为纯数学证明，已在页面覆盖表标注类型）。
- [x] 图表编号全登记：正文出现的 Figure 1-7、Table 1-7 已在第六节全集登记（含 reference_only 项）；无缺号。
- [x] 摘要/结论提及的数值均可在正文定位：正文 3.2（p6）提及 SIT Sharpe 0.6717/0.8232、GMV MDD 0.2743/Sharpe 0.4148 等均定位于 R1(Table1)；消融 0.6717→0.5691 定位于 SA1(Table2)；Figure3 均值 0.540/0.611 定位于 SA2。摘要（p1）与结论（p8）为定性表述、无独立数值。
- 无法提取内容清单：
  1. CVaR 置信水平 α 的实验取值——原文正文与全部附录均未给出具体数值（登记为歧义 A1，F7/B7 参数标 n/a）。
  2. 回看窗口 H 与预测窗口 K 的数值——正文与 Table 4 搜索空间均未列出（歧义 A2，B8 标 n/a）。
  3. 各 universe 具体成分股名单与从指数挑选子集的规则——未列出（歧义 A3）。
  4. Figure 5 交易成本×τ 敏感性热图的逐格数值（全 42 格 mean±std）——在 report_text.md p8 可得，本 spec 按实验模式（A股迁移、数值对齐豁免）不逐格转录、留作参考，正文已登记汇总数值峰值 τ≈1.3、0→10bps 降 0.03-0.04（歧义 A10）。
  5. Figure 1（p1）、Figure 2（p3）、Figure 7（p21）为示意/架构/诊断图，PDF 文本层未含可解析数值，按 reference_only 登记。
