# 研报复现系统插件化设计（v2.1）

> 立项：2026-07-09，用户指令「把项目做成一个插件，其他用户可以直接调用；用户初次使用要配置数据路径、是否自动执行（或人工参与执行）、最大迭代次数」。
> 前置：v2 十一阶段门禁状态机已交付（见 `2026-07-07-reproduce-v2-design.md`），test_v2 端到端验收进行中。
> 实施闸门：涉及在跑流程的核心文件（`.claude/skills/reproduce/`、`tools/`）的修改，一律等 test_v2 验收 G-FN 门禁通过后动手。

> **2026-07-14 增补**：v2.12.0 已把分发目标扩展为 Claude Code / Codex 双宿主。本文件保留 v2.1 的历史决策；双宿主清单、运行时宿主识别、对称异构外审、Codex agent 生成与新旧产物兼容，以 `2026-07-14-claude-codex-dual-host-design.md` 为准。

## 一、目标与用户故事

- **分发目标**：任何 Claude Code 用户安装本插件后，在自己的任意项目目录内敲 `/reproduce`，即可获得完整的研报复现流水线（11 阶段状态机 + 7 子 agent + codex 三审查点 + 门禁工具链）。
- **用户故事**：
  1. 新用户 `claude plugin install`（或 marketplace add）安装插件；
  2. 在自己的工作目录首次运行 `/reproduce setup`，向导式配置三项：**数据路径**（parquet 本地库位置）、**执行模式**（auto 全自动 / interactive 人工参与）、**最大迭代次数**（默认按难度矩阵 3/5/6，可全局覆盖）；
  3. setup 落地工作目录骨架（templates 种子、common 种子、pyproject、.reproduce.json、目录树），检测依赖与 codex CLI；
  4. 之后 `/reproduce reports/xxx.pdf` 正常起跑，产物全部落在用户自己的目录，git 自管。
- **非目标**：不做多用户共享服务、不做远程数据源适配（数据仍是用户本地 parquet + data_catalog.md 自述）。

## 二、形态决策：仓库根即插件根，双形态兼容

**决策：本仓库整体即插件**（`.claude-plugin/plugin.json` 放仓库根），不拆独立插件仓库。

理由：
1. `tools/`、`templates/` 原位不动，插件根 = 仓库根，`${CLAUDE_PLUGIN_ROOT}` 直接指向它们的父目录，路径改造量最小。
2. Hedi 本仓库的既有工作流（cwd = 仓库根直跑）零破坏：所有路径解耦机制都设计为「本仓库直跑时行为不变」（见 §六）。
3. 分发即 git 仓库本身：其他用户 marketplace add 这个 repo 即可，无需维护第二份拷贝。

**双形态定义**：
- **形态 A（本仓库直跑，Hedi 现状）**：cwd = 仓库根 = 插件资产所在地，workspace/src/output 也在此仓库。
- **形态 B（插件安装，其他用户）**：插件资产在 Claude Code 插件安装目录；cwd = 用户自己的项目目录，workspace/src/output/templates/common 都在用户目录（setup 生成）。

## 三、插件目录结构

```
report_reproduce/                    # 仓库根 = 插件根
├── .claude-plugin/
│   └── plugin.json                  # 插件清单（name/description/version/author）
├── skills/
│   └── reproduce/                   # 单一事实源（从 .claude/skills/reproduce 迁移）
│       ├── SKILL.md
│       └── stages/*.md              # 12 张执行卡（11 阶段 + 新增 setup）
├── agents/                          # 单一事实源（从 .claude/agents 迁移）
│   └── quant-*.md                   # 7 个
├── tools/                           # 原位；管线工具（state/check_gates/pdf_extract + 新增 setup_workspace.py）
├── templates/                       # 原位；作为形态 B 的种子（setup 拷贝到用户目录）
├── common/                          # 原位；作为形态 B 的种子（setup 拷贝到用户目录）
├── .claude/
│   ├── skills/reproduce -> ../../skills/reproduce    # symlink，保持形态 A 项目级加载
│   └── agents -> ../agents                            # symlink（或逐文件 symlink）
├── docs/ tests/ reports/ workspace/ src/ output/      # 形态 A 的工作区与文档（插件消费者不使用）
└── pyproject.toml                   # 形态 A 的依赖；也是形态 B pyproject 种子的来源
```

