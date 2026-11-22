# flow explain 的键

`flow explain <键>`。键可以是：

- **阶段名**：`init` `extract` `plan` `spec_audit` `implement` `code_audit` `verify` `iterate` `result_audit` `oos` `report` `review`
- **步骤编号**：如 `implement.m2.code`，给它所在阶段的那一份
- **门禁检查项编号**：如 `G-VF-6`，只给那一段；`G-VF` 给整个阶段
- **检查点名**：如 `data_gap`、`circuit_breaker`，给 `checkpoints` 里的那一段
- **主题**：
  - `collect` 点收不过的几种情况
  - `review_cycle` 外审的「审、裁、修、复审」循环与降级链
  - `data` 数据体检、缺口处置、mock 试跑
  - `revise` 定向重跑、回退、复制案例、过期报告、退回执行卡、表外派发
  - `limits` 各种上限和对应的配置键
  - `checkpoints` 全部检查点及每个选项的后果

内核自己会处理的事这里只说明「它会怎么做」，不需要你动手；写着「交给人」的才需要停下。
