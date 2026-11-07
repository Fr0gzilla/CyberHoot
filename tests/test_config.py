"""Configuration : production par défaut, secrets obligatoires, valeurs d'exemple refusées."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import ConfigurationError, charger_config, lire_secret
from app.services import passwords

CLE = "k" * 16 + "9" * 16 + "z" * 8


@pytest.fixture(autouse=True)
def environnement_propre(monkeypatch: pytest.MonkeyPatch) -> None:
    for nom in (
        "APP_ENV",
        "SECRET_KEY",
        "SECRET_KEY_FILE",
        "DATABASE_URL",
        "DB_PASSWORD",
        "DB_PASSWORD_FILE",
        "COOKIE_SECURE",
        "MAIL_BACKEND",
    ):
        monkeypatch.delenv(nom, raising=False)


def test_production_par_defaut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", CLE)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    config = charger_config()
    assert config.APP_ENV == "production"
    assert config.DEBUG is False
    assert config.SESSION_COOKIE_SECURE is True
    assert config.SESSION_COOKIE_HTTPONLY is True


def test_refus_sans_cle_secrete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    with pytest.raises(ConfigurationError, match="SECRET_KEY"):
        charger_config()


@pytest.mark.parametrize("valeur", ["changeme", "cle_secrete_a_changer_en_production", "court"])
def test_refus_cle_d_exemple_ou_trop_courte(monkeypatch: pytest.MonkeyPatch, valeur: str) -> None:
    monkeypatch.setenv("SECRET_KEY", valeur)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    with pytest.raises(ConfigurationError):
        charger_config()


def test_secret_lu_dans_un_fichier(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fichier = tmp_path / "secret_key"
    fichier.write_text(CLE + "\n", encoding="utf-8")
    monkeypatch.setenv("SECRET_KEY_FILE", str(fichier))
    assert lire_secret("SECRET_KEY") == CLE


def test_fichier_de_secret_illisible(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SECRET_KEY_FILE", str(tmp_path / "absent"))
    with pytest.raises(ConfigurationError, match="illisible"):
        lire_secret("SECRET_KEY")


def test_url_mysql_construite_avec_mot_de_passe_echappe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", CLE)
    monkeypatch.setenv("DB_PASSWORD", "p@ss:w/rd#2026")
    url = charger_config().SQLALCHEMY_DATABASE_URI
    assert url.startswith("mysql+pymysql://cyberhoot:p%40ss%3Aw%2Frd%232026@db:3306/")


def test_mode_developpement_explicite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", CLE)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    config = charger_config()
    assert config.DEBUG is True
    assert config.SESSION_COOKIE_SECURE is False


def test_environnement_inconnu_refuse() -> None:
    with pytest.raises(ConfigurationError):
        charger_config("staging")


def test_mode_d_envoi_inconnu_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", CLE)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("MAIL_BACKEND", "pigeon")
    with pytest.raises(ConfigurationError):
        charger_config()


class TestPolitiqueMotsDePasse:
    def test_phrase_de_passe_acceptee(self) -> None:
        assert passwords.problemes("cheval agrafe batterie correct") == []

    def test_trop_peu_de_caracteres_differents(self) -> None:
        assert passwords.problemes("abababababababab")

    def test_trop_long(self) -> None:
        assert passwords.problemes("a1b2c3d4" * 20)

    def test_contient_la_partie_locale_de_l_email(self) -> None:
        assert passwords.problemes("jean.dupont-2026!", email="jean.dupont@example.org")

    def test_hachage_argon2id_et_verification(self) -> None:
        empreinte = passwords.hacher("phrase de test longue")
        assert empreinte.startswith("$argon2id$")
        assert passwords.verifier(empreinte, "phrase de test longue")
        assert not passwords.verifier(empreinte, "autre phrase")
        assert not passwords.verifier("empreinte-invalide", "x")