- **单一事实源**：skills/agents 正本放根级（插件加载位置），`.claude/` 下用 symlink 指回，形态 A 的项目级加载不受影响。git 提交 symlink（macOS/Linux 原生支持；Windows 用户如有需要再议题化）。
- 插件打包不含 workspace/src/output/reports 实数据（插件安装机制只按仓库分发，消费者不会向插件目录写产物；README 说明这些目录是维护者的验收工作区）。

## 四、首次使用流程：`/reproduce setup`（新子命令）

SKILL.md 路由新增 `setup` 分支，配对执行卡 `stages/setup.md`。流程：

1. **已初始化检测**：cwd 存在 `.reproduce.json` → 打印现有配置，询问是否重新配置（AskUserQuestion），否则直接退出。
2. **五项配置（AskUserQuestion 一次问卷）**：
   - **数据路径 data_root**：默认 `~/local_data`；说明「parquet 本地数据库根目录，data_catalog.md 描述的数据都应位于此」。
   - **执行模式 default_mode**：`auto`（推荐，全自动优先：blocking 歧义按最合理假设放行并标记 major-auto，事后可 revise）/ `interactive`（遇 blocking 歧义暂停，人工裁决后继续）。
   - **最大迭代次数 default_max_iter**：`按难度自动`（推荐，easy 3 / medium 5 / hard 6）/ 自定义整数（1-10，全局覆盖难度矩阵）。
   - **回测框架 backtest_framework**（2026-07-09 增补）：默认内置 `common/`；可指定用户自有框架目录，复现代码优先复用之。
   - **偏差容忍 default_max_rel_dev**（2026-07-09 增补）：默认按 standards.json；可自定义统一相对偏差容忍度（0.005-0.5）。
3. **落地骨架（`tools/setup_workspace.py` 一条命令完成，幂等）**：
   - 生成 `.reproduce.json`（见 §五）；
   - 拷贝种子：`templates/` 全量（含 data_catalog.md 模板与五类型模板、standards.json、audit 模板、codex prompts）、`common/`（utils/backtest/data_loader/timing_backtest 等）；
   - 生成 `pyproject.toml`（若 cwd 无）：项目名 + §七依赖清单；
   - 建目录树：`reports/ workspace/ src/ output/`（含 .gitkeep）；
   - 生成 `.gitignore` 建议段（output 图表可选忽略等，仅提示不强写）。
4. **环境检测（只报告不阻塞）**：
   - `uv --version`（无则给安装指引）；
   - `uv run python -c "import pandas, pdfplumber, ..."` 逐包检测，缺失则打印 `uv sync` / `uv add` 指引；
   - `command -v codex`：无 codex CLI 时明示影响——三审查点将走已有两级降级（claude_fallback → skipped），最终报告可信度封顶 B；装了则提示确保 `codex exec` 可非交互运行。
5. **data_catalog 引导**：提示用户维护 `templates/data_catalog.md`（分诊可行性唯一判定依据）；可选提供「自动扫描草稿」：扫 data_root 下 parquet 文件名+列名生成目录草稿，供用户核对补充（列为增量功能，首版可只给模板+说明）。
6. **收尾打印**：快速开始三条命令 + 配置文件位置 + 修改配置的方法（重跑 setup 或直接编辑 .reproduce.json）。

## 五、配置文件 `.reproduce.json`（用户项目根）

```json
{
  "data_root": "~/local_data",
  "default_mode": "auto",
  "default_max_iter": null,
  "backtest_framework": null,
  "default_max_rel_dev": null,
  "plugin_root": "/Users/xxx/.claude/plugins/.../report_reproduce",
  "created_at": "2026-07-09T12:00:00+08:00",
  "config_version": 1
}
```

| 字段 | 含义 | 消费点 |
|------|------|--------|
| `data_root` | 本地 parquet 数据根 | `common/data_loader.py`（替换硬编码 `Path.home()/"local_data"`：改为模块级函数 `get_data_root()`，优先读 cwd 向上就近的 `.reproduce.json`，缺省回退 `~/local_data` 保持形态 A 行为不变） |
| `default_mode` | auto / interactive | SKILL.md init 分支：`--mode` 未显式给时取此值写入 state.json（消费机制沿用现状：mode 已存 state，歧义处理按 mode 分流） |
| `default_max_iter` | null=按难度矩阵；整数=全局覆盖 | SKILL.md init 分支：`--max-iter` 未显式给时取此值；null 则维持难度矩阵 3/5/6（plan 阶段按分诊难度回填） |
| `backtest_framework` | null=内置 `common/`；路径=用户自有回测框架目录（setup 校验存在性） | plan / implement 执行卡：非空时写入 planner 复用规划与 coder 合同——回测执行层优先调用用户框架（src 内 sys.path/包名接入），`common/` 仅补缺口；产物合同与门禁不变 |
| `default_max_rel_dev` | null=按 standards.json 分类型精细容差；0.005-0.5 小数=用户统一偏差容忍 | `check_gates.load_standards` 自动读取，深拷贝后统一替换全部含 `max_rel_dev` 键的容差（abs_eps/同号/量级/定性不动）→ G-VF-3 / G-RA-3 一致生效；verify 执行卡同步 verifier 的 comparison.json pass 口径 |
| `plugin_root` | 插件安装路径 | 工具调用路径的三级兜底之三（见 §六）；setup 写入时取 `${CLAUDE_PLUGIN_ROOT}` 实际值 |
| `config_version` | 配置 schema 版本 | 未来迁移用 |

