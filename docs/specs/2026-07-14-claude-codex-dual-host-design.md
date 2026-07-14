# Claude Code / Codex 双宿主兼容设计

**日期**：2026-07-14  
**状态**：已实施
**目标版本**：v2.12.0

## 一、目标

把当前“Claude Code 主编排、Codex CLI 异构外审”的单宿主插件改造成双宿主插件：

- 用户在 Claude Code 中运行时，Claude Code 负责主编排，Codex CLI 默认承担异构外审。
- 用户在 Codex 中运行时，Codex 负责主编排，Claude Code CLI 默认承担异构外审。
- 两端共用同一套状态机、门禁、阶段卡、模板、角色合同和业务代码。
- 异构外审不可用时允许同宿主独立盲审降级，但最终可信度评级封顶 B。
- 历史案例和现有 Claude Code 插件安装方式继续可用。

本改造只涉及插件分发、编排适配、外审执行和展示兼容，不改变量化复现算法、阶段顺序或达标判定标准。

## 二、方案选择

采用“共享核心 + 双宿主薄适配层”。不维护两份完整技能，也不在每张阶段卡中散布大量宿主分支。

共享核心包括：

- `skills/reproduce/SKILL.md` 与 `skills/reproduce/stages/*.md`
- `templates/`、`tools/`、`common/`
- 8 个量化角色的职责合同
- 审查输出 JSON、意见编号和门禁协议

宿主差异收口在：

- Claude Code 与 Codex 的插件清单
- `skills/reproduce/adapters/{claude_code,codex}.md`
- 子代理派发方式
- 默认异构外审 CLI 的选择

## 三、宿主识别与运行时路由

`/reproduce` 启动后先识别当前宿主，再读取对应适配卡：

| 当前能力 | host | 默认外审 |
|---|---|---|
| Codex 协作代理工具可用 | `codex` | `claude` |
| Claude Code Agent/Task 工具可用 | `claude_code` | `codex` |

如果两类能力均不存在或无法唯一判断，流程停止并说明环境不受支持；不得静默选择同源审查。

适配卡只定义四类差异：角色派发、并行汇合、同宿主替身盲审、面向用户的宿主提示。状态机和产物合同仍由共享技能及阶段卡定义。

## 四、外审执行器

新增 `tools/external_review.py`，集中处理外部 CLI 调用。命令行接口：

```text
python tools/external_review.py \
  --engine codex|claude \
  --prompt <prompt.md> \
  --output <review.md> \
  --cwd <workspace-root> \
  [--timeout 600]
```

执行器职责：

1. 使用 `shutil.which()` 检测目标 CLI。
2. Codex 使用只读沙箱和无颜色非交互模式。
3. Claude 使用 `-p`、无会话持久化，并仅开放 `Read`、`Glob`、`Grep`。
4. 捕获超时、非零退出、空输出、认证失败和额度耗尽。
5. 只在成功且输出非空时原子写入目标审查文件。
6. 将结构化执行结果输出到 stdout，字段固定为：
   `engine/status/reason/returncode/output/duration_seconds`。

`status` 枚举为 `success|unavailable|auth_error|quota_error|timeout|failed|empty_output`。阶段编排根据该状态决定缩减重试或同宿主降级，执行器本身不判定审查通过与否。

外审命令：

- Claude Code 宿主：`codex exec -s read-only --skip-git-repo-check ...`
- Codex 宿主：`claude -p --no-session-persistence --tools Read,Glob,Grep ...`

认证或额度错误不做无意义的缩减重试；普通失败允许按现有协议缩减输入重试一次。

## 五、子代理角色分发

`agents/*.md` 继续作为角色合同正本，并保持 Claude Code 插件自动发现方式。

新增 `tools/sync_codex_agents.py`，从 Markdown frontmatter 与正文生成 `.codex/agents/*.toml`：

- `name` 来自文件名或 frontmatter。
- `description` 来自 frontmatter。
- `developer_instructions` 等于 Markdown 正文。
- Claude 的 `model: opus|sonnet` 映射为 Codex 的推理强度；不在 TOML 中写死可能变动的模型 slug。

`/reproduce setup` 将 `.codex/agents/*.toml` 幂等复制到目标项目。若 Codex 当前任务尚未重新加载这些项目级角色，主技能使用通用子代理并在派发消息中附完整角色合同；新任务会自动发现命名角色。子代理仍禁止嵌套派发。

## 六、插件结构

保留现有 Claude Code 文件：

