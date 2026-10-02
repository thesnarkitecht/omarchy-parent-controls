"""Download pinned model bytes. Extract named regular files only; never unpack paths."""
import argparse
import hashlib
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

NAME = "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
ARCHIVE_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/" + NAME + ".tar.bz2"
ARCHIVE_SHA = "f170013b4716e41b62b9bfd809687c207cef798ef9bc6534d524e17af9b6561a"
VAD_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx"
VAD_SHA = "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6"
FILES = ["encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx", "decoder-epoch-12-avg-2-chunk-16-left-64.onnx",
         "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx", "bpe.model", "tokens.txt"]


def download(url, destination, expected, limit):
    total = 0
    digest = hashlib.sha256()
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise ValueError("Unexpectedly large model download")
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("Model checksum mismatch; nothing installed")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--destination", type=Path, default=Path("/opt/school-voice/models/wake"))
    args = p.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        archive, vad = root / "wake.tar.bz2", root / "silero_vad.onnx"
        download(ARCHIVE_URL, archive, ARCHIVE_SHA, 25_000_000)
        download(VAD_URL, vad, VAD_SHA, 5_000_000)
        with tarfile.open(archive) as tf:
            for filename in FILES:
                item = tf.getmember(NAME + "/" + filename)
                if not item.isfile() or item.size > 20_000_000:
                    raise ValueError("Unexpected model archive entry")
                with tf.extractfile(item) as source, (root / filename).open("wb") as output:
                    shutil.copyfileobj(source, output)
        args.destination.mkdir(parents=True, exist_ok=True, mode=0o755)
        for filename in [*FILES, "silero_vad.onnx"]:
            target = args.destination / filename
            shutil.copyfile(root / filename, target)
            target.chmod(0o644)
        (args.destination / "SOURCES.txt").write_text(ARCHIVE_URL + "\nSHA256 " + ARCHIVE_SHA + "\n" + VAD_URL + "\nSHA256 " + VAD_SHA + "\n")
    print("Installed local wake and voice-activity models in", args.destination)


if __name__ == "__main__":
    main()
