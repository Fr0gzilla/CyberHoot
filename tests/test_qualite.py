"""Règles de structure du dépôt, vérifiées à chaque exécution des tests."""

from __future__ import annotations

import re
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


def test_aucun_html_injecte_par_le_javascript() -> None:
    """Le JavaScript n'écrit jamais de HTML : textContent ou création d'éléments (XSS)."""
    puits = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write")
    fautifs = [
        str(f.relative_to(RACINE))
        for f in (RACINE / "app" / "static" / "js").rglob("*.js")
        if puits.search(f.read_text(encoding="utf-8"))
    ]
    assert fautifs == []


def test_documentation_d_accord_avec_la_configuration() -> None:
    """Ports et secrets cités dans la documentation = ceux de docker-compose.yml et du Makefile."""
    compose = (RACINE / "docker-compose.yml").read_text(encoding="utf-8")
    port_https = re.search(r"HTTPS_PORT:-(\d+)", compose)
    assert port_https is not None
    documents = [RACINE / "README.md", RACINE / "SECURITY.md"]
    documents += sorted((RACINE / "docs").rglob("*.md")) if (RACINE / "docs").exists() else []
    for document in documents:
        texte = document.read_text(encoding="utf-8")
        nom = document.relative_to(RACINE)
        assert "http://localhost" not in texte.replace("http://localhost:8080/` redirige", ""), (
            f"{nom} : le site n'est servi qu'en HTTPS"
        )
        for port in re.findall(r"https://localhost:(\d+)", texte):
            assert port == port_https.group(1), f"{nom} : port {port} au lieu de {port_https[1]}"
    makefile = (RACINE / "Makefile").read_text(encoding="utf-8")
    for secret in re.findall(r"file: \./secrets/(\w+)", compose):
        assert secret in makefile, f"secret {secret} attendu par Compose mais jamais créé"
