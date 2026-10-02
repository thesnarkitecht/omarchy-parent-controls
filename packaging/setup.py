"""Install/update the privileged companion. Run from the verified release bundle."""
import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[1]
LIB = Path('/usr/local/lib/omarchy-kids')
ETC = Path('/etc/omarchy-kids')
STATE = Path('/var/lib/omarchy-kids-control')
BUNDLE = Path('/usr/local/share/omarchy-kids/bundle')
PLUGIN_ID = 'thesnarkitecht.kids-lockdown'
sys.path.insert(0, str(SOURCE/'kids'))

def run(*command, **options):
    return subprocess.run(list(command), check=True, **options)

def target_user(name):
    if not name or not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', name):
        raise ValueError('Choose an existing non-root Omarchy account with --user NAME.')
    user = pwd.getpwnam(name)
    if user.pw_uid < 1000 or Path(user.pw_dir) != Path('/home')/name:
        raise ValueError('This release supports regular accounts with a standard /home/NAME directory.')
    return user

def trusted_binary(value):
    path = Path(value).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError('Hermes executable was not found.')
    for parent in [path, *path.parents]:
        info = parent.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('Hermes must be installed in a root-owned location, not a writable download directory.')
    with path.open('rb') as binary:
        if binary.read(4) != b'\x7fELF':
            raise ValueError('Select the installed Hermes Desktop executable, not a shell wrapper.')
    return str(path)

def write(path, value, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # System destinations are root-owned; never follow a substituted link.
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'w') as stream:
        stream.write(value)
    os.chmod(path, mode)

def copy(source, destination, mode=0o644):
    write(destination, Path(source).read_text(), mode)

def as_user(user, *command, **options):
    return run('/usr/bin/runuser','-u',user.pw_name,'--',*command,**options)

def user_write(user, path, data):
    as_user(user, '/usr/bin/mkdir','-p',str(Path(path).parent))
    as_user(user, '/usr/bin/tee',str(path),input=data,text=True,stdout=subprocess.DEVNULL)

def save_recovery(user):
    path = STATE/'installation.json'
    if path.exists():
        saved = json.loads(path.read_text())
        if saved['user'] != user.pw_name:
            raise ValueError('This computer already has a different controlled account.')
        return
    groups = run('/usr/bin/id','-nG',user.pw_name,capture_output=True,text=True).stdout.split()
    shadow = run('/usr/bin/getent','shadow','root',capture_output=True,text=True).stdout.split(':')[1]
    # Preserve the original baseline when upgrading the development VM.
    legacy = STATE/'native-backup'
    if (legacy/'groups').exists(): groups=(legacy/'groups').read_text().split()
    if (legacy/'root-password').exists(): shadow=(legacy/'root-password').read_text().strip().split(':',1)[1]
    handlers={}
    for scheme in ('http','https'):
        value=as_user(user,'/usr/bin/xdg-mime','query','default','x-scheme-handler/'+scheme,capture_output=True,text=True).stdout.strip()
        handlers[scheme]=value if value and value!='omarchy-kids-approved-browser.desktop' else 'chromium.desktop'
    write(path,json.dumps({'user':user.pw_name,'uid':user.pw_uid,'groups':groups,'root_shadow':shadow,'handlers':handlers})+'\n',0o600)

