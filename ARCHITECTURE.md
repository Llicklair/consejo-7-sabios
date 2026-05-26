# El Consejo de los 7 Sabios

> Cuando estás atascado, convocas al consejo. 7 sabios con visiones opuestas debaten sobre tu proyecto, un juez sintetiza un plan, y se ejecuta — autónomamente o con tu aprobación.

---

## Los 7 sabios (incentivos OPUESTOS, no complementarios)

Si todos quieren "mejorar el código", coinciden en obviedades. Si tienen visiones que chocan, el debate produce señal real.

| # | Sabio | Defiende | Ataca | Avatar (Fase 2) |
|---|-------|----------|-------|-----------------|
| 1 | **Arquitecto** | Estructura, capas, abstracciones limpias | Código pegado, acoplamiento | Bardo |
| 2 | **Conservador** | "Si funciona no lo toques", estabilidad | Reescrituras innecesarias | Druida |
| 3 | **Modernizador** | Stack al día, patrones actuales | Deuda técnica, código viejo | Caballero |
| 4 | **Simplificador (YAGNI)** | Borrar código, menos abstracciones | Sobreingeniería, capas inútiles | Mago |
| 5 | **Guardián** | Validación, errores, edge cases, seguridad | Optimismo ingenuo | Pícaro |
| 6 | **Optimizador** | Velocidad, memoria, escalabilidad | Código bonito pero lento | Clérigo |
| 7 | **Embajador (UX/DX)** | Claridad de APIs, experiencia de uso | Código que solo el autor entiende | Berserker |

**Clave:** Conservador vs Modernizador y Simplificador vs Arquitecto son pares que naturalmente chocan. Eso es deseado.

---

## Flujo

```
[1] Snapshot de seguridad
    ├─ git checkout -b consejo/<timestamp>
    └─ git commit -am "Pre-consejo snapshot"

[2] Briefing compartido (1 llamada del orquestador)
    └─ Resumen del repo + el "atasco" descrito por el usuario

[3] Debate (máx 3 rondas, en paralelo dentro de cada ronda)
    ├─ Ronda 1 — Propuestas:  cada sabio propone 1-3 mejoras
    ├─ Ronda 2 — Críticas:    cada sabio critica 2 propuestas ajenas
    └─ Ronda 3 — Defensa:     cada sabio defiende o retira las suyas

[4] Juez sintetiza
    ├─ Agrupa propuestas similares
    ├─ Clasifica por blast radius: SAFE | MEDIUM | RISKY
    └─ Produce plan priorizado (JSON estructurado)

[5] Ejecución según modo (ver siguiente sección)

[6] Reporte final
    └─ consejo-report.md  (debate completo + tareas aplicadas + pendientes)
```

---

## Dos modos de operación

### Modo autónomo (`--mode auto`)

- Ejecuta SOLO tareas clasificadas como **SAFE**.
- **MEDIUM** y **RISKY** se guardan en el reporte para que decidas después.
- Cada tarea = 1 commit atómico con autor `Sabio: <nombre>`.
- Límite duro configurable (default: 10 tareas por sesión).
- Pensado para iteraciones rápidas mientras haces otra cosa.

**Qué cuenta como SAFE:**
- Renames consistentes con grep previo
- Formateo / linter
- Extracción de constantes / magic numbers
- Docstrings y comentarios
- Tests añadidos (no modificados)
- Dependencias actualizadas a parches (no minor/major)
- Movimiento de archivos sin cambiar imports rotos

### Modo human-in-the-loop (`--mode human`)

- Tras el debate, muestra el plan completo categorizado.
- Apruebas/rechazas/editas cada tarea (TUI o CLI interactiva).
- Las aprobadas se ejecutan en lotes con tu OK final.
- Ideal para cambios arquitectónicos o cuando el consejo todavía no se ha ganado tu confianza.

**Decisión de diseño:** ambos modos comparten exactamente el mismo flujo hasta el paso [5]. Solo cambia el filtro de qué se ejecuta. Eso permite empezar en `human` y graduar a `auto` cuando ves que el consejo decide bien.

