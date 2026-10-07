"""Microsoft (Outlook / Microsoft 365) sign-in, sessions, and CSRF protection.

Employees sign in on Microsoft's own page with their Andean email and password
(plus MFA if the tenant requires it). This app never sees or stores passwords.
"""
from __future__ import annotations

import re
import secrets
import time
from typing import Optional

import msal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Employee, utcnow

router = APIRouter()

SCOPES = ["User.Read"]
REDIRECT_PATH = "/auth/callback"
SESSION_SECONDS = 8 * 60 * 60
REMEMBER_SECONDS = 30 * 24 * 60 * 60  # "Remember me"; also the cookie's lifetime
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _msal_app() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        settings.ms_client_id,
        authority=f"https://login.microsoftonline.com/{settings.ms_tenant_id}",
        client_credential=settings.ms_client_secret,
    )


def _start_session(request: Request, employee: Employee, remember: bool = False) -> None:
    # Fresh session on every login to prevent session fixation
    request.session.clear()
    request.session["employee_id"] = employee.id
    request.session["csrf"] = secrets.token_urlsafe(32)
    request.session["expires"] = int(time.time()) + (REMEMBER_SECONDS if remember else SESSION_SECONDS)


def signed_in_id(request: Request) -> Optional[int]:
    """The signed-in employee's id, or None once the session has expired."""
    employee_id = request.session.get("employee_id")
    if employee_id and request.session.get("expires", 0) > time.time():
        return employee_id
    if employee_id:
        request.session.clear()
    return None


def _login_error(code: str) -> RedirectResponse:
    return RedirectResponse(f"/login?error={code}", status_code=302)


def _upsert_employee(db: Session, *, oid: Optional[str], email: str, name: str) -> Employee:
    email = email.lower()
    employee = None
    if oid:
        employee = db.scalar(select(Employee).where(Employee.ms_oid == oid))
    if employee is None:
        employee = db.scalar(select(Employee).where(Employee.email == email))
    if employee is None:
        employee = Employee(email=email, name=name or email, is_admin=email in settings.admin_emails)
        db.add(employee)
    if oid:
        employee.ms_oid = oid
    employee.email = email
    employee.name = name or employee.name
    employee.last_login_at = utcnow()
    db.commit()
    return employee


def current_employee(request: Request, db: Session = Depends(get_db)) -> Employee:
    employee_id = signed_in_id(request)
    employee = db.get(Employee, employee_id) if employee_id else None
    if employee is None or not employee.is_active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Sign in required.")
    return employee


def require_csrf(request: Request) -> None:
    expected = request.session.get("csrf", "")
    supplied = request.headers.get("x-csrf-token", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token.")


@router.get("/auth/login")
def login(request: Request, email: str = "", remember: bool = False):
    """Start Microsoft sign-in. The login page's email prefills Microsoft's form, where the
    employee enters their password (and any second factor)."""
    if not settings.microsoft_configured:
        return _login_error("unavailable")
    email = email.strip().lower()[:320]
    if email and (not EMAIL.match(email) or not settings.email_allowed(email)):
        return _login_error("domain")
    flow = _msal_app().initiate_auth_code_flow(
        SCOPES, redirect_uri=settings.base_url + REDIRECT_PATH, login_hint=email or None)
    request.session.clear()
    request.session["auth_flow"] = flow
    request.session["remember"] = remember
    return RedirectResponse(flow["auth_uri"], status_code=302)


@router.get(REDIRECT_PATH)
def callback(request: Request, db: Session = Depends(get_db)):
    flow = request.session.pop("auth_flow", None)
    remember = bool(request.session.pop("remember", False))
    if not flow:
        return _login_error("expired")
    try:
        result = _msal_app().acquire_token_by_auth_code_flow(flow, dict(request.query_params))
    except ValueError:  # state mismatch / replayed callback
        return _login_error("state")
    claims = result.get("id_token_claims") or {}
    if "error" in result or not claims:
        return _login_error("denied")
    if claims.get("tid") != settings.ms_tenant_id:
        return _login_error("tenant")

    email = (claims.get("email") or claims.get("preferred_username") or "").lower()
    if not email or not settings.email_allowed(email):
        return _login_error("domain")

    employee = _upsert_employee(db, oid=claims.get("oid"), email=email, name=claims.get("name", ""))
    if not employee.is_active:
        return _login_error("inactive")
    _start_session(request, employee, remember)
    return RedirectResponse("/", status_code=302)


@router.post("/auth/logout", dependencies=[Depends(require_csrf)])
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/auth/dev-login")
def dev_login(request: Request, email: str, name: str = "", remember: bool = False, db: Session = Depends(get_db)):
    """Local development only: sign in as any allowed email without Microsoft."""
    if not settings.dev_login_enabled:
        raise HTTPException(status_code=404)
    email = email.strip().lower()[:320]
    if not EMAIL.match(email) or not settings.email_allowed(email):
        return _login_error("domain")
    employee = _upsert_employee(db, oid=None, email=email, name=name or email.split("@")[0].title())
    _start_session(request, employee, remember)
    return RedirectResponse("/", status_code=302)
