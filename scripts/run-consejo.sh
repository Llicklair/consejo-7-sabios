#!/usr/bin/env bash
# Lanza el Consejo de los 7 Sabios con animación TUI (POSIX wrapper).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ATASCO="${1:-}"
MODE="${MODE:-mock}"
ROUNDS="${ROUNDS:-}"
SPEED="${SPEED:-0.3}"
CC_MODEL="${CC_MODEL:-sonnet}"

if [[ ! -x ".venv/bin/python" && ! -x ".venv/Scripts/python.exe" ]]; then
    echo "❌ No encuentro .venv" >&2
    echo "   Crea el venv primero:  python -m venv .venv && .venv/bin/pip install -e ." >&2
    exit 1
fi

if [[ -z "$ATASCO" ]]; then
    read -rp "Atasco a debatir (Enter para 'Mejora general del proyecto'): " ATASCO
    ATASCO="${ATASCO:-Mejora general del proyecto}"
fi

if [[ -z "$ROUNDS" ]]; then
    if [[ "$MODE" == "claude-code" ]]; then ROUNDS=2; else ROUNDS=3; fi
fi

export PYTHONPATH=src
PY=".venv/bin/python"
[[ -x ".venv/Scripts/python.exe" ]] && PY=".venv/Scripts/python.exe"

ARGS=(-m consejo.cli "$ATASCO" --mode "$MODE" --rounds "$ROUNDS" --speed "$SPEED")
[[ "$MODE" == "claude-code" ]] && ARGS+=(--cc-model "$CC_MODEL")

echo "🔮 Convocando al Consejo..."
echo "   Atasco: $ATASCO"
echo "   Modo:   $MODE  ·  Rondas: $ROUNDS  ·  Velocidad: $SPEED"
echo ""

exec "$PY" "${ARGS[@]}"
