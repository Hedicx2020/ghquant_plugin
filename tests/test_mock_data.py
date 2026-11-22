"""mock 试跑的数据侧。

- common/data_loader.py：data_path / read_table / results_dir / 运行期数据清单；
- tools/mockdata.py：三种来源、确定性、与真实日历和代码对齐、规格报错；
- 端到端：玩具策略在试跑模式与真实模式下各跑一遍。

全部在 tmp_path 里造小数据，不依赖 ~/local_data（文末一项用真实数据的测试在没有时跳过）。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from common import data_loader as dl  # noqa: E402
from tools import mockdata as md  # noqa: E402

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")
yaml = pytest.importorskip("yaml")

CASE = "t001_toy"
ENV_KEYS = ("REPORT_REPRODUCE_ROOT", "REPRODUCE_REPORT_ID", "REPRODUCE_TRIAL")
HOLIDAYS = pd.to_datetime(["2019-02-04", "2019-02-05", "2019-10-01", "2020-01-24", "2020-01-27", "2020-10-01"])
TRADING_DAYS = pd.bdate_range("2018-01-02", "2020-12-31").difference(HOLIDAYS)
A_CODES = ["000001", "000002", "000004", "000005", "000006", "300001", "600000", "600004", "600006", "688001"]
HK_CODES = ["00001", "00002", "00005", "00700", "00939", "01299"]
REAL_DATA = Path.home() / "local_data"


# ---------------------------------------------------------------------------
# 夹具与造数
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch):
    """每个测试都从干净的环境变量和空的数据登记表开始；结束时清空，退出时就不会自动写清单。"""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    dl.reset_data_manifest()
    yield
    dl.reset_data_manifest()


@pytest.fixture()
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """临时工作区：.reproduce.json 把数据根指到 <root>/data，案例目录已建，当前目录在工作区里。"""
    root = tmp_path / "ws"
    (root / "data").mkdir(parents=True)
    (root / "workspace" / CASE).mkdir(parents=True)
    (root / ".reproduce.json").write_text(json.dumps({"data_root": str(root / "data")}), encoding="utf-8")
    monkeypatch.chdir(root)
    return root


def _write(frame: pd.DataFrame, path: Path, **kwargs: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), path, **kwargs)
    return path


def _panel(days: pd.DatetimeIndex, codes: list[str], seed: int = 0) -> pd.DataFrame:
    """日期 × 代码的行情面板：close 为正，volume 约一成为空。"""
    rng = np.random.default_rng(seed)
    frame = pd.MultiIndex.from_product([days, codes], names=["date", "stock_code"]).to_frame(index=False)
    frame["close"] = np.round(rng.lognormal(3.0, 0.5, len(frame)), 2)
    frame["volume"] = np.round(rng.lognormal(12.0, 1.0, len(frame)))
    frame.loc[rng.random(len(frame)) < 0.1, "volume"] = np.nan
    return frame


def _mock_dir(root: Path) -> Path:
    return root / "workspace" / CASE / "data_mock"


def _activate(root: Path) -> None:
    """模拟内核：写下试跑标记。"""
    _mock_dir(root).mkdir(parents=True, exist_ok=True)
    (_mock_dir(root) / "ACTIVE").write_text("trial\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# data_path / is_trial
# ---------------------------------------------------------------------------


def test_data_path_reads_data_root_when_not_trial(root: Path) -> None:
    _write(_panel(TRADING_DAYS[:3], A_CODES[:2]), root / "data" / "quote.parquet")
    # 覆盖目录里有同名文件，但没有试跑标记：不用它
    _write(_panel(TRADING_DAYS[:3], A_CODES[:2], seed=1), _mock_dir(root) / "files" / "quote.parquet")

    assert dl.is_trial(CASE) is False
    assert dl.data_path("quote.parquet", CASE) == root / "data" / "quote.parquet"
    assert dl.data_path("sub/x.parquet", CASE) == root / "data" / "sub" / "x.parquet"  # 文件不存在照样返回路径
    assert dl.data_path("quote.parquet") == root / "data" / "quote.parquet"  # 没有 report_id 等同直接读数据根


def test_data_path_prefers_overlay_in_trial(root: Path) -> None:
    _write(_panel(TRADING_DAYS[:3], A_CODES[:2]), root / "data" / "quote.parquet")
    _write(_panel(TRADING_DAYS[:3], A_CODES[:2]), root / "data" / "trade.parquet")
    _write(_panel(TRADING_DAYS[:3], A_CODES[:2], seed=1), _mock_dir(root) / "files" / "quote.parquet")
    _write(_panel(TRADING_DAYS[:3], A_CODES[:2], seed=1), _mock_dir(root) / "files" / "sub" / "x.parquet")
    _activate(root)

    assert dl.is_trial(CASE) is True
    assert dl.data_path("quote.parquet", CASE) == _mock_dir(root) / "files" / "quote.parquet"
    assert dl.data_path("sub/x.parquet", CASE) == _mock_dir(root) / "files" / "sub" / "x.parquet"
    assert dl.data_path("trade.parquet", CASE) == root / "data" / "trade.parquet"  # 试跑但没有覆盖文件
    assert dl.data_path("sub", CASE) == root / "data" / "sub"  # 覆盖按文件生效：覆盖目录里有 sub/ 也不整体替换
    assert dl.data_path("quote.parquet") == root / "data" / "quote.parquet"  # 没有 report_id 永远不是试跑
    assert dl.is_trial() is False


def test_trial_env_overrides_marker(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(_panel(TRADING_DAYS[:3], A_CODES[:2]), root / "data" / "quote.parquet")
    overlay = _write(_panel(TRADING_DAYS[:3], A_CODES[:2], seed=1), _mock_dir(root) / "files" / "quote.parquet")

    monkeypatch.setenv("REPRODUCE_TRIAL", "1")  # 没有标记文件也算试跑
    assert dl.is_trial(CASE) is True and dl.data_path("quote.parquet", CASE) == overlay
    assert dl.is_trial() is False  # 解析不出 report_id 时环境变量也不管用

    _activate(root)
    monkeypatch.setenv("REPRODUCE_TRIAL", "0")  # 有标记文件也不算
    assert dl.is_trial(CASE) is False and dl.data_path("quote.parquet", CASE) == root / "data" / "quote.parquet"

    monkeypatch.setenv("REPRODUCE_TRIAL", "yes")  # 不是 1 / 0：不覆盖，回到标记文件
    assert dl.is_trial(CASE) is True


def test_report_id_and_root_from_env(root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    overlay = _write(_panel(TRADING_DAYS[:3], A_CODES[:2]), _mock_dir(root) / "files" / "quote.parquet")
    _activate(root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ".reproduce.json").write_text(json.dumps({"data_root": str(root / "data")}), encoding="utf-8")
    monkeypatch.chdir(elsewhere)

    # 当前目录往上找不到 workspace/<id>/：定位不到案例，不是试跑
    assert dl.is_trial(CASE) is False
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(root))
    assert dl.is_trial(CASE) is True
    monkeypatch.setenv("REPRODUCE_REPORT_ID", CASE)
    assert dl.is_trial() is True and dl.data_path("quote.parquet") == overlay
    assert dl.is_trial("other_case") is False  # 显式参数优先于环境变量


def test_case_root_found_from_subdirectory(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _activate(root)
    nested = root / "src" / CASE
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert dl.is_trial(CASE) is True
    assert dl.results_dir(CASE) == root / "output" / CASE / "results_mock"


@pytest.mark.parametrize("name", ["/abs/quote.parquet", "../quote.parquet", "a/../../b.parquet", "", "."])
def test_data_path_rejects_paths_outside_data_root(root: Path, name: str) -> None:
    with pytest.raises(ValueError, match="相对数据根"):
        dl.data_path(name, CASE)


def test_report_id_must_not_be_a_path(root: Path) -> None:
    with pytest.raises(ValueError, match="report_id"):
        dl.is_trial("../other")


# ---------------------------------------------------------------------------
# read_table
# ---------------------------------------------------------------------------


@pytest.fixture()
def quote(root: Path) -> pd.DataFrame:
    """一张日期用各种写法各存一列的行情表（多个行组，方便下推生效）。"""
    frame = _panel(TRADING_DAYS[250:330], A_CODES[:5])
    frame["d_iso"] = frame["date"].dt.strftime("%Y-%m-%d")
    frame["d_compact"] = frame["date"].dt.strftime("%Y%m%d")
    frame["d_int"] = frame["d_compact"].astype("int64")
    frame["d_slash"] = frame["date"].dt.strftime("%Y/%m/%d")
    frame["d_sentinel"] = frame["d_int"].where(frame["stock_code"] != A_CODES[0], 0)  # 混了占位值 0 的整数日期
    table = pa.Table.from_pandas(frame, preserve_index=False)
    table = table.append_column("d_date32", pa.array(frame["date"].dt.date, type=pa.date32()))
    table = table.append_column("d_tz", pa.array(list(frame["date"].dt.tz_localize("Asia/Shanghai")), type=pa.timestamp("ms", tz="Asia/Shanghai")))
    pq.write_table(table, root / "data" / "quote.parquet", row_group_size=64)
    return frame


def _expected(frame: pd.DataFrame, start: Any, end: Any, columns: list[str], keep: Optional[pd.Series] = None) -> pd.DataFrame:
    """全量读入后再过滤的参照结果。"""
    mask = pd.Series(True, index=frame.index) if keep is None else keep
    if start is not None:
        mask &= frame["date"] >= pd.Timestamp(start)
    if end is not None:
        mask &= frame["date"] <= pd.Timestamp(end)
    full = pd.read_parquet(dl.get_data_root() / "quote.parquet")
    return full.loc[mask.to_numpy(), columns].reset_index(drop=True)


@pytest.mark.parametrize("date_col", ["date", "d_iso", "d_compact", "d_int", "d_date32", "d_tz"])
def test_read_table_pushes_date_range_down(quote: pd.DataFrame, monkeypatch: pytest.MonkeyPatch, date_col: str) -> None:
    # 这些写法都应当下推：把「读入后再过滤」的退路堵死，走到了就失败
    monkeypatch.setattr(dl, "_filter_by_date", lambda *args, **kwargs: pytest.fail("不该退回读入后再过滤"))
    start, end = quote["date"].iloc[60], quote["date"].iloc[-80]
    columns = ["stock_code", "close", "volume"]

    got = dl.read_table("quote.parquet", columns=columns, start=start.strftime("%Y-%m-%d"), end=int(end.strftime("%Y%m%d")), date_col=date_col)

    pd.testing.assert_frame_equal(got, _expected(quote, start, end, columns))
    assert list(got.columns) == columns and 0 < len(got) < len(quote)


@pytest.mark.parametrize("date_col", ["d_slash", "d_sentinel"])
def test_read_table_filters_after_reading_when_pushdown_is_impossible(quote: pd.DataFrame, date_col: str) -> None:
    start, end = quote["date"].iloc[60], quote["date"].iloc[-80]
    columns = ["stock_code", "close"]
    keep = quote["d_sentinel"] != 0 if date_col == "d_sentinel" else None  # 占位值不是日期，过滤时不保留

    got = dl.read_table("quote.parquet", columns=columns, start=start, end=end.date(), date_col=date_col)

    pd.testing.assert_frame_equal(got, _expected(quote, start, end, columns, keep))
    assert list(got.columns) == columns  # 借来过滤的日期列不留在结果里


@pytest.mark.parametrize("date_col", ["date", "d_iso", "d_int", "d_slash"])
def test_read_table_bounds_with_time_of_day(quote: pd.DataFrame, date_col: str) -> None:
    """起点带时分秒时，当天零点的那些行不算在内：下推与读入后再过滤一个口径。"""
    day = quote["date"].iloc[100]
    got = dl.read_table("quote.parquet", columns=["date"], start=f"{day:%Y-%m-%d} 12:00:00", end=f"{day + pd.Timedelta(days=7):%Y-%m-%d} 12:00:00", date_col=date_col)
    expected = quote.loc[(quote["date"] > day) & (quote["date"] <= day + pd.Timedelta(days=7)), ["date"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(got, expected)


def test_read_table_open_ended_and_no_range(quote: pd.DataFrame) -> None:
    start = quote["date"].iloc[200]
    pd.testing.assert_frame_equal(dl.read_table("quote.parquet", columns=["close"], start=start), _expected(quote, start, None, ["close"]))
    pd.testing.assert_frame_equal(dl.read_table("quote.parquet", columns=["close"], end=start, date_col="d_iso"), _expected(quote, None, start, ["close"]))
    whole = dl.read_table("quote.parquet", columns=["stock_code", "date"])
    pd.testing.assert_frame_equal(whole, quote[["stock_code", "date"]])
    assert len(dl.read_table("quote.parquet")) == len(quote)


def test_read_table_date_stored_as_pandas_index(root: Path) -> None:
    """日期被 pandas 存成索引的表：能下推的照常下推；下推不了的从索引里取出来过滤，结果一样。"""
    frame = _panel(TRADING_DAYS[:20], A_CODES[:3])
    start, end = TRADING_DAYS[5], TRADING_DAYS[12]
    expected = frame[(frame["date"] >= start) & (frame["date"] <= end)]
    slashes = frame["date"].dt.strftime("%Y/%m/%d")  # 这种写法下推不了

    frame.set_index("date").to_parquet(root / "data" / "by_date.parquet")
    got = dl.read_table("by_date.parquet", columns=["close"], start=start, end=end)
    assert got.index.name == "date" and list(got.index) == list(expected["date"]) and got["close"].tolist() == expected["close"].tolist()

    frame.assign(day=slashes).drop(columns="date").set_index("day").to_parquet(root / "data" / "by_day.parquet")
    got = dl.read_table("by_day.parquet", columns=["close"], start=start, end=end, date_col="day")
    assert got.index.name == "day" and list(got.columns) == ["close"]
    assert list(got.index) == slashes[expected.index].tolist() and got["close"].tolist() == expected["close"].tolist()

    frame.drop(columns="date").set_axis(slashes.to_numpy(), axis=0).to_parquet(root / "data" / "unnamed.parquet")
    got = dl.read_table("unnamed.parquet", start=start, end=end, date_col="__index_level_0__")
    assert list(got.index) == slashes[expected.index].tolist() and got["close"].tolist() == expected["close"].tolist()


def test_read_table_finds_date_column_by_common_names(root: Path) -> None:
    frame = _panel(TRADING_DAYS[:20], A_CODES[:3]).rename(columns={"date": "trade_dt", "stock_code": "stcode"})
    frame["trade_dt"] = frame["trade_dt"].dt.strftime("%Y%m%d").astype("int64")
    _write(frame, root / "data" / "factors" / "f1.parquet")
    cut = int(TRADING_DAYS[10].strftime("%Y%m%d"))

    got = dl.read_table("factors/f1.parquet", columns=["stcode", "trade_dt"], start=cut)

    assert got["trade_dt"].min() == cut and got["trade_dt"].dtype == "int64"  # 不替调用方改列类型
    assert len(got) == 10 * 3


def test_read_table_errors(root: Path, quote: pd.DataFrame) -> None:
    _write(pd.DataFrame({"stock_code": ["000001"], "name": ["平安"]}), root / "data" / "static.parquet")
    (root / "data" / "notes.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="找不到日期列"):
        dl.read_table("static.parquet", start="2020-01-01")
    assert len(dl.read_table("static.parquet")) == 1  # 不按日期过滤就不需要日期列
    with pytest.raises(ValueError, match="没有日期列 nope"):
        dl.read_table("quote.parquet", start="2020-01-01", date_col="nope")
    with pytest.raises(ValueError, match="缺少列.*nope"):
        dl.read_table("quote.parquet", columns=["close", "nope"])
    with pytest.raises(ValueError, match="start 不是有效日期"):
        dl.read_table("quote.parquet", start="not-a-date")
    with pytest.raises(FileNotFoundError, match="missing.parquet"):
        dl.read_table("missing.parquet")
    with pytest.raises(ValueError, match="不支持的数据文件格式"):
        dl.read_table("notes.json")


def test_read_table_combines_filters_with_date_range(quote: pd.DataFrame) -> None:
    import pyarrow.compute as pc

    start, end = quote["date"].iloc[60], quote["date"].iloc[-80]
    in_range = (quote["date"] >= start) & (quote["date"] <= end)
    picked = quote["stock_code"].isin(A_CODES[:2])

    flat = dl.read_table("quote.parquet", columns=["stock_code", "close"], start=start, end=end, filters=[("stock_code", "in", A_CODES[:2])])
    pd.testing.assert_frame_equal(flat, quote.loc[in_range & picked, ["stock_code", "close"]].reset_index(drop=True))

    either = dl.read_table("quote.parquet", start=start, end=end, filters=[[("stock_code", "=", A_CODES[0])], [("close", ">", 30.0)]])
    assert len(either) == int((in_range & ((quote["stock_code"] == A_CODES[0]) | (quote["close"] > 30.0))).sum())

    expression = dl.read_table("quote.parquet", columns=["close"], start=start, end=end, date_col="d_slash", filters=pc.field("close") > 30.0)
    pd.testing.assert_frame_equal(expression, quote.loc[in_range & (quote["close"] > 30.0), ["close"]].reset_index(drop=True))


@pytest.mark.parametrize("suffix", [".csv", ".feather", ".xlsx"])
def test_read_table_flat_formats(root: Path, suffix: str) -> None:
    frame = _panel(TRADING_DAYS[:30], A_CODES[:4])
    path = root / "data" / f"quote{suffix}"
    if suffix == ".csv":
        frame.to_csv(path, index=False)
    elif suffix == ".feather":
        frame.to_feather(path)
    else:
        frame.to_excel(path, index=False)
    start, end = TRADING_DAYS[5], TRADING_DAYS[14]

    got = dl.read_table(f"quote{suffix}", columns=["stock_code", "close"], start=start, end=end, filters=[("stock_code", "in", A_CODES[:2])])

    keep = (frame["date"] >= start) & (frame["date"] <= end) & frame["stock_code"].isin(A_CODES[:2])
    assert got["stock_code"].tolist() == frame.loc[keep, "stock_code"].tolist()  # 代码列按文本读，前导零还在
    np.testing.assert_allclose(got["close"].to_numpy(), frame.loc[keep, "close"].to_numpy())
    assert list(got.columns) == ["stock_code", "close"] and list(got.index) == list(range(len(got)))


def test_read_table_reads_overlay_in_trial(root: Path) -> None:
    real = _write(_panel(TRADING_DAYS[:10], A_CODES[:2]), root / "data" / "quote.parquet")
    overlay = _write(_panel(TRADING_DAYS[:10], A_CODES[:2], seed=9), _mock_dir(root) / "files" / "quote.parquet")

    before = dl.read_table("quote.parquet", columns=["close"], start=TRADING_DAYS[2], report_id=CASE)
    _activate(root)
    after = dl.read_table("quote.parquet", columns=["close"], start=TRADING_DAYS[2], report_id=CASE)

    pd.testing.assert_frame_equal(before, pd.read_parquet(real, columns=["close"]).iloc[4:].reset_index(drop=True))
    pd.testing.assert_frame_equal(after, pd.read_parquet(overlay, columns=["close"]).iloc[4:].reset_index(drop=True))
    assert not before.equals(after)


# ---------------------------------------------------------------------------
# results_dir / 数据清单
# ---------------------------------------------------------------------------


def test_results_dir_switches_with_trial(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = dl.results_dir(CASE)
    assert real == root / "output" / CASE / "results" and real.is_dir()

    _activate(root)
    mock = dl.results_dir(CASE)
    assert mock == root / "output" / CASE / "results_mock" and mock.is_dir()

    monkeypatch.setenv("REPRODUCE_REPORT_ID", CASE)
    assert dl.results_dir() == mock
    monkeypatch.delenv("REPRODUCE_REPORT_ID")
    with pytest.raises(ValueError, match="report_id"):
        dl.results_dir()


def test_results_dir_falls_back_to_cwd_without_case_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    monkeypatch.chdir(standalone)

    assert dl.results_dir("lonely") == standalone / "output" / "lonely" / "results"


def test_data_manifest_marks_mock_and_real(root: Path) -> None:
    real = _write(_panel(TRADING_DAYS[:3], A_CODES[:2]), root / "data" / "trade.parquet")
    _write(_panel(TRADING_DAYS[:3], A_CODES[:2]), root / "data" / "quote.parquet")
    overlay = _write(_panel(TRADING_DAYS[:3], A_CODES[:2], seed=1), _mock_dir(root) / "files" / "quote.parquet")
    _activate(root)

    dl.read_table("quote.parquet", report_id=CASE)
    dl.data_path("trade.parquet", CASE)
    dl.data_path("trade.parquet", CASE)  # 同一路径只记一次
    dl.data_path("absent.parquet", CASE)
    target = dl.write_data_manifest(CASE)

    assert target == root / "output" / CASE / "results_mock" / "data_manifest.json"
    manifest = json.loads(target.read_text(encoding="utf-8"))
    assert manifest["report_id"] == CASE and manifest["trial"] is True
    files = {entry["name"]: entry for entry in manifest["files"]}
    assert [entry["name"] for entry in manifest["files"]] == ["quote.parquet", "trade.parquet", "absent.parquet"]
    assert files["quote.parquet"]["source"] == "mock" and files["quote.parquet"]["path"] == str(overlay)
    assert files["trade.parquet"]["source"] == "real" and files["trade.parquet"]["path"] == str(real)
    stat = real.stat()
    assert files["trade.parquet"]["size"] == stat.st_size
    assert files["trade.parquet"]["fingerprint"] == f"{stat.st_size}-{stat.st_mtime_ns}"
    assert files["absent.parquet"] == {"name": "absent.parquet", "path": str(root / "data" / "absent.parquet"), "source": "real", "size": None, "mtime": None, "fingerprint": None}
    # 时间戳都是带 +08:00 的 ISO8601，起点不晚于终点
    for key in ("started_at", "finished_at"):
        assert manifest[key].endswith("+08:00")
    assert datetime.fromisoformat(manifest["started_at"]) <= datetime.fromisoformat(manifest["finished_at"])
    assert datetime.fromisoformat(files["trade.parquet"]["mtime"]).timestamp() == pytest.approx(stat.st_mtime, abs=1)


def test_data_manifest_fingerprint_follows_file(root: Path, tmp_path: Path) -> None:
    path = _write(_panel(TRADING_DAYS[:3], A_CODES[:2]), root / "data" / "quote.parquet")
    dl.data_path("quote.parquet", CASE)
    first = dl.build_data_manifest(CASE)

    _write(_panel(TRADING_DAYS[:30], A_CODES[:4]), path)  # 数据被换过
    dl.data_path("quote.parquet", CASE)
    unchanged = dl.build_data_manifest(CASE)  # 同一进程里同一路径只记首次读到的样子
    dl.reset_data_manifest()
    dl.data_path("quote.parquet", CASE)
    second = dl.build_data_manifest(CASE)

    assert first["trial"] is False and all(entry["source"] == "real" for entry in first["files"])
    assert unchanged["files"] == first["files"]
    assert second["files"][0]["fingerprint"] != first["files"][0]["fingerprint"]
    assert second["files"][0]["size"] == path.stat().st_size

    # 写到指定位置；重复调用以最新的登记表覆盖
    custom = tmp_path / "out" / "manifest.json"
    assert dl.write_data_manifest(CASE, custom) == custom
    dl.data_path("more.parquet", CASE)
    dl.write_data_manifest(CASE, custom)
    assert [entry["name"] for entry in json.loads(custom.read_text(encoding="utf-8"))["files"]] == ["quote.parquet", "more.parquet"]


def test_data_manifest_fills_in_file_that_appears_later(root: Path) -> None:
    dl.data_path("late.parquet", CASE)
    assert dl.build_data_manifest(CASE)["files"][0]["fingerprint"] is None
    _write(_panel(TRADING_DAYS[:3], A_CODES[:2]), root / "data" / "late.parquet")
    dl.data_path("late.parquet", CASE)

    files = dl.build_data_manifest(CASE)["files"]
    assert len(files) == 1 and files[0]["fingerprint"] is not None


def test_write_data_manifest_needs_report_id_or_path(root: Path, tmp_path: Path) -> None:
    dl.data_path("quote.parquet")  # 没有 report_id
    with pytest.raises(ValueError, match="report_id"):
        dl.write_data_manifest()
    manifest = json.loads(dl.write_data_manifest(path=tmp_path / "m.json").read_text(encoding="utf-8"))
    assert manifest["report_id"] is None and manifest["trial"] is False and len(manifest["files"]) == 1

    dl.data_path("quote.parquet", CASE)  # 之后用过 report_id：不传也认得
    assert dl.write_data_manifest() == root / "output" / CASE / "results" / "data_manifest.json"


def test_results_dir_remembers_report_id_for_the_manifest(root: Path) -> None:
    dl.data_path("quote.parquet")  # 取数时没给 report_id
    dl.results_dir(CASE)  # 取结果目录时给了：清单知道该写到哪个案例下
    assert dl.write_data_manifest() == root / "output" / CASE / "results" / "data_manifest.json"


def test_manifest_written_at_exit_even_if_only_results_dir_got_the_report_id(root: Path) -> None:
    _write(_panel(TRADING_DAYS[:5], A_CODES[:3]), root / "data" / "quote.parquet")
    script = root / "plain_main.py"
    script.write_text(
        textwrap.dedent(
            f"""
            from common.data_loader import read_table, results_dir

            frame = read_table("quote.parquet", columns=["close"])  # 没传 report_id，也没有环境变量
            (results_dir("{CASE}") / "rows.txt").write_text(str(len(frame)), encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env["PYTHONPATH"] = str(REPO_ROOT)

    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, cwd=root, timeout=300)

    assert done.returncode == 0, done.stderr
    results = root / "output" / CASE / "results"
    manifest = json.loads((results / "data_manifest.json").read_text(encoding="utf-8"))
    assert (results / "rows.txt").read_text(encoding="utf-8") == "15"
    assert manifest["report_id"] == CASE and manifest["trial"] is False
    assert [(f["name"], f["source"]) for f in manifest["files"]] == [("quote.parquet", "real")]


