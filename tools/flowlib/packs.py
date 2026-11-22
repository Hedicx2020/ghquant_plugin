"""上下文包：按「角色 × 步骤」从原始文书切出任务文件正文。

包里的每个片（Segment）都是原始文件的一段连续文本，带来源路径、起止偏移和内容哈希；
小节标题、路径清单这类说明文字（Chrome）由内核生成，不冒充原文。原始文书始终是权威，
包头写明「冲突以原文为准」。

本批（批次 A）只做影子包：拼出来、记字节、做 lint，不投喂给任何 agent。
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Optional, Union

import yaml

from . import mdslice as ms

PACK_FORMAT = "flow-pack v1"

# 口径卡包含的字段（按原文顺序取用）
CARD_FIELDS = ("假设内容", "参数绑定", "影响面", "影响 milestone", "影响指标", "状态")
# 承载「新口径」的字段：取文中最后一条
REVISION_PREFIXES = ("修订", "最终裁决", "处置记录")
# 引用闭包只看这些字段
CLOSURE_FIELD_PREFIXES = ("依赖数据", "公式", "参数")
# 口径卡省略的字段（按前缀）：出处与依据、预期与回看这类叙述，以及更早的修订记录。
# 不在这两张表里的字段一律原样带入口径卡——它们可能就是口径本身（如逐项近似的说明）。
CARD_OMIT_PREFIXES = ("来源", "行业惯例依据", "预期影响", "验证后回看", "本轮", "高亮等级", "性质", "显著声明")

ROLE_CN = {
    "coder": "编码",
    "auditor_code": "实现审计",
    "verifier": "验证",
    "auditor_result": "结果审计",
}
MILESTONE_ROLES = ("coder", "auditor_code", "verifier")
FINAL_ROLES = ("verifier", "auditor_result")
FINAL_STEP = "final"

_ELEMENT_ID_RE = re.compile(r"^(D|F|B|R|SA)\d+(\.\d+)?$")
_SRC_PATH_RE = re.compile(r"((?:src|common)/[\w./-]+?\.py)")
_BARE_PY_RE = re.compile(r"(?<![\w/.-])([\w-]+\.py)")


class PackError(ValueError):
    """这一步拼不出包（缺文书、步骤不存在等）。"""


# ---------------------------------------------------------------------------
# 片与包
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    source: str  # 相对工作区根的路径
    start: int
    end: int
    text: str
    kind: str  # element / element_index / assumption_card / assumption_index / matrix / plan / template / standards / signature
    key: str

    @property
    def sha(self) -> str:
        return ms.slice_hash(self.text)

    @property
    def nbytes(self) -> int:
        return len(self.text.encode("utf-8"))


@dataclass(frozen=True)
class Chrome:
    """内核生成的说明文字（包头、小节标题、清单）。"""

    text: str


Part = Union[Segment, Chrome]


@dataclass
class Pack:
    report_id: str
    role: str
    step: str
    parts: list[Part] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)  # 来源文件 → 文件哈希
    full_contract: dict[str, int] = field(default_factory=dict)  # 现行合同整读的文件 → 字节数
    summary: dict[str, Any] = field(default_factory=dict)

    def segments(self) -> list[Segment]:
        return [p for p in self.parts if isinstance(p, Segment)]

    def render(self) -> str:
        out: list[str] = []
        for part in self.parts:
            text = part.text
            out.append(text if text.endswith("\n") else text + "\n")
        return "".join(out)

    @property
    def nbytes(self) -> int:
        return len(self.render().encode("utf-8"))

    @property
    def full_bytes(self) -> int:
        return sum(self.full_contract.values())

    def bytes_by_kind(self) -> dict[str, int]:
        sizes: dict[str, int] = {}
        for part in self.parts:
            kind = part.kind if isinstance(part, Segment) else "chrome"
            sizes[kind] = sizes.get(kind, 0) + len(part.text.encode("utf-8"))
        return sizes

    def manifest(self) -> dict[str, Any]:
        """包的清单：消费了哪些片、各片的哈希。失效判定按片比对，不按整份文件。"""
        return {
            "format": PACK_FORMAT,
            "report_id": self.report_id,
            "role": self.role,
            "step": self.step,
            "bytes": self.nbytes,
            "full_contract_bytes": self.full_bytes,
            "sources": dict(self.sources),
            "segments": [
                {"source": s.source, "kind": s.kind, "key": s.key, "start": s.start, "end": s.end, "sha": s.sha}
                for s in self.segments()
            ],
            "bytes_by_kind": self.bytes_by_kind(),
            "warnings": list(self.warnings),
            "summary": dict(self.summary),
        }


# ---------------------------------------------------------------------------
# 案例文书
# ---------------------------------------------------------------------------


@dataclass
class Doc:
    rel: str
    path: Path
    text: str

    @property
    def nbytes(self) -> int:
        return len(self.text.encode("utf-8"))

    def segment(self, start: int, end: int, kind: str, key: str) -> Segment:
        return Segment(self.rel, start, end, self.text[start:end], kind, key)

    def whole(self, kind: str, key: str) -> Segment:
        return self.segment(0, len(self.text), kind, key)


def _load_doc(root: Path, rel: str) -> Optional[Doc]:
    path = root / rel
    if not path.is_file():
        return None
    return Doc(rel, path, ms.read_source(path))


@dataclass
class CaseDocs:
    root: Path
    report_id: str
    state: dict[str, Any]
    spec: Optional[Doc]
    assumptions: Optional[Doc]
    matrix: Optional[Doc]
    plan: Optional[Doc]
    ambiguities: Optional[Doc]
    spec_blocks: list[ms.Block] = field(default_factory=list)
    assumption_blocks: list[ms.Block] = field(default_factory=list)
    matrix_rows: list[ms.TableRow] = field(default_factory=list)
    plan_fm: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path, report_id: str) -> "CaseDocs":
        ws = f"workspace/{report_id}"
        state_path = root / ws / "state.json"
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
        except ValueError:
            state = {}
        docs = cls(
            root=root,
            report_id=report_id,
            state=state if isinstance(state, dict) else {},
            spec=_load_doc(root, f"{ws}/spec/spec.md"),
            assumptions=_load_doc(root, f"{ws}/assumptions.md"),
            matrix=_load_doc(root, f"{ws}/spec/coverage_matrix.md"),
            plan=_load_doc(root, f"{ws}/plan.md"),
            ambiguities=_load_doc(root, f"{ws}/spec/ambiguities.md"),
        )
        if docs.spec:
            docs.spec_blocks = [b for b in ms.parse_blocks(docs.spec.text) if _ELEMENT_ID_RE.match(b.id)]
        if docs.assumptions:
            docs.assumption_blocks = [b for b in ms.parse_blocks(docs.assumptions.text) if b.prefix == "AS"]
        if docs.matrix:
            docs.matrix_rows = [
                r for r in ms.parse_table_rows(docs.matrix.text) if _ELEMENT_ID_RE.match(ms.row_get(r.cells, "要素ID"))
            ]
        if docs.plan:
            span = ms.frontmatter_span(docs.plan.text)
            if span:
                inner = docs.plan.text[span[0]:span[1]]
                body = re.sub(r"\A---[ \t]*\r?\n", "", inner)
                body = re.sub(r"\r?\n---[ \t]*(?:\r?\n|\Z)\Z", "", body)
                try:
                    data = yaml.safe_load(body)
                except yaml.YAMLError:
                    data = None
                if isinstance(data, dict):
                    docs.plan_fm = data
        return docs

    # ---- 基本查询 ----

    @property
    def report_type(self) -> Optional[str]:
        return self.plan_fm.get("type") or self.state.get("type")

    def element(self, element_id: str) -> Optional[ms.Block]:
        for b in self.spec_blocks:
            if b.id == element_id:
                return b
        return None

    def assumption(self, assumption_id: str) -> Optional[ms.Block]:
        for b in self.assumption_blocks:
            if b.id == assumption_id:
                return b
        return None

    def matrix_row(self, element_id: str) -> Optional[ms.TableRow]:
        for r in self.matrix_rows:
            if ms.row_get(r.cells, "要素ID") == element_id:
                return r
        return None

    def plan_milestones(self) -> list[dict[str, Any]]:
        items = self.plan_fm.get("milestones")
        return [m for m in items if isinstance(m, dict) and m.get("id")] if isinstance(items, list) else []

    def milestone_ids(self) -> list[str]:
        ids = [str(m["id"]) for m in self.plan_milestones()]
        if not ids:
            ids = [str(m.get("id")) for m in self.state.get("milestones") or [] if isinstance(m, dict) and m.get("id")]
        if not ids:
            seen: list[str] = []
            for r in self.matrix_rows:
                for m in ms.extract_milestones(ms.row_get(r.cells, "milestone")):
                    if m not in seen:
                        seen.append(m)
            ids = sorted(seen, key=lambda x: int(x[1:]))
        return ids

    def milestone_deps(self, milestone: str) -> list[str]:
        for m in self.plan_milestones():
            if str(m["id"]) == milestone:
                deps = m.get("deps") or []
                return [str(d) for d in deps] if isinstance(deps, list) else []
        for m in self.state.get("milestones") or []:
            if isinstance(m, dict) and m.get("id") == milestone:
                return [str(d) for d in m.get("deps") or []]
        return []

    def matrix_elements(self, milestone: str) -> list[str]:
        return [
            ms.row_get(r.cells, "要素ID")
            for r in self.matrix_rows
            if milestone in ms.extract_milestones(ms.row_get(r.cells, "milestone"))
        ]

    def plan_elements(self, milestone: str) -> list[str]:
        for m in self.plan_milestones():
            if str(m["id"]) == milestone:
                elements = m.get("elements") or []
                return [str(e) for e in elements] if isinstance(elements, list) else []
        return []

    def step_elements(self, milestone: str) -> list[str]:
        """本步要素 = 矩阵 milestone 列与 plan elements 的并集，按 spec 里的出现顺序排。"""
        wanted = set(self.matrix_elements(milestone)) | set(self.plan_elements(milestone))
        ordered = [b.id for b in self.spec_blocks if b.id in wanted]
        return ordered + sorted(wanted - set(ordered))  # spec 里找不到的排在最后，交给 lint 报

    # ---- 假设归属 ----

    def assumption_primary_milestones(self, block: ms.Block) -> list[str]:
        """「影响 milestone」里首个括号之前写的 mN；写了「不影响」的子句不算。"""
        fld = block.field("影响 milestone")
        if not fld:
            return []
        head = re.split(r"[（(]", fld.value, maxsplit=1)[0]
        head = re.sub(r"不影响[^；;，,。]*", "", head)
        return ms.extract_milestones(head)

    def assumption_explicit_none(self, block: ms.Block) -> bool:
        fld = block.field("影响 milestone")
        return bool(fld and "不影响" in fld.value and not self.assumption_primary_milestones(block))

    def assumption_metric_refs(self, block: ms.Block) -> list[str]:
        fld = block.field("影响指标")
        return ms.extract_refs(fld.value) if fld else []

    def assumption_owners(self, block: ms.Block) -> list[str]:
        """这条假设归属的 milestone：主归属，并上「影响指标」命中其要素的。"""
        owners = list(self.assumption_primary_milestones(block))
        refs = set(self.assumption_metric_refs(block))
        if refs:
            for m in self.milestone_ids():
                if m not in owners and refs & set(self.step_elements(m)):
                    owners.append(m)
        return owners


# ---------------------------------------------------------------------------
# 片的构造
# ---------------------------------------------------------------------------


def _element_full(docs: CaseDocs, block: ms.Block) -> Segment:
    return docs.spec.segment(block.start, block.end, "element", block.id)


def _element_index(docs: CaseDocs, block: ms.Block) -> Segment:
    return docs.spec.segment(block.start, block.heading_end, "element_index", block.id)


def _assumption_index(docs: CaseDocs, block: ms.Block) -> Segment:
    return docs.assumptions.segment(block.start, block.heading_end, "assumption_index", block.id)


def is_known_assumption_field(name: str) -> bool:
    return name in CARD_FIELDS or name.startswith(REVISION_PREFIXES) or name.startswith(CARD_OMIT_PREFIXES)


def card_fields(block: ms.Block, extra: Iterable[str] = ()) -> list[ms.FieldSlice]:
    """口径卡取用的字段。

    固定几项，加上文中最后一条修订类记录（新口径往往只写在那里），再加上未识别的字段。
    """
    wanted = set(CARD_FIELDS) | set(extra)
    chosen = [f for f in block.fields if f.name in wanted or not is_known_assumption_field(f.name)]
    revisions = [f for f in block.fields if f.name.startswith(REVISION_PREFIXES)]
    if revisions and revisions[-1] not in chosen:
        chosen.append(revisions[-1])
    return sorted(chosen, key=lambda f: f.start)


def _assumption_card(docs: CaseDocs, block: ms.Block, extra: Iterable[str] = ()) -> list[Part]:
    doc = docs.assumptions
    if block.field("假设内容") is None:
        # 没按模板写「假设内容」的条目切不出口径卡，整块带上，宁多勿漏
        whole = doc.segment(block.start, block.end, "assumption_card", block.id)
        return [whole] if whole.text.endswith("\n\n") else [whole, Chrome("\n")]
    parts: list[Part] = [doc.segment(block.start, block.heading_end, "assumption_card", block.id)]
    for f in card_fields(block, extra):
        parts.append(doc.segment(f.start, f.end, "assumption_card", block.id))
    parts.append(Chrome("\n"))
    return parts


def _matrix_rows(docs: CaseDocs, element_ids: Iterable[str]) -> list[Part]:
    wanted = set(element_ids)
    parts: list[Part] = []
    last_header: Optional[int] = None
    for row in docs.matrix_rows:
        if ms.row_get(row.cells, "要素ID") not in wanted:
            continue
        if row.header_start != last_header:  # 每张表的表头只带一次
            parts.append(docs.matrix.segment(row.header_start, row.header_end, "matrix", "header"))
            last_header = row.header_start
        parts.append(docs.matrix.segment(row.start, row.end, "matrix", ms.row_get(row.cells, "要素ID")))
    return parts


def _plan_parts(docs: CaseDocs, milestone: str) -> tuple[list[Part], list[str]]:
    """plan 里这一步的段落，加上「回测参数」一节。"""
    parts: list[Part] = []
    warnings: list[str] = []
    text = docs.plan.text
    secs = ms.sections(text)
    step_re = re.compile(rf"^{re.escape(milestone)}(?![0-9A-Za-z_])")
    step_secs = [s for s in secs if step_re.match(s.title.strip())]
    if step_secs:
        s = step_secs[0]
        parts.append(docs.plan.segment(s.start, s.end, "plan", milestone))
    else:
        warnings.append(f"plan.md 里没有以「{milestone}」开头的小节")
    param_secs = [s for s in secs if s.level == 2 and "回测参数" in s.title]
    if param_secs:
        s = param_secs[0]
        parts.append(docs.plan.segment(s.start, s.end, "plan", "回测参数"))
    else:
        warnings.append("plan.md 里没有标题含「回测参数」的二级小节")
    return parts, warnings


def signature_segments(root: Path, rel: str) -> list[Segment]:
    """一个 Python 文件里公开函数、类、方法的签名：def 行起，到文档串首行止。"""
    path = root / rel
    if not path.is_file():
        return []
    text = ms.read_source(path)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    spans: list[tuple[int, int, str]] = []

    def visit(nodes: list[ast.stmt], owner: str = "") -> None:
        for node in nodes:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.name.startswith("_") and node.name != "__init__":
                continue
            first = node.body[0]
            last_line = node.lineno if first.lineno <= node.lineno else first.lineno - 1
            is_doc = isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str)
            if is_doc and first.lineno > node.lineno:
                last_line = first.lineno
                opener = lines[first.lineno - 1].strip().strip("rRbBuU").strip("\"'")
                if not opener and first.end_lineno and first.end_lineno > first.lineno:
                    last_line = first.lineno + 1  # 文档串首行只有引号时，带上下一行的摘要
            spans.append((node.lineno - 1, min(last_line, len(lines)), f"{owner}{node.name}"))
            if isinstance(node, ast.ClassDef):
                visit(node.body, f"{owner}{node.name}.")

    visit(tree.body)
    return [Segment(rel, offsets[a], offsets[b], text[offsets[a]:offsets[b]], "signature", name) for a, b, name in spans]


def _impl_files(docs: CaseDocs, milestones: Iterable[str]) -> list[str]:
    """矩阵「实现位置」列里，属于指定 milestone 的源码文件（相对工作区根）。"""
    wanted = set(milestones)
    files: list[str] = []
    for row in docs.matrix_rows:
        if not wanted & set(ms.extract_milestones(ms.row_get(row.cells, "milestone"))):
            continue
        location = ms.row_get(row.cells, "实现位置")
        candidates = _SRC_PATH_RE.findall(location)
        for bare in _BARE_PY_RE.findall(location):
            candidates.append(f"src/{docs.report_id}/{bare}")
        for rel in candidates:
            if rel not in files and (docs.root / rel).is_file():
                files.append(rel)
    return files


# 所有类型都会用到的公共模块；其余按报告类型、类型模板点名和上游代码的实际导入来取
BASE_COMMON_MODULES = ("utils", "data_loader", "backtest")
_COMMON_IMPORT_RE = re.compile(r"^\s*(?:from\s+common\.(\w+)\s+import|import\s+common\.(\w+)|from\s+common\s+import\s+([\w, ]+))", re.MULTILINE)
_COMMON_MENTION_RE = re.compile(r"common/(\w+)\.py")


def _common_modules(docs: CaseDocs, upstream_files: Iterable[str]) -> list[str]:
    """这一步的 coder 需要看签名的公共模块（相对工作区根的路径）。

    不把 common/ 整个列出来：机器学习引擎的签名对择时案例没有用。取四处的并集：
    通用三件、common/{类型}_*.py、类型模板里点名的模块、上游代码实际导入的模块。
    """
    common = docs.root / "common"
    if not common.is_dir():
        return []
    names = set(BASE_COMMON_MODULES)
    rtype = docs.report_type
    if rtype:
        names |= {p.stem for p in common.glob(f"{rtype}_*.py")}
        template = docs.root / "templates" / f"{rtype}.md"
        if template.is_file():
            names |= set(_COMMON_MENTION_RE.findall(template.read_text(encoding="utf-8")))
    for rel in upstream_files:
        path = docs.root / rel
        if not path.is_file():
            continue
        for a, b, c in _COMMON_IMPORT_RE.findall(path.read_text(encoding="utf-8")):
            names |= {n.strip() for n in (a, b, *c.split(",")) if n.strip()}
    return sorted(f"common/{n}.py" for n in names if (common / f"{n}.py").is_file())


def _closure(docs: CaseDocs, element_ids: Iterable[str], include_related: bool = False) -> list[str]:
    """一跳引用：「依赖数据」字段和公式、参数行里的非 R 引用（include_related 时再加「关联要素」）。"""
    base = list(element_ids)
    known = {b.id for b in docs.spec_blocks}
    out: list[str] = []
    for eid in base:
        block = docs.element(eid)
        if not block:
            continue
        for f in block.fields:
            if f.name.startswith(CLOSURE_FIELD_PREFIXES):
                # 「依赖数据: D1, D5 / 关联基准: R2-R7 / 关联歧义: A2」：R 类基准不带进来
                refs = ms.extract_refs(f.text, prefixes=("SA", "D", "F", "B"))
            elif include_related and f.name.startswith("关联要素"):
                refs = ms.extract_refs(f.text)
            else:
                continue
            for ref in refs:
                if ref in known and ref not in base and ref not in out:
                    out.append(ref)
    return [b.id for b in docs.spec_blocks if b.id in out]


# ---------------------------------------------------------------------------
# 拼包
# ---------------------------------------------------------------------------


def _require(docs: CaseDocs, *names: str) -> None:
    missing = [n for n in names if getattr(docs, n) is None]
    if missing:
        label = {"spec": "spec/spec.md", "assumptions": "assumptions.md", "matrix": "spec/coverage_matrix.md", "plan": "plan.md"}
        raise PackError(f"{docs.report_id} 缺少文书: {', '.join(label[m] for m in missing)}")


def _header(docs: CaseDocs, role: str, step: str, pack: Pack) -> Chrome:
    lines = [
        f"<!-- {PACK_FORMAT} · {docs.report_id} · {role} · {step} -->",
        f"# 任务上下文：{ROLE_CN.get(role, role)} · {step}",
        "",
        "> 下面的内容由内核从原始文书逐字切出，只包含这一步需要的部分。如与原文冲突，以原文为准。",
        f"> 只列了标题的要素或假设，需要全文时用 `flow get {docs.report_id} element <编号>` 或 "
        f"`flow get {docs.report_id} assumption <编号>` 取，不要整读原文件。",
    ]
    for w in pack.warnings:
        lines.append(f"> 注意：{w}")
    lines.append("")
    return Chrome("\n".join(lines) + "\n")


def _section(title: str, note: str = "") -> Chrome:
    return Chrome(f"\n## {title}\n" + (f"\n> {note}\n" if note else "") + "\n")


def _add_template(docs: CaseDocs, pack: Pack, parts: list[Part]) -> None:
    rtype = docs.report_type
    doc = _load_doc(docs.root, f"templates/{rtype}.md") if rtype else None
    if doc is None:
        pack.warnings.append(f"找不到类型模板 templates/{rtype}.md")
        return
    parts.append(_section("类型模板", doc.rel))
    parts.append(doc.whole("template", str(rtype)))
    pack.sources[doc.rel] = ms.file_hash(doc.path)


def _full_contract(docs: CaseDocs, role: str) -> dict[str, int]:
    """现行合同里这个角色整读的文件（用来和包的大小对比）。"""
    rtype = docs.report_type
    template = _load_doc(docs.root, f"templates/{rtype}.md") if rtype else None
    standards = _load_doc(docs.root, "templates/standards.json")
    wanted: list[Optional[Doc]] = [docs.spec, docs.assumptions, docs.matrix]
    if role == "coder":
        wanted += [docs.plan, template]
    elif role == "verifier":
        wanted += [standards, template]
    elif role == "auditor_result":
        wanted += [docs.ambiguities]
    return {d.rel: d.nbytes for d in wanted if d is not None}


def _step_mismatch_warnings(docs: CaseDocs, milestone: str) -> list[str]:
    in_matrix, in_plan = set(docs.matrix_elements(milestone)), set(docs.plan_elements(milestone))
    out: list[str] = []
    if in_plan and in_matrix - in_plan:
        out.append(f"{milestone} 的要素只在矩阵里有归属、plan 的 elements 里没有: {sorted(in_matrix - in_plan)}")
    if in_plan - in_matrix:
        out.append(f"{milestone} 的要素只在 plan 的 elements 里、矩阵 milestone 列没有: {sorted(in_plan - in_matrix)}")
    return out


def build_pack(docs: CaseDocs, role: str, step: str) -> Pack:
    """拼一个包。step 是 milestone 编号（m1、m2…）或 final。"""
    if step == FINAL_STEP:
        if role not in FINAL_ROLES:
            raise PackError(f"final 步只有 {FINAL_ROLES} 两种包，收到 {role}")
        return _build_final(docs, role)
    if role not in MILESTONE_ROLES:
        raise PackError(f"milestone 步只有 {MILESTONE_ROLES} 三种包，收到 {role}")
    if step not in docs.milestone_ids():
        raise PackError(f"{docs.report_id} 没有 milestone {step}（已有: {docs.milestone_ids()}）")
    _require(docs, "spec", "assumptions", "matrix")
    if role == "coder":
        _require(docs, "plan")

    pack = Pack(docs.report_id, role, step, full_contract=_full_contract(docs, role))
    pack.warnings.extend(_step_mismatch_warnings(docs, step))
    step_ids = docs.step_elements(step)
    missing = [e for e in step_ids if docs.element(e) is None]
    if missing:
        pack.warnings.append(f"矩阵或 plan 把这些要素归到 {step}，但 spec.md 里没有对应的块: {missing}")
    step_ids = [e for e in step_ids if docs.element(e) is not None]
    body: list[Part] = []

    if role == "coder":
        closure = _closure(docs, step_ids)
        full_ids = step_ids
        dep_ids = closure
    elif role == "auditor_code":
        all_fb = [b.id for b in docs.spec_blocks if b.prefix in ("F", "B")]
        full_ids = [b.id for b in docs.spec_blocks if b.id in set(all_fb) | set(step_ids)]
        dep_ids = []
    else:  # verifier：本步 R/SA 及其关联要素
        full_ids = [e for e in step_ids if docs.element(e).prefix in ("R", "SA")]
        dep_ids = _closure(docs, full_ids, include_related=True)

    shown = set(full_ids) | set(dep_ids)
    label = {"coder": "本步要素（全文）", "auditor_code": "全部 F、B 要素与本步其余要素（全文）", "verifier": "本步 R、SA 基准（全文）"}[role]
    body.append(_section(f"{label}，{len(full_ids)} 条", docs.spec.rel))
    body.extend(_element_full(docs, docs.element(e)) for e in full_ids)
    if dep_ids:
        dep_label = "依赖数据（一跳）" if role == "coder" else "关联要素（一跳）"
        body.append(_section(f"{dep_label}，{len(dep_ids)} 条"))
        body.extend(_element_full(docs, docs.element(e)) for e in dep_ids)
    rest = [b for b in docs.spec_blocks if b.id not in shown]
    if rest:
        body.append(_section(f"其余要素索引，{len(rest)} 条", "只列标题"))
        body.extend(_element_index(docs, b) for b in rest)

    # 假设：审计持全部口径卡；编码与验证只带主归属的，其余列标题。归属不明的进所有包。
    owners = {b.id: docs.assumption_owners(b) for b in docs.assumption_blocks}
    if role == "auditor_code":
        cards = list(docs.assumption_blocks)
    else:
        cards = [
            b for b in docs.assumption_blocks
            if step in owners[b.id] or (not owners[b.id] and not docs.assumption_explicit_none(b))
        ]
    extra = ("预期影响",) if role == "verifier" else ()
    card_ids = {b.id for b in cards}
    card_label = "全部假设的口径卡" if role == "auditor_code" else "本步假设的口径卡"
    body.append(_section(f"{card_label}，{len(cards)} 条", docs.assumptions.rel))
    for b in cards:
        body.extend(_assumption_card(docs, b, extra))
    others = [b for b in docs.assumption_blocks if b.id not in card_ids]
    if others:
        body.append(_section(f"其余假设索引，{len(others)} 条", "只列标题"))
        body.extend(_assumption_index(docs, b) for b in others)

    body.append(_section("覆盖矩阵：本步的行", docs.matrix.rel))
    body.extend(_matrix_rows(docs, step_ids))

    if role == "coder":
        plan_parts, plan_warnings = _plan_parts(docs, step)
        pack.warnings.extend(plan_warnings)
        if plan_parts:
            body.append(_section("计划：本步与回测参数", docs.plan.rel))
            body.extend(plan_parts)
        _add_template(docs, pack, body)
        upstream = _impl_files(docs, docs.milestone_deps(step))
        common_files = _common_modules(docs, upstream)
        sig_files = common_files + [f for f in upstream if f not in common_files]
        sigs = [(rel, signature_segments(docs.root, rel)) for rel in sig_files]
        sigs = [(rel, segs) for rel, segs in sigs if segs]
        if sigs:
            body.append(_section("公共模块与直接上游代码的签名", "只列签名与文档串首行；实现请直接读源文件"))
            for rel, segs in sigs:
                body.append(Chrome(f"\n### {rel}\n\n```python\n"))
                body.extend(segs)
                body.append(Chrome("```\n"))
    elif role == "verifier":
        standards = _load_doc(docs.root, "templates/standards.json")
        if standards:
            body.append(_section("达标标准", standards.rel))
            body.append(Chrome("```json\n"))
            body.append(standards.whole("standards", "standards.json"))
            body.append(Chrome("```\n"))
            pack.sources[standards.rel] = ms.file_hash(standards.path)
        _add_template(docs, pack, body)

    for doc in (docs.spec, docs.assumptions, docs.matrix, docs.plan if role == "coder" else None):
        if doc is not None:
            pack.sources[doc.rel] = ms.file_hash(doc.path)
    pack.summary = {
        "step_elements": len(step_ids),
        "full_elements": len(full_ids),
        "closure_elements": len(dep_ids),
        "index_elements": len(rest),
        "assumption_cards": len(cards),
        "assumption_index": len(others),
    }
    pack.parts = [_header(docs, role, step, pack), *body]
    return pack


def _build_final(docs: CaseDocs, role: str) -> Pack:
    _require(docs, "spec", "assumptions", "matrix")
    pack = Pack(docs.report_id, role, FINAL_STEP, full_contract=_full_contract(docs, role))
    body: list[Part] = []
    full = [b for b in docs.spec_blocks if b.prefix in ("R", "SA", "B")]
    body.append(_section(f"全部 R、SA、B 要素（全文），{len(full)} 条", docs.spec.rel))
    body.extend(_element_full(docs, b) for b in full)
    rest = [b for b in docs.spec_blocks if b.prefix not in ("R", "SA", "B")]
    if rest:
        body.append(_section(f"其余要素索引，{len(rest)} 条", "只列标题"))
        body.extend(_element_index(docs, b) for b in rest)
    body.append(_section(f"全部假设的口径卡，{len(docs.assumption_blocks)} 条", docs.assumptions.rel))
    for b in docs.assumption_blocks:
        body.extend(_assumption_card(docs, b, ("预期影响",)))
    body.append(_section("覆盖矩阵：全部行", docs.matrix.rel))
    body.extend(_matrix_rows(docs, [ms.row_get(r.cells, "要素ID") for r in docs.matrix_rows]))
    results = docs.root / "output" / docs.report_id / "results"
    charts = sorted(p.relative_to(docs.root).as_posix() for p in results.glob("*.png")) if results.is_dir() else []
    if charts:
        body.append(_section(f"图表路径，{len(charts)} 张"))
        body.append(Chrome("".join(f"- {c}\n" for c in charts)))
    if role == "verifier":
        standards = _load_doc(docs.root, "templates/standards.json")
        if standards:
            body.append(_section("达标标准", standards.rel))
            body.append(Chrome("```json\n"))
            body.append(standards.whole("standards", "standards.json"))
            body.append(Chrome("```\n"))
            pack.sources[standards.rel] = ms.file_hash(standards.path)
        _add_template(docs, pack, body)
    for doc in (docs.spec, docs.assumptions, docs.matrix):
        pack.sources[doc.rel] = ms.file_hash(doc.path)
    pack.summary = {
        "full_elements": len(full),
        "index_elements": len(rest),
        "assumption_cards": len(docs.assumption_blocks),
        "charts": len(charts),
    }
    pack.parts = [_header(docs, role, FINAL_STEP, pack), *body]
    return pack


def verify_pack(docs: CaseDocs, pack: Pack) -> list[str]:
    """核对包里的每个片确实是来源文件的逐字节子串，且偏移对得上。返回问题清单。"""
    problems: list[str] = []
    cache: dict[str, tuple[str, bytes]] = {}
    for seg in pack.segments():
        if seg.source not in cache:
            raw = (docs.root / seg.source).read_bytes()
            cache[seg.source] = (raw.decode("utf-8"), raw)
        text, raw = cache[seg.source]
        if text[seg.start:seg.end] != seg.text:
            problems.append(f"{seg.source}#{seg.key}: 偏移 {seg.start}-{seg.end} 处的内容与片不符")
        elif seg.text.encode("utf-8") not in raw:
            problems.append(f"{seg.source}#{seg.key}: 片不是原文的逐字节子串")
    return problems


# ---------------------------------------------------------------------------
# 逃生门取块
# ---------------------------------------------------------------------------


def get_block(docs: CaseDocs, kind: str, key: str) -> Segment:
    """取一个要素块、一条假设或一行矩阵的原文。"""
    if kind == "element":
        block = docs.element(key)
        if block is None:
            raise PackError(f"spec.md 里没有要素 {key}")
        return _element_full(docs, block)
    if kind == "assumption":
        block = docs.assumption(key)
        if block is None:
            raise PackError(f"assumptions.md 里没有假设 {key}")
        return docs.assumptions.segment(block.start, block.end, "assumption", key)
    if kind == "matrix-row":
        row = docs.matrix_row(key)
        if row is None:
            raise PackError(f"coverage_matrix.md 里没有要素 {key} 的行")
        return docs.matrix.segment(row.start, row.end, "matrix", key)
    raise PackError(f"不支持的取块类型: {kind}（只有 element / assumption / matrix-row）")


# ---------------------------------------------------------------------------
# lint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LintFinding:
    level: str  # warn / info
    code: str
    message: str


def lint(docs: CaseDocs) -> list[LintFinding]:
    """检查会让切片漏给或错给内容的文书问题。只告警，不拦截。"""
    out: list[LintFinding] = []
    if docs.spec is None:
        return [LintFinding("warn", "no_spec", "没有 spec/spec.md，无法切片")]
    milestones = docs.milestone_ids()
    spec_ids = {b.id for b in docs.spec_blocks}

    # 要素归属
    no_owner: list[str] = []
    for row in docs.matrix_rows:
        eid = ms.row_get(row.cells, "要素ID")
        owner = ms.extract_milestones(ms.row_get(row.cells, "milestone"))
        status = ms.row_get(row.cells, "状态")
        priority = ms.row_get(row.cells, "优先级")
        if not owner and priority in ("core", "support") and status not in ("skipped", "infeasible"):
            if not any(eid in docs.plan_elements(m) for m in milestones):
                no_owner.append(eid)
        for m in owner:
            if milestones and m not in milestones:
                out.append(LintFinding("warn", "unknown_milestone", f"{eid} 的 milestone 列写了 {m}，但 plan 里没有这个 milestone"))
        if eid not in spec_ids:
            out.append(LintFinding("warn", "matrix_without_block", f"矩阵里的 {eid} 在 spec.md 里没有对应的块"))
    if not milestones:
        out.append(LintFinding("info", "no_milestones", "plan 还没有拆出 milestone，要素与假设的归属检查暂不适用"))
    elif no_owner:
        out.append(LintFinding("warn", "element_no_owner", f"{len(no_owner)} 个 core/support 要素没有归属 milestone，不会以全文进任何一步的包: {no_owner}"))
    matrix_ids = {ms.row_get(r.cells, "要素ID") for r in docs.matrix_rows}
    if docs.matrix is not None:
        for eid in sorted(spec_ids - matrix_ids):
            out.append(LintFinding("warn", "block_without_matrix", f"spec.md 的 {eid} 在矩阵里没有行"))
    for m in milestones:
        in_matrix, in_plan = set(docs.matrix_elements(m)), set(docs.plan_elements(m))
        if in_plan and in_matrix - in_plan:
            out.append(LintFinding("info", "owner_matrix_only", f"{m}: 只在矩阵里有归属 {sorted(in_matrix - in_plan)}（取并集，不影响切片）"))
        if in_plan - in_matrix:
            out.append(LintFinding("info", "owner_plan_only", f"{m}: 只在 plan elements 里 {sorted(in_plan - in_matrix)}（取并集，不影响切片）"))
        if in_plan - spec_ids:
            out.append(LintFinding("warn", "plan_unknown_element", f"{m}: plan elements 里的 {sorted(in_plan - spec_ids)} 在 spec.md 里没有"))

    # 引用
    for block in docs.spec_blocks:
        for f in block.fields:
            if not f.name.startswith(CLOSURE_FIELD_PREFIXES):
                continue
            dangling = [r for r in ms.extract_refs(f.text, prefixes=("SA", "D", "F", "B")) if r not in spec_ids]
            if dangling and f.name.startswith("依赖数据"):
                out.append(LintFinding("warn", "dangling_ref", f"{block.id} 的「{f.name}」引用了不存在的要素 {dangling}"))

    # 假设归属与字段
    if docs.plan is not None:
        secs = ms.sections(docs.plan.text)
        for m in milestones:
            if not any(re.match(rf"^{re.escape(m)}(?![0-9A-Za-z_])", s.title.strip()) for s in secs):
                out.append(LintFinding("warn", "plan_no_step_section", f"plan.md 里没有以「{m}」开头的小节，coder 包拿不到这一步的计划段"))
        if not any(s.level == 2 and "回测参数" in s.title for s in secs):
            out.append(LintFinding("warn", "plan_no_params", "plan.md 里没有标题含「回测参数」的二级小节"))
    for block in docs.assumption_blocks:
        owners = docs.assumption_owners(block)
        if not owners and milestones:
            if docs.assumption_explicit_none(block):
                out.append(LintFinding("info", "assumption_explicit_none", f"{block.id} 写明不影响任何 milestone，只以口径卡进审计的包"))
            else:
                out.append(LintFinding("warn", "assumption_unattributed", f"{block.id} 无法归属到 milestone（「影响 milestone」与「影响指标」都对不上），会进所有包"))
        for m in docs.assumption_primary_milestones(block):
            if milestones and m not in milestones:
                out.append(LintFinding("warn", "assumption_unknown_milestone", f"{block.id} 的「影响 milestone」写了 {m}，但 plan 里没有"))
        if block.field("假设内容") is None:
            out.append(LintFinding("warn", "assumption_no_content_field", f"{block.id} 没有「假设内容」字段，切不出口径卡，按整块带入"))
        elif block.field("状态") is None:
            out.append(LintFinding("warn", "assumption_missing_field", f"{block.id} 缺「状态」字段"))
        unknown = [f.name for f in block.fields if not is_known_assumption_field(f.name)]
        if unknown and block.field("假设内容") is not None:
            out.append(LintFinding("info", "assumption_extra_field", f"{block.id} 有未识别的字段 {unknown}，已原样带入口径卡"))
    return out


# ---------------------------------------------------------------------------
# 影子包统计
# ---------------------------------------------------------------------------


def shadow_stats(root: Path, report_id: str) -> dict[str, Any]:
    """对一个案例的全部步骤拼影子包，只返回大小统计，不写任何文件。"""
    docs = CaseDocs.load(root, report_id)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    targets = [(role, m) for m in docs.milestone_ids() for role in MILESTONE_ROLES]
    targets += [(role, FINAL_STEP) for role in FINAL_ROLES]
    for role, step in targets:
        try:
            pack = build_pack(docs, role, step)
        except PackError as exc:
            errors.append(f"{role}/{step}: {exc}")
            continue
        problems = verify_pack(docs, pack)
        rows.append(
            {
                "role": role,
                "step": step,
                "bytes": pack.nbytes,
                "full_bytes": pack.full_bytes,
                "ratio": round(pack.nbytes / pack.full_bytes, 4) if pack.full_bytes else None,
                "by_kind": pack.bytes_by_kind(),
                "summary": pack.summary,
                "warnings": pack.warnings,
                "substring_ok": not problems,
            }
        )
    findings = lint(docs)
    return {
        "report_id": report_id,
        "milestones": docs.milestone_ids(),
        "packs": rows,
        "errors": errors,
        "lint": {"warn": sum(f.level == "warn" for f in findings), "info": sum(f.level == "info" for f in findings)},
    }


def summarize_ratios(stats: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按角色汇总「包大小 / 现行合同全量」的分布。"""
    by_role: dict[str, list[tuple[float, int]]] = {}
    for case in stats:
        for row in case["packs"]:
            if row["ratio"] is None:
                continue
            key = row["role"] if row["step"] != FINAL_STEP else f"{row['role']}(final)"
            by_role.setdefault(key, []).append((row["ratio"], row["bytes"]))
    out: dict[str, dict[str, Any]] = {}
    for role, values in by_role.items():
        ratios = [v[0] for v in values]
        sizes = [v[1] for v in values]
        out[role] = {
            "n": len(values),
            "ratio_min": min(ratios),
            "ratio_median": round(median(ratios), 4),
            "ratio_max": max(ratios),
            "bytes_min": min(sizes),
            "bytes_median": int(median(sizes)),
            "bytes_max": max(sizes),
        }
    return out
