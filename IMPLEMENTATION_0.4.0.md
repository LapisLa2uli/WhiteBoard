# 0.4.0 implementation checklist

Each completed improvement is committed separately. The original working tree and review are preserved in `2cb3e2c`.

- [x] Windows bridge ABI, supported loader, and native smoke test
- [ ] Atomic persistence and corrupt-cache recovery
- [ ] Real cancellation, job ownership, and bounded bridge calls
- [ ] Account isolation and real logout
- [ ] Secure credentials, HTTPS/origin restrictions, and bridge hardening
- [ ] Completion-state consistency and stable workload count
- [ ] Safe Google synchronization with partial-data protection
- [ ] Cross-platform browser opening
- [ ] Fast staged loading, cached presentation, lazy file data, and benchmarks
- [ ] Bounded network concurrency, retries, and explicit completeness
- [ ] Streaming downloads, cancellation, and collision-safe output
- [ ] Calendar overflow, current-work grouping, and clear local completion
- [ ] Accessible navigation, dialogs, contrast, locale, and reduced motion
- [ ] Compact sidebar, grouped settings, and honest grade labels
- [ ] Reproducible platform packaging, signing gates, version identity, and release documentation
- [ ] Regression suite and final native/UI verification

Apple silicon runtime testing and production signing require a Mac and signing credentials. Code and release-script work proceeds independently. No release will be published as part of implementation.

Windows verification: SDK signature audit and native smoke test passed (supported loader, script result, bridge round trip, document tab). Two ABI regression tests pass.
