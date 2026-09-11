"""Playwright login and a long-lived authenticated browser session."""

from __future__ import annotations

import concurrent.futures
import json
import queue
import sys
import threading
import time
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:  # Demo UI can run without Playwright installed.
    PlaywrightTimeoutError = TimeoutError  # type: ignore[misc, assignment]
    sync_playwright = None  # type: ignore[assignment]

DEFAULT_BASE_URL = "https://shs.blackboardchina.cn"
LOGIN_WAIT_SEC = 90
FALLBACK_BASE_URLS = (
    "https://shs.blackboardchina.cn",
    "https://shs.blackboard.cn",
)


class SessionError(RuntimeError):
    pass


class AuthExpiredError(SessionError):
    """The Blackboard session is no longer authenticated."""


SESSION_EXPIRED_MESSAGE = "Your Blackboard session expired. Sign in again to refresh."


def is_auth_error(message: str | BaseException | None) -> bool:
    status = getattr(message, "status", None)
    if status in (401, 403):
        return True
    text = str(message or "").lower()
    return any(
        token in text
        for token in ("http 401", "http 403", "unauthorized", "session expired")
    )


def url_looks_logged_in(url: str) -> bool:
    url = url.lower()
    if _url_looks_like_auth(url):
        return False
    return any(
        part in url
        for part in (
            "/ultra",
            "/webapps/portal",
            "/webapps/bb-social-learning",
        )
    )


def _url_looks_like_auth(url: str) -> bool:
    url = url.lower()
    return any(part in url for part in ("/webapps/login", "/auth-provider", "/cas/", "/sso"))


def looks_logged_in(page, *, check_page_text: bool = True) -> bool:
    url = page.url.lower()
    if _url_looks_like_auth(url):
        return False
    if url_looks_logged_in(url):
        return True
    if not check_page_text:
        return False
    try:
        if page.get_by_text("Sign Out", exact=False).count() > 0:
            return True
        if page.get_by_text("退出", exact=False).count() > 0:
            return True
        if page.get_by_text("Logout", exact=False).count() > 0:
            return True
    except Exception:
        pass
    return False


def same_site(base_url: str, target: str) -> bool:
    host = urlparse(target).hostname or ""
    allowed = urlparse(base_url).hostname or ""
    if not host or not allowed:
        return False
    return host == allowed or host.endswith("." + allowed)


def resolve_url(base_url: str, target: str) -> str:
    if target.startswith(("http://", "https://")):
        return target
    return urljoin(base_url.rstrip("/") + "/", target.lstrip("/"))


def candidate_base_urls(base_url: str) -> list[str]:
    ordered: list[str] = []
    host = (urlparse(base_url).hostname or "").lower()
    if host == "shs.blackboard.cn":
        ordered.append("https://shs.blackboardchina.cn")
    for url in (base_url.rstrip("/"), *FALLBACK_BASE_URLS):
        if url and url not in ordered:
            ordered.append(url)
    return ordered


def _dismiss_consent(page) -> None:
    button = page.locator("#agree_button")
    try:
        if button.count() == 0:
            button = page.locator("button:has-text('确定'), button:has-text('OK')")
        if button.count() == 0:
            return
        button.first.click(timeout=4_000, force=True)
        page.wait_for_timeout(300)
        overlay = page.locator(".lb-wrapper, [role='dialog']")
        if overlay.count():
            try:
                overlay.first.wait_for(state="hidden", timeout=4_000)
            except Exception:
                pass
    except Exception:
        return


def _visible_login_error(page) -> str:
    selectors = (
        "#loginErrorMessage",
        ".loginError",
        "#loginForm .error",
        "[data-automation-id='login-error']",
    )
    for selector in selectors:
        loc = page.locator(selector)
        if loc.count() == 0:
            continue
        try:
            text = " ".join((loc.first.inner_text(timeout=500) or "").split())
        except Exception:
            text = ""
        if text:
            return text
    try:
        body = " ".join((page.inner_text("body") or "").split())
    except Exception:
        body = ""
    lowered = body.lower()
    if any(
        marker in body
        for marker in ("用户名或密码", "密码不正确", "无法登录", "登录失败")
    ) or any(
        marker in lowered
        for marker in ("invalid username", "invalid password", "login failed")
    ):
        return "Username or password was not accepted."
    return ""


