# r004_all_a_style_box iter_01 实现审计

## 审计范围与结论

- 审计模式：code audit；未修改 `src/`、`tests/`、`state.json`，未运行正式 `main.py`，未写正式 `output/`。
- 审计依据：`spec.md`、`plan.md`、`assumptions.md`、`iter_01/diagnosis.md`、`iter_01/changes.md`、指定实现文件与 r004 定向测试。
- 写报告前重新读取的最新假设登记簿 SHA-256：`d0652e2ba0d5f862a272f621a1dad6d6f22d5d83f7f2dab219c3d7c651bab223`。
- 代码冻结摘要：`config.py=09501f...`、`data_pipeline.py=798ba9...`、`strategy.py=f484e7...`、`portfolio.py=79c3c6...`、`reporting.py=c9e879...`、`main.py=86e8f2...`、`workbook_builder.mjs=147f4c...`。
- 结论：失败。PIT/TTM、Value 三核心、正式 OOS 全现金初始化、公司行动显式映射、三层收益字段、12 张明细表、工作簿 QA 和独立扰动合同的主结构均已实现；但仍有 1 项 critical、3 项 major、1 项 medium，不能进入正式 verifier 全量重跑。

## 已确认实现

1. `data_pipeline.py:455-475,501-549,569-662,739-809,1210-1279` 先按 `info_publ_date <= signal_date` 选版本，非年末按 `current_ytd + prior_fy - prior_ytd` 重建 TTM；B/P、正 TTM E/P、正 TTM S/P 与不超过 5 个交易日的可选 `dv` 已落地，未见 bfill。
2. `strategy.py:351-395` 的 Value 仅由 B/P、E/P、S/P、fresh dv 构造，三核心至少 2 项；Growth 仍为两项 PIT 对称增长，Size 仍只用总市值。
3. `portfolio.py:1460-1500` 在首个正式 OOS 执行日前把六个长组合重置为 `NAV=1` 全现金，不携带预热期仓位、现金或累计成本。
4. `portfolio.py:1738-1770`、`reporting.py:203-406` 已拆出目标参考、实际成本前、实际成本后三层字段，并对同一实际持仓的累计成本差作勾稽。
5. `reporting.py:1998-2320`、`main.py:366-426,483-581` 已建立 12 张 Parquet 明细、工作簿 pending/finalize 两阶段入口与独立扰动目录/基线 SHA 不变合同；`workbook_builder.mjs` 对 inspect、render、公式错误、原生图表、OOXML 和 A2 冻结实施了实际 QA。

## 审计问题

### IA-01 退市风险退出绕过冻结的跌停禁卖规则

- 严重度：critical
- 证据：`portfolio.py:985-993` 把“有效 VWAP、非停牌、有成交量”直接定义为公告驱动退出可成交条件，没有使用同文件 `316-321` 已正确包含 `~daily_limit_down` 的 `daily_can_sell`。随后 `998-1065` 全额卖出、计成本并删除持仓。该路径与 `assumptions.md:137`、`plan.md:94` 的“跌停不得卖出”以及 `diagnosis.md:45,65` 的“下一真实可卖日”冲突。
- 独立复现：构造 `daily_limit_down=True`、`daily_can_sell=False`、有效 VWAP 且成交量为正的持仓，直接调用 `_execute_delisting_risk_exit()`，观察到 `trade_rows=1`、`shares_remaining=0.0`、`executed_vwap=9.0`。这不是测试缺失的理论分支，而是可执行的虚构卖出路径。
- 修复出口：公告只决定“应退出”，不能覆盖交易所方向限制。候选条件必须要求 `daily_can_sell=True`，或以等价字段同时证明有效 VWAP、非停牌、有成交且非跌停；不可卖日继续持有并写审计行，直到首个真实可卖日。
- 验收出口：新增故障注入测试，跌停且有真实成交量时成交 0、仓位保留；解除跌停后的首个 `daily_can_sell=True` 日才全额退出，成交日、VWAP、成本和事件审计可重算。

### IA-02 “连续两次零目标残仓”阻断只检查缺收盘价证券

- 严重度：major
- 证据：`portfolio.py:1544-1561` 先把检查集合限定为 `missing_today = held_codes - observed_close_codes`，`1588-1600` 才在该子集内检查 `zero_target_rebalances >= 2 and daily_can_sell`。因此，只要残仓当日存在正常收盘价，该证券根本不会进入循环；即使已连续两次调仓目标为 0、当前非停牌且已经可卖，也不会阻断。`1657-1658` 的报错还只描述“超过20日无行情”，掩盖了第二个门禁。
- 影响：两次调仓均因限制未卖出的证券，在之后恢复正常交易但尚未到下一月调仓时，可以继续作为无理由残仓进入收益和权重链，违反 `diagnosis.md:75` 的独立验收条件。现有 `tests/test_r004_all_a_style_box_portfolio.py:39-107` 只断言最终实际样本没有 blocker，没有覆盖“有正常收盘价的两次零目标残仓”。
- 修复出口：价格年龄检查可继续只遍历缺价持仓，但零目标次数检查必须遍历全部在持仓证券；显式持有限制/未生效或待结算事件才可豁免。恢复可卖后应按冻结规则执行退出，或在正式入口阻断，不能静默等到下一月。
- 验收出口：新增三组状态测试：缺价超过 20 日阻断；两次零目标且当前可卖、即使有正常 close 也阻断或退出；有当日已知停牌/公司行动理由时不误报。

