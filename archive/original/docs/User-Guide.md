# User Guide

This page lists **every screen and control**. Feature summaries: [Features](Features.md). Installers: [Installation](Installation.md).

Legend used on assignment-style cards (Home, Assignments, Calendar, course pages):

- **Border color** = how soon it is due (overdue, today, 3 days, this week, later).
- **Fill color** = which course.
- **Single click** = open details (or toggle selection in Select mode).
- **Double click** = open the item on Blackboard in your browser.
- **Countdown** (for todo/late items) ticks every second.

“Mark as submitted” and **Ignore** are **local flags**. They do not submit a file or change Blackboard.

---

## Login

Shown when you are signed out.

| Control | What it does |
|---|---|
| **School URL** | Blackboard site, for example `https://shs.blackboardchina.cn`. Required. Saved when you sign in or when you change it in Settings. |
| **Username** | Your Blackboard username. Saved in settings. |
| **Password** | Hidden by default. The eye icon reveals it. **Never saved to disk.** Kept in memory until Log out so Refresh can re-sign-in. |
| **Sign in** | Starts login and the loading screen. Disabled while busy. Enter in any field also submits. |
| **Cancel** | Appears while login is running. Stops the attempt, closes the browser session, returns to login with “Sign-in cancelled.” |
| Progress ring / status text | Shows opening, waiting, success, or the error (wrong password, missing Chrome/Edge, bad URL, network). |

---

## Loading

Shown during first login and during **Refresh**.

| Control | What it does |
|---|---|
| Progress bar + percent | How far the current fetch has gotten. |
| Status line | Short message (signing in, loading a course name, ready). Long course names are truncated so the percent stays visible. |
| **Cancel** | During **login**: abort and return to the login screen. During **refresh**: abort the fetch and return to the page you were on; existing snapshot stays. |

---

## Top bar (after sign-in)

The white strip at the top of every dashboard page.

| Control | What it does |
|---|---|
| Logo | Branding only. |
| **Home** | Opens the week overview. |
| **Assignments** | Opens the main work list. |
| **Submitted** | Opens submitted / graded / locally marked work. |
| **Ignored** | Opens assignments you hid. |
| **Grades** | Opens graded and pending-grade folders. |
| **Contents** | Opens the course file browser. |
| **Calendar** | Opens the calendar (list, week, or month). |
| **Settings** | Opens URL, cache, logout, shortcuts. |
| “Updated …” text | When the snapshot was last fetched. |
| Your name | Profile name from Blackboard, if loaded. |
| **Refresh** | Reloads from Blackboard. Disabled while a fetch is running. If the session expired and the password is still in memory, signs in again instead of showing empty data. |
| **Log out** | Closes the browser session, drops the in-memory password, returns to login. Username and URL stay saved. |

A thin progress bar appears under the top bar while Refresh is running. A red banner appears if the last refresh failed.

---

## Left sidebar (“Your courses”)

| Control | What it does |
|---|---|
| **Search courses** | Filters the list as you type (name, term, instructor). |
| **Activity** dropdown | **Any activity**, **Past 1 week**, **1 month**, **3 months**, **6 months**, **1 year**. Courses without activity in that window are treated as filtered out. |
| **Custom filters** label | Section heading. |
| **New** | Dialog: filter name + a checkbox per course. **Save** creates and turns the filter on. **Cancel** closes without saving. At least one course and a name are required. |
| Filter chip (name) | Click to **activate** that whitelist, or click again to **deactivate**. Active chip is highlighted. |
| **X** (delete filter) | Asks **Delete filter?** — **Cancel** or **Delete**. Delete cannot be undone. |
| **Hide assignments outside this filter** | When checked, Home, Assignments, Submitted, Grades, Contents, and Calendar hide items whose course is filtered out. The sidebar still lists filtered-out courses as dimmed “Filtered out” rows when you are searching. |
| **Next launch, only load this filter** | Stores the visible course IDs. The next login/Refresh fetches **only** those courses (less data, faster). Uncheck to load everything again on the next refresh. |
| Course row | Opens that course’s page. Color matches assignment cards for the same course. |

