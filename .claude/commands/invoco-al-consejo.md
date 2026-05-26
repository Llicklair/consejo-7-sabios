---
description: Invoca al Consejo de los 7 Sabios para debatir un atasco del proyecto actual
---

El usuario quiere convocar al Consejo de los 7 Sabios. El atasco viene en
$ARGUMENTS (si está vacío, pregunta brevemente al usuario qué quiere
debatir o usa "Mejora general del proyecto" como default).

Ejecuta el consejo en modo mock + headless desde el repo
`d:\consejo-7-sabios`:

```bash
cd d:/consejo-7-sabios && PYTHONPATH=src .venv/Scripts/python.exe -m consejo.cli "$ARGUMENTS" --mode mock --rounds 5 --speed 50 --no-ui
```

Después:
1. Encuentra el `consejo-report-*.md` más reciente generado en el cwd
2. Lee el reporte y muestra al usuario:
   - El resumen ejecutivo (sección "Resumen ejecutivo")
   - La tabla del plan priorizado (las primeras 6 filas)
   - Si hay disensos no resueltos, mencionarlos
3. Pregunta al usuario si quiere:
   a) Ejecutar las tareas SAFE en auto (re-correr con `--execute auto`)
   b) Ver la animación completa en el terminal (re-correr sin `--no-ui`)
   c) Ajustar las rondas o el atasco

NO modifiques el código del proyecto durante esta invocación — el consejo
solo propone y reporta. La ejecución es opt-in vía paso 3a.

Si el comando falla (p. ej. el venv no existe), informa al usuario y
sugiere `python -m venv .venv && .venv\Scripts\pip install -e .`.
