"""内核就地执行的确定性动作：从 plan 播种状态、统计覆盖率、备料、迭代记账、报告装配等。

这些事原来由主会话照着执行卡手工做。这里的函数要么只读、要么只写内核自己负责的文件；
凡是改状态的都接收事务对象，由调用方统一提交。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

from tools import check_gates as cg
from tools import state as st

from . import mdslice as ms
from . import packs
from .core import MAX_ITER_BY_DIFFICULTY, PLUGIN_ROOT, Ctx, read_json, sha256_file, write_json, write_text

PDF_INDEX = "workspace/_registry/pdf_index.json"


# ---------------------------------------------------------------------------
# 文书里的机器生成块
# ---------------------------------------------------------------------------


def upsert_block(text: str, name: str, body: str) -> str:
    """插入或替换机器生成块：有同名块就整体替换；有占位行 `<!-- flow:block name -->` 就替换占位行；都没有就追加到文末。

    实现只有一份，在 precheck.upsert_block（预检要认同一套标记，生成块里的内容它不查）。
    """
    from . import precheck

    return precheck.upsert_block(text, name, body)


def comparison_digest(ctx: Ctx) -> Optional[str]:
    """对比结果里数值内容的指纹（只看各条指标的研报值、复现值与定性结论，不受排版和时间戳影响）。读不了返回 None。"""
    comparison = read_json(ctx.path(f"output/{ctx.report_id}/results/comparison.json"))
    if not isinstance(comparison, dict):
        return None
    rows = [[m.get("key"), m.get("report_value"), m.get("reproduced_value")] for m in comparison.get("metrics") or [] if isinstance(m, dict)]
    rows += [[q.get("key"), q.get("expect"), q.get("observed"), q.get("pass")] for q in comparison.get("qualitative") or [] if isinstance(q, dict)]
    text = json.dumps(sorted(rows, key=lambda r: str(r[0])), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def comparison_block(ctx: Ctx) -> str:
    """嵌进文书的指标对比块：达标计数一行（重算口径）加对比总表。文书里不再手写这两样。"""
    from . import precheck

    c = precheck.comparison_breakdown(ctx.root, ctx.report_id)
    total = precheck.comparison_counts(ctx.root, ctx.report_id)
    head = f"达标 {total.get('pass')} / {total.get('total')}（数值 {c.get('metrics_pass')}/{c.get('metrics_total')}"
    if c.get("metrics_na"):
        head += f"，其中不判定 {c['metrics_na']} 项"
    if c.get("qualitative_total"):
        head += f"；定性 {c.get('qualitative_pass')}/{c.get('qualitative_total')}"
    head += "）。内核按 templates/standards.json 重算，不采信文件自述。"
    return head + "\n\n" + precheck.comparison_table(ctx.root, ctx.report_id)


def save_precheck(ctx: Ctx, result: Any) -> str:
    """把一次预检的结果写成 audit/precheck_<阶段>.md，返回相对路径（人和修文书的角色都看它）。"""
    rel = f"{ctx.ws}/audit/precheck_{result.stage}.md"
    write_text(ctx.path(rel), f"# 结果一致性预检（{result.stage}）\n\n" + "\n".join(f"- {line}" if i else line for i, line in enumerate(result.render().splitlines())) + "\n")
    return rel


# ---------------------------------------------------------------------------
# init：PDF 指纹与撞库
# ---------------------------------------------------------------------------


def pdf_duplicates(root: Path, report_id: str, sha: Optional[str]) -> list[str]:
    """已有案例里用了同一份 PDF（内容哈希相同）的那些。顺手维护 workspace/_registry/pdf_index.json。"""
    if not sha:
        return []
    index_path = root / PDF_INDEX
    index = read_json(index_path) or {}
    index = index if isinstance(index, dict) else {}
    hits: list[str] = []
    for other in st.list_case_ids(root):
        if other == report_id:
            continue
        entry = index.get(other) if isinstance(index.get(other), dict) else {}
        try:
            other_state = st.load_state(root, other)
        except (ValueError, OSError):
            continue
        pdf = root / str(other_state.get("pdf_path") or "")
        stamp = [pdf.stat().st_size, int(pdf.stat().st_mtime)] if pdf.is_file() else None
        if entry.get("stamp") != stamp or not entry.get("sha"):
            entry = {"stamp": stamp, "sha": sha256_file(pdf) if stamp else None}
            index[other] = entry
        if entry.get("sha") == sha:
            hits.append(other)
    index[report_id] = {"stamp": None, "sha": sha}
    write_json(index_path, index)
    return hits


# ---------------------------------------------------------------------------
# plan：播种
# ---------------------------------------------------------------------------


def plan_frontmatter(ctx: Ctx) -> Optional[dict[str, Any]]:
    fm, _body = cg.parse_frontmatter(ctx.read(f"{ctx.ws}/plan.md"))
    return fm if isinstance(fm, dict) else None


def seed_plan(txn: st.Txn, ctx: Ctx) -> dict[str, Any]:
    """把 plan.md frontmatter 的分诊结论写进状态，并播种 milestone 列表（已有的子状态保留）。"""
    fm = plan_frontmatter(ctx)
    if fm is None:
        return {"ok": False, "reason": "plan.md 的 frontmatter 解析不出来"}
    state = txn.state
    changed: list[str] = []
    for key, allowed in (("type", st.TYPE_VALUES), ("difficulty", st.DIFFICULTY_VALUES), ("feasibility", st.FEASIBILITY_VALUES)):
        value = fm.get(key)
        if key == "difficulty" and state.get("difficulty_override") in allowed:
            value = state["difficulty_override"]  # 人工指定的难度优先于 planner 的判定；门禁读的也是这个字段
        if value in allowed and state.get(key) != value:
            st.set_in(txn, key, value)
            changed.append(key)
    tags = [str(t) for t in fm.get("tags") or [] if isinstance(t, (str, int))]
    if tags != (state.get("tags") or []):
        st.set_in(txn, "tags", tags)
        changed.append("tags")

    known = {m.get("id"): m for m in state.get("milestones") or [] if isinstance(m, dict)}
    seeded: list[dict[str, Any]] = []
    for item in fm.get("milestones") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        mid = str(item["id"])
        old = known.get(mid) or {}
        deps = item.get("deps") if isinstance(item.get("deps"), list) else []
        seeded.append(
            {
                "id": mid,
                "name": str(item.get("name") or old.get("name") or ""),
                "deps": [str(d) for d in deps],
                "implement": old.get("implement", "pending"),
                "code_review": old.get("code_review", "pending"),
                "verify": old.get("verify", "pending"),
            }
        )
    if seeded != (state.get("milestones") or []):
        st.set_in(txn, "milestones", seeded, log=False)
        txn.log("set:milestones", {"value": [m["id"] for m in seeded]})
        changed.append("milestones")

    difficulty = state.get("difficulty_override") or state.get("difficulty")
    max_iter = state.get("max_iter") or MAX_ITER_BY_DIFFICULTY.get(str(difficulty))
    if max_iter and (state.get("iteration") or {}).get("max") != max_iter:
        st.set_in(txn, "iteration.max", int(max_iter))
        if not state.get("max_iter"):
            st.set_in(txn, "max_iter", int(max_iter))
        changed.append("iteration.max")
    return {"ok": True, "changed": changed, "milestones": [m["id"] for m in seeded]}


def ambiguity_levels(ctx: Ctx) -> dict[str, list[str]]:
    """歧义清单里各等级的编号。"""
    out: dict[str, list[str]] = {}
    for block in cg.parse_id_blocks(ctx.read(f"{ctx.ws}/spec/ambiguities.md")):
        out.setdefault(str(block.fields.get("等级") or "").strip() or "未定", []).append(block.id)
    return out


def first_of_type(ctx: Ctx) -> bool:
    """这个类型是否还没有已收尾的案例（「type 首次完成」触发 spec 外审）。"""
    for other in st.list_case_ids(ctx.root):
        if other == ctx.report_id:
            continue
        try:
            state = st.load_state(ctx.root, other)
        except (ValueError, OSError):
            continue
        if state.get("type") == ctx.report_type and state.get("status") in ("done", "done_partial", "awaiting_review"):
            return False
    return True


# ---------------------------------------------------------------------------
# 覆盖率、指标达标数
# ---------------------------------------------------------------------------


def coverage_stats(ctx: Ctx) -> dict[str, int]:
    rows = cg.load_matrix_rows(ctx.path(f"{ctx.ws}/spec/coverage_matrix.md"))
    statuses = [cg._row_get(r, "状态") for r in rows]
    return {
        "total": len(rows),
        "done": statuses.count("done"),
        "skipped": statuses.count("skipped"),
        "infeasible": statuses.count("infeasible"),
        "pending": sum(s in ("pending", "in_progress", "") for s in statuses),
    }


def recalc(ctx: Ctx, comparison_rel: Optional[str] = None) -> dict[str, Any]:
    """按 standards.json 重算对比结果：达标数、总数、未过的指标。不采信文件自述的 pass。"""
    rel = comparison_rel or f"output/{ctx.report_id}/results/comparison.json"
    comparison = read_json(ctx.path(rel))
    result = cg.recalc_comparison(
        comparison if isinstance(comparison, dict) else None, cg.load_standards(ctx.root), ctx.report_type, ctx.experimental
    )
    judged = [m for m in result.metrics if m.passed is not None]
    passed = sum(m.passed is True for m in judged) + sum(bool(q.get("passed")) for q in result.qualitative)
    return {
        "ok": result.ok,
        "pass": passed,
        "total": len(judged) + len(result.qualitative),
        "fails": list(result.fails),
        "waived": list(result.waived),
        "available": isinstance(comparison, dict),
        "file": rel,
    }


def set_verdict(txn: st.Txn, ctx: Ctx, result: str, stats: dict[str, Any]) -> None:
    st.set_in(txn, "verdict.result", result)
    st.set_in(txn, "verdict.comparison_file", stats["file"])
    st.set_in(txn, "verdict.metrics_pass", stats["pass"])
    st.set_in(txn, "verdict.metrics_total", stats["total"])
    st.set_in(txn, "verdict.decided_at", st.now_iso(), log=False)


# ---------------------------------------------------------------------------
# code_audit：备料与静态预筛
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"(?<![\w.])-?\d+\.\d+%?|(?<![\w.])-?\d{2,}%")
# 源码里独立成词的数字（前后都不挨着字母、数字、下划线或小数点）。预筛用它把每行代码切成数字记号，
# 再去字面量表里查；不要反过来为每个字面量现编一条正则逐行去搜——r009 有三百多个字面量、
# 一万多行代码，那样要编几百万次正则，一步就得等上一分多钟。
# 回应表里的意见编号：CDX-S-01、CDX-C2-03、SA-A01、CA-A02、RA-A01、EXT-02 一类（整格就是编号）
_FINDING_ID_RE = r"^[A-Z]{2,5}(?:-[A-Z0-9]{1,5}){1,3}$"
_CODE_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
_DIRECT_READ_RE = re.compile(r"\bread_(parquet|csv|feather|excel|hdf|pickle)\s*\(")


def write_common_signatures(ctx: Ctx) -> str:
    """common/ 公共函数签名清单（外审与内审备料）。"""
    rel = f"{ctx.ws}/audit/common_signatures.md"
    lines = ["# common/ 公共函数签名", ""]
    common = ctx.root / "common"
    for path in sorted(common.glob("*.py")) if common.is_dir() else []:
        try:
            segments = packs.signature_segments(ctx.root, f"common/{path.name}")
        except (OSError, SyntaxError, ValueError):
            continue
        if not segments:
            continue
        lines += [f"## common/{path.name}", "", "```python"] + [seg.text.rstrip() for seg in segments] + ["```", ""]
    write_text(ctx.root / rel, "\n".join(lines) + "\n")
    return rel


def static_prescreen(ctx: Ctx) -> dict[str, Any]:
    """代码审计前的机器预筛，只作编排依据与外审备料，不生成审计意见：

    一，spec 里 R 类要素出现的数值字面量有没有原样出现在 src/ 里（疑似硬编码结果）；
    二，src/ 里有没有绕开 data_path() / read_table() 直接读数据文件的地方。
    """
    docs = packs.CaseDocs.load(ctx.root, ctx.report_id)
    src_dir = ctx.root / "src" / ctx.report_id
    sources = {
        str(p.relative_to(ctx.root)): p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(src_dir.rglob("*.py"))
        if "__pycache__" not in p.parts
    } if src_dir.is_dir() else {}
    literals: dict[str, set[str]] = {}
    for block in docs.spec_blocks:
        if block.prefix != "R":
            continue
        for number in _NUMBER_RE.findall(block.text):
            core = number.rstrip("%").lstrip("-")
            if len(core.replace(".", "")) >= 3:  # 太短的数（0.5、10%）到处都是，不查
                literals.setdefault(core, set()).add(block.id)
    hits: list[dict[str, Any]] = []
    direct_reads: list[dict[str, Any]] = []
    order = {literal: index for index, literal in enumerate(literals)}
    for rel, text in sources.items():
        for lineno, line in enumerate(text.splitlines(), 1):
            code = line.split("#", 1)[0]
            if literals and any(ch.isdigit() for ch in code):
                found = {token for token in _CODE_NUMBER_RE.findall(code) if token in literals}
                for literal in sorted(found, key=order.__getitem__):
                    hits.append({"file": rel, "line": lineno, "literal": literal, "elements": sorted(literals[literal]), "text": line.strip()[:120]})
            if _DIRECT_READ_RE.search(code):
                direct_reads.append({"file": rel, "line": lineno, "text": line.strip()[:120]})
    rel_out = f"{ctx.ws}/audit/static_prescreen.md"
    lines = [
        "# 代码审计前的机器预筛",
        "",
        "> 由内核生成，只列事实，不是审计意见。命中不等于有问题（参数里的阈值可能恰好与研报数值相同），由审计判断。",
        "",
        f"## R 类数值字面量在 src/ 的命中（{len(hits)} 处）",
        "",
    ]
    lines += [f"- `{h['file']}:{h['line']}` 出现 `{h['literal']}`（见于 {'、'.join(h['elements'])}）：`{h['text']}`" for h in hits[:200]] or ["（没有命中）"]
    lines += ["", f"## 直接读数据文件的地方（{len(direct_reads)} 处；新案例应经 `common.data_loader.data_path()` / `read_table()` 取数）", ""]
    lines += [f"- `{d['file']}:{d['line']}`：`{d['text']}`" for d in direct_reads[:200]] or ["（没有）"]
    write_text(ctx.root / rel_out, "\n".join(lines) + "\n")
    return {"file": rel_out, "literal_hits": len(hits), "direct_reads": len(direct_reads)}


# ---------------------------------------------------------------------------
# iterate
# ---------------------------------------------------------------------------

_CONCLUSION_RE = re.compile(r"结论[:：]\s*[*_`]*(continue|stop_partial|blocked)\b")


def iter_dir(ctx: Ctx, n: int) -> str:
    return f"{ctx.ws}/iterations/iter_{n:02d}"


def diagnosis_conclusion(ctx: Ctx, n: int) -> Optional[str]:
    matches = _CONCLUSION_RE.findall(ctx.read(f"{iter_dir(ctx, n)}/diagnosis.md"))
    return matches[-1] if matches else None


def snapshot_comparison(ctx: Ctx, n: int, before: bool = False) -> bool:
    """把当前的 comparison.json 拷进本轮目录（轮次开始时是修改前的结果，重跑验证后再覆盖成修改后的）。

    before=True 时另存一份 comparison_before.json：本轮修改前的结果，重跑验证后不覆盖，趋势表拿它当起点。
    """
    source = ctx.path(f"output/{ctx.report_id}/results/comparison.json")
    if not source.is_file():
        return False
    target = ctx.path(f"{iter_dir(ctx, n)}/comparison.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if before:
        shutil.copy2(source, target.with_name("comparison_before.json"))
    return True


# ---------------------------------------------------------------------------
# iterate：给诊断者的摘要（趋势表、改善不足预警、已排除假设原文）
# ---------------------------------------------------------------------------

DIGEST_NAME = "digest.md"
STALL_IMPROVEMENT = 0.10  # 同一指标连续两轮，偏差缩小不到这个比例算改善不足
_DIGEST_MAX_ROWS = 40
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _metric_snapshot(ctx: Ctx, rel: str) -> Optional[dict[str, dict[str, Any]]]:
    """一份 comparison.json 里每条指标重算后的偏差与是否达标；读不了返回 None。"""
    comparison = read_json(ctx.path(rel))
    if not isinstance(comparison, dict):
        return None
    result = cg.recalc_comparison(comparison, cg.load_standards(ctx.root), ctx.report_type, ctx.experimental)
    out: dict[str, dict[str, Any]] = {}
    for raw, item in zip(comparison.get("metrics") or [], result.metrics):
        if isinstance(raw, dict):
            out[str(item.key)] = {"dev": item.rel_dev, "passed": item.passed, "name": raw.get("name"), "report": raw.get("report_value"), "got": raw.get("reproduced_value")}
    return out


def iterate_trend(ctx: Ctx, n: int) -> dict[str, Any]:
    """第 n 轮开始时的指标趋势：基线（第 1 轮修改前）与此前各轮修改后的偏差。

    返回 {"labels": [列名], "rows": [{key, name, report, devs: [...], passed}], "stalled": [...]}。
    rows 只含至今仍未达标、或中途曾经未达标的指标。
    """
    columns: list[tuple[str, dict[str, dict[str, Any]]]] = []
    base = _metric_snapshot(ctx, f"{iter_dir(ctx, 1)}/comparison_before.json")
    if base is not None:
        columns.append(("基线", base))
    for k in range(1, n):
        snap = _metric_snapshot(ctx, f"{iter_dir(ctx, k)}/comparison.json")
        if snap is not None:
            columns.append((f"第 {k} 轮后", snap))
    if not columns:
        now = _metric_snapshot(ctx, f"output/{ctx.report_id}/results/comparison.json")
        if now is not None:
            columns.append(("现状", now))
    keys: list[str] = []
    for _label, snap in columns:
        keys += [k for k in snap if k not in keys]
    rows, stalled = [], []
    for key in keys:
        cells = [snap.get(key) for _label, snap in columns]
        if not any(c is not None and c.get("passed") is False for c in cells):
            continue
        devs = [abs(c["dev"]) if c is not None and isinstance(c.get("dev"), (int, float)) else None for c in cells]
        last = next((c for c in reversed(cells) if c is not None), {})
        rows.append({"key": key, "name": last.get("name"), "report": last.get("report"), "got": last.get("got"), "devs": devs, "passed": last.get("passed")})
        tail = [d for d in devs[-3:]]
        if last.get("passed") is False and len(tail) == 3 and all(d is not None and d > 0 for d in tail[:2]) and tail[2] is not None:
            if all(tail[i + 1] > tail[i] * (1 - STALL_IMPROVEMENT) for i in range(2)):
                stalled.append({"key": key, "devs": tail})
    return {"labels": [label for label, _snap in columns], "rows": rows, "stalled": stalled}


def _excluded_sections(ctx: Ctx, n: int) -> list[tuple[int, str]]:
    """历史各轮诊断里「已排除假设」一节的原文（逐字摘出，不改写）。"""
    out: list[tuple[int, str]] = []
    for k in range(1, n):
        text = ctx.read(f"{iter_dir(ctx, k)}/diagnosis.md")
        for match in _H2_RE.finditer(text):
            if "已排除假设" not in match.group(1):
                continue
            following = _H2_RE.search(text, match.end())
            body = text[match.end(): following.start() if following else len(text)].strip()
            if body:
                out.append((k, body))
    return out


def write_iterate_digest(ctx: Ctx, n: int) -> Optional[str]:
    """生成第 n 轮的诊断摘要 iter_NN/digest.md，返回相对路径；第 1 轮没有历史，不生成。"""
    if n < 2:
        return None
    trend = iterate_trend(ctx, n)

    def pct(value: Optional[float]) -> str:
        return "—" if value is None else f"{value * 100:.1f}%"

    lines = [
        f"# 第 {n} 轮诊断摘要（内核按机器产物与历史诊断原文生成）",
        "",
        "这是索引，不是结论：趋势表由各轮的 comparison.json 重算而来，「已排除假设」是历史诊断的原文摘录。与原文有出入时以原文为准。",
        "",
        "## 未达标指标的偏差趋势",
        "",
    ]
    if trend["rows"]:
        lines += ["| 指标 | 研报值 | " + " | ".join(trend["labels"]) + " | 现在 |", "| --- | --- | " + " | ".join("---" for _ in trend["labels"]) + " | --- |"]
        ordered = sorted(trend["rows"], key=lambda r: (r["passed"] is not False, -(r["devs"][-1] or 0)))
        for row in ordered[:_DIGEST_MAX_ROWS]:
            name = f"`{row['key']}`" + (f" {row['name']}" if row.get("name") else "")
            status = "已达标" if row["passed"] else ("未达标" if row["passed"] is False else "不判定")
            lines.append(f"| {name} | {row['report']} | " + " | ".join(pct(d) for d in row["devs"]) + f" | {status} |")
        if len(ordered) > _DIGEST_MAX_ROWS:
            lines.append(f"\n（另有 {len(ordered) - _DIGEST_MAX_ROWS} 条未列出，见各轮目录下的 comparison.json）")
        lines += ["", "表中数字是相对偏差的绝对值；「—」表示那一轮没有这条指标。"]
    else:
        lines.append("读不到可比的历史结果（各轮目录下没有 comparison.json）。")
    lines += ["", "## 改善不足预警", ""]
    if trend["stalled"]:
        lines += [f"- `{item['key']}`：连续两轮偏差缩小都不到 {STALL_IMPROVEMENT:.0%}（{' → '.join(pct(d) for d in item['devs'])}）。同一方向再改一轮之前，先确认归因没有兜圈。" for item in trend["stalled"]]
    else:
        lines.append("没有（没有指标连续两轮改善不足）。")
    lines += ["", "## 已排除假设（历史诊断原文）", ""]
    excluded = _excluded_sections(ctx, n)
    if excluded:
        for k, body in excluded:
            lines += [f"### 第 {k} 轮诊断里写的", "", body, ""]
    else:
        lines += ["此前各轮的诊断里没有「已排除假设」一节。", ""]
    lines += ["## 各轮做了什么", ""]
    for k in range(1, n):
        conclusion = diagnosis_conclusion(ctx, k) or "（没有找到结论行）"
        changes = next((ln.strip("-# ").strip() for ln in ctx.read(f"{iter_dir(ctx, k)}/changes.md").splitlines() if ln.strip() and not ln.startswith("# ")), "（没有改动摘要）")
        lines.append(f"- 第 {k} 轮：结论 {conclusion}；改动：{changes[:160]}。原文 `{iter_dir(ctx, k)}/diagnosis.md`")
    lines += ["", f"上一轮的诊断全文必读：`{iter_dir(ctx, n - 1)}/diagnosis.md`。", ""]
    rel = f"{iter_dir(ctx, n)}/{DIGEST_NAME}"
    write_text(ctx.path(rel), "\n".join(lines))
    return rel


def append_iteration_log(ctx: Ctx, n: int, row: dict[str, str]) -> str:
    rel = f"{ctx.ws}/iterations/iteration_log.md"
    path = ctx.root / rel
    header = (
        f"# iteration_log.md — {ctx.report_id} 迭代日志\n\n"
        "| 轮次 | 触发 | 失败指标(偏差) | 采纳假设/分支 | 修改摘要 | 结果(偏差变化) | 状态 |\n"
        "|------|------|---------------|--------------|---------|---------------|------|\n"
    )
    text = path.read_text(encoding="utf-8") if path.is_file() else header
    cells = [f"iter_{n:02d}"] + [str(row.get(k, "")).replace("|", "\\|").replace("\n", " ") for k in ("trigger", "fails", "hypothesis", "changes", "result", "status")]
    line = "| " + " | ".join(cells) + " |\n"
    marker = f"| iter_{n:02d} |"
    if marker in text:  # 同一轮重复记账时覆盖旧行
        text = "".join(line if ln.startswith(marker) else ln for ln in text.splitlines(keepends=True))
    else:
        text = text.rstrip("\n") + "\n" + line
    write_text(path, text)
    return rel


# ---------------------------------------------------------------------------
# verify：试跑检查
# ---------------------------------------------------------------------------


def trial_check(ctx: Ctx) -> dict[str, Any]:
    """mock 试跑只查三件事：跑得通、产物齐、指标都算得出。"""
    results = ctx.path(f"output/{ctx.report_id}/results_mock")
    run_log = results / "run_log.md"
    ran = run_log.is_file() and "exit=0" in run_log.read_text(encoding="utf-8", errors="replace")
    standards = cg.load_standards(ctx.root).get(ctx.report_type or "") or {}
    required = list(standards.get("required_charts") or []) + list(standards.get("required_excels") or []) + ["metrics.json"]
    missing = [name for name in required if not (results / name).is_file() or (results / name).stat().st_size == 0]
    metrics = read_json(results / "metrics.json")

    def _bad(value: Any) -> bool:
        return value is None or (isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))))

    def _walk(node: Any, trail: str) -> list[str]:
        if isinstance(node, dict):
            return [hit for k, v in node.items() for hit in _walk(v, f"{trail}.{k}" if trail else str(k))]
        if isinstance(node, list):
            return [hit for i, v in enumerate(node) for hit in _walk(v, f"{trail}[{i}]")]
        return [trail] if _bad(node) else []

    empty = _walk(metrics, "") if metrics is not None else ["metrics.json 读不出来"]
    manifest = read_json(results / "data_manifest.json") or {}
    mock_files = [f.get("name") for f in manifest.get("files") or [] if isinstance(f, dict) and f.get("source") == "mock"]
    return {
        "ran": ran,
        "missing": missing,
        "empty_metrics": empty[:50],
        "mock_files": mock_files,
        "ok": ran and not missing and not empty,
        "results_dir": f"output/{ctx.report_id}/results_mock",
    }


def real_manifest_mock_files(ctx: Ctx) -> list[str]:
    """真实结果目录的数据清单里出现的 mock 文件（不该有）。"""
    manifest = read_json(ctx.path(f"output/{ctx.report_id}/results/data_manifest.json")) or {}
    return [str(f.get("name")) for f in manifest.get("files") or [] if isinstance(f, dict) and f.get("source") == "mock"]


# ---------------------------------------------------------------------------
# report：装配
# ---------------------------------------------------------------------------


def _run_tool(ctx: Ctx, script: str, *args: str) -> tuple[bool, str]:
    env = dict(os.environ, REPORT_REPRODUCE_ROOT=str(ctx.root))
    proc = subprocess.run(
        [sys.executable, str(PLUGIN_ROOT / "tools" / script), *args], capture_output=True, text=True, env=env, cwd=str(ctx.root)
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
    return proc.returncode == 0, " / ".join(tail)


def assumptions_register(ctx: Ctx) -> str:
    """假设登记簿全文（原样拼进报告附录，由内核做，不占 reporter 的上下文）。"""
    text = ctx.read(f"{ctx.ws}/assumptions.md")
    blocks = [b for b in ms.parse_blocks(text) if b.prefix == "AS"]
    if not blocks:
        return "（假设登记簿为空）"
    # 报告里降一级标题，避免打乱报告自己的章节层级
    return "\n".join("####" + b.text.rstrip()[3:] if b.text.startswith("### ") else b.text.rstrip() for b in blocks)


def assumptions_stats(ctx: Ctx) -> dict[str, int]:
    blocks = [b for b in ms.parse_blocks(ctx.read(f"{ctx.ws}/assumptions.md")) if b.prefix == "AS"]
    statuses = [(b.field("状态").value.strip() if b.field("状态") else "") for b in blocks]
    return {"total": len(blocks), **{k: sum(s.startswith(k) for s in statuses) for k in ("assumed", "confirmed", "revised")}}


def report_digest(ctx: Ctx) -> str:
    """给 reporter 的摘要：机器生成的对比总表、外审台账、回应汇总、未复现清单。reporter 读它，不整读各份原件。"""
    lines = [f"# 报告素材摘要 · {ctx.report_id}", "", "> 由内核从机器产物生成。正文引用指标时写指标编号，不要重抄数值；对比总表和假设登记簿由内核嵌入报告。", ""]
    try:
        from . import precheck

        lines += ["## 指标对比总表（重算口径）", "", precheck.comparison_table(ctx.root, ctx.report_id), ""]
        counts = precheck.comparison_counts(ctx.root, ctx.report_id)
        lines += [f"达标 {counts.get('pass')} / {counts.get('total')}（未过 {counts.get('fail')}，不判定 {counts.get('na')}）", ""]
    except Exception as exc:  # noqa: BLE001 - 摘要缺一节不该挡住报告
        stats = recalc(ctx)
        lines += ["## 指标达标（重算口径）", "", f"达标 {stats['pass']} / {stats['total']}；未过：{'、'.join(stats['fails'][:30]) or '无'}（对比总表生成失败：{exc}）", ""]
    verdict = ctx.state.get("verdict") or {}
    lines += ["## 结论与覆盖率", "", f"- verdict：{verdict.get('result')}；覆盖率：{json.dumps(coverage_stats(ctx), ensure_ascii=False)}", ""]
    lines += ["## 外审台账", ""]
    lines += [
        f"- {r.get('checkpoint')}：引擎 {r.get('engine')}，结论 {r.get('verdict')}，critical {r.get('critical')} / major {r.get('major')} / minor {r.get('minor')}"
        for r in ctx.state.get("external_reviews") or []
        if isinstance(r, dict)
    ] or ["（没有外审记录）"]
    # 回应表里外审意见（CDX-…）和内审意见（SA-A01、CA-A02、RA-A01 一类）都有，摘要要与表逐行对得上
    rows = [(cg._row_id(r, _FINDING_ID_RE), r) for r in cg.parse_markdown_table_rows(ctx.read(f"{ctx.ws}/audit/audit_responses.md"))]
    rows = [(fid, r) for fid, r in rows if fid]
    external = sum(1 for fid, _r in rows if fid.startswith("CDX-"))
    lines += ["", f"## 审计回应汇总（共 {len(rows)} 条，其中外审意见 {external} 条、内审意见 {len(rows) - external} 条）", ""]
    lines += [
        f"- {fid}（{cg._row_get(r, 'severity')}，{cg._row_get(r, '处置') or '未处置'}）：{cg._row_get(r, '摘要')[:120]}" for fid, r in rows
    ] or ["（回应表里没有意见）"]
    rejected = [fid for fid, r in rows if cg._row_get(r, "处置") == "rejected"]
    lines += ["", f"rejected 的意见必须原样出现在报告里：{'、'.join(rejected) or '无'}", ""]
    matrix = cg.load_matrix_rows(ctx.path(f"{ctx.ws}/spec/coverage_matrix.md"))
    skipped = [r for r in matrix if cg._row_get(r, "状态") in ("skipped", "infeasible")]
    lines += [f"## 未复现清单（{len(skipped)} 项）", ""]
    lines += [f"- {cg._row_get(r, '要素ID')}（{cg._row_get(r, '优先级')}，{cg._row_get(r, '状态')}）：{cg._row_get(r, '状态理由')}" for r in skipped] or ["（全部要素都已复现）"]
    history = (ctx.state.get("iteration") or {}).get("history") or []
    # 旧版流程跑出来的案例（迁移或 fork 过来的）状态里往往没有逐轮记录，以磁盘上的诊断文书为准
    diagnosed = sorted(p.parent.name for p in ctx.path(f"{ctx.ws}/iterations").glob("iter_*/diagnosis.md"))
    if len(diagnosed) > len(history):
        lines += ["", f"## 迭代历史（状态里记了 {len(history)} 轮，磁盘上有 {len(diagnosed)} 轮的诊断文书，以文书为准）", ""]
        lines += [f"- {json.dumps(h, ensure_ascii=False)}" for h in history]
        lines += [f"- 诊断文书：`{ctx.ws}/iterations/{name}/diagnosis.md`" for name in diagnosed]
    else:
        lines += ["", f"## 迭代历史（{len(history)} 轮）", ""]
        lines += [f"- {json.dumps(h, ensure_ascii=False)}" for h in history] or ["（没有进入迭代）"]
    return "\n".join(lines) + "\n"


def assemble_report(ctx: Ctx) -> dict[str, Any]:
    """reporter 交稿之后：嵌入机器生成块、渲染结果页、导出假设表。"""
    rel = f"{ctx.ws}/final_report.md"
    path = ctx.root / rel
    notes: list[str] = []
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        try:
            text = upsert_block(text, "comparison_table", comparison_block(ctx))
        except Exception as exc:  # noqa: BLE001
            notes.append(f"对比总表没有嵌入：{exc}")
        text = upsert_block(text, "assumptions_register", assumptions_register(ctx))
        write_text(path, text)
    html_ok, html_note = _run_tool(ctx, "render_report.py", ctx.report_id)
    xlsx_ok, xlsx_note = _run_tool(ctx, "assumptions_xlsx.py", "export", ctx.report_id)
    if not html_ok:
        notes.append(f"结果页没有生成：{html_note}")
    if not xlsx_ok:
        notes.append(f"假设表没有导出：{xlsx_note}")
    return {"report": rel, "html": html_ok, "xlsx": xlsx_ok, "notes": notes, "assumptions": assumptions_stats(ctx)}


def load_plan_yaml(text: str) -> Optional[dict[str, Any]]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# 失效判定的两个基础量：包里各片的漂移、milestone 的代码指纹
# ---------------------------------------------------------------------------


# 内核合并回执时会改的矩阵列与假设字段：它们的变化不算「消费过的内容变了」
_VOLATILE_MATRIX_COLUMNS = ("状态", "实现位置", "验证结果", "最后更新")
_VOLATILE_ASSUMPTION_FIELDS = ("- 参数绑定", "- 状态", "- 验证后回看")


def stable_digests(pack: Any) -> dict[str, str]:
    """包里每个片的稳定指纹，键为「来源|种类|编号」。

    同一个编号可能由多段组成（口径卡一个字段一段），合起来算一个指纹。矩阵行只算 plan 定下的列，
    假设卡不算参数绑定、状态、回看——这几处由内核合并回执时改写，改了不代表上游变了。
    """
    import hashlib

    groups: dict[str, list[str]] = {}
    volatile: list[bool] = []
    for seg in pack.segments():
        text = seg.text
        if seg.kind == "matrix":
            cells = cg._split_row_cells(text.splitlines()[0]) if text.strip() else []
            if seg.key == "header":
                volatile = [any(word in name for word in _VOLATILE_MATRIX_COLUMNS) for name in cells]
            elif volatile and len(cells) == len(volatile):
                text = "|".join(cell for cell, skip in zip(cells, volatile) if not skip)
        elif seg.kind == "assumption_card" and text.lstrip().startswith(_VOLATILE_ASSUMPTION_FIELDS):
            continue
        groups.setdefault(f"{seg.source}|{seg.kind}|{seg.key}", []).append(text)
    return {key: hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:16] for key, parts in groups.items()}


def pack_drift(ctx: Ctx, manifest: Optional[dict[str, Any]], docs: Any = None) -> list[str]:
    """一步派发时消费的片，现在有哪些变了。按片比稳定指纹，不按整份文件。

    只看派发时已有的片：后来新增的要素、假设、函数不算。拼不出包或清单里没有指纹时返回空，不误报。
    """
    from . import packs

    pack = (manifest or {}).get("pack") or {}
    recorded = (manifest or {}).get("pack_stable") or {}
    if not recorded or not pack.get("role") or not pack.get("step"):
        return []
    try:
        docs = docs or packs.CaseDocs.load(ctx.root, ctx.report_id)
        now = stable_digests(packs.build_pack(docs, pack["role"], pack["step"]))
    except Exception:  # noqa: BLE001 - 文书被改坏时拼不出包，由门禁去报，这里不猜
        return []
    changed: list[str] = []
    for key, digest in recorded.items():
        _source, kind, name = (key.split("|", 2) + ["", ""])[:3]
        if kind == "matrix" and name == "header":
            continue
        if key not in now:
            changed.append(f"{kind}:{name}（已不在包里）")
        elif now[key] != digest:
            changed.append(f"{kind}:{name}")
    return sorted(set(changed))


_PY_FILE_RE = re.compile(r"[\w./-]+\.py")


def milestone_src_files(ctx: Ctx, milestone: str) -> dict[str, str]:
    """一个 milestone 的要素实现在哪些文件里（取自矩阵「实现位置」），以及各文件现在的内容指纹。"""
    from . import packs

    try:
        docs = packs.CaseDocs.load(ctx.root, ctx.report_id)
        wanted = set(docs.step_elements(milestone))
    except Exception:  # noqa: BLE001
        return {}
    rows = cg.load_matrix_rows(ctx.path(f"{ctx.ws}/spec/coverage_matrix.md"))
    out: dict[str, str] = {}
    for row in rows:
        if cg._row_get(row, "要素ID") not in wanted:
            continue
        for name in _PY_FILE_RE.findall(cg._row_get(row, "实现位置")):
            for rel in (name, f"{ctx.src}/{name}"):
                path = ctx.path(rel)
                if path.is_file():
                    out[rel] = (sha256_file(path) or "")[:16]
                    break
    return out


def src_files_drift(ctx: Ctx, recorded: Optional[dict[str, str]]) -> list[str]:
    """派发时记下的实现文件，现在有哪些内容变了或不在了。"""
    out = []
    for rel, sha in (recorded or {}).items():
        path = ctx.path(rel)
        if not path.is_file():
            out.append(f"{rel}（已不存在）")
        elif (sha256_file(path) or "")[:16] != sha:
            out.append(rel)
    return sorted(out)

