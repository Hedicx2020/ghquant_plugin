---
report_name: r001_signature_transformer_allocation
title: Signature-Informed Transformer for Asset Allocation
institution: Pusan National University; University of Oxford
date: 2026-01-23
type: allocation
tags: [ml]
difficulty: hard
feasibility: degraded
template: templates/allocation.md
spec_ref: workspace/r001_signature_transformer_allocation/spec/spec.md
reproduction_mode: experimental
data_requirements:
  - name: A股前复权日频行情（收益序列母源）
    source: ashare_stock_price_forward.parquet
    status: substitute        # 原文 WRDS 美股日频价格 → 本地 A股前复权日频（市场迁移，登记 AS11）
  - name: CSI300 指数成分（对齐锚母池 + 迁移母池）
    source: ashare_index_components.parquet (index_code=000300)
    status: available         # R4/Table7 锚在本地可得；美股 universe 亦迁移取此母池子集
  - name: 市值（选样排序依据）
    source: ashare_stock_trade.parquet (market_value / negotiable_market_value)
    status: available
  - name: 月末调仓交易日历
    source: ashare_tradeday.parquet (IfMonthEnd / IfTradingDay)
    status: available
  - name: ST / 停牌过滤（防不可交易样本）
    source: ashare_stock_st.parquet / ashare_stock_suspend.parquet
    status: available
  - name: 日历特征向量 v_t（F 维）
    source: 由 date 衍生（sin/cos 周期编码）
    status: derive            # 内容/维度原文未明，按惯例衍生（AS4）
  - name: 路径签名 / 成对交叉签名（M=2）
    source: 由行情衍生，须自实现（本地无 signatory/iisignature/esig）
    status: derive            # M=2 解析可算，自实现（AS17）
  - name: 美股指数成分名单（S&P100 / DOW30 成员）
    source: 原文 S&P100/DOW30 成分 → 本地 CSI300 top-N（本地 usshare_stock_quote 有价无 index 成分表，原文亦未披露名单）
    status: substitute        # 原文不可得项迁移替代（AS12）；本地无美股成分、原文未披露 → CSI300 子集
milestones:
  - id: m1
    name: 数据层与 A股迁移 universe 构建
    desc: 构建 CSI300 迁移 universe（主 50 资产 + 缩减小规模），加载前复权日行情、日收益、月末调仓日历、ST/停牌点时过滤、日历特征 v_t；固定 train/val/test 时间划分（迁移到 A股可得区间）；防未来函数点时选样。
    deps: []
    elements: [D1, D2, D3]
  - id: m2
    name: 路径签名与交叉签名特征工程（F_ti 组装）
    desc: 自实现 M=2 截断路径签名（逐资产 H 切片、Chen relation 增量）、成对交叉签名 signed-area lead-lag（Eq.21）、日历特征拼接，组装决策时刻信息集 F_ti；固定 H=60 回看窗口与 K=12 多步决策窗口（K>1 保 CVaR 多期尾部非退化，AS2）。
    deps: [m1]
    elements: [D4, F1, F2, B8]
  - id: m3
    name: SIT 模型架构与前向
    desc: 签名嵌入 token（三嵌入融合 Eq.4）、时间维因果自注意力、签名增强资产维自注意力（β/qdyn/gate γ，Eq.8-16）、多步输出头产 K=12 步 µ̂∈R^(K×d) 后 softmax 分配头（τ、long-only、fully-invested）；前向产出各步合法权重（非负、和为 1）。
    deps: [m2]
    elements: [F3, F4, F5, F6]
  - id: m4
    name: CVaR 端到端训练、基线与主绩效表
    desc: CVaR 训练目标（α=0.80 对 K=12 步损失序列取尾、(1−α)K=2.4 非退化，Eq.17）+ Adam/early-stopping 训练 + 缩减网格搜索选优 + 端到端范式（µ̂ 仅作 logits）；传统基线 EW/GMV/CVaR/HRP（复用 common/allocation_backtest 待审）+ 缩减 1 个预测类两阶段基线（DLinear）；组合回测（月度 K-step 调仓、0bps）、四项指标；产出 CSI300 50 资产主绩效表（R4 锚）与缩减规模迁移表。
    deps: [m3]
    elements: [F7, F8, B1, B2, B3, B5, B6, B7, R1, R2, R3, R4]
  - id: m5
    name: 消融与敏感性分析
    desc: 模块消融（w/o CVaR / w/o Asset Attn / w/o Financial Bias / w/o Gate γ，Table2）、签名强度-注意力相关分布（Fig3）、τ×交易成本敏感性热图（Fig5，c∈{0,5,10}bps）、τ 多样化 HHI/熵（Fig6）。
    deps: [m4]
    elements: [SA1, SA2, SA3, SA4, B4]
