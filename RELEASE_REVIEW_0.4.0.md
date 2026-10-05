# WhiteBoard 0.4.0 release review

Reviewed on 5 October 2026. The findings below describe the original baseline. The subsequent implementation is documented in [IMPLEMENTATION_0.4.0.md](D:/stuff/WhiteBoard/IMPLEMENTATION_0.4.0.md): source improvements are committed, Windows packaging/native smoke tests pass, and loading strategies were measured. **Public release still requires signed artifacts and real Apple silicon/clean-machine acceptance checks.** The attached older DMG does not contain these changes.

## Scope and evidence

I read the root README, changelog, release notes, native hosts, login/crawler, Blackboard parsers and models, persistence, presentation layer, frontend, Google integration, and packaging scripts. I treated the archived Flet app as historical context. The working tree had seven modified files before this review. Those changes were preserved in `2cb3e2c` before implementation; later commits implement the findings. No release was published.

- Source baseline: commit `0d8532c`, plus the existing working-tree modifications. Baseline `static/app.js` SHA-256: `54e83e7333611875debd86f362a6b9aa40686a00968cacd4bfaa47430789fd83`.
- Attached DMG: 17,900,572 bytes; SHA-256 `afe0fc6b020249546303e1657efb80a59cfddc96d9ad9750db01f1b78e985284`.
- Windows: launched the current source in an isolated profile with Python 3.12.14 and the installed WebView2 runtime. The unmodified source hit the bridge exception described below. An **in-memory workaround in a disposable test launcher**, supplying the missing event-token pointer, allowed login and crawling. This is not a fix to the shipped application.
- Signed in to the configured Blackboard school using the supplied credentials. The snapshot contains **40 courses, 119 assignments, 136 grades, 699 calendar records, and 2,906 content nodes**, with no recorded crawl errors. The first full crawl took approximately 70–80 seconds. Its displayed counters reached 512 folders and 3,593 files; those are progress counts, not unique final inventory totals.
- Exercised the source UI against that real snapshot in a loopback-only harness with separate settings: Home, assignment search, mark/undo, history filters, Grades, calendar list/week/month, Contents tree/folder/columns and extension search, Settings, and logout/saved access. The harness blocked external writes. No coursework was submitted and no Google calendar was changed.
- Existing Windows executable and setup were inspected; both are unsigned. A packaged window was launched, but I did not establish a complete successful workflow in that older binary. Its embedded archive contains a single `host` module rather than the current `host._windows`/`host._macos` arrangement.
- DMG inspection confirmed version 0.4.0, ARM64 in all 11 inspected Mach-O files, declared minimum macOS 11.0, and ad-hoc code signatures. This Windows machine cannot establish actual macOS startup, Gatekeeper acceptance, WKWebView behavior, or Apple silicon compatibility at runtime. Extraction skipped macOS symlinks; that is a Windows extraction limitation, not evidence that those links are broken in the DMG.
- Python syntax parsing passed for 20 current source files; current and DMG JavaScript passed `node --check`. Additional isolated behavioral probes are summarized below. These are not a substitute for installer tests or a current regression suite.

Evidence and review scripts are under [build/release-review](D:/stuff/WhiteBoard/build/release-review). The report contains no passwords, tokens, individual grades, or student identifiers. Temporary review processes were stopped and the isolated authenticated profiles, snapshots, and local test settings were removed after testing. Re-running snapshot-dependent probes requires a new isolated login/crawl.

## Fix before release

### 1. P0 — Correct the Windows WebView2 bridge ABI

**Reproduced in current source.** Launching produced `OSError: exception: access violation reading 0xFFFFFFFFFFFFFFFF` at bridge registration. `ADD_WEB_MESSAGE` declares only the interface and handler arguments, whereas `add_WebMessageReceived` also requires an output `EventRegistrationToken` pointer. An invalid native write can leave a blank/uninitialized window or crash; success under one interpreter does not make this safe.

Supply the correctly typed token pointer, retain/remove the registration appropriately, and audit every manually declared COM signature and IID. Prefer the supported WebView2 loader/API over `CreateWebViewEnvironmentWithOptionsInternal` from a private runtime DLL. Run a real Windows packaged startup/bridge smoke test, including document tabs. The current `--selftest` imports AppKit unconditionally and serves only macOS.

