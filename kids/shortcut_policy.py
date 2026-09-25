"""Override restricted shortcuts while leaving Omarchy's defaults loaded."""
import json
import re
import shlex

LEGACY_FLAGS = 'omarchy_preinstalled_bindings = false\nomarchy_default_bindings = false\n\n'
LEGACY_IMPORTS = '\n'.join('require("default.hypr.bindings.' + name + '")'
                           for name in ('media','clipboard','tiling','utilities'))

def restore_default_loading(text):
    if LEGACY_FLAGS in text:
        text = text.replace(LEGACY_FLAGS, '')
        text = text.replace('require("default.hypr.omarchy")\n' + LEGACY_IMPORTS,
                            'require("default.hypr.omarchy")')
    return text

def overrides(stock, personal):
    commands = {}
    for key, label, action in re.findall(r'o\.bind\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,([^\n]+)',stock+'\n'+personal):
        web = re.search(r'webapp\s*=\s*"([^"]+)"', action)
        if web:
            commands[key] = (label, '/usr/local/bin/omarchy-kids-open-url ' + shlex.quote(web[1]))
        elif re.search(r'omarchy\s*=\s*"browser(?: --private)?"', action):
            commands[key] = ('Approved apps', 'omarchy-menu toggle apps')
        elif label in ('Docker','Signal','Music','Obsidian','Omawrite','Passwords','1Password Quick Access'):
            commands[key] = (label+' · parent approval', "notify-send 'Parent approval required' 'This app is unavailable in controlled mode.'")
    commands['SUPER + SHIFT + CTRL + A'] = ('AI agent', 'omarchy agent')
    lines = ['\n-- Kids account bindings']
    for key, (label, action) in commands.items():
        lines += ['hl.unbind('+json.dumps(key)+')',
                  'o.bind('+', '.join((json.dumps(value,ensure_ascii=False) for value in (key,label,action)))+')']
    return '\n'.join(lines)+'\n'
