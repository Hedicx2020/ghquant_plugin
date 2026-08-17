# r004_all_a_style_box 实现审计（m2 白名单修复复审）

## 审计范围与冻结点

- mode：`code`
- milestone：`m2`（2×2大小盘与成长价值风格构造）
- 覆盖矩阵中本 milestone 的全部 `done` 行：F11、F12、F16。
- 审读分离：未读取 coder 完成汇报；仅依据 `spec.md`、`coverage_matrix.md`、`plan.md`、`assumptions.md`、修复后的 `strategy.py` 及必要的 m1 接口独立复核。
- 代码冻结点：全部复核测试前后，`src/r004_all_a_style_box/strategy.py` SHA-256 均为 `937485f606cc270689824bba7fb392371034573ecebd626ecd1a42e9a611d663`。
- 方法：逐条核对公式、参数、实现位置、公开接口与简化声明；对同一面板执行无注入/有注入双跑并逐表全等比较；另回归历史反例、主动扰动、边界场景及真实月份。

## 当前 milestone 的 done 行逐条核对

| 要素 | 状态 | 当前严重级别 | 公式一致性 | 参数一致性 | 实现位置真实性 | 代码反查与简化声明 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F11 | found | 无 | B/P、E/P、S/P、股息率分别按月1%/99%缩尾并转为[0,1]百分位秩，再对有效分量等权平均；至少2/4有效，高分为Value | 1%/99%、最少2分量与 `plan.md:113-121`、AS18一致 | coverage所列 `calculate_style_factors`、`assign_style_boxes`、`build_m2_dataset`、`assert_m2_invariants` 均存在且有实质逻辑，映射见 `coverage_matrix.md:48` | 输入额外列先被显式白名单隔离；未发现估值填充、额外因子或未登记简化 | F11实现成立 |
| F12 | found | 无 | PIT营收和净利润对称同比分别缩尾、rank后等权平均；至少1/2有效，逐行 `Style=Growth-Value` | 最少1分量与 `plan.md:123-145`、AS19一致；m2只消费m1披露日对齐字段 | coverage所列四处实现均存在且有实质逻辑，映射见 `coverage_matrix.md:49` | 未读取未来收益、动量、质量、宏观或ML输入；注入列不影响任何公开产物 | F12实现成立 |
| F16 | found | 无 | 完整eligible池先按 `(market_value, stock_code)` 稳定切Size，再在既定Size桶内按 `(style_score, stock_code)` 切Style；四箱按流通市值归一化，非正或缺失时退回总市值 | 总市值Size、稳定排序、数量差限制与流通市值回退均与 `plan.md:100-111,139-151`、AS17一致 | coverage所列四处实现均存在且有实质逻辑，映射见 `coverage_matrix.md:53` | m2成员仅保留m3所需风格与权重字段，并保留回接键；未发现未登记简化 | F16实现成立 |

## 五类公开输出白名单专项复核

### 注入设计

- 在同一8股月度面板注入19列：`future`、`forward`、`lead`、`return`、`target`、`label`、`momentum`、`quality`、`macro`、`ML`，以及 `future_return_t1`、`forward_alpha`、`lead_price`、`return_t1`、`target_label`、`momentum_12m`、`quality_score`、`macro_state`、`ml_probability`。
- 对未注入基准与注入面板分别调用 `build_m2_dataset`，对五类公开输出按行、列顺序、dtype和逐值执行严格全等比较。
- `target_weight` 是F16冻结公式产生的合法目标权重；输入注入的 `target`、`target_label` 均不得借此例外透传。

| 公开输出 | 固定列数 | 注入列残留数 | 与未注入基准比较 | 下游键检查 | 证据定位 |
| --- | ---: | ---: | --- | --- | --- |
| `factor_long` | 45 | 0 | 逐值、逐dtype完全一致 | 含唯一 `(signal_date, stock_code)` | `strategy.py:52-92,276-365` |
| `box_memberships` | 13 | 0 | 逐值、逐dtype完全一致 | 含 `(signal_date, stock_code, style_box, target_weight)` | `strategy.py:93-107,368-448` |
| `monthly_statistics` | 17 | 0 | 逐值、逐dtype完全一致 | 含 `signal_date`，每月固定四箱 | `strategy.py:108-129,451-531` |
| `missingness_audit` | 22 | 0 | 逐值、逐dtype完全一致 | 含 `signal_date`，每月一行 | `strategy.py:130-142,534-557` |
| `boundary_audit` | 14 | 0 | 逐值、逐dtype完全一致 | 含 `(signal_date, stock_code)` | `strategy.py:143-158,560-620` |

