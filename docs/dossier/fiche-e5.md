# Fiche de réalisation — E5 (bloc 2, option SLAM)

**Intitulé** : CyberHoot, plateforme de quiz de sensibilisation à la cybersécurité, en solo et
en direct.

**À compléter** : nom, numéro de candidat, période de réalisation, cadre (projet personnel,
projet de formation, stage), part du travail réalisée seul ou en équipe.

## 1. Contexte

Les établissements scolaires et les petites structures doivent sensibiliser leurs membres aux
risques numériques (hameçonnage, mots de passe, Wi-Fi public, données personnelles). Les
supports existants sont souvent passifs (diaporamas) ; un quiz interactif, notamment en
classe sur le modèle des jeux de questions en direct, rend la sensibilisation plus vivante.

Une première version, Cyber-hoot, avait été réalisée en groupe. Elle fonctionnait en
démonstration mais présentait des défauts bloquants pour une mise en service : schéma de base
désynchronisé, score calculé par le navigateur, failles XSS et CSRF, configuration de
développement par défaut (inventaire complet : [avant-apres.md](../avant-apres.md)).

## 2. Besoin exprimé

- Un **joueur** s'inscrit, joue des quiz publiés, voit la correction expliquée, suit sa
  progression et gagne des badges.
- Un **créateur** rédige des quiz (plusieurs types de questions, images) et les soumet.
- Un **administrateur** valide ou refuse les quiz, gère comptes, catégories et badges, traite
  les signalements, consulte un journal d'audit.
- Un **animateur** lance une partie en direct ; les joueurs la rejoignent sans compte avec un
  code PIN ; points selon la justesse et la rapidité ; classement et podium.
- Contraintes : sécurité exemplaire (sujet de la plateforme), accessibilité, déploiement
  simple en établissement (Docker), aucun service payant.

## 3. Environnement technique

| Domaine | Choix | Raison |
|---------|-------|--------|
| Langage, cadriciel | Python 3.12, Flask 3 (fabrique d'application, blueprints) | Repris de l'ancienne version, adapté à une application de cette taille |
| Données | MySQL 8.4, SQLAlchemy 2, Alembic | Migrations comme seule source du schéma |
| Interface | Gabarits Jinja, Tailwind CSS, JavaScript sans bibliothèque | Pages rendues par le serveur, fonctionnent sans JavaScript ; CSP stricte possible |
| Direct | Interrogation de l'état chaque seconde (pas de WebSocket) | Passe tous les pare-feu d'établissement, reconnexion naturelle |
| Déploiement | Docker Compose : Nginx, application (gunicorn), tâche de fond, MySQL, Redis | Une commande pour tout démarrer |
| Qualité | pytest, ruff, mypy strict, bandit, pip-audit, Trivy, gitleaks, GitHub Actions | Chaque envoi est vérifié automatiquement |

## 4. Réalisations

1. **Modélisation** : règles de gestion numérotées, dictionnaire de données, MCD, MLD,
   diagramme de classes, diagrammes de séquence (partie en direct, correction d'une réponse)
   — [docs/modele/](../modele/README.md). Vingt tables, clés étrangères avec `ON DELETE`
   explicite, contraintes d'unicité (un avis par joueur et par quiz, un pseudo par partie).
2. **Comptes** : inscription avec confirmation par e-mail, connexion, verrouillage,
   réinitialisation, profil, suppression du compte, export de ses données.
3. **Quiz en solo** : catalogue avec recherche et filtres, partie question par question,
   correction calculée par le serveur, reprise d'une partie interrompue, avis.
4. **Éditeur de quiz** : fonctionne sans JavaScript (le serveur relit et réaffiche le
   formulaire), quatre types de questions (choix, vrai/faux, repérer le phishing, remettre
   dans l'ordre), images avec texte alternatif, cycle brouillon → en attente → publié/refusé.
5. **Partie en direct** : code PIN et QR code, salle d'attente, chrono, points de rapidité,
   histogramme des réponses, classement, pause, exclusion, export CSV. Transitions par mise à
   jour conditionnelle sur un numéro de version : deux clics simultanés ne font avancer la
   partie qu'une fois. Testé avec 200 joueurs.
6. **Progression** : 18 badges, séries de jours, réussite par thème.
7. **Administration** : tableau de bord, validation des quiz, comptes et rôles, catégories,
   badges, signalements, journal d'audit.
8. **Finition** : accessibilité WCAG 2.2 AA, HTTPS, documentation.

## 5. Compétences du bloc 2 mobilisées

| Compétence | Mise en œuvre | Preuve |
|------------|---------------|--------|
| **Concevoir et développer une solution applicative** | Analyse du besoin, modélisation, architecture en couches (routes minces, services métier, modèles), quatre types de questions partageant une règle de correction unique | `docs/modele/`, `app/services/correction.py`, `app/services/` |
| | Interface adaptée (téléphone d'abord, thèmes clair et sombre, accessibilité) | `docs/accessibilite.md`, captures du README |
| | Tests unitaires et fonctionnels du comportement | `tests/` (plus de 230 tests, couverture 94 %) |
| **Assurer la maintenance corrective ou évolutive** | Reprise d'une application existante : inventaire de 20 défauts et correction de chacun avec un test de non-régression | `docs/avant-apres.md` |
| | Six versions successives, journal des versions, intégration continue | `CHANGELOG.md`, `.github/workflows/ci.yml` |
| | Corrections issues des tests de charge (interblocage MySQL lors des arrivées simultanées, limites de débit inadaptées à une classe) | `docs/charge-v2.0.md` |
| **Gérer les données** | Schéma unique (migrations Alembic), schéma SQL généré et comparé en intégration continue | `migrations/`, `docs/modele/schema.sql` |
| | Requêtes d'agrégation (statistiques, classement, progression par thème), mises à jour atomiques (score additionné par la base) | `app/services/admin.py`, `app/services/live_bilan.py`, `app/services/live.py` |
| | Données personnelles : export, suppression, purges planifiées | `app/services/rgpd.py`, `docs/rgpd/registre.md` |

## 6. Difficultés rencontrées et solutions

**À compléter** avec les difficultés vécues. Pistes documentées dans le dépôt :

- Tests qui échouaient seulement sur MySQL (lectures en isolation « REPEATABLE READ ») :
  isolation de chaque requête de test et annulation de la transaction.
- Interblocage MySQL quand 200 joueurs rejoignent en même temps : l'arrivée d'un joueur ne
  modifie plus la partie elle-même (`docs/charge-v2.0.md`).
- En HTTPS sur un port non standard, la vérification CSRF refusait les formulaires : le proxy
  transmettait l'hôte sans son port (corrigé en v3.0, `CHANGELOG.md`).

## 7. Bilan et perspectives

**À compléter.** Évolutions possibles : notifications en temps réel par WebSocket pour les
très grandes salles, import de questions depuis un tableur, traduction de l'interface,
statistiques par classe pour un enseignant.
