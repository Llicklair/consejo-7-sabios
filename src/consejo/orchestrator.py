"""Orquestador del Consejo — driver real para Fase 1.

Reemplaza el `mock_driver` simple del bus por un consejo COMPLETO:
- Escanea el repo
- Construye briefings por expertise (per-sage)
- Lanza N rondas con mecánica sign/reject
- El juez sintetiza el plan
- Empuja eventos al mismo bus que consume el animator

Modos:
- `mock`: no toca la API. Genera respuestas plausibles per-sabio basadas
  en patrones predefinidos. Útil para testear flujo end-to-end sin coste.
- `real`: usa anthropic SDK. Requiere `ANTHROPIC_API_KEY` env. (En curso —
  scaffolding listo, implementación de llamadas pendiente.)

El plan final se devuelve y opcionalmente se vuelca a `consejo-report.md`.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TypedDict

from . import metrics
from .sages import SAGES, Sage
from .states import MAX_DEBATE_ROUNDS, EventBus, State, StateEvent
from .translator import translate_atasco_to_en, translate_plan_to_es

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

SCAN_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".toml",
                   ".yaml", ".yml", ".json"}
SCAN_EXCLUDE_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__",
                     "build", "dist", ".pytest_cache", ".mypy_cache",
                     ".ruff_cache", "assets"}

# Aggregate payload caps. The 20260527-171503 debate lost unanimity to token
# exhaustion, not disagreement — these caps make that failure mode impossible.
# Values are conservative worst-case math (80×4KB ≈ 120KB for scan; 25×1200×~5
# overhead ≈ 150KB per briefing) and should be tightened once a real-mode
# debate is instrumented to measure actual consumption.
MAX_SCAN_PAYLOAD_BYTES = 120_000
MAX_BRIEFING_PAYLOAD_BYTES = 150_000


@dataclass
class Proposal:
    title: str
    rationale: str
    blast_radius: str          # SAFE | MEDIUM | RISKY
    files_touched: list[str]
    proposed_by: str           # sage.name_en
    proposed_round: int = 1


class ProposalDict(TypedDict):
    """Driver-boundary contract for a raw proposal coming back from a sage
    subprocess (see PROPOSAL_SCHEMA in claude_code_driver). Kept here next to
    the Proposal dataclass because the orchestrator owns the domain shape —
    the driver only validates against this contract."""
    title: str
    rationale: str
    blast_radius: str
    files_touched: list[str]
    category: str


@dataclass
class SignatureRecord:
    sage_id: str
    signed: bool
    critique: str = ""
    amendments: list[Proposal] = field(default_factory=list)


# ---------- Project scanning ----------

def scan_project(repo: Path, max_files: int = 80,
                 max_bytes_per_file: int = 4000,
                 max_aggregate_bytes: int = MAX_SCAN_PAYLOAD_BYTES,
                 ) -> list[tuple[str, str]]:
    """Recolecta archivos del repo (Python/TS/MD/configs) limitando tamaño.

    Uses os.walk + in-place dirname pruning so excluded trees (.venv,
    node_modules, .git) are never descended — vs the prior rglob which
    materialized every path in the repo, sorted, and only THEN excluded.

    Stops early when the aggregate content size would exceed
    `max_aggregate_bytes`, which prevents large repos from blowing the
    downstream token budget.
    """
    import os
    files: list[tuple[str, str]] = []
    aggregate_bytes = 0
    capped = False
    for root, dirnames, fnames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d not in SCAN_EXCLUDE_DIRS]
        for fname in sorted(fnames):
            p = Path(root) / fname
            if p.suffix not in SCAN_EXTENSIONS:
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")[:max_bytes_per_file]
                if aggregate_bytes + len(content) > max_aggregate_bytes:
                    capped = True
                    metrics.record("scan", files=len(files),
                                   aggregate_bytes=aggregate_bytes,
                                   capped_by="aggregate")
                    return files
                files.append((str(p.relative_to(repo)), content))
                aggregate_bytes += len(content)
                if len(files) >= max_files:
                    capped = True
                    metrics.record("scan", files=len(files),
                                   aggregate_bytes=aggregate_bytes,
                                   capped_by="max_files")
                    return files
            except Exception:
                continue
    if not capped:
        metrics.record("scan", files=len(files),
                       aggregate_bytes=aggregate_bytes, capped_by=None)
    return files


SAGE_KEYWORDS: dict[str, list[str]] = {
    "arquitecto":    ["class ", "interface", "abstract", "import ", "from ",
                      "module", "boundary", "decoupl", "layer"],
    "conservador":   ["test", "version", "deprecat", "compat", "lock",
                      "pin ", "migration", "fragile", "rollback"],
    "modernizador":  ["async ", "await ", "typing", "TypeAlias", "match ",
                      "@override", "Protocol", "PEP", "type[", "| None"],
    "simplificador": ["TODO", "FIXME", "deprecated", "unused", "helper",
                      "wrapper", "duplicate", "legacy"],
    "guardian":      ["except", "validate", "sanitize", "auth", "permission",
                      "raise ", "security", "injection", "shell=", "eval("],
    "optimizador":   ["cache", "perf", "benchmark", "memo", "lazy",
                      "expensive", " for ", "while ", "O(n", "Image.new"],
    "embajador":     ["argparse", "help=", "README", "error", "log",
                      "ValueError", "docs/", "CLI", "click", "typer"],
    "disenador":     ["color", "style", "format", "layout", "render",
                      "draw", "pixel", "frame", "RGBA", "ImageDraw"],
    "estratega":     ["README", "ARCHITECTURE", "vision", "scope",
                      "roadmap", "user", "stakeholder", "milestone"],
}


def _score_file_for_sage(content: str, keywords: list[str]) -> int:
    lc = content.lower()
    return sum(lc.count(k.lower()) for k in keywords)


def build_briefing(files: list[tuple[str, str]],
                   for_sage: Sage | None = None,
                   max_files_in_briefing: int = 25,
                   max_chars_per_file: int = 1200,
                   max_aggregate_bytes: int = MAX_BRIEFING_PAYLOAD_BYTES,
                   ) -> str:
    """Briefing en EN. Si `for_sage` se da y aparece en SAGE_KEYWORDS,
    los archivos se ranquean por densidad de keywords del eje del sabio
    y se queda con los top N. Sin sage o sin keywords: slice alfabético.

    Stops appending files once the assembled briefing would exceed
    `max_aggregate_bytes`. With 9 sages × 25 files × 1200 chars the
    worst-case payload was ~270KB per debate round; the cap bounds it.
    """
    out: list[str] = ["# Project briefing", ""]
    keywords = SAGE_KEYWORDS.get(for_sage.id) if for_sage else None
    if for_sage and keywords:
        scored = sorted(files,
                        key=lambda fp: _score_file_for_sage(fp[1], keywords),
                        reverse=True)
        selected = scored[:max_files_in_briefing]
        out.append(f"## Filtered for {for_sage.name_en}")
        out.append(f"_{for_sage.expertise_en}_")
        out.append(f"Top {len(selected)} of {len(files)} files, ranked by "
                   f"density of axis keywords ({', '.join(keywords[:5])}, ...).")
        out.append("")
    else:
        selected = files[:max_files_in_briefing]
        out.append(f"## {len(files)} files scanned. Showing top {len(selected)}.")
    aggregate_bytes = sum(len(line) + 1 for line in out)
    files_included = 0
    capped = False
    for path, content in selected:
        chunk = [
            f"\n### `{path}`",
            "```",
            content[:max_chars_per_file],
            "```",
        ]
        chunk_bytes = sum(len(line) + 1 for line in chunk)
        if aggregate_bytes + chunk_bytes > max_aggregate_bytes:
            capped = True
            break
        out.extend(chunk)
        aggregate_bytes += chunk_bytes
        files_included += 1
    briefing = "\n".join(out)
    metrics.record(
        "briefing",
        sage=for_sage.id if for_sage else None,
        files_offered=len(selected),
        files_included=files_included,
        briefing_bytes=len(briefing),
        capped=capped,
    )
    return briefing


def render_sage_prompt(sage: Sage) -> str:
    template = (PROMPTS_DIR / "sage_template.md").read_text(encoding="utf-8")
    return (template
            .replace("{{name_en}}", sage.name_en)
            .replace("{{expertise_en}}", sage.expertise_en)
            .replace("{{voice_en}}", sage.voice_en)
            .replace("{{foil_en}}", sage.foil_en))


def render_judge_prompt() -> str:
    return (PROMPTS_DIR / "judge.md").read_text(encoding="utf-8")


# ---------- Mock responses (patrones predefinidos por sabio) ----------

_MOCK_PROPOSALS_BY_SAGE: dict[str, list[tuple]] = {
    "arquitecto": [
        ("Extract repository layer from auth module",
         "Auth currently mixes handlers, services and DB access; the layered split exposes the flow.",
         "MEDIUM", ["auth.py"]),
        ("Move shared types into a dedicated types package",
         "Type duplicates across services cause drift and silent bugs.",
         "SAFE", ["types/", "services/"]),
    ],
    "conservador": [
        ("Add integration tests before touching production code",
         "We shouldn't refactor without a real net first. The mocked tests aren't catching regressions.",
         "SAFE", ["tests/integration/"]),
        ("Pin major versions of runtime dependencies",
         "Last unpinned upgrade broke 2 services overnight. Stop the bleeding first.",
         "SAFE", ["pyproject.toml"]),
    ],
    "modernizador": [
        ("Migrate from requests to httpx with async support",
         "Other services moved last quarter; this is the last blocker for the unified client.",
         "MEDIUM", ["client.py", "tests/test_client.py"]),
        ("Replace custom retry decorator with tenacity",
         "Battle-tested lib; our implementation has edge cases around timeout cancellation.",
         "SAFE", ["utils/retry.py"]),
    ],
    "simplificador": [
        ("Delete the 4 wrapper functions in helpers/",
         "They each call only the next function in a chain. Inline them; the API public surface shrinks.",
         "SAFE", ["helpers/"]),
        ("Collapse 3-class Serializer hierarchy into one function",
         "Inheritance adds nothing here — only one concrete subclass exists.",
         "MEDIUM", ["serializer.py"]),
    ],
    "guardian": [
        ("Add input validation to /api/upload (size, mime-type, magic bytes)",
         "Endpoint currently accepts any payload; trivial DoS / RCE surface.",
         "SAFE", ["api/upload.py"]),
        ("Audit-log failed auth attempts only (not successes)",
         "Success logs flood disk and bury the actual signal. Failures are what you want to see.",
         "SAFE", ["auth.py"]),
    ],
    "optimizador": [
        ("Cache verify_token in memory (TTL = jwt_exp - 5s)",
         "Hot path. Benchmark shows it's 30% of request CPU time under load.",
         "MEDIUM", ["auth.py"]),
        ("Replace O(n^2) dedup in import job with a set",
         "Job times out above 100k rows; trivial fix and big win.",
         "SAFE", ["jobs/import.py"]),
    ],
    "embajador": [
        ("Define a documented AuthError code catalog",
         "Clients receive cryptic 401s with no context. Real teams have been blocked for hours by this.",
         "SAFE", ["auth.py", "docs/errors.md"]),
        ("Rename get_x_or_default to x_or_else for clarity",
         "Current name is ambiguous and conflicts with stdlib conventions.",
         "SAFE", ["utils/"]),
    ],
}


def _mock_propose(sage: Sage, round_num: int, seed: int,
                  scanned_files: list[tuple[str, str]] | None = None) -> list[Proposal]:
    """Mock proposer: picks 1-2 canned items from _MOCK_PROPOSALS_BY_SAGE.

    If `scanned_files` is provided, the canned `files_touched` placeholders
    (e.g. 'auth.py') are replaced with real files from the actual repo, so
    the mock report at least cites paths that exist.
    """
    rng = random.Random(hash(sage.id) + round_num + seed)
    options = _MOCK_PROPOSALS_BY_SAGE.get(sage.id, [])
    if not options:
        return []
    k = min(len(options), rng.randint(1, 2))
    chosen = rng.sample(options, k)
    real_paths = [fp[0] for fp in scanned_files] if scanned_files else []
    results: list[Proposal] = []
    for (t, r, br, canned_ft) in chosen:
        if real_paths:
            n = max(1, min(len(real_paths), len(canned_ft) or 1))
            ft = rng.sample(real_paths, n)
        else:
            ft = list(canned_ft)
        results.append(Proposal(t, r, br, ft, sage.name_en, round_num))
    return results


def _mock_sign_decision(sage: Sage, round_num: int,
                        all_proposals: list[Proposal],
                        seed: int, total_rounds_planned: int,
                        scanned_files: list[tuple[str, str]] | None = None) -> SignatureRecord:
    """Probabilidad de firmar crece con la ronda. Última ronda fuerza firma."""
    rng = random.Random(hash(sage.id) + round_num * 1000 + seed)
    if round_num >= total_rounds_planned:
        return SignatureRecord(sage_id=sage.id, signed=True)
    p_sign = min(0.92, 0.15 + round_num * 0.20)
    if rng.random() < p_sign:
        return SignatureRecord(sage_id=sage.id, signed=True)
    return SignatureRecord(
        sage_id=sage.id, signed=False,
        critique=(f"From the {sage.name_en}'s axis, the current plan "
                  f"under-weights my concerns ({sage.expertise_en[:60]}...)."),
        amendments=_mock_propose(sage, round_num + 100, seed,
                                 scanned_files=scanned_files)[:1],
    )


def _mock_judge_synthesis(atasco: str, proposals: list[Proposal],
                          signatures: dict[str, SignatureRecord],
                          rounds_used: int) -> dict:
    # Deduplicación naive: agrupar por título exacto
    by_title: dict[str, dict] = {}
    for p in proposals:
        if p.title not in by_title:
            by_title[p.title] = {
                "title": p.title,
                "rationale": p.rationale,
                "blast_radius": p.blast_radius,
                "files_touched": p.files_touched,
                "supporting_sages": [p.proposed_by],
                "auto_executable": p.blast_radius == "SAFE",
            }
        else:
            t = by_title[p.title]
            if p.proposed_by not in t["supporting_sages"]:
                t["supporting_sages"].append(p.proposed_by)

    grouped = list(by_title.values())
    # Ordenar: SAFE primero, luego MEDIUM, luego RISKY
    order = {"SAFE": 0, "MEDIUM": 1, "RISKY": 2}
    grouped.sort(key=lambda t: order.get(t["blast_radius"], 99))
    for i, t in enumerate(grouped, start=1):
        t["priority"] = i

    unanimous = bool(signatures) and all(s.signed for s in signatures.values())

    return {
        "atasco": atasco,
        "summary": (
            f"After {rounds_used} round(s) of debate, the council reached "
            f"{'unanimous ' if unanimous else 'majority '}consensus. The plan "
            f"groups {sum(1 for t in grouped if t['blast_radius']=='SAFE')} SAFE, "
            f"{sum(1 for t in grouped if t['blast_radius']=='MEDIUM')} MEDIUM, "
            f"and {sum(1 for t in grouped if t['blast_radius']=='RISKY')} RISKY tasks."
        ),
        "rounds_used": rounds_used,
        "unanimous": unanimous,
        "tasks": grouped,
        "unresolved_disagreements": [
            {"sage": sid, "critique": rec.critique}
            for sid, rec in signatures.items() if not rec.signed
        ],
    }


# ---------- Real-mode scaffolding (anthropic SDK, hardened) ----------

_REAL_TIMEOUT_S = 120.0
_REAL_MAX_RETRIES = 3
_VALID_BLAST = ("SAFE", "MEDIUM", "RISKY")
_PROPOSAL_TITLE_MAX = 200
_PROPOSAL_RATIONALE_MAX = 2000
_PROPOSAL_FILES_MAX = 10
_PROPOSAL_FILE_PATH_MAX = 300


def _parse_model_json(text: str) -> dict:
    """Robust JSON extractor for model outputs that may wrap in ```json fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("` \n")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last > first:
            return json.loads(text[first:last + 1])
        raise