If nothing matches: “No matching courses” or “No courses in this filter.”

---

## Home

| Control | What it does |
|---|---|
| Error banners | Shown per failed slice (Ultra pages, profile, deadlines, grades, courses, refresh). |
| Deadline legend | Explains border colors. |
| Upcoming row | Click → assignment or course detail. Double-click → Blackboard. Shows due time, course, countdown, kind chip (assignment / test / other). |
| **Refresh** (empty state) | Same as top-bar Refresh when the list is empty. |
| Recent grade row | Click → assignment or course. Shows title, course, score. |

---

## Assignments

| Control | What it does |
|---|---|
| **Search assignments** | Filters by title as you type. |
| Chip **All** | Foldable **To do** and **Submitted** groups. Submitted cards are gray. |
| Chip **Todo** | Not submitted, not late. |
| Chip **Submitted** | Has a Blackboard submission, a grade, or your local mark. |
| Chip **Late** | Past due and not treated as submitted. |
| **Overdue work** dropdown | **Show all overdue** / **Hide if over 1 week late** / **Hide if over 1 month late**. |
| **Select** / **Done selecting** | Turns checkboxes on each card on or off. In Select mode, clicking a card toggles its checkbox instead of opening details. |
| **Select all** | Checks every visible card. |
| **Ignore selected (N)** | Moves checked items to Ignored (local). |
| **Mark submitted (N)** | Local submitted mark on checked items that are not already submitted. |
| Checkmark icon (**Mark as submitted**) | Local mark for that one card. |
| Undo icon (**Undo submitted mark**) | Removes **your** local mark only (not a real Blackboard submission). |
| Eye-off icon (**Ignore**) | Hides that assignment on Assignments / Home lists. |
| Assignment card | Click → detail. Double-click → Blackboard. Gray + dimmed = submitted. |

---

## Submitted

Same card interactions as Assignments, without the All/Todo/Late chips and without the overdue dropdown. The list is forced to submitted items. Ignore and local mark/undo still appear where they apply.

---

## Ignored

| Control | What it does |
|---|---|
| Search | Same as Assignments. |
| **Select** / **Done selecting** | Multi-select. |
| **Select all** | Checks visible ignored items. |
| **Restore selected (N)** | Puts checked items back on Assignments. |
| Eye icon (**Restore**) | Restores that one item. |
| Card click / double-click | Detail / Blackboard, unless Select mode is on. |

---

## Assignment detail

| Control | What it does |
|---|---|
| **Back** | Previous screen (or the parent list). |
| **Course** (name button) | Opens that course page. |
| Due / Time left / Status / Grade | Read-only. Time left is a live countdown for todo/late. |
| Description card | Shown when Blackboard provided text. |
| **Open in Blackboard** | Browser to the assignment/test. |
| **Mark as submitted** | Local flag. |
| **Undo submitted mark** | Clears your local flag. |
| Card double-click | Same as Open in Blackboard. |

If the item is only a calendar deadline (not a full assignment record), you still get when, course, type chip, countdown, Open, and mark/undo.

**Item not found:** Back plus a note that it is missing from the current snapshot — use Refresh.

---

## Course page

| Control | What it does |
|---|---|
| **Back** | Previous screen. |
| Upcoming work cards | Click → assignment detail. Double-click → Blackboard. |
| Grade rows | Title and score (read-only on this page). |
| Announcement cards | Title and body or date (up to five). |
| **Open course in Blackboard** | Course home in the browser. |

**Course not found:** Back; the id is not in the snapshot.

---

## Grades

| Control | What it does |
|---|---|
| **Graded** folder | Expand/collapse posted scores. Click a row → assignment or course. |
| **Submitted, not graded** folder | Expand/collapse work waiting for a score. Click a row → assignment or course. |
| Empty **Refresh** | Top-bar Refresh when both folders are empty. |

---

## Contents

File **names and folders** load with Refresh. **Bytes** download only when you choose Download.

