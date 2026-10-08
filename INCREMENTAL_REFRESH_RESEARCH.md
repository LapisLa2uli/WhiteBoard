# Incremental content refresh investigation

Checked on 8 October 2026 against the configured school server using the supplied account, in disposable profiles. These findings describe tested capabilities; incremental refresh has not yet been implemented. Only aggregate results were saved. No course content, submission, grade, or calendar was changed. Temporary authenticated profiles were removed after testing.

## Conclusion

The school supports enough of the public content API to reconstruct changes in the content currently visible to the signed-in account. A compact manifest of content IDs, modification timestamps, and parent IDs is the recommended baseline. Full details and attachment discovery can then be restricted to added/changed entries.

No dedicated content add/edit/delete feed was found in the official public API specification. This does not establish that institution-managed event integrations do not exist. The existing app's internal activity-stream GET endpoint returned HTTP 405 in the probe and is not a verified source of complete change history or deletions.

## Verified API features

Reference: [Anthology Learn API portal](https://developer.anthology.com/portal/displayApi/Learn) and its [official OpenAPI specification](https://devportal-docstore.s3.amazonaws.com/learn-swagger.json), retrieved for this investigation (specification info version `4001.0.0`, not a claim about the school's installed version).

Endpoint:

```text
GET /learn/api/public/v1/courses/{courseId}/contents
```

Supported and tested parameters:

- `recursive=true`: includes descendants in courses where the current account is permitted to use recursive listing.
- `modified=<ISO timestamp>&modifiedCompare=greaterOrEqual`: returns content edited since a cutoff.
- `created=<ISO timestamp>&createdCompare=greaterOrEqual`: returns content created since a cutoff.
- `fields=id,parentId,created,modified,hasChildren`: compact manifest without titles or body HTML.
- `fields=id`: smallest inventory for detecting entries no longer visible.
- `limit=200`, following every `paging.nextPage` response. Forced pagination with `limit=50` preserved the requested fields and exactly the same IDs.

Date-filter results were checked against locally filtering complete API responses, including future-date controls that correctly returned zero rows. This verifies filtering behavior, rather than assuming HTTP 200 means a parameter was honored.

The public children endpoint also honored compact fields and the modified-date filter in the tested accessible folders:

```text
GET /learn/api/public/v1/courses/{courseId}/contents/{contentId}/children
```

Use `includeInActivityTracking=false` for children/detail probes where supported.

## Coverage and limits

- Of 40 enrolled courses, 26 allowed recursive content listings; 14 returned HTTP 403 for the recursive query.
- All 14 allowed nonrecursive top-level listings. Two were examined further with compact folder-by-folder traversal: accessible child listings worked, but some individual folders returned 403. The resulting inventories were therefore partial, even though all queued requests finished.
- The 26 successful recursive inventories returned 984 content items in total, all with a `modified` timestamp. This is not an account-wide file count: it excludes inaccessible scopes and attachments represented separately from their parent content item.
- Compact and full ID sets matched in all five courses compared directly, including 399-item and 102-item courses. Nonempty sampled folder descendants were already present in successful recursive root results.
- Repeated manifests for the two larger courses showed zero additions, removals or metadata changes during the observation period. No actual server-side edit/deletion was performed to manufacture changes.
- Missing entries mean "no longer returned to this account," which can reflect deletion, availability changes, or changed access. The API does not establish which happened.
- The six attachment listings sampled exposed `id`, `fileName`, and `mimeType`, with no independent modification timestamp, version, size, or content hash. The probe cannot prove that replacing attachment bytes always updates the parent content timestamp. Periodic reconciliation remains necessary for that case.

## Measured payload sizes

UTF-8 JSON response-body bytes, summed across pages; not compressed wire traffic or an end-to-end speed benchmark:

| Course sample | Items | Full content | ID/timestamp manifest | IDs only |
|---|---:|---:|---:|---:|
| Larger sample | 399 | 324,947 B | 48,840 B | 7,537 B |
| Second sample | 102 | 60,452 B | 12,129 B | 1,951 B |

The larger sample's manifest is about 85% smaller; its ID-only inventory is about 98% smaller. Individual request timings did not establish a speedup from smaller payloads alone: the larger full listing took 2.084 s versus 2.232 s for the manifest in these single runs. The expected performance gain comes primarily from skipping unchanged attachment/detail requests and redundant folder traversal.

The current crawler requests recursive content and then expands folders again. Where a complete recursive listing succeeds, the sampled folder responses added no new IDs. That second traversal is a separate opportunity to remove unnecessary requests. Retain it as a fallback where recursive listing is forbidden or incomplete.

## HTTP caching findings

No ETag was returned in the tested content responses. Cache-Control was `no-cache, max-age=0, no-store, must-revalidate`. A Last-Modified header was present but was about 20 years behind the response date and advanced across requests; it did not behave like a content revision. Sending its value in If-Modified-Since still returned HTTP 200 with the full body in all three conditional checks. Do not use this header as the incremental cursor or rely on HTTP 304 for this server.

## Recommended reconstruction algorithm

1. Store the complete normalized content index and its raw manifest per school/account/course, keeping attachment and submission-link enrichment associated with each parent content ID.
2. On refresh, fetch a compact manifest. Prefer a recursive course listing when supported; otherwise fetch nonrecursive roots and accessible folder listings. Track successful completeness for each scope and every pagination chain.
3. Compare IDs: new IDs are additions. For existing IDs, compare `modified`, `parentId`, and relevant manifest metadata. Treat missing/invalid timestamps as requiring revalidation. Fetch full content and attachments only for new/changed/revalidation candidates; reuse other enrichment.
4. Treat a previously saved ID missing from a successfully completed listing as a removal from that visible scope. Preserve cached records under failed/forbidden scopes and mark them unavailable or stale, according to the app's existing offline-data policy. Never convert 403, timeouts, pagination failure, or cancellation into deletion. For destructive local pruning, confirm absence on a second complete pass to reduce pagination/move races.
5. Commit the updated index atomically only after reconciliation for that scope succeeds. Do not infer child changes solely from a folder timestamp. Parent IDs can identify moves without requiring file contents to be downloaded.
6. Optionally use created/modified-since queries to obtain changed details in bulk. Use an overlap window and advance the cursor only after a successful fetch. Continue inventory comparison: a date query alone cannot detect deletions or newly visible old content.
7. Keep a periodic/full-refresh path for attachment replacements whose parent revision might not change, permission changes, and server behavior differences. Refresh grades, deadlines, and submission status independently.

This recovers the current visible state and minimizes repeated detail loading. It does not reconstruct a historical audit trail: an item created and deleted between two observations may never be observed.

Aggregate probe evidence and disposable scripts are ignored under `build/change-investigation/`. Production crawler behavior was not changed by this investigation.
