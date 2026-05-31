"""Tests del gate de cobertura del debate (breadth floor).

El consejo excavaba el primer filón coherente y firmaba en 2-3 rondas, ignorando
el 95% del repo. Las zonas (deterministas) + el scorecard por turno + la regla de
breadth-floor obligan a CONSIDERAR cada zona mayor antes de firmar: proponer un
ítem real o nombrar la omisión consciente.
"""

from __future__ import annotations

from pathlib import Path

from consejo.repo_skeleton import (
    Zone,
    _zone_of,
    build_dependency_graph,
    build_skeletons,
    render_coverage,
    repo_zones,
)
from consejo.council_prompts import (
    _consensus_system_prompt,
    _consensus_turn_user_message,
)
from consejo.sages import by_id


def _mk(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_zone_of_caps_at_three_segments():
    assert _zone_of("backend/app/agents/billing/tools.py") == "backend/app/agents"
    assert _zone_of("frontend/src/lib/api/client.ts") == "frontend/src/lib"
    assert _zone_of("backend/app/main.py") == "backend/app"
    assert _zone_of("README.md") == "(root)"


def test_repo_zones_ranked_by_importance(tmp_path):
    _mk(tmp_path, "pkg_a/__init__.py", "")
    _mk(tmp_path, "pkg_a/hub.py", "x = 1\n")
    for i in range(4):                       # pkg_a/hub gets fan-in → higher score
        _mk(tmp_path, f"pkg_a/u{i}.py", "from .hub import x\n")
    _mk(tmp_path, "pkg_b/leaf.py", "y = 1\n")
    sks = build_skeletons(tmp_path)
    g = build_dependency_graph(tmp_path, sks)
    names = [z.name for z in repo_zones(sks, g)]
    assert "pkg_a" in names and "pkg_b" in names
    assert names.index("pkg_a") < names.index("pkg_b")   # más importante primero


def test_render_coverage_marks_touched_and_flags_gaps():
    zones = [Zone("backend/app/core", 10, 50.0), Zone("frontend/src", 20, 30.0)]
    plan = [{"title": "T", "files_touched": ["backend/app/core/config.py"]}]
    out = render_coverage(plan, zones)
    assert "backend/app/core" in out and "✓ 1" in out
    assert "frontend/src" in out and "SIN TOCAR" in out
    assert "SIN ningún ítem" in out          # el empujón de breadth
    assert render_coverage(plan, []) == ""   # sin zonas, sin scorecard


def _turn(coverage: str) -> str:
    return _consensus_turn_user_message(
        "q", Path("."), by_id("guardian"), [], [],
        round_num=1, max_rounds=8, turn_in_round=1, total_sages=7,
        coverage=coverage)


def test_coverage_block_injected_when_present():
    m = _turn("`frontend/src` ✗ SIN TOCAR")
    assert "<coverage>" in m and "frontend/src" in m


def test_coverage_block_absent_when_empty():
    assert "<coverage>" not in _turn("")


def test_breadth_floor_rule_in_system_prompt():
    p = _consensus_system_prompt(by_id("estructurador"))
    assert "Breadth floor" in p
    assert "keyhole" in p
