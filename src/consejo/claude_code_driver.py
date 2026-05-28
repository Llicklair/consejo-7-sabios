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
import os
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from . import metrics
from .sages import ALL_SAGES, SAGES, Sage


def _json_schema_enabled() -> bool:
    """Whether to pass `--json-schema` to the claude CLI.

    Default ON since claude 2.1.85 supports it natively. Set
    `CONSEJO_USE_JSON_SCHEMA=0` to disable and fall back to free-form
    output parsed by `_extract_json_object` (the Conservador's
    belt-and-suspenders path — keep until truncation rate is measured
    in a real-mode debate).
    """
    return os.environ.get("CONSEJO_USE_JSON_SCHEMA", "1") != "0"


def _build_claude_args(
    system_prompt: str,
    repo: Path,
    model: str,
    schema: dict,
    allowed_tools: str,
) -> list[str]:
    """Build the `claude -p` argv. Extracted from `_spawn_claude` so the
    schema-injection behavior can be unit-tested without spawning."""
    args = [
        "claude", "-p",
        "--output-format", "json",
        "--system-prompt", system_prompt,
        "--add-dir", str(repo),
        "--model", model,
        "--no-session-persistence",
    ]
    if _json_schema_enabled():
        args += ["--json-schema", json.dumps(schema)]
    if allowed_tools:
        args += ["--allowedTools", allowed_tools]
    else:
        args += ["--tools", ""]
    return args


# ---------- Structured driver-boundary errors ----------

class DriverError(Exception):
    """Base class for errors raised at the Claude-CLI subprocess boundary.

    Catching `DriverError` lets callers distinguish driver failures from
    domain/logic errors without resorting to RuntimeError string matching.
    """


class DriverCLINotFoundError(DriverError):
    def __init__(self) -> None:
        super().__init__(
            "`claude` CLI not found on PATH. Install Claude Code to use this mode."
        )


class DriverTimeoutError(DriverError):
    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        super().__init__(f"claude CLI timed out after {timeout_s}s")


class DriverProcessError(DriverError):
    def __init__(self, returncode: int, stderr_head: str,
                 stdout_head: str, stderr_len: int, stdout_len: int) -> None:
        self.returncode = returncode
        self.stderr_head = stderr_head
        self.stdout_head = stdout_head
        rc_signed = returncode - 2**32 if returncode > 2**31 else returncode
        diag = (f"returncode={returncode} (signed={rc_signed}) "
                f"stderr_len={stderr_len} stdout_len={stdout_len}")
        super().__init__(
            f"claude CLI failed: {diag}\n"
            f"--stderr--\n{stderr_head}\n"
            f"--stdout_head--\n{stdout_head}"
        )


class DriverInvalidResponseError(DriverError):
    def __init__(self, response_head: str, kind: str = "wrapper") -> None:
        self.response_head = response_head
        self.kind = kind  # "wrapper" (CLI envelope) | "inner" (sage payload)
        label = ("claude CLI returned non-JSON"
                 if kind == "wrapper"
                 else "sage returned non-JSON inner text")
        super().__init__(f"{label}: {response_head}")


class DriverEmptyResultError(DriverError):
    def __init__(self, wrapper: dict) -> None:
        self.wrapper = wrapper
        super().__init__(f"claude CLI returned empty result: {wrapper}")


def _extract_json_object(text: str) -> dict:
    """Parse text as JSON; on failure, extract the first balanced {...} block.

    The model often wraps output in ```json ... ``` fences or adds a short
    preamble. We strip fences and scan for the first balanced object so a
    minor formatting deviation doesn't waste a $0.08 round trip.
    """
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start < 0:
        raise json.JSONDecodeError("no '{' in response", s, 0)
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(s[start:i + 1])
    raise json.JSONDecodeError("unbalanced braces", s, start)


