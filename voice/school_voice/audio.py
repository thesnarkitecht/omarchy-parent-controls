"""Local-only audio capture, bounded in memory, never sent to Laya or saved."""
import os
import threading


class Recorder:
    def __init__(self, maximum=15):
        self.maximum = maximum
        self.stream = None
        self.blocks = []
        self.frames = 0
        self.rate = 0
        self.level = 0.0
        self.error = None
        self.lock = threading.Lock()

    def start(self):
        import sounddevice as sd
        import numpy as np
        self.blocks, self.frames, self.level, self.error = [], 0, 0.0, None
        self.rate = int(sd.query_devices(kind="input")["default_samplerate"])
        def callback(data, frames, timing, status):
            if status:
                self.error = "Microphone audio was interrupted. Please try again."
            with self.lock:
                remaining = self.maximum * self.rate - self.frames
                if remaining <= 0:
                    raise sd.CallbackStop
                chunk = data[:remaining, 0].copy()
                self.blocks.append(chunk)
                self.frames += len(chunk)
                self.level = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0
                if self.frames >= self.maximum * self.rate:
                    raise sd.CallbackStop
        self.stream = sd.InputStream(samplerate=self.rate, channels=1, dtype="float32", callback=callback)
        self.stream.start()

    def stop(self):
        import numpy as np
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        with self.lock:
            audio = np.concatenate(self.blocks) if self.blocks else np.array([], dtype="float32")
            self.blocks = []
        if self.error:
            raise ValueError(self.error)
        if len(audio) < self.rate // 4 or not len(audio) or np.max(np.abs(audio)) < .003:
            raise ValueError("I didn't hear speech. Try again a little closer to the microphone.")
        # Whisper accepts 16 kHz PCM. Prefer the microphone's native capture rate.
        import av
        frame = av.AudioFrame.from_ndarray(audio.reshape(1, -1), format="flt", layout="mono")
        frame.sample_rate = self.rate
        resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
        frames = resampler.resample(frame) + resampler.resample(None)
        return np.concatenate([f.to_ndarray().reshape(-1) for f in frames])

    def cancel(self):
        if self.stream:
            stream, self.stream = self.stream, None
            try:
                stream.abort()
            except Exception:
                pass  # A disconnected device may already have stopped.
            finally:
                try:
                    stream.close()
                except Exception:
                    pass
        with self.lock:
            self.blocks = []
            self.level = 0


class Transcriber:
    def __init__(self, model_path, vocabulary=""):
        self.path = model_path
        self.vocabulary = vocabulary
        self.model = None

    def transcribe(self, samples, command_mode=True):
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.path, device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
        segments, _ = self.model.transcribe(samples, language="en", beam_size=5, vad_filter=True,
                                            condition_on_previous_text=False, temperature=0,
                                            hotwords=self.vocabulary if command_mode else None)
        text = " ".join(s.text.strip() for s in segments if s.no_speech_prob < .6).strip()
        if not text:
            raise ValueError("I didn't catch that. Please try again.")
        if len(text) > 500:
            raise ValueError("Please use a shorter sentence.")
        return text
