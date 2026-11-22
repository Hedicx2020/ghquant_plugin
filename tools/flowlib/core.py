"""内核的公共数据结构：案例上下文、步骤、配置与宿主识别、路径约定。

这里不做任何调度决定，也不写状态；调度在 steps.py（步骤表）与 engine.py（推进循环）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from tools import state as st

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
HOSTS = ("claude_code", "codex", "generic")
FINISHED = {"done", "skipped"}

# 步骤记录的状态
INFLIGHT = "inflight"
DONE = "done"
REDO = "redo"  # 已经做过一次，要带着原因重派
FAILED = "failed"

# 重派上限（同一步骤在首派之外最多再派几次）；可在 .reproduce.json 的 flow.redispatch_limit 里按步骤名覆盖
DEFAULT_REDISPATCH_LIMIT = 2
ADHOC_LIMIT = 5
REVIEW_ROUND_LIMIT = 3
MODIFY_ROUND_LIMIT = 3
REVISE_ROUND_LIMIT = 3
MAX_ITER_BY_DIFFICULTY = {"easy": 3, "medium": 5, "hard": 6}

ROLE_CN = {
    "quant-extractor": "提取",
    "quant-planner": "计划",
    "quant-auditor": "审计",
    "quant-coder": "编码",
    "quant-verifier": "验证",
    "quant-diagnoser": "诊断",
    "quant-oos-analyst": "样本外分析",
    "quant-reporter": "报告",
    "general-purpose": "通用子代理",
    "orchestrator": "主会话",
    "external": "外审引擎",
    "kernel": "内核",
}
# economy 档下改用经济模型的角色（与现行 SKILL.md 的派发规则一致）
ECONOMY_ROLES = {"quant-extractor", "quant-verifier", "quant-oos-analyst"}


class FlowError(ValueError):
    """内核命令的输入或当前状态不允许这个操作。"""


# ---------------------------------------------------------------------------
# 配置与宿主
# ---------------------------------------------------------------------------


def load_config(root: Path) -> dict[str, Any]:
    """读工作区的 .reproduce.json；没有或读不了时返回空字典（内核全部走默认值）。"""
    path = root / ".reproduce.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def detect_host(explicit: Optional[str] = None, state: Optional[dict[str, Any]] = None) -> str:
    """当前宿主：显式参数 > 环境变量 REPRODUCE_HOST > 宿主自带的环境变量 > 状态里记的 > generic。"""
    for candidate in (explicit, os.environ.get("REPRODUCE_HOST")):
        if candidate:
            if candidate not in HOSTS:
                raise FlowError(f"未知宿主: {candidate}，应属于 {HOSTS}")
            return candidate
    if os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude_code"
    if any(key.startswith("CODEX_") for key in os.environ):
        return "codex"
    recorded = ((state or {}).get("ext") or {}).get("host")
    return recorded if recorded in HOSTS else "generic"


def external_engine(host: str, config: Optional[dict[str, Any]] = None) -> tuple[str, str]:
    """外审用哪个引擎：与宿主不同家族。返回（引擎名, 台账里的引擎状态名）。"""
    preferred = ((config or {}).get("external_review") or {}).get("engine")
    if preferred in ("codex", "claude") and not (host == "claude_code" and preferred == "claude") and not (host == "codex" and preferred == "codex"):
        engine = preferred
    else:
        engine = "claude" if host == "codex" else "codex"
    return engine, f"{engine}_external"


# ---------------------------------------------------------------------------
# 步骤
# ---------------------------------------------------------------------------


@dataclass
class Step:
    """步骤表里的一步。kind：dispatch 派给子 agent；exec 由内核在后台跑的外审；judge 交给主会话判断。"""

    id: str
    stage: str
    kind: str = "dispatch"
    role: str = "general-purpose"
    title: str = ""
    milestone: Optional[str] = None
    instruction: str = ""
    reads: list[str] = field(default_factory=list)  # 要整读的文件（相对工作区根）
    outputs: list[str] = field(default_factory=list)  # 必须交回的文件
    writes: list[str] = field(default_factory=list)  # 允许改动的路径（文件所有权）
    pack: Optional[tuple[str, str]] = None  # 上下文包的（角色, 步骤）
    receipt: str = "optional"  # optional / required / none
    parallel_group: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)
    forbid: list[str] = field(default_factory=list)  # 这一步额外的禁读路径

    @property
    def file_stem(self) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]", "_", self.id)


def step_key(raw: str) -> str:
    """把工单里的步骤名（可能带 #次数）还原成步骤编号。"""
    return str(raw).split("#", 1)[0].strip()


# ---------------------------------------------------------------------------
# 案例上下文
# ---------------------------------------------------------------------------


