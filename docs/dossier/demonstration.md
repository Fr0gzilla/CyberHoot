# Scénario de démonstration (15 minutes)

## Préparation (la veille)

```bash
make secrets && make up      # https://localhost:8443
make admin                   # compte administrateur
make demo                    # 8 quiz de démonstration
```

- Activer la double authentification de l'administrateur (téléphone à portée de main).
- Créer un compte créateur et un compte joueur (donner le rôle créateur depuis
  Administration → Comptes).
- Accepter le certificat local dans le navigateur de présentation ; garder un téléphone
  (ou une fenêtre étroite) pour jouer le rôle d'un élève.
- Ouvrir à l'avance : le dépôt GitHub (onglet *Actions* au vert), `docs/avant-apres.md`.

## Déroulé

| Temps | Séquence | À montrer |
|-------|----------|-----------|
| 0-2 min | **Le besoin** | Sensibiliser une classe ; l'ancienne version et ses limites (tableau de `avant-apres.md`). |
| 2-5 min | **Partie solo** (compte joueur) | Catalogue et filtres ; une question « repérer le phishing » ; la correction expliquée ; la progression et un badge gagné. |
| 5-9 min | **Partie en direct** (compte créateur) | Lancer un quiz, PIN et QR code projetés ; rejoindre depuis le téléphone sans compte ; chrono, histogramme, classement, podium ; export CSV. |
| 9-11 min | **Création et validation** | Rédiger une question dans l'éditeur, la soumettre ; côté administrateur, la refuser avec un motif puis la publier. |
| 11-14 min | **Sécurité** | Connexion administrateur en deux étapes ; journal d'audit (échec de connexion visible avec son adresse) ; outils de développement : la page d'une question ne contient pas la bonne réponse ; un formulaire sans jeton CSRF est refusé ; en-têtes HTTPS (HSTS, CSP). |
| 14-15 min | **Qualité** | Intégration continue verte (tests sur MySQL, Trivy, gitleaks), `make accessibilite`. |

## Démonstrations de sécurité prêtes à l'emploi

- **Triche impossible** : dans les outils de développement, afficher le code source d'une
  question : seuls les choix y figurent. Rejouer la requête d'envoi avec un champ `score` :
  il est ignoré.
- **CSRF** : `curl -sk -o /dev/null -w "%{http_code}" -X POST https://localhost:8443/compte/connexion -d "email=a@b.c&password=x"` → 400 (formulaire sans jeton).
- **Énumération** : s'inscrire avec une adresse déjà utilisée → même message qu'une adresse
  libre.
- **Verrouillage** : 5 mots de passe faux → compte verrouillé 15 minutes, ligne dans le
  journal d'audit.
- **En-têtes** : `curl -skI https://localhost:8443/ | grep -iE 'strict|content-security|x-frame'`.

## Questions probables et éléments de réponse

- *Pourquoi pas de WebSocket pour le direct ?* L'interrogation chaque seconde passe tous les
  pare-feu d'établissement, se reconnecte d'elle-même et a tenu 200 joueurs
  (`docs/charge-v2.0.md`).
- *Comment le score reste-t-il juste si deux réponses arrivent en même temps ?* L'addition
  est faite par la base (`UPDATE … SET score = score + n`), et une contrainte d'unicité
  empêche deux réponses à la même question.
- *Que se passe-t-il si la base est copiée ?* Mots de passe en Argon2id, jetons hachés,
  secrets de double authentification chiffrés avec une clé qui n'est pas dans la base.
- *Comment savoir que la documentation est à jour ?* Le schéma SQL est généré et comparé en
  intégration continue ; un test vérifie que ports et secrets cités correspondent à la
  configuration.
