// Parties en direct : interroge l'état de la partie chaque seconde.
// - changement d'écran (nouvelle question, correction, podium) : la page se recharge ;
// - sinon : mise à jour du chrono et des compteurs, sans rechargement.
// Le chrono affiché n'est qu'indicatif : seule l'heure du serveur compte pour les réponses.
(function () {
  "use strict";
  var racine = document.querySelector("[data-direct]");
  if (!racine) {
    return;
  }
  var urlEtat = racine.getAttribute("data-etat");
  var version = Number(racine.getAttribute("data-version"));
  var joueurs = Number(racine.getAttribute("data-joueurs"));
  var animateur = racine.getAttribute("data-direct") === "animateur";
  var chronoTotal = Number(racine.getAttribute("data-chrono-total")) || 20;
  var finChrono = null;
  var resteFige = null;

  function ecrire(selecteur, texte) {
    document.querySelectorAll(selecteur).forEach(function (element) {
      element.textContent = texte;
    });
  }

  function afficherChrono() {
    var reste = resteFige;
    if (finChrono !== null) {
      reste = Math.max(0, finChrono - Date.now());
    }
    if (reste === null) {
      return;
    }
    var secondes = Math.ceil(reste / 1000);
    ecrire("[data-chrono]", String(secondes));
    var palier = Math.round((10 * reste) / (chronoTotal * 1000)) * 10;
    document.querySelectorAll("[data-chrono-barre]").forEach(function (barre) {
      barre.className = barre.className.replace(/\bbarre-\d+\b/, "barre-" + palier);
    });
  }

  function appliquer(etat) {
    var lobbyChange = animateur && etat.statut === "lobby" && etat.joueurs !== joueurs;
    if (etat.version !== version || lobbyChange) {
      window.location.reload();
      return false;
    }
    ecrire("[data-reponses]", String(etat.reponses));
    ecrire("[data-joueurs-total]", String(etat.joueurs));
    if (etat.statut === "question" && etat.reste_ms !== null) {
      finChrono = Date.now() + etat.reste_ms;
      resteFige = null;
    } else if (etat.statut === "paused") {
      finChrono = null;
      resteFige = etat.reste_ms;
    }
    afficherChrono();
    return true;
  }

  function interroger() {
    window
      .fetch(urlEtat, { credentials: "same-origin", cache: "no-store" })
      .then(function (reponse) {
        return reponse.ok ? reponse.json() : null;
      })
      .then(function (etat) {
        if (etat === null || appliquer(etat)) {
          window.setTimeout(interroger, 1000);
        }
      })
      .catch(function () {
        // Réseau coupé : on réessaie un peu plus tard.
        window.setTimeout(interroger, 3000);
      });
  }

  window.setInterval(afficherChrono, 250);
  interroger();
})();
