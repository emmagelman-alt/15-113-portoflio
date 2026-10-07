"""Create and seed a "Tasks" database in a sandbox Notion workspace for the dashboard to sync.

    .venv/bin/python scripts/setup_notion_sandbox.py --parent-page <url-or-id> --email you@andean.com

Needs NOTION_TOKEN in .env (an internal connection with Read, Update and Insert content and
"Read user information including email addresses"), and the parent page shared with that
connection (open the page → ••• → Connections → add it).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.integrations.notion import NotionError, api, make_client, notion_id  # noqa: E402

# (name, color, status group)
STATUSES = [("To do", "gray", "To-do"), ("In progress", "blue", "In progress"), ("Done", "green", "Complete")]
# (title, due in N days, status)
SAMPLE_TASKS = [
    ("Design mockup for the internal tools page", 3, "In progress"),
    ("Review the Q4 onboarding checklist with HR", 7, "To do"),
    ("Write release notes for the dashboard beta", 12, "To do"),
    ("Collect feedback on the new expense form", -2, "Done"),
]


def fail(message: str) -> None:
    sys.exit(f"Error: {message}")


def find_user(client: httpx.Client, email: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {"page_size": 100}
    people: List[Dict[str, Any]] = []
    while True:
        data = api(client, "GET", "/users", params=params)
        people += [u for u in data.get("results", []) if u.get("type") == "person"]
        if not data.get("has_more"):
            break
        params["start_cursor"] = data["next_cursor"]
    for user in people:
        if (user.get("person") or {}).get("email", "").lower() == email.lower():
            return user
    if people and not any((u.get("person") or {}).get("email") for u in people):
        fail("Notion didn't return any emails. In the connection's Configuration tab, set user capabilities "
             "to 'Read user information including email addresses', then run this again.")
    fail(f"No member of this Notion workspace has the email {email}. (Guests aren't listed; "
         "invite the person as a member.)")


def create_database(client: httpx.Client, parent_id: str, title: str, use_status: bool) -> Dict[str, Any]:
    if use_status:
        status = {"status": {"options": [{"name": n, "color": c, "group": g} for n, c, g in STATUSES]}}
    else:
        status = {"select": {"options": [{"name": n, "color": c} for n, c, _ in STATUSES]}}
    return api(client, "POST", "/databases", json={
        "parent": {"type": "page_id", "page_id": parent_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "initial_data_source": {"properties": {
            "Name": {"title": {}},
            settings.notion_assignee_property: {"people": {}},
            settings.notion_status_property: status,
            settings.notion_due_property: {"date": {}},
        }},
    })


def add_task(client: httpx.Client, source_id: str, user_id: str, kind: str,
             title: str, due: date, status: str) -> None:
    api(client, "POST", "/pages", json={
        "parent": {"type": "data_source_id", "data_source_id": source_id},
        "properties": {
            "Name": {"title": [{"type": "text", "text": {"content": title}}]},
            settings.notion_assignee_property: {"people": [{"id": user_id}]},
            settings.notion_status_property: {kind: {"name": status}},
            settings.notion_due_property: {"date": {"start": due.isoformat()}},
        },
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--parent-page", required=True, help="URL or ID of a page shared with the connection")
    parser.add_argument("--email", required=True, help="Notion email of the person to assign the sample tasks to")
    parser.add_argument("--title", default="Tasks", help="database title (default: Tasks)")
    args = parser.parse_args()

    token = os.getenv("NOTION_TOKEN", "")
    if not token:
        fail("NOTION_TOKEN isn't set. Add your connection's API token to .env as NOTION_TOKEN=...")
    parent_id = notion_id(args.parent_page)
    if len(parent_id) != 32:
        fail(f"'{args.parent_page}' doesn't look like a Notion page URL or ID.")

    with make_client(token) as client:
        try:
            user = find_user(client, args.email)
            print(f"Found Notion user {user.get('name') or args.email}")
            try:
                database = create_database(client, parent_id, args.title, use_status=True)
                kind = "status"
            except NotionError as exc:
                if exc.status != 400:
                    raise
                print(f"Couldn't create a Status-type property ({exc}); using a select instead.")
                database = create_database(client, parent_id, args.title, use_status=False)
                kind = "select"
            source_id = database["data_sources"][0]["id"]
            for title, days, status in SAMPLE_TASKS:
                add_task(client, source_id, user["id"], kind, title, date.today() + timedelta(days=days), status)
                print(f"  added: {title} ({status})")
        except NotionError as exc:
            if exc.status == 401:
                fail("Notion rejected NOTION_TOKEN. Copy the API token from the connection's Configuration tab again.")
            if exc.status == 404:
                fail("Couldn't find the parent page. Share it with your connection: open the page in Notion → "
                     "••• → Connections → add the connection, then run this again.")
            if exc.status == 403:
                fail(f"The connection is missing a capability ({exc}). In its Configuration tab enable Read, "
                     "Update and Insert content, and 'Read user information including email addresses'.")
            fail(str(exc))
        except httpx.HTTPError as exc:
            fail(f"Couldn't reach Notion: {exc}")

    print(f"\nCreated '{args.title}' with {len(SAMPLE_TASKS)} sample tasks: {database.get('url', '')}")
    print("\nAdd this line to .env, then restart the app:\n")
    print(f"NOTION_TASKS_DATABASE_ID={database['id'].replace('-', '')}")


if __name__ == "__main__":
    main()
