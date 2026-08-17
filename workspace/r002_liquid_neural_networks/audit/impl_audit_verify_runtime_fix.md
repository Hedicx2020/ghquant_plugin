# r002_liquid_neural_networks verify 运行修复独立增量审计

- 审计模式：`code`
- 审计对象：verify 运行时修复（DataLoader 批量取窗与逐模型严格指纹缓存）
- 审计原则：仅以当前规格、假设、源码和本审计亲自运行的测试为证据；`audit/verify_runtime_fix.md` 只作为待核声称索引，不采信其中结论或数值。
- 写入边界：未修改代码、规格、矩阵、假设、正式 output 或 `state.json`；动态测试全部写入 `/tmp/r002_auditor_runtime.sXdwx6`。

## 一、结论

本次增量修复通过独立审计。未发现 critical、major 或 minor issue，允许进入正式 verify 重跑。通过只表示运行修复在当前源码及小规模独立测试中满足忠实性与恢复合同，不预先宣布正式全样本运行成功，也不对最终复现指标作判断。

## 二、五维度逐项审计

### 1. 公式一致

- AS9 的标签仍为 T+1 至 T+21 前复权 VWAP 简单收益、五模型统一 MSE，规格依据见 `workspace/r002_liquid_neural_networks/assumptions.md:99-109`；配置仍为 `entry_offset=1`、`exit_offset=21`，见 `src/r002_liquid_neural_networks/config.py:61-70`。
- AS10 的输入仍为截至 T 日的 60×6 张量，见 `workspace/r002_liquid_neural_networks/assumptions.md:111-121` 与 `src/r002_liquid_neural_networks/config.py:30-58`。批量取窗仅将同一闭区间行索引向量化，单样本及批量接口分别见 `common/ml_pipeline.py:240-261`。
- AS19 的 split 归属仍要求 T、T+1、T+21 同段，窗口允许读取 split 起点前纯历史，训练预处理只拟合合格训练窗口覆盖行；依据见 `workspace/r002_liquid_neural_networks/assumptions.md:219-229`，实现见 `common/ml_pipeline.py:614-637`、`common/ml_pipeline.py:697-707`、`common/ml_pipeline.py:792-834`。
- 训练/验证仍严格拒绝非有限标签，回测预测只消费特征，见 `common/ml_training.py:267-299`、`common/ml_training.py:302-333`、`common/ml_training.py:508-538`。未发现标签筛选放松或 T/T+1/T+21 时点回归。

判定：通过。

### 2. 参数一致

- 正式默认参数仍为 hidden_size=64、单层 GRU、dropout=0、Adam、learning_rate=1e-3、batch_size=512、max_epochs=100、patience=10、seed=42、shuffle_training=True、num_workers=0，见 `src/r002_liquid_neural_networks/config.py:109-151`。
- 四个液态模型仍为固定 ncps 1.0.1 映射、units=64、AutoNCP sparsity=0.5、seed=22222、LTC ode_unfolds=6，见 `src/r002_liquid_neural_networks/config.py:154-198`。
- 五模型、10 档、20 路径、每 20 日调仓、T+1/T+21 和卖出费率 0.003 均未缩减，见 `src/r002_liquid_neural_networks/config.py:201-242`。
- 仅显式 `--synthetic-smoke` 将训练缩为 1 epoch 且强制 CPU；正式默认不走该分支，见 `src/r002_liquid_neural_networks/main.py:185-206`。`source_mode` 和 `formal_result` 同时进入指纹，见 `src/r002_liquid_neural_networks/main.py:240-264`。

判定：通过。

### 3. 实现位置真实

- 独立解析 `coverage_matrix.md`：35/35 行均为 `done`，逐一反查 134 个 `文件:符号` 定位，文件与符号全部存在；其中 124 个函数定位经 AST 反查均有实质函数体，无 `pass` 或 `NotImplementedError` 空壳。矩阵行见 `workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:9-43`。
- `strategy.py` 的公开函数均可回映矩阵要素：m1 数据与审计、m2 GRU、m3 液态族、m4 五模型预测及回测均已登记；函数位置见 `src/r002_liquid_neural_networks/strategy.py:83`、`:208`、`:271`、`:380`、`:413`、`:462`、`:549`、`:572`、`:582`、`:625`、`:698`、`:727`、`:795`、`:895`。
- 本次没有发现不存在或空壳的实现位置，因此不触发 `not_found` 判定，也无需回退矩阵状态。

判定：通过。

