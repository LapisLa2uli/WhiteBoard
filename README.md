# WhiteBoard

WhiteBoard is a personal desktop dashboard for your own Blackboard account. It opens in its own window, signs in to Blackboard, and shows courses, assignments, grades, the calendar, and course files.

The current app is the repository root. The previous Flet app is archived in [`archive/original`](archive/original).

## Run it

You need Windows and Python 3.10 or newer. WebView2, which ships with Microsoft Edge, is used for the window and for Blackboard. No extra packages are required.

```
python run.py
```

That opens the WhiteBoard window and creates a Desktop shortcut and a Start menu entry named **WhiteBoard**, so Windows Search can find it.

Sign in with your school URL, username, and password. Your courses stay in `%USERPROFILE%\.whiteboard_slim`. The archived app used a different folder and is not read.

The app is for your own account only. Follow your school's rules for automated access. Course materials stay on Blackboard; do not republish them.
