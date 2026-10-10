# Incremental course refresh

Implemented after the published 0.4.0 release. The release assets have not been changed.

## Behavior

- Normal refresh compares `id,parentId,created,modified,hasChildren` for every visible content item. Successful recursive inventories avoid a redundant second folder traversal. When recursion is unavailable, the crawler walks accessible folders with explicit pagination/completeness checks.
- Added, changed, moved, or unverifiable items reload details and attachments. Each source item's enriched nodes (including multiple attachments and embedded sibling files) stay together in the cache. Unchanged content and its discovered submission links are reused.
- A missing item is pruned only after two complete course inventories. Failed/forbidden folders, malformed pages, repeated IDs, pagination cycles, limits, and incomplete pagination never confirm absence. Course-level confirmation deliberately favors retaining stale data over removing files in a partially accessible course.
- Failed attachment enrichment retains the previous item when available and retries it later. New unverified items remain candidates for revalidation. Successful content can be saved alongside retained data for inaccessible scopes; Contents shows a notice when some content could not be verified.
- Full refresh in Settings bypasses revision reuse. Daily reconciliation reloads full listings, attachments, and course-page links, even if parent timestamps did not change. Missing or invalid timestamps always require revalidation.
- Grades, deadlines, and submission checks run independently on every refresh. This is a visible-state comparison, not a historical change feed. Newly visible old items are found by inventory, even when their timestamps precede the previous refresh.

## Persistence and migration

Revision records, raw content, enriched nodes, and course catalogs are saved inside the existing atomic snapshot. Cache identity includes schema version, HTTPS school origin, and authenticated user ID, in addition to existing account-profile separation. Filtered-out course records remain available for later selection. The previous snapshot is never mutated during reconciliation; cancellation cannot publish a new saved cache.

Old snapshots without revision records receive a full first scan. Previously saved nodes not observed during that scan are retained until complete listings confirm their absence, after matching the school and user. Existing backup/recovery and cancelled-job persistence rules still apply.

### Sign-out and next sign-in — 10 October 2026

Sign-out now offers a separate, default-on **Keep file index for faster next sign-in** choice. It writes the last saved content index to the account's atomic `crawl-cache.json`: revision manifest, enriched nodes (including sizes), course catalogs, and course identifiers. Grades, the user display name, session cookies, and login credentials are excluded. Course-page bodies and links remain local content data. The ordinary dashboard/checkpoint is still removed unless an offline copy is requested.

The sign-in worker verifies the school account, selects its profile, then loads this crawl-only cache if there is no complete dashboard snapshot. Both the wrapper and inner content manifest must match school origin and authenticated user ID. The retained index is never a signed-out dashboard and never serves as a successful authentication result. Daily/full revalidation and two-complete-inventory removal confirmation still apply across sign-outs. Clearing both logout choices removes the snapshot, checkpoint, retained index, and their backups.

Deterministic logout/restart/login tests verify that two unchanged source items need just one compact inventory request, with zero detail/attachment requests. Additional tests cover changed/new content, removal confirmation across a second logout, account/school isolation, corruption, and explicit removal. These are synthetic request-count tests, not new live-school timings.

## Validation

`python tools/test.py`: 50 Python regressions plus JavaScript syntax/UI checks. Incremental cases cover persisted-cache reuse, attachment groups, additions/edits/moves, newly visible old content, two-pass removals, incomplete and forbidden scopes, failed attachment recovery, malformed timestamps, pagination failure/cycles/duplicates/foreign URLs, full/daily refresh, account and school isolation, filtered-course cache retention, old-cache migration, cancellation, and the Full refresh API flag.

Read-only Windows WebView2 test against the configured school on 8 October 2026, using fresh request caches for each run:

| Mode | Whole refresh | Requests | Reused content items | Content nodes |
|---|---:|---:|---:|---:|
| Initial scan | 29.180 s | 1,645 | 0 | 2,911 |
| Incremental | 19.457 s | 794 | 1,092 | 2,911 |
| Forced full | 28.955 s | 1,645 | 0 | 2,911 |

All three covered 40 enrolled courses and produced identical normalized content nodes (2,181 downloadable nodes). The incremental run used about 52% fewer requests and took about 33% less time than the forced full run. These are individual runs, not a controlled performance guarantee. The deadlines/dashboard stages remained available after roughly 1/3 seconds. Atomic cache serialization and reloading preserved equality.

The school refused recursive queries for 14 courses and some child-folder queries. It also returned 400/404 for attachment discovery on 103 items; those were retried rather than marked verified. There were 25 courses with some unverified inventory or enrichment. Optional HTML endpoints also returned some 500 responses. Cached content cannot reveal unavailable school data, and these limitations are reported rather than interpreted as deletion.

Live tests did not edit/delete school content, submissions, grades, or external calendars. Add/edit/delete behavior was exercised with deterministic test fixtures. Disposable profiles and private snapshots are removed after testing; only aggregate measurements remain in ignored `build/change-investigation/`.