### 4. 代码反查

- 共享底板只在 `PreparedMLData.__post_init__` 构造一次；split 数据集仅保存源样本位置，见 `common/ml_pipeline.py:96-129`。`__getitems__` 按 DataLoader 已给索引顺序取窗，不排序、不自行随机，见 `common/ml_pipeline.py:248-261`。
- `_build_loader` 仍由 PyTorch `shuffle`、固定 generator seed 和 `drop_last=False` 控制；仅对声明支持的 dataset 使用专用 collate，见 `common/ml_training.py:223-264`。
- 缓存全局身份覆盖完整 m1-m5 配置、8 个正式源文件内容 SHA256+size、7 个关键数据/模型/训练源码、环境版本以及样本键/split/窗口/label/entry/exit，见 `src/r002_liquid_neural_networks/main.py:76-85`、`:209-264` 与 `src/r002_liquid_neural_networks/runtime_cache.py:100-203`。
- 完成态写入只接受一维有限预测，保存最佳模型 state、history、resource、模型配置和检查点内容 SHA；临时文件完成 `flush+fsync` 后原子 replace，见 `src/r002_liquid_neural_networks/runtime_cache.py:210-267`。加载时 schema、complete、指纹、模型名、检查点 SHA、严格 state_dict、预测维度/有限性/长度均逐项校验，不匹配显式异常，见 `src/r002_liquid_neural_networks/runtime_cache.py:270-345`。
- 恢复后按当前 backtest 原序重建 stock/date/label/entry/exit/tradable，见 `src/r002_liquid_neural_networks/main.py:280-340`；五模型合并再次严格比较键、label 值与 NaN 位置，见 `src/r002_liquid_neural_networks/strategy.py:727-792`。
- 缓存只替代单模型训练与完整回测预测；五模型重组、m4 回测、特征重要性、相关性、metrics、comparison、Excel、PNG 仍继续执行，见 `src/r002_liquid_neural_networks/main.py:890-1080`。异常写入 `exit=1` 后重新抛出，不静默吞掉，见 `src/r002_liquid_neural_networks/main.py:1105-1124`。

判定：通过。

### 5. 简化声明

- 本轮新增内容是执行层等价批量取窗及中间态恢复，不改变策略、样本、模型、交易或指标口径；未发现需要新增假设却未登记的 method/data/trading/output 简化。
- 正式与合成的参数差异已由显式 CLI 分支、`synthetic_smoke`、`source_mode` 和 `formal_result` 标记隔离，不会被误当成正式参数。
- 检索研报参考数值，仅出现在 `M5ReferenceConfig` 及 reporting/comparison 对照装配；未进入特征、标签、模型预测、分组、交易或复现指标计算。定位见 `src/r002_liquid_neural_networks/config.py:247-295`、`common/ml_reporting.py:289-380`、`src/r002_liquid_neural_networks/main.py:940-985`。

判定：通过。

## 三、独立动态测试记录

### 1. 60×6 旧新等价、顺序与共享底板

- 环境：PyTorch 2.12.1、NumPy 2.5.1、pandas 3.0.3。
- 本审计另构造 8 条非连续起点的 60×6 窗口，逐条以旧式 `iloc+slice.copy` 参考实现重算；新 `__getitems__` 的 features 形状为 `[8,60,6]`，features 与 labels 均逐位相等。
- seed=42、batch=3、shuffle=True 下，旧新 DataLoader 三批大小 `[3,3,2]`，每批 features/labels 逐位一致；预测用 `shuffle=False` 保持原样本顺序。
- 修改批量返回数组及单样本返回数组后，共享 `_features` 底板逐位未变；split 间不存在通过返回值反写共享底板的数据污染。
- 项目定向测试也由本审计亲自运行：`4 passed in 18.62s`。

判定：通过。

### 2. label 严格性与时点边界

- 训练/验证非有限 label 在 `_unpack_batch` 被强制拒绝；回测预测 `_unpack_features` 不读取 label。
- 独立 fixture 保留 backtest NaN label 后，预测数量与 backtest 样本数一致且预测全有限。
- AS19 分段、训练窗口 fit mask 和 T/T+1/T+21 代码路径不位于本轮批量/缓存分支内，且静态逐行反查未发现条件放松。

判定：通过。

### 3. 指纹、拒绝与部分态

