# 本地数据目录（data_catalog）

> 供 `quant-pdf-reader` **分诊**时对照，判断研报所需数据在本地是否可得，避免每次扫描 10GB。
> 数据根目录：`~/local_data/`（即 `Path.home()/"local_data"`），全部为 **parquet** 格式。
> 加载方式：`pd.read_parquet("~/local_data/<file>.parquet", columns=[...])`。
> 通用约定：日期列多为 `date`；`JSID` 为数据源内部 ID，可忽略；股票代码列为 `stock_code`（6 位，如 `600000`）。

## 如何标注 data_requirement 的 status

- `available`：下表直接有对应文件与字段 → 可直接加载。
- `derive`：本地有原料但需衍生计算（如：日收益率由 `change_pct` 或 `close/prev_close-1` 得到；月频由日频重采样；行业市值中性化所需暴露由现有字段构造）。
- `missing`：下表无对应数据，且无法由现有数据衍生（如：分钟/tick 级数据、龙虎榜个股明细外的另类数据、Wind/朝阳永续特有指标、舆情/文本/卫星等另类数据）。

---

## A 股 · 个股行情与交易

| 文件 | 关键字段 | 覆盖 | 用途 |
|------|---------|------|------|
| `ashare_stock_price.parquet` | stock_code, date, prev_close, open, high, low, close, vwap | 2000-01 ~ 至今(日) | 未复权日行情、振幅、VWAP |
| `ashare_stock_price_forward.parquet` | + adj_factor | 2000-01 ~ 至今(日) | **前复权**日行情（回测算收益优先用） |
| `ashare_stock_price_backward.parquet` | + adj_factor | 2000-01 ~ 至今(日) | 后复权日行情 |
| `ashare_stock_trade.parquet` | stock_code, date, volume, market_value, negotiable_market_value, turn_value, turnover_rate, turnover_rate_free, change_pct, range_pct | 2000-01 ~ 至今(日) | 日涨跌幅、成交、换手、总/流通市值 |
| `ashare_stock_value.parquet` | stock_code, date, pe_ttm, pb_lf, pcfs_ttm, ps_ttm, dv, dv_report | 日 | 估值因子（PE/PB/PS/股息率） |
| `ashare_stock.parquet` | stock_code, stock_name, list_date, list_state | 全量 | 上市日期、上市状态（剔除新股/退市） |

> 个股 **日收益率**：`ashare_stock_trade.change_pct`（百分比）或前复权 `close/prev_close - 1`。无分钟/tick 数据。

## A 股 · 状态过滤

| 文件 | 关键字段 | 用途 |
|------|---------|------|
| `ashare_stock_st.parquet` | stock_code, implement_date, remove_date | ST 区间（剔除 ST） |
| `ashare_stock_suspend.parquet` | stock_code, date, if_suspend | 停牌（剔除停牌日） |
| `ashare_stock_limit.parquet` | stock_code, date, stock_board, limit_board, surged_limit, decline_limit, change_pct | 涨跌停标记（剔除涨跌停） |
| `ashare_stock_industry.parquet` | stock_code, first/second/third_industry_name, standard_code | 行业分类（中性化用）。`standard_code=37` 中信一级，`38` 申万一级 |
| `ashare_tradeday.parquet` | date, IfTradingDay, IfWeekEnd, IfMonthEnd, IfQuarterEnd, IfYearEnd | 交易日历、月末/周末/季末标记（调仓日） |

## A 股 · 财务报表（季频/年频，字段数百，按需取列）

| 文件 | 内容 | 关键定位字段 |
|------|------|------|
| `ashare_stock_balance.parquet` | 资产负债表（total_assets, total_liability, total_shareholder_equity …约 240 列） | stock_code, end_date, info_publ_date |
| `ashare_stock_income.parquet` | 利润表（total_operating_revenue, operating_profit, net_profit, basic_eps …） | stock_code, end_date, info_publ_date |
| `ashare_stock_income_q.parquet` | 利润表**单季** | stock_code, end_date, mark |
| `ashare_stock_cashflow.parquet` | 现金流量表（net_operate_cash_flow …） | stock_code, end_date, info_publ_date |
| `ashare_stock_cashflow_q.parquet` | 现金流**单季** | stock_code, end_date, mark |
| `ashare_stock_equity.parquet` | 股东权益变动 | stock_code, end_date, items_name |