原则：`.reproduce.json` 只存**默认值**，命令行参数永远优先；配置一律不进插件目录（插件目录只读）。

## 六、路径解耦（三个机制）

### 6.1 工具 root 重定向：`REPORT_REPRODUCE_ROOT` 环境变量（已有钩子，零新代码）

`tools/state.py::default_root()` 现即「工具文件所在目录上一级，支持 `REPORT_REPRODUCE_ROOT` 覆盖」。形态 B 下工具文件在插件目录，推导会错指——解法：**SKILL.md 所有工具命令统一加环境变量前缀**：

```bash
REPORT_REPRODUCE_ROOT="$PWD" uv run python "$REPRODUCE_TOOLS/state.py" ...
```

形态 A 时 `$PWD` 与推导结果相同（无害），形态 B 时纠正指向用户项目。check_gates.py 经 `st.default_root()` 同一入口，自动生效。

### 6.2 工具文件定位：skill base directory 首选 + Bash 双兜底（2026-07-09 真实安装实测后修订）

**实测结论（headless 插件会话两连测）**：skill 正文中 `${CLAUDE_PLUGIN_ROOT}` **不做**文本替换（字面量原样进上下文）；Bash 工具环境中 `CLAUDE_PLUGIN_ROOT` 环境变量**未注入**。原设计的一级兜底整体失效。但 skill 加载时系统提示注入的 *Base directory for this skill*（实测两形态均指向实际加载位置的 `<根>/skills/reproduce`）是始终可靠的锚点。

修订后的定位协议（SKILL.md「二、工具与路径」）：

- **第 0 级（首选）**：skill base directory 上两级 = 插件根/仓库根，`REPRODUCE_TOOLS=<根>/tools`。编排者直接从 skill 加载信息读取，无需探测；`setup` 首跑（cwd 尚无任何落地物）也由此定位 `setup_workspace.py`，解决鸡生蛋。
- **Bash 兜底 1**：`[ -f tools/state.py ]` → 形态 A cwd。
- **Bash 兜底 2**：`.reproduce.json.plugin_root`（setup 落地后可用）。

`REPORT_REPRODUCE_ROOT="$PWD"` 前缀协议（6.1）不变，实测有效（V3 通过）。

### 6.3 资产种子化：templates/ 与 common/ 拷贝到用户项目

- **为什么拷贝而不是引用插件目录**：`templates/data_catalog.md` 描述的是**用户自己的数据**，必须用户侧可编辑；`standards.json` 容差、类型模板同理属于用户可调项；`common/` 是策略代码 import 的运行时依赖（`from common.utils import ...` 相对用户项目解析），且 coder 会按类型扩展它。
- 工具链读 templates 的现有逻辑 `root/templates/...` 在 6.1 生效后自动指向用户项目拷贝，零代码改动。
- 种子更新策略：插件升级不自动覆盖用户侧 templates/common（用户可能已定制）；`setup` 重跑时对已存在文件跳过并列出「插件侧较新」清单，由用户决定是否手动同步。

## 七、依赖与外部工具

- **Python 依赖**（setup 生成/校验用户项目 pyproject.toml）：pandas≥2.0、numpy≥1.24、scipy≥1.10、matplotlib≥3.7、seaborn≥0.12、openpyxl≥3.1、pyarrow≥14.0、pypdf≥4.0、pdfplumber≥0.11、pyyaml≥6.0；可选 extra `ml`（scikit-learn/lightgbm/torch）。
- **uv**：硬前置（所有命令 `uv run` 形态），setup 检测并给安装指引。
- **codex CLI**：软前置。检测 `command -v codex`；缺失 → 明示三审查点降级路径与可信度封顶 B（机制已内置，无新代码）。
- **agent model 档位**：7 agent 中 6 个 opus + 1 个 sonnet；README 注明订阅档位要求，以及用户可在安装副本中自行下调 model 字段（质量自负）。

