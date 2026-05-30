"""Tests del paso de análisis (P1): cobertura COMPLETA y determinista.

Lo que se valida — sin gastar LLM, con un driver stub:
- El enumerador y el hash son deterministas y detectan cambios (frescura).
- El ledger persiste, reconcilia (borra eliminados), y marca stale lo cambiado.
- El batcher respeta los topes de bytes/conteo.
- El BUCLE garantiza la completitud: el recibo re-encola lo omitido, y la cota
  de reintentos termina dejando los huecos VISIBLES, nunca perdidos en silencio.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from consejo.analysis import (
    AnalysisLedger,
    FileUnit,
    LedgerEntry,
    batch_units,
    coverage_summary,
    enumerate_units,
    render_repo_map,
    run_analysis_pass,
)


# ---------- enumeración + hash ----------

def _mk(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_enumerate_lists_source_files_and_hashes(tmp_path: Path):
    _mk(tmp_path, "a.py", "print(1)")
    _mk(tmp_path, "pkg/b.py", "x = 2")
    _mk(tmp_path, "node_modules/junk.js", "skip me")  # excluido
    _mk(tmp_path, "image.png", "binary-ish")          # extensión no escaneada
    units = enumerate_units(tmp_path)
    paths = {u.path for u in units}
    assert paths == {"a.py", "pkg/b.py"}
    assert all(len(u.content_hash) == 40 for u in units)  # sha1 hex


def test_hash_changes_with_content(tmp_path: Path):
    _mk(tmp_path, "a.py", "v1")
    h1 = enumerate_units(tmp_path)[0].content_hash
    _mk(tmp_path, "a.py", "v2")
    h2 = enumerate_units(tmp_path)[0].content_hash
    assert h1 != h2


# ---------- ledger ----------

def test_ledger_roundtrip(tmp_path: Path):
    led = AnalysisLedger({"a.py": LedgerEntry("a.py", "hhh", "abc123",
                                              {"path": "a.py", "purpose": "p"})})
    p = tmp_path / ".consejo" / "ledger.json"
    led.save(p)
    back = AnalysisLedger.load(p)
    assert back.entries["a.py"].content_hash == "hhh"
    assert back.entries["a.py"].finding["purpose"] == "p"


def test_ledger_corrupt_file_rebuilds(tmp_path: Path):
    p = tmp_path / "ledger.json"
    p.write_text("{ this is not json", encoding="utf-8")
    led = AnalysisLedger.load(p)  # no debe reventar
    assert led.entries == {}


def test_is_covered_requires_matching_hash_and_finding():
    led = AnalysisLedger()
    u = FileUnit("a.py", 10, "hash1")
    assert not led.is_covered(u)                       # sin entrada
    led.mark_analyzed(u, {"purpose": "p"})
    assert led.is_covered(u)                            # ahora cubierto
    u2 = FileUnit("a.py", 12, "hash2")                  # mismo path, hash nuevo
    assert not led.is_covered(u2)                       # stale -> pendiente


def test_reconcile_drops_deleted_files():
    led = AnalysisLedger()
    led.mark_analyzed(FileUnit("gone.py", 1, "h"), {"purpose": "p"})
    led.mark_analyzed(FileUnit("keep.py", 1, "h"), {"purpose": "p"})
    led.reconcile([FileUnit("keep.py", 1, "h")])
    assert set(led.entries) == {"keep.py"}


# ---------- batcher ----------

def test_batch_respects_file_cap():
    units = [FileUnit(f"f{i}.py", 10, "h") for i in range(45)]
    batches = batch_units(units, max_bytes=10_000, max_files=20)
    assert [len(b) for b in batches] == [20, 20, 5]


def test_batch_respects_byte_cap_and_oversized_file_is_own_batch():
    units = [FileUnit("small.py", 100, "h"),
             FileUnit("huge.py", 99_999, "h"),   # > max_bytes -> su propio lote
             FileUnit("small2.py", 100, "h")]
    batches = batch_units(units, max_bytes=50_000, max_files=20)
    # small va solo (huge no cabe con él), huge solo, small2 solo.
    assert [[u.path for u in b] for b in batches] == [
        ["small.py"], ["huge.py"], ["small2.py"],
    ]


# ---------- el bucle completo (driver stub) ----------

class _StubAnalyzer:
    """Devuelve un finding por cada archivo del manifest, salvo los `skip`
    (para simular que el analizador omite archivos → deben re-encolarse)."""

    name = "stub"

    def __init__(self, skip: set[str] | None = None, skip_rounds: int = 99):
        self.skip = skip or set()
        self.skip_rounds = skip_rounds   # nº de rondas que sigue omitiendo
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
        await asyncio.sleep(0)
        # Extrae el manifest del user_msg.
        start = user_msg.index("<manifest>") + len("<manifest>")
        end = user_msg.index("</manifest>")
        manifest = json.loads(user_msg[start:end])
        files = []
        for path in manifest:
            if path in self.skip and self.skip_rounds > 0:
                continue  # omitido a propósito
            files.append({"path": path, "purpose": f"purpose of {path}",
                          "role": "core", "key_symbols": [], "concerns": []})
        if self.skip_rounds > 0:
            self.skip_rounds -= 1
        self._in_flight -= 1
        return {"files": files}


def _units(n: int) -> list[FileUnit]:
    return [FileUnit(f"f{i}.py", 100, f"h{i}") for i in range(n)]


def test_pass_covers_everything(tmp_path: Path, monkeypatch):
    # enumerate_units real sobre un tmp repo con 5 archivos.
    for i in range(5):
        _mk(tmp_path, f"f{i}.py", f"content {i}")
    led = asyncio.run(run_analysis_pass(
        _StubAnalyzer(), tmp_path, ledger_path=tmp_path / ".consejo" / "led.json",
    ))
    units = enumerate_units(tmp_path)
    covered, total = led.coverage(units)
    assert covered == total == 5


def test_receipt_requeues_skipped_then_covers(tmp_path: Path):
    for i in range(4):
        _mk(tmp_path, f"f{i}.py", f"c{i}")
    # Omite f2.py en la 1ª ronda, lo entrega en la 2ª.
    stub = _StubAnalyzer(skip={"f2.py"}, skip_rounds=1)
    led = asyncio.run(run_analysis_pass(
        stub, tmp_path, ledger_path=tmp_path / ".consejo" / "led.json",
    ))
    units = enumerate_units(tmp_path)
    assert led.coverage(units) == (4, 4)   # acabó cubriendo el omitido
    assert stub.calls >= 2                  # hubo una ronda extra por el recibo


def test_persistently_skipped_file_recorded_not_silently_dropped(tmp_path: Path):
    for i in range(3):
        _mk(tmp_path, f"f{i}.py", f"c{i}")
    # Omite f1.py SIEMPRE → tras la cota de reintentos debe quedar registrado
    # como 'unanalyzed', visible, no perdido.
    stub = _StubAnalyzer(skip={"f1.py"}, skip_rounds=99)
    led = asyncio.run(run_analysis_pass(
        stub, tmp_path, ledger_path=tmp_path / ".consejo" / "led.json",
    ))
    units = enumerate_units(tmp_path)
    # El bucle termina (no cuelga) y f1.py tiene entrada explícita unanalyzed.
    entry = led.entries["f1.py"]
    assert entry.finding["role"] == "unanalyzed"
    summ = coverage_summary(led, units)
    assert "f1.py" in summ["unanalyzed"]


def test_resume_skips_already_covered(tmp_path: Path):
    for i in range(3):
        _mk(tmp_path, f"f{i}.py", f"c{i}")
    lp = tmp_path / ".consejo" / "led.json"
    stub1 = _StubAnalyzer()
    asyncio.run(run_analysis_pass(stub1, tmp_path, ledger_path=lp))
    calls_first = stub1.calls
    # Segunda corrida sin cambios: nada pendiente → cero llamadas al analizador.
    stub2 = _StubAnalyzer()
    asyncio.run(run_analysis_pass(stub2, tmp_path, ledger_path=lp))
    assert calls_first >= 1
    assert stub2.calls == 0


def test_render_repo_brief_bounded_with_signal():
    from consejo.analysis import render_repo_brief
    units = [FileUnit(f"backend/f{i}.py", 100, f"h{i}") for i in range(3)]
    led = AnalysisLedger()
    led.mark_analyzed(units[0], {"role": "core", "purpose": "p",
                                 "concerns": ["c1 grave", "c2"]})
    led.mark_analyzed(units[1], {"role": "test", "purpose": "p", "concerns": []})
    led.mark_analyzed(units[2], {"role": "core", "purpose": "p",
                                 "concerns": ["c3"]})
    brief = render_repo_brief(led, units)
    assert "Cobertura" in brief
    assert "c1 grave" in brief           # los concerns (señal accionable)
    assert "backend=3" in brief          # censo por directorio raíz
    assert "core=2" in brief             # censo por rol


def test_render_repo_brief_caps_concerns():
    from consejo.analysis import render_repo_brief
    units = [FileUnit(f"x{i}.py", 100, f"h{i}") for i in range(100)]
    led = AnalysisLedger()
    for u in units:
        led.mark_analyzed(u, {"role": "core", "purpose": "p",
                              "concerns": [f"concern {u.path}"]})
    brief = render_repo_brief(led, units, max_concerns=10)
    assert "y 90 más" in brief           # acotado con nota de overflow


def test_consensus_turn_message_injects_brief():
    from consejo.council_prompts import _consensus_turn_user_message
    from consejo.sages import DEBATE_SAGES
    sage = DEBATE_SAGES[0]
    msg = _consensus_turn_user_message(
        "atasco", Path("."), sage, [], [], 1, 8, 1, 6,
        repo_brief="MAPA: cobertura 5/5",
    )
    assert "repo_analysis" in msg and "MAPA: cobertura 5/5" in msg
    # Sin brief, el bloque no se inyecta (compatibilidad hacia atrás).
    msg2 = _consensus_turn_user_message(
        "atasco", Path("."), sage, [], [], 1, 8, 1, 6)
    assert "repo_analysis" not in msg2


def test_render_repo_map_is_complete_and_groups_by_role(tmp_path: Path):
    for i in range(3):
        _mk(tmp_path, f"f{i}.py", f"c{i}")
    led = asyncio.run(run_analysis_pass(_StubAnalyzer(), tmp_path,
                                        ledger_path=tmp_path / ".consejo" / "led.json"))
    units = enumerate_units(tmp_path)
    md = render_repo_map(led, units)
    assert "3/3 archivos analizados" in md
    for i in range(3):
        assert f"f{i}.py" in md
    assert "## core" in md
