# Test de charge — parties en direct (v2.0)

## Objectif

Vérifier qu'une partie en direct tient la taille maximale prévue (200 joueurs) dans le cas
le plus défavorable : **tous les joueurs derrière la même adresse IP**, comme une salle de
classe derrière le réseau d'un établissement.

## Méthode

Outil : [`outils/charge_direct.py`](../outils/charge_direct.py) (bibliothèque standard Python,
un fil d'exécution par joueur). Chaque joueur simulé :

1. rejoint la partie avec le code PIN et un pseudo ;
2. interroge l'état de la partie chaque seconde, comme le script de la page ;
3. recharge son écran seulement au changement d'écran (nouvelle question, correction) ;
4. répond à chaque question après un temps de réflexion aléatoire de 0,2 à 3 s.

L'animateur lance la partie et passe à la question suivante 2 s après chaque correction.
Quiz de 6 questions, chrono de 10 s. Pile complète (`make up`) : Nginx, 3 processus gunicorn
de 4 fils, MySQL 8.4, Redis, sur un Mac (Docker dans une machine virtuelle Colima, 4 cœurs).

```bash
python outils/charge_direct.py --url http://localhost:8080 --joueurs 200 \
  --email <compte créateur> --mot-de-passe '<mot de passe>' --quiz 1 --chrono 10
```

## Résultats (7 novembre 2026)

### 50 joueurs

| Requête | Nombre | Médiane | 95 % sous | Max |
|---------|-------:|--------:|----------:|----:|
| État de la partie | 1 421 | 3 ms | 17 ms | 87 ms |
| Réponse | 300 | 11 ms | 21 ms | 88 ms |
| Rejoindre | 50 | 74 ms | 116 ms | 126 ms |

Aucune erreur ; 300 réponses sur 300 enregistrées ; classement de 50 lignes.

### 200 joueurs (maximum prévu)

| Requête | Nombre | Médiane | 95 % sous | Max |
|---------|-------:|--------:|----------:|----:|
| État de la partie | 7 332 | 11 ms | 214 ms | 521 ms |
| Écran du joueur | 2 600 | 49 ms | 412 ms | 588 ms |
| Réponse | 1 196 | 109 ms | 384 ms | 833 ms |
| Rejoindre | 200 | 237 ms | 480 ms | 644 ms |

200 joueurs dans la salle, partie complète en 50 s, classement de 200 lignes.
1 196 réponses sur 1 200 enregistrées : les 4 autres ont été refusées pour « jeton CSRF
expiré », effet de l'horloge de la machine virtuelle Docker sur Mac, qui recule par moments
(15 reculs jusqu'à 0,24 s mesurés en 150 s) ; un serveur Linux à l'heure n'a pas ce défaut.

Même au maximum, le temps de réponse reste très inférieur au chrono (10 s minimum) : les
points de rapidité, calculés avec l'heure du serveur à la réception, ne sont pas faussés de
façon perceptible.

## Défauts trouvés par ce test, et corrigés

1. **Interblocage MySQL à l'arrivée simultanée des joueurs** (erreur 500) : chaque arrivée
   insérait un joueur puis modifiait la partie. Les arrivées ne modifient plus la partie ;
   un changement d'écran concurrent perdu dans un interblocage est ignoré sans erreur (la
   requête suivante voit l'état à jour).
2. **Limites par adresse IP pensées pour un seul utilisateur** : 38 arrivées sur 50 refusées
   par Nginx, puis les réponses au-delà de 600 par minute. Les limites tiennent maintenant
   compte d'une salle entière derrière une adresse ; seuls les **codes PIN faux** restent
   fortement limités (30 par minute), ce qui rend vain l'essai des codes un par un.
3. **Configuration Nginx non rechargée** après modification (fichiers montés un par un) : le
   dossier est monté en entier et `make up` recharge Nginx.

## Pourquoi des interrogations chaque seconde plutôt que des WebSockets

- aucune infrastructure particulière (processus asynchrones, file de messages, sessions
  « collantes ») : les mêmes processus gunicorn servent tout ;
- passe les proxys et pare-feu d'établissement qui bloquent souvent les WebSockets ;
- reconnexion naturelle : un téléphone qui perd le réseau reprend à la requête suivante ;
- coût mesuré ci-dessus : 200 requêtes par seconde légères (état de quelques octets),
  absorbées sans difficulté.
