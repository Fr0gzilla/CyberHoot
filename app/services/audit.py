"""Journal d'audit : qui a fait quoi, quand, depuis quelle adresse.

L'application ne fait qu'ajouter des lignes ; aucune page ne permet de les modifier ou de
les supprimer. Les lignes de plus de 12 mois sont purgées (données personnelles : adresse IP).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from flask import has_request_context, request
from flask_login import current_user
from sqlalchemy import delete, func, select

from app.extensions import db
from app.models import AuditLog, User, utcnow

journal = logging.getLogger(__name__)
CONSERVATION = timedelta(days=365)
PAR_PAGE = 50

ACTIONS = {
    "connexion": "Connexion réussie",
    "connexion_echec": "Échec de connexion",
    "connexion_2fa_echec": "Code de double authentification refusé",
    "deconnexion": "Déconnexion",
    "compte_verrouille": "Compte verrouillé (trop d'échecs)",
    "mot_de_passe_change": "Mot de passe changé",
    "mot_de_passe_reinitialise": "Mot de passe réinitialisé",
    "compte_supprime": "Compte supprimé par son titulaire",
    "donnees_exportees": "Export de ses données",
    "2fa_activee": "Double authentification activée",
    "2fa_desactivee": "Double authentification désactivée",
    "2fa_code_secours": "Connexion avec un code de secours",
    "2fa_codes_regeneres": "Codes de secours renouvelés",
    "admin_role": "Rôle modifié",
    "admin_compte_active": "Compte réactivé",
    "admin_compte_desactive": "Compte désactivé",
    "admin_quiz_publie": "Quiz publié",
    "admin_quiz_refuse": "Quiz refusé ou dépublié",
    "admin_categorie": "Catégorie modifiée",
    "admin_badge": "Badge modifié",
    "admin_signalement": "Signalement traité",
    "admin_avis_supprime": "Avis supprimé",
    "signalement": "Signalement envoyé",
}


def journaliser(
    action: str, cible: str | None = None, user: User | None = None, **details: Any
) -> None:
    """Ajoute une ligne au journal (et l'enregistre aussitôt)."""
    if user is None and has_request_context() and current_user.is_authenticated:
        user = current_user._get_current_object()
    db.session.add(
        AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else None,
            ip=(request.remote_addr or "")[:45] if has_request_context() else None,
            action=action[:40],
            target=(cible or "")[:120] or None,
            details=details or None,
        )
    )
    db.session.commit()


@dataclass(frozen=True)
class PageJournal:
    lignes: list[AuditLog]
    page: int
    pages: int
    total: int


def lister(
    action: str = "", pseudo: str = "", depuis: datetime | None = None, page: int = 1
) -> PageJournal:
    requete = select(AuditLog)
    if action in ACTIONS:
        requete = requete.where(AuditLog.action == action)
    if pseudo:
        requete = requete.where(AuditLog.username == pseudo.strip()[:32])
    if depuis is not None:
        requete = requete.where(AuditLog.created_at >= depuis)
    total = db.session.scalar(select(func.count()).select_from(requete.subquery())) or 0
    pages = max(1, -(-total // PAR_PAGE))
    page = min(max(1, page), pages)
    lignes = list(
        db.session.scalars(
            requete.order_by(AuditLog.id.desc()).offset((page - 1) * PAR_PAGE).limit(PAR_PAGE)
        )
    )
    return PageJournal(lignes, page, pages, total)


def de(user: User) -> list[AuditLog]:
    """Lignes concernant un compte (export de ses données)."""
    return list(
        db.session.scalars(
            select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.id)
        )
    )


def purger() -> int:
    resultat = db.session.execute(
        delete(AuditLog).where(AuditLog.created_at < utcnow() - CONSERVATION)
    )
    db.session.commit()
    return int(resultat.rowcount or 0)  # type: ignore[attr-defined]
