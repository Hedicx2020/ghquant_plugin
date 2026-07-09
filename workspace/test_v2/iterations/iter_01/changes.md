# iter_01 改动记录 · test_v2（coder）

- 本轮修改点: **M1**（且仅 M1）—— 盈亏比统计口径由「持仓日均值比」改「持仓日总额比」
- 锁定源: `workspace/test_v2/iterations/iter_01/diagnosis.md` 三·M1
- 授权改动文件（越界即违规）: **仅** `common/timing_backtest.py` 的 `timing_metrics` 函数内盈亏比计算块
- 实际改动文件数: **1**（common/timing_backtest.py）；src/test_v2/ 零改动、信号逻辑零改动、其他 common 模块零改动

---

## 一、改动清单

| 文件 | 函数 | 行范围（改后） | 改动性质 |
| --- | --- | --- | --- |
| `common/timing_backtest.py` | `timing_metrics` | docstring 约 99-105 行 | 口径说明补充（盈亏比=sum 总额比，注明依据 iter_01 M1 / R3 逐格对齐） |
| `common/timing_backtest.py` | `timing_metrics` | 盈亏比计算块约 149-163 行 | 均值比 → 总额比（含语义变更注释 + legacy 影响面说明） |

- 未触碰: `win_rate` / `sharpe` / `annual_return` / `max_drawdown` / `calmar` / `trade_count` / `annual_trade_count` / `excess_annual_return` / `benchmark_annual_return` 等任何其他指标；`signal_backtest` / `_reconstruct_returns` 全函数未动。
- 消费侧（`main.py` / `reversal.py` / `combo_ls.py` / `robustness.py` / `combo_composite.py` / `combo_final.py`）均只读 `m["profit_loss_ratio"]`，**单点修改全表自动跟随，无逐处改动**（符合 diagnosis 预判）。

---

## 二、diff 摘要（前后对照）

### 2.1 盈亏比计算块（核心）

改前（均值比 mean/|mean|，系统性偏低约 n_gain/n_loss 倍）：
```python
avg_gain = active_ret[active_ret > 0].mean()
avg_loss = active_ret[active_ret < 0].mean()
profit_loss_ratio = (
    float(avg_gain / abs(avg_loss))
    if pd.notna(avg_loss) and avg_loss < 0 and pd.notna(avg_gain)
    else 0.0
)
```

改后（总额比 Σ(收益>0)/|Σ(收益<0)|，与 strategy.py `_odds` 的 sum 口径统一）：
```python
# 盈亏比 = 持仓日总盈利额 / 持仓日总亏损额绝对值 = Σ(收益>0) / |Σ(收益<0)|（sum 总额比）。
# 语义变更（依据 iter_01 diagnosis M1）：原为均盈/均亏比 mean/|mean|，较总额比系统性偏低约
# n_gain/n_loss 倍；现改总额比，与 src/test_v2/strategy.py:_odds（R3 表3 赔率，经 spec 逐格
# 反推坐实为 sum 总额比、逐格对齐研报）统一。legacy 影响面：本模块为共享 timing 引擎，此变更
# 令所有走 timing_metrics 的业绩表（R1/R7/R8/R9/R11/R13）盈亏比语义一并对齐研报总额比口径。
sum_gain = active_ret[active_ret > 0].sum()
sum_loss = active_ret[active_ret < 0].sum()  # 负值
profit_loss_ratio = (
    float(sum_gain / abs(sum_loss))
    if sum_loss < 0 and sum_gain > 0
    else 0.0
)
```
- 条件由 `pd.notna(...) and avg_loss < 0 and pd.notna(avg_gain)` 简化为 `sum_loss < 0 and sum_gain > 0`：`active_ret` 非空由外层 `if` 保证，`sum()` 对空侧返回 0.0（非 NaN），全盈日 / 全亏日一侧自然落 `else 0.0`，语义与改前对齐、无 NaN 风险。

### 2.2 docstring 口径说明

`timing_metrics` docstring 补充：盈亏比取 **sum 总额比** `Σ(持仓日收益>0)/|Σ(持仓日收益<0)|`（非均值比），与 `strategy.py:_odds`（R3 表3 赔率）统一为总额比口径，依据 iter_01 diagnosis M1（R3 sum 总额比经 spec 逐格反推、逐格对齐研报坐实为研报盈亏比口径）。

---

## 三、冒烟实测前后值（本地可跑范围：R7 / reversal.py）

冒烟命令: `uv run python -m src.test_v2.reversal`（B1 第一段区间 2015-03-20~2023-08-02，R7 对照量级自检表）