Sources: [host/_windows.py:187](D:/stuff/WhiteBoard/host/_windows.py:187), [host/_windows.py:394](D:/stuff/WhiteBoard/host/_windows.py:394), [host/_windows.py:982](D:/stuff/WhiteBoard/host/_windows.py:982), [run.py:144](D:/stuff/WhiteBoard/run.py:144). Original exception: [stderr.log](D:/stuff/WhiteBoard/build/release-review/stderr.log).

### 2. P1 — Implement real logout and account isolation

**UI reproduction and isolated session probe.** Log out only navigates to `/login`; Open saved dashboard immediately reopens account data. Windows `clear_cookies()` is a no-op, and no logout bridge route exists. Separately, `WebSession.login()` accepts any already-authenticated session before checking the newly entered username/password. The probe passed a different username and incorrect password with an existing valid session: login succeeded without submitting those credentials.

Offer explicit “Sign out” and “Keep an offline copy” choices. Clear authentication state and close authenticated document tabs on sign-out; verify the authenticated account matches the requested account. Partition snapshots, filters, local completion marks, and tokens by school origin plus immutable account ID. Currently they share one global profile, so changing accounts can mix local state.

Sources: [static/app.js:376](D:/stuff/WhiteBoard/static/app.js:376), [session.py:148](D:/stuff/WhiteBoard/session.py:148), [host/_windows.py:1248](D:/stuff/WhiteBoard/host/_windows.py:1248), [data.py:25](D:/stuff/WhiteBoard/data.py:25).

### 3. P1 — Protect authentication material and constrain credential destinations

**Code findings; no credential theft was attempted.** macOS writes session-cookie values to ordinary JSON. Google access/refresh tokens are also written as plain JSON. The school URL is accepted without requiring HTTPS, and credential injection checks for matching input fields without verifying the page's origin after redirects. The Mac bundle enables arbitrary web-content loads globally.

Store authentication material in macOS Keychain and Windows Credential Manager/DPAPI, restrict profile permissions, require HTTPS, and check the expected school or explicitly trusted identity-provider origin before filling credentials. Make SSO/MFA interactive when needed. Scope any legacy TLS exception narrowly instead of disabling the normal transport restrictions for every web page.

As defense in depth, restrict dashboard navigation to packaged UI resources, validate native bridge message origins, and add a restrictive CSP. Remote document tabs are already created without the dashboard bridge; preserve that separation. No exploitable remote bridge path was demonstrated in this review.

Sources: [host/_macos.py:969](D:/stuff/WhiteBoard/host/_macos.py:969), [app/google_calendar.py:116](D:/stuff/WhiteBoard/app/google_calendar.py:116), [session.py:206](D:/stuff/WhiteBoard/session.py:206), [packaging/whiteboard-macos.spec:126](D:/stuff/WhiteBoard/packaging/whiteboard-macos.spec:126).

### 4. P1 — Make cancellation stop the job, and prevent indefinite loading

**Direct frontend logic probe.** Clicking Cancel sends zero backend requests: it clears the loading view and polling only. The crawler continues and can still save a snapshot or perform enabled Google sync. `_cancel` exists but no exposed action sets it. The unused crawl lock also does not enforce a single atomic job start.

Add job IDs, atomic job ownership, a cancellation endpoint/event, request aborts, and checks before persistence or Google sync. Preserve the existing dashboard while refreshing. Give bridge calls deadlines and visible errors. `api()` currently has no timeout, and `pollJob()` only finishes if it first observed `busy=true`; a job that completes before that first poll can leave the UI waiting indefinitely.

Sources: [static/app.js:71](D:/stuff/WhiteBoard/static/app.js:71), [static/app.js:522](D:/stuff/WhiteBoard/static/app.js:522), [static/app.js:692](D:/stuff/WhiteBoard/static/app.js:692), [crawl.py:114](D:/stuff/WhiteBoard/crawl.py:114).

### 5. P1 — Recover from interrupted or corrupt cache writes

