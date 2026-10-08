"""Outlook calendar for the dashboard's Calendar panel.

Each employee connects their calendar by pasting the link Outlook gives when you
publish a calendar (Settings → Calendar → Shared calendars → Publish a calendar →
ICS). The server fetches that .ics file and returns the day's events to its owner only.

This needs no Microsoft app registration. Once Microsoft sign-in is set up, the same
endpoints can read the calendar through Microsoft Graph (Calendars.Read) instead.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
import icalendar
import recurring_ical_events
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import current_employee, require_csrf
from ..config import settings
from ..db import get_db
from ..models import CalendarLink, Employee

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calendar")

# Only Outlook's published-calendar hosts, so the server can't be pointed at anything else
ALLOWED_HOSTS = {"outlook.office365.com", "outlook.office.com", "outlook.live.com"}
MAX_BYTES = 5 * 1024 * 1024
CACHE_SECONDS = 300

# Daily sample meetings in Outlook's format, for people who haven't connected a calendar
SAMPLE_ICS = (Path(__file__).parent / "sample_calendar.ics").read_bytes()

# Tests swap in an httpx.MockTransport here
transport: Optional[httpx.BaseTransport] = None
_cache: Dict[str, Tuple[float, bytes]] = {}  # url -> (fetched at, body)


class CalendarError(Exception):
    pass


class LinkIn(BaseModel):
    url: str = Field(min_length=10, max_length=2000)


def check_url(url: str) -> str:
    """The URL, if it's an https Outlook published-calendar link; raises CalendarError otherwise."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme == "webcal":  # Outlook sometimes offers webcal:// for the same file
        url = "https" + url[len("webcal"):]
        parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ALLOWED_HOSTS \
            or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise CalendarError("Paste the ICS link Outlook gives when you publish your calendar "
                            "(it starts with https://outlook.office365.com/).")
    if not parsed.path.lower().endswith(".ics"):
        raise CalendarError("That's the HTML link. Use the ICS link (it ends in .ics).")
    return url


def _check_request(request: httpx.Request) -> None:
    # Runs for every request, including redirects
    if request.url.scheme != "https" or (request.url.host or "").lower() not in ALLOWED_HOSTS:
        raise CalendarError("Outlook redirected somewhere unexpected.")


def fetch(url: str) -> bytes:
    hit = _cache.get(url)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        with httpx.Client(transport=transport, timeout=10, follow_redirects=True, max_redirects=3,
                          event_hooks={"request": [_check_request]}) as client:
            with client.stream("GET", url, headers={"Accept": "text/calendar"}) as resp:
                if resp.status_code in (401, 403, 404):
                    raise CalendarError("Outlook says that calendar link isn't published anymore. Publish it again and paste the new ICS link.")
                if resp.status_code != 200:
                    raise CalendarError(f"Outlook returned an error ({resp.status_code}). Try again in a minute.")
                body = b""
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        raise CalendarError("That calendar is too large to load.")
    except httpx.HTTPError as exc:
        log.warning("Calendar fetch failed: %s", exc)
        raise CalendarError("Couldn't reach Outlook. Try again in a minute.") from None
    if b"BEGIN:VCALENDAR" not in body[:4096]:
        raise CalendarError("That link didn't return a calendar. Make sure it's the ICS link.")
    _cache[url] = (time.monotonic(), body)
    return body


def _as_datetime(value: Any, tz: ZoneInfo) -> Tuple[datetime, bool]:
    """(aware datetime in tz, all_day)."""
    if isinstance(value, datetime):
        return (value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)), False
    return datetime(value.year, value.month, value.day, tzinfo=tz), True


def events_on(body: bytes, day: date, tz: ZoneInfo) -> List[Dict[str, Any]]:
    """The events overlapping `day` in time zone `tz`, sorted, recurrences expanded."""
    try:
        cal = icalendar.Calendar.from_ical(body)
        start = datetime(day.year, day.month, day.day, tzinfo=tz)
        occurrences = recurring_ical_events.of(cal, skip_bad_series=True).between(start, start + timedelta(days=1))
    except Exception as exc:  # malformed calendar data
        log.warning("Couldn't parse calendar: %s", exc)
        raise CalendarError("Outlook sent a calendar the dashboard couldn't read.") from None
    out = []
    for ev in occurrences:
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        begins, all_day = _as_datetime(ev.decoded("DTSTART"), tz)
        if ev.get("DTEND") is not None:
            ends, _ = _as_datetime(ev.decoded("DTEND"), tz)
        else:
            ends = begins + (ev.decoded("DURATION") if ev.get("DURATION") is not None else timedelta(days=1 if all_day else 0))
        raw = ev.get("CATEGORIES")  # one vCategory, or a list of them for several lines
        lines = raw if isinstance(raw, list) else ([raw] if raw is not None else [])
        cats = [str(c) for line in lines for c in getattr(line, "cats", [])]
        location = str(ev.get("LOCATION", "") or "")
        tag = cats[0] if cats else ("Teams" if "teams" in location.lower() else None)
        out.append({
            "title": str(ev.get("SUMMARY", "") or "(No title)"),
            "start": begins.isoformat(), "end": ends.isoformat(), "all_day": all_day,
            "location": location or None, "tag": tag,
        })
    out.sort(key=lambda e: (not e["all_day"], e["start"]))
    return out


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


@router.get("/today")
def today(tz: str = "UTC", db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    zone = _zone(tz)
    day = datetime.now(timezone.utc).astimezone(zone).date()
    link = db.get(CalendarLink, me.id)
    if link is None:
        if settings.sample_calendar:
            return {"connected": False, "sample": True, "date": day.isoformat(), "events": events_on(SAMPLE_ICS, day, zone)}
        return {"connected": False, "date": day.isoformat(), "events": []}
    try:
        events = events_on(fetch(link.ics_url), day, zone)
    except CalendarError as exc:
        return {"connected": True, "date": day.isoformat(), "events": [], "error": str(exc)}
    return {"connected": True, "date": day.isoformat(), "events": events}


@router.put("/link", dependencies=[Depends(require_csrf)])
def connect(body: LinkIn, db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    try:
        url = check_url(body.url)
        fetch(url)  # make sure it works before saving
    except CalendarError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    link = db.get(CalendarLink, me.id) or CalendarLink(employee_id=me.id)
    link.ics_url = url
    db.add(link)
    db.commit()
    return {"connected": True}


@router.delete("/link", status_code=204, dependencies=[Depends(require_csrf)])
def disconnect(db: Session = Depends(get_db), me: Employee = Depends(current_employee)):
    link = db.get(CalendarLink, me.id)
    if link is not None:
        _cache.pop(link.ics_url, None)
        db.delete(link)
        db.commit()