## 八、分发与安装

- 仓库推到 GitHub（或内网 git）；用户侧两种方式：
  1. `/plugin marketplace add <repo-url>` → 安装 `quant-report-reproduce`；
  2. 或 `claude plugin install`（marketplace 生态可用时）。
- `plugin.json` 最小清单：name=`quant-report-reproduce`、description、version=`2.1.0`、author。skills/agents 按目录约定自动发现，无需在清单中枚举。
- 安装后技能带命名空间（`quant-report-reproduce:reproduce`）；无冲突时 `/reproduce` 短名可直呼，README 写清两种呼法。

## 九、兼容性承诺

1. **形态 A 零破坏**：test_v2 及历史案例的全部命令、路径、门禁行为不变（6.1 前缀无害、6.2 命中 elif 分支、6.3 种子即原位文件）。
2. **tests/ 全绿保持**：109 个 check_gates 测试不动；新增 setup_workspace 的单测（幂等性、种子拷贝跳过逻辑、配置生成）。
3. **状态机不动**：STAGE_ORDER、门禁定义、agent 契约、审计协议一律不变——插件化只动「入口配置、路径定位、资产分发」三层。

## 十、实施清单（S1–S8）与验收标准

| # | 事项 | 产物 | 前置 |
|---|------|------|------|
| S1 | 插件清单 | `.claude-plugin/plugin.json` | 无（不影响在跑流程） |
| S2 | skills/agents 根级化 + symlink | `skills/` `agents/` 正本，`.claude/` symlink | **G-FN 后**（动 skill 目录） |
| S3 | setup 工具 | `tools/setup_workspace.py`（幂等：配置生成/种子拷贝/目录树/检测报告）+ 单测 | G-FN 后 |
| S4 | SKILL.md 改造 | setup 路由分支 + §六定位协议 + 全部工具命令加 `REPORT_REPRODUCE_ROOT` 前缀与 `$REPRODUCE_TOOLS` 路径 | G-FN 后 |
| S5 | setup 执行卡 | `skills/reproduce/stages/setup.md`（§四流程） | S3/S4 |
| S6 | data_loader 配置化 | `common/data_loader.py::get_data_root()`（就近 `.reproduce.json` → 回退 `~/local_data`） | G-FN 后 |
| S7 | 文档 | README 插件安装/首次配置/呼法/档位要求/维护者双形态说明 | S1–S6 |
| S8 | 端到端验收 | 临时目录模拟形态 B：本地安装插件 → setup 三问 → 假数据小案例跑 init+extract 两阶段确认路径全通 | S1–S7 |

**验收标准**：
- V1 形态 A 回归：test_v2 `check_gates` 全阶段重跑判定不变；tests/ 全绿。
- V2 形态 B setup：空目录一次 setup 后，`.reproduce.json`/templates/common/pyproject/目录树齐备，重跑幂等。
- V3 形态 B 路径：`$REPRODUCE_TOOLS` 三级兜底在实测中至少两级可用（插件变量 + 配置记录）；`state.py init` 产物落用户目录而非插件目录。
- V4 配置消费：`--mode`/`--max-iter` 缺省时取 `.reproduce.json`；显式参数优先；data_loader 读 data_root。
- V5 无 codex 环境：setup 明示降级；流水线跑到 spec_audit 时按既有降级协议走通。

## 十一、风险与开放问题

1. ~~`${CLAUDE_PLUGIN_ROOT}` 在 skill 正文的替换行为需实测~~ **已实测钉死（2026-07-09 真实安装）**：不替换、环境变量也不注入；协议已修订为 skill base directory 首选（见 §6.2）。
2. Windows symlink（形态 A 单一事实源）：当前用户全 macOS，遇到再议。插件安装实测中 symlink 被原样保留、无害。
3. 子 agent 定义中若存在对仓库绝对/相对路径的隐含假设（如「读 templates/xxx」相对 cwd），形态 B 下 cwd=用户项目且有种子拷贝，预期成立；S8 端到端时逐 agent 抽验。
4. 插件升级与用户侧种子漂移：首版用「跳过+清单提示」策略，不做三方合并。
5. **本地路径 marketplace 的拷贝语义（真实安装实测发现）**：`claude plugin marketplace add <本地路径>` 会全量文件系统拷贝（含 `.venv` 385M、`output/` 39M 等 gitignore 内容，实测缓存 431M）。git URL 分发只含 git 跟踪内容、不受影响。对策：正式分发一律用 git URL；本地路径仅限维护者自测（知悉体积开销）。
6. **分发必需 `.claude-plugin/marketplace.json`**（真实安装实测发现）：单插件仓库作为 marketplace 源时该清单是硬前置（`plugins[].source="./"`），已补齐入库。

