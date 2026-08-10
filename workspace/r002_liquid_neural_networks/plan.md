---
report_name: r002_liquid_neural_networks
title: 神经常微分方程与液态神经网络
institution: 广发证券
date: 2025-03-06
type: ml
tags: [ml, factor]
difficulty: hard
feasibility: degraded
template: templates/ml.md
spec_ref: workspace/r002_liquid_neural_networks/spec/spec.md
data_requirements:
  - name: 个股日频OHLC与VWAP
    source: ashare_stock_price_forward.parquet
    status: available
  - name: 个股日频成交量与成交金额
    source: ashare_stock_trade.parquet
    status: available
  - name: 股票上市状态与上市日期
    source: ashare_stock.parquet
    status: available
  - name: ST、停牌、涨跌停与交易日历
    source: ashare_stock_st.parquet, ashare_stock_suspend.parquet, ashare_stock_limit.parquet, ashare_tradeday.parquet
    status: available
  - name: 未来收益率标签
    source: ashare_stock_price_forward.parquet
    status: derive
milestones:
  - id: m1
    name: 时点安全的数据、标签与样本切分
    desc: 构建A股动态股票池、60日六通道价量输入、T+1至T+21前复权VWAP收益标签及训练/验证/回测三段样本，交付防未来函数的数据审计结果；输入与标签为用户授权的降级口径。
    deps: []
    elements: [D1, D2, D3, D4, D5, B1, B2, B3, B4, B5]
  - id: m2
    name: 受控比较框架与GRU基准
    desc: 在统一输入、20日收益标签、MSE损失和训练流程下实现GRU基准，固化随机种子并交付训练/验证损失与样本外预测。
    deps: [m1]
    elements: [F2, F3]
  - id: m3
    name: 连续时间与稀疏液态网络族
    desc: 使用固定commit的ncps 1.0.1标准PyTorch实现构造全连接LTC/CfC及AutoNCP-wired LTC/CfC，逐模型完成前向、梯度、参数量与显存测试；明确不等同原研报私有参数。
    deps: [m1, m2]
    elements: [F1, F4, F5, F6, F7]
  - id: m4
    name: 预测因子、十档组合与多路径回测
    desc: 将五模型样本外预测转换为截面因子，执行十分档、多头与多空、20交易日多路径、T+1 VWAP交易和单边卖出费率回测，交付净值及指标明细。
    deps: [m1, m2, m3]
    elements: [F8, B6, B7, B8, B9, B10, B11, B12]
  - id: m5
    name: 结果对齐、稳健性与完整输出
    desc: 对照spec中R1-R7正文摘要基准，汇总显存、相关性、全期与2024年多头/多空表现及分年度结果；原图15-24与表6-10逐格内容仅作data_missing/reference_only，自有图表显著标注“复现生成”。
    deps: [m4]
    elements: [R1, R2, R3, R4, R5, R6, R7, SA1, SA2, SA3]
---

# 神经常微分方程与液态神经网络 复现开发计划

> **方法级降级复现：采用固定版本的开源标准实现，不等同原研报私有参数。** reproduction_mode 仍为 strict，仅对方法口径和缺失图表做用户授权降级，不做市场迁移。

## 研报信息

- 标题：神经常微分方程与液态神经网络
- 来源机构：广发证券（按规格书标题来源登记，原作者署名未披露，见 A1 / AS1）
- 发布日期：2025-03-06（网页转载日期）
- 作者：未披露
- 适用市场：A股
- 复现模式：strict；本地A股市场数据可得，不采用市场迁移或替代市场。
- 当前可行性：`degraded`。A2、A3、A5、A12 已按用户授权完成降级裁决，可进入实现；最终结论必须显著披露方法口径并非原研报私有参数。

## 一、核心策略与创新点

### 1.1 研究背景与核心思想

本报告以连续时间隐藏状态模型替换常规循环网络主干，在相同输入、标签、目标函数与训练流程下比较 GRU、LTC、NCP（LTC）、CFC、NCP（CFC）五类模型。最终输出为个股截面预测因子，接入十分档选股及多头/多空回测。由于报告关注液态网络方法本身、包含端到端模型训练且比较多种网络结构，主类型判为 `ml`，截面选股作为附加标签 `factor`。

连续时间状态的已披露定义为：

\[
\frac{d h_t}{dt}=f(h(t),t,\theta)
\]

离散网络与连续形式的衔接以规格书 F1 为准。现有规格缺少 LTC、NCP 与 CFC 的完整方程及私有结构参数，因此不反向猜测原研报实现；按 A5 / AS11 使用固定commit的 `ncps` 标准实现完成方法级降级复现。

