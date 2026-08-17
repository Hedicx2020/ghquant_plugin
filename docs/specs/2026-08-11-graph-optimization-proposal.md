# 研报复现管线图工程优化方案

> 状态：待审阅。本文档为管线 token/墙钟优化的总方案，审阅通过后按「四、实施顺序与验证方式」分批落地。
> 日期：2026-08-11
> 输入材料：依赖图观察 67 条（含真实字节数/耗时证据）、双视角图分析（上下文流量 + 关键路径）、三个候选设计方案（保守派/结构派/激进派）、两位独立评审结论（实用主义视角 + 保真守门视角）。
> 上游文档：`docs/specs/2026-07-07-reproduce-v2-design.md`（v2 状态机与 K1–K8 审计体系，本方案不改动其判定语义）、`docs/specs/2026-07-09-plugin-packaging-design.md`（economy 降配与 reporter 瘦身先例）。

---

## 结论先行

两位独立评审一致选定**保守派方案（蒸馏层守界 + 摘要传递 + 机器预检下沉）**为基线（加权得分 8.3 / 8.25，结构派 6.95 / 7.63，激进派 6.25 / 7.25），并从两个败者方案中嫁接 6–7 件低风险部件补强。核心数字：单次完整复现可裁剪 **50–90 万 token**（pass 路径，无 iterate），进入 iterate 的失败路径再省 **20–40 万**（r004 规模，且这部分恰是终态 blocked 时的全额沉没）；墙钟侧以停滞哨兵截断实测最大的停滞黑盒（r001 两段合计 40.65h、r007 idle 119h、style 停滞 136h）。全部裁剪对象均为**无合同依据的无意冗余**，codex 三审、盲提取全文、K1 扰动测试、auditor(code)/verifier 的 src 全量读等刻意冗余一律不动。

---

## 一、现状诊断——用真实数字说话

### 1.1 案例盘点（9 案例，完成率 33%）

| 案例 | 状态 | verdict | events 跨度 | workspace 体积 | 关键病灶 |
|------|------|---------|------------|---------------|---------|
| r001_signature_transformer_allocation | done | pass | 57.86h | 598KB | code_audit 24.14h + report 16.51h 两段零事件黑盒，占忙时 75% |
| r002_liquid_neural_networks | paused_blocked | — | 30.75h | 440KB | idle 26.2h，verify 卡 running |
| r003_equity_factor_timing_cn | awaiting_review | pass | 12.18h | 526KB | 最干净 pass（busy 11.54h），implement 占 57% |
| r004_all_a_style_box | paused_blocked | fail | 18.73h | **1.06GB** | iterate 4 轮 10.74h blocked + result_audit 8.58h failed 双段沉没；95.6% 体积为扰动测试残留（单 ndjson 335MB） |
| r005_macro_regime_factor_allocation | aborted | — | 0.12h | 266KB | 与 r006 同一 PDF（report_text 均 253,038B），弃后重起 |
| r006_macro_regime_factor_allocation | paused_blocked | — | 22.29h | 641KB | 同 PDF 从零重跑：plan 9.04h + spec_audit 1.32h 双份沉没 |
| r007_cross_market_return_forecasting | paused_blocked | — | **132.83h** | **3.37GB** | busy 仅 13.7h，idle 119h 停在 verify running；checkpoints 占 84.6%（单 parquet 1.6GB） |
| ssrn_6115073 | done | pass | 25.94h | 778KB | assumptions.md 已胀至 95,770B（其 spec.md 的 2 倍） |
| style_factor_subdomain | running | — | 136.00h | 111KB | 卡 plan running，busy 仅 0.36h，停滞以天计未被发现 |

### 1.2 Top5 token 热点（文件 × 全量读取次数 = 放大字节数）

| 排名 | 产物 | 单体实测 | 全量装载方 | 放大字节数/次复现 | 估算 token/次 |
|------|------|---------|-----------|------------------|--------------|
| 1 | report_text.md | 135.8KB(r001) / 253KB(r005/r006) / 242.7KB(ssrn) | 设计内 3 个（extractor、auditor(mode=spec)、codex 盲提取）；**案例证据边显示它绕过蒸馏层流入全部 7 个案例的 plan 与 implement**，无任何合同依据 | ssrn 规模 5 次 ≈ **1.21MB** | **25–40 万**（按中英混排约 3B/token） |
| 2 | iterate 回环（diagnoser 输入合同） | r004 四轮 iter bundle 164,658B | 每轮全量重读 spec+plan+assumptions+src 全目录+comparison+**全部历史 iter_NN/diagnosis.md**；仅历史诊断一项四轮累计重读 ≈325KB（58.5K+111.8K+154.7K 逐轮递增） | r004 四轮合计 ≈0.5–1MB 等值 | **50–100 万**（进入时）；每新增一轮边际 15–25 万；终态 blocked 即全额沉没 |
| 3 | spec.md | 29–77KB（r006 77,439B、ssrn 49,305B） | 7–9 类 agent 全量读（planner、auditor 三模式、coder、verifier、diagnoser、oos、reporter）+ 2 份 codex prompt 内嵌（spec_audit 盲提取 diff、code_audit 的 R 类清单占位符） | 0.4–0.7MB | **15–26 万** |
| 4 | assumptions.md | 26–96KB（ssrn 95,770B） | 6 类 agent 全量读，且 planner/coder/verifier 同一 invocation 先读后写；模板「只增不删」使其单调膨胀；与 ambiguities.md 存在 auto 裁决双边复制 | 0.27–0.58MB | **9–19 万** |
| 5 | reporter 输入面（11–12 个文件） | 250–350KB/次 | spec+matrix+ambiguities+plan+assumptions+responses+evidence+iteration_log+末轮 diagnosis+comparison+verify_report(+oos)；同一条 codex 意见固定三份拷贝（codex 原文 → audit_responses 全表 → final_report rejected 清单） | 250–350KB | **8–15 万** |

