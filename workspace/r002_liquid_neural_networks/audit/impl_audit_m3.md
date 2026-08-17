# m3 实现忠实性审计

## 审计范围

- mode：code
- milestone：m3
- 案例：r002_liquid_neural_networks
- 本次仅审矩阵中m3且done的F1、F4、F5、F6、F7，共5项；不读取coder完成汇报，不提前裁决m4/m5。
- 证据范围：`spec.md`、`coverage_matrix.md`、`assumptions.md`、本案例`src/`、`common/ml_liquid.py`、`common/ml_training.py`、`pyproject.toml`、`uv.lock`及`/tmp/r002_open_sources/ncps`官方源码checkout。
- 空壳检查：5个done要素列出的全部实现函数均真实存在且有可执行函数体；沿调用链未发现 `pass`、TODO 或 `NotImplemented` 空壳。

## 五维度总体核对

| 维度 | 独立核对内容 | 结论 |
| --- | --- | --- |
| 公式一致 | 核对F1的ODE导数与欧拉残差递推、LTC官方半隐式求解、CfC官方门控闭式单元及统一回归输出。 | F1可实际计算非恒定轨迹；F4-F7直接使用固定ncps官方算子，无自造公式。通过。 |
| 参数一致 | 逐项核对6维输入、64 units、AutoNCP(64,1,0.5,22222)、LTC ode_unfolds=6、CfC mode=default、batch_first=True、return_sequences=False、mixed_memory=False。 | 集中配置、构造透传、官方签名与动态实例属性四方一致。通过。 |
| 实现位置真实 | 打开矩阵所列F1三个公共函数、`build_liquid_regressor`及`build_liquid_model`，并反查官方实现和m2训练接口。 | 所列位置均真实、非空壳且可运行。通过。 |
| 代码反查 | 从m3全部公开函数反向核对F1/F4-F7矩阵映射。 | 矩阵列出的入口可回映，但策略层4个公开函数和公共模块3个公开函数未直接回映，见CA-A01、CA-A02。 |
| 简化声明 | 对照AS9、AS10、AS11、AS15检查输入、标签、模型、训练和“非原研报私参”边界。 | AS11及代码manifest完整记录固定开源来源、参数和方法级降级；未发现未登记的core方法简化。通过。 |

## done 要素逐条核对

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | `common/ml_liquid.py:34-51`计算 `dh/dt=f(h,t,θ)`；`54-68`落实 `h_next=h+dt×f(h,t,θ)`；`71-93`在严格递增网格逐步积分。θ可由传入的可调用向量场封装，梯度链未被截断。 | 时间点至少2个、严格递增，步长为有限正数；未擅自固定向量场或步长。 | 矩阵列出的3个函数均真实存在且互相调用。 | F1三个公开计算入口全部直接列入矩阵。 | F1仅实现规格中的通用ODE/欧拉衔接，不冒充LTC私有求解公式；F4实际求解仍来自固定ncps。 | pass |
| F4 | `common/ml_liquid.py:200-210`构造官方 `LTC(input_size=6, units=64)`；官方`ltc_cell.py:203-249`用分子/分母更新并展开求解，符合规格的半隐式欧拉方法。 | 6、64、batch_first=True、return_sequences=False、mixed_memory=False、ode_unfolds=6全部由`config.py:170-180`透传；官方`ltc.py:23-35`接受相同参数。 | `common/ml_liquid.py:161-237`与`strategy.py:530-550`均真实可执行。 | 已映射两个模型构造入口；其余公开family/train/manifest函数存在缺口，见CA-A01、CA-A02。 | AS11明确这是固定开源标准实现、非原研报私参；manifest逐模型写入来源和scope。 | pass_with_issues（CA-A01、CA-A02） |
| F5 | `common/ml_liquid.py:189-208`先建AutoNCP wiring再传入官方LTC；官方`wirings.py:603-647`生成感觉输入、inter、command、motor输出的稀疏NCP连接。 | AutoNCP units=64、output=1、sparsity=0.5、seed=22222，LTC ode_unfolds=6，其余三项布尔参数均严格一致。动态实例为AutoNCP、3个内部神经元层加感觉输入、输出维度1且稀疏。 | F5矩阵所列公共和策略构造函数均真实存在。 | 构造入口已映射；训练、family和manifest公开函数未全部映射。 | AS11逐项登记wiring、稀疏度、输出维度和seed，并披露原研报可能使用不同私参。 | pass_with_issues（CA-A01、CA-A02） |
| F6 | `common/ml_liquid.py:211-219`调用官方CfC；官方`cfc.py:24-38,87-102`在非wired模式构造标准CfCCell，`mode=default`进入门控闭式实现。 | input=6、units=64、mode=default、batch_first=True、return_sequences=False、mixed_memory=False；backbone_units/layers/dropout等未覆盖，使用固定版本默认值，符合AS11。 | 矩阵所列两个构造位置真实且动态输出形状正确。 | 构造入口已映射；其余公开入口存在CA-A01、CA-A02。 | 标准实现版本和非私参边界已登记并进入manifest/checkpoint元数据。 | pass_with_issues（CA-A01、CA-A02） |
| F7 | `common/ml_liquid.py:189-219`将同一AutoNCP wiring交给官方wired CfC；官方`wired_cfc_cell.py:11-59`逐层按wiring稀疏矩阵构造CfCCell。 | AutoNCP(64,1,0.5,22222)、mode=default及三项布尔参数完全一致；动态核验三个wired CfC层的mode均为default，主干读出维度1。 | 矩阵所列构造位置真实且可执行。 | 构造入口已映射；其余公开入口存在CA-A01、CA-A02。 | AS11明确固定commit映射与私参缺失影响，代码未把本实现称作原研报参数。 | pass_with_issues（CA-A01、CA-A02） |