> 用财务数据务必用 `info_publ_date`（披露日）做时点对齐，**防未来函数**（`end_date` 是报告期，披露滞后）。

## 指数

| 文件 | 关键字段 | 覆盖 | 备注 |
|------|---------|------|------|
| `ashare_csiindex_trade.parquet` | index_code, date, OHLC, close, turnover_volume/value, change_pct, total_mv, pe, dv | 较广(日) | 中证系列指数，**含 OHLC+估值，指数行情优先用此表** |
| `ashare_index_value.parquet` | index_code, date, market_value, negotiable_market_value, pe_ttm, pb_lf, ps_ttm, dv | 日 | 指数估值（PE/PB 分位择时常用） |
| `ashare_index_trade.parquet` | index_code, date, turnover_volume/value, change_pct, negotiable_market_value | 日 | 指数成交/涨跌幅 |
| `ashare_index_price.parquet` | index_code, date, OHLC | **仅 2015~2016，覆盖窄** | 慎用，宽时间用 csiindex_trade |
| `ashare_index_components.parquet` | stock_code, in_date, out_date, index_code | 历史 | 指数成分股进出（沪深300=`000300` 等），构造股票池 |
| `ashare_index.parquet` / `ashare_index_basicinfo.parquet` | index_code, index_name, base_date … | - | 指数基础信息 |

## 债券

| 文件 | 关键字段 | 覆盖 | 用途 |
|------|---------|------|------|
| `bond_yield_curve.parquet` | date, curve_code, curve_name, years_to_maturity, yield_type, yield_value | 2015-01 ~ 2025(日) | **国债/各类收益率曲线**（期限利差、久期定价） |
| `bond_exchange_quote.parquet` | date, bond_code, accrued_interest, net/dirty price OHLC, change_pct, turnover, years_to_maturity | 2015-01 ~ 至今(日) | 交易所债券净价/全价行情 |
| `bond_basic_info.parquet` | bond_code, coupon_rate, par_value, issue/value/maturity_date, credit_rating, maturity_days … | 全量 | 债券要素（票息、期限、评级） |
| `bond_cashflow.parquet` | bond_code, payment_date, interest_per, payment_per, cashflow | - | 债券现金流（YTM/久期） |
| `bond_rating.parquet` | bond_code, rating_date, rating, rating_agency | - | 信用评级 |
| `bond_default.parquet` | bond_code, default_date, default_type, payable_amount | - | 违约事件 |
| `bond_index_quote.parquet` | index_code, date, OHLC, change_pct | - | 债券指数行情（中债系列） |
| `bond_shibor.parquet` | date, maturity_raw, rate | - | SHIBOR 各期限利率 |
| `bond_code.parquet` | bond_code, bond_type_level1/2, issuer | - | 债券分类/发行人 |

## 可转债

| 文件 | 关键字段 | 覆盖 | 用途 |
|------|---------|------|------|
| `convertible_bond_quote.parquet` | bond_code, date, OHLC, convert_price, stock_price, convert_value, convert_premium_rate, years_to_maturity | 2015-01 ~ 至今(日) | 转债行情、转股溢价率、转股价值 |
| `convertible_bond_basic.parquet` | bond_code, stock_code, coupon_rate, initial/latest_convert_price, convert_start/end_date, issue_size | 全量 | 转债要素、正股映射 |
| `convertible_bond_convert_price.parquet` | bond_code, valid_date, convert_price, change_reason | - | 转股价调整历史 |
| `convertible_bond_convert_info.parquet` | bond_code, date, convert_price, remaining_amount, converted_ratio, call/put_ratio | - | 转股/赎回/回售进度 |

## 基金

| 文件 | 关键字段 | 覆盖 | 用途 |
|------|---------|------|------|
| `fund_netvalue.parquet` | fund_code, date, unit_netvalue, re_unit_netvalue, daily_growth_rate | 2000-01 ~ 至今(日) | 基金净值（复权净值 re_ 前缀） |
| `fund_stock_portfolio.parquet` | fund_code, date, stock_code, shares_holding, market_value, ration_in_nv | 季报 | 基金重仓股全持仓 |
| `fund_keystock.parquet` | fund_code, date, stock_code, market_value, ration_in_nv | 季报 | 前十大重仓 |
| `fund_bond_portfolio.parquet` | fund_code, date, bond_code, market_value | 季报 | 基金债券持仓 |
| `fund_assetallocation.parquet` | fund_code, date, asset_type, market_value, ratio_in_asset | 季报 | 大类资产配置比例 |
| `fund_sharperatio.parquet` | fund_code, date, index_cycle, fund_sharperatio | - | 基金夏普 |
| `fund_code.parquet` | fund_code, fund_type, benchmark, if_index, establishment_date, manager | 全量 | 基金分类/基准/经理 |
| `fund_chargerate.parquet` / `fund_tradeinfo.parquet` / `fund_managernew.parquet` | 费率 / 换手 / 经理 | - | 辅助 |
| `fund_qdii_*` | QDII 持仓/配置 | - | 海外基金 |

