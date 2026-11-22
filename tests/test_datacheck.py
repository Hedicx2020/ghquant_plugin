"""tools/flowlib/datacheck.py：数据目录体检、逐年统计、与手写目录对照；数据需求体检与缺口处置。"""

from __future__ import annotations

import copy
import json
import os
import shlex
import shutil
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.flowlib import datacheck as dc  # noqa: E402

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")


def _write_quote(path: Path, plan: dict[int, tuple[int, int]], date_kind: str = "timestamp", code_col: str = "stock_code", date_col: str = "date") -> None:
    """按「年份 → (标的数, 每年日期数)」造一张行情表。"""
    codes: list[str] = []
    dates: list = []
    for year, (n_codes, n_days) in plan.items():
        for d in range(n_days):
            month, day = 1 + d // 28, 1 + d % 28
            for c in range(n_codes):
                codes.append(f"{c:06d}")
                if date_kind == "timestamp":
                    dates.append(datetime(year, month, day))
                elif date_kind == "int":
                    dates.append(year * 10000 + month * 100 + day)
                else:
                    dates.append(f"{year}-{month:02d}-{day:02d}")
    table = pa.table({code_col: codes, date_col: dates, "close": [1.0] * len(codes)})
    pq.write_table(table, path)


@pytest.fixture()
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    # 2019–2021 每年 2 只，2022 起 80 只：截面塌陷
    _write_quote(root / "hk_quote.parquet", {2019: (2, 200), 2020: (2, 200), 2021: (2, 200), 2022: (80, 200), 2023: (80, 200)})
    # 标的数逐年增长，不算塌陷
    _write_quote(root / "growth.parquet", {2018: (10, 200), 2019: (30, 200), 2020: (80, 200), 2021: (200, 200), 2022: (400, 200)}, date_kind="int", code_col="stcode", date_col="trade_dt")
    # 中间缺一整年，另有一年只有一半
    _write_quote(root / "gappy.parquet", {2018: (60, 200), 2019: (60, 90), 2021: (60, 200), 2022: (60, 200), 2023: (60, 200)}, date_kind="str")
    pq.write_table(pa.table({"stock_code": ["000001"], "stock_name": ["平安"]}), root / "static.parquet")
    pq.write_table(
        pa.table({"stock_code": ["000001", "000002"], "end_date": [datetime(2020, 12, 31), datetime(2021, 12, 31)], "info_publ_date": [datetime(2021, 3, 30), datetime(2022, 3, 30)]}),
        root / "balance.parquet",
    )
    (root / "factors").mkdir()
    _write_quote(root / "factors" / "f1.parquet", {2020: (60, 200), 2021: (60, 200)}, date_kind="int", code_col="stcode", date_col="trade_dt")
    (root / "notes.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "readme.md").write_text("不是数据文件", encoding="utf-8")
    (root / ".hidden.parquet").write_bytes(b"x")
    return root


def test_probe_records_schema_ranges_and_yearly(tmp_path: Path, data_root: Path) -> None:
    probe = dc.run_probe(tmp_path, data_root)
    files = probe["files"]
    assert sorted(files) == ["balance.parquet", "factors/f1.parquet", "gappy.parquet", "growth.parquet", "hk_quote.parquet", "notes.csv", "static.parquet"]
    assert probe["stats"]["files"] == 7 and probe["stats"]["probed"] == 7 and probe["stats"]["errors"] == 0

    hk = files["hk_quote.parquet"]
    assert hk["rows"] == (2 * 3 + 80 * 2) * 200
    assert [c["name"] for c in hk["columns"]] == ["stock_code", "date", "close"]
    assert (hk["code_column"], hk["date_column"], hk["publ_date_column"]) == ("stock_code", "date", None)
    assert hk["date_ranges"]["date"] == {"min": "2019-01-01", "max": "2023-08-04"}
    assert hk["yearly"]["2021"] == {"codes": 2, "days": 200} and hk["yearly"]["2022"] == {"codes": 80, "days": 200}
    assert hk["freq_guess"] == "日"

    growth = files["growth.parquet"]
    assert (growth["code_column"], growth["date_column"]) == ("stcode", "trade_dt")
    assert growth["date_ranges"]["trade_dt"]["min"] == "2018-01-01"  # 整数日期也认
    assert growth["yearly"]["2022"]["codes"] == 400

    balance = files["balance.parquet"]
    assert balance["date_column"] == "end_date" and balance["publ_date_column"] == "info_publ_date"
    assert set(balance["date_ranges"]) == {"end_date", "info_publ_date"}

    static = files["static.parquet"]
    assert static["date_column"] is None and "yearly" not in static
    assert files["notes.csv"] == {"path": "notes.csv", "size": 8, "mtime_ns": files["notes.csv"]["mtime_ns"], "format": "csv"}


def test_flags_distinguish_collapse_from_growth(tmp_path: Path, data_root: Path) -> None:
    files = dc.run_probe(tmp_path, data_root)["files"]
    hk_flags = {f["code"]: f["detail"] for f in files["hk_quote.parquet"]["flags"]}
    assert set(hk_flags) == {"sparse_years"}
    assert "2019–2021 年每年只有 2 个标的" in hk_flags["sparse_years"] and "2022 年有 80 个" in hk_flags["sparse_years"]
    assert files["growth.parquet"]["flags"] == []  # 逐年自然增长不报
    gappy = {f["code"]: f["detail"] for f in files["gappy.parquet"]["flags"]}
    assert "2020 年没有任何数据" in gappy["year_gap"]
    assert "2019" in gappy["short_years"]


def test_yearly_flags_ignore_future_years_and_small_tables() -> None:
    yearly = {str(y): {"codes": 100, "days": 12} for y in (2020, 2021, 2022)}
    yearly["2060"] = {"codes": 3, "days": 1}  # 预测类数据的远期年份
    assert dc.yearly_flags(yearly, this_year=2023) == []
    small = {"2020": {"codes": 1, "days": 240}, "2021": {"codes": 9, "days": 240}, "2022": {"codes": 9, "days": 240}}
    assert dc.yearly_flags(small, this_year=2023) == []  # 峰值不到 50 的小截面不判
    drop = {"2019": {"codes": 500, "days": 240}, "2020": {"codes": 500, "days": 240}, "2021": {"codes": 3, "days": 240}, "2022": {"codes": 2, "days": 240}}
    flags = dc.yearly_flags(drop, this_year=2023)
    assert [f["code"] for f in flags] == ["sparse_years"] and "2021–2022 年每年只有 2–3 个标的" in flags[0]["detail"]


def test_probe_uses_cache_and_invalidates_on_change(tmp_path: Path, data_root: Path) -> None:
    first = dc.run_probe(tmp_path, data_root)
    json_path, md_path = dc.save_probe(tmp_path, first)
    assert json_path == tmp_path / "workspace" / "_registry" / "data_probe.json" and md_path.is_file()
    assert dc.load_probe(tmp_path)["files"].keys() == first["files"].keys()

    second = dc.run_probe(tmp_path, data_root)
    assert second["stats"]["probed"] == 0 and second["stats"]["from_cache"] == 7
    assert second["files"] == first["files"]

    _write_quote(data_root / "growth.parquet", {2018: (10, 100), 2019: (10, 100)}, date_kind="int", code_col="stcode", date_col="trade_dt")
    (data_root / "static.parquet").unlink()
    third = dc.run_probe(tmp_path, data_root)
    assert third["stats"]["probed"] == 1 and third["stats"]["files"] == 6
    assert third["files"]["growth.parquet"]["yearly"]["2019"]["codes"] == 10
    assert "static.parquet" not in third["files"]

    assert dc.run_probe(tmp_path, data_root, use_cache=False)["stats"]["probed"] == 6


def test_probe_without_yearly_then_with(tmp_path: Path, data_root: Path) -> None:
    light = dc.run_probe(tmp_path, data_root, yearly=False)
    assert "yearly" not in light["files"]["hk_quote.parquet"] and light["files"]["hk_quote.parquet"]["rows"] > 0
    dc.save_probe(tmp_path, light)
    full = dc.run_probe(tmp_path, data_root, yearly=True)
    assert "yearly" in full["files"]["hk_quote.parquet"]  # 缓存里没有逐年统计的条目要补算
    assert full["stats"]["probed"] == 5  # 五张带代码列和日期列的表（含财务表与子目录里的因子表）
    assert full["stats"]["from_cache"] == 2


def test_probe_survives_broken_file_and_missing_root(tmp_path: Path, data_root: Path) -> None:
    (data_root / "broken.parquet").write_bytes(b"not a parquet file")
    probe = dc.run_probe(tmp_path, data_root)
    assert probe["stats"]["errors"] == 1 and "error" in probe["files"]["broken.parquet"]
    assert probe["files"]["hk_quote.parquet"]["rows"] > 0
    # 读不了的文件下次还会重试，不被缓存住
    dc.save_probe(tmp_path, probe)
    assert dc.run_probe(tmp_path, data_root)["stats"]["probed"] == 1

    missing = dc.run_probe(tmp_path, tmp_path / "nope")
    assert "不存在" in missing["error"] and missing["files"] == {}
    assert "体检失败" in dc.render_markdown(missing)


def test_resolve_data_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    ws = tmp_path / "proj" / "sub"
    ws.mkdir(parents=True)
    assert dc.resolve_data_root(ws) == Path.home() / "local_data"
    (tmp_path / "proj" / ".reproduce.json").write_text(json.dumps({"data_root": str(tmp_path / "mydata")}), encoding="utf-8")
    assert dc.resolve_data_root(ws) == tmp_path / "mydata"  # 向上就近找配置
    (ws / ".reproduce.json").write_text(json.dumps({"mode": "auto"}), encoding="utf-8")
    assert dc.resolve_data_root(ws) == Path.home() / "local_data"  # 最近的配置没写 data_root 就用默认


CATALOG = """# 本地数据目录

## 行情

| 文件 | 关键字段 | 覆盖 | 用途 |
|------|---------|------|------|
| `hk_quote.parquet` | stock_code, date, OHLC, turnover | 2015-01 ~ 至今(日) | 港股行情 |
| `growth.parquet` | stcode, trade_dt | 2010 ~ 至今 | 因子 |
| `gone.parquet` | stock_code | 日 | 已经不在了 |

## 财务

| 文件 | 内容 | 关键定位字段 |
|------|------|------|
| `balance.parquet` | 资产负债表 | stock_code, end_date, info_publ_date |
"""


def test_parse_catalog() -> None:
    claims = {c["file"]: c for c in dc.parse_catalog(CATALOG)}
    assert set(claims) == {"hk_quote.parquet", "growth.parquet", "gone.parquet", "balance.parquet"}
    assert claims["hk_quote.parquet"]["claimed_start_year"] == 2015
    assert claims["hk_quote.parquet"]["fields"] == ["stock_code", "date", "open", "high", "low", "close", "turnover"]
    assert claims["gone.parquet"]["claimed_start_year"] is None
    assert claims["balance.parquet"]["fields"] == ["stock_code", "end_date", "info_publ_date"]


def test_compare_with_catalog(tmp_path: Path, data_root: Path) -> None:
    probe = dc.run_probe(tmp_path, data_root)
    findings = dc.compare_with_catalog(probe, CATALOG)
    by_code: dict[str, list[dict]] = {}
    for f in findings:
        by_code.setdefault(f["code"], []).append(f)
    assert [f["file"] for f in by_code["catalog_missing_file"]] == ["gone.parquet"]
    assert by_code["catalog_sparse_years"][0]["file"] == "hk_quote.parquet"
    assert "目录写「2015-01 ~ 至今(日)」" in by_code["catalog_sparse_years"][0]["detail"]
    # 目录写 2015 起、实测 2019 起
    assert [f["file"] for f in by_code["catalog_start_later"]] == ["hk_quote.parquet", "growth.parquet"]
    missing_field = by_code["catalog_missing_field"][0]
    assert missing_field["level"] == "info" and "turnover" in missing_field["detail"] and "open" in missing_field["detail"]
    undocumented = by_code["catalog_undocumented"][0]
    assert undocumented["level"] == "info" and "gappy.parquet" in undocumented["detail"] and "factors" not in undocumented["detail"]
    assert all(f["level"] == "warn" for code in ("catalog_missing_file", "catalog_sparse_years", "catalog_start_later") for f in by_code[code])


def test_catalog_quote_is_cleaned(tmp_path: Path, data_root: Path) -> None:
    probe = dc.run_probe(tmp_path, data_root)
    table = "| 文件 | 内容 | 关键字段 | 覆盖 |\n|---|---|---|---|\n"
    # 目录用粗体写的时间范围：引用时去掉强调符号
    bold = dc.compare_with_catalog(probe, table + "| `hk_quote.parquet` | 港股 | stock_code, date | **仅 2019~2020，覆盖窄** |\n")
    sparse = [f for f in bold if f["code"] == "catalog_sparse_years"][0]
    assert sparse["detail"].startswith("目录写「仅 2019~2020，覆盖窄」，实测 ") and "*" not in sparse["detail"]
    # 目录没写时间范围：不引用
    blank = dc.compare_with_catalog(probe, table + "| `hk_quote.parquet` | 港股 | stock_code, date | - |\n")
    sparse = [f for f in blank if f["code"] == "catalog_sparse_years"][0]
    assert sparse["detail"].startswith("实测 ") and "目录写" not in sparse["detail"]


def test_render_markdown(tmp_path: Path, data_root: Path) -> None:
    probe = dc.run_probe(tmp_path, data_root)
    md = dc.render_markdown(probe, dc.compare_with_catalog(probe, CATALOG))
    assert "# 数据实况表" in md and "## 顶层文件" in md
    assert "| `hk_quote.parquet` |" in md and "2–80" in md and "2019-01-01 ~ 2023-08-04" in md
    assert "| `factors/` | 1 |" in md  # 子目录按目录汇总
    assert "`factors/f1.parquet`" not in md
    assert "## 与 data_catalog.md 对不上的地方" in md and "`gone.parquet`：目录里写了这个文件" in md
    assert "info_publ_date" in md


def test_save_probe_is_atomic_and_keeps_findings(tmp_path: Path, data_root: Path) -> None:
    probe = dc.run_probe(tmp_path, data_root)
    findings = dc.compare_with_catalog(probe, CATALOG)
    json_path, md_path = dc.save_probe(tmp_path, probe, findings)
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["catalog_findings"] == findings and saved["version"] == dc.PROBE_VERSION
    assert not list(json_path.parent.glob("*.tmp"))
    assert md_path.read_text(encoding="utf-8").startswith("# 数据实况表")
    assert sorted(os.listdir(data_root)) == sorted(os.listdir(data_root))  # 数据目录只读


# ===========================================================================
# 数据需求体检（批次 C）
# ===========================================================================


def _make_case(root: Path, requirements: list, report_id: str = "demo", spec: str = "", extra: dict | None = None, body: str = "\n# 复现计划\n") -> Path:
    """造一个最小案例：plan.md（frontmatter 里带 data_requirements），可选的 spec.md。"""
    ws = root / "workspace" / report_id
    (ws / "spec").mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "report_name": report_id,
        "type": "timing",
        **(extra or {}),
        "data_requirements": requirements,
        "milestones": [{"id": "m1", "name": "数据", "deps": [], "elements": ["D1"]}],
    }
    (ws / "plan.md").write_text("---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n" + body, encoding="utf-8")
    if spec:
        (ws / "spec" / "spec.md").write_text(spec, encoding="utf-8")
    return ws


