# Commandes du projet. Tout passe par Docker : seul Docker (Compose v2) est nécessaire.
.DEFAULT_GOAL := help
COMPOSE := docker compose
TEST_IMAGE := cyberhoot:test

.PHONY: help secrets install verify test lint smoke up down logs admin schema lock css clean

help: ## Affiche cette aide
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

secrets: ## Génère les secrets locaux (une seule fois, jamais versionnés)
	@# Dossier fermé (700) ; fichiers lisibles (644) pour le compte sans privilège du conteneur.
	@mkdir -p secrets && chmod 700 secrets
	@for f in secret_key db_password db_root_password; do \
	  [ -s secrets/$$f ] || { openssl rand -base64 48 | tr -d '\n' > secrets/$$f; chmod 644 secrets/$$f; echo "secrets/$$f créé"; }; \
	done

install: secrets ## Construit les images (application et vérification)
	docker build --target test -t $(TEST_IMAGE) .
	$(COMPOSE) build

verify: ## Lint, format, types, analyse de sécurité, tests et couverture
	docker build -q --target test -t $(TEST_IMAGE) . >/dev/null
	docker run --rm $(TEST_IMAGE)
	docker run --rm $(TEST_IMAGE) pip-audit -r requirements.txt --strict --progress-spinner off

test: ## Tests seuls (rapide)
	docker build -q --target test -t $(TEST_IMAGE) . >/dev/null
	docker run --rm $(TEST_IMAGE) pytest

up: secrets ## Démarre la pile (http://localhost:8080)
	$(COMPOSE) up -d --build --wait

down: ## Arrête la pile (les données restent)
	$(COMPOSE) down

logs: ## Suit les journaux de l'application
	$(COMPOSE) logs -f app

smoke: up ## Démarre la pile et vérifie qu'elle répond
	@curl -fsS http://localhost:$${HTTP_PORT:-8080}/health && echo
	@curl -fsS -o /dev/null -w "accueil : %{http_code}\n" http://localhost:$${HTTP_PORT:-8080}/

admin: ## Crée un compte administrateur (questions interactives)
	$(COMPOSE) exec app flask --app wsgi creer-admin

schema: ## Régénère docs/modele/schema.sql depuis les migrations
	docker build -q --target test -t $(TEST_IMAGE) . >/dev/null
	docker run --rm -e DATABASE_URL=mysql+pymysql://x:x@localhost/cyberhoot $(TEST_IMAGE) \
	  alembic upgrade head --sql > docs/modele/schema.sql

lock: ## Recalcule les versions figées (avec empreintes) des dépendances Python
	docker run --rm -v "$$PWD":/src -w /src python:3.12-slim sh -c '\
	  pip install -q pip-tools==7.4.1 && \
	  pip-compile -q --generate-hashes --strip-extras --allow-unsafe -o requirements.txt requirements.in && \
	  pip-compile -q --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.txt requirements-dev.in'

css: ## Compile la feuille de style en local (développement)
	npm ci && npm run build:css

clean: ## Supprime les conteneurs ET les données de la base
	$(COMPOSE) down -v
