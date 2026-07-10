"""复现结果单文件 HTML 渲染器（report 阶段由主会话调用）。

读取结构化产物，确定性渲染为自包含 HTML（图表 base64 内嵌，离线可开可分享）：
    workspace/{id}/state.json          verdict / 覆盖率 / 迭代 / 外审台账
    output/{id}/results/comparison.json 指标对比总表（含归因）
    output/{id}/results/*.png          图表画廊（内嵌）
    output/{id}/results/oos_metrics.json 样本外表现（存在时）
    workspace/{id}/final_report.md     可信度评级提取 + 全文（简易渲染，折叠收录）
    workspace/{id}/assumptions.md      假设登记簿（简易渲染，折叠收录）

输出：output/{id}/final_report.html

设计约束：只读不写任何其他文件；缺失的可选输入按「节省略/占位说明」容错，
不因单个文件缺失而整体失败（comparison.json 与 state.json 为硬输入）。
本工具仅供主会话 / 测试调用；子 agent 不得导入。
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state import default_root  # noqa: E402


# ---------------------------------------------------------------------------
# 简易 markdown → HTML（标题/表格/粗体/行内代码/代码块/列表/段落，够用即可）
# ---------------------------------------------------------------------------


def _md_inline(text: str) -> str:
    out = html.escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out


def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            close_list()
            block: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            out.append("<pre>" + html.escape("\n".join(block)) + "</pre>")
            i += 1
            continue
        if "|" in line and line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            close_list()
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append("<div class='tbl-scroll'><table><tr>" + "".join(f"<th>{_md_inline(c)}</th>" for c in header) + "</tr>")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{_md_inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</table></div>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            close_list()
            level = min(len(m.group(1)) + 2, 5)  # 文内标题降两级，避免与页面 h2 冲突
            out.append(f"<h{level}>{_md_inline(m.group(2))}</h{level}>")
        elif re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + _md_inline(re.sub(r"^\s*[-*]\s+", "", line)) + "</li>")
        elif line.strip().startswith(">"):
            close_list()
            out.append("<blockquote>" + _md_inline(line.strip().lstrip("> ")) + "</blockquote>")
        elif line.strip():
            close_list()
            out.append("<p>" + _md_inline(line) + "</p>")
        else:
            close_list()
        i += 1
    close_list()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# 数据装配
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_text(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _fmt(v) -> str:
    """数值人读格式：float 保留 6 位有效并去尾零；其余原样。"""
    if isinstance(v, bool) or v is None:
        return html.escape(str(v))
    if isinstance(v, float):
        return f"{v:.6g}"
    return html.escape(str(v))


def _grade_from_report(final_md: str | None) -> str | None:
    if not final_md:
        return None
    m = re.search(r"可信度评级[^ABC]{0,24}([ABC])(?![A-Za-z])", final_md)
    return m.group(1) if m else None


def _png_gallery(results_dir: Path) -> list[tuple[str, str]]:
    """返回 [(文件名, dataURI)]，按文件名排序，单图 >8MB 跳过防爆体积。"""
    items: list[tuple[str, str]] = []
    if not results_dir.is_dir():
        return items
    for p in sorted(results_dir.glob("*.png")):
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if len(raw) > 8 * 1024 * 1024:
            continue
        items.append((p.name, "data:image/png;base64," + base64.b64encode(raw).decode("ascii")))
    return items


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

CSS = """
:root { --ink:#1a2332; --paper:#fbfbf9; --card:#fff; --accent:#1f77b4; --accent-deep:#14507a;
  --accent-wash:#eaf2f8; --pass:#2e7d4f; --pass-wash:#e8f3ec; --fail:#c0392b; --fail-wash:#faece9;
  --warn:#9a6b1f; --warn-wash:#f7f0e0; --line:#d8dde3; --dim:#5b6673; --code:#f1f4f7;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace; }
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Noto Sans SC","Microsoft YaHei",sans-serif;
  background:var(--paper);color:var(--ink);line-height:1.7;font-size:15px;}
