"""Consensus dialogue: round-robin turn-by-turn debate until unanimity or cap.

This module is backend-agnostic — it calls `driver.spawn(...)` on the
SageDriver passed in by the orchestrator, so swapping Claude Code for Codex
requires no change here.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime
from pathlib import Path

from .council_prompts import (
    _consensus_system_prompt,
    _consensus_turn_user_message,
)
from .driver_protocol import SageDriver
from .sages import Sage
from .schemas import TURN_SCHEMA, _VISION_SCHEMA


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
        item = out[titles[target]]
        if "new_title" in amend:
            new_t = amend["new_title"]
            del titles[target]
            item["title"] = new_t
            titles[new_t] = out.index(item)
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

    for r in range(1, max_rounds + 1):
        rounds_used = r
        round_order = list(sages)
        rng.shuffle(round_order)
        failed_in_round = 0
        for i, sage in enumerate(round_order, start=1):
            turn_counter += 1
            user_msg = _consensus_turn_user_message(
                atasco, repo, sage, transcript, plan,
                round_num=r, max_rounds=max_rounds,
                turn_in_round=i, total_sages=len(sages),
            )
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

        if failed_in_round == len(round_order):
            raise RuntimeError(
                f"Catastrophic round failure: all {failed_in_round} sage(s) "
                f"failed in round {r}. Aborting consensus to avoid runaway "
                f"cost. Check the [sage-fail] / [empty-result-retry] messages "
                f"above. Likely causes: orphan claude.exe / node processes "
                f"holding memory, claude CLI version mismatch, or "
                f"--json-schema rejecting the model output (try --cc-model "
                f"sonnet)."
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