---

## Red de seguridad (los dos modos)

1. Rama aislada `consejo/<timestamp>` — `main` nunca se toca.
2. Commit pre-consejo siempre (snapshot recuperable).
3. Cada tarea ejecutada → 1 commit atómico (revertir es trivial).
4. `consejo-report.md` con todo el debate + qué se aplicó + qué quedó pendiente.
5. El `merge` a `main` lo haces tú a mano tras revisar. **Nunca el consejo.**

---

## Stack sugerido

- **Claude Agent SDK** (Python o TS) — orquestador + 7 subagentes con `system_prompt` distinto por rol.
- **Modelos:**
  - Haiku 4.5 para los 7 sabios (paralelo, barato, suficiente para debate).
  - Opus 4.7 para juez y orquestador (síntesis y clasificación de riesgo).
- **Herramientas por sabio durante debate:** Read, Grep, Glob (solo lectura).
- **Herramientas del ejecutor:** Edit, Write, Bash (git).
- **Estado compartido:** `consejo-session-<id>.json` con propuestas, votos, plan, ejecución.

---

## Idioma del debate

**Decisión:** los 7 sabios debaten **internamente en inglés**; el reporte final se traduce al español antes de mostrarse. Razón empírica: los LLM (Claude incluido) responden con más consistencia, menos drift y menos errores estructurales cuando `system_prompt`, instrucciones y respuestas están en inglés.

### Pipeline de idiomas

```
Usuario describe el atasco (ES o EN)
    └─ Si llega en ES, traducción rápida a EN para el briefing
        └─ 7 sabios reciben prompts EN y debaten en EN
            └─ Juez sintetiza el plan en EN (JSON estructurado)
                └─ Traducción de los textos del plan a ES
                    └─ consejo-report.md bilingüe:
                       ├─ Resumen ejecutivo (ES) — lo que lee el usuario
                       └─ Transcripción original (EN) — para auditar lo dicho
```

### Implicaciones de implementación

- `prompts/sabio-<rol>.md` están en **inglés**.
- Nombres internos de los roles (en prompts y código de orquestación) son ingleses: `Architect, Conservative, Modernizer, Simplifier, Guardian, Optimizer, Ambassador`.
- El usuario sigue viendo los nombres en español (`Arquitecto, Conservador, …`) en el reporte renderizado y en la UI.
- Traducción ES→EN del atasco y EN→ES del plan: **Haiku 4.5** (rápido y suficiente para texto técnico).
- En el reporte se conserva la transcripción en EN para que sea auditable lo que **realmente dijo cada sabio** (la traducción puede atenuar matices).

---

## MVP (primera versión)

1. CLI: `consejo --mode auto|human "<descripción del atasco>"`
2. 7 prompts hardcodeados en `prompts/sabio-<rol>.md`.
3. Juez clasifica blast radius con heurísticas simples (archivos tocados, líneas cambiadas, existencia de tests).
4. Sin UI todavía — terminal + archivos markdown.
5. Funciona en cualquier repo git con un README.

---

## Visualización (Fase 2)

> Cuando el flujo headless ya funciona, se le pone piel: pixel-art retro renderizado en la propia terminal. La consola pasa de logs a mazmorra.

### La escena

Sala de mazmorra con muros de piedra, antorchas en las paredes, chimenea crepitando al fondo, mesa redonda de madera con 7 sillas. Los sabios entran en fila por la puerta, toman asiento, debaten en lengua rúnica, se levantan y salen. Al cerrarse la puerta, queda en disco `consejo-report.md`.

### Reparto: avatares vs personalidades

**Principio:** el aspecto del sprite **no revela** el rol técnico. Los avatares son arquetipos clásicos de fantasía (mago, caballero, berserker, etc.) y el emparejamiento con la personalidad técnica es deliberadamente desacoplado — incluso paradójico. El usuario no puede deducir quién es quién mirando: tiene que escuchar el debate (leerlo en el reporte).

