// Applique le thème avant l'affichage : choix enregistré, sinon préférence du système.
(function () {
  "use strict";
  var theme = null;
  try {
    theme = window.localStorage.getItem("theme");
  } catch (erreur) {
    theme = null;
  }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
