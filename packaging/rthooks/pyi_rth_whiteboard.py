"""Mark the frozen process as a packaged Flet/Playwright app before imports run."""

import os

os.environ.setdefault("FLET_APP_PACKAGED", "1")
# Playwright looks inside its own package for browsers when this is "0".
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
