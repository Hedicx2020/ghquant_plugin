# 假设登记簿 assumptions.md

> 落盘于 `workspace/r001_signature_transformer_allocation/assumptions.md`；每条 auto 裁决/替代/缩减一条，`来源` 回填对应歧义 ID。`验证后回看` 字段 verify 阶段已整体替换为实测回看（本文件全部假设的该字段均已回填完整档实测结论，无占位符残留）。
> `性质: market-transplant` 标记者为实验模式（市场迁移）替代项，final_report 与 major-auto 一并强调。

---

### [AS1] CVaR 置信水平 α 取 0.80（与决策步 K 耦合，见 AS2）
- 来源: A1（auto 裁决）
- 假设内容: 训练目标 CVaRα 置信水平取 α=0.80（尾部质量 1−α=0.20），与 K=12 耦合得 (1−α)·K=0.20×12=2.4；两阶段基线（B7）第二阶段 CVaR 亦用 α=0.80（其 CVaR 建于历史场景数 S 上、S 大不受 K 耦合约束，取同 α 保 DFL-vs-PFL 可比）
- 行业惯例依据: α 须与 K 耦合——CVaR 经验式（spec F7 Eq.20）逐场景对 K 个损失取尾、尾部有效点数≈(1−α)·K，须 (1−α)K≥1 才非退化、宜≥2 使尾部平均有意义；退化机理：K=1 或 (1−α)K<1 时尾部无有效点，ν_i=场景损失、(L−ν_i)_+→0，逐场景 CVaR 退化为均值损失，SA1「w/o CVaR」消融与 SIT 本体恒等、消融差为零（抽掉实验模式核心达标承重墙）；原 α=0.95 在可行月度多步 K（≤12，受算力/样本截断约束）下 (1−α)K≤0.6<1 退化，故下调 α 配可行 K；α=0.80 尾部质量 0.20 仍属 CVaR 组合优化合理区间（有限样本下宽尾部使经验 CVaR 更稳），附录 E「1−α<q（尾部质量<崩盘概率）」为理论占优充分条件、非训练硬约束，K=12 个月窗口内极端下行月概率可>0.20 使 1−α=0.20 仍落 q 下，框架不必然冲突
- 影响面: method
- 影响 milestone: m4（CVaR 目标 α），耦合 m2/m3（K）
- 影响指标: R4.Sharpe/Sortino/MDD/Wealth（核心），SA1 消融 w/o CVaR 对照（本修订正为保护此承重墙）
- 预期影响: α 与 K 联合决定尾部惩罚宽度、保 CVaR 非退化与消融方向性可验证；α 在 [0.80,0.90] 内偏移主要改尾部惩罚强度→影响回撤与集中度，量级差异有限、不改「SIT>基线」方向；verify 归因尾部估计不稳时按 AS2 迭代（增 K 或维持 (1−α)K≥2 微调 α）
- 验证后回看: 完整档实测——α=0.80/K=12/(1−α)K=2.4 使 CVaR 非退化，train_cvar 逐 epoch 下降（seed0 0.106682→0.058470，val best 0.033553@epoch42）；SA1「w/o CVaR」换均值目标后 Sharpe 0.8713→-0.2216（ΔSharpe-1.0929）、MaxDD 0.1574→0.4797，承重墙作用被大幅揭示；假设获强数据支持（CVaR 目标为 SIT 最关键组件）。
- 状态: assumed
- 高亮等级: major-auto

### [AS2] 回看窗口 H=60、决策步 K=12（多步前瞻，与 α 耦合）、交叉签名取全窗口
- 来源: A2（auto 裁决）
- 假设内容: H=60 交易日回看（60 时间 token，Chen relation 增量更新逐 token 签名）；K=12 月度步（未来 12 个月多步前瞻，非单步），与 α=0.80 耦合得 (1−α)·K=2.4；成对交叉签名在全窗口 [t−H,t] 每资产对算 1 个；训练样本按月度决策点采样，每场景消耗未来 K 个月故尾部截断 K 个决策点（训练期 ~120 月点截断后 ~108 场景），样本过少时按周/半月加密决策点
- 行业惯例依据: K 从 1 上调至 12 的核心理由——原文 CVaR 是对未来 K 步损失取尾的多期 CVaR（spec F7 Eq.17-20、B8「next K periods」），本身要求 K>1；K=1 使单场景仅 1 损失点、CVaR 退化为均值损失（见 AS1），破坏方法核心与 SA1 消融，故 K 须>1 且满足耦合 (1−α)K≥1（宜≥2）；K=12 取值——月度调仓（B3 monthly k-step）下 K=12=未来一年多步前瞻、是多期 CVaR 自然中期尺度，算力上 K 仅线性增大输出头（d_model→K×d 线性投影）与损失（K 点排序），backbone（签名+factorized 注意力，与 K 无关）占主导、K=12 增量可忽略、CPU 可跑通，样本截断 12 点后场景仍充足；H≈3 个月为日频签名+月度调仓常见回看，Table4 未含 H/K 取固定惯例值；兜底——样本截断致场景过少或 CPU 超时则降至 K=6（配 α=0.80 得 (1−α)K=1.2≥1 仍非退化），触发记 run_log
- 影响面: method
- 影响 milestone: m2（窗口/K 定维）、m3（输出头产 K 步 µ̂）、m4（CVaR 对 K 步损失取尾、K-step 调仓评估）
- 影响指标: 全部 R/SA（窗口影响特征信息量与样本数；K 决定 CVaR 尾部语义与 SA1 消融有效性）
- 预期影响: H 过短欠信息、过长增算力，60 为折中；K=12 使 CVaR 非退化、SA1「w/o CVaR」消融方向性可验证；verify 欠拟合则迭代改 H（40/120）或采样频率，尾部估计不稳则增 K 或微降 α（维持 (1−α)K≥2）
- 验证后回看: 完整档实测——H=60/K=12 下监督集 asset_sig=(108,60,50,7)、labels=(108,12,50)，train 场景=108/val=24（经边界 purge），充足；CVaR 对 K=12 步损失取尾训练跑通、SA1「w/o CVaR」消融方向性成立（见 AS1）；K=12 未退化前提被验证；假设获数据支持。
- 状态: assumed
- 高亮等级: major-auto