- 禁用名称二次扫描：除内部合法派生字段 `target_weight` 外，五类输出含 `future/forward/lead/return/target/label/momentum/quality/macro/ml` 任一token的列数均为0。
- schema门禁真实性：`_assert_public_output_schemas` 对五类输出逐一执行精确schema和禁用token检查，并由 `assert_m2_invariants` 每次构造时调用，证据见 `strategy.py:159-236,643-650,964-979`。
- 派生值稳定性：注入前后五表严格全等，因此Size/Value/Growth/Style分数、四箱标签、排序位置、成员、目标权重、统计、缺失与边界记录均未变化。
- m3回接：`factor_long` 8行和 `box_memberships` 8行均按 `(signal_date, stock_code)` 与m1的执行日、收益端点、VWAP及可交易状态完成 `one_to_one` 回接，无缺键；该键与m1合同 `data_pipeline.py:23,26-35` 及plan m3依赖 `plan.md:231-236` 一致。

## 历史问题定向复核

| 编号 | 当前状态 | 证据定位 | 独立复核结论 |
| --- | --- | --- | --- |
| CA-A01 | 已清除 | `strategy.py:384-434,682-748` | 6股反例中先对6只完整合格股赋Size：市值1至3为Small、4至6为Big；最小两股Style缺失未移动Size边界，有效成员为3号SG、4号BV、5至6号BG。 |
| CA-A02 | 已清除 | `strategy.py:750-896` | 互换BV/BG、SV/SG时，语义独立重算断言拒绝；把比例权重改为等权时，权重独立重算断言拒绝。 |
| CA-A03 | 已清除 | `strategy.py:89-158,412-419,451-620,924-953` | 全Style无效、仅1只有效、仅Small桶有效三种边界均返回固定schema；成员数分别0、1、3，统计均固定4行。 |
| CA-A04 | 已清除 | `strategy.py:175-197,276-280,368-369,451-647,964-990`；`coverage_matrix.md:48-53` | 对外公开执行函数均在docstring和coverage映射F11/F12/F16；统计、缺失、边界及方向辅助函数均为内部函数，不存在未映射策略公开接口。 |

## 公式、边界、权重与真实月回归

| 测试 | 独立结果 | 判定 |
| --- | --- | --- |
| F11/F12/F16方向与等权 | 5股Size信号依次为 `0,-0.25,-0.5,-0.75,-1`；Value为 `1,0.75,0.5,0.25,0`，Growth反向递增，Style为 `-1,-0.5,0,0.5,1`；Value及Growth分量rank均值与输出最大绝对差均为0 | 公式、方向与等权一致 |
| 缺失阈值 | Value有效分量1/4时为NaN、2/4时可计算；Growth有效分量0/2时为NaN、1/2时可计算 | 阈值一致且无填充 |
| 稳定tie与四箱标签 | 8股市值和Style全部并列且输入打乱，按stock_code得到1至2号SV、3至4号SG、5至6号BV、7至8号BG | 稳定规则及四箱语义一致 |
| 流通市值权重 | 正流通市值直接使用，NaN、0、负值退回总市值；SV权重0.25/0.75，SG为2/3与1/3，BV约0.285714/0.714286，BG约0.166667/0.833333；各箱权重和均为1 | 权重公式与回退一致 |
| 主动扰动 | 错误四箱标签和箱内等权两种篡改均被独立不变量拒绝 | 语义及权重防线成立 |
| 边界合同 | 全Style无效、单股有效、仅单个Size桶有效时，成员分别0/1/3行，统计均为4行，schema不变 | 边界输出成立 |
| 真实月份 | m1实际面板2025-11-28共5,453行、eligible 5,135只；m2有效Style及成员5,030只，Big/Small为2,568/2,567，BG/BV/SG/SV为1,270/1,269/1,246/1,245；四箱权重和均为1，统计4行；Value/Growth/Style独立重算最大差均为0，未来披露0条 | 真实单月端到端通过 |
| 真实月白名单与回接 | 同样注入19列后五类输出与基准严格全等、注入列残留0；factor 5,135行、members 5,030行均可按双键一对一回接m1执行与收益字段 | 数据隔离和m3接口成立 |

## Issues

本次复审没有发现当前 issue；白名单隔离、派生稳定性、下游回接及CA-A01至CA-A04均经独立测试确认通过。

## 五维度已检查清单与结论

- 公式一致：已核对F11四分量缩尾、rank与等权，F12两分量缩尾、rank与等权及 `Style=Growth-Value`，F16完整池先Size、桶内再Style、标签和流通市值权重；合成及真实月独立重算一致。
- 参数一致：已核对1%/99%、Value至少2/4、Growth至少1/2、总市值Size、流通市值回退、`stock_code`稳定tie-break和奇数样本数量差；均与plan/assumptions一致。
- 实现位置真实：已逐个打开coverage所列四处实现；F11、F12、F16位置均存在且不是 `pass`/`TODO` 空壳，五类白名单投影和schema门禁均在实际执行链上。
- 代码反查：已从m1输入、五类输出、公开接口、内部辅助函数及m3回接方向反查；注入的未来收益、额外因子、标签、宏观和ML列均未进入产物或影响派生值，公开函数均映射要素ID。
- 简化声明：已对照assumptions核对PIT复合Value/Growth、全A总市值Size和流通市值权重；白名单仅收窄数据合同，不改变冻结公式，未新增未登记简化或偏差。

verdict: pass
