"""Audit d'accessibilité automatique : axe-core (WCAG 2.0, 2.1, 2.2 niveaux A et AA) sur les
pages de CyberHoot, en thème clair puis sombre, avec un compte administrateur.

Couvre les pages publiques, les erreurs de formulaire, le profil, l'éditeur, l'administration,
une partie solo et une partie en direct (écran de l'animateur et d'un joueur), puis des
parcours au clavier seul (formulaire refusé, rejoindre une partie, partie solo). Se lance dans
l'image officielle de Playwright, sur le réseau de la pile Docker (voir docs/accessibilite.md) :

    AUDIT_EMAIL=… AUDIT_MOT_DE_PASSE=… AUDIT_TOTP=<secret> AUDIT_QUIZ=5 \\
        python outils/audit_accessibilite.py axe.min.js

AUDIT_TOTP est le secret de double authentification du compte (base 32). Code de sortie 1 si
une règle est en défaut.
"""

from __future__ import annotations

import os
import re
import sys
import time
from typing import Any

import pyotp
from playwright.sync_api import Browser, Page, sync_playwright

BASE = os.environ.get("AUDIT_URL", "https://proxy:8443")
QUIZ = os.environ.get("AUDIT_QUIZ", "1")
REGLES = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]
PUBLIQUES = [
    ("/", "accueil"),
    ("/compte/connexion", "connexion"),
    ("/compte/inscription", "inscription"),
    ("/compte/mot-de-passe-oublie", "oubli"),
    ("/compte/activation", "renvoi-activation"),
    ("/quiz", "catalogue"),
    (f"/quiz/{QUIZ}", "detail"),
    ("/badges", "badges"),
    ("/direct/", "rejoindre"),
    ("/confidentialite", "confidentialite"),
    ("/page-inexistante", "erreur-404"),
]
CONNECTEES = [
    ("/profil/", "profil"),
    ("/profil/progression", "progression"),
    ("/profil/double-authentification", "double-authentification"),
    ("/createur/", "createur"),
    ("/createur/quiz/nouveau", "editeur"),
    ("/admin/", "administration"),
    ("/admin/comptes", "comptes"),
    ("/admin/journal", "journal"),
    ("/admin/badges", "admin-badges"),
    ("/admin/categories", "admin-categories"),
    ("/admin/signalements", "signalements"),
    (f"/admin/quiz/{QUIZ}", "revue"),
]


class Audit:
    def __init__(self, axe: str) -> None:
        self.axe = axe
        self.defauts: dict[str, dict[str, Any]] = {}
        self.pages = 0

    def __call__(self, page: Page, nom: str, theme: str) -> None:
        page.wait_for_load_state("networkidle")
        page.evaluate(self.axe)
        resultat = page.evaluate(
            "async r => await axe.run(document, {runOnly: {type: 'tag', values: r}})", REGLES
        )
        self.pages += 1
        for regle in resultat["violations"]:
            entree = self.defauts.setdefault(
                f"{regle['id']} ({regle['impact']})", {"aide": regle["help"], "ou": []}
            )
            for noeud in regle["nodes"][:2]:
                entree["ou"].append(f"{nom} [{theme}] {noeud['target']}")


def connecter(page: Page) -> None:
    page.goto(BASE + "/compte/connexion")
    page.fill("#email", os.environ["AUDIT_EMAIL"])
    page.fill("#password", os.environ["AUDIT_MOT_DE_PASSE"])
    page.click("form button[type=submit]")
    time.sleep(31 - time.time() % 30)  # un code ne sert qu'une fois : on attend le suivant
    page.fill("#code", pyotp.TOTP(os.environ["AUDIT_TOTP"]).now())
    page.click("form button[type=submit]")


