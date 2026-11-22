"""tools/flowlib/mdslice.py：围栏感知切片、字段与表格行定位、引用解析。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools import check_gates as cg  # noqa: E402
from tools.flowlib import mdslice as ms  # noqa: E402

SPEC = """---
title: 测试
---
# 复现规格书

## 二、数据要求（D 类）

### [D1] 日行情
- 页码: p3
- 原文: > "日度收盘价"
- 数据状态: available

### [D2] 财务数据
- 页码: p4
- 原文: > "归母净利润"

## 三、因子定义（F 类）

### [F1] 动量因子
- 页码: p5
- 原文: > "过去 20 日收益"
- 公式（转写）: mom = close / close.shift(20) - 1
- 依赖数据: D1, D2 / 关联基准: R1
- 数值表:

| 组 | 收益 |
|---|---|
| 1 | 1.2% |

```python
### [F9] 围栏里的假标题
x = 1
```

- 关联要素: F2

### [F3.1] 子变体
- 页码: p6
- 原文: > "变体"

## 六、图表登记清单

| 编号 | 页码 |
|---|---|
| FIG1 | p3 |
"""


def test_blocks_stop_at_same_or_higher_level_heading() -> None:
    blocks = ms.parse_blocks(SPEC)
    assert [b.id for b in blocks] == ["D1", "D2", "F1", "F3.1"]  # 围栏里的 F9 不算
    d2 = blocks[1]
    assert d2.text.rstrip().endswith('> "归母净利润"')  # 不把下一章吞进来
    assert "三、因子定义" not in d2.text
    last = blocks[-1]
    assert "图表登记清单" not in last.text and last.text.rstrip().endswith('> "变体"')
    # 旧解析器的最后一块会吞掉后面的章节
    legacy_last = cg.parse_id_blocks(SPEC)[-1]
    assert "图表登记清单" in legacy_last.body


def test_block_text_is_exact_substring() -> None:
    for block in ms.parse_blocks(SPEC):
        assert SPEC[block.start:block.end] == block.text
        assert block.heading_line == SPEC[block.start:block.heading_end]
        assert block.heading_line.startswith(f"### [{block.id}]")
        for f in block.fields:
            assert SPEC[f.start:f.end] == f.text
            assert f.text.startswith("- ") and not f.text.endswith("\n\n")


def test_fields_span_until_next_field_and_respect_fences() -> None:
    f1 = next(b for b in ms.parse_blocks(SPEC) if b.id == "F1")
    names = [f.name for f in f1.fields]
    assert names == ["页码", "原文", "公式（转写）", "依赖数据", "数值表", "关联要素"]
    table_field = f1.field("数值表")
    assert "| 1 | 1.2% |" in table_field.text  # 字段下面的表格属于这个字段
    assert "x = 1" in table_field.text  # 围栏也跟着上一个字段走
    assert "关联要素" not in table_field.text
    assert f1.field("依赖数据").value == "D1, D2 / 关联基准: R1"
    assert f1.field("不存在") is None
    assert [f.name for f in f1.fields_where(lambda n: n.startswith("公式"))] == ["公式（转写）"]


def test_headings_ignore_fenced_lines_and_sections_nest() -> None:
    text = "# 一\n\n```\n# 不是标题\n```\n\n## 二\n正文\n\n### 三\n更深\n\n## 四\n尾\n"
    assert [(h.level, h.title) for h in ms.headings(text)] == [(1, "一"), (2, "二"), (3, "三"), (2, "四")]
    secs = {s.title: s for s in ms.sections(text)}
    assert secs["二"].text == "## 二\n正文\n\n### 三\n更深\n\n"
    assert secs["三"].text == "### 三\n更深\n\n"
    assert secs["一"].text == text
    assert [s.title for s in ms.find_sections(text, lambda h: h.level == 2)] == ["二", "四"]


def test_tilde_fence_and_longer_closing_fence() -> None:
    text = "~~~\n### [F1] 假\n~~~\n### [F2] 真\n- 页码: p1\n````\n```\n### [F3] 假\n````\n"
    assert ms.block_ids(text) == ["F2"]


def test_crlf_source_stays_byte_exact(tmp_path: Path) -> None:
    raw = "### [D1] 标题\r\n- 页码: p1\r\n- 原文: > \"x\"\r\n\r\n## 下一章\r\n".encode("utf-8")
    path = tmp_path / "spec.md"
    path.write_bytes(raw)
    text = ms.read_source(path)
    block = ms.parse_blocks(text)[0]
    assert block.id == "D1" and block.title == "标题"
    assert block.text.encode("utf-8") in raw  # 不做换行符转换
    assert block.field("页码").value == "p1"
    assert "下一章" not in block.text


def test_table_rows_keep_positions() -> None:
    text = "前言\n\n| 要素ID | milestone | 状态 |\n|---|---|---|\n| D1 | m1 | done |\n| F1 | m2 | a\\|b |\n\n| 时间 | 事件 |\n|---|---|\n| t | e |\n"
    rows = ms.parse_table_rows(text)
    assert [r.cells for r in rows] == [
        {"要素ID": "D1", "milestone": "m1", "状态": "done"},
        {"要素ID": "F1", "milestone": "m2", "状态": "a|b"},
        {"时间": "t", "事件": "e"},
    ]
    for r in rows:
        assert text[r.start:r.end] == r.text
    assert text[rows[0].header_start:rows[0].header_end] == "| 要素ID | milestone | 状态 |\n|---|---|---|\n"
    assert rows[0].header_start == rows[1].header_start != rows[2].header_start
    assert [r.cells for r in rows] == cg.parse_markdown_table_rows(text)  # 拆格结果与门禁用的解析器一致
    assert ms.row_get(rows[0].cells, "要素ID") == "D1"
    assert ms.row_get({"处置(accepted/rejected)": "accepted"}, "处置") == "accepted"


def test_frontmatter_span() -> None:
    span = ms.frontmatter_span(SPEC)
    assert span is not None and SPEC[span[0]:span[1]] == "---\ntitle: 测试\n---\n"
    assert ms.frontmatter_span("# 没有 frontmatter\n") is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("D2, D4 / 关联基准: R1", ["D2", "D4", "R1"]),
        ("R2-R7 与 SA5–SA7", ["R2", "R3", "R4", "R5", "R6", "R7", "SA5", "SA6", "SA7"]),
        ("见F3.1和F3。另有 D10~D12", ["F3.1", "F3", "D10", "D11", "D12"]),
        ("XD1、D1x、R²、B_1、AS3 都不算", []),
        ("D5-D3 不是合法区间", ["D5", "D3"]),
        ("n/a", []),
    ],
)
def test_extract_refs(text: str, expected: list[str]) -> None:
    assert ms.extract_refs(text) == expected


def test_extract_refs_with_custom_prefixes() -> None:
    assert ms.extract_refs("D1, R2, AS3, A5", prefixes=("D", "F", "B", "SA")) == ["D1"]
    assert ms.extract_refs("AS3 与 A5", prefixes=("AS", "A")) == ["AS3", "A5"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("m1", ["m1"]),
        ("m2, m4、m5", ["m2", "m4", "m5"]),
        ("m3（主）、m4-m6（下游）", ["m3", "m4", "m5", "m6"]),
        ("不含 mm1、m2x、sm3；m10", ["m10"]),
        ("skip", []),
    ],
)
def test_extract_milestones(text: str, expected: list[str]) -> None:
    assert ms.extract_milestones(text) == expected


def test_slice_hash_is_stable_and_content_based() -> None:
    assert ms.slice_hash("abc") == ms.slice_hash("abc")
    assert ms.slice_hash("abc") != ms.slice_hash("abd")
    assert len(ms.slice_hash("中文")) == 16


def _real_docs() -> list[Path]:
    ws = REPO_ROOT / "workspace"
    if not ws.is_dir():
        return []
    out: list[Path] = []
    for case in sorted(ws.iterdir()):
        for rel in ("spec/spec.md", "assumptions.md", "spec/ambiguities.md"):
            if (case / rel).is_file():
                out.append(case / rel)
    return out


@pytest.mark.parametrize("path", _real_docs(), ids=lambda p: f"{p.parent.name if p.parent.name != 'spec' else p.parent.parent.name}/{p.name}")
def test_real_documents_same_ids_as_legacy_parser(path: Path) -> None:
    """真实案例的文书：切出的编号集合与门禁用的解析器一致，且每个片都是原文的逐字节子串。"""
    raw = path.read_bytes()
    text = ms.read_source(path)
    mine = ms.parse_blocks(text)
    assert [b.id for b in mine] == [b.id for b in cg.parse_id_blocks(text)]
    for block in mine:
        assert block.text.encode("utf-8") in raw
        assert all(text[f.start:f.end] == f.text for f in block.fields)
