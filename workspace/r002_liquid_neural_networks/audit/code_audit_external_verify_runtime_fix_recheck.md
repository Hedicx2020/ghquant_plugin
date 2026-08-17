复核完成。四项整改在代码与测试中均已逐条落实,静态核验未发现新的 critical/major 回归(本会话工具无 shell 执行权限,未重跑 pytest;运行证据采信 `verify_runtime_fix.md` 记录的 `4 passed` 与三次合成冒烟)。

```json
{
  "checkpoint": "verify_runtime_fix_recheck",
  "verdict": "pass",
  "items": [
    {
      "id": "CDX-VRF-01",
      "status": "fixed",
      "evidence": [
        "src/r002_liquid_neural_networks/main.py:226-237",
        "src/r002_liquid_neural_networks/main.py:255-258",
        "src/r002_liquid_neural_networks/runtime_cache.py:155-199",
        "src/r002_liquid_neural_networks/runtime_cache.py:224-226",
        "common/ml_pipeline.py:96-135",
        "src/r002_liquid_neural_networks/test_runtime.py:368-427"
      ],
      "notes": "common/data_loader.py 已加入 _runtime_code_files（main.py:236），strategy.py:16-22 依赖的五个加载函数均在该文件内。identity 的 standardized_features 节直接哈希 PreparedMLData._feature_values——即 dataset() 分发给所有 split/模型的同一只读 float32 底板（ml_pipeline.py:120,130），manifest 含 shape、source/canonical dtype、feature_columns 列名、nan_count 与分块 SHA256。底板每个字节都进 digest，单值最小扰动（np.nextafter）在 test_runtime.py:413-417 断言必然改变 digest，经 derive_model_fingerprint（identity.digest 内嵌）传导为 load 时 RuntimeCacheFingerprintError。复制控制符合要求：正式底板为 C 连续小端 float32 且管线断言标准化后无 NaN（ml_pipeline.py:839-840），np.asarray(chunk, dtype='<f4', order='C') 返回原 view，memoryview 直接喂 hashlib 零复制；仅大端转换或 NaN 规范化时复制当前 ≤10 万行分块，NaN 统一为 quiet-NaN 0x7fc00000，test_runtime.py:419-424 验证大端+NaN 数组与本机序同 hash。data_loader.py 文件变化改变 digest 亦有直接测试（test_runtime.py:409-411）。"
    },
    {
      "id": "CDX-VRF-02",
      "status": "fixed",
      "evidence": [
        "src/r002_liquid_neural_networks/main.py:240-264",
        "src/r002_liquid_neural_networks/main.py:750-754",
        "src/r002_liquid_neural_networks/main.py:828-832",
        "src/r002_liquid_neural_networks/main.py:905-1095",
        "src/r002_liquid_neural_networks/test_runtime.py:428-430",
        "workspace/r002_liquid_neural_networks/audit/verify_runtime_fix.md:115-123"
      ],
      "notes": "identity 的 configs 仅含 m1/m2/m3（main.py:250），_build_runtime_identity 签名无 m4/m5 参数且有测试断言（test_runtime.py:428-430）；模型指纹只追加该模型自身配置（GRU 用 m2，液态用 model_name+m3）。config.py 已同步移出源码指纹清单，使 m4/m5 默认值修改不再经文件 hash 作废缓存；m1/m2/m3 的实际配置值经 _jsonable 全量进入 identity，加上特征底板与样本表内容 hash 兜底，config.py 中影响 m1-m3 行为的改动仍必然失配。恢复路径与训练路径共用循环后的同一段代码：assemble_m4_prediction_panel（main.py:909）、run_m4_backtest（main.py:922）及全部 m5 输出均无条件重算，缓存只覆盖单模型训练+回测段预测。main.py/strategy.py 整文件 SHA 仍保守作废缓存一事已在 verify_runtime_fix.md:123 如实披露为独立边界，方向保守，不构成正确性问题。"
    },
    {
      "id": "CDX-VRF-03",
      "status": "fixed",
      "evidence": [
        "src/r002_liquid_neural_networks/test_runtime.py:320-365",
        "src/r002_liquid_neural_networks/test_runtime.py:401",
        "src/r002_liquid_neural_networks/runtime_cache.py:339-362",
        "src/r002_liquid_neural_networks/main.py:1124-1139",
        "workspace/r002_liquid_neural_networks/audit/verify_runtime_fix.md:69"
      ],
      "notes": "四类拒绝分支均新增直接测试并命中对应机制：checkpoint 追加字节篡改后断言'检查点内容不一致'（test:329-338 → runtime_cache.py:361-362）；缓存文件截半后断言'无法安全读取'的 RuntimeCacheError（test:341-351 → runtime_cache.py:339-342）；expected_model_name 传 LTC 断言'名称不一致'（test:320-327 → runtime_cache.py:354-357）；配置变化产生的错误指纹断言'指纹不一致'（test:353-365 → runtime_cache.py:347-353）。formal/synthetic 互斥由 test:401 断言 source_mode=synthetic_smoke 使 identity digest 改变，而 fingerprint 内嵌 identity digest（runtime_cache.py:251-256），叠加已有的指纹不符拒绝测试构成完整互斥链。所有分支均显式抛异常，run_pipeline 不捕获、main() 记日志后 re-raise（main.py:1124-1139），合成冒烟第三次运行以 RuntimeCacheFingerprintError exit 1 佐证，无静默覆盖或静默重训路径。verify_runtime_fix.md 记录 4 passed in 2.66s。"
    },
    {
      "id": "CDX-VRF-04",
      "status": "fixed",
      "evidence": [
        "src/r002_liquid_neural_networks/main.py:473",
        "src/r002_liquid_neural_networks/main.py:770-777",
        "src/r002_liquid_neural_networks/main.py:848-855",
        "src/r002_liquid_neural_networks/main.py:814-817",
        "src/r002_liquid_neural_networks/main.py:895-899",
        "src/r002_liquid_neural_networks/main.py:988",
        "src/r002_liquid_neural_networks/main.py:1059",
        "common/ml_reporting.py:354-376",
        "workspace/r002_liquid_neural_networks/audit/verify_runtime_fix.md:100-101"
      ],
      "notes": "_resource_row 固定写入 restored_from_cache=False（main.py:473），GRU 与液态模型的恢复路径均对缓存 resource_row 的副本覆盖为 True（main.py:770-772,848-850）。该列随 resources_frame 进入 model_resource_log.csv（main.py:1059）、metrics 的 training.resources 与 R2 节（main.py:988 → ml_reporting.py:376,421）、经 build_ml_chart_data 的 resource_usage 进入 Excel 工作簿与 Parquet 明细（main.py:1019-1027,1039-1049,1092）；ml_reporting 对 resource_summary 的消费均按列名取用或整表透传，新增布尔列不破坏 merge/图表/序列化，合成冒烟 fresh 与 restored 两轮均完整跑到 m5 且 CSV 五行分别为 false/true。run_log 逐模型写明 resource_record_source=fresh_training_measurement（main.py:816-817,896-898）或 completed_model_cache（main.py:775-776,853-854）。缓存写入侧 resource_row 列名单独持久化（runtime_cache.py:303-304），恢复重建保序。R2 仍为 unverifiable/pass=null，历史观测并入不影响达标判定。"
    }
  ],
  "new_findings": []
}
```