El **color del sprite** identifica al personaje. El **color del glifo en su burbuja** identifica al rol técnico (paleta independiente). Con el tiempo, el observador atento aprende la correspondencia.

| Avatar       | Rasgo de silueta (32×32)         | Personalidad técnica       | Voz interior                                                          |
|--------------|----------------------------------|----------------------------|-----------------------------------------------------------------------|
| **Bardo**    | Sombrero con pluma + laúd        | **Arquitecto**             | *"Cada balada tiene estrofas, puentes, coros. Tu código también."*    |
| **Druida**   | Hojas + bastón + búho            | **Conservador**            | *"El bosque viejo ya sabe crecer solo."*                              |
| **Caballero**| Yelmo con cresta + escudo        | **Modernizador**           | *"Mi armadura es del año pasado. Tu stack también."*                  |
| **Mago**     | Sombrero puntiagudo + báculo     | **Simplificador (YAGNI)**  | *"El verdadero hechizo es no escribir el código."*                    |
| **Pícaro**   | Capucha baja + dagas             | **Guardián**               | *"Conozco los huecos. Por eso los tapo."*                             |
| **Clérigo**  | Capucha + maza + símbolo sagrado | **Optimizador**            | *"Cada ciclo de CPU es sagrado."*                                     |
| **Berserker**| Hacha enorme + cuernos           | **Embajador (UX/DX)**      | *"¡¡¡QUE EL USUARIO ENTIENDA EL BOTÓN!!!"*                            |

**Por qué los giros funcionan:** el Mago es el minimalista (paradoja del intelectual que borra código), el Berserker es el empático (la furia canalizada en defender al usuario), el Pícaro es el guardián (conoce todas las cerraduras → las refuerza), el Caballero es el rupturista (rompe el tópico de caballero conservador). El Druida → Conservador y Bardo → Arquitecto son los emparejamientos menos retorcidos, pero siguen sin ser el tópico fuerte.

**Implicación de diseño:** cada silueta debe leerse a 32×32 — los rasgos elegidos (sombrero puntiagudo, hacha enorme, cuernos, capucha baja, búho en hombro) son los que sobreviven a esa resolución.

### Máquina de estados (mapeada al flujo)

| Estado         | Origen en el flujo         | Qué se ve                                                  |
|----------------|----------------------------|------------------------------------------------------------|
| `ENTRANDO`     | tras snapshot [1]          | Sabios cruzan el corredor hacia la sala                    |
| `SENTÁNDOSE`   | tras briefing [2]          | Toman lugar en la mesa                                     |
| `DEBATE_R1`    | ronda 1 — propuestas       | Burbujas verdes con glifos sobre cada sabio                |
| `DEBATE_R2`    | ronda 2 — críticas         | Burbujas rojas cruzan la mesa entre sabios                 |
| `DEBATE_R3`    | ronda 3 — defensa          | Burbujas amarillas, sabios se inclinan al hablar           |
| `JUEZ`         | síntesis [4]               | La chimenea arde más fuerte, todos miran al fuego          |
| `ACUERDO`      | plan listo                 | Asentimiento unísono                                       |
| `LEVANTÁNDOSE` | inicio ejecución [5]       | Empujan la silla, se ponen de pie                          |
| `SALIENDO`     | ejecución en curso         | Caminan hacia la puerta                                    |
| `REPORTE`      | fin [6]                    | Fade-out + ruta del `consejo-report.md` impresa            |

### Desacople animación / debate real

La animación corre en un hilo, el debate vía API en otro. Se comunican por un bus de eventos (`asyncio.Queue`).

- Si el debate termina antes que la animación → la TUI completa los frames pendientes a velocidad normal.
- Si la animación termina antes que el debate → frames de idle (un sabio bebe agua, otro mira la chimenea, las antorchas titilan).
- Nunca se acelera ni se salta animación por prisa: el ritmo lo manda la escena.

### Idioma inventado: glifos rúnicos