### [AS3] universe 选样规则：CSI300 成分按市值 top-N、点时快照、过滤 ST/停牌/历史不足
- 来源: A3（auto 裁决）
- 假设内容: 各 universe = CSI300（000300）成分中，按市值（market_value）降序取 top-N（主 N=50）；成员点时快照（各调仓日取当日在册成分，或以 test 起点 2020-01 快照固定，实现时择一并记录）；剔除 ST、当日停牌、样本期历史不足者
- 行业惯例依据: 原文未列成分名单与选样规则（A3）；「按市值取指数成分 top-N」是构造大盘 universe 的业内标准做法，且防未来函数需点时在册
- 影响面: data
- 影响 milestone: m1
- 影响指标: 全部 R/SA（universe 决定全部绩效）
- 预期影响: 具体成分与原文必然不同（原文本就美股）；实验模式数值豁免，只要 universe 稳定可复现即可
- 验证后回看: 完整档实测——CSI300-50 按 anchor 点时快照（实现取 AS19 第三选 train 起点，非 test 起点）产 (4510,50) 稳定面板、215 月末调仓、划分 108/24/60，universe 可复现；扰动 top-20/30 改 N 各产不同绩效（SIT Sharpe 0.4123/0.3151），选样规则真实驱动输出；假设获数据支持（成分与原文不同已豁免）。
- 状态: assumed
- 高亮等级: major-auto

### [AS4] 日历特征 v_t 用 sin/cos 周期编码、维度 F=8
- 来源: A4（auto 裁决）
- 假设内容: v_t 取 [周内位、月、月内日、年内位置] 各 sin/cos 编码，F=8 维；无节假日计数等额外项
- 行业惯例依据: 确定性日历特征最常用 sin/cos 周期编码（Time2Vec/Transformer 位置编码惯例）；原文仅称「deterministic calendar feature」未给内容
- 影响面: data
- 影响 milestone: m1
- 影响指标: 次要（日历嵌入 e_date 为辅助信息）
- 预期影响: 日历特征为弱信号，编码方式对主结论影响很小
- 验证后回看: 完整档实测——calendar_features_shape=(4510,8) 成形并入 F_ti，主表训练收敛、绩效产出；日历为弱信号未单独消融，对主结论无可测独立扰动；假设获数据支持（结构成立，弱信号性质符合预期）。
- 状态: assumed
- 高亮等级: -

### [AS5] 固定 3 个随机种子、报告 mean±std
- 来源: A5（auto 裁决）
- 假设内容: 每配置用 3 个固定随机种子重复训练，绩效报告 mean±std
- 行业惯例依据: 原文各表带 ±std 但未披露 run 数；3 种子为算力受限下评估随机性的常见最小设置
- 影响面: param
- 影响 milestone: m4
- 影响指标: 各 R 表 ±std（不影响均值方向）
- 预期影响: 仅影响 std 复现口径，不改均值与「SIT>基线」结论
- 验证后回看: 完整档实测——SIT/DLinear 各 3 种子（0/1/2）聚合产 mean±std（SIT Sharpe 0.7348±0.2659），传统基线单次；SIT std 0.2659 偏大（seed0 best_val 0.033553@epoch42 vs seed2 早停@epoch16），种子间波动显著、如实记录；假设按口径落地（3 种子最小设置下 SIT 结果稳定性偏弱，归因留 diagnoser）。
- 状态: assumed
- 高亮等级: -

### [AS6] 输出头用 last-slice、主表 τ 由验证集选优
- 来源: A6（auto 裁决）
- 假设内容: 分配头取最后一个时间 slice（last-slice，非 pooling）；主绩效表 τ 在验证集从 {0.8,1.0,1.2,1.3,1.4} 选优（与 SA3 sweep 一致）
- 行业惯例依据: last-slice 为因果序列模型输出的最简忠实取法；主表用 val 选优的 τ 符合「val 选超参」通用范式，敏感性显示峰值近 τ≈1.3
- 影响面: param
- 影响 milestone: m3
- 影响指标: R 表主绩效（τ 控集中度→夏普/回撤）、SA3/SA4
- 预期影响: pooling vs last-slice 影响有限；τ 选优保证主表用较优集中度
- 验证后回看: 完整档实测——τ val_cvar 选优 {0.8:0.0353,1.0:0.0336,1.2:0.0339,1.3:0.0410,1.4:0.0411}→选 τ=1.0（非预期近 1.3）；last-slice 输出头产合法单纯形权重（行和恒=1）；SA3 独立敏感性 0bps 峰值落 τ=0.8，与主表 val 选优 τ=1.0 口径独立；假设获数据支持（机制成立，τ 峰值位置较预期偏低，量级豁免）。
- 状态: assumed
- 高亮等级: major-auto

### [AS7] MLPβ/MLPq 为 2 层 MLP+GELU、d_cross-sig=2、hidden=HIDDEN C
- 来源: A7（auto 裁决）
- 假设内容: MLPβ、MLPq 均为 2 层（Linear→GELU→Linear），隐维取 HIDDEN C∈{8,16,32}（随网格）；β 输出 R^{NH×dβ}（dβ 取小值如 4）；交叉签名输入维 d_cross-sig=2（两个二阶交叉积分 ∫X^i dX^j、∫X^j dX^i，编码 signed area）
- 行业惯例依据: 原文仅称「a dedicated MLP」，2 层 MLP+GELU 为 Transformer 附属投影的标准结构；M=2 两资产签名的二阶交叉项恰为 2 个，编码 signed-area lead-lag（Eq.21）
- 影响面: method
- 影响 milestone: m3
- 影响指标: R 表（签名偏置强度）、SA1 w/o Financial Bias 对照、SA2 相关分布
- 预期影响: MLP 深度/激活对表达力有影响但非结构性；d_cross-sig=2 忠于 Eq.21，若过窄可扩为含 level-1 的 4 维
- 验证后回看: 完整档实测——β/γ 结构接线经 SA1 确证（w/o Financial Bias 去 γ·B 后 ΔSharpe+0.0048≈0），本迁移设定下签名偏置无可测边际贡献；SA2 签名-注意力 Pearson+0.0553 右偏（偏置结构确产正相关信号，但量级远弱于原文 0.540/0.611）；假设结构获支持、金融偏置贡献度存疑（归因留 diagnoser）。
- 状态: assumed
- 高亮等级: major-auto