---

# Signature-Informed Transformer for Asset Allocation 复现开发计划

## 研报信息
- 标题：Signature-Informed Transformer for Asset Allocation（SIT）
- 来源机构：Pusan National University；University of Oxford
- 发布日期：2026-01-23
- 作者：Yoontae Hwang、Stefan Zohren
- 适用市场：原文美股（S&P100 / DOW30）为主 + 中国 CSI300 稳健性实验；**本复现在实验模式下整体迁移至 A股（CSI300 为核心）**
- 论文性质：方法论论文（端到端深度学习资产配置模型 + 实证），非机构卖方研报

> 本文只回答「按什么顺序复现」，研报要素权威来源为 `spec/spec.md`；R 类基准数值一律引用 spec，不在此重复抄录。

---

## 〇、数据映射与市场迁移裁决（本案核心决策）

本案 `reproduction_mode=experimental`：原文主力市场（美股）本地无法忠实重建，复现目标是**「SIT 方法在 A股是否成立」**（非数值对齐原文，数值判定后续豁免）。数据映射的关键在于处理「CSI300 锚」与「美股 universe 迁移」的关系。

### 0.1 为何美股 universe 无法忠实复现（missing 判据）
- 原文 universe（D1）为 S&P100 取 30/40/50 只、DOW30 取 10/20 只——**依赖 S&P100 / DOW30 的指数成分名单**。
- 本地 `usshare_stock_quote.parquet` 有美股个股行情（有价），但 `data_catalog` 中**无美股指数成分表**（无 S&P100 / DOW30 历史成员进出），且原文**未披露具体成分名单与选样规则**（歧义 A3）。
- 结论：即便有美股价格，也无法确定「哪 40/50 只」，无法忠实重建原文 universe → 美股 universe 原文不可得，在实验模式下标 `substitute` 迁移替代至 CSI300（非 `missing` 阻断，因 experimental 授权替代且 CSI300 母池本地可得）。

### 0.2 三问裁决（对应派发指令 a/b/c）
- **(a) CSI300（R4/Table7）作为直接对齐锚——采纳。** 原文 Table 7 已在 CSI300（50/100 资产）给出 SIT 与全基线的 Sharpe/Sortino/MDD/Wealth 数值（spec R4），而 CSI300 成分（`ashare_index_components` index_code=000300）与 A股行情本地**可得**。因此本案不是「无锚移植」：CSI300 50 资产设为**主复现 universe**，可与 R4 Panel A 做**趋同比较**（convergence，非严格逐点，受缩减规模 + 数值豁免约束）。这是本案最强的数据机会，必须用足。
- **(b) 美股 universe 迁移映射。** S&P100 / DOW30 均为大盘蓝筹指数；A股大盘蓝筹等价母池即 CSI300。迁移规则：以 CSI300 成分为母池，按市值降序取 top-N（N∈{50,40,30,20,10}），点时快照 + 过滤 ST/停牌/历史不足者。即「美股大盘 top-N」→「CSI300 top-N」。这些为**纯迁移 universe**（无原文对应数值锚）。
- **(c) 两者关系与最终 universe 取舍。** 40/50 资产的「大盘」尺度本身已由 CSI300（A股大盘指数）最佳表征，故 S&P100 40/50（R1）迁移后与 CSI300 50/40（R4/CSI300 top-40）**归并同一族**，不另设独立「S&P100 迁移池」。DOW30 10/20（R3，更集中的巨头）迁移为 CSI300 top-10/20，作小规模跨尺度稳健性检验。最终执行取舍（受算力约束，详见第七节）：
  - **必跑**：CSI300 50 资产（R4-A 锚）。
  - **算力允许则跑**：CSI300 100 资产（R4-B 锚）或 CSI300 20 资产（R3 尺度跨规模）择一。
  - **可选**：CSI300 40/30/10（R1/R2/R3 尺度），单配置、算力充裕再补。