次热点：src/{id}/ 目录 50–150KB × 5–7 次全量读（auditor code、coder、verifier、diagnoser、oos，iterate 每轮再加 2 次）≈ 8–25 万；state.json 29–50KB × 10–15 次主会话 show/转述 ≈ 10–15 万（每次调用全量 load→改→全量 dump，gate --record 再触发一次全量写，events/gates 只追加不清理）；comparison.json 与 verify_report.md 的对比表全文复制（auditor result/diagnoser/reporter 三类读者同读两份）≈ 3–6 万。

模板侧根因（注定单调膨胀的条款）：`_spec_template.md` L98 R 表逐格抄录、L132–141 逐页覆盖表、L170–196 图表全集登记；`coverage_matrix.md` L23–25 每要素一行 + L57–63 只增不删；`assumptions.md` L30 revised 旧假设保留存档；`audit_responses.md` L33 一条意见一行不许合并；`codex_prompts/code_audit.md` L39–45 R 类清单内嵌 prompt。

### 1.3 关键路径耗时构成

主链（小时，9 案例实测区间）：

```
init(0.01) → extract(0.2–0.6) → plan(0.2–2.1，异常 r006 9.0) → spec_audit(0.3–6.3)
→ implement(2.5–7.9，中位约 6.1) → code_audit(0.6–24.1，中位约 1.2) → verify(0.4–1.9)
→ [iterate 0–10.4] → result_audit(0.2–8.6) → oos(0.4–1.1) → report(0.2–16.5) → review(人工)
```

三个 pass 案例墙钟：r003 12.2h / ssrn 25.9h / r001 57.9h。三条结构性结论：

1. **稳定成本 vs 方差成本分离**：implement（中位约 6.1h，r003 中占 57%）是唯一稳定大头；code_audit 24.1h、report 16.5h、spec_audit 6.3h、plan 9.0h 四个极端值全部伴随 **events 零记录黑盒**——属会话中断/跨夜停滞/人工间隙，不是计算。优化主战场是消除停滞与返工，不是压缩计算。
2. **可并行却串行**：设计写明 medium/hard 默认 code_audit ∥ verify，实测 4/4 案例严格串行（每案例白流 36–77 分钟，合计约 200 分钟）；result_audit ∥ oos 3/3 串行（每案例 22–64 分钟）；hard 难度 milestone 间串行（r001 纯空档 113 分钟，5 个 milestone 若按 deps 拓扑并行，7.89h 有望压至 2–3h）。
3. **无停滞哨兵**：r007 span 132.8h 中 idle 119h、style 136h 卡 plan、r002 idle 26.2h、r006 idle 12.2h——paused/running 状态停滞以天计才被发现；stage 内无子步骤事件，状态机无法区分「agent 运行中」与「会话已断」。

### 1.4 iterate 回环成本

- 9 案例中仅 r004 进入（按到达 verify 的 5 案例计进入率 20%），进入即 4 轮跑满 10.35h（约 156 分钟/轮），终态 blocked；result_audit failed → iterate → failed → blocked 双 ping-pong 共 11.3h；rescue 成功率 0%。
- 每轮成本结构：diagnoser 全量重读全部历史 diagnosis（第 4 轮重读前 3 轮 154KB，逐轮递增）+ spec/plan/assumptions/src 全量；verifier 全量重跑 main.py 与全部图表/Excel/evidence；iter_NN/comparison.json 每轮全量覆盖快照。
- 「同指标 3 轮红线」「连续 2 轮无 10% 改善强制升级」等防兜圈规则触发过晚——r004 跑满 max_iter 后才 blocked，前置的机器差分预判不存在。

### 1.5 磁盘与上下文防爆

r004 audit bundle 1.06GB（95.6% 为扰动测试 parquet/ndjson，单文件最大 334,851,298B）；r007 workspace 3.37GB（checkpoints 占 84.6%，m4_portfolio_members.parquet 单文件 1.6GB）。属磁盘/IO 消耗而非上下文消耗，但任一 agent 误 Read 单个 ndjson 即上下文瞬间爆炸（数十万 token + 整轮会话报废）。图中已有 2 条异常大文件观测记录，说明风险已被实际目击。

### 1.6 诊断结论

1. token 热点与墙钟热点同位：r001 最长两段（code_audit 24.14h、report 16.51h）恰对应 src×5 读者与 reporter×11–12 文件两个放大器；r004 的 iterate blocked + result_audit failed 对应逐轮膨胀回环。**砍 token 消耗即砍墙钟。**
2. check_gates.py 是已验证的正确范式：门禁自行解析本地文件、按 standards.json 重算 rel_dev/overall_pass，不把文件读进 LLM 上下文。凡可机器判定的核对（K1 grep、config vs B 类、E4 三方一致、G-FN 输入侧条件、停滞检测、同 PDF 撞库）都应继续下沉工具层。
3. 刻意冗余与无意冗余必须分开处置：codex 盲提取（§9.2）、三审查点、K1 扰动是设计拍板的防作弊开销，不裁；report_text 流入 plan/implement、comparison 全文复制进 verify_report、全历史 diagnosis 逐轮重读、审计意见三份拷贝无任何合同依据，可直接裁。
4. 比任何单 stage 优化更省 token 的是防止失败路径沉没：9 案例 5 例 blocked/fail/aborted，r007 上游 14.3h 投入全沉、r005→r006 同 PDF 双份付费。
5. 单次完整复现可裁剪 token 合计 **60–130 万**（两位 analyst 独立测算口径吻合），且全部落在无意冗余上。

---

## 二、修改方案

### 2.0 方案选型

| 方案 | 降本 | 风险控制 | 保真 | 加权总分（评审一/二） | 结论 |
|------|------|---------|------|---------------------|------|
| 保守派：蒸馏层守界 + 摘要传递 + 机器预检下沉 | 7 / 7 | 9 / 9 | 9 / 8.5 | **8.3 / 8.25** | **选定基线** |
| 结构派：蒸馏层契约化 + 机器判定下沉 + 增量证据链 | 8 / 8.5 | 6 / 7 | 7 / 7.5 | 6.95 / 7.63 | 提供 4 件嫁接件 |
| 激进派：产物 DAG + 结构化记录架构 v3 | 9 / 9.5 | 4 / 5.5 | 6 / 7 | 6.25 / 7.25 | 提供 3 件嫁接件；DAG/jsonl 化留 v3 |

