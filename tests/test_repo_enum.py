"""Tests del enumerador determinista de archivos (repo_enum).

Extraído de test_analysis.py al modularizar: el enumerador es lo único que
sobrevivió de la vieja pasada LLM. Verifica que lista TODO el código fuente,
excluye árboles vendored/build, y hashea por contenido.
"""

from __future__ import annotations

from pathlib import Path

from consejo.repo_enum import FileUnit, enumerate_units


def _mk(tmp: Path, rel: str, content: str) -> None:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_enumerate_lists_source_and_hashes(tmp_path):
    _mk(tmp_path, "a.py", "x = 1\n")
    _mk(tmp_path, "sub/b.ts", "export const y = 2;\n")
    _mk(tmp_path, "README.md", "# hi\n")
    units = enumerate_units(tmp_path)
    paths = {u.path for u in units}
    assert {"a.py", "sub/b.ts", "README.md"} <= paths
    assert all(isinstance(u, FileUnit) and len(u.content_hash) == 40
               for u in units)


def test_enumerate_excludes_vendored_and_nonsource(tmp_path):
    _mk(tmp_path, "keep.py", "x = 1\n")
    _mk(tmp_path, "node_modules/pkg/index.js", "module.exports = 1\n")
    _mk(tmp_path, "dist/bundle.js", "1\n")
    _mk(tmp_path, "data.bin", "binary\n")        # non-source extension
    paths = {u.path for u in enumerate_units(tmp_path)}
    assert "keep.py" in paths
    assert not any(p.startswith("node_modules/") for p in paths)
    assert not any(p.startswith("dist/") for p in paths)
    assert "data.bin" not in paths


def test_hash_changes_with_content(tmp_path):
    _mk(tmp_path, "a.py", "x = 1\n")
    h1 = enumerate_units(tmp_path)[0].content_hash
    _mk(tmp_path, "a.py", "x = 2\n")
    h2 = enumerate_units(tmp_path)[0].content_hash
    assert h1 != h2
