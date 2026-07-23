"""Deterministic repo skeleton — a ZERO-LLM structural summary of every source
file, so the council analyses a COMPRESSED map instead of paying an LLM to read
the whole repo.

Motivation
----------
The analysis pass (`analysis.py`) is correct but expensive: it spawns an LLM
subagent per batch and makes it READ every file FULLY. On a large repo that's
30+ agent calls and 20-30 min before the debate even starts — the cost sink the
user hit on AutomatizaPyme.

This module does the *mechanical* half deterministically. It never calls an LLM.
For each source file it extracts a structural skeleton — docstring/lead comment,
top-level symbols with signatures, and external imports — and renders a compact
2-3 line summary. The output is ~10-20x smaller than the source, so:

  - the debate can be briefed on the WHOLE repo's shape for near-zero cost, and
  - if an LLM analysis pass still runs, it reads the *skeleton* (cheap), then
    Reads only the few files that look worth a closer look — instead of being
    forced to read 100% of the source.

What it does NOT do
-------------------
Judgement. A deterministic parse can say "this file exports `parsePlan` and
imports `zod`"; it cannot say "this regex is a ReDoS risk". That's the LLM's job
— but now the LLM adds judgement on top of a free, complete map instead of
paying to rebuild the map itself.

Languages: Python via the stdlib `ast` (accurate); TS/JS/JSX/TSX via regex
(approximate but cheap and dependency-free); Markdown / JSON / YAML / TOML via
light structural extraction. Unknown extensions get a size-only stub. Stdlib
only — no tree-sitter, no third-party parsers.
"""

from __future__ import annotations

import ast
import json
import math
import posixpath
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# The deterministic enumerator: git ls-files + exclude dirs, so node_modules/
# dist/build never enter the skeleton and scope matches the rest of the council.
from .repo_enum import FileUnit, enumerate_units


@dataclass
class FileSkeleton:
    """The deterministic structural summary of one file."""
    path: str
    lang: str
    loc: int
    size_bytes: int
    lead: str = ""                 # module docstring / first doc comment (1 line)
    symbols: list[str] = field(default_factory=list)  # defs/classes/exports + sigs
    imports: list[str] = field(default_factory=list)   # external modules referenced
    raw_imports: list[str] = field(default_factory=list)  # every import spec AS WRITTEN
    note: str = ""                 # parse note (e.g. "syntax error → regex fallback")

    def to_lines(self, max_symbols: int = 12,
                 internal_deps: list[str] | None = None) -> str:
        """The compact 2-3 line rendering injected into the map. `internal_deps`
        (repo-relative paths this file imports) makes the WIRING visible."""
        head = f"`{self.path}` ({self.lang}, {self.loc} loc)"
        if self.lead:
            head += f" — {self.lead}"
        out = [head]
        if self.symbols:
            shown = self.symbols[:max_symbols]
            more = "" if len(self.symbols) <= max_symbols else \
                f" … (+{len(self.symbols) - max_symbols})"
            out.append("  symbols: " + "; ".join(shown) + more)
        if self.imports:
            out.append("  imports: " + ", ".join(sorted(set(self.imports))[:15]))
        if internal_deps:
            shown = internal_deps[:10]
            more = "" if len(internal_deps) <= 10 else \
                f" (+{len(internal_deps) - 10})"
            out.append("  → usa: " + ", ".join(shown) + more)
        return "\n".join(out)


# ---------- per-language extractors ----------

_EXT_LANG = {
    ".py": "python", ".ts": "ts", ".tsx": "tsx", ".js": "js", ".jsx": "jsx",
    ".md": "markdown", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml",
}


def _first_sentence(text: str, limit: int = 140) -> str:
    text = " ".join((text or "").split())
    if not text:
        return ""
    # Cut at first sentence end or the limit, whichever comes first.
    m = re.search(r"(?<=[.!?])\s", text)
    end = m.start() if m and m.start() < limit else limit
    return text[:end].rstrip(" .") + ("…" if len(text) > end else "")


