"""Regression tests for items 1+4 of the 20260527-183832 council plan.

`scan_project` and `build_briefing` must respect aggregate payload caps so a
debate cannot run out of token budget mid-flight — the root cause of the
20260527-171503 unanimity failure.
"""

from __future__ import annotations

from pathlib import Path

from consejo.orchestrator import (
    MAX_BRIEFING_PAYLOAD_BYTES,
    MAX_SCAN_PAYLOAD_BYTES,
    build_briefing,
    scan_project,
)
from consejo.sages import SAGES


def test_scan_project_respects_default_aggregate_cap(tmp_path: Path) -> None:
    # 200 files × 4KB = ~800KB raw, far above the 120KB default cap.
    for i in range(200):
        (tmp_path / f"f{i:03d}.py").write_text("x" * 4000)
    files = scan_project(tmp_path, max_files=500, max_bytes_per_file=4000)
    aggregate = sum(len(content) for _, content in files)
    assert aggregate <= MAX_SCAN_PAYLOAD_BYTES, (
        f"scan_project returned {aggregate} bytes, cap is "
        f"{MAX_SCAN_PAYLOAD_BYTES}. Without this cap, large repos can blow "
        f"the token budget mid-debate (council report 20260527-171503)."
    )


def test_scan_project_aggregate_cap_is_parameterizable(tmp_path: Path) -> None:
    for i in range(50):
        (tmp_path / f"f{i:03d}.py").write_text("x" * 4000)
    files = scan_project(
        tmp_path,
        max_files=500,
        max_bytes_per_file=4000,
        max_aggregate_bytes=20_000,
    )
    aggregate = sum(len(content) for _, content in files)
    assert aggregate <= 20_000


def test_scan_project_under_cap_returns_everything(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"f{i}.py").write_text(f"content {i}")
    files = scan_project(tmp_path)
    assert len(files) == 5


def test_build_briefing_respects_default_aggregate_cap() -> None:
    # 500 files × 1200 chars = ~600KB raw, far above the 150KB cap.
    huge_files = [(f"file{i:03d}.py", "y" * 1200) for i in range(500)]
    briefing = build_briefing(
        huge_files,
        for_sage=SAGES[0],
        max_files_in_briefing=500,
    )
    assert len(briefing) <= MAX_BRIEFING_PAYLOAD_BYTES, (
        f"build_briefing returned {len(briefing)} bytes, cap is "
        f"{MAX_BRIEFING_PAYLOAD_BYTES}."
    )


def test_build_briefing_aggregate_cap_is_parameterizable() -> None:
    huge_files = [(f"file{i:03d}.py", "y" * 1200) for i in range(50)]
    briefing = build_briefing(
        huge_files,
        max_files_in_briefing=50,
        max_aggregate_bytes=5_000,
    )
    assert len(briefing) <= 5_000


def test_build_briefing_under_cap_includes_all_selected_files() -> None:
    files = [(f"f{i}.py", "small") for i in range(3)]
    briefing = build_briefing(files, for_sage=SAGES[0])
    for path, _ in files:
        assert path in briefing
