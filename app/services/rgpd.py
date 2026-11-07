"""Export des données d'un compte (droit d'accès et à la portabilité, RGPD art. 15 et 20)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.extensions import db
from app.models import LivePlayer, PlaySession, Quiz, Report, Review, User, utcnow
from app.services import audit, progression


def _date(valeur: datetime | None) -> str | None:
    return valeur.isoformat(timespec="seconds") + "Z" if valeur else None


def donnees(user: User) -> dict[str, Any]:
    """Tout ce que la base contient sur ce compte, sous une forme lisible."""
    parties = db.session.scalars(
        select(PlaySession).where(PlaySession.user_id == user.id).order_by(PlaySession.id)
    )
    return {
        "export": {"genere_le": _date(utcnow()), "format": "CyberHoot, version 1"},
        "compte": {
            "pseudo": user.username,
            "email": user.email,
            "roles": user.role_names,
            "cree_le": _date(user.created_at),
            "email_confirme_le": _date(user.email_verified_at),
            "derniere_connexion": _date(user.last_login_at),
            "double_authentification": user.totp_enabled,
        },
        "parties": [
            {
                "quiz": p.quiz.title,
                "score": p.score,
                "total": p.total,
                "debut": _date(p.started_at),
                "fin": _date(p.finished_at),
                "reponses": [
                    {"question": r.question.text if r.question else None, "juste": r.is_correct}
                    for r in p.answers
                ],
            }
            for p in parties
        ],
        "parties_en_direct": [
            {"pseudo": j.nickname, "score": j.score, "rejointe_le": _date(j.joined_at)}
            for j in db.session.scalars(select(LivePlayer).where(LivePlayer.user_id == user.id))
        ],
        "avis": [
            {
                "quiz": a.quiz_id,
                "note": a.rating,
                "commentaire": a.comment,
                "date": _date(a.updated_at),
            }
            for a in db.session.scalars(select(Review).where(Review.user_id == user.id))
        ],
        "quiz_crees": [
            {"titre": q.title, "statut": q.status.value, "cree_le": _date(q.created_at)}
            for q in db.session.scalars(select(Quiz).where(Quiz.creator_id == user.id))
        ],
        "badges": [
            {"badge": ub.badge.name, "obtenu_le": _date(ub.obtained_at)}
            for ub in progression.badges_de(user)
        ],
        "signalements": [
            {"motif": r.reason, "statut": r.status.value, "date": _date(r.created_at)}
            for r in db.session.scalars(select(Report).where(Report.reporter_id == user.id))
        ],
        "journal_de_securite": [
            {
                "date": _date(ligne.created_at),
                "action": audit.ACTIONS.get(ligne.action, ligne.action),
                "adresse_ip": ligne.ip,
            }
            for ligne in audit.de(user)
        ],
    }


def export_json(user: User) -> str:
    return json.dumps(donnees(user), ensure_ascii=False, indent=2)