### 0.3 迁移替代登记表（逐条对应 assumptions market-transplant）
| 原文项 | 本地等价替代 | 状态 | 假设 |
|--------|-------------|------|------|
| WRDS 美股日频价格（D2） | A股前复权日频 `ashare_stock_price_forward` | substitute | AS11 |
| S&P100/DOW30 成分名单（D1/A3） | CSI300 成分 top-N（市值排序，点时快照） | substitute | AS12 / AS3 |
| 训练 2000-2016（D3） | 迁移为 2007-2016（CSI300 成分史起点约束） | substitute | AS13 |
| 7 组 universe（D1） | 主 CSI300-50 + 缩减子集（算力） | substitute | AS16 |

> 说明：R4（CSI300）本身是 A股市场，严格意义**非替代**——它是原文直接给出的 A股实验，本地可得，作为**锚**使用；替代关系仅存在于「美股 → A股」的迁移链（D2/D1/D3）。

---

## 一、核心策略与创新点

### 1.1 研究背景与核心思想
SIT 是端到端「决策聚焦学习（DFL）」资产配置模型：用**路径签名**编码资产内在几何与资产间 lead-lag 关系，注入 Transformer 的资产维注意力，直接以**组合级 CVaR**（非逐点预测损失）端到端训练，输出 long-only、fully-invested 权重。对比范式是「先预测后优化（PFL）」两阶段，SIT 主张两阶段的目标错配与误差放大是绩效瓶颈（spec F8、FIG1）。

### 1.2 策略构造（关键公式，详见 spec F1-F8）
1. **路径签名（F1）**：对资产价格路径取 M=2 截断签名 `SigM(X)=(1,∫dX,∫∫dX⊗dX)`；一阶=净增量，二阶=signed area。Chen relation 增量更新避免全历史重算。
2. **成对交叉签名（F2）**：`A(X^i,X^j)=∫X^i dX^j − ∫X^j dX^i`（Eq.21），二阶交叉项编码 signed area 与 lead-lag（Proposition 2.1：严格 lead-lag ⇒ A>0）。
3. **签名嵌入 token（F3, Eq.4）**：`x_k,j = Wproj[e_sig ⊕ e_date ⊕ e_asset]`，三嵌入融合，输入张量 H×d×dmodel。
4. **factorized 注意力（F4/F5）**：时间维标准因果自注意力 + 资产维签名增强注意力 `Head=softmax(QK^T/√dk + γ·B)V`（Eq.11/14），偏置 `b=⟨qdyn, β⟩`，`β=MLPβ(c)`、`qdyn=MLPq(x')`，gate `γ=softplus(γ̂)>0`（Theorem 2.2：γ>0 ⇒ α 对 β 方向导数严格为正）。
5. **分配头（F6）**：多步输出头产 **K=12 步预期收益 µ̂^(1:K)∈R^(K×d)**，每步 `w^(k)=softmax(µ̂^(k)/τ)`，天然 long-only + fully-invested；τ 为集中度温度。
6. **CVaR 目标（F7, Eq.17）**：`min_θ E[CVaRα({−(w^(k))^T r_{ti+k}}_k=1^K)]`，对 K 步损失序列逐场景取经验 α-分位（**α=0.80、K=12，(1−α)K=2.4** 保尾部非退化），无辅助预测损失（F8）。