def parcourir(navigateur: Browser, auditer: Audit, theme: str) -> None:
    options: dict[str, Any] = {
        "viewport": {"width": 1280, "height": 900},
        "color_scheme": theme,
        "ignore_https_errors": True,  # certificat auto-signé en local
        "bypass_csp": True,  # pour injecter axe-core, qui n'est pas servi par l'application
    }
    contexte = navigateur.new_context(**options)
    page = contexte.new_page()
    for chemin, nom in PUBLIQUES:
        page.goto(BASE + chemin)
        auditer(page, nom, theme)
    page.goto(BASE + "/compte/inscription")
    page.click("form button[type=submit]")
    auditer(page, "inscription-erreurs", theme)

    connecter(page)
    for chemin, nom in CONNECTEES:
        page.goto(BASE + chemin)
        auditer(page, nom, theme)
    page.goto(f"{BASE}/quiz/{QUIZ}")
    page.click("button:has-text('Commencer')")
    auditer(page, "question", theme)
    # Selon le type de la question (une partie entamée reprend où elle en était), on coche la
    # première case s'il y en a une ; sinon la page affiche l'erreur, auditée elle aussi.
    choix = page.locator("input[name=choix]")
    if choix.count():
        choix.first.evaluate("e => e.checked = true")
    page.click("button:has-text('Valider')")
    auditer(page, "correction", theme)

    page.goto(f"{BASE}/quiz/{QUIZ}")
    page.click("button:has-text('Lancer en direct')")
    auditer(page, "direct-salle", theme)
    trouve = re.search(r"\b(\d{6})\b", page.inner_text("main"))
    if trouve is None:
        raise SystemExit("code PIN introuvable sur l'écran de l'animateur")
    joueur = navigateur.new_context(**options).new_page()
    joueur.goto(BASE + "/direct/")
    joueur.fill("#pin", trouve.group(1))
    joueur.fill("#pseudo", f"Audit {theme}")
    joueur.click("form button[type=submit]")
    auditer(joueur, "direct-joueur-attente", theme)
    page.reload()
    page.click("button:has-text('Lancer la partie')")
    auditer(page, "direct-animateur", theme)
    joueur.reload()
    auditer(joueur, "direct-joueur-question", theme)
    page.click("button:has-text('Terminer')")
    contexte.close()


def entree(page: Page) -> None:
    """Appuie sur Entrée et attend la page suivante."""
    with page.expect_navigation():
        page.keyboard.press("Enter")


def tabuler_jusqu_a(page: Page, condition: str) -> None:
    """Tabule jusqu'à l'élément qui vérifie `condition` (expression JS sur `e`)."""
    for _ in range(60):
        page.keyboard.press("Tab")
        if page.evaluate(f"(e => {condition})(document.activeElement)"):
            return
    raise AssertionError(f"inatteignable au clavier : {condition}")


def clavier(navigateur: Browser) -> list[str]:
    """Parcours au clavier seul (Tab, Espace, Entrée). Renvoie les échecs constatés."""
    echecs: list[str] = []
    page = navigateur.new_context(ignore_https_errors=True).new_page()

    page.goto(BASE + "/compte/inscription")
    page.keyboard.press("Tab")
    if page.evaluate("document.activeElement.className") != "lien-evitement":
        echecs.append("le lien d'évitement n'est pas le premier élément atteint")
    tabuler_jusqu_a(page, "e.type === 'submit'")
    entree(page)
    if page.evaluate("document.activeElement.getAttribute('aria-invalid')") != "true":
        echecs.append("formulaire refusé : le focus ne va pas au premier champ fautif")

    page.goto(BASE + "/direct/")
    tabuler_jusqu_a(page, "e.id === 'pin'")
    page.keyboard.type("000000")
    page.keyboard.press("Tab")
    page.keyboard.type("Clavier")
    entree(page)
    if not page.locator("[role=alert]").count():
        echecs.append("rejoindre avec un code faux : erreur non annoncée")

    connecter(page)
    page.goto(f"{BASE}/quiz/{QUIZ}")
    tabuler_jusqu_a(page, "e.textContent.trim() === 'Commencer'")
    entree(page)
    # Une partie entamée reprend où elle en était : la question peut être de n'importe quel type.
    tabuler_jusqu_a(page, "e.closest('fieldset') && ['INPUT', 'SELECT'].includes(e.tagName)")
    if page.evaluate("document.activeElement.tagName") == "INPUT":
        page.keyboard.press("Space")
    tabuler_jusqu_a(page, "e.textContent.includes('Valider')")
    entree(page)
    if "/correction/" not in page.url and not page.locator("[role=alert]").count():
        echecs.append("partie solo : réponse impossible à envoyer au clavier")
    return echecs


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as fichier:
        auditer = Audit(fichier.read())
    with sync_playwright() as playwright:
        navigateur = playwright.chromium.launch()
        for theme in ("light", "dark"):
            parcourir(navigateur, auditer, theme)
        echecs = clavier(navigateur)
    for regle, detail in sorted(auditer.defauts.items()):
        print(f"\n{regle} — {detail['aide']}")
        for lieu in detail["ou"][:6]:
            print("   ·", lieu)
    print(f"\n{auditer.pages} pages analysées, {len(auditer.defauts)} règle(s) en défaut.")
    for echec in echecs:
        print("   clavier ·", echec)
    print("Parcours au clavier :", "réussis" if not echecs else f"{len(echecs)} échec(s)")
    return 1 if auditer.defauts or echecs else 0


if __name__ == "__main__":
    sys.exit(main())
