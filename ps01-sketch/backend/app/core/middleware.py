"""
core/middleware.py
------------------
AuditMiddleware — automatic chain-of-custody logging for every protected API action.

How It Works
============

  ┌─────────────────────────────────────────────────────────┐
  │  Incoming HTTP Request                                  │
  │                                                         │
  │  1. Match (method, path) against AUDITED_ROUTES table   │
  │     → skip silently if not listed                       │
  │                                                         │
  │  2. Cache request body bytes so the route can read it   │
  │     (Starlette streams are single-read; we replay them) │
  │                                                         │
  │  3. Best-effort JWT decode from Authorization header    │
  │     → extracts user_id UUID (None if missing/invalid)   │
  │     → middleware NEVER blocks a request on auth failure │
  │                                                         │
  │  4. Best-effort case_id extraction                      │
  │     a) UUID from the URL path  (/cases/{uuid})          │
  │     b) "case_id" key in the JSON body                   │
  │                                                         │
  │  5. Forward to the actual route handler                 │
  │                                                         │
  │  6. AFTER response:                                     │
  │     • prefix action with "[FAILED {status}]" if 4xx/5xx│
  │     • write AuditLog row using its OWN AsyncSession     │
  │       (independent of the request session which may     │
  │        have been rolled back)                           │
  │     • swallow any DB error — audit must never crash app │
  └─────────────────────────────────────────────────────────┘

Extending
=========
Add a tuple to AUDITED_ROUTES to cover a new endpoint automatically.

For precise per-action strings (e.g. "Applied Disguise: Full Beard") use the
AuditRecorder dependency from core/deps.py inside the route handler.  Both
the coarse middleware entry AND the fine recorder entry will be written —
giving you a complete picture in the audit table.

Registration (in main.py)
=========================
    from app.core.middleware import AuditMiddleware
    app.add_middleware(AuditMiddleware)
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.core.security import decode_token_silent, get_token_from_header
from app.database import AsyncSessionLocal
from app.models import AuditLog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Route → action-name mapping
# ---------------------------------------------------------------------------
# Each entry: (HTTP_METHOD, compiled_regex_for_path, action_string)
# Evaluated top-to-bottom; first match wins.
# ---------------------------------------------------------------------------
_UUID_SEG = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

AUDITED_ROUTES: list[tuple[str, re.Pattern[str], str]] = [
    # ── Auth ──────────────────────────────────────────────────────────────
    ("POST",   re.compile(r"^/auth/login$"),
               "User Login"),
    ("POST",   re.compile(r"^/auth/login/form$"),
               "User Login (Swagger Form)"),
    ("POST",   re.compile(r"^/auth/register$"),
               "User Registered"),
    ("POST",   re.compile(r"^/auth/logout$"),
               "User Logout"),
    ("GET",    re.compile(r"^/auth/me$"),
               "Viewed Own Profile"),

    # ── Cases ─────────────────────────────────────────────────────────────
    ("GET",    re.compile(r"^/cases$"),
               "Listed Cases"),
    ("POST",   re.compile(r"^/cases$"),
               "Created New Case"),
    ("GET",    re.compile(rf"^/cases/{_UUID_SEG}$"),
               "Viewed Case"),
    ("PATCH",  re.compile(rf"^/cases/{_UUID_SEG}$"),
               "Updated Case"),
    ("DELETE", re.compile(rf"^/cases/{_UUID_SEG}$"),
               "Deleted Case"),

    # ── Audit logs ────────────────────────────────────────────────────────
    ("GET",    re.compile(rf"^/audit-logs/{_UUID_SEG}$"),
               "Viewed Audit Log"),
    ("GET",    re.compile(r"^/audit-logs$"),
               "Viewed All Audit Logs"),

    # ── Sketch AI pipeline (text → traits) ────────────────────────────────
    ("POST",   re.compile(r"^/generate-sketch$"),
               "Generated Initial Sketch"),
    ("POST",   re.compile(r"^/refine-sketch$"),
               "Refined Sketch via Chat"),
    ("POST",   re.compile(r"^/apply-disguise$"),
               "Toggled Disguise Overlay"),
    ("POST",   re.compile(r"^/export$"),
               "Exported High-Res Image"),
    ("POST",   re.compile(r"^/reset$"),
               "Reset Canvas"),

    # ── Image generation & inpainting ─────────────────────────────────────
    ("GET",    re.compile(r"^/image/status$"),
               "Checked Image Generation Status"),
    ("POST",   re.compile(r"^/image/generate$"),
               "Generated AI Sketch Image"),
    ("POST",   re.compile(r"^/image/refine$"),
               "Refined AI Sketch via Inpainting"),
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------
_UUID_ANYWHERE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


def _match_route(method: str, path: str) -> str | None:
    """Return the action template string for (method, path), or None if not audited."""
    for m, pattern, action in AUDITED_ROUTES:
        if m == method and pattern.match(path):
            return action
    return None


def _uuid_from_path(path: str) -> uuid.UUID | None:
    """Extract the first UUID-shaped segment from a URL path (e.g. /cases/{uuid})."""
    match = _UUID_ANYWHERE.search(path)
    if match:
        try:
            return uuid.UUID(match.group())
        except ValueError:
            pass
    return None


def _uuid_from_body(body: bytes) -> uuid.UUID | None:
    """
    Parse the request body as JSON and return the value of the top-level
    'case_id' key as a UUID.  Returns None on any failure.
    """
    if not body:
        return None
    try:
        data: dict = json.loads(body)
        raw = data.get("case_id")
        if raw:
            return uuid.UUID(str(raw))
    except (json.JSONDecodeError, ValueError, AttributeError, TypeError):
        pass
    return None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class AuditMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that writes one audit_logs row for every action listed
    in AUDITED_ROUTES.  Register with:

        app.add_middleware(AuditMiddleware)
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        method: str = request.method
        path:   str = request.url.path

        # ── 1. Quick exit for un-audited paths ────────────────────────────
        action_template = _match_route(method, path)
        if action_template is None:
            return await call_next(request)

        # ── 2. Cache body so the downstream route can still read it ───────
        raw_body: bytes = await request.body()

        async def _replay():
            return {"type": "http.request", "body": raw_body, "more_body": False}

        # Rebuild a Request that replays the cached body bytes
        patched_request = Request(request.scope, _replay)

        # ── 3. Extract user_id from Bearer JWT (best-effort) ──────────────
        user_id: uuid.UUID | None = None
        auth_header = request.headers.get("Authorization")
        token = get_token_from_header(auth_header)
        if token:
            payload = decode_token_silent(token)
            if payload:
                try:
                    user_id = uuid.UUID(payload["sub"])
                except (KeyError, ValueError):
                    pass

        # ── 4. Extract case_id (URL path first, then request body) ────────
        case_id: uuid.UUID | None = (
            _uuid_from_path(path) or _uuid_from_body(raw_body)
        )

        # ── 5. Forward to the route handler ───────────────────────────────
        response: Response = await call_next(patched_request)
        status_code: int  = response.status_code

        # ── 6. Build final action string ──────────────────────────────────
        # 4xx/5xx responses are still logged but clearly marked as failures
        if status_code >= 400:
            final_action = f"[FAILED {status_code}] {action_template}"
        else:
            final_action = action_template

        # ── 7. Write audit row — own session, never blocks the response ───
        await self._write(user_id, case_id, final_action)

        return response

    @staticmethod
    async def _write(
        user_id: uuid.UUID | None,
        case_id: uuid.UUID | None,
        action:  str,
    ) -> None:
        """
        Open an independent DB session and persist one AuditLog row.

        Deliberately isolated from the request session so a rolled-back
        request transaction does NOT swallow the audit entry.
        All errors are caught and logged — audit must never crash the app.
        """
        try:
            async with AsyncSessionLocal() as session:
                entry = AuditLog(
                    user_id=user_id,
                    case_id=case_id,
                    action=action,
                    timestamp=datetime.now(timezone.utc),
                )
                session.add(entry)
                await session.commit()
        except Exception:
            # Swallow but surface in logs so ops can investigate
            logger.exception(
                "AuditMiddleware: failed to persist log entry "
                "[user_id=%s case_id=%s action=%r]",
                user_id,
                case_id,
                action,
            )
