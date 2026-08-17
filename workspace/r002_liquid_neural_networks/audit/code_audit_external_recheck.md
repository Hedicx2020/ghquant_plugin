复核完成。五条原 finding 与回归排查证据链已闭合，输出复核结论。

```json
{
  "checkpoint": "code_recheck",
  "verdict": "pass_with_issues",
  "items": [
    {
      "id": "CDX-C-01",
      "status": "fixed",
      "evidence": [
        "workspace/r002_liquid_neural_networks/assumptions.md:219-229 AS19完整登记：split归属仅由signal/entry/exit决定、窗口可跨段起点读纯历史、训练段可用2008年前上下文、拟合仅限训练样本实际窗口行、间隔保留、段首信号恢复与段尾删除的影响均写明",
        "workspace/r002_liquid_neural_networks/spec/ambiguities.md:133-141 A14按major-auto裁决采候选2并链接AS19",
        "common/ml_pipeline.py:473-496 assign_non_overlapping_splits仅检查date/entry_date/exit_date三端点落段，不再约束window_start_date",
        "common/ml_pipeline.py:670-672 新增window_pre_split审计列标记跨段前窗口；common/ml_pipeline.py:695-705 split_quality输出各段signal_start/signal_end/window_pre_split_count",
        "src/r002_liquid_neural_networks/strategy.py:259-267 逐段断言只约束三端点在段内，窗口仅需window_start_date<=date（原强制同段断言已移除）",
        "src/r002_liquid_neural_networks/strategy.py:107-120 数据自train_start前1年（2007-01-01）加载，段首60日窗口有纯历史可用；2020-01信号样本只需2019年60个交易日历史即可成立",
        "common/ml_pipeline.py:675-693 fit_mask由最终训练样本窗口行差分标记生成，验证/回测行不进入拟合；src/r002_liquid_neural_networks/strategy.py:243-245 断言preprocessor.fit_end不晚于train_end",
        "src/r002_liquid_neural_networks/strategy.py:277-292 sample_coverage按split输出signal_start/entry_start/exit_end供verify证据链；workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:24-26 B3/B4/B5状态理由回填AS19"
      ],
      "notes": "整改采用原建议(b)：放宽为标签端点限段、特征窗口回看纯历史，并以AS19+A14+矩阵理由三处登记。2020年从年初产生信号在代码层面成立（窗口在全面板构造、归属只看三端点、加载缓冲约244交易日>60）；output/r002_liquid_neural_networks/results/尚无正式产物，各段实际signal_start仍需verifier用sample_coverage表实证核对。"
    },
    {
      "id": "CDX-C-02",
      "status": "fixed",
      "evidence": [
        "common/ml_portfolio.py:118-122,160 prepare_factor_panel仅dropna(prediction)，forward_return缺失不再删除T日候选，docstring明示标签仅供事后诊断",
        "common/ml_portfolio.py:190-207 十分档仅按prediction降序与stock_code确定性裁决；common/ml_portfolio.py:481-485 目标持仓只取分组结果；_simulate_group_path仅读市场价格与可成交状态",
        "common/ml_pipeline.py:653-668 final_mask对allow_missing_label_splits保留缺标签样本，训练/验证标签有限断言保留；src/r002_liquid_neural_networks/strategy.py:229-233 backtest配置为allow_missing_label_splits",
        "common/ml_training.py:251-263,509-518 预测路径_unpack_features只解包特征绝不读标签，缺标签回测样本照常被五模型预测",
        "src/r002_liquid_neural_networks/strategy.py:769-790 五模型样本外键与标签逐位一致断言（equal_nan=True，NaN位置必须一致）",
        "common/ml_portfolio.py:219-241 RankIC逐截面成对删除缺标签并输出candidate_count/valid_label_count/label_missing_count及比率；common/ml_portfolio.py:338-366,400-412 路径汇总保留覆盖计数",
        "common/ml_reporting.py:275-284 校验candidate=valid+missing；common/ml_reporting.py:423-432 metrics写入label_coverage_policy且label_missing_changes_groups_or_trades=False；src/r002_liquid_neural_networks/main.py:704-714 run_log同步声明",
        "src/r002_liquid_neural_networks/main.py:232-240 合成冒烟专设唯一缺标签端点用于验证该行为；workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:13,21,26,27,33,57 D5/F8/B5/B6/B12理由与变更日志回填"
      ],
      "notes": "候选与标签可得性已彻底解耦：缺标签股票进入十分档与持仓，估值由市场面板沿最近可得VWAP处理；散点图同样成对删除后才抽样（common/ml_reporting.py:541-548）。原前视缺口消除，无需再补假设登记。"
    },
    {
      "id": "CDX-C-03",
      "status": "not_fixed",
      "evidence": [
        "src/r002_liquid_neural_networks/main.py:409-418 R2五行verification_level仍为unverifiable；main.py:507-527 pass=None计入waived_count",
        "src/r002_liquid_neural_networks/main.py:481-506 qualitative清单只有SA2覆盖/分组单调/top组/SA3四项，未加入原审计建议的CFC族显存<GRU方向性核验",
        "workspace/r002_liquid_neural_networks/spec/coverage_matrix.md:35 R2行状态理由仍写『正文摘要仍可验证』，与实现全waived的口径漂移原样保留",
        "workspace/r002_liquid_neural_networks/assumptions.md:219-229 AS19为最后一条，无R2验证等级降级的新登记",
        "workspace/r002_liquid_neural_networks/audit/audit_responses.md:3-5 无CDX-C-03处置记录；workspace/r002_liquid_neural_networks/iterations/ 为空，无登记在案的延期决定",
        "common/ml_reporting.py:357,374 不可比口径诚实披露（not_comparable_hardware_batch_dtype_unknown_in_report / computed_not_hardware_comparable），复现测量值齐全（main.py:286-316）"
      ],
      "notes": "原审计给出的两个二选一选项均未执行，也没有任何文书声明deferred，故判not_fixed而非deferred。实现侧的不可比披露本身诚实（测量口径、硬件、基线全部落盘），R2与数值主链路无关，不阻断代码审计；但result_audit前必须修正矩阵R2行理由或补方向性qualitative检查，否则口径漂移会在结果审计时再次触发。原severity为minor，维持。"
    },
    {
      "id": "CDX-C-04",
      "status": "partially_fixed",
      "evidence": [
        "已修复：common/ml_reporting.py:163 模型对记录字段为correlation；common/ml_reporting.py:174-176 矩阵长表value_name='correlation'；common/ml_reporting.py:202 逐日诊断同为correlation，AS18合同字段model_left/model_right/correlation/n_common/method/sample_scope齐全（ml_reporting.py:159-172）",
        "已修复：全仓库*.py经grep无'corr'字面量残留（含common/ml_portfolio.py:258,267的m4长表亦为correlation）；coverage_matrix.md:36,42 R3/SA2理由注明字段统一",
        "已修复：workspace/r002_liquid_neural_networks/audit/common_signatures.md:16 calculate_sharpe参数名已改为rf=，与common/utils.py:173-177实际参数名一致",
        "未修复：common_signatures.md:16,18记载periods_per_year默认252，实际calculate_sharpe/calculate_annualized_return默认均为12（common/utils.py:176,196）；common_signatures.md:19 performance_summary(returns, risk_free_rate=0.0, periods_per_year=252)与实际(returns, periods_per_year=12, name='')参数名与默认值均不符（common/utils.py:286-289）",
        "未修复：多处返回类型摘要与实际不符——calculate_prediction_diagnostics实际返回三元组（common/ml_portfolio.py:213-216，摘要:64写二元组）、build_liquid_model_manifest实际list[dict]（common/ml_liquid.py:285-293，摘要:58写dict）、build_ml_metrics实际(dict,DataFrame)（common/ml_reporting.py:303-319,466，摘要:74写dict）、predict_sequence_regressor实际np.ndarray（common/ml_training.py:488-496,518，摘要:47写pd.DataFrame）、build_window_index实际二元组（common/ml_pipeline.py:426-432，摘要:35）、transform_features实际DataFrame（common/ml_pipeline.py:539-543，摘要:38）"
      ],
      "notes": "第1点（corr→correlation）彻底完成；第2点只做了点名的rf=一处，『重新生成common_signatures.md』未真正执行，默认值与返回类型仍会误导后续审计。r002本身数值不受影响：所有调用显式传periods_per_year=252（common/ml_portfolio.py:823-830），但复用common/utils默认值12的其它案例存在被摘要误导的风险。维持minor。"
    },
    {
      "id": "CDX-C-05",
      "status": "fixed",
      "evidence": [
        "src/r002_liquid_neural_networks/main.py:148-159 _parse_args：synthetic_smoke且requested输出目录resolve后等于正式目录时，自动改写为output/r002_liquid_neural_networks/results/_smoke；环境变量R002_OUTPUT_DIR/R002_SYNTHETIC_SMOKE同受此逻辑约束（main.py:126-147）",
        "src/r002_liquid_neural_networks/main.py:533-539 run_pipeline内二次防护，绕过CLI直调run_pipeline也会重定向",
        "src/r002_liquid_neural_networks/main.py:156-158 显式指定的独立目录（requested≠正式目录）原样保留",
        "src/r002_liquid_neural_networks/main.py:663-669 run_metadata记录synthetic_smoke/formal_result/requested_output_dir/actual_output_dir/synthetic_output_redirected五字段；main.py:550-555 run_log同步留痕",
        "src/r002_liquid_neural_networks/main.py:540-541,565,822-836 run_log、checkpoints与异常日志全部写重定向后output_dir，冒烟全链路产物（metrics/comparison/workbook/parquet/图表）不触碰正式目录"
      ],
      "notes": "采用原建议的强制隔离方案且做了CLI与run_pipeline双保险，路径比较用expanduser().resolve()可抗相对路径与符号链接。冒烟在默认口径下不可能覆盖正式metrics.json/comparison.json/backtest_summary.xlsx。"
    }
  ],
  "new_findings": [
    {
      "id": "CDX-CR-01",
      "severity": "minor",
      "location": "workspace/r002_liquid_neural_networks/audit/audit_responses.md:3-5",
      "description": "audit_responses.md仅登记spec阶段CDX-S-01一条，CDX-C-01至CDX-C-05的逐条处置（accepted/rejected/deferred+修复位置）完全缺失；本次复核只能靠代码与coverage_matrix变更日志（coverage_matrix.md:55-57）反推整改范围，CDX-C-03未处理也因此没有任何登记在案的处置决定，违反项目『审计逐条回应』文书契约。",
      "suggestion": "补记5行code阶段处置：C-01/C-02/C-05标accepted并附本次复核确认的文件:行号，C-04标accepted但注明签名摘要未完全重刷，C-03必须给出明确处置（修矩阵理由+补登记，或加方向性qualitative检查，或正式登记deferred及理由）。",
      "confidence": "high"
    }
  ]
}
```

**复核结论摘要**：两条 major（CDX-C-01 分段过度保守、CDX-C-02 标签可得性前视）均已实质修复且登记闭环——split 归属改为仅看 signal/entry/exit 三端点、特征窗口允许回看段前纯历史（AS19/A14），组合候选与标签彻底解耦、RankIC 仅诊断时成对删除并全链路输出覆盖率。CDX-C-05 的冒烟隔离已用双保险落地。未修复项集中在文书层：CDX-C-03（R2 矩阵声明与 waived 实现的口径漂移）原样保留且无延期登记，CDX-C-04 的签名摘要只改了被点名的一处、未真正重新生成；两者均为 minor，不阻断，但需在 result_audit 前处理。未发现整改引入的 critical/major 代码回归，故 verdict 为 pass_with_issues。
