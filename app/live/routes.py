"""Parties en direct : rejoindre (PIN), jouer (téléphone), animer (projecteur)."""

from __future__ import annotations

import segno
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from markupsafe import Markup
from werkzeug.wrappers import Response as WResponse

from app.auth import role_required
from app.auth.forms import ConfirmForm
from app.extensions import db, limiter
from app.models import LiveGame, LivePlayer, LiveStatus, Quiz, RoleName
from app.services import correction, live, live_bilan, play

bp = Blueprint("live", __name__)

CLE_SESSION = "direct"


# --- Utilitaires ---------------------------------------------------------------------------


def _partie(game_id: int) -> LiveGame:
    partie = db.session.get(LiveGame, game_id)
    if partie is None:
        abort(404)
    return partie


def _est_hote(partie: LiveGame) -> bool:
    if not current_user.is_authenticated:
        return False
    return bool(partie.host_id == current_user.id or current_user.has_role(RoleName.ADMIN))


def _partie_animee(game_id: int) -> LiveGame:
    partie = _partie(game_id)
    if not _est_hote(partie):
        abort(404)
    return partie


def _joueur(partie: LiveGame) -> LivePlayer | None:
    jetons: dict[str, str] = session.get(CLE_SESSION, {})
    return live.joueur_par_jeton(partie, jetons.get(str(partie.id)))


def _retenir(partie: LiveGame, joueur: LivePlayer) -> None:
    jetons: dict[str, str] = dict(session.get(CLE_SESSION, {}))
    jetons[str(partie.id)] = joueur.token
    # Seules les dernières parties sont gardées : la session reste petite.
    session[CLE_SESSION] = dict(list(jetons.items())[-5:])


# --- Joueur --------------------------------------------------------------------------------


@bp.route("/", methods=["GET", "POST"])
# Une salle entière peut rejoindre depuis la même adresse (réseau d'établissement) : seuls les
# codes faux sont fortement limités, ce qui rend vain l'essai des codes un par un.
@limiter.limit(
    "30 per minute;300 per hour", methods=["POST"], deduct_when=lambda r: r.status_code == 404
)
@limiter.limit("300 per minute", methods=["POST"])
def join() -> str | WResponse | tuple[str, int]:
    form = ConfirmForm()
    pin = request.values.get("pin", "").strip()[:7]
    pseudo = request.form.get("pseudo", "").strip()[:40]
    if request.method == "GET":
        if not pseudo and current_user.is_authenticated:
            pseudo = current_user.username[:20]
        return render_template("live/join.html", form=form, pin=pin, pseudo=pseudo, erreur=None)
    if not form.validate_on_submit():
        abort(400)
    partie = live.trouver_par_pin(pin)
    if partie is None:
        # Même réponse quel que soit le PIN : pas d'indice pour qui essaierait de les deviner.
        return render_template(
            "live/join.html",
            form=form,
            pin=pin,
            pseudo=pseudo,
            erreur="Aucune partie ouverte avec ce code.",
        ), 404
    deja = _joueur(partie)
    if deja is not None:
        return redirect(url_for("live.player", game_id=partie.id))
    entree = live.rejoindre(
        partie,
        pseudo,
        current_user._get_current_object() if current_user.is_authenticated else None,
    )
    if entree.joueur is None:
        message = entree.refus.value if entree.refus else "Impossible de rejoindre."
        return render_template(
            "live/join.html", form=form, pin=pin, pseudo=pseudo, erreur=message
        ), 422
    _retenir(partie, entree.joueur)
    return redirect(url_for("live.player", game_id=partie.id))


