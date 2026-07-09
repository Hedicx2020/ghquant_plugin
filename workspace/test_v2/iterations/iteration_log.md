# 迭代日志：test_v2

| 轮 | 时间 | 触发 | 失败指标(偏差) | 采纳假设/修改 | 修改摘要 | 结果(pass变化) | 状态 |
|----|------|------|----------------|--------------|----------|----------------|------|
| 1 | 07-08 22:2x | verify_fail（35项超差） | 盈亏比家族13项 -7%~-29% 等五家族 | M1（R3 sum 总额比同库铁证） | common/timing_backtest.py 盈亏比 mean→sum | 56/91→69/91（+13，家族一清零，零回归） | 达成预期 |
| 2 | 07-08 23:2x | residual_22 | 年化夏普家族9+R1-T 2项 +5%~6.7%；下跌胜率-8.7% | M2（AS13 年化基准240）+ M3（AS7 校准不亏口径）；codex 第二意见 SO-01/02 采纳、SO-04 竞争排除 | config periods_per_year 252→240；reversal 胜率分母/不亏口径 | 69/91→81/91（+12，零回归，与诊断逐位一致） | 达成预期 |
| 3 | 07-09 00:0x | residual_10 | R1 单腿6项（长端-18%反劣化/短端5.7-7.9%/回撤±8.4%）+ 小分母4项（绝对差0.3-1.54pp） | 无（三候选探针全否决：护主列破产/主表回归/新假设兜圈） | 无代码修改；10 项写 attribution_status（accepted 8/assumption_linked 2→AS6） | 81/91 定格 | stop_partial（规则9三轮红线） |

## 各轮明细
- iter_01：diagnosis.md（同库铁证：strategy._odds sum 口径 R3 逐格对齐→推翻 v1「不可推断」）/ changes.md / comparison.json(56) / comparison_after.json(69)
- iter_02：diagnosis.md（SO-01 vs SO-04 竞争甄别，iter1「家族二不可修」自我改判为惯例层代理+数据漂移残留）/ changes.md / comparison_after.json(81)；codex_opinion.md（四假设含只读探针）
- iter_03：diagnosis.md（stop_partial；三探针机制级否决；规则9红线追溯三快照）/ comparison.json(81+归因)；codex_opinion.md

## 系统改进建议（转最终报告）
1. templates/standards.json 的 timing default 增 abs_eps≈0.005 近零保护（可回收 R10/R12_2023 两项假 fail，2016 两项>0.005 不误放）
2. check_gates 的 qualitative 项 expect==observed 字符串判定过于机械，需定义 observed 机器可判约定（本次 4 项定性语义上全过）