### 1.2 特征、标签、模型与因子构造

1. 数据与特征：按 A3 / AS10 采用规格书明确出现的六个最小输入通道 `open, high, low, close, volume, turn_value`。OHLC转为相对各自前一交易日收盘的对数比率，成交量和成交金额取 `log1p`；所有通道的0.5%/99.5%缩尾阈值、均值和标准差只用训练集拟合。固定回看60个交易日，张量形状为 `[batch, time=60, features=6]`。
2. 标签：按 A2 / AS9 定义 \(y_{i,T}=VWAP^{fwd}_{i,T+21}/VWAP^{fwd}_{i,T+1}-1\)，即T日收盘后形成样本，T+1前复权VWAP买入，T+21前复权VWAP卖出，持有20个交易日；缺任一端点则删除该训练样本。五模型统一使用未排序的连续收益标签和 MSE 回归损失，不使用排序损失。
3. 样本切分：训练期为 2008-01 至 2016-12，验证期为 2017-02 至 2019-11，回测期为 2020-01 至 2024-12；保留报告要求的一个月防暴露间隔，任何标准化参数只在训练样本拟合。
4. 模型比较：五类模型共享特征张量、标签、MSE损失、优化和训练切分，仅替换主干网络；GRU口径见 AS2，四类液态网络按 AS11 的固定 `ncps` 映射实现。该比较是开源标准实现间的受控实验，不声称还原原研报私有超参数。
5. 预测因子：对每只股票在信号日 \(t\) 生成预测 \(\hat y_{i,t}\)，按截面从大到小排序并分为10档。多头与多空构造按 AS5。
6. 交易执行：信号严格在 T 日生成、T+1 执行；买卖价、持有期、多路径与股票池时点分别按 AS7、AS6、AS3、AS4 的当前假设，均保留 verify 后回看与 revise 入口。
7. 评估：截面 RankIC 定义为 \(\rho_{rank}(\hat y_{t}, y_{t})\)，并检查分组单调性、Top-Bottom 收益、年度收益与夏普；汇总口径见 AS8。

### 1.3 创新点

- 用连续时间动态与可学习时间常数替代离散 GRU 隐藏状态更新。
- 用 NCP 稀疏四层神经电路结构约束连接，提高结构稀疏性与可解释性。
- 用 CFC 闭式连续时间近似减少数值求解开销，并比较其稀疏 NCP 版本。
- 通过统一输入、标签、损失和训练切分，尽量把性能差异归因于网络主干；由于私有参数缺失，该结论只适用于本次开源标准实现口径。

### 1.4 开源实现来源、版本与许可证

