"""CLI principal del Consejo · `consejo "<atasco>" [--repo PATH] [--mode mock|real|claude-code]`

Conecta el orquestador real al animator (mismo bus). Si `--no-ui` se pasa,
corre en modo headless e imprime las transiciones de estado.

Ejemplos:
    consejo "El módulo auth tiene 800 líneas y los tests son frágiles"
    consejo "Refactor X" --repo ./otro-repo --mode mock --speed 0.7
    consejo "..." --no-ui --rounds 5                # headless
    consejo "..." --mode real                       # ANTHROPIC_API_KEY required
    consejo "..." --mode claude-code --rounds 2     # subagents via Claude Code CLI
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from .backends import build_backend
from .executor import execute_safe_tasks, is_git_repo
from .orchestrator import render_plan_markdown, run_council
from .states import MAX_DEBATE_ROUNDS, EventBus, State


def _slugify(text: str, max_len: int = 40) -> str:
    """Lowercase ascii slug for filenames. Strips accents, collapses non-word
    runs to hyphens, caps length, strips leading/trailing hyphens."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_len].rstrip("-") or "atasco"


def _report_filename(atasco: str, when: datetime | None = None) -> Path:
    when = when or datetime.now()
    return Path.cwd() / f"consejo-report-{when:%Y%m%d-%H%M%S}-{_slugify(atasco)}.md"


def _build_driver(atasco: str, repo: Path, mode: str, speed: float,
                  target_rounds: int, seed: int | None,
                  execute_mode: str = "none",
                  max_execute_tasks: int = 10,
                  cc_model: str = "sonnet",
                  consensus_mode: bool = False,
                  consensus_max_rounds: int = 20,
                  consensus_min_rounds: int = 1,
                  backend: str = "claude-code",
                  out_holder: dict | None = None):
    """Devuelve una corutina (bus) -> None lista para pasar al animator.

    `out_holder` (dict opcional): si se pasa, el driver guarda `out_holder['path']`
    con la ruta absoluta del reporte para que main() pueda imprimirla.

    execute_mode: 'none' | 'auto' | 'manual'
      - none/manual: solo genera el reporte
      - auto: además, ejecuta tareas SAFE en una rama nueva del repo
    """
    async def driver(bus: EventBus) -> Path:
        plan = await run_council(
            atasco=atasco,
            repo=repo,
            bus=bus,
            mode=mode,
            target_rounds=target_rounds,
            speed=speed,
            seed=seed,
            cc_model=cc_model,
            consensus_mode=consensus_mode,
            consensus_max_rounds=consensus_max_rounds,
            consensus_min_rounds=consensus_min_rounds,
            backend=backend,
        )
        execution = None
        if execute_mode == "auto" and await is_git_repo(repo):
            try:
                execution = await execute_safe_tasks(
                    plan, repo, max_tasks=max_execute_tasks,
                )
            except Exception as e:
                execution = {"branch_name": "", "commits": [],
                             "skipped": [], "note": f"Execution failed: {e}"}
        out_path = _report_filename(atasco)
        out_path.write_text(render_plan_markdown(plan, execution=execution),
                            encoding="utf-8")
        if out_holder is not None:
            out_holder["path"] = out_path
        return out_path
    return driver


async def _run_headless(atasco: str, repo: Path, mode: str, speed: float,
                        target_rounds: int, seed: int | None,
                        execute_mode: str = "none",
                        max_execute_tasks: int = 10,
                        cc_model: str = "sonnet",
                        consensus_mode: bool = False,
                        consensus_max_rounds: int = 20,
                        consensus_min_rounds: int = 1,
                        backend: str = "claude-code",
                        out_holder: dict | None = None) -> Path:
    bus = EventBus()
    driver = _build_driver(atasco, repo, mode, speed, target_rounds, seed,
                           execute_mode=execute_mode,
                           max_execute_tasks=max_execute_tasks,
                           cc_model=cc_model,
                           consensus_mode=consensus_mode,
                           consensus_max_rounds=consensus_max_rounds,
                           consensus_min_rounds=consensus_min_rounds,
                           backend=backend,
                           out_holder=out_holder)

    async def consume_print() -> None:
        async for ev in bus.consume():
            suf = f" round={ev.round_num}" if ev.state == State.DEBATE else ""
            sig = ""
            if ev.state == State.DEBATE and ev.payload.get("signed_this_round"):
                sig = f" new_signs={ev.payload['signed_this_round']}"
            print(f"[{ev.state.value}]{suf}{sig}")

    producer = asyncio.create_task(driver(bus))
    consumer = asyncio.create_task(consume_print())
    out_path = await producer
    await consumer
    return out_path


