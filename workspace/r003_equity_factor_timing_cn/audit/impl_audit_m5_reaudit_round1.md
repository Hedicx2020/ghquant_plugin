# m5 第1轮修复后独立代码复审

- 审计模式: code
- 案例: `r003_equity_factor_timing_cn`
- milestone: `m5`
- 复审轮次: round 1
- 复审目标: CA-A01至CA-A03及默认33月合同回归
- 独立性: 未读取或采信coder完成汇报；静态反查正式代码，并独立运行真实中国市场2025-11/12诊断、失败CLI、合成回撤和33月覆盖门禁
- 写入边界: 仅新增本复审文件并更新原m5审计文件；未改代码、`state.json`或`results/`

## 一、复审结论

CA-A01至CA-A03全部修复，m5第1轮复审通过。

正式结果包已经补齐gross回撤时序、300 DPI `drawdown.png`、Excel回撤数据及内嵌图；16项产物合同在两个真实诊断目录均精确满足。m1诊断端点改为始终从冻结完整底座构建，2025-11和2025-12单月均可运行。运行hash已覆盖实际窗口、m2/m3参数、m4参数及报告关键口径，并在metrics、manifest和run log一致记录。成功及失败日志均包含开始/完成时间、耗时、完整命令和退出状态。

默认2023-04至2025-12共33个月、2023-03冻结、首窗2016-04至2023-03、逐月84个月、严格过去、真实m1→m4对象接线、gross主结果、R10迁移语义和原有指标/产物均无回归。本轮未发现新增issue。

## 二、CA-A01：回撤图与Excel合同

### 2.1 静态实现

- `_build_chart_data`从m4 `portfolio.chart_data`提取`gross_nav`，按组合和`return_date`排序。
- 每组合运行峰值使用`gross_nav.cummax().clip(lower=1.0)`，明确包含期初财富1.0。
- `gross_drawdown=gross_nav/running_peak_including_initial_1-1`，并断言回撤不得为正。
- `create_charts`生成`drawdown.png`，使用四组合、gross口径、时间序列尺寸和300 DPI统一输出函数。
- summary workbook增加`图_组合回撤`sheet；同一sheet同时存回撤底表并内嵌`drawdown.png`。
- `drawdown.png`进入16项正式产物合同、返回paths和OOS manifest预期文件名。

### 2.2 合成多期独立核算

审计者构造四组合三期gross NAV `[0.90, 0.81, 0.972]`。正确回撤相对期初1.0应为`[-0.10, -0.19, -0.028]`：

| 检查项 | 独立结果 | 结论 |
| --- | ---: | --- |
| 回撤数据行 | 12=4组合×3期 | pass |
| 每组合运行峰值 | 三期均为1.0 | pass |
| 与手算回撤最大误差 | `5.55e-17` | pass |
| 回撤最大值 | `-0.028`，无正值 | pass |

该试验确认首期即下跌时不会把首期NAV误当峰值，CA-A01要求的含期初1.0口径正确。

### 2.3 真实诊断产物

| 检查项 | 2025-11 | 2025-12 | 结论 |
| --- | ---: | ---: | --- |
| 回撤底表行数 | 4 | 4 | 四组合齐全 |
| `gross_nav/peak-1`最大误差 | `3.47e-18` | 0 | pass |
| 回撤最大值 | `-0.0157796` | 0 | 均不为正 |
| PNG尺寸 | 3548×1752 | 3556×1752 | 非空 |
| PNG DPI | 约300 | 约300 | pass |
| `图_组合回撤`内嵌图数 | 1 | 1 | pass |
| summary总内嵌图数 | 6 | 6 | pass |

CA-A01状态：resolved。

## 三、CA-A02：2025-11/12诊断链路

### 3.1 修复机制

`main.run_pipeline`不再把诊断`--end`写入m1 `sample_end`。m1始终使用冻结的完整`ChinaFactorTimingConfig`构造2015-01至2025-12底座，因此股票收益日程仍能取得诊断末月之后所需的下一交易期；随后仅将`monthly_features`裁到诊断end交给m2/m3。m4仍消费完整m1底座与已裁剪的m3概率，正式coverage负责拒绝区间外组合月份。

### 3.2 真实中国市场执行

审计者在两个独立`/tmp`目录执行项目`uv run --extra ml --no-sync`正式入口：

| 检查项 | 2025-11单月 | 2025-12单月 |
| --- | ---: | ---: |
| 进程退出码 | 0 | 0 |
| m1月频特征 | 132 | 132 |
| m2滚动预测 | 1 | 1 |
| m3概率 | 1 | 1 |
| m4组合收益 | 4 | 4 |
| OOS概率/组合覆盖率 | 100%/100% | 100%/100% |
| m2/m3固定84月 | 全部true | 全部true |
| m2/m3严格过去 | 全部true | 全部true |
| 正式/诊断标志 | diagnostic/false | diagnostic/false |

2025-11此前的“交易日历不足以构造下一月T+1收益”没有再出现。CA-A02状态：resolved。

## 四、16项产物合同与manifest

两个真实诊断目录均独立核对：

- 非空文件数恰为16，文件名集合与`RESULT_ARTIFACT_FILENAMES`完全相等，无缺项、无额外文件。
- 合同包括5个Excel、3个JSON、1个Markdown checklist、1个run log和6张PNG。
- manifest的`expected_total_files=16`，`expected_filenames`与目录合同逐项相同。
- manifest对13项在写manifest前已完成且内容不再变化的核心产物记录大小和SHA-256；明确排除manifest自身、随后生成的checklist和最终run log的自哈希循环。
- 审计者对两个目录各13项重新读取文件并计算SHA-256，全部与manifest一致。
- manifest中的parameter hashes与metrics完全一致。
- run log明确记录`artifacts: 16`及`artifact_count: 16`，落盘后代码再次断言目录集合恰等于16项合同。

