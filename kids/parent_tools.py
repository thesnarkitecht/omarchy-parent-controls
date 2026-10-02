"""Open fixed Omarchy parent tools without installing anything implicitly."""
import os
from pathlib import Path
import subprocess
import sys

TOOLS = {'agent', 'hermes-repair', 'windows-install', 'windows-launch'}

def ensure_windows_stopped():
    if not Path('/usr/bin/docker').is_file():
        return
    try:
        result = subprocess.run(['/usr/bin/docker','--host=unix:///run/docker.sock',
                                 'inspect','--format={{.State.Running}}','omarchy-windows'],
                                capture_output=True,text=True,timeout=5)
    except subprocess.TimeoutExpired:
        raise ValueError('Could not check Windows. Shut it down before turning controls on.')
    if result.returncode == 0 and result.stdout.strip() == 'true':
        raise ValueError('Shut down Windows before turning controlled mode on.')

def launch(tool):
    if tool not in TOOLS:
        raise ValueError('Unknown parent tool.')
    if Path('/etc/omarchy-kids/controlled-on').exists():
        raise ValueError('Turn controlled mode off before opening parent tools.')
    if tool == 'agent':
        command = ['/usr/bin/omarchy','menu','summon','setup.default.agent']
    elif tool == 'hermes-repair':
        command = ['/usr/bin/omarchy-launch-floating-terminal-with-presentation',
                   '/usr/bin/sudo /usr/bin/python3 -I /usr/local/lib/omarchy-kids/hermes_install.py']
    else:
        command = ['/usr/bin/omarchy-launch-floating-terminal-with-presentation',
                   '/usr/bin/python3 -I /usr/local/lib/omarchy-kids/parent_tools.py ' + tool]
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)

def windows(tool):
    if tool not in ('windows-install', 'windows-launch'):
        raise ValueError('Unknown Windows action.')
    if Path('/etc/omarchy-kids/controlled-on').exists():
        raise ValueError('Turn controlled mode off before opening Windows.')
    # Only this tool uses the adapter. No global pkexec/polkit rules change.
    environment = {**os.environ, 'PATH':'/usr/local/lib/omarchy-kids/windows-tools:/usr/bin:/usr/local/bin'}
    return subprocess.call(['/usr/bin/omarchy-windows-vm', tool.split('-')[1]],env=environment)

if __name__ == '__main__':
    raise SystemExit(windows(sys.argv[1]))
