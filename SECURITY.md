# Politique de sécurité

CyberHoot est une plateforme de sensibilisation à la cybersécurité : elle se doit d'être
exemplaire. Toute faille signalée est prise au sérieux.

## Signaler une faille

Merci de **ne pas ouvrir de ticket public**. Utilisez le signalement privé de GitHub :
onglet *Security* → *Report a vulnerability* de ce dépôt.

Indiquez si possible la version ou le commit, les étapes pour reproduire et l'impact estimé.

| Étape | Délai |
|-------|-------|
| Accusé de réception | 7 jours |
| Première évaluation (gravité, versions touchées) | 14 jours |
| Correctif pour une faille critique ou élevée | 30 jours |
| Publication d'un avis (GitHub Security Advisory), avec remerciements si vous le souhaitez | à la sortie du correctif |

## Versions suivies

Seule la dernière version publiée (branche `main`) reçoit des correctifs de sécurité.

## Périmètre

Dans le périmètre : le code de ce dépôt et la configuration Docker fournie (Nginx, image de
l'application, Compose).

Hors périmètre : une instance mal configurée (secrets d'exemple, `COOKIE_SECURE=false` en
ligne, ports de la base publiés à la main), les attaques par déni de service volumétrique,
l'ingénierie sociale, les failles des services tiers (VirusTotal, fournisseur SMTP).

Les tests d'intrusion ne doivent viser qu'une instance que vous avez lancée vous-même
(`make up`). Aucun test sur une instance d'établissement sans l'accord écrit de son responsable.

## Protections en place

Référentiel : OWASP ASVS niveau 2. Chaque protection est vérifiée par un test automatique.

| Domaine | Protection | Où |
|---------|-----------|----|
| Mots de passe | Argon2id ; 12 caractères minimum ; refus des mots de passe courants et de ceux qui contiennent le pseudo ou l'e-mail | `app/services/passwords.py` |
| Connexion | Verrouillage 15 min après 5 échecs ; aucun message ne révèle si un compte existe ; limitation de débit par adresse | `app/services/accounts.py`, `app/auth/routes.py` |
| Double authentification | TOTP (secret chiffré, code à usage unique, dérive d'un pas tolérée) ; 10 codes de secours hachés ; obligatoire pour l'administration | `app/services/twofa.py` |
| Jetons (activation, réinitialisation) | Aléatoires, stockés hachés, à usage unique, durée limitée (30 min) | `app/services/tokens.py` |
| Sessions | Cookies `Secure`, `HttpOnly`, `SameSite=Lax` ; jeton de session renouvelé au changement de mot de passe (les autres sessions sont fermées) | `app/config.py`, `app/models/account.py` |
| Contrôle d'accès | Rôle vérifié côté serveur sur chaque route ; un créateur n'accède qu'à ses quiz | `app/auth/__init__.py`, tests `test_security.py`, `test_creator.py` |
| CSRF | Jeton sur tous les formulaires ; vérification du `Referer` en HTTPS | Flask-WTF |
| XSS | Échappement automatique des gabarits ; CSP à nonce sans `unsafe-inline` ; aucun JavaScript en ligne ; aucun `innerHTML` sur une donnée | `app/security.py`, test `test_aucun_javascript_en_ligne_dans_les_gabarits` |
| Triche | Bonnes réponses jamais envoyées au navigateur avant la réponse ; score et points calculés par le serveur, à l'heure du serveur | `app/services/correction.py`, `app/services/live.py` |
| Téléversements | Images seulement (vérifiées par Pillow, réencodées, métadonnées retirées), 2 Mo, nom aléatoire, hors du dossier public, analysées par antivirus avant publication | `app/services/media.py`, `app/services/scan.py` |
| Transport | HTTPS seul (TLS 1.2+), HSTS un an | `docs/https.md` |
| En-têtes | CSP, `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, COOP, CORP | `app/security.py` |
| Erreurs | Pages d'erreur sans détail technique ; détail dans le journal, avec un identifiant de requête | `app/errors.py` |
| Journalisation | Journal d'audit (connexions, échecs, actions des administrateurs, avec date et adresse) ; jamais de mot de passe ni de jeton dans les journaux | `app/services/audit.py` |
| Conteneurs | Utilisateur sans privilège (uid 10001), système de fichiers en lecture seule, capacités retirées ; base et Redis sur un réseau interne, seul Nginx publie des ports | `Dockerfile`, `docker-compose.yml` |
| Secrets | Lus depuis des fichiers (`*_FILE`), jamais dans le dépôt ; refus de démarrer avec une valeur d'exemple | `app/config.py` |
| Dépendances | Versions figées avec empreintes ; `pip-audit` et Trivy en intégration continue | `requirements.txt`, `.github/workflows/ci.yml` |
| Données personnelles | Export de ses données, suppression du compte, purges automatiques (parties anonymes 24 h, journal 12 mois) | `docs/rgpd/registre.md` |

Contrôles automatiques à chaque envoi sur GitHub : ruff, mypy strict, bandit, pip-audit,
tests sur MySQL, comparaison du schéma, construction de l'image et analyse Trivy, recherche
de secrets (gitleaks), démarrage de la pile en HTTPS.

## Points d'attention pour l'exploitation

- **Changer `SECRET_KEY`** invalide les sessions, les jetons en cours **et les secrets de
  double authentification** (ils sont chiffrés avec une clé qui en dérive) : les comptes
  concernés se connectent alors avec un code de secours, puis réactivent la double
  authentification.
- **Analyse antivirus** : le mode `simule` (par défaut) n'analyse rien ; il sert aux essais.
  En service, régler `SCAN_BACKEND=virustotal` avec une clé d'API.
- **Limites de débit** : calibrées pour une classe entière derrière une seule adresse IP
  (réseau d'établissement). Sur un service ouvert au public, elles peuvent être abaissées
  (`app/auth/routes.py`, `docker/nginx/nginx.conf`).
- **Sauvegardes** : la base (`db-data`) et les images (`uploads`) sont dans des volumes
  Docker, à sauvegarder ; les sauvegardes contiennent des données personnelles.
