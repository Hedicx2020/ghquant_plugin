# r002_liquid_neural_networks 正式 verify 运行时修复记录

> 角色边界：本文只记录 quant-coder 的静态审查、小规模剖析、实现与冒烟证据；不据此宣布 code_audit、verify 或门禁通过。正式数值结果与通过判定仍归 quant-verifier / check_gates。

## 1. 失败现场与根因证据

- 正式命令：`.venv/bin/python3 -m src.r002_liquid_neural_networks.main`。
- 已知现场：2026-07-17 06:11 启动后运行超过15小时，无 `exit=0/1` 即消失；正式目录只留下 `run_log.md` 和 `checkpoints/gru.pt`，后者记录 epoch 1 / validation loss 0.0162463；没有 metrics、comparison、Excel 或 PNG。运行中 CPU 曾约300%至400%，进程内存最高约22GB；GRU首个epoch约14分钟。训练、验证、回测输入上界分别约489万、240万、576万样本。
- 本次修复前的 `PanelWindowDataset.__getitem__` 对每个样本执行一次 `samples.iloc[index]`、字符串列定位、Python标量转换、60×6窗口 `.copy()`，随后由DataLoader逐样本再拼batch。按训练+验证约729万样本估算，每个epoch需要729万次pandas行索引；100 epoch理论上界为7.29亿次。
- 修复前每次构造 train / validation / backtest 数据集都会分别把完整特征面板转换并复制成float32数组；所选split的全宽samples DataFrame还会在筛选和数据集构造时重复复制。五个模型重复构造这些对象，是正式运行的显著内存放大器。
- 修复前只有“验证损失改善时写最佳epoch检查点”，没有“模型训练已结束且全量回测预测已完成”的完成态。因此即使GRU已经完整结束，后续液态模型或进程失败后也无法证明GRU预测完整，重跑只能从GRU开始；五个模型全部完成前没有可安全恢复的模型级边界。
- `main.py` 会在训练阶段持续保留每个模型含重复stock/date/label元数据的完整预测DataFrame。回测段约576万行时，五份重复元数据会继续抬高训练阶段常驻内存。本轮已改为模型完成并落缓存后只暂存一维float64预测数组，进入五模型合并前再按同一元数据重建。

## 2. 改动文件与接口

### `common/ml_pipeline.py`

- `PreparedMLData.__post_init__`：只做一次float32特征底板转换，并缓存完整样本的窗口起止行、label数组；所有split和所有模型共享同一底板。
- `PreparedMLData.dataset`：不再复制所选split的全宽samples DataFrame，只保存该split在原样本表中的位置数组。
- `PanelWindowDataset.__getitem__`：保留原单样本接口与数值语义，但改从预提取数组取起止行和label，不再逐样本执行pandas `iloc`。
- `PanelWindowDataset.__getitems__`：接收DataLoader已经决定好的batch索引，严格按给定顺序用 `starts[:, None] + 0..59` 一次取出 `[batch,60,6]`；不自行排序、不自行shuffle。
- `PanelWindowDataset.metadata` / `samples`：保留兼容接口，metadata仍指向同一原样本行；只有显式访问 `samples` 时才物化split元数据。

### `common/ml_training.py`

- `_build_loader`：仍使用原DataLoader、原seed generator、原RandomSampler / SequentialSampler和原drop_last=False；只有数据集显式声明 `supports_prebatched_fetch` 时切换到一次转换整批NumPy数组的collate函数。
- `_collate_prebatched_arrays`：每批只执行一次 `torch.from_numpy(features/labels)`，形状和样本数不符立即报错。训练/验证的有限label检查仍由原 `_unpack_batch` 执行；预测仍只消费features，故回测缺label不被筛掉。

### `src/r002_liquid_neural_networks/runtime_cache.py`

- `build_runtime_identity`：模型完成态身份只覆盖实际生成训练与预测的m1/m2/m3配置，不包含每次都完整重算的m4/m5配置；m4/m5参数变化本身不会淘汰模型缓存。身份同时覆盖正式8个源Parquet的完整内容SHA256与size、`common/data_loader.py`及关键模型/数据/训练源码SHA256、Python/PyTorch/NumPy/pandas/ncps版本、完整样本表的键/split/窗口起止/label/entry/exit分块hash。合成冒烟明确标记 `source_mode=synthetic_smoke`，不能与正式缓存互认。
- `_feature_manifest`：直接哈希 `PreparedMLData.standardized_feature_values`，即所有split/模型实际共享并消费的float32标准化特征底板；manifest记录shape、dtype、六列顺序、NaN计数和SHA256。正式小端且无NaN路径只建立最多10万行的view并把memoryview交给hashlib，不复制整表；大端输入仅复制当前分块转为little-endian float32，NaN仅复制当前分块并统一为quiet-NaN `0x7fc00000`，保证NaN payload和机器字节序不改变同值hash。
- `derive_model_fingerprint`：在全链路身份上追加模型名和该模型配置，形成每模型唯一指纹。
- `write_completed_model_cache`：仅接受一维有限的完整预测；同时保存最佳模型state、完整history、训练资源记录、模型配置和预测值。要求最佳检查点已存在并保存其内容SHA256；同目录临时文件 `fsync` 后用原子replace发布，只有 `complete=true` 的完整文件可恢复。
- `load_completed_model_cache`：缓存不存在时返回None并训练；缓存存在时必须schema、complete、模型名、完整指纹、检查点SHA、模型state、预测长度全部一致。任一指纹不符抛 `RuntimeCacheFingerprintError`，不静默忽略、不降级为旧预测。