def _python_skeleton(src: str, sk: FileSkeleton) -> None:
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        sk.note = f"syntax error (l{e.lineno}); regex fallback"
        _regex_pyish(src, sk)
        return
    doc = ast.get_docstring(tree)
    if doc:
        sk.lead = _first_sentence(doc)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            args = [arg.arg for arg in node.args.args]
            sk.symbols.append(f"{a}def {node.name}({', '.join(args)})")
        elif isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            tail = f" {{{', '.join(methods[:8])}}}" if methods else ""
            sk.symbols.append(f"class {node.name}{tail}")
        elif isinstance(node, ast.Import):
            for n in node.names:
                sk.raw_imports.append(n.name)           # full dotted, as written
                sk.imports.append(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # Encode relative level as leading dots so the graph resolver can tell
            # `from .foo` (internal) from `from foo` (maybe external).
            spec = "." * node.level + (node.module or "")
            if spec:
                sk.raw_imports.append(spec)
            if node.module and node.level == 0:  # external display (absolute only)
                sk.imports.append(node.module.split(".")[0])


def _regex_pyish(src: str, sk: FileSkeleton) -> None:
    for m in re.finditer(r"^(?:async\s+)?def\s+(\w+)\s*\(", src, re.M):
        sk.symbols.append(f"def {m.group(1)}(…)")
    for m in re.finditer(r"^class\s+(\w+)", src, re.M):
        sk.symbols.append(f"class {m.group(1)}")


_JS_IMPORT = re.compile(r"""(?:import[^'"]*from\s*|require\s*\(\s*)['"]([^'"]+)['"]""")
_JS_EXPORT = re.compile(
    r"^export\s+(?:default\s+)?"
    r"(?:(async\s+)?function\s+(\w+)|class\s+(\w+)|"
    r"(?:const|let|var)\s+(\w+))",
    re.M,
)
_JS_DECL = re.compile(
    r"^\s*(?:export\s+)?(?:(async\s+)?function\s+(\w+)|class\s+(\w+))", re.M)


def _js_skeleton(src: str, sk: FileSkeleton) -> None:
    # Lead: first /** ... */ jsdoc or first // line comment.
    m = re.search(r"/\*\*(.*?)\*/", src, re.S)
    if m:
        sk.lead = _first_sentence(re.sub(r"^\s*\*", "", m.group(1), flags=re.M))
    else:
        m = re.match(r"\s*//\s*(.+)", src)
        if m:
            sk.lead = _first_sentence(m.group(1))
    for dep in _JS_IMPORT.findall(src):
        sk.raw_imports.append(dep)                # full specifier, as written
        if not dep.startswith("."):           # external package (display)
            # strip subpath: 'react-dom/client' → 'react-dom', '@scope/pkg/x' → '@scope/pkg'
            parts = dep.split("/")
            sk.imports.append("/".join(parts[:2]) if dep.startswith("@")
                              else parts[0])
    seen: set[str] = set()
    for mm in _JS_EXPORT.finditer(src):
        a, fn, cl, var = mm.groups()
        name = fn or cl or var
        if not name or name in seen:
            continue
        seen.add(name)
        kind = "class" if cl else ("function" if fn else "const")
        pre = "async " if a else ""
        sk.symbols.append(f"export {pre}{kind} {name}")
    # Non-exported top-level functions/classes (so the map isn't only the API).
    for mm in _JS_DECL.finditer(src):
        a, fn, cl = mm.groups()
        name = fn or cl
        if name and name not in seen:
            seen.add(name)
            sk.symbols.append(f"{'class' if cl else 'function'} {name}")


def _md_skeleton(src: str, sk: FileSkeleton) -> None:
    headings = re.findall(r"^(#{1,3})\s+(.+)$", src, re.M)
    if headings:
        sk.lead = _first_sentence(headings[0][1])
        sk.symbols = [f"{'#' * len(h)} {t.strip()}" for h, t in headings[:12]]
    else:
        first = next((ln for ln in src.splitlines() if ln.strip()), "")
        sk.lead = _first_sentence(first)


def _json_skeleton(src: str, sk: FileSkeleton) -> None:
    try:
        obj = json.loads(src)
    except (json.JSONDecodeError, ValueError):
        sk.note = "invalid json"
        return
    if isinstance(obj, dict):
        keys = list(obj.keys())
        sk.symbols = [f"key: {k}" for k in keys[:20]]
        # package.json gets special, high-signal treatment.
        if "name" in obj or "scripts" in obj or "dependencies" in obj:
            deps = len(obj.get("dependencies", {})) + \
                len(obj.get("devDependencies", {}))
            scripts = ", ".join(list(obj.get("scripts", {}))[:8])
            sk.lead = f"package '{obj.get('name', '?')}', {deps} deps" + \
                      (f"; scripts: {scripts}" if scripts else "")
    elif isinstance(obj, list):
        sk.lead = f"array of {len(obj)} items"


def _yaml_toml_skeleton(src: str, sk: FileSkeleton) -> None:
    # Top-level keys / sections without a parser (keeps it dependency-free and
    # never aborts on an exotic dialect).
    if sk.lang == "toml":
        sk.symbols = [f"[{m.group(1)}]" for m in
                      re.finditer(r"^\[([^\]]+)\]", src, re.M)][:20]
    else:  # yaml: lines starting at column 0 with `key:`
        sk.symbols = [f"{m.group(1)}:" for m in
                      re.finditer(r"^([A-Za-z_][\w-]*):", src, re.M)][:20]


_EXTRACTORS = {
    "python": _python_skeleton,
    "ts": _js_skeleton, "tsx": _js_skeleton, "js": _js_skeleton, "jsx": _js_skeleton,
    "markdown": _md_skeleton,
    "json": _json_skeleton,
    "yaml": _yaml_toml_skeleton, "toml": _yaml_toml_skeleton,
}


def skeleton_for(repo: Path, unit: FileUnit) -> FileSkeleton:
    """Extract the deterministic skeleton of one file. Never raises."""
    lang = _EXT_LANG.get(Path(unit.path).suffix, "other")
    sk = FileSkeleton(path=unit.path, lang=lang,
                      loc=0, size_bytes=unit.size_bytes)
    try:
        src = (repo / unit.path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        sk.note = "unreadable"
        return sk
    sk.loc = src.count("\n") + 1
    extractor = _EXTRACTORS.get(lang)
    if extractor:
        try:
            extractor(src, sk)
        except Exception as e:  # extractor must never sink the whole pass
            sk.note = f"extract error: {type(e).__name__}"
    return sk


def build_skeletons(repo: Path) -> list[FileSkeleton]:
    """The whole-repo skeleton: one entry per source file. Deterministic, free."""
    return [skeleton_for(repo, u) for u in enumerate_units(repo)]


# ---------- dependency graph (the WIRING: who imports whom) ----------
#
# The per-file skeleton answers "what is each file"; this answers "how do they
# connect". It resolves each INTERNAL import (relative `./x`, `from .x`, or an
# alias `@/x`) to the actual repo file it points at — deterministically, no LLM —
# so the council sees the real architecture: hubs everyone depends on (risky to
# touch), leaf modules (safe to delete), and import cycles (structural debt).

@dataclass
class DepGraph:
    edges: dict[str, list[str]]   # file -> repo-rel files it imports (internal)
    fan_in: dict[str, int]        # file -> how many files import it
    fan_out: dict[str, int]       # file -> how many internal files it imports
    cycles: list[list[str]]       # sample import cycles (entangled SCCs / self-loops)


_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".json")


def _loads_jsonc(text: str) -> dict | None:
    """Parse a tsconfig. Most are plain JSON, so try that FIRST (after stripping a
    UTF-8 BOM) — a regex that mangles comments must never corrupt valid JSON. Only
    if that fails do we apply the lenient pass: block comments, FULL-LINE `//`
    comments (line-anchored so it can't eat a `://` inside a string), and trailing
    commas. Best-effort — returns None if it still won't parse."""
    text = text.lstrip("﻿")
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    t = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    t = re.sub(r"(?m)^\s*//[^\n]*$", "", t)
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def _python_module_index(paths: set[str]) -> dict[str, str]:
    """Map a Python dotted module -> repo file, by walking `__init__.py` package
    chains. `app.agents.billing.tools` -> `backend/app/agents/billing/tools.py`,
    so absolute internal imports resolve even when the package root is a subdir."""
    pkg_dirs = {posixpath.dirname(p) for p in paths
                if posixpath.basename(p) == "__init__.py"}
    index: dict[str, str] = {}
    for p in paths:
        if not p.endswith(".py"):
            continue
        stem = posixpath.basename(p)[:-3]
        cur = posixpath.dirname(p)
        pkgs: list[str] = []
        while cur and cur in pkg_dirs:
            pkgs.append(posixpath.basename(cur))
            parent = posixpath.dirname(cur)
            if parent == cur:
                break
            cur = parent
        pkgs.reverse()
        dotted = ".".join(pkgs if stem == "__init__" else pkgs + [stem])
        if dotted:
            index.setdefault(dotted, p)
    return index


def _resolve_py(spec: str, importer: str, index: dict[str, str],
                paths: set[str]) -> str | None:
    if spec.startswith("."):                      # relative: resolve on the tree
        level = len(spec) - len(spec.lstrip("."))
        module = spec[level:]
        base = posixpath.dirname(importer)
        for _ in range(level - 1):                # one dot = current package
            base = posixpath.dirname(base)
        rel = module.replace(".", "/")
        cand = posixpath.normpath(posixpath.join(base, rel)) if rel else base
        for t in (f"{cand}.py", f"{cand}/__init__.py", f"{base}/__init__.py"):
            if t in paths:
                return t
        return None
    parts = spec.split(".")                       # absolute: longest known prefix
    for k in range(len(parts), 0, -1):
        hit = index.get(".".join(parts[:k]))
        if hit:
            return hit
    return None


def _ts_alias_map(repo: Path, paths: set[str]) -> list[tuple[str, list[str]]]:
    """Parse tsconfig/jsconfig `compilerOptions.paths` into [(prefix, [base dirs])]
    so `@/x` resolves. e.g. '@/*' -> ['./src/*'] under frontend/ becomes
    ('@/', ['frontend/src'])."""
    rules: list[tuple[str, list[str]]] = []
    for cfg in sorted(p for p in paths if posixpath.basename(p)
                      in ("tsconfig.json", "jsconfig.json")):
        try:
            data = _loads_jsonc((repo / cfg).read_text("utf-8", errors="replace"))
        except OSError:
            continue
        co = (data or {}).get("compilerOptions") or {}
        cfg_dir = posixpath.dirname(cfg)
        base = posixpath.normpath(posixpath.join(cfg_dir, co.get("baseUrl") or "."))
        base = "" if base == "." else base
        for pat, targets in (co.get("paths") or {}).items():
            prefix = pat[:-1] if pat.endswith("*") else pat
            dirs = []
            for t in (targets or []):
                t = t[:-1] if t.endswith("*") else t
                d = posixpath.normpath(posixpath.join(base, t))
                dirs.append("" if d == "." else d)
            if dirs:
                rules.append((prefix, dirs))
    return rules


def _resolve_js_file(cand: str, paths: set[str]) -> str | None:
    if cand in paths:
        return cand
    for ext in _JS_EXTS:
        if cand + ext in paths:
            return cand + ext
    for ext in _JS_EXTS:
        if f"{cand}/index{ext}" in paths:
            return f"{cand}/index{ext}"
    return None


def _resolve_js(spec: str, importer: str,
                alias: list[tuple[str, list[str]]], paths: set[str]) -> str | None:
    if spec.startswith("."):
        cand = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
        return _resolve_js_file(cand, paths)
    for prefix, dirs in alias:
        if spec.startswith(prefix):
            sub = spec[len(prefix):]
            for d in dirs:
                cand = posixpath.normpath(posixpath.join(d, sub)) if sub else d
                hit = _resolve_js_file(cand, paths)
                if hit:
                    return hit
    return None


def _find_cycles(edges: dict[str, list[str]], max_report: int = 15) -> list[list[str]]:
    """Import cycles = strongly-connected components of size > 1 (mutually
    entangled modules), plus self-loops. Iterative Tarjan so a deep import chain
    can't blow the recursion limit on a big repo."""
    idx: dict[str, int] = {}
    low: dict[str, int] = {}
    on: dict[str, bool] = {}
    stack: list[str] = []
    counter = [0]
    out: list[list[str]] = []
    for root in edges:
        if root in idx:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                idx[v] = low[v] = counter[0]
                counter[0] += 1
                stack.append(v)
                on[v] = True
            recursed = False
            neigh = edges.get(v, [])
            i = pi
            while i < len(neigh):
                w = neigh[i]
                if w not in idx:
                    work[-1] = (v, i + 1)
                    work.append((w, 0))
                    recursed = True
                    break
                if on.get(w):
                    low[v] = min(low[v], idx[w])
                i += 1
            if recursed:
                continue
            if low[v] == idx[v]:
                comp: list[str] = []
                while True:
                    w = stack.pop()
                    on[w] = False
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    out.append(comp)
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
    for v, ns in edges.items():            # self-loops aren't SCCs of size > 1
        if v in ns:
            out.append([v])
    out.sort(key=len, reverse=True)
    return out[:max_report]


def build_dependency_graph(repo: Path, skeletons: list[FileSkeleton]) -> DepGraph:
    """Resolve every internal import to its target file → the wiring graph."""
    paths = {s.path for s in skeletons}
    index = _python_module_index(paths)
    alias = _ts_alias_map(repo, paths)
    edges: dict[str, list[str]] = {}
    for s in skeletons:
        tgts: list[str] = []
        seen: set[str] = set()
        for spec in s.raw_imports:
            if s.lang == "python":
                t = _resolve_py(spec, s.path, index, paths)
            elif s.lang in ("ts", "tsx", "js", "jsx"):
                t = _resolve_js(spec, s.path, alias, paths)
            else:
                t = None
            if t and t != s.path and t not in seen:
                seen.add(t)
                tgts.append(t)
        edges[s.path] = tgts
    fan_out = {p: len(t) for p, t in edges.items()}
    fan_in: dict[str, int] = {p: 0 for p in paths}
    for t in edges.values():
        for d in t:
            fan_in[d] = fan_in.get(d, 0) + 1
    return DepGraph(edges=edges, fan_in=fan_in, fan_out=fan_out,
                    cycles=_find_cycles(edges))


# ---------- debate-priority score (where should the council look first) ----------
#
# A deterministic ATTENTION signal derived from skeleton + graph — NOT a quality
# verdict (that's the council's job). It answers "of 1300 files, which 20 deserve
# the debate's eyes first?". The drivers, in weight order:
#   - blast radius (fan-in): a defect in a file many others import is expensive;
#   - coupling (fan-out): a file that pulls in many others is hard to change;
#   - size (loc): more code, more to get wrong;
#   - cycle membership: a flat penalty — entangled modules are structural debt.
# log1p tames hub outliers (fan-in 116) so one mega-hub doesn't flatten the rest.

@dataclass
class FileScore:
    path: str
    score: float            # 0-100 debate-attention score
    ca: int                 # afferent coupling (fan-in): who depends on this
    ce: int                 # efferent coupling (fan-out): what this depends on
    loc: int
    instability: float | None  # ce/(ca+ce): 0=stable core, 1=volatile leaf
    in_cycle: bool
    churn: int = 0          # commits touching this file in the churn window


def git_churn(repo: Path, since_days: int = 365) -> dict[str, int]:
    """Change-frequency per file: how many commits touched it recently. This is
    the signal structure alone can't give — a complex hub that never changes is
    lower priority than one churning every week (CodeScene's hotspot insight).
    Deterministic, from `git log`. Returns {} if not a git repo (churn then simply
    doesn't modulate the score). Falls back to all-history if the window is empty
    (shallow clone / young repo). Paths are repo-relative posix, matching skeletons."""
    def _count(extra: list[str]) -> dict[str, int] | None:
        try:
            r = subprocess.run(
                ["git", "-C", str(repo), "log", "--format=", "--name-only",
                 "--no-renames", *extra],
                capture_output=True, text=True, timeout=60,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return None
        if r.returncode != 0:
            return None
        counts: dict[str, int] = {}
        for line in r.stdout.splitlines():
            line = line.strip()
            if line:
                counts[line] = counts.get(line, 0) + 1
        return counts

    counts = _count([f"--since={since_days} days ago"])
    if counts is None:
        return {}
    if not counts:                       # young/shallow history → use all of it
        counts = _count([]) or {}
    return counts


def score_files(skeletons: list[FileSkeleton], graph: DepGraph,
                churn: dict[str, int] | None = None) -> list[FileScore]:
    """Rank every file by how much it deserves the council's attention. Pure
    function of structure (+ git churn when given) — deterministic, no LLM, $0.

    Structure answers "how central/complex" (blast-radius + coupling + size);
    churn answers "how volatile". Hot AND central = the real hotspot. Without
    `churn` the score is purely structural (unchanged), so a stable hub keeps its
    rank; with churn, a frequently-changed file is boosted."""
    cyc = {n for c in graph.cycles for n in c}
    log = {s.path: (math.log1p(graph.fan_in.get(s.path, 0)),
                    math.log1p(graph.fan_out.get(s.path, 0)),
                    math.log1p(s.loc)) for s in skeletons}
    max_ca = max((v[0] for v in log.values()), default=0) or 1.0
    max_ce = max((v[1] for v in log.values()), default=0) or 1.0
    max_loc = max((v[2] for v in log.values()), default=0) or 1.0
    max_churn = (math.log1p(max(churn.values())) if churn else 0.0) or 1.0
    scores: list[FileScore] = []
    for s in skeletons:
        lca, lce, lloc = log[s.path]
        ca = graph.fan_in.get(s.path, 0)
        ce = graph.fan_out.get(s.path, 0)
        ch = churn.get(s.path, 0) if churn else 0
        struct = 0.45 * (lca / max_ca) + 0.25 * (lce / max_ce) + 0.20 * (lloc / max_loc)
        cycle_bonus = 10.0 if s.path in cyc else 0.0
        if churn:
            # Structure dominant (×0.8), churn an additive boost (×0.18); a stable
            # hub stays high, a hot file climbs. Both visible, neither erased.
            nc = math.log1p(ch) / max_churn
            score = 100.0 * (0.8 * struct + 0.18 * nc) + cycle_bonus
        else:
            score = 100.0 * struct + cycle_bonus
        inst = (ce / (ca + ce)) if (ca + ce) else None
        scores.append(FileScore(
            path=s.path, score=round(min(100.0, score), 1), ca=ca, ce=ce,
            loc=s.loc, instability=round(inst, 2) if inst is not None else None,
            in_cycle=s.path in cyc, churn=ch))
    scores.sort(key=lambda f: f.score, reverse=True)
    return scores


# ---------- coverage zones (the breadth gate: don't let the plan be a keyhole) ----------
#
# The debate's failure mode on a big repo is *drilling the first coherent vein*:
# it converges in 2-3 rounds on one theme (auth, or billing, or the orchestrator)
# and silently ignores the other 95% of the system. The deterministic map already
# guarantees COVERAGE for analysis; this brings the same discipline to the PLAN.
# Zones partition the repo by concern (dir prefix); a per-turn scorecard shows
# which major zones the current plan touches, so a sage can see — and the prompt's
# breadth-floor rule forces them to address — a zone the council is ducking.

@dataclass
class Zone:
    name: str            # repo-relative dir prefix, e.g. "backend/app/agents"
    file_count: int
    score: float         # sum of file debate-scores in the zone (importance)


def _zone_of(path: str) -> str:
    """The concern-zone a file belongs to: its directory, capped at 3 segments."""
    parts = path.replace("\\", "/").strip("/").split("/")
    dirs = parts[:-1]
    return "/".join(dirs[:3]) if dirs else "(root)"


def repo_zones(skeletons: list[FileSkeleton], graph: DepGraph,
               churn: dict[str, int] | None = None, top_n: int = 12) -> list[Zone]:
    """The major zones of the repo, ranked by aggregate importance (debate-score).
    Deterministic. Used to gate the plan's breadth."""
    scores = {f.path: f.score for f in score_files(skeletons, graph, churn)}
    agg: dict[str, list] = {}
    for s in skeletons:
        a = agg.setdefault(_zone_of(s.path), [0, 0.0])
        a[0] += 1
        a[1] += scores.get(s.path, 0.0)
    zones = [Zone(name=z, file_count=c, score=round(sc, 1)) for z, (c, sc) in agg.items()]
    zones.sort(key=lambda z: z.score, reverse=True)
    return zones[:top_n]


def render_coverage(plan: list[dict], zones: list[Zone]) -> str:
    """A per-turn scorecard: how many plan items touch each major zone. Injected
    into the debate so a zone with ZERO items is VISIBLE, not silently skipped."""
    if not zones:
        return ""
    covered: dict[str, int] = {}
    for task in (plan or []):
        hit = {_zone_of(str(ft)) for ft in (task.get("files_touched") or [])}
        for z in hit:
            covered[z] = covered.get(z, 0) + 1
    lines = ["Cobertura del plan por zona (zonas mayores del repo, por importancia):"]
    for z in zones:
        k = covered.get(z.name, 0)
        mark = f"✓ {k} ítem(s)" if k else "✗ SIN TOCAR"
        warn = " ⚠️" if not k else ""
        lines.append(f"- `{z.name}` ({z.file_count} arch, score {z.score:.0f}) → {mark}{warn}")
    untouched = [z.name for z in zones if not covered.get(z.name)]
    if untouched:
        lines.append("")
        lines.append(
            "Zonas mayores SIN ningún ítem: " + ", ".join(f"`{z}`" for z in untouched)
            + ". Antes de firmar: propón 1 ítem REAL de alto valor en alguna, o "
            "el plan debe nombrar por qué queda fuera esta iteración. Un plan que "
            "ignora media base es un ojo de cerradura, no un plan.")
    return "\n".join(lines)


# ---------- rendering ----------

def _render_connectivity(graph: "DepGraph", top_n: int = 15,
                         max_cycles: int = 10) -> list[str]:
    """The connectivity section: hubs (high fan-in), the most-coupled files (high
    fan-out), and import cycles. This is the architecture made explicit."""
    hubs = sorted((p for p, n in graph.fan_in.items() if n > 0),
                  key=lambda p: graph.fan_in[p], reverse=True)[:top_n]
    coupled = sorted((p for p, n in graph.fan_out.items() if n > 0),
                     key=lambda p: graph.fan_out[p], reverse=True)[:top_n]
    out = ["## 🔗 Conectividad (grafo de imports internos)", ""]
    out.append("**Hubs** (más importados — tocarlos arrastra a muchos):")
    out += [f"- `{p}` ← {graph.fan_in[p]} archivos" for p in hubs] or ["- —"]
    out.append("")
    out.append("**Más acoplados** (más dependencias internas salientes):")
    out += [f"- `{p}` → {graph.fan_out[p]} archivos" for p in coupled] or ["- —"]
    out.append("")
    if graph.cycles:
        out.append(f"**⚠️ Ciclos de import** ({len(graph.cycles)} grupos "
                   f"enredados — deuda estructural):")
        for cyc in graph.cycles[:max_cycles]:
            if len(cyc) == 1:
                out.append(f"- `{cyc[0]}` (se importa a sí mismo)")
            else:
                out.append("- " + " ↔ ".join(f"`{c}`" for c in cyc[:6])
                           + (" …" if len(cyc) > 6 else ""))
    else:
        out.append("**Ciclos de import:** ninguno ✅")
    out.append("")
    return out


def _render_priority(scores: list[FileScore], top_n: int = 20) -> list[str]:
    """The debate-priority ranking: where the council should look first."""
    has_churn = any(f.churn for f in scores)
    out = ["## 🎯 Prioridad para el debate (señal determinista, no veredicto)", ""]
    out.append("_Dónde mirar primero: blast-radius (←) + acoplamiento (→) + tamaño"
               + (" + churn (⟳ commits recientes)" if has_churn else "")
               + " + ciclo. Es una guía de ATENCIÓN; el juicio de calidad es del "
               "consejo. `←`=cuántos lo importan, `→`=cuántos importa"
               + (", `⟳`=cuántas veces cambió" if has_churn else "") + "._")
    out.append("")
    for f in scores[:top_n]:
        if f.score <= 0:
            break
        flag = " · ⚠️CICLO" if f.in_cycle else ""
        inst = f" · inest={f.instability}" if f.instability is not None else ""
        churn = f" · ⟳{f.churn}" if f.churn else ""
        out.append(f"- **{f.score:.0f}** `{f.path}` "
                   f"(←{f.ca} →{f.ce}, {f.loc} loc{churn}{inst}{flag})")
    out.append("")
    return out


def render_skeleton_map(skeletons: list[FileSkeleton],
                        graph: "DepGraph | None" = None,
                        churn: dict[str, int] | None = None) -> str:
    """A compact, COMPLETE map of the repo for the debate briefing — grouped by
    top-level directory so the LLM sees the project's shape, not a flat dump. With
    `graph`, each file shows the internal files it uses, plus connectivity (hubs /
    coupling / cycles) and a debate-priority ranking (folding in `churn` if given)."""
    from collections import defaultdict
    groups: dict[str, list[FileSkeleton]] = defaultdict(list)
    for sk in skeletons:
        top = sk.path.split("/", 1)[0] if "/" in sk.path else "(root)"
        groups[top].append(sk)

    total_loc = sum(s.loc for s in skeletons)
    out = [
        "# Repo skeleton (determinista, sin LLM)",
        f"_{len(skeletons)} archivos · {total_loc} loc · "
        f"{len(groups)} directorios raíz._",
        "",
    ]
    if graph is not None:
        out += _render_connectivity(graph)
        out += _render_priority(score_files(skeletons, graph, churn))
    for top in sorted(groups):
        files = groups[top]
        out.append(f"## {top}/  ({len(files)} archivos)")
        for sk in sorted(files, key=lambda s: s.path):
            deps = graph.edges.get(sk.path) if graph is not None else None
            out.append(sk.to_lines(internal_deps=deps))
        out.append("")
    return "\n".join(out)


def render_skeleton_brief(skeletons: list[FileSkeleton],
                          graph: "DepGraph | None" = None,
                          churn: dict[str, int] | None = None,
                          map_rel_path: str = ".consejo/repo-skeleton.md") -> str:
    """A BOUNDED census of the repo for injection into EVERY debate turn.

    The full map (`render_skeleton_map`) is too big to repeat across ~48 turns,
    so it's written to disk and the sages Read it when they need to locate a
    file. This brief is the always-present orientation: size, language mix,
    per-directory shape, and — with `graph` — the top hubs and cycle count, the
    highest-signal architecture facts. Bounded regardless of repo size. No
    'concerns' here: judgement is the debate's job, not the map's."""
    from collections import Counter

    total_loc = sum(s.loc for s in skeletons)
    by_lang: Counter[str] = Counter(s.lang for s in skeletons)
    by_dir: Counter[str] = Counter(
        (s.path.split("/", 1)[0] if "/" in s.path else "(root)")
        for s in skeletons)
    lines = [
        f"Mapa estructural determinista del repo: {len(skeletons)} archivos, "
        f"{total_loc} loc.",
        "Lenguajes: " + ", ".join(f"{lang}={n}" for lang, n in by_lang.most_common()),
        "Por directorio raíz: " + ", ".join(
            f"{d}={n}" for d, n in by_dir.most_common(15)),
    ]
    if graph is not None:
        top = [f for f in score_files(skeletons, graph, churn) if f.score > 0][:6]
        if top:
            lines.append("Prioridad de debate (score · ←importado →importa"
                         + (" ⟳cambios" if churn else "") + "): "
                         + "; ".join(
                             f"{f.path} ({f.score:.0f} ←{f.ca} →{f.ce}"
                             + (f" ⟳{f.churn}" if f.churn else "") + ")"
                             for f in top))
        lines.append(f"Ciclos de import detectados: {len(graph.cycles)}"
                     + (" ✅ ninguno" if not graph.cycles else " ⚠️"))
    lines += [
        "",
        f"El MAPA COMPLETO (propósito + símbolos + WIRING de cada archivo, hubs, "
        f"ciclos y ranking de prioridad) está en `{map_rel_path}`. Léelo con Read "
        f"para ubicar y entender conexiones antes de proponer; empieza por los "
        f"archivos de mayor score; luego Read los concretos que necesites juzgar.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":  # demo + compression measurement
    import sys
    # The console may be cp1252 (Windows); the map is UTF-8 (arrows, accents).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    units = enumerate_units(repo)
    raw_bytes = sum(u.size_bytes for u in units)
    sks = build_skeletons(repo)
    graph = build_dependency_graph(repo, sks)
    churn = git_churn(repo)
    rendered = render_skeleton_map(sks, graph, churn)
    map_bytes = len(rendered.encode("utf-8"))
    by_lang: dict[str, int] = {}
    for s in sks:
        by_lang[s.lang] = by_lang.get(s.lang, 0) + 1
    total_edges = sum(len(t) for t in graph.edges.values())
    wired = sum(1 for t in graph.edges.values() if t)
    print(f"repo:        {repo}", file=sys.stderr)
    print(f"files:       {len(units)}  ({by_lang})", file=sys.stderr)
    print(f"raw source:  {raw_bytes:,} bytes", file=sys.stderr)
    print(f"skeleton:    {map_bytes:,} bytes  (~{map_bytes // 4:,} tokens)",
          file=sys.stderr)
    print(f"compression: {raw_bytes / map_bytes:.1f}x  "
          f"({100 * map_bytes // raw_bytes}% of original)", file=sys.stderr)
    print(f"wiring:      {total_edges:,} aristas internas, {wired} archivos "
          f"conectados, {len(graph.cycles)} ciclos", file=sys.stderr)
    print(f"churn:       {len(churn)} archivos con historial git", file=sys.stderr)
    hot = score_files(sks, graph, churn)[:5]
    print("top hotspots (score): " + "; ".join(
        f"{f.path} ({f.score:.0f} ←{f.ca} →{f.ce} ⟳{f.churn})" for f in hot),
        file=sys.stderr)
    # The map itself goes to stdout so you can pipe / inspect it.
    sys.stdout.write(rendered)
