"""Règles de structure du dépôt, vérifiées à chaque exécution des tests."""

from __future__ import annotations

from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LIGNES_MAX = 400


def test_aucun_fichier_de_plus_de_400_lignes() -> None:
    trop_longs = {
        str(f.relative_to(RACINE)): n
        for dossier in ("app", "tests", "migrations", "outils")
        for f in (RACINE / dossier).rglob("*")
        if f.suffix in {".py", ".html", ".js", ".css"}
        and (n := len(f.read_text(encoding="utf-8").splitlines())) > LIGNES_MAX
    }
    assert trop_longs == {}


def test_aucune_image_televersee_dans_le_depot() -> None:
    assert not (RACINE / "uploads").exists() or not any((RACINE / "uploads").iterdir())
    assert "uploads/" in (RACINE / ".gitignore").read_text(encoding="utf-8")
