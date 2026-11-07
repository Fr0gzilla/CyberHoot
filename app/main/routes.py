"""Pages publiques et sonde de santé."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, render_template
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.wrappers import Response

from app.extensions import db

bp = Blueprint("main", __name__)
journal = logging.getLogger(__name__)


@bp.get("/")
def index() -> str:
    return render_template("main/index.html")


@bp.get("/confidentialite")
def privacy() -> str:
    return render_template("main/privacy.html")


@bp.get("/health")
def health() -> tuple[Response, int]:
    """Sonde du conteneur et du proxy : l'application répond et la base aussi."""
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        journal.exception("sonde de santé : base injoignable")
        return jsonify(status="degrade"), 503
    return jsonify(status="ok"), 200
