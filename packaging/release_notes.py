"""Read CHANGELOG.md for a version and format GitHub release notes."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
BRANDING = ROOT / "app" / "branding.py"
HEADING = re.compile(r"^## \[([^\]]+)\](?:\s*-\s*\S+)?\s*$", re.MULTILINE)
APP_VERSION_RE = re.compile(r'^APP_VERSION\s*=\s*"([^"]+)"', re.MULTILINE)
SECTION_HEADINGS = ("Added features", "Bugfixes", "Other changes")
BROKEN_RELEASES = {
    "0.1.0": "This release is known not to work. The app closes as soon as you open it, and the Mac file does not run on Intel computers. Please use 0.1.3 or later.",
    "0.1.1": "This release is known not to work. The app closes as soon as you open it. Please use 0.1.3 or later.",
    "0.1.2": "This release is known not to work. The Windows app closes as soon as you open it, and Mac installers were not included. Please use 0.1.3 or later.",
}
REQUIRED_ASSETS = (
    "WhiteBoard-{version}-Setup.exe",
    "WhiteBoard-{version}-macOS-AppleSilicon.dmg",
    "WhiteBoard-{version}-macOS-Intel.dmg",
)


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
        missing = [
            heading
            for heading in SECTION_HEADINGS
            if not re.search(rf"^### {re.escape(heading)}\s*$", body, re.MULTILINE)
        ]
        if missing:
            raise SystemExit(
                "CHANGELOG.md for "
                f"{version} must include these headings: {', '.join(SECTION_HEADINGS)}. "
                f"Missing: {', '.join(missing)}."
            )
        return body
    raise SystemExit(
        f"CHANGELOG.md is missing '## [{version}]'. "
        "Add a summarized list of major changes from the previous release before tagging."
    )


def github_title(version: str) -> str:
    if version in BROKEN_RELEASES:
        return f"WhiteBoard {version} (known not to work)"
    return f"WhiteBoard {version}"


def github_notes(version: str) -> str:
    changes = changelog_body(version)
    warning = ""
    if version in BROKEN_RELEASES:
        warning = f"**Known not to work.** {BROKEN_RELEASES[version]}\n\n"
    return f"""## {github_title(version)}

{warning}{changes}

### Downloads
- **Windows:** `WhiteBoard-{version}-Setup.exe`
- **macOS Apple Silicon (M1/M2/M3/M4):** `WhiteBoard-{version}-macOS-AppleSilicon.dmg`
- **macOS Intel:** `WhiteBoard-{version}-macOS-Intel.dmg`
- **Source:** GitHub attaches a source code zip to this release automatically.

Open the matching `.dmg` and drag WhiteBoard into Applications.

Sign in with your own school Blackboard account. Course data stays on Blackboard.
"""


def required_asset_names(version: str) -> tuple[str, ...]:
    return tuple(name.format(version=version) for name in REQUIRED_ASSETS)


def verify_release_assets(folder: Path, version: str) -> None:
    names = {path.name for path in folder.iterdir() if path.is_file()}
    missing = [name for name in required_asset_names(version) if name not in names]
    if missing:
        raise SystemExit(
            "GitHub release is missing installer(s): "
            + ", ".join(missing)
            + ". Do not publish until Windows, Intel Mac, and Apple Silicon Mac files are all present."
        )


def sync_broken_releases() -> None:
    for version, reason in BROKEN_RELEASES.items():
        tag = f"v{version}"
        view = subprocess.run(
            ["gh", "release", "view", tag],
            capture_output=True,
            text=True,
        )
        if view.returncode != 0:
            print(f"Skipping {tag}: no GitHub release")
            continue
        notes_path = Path(tempfile.gettempdir()) / f"whiteboard-{version}-broken-notes.md"
        notes_path.write_text(github_notes(version), encoding="utf-8")
        subprocess.check_call(
            [
                "gh",
                "release",
                "edit",
                tag,
                "--title",
                github_title(version),
                "--notes-file",
                str(notes_path),
            ]
        )
        print(f"Marked {tag} as known not to work")
        _ = reason


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
    parser.add_argument(
        "--verify-assets",
        metavar="DIR",
        help="Fail unless DIR contains Windows and both macOS installers.",
    )
    parser.add_argument(
        "--sync-broken-releases",
        action="store_true",
        help="Update GitHub titles/notes for versions listed as known not to work.",
    )
    args = parser.parse_args(argv)

    if args.sync_broken_releases:
        sync_broken_releases()
        return 0

    version = args.version or app_version()
    body = changelog_body(version)
    if args.verify_assets:
        verify_release_assets(Path(args.verify_assets), version)
        print(f"Found Windows and both macOS installers for {version}")
        return 0
    if args.check:
        print(f"CHANGELOG.md has notes for {version}")
        return 0
    print(github_notes(version) if args.github else body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
