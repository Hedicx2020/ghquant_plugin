"""任务文件与工单：把步骤表里的一步写成子 agent 读的任务文件，和主会话拿到的工单。

任务文件 = 这一步要做什么 + 要交回什么 + 回执怎么写 + 输入（整读的文件、上下文包）+ 纪律。
角色的不变合同在 agents/<角色>.md，任务文件只写这一步特有的东西。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from . import packs
from .core import PLUGIN_ROOT, ROLE_CN, Ctx, Step, step_file, write_json, write_text
from .kernelsteps import stable_digests

TASK_FORMAT = "flow-task v1"
RECEIPT_FORMAT = "flow-receipt v1"
AS_RESERVE = 5  # 每张会登记新假设的工单预留的假设编号个数

# 只有这两类角色的步骤可以读研报原文转写；其余角色一律经 spec 取信息
SOURCE_TEXT_FILES = ("spec/report_text.md", "spec/tables_extracted.md")
SOURCE_TEXT_STEPS = ("extract.", "spec_audit.internal")
# 任何子 agent 都不该直接读的东西
COMMON_FORBID = (
    "{ws}/state.json",
    "{ws}/events.jsonl",
    "{ws}/board.html",
    "{ws}/reviews/",
    "{out}/results/perturb_check/",
    "{out}/results/cache/",
    "{out}/results_mock/cache/",
)
FORBID_NOTE = "扰动测试的临时产物、运行缓存、ndjson / parquet 文件不要用读文件工具直接打开（要看数据就写脚本取统计量）。"

# 各角色回执里允许出现的字段
RECEIPT_FIELDS: dict[str, tuple[str, ...]] = {
    "quant-coder": ("matrix", "assumptions"),
    "quant-verifier": ("matrix", "assumptions", "verify"),
    "quant-auditor": ("audit",),
    "quant-diagnoser": ("matrix", "assumptions", "diagnosis"),
    "quant-oos-analyst": ("skip",),
    "quant-planner": (),
    "quant-extractor": (),
    "quant-reporter": (),
    "general-purpose": (),
}
RECEIPT_HELP = {
    "matrix": '"matrix": [{"id": "F3", "实现位置": "src/<id>/strategy.py:calc_f3", "状态": "done"}]'
    "  —— 覆盖矩阵的行更新。编码填「实现位置」并把状态推进到 done；验证填「验证结果」；改 skipped / infeasible 必须同时给「状态理由」",
    "assumptions": '"assumptions": {"binding": [{"id": "AS7", "参数绑定": "lookback"}], '
    '"lookback": [{"id": "AS7", "text": "复现 88.85% vs 研报 82.40%，偏差 7.8%，假设获数据支持"}], '
    '"new": [{"id": "<预留编号>", "title": "…", "fields": {"来源": "coder 主动简化", "假设内容": "…", "影响面": "method", "影响 milestone": "m2", "影响指标": "…", "预期影响": "…"}}]}'
    "  —— binding 只有编码可写，lookback 只有验证可写，new 用上面预留给你的编号。"
    "影响面取 param / data / method / trading / output，一条假设跨几个面时用顿号并列（如 `method、data`）；"
    "参数绑定只写 config.py 里的字段名，多个用英文逗号隔开，取值和说明写进假设内容",
    "verify": '"verify": {"verdict": "pass" | "fail", "failures": ["一句话一条"]}  —— 本步验证结论，内核据此决定是否回派修复',
    "audit": '"audit": {"verdict": "pass" | "fail", "critical": 0, "major": 0, "not_found": ["F3"]}  —— 审计结论的计数，明细写在审计文件里',
    "diagnosis": '"diagnosis": {"conclusion": "continue" | "stop_partial" | "blocked"}  —— 与 diagnosis.md 里的「结论:」一致',
    "skip": '"skip": {"reason": "本地没有研报回测区间之后的数据"}  —— 确实做不了时才写，写了就不用交产物',
}


def contract_path(role: str) -> Optional[Path]:
    path = PLUGIN_ROOT / "agents" / f"{role}.md"
    return path if path.is_file() else None


def contract_sha(role: str) -> Optional[str]:
    path = contract_path(role)
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12] if path else None


_CODEX_EXPECTED: Optional[dict[str, str]] = None


def host_agent(ctx: Ctx, role: str, tier: str) -> dict[str, Any]:
    """这张工单在当前宿主上用哪个命名角色（工单的 agent / model 字段）。

    Claude Code：角色名即 agent 名，经济档另给 model。
    Codex：工作区 .codex/agents/<角色>.toml 与合同正本逐字一致才用它（经济档优先用 <角色>-economy）；
    缺失或漂移时 agent 为空并写明原因——主会话改派通用子代理，任务文件开头已要求先读角色合同。
    """
    if not role.startswith("quant-"):
        return {}
    if ctx.host == "claude_code":
        return {"agent": role, **({"model": "sonnet"} if tier == "economy" else {})}
    if ctx.host != "codex":
        return {}
    global _CODEX_EXPECTED
    if _CODEX_EXPECTED is None:
        try:
            from tools import sync_codex_agents as sca

            _CODEX_EXPECTED = sca.expected_files(PLUGIN_ROOT)
        except Exception:  # noqa: BLE001 - 合同正本读不了就不做比对，交给主会话按适配卡处理
            _CODEX_EXPECTED = {}
    directory = ctx.root / ".codex" / "agents"
    for name in ([f"{role}-economy"] if tier == "economy" else []) + [role]:
        want = _CODEX_EXPECTED.get(f"{name}.toml")
        path = directory / f"{name}.toml"
        try:
            if want is not None and path.is_file() and path.read_text(encoding="utf-8") == want:
                return {"agent": name}
        except OSError:
            continue
    return {"agent": None, "agent_fallback": f".codex/agents/{role}.toml 不存在或与合同正本不一致：改派通用子代理（任务文件开头已要求先读角色合同）；重跑 setup 或同步脚本可恢复命名角色"}


def forbid_list(ctx: Ctx, step: Step) -> list[str]:
    """这一步的禁读清单（相对工作区根的路径或目录前缀）。"""
    items = [p.format(ws=ctx.ws, out=ctx.out) for p in COMMON_FORBID]
    if not any(step.id.startswith(prefix) for prefix in SOURCE_TEXT_STEPS):
        items += [f"{ctx.ws}/{name}" for name in SOURCE_TEXT_FILES]
    items += [f"{ctx.ws}/flow/tasks/", f"{ctx.ws}/flow/receipts/"]  # 别的步骤的任务文件与回执
    return items + list(step.forbid)


def escape_hatch(ctx: Ctx, step_id: str) -> str:
    flow_py = PLUGIN_ROOT / "tools" / "flow.py"
    return f'REPORT_REPRODUCE_ROOT="{ctx.root}" uv run python "{flow_py}" get {ctx.report_id} <element|assumption|matrix-row> <编号> --step {step_id}'


def build_pack(ctx: Ctx, step: Step) -> Optional[packs.Pack]:
    """这一步的上下文包；拼不出来（文书不全）时返回 None，任务文件退回整读原始文书。"""
    if not step.pack:
        return None
    role, pack_step = step.pack
    try:
        docs = packs.CaseDocs.load(ctx.root, ctx.report_id)
        pack = packs.build_pack(docs, role, pack_step)
    except packs.PackError:
        return None
    return None if packs.verify_pack(docs, pack) else pack


def reserve_assumption_ids(ctx: Ctx, step: Step, prior: Optional[list[str]] = None) -> list[str]:
    """给会登记新假设的工单预留编号。预留只前进不回收，并行的工单拿到的区间互不重叠。

    同一步重派时沿用上一次的区间（prior），只要里面的编号都还没进登记簿：上一次写下的代码注释和
    回执用的就是这些编号，换一段等于逼着接手的人把它们全改一遍，回执也没法照着上一份改。
    """
    if step.role not in ("quant-coder", "quant-diagnoser") or step.receipt == "none":
        return []
    docs = packs.CaseDocs.load(ctx.root, ctx.report_id)
    if prior and not {b.id for b in docs.assumption_blocks} & set(prior):
        return list(prior)
    used = max((int(b.number) for b in docs.assumption_blocks if b.number.isdigit()), default=0)
    start = max(used, int(ctx.flow.get("as_reserved") or 0)) + 1
    return [f"AS{n}" for n in range(start, start + AS_RESERVE)]


def render_task(
    ctx: Ctx,
    step: Step,
    attempt: int,
    *,
    redo: Optional[dict[str, Any]] = None,
    reserved: Optional[list[str]] = None,
    receipt_rel: Optional[str] = None,
    pack: Optional[packs.Pack] = None,
    notes: Optional[str] = None,
) -> str:
    """任务文件正文。"""
    role_cn = ROLE_CN.get(step.role, step.role)
    lines = [
        f"# 任务：{step.title or step.id}",
        "",
        f"- 格式：{TASK_FORMAT}",
        f"- 案例：`{ctx.report_id}`；步骤：`{step.id}`；第 {attempt} 次派发；角色：{role_cn}（`{step.role}`）",
    ]
    contract = contract_path(step.role)
    if contract:
        lines.append(f"- 角色合同：`{contract}`（哈希 {contract_sha(step.role)}）。你不是以这个角色启动的话，先读它，再做下面的事。")
    if ctx.trial:
        lines.append("- **本案例处于 mock 试跑模式**：数据里有模拟数据，结果只用来确认代码和流水线跑得通，不出任何结论。结果目录是 `" + ctx.results + "/`。")
    if ctx.experimental:
        lines.append("- 本案例是实验模式（市场迁移复现）：原文数值只作对照，不要求对齐。")

    lines += ["", "## 这一步要做什么", "", step.instruction.strip() or "按角色合同完成本步。"]
    if redo:
        lines += ["", "### 这是重派，原因如下", "", f"{redo.get('reason', '')}".strip()]
        if redo.get("detail"):
            lines += ["", "```", str(redo["detail"]).strip(), "```"]
        lines += ["", str(redo.get("hint") or "只处理上面指出的问题；与它无关的内容不要动。")]
    if notes:
        lines += ["", "### 本轮的修订要求", "", notes.strip()]

    if step.outputs:
        lines += ["", "## 你要交回的文件", ""] + [f"- `{path}`" for path in step.outputs]
    if step.writes:
        lines += ["", "你只可以改动这些路径（其余一律只读）：", ""] + [f"- `{path}`" for path in step.writes]

    fields = RECEIPT_FIELDS.get(step.role, ())
    if step.receipt != "none" and receipt_rel:
        must = "必须" if step.receipt == "required" else "请"
        lines += [
            "",
            "## 回执",
            "",
            f"做完后{must}把回执写到 `{receipt_rel}`（JSON）。"
            + (
                "覆盖矩阵、假设登记簿的回填都写在回执里，**不要直接改那两份文件**，内核会核对后替你合并。"
                if {"matrix", "assumptions"} & set(fields)
                else ""
            ),
            "",
            "```json",
            json.dumps({"format": RECEIPT_FORMAT, "step": step.id, "status": "done", "summary": "一两句话说明做了什么"}, ensure_ascii=False, indent=2),
            "```",
            "",
            "`status` 取 `done` 或 `blocked`（受阻时在 `summary` 里写清卡在哪）。按需追加下面这些字段：",
            "",
        ]
        lines += [f"- {RECEIPT_HELP[name]}" for name in fields] or ["- （本角色没有需要回填的内容，只写上面三项即可）"]
        if reserved:
            lines += ["", f"预留给你的新假设编号：{reserved[0]}–{reserved[-1]}（用不完不要紧，不要用区间之外的编号）。"]

    lines += ["", "## 输入"]
    if step.reads:
        lines += ["", "整读这些文件：", ""] + [f"- `{path}`" for path in step.reads]
    if pack is not None:
        lines += [
            "",
            f"下面是内核为这一步切好的上下文包（{pack.nbytes / 1024:.0f}KB，原始文书全量约 {pack.full_bytes / 1024:.0f}KB）。包里的每一段都是原文的逐字摘录；"
            "**与原文冲突时以原文为准**。包里没有而你确实需要的要素、假设、矩阵行，用下面的命令取，不要整读原始文书：",
            "",
            "```bash",
            escape_hatch(ctx, step.id),
            "```",
            "",
            "---",
            "",
            pack.render().rstrip(),
            "",
            "---",
        ]
    elif step.pack:
        lines += ["", "（这一步的上下文包没有拼出来，请按角色合同整读 spec.md、coverage_matrix.md、assumptions.md、plan.md。）"]

    # 禁读清单里有任务文件与回执所在的两个目录（防的是看别的步骤的东西）；写给子 agent 看时要说清楚
    # 「你自己这一步的不算」，否则它刚被要求读这份任务文件、写那份回执，下面又说这两个目录不要读。
    own_dirs = (f"{ctx.ws}/flow/tasks/", f"{ctx.ws}/flow/receipts/")
    lines += ["", "## 纪律", ""]
    lines += [f"- 不要读：`{path}`" for path in forbid_list(ctx, step) if path not in own_dirs]
    lines += [
        f"- 不要读别的步骤的任务文件与回执（`{own_dirs[0]}`、`{own_dirs[1]}` 下除你自己这一步以外的文件）。",
        f"- {FORBID_NOTE}",
        "- 运行类命令的输出重定向到日志文件，只看尾部和关键行，不要把整段输出读进上下文。",
        "- 不要碰 `state.json`，"
        + ("不要调用 `tools/` 下除上面那条取块命令以外的任何脚本" if pack is not None else "不要调用 `tools/` 下的任何脚本")
        + "，不要再派发子 agent。",
        "- 做完后对主会话只回一行：`DONE`，或 `BLOCKED: <一句话原因>`。详细内容写在交回的文件和回执里。",
    ]
    return "\n".join(lines) + "\n"


def make_order(ctx: Ctx, step: Step, attempt: int, prompt_rel: Optional[str], receipt_rel: Optional[str]) -> dict[str, Any]:
    """主会话拿到的工单。"""
    order: dict[str, Any] = {
        "step_id": f"{step.id}#{attempt}",
        "kind": step.kind,
        "stage": step.stage,
        "role": step.role,
        "title": step.title or step.id,
        "description": step.id,  # 派发描述 / 任务名必须等于它，用量按它对账
        "model_tier": ctx.model_tier(step.role),
        "prompt_file": prompt_rel,
        "outputs": list(step.outputs),
        "writes": list(step.writes),
        "receipt": receipt_rel,
        "parallel_group": step.parallel_group,
    }
    if step.milestone:
        order["milestone"] = step.milestone
    if step.kind == "dispatch":
        sha = contract_sha(step.role)
        if sha:
            order["contract"] = {"file": str(contract_path(step.role)), "sha": sha}
        order.update(host_agent(ctx, step.role, order["model_tier"]))
        order["prompt_inline"] = (
            f"读取任务文件 {ctx.root / prompt_rel} 并严格按它执行。最终只回一行：DONE，或 BLOCKED: <原因>。"
        )
    elif step.kind == "judge":
        order["answer_file"] = step.extra.get("answer_file")
        order["prompt_inline"] = (
            f"这一步要你自己判断：读 {ctx.root / prompt_rel}，把答卷按其中的格式写到 {step.extra.get('answer_file')}，"
            f"然后执行 flow done {ctx.report_id} {step.id}。"
        )
    elif step.kind == "exec":
        flow_py = PLUGIN_ROOT / "tools" / "flow.py"
        order["command"] = f'REPORT_REPRODUCE_ROOT="{ctx.root}" uv run python "{flow_py}" exec {ctx.report_id} {step.id} --detach'
        order["prompt_inline"] = "执行 command 启动后台外审，然后用 flow wait 等结果；不用派子 agent。"
    order.update({k: v for k, v in step.extra.items() if k in ("job_id", "question", "fallback_of")})
    return order


def write_task(
    ctx: Ctx,
    step: Step,
    attempt: int,
    *,
    redo: Optional[dict[str, Any]] = None,
    notes: Optional[str] = None,
    body: Optional[str] = None,
    prior_reserved: Optional[list[str]] = None,
) -> dict[str, Any]:
    """写任务文件、清单与工单，返回 {order, task_bytes, reserved, manifest}。"""
    prompt_rel = step_file(ctx, "tasks", step, attempt, ".md")
    receipt_rel = None if step.receipt == "none" else step_file(ctx, "receipts", step, attempt, ".json")
    manifest_rel = step_file(ctx, "manifests", step, attempt, ".json")
    pack = build_pack(ctx, step) if step.kind == "dispatch" else None
    reserved = reserve_assumption_ids(ctx, step, prior_reserved) if step.kind == "dispatch" else []
    text = body if body is not None else render_task(
        ctx, step, attempt, redo=redo, reserved=reserved, receipt_rel=receipt_rel, pack=pack, notes=notes
    )
    task_bytes = write_text(ctx.root / prompt_rel, text)
    order = make_order(ctx, step, attempt, prompt_rel, receipt_rel)
    manifest: dict[str, Any] = {
        "step": step.id,
        "attempt": attempt,
        "role": step.role,
        "stage": step.stage,
        "milestone": step.milestone,
        "task_file": prompt_rel,
        "task_bytes": task_bytes,
        "reads": list(step.reads),
        "outputs": list(step.outputs),
        "writes": list(step.writes),
        "forbid": forbid_list(ctx, step) if step.kind == "dispatch" else [],
        "reserved_assumptions": reserved,
        "pack": pack.manifest() if pack is not None else None,
        "pack_stable": stable_digests(pack) if pack is not None else None,
        "order": order,
    }
    write_json(ctx.root / manifest_rel, manifest)
    if receipt_rel:
        (ctx.root / receipt_rel).parent.mkdir(parents=True, exist_ok=True)
    return {"order": order, "task_bytes": task_bytes, "reserved": reserved, "manifest": manifest_rel, "receipt": receipt_rel, "prompt": prompt_rel}
