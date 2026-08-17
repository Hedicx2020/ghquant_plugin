# Iteration 01 实现复审

## 复审范围与冻结对象

- 复审对象：`impl_audit_iter_01.md` 中 IA-01 至 IA-05。
- 复审方式：同一审计者独立重读最新 `assumptions.md`、`iterations/iter_01/changes.md`、相关实现和新增故障注入测试；不采信变更说明中的自述。
- 未执行正式 `main.py`，未修改策略代码、测试、状态或正式输出。
- 冻结文件 SHA-256：
  - `workspace/r004_all_a_style_box/assumptions.md`：`d0652e2ba0d5f862a272f621a1dad6d6f22d5d83f7f2dab219c3d7c651bab223`
  - `workspace/r004_all_a_style_box/iterations/iter_01/changes.md`：`34944a245939c0beee5a1594a17d4ab368244bf013357be2d83d5ed7cbbed052`
  - `src/r004_all_a_style_box/portfolio.py`：`49c06310533da65e30867f50c0a2284f7a6b9c8b105b1b638ecc4dc0649f43b8`
  - `src/r004_all_a_style_box/reporting.py`：`37bc8fa48fb1101554f989f56c09bad6d068d17b6a21830c3fe264a5db22e555`
  - `tests/test_r004_all_a_style_box_portfolio.py`：`ae279ee9b4ce4d963d35127c253d5021d42feabba81807153d1133bd1dd2c179`
  - `tests/test_r004_all_a_style_box_reporting.py`：`f27ad6ec5a5f62bde4933c5333f3637c061221f4c74670fe5bb612450ea53cad`

## 逐项复审

### IA-01：退市风险退出绕过跌停卖出约束

状态：**closed**

证据：

- `portfolio.py:965-1096` 的退市风险退出先读取 `daily_can_sell`；不可卖时保留真实持仓，不生成成交和成本，并记录 `risk_exit_waiting_daily_can_sell`，执行 VWAP 与成交量保持缺失。
- 首个 `daily_can_sell=True` 的交易日才按该日真实 `daily_vwap`、真实成交量及完整成本退出并移除持仓。
- 故障注入测试 `test_risk_exit_waits_through_limit_down_until_first_daily_can_sell` 明确构造“跌停但有有效 VWAP 和成交量”：跌停日不成交、持仓保留；下一可卖日按 VWAP 8.5 成交，日期、成交量和成本均核对一致。

结论：原问题已关闭；有效价格和成交量不再绕过跌停不可卖约束。

### IA-02：两次调仓零目标残仓检测仅覆盖缺失收盘价持仓

状态：**closed**

证据：

- `portfolio.py:1099-1228` 的零目标残仓检测遍历全部当前持仓 `state.shares.index`，不再依赖收盘价缺失集合；连续两次目标为零后，对非生命周期豁免且当前可卖的残仓执行真实 VWAP 退出。
- `portfolio.py:1724-1936` 将停牌、待处理公司行动和待市场退出纳入明确生命周期豁免，同时保留缺失价格的陈旧残仓阻断；未解释残仓超过阈值仍会阻断。
- `test_zero_target_residual_gate_scans_all_holdings_and_honours_exemptions` 验证：有效收盘价持仓也会被发现；停牌或生命周期事件中的持仓不会被误报；实际退出使用 VWAP 9.5 并核对成本与审计记录。
- `test_full_oos_resolves_security_lifecycle_without_stale_residual` 跑过完整 33 个月生命周期场景：无未解释残仓/陈旧残仓阻断；`600466` 明确存在于 `waiting_for_daily_can_sell` 事件中，等待期执行 VWAP、成交量为空且持仓仍为正，未静默消失；实际退出事件的 VWAP、成交量为正。

结论：原问题已关闭；检测覆盖全部持仓，且 `600466` 等明确生命周期事件可等待而不会误消失。

### IA-03：PIT 证据校验器信任派生 rank/score，无法识别底层篡改

状态：**closed**

证据：

- `reporting.py:1839-2272` 从原始期间值、披露日和 TTM 腿开始重建财务值与估值比率，再重算截尾值、排名、分数和风格标签；同时检查披露时点、财年键、分母和标签映射，任一层不一致均拒绝。
- `test_pit_validator_rejects_each_tampered_numeric_layer` 与 `test_pit_validator_rejects_tampered_style_box_label` 覆盖底层比率、TTM 腿、winsor、rank、score 与 label 篡改。
- 审计者另行逐层独立注入 `book_to_price`、`ttm_revenue`、`book_to_price_winsorised`、`book_to_price_rank`、`value_score`、`style_box` 单字段篡改，六类结果均为 `REJECTED`；有效 fixture 的重建误差不超过 `1e-12`。

结论：原问题已关闭；raw、TTM、winsor、rank、score、label 任一层篡改都会失败。

### IA-04：终态生成器允许 assumptions 不完整或保留回看占位

状态：**closed**

证据：

- `reporting.py:63-91,1725-1769` 固定要求 AS1 至 AS24 恰好完整、不得重复，且每项 12 个字段均非空；`验证后回看` 中存在 `[verify 后填]` 或 pending 类占位即拒绝。
- `validate_verification_context` 在校验正式上下文和哈希前调用该登记簿完整性检查，不能绕过。
- `test_finalizer_rejects_incomplete_assumption_registry` 覆盖缺失 ID、重复 ID、缺失必填字段和 `[verify 后填]`；完整 AS1 至 AS24 fixture 可通过终态生成。
- 对最新真实 `assumptions.md` 直接调用校验器得到拒绝：AS1 至 AS24 共 24 项虽齐全，但 AS12、AS14、AS15、AS18、AS20、AS24 的 `验证后回看` 仍为占位。该拒绝是预期行为；正式终态前须由 verifier 回填这六项。

结论：原问题已关闭；当前真实登记簿不会被错误放行，尚未回填的六项是后续正式验证前置条件，不构成本轮代码缺陷仍开放。

### IA-05：月频目标参考收益的可用性语义与实现矛盾

状态：**closed**

证据：

- `reporting.py:92-98,240-245,347-363` 统一约定：月频目标参考收益可用，日频目标参考收益不可用，日频不得以实际组合毛收益伪装目标参考；可用标记必须严格等于 `frequency == monthly`，不一致即报错。
- `test_three_return_layers_and_cumulative_cost_reconcile` 验证月频逐期 `available=True`、日频逐期 `available=False`，并核对 `monthly_available`、`daily_unavailable` 合同文本和统一说明。

结论：原问题已关闭；月频 available、日频 unavailable 的数据、标记和说明语义一致。

## 独立测试结果

执行了九个定向测试节点（参数化展开为 16 个用例），包括完整 33 个月生命周期场景、六层 PIT 篡改、assumptions 完整性/占位拒绝及月日频目标参考语义。结果：

```text
16 passed in 158.98s (0:02:38)
```

未运行正式 `main.py`，也未据此生成或改写正式结果。

## 总结

IA-01 至 IA-05 均已关闭；本轮限定复审范围内未发现仍开放问题。最新真实 assumptions 登记簿仍有六项回看占位，终态校验器已按设计拒绝，必须在正式验证后回填才能最终生成。

verdict: pass
