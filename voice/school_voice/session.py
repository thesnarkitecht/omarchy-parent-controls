import os
import re
import subprocess


def is_locked():
    """No wake microphone or pending action across a locked/unknown login session."""
    def query(*args):
        return subprocess.check_output(["/usr/bin/loginctl", *args], timeout=.7, stderr=subprocess.DEVNULL, text=True).strip()
    try:
        session = os.environ.get("XDG_SESSION_ID") or query("show-user", str(os.getuid()), "-p", "Display", "--value")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session):
            return True
        return query("show-session", session, "-p", "LockedHint", "--value") != "no"
    except (OSError, subprocess.SubprocessError):
        return True
