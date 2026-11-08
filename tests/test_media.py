"""Images : contrôle du format, ré-encodage, accès, analyse antivirus."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from PIL import Image
from sqlalchemy import select

from app.extensions import db
from app.models import Media, MediaStatus, QuizStatus, User
from app.services import media as medias
from app.services import moderation, scan
from tests.conftest import connecter, creer_compte, jeton_csrf
from tests.fabrique import brouillon, formulaire


def image(format_: str = "PNG", taille: tuple[int, int] = (40, 30), exif: bool = False) -> bytes:
    sortie = io.BytesIO()
    img = Image.new("RGB", taille, (20, 120, 60))
    if exif:
        donnees = Image.Exif()
        donnees[0x010F] = "Appareil secret"  # fabricant
        img.save(sortie, format_, exif=donnees)
    else:
        img.save(sortie, format_)
    return sortie.getvalue()


def envoyer(client: FlaskClient, contenu: bytes, nom: str = "photo.png", alt: str = "Un écran"):  # type: ignore[no-untyped-def]
    champs: dict[str, Any] = formulaire(brouillon(1, "Avec image"))
    champs["q-0-alt"] = alt
    champs["q-0-image"] = (io.BytesIO(contenu), nom)
    champs["csrf_token"] = jeton_csrf(client, "/createur/quiz/nouveau")
    return client.post("/createur/quiz/nouveau", data=champs, content_type="multipart/form-data")


def dernier_media() -> Media | None:
    db.session.expire_all()
    return db.session.scalar(select(Media).order_by(Media.id.desc()))


class TestEnvoi:
    def test_image_valide_reencodee_et_sans_metadonnees(
        self, client: FlaskClient, createur: User
    ) -> None:
        connecter(client, "createur@example.org")
        assert envoyer(client, image("JPEG", exif=True), "vacances.jpg").status_code == 302
        media = dernier_media()
        assert media is not None
        assert media.mime_type == "image/jpeg"
        assert media.status is MediaStatus.PENDING
        assert "vacances" not in media.filename
        contenu = medias.dossier().joinpath(media.filename).read_bytes()
        assert b"Appareil secret" not in contenu
        with Image.open(io.BytesIO(contenu)) as relue:
            assert relue.size == (40, 30)

    def test_faux_fichier_image_refuse(self, client: FlaskClient, createur: User) -> None:
        connecter(client, "createur@example.org")
        reponse = envoyer(client, b"<?php system($_GET['c']); ?>", "shell.png")
        assert reponse.status_code == 422
        assert "pas une image valide" in reponse.get_data(as_text=True)
        assert dernier_media() is None

    def test_format_non_autorise_refuse(self, client: FlaskClient, createur: User) -> None:
        connecter(client, "createur@example.org")
        reponse = envoyer(client, image("GIF"), "anim.gif")
        assert "Format refusé" in reponse.get_data(as_text=True)

    def test_image_trop_lourde(self, app: Flask, client: FlaskClient, createur: User) -> None:
        app.config["MEDIA_MAX_BYTES"] = 100
        connecter(client, "createur@example.org")
        assert "trop lourde" in envoyer(client, image()).get_data(as_text=True)

    def test_dimensions_excessives(self, client: FlaskClient, createur: User) -> None:
        connecter(client, "createur@example.org")
        reponse = envoyer(client, image("PNG", (4100, 10)))
        assert "trop grande" in reponse.get_data(as_text=True)

    def test_description_obligatoire(self, client: FlaskClient, createur: User) -> None:
        connecter(client, "createur@example.org")
        reponse = envoyer(client, image(), alt="")
        assert reponse.status_code == 422
        assert "Décrivez l&#39;image" in reponse.get_data(as_text=True)

    def test_image_d_un_autre_createur_refusee(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        connecter(client, "createur@example.org")
        envoyer(client, image())
        media = dernier_media()
        assert media is not None
        from app.models import RoleName

        creer_compte(app, "voleur", RoleName.CREATOR)
        voleur = app.test_client()
        connecter(voleur, "voleur@example.org")
        champs = formulaire(brouillon(1, "Vol"))
        champs["q-0-media"] = media.uid
        champs["q-0-alt"] = "image volée"
        champs["csrf_token"] = jeton_csrf(voleur, "/createur/quiz/nouveau")
        reponse = voleur.post("/createur/quiz/nouveau", data=champs)
        assert reponse.status_code == 422
        assert "Image inconnue." in reponse.get_data(as_text=True)


class TestAcces:
    def preparer(self, client: FlaskClient) -> Media:
        connecter(client, "createur@example.org")
        envoyer(client, image())
        media = dernier_media()
        assert media is not None
        return media

    def test_avant_analyse_visible_par_l_auteur_seulement(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        media = self.preparer(client)
        assert client.get(f"/media/{media.uid}").status_code == 200
        assert app.test_client().get(f"/media/{media.uid}").status_code == 404

    def test_image_d_un_brouillon_invisible_meme_saine(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        media = self.preparer(client)
        scan.analyser_en_attente()
        assert app.test_client().get(f"/media/{media.uid}").status_code == 404

    def test_image_saine_d_un_quiz_publie_visible(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        from app.models import Quiz

        media = self.preparer(client)
        quiz = db.session.scalar(select(Quiz).where(Quiz.title == "Avec image"))
        assert quiz is not None
        quiz.status = QuizStatus.PENDING
        db.session.commit()
        with app.test_request_context():
            assert not moderation.publier(quiz), (
                "publication refusée tant que l'image n'est pas analysée"
            )
            assert scan.analyser_en_attente() == 1
            assert moderation.publier(quiz)
        reponse = app.test_client().get(f"/media/{media.uid}")
        assert reponse.status_code == 200
        assert reponse.mimetype == "image/png"
        assert reponse.headers["X-Content-Type-Options"] == "nosniff"

    def test_image_rejetee_par_l_analyse(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        media = self.preparer(client)
        app.config["SCAN_SIMULE_REFUS"] = frozenset({media.sha256})
        scan.analyser_en_attente()
        media = dernier_media()
        assert media is not None
        assert media.status is MediaStatus.REJECTED
        assert not medias.dossier().joinpath(media.filename).exists()
        assert client.get(f"/media/{media.uid}").status_code == 404

    def test_media_inconnu(self, client: FlaskClient) -> None:
        assert client.get("/media/inexistant").status_code == 404


class FausseReponse:
    def __init__(self, code: int, donnees: dict[str, Any]) -> None:
        self.status = code
        self._corps = json.dumps(donnees).encode()

    def read(self) -> bytes:
        return self._corps

    def __enter__(self) -> FausseReponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class TestVirusTotal:
    def media(self) -> Media:
        return Media(uid="a" * 32, mime_type="image/png", size=3, sha256="b" * 64)

    def test_fichier_connu_et_sain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        appels: list[str] = []

        def urlopen(requete: Any, timeout: float) -> FausseReponse:
            appels.append(f"{requete.get_method()} {requete.full_url}")
            assert requete.get_header("X-apikey") == "cle-test"
            stats = {"malicious": 0, "suspicious": 0, "harmless": 60}
            return FausseReponse(200, {"data": {"attributes": {"last_analysis_stats": stats}}})

        monkeypatch.setattr(scan.urllib.request, "urlopen", urlopen)
        verdict = scan.ClientVirusTotal("cle-test").analyser(self.media(), b"png")
        assert verdict.sain is True
        assert appels == [f"GET {scan.API}/files/{'b' * 64}"]

    def test_fichier_connu_malveillant(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stats = {"malicious": 3, "suspicious": 1}
        monkeypatch.setattr(
            scan.urllib.request,
            "urlopen",
            lambda *_a, **_k: FausseReponse(
                200, {"data": {"attributes": {"last_analysis_stats": stats}}}
            ),
        )
        verdict = scan.ClientVirusTotal("cle").analyser(self.media(), b"png")
        assert verdict.sain is False
        assert "3 malveillant" in verdict.detail

    def test_fichier_inconnu_envoye_puis_verdict_attendu(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        appels: list[str] = []

        def urlopen(requete: Any, timeout: float) -> FausseReponse:
            appels.append(requete.get_method())
            if requete.get_method() == "GET":
                raise scan.urllib.error.HTTPError(requete.full_url, 404, "absent", {}, None)  # type: ignore[arg-type]
            assert b"Content-Disposition: form-data" in requete.data
            return FausseReponse(200, {})

        monkeypatch.setattr(scan.urllib.request, "urlopen", urlopen)
        verdict = scan.ClientVirusTotal("cle").analyser(self.media(), b"png")
        assert verdict.sain is None
        assert appels == ["GET", "POST"]

    def test_service_indisponible(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def urlopen(requete: Any, timeout: float) -> FausseReponse:
            raise scan.urllib.error.HTTPError(requete.full_url, 503, "panne", {}, None)  # type: ignore[arg-type]

        monkeypatch.setattr(scan.urllib.request, "urlopen", urlopen)
        assert scan.ClientVirusTotal("cle").analyser(self.media(), b"png").sain is None

    def test_mode_virustotal_sans_cle_laisse_en_attente(
        self, app: Flask, client: FlaskClient, createur: User
    ) -> None:
        connecter(client, "createur@example.org")
        envoyer(client, image())
        app.config.update(SCAN_BACKEND="virustotal", VIRUSTOTAL_API_KEY=None)
        assert scan.analyser_en_attente() == 0
        media = dernier_media()
        assert media is not None
        assert media.status is MediaStatus.PENDING
        assert media.scan_detail == "clé VirusTotal absente"


def test_client_virustotal_refuse_une_autre_url() -> None:
    with pytest.raises(ValueError, match="URL refusée"):
        scan.ClientVirusTotal("cle")._requete("GET", "file:///etc/passwd")


def test_purge_des_images_orphelines(app: Flask, client: FlaskClient, createur: User) -> None:
    from datetime import timedelta

    from app.models import utcnow

    connecter(client, "createur@example.org")
    envoyer(client, image())  # utilisée par le quiz enregistré
    champs: dict[str, Any] = formulaire(brouillon(1, "Abandon"), "ajouter-question")
    champs["q-0-image"] = (io.BytesIO(image()), "abandon.png")
    champs["csrf_token"] = jeton_csrf(client, "/createur/quiz/nouveau")
    client.post("/createur/quiz/nouveau", data=champs, content_type="multipart/form-data")
    db.session.expire_all()
    tous = db.session.scalars(select(Media).order_by(Media.id)).all()
    assert len(tous) == 2
    assert medias.purger_orphelins() == 0  # trop récentes
    for m in tous:
        m.created_at = utcnow() - timedelta(hours=25)
    db.session.commit()
    assert medias.purger_orphelins() == 1
    restant = db.session.scalars(select(Media)).all()
    assert [m.uid for m in restant] == [tous[0].uid]
