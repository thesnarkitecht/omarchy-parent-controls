"""PIN-authorized removal, also used by the first-install recovery timer.

Keep private PIN/policy/recovery data for reinstall; never erase family documents.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
sys.path.insert(0,'/usr/local/lib/omarchy-kids')
STATE=Path('/var/lib/omarchy-kids-control')
LIB=Path('/usr/local/lib/omarchy-kids')
ETC=Path('/etc/omarchy-kids')

def run(*args,check=True,**kwargs):
    return subprocess.run(args,check=check,**kwargs)

def unlink(path): Path(path).unlink(missing_ok=True)

def restore_authentication(saved,user):
    run('/usr/bin/usermod','--groups',','.join(saved['groups']),user.pw_name)
    run('/usr/bin/chpasswd','--encrypted',input=('root:'+saved['root_shadow']+'\n').encode())
    unlink('/etc/sudoers.d/zzzz-omarchy-kids-parent-pin')
    unlink('/etc/polkit-1/rules.d/00-omarchy-child-account.rules')
    run('/usr/bin/visudo','-c')

def main():
    parser=argparse.ArgumentParser(description='Remove parent controls and restore the original account permissions')
    parser.add_argument('--recovery',action='store_true',help='Restore administrator access even if cleanup fails')
    args=parser.parse_args()
    if os.geteuid()!=0: raise SystemExit('Run sudo python3 -I /usr/local/lib/omarchy-kids/remove.py and enter the parent PIN.')
    saved=json.loads((STATE/'installation.json').read_text())
    user=pwd.getpwnam(saved['user'])
    if user.pw_uid != saved['uid']: raise SystemExit('Account UID changed; recovery requires administrator review.')
    config=json.loads((ETC/'account.json').read_text())
    failures=[]
    if args.recovery:
        # A broken display configuration or busy mount must not prevent the
        # recovery timer from restoring the original administrator access.
        restore_authentication(saved,user)
    try:
        run('/usr/bin/python3','-I',str(LIB/'native_mode.py'),'off')
    except subprocess.CalledProcessError as error:
        if not args.recovery: raise
        failures.append(str(error))
    # Restore the original UI once more: mode-off deliberately retains Parents.
    backup=STATE/'native-backup/ui'
    destinations={'shell.json':'.config/omarchy/shell.json','omarchy-menu.jsonc':'.config/omarchy/extensions/omarchy-menu.jsonc',
                  'hyprland.lua':'.config/hypr/hyprland.lua','bindings.lua':'.config/hypr/bindings.lua'}
    for name,relative in destinations.items():
        if (backup/name).exists():
            run('/usr/bin/runuser','-u',user.pw_name,'--','/usr/bin/tee',str(Path(user.pw_dir)/relative),input=(backup/name).read_bytes(),stdout=subprocess.DEVNULL)
    # Authentication is restored before deleting any helper it depends on.
    if not args.recovery: restore_authentication(saved,user)
    if (STATE/'family.json').exists():
        from family import revoke
        from control import Store
        revoke(Store())
    for unit in ('omarchy-kids-audio.socket','omarchy-kids-audio.service','omarchy-kids-remote','omarchy-kids-control','omarchy-kids-policy','omarchy-kids-rollback.timer'):
        run('/usr/bin/systemctl','disable','--now',unit,check=False)
    for path in Path('/etc/systemd/system').glob('omarchy-kids-*.service'): path.unlink()
    unlink('/etc/systemd/system/omarchy-kids-rollback.timer')
    unlink('/etc/systemd/system/omarchy-kids-audio.socket')
    unlink('/etc/systemd/system/display-manager.service.d/omarchy-kids.conf')
    unlink('/etc/systemd/system/user@'+str(user.pw_uid)+'.service.d/omarchy-kids.conf')
    unlink('/etc/systemd/system/user-runtime-dir@'+str(user.pw_uid)+'.service.d/omarchy-kids.conf')
    unlink('/etc/pacman.d/hooks/95-omarchy-kids.hook')
    unlink('/etc/pam.d/omarchy-kids-sudo')
    unlink('/etc/chromium/policies/managed/omarchy-kids.json')
    unlink(ETC/'controlled-on')
    unlink(ETC/'native-confirmed')
    # Remove named worker ACLs, then restore original shared-folder ACLs.
    for folder in [Path(user.pw_dir)]+[Path(user.pw_dir)/n for n in ('Downloads','Documents','Projects')]:
        if folder.is_dir():
            run('/usr/bin/setfacl','-x','u:omarchy-kids,u:omarchy-kids-hermes',str(folder),check=False)
            run('/usr/bin/setfacl','-x','d:u:omarchy-kids,d:u:omarchy-kids-hermes',str(folder),check=False)
    if (STATE/'shared-folders.acl').exists():
        from native_policy import restore_acls
        restore_acls(STATE/'shared-folders.acl')
    for name in ('omarchy-kids','omarchy-kids-admin','omarchy-kids-webapp','omarchy-kids-open-url','omarchy-kids-videos'):
        unlink('/usr/local/bin/'+name)
    original=STATE/'hermes-desktop.original'
    if original.exists(): shutil.copyfile(original,'/usr/local/bin/hermes-desktop');os.chmod('/usr/local/bin/hermes-desktop',0o755)
    elif config.get('hermes_binary'):
        # Development installs may predate the launcher backup. Preserve the
        # installed upstream app with a minimal normal launcher.
        launcher=Path('/usr/local/bin/hermes-desktop')
        launcher.write_text('#!/usr/bin/python3 -I\nimport os, sys\nos.environ.update('+repr(config.get('hermes_environment',{}))+')\nbinary='+repr(config['hermes_binary'])+'\nos.execv(binary,[binary,*sys.argv[1:]])\n')
        launcher.chmod(0o755)
    for name in ('omarchy-kids.desktop','omarchy-kids-approved-browser.desktop','omarchy-kids-hermes.desktop','little-screen.desktop'):
        unlink('/usr/local/share/applications/'+name)
    for path in Path('/usr/local/share/applications/omarchy-kids').glob('webapp-*.desktop'):
        path.unlink()
    run('/usr/bin/runuser','-u',user.pw_name,'--','/usr/bin/rm','-rf','--',str(Path(user.pw_dir)/'.config/omarchy/plugins/thesnarkitecht.kids-lockdown'))
    for scheme in ('http','https'):
        run('/usr/bin/runuser','-u',user.pw_name,'--','/usr/bin/xdg-mime','default',saved.get('handlers',{}).get(scheme,'chromium.desktop'),'x-scheme-handler/'+scheme,check=False)
    run('/usr/bin/systemctl','daemon-reload')
    print('Controls removed. Parent PIN, approved sites and recovery backups remain private for reinstall.')
    if failures:
        print('Administrator access restored, but cleanup needs attention: '+'; '.join(failures),file=sys.stderr)
        raise SystemExit(1)

if __name__=='__main__': main()
