"""Mark the frozen process as a packaged Flet app before Flet starts."""

import os

os.environ.setdefault("FLET_APP_PACKAGED", "1")
