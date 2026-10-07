# Andean Dashboard

Internal dashboard for Andean employees. It collects to-dos from three places into one list:

- **Dashboard:** to-dos you add yourself or that coworkers send you *(Phase 1, built)*
- **Notion:** tasks assigned to you *(Phase 3)*
- **Slack:** threads that @mention you with a request *(Phase 4–5)*

Employees sign in with their Andean Microsoft (Outlook) account. The password is entered on Microsoft's page, so this app never sees or stores it.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # then set SESSION_SECRET (command is in the file)
.venv/bin/uvicorn app.main:app --reload
```

Open http://localhost:8000. Until Microsoft sign-in is configured, use the **Local development sign-in** box. It's only available when `APP_ENV=development` and `DEV_LOGIN=1`, and the app refuses to start if `DEV_LOGIN` is set in production.

Run the tests with `.venv/bin/python -m pytest`.

## Microsoft sign-in setup (needs Andean IT / an Entra admin)

1. Go to the Entra admin center: **App registrations → New registration**.
   - Name: `Andean Dashboard`
   - Supported account types: **Accounts in this organizational directory only** (single tenant)
   - Redirect URI (Web): `https://<your-domain>/auth/callback`. For local testing, add `http://localhost:8000/auth/callback` too.
2. Under **Certificates & secrets**, create a client secret.
3. Set these environment variables:
   - `MS_TENANT_ID`: Directory (tenant) ID
   - `MS_CLIENT_ID`: Application (client) ID
   - `MS_CLIENT_SECRET`: the secret value
4. Optional: set `ALLOWED_EMAIL_DOMAINS` (e.g. `andean.com`) and `ADMIN_EMAILS`.

Only accounts in the Andean tenant can sign in. An employee record is created the first time someone signs in.

## How it's built

- **FastAPI** backend (`app/`), with **SQLAlchemy** on SQLite locally and Postgres in production
- Plain HTML/JS front end (`static/`) using the Andean palette and logomark from `ANDEAN-DESIGN`
- Security: signed session cookies (HTTP-only, 8h, `Secure` in prod), CSRF token on every write, strict CSP, and no API docs exposed

| File | Purpose |
|---|---|
| `app/auth.py` | Microsoft OIDC login, sessions, CSRF |
| `app/todos.py` | To-do API: list, add, send to coworker, complete, delete |
| `app/models.py` | `Employee` (with `slack_user_id` / `notion_user_id` for mapping) and `Todo` (with `source` / `source_id` / `source_url`) |

## Roadmap

1. ~~Foundation: login, personal to-dos~~
2. ~~Send to-dos to coworkers~~ · Direct messages between employees
3. **Notion:** internal integration syncs tasks where Assignee = employee, with a link back to the page
4. **Slack v1:** Slack app in the workspace; a thread that @mentions someone becomes a *suggested* to-do on their dashboard, plus an "Add to dashboard" message shortcut
5. **Slack v2:** LLM check that a mention is actually a request, with Slack DM notifications when someone sends you a to-do
6. Polish: live updates, two-way Notion status sync, admin page, Alembic migrations

**Slack note:** the bot only sees channels it has been invited to, so it must be added to the channels where requests happen. A Slack workspace admin has to approve installing the app.
