# 歧义清单 ambiguities.md

> 本文由 quant-extractor 登记研报表述不清处；`裁决结果`/`裁决依据`/`状态` 由 quant-planner（plan 阶段）回填。本案 mode=auto、reproduction_mode=experimental：major 歧义由 planner 按最合理口径 auto 裁决并登记假设，无 blocking 级、无 open 残留。

### [A1] CVaR 置信水平 α 的实验取值未给出
- 页码: p2(Eq.3)、p4(Eq.17-20)、p17(附录E)
- 关联要素: F7, B7
- 等级: major
- 候选解释: 1. α=0.95（尾部质量 1−α=0.05，风险管理常用，可能性高） 2. α=0.90 3. 论文附录E用 α∈(0,1) 一般化，未固定；实验值须外部惯例补齐
- 裁决方式: auto
- 裁决结果: 取候选 1 但下调 α=0.80（与 K=12 耦合，见 A2）；登记 AS1
- 裁决依据: α 须与决策步 K 耦合——CVaR 经验式（F7 Eq.20）尾部有效点数≈(1−α)·K，须≥1 才非退化（否则退化为均值损失、SA1「w/o CVaR」消融失效）、宜≥2；原 α=0.95 在可行月度多步 K（≤12）下 (1−α)K<1 退化，故下调至 α=0.80 配 K=12 得 (1−α)K=2.4。α=0.80 尾部质量 0.20 仍属 CVaR 合理区间且有限样本下更稳；附录 E「1−α<q」为理论占优充分条件、非训练硬约束。verify 归因尾部估计不稳时迭代调整（增 K 或维持 (1−α)K≥2 下微调 α）
- 状态: resolved

### [A2] 回看窗口 H 与预测/决策窗口 K 的数值未给出
- 页码: p2（问题定义）、p16（Table 4 搜索空间未含 H/K）
- 关联要素: B8, D4, F3, F6
- 等级: major
- 候选解释: 1. H 取某固定日频窗口（如 60/120/252 交易日），K 与月度调仓一致（如 K=1 个月步或 21 交易日） 2. H/K 亦为网格搜索项但论文漏列
- 裁决方式: auto
- 裁决结果: 取候选 1，H=60 交易日（60 时间 token，Chen 增量）、K=12 月度步（多步前瞻，非单步）、交叉签名取全窗口；训练样本按月度决策点采样（尾部截断 K 个点）；登记 AS2
- 裁决依据: H≈3 个月为日频签名+月度调仓常见回看，Table4 未含 H/K 故取固定惯例值。K 须>1：原文 CVaR 为对未来 K 步损失取尾的多期 CVaR（F7 Eq.17-20、B8「next K periods」），K=1 使单场景仅 1 损失点、CVaR 退化为均值损失，SA1「w/o CVaR」消融与本体恒等而失效；取 K=12（月度一年多步前瞻）配 α=0.80 得 (1−α)K=2.4≥2、尾部平均有意义、消融方向性可验证；K 仅线性增输出头/损失、backbone 主导、CPU 可跑通。verify 欠拟合改 H/采样频率，尾部不稳则增 K 或微调 α（维持 (1−α)K≥1、宜≥2），算力紧张兜底降 K=6
- 状态: resolved

### [A3] 各 universe 具体成分股名单与从指数挑选子集的规则未给出
- 页码: p5（数据集描述）、p1（Figure 1 仅示意 TSLA/NVDA/AAPL）
- 关联要素: D1, R1, R2, R3, R4
- 等级: major
- 候选解释: 1. 按测试期起点某日的指数成分、以市值/流动性排序取前 N 只 2. 取全期连续在册成分中前 N 只 3. 随机/固定名单，论文未公开
- 裁决方式: auto（原 human；因 reproduction_mode=experimental 已授权迁移替代规划，planner 可自裁）
- 裁决结果: 取候选 1 的口径迁移至 A股——CSI300 成分按市值 top-N、点时快照、过滤 ST/停牌/历史不足；美股 universe（S&P100/DOW30）整体迁移为 CSI300 top-N 子集；登记 AS3（选样规则）+ AS12（美股→CSI300 迁移）
- 裁决依据: 本地无美股指数成分表且原文未披露名单 → 美股无法忠实重建；实验模式授权替代，「按市值取指数成分 top-N + 点时在册」为构造大盘 universe 兼防未来函数的标准做法；CSI300 为 A股大盘蓝筹等价母池，且 R4/Table7 提供 CSI300 软锚
- 状态: resolved

### [A4] 日历特征向量 v_t 的具体内容与维度 F 未明确
- 页码: p2（信息集(iii)）、p3（e_date 投影）
- 关联要素: D4, F3
- 等级: minor
- 候选解释: 1. 星期/月份/年内位置等确定性日历编码（one-hot 或正弦） 2. 含节假日/交易日计数等；维度 F 未知
- 裁决方式: auto
- 裁决结果: 取候选 1，[周内位/月/月内日/年内位] 各 sin/cos，F=8；登记 AS4
- 裁决依据: 确定性日历特征最常用 sin/cos 周期编码（Transformer/Time2Vec 惯例）；日历为弱辅助信号，编码方式对主结论影响很小
- 状态: resolved

