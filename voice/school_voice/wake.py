"""On-device keyword spotting and end-of-speech capture; no network or audio files."""
from collections import deque
from pathlib import Path
import queue
import re
import tempfile
import threading

from .policy import trusted_file
from .capture import input_rate, input_stream

MODEL_FILES = {
    "encoder": "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "decoder": "decoder-epoch-12-avg-2-chunk-16-left-64.onnx",
    "joiner": "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "tokens": "tokens.txt",
    "bpe": "bpe.model",
    "vad": "silero_vad.onnx",
}


def strip_wake(text, phrase):
    words = phrase.split()
    # Whisper may spell this proper name phonetically. Only strip at the beginning.
    variants = [r"[\s,]+".join(re.escape(word) for word in words)]
    if phrase.casefold() == "hey laya":
        variants += [r"hey[ ,]+(?:leia|layer|layah|lay a)", r"(?:laya|leia)"]
    return re.sub(r"^\s*(?:" + "|".join(variants) + r")(?!\w)[\s,.!?;:]*", "", text, flags=re.I).strip()


class WakeCapture:
    """Pure capture state machine. Inputs are fixed 40 ms PCM frames.

    Keep one second in RAM to preserve words spoken immediately after the wake
    phrase. Require speech after a short wake-tail grace, then 0.9 s silence.
    """
    def __init__(self, silence_seconds=.9):
        self.state = "armed"
        self.pre = deque(maxlen=25)
        self.frames = []
        self.elapsed = 0.0
        self.speech = 0.0
        self.quiet = 0.0
        self.silence_seconds = silence_seconds

    def feed(self, frame, keyword=False, speech=False):
        if self.state == "done":
            return None
        if self.state == "armed":
            self.pre.append(frame)
            if keyword:
                self.state = "capture"
                self.frames = list(self.pre)
                self.pre.clear()
                return ("awake", None)
            return None
        self.frames.append(frame)
        self.elapsed += .04
        if self.elapsed >= .24:
            if speech:
                self.speech += .04
                self.quiet = 0
            else:
                self.quiet += .04
        if self.elapsed >= 15:
            self.state = "done"
            self.frames.clear()
            return ("timeout", "That command was too long. Nothing changed; try a shorter request.")
        if self.speech >= .16 and self.quiet >= self.silence_seconds:
            return self.finish()
        if self.elapsed >= 4 and self.speech < .16:
            self.state = "done"
            self.frames.clear()
            return ("timeout", None)
        return None

    def finish(self):
        if self.state != "capture":
            return None
        self.state = "done"
        frames, self.frames = self.frames, []
        return ("audio", frames) if self.speech >= .16 else ("timeout", None)

    def cancel(self):
        self.state = "done"
        self.frames.clear()
        self.pre.clear()


class Detector:
    def __init__(self, config, check=trusted_file):
        import sentencepiece
        import sherpa_onnx
        root = Path(config["model_dir"])
        paths = {key: str(check(root / name)) for key, name in MODEL_FILES.items()}
        tokenizer = sentencepiece.SentencePieceProcessor(model_file=paths["bpe"])
        tokens = tokenizer.encode(config["phrase"].upper(), out_type=str)
        if not tokens or "<unk>" in tokens:
            raise ValueError("The wake phrase contains words this model cannot represent")
        # Only text tokens, never recordings, are temporarily materialized for the
        # native library, which requires a keywords file at construction time.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as keyword_file:
            keyword_file.write(" ".join(tokens) + " @wake\n")
            keyword_file.flush()
            self.kws = sherpa_onnx.KeywordSpotter(
                tokens=paths["tokens"], encoder=paths["encoder"], decoder=paths["decoder"],
                joiner=paths["joiner"], keywords_file=keyword_file.name,
                num_threads=1, keywords_threshold=config.get("threshold", .3),
                keywords_score=1.5, num_trailing_blanks=1)
        self.stream = self.kws.create_stream()
        vad_config = sherpa_onnx.VadModelConfig()
        vad_config.silero_vad.model = paths["vad"]
        vad_config.silero_vad.threshold = .5
        vad_config.silero_vad.min_silence_duration = .1
        vad_config.silero_vad.min_speech_duration = .1
        vad_config.silero_vad.max_speech_duration = 15
        vad_config.sample_rate = 16000
        vad_config.num_threads = 1
        self.vad = sherpa_onnx.VoiceActivityDetector(vad_config, buffer_size_in_seconds=20)

    def feed(self, frame, detect_keyword=True):
        keyword = False
        if detect_keyword:
            self.stream.accept_waveform(16000, frame)
            while self.kws.is_ready(self.stream):
                self.kws.decode_stream(self.stream)
                if self.kws.get_result(self.stream):
                    keyword = True
                    self.kws.reset_stream(self.stream)
        self.vad.accept_waveform(frame)
        speech = self.vad.is_speech_detected()
        while not self.vad.empty():
            self.vad.pop()
        return keyword, speech