| Control | What it does |
|---|---|
| **Tree** | Nested expand/collapse list (default). |
| **Folder** | One folder at a time, with breadcrumbs. |
| **Columns** | Up to three Miller columns (parent \| current \| child). |
| **Download** | Enabled when something is selected. One file → Save dialog. Several files → choose a folder. Needs an active signed-in session. |
| **Open in browser** | Opens each selected item’s Blackboard URL. |
| Selection count | How many items are checked. |
| **Courses** breadcrumb / **Up** arrow | Folder and Columns: go to parent or a specific ancestor. Disabled at the root. |
| Folder name / folder icon | Opens that folder (Folder/Columns) or is paired with the chevron in Tree. |
| Chevron (Tree) | Expand or collapse a course or folder. |
| Checkbox on a file | Select/deselect for Download or Open. |
| Checkbox on a folder | Select/deselect **all files** under it. Course rows have no checkbox. |
| Open-in-new-tab icon | Opens that one file in the browser. |

Respects the sidebar filter when **Hide assignments outside this filter** is on.

---

## Calendar

| Control | What it does |
|---|---|
| **List** / **Week** / **Month** | List is the day-by-day agenda. Week and month are 7-column grids (Monday first). |
| **Today** | Jumps to today. |
| Previous / next arrows | List: move by the selected day range. Week: previous/next week. Month: previous/next month. |
| **7 days** / **14 days** / **30 days** | List view only. How far ahead to list. Default 14. |
| Day headings (list) | Groups items by date. |
| Item card / event chip | Click → assignment, course, or Blackboard. Double-click a list card → Blackboard. Gray = completed assignment. |

---

## Settings

| Control | What it does |
|---|---|
| **Blackboard base URL** | Saved when you leave the field or press Enter. Used for the next login/Refresh. |
| Last-updated line | Same timestamp as the top bar. |
| **Refresh now** | Same as top-bar Refresh. |
| **Clear cached snapshot** | Deletes `snapshot.json`. Settings (filters, ignored list, URL, username) stay. |
| **Log out** | Same as top-bar Log out. |
| **Add shortcuts…** | Dialog (see below). Status text reports success or the error. |

Privacy note on this page: personal use, do not republish course materials, cookies not written to disk.

---

## Dialogs

### Add shortcuts? / Create shortcuts

Shown on first packaged launch (unless the Windows installer already placed shortcuts) or from Settings.

| Control | What it does |
|---|---|
| **Desktop shortcut** checkbox | Windows: `Desktop\WhiteBoard.lnk`. macOS: Desktop alias/symlink to the `.app`. |
| **Start menu (Windows Search)** or **Applications folder (Spotlight search)** | Windows Start Menu `.lnk`; macOS copy/symlink under `~/Applications`. |
| **Not now** | Closes. On first run, will not ask again. |
| **Add shortcuts** | Creates the checked items. |

### New course filter

| Control | What it does |
|---|---|
| **Filter name** | Required. |
| Course checkboxes | Required: at least one. |
| **Cancel** | Close. |
| **Save** | Create and activate. |

### Delete filter?

**Cancel** or **Delete**.

---

## Keyboard and window

There is no custom shortcut map beyond ordinary text-field behavior (Enter submits login and some fields). The window defaults to 1240×780 with a minimum of 980×620.

---

## If something goes wrong

| Symptom | What to try |
|---|---|
| “Not supported on this Mac” | You opened the Apple Silicon `.dmg` on an Intel Mac. Use `*-macOS-Intel.dmg`. |
| Developer cannot be verified | Control-click the app → Open. |
| Could not start a browser | Install Microsoft Edge or Google Chrome, then reopen WhiteBoard. From source, you can instead run `python -m playwright install chromium`. |
| Empty dashboard after idle | Click **Refresh**. WhiteBoard re-signs in if the password is still in memory; otherwise Log out and Sign in. |
| Contents Download fails | Stay signed in, then try again. Links with no file skip download. |
| Wrong courses | Clear the Activity dropdown, turn off the custom filter chip, uncheck “only load this filter,” then Refresh. |