@bp.route("/jouer/<int:game_id>", methods=["GET", "POST"])
# Une réponse par joueur et par question, quelle que soit la taille de la salle.
@limiter.limit("3000 per minute", methods=["POST"])
def player(game_id: int) -> str | WResponse:
    partie = _partie(game_id)
    joueur = _joueur(partie)
    if joueur is None:
        if partie.active and partie.pin:
            flash("Rejoignez la partie avec son code.", "info")
            return redirect(url_for("live.join", pin=partie.pin))
        abort(404)
    form = ConfirmForm()
    erreur = None
    if request.method == "POST":
        if not form.validate_on_submit():
            abort(400)
        question = live.question_courante(partie)
        choix = correction.lire(question, request.form) if question else []
        resultat = live.repondre(partie, joueur, request.form.get("position", -1, type=int), choix)
        if isinstance(resultat, live.RefusReponse | correction.Refus):
            erreur = resultat.value
        else:
            return redirect(url_for("live.player", game_id=partie.id))
    live.actualiser(partie)
    db.session.refresh(joueur)
    reponse = live_bilan.reponse_de(partie, joueur, partie.current_index)
    en_train_de_choisir = partie.status is LiveStatus.QUESTION and reponse is None
    question = live.question_courante(partie)
    return render_template(
        "live/player.html",
        partie=partie,
        joueur=joueur,
        question=question,
        options=correction.ordre_affiche(question, joueur.token) if question else [],
        reponse=reponse,
        rafraichir=not en_train_de_choisir,
        rang=live_bilan.rang(partie, joueur),
        form=form,
        erreur=erreur,
        etat=live.etat(partie),
    )


@bp.get("/<int:game_id>/etat")
def state(game_id: int) -> tuple[WResponse, int]:
    """Interrogé chaque seconde par les écrans : seulement pour l'animateur et les joueurs."""
    partie = _partie(game_id)
    if not (_est_hote(partie) or _joueur(partie) is not None):
        abort(404)
    reponse = jsonify(live.etat(partie))
    reponse.headers["Cache-Control"] = "no-store"
    return reponse, 200


# --- Animateur -----------------------------------------------------------------------------


@bp.post("/lancer/<int:quiz_id>")
@role_required(RoleName.CREATOR, RoleName.ADMIN)
@limiter.limit("30 per hour")
def launch(quiz_id: int) -> WResponse:
    quiz = db.session.get(Quiz, quiz_id)
    if quiz is None or not play.jouable(quiz):
        abort(404)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    chrono = request.form.get("chrono", 20, type=int) or 20
    partie = live.creer(current_user._get_current_object(), quiz, chrono)
    return redirect(url_for("live.host", game_id=partie.id))


def _qr(partie: LiveGame) -> Markup | None:
    if not partie.pin:
        return None
    lien = f"{current_app.config['PUBLIC_URL']}{url_for('live.join', pin=partie.pin)}"
    svg = segno.make(lien, error="m").svg_inline(
        scale=6,
        dark="#07100a",
        light="#ffffff",
        omitsize=True,
        title="Code QR pour rejoindre la partie",
    )
    # Produit par segno à partir de notre propre URL : aucun contenu venu d'un utilisateur.
    return Markup(svg)  # noqa: S704  # nosec B704


@bp.get("/animer/<int:game_id>")
def host(game_id: int) -> str:
    partie = _partie_animee(game_id)
    live.actualiser(partie)
    question = live.question_courante(partie)
    return render_template(
        "live/host.html",
        partie=partie,
        question=question,
        joueurs=live.joueurs_actifs(partie),
        classement=live_bilan.classement(partie, 5 if partie.active else None),
        histogramme=live_bilan.histogramme(partie) if question else {},
        reussite=live_bilan.reussite(partie) if question else (0, 0),
        options=correction.ordre_affiche(question, f"animateur-{partie.id}") if question else [],
        etat=live.etat(partie),
        qr=_qr(partie),
        lien_rejoindre=f"{current_app.config['PUBLIC_URL']}{url_for('live.join')}",
        rafraichir=True,
        form=ConfirmForm(),
    )


ACTIONS = {
    "demarrer": live.demarrer,
    "suivant": live.suivant,
    "pause": live.pause,
    "reprendre": live.reprendre,
    "terminer": live.terminer,
}


@bp.post("/animer/<int:game_id>/<action>")
def host_action(game_id: int, action: str) -> WResponse:
    partie = _partie_animee(game_id)
    if not ConfirmForm().validate_on_submit():
        abort(400)
    if action == "exclure":
        live.exclure(partie, request.form.get("joueur", type=int) or 0)
    elif action in ACTIONS:
        ACTIONS[action](partie)
    else:
        abort(404)
    return redirect(url_for("live.host", game_id=partie.id))


@bp.get("/animer/<int:game_id>/classement.csv")
def export(game_id: int) -> Response:
    partie = _partie_animee(game_id)
    return Response(
        "\ufeff" + live_bilan.export_csv(partie),  # BOM : accents corrects dans un tableur
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="classement-{partie.id}.csv"'},
    )
