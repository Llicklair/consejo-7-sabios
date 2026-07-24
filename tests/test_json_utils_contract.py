"""Contract tests for `consejo.json_utils._extract_json_object`.

The function's type hint promises `-> dict`. Today it happily returns
whatever `json.loads` produces — a list, a string, `None`, an int — as
long as the text parses as valid JSON *before* the balanced-brace
fallback kicks in. That silently violates the declared contract and
pushes a `TypeError` (or worse, silent wrong behavior) downstream into
whatever code assumes `.get(...)` works on the result.

These tests pin the *existing* supported inputs (bare object, fenced
object, object with prose around it) and the *promised* contract for
non-object JSON: it must raise `json.JSONDecodeError`, not return the
value as-is.
"""

from __future__ import annotations

import json

import pytest

from consejo.json_utils import _extract_json_object


# --- Existing, already-supported behavior: valid objects -> dict -------


def test_bare_object_returns_dict() -> None:
    assert _extract_json_object('{"a": 1}') == {"a": 1}


def test_fenced_object_returns_dict() -> None:
    wrapped = '```json\n{"a": 1}\n```'
    assert _extract_json_object(wrapped) == {"a": 1}


def test_object_with_surrounding_prose_returns_dict() -> None:
    wrapped = 'preamble text\n{"a": 1}\ntrailing text'
    assert _extract_json_object(wrapped) == {"a": 1}


# --- Contract: non-object JSON must raise, not be returned as-is -------


def test_array_of_ints_raises_json_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        _extract_json_object("[1,2,3]")


def test_array_of_objects_never_returns_non_dict() -> None:
    # The plausible model mistake: wrapping the payload in a list. The TRUE
    # contract is "never return a non-dict": raising is valid, and so is
    # unwrapping the embedded object via the balanced-brace fallback — both
    # keep the promise. Returning the raw list is the only failure.
    try:
        result = _extract_json_object('[{"plan": 1}]')
    except json.JSONDecodeError:
        return
    assert isinstance(result, dict)


def test_bare_string_raises_json_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        _extract_json_object('"texto"')


def test_null_raises_json_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        _extract_json_object("null")


def test_number_raises_json_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        _extract_json_object("42")


def test_fenced_array_raises_json_decode_error() -> None:
    wrapped = "```json\n[1,2,3]\n```"
    with pytest.raises(json.JSONDecodeError):
        _extract_json_object(wrapped)
