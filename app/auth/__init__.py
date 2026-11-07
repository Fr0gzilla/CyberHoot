"""Comptes et authentification."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from flask import abort
from flask_login import current_user, login_required

F = TypeVar("F", bound=Callable[..., Any])


def role_required(*noms: str) -> Callable[[F], F]:
    """Exige une connexion et au moins un des rôles donnés (relus en base à chaque requête)."""

    def decorateur(vue: F) -> F:
        @wraps(vue)
        def enveloppe(*args: Any, **kwargs: Any) -> Any:
            if not any(current_user.has_role(nom) for nom in noms):
                abort(403)
            return vue(*args, **kwargs)

        return cast(F, login_required(enveloppe))

    return decorateur