```text
.claude-plugin/plugin.json
.claude-plugin/marketplace.json
agents/*.md
skills/reproduce/
```

新增 Codex 文件：

```text
.codex-plugin/plugin.json
.agents/plugins/marketplace.json
.codex/agents/*.toml
```

Codex 清单使用同一插件名 `quant-report-reproduce`，显式声明 `skills: "./skills/"`。Claude 与 Codex 各维护一份仅含分发元数据的 marketplace：Claude 使用 `.claude-plugin/marketplace.json`，Codex 使用 `.agents/plugins/marketplace.json`。后者以 Git URL 指向仓库根插件并包含安装策略、认证策略和分类字段；两份 marketplace 不复制任何 skill、agent 或业务逻辑。分开清单的原因是 Claude Code 严格校验不接受 Codex 的 `policy` 字段。

仓库现有大写 `.Codex/` 不作为正式分发路径。macOS 大小写不敏感且用户全局 ignore 可能匹配 `.codex/`，实施时需用显式路径加入版本控制。

## 七、产物与向后兼容

新案例的外审产物采用宿主无关名称：

- `spec_audit_external.md`
- `spec_external.md`（规格审查中的独立盲提取清单）
- `code_audit_external.md`
- `result_audit_external.md`
- `second_opinion_external.md`

`check_gates.py` 先找新名称，缺失时回退现有 `*_codex.md`。历史案例无需迁移，已有门禁结果不失效。

意见 ID `CDX-S/C/R-*` 暂不改名，因为它们已进入历史 `audit_responses.md`、门禁正则和最终报告。对用户展示时解释为“外部审查意见编号”，不再解释为特定引擎。

`state.json.external_reviews[].engine` 新增：

- `codex_external`
- `claude_external`
- `same_host_fallback`
- `skipped`

继续读取旧值 `codex` 与 `claude_fallback`。展示层将新旧值都映射为中文，`same_host_fallback` 和失败性 `skipped` 使用警告样式。

## 八、降级与可信度

| 宿主 | 默认异构外审 | 一级降级 | 二级降级 |
|---|---|---|---|
| Claude Code | Codex CLI | Claude 独立盲审 | skipped |
| Codex | Claude Code CLI | Codex 独立盲审 | skipped |

一级降级必须使用独立上下文，只读输入合同中的文件，不得读取主会话叙事、agent 完成汇报或既有回应表。Codex 同宿主替身使用无历史分叉；Claude 同宿主替身使用 general-purpose 独立任务。

发生 `same_host_fallback` 或失败性 `skipped` 时，最终可信度评级封顶 B。`audit_level=standard` 未触发造成的配置性 skipped 不封顶。`result_audit` 无论档位都必须至少尝试一级降级，不能直接跳过。

## 九、setup 与环境报告

`tools/setup_workspace.py` 同时检测 `codex` 与 `claude`，报告两种宿主各自可用的异构外审路径。setup 不把当前宿主写死在 `.reproduce.json`，因为同一工作目录可能交替由 Claude Code 和 Codex 使用。

setup 额外安装 `.codex/agents/*.toml`，已存在文件仍不覆盖，并进入“插件侧较新”提示清单。环境报告必须明确：缺少哪一个 CLI 只影响在哪个宿主下的异构外审，以及评级封顶规则。

## 十、验证与验收

自动测试不调用真实付费模型，使用假 CLI 或 mock 验证：

1. 外审执行器为两种引擎构造正确的只读命令。
2. 成功、CLI 缺失、认证失败、额度错误、超时、非零退出和空输出分类正确。
3. setup 会复制 Codex 代理并报告两个 CLI。
4. 新旧外审文件名均可通过 G-SA/G-CA/G-RA。
5. 新旧 engine 枚举都能正确渲染，降级引擎使用警告样式。
6. Codex 插件清单通过官方 `validate_plugin.py`。
7. 8 个 Codex TOML 可解析，正文与 Markdown 正本一致。
8. 全量 pytest 回归通过。

在用户已登录两个 CLI 的环境，可额外做一次最小只读真实冒烟测试；它不作为自动测试前置，也不得读取案例机密数据。

## 十一、非目标

- 不修改 12 阶段顺序、standards.json 或达标容差。
- 不重写历史案例产物。
- 不强制用户同时安装两个宿主；缺失外审 CLI 时按降级链继续。
- 不在本次改造中发布公共插件市场或创建正式 PR。
- 不把 Claude/Codex 的具体模型版本写死在共享业务合同中。
