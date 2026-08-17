# m2 实现忠实性审计

## 审计范围

- mode：code
- milestone：m2
- 案例：r002_liquid_neural_networks
- 本次仅审 `coverage_matrix.md` 中 milestone=m2 且 status=done 的 F2、F3 两行；不审 m1 已完成要素，也不提前裁决 m3 的 F4-F7 液态网络实现。
- 审读证据仅来自规格、覆盖矩阵、假设登记簿、本案例 `src/`、`common/ml_training.py` 及 m2 实际调用的 `common/ml_pipeline.py`；未读取 coder 完成汇报。
- 空壳检查：F2/F3 所列 `train_gru_baseline`、`build_gru_baseline` 均有完整可执行函数体，沿调用链的模型构造、训练、预测、检查点函数也均存在；未发现 `pass`、TODO 或 `NotImplemented` 空壳。

## 五维度总体核对

| 维度 | 独立核对内容 | 结论 |
| --- | --- | --- |
| 公式一致 | 核对GRU递推载体、最后时点隐藏状态、线性输出头、连续收益回归与逐样本MSE。 | F3以单向GRU最后一层最终隐藏状态接线性头，符合规格及AS2；MSE按全样本加权均值计算，符合AS9。通过。 |
| 参数一致 | 逐项核对输入6、隐藏64、1层、dropout=0、输出1、Adam、lr=1e-3、batch=512、epochs=100、patience=10、seed=42、min_delta=0、weight_decay=0。 | 配置、训练设置透传与实际算子一致；Adam beta/epsilon采用PyTorch默认值，符合AS15。通过。 |
| 实现位置真实 | 打开矩阵所列 `strategy.py:train_gru_baseline` 与 `strategy.py:build_gru_baseline`，并反查公共训练实现。 | 两处位置均真实且非空壳，调用链可达数据分段、模型工厂、训练、最佳模型恢复与样本外预测。通过。 |
| 代码反查 | 从 `strategy.py` 的m2公开函数反向映射F2/F3。 | `train_gru_baseline`回映F2、`build_gru_baseline`回映F3；公开函数 `build_m2_data_splits` 未被任何矩阵行直接映射，见CA-A01。 |
| 简化声明 | 对照AS2、AS9、AS10、AS15检查结构、标签、输入、训练细节及影响披露。 | m2当前所有结果敏感降级均有登记；设备自动选择、worker数等属于随检查点留痕的执行控制，不改模型公式或目标函数。通过。 |

## done 要素逐条核对

| 要素 | 公式一致 | 参数一致 | 实现位置真实 | 代码反查 | 简化声明 | 判定 |
| --- | --- | --- | --- | --- | --- | --- |
| F2 | `common/ml_training.py:31-39`以统一的 `[time,features]` 数据集协议提供连续标签；`145-162`把主干与统一线性输出头解耦；`358-403`以任意 `model_factory` 进入同一MSE/Adam训练路径。五模型可通过替换兼容主干或模型工厂复用同一非主干框架。 | `TrainingSettings`统一承载batch、学习率、轮数、早停、随机种子、损失和优化器；`60-74`强制MSE/Adam，`strategy.py:406-422`从同一集中配置透传。 | 矩阵所列 `strategy.py:443-498`真实存在，依次调用统一分段、通用训练器和通用预测器。 | 主入口可回映F2；但其调用的公开 `strategy.py:361-391 build_m2_data_splits`没有直接映射到F2/F3，见CA-A01。 | AS9登记五模型统一标签/MSE，AS10登记统一60日六通道输入，AS15登记统一训练与早停细节；m3液态主干的AS11参数尚未在本里程碑实现，本次不提前裁决。 | pass_with_issues（CA-A01） |
| F3 | `common/ml_training.py:111-142`用GRU处理序列并取 `hidden[-1]`；`145-162`以线性头输出连续收益，和规格“最后时间步隐藏状态经前馈网络降维拟合未来收益”一致。 | `config.py:109-140`逐项落实6/64/1/0/1、MSE、Adam、1e-3、512、100、10、42；`ml_training.py:128-135,398-403,413-442`实际按这些参数构造并训练。 | 矩阵所列 `strategy.py:394-403 build_gru_baseline`真实存在并调用 `common/ml_training.py:165-184 build_gru_regressor`。 | F3入口、GRU主干和线性头调用链闭环；未发现额外未映射的F3公开模型入口。 | AS2登记GRU结构与训练参数，AS9登记标签/MSE，AS10登记输入，AS15补充严格改善、Adam默认动量、weight_decay=0和回测隔离；代码元数据明确标为降级开源基线。 | pass |