## 重点独立核验

### 1. F1非恒定ODE与欧拉衔接

- 以 `f(h,t)=h+t`、初值 `[1,2]`、时间网格 `[0,0.5,1]`做内存重算，代码返回轨迹 `[[1,2],[1.5,3],[2.5,4.75]]`，逐步等于 `h_next=h+dt×f(h,t)`。
- 轨迹随状态和时间变化，导数、单步和多步积分均参与实际张量计算，不是元数据常量或占位返回。
- 该辅助实现对应F1通用显式欧拉/ResNet衔接；F4的LTC半隐式求解来自官方`LTCCell._ode_solver`，其6次展开与分式更新位于官方`ltc_cell.py:203-249`，两者没有混冒。

### 2. 四模型参数与官方接口

| 模型 | 实际构造 | 官方接口核验 | 动态核验 |
| --- | --- | --- | --- |
| LTC | `LTC(6,64, batch_first=True, return_sequences=False, mixed_memory=False, ode_unfolds=6)` | 官方`ltc.py:23-35,82-96`支持整数units并建立FullyConnected wiring。 | 回归输出`(2,)`；主干读出64；ode_unfolds=6。 |
| NCP（LTC） | `LTC(6, AutoNCP(64,1,0.5,22222), ..., ode_unfolds=6)` | 官方`wirings.py:603-647`签名和约束完全匹配；LTC接受Wiring。 | AutoNCP seed=22222、sparsity=0.5、output=1、实际稀疏；回归输出`(2,)`。 |
| CFC | `CfC(6,64, ..., mode="default")` | 官方`cfc.py:24-38,87-102`支持整数units和default模式。 | 主干读出64，cell mode=default，回归输出`(2,)`。 |
| NCP（CFC） | `CfC(6, AutoNCP(64,1,0.5,22222), ..., mode="default")` | 官方`cfc.py:70-86`进入wired模式，`wired_cfc_cell.py:28-58`按层应用稀疏连接。 | 主干读出1，三个wired层mode均default，回归输出`(2,)`。 |

- 四个模型的recurrent layer均实际报告 `batch_first=True`、`return_sequences=False`、`use_mixed=False`。
- `NcpsSequenceBackbone`把官方 `(readout,state)` 统一转为 `[batch,hidden]`，再由`SequenceRegressor`接相同线性回归头（`common/ml_liquid.py:96-140,221-237`）。

### 3. m2训练接口可替换性

- 液态模型返回与GRU相同的 `SequenceRegressor`，公共训练器只要求模型工厂返回`torch.nn.Module`（`common/ml_training.py:358-379`）。
- `strategy.py:598-603`复用同一M2Config训练设置；`606-676`只替换模型工厂，训练/验证数据、MSE、Adam、早停、检查点与回测后预测路径保持不变。
- `train_liquid_family`对四个model_specs逐一调用相同训练入口（`strategy.py:679-694`）。F2“非主干一致”的接口约束得到延续。

### 4. 依赖commit、版本与许可证

- `pyproject.toml:42-43`将ncps固定到commit `695ec22d7d1831f2ced67346ef7d2f08c525bd47`；`uv.lock:1058-1065`锁定同一git来源和distribution version 1.0.1。
- 本地官方checkout的HEAD独立读取为同一commit且工作区无修改；官方`setup.py:18-26`声明version 1.0.1与Apache License 2.0，根`LICENSE:1-4`为Apache License Version 2.0。
- `pyproject.toml:17`与`uv.lock:2445-2448`还将PyTorch解析为2.12.1，当前锁文件具备确定依赖解。
- `common/ml_liquid.py:275-318`在manifest生成前核验已安装distribution版本；动态核验得到actual=1.0.1，并逐模型记录source URL、commit、license和scope。固定依赖证据链成立。

### 5. “非原研报私参”声明

- AS11明确列出固定开源参数、来源版本、许可证、影响指标和与原研报私参可能不一致的预期影响（`assumptions.md:123-133`）。
- `config.py:154-180`集中记录同一来源及参数，`method_scope`明确为“方法级降级复现：固定开源标准实现，非原研报私有参数”。
- `common/ml_liquid.py:285-318`把该scope写入每个模型manifest；`strategy.py:617-640`又将manifest作为检查点模型元数据。四模型均不会在后续产物中丢失降级边界。

