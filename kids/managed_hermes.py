"""Run the unmodified Hermes Desktop behind a fixed, root-owned launcher."""
from pathlib import Path
import pwd
import re
import stat
import subprocess
from native_runtime import account

UNIT = 'omarchy-kids-hermes-desktop'
HOME = '/var/lib/omarchy-kids/hermes-home'

def launch(caller_uid):
    child = account()
    if caller_uid != child['uid']:
        raise ValueError('Hermes must be launched from the configured desktop account.')
    if not Path('/etc/omarchy-kids/controlled-on').exists():
        raise ValueError('Use the normal Hermes launcher when controlled mode is off.')
    if subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', UNIT]).returncode == 0:
        return {'ok': True}
    from display_access import grant
    worker = pwd.getpwnam('omarchy-kids-hermes')
    display = grant(child['uid'], worker.pw_uid)
    child_home = pwd.getpwnam(child['user']).pw_dir
    writable = [HOME] + [child_home + '/' + name for name in ('Projects', 'Documents', 'Downloads')]
    props = {
        'User':worker.pw_name, 'Group':'omarchy-kids', 'RuntimeDirectory':UNIT,
        'RuntimeDirectoryMode':'0700', 'NoNewPrivileges':'yes',
        'ProtectSystem':'strict', 'ProtectHome':'read-only', 'PrivateTmp':'yes',
        'ReadWritePaths':' '.join(writable), 'InaccessiblePaths':'/run/user',
        'BindReadOnlyPaths':f'{display}:/run/{UNIT}/wayland-0',
        'NoExecPaths':'/', 'ExecPaths':'/usr /opt',
        'ProtectKernelTunables':'yes', 'ProtectKernelModules':'yes',
        'ProtectControlGroups':'yes', 'RestrictSUIDSGID':'yes',
        'CapabilityBoundingSet':'', 'KillMode':'control-group',
        'TimeoutStopSec':'5', 'Type':'exec', 'UMask':'0077',
        'WorkingDirectory':child_home + '/Projects',
        'StandardOutput':'append:/var/log/omarchy-kids-hermes-desktop.log',
        'StandardError':'append:/var/log/omarchy-kids-hermes-desktop.log',
    }
    command = ['/usr/bin/systemd-run', '--collect', '--unit='+UNIT]
    command += ['--property='+k+'='+v for k,v in props.items()]
    environment = {'HOME':HOME, 'HERMES_HOME':HOME+'/.hermes',
                   'XDG_CONFIG_HOME':HOME+'/.config', 'XDG_CACHE_HOME':HOME+'/.cache',
                   'XDG_DATA_HOME':HOME+'/.local/share', 'XDG_RUNTIME_DIR':'/run/'+UNIT,
                   'WAYLAND_DISPLAY':'wayland-0'}
    environment.update(child.get('hermes_environment', {}))
    command += ['--setenv='+k+'='+v for k,v in environment.items()]
    command += [child.get('hermes_binary', '/opt/hermes-desktop/Hermes'), '--ozone-platform=wayland']
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    return {'ok':True}
