"""Persistent parent pause. Freeze work, switch to a parent-resumable login VT."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
from control import atomic_json

STATE = Path('/var/lib/omarchy-kids-control')
ETC = Path('/etc/omarchy-kids')


def desired():
    try:
        return json.loads((STATE/'access.json').read_text())['paused'] is True
    except FileNotFoundError:
        return False


def applied():
    try:
        return json.loads((STATE/'access-applied.json').read_text())
    except FileNotFoundError:
        return {'paused': False, 'units': [], 'session': None}


def status():
    intent, result = desired(), applied()
    boot = Path('/proc/sys/kernel/random/boot_id')
    current_boot = not intent or (boot.exists() and result.get('boot') == boot.read_text().strip())
    return {'paused': intent, 'enforced': current_boot and result.get('paused') == intent and not result.get('error'),
            'error': result.get('error')}


def change(paused):
    if type(paused) is not bool:
        raise ValueError('Choose Pause or Resume.')
    atomic_json(STATE/'access.json', {'paused': paused})
    subprocess.run(['/usr/bin/systemctl', 'restart', 'omarchy-kids-access.service'], check=True, timeout=40)
    if not status()['enforced']:
        raise ValueError('The access change needs attention on the laptop. Refresh before retrying.')


def run(*args, **options):
    return subprocess.run(list(args), check=True, timeout=10, **options)


def units(uid):
    value = run('/usr/bin/systemctl', 'list-units', '--all', '--no-legend', '--plain',
                'omarchy-kids-webapp-*.service', 'omarchy-kids-hermes-desktop.service',
                capture_output=True, text=True).stdout
    result = ['user-' + str(uid) + '.slice']
    for line in value.splitlines():
        name = line.split()[0] if line.split() else ''
        if re.fullmatch(r'omarchy-kids-webapp-[a-z0-9-]+\.service', name) or name == 'omarchy-kids-hermes-desktop.service':
            result.append(name)
    return result


def enforce():
    from activity import sessions
    uid = json.loads((ETC/'account.json').read_text())['uid']
    if type(uid) is not int or uid < 1000:
        raise ValueError('Invalid controlled account.')
    with (STATE/'access-enforce.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = applied()
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        if result.get('boot') != boot:
            result = {'paused': False, 'units': [], 'session': None, 'boot': boot}
        try:
            if desired():
                if not result.get('paused'):
                    current_sessions = sessions(uid)
                    if any(info.get('VTNr') == '12' for _, info in current_sessions):
                        raise ValueError('tty12 is in use. Sign out of that terminal before pausing.')
                    for key, info in current_sessions:
                        if info.get('Type') in ('wayland', 'x11') and info.get('Active') == 'yes':
                            result['session'] = key
                            run('/usr/bin/loginctl', 'lock-session', key)
                    # This root-owned getty stays outside the child's frozen slice.
                    # The parent can enter their PIN here even if the phone is offline.
                    run('/usr/bin/systemctl', 'start', 'getty@tty12.service')
                    result['parent_tty'] = True
                    atomic_json(STATE/'access-applied.json', result)
                    run('/usr/bin/chvt', '12')
                for unit in units(uid):
                    if subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', unit], timeout=5).returncode:
                        continue
                    if unit not in result['units']:
                        result['units'].append(unit)
                        atomic_json(STATE/'access-applied.json', result)
                    run('/usr/bin/systemctl', 'freeze', unit)
                result.update(paused=True, error=None)
            else:
                for unit in list(result['units']):
                    if subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', unit], timeout=5).returncode == 0:
                        run('/usr/bin/systemctl', 'thaw', unit)
                    result['units'].remove(unit)
                    atomic_json(STATE/'access-applied.json', result)
                if result.get('parent_tty'):
                    # Close our recovery login after a parent resumes, including
                    # the PAM helper that requested it. It never becomes a child shell.
                    run('/usr/bin/systemctl', 'stop', 'getty@tty12.service')
                    result['parent_tty'] = False
                if result.get('session'):
                    # The existing lock screen remains; resuming does not bypass login.
                    subprocess.run(['/usr/bin/loginctl', 'activate', result['session']], timeout=5)
                result.update(paused=False, error=None, session=None)
            atomic_json(STATE/'access-applied.json', result)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            result['error'] = 'Pause or resume did not finish. A parent can retry from the phone or sign in with the parent PIN on tty12.'
            atomic_json(STATE/'access-applied.json', result)
            raise error


def pam():
    """system-login account gate and optional parent-PIN recovery authentication."""
    import sys
    try:
        account = json.loads((ETC/'account.json').read_text())
        if os.environ.get('PAM_USER') != account['user']:
            return 1 if os.environ.get('PAM_TYPE') == 'auth' else 0
        paused = desired()
        if os.environ.get('PAM_TYPE') == 'account':
            return int(paused)
        if not paused or os.environ.get('PAM_SERVICE') not in ('login', 'sddm'):
            return 1
        pin = sys.stdin.buffer.read(128).rstrip(b'\0\n').decode('ascii')
        from client import request
        request('family-change', pin=pin, operation='set-paused', fields={'paused': False})
        return 0
    except (ValueError, OSError, RuntimeError, KeyError):
        return 1


def main():
    import sys
    if os.geteuid() != 0:
        return 1
    if sys.argv[1:] == ['pam']:
        return pam()
    enforce()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
