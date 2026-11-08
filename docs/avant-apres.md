# Avant / après : les défauts de l'ancien Cyber-hoot

CyberHoot est la refonte complète de [lele214/Cyber-hoot](https://github.com/lele214/Cyber-hoot),
projet de groupe de BTS SIO. Cette page reprend les défauts relevés dans l'ancienne version
(commit `b3c03cf`) et, pour chacun : ce qui a changé, où, et **le test qui le prouve**. Les
références « avant » renvoient aux fichiers de l'ancien dépôt.

Tous les tests cités tournent à chaque envoi sur GitHub, sur MySQL 8.4 comme en production.

| # | Défaut | Gravité |
|---|--------|---------|
| [R01](#r01) | Clé de session par défaut écrite dans le code | critique |
| [R02](#r02) | Schéma SQL écrit à la main, désynchronisé des modèles | élevée |
| [R03](#r03) | Aucune protection CSRF | élevée |
| [R04](#r04) | XSS stocké par `innerHTML` | critique |
| [R05](#r05) | Score envoyé par le navigateur, bonnes réponses exposées | élevée |
| [R06](#r06) | Conteneur en root, MySQL et Adminer publiés | élevée |
| [R07](#r07) | Configuration de développement par défaut | moyenne |
| [R08](#r08) | Lien de réinitialisation rejouable | élevée |
| [R09](#r09) | CSP incompatible avec des gestionnaires en ligne | moyenne |
| [R10](#r10) | Aucune limitation de débit | élevée |
| [R11](#r11) | Tests sur des textes de gabarit, base de test différente | moyenne |
| [R12](#r12) | Erreurs internes renvoyées au client | moyenne |
| [R13](#r13) | Énumération des comptes à l'inscription | moyenne |
| [R14](#r14) | Fonctionnalités mortes, erreurs masquées | moyenne |
| [R15](#r15) | Duplication massive | moyenne |
| [R16](#r16) | Images téléversées versionnées | moyenne |
| [R17](#r17) | Documentation suivie mais ignorée | faible |
| [R18](#r18) | Documentation contradictoire | faible |
| [R19](#r19) | Accessibilité faible | moyenne |
| [R20](#r20) | Réponses en `str(dict)`, journal de connexion sans date ni IP | moyenne |

---

### R01

Clé de session par défaut écrite dans le code.

- **Avant** — `app/config.py:20` : `SECRET_KEY = os.getenv("SECRET_KEY", "cle_secrete_a_changer_en_production")`.
  Sans variable d'environnement, toutes les installations partagent la même clé : n'importe
  qui peut fabriquer un cookie de session valide et se connecter comme n'importe quel compte.
- **Après** — aucune valeur par défaut. La clé est lue dans un fichier secret (`SECRET_KEY_FILE`)
  créé par `make secrets` ; l'application **refuse de démarrer** sans clé, avec une clé de moins
  de 32 caractères ou avec une valeur d'exemple (`app/config.py`, `lire_secret`).
- **Preuve** — `tests/test_config.py` : `test_refus_sans_cle_secrete`,
  `test_refus_cle_d_exemple_ou_trop_courte`, `test_secret_lu_dans_un_fichier`.

### R02

Schéma SQL écrit à la main, désynchronisé des modèles.

- **Avant** — `database/db_schemaV3-3.sql`, chargé au premier démarrage de MySQL, ignore ce
  que les migrations ont ajouté : pas de table `REVIEW`, pas de colonne `QUESTION.explanation`,
  table `BADGES` avec 4 colonnes contre 10 dans le modèle (`app/models/models.py:96-117`), enum
  de catégories différent (`'AUTRE'` d'un côté seulement). Une installation neuve ne
  fonctionne pas.
- **Après** — une seule source : les modèles SQLAlchemy et les migrations Alembic, appliquées
  au démarrage du conteneur. `docs/modele/schema.sql` est **généré** (`make schema`).
- **Preuve** — `tests/test_migrations.py` : `test_migrations_identiques_aux_modeles` (aucune
  différence entre la base migrée et les modèles) ; l'intégration continue régénère
  `schema.sql` et échoue s'il diffère du fichier versionné.

### R03

Aucune protection CSRF.

- **Avant** — ni Flask-WTF ni jeton dans les formulaires ; le `fetch` JSON de
  `static/js/quiz_dynamic.js:28` n'envoie aucun jeton. Un site tiers pouvait faire agir un
  utilisateur connecté (supprimer un quiz, changer son profil).
- **Après** — `CSRFProtect` sur toute l'application ; jeton dans chaque formulaire (y compris
  la déconnexion, en POST) ; en HTTPS, vérification du `Referer`.
- **Preuve** — `test_changer_de_pseudo_sans_csrf_refuse` (`tests/test_account.py`),
  `test_deconnexion_exige_post_et_csrf` (`tests/test_auth.py`).

### R04

XSS stocké par `innerHTML`.

- **Avant** — `static/js/quiz_dynamic.js:97-103` insère `${q.text}`, `${q.explanation}` et les
  textes des réponses dans `innerHTML`. Ces textes sont saisis par les créateurs : un quiz
  piégé exécutait du JavaScript chez chaque joueur.
- **Après** — aucun HTML construit en JavaScript (`textContent` et création d'éléments) ;
  les gabarits Jinja échappent tout ; la CSP interdit les scripts en ligne, ce qui neutralise
  une injection même si elle passait.
- **Preuve** — `tests/test_qualite.py` : `test_aucun_html_injecte_par_le_javascript` ;
  `tests/test_play.py` : `test_commentaire_echappe` ; `tests/test_security.py` :
  `test_entetes_de_securite`.

### R05

Score envoyé par le navigateur, bonnes réponses exposées.

- **Avant** — les bonnes réponses sont dans la page (`templates/quiz/quiz_dynamic.html:149`,
  `data-answers`) ; le score est calculé en JavaScript (`quiz_dynamic.js:18-19`), envoyé
  (`:29`) et cru par le serveur (`routes/main_routes.py:146-147`), qui attribue même des badges
  dessus. N'importe qui obtenait 100 % en une requête.
- **Après** — la page d'une question ne contient que les choix ; le serveur corrige chaque
  réponse (`app/services/correction.py`) et tient le score ; en direct, le chrono et les points
  de rapidité suivent l'horloge du serveur.
- **Preuve** — `tests/test_play.py` : `test_la_page_de_question_ne_revele_pas_les_bonnes_reponses`,
  `test_pas_de_score_envoye_par_le_client`, `test_partie_complete_score_calcule_par_le_serveur` ;
  `tests/test_live.py` : `test_la_question_n_affiche_pas_la_bonne_reponse`,
  `test_reponse_hors_delai_refusee`.

### R06

Conteneur en root, MySQL et Adminer publiés.

- **Avant** — `Dockerfile` sans `USER` ; `docker-compose.yml:22-23` publie MySQL (`3306:3306`)
  et `:64-65` Adminer (`8383:8080`) ; le code source est monté dans le conteneur.
- **Après** — image de production sans outils de compilation, utilisateur sans privilège
  (uid 10001), système de fichiers en lecture seule, toutes les capacités retirées,
  `no-new-privileges`. Seul Nginx publie des ports, sur la boucle locale par défaut ; MySQL et
  Redis sont sur un réseau Docker interne. Plus d'Adminer.
- **Preuve** — l'intégration continue démarre la pile et vérifie `id -u` = 10001 dans le
  conteneur ; l'image est analysée par Trivy (aucune vulnérabilité critique ou élevée
  corrigeable).

### R07

Configuration de développement par défaut.

- **Avant** — `app/__init__.py:12` : `os.getenv("FLASK_ENV", "development")` ;
  `DevelopmentConfig` (`DEBUG = True`, requêtes SQL affichées) est la configuration par défaut.
- **Après** — la production est la configuration par défaut ; le mode développement doit être
  demandé explicitement (`APP_ENV=development`) ; un environnement inconnu est refusé.
- **Preuve** — `tests/test_config.py` : `test_production_par_defaut`,
  `test_mode_developpement_explicite`, `test_environnement_inconnu_refuse`.

### R08

Lien de réinitialisation rejouable.

- **Avant** — le jeton embarque les 16 premiers caractères du hachage du mot de passe
  (`routes/auth.py:166`, contrôlés `:310`) pour le rendre à usage unique. Or ces caractères
  sont le préfixe fixe de l'algorithme (`scrypt:32768:8:1`), identique avant et après le
  changement : le lien restait valable une heure, autant de fois qu'on voulait.
- **Après** — jeton aléatoire stocké **haché** en base, marqué utilisé dès son emploi, annulé si
  un nouveau lien est demandé, valable 30 minutes ; un lien d'activation ne sert pas à
  réinitialiser (`app/services/tokens.py`).
- **Preuve** — `tests/test_auth.py` : `test_lien_a_usage_unique`,
  `test_nouveau_lien_annule_le_precedent`, `test_lien_expire`,
  `test_lien_d_activation_ne_sert_pas_a_reinitialiser`.

### R09

CSP incompatible avec des gestionnaires en ligne.

- **Avant** — la CSP n'autorise que les scripts avec nonce (`app/__init__.py:51`), mais les
  gabarits gardent des `onclick=` et `onsubmit="return confirm(…)"`
  (`profile/admin/admin_dashboard.html:24, 168, 253…`) : bloqués par le navigateur, les
  boutons ne font rien et les **confirmations de suppression ne s'affichent jamais**.
- **Après** — aucun gestionnaire en ligne : tout le JavaScript est dans des fichiers
  (`app/static/js/`), branché par attributs `data-*` (`data-confirmer` pour les
  confirmations) ; CSP stricte sans `unsafe-inline`, nonce différent à chaque requête.
- **Preuve** — `tests/test_security.py` : `test_aucun_javascript_en_ligne_dans_les_gabarits`,
  `test_nonce_change_a_chaque_requete_et_correspond_aux_scripts`.

### R10

Aucune limitation de débit.

- **Avant** — connexion, inscription et mot de passe oublié sans aucune limite
  (`routes/auth.py:40, 78, 190`) : essais de mots de passe illimités.
- **Après** — Flask-Limiter (compteurs dans Redis, partagés entre les processus) sur les routes
  sensibles, verrouillage d'un compte après 5 échecs, limite par adresse au niveau de Nginx.
  Les seuils tiennent compte d'une classe entière derrière une seule adresse IP.
- **Preuve** — `tests/test_auth.py` : `test_limitation_de_debit_sur_la_connexion`,
  `test_verrouillage_apres_cinq_echecs` ; `tests/test_live_service.py` :
  `test_essais_de_pin_limites_mais_pas_les_arrivees`.

### R11

Tests sur des textes de gabarit, base de test différente de la production.

- **Avant** — tests sur SQLite en mémoire avec `create_all()` (`test/conftest.py:15-19`) alors
  que la production est MySQL ; assertions du type `assert "8" in response.data`
  (`test/test_registration.py:103`).
- **Après** — plus de 230 tests qui vérifient des **comportements** (compte créé ou non, score en base,
  accès refusé, jeton consommé…) ; base construite par les migrations ; exécution sur **MySQL
  8.4** en intégration continue (`make test-mysql` en local). Couverture : 94 %.
- **Preuve** — job « Tests sur MySQL 8.4 » de `.github/workflows/ci.yml`.

### R12

Erreurs internes renvoyées au client.

- **Avant** — `routes/main_routes.py:205` renvoie `str(e)` en JSON, affiché par `alert()` ;
  `:268` le met dans un message flash.
- **Après** — pages d'erreur génériques (400, 403, 404, 429, 500) ; le détail part dans le
  journal avec un identifiant de requête (renvoyé dans l'en-tête `X-Request-ID`), qui permet
  de le retrouver.
- **Preuve** — `tests/test_security.py` : `test_erreur_interne_masquee`,
  `test_page_404_sans_detail_technique`, `test_reponse_json_pour_un_client_api`.

### R13

Énumération des comptes à l'inscription.

- **Avant** — `routes/auth.py:121` : « Cette adresse email est déjà utilisée ». On pouvait
  tester si une personne avait un compte.
- **Après** — même réponse que l'adresse soit libre ou non ; le titulaire reçoit un e-mail
  l'informant de la tentative. Même principe à la connexion et pour le mot de passe oublié.
- **Preuve** — `tests/test_auth.py` : `test_adresse_deja_prise_meme_reponse_et_aucun_nouveau_compte`,
  `test_meme_message_compte_inconnu_ou_mauvais_mot_de_passe`, `test_reponse_identique_compte_ou_non`.

### R14

Fonctionnalités mortes et erreurs masquées.

- **Avant** — `static/js/quiz.js` jamais chargé (et contenant des réponses en dur) ; modèle
  `Notification` jamais créé ; contournement par recherche de texte (`quiz_dynamic.js:137`) ;
  `except Exception: answers = {}` qui masque les erreurs de relecture (`routes/profile.py:357-359`) ;
  boutons inactifs (R09).
- **Après** — chaque route et chaque fichier JavaScript sert ; aucune exception avalée sans
  être journalisée ; les erreurs prévues sont des refus explicites (énumérations `Refus…`).
- **Preuve** — couverture de 94 % des lignes (seuil bloquant à 85 %) ; ruff (règles
  `BLE`, `S110`) refuse les `except` trop larges et les `pass` silencieux.

### R15

Duplication massive.

- **Avant** — `routes/profile.py` fait 1 502 lignes ; la liste des badges est définie **trois
  fois** (`app/__init__.py:90`, `app/seed_badges.py:20`, `seed_badges.py:20`).
- **Après** — routes minces par blueprint, logique dans `app/services/` ; un seul service par
  sujet (un seul code pour enregistrer un quiz, créateur ou administrateur) ; les badges sont
  créés une fois, par la migration `0004`, et attribués par un seul service
  (`app/services/progression.py`). Aucun fichier de plus de 400 lignes.
- **Preuve** — `tests/test_qualite.py` : `test_aucun_fichier_de_plus_de_400_lignes` ;
  `tests/test_progression.py` : `test_badges_de_reference`, `test_badges_jamais_en_double`.

### R16

Images téléversées versionnées.

- **Avant** — `uploads/8757c3….png` et `uploads/ede218….png` dans le dépôt ; `uploads/` absent
  du `.gitignore`.
- **Après** — images dans un volume Docker (`/data/uploads`), hors du dépôt et du dossier
  public ; servies par une route qui vérifie les droits et le résultat de l'analyse antivirus.
- **Preuve** — `tests/test_qualite.py` : `test_aucune_image_televersee_dans_le_depot` ;
  `tests/test_media.py` : `test_avant_analyse_visible_par_l_auteur_seulement`,
  `test_image_d_un_brouillon_invisible_meme_saine`.

### R17

Documentation suivie mais ignorée.

- **Avant** — `.gitignore` liste `docs/alembic.md` et `docs/justfile.md`, pourtant versionnés ;
  `*.sql` ignoré puis ré-autorisé au cas par cas.
- **Après** — `.gitignore` court et cohérent : secrets, fichiers des utilisateurs, fichiers
  générés.
- **Preuve** — étape « Aucun fichier versionné n'est censé être ignoré » de l'intégration
  continue (`git ls-files -ci --exclude-standard` doit être vide).

### R18

Documentation contradictoire.

- **Avant** — Adminer annoncé sur le port 8181 (`readme.md:63`) mais publié sur 8383 ;
  clé VirusTotal attendue dans `secrets/api_key` (README), `secrets/api_key.txt`
  (`.env.example:28`) ou lue sans extension (code), et jamais déclarée dans Compose ; mot de
  passe de la base dans `secrets/db_password.txt` (README, Compose) mais lu dans
  `secrets/db_password` en local.
- **Après** — un seul chemin par secret, créé par `make secrets`, lu par Compose ; un seul port
  documenté (HTTPS 8443, HTTP 8080 qui redirige).
- **Preuve** — `tests/test_qualite.py` : `test_documentation_d_accord_avec_la_configuration`
  (ports cités dans toute la documentation = ceux de `docker-compose.yml`, chaque secret
  attendu par Compose est créé par le Makefile).

### R19

Accessibilité faible.

- **Avant** — aucun attribut `aria-` dans les gabarits ; bouton de fermeture « × » sans nom
  accessible (`admin_dashboard.html:24`) ; champs créés en JavaScript sans libellé, avec un
  simple `placeholder` (`quiz_create.js:23-26`) ; réponse choisie signalée par la seule couleur
  de bordure (`quiz_dynamic.html:65`).
- **Après** — objectif WCAG 2.2 AA : libellés partout, erreurs reliées aux champs, focus
  visible, lien d'évitement, formes en plus des couleurs, messages annoncés, thèmes clair et
  sombre contrôlés. Détail : [accessibilite.md](accessibilite.md).
- **Preuve** — `make accessibilite` : axe-core sur 30 pages × 2 thèmes, **0 règle en défaut**,
  et parcours au clavier seul réussis.

### R20

Réponses en `str(dict)`, journal de connexion sans date ni IP.

- **Avant** — `routes/main_routes.py:168` : `answer=str(answers)`, relu par
  `ast.literal_eval` ; `ConnectionLog` (`models/models.py:269-275`) ne contient que
  l'identifiant du compte : ni date, ni adresse, ni échec.
- **Après** — une ligne par réponse (`play_answer`, `live_answer`) avec la question, les choix
  en JSON et le verdict ; journal d'audit avec date (UTC), compte, adresse IP, action et
  détails, pour les réussites **et** les échecs, consultable et filtrable par les
  administrateurs, purgé après 12 mois.
- **Preuve** — `tests/test_administration.py` : `test_connexions_journalisees_avec_l_adresse`,
  `test_page_du_journal_et_filtres`, `test_purge_apres_douze_mois` ;
  `tests/test_play.py` : `test_partie_complete_score_calcule_par_le_serveur`.
