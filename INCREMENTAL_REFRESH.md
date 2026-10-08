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
