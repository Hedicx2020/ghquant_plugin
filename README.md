# 研报复现系统（report_reproduce）

给定一份量化研报 PDF，按报告类型与难度自动分诊、复现策略代码与回测结果，产出与原文逐项对照、附可信度评级的最终报告。

在线手册（外部可直接访问）：**https://hedicx2020.github.io/ghquant_plugin/docs/plugin-overview.html**

本仓库同时是一个 **Claude Code 插件**（`quant-report-reproduce`）：既可以克隆后在仓库内直接使用（形态 A，维护者模式），也可以作为插件安装后在任意自己的目录中使用（形态 B，见下节）。

## 作为插件安装（推荐给其他使用者）

```bash
# 在 Claude Code 中：第一步注册插件源，第二步安装（缺一不可）
/plugin marketplace add https://github.com/Hedicx2020/ghquant_plugin
/plugin install quant-report-reproduce@hedi-quant
```

**首次使用（三步）**：

1. 进入你自己的工作目录（任意空目录即可），运行 `/reproduce setup`——向导会问五项配置：
   - **数据路径**：本地 parquet 数据根目录（默认 `~/local_data`）
   - **执行模式**：`auto` 全自动优先（推荐，歧义自动假设并登记、事后可定向重跑）/ `interactive` 遇关键歧义暂停人工裁决
   - **最大迭代次数**：按难度自动（easy 3 / medium 5 / hard 6）或自定义 1-10
   - **回测框架**：默认使用内置 `common/` 回测库；也可指定你自有回测框架的目录路径——复现代码的回测执行层将优先调用你的框架，内置库仅补缺口
   - **偏差容忍**：你能接受的复现值与原报告的偏差。默认按 `templates/standards.json` 分类型精细容差（年化/夏普等 5%、因子 IC 近零走绝对偏差等）；也可自定义统一百分比（如 10%）——所有相对偏差判定随之放宽或收紧，达标判定与最终报告一致生效
   - **经济模式**：开启后机械性角色（提取/验证/样本外）派发降为 sonnet，token 消耗约降三成；质量敏感角色（写码/审计/归因）保持 opus。另有配置文件项 `audit_level`（strict 默认 / standard 外审触发式）进一步控成本，见手册
   随后 setup 自动落地：`.reproduce.json` 配置、`templates/`（含数据目录模板与达标标准）、`common/`（公共回测库）、`pyproject.toml`、目录树，并检测 uv / Python 依赖 / codex CLI。
2. **维护 `templates/data_catalog.md`**：按你数据目录的实际内容登记数据清单——分诊阶段判断「研报所需数据是否可得」完全依据此文件。
3. 把研报 PDF 放进 `reports/`，运行 `/reproduce reports/xxx.pdf` 起跑。

