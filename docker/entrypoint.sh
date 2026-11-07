#!/bin/sh
# Démarrage du conteneur : attend la base, applique les migrations et purge les comptes
# jamais activés (application seulement), puis lance la commande demandée.
set -eu

essais=0
until python -c "
from sqlalchemy import create_engine, text
from app.config import charger_config
moteur = create_engine(charger_config().SQLALCHEMY_DATABASE_URI)
with moteur.connect() as c:
    c.execute(text('SELECT 1'))
" >/dev/null 2>&1; do
  essais=$((essais + 1))
  if [ "$essais" -ge 30 ]; then
    echo "base de données injoignable après 60 s" >&2
    exit 1
  fi
  sleep 2
done

# Un seul conteneur (l'application) applique les migrations ; le worker attend qu'il soit prêt.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  alembic upgrade head
  flask --app wsgi purger-comptes
fi
exec "$@"