## issue 清单

| 编号 | severity | 证据定位 | 一句依据 | 处置要求 |
| --- | --- | --- | --- | --- |
| CA-A01 | major | `workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:17-20`；`src/r002_liquid_neural_networks/strategy.py:553-595,606-694` | m3策略层公开函数 `build_liquid_family`、`build_m3_model_manifest`、`train_liquid_model`、`train_liquid_family`均承载F4-F7构造、证据或训练，但F4-F7实现位置只回映 `build_liquid_model`，存在公开实现“私货”。 | 将这些公开函数按实际覆盖关系回填F4-F7，或把纯辅助入口改为私有并由已映射公开入口封装；修复后定向复审代码反查。 |
| CA-A02 | major | `workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:17-20`；`common/ml_liquid.py:240-318` | 公共模块公开函数 `summarize_liquid_wiring`、`assert_ncps_version`、`build_liquid_model_manifest`实际生成稀疏度、版本、来源和许可证证据，但矩阵仅列 `build_liquid_regressor`，三项均未直接回映任何F要素。 | 将三项证据函数回填至F4-F7的实现位置，或调整为私有辅助并保持已映射调用链；不得删除其依赖核验与manifest证据。 |

## 审计结论

- 已逐条审计m3全部5个done要素：F1、F4、F5、F6、F7。
- 已检查维度：公式一致 / 参数一致 / 实现位置真实 / 代码反查 / 简化声明。
- F1为真实可计算的非恒定ODE/欧拉实现；F4-F7严格匹配AS11与固定commit官方ncps接口，依赖版本和许可证证据成立。
- 四模型均可替换接入m2统一训练器，“非原研报私参”声明进入配置、manifest和检查点元数据。
- 未发现critical问题或空壳；当前2项major均为公开函数矩阵映射缺口。

## 第1次定向复核

- 复核模式：code。
- 复核边界：仅复核CA-A01、CA-A02所列7个公开函数的矩阵回映，并在当前 `common/ml_liquid.py` 与 `strategy.py` 范围内确认F1/F4-F7原通过项未回归。
- 上文保留初审问题证据与当时结论；以下定向复核状态取代初审最终门禁判定。

### 修复复核表

| 编号 | 初审级别 | 逐函数回映核对 | 真实覆盖复核 | 复核判定 |
| --- | --- | --- | --- | --- |
| CA-A01 | major | `coverage_matrix.md:17-20`的F4、F5、F6、F7现均直接列出 `strategy.py:build_liquid_family`、`build_m3_model_manifest`、`train_liquid_model`、`train_liquid_family`，4个策略层公开函数无遗漏。 | `strategy.py:553-560`逐一构造四模型；`563-595`汇总四模型manifest；`606-676`训练指定模型并产检查点/预测；`679-694`遍历四模型统一训练。四项均真实覆盖F4-F7。 | **resolved / pass** |
| CA-A02 | major | `coverage_matrix.md:17-20`的F4-F7现均直接列出 `common/ml_liquid.py:summarize_liquid_wiring`、`assert_ncps_version`、`build_liquid_model_manifest`，3个公共公开函数无遗漏。 | `common/ml_liquid.py:240-272`按模型生成wiring证据；`275-282`核对ncps版本；`285-318`逐模型汇总来源、commit、license、版本、scope及wiring信息。三项均真实覆盖F4-F7。 | **resolved / pass** |

### 原通过项回归检查

| 要素 | 当前证据 | 结论 |
| --- | --- | --- |
| F1 | `common/ml_liquid.py:34-93`仍保留导数、欧拉单步和严格递增时间网格积分的完整计算链。 | pass |
| F4/F5 | `common/ml_liquid.py:189-210`仍按模型类型构造AutoNCP可选wiring并把LTC参数完整透传；无公式或参数路径变化。 | pass |
| F6/F7 | `common/ml_liquid.py:189-219`仍按全连接/AutoNCP区分CfC并透传mode及统一接口参数。 | pass |
| 统一适配与训练链 | `common/ml_liquid.py:221-237`仍返回统一 `SequenceRegressor`；`strategy.py:598-676`仍复用m2分段、训练、检查点与独立回测预测路径。 | pass |
| 证据与非私参边界 | `common/ml_liquid.py:285-318`及`strategy.py:563-640`仍将版本、commit、license、method_scope写入manifest及训练元数据。 | pass |

## 第1次定向复核结论

- CA-A01、CA-A02均已修复并关闭；7个公开函数全部按真实覆盖回映F4-F7。
- F1/F4/F5/F6/F7原通过的公式、参数、实现、统一训练适配和简化声明未见回归。
- 当前open issue：0项（critical 0 / major 0 / minor 0）。

verdict: pass
