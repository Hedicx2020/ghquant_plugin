# 研报复现系统（report_reproduce）

给定一份量化研报 PDF，按报告类型与难度自动分诊、复现策略代码与回测结果，产出与原文逐项对照、附可信度评级的最终报告。

本仓库同时是一个 **Claude Code 插件**（`quant-report-reproduce`）：既可以克隆后在仓库内直接使用（形态 A，维护者模式），也可以作为插件安装后在任意自己的目录中使用（形态 B，见下节）。

## 作为插件安装（推荐给其他使用者）

```bash
# 在 Claude Code 中添加本仓库为插件源并安装
/plugin marketplace add https://github.com/Hedicx2020/ghquant_plugin
```

**首次使用（三步）**：

1. 进入你自己的工作目录（任意空目录即可），运行 `/reproduce setup`——向导会问五项配置：
   - **数据路径**：本地 parquet 数据根目录（默认 `~/local_data`）
   - **执行模式**：`auto` 全自动优先（推荐，歧义自动假设并登记、事后可定向重跑）/ `interactive` 遇关键歧义暂停人工裁决
   - **最大迭代次数**：按难度自动（easy 3 / medium 5 / hard 6）或自定义 1-10
   - **回测框架**：默认使用内置 `common/` 回测库；也可指定你自有回测框架的目录路径——复现代码的回测执行层将优先调用你的框架，内置库仅补缺口
   - **偏差容忍**：你能接受的复现值与原报告的偏差。默认按 `templates/standards.json` 分类型精细容差（年化/夏普等 5%、因子 IC 近零走绝对偏差等）；也可自定义统一百分比（如 10%）——所有相对偏差判定随之放宽或收紧，达标判定与最终报告一致生效
   随后 setup 自动落地：`.reproduce.json` 配置、`templates/`（含数据目录模板与达标标准）、`common/`（公共回测库）、`pyproject.toml`、目录树，并检测 uv / Python 依赖 / codex CLI。
2. **维护 `templates/data_catalog.md`**：按你数据目录的实际内容登记数据清单——分诊阶段判断「研报所需数据是否可得」完全依据此文件。
3. 把研报 PDF 放进 `reports/`，运行 `/reproduce reports/xxx.pdf` 起跑。

**环境要求**：
- [uv](https://docs.astral.sh/uv/)（硬前置，所有工具经 `uv run` 调用）；依赖缺失时在工作目录 `uv sync`
- Claude 订阅档位：子 agent 主力为 opus（7 个中 6 个），建议 Max 档位；可自行编辑安装副本中 `agents/*.md` 的 model 字段下调（复现质量自负）
- codex CLI（软前置）：外部三审查点用；未安装会自动降级并在最终报告标注（可信度评级封顶 B）

## 快速开始（两种形态通用）

```bash
/reproduce setup                          # 首次使用配置向导（形态 A 本仓库直跑可跳过）
/reproduce reports/test.pdf --mode auto   # 新起一份复现
/reproduce status                         # 查看全部案例状态摘要（中文进度）
```

其余子命令：`/reproduce continue <report_id>` 断点续跑；`/reproduce revise <report_id> ...` / `/reproduce accept <report_id>` 用于人工 review 闸门。

## 目录导航

| 路径 | 内容 |
|------|------|
| `.claude-plugin/plugin.json` | 插件清单 |
| `docs/specs/2026-07-07-reproduce-v2-design.md` | v2 完整设计文档（状态机 / 门禁 / agent 契约 / 防偷懒审计体系） |
| `docs/specs/2026-07-09-plugin-packaging-design.md` | 插件化设计（双形态 / 路径解耦 / setup 向导） |
| `CLAUDE.md` | 编码与产出格式落地约定（命名 / Excel / 图表 / common 复用 / 数据对齐） |
| `skills/reproduce/` | `/reproduce` 主编排 SKILL.md + stage 执行卡（`.claude/skills/` 为回指 symlink） |
| `agents/` | 7 个子 agent 定义（`.claude/agents` 为回指 symlink） |
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

- 2026-07-09：setup 配置第五项——`default_max_rel_dev`（可接受的与原报告的偏差，0.005-0.5 小数；留空按 standards.json 分类型精细容差）。check_gates 的 load_standards 自动读取并统一替换所有相对偏差上限（绝对偏差/同号/量级/定性语义不变），G-VF-3/G-RA-3 与 verifier 对数口径一致生效；6 个新测试。
- 2026-07-09：setup 配置第四项——`backtest_framework`（用户自有回测框架目录，setup 校验存在性，写入 .reproduce.json）；plan/implement 派发合同据此优先复用用户框架、内置 `common/` 仅补缺口，未指定时行为不变。公开分发仓库快照剔除 reports/test.pdf（研报原文不对外）。
- 2026-07-09：内部修复——check_gates 的 G-VF-6 新鲜度检查两侧排除 `__pycache__`/`*.pyc` 派生物（重放 G-IM 的 compileall 或 results 内脚本旧字节码缓存会造成误判），附四个正反测试；不影响使用方式。
- 2026-07-09：插件化（v2.1）——新增 `.claude-plugin/plugin.json`、`/reproduce setup` 配置向导（`tools/setup_workspace.py`，数据路径 / 执行模式 / 最大迭代三项 + 种子拷贝 + 环境检测）；skills/agents 迁至仓库根级（`.claude/` 下以 symlink 回指）；工具调用统一 `REPORT_REPRODUCE_ROOT` 前缀与 `$REPRODUCE_TOOLS` 定位协议（双形态兼容，本仓库直跑行为不变）；`common/data_loader.py` 数据根改读 `.reproduce.json`（缺省回退 `~/local_data`）；status 呈现约定中文化。设计见 `docs/specs/2026-07-09-plugin-packaging-design.md`。
- 2026-07-08：内部修复——收紧 check_gates 的 G-IT 豁免正则（防结论行同行提及 stop_partial 被误判豁免），附正反测试；不影响使用方式。
- 2026-07-08：内部修复——check_gates 的 codex 输出解析器支持裸 JSON（prompt 契约允许的合法格式，端到端验收中发现只认 fenced 块的缺口）；不影响使用方式。
