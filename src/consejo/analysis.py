"""Analysis pass: deterministic, COMPLETE repo coverage feeding the council.

The council's failure mode is *satisficing* — it reads the README plus a few
"important" files, forms an opinion on a keyhole view of the repo, and leaves
the other 98% unseen until it has to implement something there. The fix is
architectural: **completeness must be a property of an orchestration LOOP driven
by a deterministic enumerator, never the model's judgement.**

Two concerns are kept strictly separate (today they are fused — the model's
prioritisation IS its coverage, so the unprioritised 98% is invisible):

  - **WHAT to cover** — mechanical & exhaustive. `enumerate_units` lists every
    source file from `git ls-files`; the ledger tracks each file's status. The
    model NEVER chooses scope.
  - **WHAT matters** — selective & with judgement. The analyzer agent reads each
    batch and records findings. But the loop feeds it EVERY file until the
    ledger is 100% green; the agent can't quietly skip the boring files because
    a per-batch receipt check re-queues anything it fails to account for.

The ledger persists in ``<repo>/.consejo/analysis-ledger.json`` keyed by content
hash, so a re-run only re-analyses files whose content changed (freshness by
hash). No silent truncation: files the analyzer keeps dropping after a bounded
number of retries are recorded explicitly as unanalysed, never hidden.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .driver_protocol import SageDriver
from .schemas import ANALYSIS_SCHEMA

# Kept local (not imported from orchestrator) so this lower-level module has no
# dependency back on the orchestrator — orchestrator imports analysis, not the
# reverse. Mirrors orchestrator.SCAN_* deliberately.
SCAN_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".toml",
                   ".yaml", ".yml", ".json"}
SCAN_EXCLUDE_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__",
                     "build", "dist", ".pytest_cache", ".mypy_cache",
                     ".ruff_cache", "assets", ".consejo"}

# A batch must fit comfortably in the analyzer's context with room for its
# reasoning. Bytes is the real constraint (15 huge files blow the window);
# the file cap is a secondary guard. A single file larger than the byte cap
# becomes its own batch (and the analyzer reads what fits).
MAX_BATCH_BYTES = 50_000
MAX_BATCH_FILES = 20

# Bounded retries per file → the loop is guaranteed to terminate. A file the
# analyzer keeps omitting is recorded as unanalysed (visible), never silently
# dropped.
MAX_RETRIES_PER_FILE = 2


# ---------- Deterministic enumeration (the WHAT-to-cover spine) ----------

@dataclass
class FileUnit:
    """One unit of coverage. `content_hash` is what makes freshness work: a
    re-run re-analyses only the files whose hash changed."""
    path: str            # repo-relative, forward-slash
    size_bytes: int
    content_hash: str    # sha1 of the file bytes


def _git_listed_files(repo: Path) -> list[str] | None:
    """Repo-relative source paths via git, or None if git can't authoritatively
    enumerate `repo` (so the caller falls back to a filesystem walk).

    Returns None unless `repo` is the TOPLEVEL of its own git repo: from a
    subdirectory, `git ls-files` reports the PARENT repo's files, which is wrong
    when the analysis target is a nested directory (or a pytest tmp dir living
    inside another repo). Combines tracked files with untracked-but-not-ignored
    ones (`--others --exclude-standard`) so new, uncommitted source is covered
    too — it's part of the project even before it's committed. git's
    .gitignore handling drops vendored/build trees for free; SCAN_EXCLUDE_DIRS
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
    """The ground-truth worklist: every source file, hashed. Deterministic,
    no LLM. This — not the model — defines the scope of the analysis."""
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