- 正式源文件清单独立计数为 8 个，总字节数 1,958,759,450；逐文件全内容 SHA256 独立运行耗时 1.116 秒，8 个 hash 均不同。
- 独立交换两行 label 的 NaN 位置后 runtime identity 改变；仅改变 `source_mode=formal/synthetic` 也改变 identity。
- 只有孤立临时文件而目标完成态不存在时，加载返回 cache miss；截断的目标完成态文件被显式 `RuntimeCacheError` 拒绝，未被视为完成。
- seed 从 42 改为 43 时，现存 GRU 完成态在恢复点显式抛 `RuntimeCacheFingerprintError`、进程 exit=1，expected/actual 指纹均输出；未静默训练或覆盖。

判定：通过。

### 4. 五模型首写、恢复与 m4/m5 全链路

- 在独立 `/tmp` 目录执行合成全链路首跑：GRU、LTC、NCP（LTC）、CFC、NCP（CFC）均写入完成态并继续生成 m4/m5 全部输出，末态 `exit=0`。
- 同目录第二次运行五模型均从缓存恢复，仍继续执行相关性、指标、图表、Excel和明细输出，末态 `exit=0`。
- 首跑与恢复跑的 `predictions.parquet` SHA256 均为 `13045a2c899f7e7682eebe5906d66db43f6f98c453f8f9c37f2b09917254080d`，证明恢复后的五模型预测、键序和下游预测明细逐位稳定。
- 合成 metrics 明确记录 `synthetic_smoke=true`、`formal_result=false`；缓存身份也按 source_mode 隔离。旧单独 `checkpoints/gru.pt` 没有对应 `*.complete.pt` 时只能形成 cache miss，不能进入恢复分支，见 `src/r002_liquid_neural_networks/main.py:742-830`。

判定：通过。

### 5. 性能与内存诚实边界

- 可重复基准均遍历 120,000 条 60×6 窗口、seed=42、num_workers=0、固定 batch=512：旧路径 3.2269 秒、37,188 样本/秒、遍历总增量峰值 13,729,792 字节；新路径 0.07373 秒、1,627,537 样本/秒、遍历总增量峰值 4,931,584 字节；两者 checksum 同为 `-452.1720733642578`。本机该数据加载路径吞吐约 43.8 倍，不能外推为完整模型训练倍数。
- 将优化路径 batch 从正式固定的 512 人为放大到 8192，遍历总增量峰值升至 29,605,888 字节，确认高级索引临时数组按 batch 线性放大。正式 batch=512 时单个 float32 特征批理论主体约 512×60×6×4=737,280 字节，另有行索引和 tensor 包装，当前配置未出现异常峰值。
- 五个 float64 预测数组在全量 backtest 下仍可能合计约 `5×N×8` 字节；五模型合并、20 路径账本、完整梯度重要性和 Parquet 输出仍是后段内存/耗时风险。该风险由缓存降低重训代价但没有消除，因此正式 verifier 仍须记录真实峰值与终态。本结论不承诺正式运行时长上限。
- 源文件 SHA256 本机热/本地读取实测约 1.116 秒；它是每次启动固定 I/O 成本，未构成当前瓶颈，但跨磁盘环境不可直接套用该耗时。

判定：通过；保留非阻断运行风险观察。

## 四、issue 清单

无。未发现需要编号为 `CA-Axx` 的 critical、major 或 minor issue。

## 五、已检查维度清单

- [x] 公式一致：AS9、AS10、AS19、训练/验证有限 label、backtest NaN label 预测、T/T+1/T+21。
- [x] 参数一致：m1-m5 正式默认、五模型、batch/epoch/patience/seed、10 档/20 路径/交易费用，及合成分支隔离。
- [x] 实现位置真实：35/35 done 行、134 个定位、124 个函数体，无空壳/不存在。
- [x] 代码反查：DataLoader 顺序、共享底板、缓存 identity、原子完成态、显式拒绝、恢复重建、m4/m5 全链路、异常传播。
- [x] 简化声明：无新增未登记策略简化；参考值未进入计算；未发现范围缩水或硬编码回灌。

verdict: pass

## 六、整改复核（CDX-VRF-01 至 CDX-VRF-04）

> 本节为外部审计整改后的最后增量复核；如与前文缓存 identity 范围表述冲突，以本节当前代码复核为准。特别更正：当前 runtime identity 只覆盖缓存模型预测所依赖的 m1-m3 配置，不再包含每次恢复后都会重新计算的 m4-m5 配置。

### CDX-VRF-01：data_loader 与实际标准化特征底板指纹

