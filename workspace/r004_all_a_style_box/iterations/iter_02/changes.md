# r004_all_a_style_box iter_02 代码改动记录

## 改动范围

本轮严格按 `diagnosis.md` 的两个锁定修改点实施，只修改以下允许文件：

- `src/r004_all_a_style_box/config.py`
- `src/r004_all_a_style_box/portfolio.py`
- `src/r004_all_a_style_box/reporting.py`
- `src/r004_all_a_style_box/main.py`
- `tests/test_r004_all_a_style_box_portfolio.py`
- `tests/test_r004_all_a_style_box_reporting.py`
- `workspace/r004_all_a_style_box/iterations/iter_02/changes.md`

未修改 `output/`、`state.json`、`spec/plan/assumptions`、历史 iteration 或因子定义、PIT、T+1、成本、OOS 冻结参数。

## 修改点一：日/月账本桥接与交付唯一月表

### 实现位置

- `src/r004_all_a_style_box/portfolio.py:_monthly_record`
  - 保存每个长组合持有月四个不可覆盖的原始账本点：起始调仓前 VWAP NAV、调仓后当日收盘 NAV、月内最后收盘 NAV、下一次调仓前/终端 VWAP NAV，毛/净各一套。
  - 显式输出首桥、月内链、尾桥收益、直接 NAV 收益与三段乘积的 reconciliation error。
  - 单列调仓成本、事件成本及成本归属语义。
- `src/r004_all_a_style_box/portfolio.py:run_china_market_backtest`
  - 下一调仓日先为旧持有月写 `tail_bridge`，再为新持有月写 `first_bridge`；正常交易日写 `intramonth_chain`。
  - 日账本按 `holding_month + portfolio` 复合后与唯一月表勾稽，不再用调仓后收盘标签掩盖旧月尾桥。
- `src/r004_all_a_style_box/portfolio.py:calculate_style_factor_returns`
  - SMB/HML/GML 的正式月收益只使用已桥接四箱月收益再按冻结四腿公式线性合成。
  - 日频合成标记为 `daily_linear_diagnostic_not_monthly_compound_equivalent`，不冒充独立资金账本或正式月频因子。
- `src/r004_all_a_style_box/portfolio.py:assert_m3_invariants`
  - 增加四点账本、三段乘积、每月唯一首/尾桥、日账本复合与月表、月度四腿因子公式断言，容差取 `config.numeric_tolerance`。
- `src/r004_all_a_style_box/reporting.py:build_return_series`
  - 保留全部 `ledger_*` 原始字段，展示净值归一不覆盖账本 NAV。
- `src/r004_all_a_style_box/reporting.py:build_comparison_payload`
  - 数据驱动生成 R10 9 实体乘 3 指标共 27 个核心键；SA4 16 个实体-基准组合乘 3 指标共 48 个核心键。
  - 对缺失、重复、多余核心键及 SA4 非 16 行设置硬断言；删除 SA4 行数占位指标。
- `src/r004_all_a_style_box/reporting.py:build_boundary_disclosures`
  - 边界披露改为 `config + terminal_accounting_date` 纯函数；metrics、comparison、五工作簿共用同一结果。
- `src/r004_all_a_style_box/main.py:run_formal_pipeline`、`write_perturbation_replay_contract`
  - comparison/workbook 显式传入本次 config。
  - 扰动合同断言 R10=27、SA4=48、三类产物披露逐字一致，OOS 月数由日期集合动态重算；`2025-11-30` 扰动为 32 个月。

### 测试覆盖

- `tests/test_r004_all_a_style_box_portfolio.py:test_two_month_formal_oos_bridges_execution_boundaries_from_cash`
  - 覆盖连续两个月调仓切换、四个账本点、首/尾桥唯一性及日/月毛净收益勾稽。
- `tests/test_r004_all_a_style_box_reporting.py:test_comparison_required_keys_cover_exact_r10_and_sa4_core_values`
  - 覆盖 27+48 必需键、唯一性和计数。
- `tests/test_r004_all_a_style_box_reporting.py:test_boundary_disclosure_uses_runtime_config_and_terminal_date`
  - 覆盖 2023-04 至 2025-11 共 32 月与动态末期记账日。
- `tests/test_r004_all_a_style_box_reporting.py:test_perturbation_contract_is_independent_and_replayable`
  - 覆盖扰动 comparison 必需键、32 月边界及 metrics/comparison/workbook 披露一致。

## 修改点二：生命周期唯一估值状态与 unpriced 硬阻断

### 实现位置

- `src/r004_all_a_style_box/config.py:AllAStyleBoxConfig`
  - 集中声明可观察市场、显式结算、限期历史携带、unpriced、行为证据的固定估值优先级，并校验严格递增。
- `src/r004_all_a_style_box/portfolio.py:_has_auditable_valuation_path`
  - 只承认配置期限内的有效停牌/持有限制携带；尚未生效的公司行动只作候选证据。
  - `risk_exit` 不进入该接口，不能形成永久估值豁免。