def main():
    parser=argparse.ArgumentParser(description='Set up native Omarchy parent controls')
    parser.add_argument('--user',default=os.environ.get('SUDO_USER'))
    parser.add_argument('--hermes-binary')
    parser.add_argument('--with-hermes', action='store_true', help='Install and approve the sandboxed terminal Hermes agent')
    parser.add_argument('--model-host',help='IP address of the existing local model server')
    parser.add_argument('--model-port',type=int,default=11434)
    parser.add_argument('--check',action='store_true',help='Read-only preflight')
    parser.add_argument('--skip-apps',action='store_true',help='Keep the current app set')
    parser.add_argument('--voice-pairing',help='Install integrated voice using this Laya device pairing directory')
    args=parser.parse_args()
    user=target_user(args.user)
    if not Path('/etc/arch-release').exists() or not Path('/usr/share/omarchy').is_dir():
        raise ValueError('This release requires Arch Linux with Omarchy 4.')
    previous=json.loads((ETC/'account.json').read_text()) if (ETC/'account.json').exists() else {}
    if previous and previous['uid'] != user.pw_uid:
        raise ValueError('Only one controlled desktop account is supported per computer.')
    controlled = not previous or (ETC/'controlled-on').exists()
    config={**previous,'user':user.pw_name,'uid':user.pw_uid,'plugin_id':PLUGIN_ID}
    candidate=args.hermes_binary or config.get('hermes_binary')
    if candidate:
        config['hermes_binary']=trusted_binary(candidate)
    if args.model_host:
        if not 1 <= args.model_port <= 65535: raise ValueError('Invalid model server port.')
        config['model_endpoint']={'host':str(ipaddress.ip_address(args.model_host)),'port':args.model_port}
    if config.get('hermes_binary') and not config.get('model_endpoint'):
        raise ValueError('Managed Hermes needs the local model server IP: --model-host ADDRESS [--model-port PORT].')
    if args.check:
        print('Preflight passed for '+user.pw_name+'. No system changes made.')
        return
    if os.geteuid() != 0: raise ValueError('Run install.sh to request administrator approval.')
    if not (ETC/'managed-by-installer').exists():
        for name in ('omarchy-kids','omarchy-kids-hermes'):
            try: pwd.getpwnam(name)
            except KeyError: pass
            else: raise ValueError('Refusing to reuse an unrelated service account: '+name)
    packages=['python','pyside6','acl','nftables','chromium','mpv','yt-dlp','qrencode','bubblewrap']
    if not args.skip_apps and not previous:
        packages += ['gnome-calculator','papers','file-roller','gnome-text-editor']
    run('/usr/bin/pacman','-S','--needed','--noconfirm',*packages)
    ETC.mkdir(parents=True,exist_ok=True)
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    STATE.chmod(0o700)
    save_recovery(user)
    shared_acl = STATE/'shared-folders.acl'
    if not shared_acl.exists():
        paths=[Path(user.pw_dir)] + [Path(user.pw_dir)/name for name in ('Downloads','Documents','Projects') if (Path(user.pw_dir)/name).exists()]
        write(shared_acl,run('/usr/bin/getfacl','-p',*map(str,paths),capture_output=True,text=True).stdout,0o600)
    if not (ETC/'managed-by-installer').exists():
        run('/usr/bin/groupadd','--system','omarchy-kids')
        for name in ('omarchy-kids','omarchy-kids-hermes'):
            run('/usr/bin/useradd','--system','--gid','omarchy-kids','--home-dir','/var/lib/'+name,'--shell','/usr/bin/nologin',name)
        write(ETC/'managed-by-installer','parent-controls\n')
    for name in ('omarchy-kids','omarchy-kids-hermes'):
        run('/usr/bin/usermod','--lock','--groups','','--shell','/usr/bin/nologin',name)
    write(ETC/'account.json',json.dumps(config)+'\n')
    for path in (LIB,BUNDLE/'native',BUNDLE/'integration',Path('/usr/local/share/omarchy-kids/applications'),Path('/usr/local/share/applications/omarchy-kids'),Path('/etc/chromium/policies/managed')):
        path.mkdir(parents=True,exist_ok=True)
    for item in (SOURCE/'kids').glob('*.py'): copy(item,LIB/item.name)
    copy(SOURCE/'native/native-ui.py',LIB/'native-ui.py')
    for name in ('run','omarchy-parent-controls','omarchy-kids','omarchy-kids-admin','omarchy-kids-webapp','omarchy-kids-open-url','omarchy-kids-videos'):
        copy(SOURCE/'bin'/name,LIB/'run' if name=='run' else Path('/usr/local/bin')/name,0o755)
    copy(SOURCE/'native/pam-pin',LIB/'pam-pin',0o755)
    copy(SOURCE/'native/windows-pkexec',LIB/'windows-tools/pkexec',0o755)
    copy(SOURCE/'native/omarchy-kids-sudo','/etc/pam.d/omarchy-kids-sudo')
    copy(SOURCE/'packaging/remove.py',LIB/'remove.py')
    copy(SOURCE/'integration/omarchy-kids.desktop',BUNDLE/'integration/omarchy-kids.desktop')
    copy(SOURCE/'integration/omarchy-kids.desktop','/usr/local/share/applications/omarchy-kids.desktop')
    copy(SOURCE/'integration/little-screen.desktop','/usr/local/share/applications/little-screen.desktop')
    copy(SOURCE/'native/video-input.conf',LIB/'video-input.conf')
    copy(SOURCE/'native/pulse-client.conf',LIB/'pulse-client.conf')
    copy(SOURCE/'systemd/omarchy-kids-audio.socket','/etc/systemd/system/omarchy-kids-audio.socket')
    write('/etc/systemd/system/omarchy-kids-audio.service',
          (SOURCE/'systemd/omarchy-kids-audio.service').read_text().replace('@CHILD_USER@', user.pw_name))
    copy(SOURCE/'systemd/omarchy-kids-remote.service','/etc/systemd/system/omarchy-kids-remote.service')
    copy(SOURCE/'native/approved-browser.desktop','/usr/local/share/applications/omarchy-kids-approved-browser.desktop')
    if config.get('hermes_binary'):
        launcher=Path('/usr/local/bin/hermes-desktop')
        saved=STATE/'hermes-desktop.original'
        if launcher.exists() and not saved.exists() and 'omarchy-kids' not in launcher.read_text(errors='replace'):
            copy(launcher,saved,0o700)
        copy(SOURCE/'native/hermes-desktop','/usr/local/bin/hermes-desktop',0o755)
        write('/usr/local/share/applications/omarchy-kids-hermes.desktop','[Desktop Entry]\nType=Application\nName=Hermes\nExec=/usr/local/bin/hermes-desktop\nIcon=hermes\nTerminal=false\nCategories=Utility;\n')
    from coding import prepare
    prepare(user)
    from hermes_install import selected, ensure
    if args.with_hermes or selected(user):
        if args.with_hermes:
            write(STATE/'approved-agent', 'hermes\n', 0o600)
            if (ETC/'controlled-on').exists():
                # Remove any old deny ACL on a previously unselected Hermes
                # runtime before checking the newly approved CLI as the child.
                from native_policy import apply
                apply()
        ensure(user)
    for name in ('omarchy-kids','omarchy-kids-hermes'):
        owner=pwd.getpwnam(name)
        destinations=['/var/lib/omarchy-kids/data','/var/lib/omarchy-kids/icons'] if name=='omarchy-kids' else ['/var/lib/omarchy-kids/hermes-home']
        for folder in destinations:
            path=Path(folder);path.mkdir(parents=True,exist_ok=True);os.chown(path,owner.pw_uid,owner.pw_gid);path.chmod(0o755 if path.name=='icons' else 0o700)
    prepare_home(user,config)
    migrate_plugin(user,previous.get('plugin_id','.'.join(('local','kids-lockdown'))))
    for name in ('manifest.json','Controls.qml','BarWidget.qml'):
        user_write(user,Path(user.pw_dir)/'.config/omarchy/plugins/thesnarkitecht.kids-lockdown'/name,(SOURCE/name).read_text())
    copy(SOURCE/'systemd/omarchy-kids-control.service','/etc/systemd/system/omarchy-kids-control.service')
    copy(SOURCE/'native/omarchy-kids-policy.service','/etc/systemd/system/omarchy-kids-policy.service')
    copy(SOURCE/'native/policy-refresh.hook','/etc/pacman.d/hooks/95-omarchy-kids.hook')
    for label,operation in [('enable','on'),('disable','off')]:
        write('/etc/systemd/system/omarchy-kids-'+label+'.service','[Unit]\nDescription=Omarchy parent controls '+operation+'\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 -I /usr/local/lib/omarchy-kids/native_mode.py '+operation+'\n')
    write('/etc/systemd/system/display-manager.service.d/omarchy-kids.conf','[Unit]\nWants=omarchy-kids-policy.service\nAfter=omarchy-kids-policy.service\n[Service]\nExecStartPre=/usr/bin/python3 -I /usr/local/lib/omarchy-kids/boot_guard.py\n')
    # Omarchy can start through a TTY/UWSM or a lingering user manager, without
    # a display manager. Gate the actual child's user manager in every case.
    write('/etc/systemd/system/user@'+str(user.pw_uid)+'.service.d/omarchy-kids.conf','[Unit]\nWants=omarchy-kids-policy.service\nAfter=omarchy-kids-policy.service\n[Service]\nExecStartPre=/usr/bin/python3 -I /usr/local/lib/omarchy-kids/boot_guard.py\n')
    runtime_dropin=Path('/etc/systemd/system/user-runtime-dir@'+str(user.pw_uid)+'.service.d/omarchy-kids.conf')
    if runtime_dropin.exists() and 'ExecStartPost=/usr/bin/mount -o remount,noexec' in runtime_dropin.read_text():
        # Migrate the development build's unconditional runtime restriction.
        Path('/run/omarchy-kids-runtime-noexec').touch(mode=0o600)
    write(runtime_dropin,'[Service]\nExecStartPost=/usr/bin/python3 -I /usr/local/lib/omarchy-kids/runtime_guard.py\n')
    write('/etc/systemd/system/omarchy-kids-rollback.service','[Unit]\nDescription=Recover unconfirmed parent-controls setup\nConditionPathExists=!/etc/omarchy-kids/native-confirmed\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 -I /usr/local/lib/omarchy-kids/remove.py --recovery\n')
    write('/etc/systemd/system/omarchy-kids-rollback.timer','[Unit]\nDescription=Recover unconfirmed parent-controls setup\n[Timer]\nOnActiveSec=15min\n[Install]\nWantedBy=timers.target\n')
    from control import Store
    from native_policy import BANNED, RUNTIME_COMMANDS
    fresh=not (STATE/'pin.json').exists()
    new_pin=None
    if fresh:
        new_pin=getpass.getpass('Choose parent PIN (8–12 digits): ')
        if new_pin != getpass.getpass('Repeat parent PIN: '): raise ValueError('PINs did not match.')
        Store().initialize(new_pin)
    denied=json.loads((ETC/'denied-commands.json').read_text()) if (ETC/'denied-commands.json').exists() else []
    write(ETC/'denied-commands.json',json.dumps(sorted((set(BANNED)|set(denied))-RUNTIME_COMMANDS),indent=2)+'\n')
    run('/usr/bin/systemctl','daemon-reload')
    run('/usr/bin/systemctl','enable','--now','omarchy-kids-audio.socket')
    run('/usr/bin/systemctl','try-restart','omarchy-kids-audio.service')
    run('/usr/bin/systemctl','enable','--now','omarchy-kids-control.service')
    run('/usr/bin/systemctl','restart','omarchy-kids-control.service')
    run('/usr/bin/systemctl','enable','--now','omarchy-kids-rollback.timer')
    install_auth(user)
    if new_pin:
        result=as_user(user,'/usr/bin/sudo','-k','-S','-p','','--','/usr/bin/true',input=new_pin+'\n',text=True,capture_output=True)
        new_pin=None
    for group in ('wheel','sudo','docker','lxd','lxc','incus-admin','disk'):
        subprocess.run(['/usr/bin/gpasswd','-d',user.pw_name,group],capture_output=True)
    run('/usr/bin/usermod','--lock','root')
    run('/usr/bin/systemctl','enable','omarchy-kids-policy.service')
    run('/usr/bin/systemctl','start','omarchy-kids-enable.service' if controlled else 'omarchy-kids-disable.service')
    write(ETC/'native-confirmed','PIN authentication configured\n')
    run('/usr/bin/systemctl','disable','--now','omarchy-kids-rollback.timer')
    if args.voice_pairing or Path('/etc/school-voice/policy.json').exists():
        sys.path.insert(0, str(SOURCE/'packaging'))
        from install_voice import install
        install(SOURCE, args.voice_pairing, user)
    as_user(user,'/usr/bin/xdg-mime','default','omarchy-kids-approved-browser.desktop','x-scheme-handler/http','x-scheme-handler/https')
    environment={**os.environ,'OMARCHY_PATH':'/usr/share/omarchy','XDG_RUNTIME_DIR':'/run/user/'+str(user.pw_uid)}
    as_user(user,'/usr/bin/omarchy','bar','put','thesnarkitecht.kids-lockdown','--after','omarchy.clock',env=environment)
    run('/usr/bin/systemctl','try-restart','omarchy-kids-remote.service')
    from control import atomic_json
    atomic_json(LIB/'release.json', {'version':json.loads((SOURCE/'manifest.json').read_text())['version']})
    os.chmod(LIB/'release.json', 0o644)
    print('Parent controls installed. Open the lock icon in the bar. Keep your PIN private.')

