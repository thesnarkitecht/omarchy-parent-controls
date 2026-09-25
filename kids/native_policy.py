"""Machine-enforced restrictions for the normal Omarchy child UID."""
import json
import ipaddress
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_runtime import account, is_mountpoint, APPS

STATE = Path('/var/lib/omarchy-kids-control')
BOOT_ID = Path('/proc/sys/kernel/random/boot_id')
BANNED = (
    'code', 'cursor',
    'chromium', 'firefox', 'google-chrome', 'google-chrome-stable', 'brave', 'brave-browser',
    'zen-browser', 'vivaldi', 'vivaldi-stable', 'microsoft-edge-stable',
    'epiphany', 'falkon', 'qutebrowser', 'dillo', 'cog', 'lynx', 'links', 'w3m',
    'discord', 'signal-desktop', 'telegram-desktop', 'slack', 'zoom', 'thunderbird', 'localsend',
    'claude', 'codex', 'copilot', 'crush', 'cursor-agent', 'gemini', 'grok', 'muse', 'omp',
    'openclaw', 'opencode', 'pi', 'mise', 'uv', 'pip', 'pip3', 'pipx', 'yay', 'paru',
    'pacman', 'pamac', 'flatpak', 'snap', 'docker', 'podman', 'nerdctl', 'npm', 'pnpm', 'yarn',
)


def command(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)

def model_rule(config, uid):
    endpoint = config.get('model_endpoint')
    if endpoint is None:
        return ''
    host = ipaddress.ip_address(endpoint['host'])
    port = endpoint['port']
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid model endpoint port')
    family = 'ip' if host.version == 4 else 'ip6'
    return f'  meta skuid {uid} {family} daddr {host} tcp dport {port} accept\n'


def targets():
    values = set()
    denied_file = Path('/etc/omarchy-kids/denied-commands.json')
    denied = json.loads(denied_file.read_text()) if denied_file.exists() else BANNED
    if not isinstance(denied, (list,tuple)) or not all(isinstance(x,str) and re.fullmatch(r'[A-Za-z0-9_.+-]+',x) for x in denied):
        raise ValueError('Invalid command denylist')
    for base in ('/usr/bin', '/usr/local/bin', '/opt'):
        for name in denied:
            p = Path(base) / name
            if p.is_file(): values.add(p.resolve())
    for folder in ('/usr/lib/chromium', '/opt/google/chrome', '/usr/lib/firefox', '/opt/brave-bin'):
        root = Path(folder)
        if root.exists():
            for p in root.rglob('*'):
                if p.is_file() and os.access(p, os.X_OK): values.add(p.resolve())
    for p in (Path('/usr/lib/qt6/QtWebEngineProcess'), Path('/usr/lib/qt6/libexec/QtWebEngineProcess')):
        if p.exists(): values.add(p.resolve())
    # The desktop contains an embedded browser. Only its isolated service UID
    # may execute this binary while controls are on.
    hermes = Path(account().get('hermes_binary', '/opt/hermes-desktop/Hermes'))
    if hermes.exists(): values.add(hermes.resolve())
    for p in Path('/usr/bin').glob('electron*'):
        if p.is_file(): values.add(p.resolve())
    return sorted(p for p in values if p.stat().st_uid == 0)


def restore_acls(backup):
    # Package updates may remove files recorded in the original ACL snapshot.
    # Restore surviving paths physically, without following replacement links.
    blocks = backup.read_text().split('\n\n')
    keep = []
    for block in blocks:
        match = re.search(r'^# file: (.+)$', block, re.M)
        if match:
            path = Path(match.group(1))
            if path.exists() and not path.is_symlink(): keep.append(block)
    if keep:
        command(['/usr/bin/setfacl', '-P', '--restore=-'], input='\n\n'.join(keep)+'\n\n')


def tracked_mounts():
    mounts=STATE/'native-mounts.json'
    boot=STATE/'native-mounts-boot-id'
    # Mounts vanish at reboot. Never unmount logind's new runtime filesystem
    # based on a path recorded during the previous boot.
    if boot.exists() and boot.read_text()!=BOOT_ID.read_text(): return []
    return json.loads(mounts.read_text()) if mounts.exists() else []


def mount_options(flags):
    return [('noexec' if flags & os.ST_NOEXEC else 'exec'),
            ('nosuid' if flags & os.ST_NOSUID else 'suid'),
            ('nodev' if flags & os.ST_NODEV else 'dev')]


def release_mount(target, options):
    if not is_mountpoint(target): return True
    # A live desktop may have GVFS/portal submounts or open working directories.
    # Restore the original flags first; a busy bind can safely remain attached
    # without restrictions until logout/reboot, and be reused on reactivation.
    command(['/usr/bin/mount','-o','remount,bind,'+','.join(options),target])
    result=subprocess.run(['/usr/bin/umount',target],capture_output=True)
    return result.returncode==0 or not is_mountpoint(target)


