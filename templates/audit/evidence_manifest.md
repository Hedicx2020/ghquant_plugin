# 证据链清单 evidence_manifest.md 骨架

> 落盘于 `workspace/{report_id}/audit/evidence_manifest.md`；由 `quant-verifier` 随跑随记，**全难度必做**。核验方式必须是「亲自执行」，转述被审者的自我陈述不算证据。

---

## E1–E6 规则（断言）

| 规则 | 断言 |
|------|------|
| E1 运行证据 | verifier 亲自执行 `main.py`；`run_log.md` 记完整命令、退出码、起止时间戳；exit≠0 一律 fail，禁止「部分成功」 |
| E2 新鲜度 | `results/` 产物 mtime 晚于 `src/` 最近修改；否则判「拿旧结果冒充」，重跑 |
| E3 文件完备 | `metrics.json` 可解析且 comparison 非空；必需图表全存在且 >15KB；Excel 非零字节 |
| E4 三方数值一致 | 抽 3–5 个核心指标逐位核对 `metrics.json` == `verify_report.md` 引用值 == `backtest_summary.xlsx`（不一致 → 报告是编的，critical） |
| E5 样本量合理 | `n_periods` 与 spec 区间推算比对（如月频 13.4 年 ≈ 161 期），偏差 >10% → 区间被截断嫌疑 |
| E6 时间链 | spec → src → results → verify_report 的 mtime 单调递增；乱序 → 先写结论后跑数嫌疑 |

---

## 证据条目（E1–E6 逐条落盘，同一规则可有多条）

每条证据固定字段：**声明来源 / 证据类型 / 证据（文件+行号+命令+时间戳）/ 佐证 / 核验方式（亲自执行，非转述）/ 结果**。

| 证据ID | 规则(E1-E6) | 声明来源 | 证据类型 | 证据（文件+行号/命令+时间戳） | 佐证 | 核验方式 | 结果(pass/fail) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EVD-01 | E1 | 声称"main.py 执行成功" | 运行日志 | `run_log.md:12`，命令 `uv run python -m src.demo.main`，2026-07-08T10:00:00+08:00 | exit=0 | 亲自执行命令并读取退出码 | pass |
| EVD-02 | E4 | 声称 RankIC 均值=0.055 | 三方核对 | `metrics.json` key `rank_ic_mean`=0.055；`verify_report.md#RankIC` 引用 0.055；`backtest_summary.xlsx` Sheet1!B2=0.055 | 三处数值逐位相同 | 分别打开三个产物逐位比对 | pass |

---

## 扰动测试记录

> hard 难度**必做一次**；`K1`（疑似硬编码）/`K2`（结果过于完美）触发时任何难度都做。`tools/check_gates.py` G-RA-4 在 hard 难度下要求本文件含「扰动测试」字样作为「有记录」的弱校验——**本节必须填写真实执行结果，不得留空占位骗过门禁**。

- 触发原因: hard 难度必做 / K2（全部对比指标相对偏差同时 <0.5%，触发加测）/ K1（R 类数值疑似硬编码）
- 扰动参数: 回测截止日提前一年（首选）/ 分组数 10→5（备选，选必然影响结果的参数）
- 执行方式: 以命令行参数/环境变量覆盖重跑 `main.py`，输出到 `results/perturb_check/`（不改源文件；跑完删除临时输出，仅登记本记录）
- 核心指标相对变化: <指标名> 变化 <x%>（断言 >0.1%；完全不变 → 输出与输入解耦，硬编码实锤 critical）
- 结论: 通过 / 硬编码嫌疑（转 critical 意见）

---

## 审计结论

- E1–E6 全部规则均有至少一条证据落盘：是 / 否（否则本文件本身即构成 E1/E3 缺失证据）
- 三方数值核对（E4）不一致条数：<n>
- 时间链（E6）是否单调递增：是 / 否
