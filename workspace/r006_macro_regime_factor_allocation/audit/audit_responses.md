# 审计回应总表

| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |
| --- | --- | --- | --- | --- | --- |
| CDX-S-01 | major | IA.11、IA.13、IA.14、IA.15 未获得内容相符的 R 要素，页面与矩阵关联错位。 | accepted | 已新增 R25-R28：`spec.md:1068,1086,1111,1136`；同步 `coverage_matrix.md:74-77` 与 `plan.md:54,69`。 | pass |
| CDX-S-02 | major | R12 漏登 Continuation × Valuation formation-period 行。 | accepted | 已在 `spec.md:682-697` 补入 0.05%、t=0.05、80/80 月并核对 Table IA.27 符号。 | pass |
| M1-E6 | major | 真实交易日历的 `signal_date=datetime64[us]` 与宏观输入的 `available_date=datetime64[ns]` 导致 `align_macro_asof()` 抛出 `MergeError`。 | accepted | `data_pipeline.py:1960-1987` 在 `merge_asof` 前显式统一日期键为无时区 `datetime64[ns]`，保留源时间先后并仍使用 backward 方向；`tests/test_r006_m1.py:139-178` 以不同 datetime 单位和月末边界复现并锁定无前视行为。 | pending verifier |
