"""Tests del roster tras añadir el sabio de PRODUCTO (Opción A).

El sabio de producto DEBATE y VOTA como uno más, pero es voice-only (sin
sprite/asiento) para no requerir pixel-art. Debe contar para la unanimidad y NO
romper el seating del animador (que itera sobre SAGES, no DEBATE_SAGES).
"""

from __future__ import annotations

from consejo.sages import ALL_SAGES, DEBATE_SAGES, SAGES, by_id
from consejo.council_prompts import _consensus_system_prompt


def test_producto_exists_and_is_voice_only():
    p = by_id("producto")
    assert p.role == "Producto"
    assert p in ALL_SAGES
    assert p in DEBATE_SAGES          # debate y vota
    assert p not in SAGES             # voice-only: sin asiento/sprite


def test_debate_sages_count_and_no_juez():
    ids = [s.id for s in DEBATE_SAGES]
    assert "juez" not in ids          # el juez encuadra/sintetiza, no debate
    assert "producto" in ids
    # 6 ingenieros sentados + producto voice-only = 7 debatientes (= unanimidad)
    assert len(DEBATE_SAGES) == 7
    assert len(set(ids)) == len(ids)  # sin duplicados


def test_seating_unaffected_producto_not_seated():
    # El animador se sienta sobre SAGES; producto no debe estar ahí.
    assert all(s.id != "producto" for s in SAGES)
    assert len(SAGES) == 7            # los 6 ingenieros + juez (sin cambios)


def test_producto_system_prompt_has_product_mandate():
    sp = _consensus_system_prompt(by_id("producto"))
    assert "USER and the MARKET" in sp
    assert "LEGAL/REGULATORY" in sp
    assert "Conservative" in sp        # su foil
    # la regla de calibración (#2) también le aplica
    assert "medido:" in sp
