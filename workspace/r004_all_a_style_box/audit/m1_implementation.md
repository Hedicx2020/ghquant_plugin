# m1 动态全A与PIT数据底座实现记录

## 派发范围

- milestone: `m1`
- elements: `D14`, `B1`, `B10`
- 实现文件: `src/r004_all_a_style_box/{config.py,data_pipeline.py,__init__.py}`
- 未实现: m2 风格复合与四箱分组、m3 回测与成本、m4 正式结果与报告

## 稳定下游接口

入口：`build_m1_dataset(config=None, smoke_months=None, smoke_stock_limit=None) -> M1Dataset`

`M1Dataset` 固定包含：

1. `schedule`：`signal_date/execution_date/return_date/holding_month/sample_phase`；完整持有月为 2015-01 至 2025-12，正式 OOS 为 2023-04 至 2025-12。
2. `monthly_panel`：每个 `signal_date,stock_code` 唯一，含交易所时点状态、上市龄、T日行情成交市值与状态、T+1方向性可成交标记、同复权口径的`execution_vwap/return_vwap`、可重算`gross_holding_return`、T日估值、PIT当期/上年同期财务原料及对称同比。
3. `exclusion_audit`：逐月候选数、合格数及每项排除标记计数。
4. `availability_audit`：总/流通市值、B/P、E/P、S/P、股息率、营收/净利润当期与上年同期、对称同比的逐月覆盖率，`missing_policy=no_bfill`。
5. `source_catalog`：由实际读取路径生成的本地文件、加载区间/行数与PIT规则；是否引用指数成分/外部路径由解析后的真实路径计算，不使用预写常量自证。
6. `exchange_code_audit`：逐信号日、原始代码前缀、交易所生效状态的候选/合格/疑似代码沿革重复计数。

合成回归入口：`run_m1_synthetic_regression_checks()`，覆盖乱序PIT、多版本、北交所开市边界、VWAP转换和上市龄119/120日边界。

## 时点与股票池口径

- 持有月前一自然月最后交易日为 T，下一交易日执行，下一持有月执行日为收益端点；首期 2015-01 因此使用 2014-12 月末信号。
- 候选来自 T 日前复权行情与成交记录的并集；不读取 `ashare_index_components.parquet`，不使用 CSI 800。
- `list_state` 只保留为 `current_list_state_audit`，不参与任何历史过滤。当前主表缺失的历史证券以其首个真实行情/成交日作为保守上市龄起点，避免用最终主表删除退市样本；来源列为 `listing_date_source`。
- 北交所保留原始代码并透明标注：`43/83/87/88/92`号段仅从2021-11-15开市日起标为`exchange=BJ, board=BSE`；此前标为`PRE_BSE_NEEQ/NEEQ`并排除。全程`code_mapping_applied=False`，同日同名多代码的疑似沿革重复全部标记并排除，不静默改码。
- T 日剔除 ST、停牌、涨停、跌停、无有效行情、无量/无成交额、总市值非正、上市龄不足 120 交易日；T+1 另算 `can_buy_t1/can_sell_t1`，不反向影响 T 日合格池。
- 估值仅接受 `valuation_date == signal_date` 的原始记录；财务先满足 `info_publ_date <= signal_date`，再选当时最新 `end_date`，上年同期由该财政期减一年匹配。PIT排序后只用显式`_row_id`一对一merge恢复，不使用位置索引回写；代码无bfill。
- T+1与收益端点从`ashare_stock_price.parquet.vwap`读取未复权VWAP。以`raw_close × adj_factor / forward_close`反推前复权归一化常数，再将原始VWAP转换到前复权口径；转换收盘价必须重构`forward_close`，原始VWAP必须为正、有限且位于同日raw low/high内。无效时不可成交，严禁close替代或后续填充。
- `gross_holding_return = return_vwap / execution_vwap - 1`；另提供同时满足T+1可买与收益端点可卖的`gross_holding_return_executable`，交易延迟处理仍留给m3。

## 真实数据最小 smoke（非正式回测）

- 命令：`python3 -c 'from src.r004_all_a_style_box import build_m1_dataset; d=build_m1_dataset(smoke_months=1)'`
- 合成回归：3行乱序、多股票、多信号日、同财政期多版本均按原键恢复；未来披露0；VWAP 9.8在示例中转换为4.9，零VWAP无效；上市龄边界为119/120。
- 2015-12：信号日2015-11-30，候选2,781、合格2,229；BJ候选/合格均0，开市前股转号段3；执行/收益VWAP非空2,778/2,777，毛收益2,374，未来披露0。
- 2021-10：信号日2021-09-30，候选4,566、合格3,969；BJ候选/合格严格为0，`PRE_BSE_NEEQ`候选75；执行/收益VWAP非空4,557/4,556，毛收益4,537，未来披露0。
- 2025-12：时序为2025-11-28信号、2025-12-01执行、2026-01-05收益端点；候选5,453、合格5,135，沪/深/北合格2,173/2,698/264。
- 候选 5,453 行，合格 5,135 行；沪/深/北候选分别 2,292 / 2,876 / 285，合格分别 2,173 / 2,698 / 264。
- 上市日期来源：主表 5,432 行，历史首个真实行情/成交记录 21 行；当前 `list_state` 未参与过滤。
- 主要排除计数：ST 175、涨停 82、上市龄不足 53、停牌 21、无量或无成交额 21、跌停 6；原因可重叠。
- PIT 当期财务 5,046 行，营收/净利润对称同比各 5,046 行；B/P、E/P、S/P、股息率可用数分别 5,409 / 3,913 / 5,446 / 3,769。
- 2025-12执行/收益VWAP非空各5,450，毛收益5,418，可执行毛收益5,330；T+1可买5,353、可卖5,421。三期均无“可交易但VWAP无效”记录，毛收益可由两个VWAP端点逐行重算。模块断言使用真实连接键、价格重构与解析后的实际路径，不读取预写来源布尔值自证。

## 已知风险（留给 verifier/auditor 判断）

- 本地 `ashare_stock_value.parquet` 的历史 T 日覆盖不均；实现严格保留缺失，不以最近估值填充，早期月份覆盖率可能较低。
- 当前 `ashare_stock.parquet` 的 `list_state` 全为当前快照，不能恢复历史退市日期；实现依赖历史日记录纳入退市证券，并对主表缺失证券用首个真实观测日计上市龄，`listing_date_source` 可逐行复核。
- 少量历史北交所旧代码与92新代码并存；实现不做主观映射，同日同名多代码会全部排除并进入`exchange_code_audit`。这避免重复计入，但可能保守损失该证券当月样本，需verifier检查实际触发数量。
- `gross_holding_return`是冻结VWAP端点的原料收益；收益端点跌停/停牌导致的延迟退出、成本和仓位延续由m3处理，`gross_holding_return_executable`仅明确“当期端点可完成买卖”的可审计子集。
- 本记录只证明最小真实数据调用可执行，不代表完整回测、数值复现或门禁通过。