def test_no_manifest_is_dropped_outside_a_case(tmp_path: Path) -> None:
    """在工作区之外跑的临时脚本（找不到案例，也没建过结果目录）：退出时不凭空建 output/。"""
    elsewhere = tmp_path / "elsewhere"
    _write(_panel(TRADING_DAYS[:5], A_CODES[:3]), elsewhere / "data" / "quote.parquet")
    (elsewhere / ".reproduce.json").write_text(json.dumps({"data_root": str(elsewhere / "data")}), encoding="utf-8")
    script = elsewhere / "adhoc.py"
    script.write_text(f'from common.data_loader import read_table\nprint(len(read_table("quote.parquet", report_id="{CASE}")))\n', encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env["PYTHONPATH"] = str(REPO_ROOT)

    done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, cwd=elsewhere, timeout=300)

    assert done.returncode == 0 and done.stdout.strip() == "15", done.stderr
    assert sorted(p.name for p in elsewhere.iterdir()) == [".reproduce.json", "adhoc.py", "data"]


# ---------------------------------------------------------------------------
# mockdata：规格
# ---------------------------------------------------------------------------


def _docstring_example() -> dict[str, Any]:
    """模块文档字符串里的规格示例。"""
    text = md.__doc__ or ""
    body = text.split("spec.yaml）::", 1)[1].split("synth 的字段类别", 1)[0]
    return yaml.safe_load(textwrap.dedent(body))


