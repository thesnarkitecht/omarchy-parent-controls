"""Launch approved webapps into the existing Omarchy desktop with a separate UID."""
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import subprocess
import tempfile

ACCOUNT = Path('/etc/omarchy-kids/account.json')
APPS = Path('/usr/local/share/omarchy-kids/applications')
LAUNCHERS = Path('/usr/local/share/applications/omarchy-kids')
CHROME_POLICY = Path('/etc/chromium/policies/managed/omarchy-kids.json')
MOUNTINFO = Path('/proc/self/mountinfo')


def is_mountpoint(path):
    # os.path.ismount misses same-filesystem bind mounts, including our launcher
    # overlay. Consult this process's mount namespace instead.
    target = os.path.abspath(path)
    for line in MOUNTINFO.read_text().splitlines():
        fields = line.split()
        if len(fields) < 6:
            continue
        mounted = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4])
        if mounted == target:
            return True
    return False

def browser_policy(policy):
    from urllib.parse import urlsplit
    allowed = []
    for app in policy['webapps']:
        for origin in app['origins']:
            p = urlsplit(origin)
            # Chrome policy filters use prefix paths, not glob paths. A leading
            # dot restricts matching to this exact host, without subdomains.
            allowed.append('https://.' + p.netloc)
    value = {'URLBlocklist':['*'], 'URLAllowlist':sorted(set(allowed)),
             'ExtensionInstallBlocklist':['*'], 'DeveloperToolsAvailability':2,
             'BrowserGuestModeEnabled':False, 'BrowserAddPersonEnabled':False,
             'IncognitoModeAvailability':1, 'DownloadRestrictions':0,
             'DownloadDirectory':str(Path(pwd.getpwnam(account()['user']).pw_dir) / 'Downloads') if configured() else '${HOME}/Downloads', 'PromptForDownloadLocation':False,
             'DefaultPopupsSetting':2, 'BrowserSignin':0, 'SyncDisabled':True,
             'PasswordManagerEnabled':False, 'BackgroundModeEnabled':False}
    CHROME_POLICY.write_text(json.dumps(value))
    CHROME_POLICY.chmod(0o644)


def configured():
    return ACCOUNT.is_file()


def account():
    value = json.loads(ACCOUNT.read_text())
    user = pwd.getpwnam(value['user'])
    if user.pw_uid != value['uid'] or user.pw_uid == 0:
        raise RuntimeError('Invalid child account configuration.')
    return value