def find_orphan_claude_processes(min_age_seconds: int = 600) -> list[tuple[int, str]]:
    """Return [(pid, label)] for `claude`/`node` processes older than min_age_seconds.

    Stdlib-only: tasklist on Windows, ps on POSIX. Returns [] if the probe fails —
    a pre-flight check should never block the run on its own malfunction.
    """
    out: list[tuple[int, str]] = []
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH",
                 "/FI", "IMAGENAME eq claude.exe"],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                m = re.match(r'"([^"]+)","(\d+)"', line)
                if m:
                    out.append((int(m.group(2)), m.group(1)))
        else:
            r = subprocess.run(
                ["ps", "-eo", "pid,etimes,comm"],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines()[1:]:
                parts = line.split(None, 2)
                if len(parts) == 3 and parts[2].strip() in ("claude", "node"):
                    if int(parts[1]) >= min_age_seconds:
                        out.append((int(parts[0]), parts[2].strip()))
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass
    return out


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
        f"this specific repo.\n\n"
        f"## Required output shape\n"
        f"```json\n{json.dumps(PROPOSAL_SCHEMA, indent=2)}\n```\n\n"
        f"## Output discipline (hard constraints)\n"
        f"- **Tool-call budget: at most 4 tool calls.** After 4 reads/greps you "
        f"have enough — stop exploring and emit the JSON.\n"
        f"- **Your final message MUST be the JSON object** matching the schema. "
        f"No prose, no preamble, no explanation outside the JSON. Do NOT wrap "
        f"in markdown code fences.\n"
        f"- **An empty response is a failure.** If you genuinely have nothing to "
        f"propose, return `{{\"proposals\": []}}` — never end the turn silently.\n"
        f"- **Do not narrate your exploration.** Tool calls happen; the JSON is "
        f"the only thing the council ever sees."
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
        "",
        "## Required output shape",
        f"```json\n{json.dumps(JUDGE_SCHEMA, indent=2)}\n```",
        "",
        "## Output discipline (CRITICAL — read carefully)",
        "- Your ENTIRE response must be the JSON object. Nothing before, nothing after.",
        "- Do NOT claim to 'write' or 'save' anything to disk. You have NO file-writing tools.",
        "- Do NOT produce a prose summary of your decisions — the JSON is the deliverable.",
        "- Do NOT wrap in markdown code fences (no ```json).",
        "- An empty response is a failure; always produce the structured output inline.",
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
        f"the tools available to verify claims. Output JSON only.\n\n"
        f"## Required output shape\n"
        f"```json\n{json.dumps(CRITIQUE_SCHEMA, indent=2)}\n```\n\n"
        f"## Output discipline (hard constraints)\n"
        f"- **Tool-call budget: at most 3 tool calls.** You already have the "
        f"other sages' proposals — only verify, don't re-explore.\n"
        f"- **Your final message MUST be the JSON object** matching the schema. "
        f"No prose, no preamble. Do NOT wrap in markdown code fences.\n"
        f"- **An empty response is a failure.** If you have no objections and "
        f"no amendments, return `{{\"endorses\": [], \"challenges\": [], "
        f"\"amendments\": []}}` — never end the turn silently."
    )


