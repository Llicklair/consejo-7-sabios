# Plan de arreglo — crash del juez (exit 4294967295)

## Diagnóstico revisado

**Tu hipótesis #2 (schema demasiado grande) queda descartada.** Mido:
- `JUDGE_SCHEMA` = 2.2 KB
- `PROPOSAL_SCHEMA` = 950 B

Ambos muy por debajo de cualquier límite plausible del flag `--json-schema`.

**Hipótesis revisadas, ordenadas por probabilidad:**

1. **Agotamiento de recursos (OOM/job-object kill).** Confirmado: PID 876 (`claude.exe`, **349 MB RSS**) + PID 28316 (`node`) siguen vivos desde las 03:24:36, exactamente la sesión que falló. Con 9 sabios en paralelo + 2 zombies, Windows mata subprocesos sin stderr. **Exit `4294967295` == `-1` unsigned == proceso terminado externamente** (signature clásica de OOM / `TerminateProcess`, no de un fallo lógico de Claude CLI).
2. **`proposals_by_sage` vacío silenciosamente.** [`orchestrator.py:528`](src/consejo/orchestrator.py#L528) guarda críticas (`if cc_rounds >= 2 and proposals_by_sage`) pero [`orchestrator.py:548`](src/consejo/orchestrator.py#L548) llama al juez sin guard. Si los 9 sabios pelean por recursos y todos lanzan excepción, `by_sage = {}` y el juez recibe `<proposals_by_sage>{}</proposals_by_sage>` → respuesta vacía o crash del schema.
3. **Sin límite de concurrencia.** [`gather_all_proposals`](src/consejo/claude_code_driver.py#L464) hace `asyncio.create_task` para `ALL_SAGES` (9) sin `Semaphore`. Lo mismo en [`gather_all_critiques`](src/consejo/claude_code_driver.py#L512). Cada `claude -p` levanta un proceso node + un proceso claude → 18+ procesos compitiendo con los zombies.

## Plan de arreglo

### A — Limpieza inmediata (manual, antes de cualquier reintento)
```powershell
Stop-Process -Id 876,28316 -Force
Get-Process claude,node -ErrorAction SilentlyContinue | Select Id,Name,StartTime
```
Verifica que no queda nada de la sesión 03:24. **Ojo:** confirma que PID 876 NO es la sesión Claude Code que tienes abierta ahora mismo (mira `StartTime`).

### B — Guard del juez (1 línea, evita crash silencioso)
En [`orchestrator.py`](src/consejo/orchestrator.py) justo antes de la llamada al juez (~línea 548):

```python
if not proposals_by_sage:
    raise RuntimeError(
        "Todos los sabios fallaron en la ronda 1 (proposals_by_sage vacío). "
        "Probable causa: agotamiento de procesos. Cierra claude.exe huérfanos "
        "y reintenta. Revisa Task Manager si persiste."
    )
```

### C — Semaphore de concurrencia (el fix real)
En [`claude_code_driver.py:464`](src/consejo/claude_code_driver.py#L464) y `:512`, envuelve cada `propose_one_sage` / `critique_one_sage` con un semáforo a nivel módulo:

```python
_SPAWN_SEM = asyncio.Semaphore(3)  # máx 3 claude -p simultáneos

async def _bounded_propose(sage, atasco, repo, round_num, model):
    async with _SPAWN_SEM:
        return await propose_one_sage(sage, atasco, repo, round_num, model)
```

Y usa `_bounded_propose` en el dict comprehension de `gather_all_proposals`. Tiempo total sube ~3× pero la sesión no se inmola.

### D — Capturar stderr aunque returncode sea raro
En [`_spawn_claude`](src/consejo/claude_code_driver.py#L384), cuando el proceso muere con código negativo/anómalo en Windows, `stderr` suele venir vacío porque `TerminateProcess` no le da tiempo a flushear. Dump del wrapper completo:

```python
if proc.returncode != 0:
    err = stderr.decode("utf-8", errors="replace")[:2000]
    diag = {
        "returncode": proc.returncode,
        "returncode_signed": proc.returncode - 2**32 if proc.returncode > 2**31 else proc.returncode,
        "stderr_len": len(stderr),
        "stdout_head": stdout[:500].decode("utf-8", errors="replace"),
    }
    raise RuntimeError(f"claude CLI failed: {diag}\n--stderr--\n{err}")
```

Esto te da `returncode_signed: -1` legible y muestra si stdout llevaba algo antes de morir.

### E — Pre-flight check (antes de lanzar la sesión)
En el CLI, antes de instanciar el debate:

```python
import psutil
zombies = [p for p in psutil.process_iter(['name','create_time'])
           if p.info['name'] in ('claude.exe','claude') and
           time.time() - p.info['create_time'] > 600]  # >10 min
if zombies:
    print(f"⚠️  {len(zombies)} claude.exe huérfanos (>10min). Cierra con: "
          f"Stop-Process -Id {','.join(str(p.pid) for p in zombies)} -Force")
    sys.exit(1)
```

## Orden recomendado de aplicación

1. **A** (manual ya) → mata zombies, prueba un debate de 1 sabio para verificar que Claude CLI funciona aislado.
2. **B + D** (10 min de código) → si vuelve a crashear tienes mensaje legible.
3. **C** (15 min) → el fix arquitectural; aplica solo si A+B+D confirman que era resource pressure.
4. **E** (opcional) → cinturón + tirantes para futuras sesiones.

## Lo que NO toques aún

- El schema `strategic_vision` (no es el culpable, tu hipótesis #2 queda descartada por las mediciones).
- El parser JSON / wrapper handling (los logs muestran que ni siquiera llegó a responder — no es un bug de parsing).
- El prompt del juez (mismo motivo).
