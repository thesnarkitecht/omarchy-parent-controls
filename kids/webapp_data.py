"""PIN-authorized profile reset, performed as the unprivileged browser worker."""
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys

DATA = Path('/var/lib/omarchy-kids/data')

def valid_key(key):
    if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', key):
        raise ValueError('Invalid webapp identifier.')

def clear(key, policy):
    valid_key(key)
    if key not in {app['id'] for app in policy['webapps']}:
        raise ValueError('This webapp no longer exists.')
    unit = 'omarchy-kids-webapp-' + key
    if subprocess.run(['/usr/bin/systemctl','is-active','--quiet',unit]).returncode == 0:
        subprocess.run(['/usr/bin/systemctl','stop',unit],check=True,timeout=30)
    subprocess.run(['/usr/bin/systemctl','stop',unit+'-open-*.service'],check=True,timeout=30)
    subprocess.run(['/usr/bin/systemd-run','--quiet','--collect','--wait',
                    '--property=User=omarchy-kids','--property=NoNewPrivileges=yes',
                    '--property=ProtectSystem=strict','--property=ProtectHome=yes',
                    '--property=ReadWritePaths='+str(DATA),
                    '/usr/bin/python3','-I','/usr/local/lib/omarchy-kids/webapp_data.py',key],
                   check=True,capture_output=True,timeout=60)

def remove_profile(key):
    valid_key(key)
    path = DATA / ('chromium-' + key)
    if path.is_symlink():
        raise ValueError('Refusing a linked browser profile.')
    if path.exists():
        shutil.rmtree(path)

if __name__ == '__main__':
    if os.getuid() != pwd.getpwnam('omarchy-kids').pw_uid:
        raise SystemExit('Profile reset must run as the browser worker.')
    remove_profile(sys.argv[1])
