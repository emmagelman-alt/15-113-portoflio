const ERRORS = {
  expired: "Your sign-in took too long. Please try again.",
  state: "That sign-in link was already used. Please try again.",
  denied: "Microsoft sign-in was cancelled or failed.",
  tenant: "Please sign in with your Andean work account.",
  domain: "Use your Andean work email (for example, you@andean.systems).",
  inactive: "Your dashboard access has been turned off. Contact an admin.",
  unavailable: "Microsoft sign-in isn't set up yet. Contact an admin.",
};

const $ = (id) => document.getElementById(id);
const form = $("login-form");
const email = $("email");

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

const code = new URLSearchParams(location.search).get("error");
if (code) showError(ERRORS[code] || "Sign-in failed. Please try again.");

form.addEventListener("submit", (e) => {
  if (!email.value.trim() || !email.checkValidity()) {
    e.preventDefault();
    showError("Enter your Andean work email.");
    email.focus();
  }
});

fetch("/auth/config")
  .then((r) => r.json())
  .then((cfg) => {
    if (cfg.microsoft) return;
    if (cfg.dev_login) {
      // Local development only: the server refuses to start with this on in production
      form.action = "/auth/dev-login";
      $("continue-text").textContent = "Continue (local test mode)";
      $("note").textContent = "Local test mode: Microsoft sign-in isn't set up yet, so no password is needed on this computer.";
    } else {
      $("continue").disabled = true;
      $("note").textContent = ERRORS.unavailable;
    }
  })
  .catch(() => {});

email.focus();
