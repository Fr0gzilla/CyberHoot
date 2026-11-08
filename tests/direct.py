"""Aides communes aux tests des parties en direct."""

from __future__ import annotations

from flask.testing import FlaskClient

from app.extensions import db
from app.models import LiveGame, Quiz
from app.services import live
from tests.conftest import jeton_csrf


def recharger(partie: LiveGame) -> LiveGame:
    db.session.expire_all()
    trouvee = db.session.get(LiveGame, partie.id)
    assert trouvee is not None
    return trouvee


def lancer(client: FlaskClient, quiz: Quiz, chrono: str = "20") -> LiveGame:
    jeton = jeton_csrf(client, f"/quiz/{quiz.id}")
    reponse = client.post(f"/direct/lancer/{quiz.id}", data={"csrf_token": jeton, "chrono": chrono})
    assert reponse.status_code == 302, reponse.status_code
    game_id = int(reponse.headers["Location"].rsplit("/", 1)[1])
    partie = db.session.get(LiveGame, game_id)
    assert partie is not None
    return partie


def rejoindre(client: FlaskClient, pin: str, pseudo: str):  # type: ignore[no-untyped-def]
    jeton = jeton_csrf(client, "/direct/")
    return client.post("/direct/", data={"csrf_token": jeton, "pin": pin, "pseudo": pseudo})


def agir(client: FlaskClient, partie: LiveGame, action: str, **champs: str):  # type: ignore[no-untyped-def]
    jeton = jeton_csrf(client, f"/direct/animer/{partie.id}")
    return client.post(f"/direct/animer/{partie.id}/{action}", data={"csrf_token": jeton, **champs})


def repondre(client: FlaskClient, partie: LiveGame, choix: list[int], position: int | None = None):  # type: ignore[no-untyped-def]
    partie = recharger(partie)
    # Le jeton se lit sur la page « Rejoindre » : l'écran du joueur n'a pas toujours de formulaire.
    jeton = jeton_csrf(client, "/direct/")
    return client.post(
        f"/direct/jouer/{partie.id}",
        data={
            "csrf_token": jeton,
            "position": str(partie.current_index if position is None else position),
            "choix": [str(c) for c in choix],
        },
    )


def bonnes(partie: LiveGame) -> list[int]:
    question = live.question_courante(recharger(partie))
    assert question is not None
    return sorted(question.correct_ids)


def mauvaise(partie: LiveGame) -> list[int]:
    question = live.question_courante(recharger(partie))
    assert question is not None
    return [next(o.id for o in question.options if not o.is_correct)]