**Reproduced with a disposable truncated snapshot.** `present.load_snapshot()` raises `JSONDecodeError`, which can reject initial state loading; `boot()` has no recovery path. Settings, tokens, and snapshots are written directly over their final files, so a crash or overlapping reader can encounter incomplete JSON.

Write to a temporary file and atomically replace the destination, serialize writes, retain a last-good snapshot, validate the schema, and recover to a usable login/offline screen with an actionable message. Do not silently replace a good snapshot with an incomplete refresh.

Sources: [present.py:43](D:/stuff/WhiteBoard/present.py:43), [blackboard/store.py:65](D:/stuff/WhiteBoard/blackboard/store.py:65), [blackboard/store.py:193](D:/stuff/WhiteBoard/blackboard/store.py:193).

### 6. P1 — Preserve Google events when a refresh is partial

**Simulated transport probe; no Google writes.** Sync treats the current event list as complete and deletes every previously managed event missing from it. Feeding it an empty list schedules deletion of a previously valid managed event. A transient calendar-fetch failure with courses still present can reach this path; filtering the loaded course set also changes the apparent authoritative inventory.

Track completeness per dataset and sync scope. Allow deletion only after a successful, complete fetch for that same account/scope; otherwise preserve existing events and report partial success. Require a separate intentional operation for clearing all managed events. Keep the existing `whiteboard=1` ownership filter, which already avoids deleting unrelated events.

A second probe found that a locally marked submitted assignment remains in `events_for_sync()`, even while Assignments displays it as submitted. Define one effective status calculation shared by dashboard, calendar, and Google export. Clearly describe when local status changes sync.

Sources: [app/google_calendar.py:76](D:/stuff/WhiteBoard/app/google_calendar.py:76), [app/google_calendar.py:230](D:/stuff/WhiteBoard/app/google_calendar.py:230), [crawl.py:184](D:/stuff/WhiteBoard/crawl.py:184).

### 7. P1 — Fix completion-state contradictions and the global count

**UI and standalone JavaScript reproductions.** Mark submitted, expand Submitted, then Undo: the item returns to the to-do list, but the calendar can still say Submitted. `reapplyManualMarks()` sets `status`, `manual`, and `finished` on calendar/home items; undo only resets `finished` there. The stale status still controls rendering.

Also, assignment search feeds `todoCount()`: searching down to one result changes the navigation badge to 1 on later renders, including other pages. It no longer represents the total workload.

Update all status fields through one reducer/derived model. Calculate the global badge independently of the text search and show a separate result count. Add regression cases for mark → filter → undo → calendar, ignore → restore → Home, and rapid overlapping updates.

Sources: [static/app.js:774](D:/stuff/WhiteBoard/static/app.js:774), [static/app.js:1196](D:/stuff/WhiteBoard/static/app.js:1196), [static/app.js:1361](D:/stuff/WhiteBoard/static/app.js:1361).

### 8. P1 — Finish platform parity and publish reproducible signed builds

**Artifact inspection and simulated macOS import check.** The current Chrome/Edge opener imports Windows-only `winreg` before its fallback handling. Simulating its absence raises `ModuleNotFoundError`; the advertised built-in fallback never runs. Use the system default browser and platform adapters, including macOS `open`, and show failures on every screen rather than only the Contents note area.

The attached DMG's UI still asks users to create a Google Cloud Desktop OAuth client and enter its ID/secret. The current source removed those fields and expects bundled configuration: the Windows spec includes `authid.txt`, but the Mac spec does not. Thus a fresh Mac build from current source has no configured Google sign-in path. Absence of that file alone does **not** prove the attached older DMG's manual setup is broken. Decide on one supported flow and test it in both final packages. A desktop OAuth client identifier is public application configuration; refresh tokens are the secrets that require secure storage.

The attached ARM64 app is ad-hoc signed; the Windows installer/executable are unsigned. For a public release, use Developer ID signing with a secure timestamp, notarize/staple, and Authenticode-sign Windows builds. Make signature verification failures fatal; the Mac script currently tolerates signing errors. Verify first launch from a quarantined downloaded DMG on a clean Apple silicon Mac.

Build both platforms from the same source revision, include version/build ID in About, pin build dependencies, and generate SHA-256 checksums. The current Mac build requires an untracked `dist/logo-macOS.png`, so it is not reproducible from a clean checkout. The active Windows build checks file presence but does not run the application. Update the stale release document that still requires Intel macOS to match the requested **Apple silicon + Windows** release scope.