## File sizes

Blackboard's attachment listings often omit size. The app preserves sizes supplied by the API and probes missing values through authenticated metadata requests. Direct file URLs use HEAD first; Learn attachment-download URLs use `Range: bytes=0-0` because this server responds to HEAD with HTTP 302 and no usable Location header. HTTP 206 uses the total in Content-Range, never the one-byte Content-Length. Every response body is cancelled without being read, including when a server ignores the range request. A noncompliant server may send buffered bytes before cancellation.

Requests and redirects are limited to the signed-in HTTPS origin. Login/error responses, encoded lengths, malformed ranges, and absent lengths remain unknown. HTML/JSON coursework attachments are accepted when the dedicated download endpoint returns a valid one-byte range with a total length; ordinary HTML/JSON pages remain unknown. Known zero-length files display **0 B**; unknown sizes display a dash with an explanation. Size tooltips show exact bytes. Unchanged nodes reuse saved sizes; missing-size failures retry daily or on Full refresh. A changed content item rechecks its sizes.

The metadata workers also accommodate the older JavaScript helpers installed by some Learn pages. A regression exercises the actual worker script with the overridden Array.from that was observed during native testing.

Final size-enabled live run (40 courses):

| Mode | Whole refresh | Total requests | Size metadata requests | Files with known size |
|---|---:|---:|---:|---:|
| Initial scan and size collection | 115.125 s | 3,826 | 2,181 | 2,180 / 2,181 |
| Incremental refresh | 27.330 s | 794 | 0 | 2,180 / 2,181 |

The dashboard stage was available after 3.742 seconds in the initial run. Collecting thousands of missing sizes adds a one-time cost, repeated by full/daily revalidation. Subsequent refreshes preserved all 2,911 normalized nodes including sizes, and made no size requests. Presentation returned 2,180 nonempty file-size labels. The remaining file was an HTML coursework attachment. A follow-up fixed that case and independently verified its 38,173-byte size, covering all 2,181 downloadable files in the tested inventory. Sample totals of 3,328,388, 2,717,688, and 6,074,788 bytes matched independently probed range headers.

Final validation: **59 Python tests**, JavaScript syntax checks, Contents rendering regressions, and metadata-worker tests for HEAD/range fallback, body cancellation, origin restrictions, and legacy Learn helpers. Native live checks ran on Windows; this change has not been independently exercised on a Mac.

## Contents and early classification follow-up — 9 October 2026

- Embedded resources in document bodies are grouped beneath their source item; unnamed media gets a source-based filename. Inline video/source, iframe, object/param, image, and file-link references are recognized. Separate attachments are retained alongside body media.
- Document items open their containing content page. Assignment, assessment, and forum entries open their specific submission/discussion routes. Coursework has an explicit assignment-link type, icon, and label, and is excluded from file download selections; its resource attachments remain ordinary files.
- A parser revision triggers revalidation of cached content. If optional attachment discovery is refused, saved resources are retained while the corrected node type and launch URL are applied from saved raw content.
- Calendar classification runs before the first published stage using account-bound cached submission evidence and lightweight content titles/handlers/links. Event-only cleanup also runs before that stage. A failed scope leaves unverified entries labeled **Checking type** rather than hiding them with events. File bodies and sizes are not required for classification.
- Contents search shows folder scope controls only for a nonempty query. Its inline × and Escape clear the query and retain the browsing location. Course filters support all/include/exclude modes for the current app session and reset on sign-out. Results sort by course or upload date in either direction; upload date prefers the creation timestamp.
- Course/deadline color customization offers a gradient plane, hue/saturation/brightness sliders, HEX input, preview, and keyboard operation. Values remain standard solid HEX colors and save through the existing settings path only on Apply.

Read-only live verification of the two reported English examples found an inline video and PDF in “Module 1: Flock”; both returned valid metadata (25,413,152 and 21,721,762 bytes). Its containing page returned HTTP 200. “Onslaught and Onslaught(er)” is a forum link; the corrected forum URL returned HTTP 200. The public discussion endpoint returned 400 for that forum, so no unsupported discussion API was added.

The final staged-loading live check showed **132 assignments at both the first deadline stage and the dashboard stage, and 132 at completion**, with **zero calendar type changes after dashboard entry**. Timings in that single run were 7.203 s for deadlines, 10.453 s for the dashboard, and 67.843 s at completion. File-size revalidation was skipped in this test to isolate classification; these timings are not a new all-features speed benchmark. The content index contained 173 assignment links, including coursework without calendar deadlines.

Validation: **70 Python tests**, JavaScript syntax checks, UI/search/color/metadata regressions, and headless Edge interaction checks with synthetic data. The rendered checks exercised clear/retype, include-course filtering, course/date sorting, HEX validation, keyboard gradient adjustment, and Apply. Picker and search-filter screenshots were visually inspected. Live school testing used Windows WebView2; this follow-up has not been independently tested on macOS. Disposable authenticated profiles were removed, and no school content was modified.
