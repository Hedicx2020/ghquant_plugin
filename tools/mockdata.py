#!/usr/bin/env python3
"""按规格确定性地生成模拟数据（mock 试跑的数据侧，方案第 4.5 节）。

    uv run python tools/mockdata.py generate <report_id> [--spec <yaml>] [--out <dir>] [--data-root <dir>]
    uv run python tools/mockdata.py check <report_id> [--spec <yaml>] [--data-root <dir>]   # 只校验，不生成

默认规格 workspace/<report_id>/data_mock/spec.yaml，默认输出 workspace/<report_id>/data_mock/files/，
并在输出目录的同级写 manifest.json（每张表的来源、行数、列名 columns 与类型 dtypes、日期起止、
标的数、sha256、退回了哪种兜底 fallbacks、生成时的说明 notes）。生成的文件与数据根里的同名：
策略代码经 common.data_loader.data_path() 取数，试跑模式下先读到这里的文件。本工具只生成数据，
不创建试跑标记 ACTIVE（那是内核的事），也不往数据根里写任何东西。

进程内调用：load_spec(path) → validate_spec(spec)（返回错误清单，空表示合法）→
generate(spec, out_dir, data_root, ...)（返回 manifest 字典）；inspect_sources() 只看每张表会
用哪种来源。规格有错抛 MockSpecError，对着实际数据生成不出来抛 MockDataError。

来源有三种，同一张表可以写多种作退路，按 sample → borrow → synth 的优先级取第一个可用的：

    sample  人给的样例文件，原样（或按 period 截取后）拷进覆盖目录
    borrow  借一张结构相近的真实表改键、改日期，保留真实的截面分布与缺失形态
            （纯随机数据容易算出除零、奇异矩阵或空信号）
    synth   前两种都没有，才按字段类别随机生成

交易日历与证券代码取数据根里的真实数据，保证与其他表对得上；取不到时退回工作日日历和自造
代码，并记在 manifest 里。随机数由（种子、表名、列名）决定：同一规格加同一份本地数据，两次
生成的文件逐字节相同；增删别的表或列不影响已有列的取值。

规格示例（workspace/<report_id>/data_mock/spec.yaml）::

    version: 1
    seed: 20261121                      # 随机种子（可省略）
    period: [2018-01-01, 2020-12-31]    # 默认区间（含两端），各表可覆盖
    freq: D                             # 默认频率 D / W / M / Q，各表可覆盖
    n_codes: 300                        # 默认标的数，各表可覆盖
    max_rows: 5000000                   # 单表行数上限，防止写错规格生成出巨表
    calendar:                           # 交易日历（可省略，省略时就是下面这几项）
      file: ashare_tradeday.parquet     #   数据根相对路径
      date_col: date
      flag_col: IfTradingDay            #   有这一列时只取等于 1 的行
    codes:                              # 证券代码来源（可省略，省略时就是下面这两项）
      file: ashare_stock.parquet
      column: stock_code
      # where: {list_state: 1}          #   只取满足条件的行；值写成列表表示「属于其中之一」
      # list: ["000001", "600000"]      #   也可以不读文件，直接给代码清单（与 file 二选一）；代码一律加引号

    tables:
      # ── 来源一 sample：人给的样例文件（优先级最高）────────────────────────────
      - name: analyst_rating.parquet        # 数据根相对路径；生成到覆盖目录里的同名文件
        note: 分析师评级，本地没有           # 备注，给人看
        sample:
          path: samples/analyst_rating.csv  # 相对路径先按规格文件所在目录找，再按仓库根找；也可写绝对路径
          trim: true                        # 按 period 截取；默认 false：原样拷贝（后缀不同则转存）
          date_col: rating_date             # 截取用的日期列；不写时按常见日期列名找
          parse_dates: [rating_date]        # csv / xlsx 转存时解析成日期的列；不写时取 date_col 和常见日期列名
        # 同一张表可以再写 borrow / columns 作退路：样例文件不存在时依次退回，退回了哪一种记在
        # manifest 里。想写死只用某一种，加一行 source: sample（或 borrow / synth）。

      # ── 来源二 borrow：借一张结构相近的真实表改键、改日期 ──────────────────────
      - name: hkshare_stock_quote_ext.parquet
        period: [2014-01-01, 2015-12-31]
        freq: D                             # W / M / Q 时每个周期只留最后一个日期的行
        n_codes: 200                        # 从借来的表里取多少个标的；不写取全部
        calendar: {file: hkshare_tradeday.parquet, date_col: date}
        borrow:
          from: ashare_stock_price.parquet  # 被借的真实表（数据根相对路径）
          columns: [stock_code, date, prev_close, open, high, low, close]   # 截取列（源表列名）；不写取全部
          rename: {stock_code: secu_code}   # 列重命名（源表列名: 新列名）
          code_col: stock_code              # 源表的代码列、日期列；不写时按常见列名找
          date_col: date
          codes:                            # 改键（不写就保持源表的代码）
            replace: {file: hkshare_stock.parquet, column: stock_code}   # 整体换成另一组代码
            # replace: true                 # true 表示换成本表（或顶层）codes 指定的那组代码
            # map: {"000001": "00001"}      # 或逐个映射（代码加引号）；没列到的保持原样，drop_unmapped: true 则丢弃
          dates:                            # 改日期（不写就是 keep）
            mode: resample                  # keep     日期不动，只按 period 截取
                                            # shift    整体平移 years / months / days（月末仍对月末），再按 period 截取；
                                            #          平移后的日期不保证是交易日，要对上日历用 resample
                                            # resample 把源表的日期按先后依次对到目标区间的日历上；
                                            #          源表日期不够时循环铺满，多了取最近的一段
            # years: -5                     # shift 用
            # source_period: [2019-01-01, 2020-12-31]   # resample 时只取源表的这一段
            # anchor: natural               # resample 的目标日期取自然周期末（默认 trading：交易日历）
            # min_coverage: 0.1             # resample 时不取截面太稀的源日期：行数不到峰值的这个比例（默认 0.1，0 为不筛）
          shift_cols: [update_time]         # 跟着主日期列一起挪的其他日期列；不写时取其余所有时间类型的列

      # ── 来源三 synth：按字段类别随机生成（前两种都没有才用）────────────────────
      - name: stock_sentiment_score.parquet
        freq: M
        n_codes: 100
        drop_rows: 0.05                     # 随机丢掉这个比例的行，模拟不平衡面板
        columns:
          - {name: stock_code, kind: code}
          - {name: date, kind: date}
          - {name: close, kind: price, start: [5, 80], vol: 0.08}
          - {name: high, kind: price, base: close, role: high}
          - {name: ret, kind: return, of: close}
          - {name: volume, kind: volume, median: 2000000, zero_rate: 0.01}
          - {name: amount, kind: amount}
          - {name: turnover, kind: ratio, low: 0, high: 0.2}
          - {name: n_reports, kind: count, mean: 3}
          - {name: industry, kind: category, values: [银行, 医药, 电子], per: code}
          - {name: is_st, kind: flag, rate: 0.03}
          - {name: stock_name, kind: text, length: 6}
          - {name: score, kind: value, mean: 0, std: 1, missing: 0.1}
          - {name: info_publ_date, kind: publ_date, base: date, lag_days: [10, 45]}

synth 的字段类别（每列都可以写 missing: 缺失率，date / code 两种主键列除外）：

    date       日期主键，取自交易日历。dtype: datetime（默认）/ str / int（YYYYMMDD）；format：
               dtype 为 str 时的写法，默认 %Y-%m-%d；anchor: trading（默认）/ natural（自然周期末，
               适合报告期）
    code       代码主键，取自 codes 指定的来源，共 n_codes 个
    price      几何随机游走，恒为正。start: 起始价或 [下限, 上限]；drift、vol：每期对数收益的
               均值、波动；round：小数位。写 base: <某个 price 列> 加 role: open / high / low /
               prev_close / vwap 则由那一列派生，保证 low ≤ open、vwap ≤ high 这些关系
    return     收益率。mean、std（按小数写）；unit: decimal（默认）/ percent；写 of: <某个 price 列>
               则由那一列算出（每个代码的首期为空）
    volume     成交量，对数正态，非负。median、sigma、zero_rate（取 0 的比例）、round
    amount     成交额，同 volume，量级更大
    ratio      比率。low、high（默认 0 到 1 均匀）；dist: normal 时用 mean、std 并截到 [low, high]
    count      非负整数。mean（泊松，默认 5），或 low、high（均匀）
    category   给定取值集合。values（必填）、weights；per: row（默认）/ code（每个代码固定一个）
    flag       0 / 1。rate：取 1 的比例；per: row / code
    text       随机文本。length、prefix；per: row / code（有代码列时默认 code）
    publ_date  披露日 = 报告期 + 若干天。base：报告期所在的 date 列（默认就是那一列）；
               lag_days: 天数或 [最少, 最多]；dtype、format 同 date
    value      一般数值，正态。mean、std、low、high；walk: true 时沿日期累加；per: row / code

没有 date 也没有 code 列的表，用表级的 rows 指定行数。

各表的代码怎么对得上：synth 表和写了 codes.replace 的 borrow 表，都从 codes 指定的全集里按同一
规则挑 n_codes 个——n_codes 相同则代码完全一致，小的是大的子集。不改键的 borrow 表沿用源表
自己的代码（同一规则，在源表有数据的代码里挑），与前两者不保证一一对应；要严格对上，给它写
codes: {replace: true}。

依赖 pandas / numpy / pyarrow / pyyaml，都在函数里按需导入；校验规格（validate_spec）只用标准库。
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import importlib
import json
import operator
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

SPEC_VERSION = 1
DEFAULT_SEED = 20261121
DEFAULT_FREQ = "D"
DEFAULT_N_CODES = 300
DEFAULT_MAX_ROWS = 5_000_000
DEFAULT_MIN_COVERAGE = 0.1  # resample 时，行数不到峰值这个比例的源日期算截面太稀，不取用
FREQS = ("D", "W", "M", "Q")
SOURCES = ("sample", "borrow", "synth")  # 优先级从高到低
SOURCE_BLOCKS = {"sample": "sample", "borrow": "borrow", "synth": "columns"}  # 每种来源在表里对应的段
OUTPUT_SUFFIXES = (".parquet", ".csv", ".feather")
DEFAULT_CALENDAR = {"file": "ashare_tradeday.parquet", "date_col": "date"}
DEFAULT_FLAG_COL = "IfTradingDay"
DEFAULT_CODES = {"file": "ashare_stock.parquet", "column": "stock_code"}
MOCK_DIR = "data_mock"
FILES_DIR = "files"
SPEC_NAME = "spec.yaml"
MANIFEST_NAME = "manifest.json"
TZ_CN = timezone(timedelta(hours=8))

# 证券代码列、日期列的识别顺序（排在前面的优先），与 tools/flowlib/datacheck.py 一致
CODE_COLUMNS = (
    "stock_code", "stcode", "secu_code", "ts_code", "symbol", "ticker",
    "index_code", "fund_code", "bond_code", "contract_code", "option_code",
    "indicator_code", "inner_code", "InnerCode", "company_code",
)
DATE_COLUMNS = (
    "date", "trade_dt", "trade_date", "trading_day", "cal_date", "TradingDay",
    "end_date", "report_date", "info_publ_date", "publ_date", "ann_date",
)
# csv / xlsx 不带列类型，这些代码列按文本读入（保住前导零）
TEXT_CODE_COLUMNS = CODE_COLUMNS[:11]
PRICE_ROLES = ("open", "high", "low", "prev_close", "vwap")
# 改日期后要按原样写回的文本日期写法
TEXT_DATE_FORMATS = (
    ("%Y-%m-%d", r"\d{4}-\d{2}-\d{2}"),
    ("%Y%m%d", r"\d{8}"),
    ("%Y/%m/%d", r"\d{4}/\d{2}/\d{2}"),
    ("%Y-%m-%d %H:%M:%S", r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"),
)


class MockSpecError(ValueError):
    """规格文件有错。errors 是逐条的中文说明，指明哪张表哪个字段。"""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        super().__init__("；".join(self.errors))


class MockDataError(RuntimeError):
    """规格本身合法，但对着实际数据生成不出来（源表缺列、截取后没有行、行数超限等）。"""


# ---------------------------------------------------------------------------
# 规格：读取与校验（只用标准库）
# ---------------------------------------------------------------------------


def load_spec(path: Path | str) -> dict[str, Any]:
    """读规格文件，返回顶层映射。文件不存在、不是合法 YAML 或顶层不是映射时抛 MockSpecError。"""
    import yaml

    path = Path(path)
    if not path.is_file():
        raise MockSpecError([f"规格文件不存在: {path}"])
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = "" if mark is None else f"第 {mark.line + 1} 行第 {mark.column + 1} 列，"
        raise MockSpecError([f"规格文件不是合法的 YAML（{path}）: {where}{getattr(exc, 'problem', None) or exc}"]) from exc
    if not isinstance(data, dict):
        raise MockSpecError([f"规格文件顶层必须是映射（键: 值），实际是 {type(data).__name__}（{path}）"])
    return data


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and abs(value) != float("inf")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_pair(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == 2


def _as_date(value: Any) -> Optional[date]:
    """把规格里的日期（YAML 日期、2020-01-31、20200131）规整成 date；认不出来返回 None。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip() if _is_int(value) or isinstance(value, str) else ""
    matched = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", text)
    if not matched:
        return None
    try:
        return date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))
    except ValueError:
        return None


