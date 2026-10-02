"""Parent-run migration: add wake defaults without altering approved desktop actions."""
import json
import os
from pathlib import Path
import shutil
import time

if os.getuid() != 0:
    raise SystemExit("Run as a parent administrator using sudo.")
from school_voice.policy import trusted_file, validate
target = trusted_file(Path("/etc/school-voice/policy.json"))
policy = json.loads(target.read_text())
if "wake_word" in policy:
    raise SystemExit("Wake settings already exist; edit them in the parent policy if needed.")
policy["wake_word"] = {"enabled": True, "phrase": "Hey Laya", "model_dir": "/opt/school-voice/models/wake", "threshold": .3, "silence_seconds": .9}
validate(policy)
shutil.copy2(target, target.with_name(f"policy.before-wake-{time.time_ns()}.json"))
temporary = target.with_suffix(".tmp")
temporary.write_text(json.dumps(policy, indent=2) + "\n")
temporary.chmod(0o644)
temporary.replace(target)
print("Wake enabled. Existing app and action permissions are unchanged.")
