"""Short local sounds; never generated speech or a network call."""
import threading


def chime(kind="ready"):
    def play():
        try:
            import numpy as np
            import sounddevice as sd
            rate = int(sd.query_devices(kind="output")["default_samplerate"])
            frequencies = {"ready": (660, 880), "done": (880,), "error": (330,)}[kind]
            notes = []
            for frequency in frequencies:
                t = np.arange(int(rate * .055)) / rate
                note = .07 * np.sin(2 * np.pi * frequency * t) * np.sin(np.pi * np.arange(len(t)) / len(t)) ** 2
                notes.append(note)
            sd.play(np.concatenate(notes).astype("float32"), rate, blocking=False)
        except Exception:
            pass  # Visual state remains available if the speakers are absent/muted.
    threading.Thread(target=play, name="school-voice-chime", daemon=True).start()
