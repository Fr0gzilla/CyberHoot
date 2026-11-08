# HTTPS

CyberHoot n'est servi qu'en HTTPS. Nginx termine TLS et transmet à l'application ; le port
HTTP ne sert qu'à rediriger (et à la validation Let's Encrypt).

| Réglage | Valeur |
|---------|--------|
| Protocoles | TLS 1.2 et 1.3 uniquement (profil « intermédiaire » de Mozilla) |
| Suites | ECDHE + AES-GCM ou ChaCha20-Poly1305 (confidentialité persistante) |
| HTTP/2 | activé |
| Redirection | `http://…` → `https://…` (301), chemin et paramètres conservés |
| HSTS | `max-age=31536000; includeSubDomains`, envoyé par l'application sur toute réponse HTTPS |
| Cookies | `Secure`, `HttpOnly`, `SameSite=Lax` |
| CSRF | en HTTPS, Flask-WTF vérifie aussi que l'en-tête `Referer` vient du même site |

Configuration : `docker/nginx/modeles/cyberhoot.conf.template` (rempli au démarrage du
conteneur avec les variables d'environnement) ; en-tête HSTS : `app/security.py`.

## En local (certificat auto-signé)

`make secrets` crée `secrets/tls/cyberhoot.crt` et sa clé (valables 825 jours, pour
`localhost` et `127.0.0.1`) ; `make up` démarre la pile sur **https://localhost:8443**.

Le navigateur prévient que le certificat n'est pas reconnu : c'est normal pour un certificat
auto-signé. On peut l'accepter pour la session, ou l'ajouter aux certificats de confiance du
poste (macOS : Trousseaux d'accès → Système → importer `cyberhoot.crt` → « Toujours approuver »).
En ligne de commande : `curl --cacert secrets/tls/cyberhoot.crt https://localhost:8443/health`.

Un certificat refusé par le navigateur ne déclenche pas HSTS : aucun risque de « bloquer »
`localhost` pour d'autres projets.

## En production (vrai certificat)

Exemple avec Let's Encrypt et un nom de domaine `quiz.exemple.fr` qui pointe vers le serveur.

1. **Ports et adresse** — dans `.env` :

   ```ini
   HTTP_BIND=0.0.0.0
   HTTP_PORT=80
   HTTPS_PORT=443
   HTTPS_SUFFIXE=
   PUBLIC_URL=https://quiz.exemple.fr
   COOKIE_SECURE=true
   ```

   `HTTPS_SUFFIXE` vide : la redirection mène à `https://quiz.exemple.fr/…` sans numéro de port.

2. **Dossier de validation** — Nginx sert `/.well-known/acme-challenge/` depuis
   `/var/www/acme`. Le monter avec un fichier `docker-compose.override.yml` (lu
   automatiquement par Compose, non versionné) :

   ```yaml
   services:
     proxy:
       volumes:
         - ./acme:/var/www/acme:ro
   ```

   puis `make up`.

3. **Obtenir le certificat** (méthode « webroot » : Nginx reste en service) :

   ```bash
   mkdir -p acme
   docker run --rm -v "$PWD/acme:/var/www/acme" -v "$PWD/secrets/letsencrypt:/etc/letsencrypt" \
     certbot/certbot certonly --webroot -w /var/www/acme -d quiz.exemple.fr \
     --email admin@exemple.fr --agree-tos --no-eff-email
   ```

4. **Brancher le certificat** — copier celui de Let's Encrypt à la place du certificat
   auto-signé :

   ```bash
   cp -L secrets/letsencrypt/live/quiz.exemple.fr/fullchain.pem secrets/tls/cyberhoot.crt
   cp -L secrets/letsencrypt/live/quiz.exemple.fr/privkey.pem secrets/tls/cyberhoot.key
   docker compose restart proxy
   ```

5. **Renouveler** — les certificats Let's Encrypt durent 90 jours au plus (durée en
   baisse progressive). Une tâche planifiée (cron) deux fois par jour suffit : `renew` ne fait
   rien tant que l'échéance est loin.

   ```bash
   docker run --rm -v "$PWD/acme:/var/www/acme" -v "$PWD/secrets/letsencrypt:/etc/letsencrypt" \
     certbot/certbot renew --quiet \
   && cp -L secrets/letsencrypt/live/quiz.exemple.fr/fullchain.pem secrets/tls/cyberhoot.crt \
   && cp -L secrets/letsencrypt/live/quiz.exemple.fr/privkey.pem secrets/tls/cyberhoot.key \
   && docker compose restart proxy
   ```

6. **Vérifier** — `curl -I https://quiz.exemple.fr` doit montrer `strict-transport-security`,
   et l'analyse de [SSL Labs](https://www.ssllabs.com/ssltest/) doit donner la note A.

Le dossier `secrets/` (clés privées comprises) n'est jamais versionné.

### Attention à HSTS

Une fois HSTS reçu par un navigateur, celui-ci refusera tout accès en clair au domaine **et à
ses sous-domaines** pendant un an. Avant la mise en ligne, s'assurer que tous les
sous-domaines concernés sont servis en HTTPS. L'inscription sur la liste « preload » des
navigateurs n'est pas demandée : elle est difficile à annuler.

## Vérifications automatiques

- Test : l'en-tête HSTS n'est envoyé qu'en HTTPS (`tests/test_security.py`).
- Intégration continue : la pile démarre, `https://localhost:8443/health` répond avec le
  certificat généré, `http://localhost:8080/` redirige en 301 vers HTTPS et la page d'accueil
  porte l'en-tête HSTS (`.github/workflows/ci.yml`).
