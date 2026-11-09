(function () {
  try {
    var saved = localStorage.getItem("lasrra-theme");
    if (saved === "light" || saved === "dark") {
      document.documentElement.setAttribute("data-theme", saved);
    }
  } catch {
    /* storage blocked: follow the system setting */
  }
})();
