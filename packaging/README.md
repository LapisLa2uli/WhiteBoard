# Building WhiteBoard 0.4.0

Build natively on Windows x64 and Apple silicon macOS from the same clean commit. Runtime source lives at the repository root; `archive/original` is historical. Release builds are gated, but passing a build does not replace installer acceptance testing.

Use a clean Python 3.12 environment (Windows validation used 3.12.14):

```sh
python -m venv .venv
.venv/bin/python -m pip install -r packaging/requirements-build.txt
```

On Windows, use `.venv\Scripts\python.exe` for both commands after creating the environment. Dependencies are pinned and checked before packaging. Native SDK/compiler versions can still affect the output; checksums identify artifacts, not a claim of byte-for-byte reproducibility.

Supply `authid.txt` locally with the Google **Desktop app** OAuth client ID on the first line and its client configuration secret on the second. Both packages include this public desktop application configuration. Never put user tokens/passwords in it. User credentials are stored separately through DPAPI/Keychain. The file stays ignored by Git.

## Windows

Install Inno Setup 6.7.3 or set `ISCC` to its compiler. WebView2 must be installed for the packaged smoke test.

```powershell
./packaging/build_windows.ps1 -Python .venv/Scripts/python.exe
```

This creates an **unsigned development** installer. `-SkipInstaller` builds just the app. Production builds require a certificate in the current user's Windows certificate store, its SHA-1 thumbprint in `WINDOWS_SIGN_THUMBPRINT`, and Windows SDK `signtool.exe` on PATH or in `SIGNTOOL`:

```powershell
./packaging/build_windows.ps1 -Python .venv/Scripts/python.exe -Release
```

The application is signed before Inno packages it; Inno signs the installer and uninstaller. Signing and verification failures are fatal. Setup uses normal application-close handling rather than force-killing every WhiteBoard process.

## Apple silicon macOS

Use native arm64 Python. The script builds the tracked PNG into an icon, assembles the `.app`, verifies its signature and architecture, runs `--selftest`, and creates a DMG with an Applications shortcut.

```sh
PYTHON=.venv/bin/python bash packaging/build_macos.sh
```

For a release, configure a Developer ID Application identity and a `notarytool` Keychain profile, then set `SIGN_ID`, `NOTARY_PROFILE`, and `WHITEBOARD_RELEASE=1`. Example (replace the identity and profile):

```sh
SIGN_ID='Developer ID Application: Your Name (TEAMID)' \
NOTARY_PROFILE='whiteboard-notary' WHITEBOARD_RELEASE=1 \
PYTHON=.venv/bin/python bash packaging/build_macos.sh
```

Both app and DMG are submitted for notarization and stapled. Any failed signing, verification, stapling, Gatekeeper assessment or native smoke test stops the build. The default ad-hoc development build is not a publicly validated release.

## Validation and outputs

The manual **Build release installers** GitHub Actions workflow builds both Windows x64 and Apple silicon on native runners. Configure `WHITEBOARD_GOOGLE_OAUTH_CONFIG` with the same two-line desktop OAuth configuration. It produces candidate installers and checksums and does not publish a release. Its default artifacts are Windows unsigned and macOS ad-hoc signed; production signing remains a separate release decision.

```sh
python tools/test.py
python tools/benchmark_loading.py
```

The regression runner creates a disposable profile. Windows DPAPI tests need the normal logged-in user's credential-store access. Native self-tests run separately in the build scripts.

Outputs in `dist/`: Windows setup or Apple silicon DMG, platform SHA256SUMS files, and `build-info-<platform>.json`. Settings shows version/source revision. Release mode refuses dirty checkouts and missing OAuth configuration.

Before publication, test the exact installers on clean target machines: installation/update/uninstall, offline and expired-session startup, account switching, SSO/MFA, cancel/partial refresh, downloads, keyboard/high-DPI layouts, and Google OAuth/sync with a disposable calendar. Verify a quarantined DMG on a real Apple silicon Mac including the oldest OS claimed. Windows development packages and static macOS checks alone do not establish these results.
