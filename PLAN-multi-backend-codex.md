# Plan — Multi-backend driver (Claude Code + Codex)

## Contexto

Hoy el consejo está acoplado al CLI `claude -p`. Queremos:
1. Bajar coste/tokens (Codex como alternativa más barata o cross-vendor).
2. Mejorar calidad del debate (mezcla de modelos = menos sesgo monocultivo).
3. No romper nada de lo que ya funciona con Claude Code.

## Hallazgos del código actual

- `claude_code_driver.py:47` — `_build_claude_args()` ya está aislado.
- `claude_code_driver.py:590` — `_spawn_claude()` es el único punto que toca el subprocess CLI.
- Todos los callers (`propose_one_sage:730`, `critique_one_sage:781`, `judge_synthesis:833`, `consensus_dialogue:1087`) invocan `_spawn_claude` con la misma firma.
- `_SPAWN_SEM = asyncio.Semaphore(3)` en `:723` cabe igual en cualquier backend.
- El retry sin schema (`:679`) es específico de la quirk de `claude -p` con `--json-schema`. Codex no la tendrá → ese branch queda dentro de `ClaudeCodeDriver`.
- `cc_model` ya viaja CLI → orchestrator → driver. Reusable.
- Sages tienen `id` estable (`arquitecto`, `conservador`, etc.) — sirve para asignar backend por sabio si en el futuro queremos mezclar.

## Decisiones de diseño

### 1. Protocolo abstracto, no clases pesadas

```python
class SageDriver(Protocol):
    name: str                      # "claude-code" | "codex"
    def available(self) -> bool: ...
    async def spawn(
        self, *,
        user_msg: str,
        system_prompt: str,
        schema: dict,
        repo: Path,
        model: str,
        allowed_tools: str,
        timeout_s: float,
    ) -> dict: ...                 # devuelve el JSON inner ya parseado
```

Cada backend implementa `spawn` y normaliza errores con las `DriverError` ya existentes (`DriverTimeoutError`, `DriverProcessError`, `DriverInvalidResponseError`). Los callers del módulo (`propose_one_sage`, etc.) reciben el driver como parámetro inyectado.

### 2. Module-level `_active_driver`, no global mutable

En lugar de pasar `driver` por 5 firmas, exponer:
```python
_active_driver: SageDriver | None = None
def set_driver(d: SageDriver) -> None: ...
def get_driver() -> SageDriver: ...
```
Set en `orchestrator.py` antes del `await consensus_dialogue(...)`. Tests pueden swapear sin tocar firmas.

### 3. Schema en Codex: instrucción inline, no flag CLI

`codex exec` no tiene `--json-schema`. Estrategia:
- Inyectar el schema en el system prompt como bloque "MUST return JSON matching this schema: ...".
- Parsear la respuesta con `_extract_json_object` (que ya es heurístico y maneja markdown fences).
- Si falla parsing, hacer un retry pidiendo "raw JSON only, no prose".
- El `--json-schema` strict-mode bug específico de claude (memoria `claude CLI empty result`) NO existe en Codex → no replicamos ese branch.

### 4. `--backend` ortogonal a `--cc-model`

```
--backend claude-code   --cc-model sonnet|opus
--backend codex         --cc-model gpt-5-codex|gpt-5
```
`--cc-model` mantiene el nombre por compatibilidad. La interpretación del valor depende del backend.

### 5. Pre-flight check

Antes de instanciar el consejo:
```python
driver = build_driver(args.backend)
if not driver.available():
    parser.error(f"--backend {args.backend} requires CLI in PATH; not found.")
```
Esto evita perder 30 min de debate por un PATH mal configurado.

## Plan de implementación

### Fase 1 — Refactor sin cambios funcionales (task #1, #2)
1. Definir `SageDriver` Protocol en `src/consejo/driver_protocol.py`.
2. Crear `src/consejo/drivers/claude_code.py` con `ClaudeCodeDriver` que envuelve todo el código actual de `_spawn_claude` + helpers.
3. En `claude_code_driver.py`, los wrappers (`propose_one_sage`, etc.) llaman a `get_driver().spawn(...)` en lugar de `_spawn_claude(...)` directamente.
4. `orchestrator.py` setea `set_driver(ClaudeCodeDriver())` al arrancar.
5. Test: lanzar mock + tarea real corta, confirmar idéntico al baseline.

### Fase 2 — Codex driver (task #3)
1. Crear `src/consejo/drivers/codex.py` con `CodexDriver`.
2. Comando base: `codex exec --model {model} --cd {repo}` con stdin = user_msg, system prompt prepended.
3. Schema → bloque inline en system prompt.
4. Parsing tolerante con retry "raw JSON only".
5. Mapear errores a las `DriverError` existentes para que el orchestrator no distinga.

### Fase 3 — Plumbing CLI (task #4)
1. `--backend {claude-code,codex}` en `cli.py:174`, default `claude-code`.
2. Propagar a `_run_with_ui` y `_build_driver` (renombrarlo a `_build_orchestrator` para no chocar con SageDriver).
3. Pre-flight: `driver.available()` antes de empezar.
4. Mensajes de error específicos: si `--backend codex` y no hay `codex` en PATH → mensaje claro.

### Fase 4 — Tasks.json y verificación (task #5)
1. Nueva entrada `Consejo: mejorar (Codex)` clonando la "auto" con `--backend codex`.
2. Smoke test: misma pregunta corta en ambos backends, confirmar que ambos producen reporte válido.
3. La Ctrl+Shift+B default sigue siendo Claude+sonnet+8 rondas.

## Lo que NO se toca en este plan

- El semáforo `_SPAWN_SEM = 3` se mantiene global (vale igual para Codex).
- `_is_unanimous`, `_apply_plan_diff`, schemas, prompts: intactos.
- Métricas: se siguen recordando con `kind="subprocess"` (añadiremos campo `backend` si hace falta luego).
- **No** se mezclan backends por sabio en esta iteración. Todos los sabios usan el mismo backend por sesión. Mezclar es una fase posterior si esto funciona.

## Riesgos

- **Codex puede no estar en PATH**: ya cubierto con pre-flight.
- **Schema enforcement débil en Codex**: el retry heurístico debería bastar; si no, fallback documentado a "abstain this round".
- **Diferente coste/latencia**: Codex podría ser más lento o más caro de lo esperado. Mitigación: la misma sesión `--consensus-rounds 8` aplica igual; si Codex tarda más, simplemente alcanzamos más rondas con menos vueltas reales.
- **Output format diff**: claude-code devuelve `{"type":"result","result":"..."}`; Codex emite directo. El branch va dentro de cada driver, transparente al caller.

## Estimación

- Fase 1: ~30 min (mecánico).
- Fase 2: ~45 min (probar `codex exec` en seco primero).
- Fase 3: ~15 min.
- Fase 4: ~15 min.

Total: ~1h45min de trabajo seguido. Cada fase es independiente y se puede commitear por separado.
