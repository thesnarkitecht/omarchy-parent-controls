"""Prepare native Omarchy menus and desktop visibility; no package files edited."""
import json
from pathlib import Path
import re
import shutil
import sys
import subprocess
import pwd
sys.path.insert(0,"/usr/local/lib/omarchy-kids")
from native_runtime import account
config = account()

def read_user(path):
    return subprocess.run(["/usr/bin/runuser", "-u", config["user"], "--", "/usr/bin/cat", str(path)], check=True, capture_output=True, text=True).stdout

def write_user(path, text):
    subprocess.run(["/usr/bin/runuser", "-u", config["user"], "--", "/usr/bin/tee", str(path)], input=text, text=True, stdout=subprocess.DEVNULL, check=True)

home = Path(pwd.getpwnam(config['user']).pw_dir)
base = Path('/usr/local/share/omarchy-kids/bundle')
apps = Path('/usr/local/share/omarchy-kids/applications')
apps.mkdir(parents=True, exist_ok=True)
# Desktop overrides use the original IDs, so the stock application provider hides them.
for folder in (Path('/usr/share/applications'), Path('/usr/local/share/applications'), home / '.local/share/applications'):
    if folder.exists():
        for item in folder.glob('*.desktop'):
            (apps / item.name).write_text('[Desktop Entry]\nType=Application\nName=Unavailable\nHidden=true\nNoDisplay=true\n')
hermes_entry = Path('/usr/local/share/applications/omarchy-kids-hermes.desktop')
if config.get('hermes_binary') and hermes_entry.exists(): shutil.copyfile(hermes_entry, apps / hermes_entry.name)
shutil.copyfile(base / 'integration/omarchy-kids.desktop', apps / 'omarchy-kids.desktop')
handler = Path('/usr/local/share/applications/omarchy-kids-approved-browser.desktop')
if handler.exists(): shutil.copyfile(handler, apps / handler.name)
for name in ('foot.desktop', 'footclient.desktop', 'org.gnome.Nautilus.desktop',
             'nvim.desktop', 'imv.desktop', 'imv-dir.desktop', 'mpv.desktop', 'btop.desktop',
             'org.gnome.Calculator.desktop', 'org.gnome.Papers.desktop',
             'org.gnome.Evince.desktop', 'org.gnome.FileRoller.desktop',
             'org.gnome.TextEditor.desktop', 'uuctl.desktop'):
    source = Path('/usr/share/applications') / name
    if source.exists(): shutil.copyfile(source, apps / name)
# Keep the native menu; hide only branches outside the chosen starting policy.
menu_path = home / '.config/omarchy/extensions/omarchy-menu.jsonc'
backup = Path('/var/lib/omarchy-kids-control/native-backup/ui')
backup.mkdir(parents=True, exist_ok=True)
if not (backup / 'omarchy-menu.jsonc').exists(): (backup / 'omarchy-menu.jsonc').write_text(read_user(menu_path))
stock = Path('/usr/share/omarchy/default/omarchy/omarchy-menu.jsonc').read_text()
ids = re.findall(r'^\s*"([a-z0-9.-]+)"\s*:', stock, re.M)
allowed_roots = ('apps', 'style', 'system', 'trigger', 'setup')
hidden = ('trigger.share', 'setup.default.agent', 'setup.default.browser',
          'setup.security.touch-id', 'setup.plugin', 'style.unlock', 'setup.webapp')
entries = {key: {'when': 'false'} for key in ids if key.split('.')[0] not in allowed_roots or any(key == x or key.startswith(x+'.') for x in hidden)}
entries['parents'] = {'label':'Parent controls','icon':'','action':'/usr/local/bin/omarchy-kids'}
if config.get('hermes_binary'):
    entries['hermes'] = {'label':'Hermes Desktop','icon':'','iconFont':'omarchy','action':'hermes-desktop'}
write_user(menu_path, json.dumps(entries, indent=2) + '\n')
# Omarchy's documented toggle keeps all core window-management/media bindings.
hypr = home / '.config/hypr/hyprland.lua'
text = read_user(hypr)
if not (backup / 'hyprland.lua').exists(): (backup / 'hyprland.lua').write_text(text)
if '\nomarchy_preinstalled_bindings = false\n' not in text:
    text = text.replace('-- Load Omarchy defaults.', 'omarchy_preinstalled_bindings = false\nomarchy_default_bindings = false\n\n-- Load Omarchy defaults.')
    text = text.replace('require("default.hypr.omarchy")', 'require("default.hypr.omarchy")\nrequire("default.hypr.bindings.media")\nrequire("default.hypr.bindings.clipboard")\nrequire("default.hypr.bindings.tiling")\nrequire("default.hypr.bindings.utilities")')
write_user(hypr, text)
# The utilities module includes the generic agent picker; replace that binding.
bindings = home / '.config/hypr/bindings.lua'
if not (backup / 'bindings.lua').exists(): (backup / 'bindings.lua').write_text(read_user(bindings))
bindings_text = read_user(bindings).split('-- Kids account bindings')[0]
write_user(bindings, bindings_text + '''\n-- Kids account bindings
hl.unbind("SUPER + SHIFT + CTRL + A")
o.bind("SUPER + SHIFT + CTRL + A", "Hermes Desktop", "hermes-desktop")
o.bind("SUPER + RETURN", "Terminal", { omarchy = "terminal" })
o.bind("SUPER + SHIFT + F", "Files", { omarchy = "nautilus" })
o.bind("SUPER + SHIFT + N", "Editor", { omarchy = "editor" })
''')
# Hide the generic agent picker; standard Hermes Desktop has its own launcher.
shell = home / '.config/omarchy/shell.json'
state = json.loads(read_user(shell))
if not (backup / 'shell.json').exists(): (backup / 'shell.json').write_text(read_user(shell))
def replace(value):
    if isinstance(value, list):
        return [replace(v) for v in value if not (isinstance(v,dict) and v.get('id') in ('omarchy.weather','omarchy.system-update','omarchy.agents','local.kids-hermes'))]
    if isinstance(value,dict):
        return {k: replace(v) for k,v in value.items()}
    return value
state = replace(state)
state['disabledPlugins'] = sorted(set(state.get('disabledPlugins', []) + ['omarchy.agents', 'omarchy.weather', 'omarchy.system-update']))
write_user(shell, json.dumps(state,indent=2)+'\n')
