# Andean Dashboard

Internal dashboard for Andean employees. It collects to-dos from three places into one list:

- **Dashboard:** to-dos you add yourself or that coworkers send you *(Phase 1, built)*
- **Notion:** tasks assigned to you in a Notion tasks database. Checking one off on the dashboard marks it done in Notion.
- **Slack:** messages and threads that @mention you show up as *suggested* to-dos you can accept or dismiss. The "Add to dashboard" message shortcut saves any message as a to-do.

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
4. Optional: set `ALLOWED_EMAIL_DOMAINS` (e.g. `andean.systems`) and `ADMIN_EMAILS`.

Only accounts in the Andean tenant can sign in. An employee record is created the first time someone signs in.

## Slack setup

1. Go to https://api.slack.com/apps → **Create New App → From an app manifest**, pick the workspace, paste [`slack-manifest.yml`](slack-manifest.yml), click **Create**, then **Install to Workspace → Allow**.
2. Copy three values into `.env`:
   - **Basic Information → App Credentials → Signing Secret** → `SLACK_SIGNING_SECRET`
   - **Basic Information → App-Level Tokens → Generate Token and Scopes**: name it `socket`, add the `connections:write` scope, and copy the `xapp-…` token → `SLACK_APP_TOKEN`
   - **OAuth & Permissions → Bot User OAuth Token** (`xoxb-…`) → `SLACK_BOT_TOKEN`
3. Restart the app. It connects over Socket Mode, so no public URL is needed.
4. In every channel where requests happen, run `/invite @Andean Dashboard`. The bot only sees channels it has been invited to.
5. Sign in to the dashboard with the same email as your Slack profile. That match is how mentions find you.

**Production:** follow the comment at the top of the manifest. Set `socket_mode_enabled: false`, set the request URLs to `https://<BASE_URL>/slack/events` and `/slack/interactions`, and leave `SLACK_APP_TOKEN` unset. Installing in Andean's real workspace needs a Slack admin's approval.

## Notion setup

1. In the Notion workspace, open https://app.notion.com/developers/connections → **Build → Internal connections → Create a new connection** and pick the workspace.
   - Under **Configuration**, enable **Read content**, **Update content** and **Insert content** (only the setup script needs Insert).
   - Choose **Read user information including email addresses**. Without it, assignees can't be matched to employees.
   - Copy the API token into `.env` as `NOTION_TOKEN`.
2. Create a page (e.g. "Dashboard Sandbox"), open **••• → Connections → + Add connection**, and choose your connection.
3. Build a seeded Tasks database (Name, Assignee, Status, Due) under that page:
   ```bash
   .venv/bin/python scripts/setup_notion_sandbox.py --parent-page "<page URL>" --email <your Notion email>
   ```
4. Add the printed `NOTION_TASKS_DATABASE_ID=…` line to `.env` and restart. Tasks sync every 2 minutes, or right away with **Sync Notion** on the dashboard.

For an existing database, skip the script. Share the database with the connection, put its URL or ID in `NOTION_TASKS_DATABASE_ID`, and set `NOTION_ASSIGNEE_PROPERTY` / `NOTION_STATUS_PROPERTY` / `NOTION_DUE_PROPERTY` if its columns are named differently.

## How it's built

- **FastAPI** backend (`app/`), with **SQLAlchemy** on SQLite locally and Postgres in production
- Plain HTML/JS front end (`static/`) using the Andean palette and logomark from `ANDEAN-DESIGN`
- Security: signed session cookies (HTTP-only, 8h, `Secure` in prod), CSRF token on every write, strict CSP, and no API docs exposed

| File | Purpose |
|---|---|
| `app/auth.py` | Microsoft OIDC login, sessions, CSRF |
| `app/todos.py` | To-do API: list, add, send to coworker, complete, delete |
| `app/integrations/slack.py` | Slack events + "Add to dashboard" shortcut (Socket Mode or HTTP) |
| `app/integrations/notion.py` | Notion sync and status push-back |
| `app/integrations/common.py` | Maps Slack/Notion users to employees by email; upserts synced to-dos |
| `scripts/setup_notion_sandbox.py` | Creates a seeded Tasks database in a sandbox Notion workspace |
| `app/models.py` | `Employee` (with `slack_user_id` / `notion_user_id` for mapping) and `Todo` (with `source` / `source_id` / `source_url`) |

## Roadmap

1. ~~Foundation: login, personal to-dos~~
2. ~~Send to-dos to coworkers~~ · Direct messages between employees
3. ~~**Notion:** assigned tasks sync in, check-offs sync back~~
4. ~~**Slack v1:** @mentions become suggested to-dos; "Add to dashboard" shortcut~~
5. **Slack v2:** LLM check that a mention is actually a request, and Slack DM notifications when someone sends you a to-do
6. Polish: live updates, admin page, Alembic migrations, Microsoft sign-in in Andean's tenant

**Testing safely:** develop against a sandbox Slack workspace and sandbox Notion workspace you own, not Andean's real ones. Switching later only changes values in `.env`.
