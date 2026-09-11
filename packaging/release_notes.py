"""Read CHANGELOG.md for a version and format GitHub release notes."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
BRANDING = ROOT / "app" / "branding.py"
HEADING = re.compile(r"^## \[([^\]]+)\](?:\s*-\s*\S+)?\s*$", re.MULTILINE)
APP_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)


def app_version(text: str | None = None) -> str:
    raw = text if text is not None else BRANDING.read_text(encoding="utf-8")
    match = APP_VERSION_RE.search(raw)
    if not match:
        raise SystemExit("Could not read APP_VERSION from app/branding.py")
    return match.group(1)


def changelog_body(version: str, text: str | None = None) -> str:
    raw = text if text is not None else CHANGELOG.read_text(encoding="utf-8")
    matches = list(HEADING.finditer(raw))
    for index, match in enumerate(matches):
        if match.group(1) != version:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        if not body:
            raise SystemExit(
                f"CHANGELOG.md has '## [{version}]' but no summary of changes. "
                "List the major changes from the previous release before packaging."
            )
        return body
    raise SystemExit(
        f"CHANGELOG.md is missing '## [{version}]'. "
        "Add a summarized list of major changes from the previous release before tagging."
    )


def github_notes(version: str) -> str:
    changes = changelog_body(version)
    return f"""## WhiteBoard {version}

### What's new
{changes}

### Downloads
- **Windows:** `WhiteBoard-{version}-Setup.exe` — install or upgrade. Includes the Flet desktop runtime and a bundled Chromium browser. Shortcuts for Desktop and Windows Search keep working.
- **macOS Apple Silicon (M1/M2/M3/M4):** `WhiteBoard-{version}-macOS-AppleSilicon.dmg`
- **macOS Intel:** `WhiteBoard-{version}-macOS-Intel.dmg` — use this on Intel MacBooks, including Ventura.
- **Source:** GitHub attaches a source code zip to this release automatically.

Open the matching `.dmg` and drag WhiteBoard into Applications.

### Notes
Sign in with your own school Blackboard account. Course data stays on Blackboard.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "version",
        nargs="?",
        help="Version to extract, for example 0.1.3. Defaults to APP_VERSION.",
    )
    parser.add_argument(
        "--github",
        action="store_true",
        help="Print full GitHub release notes instead of the changelog body only.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify CHANGELOG.md has a non-empty section for APP_VERSION.",
    )
    args = parser.parse_args(argv)

    version = args.version or app_version()
    body = changelog_body(version)
    if args.check:
        print(f"CHANGELOG.md has notes for {version}")
        return 0
    print(github_notes(version) if args.github else body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
