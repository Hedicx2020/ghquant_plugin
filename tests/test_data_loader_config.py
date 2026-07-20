"""common.data_loader.get_data_root 的配置发现回归测试。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.data_loader import get_data_root


def test_get_data_root_defaults_when_no_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert get_data_root() == Path.home() / "local_data"


def test_get_data_root_uses_nearest_valid_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "fake_home"
    workdir = tmp_path / "project" / "nested"
    workdir.mkdir(parents=True)
    config_path = tmp_path / "project" / ".reproduce.json"
    config_path.write_text(json.dumps({"data_root": "~/custom_data"}), encoding="utf-8")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.chdir(workdir)

    assert get_data_root() == fake_home / "custom_data"


def test_get_data_root_raises_for_damaged_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / ".reproduce.json"
    config_path.write_text("{damaged", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=re.escape(str(config_path.resolve()))) as exc_info:
        get_data_root()

    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_get_data_root_raises_for_unreadable_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / ".reproduce.json"
    config_path.write_text("{}", encoding="utf-8")
    original_read_text = Path.read_text

    def raise_for_config(path: Path, *args: object, **kwargs: object) -> str:
        if path == config_path:
            raise OSError("permission denied")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", raise_for_config)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match=re.escape(str(config_path.resolve()))) as exc_info:
        get_data_root()

    assert isinstance(exc_info.value.__cause__, OSError)
