"""User preferences may reduce listening, never expand parent permissions."""
import json
import os
from pathlib import Path


class Preferences:
    def __init__(self, path=None):
        self.path = path or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "school-voice/preferences.json"

    def read(self):
        try:
            data = json.loads(self.path.read_text())
            return {"muted": data.get("muted") is True, "wake_paused": data.get("wake_paused") is True}
        except FileNotFoundError:
            return {"muted": False, "wake_paused": False}
        except (ValueError, OSError, AttributeError):
            return {"muted": True, "wake_paused": True}

    def save(self, muted, wake_paused):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"muted": bool(muted), "wake_paused": bool(wake_paused)}))
        temporary.chmod(0o600)
        temporary.replace(self.path)