### 1.3 创新点
- 用路径签名（几何 + signed-area lead-lag）替代/增强标准注意力的金融归纳偏置（对比 PFL 的无结构预测）。
- 端到端组合级 CVaR 训练（DFL），µ̂ 仅作可微分配层 logits，避免预测-优化目标错配。
- 可学习正 gate γ 提供签名偏置强度的可解释、单调可控通道。

---

## 二、回测参数（复现对齐用）

> 类型特化参数清单参见 `templates/allocation.md` 与 `templates/ml.md`；数值细节见 spec B1-B8。

- **回测/评估区间**：test 2020-01-01 ~ 2024-12-27（与原文对齐，A股可得）；train 2007-01-01~2016-12-31、val 2017-01-01~2019-12-31（train 起点因 CSI300 成分史迁移，AS13）。**固定划分、非滚动、按时间不重叠。**
- **标的池 / 基准**：CSI300 top-50（主）；基准对比 EW/GMV/CVaR/HRP（common/allocation_backtest 待审复用）。
- **调仓频率**：月度（k-step，B3）；long-only、fully-invested；风险调整指标零无风险利率。
- **交易成本**：主绩效表 0 bps（AS9）；敏感性 sweep c∈{0,5,10}bps（B4，SA3）。
- **训练超参（B1）**：Adam、lr=1e-3、batch=64、dropout=0.1、max epoch=100、early stopping patience=10；验证集选优。
- **超参搜索（B2，缩减，AS14）**：原文 d_model{8,16,32,64}×d_ff{8,16,32,64}×layers{1,2}×heads{2,4,8}×hidden_c{8,16,32}=288 组 → 缩减为主 universe ≤8 组、次 universe 单配置。
- **窗口（B8，AS2）**：H=60 交易日回看（60 时间 token，Chen 增量）、**K=12 月度步（多步前瞻，非单步；与 α 耦合防 CVaR 退化）**、交叉签名取全窗口。
- **CVaR α（F7，AS1）**：**α=0.80**，与 K=12 耦合 (1−α)·K=2.4（≥2，尾部平均有意义、SA1 消融方向性可验证；α-K 耦合防退化详见 AS1/AS2）。
- **随机种子（AS5）**：3 个种子，报告 mean±std（缩减）。

---

## 三、难度判定（依 _plan_template §三 三步）
1. **方法复杂度基准**：端到端深度网络训练 + CVaR 优化求解 + 多资产联动 → **hard 基准**（三项均落 hard 维度，含模型训练自动 ≥medium 已被 hard 覆盖）。
2. **修正项**：数据可得性——复现主线需市场迁移 + 路径签名/交叉签名自实现（无签名库）——本应上调一档，但基准已 hard，**封顶 hard**；模块数≥8 但基准非 medium，规则不触发额外上调。
3. **easy 收口**：远不满足（多模块 + 训练模型 + 迁移数据）。
- **结论：difficulty = hard**（≥3 milestone 硬下限，本案 5 个）。

---

## 四、feasibility 判定 = degraded（非 blocked）
- **核心数据经迁移后 available/derive**：A股行情、CSI300 成分、市值、日历、ST/停牌全部本地可得；签名/日历特征可衍生。**无阻断性缺口。**
- **未触发 blocked**：`reproduction_mode` 已由主会话置 experimental（授权替代规划），故市场迁移不置 blocked；全部歧义（A1-A10）均可按惯例 auto 裁决，无 blocking 级、无核心方法不可确定项。
- **判 degraded 而非 feasible 的理由**：复现在三重降级下进行——(i) 市场迁移（美股→A股，数值豁免、仅 CSI300 有软锚）；(ii) 算力缩减（网格 288→≤8、深度基线 8→1、universe 7 组→1-3 组、种子未知→3）；(iii) 签名/若干结构按惯例衍生。方法可跑通并产出结论，但保真度低于原文全量复现 → **degraded**。
- **不触发人工闸门**（feasibility≠blocked 且无 blocking 歧义），按 auto 模式推进。

