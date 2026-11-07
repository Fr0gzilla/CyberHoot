# CyberHoot

Plateforme de quiz pour apprendre les bons réflexes de cybersécurité : hameçonnage, mots de
passe, Wi-Fi public, données personnelles… à faire seul ou en direct avec toute une salle.

Refonte complète de Cyber-hoot, projet de groupe réalisé en BTS SIO (dépôt d'origine :
[lele214/Cyber-hoot](https://github.com/lele214/Cyber-hoot)).

[![Intégration continue](https://github.com/Fr0gzilla/CyberHoot/actions/workflows/ci.yml/badge.svg)](https://github.com/Fr0gzilla/CyberHoot/actions/workflows/ci.yml)

## Feuille de route

| Version | Contenu | État |
|---------|---------|------|
| **v1.0 — Socle sécurisé** | Comptes (inscription avec confirmation par e-mail, connexion, verrouillage, mot de passe oublié, profil, suppression), protections CSRF, CSP stricte, limitation de débit, Docker durci, intégration continue | ✅ |
| v1.1 — Quiz solides | Catalogue, parties en solo corrigées côté serveur, création et validation des quiz, médias analysés | à venir |
| v2.0 — En direct | Parties en direct avec code PIN, chrono, classement en temps réel | à venir |
| v2.1 — Contenu cyber | Questions « repérer le phishing », catégories, badges et progression | à venir |
| v2.2 — Administrer | Double authentification, journal d'audit, données personnelles | à venir |
| v3.0 — Finition | Accessibilité complète, HTTPS, dossier technique | à venir |

## Démarrer

Seul **Docker** (avec Compose v2) est nécessaire.

```bash
make secrets   # génère les secrets locaux dans secrets/ (jamais versionnés)
make up        # construit et démarre la pile : http://localhost:8080
make admin     # crée un compte administrateur
```

En local, les e-mails ne partent pas : leur envoi est noté dans le journal (`make logs`).
Pour voir aussi leur contenu (liens d'activation), démarrez en mode développement :
`APP_ENV=development` dans l'environnement du service `app`.

| Commande | Rôle |
|----------|------|
| `make verify` | Lint, format, types (mypy strict), analyse de sécurité (bandit, pip-audit), tests et couverture |
| `make test` | Tests seuls |
| `make smoke` | Démarre la pile et vérifie qu'elle répond |
| `make schema` | Régénère `docs/modele/schema.sql` depuis les migrations |
| `make lock` | Recalcule les versions figées des dépendances |
| `make down` / `make clean` | Arrête la pile / l'arrête et efface la base |

## Architecture

```
Navigateur ──► Nginx (seul port publié, limite de débit)
                 └──► Flask + gunicorn (compte sans privilège, système de fichiers en lecture seule)
                        ├──► MySQL 8.4  (réseau interne uniquement)
                        └──► Redis      (compteurs de limitation de débit, réseau interne)
```

- `app/` : fabrique d'application, blueprints (`auth`, `account`, `main`), services métier
  (`services/`), modèles (`models/`).
- `migrations/` : migrations Alembic, **seule source du schéma** de la base.
- `docs/modele/` : règles de gestion, dictionnaire, MCD, MLD, diagrammes, schéma SQL généré.
- `tests/` : tests du comportement, exécutés sur MySQL en intégration continue.

## Sécurité

- Mots de passe : Argon2id, 12 caractères minimum, refus des mots de passe courants et de ceux
  qui contiennent le pseudo ou l'e-mail ; verrouillage après 5 échecs.
- Aucune réponse ne révèle si une adresse e-mail a un compte (inscription, connexion, oubli).
- Jetons d'activation et de réinitialisation à usage unique, à durée limitée, stockés hachés.
- Changer de mot de passe ferme toutes les autres sessions.
- Protection CSRF sur tous les formulaires ; CSP sans `unsafe-inline` ; aucun JavaScript en
  ligne ; en-têtes de sécurité complets.
- Configuration de production par défaut : l'application refuse de démarrer sans vrai secret.
- Conteneurs durcis : compte sans privilège, lecture seule, capacités retirées ; base et Redis
  injoignables depuis l'extérieur.

Pour signaler une faille : voir [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE)
