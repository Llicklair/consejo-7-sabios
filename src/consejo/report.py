"""Generador de `consejo-report.md` fake para la demo de Fase 2.

Cuando el animador llega al estado REPORTE, llama a `generate_fake_report()`
y obtiene la ruta de un markdown plausible: el debate completo en lengua
humana (no glifos), las propuestas, críticas, defensas, síntesis del juez
y plan priorizado. Es el archivo que el usuario leerá DESPUÉS de cerrar
la mazmorra.

En Fase 1, este módulo será reemplazado por uno que recoge el debate real
emitido por los 7 subagentes Claude. La FORMA del markdown es idéntica.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

DEFAULT_ATASCO = (
    "El módulo de autenticación tiene 800 líneas, los tests mockean la base "
    "de datos, y cada cambio rompe algo distinto. ¿Por dónde se ataca?"
)


# Debate de muestra. Cada sabio habla con la voz de su rol técnico (no su
# arquetipo visual). El reparto avatar↔rol queda invisible en el reporte
# a propósito — la verdad es técnica.
_DEBATE_R1 = """\
### Ronda 1 · Propuestas

**Arquitecto** — *"Dividir `auth.py` en tres capas: `handlers/`, `services/`, `repository/`. La mezcla actual oculta el flujo y hace que cualquier cambio cruce las tres responsabilidades a la vez."*

**Conservador** — *"No tocar la lógica core. El problema no es el código de auth, es la suite de tests. Refactorizar los tests primero; el código de producción lleva 3 años sin un bug serio."*

**Modernizador** — *"Sustituir el JWT casero por `python-jose` v3 o `authlib`. La cripto rodando a mano siempre es deuda."*

**Simplificador (YAGNI)** — *"Borrar los 4 wrappers que solo delegan al siguiente. La API pública de `auth` debería ser 3 funciones: `login`, `verify`, `logout`."*

**Guardián** — *"Añadir validación estricta de claims, audit log de cada `verify_token`, y un fuzzer básico sobre el parser. Lo que está sin tests es la zona de mayor riesgo, no la mejor mantenida."*

**Optimizador** — *"`verify_token` se llama en cada request. Cachear el resultado en memoria con TTL = `exp_claim - now - 5s`. Mide antes: si está bajo 1ms, ignorar."*

**Embajador (UX/DX)** — *"El cliente recibe `AuthError: 401` sin más. Crear un catálogo de códigos (`AUTH_EXPIRED`, `AUTH_REVOKED`, `AUTH_SCOPE_MISSING`) y documentarlos. Sin esto, los integradores adivinan."*
"""

_DEBATE_R2 = """\
### Ronda 2 · Críticas

**Arquitecto → Simplificador:** *"Si borras los wrappers, los callsites se llenan de detalle de bajo nivel. Lo que llamas 'simplificar' es 'mover la complejidad al consumidor'."*

**Conservador → Modernizador:** *"Migrar a librería externa = importar sus CVEs futuros + posibles cambios de API. ¿Quién mantiene esto en dos años?"*

**Modernizador → Conservador:** *"'No lo toques' es exactamente cómo llegamos a 800 líneas y tests frágiles. Estabilidad ≠ inmovilidad."*

**Guardián → Optimizador:** *"Cachear `verify_token` en memoria abre ventana de revocación. Si un token se invalida, cada nodo lo seguirá aceptando hasta TTL. ¿Es asumible?"*

**Simplificador → Arquitecto:** *"Tres capas en 800 líneas son tres carpetas con 270 líneas cada una. La 'estructura' que pides es más boilerplate que valor."*

**Embajador → Arquitecto:** *"Los códigos de error que propongo importan más que la estructura interna. El cliente no ve `handlers/`, ve el JSON. Prioridad."*

**Optimizador → Guardián:** *"Audit log de cada `verify_token` = escribir un disco/red por request. Eso sí mata la latencia."*
"""

_DEBATE_R3 = """\
### Ronda 3 · Defensa

**Arquitecto** — Mantiene la división en capas pero acepta empezar por extraer **solo** `repository/` para aislar acceso a DB. Las otras dos capas quedan para iteración futura.

**Conservador** — Retira "no tocar nada"; reformula a: refactorizar tests **antes** que código de producción. Acepta cambios de auth solo si hay tests de integración reales.

**Modernizador** — Retira la migración total. Propone aislar la verificación criptográfica en un módulo `_crypto.py` con interfaz mínima, para poder swapear más adelante sin reescribir todo.

