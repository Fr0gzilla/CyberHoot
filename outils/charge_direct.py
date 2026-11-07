"""Test de charge d'une partie en direct (bibliothèque standard seulement).

Simule un animateur et N joueurs qui rejoignent, interrogent l'état chaque seconde et
répondent à chaque question, tous depuis la même adresse IP (cas d'une salle de classe
derrière le réseau de l'établissement). Mesure les temps de réponse et compte les erreurs.

    python outils/charge_direct.py --url http://localhost:8080 --joueurs 50 \\
        --email admin@exemple.fr --mot-de-passe '…' --quiz 1

À lancer uniquement contre une instance que vous avez démarrée vous-même.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import random
import re
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

MESURES: dict[str, list[float]] = defaultdict(list)
ERREURS: dict[str, int] = defaultdict(int)
VERROU = threading.Lock()


class Navigateur:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.ouvreur = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def requete(self, nom: str, chemin: str, donnees: dict[str, object] | None = None) -> str:
        return self.ouvrir(nom, chemin, donnees)[0]

    def ouvrir(
        self, nom: str, chemin: str, donnees: dict[str, object] | None = None
    ) -> tuple[str, str]:
        """Texte de la page et adresse finale (après redirections)."""
        corps = None
        if donnees is not None:
            corps = urllib.parse.urlencode(donnees, doseq=True).encode()
        debut = time.perf_counter()
        try:
            with self.ouvreur.open(self.base + chemin, corps, timeout=15) as reponse:
                texte: str = reponse.read().decode()
                adresse: str = reponse.geturl()
        except urllib.error.HTTPError as erreur:
            with VERROU:
                ERREURS[f"{nom} HTTP {erreur.code}"] += 1
            return "", ""
        except OSError:
            with VERROU:
                ERREURS[f"{nom} réseau"] += 1
            return "", ""
        with VERROU:
            MESURES[nom].append((time.perf_counter() - debut) * 1000)
        return texte, adresse

    def jeton(self, chemin: str) -> str:
        page = self.requete("page", chemin)
        trouve = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', page)
        return trouve.group(1) if trouve else ""


def animateur(
    base: str, email: str, mdp: str, quiz: int, chrono: int
) -> tuple[Navigateur, int, str]:
    nav = Navigateur(base)
    nav.requete(
        "connexion",
        "/compte/connexion",
        {
            "email": email,
            "password": mdp,
            "csrf_token": nav.jeton("/compte/connexion"),
        },
    )
    ecran, adresse = nav.ouvrir(
        "lancer",
        f"/direct/lancer/{quiz}",
        {
            "csrf_token": nav.jeton(f"/quiz/{quiz}"),
            "chrono": chrono,
        },
    )
    identifiant = re.search(r"/direct/animer/(\d+)$", adresse)
    pin = re.search(r">(\d{6})</p>", ecran)
    if not identifiant or not pin:
        raise SystemExit("lancement impossible : identifiants, quiz publié, compte créateur ?")
    return nav, int(identifiant.group(1)), pin.group(1)


def joueur(
    base: str, game_id: int, pin: str, numero: int, fin: threading.Event, pret: threading.Barrier
) -> None:
    nav = Navigateur(base)
    nav.requete(
        "rejoindre",
        "/direct/",
        {
            "pin": pin,
            "pseudo": f"Joueur {numero}",
            "csrf_token": nav.jeton("/direct/"),
        },
    )
    pret.wait()
    deja: set[int] = set()
    version = None
    page = ""
    while not fin.is_set():
        etat = nav.requete("etat", f"/direct/{game_id}/etat").replace(" ", "")
        if '"statut":"finished"' in etat:
            break
        trouve = re.search(r'"version":(\d+)', etat)
        # Comme le navigateur : la page n'est rechargée qu'au changement d'écran.
        if trouve and trouve.group(1) != version:
            version = trouve.group(1)
            page = nav.requete("ecran", f"/direct/jouer/{game_id}")
        if '"statut":"question"' in etat:
            position = re.search(r'name="position" value="(\d+)"', page)
            options = re.findall(r'name="choix" value="(\d+)"', page)
            if position and options and int(position.group(1)) not in deja:
                time.sleep(random.uniform(0.2, 3.0))  # temps de réflexion  # noqa: S311
                nav.requete(
                    "repondre",
                    f"/direct/jouer/{game_id}",
                    {
                        "csrf_token": nav.jeton("/direct/"),
                        "position": position.group(1),
                        "choix": [random.choice(options)],  # noqa: S311
                    },
                )
                deja.add(int(position.group(1)))
        time.sleep(1)


def principal() -> None:
    args = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    args.add_argument("--url", default="http://localhost:8080")
    args.add_argument("--joueurs", type=int, default=50)
    args.add_argument("--email", required=True)
    args.add_argument("--mot-de-passe", required=True)
    args.add_argument("--quiz", type=int, default=1)
    args.add_argument("--chrono", type=int, default=10)
    options = args.parse_args()

    nav, game_id, pin = animateur(
        options.url, options.email, options.mot_de_passe, options.quiz, options.chrono
    )
    print(f"partie {game_id}, PIN {pin}, {options.joueurs} joueurs")
    fin = threading.Event()
    pret = threading.Barrier(options.joueurs + 1, timeout=120)
    fils = [
        threading.Thread(target=joueur, args=(options.url, game_id, pin, i, fin, pret))
        for i in range(1, options.joueurs + 1)
    ]
    for fil in fils:
        fil.start()
    pret.wait()
    ecran = nav.requete("animer", f"/direct/animer/{game_id}")
    print("joueurs dans la salle :", re.search(r"data-joueurs=\"(\d+)\"", ecran).group(1))  # type: ignore[union-attr]

    def action(nom: str) -> None:
        nav.requete(
            "action",
            f"/direct/animer/{game_id}/{nom}",
            {
                "csrf_token": nav.jeton(f"/direct/animer/{game_id}"),
            },
        )

    debut = time.perf_counter()
    action("demarrer")
    while True:
        etat = nav.requete("etat", f"/direct/{game_id}/etat").replace(" ", "")
        if '"statut":"reveal"' in etat:
            time.sleep(2)
            action("suivant")
        elif '"statut":"finished"' in etat:
            break
        time.sleep(1)
    duree = time.perf_counter() - debut
    fin.set()
    for fil in fils:
        fil.join()
    csv = nav.requete("csv", f"/direct/animer/{game_id}/classement.csv")

    print(f"\npartie jouée en {duree:.0f} s ; lignes du classement : {len(csv.splitlines()) - 1}")
    print(f"{'requête':<10} {'nombre':>7} {'médiane':>9} {'p95':>9} {'max':>9}  (ms)")
    for nom, valeurs in sorted(MESURES.items()):
        valeurs.sort()
        p95 = valeurs[int(len(valeurs) * 0.95) - 1] if len(valeurs) > 1 else valeurs[0]
        print(
            f"{nom:<10} {len(valeurs):>7} {statistics.median(valeurs):>9.0f} {p95:>9.0f} "
            f"{valeurs[-1]:>9.0f}"
        )
    print("erreurs :", dict(ERREURS) or "aucune")


if __name__ == "__main__":
    principal()
