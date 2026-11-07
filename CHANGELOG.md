# Journal des versions

## v1.1 — Quiz solides

- Catalogue : recherche, filtres par catégorie et niveau, pagination, note moyenne.
- Parties en solo : une question à la fois, correction et explication après chaque réponse,
  reprise d'une partie interrompue, résultat détaillé, historique sur le profil.
  Le serveur seul connaît les bonnes réponses et calcule le score ; réponses stockées en JSON.
- Questions à une ou plusieurs bonnes réponses ; boutons de couleur et de forme distinctes.
- Éditeur de quiz sans JavaScript (ajout, retrait, déplacement de questions et de réponses),
  un seul service partagé par créateurs et administrateurs.
- Cycle de validation : brouillon, soumission, publication ou refus motivé (e-mail au créateur),
  dépublication, retour en validation après modification.
- Images : contrôle du format réel, ré-encodage sans métadonnées, analyse antivirus en tâche de
  fond (worker, VirusTotal ou mode simulé), publication bloquée tant qu'une image n'est pas
  analysée, purge des images abandonnées.
- Avis (un par joueur et par quiz, après une partie), statistiques du créateur (parties, score
  moyen, réussite par question).
- 8 catégories de référence, 2 quiz de démonstration originaux (`make demo`).
- Commandes : `donner-role`, `charger-demo`, `analyser-medias`.

## v1.0 — Socle sécurisé

- Comptes : inscription avec confirmation de l'adresse e-mail, connexion, déconnexion,
  mot de passe oublié, profil (pseudo, mot de passe), suppression du compte.
- Sécurité : Argon2id, politique de mots de passe, verrouillage après 5 échecs, réponses
  qui ne révèlent pas l'existence d'un compte, jetons à usage unique hachés, sessions
  fermées au changement de mot de passe, CSRF, CSP à nonce sans `unsafe-inline`, en-têtes
  de sécurité, limitation de débit (Redis), redirections internes seulement.
- Exploitation : configuration de production par défaut, secrets obligatoires, journal JSON
  avec identifiant de requête, sonde `/health`, purge des comptes jamais activés.
- Docker : image multi-étapes, compte sans privilège, lecture seule, Nginx seul exposé.
- Qualité : migrations Alembic seule source du schéma, tests sur MySQL, mypy strict, ruff,
  bandit, pip-audit, Trivy, recherche de secrets.
- Interface : identité « terminal » reprise de Cyber-hoot, thèmes clair et sombre, mobile
  d'abord, focus visible, formulaires accessibles.