### [AS8] Table 7 题注笔误、以 Panel 标题 50/100 资产 CSI300 为准
- 来源: A8（auto 裁决）
- 假设内容: Table 7 题注「10 and 20-asset from CSI300」判为笔误，采信 Panel A/B 标题 50/100 资产 CSI300；结论句「tested on U.S. equity」判为概述遗漏，不影响 CSI300 锚复现口径
- 行业惯例依据: Panel 内标题与数值自洽，题注与正文概述属文档不一致，取数值表标题为准
- 影响面: output
- 影响 milestone: m4
- 影响指标: R4（锚规模确认为 50/100）
- 预期影响: 纯文档订正，无运行时影响
- 验证后回看: 完整档确认——R4 锚采 Panel A 50 资产 CSI300（benchmarks.py R4_ANCHOR_CSI300_50，SIT 1.9373/2.3399/0.0964/1.2804），主表对照口径正确落地、xlsx 对照 sheet 逐位一致；纯文档订正无运行时影响；假设成立。
- 状态: assumed
- 高亮等级: -

### [AS9] 主绩效表（Table1/5/6/7）按零交易成本（0 bps）复现
- 来源: A9（auto 裁决）
- 假设内容: 主绩效表设定为单边 0 bps（零成本）；成本仅在 SA3 敏感性中 sweep {0,5,10}bps
- 行业惯例依据: 占优解释——Fig5 的 0.0bps 列与 Table1 SIT Sharpe 量级吻合，且「All other settings follow the main evaluation」暗示主表为 sweep 的 0bps 基准
- 影响面: trading
- 影响 milestone: m4
- 影响指标: 全部 R 表（成本抬升会压低夏普）
- 预期影响: 若原文主表含默认成本，复现值将系统性偏高；实验模式数值豁免，方向不受影响
- 验证后回看: 完整档实测——主绩效表以 cost_bps=0 产出（metrics.json/run_log 确认）；SA3 sweep 0/5/10bps 每 τ 下 0>5>10bps 成本单调压缩（τ=1.0：0.8713/0.8656/0.8599），0bps 为 sweep 基准自洽；假设获数据支持。
- 状态: assumed
- 高亮等级: major-auto

### [AS10] Fig5 敏感性热图自生成、仅作定性对比
- 来源: A10（auto 裁决）
- 假设内容: SA3 的 (τ,c) 热图由本复现自训练生成，不尝试对齐原文逐格数值（原文文本层无法可靠转录）；对比目标仅为定性形态（峰值近 τ≈1.3、成本近似线性压缩夏普）
- 行业惯例依据: 原文热图以图形呈现、pdfplumber 提取残缺（A10）；实验模式本就数值豁免
- 影响面: output
- 影响 milestone: m5
- 影响指标: SA3（定性形态）
- 预期影响: 仅影响 SA3 对比方式（形态 vs 逐格），不影响主结论
- 验证后回看: 完整档实测——SA3 (τ,c) 网格自生成，成本近似线性压缩 Sharpe（每 τ 下 0>5>10bps 单调）方向与原文一致；峰值 τ=0.8 与原文 τ≈1.3 有偏移；定性形态对比达成、逐格数值豁免；假设成立（成本方向印证，峰值位置偏移属迁移市场差异）。
- 状态: assumed
- 高亮等级: -

### [AS11] 市场迁移：WRDS 美股日频价格 → 本地 A股前复权日频
- 来源: 数据限制
- 性质: market-transplant
- 假设内容: 原文 D2 的 WRDS 美股日频价格整体替换为本地 `ashare_stock_price_forward`（A股前复权日频），日收益由 close/prev_close−1（或 change_pct）得到
- 行业惯例依据: 实验模式（reproduction_mode=experimental）复现目标为「方法在 A股是否成立」；A股前复权行情为回测收益的标准母源
- 影响面: data
- 影响 milestone: m1
- 影响指标: 全部 R/SA
- 预期影响: 市场整体改变，绝对数值不可与原文对齐（数值豁免）；方法机制可检验
- 验证后回看: 完整档实测——A股前复权对数收益面板 (4510,50) 成形驱动全流程，SIT 主表四指标 + SA1-4 方向性全部产出；绝对数值与原文不可对齐（已豁免），方法机制在 A股可检验（CVaR/AssetAttn 组件有效、τ 单调、签名-注意力正相关）；假设获数据支持。
- 状态: assumed
- 高亮等级: major-auto

### [AS12] 市场迁移：美股 universe（S&P100/DOW30）→ CSI300 top-N 子集
- 来源: A3（auto 裁决）
- 性质: market-transplant
- 假设内容: 因本地无美股指数成分表且原文未披露名单，S&P100 40/50/30、DOW30 10/20 各 universe 迁移为 CSI300 成分按市值 top-{40,50,30,10,20}；与 R4 的 CSI300 50/40 归并同族，不另设独立美股迁移池
- 行业惯例依据: S&P100/DOW30 均为大盘蓝筹指数，A股大盘蓝筹等价即 CSI300；迁移保持「大盘 top-N」尺度语义一致
- 影响面: data
- 影响 milestone: m4
- 影响指标: R1/R2/R3（纯迁移无锚，数值豁免）
- 预期影响: 迁移后 R1/R2/R3 仅作方向/跨规模机制对比，无原文数值锚
- 验证后回看: 完整档实测——CSI300 top-50 主档完整跑通（=R4-A 主锚）；扰动 top-20/30 佐证 top-N 尺度改变驱动输出（Sharpe 0.4123/0.3151）；R1（40 资产）/R2（30）/R3（10/20）完整档未跑（AS16 缩减），仅主档 CSI300-50 覆盖；假设主档获支持、次尺度覆盖有限。
- 状态: assumed
- 高亮等级: major-auto

### [AS13] 样本区间迁移：训练期起点 2000 → 2007
- 来源: 数据限制
- 性质: market-transplant
- 假设内容: train 迁移为 2007-01-01~2016-12-31（受 CSI300 成分历史起点约束），val 2017-2019、test 2020-2024 与原文对齐
- 行业惯例依据: CSI300 指数 2005 发布，成分进出数据成熟约 2007 起；保留 test 2020-2024 与原文/R4 同窗以增强锚可比性
- 影响面: data
- 影响 milestone: m1
- 影响指标: 全部 R/SA（训练期缩短约 7 年）
- 预期影响: 训练样本减少可能略降拟合；test 同窗保证与 R4 锚可比
- 验证后回看: 完整档实测——train 2007-2016（108 场景经 purge）、val 2017-19（24）、test 2020-24（60 期）成形，test 同窗保 R4 可比；训练期缩短下 SIT 未碾压基线（Sharpe 0.7348 居第 3），拟合充分性可能受训练期短影响；假设落地、训练充分性存疑（归因留 diagnoser）。
- 状态: assumed
- 高亮等级: -

