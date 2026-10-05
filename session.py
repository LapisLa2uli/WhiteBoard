"""Blackboard session that runs inside WhiteBoard's hidden WebView2 view.

The signed-in page fetches Learn JSON with the browser cookies. No Playwright.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import urlparse

from blackboard.auth import ApiRequestError, SessionError, resolve_url, same_site

import host

_LINK_RE = re.compile(
    r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")

_FETCH_JS = r"""
(() => {
  const key = __KEY__;
  window[key] = null;
  const urls = __URLS__;
  const accept = __ACCEPT__;
  const headers = { Accept: accept, "X-Requested-With": "XMLHttpRequest" };
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    const keyName = trimmed.slice(0, eq).toLowerCase();
    if (keyName.includes("xsrf")) headers["X-Blackboard-XSRF"] = trimmed.slice(eq + 1);
  }
  const found = new Array(urls.length);
  const limit = 24;
  let cursor = 0;
  async function run() {
    while (cursor < urls.length) {
      const index = cursor++;
      const url = urls[index];
      const controller = new AbortController();
      (window.__wbControllers ||= new Set()).add(controller);
      const timer = setTimeout(() => controller.abort(), 20000);
      try {
        const res = await fetch(url, { method: "GET", credentials: "include", headers, signal: controller.signal });
        const type = (res.headers.get("content-type") || "").toLowerCase();
        const binary = type.startsWith("image/") || type.startsWith("audio/") || type.startsWith("video/")
          || type.includes("octet-stream") || type.includes("pdf") || type.includes("zip");
        let text = "";
        if (!binary) {
          text = await res.text();
          if (text.length > 2000000) text = text.slice(0, 2000000);
        }
        found[index] = { url, status: res.status, text };
      } catch (err) {
        found[index] = { url, status: 0, text: "", error: String(err) };
      } finally {
        clearTimeout(timer);
        window.__wbControllers.delete(controller);
      }
    }
  }
  const workers = [];
  for (let n = 0; n < Math.min(limit, Math.max(urls.length, 1)); n++) workers.push(run());
  Promise.all(workers).then(() => { window[key] = found; }).catch((err) => {
    window[key] = { error: String(err) };
  });
  return "started";
})()
"""


_BYTES_JS = r"""
(() => {
  const key = __KEY__;
  const url = __URL__;
  window[key] = null;
  const headers = { "X-Requested-With": "XMLHttpRequest" };
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    const keyName = trimmed.slice(0, eq).toLowerCase();
    if (keyName.includes("xsrf")) headers["X-Blackboard-XSRF"] = trimmed.slice(eq + 1);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  fetch(url, { method: "GET", credentials: "include", headers, signal: controller.signal })
    .then(async (res) => {
      const bytes = new Uint8Array(await res.arrayBuffer());
      let binary = "";
      const size = 0x2000;
      for (let index = 0; index < bytes.length; index += size) {
        binary += String.fromCharCode.apply(null, bytes.subarray(index, Math.min(index + size, bytes.length)));
      }
      window[key] = { status: res.status, b64: btoa(binary) };
    })
    .catch((err) => { window[key] = { status: 0, b64: "", error: String(err) }; })
    .finally(() => clearTimeout(timer));
  return "started";
})()
"""


class WebSession:
    """Enough of BlackboardSession for fetch_snapshot and course-file indexing."""

    def __init__(self, base_url: str, on_progress=None) -> None:
        from accounts import school_origin
        self.base_url = school_origin(base_url)
        self.user = {}
        self.on_progress = on_progress
        self.logged_in = False
        self.cancel_event = None

    def _check_cancelled(self):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise SessionError("Refresh cancelled.")

    def abort(self):
        try:
            host.eval_js("(window.__wbControllers || []).forEach(c => c.abort())", timeout=3)
        except Exception:
            pass

    def _tell(self, message: str, progress: float | None = None) -> None:
        self._check_cancelled()
        host.set_title(f"WhiteBoard — {message}")
        if self.on_progress:
            self.on_progress(message, progress)

    def prepare(self) -> None:
        self._tell("Preparing Blackboard…", 0.03)
        host.wait_browser()
        self.navigate(self.base_url)

    def navigate(self, target: str) -> str:
        url = resolve_url(self.base_url, target)
        self._tell("Opening Blackboard…", 0.05)
        host.navigate_bb(url)
        time.sleep(0.8)
        deadline = time.time() + 45
        last = ""
        last_error = ""
        while time.time() < deadline:
            self._check_cancelled()
            try:
                href = host.eval_js("location.href", timeout=15)
            except Exception as exc:
                last_error = str(exc)
                time.sleep(0.5)
                continue
            last = href if isinstance(href, str) else ""
            host_name = urlparse(last).hostname or ""
            if host_name and host_name not in {"127.0.0.1", "localhost"}:
                return last
            time.sleep(0.3)
        detail = last or last_error or "the page did not load"
        raise SessionError(f"Could not open Blackboard ({detail}).")

    def login(self, username: str, password: str) -> None:
        host.wait_browser()
        host.clear_cookies()
        self.prepare()
        self._tell("Waiting for the Blackboard sign-in form…", 0.06)
        # Consent and identity-provider pages remain under the user's control.
        deadline = time.time() + 25
        filled = None
        while time.time() < deadline:
            self._check_cancelled()
            filled = self._submit_login(username, password)
            if isinstance(filled, dict) and filled.get("external"):
                return self.interactive_login(username, prepared=True)
            if isinstance(filled, dict) and filled.get("found"):
                break
            if self._me_ok():
                self._verify_user(username)
                self.logged_in = True
                self._tell("Signed in.", 0.12)
                return
            time.sleep(0.5)
        if not isinstance(filled, dict) or not filled.get("found"):
            href = filled.get("href") if isinstance(filled, dict) else ""
            raise SessionError(
                "Could not find the Blackboard username and password fields."
                + (f" The page is {href}." if href else "")
            )
        self._tell("Signing in…", 0.1)
        deadline = time.time() + 40
        while time.time() < deadline:
            self._check_cancelled()
            if self._me_ok():
                self._verify_user(username)
                self.logged_in = True
                self._tell("Signed in.", 0.12)
                return
            notice = self._login_notice()
            if notice:
                raise SessionError(notice)
            time.sleep(0.6)
        try:
            href = host.eval_js("location.href", timeout=8)
        except Exception:
            href = ""
        raise SessionError(
            "Sign-in did not finish. Check the username, password, and school URL."
            + (f" The browser stopped at {href}." if href else "")
        )

    def interactive_login(self, username, prepared=False):
        if not prepared:
            host.wait_browser()
            host.clear_cookies()
            self.prepare()
        host.show_login()
        self._tell("Complete school sign-in in the browser window…", .08)
        try:
            deadline = time.time() + 180
            while time.time() < deadline:
                self._check_cancelled()
                if self._me_ok():
                    self._verify_user(username)
                    self.logged_in = True
                    return
                time.sleep(1)
            raise SessionError("School sign-in timed out. Try again.")
        finally:
            host.hide_login()

    def _dismiss_consent(self) -> None:
        host.eval_js(
            """(() => {
              const agree = document.querySelector('#agree_button');
              if (agree) { agree.click(); return true; }
              const button = [...document.querySelectorAll('button, input[type="button"], input[type="submit"]')]
                .find((el) => /确定|同意|OK|Accept/i.test(el.innerText || el.value || ''));
              if (button) { button.click(); return true; }
              return false;
            })()""",
            timeout=10,
        )

    def _submit_login(self, username: str, password: str):
        script = (
            "(() => {"
            f"const expectedOrigin = {json.dumps(self.base_url)};"
            "if (location.origin !== expectedOrigin) return {found:false, external:true};"
            f"const userName = {json.dumps(username)};"
            f"const secret = {json.dumps(password)};"
            """
            const user = document.querySelector('input#user_id, input[name="user_id"], input[name="username"]');
            const pass = document.querySelector('input#password, input[name="password"]');
            if (!user || !pass) return { found: false, href: location.href };
            user.focus();
            user.value = userName;
            pass.focus();
            pass.value = secret;
            user.dispatchEvent(new Event('input', { bubbles: true }));
            pass.dispatchEvent(new Event('input', { bubbles: true }));
            const submit = document.querySelector('#entry-login, input[name="login"][type="submit"]');
            if (submit) submit.click();
            else if (pass.form) pass.form.submit();
            return { found: true, href: location.href };
            })()"""
        )
        try:
            return host.eval_js(script, timeout=12)
        except Exception as exc:
            return {"found": False, "href": str(exc)}

    def _login_notice(self) -> str:
        try:
            text = host.eval_js(
                """(() => {
                  const nodes = document.querySelectorAll('#loginErrorMessage, .loginError, #loginForm .error');
                  for (const node of nodes) {
                    const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                    if (text) return text;
                  }
                  return '';
                })()""",
                timeout=8,
            )
        except Exception:
            return ""
        return text if isinstance(text, str) else ""

    def _page_logged_in(self) -> bool:
        try:
            href = host.eval_js("location.href", timeout=8)
        except Exception:
            return False
        if not isinstance(href, str):
            return False
        lower = href.lower()
        if any(part in lower for part in ("/webapps/login", "/auth-provider", "/cas/", "/sso")):
            return False
        return any(part in lower for part in ("/ultra", "/webapps/portal", "/webapps/bb-social-learning"))

    def _me_ok(self) -> bool:
        try:
            me = self.get_json("/learn/api/v1/users/me")
        except Exception:
            return False
        if isinstance(me, dict) and (me.get("id") or me.get("uuid")):
            self.user = me
            return True
        return False

    def _verify_user(self, username):
        actual = str(self.user.get("userName") or self.user.get("username") or "")
        if not actual or actual.casefold() != username.strip().casefold():
            host.clear_cookies()
            raise SessionError("The signed-in account does not match the requested username. Sign in again.")

    def get_bytes(self, path: str) -> bytes:
        import base64

        url = resolve_url(self.base_url, path).replace("/.learn/", "/learn/")
        if not same_site(self.base_url, url):
            raise SessionError(f"Refusing to download a different site: {url}")
        key = "wb" + __import__("secrets").token_hex(4)
        script = _BYTES_JS.replace("__KEY__", json.dumps(key)).replace("__URL__", json.dumps(url))
        host.eval_js(script, timeout=20)
        deadline = time.time() + 70
        value = None
        while time.time() < deadline:
            self._check_cancelled()
            value = host.eval_js(f"window[{json.dumps(key)}]", timeout=25)
            if value is None:
                time.sleep(0.35)
                continue
            host.eval_js(f"window[{json.dumps(key)}] = null", timeout=8)
            break
        if not isinstance(value, dict):
            raise SessionError("Blackboard did not return the file.")
        if value.get("error"):
            raise SessionError(str(value["error"]))
        status = int(value.get("status") or 0)
        if status >= 400 or not status:
            raise SessionError(f"Download failed (HTTP {status}).")
        try:
            data = base64.b64decode(str(value.get("b64") or ""))
        except Exception as exc:
            raise SessionError("Blackboard returned a file that could not be saved.") from exc
        head = data[:80].lstrip().lower()
        if head.startswith(b"<!doctype") or head.startswith(b"<html"):
            raise SessionError("Sign in, then try the download again.")
        return data

    def get_json(self, path: str) -> Any:
        url = resolve_url(self.base_url, path).replace("/.learn/", "/learn/")
        if not same_site(self.base_url, url):
            raise SessionError(f"Refusing to request a different site: {url}")
        row = self._fetch([url])[0]
        status = int(row.get("status") or 0)
        if row.get("error") and not status:
            raise ApiRequestError(0, url, str(row.get("error")))
        if status >= 400:
            raise ApiRequestError(status, url)
        text = row.get("text") or ""
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ApiRequestError(status, url, "Response was not JSON") from exc

    def get_json_many(self, paths: list[str]) -> list[dict[str, Any]]:
        targets = []
        for raw in paths:
            url = resolve_url(self.base_url, raw).replace("/.learn/", "/learn/")
            if same_site(self.base_url, url):
                targets.append(url)
        parsed: list[dict[str, Any]] = []
        for row in self._fetch(targets):
            text = row.get("text") or ""
            data = None
            if text:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = None
            parsed.append(
                {"url": row.get("url") or "", "status": int(row.get("status") or 0), "data": data}
            )
        return parsed

    def get_html_documents(self, urls: list[str]) -> list[dict[str, Any]]:
        targets = [resolve_url(self.base_url, raw) for raw in urls if same_site(self.base_url, resolve_url(self.base_url, raw))]
        documents = []
        for row in self._fetch(targets, accept="text/html,application/xhtml+xml"):
            documents.append(
                {
                    "url": row.get("url") or "",
                    "status": int(row.get("status") or 0),
                    "html": row.get("text") or "",
                }
            )
        return documents

    def read_mygrades_pages(self, urls: list[str]) -> list[dict[str, Any]]:
        return [{"url": resolve_url(self.base_url, raw), "rows": [], "html": ""} for raw in urls]

    def check_submission_pages(self, urls: list[str]) -> list[dict[str, Any]]:
        rows = []
        for document in self.get_html_documents(urls):
            html = document.get("html") or ""
            title = ""
            match = re.search(r'id=["\']pageTitleText["\'][^>]*>(.*?)</span>', html, re.I | re.S)
            if match:
                title = _TAG_RE.sub(" ", match.group(1))
                title = " ".join(title.split())
            submitted = bool(
                re.search(r"复查提交历史记录|复查测试提交|复查测试结果|查看提交收据", title)
                or re.search(r"review submission history|review test submission|submission receipt", title, re.I)
                or re.search(r'id=["\']currentAttempt_attemptFile_', html)
                or re.search(r"/webapps/assignment/download\?[^\"' ]*attempt_id=_", html)
            )
            rows.append({"url": document.get("url") or "", "title": title, "submitted": submitted})
        return rows

    def crawl_html_links(self, urls: list[str]) -> list[dict[str, str]]:
        found: list[dict[str, str]] = []
        for document in self.get_html_documents(urls):
            html = document.get("html") or ""
            source = document.get("url") or ""
            for match in _LINK_RE.finditer(html):
                text = " ".join(_TAG_RE.sub(" ", match.group(2)).split())
                found.append({"href": match.group(1), "text": text, "source": source})
        return found

    def harvest_learn_json(self, paths: tuple[str, ...] | None = None) -> list[tuple[str, Any]]:
        for path in paths or ("/ultra/course",):
            try:
                self.navigate(path)
                time.sleep(0.6)
            except Exception:
                continue
        found: list[tuple[str, Any]] = []
        for path in (
            "/learn/api/v1/users/me",
            "/learn/api/v1/users/me/memberships?expand=course",
            "/learn/api/v1/users/me/courses",
            "/learn/api/v1/calendars/dueDateCalendarItems",
            "/learn/api/v1/users/me/grades",
        ):
            try:
                payload = self.get_json(path)
            except Exception:
                continue
            if payload:
                found.append((resolve_url(self.base_url, path), payload))
        return found

    def _fetch(self, urls: list[str], accept: str = "application/json") -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(urls), 24):
            rows.extend(self._fetch_batch(urls[offset : offset + 24], accept))
        return rows

    def _fetch_batch(self, urls: list[str], accept: str) -> list[dict[str, Any]]:
        self._check_cancelled()
        if not urls:
            return []
        import secrets

        key = "wb" + secrets.token_hex(4)
        script = (
            _FETCH_JS.replace("__KEY__", json.dumps(key))
            .replace("__URLS__", json.dumps(urls))
            .replace("__ACCEPT__", json.dumps(accept))
        )
        host.eval_js(script, timeout=20)
        deadline = time.time() + 36
        while time.time() < deadline:
            self._check_cancelled()
            value = host.eval_js(f"window[{json.dumps(key)}]", timeout=25)
            if value is None:
                time.sleep(0.35)
                continue
            host.eval_js(f"window[{json.dumps(key)}] = null", timeout=8)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
            if isinstance(value, dict) and value.get("error"):
                raise SessionError(str(value["error"]))
            raise SessionError("Blackboard did not return a page result.")
        raise SessionError("Blackboard did not answer.")
