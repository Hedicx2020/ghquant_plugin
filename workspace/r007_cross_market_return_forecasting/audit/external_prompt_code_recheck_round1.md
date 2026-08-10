# r007 code_audit 第 1 轮修复增量外审

你是只读量化代码审计员。只审本轮 CA-ALL-01～09 修复是否真实关闭；不要修改仓库，不要采信修复者结论，不要读取 `audit_responses.md`、旧 agent 消息或正式结果。

## 合同与定位输入

先读：

- `workspace/r007_cross_market_return_forecasting/audit/impl_audit_mall.md` 的 CA-ALL-01～09
- `workspace/r007_cross_market_return_forecasting/audit/code_audit_fix_round1.md`（仅作函数定位，不作通过证据）
- `workspace/r007_cross_market_return_forecasting/spec/coverage_matrix.md` 中 D1、D6、F4、F5、F7～F9、F18、F19、B1、B7、B11、R2、SA3、SA6

然后只读下列实现函数及其直接调用上下文：

- `data_pipeline.py:audit_us_merged_panel_contract`
- `data_pipeline.py:audit_security_calendar_coverage`
- `data_pipeline.py:audit_return_distributions`
- `main.py:_path_identity_manifest`
- `main.py:CheckpointStore.code_manifest/build_context/validate_stage`
- `main.py:_stage_m1`
- `portfolio_pipeline.py:audit_formal_prediction_coverage`
- `portfolio_pipeline.py:run_m4_portfolios`
- `main.py:_stage_m4`
- `main.py:_m5_input_manifest`
- `main.py:_run_sa3`
- `main.py:_stage_m5`
- `main.py:_build_fig03_graph_evidence`
- `main.py:_build_fig05_long_table`
- `reporting.py:create_result_charts`
- `reporting.py:write_formal_outputs`
- `sensitivity_pipeline.py:predict_snapshot_single_model`

## 必须逐项裁决

1. 美股 `请求集合 == manifest success == 合并面板实际集合`，逐证券缓存与合并切片内容一致，实际少于 500 或失败超过 1 必须中止。
2. 2016–2021 两方向、三规格、十模型、预期锚点/交易日/股票键不得只以“非空”通过；缺一键必须失败。
3. M1 schema、加载面板、收益面板、逐证券覆盖、分布与缺失审计真实接入 checkpoint 和 evidence 输出。
4. checkpoint 代码闭包含 `common/data_loader.py`、`common/backtest.py`、`common/utils.py`、`pyproject.toml`、`uv.lock`。
5. SA6 行业 parquet 的完整正文 SHA256 与 schema SHA256 进入 M5 上下文。
6. 正式原始大文件也做完整流式内容 SHA256，不能只依赖 size/mtime/schema。
7. FIG3 消费真实 US→CN 快照并生成行 CN、列 US 的带符号 t 值矩阵；不能是空占位。
8. FIG5 同时绘制两方向 q25/q50/q75 六序列，且同 sheet 保留底表与图片。
9. SA3 每配置持久化 predictions 与 model_audit；Sharpe 前要求配置间样本键完全一致并覆盖正式日历/股票池；无入边不能静默丢审计。

同时检查本轮是否引入新的未来函数、R2 参考值进入计算、核心 `except/pass/continue` 静默降级，或 smoke-only 修复。

## 输出合同

只输出一个 JSON 对象：

```json
{
  "checkpoint": "code_recheck_round1",
  "verdict": "pass | pass_with_issues | fail",
  "closed": [
    {"issue": "CA-ALL-01", "result": "closed | open", "evidence": "文件:行号 + 一句证据"}
  ],
  "dimensions_checked": [
    {"dimension": "九项原问题关闭", "result": "no_findings 或 finding id"},
    {"dimension": "未来函数与时点", "result": "no_findings 或 finding id"},
    {"dimension": "R2硬编码隔离", "result": "no_findings 或 finding id"},
    {"dimension": "静默吞错与范围缩水", "result": "no_findings 或 finding id"},
    {"dimension": "正式输出与checkpoint", "result": "no_findings 或 finding id"}
  ],
  "findings": [
    {
      "id": "CDX-C-R1-01",
      "severity": "critical | major | minor",
      "category": "未来函数 | 硬编码 | 参数不符 | 静默吞错 | 范围缩水 | 输出合同",
      "location": "文件:行号",
      "description": "可复核描述",
      "suggestion": "定点建议",
      "confidence": "high | medium | low"
    }
  ]
}
```

`closed` 必须恰有 CA-ALL-01～09 九行；五个维度必须全部出现；每条 finding 必须有精确行号。