Sources: [server.py:419](D:/stuff/WhiteBoard/server.py:419), [server.py:460](D:/stuff/WhiteBoard/server.py:460), [packaging/whiteboard.spec:12](D:/stuff/WhiteBoard/packaging/whiteboard.spec:12), [packaging/whiteboard-macos.spec:27](D:/stuff/WhiteBoard/packaging/whiteboard-macos.spec:27), [packaging/build_macos.sh:55](D:/stuff/WhiteBoard/packaging/build_macos.sh:55), [packaging/build_macos.sh:134](D:/stuff/WhiteBoard/packaging/build_macos.sh:134).

## UI and experience improvements

| Priority | Observation | Proposed change |
|---|---|---|
| High | 38 to-do items, 36 overdue; the first page starts with deadlines over 500 days old. Dates omit the year. | Default to current-term work. Group Now, Upcoming, Overdue, and Archived; put the nearest actionable deadline first. Show the year for older dates. Keep archive filtering reversible. |
| High | “Mark submitted” is a local marker. Home even shows it for a school schedule event. | Use “Mark done in WhiteBoard” with a short explanation, distinguish confirmed Blackboard submission from a local mark, and give events appropriate actions. Label bulk completion clearly and offer immediate Undo. |
| High | Month view limits each date to three events; “+2 more” is a noninteractive div. | Make it a button that opens all events for that date or switches to the day list. Preserve the date and scroll position on return. |
| High | Yellow and green countdown text have about 1.92:1 and 2.28:1 contrast on white; orange is about 3.56:1. File buttons/checkboxes and several selects lack useful accessible names. Cards/folder names are clickable non-keyboard elements. | Use dark text with colored borders/status badges. Add associated labels, named icon buttons, semantic links/buttons, keyboard navigation, dialog focus management/Escape, and reduced-motion support. Target 4.5:1 for normal text. |
| Medium | Sign-in copy discusses “the other WhiteBoard app”; forms have no clear validation or password-visibility control. | Explain the benefit and where credentials go; validate URL/empty fields locally, add properly associated labels and autocomplete attributes, and provide a visible SSO/MFA flow. |
| Medium | The dashboard is unavailable throughout a full crawl. Progress remains titled “Signing in” while thousands of files are indexed. | Separate authentication from synchronization. Show assignments/grades first and index files in the background, with last-updated and partial/offline indicators. Make progress phase-based and cancellable. |
| Medium | At 1280×720 the header wraps Refresh/Log out onto a second row. Forty colorful course cards dominate the sidebar. | Use a collapsible sidebar, current-term/favorite groups, shorter display names with full-name tooltips, and an account menu. Keep global actions in a stable location. |
| Medium | Settings places Google integration after all 40 course color cards. Fonts and explanatory text are Windows-specific. | Group Account, Sync, Appearance, and Storage. Move per-course appearance into a collapsible editor. Use `system-ui` by default and only offer available platform fonts. |
| Medium | The interface mixes English date strings with OS-localized Chinese dates. Course totals simply sum points and may not reflect weighted Blackboard grading. | Apply one locale/timezone policy, display timezone near deadlines, and label totals “unweighted points estimate” unless official weighted totals are available. |
| Medium | The visible grade cards displayed “No date.” | Distinguish unknown posted date from due date; avoid implying “Recent” is reliably chronological when timestamps are missing. |

Observed month view (account identifier redacted):

![Calendar UI showing dense sidebar, wrapping toolbar, and noninteractive event overflow](D:/stuff/WhiteBoard/build/release-review/calendar-review.jpg)

Relevant UI locations: [static/app.js:869](D:/stuff/WhiteBoard/static/app.js:869), [static/app.js:1557](D:/stuff/WhiteBoard/static/app.js:1557), [static/app.js:1956](D:/stuff/WhiteBoard/static/app.js:1956), [static/app.js:2245](D:/stuff/WhiteBoard/static/app.js:2245), [blackboard/api.py:4092](D:/stuff/WhiteBoard/blackboard/api.py:4092).