- `common/data_loader.py` 已进入关键源码清单，见 `src/r002_liquid_neural_networks/main.py:226-237`。
- `PreparedMLData` 将训练/预测共用的实际 float32 底板设为只读，并由 `standardized_feature_values` 原样暴露给指纹函数，见 `common/ml_pipeline.py:96-120`。
- runtime identity 直接接收该实际底板及列名，见 `src/r002_liquid_neural_networks/main.py:248-258`；特征 hash 按最多 100,000 行分块，规范为 little-endian float32、C 顺序并统一 NaN 位型，见 `src/r002_liquid_neural_networks/runtime_cache.py:155-199`、`:202-240`。
- 现有测试独立覆盖 `data_loader.py` 内容变化、单个实际特征 float32 值变化、NaN 位型及大小端规范化，见 `src/r002_liquid_neural_networks/test_runtime.py:368-424`。

判定：通过。

### CDX-VRF-02：缓存配置范围限定为 m1-m3

- `_build_runtime_identity` 的签名与入参仅含 m1、m2、m3，manifest 的 `configs` 也仅写入这三层，见 `src/r002_liquid_neural_networks/main.py:240-258`。
- m4/m5 在模型恢复后完整重算，不影响缓存内模型 state 与预测；因此不把 m4/m5 配置纳入模型完成态 identity 可避免输出或回测层变化导致无必要重训，同时不绕过 m4/m5 当前代码。
- 现有测试反查函数签名，明确断言不存在 m4/m5 参数，见 `src/r002_liquid_neural_networks/test_runtime.py:426-430`。

判定：通过；本节取代前文“完整 m1-m5 配置进入缓存身份”的旧描述。

### CDX-VRF-03：四类显式拒绝测试

- 模型名不一致：显式抛 `RuntimeCacheFingerprintError`，测试定位 `src/r002_liquid_neural_networks/test_runtime.py:320-327`。
- 最佳检查点内容被篡改：显式抛 `RuntimeCacheError`，测试定位 `src/r002_liquid_neural_networks/test_runtime.py:329-339`。
- 完成态文件截断：安全读取失败并显式抛 `RuntimeCacheError`，测试定位 `src/r002_liquid_neural_networks/test_runtime.py:341-351`。
- 模型配置/seed 导致指纹变化：显式抛 `RuntimeCacheFingerprintError`，测试定位 `src/r002_liquid_neural_networks/test_runtime.py:353-365`。
- 当前加载实现对应拒绝点见 `src/r002_liquid_neural_networks/runtime_cache.py:324-374`；没有捕获后静默训练或降级恢复。

判定：通过。

### CDX-VRF-04：resource 来源贯通

- 新训练资源行在 `_resource_row` 明确写入 `restored_from_cache=False`，见 `src/r002_liquid_neural_networks/main.py:429-474`；该完整 resource row 同模型完成态一起保存，见 `src/r002_liquid_neural_networks/runtime_cache.py:264-321`。
- GRU 恢复时复制缓存 resource row 并置 `restored_from_cache=True`，run_log 同时记录 `resource_record_source=completed_model_cache`，见 `src/r002_liquid_neural_networks/main.py:762-777`；四个液态模型采用同一处理，见 `src/r002_liquid_neural_networks/main.py:840-855`。
- 新训练分支 run_log 明确记录 `resource_record_source=fresh_training_measurement`，见 `src/r002_liquid_neural_networks/main.py:789-818`、`:868-899`。
- 五模型 resource 行统一合并为 `resources_frame` 后继续传入 metrics、comparison、chart data、detail/output，见 `src/r002_liquid_neural_networks/main.py:921`、`:988`、`:1023`、`:1053`、`:1059`；恢复来源标记不会在下游装配前丢失。
- 缓存现有测试逐帧核对 resource row 写入与恢复一致，见 `src/r002_liquid_neural_networks/test_runtime.py:253-294`。

判定：通过。

### 整改测试结果与 issue

- 执行命令：`MPLCONFIGDIR=/tmp/r002_audit_mpl .venv/bin/python3 -m pytest -q src/r002_liquid_neural_networks/test_runtime.py`
- 结果：`4 passed in 2.67s`。
- issue：无。未发现新增 critical、major 或 minor issue。
- 剩余风险：特征底板 hash 增加一次线性内存读取成本；仅分块处理、不会复制整张底板。正式全样本训练、五模型预测合并及 m4/m5 后段耗时/内存风险仍按前文披露，本次四项整改不对正式运行时长作保证。

verdict: pass
