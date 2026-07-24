"""Tests de la ronda estable: el consejo solo converge en una ronda donde TODOS
firman Y nadie tocó el plan. Una ronda unánime que aún enmendó deja firmas rancias
(emitidas contra un plan anterior) → una ronda más para confirmar o retractarse.
"""

from __future__ import annotations

import asyncio
import re

from consejo.consensus import consensus_dialogue
from consejo.sages import DEBATE_SAGES


class _RoundAwareStub:
    """Firma siempre. En ronda 1 cada sabio AÑADE (contribuye, requisito para
    firmar). Después: si `keep_amending`, sigue enmendando cada ronda (el plan
    nunca se congela); si no, calla (ronda quieta → debe converger)."""
    name = "stub"

    def __init__(self, keep_amending: bool):
        self.keep_amending = keep_amending
        self.n = 0

    def available(self) -> bool:
        return True

    async def spawn(self, *, user_msg, system_prompt, schema, repo, model,
                    allowed_tools="Read,Glob,Grep", timeout_s=300.0):
        if "product_questions" in (schema.get("properties") or {}):   # encuadre
            return {"product_questions": ["q"], "missed_angles": ["a"]}
        rnd = int((re.search(r"<round>(\d+)/", user_msg) or [0, 1])[1]) \
            if re.search(r"<round>(\d+)/", user_msg) else 1
        self.n += 1
        if rnd == 1 or self.keep_amending:
            diff = {"add": [{"title": f"T{self.n}", "rationale": "r",
                             "files_touched": ["a.py"], "blast_radius": "SAFE",
                             "horizon": "now"}]}
        else:
            diff = {}                                                 # ronda quieta
        return {"message": "ok", "plan_diff": diff,
                "vote": {"signed": True, "objections": [], "reasoning": "ok"},
                "_meta": {"output_tokens": 1}}


def test_converges_on_quiet_unanimous_round(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = _RoundAwareStub(keep_amending=False)
    plan = asyncio.run(consensus_dialogue(
        d, "q", tmp_path, DEBATE_SAGES, max_rounds=6, min_rounds=2, model="sonnet"))
    assert plan["unanimous"] is True
    # r1: contribuyen (firma suprimida); r2: callan + firman → ronda estable.
    assert plan["rounds_used"] == 2


def test_no_convergence_while_plan_keeps_changing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = _RoundAwareStub(keep_amending=True)
    plan = asyncio.run(consensus_dialogue(
        d, "q", tmp_path, DEBATE_SAGES, max_rounds=3, min_rounds=2, model="sonnet"))
    # cada ronda enmienda → nunca hay ronda quieta → no converge, agota max_rounds.
    assert plan["unanimous"] is False
    assert plan["rounds_used"] == 3