- `src/r004_all_a_style_box/portfolio.py:_is_unexplained_missing_price_residual`
  - 超阈值无估值路径时与目标权重是否为零无关，仍持有的资产同样进入阻断。
- `src/r004_all_a_style_box/portfolio.py:_normalise_valuation_audit`
  - 将退出行为和估值候选归一到唯一 `(date, portfolio, stock_code)` 状态。
  - 保留候选来源、候选数量、冲突决议、行为动作、优先级、`selected_for_valuation`、选择理由、实际 mark、mark reconciliation error。
- `src/r004_all_a_style_box/portfolio.py:run_china_market_backtest`
  - 风险退出公告只触发真实可卖日退出尝试，不再进入生命周期豁免集合。
  - 对超期且无可审计路径的资产保留数量，但硬阻断完整 NAV、单点收益及 R4/R7/R10/SA4；错误信息明确禁止 `risk_exit` 永久豁免。
- `src/r004_all_a_style_box/reporting.py:validate_security_event_audit`
  - 新增唯一键、唯一 selected、冲突已决议、mark 对账、unpriced/blocking、risk_exit 超期豁免为零等断言。
- `src/r004_all_a_style_box/main.py:run_formal_pipeline`
  - 任何正式结果写盘前执行生命周期硬门禁；存在 unpriced/blocking 时非零退出，不写完整收益结论。

### 测试覆盖

- `tests/test_r004_all_a_style_box_portfolio.py:test_valuation_state_normalises_duplicate_behavior_and_unpriced_candidate`
  - 用 600466 式陈旧 risk_exit 候选验证同键双记录压成唯一 `unpriced_asset`，并保留退出行为证据。
- `tests/test_r004_all_a_style_box_portfolio.py:test_zero_target_residual_gate_scans_all_holdings_and_honours_exemptions`
  - 锁定 active suspension/risk_exit 不构成超期永久估值豁免。
- `tests/test_r004_all_a_style_box_portfolio.py:test_full_oos_blocks_unclosed_delisting_asset_instead_of_using_stale_mark`
  - 供 verifier 正式测试时确认未闭环资产触发非零硬阻断；coder 未运行该完整 OOS 测试。
- `tests/test_r004_all_a_style_box_reporting.py:test_security_event_validator_rejects_duplicate_valuation_keys`
  - 覆盖审计表重复估值键拒绝。

## 冒烟与定向测试

1. `python3 -m compileall -q src/r004_all_a_style_box tests/test_r004_all_a_style_box_portfolio.py tests/test_r004_all_a_style_box_reporting.py`
   - 结果：通过。
2. `.venv/bin/pytest -q ...`（桥接、状态归一、PIT/事件明细、收益层、实体审计、最终化、comparison、边界、扰动、图轴定向集合）
   - 结果：`13 passed, 12 deselected in 73.55s`。
3. `.venv/bin/pytest -q tests/test_r004_all_a_style_box_portfolio.py::test_two_month_formal_oos_bridges_execution_boundaries_from_cash`
   - 结果：`1 passed in 20.58s`。
4. `.venv/bin/pytest -q ...`（最终聚焦 comparison、边界、唯一状态、扰动及生命周期行为）
   - 结果：`4 passed, 21 deselected in 17.28s`。

环境说明：系统无 `python` 命令，且 `uv` 默认缓存目录受沙箱权限限制；最终使用仓库 `.venv/bin/python` / `.venv/bin/pytest` 完成冒烟与定向测试，未下载或修改依赖。

## 剩余边界与自检

- [x] 只改 diagnosis 允许的文件；未写 `output/`、`state.json`、spec/plan/assumptions 或历史 iteration。
- [x] 未改 Size、Value、Growth 定义，未新增其他因子族，未改 PIT、T+1、成本和正式 OOS 参数。
- [x] 日/月桥接、月度四腿因子、R10 27 项、SA4 48 项、动态 32 月扰动边界均有定向测试。
- [x] 生命周期选择优先级、唯一键、唯一 selected、选择理由、mark 对账和 risk_exit 非豁免均有实现与断言。
- [x] 未使用未来报价、虚构 VWAP/成交/结算、追溯结算或强制零值。
- [x] 未闭环资产采用 diagnosis 明确允许的硬阻断路径，不属于 coder 主动简化，未新增 assumptions 条目。
- [ ] 六个长组合正式 33 月共 198 个实体月、三个合成因子 99 个实体月及 600466/其余证券的全量数值，须由 verifier 正式重跑后独立核验；coder 不声明数值达标或 PASS。
- [ ] 若正式本地证据触发 unpriced 硬阻断，verifier 应据实保留非零退出与阻断证据，不得将其改写成完整可估值 NAV。

仅代码冒烟，正式结果待 verifier。
