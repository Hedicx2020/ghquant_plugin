"""用量采集：从宿主的会话记录里读出每个会话的 token 用量。

两个宿主的记录格式都没有公开承诺（Claude Code 的还会被定期清理），所以这里只当增强：
读得到就给精确值，读不到就留空，任何解析错误都不向上抛。四项分开记——未缓存输入、
缓存写入、缓存读取、输出——因为它们的单价差一个数量级。

只取数字、时间和工具名，不保留会话内容。

两种读法：整份会话的用量；或只算落在给定时段里的那部分（一个长会话先后跑了几个案例、
或者要把主会话的开销摊到某一步时用）。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional, Sequence

# 折算开支用的相对权重（以未缓存输入为 1）
COST_WEIGHTS = {"uncached_input": 1.0, "cache_write": 1.25, "cache_read": 0.1, "output": 5.0}
CODEX_TOOL_TYPES = ("function_call", "custom_tool_call", "local_shell_call")
Interval = tuple[datetime, datetime]
SPAN_MARGIN_HOURS = 1.0  # 按案例的起止时间找会话时，前后各留的余量
_CODEX_NAME_TS_RE = re.compile(r"rollout-(\d{4})-(\d{2})-(\d{2})T(\d{2})-(\d{2})-(\d{2})")


@dataclass
class Usage:
    uncached_input: int = 0
    cache_write: int = 0
    cache_read: int = 0
    output: int = 0
    reasoning_output: int = 0  # 输出里的推理部分（Codex 才有，已含在 output 内）
    calls: int = 0  # 模型调用次数
    tool_calls: int = 0
    peak_context: int = 0  # 单次调用的最大输入（上下文峰值）

    @property
    def total_input(self) -> int:
        return self.uncached_input + self.cache_write + self.cache_read

    @property
    def weighted(self) -> float:
        """按相对单价折算的开支（单位：等价的未缓存输入 token）。"""
        return sum(getattr(self, key) * weight for key, weight in COST_WEIGHTS.items())

    def add(self, other: "Usage") -> "Usage":
        return Usage(
            uncached_input=self.uncached_input + other.uncached_input,
            cache_write=self.cache_write + other.cache_write,
            cache_read=self.cache_read + other.cache_read,
            output=self.output + other.output,
            reasoning_output=self.reasoning_output + other.reasoning_output,
            calls=self.calls + other.calls,
            tool_calls=self.tool_calls + other.tool_calls,
            peak_context=max(self.peak_context, other.peak_context),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_input"] = self.total_input
        data["weighted"] = round(self.weighted, 1)
        return data


@dataclass
class SessionUsage:
    host: str  # claude_code / codex
    session_id: str
    path: str
    usage: Usage = field(default_factory=Usage)
    parent_id: Optional[str] = None  # 子代理的父会话
    role: Optional[str] = None  # 子代理类型；主会话为 main
    label: Optional[str] = None  # 派发描述或任务名（v3 工单规定它等于 step_id）
    model: Optional[str] = None
    effort: Optional[str] = None
    originator: Optional[str] = None
    cwd: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    tools: dict[str, int] = field(default_factory=dict)
    mentions: bool = False  # 会话里是否出现过要找的字符串（案例编号）
    mention_counts: dict[str, int] = field(default_factory=dict)  # 各个要找的字符串出现在多少行里
    inherited_input: int = 0  # 分叉式派发从父会话继承来、已扣除的输入 token
    sliced: bool = False  # usage 只算了给定时段内的部分
    active_seconds: Optional[float] = None  # 切片时：各时段内首末记录之间的时长之和
    error: Optional[str] = None

    @property
    def seconds(self) -> Optional[float]:
        if self.sliced:
            return self.active_seconds
        start, end = _parse_ts(self.started_at), _parse_ts(self.ended_at)
        return (end - start).total_seconds() if start and end else None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["usage"] = self.usage.to_dict()
        data["seconds"] = self.seconds
        return data


def _parse_ts(value: Any) -> Optional[datetime]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def span_interval(start: Any, end: Any, margin_hours: float = SPAN_MARGIN_HOURS) -> Optional[Interval]:
    """从起止时间得到一个前后各留余量的时段；任一头缺失返回 None。"""
    low, high = _parse_ts(start), _parse_ts(end)
    if low is None or high is None:
        return None
    margin = timedelta(hours=margin_hours)
    return (min(low, high) - margin, max(low, high) + margin)


class _Slicer:
    """判断一条记录落不落在给定时段里，并记下各时段内首末记录的时间。不给时段时全部算在内。"""

    def __init__(self, intervals: Optional[Sequence[Interval]]):
        self.intervals = sorted(intervals) if intervals is not None else None
        self.spans: dict[int, list[datetime]] = {}

    def hit(self, ts: Optional[datetime]) -> bool:
        if self.intervals is None:
            return True
        if ts is None:
            return False
        for i, (low, high) in enumerate(self.intervals):
            if low <= ts <= high:
                span = self.spans.setdefault(i, [ts, ts])
                span[0], span[1] = min(span[0], ts), max(span[1], ts)
                return True
        return False

    @property
    def seconds(self) -> Optional[float]:
        if self.intervals is None:
            return None
        return sum((high - low).total_seconds() for low, high in self.spans.values())


def _needles(needle: Optional[str], needles: Iterable[str]) -> list[str]:
    out = [needle] if needle else []
    out += [n for n in needles if n and n not in out]
    return out


# ---------------------------------------------------------------------------
# 逐行读取（支持 .zst）
# ---------------------------------------------------------------------------


def _iter_lines(path: Path) -> Iterator[str]:
    """逐行读一个会话文件。.zst 依次尝试标准库、zstandard 模块、zstd 命令。"""
    if path.suffix != ".zst":
        with path.open("r", encoding="utf-8", errors="replace") as f:
            yield from f
        return
    if importlib.util.find_spec("compression") and importlib.util.find_spec("compression.zstd"):
        from compression import zstd  # type: ignore[import-not-found]

        with zstd.open(path, "rt", encoding="utf-8", errors="replace") as f:
            yield from f
        return
    if importlib.util.find_spec("zstandard"):
        import io

        import zstandard  # type: ignore[import-not-found]

        with path.open("rb") as raw:
            reader = zstandard.ZstdDecompressor().stream_reader(raw)
            yield from io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
        return
    exe = shutil.which("zstd")
    if not exe:
        raise RuntimeError("读 .zst 会话需要 zstd 命令或 zstandard 模块")
    proc = subprocess.Popen([exe, "-dc", str(path)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            yield raw_line.decode("utf-8", errors="replace")
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
        proc.wait()


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------


def claude_project_dir(root: Path, home: Optional[Path] = None) -> Path:
    """Claude Code 为一个工作目录存会话记录的地方：路径里的非字母数字都换成连字符。"""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(root))
    return (home or Path.home()) / ".claude" / "projects" / slug


def parse_claude_transcript(
    path: Path,
    needle: Optional[str] = None,
    needles: Iterable[str] = (),
    intervals: Optional[Sequence[Interval]] = None,
) -> SessionUsage:
    """读一份 Claude Code 会话记录（主会话或子代理）。

    同一次模型调用会按内容块写成多行、重复带同一份 usage，这里按消息编号去重。
    给了 intervals 时只算落在这些时段里的调用、工具和提及；起止时间仍是整份会话的。
    """
    is_sub = path.parent.name == "subagents"
    session = SessionUsage(
        host="claude_code",
        session_id=path.stem,
        path=str(path),
        role=None if is_sub else "main",
        parent_id=path.parent.parent.name if is_sub else None,
    )
    meta_path = path.with_suffix(".meta.json")
    if is_sub and meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            session.role = meta.get("agentType") or session.role
            session.label = meta.get("description")
        except (OSError, ValueError):
            pass

    wanted = _needles(needle, needles)
    slicer = _Slicer(intervals)
    session.sliced = intervals is not None
    per_message: dict[str, dict[str, int]] = {}
    tool_ids: dict[str, str] = {}
    anonymous = 0
    when: Optional[datetime] = None  # 没带时间的行沿用上一行的时间
    try:
        for line in _iter_lines(path):
            hits = [n for n in wanted if n in line]
            if not hits and '"timestamp"' not in line and '"usage"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            ts = record.get("timestamp")
            if isinstance(ts, str):
                session.started_at = session.started_at or ts
                session.ended_at = ts
                when = _parse_ts(ts) or when
            inside = slicer.hit(when)
            if inside:
                for n in hits:
                    session.mention_counts[n] = session.mention_counts.get(n, 0) + 1
            session.cwd = session.cwd or record.get("cwd")
            message = record.get("message")
            if record.get("type") != "assistant" or not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if isinstance(usage, dict):
                mid = message.get("id")
                if not isinstance(mid, str):
                    anonymous += 1
                    mid = f"_anon{anonymous}"
                if inside or mid in per_message:  # 一条消息的几行按第一行的时间归属
                    slot = per_message.setdefault(mid, {})
                    for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"):
                        slot[key] = max(slot.get(key, 0), _int(usage.get(key)))
                session.model = session.model or message.get("model")
            if inside:
                for block in message.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_ids[str(block.get("id") or len(tool_ids))] = str(block.get("name") or "?")
    except (OSError, RuntimeError) as exc:
        session.error = f"{type(exc).__name__}: {exc}"[:200]
    session.mentions = bool(needle and session.mention_counts.get(needle))
    session.active_seconds = slicer.seconds

    usage_total = Usage(calls=len(per_message), tool_calls=len(tool_ids))
    for slot in per_message.values():
        usage_total.uncached_input += slot.get("input_tokens", 0)
        usage_total.cache_write += slot.get("cache_creation_input_tokens", 0)
        usage_total.cache_read += slot.get("cache_read_input_tokens", 0)
        usage_total.output += slot.get("output_tokens", 0)
        context = slot.get("input_tokens", 0) + slot.get("cache_creation_input_tokens", 0) + slot.get("cache_read_input_tokens", 0)
        usage_total.peak_context = max(usage_total.peak_context, context)
    session.usage = usage_total
    for name in tool_ids.values():
        session.tools[name] = session.tools.get(name, 0) + 1
    return session


def claude_transcript_label(path: Path) -> Optional[str]:
    """子代理会话的派发描述（同名 .meta.json 里的 description）。主会话、没有元数据文件的都是 None。

    与 parse_claude_transcript 填 label 的口径相同，但不用打开会话记录本身。
    """
    if path.parent.name != "subagents":
        return None
    try:
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    label = meta.get("description") if isinstance(meta, dict) else None
    return label if isinstance(label, str) else None


def find_claude_transcripts(root: Path, home: Optional[Path] = None) -> list[Path]:
    """这个工作目录下的全部 Claude Code 会话记录：主会话与各自的子代理。"""
    project = claude_project_dir(root, home)
    if not project.is_dir():
        return []
    return sorted(project.glob("*.jsonl")) + sorted(project.glob("*/subagents/*.jsonl"))


_TRANSCRIPT_START: dict[str, Optional[datetime]] = {}
TRANSCRIPT_START_PROBE_LINES = 200


def claude_transcript_start(path: Path) -> Optional[datetime]:
    """一份 Claude Code 会话记录按文件顺序的第一个时间戳，只读开头若干行；读不到返回 None。

    与 parse_claude_transcript 填 started_at 的口径相同。用来在整份解析之前排除开始得比案例
    时间窗还晚的会话：一个工作目录下的会话记录会越积越多，逐案例整份重读是看板最慢的一步。
    """
    key = str(path)
    if key in _TRANSCRIPT_START:
        return _TRANSCRIPT_START[key]
    found: Optional[datetime] = None
    try:
        for index, line in enumerate(_iter_lines(path)):
            if index >= TRANSCRIPT_START_PROBE_LINES:
                break
            if '"timestamp"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            ts = record.get("timestamp") if isinstance(record, dict) else None
            if isinstance(ts, str):
                found = _parse_ts(ts)  # 第一个时间戳解析不了时与整份解析一样按「没有时间」处理
                break
    except (OSError, RuntimeError):
        found = None
    _TRANSCRIPT_START[key] = found
    return found


# ---------------------------------------------------------------------------
# Codex
# ---------------------------------------------------------------------------


def parse_codex_session(
    path: Path,
    needle: Optional[str] = None,
    needles: Iterable[str] = (),
    intervals: Optional[Sequence[Interval]] = None,
    only_cwd: Optional[str] = None,
    only_label: Optional[Callable[[Optional[str]], bool]] = None,
) -> SessionUsage:
    """读一份 Codex 会话记录。

    给了 only_cwd（规范化后的工作目录）时，会话元信息里的工作目录对不上就立刻停下不再往后读：
    调用方反正不要别的工作目录的会话，而一台机器上绝大多数 Codex 会话都属于别的目录。
    only_label 同理：拿会话的任务名去问它，回答不要就停。

    Codex 记的是累计计数器，用量按相邻两次计数的差累加。全新会话的首条计数事件里
    「累计 = 单次」，从零算起；带着父会话历史分叉出来的子代理，创建时会先写一条父会话
    计数器的快照（累计远大于单次），这条快照是要扣掉的基数，它本身也不算一次调用。
    给了 intervals 时只累加落在这些时段里的差值、工具和提及；起止时间仍是整份会话的。
    """
    session = SessionUsage(host="codex", session_id=path.name.split(".")[0], path=str(path))
    wanted = _needles(needle, needles)
    slicer = _Slicer(intervals)
    session.sliced = intervals is not None
    keys = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens")
    prev: Optional[dict[str, int]] = None  # 上一次的累计值；None 表示还没见到计数事件
    own = {k: 0 for k in keys}
    calls = 0
    seen_meta = False
    when: Optional[datetime] = None
    try:
        for line in _iter_lines(path):
            hits = [n for n in wanted if n in line]
            if not hits and not any(
                marker in line for marker in ('"token_count"', '"session_meta"', '"turn_context"', '_call"', '"task_')
            ):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            ts = record.get("timestamp")
            if isinstance(ts, str):
                session.started_at = session.started_at or ts
                session.ended_at = ts
                when = _parse_ts(ts) or when
            inside = slicer.hit(when)
            if inside:
                for n in hits:
                    session.mention_counts[n] = session.mention_counts.get(n, 0) + 1
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            rtype, ptype = record.get("type"), payload.get("type")
            if rtype == "session_meta":
                if seen_meta:
                    continue  # 分叉会话里会重放父会话的元信息，只认第一条
                seen_meta = True
                session.session_id = str(payload.get("id") or session.session_id)
                session.cwd = payload.get("cwd")
                if only_cwd and session.cwd and os.path.normpath(str(session.cwd)) != only_cwd:
                    break
                session.originator = payload.get("originator")
                source = payload.get("source")
                if isinstance(source, dict):
                    sub = source.get("subagent")
                    spawn = sub.get("thread_spawn") if isinstance(sub, dict) else None
                    if isinstance(spawn, dict):
                        session.parent_id = spawn.get("parent_thread_id")
                        session.role = spawn.get("agent_role") or "subagent"
                        session.label = spawn.get("agent_nickname") or spawn.get("agent_path")
                    else:
                        session.role = "subagent"
                else:
                    session.role = "main"
                if only_label is not None and not only_label(session.label):
                    break
            elif rtype == "turn_context":
                session.model = payload.get("model") or session.model
                session.effort = payload.get("effort") or session.effort
            elif ptype == "token_count":
                info = payload.get("info")
                total = info.get("total_token_usage") if isinstance(info, dict) else None
                if not isinstance(total, dict):
                    continue
                last = info.get("last_token_usage") if isinstance(info.get("last_token_usage"), dict) else {}
                current = {k: _int(total.get(k)) for k in keys}
                if prev is None:
                    if current["input_tokens"] > _int(last.get("input_tokens")):  # 父会话计数器的快照
                        session.inherited_input = current["input_tokens"]
                        prev = current
                        continue
                    prev = {k: 0 for k in keys}
                if (current["input_tokens"], current["output_tokens"]) == (prev["input_tokens"], prev["output_tokens"]):
                    continue  # 同一次调用重复上报
                delta = {k: max(current[k] - prev[k], 0) for k in keys}
                prev = current
                if inside:
                    for k in keys:
                        own[k] += delta[k]
                    calls += 1
                    session.usage.peak_context = max(session.usage.peak_context, _int(last.get("input_tokens")))
            elif rtype == "response_item" and ptype in CODEX_TOOL_TYPES and inside:
                name = str(payload.get("name") or ptype)
                session.tools[name] = session.tools.get(name, 0) + 1
    except (OSError, RuntimeError) as exc:
        session.error = f"{type(exc).__name__}: {exc}"[:200]

    session.usage.cache_read = own["cached_input_tokens"]
    session.usage.cache_write = own["cache_write_input_tokens"]
    session.usage.uncached_input = max(own["input_tokens"] - own["cached_input_tokens"] - own["cache_write_input_tokens"], 0)
    session.usage.output = own["output_tokens"]
    session.usage.reasoning_output = own["reasoning_output_tokens"]
    session.usage.calls = calls
    session.usage.tool_calls = sum(session.tools.values())
    session.mentions = bool(needle and session.mention_counts.get(needle))
    session.active_seconds = slicer.seconds
    return session


def forbidden_reads(path: Path, host: str, forbidden: Sequence[str], allowed: Sequence[str] = ()) -> list[str]:
    """事后核对：一份会话记录里，工具调用的参数中出现过哪些禁读路径。

    只看工具调用的参数（读文件的路径、执行的命令），不看工具输出与正文——任务文件的「纪律」一节
    本身就列着禁读清单，按全文找会全部命中。allowed 里的路径（这一步自己的任务文件与回执）先剔除。
    没有读文件前钩子的宿主靠它留痕；有钩子的宿主也照查一遍，钩子没装好时能看出来。
    """
    wanted = [f for f in forbidden if f]
    if not wanted:
        return []
    # 产物目录（扰动结果、运行缓存）脚本要往里写，命令里出现是正常的：只有用读文件工具直接打开才算
    in_commands = [f for f in wanted if not f.startswith("output/")]
    hits: set[str] = set()

    def scan(chunk: Any, targets: list[str]) -> None:
        if not chunk or not targets:
            return
        text = chunk if isinstance(chunk, str) else json.dumps(chunk, ensure_ascii=False)
        for item in allowed:
            text = text.replace(item, "")
        hits.update(f for f in targets if f in text)

    try:
        for line in _iter_lines(path):
            if not any(f in line for f in wanted):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            if host == "codex":
                payload = record.get("payload")
                if record.get("type") == "response_item" and isinstance(payload, dict) and payload.get("type") in CODEX_TOOL_TYPES:
                    for key in ("arguments", "input", "action", "command"):
                        scan(payload.get(key), in_commands)  # Codex 读文件也是跑命令
            else:
                message = record.get("message")
                for block in (message.get("content") if isinstance(message, dict) else None) or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        scan(block.get("input"), wanted if block.get("name") in ("Read", "Grep", "Glob") else in_commands)
    except (OSError, RuntimeError):
        return sorted(hits)
    return sorted(hits)


def codex_session_time(path: Path) -> Optional[datetime]:
    """从文件名取会话开始时间（本地时间），不用打开文件。"""
    m = _CODEX_NAME_TS_RE.search(path.name)
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups()))
    except ValueError:
        return None


FILENAME_SLACK = timedelta(hours=36)  # 文件名里的时间是写入时的本地时间，时区未知，按宽余量粗筛


def find_codex_sessions(
    since: Optional[datetime] = None, until: Optional[datetime] = None, home: Optional[Path] = None
) -> list[Path]:
    """Codex 的会话记录（含归档与压缩的）。

    since/until 只用来按文件名粗筛（前后各放宽 36 小时），省得把上千个压缩文件都打开；
    精确的时间判断由调用方按会话内的时间戳做。
    """
    base = (home or Path.home()) / ".codex"
    candidates: list[Path] = []
    for directory in (base / "sessions", base / "archived_sessions"):
        if directory.is_dir():
            for pattern in ("*.jsonl", "*.jsonl.zst"):
                candidates.extend(directory.rglob(pattern))
    low = since.replace(tzinfo=None) - FILENAME_SLACK if since else None
    high = until.replace(tzinfo=None) + FILENAME_SLACK if until else None
    out: list[Path] = []
    for path in candidates:
        when = codex_session_time(path)
        if when is not None and ((low and when < low) or (high and when > high)):
            continue
        out.append(path)
    return sorted(out, key=lambda p: p.name)


# ---------------------------------------------------------------------------
# 按案例汇总
# ---------------------------------------------------------------------------


def case_window(state: dict[str, Any], margin_hours: float = SPAN_MARGIN_HOURS) -> tuple[Optional[datetime], Optional[datetime]]:
    """案例从建立到最后更新的时间窗（带时区的绝对时间，前后各留一点余量）。"""
    start, end = _parse_ts(state.get("created_at")), _parse_ts(state.get("updated_at"))
    margin = timedelta(hours=margin_hours)
    return (start - margin if start else None, end + margin if end else None)


def _in_window(session: SessionUsage, since: Optional[datetime], until: Optional[datetime]) -> bool:
    """会话的起止时间与时间窗有交叠（会话没有时间戳时不排除）。"""
    start, end = _parse_ts(session.started_at), _parse_ts(session.ended_at)
    if start is None or end is None:
        return True
    return not ((until and start > until) or (since and end < since))


def _dominant(session: SessionUsage, report_id: str) -> bool:
    """这个会话（在所算的时段里）提到本案例的行数比提到其他任何案例的都多。"""
    own = session.mention_counts.get(report_id, 0)
    others = max((n for key, n in session.mention_counts.items() if key != report_id), default=0)
    return own > 0 and own > others


def collect_case_usage(
    root: Path,
    report_id: str,
    state: Optional[dict[str, Any]] = None,
    hosts: Iterable[str] = ("claude_code", "codex"),
    home: Optional[Path] = None,
    intervals: Optional[Sequence[Interval]] = None,
    other_ids: Iterable[str] = (),
) -> list[SessionUsage]:
    """找出与一个案例有关的宿主会话，读出落在案例生命周期里的用量。

    这是给没有连接键的旧案例用的估计办法，v3 的新案例按 step_id 对账。三个条件：
    会话的工作目录是本工作区；只算给定时段内的调用（intervals，通常是案例从第一条到最后
    一条业务事件、前后各留一小时；不给时取 state 的建立与最后更新时间）；在这段时间里，
    会话提到本案例的行数比提到其他任何案例（other_ids）的都多。子代理跟着父会话走。
    同一个会话在同一段时间里同时推进两个案例时分不开，会记到被提到更多的那个头上。
    """
    if intervals is None:
        since, until = case_window(state or {})
        intervals = [(since, until)] if since and until else None
    since = min((low for low, _ in intervals), default=None) if intervals else None
    until = max((high for _, high in intervals), default=None) if intervals else None
    needles = [report_id, *(i for i in other_ids if i != report_id)]
    root_text = os.path.normpath(str(root))
    sessions: list[SessionUsage] = []
    if "claude_code" in hosts:
        for path in find_claude_transcripts(root, home):
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if since and mtime < since:
                continue
            started = claude_transcript_start(path) if until else None
            if until and started and started > until:
                continue  # 案例收尾之后才开始的会话，整份解析后也会被 _in_window 排除
            parsed = parse_claude_transcript(path, needle=report_id, needles=needles, intervals=intervals)
            if _in_window(parsed, since, until):
                sessions.append(parsed)
    if "codex" in hosts:
        for path in find_codex_sessions(since, until, home):
            parsed = parse_codex_session(path, needle=report_id, needles=needles, intervals=intervals, only_cwd=root_text)
            if parsed.cwd and os.path.normpath(parsed.cwd) != root_text:
                continue
            if _in_window(parsed, since, until):
                sessions.append(parsed)

    sessions = [s for s in sessions if s.usage.calls > 0]  # 活动时段内没有调用的不算
    related = {s.session_id for s in sessions if _dominant(s, report_id)}
    changed = True
    while changed:  # 子代理跟着父会话
        changed = False
        for s in sessions:
            if s.session_id not in related and s.parent_id and s.parent_id in related:
                related.add(s.session_id)
                changed = True
    return [s for s in sessions if s.session_id in related]


def summarize(sessions: Iterable[SessionUsage]) -> dict[str, Any]:
    """按宿主、角色汇总。"""
    sessions = list(sessions)
    total = Usage()
    by_group: dict[str, dict[str, Any]] = {}
    for s in sessions:
        total = total.add(s.usage)
        key = f"{s.host}/{s.role or '未知'}"
        slot = by_group.setdefault(key, {"sessions": 0, "usage": Usage(), "seconds": 0.0})
        slot["sessions"] += 1
        slot["usage"] = slot["usage"].add(s.usage)
        slot["seconds"] += s.seconds or 0.0
    return {
        "sessions": len(sessions),
        "total": total.to_dict(),
        "groups": {
            key: {"sessions": v["sessions"], "seconds": round(v["seconds"], 1), **v["usage"].to_dict()}
            for key, v in sorted(by_group.items())
        },
    }


# ---------------------------------------------------------------------------
# 输入侧账本：内核自己记的，任何宿主都有
# ---------------------------------------------------------------------------

_STEP_EVENT_RE = re.compile(r"step:(?P<step>.+):(?P<what>issued|done|failed)")
_USAGE_KEYS = ("uncached_input", "cache_write", "cache_read", "output", "calls", "tool_calls")


CALLS_LOG = "flow/calls.jsonl"  # 相对 workspace/<id>/；内核每被调用一次追加一行


def log_call(root: Path, report_id: str, command: str, returncode: int, out_bytes: int) -> None:
    """记一次内核调用（命令、返回码、输出了多少字节）。主会话读不到用量时，拿它当开销的代理。记不上不报错。"""
    path = root / "workspace" / report_id / CALLS_LOG
    try:
        if not path.parent.parent.is_dir():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
        line = json.dumps({"ts": now, "cmd": command, "rc": returncode, "out_bytes": out_bytes}, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def read_calls(root: Path, report_id: str) -> dict[str, Any]:
    """内核调用的汇总：{"total", "out_bytes", "by_command": {命令: 次数}}。"""
    path = root / "workspace" / report_id / CALLS_LOG
    summary: dict[str, Any] = {"total": 0, "out_bytes": 0, "by_command": {}}
    if not path.is_file():
        return summary
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        summary["total"] += 1
        summary["out_bytes"] += _int(item.get("out_bytes"))
        cmd = str(item.get("cmd") or "?")
        summary["by_command"][cmd] = summary["by_command"].get(cmd, 0) + 1
    return summary


def step_ledger(records: Iterable[dict[str, Any]], calls: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """从事件流还原每一次派发：任务文件多大、花了多久、结果如何，读得到宿主记录时再加 token。

    每张工单的任务文件字节数与墙钟由内核自己记，所以这张账在任何宿主上都有；token 是当场从宿主的
    会话记录里读出来的，读不到就空着。返回 rows（逐次派发）、by_stage / by_role（汇总）、totals，
    以及主会话侧的代理指标 kernel_calls（read_calls 的结果：内核被调用了多少次、一共输出了多少字节）。
    """
    rows: list[dict[str, Any]] = []
    open_rows: dict[str, dict[str, Any]] = {}
    for record in records:
        match = _STEP_EVENT_RE.fullmatch(str(record.get("event") or ""))
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        if not match or payload.get("kind") == "kernel":
            continue
        step, what = match.group("step"), match.group("what")
        if what == "issued":
            row = {
                "step": step,
                "stage": step.split(".")[0],
                "attempt": payload.get("attempt"),
                "kind": payload.get("kind") or "dispatch",
                "role": payload.get("role") or ("external" if payload.get("kind") == "exec" else "orchestrator"),
                "task_bytes": int(payload.get("task_bytes") or 0),
                "redo_reason": payload.get("reason"),
                "issued_at": record.get("ts"),
                "ended_at": None,
                "seconds": None,
                "outcome": "inflight",
                "usage": None,
            }
            rows.append(row)
            open_rows[step] = row
            continue
        row = open_rows.pop(step, None)
        if row is None:
            continue
        start, end = _parse_ts(row["issued_at"]), _parse_ts(record.get("ts"))
        row["ended_at"] = record.get("ts")
        row["seconds"] = payload.get("seconds") if isinstance(payload.get("seconds"), (int, float)) else (round((end - start).total_seconds()) if start and end else None)
        row["outcome"] = "done" if what == "done" else f"failed:{payload.get('class') or ''}".rstrip(":")
        if payload.get("state") and payload.get("state") != "success":
            row["outcome"] = f"failed:{payload.get('reason') or payload.get('state')}"
        if isinstance(payload.get("usage"), dict):
            row["usage"] = payload["usage"]
        for key in ("input_bytes", "subsessions", "engine", "mode"):
            if payload.get(key) is not None:
                row[key] = payload[key]

    def _group(key: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            slot = out.setdefault(str(row[key]), {"dispatches": 0, "redispatches": 0, "task_bytes": 0, "seconds": 0, "with_usage": 0, **{k: 0 for k in _USAGE_KEYS}})
            slot["dispatches"] += 1
            slot["redispatches"] += 1 if int(row.get("attempt") or 1) > 1 else 0
            slot["task_bytes"] += row["task_bytes"] + int(row.get("input_bytes") or 0)
            slot["seconds"] += int(row.get("seconds") or 0)
            if row.get("usage"):
                slot["with_usage"] += 1
                for k in _USAGE_KEYS:
                    slot[k] += _int(row["usage"].get(k))
        return out

    totals = {"dispatches": len(rows), "redispatches": sum(1 for r in rows if int(r.get("attempt") or 1) > 1), "task_bytes": 0, "seconds": 0, "with_usage": 0, **{k: 0 for k in _USAGE_KEYS}}
    for slot in _group("stage").values():
        for key in ("task_bytes", "seconds", "with_usage", *_USAGE_KEYS):
            totals[key] += slot[key]
    return {"rows": rows, "by_stage": _group("stage"), "by_role": _group("role"), "totals": totals, "kernel_calls": calls or {"total": 0, "out_bytes": 0, "by_command": {}}}
