"""Regression tests for the `--json-schema` opt-in flag.

The driver does NOT pass `--json-schema` by default: on claude 2.1.85 strict
validation swallowed every opus turn as an empty result (measured: 100%
empty-result retries in a real consensus debate), doubling cost and stripping
repo tools from the regenerated answer. The heuristic `_extract_json_object`
fallback is the default path. `CONSEJO_USE_JSON_SCHEMA=1` opts back in.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from consejo.claude_code_driver import (
    _build_claude_args,
    _json_schema_enabled,
)
from consejo.json_utils import _extract_json_object
from consejo.schemas import PROPOSAL_SCHEMA


def test_json_schema_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONSEJO_USE_JSON_SCHEMA", raising=False)
    assert _json_schema_enabled() is False


def test_json_schema_can_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONSEJO_USE_JSON_SCHEMA", "1")
    assert _json_schema_enabled() is True


def test_json_schema_enabled_only_for_explicit_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Opt-in is strict: only "1" enables it. Anything else stays off.
    monkeypatch.setenv("CONSEJO_USE_JSON_SCHEMA", "0")
    assert _json_schema_enabled() is False
    monkeypatch.setenv("CONSEJO_USE_JSON_SCHEMA", "true")
    assert _json_schema_enabled() is False


def test_args_include_serialized_schema_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONSEJO_USE_JSON_SCHEMA", "1")
    args = _build_claude_args(
        system_prompt="you are the architect",
        repo=Path("/tmp/repo"),
        model="claude-opus-4-7",
        schema=PROPOSAL_SCHEMA,
        allowed_tools="Read,Glob,Grep",
    )
    assert "--json-schema" in args
    schema_idx = args.index("--json-schema")
    serialized = args[schema_idx + 1]
    # Must be valid JSON and equal to PROPOSAL_SCHEMA when re-parsed.
    assert json.loads(serialized) == PROPOSAL_SCHEMA


def test_args_omit_schema_flag_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONSEJO_USE_JSON_SCHEMA", "0")
    args = _build_claude_args(
        system_prompt="you are the architect",
        repo=Path("/tmp/repo"),
        model="claude-opus-4-7",
        schema=PROPOSAL_SCHEMA,
        allowed_tools="Read,Glob,Grep",
    )
    assert "--json-schema" not in args


def test_args_always_include_core_claude_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CONSEJO_USE_JSON_SCHEMA", raising=False)
    args = _build_claude_args(
        system_prompt="sp",
        repo=Path("/tmp/r"),
        model="claude-opus-4-7",
        schema={},
        allowed_tools="Read",
    )
    assert args[:2] == ["claude", "-p"]
    assert "--output-format" in args
    assert "--system-prompt" in args
    assert "--no-session-persistence" in args
    assert "--allowedTools" in args


def test_extract_json_object_fallback_still_works() -> None:
    """The belt-and-suspenders fallback must keep parsing prose-wrapped JSON
    so the driver survives if --json-schema produces truncated output."""
    wrapped = 'preamble\n```json\n{"proposals": []}\n```\ntrailing text'
    parsed = _extract_json_object(wrapped)
    assert parsed == {"proposals": []}