def _spec(*tables: dict[str, Any], **top: Any) -> dict[str, Any]:
    """测试用规格：日历与代码指向夹具里的文件。"""
    base = {
        "seed": 11,
        "period": ["2019-01-01", "2019-12-31"],
        "calendar": {"file": "tradeday.parquet", "date_col": "date"},
        "codes": {"file": "stock.parquet", "column": "stock_code", "where": {"list_state": 1}},
    }
    return {**base, **top, "tables": list(tables)}


def test_docstring_example_is_a_valid_spec() -> None:
    example = _docstring_example()
    assert md.validate_spec(example) == []
    assert [sorted(set(t) & {"sample", "borrow", "columns"}) for t in example["tables"]] == [["sample"], ["borrow"], ["columns"]]
    # 示例里把每种字段类别都用到了
    assert {c["kind"] for c in example["tables"][2]["columns"]} == set(md.KINDS)


def test_load_spec_errors(tmp_path: Path) -> None:
    with pytest.raises(md.MockSpecError, match="规格文件不存在"):
        md.load_spec(tmp_path / "absent.yaml")
    broken = tmp_path / "broken.yaml"
    broken.write_text("tables: [\n  - name: x\n", encoding="utf-8")
    with pytest.raises(md.MockSpecError, match="不是合法的 YAML"):
        md.load_spec(broken)
    listed = tmp_path / "list.yaml"
    listed.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(md.MockSpecError, match="顶层必须是映射"):
        md.load_spec(listed)
    good = tmp_path / "good.yaml"
    good.write_text("period: [2019-01-01, 2019-12-31]\ntables:\n  - name: a.parquet\n    rows: 3\n    columns:\n      - {name: v, kind: value}\n", encoding="utf-8")
    assert md.validate_spec(md.load_spec(good)) == []  # YAML 里不加引号的日期也认


SYNTH_KEYS = [{"name": "stock_code", "kind": "code"}, {"name": "date", "kind": "date"}]