## 重点独立核验

### 1. 五模型共享框架与主干可替换性

- `SequenceRegressionDataset`只约束序列窗口与连续标签，不依赖GRU类型（`common/ml_training.py:31-39`）。
- `SequenceRegressor`把任意返回 `[batch,hidden]` 的主干与统一线性输出头组合（`common/ml_training.py:145-162`）；`train_sequence_regressor`进一步只要求 `model_factory` 返回 `torch.nn.Module`（`358-379`），因此也允许后续主干使用适配器或自有统一回归封装。
- 数据加载、MSE、Adam、早停、检查点和预测均位于公共路径，不在GRU主干内分叉（`common/ml_training.py:219-240,358-494`）。这满足F2“仅主干不同、其余一致”的框架要求。
- F4-F7的具体ncps主干及适配器尚属m3 pending；本结论只确认框架具备可替换接口，不把未来四个模型视为已经实现或审计通过。

### 2. GRU结构与参数重算

| 项目 | 规格/假设值 | 配置值 | 实际算子 | 结论 |
| --- | --- | --- | --- | --- |
| 输入维度 | AS10六通道 | 6 | `nn.GRU(input_size=6)` | 一致 |
| 隐藏维度 | AS2=64 | 64 | `nn.GRU(hidden_size=64)` | 一致 |
| 层数 | AS2=1 | 1 | `nn.GRU(num_layers=1)` | 一致 |
| dropout | AS2=0 | 0.0 | `nn.GRU(dropout=0.0)` | 一致 |
| 输出 | 最终隐藏状态接线性头 | 1 | `hidden[-1] → Linear(64,1)` | 一致 |
| 损失 | AS9=MSE | mse | `nn.MSELoss(reduction="mean")` | 一致 |
| 优化器 | AS2/AS15=Adam | adam | `torch.optim.Adam` | 一致 |
| lr / batch | 1e-3 / 512 | 1e-3 / 512 | 训练器直接透传 | 一致 |
| epochs / patience | 100 / 10 | 100 / 10 | `range(1,101)`上限与连续10轮未改善停止 | 一致 |
| seed | 42 | 42 | Python、NumPy、Torch、DataLoader generator均设42 | 一致 |

- 独立按PyTorch单层GRU参数公式重算：输入权重 `3×64×6=1,152`，循环权重 `3×64×64=12,288`，两组偏置 `2×3×64=384`，GRU合计13,824；线性头 `64+1=65`，模型总参数应为 **13,889**。公共资源函数按 `parameter.numel()` 统计，可对该理论值留痕（`common/ml_training.py:340-355`）。

### 3. 验证集用途与回测隔离

- `train_sequence_regressor`的函数签名只接收训练集与验证集，不接收回测集（`common/ml_training.py:358-370`）。
- 训练loader打乱、验证loader不打乱；每轮训练更新后，验证仅在 `optimizer=None` 的推理上下文计算MSE（`382-420`）。没有验证集梯度更新、学习率调度或二次拟合。
- `strategy.py:454-463`只把train/validation传给训练器；最佳模型恢复完成后，才在`465-472`把backtest传给预测器。回测段不参与早停、epoch选择或调参。通过。

### 4. 早停、检查点与预测追溯

