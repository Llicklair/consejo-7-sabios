"""CodexBackend — adapter for OpenAI's Codex CLI (`codex exec`).

Implementation notes
--------------------
Codex CLI differs from `claude -p` in three important ways:

1. **No `--system-prompt` flag.** Codex takes a single prompt via stdin or
   argv. We concatenate the system prompt and user message with a clear
   separator. The model is instructed by the prefixed system block.
2. **No `--json-schema` enforcement.** Codex prints free-form agent output.
   We embed the schema instruction inline in the prompt and parse the
   final message heuristically with `_extract_json_object`. A single
   retry pass tightens the instruction if the first attempt fails.
3. **Final message extraction.** `codex exec --output-last-message FILE`
   writes the agent's final assistant message to FILE (cleanly separated
   from intermediate tool turns). We read that file instead of parsing
   stdout, which is a streaming UI log.

Sandbox: we map `allowed_tools` heuristically. Tools that include any of
Read/Glob/Grep imply read-only access → `--sandbox read-only`. Empty
allowed_tools (judge/vision) → also read-only (we never want the council
to write files). Codex's `workspace-write` is reserved for future
write-mode features.

Errors are normalized into the same `DriverError` hierarchy that
`ClaudeCodeBackend` uses, so the orchestrator does not need to know which
backend raised.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

from ..driver_errors import (
    DriverCLINotFoundError,
    DriverEmptyResultError,
    DriverInvalidResponseError,
    DriverProcessError,
    DriverTimeoutError,
)
from ..json_utils import _extract_json_object


def codex_available() -> bool:
    return shutil.which("codex") is not None


def _build_codex_args(
    *,
    repo: Path,
    model: str,
    sandbox: str,
    output_last_message: Path,
) -> list[str]:
    """Build the `codex exec` argv. Extracted for unit-testing."""
    args = [
        "codex", "exec",
        "--model", model,
        "--cd", str(repo),
        "--sandbox", sandbox,
        "--skip-git-repo-check",
        "--color", "never",
        "--output-last-message", str(output_last_message),
        "-",
    ]
    return args


def _compose_prompt(
    *,
    system_prompt: str,
    user_msg: str,
    schema: dict,
    inject_schema_hint: bool,
) -> str:
    """Codex has no `--system-prompt`. Prepend the identity block to the
    user message with a hard separator so the model treats it as
    durable context, not part of the user turn.

    When `inject_schema_hint` is True (default) we append a strong
    structured-output instruction. The retry path strengthens it further.
    """
    schema_json = json.dumps(schema, indent=2)
    schema_block = ""
    if inject_schema_hint:
        schema_block = (
            "\n\n## Required output\n"
            "Your final assistant message MUST be a single JSON object "
            "matching this schema. No prose around it, no markdown fences, "
            "no commentary. Emit the JSON object directly as your final "
            "message:\n"
            f"```json\n{schema_json}\n```\n"
        )
    return (
        f"<system_identity>\n{system_prompt}\n</system_identity>\n\n"
        f"<user_request>\n{user_msg}\n</user_request>"
        f"{schema_block}"
    )


def _sandbox_for(allowed_tools: str) -> str:
    """Map the council's `allowed_tools` string to a Codex sandbox mode.

    Council sages are always read-only by design — the orchestrator does
    not allow Write/Edit. Both populated allowed_tools (Read/Glob/Grep)
    and empty allowed_tools (judge/vision) map to `read-only`.
    """
    return "read-only"


class CodexBackend:
    name = "codex"

    def available(self) -> bool:
        return codex_available()

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
        return await self._spawn(
            user_msg=user_msg,
            system_prompt=system_prompt,
            schema=schema,
            repo=repo,
            model=model,
            allowed_tools=allowed_tools,
            timeout_s=timeout_s,
            retry_attempt=0,
        )

    async def _spawn(
        self,
        *,
        user_msg: str,
        system_prompt: str,
        schema: dict,
        repo: Path,
        model: str,
        allowed_tools: str,
        timeout_s: float,
        retry_attempt: int,
    ) -> dict:
        if not codex_available():
            raise DriverCLINotFoundError()

        # codex exec --output-last-message writes the final assistant
        # message to disk for clean parsing.
        out_file = Path(tempfile.mkstemp(prefix="codex-out-", suffix=".txt")[1])
        try:
            args = _build_codex_args(
                repo=repo,
                model=model,
                sandbox=_sandbox_for(allowed_tools),
                output_last_message=out_file,
            )
            prompt = _compose_prompt(
                system_prompt=system_prompt,
                user_msg=user_msg,
                schema=schema,
                inject_schema_hint=True,
            )

            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                async with asyncio.timeout(timeout_s):
                    stdout, stderr = await proc.communicate(
                        input=prompt.encode("utf-8")
                    )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise DriverTimeoutError(timeout_s=timeout_s) from None

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

            # Prefer the dedicated output file. Fall back to stdout if for
            # any reason the file is empty (older codex versions, sandbox
            # quirks).
            final_msg = ""
            if out_file.exists():
                final_msg = out_file.read_text(
                    encoding="utf-8", errors="replace"
                ).strip()
            if not final_msg:
                final_msg = stdout.decode("utf-8", errors="replace").strip()

            if not final_msg:
                if retry_attempt == 0:
                    print(
                        "[codex empty-result-retry] final message empty; "
                        "retrying with hardened JSON-only instruction",
                        file=sys.stderr,
                    )
                    return await self._spawn(
                        user_msg=(
                            f"{user_msg}\n\n"
                            f"## URGENT: previous attempt produced no final message.\n"
                            f"You may NOT use tools this time. Emit the JSON "
                            f"object DIRECTLY as your final message — no preamble, "
                            f"no fences, no commentary. If you have nothing to "
                            f"propose, return the minimal valid object (empty "
                            f"arrays for list fields)."
                        ),
                        system_prompt=system_prompt,
                        schema=schema,
                        repo=repo,
                        model=model,
                        allowed_tools="",
                        timeout_s=timeout_s,
                        retry_attempt=1,
                    )
                raise DriverEmptyResultError(wrapper={"raw_stdout_head": stdout[:500].decode("utf-8", errors="replace")})

            try:
                return _extract_json_object(final_msg)
            except json.JSONDecodeError as e:
                if retry_attempt == 0:
                    print(
                        f"[codex parse-retry] heuristic JSON parse failed; "
                        f"retrying with stricter instruction. head={final_msg[:200]!r}",
                        file=sys.stderr,
                    )
                    return await self._spawn(
                        user_msg=(
                            f"{user_msg}\n\n"
                            f"## CRITICAL: previous attempt did not return parseable JSON.\n"
                            f"Output ONLY the JSON object. No text before. No text "
                            f"after. No markdown fences. The very first character "
                            f"of your final message MUST be `{{` and the very "
                            f"last MUST be `}}`."
                        ),
                        system_prompt=system_prompt,
                        schema=schema,
                        repo=repo,
                        model=model,
                        allowed_tools="",
                        timeout_s=timeout_s,
                        retry_attempt=1,
                    )
                raise DriverInvalidResponseError(
                    response_head=final_msg[:500], kind="inner",
                ) from e
        finally:
            try:
                if out_file.exists():
                    out_file.unlink()
            except OSError:
                pass
