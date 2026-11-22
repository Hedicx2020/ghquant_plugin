"""数据体检：目录体检（批次 A）与数据需求体检（批次 C）。

目录体检：对数据根目录下的每个文件记录字段与类型、行数、日期起止；带证券代码和日期的表
再算每年的标的数与交易日数。结果缓存到 workspace/_registry/data_probe.json，按文件大小与
修改时间失效。只读，不改数据目录里的任何东西。

需求体检（文件后半部分）：把 plan.md 的 data_requirements 逐条对着数据核对——文件在不在、
字段齐不齐、区间盖不盖得住、每年标的数有没有塌陷、频率、主键重复、关键字段缺失率、财务类
数据有没有披露日列——结论写 workspace/<id>/data_check.json，缺口留给人在检查点处置。
除这个文件外不写任何东西，不碰 state.json。

读 parquet 需要 pyarrow（复现环境里 pandas 读 parquet 本来就要用它）；没装时目录探测降级为
只记文件大小、需求体检降级为文件存在性检查，并在结果里写明。模块顶层只依赖标准库与 pyyaml。
"""

from __future__ import annotations

import calendar
import difflib
import json
import os
import re
import subprocess
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Optional

import yaml

from . import mdslice as ms

PROBE_VERSION = 2
REGISTRY_DIR = "workspace/_registry"
PROBE_JSON = f"{REGISTRY_DIR}/data_probe.json"
PROBE_MD = f"{REGISTRY_DIR}/data_probe.md"

# 证券代码列、日期列的识别顺序（排在前面的优先）
CODE_COLUMNS = (
    "stock_code", "stcode", "secu_code", "ts_code", "symbol", "ticker",
    "index_code", "fund_code", "bond_code", "contract_code", "option_code",
    "indicator_code", "inner_code", "InnerCode", "company_code",
)
DATE_COLUMNS = (
    "date", "trade_dt", "trade_date", "trading_day", "cal_date", "TradingDay",
    "end_date", "report_date", "info_publ_date", "publ_date", "ann_date",
)
PUBL_DATE_COLUMNS = ("info_publ_date", "publ_date", "ann_date")
SPARSE_RATIO = 0.10  # 标的数不到峰值的这个比例，才算稀疏年份
SPARSE_MIN_PEAK = 50  # 峰值标的数不到这个数的表不判（本来就是小截面）
CLIFF_RATIO = 5.0  # 稀疏年份与相邻的正常年份相差这么多倍，才算截面塌陷（逐年自然增长的不算）
SHORT_YEAR_RATIO = 0.60  # 日频表的中间年份，日期数不到常年的这个比例，记为不完整年份
SKIP_DIR_NAMES = {"__pycache__", ".git", ".ipynb_checkpoints"}
DATA_SUFFIXES = {".parquet", ".csv", ".feather", ".xlsx", ".xls", ".h5", ".hdf", ".pkl", ".json", ".txt"}