def apply():
    config = account()
    uid, home = config['uid'], pwd.getpwnam(config['user']).pw_dir
    paths = targets()
    backup = STATE / 'native-acls.txt'
    if backup.exists():
        restore_acls(backup)
    saved = backup.read_text() if backup.exists() else ''
    recorded = set(re.findall(r'^# file: (.+)$', saved, re.M))
    new_paths = [p for p in paths if str(p) not in recorded]
    if new_paths:
        result = command(['/usr/bin/getfacl', '-p', *map(str, new_paths)], capture_output=True)
        backup.write_text(saved + result.stdout)
    for path in paths:
        command(['/usr/bin/setfacl', '-m', f'u:{uid}:---', str(path)])
    # Terminal requests are allowed. Only the managed Hermes desktop/agent UID
    # is restricted, including its embedded browser and any subprocesses.
    agent_uid = pwd.getpwnam('omarchy-kids-hermes').pw_uid
    exists = subprocess.run(['/usr/bin/nft', 'list', 'table', 'inet', 'omarchy_kids'], capture_output=True).returncode == 0
    rules = ('delete table inet omarchy_kids\n' if exists else '') + f'''table inet omarchy_kids {{
 chain child_output {{
  type filter hook output priority -150; policy accept;
  meta skuid {agent_uid} ip daddr 127.0.0.1 tcp dport 32768-60999 accept
{model_rule(config, agent_uid)}\
  meta skuid {agent_uid} counter reject
 }}
}}
'''
    command(['/usr/bin/nft', '-f', '-'], input=rules)
    from hosts_policy import apply as apply_hosts, wait_until_applied
    apply_hosts(True)
    subprocess.run(['/usr/bin/resolvectl', 'flush-caches'], capture_output=True)
    wait_until_applied()
    # Writable files cannot become new executable mappings, including through ld.so.
    old = tracked_mounts()
    options_file=STATE/'native-mount-options.json'
    stored_options=json.loads(options_file.read_text()) if options_file.exists() else {}
    options={target:stored_options[target] for target in old if target in stored_options}
    mounted = []
    for target in (home, '/tmp', '/var/tmp', '/dev/shm', '/run/lock', '/run/user/' + str(uid)):
        if not Path(target).exists(): continue
        flags=os.statvfs(target).f_flag
        if flags & os.ST_NOEXEC: continue
        options.setdefault(target,mount_options(flags))
        if target not in old:
            command(['/usr/bin/mount', '--bind', target, target])
        command(['/usr/bin/mount', '-o', 'remount,bind,noexec,nosuid,nodev', target])
        mounted.append(target)
    (STATE / 'native-mounts.json').write_text(json.dumps(list(dict.fromkeys(old + mounted))))
    options_file.write_text(json.dumps(options))
    (STATE / 'native-mounts-boot-id').write_text(BOOT_ID.read_text())
    # Mount after the home restriction, so it remains visible on every boot.
    apps = Path(home) / '.local/share/applications'
    if not is_mountpoint(apps):
        command(['/usr/bin/mount', '--bind', '/usr/local/share/omarchy-kids/applications', str(apps)])
    if not os.path.samefile(apps, APPS):
        raise RuntimeError('The applications directory has an unrelated mount; refusing to replace it.')
    command(['/usr/bin/mount', '-o', 'remount,bind,ro,nosuid,nodev,noexec', str(apps)])
    # Existing browser sessions must not survive policy activation.
    blocked = set(map(str, paths))
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if proc.stat().st_uid == uid and str((proc / 'exe').resolve()) in blocked:
                os.kill(int(proc.name), 15)
        except (OSError, ValueError): pass


def hermes_acl():
    uid = account()['uid']
    folder = Path('/run/omarchy-kids-hermes')
    sock = folder / 'chat.sock'
    for _ in range(100):
        if sock.exists():
            command(['/usr/bin/setfacl', '-m', f'u:{uid}:rx', str(folder)])
            command(['/usr/bin/setfacl', '-m', f'u:{uid}:rw', str(sock)])
            return
        time.sleep(0.2)
    raise RuntimeError('Hermes did not create its chat socket.')


def remove_launcher_mounts(apps):
    # beta.1 could stack bind mounts because os.path.ismount did not see them.
    # Remove every owned layer, leaving unrelated mounts and user files intact.
    for _ in range(64):
        if not is_mountpoint(apps) or not os.path.samefile(apps, APPS):
            return
        command(['/usr/bin/umount', '--lazy', str(apps)])
    raise RuntimeError('Could not detach all controlled launcher mounts.')


def remove():
    config = account()
    apps = pwd.getpwnam(config['user']).pw_dir + '/.local/share/applications'
    remove_launcher_mounts(apps)
    subprocess.run(['/usr/bin/nft', 'delete', 'table', 'inet', 'omarchy_kids'], capture_output=True)
    from hosts_policy import apply as apply_hosts
    apply_hosts(False)
    subprocess.run(['/usr/bin/resolvectl', 'flush-caches'], capture_output=True)
    backup = STATE / 'native-acls.txt'
    if backup.exists(): restore_acls(backup)
    mounts = STATE / 'native-mounts.json'
    if mounts.exists():
        remaining = tracked_mounts()
        options_file=STATE/'native-mount-options.json'
        options=json.loads(options_file.read_text()) if options_file.exists() else {}
        for target in reversed(remaining[:]):
            legacy=['exec','nosuid','nodev'] if target.startswith(('/dev/','/run/')) else ['exec','suid','dev']
            if release_mount(target,options.get(target,legacy)):
                remaining.remove(target)
            mounts.write_text(json.dumps(remaining))
        if not remaining: mounts.unlink()
    runtime_marker=Path('/run/omarchy-kids-runtime-noexec')
    if runtime_marker.exists():
        target='/run/user/'+str(config['uid'])
        if Path(target).exists(): command(['/usr/bin/mount','-o','remount,exec',target])
        runtime_marker.unlink()


def main():
    if os.geteuid() != 0: raise SystemExit('Administrator approval is required.')
    {'apply': apply, 'remove': remove, 'hermes-acl': hermes_acl}[sys.argv[1]]()


if __name__ == '__main__': main()