def _sanitize_proposal_dict(p: dict, sage_name: str, round_num: int) -> Proposal | None:
    """Validate + clamp a model-produced proposal. Returns None if malformed.

    Expected shape is `ProposalDict` (title, rationale, blast_radius,
    files_touched, category). Anything missing or malformed → None.
    """
    if not isinstance(p, dict):
        return None
    title = str(p.get("title", "")).strip()[:_PROPOSAL_TITLE_MAX]
    if not title:
        return None
    rationale = str(p.get("rationale", "")).strip()[:_PROPOSAL_RATIONALE_MAX]
    blast = str(p.get("blast_radius", "")).upper().strip()
    if blast not in _VALID_BLAST:
        blast = "MEDIUM"
    files_raw = p.get("files_touched", []) or []
    if not isinstance(files_raw, list):
        files_raw = []
    files = [
        str(f).strip()[:_PROPOSAL_FILE_PATH_MAX]
        for f in files_raw[:_PROPOSAL_FILES_MAX]
        if isinstance(f, str) and str(f).strip()
    ]
    return Proposal(title, rationale, blast, files, sage_name, round_num)


async def _anthropic_call_with_retry(coro_factory, label: str,
                                      timeout_s: float = _REAL_TIMEOUT_S,
                                      max_retries: int = _REAL_MAX_RETRIES) -> object:
    """Call `coro_factory()` with timeout + exponential backoff on transient errors.

    `coro_factory` is a zero-arg sync callable returning a fresh coroutine each
    attempt (anthropic SDK coroutines can only be awaited once).
    """
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return await asyncio.wait_for(coro_factory(), timeout=timeout_s)
        except asyncio.TimeoutError as e:
            last_err = e
            wait_s = min(2 ** attempt, 16)
        except Exception as e:  # APIError, RateLimitError, transient network
            last_err = e
            name = type(e).__name__
            if name in {"AuthenticationError", "PermissionDeniedError",
                        "BadRequestError", "NotFoundError"}:
                raise
            wait_s = min(2 ** attempt, 16)
        if attempt < max_retries:
            await asyncio.sleep(wait_s)
    raise RuntimeError(
        f"{label}: failed after {max_retries} attempts. last_error={last_err!r}"
    ) from last_err


