# 证据链清单 evidence_manifest.md · ssrn_6115073（verify 阶段最终验证 · member 过滤后权威版）

> 由 `quant-verifier` 随跑随记；核验方式一律「亲自执行」，不转述被审者自述。
> 复现模式 experimental（市场迁移 A股）。**本清单为 verify 阶段最终验证**：在 code_audit 修正后
> （CA-CDX-C-01：建仓前 member∩tradeable 时点成分过滤）的代码上重跑权威产物，落 E1–E6 逐条证据
> + 扰动测试记录，覆盖 spec→src→results→verify_report 全时间链（E6）。旧里程碑级 tradeable 口径
> 证据（CPMM-EW SR=0.6042）已被本轮 member 过滤后新基准（CPMM-EW SR=0.7168）取代。

---

## E1–E6 规则（断言）

| 规则 | 断言 |
|------|------|
| E1 运行证据 | verifier 亲自执行 main.py/robustness.py；`run_log.md` 记完整命令、退出码、起止时间戳；exit≠0 一律 fail，禁止「部分成功」 |
| E2 新鲜度 | `results/` 产物 mtime 晚于 `src/` 最近修改；否则判「拿旧结果冒充」，重跑 |
| E3 文件完备 | `metrics.json` 可解析且 comparison 非空；必需图表全存在且 >15KB；Excel 非零字节可解析；独立复算坐实非转抄 |
| E4 三方数值一致 | 抽核心指标逐位核对 `metrics.json` == `backtest_summary.xlsx` 单元格 == `verify_report.md` 引用值 |
| E5 样本量合理 | `n_periods` 与 spec 区间推算比对 |
| E6 时间链 | spec → src → results → verify_report 的 mtime 单调递增 |

---

## 证据条目（E1–E6 逐条落盘）

固定字段：声明来源 / 证据类型 / 证据（文件/命令+时间戳）/ 佐证 / 核验方式（亲自执行）/ 结果。

