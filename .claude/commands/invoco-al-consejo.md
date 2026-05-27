---
description: Invoca al Consejo de los 7 Sabios para debatir un atasco del proyecto actual
---

El usuario quiere convocar al Consejo de los 7 Sabios. El atasco viene en
$ARGUMENTS (si está vacío, pregunta brevemente al usuario qué quiere
debatir o usa "Mejora general del proyecto" como default).

## Antes de lanzar — avisa al usuario

El modo `claude-code --consensus` es el debate REAL (no mock):
- Se lanzan 9 subprocesos `claude -p` (semáforo a 3 simultáneos)
- Round-robin turn-by-turn hasta unanimidad o cap de 20 rondas
- En atascos serios suele converger en ~11 rondas (~99 turnos)
- Duración típica: 30-60+ minutos wall time
- Coste real con tokens del usuario; sin cap

Si el atasco es trivial, sugiere `--consensus-rounds 5` para acortar.
Si el atasco es serio, el default (20) está bien.

## Lanza el consejo

Desde `d:\consejo-7-sabios`, modo claude-code + consensus + headless
(la animación pygame no se renderiza en este chat — los logs por turno
sí muestran el progreso):

```bash
cd d:/consejo-7-sabios && PYTHONPATH=src .venv/Scripts/python.exe -m consejo.cli "$ARGUMENTS" --mode claude-code --consensus --consensus-rounds 20 --cc-model sonnet --no-ui
```

**Lánzalo en background** (`run_in_background: true` en Bash) y monta un
Monitor sobre el log para reportar progreso por turno sin esperar
bloqueando. Patrón de evento útil:

```
tail -F <log-path> 2>/dev/null | grep -E --line-buffered "turn [0-9]+ . r[0-9]|Consenso|reporte:|RuntimeError"
```

## Después

1. Encuentra el `consejo-report-*.md` más reciente generado en el cwd.
2. Lee el reporte y muéstralo al usuario:
   - Resumen ejecutivo (sección "Resumen ejecutivo")
   - Tabla del plan priorizado
   - Visión estratégica (headline + 1 párrafo de `where_to_take_it`)
   - Disensos no resueltos si los hay
3. Pregunta al usuario si quiere:
   a) Ejecutar las tareas SAFE en auto (`--execute auto`)
   b) Re-correr con Opus para más profundidad (`--cc-model opus`)
   c) Ajustar el atasco o las rondas

NO modifiques el código del proyecto durante esta invocación — el consejo
solo propone y reporta. La ejecución es opt-in vía paso 3a.

Si el comando falla (p. ej. el venv no existe, falta `claude` CLI),
informa al usuario y sugiere los fixes apropiados.

## Si el usuario prefiere la animación

Dile que en lugar del slash command puede usar la VSCode task
"Consejo: invocar (claude-code, CONSENSUS conversacional)" (Ctrl+Shift+P
→ Tasks: Run Task) — eso abre un terminal nuevo en VSC con la animación
TUI corriendo en tiempo real durante el debate.
