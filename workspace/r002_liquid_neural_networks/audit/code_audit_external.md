五个维度审查完毕，证据链闭合。输出审计结论。

## 审计结论

```json
{
  "checkpoint": "code",
  "verdict": "pass_with_issues",
  "dimensions_checked": [
    {"dimension": "公式逐要素对照", "result": "CDX-C-03, CDX-C-04"},
    {"dimension": "未来函数/前视检查", "result": "CDX-C-02"},
    {"dimension": "数据对齐检查", "result": "CDX-C-01"},
    {"dimension": "config vs B类核对", "result": "no_findings"},
    {"dimension": "作弊模式排查(K1/K5/K6)", "result": "CDX-C-05（K1硬编码/K5吞错未发现实锤）"}
  ],
  "findings": [
    {
      "id": "CDX-C-01",
      "severity": "major",
      "category": "未登记的区间对齐偏差/日期范围缩水",
      "location": "common/ml_pipeline.py:453-477; src/r002_liquid_neural_networks/strategy.py:246-252",
      "description": "assign_non_overlapping_splits 要求 window_start_date 与 date/entry/exit 同落一个分段，且 strategy.py 逐段断言强制该约束。60 日窗口因此使验证段、回测段各自开头约 60 个交易日（约 3 个月）不产生任何信号样本：回测实际首个信号约在 2020 年 4 月，2020Q1 完全缺失，与 B5 声明的『2020年1月～2024年12月』回测区间不符，直接影响 R4/R6 全期年化收益与 SA3 的 2020 年行。原文『与训练/验证数据间隔 1 个月防止数据暴露』（1 个月 < 60 交易日）暗示原文允许特征窗口跨段回看、仅隔离标签；本实现的更强约束是结果敏感的实现选择，但 assumptions.md 无对应条目（AS10 只登记 60 日连续窗口），coverage_matrix B5 行状态理由为空。",
      "suggestion": "二选一：(a) 在 assumptions.md 显式登记该保守约束及 2020Q1/验证段头部缺失的影响；(b) 放宽为『标签与信号日必须在段内、特征窗口允许回看跨入前段』，训练段起点仍由数据加载边界控制。verify 时应量化各段实际信号起止日并写入证据链。",
      "confidence": "high"
    },
    {
      "id": "CDX-C-02",
      "severity": "major",
      "category": "样本过滤引入的可交易性前视（超出已登记假设范围）",
      "location": "common/ml_portfolio.py:146-155; common/ml_pipeline.py:612-615",
      "description": "prepare_factor_panel 对 prediction 和 forward_return（T+1~T+21 标签）同时 dropna，且组合分组、_build_path_events 的目标持仓均基于该过滤后截面。这意味着 T 日持仓决策隐含使用了 T+1/T+21 两个端点的可交易性与存续信息：未来 20 日内端点停牌或摘牌的股票被提前移出候选池，属于幸存者式前视（方向大概率有利于复现收益）。AS9 仅登记『任一端点缺失则删除该训练样本』，未覆盖回测段组合构建；AS16 的分档描述也未提标签过滤。RankIC 删除无标签样本是必要的，但逐日账本回测本可让无标签股票进入持仓、靠执行日 tradable/沿价估值处理（该机制已存在）。信号数值本身无未来信息，剔除比例受停牌率限制，故评 major 而非 critical。",
      "suggestion": "组合候选与标签过滤解耦：分组截面仅要求 prediction 有效，标签缺失样本保留进持仓模拟；或至少在 assumptions.md 登记该前视缺口并由 verifier 量化逐截面剔除比例（label_valid=False 占比）评估影响。",
      "confidence": "high"
    },
    {
      "id": "CDX-C-03",
      "severity": "minor",
      "category": "矩阵声明与实现验证等级不一致",
      "location": "src/r002_liquid_neural_networks/main.py:387-397; src/r002_liquid_neural_networks/config.py:266-272",
      "description": "coverage_matrix R2 行（core）声称『正文摘要仍可验证』，但实现把 R2 五行全部置为 verification_level=unverifiable（pass=None、计入 waived），metrics 中标 not_comparable_hardware_batch_dtype_unknown_in_report。本地无对等硬件、测量口径（设备增量/MPS 非真峰值/CPU RSS 累计）已诚实披露，不硬比是合理的，但该验证等级降级未在 assumptions.md 登记，与矩阵声明存在张力；R2 的相对关系（CFC 族显存远小于 GRU）本可做方向性核验。",
      "suggestion": "либо把 R2 的方向性断言（CFC/NCP(CFC) 内存 < GRU）加入 qualitative 检查，либо修正 coverage_matrix R2 状态理由为 unverifiable 并补一条假设登记，避免 result_audit 时口径漂移。",
      "confidence": "medium"
    },
    {
      "id": "CDX-C-04",
      "severity": "minor",
      "category": "产物合同/证据文档一致性",
      "location": "common/ml_reporting.py:159-172; common/utils.py:173-177",
      "description": "两处文档与实现不一致：(1) AS18 明文要求相关性按模型对输出字段 model_left/model_right/correlation/n_common/method/sample_scope，实现的 pair 表字段名为 corr 而非 correlation（矩阵长表有 correlation 列，实质数据齐全）；(2) 审计输入 common_signatures.md 记载 calculate_sharpe(returns, risk_free_rate=...)，实际签名为 rf=（ml_portfolio 调用用 rf=，运行无误，但签名摘要过时会误导后续审计）。均不影响数值。",
      "suggestion": "把 pair 表 corr 列更名为 correlation 以与 AS18 合同一致；重新生成 common_signatures.md。",
      "confidence": "high"
    },
    {
      "id": "CDX-C-05",
      "severity": "minor",
      "category": "合成冒烟与正式产物同路径的防呆缺口",
      "location": "src/r002_liquid_neural_networks/main.py:62,143-148,532",
      "description": "--synthetic-smoke（或 R002_SYNTHETIC_SMOKE=1）使用合成面板端到端出全套产物，且默认输出目录与正式运行相同（output/r002_liquid_neural_networks/results），冒烟一旦在正式运行之后执行会直接覆盖正式 metrics.json/comparison.json/backtest_summary.xlsx。run_metadata.synthetic_smoke 与 formal_result=False 标记齐全、run_log 追加留痕，故不构成静默替换实锤，但存在把合成结果误当正式产物的操作风险。",
      "suggestion": "synthetic_smoke=True 时强制把输出重定向到独立子目录（如 results/_smoke/），或在正式产物存在时拒绝覆盖。verifier 核验 metrics.json 时必须检查 run_metadata.synthetic_smoke=False。",
      "confidence": "high"
    }
  ]
}
```