选定理由（双评审共识）：保守派 13 条改动中 8 条低风险、4 条中风险，唯一中高风险项（iterate digest）自带灰度方案；全部改动为「agent 合同文字 + 新增确定性工具 + stage 卡补丁」，十二阶段状态机、8 agent 划分、K1–K8、G-XX 门禁判定出口一字不动；机器解析函数全部复用 check_gates 既有实现，不产生第二套口径；对已跑通 9 案例的管线回归面最小。其两处短板（文本禁令无强制力、并行未落实）恰好可用败者方案的低成本部件补齐。

**嫁接件清单**（并入下文各条）：① guard.py PreToolUse 机器禁读钩（激进派）；② 单消息同批并行派发硬模板 + Monitor 完成通知（结构派）；③ 切片 manifest.json 新鲜度断言（结构派）；④ iterate 趋势机器预警（结构派）；⑤ iter≥3 自适应恢复全历史投喂（激进派）；⑥ codex 调用一律 run_in_background（激进派）；⑦ second_opinion 保留全量历史投喂（激进派，修复保守派 change 4 违反「双通道只降其一」的失分点）。

### 2.1 立即可做（低风险纯收益，当周可上）

#### A1. report_text 禁读红线 + 机器强制护栏（保守派 change 1 + 嫁接 guard.py）