def _current_commit(repo: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


# ---------- The ledger (persistent coverage state) ----------

@dataclass
class LedgerEntry:
    path: str
    content_hash: str
    analyzed_at_commit: str | None = None
    finding: dict | None = None  # the analyzer's structured finding for this file


class AnalysisLedger:
    """Maps file path → coverage state. A file is *covered* iff it has an entry
    whose hash matches the current file AND a recorded finding. Anything else —
    new file, changed file, never-analysed — is *pending*."""

    def __init__(self, entries: dict[str, LedgerEntry] | None = None):
        self.entries: dict[str, LedgerEntry] = entries or {}

    @classmethod
    def load(cls, path: Path) -> "AnalysisLedger":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()  # a corrupt ledger must not block the run; rebuild it
        entries = {}
        for p, e in (raw.get("entries") or {}).items():
            try:
                entries[p] = LedgerEntry(
                    path=e["path"],
                    content_hash=e["content_hash"],
                    analyzed_at_commit=e.get("analyzed_at_commit"),
                    finding=e.get("finding"),
                )
            except (KeyError, TypeError):
                continue
        return cls(entries)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": {p: asdict(e) for p, e in self.entries.items()}}
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def reconcile(self, units: list[FileUnit]) -> None:
        """Drop entries for files no longer present. (New/changed files become
        pending automatically via `is_covered` — no bookkeeping needed.)"""
        current = {u.path for u in units}
        for path in list(self.entries):
            if path not in current:
                del self.entries[path]

    def is_covered(self, unit: FileUnit) -> bool:
        e = self.entries.get(unit.path)
        return (e is not None
                and e.content_hash == unit.content_hash
                and e.finding is not None)

    def pending_units(self, units: list[FileUnit]) -> list[FileUnit]:
        return [u for u in units if not self.is_covered(u)]

    def mark_analyzed(self, unit: FileUnit, finding: dict,
                      commit: str | None = None) -> None:
        self.entries[unit.path] = LedgerEntry(
            path=unit.path, content_hash=unit.content_hash,
            analyzed_at_commit=commit, finding=finding,
        )

    def coverage(self, units: list[FileUnit]) -> tuple[int, int]:
        covered = sum(1 for u in units if self.is_covered(u))
        return covered, len(units)


# ---------- Batching ----------

def batch_units(units: list[FileUnit],
                max_bytes: int = MAX_BATCH_BYTES,
                max_files: int = MAX_BATCH_FILES) -> list[list[FileUnit]]:
    """Group files so each batch fits the analyzer's context. A single file
    larger than `max_bytes` becomes its own batch (cur is empty at the check)."""
    batches: list[list[FileUnit]] = []
    cur: list[FileUnit] = []
    cur_bytes = 0
    for u in units:
        if cur and (cur_bytes + u.size_bytes > max_bytes or len(cur) >= max_files):
            batches.append(cur)
            cur, cur_bytes = [], 0
        cur.append(u)
        cur_bytes += u.size_bytes
    if cur:
        batches.append(cur)
    return batches


# ---------- The analyzer agent (the WHAT-matters layer) ----------

def _analyzer_system_prompt() -> str:
    return (
        "You are the **Cartographer** of the Council of Sages. You map ONE "
        "batch of source files so the sages debate over a COMPLETE picture of "
        "the project instead of a keyhole view.\n\n"
        "## Your job\n"
        "- READ EVERY file in the manifest FULLY (use the Read tool on each "
        "path). Do not guess a file's purpose from its name — open it.\n"
        "- For each file, record: `purpose` (what it does, concrete, from "
        "reading it), `role`, `key_symbols`, and `concerns` (real tech debt, "
        "bugs, smells, risks you actually see — empty if clean).\n\n"
        "## The one rule that matters\n"
        "**You MUST return one entry for EVERY file in the manifest.** Do not "
        "skip files as 'unimportant' or 'boilerplate' — completeness is the "
        "entire point of this pass. A config or a tiny util still gets an "
        "entry. If a file is trivial, say so in one line, but ACCOUNT FOR IT. "
        "Any file you omit is re-queued and analysed again, wasting a whole "
        "round — so just cover them all the first time.\n\n"
        "## Discipline\n"
        "- `path` must match the manifest EXACTLY (repo-relative, as given).\n"
        "- Be terse. One or two sentences per field. This is a map, not an "
        "essay — the debate is where opinions are argued.\n"
        "- Report concerns you can see in the file, not speculation about "
        "files you weren't given.\n\n"
        "Output ONLY the JSON object matching the schema. No prose outside."
    )


def _analyzer_user_message(repo: Path, manifest: list[str]) -> str:
    return (
        f"<repo>{repo.resolve()}</repo>\n\n"
        f"<manifest>\n{json.dumps(manifest, indent=2)}\n</manifest>\n\n"
        f"Read every file in the manifest above (all {len(manifest)}) and "
        f"return one entry per file. Omitting any file re-queues it.\n\n"
        f"## Required output shape\n"
        f"```json\n{json.dumps(ANALYSIS_SCHEMA, indent=2)}\n```\n\n"
        f"Output ONLY the JSON object. No prose outside, no markdown fences."
    )


async def analyze_batch(driver: SageDriver, repo: Path,
                        batch: list[FileUnit], model: str = "sonnet",
                        ) -> dict[str, dict]:
    """Analyse one batch. Returns {path: finding} for the files the agent
    actually accounted for (the receipt). Never raises — a failed batch returns
    an empty receipt so the loop re-queues every file in it."""
    manifest = [u.path for u in batch]
    try:
        out = await driver.spawn(
            user_msg=_analyzer_user_message(repo, manifest),
            system_prompt=_analyzer_system_prompt(),
            schema=ANALYSIS_SCHEMA,
            repo=repo,
            model=model,
            allowed_tools="Read,Glob,Grep",
            timeout_s=420.0,
        )
    except Exception as e:
        print(
            f"[analysis-fail] batch of {len(manifest)} "
            f"({manifest[0] if manifest else '?'}...): "
            f"{type(e).__name__}: {str(e)[:300]}",
            file=sys.stderr,
        )
        return {}
    if not isinstance(out, dict):
        return {}
    receipt: dict[str, dict] = {}
    for f in (out.get("files") or []):
        if isinstance(f, dict) and f.get("path"):
            receipt[str(f["path"])] = f
    return receipt


# ---------- The orchestration loop (the completeness guarantee) ----------

async def run_analysis_pass(
    driver: SageDriver,
    repo: Path,
    model: str = "sonnet",
    max_concurrency: int = 3,
    ledger_path: Path | None = None,
    on_progress=None,
    max_batches: int | None = None,
) -> AnalysisLedger:
    """Analyse EVERY source file in `repo`, resuming from the persistent ledger.

    The loop batches all pending files, analyses the batches concurrently,
    checks each batch's receipt, marks covered files in the ledger, and repeats
    until nothing is pending. Files the analyzer keeps omitting are retried up
    to `MAX_RETRIES_PER_FILE`, then recorded as explicitly unanalysed (never
    silently dropped). The ledger is saved after every round so a crash loses
    at most one round.

    `max_batches`: if set, stop after dispatching this many batches total. The
    rest stay pending in the ledger, so a later call resumes exactly where this
    one left off — lets a big repo be covered in budget-bounded chunks (and
    makes a cheap partial proof run possible).
    `on_progress`: optional async callable `(covered, total) -> None` for UI.
    """
    ledger_path = ledger_path or (repo / ".consejo" / "analysis-ledger.json")
    units = enumerate_units(repo)
    ledger = AnalysisLedger.load(ledger_path)
    ledger.reconcile(units)
    commit = _current_commit(repo)

    retries: dict[str, int] = {}
    sem = asyncio.Semaphore(max_concurrency)
    pending = ledger.pending_units(units)
    batches_done = 0

    async def _do(batch: list[FileUnit]) -> tuple[list[FileUnit], dict[str, dict]]:
        async with sem:
            return batch, await analyze_batch(driver, repo, batch, model)

    while pending:
        batches = batch_units(pending)
        if max_batches is not None:
            room = max(0, max_batches - batches_done)
            if room == 0:
                print(f"[analysis] tope de {max_batches} lotes alcanzado; "
                      f"{len(pending)} archivos quedan pendientes (resumible).",
                      file=sys.stderr)
                break
            dispatch, deferred = batches[:room], batches[room:]
        else:
            dispatch, deferred = batches, []
        batches_done += len(dispatch)
        results = await asyncio.gather(*[_do(b) for b in dispatch])

        # Un-dispatched batches (held back by max_batches) stay pending.
        next_pending: list[FileUnit] = [u for b in deferred for u in b]
        for batch, receipt in results:
            for u in batch:
                finding = receipt.get(u.path)
                if finding is not None:
                    ledger.mark_analyzed(u, finding, commit)
                    continue
                # Not accounted for — re-queue up to the retry cap, then record
                # as unanalysed so the gap is VISIBLE, never silently hidden.
                retries[u.path] = retries.get(u.path, 0) + 1
                if retries[u.path] <= MAX_RETRIES_PER_FILE:
                    next_pending.append(u)
                else:
                    ledger.mark_analyzed(u, {
                        "path": u.path,
                        "purpose": "(NO ANALIZADO: el analizador lo omitió tras "
                                   f"{retries[u.path]} intentos)",
                        "role": "unanalyzed",
                        "key_symbols": [],
                        "concerns": [],
                    }, commit)
                    print(f"[analysis] DROPPED (unanalyzed) after "
                          f"{retries[u.path]} tries: {u.path}", file=sys.stderr)

        ledger.save(ledger_path)
        covered, total = ledger.coverage(units)
        print(f"[analysis] {covered}/{total} files covered "
              f"({100 * covered // total if total else 100}%)", file=sys.stderr)
        if on_progress:
            await on_progress(covered, total)
        pending = next_pending

    ledger.save(ledger_path)
    return ledger


# ---------- Rendering (compact map for the debate briefing) ----------

def coverage_summary(ledger: AnalysisLedger, units: list[FileUnit]) -> dict:
    """Counts for observability: covered/total, files per role, total concerns,
    and any files recorded as unanalysed (the visible gaps)."""
    covered, total = ledger.coverage(units)
    by_role: dict[str, int] = {}
    concerns = 0
    unanalyzed: list[str] = []
    for u in units:
        e = ledger.entries.get(u.path)
        if not e or not e.finding:
            continue
        f = e.finding
        role = str(f.get("role") or "other")
        by_role[role] = by_role.get(role, 0) + 1
        concerns += len(f.get("concerns") or [])
        if role == "unanalyzed":
            unanalyzed.append(u.path)
    return {
        "covered": covered, "total": total,
        "by_role": by_role, "concerns": concerns,
        "unanalyzed": unanalyzed,
    }


def render_repo_map(ledger: AnalysisLedger, units: list[FileUnit],
                    max_concerns: int = 60) -> str:
    """A compact, complete map of the repo for injection into the debate
    briefing: every covered file with its one-line purpose, grouped by role,
    plus a surfaced list of concerns. Stores conclusions, not source — so the
    whole repo's shape fits in a fraction of the context the source would need."""
    summ = coverage_summary(ledger, units)
    lines: list[str] = [
        "# Repo map (análisis completo)",
        f"_{summ['covered']}/{summ['total']} archivos analizados · "
        f"{summ['concerns']} concerns detectados._",
        "",
    ]
    # Group covered files by role.
    grouped: dict[str, list[tuple[str, str]]] = {}
    all_concerns: list[tuple[str, str]] = []
    for u in units:
        e = ledger.entries.get(u.path)
        if not e or not e.finding:
            continue
        f = e.finding
        role = str(f.get("role") or "other")
        grouped.setdefault(role, []).append((u.path, str(f.get("purpose") or "")))
        for c in (f.get("concerns") or []):
            all_concerns.append((u.path, str(c)))

    for role in sorted(grouped):
        lines.append(f"## {role}")
        for path, purpose in sorted(grouped[role]):
            lines.append(f"- `{path}` — {purpose}")
        lines.append("")

    if all_concerns:
        lines.append("## Concerns detectados (muestra)")
        for path, c in all_concerns[:max_concerns]:
            lines.append(f"- `{path}`: {c}")
        if len(all_concerns) > max_concerns:
            lines.append(f"- … y {len(all_concerns) - max_concerns} más.")
        lines.append("")

    if summ["unanalyzed"]:
        lines.append("## ⚠️ Sin analizar (huecos visibles)")
        for path in summ["unanalyzed"]:
            lines.append(f"- `{path}`")
    return "\n".join(lines)


def render_repo_brief(ledger: AnalysisLedger, units: list[FileUnit],
                      max_concerns: int = 40) -> str:
    """A BOUNDED brief of the analysis for injection into every debate turn —
    the full per-file map (`render_repo_map`) would be huge for a big repo and
    is multiplied across ~48 turns. The brief keeps only the actionable signal:
    coverage, the repo's shape (role + top-dir census), and the concerns the
    analysis surfaced, capped. Sages ground proposals in this and Read specifics
    to verify. Size is bounded regardless of repo size."""
    from collections import Counter

    summ = coverage_summary(ledger, units)
    dircount: Counter[str] = Counter()
    for u in units:
        top = u.path.split("/", 1)[0] if "/" in u.path else "(root)"
        dircount[top] += 1

    lines: list[str] = [
        f"Cobertura del análisis: {summ['covered']}/{summ['total']} archivos "
        f"({100 * summ['covered'] // summ['total'] if summ['total'] else 100}%).",
        "Composición por rol: " + (", ".join(
            f"{r}={n}" for r, n in sorted(summ["by_role"].items())) or "—"),
        "Por directorio raíz: " + ", ".join(
            f"{d}={n}" for d, n in dircount.most_common(15)),
        "",
    ]

    concerns: list[tuple[str, str]] = []
    for u in units:
        e = ledger.entries.get(u.path)
        if e and e.finding:
            for c in (e.finding.get("concerns") or []):
                concerns.append((u.path, str(c)))
    if concerns:
        shown = min(len(concerns), max_concerns)
        lines.append(f"Concerns detectados en el análisis "
                     f"({len(concerns)} en total, primeros {shown}):")
        for path, c in concerns[:max_concerns]:
            lines.append(f"- {path}: {c}")
        if len(concerns) > max_concerns:
            lines.append(f"- … y {len(concerns) - max_concerns} más "
                         f"(mapa completo en .consejo/repo-map.md).")
    if summ["unanalyzed"]:
        lines.append("")
        lines.append(f"⚠️ {len(summ['unanalyzed'])} archivos quedaron SIN "
                     f"analizar — el mapa no es completo aún.")
    return "\n".join(lines)
