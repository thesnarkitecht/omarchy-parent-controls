"""Read live approvals from the installed root broker. Fail closed if unavailable."""
import json
import socket
from pathlib import Path
import stat

SOCKET = Path('/run/omarchy-kids-control/control.sock')

def merge(policy):
    info = SOCKET.lstat()
    if info.st_uid != 0 or not stat.S_ISSOCK(info.st_mode):
        raise ValueError('Parent-control broker is not trusted')
    parent = SOCKET.parent.stat()
    if parent.st_uid != 0 or parent.st_mode & 0o022:
        raise ValueError('Parent-control socket directory is not trusted')
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(2)
        client.connect(str(SOCKET))
        client.sendall(b'{"action":"voice-catalog"}\n')
        raw = client.makefile('rb').readline(65537)
    if len(raw) > 65536:
        raise ValueError('Parent catalog too large')
    result = json.loads(raw)
    if not result.get('ok'):
        raise ValueError('Parent controls are unavailable')
    voice = result['voice']
    return {**policy, 'enabled': voice['enabled'], 'apps': result['apps'],
            'wake_word': {**policy['wake_word'], 'enabled': voice['wake_enabled'], 'phrase': voice['phrase']}}
