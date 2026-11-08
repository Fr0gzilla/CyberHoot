# Journal des versions

## v3.0 — Finition

- HTTPS au proxy : TLS 1.2 et 1.3, HTTP/2, redirection permanente depuis HTTP, HSTS (un an),
  cookies `Secure` par défaut ; certificat auto-signé créé par `make secrets` ; guide pour un
  vrai certificat Let's Encrypt (`docs/https.md`). L'hôte est transmis avec son port, ce qui
  corrige le refus CSRF (`Referer`) en HTTPS sur un port non standard.
- Accessibilité : revue WCAG 2.2 AA outillée (`make accessibilite` : axe-core sur 30 pages en
  thème clair et sombre, parcours au clavier seul) ; liens soulignés dans le texte, titre de
  niveau 1 sur les écrans de question, focus sur le premier champ fautif. Rapport :
  `docs/accessibilite.md`.
- `docs/avant-apres.md` : les 20 défauts de l'ancienne version, leur correction et le test qui
  le prouve.
- Nouveaux contrôles automatiques : aucun fichier de plus de 400 lignes, aucun HTML injecté
  par le JavaScript, documentation d'accord avec la configuration, aucun fichier versionné
  ignoré, règle ruff contre les `except` trop larges.
- Découpage des services trop longs : bilan et classement du direct, pseudos, entretien,
  décision de l'administrateur (`moderation`), réception des images dans `media`.
- `SECURITY.md` complété ; captures d'écran dans le README ; dossier technique
  (`docs/dossier/`).
- gunicorn 26 : interface de pilotage désactivée (système de fichiers en lecture seule).

## v2.2 — Administrer

- Double authentification TOTP : activation par code QR, connexion en deux étapes (5 min),
  secret chiffré en base, chaque code utilisable une seule fois, 10 codes de secours hachés,
  codes faux comptés dans le verrouillage. Obligatoire pour accéder à l'administration.
- Journal d'audit : connexions (réussies, échouées, verrouillages), mots de passe, double
  authentification, suppressions, exports, toutes les actions d'administration ; adresse IP ;
  consultation filtrable ; aucune modification possible ; purge après 12 mois.
- Administration : tableau de bord (comptes, joueurs actifs, parties, direct, signalements,
  parties par jour), gestion des comptes (recherche, rôles, désactivation, garde-fous : pas sur
  soi-même, toujours un administrateur), catégories, badges (nom, description, icône, seuil).
- Signalements de quiz et d'avis par les joueurs ; traitement par les administrateurs
  (classer, supprimer l'avis, dépublier le quiz).
- Données personnelles : export complet en JSON depuis le profil, registre des traitements
  (`docs/rgpd/registre.md`), politique de confidentialité complétée.

## v2.1 — Contenu cyber

- Nouveaux types de questions, en solo comme en direct :
  - **vrai ou faux** ;
  - **repérer le phishing** : un faux e-mail ou SMS (expéditeur, objet, texte) dont le joueur
    touche les passages suspects ; correction surlignée, indices manqués signalés ;
  - **remettre dans l'ordre** : étapes présentées mélangées (mélange stable pendant la
    partie), rang à choisir pour chacune.
- Une seule règle de correction partagée par le solo et le direct (`services/correction.py`).
- Éditeur : type par question, champs propres au phishing, vrai/faux préparé automatiquement.
- 18 badges définis une seule fois (migration) : première partie, série de jours, sans faute,
  « maillon faible », expert de chaque thème, maître de cérémonie, champion de la salle,
  auteur publié… attribués par un service unique et annoncés au joueur.
- Progression : réussite par thème, parties jouées, série en cours et record, badges ; page
  publique des badges.
- Icônes locales des 8 catégories.
- 8 quiz de démonstration originaux de 10 questions, avec sources publiques.

## v2.0 — En direct

- Parties en direct : l'animateur lance un quiz publié et projette un code PIN à 6 chiffres et
  un QR code ; les joueurs rejoignent sur leur téléphone, avec ou sans compte.
- Salle d'attente, chrono par question (10 à 60 s), correction automatique à la fin du chrono
  ou quand tout le monde a répondu, histogramme des réponses, classement, podium.
- Points : 500 par bonne réponse, plus jusqu'à 500 selon la rapidité, calculés avec l'heure du
  serveur ; pause et reprise sans pénalité.
- Animateur : pause, question suivante, exclusion d'un joueur, fin de partie, export CSV du
  classement (protégé contre l'injection de formules).
- Robustesse : changements d'écran par mise à jour conditionnelle (double clic sans effet),
  reconnexion d'un joueur, pseudos filtrés, parties abandonnées terminées après 3 h et
  effacées 24 h après la fin, résultats des joueurs connectés dans leur historique.
- Écrans mis à jour par interrogation de l'état chaque seconde (pas de WebSocket : passe les
  pare-feu d'établissement) ; fonctionne aussi sans JavaScript (rechargement automatique).
- Test de charge : 200 joueurs derrière une même adresse IP ; il a révélé et fait corriger un
  interblocage MySQL et des limites de débit inadaptées à une salle de classe.

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
