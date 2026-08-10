# r004_all_a_style_box iter_03 changes

## 实现状态

- coder 定向实现已完成：仅为 `600466→400165` 增加 1:1、最多 45 个交易日的 `pending_transfer` 及 2023-07-26 冻结真实行情退出链。
- 普通证券 `maximum_unexplained_price_age_trading_days=20` 未放宽；33 个月烟测首次推进时仍由普通生命周期门禁在 `000540` 处硬阻断。
- 未运行正式 `src/r004_all_a_style_box/main.py`，未生成或改写任何 `output/` 结果，未执行 75 项 comparison 与 32 个月 hard 扰动，不宣布正式达标；上述结论与完整结果均待 verifier。

## 改动文件与 diff 摘要

### 冻结证据包

- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/external_data/600466_to_400165/source_manifest.json`
  - 登记 SSE 摘牌、NEEQ 后继代码/进入日期、同花顺未复权日线三类来源。
  - 逐源保存 URL、下载时间、HTTP 参数、代码/日期范围、字段单位、raw/parsed 完整 SHA-256；声明正式运行仅离线读取、后继代码白名单仅 `400165`、用途仅 `600466` 生命周期退出。
  - manifest SHA-256：`926256a77dc5f882f4b592fc4874058d23feb34a9330f85ae49fc0ada08c1cbc`，同样由 config 固定并在正式加载前校验。
- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/external_data/600466_to_400165/sse_600466_delisting_20230605.pdf`
  - SSE 官方摘牌及 45 交易日转板窗口原始证据；SHA-256 `e9f53e9693106878aab293fe231a7385f53639b95b0eaea571c3644ee6cf7983`，8 页。
- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/external_data/600466_to_400165/sse_600466_delisting_20230605.txt`
  - PDF 文本提取中间证据；SHA-256 `b1300d91c968504cde1858cbaac71390fa504dd276f8893787268aed26e819bb`。
- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/external_data/600466_to_400165/sse_delisting_facts.csv`
  - SSE 事实解析 1 行；SHA-256 `458f3b076ef1aa33f687f44d8e68da5df50ea9cce63b04c0b164329e9d9c6147`。
- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/external_data/600466_to_400165/neeq_400165_company_report_20250828.pdf`
  - NEEQ 后继代码、进入日期及股份数量原始证据；SHA-256 `62d2177c2991dfe48ec2a734df7d3b3adb8d12b8a4890c90f41c9d79444d960d`，157 页。
- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/external_data/600466_to_400165/neeq_400165_company_report_20250828.txt`
  - PDF 文本提取中间证据；SHA-256 `0d9c4c713e70f4af19104fa7b410175b6bcda9cf51e690d9557ef12022b6b093`。
- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/external_data/600466_to_400165/neeq_successor_facts.csv`
  - NEEQ 事实解析 1 行；SHA-256 `40af0944e2bd7c744c529d072d1b4ee2b97f7f148ba0b51c74320b1cdce8bff5`。
- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/external_data/600466_to_400165/10jqka_400165_daily_all.js`
  - 同花顺公开未复权原始日线 callback；SHA-256 `6284dd992927823f269c5a6f11f60e9554f74199ab33996c77a249cf3e02539b`，`total=429`、`start=20230726`、`priceFactor=100`。
- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/external_data/600466_to_400165/10jqka_400165_daily_all.csv`
  - 原始 callback 离线解析 429 行（另 1 行表头）；SHA-256 `e2517458d828009e545f8b53d1e75a0d9d4ebac4378210ee1caba6f819898eb8`。首行 `2023-07-26`，OHLC 均为 `0.38` 元，`volumn=5,753,700` 股，`amount_status=unavailable`。

### 策略代码

- `/Users/hedi/report_reproduce/src/r004_all_a_style_box/config.py`
  - 实现位置：`AllAStyleBoxConfig`。
  - 集中登记旧/新代码、公开/摘牌/映射/生效日、1:1 比例、45 日上限、0.40 旧 mark、0.38 退出价、成交量单位、429 行源合同及 6 个运行时冻结文件完整哈希。
  - 新增参数不变量与文件/hash/估值优先级校验；普通 20 日门禁保持原值。
- `/Users/hedi/report_reproduce/src/r004_all_a_style_box/data_pipeline.py`
  - 实现位置：`_load_transfer_source_manifest`、`load_frozen_transfer_market_data`。
  - 正式加载只读本地冻结包，逐文件 SHA-256 校验，不含网络请求；断网解析 callback、429 行/日期/代码/未复权/OHLC/股单位/正成交量/parsed CSV 逐项复核。
  - 源无成交额，运行表 `amount` 保留 `NaN`、`amount_available=False`；仅在正成交量且 OHLC 四价同一时数学确定 VWAP。
- `/Users/hedi/report_reproduce/src/r004_all_a_style_box/portfolio.py`
  - 实现位置：`_transfer_window_age_trading_days`、`_is_pending_security_transfer`、`load_daily_mark_prices`、`_execute_security_transfer_exit`、`_has_auditable_valuation_path`、`_normalise_valuation_audit`、`run_china_market_backtest`。
  - 2023-07-26 前只允许 `600466` 在官方 45 交易日上限内携带 2023-06-05 的 0.40 旧 mark，不披露 `400165` 及其行情。
  - 映射日临时按 1:1 转为 `400165`，校验冻结 hash、0.38 单一成交价、`volumn` 股单位、退出份额不超过 5,753,700 股后全部卖出；佣金、滑点、卖出印花税沿用既有配置，旧/新代码份额均归零。
  - 缺行情、hash/字段失败、非同价 OHLC、容量不足、超过 45 日或错过映射日均硬阻断；第三方数据不进入目标构造和普通证券行情覆盖。
- `/Users/hedi/report_reproduce/src/r004_all_a_style_box/reporting.py`
  - 实现位置：`build_boundary_disclosures`、`validate_security_event_audit`。
  - 新增映射前后继代码泄漏、pending 期限/旧 mark、1:1 数量、OHLC/成交量/单位、amount unavailable、数学 VWAP、成本、现金、退出后余额及三源 hash 硬校验。
  - 最终边界披露增加“官方 45 日有限等待、映射公开生效日冻结真实行情退出”语义。
- `/Users/hedi/report_reproduce/src/r004_all_a_style_box/main.py`
  - 实现位置：`run_formal_pipeline`。
  - 正式 m1 前增加冻结包离线 preflight；返回行情不会进入选股信息集。

### 测试

- `/Users/hedi/report_reproduce/tests/test_r004_all_a_style_box_transfer.py`
  - 新增 6 项定向测试：断网重放/首日字段、hash 篡改、代码范围与普通 20 日门禁、1:1/容量/成本/现金勾稽、缺行情/容量/45 日超期硬阻断、映射公开日前后继代码泄漏拒绝。
- `/Users/hedi/report_reproduce/tests/test_r004_all_a_style_box_portfolio.py`
  - 保留 iter_02 两个月桥接烟测；原 33 个月阻断回归更新为明确验证新的普通阻断资产 `000540`，未放宽普通生命周期门禁。
- `/Users/hedi/report_reproduce/workspace/r004_all_a_style_box/iterations/iter_03/changes.md`
  - 本文件，登记增量文件、实现位置、冻结哈希、测试证据及 verifier 待办。

## 冒烟与定向测试

- `python -m compileall -q src/r004_all_a_style_box`
  - 环境失败，exit `127`：`zsh: command not found: python`。这是裸 `python` 命令不存在，不是代码编译失败。
- `uv run python -m compileall -q src/r004_all_a_style_box`
  - 环境失败，exit `2`：uv 无法在 `/Users/hedi/.cache/uv` 初始化缓存，`Operation not permitted`。随后按仓库解释器重跑。
- `.venv/bin/python -m compileall -q src/r004_all_a_style_box tests/test_r004_all_a_style_box_transfer.py tests/test_r004_all_a_style_box_portfolio.py`
  - exit `0`。
- `.venv/bin/python -c 'from src.r004_all_a_style_box.data_pipeline import load_frozen_transfer_market_data; ...'`
  - exit `0`；离线加载 `429` 行，首行 `400165/2023-07-26/OHLC=0.38/volumn=5753700 shares/amount unavailable/VWAP=0.38`。
- `MPLCONFIGDIR=/tmp/r004_iter03_mpl .venv/bin/python -m pytest -q tests/test_r004_all_a_style_box_transfer.py`
  - 首次 `6 passed in 18.34s`；增加 manifest 自身 hash 门禁后的最终复跑 `6 passed in 1.51s`。
- `MPLCONFIGDIR=/tmp/r004_iter03_mpl .venv/bin/python -m pytest -q tests/test_r004_all_a_style_box_reporting.py`
  - `20 passed in 57.83s`。
- `MPLCONFIGDIR=/tmp/r004_iter03_mpl .venv/bin/python -m pytest -q tests/test_r004_all_a_style_box_portfolio.py -k 'not 33_month and not two_month'`
  - `3 passed, 2 deselected in 1.20s`。
- `MPLCONFIGDIR=/tmp/r004_iter03_mpl .venv/bin/python -m pytest -q tests/test_r004_all_a_style_box_portfolio.py::test_two_month_formal_oos_bridges_execution_boundaries_from_cash`
  - `1 passed in 4.37s`，iter_02 桥接回归保留。
- 33 个月生命周期 smoke 首次执行精确失败：`RuntimeError ... 不得以risk_exit永久豁免: ['000540']`，位置 `portfolio.py:2949`。该资产不在 iter_03 允许修复范围，未越界处理、未放宽门禁。
- `MPLCONFIGDIR=/tmp/r004_iter03_mpl .venv/bin/python -m pytest -q tests/test_r004_all_a_style_box_portfolio.py::test_33_month_oos_still_blocks_other_unclosed_delisting_assets`
  - `1 passed in 34.53s`，明确固化上述普通资产硬阻断证据。

## 自检 checklist

- [x] 只改 diagnosis 列明的文件范围；未改 `state.json`、spec、plan、assumptions、coverage、history 或 output
- [x] 第三方逻辑仅为 r004 特定生命周期接入；未在 src 重写通用回测引擎
- [x] 未来函数三查：映射公开日前不暴露 400165 / 映射日才 1:1 执行 / 无滚动或未来价格回填
- [x] 未新增 coder 主动简化；同花顺替代与 amount unavailable 均直接执行 diagnosis 的已裁决合同，无需追加 assumptions
- [x] config.py 集中全部新增参数，无函数体新增策略魔法数字
- [x] 冒烟编译与定向测试通过；未运行正式 main.py、未声称完整回测或验证达标
- [x] iter_02 日/月桥接、唯一估值状态及既有报告回归未回退；75 项 comparison 与 32 个月扰动留待 verifier 正式重跑

## verifier 待办

- 亲自运行正式 `src/r004_all_a_style_box/main.py`，确认不再因 `600466` 阻断；不得把本轮 33 个月 smoke 中的 `000540` 硬阻断隐去或解释为已解决。
- 核对正式 `security_event_audit` 在 2023-07-26 前无 `400165` 行情/成交/退出结果，映射日 1:1 股数、0.38 元、5,753,700 股容量、amount unavailable、费用、现金及两代码余额逐项勾稽。
- 重跑并核验 75 项 comparison、32 个月 hard 扰动、工作簿、图表与完整证据链；裁判结论只由 verifier/check_gates 给出。
