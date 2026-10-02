from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time


def runtime_dir():
    base = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    info = base.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("A private XDG_RUNTIME_DIR is required")
    folder = base / "school-voice"
    folder.mkdir(mode=0o700, exist_ok=True)
    info = folder.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Voice runtime directory is not private")
    return folder


def send(path, command):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(1)
        client.connect(str(path))
        client.sendall(command.encode())


def serve(initial=None):
    folder = runtime_dir()
    lock = open(folder / "instance.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    from PySide6.QtCore import QTimer, QSocketNotifier
    from PySide6.QtWidgets import QApplication
    from .ui import VoiceWindow
    app = QApplication(["school-voice"])
    app.setDesktopFileName("school-voice")
    app.setQuitOnLastWindowClosed(False)
    path = folder / "control.sock"
    path.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_UNIX)
    listener.bind(str(path))
    path.chmod(0o600)
    listener.listen(4)
    listener.setblocking(False)
    window = VoiceWindow()
    QTimer.singleShot(0, window.initialize_voice)
    def receive():
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(.1)
            try:
                command = connection.recv(32).decode("ascii")
            except (TimeoutError, UnicodeError):
                return
        if command in ("command", "dictate"):
            window.toggle(command)
        elif command == "cancel":
            window.cancel()
        elif command == "show":
            window.show()
        elif command == "mute":
            window.toggle_mute()
    notifier = QSocketNotifier(listener.fileno(), QSocketNotifier.Type.Read)
    notifier.activated.connect(receive)
    app.aboutToQuit.connect(window.shutdown)
    if initial in ("command", "dictate"):
        QTimer.singleShot(0, lambda: window.toggle(initial))
    elif initial == "show":
        window.show()
    try:
        app.exec()
    finally:
        listener.close()
        path.unlink(missing_ok=True)
        lock.close()


def doctor():
    from .policy import load, trusted_file, catalog
    policy = load()
    for key in ("ca_file", "token_file"):
        trusted_file(Path(policy["server"][key]))
    model = Path(policy["whisper_model"])
    for name in ("model.bin", "config.json", "tokenizer.json"):
        trusted_file(model / name)
    if policy.get("wake_word", {}).get("enabled"):
        from .wake import MODEL_FILES
        for name in MODEL_FILES.values():
            trusted_file(Path(policy["wake_word"]["model_dir"]) / name)
        print("Wake phrase:", policy["wake_word"]["phrase"])
    for app in policy["apps"].values():
        trusted_file(Path(app["argv"][0]))
    for binary in ("hyprctl", "wpctl", "playerctl"):
        if not (Path("/usr/bin") / binary).is_file():
            raise ValueError("Missing desktop dependency: " + binary)
    import sounddevice as sd
    print("Microphone:", sd.query_devices(kind="input")["name"])
    print("Approved actions:", ", ".join(catalog(policy)))
    print("Local checks passed. Use a real voice command to test the paired Laya service.")


def main():
    parser = argparse.ArgumentParser(description="Local speech recognition and voice control for Omarchy")
    parser.add_argument("command", choices=["toggle", "dictate", "cancel", "show", "mute", "serve", "doctor"], nargs="?", default="show")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            return doctor()
        if args.command == "serve":
            return serve()
        command = "command" if args.command == "toggle" else args.command
        path = runtime_dir() / "control.sock"
        try:
            send(path, command)
            return
        except (FileNotFoundError, ConnectionRefusedError):
            if command == "cancel":
                return
        # Spawn once under a process lock; hotkey invocations do not compete for the mic.
        subprocess.Popen([sys.executable, "-I", "-m", "school_voice.cli", "serve"], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            time.sleep(.1)
            try:
                send(path, command)
                return
            except (FileNotFoundError, ConnectionRefusedError):
                continue
        raise ValueError("School Voice could not start. Run school-voice serve in a terminal for details.")
    except Exception as error:
        print(str(error), file=sys.stderr)
        if sys.platform == "linux" and Path("/usr/bin/notify-send").exists():
            subprocess.run(["/usr/bin/notify-send", "School Voice", str(error)[:300]], check=False)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