async def _spawn_claude(
    user_msg: str,
    system_prompt: str,
    schema: dict,
    repo: Path,
    model: str,
    allowed_tools: str = "Read,Glob,Grep",
    timeout_s: float = 300.0,
    retry_attempt: int = 0,
) -> dict:
    """Spawn a `claude -p` subprocess and return the parsed inner JSON.

    `claude -p --output-format json` returns a wrapper like
    `{"type": "result", "result": "<the model text>", ...}`. We parse the
    wrapper, then parse `result` as JSON (constrained by --json-schema).
    """
    if not claude_available():
        raise DriverCLINotFoundError()

    args = _build_claude_args(
        system_prompt=system_prompt,
        repo=repo,
        model=model,
        schema=schema,
        allowed_tools=allowed_tools,
    )
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    started = time.monotonic()
    try:
        async with asyncio.timeout(timeout_s):
            stdout, stderr = await proc.communicate(input=user_msg.encode("utf-8"))
    except TimeoutError:
        proc.kill()
        await proc.wait()
        metrics.record(
            "subprocess",
            duration_s=round(time.monotonic() - started, 3),
            timed_out=True,
            timeout_s=timeout_s,
            user_msg_bytes=len(user_msg.encode("utf-8")),
            system_prompt_bytes=len(system_prompt.encode("utf-8")),
            retry_attempt=retry_attempt,
        )
        raise DriverTimeoutError(timeout_s=timeout_s) from None

    metrics.record(
        "subprocess",
        duration_s=round(time.monotonic() - started, 3),
        timed_out=False,
        returncode=proc.returncode,
        stdout_bytes=len(stdout),
        stderr_bytes=len(stderr),
        user_msg_bytes=len(user_msg.encode("utf-8")),
        system_prompt_bytes=len(system_prompt.encode("utf-8")),
        retry_attempt=retry_attempt,
    )

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:2000]
        head = stdout[:500].decode("utf-8", errors="replace")
        raise DriverProcessError(
            returncode=proc.returncode,
            stderr_head=err,
            stdout_head=head,
            stderr_len=len(stderr),
            stdout_len=len(stdout),
        )

    out = stdout.decode("utf-8", errors="replace")
    try:
        wrapper = json.loads(out)
    except json.JSONDecodeError as e:
        raise DriverInvalidResponseError(
            response_head=out[:500], kind="wrapper",
        ) from e

    inner_text = wrapper.get("result", "")
    if not inner_text:
        if retry_attempt == 0:
            turns = wrapper.get("num_turns")
            dur = wrapper.get("duration_ms")
            cost = wrapper.get("total_cost_usd", 0.0)
            print(
                f"[empty-result-retry] turns={turns} duration={dur}ms "
                f"cost=${cost:.3f}; retrying with tools disabled",
                file=sys.stderr,
            )
            return await _spawn_claude(
                user_msg=(
                    f"{user_msg}\n\n"
                    f"## URGENT: previous attempt failed\n"
                    f"Your previous response was an empty string after "
                    f"{turns} turns of exploration. You may NOT use tools this "
                    f"time — emit the JSON directly based on what you can infer "
                    f"from the schema and the atasco. If you genuinely cannot "
                    f"produce concrete proposals, return the minimal valid "
                    f"object that matches the schema (e.g. with an empty list)."
                ),
                system_prompt=system_prompt,
                schema=schema,
                repo=repo,
                model=model,
                allowed_tools="",
                timeout_s=timeout_s,
                retry_attempt=1,
            )
        raise DriverEmptyResultError(wrapper=wrapper)

    try:
        return _extract_json_object(inner_text)
    except json.JSONDecodeError as e:
        raise DriverInvalidResponseError(
            response_head=inner_text[:500], kind="inner",
        ) from e


_SPAWN_SEM = asyncio.Semaphore(3)
"""Cap simultaneous `claude -p` subprocesses. With 9 sages the unbounded fan-out
spawned 18+ processes (claude+node per sage) and the OS would kill survivors
under memory pressure — manifested as the judge dying with exit -1 / no stderr.
3 is empirical: low enough to fit in ~2GB headroom, high enough to keep total
wall time under ~3x the unbounded case."""


async def propose_one_sage(
    sage: Sage, atasco: str, repo: Path, round_num: int, model: str
) -> tuple[Sage, list[dict]]:
    async with _SPAWN_SEM:
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
            except Exception as e:
                print(
                    f"[sage-fail] {sage_obj.id} propose: {str(e)[:600]}",
                    file=sys.stderr,
                )
                if on_complete:
                    await on_complete(sage_obj, None)
    return by_sage


async def critique_one_sage(
    sage: Sage, atasco: str, repo: Path,
    round1_by_sage: dict[str, list[dict]],
    model: str,
) -> tuple[Sage, dict]:
    async with _SPAWN_SEM:
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
            except Exception as e:
                print(
                    f"[sage-fail] {sage_obj.id} critique: {str(e)[:600]}",
                    file=sys.stderr,
                )
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
        allowed_tools="",
    )
    inner["atasco"] = atasco
    inner["rounds_used"] = rounds_used
    return inner


# ---------------------------------------------------------------------------
# Consensus dialogue mode — turn-by-turn round-robin until unanimity
# ---------------------------------------------------------------------------