async def _real_propose(sage: Sage, briefing: str, atasco: str,
                        round_num: int, proposals_so_far: list[Proposal]) -> list[Proposal]:
    """Llamada real a Claude. Requiere ANTHROPIC_API_KEY.

    Hardened: timeout, retry/backoff on transient errors, model output is
    sanitized and length-capped before constructing Proposals."""
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK no instalado. `pip install anthropic`.") from e
    client = AsyncAnthropic()
    system = render_sage_prompt(sage)
    user_msg = (
        f"<atasco>{atasco}</atasco>\n\n"
        f"<round>{round_num}</round>\n\n"
        f"<briefing>\n{briefing}\n</briefing>\n\n"
        f"<proposals>\n{json.dumps([asdict(p) for p in proposals_so_far], indent=2)}\n</proposals>\n\n"
        f"Output JSON only."
    )
    resp = await _anthropic_call_with_retry(
        lambda: client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        ),
        label=f"_real_propose[{sage.id} r{round_num}]",
    )
    try:
        data = _parse_model_json(resp.content[0].text)
    except (json.JSONDecodeError, IndexError):
        return []
    raw = data.get("proposals", data.get("amendments", []))
    if not isinstance(raw, list):
        return []
    out: list[Proposal] = []
    for p in raw:
        sanitized = _sanitize_proposal_dict(p, sage.name_en, round_num)
        if sanitized is not None:
            out.append(sanitized)
    return out


