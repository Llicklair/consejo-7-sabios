"""Tests del extractor de esqueleto determinista (P1 sin LLM).

El esqueleto reemplaza la pasada de análisis con LLM: debe ser exacto en Python
(via AST), razonable en TS/JS (via regex), no lanzar nunca, y producir un brief
acotado. La compresión es la propiedad clave: el mapa debe ser mucho menor que
el código que resume.
"""

from __future__ import annotations

from pathlib import Path

from consejo.repo_enum import FileUnit
from consejo.repo_skeleton import (
    build_dependency_graph,
    build_skeletons,
    git_churn,
    render_skeleton_brief,
    render_skeleton_map,
    score_files,
    skeleton_for,
)


def _mk(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _unit(tmp: Path, rel: str) -> FileUnit:
    data = (tmp / rel).read_bytes()
    import hashlib
    return FileUnit(path=rel, size_bytes=len(data),
                    content_hash=hashlib.sha1(data).hexdigest())


def test_python_ast_extracts_docstring_symbols_imports(tmp_path):
    _mk(tmp_path, "mod.py",
        '"""Module that does X. Second sentence ignored."""\n'
        "import os\n"
        "from collections import Counter\n"
        "from .local import thing\n"  # relative → not an external import
        "def foo(a, b):\n    return a\n"
        "async def bar(x):\n    return x\n"
        "class Widget:\n"
        "    def m1(self):\n        pass\n"
        "    def m2(self):\n        pass\n")
    sk = skeleton_for(tmp_path, _unit(tmp_path, "mod.py"))
    assert sk.lang == "python"
    assert sk.lead.startswith("Module that does X")
    assert "def foo(a, b)" in sk.symbols
    assert "async def bar(x)" in sk.symbols
    assert any(s.startswith("class Widget") and "m1" in s and "m2" in s
               for s in sk.symbols)
    assert "os" in sk.imports
    assert "collections" in sk.imports
    assert "local" not in sk.imports  # relative import excluded


def test_python_syntax_error_falls_back_not_raises(tmp_path):
    _mk(tmp_path, "broken.py", "def ok():\n    pass\ndef oops(:\n")
    sk = skeleton_for(tmp_path, _unit(tmp_path, "broken.py"))
    assert "syntax error" in sk.note
    assert any("ok" in s for s in sk.symbols)  # regex fallback still maps it


def test_ts_extracts_exports_and_external_imports(tmp_path):
    _mk(tmp_path, "page.tsx",
        "import { useState } from 'react';\n"
        "import { Button } from '@/components/ui';\n"
        "import { local } from './helper';\n"  # relative → excluded
        "export function LoginPage() { return null; }\n"
        "function handleSubmit() {}\n"
        "export const API = 1;\n")
    sk = skeleton_for(tmp_path, _unit(tmp_path, "page.tsx"))
    assert sk.lang == "tsx"
    assert "export function LoginPage" in sk.symbols
    assert "function handleSubmit" in sk.symbols
    assert "export const API" in sk.symbols
    assert "react" in sk.imports
    assert "@/components" in sk.imports  # scoped pkg keeps two segments
    assert not any(i.startswith(".") for i in sk.imports)  # no relative


def test_package_json_high_signal(tmp_path):
    _mk(tmp_path, "package.json",
        '{"name": "myapp", "scripts": {"build": "x", "test": "y"}, '
        '"dependencies": {"react": "1", "next": "2"}}')
    sk = skeleton_for(tmp_path, _unit(tmp_path, "package.json"))
    assert "myapp" in sk.lead
    assert "2 deps" in sk.lead
    assert "build" in sk.lead


def test_skeleton_for_never_raises_on_unreadable_or_unknown(tmp_path):
    _mk(tmp_path, "data.bin", "\x00\x01binary")
    sk = skeleton_for(tmp_path, _unit(tmp_path, "data.bin"))
    assert sk.lang == "other"  # unknown ext → stub, no crash


def test_brief_is_bounded_and_points_to_full_map(tmp_path):
    # Many files: the brief must stay compact (census, not per-file).
    for i in range(200):
        _mk(tmp_path, f"src/f{i}.py", f"def g{i}():\n    pass\n")
    skeletons = build_skeletons(tmp_path)
    brief = render_skeleton_brief(skeletons)
    full = render_skeleton_map(skeletons)
    assert len(brief) < 600          # bounded regardless of file count
    assert ".consejo/repo-skeleton.md" in brief
    assert "src=200" in brief        # per-directory census present
    assert len(full) > len(brief) * 10  # full map is the big one


def test_graph_python_relative_and_absolute_imports(tmp_path):
    _mk(tmp_path, "pkg/__init__.py", "")
    _mk(tmp_path, "pkg/a.py", "from .b import thing\nfrom pkg.c import other\n")
    _mk(tmp_path, "pkg/b.py", "x = 1\n")
    _mk(tmp_path, "pkg/c.py", "y = 2\n")
    g = build_dependency_graph(tmp_path, build_skeletons(tmp_path))
    assert set(g.edges["pkg/a.py"]) == {"pkg/b.py", "pkg/c.py"}
    assert g.fan_in["pkg/b.py"] == 1
    assert g.fan_in["pkg/c.py"] == 1
    assert g.fan_out["pkg/a.py"] == 2


def test_graph_excludes_external_imports(tmp_path):
    _mk(tmp_path, "m.py", "import os\nimport requests\nfrom collections import deque\n")
    g = build_dependency_graph(tmp_path, build_skeletons(tmp_path))
    assert g.edges["m.py"] == []  # os/requests/collections are not repo files


def test_graph_ts_relative_and_alias(tmp_path):
    _mk(tmp_path, "tsconfig.json",
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./src/*"]}}}')
    _mk(tmp_path, "src/lib/auth.ts", "export const login = 1;\n")
    _mk(tmp_path, "src/components/Button.tsx", "export function Button() {}\n")
    _mk(tmp_path, "src/app/page.tsx",
        "import { login } from '@/lib/auth';\n"
        "import { Button } from '../components/Button';\n"
        "import { useState } from 'react';\n")
    g = build_dependency_graph(tmp_path, build_skeletons(tmp_path))
    assert set(g.edges["src/app/page.tsx"]) == {
        "src/lib/auth.ts", "src/components/Button.tsx"}  # react excluded


def test_graph_detects_cycle_and_self_loop(tmp_path):
    _mk(tmp_path, "pkg/__init__.py", "")
    _mk(tmp_path, "pkg/a.py", "from .b import f\n")
    _mk(tmp_path, "pkg/b.py", "from .a import g\n")          # a <-> b cycle
    _mk(tmp_path, "pkg/leaf.py", "z = 1\n")                  # no cycle
    g = build_dependency_graph(tmp_path, build_skeletons(tmp_path))
    cyc_nodes = {n for c in g.cycles for n in c}
    assert {"pkg/a.py", "pkg/b.py"} <= cyc_nodes
    assert "pkg/leaf.py" not in cyc_nodes


def test_map_and_brief_render_connectivity(tmp_path):
    _mk(tmp_path, "pkg/__init__.py", "")
    _mk(tmp_path, "pkg/hub.py", "x = 1\n")
    for i in range(3):
        _mk(tmp_path, f"pkg/u{i}.py", "from .hub import x\n")
    sks = build_skeletons(tmp_path)
    g = build_dependency_graph(tmp_path, sks)
    full = render_skeleton_map(sks, g)
    brief = render_skeleton_brief(sks, g)
    assert "Conectividad" in full
    assert "Hubs" in full                           # connectivity section present
    assert "pkg/hub.py" in full and "← 3" in full   # hub surfaced with fan-in
    assert "→ usa" in full                          # per-file wiring shown
    assert "pkg/hub.py" in brief                    # hub surfaces in the brief too


def test_ts_alias_resolves_with_bom_tsconfig(tmp_path):
    # Regression: a UTF-8 BOM (common on Windows) used to make _loads_jsonc fail
    # silently → every '@/...' import dropped → frontend wiring invisible.
    _mk(tmp_path, "frontend/tsconfig.json",
        '﻿{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./src/*"]}}}')
    _mk(tmp_path, "frontend/src/lib/auth.ts", "export const login = 1;\n")
    _mk(tmp_path, "frontend/src/app/page.tsx",
        "import { login } from '@/lib/auth';\n")
    g = build_dependency_graph(tmp_path, build_skeletons(tmp_path))
    assert g.edges["frontend/src/app/page.tsx"] == ["frontend/src/lib/auth.ts"]


def test_score_ranks_hub_above_leaf(tmp_path):
    # hub is imported by many → high blast radius → must outrank an isolated leaf.
    _mk(tmp_path, "pkg/__init__.py", "")
    _mk(tmp_path, "pkg/hub.py", "x = 1\n")
    for i in range(5):
        _mk(tmp_path, f"pkg/u{i}.py", "from .hub import x\n")
    _mk(tmp_path, "pkg/leaf.py", "# isolated, nobody imports it\nz = 1\n")
    scores = score_files(build_skeletons(tmp_path),
                         build_dependency_graph(tmp_path, build_skeletons(tmp_path)))
    by_path = {f.path: f for f in scores}
    assert by_path["pkg/hub.py"].score > by_path["pkg/leaf.py"].score
    assert by_path["pkg/hub.py"].ca == 5
    assert scores == sorted(scores, key=lambda f: f.score, reverse=True)  # ranked
    assert 0 <= by_path["pkg/hub.py"].score <= 100


def test_score_flags_cycle_membership(tmp_path):
    _mk(tmp_path, "pkg/__init__.py", "")
    _mk(tmp_path, "pkg/a.py", "from .b import f\n")
    _mk(tmp_path, "pkg/b.py", "from .a import g\n")
    scores = {f.path: f for f in score_files(
        build_skeletons(tmp_path),
        build_dependency_graph(tmp_path, build_skeletons(tmp_path)))}
    assert scores["pkg/a.py"].in_cycle and scores["pkg/b.py"].in_cycle


def test_priority_section_in_map(tmp_path):
    _mk(tmp_path, "pkg/__init__.py", "")
    _mk(tmp_path, "pkg/hub.py", "x = 1\n")
    for i in range(3):
        _mk(tmp_path, f"pkg/u{i}.py", "from .hub import x\n")
    sks = build_skeletons(tmp_path)
    g = build_dependency_graph(tmp_path, sks)
    full = render_skeleton_map(sks, g)
    brief = render_skeleton_brief(sks, g)
    assert "Prioridad para el debate" in full
    assert "Prioridad de debate" in brief


def test_git_churn_counts_commits(tmp_path):
    import subprocess

    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a],
                       check=True, capture_output=True)
    git("init")
    git("config", "user.email", "t@t.test")
    git("config", "user.name", "tester")
    _mk(tmp_path, "a.py", "x = 1\n")
    git("add", "-A")
    git("commit", "-m", "1")
    _mk(tmp_path, "a.py", "x = 2\n")
    git("add", "-A")
    git("commit", "-m", "2")
    _mk(tmp_path, "b.py", "y = 1\n")
    git("add", "-A")
    git("commit", "-m", "3")
    churn = git_churn(tmp_path)
    assert churn.get("a.py") == 2   # touched in 2 commits
    assert churn.get("b.py") == 1


def test_git_churn_empty_on_non_git(tmp_path):
    _mk(tmp_path, "a.py", "x = 1\n")
    assert git_churn(tmp_path) == {}   # not a git repo → no churn, no crash


def test_score_churn_boosts_hot_file(tmp_path):
    # structurally identical leaves; the more-churned one must rank higher.
    _mk(tmp_path, "pkg/__init__.py", "")
    _mk(tmp_path, "pkg/cold.py", "def f():\n    pass\n")
    _mk(tmp_path, "pkg/hot.py", "def g():\n    pass\n")
    sks = build_skeletons(tmp_path)
    g = build_dependency_graph(tmp_path, sks)
    churn = {"pkg/hot.py": 50, "pkg/cold.py": 1}
    sc = {f.path: f for f in score_files(sks, g, churn)}
    assert sc["pkg/hot.py"].score > sc["pkg/cold.py"].score
    assert sc["pkg/hot.py"].churn == 50


def test_score_without_churn_is_structural(tmp_path):
    # churn=None path stays purely structural (backward compatible).
    _mk(tmp_path, "pkg/__init__.py", "")
    _mk(tmp_path, "pkg/a.py", "x = 1\n")
    sks = build_skeletons(tmp_path)
    g = build_dependency_graph(tmp_path, sks)
    assert all(f.churn == 0 for f in score_files(sks, g))


def test_compression_beats_source(tmp_path):
    _mk(tmp_path, "big.py",
        '"""Big module."""\n' + "\n".join(
            f"def fn_{i}(a, b, c):\n    x = a + b + c  # filler line\n    return x"
            for i in range(80)))
    skeletons = build_skeletons(tmp_path)
    full = render_skeleton_map(skeletons)
    raw = (tmp_path / "big.py").stat().st_size
    assert len(full.encode("utf-8")) < raw  # the map is smaller than the source