| 来源 | 固定版本 | 许可证 | 本计划用途 |
| --- | --- | --- | --- |
| [mlech26l/ncps](https://github.com/mlech26l/ncps) | commit `695ec22d7d1831f2ced67346ef7d2f08c525bd47`；package version `1.0.1` | Apache-2.0 | 主实现依赖：`ncps.torch.LTC`、`ncps.torch.CfC`、`ncps.wirings.AutoNCP` |
| [raminmh/liquid_time_constant_networks](https://github.com/raminmh/liquid_time_constant_networks) | commit `4a8a4fa22a91c4067b6944a264819ff30a4aae9d` | Apache-2.0 | LTC论文与官方实现脉络证据；README指向 `ncps` 的PyTorch实现 |
| [raminmh/CfC](https://github.com/raminmh/CfC) | commit `3ebaa0307a280c5a9ee8261fdf733ad9bd5636ad` | Apache-2.0 | CfC论文与作者实现脉络证据 |
| [rtqichen/torchdiffeq](https://github.com/rtqichen/torchdiffeq) | commit `657943acefa826ef04c025ebeb1ff5e9d60dc268` | MIT | Neural ODE背景和可选对照；不纳入四类液态模型主实现依赖 |

四模型一一对应为：全连接LTC=`LTC(input_size=6, units=64)`；NCP（LTC）=`LTC(input_size=6, units=AutoNCP(64, 1, sparsity_level=0.5, seed=22222))`；全连接CFC=`CfC(input_size=6, units=64, mode="default")`；NCP（CFC）=`CfC(input_size=6, units=AutoNCP(64, 1, sparsity_level=0.5, seed=22222), mode="default")`。均设置 `batch_first=True`、`return_sequences=False`、`mixed_memory=False`；LTC沿用 `ode_unfolds=6`，其余未显式参数使用该固定版本默认值。四模型配置与来源commit必须写入运行日志。

## 二、回测参数

- 选股范围：每个信号日的A股动态全市场股票池（AS4）。
- 过滤规则：剔除未上市/摘牌、ST/*ST、上市未满1年；交易执行日停牌或涨跌停不可成交（AS4）。
- 训练区间：2008-01 至 2016-12。
- 验证区间：2017-02 至 2019-11，与训练期保留1个月间隔。
- 回测区间：2020-01 至 2024-12，与验证期保留1个月间隔。
- 特征字段与回看窗口：六通道OHLC/成交量/成交金额，60交易日窗口，训练集拟合缩尾和标准化（AS10）。
- 标签周期与目标函数：T+1至T+21前复权VWAP简单收益，MSE回归损失，不使用排序损失（AS9）。
- 模型结构：GRU采用AS2；LTC、NCP（LTC）、CFC、NCP（CFC）采用固定commit的`ncps` 1.0.1标准实现（AS11）。
- 分组数：10档，因子从大到小排序。
- 多头/多空：第一档等权多头；第一档减第十档的等权多空（AS5）。
- 调仓与持有：每20个交易日调仓，当前令 \(n=20\)（AS6）。
- 多路径：20个起始交易日偏移路径分别回测后算术平均（AS3）。
- 信号与成交：T日信号、T+1执行，成交价取日VWAP（AS7）。
- 交易成本：卖出单边0.3%，买入不收费。
- RankIC、年化与夏普：按 AS8 计算；无风险利率暂取0。
- 随机性：模型训练固定种子42；必要的重复训练仅作为扰动测试，不混入 AS3 的回测路径定义。

## 三、研报核心结果（验证基准）

> 具体数值、原文和页码只引用 `workspace/r002_liquid_neural_networks/spec/spec.md`，本计划不重复抄录。

| R 要素ID | 一句话摘要 | 关联 milestone |
| --- | --- | --- |
| R1 | LTC文献任务性能提升范围，属于文献背景参照 | m5 |
| R2 | 五类模型显存依赖对比 | m5 |
| R3 | 五类模型因子相关系数范围 | m5 |
| R4 | 2020至2024年多头表现 | m5 |
| R5 | 2024年多头表现 | m5 |
| R6 | 2020至2024年多空表现 | m5 |
| R7 | 2024年多空表现 | m5 |

## 四、复现计划（按 milestone 拆分）

### m1: 时点安全的数据、标签与样本切分

- 实现内容：读取前复权行情、成交、股票状态、ST/停牌/涨跌停与交易日历；按日生成动态股票池；构造输入张量、标签和训练/验证/回测切分。
- 依赖数据：frontmatter 的5项数据要求，均为 `available` 或 `derive`；A2、A3 的用户授权方法口径分别见 AS9、AS10，不改写数据目录状态。
- 产出文件：数据质量表、样本数量与日期覆盖表、特征统计与缺失率、标签分布、股票池过滤日志。
- 验证点：训练统计量不得使用验证/回测样本；标签不跨越切分边界；上市/ST/停牌/涨跌停状态按时点生效；T日特征不得含T后信息。
- 降级边界：60日六通道输入和T+1至T+21标签不是原研报披露参数；运行日志、comparison和最终报告必须引用 AS9、AS10。

### m2: 受控比较框架与GRU基准

- 实现内容：建立共享数据接口、损失、优化、早停、随机种子和输出头；实现GRU基准并保存训练检查点和样本外预测。
- 依赖数据：m1 的特征、标签和切分。
- 产出文件：GRU模型配置、训练/验证损失、样本外预测、显存与参数量日志。
- 验证点：同一配置重复运行可复现；验证期只用于模型选择；回测期不参与调参；AS2 全量写入配置并保留可切换入口。
- 降级边界：MSE与GRU超参数属于用户授权的可复现基线，不得写成原文参数；所有模型必须共用同一标签与损失。

### m3: 连续时间与稀疏液态网络族

- 实现内容：在 m2 的共享框架下，用 `ncps` 1.0.1固定commit实现全连接LTC/CfC与AutoNCP-wired LTC/CfC一一对应的四模型；逐模型保存检查点、预测和资源日志。
- 依赖数据：m1 数据，m2 共享训练框架。
- 产出文件：四类液态网络配置与权重、单元测试、训练曲线、样本外预测、参数量和显存结果。
- 验证点：单步前向维度、梯度有限性、稀疏连接约束、数值稳定性、训练/预测无未来样本泄漏。
- 降级边界：实现只代表 AS11 所列开源标准模型，不等同原研报私有结构、参数或训练代码；不得用 `torchdiffeq` 替换四模型主实现。

### m4: 预测因子、十档组合与多路径回测

- 实现内容：合并五模型预测，计算因子相关性；执行十分档、第一档多头和第一档减第十档多空；实现20路径、T+1 VWAP、20日持有与卖出费率。
- 依赖数据：m1 股票池和行情，m2/m3 五模型样本外预测。
- 产出文件：因子面板、相关性矩阵、各路径持仓与交易明细、十分档净值、RankIC时序、全期和年度指标表。
- 验证点：T日排序、T+1成交；不可成交处理无前视；费用仅在卖出扣除；20路径分别可复算且聚合无重复计权。

### m5: 结果对齐、稳健性与完整输出

- 实现内容：对照 R1-R7 正文摘要和 SA1-SA3，生成 `backtest_summary.xlsx` 及多sheet明细；输出 `feature_importance.png`、`ic_series.png`、`group_cumulative_returns.png`、`train_val_loss.png`、`prediction_scatter.png`，并补充五模型相关性、年度收益和资源占用图表。所有自有图表标题须含“复现生成—非原图复刻”。
- 依赖数据：m4 的全部预测、持仓、路径和指标结果，以及 m2/m3 的训练与资源日志。
- 产出文件：Excel、PNG、`metrics.json`、`comparison.json` 与逐项证据清单。
- 验证点：对R1-R7正文摘要逐项核验；模型层检查IC方向、量级、分组单调性和Top组排序；2024子样本与复现生成的分年度统计可由明细重算。
- 降级边界：原图15-24、表6-10逐格内容因 `data_missing` 判为 `infeasible/reference_only`，不得生成同编号、同题名图表冒充原图复现；表4-5缺失逐格内容亦只核正文摘要。降级范围见 AS12。

## 五、难度判定

- 方法复杂度基准：`hard`。该报告需要训练五类端到端神经网络，包含连续时间微分方程求解、稀疏网络结构与统一控制实验，直接命中“训练模型/优化求解”高复杂度主轴。
- 数据可得性修正：市场数据均可直接取得或衍生，不因市场数据上调；输入、标签、模型参数和逐格图表缺失已由用户授权降级表达，故可行性为 `degraded` 而非 blocked。
- 模块数量修正：五类模型、数据管线、组合回测和结果核验构成多模块链路；难度已封顶 hard，不再重复上调。
- easy 收口：不满足。该任务不是单模块标准公式，包含五模型训练和多项用户授权降级假设。
- 编排拆分：采用5个无环里程碑，顺序为 `m1 → m2 → m3 → m4 → m5`；每个里程碑均有独立产物和验证点，hard 的最低3个里程碑要求已满足。

## 六、可行性与用户授权降级范围

| 歧义 | 用户授权裁决 | 理由码 | 影响 milestone |
| --- | --- | --- | --- |
| A2 | 采用T+1至T+21前复权VWAP简单收益与MSE，见AS9 | method_underspecified | m1, m2, m3 |
| A3 | 采用60日六通道价量张量及训练集拟合标准化，见AS10 | method_underspecified | m1, m2, m3 |
| A5 | 采用固定commit的`ncps`标准四模型映射，见AS11 | method_underspecified | m3 |
| A12 | R1-R7摘要仍作基准；原图15-24和表6-10逐格内容仅reference_only，见AS12 | data_missing | m5 |

四项原阻断歧义已全部 resolved，流程可实施，但可行性仅为 `degraded`。本地A股数据覆盖原市场，reproduction_mode 保持 strict，不触发实验模式或市场迁移。

## 七、改进建议与潜在问题（AI 视角）

- 若后续取得带完整图片的原研报或私有训练代码，应优先用 `/reproduce revise` 替换 AS9-AS12，而不是把当前开源口径追认为原文参数。
- 对所有特征预处理器执行“只在训练段拟合”的单元测试，并核验标签时间戳与T+1交易之间的边界，防止隐性未来函数。
- 将 AS2-AS12 全部参数化，verify 后逐条回看；若核心指标偏差集中指向某项假设，可用 `/reproduce revise` 定向重跑。
- 显存数字高度依赖硬件、batch size、精度和框架版本；即使结构补齐，也应同时报告绝对值与相对比例，并记录运行环境。
- 神经网络结果应固定种子并做至少一次种子扰动；扰动用于稳健性，不应与“20个回测起始路径”混为一谈。
- 结果对齐必须明确标为“方法级降级复现/摘要数值核验”；不能宣称完整复原图15-24、表4-10，也不能把自有诊断图编号成原研报图表。