### [AS14] 算力缩减：网格搜索 288 组 → 主 ≤8 组 / 次单配置
- 来源: 数据限制
- 假设内容: 原文 d_model{8,16,32,64}×d_ff{8,16,32,64}×layers{1,2}×heads{2,4,8}×hidden_c{8,16,32}=288 组缩减为主 universe ≤8 组（如 d_model{16,32}×d_ff{16,32}×layers1×heads{2,4}×hidden_c16）、次 universe 单配置，val 选优
- 行业惯例依据: CPU 环境无法完成 288×多种子×多 universe；缩减网格为算力受限下的标准折中
- 影响面: param
- 影响 milestone: m4
- 影响指标: 全部 R/SA（可能未命中原文最优配置）
- 预期影响: 加剧与原文数值偏离（已豁免）；不改方法方向；若欠拟合明显留待迭代扩网格
- 验证后回看: 完整档实测——8 组网格 val_cvar 选优 d_model=32/d_ff=32/heads=4（best 0.033553，即最大档）；选优落网格上界暗示更大模型或未含配置可能更优、缩减网格未必命中最优（SIT 绝对绩效偏低、未碾压基线）；假设落地、加剧数值偏离（已豁免），不改方法方向；欠拟合嫌疑归因留 diagnoser。
- 状态: assumed
- 高亮等级: major-auto

### [AS15] 算力缩减：预测类基线 8 个 → 4 传统 + 1 DLinear
- 来源: 数据限制
- 假设内容: 8 个深度预测基线（Autoformer/DLinear/FEDformer/PatchTST/iTransformer/NSformer/TimesNet/RFormer）缩减为保留 4 传统基线（EW/GMV/CVaR/HRP）+ 1 个代表性预测类两阶段基线 DLinear（B7 两阶段 MSE+CVaR 框架仅对其实现）
- 行业惯例依据: 逐一复现 8 个 SOTA 时序 Transformer 于 CPU 不可完成；DLinear 结构最简、可代表 PFL 两阶段范式，支撑 FIG4「DFL vs PFL」机制对照
- 影响面: method
- 影响 milestone: m4
- 影响指标: R 表基线列（缺 7 个深度基线）、FIG4（退化为 1 基线对照）
- 预期影响: SIT vs 传统基线主对比完整；FIG4「DFL 一致优于预测-only」仅 1 基线佐证
- 验证后回看: 完整档实测——保留 EW/GMV/CVaR/HRP+DLinear 共 5 基线四指标产出；DLinear 阶段一 best_val_mse≈7.7e-3 收敛（PFL 对照）；缺 7 个深度基线；SIT（DFL）Sharpe 0.7348 与 DLinear（PFL）0.7306 几乎持平，「DFL 优于 PFL」在本迁移单基线对照下未显现；假设落地、基线覆盖变窄，DFL-vs-PFL 结论存疑（归因留 diagnoser）。
- 状态: assumed
- 高亮等级: major-auto

### [AS16] 算力缩减：universe 7 组 → 主 CSI300-50 + 次 1-2 组
- 来源: 数据限制
- 性质: market-transplant
- 假设内容: 原文 7 组 universe 缩减为必跑 CSI300-50（R4-A 锚）、算力允许补 CSI300-100（R4-B 锚）或 CSI300-20（R3 尺度）择一；40/30/10 可选、单配置
- 行业惯例依据: 每 universe 需独立训练 + 网格 + 消融，CPU 无法全跑；保留主锚 + 一个跨尺度点即可支撑「方法成立 + 规模稳健」
- 影响面: data
- 影响 milestone: m4
- 影响指标: R1/R2/R3（部分尺度缺失）
- 预期影响: 跨市场/跨尺度覆盖变窄；主结论（CSI300 上方法是否成立）不受损
- 验证后回看: 完整档实测——CSI300-50 主锚完整跑通（主表 + SA1-4）；CSI300-100/20 等次尺度完整档未跑（扰动 smoke top-20/30 为耦合旁证、非验证主体）；跨尺度覆盖窄，主结论（CSI300-50 上方法机制成立、但 SIT 未碾压基线）已覆盖；假设落地、跨尺度稳健性未充分验证。
- 状态: assumed
- 高亮等级: major-auto

### [AS17] 路径签名 M=2 自实现（无签名库依赖）
- 来源: 数据限制
- 假设内容: 本地无 signatory/iisignature/esig，M=2 截断签名（level-1 增量 + level-2 迭代积分/signed area）与 Chen relation 增量更新自实现；对合成 lead-lag 路径做符号/量级单元测试（Proposition 2.1）
- 行业惯例依据: M=2 签名解析式简单、可精确手算，无需外部库；自实现避免依赖安装风险
- 影响面: method
- 影响 milestone: m2
- 影响指标: 全部 R/SA（签名为核心特征）
- 预期影响: 实现正确性经单元测试保障；风险在交叉签名符号，测试可拦截
- 验证后回看: 完整档实测——签名张量 asset_sig (108,60,50,7)+交叉签名成形驱动训练，全流程无签名库依赖跑通（EXIT 0）；结合 coder 单测（lead-lag A≈2π sinφ 符号量级校验）双重保障；SA2 签名信号正相关右偏佐证签名非平凡；假设获数据支持。
- 状态: assumed
- 高亮等级: major-auto

### [AS18] 算力兜底：训练超时则进一步降 d_model/H/epoch
- 来源: 数据限制
- 假设内容: 若 CPU 单次训练超时，按序进一步缩减 d_model（≤16）、H（≤40）、max epoch（≤50）以保证跑通，触发时逐项记录于 run_log
- 行业惯例依据: 「宁可缩小规模跑通并如实标注，不规划跑不完的方案」；分级降规是算力兜底标准做法
- 影响面: param
- 影响 milestone: m4
- 影响指标: 全部 R/SA（拟合能力随规模下降）
- 预期影响: 触发时绩效可能整体走低，需在报告标注为算力下限而非方法失效
- 验证后回看: 完整档实测——未触发本兜底：主表全档 d_model=32/H=60/max_epoch=100（早停 patience10）按 AS14 网格正常跑通（主表全档 EXIT0 约 15.5min、消融全档 403.5s），run_log 无超时降级记录；假设为备用兜底、本次未激活。
- 状态: assumed
- 高亮等级: major-auto