async def _real_judge(atasco: str, proposals: list[Proposal],
                      signatures: dict, rounds_used: int) -> dict:
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK no instalado.") from e
    client = AsyncAnthropic()
    user_msg = (
        f"<atasco>{atasco}</atasco>\n\n"
        f"<rounds_used>{rounds_used}</rounds_used>\n\n"
        f"<proposals>{json.dumps([asdict(p) for p in proposals], indent=2)}</proposals>\n\n"
        f"<signatures>{json.dumps({k: asdict(v) for k, v in signatures.items()}, indent=2)}</signatures>\n\n"
        f"Output JSON only."
    )
    resp = await _anthropic_call_with_retry(
        lambda: client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4000,
            system=render_judge_prompt(),
            messages=[{"role": "user", "content": user_msg}],
        ),
        label="_real_judge",
    )
    try:
        return _parse_model_json(resp.content[0].text)
    except (json.JSONDecodeError, IndexError):
        return {
            "atasco": atasco, "summary": "Judge returned malformed JSON.",
            "rounds_used": rounds_used, "unanimous": False,
            "tasks": [], "unresolved_disagreements": [],
        }


# ---------- Main orchestrator ----------

async def run_council(atasco: str, repo: Path, bus: EventBus,
                      mode: str = "mock",
                      max_rounds: int = MAX_DEBATE_ROUNDS,
                      target_rounds: int = 3,
                      speed: float = 1.0,
                      seed: int | None = None,
                      atasco_lang: str = "es",
                      cc_model: str = "sonnet",
                      consensus_mode: bool = False,
                      consensus_max_rounds: int = 20,
                      consensus_min_rounds: int = 1) -> dict:
    """Ejecuta el consejo completo y empuja eventos al bus para el animator.

    `atasco_lang`: idioma del atasco del usuario ('es' o 'en'). Si es 'es' y
    mode=='real', se traduce a EN antes de pasarlo a los sabios. El plan final
    vuelve a ES para el reporte (con el original EN preservado).
    """
    rng_seed = seed if seed is not None else random.randint(0, 99999)
    n_sages = len(SAGES)

    async def emit(state: State, **kw) -> None:
        await bus.publish(StateEvent(state=state, **kw))

    await emit(State.ENTRANDO)
    await asyncio.sleep(4.0 / speed)
    await emit(State.SENTANDOSE)
    await asyncio.sleep(1.5 / speed)

    # === ANALIZANDO ===
    await emit(State.ANALIZANDO)
    atasco_es_original = atasco

    # claude-code mode: sages run as parallel `claude -p` subprocesses; they
    # do their own repo reading and there is no multi-round sign/amend loop.
    # The ANALIZANDO phase covers the time the subagents work in parallel.
    if mode == "claude-code" and consensus_mode:
        from .claude_code_driver import consensus_dialogue, post_consensus_vision
        from .sages import ALL_SAGES
        await asyncio.sleep(2.0 / speed)

        prev_signed: set[int] = set()

        async def _on_turn(sage, turn_num, round_num, entry, current_plan, current_votes):
            # Build the current vote state across all VISIBLE sages (SAGES).
            # Voice-only sages still speak but do not occupy seats, so they
            # don't appear in the animator. Vote state is REPLACED each turn,
            # not accumulated — a sage that signs then later blocks must lose
            # their seal in the animation.
            currently_signed: list[int] = []
            for i, s in enumerate(SAGES):
                v = current_votes.get(s.id, {}) or {}
                if v.get("signed"):
                    currently_signed.append(i)
            new_signs = sorted(set(currently_signed) - prev_signed)
            prev_signed.clear()
            prev_signed.update(currently_signed)
            speaker_idx = SAGES.index(sage) if sage in SAGES else -1
            await emit(State.DEBATE, round_num=round_num, payload={
                "signed_this_round": new_signs,
                "total_signed": currently_signed,
                "turn": turn_num,
                "speaker": sage.id,
                "speaker_idx": speaker_idx,
                "plan_size": len(current_plan),
                "voice_only": speaker_idx == -1,
            })

        plan = await consensus_dialogue(
            atasco, repo, list(ALL_SAGES),
            max_rounds=consensus_max_rounds,
            min_rounds=consensus_min_rounds,
            model=cc_model,
            on_turn=_on_turn,
        )
        plan["atasco_es"] = atasco_es_original
        plan["atasco_en"] = atasco
        await asyncio.sleep(2.0 / speed)
        await emit(State.JUEZ)
        if plan.get("unanimous"):
            try:
                vision = await post_consensus_vision(
                    atasco, plan.get("tasks") or [],
                    plan.get("transcript") or [],
                    model="opus",
                )
                plan["strategic_vision"] = vision
            except Exception as e:
                print(f"[vision-fail] {str(e)[:400]}", file=sys.stderr)
        await asyncio.sleep(1.0 / speed)
        await emit(State.ACUERDO)
        await asyncio.sleep(2.0 / speed)
        await emit(State.LEVANTANDOSE)
        await asyncio.sleep(1.5 / speed)
        await emit(State.SALIENDO)
        await asyncio.sleep(4.0 / speed)
        await emit(State.REPORTE, payload={"plan": plan})
        return plan

    if mode == "claude-code":
        from .claude_code_driver import (
            gather_all_proposals, gather_all_critiques, judge_synthesis,
        )
        await asyncio.sleep(2.0 / speed)
        cc_rounds = max(1, min(target_rounds, 2))

        # Round 1: parallel proposals
        signed_r1: list[int] = []

        async def _on_propose_done(sage, props) -> None:
            if sage not in SAGES or not props:
                return
            idx = SAGES.index(sage)
            signed_r1.append(idx)
            await emit(State.DEBATE, round_num=1, payload={
                "signed_this_round": [idx],
                "total_signed": signed_r1.copy(),
            })

        proposals_by_sage = await gather_all_proposals(
            atasco, repo, model=cc_model, on_complete=_on_propose_done,
        )
        await asyncio.sleep(1.5 / speed)

        # Round 2: parallel cross-examination
        critiques_by_sage: dict[str, dict] | None = None
        if cc_rounds >= 2 and proposals_by_sage:
            signed_r2: list[int] = []

            async def _on_critique_done(sage, critique) -> None:
                if sage not in SAGES or not critique:
                    return
                idx = SAGES.index(sage)
                signed_r2.append(idx)
                await emit(State.DEBATE, round_num=2, payload={
                    "signed_this_round": [idx],
                    "total_signed": signed_r2.copy(),
                })

            critiques_by_sage = await gather_all_critiques(
                atasco, repo, proposals_by_sage,
                model=cc_model, on_complete=_on_critique_done,
            )
            await asyncio.sleep(1.5 / speed)

        if not proposals_by_sage:
            raise RuntimeError(
                "Todos los sabios fallaron en la ronda 1 (proposals_by_sage vacío). "
                "Causa probable: agotamiento de procesos (claude.exe huérfanos de "
                "sesiones previas). Cierra los procesos zombi y reintenta. "
                "PowerShell: Get-Process claude,node | Stop-Process -Force"
            )

        await emit(State.JUEZ)
        plan = await judge_synthesis(
            atasco, proposals_by_sage,
            critiques_by_sage=critiques_by_sage,
            rounds_used=cc_rounds, model=cc_model,
        )
        plan["atasco_es"] = atasco_es_original
        plan["atasco_en"] = atasco
        await asyncio.sleep(3.0 / speed)
        await emit(State.ACUERDO)
        await asyncio.sleep(2.0 / speed)
        await emit(State.LEVANTANDOSE)
        await asyncio.sleep(1.5 / speed)
        await emit(State.SALIENDO)
        await asyncio.sleep(4.0 / speed)
        await emit(State.REPORTE, payload={"plan": plan})
        return plan

    if atasco_lang == "es":
        atasco_en = await translate_atasco_to_en(atasco, mode=mode)
    else:
        atasco_en = atasco
    files = scan_project(repo)
    briefings = {s.id: build_briefing(files, for_sage=s) for s in SAGES}
    await asyncio.sleep(6.0 / speed)

    # === DEBATE rounds ===
    all_proposals: list[Proposal] = []
    signatures: dict[str, SignatureRecord] = {}
    signed_ids: set[str] = set()
    used_rounds = 0

    for r in range(1, max_rounds + 1):
        used_rounds = r
        new_signs_idx: list[int] = []

        if r == 1:
            # Round 1: cada sabio propone
            for s in SAGES:
                if mode == "mock":
                    props = _mock_propose(s, r, rng_seed, scanned_files=files)
                else:
                    props = await _real_propose(s, briefings[s.id], atasco_en, r, all_proposals)
                all_proposals.extend(props)
        else:
            # Round 2+: cada sabio firma o propone enmiendas
            for s in SAGES:
                if s.id in signed_ids:
                    continue
                if mode == "mock":
                    rec = _mock_sign_decision(s, r, all_proposals, rng_seed,
                                              target_rounds, scanned_files=files)
                else:
                    # Real mode: usa _real_propose para obtener sign+amendments
                    # (scaffolding — simplificado por ahora)
                    props = await _real_propose(s, briefings[s.id], atasco_en, r, all_proposals)
                    rec = SignatureRecord(
                        sage_id=s.id, signed=len(props) == 0,
                        amendments=props,
                    )
                signatures[s.id] = rec
                if rec.signed:
                    signed_ids.add(s.id)
                    new_signs_idx.append(SAGES.index(s))
                else:
                    all_proposals.extend(rec.amendments)

        await emit(
            State.DEBATE,
            round_num=r,
            payload={
                "signed_this_round": new_signs_idx,
                "total_signed": [i for i, s in enumerate(SAGES) if s.id in signed_ids],
            },
        )
        await asyncio.sleep(3.5 / speed)

        # Convergencia: todos firmados
        if len(signed_ids) == n_sages:
            break

    # === JUEZ ===
    await emit(State.JUEZ)
    if mode == "mock":
        plan_en = _mock_judge_synthesis(atasco_en, all_proposals, signatures, used_rounds)
    else:
        plan_en = await _real_judge(atasco_en, all_proposals, signatures, used_rounds)
    # Traduce campos visibles a ES preservando el plan original (EN) para auditar
    plan = await translate_plan_to_es(plan_en, mode=mode)
    plan["atasco_es"] = atasco_es_original
    plan["atasco_en"] = atasco_en
    await asyncio.sleep(3.0 / speed)

    # === ACUERDO → LEVANTANDOSE → SALIENDO → REPORTE ===
    await emit(State.ACUERDO)
    await asyncio.sleep(2.0 / speed)
    await emit(State.LEVANTANDOSE)
    await asyncio.sleep(1.5 / speed)
    await emit(State.SALIENDO)
    await asyncio.sleep(4.0 / speed)
    await emit(State.REPORTE, payload={"plan": plan})

    return plan


