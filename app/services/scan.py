"""Analyse antivirus des images, en tâche de fond (commande `flask analyser-medias`).

Deux modes, choisis par SCAN_BACKEND :
- « simule » (défaut, développement, tests, recette) : aucun appel réseau ; les images sont
  déclarées saines, sauf celles dont l'empreinte figure dans SCAN_SIMULE_REFUS ;
- « virustotal » : API v3 de VirusTotal avec la clé VIRUSTOTAL_API_KEY. L'empreinte est
  d'abord cherchée (aucun envoi si le fichier est déjà connu), sinon le fichier est envoyé
  puis l'analyse est relue au passage suivant.

Une image n'est servie que lorsque son statut est « clean ».
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import Media, MediaStatus, utcnow
from app.services import live
from app.services import media as medias

journal = logging.getLogger(__name__)
API = "https://www.virustotal.com/api/v3"
SEUIL_MALVEILLANT = 1


@dataclass(frozen=True)
class Verdict:
    """Résultat d'une analyse ; `None` pour `sain` signifie « pas encore de réponse »."""

    sain: bool | None
    detail: str


class ClientVirusTotal:
    def __init__(self, cle: str, delai: float = 20.0) -> None:
        self.cle = cle
        self.delai = delai

    def _requete(
        self,
        methode: str,
        url: str,
        corps: bytes | None = None,
        entetes: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        # Seule l'API HTTPS de VirusTotal est appelée : aucune URL venue de l'extérieur.
        if not url.startswith(f"{API}/"):
            raise ValueError(f"URL refusée : {url}")
        requete = urllib.request.Request(  # noqa: S310
            url, data=corps, method=methode, headers={"x-apikey": self.cle, **(entetes or {})}
        )
        try:
            with urllib.request.urlopen(requete, timeout=self.delai) as reponse:  # noqa: S310 # nosec B310
                return reponse.status, json.loads(reponse.read() or b"{}")
        except urllib.error.HTTPError as erreur:
            return erreur.code, {}

    @staticmethod
    def _verdict_depuis(stats: dict[str, int]) -> Verdict:
        malveillant = stats.get("malicious", 0) + stats.get("suspicious", 0)
        detail = (
            f"{stats.get('malicious', 0)} malveillant(s), {stats.get('suspicious', 0)} suspect(s)"
        )
        return Verdict(sain=malveillant < SEUIL_MALVEILLANT, detail=detail)

    def analyser(self, media: Media, contenu: bytes) -> Verdict:
        code, donnees = self._requete("GET", f"{API}/files/{media.sha256}")
        if code == 200:
            stats = donnees.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            if stats:
                return self._verdict_depuis(stats)
        if code not in (200, 404):
            return Verdict(sain=None, detail=f"VirusTotal indisponible (HTTP {code})")
        # Fichier inconnu : envoi (multipart), le verdict sera relu au passage suivant.
        frontiere = uuid.uuid4().hex
        corps = (
            (
                f'--{frontiere}\r\nContent-Disposition: form-data; name="file"; '
                f'filename="{media.filename}"\r\nContent-Type: {media.mime_type}\r\n\r\n'
            ).encode()
            + contenu
            + f"\r\n--{frontiere}--\r\n".encode()
        )
        code, _ = self._requete(
            "POST",
            f"{API}/files",
            corps,
            {"Content-Type": f"multipart/form-data; boundary={frontiere}"},
        )
        return Verdict(sain=None, detail=f"envoyé à VirusTotal (HTTP {code})")


def _verdict(media: Media) -> Verdict:
    mode = current_app.config["SCAN_BACKEND"]
    if mode == "simule":
        if media.sha256 in current_app.config["SCAN_SIMULE_REFUS"]:
            return Verdict(sain=False, detail="analyse simulée : empreinte refusée")
        return Verdict(sain=True, detail="analyse simulée")
    cle = current_app.config["VIRUSTOTAL_API_KEY"]
    if not cle:
        return Verdict(sain=None, detail="clé VirusTotal absente")
    return ClientVirusTotal(cle).analyser(media, medias.chemin(media).read_bytes())


def analyser_en_attente(limite: int = 20) -> int:
    """Analyse les médias en attente ; renvoie le nombre de verdicts rendus."""
    en_attente = db.session.scalars(
        select(Media).where(Media.status == MediaStatus.PENDING).order_by(Media.id).limit(limite)
    ).all()
    rendus = 0
    for media in en_attente:
        try:
            verdict = _verdict(media)
        except OSError:
            journal.exception("analyse du média %s impossible", media.uid)
            continue
        media.scan_detail = verdict.detail[:255]
        if verdict.sain is not None:
            media.status = MediaStatus.CLEAN if verdict.sain else MediaStatus.REJECTED
            media.scanned_at = utcnow()
            rendus += 1
            if not verdict.sain:
                medias.supprimer_fichier(media)
                journal.warning("média %s rejeté : %s", media.uid, verdict.detail)
        db.session.commit()
    return rendus


def boucle(intervalle: float = 15.0) -> None:  # pragma: no cover  (processus du conteneur worker)
    journal.info("analyse des médias : boucle démarrée (toutes les %.0f s)", intervalle)
    while True:
        analyser_en_attente()
        medias.purger_orphelins()
        live.purger()
        db.session.remove()
        time.sleep(intervalle)
