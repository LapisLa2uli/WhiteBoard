# Changelog

Summarized major changes for each WhiteBoard release, compared with the version before it.
Write for someone using the app, not for developers. Every version needs the three
headings below. Packaging and GitHub Releases copy this text.

## [Unreleased]

### Added features
- Contents search has an inline clear button, course include/exclude filters, and sorting by course or upload date. **Only this folder** appears while a search is active.
- Refresh reuses unchanged course files and checks for added, edited, moved, and removed content. Settings now includes **Full refresh**, and file details are rechecked daily.

### Bugfixes
- Calendar submission links are classified before the dashboard first appears, while file downloads and sizes load later. Unverified entries show **Checking type** and stay visible when events are hidden.
- Coursework in Contents is labeled **Assignment link** with a distinct icon and opens its submission/discussion page. Attached resources remain downloadable separately.
- Embedded course media and documents are grouped under their source page with usable file names. Content pages and discussions open their proper Blackboard pages instead of broken file links.
- Contents shows file sizes even when Blackboard omits them from its file list. Sizes are saved for unchanged files, empty files show **0 B**, and hovering over a size shows its exact byte count.
- Calendar items with a submission page are treated as assignments, even when Blackboard labels them as events or their titles mention tests or reviews. Saved entries are corrected from their known submission links and indexed course content.

### Other changes
- None in this release.

## [0.4.0] - 2026-10-05

### Added features
- Windows x64 setup and an Apple silicon Mac disk image.
- Your dashboard opens in stages: deadlines first, then grades, while course files finish loading. Saved data opens quickly, and you can cancel an active refresh.
- Collapse the course sidebar, favorite courses, and browse assignments grouped into current, overdue, archived, and completed work.
- Mark individual or overdue assignments **done in WhiteBoard**, with Undo. These are local reminders; submit coursework on Blackboard.
- Open all events on a busy calendar day using the **more** button. Calendar list, week, and month views keep your place when you open an assignment.
- Search files and folders by name or extension, browse them in tree/folder/column views, and download selected files or folders.
- Use school sign-in for SSO/MFA, choose how external pages open, and adjust fonts, colors, page sizes, and decorative motion in grouped Settings.
- Keyboard navigation, named controls, visible focus, dialog Escape handling, and reduced-motion support.

### Bugfixes
- Fixed Windows startup crashes and unreliable document tabs.
- Fixed Mac crashes after closing document tabs and restored saved school sessions securely on restart.
- Sign out clears the school session and separates saved data/settings by account. You can explicitly keep an offline dashboard.
- Saved session credentials use operating-system protection. Interrupted saves and incomplete refreshes preserve usable data.
- Cancel stops a refresh. Searching no longer changes the total assignment badge, and local completion stays consistent across screens.
- Partial or empty refreshes cannot silently delete managed Google Calendar events.
- Downloads stream to disk, can be cancelled, and avoid overwriting existing filenames.
- Calendar overflow is clickable, and older dates include the year and local UTC offset.
- Updated a build dependency to fix reported security vulnerabilities.

### Other changes
- Settings shows the app version and source revision. Both installers are built from the same commit and accompanied by SHA-256 checksums.
- Dashboard presentation uses cached data and loads file details on demand. In one live-account comparison, the dashboard appeared in about 4.3 seconds while full indexing completed in about 45 seconds; results depend on your school and connection.
- Grades label totals as unweighted points estimates and distinguish missing posted dates. Blackboard may calculate final grades differently.
- Windows uses Microsoft Edge WebView2; macOS uses its built-in web view. Intel Macs are outside this release's scope.
- Google sign-in uses the app's bundled desktop client configuration. User passwords and refresh tokens are never bundled in the installers.


## [0.3.0] - 2026-09-11

### Added features
- On Assignments (All), submitted work is in its own foldable group under the to-do list.
- Calendar can switch between a day-by-day list, a week grid, and a month grid, similar to Google Calendar.
- Calendar now includes Blackboard events such as meetings and office hours, not only assignments.
- Completed assignments on the calendar are shown in gray.

### Bugfixes
- Long assignment or course names no longer cover the Mark as submitted / Undo buttons.
- Each posted grade is listed once on Grades instead of appearing twice.

### Other changes
- None in this release.

## [0.2.0] - 2026-09-11

### Added features
- If neither Microsoft Edge nor Google Chrome is installed, WhiteBoard now explains what is needed instead of only reporting that its browser could not start.

### Bugfixes
- Release checks now prevent a second browser from being included accidentally and making future downloads much larger.

### Other changes
- Windows and Mac downloads are substantially smaller because WhiteBoard now uses Microsoft Edge or Google Chrome already installed on your computer.
- Microsoft Edge or Google Chrome is now required before you sign in. The browser is no longer included inside WhiteBoard.

## [0.1.3] - 2026-09-11

### Added features
- The Windows and Mac apps now include everything needed to open and sign in. You do not need to install Chrome or Edge first.

### Bugfixes
- The Mac apps no longer quit the moment you open them. Older Mac downloads had the same kind of startup failure as Windows 0.1.2.
- A GitHub release is not published unless Windows, Intel Mac, and Apple Silicon Mac installers are all present.
- The Mac installers for this version are included. An earlier 0.1.3 upload only had the Windows installer.

### Other changes
- The download is larger because the app now carries its own browser.
- Release notes are grouped into Added features, Bugfixes, and Other changes.

## [0.1.2] - 2026-09-11

**Known not to work.** The Windows app closed as soon as you opened it. Use 0.1.3 or later.

### Added features
- None in this release.

### Bugfixes
- Attempted to fix the Windows app closing on startup. The fix was incomplete.

### Other changes
- Mac installers were not included in this release.

## [0.1.1] - 2026-09-10

**Known not to work.** The app closes as soon as you open it. Use 0.1.3 or later.

### Added features
- Separate Mac downloads for Intel computers and Apple Silicon (M1, M2, M3, M4).

### Bugfixes
- None in this release.

### Other changes
- None in this release.

## [0.1.0] - 2026-09-10

**Known not to work.** The app closes as soon as you open it. The Mac file also would not run on Intel computers. Use 0.1.3 or later.

### Added features
- First downloadable app: Windows setup and a Mac disk image.
- Sign in to your own Blackboard account and view courses, assignments, grades, calendar, and files.

### Bugfixes
- None in this release.

### Other changes
- None in this release.