**环境要求**：
- [uv](https://docs.astral.sh/uv/)（硬前置，所有工具经 `uv run` 调用）；依赖缺失时在工作目录 `uv sync`
- Claude 订阅档位：子 agent 主力为 opus（7 个中 6 个），建议 Max 档位；可自行编辑安装副本中 `agents/*.md` 的 model 字段下调（复现质量自负）
- codex CLI（软前置）：外部三审查点用；**未安装或额度耗尽都不断链**——自动降级为 Claude 替身盲审（同一审查 prompt、独立上下文、意见照样逐条回应闭环），替身也不可行才标记跳过；发生任一失败性降级时最终报告如实标注、可信度评级封顶 B。装好 codex / 额度恢复后无需重新配置，下次运行自动启用

## 快速开始（两种形态通用）

```bash
/reproduce setup                          # 首次使用配置向导（形态 A 本仓库直跑可跳过）
/reproduce reports/test.pdf --mode auto   # 新起一份复现（自动分配案例编号 rNNN_<slug>）
/reproduce reports/us_paper.pdf --experimental   # 实验模式：海外报告市场迁移复现（等价数据替代，数值判定豁免）
/reproduce status                         # 全部案例一览表（编号 | id | 类型/难度 | 状态 | 阶段）
/reproduce continue r3                    # 编号缩写即可续跑（r3 / r003 / 3 都指向 r003_xxx）
```

**案例统一编号**：新案例自动分配 `rNNN_<slug>` 形式的 report_id（三位顺序号 + 语义短名，如 `r001_style_factor`），起跑时终端会明示编号；所有子命令（`continue` / `status` / `revise` / `accept`）都接受编号缩写或唯一前缀，忘了 id 就跑一次无参 `/reproduce status`。`--id` 仍可显式指定覆盖。

## 目录导航

| 路径 | 内容 |
|------|------|
| `.claude-plugin/plugin.json` | 插件清单 |
| `docs/specs/2026-07-07-reproduce-v2-design.md` | v2 完整设计文档（状态机 / 门禁 / agent 契约 / 防偷懒审计体系） |
| `docs/specs/2026-07-09-plugin-packaging-design.md` | 插件化设计（双形态 / 路径解耦 / setup 向导） |
| `CLAUDE.md` | 编码与产出格式落地约定（命名 / Excel / 图表 / common 复用 / 数据对齐） |
| `skills/reproduce/` | `/reproduce` 主编排 SKILL.md + stage 执行卡（`.claude/skills/` 为回指 symlink） |
| `agents/` | 8 个子 agent 定义（`.claude/agents` 为回指 symlink） |
| `templates/` | 分诊、类型、审计模板 + `standards.json` 达标标准（插件形态下作为种子拷贝到用户目录） |
| `common/` | 公共回测库（同上，种子） |
| `tools/` | `state.py`（状态写入口）/ `check_gates.py`（门禁判定）/ `pdf_extract.py`（PDF 转文本）/ `setup_workspace.py`（首次配置落地） |
| `reports/{id}.pdf` | PDF 收件箱 |
| `workspace/{id}/` | 每份报告的管线文书（spec / plan / audit / iterations / final_report） |
| `src/{id}/`、`output/{id}/` | 策略代码与回测结果 |
| `docs/legacy/` | 已退役旧命令 / 旧 agent 的存档备份 |

> 形态 B（插件安装）下，`templates/ common/ reports/ workspace/ src/ output/` 全部位于**用户自己的工作目录**（setup 生成），插件安装目录只读；工具通过 `REPORT_REPRODUCE_ROOT` 环境变量把产物根定向到用户目录。

**维护者分发说明**：`.claude-plugin/marketplace.json` 是分发硬前置（单插件仓库亦然）。正式分发一律用 **git URL**（marketplace add 只取 git 跟踪内容）；`marketplace add <本地路径>` 会全量拷贝目录（含 `.venv`/`output` 等 gitignore 内容，实测 400M+），仅限维护者自测。已实测结论：skill 正文不替换 `${CLAUDE_PLUGIN_ROOT}`、Bash 也不注入该环境变量——工具定位依赖 SKILL.md 协议第 0 级（skill base directory 上两级），勿在 skill/stages 中引入对该变量的新依赖。

## 已归档案例

`test`（新流程验收用例）、`momentum_factor`、`long_term_momentum` 三案例已用 `--legacy` 归档，详见对应 `workspace/{id}/state.json`。

## 变更记录

- 2026-07-11（v2.10.0）：案例统一编号——新案例 report_id 自动编号为 `rNNN_<slug>`（`state.py next-id` 分配，接现存最大编号；slug 取 PDF 文件名或研报标题的英文短名，保证看名知义）；全部子命令接受编号缩写（`r3`/`r003`/`3`）与唯一前缀（`state.py resolve` 解析，歧义时列候选）；无参 `status` 输出按编号排序的案例一览表。既有案例不迁移（旧式 id 照常可用、可前缀缩写）；`--id` 显式指定不强加编号。
- 2026-07-11（v2.9.0）：codex 备用方案补强——外审降级链细化为可执行协议（正本收口在 spec_audit 执行卡）：① 调用前 `command -v codex` 速判，未安装零成本直降、会话内沿用不反复探测；② 失败特征分类：额度/认证类错误（usage limit/quota/429/401）跳过无意义的缩减重试直接降级；③ 一级降级 Claude 替身盲审规范化（general-purpose 执行同一份已填充审查 prompt、禁读过程性文件、直接写原输出路径、不受经济模式降配），二级才 skipped；④ result 审查点（反虚报最后防线）必须先试替身、不得直接 skipped；⑤ iterate 第二意见同链降级（替身独立上下文保留防兜圈价值）；⑥ verifier 辅助自查失败即跳过不替代；⑦ 评级口径统一：失败性降级/缺失（claude_fallback 或 skipped）不分难度封顶 B，audit_level=standard 未触发的配置性 skipped 不封顶。门禁只核产物文件与格式、不核 engine 字段，全链零代码变更。
- 2026-07-11（v2.8.0）：实验模式（市场迁移复现）——`/reproduce reports/xxx.pdf --experimental`：海外报告原文市场数据本地不可得时，用本地等价数据替代（如美国 CPI → 中国 CPI），复现目标从「数值对齐原文」变为「方法在迁移市场是否成立」。数值对齐判定整体豁免（G-VF-3 只核产出完整、G-RA-3 无超差归因语义、iterate 天然跳过），替代数据逐条入假设登记簿（market-transplant），最终报告与 HTML 结果页强制显著声明（G-FN 核验「市场迁移」章节、结果页顶部醒目 banner）；反虚报照审（数字仍不能编）。strict 模式下 planner 发现整体不可得只能建议、经人工闸门裁决切换，agent 无权自行切换。

- 2026-07-11（v2.7.0）：墙钟加速——① implement 流水线化：milestone 验证与下一 milestone 编码滚动重叠（medium 从完全串行改为流水线，hard 依赖链同享；含汇合分诊表：假 FAIL 复跑不占重派、下游缓验+增量适配、尾部条件封堵协议洞）；② code_audit∥verify 默认并行（easy/ml 例外，G-VF-6 新鲜度机器兜底作废规则）；③ result_audit∥oos 可选并发；④ milestone 拆分粒度收紧（hard 3~5 为宜、<100 行相邻同主题合并）；⑤ 并行纪律入硬约束（state.py 写命令严禁同批并行、同批 agent 写集不相交——顺带修复既有 hard 路径丢更新隐患）；⑥ iterate 卡 join codex 歧义修正。预期 medium 每跑省 25-55 分钟、hard 省 40-110+ 分钟；纯文案层，门禁与审计体系零变更。

- 2026-07-10（v2.6.0）：四项修订——① 分诊判据修正：方法复杂度为主轴（训练/优化/多资产联动才 hard），删除 milestone 数维度（循环论证），已降级支线的数据缺失不再抬难度，「工作量大 ≠ 技术难」；② 经济模式 `economy`：机械性角色（extractor/verifier/oos-analyst）派发降 sonnet，质量敏感角色保持 opus；③ 外审档位 `audit_level: strict|standard`：standard 时 spec/code 外审触发式（skipped 明示落档保持门禁兼容），result 外审任何档位必跑；④ 核验分级 `verification_level`：研报参数不明的指标经 diagnoser 裁定可降级为方向/量级/不可核验（必须锚定 assumption_linked 防作弊，报告分层展示）。reporter 输入合同瘦身（总表替代全量原文）。

- 2026-07-10：新增复现结果单文件 HTML 展示页——report 阶段由 `tools/render_report.py` 确定性渲染 `output/{id}/final_report.html`（指标对比总表可筛选、图表 base64 内嵌自包含、样本外/审计台账/假设登记簿与报告全文折叠收录，浏览器直接打开可分享）；G-FN-7 门禁核验；5 个渲染器单测。

- 2026-07-10：修复 setup 执行卡——五项配置问卷分两批收集（AskUserQuestion 工具单次上限 4 问，原「一次问卷收齐」在实际运行中触发 InputValidationError）。

- 2026-07-09：新增 oos 阶段与 quant-oos-analyst agent——复现达标（pass/partial）后自动把策略原样延伸到研报回测区间之后的数据，评估效应延续/衰减/失效/样本不足；出口门禁 G-OS（区间零重叠防样本内冒充、结论枚举、短样本警示、净值延伸图），final_report 相应必含「样本外表现」章节（G-FN 动态核验）。STAGE_ORDER 变为十二阶段，旧案例经 `state.py migrate` 补键（oos=skipped）。

- 2026-07-09：setup 配置第五项——`default_max_rel_dev`（可接受的与原报告的偏差，0.005-0.5 小数；留空按 standards.json 分类型精细容差）。check_gates 的 load_standards 自动读取并统一替换所有相对偏差上限（绝对偏差/同号/量级/定性语义不变），G-VF-3/G-RA-3 与 verifier 对数口径一致生效；6 个新测试。
- 2026-07-09：setup 配置第四项——`backtest_framework`（用户自有回测框架目录，setup 校验存在性，写入 .reproduce.json）；plan/implement 派发合同据此优先复用用户框架、内置 `common/` 仅补缺口，未指定时行为不变。公开分发仓库快照剔除 reports/test.pdf（研报原文不对外）。
- 2026-07-09：内部修复——check_gates 的 G-VF-6 新鲜度检查两侧排除 `__pycache__`/`*.pyc` 派生物（重放 G-IM 的 compileall 或 results 内脚本旧字节码缓存会造成误判），附四个正反测试；不影响使用方式。
- 2026-07-09：插件化（v2.1）——新增 `.claude-plugin/plugin.json`、`/reproduce setup` 配置向导（`tools/setup_workspace.py`，数据路径 / 执行模式 / 最大迭代三项 + 种子拷贝 + 环境检测）；skills/agents 迁至仓库根级（`.claude/` 下以 symlink 回指）；工具调用统一 `REPORT_REPRODUCE_ROOT` 前缀与 `$REPRODUCE_TOOLS` 定位协议（双形态兼容，本仓库直跑行为不变）；`common/data_loader.py` 数据根改读 `.reproduce.json`（缺省回退 `~/local_data`）；status 呈现约定中文化。设计见 `docs/specs/2026-07-09-plugin-packaging-design.md`。
- 2026-07-08：内部修复——收紧 check_gates 的 G-IT 豁免正则（防结论行同行提及 stop_partial 被误判豁免），附正反测试；不影响使用方式。
- 2026-07-08：内部修复——check_gates 的 codex 输出解析器支持裸 JSON（prompt 契约允许的合法格式，端到端验收中发现只认 fenced 块的缺口）；不影响使用方式。