def _show(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _brief(names: Sequence[Any], limit: int = 20) -> str:
    shown = ", ".join(str(n) for n in names[:limit])
    return shown if len(names) <= limit else f"{shown} 等 {len(names)} 个"


def _choice(*options: str) -> tuple[Callable[[Any], bool], str]:
    return (lambda value: value in options, " / ".join(options) + " 之一")


def _uniform_scalars(value: Any) -> bool:
    """非空列表，取值类型一致：都是文本，或都是数字。"""
    if not isinstance(value, list) or not value:
        return False
    return all(isinstance(v, str) for v in value) or all(_is_num(v) for v in value)


_RULES: dict[str, tuple[Callable[[Any], bool], str]] = {
    "text": (_is_text, "非空文本"),
    "any_text": (lambda v: isinstance(v, str), "文本"),
    "num": (_is_num, "数字"),
    "nonneg": (lambda v: _is_num(v) and v >= 0, "不小于 0 的数字"),
    "pos": (lambda v: _is_num(v) and v > 0, "正数"),
    "rate": (lambda v: _is_num(v) and 0 <= v <= 1, "0 到 1 之间的数字"),
    "part": (lambda v: _is_num(v) and 0 <= v < 1, "0（含）到 1（不含）之间的数字"),
    "int": (_is_int, "整数"),
    "nonneg_int": (lambda v: _is_int(v) and v >= 0, "非负整数"),
    "pos_int": (lambda v: _is_int(v) and v > 0, "正整数"),
    "bool": (lambda v: isinstance(v, bool), "true / false"),
    "start": (
        lambda v: (_is_num(v) and v > 0) or (_is_pair(v) and all(_is_num(x) and x > 0 for x in v) and v[0] <= v[1]),
        "正数，或 [下限, 上限]（都为正）",
    ),
    "lag": (
        lambda v: (_is_int(v) and v >= 0) or (_is_pair(v) and all(_is_int(x) and x >= 0 for x in v) and v[0] <= v[1]),
        "非负整数，或 [最少天数, 最多天数]",
    ),
    "values": (_uniform_scalars, "非空列表，且取值类型一致（都是文本或都是数字）"),
    "weights": (
        lambda v: isinstance(v, list) and bool(v) and all(_is_num(x) and x >= 0 for x in v) and sum(v) > 0,
        "非负数字的列表（不能全为 0）",
    ),
    "names": (lambda v: isinstance(v, list) and all(_is_text(x) for x in v), "列名的列表"),
}
_DATE_REPR = {"dtype": _choice("datetime", "str", "int"), "format": _RULES["text"]}
_PER = {"per": _choice("row", "code")}
_VOLUME = {"median": _RULES["pos"], "sigma": _RULES["nonneg"], "zero_rate": _RULES["rate"], "round": _RULES["nonneg_int"]}
# 每种字段类别可写的参数及其取值要求
_KIND_PARAMS: dict[str, dict[str, tuple[Callable[[Any], bool], str]]] = {
    "date": {**_DATE_REPR, "anchor": _choice("trading", "natural")},
    "code": {},
    "price": {
        "start": _RULES["start"], "drift": _RULES["num"], "vol": _RULES["nonneg"], "round": _RULES["nonneg_int"],
        "base": _RULES["text"], "role": _choice(*PRICE_ROLES), "spread": _RULES["nonneg"],
    },
    "return": {"mean": _RULES["num"], "std": _RULES["nonneg"], "unit": _choice("decimal", "percent"), "of": _RULES["text"]},
    "volume": _VOLUME,
    "amount": _VOLUME,
    "ratio": {"low": _RULES["num"], "high": _RULES["num"], "dist": _choice("uniform", "normal"), "mean": _RULES["num"], "std": _RULES["nonneg"]},
    "count": {"mean": _RULES["nonneg"], "low": _RULES["nonneg_int"], "high": _RULES["nonneg_int"]},
    "category": {"values": _RULES["values"], "weights": _RULES["weights"], **_PER},
    "flag": {"rate": _RULES["rate"], **_PER},
    "text": {"length": _RULES["pos_int"], "prefix": _RULES["any_text"], **_PER},
    "publ_date": {"base": _RULES["text"], "lag_days": _RULES["lag"], **_DATE_REPR},
    "value": {"mean": _RULES["num"], "std": _RULES["nonneg"], "low": _RULES["num"], "high": _RULES["num"], "walk": _RULES["bool"], **_PER},
}
KINDS = tuple(_KIND_PARAMS)
_KEY_KINDS = ("date", "code")
_COLUMN_COMMON = ("name", "kind", "missing", "note")
_QUOTE_CODES = "代码要加引号写成文本：不加引号时 YAML 会把 000001 读成 1、把 000010 读成 8"

_TOP_KEYS = ("version", "seed", "period", "freq", "n_codes", "max_rows", "calendar", "codes", "tables", "note")
_TABLE_KEYS = ("name", "note", "source", "period", "freq", "n_codes", "calendar", "codes", "sample", "borrow", "columns", "drop_rows", "rows")
_SAMPLE_KEYS = ("path", "trim", "date_col", "code_col", "parse_dates")
_BORROW_KEYS = ("from", "columns", "rename", "code_col", "date_col", "codes", "dates", "shift_cols")
_BORROW_CODES_KEYS = ("map", "replace", "drop_unmapped")
_DATES_KEYS = ("mode", "years", "months", "days", "source_period", "anchor", "min_coverage")
_DATE_MODES = ("keep", "shift", "resample")
_CALENDAR_KEYS = ("file", "date_col", "flag_col")
_CODES_KEYS = ("file", "column", "where", "list")
_SCALAR_RULES: dict[str, tuple[Callable[[Any], bool], str]] = {
    "version": (lambda v: v == SPEC_VERSION, str(SPEC_VERSION)),
    "seed": _RULES["nonneg_int"],
    "freq": _choice(*FREQS),
    "n_codes": _RULES["pos_int"],
    "max_rows": _RULES["pos_int"],
    "note": _RULES["any_text"],
    "drop_rows": _RULES["part"],
    "rows": _RULES["pos_int"],
}


def _unknown_keys(where: str, node: dict[Any, Any], allowed: Iterable[str]) -> list[str]:
    allowed = list(allowed)
    extra = [str(k) for k in node if k not in allowed]
    return [f"{where}: 不认识的字段 {extra}（可用: {', '.join(allowed)}）"] if extra else []


def _check_rules(where: str, node: dict[str, Any], rules: dict[str, tuple[Callable[[Any], bool], str]]) -> list[str]:
    """node 里出现的字段，凡在 rules 里有要求的逐个核对。"""
    return [
        f"{where}: {key} 取值不对（要求: {rules[key][1]}），实际是 {_show(node[key])}"
        for key in rules
        if key in node and not rules[key][0](node[key])
    ]


def _check_rel_path(where: str, key: str, value: Any) -> list[str]:
    if not _is_text(value):
        return [f"{where}: {key} 应为非空文本（数据根相对路径），实际是 {_show(value)}"]
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return [f"{where}: {key} 必须是数据根下的相对路径，不能是绝对路径或含 ..（实际是 {_show(value)}）"]
    return []


def _check_period(where: str, key: str, value: Any) -> list[str]:
    if not _is_pair(value):
        return [f"{where}: {key} 应写成 [起始日期, 截止日期]，实际是 {_show(value)}"]
    days = [_as_date(v) for v in value]
    bad = [v for v, day in zip(value, days) if day is None]
    if bad:
        return [f"{where}: {key} 里的 {_show(bad[0])} 不是日期（写成 2020-01-31 或 20200131）"]
    return [f"{where}: {key} 的起点 {days[0]} 晚于终点 {days[1]}"] if days[0] > days[1] else []


def _check_calendar(where: str, value: Any) -> list[str]:
    if not isinstance(value, dict):
        return [f"{where}: calendar 应为映射（file、date_col、flag_col），实际是 {_show(value)}"]
    inner = f"{where}: calendar"
    errors = _unknown_keys(inner, value, _CALENDAR_KEYS)
    errors += _check_rel_path(inner, "file", value.get("file"))
    return errors + _check_rules(inner, value, {"date_col": _RULES["text"], "flag_col": _RULES["text"]})


def _check_codes(where: str, key: str, value: Any) -> list[str]:
    inner = f"{where}: {key}"
    if not isinstance(value, dict):
        return [f"{inner} 应为映射（file + column，或 list），实际是 {_show(value)}"]
    errors = _unknown_keys(inner, value, _CODES_KEYS)
    if "list" in value:
        codes = value["list"]
        if not isinstance(codes, list) or not codes or not all(_is_text(c) for c in codes):
            errors.append(f"{inner}.list 应为非空的代码列表（{_QUOTE_CODES}），实际是 {_show(codes)}")
        if "file" in value or "column" in value or "where" in value:
            errors.append(f"{inner}: list 与 file / column / where 只能写一种")
        return errors
    errors += _check_rel_path(inner, "file", value.get("file"))
    if not _is_text(value.get("column")):
        errors.append(f"{inner}: column 应为非空文本（代码所在的列），实际是 {_show(value.get('column'))}")
    if "where" in value and not (isinstance(value["where"], dict) and all(_is_text(k) for k in value["where"])):
        errors.append(f"{inner}: where 应为映射（列名: 取值或取值列表），实际是 {_show(value['where'])}")
    return errors


def _check_shared(where: str, node: dict[str, Any], scalar_keys: Sequence[str]) -> list[str]:
    """顶层和表都能写的那几项：period / calendar / codes，以及给定的标量字段。"""
    errors = _check_rules(where, node, {key: _SCALAR_RULES[key] for key in scalar_keys})
    errors += _check_period(where, "period", node["period"]) if "period" in node else []
    errors += _check_calendar(where, node["calendar"]) if "calendar" in node else []
    errors += _check_codes(where, "codes", node["codes"]) if "codes" in node else []
    return errors


def _has_period(table: dict[str, Any], spec: dict[str, Any]) -> bool:
    return "period" in table or "period" in spec


def _check_sample(where: str, table: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    conf = table["sample"]
    inner = f"{where}: sample"
    if not isinstance(conf, dict):
        return [f"{inner} 应为映射（path、trim、date_col ...），实际是 {_show(conf)}"]
    errors = _unknown_keys(inner, conf, _SAMPLE_KEYS)
    if not _is_text(conf.get("path")):
        errors.append(f"{inner}.path 必填（样例文件的路径），实际是 {_show(conf.get('path'))}")
    errors += _check_rules(inner, conf, {"trim": _RULES["bool"], "date_col": _RULES["text"], "code_col": _RULES["text"], "parse_dates": _RULES["names"]})
    if conf.get("trim") is True and not _has_period(table, spec):
        errors.append(f"{inner}.trim 为 true 时要有 period（写在这张表或顶层）")
    return errors


def _check_borrow_codes(inner: str, value: Any) -> list[str]:
    where = f"{inner}.codes"
    if not isinstance(value, dict):
        return [f"{where} 应为映射（map 或 replace），实际是 {_show(value)}"]
    errors = _unknown_keys(where, value, _BORROW_CODES_KEYS)
    if ("map" in value) == ("replace" in value):
        errors.append(f"{where}: map 与 replace 要写且只能写一个")
    if "map" in value:
        mapping = value["map"]
        if not isinstance(mapping, dict) or not mapping or not all(_is_text(k) and _is_text(v) for k, v in mapping.items()):
            errors.append(f"{where}.map 应为非空映射（原代码: 新代码；{_QUOTE_CODES}），实际是 {_show(mapping)}")
    if "replace" in value and value["replace"] is not True:
        errors += _check_codes(inner, "codes.replace", value["replace"])
    if "drop_unmapped" in value and not (isinstance(value["drop_unmapped"], bool) and "map" in value):
        errors.append(f"{where}.drop_unmapped 应为 true / false，且只与 map 一起用")
    return errors


def _dates_conf(conf: dict[str, Any]) -> dict[str, Any]:
    """borrow.dates 的规整形式：简写 dates: shift 展开成 {mode: shift}，不写就是 keep。"""
    dates = conf.get("dates")
    if dates is None:
        return {"mode": "keep"}
    return {"mode": dates} if isinstance(dates, str) else dates


def _check_borrow_dates(inner: str, table: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    where = f"{inner}.dates"
    dates = _dates_conf(table["borrow"])
    if not isinstance(dates, dict):
        return [f"{where} 应为 keep / shift / resample 之一，或带 mode 的映射，实际是 {_show(dates)}"]
    errors = _unknown_keys(where, dates, _DATES_KEYS)
    mode = dates.get("mode", "keep")
    if mode not in _DATE_MODES:
        return errors + [f"{where}.mode 应为 {' / '.join(_DATE_MODES)} 之一，实际是 {_show(mode)}"]
    errors += _check_rules(where, dates, {"years": _RULES["int"], "months": _RULES["int"], "days": _RULES["int"], "anchor": _choice("trading", "natural"), "min_coverage": _RULES["rate"]})
    offsets = [key for key in ("years", "months", "days") if key in dates]
    if mode == "shift" and not any(_is_int(dates[key]) and dates[key] != 0 for key in offsets):
        errors.append(f"{where}: mode 为 shift 时要写 years / months / days 中至少一个非零的整数")
    if mode != "shift" and offsets:
        errors.append(f"{where}: {' / '.join(offsets)} 只在 mode 为 shift 时使用")
    stray = [key for key in ("source_period", "anchor", "min_coverage") if key in dates and mode != "resample"]
    if stray:
        errors.append(f"{where}: {' / '.join(stray)} 只在 mode 为 resample 时使用")
    if "source_period" in dates:
        errors += _check_period(where, "source_period", dates["source_period"])
    if mode == "resample" and not _has_period(table, spec):
        errors.append(f"{where}: mode 为 resample 时要有 period（写在这张表或顶层）")
    return errors


def _check_borrow(where: str, table: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    conf = table["borrow"]
    inner = f"{where}: borrow"
    if not isinstance(conf, dict):
        return [f"{inner} 应为映射（from、columns、rename ...），实际是 {_show(conf)}"]
    errors = _unknown_keys(inner, conf, _BORROW_KEYS)
    errors += _check_rel_path(inner, "from", conf.get("from")) if "from" in conf else [f"{inner}.from 必填（被借的真实表，数据根相对路径）"]
    errors += _check_rules(inner, conf, {"columns": _RULES["names"], "code_col": _RULES["text"], "date_col": _RULES["text"], "shift_cols": _RULES["names"]})
    columns = conf.get("columns")
    if isinstance(columns, list) and (not columns or len(set(map(str, columns))) != len(columns)):
        errors.append(f"{inner}.columns 不能为空，也不能有重复的列")
    rename = conf.get("rename")
    if rename is not None:
        if not isinstance(rename, dict) or not all(_is_text(k) and _is_text(v) for k, v in rename.items()):
            errors.append(f"{inner}.rename 应为映射（源表列名: 新列名），实际是 {_show(rename)}")
        elif len(set(rename.values())) != len(rename):
            errors.append(f"{inner}.rename 里有两列被改成了同一个名字")
    errors += _check_borrow_codes(inner, conf["codes"]) if "codes" in conf else []
    return errors + _check_borrow_dates(inner, table, spec)


def _column_label(where: str, index: int, column: Any) -> str:
    name = column.get("name") if isinstance(column, dict) else None
    return f"{where}: columns[{index}]" + (f"（{name}）" if _is_text(name) else "")


def _check_column(where: str, column: Any) -> list[str]:
    """一列自身的合法性：name、kind、该类别允许的参数及取值。"""
    if not isinstance(column, dict):
        return [f"{where} 应为映射（name、kind 及参数），实际是 {_show(column)}"]
    errors = [] if _is_text(column.get("name")) else [f"{where}: 缺少 name（列名）"]
    kind = column.get("kind")
    if kind not in _KIND_PARAMS:
        return errors + [f"{where}: kind {_show(kind)} 不认识，可选 {' / '.join(KINDS)}"]
    params = _KIND_PARAMS[kind]
    errors += _unknown_keys(f"{where}（kind={kind}）", column, [*_COLUMN_COMMON, *params])
    errors += _check_rules(where, column, params)
    errors += _check_rules(where, column, {"note": _RULES["any_text"]})
    if "missing" in column:
        if kind in _KEY_KINDS:
            errors.append(f"{where}: {kind} 列是主键，不能设 missing")
        else:
            errors += _check_rules(where, column, {"missing": _RULES["part"]})
    low, high = column.get("low"), column.get("high")
    if kind == "ratio" and column.get("dist", "uniform") == "uniform":
        low, high = (0 if low is None else low), (1 if high is None else high)
    if _is_num(low) and _is_num(high) and low > high:
        errors.append(f"{where}: low（{low}）大于 high（{high}）")
    if kind == "category":
        values, weights = column.get("values"), column.get("weights")
        if "values" not in column:
            errors.append(f"{where}: category 要写 values（取值集合）")
        elif isinstance(values, list) and isinstance(weights, list) and len(values) != len(weights):
            errors.append(f"{where}: weights 的个数（{len(weights)}）与 values（{len(values)}）不一致")
    if kind == "price" and ("base" in column) != ("role" in column):
        errors.append(f"{where}: base 与 role 要一起写（由哪一列派生、派生成什么）")
    if kind == "price" and "base" in column and any(key in column for key in ("start", "drift", "vol")):
        errors.append(f"{where}: 写了 base 就是派生列，start / drift / vol 不起作用，请去掉")
    if kind == "return" and "of" in column and any(key in column for key in ("mean", "std")):
        errors.append(f"{where}: 写了 of 就是由价格算出的收益，mean / std 不起作用，请去掉")
    if kind == "value" and column.get("walk") is True and column.get("per") == "code":
        errors.append(f"{where}: walk 与 per: code 不能同时用")
    return errors


def _check_columns(where: str, table: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """synth 的列定义：逐列检查，再查列与列之间的引用。"""
    columns = table["columns"]
    if not isinstance(columns, list) or not columns:
        return [f"{where}: columns 应为非空列表（每列写 name、kind 及参数）"]
    labels = [_column_label(where, i, c) for i, c in enumerate(columns)]
    errors = [e for label, column in zip(labels, columns) for e in _check_column(label, column)]
    known = [(label, c) for label, c in zip(labels, columns) if isinstance(c, dict) and _is_text(c.get("name")) and c.get("kind") in _KIND_PARAMS]
    names = [c["name"] for _, c in known]
    errors += [f"{where}: columns 里列名 {name} 重复" for name in dict.fromkeys(n for n in names if names.count(n) > 1)]
    by_kind = {kind: [c["name"] for _, c in known if c["kind"] == kind] for kind in KINDS}
    errors += [f"{where}: columns 里最多只能有一个 {kind} 列（现有 {by_kind[kind]}）" for kind in _KEY_KINDS if len(by_kind[kind]) > 1]
    primary_prices = [c["name"] for _, c in known if c["kind"] == "price" and "base" not in c]
    for label, column in known:
        kind = column["kind"]
        if kind == "publ_date":
            if not by_kind["date"]:
                errors.append(f"{label}: publ_date 要以表里的 date 列为基准，这张表没有 date 列")
            elif "base" in column and column["base"] not in by_kind["date"]:
                errors.append(f"{label}: base 应指向表里的 date 列（{by_kind['date'][0]}），实际是 {_show(column['base'])}")
        for key in ("base", "of"):
            if kind in ("price", "return") and _is_text(column.get(key)) and column[key] not in primary_prices:
                errors.append(f"{label}: {key} 应指向表里一个不是派生出来的 price 列（现有 {primary_prices}），实际是 {_show(column[key])}")
        if column.get("per") == "code" and not by_kind["code"]:
            errors.append(f"{label}: per: code 需要表里有 code 列")
    keyed = bool(by_kind["date"] or by_kind["code"])
    if not keyed and "rows" not in table:
        errors.append(f"{where}: 既没有 date 列也没有 code 列时，要用 rows 指定行数")
    if keyed and "rows" in table:
        errors.append(f"{where}: rows 只在既没有 date 列也没有 code 列时使用")
    if by_kind["date"] and not _has_period(table, spec):
        errors.append(f"{where}: 有 date 列时要有 period（写在这张表或顶层）")
    return errors


def _table_label(index: int, table: Any) -> str:
    name = table.get("name") if isinstance(table, dict) else None
    return f"表 {name}" if _is_text(name) else f"tables[{index}]"


def _check_table(where: str, table: Any, spec: dict[str, Any]) -> list[str]:
    if not isinstance(table, dict):
        return [f"{where} 应为映射（name 加来源定义），实际是 {_show(table)}"]
    errors = _unknown_keys(where, table, _TABLE_KEYS)
    errors += _check_rel_path(where, "name", table.get("name")) if "name" in table else [f"{where}: 缺少 name（数据根相对路径）"]
    errors += _check_shared(where, table, ("freq", "n_codes", "note", "drop_rows", "rows"))
    declared = [s for s in SOURCES if SOURCE_BLOCKS[s] in table]
    if not declared:
        errors.append(f"{where}: 没有写来源，至少要有 sample / borrow / columns（synth）之一")
    source = table.get("source")
    if source is not None and source not in SOURCES:
        errors.append(f"{where}: source 应为 {' / '.join(SOURCES)} 之一，实际是 {_show(source)}")
    elif source is not None and source not in declared:
        errors.append(f"{where}: source 写的是 {source}，但没有对应的 {SOURCE_BLOCKS[source]} 段")
    errors += _check_sample(where, table, spec) if "sample" in table else []
    errors += _check_borrow(where, table, spec) if "borrow" in table else []
    errors += _check_columns(where, table, spec) if "columns" in table else []
    if "drop_rows" in table and "columns" not in table:
        errors.append(f"{where}: drop_rows 只对 synth（columns）起作用")
    name = table.get("name")
    suffix = Path(name).suffix.lower() if _is_text(name) else ""
    if _is_text(name) and suffix not in OUTPUT_SUFFIXES:
        sample = table.get("sample")
        plain_copy = (
            declared == ["sample"] and isinstance(sample, dict) and sample.get("trim") is not True
            and _is_text(sample.get("path")) and bool(suffix) and Path(sample["path"]).suffix.lower() == suffix
        )
        if not plain_copy:
            errors.append(
                f"{where}: name 的后缀 {suffix or '（无）'} 不支持生成，可选 {' / '.join(OUTPUT_SUFFIXES)}"
                "（只有原样拷贝同后缀的样例文件时不限后缀）"
            )
    return errors


def validate_spec(spec: Any) -> list[str]:
    """校验规格，返回错误清单（空表示合法）。每条都指明是哪张表的哪个字段。

    只查规格自身（字段名、取值、列之间的引用），不碰数据文件；源表缺列这类要对着数据才知道
    的问题由 inspect_sources() / generate() 报。
    """
    if not isinstance(spec, dict):
        return [f"顶层: 规格应为映射（键: 值），实际是 {type(spec).__name__}"]
    errors = _unknown_keys("顶层", spec, _TOP_KEYS)
    errors += _check_shared("顶层", spec, ("version", "seed", "freq", "n_codes", "max_rows", "note"))
    tables = spec.get("tables")
    if not isinstance(tables, list) or not tables:
        return errors + ["顶层: tables 应为非空列表（至少要有一张表）"]
    errors += [e for i, table in enumerate(tables) for e in _check_table(_table_label(i, table), table, spec)]
    names = [t["name"] for t in tables if isinstance(t, dict) and _is_text(t.get("name"))]
    return errors + [f"表 {name}: name 重复，每张表只能出现一次" for name in dict.fromkeys(n for n in names if names.count(n) > 1)]


# ---------------------------------------------------------------------------
# 生成：公共部件（日历、代码、随机数、读写）
# ---------------------------------------------------------------------------


@dataclass
class _Context:
    """一次生成用到的环境。cache 存已读过的日历与代码全集。"""

    spec: dict[str, Any]
    data_root: Path
    root: Path
    spec_dir: Optional[Path]
    seed: int
    max_rows: int
    cache: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Built:
    """一张表的生成结果。table 是 pyarrow.Table；原样拷贝样例文件时只有 copy_from。"""

    table: Any = None
    copy_from: Optional[Path] = None
    date_col: Optional[str] = None
    code_col: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    fallbacks: list[dict[str, str]] = field(default_factory=list)


def _tools_module(name: str) -> Any:
    """按需导入 tools 包里的模块（作为脚本直接运行时仓库根不在 sys.path 里）。"""
    repo_root = str(Path(__file__).resolve().parents[1])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return importlib.import_module(f"tools.{name}")


def default_root() -> Path:
    """仓库（工作区）根：用 tools.state.default_root()，支持 REPORT_REPRODUCE_ROOT 环境变量。"""
    try:
        return _tools_module("state").default_root()
    except Exception:  # noqa: BLE001 - state.py 一时导入不了时按同一规则自己算
        override = os.environ.get("REPORT_REPRODUCE_ROOT")
        return Path(override).resolve() if override else Path(__file__).resolve().parents[1]


def resolve_data_root(root: Path) -> Path:
    """数据根目录：与内核体检用同一条规则（工作区的 .reproduce.json，找不到用 ~/local_data）。"""
    return _tools_module("flowlib.datacheck").resolve_data_root(root)


def _now_iso() -> str:
    return datetime.now(TZ_CN).isoformat(timespec="seconds")


def _effective(table: dict[str, Any], spec: dict[str, Any], key: str, default: Any = None) -> Any:
    """表里写了用表的，没写用顶层的，都没写用默认值。"""
    return table.get(key, spec.get(key, default))


def _period(table: dict[str, Any], spec: dict[str, Any]) -> Optional[tuple[Any, Any]]:
    """这张表的区间（两个时间戳，含两端）；哪儿都没写返回 None。"""
    import pandas as pd

    value = _effective(table, spec, "period")
    return None if value is None else (pd.Timestamp(_as_date(value[0])), pd.Timestamp(_as_date(value[1])))


def _span(start: Any, end: Any) -> str:
    return f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d}"


def _rng(seed: int, *parts: str) -> Any:
    """由（种子、表名、列名…）决定的随机数发生器：互不干扰，增删别的列不影响这一列。"""
    import numpy as np

    digest = hashlib.sha256("\x1f".join([str(seed), *parts]).encode("utf-8")).digest()
    return np.random.default_rng(int.from_bytes(digest[:16], "big"))


def _pick_codes(codes: Sequence[str], n: Optional[int], seed: int) -> list[str]:
    """从一组代码里挑 n 个：按（种子, 代码）的哈希排序取前 n 个，再按代码排序返回。

    同一个代码在任何表里的名次都一样，所以各表挑出来的代码互相对得上，n 小的是 n 大的子集。
    """
    ranked = sorted(codes, key=lambda code: (hashlib.sha256(f"{seed}:{code}".encode("utf-8")).hexdigest(), code))
    return sorted(ranked if n is None else ranked[:n])


def _need_columns(source: Any, available: Sequence[str], wanted: Optional[Sequence[str]]) -> None:
    missing = [c for c in wanted or [] if c not in available]
    if missing:
        raise MockDataError(f"{source} 里没有列 {missing}（现有: {_brief(list(available))}）")


def _read_text_frame(path: Path) -> Any:
    """读 csv / xlsx：常见代码列按文本读入；csv 先按 UTF-8 读，不行再按 GB18030。"""
    import pandas as pd

    def text_columns(header: Any) -> dict[str, type]:
        return {c: str for c in header if c in TEXT_CODE_COLUMNS}

    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, dtype=text_columns(pd.read_excel(path, nrows=0).columns))

    def read_csv(encoding: str) -> Any:
        return pd.read_csv(path, dtype=text_columns(pd.read_csv(path, nrows=0, encoding=encoding).columns), encoding=encoding)

    try:
        return read_csv("utf-8-sig")
    except UnicodeDecodeError:
        return read_csv("gb18030")


def _read_frame(path: Path, columns: Optional[Sequence[str]] = None) -> Any:
    """读一个数据文件（parquet / feather / csv / xlsx）成 DataFrame，可只取部分列。"""
    import pandas as pd

    suffix = path.suffix.lower()
    wanted = None if columns is None else list(dict.fromkeys(columns))
    if suffix == ".parquet":
        import pyarrow.parquet as pq

        _need_columns(path, pq.read_schema(path).names, wanted)
        return pd.read_parquet(path, columns=wanted)
    if suffix not in (".feather", ".csv", ".xlsx"):
        raise MockDataError(f"不支持的文件格式 {suffix or '（无后缀）'}: {path}（支持 .parquet / .feather / .csv / .xlsx）")
    frame = pd.read_feather(path) if suffix == ".feather" else _read_text_frame(path)
    _need_columns(path, list(frame.columns), wanted)
    return frame if wanted is None else frame[wanted]


def _read_arrow(path: Path) -> Any:
    """读一个数据文件成 pyarrow.Table。"""
    import pyarrow as pa

    if path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq

        return pq.read_table(path)
    return pa.Table.from_pandas(_read_frame(path), preserve_index=False)


def _to_datetime(values: Any) -> Any:
    """把一列日期（时间戳 / date / 文本 / YYYYMMDD 数值）转成不带时区的时间戳列；认不出来的记为 NaT。"""
    import pandas as pd

    if pd.api.types.is_datetime64_any_dtype(values.dtype):
        return values.dt.tz_localize(None) if values.dt.tz is not None else values
    if isinstance(values.dtype, pd.CategoricalDtype):
        values = values.astype(object)
    unique = pd.Series(pd.unique(values.dropna()))
    if unique.empty:
        return pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    kind = pd.api.types.infer_dtype(unique, skipna=True)
    if kind in ("datetime", "datetime64", "date"):
        parsed = pd.to_datetime(unique, errors="coerce")
    else:
        text = unique.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        compact = text.str.fullmatch(r"\d{8}").to_numpy(dtype=bool)
        parsed = pd.to_datetime(text.where(compact), format="%Y%m%d", errors="coerce")
        if not compact.all() and kind not in ("integer", "floating", "mixed-integer-float", "decimal"):
            parsed = parsed.fillna(pd.to_datetime(text.where(~compact), format="mixed", errors="coerce"))
    return values.map(pd.Series(parsed.to_numpy(), index=unique.to_numpy()))


def _load_calendar(conf: dict[str, Any], ctx: _Context) -> tuple[Any, Optional[str]]:
    """读交易日历，返回（升序去重的日期, None）；取不到返回（None, 原因）。"""
    import pandas as pd

    key = "calendar:" + json.dumps(conf, sort_keys=True, ensure_ascii=False, default=str)
    if key in ctx.cache:
        return ctx.cache[key]
    path = ctx.data_root / conf["file"]
    if not path.is_file():
        result: tuple[Any, Optional[str]] = (None, f"交易日历文件不存在: {path}")
    else:
        date_col = conf.get("date_col", "date")
        available = list(_read_arrow(path).schema.names) if path.suffix.lower() != ".parquet" else _parquet_names(path)
        flag_col = conf.get("flag_col") or (DEFAULT_FLAG_COL if DEFAULT_FLAG_COL in available else None)
        frame = _read_frame(path, [date_col, *([flag_col] if flag_col else [])])
        frame = frame if flag_col is None else frame[frame[flag_col] == 1]
        days = pd.DatetimeIndex(_to_datetime(frame[date_col]).dropna().dt.normalize().unique()).sort_values()
        result = (days, None) if len(days) else (None, f"交易日历 {conf['file']} 里没有可用的日期")
    ctx.cache[key] = result
    return result


def _parquet_names(path: Path) -> list[str]:
    import pyarrow.parquet as pq

    return list(pq.read_schema(path).names)


def _trading_days(table: dict[str, Any], ctx: _Context, start: Any, end: Any) -> tuple[Any, Optional[str]]:
    """[start, end 之后约一个季度] 内的交易日，以及用了兜底时的说明。

    多取一段是为了判断区间末尾是不是周 / 月 / 季的最后一个交易日。真实日历取不到时整段用
    工作日；只覆盖一部分时，超出的部分用工作日补齐。
    """
    import pandas as pd

    conf = table.get("calendar") or ctx.spec.get("calendar") or DEFAULT_CALENDAR
    real, reason = _load_calendar(conf, ctx)
    horizon = end + pd.Timedelta(days=100)
    if real is None:
        return pd.bdate_range(start, horizon), f"交易日历取不到（{reason}），改用工作日日历"
    one_day = pd.Timedelta(days=1)
    before = pd.bdate_range(start, real[0] - one_day) if start < real[0] else real[:0]
    after = pd.bdate_range(real[-1] + one_day, horizon) if horizon > real[-1] else real[:0]
    days = before.append(real[(real >= start) & (real <= horizon)]).append(after)
    short = len(before) > 0 or end > real[-1]
    note = f"交易日历 {conf['file']} 只覆盖 {_span(real[0], real[-1])}，区间里超出的部分用工作日补齐" if short else None
    return days, note


def _freq_ends(days: Any, freq: str) -> Any:
    """每个周 / 月 / 季里的最后一个日期；D 原样返回。"""
    import pandas as pd

    if freq == "D" or len(days) == 0:
        return days
    buckets = days.to_period({"W": "W-SUN", "M": "M", "Q": "Q-DEC"}[freq])
    return pd.DatetimeIndex(pd.Series(days, index=buckets).groupby(level=0).max().to_numpy())


def _natural_dates(start: Any, end: Any, freq: str) -> Any:
    """自然日历上的日期：D 为每一天，W 为每周五，M / Q 为月末 / 季末。"""
    import pandas as pd

    if freq == "D":
        return pd.date_range(start, end, freq="D")
    ends = pd.period_range(start, end, freq={"W": "W-FRI", "M": "M", "Q": "Q-DEC"}[freq]).to_timestamp(how="end").normalize()
    return ends[(ends >= start) & (ends <= end)]


def _target_dates(table: dict[str, Any], ctx: _Context, period: tuple[Any, Any], freq: str, anchor: str) -> tuple[Any, Optional[str]]:
    """目标区间内、给定频率下的日期序列，以及日历用了兜底时的说明。"""
    start, end = period
    if anchor == "natural":
        return _natural_dates(start, end, freq), None
    days, note = _trading_days(table, ctx, start, end)
    ends = _freq_ends(days, freq)
    return ends[(ends >= start) & (ends <= end)], note


def _load_codes(conf: dict[str, Any], ctx: _Context) -> tuple[list[str], Optional[str]]:
    """代码全集（去重、按文本排序）；取不到返回（[], 原因）。"""
    if "list" in conf:
        return sorted({str(code) for code in conf["list"]}), None
    key = "codes:" + json.dumps(conf, sort_keys=True, ensure_ascii=False, default=str)
    if key in ctx.cache:
        return ctx.cache[key]
    path = ctx.data_root / conf["file"]
    if not path.is_file():
        result: tuple[list[str], Optional[str]] = ([], f"代码来源表不存在: {path}")
    else:
        where = conf.get("where") or {}
        frame = _read_frame(path, [conf["column"], *where])
        masks = (frame[col].isin(want) if isinstance(want, list) else frame[col] == want for col, want in where.items())
        keep = functools.reduce(operator.and_, masks, frame[conf["column"]].notna())
        codes = sorted(frame.loc[keep, conf["column"]].astype(str).unique().tolist())
        result = (codes, None) if codes else ([], f"代码来源表 {conf['file']} 按条件筛完没有代码")
    ctx.cache[key] = result
    return result


def _universe(table: dict[str, Any], ctx: _Context, conf: Any, n: int) -> tuple[list[str], Optional[str], Optional[str]]:
    """挑 n 个目标代码，返回（代码, 用了兜底时的说明, 其他说明）。

    conf 为映射时用它指定的来源，否则用本表或顶层的 codes。来源取不到时退回自造代码。
    """
    source = conf if isinstance(conf, dict) else (table.get("codes") or ctx.spec.get("codes") or DEFAULT_CODES)
    universe, reason = _load_codes(source, ctx)
    if not universe:
        return [f"{i:06d}" for i in range(1, n + 1)], f"证券代码取不到（{reason}），改用自造代码 000001 ~ {n:06d}", None
    note = None if len(universe) >= n else f"代码来源只有 {len(universe)} 个代码，不够 {n} 个，全部取用"
    return _pick_codes(universe, n, ctx.seed), None, note


def _normalize_schema(table: Any) -> Any:
    """统一成与本地真实数据一致的类型：文本用 large_string，时间戳用微秒；去掉 pandas 元数据。"""
    import pyarrow as pa

    def unified(arrow_type: Any) -> Any:
        if pa.types.is_string(arrow_type):
            return pa.large_string()
        if pa.types.is_timestamp(arrow_type) and arrow_type.unit != "us":
            return pa.timestamp("us", tz=arrow_type.tz)
        return arrow_type

    schema = pa.schema([pa.field(f.name, unified(f.type)) for f in table.schema])
    return table.replace_schema_metadata(None).cast(schema, safe=False)


def _write_table(table: Any, target: Path) -> None:
    """按后缀把表写成 parquet / feather / csv（都不含时间戳之类会变的内容）。"""
    suffix = target.suffix.lower()
    if suffix == ".parquet":
        import pyarrow.parquet as pq

        pq.write_table(table, target)
    elif suffix == ".feather":
        import pyarrow.feather as feather

        feather.write_feather(table, target)
    else:
        table.to_pandas().to_csv(target, index=False, encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _table_stats(table: Any, date_col: Optional[str], code_col: Optional[str]) -> dict[str, Any]:
    """行数、列名（columns）与各列类型（dtypes）、日期起止、标的数。"""
    import pyarrow.compute as pc

    names = table.schema.names
    stats: dict[str, Any] = {
        "rows": table.num_rows,
        "columns": list(names),
        "dtypes": {f.name: str(f.type) for f in table.schema},
        "date_column": None,
        "date_min": None,
        "date_max": None,
        "code_column": None,
        "n_codes": None,
    }
    if date_col in names and table.num_rows:
        when = _to_datetime(pc.unique(table[date_col]).to_pandas()).dropna()
        if len(when):
            stats.update(date_column=date_col, date_min=f"{when.min():%Y-%m-%d}", date_max=f"{when.max():%Y-%m-%d}")
    if code_col in names:
        stats.update(code_column=code_col, n_codes=pc.count_distinct(table[code_col]).as_py())
    return stats


# ---------------------------------------------------------------------------
# 来源一：sample
# ---------------------------------------------------------------------------


def _sample_path(table: dict[str, Any], ctx: _Context) -> Optional[Path]:
    """样例文件的实际位置：相对路径先按规格文件所在目录找，再按仓库根找；不存在返回 None。"""
    raw = Path(str(table["sample"]["path"])).expanduser()
    bases = [None] if raw.is_absolute() else [base for base in (ctx.spec_dir, ctx.root) if base is not None]
    return next((p for p in (raw if base is None else base / raw for base in bases) if p.is_file()), None)


def _build_sample(table: dict[str, Any], ctx: _Context) -> _Built:
    """样例文件：同后缀且不截取时原样拷贝，否则读入后（截取、）转存。"""
    import pyarrow as pa

    name, conf = table["name"], table["sample"]
    label = f"表 {name}"
    source = _sample_path(table, ctx)
    assert source is not None  # 可用性已由 _resolve_source 确认
    trim = conf.get("trim") is True
    if source.suffix.lower() == Path(name).suffix.lower() and not trim:
        return _Built(copy_from=source, date_col=conf.get("date_col"), code_col=conf.get("code_col"), notes=[f"原样拷贝样例文件 {source}"])
    frame = _read_frame(source)
    names = list(frame.columns)
    _need_columns(f"{label}: 样例文件 {source}", names, [conf[key] for key in ("date_col", "code_col") if key in conf] + list(conf.get("parse_dates") or []))
    if source.suffix.lower() in (".csv", ".xlsx"):
        parse = conf["parse_dates"] if "parse_dates" in conf else [c for c in names if c in DATE_COLUMNS or c == conf.get("date_col")]
        frame = frame.assign(**{c: _to_datetime(frame[c]) for c in parse})
    date_col = conf.get("date_col") or next((c for c in DATE_COLUMNS if c in names), None)
    code_col = conf.get("code_col") or next((c for c in CODE_COLUMNS if c in names), None)
    notes = [f"取自样例文件 {source}"]
    if trim:
        if date_col is None:
            raise MockDataError(f"{label}: sample.trim 需要日期列，样例文件里按常见列名找不到，请写 sample.date_col")
        start, end = _period(table, ctx.spec)
        when = _to_datetime(frame[date_col])
        inside = ((when >= start) & (when <= end)).to_numpy(dtype=bool)
        if not inside.any():
            have = "没有可用的日期" if when.isna().all() else f"日期为 {_span(when.min(), when.max())}"
            raise MockDataError(f"{label}: 样例文件 {source} 在 {_span(start, end)} 内没有数据（样例{have}）")
        notes.append(f"按 {_span(start, end)} 截取，{len(frame)} 行里留下 {int(inside.sum())} 行")
        frame = frame.loc[inside]
    built = _normalize_schema(pa.Table.from_pandas(frame.reset_index(drop=True), preserve_index=False))
    return _Built(table=built, date_col=date_col, code_col=code_col, notes=notes)


# ---------------------------------------------------------------------------
# 来源二：borrow（全程在 pyarrow 里做，列类型与空值原样保留）
# ---------------------------------------------------------------------------


class _DateCodec:
    """一列日期的原生写法与时间戳互转：改完日期后按原来的类型和写法写回去。"""

    def __init__(self, arrow_type: Any, label: str, samples: Sequence[Any]) -> None:
        import pyarrow as pa

        self.type, self.label, self.fmt = arrow_type, label, None
        if pa.types.is_timestamp(arrow_type):
            self.kind = "timestamp"
        elif pa.types.is_date(arrow_type):
            self.kind = "date"
        elif pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
            self.kind = "text"
            texts = [s for s in samples if isinstance(s, str)]
            self.fmt = next((fmt for fmt, pattern in TEXT_DATE_FORMATS if texts and all(re.fullmatch(pattern, s) for s in texts)), None)
        elif pa.types.is_integer(arrow_type):
            self.kind = "int"
            self.fmt = "%Y%m%d" if samples and all(_as_date(s) is not None and len(str(s)) == 8 for s in samples) else None
        else:
            raise MockDataError(f"{label}: 类型 {arrow_type} 不能当日期列用")

    def parse(self, values: Any) -> Any:
        """原生值 → 不带时区的时间戳列（认不出来的为 NaT）。"""
        return _to_datetime(values.to_pandas().reset_index(drop=True))

    def format(self, when: Any) -> Any:
        """时间戳 → 与原列同类型、同写法的 pyarrow 数组。"""
        import pandas as pd
        import pyarrow as pa

        series = pd.Series(when).reset_index(drop=True)
        if self.kind == "timestamp":
            series = series if self.type.tz is None else series.dt.tz_localize(self.type.tz)
            return pa.Array.from_pandas(series, type=self.type, safe=False)
        if self.kind == "date":
            return pa.Array.from_pandas(series.dt.floor("D"), type=pa.timestamp("s")).cast(self.type)
        if self.fmt is None:
            raise MockDataError(
                f"{self.label}: 日期的写法认不出来（认得 2020-01-02 / 20200102 / 2020/01/02 / 2020-01-02 00:00:00），"
                "没法改日期；dates.mode: keep 不受影响"
            )
        text = series.dt.strftime(self.fmt)
        if self.kind == "text":
            return pa.Array.from_pandas(text, type=self.type)
        return pa.Array.from_pandas(pd.to_numeric(text, errors="coerce").astype("Int64"), type=self.type)


def _open_dataset(path: Path) -> Any:
    """把源表打开成 pyarrow 数据集：parquet 按需读，其他格式整表读进内存。"""
    import pyarrow.dataset as ds

    if path.suffix.lower() == ".parquet":
        return ds.dataset(str(path), format="parquet")
    return ds.dataset(_read_arrow(path).replace_schema_metadata(None))


def _plain_type(arrow_type: Any) -> Any:
    import pyarrow as pa

    return arrow_type.value_type if pa.types.is_dictionary(arrow_type) else arrow_type


def _field(schema: Any, column: str) -> Any:
    """过滤表达式里引用一列；字典编码的列先解码。"""
    import pyarrow as pa
    import pyarrow.compute as pc

    arrow_type = schema.field(column).type
    return pc.field(column).cast(arrow_type.value_type) if pa.types.is_dictionary(arrow_type) else pc.field(column)


def _all_of(*filters: Any) -> Any:
    present = [f for f in filters if f is not None]
    return functools.reduce(operator.and_, present) if present else None


def _value_counts(dataset: Any, column: str, flt: Any = None) -> tuple[Any, Any]:
    """一列里互不相同的非空值（升序）和各自的行数。按批扫描，不把整列读进内存。"""
    import numpy as np
    import pyarrow as pa
    import pyarrow.compute as pc

    plain = _plain_type(dataset.schema.field(column).type)
    batches = dataset.to_batches(columns={column: _field(dataset.schema, column)}, filter=flt)
    parts = [pc.value_counts(batch.column(0)) for batch in batches if batch.num_rows]
    if not parts:
        return pa.array([], type=plain), np.array([], dtype="int64")
    pairs = pa.table({"value": pa.concat_arrays([p.field("values") for p in parts]), "rows": pa.concat_arrays([p.field("counts") for p in parts])})
    merged = pairs.group_by("value").aggregate([("rows", "sum")])
    merged = merged.filter(pc.is_valid(merged["value"])).sort_by("value")
    return merged["value"].combine_chunks(), merged["rows_sum"].to_numpy().astype("int64")


def _one_of(field_ref: Any, values: Any) -> Any:
    """「这一列取值在 values 之内」的过滤条件。带上最小、最大值，按行组统计信息能跳过大半文件。"""
    import pyarrow as pa
    import pyarrow.compute as pc

    try:
        bounds = pc.min_max(values)
        return (field_ref >= bounds["min"]) & (field_ref <= bounds["max"]) & field_ref.isin(values)
    except pa.ArrowException:  # 个别类型没有大小比较，退回只用 isin
        return field_ref.isin(values)


def _set_column(table: Any, name: str, values: Any) -> Any:
    index = table.schema.get_field_index(name)
    return table.set_column(index, table.schema.field(index), values)


def _decode_dictionaries(table: Any) -> Any:
    import pyarrow as pa

    schema = pa.schema([pa.field(f.name, _plain_type(f.type), f.nullable) for f in table.schema])
    return table if schema.equals(table.schema.remove_metadata()) else table.cast(schema)


def _shift_dates(days: Any, years: int, months: int, extra_days: int) -> Any:
    """整体平移：先按年、月平移（月末仍对月末），再加天数。"""
    import pandas as pd

    moved = days
    if years or months:
        moved = days + pd.DateOffset(years=years, months=months)
        moved = moved.where(~days.is_month_end, moved + pd.offsets.MonthEnd(0))
    return moved + pd.Timedelta(days=extra_days)


def _borrow_plan(table: dict[str, Any], ctx: _Context) -> dict[str, Any]:
    """打开源表，把规格里引用的列对着源表的实际列核一遍。"""
    name, conf = table["name"], table["borrow"]
    label = f"表 {name}"
    dataset = _open_dataset(ctx.data_root / conf["from"])
    available = list(dataset.schema.names)

    def need(key: str, wanted: Sequence[str], pool: Sequence[str], pool_name: str) -> None:
        missing = [c for c in wanted if c not in pool]
        if missing:
            raise MockDataError(f"{label}: borrow.{key} 里的列 {missing} 不在{pool_name}里（现有: {_brief(list(pool))}）")

    source_name = f"源表 {conf['from']} "
    keep_cols = list(conf.get("columns") or available)
    need("columns", keep_cols, available, source_name)
    rename = dict(conf.get("rename") or {})
    need("rename", list(rename), keep_cols, "截取的列")
    need("shift_cols", list(conf.get("shift_cols") or []), keep_cols, "截取的列")
    need("code_col", [conf["code_col"]] if "code_col" in conf else [], available, source_name)
    need("date_col", [conf["date_col"]] if "date_col" in conf else [], available, source_name)
    out_names = [rename.get(c, c) for c in keep_cols]
    clash = list(dict.fromkeys(n for n in out_names if out_names.count(n) > 1))
    if clash:
        raise MockDataError(f"{label}: borrow.rename 之后列名 {clash} 重复")
    return {
        "dataset": dataset,
        "keep_cols": keep_cols,
        "out_names": out_names,
        "rename": rename,
        "code_col": conf.get("code_col") or next((c for c in CODE_COLUMNS if c in available), None),
        "date_col": conf.get("date_col") or next((c for c in DATE_COLUMNS if c in available), None),
    }


def _remap_dates(raw: Any, date_col: str, segment: tuple[Any, Any, Any], shift_cols: Sequence[str], label: str) -> Any:
    """按一段「源日期 → 目标日期」的对照改写主日期列，其余日期列按同一行的差值一起挪。"""
    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc

    source_days, target_days, delta = segment
    position = pc.index_in(raw[date_col], value_set=source_days)
    hit = pc.is_valid(position)
    part = raw.filter(hit)
    rows = position.filter(hit).to_numpy().astype("int64")
    part = _set_column(part, date_col, target_days.take(pa.array(rows)))
    row_delta = pd.to_timedelta(delta[rows])

    def moved(column: str) -> Any:
        values = part[column]
        codec = _DateCodec(values.type, f"{label}: shift_cols 里的 {column}", pc.unique(values).slice(0, 5000).to_pylist())
        return codec.format(codec.parse(values) + row_delta)

    return functools.reduce(lambda acc, column: _set_column(acc, column, moved(column)), shift_cols, part)


def _borrow_dates(table: dict[str, Any], ctx: _Context, plan: dict[str, Any], built: _Built) -> tuple[Any, Optional[list[tuple[Any, Any, Any]]]]:
    """决定读源表的哪些日期、各自改成什么。

    返回（按日期筛源表的过滤条件, 改日期的对照段）。对照段为 None 表示日期不动；resample 铺满
    时有多段，每段是（源日期的原生值, 目标日期的原生值, 目标减源的时间差）。
    """
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc

    name, conf = table["name"], table["borrow"]
    label = f"表 {name}"
    dataset, date_col = plan["dataset"], plan["date_col"]
    dates = _dates_conf(conf)
    mode = dates.get("mode", "keep")
    period = _period(table, ctx.spec)
    freq = _effective(table, ctx.spec, "freq", DEFAULT_FREQ)
    if date_col is None:
        if mode != "keep":
            raise MockDataError(f"{label}: borrow.dates.mode 为 {mode} 需要日期列，源表 {conf['from']} 里按常见列名找不到，请写 borrow.date_col")
        if "period" in table:
            built.notes.append("源表没有日期列，period 不起作用")
        return None, None
    if mode == "keep" and period is None and freq == "D":
        return None, None  # 既不截取也不降频：整张表原样借，不用看日期

    native, native_rows = _value_counts(dataset, date_col)
    codec = _DateCodec(native.type, f"{label}: 日期列 {date_col}", native.to_pylist())
    parsed = codec.parse(native)
    valid = parsed.notna().to_numpy(dtype=bool)
    order = np.argsort(parsed.to_numpy()[valid], kind="stable")
    source_native = native.filter(pa.array(valid)).take(pa.array(order))
    source_days = pd.DatetimeIndex(parsed.to_numpy()[valid][order])
    source_rows = native_rows[valid][order]
    if len(source_days) == 0:
        raise MockDataError(f"{label}: 源表 {conf['from']} 的日期列 {date_col} 里没有认得出的日期")
    covered = _span(source_days[0], source_days[-1])
    wanted = "目标区间内" if period is None else f"目标区间 {_span(*period)} 内"
    field_ref = _field(dataset.schema, date_col)

    def within(days: Any, bounds: Optional[tuple[Any, Any]]) -> Any:
        return np.ones(len(days), dtype=bool) if bounds is None else np.asarray((days >= bounds[0]) & (days <= bounds[1]))

    def at_freq(days: Any, chosen: Any) -> Any:
        return chosen & np.asarray(days.isin(_freq_ends(days[chosen], freq)))

    if mode == "keep":
        chosen = at_freq(source_days, within(source_days, period))
        if not chosen.any():
            raise MockDataError(f"{label}: 源表 {conf['from']} 在{wanted}没有数据（源表日期 {covered}）；可改用 borrow.dates.mode: shift 或 resample")
        built.notes.append(f"源表日期 {covered}，取用 {_span(source_days[chosen][0], source_days[chosen][-1])} 共 {int(chosen.sum())} 个日期，日期不动")
        untouched = chosen.all() and valid.all()
        return (None if untouched else _one_of(field_ref, source_native.filter(pa.array(chosen)))), None

    if mode == "shift":
        moved = _shift_dates(source_days, dates.get("years", 0), dates.get("months", 0), dates.get("days", 0))
        chosen = at_freq(moved, within(moved, period))
        if not chosen.any():
            raise MockDataError(f"{label}: 源表 {conf['from']} 平移后的日期是 {_span(moved[0], moved[-1])}，在{wanted}没有数据")
        picked = source_native.filter(pa.array(chosen))
        built.notes.append(f"源表日期 {covered}，整体平移后取用 {_span(moved[chosen][0], moved[chosen][-1])} 共 {int(chosen.sum())} 个日期")
        return _one_of(field_ref, picked), [(picked, codec.format(moved[chosen]), (moved[chosen] - source_days[chosen]).to_numpy())]

    source_period = dates.get("source_period")
    bounds = None if source_period is None else (pd.Timestamp(_as_date(source_period[0])), pd.Timestamp(_as_date(source_period[1])))
    candidates = within(source_days, bounds)
    if not candidates.any():
        raise MockDataError(f"{label}: 源表 {conf['from']} 在 borrow.dates.source_period 内没有数据（源表日期 {covered}）")
    # 截面太稀的日期（行数不到峰值的一成）不拿来铺：真实表常有早年只有零星几个标的的情况
    coverage = dates.get("min_coverage", DEFAULT_MIN_COVERAGE)
    dense = source_rows >= coverage * source_rows[candidates].max()
    sparse = int((candidates & ~dense).sum())
    if sparse:
        built.notes.append(f"源表有 {sparse} 个日期的行数不到峰值的 {coverage:.0%}（截面太稀），没有取用")
    pool = at_freq(source_days, candidates & dense)
    pool_native, pool_days = source_native.filter(pa.array(pool)), source_days[pool]
    targets, calendar_note = _target_dates(table, ctx, period, freq, dates.get("anchor", "trading"))
    if calendar_note:
        built.fallbacks.append({"kind": "calendar", "detail": calendar_note})
    if len(targets) == 0:
        raise MockDataError(f"{label}: {wanted}没有 {freq} 频率的日期")
    # 从末尾对齐：最后一个目标日期对源表最后一个日期；源表不够长就往前循环
    offset = np.arange(len(targets)) - len(targets)
    position, tile = offset % len(pool_days), offset // len(pool_days)
    tiles = np.unique(tile)
    segments = [
        (
            pool_native.take(pa.array(position[tile == k])),
            codec.format(targets[tile == k]),
            (targets[tile == k] - pool_days[position[tile == k]]).to_numpy(),
        )
        for k in tiles
    ]
    used = pool_days[np.unique(position)]
    built.notes.append(f"源表日期 {covered}，取 {_span(used[0], used[-1])} 的 {len(used)} 个日期，依次对到 {_span(targets[0], targets[-1])} 的 {len(targets)} 个日期上")
    if len(tiles) > 1:
        built.notes.append(f"源表只有 {len(pool_days)} 个可用日期，不够 {len(targets)} 个，已循环铺满 {len(tiles)} 遍（接缝处的数值不连续）")
    return _one_of(field_ref, pc.unique(pa.concat_arrays([segment[0] for segment in segments]))), segments


def _cast_codes(codes: Sequence[str], arrow_type: Any, label: str) -> Any:
    """把目标代码转成与源表代码列相同的类型。"""
    import pyarrow as pa

    try:
        return pa.array([int(c) for c in codes] if pa.types.is_integer(arrow_type) else list(codes), type=arrow_type)
    except (ValueError, pa.ArrowException) as exc:
        raise MockDataError(f"{label}: 目标代码（形如 {list(codes)[:3]}）转不成源表代码列的类型 {arrow_type}") from exc


def _borrow_codes(table: dict[str, Any], ctx: _Context, plan: dict[str, Any], built: _Built, date_filter: Any) -> tuple[Any, Optional[tuple[Any, Any]]]:
    """决定取源表的哪些代码、各自改成什么。返回（按代码筛源表的过滤条件, (原代码, 新代码) 对照）。"""
    import pyarrow as pa

    name, conf = table["name"], table["borrow"]
    label = f"表 {name}"
    dataset, code_col = plan["dataset"], plan["code_col"]
    codes_conf = conf.get("codes") or {}
    n_codes = _effective(table, ctx.spec, "n_codes")
    if code_col is None:
        if codes_conf:
            raise MockDataError(f"{label}: 写了 borrow.codes，但源表 {conf['from']} 里按常见列名找不到代码列，请写 borrow.code_col")
        if "n_codes" in table:
            built.notes.append("源表没有代码列，n_codes 不起作用")
        return None, None
    if not codes_conf and n_codes is None:
        return None, None

    present = _value_counts(dataset, code_col, date_filter)[0]
    texts = [str(v) for v in present.to_pylist()]
    scope = "源表" if date_filter is None else "源表在取用的日期内"
    if not texts:
        raise MockDataError(f"{label}: {scope}没有任何代码（{conf['from']} 的 {code_col} 列）")
    mapping = {str(k): str(v) for k, v in (codes_conf.get("map") or {}).items()}
    pool = texts
    if mapping:
        mapped = [c for c in texts if c in mapping]
        if not mapped:
            raise MockDataError(f"{label}: borrow.codes.map 的键没有一个出现在源表的代码列 {code_col} 里（源表代码形如 {texts[:3]}）")
        pool = mapped if codes_conf.get("drop_unmapped") else texts
    chosen = _pick_codes(pool, n_codes, ctx.seed)
    targets: Optional[list[str]] = None
    if "replace" in codes_conf:
        universe, fallback, note = _universe(table, ctx, codes_conf["replace"], len(chosen))
        built.fallbacks += [{"kind": "codes", "detail": fallback}] if fallback else []
        if len(universe) < len(chosen):
            built.notes.append(f"目标代码只有 {len(universe)} 个，源表的代码也只取 {len(universe)} 个")
            chosen = _pick_codes(chosen, len(universe), ctx.seed)
        targets = universe[: len(chosen)]
    elif mapping:
        targets = [mapping.get(c, c) for c in chosen]
    index = {text: i for i, text in enumerate(texts)}
    chosen_native = present.take(pa.array([index[c] for c in chosen], type=pa.int64()))
    code_filter = _field(dataset.schema, code_col).isin(chosen_native) if len(chosen) < len(texts) else None
    built.notes.append(f"{scope}有 {len(texts)} 个代码，取用 {len(chosen)} 个" + ("" if targets is None else "并改键"))
    code_map = None if targets is None or targets == chosen else (chosen_native, _cast_codes(targets, present.type, label))
    return code_filter, code_map


def _build_borrow(table: dict[str, Any], ctx: _Context) -> _Built:
    """借一张真实表：筛日期与代码 → 改日期 → 改键 → 截取列、重命名。数值与空值原样保留。"""
    import pyarrow as pa
    import pyarrow.compute as pc

    name, conf = table["name"], table["borrow"]
    label = f"表 {name}"
    plan = _borrow_plan(table, ctx)
    dataset, keep_cols, date_col, code_col = plan["dataset"], plan["keep_cols"], plan["date_col"], plan["code_col"]
    built = _Built()
    date_filter, segments = _borrow_dates(table, ctx, plan, built)
    code_filter, code_map = _borrow_codes(table, ctx, plan, built, date_filter)

    row_filter = _all_of(date_filter, code_filter)
    expected = dataset.count_rows(filter=row_filter) * max(1, len(segments or []))
    if expected > ctx.max_rows:
        raise MockDataError(f"{label}: 预计 {expected} 行，超过上限 {ctx.max_rows}（减小 n_codes 或 period，或调大顶层的 max_rows）")
    read_cols = list(dict.fromkeys([*keep_cols, *(c for c in (date_col, code_col) if c is not None)]))
    raw = _decode_dictionaries(dataset.to_table(columns=read_cols, filter=row_filter, use_threads=False))

    out = raw
    if segments is not None:
        temporal = [f.name for f in raw.schema if f.name != date_col and f.name in keep_cols and (pa.types.is_timestamp(f.type) or pa.types.is_date(f.type))]
        shift_cols = list(conf["shift_cols"]) if "shift_cols" in conf else temporal
        out = pa.concat_tables([_remap_dates(raw, date_col, segment, [c for c in shift_cols if c != date_col], label) for segment in segments])
        if shift_cols:
            built.notes.append(f"跟着主日期列 {date_col} 一起挪的日期列: {', '.join(shift_cols)}")
        planned, landed = sum(len(segment[1]) for segment in segments), pc.count_distinct(out[date_col]).as_py()
        if landed < planned and _dates_conf(conf).get("mode") == "resample":
            built.notes.append(f"目标区间要 {planned} 个日期，生成的表里只有 {landed} 个日期有数据（取用的代码在其余的源日期上没有行）")
    if out.num_rows == 0:
        raise MockDataError(f"{label}: 从源表 {conf['from']} 借出来是空表")
    if code_map is not None:
        position = pc.index_in(out[code_col], value_set=code_map[0])
        out = _set_column(out, code_col, pc.if_else(pc.is_valid(position), pc.take(code_map[1], position), out[code_col]))
    rename = plan["rename"]
    built.table = out.select(keep_cols).rename_columns(plan["out_names"]).replace_schema_metadata(None)
    built.date_col = rename.get(date_col, date_col) if date_col in keep_cols else None
    built.code_col = rename.get(code_col, code_col) if code_col in keep_cols else None
    return built


# ---------------------------------------------------------------------------
# 来源三：synth
# ---------------------------------------------------------------------------


@dataclass
class _Grid:
    """synth 的行骨架：n_dates × n_codes，按「日期在外、代码在内」排成行。"""

    n_dates: int
    n_codes: int
    dates: Any  # 每行的日期（没有 date 列时为 None）
    codes: Any  # 每行的代码（没有 code 列时为 None）

    @property
    def rows(self) -> int:
        return self.n_dates * self.n_codes

    @property
    def shape(self) -> tuple[int, int]:
        return (self.n_dates, self.n_codes)


def _per(column: dict[str, Any], grid: _Grid, draw: Callable[[int], Any], default: str = "row") -> Any:
    """按 per 抽样：row 每行抽一个，code 每个代码抽一个再铺到各个日期上。"""
    import numpy as np

    return np.tile(draw(grid.n_codes), grid.n_dates) if column.get("per", default) == "code" else draw(grid.rows)


def _date_repr(when: Any, column: dict[str, Any]) -> Any:
    """日期列的输出写法：时间戳（默认）、文本或 YYYYMMDD 整数。"""
    import pandas as pd

    series = pd.Series(when)
    dtype = column.get("dtype", "datetime")
    if dtype == "str":
        return series.dt.strftime(column.get("format", "%Y-%m-%d"))
    return series.dt.strftime("%Y%m%d").astype("int64") if dtype == "int" else series.astype("datetime64[us]")


def _gen_price(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    """价格：几何随机游走，恒为正；写了 base 时由那一列派生出开高低、昨收、均价。"""
    import numpy as np

    digits = int(column.get("round", 2))
    tick, scale = 10.0 ** -digits, 10.0 ** digits
    if "base" not in column:
        start = column.get("start", [5, 50])
        low, high = (start, start) if _is_num(start) else start
        level = np.exp(rng.uniform(np.log(low), np.log(high), size=grid.n_codes))
        steps = rng.normal(column.get("drift", 0.0002), column.get("vol", 0.02), size=grid.shape)
        steps[0] = 0.0
        walk = level * np.exp(np.clip(np.cumsum(steps, axis=0), -30.0, 30.0))
        return np.maximum(np.round(walk, digits), tick).reshape(-1)
    base = np.asarray(done[column["base"]], dtype=float).reshape(grid.shape)
    prev = np.vstack([base[:1], base[:-1]])
    upper, lower = np.maximum(base, prev), np.minimum(base, prev)
    role, spread = column["role"], column.get("spread", 0.01)
    if role == "prev_close":
        out = prev
    elif role in ("open", "vwap"):
        out = np.clip(np.round(lower + rng.random(grid.shape) * (upper - lower), digits), lower, upper)
    elif role == "high":
        out = np.maximum(np.ceil(upper * np.exp(np.abs(rng.normal(0.0, spread, size=grid.shape))) * scale) / scale, upper)
    else:
        out = np.maximum(np.minimum(np.floor(lower * np.exp(-np.abs(rng.normal(0.0, spread, size=grid.shape))) * scale) / scale, lower), tick)
    return out.reshape(-1)


def _gen_return(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    import numpy as np

    scale = 100.0 if column.get("unit", "decimal") == "percent" else 1.0
    if "of" not in column:
        return rng.normal(column.get("mean", 0.0), column.get("std", 0.02), size=grid.rows) * scale
    base = np.asarray(done[column["of"]], dtype=float).reshape(grid.shape)
    out = np.full(grid.shape, np.nan)
    out[1:] = base[1:] / base[:-1] - 1.0
    return (out * scale).reshape(-1)


def _gen_volume(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    """成交量 / 成交额：对数正态，非负；每个代码有自己的量级。"""
    import numpy as np

    amount = column["kind"] == "amount"
    typical = column.get("median", 1e8 if amount else 1e6) * np.exp(rng.normal(0.0, 0.8, size=grid.n_codes))
    out = np.round(typical * np.exp(rng.normal(0.0, column.get("sigma", 0.6), size=grid.shape)), int(column.get("round", 2 if amount else 0)))
    return np.where(rng.random(grid.shape) < column.get("zero_rate", 0.0), 0.0, out).reshape(-1)


def _gen_ratio(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    import numpy as np

    low, high = column.get("low"), column.get("high")
    if column.get("dist", "uniform") == "normal":
        out = rng.normal(column.get("mean", 0.0), column.get("std", 1.0), size=grid.rows)
        return out if low is None and high is None else np.clip(out, low, high)
    return rng.uniform(0.0 if low is None else low, 1.0 if high is None else high, size=grid.rows)


def _gen_count(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    if "low" in column or "high" in column:
        low = column.get("low", 0)
        return rng.integers(low, column.get("high", low + 10) + 1, size=grid.rows).astype("int64")
    return rng.poisson(column.get("mean", 5), size=grid.rows).astype("int64")


def _gen_category(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    import numpy as np

    values = np.array(column["values"], dtype=object)
    weights = column.get("weights")
    chance = None if weights is None else np.asarray(weights, dtype=float) / float(sum(weights))
    return _per(column, grid, lambda n: values[rng.choice(len(values), size=n, p=chance)])


def _gen_flag(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    return _per(column, grid, lambda n: (rng.random(n) < column.get("rate", 0.1)).astype("int64"))


def _gen_text(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    import numpy as np

    letters = np.array(list("abcdefghijklmnopqrstuvwxyz0123456789"))
    length, prefix = int(column.get("length", 8)), column.get("prefix", "")

    def draw(n: int) -> Any:
        words = letters[rng.integers(0, len(letters), size=(n, length))].view(f"<U{length}").reshape(-1)
        return np.char.add(prefix, words).astype(object)

    return _per(column, grid, draw, default="code" if grid.codes is not None else "row")


def _gen_publ_date(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    """披露日：报告期（表里的 date 列）之后若干天。"""
    lag = column.get("lag_days", [15, 90])
    low, high = (lag, lag) if _is_int(lag) else lag
    return _date_repr(grid.dates + rng.integers(low, high + 1, size=grid.rows).astype("timedelta64[D]"), column)


def _gen_value(column: dict[str, Any], grid: _Grid, rng: Any, done: dict[str, Any]) -> Any:
    import numpy as np

    mean, std = column.get("mean", 0.0), column.get("std", 1.0)
    if column.get("walk"):
        out = (mean + np.cumsum(rng.normal(0.0, std, size=grid.shape), axis=0)).reshape(-1)
    else:
        out = _per(column, grid, lambda n: rng.normal(mean, std, size=n))
    low, high = column.get("low"), column.get("high")
    return out if low is None and high is None else np.clip(out, low, high)


_GENERATORS: dict[str, Callable[[dict[str, Any], _Grid, Any, dict[str, Any]], Any]] = {
    "date": lambda column, grid, rng, done: _date_repr(grid.dates, column),
    "code": lambda column, grid, rng, done: grid.codes,
    "price": _gen_price,
    "return": _gen_return,
    "volume": _gen_volume,
    "amount": _gen_volume,
    "ratio": _gen_ratio,
    "count": _gen_count,
    "category": _gen_category,
    "flag": _gen_flag,
    "text": _gen_text,
    "publ_date": _gen_publ_date,
    "value": _gen_value,
}


def _with_missing(values: Any, column: dict[str, Any], rng: Any) -> Any:
    """按缺失率把一部分值置空（整数列改用可空整数，保住整数类型）。"""
    import pandas as pd

    series = pd.Series(values).reset_index(drop=True)
    rate = column.get("missing", 0)
    if not rate:
        return series
    series = series.astype("Int64") if pd.api.types.is_integer_dtype(series.dtype) else series
    return series.mask(rng.random(len(series)) < rate)


def _build_synth(table: dict[str, Any], ctx: _Context) -> _Built:
    """按字段类别随机生成：先搭「日期 × 代码」骨架，再逐列生成，最后置空、丢行。"""
    import numpy as np
    import pandas as pd
    import pyarrow as pa

    name, columns = table["name"], table["columns"]
    label = f"表 {name}"
    built = _Built()
    date_def = next((c for c in columns if c["kind"] == "date"), None)
    code_def = next((c for c in columns if c["kind"] == "code"), None)
    days, codes = None, None
    if date_def is not None:
        period = _period(table, ctx.spec)
        freq = _effective(table, ctx.spec, "freq", DEFAULT_FREQ)
        days, calendar_note = _target_dates(table, ctx, period, freq, date_def.get("anchor", "trading"))
        built.fallbacks += [{"kind": "calendar", "detail": calendar_note}] if calendar_note else []
        if len(days) == 0:
            raise MockDataError(f"{label}: 区间 {_span(*period)} 内没有 {freq} 频率的日期")
    if code_def is not None:
        codes, fallback, note = _universe(table, ctx, None, _effective(table, ctx.spec, "n_codes", DEFAULT_N_CODES))
        built.fallbacks += [{"kind": "codes", "detail": fallback}] if fallback else []
        built.notes += [note] if note else []
    n_dates = len(days) if days is not None else (1 if codes is not None else int(table["rows"]))
    n_codes = len(codes) if codes is not None else 1
    if n_dates * n_codes > ctx.max_rows:
        raise MockDataError(f"{label}: 预计 {n_dates} 个日期 × {n_codes} 个代码 = {n_dates * n_codes} 行，超过上限 {ctx.max_rows}（减小 n_codes 或 period，或调大顶层的 max_rows）")
    grid = _Grid(
        n_dates=n_dates,
        n_codes=n_codes,
        dates=None if days is None else np.repeat(days.to_numpy(), n_codes),
        codes=None if codes is None else np.tile(np.array(codes, dtype=object), n_dates),
    )
    # 派生列（由别的 price 列算出）排在后面生成；置空放到最后，派生时用的是完整的底稿
    derived = [c for c in columns if "base" in c and c["kind"] == "price" or "of" in c]
    done: dict[str, Any] = {}
    for column in [c for c in columns if c not in derived] + derived:
        done[column["name"]] = _GENERATORS[column["kind"]](column, grid, _rng(ctx.seed, name, column["name"]), done)
    frame = pd.DataFrame({c["name"]: _with_missing(done[c["name"]], c, _rng(ctx.seed, name, c["name"], "missing")) for c in columns})
    drop = table.get("drop_rows", 0)
    if drop:
        frame = frame.loc[_rng(ctx.seed, name, "drop_rows").random(len(frame)) >= drop].reset_index(drop=True)
    built.table = _normalize_schema(pa.Table.from_pandas(frame, preserve_index=False))
    built.date_col = None if date_def is None else date_def["name"]
    built.code_col = None if code_def is None else code_def["name"]
    return built


# ---------------------------------------------------------------------------
# 生成：选来源、写文件、出清单
# ---------------------------------------------------------------------------

_BUILDERS: dict[str, Callable[[dict[str, Any], _Context], _Built]] = {"sample": _build_sample, "borrow": _build_borrow, "synth": _build_synth}


def _unavailable(source: str, table: dict[str, Any], ctx: _Context) -> Optional[str]:
    """这种来源现在用不了的原因；能用返回 None。"""
    if source == "sample" and _sample_path(table, ctx) is None:
        return f"样例文件不存在: {table['sample']['path']}"
    if source == "borrow" and not (ctx.data_root / table["borrow"]["from"]).is_file():
        return f"源表不存在: {ctx.data_root / table['borrow']['from']}"
    return None


def _with_table(name: str, exc: MockDataError) -> MockDataError:
    """报错里还没有表名的（读日历、读代码表时抛出来的），补上是哪张表。"""
    return exc if str(exc).startswith(f"表 {name}") else MockDataError(f"表 {name}: {exc}")


def _resolve_source(table: dict[str, Any], ctx: _Context) -> tuple[str, list[dict[str, str]]]:
    """按 sample → borrow → synth 的优先级取第一个可用的来源；写了 source 就只认那一种。"""
    candidates = [table["source"]] if table.get("source") else [s for s in SOURCES if SOURCE_BLOCKS[s] in table]
    reasons = [(source, _unavailable(source, table, ctx)) for source in candidates]
    usable = next((source for source, reason in reasons if reason is None), None)
    if usable is None:
        raise MockDataError(f"表 {table['name']}: 没有可用的来源（" + "；".join(f"{s} 的{reason}" for s, reason in reasons) + "）")
    skipped = reasons[: candidates.index(usable)]
    return usable, [{"kind": "source", "detail": f"{source} 的{reason}，退回 {usable}"} for source, reason in skipped]


def _make_context(spec: dict[str, Any], data_root: Path, root: Optional[Path], spec_path: Optional[Path]) -> _Context:
    return _Context(
        spec=spec,
        data_root=Path(data_root).expanduser(),
        root=Path(root) if root is not None else default_root(),
        spec_dir=None if spec_path is None else Path(spec_path).resolve().parent,
        seed=int(spec.get("seed", DEFAULT_SEED)),
        max_rows=int(spec.get("max_rows", DEFAULT_MAX_ROWS)),
    )


def inspect_sources(spec: dict[str, Any], data_root: Path, root: Optional[Path] = None, spec_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """不生成，只看每张表会用哪种来源、退回了什么，并把 borrow 引用的列对着源表核一遍。

    返回每张表一项：{name, source, fallbacks, errors}。规格不合法时抛 MockSpecError。
    """
    errors = validate_spec(spec)
    if errors:
        raise MockSpecError(errors)
    ctx = _make_context(spec, data_root, root, spec_path)

    def inspect(table: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {"name": table["name"], "source": None, "fallbacks": [], "errors": []}
        try:
            source, skipped = _resolve_source(table, ctx)
            entry.update(source=source, fallbacks=skipped)
            if source == "borrow":
                _borrow_plan(table, ctx)
        except MockDataError as exc:
            entry["errors"].append(str(_with_table(table["name"], exc)))
        return entry

    return [inspect(table) for table in spec["tables"]]


def _build_table(table: dict[str, Any], ctx: _Context, staging: Path) -> dict[str, Any]:
    """生成一张表到暂存目录，返回它在 manifest 里的那一项。"""
    name = table["name"]
    source, skipped = _resolve_source(table, ctx)
    try:
        built = _BUILDERS[source](table, ctx)
        target = staging / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if built.copy_from is not None:
            shutil.copyfile(built.copy_from, target)
            try:
                content = _read_arrow(target)
            except Exception:  # noqa: BLE001 - 原样拷贝的文件读不懂时，清单里只记大小和哈希
                content = None
        else:
            _write_table(built.table, target)
            content = built.table
    except MockDataError as exc:
        raise _with_table(name, exc) from exc
    except Exception as exc:  # noqa: BLE001 - 读写与类型转换里的各种失败，统一带上表名报出去
        raise MockDataError(f"表 {name}: 用 {source} 生成失败: {type(exc).__name__}: {exc}") from exc
    if content is None:
        stats: dict[str, Any] = {"rows": None, "columns": [], "dtypes": {}}
    else:
        names = content.schema.names
        stats = _table_stats(
            content,
            built.date_col or next((c for c in DATE_COLUMNS if c in names), None),
            built.code_col or next((c for c in CODE_COLUMNS if c in names), None),
        )
    return {
        "name": name,
        "source": source,
        **stats,
        "size": target.stat().st_size,
        "sha256": _sha256(target),
        "fallbacks": skipped + built.fallbacks,
        "notes": built.notes,
    }


def _case_layout(out_dir: Path) -> tuple[Optional[Path], Optional[str]]:
    """输出目录是常规的 <根>/workspace/<report_id>/data_mock/files 时，返回（根, report_id）；不是返回两个 None。"""
    parts = out_dir.parts
    if len(parts) > 4 and parts[-1] == FILES_DIR and parts[-2] == MOCK_DIR and parts[-4] == "workspace":
        return out_dir.parents[3], parts[-3]
    return None, None


def _previous_tables(manifest_path: Path, out_dir: Path) -> list[str]:
    """上一次生成到同一个输出目录的表名（用来清掉这次规格里已经没有的旧文件）。"""
    try:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(old, dict) or old.get("out_dir") != str(out_dir):
        return []
    names = [t.get("name") for t in old.get("tables") or [] if isinstance(t, dict)]
    return [n for n in names if _is_text(n) and not Path(n).is_absolute() and ".." not in Path(n).parts]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def generate(
    spec: dict[str, Any],
    out_dir: Path,
    data_root: Path,
    *,
    root: Optional[Path] = None,
    spec_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    report_id: Optional[str] = None,
) -> dict[str, Any]:
    """按规格生成全部表，返回 manifest 字典（同时写到 manifest_path）。

    全部表先生成到暂存目录，都成功了才搬进 out_dir；任何一张失败，out_dir 保持原样。上一次
    生成过、这次规格里已经没有的表会从 out_dir 删掉，免得旧的 mock 文件继续盖住真实数据。

    Args:
        spec: 规格（load_spec 的返回）。
        out_dir: 覆盖目录，通常是 workspace/<report_id>/data_mock/files。
        data_root: 数据根目录；只读，日历、代码、被借的表都从这里取。
        root: 仓库根，用来找样例文件；不给时按 out_dir 的常规布局
            （<根>/workspace/<report_id>/data_mock/files）推出，推不出用 default_root()。
        spec_path: 规格文件的位置；样例文件的相对路径先按它所在的目录找。不给时，out_dir
            的上一级里有 spec.yaml 就按那个目录找。
        manifest_path: 清单写到哪里；默认是 out_dir 同级的 manifest.json。
        report_id: 写进清单，仅作标识；不给时按 out_dir 的常规布局推出。

    Raises:
        MockSpecError: 规格不合法。
        MockDataError: 对着实际数据生成不出来，或输出目录与数据根重叠。
    """
    errors = validate_spec(spec)
    if errors:
        raise MockSpecError(errors)
    out_dir = Path(out_dir).expanduser().resolve()
    layout_root, layout_id = _case_layout(out_dir)
    ctx = _make_context(spec, data_root, root if root is not None else layout_root, spec_path)
    if ctx.spec_dir is None and (out_dir.parent / SPEC_NAME).is_file():
        ctx.spec_dir = out_dir.parent
    report_id = report_id if report_id is not None else layout_id
    real_root = ctx.data_root.resolve()
    if out_dir == real_root or real_root in out_dir.parents or out_dir in real_root.parents:
        raise MockDataError(f"输出目录 {out_dir} 与数据根 {real_root} 重叠：mock 文件不能写进真实数据目录")
    manifest_path = Path(manifest_path) if manifest_path is not None else out_dir.parent / MANIFEST_NAME
    stale = [n for n in _previous_tables(manifest_path, out_dir) if n not in {t["name"] for t in spec["tables"]}]

    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".mock_staging_", dir=out_dir.parent))
    try:
        entries = [_build_table(table, ctx, staging) for table in spec["tables"]]
        for entry in entries:
            target = out_dir / entry["name"]
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / entry["name"], target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    removed = [n for n in stale if (out_dir / n).is_file()]
    for name in removed:
        (out_dir / name).unlink()

    manifest = {
        "version": SPEC_VERSION,
        "report_id": report_id,
        "generated_at": _now_iso(),
        "seed": ctx.seed,
        "spec_path": None if spec_path is None else str(Path(spec_path).resolve()),
        "spec_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest(),
        "data_root": str(real_root),
        "out_dir": str(out_dir),
        "tables": entries,
        "removed": removed,
        "fallbacks": [{"table": e["name"], **item} for e in entries for item in e["fallbacks"]],
    }
    _write_json(manifest_path, manifest)
    return manifest


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    """（仓库根, 规格文件, 输出目录, 数据根）：没给的按默认位置取。"""
    root = default_root()
    mock_dir = root / "workspace" / args.report_id / MOCK_DIR
    spec_path = Path(args.spec).expanduser() if args.spec else mock_dir / SPEC_NAME
    out_dir = Path(args.out).expanduser() if getattr(args, "out", None) else mock_dir / FILES_DIR
    data_root = Path(args.data_root).expanduser() if args.data_root else resolve_data_root(root)
    return root, spec_path, out_dir, data_root


def _describe(entry: dict[str, Any]) -> str:
    span = f"{entry['date_min']} ~ {entry['date_max']}" if entry.get("date_min") else "无日期列"
    codes = f"{entry['n_codes']} 个标的" if entry.get("n_codes") is not None else "无代码列"
    return f"  {entry['name']}: {entry['source']}，{entry['rows']} 行，{span}，{codes}"


def cmd_check(args: argparse.Namespace) -> int:
    root, spec_path, _out_dir, data_root = _paths(args)
    spec = load_spec(spec_path)
    plans = inspect_sources(spec, data_root, root=root, spec_path=spec_path)
    failures = [error for plan in plans for error in plan["errors"]]
    for error in failures:
        print(f"规格错误: {error}", file=sys.stderr)
    if failures:
        return 1
    print(f"规格合法: {spec_path}，共 {len(plans)} 张表（数据根 {data_root}）")
    for plan in plans:
        print(f"  {plan['name']}: 将用 {plan['source']}")
        for item in plan["fallbacks"]:
            print(f"    兜底: {item['detail']}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    root, spec_path, out_dir, data_root = _paths(args)
    spec = load_spec(spec_path)
    manifest = generate(spec, out_dir, data_root, root=root, spec_path=spec_path, report_id=args.report_id)
    print(f"已生成 {len(manifest['tables'])} 张表 → {manifest['out_dir']}")
    for entry in manifest["tables"]:
        print(_describe(entry))
        for item in entry["fallbacks"]:
            print(f"    兜底: {item['detail']}")
    for name in manifest["removed"]:
        print(f"  已删除上次生成、这次规格里没有的 {name}")
    print(f"清单: {Path(manifest['out_dir']).parent / MANIFEST_NAME}")
    return 0


def _report_id_arg(text: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", text) or ".." in text:
        raise argparse.ArgumentTypeError(f"report_id 不合法: {text!r}（只能含字母、数字、下划线、连字符，不能带路径）")
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="按规格确定性地生成模拟数据（mock 试跑用）")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler, text in (("generate", cmd_generate, "按规格生成模拟数据"), ("check", cmd_check, "只校验规格，不生成")):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("report_id", type=_report_id_arg, help="案例编号")
        cmd.add_argument("--spec", help="规格文件，默认 workspace/<report_id>/data_mock/spec.yaml")
        cmd.add_argument("--data-root", dest="data_root", help="数据根目录，默认按 .reproduce.json 解析")
        if name == "generate":
            cmd.add_argument("--out", help="输出目录，默认 workspace/<report_id>/data_mock/files")
        cmd.set_defaults(func=handler)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MockSpecError as exc:
        for error in exc.errors:
            print(f"规格错误: {error}", file=sys.stderr)
        return 1
    except MockDataError as exc:
        print(f"生成失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
