"""Tests for the opt-in metrics module — answers the empirical thread from
the 20260527-183832 council report on real token consumption distribution.

The module MUST be zero-overhead when disabled (default) and MUST produce
a valid JSON dump only when explicitly enabled. These tests verify both
paths without spawning real subprocesses.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


def _fresh_metrics_module(monkeypatch: pytest.MonkeyPatch, enabled: bool):
    """Reload `consejo.metrics` with CONSEJO_METRICS set as requested.

    The enabled flag is captured at import time, so each test that toggles
    it needs a fresh module instance.
    """
    if enabled:
        monkeypatch.setenv("CONSEJO_METRICS", "1")
    else:
        monkeypatch.delenv("CONSEJO_METRICS", raising=False)
    sys.modules.pop("consejo.metrics", None)
    m = importlib.import_module("consejo.metrics")
    m.reset_for_tests()
    return m


def test_record_is_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _fresh_metrics_module(monkeypatch, enabled=False)
    assert m.is_enabled() is False
    m.record("subprocess", duration_s=1.0, stdout_bytes=500)
    assert m.snapshot() == []


def test_record_accumulates_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _fresh_metrics_module(monkeypatch, enabled=True)
    assert m.is_enabled() is True
    m.record("subprocess", duration_s=1.0, stdout_bytes=500)
    m.record("scan", files=42, aggregate_bytes=80_000)
    snap = m.snapshot()
    assert len(snap) == 2
    assert snap[0]["kind"] == "subprocess"
    assert snap[0]["stdout_bytes"] == 500
    assert snap[1]["kind"] == "scan"
    assert snap[1]["files"] == 42


def test_records_have_timestamps(monkeypatch: pytest.MonkeyPatch) -> None:
    m = _fresh_metrics_module(monkeypatch, enabled=True)
    m.record("scan", files=1)
    rec = m.snapshot()[0]
    assert "t" in rec
    assert isinstance(rec["t"], (int, float))
    assert rec["t"] >= 0


def test_dump_produces_valid_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    m = _fresh_metrics_module(monkeypatch, enabled=True)
    monkeypatch.chdir(tmp_path)
    m.record("subprocess", duration_s=2.5, stdout_bytes=10_000)
    m.record("scan", files=80, aggregate_bytes=120_000)
    m._dump()  # type: ignore[attr-defined]
    dumps = list(tmp_path.glob("consejo-metrics-*.json"))
    assert len(dumps) == 1
    data = json.loads(dumps[0].read_text(encoding="utf-8"))
    assert "started_at_unix" in data
    assert len(data["records"]) == 2
    assert data["records"][0]["kind"] == "subprocess"


def test_dump_is_noop_when_no_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    m = _fresh_metrics_module(monkeypatch, enabled=True)
    monkeypatch.chdir(tmp_path)
    m._dump()  # type: ignore[attr-defined]
    assert list(tmp_path.glob("consejo-metrics-*.json")) == []


def test_scan_project_records_metrics_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    m = _fresh_metrics_module(monkeypatch, enabled=True)
    # Reload orchestrator so it picks up the reloaded metrics module.
    sys.modules.pop("consejo.orchestrator", None)
    from consejo.orchestrator import scan_project
    for i in range(3):
        (tmp_path / f"f{i}.py").write_text("x" * 100)
    scan_project(tmp_path)
    scan_records = [r for r in m.snapshot() if r["kind"] == "scan"]
    assert len(scan_records) == 1
    assert scan_records[0]["files"] == 3
    assert scan_records[0]["aggregate_bytes"] == 300


def test_briefing_records_metrics_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    m = _fresh_metrics_module(monkeypatch, enabled=True)
    sys.modules.pop("consejo.orchestrator", None)
    from consejo.orchestrator import build_briefing
    from consejo.sages import SAGES
    files = [(f"f{i}.py", "y" * 100) for i in range(5)]
    build_briefing(files, for_sage=SAGES[0])
    briefing_records = [r for r in m.snapshot() if r["kind"] == "briefing"]
    assert len(briefing_records) == 1
    rec = briefing_records[0]
    assert rec["sage"] == SAGES[0].id
    assert rec["files_offered"] == 5
    assert rec["files_included"] == 5
    assert rec["briefing_bytes"] > 0