BROKEN_SPECS: list[tuple[dict[str, Any], list[str]]] = [
    ({"tables": []}, ["顶层", "tables"]),
    ({"tabels": [], "tables": [{"name": "a.parquet", "rows": 1, "columns": [{"name": "v", "kind": "value"}]}]}, ["顶层", "不认识的字段", "tabels"]),
    (_spec({"columns": SYNTH_KEYS}), ["tables[0]", "name"]),
    (_spec({"name": "a.parquet"}), ["表 a.parquet", "没有写来源"]),
    (_spec({"name": "../a.parquet", "columns": SYNTH_KEYS}), ["表 ../a.parquet", "name", "相对路径"]),
    (_spec({"name": "a.h5", "columns": SYNTH_KEYS}), ["表 a.h5", "后缀"]),
    (_spec({"name": "a.parquet", "columns": SYNTH_KEYS}, {"name": "a.parquet", "columns": SYNTH_KEYS}), ["表 a.parquet", "name 重复"]),
    (_spec({"name": "a.parquet", "freq": "Y", "columns": SYNTH_KEYS}), ["表 a.parquet", "freq", "D / W / M / Q"]),
    (_spec({"name": "a.parquet", "period": ["2020-06-01", "2020-01-01"], "columns": SYNTH_KEYS}), ["表 a.parquet", "period", "晚于"]),
    (_spec({"name": "a.parquet", "period": ["2020-13-01", "2020-12-31"], "columns": SYNTH_KEYS}), ["表 a.parquet", "period", "不是日期"]),
    (_spec({"name": "a.parquet", "n_codes": 0, "columns": SYNTH_KEYS}), ["表 a.parquet", "n_codes"]),
    (_spec({"name": "a.parquet", "source": "borrow", "columns": SYNTH_KEYS}), ["表 a.parquet", "source", "borrow"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "px", "kind": "prices"}]}), ["表 a.parquet", "columns[2]（px）", "kind"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "px", "kind": "price", "start": -1}]}), ["表 a.parquet", "columns[2]（px）", "start"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "px", "kind": "price", "sigma": 1}]}), ["表 a.parquet", "columns[2]（px）", "sigma"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "c", "kind": "category"}]}), ["表 a.parquet", "columns[2]（c）", "values"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "c", "kind": "category", "values": ["a", 1]}]}), ["表 a.parquet", "columns[2]（c）", "values"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "r", "kind": "ratio", "low": 2, "high": 1}]}), ["表 a.parquet", "columns[2]（r）", "low"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "r", "kind": "ratio", "missing": 1.5}]}), ["表 a.parquet", "columns[2]（r）", "missing"]),
    (_spec({"name": "a.parquet", "columns": [{"name": "stock_code", "kind": "code", "missing": 0.1}, SYNTH_KEYS[1]]}), ["表 a.parquet", "columns[0]（stock_code）", "主键"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "hi", "kind": "price", "base": "nope", "role": "high"}]}), ["表 a.parquet", "columns[2]（hi）", "base"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "r", "kind": "return", "of": "date"}]}), ["表 a.parquet", "columns[2]（r）", "of"]),
    (_spec({"name": "a.parquet", "columns": [SYNTH_KEYS[0], {"name": "p", "kind": "publ_date"}]}), ["表 a.parquet", "columns[1]（p）", "date 列"]),
    (_spec({"name": "a.parquet", "columns": [*SYNTH_KEYS, {"name": "date", "kind": "value"}]}), ["表 a.parquet", "列名 date 重复"]),
    (_spec({"name": "a.parquet", "columns": [{"name": "v", "kind": "value"}]}), ["表 a.parquet", "rows"]),
    ({"tables": [{"name": "a.parquet", "columns": SYNTH_KEYS}]}, ["表 a.parquet", "period"]),
    (_spec({"name": "a.parquet", "sample": {"trim": True}}), ["表 a.parquet", "sample.path"]),
    (_spec({"name": "a.parquet", "borrow": {"columns": ["x"]}}), ["表 a.parquet", "borrow.from"]),
    (_spec({"name": "a.parquet", "borrow": {"from": "q.parquet", "dates": {"mode": "stretch"}}}), ["表 a.parquet", "borrow.dates.mode"]),
    (_spec({"name": "a.parquet", "borrow": {"from": "q.parquet", "dates": "shift"}}), ["表 a.parquet", "borrow.dates", "years / months / days"]),
    (_spec({"name": "a.parquet", "borrow": {"from": "q.parquet", "dates": {"mode": "keep", "min_coverage": 0.5}}}), ["表 a.parquet", "borrow.dates", "min_coverage", "resample"]),
    (_spec({"name": "a.parquet", "borrow": {"from": "q.parquet", "dates": {"mode": "resample", "min_coverage": 2}}}), ["表 a.parquet", "borrow.dates", "min_coverage", "0 到 1"]),
    (_spec({"name": "a.parquet", "borrow": {"from": "q.parquet", "codes": {"map": {"a": "b"}, "replace": True}}}), ["表 a.parquet", "borrow.codes", "map 与 replace"]),
    # 不加引号的代码会被 YAML 读成数字（000001 → 1），一律要求写成文本
    (_spec({"name": "a.parquet", "borrow": {"from": "q.parquet", "codes": {"map": {1: "00001"}}}}), ["表 a.parquet", "borrow.codes.map", "加引号"]),
    (_spec({"name": "a.parquet", "borrow": {"from": "q.parquet", "codes": {"map": {"000001": 448}}}}), ["表 a.parquet", "borrow.codes.map", "加引号"]),
    (_spec({"name": "a.parquet", "codes": {"list": [1, 600000]}, "columns": [{"name": "c", "kind": "code"}]}), ["表 a.parquet", "codes.list", "加引号"]),
    (_spec({"name": "a.parquet", "borrow": {"from": "q.parquet", "rename": {"a": "x", "b": "x"}}}), ["表 a.parquet", "borrow.rename"]),
    (_spec({"name": "a.parquet", "calendar": {"date_col": "d"}, "columns": SYNTH_KEYS}), ["表 a.parquet", "calendar", "file"]),
    (_spec({"name": "a.parquet", "codes": {"file": "s.parquet"}, "columns": SYNTH_KEYS}), ["表 a.parquet", "codes", "column"]),
]


@pytest.mark.parametrize("spec,needles", BROKEN_SPECS, ids=[" ".join(needles) for _, needles in BROKEN_SPECS])
def test_validate_spec_names_table_and_field(spec: dict[str, Any], needles: list[str]) -> None:
    errors = md.validate_spec(spec)
    assert any(all(needle in error for needle in needles) for error in errors), errors


def test_validate_spec_reports_every_problem_at_once() -> None:
    spec = _spec(
        {"name": "a.parquet", "freq": "Y", "columns": [*SYNTH_KEYS, {"name": "px", "kind": "prices"}]},
        {"name": "b.parquet", "borrow": {"dates": "resample"}},
    )
    errors = md.validate_spec(spec)
    assert len(errors) == 3
    assert sum("表 a.parquet" in e for e in errors) == 2 and sum("表 b.parquet" in e for e in errors) == 1
    assert md.validate_spec(["not", "a", "mapping"]) == ["顶层: 规格应为映射（键: 值），实际是 list"]


# ---------------------------------------------------------------------------
# mockdata：生成
# ---------------------------------------------------------------------------


@pytest.fixture()
def lake(root: Path) -> Path:
    """数据根里的「真实」数据：交易日历、代码表、日行情、季度财报、整数日期的因子表。"""
    data = root / "data"
    calendar = pd.DataFrame({"date": TRADING_DAYS, "IfTradingDay": 1})
    closed = pd.DataFrame({"date": HOLIDAYS, "IfTradingDay": 2})  # 非交易日也在表里，但标记不是 1
    _write(pd.concat([calendar, closed]).sort_values("date"), data / "tradeday.parquet")
    _write(pd.DataFrame({"stock_code": [*A_CODES, "000003", "600001"], "list_state": [1] * len(A_CODES) + [5, 5]}), data / "stock.parquet")
    _write(pd.DataFrame({"stock_code": HK_CODES}), data / "hk_stock.parquet")

    days_2019 = TRADING_DAYS[(TRADING_DAYS >= "2019-01-01") & (TRADING_DAYS <= "2019-12-31")]
    quote = _panel(days_2019, A_CODES[:8])
    quote["update_time"] = quote["date"] + pd.Timedelta(hours=18)
    _write(quote, data / "quote.parquet", row_group_size=500)

    ends = pd.period_range("2017Q1", "2019Q4", freq="Q").to_timestamp(how="end").normalize()
    income = pd.MultiIndex.from_product([A_CODES[:6], ends], names=["stock_code", "end_date"]).to_frame(index=False)
    rng = np.random.default_rng(3)
    income["info_publ_date"] = income["end_date"] + pd.to_timedelta(rng.integers(20, 110, len(income)), unit="D")
    income["revenue"] = np.round(rng.lognormal(20.0, 1.0, len(income)), 2)
    income.loc[rng.random(len(income)) < 0.15, "revenue"] = np.nan
    _write(income, data / "income.parquet")

    factor = _panel(days_2019[:60], A_CODES[:5], seed=5).rename(columns={"stock_code": "stcode", "date": "trade_dt"})
    factor["trade_dt"] = factor["trade_dt"].dt.strftime("%Y%m%d").astype("int64")
    _write(factor[["stcode", "trade_dt", "close"]], data / "factor.parquet")
    return data


def _generate(root: Path, spec: dict[str, Any], out: Optional[Path] = None, **kwargs: Any) -> dict[str, Any]:
    out = out or _mock_dir(root) / "files"
    return md.generate(spec, out, root / "data", root=root, spec_path=_mock_dir(root) / "spec.yaml", report_id=CASE, **kwargs)