- Set fijo de **16–32 glifos** pixel-art (sprites 8×8 o 16×16) inspirados en futhark / élfico.
- Mapeo determinista `texto_real → glifos`: hash por sílaba → índice de glifo. Misma propuesta = misma secuencia rúnica (reproducible).
- Color del glifo según el sabio que habla (paleta por rol).
- Ilegible a propósito: el debate "de verdad" se lee en `consejo-report.md`. La pantalla es pura atmósfera.

### Stack de renderizado

- **`rich-pixels`** (o **chafa** como backend) — renderiza PNGs a half-blocks (`▀`) con truecolor: 2 píxeles por celda de terminal.
- **Textual** — sólo para el ciclo de eventos, layout y entrada de teclado (no para los sprites).
- **Sprites en PNG** diseñados en Aseprite / Piskel. Resolución objetivo: 160×100 píxeles "lógicos" (≈ 160×50 celdas de terminal).
- **Paleta retro** de 16 colores estilo PICO-8 / NES, sesgada a azules-grises de mazmorra y naranjas de fuego.

### Assets necesarios

| Tipo           | Detalle                                                                                            |
|----------------|----------------------------------------------------------------------------------------------------|
| Tileset sala   | Muros, suelo, puerta, chimenea (3-4 frames de fuego), antorchas (2 frames)                         |
| Mesa y sillas  | Mesa redonda, 7 sillas en perspectiva 3/4                                                          |
| 7 sabios       | Silueta distinguible por rol (regla, escudo, engranaje, libro, lupa, balanza, pluma). Frames: idle, walk, talk, stand-up |
| Burbujas       | Marco pixel con cola hacia el sabio, 3 colores (verde / rojo / amarillo)                           |
| Glifos rúnicos | 16-32 sprites pequeños                                                                             |
| Efectos        | Humo de antorcha, brasas, fade in / out                                                            |

### Requisitos de terminal

- Truecolor (24-bit) + Unicode.
- Windows Terminal ✅, WezTerm ✅, iTerm2 ✅, PowerShell 7 + Windows Terminal ✅.
- `cmd.exe` clásico ❌ → degrada a modo headless con logs.
- Fuente monoespaciada de altura/anchura consistente (Cascadia Code, JetBrains Mono).

### Qué NO entra en Fase 2

- Sonido (rompería "todo en terminal" sin shellear a un reproductor).
- Interactividad durante el debate (los sabios no responden al teclado mientras debaten; sólo `Ctrl-C` aborta).
- Cambiar layout en runtime — la mesa es fija.
- 3D, parallax, raycasting — pixel-art plano, 2D top-down 3/4.

---

## Decisiones abiertas

- ¿Los 7 sabios son fijos o configurables por proyecto? (Ej. añadir "Sabio de Accesibilidad" para apps web).
- ¿Debate en texto libre o estructurado (JSON con `proposal/critique/vote`)?
- ¿Memoria entre sesiones (aprende qué propuestas suelen aprobarse) o stateless cada vez?
- ¿El juez puede convocar una "ronda extra" si detecta desacuerdo fuerte, o siempre 3 rondas fijas?
- ¿Qué pasa si el modo autónomo no encuentra ninguna tarea SAFE? ¿Reporta y se va, o degrada a modo human?
- ¿Añadir un 8º sabio **Empirista** (exige evidencia: benchmarks, logs, métricas, quejas reales de usuario) como antídoto a debates puramente especulativos? Implica replantear la mesa de 7 a 8 sillas en Fase 2.

---

## Riesgos conocidos

- **Token cost:** 7 agentes × 3 rondas × repo grande = caro. Mitigación: briefing compartido una vez, Haiku para los sabios.
- **Consensus mush:** todos acaban de acuerdo en obviedades. Mitigación: incentivos opuestos + obligación de criticar en ronda 2.
- **Análisis parálisis:** proponen reescribir medio proyecto. Mitigación: límite duro de tareas por sesión + clasificación por blast radius.
- **Cambios autónomos rotos:** el modo auto rompe algo y no te enteras. Mitigación: rama aislada + commit por tarea + nunca tocar main.
