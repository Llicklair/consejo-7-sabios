# El Consejo de los 7 Sabios

> Cuando estás atascado, convocas al consejo. 7 sabios con visiones opuestas
> debaten sobre tu proyecto, firman cuando llegan al 100% de acuerdo, un juez
> sintetiza el plan, y se ejecuta — autónomamente o con tu aprobación.

![Escena del Consejo](docs/demo-scene.png)

---

## Qué es esto

Un sistema de revisión técnica multi-agente con **incentivos opuestos por
diseño**: si todos los agentes quieren "mejorar el código", coinciden en
obviedades; si tienen visiones que chocan, el debate produce señal real.

Los 7 sabios (cada uno con expertise específica + un foil natural):

| Sabio | Defiende | Foil |
|-------|----------|------|
| **Architect** | Estructura, capas, abstracciones | Simplifier |
| **Conservative** | Estabilidad, "no toques lo que funciona" | Modernizer |
| **Modernizer** | Stack al día, patrones actuales | Conservative |
| **Simplifier (YAGNI)** | Borrar código, menos abstracciones | Architect |
| **Guardian** | Validación, errores, seguridad | Optimizer |
| **Optimizer** | Velocidad, memoria, escalabilidad | Guardian |
| **Ambassador (UX/DX)** | Claridad de APIs, ergonomía | Architect |

Cada sesión, los 7 se sientan **aleatoriamente** alrededor de la mesa.

![Debate en curso](docs/demo-debate.png)

---

## Mecánica del debate

1. **Análisis**: cada sabio escanea el repo desde su expertise (libro
   flotante en pantalla mientras pasa páginas)
2. **Propose**: ronda 1, cada sabio propone 1-3 mejoras
3. **Sign or reject**: rondas 2+, cada sabio re-lee TODAS las propuestas y
   firma SOLO si está 100% de acuerdo; si no, añade enmiendas
4. **Convergencia**: cuando los 7 firman → juez sintetiza. Si supera 30
   rondas, el umbral baja gradualmente
5. **Ejecución**: 2 modos
   - `auto`: el consejo crea una rama `consejo/<ts>` y commitea las tareas
     SAFE — `master` jamás se toca
   - `manual`: solo genera el reporte priorizado para revisión humana

![Acuerdo unánime](docs/demo-agreement.png)

---

## Quick start

```powershell
git clone https://github.com/Llicklair/consejo-7-sabios
cd consejo-7-sabios
python -m venv .venv
.venv\Scripts\pip install -e .

# Genera assets procedurales (sprites + sonidos)
python -m consejo.sprites
python -m consejo.sound

# Lanza el consejo en modo demo (sin API)
consejo "El módulo auth tiene 800 líneas y los tests son frágiles" `
  --mode mock --rounds 3 --speed 0.7

# Modo headless (solo logs, sin animación)
consejo "..." --no-ui --mode mock

# Auto-execute (crea rama + commits SAFE en un repo git)
consejo "..." --mode mock --execute auto
```

Requiere terminal con truecolor + Unicode: Windows Terminal, WezTerm,
iTerm2. `cmd.exe` clásico no.

---

## Modo real (con Claude API)

```powershell
$env:ANTHROPIC_API_KEY="sk-ant-..."
consejo "tu atasco en español" --mode real --rounds 3
```

- Sabios usan **Claude Haiku 4.5** (paralelo, barato)
- Juez usa **Claude Opus 4.7** (síntesis y clasificación de riesgo)
- Traducción ES→EN del atasco al inicio y EN→ES del plan al final
- El reporte incluye transcripción original (EN) para auditar lo dicho

---

## Pixel-art en terminal

La sala es una mazmorra con:
- Chimenea con fuego de 3 frames cicládos (chisporroteo)
- Halos cálidos que pulsan sobre antorchas + braziers
- Mesa enorme con palantir + planta brillante + vela + pergaminos
- Suelo de madera frente a la chimenea, suelo de piedra con 4 variantes
- 4 librerías grandes contra los muros laterales
- Runa mágica brillante en el suelo
- Decoración: anvil, barril, cajas, cofres, calaveras, banners

![Análisis con libro flotante](docs/demo-analyzing.png)

Estados de la escena (10):
`ENTRANDO → SENTANDOSE → ANALIZANDO → DEBATE×N → JUEZ → ACUERDO → LEVANTANDOSE → SALIENDO → REPORTE`

Cada estado tiene sus propios sonidos procedurales (sin assets externos):
crackle de chimenea, page turn, magic sparkle, palantir hum, seal thump,
chair creak, door creak, quill writing. Vía `pygame.mixer` con fallback a
`winsound` stdlib.

---

## Arquitectura

Ver [ARCHITECTURE.md](ARCHITECTURE.md) para el documento completo.

```
src/consejo/
├── sages.py         — Los 7 sabios (ES + EN)
├── sprites.py       — Sprites/tiles procedurales (PIL)
├── scene.py         — Composición de escena dungeon
├── animator.py      — Bucle de animación + bus de eventos
├── states.py        — Máquina de estados (ENTRANDO..REPORTE)
├── orchestrator.py  — Consejo real (mock + scaffolding anthropic)
├── translator.py    — Pipeline ES↔EN
├── executor.py      — Modo auto: git branches + commits SAFE
├── sound.py         — Sonido procedural polifónico
├── glyphs.py        — Idioma rúnico inventado
├── renderer.py      — rich-pixels → terminal
└── cli.py           — `consejo` entry point

prompts/
├── sage_template.md — System prompt unificado (interpolado por sabio)
└── judge.md         — Síntesis del juez
```

---

## Red de seguridad (modo auto)

1. ✅ Rama aislada `consejo/<ts>` — `master` jamás se toca
2. ✅ Snapshot pre-consejo si había cambios sin commitear
3. ✅ Cada tarea SAFE = 1 commit atómico (revertir trivial)
4. ✅ Autor `Sabio: <Name>` — auditabilidad por origen
5. ✅ Solo SAFE auto-ejecutables; MEDIUM/RISKY quedan en reporte
6. ✅ Cap duro (`--max-execute-tasks N`, default 10)
7. ✅ El merge a `master` lo haces TÚ a mano tras revisar

---

## Estado

- **Fase 2 (visual + audio)**: ✅ completo
- **Fase 1 (consejo real)**: ✅ mock end-to-end · ⏳ real-mode (anthropic SDK) con scaffolding listo, falta debugging con API key real
- **Real executor agent** (Claude implementa SAFE tasks de verdad, no
  commits vacíos): ⏳ pendiente
- **Versión inglesa del repo**: ⏳ planeada

---

## Licencia

MIT (pendiente de añadir el archivo).