def _table(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(entry for entry in manifest["tables"] if entry["name"] == name)


def test_sample_is_copied_verbatim_or_trimmed(root: Path, lake: Path) -> None:
    samples = _mock_dir(root) / "samples"
    same = _write(_panel(TRADING_DAYS[300:310], A_CODES[:3]), samples / "rating.parquet")
    samples.joinpath("survey.csv").write_text(
        "stock_code,survey_date,score\n000001,2018-12-28,1.5\n000002,2019-03-01,2.5\n600000,20190615,3.5\n000001,2020-01-02,4.5\n", encoding="utf-8"
    )
    spec = _spec(
        {"name": "rating.parquet", "sample": {"path": "samples/rating.parquet"}},
        {"name": "sub/survey.parquet", "sample": {"path": str(samples / "survey.csv"), "trim": True, "date_col": "survey_date"}},
    )

    manifest = _generate(root, spec)
    files = _mock_dir(root) / "files"

    rating = _table(manifest, "rating.parquet")
    assert rating["source"] == "sample" and rating["sha256"] == _sha(same) == _sha(files / "rating.parquet")  # 原样拷贝
    assert (rating["rows"], rating["n_codes"], rating["date_column"]) == (30, 3, "date")
    assert (rating["date_min"], rating["date_max"]) == (f"{TRADING_DAYS[300]:%Y-%m-%d}", f"{TRADING_DAYS[309]:%Y-%m-%d}")

    survey = pd.read_parquet(files / "sub" / "survey.parquet")
    assert survey["stock_code"].tolist() == ["000002", "600000"]  # 按 period 截取，前导零还在
    assert survey["survey_date"].tolist() == [pd.Timestamp("2019-03-01"), pd.Timestamp("2019-06-15")]  # 转存时解析成日期
    entry = _table(manifest, "sub/survey.parquet")
    assert (entry["rows"], entry["date_min"], entry["date_max"], entry["n_codes"]) == (2, "2019-03-01", "2019-06-15", 2)
    assert not (_mock_dir(root) / "ACTIVE").exists()  # 生成不负责试跑标记
    assert json.loads((_mock_dir(root) / "manifest.json").read_text(encoding="utf-8"))["tables"] == manifest["tables"]


def test_borrow_keeps_values_and_gaps(root: Path, lake: Path) -> None:
    spec = _spec(
        {
            "name": "quote_x.parquet",
            "period": ["2019-03-01", "2019-04-30"],
            "borrow": {
                "from": "quote.parquet",
                "columns": ["stock_code", "date", "close", "volume"],
                "rename": {"stock_code": "secu_code", "close": "px"},
                "codes": {"map": {"000001": "X00001", "000002": "X00002"}},
            },
        }
    )

    manifest = _generate(root, spec)

    got = pd.read_parquet(_mock_dir(root) / "files" / "quote_x.parquet")
    source = pd.read_parquet(lake / "quote.parquet")
    source = source[(source["date"] >= "2019-03-01") & (source["date"] <= "2019-04-30")].reset_index(drop=True)
    assert list(got.columns) == ["secu_code", "date", "px", "volume"]
    assert got["secu_code"].tolist() == source["stock_code"].replace({"000001": "X00001", "000002": "X00002"}).tolist()
    pd.testing.assert_series_equal(got["date"], source["date"])
    np.testing.assert_array_equal(got["px"].to_numpy(), source["close"].to_numpy())
    np.testing.assert_array_equal(got["volume"].to_numpy(), source["volume"].to_numpy())  # 空值的位置也一样
    assert got["volume"].isna().any()
    borrowed, original = pq.read_schema(_mock_dir(root) / "files" / "quote_x.parquet"), pq.read_schema(lake / "quote.parquet")
    assert borrowed.types == [original.field(name).type for name in ("stock_code", "date", "close", "volume")]  # 列类型与源表一致
    entry = _table(manifest, "quote_x.parquet")
    assert (entry["source"], entry["rows"], entry["code_column"], entry["n_codes"], entry["fallbacks"]) == ("borrow", len(source), "secu_code", 8, [])


def test_borrow_replaces_codes_and_resamples_onto_calendar(root: Path, lake: Path) -> None:
    spec = _spec(
        {
            "name": "hk_quote.parquet",
            "period": ["2018-07-02", "2018-12-31"],
            "n_codes": 4,
            "borrow": {"from": "quote.parquet", "codes": {"replace": {"file": "hk_stock.parquet", "column": "stock_code"}}, "dates": "resample"},
        }
    )

    manifest = _generate(root, spec)

    got = pd.read_parquet(_mock_dir(root) / "files" / "hk_quote.parquet")
    source = pd.read_parquet(lake / "quote.parquet")
    wanted = TRADING_DAYS[(TRADING_DAYS >= "2018-07-02") & (TRADING_DAYS <= "2018-12-31")]
    assert sorted(got["date"].unique()) == list(wanted)  # 日期一一落在真实日历上
    assert set(got["stock_code"]) <= set(HK_CODES) and got["stock_code"].nunique() == 4
    assert len(got) == len(wanted) * 4
    # 取的是源表最近的一段，逐日对应：每个目标日的截面就是对应源日期的截面（数值、空值原样）
    used = sorted(source["date"].unique())[-len(wanted):]
    for target_day, source_day in ((wanted[0], used[0]), (wanted[-1], used[-1])):
        ours = got.loc[got["date"] == target_day, "close"].to_numpy()
        theirs = source.loc[source["date"] == source_day, "close"].to_numpy()
        assert set(ours) <= set(theirs) and len(ours) == 4
    assert ((got["update_time"] - got["date"]) == pd.Timedelta(hours=18)).all()  # 其他日期列跟着一起挪
    entry = _table(manifest, "hk_quote.parquet")
    assert (entry["date_min"], entry["date_max"], entry["n_codes"]) == ("2018-07-02", "2018-12-31", 4)
    assert any("update_time" in note for note in entry["notes"])


def test_borrow_resample_tiles_when_source_is_short(root: Path, lake: Path) -> None:
    spec = _spec(
        {
            "name": "factor_long.parquet",
            "period": ["2018-01-02", "2018-12-31"],
            "borrow": {"from": "factor.parquet", "dates": {"mode": "resample"}},
        }
    )

    manifest = _generate(root, spec)

    got = pd.read_parquet(_mock_dir(root) / "files" / "factor_long.parquet")
    wanted = TRADING_DAYS[(TRADING_DAYS >= "2018-01-02") & (TRADING_DAYS <= "2018-12-31")]
    assert got["trade_dt"].dtype == "int64"  # 整数日期还是整数日期
    assert sorted(got["trade_dt"].unique()) == [int(f"{day:%Y%m%d}") for day in wanted]
    assert len(got) == len(wanted) * 5 and set(got["stcode"]) == set(A_CODES[:5])
    source = pd.read_parquet(lake / "factor.parquet")
    last = got[got["trade_dt"] == int(f"{wanted[-1]:%Y%m%d}")]
    np.testing.assert_array_equal(last["close"].to_numpy(), source[source["trade_dt"] == source["trade_dt"].max()]["close"].to_numpy())
    assert any("循环铺满" in note for note in _table(manifest, "factor_long.parquet")["notes"])


def test_borrow_resample_skips_sparse_source_dates(root: Path, lake: Path) -> None:
    """真实表常有「早年只有零星几个标的」的情况：这样的日期不拿来铺，否则目标区间里会整段没有数据。"""
    days = TRADING_DAYS[TRADING_DAYS.year == 2019]
    thin = _panel(days[:40], A_CODES[:1])  # 前 40 天只有 1 个标的
    full = _panel(days[40:100], [*A_CODES, *HK_CODES], seed=2)  # 之后 60 天有 16 个
    _write(pd.concat([thin, full], ignore_index=True), lake / "collapsed.parquet")
    wanted = TRADING_DAYS[(TRADING_DAYS >= "2018-01-02") & (TRADING_DAYS <= "2018-06-29")]

    def table(name: str, **dates: Any) -> dict[str, Any]:
        # 只取后 4 个代码（那 40 天里没有它们）
        borrow = {
            "from": "collapsed.parquet",
            "codes": {"map": {code: code for code in A_CODES[1:5]}, "drop_unmapped": True},
            "dates": {"mode": "resample", "source_period": ["2019-01-01", "2019-12-31"], **dates},
        }
        return {"name": name, "period": ["2018-01-02", "2018-06-29"], "borrow": borrow}

    manifest = _generate(root, _spec(table("dense.parquet"), table("naive.parquet", min_coverage=0)))

    dense = pd.read_parquet(_mock_dir(root) / "files" / "dense.parquet")
    assert sorted(dense["date"].unique()) == list(wanted)  # 每个目标日期都有数据
    assert (dense.groupby("date").size() == 4).all() and set(dense["stock_code"]) == set(A_CODES[1:5])
    notes = " ".join(_table(manifest, "dense.parquet")["notes"])
    assert "40 个日期的行数不到峰值的 10%" in notes and "循环铺满" in notes and "只有" not in notes.split("循环铺满")[1]
    # 关掉筛选（min_coverage: 0）就会把那 40 天也铺进去：目标区间里有一段没有数据，清单里如实写明
    naive = pd.read_parquet(_mock_dir(root) / "files" / "naive.parquet")
    notes = " ".join(_table(manifest, "naive.parquet")["notes"])
    assert naive["date"].nunique() == len(wanted) - 40 and "截面太稀" not in notes
    assert f"目标区间要 {len(wanted)} 个日期，生成的表里只有 {len(wanted) - 40} 个日期有数据" in notes


def test_borrow_whole_table_without_period(root: Path, lake: Path) -> None:
    spec = {"tables": [{"name": "copy.parquet", "borrow": {"from": "income.parquet", "rename": {"revenue": "rev"}}}]}

    manifest = _generate(root, spec)

    got, source = pd.read_parquet(_mock_dir(root) / "files" / "copy.parquet"), pd.read_parquet(lake / "income.parquet")
    pd.testing.assert_frame_equal(got, source.rename(columns={"revenue": "rev"}))  # 不截取、不改键：整张表原样
    entry = _table(manifest, "copy.parquet")
    assert (entry["rows"], entry["date_column"], entry["date_min"], entry["date_max"]) == (len(source), "end_date", "2017-03-31", "2019-12-31")


def test_borrow_shift_keeps_quarter_ends_and_publication_lag(root: Path, lake: Path) -> None:
    spec = _spec(
        {
            "name": "income_ext.parquet",
            "period": ["2021-01-01", "2022-12-31"],
            "borrow": {"from": "income.parquet", "dates": {"mode": "shift", "years": 3}},
        }
    )

    _generate(root, spec)

    got = pd.read_parquet(_mock_dir(root) / "files" / "income_ext.parquet")
    source = pd.read_parquet(lake / "income.parquet")
    source = source[(source["end_date"] >= "2018-01-01") & (source["end_date"] <= "2019-12-31")].reset_index(drop=True)
    assert len(got) == len(source) == 6 * 8
    assert got["end_date"].dt.is_quarter_end.all() and got["end_date"].dt.year.isin([2021, 2022]).all()
    pd.testing.assert_series_equal(got["info_publ_date"] - got["end_date"], source["info_publ_date"] - source["end_date"])  # 披露滞后原样
    np.testing.assert_array_equal(got["revenue"].to_numpy(), source["revenue"].to_numpy())
    assert got["stock_code"].tolist() == source["stock_code"].tolist()


def test_borrow_downsamples_and_subsets_codes_consistently(root: Path, lake: Path) -> None:
    def table(name: str, n_codes: int) -> dict[str, Any]:
        return {"name": name, "freq": "M", "n_codes": n_codes, "borrow": {"from": "quote.parquet", "columns": ["stock_code", "date", "close"]}}

    _generate(root, _spec(table("three.parquet", 3), table("five.parquet", 5)))

    three = pd.read_parquet(_mock_dir(root) / "files" / "three.parquet")
    five = pd.read_parquet(_mock_dir(root) / "files" / "five.parquet")
    month_ends = pd.Series(TRADING_DAYS[TRADING_DAYS.year == 2019]).groupby(TRADING_DAYS[TRADING_DAYS.year == 2019].month).max().tolist()
    assert sorted(five["date"].unique()) == month_ends  # 每月只留最后一个交易日
    assert three["stock_code"].nunique() == 3 and five["stock_code"].nunique() == 5
    assert set(three["stock_code"]) < set(five["stock_code"]) <= set(A_CODES[:8])  # 少的是多的子集，各表对得上


def test_borrow_reports_columns_missing_in_source(root: Path, lake: Path) -> None:
    spec = _spec({"name": "x.parquet", "borrow": {"from": "quote.parquet", "columns": ["stock_code", "turnover"]}})
    with pytest.raises(md.MockDataError, match=r"表 x.parquet: borrow.columns 里的列 \['turnover'\]"):
        _generate(root, spec)
    plans = md.inspect_sources(spec, lake, root=root)
    assert plans[0]["source"] == "borrow" and "turnover" in plans[0]["errors"][0]
    empty = _spec({"name": "y.parquet", "period": ["2010-01-01", "2010-12-31"], "borrow": {"from": "quote.parquet"}})
    with pytest.raises(md.MockDataError, match="表 y.parquet: 源表 quote.parquet 在目标区间 2010-01-01 ~ 2010-12-31 内没有数据"):
        _generate(root, empty)
    strangers = _spec({"name": "z.parquet", "borrow": {"from": "quote.parquet", "codes": {"map": {"999999": "X"}}}})
    with pytest.raises(md.MockDataError, match="表 z.parquet: borrow.codes.map 的键没有一个出现在源表"):
        _generate(root, strangers)
    # 读日历、读代码表时才发现的问题，报错里同样带表名
    no_column = {"tables": [{"name": "w.parquet", "codes": {"file": "stock.parquet", "column": "nope"}, "columns": [{"name": "c", "kind": "code"}]}]}
    with pytest.raises(md.MockDataError, match=r"表 w.parquet: .*stock.parquet 里没有列 \['nope'\]"):
        _generate(root, no_column)
    assert not (_mock_dir(root) / "files").exists()  # 失败时不留半成品


SYNTH_COLUMNS: list[dict[str, Any]] = [
    {"name": "stock_code", "kind": "code"},
    {"name": "date", "kind": "date"},
    {"name": "close", "kind": "price", "start": [5, 80], "vol": 0.03},
    {"name": "open", "kind": "price", "base": "close", "role": "open"},
    {"name": "high", "kind": "price", "base": "close", "role": "high"},
    {"name": "low", "kind": "price", "base": "close", "role": "low"},
    {"name": "prev_close", "kind": "price", "base": "close", "role": "prev_close"},
    {"name": "ret", "kind": "return", "of": "close", "unit": "percent"},
    {"name": "noise", "kind": "return", "std": 0.01},
    {"name": "volume", "kind": "volume", "zero_rate": 0.2},
    {"name": "amount", "kind": "amount"},
    {"name": "turnover", "kind": "ratio", "low": 0.0, "high": 0.2},
    {"name": "beta", "kind": "ratio", "dist": "normal", "mean": 1.0, "std": 0.3, "low": 0.0},
    {"name": "n_reports", "kind": "count", "mean": 3},
    {"name": "n_analysts", "kind": "count", "low": 2, "high": 4, "missing": 0.3},
    {"name": "industry", "kind": "category", "values": ["银行", "医药", "电子"], "per": "code"},
    {"name": "rating", "kind": "category", "values": [1, 2, 3], "weights": [1, 0, 0]},
    {"name": "is_st", "kind": "flag", "rate": 0.3},
    {"name": "stock_name", "kind": "text", "length": 6, "prefix": "N"},
    {"name": "score", "kind": "value", "mean": 5.0, "std": 1.0, "missing": 0.25},
    {"name": "level", "kind": "value", "walk": True},
    {"name": "info_publ_date", "kind": "publ_date", "lag_days": [10, 45]},
    {"name": "ann_dt", "kind": "publ_date", "lag_days": 3, "dtype": "int"},
]


def test_synth_field_kinds(root: Path, lake: Path) -> None:
    manifest = _generate(root, _spec({"name": "synth.parquet", "n_codes": 6, "columns": SYNTH_COLUMNS}))

    got = pd.read_parquet(_mock_dir(root) / "files" / "synth.parquet")
    days = TRADING_DAYS[TRADING_DAYS.year == 2019]
    assert list(got.columns) == [c["name"] for c in SYNTH_COLUMNS]
    assert len(got) == len(days) * 6 and not got.duplicated(["stock_code", "date"]).any()
    assert sorted(got["date"].unique()) == list(days)
    assert (got[["close", "open", "high", "low", "prev_close"]] > 0).all().all()
    body = got[["open", "close", "prev_close"]]
    assert (got["high"] >= body.max(axis=1)).all() and (got["low"] <= body.min(axis=1)).all()
    by_code = got.sort_values(["stock_code", "date"]).groupby("stock_code")
    np.testing.assert_allclose(by_code["close"].shift(1).dropna(), got.sort_values(["stock_code", "date"])["prev_close"][by_code.cumcount() > 0])
    np.testing.assert_allclose((by_code["close"].pct_change() * 100).dropna(), got.sort_values(["stock_code", "date"])["ret"].dropna())
    assert got["ret"].isna().sum() == 6  # 每个代码的首期没有收益
    assert got["noise"].abs().max() < 0.1
    assert (got["volume"] >= 0).all() and 0.1 < (got["volume"] == 0).mean() < 0.3 and (got["volume"] % 1 == 0).all()
    assert (got["amount"] > 0).all()
    assert got["turnover"].between(0, 0.2).all() and (got["beta"] >= 0).all()
    assert got["n_reports"].dtype == "int64" and (got["n_reports"] >= 0).all()
    analysts = got["n_analysts"].dropna()
    assert set(analysts.unique()) == {2, 3, 4} and 0.2 < got["n_analysts"].isna().mean() < 0.4
    assert set(got["industry"].unique()) <= {"银行", "医药", "电子"} and (got.groupby("stock_code")["industry"].nunique() == 1).all()
    assert (got["rating"] == 1).all()  # 权重全压在第一个取值上
    assert set(got["is_st"].unique()) == {0, 1} and 0.2 < got["is_st"].mean() < 0.4
    assert got["stock_name"].str.fullmatch(r"N[a-z0-9]{6}").all() and (got.groupby("stock_code")["stock_name"].nunique() == 1).all()
    assert 0.15 < got["score"].isna().mean() < 0.35 and got["score"].mean() == pytest.approx(5.0, abs=0.2)
    lag = (got["info_publ_date"] - got["date"]).dt.days
    assert lag.between(10, 45).all() and lag.nunique() > 10  # 披露日晚于报告期
    assert (pd.to_datetime(got["ann_dt"].astype(str), format="%Y%m%d") - got["date"]).dt.days.eq(3).all()
    schema = pq.read_schema(_mock_dir(root) / "files" / "synth.parquet")
    assert schema.field("date").type == pa.timestamp("us") and schema.field("stock_code").type == pa.large_string()
    assert schema.field("n_analysts").type == pa.int64() and schema.field("ann_dt").type == pa.int64()
    entry = _table(manifest, "synth.parquet")
    assert (entry["source"], entry["rows"], entry["n_codes"], entry["date_min"], entry["date_max"]) == ("synth", len(got), 6, f"{days[0]:%Y-%m-%d}", f"{days[-1]:%Y-%m-%d}")
    assert len(entry["sha256"]) == 64 and entry["columns"] == list(got.columns)  # 列名列表，内核拿它和真实文件的列名比
    assert entry["dtypes"] == {field.name: str(field.type) for field in schema}


def test_synth_shapes_without_full_keys(root: Path, lake: Path) -> None:
    spec = _spec(
        {"name": "series.csv", "freq": "W", "columns": [{"name": "date", "kind": "date", "dtype": "str"}, {"name": "rate", "kind": "value", "mean": 3.0, "std": 0.1}]},
        {"name": "static.feather", "n_codes": 4, "columns": [{"name": "stock_code", "kind": "code"}, {"name": "industry", "kind": "category", "values": ["a", "b"]}]},
        {"name": "plain.parquet", "rows": 7, "columns": [{"name": "v", "kind": "count"}]},
        {"name": "report.parquet", "freq": "Q", "n_codes": 3, "drop_rows": 0.5,
         "columns": [{"name": "stock_code", "kind": "code"}, {"name": "end_date", "kind": "date", "anchor": "natural"}, {"name": "eps", "kind": "value"}]},
    )

    manifest = _generate(root, spec)
    files = _mock_dir(root) / "files"

    series = pd.read_csv(files / "series.csv")
    week_ends = pd.Series(TRADING_DAYS).groupby(TRADING_DAYS.to_period("W-SUN")).max()
    # 每周最后一个交易日，文本写法；2019-12-31 是周二，那一周的最后一个交易日在 2020 年，不算
    assert series["date"].tolist() == [f"{day:%Y-%m-%d}" for day in week_ends if day.year == 2019]
    assert series["date"].iloc[-1] == "2019-12-27"
    static = pd.read_feather(files / "static.feather")
    assert len(static) == 4 and set(static["stock_code"]) <= set(A_CODES)
    assert len(pd.read_parquet(files / "plain.parquet")) == 7
    report = pd.read_parquet(files / "report.parquet")
    assert set(report["end_date"]) <= set(pd.to_datetime(["2019-03-31", "2019-06-30", "2019-09-30", "2019-12-31"]))  # 自然季末
    assert 0 < len(report) < 12  # 丢了一部分行
    assert [(_table(manifest, n)["date_column"], _table(manifest, n)["code_column"]) for n in ("series.csv", "static.feather", "plain.parquet")] == [("date", None), (None, "stock_code"), (None, None)]


def test_generate_twice_gives_identical_files(root: Path, lake: Path, tmp_path: Path) -> None:
    spec = _spec(
        {"name": "synth.parquet", "n_codes": 6, "columns": SYNTH_COLUMNS},
        {"name": "hk.parquet", "period": ["2018-07-02", "2018-12-31"], "n_codes": 4, "borrow": {"from": "quote.parquet", "codes": {"replace": True}, "dates": "resample"}},
    )

    first = _generate(root, spec, out=tmp_path / "one" / "files")
    second = _generate(root, spec, out=tmp_path / "two" / "files")

    assert [t["sha256"] for t in first["tables"]] == [t["sha256"] for t in second["tables"]]
    assert first["spec_sha256"] == second["spec_sha256"]
    for name in ("synth.parquet", "hk.parquet"):
        assert (tmp_path / "one" / "files" / name).read_bytes() == (tmp_path / "two" / "files" / name).read_bytes()
    # 增删别的列不影响已有列；换种子才会变
    fewer = _spec({"name": "synth.parquet", "n_codes": 6, "columns": [c for c in SYNTH_COLUMNS if c["name"] not in ("noise", "amount")]})
    _generate(root, fewer, out=tmp_path / "three" / "files")
    full, part = pd.read_parquet(tmp_path / "one" / "files" / "synth.parquet"), pd.read_parquet(tmp_path / "three" / "files" / "synth.parquet")
    pd.testing.assert_frame_equal(full[part.columns], part)
    _generate(root, {**spec, "seed": 12}, out=tmp_path / "four" / "files")
    assert not pd.read_parquet(tmp_path / "four" / "files" / "synth.parquet")["close"].equals(full["close"])


def test_generate_aligns_with_real_calendar_and_codes(root: Path, lake: Path) -> None:
    spec = _spec(
        {"name": "daily.parquet", "period": ["2019-01-28", "2019-02-15"], "n_codes": 5, "columns": [*SYNTH_KEYS, {"name": "v", "kind": "value"}]},
        {"name": "more.parquet", "period": ["2019-01-28", "2019-02-15"], "n_codes": 8, "columns": [*SYNTH_KEYS, {"name": "w", "kind": "value"}]},
        {"name": "listed.parquet", "n_codes": 3, "codes": {"list": ["B", "A", "C", "D"]}, "columns": [SYNTH_KEYS[0], {"name": "v", "kind": "flag"}]},
    )

    manifest = _generate(root, spec)

    daily = pd.read_parquet(_mock_dir(root) / "files" / "daily.parquet")
    more = pd.read_parquet(_mock_dir(root) / "files" / "more.parquet")
    days = sorted(daily["date"].unique())
    assert pd.Timestamp("2019-02-04") not in days and pd.Timestamp("2019-02-05") not in days  # 节假日不在真实日历里
    assert days == list(TRADING_DAYS[(TRADING_DAYS >= "2019-01-28") & (TRADING_DAYS <= "2019-02-15")])
    assert set(daily["stock_code"]) < set(more["stock_code"]) <= set(A_CODES)  # 已退市的两只（list_state=5）不取
    assert len(daily.merge(more, on=["stock_code", "date"])) == len(daily)  # 与别的表按代码、日期对得上
    assert set(pd.read_parquet(_mock_dir(root) / "files" / "listed.parquet")["stock_code"]) < {"A", "B", "C", "D"}
    assert manifest["fallbacks"] == [] and all(t["fallbacks"] == [] for t in manifest["tables"])


def test_generate_falls_back_without_calendar_and_codes(root: Path) -> None:
    spec = {
        "period": ["2019-01-28", "2019-02-15"],
        "n_codes": 3,
        "tables": [{"name": "daily.parquet", "columns": [*SYNTH_KEYS, {"name": "v", "kind": "value"}]}],
    }

    manifest = _generate(root, spec)  # 数据根是空的

    daily = pd.read_parquet(_mock_dir(root) / "files" / "daily.parquet")
    assert sorted(daily["date"].unique()) == list(pd.bdate_range("2019-01-28", "2019-02-15"))  # 工作日日历
    assert sorted(daily["stock_code"].unique()) == ["000001", "000002", "000003"]  # 自造代码
    kinds = {item["kind"]: item["detail"] for item in _table(manifest, "daily.parquet")["fallbacks"]}
    assert "工作日日历" in kinds["calendar"] and "ashare_tradeday.parquet" in kinds["calendar"]
    assert "自造代码" in kinds["codes"] and "ashare_stock.parquet" in kinds["codes"]
    assert [item["table"] for item in manifest["fallbacks"]] == ["daily.parquet", "daily.parquet"]


def test_generate_pads_calendar_outside_its_coverage(root: Path, lake: Path) -> None:
    spec = _spec({"name": "late.parquet", "period": ["2020-12-21", "2021-01-15"], "columns": [SYNTH_KEYS[1], {"name": "v", "kind": "value"}]})

    manifest = _generate(root, spec)

    late = pd.read_parquet(_mock_dir(root) / "files" / "late.parquet")
    expected = list(TRADING_DAYS[TRADING_DAYS >= "2020-12-21"]) + list(pd.bdate_range("2021-01-01", "2021-01-15"))
    assert late["date"].tolist() == expected
    assert "只覆盖" in _table(manifest, "late.parquet")["fallbacks"][0]["detail"]


def test_source_priority_and_fallback(root: Path, lake: Path) -> None:
    columns = [*SYNTH_KEYS, {"name": "close", "kind": "price"}]
    chain = {"name": "t.parquet", "n_codes": 3, "sample": {"path": "samples/t.parquet"}, "borrow": {"from": "quote.parquet", "columns": ["stock_code", "date", "close"]}, "columns": columns}

    borrowed = _generate(root, _spec(chain))  # 样例文件不存在：退回 borrow
    entry = _table(borrowed, "t.parquet")
    assert entry["source"] == "borrow"
    assert [(item["kind"], "sample" in item["detail"], "退回 borrow" in item["detail"]) for item in entry["fallbacks"]] == [("source", True, True)]

    synthetic = _generate(root, _spec({**chain, "borrow": {"from": "nowhere.parquet"}}))  # 源表也不存在：退回 synth
    entry = _table(synthetic, "t.parquet")
    assert entry["source"] == "synth" and len(entry["fallbacks"]) == 2 and all("退回 synth" in item["detail"] for item in entry["fallbacks"])

    _write(_panel(TRADING_DAYS[300:303], A_CODES[:2]), _mock_dir(root) / "samples" / "t.parquet")
    sampled = _generate(root, _spec(chain))  # 样例文件到位：用它
    assert _table(sampled, "t.parquet")["source"] == "sample" and _table(sampled, "t.parquet")["fallbacks"] == []

    pinned = _generate(root, _spec({**chain, "source": "synth"}))  # 写死来源
    assert _table(pinned, "t.parquet")["source"] == "synth" and _table(pinned, "t.parquet")["fallbacks"] == []

    plans = md.inspect_sources(_spec({**chain, "sample": {"path": "samples/none.parquet"}}), lake, root=root, spec_path=_mock_dir(root) / "spec.yaml")
    assert (plans[0]["source"], plans[0]["errors"], len(plans[0]["fallbacks"])) == ("borrow", [], 1)
    with pytest.raises(md.MockDataError, match="表 t.parquet: 没有可用的来源.*样例文件不存在.*源表不存在"):
        _generate(root, _spec({"name": "t.parquet", "sample": {"path": "samples/none.parquet"}, "borrow": {"from": "nowhere.parquet"}}))
    with pytest.raises(md.MockDataError, match="表 t.parquet: 没有可用的来源.*样例文件不存在"):
        _generate(root, _spec({**chain, "source": "sample", "sample": {"path": "samples/none.parquet"}}))


def test_generate_replaces_stale_files_and_is_all_or_nothing(root: Path, lake: Path) -> None:
    files = _mock_dir(root) / "files"
    one = {"name": "one.parquet", "rows": 3, "columns": [{"name": "v", "kind": "value"}]}
    two = {"name": "sub/two.parquet", "rows": 3, "columns": [{"name": "v", "kind": "value"}]}
    _generate(root, _spec(one, two))
    (files / "by_hand.parquet").write_bytes(b"kept")  # 不是生成器写的文件不动
    before = _sha(files / "one.parquet")

    # 第二张表会失败：整次生成不落盘，已有文件原样
    with pytest.raises(md.MockDataError, match="表 bad.parquet"):
        _generate(root, _spec({**one, "rows": 9}, {"name": "bad.parquet", "source": "borrow", "borrow": {"from": "quote.parquet", "columns": ["nope"]}}))
    assert _sha(files / "one.parquet") == before and (files / "sub" / "two.parquet").is_file()
    assert sorted(p.name for p in _mock_dir(root).iterdir()) == ["files", "manifest.json"]  # 暂存目录已清掉

    manifest = _generate(root, _spec(one))  # 规格里去掉了第二张表：旧文件删掉，免得继续盖住真实数据
    assert manifest["removed"] == ["sub/two.parquet"] and not (files / "sub" / "two.parquet").exists()
    assert (files / "by_hand.parquet").read_bytes() == b"kept" and _sha(files / "one.parquet") == before


def test_generate_refuses_to_write_into_data_root(root: Path, lake: Path) -> None:
    spec = _spec({"name": "quote.parquet", "rows": 3, "columns": [{"name": "v", "kind": "value"}]})
    before = _sha(lake / "quote.parquet")
    for out in (lake, lake / "mock", root):
        with pytest.raises(md.MockDataError, match="重叠"):
            md.generate(spec, out, lake, root=root)
    assert _sha(lake / "quote.parquet") == before
    with pytest.raises(md.MockSpecError) as excinfo:
        md.generate({"tables": [{"name": "a.parquet"}]}, root / "x" / "files", lake, root=root)
    assert excinfo.value.errors == ["表 a.parquet: 没有写来源，至少要有 sample / borrow / columns（synth）之一"]
    with pytest.raises(md.MockDataError, match="超过上限 10"):
        md.generate({**_spec({"name": "big.parquet", "columns": SYNTH_KEYS}), "max_rows": 10}, root / "x" / "files", lake, root=root)


# ---------------------------------------------------------------------------
# mockdata：命令行
# ---------------------------------------------------------------------------


def _write_spec(root: Path, spec: dict[str, Any]) -> Path:
    path = _mock_dir(root) / "spec.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_cli_check_and_generate(root: Path, lake: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(root))
    _write_spec(root, _spec({"name": "daily.parquet", "n_codes": 3, "sample": {"path": "samples/absent.csv"}, "columns": [*SYNTH_KEYS, {"name": "v", "kind": "value"}]}))

    assert md.main(["check", CASE]) == 0
    checked = capsys.readouterr()
    assert "规格合法" in checked.out and "daily.parquet: 将用 synth" in checked.out and "退回 synth" in checked.out
    assert not (_mock_dir(root) / "files").exists()  # check 不生成

    assert md.main(["generate", CASE]) == 0
    generated = capsys.readouterr()
    assert "已生成 1 张表" in generated.out and "daily.parquet: synth" in generated.out
    manifest = json.loads((_mock_dir(root) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["report_id"] == CASE and manifest["data_root"] == str(lake) and manifest["out_dir"] == str(_mock_dir(root) / "files")
    assert (_mock_dir(root) / "files" / "daily.parquet").is_file() and not (_mock_dir(root) / "ACTIVE").exists()


def test_generate_called_the_way_the_kernel_calls_it(root: Path, lake: Path) -> None:
    """内核只传（规格, 覆盖目录, 数据根）：案例编号、样例文件的位置按目录布局推出来；清单是纯 JSON，列名可直接比。"""
    _write(_panel(TRADING_DAYS[300:310], A_CODES[:3]), _mock_dir(root) / "samples" / "rating.parquet")
    _write_spec(
        root,
        _spec(
            {"name": "rating.parquet", "sample": {"path": "samples/rating.parquet"}},
            {"name": "daily.parquet", "n_codes": 3, "columns": [*SYNTH_KEYS, {"name": "v", "kind": "value"}]},
        ),
    )
    spec = md.load_spec(_mock_dir(root) / "spec.yaml")
    assert md.validate_spec(spec) == []

    manifest = md.generate(spec, _mock_dir(root) / "files", lake)

    assert manifest["report_id"] == CASE
    assert [(t["name"], t["source"], t["fallbacks"]) for t in manifest["tables"]] == [("rating.parquet", "sample", []), ("daily.parquet", "synth", [])]
    assert json.loads(json.dumps(manifest)) == manifest  # 纯 JSON 类型：内核会把返回值原样再写一遍
    assert json.loads((_mock_dir(root) / "manifest.json").read_text(encoding="utf-8")) == manifest
    daily = pd.read_parquet(_mock_dir(root) / "files" / "daily.parquet")
    assert set(_table(manifest, "daily.parquet")["columns"]) == set(daily.columns)  # 内核拿它和真实文件的列名做集合比较
    assert not (_mock_dir(root) / "ACTIVE").exists()  # 试跑标记由内核写，生成器不碰


def test_generate_outside_the_case_layout_has_no_report_id(root: Path, lake: Path, tmp_path: Path) -> None:
    spec = _spec({"name": "daily.parquet", "n_codes": 3, "columns": [*SYNTH_KEYS, {"name": "v", "kind": "value"}]})

    manifest = md.generate(spec, tmp_path / "anywhere" / "files", lake)

    assert manifest["report_id"] is None and manifest["spec_path"] is None
    assert (tmp_path / "anywhere" / "manifest.json").is_file()


def test_cli_reports_spec_errors_with_exit_code_1(root: Path, lake: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(root))
    assert md.main(["check", CASE]) == 1  # 规格文件还不存在
    assert "规格文件不存在" in capsys.readouterr().err

    _write_spec(root, _spec({"name": "daily.parquet", "freq": "Y", "columns": [*SYNTH_KEYS, {"name": "px", "kind": "price", "start": "high"}]}))
    for command in ("check", "generate"):
        assert md.main([command, CASE]) == 1
        err = capsys.readouterr().err
        assert "规格错误: 表 daily.parquet: freq" in err and "规格错误: 表 daily.parquet: columns[2]（px）: start" in err
    assert not (_mock_dir(root) / "files").exists()

    # 规格合法，但引用的列源表里没有：check 也报出来
    _write_spec(root, _spec({"name": "x.parquet", "borrow": {"from": "quote.parquet", "rename": {"turnover": "tr"}, "columns": ["stock_code"]}}))
    assert md.main(["check", CASE]) == 1
    assert "表 x.parquet: borrow.rename 里的列 ['turnover']" in capsys.readouterr().err
    assert md.main(["generate", CASE]) == 1
    assert "生成失败: 表 x.parquet: borrow.rename" in capsys.readouterr().err


def test_cli_rejects_report_id_with_path(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("REPORT_REPRODUCE_ROOT", str(root))
    with pytest.raises(SystemExit) as stop:
        md.main(["generate", "../elsewhere"])
    assert stop.value.code == 2 and "report_id 不合法" in capsys.readouterr().err


def test_cli_is_deterministic_across_processes(root: Path, lake: Path, tmp_path: Path) -> None:
    """两个进程、不同的哈希随机化种子，生成的文件逐字节相同（顺带覆盖 --spec / --out / --data-root）。"""
    spec_path = tmp_path / "anywhere" / "spec.yaml"
    spec_path.parent.mkdir()
    spec = _spec(
        {"name": "synth.parquet", "n_codes": 6, "columns": SYNTH_COLUMNS},
        {"name": "hk.parquet", "period": ["2018-07-02", "2018-12-31"], "n_codes": 4,
         "borrow": {"from": "quote.parquet", "codes": {"replace": {"file": "hk_stock.parquet", "column": "stock_code"}}, "dates": "resample"}},
    )
    spec_path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def run(tag: str, hash_seed: str) -> dict[str, Any]:
        out = tmp_path / tag / "files"
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "REPORT_REPRODUCE_ROOT": str(root)}
        done = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "mockdata.py"), "generate", CASE, "--spec", str(spec_path), "--out", str(out), "--data-root", str(lake)],
            capture_output=True, text=True, env=env, cwd=tmp_path, timeout=300,
        )
        assert done.returncode == 0, done.stderr
        return json.loads((tmp_path / tag / "manifest.json").read_text(encoding="utf-8"))

    first, second = run("p1", "1"), run("p2", "987")
    assert [t["sha256"] for t in first["tables"]] == [t["sha256"] for t in second["tables"]]
    assert (tmp_path / "p1" / "files" / "synth.parquet").read_bytes() == (tmp_path / "p2" / "files" / "synth.parquet").read_bytes()
    assert not (_mock_dir(root) / "files").exists()  # 指定了 --out 就不碰案例目录


