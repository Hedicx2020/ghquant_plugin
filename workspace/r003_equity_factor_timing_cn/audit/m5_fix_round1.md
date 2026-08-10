# m5 第1轮定向修复记录

- 案例: `r003_equity_factor_timing_cn`
- milestone: m5
- 修复依据: `audit/impl_audit_m5.md`、`output/r003_equity_factor_timing_cn/verify_report.md` 的 m5 章节
- 修改边界: 仅修改 `src/r003_equity_factor_timing_cn/reporting.py`、`main.py`，新增本记录；未修改 m1-m4、`common/`、`state.json` 或正式 `results/`
- 结论边界: 本记录只报告 coder 修复与烟测证据，不给出独立验证结论

## 一、问题逐条回应

### CA-A01：缺少独立回撤PNG

- `reporting._build_chart_data` 现在从 m4 四组合 `gross_nav` 构造逐月毛收益回撤。历史峰值以期初净值1.0为下限，与 `common.utils.calculate_max_drawdown` 的期初口径一致；回撤大于0会触发断言。
- `create_charts` 新增 `drawdown.png`，尺寸为12×6、300 DPI，内容为中国OOS四组合毛收益回撤，不使用原研报R10数值或合成回退。
- `backtest_summary.xlsx` 新增 `图_组合回撤` sheet，原始回撤数据与 `drawdown.png` 嵌入同一sheet。
- 原五图全部保留。正式产物合同从15项扩为16项：5个Excel、6个PNG、3个JSON、2个Markdown。
- `metrics.json` 与 `oos_evidence_manifest.json` 均写入16项文件名合同；manifest哈希明细新增 `drawdown.png`，稳定核心产物SHA-256行数由12增至13。

### CA-A02：2025-11显式诊断端点截断m1交易日历

- `main.run_pipeline` 不再把 `--end` 写入 `ChinaFactorTimingConfig.sample_end`。
- m1始终使用冻结的2015-01至2025-12完整底座构造，因此最后诊断目标月所需的下一交易月末及其后首个交易日不会被CLI截断。
- `--end` 只裁剪传给m2/m3的 `monthly_features`；m4继续消费完整m1底座并与裁剪后的m3概率取交集。
- 正式默认仍为2023-04至2025-12，静态展开恰33个月。

### CA-A03：运行哈希未覆盖实际窗口及m4/R9

- 保留只覆盖 `ChinaFactorTimingConfig` 的 `base_configuration` 哈希，另将 `parameter_hashes.configuration` 明确升级为完整运行配置哈希，并同时保存为 `parameter_hashes.run_configuration`。
- 完整运行配置哈希覆盖：基础config、实际 `prediction_start/end`、OOS cutoff、m2/m3参数哈希、m4的15%主动倾斜/买卖成本/印花税、R9完整方向矩阵、四组合顺序、年化/回撤/相对收益/换手公式口径、R10参照值及16项产物合同。
- 同一运行哈希同步进入 `metrics.json`、`oos_evidence_manifest.json` 和 `run_log.md`。
- 真实2025-11与2025-12使用同一基础配置哈希，但完整运行哈希不同，证明CLI窗口已进入运行身份。

### E1/G-VF：run_log证据不完整

- 开始运行即写入ISO 8601 `started_at` 和完整可重放命令。
- 成功完成后写入ISO 8601 `finished_at`、`elapsed_seconds`、完整命令、`exit=0`、`artifact_count: 16` 和 `artifacts: 16`。
- 产物完成后会把结果目录实际非空文件名与16项合同逐项比较；多文件、缺文件或空文件均不会静默写成成功。
- 失败路径也写入 `started_at`、`finished_at`、`elapsed_seconds`、完整命令、`exit=1`、异常类型和错误文本。

## 二、临时真实单月复验

### 2025-11

- 临时目录: `/private/tmp/r003_m5_fix_r1_real_2025_11_20260718`
- 命令: `uv run --extra ml --no-sync python -m src.r003_equity_factor_timing_cn.main --output-root /private/tmp/r003_m5_fix_r1_real_2025_11_20260718 --prediction-start 2025-11 --end 2025-11`
- 退出: 0；日志 `exit=0`
- 开始/结束: `2026-07-18T08:56:29+08:00` / `2026-07-18T08:57:00+08:00`
- elapsed: `31.650695` 秒
- m1完整月频行: 132；裁至诊断终点的预测特征行: 131
- m2/m3概率月: 1；m4组合收益行: 4
- 训练窗: 2018-11至2025-10，固定84个月
- 实际文件: 16；PNG: 6；`drawdown.png` 约300 DPI；summary为15个sheet且回撤sheet内嵌1图
- 完整运行哈希: `17b1a7e5ba4c9948e3fd166ea63332899c0641a36759b687a1c9fba9511cc488`
- 原“交易日历不足以构造下一月T+1收益”未再出现。

### 2025-12

- 临时目录: `/private/tmp/r003_m5_fix_r1_real_2025_12_20260718`
- 命令: `uv run --extra ml --no-sync python -m src.r003_equity_factor_timing_cn.main --output-root /private/tmp/r003_m5_fix_r1_real_2025_12_20260718 --prediction-start 2025-12 --end 2025-12`
- 退出: 0；日志 `exit=0`
- 开始/结束: `2026-07-18T08:57:26+08:00` / `2026-07-18T08:57:58+08:00`
- elapsed: `31.254021` 秒
- m1完整月频行/预测特征行: 132/132
- m2/m3概率月: 1；m4组合收益行: 4
- 训练窗: 2018-12至2025-11，固定84个月
- 实际文件: 16；PNG: 6；`drawdown.png` 约300 DPI；summary回撤sheet内嵌1图
- 完整运行哈希: `2bc3af3afdc088711e07b65fc0eb530dda7854e343361013aacacaad8bd00d96`

两次运行的基础配置哈希均为 `476eee2687973b5f9dede0249842e6f62ef00303eeb91d61f81a853f27a7b843`，完整运行哈希因实际窗口不同而不同。两份 manifest 的运行哈希均与各自 metrics 一致，artifact contract均为16，稳定核心产物SHA-256均为13行。

## 三、失败路径与静态回归

- 无效窗口临时命令 `--prediction-start 2025-12 --end 2025-11` 按预期退出1；`/private/tmp/r003_m5_fix_r1_invalid_window_20260718/run_log.md` 已记录两个ISO时间戳、elapsed、完整命令、`exit=1`、`ValueError`及错误文本。
- `uv run --extra ml --no-sync python -m py_compile reporting.py main.py` 通过。
- 正式CLI `--help` 通过；默认窗口静态复核为2023-04至2025-12，共33个月。
- 合成报告层重放路径 `/private/tmp/r003_m5_fix_r1_synth_20260718_0910` 通过16项文件、6张PNG、6个Excel内嵌图、manifest/metrics哈希一致、成功日志字段完整等检查。
- sklearn 1.9 对 `SVC(probability=True)` 给出未来弃用警告；这是m2既有实现警告，不影响本轮两次退出码及m5产物。
- 未运行正式33个月结果，未写 `output/r003_equity_factor_timing_cn/results/`。