结论：16项计数、文件集合、manifest范围及稳定核心产物哈希通过。

## 五、成功/失败run log

### 5.1 成功日志

两个真实诊断成功日志均包含：

- 初始`started_at`，完成块再次记录相同`started_at`及独立`finished_at`；
- 正数`elapsed_seconds`：2025-11为`33.083196`秒，2025-12为`32.250427`秒；
- 完整可运行命令，明确记录Python解释器、模块、绝对output root、prediction start和end；
- `exit=0`；
- OOS窗口、预期月数、m2/m3/config/base config hash、gross主结果和16项计数；
- 每个目标月m2/m3训练窗口。

### 5.2 失败日志

审计者以无效`--prediction-start 2023-03 --end 2025-12`运行正式入口：

| 检查项 | 独立结果 |
| --- | --- |
| 实际进程退出码 | 1 |
| started/finished | 均存在 |
| elapsed_seconds | `0.000805` |
| 完整命令 | 含绝对output root及全部窗口参数 |
| 日志退出状态 | `exit=1` |
| 错误类型/原因 | `ValueError`，起点不得早于冻结切点 |
| 状态 | `failed_without_verifier_judgement` |

结论：成功exit0和失败exit1证据均为真实进程结果，不是静态推断。

## 六、CA-A03：运行hash

### 6.1 hash内容

run configuration hash覆盖：

- 完整基础中国市场配置及数据路径；
- 实际`prediction_start`、`prediction_end`和OOS cutoff；
- m2、m3参数hash；
- m4 `active_tilt_budget=0.15`、买入成本0.001、卖出成本0.001和卖出印花税0.0005；
- R9四周期方向矩阵、四组合顺序；
- 年化、rf、gross/net、MDD期初1.0、主动收益和换手公式；
- R10美国原值和16项产物合同。

### 6.2 独立一致性

| 检查项 | 2025-11 | 2025-12 |
| --- | --- | --- |
| configuration/run hash | `17b1a7e5...c488` | `2bc3af3a...0d96` |
| 从冻结配置与实际参数独立重建 | 完全一致 | 完全一致 |
| metrics与manifest | 一致 | 一致 |
| metrics与run log | 一致 | 一致 |
| 两窗口hash是否不同 | 是 | 是 |

base configuration hash另行保留，便于区分基础参数冻结与实际运行身份。CA-A03状态：resolved。

## 七、默认33个月无回归

静态默认参数及合成正式覆盖门禁独立复核结果：

| 检查项 | 结果 | 结论 |
| --- | ---: | --- |
| 默认起点 | 2023-04 | pass |
| 默认终点 | 2025-12 | pass |
| 默认月份数 | 33 | pass |
| formal default flag | true | pass |
| 概率覆盖 | 33/33、100% | pass |
| 四组合覆盖 | 33/33、100% | pass |
| 首月训练窗 | 2016-04至2023-03 | pass |
| m2/m3全部84月 | true | pass |
| m2/m3严格过去 | true | pass |
| OOS六项证据 | 全部true | pass |

默认m1仍构造完整132月真实底座；m2/m3只接收截止end的真实特征；m4和m5正式对象接线、gross主结果、成本补充、指标公式、R10美国/中国不可比语义和原有五图均未改变。

## 八、issue闭环

| issue | 初审严重度 | 当前状态 | 通过条件证据 |
| --- | --- | --- | --- |
| CA-A01 | major | resolved | 合成回撤误差`5.55e-17`；真实PNG约300 DPI；Excel数据和嵌图完整 |
| CA-A02 | minor | resolved | 2025-11/12真实诊断均exit0且16项齐全 |
| CA-A03 | minor | resolved | hash包含窗口/m4/报告口径，独立重建且三处一致 |

本轮没有发现新增issue。

## 九、五维度复审结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | pass | 回撤、覆盖、84月、绩效和hash输入口径均通过 |
| 参数一致 | pass | 默认33月、冻结切点、m4参数和R10口径完整进入结果/运行身份 |
| 实现位置真实 | pass | 回撤、日志、manifest和run hash均位于正式m5路径 |
| 代码反查 | pass | 两个真实成功运行、一个真实失败运行及合成门禁全部符合合同 |
| 简化声明 | pass | manifest哈希范围、诊断窗口、gross主结果和市场迁移边界均明确 |

## 十、复审检查清单

- [x] `drawdown.png`公式、300 DPI、非空图像
- [x] Excel回撤数据sheet及图像内嵌
- [x] 两个真实目录16项精确文件合同
- [x] manifest 16项声明、13项稳定核心产物SHA-256
- [x] 成功run log双时间、elapsed、完整命令和exit0
- [x] 失败run log双时间、elapsed、完整命令和exit1
- [x] run hash包含窗口、m2/m3 hash、m4参数和报告口径
- [x] metrics、manifest、run log hash一致
- [x] 2025-11及2025-12真实中国市场诊断
- [x] 默认2023-04至2025-12共33个月无回归
- [x] 首窗2016-04至2023-03、逐月84月、严格过去
- [x] m1→m4真实对象、gross主结果及R10迁移语义无回归
- [x] 五维度：公式一致、参数一致、实现位置真实、代码反查、简化声明

verdict: pass
