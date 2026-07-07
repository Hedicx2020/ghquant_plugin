# 研报复现系统（report_reproduce）

给定一份量化研报 PDF，按报告类型与难度自动分诊、复现策略代码与回测结果，产出与原文逐项对照、附可信度评级的最终报告。

## 快速开始

```bash
/reproduce reports/test.pdf --mode auto   # 新起一份复现（test 亦作为新流程验收用例）
/reproduce status                         # 查看全部案例状态摘要
```

其余子命令：`/reproduce continue <report_id>` 断点续跑；`/reproduce revise <report_id> ...` / `/reproduce accept <report_id>` 用于人工 review 闸门。

## 目录导航

| 路径 | 内容 |
|------|------|
| `docs/specs/2026-07-07-reproduce-v2-design.md` | v2 完整设计文档（状态机 / 门禁 / agent 契约 / 防偷懒审计体系） |
| `CLAUDE.md` | 编码与产出格式落地约定（命名 / Excel / 图表 / common 复用 / 数据对齐） |
| `.claude/skills/reproduce/` | `/reproduce` 主编排 SKILL.md + 11 张 stage 执行卡 |
| `.claude/agents/` | 7 个子 agent 定义 |
| `templates/` | 分诊、类型、审计模板 + `standards.json` 达标标准 |
| `tools/` | `state.py`（状态写入口）/ `check_gates.py`（门禁判定）/ `pdf_extract.py`（PDF 转文本） |
| `reports/{id}.pdf` | PDF 收件箱 |
| `workspace/{id}/` | 每份报告的管线文书（spec / plan / audit / iterations / final_report） |
| `src/{id}/`、`output/{id}/` | 策略代码与回测结果 |
| `docs/legacy/` | 已退役旧命令 / 旧 agent 的存档备份 |

## 已归档案例

`test`（新流程验收用例）、`momentum_factor`、`long_term_momentum` 三案例已用 `--legacy` 归档，详见对应 `workspace/{id}/state.json`。

## 变更记录

- 2026-07-08：内部修复——收紧 check_gates 的 G-IT 豁免正则（防结论行同行提及 stop_partial 被误判豁免），附正反测试；不影响使用方式。
