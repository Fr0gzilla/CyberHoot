"""Mots de passe : hachage Argon2id et politique de robustesse.

La politique suit les recommandations de l'ANSSI et du NIST SP 800-63B : une longueur
minimale suffisante plutôt que des règles de composition, et le refus des mots de passe
connus ou dérivés de l'identité de l'utilisateur.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

LONGUEUR_MIN = 12
LONGUEUR_MAX = 128

_hasher = PasswordHasher()

# Empreinte calculée une fois : sert à dépenser le même temps quand le compte n'existe pas
# (sinon le temps de réponse révèle quels e-mails ont un compte).
_EMPREINTE_FACTICE = _hasher.hash("mot-de-passe-factice-pour-temps-constant")


def hacher(mot_de_passe: str) -> str:
    return _hasher.hash(mot_de_passe)


def verifier(empreinte: str, mot_de_passe: str) -> bool:
    try:
        return _hasher.verify(empreinte, mot_de_passe)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verifier_factice(mot_de_passe: str) -> None:
    """Même coût qu'une vraie vérification, résultat ignoré."""
    verifier(_EMPREINTE_FACTICE, mot_de_passe)


def doit_rehacher(empreinte: str) -> bool:
    return _hasher.check_needs_rehash(empreinte)


@lru_cache(maxsize=1)
def _mots_de_passe_courants() -> frozenset[str]:
    texte = resources.files("app.data").joinpath("mots_de_passe_courants.txt").read_text("utf-8")
    return frozenset(
        ligne.strip().lower()
        for ligne in texte.splitlines()
        if ligne.strip() and not ligne.startswith("#")
    )


def problemes(mot_de_passe: str, username: str = "", email: str = "") -> list[str]:
    """Liste les raisons de refuser un mot de passe (vide si acceptable)."""
    erreurs: list[str] = []
    if len(mot_de_passe) < LONGUEUR_MIN:
        erreurs.append(f"Au moins {LONGUEUR_MIN} caractères.")
    if len(mot_de_passe) > LONGUEUR_MAX:
        erreurs.append(f"Au plus {LONGUEUR_MAX} caractères.")
    minuscule = mot_de_passe.lower()
    if minuscule in _mots_de_passe_courants():
        erreurs.append("Ce mot de passe fait partie des plus utilisés : choisissez-en un autre.")
    if len(set(mot_de_passe)) <= 3:
        erreurs.append("Trop peu de caractères différents.")
    identite = [username.lower(), email.lower().split("@")[0]]
    if any(len(element) >= 3 and element in minuscule for element in identite):
        erreurs.append("Le mot de passe ne doit pas contenir votre pseudo ni votre adresse e-mail.")
    return erreurs
