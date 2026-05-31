"""Tests de las dos mejoras del consejo:
- #2 calibración en origen: regla 'sin medida no hay cifra' en el system prompt.
- #1-B turno de encuadre: el juez siembra la lente de producto ANTES del debate,
  y ese encuadre se inyecta en cada turno de los seis ingenieros.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from consejo.council_prompts import (
    _consensus_system_prompt,
    _consensus_turn_user_message,
    _juez_framing_system_prompt,
    _juez_framing_user_message,
    render_framing,
)
from consejo.consensus import consensus_dialogue
from consejo.sages import DEBATE_SAGES, by_id
from consejo.schemas import FRAMING_SCHEMA


# ---------- #2 calibración ----------

def test_calibration_rule_in_system_prompt():
    p = _consensus_system_prompt(by_id("estructurador"))
    assert "medido:" in p                      # exige citar la medida inline
    assert "estimado" in p                     # alternativa cuando no se puede medir
    assert "without a receipt" in p.lower()


# ---------- #1-B encuadre: inyección en el turno ----------

def _msg(framing: str) -> str:
    return _consensus_turn_user_message(
        "¿mejoras?", Path("."), by_id("guardian"), [], [],
        round_num=1, max_rounds=8, turn_in_round=1, total_sages=6,
        repo_brief="", framing=framing)


def test_framing_block_injected_when_present():
    m = _msg("- Ángulo: añadir feature X")
    assert "<framing>" in m and "feature X" in m


def test_framing_block_absent_when_empty():
    assert "<framing>" not in _msg("")


def test_render_framing_lists_questions_and_angles():
    out = render_framing({"product_questions": ["¿Quién es el usuario?"],
                          "missed_angles": ["Algoritmo de ranking mejor"]})
    assert "¿Quién es el usuario?" in out
    assert "Algoritmo de ranking mejor" in out
    assert render_framing("no-dict") == ""     # robusto ante basura
    assert render_framing({}) == ""


def test_framing_schema_and_prompts_build():
    assert FRAMING_SCHEMA["type"] == "object"
    assert set(FRAMING_SCHEMA["required"]) == {"product_questions", "missed_angles"}
    sysp = _juez_framing_system_prompt()
    assert "WIDEN THE LENS" in sysp and "not voting" in sysp.lower() or "NOT voting" in sysp
    usr = _juez_framing_user_message("¿mejoras?", Path("."), repo_brief="MAPA")
    assert "missed_angles" in usr and "MAPA" in usr


# ---------- #1-B encuadre: integración con el diálogo ----------

class _StubDriver:
    """Devuelve un encuadre para el spawn del juez (FRAMING_SCHEMA) y un turno
    firmado para cada sabio. Registra (es_framing, user_msg) por llamada."""
    name = "stub"

    def __init__(self):
        self.calls: list[tuple[bool, str]] = []
        self._n = 0

    def available(self) -> bool:
        return True

    async def spawn(self, *, user_msg, system_prompt, schema, repo, model,
                    allowed_tools="Read,Glob,Grep", timeout_s=300.0):
        is_framing = "product_questions" in (schema.get("properties") or {})
        self.calls.append((is_framing, user_msg))
        if is_framing:
            return {"product_questions": ["¿Quién paga por esto?"],
                    "missed_angles": ["FEATURE-ZZZ: panel de métricas para el dueño"]}
        self._n += 1
        return {
            "message": "ok",
            "plan_diff": {"add": [{
                "title": f"Tarea {self._n}", "rationale": "r",
                "files_touched": ["a.py"], "blast_radius": "SAFE",
                "horizon": "now"}]},
            "vote": {"signed": True, "objections": [], "reasoning": "ok"},
            "_meta": {"output_tokens": 1},
        }


def test_dialogue_runs_framing_first_and_injects_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                # el live-log jsonl cae en tmp
    d = _StubDriver()
    asyncio.run(consensus_dialogue(
        d, "¿cómo mejoramos?", tmp_path, DEBATE_SAGES,
        max_rounds=2, min_rounds=2, model="sonnet", repo_brief="MAPA"))
    assert d.calls, "no hubo spawns"
    # 1) el PRIMER spawn es el encuadre del juez
    assert d.calls[0][0] is True, "el primer turno debe ser el encuadre"
    # 2) los turnos de los sabios llevan el encuadre inyectado
    sage_msgs = [msg for is_fr, msg in d.calls if not is_fr]
    assert sage_msgs, "no hubo turnos de sabios"
    assert any("<framing>" in m and "FEATURE-ZZZ" in m for m in sage_msgs), \
        "el encuadre del juez no llegó a los turnos de los sabios"
