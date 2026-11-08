# Revue d'accessibilité (v3.0)

Objectif : **WCAG 2.2 niveau AA** sur toutes les pages, en thème clair et en thème sombre,
sur ordinateur comme sur téléphone.

## Résultat

| Contrôle | Méthode | Résultat |
|----------|---------|----------|
| Règles WCAG 2.0, 2.1 et 2.2 (A et AA) + bonnes pratiques | axe-core 4.10.2, 30 pages × 2 thèmes | **0 règle en défaut** |
| Contrastes (texte, liens dans le texte, champs, focus) | axe-core (calcul sur le rendu réel) | conformes dans les deux thèmes |
| Navigation au clavier | parcours scriptés au clavier seul | lien d'évitement en premier, ordre logique, focus visible, parcours complets possibles |
| Affichage sur téléphone (360 px) | largeur de défilement mesurée | aucun défilement horizontal |
| Animations | `prefers-reduced-motion` | toutes coupées |

Pages analysées : accueil, connexion (vierge et avec erreurs), inscription (vierge et avec
erreurs), mot de passe oublié, renvoi d'activation, catalogue, fiche d'un quiz, badges,
rejoindre une partie, confidentialité, page 404, profil, progression, double authentification,
espace créateur, éditeur de quiz, administration (tableau de bord, comptes, journal, badges,
catégories, signalements, revue d'un quiz), partie solo (question et correction), partie en
direct (salle d'attente et question, côté animateur et côté joueur).

## Constats et corrections

La première analyse a relevé deux règles en défaut, et la vérification au clavier un manque ;
les trois sont corrigés dans cette version :

1. **Liens distingués par la seule couleur** (`link-in-text-block`, critère 1.4.1) : un lien
   au milieu d'une phrase (« Créer un compte », « politique de confidentialité ») n'était
   reconnaissable qu'à sa couleur. Correction : les liens placés dans un texte sont soulignés
   (`assets/app.css`, règle `:where(p, li, dd, td, label, small) a`).
2. **Pas de titre de niveau 1** sur la question d'une partie solo et sur l'écran du joueur en
   direct (`page-has-heading-one`) : les lecteurs d'écran n'avaient pas de repère pour
   « aller au titre ». Correction : `<h1>` « quiz · question N sur M » (`quiz/play.html`) et
   titre réservé aux lecteurs d'écran sur l'écran du joueur (`live/player.html`).
3. **Focus perdu après un formulaire refusé** : la page revenait avec les erreurs, mais le
   focus restait en haut. Correction : il est placé sur le premier champ à corriger, dont le
   message d'erreur est lu grâce à `aria-describedby` (`static/js/app.js`).

## Ce qui est en place (toutes versions)

- **Structure** : `lang="fr"`, un `<h1>` par page, repères `header` / `nav` / `main` /
  `footer`, lien « Aller au contenu » (premier élément atteint à la tabulation).
- **Formulaires** : chaque champ a son `<label>` ; les erreurs sont reliées au champ
  (`aria-describedby`, `aria-invalid`) et le premier champ fautif reçoit le focus ; les
  réponses d'un quiz sont des boutons radio ou cases à cocher natifs regroupés dans un
  `fieldset` avec sa `legend` (la question).
- **Couleurs** : les réponses ne se distinguent jamais par la seule couleur (une forme ▲ ◆ ● ■
  accompagne chacune) ; la correction écrit « bonne réponse » / « votre choix » en plus des
  symboles ✓ et ✗.
- **Messages d'état** : les messages après une action sont dans une zone `role="status"`
  `aria-live="polite"` et restent affichés jusqu'à leur fermeture ; une erreur de saisie
  (code PIN, réponse) est en `role="alert"`. Le chrono d'une partie en direct n'est volontairement
  pas annoncé à chaque seconde.
- **Images** : texte alternatif obligatoire dans l'éditeur pour toute image de question ; le
  code QR d'une partie est accompagné du code PIN écrit en clair.
- **Thèmes** : clair et sombre, choix mémorisé ; contrastes vérifiés dans les deux.
- **Pas de piège** : aucun contenu ne bloque le focus, aucune limite de temps sans
  alternative en solo (seules les parties en direct sont chronométrées, et l'animateur peut
  mettre en pause).

## Refaire l'audit

La pile doit tourner (`make up`) et un compte administrateur avec double authentification
doit exister ; `AUDIT_TOTP` est son secret (affiché sous le code QR lors de l'activation).

```bash
AUDIT_EMAIL=admin@exemple.fr AUDIT_MOT_DE_PASSE='…' AUDIT_TOTP=SECRETBASE32 AUDIT_QUIZ=1 \
  make accessibilite
```

La commande télécharge axe-core (version figée, empreinte SHA-256 vérifiée), lance Chromium
dans l'image officielle de Playwright, parcourt les pages dans les deux thèmes (une partie
en direct comprise), rejoue les parcours au clavier et échoue au moindre défaut. Script : `outils/audit_accessibilite.py`.

## Limites

Un outil automatique ne détecte qu'une partie des problèmes. Vérifications faites en plus,
au clavier seul (touches Tab, Espace, Entrée ; inclus dans `make accessibilite`) : envoi d'un formulaire
d'inscription vide (le focus va au premier champ fautif), connexion, partie solo complète
(choisir une réponse, valider, lire la correction), rejoindre une partie avec un code faux
(l'erreur est annoncée) ; affichage à 360 px de large sur les pages publiques.

Reste à faire par une personne : un parcours avec un lecteur d'écran (NVDA ou VoiceOver),
idéalement par quelqu'un qui l'utilise au quotidien, et un contrôle du zoom à 200 % page par page.