def render_plan_markdown(plan: dict, execution: dict | None = None) -> str:
    """Reporte bilingüe: resumen ES (lo que lee el usuario) + transcripción EN
    (auditabilidad — lo que dijeron de verdad los sabios). Si `execution` se
    pasa (resultado de executor.execute_safe_tasks), incluye la sección
    de tareas aplicadas con sus commits."""
    atasco_es = plan.get("atasco_es", plan.get("atasco", "unknown"))
    atasco_en = plan.get("atasco_en", "")
    lines: list[str] = [
        "# Consejo de los 7 Sabios — Reporte",
        "",
        f"**Atasco (ES):** {atasco_es}",
    ]
    if atasco_en and atasco_en != atasco_es:
        lines.append(f"**Atasco (EN):** {atasco_en}")
    lines += [
        f"**Rondas usadas:** {plan['rounds_used']}",
        f"**Unánime:** {'sí' if plan['unanimous'] else 'no'}",
        "",
        "## Resumen ejecutivo",
        "",
        plan["summary"],
        "",
        "## Plan priorizado",
        "",
        "| # | Tarea | Sabios | Discrepó (resuelto) | Blast | Auto |",
        "|---|-------|--------|---------------------|-------|------|",
    ]
    has_any_dissent = False
    for t in plan["tasks"]:
        sages = ", ".join(t.get("supporting_sages", []))
        dissent = t.get("dissented_at_some_point") or []
        dissent_str = ", ".join(dissent) if dissent else "—"
        if dissent:
            has_any_dissent = True
        auto = "✅" if t.get("auto_executable") else "⛔"
        lines.append(
            f"| {t['priority']} | **{t['title']}** | {sages} | "
            f"{dissent_str} | `{t['blast_radius']}` | {auto} |"
        )
    if has_any_dissent:
        lines += ["",
                  "_Columna **Discrepó**: sabios que bloquearon el item en "
                  "alguna ronda y luego firmaron tras enmiendas — la textura "
                  "del debate aunque el resultado final sea unánime._"]

    # Sección de ejecución (si modo auto se ejecutó)
    if execution:
        lines += ["", "## Tareas aplicadas (modo auto)", ""]
        if execution["commits"]:
            lines.append(f"Rama creada: `{execution['branch_name']}` "
                         f"(rama origen: `{execution['original_branch']}`)")
            if execution.get("snapshot_hash"):
                lines.append(f"\nSnapshot pre-consejo: `{execution['snapshot_hash']}`")
            lines.append("")
            lines.append("| # | Tarea | Sabio | Commit | Blast |")
            lines.append("|---|-------|-------|--------|-------|")
            for i, c in enumerate(execution["commits"], 1):
                lines.append(f"| {i} | {c['task_title']} | {c['sage']} | "
                             f"`{c['hash']}` | `{c['blast_radius']}` |")
            lines.append("")
            lines.append(f"Total: {len(execution['commits'])} commits aplicados. "
                         f"`git merge {execution['branch_name']}` para integrar.")
        else:
            lines.append(execution.get("note", "Sin tareas SAFE para auto-ejecutar."))
        if execution.get("skipped"):
            lines.append("")
            lines.append(f"**{len(execution['skipped'])} tareas pendientes** "
                         "(MEDIUM/RISKY) — revisión manual requerida en el reporte arriba.")

    # Visión estratégica (forward-looking)
    vision = plan.get("strategic_vision")
    if isinstance(vision, dict) and vision:
        lines += ["", "## 🔭 Visión estratégica", ""]
        if vision.get("headline"):
            lines.append(f"**{vision['headline']}**")
            lines.append("")
        if vision.get("where_to_take_it"):
            lines.append("### Hacia dónde encauzarlo")
            lines.append("")
            lines.append(vision["where_to_take_it"])
            lines.append("")
        future_features = vision.get("future_features") or []
        if future_features:
            lines.append("### Features futuros propuestos")
            lines.append("")
            lines.append("| Horizonte | Feature | Por qué | Sabios |")
            lines.append("|-----------|---------|---------|--------|")
            for ff in future_features:
                horizon = ff.get("horizon", "next-quarter")
                title = ff.get("title", "?")
                why = ff.get("why", "")
                sages = ", ".join(ff.get("supporting_sages") or [])
                lines.append(f"| `{horizon}` | **{title}** | {why} | {sages} |")
            lines.append("")
        threads = vision.get("research_threads") or []
        if threads:
            lines.append("### Hilos de investigación abiertos")
            lines.append("")
            for t in threads:
                q = t.get("question", "?")
                why = t.get("why_it_matters", "")
                lines.append(f"- **{q}** — {why}")
            lines.append("")

    # Disensos
    if plan.get("unresolved_disagreements"):
        lines += ["", "## Disensos no resueltos", ""]
        for d in plan["unresolved_disagreements"]:
            who = d.get("sage", d.get("topic", "?"))
            what = d.get("critique", d.get("judge_call", ""))
            if isinstance(d.get("positions"), list):
                positions = " · ".join(d["positions"])
                lines.append(f"- **{who}**: {positions}")
            else:
                lines.append(f"- **{who}**: {what}")

    # Transcripción original en EN (auditabilidad)
    original_en = plan.get("_original_en")
    if original_en:
        lines += [
            "",
            "---",
            "",
            "## Transcripción original (EN)",
            "",
            "_Lo que los sabios dijeron literalmente, antes de la traducción._",
            "",
            "### Executive summary",
            "",
            original_en.get("summary", ""),
            "",
            "### Original tasks",
            "",
            "| # | Title | Supporting | Blast | Auto |",
            "|---|-------|------------|-------|------|",
        ]
        for t in original_en.get("tasks", []):
            sages = ", ".join(t.get("supporting_sages", []))
            auto = "✅" if t.get("auto_executable") else "⛔"
            lines.append(
                f"| {t['priority']} | **{t['title']}** | {sages} | "
                f"`{t['blast_radius']}` | {auto} |"
            )
    return "\n".join(lines)
