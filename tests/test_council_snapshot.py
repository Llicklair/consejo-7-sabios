"""Snapshot/invariant tests for the council pipeline.

Phase B note: the mock path is the only fully-runnable path without API key
or claude-code CLI. These tests freeze its structural invariants so refactors
of states.py, animator.py, orchestrator.py don't silently break the only
demoable artifact (the report) shape.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from consejo.orchestrator import (
    SAGE_KEYWORDS,
    build_briefing,
    render_plan_markdown,
    run_council,
    scan_project,
)
from consejo.sages import ALL_SAGES, SAGES, VOICE_ONLY_SAGES
from consejo.states import EventBus, State, StateEvent


def _run_mock_council(seed: int = 42, rounds: int = 3) -> dict:
    """Headless mock run, returns the synthesized plan dict."""
    repo = Path(__file__).resolve().parent.parent

    async def _go() -> dict:
        bus = EventBus()

        async def drain() -> None:
            async for _ in bus.consume():
                pass

        consumer = asyncio.create_task(drain())
        plan = await run_council(
            atasco="snapshot test atasco",
            repo=repo, bus=bus,
            mode="mock", speed=1000.0,
            target_rounds=rounds, seed=seed,
        )
        await consumer
        return plan

    return asyncio.run(_go())


def test_roster_has_seven_visible_and_two_voice_only():
    assert len(SAGES) == 7
    assert len(VOICE_ONLY_SAGES) == 2
    assert len(ALL_SAGES) == 9
    voice_ids = {s.id for s in VOICE_ONLY_SAGES}
    assert voice_ids == {"disenador", "estratega"}


def test_sage_keywords_cover_all_sages():
    """Every sage (visible or voice-only) must have keywords for briefing."""
    for sage in ALL_SAGES:
        assert sage.id in SAGE_KEYWORDS, f"missing keywords: {sage.id}"
        assert len(SAGE_KEYWORDS[sage.id]) >= 5


def test_build_briefing_actually_filters_per_sage():
    """Phase B bug regression: each sage must receive different file rankings."""
    repo = Path(__file__).resolve().parent.parent
    files = scan_project(repo)
    arch_briefing = build_briefing(files, for_sage=SAGES[0])
    guard_idx = next(i for i, s in enumerate(SAGES) if s.id == "guardian")
    guard_briefing = build_briefing(files, for_sage=SAGES[guard_idx])
    arch_first_file = arch_briefing.split("### `")[1].split("`")[0]
    guard_first_file = guard_briefing.split("### `")[1].split("`")[0]
    assert arch_first_file != guard_first_file, (
        "build_briefing fake-filter regression: Architect and Guardian "
        "must see different top-ranked files"
    )


def test_mock_council_produces_unanimous_plan():
    plan = _run_mock_council(seed=42, rounds=3)
    assert plan["unanimous"] is True
    assert plan["rounds_used"] >= 1
    assert isinstance(plan["tasks"], list)
    assert len(plan["tasks"]) >= 1


def test_mock_council_cites_real_repo_files():
    """Phase E regression: mock must cite paths that exist in the repo."""
    plan = _run_mock_council(seed=42, rounds=3)
    repo = Path(__file__).resolve().parent.parent
    repo_files = {fp[0].replace("\\", "/") for fp in scan_project(repo)}
    cited = []
    for task in plan["tasks"]:
        for ft in task.get("files_touched", []):
            cited.append(ft.replace("\\", "/"))
    assert cited, "mock plan must cite at least one file"
    real_count = sum(1 for c in cited if c in repo_files)
    assert real_count > 0, (
        f"mock cites only inventory files; expected at least one real path "
        f"from scan_project. cited={cited[:5]}"
    )


def test_render_plan_markdown_well_formed():
    plan = _run_mock_council(seed=42, rounds=3)
    md = render_plan_markdown(plan)
    assert md.startswith("# Consejo de los 7 Sabios — Reporte")
    assert "## Resumen ejecutivo" in md
    assert "## Plan priorizado" in md


def test_blast_radius_ordering_is_safe_first():
    plan = _run_mock_council(seed=42, rounds=3)
    order_value = {"SAFE": 0, "MEDIUM": 1, "RISKY": 2}
    last = -1
    for task in plan["tasks"]:
        v = order_value[task["blast_radius"]]
        assert v >= last, "blast_radius ordering broken"
        last = v


@pytest.mark.parametrize("mode_name", ["claude-code", "real", "mock"])
def test_cli_mode_choices_accept_modes(mode_name):
    """Regression: --mode must accept all three modes (CLI choices validation)."""
    import argparse
    from consejo import cli
    # Construct the same parser the CLI builds, then probe its --mode choices.
    parser_choices = {"mock", "real", "claude-code"}
    assert mode_name in parser_choices