# ---------------------------------------------------------------------------
# 端到端：玩具策略在试跑与真实模式下各跑一遍
# ---------------------------------------------------------------------------

TOY_STRATEGY = """
import json

from common.data_loader import read_table, results_dir

quote = read_table("quote.parquet", columns=["stock_code", "date", "close"], start="2019-03-01", end="2019-03-29")
score = read_table("score.parquet", columns=["stock_code", "date", "score"], start="2019-03-01", end="2019-03-29")
merged = quote.merge(score, on=["stock_code", "date"])
metrics = {"rows": int(len(merged)), "mean_score": float(merged["score"].mean()), "mean_close": float(merged["close"].mean())}
(results_dir() / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
"""


def test_end_to_end_trial_then_real(root: Path, lake: Path, tmp_path: Path) -> None:
    quote = pd.read_parquet(lake / "quote.parquet")
    _write(quote[["stock_code", "date"]].assign(score=1.0), lake / "score.parquet")  # 真实的 score 恒为 1
    # mock 的 score 取全部 10 个在市代码（行情表里的 8 个都在其中），均值 100
    spec = _spec({"name": "score.parquet", "n_codes": 10, "columns": [*SYNTH_KEYS, {"name": "score", "kind": "value", "mean": 100.0, "std": 1.0}]})
    manifest = _generate(root, spec)
    assert _table(manifest, "score.parquet")["fallbacks"] == []
    script = root / "toy_main.py"
    script.write_text(TOY_STRATEGY, encoding="utf-8")
    output = root / "output" / CASE

    def run() -> None:
        env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
        env.update(PYTHONPATH=str(REPO_ROOT), REPORT_REPRODUCE_ROOT=str(root), REPRODUCE_REPORT_ID=CASE)
        done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=env, cwd=root, timeout=300)
        assert done.returncode == 0, done.stderr

    def load(folder: str) -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            json.loads((output / folder / "metrics.json").read_text(encoding="utf-8")),
            json.loads((output / folder / "data_manifest.json").read_text(encoding="utf-8")),  # 策略没有自己写，是退出时自动写的
        )

    # 试跑：结果落在 results_mock，清单标出 mock 文件
    _activate(root)
    run()
    assert not (output / "results").exists()
    trial_metrics, trial_manifest = load("results_mock")
    assert trial_manifest["report_id"] == CASE and trial_manifest["trial"] is True
    assert {f["name"]: f["source"] for f in trial_manifest["files"]} == {"quote.parquet": "real", "score.parquet": "mock"}
    assert Path(trial_manifest["files"][1]["path"]) == _mock_dir(root) / "files" / "score.parquet"
    assert trial_manifest["argv"][0].endswith("toy_main.py")
    assert trial_metrics["rows"] > 0 and trial_metrics["mean_score"] == pytest.approx(100.0, abs=1.0)  # mock 与真实表按代码、日期对得上

    # 去掉标记再跑：结果落在 results，清单全是真实文件；试跑目录原样
    (_mock_dir(root) / "ACTIVE").unlink()
    run()
    real_metrics, real_manifest = load("results")
    assert real_manifest["trial"] is False and {f["source"] for f in real_manifest["files"]} == {"real"}
    assert {Path(f["path"]).parent for f in real_manifest["files"]} == {lake}
    assert real_metrics["mean_score"] == 1.0
    # 两次读到的行情是同一份，mock 的 score 又与它按代码、日期全对得上：行数与收盘价均值相同
    assert real_metrics["rows"] == trial_metrics["rows"] and real_metrics["mean_close"] == pytest.approx(trial_metrics["mean_close"])
    assert load("results_mock") == (trial_metrics, trial_manifest)
    assert real_manifest["files"][0]["fingerprint"] == trial_manifest["files"][0]["fingerprint"]  # 同一个真实文件，指纹不变


