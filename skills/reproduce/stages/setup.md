# stage: setup（首次使用配置向导，非状态机阶段，幂等可重跑）

用户工作目录初始化：三项配置 + 骨架落地 + 环境检测。**不是 STAGE_ORDER 的一员**，不写 state.json、无门禁；任何时候可重跑（重跑默认保留已有配置与用户已改文件）。

## 动作序列

1. **已初始化检测**：cwd 存在 `.reproduce.json` → 读出并展示现有三项配置，用 AskUserQuestion 问「保留现有配置只补齐缺失文件 / 重新配置三项」；选保留则跳过步骤 2，调用步骤 3 时**不带** `--force-config`。

2. **六项配置（AskUserQuestion 分两批收齐；工具单次上限 4 问，严禁超限）**：

   **第一批（4 问）**：
   - **数据路径**（header: 数据路径）：本地 parquet 数据根目录。选项：`~/local_data`（默认）/ 自定义（Other 输入）。说明：分诊数据可行性以 `templates/data_catalog.md` 为唯一判定依据，该目录下的数据请在 setup 后维护进 catalog。
   - **执行模式**（header: 执行模式）：`auto`（推荐——全自动优先：研报歧义按最合理假设放行并登记高亮，跑完统一人工 review，可事后 revise 定向重跑）/ `interactive`（遇 blocking 级歧义暂停，人工裁决后继续）。
   - **最大迭代次数**（header: 迭代上限）：`按难度自动`（推荐——easy 3 / medium 5 / hard 6 轮）/ 自定义 1-10 的整数（全局覆盖）。说明：指标未达标时的自动迭代修正轮数上限；轮次越多复现越充分、耗时与成本越高。
   - **回测框架**（header: 回测框架）：`内置框架`（推荐——使用随插件落地的 `common/` 回测库）/ 自定义路径（Other 输入你自有回测框架的目录）。说明：指定后复现代码的回测执行层优先调用你的框架、`common/` 仅补缺口；路径必须真实存在（工具会校验）。

   **第二批（2 问）**：
   - **偏差容忍**（header: 偏差容忍）：`按内置标准`（推荐——分类型精细容差：如年化/夏普等相对偏差 5%、因子 IC 近零走绝对偏差 0.005，详见 `templates/standards.json`，落地后可手工细调）/ 自定义百分比（Other 输入如 `10%` 或 `0.1`，换算为 0.005-0.5 的小数）。说明：你能接受的复现值与原报告的偏差——自定义后**所有按相对偏差判定的指标统一用该容忍度**（绝对偏差/同号/数量级/定性判定语义不变），达标门禁与最终报告的 pass/partial 判定随之变化。

   - **经济模式**（header: 经济模式）：`关闭`（推荐首次使用——全 opus 质量优先）/ `开启`（机械性角色 extractor/verifier/oos-analyst 派发降为 sonnet，token 消耗约降三成；coder/auditor/diagnoser 等质量敏感角色不受影响）。

   > 外审档位 `audit_level`（strict|standard）不进问卷，默认 strict；需要降为 standard（spec/code 外审触发式、result 必跑）时直接编辑 `.reproduce.json` 或带 `--audit-level standard` 重跑本工具。
   > 未来新增配置项时同样遵守 4 问上限分批；两批答案合并后一次性传给步骤 3。

3. **落地骨架**（命令按 SKILL.md 二、工具定位协议展开）：
   ```
   uv run python tools/setup_workspace.py --target . --data-root "<答案1>" --mode <答案2> --max-iter <答案3|留空> --backtest-framework "<答案4|留空>" --max-rel-dev <答案5小数|留空> [--economy] [--audit-level strict|standard] [--force-config]
   ```
   - 重新配置时带 `--force-config`；保留现有配置时不带。
   - `--max-iter` 用户选「按难度自动」时留空；`--backtest-framework` 用户选「内置框架」时留空（省略该参数）；`--max-rel-dev` 用户选「按内置标准」时留空，自定义时把百分比换算为小数（10% → 0.1）。

4. **点收与转述**：核对命令输出——`.reproduce.json` 动作（created/kept/overwritten）、种子拷贝计数、pyproject 动作、目录树、环境检测三行。转述给用户时讲人话：
   - uv 缺失 → 给安装指引，明确这是硬前置；
   - Python 依赖缺失 → 指引在本目录运行 `uv sync`；
   - codex CLI 缺失 → 明示影响：「外部审查（codex 三审查点）将自动降级，最终报告可信度评级封顶 B；安装 codex CLI 后无需重新 setup，下次运行自动启用」。不阻塞。
   - 「插件侧较新」清单非空 → 列给用户，说明这些模板文件插件有更新但你本地已定制、未覆盖，需要的话手动对比同步。

5. **data_catalog 引导（关键一步，明确告知）**：`templates/data_catalog.md` 当前是模板/种子内容，描述的是维护者的数据清单；**用户必须按自己 data_root 下的实际数据维护它**——分诊阶段判断「研报需要的数据是否可得」完全依据此文件，写漏会被误判 missing、写多会引发运行期报错。给出维护建议：每张表一节，写明文件名、关键列、时间范围、已知口径注意事项（如财务数据必须用披露日 info_publ_date 对齐）。

6. **收尾打印**：
   - 快速开始：`/reproduce reports/<你的研报>.pdf` / `/reproduce status` / `/reproduce continue <id>`
   - 配置位置与改法：`.reproduce.json` 可直接编辑，或重跑 `/reproduce setup` 选「重新配置」。

## 失败处理

- `setup_workspace.py` 报错（参数校验 SystemExit）→ 把报错原样呈给用户，修正参数重跑。
- 目标目录无写权限 / 磁盘问题 → 呈报错误，不重试。