def _error_missing_api_key() -> str:
    return (
        "--mode real requires ANTHROPIC_API_KEY in env / requiere ANTHROPIC_API_KEY en env.\n\n"
        "  PowerShell:  $env:ANTHROPIC_API_KEY = \"sk-ant-...\"\n"
        "  bash/zsh:    export ANTHROPIC_API_KEY=sk-ant-...\n"
        "  cmd.exe:     setx ANTHROPIC_API_KEY \"sk-ant-...\"  (permanent, reopen shell)\n\n"
        "Get a key: https://console.anthropic.com/settings/keys\n"
        "Note: a Pro/Max subscription does NOT include API credits — they bill separately.\n"
        "Tip: use --mode claude-code to run via your Claude Code session without an API key."
    )


def _error_missing_anthropic_sdk() -> str:
    return (
        "--mode real requires the `anthropic` SDK / requiere el SDK anthropic.\n\n"
        "  Install:  .venv/Scripts/pip install anthropic   (Windows)\n"
        "            .venv/bin/pip install anthropic       (POSIX)\n\n"
        "Tip: use --mode claude-code to skip the SDK and run via Claude Code CLI."
    )


def _error_missing_claude_cli() -> str:
    return (
        "--mode claude-code requires the `claude` CLI in PATH / requiere el CLI `claude` en PATH.\n\n"
        "  Install Claude Code: https://docs.claude.com/claude-code\n"
        "  Verify after install: claude --version\n\n"
        "If installed but not found, restart the shell so PATH is reloaded."
    )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="consejo",
        description="El Consejo de los 7 Sabios — debate técnico estructurado.",
    )
    parser.add_argument(
        "atasco", nargs="?", default="Mejora general del proyecto",
        help="Stuck point / improvement target. Spanish or English. "
             "Alias en inglés: --problem.",
    )
    parser.add_argument(
        "--problem", dest="atasco_en", default=None,
        help="English alias for the positional `atasco` argument. "
             "If set, overrides positional.",
    )
    parser.add_argument("--repo", type=Path, default=Path.cwd(),
                    help="Ruta del repo a analizar (default: cwd)")
    parser.add_argument("--mode", choices=["mock", "real", "claude-code"], default="mock",
                        help="mock = canned proposals · real = anthropic SDK · "
                             "claude-code = 7 subagents via Claude Code CLI (no API key)")
    parser.add_argument("--cc-model", default="opus",
                        help="Model for --mode claude-code (sonnet|opus|alias). "
                             "Default: opus (deeper debate; cheaper switch: --cc-model sonnet)")
    parser.add_argument("--backend", choices=["claude-code", "codex"],
                        default="claude-code",
                        help="Backend CLI for sage subprocesses. "
                             "claude-code: uses `claude -p` (default). "
                             "codex: uses OpenAI `codex exec`. "
                             "Only applies with --mode claude-code.")
    parser.add_argument("--rounds", type=int, default=3,
                        help="Rondas objetivo de debate. mock/real: 1..30. "
                             "claude-code: auto-capped to 1-2 (round 1 propose, "
                             "round 2 cross-examination)")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Velocidad de la animación")
    parser.add_argument("--seed", type=int, default=None,
                        help="Semilla para asignación de asientos / mock")
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--sound", action="store_true",
                        help="Habilita sonido (default: OFF). Por defecto la "
                             "sesión es silenciosa para no romper grabaciones / "
                             "reuniones / contextos de oficina.")
    parser.add_argument("--no-ui", action="store_true",
                        help="Modo headless: sin animación, solo logs")
    parser.add_argument("--execute", choices=["none", "auto", "manual"],
                        default="none",
                        help="auto: crea rama + commits SAFE · manual/none: solo reporte")
    parser.add_argument("--max-execute-tasks", type=int, default=10,
                        help="Tope de tareas SAFE a commitear en modo auto")
    parser.add_argument("--consensus", action="store_true",
                        help="Modo conversacional turn-by-turn: los 9 sabios "
                             "debaten en ronda-robin hasta unanimidad o cap. "
                             "Solo aplica con --mode claude-code.")
    parser.add_argument("--consensus-rounds", type=int, default=20,
                        help="Cap de rondas en --consensus (default: 20). "
                             "Cada ronda son 9 turnos (1 por sabio).")
    parser.add_argument("--consensus-min-rounds", type=int, default=1,
                        help="Floor de rondas mínimas (default: 1). Fuerza "
                             "al consejo a seguir aunque firmen todos antes. "
                             "Sube a 5+ si convergen demasiado rápido.")
    args = parser.parse_args()

    atasco = args.atasco_en if args.atasco_en else args.atasco

    if args.rounds < 1 or args.rounds > MAX_DEBATE_ROUNDS:
        parser.error(f"--rounds debe estar entre 1 y {MAX_DEBATE_ROUNDS}")

    if args.mode == "real":
        try:
            import importlib
            importlib.import_module("anthropic")
        except ImportError:
            parser.error(_error_missing_anthropic_sdk())
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            parser.error(_error_missing_api_key())

    if args.mode == "claude-code":
        from .claude_code_driver import find_orphan_claude_processes
        try:
            backend_instance = build_backend(args.backend)
        except ValueError as e:
            parser.error(str(e))
        if not backend_instance.available():
            if args.backend == "codex":
                parser.error(
                    "--backend codex requires the `codex` CLI in PATH / "
                    "requiere el CLI `codex` en PATH.\n\n"
                    "  Install: npm install -g @openai/codex\n"
                    "  Verify:  codex --version\n\n"
                    "If installed but not found, restart the shell so PATH is reloaded."
                )
            parser.error(_error_missing_claude_cli())
        orphans = find_orphan_claude_processes()
        if orphans:
            pids = ",".join(str(p) for p, _ in orphans)
            print(
                f"\n[WARN] {len(orphans)} proceso(s) claude/node detectado(s) "
                f"(PIDs: {pids}). Si vienen de una sesion previa del consejo, "
                f"pueden agotar memoria y matar al juez (exit -1 sin stderr).\n"
                f"  PowerShell: Stop-Process -Id {pids} -Force\n"
                f"  Ojo: confirma que ninguno sea tu Claude Code activo "
                f"(mira StartTime en Get-Process).\n",
                file=sys.stderr,
            )

    out_holder: dict = {}

    if args.consensus and args.mode != "claude-code":
        parser.error("--consensus solo funciona con --mode claude-code")

    if args.no_ui:
        asyncio.run(_run_headless(
            atasco, args.repo, args.mode, args.speed,
            args.rounds, args.seed,
            execute_mode=args.execute,
            max_execute_tasks=args.max_execute_tasks,
            cc_model=args.cc_model,
            consensus_mode=args.consensus,
            consensus_max_rounds=args.consensus_rounds,
            consensus_min_rounds=args.consensus_min_rounds,
            backend=args.backend,
            out_holder=out_holder,
        ))
    else:
        from .animator import animate
        driver = _build_driver(atasco, args.repo, args.mode, args.speed,
                               args.rounds, args.seed,
                               execute_mode=args.execute,
                               max_execute_tasks=args.max_execute_tasks,
                               cc_model=args.cc_model,
                               consensus_mode=args.consensus,
                               consensus_max_rounds=args.consensus_rounds,
                               consensus_min_rounds=args.consensus_min_rounds,
                               backend=args.backend,
                               out_holder=out_holder)
        asyncio.run(animate(
            speed=args.speed,
            scale=args.scale,
            seed=args.seed,
            sound=args.sound,
            driver=driver,
        ))

    report = out_holder.get("path")
    if report and report.exists():
        print(f"\n📜 Consejo finalizado · reporte: {report}", file=sys.stderr)
    else:
        print("\nConsejo finalizado.", file=sys.stderr)


if __name__ == "__main__":
    main()