### `src/r002_liquid_neural_networks/main.py`

- 正式配置、样本区间、五模型集合、batch=512、max_epochs=100、patience=10、seed=42、数据过滤、标签、组合与指标口径均未改变。
- 每个模型按“严格恢复；否则训练→全量回测预测→资源记录→原子完成态缓存”的顺序执行，并立刻在run_log记录 `written` 或 `restored`。
- `_resource_row` 新增 `restored_from_cache` 布尔列：新训练测量为false，恢复缓存为true；run_log同步写 `resource_record_source=fresh_training_measurement` 或 `completed_model_cache`。该列随原resource DataFrame进入CSV、metrics、Excel和Parquet链路，不替换任何原资源口径。
- 恢复时重新实例化原模型并严格加载state；按当前 `prepared.samples` 的backtest原序重建stock/date/label/entry/exit/tradable元数据，再填入缓存预测。随后仍调用 `assemble_m4_prediction_panel`，由原逻辑对五模型集合、键、label值及NaN位置逐项精确断言。
- 训练阶段只保留每模型一维float64预测值，释放重复预测元数据；五模型训练/恢复完成后才重新构造预测表。最终m4/m5、完整五模型合并、20路径组合、metrics/comparison/Excel/PNG均仍从完整五模型链生成，缓存本身不被当作最终结果。

### 定向测试与基准

- `src/r002_liquid_neural_networks/test_runtime.py`：覆盖旧新窗口逐值/逐label、metadata键、完整Sampler shuffle序列、三split样本数、训练/验证有限label、回测缺label仍预测、缓存缺失/首写/恢复/错指纹、checkpoint内容篡改、截断cache、错误expected_model_name、formal/synthetic source_mode互斥、模型state/history/resource/预测/键/label NaN恢复合同，以及源文件、`data_loader.py`、m1-m3配置、源码、样本或单个标准化feature变化引起身份变化；另断言m4/m5不进入模型缓存配置身份。
- `src/r002_liquid_neural_networks/benchmark_runtime.py`：独立进程运行旧/新窗口路径的小规模吞吐与ru_maxrss基准，不训练模型、不读取或写入正式output。

## 3. 数值语义不变断言

- 60×6窗口：旧路径和新批量路径逐值最大误差为0；label最大误差为0；同一固定模型经旧/新预测loader得到的预测数组逐值一致。
- shuffle：两条路径继续使用同一个DataLoader generator与RandomSampler；seed=42时逐batch features与labels完全相同，257/257样本顺序一致。
- split：定向测试中train / validation / backtest各43条，与修复前选择条件一致。
- label用途：train与validation所有label严格有限；backtest保留1个NaN label，预测仍输出43/43条且全部预测有限。
- 缓存恢复：模型state逐tensor一致，float64预测逐值一致，history与resource合同一致；重建的stock/date键、label值与NaN位置与当前backtest元数据完全一致。
- 未来函数约束未动：特征窗口截至T日、训练预处理只拟合训练窗口、训练/验证label有限、回测缺label仍可预测、T日信号T+1执行等CDX-C-01/02相关实现均未放松。

## 4. 小规模测试与基准结果

### 回归测试

命令：

```bash
MPLCONFIGDIR=/tmp/r002_mpl .venv/bin/python3 -m pytest -q src/r002_liquid_neural_networks/test_runtime.py
```

增量审计修复后最终复跑结果：`4 passed in 2.66s`。

### DataLoader吞吐 / 峰值RSS基准

命令：

```bash
MPLCONFIGDIR=/tmp/r002_mpl .venv/bin/python3 -m src.r002_liquid_neural_networks.benchmark_runtime --mode legacy --samples 120000 --batch-size 512
MPLCONFIGDIR=/tmp/r002_mpl .venv/bin/python3 -m src.r002_liquid_neural_networks.benchmark_runtime --mode optimized --samples 120000 --batch-size 512
```

两次均遍历12万条60×6窗口、num_workers=0、seed=42，checksum均为 `-452.1720733642578`：

| 路径 | 耗时 | 吞吐 | dataset构造增量峰值RSS | 完成遍历总增量峰值RSS |
| --- | ---: | ---: | ---: | ---: |
| 修复前模拟 | 3.2034秒 | 37,460样本/秒 | 5,898,240字节 | 12,599,296字节 |
| 修复后 | 0.07827秒 | 1,533,191样本/秒 | 1,802,240字节 | 4,456,448字节 |

