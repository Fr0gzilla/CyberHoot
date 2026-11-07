# Registre des activités de traitement — CyberHoot

Registre tenu au titre de l'article 30 du RGPD. CyberHoot est un projet pédagogique ; le
responsable de traitement est l'organisme qui déploie l'application (établissement,
entreprise, association), qui complète la ligne « Responsable » ci-dessous.

| Champ | Valeur |
|-------|--------|
| Responsable de traitement | *(nom, adresse et contact de l'organisme qui déploie CyberHoot)* |
| Délégué à la protection des données | *(le cas échéant)* |
| Sous-traitants | Hébergeur choisi par le responsable ; VirusTotal (analyse des images, si activée) ; fournisseur SMTP (envoi des e-mails, si activé) |
| Transferts hors UE | Aucun par défaut. VirusTotal (Google) reçoit l'empreinte, et éventuellement le contenu, des images envoyées par les créateurs : à évaluer avant activation (mode simulé par défaut). |

## Traitement 1 — Comptes et sécurité

| Champ | Valeur |
|-------|--------|
| Finalité | Créer et sécuriser les comptes ; protéger la plateforme contre les abus |
| Base légale | Exécution du service demandé (art. 6.1.b) ; intérêt légitime pour la sécurité (art. 6.1.f) |
| Personnes concernées | Utilisateurs inscrits |
| Données | Pseudo, adresse e-mail, empreinte Argon2id du mot de passe, rôles, dates de création, de confirmation et de dernière connexion, compteur d'échecs, secret de double authentification (chiffré), codes de secours (hachés) |
| Destinataires | Administrateurs de la plateforme (pseudo, e-mail, rôles, état du compte) |
| Durée de conservation | Tant que le compte existe ; compte jamais activé : 30 jours |
| Sécurité | Voir `SECURITY.md` et le README : hachage, chiffrement du secret TOTP, CSRF, CSP, limitation de débit, journal d'audit |

## Traitement 2 — Journal d'audit

| Champ | Valeur |
|-------|--------|
| Finalité | Détecter et analyser les incidents de sécurité ; tracer les actions d'administration |
| Base légale | Intérêt légitime (art. 6.1.f) ; obligation de sécurité (art. 32) |
| Données | Date, compte et pseudo, adresse IP, action, cible de l'action |
| Destinataires | Administrateurs (consultation seule, aucune modification possible) |
| Durée de conservation | 12 mois, puis suppression automatique |

## Traitement 3 — Activité pédagogique

| Champ | Valeur |
|-------|--------|
| Finalité | Jouer aux quiz, suivre sa progression, obtenir des badges ; statistiques pour les créateurs |
| Base légale | Exécution du service (art. 6.1.b) |
| Données | Parties (réponses, scores, dates), badges, avis (note, commentaire publiés avec le pseudo), quiz créés, signalements |
| Destinataires | L'utilisateur ; les créateurs (statistiques agrégées, sans identité) ; les administrateurs (avis et signalements) |
| Durée de conservation | Tant que le compte existe ; à la suppression du compte, les avis sont effacés et les parties conservées de façon anonyme (statistiques) |

## Traitement 4 — Parties en direct

| Champ | Valeur |
|-------|--------|
| Finalité | Organiser une partie en direct animée en salle |
| Base légale | Exécution du service (art. 6.1.b) |
| Données | Pseudo choisi pour la partie (sans compte nécessaire), réponses, points ; lien avec le compte si le joueur est connecté |
| Destinataires | Animateur et participants (classement) |
| Durée de conservation | 24 heures après la fin de la partie (classement compris) ; les joueurs connectés retrouvent la partie dans leur historique |

## Exercice des droits

- **Accès et portabilité** (art. 15 et 20) : « Mon profil » → « Télécharger toutes mes données »
  (fichier JSON complet, y compris le journal de sécurité du compte).
- **Rectification** (art. 16) : pseudo et mot de passe modifiables depuis le profil ; adresse
  e-mail : sur demande au responsable.
- **Effacement** (art. 17) : « Mon profil » → « Supprimer mon compte », immédiat.
- **Réclamation** : auprès de la CNIL (cnil.fr).
