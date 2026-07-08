# 研报复现系统插件化设计（v2.1）

> 立项：2026-07-09，用户指令「把项目做成一个插件，其他用户可以直接调用；用户初次使用要配置数据路径、是否自动执行（或人工参与执行）、最大迭代次数」。
> 前置：v2 十一阶段门禁状态机已交付（见 `2026-07-07-reproduce-v2-design.md`），test_v2 端到端验收进行中。
> 实施闸门：涉及在跑流程的核心文件（`.claude/skills/reproduce/`、`tools/`）的修改，一律等 test_v2 验收 G-FN 门禁通过后动手。

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
2. **三项配置（AskUserQuestion 一次问卷）**：
   - **数据路径 data_root**：默认 `~/local_data`；说明「parquet 本地数据库根目录，data_catalog.md 描述的数据都应位于此」。
   - **执行模式 default_mode**：`auto`（推荐，全自动优先：blocking 歧义按最合理假设放行并标记 major-auto，事后可 revise）/ `interactive`（遇 blocking 歧义暂停，人工裁决后继续）。
   - **最大迭代次数 default_max_iter**：`按难度自动`（推荐，easy 3 / medium 5 / hard 6）/ 自定义整数（1-10，全局覆盖难度矩阵）。
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