def _check(root: Path, data: Path, requirements: list, **kwargs) -> dict:
    _make_case(root, requirements)
    return dc.check_requirements(root, "demo", data_root=data, **kwargs)


def _one(root: Path, data: Path, requirement: dict, **kwargs) -> dict:
    """只有一条需求时，直接返回它的体检条目。"""
    return _check(root, data, [{"name": "测试数据", "source": "见 files", "status": "available", **requirement}], **kwargs)["requirements"][0]


def _codes(entry: dict) -> list[str]:
    return [p["code"] for p in entry["problems"]]


def _problem(entry: dict, code: str) -> dict:
    return next(p for p in entry["problems"] if p["code"] == code)


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture()
def req_data(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    # 行情：2019–2021 每年 2 只，2022 起 80 只；每年 200 个日期（1 月 1 日到 8 月 4 日）
    _write_quote(root / "quote.parquet", {2019: (2, 200), 2020: (2, 200), 2021: (2, 200), 2022: (80, 200), 2023: (80, 200)})
    # 标的数逐年增长，没有断崖
    _write_quote(root / "growth.parquet", {2018: (10, 200), 2019: (30, 200), 2020: (80, 200), 2021: (200, 200), 2022: (400, 200)})
    # 每年只有 12 个日期
    _write_quote(root / "monthly.parquet", {y: (60, 12) for y in range(2018, 2024)})
    # 中间缺一整年（2020），另有一年只有 90 个日期
    _write_quote(root / "gappy.parquet", {2018: (60, 200), 2019: (60, 90), 2021: (60, 200), 2022: (60, 200), 2023: (60, 200)}, date_kind="str")
    # 主键重复：把前 3 行再追加一遍
    _write_quote(root / "dups.parquet", {2022: (5, 200), 2023: (5, 200)})
    table = pq.read_table(root / "dups.parquet")
    pq.write_table(pa.concat_tables([table, table.slice(0, 3)]), root / "dups.parquet")
    # 持仓表：同一（股票, 日期）下有 4 只基金，（代码列, 日期列）不是主键
    held = [(f"{s:06d}", f"F{f}", datetime(2022, 3 * q + 3, 28)) for q in range(4) for s in range(30) for f in range(4)]
    pq.write_table(pa.table({"stock_code": [h[0] for h in held], "fund_code": [h[1] for h in held], "date": [h[2] for h in held]}), root / "holdings.parquet")
    # 缺失率：close 八成为空，volume 一成是 NaN
    n = 1000
    pq.write_table(
        pa.table(
            {
                "stock_code": [f"{i % 10:06d}" for i in range(n)],
                "date": [datetime(2022, 1 + (i // 10) // 28, 1 + (i // 10) % 28) for i in range(n)],
                "close": [None if i % 5 else 1.0 for i in range(n)],
                "volume": [float("nan") if i % 10 == 0 else 1.0 for i in range(n)],
                "amount": [1.0] * n,
            }
        ),
        root / "nulls.parquet",
    )
    # 财务表：单季表没有披露日列，累计表有
    ends = [datetime(y, m, d) for y in (2020, 2021, 2022) for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))]
    stocks = [f"{c:06d}" for c in range(20)]
    fin = {"stock_code": [c for _ in ends for c in stocks], "end_date": [e for e in ends for _ in stocks], "revenue": [1.0] * (len(ends) * len(stocks))}
    pq.write_table(pa.table(fin), root / "income_q.parquet")
    pq.write_table(pa.table({**fin, "info_publ_date": fin["end_date"]}), root / "income.parquet")
    pq.write_table(pa.table(fin), root / "main_index.parquet")
    # 宽表：日期在 pandas 写出的索引列里，每月一个日期
    months = [datetime(y, m, 28) for y in range(2015, 2024) for m in range(1, 13)]
    pq.write_table(pa.table({"cpi_yoy": [1.0] * len(months), "__index_level_0__": months}), root / "wide.parquet")
    pq.write_table(pa.table({"stock_code": ["000001"], "stock_name": ["平安"]}), root / "static.parquet")
    (root / "factors").mkdir()
    _write_quote(root / "factors" / "f1.parquet", {2020: (60, 200), 2021: (60, 200)})
    (root / "broken.parquet").write_bytes(b"not a parquet file")
    (root / "notes.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    return root


# ---- 读 plan ----


def test_requirements_from_plan_accepts_old_and_new_fields(tmp_path: Path) -> None:
    _make_case(
        tmp_path,
        [
            {"name": "A股日行情", "source": "ashare_stock_price_forward.parquet", "status": "available"},
            {
                "name": "港股日行情",
                "source": "hk_stock_quote.parquet",
                "status": "Available（已核）",
                "files": ["hk_stock_quote.parquet"],
                "fields": ["close", "volume"],
                "period": [datetime(2014, 1, 1).date(), datetime(2024, 12, 31).date()],
                "freq": "D",
                "min_codes": 500,
                "core": True,
                "elements": ["D3", "F2"],
                "probe": "python -c 'print(1)'",
            },
            {
                "name": "宏观",
                "source": "macro",
                "status": "substitute",
                "note": "替代理由",
                "files": "a.parquet + b.parquet",
                "period": "2014~2024-06",
                "freq": "月频",
                "min_codes": "30",
                "core": "否",
                "elements": "D1-D3, FIG5",
                "keys": [],
                "max_null_rate": "80%",
            },
            {"name": "写错的", "source": "x", "status": "derive", "period": "去年到今年", "freq": "每十分钟", "min_codes": "很多", "max_null_rate": 3},
            "外部数据（只写了一句话）",
            {"name": "数值离谱的", "source": "x", "status": "available", "min_codes": float("inf"), "max_null_rate": float("nan"), "period": [[2014], {"a": 1}]},
        ],
    )
    old, new, loose, bad, bare, wild = dc.requirements_from_plan(tmp_path, "demo")
    assert wild["invalid"] == ["period", "min_codes", "max_null_rate"] and (wild["min_codes"], wild["max_null_rate"], wild["period"]) == (None, None, None)
    assert (old["name"], old["source"], old["status"], old["legacy"]) == ("A股日行情", "ashare_stock_price_forward.parquet", "available", True)
    assert (old["files"], old["fields"], old["period"], old["freq"], old["min_codes"], old["core"], old["elements"], old["probe"], old["keys"]) == ([], [], None, None, None, None, [], None, None)

    assert new["status"] == "available" and not new["legacy"] and new["invalid"] == []
    assert new["files"] == ["hk_stock_quote.parquet"] and new["fields"] == ["close", "volume"]
    assert new["period"] == ["2014-01-01", "2024-12-31"]  # YAML 把日期解析成 date 对象也认
    assert (new["freq"], new["min_codes"], new["core"], new["elements"], new["probe"]) == ("D", 500, True, ["D3", "F2"], "python -c 'print(1)'")

    assert loose["files"] == ["a.parquet", "b.parquet"] and loose["note"] == "替代理由"
    assert loose["period"] == ["2014-01-01", "2024-06-30"]  # 只写到年、月：起点取期初，终点取期末
    assert (loose["freq"], loose["min_codes"], loose["core"], loose["keys"], loose["max_null_rate"]) == ("M", 30, False, [], 0.8)
    assert loose["elements"] == ["D1", "D2", "D3", "FIG5"]  # 区间展开，认不出的编号照原样留着

    assert bad["invalid"] == ["period", "freq", "min_codes", "max_null_rate"] and bad["period"] is None and not bad["legacy"]
    assert (bare["name"], bare["source"], bare["status"], bare["legacy"]) == ("外部数据（只写了一句话）", "外部数据（只写了一句话）", "", True)
    assert [r["index"] for r in (old, new, loose, bad, bare)] == [0, 1, 2, 3, 4]

    assert dc.requirements_from_plan(tmp_path, "nope") == []  # 没有这个案例
    plan = tmp_path / "workspace" / "demo" / "plan.md"
    plan.write_text("---\nreport_name: demo\ndata_requirements: 见正文\n---\n", encoding="utf-8")
    assert dc.requirements_from_plan(tmp_path, "demo") == []  # 不是列表
    unlisted = dc.check_requirements(tmp_path, "demo", data_root=tmp_path)
    assert unlisted["requirements"] == [] and unlisted["notes"][0] == "plan.md 的 frontmatter 里没有 data_requirements 列表，没有可核对的数据需求"
    plan.write_text("# 没有 frontmatter 的 plan\n", encoding="utf-8")
    assert dc.requirements_from_plan(tmp_path, "demo") == []


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        (["2014-01-01", "2024-12-31"], ["2014-01-01", "2024-12-31"]),
        ("2014-01-01~2024-12-31", ["2014-01-01", "2024-12-31"]),
        ("2014-01-01 至 2024-12-31", ["2014-01-01", "2024-12-31"]),
        ("2014-01-01 - 2024-12-31", ["2014-01-01", "2024-12-31"]),
        ([2014, 2024], ["2014-01-01", "2024-12-31"]),
        ("2014-2024", ["2014-01-01", "2024-12-31"]),
        ("2024-2014", None),
        ("20140105~", ["2014-01-05", None]),
        ("2014年3月 至 今", ["2014-03-01", None]),
        ({"start": "2015-02", "end": "2015-02"}, ["2015-02-01", "2015-02-28"]),
        ("2014-01-01", ["2014-01-01", None]),
        (["2020-01-01", "2019-01-01"], None),  # 起止颠倒
        ("2014-13-01~2015", None),
        ("abc", None),
    ],
)
def test_period_spellings(tmp_path: Path, written, expected) -> None:
    _make_case(tmp_path, [{"name": "x", "source": "x", "status": "available", "period": written}])
    requirement = dc.requirements_from_plan(tmp_path, "demo")[0]
    assert requirement["period"] == expected
    assert requirement["invalid"] == ([] if expected else ["period"])


def test_plan_requirements_hash_tracks_only_data_requirements(tmp_path: Path) -> None:
    requirements = [
        {"name": "行情", "source": "quote.parquet", "status": "available", "files": ["quote.parquet"], "period": ["2019-01-01", "2023-08-01"]},
        {"name": "一致预期", "source": "外部", "status": "missing", "note": "本地没有"},
    ]
    _make_case(tmp_path, requirements)
    base = dc.plan_requirements_hash(tmp_path, "demo")
    assert isinstance(base, str) and len(base) == 16

    # plan 的其他部分怎么改都不变：frontmatter 的别的键、milestone、正文
    _make_case(tmp_path, requirements, extra={"difficulty": "hard", "feasibility": "degraded"}, body="\n# 换了正文\n\n## 一、核心策略\n改了很多字。\n")
    assert dc.plan_requirements_hash(tmp_path, "demo") == base
    # 只改写法（流式 YAML、键的顺序、注释）也不变
    plan = tmp_path / "workspace" / "demo" / "plan.md"
    reordered = [dict(reversed(list(r.items()))) for r in requirements]
    plan.write_text("---\n# 注释\nreport_name: demo\ndata_requirements: " + json.dumps(reordered, ensure_ascii=False) + "\n---\n正文\n", encoding="utf-8")
    assert dc.plan_requirements_hash(tmp_path, "demo") == base

    # 数据需求本身一变就变：改字段、改自由文本、增删条目、调换顺序
    changed = [
        [{**requirements[0], "period": ["2018-01-01", "2023-08-01"]}, requirements[1]],
        [requirements[0], {**requirements[1], "note": "改了说明"}],
        [requirements[0], {**requirements[1], "status": "substitute"}],
        requirements[:1],
        requirements + [{"name": "新增", "source": "x", "status": "derive"}],
        requirements[::-1],
    ]
    hashes = set()
    for variant in changed:
        _make_case(tmp_path, variant)
        hashes.add(dc.plan_requirements_hash(tmp_path, "demo"))
    assert len(hashes) == len(changed) and base not in hashes

    assert dc.plan_requirements_hash(tmp_path, "nope") is None
    plan.write_text("---\nreport_name: demo\nmilestones: []\n---\n", encoding="utf-8")
    assert dc.plan_requirements_hash(tmp_path, "demo") is None  # 没有 data_requirements 一段
    plan.write_text("---\nreport_name: [没闭合\n---\n", encoding="utf-8")
    assert dc.plan_requirements_hash(tmp_path, "demo") is None  # frontmatter 解析不了


# ---- 各问题代码 ----


def test_file_missing_and_unreadable(tmp_path: Path, req_data: Path) -> None:
    gone = _one(tmp_path, req_data, {"files": ["quote2.parquet"]})
    assert gone["result"] == "missing" and _codes(gone) == ["file_missing"] and gone["machine_checked"] and gone["plan_mismatch"]
    assert "数据根目录下没有 `quote2.parquet`" in gone["problems"][0]["detail"] and "quote.parquet" in gone["problems"][0]["detail"]
    assert gone["problems"][0]["evidence"] == {"file": "quote2.parquet", "similar": ["quote.parquet"]}

    part = _one(tmp_path, req_data, {"files": ["quote.parquet", "nope_at_all.parquet"], "min_codes": 1})
    assert part["result"] == "partial" and _codes(part) == ["file_missing"]  # 有一个在：部分满足

    broken = _one(tmp_path, req_data, {"files": ["broken.parquet"]})
    assert broken["result"] == "missing" and _codes(broken) == ["file_unreadable"]  # 在但读不了，等于没有
    assert "存在但读不了" in broken["problems"][0]["detail"]

    outside = _one(tmp_path, req_data, {"files": ["../secret.parquet", str(tmp_path / "elsewhere.parquet")]})
    assert outside["result"] == "unchecked" and _codes(outside) == ["not_machine_checkable"] and outside["files"] == []
    assert "数据根目录下的相对路径" in outside["notes"][0]

    absolute = _one(tmp_path, req_data, {"files": [str(req_data / "static.parquet"), "notes.csv", "factors"]})
    assert absolute["result"] == "ok" and absolute["files"] == ["static.parquet", "notes.csv", "factors"]  # 绝对路径落在数据根下也认
    assert "只查了在不在" in absolute["notes"][0] and "notes.csv" in absolute["notes"][0] and "factors" in absolute["notes"][0]


def test_field_missing_suggests_similar_columns(tmp_path: Path, req_data: Path) -> None:
    entry = _one(tmp_path, req_data, {"files": ["quote.parquet"], "fields": ["close", "Close", "stock_cod", "turnover"], "min_codes": 1})
    assert entry["result"] == "partial" and _codes(entry) == ["field_missing"]
    problem = entry["problems"][0]
    assert problem["evidence"]["missing"] == ["Close", "stock_cod", "turnover"] and problem["evidence"]["file"] == "quote.parquet"
    assert problem["evidence"]["similar"] == {"Close": ["close"], "stock_cod": ["stock_code"]}
    assert "`quote.parquet` 里没有字段 Close, stock_cod, turnover" in problem["detail"] and "Close → close" in problem["detail"]

    # 一条需求由几张表拼起来：字段在任何一张里有就行；OHLC 是简写
    joined = _one(tmp_path, req_data, {"files": ["quote.parquet", "income.parquet"], "fields": ["close", "revenue", "info_publ_date"], "min_codes": 1})
    assert "field_missing" not in _codes(joined)
    short = _one(tmp_path, req_data, {"files": ["quote.parquet"], "fields": ["OHLC"], "min_codes": 1})
    assert _problem(short, "field_missing")["evidence"]["missing"] == ["open", "high", "low"]
    # 还有读不到表头的文件时不下结论
    unsure = _one(tmp_path, req_data, {"files": ["quote.parquet", "notes.csv"], "fields": ["turnover"], "min_codes": 1})
    assert unsure["result"] == "ok" and unsure["skipped"][0]["check"] == "fields"


def test_period_short_names_the_missing_segments(tmp_path: Path, req_data: Path) -> None:
    # quote.parquet 实测 2019-01-01 ~ 2023-08-04
    entry = _one(tmp_path, req_data, {"files": ["quote.parquet"], "period": ["2015-01-01", "2023-12-31"], "min_codes": 1})
    assert entry["result"] == "partial" and _codes(entry) == ["period_short"]
    problem = entry["problems"][0]
    assert problem["evidence"]["missing"] == [["2015-01-01", "2018-12-31"], ["2023-08-05", "2023-12-31"]]
    assert problem["evidence"]["measured"] == ["2019-01-01", "2023-08-04"] and problem["evidence"]["required"] == ["2015-01-01", "2023-12-31"]
    assert problem["evidence"]["date_column"] == "date" and problem["evidence"]["file"] == "quote.parquet"
    assert "实测 2019-01-01 ~ 2023-08-04" in problem["detail"] and "缺 2015-01-01 ~ 2018-12-31、2023-08-05 ~ 2023-12-31" in problem["detail"]

    # 出入在容许范围内（日频 10 天）不报
    assert _one(tmp_path, req_data, {"files": ["quote.parquet"], "period": ["2018-12-25", "2023-08-10"], "min_codes": 1})["result"] == "ok"
    assert _codes(_one(tmp_path, req_data, {"files": ["quote.parquet"], "period": ["2018-12-15", "2023-08-01"], "min_codes": 1})) == ["period_short"]
    # 完全不相交：整段都缺
    apart = _one(tmp_path, req_data, {"files": ["quote.parquet"], "period": "2010~2012", "min_codes": 1})
    assert _problem(apart, "period_short")["evidence"]["missing"] == [["2010-01-01", "2012-12-31"]]
    # 只限一头
    assert _one(tmp_path, req_data, {"files": ["quote.parquet"], "period": "2019-01-01~", "min_codes": 1})["result"] == "ok"
    # 止在今天之后：今天之后的数据谁也没有，按今天算
    future = _one(tmp_path, req_data, {"files": ["quote.parquet"], "period": ["2019-01-01", "2099-12-31"], "min_codes": 1})
    assert _problem(future, "period_short")["evidence"]["required"][1] == future_today()
    # 没有日期列的表：区间没法核对，记为未检而不是问题
    static = _one(tmp_path, req_data, {"files": ["static.parquet"], "period": ["2019-01-01", "2023-01-01"]})
    assert static["result"] == "ok" and [s["check"] for s in static["skipped"]] == ["period"]


def future_today() -> str:
    return datetime.now(dc._TZ_CN).date().isoformat()


def test_period_short_reports_empty_and_thin_years(tmp_path: Path, req_data: Path) -> None:
    # gappy.parquet：2020 年整年没有，2019 年只有 90 个日期
    plain = _one(tmp_path, req_data, {"files": ["gappy.parquet"], "period": ["2018-01-01", "2023-08-01"]})
    problem = _problem(plain, "period_short")
    assert problem["evidence"]["missing"] == [] and problem["evidence"]["missing_years"] == [2020] and problem["evidence"]["thin_years"] == {}
    assert "2020 年整年没有数据" in problem["detail"]
    # 标了频率才判稀疏年份（事件类的表日期本来就不均匀）
    daily = _one(tmp_path, req_data, {"files": ["gappy.parquet"], "period": ["2018-01-01", "2023-08-01"], "freq": "D"})
    problem = _problem(daily, "period_short")
    assert problem["evidence"]["thin_years"] == {"2019": 90} and "2019 年每年只有 90 个日期" in problem["detail"]
    assert "freq_mismatch" not in _codes(daily)  # 常年是日频，只是个别年份稀疏
    # 区间避开这两年就没事
    assert _one(tmp_path, req_data, {"files": ["gappy.parquet"], "period": ["2021-01-01", "2023-08-01"], "freq": "D"})["result"] == "ok"


def test_period_tolerance_follows_the_grain_of_the_data(tmp_path: Path, req_data: Path) -> None:
    # 宽表每月 28 日一个值、日期在索引列里：2015-01-28 ~ 2023-12-28，月频的出入容许 35 天
    wide = _one(tmp_path, req_data, {"files": ["wide.parquet"], "period": ["2015-01-01", "2023-12-31"], "freq": "M", "fields": ["cpi_yoy"]})
    assert wide["result"] == "ok" and wide["problems"] == []
    assert wide["measured"]["wide.parquet"] == {"rows": 108, "date_column": "__index_level_0__", "date_range": ["2015-01-28", "2023-12-28"], "freq": "M"}
    late = _one(tmp_path, req_data, {"files": ["wide.parquet"], "period": ["2014-06-01", "2023-12-31"]})
    assert _problem(late, "period_short")["evidence"]["missing"] == [["2014-06-01", "2015-01-27"]]


def test_cross_section_collapse_with_and_without_min_codes(tmp_path: Path, req_data: Path) -> None:
    entry = _one(tmp_path, req_data, {"files": ["quote.parquet"], "period": ["2019-01-01", "2023-08-01"], "min_codes": 50})
    assert entry["result"] == "partial" and _codes(entry) == ["cross_section_collapse"]
    problem = entry["problems"][0]
    assert problem["evidence"]["yearly_codes"] == {"2019": 2, "2020": 2, "2021": 2, "2022": 80, "2023": 80}
    assert problem["evidence"]["deficient_years"] == [2019, 2020, 2021] and problem["evidence"]["min_codes"] == 50
    assert problem["evidence"]["file"] == "quote.parquet" and problem["evidence"]["code_column"] == "stock_code"
    assert problem["detail"] == "`quote.parquet` 2019–2021 年每年只有 2 个标的，2022 年起有 80 个；要求每年不少于 50 个"

    # 没写 min_codes：只报断崖式塌陷
    cliff = _one(tmp_path, req_data, {"files": ["quote.parquet"], "period": ["2019-01-01", "2023-08-01"]})
    problem = _problem(cliff, "cross_section_collapse")
    assert problem["evidence"]["deficient_years"] == [2019, 2020, 2021] and problem["evidence"]["min_codes"] is None
    assert "不到峰值（2022 年 80 个）的一成" in problem["detail"]
    # 只用少数几个代码的需求写 min_codes: 1；区间避开塌陷年份也不报
    assert _one(tmp_path, req_data, {"files": ["quote.parquet"], "period": ["2019-01-01", "2023-08-01"], "min_codes": 1})["result"] == "ok"
    assert _one(tmp_path, req_data, {"files": ["quote.parquet"], "period": ["2022-01-01", "2023-08-01"]})["result"] == "ok"

    # 逐年自然增长不算塌陷；但写了 min_codes 就按它判
    assert _one(tmp_path, req_data, {"files": ["growth.parquet"], "period": ["2018-01-01", "2022-08-01"]})["result"] == "ok"
    grown = _one(tmp_path, req_data, {"files": ["growth.parquet"], "period": ["2018-01-01", "2022-08-01"], "min_codes": 100})
    assert _problem(grown, "cross_section_collapse")["evidence"]["deficient_years"] == [2018, 2019, 2020]
    # 没有代码列和日期列的表算不出标的数：记为未检
    static = _one(tmp_path, req_data, {"files": ["static.parquet"], "min_codes": 10})
    assert static["result"] == "ok" and static["skipped"] == [{"check": "min_codes", "file": "static.parquet", "reason": "这张表没有代码列和日期列，算不出每年的标的数"}]


def test_freq_mismatch_only_when_data_is_coarser(tmp_path: Path, req_data: Path) -> None:
    entry = _one(tmp_path, req_data, {"files": ["monthly.parquet"], "freq": "D", "period": ["2018-01-01", "2023-01-10"]})
    assert entry["result"] == "partial" and _codes(entry) == ["freq_mismatch"]  # 整体就不是日频，不再逐年报稀疏
    problem = entry["problems"][0]
    assert (problem["evidence"]["required"], problem["evidence"]["measured"], problem["evidence"]["dates_per_year"]) == ("D", "M", 12)
    assert problem["detail"] == "`monthly.parquet` 要求日频，实测 2019–2022 年每年约 12 个日期（像月频）"
    assert _codes(_one(tmp_path, req_data, {"files": ["monthly.parquet"], "freq": "周"})) == ["freq_mismatch"]
    for enough in ("M", "Q", "A"):  # 数据比要求的细不算问题
        assert _one(tmp_path, req_data, {"files": ["monthly.parquet"], "freq": enough})["result"] == "ok"
    assert _one(tmp_path, req_data, {"files": ["quote.parquet"], "freq": "D", "min_codes": 1})["result"] == "ok"
    # 只有日期列的宽表：读日期列现算每年的日期数
    assert _codes(_one(tmp_path, req_data, {"files": ["wide.parquet"], "freq": "D"})) == ["freq_mismatch"]
    # 没有日期列：记为未检
    static = _one(tmp_path, req_data, {"files": ["static.parquet"], "freq": "D"})
    assert static["result"] == "ok" and [s["check"] for s in static["skipped"]] == ["freq"]


def test_dup_keys_default_explicit_and_not_a_key(tmp_path: Path, req_data: Path) -> None:
    entry = _one(tmp_path, req_data, {"files": ["dups.parquet"]})
    assert entry["result"] == "partial" and _codes(entry) == ["dup_keys"]
    evidence = entry["problems"][0]["evidence"]
    assert (evidence["keys"], evidence["keys_from"], evidence["rows"], evidence["dup_keys"], evidence["extra_rows"]) == (["stock_code", "date"], "default", 2003, 3, 3)
    assert evidence["sampled"] is False and evidence["scoped"] is False and len(evidence["examples"]) == 3
    assert sorted(evidence["examples"]) == [["000000", "2022-01-01"], ["000001", "2022-01-01"], ["000002", "2022-01-01"]]
    assert "按默认主键（stock_code, date）核对 2003 行，有 3 个键重复、多出 3 行" in entry["problems"][0]["detail"]
    assert "在 keys 里写明主键（写 [] 表示不查）" in entry["problems"][0]["detail"]  # 主键是猜的，给出改法

    # 只看所需区间内的行
    inside = _one(tmp_path, req_data, {"files": ["dups.parquet"], "period": ["2022-01-01", "2023-08-01"]})
    assert _problem(inside, "dup_keys")["evidence"]["scoped"] is True and "所需区间内" in _problem(inside, "dup_keys")["detail"]
    assert _one(tmp_path, req_data, {"files": ["dups.parquet"], "period": ["2023-01-01", "2023-08-01"]})["result"] == "ok"
    # keys 写明主键；写空表示不查
    stated = _problem(_one(tmp_path, req_data, {"files": ["dups.parquet"], "keys": ["stock_code", "date"]}), "dup_keys")
    assert stated["evidence"]["keys_from"] == "plan" and "按 plan 写的主键（stock_code, date）" in stated["detail"] and "猜" not in stated["detail"]
    assert _one(tmp_path, req_data, {"files": ["dups.parquet"], "keys": []})["result"] == "ok"
    assert _one(tmp_path, req_data, {"files": ["quote.parquet"], "min_codes": 1})["result"] == "ok"

    # 持仓表：（代码列, 日期列）下多出来的行占 75%，不是主键——不判，记一笔
    held = _one(tmp_path, req_data, {"files": ["holdings.parquet"]})
    assert held["result"] == "ok" and held["problems"] == []
    assert held["skipped"][0]["check"] == "dup_keys" and "不是这张表的主键" in held["skipped"][0]["reason"] and "75%" in held["skipped"][0]["reason"]
    assert _one(tmp_path, req_data, {"files": ["holdings.parquet"], "keys": ["stock_code", "fund_code", "date"]})["skipped"] == []
    assert _codes(_one(tmp_path, req_data, {"files": ["holdings.parquet"], "keys": ["stock_code", "date"]})) == ["dup_keys"]  # 写明了就照它判
    # keys 里的列不存在
    wrong = _one(tmp_path, req_data, {"files": ["dups.parquet"], "keys": ["stock_code", "trade_date"]})
    assert _codes(wrong) == ["field_missing"] and wrong["problems"][0]["evidence"]["missing"] == ["trade_date"]
    # 财务类表同一报告期可以有多行，默认不查
    fin = _one(tmp_path, req_data, {"files": ["income.parquet"]})
    assert fin["result"] == "ok" and fin["skipped"][0]["check"] == "dup_keys" and "默认不查重" in fin["skipped"][0]["reason"]


def test_null_rate_counts_nan_and_respects_the_limit(tmp_path: Path, req_data: Path) -> None:
    entry = _one(tmp_path, req_data, {"files": ["nulls.parquet"], "fields": ["close", "volume", "amount"]})
    assert entry["result"] == "partial" and _codes(entry) == ["null_rate"]
    evidence = entry["problems"][0]["evidence"]
    assert evidence["rates"] == {"close": 0.8} and evidence["fields"] == ["close"] and evidence["limit"] == 0.5 and evidence["rows"] == 1000
    assert entry["problems"][0]["detail"] == "`nulls.parquet` 全文件关键字段缺失率过高：close 80.0%（上限 50%）"

    strict = _one(tmp_path, req_data, {"files": ["nulls.parquet"], "fields": ["close", "volume", "amount"], "max_null_rate": 0.05})
    assert _problem(strict, "null_rate")["evidence"]["rates"] == {"close": 0.8, "volume": 0.1}  # NaN 也算缺失
    assert _one(tmp_path, req_data, {"files": ["nulls.parquet"], "fields": ["close"], "max_null_rate": "90%"})["result"] == "ok"
    scoped = _one(tmp_path, req_data, {"files": ["nulls.parquet"], "fields": ["close"], "period": ["2022-01-01", "2022-04-20"]})
    assert _problem(scoped, "null_rate")["evidence"]["scoped"] is True and "所需区间内" in _problem(scoped, "null_rate")["detail"]


def test_big_files_are_sampled_not_read_whole(tmp_path: Path, req_data: Path, monkeypatch) -> None:
    # 2000 行、每 100 行一个行组（每组 10 天 × 10 只），日期递增；前 1200 行 close 为空；末尾再追加一遍最后 5 行
    n = 2000
    start = datetime(2022, 1, 1)
    table = pa.table(
        {
            "stock_code": [f"{i % 10:06d}" for i in range(n)],
            "date": [start + timedelta(days=i // 10) for i in range(n)],
            "close": [None if i < 1200 else 1.0 for i in range(n)],
        }
    )
    pq.write_table(pa.concat_tables([table, table.slice(n - 5, 5)]), req_data / "big.parquet", row_group_size=100)
    monkeypatch.setattr(dc, "SAMPLE_ROWS", 500)

    # 挑行组：放得下就全读；放不下按位置均匀取，查重时先保住文件末尾（重复追加的数据在那里）
    sizes = [100] * 20 + [5]
    assert dc._sample_groups([100] * 5, 500, True) == [0, 1, 2, 3, 4]
    assert dc._sample_groups(sizes, 500, False) == [2, 6, 10, 14, 18]
    assert dc._sample_groups(sizes, 500, True) == [2, 6, 10, 19, 20]
    assert dc._sample_groups([10_000], 500, True) == [0]  # 只有一个大行组：读它的开头一段

    entry = _one(tmp_path, req_data, {"files": ["big.parquet"], "fields": ["close"]})
    assert entry["result"] == "partial" and _codes(entry) == ["dup_keys", "null_rate"]
    dup, nulls = entry["problems"]
    assert (dup["evidence"]["rows"], dup["evidence"]["dup_keys"], dup["evidence"]["extra_rows"], dup["evidence"]["sampled"]) == (405, 5, 5, True)
    assert "抽查 405 行" in dup["detail"]
    assert (nulls["evidence"]["rows"], nulls["evidence"]["rates"], nulls["evidence"]["sampled"]) == (500, {"close": 0.6}, True)  # 全表实际 59.9%
    assert "全文件（抽查）关键字段缺失率过高：close 60.0%" in nulls["detail"]

    # 给了区间：先按行组统计剪掉区间外的行组，读出来再按行过滤
    late = _one(tmp_path, req_data, {"files": ["big.parquet"], "fields": ["close"], "period": ["2022-06-01", "2022-07-19"]})
    assert _codes(late) == ["dup_keys"]  # 6 月以后 close 都有值
    assert late["problems"][0]["evidence"]["scoped"] is True and late["problems"][0]["evidence"]["dup_keys"] == 5
    assert late["problems"][0]["evidence"]["rows"] < 505 and "抽查所需区间内" in late["problems"][0]["detail"]
    early = _one(tmp_path, req_data, {"files": ["big.parquet"], "fields": ["close"], "period": ["2022-01-01", "2022-03-31"]})
    assert _codes(early) == ["null_rate"] and early["problems"][0]["evidence"]["rates"] == {"close": 1.0}  # 末尾的重复不在区间内

    # 只有一个行组的大文件：读到上限就停
    pq.write_table(table, req_data / "one_group.parquet")
    single = _one(tmp_path, req_data, {"files": ["one_group.parquet"], "fields": ["close"]})
    assert _problem(single, "null_rate")["evidence"] == {"file": "one_group.parquet", "fields": ["close"], "rates": {"close": 1.0}, "limit": 0.5, "rows": 500, "sampled": True, "scoped": False}


def test_no_publ_date_for_financial_tables(tmp_path: Path, req_data: Path) -> None:
    entry = _one(tmp_path, req_data, {"files": ["income_q.parquet"]})
    assert entry["result"] == "partial" and _codes(entry) == ["no_publ_date"]
    assert entry["problems"][0]["evidence"] == {"file": "income_q.parquet", "files": ["income_q.parquet"], "expected": ["info_publ_date", "publ_date", "ann_date"]}
    assert "没有披露日列（info_publ_date / publ_date / ann_date）" in entry["problems"][0]["detail"]

    # 同一条需求里有一张带披露日列的表，就能对齐：不报，只提醒
    paired = _one(tmp_path, req_data, {"files": ["income_q.parquet", "income.parquet"]})
    assert paired["result"] == "ok" and any("income_q.parquet 没有披露日列" in note for note in paired["notes"])
    assert _one(tmp_path, req_data, {"files": ["income.parquet"]})["result"] == "ok"

    # 文件名看不出是财务表时，看需求名称加报告期列
    named = _check(tmp_path, req_data, [{"name": "主要财务指标", "source": "x", "status": "available", "files": ["main_index.parquet"], "keys": []}])["requirements"][0]
    assert _codes(named) == ["no_publ_date"]
    other = _check(tmp_path, req_data, [{"name": "指标字典", "source": "x", "status": "available", "files": ["main_index.parquet"], "keys": []}])["requirements"][0]
    assert other["result"] == "ok"  # 只是带 end_date 的表，不算财务类
    assert _one(tmp_path, req_data, {"files": ["quote.parquet"], "min_codes": 1})["result"] == "ok"  # 行情表不需要披露日
    # 文件名像财务表、实际按交易日记的表（金融期货行情、债券现金流）不算财务类：不要求披露日，照常按（代码, 日期）查重
    for name in ("financial_future_price.parquet", "bond_cashflow.parquet"):
        _write_quote(req_data / name, {2022: (5, 200), 2023: (5, 200)}, code_col="contract_code")
        traded = _check(tmp_path, req_data, [{"name": "财务数据", "source": "x", "status": "available", "files": [name]}])["requirements"][0]
        assert traded["result"] == "ok" and traded["problems"] == [] and traded["skipped"] == []


def test_smoke_probe_runs_only_when_asked(tmp_path: Path, req_data: Path) -> None:
    python = shlex.quote(sys.executable)
    failing = {"name": "一致预期", "source": "JyPy 接口", "status": "available", "probe": f'{python} -c "import sys; print(\'boom\', file=sys.stderr); sys.exit(3)"'}
    passing = {"name": "宏观接口", "source": "JyPy 接口", "status": "available", "probe": f'{python} -c "print(1)"'}

    skipped = _check(tmp_path, req_data, [failing, passing])  # 默认不执行
    assert [e["result"] for e in skipped["requirements"]] == ["unchecked", "unchecked"] and skipped["smoke_run"] is False
    assert _codes(skipped["requirements"][0]) == ["smoke_not_run"] and not skipped["requirements"][0]["machine_checked"]
    assert skipped["summary"]["gaps"] == 0 and dc.open_gaps(skipped) == []

    ran = _check(tmp_path, req_data, [failing, passing], run_smoke=True)
    bad, good = ran["requirements"]
    assert bad["result"] == "missing" and _codes(bad) == ["smoke_failed"] and bad["machine_checked"] and bad["plan_mismatch"]
    assert bad["problems"][0]["evidence"]["returncode"] == 3 and bad["problems"][0]["evidence"]["output_tail"] == "boom"
    assert "退出码 3" in bad["problems"][0]["detail"]
    assert good["result"] == "ok" and good["problems"] == [] and good["machine_checked"] and "跑通" in good["notes"][0]

    # 文件查过了、另有一条没执行的冒烟调用：结论按文件
    both = _check(tmp_path, req_data, [{**passing, "files": ["static.parquet"]}])["requirements"][0]
    assert both["result"] == "ok" and _codes(both) == ["smoke_not_run"]


def test_smoke_probe_times_out(tmp_path: Path, req_data: Path, monkeypatch) -> None:
    monkeypatch.setattr(dc, "SMOKE_TIMEOUT", 0.2)
    slow = {"name": "慢接口", "source": "API", "status": "available", "probe": f'{shlex.quote(sys.executable)} -c "import time; time.sleep(5)"'}
    entry = _check(tmp_path, req_data, [slow], run_smoke=True)["requirements"][0]
    assert entry["result"] == "missing" and _codes(entry) == ["smoke_failed"] and "没有返回" in entry["problems"][0]["detail"]


def test_not_machine_checkable_and_declared_missing(tmp_path: Path, req_data: Path) -> None:
    result = _check(
        tmp_path,
        req_data,
        [
            {"name": "分析师一致预期", "source": "外部（Wind）", "status": "available"},
            {"name": "北向持股", "source": "外部（港交所），quote.parquet 也替代不了", "status": "missing", "core": True, "elements": ["D1"]},
        ],
    )
    external, declared = result["requirements"]
    assert external["result"] == "unchecked" and _codes(external) == ["not_machine_checkable"]
    assert not external["machine_checked"] and external["gap_key"] is None and not external["plan_mismatch"]
    # plan 自己标 missing 的是已知缺口：不查文件，直接等处置
    assert declared["result"] == "missing" and _codes(declared) == ["declared_missing"] and declared["files"] == []
    assert not declared["machine_checked"] and not declared["plan_mismatch"] and declared["core"] is True
    assert result["summary"] == {"total": 2, "ok": 0, "partial": 0, "missing": 1, "unchecked": 1, "gaps": 1, "open_gaps": 1, "substituted": 0}
    assert [e["name"] for e in dc.open_gaps(result)] == ["北向持股"]


# ---- 旧 plan、替代、降级、缓存 ----


def test_legacy_plan_only_checks_existence(tmp_path: Path, req_data: Path) -> None:
    probe = dc.run_probe(tmp_path, req_data)
    result = _check(
        tmp_path,
        req_data,
        [
            {"name": "行情", "source": "quote.parquet（前复权）", "status": "available"},
            {"name": "没了的", "source": "gone.parquet", "status": "available"},
            {"name": "一半在", "source": "quote.parquet.close / gone.parquet", "status": "derive"},
            {"name": "不带扩展名", "source": "quote / monthly(close) + nothing_like_this", "status": "available"},
            {"name": "目录", "source": "factors/；m1 构造的因子面板", "status": "available"},
            {"name": "子目录里的", "source": "f1.parquet", "status": "available"},
            {"name": "外部", "source": "外部（Wind）", "status": "available"},
            {"name": "写了区间没写文件", "source": "quote.parquet", "status": "available", "period": ["2010-01-01", "2023-01-01"], "min_codes": 500},
            {"name": "自己算出来的", "source": "m1 产出 output/demo/results/factor_panel.parquet", "status": "derive"},
        ],
        probe=probe,
    )
    *listed, derived = result["requirements"]
    # 写的是工作区里的产物路径，不是数据根下的文件：不当成缺文件，记未机检
    assert derived["result"] == "unchecked" and derived["files"] == [] and _codes(derived) == ["not_machine_checkable"] and not derived["plan_mismatch"]
    result = {**result, "requirements": listed, "summary": dc._summarize(listed)}
    plain, gone, half, bare, folder, nested, external, loose = listed
    # 文件在就是通过：截面塌陷这类问题旧 plan 查不到，只在 hints 里带上目录体检的提示
    assert plain["result"] == "ok" and plain["files"] == ["quote.parquet"] and plain["problems"] == [] and plain["machine_checked"]
    assert plain["measured"] == {} and len(plain["hints"]) == 1 and "2019–2021 年每年只有 2 个标的" in plain["hints"][0]
    assert gone["result"] == "missing" and _codes(gone) == ["file_missing"] and gone["plan_mismatch"]
    assert half["result"] == "partial" and half["files"] == ["quote.parquet", "gone.parquet"]
    assert bare["result"] == "ok" and bare["files"] == ["quote.parquet", "monthly.parquet"]  # 不带扩展名的只认确有其文件的
    assert folder["result"] == "ok" and folder["files"] == ["factors"]
    assert nested["result"] == "ok" and nested["files"] == ["factors/f1.parquet"]  # 目录体检里唯一的同名文件
    assert external["result"] == "unchecked" and _codes(external) == ["not_machine_checkable"]
    assert loose["result"] == "ok" and loose["problems"] == [] and "没有填 files" in loose["notes"][0]
    assert result["summary"] == {"total": 8, "ok": 5, "partial": 1, "missing": 1, "unchecked": 1, "gaps": 2, "open_gaps": 2, "substituted": 0}
    # 提示只给人看：通过的列在清单末尾，本身是缺口的列在它那一条里
    assert [bool(e["hints"]) for e in result["requirements"]] == [True, False, True, True, False, False, False, True]
    report = dc.render_gap_report(result)
    assert "## 目录体检的提示（不计入结论）" in report and "- 行情：`quote.parquet`：2019–2021 年每年只有 2 个标的" in report
    assert "- 目录体检的提示（不计入结论）：`quote.parquet`：2019–2021 年每年只有 2 个标的" in report  # 「一半在」那条缺口里
    # 没有目录体检缓存时没有提示，结论不变
    bare_result = _check(tmp_path, req_data, [{"name": "行情", "source": "quote.parquet（前复权）", "status": "available"}], probe={})
    assert bare_result["requirements"][0]["result"] == "ok" and bare_result["requirements"][0]["hints"] == []


def test_substitute_shows_as_substituted(tmp_path: Path, req_data: Path) -> None:
    result = _check(
        tmp_path,
        req_data,
        [
            {"name": "全A指数", "source": "原文 wind_a.parquet → 替代：quote 流通市值加权合成", "status": "substitute", "note": "登记 AS1"},
            {"name": "中观指标", "source": "原文 963 个指标 → 替代：同一本地指标池子集", "status": "substitute"},
            {"name": "替代数据本身有问题", "source": "x", "status": "substitute", "files": ["quote.parquet"], "period": ["2019-01-01", "2023-08-01"], "min_codes": 50},
            {"name": "替代文件不在", "source": "原文 a → 替代：gone.parquet", "status": "substitute"},
        ],
    )
    done, vague, flawed, absent = result["requirements"]
    # 「原文 X → 替代 Y」只看 Y：原文一侧的文件名不在不算缺
    assert done["result"] == "ok" and done["substituted"] is True and done["files"] == ["quote.parquet"] and done["problems"] == []
    assert vague["result"] == "unchecked" and vague["substituted"] is True  # 认不出文件：未机检，但仍是已替代
    assert flawed["result"] == "partial" and flawed["substituted"] is False and _codes(flawed) == ["cross_section_collapse"]
    assert absent["result"] == "missing" and absent["substituted"] is False and _codes(absent) == ["file_missing"]
    assert not any(e["plan_mismatch"] for e in result["requirements"])  # 标了 substitute 的不退回 planner，直接等人处置
    assert result["summary"]["substituted"] == 2 and [e["name"] for e in dc.open_gaps(result)] == ["替代数据本身有问题", "替代文件不在"]
    report = dc.render_gap_report(result)
    assert "## 已替代（2 条，不算缺口）" in report and "- 全A指数：替代数据查过，`quote.parquet` 都在" in report and "- 中观指标：替代数据机器查不了" in report


def test_degrades_to_existence_check_without_pyarrow(tmp_path: Path, req_data: Path, monkeypatch) -> None:
    probe = dc.run_probe(tmp_path, req_data)
    requirements = [
        {"name": "行情", "source": "x", "status": "available", "files": ["quote.parquet"], "fields": ["close", "turnover"], "period": ["2019-01-01", "2023-08-01"], "min_codes": 50},
        {"name": "没了的", "source": "x", "status": "available", "files": ["gone.parquet"]},
    ]
    monkeypatch.setattr(dc, "_have_pyarrow", lambda: False)
    result = _check(tmp_path, req_data, requirements, probe={})
    quote, gone = result["requirements"]
    assert result["pyarrow"] is False and any("未安装 pyarrow" in note for note in result["notes"])
    assert quote["result"] == "ok" and quote["problems"] == [] and quote["skipped"] == [{"check": "内容核对", "file": "quote.parquet", "reason": "未安装 pyarrow，只查了文件在不在"}]
    assert gone["result"] == "missing" and _codes(gone) == ["file_missing"]
    # 目录体检缓存里已有的实测照用；要读数据的两项（查重、缺失率）记为未检
    cached = _check(tmp_path, req_data, requirements, probe=probe)["requirements"][0]
    assert sorted(_codes(cached)) == ["cross_section_collapse", "field_missing"]
    assert sorted(s["check"] for s in cached["skipped"]) == ["dup_keys", "null_rate"]


def test_uses_probe_cache_and_probes_only_involved_files(tmp_path: Path, req_data: Path, monkeypatch) -> None:
    requirements = [
        {"name": "行情", "source": "x", "status": "available", "files": ["quote.parquet"], "period": ["2019-01-01", "2023-08-01"], "min_codes": 50},
        {"name": "月频", "source": "x", "status": "available", "files": ["monthly.parquet", "quote.parquet"], "min_codes": 1},
        {"name": "旧写法", "source": "growth.parquet", "status": "available"},
    ]
    probe = dc.run_probe(tmp_path, req_data)
    real_probe_file = dc.probe_file
    probed: list[str] = []
    threads: set[str] = set()

    def recording(path, data_root, yearly=True):
        probed.append(Path(path).name)
        threads.add(threading.current_thread().name)
        return real_probe_file(path, data_root, yearly)

    monkeypatch.setattr(dc, "probe_file", recording)

    # 给了 probe：缓存新鲜，一个文件都不用现测
    with_cache = _check(tmp_path, req_data, requirements, probe=probe)
    assert probed == [] and with_cache["probe_generated_at"] == probe["generated_at"]
    assert _codes(with_cache["requirements"][0]) == ["cross_section_collapse"]

    # 没有缓存：只现测涉及的文件（写了 files 的那两个），每个只测一次、并行着测；旧写法的只查存在
    without = _check(tmp_path, req_data, requirements, probe={})
    assert sorted(probed) == ["monthly.parquet", "quote.parquet"] and without["probe_generated_at"] is None
    assert threads and threading.main_thread().name not in threads
    assert [e["problems"] for e in without["requirements"]] == [e["problems"] for e in with_cache["requirements"]]

    # probe 不给时读 workspace/_registry 下的缓存
    probed.clear()
    dc.save_probe(tmp_path, probe)
    assert _check(tmp_path, req_data, requirements)["probe_generated_at"] == probe["generated_at"] and probed == []

    # 文件变了（大小、修改时间对不上）：只重测这一个
    _write_quote(req_data / "quote.parquet", {2019: (60, 200), 2020: (60, 200), 2021: (60, 200), 2022: (80, 200), 2023: (80, 200)})
    changed = _check(tmp_path, req_data, requirements, probe=probe)
    assert probed == ["quote.parquet"] and changed["requirements"][0]["result"] == "ok"

    # 缓存是别的数据根的：不用
    probed.clear()
    other = {**probe, "data_root": str(tmp_path / "elsewhere")}
    assert _check(tmp_path, req_data, requirements, probe=other)["probe_generated_at"] is None and sorted(probed) == ["monthly.parquet", "quote.parquet"]


def test_check_requirements_shape_and_read_only(tmp_path: Path, req_data: Path) -> None:
    _make_case(
        tmp_path,
        [
            {"name": "行情", "source": "quote.parquet", "status": "available", "files": ["quote.parquet"], "period": ["2019-01-01", "2023-08-01"], "min_codes": 50, "core": True, "elements": ["D1"]},
            {"name": "日历", "source": "static.parquet", "status": "available"},
        ],
    )
    before = _snapshot(tmp_path)
    result = dc.check_requirements(tmp_path, "demo", data_root=req_data)
    assert _snapshot(tmp_path) == before  # 体检本身不写任何文件
    assert set(result) == {"version", "report_id", "checked_at", "data_root", "probe_generated_at", "plan_hash", "pyarrow", "smoke_run", "seconds", "notes", "requirements", "summary"}
    assert result["report_id"] == "demo" and result["checked_at"].endswith("+08:00") and result["data_root"] == str(req_data)
    assert result["plan_hash"] == dc.plan_requirements_hash(tmp_path, "demo") and result["pyarrow"] is True
    assert result["notes"] == ["没有 spec.md：受影响要素只列了需求自己写的 elements"]
    assert result["summary"] == {"total": 2, "ok": 1, "partial": 1, "missing": 0, "unchecked": 0, "gaps": 1, "open_gaps": 1, "substituted": 0}
    entry = result["requirements"][0]
    assert set(entry) == {
        "name", "status_plan", "core", "source", "files", "elements", "affected_elements", "affected_truncated", "result", "problems",
        "machine_checked", "substituted", "plan_mismatch", "notes", "skipped", "hints", "measured", "gap_key", "disposition",
    }
    assert (entry["name"], entry["status_plan"], entry["core"], entry["files"], entry["elements"], entry["affected_elements"]) == ("行情", "available", True, ["quote.parquet"], ["D1"], ["D1"])
    assert entry["result"] == "partial" and entry["machine_checked"] is True and entry["plan_mismatch"] is True and entry["disposition"] is None
    assert set(entry["problems"][0]) == {"code", "detail", "evidence"} and len(entry["gap_key"]) == 16
    assert entry["measured"]["quote.parquet"] == {"rows": 33200, "date_column": "date", "date_range": ["2019-01-01", "2023-08-04"], "freq": "D", "code_column": "stock_code", "codes_per_year": [2, 80]}
    assert json.loads(json.dumps(result, ensure_ascii=False)) == result  # 整个结果能原样进 JSON

    target = dc.save_check(tmp_path, "demo", result)
    assert target == tmp_path / "workspace" / "demo" / "data_check.json" and dc.load_check(tmp_path, "demo") == result
    assert set(_snapshot(tmp_path)) - set(before) == {"workspace/demo/data_check.json"}  # 只多出这一个文件
    assert _snapshot(req_data) == {k[len("data/"):]: v for k, v in before.items() if k.startswith("data/")}  # 数据目录只读

    # 案例不存在、数据根不存在：照样给出结果，说明写在 notes 里
    empty = dc.check_requirements(tmp_path, "nope", data_root=req_data)
    assert empty["requirements"] == [] and empty["plan_hash"] is None and "读不到 plan.md" in empty["notes"][0]
    lost = dc.check_requirements(tmp_path, "demo", data_root=tmp_path / "no_such_dir")
    assert [e["result"] for e in lost["requirements"]] == ["missing", "missing"] and any("数据根目录不存在" in note for note in lost["notes"])
    assert dc.load_check(tmp_path, "nope") is None


def test_one_broken_requirement_does_not_sink_the_rest(tmp_path: Path, req_data: Path, monkeypatch) -> None:
    requirements = [
        {"name": "会出错的", "source": "quote.parquet", "status": "available", "files": ["quote.parquet"], "core": True, "elements": ["D1"]},
        {"name": "正常的", "source": "quote.parquet", "status": "available", "files": ["quote.parquet"], "period": ["2019-01-01", "2023-08-01"], "min_codes": 50},
        {"name": "已知缺的", "source": "外部", "status": "missing", "elements": ["D2"]},
    ]
    _make_case(tmp_path, requirements, spec=SPEC)
    normal = dc.check_requirements(tmp_path, "demo", data_root=str(req_data))  # 数据根给字符串也认
    assert [e["result"] for e in normal["requirements"]] == ["partial", "partial", "missing"] and normal["data_root"] == str(req_data)

    real = dc._check_in_depth

    def flaky(ctx, req, present, out):
        if req["name"] == "会出错的":
            raise RuntimeError("boom")
        return real(ctx, req, present, out)

    monkeypatch.setattr(dc, "_check_in_depth", flaky)
    result = dc.check_requirements(tmp_path, "demo", data_root=req_data)
    broken, fine, declared = result["requirements"]
    # 出错的那条记未机检并写明原因，不算缺口；其他条目照常
    assert broken["result"] == "unchecked" and _codes(broken) == ["not_machine_checkable"] and "RuntimeError: boom" in broken["problems"][0]["detail"]
    assert (broken["machine_checked"], broken["gap_key"], broken["core"], broken["affected_elements"], broken["files"]) == (False, None, True, ["D1"], [])
    assert fine == normal["requirements"][1] and declared == normal["requirements"][2]
    assert result["summary"] == {"total": 3, "ok": 0, "partial": 1, "missing": 1, "unchecked": 1, "gaps": 2, "open_gaps": 2, "substituted": 0}

    # 连传递受影响要素都出错：plan 标 missing 的仍是 missing，缺口指纹不变（已有的处置决定不会因此作废）
    monkeypatch.setattr(dc, "_propagate", lambda *args: (_ for _ in ()).throw(KeyError("bad graph")))
    worst = dc.check_requirements(tmp_path, "demo", data_root=req_data)
    assert [e["result"] for e in worst["requirements"]] == ["unchecked", "unchecked", "missing"]
    assert _codes(worst["requirements"][2]) == ["declared_missing", "not_machine_checkable"]
    assert worst["requirements"][2]["gap_key"] == declared["gap_key"] and worst["requirements"][2]["affected_elements"] == ["D2"]


# ---- 受影响的要素 ----

SPEC = """# 规格书

## 二、数据要求（D 类）

### [D1] 行情
- 页码: p1
- 原文: > "x"
- 关联要素: B1 / 关联歧义: A1

### [D2] 另一份数据
- 页码: p1
- 原文: > "x"
- 关联要素: F9

### [D3] 第三份数据（自己没写谁在用它）
- 页码: p1
- 原文: > "x"

## 三、因子定义（F 类）

### [F1] 因子一
- 页码: p2
- 原文: > "x"
- 依赖数据: D1, F2 / 关联基准: R1.2 / 关联歧义: A3

### [F2] 因子二（与 F1 互相依赖）
- 页码: p2
- 原文: > "x"
- 依赖数据: F1

### [F3] 因子三
- 页码: p2
- 原文: > "x"
- 依赖数据: D2 / 关联基准: R2

### [F9] 另一条线
- 页码: p2
- 原文: > "x"
- 依赖数据: D2

## 四、回测设置（B 类）

### [B1] 股票池
- 页码: p3
- 原文: > "x"
- 关联要素: D1, F3

### [B2] 支线的回测设置（上下游混着写）
- 页码: p3
- 原文: > "x"
- 关联要素: D3, R3, F9, B1

## 五、结果（R 类）

### [R1] 表一
- 页码: p4
- 原文: > "x"
- 关联要素: F1, B1；对应图表 TBL1

### [R2] 表二
- 页码: p4
- 原文: > "x"
- 关联要素: F3

### [R3] 表三（自己没写来源）
- 页码: p4
- 原文: > "x"

## 七、稳健性（SA 类）

### [SA1] 敏感性
- 页码: p5
- 原文: > "x"
- 关联要素: R1
"""


def test_affected_elements_follow_spec_dependencies(tmp_path: Path, req_data: Path, monkeypatch) -> None:
    requirements = [{"name": "行情", "source": "quote.parquet", "status": "available", "files": ["quote.parquet"], "min_codes": 50, "elements": ["D1"]}]
    _make_case(tmp_path, requirements, spec=SPEC)
    # D1 → B1（D 的关联要素）、F1（依赖数据）→ F2（依赖 F1；F1 也依赖 F2，成环）、R1（F1 的关联基准 R1.2 归到 R1）→ SA1
    # 不带进来：B1 的关联要素 F3（方向不明）、D2 那条线
    assert dc.affected_elements(tmp_path, "demo", {"elements": ["D1"]}) == ["D1", "F1", "F2", "B1", "R1", "SA1"]
    assert dc.affected_elements(tmp_path, "demo", {"elements": "D2"}) == ["D2", "F3", "F9", "R2"]
    assert dc.affected_elements(tmp_path, "demo", {"elements": ["F2", "D2"]}) == ["F2", "D2", "F1", "F3", "F9", "R1", "R2", "SA1"]  # 先是自己写的，再按 spec 顺序
    assert dc.affected_elements(tmp_path, "demo", {"elements": ["R1.2", "FIG5"]}) == ["R1.2", "FIG5", "SA1"]  # 行级编号按上一级传递
    assert dc.affected_elements(tmp_path, "demo", {"elements": ["SA1"]}) == ["SA1"] and dc.affected_elements(tmp_path, "demo", {}) == []
    # B 类的关联要素上下游混着写，只走方向确定的：写的 D 是它的上游（D3 → B2），写的 R 是它的下游（B2 → R3）；
    # 写的 F9、B1 方向不明，不带进来，反过来 F9、B1 受影响也不牵连 B2
    assert dc.affected_elements(tmp_path, "demo", {"elements": ["D3"]}) == ["D3", "B2", "R3"]
    assert dc.affected_elements(tmp_path, "demo", {"elements": ["B2"]}) == ["B2", "R3"]
    assert dc.affected_elements(tmp_path, "demo", {"elements": ["F9"]}) == ["F9"] and dc.affected_elements(tmp_path, "demo", {"elements": ["B1"]}) == ["B1", "R1", "SA1"]
    entry = dc.check_requirements(tmp_path, "demo", data_root=req_data)["requirements"][0]
    assert entry["affected_elements"] == ["D1", "F1", "F2", "B1", "R1", "SA1"] and entry["affected_truncated"] is False

    # 上限：按层推进，截断时留下离得近的
    monkeypatch.setattr(dc, "AFFECTED_LIMIT", 3)
    assert dc.affected_elements(tmp_path, "demo", {"elements": ["D1"]}) == ["D1", "F1", "B1"]
    capped = dc.check_requirements(tmp_path, "demo", data_root=req_data)["requirements"][0]
    assert capped["affected_elements"] == ["D1", "F1", "B1"] and capped["affected_truncated"] is True
    assert "已到上限，可能不全" in dc.render_gap_report({"requirements": [capped]})

    # spec 不存在：只返回需求自己写的
    (tmp_path / "workspace" / "demo" / "spec" / "spec.md").unlink()
    assert dc.affected_elements(tmp_path, "demo", {"elements": ["D1", "F1-F2"]}) == ["D1", "F1", "F2"]


# ---- 存取与处置 ----

GAP_PLAN = [
    {"name": "港股行情", "source": "quote.parquet", "status": "available", "files": ["quote.parquet"], "period": ["2019-01-01", "2023-08-01"], "min_codes": 50, "core": True, "elements": ["D1"]},
    {"name": "一致预期", "source": "外部（Wind）", "status": "missing", "core": False},
    {"name": "日历", "source": "static.parquet", "status": "available"},
]


def _checked(root: Path, data: Path, requirements: list) -> dict:
    result = _check(root, data, requirements)
    dc.save_check(root, "demo", result)
    return result


def test_set_disposition_and_open_gaps(tmp_path: Path, req_data: Path) -> None:
    with pytest.raises(ValueError, match="还没有数据体检结果"):
        dc.set_disposition(tmp_path, "demo", None, "narrow")
    result = _checked(tmp_path, req_data, GAP_PLAN)
    assert [e["name"] for e in dc.open_gaps(result)] == ["港股行情", "一致预期"] and result["summary"]["open_gaps"] == 2

    with pytest.raises(ValueError, match="处置方式只能是"):
        dc.set_disposition(tmp_path, "demo", None, "ignore")
    with pytest.raises(ValueError, match="没有这些需求"):
        dc.set_disposition(tmp_path, "demo", ["港股行情", "不存在的需求"], "drop")
    assert dc.load_check(tmp_path, "demo") == result  # 被拒的调用不留痕迹
    # 点到的需求不是缺口（比如检查点开出来之后数据已经补上）：跳过，不报错，也不给它记决定
    assert dc.set_disposition(tmp_path, "demo", ["日历"], "drop") == result

    updated = dc.set_disposition(tmp_path, "demo", ["港股行情", "日历"], "narrow", checkpoint="cp_03_data_gap", note="只做 2022 年以后")
    assert updated["requirements"][2]["disposition"] is None  # 一起点到的「日历」不是缺口，没有被记决定
    decided = updated["requirements"][0]["disposition"]
    assert decided == {"choice": "narrow", "checkpoint": "cp_03_data_gap", "note": "只做 2022 年以后", "decided_at": decided["decided_at"], "gap_key": updated["requirements"][0]["gap_key"]}
    assert decided["decided_at"].endswith("+08:00")
    assert updated == dc.load_check(tmp_path, "demo") and updated["summary"]["open_gaps"] == 1 and updated["summary"]["gaps"] == 2
    assert [e["name"] for e in dc.open_gaps(updated)] == ["一致预期"]

    # names=None：只动还没处置的；已有的决定不动
    rest = dc.set_disposition(tmp_path, "demo", None, "drop", checkpoint="cp_03_data_gap")
    assert [e["disposition"]["choice"] if e["disposition"] else None for e in rest["requirements"]] == ["narrow", "drop", None]
    assert dc.open_gaps(rest) == [] and rest["summary"]["open_gaps"] == 0
    assert dc.set_disposition(tmp_path, "demo", None, "abort") == rest  # 没有待处置的：什么都不改
    # 点名可以改写已有的决定
    again = dc.set_disposition(tmp_path, "demo", ["港股行情", "一致预期"], "mock")
    assert [e["disposition"]["choice"] for e in again["requirements"][:2]] == ["mock", "mock"]
    single = dc.set_disposition(tmp_path, "demo", "港股行情", "supply")  # 只点一条时直接给名称也认
    assert [e["disposition"]["choice"] for e in single["requirements"][:2]] == ["supply", "mock"]
    assert dc.set_disposition(tmp_path, "demo", [], "abort") == single  # 空名单：谁也不动
    assert not list((tmp_path / "workspace" / "demo").glob("*.tmp"))


def test_save_check_keeps_or_clears_dispositions(tmp_path: Path, req_data: Path) -> None:
    _checked(tmp_path, req_data, GAP_PLAN)
    dc.set_disposition(tmp_path, "demo", ["港股行情"], "narrow", checkpoint="cp_03", note="只做 2022 年以后")
    dc.set_disposition(tmp_path, "demo", ["一致预期"], "drop")

    # 缺口没变：重检后处置决定原样保留（plan 里无关缺口的改动、换了条目顺序都不影响）
    reordered = [GAP_PLAN[2], {**GAP_PLAN[0], "core": False, "note": "补了说明"}, GAP_PLAN[1]]
    fresh = _check(tmp_path, req_data, reordered)
    assert all(e["disposition"] is None for e in fresh["requirements"]) and fresh["summary"]["open_gaps"] == 2  # 体检本身不带旧决定
    dc.save_check(tmp_path, "demo", fresh)
    kept = {e["name"]: e for e in fresh["requirements"]}  # save_check 就地更新了传进去的结果
    assert kept["港股行情"]["disposition"]["choice"] == "narrow" and kept["港股行情"]["disposition"]["note"] == "只做 2022 年以后"
    assert kept["一致预期"]["disposition"]["choice"] == "drop" and fresh["summary"]["open_gaps"] == 0
    assert dc.load_check(tmp_path, "demo") == fresh and dc.open_gaps(fresh) == []

    # 缺口变了（缺的年份不同了）：清掉，留一笔
    moved = _check(tmp_path, req_data, [{**GAP_PLAN[0], "period": ["2020-01-01", "2023-08-01"]}, GAP_PLAN[1], GAP_PLAN[2]])
    dc.save_check(tmp_path, "demo", moved)
    hk, expectation = moved["requirements"][0], moved["requirements"][1]
    assert hk["disposition"] is None and hk["cleared_disposition"]["choice"] == "narrow" and hk["cleared_disposition"]["reason"] == "缺口有变化"
    assert hk["cleared_disposition"]["cleared_at"].endswith("+08:00")
    assert expectation["disposition"]["choice"] == "drop"  # 别的缺口不受牵连
    assert [e["name"] for e in dc.open_gaps(moved)] == ["港股行情"] and moved["summary"]["open_gaps"] == 1
    assert "之前定过「缩小范围」，缺口有变化，已作废" in dc.render_gap_report(moved)
    # 还没重新处置期间，作废记录一直带着：缺口没变的重检、缺口又变了一次的重检都一样；重新处置后消掉
    again = _checked(tmp_path, req_data, [{**GAP_PLAN[0], "period": ["2020-01-01", "2023-08-01"]}, GAP_PLAN[1], GAP_PLAN[2]])
    assert again["requirements"][0]["cleared_disposition"] == hk["cleared_disposition"]
    third = _checked(tmp_path, req_data, [{**GAP_PLAN[0], "period": ["2021-01-01", "2023-08-01"]}, GAP_PLAN[1], GAP_PLAN[2]])
    assert third["requirements"][0]["gap_key"] != again["requirements"][0]["gap_key"]
    assert third["requirements"][0]["disposition"] is None and third["requirements"][0]["cleared_disposition"] == hk["cleared_disposition"]
    redone = dc.set_disposition(tmp_path, "demo", ["港股行情"], "supply")
    assert "cleared_disposition" not in redone["requirements"][0]

    # 缺口没了（数据补齐）：清掉
    _write_quote(req_data / "quote.parquet", {y: (80, 200) for y in range(2019, 2024)})
    closed = _checked(tmp_path, req_data, GAP_PLAN)
    assert closed["requirements"][0]["result"] == "ok" and closed["requirements"][0]["disposition"] is None
    assert closed["requirements"][0]["cleared_disposition"]["choice"] == "supply" and closed["requirements"][0]["cleared_disposition"]["reason"] == "缺口已经没有了"
    assert closed["summary"] == {"total": 3, "ok": 2, "partial": 0, "missing": 1, "unchecked": 0, "gaps": 1, "open_gaps": 0, "substituted": 0}
    # 缺口后来又出现：算新缺口，等人处置，不再提已经了结的那一笔
    _write_quote(req_data / "quote.parquet", {2019: (2, 200), 2020: (2, 200), 2021: (2, 200), 2022: (80, 200), 2023: (80, 200)})
    back = _checked(tmp_path, req_data, GAP_PLAN)
    assert back["requirements"][0]["result"] == "partial" and back["requirements"][0]["disposition"] is None
    assert "cleared_disposition" not in back["requirements"][0] and [e["name"] for e in dc.open_gaps(back)] == ["港股行情"]
    # 调用方自己带了处置决定：照它的
    own = _check(tmp_path, req_data, GAP_PLAN)
    own["requirements"][1]["disposition"] = {"choice": "abort", "checkpoint": "", "note": "", "decided_at": "2026-01-01T00:00:00+08:00", "gap_key": own["requirements"][1]["gap_key"]}
    dc.save_check(tmp_path, "demo", own)
    assert dc.load_check(tmp_path, "demo")["requirements"][1]["disposition"]["choice"] == "abort"


def test_gap_key_ignores_wording_and_small_drift(tmp_path: Path, req_data: Path) -> None:
    entry = _check(tmp_path, req_data, GAP_PLAN)["requirements"][0]
    drifted = copy.deepcopy(entry)
    drifted["problems"][0]["detail"] = "措辞改了"
    drifted["problems"][0]["evidence"]["yearly_codes"]["2021"] = 3  # 数字小有出入，缺的年份没变
    drifted["notes"].append("多了一条说明")
    assert dc._gap_key(drifted) == entry["gap_key"]
    fewer = copy.deepcopy(entry)
    fewer["problems"][0]["evidence"]["deficient_years"] = [2019, 2020]
    assert dc._gap_key(fewer) != entry["gap_key"]
    more = copy.deepcopy(entry)
    more["problems"].append({"code": "field_missing", "detail": "", "evidence": {"file": "quote.parquet", "missing": ["volume"]}})
    assert dc._gap_key(more) != entry["gap_key"]
    assert dc._gap_key({**entry, "result": "ok"}) is None and dc._gap_key({**entry, "result": "missing"}) != entry["gap_key"]


# ---- 缺口清单 ----


def test_render_gap_report(tmp_path: Path, req_data: Path) -> None:
    _make_case(
        tmp_path,
        GAP_PLAN
        + [
            {"name": "外部接口", "source": "JyPy 接口", "status": "available"},
            {"name": "全A指数", "source": "原文 Wind 全A → 替代：growth 合成", "status": "substitute"},
            {"name": "旧写法的行情", "source": "quote.parquet", "status": "available"},
        ],
        spec=SPEC,
    )
    result = dc.check_requirements(tmp_path, "demo", data_root=req_data, probe=dc.run_probe(tmp_path, req_data))
    dc.save_check(tmp_path, "demo", result)
    report = dc.render_gap_report(result)
    assert report.startswith("# 数据缺口清单 · demo\n")
    assert f"数据根目录 `{req_data}`" in report and "共 6 条数据需求：通过 3、部分满足 1、缺失 1、未机检 1。缺口 2 个，其中 2 个还没有处置决定。" in report
    # 逐条：缺什么（附实测证据）、影响哪些要素、是否核心、plan 里标的状态、处置决定
    assert "## 1. 港股行情" in report and "- 结论：部分满足 · 核心数据 · 待处置" in report
    assert "- plan 里标的状态：available（plan 没把它当缺口，与实测不符）" in report and "- 文件：`quote.parquet`" in report
    assert "  - 截面塌陷（cross_section_collapse）：`quote.parquet` 2019–2021 年每年只有 2 个标的，2022 年起有 80 个；要求每年不少于 50 个" in report
    assert "    - 逐年标的数 2019: 2、2020: 2、2021: 2、2022: 80、2023: 80" in report
    assert "- 影响要素（6 个）：D1、F1、F2、B1、R1、SA1" in report
    assert "- 处置决定：未定。可选：补数据（supply） / 等价替代（substitute） / 缩小范围（narrow） / 先用 mock 试跑（mock） / 砍掉相关要素（drop） / 终止（abort）" in report
    assert "## 2. 一致预期" in report and "- 结论：缺失 · 非核心数据 · 待处置" in report and "- plan 里标的状态：missing\n" in report
    assert "- 来源：外部（Wind）" in report and "  - plan 已标缺失（declared_missing）：plan 已标 missing：外部（Wind）" in report
    assert "- 影响要素：plan 没有写 elements，无从传递" in report
    # 不算缺口的几类各一行
    assert "## 已替代（1 条，不算缺口）" in report and "## 未机检（1 条，不算缺口）" in report and "- 外部接口：source 里认不出数据文件" in report
    assert "## 目录体检的提示（不计入结论）" in report and "- 旧写法的行情：`quote.parquet`：2019–2021 年每年只有 2 个标的" in report
    assert "## 3." not in report

    # 处置之后
    dc.set_disposition(tmp_path, "demo", ["港股行情"], "narrow", checkpoint="cp_03_data_gap", note="只做 2022 年以后")
    decided = dc.load_check(tmp_path, "demo")
    full = dc.render_gap_report(decided)
    assert "- 结论：部分满足 · 核心数据 · 已定：缩小范围" in full and "缺口 2 个，其中 1 个还没有处置决定。" in full
    assert "- 处置决定：缩小范围（narrow）；检查点 cp_03_data_gap；只做 2022 年以后；" in full
    pending = dc.render_gap_report(decided, only_open=True)
    assert "港股行情" not in pending and "## 1. 一致预期" in pending and "下面只列待处置的" in pending and "## 已替代" not in pending
    dc.set_disposition(tmp_path, "demo", None, "drop")
    assert dc.render_gap_report(dc.load_check(tmp_path, "demo"), only_open=True) == "没有待处置的数据缺口：2 个缺口都已有处置决定。\n"

    # 没有缺口：一句话
    clean = _check(tmp_path, req_data, [GAP_PLAN[2], {"name": "外部接口", "source": "JyPy 接口", "status": "available"}])
    assert dc.render_gap_report(clean) == "没有数据缺口（2 条数据需求：通过 1、部分满足 0、缺失 0、未机检 1）。\n"
    assert dc.render_gap_report(clean, only_open=True) == dc.render_gap_report(clean)
    assert dc.render_gap_report({}) == "没有数据缺口（0 条数据需求：通过 0、部分满足 0、缺失 0、未机检 0）。\n"
    swapped = _check(tmp_path, req_data, [GAP_PLAN[2], {"name": "全A指数", "source": "原文 Wind 全A → 替代：growth 合成", "status": "substitute"}])
    assert dc.render_gap_report(swapped) == "没有数据缺口（2 条数据需求：通过 2、部分满足 0、缺失 0、未机检 0；已替代 1 条）。\n"
    hinted = _check(tmp_path, req_data, [{"name": "旧写法的行情", "source": "quote.parquet", "status": "available"}], probe=dc.run_probe(tmp_path, req_data))
    assert dc.render_gap_report(hinted) == "没有数据缺口（1 条数据需求：通过 1、部分满足 0、缺失 0、未机检 0；其中 1 条只查了文件在不在，而目录体检对它们的文件有提示：旧写法的行情）。\n"


# ---- 真实数据回放（只读：把文书拷到临时案例里再补字段；数据或案例不在就跳过） ----

LOCAL_DATA = Path.home() / "local_data"
R010 = "r010_breakout_ratio_timing"
R009 = "r009_industry_rotation"


def _has_case(report_id: str, *files: str) -> bool:
    ws = REPO_ROOT / "workspace" / report_id
    return (ws / "plan.md").is_file() and (ws / "spec" / "spec.md").is_file() and all((LOCAL_DATA / name).is_file() for name in files)


def _clone_case(tmp_path: Path, report_id: str) -> Path:
    ws = tmp_path / "workspace" / report_id
    (ws / "spec").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "workspace" / report_id / "plan.md", ws / "plan.md")
    shutil.copy(REPO_ROOT / "workspace" / report_id / "spec" / "spec.md", ws / "spec" / "spec.md")
    return ws


def _real_case_listing(report_id: str) -> list[str]:
    return sorted(p.name for p in (REPO_ROOT / "workspace" / report_id).iterdir())


@pytest.mark.skipif(not _has_case(R010, "hkshare_stock_quote.parquet"), reason="本机没有 r010 案例或港股行情文件")
def test_replay_r010_reports_hk_cross_section_collapse(tmp_path: Path) -> None:
    yearly = dc.probe_file(LOCAL_DATA / "hkshare_stock_quote.parquet", LOCAL_DATA).get("yearly") or {}
    if not all(0 < yearly.get(str(y), {}).get("codes", 0) < 10 for y in range(2014, 2025)):
        pytest.skip("本地港股行情 2014–2024 已不是个位数标的（数据补过了），这个回放不再适用")
    listing = _real_case_listing(R010)
    ws = _clone_case(tmp_path, R010)

    # 原样（旧写法）：只查文件在不在，港股行情那条照 plan 标的 available 过了——这正是当初漏掉的地方
    legacy = dc.check_requirements(tmp_path, R010, data_root=LOCAL_DATA, probe={})
    legacy_hk = next(e for e in legacy["requirements"] if e["files"] == ["hkshare_stock_quote.parquet"])
    assert legacy["summary"]["total"] == 10 and legacy_hk["status_plan"] == "available"
    assert legacy_hk["result"] == "ok" and legacy_hk["problems"] == [] and not legacy_hk["plan_mismatch"]

    # 给港股行情那条补上可查字段：文件、期间 2014 年起（到研报测算区间末 2026-08）、每年至少 500 只、依赖它的要素
    text = (ws / "plan.md").read_text(encoding="utf-8")
    head, body = text[4:].split("\n---\n", 1)
    frontmatter = yaml.safe_load(head)
    hk = next(r for r in frontmatter["data_requirements"] if r["source"] == "hkshare_stock_quote.parquet")
    hk.update({"files": ["hkshare_stock_quote.parquet"], "period": ["2014-01-01", "2026-08-23"], "min_codes": 500, "core": False, "elements": ["D6"]})
    (ws / "plan.md").write_text("---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False) + "---\n" + body, encoding="utf-8")

    result = dc.check_requirements(tmp_path, R010, data_root=LOCAL_DATA, probe={})
    entry = next(e for e in result["requirements"] if e["files"] == ["hkshare_stock_quote.parquet"])
    assert entry["status_plan"] == "available" and entry["result"] == "partial" and entry["plan_mismatch"] is True
    assert entry["name"] in [e["name"] for e in dc.open_gaps(result)] and result["summary"]["partial"] == legacy["summary"]["partial"] + 1
    # 其余九条没有动，结论与原样时一致
    assert [e["result"] for e in result["requirements"] if e is not entry] == [e["result"] for e in legacy["requirements"] if e is not legacy_hk]
    problem = _problem(entry, "cross_section_collapse")
    assert problem["evidence"]["file"] == "hkshare_stock_quote.parquet" and problem["evidence"]["min_codes"] == 500
    assert problem["evidence"]["deficient_years"] == list(range(2014, 2025))
    assert all(0 < problem["evidence"]["yearly_codes"][str(y)] < 10 for y in range(2014, 2025))  # 2014–2024 各年标的数是个位数
    assert problem["evidence"]["first_ok_after"]["year"] == 2025 and problem["evidence"]["first_ok_after"]["codes"] > 2000
    assert "2014–2024 年每年只有" in problem["detail"] and "要求每年不少于 500 个" in problem["detail"]
    # 缺口顺 spec 传到 H 股实证的设置与结果表
    assert entry["affected_elements"][0] == "D6" and {"B7", "R5", "R7"} <= set(entry["affected_elements"])
    assert not {"F1", "F2", "F3", "R1", "R2"} & set(entry["affected_elements"])  # A 股主线不受影响
    report = dc.render_gap_report(result)
    assert "截面塌陷（cross_section_collapse）" in report and "逐年标的数 2014:" in report and "H股个股日行情" in report

    dc.save_check(tmp_path, R010, result)
    assert (ws / "data_check.json").is_file() and _real_case_listing(R010) == listing  # 真实案例目录没有被动过


@pytest.mark.skipif(
    not _has_case(R009, "ashare_stock_trade.parquet", "macro_cache.parquet", "macro_gdp.parquet", "bond_yield_curve.parquet", "financial_future_price.parquet"),
    reason="本机没有 r009 案例或它用到的替代数据文件",
)
def test_replay_r009_substitutes_show_as_substituted(tmp_path: Path) -> None:
    listing = _real_case_listing(R009)
    _clone_case(tmp_path, R009)
    result = dc.check_requirements(tmp_path, R009, data_root=LOCAL_DATA, probe={})
    replaced = [e for e in result["requirements"] if e["status_plan"] == "substitute"]
    assert len(replaced) == 3 and all(e["substituted"] is True for e in replaced) and result["summary"]["substituted"] == 3
    whole_a, level1, level2 = replaced
    # 万得全A → 个股行情合成：认出替代文件，文件在
    assert whole_a["result"] == "ok" and whole_a["files"] == ["ashare_stock_trade.parquet"]
    # 一级中观指标库 → 本地宏观指标池：认出其中写了全名的几个文件，都在
    assert level1["result"] == "ok" and level1["files"] == ["macro_cache.parquet", "macro_gdp.parquet", "bond_yield_curve.parquet", "financial_future_price.parquet"]
    # 二级中观指标库 → 「同一本地宏观指标池子集」：没有写文件名，机器查不了，但仍显示已替代
    assert level2["result"] == "unchecked" and level2["files"] == [] and _codes(level2) == ["not_machine_checkable"]
    assert not any(e["plan_mismatch"] for e in replaced) and not [e for e in dc.open_gaps(result) if e["status_plan"] == "substitute"]
    assert result["summary"]["total"] == 8
    report = dc.render_gap_report(result)
    if result["summary"]["gaps"]:  # 本机别的数据文件不全时才会有缺口；三条替代照样列在「已替代」里
        assert "## 已替代（3 条，不算缺口）" in report
    else:
        assert report.startswith("没有数据缺口（8 条数据需求：") and "；已替代 3 条" in report
    assert _real_case_listing(R009) == listing


def test_clear_dispositions_keeps_a_trace_and_reopens_the_gap(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "workspace" / "r1").mkdir(parents=True)
    result = {
        "version": dc.CHECK_VERSION,
        "requirements": [
            {"name": "A", "result": "missing", "gap_key": "k1", "disposition": {"choice": "mock", "checkpoint": "cp_01"}},
            {"name": "B", "result": "partial", "gap_key": "k2", "disposition": {"choice": "drop", "checkpoint": "cp_01"}},
            {"name": "C", "result": "ok", "gap_key": None, "disposition": None},
        ],
    }
    assert dc.clear_dispositions(root, "r1", reason="x") == {}  # 还没有体检结果：什么都不写
    dc._write_check(root, "r1", result)
    after = dc.clear_dispositions(root, "r1", reason="人决定改用别的处置方式", names=["A"])
    by_name = {e["name"]: e for e in after["requirements"]}
    assert by_name["A"]["disposition"] is None and by_name["A"]["cleared_disposition"]["choice"] == "mock"
    assert by_name["A"]["cleared_disposition"]["reason"] == "人决定改用别的处置方式"
    assert by_name["B"]["disposition"]["choice"] == "drop" and after["summary"]["open_gaps"] == 1
    after = dc.clear_dispositions(root, "r1", reason="再来")
    assert [e["name"] for e in dc.open_gaps(after)] == ["A", "B"]
    assert dc.load_check(root, "r1")["summary"]["open_gaps"] == 2
