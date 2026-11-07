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
| **v1.1 — Quiz solides** | Catalogue (recherche, filtres, notes), parties en solo corrigées côté serveur, éditeur de quiz, validation par un administrateur, images analysées, avis, statistiques | ✅ |
| **v2.0 — En direct** | Parties en direct : code PIN et QR code, salle d'attente, chrono, points selon la rapidité, histogramme, classement et podium, pause, exclusion, export CSV ; testé avec 200 joueurs ([rapport](docs/charge-v2.0.md)) | ✅ |
| **v2.1 — Contenu cyber** | Questions vrai/faux, « repérer le phishing » et « remettre dans l'ordre », 18 badges, progression par thème et séries, 8 quiz de démonstration de 10 questions | ✅ |
| v2.2 — Administrer | Double authentification, journal d'audit, données personnelles | à venir |
| v3.0 — Finition | Accessibilité complète, HTTPS, dossier technique | à venir |

## Démarrer

Seul **Docker** (avec Compose v2) est nécessaire.

```bash
make secrets   # génère les secrets locaux dans secrets/ (jamais versionnés)
make up        # construit et démarre la pile : http://localhost:8080
make admin     # crée un compte administrateur
make demo      # ajoute les quiz de démonstration (auteur : le compte demandé)
```

Donner le rôle de créateur à un compte :
`docker compose exec app flask --app wsgi donner-role --email <adresse> --role creator`.

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
                        ├──► Redis      (compteurs de limitation de débit, réseau interne)
                        └──► volume des images ◄── worker : analyse antivirus en tâche de fond
                                                    (VirusTotal ou mode simulé)
```

- `app/` : fabrique d'application, blueprints (`auth`, `account`, `main`, `quiz`, `creator`,
  `admin`), services métier (`services/`), modèles (`models/`).
- `migrations/` : migrations Alembic, **seule source du schéma** de la base.
- `docs/modele/` : règles de gestion, dictionnaire, MCD, MLD, diagrammes, schéma SQL généré.
- `tests/` : tests du comportement, exécutés sur MySQL en intégration continue.
- `outils/charge_direct.py` : test de charge d'une partie en direct.

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
- Quiz : le navigateur ne reçoit jamais les bonnes réponses avant d'avoir répondu et n'envoie
  jamais de score ; le serveur corrige chaque réponse, une seule fois, dans l'ordre.
- Direct : chrono et points calculés avec l'heure du serveur ; une réponse par joueur et par
  question ; changements d'écran par mise à jour conditionnelle (aucun double déclenchement) ;
  seuls les codes PIN faux sont fortement limités ; données des joueurs effacées sous 24 h.
- Images : format réel vérifié, ré-encodage (métadonnées retirées), nom aléatoire, analyse
  antivirus avant toute diffusion.
- Contrôle d'accès vérifié côté serveur sur chaque page : un brouillon, une partie ou une image
  d'un autre utilisateur répondent « introuvable ».

Pour signaler une faille : voir [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE)