## 十二、2026-07-09 增补：oos 阶段（样本外表现分析）

用户需求：「如果复现成功，要处理研报回测区间样本外的表现」。

- **状态机**：STAGE_ORDER 插入 `oos`（`result_audit → oos(条件) → report`），条件 stage 语义与 iterate 一致（SKIPPABLE_STAGES）。触发条件 `verdict.result ∈ {pass, partial}`；verdict 不满足或本地数据未超出研报区间 → skipped（record-event 留痕），不阻塞 report。
- **新 agent `quant-oos-analyst`（opus）**：把 `src/{id}` 策略**原样**延伸到样本外区间。核心红线：严禁修改策略逻辑与参数（防数据窥探美化样本外）；区间零重叠（oos_start = 样本内末日次一交易日）；指标与 comparison.json 同族同口径；结论四选一枚举（延续/衰减/失效/样本不足），判读阈值写明。
- **产物合同**：`oos_metrics.json`（区间/oos_days/指标对比/conclusion）、`oos_nav.png`（内外分色+分界线）、`oos_summary.xlsx`、`workspace/{id}/oos_report.md`（oos_days<60 强制「样本外过短」警示）。
- **门禁 G-OS**（5 项）：产物结构 / **区间零重叠（防样本内数据冒充样本外）** / 结论枚举 / 短样本警示 / 图表字节数。G-FN 动态：`stages.oos.status==done` 时 final_report 必含「样本外表现」章节；skipped 不要求（旧案例零追溯影响）。
- **旧 state 迁移**：`state.py migrate <id>`（幂等）——STAGE_ORDER 演进后补缺失 stage 键，顶层终态补 skipped、运行中补 pending。本仓库 4 个历史案例已迁移。

## 十三、2026-07-10 增补：复现结果单文件 HTML 展示页

用户需求：「输出复现结果最终都放到一个 html 里展示」。

- **确定性工具而非模型生成**：`tools/render_report.py` 读结构化产物（state.json 硬输入 / comparison.json 硬输入 / oos_metrics.json / *.png / final_report.md / assumptions.md）按固定模板渲染 `output/{id}/final_report.html`——每份报告样式统一、零 token、幂等可重跑；可选输入缺失按节省略/占位容错。
- **页面内容**：verdict/评级/覆盖率/迭代 KPI 卡、指标对比总表（pass/fail 标色 + 全部/仅未达标筛选 + 归因列）、图表画廊（base64 内嵌自包含，单图 >8MB 跳过）、样本外表现节（oos 产物存在时）、外部审查台账、假设登记簿与最终报告全文（简易 markdown 渲染折叠收录）。所有产物文本 HTML 转义（注入防护有单测）。
- **集成**：report 执行卡步骤 5（reporter 点收后主会话跑工具）；门禁 G-FN-7（存在 + 含 report_id 与「指标对比总表」锚 + >5KB）。
- 评级 A/B/C 从 final_report.md 正则提取（state 不存评级）。

## 十四、2026-07-10 增补（v2.6.0）：分诊判据修正 + 成本三刀 + 核验分级

