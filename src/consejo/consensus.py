"""Consensus dialogue: round-robin turn-by-turn debate until unanimity or cap.

This module is backend-agnostic — it calls `driver.spawn(...)` on the
SageDriver passed in by the orchestrator, so swapping Claude Code for Codex
requires no change here.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from .council_prompts import (
    _consensus_system_prompt,
    _consensus_turn_user_message,
    _juez_framing_system_prompt,
    _juez_framing_user_message,
    render_framing,
)
from .driver_protocol import SageDriver
from .repo_skeleton import render_coverage
from .sages import Sage, by_id
from .schemas import (
    FRAMING_SCHEMA,
    TURN_SCHEMA,
    VERIFICATION_SCHEMA,
    _VISION_SCHEMA,
)


def _apply_plan_diff(plan: list[dict], diff: dict) -> list[dict]:
    """Return a new plan with the diff applied. Idempotent on duplicates."""
    if not diff:
        return plan
    out = [dict(p) for p in plan]
    titles = {p.get("title"): i for i, p in enumerate(out)}
    for new_item in diff.get("add", []) or []:
        t = new_item.get("title")
        if t and t not in titles:
            out.append(new_item)
            titles[t] = len(out) - 1
    for amend in diff.get("amend", []) or []:
        target = amend.get("target_title")
        if target not in titles:
            continue
        idx = titles[target]
        item = out[idx]
        if "new_title" in amend:
            new_t = amend["new_title"]
            del titles[target]
            item["title"] = new_t
            # Usa el índice conocido, NO out.index(item): list.index compara por
            # igualdad, así que con dos ítems de igual contenido devolvía el
            # índice equivocado y corrompía el mapa de títulos.
            titles[new_t] = idx
        if "new_rationale" in amend:
            item["rationale"] = amend["new_rationale"]
        if "new_blast_radius" in amend:
            item["blast_radius"] = amend["new_blast_radius"]
        if "new_category" in amend:
            item["category"] = amend["new_category"]
        if "new_horizon" in amend:
            item["horizon"] = amend["new_horizon"]
        if "new_files_touched" in amend:
            item["files_touched"] = list(amend["new_files_touched"])
    for rm in diff.get("remove", []) or []:
        if rm in titles:
            out = [p for p in out if p.get("title") != rm]
            titles = {p.get("title"): i for i, p in enumerate(out)}
    return out


def _is_unanimous(plan: list[dict], votes: dict[str, dict], sage_ids: list[str]) -> bool:
    if not plan:
        return False
    for sid in sage_ids:
        v = votes.get(sid)
        if not v or not v.get("signed"):
            return False
        if v.get("objections"):
            return False
    return True


async def consensus_dialogue(
    driver: SageDriver,
    atasco: str,
    repo: Path,
    sages: list[Sage],
    max_rounds: int = 20,
    min_rounds: int = 1,
    model: str = "sonnet",
    on_turn=None,
    repo_brief: str = "",
    zones: list | None = None,
) -> dict:
    """Round-robin turn-by-turn dialogue until all sages sign the same plan.

    Each turn carries the full transcript + current plan. A round = one turn
    per sage in the provided `sages` list order. The Juez is NOT included here
    — pass DEBATE_SAGES (the six debaters) so the judge only synthesizes at
    the end. Stops at unanimity (only after `min_rounds`) or `max_rounds`.
    `min_rounds` forces the council to keep iterating even if everyone signs
    early — useful when premature convergence hides insufficiently-explored axes.

    Returns a dict shaped like `judge_synthesis`'s output so the existing
    report writer works unchanged.
    """
    transcript: list[dict] = []
    plan: list[dict] = []
    votes: dict[str, dict] = {}
    sage_ids = [s.id for s in sages]
    turn_counter = 0
    rounds_used = 0
    converged_at_round: int | None = None

    rng = random.Random()
    contributed: set[str] = set()  # sage ids that have added or amended at least once
    # title -> set of sage_ids that ever blocked it during the debate. Survives
    # later signing — a sage that blocked X in r1 and signed in r3 still leaves
    # a fingerprint in dissent_history[X], so the final report can show debate
    # texture even when the headline says "unánime".
    dissent_history: dict[str, set[str]] = {}

    # Live debate log: append each turn as JSONL so the run can be followed in
    # real time from another terminal — e.g. `Get-Content <file> -Wait` (Win)
    # or `tail -f <file>`. The full transcript still goes to the final report;
    # this is just a live tap. Write failures never interrupt the debate.
    live_log: Path | None = (
        Path.cwd() / f"consejo-debate-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    )
    try:
        with live_log.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(
                {"kind": "header", "atasco": atasco,
                 "sages": sage_ids, "max_rounds": max_rounds,
                 "min_rounds": min_rounds},
                ensure_ascii=False,
            ) + "\n")
        print(f"[debate-log] {live_log}", file=sys.stderr)
    except OSError:
        live_log = None

    # === Framing turn (Strategist) — seed the product/user/strategic lens BEFORE
    # the six engineers default to tech-debt cleanup. The Juez normally only
    # synthesizes at the END, too late to widen the debate; this early turn
    # injects the angles an all-engineer council misses. Failure degrades to no
    # framing — it never blocks the debate. One extra spawn per run. ===
    framing = ""
    try:
        framing_out = await driver.spawn(
            user_msg=_juez_framing_user_message(atasco, repo, repo_brief),
            system_prompt=_juez_framing_system_prompt(),
            schema=FRAMING_SCHEMA,
            repo=repo,
            model=model,
            allowed_tools="Read,Glob,Grep",
            timeout_s=300.0,
        )
        framing = render_framing(framing_out)
        if framing and live_log:
            try:
                with live_log.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(
                        {"kind": "framing", "sage_id": "juez", "framing": framing},
                        ensure_ascii=False) + "\n")
            except OSError:
                pass
        print(f"[framing] encuadre del juez listo ({len(framing)} chars)",
              file=sys.stderr)
    except Exception as e:
        print(f"[framing-fail] {str(e)[:300]} — debate sigue sin encuadre",
              file=sys.stderr)

    for r in range(1, max_rounds + 1):
        rounds_used = r
        round_order = list(sages)
        rng.shuffle(round_order)
        failed_in_round = 0
        round_output_tokens = 0
        round_secs = 0.0
        for i, sage in enumerate(round_order, start=1):
            turn_counter += 1
            user_msg = _consensus_turn_user_message(
                atasco, repo, sage, transcript, plan,
                round_num=r, max_rounds=max_rounds,
                turn_in_round=i, total_sages=len(sages),
                repo_brief=repo_brief,
                framing=framing,
                coverage=render_coverage(plan, zones) if zones else "",
            )
            _t0 = time.monotonic()
            try:
                turn_out = await driver.spawn(
                    user_msg=user_msg,
                    system_prompt=_consensus_system_prompt(sage),
                    schema=TURN_SCHEMA,
                    repo=repo,
                    model=model,
                    allowed_tools="Read,Glob,Grep",
                    timeout_s=420.0,
                )
            except Exception as e:
                print(
                    f"[sage-fail] {sage.id} turn {turn_counter} (r{r}): "
                    f"{str(e)[:400]}",
                    file=sys.stderr,
                )
                failed_in_round += 1
                turn_out = {
                    "message": "(turn failed — abstaining this round)",
                    "plan_diff": {},
                    "vote": {
                        "signed": False,
                        "objections": [],
                        "reasoning": "turn failed",
                    },
                }
            turn_secs = round(time.monotonic() - _t0, 2)
            _meta = turn_out.get("_meta") or {}
            round_secs += turn_secs
            if _meta.get("output_tokens"):
                round_output_tokens += _meta["output_tokens"]

            diff = turn_out.get("plan_diff") or {}
            if (diff.get("add") or diff.get("amend")):
                contributed.add(sage.id)
            plan = _apply_plan_diff(plan, diff)
            vote = turn_out.get("vote") or {}
            # Server-side enforcement of friction discipline. The model knows
            # the rule from the system prompt; this guarantees it isn't bypassed.
            if r == 1 and vote.get("signed"):
                vote = {**vote, "signed": False,
                        "reasoning": "(blocked: round 1 sign suppressed — propose or amend first)"}
            elif vote.get("signed") and sage.id not in contributed:
                vote = {**vote, "signed": False,
                        "reasoning": "(blocked: must add or amend at least one item before signing)"}
            votes[sage.id] = vote
            for obj_title in (vote.get("objections") or []):
                dissent_history.setdefault(obj_title, set()).add(sage.id)
            entry = {
                "turn": turn_counter,
                "round": r,
                "sage_id": sage.id,
                "message": turn_out.get("message", ""),
                "vote": vote,
                "metrics": {
                    "duration_s": turn_secs,
                    "input_tokens": _meta.get("input_tokens"),
                    "output_tokens": _meta.get("output_tokens"),
                    "cost_usd": _meta.get("cost_usd"),
                },
            }
            transcript.append(entry)
            if live_log is not None:
                try:
                    with live_log.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except OSError:
                    pass
            print(
                f"[turn {turn_counter:>3} · r{r} · {sage.id:>14}] "
                f"{'SIGN' if vote.get('signed') else 'BLOCK'} "
                f"plan={len(plan)} obj={len(vote.get('objections') or [])}",
                file=sys.stderr,
            )
            if on_turn:
                await on_turn(sage, turn_counter, r, entry, plan, votes)

        # --- fin de ronda: observabilidad + quorum ---
        succeeded_in_round = len(round_order) - failed_in_round
        quorum = len(sage_ids) // 2 + 1  # mayoría estricta
        if live_log is not None:
            try:
                with live_log.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({
                        "kind": "round_summary",
                        "round": r,
                        "succeeded": succeeded_in_round,
                        "failed": failed_in_round,
                        "total": len(round_order),
                        "quorum": quorum,
                        "output_tokens": round_output_tokens,
                        "duration_s": round(round_secs, 1),
                    }, ensure_ascii=False) + "\n")
            except OSError:
                pass
        print(
            f"[round {r}] succeeded={succeeded_in_round}/{len(round_order)} "
            f"failed={failed_in_round} quorum={quorum}",
            file=sys.stderr,
        )
        # Quorum: si la MAYORÍA de sabios falló, el consenso de esta ronda sería
        # de una minoría. Abortar en vez de (a) etiquetar como unánime un
        # acuerdo degradado o (b) quemar coste hasta max_rounds sin posibilidad
        # real de converger. Subsume el caso "todos fallaron" (succeeded=0).
        if succeeded_in_round < quorum:
            raise RuntimeError(
                f"Quorum no alcanzado en la ronda {r}: solo "
                f"{succeeded_in_round}/{len(round_order)} sabios respondieron "
                f"(quorum={quorum}). Abortando para no construir consenso sobre "
                f"una minoría. Causas probables: procesos claude/node huérfanos "
                f"agotando memoria, versión del CLI, o timeouts. Revisa "
                f"[sage-fail]/[empty-result-retry] arriba."
            )

        if r >= min_rounds and _is_unanimous(plan, votes, sage_ids):
            converged_at_round = r
            break

    unanimous = converged_at_round is not None

    tasks = []
    for prio, p in enumerate(plan, start=1):
        title = p.get("title", "")
        signers = [
            sid for sid in sage_ids
            if votes.get(sid, {}).get("signed")
            and title not in (votes.get(sid, {}).get("objections") or [])
        ]
        tasks.append({
            "priority": prio,
            "title": title,
            "rationale": p.get("rationale", ""),
            "blast_radius": p.get("blast_radius", "MEDIUM"),
            "category": p.get("category", "code-fix"),
            "horizon": p.get("horizon", "now"),
            "files_touched": p.get("files_touched", []),
            "supporting_sages": signers,
            "dissented_at_some_point": sorted(dissent_history.get(title, set())),
            "auto_executable": False,
        })

    unresolved = []
    for sid in sage_ids:
        v = votes.get(sid, {}) or {}
        for obj_title in (v.get("objections") or []):
            unresolved.append({
                "title": obj_title,
                "objecting_sage": sid,
                "reasoning": v.get("reasoning", ""),
            })

    summary = (
        f"Consenso unánime alcanzado en {converged_at_round} ronda(s) "
        f"({turn_counter} turnos)."
        if unanimous else
        f"Sin unanimidad tras {rounds_used} ronda(s) ({turn_counter} turnos). "
        f"{len(unresolved)} objeción(es) abierta(s)."
    )

    return {
        "summary": summary,
        "unanimous": unanimous,
        "tasks": tasks,
        "strategic_vision": {
            "headline": "(consensus mode — strategic vision computed separately)",
            "where_to_take_it": "",
            "future_features": [],
            "research_threads": [],
        },
        "unresolved_disagreements": unresolved,
        "transcript": transcript,
        "atasco": atasco,
        "rounds_used": rounds_used,
        "turns_used": turn_counter,
    }


async def post_consensus_vision(
    driver: SageDriver,
    atasco: str,
    plan_tasks: list[dict],
    transcript: list[dict],
    model: str = "opus",
) -> dict:
    """After the council reaches consensus on tactical tasks, generate the
    strategic_vision separately. The vision is the synthesis layer the user
    reads to decide what the project IS, not just to fix today.

    Returns a dict shaped like the `strategic_vision` field of the classic
    judge output.
    """
    # Compress the transcript to keep the prompt focused on signal: the final
    # vote, the items each sage championed, and any unresolved tension.
    transcript_compact = [
        {
            "turn": e["turn"],
            "sage": e["sage_id"],
            "signed": bool((e.get("vote") or {}).get("signed")),
            "msg": (e.get("message") or "")[:400],
        }
        for e in transcript[-30:]  # last 30 turns carry the convergence story
    ]
    sys_prompt = (
        "You are the Judge of the Council. The six sages have reached "
        "consensus on the TACTICAL plan. Your job is to read their debate and "
        "name where the project SHOULD GO — the strategic vision that the "
        "tactical tasks serve. This is what the user reads to decide what the "
        "project IS, not just to fix today's bugs.\n\n"
        "## Required fields\n"
        "- headline: ONE sentence naming the direction.\n"
        "- where_to_take_it: 2-4 paragraphs synthesizing the debate into a "
        "coherent direction. Name the user persona, the distribution channel, "
        "the moat. Be opinionated. If the debate revealed tension between "
        "axes (e.g., Conservative vs Modernizer), declare a default and "
        "explain why.\n"
        "- future_features: 2-5 concrete capabilities to build next-quarter "
        "or next-year, drawn from the debate.\n"
        "- research_threads: 1-3 open questions worth investigating BEFORE "
        "the team commits to a direction.\n\n"
        "## Depth bar\n"
        "STRICTLY DEEP and SPECIFIC to THIS project. A vision that could "
        "apply to any Python repo has failed. Cite the council's own words "
        "and the project's actual context.\n\n"
        "## Output\n"
        "Emit ONLY the JSON object. No prose, no markdown fences."
    )
    user_msg = (
        f"<atasco>{atasco}</atasco>\n\n"
        f"<agreed_plan>\n{json.dumps(plan_tasks, indent=2)}\n</agreed_plan>\n\n"
        f"<debate_transcript_tail>\n"
        f"{json.dumps(transcript_compact, indent=2)}\n"
        f"</debate_transcript_tail>\n\n"
        f"## Required output shape\n"
        f"```json\n{json.dumps(_VISION_SCHEMA, indent=2)}\n```\n\n"
        f"Output ONLY the JSON object. No prose outside, no markdown fences."
    )
    inner = await driver.spawn(
        user_msg=user_msg,
        system_prompt=sys_prompt,
        schema=_VISION_SCHEMA,
        repo=Path.cwd(),
        model=model,
        allowed_tools="",
        # La visión solo redacta (sin tools); 120s sobra. El default de 300s
        # colgaba el pipeline 5 min cuando la llamada se atascaba.
        timeout_s=120.0,
    )
    return inner


def _verifier_system_prompt() -> str:
    return (
        "You are the **Verifier** of the Council of Sages — an adversarial "
        "fact-checker. The sages have agreed on a plan, but a turn-by-turn "
        "debate manufactures confident-sounding numbers that were NEVER "
        "measured ('5 of 30 sites', '10-50x slower', 'wrapped in bare "
        "except'). Your ONLY job is to check the factual and quantitative "
        "claims in ONE task's rationale against the ACTUAL repository, and "
        "report what the code really says.\n\n"
        "## How you work\n"
        "- You have Read, Glob and Grep with NO call budget. Use as many "
        "calls as you need — checking '5 of 30 sites' means grepping ALL the "
        "sites and ACTUALLY counting, not eyeballing two files.\n"
        "- Extract every checkable claim from the rationale: counts, ratios, "
        "existence claims ('bare except swallows errors'), and verify each "
        "path in files_touched actually exists.\n"
        "- For each claim, run the command that confirms or refutes it and "
        "record (a) the command you ran and (b) what you OBSERVED — the real "
        "count, the matching lines, or the absence.\n\n"
        "## Discipline — default to skepticism\n"
        "- `verified` ONLY when you reproduced it against the code.\n"
        "- **A raw match count is NOT the claim.** `grep -c '.all()'` may "
        "return 153, but if the claim is 'unbounded queries' you must OPEN the "
        "matches and count only those that actually exhibit the property — e.g. "
        "a `.all()` with NO `.limit()`/`.offset()` nearby. Counting text "
        "occurrences instead of the real property is the #1 way a number lies "
        "(a `.scalars().all()` two lines under a `.limit(50)` is bounded). Use "
        "`-B/-A` context and read; never report a grep tally as the fact.\n"
        "- `refuted` when the real value differs materially (the claim said "
        "'5 of 30' and you counted 92 — that is refuted, not weakened).\n"
        "- `unverifiable` when the tools cannot measure it (a perf ratio with "
        "no benchmark, a subjective judgement). `unverifiable` is NOT a pass.\n"
        "- **Mark `is_core: true`** on the claim(s) that ARE the task's central "
        "justification — the reason the task exists. Peripheral details are "
        "`is_core: false`. Be honest about which is which.\n"
        "- Overall `verdict`: `solid` only if every material claim verified; "
        "`refuted` if a CORE claim is false (the task's premise collapses — "
        "even if peripheral claims hold); `weakened` ONLY when the core holds "
        "but some peripheral claims are unverifiable or minor mismatches. Do "
        "NOT soften a refuted core premise to `weakened` — if the reason the "
        "task exists is false, the verdict is `refuted`.\n"
        "- You do NOT fix code, propose changes, or re-debate. You only check. "
        "Be terse and numeric.\n\n"
        "Output ONLY the JSON object matching the schema. No prose outside."
    )


def _verifier_user_message(repo: Path, task: dict) -> str:
    subset = {
        k: task.get(k)
        for k in ("title", "rationale", "blast_radius", "files_touched")
    }
    return (
        f"<repo>{repo.resolve()}</repo>\n\n"
        f"<task_under_review>\n"
        f"{json.dumps(subset, indent=2, ensure_ascii=False)}\n"
        f"</task_under_review>\n\n"
        f"Check every factual/quantitative claim in the rationale above "
        f"against the real repository, and confirm each path in files_touched "
        f"exists. Use as many Read/Glob/Grep calls as you need — there is no "
        f"budget here; accuracy is the whole point.\n\n"
        f"## Required output shape\n"
        f"```json\n{json.dumps(VERIFICATION_SCHEMA, indent=2)}\n```\n\n"
        f"Output ONLY the JSON object. No prose outside, no markdown fences."
    )


def _enforce_core_refutation(ver: dict) -> dict:
    """Deterministic guard: if any claim the verifier marked ``is_core`` was
    refuted, the overall task verdict is ``refuted`` — no matter what the model
    rolled up. The model supplies the judgement (which claim is core); the code
    enforces the consequence, the same split used for round-1 sign suppression.

    Closes the calibration miss seen 2026-05-30: a task whose central premise
    was refuted got rolled up to ``weakened`` and so was never demoted out of
    the actionable plan. Degrades safely — if no claim carries ``is_core`` the
    model's own verdict stands.
    """
    if not isinstance(ver, dict):
        return ver
    claims = ver.get("claims") or []
    core_refuted = any(
        isinstance(c, dict) and c.get("is_core") and c.get("verdict") == "refuted"
        for c in claims
    )
    if core_refuted and ver.get("verdict") != "refuted":
        note = ver.get("note") or ""
        ver = {
            **ver,
            "verdict": "refuted",
            "note": ("[auto: premisa central refutada → tarea refutada] " + note).strip(),
        }
    return ver


async def verify_plan_claims(
    driver: SageDriver,
    repo: Path,
    plan: dict,
    model: str = "sonnet",
    max_concurrency: int = 3,
    on_task=None,
) -> dict:
    """Adversarially fact-check every task's claims against the real repo.

    For each task in ``plan['tasks']`` a Verifier subagent re-runs the
    quantitative/factual claims in the rationale with an UNCAPPED tool budget
    (the debate's tight cap is exactly what forces sages to assert unmeasured
    numbers). Each task gains a ``verification`` dict; the plan gains a
    ``verification_summary``. The report demotes ``refuted`` tasks out of the
    actionable plan instead of presenting fabricated claims as fact.

    Mutates ``plan`` in place and returns it. Never raises: a verifier that
    fails leaves its task tagged ``unverifiable`` so a single bad subprocess
    can't sink the whole report.

    Concurrency is bounded by a LOCAL semaphore (default 3) to honour the same
    memory ceiling as ``_SPAWN_SEM`` in the claude-code driver, without coupling
    this backend-agnostic module to that concrete backend.
    """
    tasks = plan.get("tasks") or []
    if not tasks:
        plan["verification_summary"] = {
            "solid": 0, "weakened": 0, "refuted": 0, "total": 0,
        }
        return plan

    sem = asyncio.Semaphore(max_concurrency)

    async def _verify_one(task: dict) -> dict:
        async with sem:
            try:
                out = await driver.spawn(
                    user_msg=_verifier_user_message(repo, task),
                    system_prompt=_verifier_system_prompt(),
                    schema=VERIFICATION_SCHEMA,
                    repo=repo,
                    model=model,
                    allowed_tools="Read,Glob,Grep",
                    timeout_s=420.0,
                )
            except Exception as e:
                print(
                    f"[verify-fail] {str(task.get('title', '?'))[:60]}: "
                    f"{type(e).__name__}: {str(e)[:300]}",
                    file=sys.stderr,
                )
                return {
                    "verdict": "unverifiable",
                    "claims": [],
                    "files_exist": [],
                    "note": (
                        f"verification failed ({type(e).__name__}); claims "
                        f"left unchecked — treat the rationale as unconfirmed."
                    ),
                }
            if isinstance(out, dict):
                out.pop("_meta", None)
            return _enforce_core_refutation(out)

    results = await asyncio.gather(*[_verify_one(t) for t in tasks])

    counts = {"solid": 0, "weakened": 0, "refuted": 0}
    for task, ver in zip(tasks, results):
        task["verification"] = ver
        v = (ver or {}).get("verdict")
        if v in counts:
            counts[v] += 1
        print(
            f"[verify] {str(task.get('title', '?'))[:50]:>50} -> "
            f"{v or 'none'}",
            file=sys.stderr,
        )
        if on_task:
            await on_task(task, ver)

    plan["verification_summary"] = {**counts, "total": len(tasks)}
    print(
        f"[verify] summary: solid={counts['solid']} "
        f"weakened={counts['weakened']} refuted={counts['refuted']} "
        f"of {len(tasks)}",
        file=sys.stderr,
    )
    return plan
