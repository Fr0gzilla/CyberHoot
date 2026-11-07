# Journal des versions

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