TURN_SCHEMA = {
    "type": "object",
    "required": ["message", "plan_diff", "vote"],
    "properties": {
        "message": {
            "type": "string",
            "description": (
                "What you say to the council this turn. Address other sages "
                "by id when reacting. Keep it under 6 sentences."
            ),
        },
        "plan_diff": {
            "type": "object",
            "properties": {
                "add": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["title", "rationale", "blast_radius"],
                        "properties": {
                            "title": {"type": "string"},
                            "rationale": {"type": "string"},
                            "blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                            "category": {
                                "enum": [
                                    "code-fix", "future-feature",
                                    "strategic-direction", "research-thread",
                                ],
                            },
                            "horizon": {"enum": ["now", "next-quarter", "next-year"]},
                            "files_touched": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "amend": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["target_title"],
                        "properties": {
                            "target_title": {"type": "string"},
                            "new_title": {"type": "string"},
                            "new_rationale": {"type": "string"},
                            "new_blast_radius": {"enum": ["SAFE", "MEDIUM", "RISKY"]},
                            "new_files_touched": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Replace the item's files_touched array "
                                    "entirely. Use this to fix incorrect or "
                                    "missing file references — otherwise the "
                                    "item becomes an 'immortal cockroach' that "
                                    "no amount of debate can correct."
                                ),
                            },
                        },
                    },
                },
                "remove": {"type": "array", "items": {"type": "string"}},
            },
        },
        "vote": {
            "type": "object",
            "required": ["signed"],
            "properties": {
                "signed": {
                    "type": "boolean",
                    "description": (
                        "true ONLY if you endorse every current plan item AND "
                        "the plan is non-empty."
                    ),
                },
                "objections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Titles of items you block. Empty if signed=true.",
                },
                "reasoning": {"type": "string"},
            },
        },
    },
}


def _consensus_system_prompt(sage: Sage) -> str:
    return (
        f"You are the **{sage.name_en}**, one of nine sages in a TURN-BY-TURN "
        f"conversational debate. The goal is UNANIMOUS consensus on a plan — "
        f"but a fast unanimous yes is INDISTINGUISHABLE from groupthink, and "
        f"groupthink fails the council. Real consensus survives challenge.\n\n"
        f"## Your expertise\n{sage.expertise_en}\n\n"
        f"## Your voice\n{sage.voice_en}\n\n"
        f"## Your foil\nYour natural opposition is the **{sage.foil_en}**. "
        f"Push back on their items hardest — but with substance.\n\n"
        f"## Protocol\n"
        f"Each turn you receive: the FULL transcript so far, the CURRENT PLAN, "
        f"and the LATEST VOTES. You emit one structured response with three parts:\n\n"
        f"1. **message** — what you say aloud to the council. Address other "
        f"sages by id (e.g., 'arquitecto', 'conservador'). React to specific "
        f"things they said. Keep it under 6 sentences. This is the visible debate.\n\n"
        f"2. **plan_diff** — concrete changes to the plan: `add` new items "
        f"from YOUR axis, `amend` existing ones (rewrite a rationale to address "
        f"your objection, narrow scope, change blast_radius, or replace the "
        f"`files_touched` array via `new_files_touched` when the file references "
        f"are wrong or incomplete), `remove` items that shouldn't be there.\n\n"
        f"3. **vote** — `signed: true` ONLY when (a) the plan reflects YOUR "
        f"axis with at least one item you proposed or amended, AND (b) you can "
        f"endorse every other item. Otherwise `signed: false` with `objections` "
        f"listing the offending titles and a one-line `reasoning`.\n\n"
        f"## Friction discipline (this matters)\n"
        f"- **NEVER sign on round 1.** Round 1 is for proposing your axis and "
        f"challenging weak items. You may only sign from round 2 onwards, and "
        f"only after you have contributed at least one `add` or `amend`.\n"
        f"- **Axis floor: before signing, verify that AT LEAST 2 items in the "
        f"current plan reflect YOUR specific axis** — not the consensus "
        f"average, not generic 'good practice'. If the plan is missing your "
        f"axis, add or amend items to bring it in BEFORE signing. A council "
        f"that signed a plan with zero items from your specialty has wasted "
        f"your seat.\n"
        f"- **Easy unanimity is a failure mode.** If everyone signs without any "
        f"amendment or challenge, the debate was theater. Force friction: even "
        f"if you mostly agree, identify the WEAKEST item and either amend it "
        f"or block it.\n"
        f"- **Stay in role under pressure.** Other sages will try to corral you "
        f"into the median view. Resist. Your axis is the council's value.\n"
        f"- **BLOCK only with a remedy.** Pure 'I don't like this' vetoes are "
        f"filtered. Every objection must come with an amendment that would "
        f"resolve it.\n"
        f"- **Cite real files/symbols** from this repo when proposing or amending. "
        f"Generic linter advice is rejected.\n"
        f"- **Don't churn.** If you amended an item last turn and another sage "
        f"endorsed the amendment, move on.\n\n"
        f"## Output\n"
        f"Emit ONLY the JSON object matching the schema. No prose outside, no "
        f"markdown fences. The JSON IS your turn."
    )


