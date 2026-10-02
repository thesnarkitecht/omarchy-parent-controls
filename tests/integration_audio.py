"""On an installed Omarchy test machine: sudo python3 tests/integration_audio.py.

Checks real worker access to audio devices with /run/user hidden. Reads device
metadata only: this does not record the microphone or play a test sound.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess


def is_microphone(source):
    """Recognize pactl's named monitor_source and older indexed schemas."""
    properties = source.get('properties', {})
    if properties.get('device.class') == 'monitor' or source.get('name', '').endswith('.monitor'):
        return False
    if 'monitor_source' in source:
        return source['monitor_source'] in (None, '')
    if 'monitor_of_sink' in source:
        return source['monitor_of_sink'] in (None, 4294967295, '4294967295')
    return properties.get('media.class') in ('Audio/Source', 'Audio/Source/Virtual')


def worker_command(*arguments):
    unit = 'omarchy-kids-audio-check-' + secrets.token_hex(4)
    command = ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--collect', '--unit=' + unit,
               '--property=User=omarchy-kids', '--property=Group=omarchy-kids',
               '--property=RuntimeDirectory=' + unit, '--property=RuntimeDirectoryMode=0700',
               '--property=NoNewPrivileges=yes', '--property=CapabilityBoundingSet=',
               '--property=ProtectSystem=strict', '--property=ProtectHome=yes',
               '--property=PrivateTmp=yes', '--property=InaccessiblePaths=/run/user',
               '--property=RuntimeMaxSec=15', '--property=TimeoutStopSec=2',
               '--property=BindReadOnlyPaths=/run/omarchy-kids-audio/native:/run/' + unit + '/pulse-native',
               '--setenv=HOME=/var/lib/omarchy-kids/data', '--setenv=XDG_RUNTIME_DIR=/run/' + unit,
               '--setenv=PULSE_SERVER=unix:/run/' + unit + '/pulse-native',
               '--setenv=PULSE_CLIENTCONFIG=/usr/local/lib/omarchy-kids/pulse-client.conf',
               *arguments]
    return command


def query(*arguments):
    return subprocess.run(worker_command('/usr/bin/pactl', *arguments), check=True,
                          capture_output=True, text=True, timeout=20).stdout


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run this diagnostic with sudo and the parent PIN while the child is logged in.')
    if not Path('/usr/bin/pactl').is_file():
        raise SystemExit('Install the libpulse tools first.')
    query('info')
    sinks = json.loads(query('--format=json', 'list', 'sinks'))
    sources = json.loads(query('--format=json', 'list', 'sources'))
    assert sinks, 'The desktop audio service has no playback devices.'
    assert sources, 'The desktop audio service has no input/monitor devices.'
    microphones = [s for s in sources if is_microphone(s)]
    print(json.dumps({'worker_connected': True, 'playback_devices': len(sinks),
                      'input_or_monitor_devices': len(sources), 'non_monitor_inputs': len(microphones)}))
    if not microphones:
        raise SystemExit('Audio transport works, but no microphone input was reported. Check the desktop input device.')
    print('Device enumeration passed. Next verify audible web playback, a site microphone permission, and local dictation.')


if __name__ == '__main__':
    main()
