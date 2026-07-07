# 研报复现系统 v2 重构设计方案

> 状态：待审阅。本文档为完整设计规格，审阅通过后按「十一、实施批次」落地。
> 日期：2026-07-07

---

## 一、背景与目标

现有系统（quant-pdf-reader → quant-coder → quant-verify + 5 类型模板 + common/ 回测框架）已跑通 3 个案例，但存在核心缺陷：

| # | 缺陷 | 后果 |
|---|------|------|
| 1 | 提取环节单 agent 单次通过，无覆盖矩阵、无页码引用 | 研报要素遗漏无从发现（如 12 个因子只提取 6 个、跳过敏感性分析） |
| 2 | 无审计环节，spec/plan 质量无门禁 | 可能未实际运行就声称验证通过 |
| 3 | 歧义处理无结构 | 临时问用户或悄悄假设，无假设登记与事后回看 |
| 4 | codex 仅用于救火调试 | 外部交叉验证能力未流程化 |
| 5 | 状态靠手工 TaskCreate | 断点续跑弱，跨 session 无法可靠继续 |
| 6 | 迭代无结构 | 诊断-修正-重跑无轮数控制、无历史，容易兜圈子 |

### 已拍板的四项决策

| 决策点 | 选择 |
|--------|------|
| 人工介入默认策略 | **全自动优先**：歧义自动按行业惯例假设并登记，跑完人工统一 review 假设清单，有问题定向迭代；blocking 级（核心数据缺失/核心方法无法确定）两种模式都暂停；`--mode interactive` 可切换 |
| 编排载体 | **主会话编排 + 文件状态**：skill 驱动状态机，每阶段派子 agent，状态落盘，支持断点续跑跨 session |
| 达标标准 | **分类型量化容差**，机器化为 `templates/standards.json` |
| codex 外部审查 | **三审查点（最严格）**：spec 审计 + 代码审计 + 结果审计，审查意见逐条回应制 |

### 设计原则

| 原则 | 含义 | 落地机制 |
|------|------|---------|
| 要素守恒 | 研报每个可复现要素一经登记只允许状态流转，不允许无痕消失 | 要素 ID 体系 + 覆盖矩阵只增不删 |
| 证据优先 | 任何「已完成」声明必须挂接可独立核验的证据；转述不算证据 | evidence_manifest.md（E1–E6） |
| 审读分离 | 提取者、实现者、审计者是不同上下文的 agent；审计者只拿文件，不拿被审者自述 | 独立审计 agent + codex 外审 |
| 门禁可机验 | stage 放行条件是「文件存在 + 正则/计数校验 + verdict 字段」类机器断言 | tools/check_gates.py |
| 编排与生产分离 | 主会话只派发/审门禁/调 codex/记账，不亲自生产内容 | SKILL.md 六条硬规则 |
| YAGNI | 纯文件驱动（markdown+json），无数据库/队列/界面 | 工具脚本仅 3 个 |

---

## 二、总架构与目录结构

```
主会话（orchestrator，skill 驱动，唯一可并行派发方）
 ├── 派发 7 个子 agent（Claude，不嵌套、产物落盘）
 ├── 调用 codex exec（Bash，read-only 沙箱，三审查点 + 第二意见）
 ├── 运行 tools/*.py（门禁检查、状态读写、PDF 转文本）
 └── 读写编排记录（state.json / iteration_log.md / *_responses.md）

内容产物（spec/plan/代码/结果/诊断/报告）一律出自子 agent；
达标判定一律出自 check_gates + standards.json 重算，不信任任何 agent 自述。
```

### 目录布局

取舍：**workspace 收拢文书 + src/output 保留原位**。`python3 -m src.{id}.main` 运行方式与 `from common import ...` 导入约定零改动，3 个已完成案例代码免迁移；旧 `plan/` 目录退役升级为 `workspace/`。

```
/Users/hedi/report_reproduce/
├── CLAUDE.md                          # 从 .claude/agents/CLAUDE.md 迁出改写
├── pyproject.toml                     # 依赖增加 pypdf、pdfplumber
├── common/                            # 原样保留：utils/backtest/data_loader + 按需 {type}_*.py
├── templates/
│   ├── data_catalog.md                # 保留（infeasible/data_missing 判定唯一依据源）
│   ├── _plan_template.md              # 改造：frontmatter 增 milestones[].deps、瘦身为「怎么做」
│   ├── _spec_template.md              # 新增：spec 章节骨架 + 要素 ID 规范 + 自检声明
│   ├── standards.json                 # 新增：分类型机器可读达标标准
│   ├── {factor,timing,allocation,fixed_income,ml}.md   # 保留，注明容差以 standards.json 为准
│   ├── audit/                         # 新增：审计产物模板
│   │   ├── coverage_matrix.md / ambiguities.md / assumptions.md
│   │   ├── extract_audit.md / evidence_manifest.md / audit_responses.md
│   │   └── review_schema.json         # codex 结构化输出 schema
│   └── codex_prompts/                 # 新增：spec_audit / code_audit / result_audit / second_opinion.md
├── tools/                             # 新增：管线工具（主会话专用）
│   ├── state.py                       # state.json 唯一写入口（init/show/set-stage/set/record-event/milestone/gate）
│   ├── check_gates.py                 # 门禁机器判定（--stage X [--assert-done]，输出 PASS/FAIL+原因）
│   └── pdf_extract.py                 # PDF → report_text.md（分页标记）+ tables_extracted.md
├── reports/{report_id}.pdf            # PDF 收件箱（原样）
├── workspace/{report_id}/             # 每报告管线文书（取代 plan/）
│   ├── state.json
│   ├── spec/
│   │   ├── report_text.md             # 逐页文本，===== PAGE n ===== 分隔（喂 codex/grep）
│   │   ├── tables_extracted.md        # pdfplumber 表格附录
│   │   ├── spec.md                    # 复现规格书（§四）
│   │   ├── spec_codex.md              # codex 盲提取清单（spec_audit 产出）
│   │   ├── coverage_matrix.md         # 覆盖矩阵（§五）
│   │   └── ambiguities.md             # 歧义清单（§七）
│   ├── plan.md                        # 复现计划（frontmatter 分诊）
│   ├── assumptions.md                 # 假设登记簿（§七）
│   ├── audit/
│   │   ├── extract_audit.md           # 内部提取完整性审计
│   │   ├── extract_diff.md            # 盲提取交叉 diff 裁决
│   │   ├── impl_audit_m{X}.md         # 实现忠实性审计（按 milestone）
│   │   ├── evidence_manifest.md       # 证据清单（E1–E6）
│   │   ├── codex_prompt_{spec|code|result}.md    # 实际使用的 prompt 落盘（可追溯）
│   │   ├── {spec|code|result}_audit_codex.md     # codex 原始输出
│   │   └── audit_responses.md         # 全部外审意见逐条回应总表
│   ├── iterations/
│   │   ├── iteration_log.md           # 全轮次总账
│   │   └── iter_NN/{diagnosis.md, codex_opinion.md, changes.md, comparison.json}
│   └── final_report.md                # 最终复现报告（人工 review 对象）
├── src/{report_id}/                   # 代码（约定不变：strategy/config/main.py）
├── output/{report_id}/
│   ├── results/                       # *.xlsx/*.png + metrics.json + comparison.json + run_log.md
│   └── verify_report.md
└── .claude/
    ├── agents/                        # 7 个 agent 定义（§六）
    └── skills/reproduce/{SKILL.md, stages/*.md}   # 主编排 + 11 张 stage 执行卡（§九）
```

