// Comportements communs à toutes les pages. Aucun gestionnaire en ligne dans le HTML :
// tout est branché ici, ce qui permet une CSP sans 'unsafe-inline'.
(function () {
  "use strict";

  function brancherTheme() {
    var bouton = document.querySelector("[data-bascule-theme]");
    if (!bouton) {
      return;
    }
    var libelle = bouton.querySelector("[data-libelle-theme]");
    function afficher() {
      var sombre = document.documentElement.getAttribute("data-theme") === "dark";
      bouton.setAttribute("aria-pressed", sombre ? "true" : "false");
      if (libelle) {
        libelle.textContent = sombre ? "Thème clair" : "Thème sombre";
      }
    }
    bouton.addEventListener("click", function () {
      var sombre = document.documentElement.getAttribute("data-theme") === "dark";
      var suivant = sombre ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", suivant);
      try {
        window.localStorage.setItem("theme", suivant);
      } catch (erreur) {
        // Stockage indisponible (navigation privée) : le choix vaut pour cette page.
      }
      afficher();
    });
    afficher();
  }

  function brancherMessages() {
    document.querySelectorAll("[data-fermer-message]").forEach(function (bouton) {
      bouton.addEventListener("click", function () {
        var message = bouton.closest(".message");
        if (message) {
          message.remove();
        }
      });
    });
  }

  // Demande une confirmation avant les actions irréversibles : <form data-confirmer="...">.
  function brancherConfirmations() {
    document.querySelectorAll("form[data-confirmer]").forEach(function (formulaire) {
      formulaire.addEventListener("submit", function (evenement) {
        if (!window.confirm(formulaire.getAttribute("data-confirmer"))) {
          evenement.preventDefault();
        }
      });
    });
  }

  // Formulaire renvoyé avec des erreurs : le focus va au premier champ à corriger, dont le
  // message d'erreur est lu grâce à aria-describedby.
  function placerFocusSurErreur() {
    var champ = document.querySelector('[aria-invalid="true"]');
    if (champ) {
      champ.focus();
    }
  }

  brancherTheme();
  brancherMessages();
  brancherConfirmations();
  placerFocusSurErreur();
})();
