# Changelog

Summarized major changes for each WhiteBoard release, compared with the version before it.
GitHub Releases copy the matching section into the release notes. Add a new `## [x.y.z]` heading
when you bump `APP_VERSION` — packaging fails if that heading is missing.

## [0.1.3] - 2026-09-11

- Packaged Windows and macOS apps now ship the Flet desktop client **and** Playwright Chromium, so a clean machine does not need Chrome, Edge, or a first-launch download.
- Frozen builds start the bundled Chromium first, then fall back to Edge or Chrome if those are installed.
- Release packaging fails if the Flet archive, Playwright driver, or Chromium is missing from the installer tree.
- Installers are larger (Chromium is included). Chrome and Edge remain optional fallbacks.

## [0.1.2] - 2026-09-11

- Fixed Windows launch: the installer now includes the `flet-desktop` Python package, so the app no longer tries to pip-install it at startup and crash.
- Windows setup still publishes if a macOS build fails, so a working Windows installer is not blocked on the Mac jobs.

## [0.1.1] - 2026-09-10

- Separate macOS disk images for **Intel** and **Apple Silicon**. Intel Macs (including Ventura) should use the Intel `.dmg`.
- macOS builds record a minimum system version of 11.0 and check the binary architecture before the disk image is created.

## [0.1.0] - 2026-09-10

- First packaged release: Windows setup (per-user, no administrator), GitHub Actions release workflow, and a macOS disk image.
- Desktop dashboard for a personal Blackboard account: sign-in, courses, assignments, grades, calendar, contents, local ignore / mark-submitted, and shortcuts.