# ---------------------------------------------------------------------------
# 用真实数据的一项（没有 ~/local_data 时跳过）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not all((REAL_DATA / name).is_file() for name in ("ashare_tradeday.parquet", "ashare_stock.parquet")), reason="没有本地真实数据")
def test_aligns_with_real_local_data(tmp_path: Path) -> None:
    spec = {
        "period": ["2024-01-01", "2024-03-31"],
        "tables": [
            {"name": "mock_factor.parquet", "n_codes": 20, "columns": [*SYNTH_KEYS, {"name": "v", "kind": "value"}]},
            {"name": "mock_listing.parquet", "n_codes": 30, "borrow": {"from": "ashare_stock.parquet", "columns": ["stock_code", "list_date"], "rename": {"list_date": "ipo_date"}}},
        ],
    }

    manifest = md.generate(spec, tmp_path / "files", REAL_DATA, root=tmp_path)

    calendar = pd.read_parquet(REAL_DATA / "ashare_tradeday.parquet", columns=["date"])["date"]
    stocks = pd.read_parquet(REAL_DATA / "ashare_stock.parquet", columns=["stock_code", "list_date"])
    factor = pd.read_parquet(tmp_path / "files" / "mock_factor.parquet")
    expected_days = sorted(calendar[(calendar >= "2024-01-01") & (calendar <= "2024-03-31")].unique())
    assert sorted(factor["date"].unique()) == expected_days
    assert set(factor["stock_code"]) <= set(stocks["stock_code"]) and factor["stock_code"].nunique() == 20
    listing = pd.read_parquet(tmp_path / "files" / "mock_listing.parquet")
    assert list(listing.columns) == ["stock_code", "ipo_date"] and len(listing) == 30
    merged = listing.merge(stocks, on="stock_code")
    assert len(merged) == 30 and (merged["ipo_date"] == merged["list_date"]).all()
    assert set(factor["stock_code"]) <= set(listing["stock_code"])  # 20 个是 30 个的子集
    assert manifest["fallbacks"] == []
