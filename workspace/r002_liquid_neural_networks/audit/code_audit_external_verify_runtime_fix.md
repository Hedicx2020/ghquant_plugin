静态审读已完成全部六个维度（本会话无 shell 执行权限，未运行动态测试；等价性判断基于代码语义与已有对拍测试的静态核验）。结论：批量取窗与旧路径逐值/顺序等价性成立，缓存拒绝与原子写机制完整，恢复后 m4/m5 全量重算不绕过指标链；发现 1 项 major（指纹遗漏 `common/data_loader.py` 且特征数值不入指纹）与 3 项 minor。

```json
{
  "checkpoint": "verify_runtime_fix_code_audit",
  "verdict": "pass_with_issues",
  "dimensions_checked": [
    {"dimension": "数值与顺序等价", "result": "no_findings"},
    {"dimension": "未来函数与标签边界", "result": "no_findings"},
    {"dimension": "缓存指纹与原子性", "result": "CDX-VRF-01, CDX-VRF-02, CDX-VRF-03"},
    {"dimension": "恢复后完整链路", "result": "CDX-VRF-04"},
    {"dimension": "正式隔离与异常处理", "result": "no_findings"},
    {"dimension": "性能与内存风险", "result": "no_findings"}
  ],
  "findings": [
    {
      "id": "CDX-VRF-01",
      "severity": "major",
      "location": "src/r002_liquid_neural_networks/main.py:226-237, main.py:76-86",
      "description": "运行身份的源码指纹清单 _runtime_code_files 只含 main/config/strategy/runtime_cache/ml_pipeline/ml_training/ml_liquid 七个文件，遗漏 common/data_loader.py；而 strategy.load_m1_inputs 直接依赖该文件的 load_stock_price_forward/load_st_data/load_suspend_status/load_limit_status/load_trade_calendar 读取与清洗逻辑（strategy.py:16-22）。同时样本指纹 CACHE_SAMPLE_COLUMNS 仅覆盖 stock_code/date/split/panel_row_start/panel_row_end/label/entry_date/exit_date 八列元数据，不含标准化后特征面板数值。两者叠加形成缺口：若未来对 data_loader.py 做仅改变特征数值、不改变样本键/label/窗口行号的改动（例如对 OHLC 列的数值清洗或类型处理，close/volume/turn_value 不动则 label 与窗口索引均不变），指纹不变，旧模型完成态缓存会被接受，恢复的预测与新特征管线不一致。当前代码状态下不会触发（8 个源 Parquet 内容 SHA 与其余七个源码文件已覆盖绝大多数变更路径），属于防御性覆盖不足而非现行错误恢复，故判 major 而非 critical。",
      "suggestion": "将 common/data_loader.py 加入 _runtime_code_files；更强的做法是把 PreparedMLData._feature_values（float32 特征底板）的分块 SHA256 并入 runtime identity，使特征数值内容直接参与指纹。",
      "confidence": "high"
    },
    {
      "id": "CDX-VRF-02",
      "severity": "minor",
      "location": "src/r002_liquid_neural_networks/main.py:250-264",
      "description": "runtime identity 的 configs 把 m4（组合回测）与 m5（纯输出/展示配置：excel_detail_row_limit、图表颜色、DPI、文件名等）全部纳入每个模型完成态指纹，而模型训练与回测段预测只依赖 m1-m3。verify/迭代阶段常见的输出层参数微调（如改一个行数上限）会作废全部五模型缓存，且指纹不符是抛 RuntimeCacheFingerprintError 中止而非重训，需人工清理后从零重训（单轮可能十余小时）。方向保守、无正确性风险，但实质削弱本轮'模型级可续跑'目标。",
      "suggestion": "把模型完成态指纹的配置范围收窄为 m1/m2/m3 加该模型自身配置；m4/m5 每次运行本就完整重算，其配置变化不应作废训练缓存。若保持现状，应在文档明确'调整 m4/m5 配置将强制全量重训'。",
      "confidence": "high"
    },
    {
      "id": "CDX-VRF-03",
      "severity": "minor",
      "location": "src/r002_liquid_neural_networks/test_runtime.py:198-356",
      "description": "定向测试覆盖了缓存缺失/首写/恢复/错指纹（配置变化）四种路径，但未覆盖 runtime_cache.py 中其余显式拒绝分支的直接回归：(a) 检查点内容 SHA 不符（runtime_cache.py:307-308）；(b) 缓存文件损坏/截断触发 RuntimeCacheError（runtime_cache.py:284-288）；(c) expected_model_name 不符（runtime_cache.py:300-303）；(d) synthetic 与 formal 的 source_mode 互斥仅由指纹机制间接保证，无直接断言。'部分/损坏缓存显式拒绝'合同的测试证据不完整，机制代码本身经静态审读无误。",
      "suggestion": "补四个小测试：篡改 checkpoint 内容后断言拒绝、截断缓存文件后断言 RuntimeCacheError、错误模型名断言拒绝、source_mode=synthetic_smoke 与 formal_local_parquet 两个 identity 的模型指纹互不相认。",
      "confidence": "high"
    },
    {
      "id": "CDX-VRF-04",
      "severity": "minor",
      "location": "src/r002_liquid_neural_networks/main.py:771, main.py:839",
      "description": "恢复路径把缓存内保存的历史 resource_row（训练当时的 CPU RSS/设备内存观测）原样并入本次运行的 model_resource_log.csv 与 comparison 的 R2 行，行内无 restored_from_cache 标记列。R2 已按 AS20 判 unverifiable/pass=null，不影响达标判定；恢复运行报告训练时观测也属诚实（本次未重训无新观测），且 run_log 的 restored 行可交叉推断，但资源日志单独阅读时无法区分'本次训练观测'与'缓存恢复的历史观测'。",
      "suggestion": "在 _artifact_from_cache 或 resources.append 前给恢复的 resource_row 增加 restored_from_cache=True（训练路径为 False）一列，并在 run_log 说明资源行来源口径。",
      "confidence": "high"
    }
  ]
}
```
