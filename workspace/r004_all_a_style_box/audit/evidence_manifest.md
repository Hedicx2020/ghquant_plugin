# r004_all_a_style_box verifier 证据清单

## 历史基线与本轮追加

iter_01曾在旧代码与旧生命周期口径下形成`exit=0`的完整结果包；其metrics、comparison、Excel及PNG仍保留在`output/r004_all_a_style_box/results/`，mtime早于iter_02正式运行。iter_02没有覆盖这些旧数值产物，本节以下追加记录iter_02的独立硬阻断；旧PASS不得用于替代本轮结论。

iter_02当前有效结论为`FAIL`，新鲜运行证据只有06:56:45写入的`run_log.md`及本阻断文书。

## iter_02 E1-E6

| 规则 | iter_02证据 | 结果 |
| --- | --- | --- |
| E1 运行证据 | verifier亲自执行正式入口；06:50:29→06:56:45；exit=1 | fail |
| E2 新鲜度 | 只有run_log为本轮新鲜；metrics/comparison/Excel/PNG均早于本轮且不得使用 | fail |
| E3 文件完备 | 运行日志明确“未生成完整产物” | fail |
| E4 三方数值一致 | 生命周期门禁发生在完整NAV与结果写盘前，无本轮三方数值包 | not_run |
| E5 样本量合理 | 2023-07-06已阻断，无法形成33个月完整正式样本 | fail |
| E6 时间链 | 门禁识别到600466超20日历史点价且无结算/转板估值路径 | pass_gate_blocked_result |

## 证据条目

| ID | 证据 | 结果 |
| --- | --- | --- |
| EVD-B01 | 正式命令`.venv/bin/python -m src.r004_all_a_style_box.main`，exit=1 | fail |
| EVD-B02 | fresh run log mtime 06:56:45；旧metrics/comparison mtime 05:21:16 | old_results_rejected |
| EVD-B03 | RuntimeError只列出600466，并显式阻断NAV/R4/R7/R10/SA4 | fail |
| EVD-B04 | 异常栈只读重放：首日2023-07-06、ALL_A、shares 4.288027739673176e-05、target 0 | confirmed |
| EVD-B05 | 最后mark=0.40，source=2023-06-05，age=21>20，VWAP为空 | confirmed |
| EVD-B06 | 600466事件仅是2023-04-28公告/2023-05-04生效的risk exit行为，不是估值源 | confirmed |
| EVD-B07 | 现场68条候选记录；等待可卖与行为记录均没有有效成交 | confirmed |
| EVD-B08 | 本地raw/forward/trade各有600466 5,417行，均止于2023-06-05 | confirmed |
| EVD-B09 | 本地raw/forward/trade/master/suspend中400165均为0行 | confirmed |
| EVD-B10 | 外部只读核实存在600466→400165及挂牌后行情，但当前本地未纳入 | data_gap |
| EVD-B11 | 6长组合桥接、3合成因子、R4/R7/SA4、27+48 comparison均未运行 | not_run |
| EVD-B12 | hard扰动、finalizer、Excel/PNG终验未执行 | not_run |
| EVD-B13 | 未复制旧comparison到iter_02，未修改src/tests/state | pass |

## 关键边界

- 超阈值陈旧点价不能生成完整可实现NAV，即使份额很小、目标权重为0或已有risk_exit公告。
- `risk_exit`是行为证据，不是价格、现金结算或换股估值依据。
- 外部存在400165行情并不等于当前本地回测可使用；在数据映射和PIT来源纳入前必须保持阻断。
- 本轮不存在可报告的新9实体指标；任何05:21的指标均为iter_01遗留。

详细证据：`workspace/r004_all_a_style_box/iterations/iter_02/verification_blocker.md`。

verdict: fail