- **改哪个文件**：`.claude/agents/{quant-coder,quant-verifier,quant-diagnoser,quant-oos-analyst}.md` 输入合同「缺失处理」段；`.claude/skills/reproduce/stages/{plan,implement,verify,iterate,oos}.md` 派发模板；新增 `tools/guard.py` + `settings.json` PreToolUse hook。
- **怎么改**：四个 agent 各加禁读条款——「workspace/{id}/spec/report_text.md 与 tables_extracted.md 不属于本 agent 输入，禁止 Read/grep；spec 信息缺口一律登记交主会话，不得回原文自救」（quant-planner.md 第 20 行已有同款条款，本次补齐到其余四个）；五张 stage 卡派发步骤加主会话自查句「派发 prompt 中如出现 report_text/tables_extracted 路径即违规，删除后再发」。guard.py 作为 PreToolUse hook 把文字红线升级为机器拦截：白名单外 agent 对这两个路径的 Read 直接拒绝并返回合法切片获取指引；同时实现大文件护栏——`audit/perturbation_*`、`checkpoints/` 写入禁读名单，合同外单文件 >500KB 须先向主会话申请切片，*.ndjson/*.parquet 一律禁 Read（只能经工具查询）。
- **预计省多少**：切断 plan/implement/diagnose/oos 四处实际流入，**15–30 万 token/次**（report_text 135.8–253KB，单次全量装载 4.5–8.5 万）；护栏防 335MB ndjson 误读的尾部爆炸（单次即数十万 token + 会话全损）。
- **审计体系等价替代**：无裁剪——这些路径本就不在任何 agent 的输入合同内，禁令是把既有设计意图写明并赋予强制力。agent 私下回原文补齐会使 spec 缺口永不暴露、spec_audit 盲提取 diff 失去校验对象，切断后缺口改为「声明缺失 → 主会话补派 extractor」，正是设计想要的暴露行为。codex 盲提取全文通道保留（§9.2 刻意冗余不动）。

#### A2. 停滞哨兵 + 子步骤埋点 + codex 后台化（保守派 change 10 + 嫁接激进派调用方式）

- **改哪个文件**：`tools/state.py`（set-stage running 记 running_since、record-event 刷新 updated_at、新增 `stall-check <id>|--all` 子命令、show 输出追加停滞告警）；四张含 codex 调用的 stage 卡（spec_audit/code_audit/result_audit/iterate）调用前后各插一条 record-event（codex_start/codex_end）；`SKILL.md` 第七节加 stall-check 驱动协议；四张卡的 codex 调用样板改为 `run_in_background` + Monitor 完成通知。
- **怎么改**：当前 stage=running 且 now − max(stage.updated_at, 最新 event 时间) > 阈值（默认 3h，`.reproduce.json` 的 stall_hours 可覆盖）时输出 STALL 告警行；/goal 或 /loop 驱动器每轮 continue 先跑 `stall-check --all`，命中即 PushNotification 通知人工并暂停推进该案例，不干等。codex_start 后 10 分钟内不报 STALL（区分「codex 还在跑」与「会话已断」）。
- **预计省多少**：墙钟主战场——r001 两段黑盒 40.65h（对照组仅 1.2h/0.35h）、r007 idle 119h、style 136h、r002 idle 26.2h；3h 阈值告警生效后**单案例避免 10–100h 级停滞**，并间接止损 r007 式上游 token 全沉。token 侧直接消耗为零。
- **审计体系等价替代**：**全方案唯一可诚实写「零 fidelity 代价」的一条**——纯观测性埋点与告警，不裁剪任何内容、不改变任何门禁与审计语义，state 只新增字段不改既有字段；事件埋点反而增厚审计账簿（事后图分析从跨案例对照推断升级为事件定位）。

#### A3. state.py append-review + events 归档（保守派 change 8）

- **改哪个文件**：`tools/state.py`（新增 `append-review <id> '<json条目>'` 子命令；record-event 在 events 超 100 条时把最老 50% 迁移到 `workspace/<id>/events.log`，state.json 只留 events_count 与最近 50 条）；`stages/{spec_audit,code_audit,result_audit}.md` 的台账「读改写三步」（含整段「警告：set 是整体覆盖」口诀）替换为单条命令。
- **预计省多少**：三处台账读改写各要求主会话 Read state.json 全文（r007 已 50KB、r004 82 事件持续膨胀），单次复现 3–6 次 ≈ **3–6 万 token 主会话上下文**；另消除「读改写三步丢一笔记录」的实发操作风险。
- **审计体系等价替代**：追加与读改写语义等价，外审台账 A.3 章节素材一条不少；追溯链从单文件变「state.json + events.log」两文件，show 末尾打印指引，追溯能力不降。接近零代价。

#### A4. 同 PDF 撞库缓存 + 撞库提示（保守派 change 7）

- **改哪个文件**：`tools/pdf_extract.py`（run_extract 开头计算 PDF 内容 sha256，缓存 `~/.cache/reproduce_pdf/<工具版本号>/<sha256>/`，命中直接拷贝幂等产物）；`tools/state.py` init 记 pdf_hash + 撞库查询；`stages/init.md` 加撞库步骤；`SKILL.md` 3.1 补规则。
- **怎么改**：init 前按 pdf_hash 扫全部 workspace——同 hash 已有案例（尤其 aborted/paused_blocked）时主会话必须 AskUserQuestion 提示「该 PDF 已有案例 rNNN（状态 X），建议 /reproduce continue 续跑」，用户坚持新建才放行；aborted 案例优先原 ID 续跑，同 PDF 另起新 ID 须显式说明理由。缓存 key 含工具版本号，pdf_extract 升级后旧缓存自动失效。
- **预计省多少**：r005→r006 实证同一份 253KB PDF 两次起跑，重做 extract 0.28h + plan 9.04h + spec_audit 1.32h。缓存直接省 extract 重做（**确定性 2–4 万 token + 0.3h**）；撞库提示被采纳则省整个上游（**条件性 10–15 万 token + 10.6h 墙钟**）。r003/r004 亦为同一 PDF（report_text 均 84.8KB）各自重跑全链。
- **审计体系等价替代**：同一 PDF 的提取产物由确定性工具产出、位级一致，缓存复用不改变任何下游输入；sha256 按内容算，同名不同内容 PDF 天然免疫。零实质代价。

#### A5. G-FN 输入侧预检（保守派 change 11）

- **改哪个文件**：新增 `tools/report_digest.py --precheck <id>`；`stages/report.md` 步骤 2 改为「先预检、全绿才派 reporter」。
- **怎么改**：机器核验 G-FN 全部输入侧条件——矩阵无 pending/in_progress 行（G-FN-3 对象）、assumptions.md 无 [verify 后填] 残留（G-FN-4 对象）、audit_responses 可解析且 rejected 清单可机抽（G-FN-5 对象）、coverage_stats.total>0（G-FN-6）、comparison.json 可解析、rejected 意见 ID 清单机抽落盘。任一红灯主会话直接回上游修，不消耗 reporter 上下文。判定逻辑全部复用 check_gates 既有解析函数（load_matrix_rows/_parse_audit_responses）。
- **预计省多少**：常态 1–2 万/次；返工场景收益大——r001 report 16.51h 对照 r003 0.16h 差 60–100 倍，大概率是 G-FN 反复 fail → 重派 reporter（每重派一次 250–350KB 输入面 ≈ 8–12 万 token），预检把三类最常见 FAIL 在派发前拦截。
- **审计体系等价替代**：G-FN 出口门禁一项不改，预检只是同一判定逻辑的输入侧前置，不产生新判据、无错误放行风险。fidelity 上唯一变化是返工路径变短、出错窗口前移，属正面。

### 2.2 中期改造（需回归验证）

#### B1. spec.md 机器切片分发（保守派 change 2 + 嫁接 refs 闭包 + manifest 新鲜度断言）

- **改哪个文件**：新增 `tools/spec_slice.py`；`stages/{implement,verify,code_audit,oos,report}.md` 派发步骤；`.claude/agents/{quant-coder,quant-verifier,quant-oos-analyst,quant-reporter}.md` 输入合同。
- **怎么改**：spec_slice.py 按既有门禁正则（`^### \[(D|F|B|R|SA)` 与 H2 章节，与 check_gates 共用同一套解析器，防止口径漂移）把 spec.md 拆为 `spec/slices/{frontmatter_card.md, D.md, F.md, B.md, R.md, SA.md}`，并按 plan.md frontmatter 的 milestones[].elements 聚合 `slices/m{mid}.md`；**嫁接一**：机器解析要素间 D/F 引用关系，被引用要素全文自动随切片携带（refs 闭包，压掉「plan 的 elements 漏登一个关联要素即缺上下文」的最大漏切风险）；**嫁接二**：生成时把 spec.md 的 sha256+mtime 写 `slices/manifest.json`，spec 变更后切片自动失效强制重生成（防陈旧切片静默误喂）。合同分发：coder 收 m{mid}.md；verifier 收 R.md（现合同本已限定 R 类基准表，切片只是把限定机械化）；auditor(mode=code) 收 F+B+本 milestone 的 D/SA 要素块；oos 收 B+R；reporter 收 R+SA+frontmatter_card。每个合同统一加逃生门：「需要切片外要素时，允许按要素 ID grep spec.md 原文定位后 Read 该行块」。codex 两审继续持 spec.md 全文（刻意冗余不动）；G-EX 三方一致等门禁全部作用于 spec.md 本体，切片是只读派生物，门禁零改动。
- **预计省多少**：**10–18 万 token/次**（spec 29–77KB × 7–9 读者，切片后单次装载降至 10–30%，压缩率 60–75%）。
- **审计体系等价替代**：切片键与 coverage_matrix 同源，漏切风险与既有「矩阵登记错误」风险同源同大小，由 G-PL-6（矩阵 milestone 列非空）+ G-EX-4（三方计数一致）对冲；codex code_audit 持全文做五维度外审，双通道只降其一；verifier 的 R 切片与现合同语义完全等价。fidelity 损失是概率性漏看略升，非审计通道关闭。

#### B2. assumptions.md 状态分层 + 影响字段门禁（保守派 change 3 + 嫁接单一真相源）

- **改哪个文件**：`templates/audit/assumptions.md`（设「## 活跃假设」与「## 存档区（revised）」两个 H2）；`templates/audit/ambiguities.md`（auto 裁决全文只存 ambiguities，assumptions 条目写「详见 A{n}」引用，消除双边复制漂移）；`tools/check_gates.py`（check_plan 新增机器校验：每条假设「影响 milestone」字段非空且取值 ∈ plan milestones 集合）；spec_slice.py 复用扩展出 assumptions 切片；`stages/{implement,verify,iterate}.md` 与四个 agent 合同。
- **怎么改**：revised 条目由主会话在 revise/iterate 记账时机器迁移到存档区（原文保留，只增不删规则不变）。coder/verifier/diagnoser/oos 合同改为「本 milestone 相关假设条目全文 + 全活跃假设的 ID|一句话摘要索引（约 1–2KB）」，按索引可按需 Read 全文；存档区只给 reporter 与 auditor(mode=result)（final_report 硬约束 6③ 全文收录义务不受影响）。G-FN-4 占位符全文搜索仍扫整个文件。
- **预计省多少**：**5–12 万 token/次**（26–96KB × 6 读者 → 单 agent 实读 5–15KB + 2KB 索引）。
- **审计体系等价替代**：「影响 milestone 字段非空」下沉为 G-PL 机器校验，漏登在 plan 阶段即 FAIL 暴露；每 agent 持全量索引知悉存在性可按需取全文；codex/auditor(code) 外审仍持 assumptions 全量做「未登记简化」核查（该通道不裁剪）；审计追溯原文未删、门禁照扫。

#### B3. src/{id}/ 按角色收窄（保守派 change 6）

- **改哪个文件**：`.claude/agents/{quant-oos-analyst,quant-diagnoser}.md` 输入合同；`stages/iterate.md` 步骤 6（continue 分支 coder prompt 模板）、`stages/oos.md` 步骤 2。
- **怎么改**：三处收窄——(a) oos-analyst 由「src 全部」收窄为「main.py+config.py+strategy.py + 允许 ls 目录后按需增读 import 链文件」；(b) diagnoser 的 src 输入收窄为「最近一轮 diagnosis 列明文件 + 本轮失败指标链相关文件（主会话按 coverage_matrix 实现位置列的文件:函数锚点转述）+ 可按需增读」；(c) iterate 的 continue 轮 coder prompt 明确「只 Read diagnosis 列明的允许改动文件及其直接依赖」。**auditor(mode=code) 与 verifier 保持 src 全量**——前者忠实性逐条核对是本职，后者要跑 main.py 并判 E2 新鲜度范围，两条全量腿刻意保留。
- **预计省多少**：**3–10 万 token/次**（50–150KB × 5–7 次装载砍 30–40%；无 iterate 的 pass 案例取低区）。
- **审计体系等价替代**：三处均带「可按需增读」逃生门；oos 的区间改动正确性由 G-OS-2 区间零重叠机器判定 + 点收 git diff 双重兜底；反虚报与忠实性审计两条全量通道无缺口。

#### B4. comparison.json 确立为指标明细唯一真相源（保守派 change 13）

- **改哪个文件**：`.claude/agents/quant-verifier.md` 输出合同 2/3；`.claude/agents/quant-auditor.md` mode=result 硬约束 8(b)；`.claude/agents/quant-reporter.md`；report_digest.py 复用。
- **怎么改**：verify_report.md 不再全文复制对比表，改为「偏差摘要表（Top-N 超差项 + pass 计数）+ 已知口径差异节 + 实现忠实性抽查节（easy）」，正文写「完整逐指标对比见 results/comparison.json」；auditor(result) 的 E4 三方一致核对对象改为 metrics.json ↔ comparison.json ↔ backtest_summary.xlsx，消除第四份拷贝；reporter 的指标对比总表由 report_digest.py 从 comparison.json 机器生成 markdown 供其原样粘贴（硬约束 5「不重算」下连手工转抄也去掉）。
- **预计省多少**：**3–6 万 token/次**（ssrn verify_report 85.6KB 含全表复制，规模越大省越多）。
- **审计体系等价替代**：少一层 LLM 手工转抄即少一类 K8 转抄错误面（verifier 抄错 comparison 的场景从源头消失）；E4 核对函数不变、对象更直接；对比总表机器生成后「措辞与数据一致」义务由工具保证，比 sonnet reporter 转抄更稳。正反相抵偏正面。

#### B5. auditor(mode=spec) 改切片穷举（保守派 change 9）

- **改哪个文件**：`.claude/agents/quant-auditor.md` mode=spec 输入合同与硬约束 6；`templates/audit/extract_audit.md` C1/C2/C3/C6 执行方式节。
- **怎么改**：report_text.md 只给路径不给全文装载指令，合同明写「禁止一次性 Read 全文」；C6 幻觉抽查（≥10 条）按要素登记页码用 grep/sed 抽取「===== PAGE n =====」页范围核对；C1 编号连续性用 grep -oE 独立重算 fig_max/tbl_max；C3 触发词 grep 命中页清单后逐命中页核对；extract_audit 模板加机器可核断言「PAGE 标记数 == state.pdf_pages」（grep -c 即可），把整页缺失变硬检查。codex 盲提取通道的全文通读保留（双通道不同时降级）。
- **预计省多少**：**3–6 万 token/次**（auditor(spec) 全量读 135.8–253KB → 实读 20–40KB 等值）。
- **审计体系等价替代**：C1/C3/C6 从「人读穷举」变「grep 穷举」，召回不降反升（人读会疲劳漏看，grep 不会）；PAGE 数机器断言兜底整页提取失败；系统性遗漏的最终兜底（codex 盲提取全文）完整保留。代价是文风级语义曲解的捕捉力下降，属概率性非结构性损失。

#### B6. reporter 输入面 digest 化（保守派 change 5）

- **改哪个文件**：`tools/report_digest.py`（进 report 前主会话跑，零 LLM）；`stages/report.md` 步骤 2/3；`.claude/agents/quant-reporter.md` 输入合同 1/3。
- **怎么改**：产 `audit/report_digest.md`——(a) audit_responses 压缩表：rejected/deferred 行全文保留（含技术理由，G-FN-5 与人话列所需），accepted 行压为「ID|severity|一句话摘要|accepted|复核」单行 + 总数统计；(b) evidence_manifest 的 E1–E6 结论行 + 扰动测试结论；(c) 从 state.json 机器抽取 external_reviews/verdict/coverage_stats/reproduction_mode 摘要（替代主会话手工转述）；(d) 从 comparison.json 机器生成指标对比总表。reporter 合同改为 report_digest + assumptions 全量（硬约束 6③ 必须）+ comparison.json + oos 产物 + spec 切片；不再给 matrix/plan/evidence/verify_report 全文与 audit_responses 全表。
- **预计省多少**：reporter 输入面 250–350KB → 120–180KB，**4–7 万 token/次**；叠加主会话免为转述 Read state.json/responses 约 3–5 万，合计 **7–12 万/次**。
- **审计体系等价替代**：digest 是确定性工具生成，无 LLM 转述失真；G-FN-5 核验对象是 final_report vs audit_responses.md **原文**，不经 reporter 上下文，语义不变；accepted 明细在 audit_responses.md 原文与 render_report.py 生成的 HTML 折叠收录中可供人查，审计追溯链完整。rejected 抽取逻辑与 check_gates 的 _parse_audit_responses 共用同一解析函数。

#### B7. iterate 回环增量上下文（保守派 change 4 + 三件嫁接保险丝）

- **改哪个文件**：新增 `tools/iter_digest.py`；`stages/iterate.md` 步骤 3/5；`.claude/agents/quant-diagnoser.md` 输入合同 4；`templates/codex_prompts/second_opinion.md` 占位符语义；`tools/check_gates.py` check_iterate。
- **怎么改**：iter_digest.py（确定性工具）产 `iterations/iter_digest.md`——(a) 全部历史 diagnosis.md 的「## 已排除假设」节机器原文抽取汇总（逐条标注排除轮次与当轮偏差变化，原文抽取非改写）；(b) 指标×轮次 rel_dev 差分表（从各 iter_NN/comparison.json 重算）；(c) 各轮修改点与结论索引行。diagnoser 合同改为 digest + 最近一轮 diagnosis 全文 + 本轮 comparison 快照 + spec/assumptions 切片；更早历史「按需 Read 全文」逃生门保留。iter_NN/comparison 快照改 diff 存储。抽不中任一轮「已排除假设」节时 digest 头部显式告警，主会话见此回退全量投喂该轮。
- **三件嫁接保险丝**：① second_opinion 的 {iteration_history_paths} 改填 digest + 最近一轮路径，但 **codex 第二意见通道保留全量历史阅读权**（其「逐份读已排除假设节」契约不变）——修复保守派原稿把 diagnoser 与 second_opinion 同时收窄、违反「双通道只降其一」的失分点；② **iter≥3 仍未收敛时自动恢复全历史投喂**（此时防兜圈价值 > token），把尾部风险从「索引化漏检可能兜圈」封成「最多多付一轮全量成本」；③ check_gates 新增 `--stage iterate --trend`：同指标连续 2 轮 rel_dev 改善 <10% 即机器预警 stop_partial，比 3 轮红线提前一轮截断 r004 式全损回环——这是原体系不存在的新机器防线，恰好对冲 diagnoser 失去全历史语境后的跨轮模式识别下降。G-IT-1 三件套与 G-IT-3 判定不变。
- **预计省多少**：进入 iterate 的案例 **20–40 万 token**（r004 规模：历史重读 325KB 消化为 5–10KB/轮恒定，每轮省 5–10 万），终态 blocked 时即净止损；墙钟每轮省约 30–60 分钟。
- **审计体系等价替代**：诚实声明——这是全方案 fidelity 妥协最大的一条。防兜圈核心（已排除假设不重提、假设族唯一性、轮次红线）由 digest 原文抽取完整承载，不退化；退化的是 diagnoser 对历史「推理过程语境」的视野。对冲依据：r004 全历史通读 4 轮仍 blocked、rescue 成功率 0%，全历史并未换来收敛；逃生门 + second_opinion 独立通道全量保留 + iter≥3 自适应恢复 + 机器趋势预警四重兜底。**本条最后实施，先灰度验证（见 §4）。**

#### B8. 机器预筛下沉 + 并行落实（保守派 change 12 + 嫁接结构派并行硬模板）

- **改哪个文件**：新增 `tools/static_prescan.py`；`stages/code_audit.md` 步骤 2；`SKILL.md` 五.3 并行规则；`stages/{code_audit,result_audit}.md` 改单消息同批派发模板；`tools/state.py` 记 batch 组成事件。
- **怎么改**：static_prescan.py（code_audit 派发前跑，零 LLM）：(a) 从 spec.md 第五节 R 类要素机抽全部数值字面量，在 src/ 下 grep 命中清单（区分注释/字符串/计算行三种形态）；(b) B 类要素参数值字面量（区间/费率/分组数/调仓频率）与 config.py 字符串级核对。产出 audit/prescan_code.md + 机器生成 {r_class_values_list}（code_audit.md 步骤 2 的手工抄录备料改为一行工具调用）。编排联动：预筛命中「计算行级 K1 候选或 B 类参数不符」时本案例 code_audit∥verify 退化为串行（先审后跑）；未命中则按**嫁接的并行硬模板**落实设计已有但 4/4 案例未执行的并行——同一消息内发起 codex（run_in_background）+ auditor(code) + verifier（medium/hard），result_audit ∥ oos 同款（verdict pass/partial 时），每批 record-event 记 batch 组成，主会话用 Monitor 等完成通知不轮询。easy/ml 维持串行的既有条款不变；G-VF-6 新鲜度断言与 oos 作废规则不变。预筛输出只作编排决策与 codex prompt 备料，不生成 finding（finding 仍是 codex/auditor 专属职权）。
- **预计省多少**：作废性浪费条件性 **5–15 万 token/次** + 主会话备料抄录 1–2 万/次；墙钟每案例 **60–140 分钟**（code_audit∥verify 36–77 分钟 + result_audit∥oos 22–64 分钟，analyst 实测 4 案例合计约 200 分钟 + r001 64 分钟）。
- **审计体系等价替代**：codex 的 K1 审查与 R 类清单一字不减照跑，预筛只是同一信号的机器先验；字符串核对假阳性的代价仅是退化为串行（对齐 easy/ml 既定的更保守路径，方向上是加固）；G-VF-6 mtime 断言保证作废路径不可能拿旧产物蒙混过门。审计覆盖零裁剪。

### 2.3 长期重构（DAG 化，留 v3 再议）

以下三条来自激进派方案，评审一致认为收益/风险不成比例，**本期不做，留待保守派落地后积累实测数据再评估**：

- **C1. 产物 DAG 调度（tools/dag.py）**：以工件为节点声明依赖 DAG，机器做拓扑排序、并行批排、内容 hash 级联失效，STAGE_ORDER 降级为兼容投影。潜在收益：hard 案例 implement 中位 6.1h 压至 3–4h、调度决策不进 LLM 上下文。风险：调度器 bug 乱序/误失效让陈旧产物蒙混过关；需先「STAGE_ORDER 编译为等价 DAG」双跑一个案例逐条比对 gate 输出。
- **C2. spec.md → elements.jsonl 结构化记录 + materialize.py 物化视图**：spec 从单一 markdown 改结构化记录，切片合同由物化视图渲染，check_gates 改读 jsonl。潜在收益：解析更硬、消除 markdown 表格解析脆弱性。风险：jsonl schema/解析器 bug 系统性漏要素 + 历史案例迁移。
- **C3. state.json 事件/门禁 JSONL 化 + 主会话搬运清零**：events/gates 改 append-only JSONL，codex prompt 占位符填充/SPEC_CODEX 切分/标量注入全部机器渲染。潜在收益：主会话 10–15 万 token/次。风险：check_gates 读取路径改造回归面大。

启动评估的前置条件：保守派三批全部落地、停滞哨兵与预筛跑出至少 2 个新案例的对照数据（token/墙钟/漏检率），届时用实测而非估算决定 DAG 是否值得上。

---

## 三、明确不做什么

以下各点经双评审明确否决或本方案主动排除，逐条注明理由与所保护的机制。**总原则：六条硬规则、十二阶段状态机、8 agent 划分、G-XX 门禁判定出口、K1–K8 防偷懒审计体系、codex 三审查点与盲提取，全部不动。**

| # | 不做的事 | 理由（保护的机制） |
|---|---------|-------------------|
| 1 | 不合并 spec_audit 双通道（codex 盲提取 + auditor 内审）为单通道 | §9.2 刻意冗余，专为暴露系统性遗漏与锚定效应；盲提取对 report_text 的全文通读保留，auditor(spec) 切片化后双通道仍保一条全量腿 |
| 2 | 不裁 code_audit 独立于 verify 运行、不取消 ml 标签必跑 auditor(code) | 未来函数/训练泄漏使指标「偏好」而非偏差，数值验证（verify）抓不到，属 verify 无法替代的刻意冗余（§3 裁剪矩阵补充规则） |
| 3 | 不裁 result_audit 外审、不合并 evidence 采集与审计 | 「证据采集 vs 证据审计」分离是 §9.5 刻意冗余；G-RA 按 standards.json 逐条重算 rel_dev、不信任 comparison.json 自述 pass 字段的逻辑一行不动 |
| 4 | 不裁 K1 扰动测试、不把 K8 文件改动核验降级 | K1 是硬编码检测杀手锏（计算开销换真实性）；K8 mtime+diff 核验是 IO 开销换防假修复；static_prescan 的机器 grep 只是新增前置层，codex/auditor 的 K1 语义审查照跑 |
| 5 | **不把 auditor(mode=result) 的 PNG 逐张 Read 降为机器判定+抽查** | 保真守门评审的决定性理由：quant-auditor.md 硬约束 8a「每张 PNG 已用 Read 实际查看」是 K3 视觉主判定；机器能判空白/占位图，判不了曲线标签张冠李戴这类语义错误，E4 数值重算只能部分兜底。结构派 change 5 与激进派 change 13 的此条被否决（代价仅 1–2 万 token/次，不值得动） |
| 6 | **不把 auditor(mode=code) 按锚点切片、不裁 verifier 的 src 全量读** | 内审是忠实性审计第一道防线，锚点化使其变薄、跨文件未来函数泄漏漏检率上升（激进派自评「概率非零」）；两条全量腿（auditor code + verifier）与 codex 外审全量共同构成 src 语义审查纵深，只收窄 oos/diagnoser/iterate-coder 三处 |
| 7 | **本期不做 verifier 迭代轮「失败指标子集重跑」** | 无出口轮全量锚点的子集重跑会产生拼盘 comparison、掩盖交叉回归（激进派 change 5 被点名）。若未来采纳，必须以「出口轮强制全量重跑 main.py + G-VF 全量重算」为锚点，且先用 r004 历史轮次回放验证 |
| 8 | 不做 extract+plan 合并蒸馏（economy 档也不开放） | 评审一号：「在代码里埋一把上膛的枪」。planner 只读 spec 的隔离纪律是倒逼 spec 完备的软强制，合并后 spec 缺口被规划静默代偿、in-passing 检查失效——用结构性保真换 token，评审不接受 |
| 9 | 本期不做 spec.md→jsonl 迁移、不做 DAG 主循环替换、不做 PreToolUse 全 hook 化（仅保留 A1 的禁读护栏单点） | 激进派的系统性爆炸半径：对一条已验证管线是数量级的实施风险差，收益只比保守派高 10–30%，收益/风险不成比例。留 v3 用实测数据再决策（见 §2.3） |
| 10 | 不删 events/gates 历史、不改任何 G-XX 门禁判定语义 | state.json 只归档不删除（events.log 可查）；check_gates 按 standards.json 重算的全部逻辑零改动；G-VF-6 新鲜度断言、G-FN-5 rejected 原样收录等防作弊兜底全部保留 |
| 11 | 不动 economy 降配规则、不动 /goal 终态措辞纪律 | 「planner/coder/auditor/diagnoser 恒 opus」是核心质量底线；「到达四个终态之一即停」的措辞纪律是防驱动层冲撞人工闸门，属运行时长换正确性 |
| 12 | 不做「diagnoser 与 second_opinion 同时收窄」 | 违反本方案自定的「双通道只降其一」原则；B7 已按评审嫁接修复——codex 第二意见保留全量历史阅读权 |

---

## 四、实施顺序与验证方式

### 4.1 分批实施

| 批次 | 内容 | 性质 | 时间窗 |
|------|------|------|--------|
| 第一批 | A1（禁读红线 + guard.py）、A2（停滞哨兵 + 埋点 + codex 后台化）、A3（append-review + events 归档）、A4（PDF 撞库缓存）、A5（G-FN 预检） | 纯文字红线 + 工具新增，零合同结构变更，几乎不可能把跑通案例弄坏 | 当周 |
| 第二批 | B6（report_digest.py）、B8（static_prescan.py + 并行硬模板）、B4（comparison 唯一真相源） | digest 与预筛工具，须与 check_gates 共用解析函数 | 第一批稳定后 |
| 第三批 | B1（spec 切片 + refs 闭包 + manifest）、B2（assumptions 分层 + 影响字段门禁）、B3（src 收窄）、B5（auditor spec 切片穷举） | 切片分发，须先跑通 spec_slice.py 与矩阵联动校验 | 第二批验证后 |
| 第四批 | B7（iterate digest + 三件保险丝） | fidelity 妥协最大项，灰度制 | 最后，见 §4.3 |

工具一致性纪律：spec_slice.py / report_digest.py / static_prescan.py / iter_digest.py 的解析函数全部复用 check_gates 既有实现（标题块正则、load_matrix_rows、_parse_audit_responses），禁止第二套口径；state.py 改动后跑 validate_state 全量校验，旧案例迁移走既有 migrate 先例。

### 4.2 token 计量基线（先建尺子再谈优化）

在每批落地前先补计量：主会话每次派发子 agent 时把输入面文件清单（路径 × 字节数）以 record-event 落盘，events 即成为 token 消耗的代理账本（按 3B/token 折算）；墙钟侧用 A2 的子步骤埋点（codex_start/end、auditor_mN_start/end、verify_run_start/end）消除「黑盒只能靠跨案例对照推断」的观测缺口。没有这把尺，§4.3 的回归对比无从谈起。

### 4.3 回归验证设计

1. **双案例回归对照**：选 r003（最干净 pass，12.18h，无 iterate）与 r004（iterate 4 轮 blocked + result_audit failed 全损路径）两个已完成案例做同 PDF 重跑——同 PDF 撞库缓存（A4）保证 report_text 位级一致，变量只剩本方案改动。
2. **比对指标**：
   - verdict 一致性（r003 须仍 pass；r004 允许 stop_partial 提前止损，但不允许假 pass）；
   - codex/auditor findings 数不显著下降（漏检率代理指标）；
   - spec_audit 漏要素率不升（盲提取 diff 比对）；
   - G-FN 一次通过率不降；
   - token 消耗（§4.2 账本）与墙钟对比基线。
3. **B7 灰度制**：先在下一个进入 iterate 的案例以「digest + 全量历史并行投喂」灰度一轮，对比 diagnoser 诊断质量（是否重提已排除假设、归因是否命中、结论三分支是否一致），无退化再切默认为 digest-only；灰度轮的双重投喂成本一次性，可接受。
4. **切片漏切演练**：B1/B2 上线前用 r006（spec 77.4KB，要素最多）与 ssrn（assumptions 95.8KB）离线跑 spec_slice.py，人工抽查每个 milestone 切片的要素完备性 + refs 闭包命中率，作为工具级单测。
5. **推广门槛**：回归双案例全部通过 §4.3.2 指标，方准从 pilot 推广为默认路径；任一指标劣化，该批次整体回退（每批改动独立可回退，合同文字与工具新增互不累加状态）。

### 4.4 预期总收益（与 analyst 量化证据对齐）

| 维度 | 构成 | 量级 |
|------|------|------|
| token（pass 路径主线） | A1 report_text 守界 15–30 万 + B1 spec 切片 10–18 万 + B2 assumptions 5–12 万 + B6 reporter digest 7–12 万 + B3 src 3–10 万 + A3 state 通道 3–6 万 + B5 auditor(spec) 3–6 万 + B4 comparison 去重 3–6 万 | **50–90 万/次** |
| token（失败路径追加） | B7 iterate digest（r004 规模） | **20–40 万/次**，且为 blocked 时的净止损 |
| token（条件性） | B8 并行作废避免 5–15 万 + A4 同 PDF 重跑 10–15 万 | 按发生概率兑现 |
| 墙钟 | A2 停滞哨兵截断停滞（单案例 10–100h 级）+ B8 并行落实 60–140 分钟/案例 + B7 iterate 每轮 30–60 分钟 + A4 撞库 0.3–10.6h | pass 案例忙时 12.2–57.9h 有望压至约 8–15h 区间 |
| 完成率 | 停滞未发现（r007/style/r002）、iterate 全损（r004）、案例级重做（r005→r006）三大死因分别被 A2、B7+趋势预警、A4 正面命中 | 目标：完成率从 33% 显著抬升 |

**诚实总账**：全方案唯一零代价项是 A2 停滞哨兵（纯观测）；最大妥协项是 B7 iterate digest（diagnoser 失去历史推理语境，已配原文抽取 digest + 逃生门 + second_opinion 全量保留 + iter≥3 自适应恢复 + 机器趋势预警五重对冲）；其余切片类改动把「全量读」降为「默认索引 + 按需取」，能力未被剥夺，fidelity 损失是概率性漏看略升而非审计通道关闭，且有 G-EX/G-PL 交叉门禁与 codex 异构通道双层兜底。结构派的 DAG 与激进派的 jsonl 化留 v3——等停滞哨兵和预筛跑出新案例对照数据后，用实测而非估算决定是否再上。