def resolve_data_root(root: Path) -> Path:
    """数据根目录：从工作区根向上找最近的 .reproduce.json 的 data_root，找不到用 ~/local_data。

    与 common/data_loader.get_data_root 的规则一致（那边从当前目录找起）。内核不导入 common/。
    """
    for directory in [root, *root.parents]:
        cfg = directory / ".reproduce.json"
        if cfg.is_file():
            try:
                config = json.loads(cfg.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                break
            data_root = config.get("data_root") if isinstance(config, dict) else None
            if isinstance(data_root, str) and data_root:
                return Path(data_root).expanduser()
            break
    return Path.home() / "local_data"


def _have_pyarrow() -> bool:
    try:
        import pyarrow.parquet  # noqa: F401
    except Exception:  # noqa: BLE001 - 任何导入失败都按「没有」处理
        return False
    return True


def _to_date_str(value: Any) -> Optional[str]:
    """把统计信息里的日期值规整成 YYYY-MM-DD；认不出来返回 None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, int) and not isinstance(value, bool):
        if 19000101 <= value <= 21001231:
            text = str(value)
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"
        return None
    if isinstance(value, str):
        m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})", value.strip())
        if m and 1900 <= int(m.group(1)) <= 2100:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _column_range(metadata: Any, index: int) -> Optional[tuple[str, str]]:
    """从各行组的统计信息取一列的最小、最大值（不读数据）。任何一个行组没有统计就放弃。"""
    lows: list[str] = []
    highs: list[str] = []
    for g in range(metadata.num_row_groups):
        stats = metadata.row_group(g).column(index).statistics
        if stats is None or not stats.has_min_max:
            return None
        low, high = _to_date_str(stats.min), _to_date_str(stats.max)
        if low is None or high is None:
            return None
        lows.append(low)
        highs.append(high)
    return (min(lows), max(highs)) if lows else None


def _yearly_stats(parquet_file: Any, code: str, date_col: str) -> Optional[dict[str, dict[str, int]]]:
    """逐年的标的数与交易日数。只读代码列和日期列，按批聚合。"""
    import pyarrow as pa
    import pyarrow.compute as pc

    codes: dict[int, set] = {}
    days: dict[int, set] = {}
    for batch in parquet_file.iter_batches(batch_size=2_000_000, columns=[code, date_col]):
        d = batch.column(date_col)
        c = batch.column(code)
        t = d.type
        if pa.types.is_dictionary(t):
            d = pc.cast(d, t.value_type)
            t = d.type
        if pa.types.is_timestamp(t) or pa.types.is_date(t):
            year = pc.year(d)
        elif pa.types.is_string(t) or pa.types.is_large_string(t):
            year = pc.cast(pc.utf8_slice_codeunits(d, 0, 4), pa.int32(), safe=False)
        elif pa.types.is_integer(t):
            year = pc.cast(pc.divide(d, 10000), pa.int32(), safe=False)
        else:
            return None
        table = pa.table({"y": year, "c": c, "d": d})
        by_code = table.group_by(["y", "c"]).aggregate([])
        for y, value in zip(by_code.column("y").to_pylist(), by_code.column("c").to_pylist()):
            if y is not None and value is not None:
                codes.setdefault(y, set()).add(value)
        by_day = table.group_by(["y", "d"]).aggregate([])
        for y, value in zip(by_day.column("y").to_pylist(), by_day.column("d").to_pylist()):
            if y is not None and value is not None:
                days.setdefault(y, set()).add(value)
    years = sorted(y for y in set(codes) | set(days) if 1900 <= y <= 2100)
    return {str(y): {"codes": len(codes.get(y, ())), "days": len(days.get(y, ()))} for y in years}


def _typical_days(yearly: dict[str, dict[str, int]]) -> Optional[float]:
    """常年的日期数：取最近几个完整年份的中位数（最后一年通常没走完，不算）。"""
    years = sorted(yearly)
    complete = years[:-1] if len(years) > 1 else years
    recent = [yearly[y]["days"] for y in complete[-5:]]
    return median(recent) if recent else None


def _freq_guess(yearly: dict[str, dict[str, int]]) -> Optional[str]:
    typical = _typical_days(yearly)
    if typical is None:
        return None
    if typical >= 180:
        return "日"
    if 40 <= typical <= 60:
        return "周"
    if 10 <= typical <= 14:
        return "月"
    if 3 <= typical <= 5:
        return "季"
    if typical <= 2:
        return "年"
    return "不规则"


def _ranges(years: list[int]) -> str:
    """把年份列表写成 2014–2024、2026 这样的区间。"""
    if not years:
        return ""
    years = sorted(years)
    out: list[str] = []
    start = prev = years[0]
    for y in years[1:]:
        if y == prev + 1:
            prev = y
            continue
        out.append(f"{start}–{prev}" if start != prev else str(start))
        start = prev = y
    out.append(f"{start}–{prev}" if start != prev else str(start))
    return "、".join(out)


def yearly_flags(yearly: dict[str, dict[str, int]], this_year: Optional[int] = None) -> list[dict[str, str]]:
    """从逐年统计里找出值得人看一眼的情况。只陈述事实，不下「数据不可用」的结论。

    - year_gap：起止之间有整年没有数据；
    - sparse_years：截面塌陷——某些年份的标的数不到峰值的一成，且与相邻的正常年份相差 5 倍
      以上。标的数逐年自然增长（如基金、指数的早年）不算；
    - short_years：日频表里，中间某些年份的日期数明显少于常年。
    晚于今年的年份（预测类数据会有）不参与判断。
    """
    flags: list[dict[str, str]] = []
    this_year = this_year or datetime.now().year
    years = sorted(int(y) for y in yearly if int(y) <= this_year)
    if not years:
        return flags
    codes = {y: yearly[str(y)]["codes"] for y in years}
    days = {y: yearly[str(y)]["days"] for y in years}

    missing = [y for y in range(years[0], years[-1] + 1) if y not in codes]
    if missing:
        flags.append({"code": "year_gap", "detail": f"{_ranges(missing)} 年没有任何数据"})

    peak = max(codes.values())
    if peak >= SPARSE_MIN_PEAK:
        sparse = [y for y in years if codes[y] < peak * SPARSE_RATIO]
        sparse_set = set(sparse)
        cliffs: list[tuple[int, int]] = []  # （稀疏年, 相邻的正常年）
        for a, b in zip(years, years[1:]):
            if (a in sparse_set) == (b in sparse_set):
                continue
            low, high = (a, b) if a in sparse_set else (b, a)
            if codes[high] >= SPARSE_MIN_PEAK and codes[high] > max(codes[low], 1) * CLIFF_RATIO:
                cliffs.append((low, high))
        if sparse and cliffs:
            low_n, high_n = min(codes[y] for y in sparse), max(codes[y] for y in sparse)
            span = f"{low_n}" if low_n == high_n else f"{low_n}–{high_n}"
            jumps = "、".join(f"{high} 年有 {codes[high]} 个" for _low, high in cliffs[:3])
            flags.append(
                {
                    "code": "sparse_years",
                    "detail": f"{_ranges(sparse)} 年每年只有 {span} 个标的，而 {jumps}（峰值 {peak} 个）",
                }
            )

    typical = _typical_days(yearly)
    middle = years[1:-1]
    if typical is not None and typical >= 180 and middle:
        short = [y for y in middle if days[y] < typical * SHORT_YEAR_RATIO]
        if short:
            flags.append({"code": "short_years", "detail": f"{_ranges(short)} 年的日期数明显少于常年（常年约 {int(typical)} 个）"})
    return flags


def probe_file(path: Path, data_root: Path, yearly: bool = True) -> dict[str, Any]:
    """体检一个文件。出错不抛，写进结果的 error 字段。"""
    stat = path.stat()
    entry: dict[str, Any] = {
        "path": path.relative_to(data_root).as_posix(),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "format": path.suffix.lower().lstrip("."),
    }
    if path.suffix.lower() != ".parquet":
        return entry
    try:
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        schema = pf.schema_arrow
        meta = pf.metadata
        names = list(schema.names)
        entry.update(
            {
                "rows": meta.num_rows,
                "row_groups": meta.num_row_groups,
                "columns": [{"name": f.name, "type": str(f.type)} for f in schema],
            }
        )
        code_col = next((c for c in CODE_COLUMNS if c in names), None)
        date_cols = [c for c in DATE_COLUMNS if c in names]
        date_col = date_cols[0] if date_cols else None
        entry["code_column"] = code_col
        entry["date_column"] = date_col
        entry["publ_date_column"] = next((c for c in PUBL_DATE_COLUMNS if c in names), None)
        ranges: dict[str, dict[str, str]] = {}
        for col in date_cols:
            found = _column_range(meta, names.index(col))
            if found:
                ranges[col] = {"min": found[0], "max": found[1]}
        entry["date_ranges"] = ranges
        if yearly and code_col and date_col and meta.num_rows:
            stats = _yearly_stats(pf, code_col, date_col)
            if stats is not None:
                entry["yearly"] = stats
                entry["freq_guess"] = _freq_guess(stats)
                entry["flags"] = yearly_flags(stats)
    except Exception as exc:  # noqa: BLE001 - 单个文件读不了不该让整次体检失败
        entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return entry


def _iter_data_files(data_root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(data_root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            path = Path(dirpath) / name
            if path.suffix.lower() in DATA_SUFFIXES:
                yield path


def load_probe(root: Path) -> Optional[dict[str, Any]]:
    path = root / PROBE_JSON
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def run_probe(
    root: Path,
    data_root: Optional[Path] = None,
    yearly: bool = True,
    use_cache: bool = True,
    workers: Optional[int] = None,
) -> dict[str, Any]:
    """体检整个数据目录，返回结果（不写盘；写盘用 save_probe）。"""
    data_root = (data_root or resolve_data_root(root)).expanduser()
    started = time.time()
    result: dict[str, Any] = {
        "version": PROBE_VERSION,
        "data_root": str(data_root),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "yearly": yearly,
        "pyarrow": _have_pyarrow(),
        "files": {},
    }
    if not data_root.is_dir():
        result["error"] = f"数据根目录不存在: {data_root}"
        return result

    cached: dict[str, Any] = {}
    previous = load_probe(root) if use_cache else None
    if previous and previous.get("version") == PROBE_VERSION and previous.get("data_root") == str(data_root):
        cached = previous.get("files") or {}

    paths = list(_iter_data_files(data_root))
    todo: list[Path] = []
    for path in paths:
        rel = path.relative_to(data_root).as_posix()
        old = cached.get(rel)
        stat = path.stat()
        fresh = (
            isinstance(old, dict)
            and old.get("size") == stat.st_size
            and old.get("mtime_ns") == stat.st_mtime_ns
            and not old.get("error")
            and (not yearly or path.suffix.lower() != ".parquet" or "yearly" in old or not (old.get("code_column") and old.get("date_column")))
        )
        if fresh:
            result["files"][rel] = old
        else:
            todo.append(path)

    if todo and not result["pyarrow"]:
        for path in todo:
            entry = probe_file(path, data_root, yearly=False) if path.suffix.lower() != ".parquet" else {
                "path": path.relative_to(data_root).as_posix(),
                "size": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "format": "parquet",
                "error": "未安装 pyarrow，无法读取元数据",
            }
            result["files"][entry["path"]] = entry
    elif todo:
        with ThreadPoolExecutor(max_workers=workers or min(8, (os.cpu_count() or 2))) as pool:
            for entry in pool.map(lambda p: probe_file(p, data_root, yearly), todo):
                result["files"][entry["path"]] = entry

    result["files"] = dict(sorted(result["files"].items()))
    result["stats"] = {
        "files": len(paths),
        "probed": len(todo),
        "from_cache": len(paths) - len(todo),
        "bytes": sum(f.get("size", 0) for f in result["files"].values()),
        "seconds": round(time.time() - started, 2),
        "errors": sum(1 for f in result["files"].values() if f.get("error")),
        "flagged": sum(1 for f in result["files"].values() if f.get("flags")),
    }
    return result


# ---------------------------------------------------------------------------
# 与手写数据目录对照
# ---------------------------------------------------------------------------

_CATALOG_FILE_RE = re.compile(r"`([\w./-]+\.parquet)`")
_CLAIM_START_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:-(\d{1,2}))?\s*(?:~|～|至|起|-|—|–)")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_catalog(text: str) -> list[dict[str, Any]]:
    """从 data_catalog.md 的表格里取每个文件的声明：关键字段、覆盖区间。"""
    out: list[dict[str, Any]] = []
    header: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            header = []
            continue
        cells = [c.strip() for c in stripped[1:-1].split("|")]
        if all(re.fullmatch(r"[\s:-]*", c) for c in cells):
            continue
        if not header:
            header = cells
            continue
        files = _CATALOG_FILE_RE.findall(cells[0]) if cells else []
        if not files:
            continue
        row = {header[i]: cells[i] for i in range(min(len(header), len(cells)))}
        coverage = next((v for k, v in row.items() if "覆盖" in k), "")
        fields_text = next((v for k, v in row.items() if "字段" in k), "")
        fields: list[str] = []
        for token in (t.strip() for t in fields_text.split(",")):
            if token == "OHLC":  # 目录里的惯用简写
                fields += ["open", "high", "low", "close"]
            elif _IDENT_RE.match(token):
                fields.append(token)
        m = _CLAIM_START_RE.search(coverage)
        for name in files:
            out.append(
                {
                    "file": name,
                    "coverage": coverage,
                    "claimed_start_year": int(m.group(1)) if m else None,
                    "fields": fields,
                }
            )
    return out


def compare_with_catalog(probe: dict[str, Any], catalog_text: str) -> list[dict[str, str]]:
    """目录的声明与实测对不上的地方。level 为 warn 的值得改目录或提醒 planner。"""
    files = probe.get("files") or {}
    by_name: dict[str, dict[str, Any]] = {}
    for rel, entry in files.items():
        by_name.setdefault(Path(rel).name, entry)
    findings: list[dict[str, str]] = []
    documented: set[str] = set()
    for claim in parse_catalog(catalog_text):
        name = claim["file"]
        documented.add(Path(name).name)
        entry = files.get(name) or by_name.get(Path(name).name)
        if entry is None:
            findings.append({"level": "warn", "code": "catalog_missing_file", "file": name, "detail": "目录里写了这个文件，数据目录下没有"})
            continue
        columns = {c["name"] for c in entry.get("columns") or []}
        absent = [f for f in claim["fields"] if columns and f not in columns]
        if absent:
            findings.append({"level": "info", "code": "catalog_missing_field", "file": name, "detail": f"目录列出的字段在文件里找不到: {absent}"})
        date_col = entry.get("date_column")
        measured = (entry.get("date_ranges") or {}).get(date_col or "")
        claimed = claim["claimed_start_year"]
        # 引用目录原文时去掉 markdown 的强调符号；目录没写时间范围（空或「-」）就不引用
        quoted = re.sub(r"[*`]", "", claim["coverage"] or "").strip()
        prefix = f"目录写「{quoted}」，实测" if quoted.strip("-—– ") else "实测"
        if claimed and measured and int(measured["min"][:4]) > claimed + 1:
            findings.append(
                {
                    "level": "warn",
                    "code": "catalog_start_later",
                    "file": name,
                    "detail": f"{prefix}最早日期是 {measured['min']}",
                }
            )
        for flag in entry.get("flags") or []:
            if flag["code"] in ("sparse_years", "year_gap"):
                findings.append(
                    {
                        "level": "warn",
                        "code": f"catalog_{flag['code']}",
                        "file": name,
                        "detail": f"{prefix} {flag['detail']}",
                    }
                )
    top_level = sorted(rel for rel in files if "/" not in rel and rel.endswith(".parquet"))
    undocumented = [rel for rel in top_level if rel not in documented]
    if undocumented:
        findings.append(
            {
                "level": "info",
                "code": "catalog_undocumented",
                "file": "",
                "detail": f"数据目录顶层有 {len(undocumented)} 个文件没写进目录: {undocumented[:40]}" + ("…" if len(undocumented) > 40 else ""),
            }
        )
    return findings


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def _fmt_rows(n: Optional[int]) -> str:
    if n is None:
        return "-"
    if n >= 1e8:
        return f"{n / 1e8:.2f} 亿"
    if n >= 1e4:
        return f"{n / 1e4:.0f} 万"
    return str(n)


def _fmt_size(n: int) -> str:
    return f"{n / 1e9:.2f} GB" if n >= 1e9 else f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{n / 1e3:.0f} KB"


def _codes_summary(entry: dict[str, Any]) -> str:
    yearly = entry.get("yearly")
    if not yearly:
        return "-"
    counts = [v["codes"] for v in yearly.values()]
    return f"{min(counts)}–{max(counts)}" if min(counts) != max(counts) else str(counts[0])


def _range_summary(entry: dict[str, Any]) -> str:
    col = entry.get("date_column")
    rng = (entry.get("date_ranges") or {}).get(col or "")
    if rng:
        return f"{rng['min']} ~ {rng['max']}"
    yearly = entry.get("yearly")
    if yearly:
        years = sorted(yearly)
        return f"{years[0]} ~ {years[-1]}（按年）"
    return "-"


def render_markdown(probe: dict[str, Any], findings: Optional[list[dict[str, str]]] = None) -> str:
    """数据实况表：给人和 planner 看的摘要。顶层文件逐个列，子目录按目录汇总。"""
    files = probe.get("files") or {}
    stats = probe.get("stats") or {}
    lines = [
        "# 数据实况表",
        "",
        f"> 由 `flow data probe` 实测生成，{probe.get('generated_at', '')}。数据根目录：`{probe.get('data_root', '')}`。",
        f"> 共 {stats.get('files', len(files))} 个文件，{_fmt_size(stats.get('bytes', 0))}。"
        "数据可得性以本表为准；`templates/data_catalog.md` 是说明性文字，两者对不上的地方列在文末。",
        "",
    ]
    if probe.get("error"):
        lines += [f"**体检失败**：{probe['error']}", ""]
        return "\n".join(lines)

    top = {rel: e for rel, e in files.items() if "/" not in rel}
    nested: dict[str, list[dict[str, Any]]] = {}
    for rel, e in files.items():
        if "/" in rel:
            nested.setdefault(str(Path(rel).parent), []).append(e)

    lines += ["## 顶层文件", "", "| 文件 | 行数 | 代码列 | 每年标的数 | 日期列 | 起止 | 频率 | 披露日列 | 提示 |", "|---|---|---|---|---|---|---|---|---|"]
    for rel, e in top.items():
        notes = "；".join(f["detail"] for f in e.get("flags") or [])
        if e.get("error"):
            notes = f"读取失败：{e['error']}"
        lines.append(
            f"| `{rel}` | {_fmt_rows(e.get('rows'))} | {e.get('code_column') or '-'} | {_codes_summary(e)} | "
            f"{e.get('date_column') or '-'} | {_range_summary(e)} | {e.get('freq_guess') or '-'} | "
            f"{e.get('publ_date_column') or '-'} | {notes or '-'} |"
        )

    if nested:
        lines += ["", "## 子目录（按目录汇总，逐文件明细在 data_probe.json）", "", "| 目录 | 文件数 | 大小 | 字段 | 起止 | 有提示的文件 |", "|---|---|---|---|---|---|"]
        for directory in sorted(nested):
            entries = nested[directory]
            schemas: dict[str, int] = {}
            lows: list[str] = []
            highs: list[str] = []
            for e in entries:
                key = ", ".join(c["name"] for c in e.get("columns") or [])
                schemas[key] = schemas.get(key, 0) + 1
                rng = (e.get("date_ranges") or {}).get(e.get("date_column") or "")
                if rng:
                    lows.append(rng["min"])
                    highs.append(rng["max"])
            common_schema = max(schemas, key=schemas.get) if schemas else "-"
            if len(common_schema) > 60:
                common_schema = common_schema[:60] + "…"
            schema_note = common_schema if len(schemas) <= 1 else f"{common_schema}（另有 {len(schemas) - 1} 种）"
            flagged = [Path(e["path"]).name for e in entries if e.get("flags") or e.get("error")]
            flagged_note = "-" if not flagged else f"{len(flagged)} 个：" + "、".join(flagged[:5]) + ("…" if len(flagged) > 5 else "")
            lines.append(
                f"| `{directory}/` | {len(entries)} | {_fmt_size(sum(e.get('size', 0) for e in entries))} | {schema_note or '-'} | "
                f"{(min(lows) + ' ~ ' + max(highs)) if lows else '-'} | {flagged_note} |"
            )

    if findings is not None:
        warns = [f for f in findings if f["level"] == "warn"]
        infos = [f for f in findings if f["level"] != "warn"]
        lines += ["", "## 与 data_catalog.md 对不上的地方", ""]
        if not findings:
            lines.append("没有发现出入。")
        for f in warns:
            lines.append(f"- `{f['file']}`：{f['detail']}")
        for f in infos:
            lines.append(f"- （提示）" + (f"`{f['file']}`：" if f["file"] else "") + f["detail"])
    lines.append("")
    return "\n".join(lines)


def save_probe(root: Path, probe: dict[str, Any], findings: Optional[list[dict[str, str]]] = None) -> tuple[Path, Path]:
    """把体检结果写到 workspace/_registry/（原子替换）。"""
    target = root / PROBE_JSON
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(probe)
    if findings is not None:
        payload["catalog_findings"] = findings
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, target)
    md = root / PROBE_MD
    md_tmp = md.with_suffix(".md.tmp")
    md_tmp.write_text(render_markdown(probe, findings), encoding="utf-8")
    os.replace(md_tmp, md)
    return target, md


# ===========================================================================
# 数据需求体检：plan 的 data_requirements 逐条对着数据核对
# ===========================================================================

CHECK_VERSION = 1
CHECK_JSON = "data_check.json"  # 落在 workspace/<id>/ 下
RESULTS = ("ok", "partial", "missing", "unchecked")
GAP_RESULTS = ("partial", "missing")  # 算缺口的结论，要人给处置决定
DISPOSITIONS = ("supply", "substitute", "narrow", "mock", "drop", "abort")

RESULT_CN = {"ok": "通过", "partial": "部分满足", "missing": "缺失", "unchecked": "未机检"}
DISPOSITION_CN = {
    "supply": "补数据",
    "substitute": "等价替代",
    "narrow": "缩小范围",
    "mock": "先用 mock 试跑",
    "drop": "砍掉相关要素",
    "abort": "终止",
}
PROBLEM_CN = {
    "file_missing": "文件不存在",
    "file_unreadable": "文件读不了",
    "field_missing": "缺字段",
    "period_short": "区间盖不住",
    "cross_section_collapse": "截面塌陷",
    "freq_mismatch": "频率不够",
    "dup_keys": "主键重复",
    "null_rate": "关键字段缺失率过高",
    "no_publ_date": "财务类数据没有披露日列",
    "smoke_failed": "取数冒烟调用失败",
    "smoke_not_run": "冒烟调用没有执行",
    "not_machine_checkable": "机器查不了",
    "declared_missing": "plan 已标缺失",
}
# 只说明「没查成」的问题代码：一条需求只有它们时，结论是未机检，不算缺口
UNCHECKED_CODES = ("not_machine_checkable", "smoke_not_run")

# plan 里可写的机器可查字段；一个都没写的需求按旧 plan 处理（只查文件在不在）
MACHINE_FIELDS = ("files", "fields", "period", "freq", "min_codes", "probe", "keys", "max_null_rate")
FREQS = ("D", "W", "M", "Q", "A")  # 由细到粗
FREQ_CN = {"D": "日", "W": "周", "M": "月", "Q": "季", "A": "年"}
# 每年至少有这么多个不同的日期，才算达到这个频率（档位与 _freq_guess 一致）
FREQ_MIN_DATES = {"D": 180, "W": 40, "M": 10, "Q": 3, "A": 1}
# 区间起止允许的出入（日历日）：日频要容得下长假，低频数据的日期多落在期末
PERIOD_TOLERANCE_DAYS = {"D": 10, "W": 14, "M": 35, "Q": 100, "A": 370}
NULL_RATE_LIMIT = 0.5  # 关键字段的缺失率超过它算过高；单条需求可用 max_null_rate 改
DUP_NOT_KEY_RATE = 0.05  # 按默认主键查重时多出来的行超过这个比例，说明默认主键不是这张表的主键，不判
SAMPLE_ROWS = 1_000_000  # 要读数据的检查（查重、缺失率）每个文件最多读这么多行
DATE_ONLY_MAX_ROWS = 20_000_000  # 没有代码列的表要现算每年日期数时，行数超过它就放弃
SMOKE_TIMEOUT = 60  # 冒烟调用的时限（秒）
AFFECTED_LIMIT = 300  # 一条需求最多传递到这么多个要素，防失控

# 「财务类」文件的认定，见 _is_financial
FINANCIAL_FILE_TOKENS = ("balance", "income", "cashflow", "financial", "finance", "fina")
FINANCIAL_NAME_KEYWORDS = ("财务", "财报", "利润表", "资产负债", "现金流量")
REPORT_PERIOD_COLUMNS = ("end_date", "report_date", "report_period")

_TZ_CN = timezone(timedelta(hours=8))


def _now_cn() -> str:
    """ISO8601 时间戳，固定带 +08:00（与 tools/state.py 的口径一致）。"""
    return datetime.now(_TZ_CN).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 读 plan：data_requirements 归一
# ---------------------------------------------------------------------------

_STATUS_RE = re.compile(r"[a-z_]+")
_DAY_RE = re.compile(r"(\d{4})年?(?:[-/.]?(\d{1,2})月?)?(?:[-/.]?(\d{1,2})日?)?")
_PERIOD_SPLIT_RE = re.compile(r"\s*(?:~|～|至|到|—|–|\.{2,}|\s-\s|\bto\b)\s*")
_YEAR_SPAN_RE = re.compile(r"((?:19|20)\d{2})\s*-\s*((?:19|20)\d{2})")
_OPEN_WORDS = {"", "至今", "今", "now", "today", "present", "latest", "none", "null", "-"}
_FREQ_ALIASES = {
    **{k: "D" for k in ("d", "b", "1d", "day", "daily", "日", "日频", "日度")},
    **{k: "W" for k in ("w", "1w", "week", "weekly", "周", "周频", "周度")},
    **{k: "M" for k in ("m", "1m", "me", "month", "monthly", "月", "月频", "月度")},
    **{k: "Q" for k in ("q", "quarter", "quarterly", "季", "季频", "季度")},
    **{k: "A" for k in ("a", "y", "year", "yearly", "annual", "annually", "年", "年频", "年度")},
}
_TRUE_WORDS = {"true", "yes", "y", "1", "是", "核心"}
_FALSE_WORDS = {"false", "no", "n", "0", "否", "非核心"}


def _plan_frontmatter(root: Path, report_id: str) -> Optional[dict[str, Any]]:
    """plan.md 的 frontmatter；文件不在、没有 frontmatter 或 YAML 解析不了都返回 None。"""
    path = root / "workspace" / report_id / "plan.md"
    if not path.is_file():
        return None
    try:
        text = ms.read_source(path)
    except (OSError, UnicodeDecodeError):
        return None
    span = ms.frontmatter_span(text)
    if not span:
        return None
    body = re.sub(r"\A---[ \t]*\r?\n", "", text[span[0]:span[1]])
    body = re.sub(r"\r?\n---[ \t]*(?:\r?\n|\Z)\Z", "", body)
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def plan_requirements_hash(root: Path, report_id: str) -> Optional[str]:
    """plan.md 里 data_requirements 一段的内容哈希；plan 读不到或没有这一段返回 None。

    按解析后的内容算（键排序后的规范 JSON），所以只在数据需求本身变了才变：改 plan 的其他部分、
    调缩进、加注释都不影响；增删改任何一条需求的任何字段（含 note 这类自由字段）或调换顺序都会变。
    内核用它判断数据需求有没有被改动、要不要重检。
    """
    frontmatter = _plan_frontmatter(root, report_id)
    if frontmatter is None or "data_requirements" not in frontmatter:
        return None
    raw = frontmatter["data_requirements"]
    try:
        canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    except TypeError:  # 键的类型混杂、排不了序
        canonical = repr(raw)
    return ms.slice_hash(canonical)


def _as_list(value: Any) -> list[str]:
    """YAML 里写成列表，或一串用逗号、分号、加号、空白隔开的文字，都规整成字符串列表。"""
    if value is None or isinstance(value, bool):
        return []
    items = value if isinstance(value, (list, tuple)) else re.split(r"[,，;；+\s]+", str(value))
    return [text for text in (str(item).strip().strip("`'\"") for item in items if item is not None) if text]


def _as_elements(value: Any) -> list[str]:
    """要素编号列表：`D1-D3` 这类区间展开；认不出是 D/F/B/R/SA 编号的（如 FIG5）照原样留着。"""
    out: list[str] = []
    for item in _as_list(value):
        out.extend(ms.extract_refs(item) or [item])
    return list(dict.fromkeys(out))


def _parse_day(value: Any, end: bool = False) -> Optional[str]:
    """把 plan 里写的日期规整成 YYYY-MM-DD。只写到年或月的，作起点取期初、作终点取期末；认不出返回 None。"""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, bool):
        return None
    m = _DAY_RE.fullmatch(str(value).strip())
    if not m or not 1900 <= int(m.group(1)) <= 2100:
        return None
    year = int(m.group(1))
    month = int(m.group(2)) if m.group(2) else (12 if end else 1)
    if not 1 <= month <= 12:
        return None
    last = calendar.monthrange(year, month)[1]
    day = int(m.group(3)) if m.group(3) else (last if end else 1)
    return date(year, month, day).isoformat() if 1 <= day <= last else None


def _parse_period(value: Any) -> tuple[Optional[list[Optional[str]]], bool]:
    """period 可以写 [起, 止]、"起~止"（也认 ～、至、到、—，以及 "2014-2024" 这种年份区间）或 {start, end}；哪头留空或写「至今」表示那头不限。

    返回（[起, 止] 或 None, 写法认不认得出）。没写算认得出；起止颠倒、两头都空、日期认不出算认不出。
    """
    if value is None:
        return None, True
    if isinstance(value, dict):
        parts: list[Any] = [value.get("start"), value.get("end")]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    elif isinstance(value, (date, datetime)):
        parts = [value]
    else:
        text = str(value).strip()
        years = _YEAR_SPAN_RE.fullmatch(text)  # "2014-2024"：两个年份中间一个连字符
        parts = list(years.groups()) if years else _PERIOD_SPLIT_RE.split(text, maxsplit=1)
    parts = (parts + [None, None])[:2]
    is_open = [p is None or str(p).strip().lower() in _OPEN_WORDS for p in parts]
    start, end = _parse_day(parts[0]), _parse_day(parts[1], end=True)
    valid = (
        (start is not None or is_open[0])
        and (end is not None or is_open[1])
        and (start is not None or end is not None)
        and not (start and end and start > end)
    )
    return ([start, end] if valid else None), valid


def _parse_freq(value: Any) -> Optional[str]:
    return None if value is None or isinstance(value, bool) else _FREQ_ALIASES.get(str(value).strip().lower())


def _parse_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool) or value is None:
        return value
    text = str(value).strip().lower()
    return True if text in _TRUE_WORDS else False if text in _FALSE_WORDS else None


def _parse_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(float(str(value).strip()))
    except (ValueError, OverflowError):
        return None
    return number if number >= 0 else None


def _parse_rate(value: Any) -> Optional[float]:
    """0–1 之间的比例，也认 `30%` 这种写法。"""
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    try:
        rate = float(text.rstrip("%")) / (100 if text.endswith("%") else 1)
    except ValueError:
        return None
    return rate if 0 <= rate <= 1 else None


def _normalize_requirement(raw: Any, index: int) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {"name": str(raw), "source": str(raw)}

    def text(key: str) -> str:
        return "" if item.get(key) is None else str(item.get(key)).strip()

    status = _STATUS_RE.match(text("status").lower())
    period, period_ok = _parse_period(item.get("period"))
    parsed = {
        "freq": _parse_freq(item.get("freq")),
        "min_codes": _parse_int(item.get("min_codes")),
        "max_null_rate": _parse_rate(item.get("max_null_rate")),
    }
    invalid = ([] if period_ok else ["period"]) + [k for k, v in parsed.items() if item.get(k) is not None and v is None]
    return {
        "index": index,
        "name": text("name") or f"（第 {index + 1} 条，未命名）",
        "source": text("source"),
        "status": status.group(0) if status else "",
        "note": text("note"),
        "files": _as_list(item.get("files")),
        "fields": _as_list(item.get("fields")),
        "period": period,
        "freq": parsed["freq"],
        "min_codes": parsed["min_codes"],
        "core": _parse_bool(item.get("core")),
        "elements": _as_elements(item.get("elements")),
        "probe": text("probe") or None,
        "keys": None if item.get("keys") is None else _as_list(item.get("keys")),
        "max_null_rate": parsed["max_null_rate"],
        "legacy": not any(item.get(k) is not None for k in MACHINE_FIELDS),
        "invalid": invalid,
    }


def requirements_from_plan(root: Path, report_id: str) -> list[dict[str, Any]]:
    """读 plan.md frontmatter 的 data_requirements，归一成统一形状（新旧字段都认）。

    每条返回：
    - 旧字段 name / source / status（小写，plan 没写为空串）/ note；
    - 机器可查字段 files（list）、fields（list，`OHLC` 这类简写核对时再展开）、
      period（[起, 止]，YYYY-MM-DD，哪头不限哪头为 None；整项没写为 None；可以写成 [a, b]、
      "a~b" 或 {start, end}，只写到年或月的起点取期初、终点取期末）、freq（D/W/M/Q/A 或 None，
      也认 daily、日频 这类写法）、min_codes（int 或 None）、core（bool，没标为 None）、
      elements（list，`D1-D3` 展开）、probe（冒烟命令或 None）；
    - 本模块另认两个可选字段：keys（主键列；None=按默认猜，[]=不查重）、
      max_null_rate（关键字段缺失率上限，None=按 NULL_RATE_LIMIT）；
    - index（在 plan 里的序号）、legacy（一个机器可查字段都没写）、invalid（写了但认不出的字段名）。
    plan 不存在、没有 frontmatter 或没有 data_requirements 时返回空列表。
    """
    frontmatter = _plan_frontmatter(root, report_id)
    raw = frontmatter.get("data_requirements") if frontmatter else None
    return [_normalize_requirement(item, i) for i, item in enumerate(raw)] if isinstance(raw, list) else []


# ---------------------------------------------------------------------------
# 读 spec：把缺口传递到受影响的要素
# ---------------------------------------------------------------------------

_CLAUSE_RE = re.compile(r"^\s*((?:依赖|关联)[^:：/]{0,10})[:：](.*)$", re.DOTALL)


def _relation_clauses(block: ms.Block) -> dict[str, list[str]]:
    """把要素块里「依赖数据: D1, D2 / 关联基准: R1 / 关联歧义: A3」这类字段拆成 {小标题: [要素编号]}。"""
    out: dict[str, list[str]] = {}
    for fld in block.fields:
        if not fld.name.startswith(("依赖", "关联")):
            continue
        label = fld.name
        for part in re.sub(r"^-\s*[^:：]+[:：]", "", fld.text, count=1).split("/"):
            m = _CLAUSE_RE.match(part)
            if m:
                label, part = m.group(1).strip(), m.group(2)
            out.setdefault(label, []).extend(ms.extract_refs(part))
    return out


def _spec_graph(root: Path, report_id: str) -> Optional[dict[str, Any]]:
    """从 spec.md 读出「X 受影响则 Y 也受影响」的边；spec 不存在或读不了返回 None。

    边的来历（宁多勿漏，但不走方向不明的关联）：
    - Y 的「依赖数据」写了 X：X → Y；
    - X 的「关联基准」写了 Y：X → Y（X 算出来的结果要拿 Y 对数）；
    - X 是数据要素（D 类），它的「关联要素」写了 Y：X → Y（D 类的关联要素就是用这份数据的要素）；
    - Y 是结果或稳健性要素（R / SA 类），它的「关联要素」写了 X：X → Y（R / SA 的关联要素是它的来源）；
    - F、B 类的「关联要素」里上下游混着写，只走方向确定的两种：写的是数据要素 D，D → 它；
      写的是结果或稳健性要素 R / SA，它 → R / SA。写的是别的 F、B 要素时方向不明，不沿它传递
      （否则一份支线数据的缺口会经共用的因子定义漫到主线的全部结果）。
    行级编号（如 R2.3）在 spec 里没有对应要素块时归到上一级（R2）。
    """
    path = root / "workspace" / report_id / "spec" / "spec.md"
    if not path.is_file():
        return None
    try:
        blocks = [b for b in ms.parse_blocks(ms.read_source(path)) if b.prefix in ms.ELEMENT_PREFIXES]
    except Exception:  # noqa: BLE001 - spec 读不了或解析不了，都按没有 spec 处理
        return None
    order = {b.id: i for i, b in enumerate(blocks)}

    def pairs(block: ms.Block) -> Iterable[tuple[str, str]]:
        for label, refs in _relation_clauses(block).items():
            if label.startswith("依赖"):
                yield from ((ref, block.id) for ref in refs)
            elif label.startswith("关联基准"):
                yield from ((block.id, ref) for ref in refs)
            elif label.startswith("关联要素") and block.prefix == "D":
                yield from ((block.id, ref) for ref in refs)
            elif label.startswith("关联要素") and block.prefix in ("R", "SA"):
                yield from ((ref, block.id) for ref in refs)
            elif label.startswith("关联要素"):
                yield from ((ref, block.id) for ref in refs if _ref_prefix(ref) == "D")
                yield from ((block.id, ref) for ref in refs if _ref_prefix(ref) in ("R", "SA"))

    edges: dict[str, set[str]] = {}
    for source, target in (pair for block in blocks for pair in pairs(block)):
        a, b = _known_element(order, source), _known_element(order, target)
        if a and b and a != b:
            edges.setdefault(a, set()).add(b)
    return {"order": order, "edges": edges}


def _ref_prefix(ref: str) -> str:
    """要素编号的类别前缀：D6 → D，SA1 → SA，R2.3 → R。"""
    m = re.match(r"[A-Z]+", ref)
    return m.group(0) if m else ""


def _known_element(order: dict[str, int], ref: str) -> Optional[str]:
    if ref in order:
        return ref
    parent = ref.split(".", 1)[0]
    return parent if parent in order else None


def _propagate(graph: dict[str, Any], seeds: list[str], limit: int) -> tuple[list[str], bool]:
    """从 seeds 出发沿边一层层往外传，到不再新增或总数达到 limit 为止。

    返回（要素列表, 是否因上限截断）。列表先是 seeds（照原样），再是传递到的要素（按 spec 里的
    出现顺序）。按层推进，所以截断时留下的是离得近的；图里有环也只会各到一次。
    """
    order, edges = graph["order"], graph["edges"]
    seeds = list(dict.fromkeys(seeds))
    frontier = [n for n in dict.fromkeys(_known_element(order, s) for s in seeds) if n]
    visited = set(frontier)
    added: list[str] = []
    truncated = False
    while frontier and not truncated:
        following: list[str] = []
        for node in frontier:
            for target in sorted(edges.get(node, ()), key=order.__getitem__):
                if target in visited:
                    continue
                if len(seeds) + len(added) >= limit:
                    truncated = True
                    break
                visited.add(target)
                added.append(target)
                following.append(target)
            if truncated:
                break
        frontier = following
    return seeds + sorted((n for n in added if n not in seeds), key=order.__getitem__), truncated


def affected_elements(root: Path, report_id: str, requirement: dict[str, Any]) -> list[str]:
    """这条数据需求影响哪些 spec 要素。

    需求自己写的 elements，并上顺 spec 的依赖关系传递到的要素（边的来历见 _spec_graph）；
    宁多勿漏，传到不再新增为止，总数以 AFFECTED_LIMIT 为上限防失控。spec 不存在时只返回
    需求自己写的 elements。requirement 可以是 plan 里的原始条目、归一后的需求或体检结果条目。
    """
    seeds = _as_elements(requirement.get("elements"))
    graph = _spec_graph(root, report_id)
    return seeds if graph is None else _propagate(graph, seeds, AFFECTED_LIMIT)[0]


# ---------------------------------------------------------------------------
# 认文件、取实况
# ---------------------------------------------------------------------------

_SOURCE_FILE_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_][A-Za-z0-9_./-]*?\.(?:parquet|csv|feather|xlsx|xls|h5|hdf|pkl))(?![A-Za-z0-9_])"
)
_SOURCE_DIR_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])([A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*)/(?![A-Za-z0-9_])"
)
_SOURCE_WORD_RE = re.compile(r"(?<![A-Za-z0-9_.-])([A-Za-z][A-Za-z0-9_]{2,})(?![A-Za-z0-9_.])")
_ARROW_RE = re.compile(r"→|⇒|->|=>")
# 工作区自己的目录：source 里以它们开头的路径是复现过程的产物，不是数据根下的文件
_WORKSPACE_DIRS = ("output", "workspace", "src", "common", "tools", "templates", "reports", "tests", "docs")


@dataclass
class _CheckContext:
    """一次体检共用的东西：数据根、可用的目录体检条目、数据根顶层的文件名，以及本次运行内的缓存。"""

    root: Path
    data_root: Path
    probe_files: dict[str, Any]
    have_pyarrow: bool
    run_smoke: bool
    today: date
    top_files: dict[str, str] = field(default_factory=dict)  # 主干名 → 文件名（数据根顶层）
    cache: dict[Any, Any] = field(default_factory=dict)


@dataclass
class _Findings:
    """一条需求查下来的东西：问题、说明、没查成的项、各文件的实测。"""

    problems: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    measured: dict[str, Any] = field(default_factory=dict)

    def problem(self, code: str, detail: str, **evidence: Any) -> None:
        self.problems.append({"code": code, "detail": detail, "evidence": evidence})

    def skip(self, check: str, reason: str, file: str = "") -> None:
        self.skipped.append({"check": check, "file": file, "reason": reason})


def _same_path(a: Any, b: Path) -> bool:
    return isinstance(a, str) and os.path.realpath(os.path.expanduser(a)) == os.path.realpath(str(b))


def _scan_top(data_root: Path) -> dict[str, str]:
    """数据根顶层的数据文件：主干名 → 文件名（同名时 parquet 优先）。"""
    try:
        names = sorted(e.name for e in os.scandir(data_root) if e.is_file() and not e.name.startswith("."))
    except OSError:
        return {}
    found: dict[str, str] = {}
    for name in names:
        stem, suffix = Path(name).stem, Path(name).suffix.lower()
        if suffix in DATA_SUFFIXES and (stem not in found or suffix == ".parquet"):
            found[stem] = name
    return found


def _locate(ctx: _CheckContext, token: str) -> str:
    """source 里写的文件名落在数据根的哪里：原样、顶层同名、目录体检里唯一的同名文件，都找不到就原样返回。"""
    token = os.path.normpath(token).replace(os.sep, "/")
    if (ctx.data_root / token).exists():
        return token
    name = Path(token).name
    if (ctx.data_root / name).is_file():
        return name
    nested = [rel for rel in ctx.probe_files if rel.endswith("/" + name)]
    return nested[0] if len(nested) == 1 else token


def _files_from_source(ctx: _CheckContext, text: str) -> list[str]:
    """从自由文本的 source 里认数据文件（旧 plan 只有这个可查）。

    带扩展名的文件名（xxx.parquet 等）直接认，不存在就是缺文件；以 / 结尾的目录名只在目录确实
    存在时才认；一个带扩展名的文件名都没有时，再认不带扩展名的单词——只认数据根顶层确有同名
    文件的（如 `ashare_stock_trade`），所以这一类只会给出「在」的证据。写的是工作区里的产物
    路径（如 derive 类需求写的 `output/<id>/results/x.parquet`）不算数据文件，不认。
    """

    def is_workspace_path(token: str) -> bool:
        return "/" in token and token.split("/", 1)[0] in _WORKSPACE_DIRS and not (ctx.data_root / token).exists()

    named = [_locate(ctx, token) for token in _SOURCE_FILE_RE.findall(text) if not is_workspace_path(token)]
    dirs = [token for token in _SOURCE_DIR_RE.findall(text) if (ctx.data_root / token).is_dir()]
    words = [] if named else [ctx.top_files[w] for w in _SOURCE_WORD_RE.findall(text) if w in ctx.top_files]
    return list(dict.fromkeys(named + dirs + words))


def _resolve_rel(ctx: _CheckContext, raw: str) -> Optional[str]:
    """把 plan 的 files 里写的路径规整成数据根下的相对路径；落在数据根之外的返回 None（不查）。"""
    path = Path(raw).expanduser()
    if path.is_absolute():
        try:
            return Path(os.path.realpath(path)).relative_to(os.path.realpath(ctx.data_root)).as_posix()
        except ValueError:
            return None
    norm = os.path.normpath(raw).replace(os.sep, "/")
    return None if norm == ".." or norm.startswith("../") else norm


def _fresh_entry(entry: Any, path: Path) -> Optional[dict[str, Any]]:
    """目录体检缓存里的条目还能不能用：大小、修改时间没变，没有读取错误，该有逐年统计的已经有了。"""
    if not isinstance(entry, dict) or entry.get("error"):
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    if entry.get("size") != stat.st_size or entry.get("mtime_ns") != stat.st_mtime_ns:
        return None
    if "yearly" not in entry and entry.get("code_column") and entry.get("date_column") and entry.get("rows"):
        return None
    return entry


def _file_facts(ctx: _CheckContext, rel: str) -> dict[str, Any]:
    """一个 parquet 文件的实况（字段、行数、日期起止、逐年统计），形状同 probe_file 的条目。

    目录体检缓存里的条目仍然新鲜就用它，否则只现测这一个文件；现测的结果不写回缓存。
    """
    key = ("facts", rel)
    if key not in ctx.cache:
        path = ctx.data_root / rel
        entry = _fresh_entry(ctx.probe_files.get(rel), path)
        if entry is None and not ctx.have_pyarrow:
            entry = {"path": rel, "error": "未安装 pyarrow"}
        elif entry is None:
            try:
                entry = probe_file(path, ctx.data_root, yearly=True)
            except (OSError, ValueError) as exc:
                entry = {"path": rel, "error": f"{type(exc).__name__}: {exc}"[:300]}
        ctx.cache[key] = entry
    return ctx.cache[key]


def _warm_facts(ctx: _CheckContext, requirements: list[dict[str, Any]]) -> None:
    """要逐项核对而目录体检缓存里没有（或已过期）的文件，先并行现测一遍。

    现测一个大文件的逐年统计要一两秒，一份 plan 常涉及十几个；并行之后没有缓存也能在几秒内
    查完。每个文件只测一次，结果放进本次运行的缓存，后面逐条核对时直接取。
    """
    if not ctx.have_pyarrow:
        return
    listed = (
        _resolve_rel(ctx, raw)
        for req in requirements
        if req["status"] != "missing"
        for raw in req["files"]
    )
    wanted = [rel for rel in dict.fromkeys(listed) if rel and rel.lower().endswith(".parquet") and (ctx.data_root / rel).is_file()]
    todo = [rel for rel in wanted if _fresh_entry(ctx.probe_files.get(rel), ctx.data_root / rel) is None]
    if len(todo) > 1:
        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 2, len(todo))) as pool:
            list(pool.map(lambda rel: _file_facts(ctx, rel), todo))


def _date_ints(values: Any) -> Any:
    """把日期列规整成 YYYYMMDD 的整数（时间戳、日期、字符串、整数都认，时间戳丢掉时分秒）；认不出返回 None。"""
    import pyarrow as pa
    import pyarrow.compute as pc

    kind = values.type
    if pa.types.is_dictionary(kind):
        values = pc.cast(values, kind.value_type)
        kind = values.type
    if pa.types.is_timestamp(kind) or pa.types.is_date(kind):
        parts = [pc.cast(part(values), pa.int32()) for part in (pc.year, pc.month, pc.day)]
        return pc.add(pc.add(pc.multiply(parts[0], 10000), pc.multiply(parts[1], 100)), parts[2])
    if pa.types.is_string(kind) or pa.types.is_large_string(kind):
        digits = pc.replace_substring_regex(pc.utf8_slice_codeunits(values, 0, 10), r"[^0-9]", "")
        return pc.cast(pc.utf8_slice_codeunits(digits, 0, 8), pa.int32(), safe=False)
    if pa.types.is_integer(kind):
        return pc.cast(values, pa.int32(), safe=False)
    return None


def _column_span(path: Path, column: str) -> Optional[tuple[str, str]]:
    """一列的最小、最大日期：先看行组统计，没有再读这一列现算（行数太多就放弃）。"""
    try:
        import pyarrow.compute as pc
        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        names = list(pf.schema_arrow.names)
        if column not in names:
            return None
        found = _column_range(pf.metadata, names.index(column))
        if found or not 0 < pf.metadata.num_rows <= DATE_ONLY_MAX_ROWS:
            return found
        days = _date_ints(pf.read(columns=[column]).column(0))
        bounds = pc.min_max(days).as_py() if days is not None else {}
        low, high = _to_date_str(bounds.get("min")), _to_date_str(bounds.get("max"))
        return (low, high) if low and high else None
    except Exception:  # noqa: BLE001 - 读不了就当没有日期起止
        return None


def _date_axis(ctx: _CheckContext, rel: str, facts: dict[str, Any]) -> Optional[dict[str, str]]:
    """文件的日期轴 {"column", "min", "max"}；拿不到返回 None。

    用目录体检认出的日期列；没有的话认 pandas 写出的日期型索引列（如宽表 macro_cache 的
    `__index_level_0__`）。行组统计里没有起止时读这一列现算。
    """
    key = ("axis", rel)
    if key not in ctx.cache:
        index_like = (
            c["name"]
            for c in facts.get("columns") or []
            if c["name"].startswith("__index_level_") and str(c.get("type", "")).startswith(("timestamp", "date"))
        )
        column = facts.get("date_column") or next(index_like, None)
        known = (facts.get("date_ranges") or {}).get(column or "")
        span = (known["min"], known["max"]) if known else None
        if column and span is None and ctx.have_pyarrow:
            span = _column_span(ctx.data_root / rel, column)
        ctx.cache[key] = {"column": column, "min": span[0], "max": span[1]} if column and span else None
    return ctx.cache[key]


def _dates_per_year(ctx: _CheckContext, rel: str, facts: dict[str, Any], axis: Optional[dict[str, str]]) -> Optional[dict[int, int]]:
    """每年有多少个不同的日期：带代码列的表用目录体检的逐年统计，只有日期列的表读这一列现算。"""
    if facts.get("yearly"):
        return {int(y): int(v["days"]) for y, v in facts["yearly"].items()}
    key = ("per_year", rel)
    if key not in ctx.cache:
        found: Optional[dict[int, int]] = None
        if axis and ctx.have_pyarrow and 0 < (facts.get("rows") or 0) <= DATE_ONLY_MAX_ROWS:
            try:
                import pyarrow.compute as pc
                import pyarrow.parquet as pq

                days = _date_ints(pq.ParquetFile(ctx.data_root / rel).read(columns=[axis["column"]]).column(0))
                counts = pc.value_counts(pc.divide(pc.unique(days), 10000)).to_pylist() if days is not None else []
                found = {int(c["values"]): int(c["counts"]) for c in counts if c["values"] is not None} or None
            except Exception:  # noqa: BLE001 - 算不出就当不知道
                found = None
        ctx.cache[key] = found
    return ctx.cache[key]


def _grain(per_year: Optional[dict[int, int]], axis: dict[str, str]) -> Optional[str]:
    """数据自己的粒度（D/W/M/Q/A）：取最近几个完整年份每年日期数的中位数，口径同 _typical_days。

    首尾两年可能不完整，不算；早年稀疏的表（如只有零星几天的历史段）不会把粒度拉低。没有中间
    年份返回 None。
    """
    first, last = int(axis["min"][:4]), int(axis["max"][:4])
    inner = [n for _year, n in sorted((per_year or {}).items()) if first < _year < last]
    if not inner:
        return None
    typical = median(inner[-5:])
    return next((f for f in FREQS if typical >= FREQ_MIN_DATES[f]), "A")


def _collapsed_years(yearly: dict[str, dict[str, int]], this_year: int) -> list[int]:
    """目录体检判为截面塌陷的年份，口径同 yearly_flags 的 sparse_years：标的数不到峰值的一成，且与相邻的正常年份相差 5 倍以上。"""
    if not any(f["code"] == "sparse_years" for f in yearly_flags(yearly, this_year)):
        return []
    codes = {int(y): v["codes"] for y, v in yearly.items() if int(y) <= this_year}
    peak = max(codes.values())
    return sorted(y for y, n in codes.items() if n < peak * SPARSE_RATIO)


def _is_financial(rel: str, facts: dict[str, Any], requirement_name: str) -> bool:
    """这个文件算不算「财务类」（财务类数据必须有披露日列才能做时点对齐）。

    认定方式：文件带报告期列（end_date / report_date / report_period），并且满足其一——
    - 文件名按下划线拆开后含 balance / income / cashflow / financial / finance / fina 之一
      （如 ashare_stock_income_q、hkshare_stock_balance）；
    - 需求名称里有「财务、财报、利润表、资产负债、现金流量」之一。
    两头都要：只看文件名会把 bond_cashflow（债券现金流）、financial_future_price（金融期货行情）
    这类按交易日记的表算进来；只看报告期列会把指标字典、预测统计这类也带 end_date 的表算进来。
    """
    columns = {c["name"] for c in facts.get("columns") or []}
    if not columns & set(REPORT_PERIOD_COLUMNS):
        return False
    named_like_statement = bool(set(re.split(r"[^a-z0-9]+", Path(rel).stem.lower())) & set(FINANCIAL_FILE_TOKENS))
    return named_like_statement or any(k in requirement_name for k in FINANCIAL_NAME_KEYWORDS)


# ---------------------------------------------------------------------------
# 要读数据的检查：只读需要的列，行数有上限
# ---------------------------------------------------------------------------


def _sample_groups(sizes: list[int], max_rows: int, prefer_tail: bool) -> list[int]:
    """从一串行组里挑一部分，合计行数尽量不超过 max_rows，返回挑中的位置（升序）。

    prefer_tail 时先取最后两组（重复追加的数据落在文件末尾），其余按位置均匀取。
    """
    n = len(sizes)
    if sum(sizes) <= max_rows:
        return list(range(n))
    k = max(1, int(max_rows // max(sum(sizes) / n, 1)))
    spread = [min(n - 1, int((i + 0.5) * n / k)) for i in range(k)]
    order = list(dict.fromkeys(([n - 1, n - 2] if prefer_tail and n >= 2 else []) + spread))
    picked: list[int] = []
    rows = 0
    for pos in order:
        if picked and rows + sizes[pos] > max_rows:
            continue
        picked.append(pos)
        rows += sizes[pos]
    return sorted(picked)


def _read_rows(
    path: Path,
    columns: list[str],
    axis_column: Optional[str],
    start: Optional[str],
    end: Optional[str],
    prefer_tail: bool = False,
) -> dict[str, Any]:
    """读若干列，最多 SAMPLE_ROWS 行，返回 {"table", "sampled", "scoped"}。

    给了所需区间和日期列时，先用行组统计留下与区间有交集的行组，读出来再按行过滤（scoped=True）；
    行数超过上限就只读其中一部分行组（sampled=True）。读不了抛异常，由调用方记为未检。
    """
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(path)
    meta = pf.metadata
    names = list(pf.schema_arrow.names)
    scoped = bool(axis_column and axis_column in names and (start or end))
    groups = list(range(meta.num_row_groups))
    if scoped:
        index = names.index(axis_column)

        def overlaps(g: int) -> bool:
            stats = meta.row_group(g).column(index).statistics
            if stats is None or not stats.has_min_max:
                return True
            low, high = _to_date_str(stats.min), _to_date_str(stats.max)
            if low is None or high is None:
                return True
            return not ((end and low > end) or (start and high < start))

        groups = [g for g in groups if overlaps(g)]
    sizes = [meta.row_group(g).num_rows for g in groups]
    picked = [groups[i] for i in _sample_groups(sizes, SAMPLE_ROWS, prefer_tail)] if groups else []
    wanted = list(dict.fromkeys(columns + ([axis_column] if scoped else [])))
    batches: list[Any] = []
    rows = 0
    if picked:
        for batch in pf.iter_batches(batch_size=min(262_144, SAMPLE_ROWS), row_groups=picked, columns=wanted):
            batches.append(batch)
            rows += batch.num_rows
            if rows >= SAMPLE_ROWS:
                break
    table = pa.Table.from_batches(batches) if batches else pf.schema_arrow.empty_table().select(wanted)
    sampled = len(picked) < len(groups) or rows < sum(meta.row_group(g).num_rows for g in picked)
    if scoped and table.num_rows:
        days = _date_ints(table.column(axis_column))
        bounds = [(start, pc.greater_equal), (end, pc.less_equal)]
        masks = [compare(days, int(bound.replace("-", ""))) for bound, compare in bounds if bound and days is not None]
        if masks:
            table = table.filter(masks[0] if len(masks) == 1 else pc.and_(masks[0], masks[1]))
        scoped = bool(masks)
    return {"table": table, "sampled": sampled, "scoped": scoped}


def _plain(value: Any) -> Any:
    """把读出来的值变成能进 JSON、人也看得懂的样子。"""
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)


def _dup_check(path: Path, keys: list[str], axis_column: Optional[str], start: Optional[str], end: Optional[str]) -> dict[str, Any]:
    """按给定的主键列查重（键里有空值的行不参与）。返回行数、重复的键数、多出来的行数和几个例子。"""
    import pyarrow as pa
    import pyarrow.compute as pc

    data = _read_rows(path, keys, axis_column, start, end, prefer_tail=True)
    table = data["table"].select(keys).drop_null()
    found = {"rows": table.num_rows, "dup_keys": 0, "extra_rows": 0, "examples": [], "sampled": data["sampled"], "scoped": data["scoped"]}
    if not table.num_rows:
        return found

    def hashable(name: str) -> Any:
        column = table.column(name)
        if pa.types.is_dictionary(column.type):
            column = column.cast(column.type.value_type)
        column = column.combine_chunks()
        # 大字符串列直接分组很慢（百万行要一两秒），先编成字典再分组
        return column.dictionary_encode() if pa.types.is_string(column.type) or pa.types.is_large_string(column.type) else column

    grouped = pa.table({name: hashable(name) for name in keys}).group_by(keys).aggregate([([], "count_all")])
    repeated = grouped.filter(pc.greater(grouped.column("count_all"), 1))
    found.update(
        dup_keys=repeated.num_rows,
        extra_rows=table.num_rows - grouped.num_rows,
        examples=[[_plain(row[name]) for name in keys] for row in repeated.slice(0, 3).to_pylist()],
    )
    return found


def _null_check(path: Path, fields: list[str], axis_column: Optional[str], start: Optional[str], end: Optional[str]) -> dict[str, Any]:
    """关键字段的缺失率（浮点列的 NaN 也算缺失）。返回行数与各字段的缺失率。"""
    import pyarrow as pa
    import pyarrow.compute as pc

    data = _read_rows(path, fields, axis_column, start, end)
    table = data["table"]
    rows = table.num_rows

    def rate(name: str) -> float:
        column = table.column(name)
        missing = pc.sum(pc.is_null(column, nan_is_null=pa.types.is_floating(column.type))).as_py() or 0
        return round(missing / rows, 4)

    return {"rows": rows, "rates": {name: rate(name) for name in fields} if rows else {}, "sampled": data["sampled"], "scoped": data["scoped"]}


def _run_smoke(root: Path, command: str) -> dict[str, Any]:
    """执行一条取数冒烟调用（在工作区根目录下跑，有时限）。退出码为 0 算通。"""
    started = time.time()
    try:
        proc = subprocess.run(
            command, shell=True, cwd=str(root), capture_output=True, text=True, errors="replace", timeout=SMOKE_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "why": f"超过 {SMOKE_TIMEOUT} 秒没有返回", "returncode": None, "seconds": round(time.time() - started, 1), "output_tail": ""}
    except OSError as exc:
        return {"ok": False, "why": f"命令起不来：{exc}", "returncode": None, "seconds": round(time.time() - started, 1), "output_tail": ""}
    tail = (proc.stderr or proc.stdout or "").strip()[-300:]
    return {
        "ok": proc.returncode == 0,
        "why": "" if proc.returncode == 0 else f"退出码 {proc.returncode}",
        "returncode": proc.returncode,
        "seconds": round(time.time() - started, 1),
        "output_tail": tail,
    }


# ---------------------------------------------------------------------------
# 逐项核对（每项只往 _Findings 里记，不抛异常）
# ---------------------------------------------------------------------------


def _expand_fields(fields: list[str]) -> list[str]:
    """`OHLC` 展开成 open / high / low / close（data_catalog 里的惯用简写）。"""
    return list(dict.fromkeys(name for f in fields for name in (["open", "high", "low", "close"] if f == "OHLC" else [f])))


def _gap_days(earlier: str, later: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def _shift_day(day: str, days: int) -> str:
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


def _in_period(year: int, start: Optional[str], end: Optional[str]) -> bool:
    return (not start or year >= int(start[:4])) and (not end or year <= int(end[:4]))


def _span_text(counts: Iterable[int]) -> str:
    low, high = min(counts), max(counts)
    return str(low) if low == high else f"{low}–{high}"


def _check_fields(req: dict[str, Any], facts: dict[str, dict[str, Any]], readable: list[str], unread: list[str], out: _Findings) -> None:
    """字段齐不齐：每个要的字段至少在所列文件之一里有（一条需求常由几张表拼起来）。"""
    union = list(dict.fromkeys(c["name"] for rel in readable for c in facts[rel].get("columns") or []))
    missing = [f for f in _expand_fields(req["fields"]) if f not in union]
    if not missing:
        return
    if unread:
        out.skip("fields", f"字段 {', '.join(missing)} 在读得了的文件里没有，但还有没读到表头的文件：{'、'.join(unread)}")
        return
    lowered = {name.lower(): name for name in union}
    similar = {f: [lowered[f.lower()]] if f.lower() in lowered else difflib.get_close_matches(f, union, n=2, cutoff=0.6) for f in missing}
    similar = {f: names for f, names in similar.items() if names}
    hint = "；相近的列：" + "、".join(f"{f} → {' / '.join(names)}" for f, names in similar.items()) if similar else ""
    where = "、".join(f"`{rel}`" for rel in readable)
    out.problem(
        "field_missing",
        f"{where} 里没有字段 {', '.join(missing)}{hint}",
        file=readable[0] if len(readable) == 1 else "",
        files=readable,
        missing=missing,
        similar=similar,
    )


def _check_freq(
    rel: str,
    axis: Optional[dict[str, str]],
    per_year: Optional[dict[int, int]],
    start: Optional[str],
    end: Optional[str],
    freq: str,
    out: _Findings,
) -> bool:
    """频率够不够：所需区间内中间年份每年日期数的中位数，达不到所标频率的下限（FREQ_MIN_DATES）即报。

    数据比所标的更细（要月频、给日频）不算问题。返回是否报了问题。
    """
    if not axis or not per_year:
        out.skip("freq", "没有认得出的日期列，或算不出每年的日期数", rel)
        return False
    first, last = int(axis["min"][:4]), int(axis["max"][:4])
    years = [y for y in sorted(per_year) if first < y < last and _in_period(y, start, end)]
    if not years:
        out.skip("freq", "所需区间内没有完整的年份，频率没法判定", rel)
        return False
    typical = median(per_year[y] for y in years)
    if typical >= FREQ_MIN_DATES[freq]:
        return False
    seen = next((f for f in FREQS if typical >= FREQ_MIN_DATES[f]), "A")
    out.problem(
        "freq_mismatch",
        f"`{rel}` 要求{FREQ_CN[freq]}频，实测 {years[0]}–{years[-1]} 年每年约 {typical:g} 个日期（像{FREQ_CN[seen]}频）",
        file=rel,
        required=freq,
        measured=seen,
        dates_per_year=typical,
        years=[years[0], years[-1]],
    )
    return True


def _check_period(
    rel: str,
    axis: Optional[dict[str, str]],
    per_year: Optional[dict[int, int]],
    start: Optional[str],
    end: Optional[str],
    freq: Optional[str],
    freq_bad: bool,
    out: _Findings,
) -> None:
    """区间盖不盖得住，写明缺哪一段。

    - 头、尾：实测起止与所需起止的出入超过容许值（PERIOD_TOLERANCE_DAYS，按数据自己的粒度取）；
    - 中间整年没有数据；
    - plan 标了频率时，中间某年的日期数不到该频率下限的六成（SHORT_YEAR_RATIO），记为稀疏年份。
    """
    if not (start or end):
        return
    if not axis:
        out.skip("period", "没有认得出的日期列，区间没法核对", rel)
        return
    low, high = axis["min"], axis["max"]
    tolerance = PERIOD_TOLERANCE_DAYS[_grain(per_year, axis) or freq or "M"]
    if (start and high < start) or (end and low > end):
        segments = [[start or low, end or high]]  # 实测区间与所需区间完全不相交
    else:
        head = [[start, _shift_day(low, -1)]] if start and _gap_days(start, low) > tolerance else []
        tail = [[_shift_day(high, 1), end]] if end and _gap_days(high, end) > tolerance else []
        segments = head + tail
    inner = [y for y in range(int(low[:4]) + 1, int(high[:4])) if _in_period(y, start, end)] if per_year else []
    missing_years = [y for y in inner if not per_year.get(y)]
    floor = FREQ_MIN_DATES[freq] * SHORT_YEAR_RATIO if freq and not freq_bad else 0
    thin = {y: per_year[y] for y in inner if 0 < per_year.get(y, 0) < floor}
    if not (segments or missing_years or thin):
        return
    parts = (
        (["缺 " + "、".join(f"{a} ~ {b}" for a, b in segments)] if segments else [])
        + ([f"{_ranges(missing_years)} 年整年没有数据"] if missing_years else [])
        + (
            [f"{_ranges(list(thin))} 年每年只有 {_span_text(thin.values())} 个日期（{FREQ_CN[freq]}频每年通常不少于 {FREQ_MIN_DATES[freq]} 个）"]
            if thin
            else []
        )
    )
    out.problem(
        "period_short",
        f"`{rel}` 的 {axis['column']} 列实测 {low} ~ {high}，要求 {start or '不限'} ~ {end or '不限'}：" + "；".join(parts),
        file=rel,
        date_column=axis["column"],
        required=[start, end],
        measured=[low, high],
        missing=segments,
        missing_years=missing_years,
        thin_years={str(y): n for y, n in thin.items()},
    )


def _check_cross_section(
    rel: str,
    facts: dict[str, Any],
    start: Optional[str],
    end: Optional[str],
    min_codes: Optional[int],
    this_year: int,
    out: _Findings,
) -> None:
    """每年标的数有没有塌陷，只看所需区间内有数据的年份（整年没有数据归 period_short）。

    - 写了 min_codes：标的数低于它的年份即报；
    - 没写 min_codes：报目录体检判为塌陷的年份（不到峰值一成且有 5 倍以上的断崖，见 yearly_flags）。
    """
    yearly = facts.get("yearly")
    if not yearly:
        if min_codes is not None:
            out.skip("min_codes", "这张表没有代码列和日期列，算不出每年的标的数", rel)
        return
    codes = {int(y): int(v["codes"]) for y, v in yearly.items() if int(y) <= this_year}
    collapsed = set(_collapsed_years(yearly, this_year)) if min_codes is None else set()

    def deficient(year: int) -> bool:
        return codes[year] < min_codes if min_codes is not None else year in collapsed

    scope = [y for y in sorted(codes) if _in_period(y, start, end)]
    bad = [y for y in scope if deficient(y)]
    if not bad:
        return
    after = next((y for y in sorted(codes) if y > bad[-1] and not deficient(y)), None)
    peak_year = max(codes, key=codes.get)
    then = f"，{after} 年起有 {codes[after]} 个" if after is not None else ""
    need = f"；要求每年不少于 {min_codes} 个" if min_codes is not None else f"；不到峰值（{peak_year} 年 {codes[peak_year]} 个）的一成"
    out.problem(
        "cross_section_collapse",
        f"`{rel}` {_ranges(bad)} 年每年只有 {_span_text([codes[y] for y in bad])} 个标的{then}{need}",
        file=rel,
        code_column=facts.get("code_column"),
        yearly_codes={str(y): codes[y] for y in scope},
        deficient_years=bad,
        min_codes=min_codes,
        first_ok_after=({"year": after, "codes": codes[after]} if after is not None else None),
        peak={"year": peak_year, "codes": codes[peak_year]},
    )


def _check_publ_date(financial: list[str], facts: dict[str, dict[str, Any]], readable: list[str], out: _Findings) -> None:
    """财务类数据有没有披露日列（按一条需求整体看：所列文件里只要有一张带披露日列，就能对齐）。"""
    if not financial:
        return
    with_publ = [rel for rel in readable if facts[rel].get("publ_date_column")]
    lacking = [rel for rel in financial if not facts[rel].get("publ_date_column")]
    if not with_publ:
        out.problem(
            "no_publ_date",
            "财务类数据 " + "、".join(f"`{rel}`" for rel in financial) + f" 没有披露日列（{' / '.join(PUBL_DATE_COLUMNS)}），没法按披露日做时点对齐",
            file=financial[0] if len(financial) == 1 else "",
            files=financial,
            expected=list(PUBL_DATE_COLUMNS),
        )
    elif lacking:
        out.notes.append(f"{'、'.join(lacking)} 没有披露日列，披露日要从同一条需求里的 {'、'.join(with_publ)} 对齐")


def _check_dup(
    ctx: _CheckContext,
    req: dict[str, Any],
    rel: str,
    facts: dict[str, Any],
    axis: Optional[dict[str, str]],
    start: Optional[str],
    end: Optional[str],
    financial: bool,
    out: _Findings,
) -> None:
    """主键重复。

    - plan 写了 keys：按它查，有重复即报（只查含全部主键列的文件；keys 为空表示不查）；
    - 没写 keys：有日期列的表按（代码列, 日期列）查，没有代码列就只按日期列。多出来的行占比超过
      DUP_NOT_KEY_RATE 时，说明这组列不是这张表的主键（如持仓表、分档预测表），不判、只记一笔；
      财务类表和以报告期、披露日为日期列的表同一键可以有多行，默认不查。
    只看所需区间内的行；大文件抽查 SAMPLE_ROWS 行（优先取文件末尾）。
    """
    explicit = req["keys"] is not None
    columns = {c["name"] for c in facts.get("columns") or []}
    if explicit:
        keys = req["keys"]
        if not keys or not set(keys) <= columns:
            return
    else:
        day = axis["column"] if axis else None
        if not day:
            return
        if financial or day in REPORT_PERIOD_COLUMNS or day in PUBL_DATE_COLUMNS:
            out.skip("dup_keys", "财务类、按报告期或披露日记的表同一键可以有多行，默认不查重；要查请在 keys 里写明主键", rel)
            return
        keys = [c for c in (facts.get("code_column"), day) if c]
    if not ctx.have_pyarrow:
        out.skip("dup_keys", "未安装 pyarrow", rel)
        return
    key = ("dup", rel, tuple(keys), start, end)
    if key not in ctx.cache:
        try:
            ctx.cache[key] = _dup_check(ctx.data_root / rel, keys, axis["column"] if axis else None, start, end)
        except Exception as exc:  # noqa: BLE001 - 读不了记为未检
            ctx.cache[key] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    found = ctx.cache[key]
    if found.get("error"):
        out.skip("dup_keys", f"读不了：{found['error']}", rel)
        return
    if not found["extra_rows"]:
        return
    rate = found["extra_rows"] / found["rows"]
    label = ", ".join(keys)
    if not explicit and rate > DUP_NOT_KEY_RATE:
        out.skip("dup_keys", f"按（{label}）查，多出来的行占 {rate:.0%}，看来它不是这张表的主键，没有判定；要查请在 keys 里写明主键", rel)
        return
    how = ("抽查" if found["sampled"] else "核对") + ("所需区间内 " if found["scoped"] else " ")
    examples = "，如 " + "、".join("(" + ", ".join(str(v) for v in example) + ")" for example in found["examples"]) if found["examples"] else ""
    whose = " plan 写的主键" if explicit else "默认主键"
    advice = "" if explicit else "。默认主键是按列名猜的：这张表若本来就一键多行，在 keys 里写明主键（写 [] 表示不查）"
    out.problem(
        "dup_keys",
        f"`{rel}` 按{whose}（{label}）{how}{found['rows']} 行，有 {found['dup_keys']} 个键重复、多出 {found['extra_rows']} 行{examples}{advice}",
        file=rel,
        keys=keys,
        keys_from="plan" if explicit else "default",
        rows=found["rows"],
        dup_keys=found["dup_keys"],
        extra_rows=found["extra_rows"],
        examples=found["examples"],
        sampled=found["sampled"],
        scoped=found["scoped"],
    )


def _check_nulls(
    ctx: _CheckContext,
    req: dict[str, Any],
    rel: str,
    facts: dict[str, Any],
    axis: Optional[dict[str, str]],
    start: Optional[str],
    end: Optional[str],
    out: _Findings,
) -> None:
    """关键字段（plan 的 fields 里、这个文件有的那些）的缺失率，超过上限即报。

    只看所需区间内的行；浮点列的 NaN 也算缺失；大文件抽查 SAMPLE_ROWS 行。
    """
    columns = {c["name"] for c in facts.get("columns") or []}
    fields = [f for f in _expand_fields(req["fields"]) if f in columns]
    if not fields:
        return
    if not ctx.have_pyarrow:
        out.skip("null_rate", "未安装 pyarrow", rel)
        return
    key = ("nulls", rel, tuple(fields), start, end)
    if key not in ctx.cache:
        try:
            ctx.cache[key] = _null_check(ctx.data_root / rel, fields, axis["column"] if axis else None, start, end)
        except Exception as exc:  # noqa: BLE001 - 读不了记为未检
            ctx.cache[key] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    found = ctx.cache[key]
    if found.get("error"):
        out.skip("null_rate", f"读不了：{found['error']}", rel)
        return
    limit = req["max_null_rate"] if req["max_null_rate"] is not None else NULL_RATE_LIMIT
    high = {name: rate for name, rate in found["rates"].items() if rate > limit}
    if not high:
        return
    scope = ("所需区间内" if found["scoped"] else "全文件") + ("（抽查）" if found["sampled"] else "")
    out.problem(
        "null_rate",
        f"`{rel}` {scope}关键字段缺失率过高：" + "、".join(f"{name} {rate:.1%}" for name, rate in high.items()) + f"（上限 {limit:.0%}）",
        file=rel,
        fields=sorted(high),
        rates=high,
        limit=limit,
        rows=found["rows"],
        sampled=found["sampled"],
        scoped=found["scoped"],
    )


def _measured(facts: dict[str, Any], axis: Optional[dict[str, str]], per_year: Optional[dict[int, int]]) -> dict[str, Any]:
    """一个文件的实测摘要（退回 planner 时带上）。"""
    codes = [v["codes"] for v in (facts.get("yearly") or {}).values()]
    pairs = {
        "rows": facts.get("rows"),
        "date_column": axis["column"] if axis else None,
        "date_range": [axis["min"], axis["max"]] if axis else None,
        "freq": _grain(per_year, axis) if axis else None,
        "code_column": facts.get("code_column"),
        "codes_per_year": [min(codes), max(codes)] if codes else None,
        "publ_date_column": facts.get("publ_date_column"),
    }
    return {k: v for k, v in pairs.items() if v is not None}


def _check_in_depth(ctx: _CheckContext, req: dict[str, Any], present: list[str], out: _Findings) -> list[str]:
    """对存在的文件逐项核对；返回存在但读不了的文件。"""
    parquet = [rel for rel in present if rel.lower().endswith(".parquet") and (ctx.data_root / rel).is_file()]
    others = [rel for rel in present if rel not in parquet]
    if others:
        out.notes.append("目录和非 parquet 文件只查了在不在：" + "、".join(others))
    facts = {rel: _file_facts(ctx, rel) for rel in parquet}
    broken = [rel for rel in parquet if facts[rel].get("error")]
    if broken and not ctx.have_pyarrow:
        out.skip("内容核对", "未安装 pyarrow，只查了文件在不在", "、".join(broken))
        broken_for_real: list[str] = []
    else:
        broken_for_real = broken
        for rel in broken:
            out.problem("file_unreadable", f"`{rel}` 存在但读不了：{facts[rel]['error']}", file=rel, error=facts[rel]["error"])
    readable = [rel for rel in parquet if rel not in broken]
    if not readable:
        return broken_for_real

    start, end = req["period"] or (None, None)
    today = ctx.today.isoformat()
    if start and start > today:
        out.notes.append(f"所需区间从 {start} 才开始，还没到，区间类检查没有做")
        start = end = None
    elif end:
        end = min(end, today)  # 今天之后的数据谁也没有，不算缺

    if req["fields"]:
        _check_fields(req, facts, readable, others + broken, out)
    financial = [rel for rel in readable if _is_financial(rel, facts[rel], req["name"])]
    for rel in readable:
        axis = _date_axis(ctx, rel, facts[rel])
        per_year = _dates_per_year(ctx, rel, facts[rel], axis)
        out.measured[rel] = _measured(facts[rel], axis, per_year)
        freq_bad = bool(req["freq"]) and _check_freq(rel, axis, per_year, start, end, req["freq"], out)
        _check_period(rel, axis, per_year, start, end, req["freq"], freq_bad, out)
        _check_cross_section(rel, facts[rel], start, end, req["min_codes"], ctx.today.year, out)
        _check_dup(ctx, req, rel, facts[rel], axis, start, end, rel in financial, out)
        _check_nulls(ctx, req, rel, facts[rel], axis, start, end, out)
    _check_publ_date(financial, facts, readable, out)

    keys = req["keys"] or []
    if keys and not any(set(keys) <= {c["name"] for c in facts[rel].get("columns") or []} for rel in readable):
        union = {c["name"] for rel in readable for c in facts[rel].get("columns") or []}
        absent = [k for k in keys if k not in union] or keys
        out.problem(
            "field_missing",
            "、".join(f"`{rel}`" for rel in readable) + f" 里没有一张表同时有 keys 写的主键列（{', '.join(keys)}）；找不到的列：{', '.join(absent)}",
            file=readable[0] if len(readable) == 1 else "",
            files=readable,
            missing=absent,
            similar={},
        )
    return broken_for_real


def _check_smoke(ctx: _CheckContext, req: dict[str, Any], out: _Findings) -> Optional[bool]:
    """处理 plan 里写的取数冒烟调用。返回 True=跑通，False=失败，None=没有或没执行。"""
    command = req["probe"]
    if not command:
        return None
    if not ctx.run_smoke:
        out.problem("smoke_not_run", "写了取数冒烟调用，这次体检没有开启执行（run_smoke）", command=command)
        return None
    ran = _run_smoke(ctx.root, command)
    if ran["ok"]:
        out.notes.append(f"取数冒烟调用跑通（{ran['seconds']} 秒）")
        return True
    out.problem(
        "smoke_failed",
        f"取数冒烟调用没有跑通：{ran['why']}",
        command=command,
        returncode=ran["returncode"],
        seconds=ran["seconds"],
        output_tail=ran["output_tail"],
    )
    return False


def _legacy_hints(ctx: _CheckContext, files: list[str]) -> list[str]:
    """只查了文件在不在的需求：目录体检缓存对这些文件有提示（截面塌陷、整年缺数据）就带上，不计入结论。"""

    def details(rel: str) -> list[str]:
        entry = _fresh_entry(ctx.probe_files.get(rel), ctx.data_root / rel) or {}
        return [f["detail"] for f in entry.get("flags") or [] if f.get("code") in ("sparse_years", "year_gap")]

    return [f"`{rel}`：{detail}" for rel in files for detail in details(rel)]


def _problem_signature(problem: dict[str, Any]) -> list[Any]:
    """一个问题里不随日常数据更新而变的部分（哪个文件、缺哪些年、哪些字段），用来判断缺口变没变。"""
    code, evidence = problem.get("code"), problem.get("evidence") or {}
    base: list[Any] = [code, evidence.get("file") or ""]
    if code == "field_missing":
        return base + [sorted(evidence.get("missing") or [])]
    if code == "period_short":
        years = {y for a, b in evidence.get("missing") or [] for y in range(int(a[:4]), int(b[:4]) + 1)}
        years |= set(evidence.get("missing_years") or []) | {int(y) for y in evidence.get("thin_years") or {}}
        return base + [sorted(years)]
    if code == "cross_section_collapse":
        return base + [sorted(evidence.get("deficient_years") or [])]
    if code == "null_rate":
        return base + [sorted(evidence.get("fields") or [])]
    if code == "dup_keys":
        return base + [list(evidence.get("keys") or [])]
    if code == "freq_mismatch":
        return base + [evidence.get("required")]
    return base


def _gap_key(entry: dict[str, Any]) -> Optional[str]:
    """缺口指纹：结论加各问题的稳定部分。不是缺口返回 None。

    指纹只到「哪个文件、哪些年份、哪些字段」这一层：数据逐日追加、缺失率小幅波动都不会让它变；
    缺的年份或字段变了、问题多了少了、结论变了才会变。
    """
    if entry.get("result") not in GAP_RESULTS:
        return None
    signatures = sorted(
        json.dumps(_problem_signature(p), ensure_ascii=False, sort_keys=True)
        for p in entry.get("problems") or []
        if p.get("code") not in UNCHECKED_CODES
    )
    return ms.slice_hash(json.dumps([entry.get("result"), signatures], ensure_ascii=False))


def _conclude(status: str, files: list[str], absent: list[str], problems: list[dict[str, Any]], checked: bool) -> str:
    """四种结论：ok 通过、partial 部分满足、missing 缺失、unchecked 未机检。"""
    if status == "missing":
        return "missing"
    real = [p for p in problems if p["code"] not in UNCHECKED_CODES]
    if not real:
        return "ok" if checked else "unchecked"
    if files and set(files) <= set(absent):
        return "missing"  # 列出的文件一个都用不了
    if not files and {p["code"] for p in real} == {"smoke_failed"}:
        return "missing"  # 非文件来源，取数调用不通
    return "partial"


def _make_entry(
    req: dict[str, Any],
    graph: Optional[dict[str, Any]],
    files: list[str],
    result: str,
    out: _Findings,
    checked: bool,
    hints: list[str],
) -> dict[str, Any]:
    """把一条需求查下来的东西装成体检结果里的条目。"""
    status = req["status"]
    affected, truncated = (req["elements"], False) if graph is None else _propagate(graph, req["elements"], AFFECTED_LIMIT)
    entry: dict[str, Any] = {
        "name": req["name"],
        "status_plan": status,
        "core": req["core"],
        "source": req["source"][:300],
        "files": files,
        "elements": req["elements"],
        "affected_elements": affected,
        "affected_truncated": truncated,
        "result": result,
        "problems": out.problems,
        "machine_checked": checked,
        # plan 标了 substitute 且替代数据没查出问题：看板显示「已替代」
        "substituted": status == "substitute" and result in ("ok", "unchecked"),
        # plan 没把它当缺口（标的是 available / derive 等）而体检不过：要带实测结果退回 planner
        "plan_mismatch": status not in ("missing", "substitute") and result in GAP_RESULTS,
        "notes": out.notes,
        "skipped": out.skipped,
        "hints": hints,
        "measured": out.measured,
    }
    entry["gap_key"] = _gap_key(entry)
    entry["disposition"] = None
    return entry


def _declare_missing(req: dict[str, Any], out: _Findings) -> None:
    out.problem("declared_missing", "plan 已标 missing" + (f"：{req['source']}" if req["source"] else ""), source=req["source"])


def _check_requirement(ctx: _CheckContext, req: dict[str, Any], graph: Optional[dict[str, Any]]) -> dict[str, Any]:
    """核对一条数据需求，返回体检结果里的一个条目。

    核对过程中出了没料到的错，这一条记为未机检并写明原因（plan 标 missing 的仍是 missing），
    不抛异常，也不连累其他需求。
    """
    try:
        return _examine_requirement(ctx, req, graph)
    except Exception as exc:  # noqa: BLE001 - 一条需求出错不该让整次体检失败
        out = _Findings()
        declared = req["status"] == "missing"
        if declared:
            _declare_missing(req, out)
        out.problem("not_machine_checkable", f"核对这条需求时出错，没有查成：{type(exc).__name__}: {exc}"[:300], source=req["source"])
        return _make_entry(req, None, [], "missing" if declared else "unchecked", out, False, [])


def _examine_requirement(ctx: _CheckContext, req: dict[str, Any], graph: Optional[dict[str, Any]]) -> dict[str, Any]:
    out = _Findings()
    status = req["status"]
    files: list[str] = []
    absent: list[str] = []
    hints: list[str] = []
    checked = False
    if req["invalid"]:
        out.notes.append("这些字段的写法认不出，没有核对：" + "、".join(req["invalid"]))

    if status == "missing":
        # plan 自己标的已知缺口：不再查文件，直接等处置
        _declare_missing(req, out)
    else:
        in_depth = bool(req["files"])
        if in_depth:
            resolved = {raw: _resolve_rel(ctx, raw) for raw in req["files"]}
            outside = [raw for raw, rel in resolved.items() if rel is None]
            if outside:
                out.notes.append("files 要写数据根目录下的相对路径，这些没有查：" + "、".join(outside))
            files = list(dict.fromkeys(rel for rel in resolved.values() if rel))
        else:
            # 「原文 X → 替代 Y」只看替代的一侧
            text = _ARROW_RE.split(req["source"])[-1] if status == "substitute" else req["source"]
            files = _files_from_source(ctx, text)
        present = [rel for rel in files if (ctx.data_root / rel).exists()]
        absent = [rel for rel in files if rel not in present]
        for rel in absent:
            near = difflib.get_close_matches(Path(rel).name, sorted(ctx.top_files.values()), n=2, cutoff=0.75)
            out.problem("file_missing", f"数据根目录下没有 `{rel}`" + ("；相近的文件名：" + "、".join(near) if near else ""), file=rel, similar=near)
        checked = bool(files)
        if in_depth:
            absent = absent + _check_in_depth(ctx, req, present, out)
        else:
            if files and not req["legacy"]:
                out.notes.append("没有填 files，只按 source 里认出的文件名查了在不在，fields / period 等没有核对")
            hints = _legacy_hints(ctx, present)
        checked = (_check_smoke(ctx, req, out) is not None) or checked
        if not files and not req["probe"]:
            why = "files 里写的路径都不在数据根目录下" if req["files"] else "source 里认不出数据文件，也没有写冒烟调用（probe）"
            out.problem("not_machine_checkable", why, source=req["source"])

    result = _conclude(status, files, absent, out.problems, checked)
    return _make_entry(req, graph, files, result, out, checked, hints)


# ---------------------------------------------------------------------------
# 对外接口：体检、存取、处置、缺口清单
# ---------------------------------------------------------------------------


def _summarize(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(e.get("result") for e in entries)
    gaps = [e for e in entries if e.get("result") in GAP_RESULTS]
    return {
        "total": len(entries),
        **{name: counts.get(name, 0) for name in RESULTS},
        "gaps": len(gaps),
        "open_gaps": sum(1 for e in gaps if not e.get("disposition")),
        "substituted": sum(1 for e in entries if e.get("substituted")),
    }


def check_requirements(
    root: Path,
    report_id: str,
    *,
    probe: Optional[dict[str, Any]] = None,
    data_root: Optional[Path] = None,
    run_smoke: bool = False,
) -> dict[str, Any]:
    """逐条核对 plan 的数据需求，返回体检结果（不写文件；写盘用 save_check）。

    probe 不给时用 load_probe() 读目录体检缓存；缓存没有、过期或数据根对不上时，只对涉及的文件
    现测（并行，每个文件一次），不扫全目录，也不写缓存。run_smoke=True 才执行 plan 里 `probe`
    字段的冒烟命令，默认不执行，记为未机检并注明原因。

    口径：
    - plan 标 missing 的需求是已知缺口，result 记 missing，等人处置；
    - plan 标 substitute 的按替代数据查（source 写成「原文 X → 替代 Y」时只看 Y 一侧），没查出问题
      就在条目里标 substituted=true（看板显示「已替代」），替代数据自身有问题照常报；
    - derive / available 等其余状态，按列出的源文件查；
    - 没写 files 的需求（旧 plan）只查文件在不在：从 source 里认得出文件名的查存在，认不出的记
      unchecked；目录体检缓存对这些文件有提示时放进 hints，不计入结论；
    - 写了 files 的逐项核对：字段、区间、每年标的数、频率、主键重复、关键字段缺失率、财务类数据
      的披露日列。读不了的项记进 skipped 并说明，不抛异常；
    - 没装 pyarrow 时只查文件在不在（缓存里已有的实测照用），结果的 notes 里注明。

    每个条目另带 gap_key（缺口指纹）、plan_mismatch（plan 没当它是缺口而体检不过）、measured
    （各文件的实测摘要）。返回值的形状见设计文档 4.5 节与本模块的测试。
    """
    started = time.time()
    data_root = Path(os.path.abspath(Path(data_root or resolve_data_root(root)).expanduser()))
    probe = probe if probe is not None else load_probe(root)
    usable = isinstance(probe, dict) and probe.get("version") == PROBE_VERSION and _same_path(probe.get("data_root"), data_root)
    ctx = _CheckContext(
        root=root,
        data_root=data_root,
        probe_files=(probe.get("files") or {}) if usable else {},
        have_pyarrow=_have_pyarrow(),
        run_smoke=run_smoke,
        today=datetime.now(_TZ_CN).date(),
        top_files=_scan_top(data_root),
    )
    graph = _spec_graph(root, report_id)
    frontmatter = _plan_frontmatter(root, report_id)
    requirements = requirements_from_plan(root, report_id)
    try:
        _warm_facts(ctx, requirements)
    except Exception:  # noqa: BLE001 - 预热只为省时间，出错就退回逐条现测
        pass
    entries = [_check_requirement(ctx, req, graph) for req in requirements]
    remarks = [
        ("读不到 plan.md 的 frontmatter，没有可核对的数据需求", frontmatter is None),
        ("plan.md 的 frontmatter 里没有 data_requirements 列表，没有可核对的数据需求", frontmatter is not None and not isinstance(frontmatter.get("data_requirements"), list)),
        (f"数据根目录不存在：{data_root}", not data_root.is_dir()),
        ("未安装 pyarrow：只查了文件在不在，字段、区间、截面等没有核对（目录体检缓存里已有的实测除外）", not ctx.have_pyarrow),
        ("没有 spec.md：受影响要素只列了需求自己写的 elements", graph is None),
    ]
    return {
        "version": CHECK_VERSION,
        "report_id": report_id,
        "checked_at": _now_cn(),
        "data_root": str(data_root),
        "probe_generated_at": probe.get("generated_at") if usable else None,
        "plan_hash": plan_requirements_hash(root, report_id),
        "pyarrow": ctx.have_pyarrow,
        "smoke_run": run_smoke,
        "seconds": round(time.time() - started, 2),
        "notes": [text for text, hit in remarks if hit],
        "requirements": entries,
        "summary": _summarize(entries),
    }


def load_check(root: Path, report_id: str) -> Optional[dict[str, Any]]:
    """读 workspace/<id>/data_check.json；没有或读不了返回 None。"""
    path = root / "workspace" / report_id / CHECK_JSON
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_check(root: Path, report_id: str, result: dict[str, Any]) -> Path:
    target = root / "workspace" / report_id / CHECK_JSON
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, target)
    return target


def save_check(root: Path, report_id: str, result: dict[str, Any]) -> Path:
    """写 workspace/<id>/data_check.json（原子替换）。

    写之前把已有文件里的处置决定并进来：同名需求的缺口没变（gap_key 相同）就保留；缺口变了或
    没了就清掉，并在条目的 cleared_disposition 里留一笔（原决定、作废时间与原因），这一笔在它
    仍是缺口、还没重新处置期间一直带着。同名需求有多条时按出现顺序对应。result 会被就地更新
    （处置决定与 summary），存完直接拿它算 open_gaps 即可。
    """
    previous = load_check(root, report_id) or {}
    earlier: dict[Any, list[dict[str, Any]]] = {}
    for old in previous.get("requirements") or []:
        if isinstance(old, dict):
            earlier.setdefault(old.get("name"), []).append(old)
    entries = result.get("requirements") or []
    for entry in entries:
        queue = earlier.get(entry.get("name")) or []
        old = queue.pop(0) if queue else {}
        gap_key = entry.setdefault("gap_key", _gap_key(entry))
        if entry.get("disposition"):
            continue  # 调用方自己带了处置决定，照它的
        decided = old.get("disposition")
        same_gap = gap_key is not None and gap_key == old.get("gap_key")
        if decided and same_gap:
            entry["disposition"] = decided
        elif decided:
            entry["disposition"] = None
            reason = "缺口已经没有了" if gap_key is None else "缺口有变化"
            entry["cleared_disposition"] = {**decided, "cleared_at": _now_cn(), "reason": reason}
        elif gap_key is not None and old.get("gap_key") is not None and old.get("cleared_disposition"):
            entry["cleared_disposition"] = old["cleared_disposition"]
    result["summary"] = _summarize(entries)
    return _write_check(root, report_id, result)


def open_gaps(result: dict[str, Any]) -> list[dict[str, Any]]:
    """还没有处置决定的缺口：结论是 partial / missing 且 disposition 为空的需求条目。

    plan 标 missing 的需求结论就是 missing，照样要处置；标 substitute 且替代数据没查出问题的
    结论是 ok 或 unchecked（带 substituted=true），不算缺口；unchecked 也不算缺口。
    """
    return [e for e in result.get("requirements") or [] if e.get("result") in GAP_RESULTS and not e.get("disposition")]


def set_disposition(
    root: Path,
    report_id: str,
    names: Optional[list[str]],
    choice: str,
    *,
    checkpoint: str = "",
    note: str = "",
) -> dict[str, Any]:
    """给指定名称的缺口记下处置决定并写回 data_check.json，返回更新后的结果。

    names=None 表示全部还没处置的缺口；给了名称则只动其中现在是缺口的，已有决定的会被改写。
    点到的需求已经不是缺口（检查点开出来之后数据补上、又重检过）就跳过，不报错——决定要能
    落到剩下的缺口上。choice 不在 DISPOSITIONS 里、还没有体检结果、名称在体检结果里找不到，
    抛 ValueError，且什么都不写。处置决定的形状：{"choice", "checkpoint", "note", "decided_at", "gap_key"}。
    """
    if choice not in DISPOSITIONS:
        raise ValueError(f"处置方式只能是 {' / '.join(DISPOSITIONS)}，收到 {choice!r}")
    result = load_check(root, report_id)
    if result is None:
        raise ValueError(f"{report_id} 还没有数据体检结果（{CHECK_JSON}），先做体检")
    entries = result.get("requirements") or []
    gaps = [e for e in entries if e.get("result") in GAP_RESULTS]
    if names is None:
        targets = [e for e in gaps if not e.get("disposition")]
    else:
        wanted = list(dict.fromkeys([names] if isinstance(names, str) else names))
        unknown = [n for n in wanted if not any(e.get("name") == n for e in entries)]
        if unknown:
            raise ValueError(f"体检结果里没有这些需求：{unknown}")
        targets = [e for e in gaps if e.get("name") in wanted]
    decided_at = _now_cn()
    for entry in targets:
        entry["disposition"] = {
            "choice": choice,
            "checkpoint": checkpoint,
            "note": note,
            "decided_at": decided_at,
            "gap_key": entry.get("gap_key"),
        }
        entry.pop("cleared_disposition", None)
    result["summary"] = _summarize(entries)
    _write_check(root, report_id, result)
    return result


def clear_dispositions(root: Path, report_id: str, *, reason: str, names: Optional[list[str]] = None) -> dict[str, Any]:
    """把缺口上已有的处置决定清掉并写回 data_check.json（人要重新选时用），返回更新后的结果。

    names=None 表示全部缺口；被清掉的决定留在条目的 cleared_disposition 里（原决定、作废时间与原因）。
    还没有体检结果时返回空字典，什么都不写。
    """
    result = load_check(root, report_id)
    if result is None:
        return {}
    entries = result.get("requirements") or []
    cleared_at = _now_cn()
    for entry in entries:
        if entry.get("result") not in GAP_RESULTS or not entry.get("disposition"):
            continue
        if names is not None and entry.get("name") not in names:
            continue
        entry["cleared_disposition"] = {**entry["disposition"], "cleared_at": cleared_at, "reason": reason}
        entry["disposition"] = None
    result["summary"] = _summarize(entries)
    _write_check(root, report_id, result)
    return result


def _evidence_lines(problem: dict[str, Any]) -> list[str]:
    """问题说明之外值得再列出来的实测数字。"""
    code, evidence = problem.get("code"), problem.get("evidence") or {}

    def listing(pairs: dict[str, Any], limit: int = 24) -> str:
        items = [f"{k}: {v}" for k, v in pairs.items()]
        return "、".join(items[:limit]) + (f" …（共 {len(items)} 年）" if len(items) > limit else "")

    if code == "cross_section_collapse" and evidence.get("yearly_codes"):
        return ["逐年标的数 " + listing(evidence["yearly_codes"])]
    if code == "period_short" and evidence.get("thin_years"):
        return ["逐年日期数 " + listing(evidence["thin_years"])]
    if code == "smoke_failed":
        tail = (evidence.get("output_tail") or "").strip().splitlines()
        return [f"命令：`{evidence.get('command', '')}`"] + ([f"末尾输出：{tail[-1][:200]}"] if tail else [])
    if code == "smoke_not_run":
        return [f"命令：`{evidence.get('command', '')}`"]
    return []


def _render_gap(number: int, entry: dict[str, Any]) -> list[str]:
    decided = entry.get("disposition")
    core = {True: "核心数据", False: "非核心数据"}.get(entry.get("core"), "是否核心没有标")
    state = "已定：" + DISPOSITION_CN.get(decided.get("choice"), str(decided.get("choice"))) if decided else "待处置"
    lines = [
        f"## {number}. {entry.get('name', '')}",
        "",
        f"- 结论：{RESULT_CN.get(entry.get('result'), entry.get('result'))} · {core} · {state}",
        f"- plan 里标的状态：{entry.get('status_plan') or '（没写）'}" + ("（plan 没把它当缺口，与实测不符）" if entry.get("plan_mismatch") else ""),
    ]
    if entry.get("files"):
        lines.append("- 文件：" + "、".join(f"`{name}`" for name in entry["files"]))
    elif entry.get("source"):
        lines.append(f"- 来源：{entry['source']}")
    lines.append("- 缺什么：")
    for problem in entry.get("problems") or []:
        code = problem.get("code", "")
        lines.append(f"  - {PROBLEM_CN.get(code, code)}（{code}）：{problem.get('detail', '')}")
        lines += [f"    - {text}" for text in _evidence_lines(problem)]
    if entry.get("hints"):
        lines.append("- 目录体检的提示（不计入结论）：" + "；".join(entry["hints"]))
    affected = entry.get("affected_elements") or []
    if affected:
        cap = "，已到上限，可能不全" if entry.get("affected_truncated") else ""
        lines.append(f"- 影响要素（{len(affected)} 个{cap}）：" + "、".join(affected))
    else:
        lines.append("- 影响要素：plan 没有写 elements，无从传递")
    if decided:
        extras = [
            f"检查点 {decided['checkpoint']}" if decided.get("checkpoint") else "",
            decided.get("note") or "",
            decided.get("decided_at") or "",
        ]
        lines.append(f"- 处置决定：{DISPOSITION_CN.get(decided.get('choice'), '')}（{decided.get('choice')}）" + "".join(f"；{text}" for text in extras if text))
    else:
        lines.append("- 处置决定：未定。可选：" + " / ".join(f"{cn}（{key}）" for key, cn in DISPOSITION_CN.items()))
        cleared = entry.get("cleared_disposition")
        if cleared:
            lines.append(f"  - 之前定过「{DISPOSITION_CN.get(cleared.get('choice'), cleared.get('choice'))}」，{cleared.get('reason', '缺口有变化')}，已作废，要重新定")
    return lines + [""]


def render_gap_report(result: dict[str, Any], *, only_open: bool = False) -> str:
    """给人看的缺口清单（markdown）。

    逐条写：缺什么（附实测证据：哪个文件、实测区间、每年标的数的塌陷年份等）、影响哪些要素、
    是否核心、plan 里标的状态、已有的处置决定。only_open=True 只列还没处置的缺口。完整清单的
    末尾另附不算缺口的几类（已替代、未机检、目录体检的提示）各一行。没有缺口时只有一句话。
    """
    entries = result.get("requirements") or []
    summary = _summarize(entries)
    gaps = [e for e in entries if e.get("result") in GAP_RESULTS]
    pending = [e for e in gaps if not e.get("disposition")]
    hinted = [e for e in entries if e.get("hints") and e.get("result") not in GAP_RESULTS]
    counts = f"{summary['total']} 条数据需求：通过 {summary['ok']}、部分满足 {summary['partial']}、缺失 {summary['missing']}、未机检 {summary['unchecked']}"
    if not gaps:
        names = "、".join(e.get("name", "") for e in hinted[:3]) + (" 等" if len(hinted) > 3 else "")
        asides = ([f"已替代 {summary['substituted']} 条"] if summary["substituted"] else []) + (
            [f"其中 {len(hinted)} 条只查了文件在不在，而目录体检对它们的文件有提示：{names}"] if hinted else []
        )
        return f"没有数据缺口（{counts}{''.join('；' + text for text in asides)}）。\n"
    if only_open and not pending:
        return f"没有待处置的数据缺口：{len(gaps)} 个缺口都已有处置决定。\n"
    lines = [
        f"# 数据缺口清单 · {result.get('report_id', '')}",
        "",
        f"> 体检于 {result.get('checked_at', '')}，数据根目录 `{result.get('data_root', '')}`。",
        f"> 共 {counts}。缺口 {len(gaps)} 个，其中 {len(pending)} 个还没有处置决定" + ("；下面只列待处置的。" if only_open else "。"),
    ]
    lines += [f"> 注意：{text}" for text in result.get("notes") or []] + [""]
    for number, entry in enumerate(pending if only_open else gaps, 1):
        lines += _render_gap(number, entry)
    if not only_open:
        replaced = [e for e in entries if e.get("substituted")]
        unchecked = [e for e in entries if e.get("result") == "unchecked" and not e.get("substituted")]
        if replaced:
            lines += [f"## 已替代（{len(replaced)} 条，不算缺口）", ""]
            lines += [
                f"- {e.get('name', '')}：" + ("替代数据查过，" + "、".join(f"`{f}`" for f in e["files"]) + " 都在" if e.get("files") else "替代数据机器查不了")
                for e in replaced
            ] + [""]
        if unchecked:
            lines += [f"## 未机检（{len(unchecked)} 条，不算缺口）", ""]
            lines += [f"- {e.get('name', '')}：" + "；".join(p.get("detail", "") for p in e.get("problems") or []) for e in unchecked] + [""]
        if hinted:
            lines += ["## 目录体检的提示（不计入结论）", ""]
            lines += [f"- {e.get('name', '')}：{text}" for e in hinted for text in e["hints"]] + [""]
    return "\n".join(lines)
