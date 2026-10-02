import json
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download

root = Path("/opt/school-voice/models/whisper")
root.mkdir(parents=True, exist_ok=True)
revision = HfApi().model_info("Systran/faster-whisper-base.en").sha
snapshot_download("Systran/faster-whisper-base.en", revision=revision, local_dir=str(root),
                  allow_patterns=["*.json", "*.bin", "*.txt"])
(root / "revision.json").write_text(json.dumps({"repository": "Systran/faster-whisper-base.en", "revision": revision}, indent=2))