| 证据ID | 规则 | 声明来源 | 证据类型 | 证据（文件/命令+时间戳） | 佐证 | 核验方式（亲自执行） | 结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EVD-01 | E1 | coder 声称"m6 端到端产出" | 运行日志 | `run_log.md` 命令1 `uv run python -m src.ssrn_6115073.main`，起 2026-07-11T19:47:36 止 19:48:35 | stdout 打印 R1 表 SR 行 + "已写 backtest_summary.xlsx / 7 张 PNG"，无 stderr | 亲自执行命令、读退出码 | pass（exit=0） |
| EVD-02 | E1 | coder 声称"m7 稳健性产出" | 运行日志 | `run_log.md` 命令2 `uv run python -m src.ssrn_6115073.robustness`，起 19:48:46 止 19:49:58 | stdout base 三路径 Δ=+0.0000 + SA1/2/3/4 全表 | 亲自执行命令、读退出码 | pass（exit=0） |
| EVD-03 | E1 | hard 难度扰动必做 | 运行日志 | `run_log.md` 命令4 `verify_perturb.py`，起 20:02:15 止 20:04:11 | stdout 末 `PERTURB_DONE`，断言 PASS | 亲自执行扰动重跑、读退出码 | pass（exit=0） |
| EVD-04 | E2 | coder 于 19:2x 产 src | mtime 比对 | `src/ssrn_6115073/robustness.py` mtime=2026-07-11T19:28:21（src 最新）；`common/allocation_backtest.py` 18:08:44；`results/backtest_summary.xlsx` mtime=19:48:33（权威产物最早） | 权威产物晚于 src 最新约 20 分钟 | `stat -f "%Sm %N"` 亲读 mtime | pass |
| EVD-05 | E3 | 声称图表/Excel 产齐 | 文件核验 | required_charts（allocation 5）weight_evolution(1166KB)/portfolio_nav(310KB)/asset_contribution(117KB)/rolling_volatility(279KB)/drawdown(283KB)；R5 累计 cumulative_returns_hs300(522KB)/_all_markets(455KB)；SA sa1(108KB)/sa3(291KB)/sa4(129KB)——全 >15KB；`backtest_summary.xlsx`(15965B,6 sheet)+`robustness_summary.xlsx`(14756B,7 sheet) 可 pandas/openpyxl 解析；`metrics.json`(20606B)/`comparison.json`(36025B,81 metrics+17 qual) 可 json 解析 | 图>15KB、Excel 非零可解析、json 非空 | `stat` 读字节 + pandas.read_excel 加载 + json.load | pass |
| EVD-06 | E3 | 声称 metrics.json SR 非转抄 spec | 独立复算 | 从 hs300 CPMM-EW 原始 port_returns（69 期）用 numpy 独立重算：SR=(mean(r)−rf̄)/std(r,ddof=1)×√12=0.716811 == 引擎 0.716811（abs_diff=0.0）；AR=mean×12=0.225890 == 引擎；累计从收益累乘 1.944350 == 从净值末值 1.944350 == 引擎 | 三路径独立算法逐位一致，数值确来自本次净值序列 | 亲自 numpy 独立重算 + 比对引擎值（见 metrics.json `independent_recheck`） | pass |
| EVD-07 | E4 | R1 表数字 | 三方逐位核对 | 抽 6 核心格：`backtest_summary.xlsx` sheet `R1_表2主结果` CPMM-EW 沪深300 SR=0.7168/AR=0.2259/PSR=0.9595、CPMM-MV 沪深300 SR=0.9297、CPMM-EW 上证50 SR=0.5982/中证500 SR=0.5946 == `metrics.json` `markets` 对应键逐位一致 == `verify_report.md` 最终验证小节引用值 | 三源逐位相同（abs_diff<1e-4） | pandas 读 xlsx 单元格 vs json.load vs verify_report | pass |
| EVD-08 | E4 | R4 溢出表 | 三方逐位核对 | `backtest_summary.xlsx` sheet `R4_宏观溢出强度` hs300 CPI to_index_share=4.986015 == `metrics.json` `spillover_to_index.hs300.CPI`=4.986015 == comparison.json `R4.CPI.hs300` reproduced_value | 三源逐位相同 | pandas 读 xlsx vs json | pass |
| EVD-09 | E1 | robustness 重跑口径无偏 | base Δ=0 复现 | 命令2 stdout：CPMM-EW hs300 nc=base/w=base 重跑 SR=0.7168 vs m6 基准 0.7168（Δ+0.0000）；CPMM-MV λ=base 0.9297 vs 0.9297（Δ+0.0000） | 三路径 Δ=0，member 过滤后同构无偏 | 亲跑 robustness.py 读 base 复现校验行 | pass |
| EVD-10 | E5 | 样本量 | 区间推算比对 | metrics.json：CPMM-EW hs300 n_periods=69；测试段 2019-01..2024-12=72 月，CPMM 系两阶段 pattern matching 预热损前 ~3 期 → 69（偏差 4.2%<10%）；CPM-EW 71/CPM-MV 71/PMM 68/EWMFM 68/外部基准 71，均自洽；SA1 4 年窗=48 月、SA2 尾窗 2023-2024=24 月自洽 | n 与区间一致，无截断嫌疑 | 亲读 metrics.json n_periods + 区间推算 | pass |
| EVD-11 | E6 | 时间链 | mtime 单调 | spec.md/coverage_matrix.md（≤19:36）→ src/robustness.py 19:28:21 → results 图表/xlsx 19:48-19:49 → metrics.json 19:57 / comparison.json 19:58 → verify_report/evidence 本轮写入（20:0x+）单调递增 | 无「先写结论后跑数」 | `stat` 亲读各产物 mtime | pass |

---

## 扰动测试记录

- 触发原因：**hard 难度必做一次**（difficulty=hard，见 coverage_matrix plan 行）。
- 扰动参数：**训练截止日提前一年**——`src.ssrn_6115073.data_prep.TRAIN_END` 由 `2018-12-31` monkeypatch 为 `2017-12-31`（data_prep `from config import TRAIN_END` 绑定名，prepare_all 构造 PreparedData 时用之；pattern_matching 经 `prep.train_end` 取值故随之改变；**测试期 TEST_START=2019-01-01 保持不变**，纯隔离训练期缩短对最优窗口 w / 簇数 nc / BorutaShap 因子重选的影响）。同进程先跑 base 再 monkeypatch 重跑 perturbed。
- 执行方式：`run_log.md` 命令4，`uv run python <scratchpad>/verify_perturb.py`，exit=0（stdout 末 `PERTURB_DONE`）；临时输出到 `results/perturb_check/perturb_metrics.json`，**跑完 `rm -rf output/ssrn_6115073/results/perturb_check` 删除，已确认目录不存在**；未改任何源文件。
- 核心指标相对变化：**CPMM-EW hs300 SR 0.716811 → 0.521495，相对变化 27.25%**；另 CPMM-MV SR 0.9297 → 0.6194（33.38%）、PMM SR 0.7702 → 0.9632（25.06%）、CPMM-MV 累计 5.6026 → 2.3542（57.98%）、PMM 累计 2.5447 → 4.4763（75.91%，全核心指标最大变化）；base_SR=0.716811 与权威运行逐位一致（同源佐证）。
- 结论：**通过**——核心指标相对变化远超 0.1% 阈值，输出随训练输入真实变动，**无硬编码 / 输入解耦嫌疑**（若硬编码，扰动后仍应输出 0.7168）。

