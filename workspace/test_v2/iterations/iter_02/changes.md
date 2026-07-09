# iter_02 改动记录 · test_v2（coder）

- 轮次: iter=2 / max_iter=6；结论 continue
- 本轮修改点: **M2**（年化基准 252→240）+ **M3**（上涨/下跌胜率口径）
- 权威指令来源: `workspace/test_v2/iterations/iter_02/diagnosis.md` 第四节 M2/M3
- 允许改动文件范围（diagnosis 逐条列明）: `src/test_v2/config.py`（仅 75 行）、`src/test_v2/reversal.py`（仅 `_directional_win_rates` 的 up/down 两项及其 docstring）、`workspace/test_v2/assumptions.md`（三处登记）
- 严禁改动（已恪守，未触碰）: strategy.py / combo_*.py / robustness.py / common/ / 信号逻辑 / long_win_rate·short_win_rate / timing_metrics 主胜率 win_rate / TRADING_DAYS_PER_YEAR 模块默认

---

## 一、改动文件清单（3 个）

| 文件 | 改动点 | 行 | 归属 |
| --- | --- | --- | --- |
| `src/test_v2/config.py` | `periods_per_year` 252→240 + 旁注引 AS13 | 75（单行） | M2 |
| `src/test_v2/reversal.py` | `_directional_win_rates` docstring 上涨/下跌两行 + up/down_win_rate 代码块（删仅服务这两项的 `held` 中间变量） | docstring 139-141、code 147-157 | M3 |
| `workspace/test_v2/assumptions.md` | 新增 AS13；AS6 块末改判行；AS7 块末校准行；AS13 影响指标补年择时次数 | 见第四节 | 连带登记 |

---

## 二、M2 diff（config.py:75）+ 预期变化

**diff：**
```diff
-    periods_per_year: int = 252                # 日频交易日年化基准
+    periods_per_year: int = 240                # 年化交易日基准（iter_02 M2/SO-01：中国研报常用 240 交易日；T 基准探针 0.02301 精确命中研报 0.023，见 AS13）
```

**预期逐列变化（引 diagnosis 第四节 M2 复算表，本 coder 不重算、不下判定）：**
- diagnosis 复算 R8/R9/R11 组合年化/夏普 9 项 + R1-T 年化/夏普 2 项 = **共 11 项 fail→pass、0 项翻 fail**；核心证据 R1_T_annual 0.024166→0.02301 精确命中研报 0.023（残差 +0.03%）。逐列预测值见 diagnosis 第四节 M2 表（R8_多空_annual 0.061351→0.05834、R9_多空_annual 0.067366→0.06406、R11_仅做多_annual 0.053748→0.05112 等）。
- 副作用监控（现 pass、改后仍 pass 但劣化，verifier 必核）：R1_长短端_annual 约 0.49%→4.37%、R7_仅做多_annual 约 0.39%→4.46%（均边界内）；R11_多空_年化波动率 0.12%→约 -2.29%。
- **说明**：R8/R9/R11/R1-T 是 combo_*/main 产物，reversal.py 冒烟不覆盖，逐列收敛由 verifier 跑完整 comparison.json 裁定。

**冒烟佐证（R7 表内的 T 基准，同机制旁证 M2 方向）：**
- R7 的 T 列（国债期货买入持有，区间 2015-03-20~2023-08-02）年化 **0.0239→0.0228**，随 240 下降。
- 注意区间差异：R7-T 区间起点 2015-03-20，与 diagnosis M2 表的 **R1-T**（主区间 2015-03-24 起）**不是同一段回测**，故绝对值不同（R7-T 0.0228 ≠ R1-T 预测 0.02301）；两者同为「T 买入持有 + 240 年化」，方向、机制一致，佐证 M2 单点 config 改动对 T 基准生效。config 注释与 AS13 引用的 0.02301 特指 diagnosis 主区间 R1-T 探针（命中研报 0.023）。

---

## 三、M3 diff（reversal.py）+ 预期变化

**diff（docstring）：**
```diff
-    - 上涨胜率 = 标的当日上涨（close_return>0）且有持仓日中策略日收益为正的占比；
-    - 下跌胜率 = 标的当日下跌（close_return<0）且有持仓日中策略日收益为正的占比。
+    - 上涨胜率 = 标的当日上涨（asset_ret>0，全标的上涨日为分母）中策略日收益为正（strat>0）的占比；
+    - 下跌胜率 = 标的当日下跌（asset_ret<0，全标的下跌日为分母）中策略日「不亏」（strat>=0，含0）的占比。
+      （iter_02 M3/SO-02 校准：去 held 交集、下跌用不亏口径；探针 R11 下跌 0.4901 vs 研报 0.4902）
```

