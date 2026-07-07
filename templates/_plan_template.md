# 通用 plan.md 骨架

> `quant-planner` 生成 `workspace/{report_name}/plan.md` 时遵循本骨架：**先 frontmatter（分诊结论），后正文**。
> 正文的类型特化章节见对应的 `templates/{type}.md`。
> `quant-planner` **只读 spec.md 不读 PDF**（倒逼 spec 完备，缺口由审计暴露）——本文件回答「按什么顺序做」，不重复回答「研报里有什么」，研报要素的权威来源永远是 `workspace/{report_name}/spec/spec.md`。

---

## 一、frontmatter schema（plan.md 文件最顶部，YAML）

```yaml
---
report_name: <snake_case，与目录名一致>
title: <研报标题>
institution: <机构>
date: <研报发布日 YYYY-MM-DD>
type: <factor | timing | allocation | fixed_income | ml>   # 主类型，单选，决定回测框架与验证标准
tags: []                  # 附加维度（可选，多选）：ml / event / convertible_bond / fund / industry_rotation ...
difficulty: <easy | medium | hard>
feasibility: <feasible | degraded | blocked>
template: templates/<type>.md
spec_ref: workspace/<report_name>/spec/spec.md   # 指向本报告的复现规格书；R 类基准表等要素内容一律引用它，不在 plan.md 重复抄录
data_requirements:
  - name: <数据名，如 A股日行情>
    source: <local_data 文件名，或「外部」>
    status: <available | derive | missing>
  # ... 逐条列出复现所需数据，对照 templates/data_catalog.md 标 status
milestones:
  - id: m1
    name: <里程碑名>
    desc: <该里程碑要交付什么>
    deps: []                        # 依赖的其它 milestone id 列表，无依赖写 []；check_gates 按此判环（G-PL-5）
    elements: [F1, F2, B1]           # 本 milestone 覆盖的 spec.md 要素 ID 列表，供 coverage_matrix.md 的 milestone 列回填核对
  # easy=1 个；medium=2~3 个；hard=≥3 个
---
```

### 字段填写规则
- **type**：看研报最终回测对象。截面选股=`factor`；时序仓位信号=`timing`；多资产权重=`allocation`；债券/收益率曲线=`fixed_income`；需训练模型=`ml`。混合时取「最终回测形态」为 type，其余进 tags（例：深度学习选股 → `type: factor` + `tags: [ml]`）。
- **difficulty**：按 §三 难度判定表，任一维度落 hard 即 hard；含模型训练自动 ≥ medium。
- **feasibility**：取值 ∈ `{feasible, degraded, blocked}`（与 `tools/state.py` 的 `FEASIBILITY_VALUES` 逐字对齐，注意不是 `ok/partial`）。所有核心 data_requirement 为 available/derive → `feasible`；部分非核心数据 missing 但不影响主结论、需降级复现 → `degraded`；核心数据 missing 或核心方法无法确定 → `blocked`（触发主流程停下问用户，`tools/check_gates.py` G-PL-9 断言 `feasibility != blocked` 才能放行）。
- **milestones**：每个里程碑应是一个「可独立实现+验证」的闭环单元，粒度参考对应类型模板的「plan 正文结构」。`deps` 描述里程碑间的先后依赖（`tools/check_gates.py` G-PL-5 会检测环依赖，成环直接判 FAIL）；`elements` 是该里程碑要交付的 spec.md 要素 ID 清单，写完后须与 `coverage_matrix.md` 对应行的 milestone 列相互印证（一个要素只能落在一个 milestone）。

---

## 二、正文章节骨架

```markdown
# {研报标题} 复现开发计划

## 研报信息
- 标题 / 来源机构 / 发布日期 / 作者 / 适用市场（A股/港股/美股/多资产）

## 一、核心策略与创新点
### 1.1 研究背景与核心思想
### 1.2 因子/信号/策略构造（逐步骤，**写出关键公式**）
### 1.3 创新点（相对基准做了什么改进）

## 二、回测参数（复现对齐用，务必抄全）
- 回测区间 start ~ end
- 标的池 / 基准
- 调仓频率、费率、其它关键参数（中性化方式、分组数、训练窗口等）
> 类型特化的参数清单见 templates/{type}.md

## 三、研报核心结果（验证基准）
> 引用 spec.md 的「五、研报核心数值结果基准（R 类）」，**不在本文件重复抄录数值**——spec.md 是验证基准的唯一真相源，两处各抄一份容易产生不一致。本节只需列出本计划覆盖到的 R 要素 ID、一句话摘要与关联 milestone，具体数值/原文/页码以 spec.md 为准。
| R 要素ID | 一句话摘要 | 关联 milestone |
|----------|-----------|---------------|
| R1 | 表3 动量因子测试结果 | m1 |

## 四、复现计划（按 milestone 拆分）
### m1: {名称}
- 实现内容、依赖数据、产出文件、验证点
### m2: {名称}
- ...

## 五、改进建议与潜在问题（AI 视角）
- 数据/方法的潜在缺陷、未来函数风险、可改进方向
```

---

## 三、难度判定表（决定 milestone 数与编排强度）

| 维度 | easy | medium | hard |
|------|------|--------|------|
| 模块/因子数 | 1 | 2–4 | ≥5 |
| 数据可得性 | 本地全有 | 需简单衍生 | 需外部/复杂衍生 |
| 方法复杂度 | 标准公式 | 回归/中性化/参数优化 | 训练模型/优化求解/多资产联动 |
| milestone 数 | 1 | 2–3 | ≥3 |

> 主流程据 difficulty 选编排：easy 直接串行；medium 单 coder 逐 milestone；hard 按 milestone 派发独立 coder 子实例（独立模块可并行）+ 每 milestone 独立复核。详见 `.claude/skills/reproduce/SKILL.md`。
