"""Images téléversées : contrôle du vrai format, ré-encodage, stockage hors du dépôt.

Ce qui est vérifié avant d'accepter un fichier :
- taille maximale (MEDIA_MAX_BYTES) ;
- format réel lu par Pillow (signature du fichier, pas l'extension ni l'en-tête du client) :
  PNG, JPEG ou WebP seulement ;
- dimensions raisonnables (protection contre les « bombes de décompression ») ;
- ré-encodage complet : les métadonnées (EXIF, GPS…) et tout contenu caché disparaissent ;
- nom aléatoire : le nom d'origine n'est jamais réutilisé.

L'image est ensuite analysée en tâche de fond (services.scan) et n'est servie qu'une fois
déclarée saine.
"""

from __future__ import annotations

import hashlib
import io
import secrets
from datetime import timedelta
from pathlib import Path

from flask import current_app
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import Media, MediaStatus, Question, User, utcnow

FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
DIMENSION_MAX = 4000
# Refus au-delà de ce nombre de pixels, avant même de décoder l'image.
Image.MAX_IMAGE_PIXELS = DIMENSION_MAX * DIMENSION_MAX


class MediaInvalideError(ValueError):
    """Fichier refusé ; le message est affichable tel quel."""


def dossier() -> Path:
    chemin = Path(current_app.config["UPLOAD_DIR"])
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def _reencoder(brut: bytes) -> tuple[bytes, str]:
    try:
        with Image.open(io.BytesIO(brut)) as image:
            format_lu = image.format or ""
            if format_lu not in FORMATS:
                raise MediaInvalideError(
                    "Format refusé : seules les images PNG, JPEG et WebP sont acceptées."
                )
            largeur, hauteur = image.size
            if largeur > DIMENSION_MAX or hauteur > DIMENSION_MAX:
                raise MediaInvalideError(
                    f"Image trop grande (maximum {DIMENSION_MAX} × {DIMENSION_MAX} pixels)."
                )
            image.load()
            sortie = io.BytesIO()
            if format_lu == "JPEG":
                image.convert("RGB").save(sortie, "JPEG", quality=85, optimize=True)
            elif format_lu == "PNG":
                image.save(sortie, "PNG", optimize=True)
            else:
                image.save(sortie, "WEBP", quality=85)
    except MediaInvalideError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise MediaInvalideError("Ce fichier n'est pas une image valide.") from exc
    return sortie.getvalue(), FORMATS[format_lu]


def enregistrer(fichier: FileStorage, proprietaire: User) -> Media:
    """Valide, ré-encode et stocke l'image ; renvoie le média en attente d'analyse."""
    maximum = current_app.config["MEDIA_MAX_BYTES"]
    brut = fichier.stream.read(maximum + 1)
    if not brut:
        raise MediaInvalideError("Le fichier est vide.")
    if len(brut) > maximum:
        raise MediaInvalideError(f"Image trop lourde (maximum {maximum // (1024 * 1024)} Mo).")
    contenu, mime = _reencoder(brut)
    media = Media(
        uid=secrets.token_hex(16),
        owner_id=proprietaire.id,
        mime_type=mime,
        size=len(contenu),
        sha256=hashlib.sha256(contenu).hexdigest(),
        status=MediaStatus.PENDING,
    )
    (dossier() / media.filename).write_bytes(contenu)
    db.session.add(media)
    db.session.flush()
    return media


def chemin(media: Media) -> Path:
    return dossier() / media.filename


def supprimer_fichier(media: Media) -> None:
    chemin(media).unlink(missing_ok=True)


DELAI_ORPHELIN = timedelta(hours=24)


def purger_orphelins() -> int:
    """Supprime les images envoyées puis abandonnées (aucune question) depuis plus de 24 h."""
    limite = utcnow() - DELAI_ORPHELIN
    utilisees = select(Question.media_id).where(Question.media_id.is_not(None))
    orphelins = db.session.scalars(
        select(Media).where(Media.created_at < limite, Media.id.not_in(utilisees))
    ).all()
    for orphelin in orphelins:
        supprimer_fichier(orphelin)
        db.session.delete(orphelin)
    db.session.commit()
    return len(orphelins)
