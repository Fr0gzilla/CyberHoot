"""Formulaires des quiz (l'éditeur, dynamique, est lu par services.quizzes)."""

from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import RadioField, TextAreaField
from wtforms.fields.choices import SelectChoice
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class ReviewForm(FlaskForm):  # type: ignore[misc]
    rating = RadioField(
        "Votre note",
        choices=[SelectChoice(n, f"{n} sur 5") for n in range(5, 0, -1)],
        coerce=int,
        validators=[DataRequired(), NumberRange(1, 5)],
    )
    comment = TextAreaField("Commentaire (facultatif)", validators=[Optional(), Length(max=1000)])


class RejectForm(FlaskForm):  # type: ignore[misc]
    reason = TextAreaField(
        "Motif (envoyé au créateur)",
        validators=[DataRequired(), Length(min=5, max=500)],
    )