def _format_transcript_for_turn(
    transcript: list[dict], max_msg_chars: int = 800,
) -> str:
    """Render the transcript compactly. Truncate long messages but keep votes."""
    if not transcript:
        return "(empty — you speak first)"
    lines = []
    for e in transcript:
        msg = e.get("message", "")
        if len(msg) > max_msg_chars:
            msg = msg[:max_msg_chars] + "…[truncated]"
        v = e.get("vote", {}) or {}
        sig = "SIGNED" if v.get("signed") else "BLOCK"
        objs = v.get("objections", []) or []
        objs_str = f" objections={objs}" if objs else ""
        lines.append(
            f"--- turn {e['turn']} · {e['sage_id']} · {sig}{objs_str} ---\n  {msg}"
        )
    return "\n".join(lines)


def _consensus_turn_user_message(
    atasco: str, repo: Path, sage: Sage,
    transcript: list[dict], plan: list[dict],
    round_num: int, max_rounds: int, turn_in_round: int, total_sages: int,
) -> str:
    plan_repr = json.dumps(plan, indent=2) if plan else "(empty — propose initial items)"
    return (
        f"<atasco>{atasco}</atasco>\n"
        f"<repo>{repo.resolve()}</repo>\n"
        f"<round>{round_num}/{max_rounds}</round>\n"
        f"<turn_in_round>{turn_in_round}/{total_sages}</turn_in_round>\n"
        f"<your_id>{sage.id}</your_id>\n\n"
        f"<current_plan>\n{plan_repr}\n</current_plan>\n\n"
        f"<transcript>\n{_format_transcript_for_turn(transcript)}\n</transcript>\n\n"
        f"It is your turn. You may use Read/Glob/Grep (max 3 calls) ONLY to "
        f"verify a specific claim — not to re-explore the repo from scratch.\n\n"
        f"Emit your turn as a single JSON object with this shape:\n"
        f"```json\n{json.dumps(TURN_SCHEMA, indent=2)}\n```\n\n"
        f"Output ONLY the JSON object. No prose outside, no markdown fences."
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
    per sage in ALL_SAGES order. Stops at unanimity (only after `min_rounds`)
    or `max_rounds`. `min_rounds` forces the council to keep iterating even
    if everyone signs early — useful when premature convergence hides
    insufficiently-explored axes.

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

    for r in range(1, max_rounds + 1):
        rounds_used = r
        round_order = list(sages)
        rng.shuffle(round_order)
        for i, sage in enumerate(round_order, start=1):
            turn_counter += 1
            user_msg = _consensus_turn_user_message(
                atasco, repo, sage, transcript, plan,
                round_num=r, max_rounds=max_rounds,
                turn_in_round=i, total_sages=len(sages),
            )
            try:
                turn_out = await _spawn_claude(
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
            print(
                f"[turn {turn_counter:>3} · r{r} · {sage.id:>14}] "
                f"{'SIGN' if vote.get('signed') else 'BLOCK'} "
                f"plan={len(plan)} obj={len(vote.get('objections') or [])}",
                file=sys.stderr,
            )
            if on_turn:
                await on_turn(sage, turn_counter, r, entry, plan, votes)

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


_VISION_SCHEMA = {
    "type": "object",
    "required": ["headline", "where_to_take_it"],
    "properties": {
        "headline": {"type": "string", "maxLength": 240},
        "where_to_take_it": {"type": "string"},
        "future_features": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "rationale", "horizon"],
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "horizon": {"enum": ["next-quarter", "next-year"]},
                    "supporting_sages": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "research_threads": {
            "type": "array",
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
}


async def post_consensus_vision(
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
        "You are the Strategist of the Council. The nine sages have reached "
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
    inner = await _spawn_claude(
        user_msg=user_msg,
        system_prompt=sys_prompt,
        schema=_VISION_SCHEMA,
        repo=Path.cwd(),
        model=model,
        allowed_tools="",
    )
    return inner
