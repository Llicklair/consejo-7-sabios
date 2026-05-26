"""CLI principal del Consejo: `consejo "<atasco>" [--repo PATH] [--mode mock|real]`

Conecta el orquestador real al animator (mismo bus). Si `--no-ui` se pasa,
corre en modo headless e imprime las transiciones de estado.

Ejemplos:
    consejo "El módulo auth tiene 800 líneas y los tests son frágiles"
    consejo "Refactor X" --repo ./otro-repo --mode mock --speed 0.7
    consejo "..." --no-ui --rounds 5   # headless
    consejo "..." --mode real           # ANTHROPIC_API_KEY required
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from functools import partial
from pathlib import Path

from .executor import execute_safe_tasks, is_git_repo
from .orchestrator import render_plan_markdown, run_council
from .states import MAX_DEBATE_ROUNDS, EventBus, State


def _build_driver(atasco: str, repo: Path, mode: str, speed: float,
                  target_rounds: int, seed: int | None,
                  execute_mode: str = "none",
                  max_execute_tasks: int = 10,
                  cc_model: str = "sonnet"):
    """Devuelve una corutina (bus) -> None lista para pasar al animator.

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
        )
        # Modo auto: crear rama + commitear SAFE tasks
        execution = None
        if execute_mode == "auto" and is_git_repo(repo):
            try:
                execution = execute_safe_tasks(plan, repo, max_tasks=max_execute_tasks)
            except Exception as e:
                execution = {"branch_name": "", "commits": [],
                             "skipped": [], "note": f"Execution failed: {e}"}
        # Reporte (bilingüe + ejecución)
        ts = datetime.now()
        out_path = Path.cwd() / f"consejo-report-{ts:%Y%m%d-%H%M%S}.md"
        out_path.write_text(render_plan_markdown(plan, execution=execution),
                            encoding="utf-8")
        return out_path
    return driver


async def _run_headless(atasco: str, repo: Path, mode: str, speed: float,
                        target_rounds: int, seed: int | None,
                        execute_mode: str = "none",
                        max_execute_tasks: int = 10,
                        cc_model: str = "sonnet") -> Path:
    bus = EventBus()
    driver = _build_driver(atasco, repo, mode, speed, target_rounds, seed,
                           execute_mode=execute_mode,
                           max_execute_tasks=max_execute_tasks,
                           cc_model=cc_model)

    async def consume_print() -> None:
        async for ev in bus.consume():
            suf = f" round={ev.round_num}" if ev.state == State.DEBATE else ""
            sig = ""
            if ev.state == State.DEBATE and ev.payload.get("signed_this_round"):
                sig = f" new_signs={ev.payload['signed_this_round']}"
            print(f"[{ev.state.value}]{suf}{sig}")

    producer = asyncio.create_task(driver(bus))
    consumer = asyncio.create_task(consume_print())
    await producer
    await consumer

    ts = datetime.now()
    out_path = Path.cwd() / f"consejo-report-{ts:%Y%m%d-%H%M%S}.md"
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="consejo",
        description="El Consejo de los 7 Sabios — debate técnico estructurado.",
    )
    parser.add_argument("atasco", nargs="?",
                        default="Mejora general del proyecto",
                        help="Descripción del problema a debatir")
    parser.add_argument("--repo", type=Path, default=Path.cwd(),
                        help="Ruta del repo a analizar (default: cwd)")
    parser.add_argument("--mode", choices=["mock", "real", "claude-code"], default="mock",
                        help="mock = sin API · real = anthropic SDK · "
                             "claude-code = 7 subagentes via Claude Code CLI (sin API key)")
    parser.add_argument("--cc-model", default="sonnet",
                        help="Modelo para --mode claude-code (sonnet|opus|alias). "
                             "Default: sonnet")
    parser.add_argument("--rounds", type=int, default=3,
                        help="Rondas objetivo de debate. mock/real: 1..30. "
                             "claude-code: auto-capado a 1-2 (round 1 propose, "
                             "round 2 cross-examination)")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Velocidad de la animación")
    parser.add_argument("--seed", type=int, default=None,
                        help="Semilla para asignación de asientos / mock")
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--no-sound", action="store_true")
    parser.add_argument("--no-ui", action="store_true",
                        help="Modo headless: sin animación, solo logs")
    parser.add_argument("--execute", choices=["none", "auto", "manual"],
                        default="none",
                        help="auto: crea rama + commits SAFE · manual/none: solo reporte")
    parser.add_argument("--max-execute-tasks", type=int, default=10,
                        help="Tope de tareas SAFE a commitear en modo auto")
    args = parser.parse_args()

    if args.rounds < 1 or args.rounds > MAX_DEBATE_ROUNDS:
        parser.error(f"--rounds debe estar entre 1 y {MAX_DEBATE_ROUNDS}")

    if args.mode == "real":
        try:
            import anthropic  # noqa
        except ImportError:
            parser.error("--mode real requiere `pip install anthropic`")
        import os
        if not os.environ.get("ANTHROPIC_API_KEY"):
            parser.error("--mode real requiere ANTHROPIC_API_KEY en env")

    if args.mode == "claude-code":
        from .claude_code_driver import claude_available
        if not claude_available():
            parser.error(
                "--mode claude-code requiere el CLI `claude` en PATH. "
                "Instala Claude Code: https://docs.claude.com/claude-code"
            )

    if args.no_ui:
        asyncio.run(_run_headless(
            args.atasco, args.repo, args.mode, args.speed,
            args.rounds, args.seed,
            execute_mode=args.execute,
            max_execute_tasks=args.max_execute_tasks,
            cc_model=args.cc_model,
        ))
    else:
        from .animator import animate
        driver = _build_driver(args.atasco, args.repo, args.mode, args.speed,
                               args.rounds, args.seed,
                               execute_mode=args.execute,
                               max_execute_tasks=args.max_execute_tasks,
                               cc_model=args.cc_model)
        asyncio.run(animate(
            speed=args.speed,
            scale=args.scale,
            seed=args.seed,
            sound=not args.no_sound,
            driver=driver,
        ))
    print(f"\nConsejo finalizado.", file=sys.stderr)


if __name__ == "__main__":
    main()
