"""Root-run checks for the revised terminal-friendly policy."""
import os
from pathlib import Path
import subprocess
import sys
assert os.geteuid() == 0
sys.path.insert(0,'/usr/local/lib/omarchy-kids')
from native_runtime import account
child = account()['user']

def run_as(user, code):
    result = subprocess.run(['/usr/bin/runuser','-u',user,'--','/usr/bin/python3','-I','-c',code],
                            capture_output=True,text=True,timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    print(result.stdout.strip(),flush=True)

run_as(child, '''
import socket, subprocess, urllib.request
with urllib.request.urlopen('https://example.com',timeout=15) as response:
    assert response.status == 200
print('TERMINAL_HTTPS_ALLOWED')
try:
    addresses = {r[4][0] for r in socket.getaddrinfo('brave.com',443)}
except socket.gaierror:
    addresses = set()  # systemd-resolved deliberately omits unspecified addresses.
assert addresses <= {'0.0.0.0','::'}, addresses
print('KNOWN_BROWSER_DOWNLOAD_HOST_BLOCKED')
for binary in ['/usr/bin/chromium','/usr/bin/pacman']:
    try: subprocess.run([binary,'--version'],capture_output=True,timeout=3)
    except PermissionError: pass
    else: raise AssertionError('Restricted executable ran: '+binary)
assert subprocess.run(['/usr/bin/sudo','-k','-n','true'],capture_output=True).returncode != 0
print('BROWSERS_INSTALLER_AND_AGENT_DIRECT_LAUNCH_DENIED')
''')
run_as('omarchy-kids-hermes', '''
import socket
with socket.socket() as s:
    s.settimeout(2)
    try: s.connect(('1.1.1.1',443))
    except OSError: pass
    else: raise AssertionError('Hermes can reach an arbitrary website')
print('HERMES_EXTERNAL_NETWORK_DENIED')
''')
run_as('omarchy-kids', f'''
from pathlib import Path
Path('/home/{child}/Downloads/parent-controls-download-check.txt').write_text('download check\\n')
print('WEBAPP_DOWNLOAD_DIRECTORY_WRITABLE')
''')
run_as(child, f'''
from pathlib import Path
p=Path('/home/{child}/Downloads/parent-controls-download-check.txt')
assert p.read_text() == 'download check\\n'
p.unlink()
print('CHILD_CAN_READ_DOWNLOADED_FILE')
''')
run_as(child, '''
import os, pathlib, shutil, subprocess, tempfile
folder=pathlib.Path.home()/'Downloads'
fd,name=tempfile.mkstemp(prefix='parent-controls-exec-check-',dir=folder)
os.close(fd)
try:
    shutil.copyfile('/usr/bin/true',name)
    os.chmod(name,0o700)
    try: subprocess.run([name],check=True)
    except PermissionError: pass
    else: raise AssertionError('A downloaded native executable ran')
finally:
    pathlib.Path(name).unlink()
assert not os.access('/etc/omarchy-kids/account.json',os.W_OK)
assert not os.access('/usr/local/lib/omarchy-kids/control.py',os.W_OK)
assert not os.access('/var/lib/omarchy-kids-control/pin.json',os.R_OK)
print('DOWNLOADED_NATIVE_EXECUTABLE_AND_POLICY_TAMPERING_DENIED')
''')