### [AS19] 固定资产集选样锚点取 train 起点点时快照、不可交易期收益置 0 占位
- 来源: coder 主动简化
- 性质: market-transplant
- 假设内容: SIT 需资产数 d 与资产身份跨 train/val/test 固定（资产维注意力 + 可学习 e_asset），故 universe 取 **anchor 日点时快照的固定资产集**、全程固定；anchor 默认取 train 段首个月末交易日（2007-01-31），按当日 CSI300 在册成分的当日市值 top-N 选样（这是 AS3 所列「各调仓日浮动」「test 起点快照」两选项之外的第三选，实现时择此并记录）。train 起点 top-50 中有 3 只在 test 期退市/长停致行情洞，对其不可交易期日收益置 0 占位（等价持现金无损益），并在 `universe_meta`（first_date/last_date/test_coverage/full_test）标注每资产有效交易区间，供 m4 回测屏蔽或权重重分配；`config.universe_anchor` 可切 "test_start" 得完整面板（备选，代价为回溯幸存偏差）
- 行业惯例依据: SIT 原文用固定指数成分回溯全 history；「固定资产集」与「防未来函数」刚性冲突时，固定 anchor 点时快照是唯一同时满足者，train 起点较 test 起点更严（后者选样用了未来在册信息，引入回溯幸存偏差）；停牌/退市样本不可交易期 0 收益为业内标准占位口径
- 影响面: data
- 影响 milestone: m1（选样与收益面板），下游 m4（回测屏蔽不可交易资产）
- 影响指标: 全部 R/SA（universe 决定全部绩效；退市洞仅占 3/50，冒烟实测 46/50 满 test 覆盖，影响有限）
- 预期影响: train 起点固定集含轻微退市洞，绝对数值受影响、实验模式数值已豁免、方法机制不受损；若 verify 认为洞干扰过大可切 universe_anchor="test_start"（面板完整、引回溯偏差）重跑
- 验证后回看: 完整档实测——3 只真死票（600005/600832/000562，test_coverage=0）在 SIT 面板全期权重恒=0.00e+00、活票 renorm 行和 min/max/mean 恒=1.000000，屏蔽机制生效；full_test=46/50、实测 3 真死+1 部分覆盖（000792 cov=0.754，可交易日合法权重 max=2.92e-03），退市洞占比小、影响有限；假设获数据支持（death mask 无幸存偏差）。
- 状态: assumed
- 高亮等级: major-auto

### [AS20] 连续路径重建（D5-i）用线性插值 → 分段线性路径，M=2 签名取精确闭式
- 来源: coder 主动简化
- 假设内容: spec D5「treat the price series as a continuous path via an appropriate interpolation」未指定插值方法，取**线性插值**（离散观测间直线连接 → piecewise-linear 路径）。对分段线性路径，M=2 截断签名有精确闭式：单段增量 δ 贡献 level-2 = ½ δ⊗δ、level-1 = δ；多段经 Chen relation 逐段拼接（level-1 可加、level-2 累加 running_level1⊗δ + ½ δ⊗δ）。故**无需 signatory/iisignature/esig 数值积分库**（AS17），签名为解析精确值而非数值近似（`signatures.py:signature_m2_parts` 参考实现即此递推，向量化版 `cross_signature_matrix`/`asset_signature_sequence` 数值等价，`test_signatures.py` 断言两者一致）
- 行业惯例依据: 线性插值是签名方法处理离散时间序列的默认路径重建（rough-path/signature 文献标准做法，如 lead-lag/time-joined transform 前置皆用线性插值）；分段线性路径签名有闭式、无积分离散误差，是最稳健的自实现路径
- 影响面: method
- 影响 milestone: m2（签名/交叉签名计算），下游 m3/m4（签名为核心特征）
- 影响指标: 全部 R/SA（签名为核心特征）
- 预期影响: 线性插值 vs 其它插值（样条等）对 M=2 低阶签名影响很小；闭式精确无数值误差，正确性经单元测试保障
- 验证后回看: 完整档实测——signatures.py 分段线性 M=2 闭式落地，签名特征成形并驱动训练收敛（train_cvar 稳定下降、无数值病态）；闭式无积分离散误差；假设获数据支持（结构成立）。
- 状态: assumed
- 高亮等级: -

### [AS21] 逐资产路径时间增广（time augmentation）：(归一化时间 k/H, 累积收益)，使单资产 M=2 signed-area 非退化
- 来源: coder 主动简化
- 假设内容: D4-(i)「for each asset j, a sequence of truncated path signatures」逐资产签名的输入路径取**时间增广 2D 路径** (t_k=k/H, X_k)（plan m2 明列「+时间增广」）。理由：单资产 1D 价格路径的 M=2 签名退化为 (1, ΔX, ½(ΔX)²)——level-2 仅 ½(ΔX)²、无 signed-area/几何信息；增广时间维后 level-2 含 ∫t dX、∫X dt 交叉项（时间-价格 signed area），编码窗口内动量/加速几何。故逐资产签名维 d_sig = 1(level0) + 2(level1) + 4(level2) = **7**（config.asset_signature_dim，时间增广+含 level0）。注：成对交叉签名（F2/D4-ii）用两资产价格构 2D 路径 (X^i, X^j)、**不另加时间维**（signed-area 即价-价 lead-lag，Eq.21），d_cross-sig=2（AS7）
- 行业惯例依据: 时间增广是签名方法处理单变量/低维序列的标准前置（否则 1D 路径签名平凡）；归一化时间 k/H∈[0,1] 为常用 time-embedding
- 影响面: method
- 影响 milestone: m2（逐资产签名维度），下游 m3（F3 签名嵌入 e_sig 定维 d_sig=7）
- 影响指标: 全部 R/SA
- 预期影响: 时间增广提升单资产签名信息量、为 SIT 资产内几何编码的通行做法；若 m3/verify 认为维度冗余可关 config.signature_time_augment（退化为 1D，d_sig=3）
- 验证后回看: 完整档实测——asset_sig 末维=7（1+2+4，时间增广含 level0）成形，签名特征驱动 SIT 训练；SA2 签名强度-注意力横截面 Pearson+0.0553 右偏，佐证时间增广签名携带非平凡信号；假设获数据支持。
- 状态: assumed
- 高亮等级: major-auto

