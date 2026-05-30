"""Runner standalone del paso de análisis (P1).

Uso:
  python scripts/analyze.py <repo> [--dry-run] [--model sonnet] [--max-batches N]

`--dry-run` solo enumera y lotea (sin LLM) e imprime la ESCALA, para saber el
coste antes de lanzar la pasada real. `--max-batches` cota la pasada real a los
primeros N lotes (útil para una prueba parcial barata).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from consejo.analysis import (  # noqa: E402
    batch_units,
    coverage_summary,
    enumerate_units,
    render_repo_map,
    run_analysis_pass,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--max-batches", type=int, default=None,
                    help="Cota la pasada a N lotes (resto pendiente, resumible).")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        ap.error(f"no es un directorio: {repo}")

    units = enumerate_units(repo)
    total_bytes = sum(u.size_bytes for u in units)
    batches = batch_units(units)
    print(f"repo:            {repo}")
    print(f"archivos fuente: {len(units)}")
    print(f"tamaño total:    {total_bytes / 1000:.0f} KB "
          f"({total_bytes / 1_000_000:.2f} MB)")
    print(f"lotes:           {len(batches)}  (= nº de llamadas al analizador)")
    ext = Counter(Path(u.path).suffix for u in units)
    print(f"por extensión:   {dict(ext.most_common())}")

    if args.dry_run:
        print("\n[dry-run] no se lanza el analizador.")
        return

    from consejo.backends import build_backend  # noqa: E402
    driver = build_backend("claude-code")

    async def _progress(cov: int, tot: int) -> None:
        pct = 100 * cov // tot if tot else 100
        print(f"  ... cobertura {cov}/{tot} ({pct}%)", flush=True)

    ledger = asyncio.run(
        run_analysis_pass(driver, repo, model=args.model,
                          on_progress=_progress, max_batches=args.max_batches)
    )

    units2 = enumerate_units(repo)
    summ = coverage_summary(ledger, units2)
    print(f"\n=== COBERTURA: {summ['covered']}/{summ['total']} ===")
    print(f"por rol:  {summ['by_role']}")
    print(f"concerns: {summ['concerns']}")
    if summ["unanalyzed"]:
        print(f"SIN ANALIZAR ({len(summ['unanalyzed'])}): "
              f"{summ['unanalyzed'][:20]}")

    out = repo / ".consejo" / "repo-map.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_repo_map(ledger, units2), encoding="utf-8")
    print(f"mapa escrito en: {out}")


if __name__ == "__main__":
    main()