| R7 列 | 改前(均值比) | 改后(总额比) | diagnosis 预测总额比 | 研报值 | 改后对研报偏差 |
| --- | --- | --- | --- | --- | --- |
| 隔日反转(多空) | 1.0537 | **1.3109** | ~1.291 | 1.31 | +0.07% ✓ |
| 隔日反转(仅做多) | 1.0434 | **1.4583** | 1.43~1.52（区间） | — | 落区间内 ✓ |
| T 基准 | 1.0137 | **1.1147** | ~1.05（临界预警） | 1.11 | +0.42% ✓ |

- 方向: 全部升高，与 diagnosis「均值比→总额比乘以 n_gain/n_loss>1 因子」预期一致。
- 实测优于预测: R7 多空实测 1.3109 比预测 1.291 更贴研报 1.31（diagnosis 用 `win_rate/(1-win_rate)` 近似 n_g/n_l 略保守）；**T 基准 diagnosis 曾预警临界（~1.05 vs 1.11 可能仍超），实测 1.1147 反而对齐研报 1.11**——临界担忧未兑现。
- 零副作用佐证: R7 表其余 13 项指标（区间收益 0.4824 / 年化 0.0499 / 回撤 -0.0343 / 波动 0.0340 / 卡玛 1.4524 / 夏普 1.4651 / 胜率 0.5505 / 看多 0.5779 / 看空 0.5253 / 上涨 0.5304 / 下跌 0.5808 / 年择时 152.7572 / 交易日 2039）**改前改后逐格完全一致**，证明只改盈亏比、未触碰任何其他指标。

---

## 四、预期影响面（全表，引用 diagnosis 家族一逐列预测表，待 verifier 完整重跑确认）

本地冒烟仅覆盖 R7（reversal.py 入口）。其余走 `timing_metrics` 的业绩表盈亏比按同一 sum 口径自动跟随，diagnosis 逐列预测如下（**R7 已本地实测坐实，余列待 verifier comparison.json 确认**）：

| 列 | 现均值比 | 预测总额比 | 研报值 | 预测偏差 | 本地状态 |
| --- | --- | --- | --- | --- | --- |
| R1 长短端 | 1.107 | 1.209 | 1.23 | -1.8% | 待 verifier |
| R1 长端 | 1.029 | 1.167 | 1.22 | -4.3% | 待 verifier |
| R1 短端 | 1.088 | 1.166 | 1.17 | -0.4% | 待 verifier |
| R7 多空 | 1.054 | 1.291 | 1.31 | -1.5% | **实测 1.3109 ✓** |
| R8 多空 | 1.085 | 1.318 | 1.33 | -0.9% | 待 verifier |
| R9 多空 | 1.103 | 1.352 | 1.36 | -0.6% | 待 verifier |
| R11 多空 / R13 | 1.116 | 1.426 | 1.44 | -1.0% | 待 verifier |

- 预期收敛: 家族一 13 项中 8-12 项收敛入 ±5%；R7 三列本地已全部逼近研报（多空/仅做多/T 基准）。
- 回归检查项（留 verifier）: R3（`strategy.py:_odds`，本已 pass）走独立实现、不经 `timing_metrics`，应不受影响仍全 pass。

---

## 五、假设与越界自检

- **不新增 / 不修改 assumptions.md**: 本次为「修正对齐既有已验证口径」而非 coder 主动简化——对齐目标即 **AS8**（R3 赔率=sum 总额比，已 verify 逐格吻合、AS8 维持）。此前 AS4/AS9/AS10「验证后回看」反复记录的「盈亏比与全表同族偏低」正源于 timing 引擎均值比与 R3 sum 口径的不一致，本次 M1 消除该不一致，不引入新假设。timing 引擎原均值比口径此前未登记为独立假设条目（早期实现选择），本次直接修正对齐、无遗留登记债务。
- **越界自检**: 仅改 `common/timing_backtest.py` 单函数块（diagnosis 授权范围）；未改 `src/test_v2/strategy.py:_odds`（口径基准，保持不动）；未改 F1-F8 任何信号逻辑；未改其他 common 模块；未读写 state.json。

---

## 六、验证记录

- 编译: `uv run python -m compileall common/timing_backtest.py` 通过（无语法错误）。
- 冒烟: `uv run python -m src.test_v2.reversal` 跑通，盈亏比升高见第三节。
- 回归: `uv run pytest -q` → **108 passed**（19.61s），全绿。4 个测试文件（`src/test/test_strategy.py` 测 v1 独立实现、`tests/test_check_gates.py` / `test_pdf_extract.py` / `test_state.py` 属 tools 层）无一引用 `timing_backtest`/`timing_metrics`，改动不被任何测试断言、回归无影响。
- 通过判定与全表 comparison.json 归 verifier，本记录只报冒烟对数、不宣布验证结论。