### [AS22] 签名路径母源取前复权对数收益累积（≡ log 价格路径, 窗口起点 rebased），非原始价格
- 来源: coder 主动简化
- 假设内容: D5「Let S_u ∈ R^d denote the price path」的价格路径，签名计算时取**前复权对数收益累积** X_k = Σ_{m≤k} r_m（r 为 m1 `daily_log_returns`，AS11），等价 log 价格路径 log(S_k) 减窗口起点常数（rebased 至 0）。签名对路径整体平移不变（仅依赖增量 dX），故 rebase 不改签名值；用对数收益而非原始价格：跨资产尺度可比（¥300 股与 ¥8 股的绝对价差不可比、其 level-2≈(ΔS)² 量级天差，会使签名病态），对数收益 O(0.01–0.5) 量级均衡、数值良态
- 行业惯例依据: 签名平移不变 → log 价格 vs 累积对数收益等价；用（对数）收益而非原始价格是量价特征跨标的可比的标准归一化，避免高价股主导
- 影响面: method
- 影响 milestone: m2（签名输入母源），下游 m3/m4
- 影响指标: 全部 R/SA
- 预期影响: 对数收益路径使签名跨资产量纲一致、数值稳定；与原始价格路径的差异属单调变换 + rebase，不改 lead-lag 符号与几何方向（signed-area 符号保持）
- 验证后回看: 完整档实测——daily_log_returns 面板 (4510,50) 作签名母源，跨资产量纲一致、数值良态（训练 CVaR loss 稳定单调下降、无梯度爆炸/病态）；假设获数据支持。
- 状态: assumed
- 高亮等级: major-auto

### [AS23] SIT 网络结构细化：F3 三嵌入各投影 d_model + factorized 层(时间因果→签名资产→FFN, post-LN) + 无独立位置编码 + 输出头 Linear(d_model→K)
- 来源: coder 主动简化
- 假设内容: spec F3-F6 与 Table4 Panel E 未逐一钉死的网络结构细节，按 Transformer 惯例定型（`model.py`）：
  (1) **F3 嵌入子维（Eq.4）**：e_sig/e_date/e_asset 三源各线性投影至 d_model，拼接为 3·d_model 后经 W_proj→d_model；原文仅述「拼接后线性投影」未指定各源子维，取 d_model 为对称最简选择（`SignatureEmbedding`）。
  (2) **factorized 层结构（F4/F5）**：每层 = 时间维因果自注意力 → 签名增强资产维自注意力 → 前馈 FFN(Linear→GELU→Linear，隐维 d_ff=B2 D_FFS)，三子层均 **post-LN 残差**（`out→+residual→LayerNorm`，忠于 F5 Eq.15-16「W_O + 残差 + LayerNorm」措辞）；FFN 为标准 Transformer 组件、原文架构图(FIG2)含 FFN 但未给结构。
  (3) **无独立位置编码**：时间维因果注意力不额外加正弦/可学习位置编码——位置信息由 e_date（日历嵌入，含周内位/月/月内日/年内位）与时间增广签名（含归一化时间 k/H，AS21）提供，忠于 Eq.4 恰三源、不引入第四源。
  (4) **输出头（F6/AS6）**：last-slice 表征 (d, d_model) 经 Linear(d_model→K) 逐资产产 µ̂∈R^{K×d}（转置得 (K,d)），是「a linear projection ... produces µ̂^{1:K}」的最简忠实映射。
  (5) **gate γ̂ 初值 0**：γ=softplus(0)=ln2≈0.693 温和非零起点，避免签名偏置初期被压没（原文未给初值）。
  (6) **d_β 偏置嵌入维取 4**（原文未明，AS7 已登记取小值，此处定 sit_d_beta=4）。
- 行业惯例依据: 原文正文 + Table4 仅给 d_model/d_ff/layers/heads/hidden_c/sig-level 六项网格（B2），嵌入子维、残差/LN 位置、FFN 结构、位置编码、输出头映射、γ̂/d_β 初值均属实现自由度；上列取法为 Transformer/签名注意力文献通行的最简忠实实现，均可由 config 字段调整（sit_d_model/d_ff/n_layers/n_heads/hidden_c/d_beta/tau）供 m4 网格搜索
- 影响面: method
- 影响 milestone: m3（网络结构），下游 m4（训练/搜索）/m5（消融）
- 影响指标: 全部 R/SA（网络结构影响拟合能力与签名偏置强度）
- 预期影响: 结构细节对表达力有影响但非方法性——三嵌入融合/因果时间注意力/签名资产偏置/多步 softmax 分配四大骨架忠于 spec，细化项属通行默认；post-LN vs pre-LN、有无位置编码等可在 verify 欠拟合时迭代切换
- 验证后回看: 完整档实测——SIT 架构（三嵌入融合/因果时间注意力/签名增强资产偏置/softmax 分配头）完整跑通，产合法单纯形权重（行和恒=1）、端到端梯度回流（SA1 各消融开关方向可辨、证接线真实）；post-LN/无位置编码/输出头 Linear/γ̂ 初值 0 等细化项未致训练失败或数值病态；假设获数据支持（四骨架忠实、细化项跑通；模型是否欠拟合 → 见 AS14 归因）。
- 状态: assumed
- 高亮等级: major-auto