def publish_entry(path, text):
    # Never expose an empty or root-only .desktop file to launcher watchers.
    # The broker runs with umask 0077; chmod after publishing can be too late.
    if path.exists() and path.read_text() == text and stat.S_IMODE(path.stat().st_mode) == 0o644:
        return
    fd, temporary = tempfile.mkstemp(prefix='.webapp-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(text)
            output.flush()
            os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def desktop_entries(policy):
    if Path('/etc/omarchy-kids/controlled-on').exists(): browser_policy(policy)
    APPS.mkdir(parents=True, exist_ok=True)
    LAUNCHERS.mkdir(parents=True, exist_ok=True)
    LAUNCHERS.chmod(0o755)
    approved = {app['id'] for app in policy['webapps']}
    for folder, prefix in ((APPS, 'omarchy-kids-webapp-'), (LAUNCHERS, 'webapp-')):
        for path in folder.glob(prefix + '*.desktop'):
            if path.name[len(prefix):-len('.desktop')] not in approved:
                path.unlink()
    for app in policy['webapps']:
        # IDs and names have already passed core.validate_policy.
        name = app['name'].replace('\\', '\\\\')
        text = (
            '[Desktop Entry]\nType=Application\nName=' + name + '\n'
            'Exec=/usr/local/bin/omarchy-kids-webapp ' + app['id'] + '\n'
            'Icon=/var/lib/omarchy-kids/icons/' + app['id'] + '.png\nCategories=Education;\nTerminal=false\n')
        icon = Path('/var/lib/omarchy-kids/icons') / (app['id'] + '.png')
        if not icon.exists():
            subprocess.run(['/usr/bin/systemd-run','--collect','--quiet','--wait',
                '--unit=omarchy-kids-icon-'+app['id'],
                '--property=User=omarchy-kids','--property=Group=omarchy-kids',
                '--property=NoNewPrivileges=yes','--property=ProtectSystem=strict',
                '--property=ProtectHome=yes','--property=ReadWritePaths=/var/lib/omarchy-kids/icons',
                '--property=RuntimeMaxSec=30','/usr/bin/python3','-I',
                '/usr/local/lib/omarchy-kids/fetch_icon.py',app['id'],app['url']],
                timeout=35, capture_output=True)
        # The system directory stays mounted in both modes. Its nested desktop
        # ID matches the controlled overlay: omarchy-kids-webapp-<id>.
        # Publish it last so the XDG directory change sees the complete overlay.
        publish_entry(APPS / ('omarchy-kids-webapp-' + app['id'] + '.desktop'), text)
        publish_entry(LAUNCHERS / ('webapp-' + app['id'] + '.desktop'), text)


def revoke_webapps():
    subprocess.run(['/usr/bin/systemctl', 'stop', 'omarchy-kids-webapp-*.service'], check=True, timeout=30)


def launch_webapp(key, caller_uid, policy, url=None):
    config = account()
    if not isinstance(key, str) or (caller_uid != config['uid'] and caller_uid != pwd.getpwnam('omarchy-kids-hermes').pw_uid):
        raise ValueError('This request must come from the configured child account.')
    if key not in {app['id'] for app in policy['webapps']}:
        raise ValueError('This webapp has not been approved by a parent.')
    entry = next(app for app in policy['webapps'] if app['id'] == key)
    from core import approved_url
    if url is not None and not approved_url(url,entry['origins']):
        raise ValueError('This website has not been approved by a parent.')
    from display_access import grant
    worker = pwd.getpwnam('omarchy-kids')
    display = grant(config['uid'], worker.pw_uid)
    unit = 'omarchy-kids-webapp-' + key
    if subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', unit]).returncode == 0:
        return {'ok': True}
    entry = next(app for app in policy['webapps'] if app['id'] == key)
    props = {
        'User': 'omarchy-kids', 'Group': 'omarchy-kids', 'RuntimeDirectory': unit,
        'RuntimeDirectoryMode': '0700', 'NoNewPrivileges': 'yes', 'ProtectSystem': 'strict',
        'ProtectHome': 'read-only', 'PrivateTmp': 'yes',
        'ReadWritePaths': '/var/lib/omarchy-kids/data ' + pwd.getpwnam(config['user']).pw_dir + '/Downloads',
        'InaccessiblePaths': '/run/user',
        'BindReadOnlyPaths': f'{display}:/run/{unit}/wayland-0',
        'RestrictSUIDSGID': 'yes', 'ProtectKernelTunables': 'yes',
        'ProtectKernelModules': 'yes', 'ProtectControlGroups': 'yes',
        'CapabilityBoundingSet': '', 'KillMode': 'control-group', 'TimeoutStopSec': '5',
        'Type':'exec', 'UMask':'0022',
        'StandardOutput':'append:/var/log/omarchy-kids-webapps.log',
        'StandardError':'append:/var/log/omarchy-kids-webapps.log',
    }
    command = ['/usr/bin/systemd-run', '--collect', '--unit=' + unit]
    command += ['--property=' + k + '=' + v for k, v in props.items()]
    command += ['--setenv=HOME=/var/lib/omarchy-kids/data',
                '--setenv=XDG_RUNTIME_DIR=/run/' + unit,
                '--setenv=WAYLAND_DISPLAY=wayland-0',
                '/usr/bin/chromium', '--ozone-platform=wayland', '--password-store=basic',
                '--no-first-run', '--no-default-browser-check', '--disable-sync',
                '--user-data-dir=/var/lib/omarchy-kids/data/chromium-'+key,
                '--class=omarchy-webapp-'+key, '--app='+(url or entry['url'])]
    subprocess.run(command, check=True, timeout=30, capture_output=True)
    return {'ok': True}