## 期货

| 文件 | 关键字段 | 覆盖 | 用途 |
|------|---------|------|------|
| `financial_future_price.parquet` | date, contract_code, contract_name, OHLC, settle, hold_volume, volume, basis_value, basis_annual_yield, main_contract | 2010-04 ~ 至今(日) | **金融期货**（国债期货、股指期货），含基差、主力合约标记 |
| `futures_contract.parquet` | contract_code, multiplier, min_margin_ratio, contract_month, delivery_date | - | 合约规格（乘数、保证金） |
| `member_rank.parquet` | date, contract_code, member_name, indicator_volume | - | 期货会员持仓排名（龙虎榜） |

## 宏观（多为月频/季频，统一结构 date, indicator_name, data_value）

| 文件 | 内容 | 覆盖 |
|------|------|------|
| `macro_gdp.parquet` | GDP | 1990 ~ 至今(季) |
| `macro_cpi.parquet` / `macro_ppi.parquet` | CPI / PPI | 月 |
| `macro_pmi.parquet` | PMI | 2005 ~ 至今(月) |
| `macro_money_supply.parquet` | M0/M1/M2 货币供应 | 月 |
| `macro_social_financing.parquet` | 社融 | 月 |
| `macro_lpr.parquet` | LPR 利率 | - |
| `macro_fixed_asset_investment.parquet` | 固定资产投资 | 月 |
| `macro_industrial_production.parquet` | 工业增加值 | 月 |
| `macro_trade.parquet` | 进出口 | - |
| `macro_cache.parquet` | 宽表：cpi_yoy, ppi_yoy, bond_yield_10y, credit_spread, term_spread, m1_yoy, m2_yoy, social_financing_yoy, gdp_real_yoy … | 月(约483期) | **宏观择时/资产配置常用衍生指标，一表打包** |
| `macro_indicator_main.parquet` | 宏观指标元数据字典（indicator_code → 名称/频率/起止） | - | 查指标编码 |

## 港股 / 美股 / 海外

| 文件 | 关键字段 | 覆盖 | 用途 |
|------|---------|------|------|
| `hkshare_stock_quote.parquet` | stock_code, date, OHLC, vwap, volume, change_pct, currency | 2000-10 ~ 至今(日) | 港股个股行情 |
| `hkshare_index_price.parquet` | index_code, date, OHLC, change_pct | 日 | 港股指数（恒生等） |
| `usshare_stock_quote.parquet` | stock_code, date, OHLC, volume, market_cap, eps_ttm, change_pct | 2000-01 ~ 至今(日) | 美股个股行情 |
| `osshare_index_price.parquet` | index_code, date, OHLC, change_pct | 日 | 海外/中概指数行情 |
| `usshare_index.parquet` / `hkshare_stock.parquet` / `usshare_stock.parquet` | 基础信息 | - | 代码表 |

## 因子库

| 文件 | 关键字段 | 用途 |
|------|---------|------|
| `factor_factor_info.parquet` | factor_id, factor_id_cn, level1, level2 | 预置因子元数据字典（约 390 个因子定义） |
| `factors/`（目录） | - | 预计算因子数据（如有，按需探查） |

---

## 常见数据缺口（直接判 missing，触发异常停止）

- 分钟 / tick / 高频订单簿数据 → 无（本地最细为日频）。
- 个股逐笔、Level-2、资金流向明细 → 无。
- 舆情 / 研报文本 / 分析师预期（朝阳永续）/ 卫星 / 另类数据 → 无。
- 期权合约行情、商品期货逐合约全历史 → 仅金融期货（国债/股指）可得，商品期货无。
- 海外个股财务、ESG 明细 → 无。
