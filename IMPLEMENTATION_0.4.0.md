# 0.4.0 implementation record

Implemented on 5 October 2026. Each improvement/fix was committed independently; the original working tree and review were preserved in `2cb3e2c`.

- [x] Windows WebView2 ABI, supported loader, and native smoke test
- [x] Atomic persistence, backups, corrupt-cache recovery
- [x] Real cancellation, atomic job ownership, bounded bridge requests/polling
- [x] Account isolation, explicit offline retention and real sign-out
- [x] DPAPI/Keychain credentials, HTTPS/origin restrictions, native bridge hardening
- [x] Consistent completion state and stable workload counts
- [x] Google synchronization guards for partial/empty refreshes and account/scope changes
- [x] Cross-platform external browser opening with visible fallback messages
- [x] Staged dashboards, first-run checkpoint, cached presentation, lazy view data
- [x] Measured network concurrency, bounded retries/backoff, explicit completeness
- [x] Streaming downloads/ZIPs, cancellation, collision-safe output reservations
- [x] Calendar overflow day view, current/overdue/archive grouping, local completion wording
- [x] Keyboard controls, dialog focus/Escape, readable status text, reduced motion, consistent local UTC offsets
- [x] Collapsible sidebar, favorites, grouped settings and unweighted grade labels
- [x] Runtime asset parity, build identity, pinned build dependencies, signing/notarization gates
- [x] Windows x64 setup and Apple silicon DMG builds with native packaged smoke tests
- [x] macOS document-window lifetime, Cocoa-thread cookie access and secure session restoration
- [x] Python/JavaScript regressions and browser UI verification

## Loading experiments

Synthetic representative dataset: 40 courses, 119 assignments, 136 grades, 699 events, 2,906 file nodes. Three runs per strategy; timing varies with machine load.

| Presentation strategy | Final median | JSON size |
|---|---:|---:|
| Full, without title cache | 1.086 s | 988,330 bytes |
| Full, with title cache | 0.328 s | 988,330 bytes |
| Lean dashboard | 0.209 s | 422,326 bytes |
| Warm cached dashboard | 0.016 s | 422,326 bytes |

The benchmark checks semantic equality for cached vs uncached presentation, excluding time-sensitive countdown labels. `tools/benchmark_loading.py` reproduces it without private data.

| Live-account network strategy | Deadlines | Dashboard | Complete file index |
|---|---:|---:|---:|
| 12 concurrent requests | 2.453 s | 4.547 s | 51.813 s |
| 24 concurrent requests | 2.125 s | 4.250 s | 45.000 s |

Both returned the same complete inventory (40 courses, 119 assignments, 136 grades, 699 calendar records, 2,906 content nodes). These are individual network runs, not statistically controlled estimates. The chosen default is 24 with backoff to smaller batches on 429/503. Earlier full-crawl baseline was roughly 70–80 seconds.

Deadlines and dashboard stages are usable before background indexing finishes. A first-run checkpoint survives restart without replacing a previous complete snapshot; incomplete refreshes preserve the saved complete copy. File and course presentation is requested when those views open. Full indexing remains necessary to verify assignment links/statuses; the UI reports that ongoing work.

## Verification and release limits

25 Python tests pass, plus JavaScript syntax and UI regression checks. They cover storage recovery, OS encryption, account isolation, cancellation, sync deletion safety, streaming downloads/collisions, origin/bridge trust, WebView2 ABI, staging, throttling and macOS logout callback ordering. `python tools/test.py` uses an isolated profile.

Real Windows WebView2 and the packaged application passed startup, script results, bridge round trip, document tabs and cookie clearing. Inno Setup 6.7.3 produced the development installer. Browser verification used only synthetic data: Home, compact navigation, Settings, lazy Contents, course folder expansion, calendar month overflow and UTC-offset date labels at narrow and 1280×720 viewports.

Private live-test snapshots and authenticated profiles were removed after testing. Aggregate timings remain in ignored `build/implementation-test/`. No external Google/calendar or coursework writes were performed.

The native Windows x64 and macOS 15 Apple silicon builds both passed at revision `0e7c34a` ([build evidence](https://github.com/LapisLa2uli/WhiteBoard/actions/runs/37308962734)). macOS verified arm64 architecture and the ad-hoc signature, opened/closed document tabs, and saved, cleared and restored an encrypted session through Keychain. Native testing found and fixed Cocoa window ownership, cookie-store thread access and an unsupported cookie setter. Windows regressions and packaged WebView2 startup passed.

The workflow also checks Windows setup, same-version reinstall, installed-app launch and uninstall on a disposable runner, and verifies/mounts the DMG before copying and launching the Mac app. These checks do not establish upgrades from older releases or the oldest supported macOS version.

**Distribution status:** the candidate Windows installer is unsigned; the Mac app is ad-hoc signed and not notarized. Production signing and Gatekeeper acceptance remain unverified, and publication awaits the signing decision. Broader manual acceptance still includes screen-reader/high-DPI coverage, SSO/MFA variations, old-version upgrades and Google OAuth/sync with a disposable calendar. No release has been published at the time of this record. See `packaging/README.md` for build and verification commands.
