# Fiche de réalisation — E6 (bloc 3, cybersécurité)

**Intitulé** : sécurisation de bout en bout d'une application web de quiz (CyberHoot).

**À compléter** : nom, numéro de candidat, période, cadre de réalisation.

## 1. Contexte et enjeux

CyberHoot enseigne les bons réflexes de cybersécurité : une faille y serait doublement
grave. L'application traite des données personnelles (adresses e-mail, pseudos, résultats,
adresses IP dans le journal), accueille des joueurs anonymes en classe, reçoit des fichiers
envoyés par des utilisateurs et donne des droits d'administration.

L'ancienne version présentait des failles exploitables (référentiel : OWASP Top 10 2021) :

| Faille de l'ancienne version | Catégorie OWASP | Conséquence |
|------------------------------|-----------------|-------------|
| Clé de session par défaut dans le code | A02 Défaillances cryptographiques, A05 Mauvaise configuration | Usurpation de n'importe quel compte |
| XSS stocké par `innerHTML` | A03 Injection | Exécution de code chez chaque joueur d'un quiz piégé |
| Aucune protection CSRF | A01 Contrôle d'accès défaillant | Actions forcées à l'insu d'un utilisateur connecté |
| Score envoyé par le navigateur | A04 Conception non sécurisée | Triche, badges obtenus sans jouer |
| Lien de réinitialisation rejouable | A07 Identification et authentification | Prise de contrôle d'un compte pendant une heure |
| Aucune limitation de débit, énumération des comptes | A07 | Essais de mots de passe illimités sur des comptes connus |
| Conteneur en root, base publiée | A05 | Exposition de la base, escalade en cas de faille |
| Erreurs internes renvoyées | A05 | Fuite d'informations techniques |
| Journal de connexion sans date ni IP | A09 Journalisation et surveillance | Aucune enquête possible après un incident |

Détail et preuves : [avant-apres.md](../avant-apres.md).

## 2. Mesures mises en œuvre et compétences du bloc 3

### Protéger les données à caractère personnel

- Registre des traitements, finalités, durées de conservation : `docs/rgpd/registre.md`.
- Minimisation : les joueurs du direct n'ont pas besoin de compte ; leurs données sont
  effacées 24 h après la partie. Comptes jamais activés purgés après 30 jours.
- Droits des personnes : export complet en JSON depuis le profil, suppression du compte
  par son titulaire.
- Preuves : `test_export_de_mes_donnees`, `test_supprimer_son_compte`, `test_purge`.

### Préserver l'identité numérique de l'organisation

- HTTPS seul (TLS 1.2+), HSTS : le site ne peut pas être usurpé ou intercepté en clair
  (`docs/https.md`).
- Un quiz n'est visible qu'après validation par un administrateur ; signalement de contenus
  par les joueurs ; dépublication.
- Les e-mails de l'application ne contiennent que des liens construits depuis l'adresse
  publique configurée (pas depuis l'en-tête `Host` de la requête).
- Preuves : `test_lien_construit_depuis_l_url_publique`, `test_signaler_puis_depublier`.

### Sécuriser les équipements et les usages des utilisateurs

- Mots de passe : Argon2id, 12 caractères minimum, refus des mots de passe courants et de
  ceux qui contiennent le pseudo ou l'e-mail ; verrouillage après 5 échecs.
- Double authentification TOTP, obligatoire pour l'administration, codes de secours.
- Changer de mot de passe ferme les autres sessions ; un compte désactivé perd sa session.
- Preuves : `tests/test_auth.py`, `tests/test_double_authentification.py`,
  `test_changer_de_mot_de_passe_deconnecte_les_autres_sessions`.

### Garantir la disponibilité, l'intégrité et la confidentialité des services et des données

- **Disponibilité** : limitation de débit (Nginx et application, compteurs dans Redis)
  calibrée pour une classe derrière une seule adresse ; test de charge à 200 joueurs ; sonde
  de santé ; redémarrage automatique des conteneurs.
- **Intégrité** : score et points calculés par le serveur ; une réponse par question ;
  transitions de partie atomiques ; journal d'audit en ajout seul.
- **Confidentialité** : contrôle d'accès vérifié sur chaque route (un créateur ne voit pas
  le brouillon d'un autre), secrets de double authentification chiffrés, jetons stockés hachés.
- Preuves : `test_un_createur_ne_touche_pas_au_quiz_d_un_autre`,
  `test_double_clic_de_l_animateur_n_avance_qu_une_fois`, `docs/charge-v2.0.md`.

### Assurer la cybersécurité d'une solution applicative et de son développement

- **Développement** : entrées validées côté serveur, sorties échappées, CSP stricte à nonce,
  aucun JavaScript en ligne, protection CSRF, en-têtes de sécurité, erreurs sans détail.
- **Fichiers envoyés** : vérification du format réel, ré-encodage, métadonnées retirées,
  stockage hors du dossier public, analyse antivirus (VirusTotal) avant diffusion.
- **Chaîne de production** : dépendances figées avec empreintes, `pip-audit`, analyse
  statique `bandit`, analyse de l'image par Trivy, recherche de secrets par gitleaks, à
  chaque envoi sur GitHub.
- **Exploitation** : conteneurs sans privilège, en lecture seule, capacités retirées ; base
  sur un réseau interne ; secrets dans des fichiers, jamais dans le dépôt ; journal d'audit.
- **Politique** : signalement responsable des failles, délais de correction (`SECURITY.md`).

## 3. Tests de sécurité

| Vérification | Outil | Où |
|--------------|-------|----|
| Comportements de sécurité (CSRF refusé, accès interdit, jeton consommé, score non falsifiable…) | pytest | `tests/` |
| Code Python | bandit, ruff (règles de sécurité `S`) | intégration continue |
| Dépendances | pip-audit | intégration continue |
| Image Docker | Trivy (aucune vulnérabilité critique ou élevée corrigeable) | intégration continue |
| Secrets publiés par erreur | gitleaks, sur tout l'historique | intégration continue |
| Configuration TLS et en-têtes | curl en intégration continue ; SSL Labs en production | `docs/https.md` |

**À compléter** : si un test d'intrusion manuel a été mené (par exemple avec OWASP ZAP ou
Burp Suite sur une instance locale), en décrire la méthode et les résultats.

## 4. Bilan

**À compléter.** Risques résiduels connus et documentés dans `SECURITY.md` (« Points
d'attention pour l'exploitation ») : rotation de `SECRET_KEY`, mode antivirus simulé par
défaut, limites de débit à ajuster pour un service ouvert au public, sauvegardes.
