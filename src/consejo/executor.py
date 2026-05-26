"""Executor — modo `auto`: crea rama y commitea tareas SAFE.

Seguridad (ARCHITECTURE.md "Red de seguridad"):
1. SIEMPRE crea rama nueva `consejo/<ts>` — `main` no se toca
2. Commit pre-consejo si hay cambios sin commitear
3. Cada tarea SAFE = 1 commit atómico con `Sabio: <name>` como autor
4. Límite duro de tareas por sesión (default 10)
5. MEDIUM/RISKY NUNCA se ejecutan en auto — quedan en el reporte para revisión

Modo MOCK: commits VACÍOS con el mensaje + autor del sabio. Útil para
verificar el flujo de git sin tocar código real.

Modo REAL: pendiente. Cada tarea SAFE pasaría a un executor agent (Claude
con `Edit`/`Write`) que la implementaría real, una por commit.
"""

from __future__ import annotations

import subprocess
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
    "Council": "council@consejo.local",
}


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def is_git_repo(repo: Path) -> bool:
    try:
        _git(repo, "rev-parse", "--git-dir")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def has_uncommitted_changes(repo: Path) -> bool:
    try:
        return bool(_git(repo, "status", "--porcelain"))
    except subprocess.CalledProcessError:
        return False


def current_branch(repo: Path) -> str:
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def create_council_branch(repo: Path, label: str | None = None) -> str:
    """Crea rama `consejo/<ts>` y la checkoutea. Devuelve el nombre."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    branch = f"consejo/{label or ts}"
    _git(repo, "checkout", "-b", branch)
    return branch


def commit_pre_snapshot(repo: Path) -> str:
    """Snapshot inicial si hay cambios sin commitear. Devuelve hash o ''."""
    if not has_uncommitted_changes(repo):
        return ""
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "consejo: pre-debate snapshot")
    return _git(repo, "rev-parse", "HEAD")


def commit_task_empty(repo: Path, task: dict, sage_name: str) -> str:
    """Commit VACÍO (sin diff) con título de la tarea + autor del sabio.
    Esto es el placeholder mock — en modo real, el executor agent haría el
    diff de verdad antes de commitear."""
    title = task.get("title", "(sin título)")
    rationale = task.get("rationale", "")
    supporting = ", ".join(task.get("supporting_sages", []))
    files = ", ".join(task.get("files_touched", []))
    blast = task.get("blast_radius", "SAFE")
    message = (
        f"[{blast}] {title}\n"
        f"\n{rationale}\n"
        f"\nProposed-by: {supporting}\n"
        f"Files: {files}\n"
        f"\n(mock execution — empty commit; real executor pending)"
    )
    email = SAGE_EMAILS.get(sage_name, "unknown@consejo.local")
    author = f"Sabio: {sage_name} <{email}>"
    _git(repo, "commit", "--allow-empty",
         "--author", author,
         "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def execute_safe_tasks(plan: dict, repo: Path,
                       max_tasks: int = 10,
                       branch_label: str | None = None) -> dict:
    """Ejecuta las tareas SAFE del plan en una rama nueva.

    Devuelve dict con:
      branch_name, original_branch, snapshot_hash, commits[], skipped[],
      branch_label, max_tasks.

    Lanza RuntimeError si el repo no está inicializado con git.
    """
    if not is_git_repo(repo):
        raise RuntimeError(
            f"{repo} no es un repo git. Inicializa con `git init && git add . "
            f"&& git commit -m init` primero."
        )

    safe_tasks = [t for t in plan.get("tasks", [])
                  if t.get("auto_executable") and t.get("blast_radius") == "SAFE"]
    if not safe_tasks:
        return {
            "branch_name": "",
            "original_branch": current_branch(repo),
            "snapshot_hash": "",
            "commits": [],
            "skipped": [t for t in plan.get("tasks", []) if not t.get("auto_executable")],
            "branch_label": branch_label,
            "max_tasks": max_tasks,
            "note": "No SAFE auto_executable tasks; nothing to commit.",
        }

    original_branch = current_branch(repo)
    safe_tasks = safe_tasks[:max_tasks]
    overflow = [t for t in plan["tasks"]
                if t.get("auto_executable") and t.get("blast_radius") == "SAFE"][max_tasks:]
    medium_risky = [t for t in plan["tasks"]
                    if t.get("blast_radius") in ("MEDIUM", "RISKY")]

    branch = create_council_branch(repo, branch_label)
    snapshot_hash = commit_pre_snapshot(repo)

    commits = []
    for task in safe_tasks:
        sages = task.get("supporting_sages", [])
        primary_sage = sages[0] if sages else "Council"
        commit_hash = commit_task_empty(repo, task, primary_sage)
        commits.append({
            "task_title": task["title"],
            "sage": primary_sage,
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