**diff（代码块）：**
```diff
-    held = position.ne(0)
-    return {
-        "long_win_rate": _rate(position > 0),
-        "short_win_rate": _rate(position < 0),
-        "up_win_rate": _rate(held & (asset_ret > 0)),
-        "down_win_rate": _rate(held & (asset_ret < 0)),
-    }
+    # 上涨/下跌胜率分母改为全标的涨/跌日（去 held 交集）；下跌用「不亏」口径 strat>=0（含 0）。
+    up_sub = strategy_ret[asset_ret > 0]
+    down_sub = strategy_ret[asset_ret < 0]
+    return {
+        "long_win_rate": _rate(position > 0),
+        "short_win_rate": _rate(position < 0),
+        # iter_02 M3/SO-02：分母=全标的上涨日，命中=strat>0（探针 R7 上涨 0.4443 vs 研报 0.4448）
+        "up_win_rate": float((up_sub > 0).mean()) if len(up_sub) else float("nan"),
+        # iter_02 M3/SO-02：分母=全标的下跌日，不亏=strat>=0（含0）（探针 R11 下跌 0.4901 vs 研报 0.4902）
+        "down_win_rate": float((down_sub >= 0).mean()) if len(down_sub) else float("nan"),
+    }
```
> `long_win_rate`/`short_win_rate` 仍用原 `_rate`（`>0` 口径），未改（diagnosis 严禁）。删除的 `held` 变量原仅服务 up/down 交集，改口径后无引用，删之避免死代码/未用变量告警——属 M3 修改的必要连带，不越界。

**预期变化（引 diagnosis M3）：**
- 计分项：**R11_多空_下跌胜率 0.462212→0.490135（研报 0.4902，rel≈0.03%）fail→pass（+1）**；R11_多空_上涨胜率 0.656466→约 0.63（研报 0.6289）pass 且改善。R11 是 combo_final 产物，由 verifier 核（须核 R11 上涨胜率不过冲翻 fail）。

**冒烟佐证（R7 多空列，与 diagnosis 第 120 行 R7 探针逐位吻合）：**
- R7 多空 上涨胜率 **0.5304→0.4443**（研报 R7 0.4448，diagnosis R7 探针 0.4443）——逐位命中。
- R7 多空 下跌胜率 **0.5808→0.6504**（研报 R7 0.6528，diagnosis R7 探针 0.6504）——逐位命中。
- 旧口径（0.5304/0.5808）反而远离研报，新口径显著逼近，坐实「全涨跌日分母 + 下跌不亏」口径正确性。

**M3 连带（非 bug，数学恒等，供 result_audit 免疑）：**
- **T 列** 上涨→1.0000、下跌→0.0000：T 为买入持有（position 恒 +1，strat=asset），涨日 strat>0 必赢=1.0、跌日 strat<0 不亏口径 =0.0，数学必然。
- **仅做多列** 上涨/下跌胜率 = 多空列（同为 0.4443/0.6504）：新口径按「标的涨跌日」分组 + 不亏口径下二者恒等——(a) 上涨日分子 =#{asset>0 且 position_多头腿>0}，仅做多多头腿=多空多头腿，故相等；(b) 下跌日「不亏」分子中，多空的做空腿（strat>0 赢）与仅做多对应的空仓（strat=0 不亏）一一对应、均计入 >=0，故相等。是口径的数学性质，非实现错误。

---

## 四、冒烟前后值对照（R7 全表，252/旧口径 → 240/新口径）

`uv run python src/test_v2/reversal.py` 输出（写 output/test_v2/results/reversal_baseline_stats.csv）：

