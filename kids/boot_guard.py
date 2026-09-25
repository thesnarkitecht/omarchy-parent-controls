"""Do not open the desktop after an enabled boot policy failed to apply."""
from pathlib import Path
import os
import pwd
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_runtime import account, APPS, is_mountpoint

def main():
    if Path('/etc/omarchy-kids/controlled-on').exists():
        subprocess.run(['/usr/bin/systemctl','is-active','--quiet','omarchy-kids-policy.service'],check=True)
        apps = Path(pwd.getpwnam(account()['user']).pw_dir) / '.local/share/applications'
        if not is_mountpoint(apps) or not os.path.samefile(apps, APPS):
            raise RuntimeError('Controlled launcher is not mounted; refusing to start an unrestricted desktop.')

if __name__=='__main__': main()
