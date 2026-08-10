# r007 code_audit 外审缩减重试

你是只读量化代码审计员。首次全仓审计已超时；本次严格按降级合同，只读取：

- `src/r007_cross_market_return_forecasting/strategy.py`

不要读取其他文件、过程叙事、agent 报告或 `audit_responses.md`，不要修改仓库。

背景：本案例为 hard / ml / experimental 的跨市场滚动机器学习复现。实验模式不豁免未来函数、方向错误、结果硬编码、静默吞错或正式范围缩水。

只检查 `strategy.py` 中以下事项：

1. 八个基础回归器（OLS、LASSO、RIDGE、RBF SVM、XGBoost、LGBM、RF、AdaBoost）的构造是否真实、参数是否来自配置、随机性是否固定。
2. `avg` 与 `median` 是否严格只在八个基础模型全部存在时生成；是否有部分失败后继续、填零、复用旧预测或静默吞错。
3. 预测/训练接口是否可能在本文件内引入未来标签、方向反转或对模型失败进行静默降级。
4. 下列 R2 论文参考数值是否进入模型构造、预测、选参、组合或 PnL 计算；若仅在本文件完全不存在则明确说明：

```text
0.848 0.969 1.238 1.650 1.821 1.777
1.238 1.293 1.437 1.715 1.668 1.550
0.743 0.751 0.782 0.719 1.020 0.836
1.445 1.480 1.587 1.539 1.381 0.964
1.320 1.457 1.541 1.440 1.652 1.424
1.481 1.558 1.639 1.799 1.747 1.090
1.389 1.405 1.549 1.548 1.100 0.667
```

只输出一个 JSON 对象：

```json
{
  "checkpoint": "code",
  "verdict": "pass | pass_with_issues | fail",
  "dimensions_checked": [
    {"dimension": "模型构造与参数来源", "result": "no_findings 或 finding id"},
    {"dimension": "八模型事务与集成完整性", "result": "no_findings 或 finding id"},
    {"dimension": "未来标签与方向", "result": "no_findings 或 finding id"},
    {"dimension": "R2结果硬编码", "result": "no_findings 或 finding id"},
    {"dimension": "静默吞错与降级", "result": "no_findings 或 finding id"}
  ],
  "findings": [
    {
      "id": "CDX-C-01",
      "severity": "critical | major | minor",
      "category": "未来函数 | 硬编码 | 参数不符 | 静默吞错 | 范围缩水 | 输出合同",
      "location": "src/r007_cross_market_return_forecasting/strategy.py:行号",
      "description": "可复核描述",
      "suggestion": "定点建议",
      "confidence": "high | medium | low"
    }
  ]
}
```

五个维度必须全部出现；findings 为空也必须给 verdict。
