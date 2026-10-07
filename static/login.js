const ERRORS = {
  expired: "Your sign-in took too long. Please try again.",
  state: "That sign-in link was already used. Please try again.",
  denied: "Microsoft sign-in was cancelled or failed.",
  tenant: "Please sign in with your Andean work account.",
  domain: "That email isn't allowed to use this dashboard.",
  inactive: "Your dashboard access has been turned off. Contact an admin.",
};

const code = new URLSearchParams(location.search).get("error");
if (code) {
  const box = document.getElementById("error");
  box.textContent = ERRORS[code] || "Sign-in failed. Please try again.";
  box.hidden = false;
}

fetch("/auth/config")
  .then((r) => r.json())
  .then((cfg) => {
    if (!cfg.microsoft) {
      const btn = document.getElementById("ms-login");
      btn.setAttribute("aria-disabled", "true");
      btn.removeAttribute("href");
      btn.style.opacity = ".5";
      btn.title = "Microsoft sign-in is not configured yet";
    }
    document.getElementById("dev-login").hidden = !cfg.dev_login;
  })
  .catch(() => {});
