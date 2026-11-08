"""Pseudos des parties en direct : forme autorisée et modération simple."""

from __future__ import annotations

import re
import unicodedata

MOTIF_PSEUDO = re.compile(r"^[\w][\w \-]{0,18}[\w]$|^[\w]$")
# Courte liste de mots refusés dans les pseudos (comparés sans accents, espaces ni casse) :
# refusés s'ils apparaissent n'importe où dans le pseudo…
MOTS_INTERDITS = frozenset(
    {"connard", "encule", "salope", "putain", "hitler", "nazi", "batard", "nique", "merde"}
)
# …ou seulement s'ils sont le pseudo entier (trop courts ou trop courants dans d'autres mots).
PSEUDOS_INTERDITS = frozenset(
    {"admin", "administrateur", "animateur", "con", "conne", "fdp", "pute", "pd"}
)


def cle(pseudo: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", pseudo).encode("ascii", "ignore").decode()
    return re.sub(r"[\s_\-]+", "", sans_accents.lower())


def valide(pseudo: str) -> bool:
    return len(pseudo) <= 20 and MOTIF_PSEUDO.fullmatch(pseudo) is not None


def accepte(cle_pseudo: str) -> bool:
    """Refuse une clé vide, un pseudo réservé ou contenant un mot injurieux."""
    return (
        bool(cle_pseudo)
        and cle_pseudo not in PSEUDOS_INTERDITS
        and not any(mot in cle_pseudo for mot in MOTS_INTERDITS)
    )
