"""Claude Code driver: spawns `claude -p` subprocesses as the 7 sages.

Uses the user's authenticated Claude Code session (Pro/Max subscription).
No ANTHROPIC_API_KEY required.

This module now contains only the claude-CLI-specific pieces:
  - argv builder + subprocess spawn (`_spawn_claude`)
  - sage wrappers that the orchestrator calls (propose / critique / judge)
  - zombie process detection (`find_orphan_claude_processes`)

Backend-agnostic pieces have been extracted:
  - DriverError* hierarchy → driver_errors.py
  - _extract_json_object   → json_utils.py
  - JSON schemas           → schemas.py
  - prompt strings         → council_prompts.py
  - consensus dialogue     → consensus.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .council_prompts import (
    _build_critique_user_message,
    _build_judge_user_message,
    _build_sage_user_message,
    _judge_system_prompt,
    _sage_critique_system_prompt,
    _sage_system_prompt,
)
from .driver_errors import (
    DriverCLINotFoundError,
    DriverEmptyResultError,
    DriverInvalidResponseError,
    DriverProcessError,
    DriverTimeoutError,
)
from .driver_protocol import SageDriver
from .json_utils import _extract_json_object
from .sages import ALL_SAGES, Sage
from .schemas import CRITIQUE_SCHEMA, JUDGE_SCHEMA, PROPOSAL_SCHEMA


def _json_schema_enabled() -> bool:
    """Whether to pass `--json-schema` to the claude CLI.

    Default OFF. On claude 2.1.85 the strict `--json-schema` validation
    swallowed *every* opus turn as an empty `result` (100% empty-result
    retries in a real consensus debate), which doubled cost and — worse —
    stripped repo tools (Read/Glob/Grep) from the regenerated answer, so the
    debate ran without code grounding. The heuristic `_extract_json_object`
    fallback parses the free-text output reliably and keeps tools on the
    primary call. Set `CONSEJO_USE_JSON_SCHEMA=1` to opt back in if a future
    CLI fixes the validation behavior.
    """
    return os.environ.get("CONSEJO_USE_JSON_SCHEMA") == "1"


def _build_claude_args(
    system_prompt: str,
    repo: Path,
    model: str,
    schema: dict,
    allowed_tools: str,
    disable_schema: bool = False,
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
    if _json_schema_enabled() and not disable_schema:
        args += ["--json-schema", json.dumps(schema)]
    if allowed_tools:
        args += ["--allowedTools", allowed_tools]
    else:
        args += ["--tools", ""]
    return args

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


def claude_available() -> bool:
    return shutil.which("claude") is not None


async def _spawn_claude(
    user_msg: str,
    system_prompt: str,
    schema: dict,
    repo: Path,
    model: str,
    allowed_tools: str = "Read,Glob,Grep",
    timeout_s: float = 300.0,
    retry_attempt: int = 0,
    disable_schema: bool = False,
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
        disable_schema=disable_schema,
    )
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(timeout_s):
            stdout, stderr = await proc.communicate(input=user_msg.encode("utf-8"))
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise DriverTimeoutError(
            timeout_s=timeout_s,
            context={
                "model": model,
                "user_msg_bytes": len(user_msg.encode("utf-8")),
                "system_prompt_bytes": len(system_prompt.encode("utf-8")),
                "retry_attempt": retry_attempt,
            },
        ) from None

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:2000]
        head = stdout[:500].decode("utf-8", errors="replace")
        raise DriverProcessError(
            returncode=proc.returncode,
            stderr_head=err,
            stdout_head=head,
            stderr_len=len(stderr),
            stdout_len=len(stdout),
            context={
                "model": model,
                "user_msg_bytes": len(user_msg.encode("utf-8")),
                "system_prompt_bytes": len(system_prompt.encode("utf-8")),
                "retry_attempt": retry_attempt,
            },
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
            # The retry also drops --json-schema. Empirically, strict schema
            # validation in `claude -p` swallows the model's output as empty
            # string when it doesn't pass validation (opus emits valid-looking
            # JSON of 700-900 tokens but the wrapper.result still comes back
            # ''). Without --json-schema the model emits free text and
            # `_extract_json_object` parses out the JSON heuristically.
            print(
                f"[empty-result-retry] turns={turns} duration={dur}ms "
                f"cost=${cost:.3f}; retrying without tools and without schema",
                file=sys.stderr,
            )
            schema_hint = json.dumps(schema, indent=2)
            return await _spawn_claude(
                user_msg=(
                    f"{user_msg}\n\n"
                    f"## URGENT: previous attempt failed\n"
                    f"Your previous response was an empty string after "
                    f"{turns} turns. You may NOT use tools this time — emit "
                    f"the JSON object **directly as your final message** "
                    f"(no preamble, no markdown fences). It must match this "
                    f"schema:\n```json\n{schema_hint}\n```\n"
                    f"If you genuinely have nothing to propose, return the "
                    f"minimal valid object (empty arrays for list fields)."
                ),
                system_prompt=system_prompt,
                schema=schema,
                repo=repo,
                model=model,
                allowed_tools="",
                timeout_s=timeout_s,
                retry_attempt=1,
                disable_schema=True,
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
    driver: SageDriver, sage: Sage, atasco: str, repo: Path,
    round_num: int, model: str,
) -> tuple[Sage, list[dict]]:
    async with _SPAWN_SEM:
        inner = await driver.spawn(
            user_msg=_build_sage_user_message(atasco, repo, round_num),
            system_prompt=_sage_system_prompt(sage),
            schema=PROPOSAL_SCHEMA,
            repo=repo,
            model=model,
        )
    return sage, inner.get("proposals", [])


async def gather_all_proposals(
    driver: SageDriver, atasco: str, repo: Path, model: str = "sonnet",
    on_complete=None,
) -> dict[str, list[dict]]:
    """Run all 7 sages in parallel.

    `on_complete`: optional async callable `(sage, props_or_none) -> None`
    invoked as each sage finishes. Used by the animator to emit per-sage
    DEBATE events so the long parallel analysis feels alive instead of
    a single blocking wait.
    """
    pending: dict[asyncio.Task, Sage] = {
        asyncio.create_task(propose_one_sage(driver, s, atasco, repo, 1, model)): s
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
    driver: SageDriver, sage: Sage, atasco: str, repo: Path,
    round1_by_sage: dict[str, list[dict]],
    model: str,
) -> tuple[Sage, dict]:
    async with _SPAWN_SEM:
        inner = await driver.spawn(
            user_msg=_build_critique_user_message(atasco, repo, round1_by_sage, sage.id),
            system_prompt=_sage_critique_system_prompt(sage),
            schema=CRITIQUE_SCHEMA,
            repo=repo,
            model=model,
        )
    return sage, inner


async def gather_all_critiques(
    driver: SageDriver, atasco: str, repo: Path,
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
            critique_one_sage(driver, s, atasco, repo, round1_by_sage, model)
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
    driver: SageDriver,
    atasco: str,
    proposals_by_sage: dict[str, list[dict]],
    critiques_by_sage: dict[str, dict] | None = None,
    rounds_used: int = 1,
    model: str = "opus",
) -> dict:
    """Run the judge to synthesize all proposals into a prioritized plan +
    a strategic vision. Always uses Opus regardless of `model` — synthesis
    is where depth/coherence pay off the most."""
    inner = await driver.spawn(
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


class ClaudeCodeBackend:
    """SageDriver respaldado por el flujo `claude -p` de este módulo.

    Colapsado desde el antiguo `backends/claude_code.py` (adaptador fino): el
    backend vive ahora junto a su implementación (`_spawn_claude` /
    `claude_available`), sin la indirección entre módulos.
    """

    name = "claude-code"

    def available(self) -> bool:
        return claude_available()

    async def spawn(
        self,
        *,
        user_msg: str,
        system_prompt: str,
        schema: dict,
        repo: Path,
        model: str,
        allowed_tools: str = "Read,Glob,Grep",
        timeout_s: float = 300.0,
    ) -> dict:
        return await _spawn_claude(
            user_msg=user_msg,
            system_prompt=system_prompt,
            schema=schema,
            repo=repo,
            model=model,
            allowed_tools=allowed_tools,
            timeout_s=timeout_s,
        )