---

## 审计结论

- E1–E6 全部规则均有至少一条「亲自执行」证据落盘：**是**（E1:EVD-01/02/03/09，E2:EVD-04，E3:EVD-05/06，E4:EVD-07/08，E5:EVD-10，E6:EVD-11）。
- 独立复算（E3 非转抄）：hs300 CPMM-EW SR/AR/累计三路径逐位一致，abs_diff=0.0。
- 三方数值核对（E4）不一致条数：**0**（R1 六核心格 + R4 溢出格 xlsx==metrics.json==verify_report 全逐位一致）。
- 时间链（E6）是否单调递增：**是**（spec/coverage→src→results→verify 单调）。
- 扰动测试（hard 必做）：**已执行、通过（27.25%>0.1%）、临时输出已删**。
- 达标/领先/延续判定：不在本清单——归 check_gates（按 standards.json 重算）/ diagnoser / oos。

---

## 反虚报复核（result_audit）

> 由 quant-auditor（mode=result）追加，独立于 verifier/主会话自述：一切数值回 comparison.json / metrics.json / backtest_summary.xlsx / robustness_summary.xlsx 逐位重算比对，10 张 PNG 全部亲自 Read 看图核对。防幻觉三约束：只引用亲自打开的产物、不采信被审者结论、关键数字均独立重算。experimental（市场迁移）——数值不与原文对齐属设计内，不列为问题；审查点为「迁移数字是否自洽·结论措辞是否夸大·skip/降级是否成立·扰动是否解耦」。

### 已检查维度清单（无一省略）
K3/E4 三方数值一致 · K2 过于完美/硬编码 · 归因结论措辞相符 · skip/infeasible 理由 · 扰动测试触发判断 · 核验分级合理性（本案 N/A，见下）。

### K3/E4 三方一致（comparison.json == metrics.json == xlsx，独立逐位比对）
抽核心格三源亲自打开对照，全部逐位一致（abs_diff≤1e-4，四位显示口径）：

| 抽查格 | comparison.reproduced | metrics.json | backtest_summary.xlsx | 一致 |
| --- | --- | --- | --- | --- |
| R1 CPMM-EW hs300 SR | 0.716811 | markets.hs300.CPMM-EW.SR=0.716811 | R1表2 R08=0.7168 / 明细 R02=0.7168 | ✓ |
| R1 CPMM-EW hs300 AR | 0.22589 | 0.22589 | R1表2 R02=0.2259 | ✓ |
| R1 CPMM-EW hs300 AStd | 0.276372 | 0.276372 | R05=0.2764 | ✓ |
| R1 CPMM-EW hs300 PSR | 0.959547 | 0.959547 | R11=0.9595 | ✓ |
| R1 CPMM-MV hs300 SR | 0.929747 | 0.929747 | R08=0.9297 | ✓ |
| R1 CPMM-EW sz50 SR | 0.598233 | 0.598233 | R09=0.5982 | ✓ |
| R1 CPMM-EW zz500 SR | 0.594561 | 0.594561 | R10=0.5946 | ✓ |
| R4 CPI hs300 溢出 | 4.986015 | spillover.hs300.CPI=4.986015 | R4宏观溢出 R02 to_index=4.986015 | ✓（逐位精确） |
| R4 CPI sz50 | 4.922668 | 4.922668 | R09=4.922668 | ✓ |
| R4 CPI zz500 | 4.931758 | 4.931758 | R16=4.931758 | ✓ |
| R4 PPI zz500 | 5.06743 | 5.06743 | R17=5.06743 | ✓ |
| R5 CPMM-EW hs300 累计 | 1.94435 | cum_return=1.94435 | 补充累计 R02=1.9443 | ✓ |
| R3 CPMM-EW hs300 β⁺/β⁻/Δβ | 1.164893/0.946858/0.218034 | method_level_beta 同值 | （xlsx 无 R3 表，comparison==metrics 二方） | ✓ |

