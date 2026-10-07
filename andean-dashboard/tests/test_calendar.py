from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.integrations import outlook
from tests.conftest import login

GOOD = "https://outlook.office365.com/owa/calendar/abc@andean.systems/def123/calendar.ics"

# Outlook-style feed: Windows time zone name with its own VTIMEZONE block
OUTLOOK_ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:Microsoft Exchange Server 2010
BEGIN:VTIMEZONE
TZID:Eastern Standard Time
BEGIN:STANDARD
DTSTART:16010101T020000
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=1SU;BYMONTH=11
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:16010101T020000
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=2SU;BYMONTH=3
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:standup
SUMMARY:Design team sync
DTSTART;TZID=Eastern Standard Time:20260901T113000
DTEND;TZID=Eastern Standard Time:20260901T120000
RRULE:FREQ=WEEKLY;BYDAY=TU,WE
CATEGORIES:Team
END:VEVENT
BEGIN:VEVENT
UID:allhands
SUMMARY:All hands
DTSTART;TZID=Eastern Standard Time:20261007T100000
DTEND;TZID=Eastern Standard Time:20261007T104500
LOCATION:Microsoft Teams Meeting
END:VEVENT
BEGIN:VEVENT
UID:cancelled
SUMMARY:Cancelled review
STATUS:CANCELLED
DTSTART;TZID=Eastern Standard Time:20261007T140000
DTEND;TZID=Eastern Standard Time:20261007T150000
END:VEVENT
BEGIN:VEVENT
UID:offsite
SUMMARY:Offsite
DTSTART;VALUE=DATE:20261007
DTEND;VALUE=DATE:20261008
END:VEVENT
BEGIN:VEVENT
UID:tomorrow
SUMMARY:Tomorrow only
DTSTART;TZID=Eastern Standard Time:20261008T090000
DTEND;TZID=Eastern Standard Time:20261008T093000
END:VEVENT
END:VCALENDAR
"""


def today_ics(title="Q4 launch check-in"):
    d = datetime.now(timezone.utc).strftime("%Y%m%d")
    return (f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:x\r\nSUMMARY:{title}\r\n"
            f"DTSTART:{d}T163000Z\r\nDTEND:{d}T170000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n").encode()


@pytest.fixture
def feed(monkeypatch):
    calls = []
    body = {"value": today_ics(), "status": 200}

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(body["status"], content=body["value"], headers={"Content-Type": "text/calendar"})

    monkeypatch.setattr(outlook, "transport", httpx.MockTransport(handler))
    monkeypatch.setattr(outlook, "_cache", {})
    return {"calls": calls, "body": body}


def test_only_outlook_ics_links_are_accepted():
    assert outlook.check_url(GOOD) == GOOD
    assert outlook.check_url(GOOD.replace("https", "webcal", 1)) == GOOD
    for bad in (
        GOOD.replace("https", "http", 1),                                   # not https
        "https://evil.example.com/owa/calendar/x/calendar.ics",             # other host
        "https://outlook.office365.com.evil.com/owa/calendar/x/calendar.ics",
        "https://user:pw@outlook.office365.com/owa/calendar/x/calendar.ics",
        "https://outlook.office365.com:8443/owa/calendar/x/calendar.ics",
        "https://127.0.0.1/calendar.ics",
        GOOD.replace("calendar.ics", "calendar.html"),                      # the HTML link
    ):
        with pytest.raises(outlook.CalendarError):
            outlook.check_url(bad)


def test_parses_outlook_feed_with_recurrence_timezones_and_all_day():
    ny = ZoneInfo("America/New_York")
    events = outlook.events_on(OUTLOOK_ICS, date(2026, 10, 7), ny)  # a Wednesday
    assert [e["title"] for e in events] == ["Offsite", "All hands", "Design team sync"]
    offsite, allhands, sync = events
    assert offsite["all_day"]
    assert allhands["start"] == "2026-10-07T10:00:00-04:00" and allhands["tag"] == "Teams"
    assert sync["start"] == "2026-10-07T11:30:00-04:00" and sync["tag"] == "Team"  # weekly recurrence expanded
    # Same feed viewed from London: times shift, the day's set changes accordingly
    london = outlook.events_on(OUTLOOK_ICS, date(2026, 10, 7), ZoneInfo("Europe/London"))
    assert next(e for e in london if e["title"] == "All hands")["start"] == "2026-10-07T15:00:00+01:00"


def test_connect_today_and_disconnect(feed):
    emma = login("emma@andean.test")
    assert emma.get("/api/calendar/today", params={"tz": "UTC"}).json()["connected"] is False

    assert emma.put("/api/calendar/link", json={"url": GOOD}).json() == {"connected": True}
    data = emma.get("/api/calendar/today", params={"tz": "UTC"}).json()
    assert data["connected"] and [e["title"] for e in data["events"]] == ["Q4 launch check-in"]
    assert feed["calls"] == [GOOD]  # validated once, then served from the 5-minute cache

    # Another employee never sees Emma's calendar or link
    sam = login("sam@andean.test")
    assert sam.get("/api/calendar/today").json() == {"connected": False, "date": sam.get("/api/calendar/today").json()["date"], "events": []}

    assert emma.delete("/api/calendar/link").status_code == 204
    assert emma.get("/api/calendar/today").json()["connected"] is False


def test_rejects_bad_links_and_requires_csrf(feed):
    client = login("emma@andean.test")
    r = client.put("/api/calendar/link", json={"url": "https://example.com/calendar.ics"})
    assert r.status_code == 400 and "outlook.office365.com" in r.json()["detail"]

    feed["body"]["value"] = b"<html>sign in</html>"
    r = client.put("/api/calendar/link", json={"url": GOOD})
    assert r.status_code == 400 and "ICS" in r.json()["detail"]

    feed["body"].update(status=404, value=b"")
    r = client.put("/api/calendar/link", json={"url": GOOD})
    assert r.status_code == 400 and "isn't published" in r.json()["detail"]

    client.headers.pop("X-CSRF-Token")
    assert client.put("/api/calendar/link", json={"url": GOOD}).status_code == 403


def test_redirects_off_outlook_are_blocked(monkeypatch):
    def handler(request):
        if request.url.host == "outlook.office365.com":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})
        return httpx.Response(200, content=b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")
    monkeypatch.setattr(outlook, "transport", httpx.MockTransport(handler))
    monkeypatch.setattr(outlook, "_cache", {})
    with pytest.raises(outlook.CalendarError, match="unexpected"):
        outlook.fetch(GOOD)


def test_feed_errors_show_in_panel_without_failing(feed):
    client = login("emma@andean.test")
    client.put("/api/calendar/link", json={"url": GOOD})
    monkey_cache = outlook._cache
    monkey_cache.clear()
    feed["body"].update(status=500, value=b"")
    data = client.get("/api/calendar/today").json()
    assert data["connected"] and data["events"] == [] and "error" in data
