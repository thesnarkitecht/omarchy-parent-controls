"""Exercise real bind mounts in an unprivileged private user/mount namespace."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import native_policy
from native_runtime import is_mountpoint

if len(sys.argv) == 1:
    subprocess.run(['/usr/bin/unshare', '--user', '--map-root-user', '--mount',
                    sys.executable, __file__, os.readlink('/proc/self/ns/mnt')], check=True)
    raise SystemExit(0)
# Refuse to operate in the caller's mount namespace.
assert os.readlink('/proc/self/ns/mnt') != sys.argv[1]
subprocess.run(['/usr/bin/mount', '--make-rprivate', '/'], check=True)
with tempfile.TemporaryDirectory(prefix='kids-mount-check-') as folder:
    root=Path(folder)
    source=root/'controlled'; target=root/'applications'
    source.mkdir(); target.mkdir()
    (source/'approved.desktop').write_text('approved')
    (target/'original.desktop').write_text('original installed application')
    native_policy.APPS=source
    try:
        for _ in range(2):
            subprocess.run(['/usr/bin/mount','--bind',str(source),str(target)],check=True)
        subprocess.run(['/usr/bin/mount','-o','remount,bind,ro',str(target)],check=True)
        assert not os.path.ismount(target), 'Expected reproduction uses same-filesystem bind mounts'
        assert is_mountpoint(target)
        assert os.path.samefile(target, source)
        assert (target/'approved.desktop').exists()
        print('PASS: reproduces old mount-detection failure and detects both controlled layers')
        native_policy.remove_launcher_mounts(target)
        assert not is_mountpoint(target)
        assert (target/'original.desktop').read_text() == 'original installed application'
        assert not (target/'approved.desktop').exists()
        assert (source/'approved.desktop').read_text() == 'approved'
        print('PASS: all controlled layers detached; original installed app restored without installation or deletion')
    finally:
        native_policy.remove_launcher_mounts(target)