robustness 三方（comparison.qualitative == metrics.robustness == robustness_summary.xlsx）：SA1 沪深300 2019-2022 SR=1.345（xlsx SA1_CPMM领先性 R02）/ SA2 hs300 CPMM-EW=-0.3547（xlsx SA2 R08）/ SA3 w 列=[0.4431,0.8021,0.7168,0.4492,0.6194]（xlsx SA3 R08）/ SA4 PMI 仅用 1.1674·剔除 0.8159（xlsx SA4 R07）——逐值一致。
**结论：K3/E4 无不实，三方零偏差；迁移数字未编。**

### K2 过于完美/硬编码复核
- experimental 无容差 pass 判定；98 metric 无一「复现值==原文值」（rel_dev 区间 1.5%–868%，最小 R1.SOR.hs300 1.52% 仍非 0），无逐格=原文的硬编码伪迹。
- r_class_values.txt（0.269/0.205/1.317… 原文字面量）已由 code_audit codex 排查代码未硬编码；本轮独立佐证：扰动后核心指标变（见下），非恒定常量。
- metrics.json `independent_recheck` 显示引擎 SR==numpy 独立重算 SR=0.716811（abs_diff=0）——此为「同数据同公式」应然一致，且扰动测试证明输出随输入变，非硬编码。
- R4 CPI 三市场 to_index 均≈4.9 曾疑聚集，但 _gamma_weight（0.171/0.321/0.0）与 net_spillover（-9.3/-7.4/-7.7）三市场各异，底层 VAR/GFEVD 计算确不同；CPI 为全国性宏观量、对三宽基溢出量级相近属合理，非硬编码。
**结论：无 K2 过于完美/硬编码嫌疑。**

### 归因/结论措辞相符（防「比数据更乐观」）
逐条比对 verify_report.md「最终验证（member 过滤后权威版）」措辞 vs 产物分布，措辞均不超前于数据、known 差异如实标注：
- 领先性：如实述 CPMM-EW SR 排名 4/2/3（hs300/sz50/zz500），被 CPMM-MV 全市场反超、被 PMM(0.770)/OLMAR(0.746) 局部反超——未夸大成「CPMM-EW 领先」。
- 消融：如实述「去聚类(PMM) 在 hs300/zz500 未劣于全量→聚类增量存疑（呼应 AS48）」——**未把「PMM 去聚类未降」说成「聚类有效」**（task 点名的失败模式未发生）。
- R4：如实述「CPI 迁移成立（前二）、IR 方向相反（三市场垫底 #7/#6/#7）」，7 处 direction_match=false 保留在 comparison.json。
- R3：如实述下行保护仅 sz50 β⁻≈-0.02 显现、hs300/zz500 β⁻ 正未显。
- SA1/SA2/SA4：如实述「非跨子区间稳定全胜」「hs300 样本外 SR 转负 -0.3547」「PMI 最强单因子但剔除任一 SR 不降=组合不依赖单因子、原文 CPI/IR 未迁移」。
- known 口径差异（MR 偏低/累计量级 560% vs 75%/R4 量级 0.7-5.1 vs 0.3-319/持仓~3只）均标注为 experimental 豁免、非计算错误。
与 task 预期核心结论「方法部分迁移：宏观模式匹配+溢出加权有增量·聚类无增量·对 w 脆弱·样本外主市场衰减·关键因子 A股为 PMI·member 过滤后集中~3只」逐条吻合。
**结论：结论措辞不夸大、无归因造假；comparison.qualitative observed 文本亦忠实于数据。**

### 图表真实性（10 张 PNG 全部亲自 Read 看图核对）
曲线条数=分组数、坐标与 metrics 吻合：cumulative_returns_hs300（11 曲线=11 方法；CPMM-EW 终点≈194%==cum 1.944、CPMM-MV≈560%==5.60、OLMAR≈462%==4.62、Index≈22.5%==0.225）；portfolio_nav（**净值终点 2.94≈1+1.944** ✓，EWMFM 2.47==1+1.466，Index 1.22==1+0.225）；cumulative_all_markets（三市场 CPMM-EW/MV/Index 终点均对 metrics）；drawdown（CPMM-EW 谷≈-41.6%==MDD 0.4156）；rolling_volatility（量级对 AStd）；sa1（三区间×三市场柱高对 metrics 1.345/0.458/0.109…）；sa3（nc/w/λ 三面板逐点对 metrics，base 红点在第3列，w=8 骤降 0.45）；sa4（baseline 0.717、PMI 仅用 1.17 最高、剔除红柱全在 baseline 上=剔除任一不降）；weight_evolution（标注「每月约3只在仓」权重和=1）；asset_contribution（蓝正/红负，600809 居首=m3 medoid）。**无图表造假，与 metrics 一致。**