1. **分诊判据修正**（_plan_template §三）：test_v2 实测暴露旧判据三缺陷——milestone 数 ≥3 即 hard 是循环论证（拆分产出反推难度）、any-hard 规则太激进（已降级支线缺失仍抬档）、模块数量≠技术难度。新判据：方法复杂度定基准档（训练/优化/多资产联动才 hard）→ 修正项各最多上调一档（主线数据需外部/复杂衍生；模块 ≥8 且基准已 medium）→ easy 收口（单模块+标准公式+数据全有）。
2. **经济模式**（`.reproduce.json economy`，问卷第二批第 2 问）：Agent 派发 model 覆盖——extractor/verifier/oos-analyst → sonnet；planner/coder/auditor/diagnoser 恒 opus。SKILL.md 全局派发规则。
3. **外审档位**（`audit_level: strict|standard`，配置文件项不进问卷）：standard 时 spec 外审触发条件（blocking/major 歧义 ∨ 首次类型 ∨ hard）、code 外审触发条件（ml tag ∨ hard ∨ 内审 critical）；不触发时落明示 skipped 的占位档（占位 JSON findings=[] 天然过三关解析，G-SA-1 三件套占位齐、external_reviews 记 skipped，报告如实展示）。result 外审任何档位必跑。
4. **reporter 瘦身**：输入合同以 audit_responses 总表 + iteration_log + 最后一轮 diagnosis 替代全量原文（验收实测 reporter 380k token 的主要来源）。
5. **核验分级**（`verification_level: full|directional|magnitude|unverifiable`）：参数不明指标的诚实降级。裁定权唯一在 diagnoser（限 assumption_linked 项、AS 性质须为参数不明）；verifier 只落字段无权发起；recalc_metric 分路径判定（方向/量级/不计入分母）；**防作弊**：降级未锚定 assumption_linked 直接 False；auditor(result) 三点人审（AS 性质/裁定出处/档位不过度）；G-VF-3 对 unverifiable 豁免且透明展示（waived 清单），渲染页分层统计。

## 十五、2026-07-11 增补（v2.7.0）：墙钟加速与暂缓清单

机器事实锚点：G-IM-4 只核 implement=done（milestone verify 子状态无 gate 消费）；G-VF-6 新鲜度是 critical 修复后旧 verify 产物的机器作废兜底；state.py 无文件锁（同批并行写丢更新）；Agent 并行为 fork-join 批次（不可中途召回，「作废在途」不可行 → 语义改为「缓验 + 增量适配」）。

落地五项（全部文案层）：implement 流水线（verify(mN)∥code(mN+1) 滚动深度 1 + 汇合分诊表：mN 所辖 FAIL 计重派/流水线干扰假 FAIL 复跑不计/下游缓验/尾部条件后才 G-IM --record）；code_audit∥verify 默认化（easy/ml 例外）；result_audit∥oos 可选并发（G-RA 先行、critical 回 verify 则 oos 作废）；拆分粒度收紧（hard 3~5、<100 行合并、elements 不减条）；并行纪律两条入硬约束。

**暂缓清单**（本次不做，留档）：
1. G-IM-6：核 medium/hard milestones 全部 verify=done——关掉「在途验证被遗忘」协议洞的机器化方案，属门禁语义变更。
2. verifier 增量重跑：迭代轮只重算受影响指标族+抽样全量校验——需案例数据支撑正确性设计。
3. plan∥codex 盲提取预跑：coverage_matrix 撕裂读产生噪声意见污染审计台账；若做需先从 codex prompt 输入清单移除矩阵。

## 十六、2026-07-11 增补（v2.8.0）：实验模式（市场迁移复现）

用户需求：复现海外报告时原文市场数据本地没有（如某论文用美国 CPI），可用中国大陆等价数据替代，运行后给出明确提示，此类复现不要求结果与原论文一致。

- **state 字段** `reproduction_mode: strict|experimental`（默认 strict；init `--experimental` 写入；migrate 对旧 state 补 strict）。唯一写入口为主会话——agent 无法自行切换，防止借实验语义绕过 strict 容差。
- **门禁分流**（`_is_experimental`）：G-VF-3 只核每个原文指标有迁移市场产出（数值对齐豁免→iterate 天然 skipped）；G-RA-3 无超差归因语义直接 PASS（detail 注明）；G-FN 动态必含「市场迁移」章节（用户核心要求：运行后明确提示）。反虚报（K/E 系列、codex result 审查）照跑——数字与产物一致性、结论措辞不夸大（不得把迁移结果说成原文复现成功）。
- **数据映射**：plan 的 data_requirements 新状态 `substitute`（原文数据→本地等价+理由），每个替代入 assumptions（性质 market-transplant）。G-PL 不校验该枚举，零门禁改动。
- **切换协议**：strict 下 planner 发现原文市场整体不可得但可替代 → 写明方案后置 feasibility: blocked 交人工裁决；用户确认后主会话 `set <id> reproduction_mode experimental` 续跑。
- **展示**：render_report.py 顶部 warn 色 banner + hero「实验模式·市场迁移」徽章 + 指标表列头改「原文值（对照参考）/迁移复现值」。
- **oos 兼容**：实验模式下样本外分析照常（验证迁移市场上方法的持续性）。

## 十七、2026-07-11 增补（v2.9.0）：codex 备用方案补强（外审降级链细化）