class WakeListener:
    def __init__(self, config, callback):
        self.config, self.callback = config, callback
        self.stopped = threading.Event()
        self.finish_requested = threading.Event()
        self.thread = None
        self.stream = None
        self.level = 0.0
        self.engine = WakeCapture(config.get("silence_seconds", .9))

    def start(self):
        self.thread = threading.Thread(target=self._run, name="school-voice-wake", daemon=True)
        self.thread.start()

    def finish(self):
        self.finish_requested.set()

    def stop(self):
        self.stopped.set()
        stream = self.stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

    def _run(self):
        result = None
        try:
            import av
            import numpy as np
            detector = Detector(self.config)
            if self.stopped.is_set():
                return
            frames = queue.Queue(maxsize=20)
            overflow = threading.Event()
            rate = input_rate()
            resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
            pending = np.empty(0, dtype="float32")
            def capture(data, count, timing, status):
                if status:
                    overflow.set()
                try:
                    frames.put_nowait(data[:, 0].copy())
                except queue.Full:
                    overflow.set()
            with input_stream(samplerate=rate,
                                blocksize=max(1, int(rate * .04)), callback=capture) as stream:
                self.stream = stream
                if self.stopped.is_set():
                    return
                self.callback("armed", None)
                while not self.stopped.is_set():
                    if overflow.is_set():
                        raise ValueError("Microphone audio was interrupted. Wake listening stopped; use Resume microphone to retry.")
                    if self.finish_requested.is_set():
                        result = self.engine.finish()
                        break
                    try:
                        data = frames.get(timeout=.1)
                    except queue.Empty:
                        if not stream.active:
                            raise ValueError("The microphone disconnected. Wake listening stopped.")
                        continue
                    frame = av.AudioFrame.from_ndarray(data.reshape(1, -1), format="flt", layout="mono")
                    frame.sample_rate = rate
                    for resampled in resampler.resample(frame):
                        pending = np.concatenate((pending, resampled.to_ndarray().reshape(-1)))
                    while len(pending) >= 640 and not self.stopped.is_set():
                        chunk, pending = pending[:640], pending[640:]
                        self.level = float(np.sqrt(np.mean(chunk ** 2)))
                        keyword, speech = detector.feed(chunk, self.engine.state == "armed")
                        event = self.engine.feed(chunk.copy(), keyword, speech)
                        if event:
                            if event[0] == "awake":
                                self.callback(*event)
                            else:
                                result = event
                                break
                    if result:
                        break
            self.stream = None
            if result and not self.stopped.is_set():
                kind, payload = result
                if kind == "audio":
                    payload = np.concatenate(payload)
                self.callback(kind, payload)
        except Exception as error:
            if not self.stopped.is_set():
                self.callback("error", str(error))
        finally:
            self.stream = None
            self.engine.cancel()
