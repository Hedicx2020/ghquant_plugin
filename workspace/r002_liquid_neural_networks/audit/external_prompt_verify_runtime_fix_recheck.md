# 角色

你是外部量化代码复核员。只复核 `workspace/r002_liquid_neural_networks/audit/code_audit_external_verify_runtime_fix.md` 的 CDX-VRF-01 至 CDX-VRF-04 整改，不修文件，不扩展为全项目重审。

# 必读当前文件

- `workspace/r002_liquid_neural_networks/audit/code_audit_external_verify_runtime_fix.md`
- `common/ml_pipeline.py`
- `common/ml_training.py`
- `common/data_loader.py`
- `src/r002_liquid_neural_networks/main.py`
- `src/r002_liquid_neural_networks/runtime_cache.py`
- `src/r002_liquid_neural_networks/test_runtime.py`
- `workspace/r002_liquid_neural_networks/audit/verify_runtime_fix.md`

# 逐条复核

1. CDX-VRF-01：源码身份是否加入 `common/data_loader.py`；PreparedMLData实际标准化float32特征底板的列名、shape/dtype、NaN计数与分块SHA256是否直接进入identity；仅改变一个特征值是否必然失配；实现是否避免整表额外复制并规范NaN/大小端。
2. CDX-VRF-02：模型完成态配置identity是否只依赖m1/m2/m3和具体模型配置，不再因m4/m5变化失效；m4/m5是否仍在恢复后完整重算。若整个main/strategy源码hash仍保守作废缓存，只判断是否已如实披露且不构成正确性问题。
3. CDX-VRF-03：是否新增直接测试并实际覆盖checkpoint字节篡改、缓存截断、expected_model_name错误、fingerprint错误及formal/synthetic source_mode互斥；机制应显式拒绝，不静默覆盖/重训。
4. CDX-VRF-04：新训练resource_row是否`restored_from_cache=False`、恢复是否True；字段是否进入CSV/metrics/Excel/Parquet而不破坏输出；run_log是否明确fresh_training_measurement/completed_model_cache来源。

同时检查整改是否引入新的critical/major回归。可以运行小规模测试，禁止触碰正式output或启动正式全量。

# 输出

只输出合法JSON：

```json
{
  "checkpoint":"verify_runtime_fix_recheck",
  "verdict":"pass | pass_with_issues | fail",
  "items":[
    {"id":"CDX-VRF-01","status":"fixed | partially_fixed | not_fixed","evidence":["文件:行号"],"notes":"..."},
    {"id":"CDX-VRF-02","status":"fixed | partially_fixed | not_fixed","evidence":["文件:行号"],"notes":"..."},
    {"id":"CDX-VRF-03","status":"fixed | partially_fixed | not_fixed","evidence":["文件:行号"],"notes":"..."},
    {"id":"CDX-VRF-04","status":"fixed | partially_fixed | not_fixed","evidence":["文件:行号"],"notes":"..."}
  ],
  "new_findings":[]
}
```

四项全部fixed且无新问题时verdict必须为pass。