## 结论说明

**verdict = pass_with_issues**（2 major / 3 minor，无 critical）。核心结论：

- **无作弊实锤**：R1-R7 全部字面量仅存在于 `config.py:M5ReferenceConfig` 的 reference 表，经 `build_report_reference_tables` → `report_*` 前缀列与复现值分栏合并计算偏差，`report_value_used_as_reproduction=False`；全代码唯一的 `except Exception` 在 `main.py:767`，记录后重新 raise。日期、股票池、epoch、模型集合、20 路径均有断言防缩水（`MLPortfolioSettings.validate` 强制 offsets==range(20)、持有期==调仓周期；strict 模式禁止延长回测截止日）。
- **时点安全的主链路扎实**：预处理器仅训练段拟合并有起止日断言；标签端点按全市场交易日历核验 T+1/T+21；训练器签名不接收回测集；执行状态列不回流 T 日因子（有显式断言）。
- **两个 major 都是"实现选择超出登记假设"而非蓄意作弊**：CDX-C-01（分段过度保守导致 2020Q1 无信号，属未登记范围缩水）和 CDX-C-02（组合候选池被 T+1/T+21 标签可得性过滤，带前视性质）。建议 iterate 阶段优先处理这两条，或经用户确认后补登记 assumptions.md 并让 verifier 量化影响。