- `validation_loss < best_validation_loss - min_delta`且 `min_delta=0`实现严格改善；连续10轮未改善退出，并在训练结束加载内存中的最佳状态（`common/ml_training.py:424-446`）。
- 每次改善均原子写入模型状态、优化器状态、epoch、验证损失、完整训练设置和模型元数据（`299-322,430-438`）；`TrainingResult`保留 `checkpoint_path`，独立加载函数可回读epoch、验证损失、训练设置与模型元数据（`497-517`）。
- 回测预测器固定顺序、不打乱样本（`464-494`）；`strategy.py:473-489`先校验预测数与元数据行数一致，再保留 `stock_code/date/label/entry_date/exit_date/entry_tradable` 并追加模型名和预测值。`PreparedMLData.dataset`与元数据使用相同split过滤及reset顺序（`common/ml_pipeline.py:82-121`），行级对应关系成立。
- `M2Artifacts`把训练结果（含检查点）、逐epoch损失、预测表、模型配置与资源记录绑定在同一返回对象（`strategy.py:350-358,492-498`）。检查点和预测元数据可追溯。通过。

### 5. AS15新增训练细节覆盖

- 完整遍历训练集：loader设 `drop_last=False`，epoch循环遍历全部batch（`common/ml_training.py:219-240,258-289`）。
- 严格验证MSE改善、min_delta=0、patience=10、恢复最佳检查点：均与AS15一致（`424-446`）。
- seed=42确定性打乱：全局随机源与DataLoader generator均固定；训练打乱、验证及预测不打乱（`187-197,219-240,382-397,477-484`）。
- Adam默认beta/epsilon与weight_decay=0：构造器只显式传入lr和weight_decay，未覆盖PyTorch默认动量参数（`398-403`）。
- 回测仅在模型选择后预测：由训练器签名和调用顺序双重隔离。AS15已覆盖这些新增且会影响结果的训练细节，未发现未登记的core方法简化。

## issue 清单

| 编号 | severity | 证据定位 | 一句依据 | 处置要求 |
| --- | --- | --- | --- | --- |
| CA-A01 | major | `workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:15-16`；`src/r002_liquid_neural_networks/strategy.py:361-391` | m2公开函数 `build_m2_data_splits`负责三段数据接口和回测元数据对齐，但F2/F3实现位置均未直接回映该函数，构成策略层公开实现的矩阵映射缺口。 | 按实际覆盖关系把该函数回填至F2（必要时同时回填F3）的实现位置，或将其改为明确私有辅助函数并继续由已映射入口封装；修复后定向复审代码反查维度。 |

## 审计结论

- 已逐条核对m2全部2个done要素：F2、F3。
- 已检查维度：公式一致 / 参数一致 / 实现位置真实 / 代码反查 / 简化声明。
- 五模型共享训练框架具备真实的主干/模型工厂替换接口；本次不提前裁决m3的四个液态主干。
- GRU结构与训练参数完全落实AS2/AS9/AS10/AS15；验证集仅用于早停，回测段不参与调参，最佳检查点及预测元数据追溯链成立。
- 未发现critical问题或实现空壳；现有1项major仅为公开函数矩阵映射缺口。

## 第1次定向复核

- 复核模式：code。
- 复核边界：仅复核CA-A01的公开函数矩阵回映，并在当前 `strategy.py` 范围内确认F2/F3原通过项未受影响；未扩展审读到其他文件或m3实现。
- 上文保留初审issue证据与当时结论；以下定向复核状态取代初审最终门禁判定。

### 修复复核表

| 编号 | 初审级别 | 修复后证据 | 原通过项回归检查 | 复核判定 |
| --- | --- | --- | --- | --- |
| CA-A01 | major | `coverage_matrix.md:15`的F2实现位置现包含 `strategy.py:build_m2_data_splits`；`coverage_matrix.md:16`的F3实现位置也包含该公开函数。`strategy.py:361-391`函数真实存在，并由 `train_gru_baseline` 在`454`行实际调用。 | `strategy.py:394-403`仍按集中配置构造GRU；`406-422`仍完整透传统一训练设置；`443-498`仍保持train/validation训练、最佳模型完成后backtest预测及预测元数据对齐。F2/F3初审通过项未见回归。 | **resolved / pass**：公开m2数据分段函数已完成F2/F3双向回映。 |

## 第1次定向复核结论

- CA-A01已修复并关闭。
- F2/F3原通过的公式、参数、实现真实性、训练/回测隔离和追溯逻辑未受影响。
- 当前open issue：0项（critical 0 / major 0 / minor 0）。

verdict: pass