**问题**：用户可能未安装 codex CLI，或订阅额度中途耗尽。既有协议已有两级降级（claude_fallback → skipped）骨架，但存在六处盲区：额度耗尽会白做「缩减输入重试」（缩输入救不了配额）；未安装时每个审查点反复空调用；替身派发细节不明（subagent_type/prompt 来源/产物落盘方/economy 降配与否全靠现场发挥）；评级封顶口径三处不一致（reporter 判据「降级或缺失→B」vs spec_audit 卡「二级 skipped 才封顶且限 hard」vs result_audit 卡「hard 缺外审封顶 B」）；iterate 第二意见一边写「防兜圈关键输入必须 join」一边失败即缺席、无替身路径；verifier 辅助 codex 无失败条款。

**方案（全部文案层，零代码/零门禁变更——check_gates 只核产物文件与 JSON 格式、不核 engine 字段，替身写同路径同格式天然过三关解析）**：

- **正本收口**：降级链完整协议收口在 `stages/spec_audit.md`「codex 降级链」节，code_audit / result_audit / iterate 三卡引用正本、只保留差异项（缩减重试输入、替身输出路径、标记块要求）。SKILL.md 二节留 4 行全局指针。
- **速判**：调用前 `command -v codex`，未安装零成本直降一级；「未安装」在案例内沿用（后续审查点不再探测），「额度/临时故障」不沿用（额度可能恢复，每审查点先试一次、失败即快速降级）。
- **失败分类**：stderr/输出含 usage limit/quota/429/401/402/login 等额度认证特征 → 跳过缩减重试直接降级；超时/网络/截断类才缩减重试 1 次。
- **替身规范**（一级降级）：subagent_type=`general-purpose`，prompt=该审查点已填充的 codex prompt 正文（骨架引擎无关，「苛刻审稿人」角色设定通用）+ 四条替身约束（只读列出的输入文件禁读过程性文件 / 输出契约与原 prompt 一致含标记块 / 全文 Write 入原 codex 输出路径 / 不派发不调 skill）；替身属质量敏感角色不受 economy 降配。external_reviews 记 engine=claude_fallback + reason。
- **result 特殊地位**：反虚报最后防线，任何 audit_level 必须至少走到替身，不得直接 skipped。
- **iterate second_opinion 同链**：一级替身出第二意见（独立上下文保留防兜圈价值），替身也不可行才允许缺席（「如有」的唯一语义），iteration_log 记缺席原因；不入 external_reviews、不影响评级。
- **verifier 辅助自查**：codex 不可用直接跳过，辅助缺席不构成验证失败、不做替代调用（替身降级仅限主会话三审查点）。
- **评级口径统一（以 reporter 判据为权威）**：失败性降级/缺失（claude_fallback 或因不可用落 skipped）不分难度封顶 B——替身保住审查覆盖、不恢复异构引擎交叉验证的可信度；**audit_level=standard 未触发的配置性 skipped 不封顶**（触发条件本身是风险导向的，未触发=低风险路径，result 必跑兜底；否则 standard 用户永远拿不到 A，档位失去意义）。装回 codex / 额度恢复即自动回主路径，无需配置。

**边界如实**：替身与被审代码同为 Claude 家族，异构盲区（同源幻觉、同源口径偏好）无法靠替身消除——这正是封顶 B 的理由；用户长期无 codex 时评级上限即 B，这是诚实标注而非惩罚。

## 十八、2026-07-11 增补（v2.10.0）：案例统一编号

**问题**：report_id 从 PDF 文件名派生，下载的研报常是无语义编号名（`ssrn_6115073`）或中文名，用户记不住、引用麻烦（continue/revise/accept 都要敲全名）。

**方案**：
- **自动编号**：未给 `--id` 时，init 前调 `state.py next-id --slug <slug>` 得 `rNNN_<slug>`——NNN 三位顺序号接现存最大编号（`^r(\d{3})_` 前缀扫描 workspace/ 下含 state.json 的目录），slug 取 PDF 文件名 snake_case、文件名无语义或非 ASCII 时由主会话从研报标题取 2-4 个英文词。字母前缀 r 保证 id 仍是合法 Python 包名（src/{id} 模块路径约束）。
- **缩写解析**：`state.py resolve <query>`——完整 id 精确命中 > 编号缩写（`r?0*(\d+)` 规范化为 rNNN_ 前缀，r3/r003/3 等价）> 一般前缀兜底（编号零命中时回退，r00 视为打一半的前缀而非编号 0）。唯一命中输出完整 id；多命中列候选 exit 1；零命中列现有案例 exit 1。SKILL.md 三节头部定全局协议：所有接受 `<id>` 的子命令先 resolve 再用。
- **status 一览表**：无参 status 按编号排序制表（编号 | report_id | 类型/难度 | 状态 | 当前阶段），作为「我有哪些案例」的唯一入口。
- **兼容**：既有案例不迁移（在跑案例改 id 要动 workspace/src/output 三处目录 + state 内路径 + 代码 import，风险大收益小）；旧式 id 照常用、可前缀缩写；`--id` 显式指定不强加编号。两个子命令均只读，不违反 state.py「唯一写入口」架构（编号在 init 落盘时才被占用；并发起两个新案例不在设计内）。

