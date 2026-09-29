"""
CLI helper: sign in with your own account and inspect a data snapshot.

Use only with your own account, and only in ways your school allows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from blackboard.api import fetch_snapshot
from blackboard.auth import (
    DEFAULT_BASE_URL,
    BlackboardSession,
    resolve_url,
    same_site,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sign in to your Blackboard account and print a JSON snapshot."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    session = BlackboardSession(base_url, headless=False)
    session.start()
    print("Sign in in the Blackboard window. This script continues after login.")
    try:
        if not session.wait_for_interactive_login():
            print("Sign-in was not finished.")
            return 1
        state = session.storage_state()
        session.close()
        session = BlackboardSession(base_url, headless=True, storage_state=state)
        session.start()
        session.prepare_origin()
        snapshot = fetch_snapshot(session)
        print(json.dumps(snapshot.to_dict(), indent=2, default=str))
        _interactive_loop(session, base_url)
    finally:
        session.close()
    return 0


def _interactive_loop(session: BlackboardSession, base_url: str) -> None:
    print(
        "\nCommands:\n"
        "  <path or url>     open a page\n"
        "  text              print visible text\n"
        "  save [file.html]  save the current page HTML\n"
        "  quit              close the browser\n"
    )
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        command, *rest = raw.split(maxsplit=1)
        lower = command.lower()
        if lower in {"quit", "exit"}:
            break
        if lower == "text":
            print(f"URL:   {session.current_url()}")
            print(f"Title: {session.page_title()}")
            preview = " ".join(session.page_text().split())
            print(preview[:800] + ("..." if len(preview) > 800 else ""))
            continue
        if lower == "save":
            dest = Path(rest[0]) if rest else Path("blackboard_page.html")
            dest.write_text(session.page_html(), encoding="utf-8")
            print(f"Saved HTML to {dest.resolve()}")
            continue
        target = resolve_url(base_url, raw)
        if not same_site(base_url, target):
            print(f"Refusing to open a different site: {target}")
            continue
        try:
            session.open_url(target)
            print(f"URL:   {session.current_url()}")
            print(f"Title: {session.page_title()}")
        except Exception as exc:
            print(exc)


if __name__ == "__main__":
    sys.exit(main())
