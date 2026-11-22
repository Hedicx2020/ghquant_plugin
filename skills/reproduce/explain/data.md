# 数据体检、缺口处置与 mock 试跑

## 体检

plan 写完后内核逐条核对 `data_requirements`：文件在不在、字段、区间、每年标的数、频率、主键重复、缺失率、财务数据有没有披露日列。结论写 `workspace/<id>/data_check.json`。

- planner 标了 available 而实测不过：带着实测结果退回 planner 改一次（改状态、换文件、收窄区间或登记假设）。
- 改完仍有缺口，或 planner 自己标了 missing：开 `data_gap` 检查点，**只能由人选处置**。
- 进入编码前再核一次；数据需求在体检之后被改过会自动重查。

## 六种处置

| 选项 | 之后 |
|---|---|
| `supply` 补数据 | 停在 `data_wait`；人补完后选 `recheck` 重新体检 |
| `substitute` 等价替代 | planner 登记替代假设；严格复现模式下案例切到实验模式（数值判定豁免，报告显著声明） |
| `narrow` 缩小范围 | planner 把区间或标的范围改到有数据的部分并登记假设 |
| `mock` 先试跑 | 整轮只算试跑，见下 |
| `drop` 砍掉相关要素 | 相关要素标 infeasible（data_missing），其余照做；这个决定在之后的重查里按需求名称沿用 |
| `abort` 终止 | 案例结束 |

建案时的 `--on-missing`：`mock` 遇到缺口自动选 mock 并自动确认规格（凭据记为「启动时预先声明的策略」）；`ask`（默认）与 `stop` 在内核里都是停下等人——`ask` 时你当场向人提问，`stop` 时只汇报停在哪里、不追问（无人值守时用）。

## mock 试跑

1. planner 起草 `data_mock/spec.yaml`，停在 `mock_spec` 检查点给人看。
2. 内核按规格生成模拟数据（固定随机种子），编码、内审、代码外审照常做。
3. 验证只确认三件事：跑得通、产物齐、指标都算得出。结果写在 `output/<id>/results_mock/`，不出结论、不写报告，停在 `trial_done`。
4. `wait_real`：停在 `data_wait`；真实数据到位后选 `recheck`（或执行 `flow data recheck <id> --quote "…"`）重新体检。结构与 mock 规格一致，只重跑验证；不一致，相关编码一并重做。`change`：结束试跑，回到缺口处置重新选。

真实结果目录里不允许出现 mock 算出来的东西：门禁 G-VF-8 核对数据清单，命中即不过。
