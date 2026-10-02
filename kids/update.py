"""Parent-authorized updates from this project's published GitHub releases."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
import time

REPOSITORY = 'thesnarkitecht/omarchy-parent-controls'
LIB = Path('/usr/local/lib/omarchy-kids')
ETC = Path('/etc/omarchy-kids')
STATE = Path('/var/lib/omarchy-kids-control')
STAGING = '/var/tmp'
VERSION = re.compile(r'(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?\Z')
MAX_ARCHIVE = 32 * 1024 * 1024


def version_key(value):
    match = VERSION.fullmatch(value)
    if not match:
        raise ValueError('Unsupported release version: ' + value)
    major, minor, patch, stage, number = match.groups()
    return (int(major), int(minor), int(patch),
            {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}[stage], int(number or 0))


def installed():
    return json.loads((LIB / 'release.json').read_text())['version']


def download(url, destination, limit=MAX_ARCHIVE):
    # Ignore user curl configuration, proxy and CA overrides, even under sudo -E.
    subprocess.run(['/usr/bin/curl', '-q', '--fail', '--silent', '--show-error',
                    '--location', '--proto', '=https', '--proto-redir', '=https',
                    '--tlsv1.2', '--connect-timeout', '15', '--max-time', '180',
                    '--max-filesize', str(limit), '--output', str(destination), url],
                   env={'PATH': '/usr/bin', 'HOME': '/root', 'LANG': 'C.UTF-8'}, check=True)
    if destination.stat().st_size > limit:
        raise ValueError('Release download exceeded its size limit.')


def latest(current, folder):
    path = folder / 'releases.json'
    download('https://api.github.com/repos/' + REPOSITORY + '/releases?per_page=100', path, 4 * 1024 * 1024)
    releases = json.loads(path.read_text())
    candidates = []
    for release in releases:
        if release.get('draft'):
            continue
        tag = release.get('tag_name', '')
        if not tag.startswith('v') or not VERSION.fullmatch(tag[1:]):
            continue
        version = tag[1:]
        # Stable installations stay on stable releases; preview installations
        # follow previews until a stable release supersedes them.
        if '-' not in current and (release.get('prerelease') or '-' in version):
            continue
        candidates.append(version)
    if not candidates:
        raise ValueError('No published release is available for this update channel.')
    return max(candidates, key=version_key)


def verified_source(version, folder):
    base = 'https://github.com/' + REPOSITORY + '/releases/download/v' + version + '/'
    metadata = folder / 'release.json'
    download(base + 'release.json', metadata, 16384)
    record = json.loads(metadata.read_text())
    name = 'omarchy-parent-controls-' + version + '.tar.gz'
    if (record.get('repository') != REPOSITORY or record.get('version') != version
            or record.get('archive') != name
            or not re.fullmatch(r'[0-9a-f]{64}', record.get('sha256', ''))):
        raise ValueError('Invalid release metadata.')
    archive = folder / name
    download(base + name, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('Release checksum mismatch; nothing was installed.')
    source = unpack(archive, folder / 'source')
    manifest = json.loads((source / 'manifest.json').read_text())
    if manifest.get('version') != version or manifest.get('id') != 'thesnarkitecht.kids-lockdown':
        raise ValueError('Release manifest does not match the selected release.')
    if not (source / 'packaging/setup.py').is_file():
        raise ValueError('The release has no installer.')
    return source


def unpack(archive, destination):
    """Extract regular files only, after validating every archive member."""
    with tarfile.open(archive, 'r:gz') as bundle:
        members = []
        seen = set()
        size = 0
        for item in bundle:
            path = PurePosixPath(item.name)
            size += item.size
            if (path.is_absolute() or '..' in path.parts or not path.parts
                    or path.parts[0] != 'omarchy-parent-controls'
                    or not (item.isfile() or item.isdir()) or path in seen
                    or item.size < 0 or size > 128 * 1024 * 1024 or len(members) >= 4000):
                raise ValueError('Unsafe release archive; nothing was installed.')
            seen.add(path)
            members.append(item)
        destination.mkdir(mode=0o700)
        for item in members:
            target = destination / item.name
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(item) as source, target.open('xb') as out:
                    import shutil
                    shutil.copyfileobj(source, out)
                target.chmod(0o755 if item.mode & 0o111 else 0o644)
    return destination / 'omarchy-parent-controls'


def backup_settings():
    folder = STATE / 'update-backups'
    folder.mkdir(mode=0o700, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=time.strftime('%Y%m%d-%H%M%S-'), suffix='.tar.gz', dir=folder)
    with os.fdopen(fd, 'wb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as bundle:
        bundle.add(ETC, arcname='etc/omarchy-kids')
        for path in sorted(STATE.iterdir()):
            if path.name != 'update-backups':
                bundle.add(path, arcname='var/lib/omarchy-kids-control/' + path.name)
        voice = Path('/etc/school-voice')
        if voice.exists():
            bundle.add(voice, arcname='etc/school-voice')
    return name


@contextlib.contextmanager
def update_lock():
    fd = os.open('/run/lock/omarchy-parent-controls-update.lock',
                 os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another parent-controls update is already running.') from None
        yield


def upgrade(check=False):
    current = installed()
    with tempfile.TemporaryDirectory(prefix='omarchy-parent-controls-', dir=STAGING) as temp:
        folder = Path(temp)
        candidate = latest(current, folder)
        if version_key(candidate) <= version_key(current):
            print('Parent Controls ' + current + ' is up to date.')
            return
        print('Parent Controls: ' + current + ' → ' + candidate, flush=True)
        if check:
            print('Run omarchy-parent-controls update to install it (parent PIN required).')
            return
        source = verified_source(candidate, folder)
        account = json.loads((ETC / 'account.json').read_text())
        backup = backup_settings()
        print('Settings backup: ' + backup, flush=True)
        try:
            subprocess.run(['/usr/bin/python3', '-I', '-B', str(source / 'packaging/setup.py'),
                            '--user', account['user'], '--skip-apps'], check=True,
                           env={'PATH': '/usr/local/bin:/usr/bin', 'HOME': '/root', 'LANG': 'C.UTF-8'})
        except subprocess.CalledProcessError:
            raise ValueError('Update did not finish. Settings backup: ' + backup +
                             '. Fix the reported error and run update again; no automatic rollback was performed.') from None
        print('Updated to Parent Controls ' + candidate + '.')


def main():
    parser = argparse.ArgumentParser(description='Install service updates and inspect Omarchy Parent Controls')
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('version', help='Show the installed version')
    sub.add_parser('status', help='Show control and service status')
    pair = sub.add_parser('pair', help='Show a temporary pairing code for the parent phone (parent PIN required)')
    pair.add_argument('--wait', action='store_true', help='Keep the pairing screen open')
    sub.add_parser('resume', help='Resume a paused laptop using the parent PIN')
    sub.add_parser('unpair', help='Disconnect all parent phones (parent PIN required)')
    sub.add_parser('restart', help='Restart services (parent PIN required)')
    update = sub.add_parser('update', help='Install the newest published release (parent PIN required)')
    update.add_argument('--check', action='store_true', help='Check for updates without making changes')
    args = parser.parse_args()
    privileged = args.action in ('restart', 'pair', 'unpair', 'resume') or (args.action == 'update' and not args.check)
    if privileged and os.geteuid() != 0:
        # Re-enter only the installed, root-owned command, with fixed arguments.
        os.execv('/usr/bin/sudo', ['sudo', '--', '/usr/local/bin/omarchy-parent-controls', args.action] + (['--wait'] if getattr(args, 'wait', False) else []))
    try:
        if args.action == 'version':
            print('Parent Controls ' + installed())
        elif args.action == 'status':
            print('Parent Controls ' + installed(), flush=True)
            print('Controlled mode: ' + ('on' if (ETC / 'controlled-on').exists() else 'off'), flush=True)
            return subprocess.run(['/usr/bin/systemctl', '--no-pager', 'status',
                                   'omarchy-kids-control.service', 'omarchy-kids-policy.service',
                                   'omarchy-kids-audio.socket', 'omarchy-kids-relay.service',
                                   'omarchy-kids-access.timer', 'omarchy-kids-activity.service']).returncode
        elif args.action == 'resume':
            from client import request
            request('access-admin', paused=False)
            print('Computer access resumed.')
        elif args.action in ('pair', 'unpair'):
            from pair_parent import main as pair
            return pair(['--revoke-all'] if args.action == 'unpair' else (['--qr', '--wait'] if args.wait else ['--qr']))
        elif args.action == 'restart':
            with update_lock():
                subprocess.run(['/usr/bin/systemctl', 'restart', 'omarchy-kids-control.service'], check=True)
                subprocess.run(['/usr/bin/systemctl', 'try-restart', 'omarchy-kids-policy.service',
                                'omarchy-kids-audio.service', 'omarchy-kids-remote.service',
                                'omarchy-kids-relay.service', 'omarchy-kids-activity.service'], check=True)
            print('Parent Controls services restarted.')
        elif args.check:
            upgrade(check=True)
        else:
            with update_lock():
                upgrade()
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as error:
        print('Parent Controls: ' + str(error), file=__import__('sys').stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
