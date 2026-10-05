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
  const limit = __LIMIT__;
  let cursor = 0;
  async function run() {
    while (cursor < urls.length) {
      const index = cursor++;
      const url = urls[index];
      const controller = new AbortController();
      (window.__wbControllers ||= new Set()).add(controller);
      const timer = setTimeout(() => controller.abort(), 20000);
      try {
        let res;
        for (let attempt = 0; attempt < 3; attempt++) {
          res = await fetch(url, { method: "GET", credentials: "include", headers, signal: controller.signal });
          if (![429, 503].includes(res.status) || attempt === 2) break;
          const retry = res.headers.get("retry-after");
          const seconds = Number(retry) || Math.max(0, (Date.parse(retry) - Date.now()) / 1000) || 2 ** attempt;
          await new Promise(resolve => setTimeout(resolve, Math.min(seconds, 8) * 1000));
        }
        const type = (res.headers.get("content-type") || "").toLowerCase();
        const binary = type.startsWith("image/") || type.startsWith("audio/") || type.startsWith("video/")
          || type.includes("octet-stream") || type.includes("pdf") || type.includes("zip");
        let text = "";
        if (!binary) {
          text = await res.text();
          if (text.length > 16000000) throw new Error("Response exceeds 16 MB; request a smaller page.");
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


_STREAM_JS = r"""
(() => {
  const key = __KEY__, url = __URL__;
  const controller = new AbortController();
  (window.__wbControllers ||= new Set()).add(controller);
  const state = window[key] = {queue: [], done: false, error: "", controller};
  (async () => {
    try {
      const res = await fetch(url, {credentials:"include", signal:controller.signal});
      if (!res.ok) throw new Error(`Download failed (HTTP ${res.status})`);
      if ((res.headers.get("content-type") || "").includes("text/html")) throw new Error("Sign in again before downloading this file.");
      const reader = res.body.getReader();
      while (true) {
        const {value,done} = await reader.read();
        if (done) break;
        for (let pos=0; pos<value.length; pos+=65536) {
          while (state.queue.length >= 4) {
            if (controller.signal.aborted) throw new Error("Download cancelled.");
            await new Promise(r=>setTimeout(r,15));
          }
          const part=value.subarray(pos, pos+65536);
          let binary="";
          for (let i=0;i<part.length;i+=8192) binary+=String.fromCharCode(...part.subarray(i,i+8192));
          state.queue.push(btoa(binary));
        }
      }
    } catch(error) { state.error=String(error); }
    finally { state.done=true; window.__wbControllers.delete(controller); }
  })();
  return true;
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
        # Real-account comparison: 24 completed in 45s versus 52s at 12.
        # _fetch halves this bound if the service reports throttling.
        self.concurrency = 24
        self._responses = {}
        self.network_errors = []
        self.request_warnings = []
        self.failed_file_courses = set()
        self.metrics = {"requests": 0, "cache_hits": 0, "batches": 0}

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

    def iter_bytes(self, path):
        import base64
        import secrets
        url = resolve_url(self.base_url, path).replace("/.learn/", "/learn/")
        if not same_site(self.base_url, url) or urlparse(url).scheme != 'https':
            raise SessionError("Downloads must come from the HTTPS school address.")
        key = 'wb' + secrets.token_hex(8)
        host.eval_js(_STREAM_JS.replace('__KEY__', json.dumps(key)).replace('__URL__', json.dumps(url)))
        deadline = time.monotonic() + 60
        try:
            while True:
                self._check_cancelled()
                value = host.eval_js(f"(() => {{ const s=window[{json.dumps(key)}]; return {{chunks:s.queue.splice(0,4),done:s.done,error:s.error}}; }})()")
                if value.get('error'):
                    raise SessionError(value['error'])
                chunks = value.get('chunks') or []
                for chunk in chunks:
                    deadline = time.monotonic() + 60
                    yield base64.b64decode(chunk, validate=True)
                if value.get('done') and not chunks:
                    break
                if time.monotonic() > deadline:
                    raise SessionError('Download stalled for 60 seconds.')
                if not chunks:
                    time.sleep(.03)
        finally:
            host.eval_js(f"(() => {{ const s=window[{json.dumps(key)}]; if(s)s.controller.abort(); delete window[{json.dumps(key)}]; }})()",timeout=5)

    def download_to(self, path, output):
        for chunk in self.iter_bytes(path):
            output.write(chunk)

    def get_json(self, path: str) -> Any:
        url = resolve_url(self.base_url, path).replace("/.learn/", "/learn/")
        if not same_site(self.base_url, url):
            raise SessionError(f"Refusing to request a different site: {url}")
        row = self._fetch([url])[0]
        status = int(row.get("status") or 0)
        if row.get("error"):
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
                    row["error"] = "Response was not complete JSON"
                    if 200 <= int(row.get("status") or 0) < 300:
                        row["status"] = 0
                        self.request_warnings.append("Invalid JSON response")
            parsed.append(
                {"url": row.get("url") or "", "status": int(row.get("status") or 0), "data": data, "error": row.get("error", "")}
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
        self._check_cancelled()
        pending = list(dict.fromkeys(url for url in urls if (url, accept) not in self._responses))
        self.metrics['cache_hits'] += len(urls) - len(pending)
        found = {}
        offset = 0
        while offset < len(pending):
            batch = pending[offset:offset+self.concurrency]
            offset += len(batch)
            rows = self._fetch_batch(batch, accept)
            self.metrics['batches'] += 1
            self.metrics['requests'] += len(rows)
            for row in rows:
                found[row['url']] = row
                status = int(row.get('status') or 0)
                if 200 <= status < 300 and not row.get('error') and not re.search(r"/users/me(?:[?]|$)", row["url"]):
                    self._responses[(row['url'], accept)] = row
                elif status == 0 or status >= 500 or status == 429:
                    self.request_warnings.append(str(row.get('error') or f'HTTP {status}'))
            if any(int(r.get('status') or 0) in (429,503) for r in rows):
                self.concurrency = max(4, self.concurrency // 2)
        return [self._responses.get((url,accept)) or found.get(url) or {'url':url,'status':0,'error':'No response'} for url in urls]

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
            .replace("__LIMIT__", str(self.concurrency))
        )
        host.eval_js(script, timeout=20)
        deadline = time.time() + 45
        delay = .03
        while time.time() < deadline:
            self._check_cancelled()
            value = host.eval_js(f"window[{json.dumps(key)}]", timeout=25)
            if value is None:
                time.sleep(delay)
                delay = min(.2, delay * 1.4)
                continue
            host.eval_js(f"window[{json.dumps(key)}] = null", timeout=8)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
            if isinstance(value, dict) and value.get("error"):
                raise SessionError(str(value["error"]))
            raise SessionError("Blackboard did not return a page result.")
        raise SessionError("Blackboard did not answer.")
