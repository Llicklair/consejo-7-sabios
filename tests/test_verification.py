"""Tests de la etapa verificadora (fact-checker adversarial post-consenso).

El consejo publicaba cifras que nunca midió ("5 de 30 sitios", "10-50x"); estas
pruebas cubren que `verify_plan_claims` adjunta el veredicto a cada tarea y que
`render_plan_markdown` saca del plan accionable las tareas REFUTADAS y muestra
el detalle afirmación→comando→observado.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from consejo.consensus import verify_plan_claims
from consejo.orchestrator import render_plan_markdown


class _StubDriver:
    """Driver falso: devuelve un veredicto canónico por título de tarea y cuenta
    cuántas veces se le invocó (para comprobar 1 spawn por tarea)."""

    name = "stub"

    def __init__(self, verdicts_by_title: dict[str, dict]):
        self._verdicts = verdicts_by_title
        self.calls = 0
        self.max_in_flight = 0
        self._in_flight = 0

    def available(self) -> bool:
        return True

    async def spawn(self, *, user_msg, system_prompt, schema, repo, model,
                    allowed_tools="Read,Glob,Grep", timeout_s=300.0) -> dict:
        self.calls += 1
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        await asyncio.sleep(0)  # ceder para permitir solape real bajo gather
        # El verificador recibe el título dentro del user_msg; lo localizamos.
        for title, verdict in self._verdicts.items():
            if title in user_msg:
                self._in_flight -= 1
                return dict(verdict)
        self._in_flight -= 1
        return {"verdict": "unverifiable", "claims": [], "files_exist": [],
                "note": "no match"}


def _plan(tasks: list[dict]) -> dict:
    return {
        "atasco_es": "como mejoramos esto",
        "summary": "resumen",
        "unanimous": True,
        "rounds_used": 3,
        "tasks": tasks,
    }


def test_verify_attaches_verdict_and_summary():
    tasks = [
        {"priority": 1, "title": "Acotar queries", "rationale": "r",
         "blast_radius": "SAFE"},
        {"priority": 2, "title": "Estrechar except", "rationale": "r",
         "blast_radius": "MEDIUM"},
    ]
    driver = _StubDriver({
        "Acotar queries": {"verdict": "solid", "claims": [], "files_exist": []},
        "Estrechar except": {"verdict": "refuted", "claims": [],
                             "files_exist": [], "note": "0 bare excepts"},
    })
    plan = asyncio.run(verify_plan_claims(driver, Path("."), _plan(tasks)))

    assert driver.calls == 2  # un spawn por tarea
    assert plan["tasks"][0]["verification"]["verdict"] == "solid"
    assert plan["tasks"][1]["verification"]["verdict"] == "refuted"
    assert plan["verification_summary"] == {
        "solid": 1, "weakened": 0, "refuted": 1, "total": 2,
    }


def test_core_refuted_claim_escalates_task_to_refuted():
    """Calibración 2026-05-30: si una claim marcada is_core se refuta, la tarea
    queda 'refuted' aunque el modelo la haya rodado a 'weakened'. El código
    fuerza la consecuencia; el modelo solo aporta el juicio (qué es core)."""
    tasks = [{"priority": 1, "title": "Extraer renderer real", "rationale": "r",
              "blast_radius": "MEDIUM"}]
    driver = _StubDriver({
        # El modelo rodó a 'weakened' pese a refutar la premisa central.
        "Extraer renderer real": {
            "verdict": "weakened",
            "claims": [
                {"claim": "no existe renderer real", "verdict": "refuted",
                 "is_core": True, "observed": "render_plan_markdown ya existe"},
                {"claim": "report.py es fake", "verdict": "verified",
                 "is_core": False},
            ],
            "files_exist": [],
        },
    })
    plan = asyncio.run(verify_plan_claims(driver, Path("."), _plan(tasks)))
    ver = plan["tasks"][0]["verification"]
    assert ver["verdict"] == "refuted"  # escalado forzado en código
    assert "premisa central refutada" in ver["note"]
    assert plan["verification_summary"]["refuted"] == 1


def test_peripheral_refuted_claim_does_not_escalate():
    """Una claim refutada NO-core no debe hundir la tarea: si el core aguanta,
    el veredicto del modelo (weakened) se respeta."""
    tasks = [{"priority": 1, "title": "T", "rationale": "r", "blast_radius": "SAFE"}]
    driver = _StubDriver({
        "T": {"verdict": "weakened", "files_exist": [], "claims": [
            {"claim": "detalle menor", "verdict": "refuted", "is_core": False},
            {"claim": "premisa", "verdict": "verified", "is_core": True},
        ]},
    })
    plan = asyncio.run(verify_plan_claims(driver, Path("."), _plan(tasks)))
    assert plan["tasks"][0]["verification"]["verdict"] == "weakened"  # sin escalar


def test_verify_empty_plan_is_noop():
    plan = asyncio.run(verify_plan_claims(_StubDriver({}), Path("."), _plan([])))
    assert plan["verification_summary"]["total"] == 0


def test_verify_failure_marks_unverifiable_not_crash():
    class _Boom(_StubDriver):
        async def spawn(self, **kw):
            raise RuntimeError("subprocess died")

    tasks = [{"priority": 1, "title": "X", "rationale": "r",
              "blast_radius": "SAFE"}]
    plan = asyncio.run(verify_plan_claims(_Boom({}), Path("."), _plan(tasks)))
    # Un verificador que revienta deja la tarea como no-comprobable, no hunde
    # el reporte entero.
    assert plan["tasks"][0]["verification"]["verdict"] == "unverifiable"
    assert plan["verification_summary"]["refuted"] == 0


def test_verify_bounded_concurrency():
    tasks = [{"priority": i, "title": f"T{i}", "rationale": "r",
              "blast_radius": "SAFE"} for i in range(6)]
    driver = _StubDriver({f"T{i}": {"verdict": "solid", "claims": [],
                                    "files_exist": []} for i in range(6)})
    asyncio.run(verify_plan_claims(driver, Path("."), _plan(tasks),
                                   max_concurrency=3))
    assert driver.max_in_flight <= 3  # el semáforo local respeta el techo


def test_render_demotes_refuted_out_of_actionable_table():
    tasks = [
        {"priority": 1, "title": "Tarea real", "blast_radius": "SAFE",
         "supporting_sages": ["guardian"],
         "verification": {"verdict": "solid", "claims": [
             {"claim": "153 .all() sin limit", "command": "grep -c .all()",
              "observed": "153", "verdict": "verified"}]}},
        {"priority": 2, "title": "Tarea fabricada", "blast_radius": "MEDIUM",
         "supporting_sages": ["optimizador"],
         "verification": {"verdict": "refuted",
                          "note": "Afirmaba 5 de 30; el repo tiene 92.",
                          "claims": [
             {"claim": "5 de 30 con eager-load", "command": "grep -c selectinload",
              "observed": "92 en 22 archivos", "verdict": "refuted"}]}},
    ]
    md = render_plan_markdown(_plan(tasks))

    # La refutada NO aparece como fila accionable, sí en su propia sección.
    assert "## ❌ Refutadas por la verificación" in md
    assert "Tarea fabricada" in md
    assert "Afirmaba 5 de 30" in md
    # El detalle muestra comando + observado.
    assert "## Verificación de afirmaciones" in md
    assert "92 en 22 archivos" in md
    # La columna Verif. existe en la tabla del plan.
    assert "Verif." in md


def test_render_without_verification_is_backward_compatible():
    # Plan sin campo `verification` (modo mock / etapa saltada): no rompe.
    tasks = [{"priority": 1, "title": "Algo", "blast_radius": "SAFE",
              "supporting_sages": []}]
    md = render_plan_markdown(_plan(tasks))
    assert "Algo" in md
    assert "## ❌ Refutadas" not in md  # nada que demover
