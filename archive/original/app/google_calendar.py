"""One-way sync of Blackboard deadlines into a Google calendar named WhiteBoard.

Sign-in uses a desktop OAuth client the user creates in Google Cloud. The
refresh token stays in the local data folder and is not written into settings.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

from blackboard.api import deadline_is_finished, event_is_all_day
from blackboard.auth import resolve_url
from blackboard.models import Deadline, Snapshot
from blackboard.store import DATA_DIR

ACCOUNT_PATH = DATA_DIR / "google_calendar.json"
CALENDAR_NAME = "WhiteBoard"
SCOPE = "openid email https://www.googleapis.com/auth/calendar.app.created"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_ROOT = "https://www.googleapis.com/calendar/v3"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

_LOCK = threading.Lock()
Transport = Callable[[str, str, dict[str, str] | None, bytes | None], tuple[int, Any]]


class GoogleCalendarError(RuntimeError):
    pass


def google_event_id(key: str) -> str:
    """Stable Calendar event id. Google only allows a-v and digits."""
    number = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
    alphabet = "0123456789abcdefghijklmnopqrstuv"
    chars: list[str] = []
    while number and len(chars) < 48:
        number, rem = divmod(number, 32)
        chars.append(alphabet[rem])
    # Prefix must stay inside Google's a-v alphabet. "w" is not allowed.
    return "bb" + "".join(chars)


def events_for_sync(
    snapshot: Snapshot,
    *,
    base_url: str,
    hide_other: bool = False,
    allowed_course_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Events that should exist on the WhiteBoard calendar right now."""
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for deadline in snapshot.deadlines:
        if deadline.when is None:
            continue
        if hide_other and deadline.kind == "other":
            continue
        if deadline.kind != "other" and deadline_is_finished(snapshot, deadline):
            continue
        if allowed_course_ids is not None and deadline.course_id:
            if deadline.course_id not in allowed_course_ids:
                continue
        event = _event_body(snapshot, deadline, base_url)
        if event["id"] in seen:
            continue
        seen.add(event["id"])
        events.append(event)
    return events


def load_account() -> dict[str, Any]:
    if not ACCOUNT_PATH.exists():
        return {}
    try:
        data = json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return _clean_account(data)