@dataclass
class Ctx:
    root: Path
    report_id: str
    state: dict[str, Any]
    config: dict[str, Any] = field(default_factory=dict)
    host: str = "generic"

    # ---- 路径 ----
    @property
    def ws(self) -> str:
        return f"workspace/{self.report_id}"

    @property
    def src(self) -> str:
        return f"src/{self.report_id}"

    @property
    def results(self) -> str:
        return f"output/{self.report_id}/{'results_mock' if self.trial else 'results'}"

    @property
    def out(self) -> str:
        return f"output/{self.report_id}"

    def path(self, rel: str) -> Path:
        return self.root / rel

    def exists(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    def read(self, rel: str) -> str:
        path = self.root / rel
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def template(self, rel: str) -> str:
        """模板路径：工作区里有就用工作区的（用户可以改种子），否则用插件自带的。返回相对或绝对路径字符串。"""
        if (self.root / rel).is_file():
            return rel
        return str(PLUGIN_ROOT / rel)

    # ---- 状态里的常用量 ----
    @property
    def flow(self) -> dict[str, Any]:
        return self.state.get("flow") or {}

    @property
    def steps(self) -> dict[str, dict[str, Any]]:
        return self.flow.get("steps") or {}

    def rec(self, step_id: str) -> Optional[dict[str, Any]]:
        return self.steps.get(step_id)

    def status_of(self, step_id: str) -> Optional[str]:
        return (self.steps.get(step_id) or {}).get("status")

    def is_done(self, step_id: str) -> bool:
        return self.status_of(step_id) == DONE

    def result_of(self, step_id: str) -> dict[str, Any]:
        return (self.steps.get(step_id) or {}).get("result") or {}

    @property
    def generation(self) -> int:
        return int(self.flow.get("generation") or 0)

    @property
    def policy(self) -> dict[str, Any]:
        return self.state.get("policy") or {}

    @property
    def ext(self) -> dict[str, Any]:
        return self.state.get("ext") or {}

    @property
    def mode(self) -> str:
        return str(self.state.get("mode") or "auto")

    @property
    def difficulty(self) -> str:
        return str(self.state.get("difficulty_override") or self.state.get("difficulty") or "medium")

    @property
    def report_type(self) -> Optional[str]:
        return self.state.get("type")

    @property
    def tags(self) -> set[str]:
        return set(self.state.get("tags") or [])

    @property
    def is_ml(self) -> bool:
        return "ml" in self.tags or self.report_type == "ml"

    @property
    def experimental(self) -> bool:
        return self.state.get("reproduction_mode") == "experimental"

    @property
    def audit_level(self) -> str:
        level = self.config.get("audit_level")
        return level if level in ("strict", "standard") else "strict"

    @property
    def economy(self) -> bool:
        return bool(self.config.get("economy"))

    @property
    def iterate_digest(self) -> str:
        """诊断摘要怎么用：shadow（默认，灰度：摘要与全部历史一起给）/ on（摘要代替更早的历史）/ off。"""
        value = (self.config.get("flow") or {}).get("iterate_digest")
        return value if value in ("shadow", "on", "off") else "shadow"

    @property
    def trial(self) -> bool:
        return bool((self.ext.get("trial") or {}).get("active"))

    @property
    def created_by_kernel(self) -> bool:
        """v3 内核新建的案例。只对它们生效的新检查项（数据体检、一致性预检）据此判断。"""
        return self.ext.get("created_by") == "flow"

    @property
    def milestones(self) -> list[dict[str, Any]]:
        return [m for m in self.state.get("milestones") or [] if isinstance(m, dict) and m.get("id")]

    def milestone(self, mid: str) -> Optional[dict[str, Any]]:
        return next((m for m in self.milestones if m.get("id") == mid), None)

    def stage_status(self, stage: str) -> Optional[str]:
        return ((self.state.get("stages") or {}).get(stage) or {}).get("status")

    def redispatch_limit(self, step_id: str) -> int:
        table = (self.config.get("flow") or {}).get("redispatch_limit") or {}
        for key, value in table.items():
            if step_id == key or step_id.startswith(key + "."):
                return int(value)
        return DEFAULT_REDISPATCH_LIMIT

    def model_tier(self, role: str) -> str:
        return "economy" if self.economy and role in ECONOMY_ROLES else "default"


def make_ctx(root: Path, report_id: str, state: Optional[dict[str, Any]] = None, host: Optional[str] = None) -> Ctx:
    state = state if state is not None else st.load_state(root, report_id)
    return Ctx(root=root, report_id=report_id, state=state, config=load_config(root), host=detect_host(host, state))


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def src_fingerprint(root: Path, report_id: str) -> Optional[str]:
    """src/<id>/ 下全部 .py 的内容指纹（路径 + 内容），用来判断预跑的验证是否因代码改动而作废。"""
    base = root / "src" / report_id
    if not base.is_dir():
        return None
    digest = hashlib.sha256()
    files = sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    if not files:
        return None
    for path in files:
        digest.update(str(path.relative_to(base)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def write_text(path: Path, text: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return len(text.encode("utf-8"))


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def flow_dir(ctx: Ctx, kind: str) -> str:
    """任务文件 / 回执 / 清单目录（相对工作区根）。"""
    return f"{ctx.ws}/flow/{kind}"


def step_file(ctx: Ctx, kind: str, step: Step, attempt: int, suffix: str) -> str:
    gen = f"g{ctx.generation}." if ctx.generation else ""
    return f"{flow_dir(ctx, kind)}/{gen}{step.file_stem}.{attempt}{suffix}"