main{max-width:1080px;margin:0 auto;padding:40px 36px 90px;}
h1{font-size:26px;font-weight:800;line-height:1.35;text-wrap:balance;}
h2{font-size:19px;font-weight:800;margin:52px 0 14px;padding-top:18px;border-top:1px solid var(--line);}
h3{font-size:15.5px;font-weight:700;margin:22px 0 8px;color:var(--accent-deep);}
h4,h5{font-size:14px;font-weight:700;margin:16px 0 6px;color:var(--accent-deep);}
p{margin:8px 0;max-width:78ch;} ul{margin:8px 0 8px 20px;} li{margin:3px 0;}
blockquote{border-left:3px solid var(--line);padding-left:12px;color:var(--dim);margin:8px 0;}
code{font-family:var(--mono);font-size:.86em;background:var(--code);border-radius:3px;padding:1px 5px;}
pre{background:#10202e;color:#dce8f2;border-radius:6px;padding:12px 16px;overflow-x:auto;margin:12px 0;font-size:13px;line-height:1.6;}
pre code{background:none;color:inherit;padding:0;}
.pill{display:inline-block;font-family:var(--mono);font-size:11px;letter-spacing:.06em;border-radius:999px;
  padding:1px 9px;vertical-align:1px;white-space:nowrap;}
.pill.pass{background:var(--pass-wash);color:var(--pass);border:1px solid #bcd9c6;}
.pill.fail{background:var(--fail-wash);color:var(--fail);border:1px solid #ecc4bc;}
.pill.gate{background:var(--accent-wash);color:var(--accent-deep);border:1px solid #c2d8ea;}
.pill.dim{background:#eef0f2;color:var(--dim);border:1px solid var(--line);}
.pill.warn{background:var(--warn-wash);color:var(--warn);border:1px solid #e3d3ac;}
.hero-meta{display:flex;gap:9px;flex-wrap:wrap;margin:14px 0 6px;align-items:center;}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0;}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:12px 14px;}
.kpi .k-label{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;color:var(--dim);text-transform:uppercase;}
.kpi .k-value{font-size:22px;font-weight:800;font-variant-numeric:tabular-nums;margin-top:2px;}
.kpi .k-sub{font-size:12px;color:var(--dim);}
.tbl-scroll{overflow-x:auto;margin:12px 0;}
table{border-collapse:collapse;width:100%;font-size:13.5px;}
th{text-align:left;font-weight:700;font-size:12px;color:var(--dim);letter-spacing:.04em;
  border-bottom:2px solid var(--ink);padding:6px 12px 6px 0;white-space:nowrap;}
td{border-bottom:1px solid var(--line);padding:6px 12px 6px 0;vertical-align:top;font-variant-numeric:tabular-nums;}
td:first-child,th:first-child{padding-left:2px;} tr:last-child td{border-bottom:none;}
tr.f-row{background:var(--fail-wash);}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:16px;margin:14px 0;}
.fig{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:10px;}
.fig img{max-width:100%;height:auto;display:block;}
.fig .cap{font-family:var(--mono);font-size:11.5px;color:var(--dim);margin-top:6px;}
details{border:1px solid var(--line);border-radius:6px;background:var(--card);margin:12px 0;}
summary{cursor:pointer;font-weight:700;font-size:14px;padding:11px 15px;}
details>div{padding:2px 16px 14px;}
.filter-bar{display:flex;gap:8px;margin:10px 0;align-items:center;font-size:13px;color:var(--dim);}
.filter-bar button{font:inherit;font-size:12.5px;padding:3px 12px;border-radius:999px;border:1px solid var(--line);
  background:var(--card);cursor:pointer;color:var(--ink);}
.filter-bar button.on{background:var(--accent-wash);border-color:var(--accent);color:var(--accent-deep);font-weight:700;}
.note{border-left:3px solid var(--accent);background:var(--accent-wash);padding:10px 14px;border-radius:0 6px 6px 0;
  margin:12px 0;font-size:13.5px;max-width:82ch;}
footer{margin-top:64px;padding-top:14px;border-top:1px solid var(--line);font-size:12.5px;color:var(--dim);
  display:flex;gap:16px;flex-wrap:wrap;}
@media(max-width:720px){main{padding:24px 16px 60px;} .gallery{grid-template-columns:1fr;}}
"""

FILTER_JS = """
function fl(mode, btn){
  document.querySelectorAll('#cmp tbody tr').forEach(function(tr){
    tr.style.display = (mode==='all' || tr.dataset.s===mode) ? '' : 'none';
  });
  document.querySelectorAll('.filter-bar button').forEach(function(b){b.classList.remove('on');});
  btn.classList.add('on');
}
"""


def render(root: Path, report_id: str) -> Path:
    ws = root / "workspace" / report_id
    res = root / "output" / report_id / "results"

    state = _read_json(ws / "state.json")
    comparison = _read_json(res / "comparison.json")
    if state is None:
        raise SystemExit(f"缺硬输入: {ws / 'state.json'}")
    if comparison is None:
        raise SystemExit(f"缺硬输入: {res / 'comparison.json'}")

    final_md = _read_text(ws / "final_report.md")
    assumptions_md = _read_text(ws / "assumptions.md")
    oos = _read_json(res / "oos_metrics.json")
    oos_md = _read_text(ws / "oos_report.md")

    verdict = state.get("verdict") or {}
    cov = state.get("coverage_stats") or {}
    it = state.get("iteration") or {}
    reviews = state.get("external_reviews") or []
    grade = _grade_from_report(final_md)

    result = verdict.get("result") or "?"
    result_pill = {"pass": "pass", "partial": "warn"}.get(result, "fail")
    metrics = comparison.get("metrics") or []
    pass_count = comparison.get("pass_count")
    total = comparison.get("total")

    B: list[str] = []
    esc = html.escape

    # ---- Hero ----
    B.append(f"<header><div style='font-family:var(--mono);font-size:11px;letter-spacing:.14em;color:var(--accent);text-transform:uppercase'>Reproduction Report · quant-report-reproduce</div>")
    B.append(f"<h1>复现结果报告：{esc(report_id)}</h1>")
    B.append("<div class='hero-meta'>")
    B.append(f"<span class='pill {result_pill}'>verdict: {esc(str(result))}</span>")
    if grade:
        gp = {"A": "pass", "B": "warn", "C": "fail"}.get(grade, "dim")
        B.append(f"<span class='pill {gp}'>可信度评级 {grade}</span>")
    if state.get("type"):
        B.append(f"<span class='pill dim'>{esc(str(state.get('type')))} · {esc(str(state.get('difficulty') or '-'))}</span>")
    B.append(f"<span class='pill dim'>生成于 {esc(str(state.get('updated_at') or ''))}</span>")
    B.append("</div>")

    # KPI 卡
    B.append("<div class='kpis'>")
    if pass_count is not None and total:
        B.append(f"<div class='kpi'><div class='k-label'>指标达标</div><div class='k-value'>{pass_count}/{total}</div><div class='k-sub'>comparison.json</div></div>")
    if cov.get("total"):
        B.append(f"<div class='kpi'><div class='k-label'>要素覆盖</div><div class='k-value'>{cov.get('done', 0)}/{cov['total']}</div><div class='k-sub'>skipped {cov.get('skipped', 0)} · infeasible {cov.get('infeasible', 0)}</div></div>")
    if it.get("current") is not None:
        B.append(f"<div class='kpi'><div class='k-label'>迭代轮次</div><div class='k-value'>{it.get('current', 0)}/{it.get('max') or '-'}</div><div class='k-sub'>自动修正</div></div>")
    if oos:
        B.append(f"<div class='kpi'><div class='k-label'>样本外结论</div><div class='k-value' style='font-size:18px'>{esc(str(oos.get('conclusion', '-')))}</div><div class='k-sub'>{esc(str(oos.get('oos_days', '-')))} 个交易日</div></div>")
    B.append("</div></header>")

    # ---- 指标对比总表 ----
    B.append("<section><h2>指标对比总表</h2>")
    B.append("<div class='filter-bar'>筛选："
             "<button class='on' onclick=\"fl('all',this)\">全部</button>"
             "<button onclick=\"fl('fail',this)\">仅未达标</button>"
             "<button onclick=\"fl('pass',this)\">仅达标</button></div>")
    B.append("<div class='tbl-scroll'><table id='cmp'><thead><tr>"
             "<th>指标</th><th>研报值</th><th>复现值</th><th>相对偏差</th><th>状态</th><th>归因</th></tr></thead><tbody>")
    for m in metrics:
        p = m.get("pass")
        s = "pass" if p is True else "fail"
        row_cls = "" if p is True else " class='f-row'"
        rep_v = m.get("report_value", m.get("expect", ""))
        rec_v = m.get("reproduced_value", m.get("observed", ""))
        rel = m.get("rel_dev")
        rel_s = f"{rel:.2%}" if isinstance(rel, (int, float)) and not isinstance(rel, bool) else "-"
        att = m.get("attribution_status") or ""
        note = m.get("attribution_note") or ""
        att_cell = f"<span class='pill dim'>{esc(att)}</span> {esc(note[:80])}" if att else ""
        B.append(f"<tr{row_cls} data-s='{s}'><td><code>{esc(str(m.get('key', '?')))}</code></td>"
                 f"<td>{_fmt(rep_v)}</td><td>{_fmt(rec_v)}</td><td>{rel_s}</td>"
                 f"<td><span class='pill {s}'>{'PASS' if p is True else 'FAIL'}</span></td><td>{att_cell}</td></tr>")
    B.append("</tbody></table></div></section>")

    # ---- 图表画廊 ----
    gallery = _png_gallery(res)
    B.append("<section><h2>图表</h2>")
    if gallery:
        B.append("<div class='gallery'>")
        for name, uri in gallery:
            B.append(f"<figure class='fig'><img src='{uri}' alt='{esc(name)}' loading='lazy'><figcaption class='cap'>{esc(name)}</figcaption></figure>")
        B.append("</div>")
    else:
        B.append("<p class='note'>本目录下未找到 PNG 图表（可能已被清理；可复跑 main.py 重建后重新渲染）。</p>")
    B.append("</section>")

    # ---- 样本外表现 ----
    if oos:
        B.append("<section><h2>样本外表现</h2>")
        B.append(f"<p>样本内截至 <code>{esc(str(oos.get('in_sample_end', '-')))}</code>，样本外区间 "
                 f"<code>{esc(str(oos.get('oos_start', '-')))} ~ {esc(str(oos.get('oos_end', '-')))}</code>"
                 f"（{esc(str(oos.get('oos_days', '-')))} 个交易日），基线 {esc(str(oos.get('baseline', '-')))}，"
                 f"结论：<strong>{esc(str(oos.get('conclusion', '-')))}</strong></p>")
        om = oos.get("metrics") or []
        if om:
            B.append("<div class='tbl-scroll'><table><tr><th>指标</th><th>样本内</th><th>样本外</th><th>变化</th></tr>")
            for m in om:
                B.append(f"<tr><td><code>{esc(str(m.get('key', '?')))}</code></td><td>{_fmt(m.get('in_sample_value'))}</td>"
                         f"<td>{_fmt(m.get('oos_value'))}</td><td>{_fmt(m.get('change'))}</td></tr>")
            B.append("</table></div>")
        if oos_md:
            B.append(f"<details><summary>样本外分析全文（oos_report.md）</summary><div>{md_to_html(oos_md)}</div></details>")
        B.append("</section>")

    # ---- 审计台账 ----
    if reviews:
        B.append("<section><h2>外部审查台账</h2><div class='tbl-scroll'><table><tr><th>审查点</th><th>引擎</th><th>结论</th><th>critical</th><th>major</th><th>minor</th></tr>")
        for r in reviews:
            v = str(r.get("verdict", "-"))
            vp = "pass" if v.startswith("pass") else ("fail" if v == "fail" else "dim")
            B.append(f"<tr><td><code>{esc(str(r.get('checkpoint', '-')))}</code></td><td>{esc(str(r.get('engine', '-')))}</td>"
                     f"<td><span class='pill {vp}'>{esc(v)}</span></td>"
                     f"<td>{r.get('critical', 0)}</td><td>{r.get('major', 0)}</td><td>{r.get('minor', 0)}</td></tr>")
        B.append("</table></div><p class='note'>fail 结论代表该审查点曾抓出 critical 问题——按协议均已修复并经缩减复审通过后才可能走到本报告（详见 audit_responses.md）。</p></section>")

    # ---- 假设登记簿 / 最终报告全文（折叠收录） ----
    B.append("<section><h2>文书收录</h2>")
    if assumptions_md:
        B.append(f"<details><summary>假设登记簿（assumptions.md 全文）</summary><div>{md_to_html(assumptions_md)}</div></details>")
    if final_md:
        B.append(f"<details><summary>最终复现报告（final_report.md 全文）</summary><div>{md_to_html(final_md)}</div></details>")
    if not assumptions_md and not final_md:
        B.append("<p class='note'>未找到 assumptions.md / final_report.md。</p>")
    B.append("</section>")

    B.append(f"<footer><span>report_id: <code>{esc(report_id)}</code></span>"
             f"<span>verdict: {esc(str(result))}{' · 评级 ' + grade if grade else ''}</span>"
             f"<span>quant-report-reproduce</span></footer>")

    doc = (f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>复现结果：{esc(report_id)}</title><style>{CSS}</style>"
           f"<script>{FILTER_JS}</script></head><body><main>" + "\n".join(B) + "</main></body></html>")

    out = root / "output" / report_id / "final_report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="复现结果单文件 HTML 渲染（确定性，幂等可重跑）")
    parser.add_argument("report_id")
    args = parser.parse_args(argv)
    out = render(default_root(), args.report_id)
    print(f"已渲染: {out} ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