class BlackboardSession:
    """Runs Playwright on a worker thread so the desktop UI stays responsive."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        headless: bool = True,
        storage_state: dict[str, Any] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_progress: Callable[[str, float | None], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self._storage_state = storage_state
        self.on_status = on_status
        self.on_progress = on_progress
        self.needs_manual_login = False
        self.logged_in = False
        self._jobs: queue.Queue = queue.Queue()
        self._started = threading.Event()
        self._start_error: Exception | None = None
        self._thread = threading.Thread(target=self._loop, daemon=True, name="bb-playwright")
        self._closed = False
        self._page = None
        self._context = None
        self._browser = None

    @property
    def is_open(self) -> bool:
        return not self._closed and self._thread.is_alive()

    def _tell(self, message: str, progress: float | None = None) -> None:
        if self.on_progress:
            try:
                self.on_progress(message, progress)
            except Exception:
                pass
        if self.on_status:
            try:
                self.on_status(message)
            except Exception:
                pass

    def start(self) -> None:
        if self._thread.is_alive():
            return
        self._thread.start()
        if not self._started.wait(timeout=32):
            raise SessionError("Timed out starting the browser. Is Chrome or Edge installed?")
        if self._start_error:
            raise SessionError(str(self._start_error)) from self._start_error

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._jobs.put(None)
        self._thread.join(timeout=8)
        self.logged_in = False

    def call(self, fn: Callable[[], Any], timeout: float = 120) -> Any:
        if self._closed:
            raise SessionError("The browser session is closed.")
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._jobs.put((fn, future))
        return future.result(timeout=timeout)

    def _loop(self) -> None:
        if sync_playwright is None:
            self._start_error = SessionError(
                "Playwright is not installed. Run: pip install playwright && playwright install chromium"
            )
            self._started.set()
            return
        try:
            with sync_playwright() as playwright:
                self._browser = _launch_chromium(playwright, headless=self.headless)
                ctx_kwargs: dict[str, Any] = {"ignore_https_errors": True}
                if self._storage_state is not None:
                    ctx_kwargs["storage_state"] = self._storage_state
                self._context = self._browser.new_context(**ctx_kwargs)
                self._page = self._context.new_page()
                self._started.set()
                while True:
                    item = self._jobs.get()
                    if item is None:
                        break
                    fn, future = item
                    try:
                        future.set_result(fn())
                    except Exception as exc:
                        future.set_exception(exc)
                self._context.close()
                self._browser.close()
        except Exception as exc:
            self._start_error = exc
            self._started.set()

    def wait_for_interactive_login(self, timeout_sec: float = LOGIN_WAIT_SEC) -> bool:
        """Open Blackboard in a visible window and wait until the user finishes sign-in."""

        def work() -> bool:
            self.needs_manual_login = True
            self._page.set_default_timeout(20_000)
            self._tell("Blackboard opened. Sign in in that window.")
            self._page.goto(self.base_url, wait_until="domcontentloaded", timeout=30_000)
            try:
                self._page.bring_to_front()
            except Exception:
                pass
            deadline = time.monotonic() + timeout_sec
            next_api_check = 0.0
            while time.monotonic() < deadline and not self._closed:
                try:
                    url = self._page.url
                except Exception:
                    return False
                if url_looks_logged_in(url):
                    self._page.wait_for_timeout(600)
                    try:
                        url = self._page.url
                    except Exception:
                        return False
                    if url_looks_logged_in(url) or _session_api_ok(self._page, self.base_url):
                        self.logged_in = True
                        self.needs_manual_login = False
                        return True
                if (
                    same_site(self.base_url, url)
                    and not _url_looks_like_auth(url)
                    and time.monotonic() >= next_api_check
                ):
                    next_api_check = time.monotonic() + 2
                    if _session_api_ok(self._page, self.base_url):
                        self.logged_in = True
                        self.needs_manual_login = False
                        return True
                self._page.wait_for_timeout(300)
            return False

        return bool(self.call(work, timeout=timeout_sec + 45))

    def login_with_credentials(
        self, username: str, password: str, timeout_sec: float = LOGIN_WAIT_SEC
    ) -> bool:
        """Fill the Blackboard login form in this (usually headless) browser."""

        user = (username or "").strip()
        secret = password or ""
        if not user or not secret:
            raise SessionError("Username and password are required.")

        def work() -> bool:
            page = self._page
            page.set_default_timeout(20_000)
            self._tell("Opening Blackboard…")
            last_error: Exception | None = None
            opened = False
            for url in candidate_base_urls(self.base_url):
                for _attempt in range(2):
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                        if "chrome-error" in (page.url or "").lower():
                            raise SessionError("Blackboard returned an empty page.")
                        opened = True
                        self.base_url = url.rstrip("/")
                        break
                    except Exception as exc:
                        last_error = exc
                        try:
                            page.goto("about:blank", timeout=5_000)
                        except Exception:
                            pass
                        page.wait_for_timeout(400)
                if opened:
                    break
            if not opened:
                raise SessionError(
                    f"Could not open Blackboard. Check the school URL and network. {last_error or ''}"
                )
            try:
                page.locator("#agree_button").wait_for(state="visible", timeout=5_000)
            except Exception:
                pass
            _dismiss_consent(page)
            if looks_logged_in(page) or _session_api_ok(page, self.base_url):
                self.logged_in = True
                self.needs_manual_login = False
                return True
            user_box = page.locator('input#user_id, input[name="user_id"]')
            pwd_box = page.locator('input#password, input[name="password"]')
            if user_box.count() == 0 or pwd_box.count() == 0:
                if looks_logged_in(page) or _session_api_ok(page, self.base_url):
                    self.logged_in = True
                    self.needs_manual_login = False
                    return True
                raise SessionError("Could not find the Blackboard username and password fields.")
            user_box.first.fill(user)
            pwd_box.first.fill(secret)
            self._tell("Signing in…")
            submit = page.locator('#entry-login, input[name="login"][type="submit"]')
            if submit.count():
                try:
                    submit.first.click(timeout=8_000)
                except Exception:
                    submit.first.click(timeout=5_000, force=True)
            else:
                pwd_box.first.press("Enter")
            deadline = time.monotonic() + timeout_sec
            form_deadline = time.monotonic() + 20
            while time.monotonic() < deadline and not self._closed:
                try:
                    url = page.url
                except Exception:
                    return False
                if looks_logged_in(page) or url_looks_logged_in(url):
                    page.wait_for_timeout(500)
                    try:
                        url = page.url
                    except Exception:
                        return False
                    if looks_logged_in(page) or _session_api_ok(page, self.base_url):
                        self.logged_in = True
                        self.needs_manual_login = False
                        return True
                error = _visible_login_error(page)
                if error:
                    raise SessionError(error)
                if time.monotonic() > form_deadline:
                    still_form = False
                    try:
                        still_form = page.locator('input#password, input[name="password"]').count() > 0
                    except Exception:
                        still_form = False
                    if still_form and not looks_logged_in(page):
                        raise SessionError(
                            "Username or password was not accepted."
                        )
                page.wait_for_timeout(300)
            raise SessionError(
                "Sign-in did not finish. Check username, password, and school URL."
            )

        try:
            return bool(self.call(work, timeout=timeout_sec + 45))
        finally:
            secret = ""

    def storage_state(self) -> dict[str, Any]:
        return dict(self.call(lambda: self._context.storage_state(), timeout=15) or {})

    def prepare_origin(self) -> None:
        """Load Blackboard in this (usually headless) context so in-page fetch works."""

        def work() -> None:
            self._page.set_default_timeout(20_000)
            self._page.goto(
                resolve_url(self.base_url, "/ultra"),
                wait_until="domcontentloaded",
                timeout=25_000,
            )
            self.logged_in = looks_logged_in(self._page) or _session_api_ok(
                self._page, self.base_url
            )

        self.call(work, timeout=35)

    def confirm_login(self) -> bool:
        def work() -> bool:
            self.logged_in = looks_logged_in(self._page) or _session_api_ok(self._page, self.base_url)
            return self.logged_in

        return bool(self.call(work, timeout=15))

    def current_url(self) -> str:
        return str(self.call(lambda: self._page.url, timeout=10))

    def get_json(self, path: str) -> Any:
        def work() -> Any:
            url = resolve_url(self.base_url, path).replace("/.learn/", "/learn/")
            if not same_site(self.base_url, url):
                raise SessionError(f"Refusing to request a different site: {url}")
            try:
                return _in_page_get_json(self._page, url)
            except ApiRequestError as exc:
                if exc.status in (401, 403):
                    self.logged_in = False
                raise

        return self.call(work, timeout=20)

    def crawl_html_links(self, urls: list[str]) -> list[dict[str, str]]:
        """Fetch course pages with the signed-in session and return their links."""

        targets = []
        for raw in urls:
            url = resolve_url(self.base_url, raw)
            if same_site(self.base_url, url):
                targets.append(url)
        if not targets:
            return []

        def work() -> list[dict[str, str]]:
            return _in_page_collect_links(self._page, targets)

        return list(self.call(work, timeout=min(120, 15 + 6 * len(targets))) or [])

    def check_submission_pages(self, urls: list[str]) -> list[dict[str, Any]]:
        """Open assignment pages and report whether each already has a student attempt."""

        targets = []
        for raw in urls:
            url = resolve_url(self.base_url, raw)
            if same_site(self.base_url, url):
                targets.append(url)
        if not targets:
            return []

        def work() -> list[dict[str, Any]]:
            return _in_page_check_submissions(self._page, targets)

        return list(self.call(work, timeout=min(180, 20 + 6 * len(targets))) or [])

    def harvest_learn_json(
        self, paths: tuple[str, ...] | None = None
    ) -> list[tuple[str, Any]]:
        """Load Ultra pages and collect the JSON those pages already request."""

        pages = paths or ("/ultra/course",)

        def work() -> list[tuple[str, Any]]:
            captured: list[tuple[str, Any]] = []

            def on_response(response) -> None:
                try:
                    url = response.url
                    if "/learn/api/" not in url or response.status != 200:
                        return
                    payload = response.json()
                    captured.append((url, payload))
                except Exception:
                    return

            self._page.on("response", on_response)
            for path in pages:
                try:
                    self._page.goto(
                        resolve_url(self.base_url, path),
                        wait_until="domcontentloaded",
                        timeout=15_000,
                    )
                    self._page.wait_for_timeout(800)
                except Exception:
                    continue
            try:
                self._page.remove_listener("response", on_response)
            except Exception:
                pass
            return captured

        return self.call(work, timeout=35)

    def get_bytes(self, path: str, timeout: float = 90) -> bytes:
        """Download a same-site URL with the signed-in session. Does not crawl."""
        url = resolve_url(self.base_url, path)
        if not same_site(self.base_url, url):
            raise SessionError(f"Refusing to request a different site: {url}")

        def work() -> bytes:
            response = self._context.request.get(url, timeout=int(timeout * 1000))
            if response.status >= 400:
                raise SessionError(f"HTTP {response.status} for {url}")
            return bytes(response.body())

        return self.call(work, timeout=timeout + 15)

    def open_url(self, target: str) -> None:
        url = resolve_url(self.base_url, target)

        def work() -> None:
            if not same_site(self.base_url, url):
                raise SessionError(f"Refusing to open a different site: {url}")
            self._page.goto(url, wait_until="domcontentloaded", timeout=45_000)

        self.call(work, timeout=50)

    def page_title(self) -> str:
        return str(self.call(lambda: self._page.title(), timeout=10))

    def page_text(self) -> str:
        return str(self.call(lambda: self._page.inner_text("body"), timeout=20))

    def page_html(self) -> str:
        return str(self.call(lambda: self._page.content(), timeout=20))


def _session_api_ok(page, base_url: str) -> bool:
    try:
        if not same_site(base_url, page.url):
            return False
        me = _in_page_get_json(page, resolve_url(base_url, "/learn/api/v1/users/me"))
        return isinstance(me, dict) and bool(me.get("id") or me.get("userName"))
    except Exception:
        return False


def _chromium_launch_attempts(*, headless: bool) -> tuple[dict[str, Any], ...]:
    bundled = {"headless": headless, "timeout": 12_000}
    edge = {"headless": headless, "channel": "msedge", "timeout": 12_000}
    chrome = {"headless": headless, "channel": "chrome", "timeout": 12_000}
    if getattr(sys, "frozen", False):
        return (bundled, edge, chrome)
    return (edge, chrome, {"headless": headless, "timeout": 6_000})


def _launch_chromium(playwright, *, headless: bool = True):
    errors: list[str] = []
    for kwargs in _chromium_launch_attempts(headless=headless):
        try:
            return playwright.chromium.launch(**kwargs)
        except Exception as exc:
            errors.append(str(exc))
    if getattr(sys, "frozen", False):
        raise SessionError(
            "Could not start the bundled browser. Last error: "
            + (errors[-1] if errors else "unknown")
        )
    raise SessionError(
        "Could not start Chrome or Edge. Install one of those browsers, or run "
        "`python -m playwright install chromium`. Last error: "
        + (errors[-1] if errors else "unknown")
    )


def _in_page_get_json(page, url: str) -> Any:
    # Playwright 1.62 evaluate() does not accept a timeout= argument.
    page.set_default_timeout(15_000)
    result = page.evaluate(
        """async (url) => {
            const headers = {
                Accept: "application/json",
                "X-Requested-With": "XMLHttpRequest",
            };
            for (const part of document.cookie.split(";")) {
                const trimmed = part.trim();
                const eq = trimmed.indexOf("=");
                if (eq < 0) continue;
                const key = trimmed.slice(0, eq).toLowerCase();
                const value = trimmed.slice(eq + 1);
                if (key.includes("xsrf")) {
                    headers["X-Blackboard-XSRF"] = value;
                }
            }
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 8000);
            try {
                const res = await fetch(url, {
                    method: "GET",
                    credentials: "include",
                    headers,
                    signal: controller.signal,
                });
                return { status: res.status, text: await res.text() };
            } catch (err) {
                return { status: 0, text: "", error: String(err) };
            } finally {
                clearTimeout(timer);
            }
        }""",
        url,
    )
    if not result:
        raise ApiRequestError(0, url, "Empty evaluate result")
    if result.get("error") and not result.get("status"):
        raise ApiRequestError(0, url, str(result.get("error")))
    status = int(result.get("status") or 0)
    text = result.get("text") or ""
    if status >= 400:
        raise ApiRequestError(status, url)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ApiRequestError(status, url, "Response was not JSON") from exc


def _in_page_collect_links(page, urls: list[str]) -> list[dict[str, str]]:
    page.set_default_timeout(20_000)
    result = page.evaluate(
        """async (urls) => {
            const headers = {
                Accept: "text/html,application/xhtml+xml",
                "X-Requested-With": "XMLHttpRequest",
            };
            for (const part of document.cookie.split(";")) {
                const trimmed = part.trim();
                const eq = trimmed.indexOf("=");
                if (eq < 0) continue;
                const key = trimmed.slice(0, eq).toLowerCase();
                const value = trimmed.slice(eq + 1);
                if (key.includes("xsrf")) {
                    headers["X-Blackboard-XSRF"] = value;
                }
            }
            const found = [];
            for (const url of urls) {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 6000);
                try {
                    const res = await fetch(url, {
                        method: "GET",
                        credentials: "include",
                        headers,
                        signal: controller.signal,
                    });
                    const html = await res.text();
                    const re = /<a\\s+[^>]*href=["']([^"']+)["'][^>]*>([\\s\\S]*?)<\\/a>/gi;
                    let match;
                    while ((match = re.exec(html))) {
                        found.push({
                            href: match[1],
                            text: match[2].replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim(),
                            source: url,
                        });
                    }
                } catch (err) {
                    continue;
                } finally {
                    clearTimeout(timer);
                }
            }
            return found;
        }""",
        urls,
    )
    return [row for row in (result or []) if isinstance(row, dict) and row.get("href")]


def _in_page_check_submissions(page, urls: list[str]) -> list[dict[str, Any]]:
    page.set_default_timeout(20_000)
    result = page.evaluate(
        """async (urls) => {
            const headers = {
                Accept: "text/html,application/xhtml+xml",
                "X-Requested-With": "XMLHttpRequest",
            };
            for (const part of document.cookie.split(";")) {
                const trimmed = part.trim();
                const eq = trimmed.indexOf("=");
                if (eq < 0) continue;
                const key = trimmed.slice(0, eq).toLowerCase();
                const value = trimmed.slice(eq + 1);
                if (key.includes("xsrf")) {
                    headers["X-Blackboard-XSRF"] = value;
                }
            }
            const titleFrom = (html) => {
                const match = html.match(/id=["']pageTitleText["'][^>]*>([\\s\\S]*?)<\\/span>/i);
                return match ? match[1].replace(/<[^>]+>/g, " ").replace(/\\s+/g, " ").trim() : "";
            };
            const submitted = (html, title) => {
                if (/复查提交历史记录|复查测试提交|复查测试结果|查看提交收据/.test(title)) return true;
                if (/review submission history|review test submission|review test results|submission receipt/i.test(title)) return true;
                if (/id=["']currentAttempt_attemptFile_/.test(html)) return true;
                if (/\\/webapps\\/assignment\\/download\\?[^"' ]*attempt_id=_/.test(html)) return true;
                if (/id=["']currentAttempt_submissionList["']/.test(html) && /attachment/.test(html)) return true;
                return false;
            };
            const found = [];
            for (const url of urls) {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 6000);
                try {
                    const res = await fetch(url, {
                        method: "GET",
                        credentials: "include",
                        headers,
                        signal: controller.signal,
                    });
                    const html = await res.text();
                    const title = titleFrom(html);
                    found.push({ url, title, submitted: submitted(html, title) });
                } catch (err) {
                    found.push({ url, title: "", submitted: false });
                } finally {
                    clearTimeout(timer);
                }
            }
            return found;
        }""",
        urls,
    )
    return [row for row in (result or []) if isinstance(row, dict)]


class ApiRequestError(Exception):
    def __init__(self, status: int, path: str, detail: str = "") -> None:
        self.status = status
        self.path = path
        extra = f" ({detail})" if detail else ""
        super().__init__(f"HTTP {status} for {path}{extra}")