**边界如实**：next-id 只扫描不锁号，同时起两个新案例会拿到同号——单用户串行起跑场景不设防；resolve 的编号匹配不 fallback 到「rNN 开头的非编号 id」歧义场景（id 规范排除了数字开头，实际不冲突）。

## 十九、2026-07-12 增补（v2.11.0）：术语人话化（客户可读性）

**问题**：外部客户看不懂 G-XX（门禁）、CDX-X-##（外审意见）、K/E 系列等代号，对照手册术语表也麻烦。用户拍板：手册单页人话化+悬浮释义（不拆双页）；复现产物（final_report.md + final_report.html）一起改。

**边界（先于方案确立）**：内部审计文书与 state.json 枚举零改动——代号是机器解析依赖（`_parse_audit_responses` 按 `CDX-` 前缀分拣），只改展示层不改数据层；check_gates.py 不改。实施前双重核实的「不可动清单」：G-FN-2 的 H2 关键词子串、G-FN-5 的 rejected `CDX-X-NN` 原样出现、G-FN-7 的「指标对比总表」字面量、render_report 的 `_grade_from_report` 评级提取正则（「可信度评级」四字后 ≤24 字符内即评级字母）。

**三个界面的落地**：
- **手册**：`.term[data-tip]` + 共享 `#tt` 悬浮层（position:fixed 免受 tbl-scroll/track-scroll 的 overflow 裁剪——absolute 伪元素方案在这些容器首末行必被裁；约 25 行内联 JS 只做定位：pointerover/focusin/touchstart 显示、scroll/Escape 收起、视口边界钳制）。22 处挂点：轨道 11 门禁 pill（tip 文案抄阶段表末列，不造新口径）+ 正文 11 处（K/E 系列、外审三审查点、stop_partial/blocked、paused_blocked、失败性降级、market-transplant、major-auto×2 等）。无 JS 降级：虚线仍标识术语、术语表节兜底（引言注明悬停用法）。阶段表不挂（已有人话列，挂了是噪音）；代码块内代号不挂（破坏观感，紧邻正文已释义）。
- **结果页（render_report.py）**：7 个展示层映射 dict（VERDICT/TYPE/DIFFICULTY/CHECKPOINT/ENGINE/REVIEW_VERDICT/ATTRIBUTION_CN），`_cn()` 统一「中文为主+原始值括注」，`.get(v,v)` 兜底未知枚举原样透传不吞值。8 处渲染点：hero 判定、类型难度、KPI 卡、归因列、指标状态（达标/超差）、样本外基线、外审台账（表头中文化+降级引擎 warn pill 凸显+先按原始值判色后换文案——`v.startswith("pass")` 顺序反了 pass_with_issues 掉色）、footer。
- **最终报告（quant-reporter.md 硬约束第 11 条 a–g + checklist 两项）**：H2 关键词在行内可加人话后缀；代号首现附中文说明；审计回应汇总表必含「这条意见说什么·我们怎么处理」人话列（只复述不新增结论）；rejected 句式固定（代号原样保 G-FN-5）；附录 A.3 列头取值中文化；**评级句式固定「可信度评级：X（一句话判据）」**（渲染器正则契约——前置判据句「可信度评级（A/B/C 三档）」会让徽章误抓 A）；状态枚举中文化首现括注。report 执行卡三处配套（主会话转述用固定中文对照防 reporter 自造译名/点收加验三点/失败处理加徽章误抓分支）。

**边界如实**：悬浮释义在 iOS 页面缩放下 fixed 坐标有轻微偏差（max-width 340 + 边界钳制兜住，不引 visualViewport 保持极简）；reporter 为 sonnet 档，11 条措辞全部写成机械可执行句式，不留自由裁量。
