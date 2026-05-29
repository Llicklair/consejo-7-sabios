"""Tests de `_apply_plan_diff` (ítem 7 del plan del consejo 20260529-182257).

Cubre add / amend (todos los campos) / remove / rename, y en particular la
regresión del bug que el propio consejo detectó: `titles[new_t] = out.index(item)`
usaba igualdad en vez del índice conocido, así que tras una colisión de título
el mapa apuntaba al ítem equivocado.
"""

from __future__ import annotations

from consejo.consensus import _apply_plan_diff


def test_add_appends_new_items():
    out = _apply_plan_diff([], {"add": [{"title": "A", "rationale": "r"}]})
    assert [p["title"] for p in out] == ["A"]


def test_add_skips_duplicate_titles():
    plan = [{"title": "A", "rationale": "r1"}]
    out = _apply_plan_diff(plan, {"add": [{"title": "A", "rationale": "r2"}]})
    assert len(out) == 1
    assert out[0]["rationale"] == "r1"  # el duplicado se ignora


def test_amend_updates_all_scalar_fields():
    plan = [{"title": "A", "rationale": "old", "blast_radius": "SAFE",
             "category": "code-fix", "horizon": "now"}]
    out = _apply_plan_diff(plan, {"amend": [{
        "target_title": "A",
        "new_rationale": "new",
        "new_blast_radius": "RISKY",
        "new_category": "future-feature",
        "new_horizon": "next-quarter",
    }]})
    item = out[0]
    assert item["rationale"] == "new"
    assert item["blast_radius"] == "RISKY"
    assert item["category"] == "future-feature"
    assert item["horizon"] == "next-quarter"


def test_amend_new_files_touched_replaces_array():
    plan = [{"title": "A", "files_touched": ["old.py"]}]
    out = _apply_plan_diff(plan, {"amend": [{
        "target_title": "A", "new_files_touched": ["a.py", "b.py"],
    }]})
    assert out[0]["files_touched"] == ["a.py", "b.py"]


def test_amend_unknown_target_is_noop():
    plan = [{"title": "A", "rationale": "r"}]
    out = _apply_plan_diff(plan, {"amend": [{"target_title": "ghost",
                                             "new_rationale": "x"}]})
    assert out[0]["rationale"] == "r"


def test_amend_rename_updates_title_and_map():
    plan = [{"title": "A", "rationale": "r"}]
    out = _apply_plan_diff(plan, {"amend": [{"target_title": "A",
                                             "new_title": "B"}]})
    assert out[0]["title"] == "B"
    # El nuevo título debe ser direccionable por un amend posterior.
    out2 = _apply_plan_diff(out, {"amend": [{"target_title": "B",
                                             "new_rationale": "r2"}]})
    assert out2[0]["rationale"] == "r2"


def test_remove_drops_item():
    plan = [{"title": "A"}, {"title": "B"}]
    out = _apply_plan_diff(plan, {"remove": ["A"]})
    assert [p["title"] for p in out] == ["B"]


def test_rename_collision_maps_to_renamed_item_not_duplicate():
    """Regresión del bug `out.index(item)`: al renombrar un ítem a un título que
    ya existe con contenido idéntico, el mapa debe apuntar al ítem RENOMBRADO
    (índice conocido), no al primer ítem de igual contenido."""
    plan = [
        {"title": "T", "rationale": "shared"},
        {"title": "other", "rationale": "shared"},
    ]
    # rename "other" -> "T": dos ítems con título "T" e idéntico contenido.
    out = _apply_plan_diff(plan, {"amend": [{"target_title": "other",
                                             "new_title": "T"}]})
    # Un amend posterior de "T" debe alcanzar el ítem renombrado (índice 1).
    # Con el bug (out.index), el mapa apuntaba al índice 0 y cambiaba el ítem
    # equivocado.
    out2 = _apply_plan_diff(out, {"amend": [{"target_title": "T",
                                             "new_rationale": "CHANGED"}]})
    assert out2[1]["rationale"] == "CHANGED"   # el renombrado se actualizó
    assert out2[0]["rationale"] == "shared"    # el original quedó intacto


def test_empty_diff_returns_plan_unchanged():
    plan = [{"title": "A"}]
    assert _apply_plan_diff(plan, {}) == plan
