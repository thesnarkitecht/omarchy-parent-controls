"""Parent-authorized official Hermes install with a read-only shared runtime.

Program files remain root-owned. The managed CLI mounts dedicated coding and
agent-state directories inside a sandbox. Never run Hermes as root to chat.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path('/opt/omarchy-parent-controls-hermes')
COMMAND = Path('/usr/local/bin/hermes')
COMMIT = '85c7e87fc7bbbd2b646da3398b402c42c88454cb'
INSTALLER_SHA256 = 'b6d77a3491ab1d8e842071a8d92f76ae118836479b1ac69436e00f85f541d5a1'
INSTALLER_URL = 'https://raw.githubusercontent.com/NousResearch/hermes-agent/' + COMMIT + '/scripts/install.sh'
MARKER = '# Omarchy parent controls: official Hermes runtime'


def selected(user):
    result = subprocess.run(['/usr/bin/runuser','-u',user.pw_name,'--','/usr/bin/cat',
                             user.pw_dir+'/.config/omarchy/defaults/agent'],
                            capture_output=True,text=True)
    return result.returncode == 0 and result.stdout.strip() == 'hermes'


def launch_text():
    return ('#!/bin/sh\n' + MARKER + '\n'
            'exec /usr/local/lib/omarchy-kids/run hermes_cli "$@"\n')


def run(*args, **kwargs):
    return subprocess.run(list(args),check=True,**kwargs)


def installer_lock(path, info):
    # uv intentionally creates mode-0666 advisory locks. These are not code or
    # cached packages. Accept only non-executable regular locks in its known
    # scratch/cache directories; ownership is still checked by trusted_tree.
    return (stat.S_ISREG(info.st_mode) and not info.st_mode & 0o111
            and path.name.endswith('.lock')
            and any(path.is_relative_to(ROOT / name) for name in
                    ('tmp', 'build-home/.cache/uv', 'data/cache/uv')))


def trusted_tree():
    # Never adopt a pre-existing child-owned installation as privileged code.
    for path in [ROOT, *ROOT.parents]:
        if path.exists() and (path.is_symlink() or path.stat().st_uid != 0 or path.stat().st_mode & 0o022):
            raise ValueError('Hermes installation path must be root-owned and not writable by other users: '+str(path))
    if ROOT.exists():
        for base, dirs, files in os.walk(ROOT, followlinks=False):
            for name in dirs + files:
                path = Path(base)/name
                info = path.lstat()
                if info.st_uid != 0 or (not path.is_symlink() and info.st_mode & 0o022
                                        and not installer_lock(path, info)):
                    raise ValueError('Untrusted file in Hermes runtime: '+str(path))


def install_runtime():
    trusted_tree()
    ready = ROOT/'parent-controls-ready.json'
    if ready.exists() and json.loads(ready.read_text()).get('commit') == COMMIT:
        return
    ROOT.mkdir(mode=0o755,parents=True,exist_ok=True)
    for name in ('build-home','data','tools','tmp'):
        (ROOT/name).mkdir(mode=0o755,exist_ok=True)
    # Ignore child-provided installer overrides, PATH, git config and Python env.
    environment = {'HOME':str(ROOT/'build-home'), 'HERMES_HOME':str(ROOT/'data'),
                   'HERMES_RUNTIME_DIR':str(ROOT/'tools'), 'TMPDIR':str(ROOT/'tmp'),
                   'PATH':'/usr/bin:/bin', 'SHELL':'/bin/bash', 'LANG':'C.UTF-8',
                   'UV_PYTHON_INSTALL_DIR':str(ROOT/'bootstrap-python'),
                   'GIT_CONFIG_NOSYSTEM':'1', 'GIT_CONFIG_GLOBAL':'/dev/null',
                   'HERMES_INSTALL_VERBOSE':'1'}
    script = ROOT/'official-install.sh'
    run('/usr/bin/curl','--fail','--silent','--show-error','--location',
        '--proto','=https','--tlsv1.2',INSTALLER_URL,'--output',str(script),env=environment)
    if hashlib.sha256(script.read_bytes()).hexdigest() != INSTALLER_SHA256:
        raise ValueError('Official Hermes installer checksum did not match; nothing was executed.')
    run('/usr/bin/bash',str(script),'--commit',COMMIT,'--dir',str(ROOT/'source'),
        '--non-interactive','--skip-browser',env=environment,cwd=ROOT)
    key = hashlib.sha256(str(ROOT/'source').encode()).hexdigest()[:16]
    facts = json.loads((ROOT/'data/installs'/key/'facts.json').read_text())
    venv = Path(facts['packages']['venv']['environment']).resolve(strict=True)
    if not venv.is_relative_to((ROOT/'data/installs'/key/'environments').resolve()):
        raise ValueError('Official installer returned an unexpected dependency location.')
    # Upstream's supported sealed-payload layout lets its own launcher resolve
    # shared dependencies without pointing HERMES_HOME at another user's data.
    (ROOT/'manifest.json').write_text(json.dumps({'repo':'source',
        'venv':str(venv.relative_to(ROOT)), 'store':'tools'})+'\n')
    for folder in (ROOT/'data', ROOT/'data/installs'):
        folder.chmod(0o755)
    for base, dirs, files in os.walk(ROOT/'data/installs'):
        Path(base).chmod(0o755)
        for name in files:
            path=Path(base)/name
            if not path.is_symlink(): path.chmod(0o755 if path.stat().st_mode & 0o111 else 0o644)
    ready.write_text(json.dumps({'commit':COMMIT,'installer_sha256':INSTALLER_SHA256})+'\n')


def publish(user):
    # Preserve the prior entry point; no existing Hermes source, settings or
    # conversation data is removed. Atomic publication avoids half-written CLI.
    backup = ROOT/'previous-system-command'
    if COMMAND.exists() or COMMAND.is_symlink():
        if not COMMAND.is_symlink() and COMMAND.read_text(errors='replace') == launch_text():
            pass
        elif not backup.exists() and not backup.is_symlink():
            shutil.copy2(COMMAND,backup,follow_symlinks=False)
    fd, temporary = tempfile.mkstemp(prefix='.hermes-',dir=COMMAND.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            stream.write(launch_text());os.fchmod(stream.fileno(),0o755)
        os.replace(temporary,COMMAND)
    finally:
        Path(temporary).unlink(missing_ok=True)
    # Do all writes inside the user home as that user, not as root following
    # user-controlled symlinks. A symlink resolves to the executable system FS.
    script = '''import os,pathlib,time
p=pathlib.Path.home()/'.local/bin/hermes'
p.parent.mkdir(parents=True,exist_ok=True)
if p.is_symlink() and os.readlink(p)=='/usr/local/bin/hermes': raise SystemExit(0)
if p.exists() or p.is_symlink():
    p.rename(p.with_name('hermes.before-parent-controls-'+str(time.time_ns())))
p.symlink_to('/usr/local/bin/hermes')
'''
    run('/usr/bin/runuser','-u',user.pw_name,'--','/usr/bin/python3','-I','-c',script)


def ensure(user):
    if os.geteuid() != 0:
        raise ValueError('Installing or repairing Hermes requires the parent PIN through sudo.')
    install_runtime()
    from coding import prepare
    prepare(user)
    publish(user)
    # Do not borrow the development VM's old root-installed runtime or state.
    run('/usr/bin/runuser','-u',user.pw_name,'--','/usr/bin/env',
        'HOME='+user.pw_dir, str(COMMAND),'--version',timeout=60)


if __name__ == '__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from native_runtime import account
    user=pwd.getpwnam(account()['user'])
    ensure(user)
    if Path('/etc/omarchy-kids/controlled-on').exists():
        from native_policy import apply
        apply()
    print('Hermes is ready. Run hermes in your terminal; run hermes model to configure a provider if needed.')