## Optimization and reliability work

1. **Cache normalized titles and index relationships.** Five ordinary `build_state()` measurements had a median of **2.62 s** and maximum **2.77 s**, producing **1,681,846 bytes** of JSON. Profiling showed over 522,000 title-normalization calls in one build, driven by repeated assignment/submission matching. A disposable in-memory `lru_cache` experiment reduced three builds to **0.396 / 0.383 / 0.387 s**. This suggests roughly a 6–7× improvement is available without changing the product design. Use bounded caches and account/snapshot-scoped indexes for assignments, grades, and normalized titles; verify identical results before adopting it. Profiling itself adds overhead, so its 19-second instrumented duration is not normal latency.
2. **Return smaller data by view.** Cache immutable presentation data by snapshot/settings revision. Load file trees and course details on demand. Google status polling currently rebuilds the entire state, including the 2,906-node inventory, every cycle. A tiny status endpoint would avoid that work.
3. **Stream downloads and ZIP output.** JavaScript reads an entire file, converts it to a binary string and base64, and passes it through JSON. Folder ZIP creation retains all downloaded bytes before writing. Peak memory can substantially exceed total file size. Stream to temporary files or use native authenticated downloads, append ZIP entries incrementally, limit concurrent downloads, and support cancellation/disk-full recovery.
4. **Never overwrite on filename exhaustion.** A probe created `file.pdf` and all suffixes 2–99; `_unique_path()` returned the already-existing original. Use exclusive creation and an unbounded/UUID suffix rather than falling back to the original. This is a confirmed local data-loss edge case.
5. **Make network failures explicit.** The fetcher uses up to 24 concurrent requests and truncates response text at 2,000,000 characters before JSON parsing. Add adaptive concurrency, bounded backoff for 429/503 with Retry-After, pagination/size-limit errors, and per-section completeness. Do not silently treat an unreadable response as an empty dataset.
6. **Reduce avoidable UI work.** Cache file ancestor paths instead of repeated linear scans during search; debounce expensive searches. Update only changed DOM regions, pause second-by-second countdown work when hidden, and make hover/scroll ripples optional. On the test account, search returned 1,409 PDF/folder matches and pagination worked; this recommendation addresses scale and motion rather than a demonstrated search failure.
7. **Trim distribution assets.** The DMG contains the same 2.55 MB icon in Resources and Resources/assets. The current Windows spec copies the complete design-assets directory. Package runtime assets explicitly; preserve editable design files as build inputs.

Sources: [present.py:159](D:/stuff/WhiteBoard/present.py:159), [blackboard/api.py:1667](D:/stuff/WhiteBoard/blackboard/api.py:1667), [session.py:28](D:/stuff/WhiteBoard/session.py:28), [session.py:77](D:/stuff/WhiteBoard/session.py:77), [server.py:759](D:/stuff/WhiteBoard/server.py:759), [server.py:980](D:/stuff/WhiteBoard/server.py:980), [static/app.js:1777](D:/stuff/WhiteBoard/static/app.js:1777).

## Release acceptance tests

Before signing off 0.4.0, run the exact final installers on a clean Windows x64 machine and a real Apple silicon Mac, including the oldest OS version you intend to claim. Exercise install/update/uninstall, first launch, WebView2-missing recovery, valid/invalid login, SSO/MFA, true logout/account switching, expired sessions, offline startup, cancelled and partial refreshes, snapshot recovery, assignment deep links, document tab lifecycle, actual small/large downloads, collisions, and Google OAuth/sync using a disposable calendar. Add keyboard/screen-reader and high-DPI/narrow-window checks.

For this review, actual Google authorization/sync, coursework submission, native large downloads, Windows installer upgrade/uninstall, and all macOS runtime behaviors remain **unverified**. The Google deletion and account-switch findings were isolated simulations; they did not alter external account data. The successful login/crawl used the current Windows source with the test-launcher ABI workaround, not the DMG or a validated final installer.

Suggested implementation order: Windows bridge → logout/account isolation and secure token storage → atomic persistence/cancellation → completion and sync correctness → platform/build parity → performance and UI improvements. Rebuild both release artifacts from the resulting revision and repeat the acceptance tests on those artifacts.