def save_account(account: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNT_PATH.write_text(
        json.dumps(_clean_account(account), indent=2),
        encoding="utf-8",
    )


def remember_client(client_id: str, client_secret: str) -> dict[str, Any]:
    account = load_account()
    if client_id.strip():
        account["client_id"] = client_id.strip()
    if client_secret.strip():
        account["client_secret"] = client_secret.strip()
    save_account(account)
    return account


def sign_in(client_id: str, client_secret: str, *, timeout: float = 180) -> dict[str, Any]:
    """Open the system browser and wait for Google to redirect back here."""
    client_id = client_id.strip()
    client_secret = client_secret.strip()
    if not client_id or not client_secret:
        raise GoogleCalendarError("Paste the Google OAuth client ID and secret first.")
    verifier = secrets.token_urlsafe(64)
    challenge = _code_challenge(verifier)
    state = secrets.token_urlsafe(24)
    result: dict[str, list[str]] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            result.update(urllib.parse.parse_qs(parsed.query))
            body = (
                "<html><body><p>Google sign-in complete. "
                "You can close this window and return to WhiteBoard.</p></body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 1
    port = int(server.server_address[1])
    redirect_uri = f"http://127.0.0.1:{port}/"
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    webbrowser.open(f"{AUTH_URL}?{query}")
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline and not result:
            server.handle_request()
    finally:
        server.server_close()
    if not result:
        raise GoogleCalendarError("Google sign-in was cancelled.")
    if (result.get("state") or [""])[0] != state:
        raise GoogleCalendarError("Google sign-in did not match this app. Try again.")
    if result.get("error"):
        raise GoogleCalendarError(result["error"][0])
    code = (result.get("code") or [""])[0]
    if not code:
        raise GoogleCalendarError("Google did not return a sign-in code.")
    token = _token_request(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
    )
    account = load_account()
    account.update(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": str(token.get("refresh_token") or account.get("refresh_token") or ""),
            "access_token": str(token.get("access_token") or ""),
            "expires_at": time.time() + int(token.get("expires_in") or 3600),
            "calendar_id": str(account.get("calendar_id") or ""),
        }
    )
    if not account["refresh_token"]:
        raise GoogleCalendarError("Google did not grant offline access. Sign in again.")
    account["email"] = _email(account["access_token"])
    save_account(account)
    return account


def sign_out() -> None:
    account = load_account()
    for key in ("refresh_token", "access_token", "expires_at", "email", "calendar_id"):
        account.pop(key, None)
    save_account(account)


def sync_account(
    account: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    transport: Transport | None = None,
) -> tuple[dict[str, Any], str]:
    """Create or update the WhiteBoard calendar so it matches `events`."""
    with _LOCK:
        account = _ensure_access(dict(account), transport)
        calendar_id = str(account.get("calendar_id") or "")
        if calendar_id and not _calendar_exists(account, calendar_id, transport):
            calendar_id = ""
        if not calendar_id:
            calendar_id = _find_whiteboard_calendar(account, transport) or _create_calendar(
                account, transport
            )
            account["calendar_id"] = calendar_id
            save_account(account)
        _show_calendar(account, calendar_id, transport)
        wanted = {str(event["id"]) for event in events}
        updated = _upsert_events(account, calendar_id, events, transport)
        removed = 0
        stale = [
            existing_id
            for existing_id in _list_event_ids(account, calendar_id, transport)
            if existing_id not in wanted
        ]
        _delete_events(account, calendar_id, stale, transport)
        removed = len(stale)
        save_account(account)
    noun = "event" if updated == 1 else "events"
    return (
        account,
        f"Google Calendar updated: {updated} {noun}, removed {removed}. "
        "Turn on the calendar named WhiteBoard in Google Calendar's sidebar.",
    )


def _event_body(snapshot: Snapshot, deadline: Deadline, base_url: str) -> dict[str, Any]:
    course = snapshot.course_name(deadline.course_id)
    title = deadline.title or "Untitled"
    summary = f"{course}: {title}" if course else title
    kind = {"assignment": "Assignment", "test": "Test"}.get(deadline.kind, "Event")
    lines = [kind]
    if course:
        lines.append(course)
    if deadline.blackboard_url:
        lines.append(resolve_url(base_url, deadline.blackboard_url))
    key = deadline.id or f"{deadline.course_id}:{title}:{deadline.when}"
    return {
        "id": google_event_id(key),
        "summary": summary,
        "description": "\n".join(lines),
        "start": _when_bound(deadline.when, end=False),
        "end": _when_bound(deadline.when, end=True),
        "extendedProperties": {"private": {"whiteboard": "1"}},
    }


def _when_bound(when: datetime | None, *, end: bool) -> dict[str, str]:
    assert when is not None
    if event_is_all_day(when):
        day = when.astimezone().date()
        if end:
            day = day + timedelta(days=1)
        return {"date": day.isoformat()}
    moment = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    local = moment.astimezone()
    if end:
        local = local + timedelta(minutes=30)
    return {"dateTime": local.isoformat(timespec="seconds")}


def _ensure_access(account: dict[str, Any], transport: Transport | None) -> dict[str, Any]:
    if not account.get("refresh_token"):
        raise GoogleCalendarError("Sign in to Google in Settings.")
    if not account.get("client_id") or not account.get("client_secret"):
        raise GoogleCalendarError("Paste the Google OAuth client ID and secret first.")
    expires = float(account.get("expires_at") or 0)
    if account.get("access_token") and expires > time.time() + 60:
        return account
    token = _token_request(
        {
            "client_id": account["client_id"],
            "client_secret": account["client_secret"],
            "refresh_token": account["refresh_token"],
            "grant_type": "refresh_token",
        },
        transport=transport,
    )
    account["access_token"] = str(token.get("access_token") or "")
    account["expires_at"] = time.time() + int(token.get("expires_in") or 3600)
    if token.get("refresh_token"):
        account["refresh_token"] = str(token["refresh_token"])
    if not account["access_token"]:
        raise GoogleCalendarError("Google did not refresh the sign-in. Sign in again.")
    return account


def _calendar_exists(
    account: dict[str, Any], calendar_id: str, transport: Transport | None
) -> bool:
    status, _body = _api("GET", f"/calendars/{_q(calendar_id)}", account, transport=transport)
    return status == 200


def _find_whiteboard_calendar(account: dict[str, Any], transport: Transport | None) -> str:
    """Reuse a WhiteBoard calendar left behind when an earlier sync stopped early."""
    page = ""
    while True:
        query = "maxResults=250"
        if page:
            query += "&pageToken=" + _q(page)
        status, body = _api(
            "GET",
            f"/users/me/calendarList?{query}",
            account,
            transport=transport,
        )
        if status != 200 or not isinstance(body, dict):
            return ""
        for item in body.get("items") or []:
            if isinstance(item, dict) and item.get("summary") == CALENDAR_NAME and item.get("id"):
                return str(item["id"])
        page = str(body.get("nextPageToken") or "")
        if not page:
            return ""


def _show_calendar(account: dict[str, Any], calendar_id: str, transport: Transport | None) -> None:
    """Make sure the WhiteBoard calendar is checked in the Google Calendar sidebar."""
    status, _body = _api(
        "POST",
        "/users/me/calendarList",
        account,
        payload={"id": calendar_id, "selected": True, "hidden": False},
        transport=transport,
    )
    if status == 409:
        _api(
            "PATCH",
            f"/users/me/calendarList/{_q(calendar_id)}",
            account,
            payload={"selected": True, "hidden": False},
            transport=transport,
        )


def _create_calendar(account: dict[str, Any], transport: Transport | None) -> str:
    status, body = _api(
        "POST",
        "/calendars",
        account,
        payload={"summary": CALENDAR_NAME, "description": "Deadlines and events from WhiteBoard"},
        transport=transport,
    )
    if status not in (200, 201) or not isinstance(body, dict) or not body.get("id"):
        raise GoogleCalendarError(_error_text(body) or "Couldn't create the WhiteBoard calendar.")
    return str(body["id"])


def _upsert_events(
    account: dict[str, Any],
    calendar_id: str,
    events: list[dict[str, Any]],
    transport: Transport | None,
) -> int:
    missing: list[dict[str, Any]] = []
    for chunk in _chunks(events, 40):
        calls = [
            (
                str(event["id"]),
                "PUT",
                f"/calendars/{_q(calendar_id)}/events/{_q(str(event['id']))}",
                event,
            )
            for event in chunk
        ]
        results = _batch_api(account, calls, transport)
        for event in chunk:
            status, body = results.get(str(event["id"]), (0, {}))
            if status == 404:
                missing.append(event)
            elif status not in (200, 201):
                raise GoogleCalendarError(_error_text(body) or "Couldn't update a Google Calendar event.")
    for chunk in _chunks(missing, 40):
        calls = [
            (
                str(event["id"]),
                "POST",
                f"/calendars/{_q(calendar_id)}/events",
                event,
            )
            for event in chunk
        ]
        results = _batch_api(account, calls, transport)
        for event in chunk:
            status, body = results.get(str(event["id"]), (0, {}))
            if status not in (200, 201):
                raise GoogleCalendarError(_error_text(body) or "Couldn't add a Google Calendar event.")
    return len(events)


def _delete_events(
    account: dict[str, Any],
    calendar_id: str,
    event_ids: list[str],
    transport: Transport | None,
) -> None:
    for chunk in _chunks(event_ids, 40):
        calls = [
            (
                f"del-{event_id}",
                "DELETE",
                f"/calendars/{_q(calendar_id)}/events/{_q(event_id)}",
                None,
            )
            for event_id in chunk
        ]
        results = _batch_api(account, calls, transport)
        for event_id in chunk:
            status, body = results.get(f"del-{event_id}", (0, {}))
            if status not in (200, 204, 404, 410):
                raise GoogleCalendarError(
                    _error_text(body) or "Couldn't remove an old Google Calendar event."
                )


def _list_event_ids(
    account: dict[str, Any], calendar_id: str, transport: Transport | None
) -> list[str]:
    ids: list[str] = []
    page = ""
    while True:
        query = "maxResults=250&singleEvents=true&privateExtendedProperty=whiteboard%3D1"
        if page:
            query += "&pageToken=" + _q(page)
        status, body = _api(
            "GET",
            f"/calendars/{_q(calendar_id)}/events?{query}",
            account,
            transport=transport,
        )
        if status != 200 or not isinstance(body, dict):
            raise GoogleCalendarError(_error_text(body) or "Couldn't list Google Calendar events.")
        for item in body.get("items") or []:
            if isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
        page = str(body.get("nextPageToken") or "")
        if not page:
            return ids


def _batch_api(
    account: dict[str, Any],
    calls: list[tuple[str, str, str, dict[str, Any] | None]],
    transport: Transport | None,
) -> dict[str, tuple[int, Any]]:
    if not calls:
        return {}
    boundary = "batch_" + secrets.token_hex(8)
    chunks: list[str] = []
    for content_id, method, path, payload in calls:
        head = [
            f"--{boundary}",
            "Content-Type: application/http",
            f"Content-ID: <{content_id}>",
            "",
            f"{method} /calendar/v3{path} HTTP/1.1",
        ]
        if payload is None:
            head.append("")
        else:
            head.extend(["Content-Type: application/json; charset=utf-8", "", json.dumps(payload)])
        chunks.append("\r\n".join(head))
    body = ("\r\n".join(chunks) + f"\r\n--{boundary}--").encode("utf-8")
    status, raw = _request(
        "POST",
        "https://www.googleapis.com/batch/calendar/v3",
        headers={
            "Authorization": f"Bearer {account.get('access_token') or ''}",
            "Content-Type": f"multipart/mixed; boundary={boundary}",
        },
        payload=body,
        transport=transport,
        parse_json=False,
    )
    if status != 200 or not isinstance(raw, str):
        raise GoogleCalendarError(_error_text(raw) or "Google Calendar batch update failed.")
    return _parse_batch(raw)


def _parse_batch(raw: str) -> dict[str, tuple[int, Any]]:
    marker = ""
    for line in raw.splitlines():
        if line.startswith("--") and not line.endswith("--"):
            marker = line.strip()
            break
    if not marker:
        raise GoogleCalendarError("Google Calendar returned an unreadable update.")
    found: dict[str, tuple[int, Any]] = {}
    for part in raw.split(marker):
        status_match = re.search(r"HTTP/1\.[01] (\d+)", part)
        if not status_match:
            continue
        id_match = re.search(r"Content-ID:\s*<?([^>\r\n]+)>?", part, re.I)
        content_id = id_match.group(1).strip() if id_match else ""
        if content_id.lower().startswith("response-"):
            content_id = content_id[9:]
        body: Any = {}
        json_match = re.search(r"(\{.*\})", part, re.S)
        if json_match:
            try:
                body = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                body = {}
        found[content_id] = (int(status_match.group(1)), body)
    return found


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _email(access_token: str) -> str:
    status, body = _request(
        "GET",
        USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        payload=None,
    )
    if status == 200 and isinstance(body, dict):
        return str(body.get("email") or "")
    return ""


def _token_request(form: dict[str, str], *, transport: Transport | None = None) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(form).encode("utf-8")
    status, body = _request(
        "POST",
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        payload=encoded,
        transport=transport,
    )
    if status != 200 or not isinstance(body, dict):
        raise GoogleCalendarError(_error_text(body) or "Google sign-in failed.")
    return body


def _api(
    method: str,
    path: str,
    account: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
    transport: Transport | None = None,
) -> tuple[int, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {account.get('access_token') or ''}",
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    return _request(method, API_ROOT + path, headers=headers, payload=data, transport=transport)


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None,
    payload: bytes | None,
    transport: Transport | None = None,
    parse_json: bool = True,
) -> tuple[int, Any]:
    if transport is not None:
        return transport(method, url, headers, payload)
    request = urllib.request.Request(url, data=payload, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        raise GoogleCalendarError("Couldn't reach Google. Check the network and try again.") from exc
    if not parse_json:
        return status, raw
    if not raw:
        return status, {}
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, {"error": {"message": raw[:240]}}


def _error_text(body: Any) -> str:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("status") or "")
        if isinstance(error, str):
            return str(body.get("error_description") or error)
    return ""


def _clean_account(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = {
        "client_id": str(data.get("client_id") or ""),
        "client_secret": str(data.get("client_secret") or ""),
        "refresh_token": str(data.get("refresh_token") or ""),
        "access_token": str(data.get("access_token") or ""),
        "email": str(data.get("email") or ""),
        "calendar_id": str(data.get("calendar_id") or ""),
    }
    try:
        cleaned["expires_at"] = float(data.get("expires_at") or 0)
    except (TypeError, ValueError):
        cleaned["expires_at"] = 0
    return cleaned


def _code_challenge(verifier: str) -> str:
    import base64

    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _q(value: str) -> str:
    return urllib.parse.quote(value, safe="")
