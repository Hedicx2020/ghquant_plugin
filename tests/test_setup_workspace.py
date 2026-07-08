"""tools/setup_workspace.py 单测：幂等性 / 种子拷贝跳过 / 配置生成与覆盖 / 参数校验。

环境检测（check_env）依赖外部 uv/codex，单测中以 monkeypatch 短路，不做真实探测。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import setup_workspace as sw  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_env_check(monkeypatch):
    """短路环境探测：单测不依赖 uv/codex 真实存在。"""
    monkeypatch.setattr(sw, "check_env", lambda target, report: report.env.update({
        "uv": "/fake/uv", "codex": None, "missing_deps": [],
    }))


def _run(tmp_path: Path, **kw) -> sw.SetupReport:
    defaults = dict(data_root="~/local_data", mode="auto", max_iter=None,
                    force_config=False, check_only=False)
    defaults.update(kw)
    return sw.run_setup(target=tmp_path, **defaults)


def test_fresh_setup_creates_everything(tmp_path):
    report = _run(tmp_path)
    # 配置
    assert report.config_action == "created"
    cfg = json.loads((tmp_path / ".reproduce.json").read_text(encoding="utf-8"))
    assert cfg["data_root"] == "~/local_data"
    assert cfg["default_mode"] == "auto"
    assert cfg["default_max_iter"] is None
    assert Path(cfg["plugin_root"]) == sw.plugin_root()
    assert cfg["config_version"] == sw.CONFIG_VERSION
    # 种子：standards.json 与 data_loader 必到位
    assert (tmp_path / "templates" / "standards.json").is_file()
    assert (tmp_path / "common" / "data_loader.py").is_file()
    assert report.copied and not report.skipped_existing
    # pyproject 与目录树
    assert report.pyproject_action == "created"
    assert "pandas>=2.0" in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    for d in sw.WORK_DIRS:
        assert (tmp_path / d).is_dir()


def test_rerun_is_idempotent_and_skips_existing(tmp_path):
    first = _run(tmp_path)
    second = _run(tmp_path)
    assert second.config_action == "kept"
    assert second.pyproject_action == "kept"
    assert not second.copied
    # 首次拷贝的每个文件重跑时都被跳过
    assert set(second.skipped_existing) == set(first.copied)
    assert second.dirs_created == []


def test_user_customization_never_overwritten(tmp_path):
    _run(tmp_path)
    catalog = tmp_path / "templates" / "data_catalog.md"
    catalog.write_text("用户自己的数据目录\n", encoding="utf-8")
    _run(tmp_path)
    assert catalog.read_text(encoding="utf-8") == "用户自己的数据目录\n"


def test_plugin_newer_listed_when_seed_updated(tmp_path):
    _run(tmp_path)
    catalog = tmp_path / "templates" / "data_catalog.md"
    # 把用户侧文件 mtime 拨回过去，模拟插件侧种子更新
    import os
    old = catalog.stat().st_mtime - 10_000
    os.utime(catalog, (old, old))
    report = _run(tmp_path)
    assert "templates/data_catalog.md" in report.plugin_newer
    # 但内容不被覆盖（skipped 仍包含它）
    assert "templates/data_catalog.md" in report.skipped_existing


def test_force_config_overwrites(tmp_path):
    _run(tmp_path)
    report = _run(tmp_path, mode="interactive", max_iter=4, force_config=True)
    assert report.config_action == "overwritten"
    cfg = json.loads((tmp_path / ".reproduce.json").read_text(encoding="utf-8"))
    assert cfg["default_mode"] == "interactive"
    assert cfg["default_max_iter"] == 4


def test_invalid_mode_and_max_iter_rejected(tmp_path):
    with pytest.raises(SystemExit):
        _run(tmp_path, mode="yolo")
    with pytest.raises(SystemExit):
        _run(tmp_path, max_iter=99)


def test_check_only_touches_nothing(tmp_path):
    report = _run(tmp_path, check_only=True)
    assert not (tmp_path / ".reproduce.json").exists()
    assert not (tmp_path / "templates").exists()
    assert report.config_action == "" and not report.copied
    assert report.env["uv"] == "/fake/uv"


def test_main_cli_json_output(tmp_path, capsys):
    rc = sw.main(["--target", str(tmp_path), "--data-root", "~/mydata",
                  "--mode", "interactive", "--max-iter", "3", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["config"]["data_root"] == "~/mydata"
    assert out["config"]["default_max_iter"] == 3


def test_main_cli_max_iter_blank_means_auto(tmp_path, capsys):
    rc = sw.main(["--target", str(tmp_path), "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["config"]["default_max_iter"] is None


def test_render_text_codex_missing_shows_degradation_note(tmp_path):
    """codex 缺失时报告必须明示降级影响（可信度封顶 B），不得静默。"""
    report = sw.SetupReport(target=str(tmp_path))
    report.env = {"uv": "/fake/uv", "codex": None, "missing_deps": ["pandas"]}
    text = report.render_text()
    assert "封顶 B" in text
    assert "uv sync" in text
