# 审计回应总表

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | major | 补录Stacking交叉熵损失 | accepted | 已补至workspace/r003_equity_factor_timing_cn/spec/spec.md:295 | pass |
| CDX-S-02 | major | 补录单树、树内归一化、森林汇总三层特征重要性公式 | accepted | 已补至workspace/r003_equity_factor_timing_cn/spec/spec.md:320-323 | pass |
| CDX-S-03 | major | 显式登记shadow rate changes与市场状态目标冲突 | accepted | 已补至workspace/r003_equity_factor_timing_cn/spec/spec.md:297-300及525-539，并关联A6 | pass |
| SA-A01 | critical | 25个宏观驱动只公开10项 | accepted | 已在workspace/r003_equity_factor_timing_cn/spec/spec.md:149-268登记D15-D29未知占位，均为missing/nonrecoverable且未虚构 | pass |
| SA-A02 | critical | R1-R10自动表格提取证据层不完整 | accepted | 已在workspace/r003_equity_factor_timing_cn/spec/tables_extracted.md:6-109重建全部R表并保留空白 | pass |
| SA-A03 | minor | 修复后plan要素计数仍为旧口径 | accepted | 已修正workspace/r003_equity_factor_timing_cn/plan.md:195为78项登记、63项可行动、15项占位 | pass |
| CDX-C-01 | major | 杠杆条件代理公式少扣一次名义GDP增速 | accepted | 已按AS7改为两个名义GDP缺口的等权平均，见src/r003_equity_factor_timing_cn/data_pipeline.py:226 | pass |
| CDX-C-02 | major | 执行日及退出日可交易状态对齐不完整 | accepted | 已在执行日复核ST/无量/停牌/涨跌停，并对退出受限头寸实施最多20个交易日延迟退出且不重选不重归一；证据字段见src/r003_equity_factor_timing_cn/strategy.py:694-717及806-817 | pass |
| CDX-C-R1-01 | critical | m3标签可得日截止到目标月末导致前视 | accepted | 已将训练标签截止改为真实决策时点predictor_date并增加最终断言，见src/r003_equity_factor_timing_cn/factor_model.py:625-629及743-849 | pass |
| CDX-R-01 | minor | AS41与中证800无成本理论基准口径不一致 | accepted | 已修订AS41，明确成本仅适用于三个可投资因子组合，中证800免交易成本且净主动收益以无成本指数为基准，见workspace/r003_equity_factor_timing_cn/assumptions.md:527-538 | pass |
| RA-A01 | major | 预测散点图按精确日期连接丢失11/33个月 | accepted | 已改为预测月份Period键连接并加入33×6=198、实际收益非空及唯一赢家断言，见src/r003_equity_factor_timing_cn/reporting.py及workspace/r003_equity_factor_timing_cn/audit/result_fix_round1.md | pass |
| RA-A02 | major | 正式交付缺逐股票执行/退出证据 | accepted | 已将OOS逐股票交易限制与延迟退出审计纳入returns_detail.xlsx的execution_exit_audit sheet；v2规范化哈希可由Excel回读稳定复算，见src/r003_equity_factor_timing_cn/reporting.py:834-924、workspace/r003_equity_factor_timing_cn/audit/result_fix_reaudit_round2.md | pass |