---

## 五、研报核心结果（验证基准，数值见 spec R 类）
> 实验模式数值豁免：R1/R2/R3 为纯迁移（无锚，仅方向/机制对比）；R4 为 CSI300 软锚（趋同比较）。

| R 要素ID | 一句话摘要 | 关联 milestone | 复现定位 |
|----------|-----------|---------------|---------|
| R1 | Table1 40&50 资产 S&P100 主结果 | m4 | 迁移 CSI300 40/50（与 R4 归并，数值豁免） |
| R2 | Table5 30 资产 S&P100 | m4 | 迁移 CSI300-30（可选，数值豁免） |
| R3 | Table6 10&20 资产 DOW30 | m4 | 迁移 CSI300-10/20（跨规模，数值豁免） |
| R4 | Table7 50&100 资产 CSI300 | m4 | **主锚**，CSI300-50 趋同比较；100 可选 |

核心可复现结论目标（机制层，非逐点）：
1. SIT 在 A股 CSI300 上是否**优于传统基线**（EW/GMV/CVaR/HRP）——最直接的「方法成立」判据。
2. 消融（SA1）：移除 CVaR / 资产注意力 / 签名偏置 / gate γ 是否各自导致显著退化——验证各组件贡献。
3. 签名强度-注意力正相关（SA2）、τ 单调调控多样化（SA4）——验证机制。

---

## 六、复现计划（milestone 详述）

### m1: 数据层与 A股迁移 universe 构建（deps: []）
- **实现内容**：
  - universe：`load_index_components`/`get_index_members_on_date`(000300) 取 CSI300 成分，按市值（`ashare_stock_trade.market_value`）降序取 top-N（主 N=50）；**点时快照于各调仓日**（或固定 test 起点，AS3 记方案），过滤 ST（`ashare_stock_st`）、停牌（`ashare_stock_suspend`）、历史不足者。
  - 行情：`ashare_stock_price_forward` 前复权，日收益 = close/prev_close−1（或 `change_pct`）。
  - 调仓日历：`ashare_tradeday` 月末交易日（`get_month_end_trading_days`）。
  - 日历特征 v_t（F=8）：sin/cos(周内位/月/月内日/年内位)（AS4）。
  - 时间划分：train 2007-2016 / val 2017-2019 / test 2020-2024，固定、不重叠（AS13）。
- **依赖数据**：ashare_stock_price_forward / ashare_stock_trade / ashare_index_components / ashare_tradeday / ashare_stock_st / ashare_stock_suspend（均 available，行情 substitute）。
- **复用**：common/data_loader 全套；不在 src/ 重复实现。
- **产出**：`output/.../data_panel`（收益矩阵、universe 成员、调仓日、日历特征）。
- **验证点（含 ML 红线）**：① universe 成员点时正确、无退市/ST 混入；② 收益矩阵无缺失/未来数据；③ train/val/test 时间不重叠、无泄漏；④ 月末调仓日对齐交易日历。

### m2: 路径签名与交叉签名特征工程（deps: [m1]）
- **实现内容**：
  - M=2 截断签名（F1）：**自实现**（无 signatory/iisignature/esig，AS17），逐资产对价格（+时间增广）路径按 H=60 切片计算 level-1（增量）+ level-2（迭代积分）；Chen relation 增量更新（AS2）。
  - 成对交叉签名（F2）：全窗口每资产对 `A=∫X^i dX^j−∫X^j dX^i`（signed area），d_cross-sig=2（两个二阶交叉积分，AS7）。
  - F_ti 组装（D4）：(i) H 个逐资产签名 token +(ii) 资产对交叉签名 +(iii) H 个日历向量。
  - 窗口固定 H=60、K=12（B8，AS2；K>1 多步前瞻保 CVaR 多期尾部非退化，训练场景尾部截断 K 个决策点）。
