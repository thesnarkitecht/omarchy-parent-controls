"""Optional voice installation, owned and configured by Parent Controls."""
import json
import os
from pathlib import Path
import shutil
import subprocess

def install(source, pairing, user):
    source = Path(source) / 'voice'
    dest = Path('/usr/local/share/omarchy-kids/voice')
    shutil.copytree(source, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__','*.pyc','build','*.egg-info'))
    policy = Path('/etc/school-voice/policy.json')
    if not policy.exists():
        subprocess.run(['/usr/bin/bash', str(dest/'scripts/install.sh'), str(Path(pairing).resolve(strict=True))], check=True)
    else:
        subprocess.run(['/opt/school-voice/venv/bin/python','-m','pip','install',str(dest)],check=True)
        subprocess.run(['/opt/school-voice/venv/bin/python',str(dest/'scripts/download-wake-model.py')],check=True)
    data = json.loads(policy.read_text())
    data['parent_controls'] = True
    data.setdefault('wake_word', {'enabled':True, 'phrase':'Hey Laya','model_dir':'/opt/school-voice/models/wake','threshold':0.3,'silence_seconds':0.9})
    # Service uses its own live approvals; do not retain a second app list.
    data['apps'] = {}
    backup = policy.with_suffix('.before-parent-controls.json')
    if not backup.exists(): shutil.copy2(policy, backup)
    temp = policy.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2)+'\n'); temp.chmod(0o644); os.replace(temp,policy)
    runtime = Path('/run/user')/str(user.pw_uid)
    sockets = list((runtime/'hypr').glob('*/.socket.sock'))
    if sockets:
        subprocess.run(['/usr/bin/runuser','-u',user.pw_name,'--','/usr/bin/env',
            'XDG_RUNTIME_DIR='+str(runtime),'HYPRLAND_INSTANCE_SIGNATURE='+sockets[0].parent.name,
            '/usr/bin/python3',str(dest/'scripts/setup-desktop.py')],check=True)
        displays = [p for p in runtime.glob('wayland-*') if p.is_socket()]
        if displays:
            # Start in the child's graphical session, never as root. Its lock prevents duplicates.
            subprocess.Popen(['/usr/bin/runuser','-u',user.pw_name,'--','/usr/bin/env',
                'XDG_RUNTIME_DIR='+str(runtime),'WAYLAND_DISPLAY='+displays[0].name,
                'QT_QPA_PLATFORM=wayland','DBUS_SESSION_BUS_ADDRESS=unix:path='+str(runtime/'bus'),
                'HYPRLAND_INSTANCE_SIGNATURE='+sockets[0].parent.name,
                '/usr/local/bin/school-voice','serve'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,start_new_session=True)
    else:
        print('At the next desktop login, run: python /usr/local/share/omarchy-kids/voice/scripts/setup-desktop.py')
    print('Voice installed. Enable it from Parent Controls → Voice, videos & requests.')
