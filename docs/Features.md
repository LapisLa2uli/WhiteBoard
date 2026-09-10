# Features

How to reach each capability. For the control-by-control list, see [User Guide](User-Guide.md).

## Sign in and session

**What it does.** Opens a headless Chrome/Edge session to your school's Blackboard site, signs in with the username and password you type, then loads courses, calendar deadlines, assignment links, submission status, grades, announcements, and course-file metadata.

**How to access.** Launch WhiteBoard. The login card is the first screen if you are not signed in.

**Related**

- **Refresh** (top bar or Settings) reloads data. If Blackboard returned 401/403 or the session died, Refresh signs in again using the password still in RAM.
- **Log out** closes the browser session and forgets the in-memory password.
- Password is **never** written to disk. Username and school URL are.

## Home

**What it does.** Week-at-a-glance: unsubmitted deadlines in the next 7 days, plus a handful of recent grades.

**How to access.** Top bar → **Home** (house icon), or it opens automatically after a successful sign-in.

**Related.** Click a row for details; double-click to open in Blackboard. Countdown text updates every second. Card **border color** is how soon it is due; **fill color** is the course.

## Course list (left sidebar)

**What it does.** Lists your courses, search, activity window, and named custom filters (whitelists). Click a course to open its page.

**How to access.** Always visible after sign-in on the left.

**Related**

- **Activity** dropdown: only keep courses with recent grades/announcements/activity in the chosen window (1 week through 1 year, or any).
- **New** custom filter: name + check courses. Click a filter chip to turn it on or off. **X** deletes it (confirm dialog).
- **Hide assignments outside this filter:** Home, Assignments, Submitted, Grades, Contents, and Calendar hide work from courses not in the active filter.
- **Next launch, only load this filter:** the next Refresh/login fetches those courses only (faster, less complete).

## Course page

**What it does.** One course: upcoming work, grades, latest announcements, and a button to open the course on Blackboard.

**How to access.** Click a course in the left list, or follow the course name on an assignment detail page.

## Assignments

**What it does.** Unsubmitted work first (when filter is All), then submitted cards in gray. Search, status chips, overdue hiding, multi-select, ignore, and local “mark as submitted.”

**How to access.** Top bar → **Assignments**.

**Related.** Status chips: All / Todo / Submitted / Late. Overdue dropdown: show all, hide if >1 week late, hide if >1 month late. Ignore sends items to the Ignored list (local only). Mark as submitted is **local only** — it does not upload a file to Blackboard.

## Submitted

**What it does.** Work that already has a Blackboard submission, a grade, or your local submitted mark.

**How to access.** Top bar → **Submitted**.

## Ignored

**What it does.** Assignments you hid from the main lists. Restore one or several.

**How to access.** Top bar → **Ignored**.

## Assignment / deadline detail

**What it does.** Title, course link, due date, live countdown, status, grade if any, description if present, Open in Blackboard, Mark as submitted / Undo.

**How to access.** Click an assignment or calendar/home card. **Back** returns to the previous screen.

## Grades

**What it does.** Two folders: **Graded** (posted scores) and **Submitted, not graded**. Unsubmitted work is hidden here.

**How to access.** Top bar → **Grades**. Click a row to open the assignment or course.

## Contents (course files)

**What it does.** Browse course content trees. Metadata arrives with Refresh; file bytes download only when you click **Download**.

**How to access.** Top bar → **Contents**.

**Related.** Views: **Tree**, **Folder**, **Columns** (Finder-style). Checkboxes select files or whole folders. **Download** saves via a file/folder picker. **Open in browser** / the open-icon opens the Blackboard URL.

## Calendar

**What it does.** Upcoming deadlines grouped by day.

**How to access.** Top bar → **Calendar**. Chips switch the window: **7 / 14 / 30 days**.

## Settings

**What it does.** School URL, Refresh, clear snapshot cache, Log out, create Desktop / Search shortcuts.

**How to access.** Top bar → **Settings**.

## Shortcuts

**What it does.** Desktop shortcut plus Start menu (Windows Search) or Applications/Spotlight (macOS).

**How to access.** First sign-in on a packaged build that was **not** installed by the Windows setup, or **Settings → Add shortcuts…**. The Windows installer already writes those `.lnk` files.

## Open in Blackboard

**What it does.** Opens the assignment, test, or course in your normal browser so you can submit or read the official page.

**How to access.** Double-click most work cards, or the **Open in Blackboard** / **Open course in Blackboard** / **Open in browser** buttons.

## Privacy and local data

| Stored | Where |
|---|---|
| Username, URL, filters, ignored IDs, local submitted marks | `~/.blackboard_dashboard/settings.json` |
| Last snapshot (courses, grades, file names, …) | `~/.blackboard_dashboard/snapshot.json` |
| Password and cookies | Process memory only |

See [Installation](Installation.md) and the README for wiping that folder.