- **依赖数据**：m1 收益/价格面板。
- **产出**：`output/.../features`（签名张量、交叉签名张量、日历张量），供 m3 定维。
- **验证点**：① signed-area 对合成 lead-lag 路径符号正确（Proposition 2.1 自检）；② 签名只用 [t−H,t] 历史、无前视；③ 维度与 m3 输入契约一致。

### m3: SIT 模型架构与前向（deps: [m2]）
- **实现内容**（torch，src/{id}/strategy.py + model）：
  - 签名嵌入 token（F3, Eq.4）三嵌入融合 + 线性投影。
  - 时间维因果自注意力（F4），资产维把时间当 batch。
  - 签名增强资产注意力（F5）：`softmax(QK^T/√dk + γ·B)V`；β=MLPβ(c)、qdyn=MLPq(x')、MLPβ/MLPq=2 层 MLP+GELU、hidden=HIDDEN C（AS7）；γ=softplus(γ̂)。
  - 多步输出头（F6）：last-slice → 线性投影产 K=12 步 µ̂^(1:K)∈R^(K×d) → 各步 `w^(k)=softmax(µ̂^(k)/τ)`，long-only + fully-invested（AS6）。
- **依赖数据**：m2 特征维度。
- **产出**：可配置 SIT 模型（d_model/d_ff/layers/heads/hidden_c 参数化，供 m4 搜索）。
- **验证点**：① 前向输出权重非负且逐步和为 1；② 因果注意力不看未来 token；③ γ>0 恒成立；④ 梯度可回流（端到端可训练）。

### m4: CVaR 端到端训练、基线与主绩效表（deps: [m3]）
- **实现内容**：
  - CVaR 目标（F7, Eq.17）torch 实现：逐场景对 K=12 步损失序列 {−(w^(k))^T r_{ti+k}} 取经验 α-分位后算 CVaR（尾部均值），α=0.80、(1−α)K=2.4 保证尾部含 ~2.4 个损失点非退化（AS1/AS2）。
  - 训练（B1）：Adam lr=1e-3、batch=64、dropout=0.1、max 100 epoch、early stop patience=10；**超参/τ 仅在 val 选优、test 封存**（ML 红线）。
  - 缩减网格（B2, AS14）：主 universe ≤8 组，次 universe 单配置。
  - 端到端范式（F8）：唯一训练信号为 CVaR，µ̂ 不带预测损失。
  - 基线（B5）：EW/GMV/CVaR/HRP——EW/GMV/HRP 复用 common/allocation_backtest（`equal_weights`/`_min_variance_weights`/`hrp_weights`，**待审复用**）；CVaR 传统基线需新增（scipy linprog，Rockafellar-Uryasev）。缩减 1 个预测类两阶段基线 DLinear（B7, AS15）。
  - 回测（B3/B6）：月度 K-step 调仓（B3；K=12 步前瞻权重序列用于 CVaR 训练取尾，回测按月度滚动结算实现收益）、0bps（AS9），`portfolio_backtest`（待审）出 nav/turnover；四指标 Sharpe/Sortino/MaxDD/Wealth（common/utils）。
  - universe 尺度（R1-R4）：必跑 CSI300-50（R4-A 锚）；算力允许补 100 或 20；数值豁免。
- **依赖数据**：m3 模型、m1/m2 面板与特征。
- **产出**：`backtest_summary.xlsx`（SIT vs 基线 vs R4 锚偏差）、主绩效表、nav 曲线。
- **验证点**：① 权重每期 long-only/fully-invested；② 信号 T 算 T+1 执行；③ test 未参与选优；④ 传统基线复用件经 code_audit 核忠实性。

### m5: 消融与敏感性分析（deps: [m4]）
- **实现内容**：
  - 模块消融（SA1, Table2）：w/o CVaR（换风险中性均值最大化——K=12 下 CVaR 尾部 (1−α)K=2.4 与均值目标有实质差异，消融方向性方成立，AS1/AS2）/ w/o Asset Attn / w/o Financial Bias / w/o Gate γ，各在主 universe 复训；配对显著性（b:p<0.05, c:p<0.001）。
  - 签名强度-注意力相关（SA2, Fig3）：逐时刻 s_t,j 与入向注意力份额 a_t,j 的 Pearson，测试期分布（预期右偏、均值 >0）。
  - τ×成本敏感性（SA3, Fig5）：sweep τ∈{0.8,1.0,1.2,1.3,1.4}×c∈{0,5,10}bps，出均值±std Sharpe 热图（**自生成，不对齐原文逐格**，AS10）。
  - τ 多样化（SA4, Fig6）：τ 变动下 HHI=Σw²（`frobenius_diversification` 或直接算）与 Shannon 熵单调关系。
- **依赖数据**：m4 训练管线。
- **产出**：消融表、Fig3/5/6 图。
- **验证点**：① 消融仅改单组件、其余超参不变；② 敏感性 sweep 复用主评估设定；③ 结论为方向/单调性（数值豁免）。

---

## 七、算力缩减登记（宁可缩小跑通，逐条如实标注）
本文为 CPU 环境深度学习论文，全量方案不可完成，缩减如下（逐条 → assumptions）：

| 维度 | 原文规模 | 缩减方案 | 影响 | 假设 |
|------|---------|---------|------|------|
| universe 组数 | 7 组（30/40/50 S&P + 10/20 DOW + 50/100 CSI） | 主 CSI300-50，次 100/20 择一 | 少数跨市场/跨尺度点缺失；主结论（方法是否成立）不受损 | AS16 |
| 网格搜索 | 288 组 × 多种子 | 主 ≤8 组，次单配置 | 可能未命中原文最优配置 → 加剧数值偏离（已豁免）；不改方法方向 | AS14 |
| 预测类基线 | 8 个（Autoformer…RFormer） | 保留 4 传统 + 1 DLinear | FIG4「DFL vs 8 基线」退化为 1 基线对照；SIT-vs-传统主对比完整 | AS15 |
| 随机种子 | 未披露（表带±std） | 固定 3 种子 | ±std 复现口径不同；均值方向不受影响 | AS5 |
| 训练样本频率 | 未明 | 月度决策点采样（K=12 尾部截断 ~12 点后 ~108 样本），必要时提采样频/兜底降 K=6 | 样本量偏小可能欠拟合；缩训练时长保跑通 | AS2 |
| 样本区间 | train 2000-2016 | train 2007-2016（CSI300 成分史） | 训练期缩短约 7 年 | AS13 |
| 网络/epoch 规模 | 见 B1/B2 | 若超时进一步降 d_model/H/epoch | 拟合能力下降，登记后按需触发 | AS18 |

> 缩减原则：**主 universe（CSI300-50）+ SIT-vs-传统基线 + 消融**为不可缩减的「方法成立」最小闭环；其余为算力弹性项。

---

## 八、改进建议与潜在问题（AI 视角）
- **未来函数红线**（ML 专项，已落 m1/m2/m4 验证点）：universe 点时选样、签名只用历史窗口、超参/τ 仅 val 选优 test 封存、信号 T 算 T+1 执行、月末调仓对齐交易日。code_audit / codex 须逐点核查。
- **签名自实现风险**：无签名库，M=2 手写须对合成 lead-lag 路径做符号/量级单元测试（Proposition 2.1），防交叉签名符号错误。
- **CSI300 锚的价值与局限**：R4 提供软锚可趋同比较，但本案缩减规模 + 迁移 + 数值豁免，趋同仅作参考、不作达标判据；「方法成立」以 SIT>传统基线 + 消融显著退化为准。
- **A股制度差异**：涨跌停、T+1 交易、停复牌较美股更强，月度 long-only 配置受影响较小，但换手/成本敏感性（SA3）结论可能偏离原文——属市场迁移正常差异，记录不强对齐。
- **待审复用件**：common/allocation_backtest.py（EW/GMV/HRP/portfolio_backtest）为前次未审产物，按「待审复用」对待，忠实性交 code_audit 核，不在 src/ 重复实现。
