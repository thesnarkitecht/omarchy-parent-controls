"""Fail-closed sandbox for the managed Hermes CLI; no desktop or admin sockets.

Network access is intentional. This is not a network filter or an enforcement
mechanism for commands the child independently runs in an ordinary terminal.
"""
import os
from pathlib import Path
import sys

from coding import PROJECTS, STATE, checked_storage, trusted_parent
from hermes_install import ROOT

BWRAP = Path('/usr/bin/bwrap')
SYSTEM_FILES = ('resolv.conf', 'hosts', 'nsswitch.conf', 'passwd', 'group',
                'localtime', 'ssl', 'ca-certificates', 'pki')
# Only explicitly named provider settings cross the boundary. No session,
# loader, Python, proxy, shell initialization or parent-control variables.
PROVIDER_ENV = ('OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY',
                'GROQ_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY')


def command(projects, state, cwd, arguments, environment):
    """Build argv without a shell. Callers validate the two stable storage roots."""
    current = Path(cwd).resolve()
    relative = current.relative_to(projects) if current.is_relative_to(projects) else Path('.')
    args = [str(BWRAP), '--die-with-parent', '--new-session', '--unshare-user',
            '--unshare-pid', '--unshare-ipc', '--unshare-uts', '--disable-userns',
            '--cap-drop', 'ALL', '--clearenv', '--ro-bind', '/usr', '/usr']
    for name in ('bin', 'sbin', 'lib', 'lib64'):
        if Path('/' + name).exists():
            args += ['--symlink', 'usr/' + name, '/' + name]
    args += ['--ro-bind', str(ROOT), str(ROOT), '--dir', '/etc']
    for name in SYSTEM_FILES:
        source = Path('/etc') / name
        if source.exists():
            args += ['--ro-bind', str(source.resolve()), str(source)]
    args += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--tmpfs', '/run',
             '--dir', '/home/agent', '--bind', str(state), '/home/agent/.hermes',
             '--bind', str(projects), '/workspace', '--chdir', str(Path('/workspace') / relative)]
    values = {'HOME': '/home/agent', 'USER': 'agent', 'LOGNAME': 'agent',
              'SHELL': '/bin/bash', 'PATH': '/usr/local/bin:/usr/bin:/bin',
              'LANG': 'C.UTF-8', 'TERM': 'xterm-256color', 'TMPDIR': '/tmp',
              'HERMES_HOME': '/home/agent/.hermes', 'HERMES_RUNTIME_DIR': str(ROOT / 'tools'),
              'HERMES_DISABLE_LAZY_INSTALLS': '1'}
    for name in PROVIDER_ENV:
        if environment.get(name):
            values[name] = environment[name]
    for name, value in values.items():
        args += ['--setenv', name, value]
    return args + ['--', str(ROOT / 'source/.hermes/bin/hermes'), *arguments]


def main():
    try:
        from native_runtime import account
        uid = os.getuid()
        if uid == 0 or uid != os.geteuid() or uid != account()['uid']:
            raise ValueError('Run Hermes from the configured child account, never with sudo.')
        if not BWRAP.is_file():
            raise ValueError('The Hermes sandbox is unavailable. Ask a parent to update Parent Controls.')
        trusted_parent(BWRAP.parent)
        info = BWRAP.stat()
        if info.st_uid != 0 or info.st_mode & 0o6022:
            raise ValueError('The sandbox launcher must be root-owned, non-setuid and non-writable.')
        projects, state = checked_storage(PROJECTS, uid), checked_storage(STATE, uid)
        # Check the installation path, not user-writable project contents.
        trusted_parent(ROOT)
        cwd = Path.cwd().resolve()
        if not cwd.is_relative_to(projects):
            print('Hermes workspace: ' + str(projects) + ' (~/Projects/Workspace)', file=sys.stderr)
        argv = command(projects, state, cwd, sys.argv[1:], os.environ)
        os.execve(str(BWRAP), argv, {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    except (OSError, ValueError, RuntimeError) as error:
        print('Hermes did not start: ' + str(error), file=sys.stderr)
        return 1
