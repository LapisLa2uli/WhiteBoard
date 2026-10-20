"""Run regressions without reading or changing the user's WhiteBoard profile."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='whiteboard-tests-') as directory:
    environment = dict(os.environ, WHITEBOARD_DATA_DIR=directory)
    for command in (
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
        ['node', '--check', 'static/app.js'],
        ['node', '--check', 'static/tabs.js'],
        ['node', 'tests/ui_state.cjs'],
        ['node', 'tests/grades_sort.cjs'],
        ['node', 'tests/session_lifecycle.cjs'],
        ['node', 'tests/login_progress.cjs'],
        ['node', 'tests/browser_notice.cjs'],
        ['node', 'tests/contents_search.cjs'],
        ['node', 'tests/color_picker.cjs'],
        ['node', 'tests/metadata_requests.cjs'],
    ):
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
