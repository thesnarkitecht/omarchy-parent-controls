"""Bounded, local microphone transport; PulseAudio on Omarchy/PipeWire.

Avoid PortAudio's ALSA compatibility path on Linux. The desktop's Pulse service
negotiates the requested sample rate and delivers actual 16 kHz mono PCM.
"""
import os
import subprocess
import sys
import threading


class CaptureStopped(Exception):
    pass


def input_rate():
    if sys.platform == 'linux':
        return 16000
    import sounddevice as sd
    return int(sd.query_devices(kind='input')['default_samplerate'])


def default_source():
    source = subprocess.run(['/usr/bin/pactl', 'get-default-source'], check=True,
                            capture_output=True, text=True, timeout=3).stdout.strip()
    if not source or len(source) > 1024 or '\n' in source:
        raise ValueError('Select a microphone in desktop sound settings.')
    return source


def input_stream(*, callback, samplerate, blocksize=0):
    if sys.platform == 'linux':
        if samplerate != 16000:
            raise ValueError('Linux voice capture requires 16 kHz PCM.')
        return PulseInput(callback, blocksize or 640)
    import sounddevice as sd
    def forward(*args):
        try:
            callback(*args)
        except CaptureStopped:
            raise sd.CallbackStop
    return sd.InputStream(samplerate=samplerate, channels=1, dtype='float32',
                          blocksize=blocksize, callback=forward)


class PulseInput:
    def __init__(self, callback, blocksize=640):
        if not 1 <= blocksize <= 16000:
            raise ValueError('Invalid audio block size.')
        self.callback, self.blocksize = callback, blocksize
        self.process = self.thread = None
        self.stopped = threading.Event()
        self.error = None

    @property
    def active(self):
        return (not self.stopped.is_set() and self.process is not None
                and self.process.poll() is None)

    def start(self):
        import numpy as np
        self.numpy = np
        if self.process is not None:
            raise ValueError('Microphone capture has already started.')
        # Resolve the current desktop selection explicitly. Pulse stream-restore
        # can otherwise reconnect an application to an obsolete input device.
        source = default_source()
        self.process = subprocess.Popen([
            '/usr/bin/parec', '--raw', '--format=float32le', '--rate=16000',
            '--channels=1', '--latency-msec=50', '--client-name=Omarchy Voice',
            '--stream-name=Local voice capture', '--device=' + source],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.thread = threading.Thread(target=self._read, name='voice-pulse-input', daemon=True)
        self.thread.start()
        return self

    def _read(self):
        np = self.numpy
        pending = bytearray()
        size = self.blocksize * 4
        try:
            while not self.stopped.is_set():
                chunk = os.read(self.process.stdout.fileno(), size - len(pending))
                if not chunk:
                    if not self.stopped.is_set():
                        raise ValueError('The microphone disconnected. Select an input and try again.')
                    break
                pending.extend(chunk)
                if len(pending) == size:
                    data = np.frombuffer(pending, dtype='<f4').copy().reshape(-1, 1)
                    pending.clear()
                    self.callback(data, self.blocksize, None, False)
        except CaptureStopped:
            pass
        except Exception as error:
            if not self.stopped.is_set():
                self.error = str(error)
                self.callback(np.empty((0, 1), dtype='float32'), 0, None, True)
        finally:
            self.stopped.set()
            self._terminate()
            self.process.stdout.close()

    def _terminate(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)

    def stop(self):
        self.stopped.set()
        self._terminate()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

    abort = close = stop

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()
