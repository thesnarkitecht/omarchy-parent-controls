"""Root-run audio bridge check using an isolated virtual sink, never a real mic.

Exercises actual PulseAudio playback and capture through the installed proxy and
worker namespace. Does not change the desktop's default devices or permissions.
"""
import json
import os
import secrets
import subprocess
import sys

from integration_audio import worker_command

PROBE = r'''
import array, concurrent.futures, json, math, subprocess, sys, time
sink = sys.argv[1]
common = ['--raw', '--format=s16le', '--rate=16000', '--channels=1', '--latency-msec=50']
capture = subprocess.Popen(['/usr/bin/parec', *common, '--device=' + sink + '.monitor'], stdout=subprocess.PIPE)
pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
recording = pool.submit(capture.communicate)
try:
    time.sleep(.3)
    tone = array.array('h', (int(6000 * math.sin(2 * math.pi * 440 * n / 16000)) for n in range(16000)))
    subprocess.run(['/usr/bin/pacat', '--playback', *common, '--device=' + sink], input=tone.tobytes(), check=True, timeout=8)
    time.sleep(.3)
finally:
    capture.terminate()
raw, _ = recording.result(timeout=3)
pool.shutdown()
samples = array.array('h'); samples.frombytes(raw[:len(raw)//2*2])
assert len(samples) >= 16000, 'Capture stream did not deliver one second of audio'
peak = max(abs(v) for v in samples)
assert peak > 1000, 'Only silence came through the proxy'
# Detect the generated frequency rather than merely accepting arbitrary noise.
energy = sum(v*v for v in samples)
component = abs(sum(v * complex(math.cos(2*math.pi*440*n/16000), math.sin(2*math.pi*440*n/16000)) for n,v in enumerate(samples)))
assert component > 0.1 * math.sqrt(energy * len(samples)), 'Test tone did not survive the round trip'
print(json.dumps({'worker_playback_and_capture': True, 'captured_frames': len(samples), 'peak': peak, 'tone_hz': 440, 'physical_devices_used': False}))
'''


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo on the installed test computer.')
    sys.path.insert(0, '/usr/local/lib/omarchy-kids')
    from native_runtime import account
    child = account()
    desktop = ['/usr/bin/runuser', '-u', child['user'], '--', '/usr/bin/env',
               'XDG_RUNTIME_DIR=/run/user/' + str(child['uid']), '/usr/bin/pactl']
    sink = 'parent_controls_test_' + secrets.token_hex(4)
    module = subprocess.check_output(desktop + ['load-module', 'module-null-sink',
                                     'sink_name=' + sink, 'rate=16000', 'channels=1'], text=True).strip()
    try:
        result = subprocess.run(worker_command('/usr/bin/python3', '-c', PROBE, sink),
                                capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        print(result.stdout.strip())
    finally:
        subprocess.run(desktop + ['unload-module', module], check=True)


if __name__ == '__main__':
    main()
