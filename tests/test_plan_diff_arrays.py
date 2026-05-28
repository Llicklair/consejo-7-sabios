"""Regression tests for the plan_diff array-mutation meta-bug.

Before this fix, `_apply_plan_diff` could amend scalar fields (title,
rationale, blast_radius) but had no way to change `files_touched`. Items
with wrong/missing file references became 'immortal cockroaches' — every
sage tried to fix them across multiple rounds without success because the
patch vocabulary literally could not express the change.

The fix extends `amend` with `new_files_touched` (full-array replacement,
symmetric with `new_title`/`new_rationale`/`new_blast_radius`). Tests verify
the mutation works, is idempotent on re-apply, and tolerates edge inputs.
"""

from __future__ import annotations

from consejo.claude_code_driver import TURN_SCHEMA, _apply_plan_diff


def _seed_plan() -> list[dict]:
    return [
        {
            "title": "Cap aggregate scan payload",
            "rationale": "prevent token exhaustion",
            "blast_radius": "SAFE",
            "files_touched": ["wrong/path.py"],
        },
    ]


def test_amend_can_replace_files_touched() -> None:
    plan = _seed_plan()
    diff = {
        "amend": [{
            "target_title": "Cap aggregate scan payload",
            "new_files_touched": ["src/consejo/orchestrator.py"],
        }],
    }
    out = _apply_plan_diff(plan, diff)
    assert out[0]["files_touched"] == ["src/consejo/orchestrator.py"]


def test_amend_files_touched_does_not_mutate_input() -> None:
    plan = _seed_plan()
    diff = {
        "amend": [{
            "target_title": "Cap aggregate scan payload",
            "new_files_touched": ["fixed.py"],
        }],
    }
    out = _apply_plan_diff(plan, diff)
    assert plan[0]["files_touched"] == ["wrong/path.py"], (
        "_apply_plan_diff must not mutate the input plan in place."
    )
    assert out[0]["files_touched"] == ["fixed.py"]


def test_amend_files_touched_to_empty_list_is_allowed() -> None:
    plan = _seed_plan()
    diff = {
        "amend": [{
            "target_title": "Cap aggregate scan payload",
            "new_files_touched": [],
        }],
    }
    out = _apply_plan_diff(plan, diff)
    assert out[0]["files_touched"] == []


def test_amend_files_touched_is_idempotent() -> None:
    plan = _seed_plan()
    diff = {
        "amend": [{
            "target_title": "Cap aggregate scan payload",
            "new_files_touched": ["src/a.py", "src/b.py"],
        }],
    }
    once = _apply_plan_diff(plan, diff)
    twice = _apply_plan_diff(once, diff)
    assert once == twice


def test_amend_files_touched_combines_with_scalar_amends() -> None:
    plan = _seed_plan()
    diff = {
        "amend": [{
            "target_title": "Cap aggregate scan payload",
            "new_rationale": "stop token exhaustion via hard cap",
            "new_blast_radius": "MEDIUM",
            "new_files_touched": ["src/consejo/orchestrator.py"],
        }],
    }
    out = _apply_plan_diff(plan, diff)
    assert out[0]["rationale"] == "stop token exhaustion via hard cap"
    assert out[0]["blast_radius"] == "MEDIUM"
    assert out[0]["files_touched"] == ["src/consejo/orchestrator.py"]


def test_amend_files_touched_on_unknown_target_is_noop() -> None:
    plan = _seed_plan()
    diff = {
        "amend": [{
            "target_title": "does not exist",
            "new_files_touched": ["nope.py"],
        }],
    }
    out = _apply_plan_diff(plan, diff)
    assert out == plan


def test_turn_schema_declares_new_files_touched() -> None:
    """If the schema doesn't advertise the field, the model can't use it
    when `--json-schema` constrains output. Make the contract explicit."""
    amend_props = (
        TURN_SCHEMA["properties"]["plan_diff"]
                   ["properties"]["amend"]
                   ["items"]["properties"]
    )
    assert "new_files_touched" in amend_props
    assert amend_props["new_files_touched"]["type"] == "array"
    assert amend_props["new_files_touched"]["items"] == {"type": "string"}