def migrate_plugin(user,old_id):
    if old_id==PLUGIN_ID: return
    if not re.fullmatch(r'[a-z0-9-]+\.[a-z0-9-]+',old_id): raise ValueError('Invalid previous plugin identifier.')
    path=Path(user.pw_dir)/'.config/omarchy/shell.json'
    text=as_user(user,'/usr/bin/cat',str(path),capture_output=True,text=True).stdout
    user_write(user,path,text.replace(json.dumps(old_id),json.dumps(PLUGIN_ID)))
    # Remove the development widget from the original restoration snapshot.
    # Off-mode adds the current Parents widget explicitly.
    backup=STATE/'native-backup/ui/shell.json'
    if backup.exists():
        def clean(value):
            if isinstance(value,list): return [clean(v) for v in value if not(isinstance(v,dict) and v.get('id')==old_id)]
            if isinstance(value,dict): return {key:clean(v) for key,v in value.items()}
            return value
        write(backup,json.dumps(clean(json.loads(backup.read_text())),indent=2)+'\n',0o600)
    as_user(user,'/usr/bin/rm','-rf','--',str(Path(user.pw_dir)/'.config/omarchy/plugins'/old_id))

def prepare_home(user,config):
    home=Path(user.pw_dir)
    for relative,default in [('.config/omarchy/extensions/omarchy-menu.jsonc','{}\n'),('.config/omarchy/shell.json','{}\n')]:
        if not (home/relative).exists(): user_write(user,home/relative,default)
    run('/usr/bin/setfacl','-m','u:omarchy-kids:--x,u:omarchy-kids-hermes:--x',str(home))
    for name in ('Downloads','Documents','Projects'):
        as_user(user,'/usr/bin/mkdir','-p',str(home/name))
        run('/usr/bin/setfacl','-m','u:omarchy-kids-hermes:rwx',str(home/name))
        run('/usr/bin/setfacl','-d','-m','u:'+user.pw_name+':rwx,u:omarchy-kids-hermes:rwx',str(home/name))
    run('/usr/bin/setfacl','-m','u:omarchy-kids:rwx',str(home/'Downloads'))
    agent=pwd.getpwnam('omarchy-kids-hermes')
    agent_home=Path('/var/lib/omarchy-kids/hermes-home')
    for name in ('.hermes','.config','.cache','.local/share'):
        folder=agent_home/name;folder.mkdir(parents=True,exist_ok=True);os.chown(folder,agent.pw_uid,agent.pw_gid);folder.chmod(0o700)
    for name in ('config.yaml','.env'):
        dest=agent_home/'.hermes'/name
        if config.get('hermes_binary') and not dest.exists() and (home/'.hermes'/name).exists():
            data=as_user(user,'/usr/bin/cat',str(home/'.hermes'/name),capture_output=True,text=True).stdout
            write(dest,data,0o600);os.chown(dest,agent.pw_uid,agent.pw_gid)

