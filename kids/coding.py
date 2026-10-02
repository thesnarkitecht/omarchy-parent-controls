"""Persistent executable projects and private agent state, outside noexec homes."""
import os
from pathlib import Path
import stat
import subprocess

PROJECTS = Path('/var/lib/omarchy-coding')
STATE = Path('/var/lib/omarchy-hermes-state')


def trusted_parent(path):
    for part in (path, *path.parents):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Coding storage needs a root-owned, non-writable parent: ' + str(part))


def checked_storage(base, uid):
    trusted_parent(base)
    path = base / str(uid)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & 0o077:
        raise ValueError('Coding storage must be a private directory owned by the child: ' + str(path))
    return path


def prepare(user):
    if os.geteuid() != 0 or user.pw_uid < 1000:
        raise ValueError('A parent must prepare coding storage for a regular child account.')
    for base in (PROJECTS, STATE):
        trusted_parent(base.parent)
        base.mkdir(mode=0o755, exist_ok=True)
        trusted_parent(base)
        path = base / str(user.pw_uid)
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            checked_storage(base, user.pw_uid)
        else:
            os.chown(path, user.pw_uid, user.pw_gid)
        checked_storage(base, user.pw_uid)
    # Home paths are child-controlled. Never follow them with root privileges,
    # and preserve any existing Projects/Workspace rather than replacing it.
    script = '''import pathlib,sys
p=pathlib.Path.home()/'Projects'/'Workspace'
p.parent.mkdir(parents=True,exist_ok=True)
if not p.exists() and not p.is_symlink(): p.symlink_to(sys.argv[1],target_is_directory=True)
'''
    subprocess.run(['/usr/bin/runuser', '-u', user.pw_name, '--', '/usr/bin/python3', '-I',
                    '-c', script, str(PROJECTS / str(user.pw_uid))], check=True)