- 纯取窗/拼batch吞吐约40.9倍；dataset构造增量峰值约下降69%，完成遍历总增量峰值约下降65%。
- 该倍数只适用于DataLoader数据路径，不能外推为完整训练加速倍数。GRU/LTC/CfC前后向、验证和模型结构计算仍占主要时间。按729万训练+验证样本和旧基准吞吐粗算，修复前纯数据路径约195秒/epoch；新路径可大幅削减这部分，但不改变模型计算量。

### 合成全链路首写/恢复/拒绝冒烟

增量审计修复后的命令均显式使用 `/tmp/r002_runtime_fix_smoke_v2`，未写正式output：

```bash
MPLCONFIGDIR=/tmp/r002_mpl .venv/bin/python3 -m src.r002_liquid_neural_networks.main --synthetic-smoke --output-dir /tmp/r002_runtime_fix_smoke_v2
MPLCONFIGDIR=/tmp/r002_mpl .venv/bin/python3 -m src.r002_liquid_neural_networks.main --synthetic-smoke --output-dir /tmp/r002_runtime_fix_smoke_v2
MPLCONFIGDIR=/tmp/r002_mpl .venv/bin/python3 -m src.r002_liquid_neural_networks.main --synthetic-smoke --seed 43 --output-dir /tmp/r002_runtime_fix_smoke_v2
```

- 第一次：五个模型均记录 `written` 与 `resource_record_source=fresh_training_measurement`，完整走到m5并以 `completed_without_verifier_judgement` 结束；`model_resource_log.csv` 五行 `restored_from_cache=false`。
- 第二次：五个模型均记录 `restored` 与 `resource_record_source=completed_model_cache`，恢复后仍完整走到m5；资源CSV五行 `restored_from_cache=true`，该字段也进入metrics，Excel/Parquet链路未报错。
- 第三次：seed改变后在GRU恢复点抛 `RuntimeCacheFingerprintError` 并exit 1，expected/actual指纹明确不同，没有混用或覆盖旧缓存。
- 以上是合成接口冒烟，不是正式数据结果，不可用于任何复现达标结论。

## 5. 正式重跑方式

保持原正式命令不变：

```bash
.venv/bin/python3 -m src.r002_liquid_neural_networks.main
```

- 首次使用本修复时，旧 `checkpoints/gru.pt` 不是模型完成态缓存，不能证明训练与全量预测都完成，因此不会被当作可恢复模型；GRU会按原参数重新训练。
- 每个模型真正完成后会新增 `output/r002_liquid_neural_networks/results/runtime_cache/{model}.complete.pt`。若后续模型或m4/m5失败，原命令重跑会在指纹完全一致时跳过已经完成的模型训练与全量预测。
- 若训练/预测相关源码、m1/m2/m3或当前模型配置、任一正式源Parquet内容、实际标准化float32特征值、环境版本、样本键/label位置或对应最佳检查点发生变化，现存缓存会被拒绝。m4/m5配置不进入模型缓存身份，因为恢复后这两阶段始终完整重算。应由主会话明确处理旧缓存或指定新的输出位置，不应在正式运行中静默覆盖。

## 6. 未消除风险与正式目录边界

- 五类模型的前后向计算量、100 epoch上限与10轮早停均未改变；DataLoader优化不能保证每个模型训练时间达到某个固定上限。
- 完整五模型预测合并约2880万行，m4多路径账本、m5全样本梯度重要性和全量Parquet仍可能形成新的内存/耗时峰值；本轮缓存使这类后段失败后至少不必重训已完成模型，但正式峰值仍须verifier记录。
- 正式源文件内容hash约需顺序读取约1.9GB本地Parquet；这是每次启动的额外I/O成本，用于保证可续跑不混入变化数据，相对模型训练耗时较小，但仍应在正式run_log时间线上披露。
- 标准化特征底板还会被顺序读取一遍计算SHA256，但不创建整表副本；哈希耗时与内存带宽相关，应由verifier在正式时间线记录。
- 代码身份仍保守地包含整个 `main.py` 和 `strategy.py` 文件：即使只修改其中与m4/m5输出有关的源码，文件SHA变化也会淘汰模型缓存。没有采用脆弱的函数源码截取hash；“m4/m5配置值变化不失效”与“关键源码文件变化保守失效”是两条不同边界。
- 缓存依赖对应最佳检查点的内容SHA；检查点缺失或内容变化会明确拒绝恢复，即使完成态文件自身仍存在。
- 本轮未修改 `workspace/r002_liquid_neural_networks/spec/coverage_matrix.md`：原D/F/B/R/SA实现位置均仍真实，新增代码只优化执行与恢复机制，不新增或改写任何研报要素口径。
- 本轮未追加assumptions：没有新增策略、参数、数据、标签、交易或指标简化；运行缓存和等价批量取窗属于实现层优化。
- 正式目录保持原失败现场未触碰：`results/run_log.md` mtime仍为2026-07-17 06:11:59，`results/checkpoints/gru.pt` mtime仍为2026-07-17 06:26:50，`verify_report.md` mtime仍为2026-07-17 05:11:02；未生成、覆盖或清理任何正式metrics/comparison/Excel/PNG。
