"""Lecture du catalogue : recherche, filtres, notes moyennes, avis, statistiques."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select

from app.extensions import db
from app.models import (
    Difficulty,
    PlayAnswer,
    PlaySession,
    Question,
    Quiz,
    QuizStatus,
    Review,
    User,
)
from app.services import play

PAR_PAGE = 12


@dataclass(frozen=True)
class Note:
    moyenne: float | None
    nombre: int


@dataclass(frozen=True)
class Page:
    quiz: list[Quiz]
    notes: dict[int, Note]
    page: int
    pages: int
    total: int


def _echapper_like(texte: str) -> str:
    return texte.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def rechercher(
    texte: str = "", categorie: int | None = None, niveau: str = "", page: int = 1
) -> Page:
    requete = select(Quiz).where(Quiz.status == QuizStatus.PUBLISHED)
    texte = texte.strip()[:100]
    if texte:
        motif = f"%{_echapper_like(texte)}%"
        requete = requete.where(
            or_(Quiz.title.ilike(motif, escape="\\"), Quiz.description.ilike(motif, escape="\\"))
        )
    if categorie:
        requete = requete.where(Quiz.category_id == categorie)
    if niveau in {d.value for d in Difficulty}:
        requete = requete.where(Quiz.difficulty == Difficulty(niveau))
    total = db.session.scalar(select(func.count()).select_from(requete.subquery())) or 0
    pages = max(1, -(-total // PAR_PAGE))
    page = min(max(1, page), pages)
    resultats = list(
        db.session.scalars(
            requete.order_by(Quiz.published_at.desc(), Quiz.id.desc())
            .offset((page - 1) * PAR_PAGE)
            .limit(PAR_PAGE)
        )
    )
    return Page(resultats, notes([q.id for q in resultats]), page, pages, total)


def notes(ids: list[int]) -> dict[int, Note]:
    if not ids:
        return {}
    lignes = db.session.execute(
        select(Review.quiz_id, func.avg(Review.rating), func.count(Review.id))
        .where(Review.quiz_id.in_(ids))
        .group_by(Review.quiz_id)
    ).all()
    trouvees = {qid: Note(round(float(moy), 1), n) for qid, moy, n in lignes}
    return {i: trouvees.get(i, Note(None, 0)) for i in ids}


def avis(quiz: Quiz) -> list[Review]:
    return list(
        db.session.scalars(
            select(Review).where(Review.quiz_id == quiz.id).order_by(Review.updated_at.desc())
        )
    )


def avis_de(user: User, quiz: Quiz) -> Review | None:
    trouve: Review | None = db.session.scalar(
        select(Review).where(Review.user_id == user.id, Review.quiz_id == quiz.id)
    )
    return trouve


def donner_avis(user: User, quiz: Quiz, note: int, commentaire: str) -> bool:
    """Un avis par joueur et par quiz, après au moins une partie terminée (mis à jour sinon)."""
    if not play.a_termine(user, quiz) or not 1 <= note <= 5:
        return False
    existant = avis_de(user, quiz)
    if existant is None:
        existant = Review(user_id=user.id, quiz_id=quiz.id, rating=note)
        db.session.add(existant)
    existant.rating = note
    existant.comment = commentaire.strip()[:1000] or None
    db.session.commit()
    return True


# --- Statistiques d'un quiz pour son créateur ------------------------------------------------


@dataclass(frozen=True)
class StatQuestion:
    question: Question
    reponses: int
    reussite: int | None  # pourcentage, None sans réponse


@dataclass(frozen=True)
class Statistiques:
    parties: int
    score_moyen: int | None
    questions: list[StatQuestion]

    @property
    def plus_ratee(self) -> StatQuestion | None:
        avec_reponses = [q for q in self.questions if q.reussite is not None]
        return min(avec_reponses, key=lambda q: q.reussite or 0) if avec_reponses else None


def statistiques(quiz: Quiz) -> Statistiques:
    parties, moyenne = db.session.execute(
        select(
            func.count(PlaySession.id), func.avg(100.0 * PlaySession.score / PlaySession.total)
        ).where(PlaySession.quiz_id == quiz.id, PlaySession.finished_at.is_not(None))
    ).one()
    par_question = {
        qid: (n, justes)
        for qid, n, justes in db.session.execute(
            select(
                PlayAnswer.question_id,
                func.count(PlayAnswer.id),
                func.sum(func.cast(PlayAnswer.is_correct, db.Integer)),
            )
            .where(PlayAnswer.question_id.in_([q.id for q in quiz.questions]))
            .group_by(PlayAnswer.question_id)
        ).all()
    }
    lignes = []
    for question in quiz.questions:
        n, justes = par_question.get(question.id, (0, 0))
        lignes.append(StatQuestion(question, n, round(100 * (justes or 0) / n) if n else None))
    return Statistiques(
        parties=parties or 0,
        score_moyen=round(float(moyenne)) if moyenne is not None else None,
        questions=lignes,
    )