---

## 三、端到端流程状态机

stage 顺序（写死在 tools/state.py 与 SKILL.md）：
`init → extract → plan → spec_audit → implement → code_audit → verify → iterate(条件) → result_audit → report → review`

| # | stage | 执行者 | 关键输出 | 出口门禁（G-XX，check_gates 机器判定） | 失败处理 |
|---|-------|--------|---------|--------------------------------------|---------|
| 0 | init | 主会话 + tools | state.json、目录骨架、report_text.md、tables_extracted.md | **G-IN**：PDF 可解析；PAGE 标记数 == PDF 页数；tables_extracted 存在；state 初始化 | PDF 不可解析 → 终止 |
| 1 | extract | quant-extractor（opus） | spec.md、coverage_matrix.md、ambiguities.md | **G-EX**：frontmatter 可解析；正则统计要素数 == element_counts == 矩阵行数（三方一致）；每要素含页码行+原文行；R 类 ≥1；FIG/TBL 登记数 == exhibit_declared | 带缺失项重派 1 次；再失败 → paused_blocked |
| 2 | plan | quant-planner（opus） | plan.md（frontmatter 分诊）、assumptions.md、矩阵回填 milestone 列 | **G-PL**：frontmatter 枚举合法；milestone 数 ≥ 难度下限且 deps 无环；所有非 skip 的 core/support 行 milestone 列非空且并集==全部非 skip 行；每条歧义 status=resolved（或 blocked）；feasibility ≠ blocked | blocked / blocking 级歧义 → 两种模式都暂停问人工：补数据/降级复现/放弃 |
| 3 | spec_audit | codex（必跑）∥ quant-auditor mode=spec（medium+） | spec_codex.md、extract_diff.md、extract_audit.md、spec_audit_codex.md、audit_responses.md 追加 | **G-SA**：应跑通道审计文件齐；extract_diff 所有 DIF 行裁决列非空；responses 行数 == issue 总数；critical=0 且 major 全部有回应 | critical/未回应 major → 回派 extractor/planner 定向修复复审；修复轮 >2 → paused_blocked |
| 4 | implement | quant-coder（opus）× milestone（hard 并行独立模块；hard/ml 每 milestone 后插 auditor mode=code + milestone 级 verify） | src/{id}/*.py、按需 common/{type}_*.py、矩阵回填实现位置列 | **G-IM**：全 milestone done；`uv run python -m compileall src/{id}` 通过；矩阵实现位置列无空（excluded 除外） | coder 报错带上下文重派（每 milestone 上限 2 次）；复核不通过回 coder 重走该 milestone |
| 5 | code_audit | codex（read-only） | code_audit_codex.md、responses 追加 | **G-CA**：impl_audit 无 not_found；responses 全覆盖；critical（未来函数/硬编码/方向反）=0 | critical → coder 修复 → codex 复审（上限 3 轮）→ 超限 paused_blocked |
| 6 | verify | quant-verifier（opus，可直调 codex 辅助） | results/*（图表 Excel）、metrics.json、comparison.json、run_log.md、verify_report.md、evidence_manifest.md | **G-VF**：run_log 含 exit=0；E2 新鲜度断言；comparison.json 合法且 check_gates 按 standards.json **重算** overall_pass；必需图表齐且 >15KB；矩阵验证列无空（core/important） | 运行报错 → 回 coder（计 1 次迭代）；指标超容差 → 进 iterate |
| 7 | iterate（条件） | quant-diagnoser（opus）→ quant-coder → quant-verifier；iter≥2 并行 codex 第二意见 | iter_NN/ 三件套、iteration_log.md | **G-IT**：每轮三件套齐；rounds ≤ max_iter；diagnosis 含「已排除假设」节（N≥2） | 三出口：达标 / 超限 partial / blocked（§八） |
| 8 | result_audit | codex（read-only）∥ quant-auditor mode=result（hard 必跑，medium 触发） | result_audit_codex.md、responses 追加、扰动测试记录 | **G-RA**：无 open critical（数字与原始产物不符/漏对比项/归因造假）；超差指标归因状态 ∈ {accepted, assumption_linked}；触发的扰动测试有记录 | 数字不实 → 回 verify 重出；代码问题 → 计入迭代轮 |
| 9 | report | quant-reporter（sonnet） | final_report.md | **G-FN**：必需 H2 章节齐；矩阵无 pending/in_progress；coverage_stats 写入 state；假设登记簿无未决议条目；所有 rejected 意见出现在报告 | 缺章节重派补写 |
| 10 | review | 人工 | `/reproduce revise` 或 `/reproduce accept` | accept → done | awaiting_review 可跨 session 挂起 |

### stage × difficulty 裁剪矩阵

**codex 三审查点对所有难度必跑**（核心诉求）；内部 Claude 审计按难度裁剪。check_gates 内置本矩阵：必跑 stage 缺产物判 FAIL；「跳过」仅接受显式 skipped 状态（防止把必跑阶段悄悄标 skipped）。

| 机制 | easy | medium | hard |
|------|------|--------|------|
| spec_audit：codex（含盲提取协议） | 必跑（轻量：仅 R 表逐格 + 图表编号连续性） | 必跑（盲抄全部结果表数值 + 全维度） | 必跑（全量盲提取 diff + 全维度） |
| spec_audit：auditor(spec) 内审 | 跳过 | 必跑 | 必跑 |
| implement 编排 | 单 coder 一次实现 | 单 coder 逐 milestone 串行 | 按 milestone 派独立 coder，无依赖模块并行 |
| milestone 级 verify | 跳过（并入 final verify） | 每 milestone | 每 milestone |
| auditor(code) 实现忠实性审计 | 并入 verify（抽 2 条核心要素） | 逐条核对 core 要素（含 ml tag 时全量） | 逐条核对全部要素，每 milestone |
| code_audit / result_audit：codex | 必跑 | 必跑 | 必跑 |
| auditor(result) 反虚报核查 | 仅触发时 | 仅触发时 | 必跑 |
| 扰动测试 | 仅触发（K2 命中） | 仅触发 | 必做一次 |
| iterate 默认 max_iter | 3 | 5 | 6 |

补充规则：
- tags 含 `ml` 时 auditor(code) 无视难度必跑——未来函数/训练泄漏使指标「偏好」而非偏差，数值验证抓不到，必须在 verify 之前独立查代码。
- `--difficulty` 启动参数可人工覆盖分诊结果（记入 state.difficulty_override）。

---

## 四、复现规格书 spec.md（要素 ID 体系）

spec.md 回答「研报里有什么必须被复现」；plan.md 只回答「按什么顺序做」。所有下游文件通过要素 ID 引用；ID 一经分配永不复用、永不删除。

### 要素 ID 前缀

| 前缀 | 类别 | 规则 | 示例 |
|------|------|------|------|
| D | 数据要求 | D1..Dn | D3 中信一级行业分类 |
| F | 因子/信号/策略定义（含公式） | F1..Fn；子变体 F3.1 | F2 趋势动量 MA_60 |
| B | 回测设置（区间/池/费率/调仓/中性化/分组） | B1..Bn | B4 月末调仓 |
| R | 研报核心数值结果基准 | R1..Rn 对应研报一张结果表；行级 R1.3 | R1 表3 动量因子测试结果 |
| TBL / FIG | 研报表/图登记（全集） | **用研报原生编号**：FIG12 即研报图12 | FIG12 |
| EX | 研报用「图表N」统一编号时替代 TBL/FIG | EX1..EXn | EX25 |
| SA | 敏感性/稳健性/子样本分析 | SA1..SAn | SA1 参数 L 敏感性 |

关键设计：FIG/TBL 用研报原生编号，使「编号连续性审计」变成纯机械检查；**图表登记全集、复现子集**——每张图必须登记，但可标 `复现意图: skip/reference_only`（须给理由），防止「没登记所以不算漏」。

### 模板骨架（templates/_spec_template.md）

```markdown
---
report_name / title / institution / report_date / authors / market
pdf_pages: 28                  # PDF 物理总页数
exhibit_declared: {fig_max: 25, tbl_max: 9}   # 全文出现的最大图/表号（防遗漏锚点）
element_counts: {D: 8, F: 12, B: 7, R: 4, SA: 2, FIG_registered: 25, TBL_registered: 9}
type_hint / tags_hint          # extractor 初判，planner 定稿
---
## 一、研报元信息与结构地图
- 章节目录抄录（含页码）+ 页面覆盖表：| 页码 | 内容类型 | 关联要素 |
  （无关联页必须标注 封面/目录/免责声明 等类型——审计 C2 的依据）
## 二、数据要求（D 类）      ← 每条对照 data_catalog 标 available/derive/missing
## 三、因子/策略定义（F 类）
## 四、回测设置（B 类）
## 五、研报核心数值结果基准（R 类）  ← 数值原样抄录含正负号/百分号，研报没给的格子写 n/a 禁止填补
## 六、图表登记清单（FIG/TBL 全集）  ← | ID | 标题 | 页码 | 摘要 | 复现意图 | 理由/关联要素 |
## 七、敏感性/稳健性分析（SA 类）
## 八、提取自检声明          ← 逐页扫描确认 / 图表编号全登记 / 摘要结论数值可定位 / 无法提取内容清单
```

每条要素固定格式（机器可校验）：

```markdown
### [F2] 趋势动量因子 MA_60
- 页码: p9-p10                        # 必填，PDF 物理页，与 report_text.md 分页标记一致
- 原文: > "MA_{j,t,L} = (P_{j,d-L+1} + ... + P_{j,d}) / L……"   # ≤80字关键句，数值/单位/正负号原样，禁止转述
- 公式（转写）: MA_bar = mean(close, L=60) / close_d
- 参数: L=60；取值日=月末最后交易日
- 依赖数据: D1 / 关联基准: R2.2 / 关联歧义: A3（如有）
```

门禁锚点：frontmatter 的 `element_counts` 与正文正则统计（`^### \[(D|F|B|R|SA)[0-9]+`）、coverage_matrix 行数**三方一致**；`exhibit_declared` 由审计 agent 独立重算比对。

---

## 五、覆盖矩阵 coverage_matrix.md

| 列 | 填写者 | 说明 |
|----|--------|------|
| 要素ID | extractor | 与 spec.md 一致 |
| 类别 / 描述(短) / 页码 | extractor | 页码必填 |
| 优先级 | extractor 初判，spec_audit 可改 | core（进入研报核心结论）/ support（敏感性、辅助）/ optional（示意图等） |
| milestone | planner | 所有非 skip 行必填 |
| 状态 | 各阶段 | pending / in_progress / done / skipped / infeasible |
| 状态理由 | 改 skip/infeasible 者 | `<理由码>: <一句话>`；理由码枚举 data_missing / method_underspecified / out_of_scope / cost_prohibitive / reference_only |
| 实现位置 | coder | `src文件:函数`（真实存在，审计核验） |
| 验证结果 | verifier | `verify_report.md#锚点 偏差x% pass|fail` |
| 最后更新 | 各阶段 | 阶段名 |

**要素守恒硬规则**（审计 agent 逐条执行）：
1. **只增不删**：任何 agent 不得删行；不需要做改状态并填理由。行数只能因「审计补漏」增加，变更日志（文件尾只追加）登记来源（如 `依据 CDX-S-02 追加`）。
2. **done 三件套**：改 done 必须同时填实现位置 + 验证结果，缺一门禁 fail。
3. **core 不许静默 skip**：core 级要改 skipped/infeasible 必须关联歧义或假设登记，并强制出现在 final_report「未复现清单」。
4. **合法流转**：pending→in_progress→done；pending/in_progress→skipped/infeasible（带理由）；done→in_progress（仅迭代回退，日志记触发意见 ID）。**禁止 done→skipped**（掩盖失败）。
5. **终态检查**：进 report 阶段不允许存在 pending/in_progress 行。

---

## 六、agent 清单与职责契约

| agent | 处置 | model | 单一职责 | 关键硬约束 |
|-------|------|-------|---------|-----------|
| quant-extractor | 新增（拆自 pdf-reader） | opus | 研报说了什么：spec 三件套，页码引用制 | 只陈述不设计；不确定处进 ambiguities 不脑补；R 类只抄录不推算 |
| quant-planner | 新增（拆自 pdf-reader） | opus | 怎么复现：分诊（type/tags/difficulty/feasibility）、数据映射、milestone（含 deps）、歧义决议、假设登记 | **只读 spec 不读 PDF**（倒逼 spec 完备，缺口由审计暴露）；blocking 级一律 blocked 不得擅自降级 |
| quant-auditor | 新增（吸收旧 verify 模式 B） | opus | 对照审计三模式：spec（PDF vs 提取/计划，检查项 C1–C6）；code（spec vs 实现，忠实性逐条核对）；result（反虚报 K2/K3、证据 manifest 复核） | **只读不改**；只拿文件不拿被审者自述；「无问题」必须列已检查维度清单，禁止空泛通过 |
| quant-coder | 保留改造 | opus | 按 plan 切片实现 + 回填矩阵实现位置 | 只实现派发范围；通用引擎沉淀 common/ 严禁进 src/；财务数据按 info_publ_date 对齐；**只许冒烟运行，不得自行宣布验证结论**；遵守 assumptions 已登记口径；简化处理必须登记假设 |
| quant-verifier | 改造（原 quant-verify，**不降配**） | opus | 亲自跑 main.py、对数出 comparison.json、出图表、产 evidence_manifest（E1–E6）、触发时跑扰动测试；**可 Bash 直调 `codex exec`（read-only）辅助验证**：(a) main.py 报错时让 codex 定位原因（只诊断不修复，修复归 coder/iterate）；(b) 超差指标进 iterate 前先做一次口径自查（让 codex 独立核对该指标计算口径——复利/单利、年化倍数、分母定义——排除「口径抄错」类低级偏差，避免浪费整轮迭代）；调用输出落盘 `workspace/{id}/audit/verify_assist_codex_NN.md` | **不采信 coder 声明**；不修代码不归因，如实报告；comparison 数值必须来自实际运行产物；codex 只能 Bash 直调 `codex exec`（不得派发 codex:rescue agent 或调 skill——子 agent 不嵌套约束）；codex 自查结论仅供参考，不改变门禁判定 |
| quant-diagnoser | 新增 | opus | 偏差归因 + 修正指令 + 防兜圈（读全部历史轮次） | iter≥2 必含「已排除假设」节；禁止重提已排除假设；每轮最多锁定 1–2 个修改点；必须给预期指标变化方向；结论三选一 continue/stop_partial/blocked |
| quant-reporter | 新增（并入旧 visualizer 职能） | sonnet | 汇总 final_report.md | 只汇总不新增结论；假设登记簿全文收录并给每条 revise 指引；残余偏差如实列示 |

- 每个 agent 定义统一四节：**输入合同**（派发时必须给到的文件路径）/ **输出合同**（必须产出的文件，主会话逐一点收）/ **硬约束** / **完成报告格式**（产物清单 + 自检 checklist 逐项勾选）。
- 并行约束沿用：子 agent 不嵌套派发、不启动 Task tool；并行只由主会话发起（hard 多 coder、审计双通道、code_audit∥verify 汇合过门禁）。
- **子 agent 一律不碰 state.json**（tools/state.py 是唯一写入口，主会话专用）。

---

## 七、歧义与假设管理

### ambiguities.md（歧义清单）

```markdown
### [A3] 换手率口径不明
- 页码: p8（表3 Turnover 列） / 关联要素: R1, B6
- 等级: major                    # blocking / major / minor，判据见下表
- 候选解释: 1. 多头组单边换手（惯例，可能性高） 2. 多空双边换手（量级同样吻合）
- 裁决方式: auto                 # auto / human
- 裁决结果: 采解释1 → 登记 AS4
- 裁决依据: 同机构系列报告惯例 + 复现值反推更接近
- 状态: resolved                 # open / resolved / blocked
```

**分级判据**（按顺序判定，命中即停）：

| 序 | 判据 | 等级 |
|----|------|------|
| 1 | 核心方法完全无法确定（缺关键公式/步骤）或核心数据 missing 无替代 | blocking |
| 2 | 影响信号/因子方向定义（多空方向、排序、买卖规则） | major |
| 3 | 影响全局回测设置（区间、股票池、调仓频率、费率计入与否） | major |
| 4 | 预期使某 core 级指标偏移超过该类型容差的 1/2 | major |
| 5 | 仅影响 support 级指标，或预期偏移 < 容差 1/4 | minor |
| 6 | 纯呈现细节（图表样式、小数位、缩尾分位） | minor |
| 兜底 | 无法估计影响量级 | 按 major 保守处理 |

**全自动模式的裁决边界**（一句可执行规则：**能做且能事后校验的都不停——登记+高亮+回看；做不了或做了也无法判断对错的才停**）：

| 情形 | 处置 |
|------|------|
| minor | 一律 auto：选最符合惯例的解释，登记假设，不打断 |
| major 且有占优解释（上下文可推断/惯例唯一/仅一个候选能对上研报数值量级） | auto 裁决 + 假设标 `major-auto` 高亮 + 强制进 final_report 假设章节 + verify 后必须「回看」该假设是否被数据支持 |
| major 且无占优解释、但候选都可实现 | auto 选可能性较高者；verify 超差且归因指向该歧义时，迭代轮切换另一解释重测（歧义条目记录两次试算） |
| blocking | paused_blocked：暂停，AskUserQuestion 给出候选解释与影响说明（interactive 模式下 major 也问） |

### assumptions.md（假设登记簿，revise 的操作对象）

```markdown
### [AS4] 换手率按多头组单边口径计算
- 来源: A3（auto 裁决）           # 或 coder主动简化 / 数据限制
- 假设内容 / 行业惯例依据
- 影响面: output                  # data / method / param / trading / output → 驱动 revise 定向重跑范围
- 影响 milestone / 影响指标: R1.Turnover（support 级），不影响 IC/Sharpe 核心结论
- 预期影响: 若口径错误，复现值约为研报 2 倍
- 验证后回看: [verify 后填] 复现 88.85% vs 研报 82.40%，偏差 7.8%，假设获数据支持
- 状态: assumed                   # assumed / confirmed / revised
- 高亮等级: major-auto            # major-auto 在 final_report 强制高亮
```

---

## 八、迭代引擎

触发源：final verify 门禁 FAIL / code_audit critical / result_audit 发现问题 / 人工 revise。

每轮严格按序：建 iter_NN/ → 快照 comparison → [N≥2 后台 codex 第二意见] → 派 diagnoser（结论三选一）→ continue 则派 coder（只给限定修改指令与文件范围）→ verifier 重跑 → check_gates 重算判定 → 主会话追加 iteration_log.md 总账（轮次表：触发/失败指标(偏差)/采纳假设/修改摘要/结果(偏差变化)/状态 + 每轮明细节）。

**防兜圈五规则**（写死在 diagnoser 定义与门禁）：
1. 历史强制回顾：iter≥2 时 diagnosis.md 必含「已排除假设」节（gate 检查存在性），禁止重提已排除假设
2. 假设唯一性：同一失败指标+同一假设族出现过且 no_improve → 必须换假设族或 stop_partial
3. 收敛监测：连续 2 轮无指标相对偏差改善超其自身 10% → 强制升级：必调 codex 第二意见且 diagnoser 只能选换假设族/stop_partial/blocked
4. 小步修改：每轮最多 1–2 个修改点；coder 只改 diagnosis 列明的文件范围（changes.md 比对，越界由 result_audit 增量复查抓）
5. 同指标 3 轮红线：同一指标连续 3 轮 fail → 自动 stop_partial（标注「无法收敛，疑数据源口径差异」进报告）

**三出口**：

| 出口 | 条件 | 后续 |
|------|------|------|
| 达标 | check_gates 重算全过 | verdict=pass → result_audit |
| 超限 partial | rounds==max_iter 或 diagnoser stop_partial | verdict=partial；残余偏差+归因+已试假设入报告；**照常走 result_audit→report**（partial 也必须出完整报告与审计） |
| blocked | 核心数据/方法缺失 | paused_blocked，pending_question 写明所需外部输入 |

**revise 定向重跑**（人工 review 后）：`/reproduce revise <id> --assumption AS3 "改用后复权口径"`。planner 更新 assumptions（AS3→revised）→ 按影响面查表定重跑范围 → 只重跑受影响链路 → reporter 增量更新报告。revise 轮记 history（trigger=revise）**不占 max_iter**，单条内部收敛上限 3 轮。

| 影响面 | 重跑范围 |
|--------|---------|
| data / method | 受影响 milestone 的 implement → codex 增量 code_audit → verify → result_audit → report |
| param / trading | implement（config 级）→ verify → result_audit（轻量）→ report |
| output | verify（重出图表/Excel）→ report |

### 自主驱动层（/goal 驱动的无人值守多次迭代）

iterate 引擎本身即目标驱动（goal = check_gates 按 standards.json 重算达标，上限 max_iter）。在此之上用 **Claude Code 内置 `/goal` 命令**作为外层自主驱动（官方功能，交互模式 / `-p` 无头模式 / Remote Control 均可用；设定完成条件后 harness 跨轮持续推进直到条件满足，带耗时/轮数/token 实时面板）。

**标准用法**：启动复现后设置一条目标（skill 在启动完成时打印这条可直接复制的命令，用户粘贴即启用无人值守）：

```
/goal 持续执行 /reproduce continue <report_id>，直到 workspace/<report_id>/state.json 的
status 变为 awaiting_review、done、done_partial 或 paused_blocked 四个终态之一；
到达 paused_blocked 或 awaiting_review 时视为目标达成，停下并汇报待决事项与报告位置
```

**目标措辞的安全设计（重要）**：goal 条件必须写成「**到达四个终态之一即停**」，严禁写成「status == done」或「复现成功」——后者会给驱动层制造冲撞人工闸门、诱导虚报达标的压力。人工闸门语义不变：
- **paused_blocked = 目标达成（停）**：blocking 级歧义/数据缺失必须人工裁决，任何驱动器不得冲过
- **awaiting_review = 目标达成（停）**：最终报告等人工 review，驱动器不得自行 accept
- /goal 只负责「推进到终态」；pass/partial 的达标判定唯一出自 check_gates，goal 达成 ≠ 复现达标

**headless 组合**：`claude -p "/reproduce reports/x.pdf --mode auto" + /goal` 可完全无人值守批量跑（官方支持 -p 模式下的 goal）。

**Codex 侧 goals**（`features.goals` 已启用，含 token_budget/pause/resume 六态管理）：可选用于 iterate 期的长诊断第二意见会话——给 codex 设目标+token 预算让其自主深挖顽固偏差；常规三审查点仍用单次 `codex exec`（短任务无需 goal）。

**备选驱动**（不作首选）：ralph-loop 插件或 /loop 技能包裹 `/reproduce continue <id>`，适用于需要固定节奏轮询或 /goal 不可用的场景；退出条件与人工闸门语义同上。

**接入面统一为 `/reproduce continue <id>`**：状态机幂等续跑是所有驱动器的通用接入点。

---

## 九、防偷懒审计体系（核心）

### 9.1 提取完整性审计（auditor mode=spec，产 extract_audit.md）

独立审计 agent，只给 PDF、report_text.md、spec.md、coverage_matrix.md 四个文件路径，**不给提取 agent 的完成汇报**。

| 检查项 | 操作规程 | 遗漏判定信号 |
|--------|---------|-------------|
| C1 图表编号连续性 | 全文正则搜「图N/表N/图表N/Exhibit N」，取最大编号与全部编号集合，对照 spec 登记清单 | 出现过的编号未登记 → 每缺 1 号一条遗漏（含页码）；声明 fig_max 与独立重算不一致 → fail |
| C2 逐页覆盖扫描 | 对照 spec「页面覆盖表」逐页核对 | 含 ≥3 个百分数或公式符号的页无要素关联且无类型标注 → 遗漏嫌疑 |
| C3 触发词检查 | 全文搜：敏感性、稳健性、参数、分组、分年度、子样本、分市值、牛熊、附录、进一步 | 命中页无 SA/F/R 关联且无排除说明 → 遗漏嫌疑（防「漏掉参数敏感性分析」的直接防线） |
| C4 计数交叉 | 摘要/引言/结论中的计数声明（「我们测试了 12 个因子」「从四个角度改造」） | spec 对应类别要素数 < 声明数 → fail 级遗漏 |
| C5 基准表完备 | 每个 R 要素行列数与 tables_extracted.md 对应表比对 | 少行/少列（抄一半）→ fail |
| C6 幻觉引用抽查 | 随机抽 10 条要素（覆盖各类别），按页码回 report_text.md 查原文摘录（允许 OCR 级模糊匹配） | 摘录在该页找不到近似文本 → 幻觉引用，critical |

### 9.2 codex 盲提取交叉验证（spec_audit 内，防锚定效应）

拿着 spec 找漏往往找不全；独立重做一遍再 diff 更能暴露系统性遗漏。codex spec 审计采用**单会话两阶段协议**（prompt 明确顺序）：

- 阶段一（盲）：不读 spec.md，仅凭 report_text.md + tables_extracted.md 产出轻量清单 spec_codex.md（要素名+类别+页码+关键参数/数值）
- 阶段二（diff）：读 spec.md，对齐两份清单 + R 表逐格核对，输出结构化意见

diff 裁决（主会话派对比归入 extract_diff.md，每条 `| DIF-01 | 类别 | 描述 | 页码 | 裁决(adopted/dismissed/corrected) | 依据 |`）：

| diff 类别 | 裁决规则 |
|-----------|---------|
| 仅 codex 有 | 回原文核对：确有 → Claude 遗漏，补入 spec（日志记来源）；没有 → codex 幻觉，dismissed 留记录 |
| 仅 Claude 有 | 确有 → 保留（常因 pdftotext 丢表格致 codex 看不到，同时提示修补 tables_extracted）；没有 → Claude 幻觉，critical |
| R 类数值不一致 | 以 PDF 原文为终审（审计 agent 直接读 PDF 对应页）；两者都错 → 重抄并登记歧义 |

### 9.3 实现忠实性审计（auditor mode=code，产 impl_audit_m{X}.md）

输入 spec + 矩阵 + src/ + assumptions，**不给 coder 完成汇报**。对当前 milestone 全部 done 行逐条核对：

| 维度 | 规程 | 判定 |
|------|------|------|
| 公式一致 | 打开实现位置指向的函数，逐符号对照：窗口、算子、分子分母、时点（t/t-1） | consistent / deviation_declared（assumptions 有登记）/ **deviation_undeclared**（major；core 要素 critical） |
| 参数一致 | B 类取值反查 config；函数体内魔法数字逐个反查 spec/假设 | config 值不同 → major；魔法数字无出处 → minor 登记 |
| 实现位置真实 | 文件:函数必须真实存在且非 pass/TODO 空壳 | 空壳 → **虚报 critical**，状态打回 in_progress |
| 代码反查 | strategy.py 每个公开函数映射回要素 ID；映射不上的逻辑块要求解释 | 无法解释的「私货」（私自替换研报方法）→ major |
| 简化声明 | 代码注释中「近似/简化/暂用」字样 vs assumptions 登记比对 | 注释承认简化但未登记 → 登记漏报 |

### 9.4 证据链核验（verifier 产 evidence_manifest.md，全难度必做）

| 规则 | 断言 |
|------|------|
| E1 运行证据 | verifier 亲自执行 main.py；run_log.md 记完整命令、退出码、起止时间戳；exit≠0 一律 fail，禁止「部分成功」 |
| E2 新鲜度 | results/ 产物 mtime 晚于 src/ 最近修改；否则判「拿旧结果冒充」，重跑 |
| E3 文件完备 | metrics.json 可解析且 comparison 非空；必需图表全存在且 >15KB；Excel 非零字节 |
| E4 三方数值一致 | 抽 3–5 个核心指标逐位核对 metrics.json == verify_report 引用值 == backtest_summary.xlsx（不一致 → 报告是编的，critical） |
| E5 样本量合理 | n_periods 与 spec 区间推算比对（月频 13.4 年 ≈ 161 期），偏差 >10% → 区间被截断嫌疑 |
| E6 时间链 | spec → src → results → verify_report 的 mtime 单调递增；乱序 → 先写结论后跑数嫌疑 |

每条证据格式：声明来源 / 证据类型 / 证据（文件+行号+命令+时间戳）/ 佐证 / 核验方式（亲自执行，非转述）/ 结果。

### 9.5 反虚报机制（LLM 作弊模式对照表 K1–K8）

| # | 作弊模式 | 针对性检测 | severity |
|---|---------|-----------|----------|
| K1 | 硬编码研报数值假装复现 | 从 R 类提取全部基准数值字面量 grep src/（计算路径命中即嫌疑）；终审用**扰动测试** | grep 命中 critical；扰动不变 critical 实锤 |
| K2 | 结果「过于完美」 | 全部对比指标相对偏差同时 <0.5%（数据源不同的 factor/ml 几乎不可能）→ 触发扰动测试 | 触发加测，不直接定罪 |
| K3 | 占位图/空白图 | 初筛 PNG<15KB；主判定：auditor(result) 用视觉实际查看图片——曲线条数=分组数、坐标范围与 metrics 吻合（净值终点 ≈ 1+累计收益） | 空白/占位 critical；图数不符 major |
| K4 | 未运行就声称通过 | E1/E2/E6（日志+时间戳链） | 无日志或时间倒挂 critical |
| K5 | 静默吞错 | grep `except` 块内无 raise/log 的静默继续；run_log 中 skip/warning 计数 | 关键计算路径 major |
| K6 | 偷偷缩小范围提速 | config 与 metrics 实际 start/end、股票池规模对照 spec；月截面股票数量级抽查（全 A 应 3000–5000） | 与 spec 不符且无假设登记 major~critical |
| K7 | 幻觉引用（编页码/原文） | C6 抽查回原文 | critical |
| K8 | 声称已修复实未改 | responses 标 accepted 的意见必须对应文件 mtime 变化/diff 非空；复审定点核对 | 无变更痕迹 critical，该 coder 输出全部降信 |

**扰动测试规程**（防 K1/K2 杀手锏；hard 必做一次，触发时任何难度都做；verifier 执行）：选必然影响结果的参数（首选回测截止日提前一年；备选分组数 10→5），以命令行参数/环境变量覆盖重跑 main.py 输出到 `results/perturb_check/`（不改源文件，跑完删临时输出）；断言核心指标相对变化 >0.1%。完全不变 → 输出与输入解耦，硬编码实锤 critical。记入 evidence_manifest。

### 9.6 防主流程偷懒六条硬规则（SKILL.md 置顶）

1. **门禁即代码**：任何 stage 结束必须运行 check_gates 并把输出贴进回复；FAIL 禁止进下一 stage、禁止口头声称通过
2. **编排与生产分离**：主会话只派发、审门禁、调 codex、写编排记录；严禁亲自撰写 spec/plan/代码/验证结论/最终报告
3. **产物合同逐一点收**：agent 返回后逐一 ls 验证输出合同，缺一即该步失败
4. **状态先行**：stage 开始/结束先写 state（set-stage running/done），杜绝「跑完再补账」
5. **审计逐条回应**：issue 全量编号入 responses 表，gate 校验行数一致且 critical/major 闭环；不允许「总体没问题」式含糊回应
6. **达标判定唯一出口**：pass/partial 只能由 check_gates 依据 standards.json 重算得出；任何 agent 自述结论仅供参考

---

## 十、codex 外部审查集成

### 10.1 通用调用规范

```bash
command codex exec \
  -s read-only \
  --skip-git-repo-check \
  -C /Users/hedi/report_reproduce \
  --color never \
  --output-last-message "workspace/{id}/audit/{point}_audit_codex.md" \
  - < "workspace/{id}/audit/codex_prompt_{point}.md"
```

工程要点：
1. **`command codex`**：用户 zsh 对 codex 有 alias 追加 `--dangerously-bypass-approvals-and-sandbox`；显式 `command` + 显式 `-s read-only` 双保险——审查进程只读，不许 codex 改仓库
2. **prompt 经 stdin**（`-` 占位），避免长中文 prompt 的 shell 转义问题；prompt 由主会话按 `templates/codex_prompts/{point}.md` 骨架填充路径后写盘归档（可追溯，防临场编 prompt 导致审查强度漂移）
3. **结构化输出**：优先 `--output-schema templates/audit/review_schema.json` 强制 JSON（checkpoint/verdict/findings[]{id,severity,category,location,description,suggestion,confidence}）；schema 模式异常则退回「markdown 表格+末行 verdict」约定
4. **模型**：默认用 codex 配置的默认模型；可通过 skill 参数显式指定 `-m`
5. **超时**：Bash timeout 10 分钟；超时/非零退出/输出为空 → 重试 1 次（重试缩减输入：spec 审只喂 R 类章节+图表清单；代码审只喂 strategy.py）
6. **两级降级**：一级——派全新 Claude 子 agent 作「外审替身」（同样材料同样 prompt，禁止读任何过程性文件），state 记 `engine: claude_fallback`；二级——记 `engine: skipped`，final_report 显著标注「该审查点外审缺失」，hard 报告缺外审时可信度评级封顶 B
7. **防 codex 幻觉**：所有 prompt 末尾固定三条——每条意见必须给页码或 文件:行号；未发现问题的维度输出 no_findings，禁止凑数；不确定标 confidence: low

### 10.2 三审查点要点

| 审查点 | 输入材料 | 审查焦点 | 意见前缀 / severity 判据 |
|--------|---------|---------|------------------------|
| spec（extract+plan 后） | report_text.md、tables_extracted.md、spec.md、coverage_matrix.md | ①盲提取（两阶段协议见 9.2）②遗漏 ③R 表逐格抄录核对 ④编号完整性独立重算 ⑤页码真实性抽查 8 条。不做：复述正确内容/评价文风/建议超范围增强 | CDX-S-；遗漏 core 结果表或因子=critical；漏敏感性分析或数值抄错=major；reference 类图表缺漏=minor |
| code（implement 后、verify 前） | spec.md、coverage_matrix.md、assumptions.md、src/ 全部、common 函数签名摘要 | ①F 类公式逐个对照 ②未来函数/前视（披露日对齐、T+1 执行、滚动窗口、标签对齐）③数据对齐（复权/ST 过滤时点/月末截面）④config vs B 类逐项 ⑤作弊模式（附 R 类数值清单让 codex grep 硬编码；静默吞错；范围缩水） | CDX-C-；结果不可信（未来函数/硬编码/方向反）=critical；数值明显偏移（参数错/对齐错）=major；风格效率=minor |
| result（iterate 收敛后） | comparison 对比表、verify_report.md、assumptions.md、ambiguities.md、coverage_matrix.md | ①超差归因是否有证据还是「万能借口」（全推给数据源差异而不给量级推算）②假设→偏差方向一致性（AS 预期偏高实际偏低 → 归因不成立）③未超差指标是否可疑地过于精确（联动 K2）④skip/infeasible 理由是否成立（声称 data_missing 但 catalog 显示可 derive）⑤结论措辞与数据相符性 | CDX-R-；fail 不打回代码，打回 verify_report 归因重写或触发新迭代 |

### 10.3 意见处理协议（audit_responses.md）

`| 意见ID | severity | 摘要 | 处置(accepted/rejected/deferred) | 回应（修复位置 文件:行号 或技术理由） | 复核 |`

| severity | 规则 |
|----------|------|
| critical | **阻断**：门禁 fail；必须修复并复审（复审输入=修复 diff+原意见+定位文件，缩减 prompt）；未清零不得推进 |
| major | 必须逐条回应（accepted 修 / rejected 说理）；未回应的 major 视同 critical |
| minor | 登记即可，计数进 final_report |
| 升级 | 同一意见连续两轮 rejected 且 codex 复审坚持 → 升级人工；同一审查点审→修→复审最多 3 轮，仍有 critical → paused_blocked |

accepted 必须给修复位置且复核列最终 pass（配合 K8 的 mtime/diff 核验）；rejected 理由自动汇入 final_report 遗留清单。

---

## 十一、关键 schema

### state.json（tools/state.py 唯一写入口，原子写+schema 校验）

```
schema_version / report_id / pdf_path / paths{workspace,src,output}
mode(auto|interactive) / max_iter / type / tags / difficulty(+override) / feasibility
current_stage / status(running|paused_blocked|awaiting_review|done|done_partial|aborted)
stages{每stage: status(pending|running|done|failed|skipped|blocked), attempts, 时间戳, issues计数}
gates[{stage, checks[{id,desc,result}], verdict, timestamp}]          # G-XX 记录
external_reviews[{checkpoint, engine(codex|claude_fallback|skipped), verdict, critical/major/minor 计数, raw路径}]
milestones[{id,name,deps,implement,code_review,verify}]
iteration{current, max, history[{iter,trigger,failed_metrics,diagnosis,hypothesis,result,metrics_delta}]}
verdict{result(pass|partial|fail), comparison_file, metrics_pass/total, decided_at}
coverage_stats{total,done,skipped,infeasible,pending}
assumptions{total,assumed,confirmed,revised} / blockers[] / pending_question / events[]
```

**断点续跑算法**（skill 启动执行）：show 读态 → 按 status 分派（done→建议 revise/accept；paused_blocked→展示 pending_question 问人工；awaiting_review→等指令；running→续跑）→ 沿 stage_order 找第一个非 done/skipped 的 stage → 进入前幂等自愈（check_gates 若产物已在且 PASS 直接标 done 跳过，否则 attempts+1 重跑覆盖写）→ iterate 按 iter_NN 三件套完整性决定从诊断/修正/重跑哪步续起。

### comparison.json（verifier 产出）

metrics[]{key, name, report_value, reproduced_value, rel_dev, direction_match, tolerance_key, source_page, source_element, layer(ml类), pass} + qualitative[]{key, expect, observed, pass} + overall_pass/pass_count/total。**check_gates 按 standards.json 重算 rel_dev 与 pass，不信任文件内结论**；codex result 审计再对照 xlsx/metrics.json 复核数值真实性。

### templates/standards.json（达标标准机器化）

| 类型 | 容差要点 |
|------|---------|
| factor | rank_ic_mean{rel_dev≤0.20, 同向, abs_eps 0.005}、icir{0.20,同向}、ls_annual_return{0.15}、ls_sharpe{0.15}、turnover{量级一致}、default{0.15}；qualitative: 分组单调性；必需图表 5 张 + backtest_summary.xlsx |
| timing | annual_return/max_drawdown/sharpe/win_rate/profit_loss_ratio{0.05}、trade_count{量级}、default{0.05}；图表 5 张 |
| allocation | default{0.10} + weight_path_similarity |
| fixed_income | ytm/duration/convexity{0.05 计算类}、组合类{0.10} |
| ml | 分层：data_feature 层{0.05 精确}、model 层{仅方向性: ic_same_sign / group_monotonicity / top_group_rank} |

约定：未收录指标落 default；abs_eps 处理近零值（|研报值|<abs_eps 改用绝对偏差）；每份研报可在 plan 阶段登记指标级覆盖（记入 state 与报告）。

---

## 十二、final_report.md 审计章节（附录A）

- **A.1 覆盖率统计**：分类别 total/done/skipped/infeasible/覆盖率 + **未复现要素逐条说明**（skipped/infeasible 全量列出，不允许缺席）
- **A.2 假设清单与验证后回看**：全部假设 + major-auto 高亮 + 回看结论（数据支持/不支持）
- **A.3 外部审查结论**：三审查点 engine/verdict/critical-major-minor 计数/采纳-拒绝-搁置/遗留 rejected 清单（降级的显著标注）
- **A.4 迭代历史摘要**：轮次/触发/改动/关键指标变化
- **A.5 遗留偏差与归因**：指标/研报值/复现值/偏差/容差/归因/归因状态
- **A.6 反虚报核查记录与总体可信度**：扰动测试结果、证据链条数、幻觉抽查命中率、**可信度评级**：
  - A = 覆盖率≥90%（core 100%）+ 三外审通过 + 零 critical 遗留
  - B = core 覆盖 100% 但 support 有缺 / 外审有降级或缺失
  - C = 存在 core 未复现或 major 遗留未回应（正文结论区显著提示）

---

## 十三、skill 编排（/reproduce）

位置：`.claude/skills/reproduce/SKILL.md` + `stages/*.md`（11 张执行卡，进入该 stage 按需读取，统一格式：入口条件/动作序列（含派发 prompt 要点与产物合同）/出口门禁 checklist/失败处理分支）。**删除旧双入口**：`~/.claude/commands/reproduce.md` 与 `.claude/agents/reproduce.md`。

```
/reproduce <pdf_path> [--mode auto|interactive] [--max-iter N] [--id name] [--difficulty easy|medium|hard]
/reproduce continue <report_id>          # 断点续跑
/reproduce status [report_id]            # 状态摘要（无参列出全部 workspace）
/reproduce revise <report_id> --assumption <ASid> "<新口径>" | --instruction "<指令>"
/reproduce accept <report_id>            # review 通过 → done
```

主循环协议（写死）：读 stage 执行卡 → 前置断言 `check_gates --stage {prev} --assert-done` → 派 agent/调 codex/跑工具 → 逐一点收产物 → 出口门禁 `check_gates --stage {cur}` → PASS 才 set-stage done 进下一阶段；同一 gate 连续 3 次 fail → 暂停问用户。

无人值守模式（见 §八自主驱动层）：首选内置 `/goal`——skill 在启动 stage 完成后**打印可直接复制的 /goal 命令**（目标条件=到达四个终态之一即停），用户粘贴即启用；备选 /loop 或 ralph-loop 包裹 `/reproduce continue`。paused_blocked 与 awaiting_review 两个人工闸门任何驱动器不得冲过。

TaskCreate 镜像：plan 定稿后按 milestone×stage 建任务树+依赖链，仅作 UI 进度镜像；state.json 为唯一真相源。

---

## 十四、迁移策略与实施批次

### 资产处置

| 现有资产 | 处置 |
|---------|------|
| `~/.claude/commands/reproduce.md`、`.claude/agents/reproduce.md`、`Command/` | 删除（防三份编排逻辑打架） |
| `.claude/agents/CLAUDE.md` | 迁至项目根 CLAUDE.md 并按新结构改写 |
| quant-pdf-reader | 拆分 → quant-extractor + quant-planner |
| quant-coder | 保留改造（输入/输出合同、矩阵回填、禁自验证条款） |
| quant-verify | 改造 → quant-verifier（**保持 opus**；模式 B 剥离给 auditor；旧内嵌 /codex:rescue 改为 Bash 直调 `codex exec` 辅助验证；增 evidence_manifest 与扰动测试义务） |
| 新增 agent | quant-auditor（三模式）/ quant-diagnoser / quant-reporter |
| `plan/{id}/plan.md` ×3 | 移入 workspace/{id}/plan.md；plan/ 退役 |
| common/ src/ output/ reports/ | 原样保留 |
| 3 个已完成案例 | legacy 化：`state.py init --legacy`（stages 全 skipped，verdict 按现有 verify_report 人工录入）；**test 案例作为新流程验收用例** |
| pyproject.toml | 依赖增 pypdf、pdfplumber（poppler 的 pdftotext 优先，缺失时 pypdf 兜底） |

### 实施批次（4 批，每批可独立验证）

| 批 | 内容 | 验证方式 |
|----|------|---------|
| 1 基础设施 | tools 三脚本 + standards.json + _spec_template.md + templates/audit/ + codex_prompts/ + state schema | 对旧 test 案例手工造 comparison.json，`check_gates --stage verify` 试算；`pdf_extract.py reports/test.pdf` 出文本 |
| 2 agents | 7 个 agent 定义（新增 3、改造 3、拆分 1） | 单独派 extractor 处理 reports/test.pdf 出 spec 三件套，人工抽查页码引用真实性 |
| 3 skill | SKILL.md + 11 张执行卡；删旧入口 | status/continue 读态逻辑；对半成品 workspace 断点续跑演练 |
| 4 迁移与验收 | 3 案例 legacy 化；CLAUDE.md 改写；**端到端验收** | `/reproduce reports/test.pdf --mode auto` 全流程跑通（含三次 codex 审查）；对照旧 verify_report（多空年化偏差应仍 <5%）；**人为注入一个错误参数**验证迭代引擎与审计能抓到；扰动测试演练 |

---

## 十五、设计裁决记录（两份子设计的冲突消解）

| 冲突点 | 裁决 | 理由 |
|--------|------|------|
| 目录：workspace 统一 vs 保留 plan/ | workspace/{id}/ 收拢全部文书，src/output 原位 | 状态与审计产物同处一域；代码运行约定零改动 |
| 要素 ID：通用 E01 vs 类型化 D/F/B/R/SA/FIG/TBL | 类型化前缀 | FIG/TBL 用研报原生编号使连续性审计变机械检查 |
| PDF 转文本：pypdf vs pdftotext+pdfplumber | pdftotext -layout 优先（pypdf 兜底）+ pdfplumber 表格 | layout 保持利于 codex 读表；表格附录供 C5/盲抄核对 |
| severity 词表：P0/P1/P2 vs critical/major/minor | 审计意见统一 critical/major/minor；歧义等级 blocking/major/minor | 两套语义不同物：意见=修复优先级，歧义=介入等级 |
| codex spec 审：独立盲提取调用 + 审查调用（2 次）vs 单会话两阶段 | 单会话两阶段协议（盲提取→diff→逐格核对） | 省一半成本时延；prompt 顺序保证盲性；不可靠时可拆分 |
| codex 调用：参数内嵌 prompt vs stdin | stdin（`-`）+ prompt 文件落盘 | 免转义；可追溯 |
| 反虚报执行者 | E1–E6 由 verifier 随跑随记；K2/K3/E4 复核由 auditor mode=result；扰动测试由 verifier 执行 | 证据采集与证据审计分离，不新增 agent |
| verifier 模型与 codex 能力（用户裁定） | 保持 opus 不降配；可 Bash 直调 codex exec 做故障定位与超差口径自查 | 用户明确要求；codex 自查可避免「口径抄错」浪费整轮迭代；直调 CLI 不违反子 agent 不嵌套约束 |
| 多次迭代驱动：/goal（用户提议，经查证为两 CLI 内置功能） | **首选 Claude Code 内置 /goal**（`/goal <condition>`，每次回复后检查条件持续工作，交互/-p 均可用）包裹 `/reproduce continue`；codex 侧 goals（已启用，带 token_budget）可选用于长诊断会话；ralph-loop//loop 降为备选 | goal 条件必须写「到达四个终态之一即停」而非「status==done」——防驱动层冲撞人工闸门/诱导虚报；goal 达成 ≠ 复现达标（判定唯一出自 check_gates）；/goal 需受信任工作区 |