**Simplificador** — Mantiene el borrado de wrappers pero acepta que la API pública crezca de 3 a 5 funciones (incluyendo `refresh` y `revoke` explícitas).

**Guardián** — Mantiene audit log pero solo para `verify_token` que fallen, no los exitosos. Mantiene fuzzer del parser JWT como tarea aislada.

**Optimizador** — Mantiene cacheo, con un canal de invalidación pub/sub para revocación instantánea. Aprende del Guardián.

**Embajador** — Mantiene catálogo de códigos. Sin cambios.
"""

_JUEZ = """\
### El juez sintetiza

Convergencia: 4 de 7 sabios apuntan al **acoplamiento entre tests y código de producción** como raíz. El resto identifica problemas reales pero secundarios.

#### Plan priorizado

| # | Tarea | Sabio origen | Blast radius | Modo auto |
|---|-------|--------------|--------------|-----------|
| 1 | Catálogo de códigos de error en `AuthError` con documentación | Embajador | **SAFE** | ✅ |
| 2 | Audit log solo en `verify_token` fallidos (no exitosos) | Guardián | **SAFE** | ✅ |
| 3 | Extraer constantes de TTL, scopes y claims al top del módulo | Simplificador | **SAFE** | ✅ |
| 4 | Refactor de tests para no mockear la DB (usar SQLite temporal) | Conservador | **MEDIUM** | ⛔ (manual) |
| 5 | Aislar verificación cripto en `_crypto.py` con interfaz mínima | Modernizador | **MEDIUM** | ⛔ (manual) |
| 6 | Cachear `verify_token` + canal pub/sub de revocación | Optimizador + Guardián | **MEDIUM** | ⛔ (manual) |
| 7 | Extraer `repository/` para aislar acceso a DB del resto de auth | Arquitecto | **RISKY** | ⛔ (revisar) |
| 8 | Fuzzer básico sobre parser JWT | Guardián | **RISKY** | ⛔ (revisar) |

#### Disensos no resueltos

- **Cachear `verify_token`**: el Guardián cedió pero la ventana de revocación quedó como riesgo aceptado por consenso 5-2. Decisión: implementar **con** canal de invalidación obligatorio.
- **División en capas completa**: Arquitecto vs Simplificador. Aplazado: revisar tras tareas 4 y 5.
"""

_APPLIED = """\
### Tareas aplicadas (modo auto)

Commit `consejo/<timestamp>`:

- ✅ `feat(auth): catálogo de códigos AuthError documentado` — Embajador
- ✅ `feat(auth): audit log en verify_token fallidos` — Guardián
- ✅ `refactor(auth): extracción de constantes TTL y scopes` — Simplificador

3 tareas aplicadas. 5 tareas pendientes para revisión manual.
"""

_FOOTER = """\
### Próximos pasos

Las tareas MEDIUM y RISKY del plan quedan en este reporte para tu decisión.
Recomendación del juez: empezar por la #4 (refactor de tests), porque
desbloquea todas las demás.

> *Generado por El Consejo de los 7 Sabios — Fase 2 demo (sin debate real).*
> *El debate real ocurrirá cuando Fase 1 conecte el orquestador Claude al bus de eventos.*
"""


def generate_fake_report(out_path: Path | None = None, atasco: str = DEFAULT_ATASCO) -> Path:
    """Escribe un consejo-report.md plausible en `out_path` y devuelve la ruta.

    Si `out_path` es None, usa `consejo-report-<timestamp>.md` en el cwd.
    """
    ts = datetime.now()
    if out_path is None:
        out_path = Path.cwd() / f"consejo-report-{ts:%Y%m%d-%H%M%S}.md"

    content = f"""# Consejo de los 7 Sabios — Reporte

**Sesión:** `consejo/{ts:%Y%m%d-%H%M%S}`
**Modo:** auto
**Atasco planteado:**

> {atasco}

---

{_DEBATE_R1}

---

{_DEBATE_R2}

---

{_DEBATE_R3}

---

{_JUEZ}

---

{_APPLIED}

---

{_FOOTER}
"""
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera un consejo-report.md fake.")
    parser.add_argument("--out", type=Path, default=None,
                        help="Ruta de salida (default: consejo-report-<timestamp>.md en cwd)")
    parser.add_argument("--atasco", type=str, default=DEFAULT_ATASCO,
                        help="Descripción del atasco (placeholder en la demo)")
    args = parser.parse_args()

    path = generate_fake_report(args.out, args.atasco)
    print(f"Reporte generado: {path.resolve()}")


if __name__ == "__main__":
    main()