| 指标 | 多空 前 | 多空 后 | 仅做多 前 | 仅做多 后 | T 前 | T 后 | 归因 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 区间收益 | 0.4824 | 0.4824 | 0.3151 | 0.3151 | 0.2108 | 0.2108 | 不变（无 N） |
| 年化收益 | 0.0499 | **0.0474** | 0.0344 | **0.0328** | 0.0239 | **0.0228** | M2 |
| 最大回撤 | -0.0343 | -0.0343 | -0.0316 | -0.0316 | -0.0757 | -0.0757 | 不变（无 N） |
| 年化波动率 | 0.0340 | **0.0332** | 0.0247 | **0.0241** | 0.0389 | **0.0380** | M2 |
| 卡玛比率 | 1.4524 | **1.3817** | 1.0893 | **1.0366** | 0.3159 | **0.3007** | M2（含年化） |
| 夏普比率 | 1.4651 | **1.4281** | 1.3951 | **1.3604** | 0.6142 | **0.5990** | M2 |
| 胜率 | 0.5505 | 0.5505 | 0.5779 | 0.5779 | 0.5199 | 0.5199 | 不变（严禁·未碰） |
| 看多胜率 | 0.5779 | 0.5779 | 0.5779 | 0.5779 | 0.5199 | 0.5199 | 不变（严禁·未碰） |
| 看空胜率 | 0.5253 | 0.5253 | NaN | NaN | NaN | NaN | 不变（严禁·未碰） |
| 上涨胜率 | 0.5304 | **0.4443** | 1.0000 | **0.4443** | 1.0000 | 1.0000 | M3 |
| 下跌胜率 | 0.5808 | **0.6504** | 0.0000 | **0.6504** | 0.0000 | 0.0000 | M3 |
| 盈亏比 | 1.3109 | 1.3109 | 1.4583 | 1.4583 | 1.1147 | 1.1147 | 不变（无 N） |
| 年择时次数 | 152.7572 | **145.4831** | 114.8151 | **109.3477** | 0.1236 | 0.1177 | M2（annual_trade_count 亦年化，×240/252） |
| 交易日数 | 2039 | 2039 | 2039 | 2039 | 2039 | 2039 | 不变 |

---

## 五、改动隔离性自查（交叉验证 M2/M3 各行其道、未越界）

- **M2 仅动年化类**：区间收益/最大回撤/胜率/看多·看空胜率/盈亏比/交易日数 前后完全一致（不含 periods_per_year，数学上不应变——冒烟坐实）。年择时次数变化=annual_trade_count 的年化系数连带（已在 AS13 影响指标登记）。
- **M3 仅动上涨/下跌胜率**：主胜率 win_rate（0.5505）、看多（0.5779）、看空（0.5253）前后不变——diagnosis 严禁改动项零触碰，冒烟坐实。
- 两修改点正交（M2 不碰口径、M3 不碰年化），互不干扰。

---

## 六、assumptions.md 三处登记

1. **新增 [AS13]**（年化基准采用 240 交易日）：来源 iter_02 diagnosis M2/SO-01 甄别；影响面 param；影响全部年化/夏普/波动率/卡玛/年择时次数；可信度**中等**（惯例层代理、残余数据漂移在案，须最终报告标注）；状态 assumed；高亮 major-auto；验证后回看留 verifier 后填。
2. **AS6 块末改判行**：`【iter_02 改判】家族二年化偏差根因改判为年化基准（AS13），换月口径不再承担该归因；AS6 保留适用于年择时次数与逐日路径细节`。
3. **AS7 块末校准行**：`【iter_02 校准】上涨/下跌胜率口径已按 M3 落地（全涨跌日分母+下跌不亏），替代原自定义口径`。

> AS13 影响指标经冒烟观测补入「年择时次数（×240/252）」，与实测一致（登记不漏报）。AS6/AS7 正式条目重写走 revise，本轮仅按 diagnosis 指令追加修订行。

---

## 七、冒烟与测试证据

- `uv run python -m compileall src/test_v2/config.py src/test_v2/reversal.py` → 编译通过（Compiling config.py / reversal.py，无 SyntaxError）。
- `uv run python src/test_v2/reversal.py` → R7 表正常输出（见第四节），CSV 写入 output/test_v2/results/reversal_baseline_stats.csv。
- `uv run pytest -q` → **108 passed in ~20s**（框架层 test_check_gates / test_state / test_pdf_extract 全绿，未受策略参数改动影响）。
- 冒烟仅确认可执行 + 前后量级，**不下通过判定**——comparison.json 逐列对数、副作用核查、R11 计分归 verifier。

---

## 八、遗留 verifier（本 coder 不裁定）

1. 跑完整 main.py/combo 链，出 iter_02 comparison.json，核 M2 家族二 9 + R1-T 2 = 11 项 fail→pass、M3 R11 下跌胜率 1 项 fail→pass（预期 69→81/91）。
2. 副作用必核：R1_长短端_annual、R7_仅做多_annual 是否仍在容差内（边界）；R11_多空_年化波动率劣化幅度；R11_多空_上涨胜率是否过冲翻 fail。
3. 残余 10 项（家族三单腿 6 + 家族四小分母/数据源 4）按 diagnosis 第六节 stop_partial 预案，iter3 逼近同指标 3 轮红线。
