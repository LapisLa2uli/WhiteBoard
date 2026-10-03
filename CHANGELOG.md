# Changelog

Summarized major changes for each WhiteBoard release, compared with the version before it.
Write for someone using the app, not for developers. Every version needs the three
headings below. Packaging and GitHub Releases copy this text.

## [0.4.0] - 2026-10-02

### Added features
- The Assignments tab shows a red badge with how many items are still to do. The number can grow to four digits without pushing the other tabs aside.
- You can leave old assignments off the lists: skip work due more than a week, a month, three months, six months, or a year ago, or before a date you choose. The next refresh does not load those old items.
- Assignments has **Mark late as submitted**. It asks you to confirm, then marks every overdue assignment that is still to do.
- Contents can search for a folder name, a file name, or a file extension.
- The calendar list and the assignment list put the soonest due date first.
- **Open** sits on each assignment card, next to **Mark submitted** and **Ignore**. It opens that Blackboard page in a WhiteBoard window with tabs.
- Settings has a **Font** choice: Segoe UI, Calibri, Candara, Constantia, Cambria, Georgia, Verdana, Trebuchet MS, or Arial.
- Recent grades on Home use the same course color as the assignment cards.
- Assignment names, dates, and course names are larger. The countdown and buttons sit under that text.
- The Windows setup asks whether to add a Desktop shortcut and a Windows Search shortcut. You can turn either one off.
- Settings lets you choose how many rows appear on one page, change deadline and course colors, and send deadlines to a Google calendar named WhiteBoard.
- While signing in or refreshing, the loading screen shows how many courses, folders, and files it has read, and the latest item.

### Bugfixes
- Opening an assignment stays on that assignment. It no longer drops you on the Blackboard home page.
- Homework stays an assignment when the title also contains a word such as holiday, as long as it has a due date and a submission page.
- Submitted work no longer shows an overdue countdown. It shows that it was submitted, the time WhiteBoard recorded when you marked it, and how long it has been since the deadline.
- Marking an assignment submitted stays marked after you filter that course out and turn the filter back on.
- Course filters and the main list buttons respond again.
- Home and the course filters use less of the computer while you are looking at them.

### Other changes
- There is no separate Submitted tab. Submitted work is a foldable group on Assignments.
- The app opens on the sign-in page. It does not reopen a dashboard saved by the previous WhiteBoard.
- Your courses are stored in `%USERPROFILE%\.whiteboard_slim`. The previous app’s files are left where they were.
- Microsoft Edge is required. You do not need a separate Chrome install.
- The Windows download is named `WhiteBoard-<version>-Setup.exe`.
- Opening an assignment from the calendar, then going back, returns to the same list, week, or month.

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
