"""Apply the persisted runtime restriction when logind creates the user runtime."""
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_runtime import account

def main():
    if os.geteuid() != 0: raise SystemExit(1)
    if not Path('/etc/omarchy-kids/controlled-on').exists(): return
    target='/run/user/'+str(account()['uid'])
    if os.statvfs(target).f_flag & os.ST_NOEXEC: return
    # logind owns this tmpfs. Preserve its normal no-suid/no-device restrictions.
    subprocess.run(['/usr/bin/mount','-o','remount,noexec,nosuid,nodev',target],check=True)
    Path('/run/omarchy-kids-runtime-noexec').touch(mode=0o600)

if __name__ == '__main__': main()