### skip/infeasible 理由核实（对照 data_catalog）
- **SA5 附录G ES**：skip=out_of_scope（optional 次相似变体、非主结论）——optional 元素、迁移聚焦主方法，理由成立。
- **SA6 6.1节 TDA**：skip=method_underspecified（ε/持续同调/异常阈值原文未给，AS27 佐证）——optional 且参数不可复现，理由成立。
- **UR 失业率降维（AS30）**：核 data_catalog 宏观区（macro_gdp/cpi/ppi/pmi/money_supply/social_financing/lpr/fixed_asset_investment/industrial_production/trade/cache）**确无任何失业率序列**，macro_cache 列亦无——本地无干净等价物、据实降维不强代理，理由成立（非本可衍生却偷懒）。
- **SF 社融剔除/DGDP 降维（AS35）**：社融各口径月度同比早期小基数剧烈波动（直接融资累计同比 |Δ|=926、社融总量同比 |Δ|=109，远超 CPI≈2.5/M2≈5），保留会污染 Δβ 的 X>0/X<0 分区；据实剔除、信用维度由 M2（|Δ|≈5 平稳，γ̃ hs300=0.935）承载——数据质量驱动的剔除、理由成立。
- 宏观映射 AS29（CPI/PPI/GDP/IP→对应 macro_*、IR→lpr/bond_yield_10y、M2/PMI 补充）所引本地文件均在 data_catalog 内、映射真实。
**结论：无 skip/降级理由不成立（非「本可衍生却偷懒」）。**

### 扰动测试触发判断复核（hard 必做）
- 触发：difficulty=hard → 必做一次；evidence_manifest 扰动节 + run_log 命令4 均有记录（exit=0，stdout `PERTURB_DONE`）。
- 扰动手段：TRAIN_END 2018-12-31→2017-12-31（TEST_START 不变），同进程 base vs perturbed。
- 核心指标相对变化：CPMM-EW hs300 SR 0.716811→0.521495=**27.25%**（>>0.1%），全核心最大 75.91%（PMM 累计）；base_SR=0.716811 与权威产物逐位同源。另 verify_report m5 段独立做溢出扰动（to_index 变 25-38%）、m6 段 TEST_END 扰动（SR 变 27.95%），三处独立扰动均显著解耦。
**结论：扰动已触发、已记录、核心指标变化远超阈值=输出耦合输入、无硬编码/解耦嫌疑。**

### 核验分级合理性核查（2026-07-10 契约项）
comparison.json 无 `verification_level` 字段（全部 tolerance_key=allocation.default experimental 豁免、无分级降级标记）——本案不涉分级降级，此子核查 N/A（无 unverifiable/direction-only 降级需核 AS 性质/diagnoser 出处/降档过度）。

### findings

| id | severity | 定位 | 描述 |
| --- | --- | --- | --- |
| RA-01 | minor | output/ssrn_6115073/verify_report.md:515-565（m7 里程碑段）vs :644（最终权威段） | verify_report 里程碑 m6/m7 段保留旧 tradeable-only 口径数字（如 m7 SA4 :562「PMI 剔除后 ΔSR −0.0610→最关键」、SA1 :520「1.0373」、SA2 :537「hs300 −0.1029」），与最终权威段（:644「PMI 剔除 +0.099、剔除任一 SR 不降=不依赖单因子」、SA1「1.345」、SA2「−0.3547」）及全部权威产物（comparison/metrics/xlsx/coverage_matrix 验证结果列，均 member 过滤后新口径）结论相反乃至翻转。已由 :610 表头「以下数字取代上文里程碑旧口径」及 coverage_matrix 变更日志（旧 verifier 列过时需重跑）显式披露、且权威产物内部自洽零偏差，故非数字不实/非造假；属文书卫生——下游若误引 m7 段过时段落可能传播相反 SA4 结论，建议 coordinator 清理或加行内过时标注。非阻断。 |

**说明**：K3/E4 三方零偏差、K2 无硬编码、措辞不夸大、skip/降级理由全成立、扰动已解耦——反虚报核心项全清；仅 RA-01 一条 minor 文书卫生项（已披露、不污染权威产物）。

**verdict**: pass_with_issues
