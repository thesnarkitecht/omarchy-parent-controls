"""Root-run visible Chromium check; the screenshot requires human verification.

The production policy disables developer tools, so this check uses a normal
window instead of remote debugging or headless DevTools automation.
"""
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,'/usr/local/lib/omarchy-kids')
from display_access import grant
from native_runtime import account

def main():
    if os.geteuid()!=0: raise SystemExit('Administrator approval is required.')
    config=account();child=pwd.getpwnam(config['user']);worker=pwd.getpwnam('omarchy-kids')
    display=grant(child.pw_uid,worker.pw_uid)
    profile=Path(tempfile.mkdtemp(prefix='policy-check-',dir='/var/lib/omarchy-kids/data'))
    os.chown(profile,worker.pw_uid,worker.pw_gid)
    unit='omarchy-kids-browser-verification'
    try:
        subprocess.run(['/usr/bin/systemd-run','--collect','--unit='+unit,
            '--property=User=omarchy-kids','--property=Group=omarchy-kids',
            '--property=RuntimeDirectory='+unit,'--property=RuntimeDirectoryMode=0700',
            '--property=NoNewPrivileges=yes','--property=ProtectSystem=strict',
            '--property=ProtectHome=read-only','--property=PrivateTmp=yes',
            '--property=ReadWritePaths='+str(profile),'--property=InaccessiblePaths=/run/user',
            '--property=BindReadOnlyPaths='+str(display)+':/run/'+unit+'/wayland-0',
            '--property=CapabilityBoundingSet=','--property=RuntimeMaxSec=45',
            '--property=KillMode=control-group','--property=TimeoutStopSec=5',
            '--setenv=HOME=/var/lib/omarchy-kids/data','--setenv=XDG_RUNTIME_DIR=/run/'+unit,
            '--setenv=WAYLAND_DISPLAY=wayland-0','/usr/bin/chromium',
            '--ozone-platform=wayland','--no-first-run','--no-default-browser-check',
            '--password-store=basic','--user-data-dir='+str(profile),
            '--class=parent-controls-browser-test','--app=https://example.com'],check=True)
        time.sleep(8)
        screenshot=Path(child.pw_dir)/'parent-controls-blocked-navigation.png'
        subprocess.run(['/usr/bin/runuser','-u',child.pw_name,'--','/usr/bin/env',
            'XDG_RUNTIME_DIR=/run/user/'+str(child.pw_uid),'WAYLAND_DISPLAY='+display.name,
            '/usr/bin/grim',str(screenshot)],check=True)
        print('BROWSER_SCREENSHOT_REQUIRES_VISUAL_REVIEW: '+str(screenshot),flush=True)
    finally:
        subprocess.run(['/usr/bin/systemctl','stop',unit+'.service'],check=False)
        shutil.rmtree(profile)

if __name__=='__main__': main()