### [AS24] CVaR 训练实现：ν_i 取经验 α-分位并 detach（包络定理）+ 回测取 K 步第 1 步 w^(1) 月度调仓
- 来源: coder 主动简化
- 假设内容: spec F7 Eq.20「逐场景 min ν_i + [1/((1−α)K)]·Σ(L_i^(k)−ν_i)_+」的 ν_i，训练实现取**经验 α-分位 VaR_α 并 detach**（`train.py:cvar_from_losses`）：ν_i=torch.quantile(losses.detach, α)，梯度只经尾部超额项 (L−ν)_+ 回流。理由——Rockafellar-Uryasev 目标对 ν 凸、min 处次梯度含 0（包络定理 ∂CVaR/∂ν=0），plug-in α-分位即该逐场景 min 的解，detach 避免分位插值梯度噪声；损失**值**仍含 ν（=真 CVaR，手算校验精确一致：K=12/α=0.8 单场景 CVaR=ν+尾部超额逐位相符）。**回测调仓（B3）**：SIT 每决策日产 K=12 步权重 w^(1:K)，月度回测取**第 1 步 w^(1)**（`config.backtest_decision_step=0`）作当月目标权重、下月 receding-horizon 再决策（MPC 式滚动）；K 步序列整体仅供 F7 CVaR 训练取尾，非一次性持有 K 月。cvar_detach_nu 可切 False 让 autograd 经 torch.quantile 全微分（备选）。
- 行业惯例依据: RU CVaR 深度学习实现两条通行路径——ζ 作可学习辅助变量 或 plug-in 分位 detach；后者在 mini-batch（场景每 batch 变）下更简且梯度即尾部损失平均梯度（DFL 标准）。多步分配「plan K 步、执行第 1 步、下期重规划」是 receding-horizon/MPC 标准，与月度调仓自洽。
- 影响面: method
- 影响 milestone: m4（CVaR 训练目标 + 月度回测调仓）
- 影响指标: 全部 R/SA（训练梯度语义 + 回测权重来源）
- 预期影响: plug-in-detach 与可学习 ζ 数值等价（CVaR 值相同、梯度即尾部平均），不改方法方向；w^(1) 月度调仓是多步分配的标准执行口径，若 verify 认为应持有 K 月非重叠块可切 backtest_decision_step 语义（登记后触发）
- 验证后回看: 完整档实测——CVaR train loss 逐 epoch 下降（seed0 0.106682→0.058470，ν detach 尾部超额梯度回流有效），w^(1) 月度 receding-horizon 调仓产 60 期绩效表；SA1 w/o CVaR（换均值目标）ΔSharpe-1.09 反证 CVaR 训练语义真实生效；假设获强数据支持。
- 状态: assumed
- 高亮等级: major-auto

### [AS25] 基线协方差/场景窗口 + GMV 复用路径改 common.mean_variance_weights(µ=0)
- 来源: coder 主动简化
- 假设内容: (1) **GMV 复用路径**：plan m4 原列复用 `common._min_variance_weights`，但隔离验证发现其负权时回退的 SLSQP 用 λ=1e6 数值病态——>40 资产满秩样本协方差下 SLSQP 不收敛、逐位退化为等权（max=min=1/n、std=0，GMV 与 EW 完全相同）；故 GMV 改走 common **公开 API** `mean_variance_weights(exp_ret=0, cov, risk_aversion=1.0)`（同一最小方差目标 min wᵀΣw、良性缩放），产真 GMV（长仓集中，max≈0.35/std≈0.07）。仍属复用 common，非 src 重复实现。(2) **协方差窗口**：GMV/HRP 滚动样本协方差窗口 `cov_estimate_window=120` 月（须 > universe 资产数保满秩，否则秩亏→GMV 求逆退化；pre-test 史约 156 月支持 120）；(3) **CVaR 场景窗口**：传统 CVaR/两阶段 Mean-CVaR 的 RU-LP 历史场景 `cvar_scenario_window=60` 月（场景式不要求满秩）、最少 `cvar_min_scenarios=12`（不足回退等权）；窗口均取决策日 ≤T 的月度实现收益（点时、无未来）。
- 行业惯例依据: 长仓 GMV=均值方差在 µ=0 的特例（业内等价写法）；样本协方差满秩需 obs>assets 是统计常识；RU CVaR 组合优化场景数 S 与资产数无秩约束，60 月为月频常用回看。
- 影响面: method / param
- 影响 milestone: m4（基线权重估计）
- 影响指标: R 表 GMV/HRP/CVaR 基线列（窗口/求解影响基线绩效，SIT 对比基准）
- 预期影响: GMV 路径修正使其成为有意义的强基线（非退化等权）；窗口取值影响基线绝对绩效、不改「SIT vs 基线」对比结构；实验模式数值豁免
- 验证后回看: 完整档实测——GMV 走 mean_variance_weights(µ=0) 产真最小方差组合，主表 GMV Sharpe 0.9401（居首、非退化等权）显著 ≠ EW 0.4050，未退化；GMV/CVaR 作为强基线反超 SIT（0.7348），构成 SIT 未碾压基线的对照实证；假设获强数据支持（GMV 路径修正生效）。
- 状态: assumed
- 高亮等级: major-auto

### [AS26] DLinear 两阶段实现：分解核宽 25、µtarget 取等权组合预测收益、阶段一独立 MSE 早停
- 来源: coder 主动简化
- 假设内容: B7 两阶段仅实现 DLinear（AS15）。**阶段一**：DLinear（Zeng 2023 序列分解线性，通道独立、趋势+季节两线性分支）以 MSE 训练预测 K 步收益，输入=逐资产 H=60 日频回看序列，移动平均分解核宽 `dlinear_kernel=25`（日频惯例）、`dlinear_lr=1e-3`（沿用 B1）、`dlinear_max_epoch=60`/`dlinear_patience=8`（线性模型收敛快，独立 val MSE 早停）。**阶段二**：冻结预测器，取下期（第 1 步）预测收益 r̂ 作预期收益，min-CVaR 加目标收益约束 wᵀr̂ ≥ µtarget（RU-LP），**µtarget 取等权组合预测收益** mean(r̂)（`mean_cvar_target="equal_weight"`）——原文未给 µtarget，取等权预测收益保证 LP 恒可行（EW 天然满足约束）且构成「至少不劣于等权预测」的温和收益倾斜。
- 行业惯例依据: DLinear 分解核 25 为原论文日频默认；PFL 两阶段「预测收益→喂第二阶段优化」为 predict-then-optimize 标准；µtarget 取基准组合收益是避免 min-CVaR 目标收益约束不可行的常用兜底。
- 影响面: method / param
- 影响 milestone: m4（B7 两阶段基线，F8 的 PFL 对照）
- 影响指标: R 表 DLinear 基线列、FIG4「DFL vs PFL」机制对照（缩减为 1 基线佐证）
- 预期影响: DLinear 为 8 深度基线的代表性缩减（AS15），支撑「SIT 端到端 DFL vs 预测-优化 PFL」定性对照；µtarget/核宽取值影响 DLinear 绝对绩效、不改机制对照方向
- 验证后回看: 完整档实测——DLinear 阶段一 best_val_mse≈7.7e-3 收敛（3 种子 7.759632/7.719736/7.692372e-3，早停生效），两阶段 min-CVaR 产 DLinear 基线 Sharpe 0.7306±0.0779；DLinear（PFL）与 SIT（DFL）0.7348 几乎持平，「DFL 优于 PFL」在本迁移单基线对照下未显现；假设落地、机制对照方向存疑（归因留 diagnoser）。
- 状态: assumed
- 高亮等级: major-auto

