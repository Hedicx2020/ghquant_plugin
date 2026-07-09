# stage: init（主会话 + tools）

初始化 workspace 骨架、state.json、PDF 转文本。本 stage 由主会话直接跑工具完成，不派子 agent。

## 入口条件

- 新跑触发（`/reproduce <pdf_path> ...`）。
- `<pdf_path>` 指向的 PDF 文件存在（先 `ls -la <pdf_path>` 确认；不存在则直接报错停止）。
- 首阶段，无前置断言。

## 动作序列

1. **定 id**：`--id` 给定则用之；否则由 PDF 文件名取 snake_case（如 `reports/xxx_timing.pdf` → `xxx_timing`）。
2. **初始化 state 与目录骨架**（自动创建 `workspace/<id>/{spec,audit,iterations}`、`output/<id>/results`、`src/<id>`）：
   ```
   uv run python tools/state.py init <id> --pdf <pdf_path> [--mode auto|interactive] [--max-iter N]
   ```
3. **状态先行**：`uv run python tools/state.py set-stage <id> init running`
4. **PDF 转文本**（出 `report_text.md` + `tables_extracted.md` 到 spec 目录）：
   ```
   uv run python tools/pdf_extract.py <pdf_path> workspace/<id>/spec
   ```
   记录 stdout 报告的物理页数 `n_pages`。
5. **回填页数**（G-IN-5 用它核对 PAGE 标记数）：`uv run python tools/state.py set <id> pdf_pages <n_pages>`
6. **难度覆盖**（仅当启动带 `--difficulty <d>`）：`uv run python tools/state.py set <id> difficulty_override <d>`

## 出口门禁

```
uv run python tools/check_gates.py <id> --stage init --record
```
把完整输出原样贴进回复。G-IN 逐条：
- G-IN-1 state schema 合法
- G-IN-2 目录树齐全（workspace spec/audit/iterations + output/results + src）
- G-IN-3 report_text.md 存在
- G-IN-4 PAGE 标记数 ≥ 1
- G-IN-5 PAGE 标记数 == PDF 页数（== state.pdf_pages）
- G-IN-6 tables_extracted.md 存在

VERDICT PASS → `set-stage <id> init done`，随后**打印可复制的 /goal 无人值守命令**（见 SKILL.md 第七节），再进入 extract。

## 失败处理

- **PDF 不可解析**（`pdf_extract` 非零退出：无法打开/页数为 0）→ 终止：`set <id> status aborted` + `record-event <id> pdf_unparseable`，说明 PDF 损坏，请人工换文件。
- **G-IN-5 页数不一致**（`pdftotext` 与 pypdf 分页差异）→ 重跑 `pdf_extract`；仍不一致则核对 `pdf_pages` 是否为真实物理页数后重设。
- 其它 FAIL（目录缺失/schema）→ 重跑对应工具步骤覆盖写。
