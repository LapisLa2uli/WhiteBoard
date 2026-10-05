"""Release identity shared by the UI and both package builders."""
import json

APP_VERSION = "0.4.0"


def build_info():
    import data
    try:
        payload = json.loads((data.resource_root() / "build-info.json").read_text(encoding="utf-8"))
        return {"version": APP_VERSION, "revision": str(payload["revision"]), "platform": str(payload["platform"])}
    except (OSError, ValueError, KeyError, TypeError):
        return {"version": APP_VERSION, "revision": "development", "platform": "source"}
