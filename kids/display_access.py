"""Grant access to a verified Wayland socket without following a swapped link."""
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

def grant(uid, worker_uid):
    if os.geteuid() == 0:
        # The broker sees user homes/runtime directories read-only. Ask PID 1
        # to run this fixed helper as the socket's owner, with no capabilities.
        # This also prevents a child-controlled symlink from receiving a root ACL.
        result = subprocess.run([
            '/usr/bin/systemd-run','--quiet','--collect','--wait','--pipe',
            '--property=User='+str(uid), '--property=NoNewPrivileges=yes',
            '--property=CapabilityBoundingSet=',
            '/usr/bin/python3','-I','/usr/local/lib/omarchy-kids/display_access.py',
            str(uid),str(worker_uid)], check=True,capture_output=True,text=True,timeout=15)
        value = Path(result.stdout.strip())
        if value.parent != Path('/run/user')/str(uid) or not re.fullmatch(r'wayland-[0-9]+', value.name):
            raise ValueError('Invalid display helper response.')
        return value
    if os.getuid() != uid:
        raise ValueError('The display helper must run as the desktop account.')
    runtime = Path('/run/user') / str(uid)
    sockets = []
    for path in runtime.glob('wayland-*'):
        info = path.lstat()
        if re.fullmatch(r'wayland-[0-9]+', path.name) and stat.S_ISSOCK(info.st_mode) and info.st_uid == uid:
            sockets.append(path)
    if len(sockets) != 1:
        raise RuntimeError('Could not identify the Omarchy display.')
    display = sockets[0]
    fd = os.open(display, os.O_PATH | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != uid:
            raise ValueError('The display socket changed. Try again.')
        subprocess.run(['/usr/bin/setfacl', '-m', f'u:{worker_uid}:rw', f'/proc/self/fd/{fd}'],
                       pass_fds=(fd,), check=True)
    finally:
        os.close(fd)
    return display

if __name__ == '__main__':
    print(grant(int(sys.argv[1]), int(sys.argv[2])))
