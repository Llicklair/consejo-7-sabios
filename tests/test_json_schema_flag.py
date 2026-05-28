"""Regression tests for item 7 of the 20260527-183832 council plan.

The driver should pass `--json-schema <schema>` to the claude CLI by default
(structured output, constrains the model to schema-valid JSON) but allow
disabling via `CONSEJO_USE_JSON_SCHEMA=0` so the Conservador's belt-and-
suspenders fallback (`_extract_json_object`) remains reachable until the
truncation rate of --json-schema is measured in a real-mode debate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from consejo.claude_code_driver import (
    PROPOSAL_SCHEMA,
    _build_claude_args,
    _extract_json_object,
    _json_schema_enabled,
)


def test_json_schema_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONSEJO_USE_JSON_SCHEMA", raising=False)
    assert _json_schema_enabled() is True


def test_json_schema_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONSEJO_USE_JSON_SCHEMA", "0")
    assert _json_schema_enabled() is False


def test_json_schema_enabled_for_any_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONSEJO_USE_JSON_SCHEMA", "1")
    assert _json_schema_enabled() is True
    monkeypatch.setenv("CONSEJO_USE_JSON_SCHEMA", "true")
    assert _json_schema_enabled() is True


def test_args_include_serialized_schema_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CONSEJO_USE_JSON_SCHEMA", raising=False)
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