def install_auth(user):
    name=user.pw_name
    write('/etc/sudoers.d/zzzz-omarchy-kids-parent-pin',f'Defaults:{name} authenticate, timestamp_timeout=0, pam_service="omarchy-kids-sudo", pam_login_service="omarchy-kids-sudo", passprompt="Parent PIN: ", !rootpw, !targetpw, !runaspw\n{name} ALL=(ALL:ALL) PASSWD: ALL\n',0o440)
    run('/usr/bin/visudo','-c')
    allowed=['org.freedesktop.login1.'+x for x in ('power-off','reboot','suspend','hibernate')]
    allowed += ['org.freedesktop.NetworkManager.'+x for x in ('network-control','enable-disable-network','enable-disable-wifi','wifi.scan','settings.modify.own','settings.modify.system')]
    write('/etc/polkit-1/rules.d/00-omarchy-child-account.rules','polkit.addRule(function(action, subject) {\n  if (subject.user !== '+json.dumps(name)+') return;\n  if (subject.local && subject.active && '+json.dumps(allowed)+'.indexOf(action.id) >= 0) return polkit.Result.YES;\n  return polkit.Result.NO;\n});\n')

if __name__=='__main__':
    try: main()
    except (ValueError,OSError,KeyError,subprocess.SubprocessError) as error:
        print('Setup did not finish: '+str(error),file=sys.stderr)
        raise SystemExit(1)
