"""Run AS THE CHILD on an installed Linux test machine. Never run as root.

Uses the production namespace builder with a fixed diagnostic program instead
of the model. No network/model credentials, policy mutations or PIN required.
Exits nonzero if isolation or executable project storage fails.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, '/usr/local/lib/omarchy-kids')
import hermes_cli
from coding import PROJECTS, STATE, checked_storage
from native_runtime import account

PROBE = r'''
import json, os, pathlib, subprocess, sys
p = pathlib.Path
hidden = ['/etc/omarchy-kids', '/etc/shadow', '/etc/sudoers',
          '/var/lib/omarchy-kids-control', '/run/omarchy-kids-control',
          '/run/dbus', '/run/user', sys.argv[1]]
assert all(not p(v).exists() for v in hidden), 'Host authority or session files exposed'
assert all(k not in os.environ for k in ('SSH_AUTH_SOCK', 'DBUS_SESSION_BUS_ADDRESS', 'WAYLAND_DISPLAY'))
status = p('/proc/self/status').read_text().splitlines()
assert next(v for v in status if v.startswith('CapEff:')).split()[1] == '0000000000000000'
assert next(v for v in status if v.startswith('NoNewPrivs:')).split()[1] == '1'
try:
    p('/usr/.parent-controls-probe').write_text('must fail')
except PermissionError:
    pass
except OSError as e:
    assert e.errno == 30, e
else:
    raise AssertionError('System mount was writable')
result = subprocess.run(['/usr/bin/unshare', '--user', '--map-root-user', '/usr/bin/true'], capture_output=True)
assert result.returncode != 0, 'Nested user namespaces were not disabled'
p('project-check.sh').write_text('#!/bin/sh\nprintf coding-ok')
p('project-check.sh').chmod(0o700)
assert subprocess.check_output(['./project-check.sh'], text=True) == 'coding-ok'
subprocess.run(['/usr/bin/python3', '-m', 'venv', '--without-pip', '.venv'], check=True)
assert subprocess.check_output(['.venv/bin/python', '-c', 'print(6 * 7)'], text=True).strip() == '42'
subprocess.run(['/usr/bin/git', 'init', '--quiet'], check=True)
print(json.dumps({'hidden_authority': True, 'no_new_privileges': True,
                  'no_capabilities': True, 'nested_userns_denied': True,
                  'system_readonly': True, 'project_exec': True, 'venv': True, 'git': True}))
'''


def main():
    if sys.platform != 'linux' or os.getuid() == 0 or os.getuid() != account()['uid']:
        raise SystemExit('Run this check on Linux as the configured child, without sudo.')
    uid = os.getuid()
    projects, state = checked_storage(PROJECTS, uid), checked_storage(STATE, uid)
    with tempfile.TemporaryDirectory(prefix='.sandbox-check-', dir=projects) as folder:
        argv = hermes_cli.command(projects, state, folder, [], {})
        argv = argv[:argv.index('--') + 1] + ['/usr/bin/python3', '-c', PROBE, str(Path.home())]
        subprocess.run(argv, check=True, timeout=60, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    # Check the real upstream launcher separately, still through its sandbox.
    subprocess.run(['/usr/local/bin/hermes', '--version'], check=True, timeout=60)


if __name__ == '__main__':
    main()
