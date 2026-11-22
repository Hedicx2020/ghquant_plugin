"""flow explain：键的解析、按段取用、门禁未过时附带的说明，以及说明文件与内核表的一致性。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_harness as fh  # noqa: E402
from tools import check_gates as cg  # noqa: E402
from tools import flow  # noqa: E402
from tools import state as st  # noqa: E402
from tools.flowlib import checkpoints as cps  # noqa: E402
from tools.flowlib import core, explain  # noqa: E402

DIR = explain.EXPLAIN_DIR


def test_every_stage_checkpoint_and_topic_has_an_entry() -> None:
    names = set(explain.available())
    assert set(st.STAGE_ORDER) <= names
    assert {"index", "checkpoints", "collect", "review_cycle", "data", "revise", "limits"} <= names
    text = (DIR / "checkpoints.md").read_text(encoding="utf-8")
    for name in list(cps.HUMAN) + list(cps.AUTO):
        assert explain.section_of(text, name) is not None, f"checkpoints.md 里没有 {name} 的说明"
    index = (DIR / "index.md").read_text(encoding="utf-8")
    for topic in names - set(st.STAGE_ORDER) - {"index"}:
        assert f"`{topic}`" in index, f"index.md 没有列出 {topic}"


def test_keys_resolve_to_the_right_file_and_section() -> None:
    assert explain.resolve("verify") == ("verify", None)
    assert explain.resolve("implement.m2.code#3") == ("implement", None)
    assert explain.resolve("G-VF-6") == ("verify", "G-VF-6")
    assert explain.resolve("g-vf") == ("verify", None)
    assert explain.resolve("G-FN-7") == ("report", "G-FN-7")
    assert explain.resolve("data_gap") == ("checkpoints", "data_gap")
    assert explain.resolve("review_cycle") == ("review_cycle", None)
    assert explain.resolve("没有这个键") is None and explain.resolve("G-ZZ-1") is None and explain.resolve("") is None

    one = explain.lookup("G-VF-6")
    assert one.startswith("# verify") and "## G-VF-6" in one and "整批重出" in one and "G-VF-3" not in one
    shared = explain.lookup("G-VF-5")  # 与 G-VF-4 合写的一段
    assert "## G-VF-4、G-VF-5" in shared
    assert "## circuit_breaker" in explain.lookup("stuck") and "pin_card" in explain.lookup("stuck")
    assert explain.lookup("G-VF") == (DIR / "verify.md").read_text(encoding="utf-8")
    assert explain.lookup("nope") is None


def test_sections_stay_small_and_cover_every_gate_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 走完一个玩具案例，拿到每个阶段真实的检查项编号
    root = fh.make_root(tmp_path)
    rid = fh.new_case(root, monkeypatch)
    stub = fh.Stub(root, rid, fh.Scenario())
    fh.install_fake_review(monkeypatch, stub)
    fh.drive(root, rid, stub)
    for stage in st.STAGE_ORDER[:-1]:
        text = (DIR / f"{stage}.md").read_text(encoding="utf-8")
        assert len(text.encode("utf-8")) < 4096, f"{stage}.md 太长"
        for check in cg.evaluate(root, rid, stage).checks:
            found = explain.resolve(check.id)
            assert found is not None and found[0] == stage, check.id
        for heading in re.findall(r"^## (.+)$", text, re.MULTILINE):
            part = explain.section_of(text, re.findall(r"[A-Za-z][A-Za-z0-9_.\-]*", heading)[0]) if re.findall(r"[A-Za-z][A-Za-z0-9_.\-]*", heading) else None
            if part is not None:
                assert len(part.encode("utf-8")) <= explain.INLINE_LIMIT, f"{stage}.md 的「{heading}」一段超过 {explain.INLINE_LIMIT} 字节"
    # 只有 G-VF-3 不过是进入迭代的正常路径：说明里必须讲清楚，不能让人去「修」
    assert "不算失败" in explain.lookup("G-VF-3")


def test_inline_text_for_failed_checks_is_bounded() -> None:
    text = explain.inline(["G-VF-6", "G-VF-4", "G-VF-5", "G-VF-1", "G-VF-7"])
    parts = text.split("\n\n## ")
    assert len(parts) == 3 and text.startswith("## G-VF-6")  # 最多三段；合写的一段只出现一次
    assert explain.inline(["G-ZZ-9", "REVIEW"]) == "" and explain.inline([]) == ""
    long = DIR.parent / "explain"
    assert all(len(p.encode("utf-8")) <= explain.INLINE_LIMIT + 80 for p in text.split("\n\n"))
    assert long.is_dir()


def test_gate_failure_note_carries_the_explanation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = fh.make_root(tmp_path)
    rid = fh.new_case(root, monkeypatch)

    def stale(stub: fh.Stub, order: dict) -> None:  # 第一次验证后把结果的时间拨回去：结果比代码旧
        if stub.counts["verify.main"] == 1:
            for path in stub.results().rglob("*"):
                if path.is_file():
                    __import__("os").utime(path, (1_000_000_000, 1_000_000_000))

    stub = fh.Stub(root, rid, fh.Scenario(hooks={"verify.main": stale}))
    fh.install_fake_review(monkeypatch, stub)
    notes: list[str] = []
    out = fh.drive(root, rid, stub, until=lambda o: notes.extend(o.get("notes") or []) or any("G-VF-6" in n for n in notes))
    note = next(n for n in notes if "G-VF-6" in n)
    assert "验证门禁未过" in note and "处理说明" in note and "结果必须整批重出" in note
    assert out is not None


def test_cli_explain(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(tmp_path))
    assert flow.main(["explain", "G-PL-11"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# plan") and "## G-PL-11" in out and "data_gap" in out
    assert flow.main(["explain", "limits"]) == 0 and "flow.redispatch_limit" in capsys.readouterr().out
    assert flow.main(["explain", "no_such_key"]) == 1
    assert "flow explain index" in capsys.readouterr().err


def test_limits_page_matches_kernel_constants() -> None:
    text = (DIR / "limits.md").read_text(encoding="utf-8")
    assert f"| 同一步骤重派（首派之外） | {core.DEFAULT_REDISPATCH_LIMIT} 次" in text
    assert f"| 外审复审 | {core.REVIEW_ROUND_LIMIT} 轮" in text
    assert f"| 检查点上「修改后继续」 | {core.MODIFY_ROUND_LIMIT} 轮" in text
    assert f"| 一次定向重跑内部的收敛 | {core.REVISE_ROUND_LIMIT} 轮" in text
    assert f"| 表外派发（`flow adhoc`） | {core.ADHOC_LIMIT} 次" in text
    easy, medium, hard = (core.MAX_ITER_BY_DIFFICULTY[k] for k in ("easy", "medium", "hard"))
    assert f"easy {easy} / medium {medium} / hard {hard}" in text
