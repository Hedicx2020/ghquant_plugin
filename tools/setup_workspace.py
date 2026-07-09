"""用户工作目录初始化工具（插件形态 B 的 /reproduce setup 后端）。

职责（全部幂等，可重复运行）：
1. 生成 `.reproduce.json` 配置（数据路径 / 执行模式 / 最大迭代次数 / 插件根记录）
2. 种子拷贝：插件根的 `templates/`、`common/` → 用户目录（已存在文件跳过，列「插件侧较新」清单）
3. 生成精简 `pyproject.toml`（目标目录无该文件时）
4. 建目录树：`reports/ workspace/ src/ output/`（含 .gitkeep）
5. 环境检测（只报告不阻塞）：uv / Python 依赖 / codex CLI

设计依据：docs/specs/2026-07-09-plugin-packaging-design.md §四、§五、§七。
本工具只被主会话（编排者）调用；子 agent 不得导入。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

CONFIG_NAME = ".reproduce.json"
CONFIG_VERSION = 1
SEED_DIRS = ("templates", "common")
WORK_DIRS = ("reports", "workspace", "src", "output")
VALID_MODES = ("auto", "interactive")

# 与插件根 pyproject.toml 的 dependencies 保持同步（设计 §七）
RUNTIME_DEPS = [
    "pandas>=2.0",
    "numpy>=1.24",
    "scipy>=1.10",
    "matplotlib>=3.7",
    "seaborn>=0.12",
    "openpyxl>=3.1",
    "pyarrow>=14.0",
    "pypdf>=4.0",
    "pdfplumber>=0.11",
    "pyyaml>=6.0",
]
# 依赖检测用的顶层 import 名（与 RUNTIME_DEPS 一一对应）
IMPORT_NAMES = [
    "pandas", "numpy", "scipy", "matplotlib", "seaborn",
    "openpyxl", "pyarrow", "pypdf", "pdfplumber", "yaml",
]


def plugin_root() -> Path:
    """插件根 = 本文件所在 tools/ 的上一级。"""
    return Path(__file__).resolve().parent.parent


@dataclass
class SetupReport:
    """一次 setup 运行的结果汇总（人读 + --json 机器可读）。"""

    target: str
    config_action: str = ""            # created / kept / overwritten
    config: dict | None = None
    copied: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    plugin_newer: list[str] = field(default_factory=list)   # 用户侧已存在但插件侧 mtime 更新
    pyproject_action: str = ""         # created / kept
    dirs_created: list[str] = field(default_factory=list)
    env: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, indent=2)

    def render_text(self) -> str:
        lines = [f"目标目录: {self.target}"]
        lines.append(f"配置文件 {CONFIG_NAME}: {self.config_action}")
        if self.config:
            lines.append(f"  data_root={self.config['data_root']}  default_mode={self.config['default_mode']}  "
                         f"default_max_iter={self.config['default_max_iter']}")
            bf = self.config.get("backtest_framework")
            lines.append(f"  backtest_framework={bf or '（未指定，使用内置 common/ 回测框架）'}")
            mrd = self.config.get("default_max_rel_dev")
            lines.append(f"  default_max_rel_dev={f'{mrd}（所有相对偏差判定统一用此容忍度）' if mrd is not None else '（未指定，按 templates/standards.json 分类型精细容差）'}")
            lines.append(f"  economy={self.config.get('economy', False)}（true 时机械性角色 extractor/verifier/oos-analyst 派发降为 sonnet）  audit_level={self.config.get('audit_level', 'strict')}（standard 时 spec/code 外审改触发式，result 外审任何档位必跑）")
        lines.append(f"种子拷贝: 新拷 {len(self.copied)} 个，已存在跳过 {len(self.skipped_existing)} 个")
        if self.plugin_newer:
            lines.append("  [提示] 以下文件插件侧较新（未覆盖，需人工决定是否同步）:")
            lines.extend(f"    - {p}" for p in self.plugin_newer)
        lines.append(f"pyproject.toml: {self.pyproject_action}")
        if self.dirs_created:
            lines.append(f"目录树新建: {', '.join(self.dirs_created)}")
        env = self.env
        if env:
            lines.append("环境检测:")
            lines.append(f"  uv: {env.get('uv') or '未找到（请先安装 uv: https://docs.astral.sh/uv/）'}")
            missing = env.get("missing_deps", [])
            if missing:
                lines.append(f"  Python 依赖缺失 {len(missing)} 个: {', '.join(missing)}")
                lines.append("    → 在目标目录运行: uv sync")
            else:
                lines.append("  Python 依赖: 全部可导入")
            if env.get("codex"):
                lines.append(f"  codex CLI: {env['codex']}（外审三审查点可用；运行中额度耗尽会自动降级为 Claude 替身盲审，不断链）")
            else:
                lines.append("  codex CLI: 未找到 → 外审自动降级为 Claude 替身盲审（审查照跑、意见照样逐条回应；替身也不可行才 skipped），最终报告可信度封顶 B；装好后无需重新 setup，下次运行自动启用")
        return "\n".join(lines)


def _now_iso() -> str:
    """本地时区 ISO 时间戳（秒级）。"""
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def write_config(target: Path, data_root: str, mode: str, max_iter: int | None,
                 backtest_framework: str | None, max_rel_dev: float | None,
                 economy: bool, audit_level: str,
                 force: bool, report: SetupReport) -> None:
    cfg_path = target / CONFIG_NAME
    existed = cfg_path.is_file()
    if existed and not force:
        report.config_action = "kept"
        report.config = json.loads(cfg_path.read_text(encoding="utf-8"))
        return
    if mode not in VALID_MODES:
        raise SystemExit(f"default_mode 必须是 {VALID_MODES} 之一，收到: {mode}")
    if max_iter is not None and not (1 <= max_iter <= 10):
        raise SystemExit(f"default_max_iter 必须在 1-10 之间或留空（按难度矩阵），收到: {max_iter}")
    if backtest_framework is not None and not Path(backtest_framework).expanduser().is_dir():
        raise SystemExit(f"backtest_framework 路径不存在或不是目录: {backtest_framework}（留空则使用内置 common/ 回测框架）")
    if max_rel_dev is not None and not (0.005 <= max_rel_dev <= 0.5):
        raise SystemExit(f"default_max_rel_dev 必须在 0.005-0.5（即 0.5%-50%）之间或留空（按 standards.json 分类型精细容差），收到: {max_rel_dev}")
    if audit_level not in ("strict", "standard"):
        raise SystemExit(f"audit_level 必须是 strict|standard，收到: {audit_level}")
    config = {
        "data_root": data_root,
        "default_mode": mode,
        "default_max_iter": max_iter,
        "backtest_framework": backtest_framework,
        "default_max_rel_dev": max_rel_dev,
        "economy": economy,
        "audit_level": audit_level,
        "plugin_root": str(plugin_root()),
        "created_at": _now_iso(),
        "config_version": CONFIG_VERSION,
    }
    cfg_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.config_action = "overwritten" if existed else "created"
    report.config = config


def copy_seeds(target: Path, report: SetupReport) -> None:
    """种子拷贝：已存在的用户侧文件一律不覆盖（用户可能已定制）。"""
    root = plugin_root()
    for seed in SEED_DIRS:
        src_dir = root / seed
        if not src_dir.is_dir():
            continue
        for src in sorted(src_dir.rglob("*")):
            if src.is_dir() or "__pycache__" in src.parts:
                continue
            rel = src.relative_to(root)
            dst = target / rel
            if dst.exists():
                report.skipped_existing.append(str(rel))
                if src.stat().st_mtime > dst.stat().st_mtime:
                    report.plugin_newer.append(str(rel))
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            report.copied.append(str(rel))


def write_pyproject(target: Path, report: SetupReport) -> None:
    pp = target / "pyproject.toml"
    if pp.is_file():
        report.pyproject_action = "kept"
        return
    name = target.resolve().name.replace("_", "-").replace(" ", "-").lower() or "report-reproduce-workspace"
    deps = "\n".join(f'    "{d}",' for d in RUNTIME_DEPS)
    pp.write_text(
        "[project]\n"
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
        'description = "研报复现工作目录（quant-report-reproduce 插件初始化）"\n'
        'requires-python = ">=3.10"\n'
        "dependencies = [\n"
        f"{deps}\n"
        "]\n\n"
        "[project.optional-dependencies]\n"
        "# ML 类研报按需安装：uv sync --extra ml\n"
        'ml = ["scikit-learn>=1.3", "lightgbm>=4.0", "torch>=2.0"]\n',
        encoding="utf-8",
    )
    report.pyproject_action = "created"


def make_dirs(target: Path, report: SetupReport) -> None:
    for d in WORK_DIRS:
        p = target / d
        if not p.is_dir():
            p.mkdir(parents=True)
            report.dirs_created.append(d)
        keep = p / ".gitkeep"
        if not any(p.iterdir()):
            keep.touch()


def check_env(target: Path, report: SetupReport) -> None:
    env: dict = {}
    env["uv"] = shutil.which("uv")
    env["codex"] = shutil.which("codex")
    missing: list[str] = []
    if env["uv"]:
        probe = "\n".join(
            f"try:\n import {m}\nexcept Exception:\n print('MISS:{m}')" for m in IMPORT_NAMES
        )
        proc = subprocess.run(
            ["uv", "run", "--no-sync", "python", "-c", probe],
            capture_output=True, text=True, cwd=target, timeout=120,
        )
        if proc.returncode == 0:
            missing = [ln.removeprefix("MISS:") for ln in proc.stdout.splitlines() if ln.startswith("MISS:")]
        else:
            # venv 尚未创建等情况：全部按缺失报告，指引 uv sync
            missing = list(IMPORT_NAMES)
    env["missing_deps"] = missing
    report.env = env


def run_setup(target: Path, data_root: str, mode: str, max_iter: int | None,
              force_config: bool, check_only: bool,
              backtest_framework: str | None = None,
              max_rel_dev: float | None = None,
              economy: bool = False,
              audit_level: str = "strict") -> SetupReport:
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    report = SetupReport(target=str(target))
    if not check_only:
        write_config(target, data_root, mode, max_iter, backtest_framework, max_rel_dev, economy, audit_level, force_config, report)
        copy_seeds(target, report)
        write_pyproject(target, report)
        make_dirs(target, report)
    check_env(target, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="研报复现插件：用户工作目录初始化（幂等）")
    parser.add_argument("--target", default=".", help="用户工作目录（默认当前目录）")
    parser.add_argument("--data-root", default="~/local_data", help="本地 parquet 数据根目录（默认 ~/local_data）")
    parser.add_argument("--mode", default="auto", choices=VALID_MODES, help="默认执行模式（auto=全自动优先 / interactive=blocking 歧义人工裁决）")
    parser.add_argument("--max-iter", default=None, help="默认最大迭代次数 1-10；留空=按难度矩阵 easy3/medium5/hard6")
    parser.add_argument("--backtest-framework", default=None,
                        help="用户自有回测框架目录路径（复现代码优先复用其中实现）；留空=使用内置 common/ 回测框架")
    parser.add_argument("--economy", action="store_true",
                        help="经济模式：机械性角色（extractor/verifier/oos-analyst）派发降为 sonnet，质量敏感角色保持 opus")
    parser.add_argument("--audit-level", default="strict", choices=["strict", "standard"],
                        help="外审档位：strict=codex 三审查点全跑（默认）；standard=spec/code 审查点触发式、result 必跑")
    parser.add_argument("--max-rel-dev", default=None,
                        help="可接受的与原报告的偏差（小数，0.005-0.5，如 0.1=10%%，对所有相对偏差判定统一生效）；留空=按 standards.json 分类型精细容差")
    parser.add_argument("--force-config", action="store_true", help="覆盖已存在的 .reproduce.json（默认保留）")
    parser.add_argument("--check-only", action="store_true", help="只做环境检测，不落任何文件")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON 摘要")
    args = parser.parse_args(argv)

    max_iter: int | None
    if args.max_iter in (None, "", "auto", "null"):
        max_iter = None
    else:
        try:
            max_iter = int(args.max_iter)
        except ValueError:
            parser.error(f"--max-iter 需要整数或留空，收到: {args.max_iter}")

    backtest_framework = args.backtest_framework or None

    max_rel_dev: float | None
    if args.max_rel_dev in (None, "", "auto", "null"):
        max_rel_dev = None
    else:
        try:
            max_rel_dev = float(args.max_rel_dev)
        except ValueError:
            parser.error(f"--max-rel-dev 需要小数或留空，收到: {args.max_rel_dev}")

    report = run_setup(
        target=Path(args.target),
        data_root=args.data_root,
        mode=args.mode,
        max_iter=max_iter,
        force_config=args.force_config,
        check_only=args.check_only,
        backtest_framework=backtest_framework,
        max_rel_dev=max_rel_dev,
        economy=args.economy,
        audit_level=args.audit_level,
    )
    print(report.to_json() if args.json else report.render_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
