"""Run as the child: verify real Hermes terminal startup without sending a chat."""
import errno
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import time

assert os.geteuid() != 0, 'Hermes acceptance must run as the desktop user'
for arguments in ([], ['--cli']):
    child, fd = pty.fork()
    if child == 0:
        os.environ['TERM'] = 'xterm-256color'
        os.execv('/usr/local/bin/hermes',['hermes',*arguments])
    output = b''
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if not select.select([fd],[],[],.2)[0]:continue
            try: block=os.read(fd,65536)
            except OSError as error:
                if error.errno == errno.EIO:break
                raise
            if not block:break
            output += block
            if b'Welcome to Hermes Agent!' in output:break
        assert b'Welcome to Hermes Agent!' in output, output[-2000:].decode(errors='replace')
        assert b'Permission denied' not in output and b'Traceback (most recent call last)' not in output
        print('PASS: real hermes '+(' '.join(arguments) or '(default)')+' reached its interactive prompt',flush=True)
        os.write(fd,b'/exit\r')
    finally:
        os.close(fd)
        try:os.killpg(child,signal.SIGTERM)
        except ProcessLookupError:pass
        os.waitpid(child,0)

# Check real executables, including Hermes's private tool store, rather than
# merely checking that a string disappeared from the denylist.
subprocess.run(['/usr/bin/mise','--version'],check=True,timeout=10)
root=Path('/opt/omarchy-parent-controls-hermes/tools')
for name in ('uv','node'):
    candidates=[p for p in root.rglob(name) if p.is_file() and os.access(p,os.X_OK)]
    assert candidates, name+' runtime not found'
    subprocess.run([str(candidates[0]),'--version'],check=True,timeout=10)
print('PASS: mise and the official Hermes uv/node executables run',flush=True)
