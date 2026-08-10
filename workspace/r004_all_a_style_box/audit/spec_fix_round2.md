# r004 spec修复第二轮同步记录

## 一、修复范围

本轮仅处理SA-A03与SA-A04，不修改`spec/spec.md`正文、策略定义、milestones、代码、results或state。

读取与写入均限定在当前r004文书：核对`spec.md`、`ambiguities.md`、`coverage_matrix.md`、`plan.md`与`assumptions.md`；写入`ambiguities.md`、`coverage_matrix.md`、`plan.md`、`assumptions.md`及本记录。

## 二、SA-A03：A23来源证据去推断化

### 修复前问题

A23曾把Exhibit 5的通用来源行扩写为“美国国债来自FRED、S&P 500行业收益来自Factset”。该逐变量分配没有得到当前spec所登记的通用来源行直接支持，属于超出证据的推断。

### 修复结果

- A23只保留p5的Refinitiv表述与Exhibit 5通用来源行`Source: FRED, Factset`。
- 明确通用来源行只能证明FRED与Factset均被列为来源，不能将二者分配给Treasury、S&P 500行业收益或任何其它具体变量。
- 不裁定Refinitiv与FRED/Factset哪一方是原文唯一正确来源；冲突继续作为`reference_only`保留。
- r004的实现裁决不变：只使用`data_catalog.md`登记的本地A股数据源。
- AS22与plan中A23相关表述同步为“通用来源行不可作逐变量归属”。

## 三、SA-A04：coverage页码同步

| 要素 | 修复前 | 修复后 | 对应冲突 |
| --- | --- | --- | --- |
| F9 | `p5, p9-p10` | `p4-p5` | A24的Exhibit 1与正文daily/monthly冲突 |
| B1 | `p5` | `p5, p12` | A25的正文Mar-23与Exhibit 16横轴May-23冲突 |

只同步页码字段；F9继续`skipped`，B1继续由m1覆盖，状态、理由、milestone和策略口径均未改变。

## 四、保持不变的边界

- `type=factor`、`difficulty=hard`、`feasibility=feasible`不变。
- 2×2风格定义、PIT口径、T+1执行、成本、OOS区间及m1-m4不变。
- A23继续`major/resolved`并关联AS22；A24/A25及其它歧义不改。
- assumptions仍为AS1-AS24，共24条；没有新增、删除或改号。
- coverage仍为78行：14项`pending`、49项`skipped`、15项`infeasible`。

## 五、自检

- A23不存在把FRED/Factset分配给具体变量的表述。
- F9页码为`p4-p5`，B1页码为`p5, p12`，分别与A24/A25冲突页码一致。
- ambiguities无`open`残留。
- `git diff --check`通过。
