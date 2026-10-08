# Andean Dashboard

Internal dashboard for Andean employees. It collects to-dos from three places into one list:

- **Dashboard:** to-dos you add yourself or that coworkers send you *(Phase 1, built)*
- **Notion:** tasks assigned to you in a Notion tasks database. Checking one off on the dashboard marks it done in Notion.
- **Slack:** messages and threads that @mention you show up as *suggested* to-dos you can accept or dismiss. The "Add to dashboard" message shortcut saves any message as a to-do.

**Click any to-do** to open its task panel and work on it without leaving the dashboard:
- **Slack:** the full thread, with a reply box. Replies post as you when your Slack user token is set; otherwise they post as the Andean Dashboard bot, signed with your name.
- **Notion:** the page's content and comments. Change the status or due date (written back to Notion) and add comments.
- **From a coworker:** a conversation with the person who sent it.
- **Attach files** (📎 or paste) to any reply, up to 10 MB each. Coworker conversations show them inline; Notion comments get them as real Notion attachments (up to 3); Slack replies upload them when the app has `files:write`, otherwise they include a link to the file on the dashboard.
- **Linked docs:** Figma files and Google Docs/Sheets/Slides preview inline. Linked Notion pages render inside the panel when they're shared with the connection.

The layout follows the Figma "Dashboard" frame: to-dos on the left; **Calendar**, **Machines** and the **sherpa.ai** assistant on the right. **Calendar** shows today's meetings from each person's own Outlook calendar; **Machines** and **sherpa.ai** show labelled sample data (`static/widgets.js`) until real sources are connected.

Employees sign in with their Andean Microsoft (Outlook) account. The login page (from the Figma design) takes their work email, then hands off to Microsoft's own page, prefilled, for the password and any two-factor code, so the dashboard never handles passwords. **Remember me** keeps them signed in for 30 days instead of 8 hours, and **Forgot?** opens Microsoft's password reset. The password is entered on Microsoft's page, so this app never sees or stores it.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # then set SESSION_SECRET (command is in the file)
.venv/bin/uvicorn app.main:app --reload
```

Open http://localhost:8000. Until Microsoft sign-in is configured, use the **Local development sign-in** box. It's only available when `APP_ENV=development` and `DEV_LOGIN=1`, and the app refuses to start if `DEV_LOGIN` is set in production.

Run the tests with `.venv/bin/python -m pytest`.

## Password-protected demo (class portfolio)

`APP_ENV=demo` runs a showcase with no Microsoft, Slack or Notion setup:

- The login page asks for an email and a **shared demo password** (`DEMO_PASSWORD`, at least 6 characters; the app refuses to start without it). Wrong passwords are rate-limited: 8 tries per visitor and 60 overall per 5 minutes.
- Only emails in `ALLOWED_EMAIL_DOMAINS` (set it to a demo domain like `andean.test`) can sign in, so real company accounts never exist in the demo.
- Each new visitor gets a few starter to-dos from sample coworkers.
- Everything except the login page, static files and `/healthz` requires sign-in.

On Render: set `APP_ENV=demo`, `DEMO_PASSWORD`, `ALLOWED_EMAIL_DOMAINS=andean.test`, and a generated `SESSION_SECRET`. `BASE_URL` defaults to Render's `RENDER_EXTERNAL_URL`. With the default SQLite database the demo resets on each deploy.

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
6. **Replying from the task panel (optional):** under **OAuth & Permissions → User Token Scopes**, add `chat:write` (the manifest already includes it), click **Reinstall to Workspace**, and copy the **User OAuth Token** (`xoxp-…`) into `.env` as `SLACK_USER_TOKEN`. Replies then post as the person who owns that token. This is a one-person prototype; a per-employee "Connect Slack" flow comes later.

**Production:** follow the comment at the top of the manifest. Set `socket_mode_enabled: false`, set the request URLs to `https://<BASE_URL>/slack/events` and `/slack/interactions`, and leave `SLACK_APP_TOKEN` unset. Installing in Andean's real workspace needs a Slack admin's approval.

## Notion setup

1. In the Notion workspace, open https://app.notion.com/developers/connections → **Build → Internal connections → Create a new connection** and pick the workspace.
   - Under **Configuration**, enable **Read content**, **Update content** and **Insert content** (only the setup script needs Insert), plus **Read comments** and **Insert comments** for the task panel.
   - Choose **Read user information including email addresses**. Without it, assignees can't be matched to employees.
   - Copy the API token into `.env` as `NOTION_TOKEN`.
2. Create a page (e.g. "Dashboard Sandbox"), open **••• → Connections → + Add connection**, and choose your connection.
3. Build a seeded Tasks database (Name, Assignee, Status, Due) under that page:
   ```bash
   .venv/bin/python scripts/setup_notion_sandbox.py --parent-page "<page URL>" --email <your Notion email>
   ```
4. Add the printed `NOTION_TASKS_DATABASE_ID=…` line to `.env` and restart. Tasks sync every 2 minutes, or right away with **Sync Notion** on the dashboard.

For an existing database, skip the script. Share the database with the connection, put its URL or ID in `NOTION_TASKS_DATABASE_ID`, and set `NOTION_ASSIGNEE_PROPERTY` / `NOTION_STATUS_PROPERTY` / `NOTION_DUE_PROPERTY` if its columns are named differently.

## Outlook calendar

Each employee connects their own calendar from the Calendar panel. No Microsoft app registration is needed:

1. In Outlook on the web, go to **Settings → Calendar → Shared calendars**.
2. Under **Publish a calendar**, choose the calendar and **Can view all details**, then **Publish**.
3. Copy the **ICS** link (ends in `.ics`) and paste it into the Calendar panel.

The link is stored on the server (`calendar_links` table) and only that person's meetings are returned to them. Only `https://outlook.office365.com`, `outlook.office.com` and `outlook.live.com` links are accepted, including after redirects, so the server can't be pointed elsewhere. Unpublishing the calendar in Outlook revokes the link. Once Microsoft sign-in is set up, this can move to Microsoft Graph (`Calendars.Read`).

## How it's built

- **FastAPI** backend (`app/`), with **SQLAlchemy** on SQLite locally and Postgres in production
- Plain HTML/JS front end (`static/`) using the Andean palette and logomark from `ANDEAN-DESIGN`
- Security: signed session cookies (HTTP-only, 8h, `Secure` in prod), CSRF token on every write, strict CSP, and no API docs exposed

| File | Purpose |
|---|---|
| `app/auth.py` | Microsoft OIDC login, sessions, CSRF |
| `app/todos.py` | To-do API: list, add, send to coworker, complete, delete |
| `app/demo.py` | Password-protected demo sign-in and starter to-dos |
| `app/integrations/outlook.py` | Outlook calendar: link validation, .ics fetch, recurring events in the viewer's time zone |
| `static/widgets.js` | Calendar, Machines and sherpa.ai panels |
| `app/details.py` | Task panel API: Slack thread and replies, Notion page/comments/edits, coworker conversation, linked-doc previews |
| `static/panel.js` | The task panel UI |
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
