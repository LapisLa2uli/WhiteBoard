# WhiteBoard

WhiteBoard is a personal desktop dashboard for your own Blackboard account. It opens in its own window, signs in to Blackboard, and shows courses, assignments, grades, the calendar, and course files.

The current app is the repository root. The previous Flet app is archived in [`archive/original`](archive/original).

Sign in with your school URL, username, and password. The app is for your own account only. Follow your school's rules for automated access. Course materials stay on Blackboard; do not republish them.
## Run it
### Windows
You need Windows and Python 3.10 or newer. WebView2, which ships with Microsoft Edge, is used for the window and for Blackboard. No extra packages are required.

```
python run.py
```

That opens the WhiteBoard window and creates a Desktop shortcut and a Start menu entry named **WhiteBoard**, so Windows Search can find it.

Your courses stay in `%USERPROFILE%\.whiteboard_slim`. The archived app used a different folder and is not read.

### macOS
Open the `.dmg` and Control-click → “Open” to run WhiteBoard. 
- Drag it along the arrow to the Applications folder to install. 
- You can, however, run it directly from the DMG (or anywhere else). 
- No dependencies required beyond a functioning macOS system.

Your courses stay in `~/.config/whiteboard`. 

Accounts keep separate saved data. Use **Account → Sign out** to clear the session and choose whether to retain an offline dashboard. Passwords are not saved; session credentials use Windows DPAPI or macOS Keychain.

## Development and release checks

Run `python tools/test.py` for isolated regressions (Python 3.12 and Node.js), and `python tools/benchmark_loading.py` to compare loading strategies with synthetic data. Build instructions and signing requirements are in [packaging/README.md](packaging/README.md). Implementation results and remaining platform acceptance checks are in [IMPLEMENTATION_0.4.0.md](IMPLEMENTATION_0.4.0.md).

## Dashboard

WhiteBoard returns to sign-in when Blackboard confirms that your session has expired. While the dashboard is open, it checks the school session once a minute and when you return to the window. Offline copies are exempt; network failures alone do not sign you out.

Signing out stops the current refresh and clears its progress, partial dashboard, and error messages. A new sign-in starts with fresh status; late responses from the previous session are ignored.

Home separates this week's assignments and events into their own lists. Entries whose submission type is still being verified appear under **Checking type** until refresh confirms their type. Course filters apply to all three lists.

Events leave Home at their scheduled start time (midnight for all-day events). The open dashboard updates automatically; event history remains in Calendar and overdue assignments stay visible.

In Grades, **Sort grades by** orders each graded/pending list by name, course, or deadline in either direction. The default is newest deadline first. Missing deadlines stay last; posted dates are shown separately and are never used as substitute deadlines. Your selection lasts for the current session and works with search, course filters, and pagination.

## Refreshing course content

Refresh checks a compact list of course content and reuses saved file details when their revisions match. New or changed items are loaded again; grades, deadlines, and submission status still refresh independently. **Settings → Storage and refresh → Full refresh** rechecks file details immediately. They are also rechecked daily.

Files missing from two complete course checks are removed locally. Inaccessible or failed listings preserve saved files and show a notice in Contents. This detects content no longer visible to your account; it cannot distinguish deletion from changed permissions. See [incremental refresh implementation and tests](INCREMENTAL_REFRESH.md).

Contents also checks missing file sizes without reading file bodies. The first size check for a large account takes extra time; subsequent refreshes reuse those sizes. Hover over a displayed size for the exact byte count. A dash means Blackboard did not provide a verifiable size.

In Contents, type a search to reveal **Only this folder** and **Course filter**. Choose **Only selected courses** to whitelist results, or **Exclude selected courses** to hide courses from results. Click **Course** or **Date uploaded** in the results header to switch sort direction; × clears the search and keeps your browsing location. Upload dates use the creation timestamp when available.

Use **Settings → Colors → Change** for the gradient picker. Choose a hue, click or drag on the gradient, or enter a six-digit HEX code. The preview and sliders stay synchronized. Arrow keys adjust the gradient; Shift uses larger steps. Changes are saved only when you choose **Use this color**.
