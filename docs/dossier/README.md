# Dossier technique — CyberHoot

Support pour présenter le projet aux épreuves du BTS SIO option SLAM : la réalisation
applicative (bloc 2, épreuve E5) et sa cybersécurité (bloc 3, épreuve E6).

| Document | Contenu |
|----------|---------|
| [Fiche E5 — réalisation applicative](fiche-e5.md) | Contexte, besoin, choix techniques, réalisations, compétences du bloc 2 et leurs preuves |
| [Fiche E6 — cybersécurité](fiche-e6.md) | Risques, mesures, compétences du bloc 3 et leurs preuves |
| [Scénario de démonstration](demonstration.md) | Déroulé d'une présentation de 15 minutes, avec les comptes et données à préparer |

Les fiches suivent les rubriques habituelles d'une fiche descriptive de réalisation
professionnelle ; elles sont à recopier dans le modèle officiel fourni par l'établissement
(numéro de candidat, période, modalité de réalisation). Les passages marqués **À compléter**
ne peuvent être remplis que par le candidat.

## Le projet en bref

CyberHoot est une plateforme web de quiz de sensibilisation à la cybersécurité, utilisable
seul (parcours, correction expliquée, progression, badges) ou en classe : un animateur projette
une partie en direct, les élèves répondent sur leur téléphone avec un code PIN.

C'est la refonte complète de Cyber-hoot, un projet de groupe de BTS SIO
([lele214/Cyber-hoot](https://github.com/lele214/Cyber-hoot)) : l'ancienne version présentait
20 défauts, dont plusieurs failles de sécurité, décrits avec leur correction dans
[avant-apres.md](../avant-apres.md).

| Chiffres | |
|---|---|
| Versions livrées | 6 (v1.0 à v3.0), chacune avec intégration continue verte |
| Tests automatisés | plus de 230, exécutés sur MySQL 8.4 ; couverture 94 % |
| Accessibilité | 0 défaut axe-core (WCAG 2.2 AA) sur 30 pages, deux thèmes |
| Charge | 200 joueurs simultanés derrière une seule adresse IP ([rapport](../charge-v2.0.md)) |

## Documents de référence

- Modélisation : [docs/modele/](../modele/README.md) (règles de gestion, dictionnaire, MCD, MLD,
  diagrammes de classes et de séquence, schéma SQL généré).
- Sécurité : [SECURITY.md](../../SECURITY.md), [HTTPS](../https.md), [registre RGPD](../rgpd/registre.md).
- Qualité : [accessibilité](../accessibilite.md), [charge](../charge-v2.0.md),
  [journal des versions](../../CHANGELOG.md).
