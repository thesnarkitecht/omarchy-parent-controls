"""Root-only, fixed on/off transitions for the existing desktop account."""
import os
import pwd
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from native_runtime import account, desktop_entries
from control import Store

def run(*args):
    return subprocess.run(list(args),check=True,text=True)

def disable_policy():
    subprocess.run(['/usr/bin/systemctl','stop','omarchy-kids-policy.service'],
                   capture_output=True, text=True, timeout=90)
    # A failed or already inactive unit does not run ExecStop again. Always
    # reconcile the actual restrictions so retrying off can recover it.
    from native_policy import remove
    remove()
    run('/usr/bin/systemctl','reset-failed','omarchy-kids-policy.service')

def main():
    if os.geteuid() != 0: raise SystemExit(1)
    config=account()
    home=pwd.getpwnam(config['user']).pw_dir
    marker=Path('/etc/omarchy-kids/controlled-on')
    if sys.argv[1] == 'on':
        from parent_tools import ensure_windows_stopped
        ensure_windows_stopped()
        marker.touch(mode=0o644)
        run('/usr/bin/python3','-I','/usr/local/lib/omarchy-kids/native-ui.py')
        desktop_entries(Store().read('policy.json'))
        marker.touch(mode=0o644)
        run('/usr/bin/systemctl','restart','omarchy-kids-policy.service')
    elif sys.argv[1] == 'off':
        from native_runtime import revoke_webapps, CHROME_POLICY
        revoke_webapps()
        # A machine that has never opened Hermes has no transient unit yet.
        if subprocess.run(['/usr/bin/systemctl','is-active','--quiet','omarchy-kids-hermes-desktop.service']).returncode == 0:
            run('/usr/bin/systemctl','stop','omarchy-kids-hermes-desktop.service')
        disable_policy()
        marker.unlink(missing_ok=True)
        CHROME_POLICY.unlink(missing_ok=True)
        backup=Path('/var/lib/omarchy-kids-control/native-backup/ui')
        files={'omarchy-menu.jsonc':'.config/omarchy/extensions/omarchy-menu.jsonc',
               'shell.json':'.config/omarchy/shell.json', 'hyprland.lua':'.config/hypr/hyprland.lua',
               'bindings.lua':'.config/hypr/bindings.lua'}
        for name,dest in files.items():
            if not (backup/name).exists(): continue
            subprocess.run(['/usr/bin/runuser','-u',config['user'],'--','/usr/bin/tee',home+'/'+dest],
                           input=(backup/name).read_bytes(),stdout=subprocess.DEVNULL,check=True)
        # Keep the quick parent toggle available on the unrestricted desktop.
        run('/usr/bin/runuser','-u',config['user'],'--','/usr/bin/env',
            'OMARCHY_PATH=/usr/share/omarchy','XDG_RUNTIME_DIR=/run/user/'+str(config['uid']),
            '/usr/bin/omarchy','bar','put','thesnarkitecht.kids-lockdown','--after','omarchy.clock')
    else: raise SystemExit(2)
    runtime='/run/user/'+str(config['uid'])
    instances=list((Path(runtime)/'hypr').glob('*/.socket.sock'))
    if instances:
        run('/usr/bin/runuser','-u',config['user'],'--','/usr/bin/env',
            'XDG_RUNTIME_DIR='+runtime,'HYPRLAND_INSTANCE_SIGNATURE='+instances[0].parent.name,
            '/usr/bin/hyprctl','reload')
        # Mounting/unmounting the controlled applications folder leaves existing
        # inotify watches attached to the old directory. Reconnect the shell's
        # app provider after the transition; running applications stay open.
        environment = ['/usr/bin/runuser','-u',config['user'],'--','/usr/bin/env',
                       'OMARCHY_PATH=/usr/share/omarchy','XDG_RUNTIME_DIR='+runtime,
                       'DBUS_SESSION_BUS_ADDRESS=unix:path='+runtime+'/bus',
                       'HYPRLAND_INSTANCE_SIGNATURE='+instances[0].parent.name]
        voice_setup = Path('/usr/local/share/omarchy-kids/voice/scripts/setup-desktop.py')
        if voice_setup.is_file() and Path('/etc/school-voice/policy.json').is_file():
            # Restoring the parent's old bindings must not drop the voice shortcuts.
            # The helper backs up, checks conflicts and validates/reverts Hyprland.
            run(*environment, '/usr/bin/python3', str(voice_setup))
        if subprocess.run(environment + ['/usr/bin/omarchy','shell','shell','ping'],
                          capture_output=True, timeout=5).returncode == 0:
            run(*environment, '/usr/bin/omarchy','restart','shell')

if __name__ == '__main__': main()
