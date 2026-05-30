"""Deterministic repo enumeration — the ground-truth worklist of source files.

One responsibility: list every source file in a repo (and hash it), deterministically
and without an LLM. `git ls-files` when the target is a git toplevel (so .gitignore
drops vendored/build trees for free), an `os.walk` with dir-pruning otherwise.

This was extracted from the old `analysis.py` (the LLM coverage pass, since replaced
by `repo_skeleton`). The enumerator is the one piece of that module still needed:
`repo_skeleton` builds on it to map and score the repo.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Mirrors orchestrator.SCAN_* deliberately; kept local so this low-level module
# has no dependency back on the orchestrator.
SCAN_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".toml",
                   ".yaml", ".yml", ".json"}
SCAN_EXCLUDE_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__",
                     "build", "dist", ".pytest_cache", ".mypy_cache",
                     ".ruff_cache", "assets", ".consejo"}


@dataclass
class FileUnit:
    """One source file: its repo-relative path, size, and content hash. The hash
    lets callers detect when a file's content changed between runs."""
    path: str            # repo-relative, forward-slash
    size_bytes: int
    content_hash: str    # sha1 of the file bytes


def _git_listed_files(repo: Path) -> list[str] | None:
    """Repo-relative source paths via git, or None if git can't authoritatively
    enumerate `repo` (so the caller falls back to a filesystem walk).

    Returns None unless `repo` is the TOPLEVEL of its own git repo: from a
    subdirectory, `git ls-files` reports the PARENT repo's files, which is wrong
    when the target is a nested directory (or a pytest tmp dir living inside
    another repo). Combines tracked files with untracked-but-not-ignored ones
    (`--others --exclude-standard`) so new, uncommitted source is covered too.
    git's .gitignore handling drops vendored/build trees for free; SCAN_EXCLUDE_DIRS
    is a belt-and-suspenders second filter."""
    try:
        top = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if top.returncode != 0:
        return None
    try:
        if Path(top.stdout.strip()).resolve() != repo.resolve():
            return None  # repo is nested in a bigger repo → walk it instead
    except OSError:
        return None

    paths: set[str] = set()
    for extra in ([], ["--others", "--exclude-standard"]):
        try:
            r = subprocess.run(
                ["git", "-C", str(repo), "ls-files", *extra],
                capture_output=True, text=True, timeout=30,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return None
        if r.returncode != 0:
            return None
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            p = Path(line)
            if p.suffix not in SCAN_EXTENSIONS:
                continue
            if set(p.parts) & SCAN_EXCLUDE_DIRS:
                continue
            paths.add(line)
    return sorted(paths)


def _walk_files(repo: Path) -> list[str]:
    """Fallback enumeration for non-git repos: os.walk with dir pruning."""
    out: list[str] = []
    for root, dirnames, fnames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in SCAN_EXCLUDE_DIRS]
        for fname in fnames:
            p = Path(root) / fname
            if p.suffix not in SCAN_EXTENSIONS:
                continue
            out.append(p.relative_to(repo).as_posix())
    return out


def enumerate_units(repo: Path) -> list[FileUnit]:
    """The ground-truth worklist: every source file, hashed. Deterministic, no
    LLM. This — not a model's judgement — defines the scope the council sees."""
    paths = _git_listed_files(repo)
    if paths is None:
        paths = _walk_files(repo)
    units: list[FileUnit] = []
    for rel in sorted(set(paths)):
        try:
            data = (repo / rel).read_bytes()
        except OSError:
            continue
        units.append(FileUnit(
            path=rel,
            size_bytes=len(data),
            content_hash=hashlib.sha1(data).hexdigest(),
        ))
    return units
