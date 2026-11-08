"""Parties en direct : barème, export, purge, actions refusées, limitation des essais de PIN."""

from __future__ import annotations

from datetime import timedelta

from flask import Flask
from flask.testing import FlaskClient

from app.extensions import db
from app.models import LiveGame, LivePlayer, LiveStatus, Quiz, utcnow
from app.services import live, live_bilan, live_entretien
from tests.direct import agir, recharger, rejoindre


class TestService:
    def test_bareme(self) -> None:
        assert live_bilan.points(False, 0, 20) == 0
        assert live_bilan.points(True, 0, 20) == 1000
        assert live_bilan.points(True, 10_000, 20) == 750
        assert live_bilan.points(True, 25_000, 20) == 500

    def test_export_csv_neutralise_les_formules(
        self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        _, partie, _ = salle
        db.session.add(
            LivePlayer(game_id=partie.id, nickname="=1+1", nickname_key="x", token="t" * 43)
        )
        db.session.commit()
        assert "'=1+1" in live_bilan.export_csv(recharger(partie))

    def test_purge(self, app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]) -> None:
        _, partie, _ = salle
        partie.last_activity_at = utcnow() - timedelta(hours=4)
        db.session.commit()
        assert live_entretien.purger() == (1, 0)
        partie = recharger(partie)
        assert partie.status is LiveStatus.FINISHED
        partie.ended_at = utcnow() - timedelta(hours=25)
        db.session.commit()
        identifiant = partie.id
        assert live_entretien.purger() == (0, 1)
        db.session.expire_all()
        assert db.session.get(LiveGame, identifiant) is None

    def test_actions_inconnues_ou_hors_etat(
        self, salle: tuple[FlaskClient, LiveGame, Quiz]
    ) -> None:
        animateur, partie, _ = salle
        assert agir(animateur, partie, "inconnue").status_code == 404
        assert not live.pause(partie)
        assert not live.reprendre(partie)
        assert not live.suivant(partie)
        assert not live.exclure(partie, 123456)
        assert live.terminer(partie)
        assert not live.terminer(partie)


def test_essais_de_pin_limites_mais_pas_les_arrivees(
    app: Flask, salle: tuple[FlaskClient, LiveGame, Quiz]
) -> None:
    _, partie, _ = salle
    client = app.test_client()
    for i in range(35):
        assert rejoindre(app.test_client(), partie.pin or "", f"Eleve {i}").status_code == 302
    codes = [rejoindre(client, "000000", "Devin").status_code for _ in range(31)]
    assert codes[-1] == 429
    assert set(codes[:30]) == {404}
