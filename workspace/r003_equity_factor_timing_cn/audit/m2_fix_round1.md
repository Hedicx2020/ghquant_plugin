# m2 第1轮实现修复记录

- 修复轮次: round 1
- 修复依据: `audit/impl_audit_m2.md`、`output/r003_equity_factor_timing_cn/verify_report.md` 的 m2 章节
- 修改范围: `regime_model.py`、`spec/coverage_matrix.md`、本记录
- 未修改: m1代码、`factor_model.py`、`main.py`、`state.json`、`results/`、`common/`

## 一、审计问题逐项回应

### CA-A01：二级Logistic使用一级模型in-sample概率

- 修复位置: `src/r003_equity_factor_timing_cn/regime_model.py:fit_stacking_classifier`
- 修改内容:
  1. 在每个待拟合的Stacking训练集内部再次执行固定五折`TimeSeriesSplit`。
  2. 每个内部子折只在其训练索引上拟合中位数插补、标准化、训练集过采样及RF/SVC/GNB。
  3. 一级模型只对严格晚于内部训练索引的验证子折生成概率，形成OOF元特征。
  4. `TimeSeriesSplit`最前端没有更早训练历史的首段不进入元学习器；Logistic只拟合有OOF概率的后续行。
  5. 元学习器拟合后，一级预处理器和RF/SVC/GNB才在完整84月训练集上重训，用于正式目标月预测。
- 新增审计字段: `meta_oof_rows`、`meta_oof_total_rows`、`meta_oof_coverage`、`meta_oof_first_position`，进入滚动预测、外层折指标和逐月训练审计。
- 静态证据: Logistic拟合输入为`oof_meta[oof_mask]`与对应`meta_labels`；源码不存在用完整训练集一级in-sample概率拟合元学习器的路径。

### 验证失败：latest_training_assignment误计为116个月

- 修复位置: `src/r003_equity_factor_timing_cn/regime_model.py:summarize_regime_distribution`
- 修改内容: 先筛选`prediction_date`最大值对应的单个最新滚动窗，再统计该窗状态；不再对所有滚动窗按`regime_date`去重。
- 阻断断言: 最新窗行数及唯一目标月数必须同时等于配置的`train_window_months`，本案例为84；否则立即抛出异常。

### CA-A03：缺少肘部法候选K与inertia合同

- 修复位置: `src/r003_equity_factor_timing_cn/regime_model.py:calculate_elbow_diagnostics`
- 修改内容: 每个预测月基于其严格过去84月回撤窗计算K=2、3、4、5、6的K-Means inertia，并输出：
  - `prediction_date`
  - `train_start` / `train_end`
  - `k`
  - `inertia`
  - `inertia_reduction_from_previous_k`
  - `selected_k`
- 结果合同: `StageOneRegimeResult.elbow_diagnostics`；固定执行K仍为3，不因样本外结果改参。
- 覆盖矩阵: F2实现位置更新为真实函数`calculate_elbow_diagnostics`，状态保持`done`，验证列仍为空。

### CA-A02：项目uv环境缺少scikit-learn

- 外部状态: 主会话已同步项目`ml` extra，本轮未修改依赖文件。
- 本轮复核: `uv run --extra ml`实际导入`scikit-learn 1.9.0`，并在同一环境完成合成与真实受限烟测。

## 二、文件diff摘要

| 文件 | 修改摘要 |
| --- | --- |
| `src/r003_equity_factor_timing_cn/regime_model.py` | 严格时序OOF元学习、OOF覆盖审计、最新84月状态统计、K=2..6肘部数据合同、参数哈希口径更新 |
| `workspace/r003_equity_factor_timing_cn/spec/coverage_matrix.md` | F2实现位置改为肘部数据函数；m2各行保持done且验证列留空 |
| `workspace/r003_equity_factor_timing_cn/audit/m2_fix_round1.md` | 本轮逐项修复与烟测证据 |

## 三、冒烟记录

### 3.1 编译

- 命令口径: `python -m compileall`仅编译`regime_model.py`。
- 结果: 退出码0。

### 3.2 uv ML环境合成月频面板

- 环境: `UV_CACHE_DIR=/private/tmp/report_reproduce_uv_cache uv run --extra ml`，`scikit-learn=1.9.0`。
- 输入: 100个连续合成月、三档回撤、九个模型特征；仅预测最后1个月；为缩短烟测使用RF 12棵树，不改变正式默认500棵配置。
- 结果:
  - 正式84月拟合的元OOF覆盖为70/84，即0.833333；无前史的最前14行未进入Logistic。
  - 外层五折各自记录其内部OOF行数和覆盖率，验证折没有进入预处理或过采样。
  - `latest_training_assignment`三状态数量合计84、占比和为1。
  - 肘部合同返回K列表`[2, 3, 4, 5, 6]`，仅K=3的`selected_k=True`。

### 3.3 uv ML环境真实受限面板

- 输入: m1完整132月日历、股票数限制20；m2只预测2025-12一个月；为缩短烟测使用RF 8棵树。
- 结果:
  - m1月频公开面板形状为132×39。
  - m2正式训练窗为84行，元OOF覆盖70/84。
  - 最新训练状态数量合计84。
  - 肘部合同返回K=2至6共5行。
- 附带记录: 首次尝试将m1截为100个月时，既有m1下一月退出日历不足而在进入m2前中止；该问题不属于本轮授权文件，故未修改。随后改用完整月历、20股限制完成真实受限烟测。

## 四、本轮边界

- 未运行33个月正式全量第一阶段验证。
- 未生成或覆盖任何正式`results/`产物。
- 本记录只说明修复已实现并完成冒烟，不作门禁通过或复现达标结论；验证结论仍由verifier与check_gates给出。

