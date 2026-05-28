"""Executor — modo `auto`: crea rama y commitea tareas SAFE.

Seguridad (ARCHITECTURE.md "Red de seguridad"):
1. SIEMPRE crea rama nueva `consejo/<ts>` — `main` no se toca
2. Commit pre-consejo si hay cambios sin commitear
3. Cada tarea SAFE = 1 commit atómico con `Sabio: <name>` como autor
4. Límite duro de tareas por sesión (default 10)
5. MEDIUM/RISKY NUNCA se ejecutan en auto — quedan en el reporte para revisión
6. Phase D hardening: model output is treated as untrusted — every string
   passed to git is sanitized (control chars stripped, length-capped,
   author headers normalized) and files_touched is asserted to live inside
   `repo` before being mentioned.

Phase D async: subprocess calls use `asyncio.create_subprocess_exec` so the
Rich Live animator's event loop is never blocked by git I/O.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path

SAGE_EMAILS = {
    "Architect": "architect@consejo.local",
    "Conservative": "conservative@consejo.local",
    "Modernizer": "modernizer@consejo.local",
    "Simplifier": "simplifier@consejo.local",
    "Guardian": "guardian@consejo.local",
    "Optimizer": "optimizer@consejo.local",
    "Ambassador": "ambassador@consejo.local",
    "Designer": "designer@consejo.local",
    "Strategist": "strategist@consejo.local",
    "Council": "council@consejo.local",
}

_TITLE_MAX = 200
_RATIONALE_MAX = 1500
_FILES_MAX_PER_TASK = 10
_FILE_PATH_MAX = 300
_AUTHOR_NAME_MAX = 80
_GIT_TIMEOUT_S = 30.0


def _strip_controls(s: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", s)


def _clamp(s: str, n: int) -> str:
    return s[:n].rstrip()


def _safe_inline(s: str, n: int) -> str:
    return _clamp(_strip_controls(s or ""), n)


def _safe_multiline(s: str, n: int) -> str:
    cleaned = re.sub(r"[\x00\x7f]", "", s or "")
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    return _clamp(cleaned, n)


def _safe_files_in_repo(repo: Path, files: list) -> list[str]:
    if not isinstance(files, list):
        return []
    repo_resolved = repo.resolve()
    safe: list[str] = []
    for raw in files[:_FILES_MAX_PER_TASK]:
        if not isinstance(raw, str):
            continue
        raw = _safe_inline(raw, _FILE_PATH_MAX)
        if not raw:
            continue
        try:
            candidate = (repo / raw).resolve()
            candidate.relative_to(repo_resolved)
        except (ValueError, OSError):
            continue
        safe.append(raw)
    return safe


def _safe_author(sage_name: str) -> tuple[str, str]:
    name = _safe_inline(sage_name or "Council", _AUTHOR_NAME_MAX)
    if not name:
        name = "Council"
    email = SAGE_EMAILS.get(name, "unknown@consejo.local")
    return name, email


def _validate_repo(repo: Path) -> Path:
    if not repo.exists():
        raise RuntimeError(f"repo path does not exist: {repo}")
    if not repo.is_dir():
        raise RuntimeError(f"repo path is not a directory: {repo}")
    if repo.is_symlink():
        raise RuntimeError(f"repo path is a symlink (refusing): {repo}")
    return repo


async def _git(repo: Path, *args: str, check: bool = True) -> str:
    """Async git call via create_subprocess_exec — never blocks the event loop."""
    proc = await asyncio.create_subprocess_exec(
        "git", "-C", str(repo), *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(_GIT_TIMEOUT_S):
            stdout, stderr = await proc.communicate()
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"git {' '.join(args[:2])} timed out") from None
    if check and proc.returncode != 0:
        err = (stderr or b"").decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"git failed (exit {proc.returncode}): {err}")
    return (stdout or b"").decode("utf-8", errors="replace").strip()


async def is_git_repo(repo: Path) -> bool:
    try:
        _validate_repo(repo)
        await _git(repo, "rev-parse", "--git-dir")
        return True
    except (RuntimeError, FileNotFoundError):
        return False


async def has_uncommitted_changes(repo: Path) -> bool:
    try:
        return bool(await _git(repo, "status", "--porcelain"))
    except RuntimeError:
        return False


async def current_branch(repo: Path) -> str:
    return await _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


async def create_council_branch(repo: Path, label: str | None = None) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "-", label or ts).strip("-")[:60] or ts
    branch = f"consejo/{safe_label}"
    await _git(repo, "checkout", "-b", branch)
    return branch


async def commit_pre_snapshot(repo: Path) -> str:
    if not await has_uncommitted_changes(repo):
        return ""
    await _git(repo, "add", "-A")
    await _git(repo, "commit", "-m", "consejo: pre-debate snapshot")
    return await _git(repo, "rev-parse", "HEAD")


async def commit_task_empty(repo: Path, task: dict, sage_name: str) -> str:
    title = _safe_inline(task.get("title", "(sin título)"), _TITLE_MAX)
    rationale = _safe_multiline(task.get("rationale", ""), _RATIONALE_MAX)
    supporting_raw = task.get("supporting_sages", [])
    supporting_clean = [
        _safe_inline(s, _AUTHOR_NAME_MAX)
        for s in supporting_raw if isinstance(s, str)
    ]
    supporting = ", ".join(s for s in supporting_clean if s)[:400]
    files_clean = _safe_files_in_repo(repo, task.get("files_touched", []))
    files = ", ".join(files_clean)[:600]
    blast = task.get("blast_radius", "SAFE")
    if blast not in ("SAFE", "MEDIUM", "RISKY"):
        blast = "SAFE"
    message = (
        f"[{blast}] {title}\n"
        f"\n{rationale}\n"
        f"\nProposed-by: {supporting}\n"
        f"Files: {files}\n"
        f"\n(mock execution — empty commit; real executor pending)"
    )
    name, email = _safe_author(sage_name)
    author = f"Sabio: {name} <{email}>"
    await _git(repo, "commit", "--allow-empty",
               "--author", author,
               "-m", message)
    return await _git(repo, "rev-parse", "HEAD")


async def execute_safe_tasks(plan: dict, repo: Path,
                             max_tasks: int = 10,
                             branch_label: str | None = None) -> dict:
    """Ejecuta las tareas SAFE del plan en una rama nueva. Async — no bloquea
    el event loop ni la animación Rich Live durante los commits.
    """
    _validate_repo(repo)
    if not await is_git_repo(repo):
        raise RuntimeError(
            f"{repo} no es un repo git. Inicializa con `git init && git add . "
            f"&& git commit -m init` primero."
        )

    safe_tasks = [t for t in plan.get("tasks", [])
                  if t.get("auto_executable") and t.get("blast_radius") == "SAFE"]
    if not safe_tasks:
        return {
            "branch_name": "",
            "original_branch": await current_branch(repo),
            "snapshot_hash": "",
            "commits": [],
            "skipped": [t for t in plan.get("tasks", []) if not t.get("auto_executable")],
            "branch_label": branch_label,
            "max_tasks": max_tasks,
            "note": "No SAFE auto_executable tasks; nothing to commit.",
        }

    original_branch = await current_branch(repo)
    safe_tasks = safe_tasks[:max_tasks]
    overflow = [t for t in plan["tasks"]
                if t.get("auto_executable") and t.get("blast_radius") == "SAFE"][max_tasks:]
    medium_risky = [t for t in plan["tasks"]
                    if t.get("blast_radius") in ("MEDIUM", "RISKY")]

    branch = await create_council_branch(repo, branch_label)
    snapshot_hash = await commit_pre_snapshot(repo)

    commits = []
    for task in safe_tasks:
        sages = task.get("supporting_sages", [])
        primary_sage = sages[0] if sages else "Council"
        commit_hash = await commit_task_empty(repo, task, primary_sage)
        commits.append({
            "task_title": _safe_inline(task["title"], _TITLE_MAX),
            "sage": _safe_inline(primary_sage, _AUTHOR_NAME_MAX),
            "hash": commit_hash[:12],
            "blast_radius": task["blast_radius"],
        })

    return {
        "branch_name": branch,
        "original_branch": original_branch,
        "snapshot_hash": snapshot_hash[:12] if snapshot_hash else "",
        "commits": commits,
        "skipped": overflow + medium_risky,
        "branch_label": branch_label,
        "max_tasks": max_tasks,
    }