### [A5] 多次运行的次数与随机种子设置未给出
- 页码: p5-p6、p19-p20（各绩效表均带 ± 标准差）
- 关联要素: R1, R2, R3, R4, SA1
- 等级: minor
- 候选解释: 1. 固定若干随机种子（如 3/5/10 次）重复训练取均值±std 2. 论文未披露 run 数，仅影响 std 复现、不改均值方向
- 裁决方式: auto
- 裁决结果: 固定 3 个随机种子、报告 mean±std（算力缩减）；登记 AS5
- 裁决依据: 原文未披露 run 数，3 种子为算力受限下评估随机性的常见最小设置；仅影响 std 复现口径，不改均值与结论方向
- 状态: resolved

### [A6] 输出头 pooling/last-slice 选择与主结果表 τ 取值未明确
- 页码: p4（输出头 "optionally preceded by pooling ... or using the last slice"）、p8（τ sweep {0.8,...,1.4}）
- 关联要素: F6
- 等级: major
- 候选解释: 1. 主表用验证集选出的最优 τ（敏感性显示峰值近 τ≈1.3） 2. 主表 τ=1.0 默认；pooling 与 last-slice 二者择一由验证集定
- 裁决方式: auto
- 裁决结果: 输出头取 last-slice；主表 τ 在验证集从 {0.8,1.0,1.2,1.3,1.4} 选优；登记 AS6
- 裁决依据: last-slice 为因果序列输出最简忠实取法；主表用 val 选优 τ 符合通用「val 选超参」范式，与敏感性峰值 τ≈1.3 相容
- 状态: resolved

### [A7] MLPβ/MLPq 结构与交叉签名输入维度 d_cross-sig 未给出
- 页码: p3（Eq.8-9 "a dedicated MLP"）
- 关联要素: F5
- 等级: major
- 候选解释: 1. 标准 2 层 MLP + 激活（如 ReLU/GELU），隐维取 HIDDEN C∈{8,16,32} 2. 单层线性投影；d_cross-sig 由签名阶 M=2 与资产对维度决定但未显式给出
- 裁决方式: auto
- 裁决结果: 取候选 1——MLPβ/MLPq=2 层 MLP+GELU、隐维=HIDDEN C；d_cross-sig=2（两个二阶交叉积分 ∫X^i dX^j、∫X^j dX^i，编码 signed area）；登记 AS7
- 裁决依据: 「a dedicated MLP」惯例为 2 层 MLP+GELU；M=2 两资产签名的二阶交叉项恰为 2 个，忠于 Eq.21 signed-area 定义；过窄可扩含 level-1 至 4 维
- 状态: resolved

### [A8] Table 7 题注与 Panel 标题、结论与 CSI300 市场表述不一致
- 页码: p20（Table 7 题注写 "10 and 20-asset from CSI300"，但 Panel A/B 为 50/100 资产）、p8（结论 "tested on U.S. equity data" 未提 CSI300）
- 关联要素: R4, D1
- 等级: minor
- 候选解释: 1. 题注为笔误，应以 Panel 标题 50/100 资产 CSI300 为准 2. 结论句为概述性表述、遗漏 CSI300 稳健性实验；均属文档不一致、不影响复现口径
- 裁决方式: auto
- 裁决结果: 取候选 1——采信 Panel 标题 50/100 资产 CSI300，题注/结论句判为文档不一致；登记 AS8
- 裁决依据: Panel 内标题与数值自洽，题注与正文概述属文档笔误/遗漏，取数值表标题为准；纯文档订正无运行时影响
- 状态: resolved

### [A9] 主绩效表（Table 1/5/6/7）是否为零交易成本未显式说明
- 页码: p5（Table 1 无成本标注）、p8（成本敏感性 c∈{0,5,10}bps，"All other settings follow the main evaluation"）
- 关联要素: B4, R1
- 等级: major
- 候选解释: 1. 主表为 0 bps 零成本（占优解释：Figure 5 的 0.0bps 列与 Table 1 SIT Sharpe 量级吻合） 2. 主表含某默认成本
- 裁决方式: auto
- 裁决结果: 取候选 1（占优）——主绩效表按单边 0 bps 复现，成本仅在 SA3 sweep；登记 AS9
- 裁决依据: Fig5 的 0.0bps 列与 Table1 SIT Sharpe 量级吻合，且「All other settings follow the main evaluation」暗示主表为 sweep 的 0bps 基准；实验模式数值豁免，方向不受影响
- 状态: resolved

### [A10] Figure 5 敏感性热图逐格数值的处理（原文 p8 可得、非不可转录；实验模式自算网格）
- 页码: p8
- 关联要素: SA3
- 等级: minor
- 候选解释: 1. Figure 5 的 (τ,c) 网格 mean±std 全部 42 格在 report_text.md p8 文本层可得（3 档 c × 7 档 τ × 40/50 两 Panel），可逐格参考 2. 实验模式（A股迁移、数值对齐豁免）下无需逐格对齐原文，自算 τ×c 网格即可
- 裁决方式: auto
- 裁决结果: SA3 热图由本复现自训练生成，仅作定性形态对比（峰值近 τ≈1.3、成本近似线性压缩夏普），不逐格对齐原文；原文 42 格数值在 p8 可得、留作参考；登记 AS10
- 裁决依据: 前次「文本层提取残缺、无法逐格还原」表述不实——Figure 5 全 42 格 mean±std 在 report_text.md p8 可提取；本案取「自算网格 + 原文值作参考」是因实验模式数值豁免，非因不可转录
- 状态: resolved
