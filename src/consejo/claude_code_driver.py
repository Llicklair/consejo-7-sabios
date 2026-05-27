"""Claude Code driver: spawns `claude -p` subprocesses as the 7 sages.

Uses the user's authenticated Claude Code session (Pro/Max subscription).
No ANTHROPIC_API_KEY required.

Each sage runs as a parallel `claude -p --output-format json` subprocess with:
- Its identity injected via --system-prompt
- Read-only repo access via --add-dir + --allowedTools "Read,Glob,Grep"
- Structured output via --json-schema
- --no-session-persistence to avoid disk clutter

Round model: single round of parallel propose + judge synthesis. The multi-round
sign/amend loop that lives in `orchestrator._real_propose` is API-cost-conscious
and doesn't make sense when each round = 7 subprocesses.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from .sages import ALL_SAGES, SAGES, Sage


PROPOSAL_SCHEMA = {
    "type": "object",
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "minItems": 2,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["title", "rationale", "blast_radius", "category"],
                "properties": {
                    "title": {"type": "string", "maxLength": 200},
                    "rationale": {"type": "string", "maxLength": 3000},
                    "blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                    "category": {
                        "enum": [
                            "code-fix",
                            "future-feature",
                            "strategic-direction",
                            "research-thread",
                        ],
                        "description": (
                            "code-fix: improve existing code · "
                            "future-feature: new capability to build · "
                            "strategic-direction: where the project should go · "
                            "research-thread: open question worth investigating"
                        ),
                    },
                    "files_touched": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 300},
                        "maxItems": 10,
                    },
                    "horizon": {
                        "enum": ["now", "next-quarter", "next-year"],
                        "description": "Time horizon. 'now' = this PR; 'next-quarter' = real work; 'next-year' = vision.",
                    },
                },
            },
        }
    },
}

CRITIQUE_SCHEMA = {
    "type": "object",
    "required": ["endorses", "challenges", "amendments"],
    "properties": {
        "endorses": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["proposal_title", "proposed_by"],
                "properties": {
                    "proposal_title": {"type": "string"},
                    "proposed_by": {"type": "string"},
                    "reason": {"type": "string", "maxLength": 500},
                },
            },
        },
        "challenges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["proposal_title", "proposed_by", "objection"],
                "properties": {
                    "proposal_title": {"type": "string"},
                    "proposed_by": {"type": "string"},
                    "objection": {"type": "string", "maxLength": 1500},
                },
            },
        },
        "amendments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "rationale", "blast_radius"],
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string", "maxLength": 1500},
                    "blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                    "files_touched": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


JUDGE_SCHEMA = {
    "type": "object",
    "required": ["summary", "unanimous", "tasks", "strategic_vision"],
    "properties": {
        "summary": {"type": "string"},
        "unanimous": {"type": "boolean"},
        "tasks": {
            "type": "array",
            "description": "Tactical/code-fix items the user can execute now",
            "items": {
                "type": "object",
                "required": ["title", "rationale", "blast_radius", "supporting_sages"],
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                    "category": {"enum": ["code-fix", "future-feature", "strategic-direction", "research-thread"]},
                    "horizon": {"enum": ["now", "next-quarter", "next-year"]},
                    "supporting_sages": {"type": "array", "items": {"type": "string"}},
                    "files_touched": {"type": "array", "items": {"type": "string"}},
                    "auto_executable": {"type": "boolean"},
                    "priority": {"type": "integer"},
                },
            },
        },
        "strategic_vision": {
            "type": "object",
            "required": ["headline", "where_to_take_it", "future_features", "research_threads"],
            "description": "Forward-looking synthesis: where the project should go, not just what to fix.",
            "properties": {
                "headline": {
                    "type": "string",
                    "description": "1-sentence vision statement.",
                },
                "where_to_take_it": {
                    "type": "string",
                    "description": "2-4 paragraphs on the project's direction over the next year, derived from the council's strategic-direction proposals.",
                },
                "future_features": {
                    "type": "array",
                    "description": "Concrete new capabilities worth building (not bugs to fix).",
                    "items": {
                        "type": "object",
                        "required": ["title", "why", "horizon"],
                        "properties": {
                            "title": {"type": "string"},
                            "why": {"type": "string"},
                            "horizon": {"enum": ["next-quarter", "next-year"]},
                            "supporting_sages": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "research_threads": {
                    "type": "array",
                    "description": "Open questions worth investigating before committing to a path.",
                    "items": {
                        "type": "object",
                        "required": ["question", "why_it_matters"],
                        "properties": {
                            "question": {"type": "string"},
                            "why_it_matters": {"type": "string"},
                        },
                    },
                },
            },
        },
        "unresolved_disagreements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "positions": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


def claude_available() -> bool:
    return shutil.which("claude") is not None


def _sage_system_prompt(sage: Sage) -> str:
    return (
        f"You are the **{sage.name_en}**, one of nine sages convened to review a "
        f"software project IN DEPTH. The other eight sages debate beside you; "
        f"their views often clash with yours — that friction is by design.\n\n"
        f"## Your expertise\n{sage.expertise_en}\n\n"
        f"## Your voice\n{sage.voice_en}\n\n"
        f"## Your foil\nYour natural opposition is the **{sage.foil_en}**. "
        f"You disagree with them by default — never sign on autopilot.\n\n"
        f"## Scope of proposals — read carefully\n\n"
        f"The council is NOT just a linter. Your job covers FOUR distinct kinds "
        f"of proposals, and a strong sage produces a mix:\n\n"
        f"  - **`code-fix`**: improve existing code (the linter axis: refactor, "
        f"tighten, delete dead code, harden inputs, etc.)\n"
        f"  - **`future-feature`**: a new capability worth building from your "
        f"axis — something the project does NOT do today but SHOULD.\n"
        f"  - **`strategic-direction`**: where the project should go over the "
        f"next quarter / year, derived from your axis. Vision, not tasks.\n"
        f"  - **`research-thread`**: an open question that needs investigation "
        f"BEFORE the team picks a path. Articulate the unknown.\n\n"
        f"Each proposal MUST include `category` (one of the four above) and "
        f"`horizon` (`now` = this PR · `next-quarter` = real work · "
        f"`next-year` = vision).\n\n"
        f"## Rules\n"
        f"1. Propose **2-6 items**. A mix of categories is expected; a sage who "
        f"only offers `code-fix` items is doing half the job.\n"
        f"2. **NO BOILERPLATE.** Generic advice without referencing real symbols, "
        f"file paths, or specific aspects of THIS repo will be rejected. "
        f"For `future-feature` and `strategic-direction`: tie the proposal to "
        f"WHAT THIS PROJECT IS and where it sits in the wider landscape "
        f"(competitors, adjacent tools, user persona, distribution model).\n"
        f"3. **Stay in role.** Focus on YOUR axis even when other concerns are "
        f"obvious — other sages will cover them.\n"
        f"4. **Depth over breadth.** A single deep `rationale` (3-6 sentences "
        f"with named evidence) beats five shallow ones.\n"
        f"5. **Output ONLY the JSON object** matching the schema. No prose outside."
    )


def _judge_system_prompt() -> str:
    return (
        "You are the **Judge** of the Council of Sages. The roster has nine "
        "voices: 7 visible sages (Architect, Conservative, Modernizer, "
        "Simplifier, Guardian, Optimizer, Ambassador) and 2 voice-only sages "
        "(Designer, Strategist). Synthesize their work into TWO outputs:\n\n"
        "  1. **`tasks`** — a tactical plan the user can execute. These are "
        "the `code-fix` items mostly, plus `future-feature` items with "
        "`horizon=now`.\n"
        "  2. **`strategic_vision`** — a forward-looking synthesis of where "
        "the project SHOULD go, derived from the council's `strategic-direction`, "
        "`future-feature`, and `research-thread` proposals. This is the "
        "section the user reads to decide what the project IS, not just to fix "
        "bugs.\n\n"
        "Both outputs are required.\n\n"
        "## Inputs\n"
        "- `proposals_by_sage`: each sage's round-1 proposals, each with a "
        "`category` (code-fix | future-feature | strategic-direction | "
        "research-thread) and `horizon` (now | next-quarter | next-year).\n"
        "- `critiques_by_sage` (optional): each sage's round-2 cross-examination "
        "with `endorses`, `challenges` (specific objections), and `amendments`.\n\n"
        "## Your responsibilities\n"
        "1. **Dedupe** proposals that overlap (same idea, different wording). "
        "Aggregate `supporting_sages` when multiple sages converged. When "
        "`critiques.endorses` mentions a proposal, add the endorser too.\n"
        "2. **Sort tactical `tasks`** by blast_radius (SAFE → MEDIUM → RISKY) "
        "and assign 1-based `priority`.\n"
        "3. **Build `strategic_vision`**:\n"
        "   - `headline`: ONE sentence that names where the project is going.\n"
        "   - `where_to_take_it`: 2-4 paragraphs synthesizing the "
        "`strategic-direction` proposals into a coherent direction. Be opinionated. "
        "Name the user persona, the distribution channel, the moat. If sages "
        "disagree on direction, declare a default and note the alternative.\n"
        "   - `future_features`: concrete new capabilities (from `future-feature` "
        "proposals and amendments). Each names what it adds and why.\n"
        "   - `research_threads`: open questions worth investigating BEFORE "
        "the team commits to a path (from `research-thread` proposals).\n"
        "4. **Surface dissents** as `unresolved_disagreements` when a sage "
        "challenges another with a substantive objection. Drop the challenged "
        "proposal OR include it and name both positions. Never paper over "
        "real disagreement to look unanimous.\n"
        "5. **Auto-executable**: SAFE `code-fix` tasks with no unresolved "
        "challenges → `auto_executable=true`. Never mark `future-feature` or "
        "`strategic-direction` items auto-executable; those need human steering.\n\n"
        "## Depth bar\n"
        "Write at the level the user explicitly asked for: STRICTLY DEEP and "
        "RELEVANT TO THIS SPECIFIC PROJECT. A judge whose `strategic_vision` "
        "could apply to any Python repo has failed. Tie every observation to "
        "what THIS project is, who its user is, and where it sits among "
        "alternatives.\n\n"
        "Output ONLY the JSON matching the schema. No prose outside."
    )


def _build_sage_user_message(atasco: str, repo: Path, round_num: int) -> str:
    return (
        f"<atasco>{atasco}</atasco>\n\n"
        f"<round>{round_num}</round>\n\n"
        f"<repo>{repo.resolve()}</repo>\n\n"
        f"Analyze the repository above by reading files with the tools available "
        f"to you (Read, Glob, Grep). Bias your reading toward YOUR axis. Return "
        f"a JSON object with 1-3 proposals, each citing a real file/symbol from "
        f"this specific repo."
    )


def _build_judge_user_message(
    atasco: str,
    proposals_by_sage: dict[str, list[dict]],
    critiques_by_sage: dict[str, dict] | None = None,
) -> str:
    parts = [
        f"<atasco>{atasco}</atasco>",
        "",
        "<proposals_by_sage>",
        json.dumps(proposals_by_sage, indent=2),
        "</proposals_by_sage>",
    ]
    if critiques_by_sage:
        parts += [
            "",
            "<critiques_by_sage>",
            "Each sage cross-examined the others' proposals. For each sage:",
            "  - endorses: proposals they support",
            "  - challenges: proposals they reject (with specific objection)",
            "  - amendments: their own additional proposals after seeing others'",
            json.dumps(critiques_by_sage, indent=2),
            "</critiques_by_sage>",
        ]
    parts += [
        "",
        "Synthesize into a single prioritized plan. Dedupe overlapping proposals, "
        "sort by blast_radius (SAFE first), and aggregate supporting_sages. "
        "When critiques reveal a proposal is rejected by another sage with a "
        "substantive objection, record this as an unresolved_disagreement "
        "instead of forcing a synthesis. The dissent should name both positions.",
    ]
    return "\n".join(parts)


def _sage_critique_system_prompt(sage: Sage) -> str:
    return (
        f"You are the **{sage.name_en}**, one of nine sages convened to review a "
        f"software project. You have already proposed your own items in round 1. "
        f"Now in round 2, you read the proposals submitted by the OTHER eight "
        f"sages and cross-examine them from your axis.\n\n"
        f"## Your expertise\n{sage.expertise_en}\n\n"
        f"## Your voice\n{sage.voice_en}\n\n"
        f"## Your foil\nYour natural opposition is the **{sage.foil_en}**. "
        f"Challenge their proposals especially hard — but only with substance, "
        f"never on autopilot.\n\n"
        f"## Round 2 protocol\n"
        f"For each proposal made by OTHER sages, decide:\n"
        f"- **Endorse:** the proposal is sound from your axis (cite it in `endorses`).\n"
        f"- **Challenge:** the proposal conflicts with your axis (cite it in "
        f"`challenges` with a SPECIFIC objection — never 'I disagree', always "
        f"'this fails because X, and the consequence is Y').\n"
        f"- **Stay neutral:** omit it from both lists.\n\n"
        f"You may also add **amendments** — new proposals you only thought of "
        f"after seeing what others proposed.\n\n"
        f"## Rules\n"
        f"1. **Be substantive.** Vague objections will be filtered.\n"
        f"2. **Stay in role.** Never drift toward consensus that contradicts your axis.\n"
        f"3. **Output ONLY the JSON object** matching the schema. No prose outside."
    )


def _build_critique_user_message(
    atasco: str, repo: Path, round1_by_sage: dict[str, list[dict]],
    my_sage_id: str,
) -> str:
    others = {sid: props for sid, props in round1_by_sage.items() if sid != my_sage_id}
    return (
        f"<atasco>{atasco}</atasco>\n\n"
        f"<round>2</round>\n\n"
        f"<repo>{repo.resolve()}</repo>\n\n"
        f"<other_sages_proposals>\n"
        f"{json.dumps(others, indent=2)}\n"
        f"</other_sages_proposals>\n\n"
        f"Cross-examine the proposals above. You may also read repo files with "
        f"the tools available to verify claims. Output JSON only."
    )


async def _spawn_claude(
    user_msg: str,
    system_prompt: str,
    schema: dict,
    repo: Path,
    model: str,
    allowed_tools: str = "Read,Glob,Grep",
    timeout_s: float = 300.0,
) -> dict:
    """Spawn a `claude -p` subprocess and return the parsed inner JSON.

    `claude -p --output-format json` returns a wrapper like
    `{"type": "result", "result": "<the model text>", ...}`. We parse the
    wrapper, then parse `result` as JSON (constrained by --json-schema).
    """
    if not claude_available():
        raise RuntimeError(
            "`claude` CLI not found on PATH. Install Claude Code to use this mode."
        )

    args = [
        "claude", "-p",
        "--output-format", "json",
        "--system-prompt", system_prompt,
        "--add-dir", str(repo),
        "--model", model,
        "--json-schema", json.dumps(schema),
        "--no-session-persistence",
        "--allowedTools", allowed_tools,
    ]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=user_msg.encode("utf-8")),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"claude CLI timed out after {timeout_s}s")

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"claude CLI failed (exit {proc.returncode}): {err}")

    out = stdout.decode("utf-8", errors="replace")
    try:
        wrapper = json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"claude CLI returned non-JSON: {out[:500]}") from e

    inner_text = wrapper.get("result", "")
    if not inner_text:
        raise RuntimeError(f"claude CLI returned empty result: {wrapper}")

    try:
        return json.loads(inner_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"sage returned non-JSON inner text: {inner_text[:500]}"
        ) from e


async def propose_one_sage(
    sage: Sage, atasco: str, repo: Path, round_num: int, model: str
) -> tuple[Sage, list[dict]]:
    inner = await _spawn_claude(
        user_msg=_build_sage_user_message(atasco, repo, round_num),
        system_prompt=_sage_system_prompt(sage),
        schema=PROPOSAL_SCHEMA,
        repo=repo,
        model=model,
    )
    return sage, inner.get("proposals", [])


async def gather_all_proposals(
    atasco: str, repo: Path, model: str = "sonnet",
    on_complete=None,
) -> dict[str, list[dict]]:
    """Run all 7 sages in parallel.

    `on_complete`: optional async callable `(sage, props_or_none) -> None`
    invoked as each sage finishes. Used by the animator to emit per-sage
    DEBATE events so the long parallel analysis feels alive instead of
    a single blocking wait.
    """
    pending: dict[asyncio.Task, Sage] = {
        asyncio.create_task(propose_one_sage(s, atasco, repo, 1, model)): s
        for s in ALL_SAGES
    }
    by_sage: dict[str, list[dict]] = {}
    while pending:
        done, _ = await asyncio.wait(
            pending.keys(), return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            sage_obj = pending.pop(task)
            try:
                sage, props = await task
                by_sage[sage.id] = props
                if on_complete:
                    await on_complete(sage, props)
            except Exception:
                if on_complete:
                    await on_complete(sage_obj, None)
    return by_sage


async def critique_one_sage(
    sage: Sage, atasco: str, repo: Path,
    round1_by_sage: dict[str, list[dict]],
    model: str,
) -> tuple[Sage, dict]:
    inner = await _spawn_claude(
        user_msg=_build_critique_user_message(atasco, repo, round1_by_sage, sage.id),
        system_prompt=_sage_critique_system_prompt(sage),
        schema=CRITIQUE_SCHEMA,
        repo=repo,
        model=model,
    )
    return sage, inner


async def gather_all_critiques(
    atasco: str, repo: Path,
    round1_by_sage: dict[str, list[dict]],
    model: str = "sonnet",
    on_complete=None,
) -> dict[str, dict]:
    """Round 2: each sage cross-examines the others' proposals. Parallel."""
    pending: dict[asyncio.Task, Sage] = {}
    for s in ALL_SAGES:
        if s.id not in round1_by_sage:
            continue
        pending[asyncio.create_task(
            critique_one_sage(s, atasco, repo, round1_by_sage, model)
        )] = s
    by_sage: dict[str, dict] = {}
    while pending:
        done, _ = await asyncio.wait(
            pending.keys(), return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            sage_obj = pending.pop(task)
            try:
                sage, critique = await task
                by_sage[sage.id] = critique
                if on_complete:
                    await on_complete(sage, critique)
            except Exception:
                if on_complete:
                    await on_complete(sage_obj, None)
    return by_sage


async def judge_synthesis(
    atasco: str,
    proposals_by_sage: dict[str, list[dict]],
    critiques_by_sage: dict[str, dict] | None = None,
    rounds_used: int = 1,
    model: str = "opus",
) -> dict:
    """Run the judge to synthesize all proposals into a prioritized plan +
    a strategic vision. Always uses Opus regardless of `model` — synthesis
    is where depth/coherence pay off the most."""
    inner = await _spawn_claude(
        user_msg=_build_judge_user_message(atasco, proposals_by_sage, critiques_by_sage),
        system_prompt=_judge_system_prompt(),
        schema=JUDGE_SCHEMA,
        repo=Path.cwd(),
        model="opus",
    )
    inner["atasco"] = atasco
    inner["rounds_used"] = rounds_used
    return inner