### IA-03 PIT 明细“独立重算”可在原始估值与 TTM 被篡改时假通过

- 严重度：major
- 证据：`reporting.py:1796-1849` 直接使用交付表中已经生成的 `*_rank` 列求 Value/Growth/Style，只核对得分；没有从 B/P、E/P、S/P、dv 和 Growth 原始值重新做 1%/99% 缩尾与横截面秩，也没有从市值、权益及 TTM 三段值复算 B/P/E/P/S/P。`1924-1934` 只核对来源日不晚于信号日。
- 独立复现：把测试 PIT 表的 `book_to_price` 改为 `999`、`earnings_to_price` 改为 `-123`、`sales_to_price` 改为 `0`，并把 `ttm_revenue/ttm_net_profit` 改为 `-1e9`，保持既有 rank/score 不变，`validate_pit_style_inputs()` 仍返回 Value/Growth/Style 最大误差约 `1.11e-16/0/1.11e-16`、未来披露 0，判定通过。
- 影响：`pit_style_inputs.parquet` 无法独立证明 Value/Growth/Style 来自所披露的 PIT 原料，未满足 `diagnosis.md:99,108` 的“由该表独立重算”证据合同；错误或被污染的 rank/score 可以相互自洽地假绿。
- 修复出口：验证器必须从原始字段逐层重算：PIT/TTM 三段与来源日、B/P/E/P/S/P、dv 新鲜度、1%/99% 缩尾、百分位秩、有效分量数、Value/Growth/Style、Size/Style 二分和四箱标签；不得把待验证 rank 当作可信输入。
- 验收出口：为每一层加入单字段篡改故障注入，任何 raw ratio、TTM leg、winsorised、rank、score 或标签篡改均须非零失败；未改 fixture 最大误差仍 `<=1e-12`。

### IA-04 工作簿最终化未阻断不完整的 24 条验证后回看

- 严重度：major
- 证据：最新 `assumptions.md` 的 AS12、AS14、AS15、AS18、AS20、AS24 仍为 `验证后回看: [verify 后填]`。`reporting.py:1642-1673` 会解析这些占位文本；`1691-1727` 最终化只校验行数为 24 和整表 SHA，不校验 ID 精确为 AS1--AS24、唯一性、必需字段或“验证后回看”是否已填写。`tests/test_r004_all_a_style_box_reporting.py:277-319` 甚至用只有 `assumption_id/title` 的 24 行表成功生成 `verified/PASS` 工作簿。
- 影响：只要 verifier context 对当前占位表重新计算 SHA，5 本工作簿即可显示 `verified/PASS`，同时 Assumptions 仍含六条未回看项，违反 `diagnosis.md:98,110,121-130` 的 24/24 当前回看门禁。
- 修复出口：最终化前强制验证精确且唯一的 AS1--AS24；要求登记簿必需字段齐全，所有“验证后回看”非空且不含 `[verify 后填]`、`pending` 等占位；再对该合格表计算并核对 context SHA。
- 验收出口：增加缺 ID、重复 ID、缺字段、任一占位回看四类拒绝测试；只有 24 条完整当前回看才能生成 `verified/PASS`，pending 阶段仍允许保留占位但不得最终化。

### IA-05 目标参考收益的公开语义与实际月度输出矛盾

- 严重度：medium
- 证据：`reporting.py:51-57,207-211` 把 `target_reference_return` 的统一语义写成“当前正式执行链未单独输出”，但 `portfolio.py:1738-1767` 已对月度长组合实际生成该字段，`1866-1884` 也生成月度风格因子目标参考收益；`reporting.py:319-330` 还会把月度该层标记为 available。该矛盾会同时进入 Excel Checks、指标定义和报告措辞。
- 修复出口：把语义改为“月度目标参考可用、日频不可用”，并在字段级明确频率；不得用实际成本前收益代替日频目标层。
- 验收出口：月度 `target_reference_available=True`、日频为 False，语义文本与表内可用标志逐行一致，Excel 标题和 metrics 定义使用同一措辞。

## 定向测试记录

- 命令：`uv run pytest -q tests/test_r004_all_a_style_box_data.py tests/test_r004_all_a_style_box_portfolio.py tests/test_r004_all_a_style_box_reporting.py tests/test_r004_workbook_freeze.py`
- 结果：`14 passed in 217.58s`，exit=0。
- 审计解释：现有测试证明主结构可以运行，但没有覆盖 IA-01、IA-02、IA-03、IA-04 的故障注入；因此绿灯不能作为本轮 code gate 通过依据。

verdict: fail