### [AS27] m5 消融/敏感性实现口径：消融开关映射、SA2 聚合约定、SA3/SA4 权重来源
- 来源: coder 主动简化
- 假设内容: spec SA1-SA4 未逐一钉死的 m5 实现细节，按 spec 措辞最简忠实定型（`ablation.py`/`sensitivity.py` + `model.py`/`train.py` 向后兼容开关，默认 full 等价现行为）：
  (1) **SA1 四消融的开关实现**（spec SA1 测试设计 p6）：
    - **w/o CVaR**：结构保持完整 SIT，仅把训练损失从 F7 CVaR 换为**风险中性最大化均值收益** min E[−(w^k)ᵀr^k]（`train.py:portfolio_loss(objective="mean")`，忠于 spec「换为风险中性最大化均值收益」）；早停指标同步用 mean 目标（与训练目标一致）。
    - **w/o Asset Attn**：`SITBlock.ablation_disable_asset_attn=True` **整个跳过 F5 签名增强资产维自注意力子层**（残差与 LN 一并跳过，退化为仅时间因果注意力+FFN），忠于「禁用整个签名增强资产注意力」。
    - **w/o Financial Bias**：`SignatureAssetAttention.ablation_disable_bias=True` 令资产注意力取 `softmax(QK^T/√d_k)`（**去 γ·B 偏置项、退回标准注意力**），保留资产注意力结构本身。
    - **w/o Gate γ**：`ablation_gamma_fixed=1.0` **固定 γ=1**（保留签名偏置 B、去掉可学习 gate；γ 常数不参与梯度），忠于「去掉可学习 gate γ」。
    - 消融仅改单组件、其余超参（d_model/H/K/α/lr/…）不变（spec SA1「其余超参不变」）；被消融组件的冗余参数仍在优化器中但梯度为 0、不影响结果（不额外过滤，实现最简）。
  (2) **SA2 聚合与索引约定**（spec SA2 定义式 p7）：签名强度 s_{t,j}、入向注意力份额 a_{t,j} 从 SIT 前向 `return_aux` 暴露的**末个 factorized block**（`n_layers=1` 时唯一 block）的偏置矩阵 B（`aux["bias"]`）与注意力 α（`aux["attn"]`，形状 (N,H,N_H,d_query,d_key)）计算；约定张量 `[...,q,l]`=query q→key l，spec 的「来源 m→目标 j」即 **query=m、key=j**，故对 j 的三重求和 Σ_{k,h,m} 实现为沿 (切片 H、头 N_H、来源 query 轴) 求和、保留 key 轴=目标 j，再除 H·N_H·d 归一；逐决策时刻 t 对 {s_{t,j}}、{a_{t,j}} 求横截面 Pearson，零方差截面记 nan 不计入分布。
  (3) **SA3 权重面板/成本**：每 τ 用 `backtest.sit_weight_panel`（含 CA-A01 死票屏蔽 renorm）产一次月度权重面板（权重只依赖 τ），成本 c∈{0,5,10}bps 仅在回测经 `common.portfolio_backtest` 换手扣减（`dataclasses.replace(config, cost_bps=c)`）；主评估其余设定沿用（月度、long-only、0 rf）。
  (4) **SA4 集中度母源**：HHI=Σ_j w_j²、Shannon 熵 H=−Σ_j w_j·log w_j 用 SIT **原始 softmax 分配权重 w^(step)=softmax(µ̂^(step)/τ)**（未过死票屏蔽 renorm），度量**纯 τ 温度**对横截面集中度的单调效应（忠于 Fig6 语义，避免死票 renorm 引入的活票集变动噪声）；对测试期各决策日横截面指标取均值。
- 行业惯例依据: spec 仅给出各消融「移除什么组件」与两定义式，具体到「跳整层 vs 置零」「γ 固定值取 1」「B/α 的 query-key 索引朝向」「HHI 用原始权重 vs 屏蔽后权重」均为实现自由度；上列取法为 Transformer 消融与签名注意力可视化的通行最简忠实实现，且向后兼容开关默认关闭、不改 m3/m4 现行为。
- 影响面: method
- 影响 milestone: m5（SA1 消融 / SA2 相关 / SA3 敏感性 / SA4 多样化）
- 影响指标: SA1/SA2/SA3/SA4（全部为方向/单调性结论，数值豁免 experimental）
- 预期影响: 消融方向性（各组件移除⟹退化）与机制单调性（Thm2.2 正相关、τ↑⇒HHI↓熵↑）依赖完整训练方充分显现；冒烟 1 epoch/d_model=8 欠训练下 SA1 方向未完全分离、SA2 相关≈0，属欠训练非机制错误，完整训练档留 verify 核；开关/聚合口径若 verify 认为需调（如 SA2 跨层平均、SA4 用屏蔽后权重）可切换，登记后触发
- 验证后回看: 完整档实测（best-config，max_epoch100 早停10）——机制**部分支持**：SA1 两核心组件有贡献——w/o CVaR ΔSharpe-1.0929（0.8713→-0.2216）、w/o Asset Attn ΔSharpe-0.2898（→0.5815）显著退化；但 w/o Financial Bias +0.0048、w/o Gate γ +0.0067 两细组件**无可测贡献、原因未定**（单种子点估计、无配对多种子误差区间，不强行归因为噪声/欠训练，留 diagnoser 定）。SA2：Pearson n=59 均值+0.0553 中位+0.0259 右偏=True 正相关占比57.63%，方向印证 Thm2.2、量级远弱于原文 0.540/0.611。SA3：每 τ 下 0>5>10bps 成本单调压缩、0bps 峰值 τ=0.8。SA4：τ0.5→2.0 HHI 0.5961→0.0748 单调降、熵 0.8046→3.2497 单调升。核心组件与 SA2/3/4 方向获数据支持、两细组件贡献未定，整体部分支持（experimental）。
- 状态: assumed
- 高亮等级: major-auto
