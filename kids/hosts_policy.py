"""Reversible hostname guardrails; execution restrictions remain the boundary."""
from pathlib import Path
import os
import re
import tempfile
import socket
import time
import json

BEGIN = '# BEGIN OMARCHY PARENT CONTROLS'
END = '# END OMARCHY PARENT CONTROLS'
HOSTS = Path('/etc/hosts')
NSS = Path('/etc/nsswitch.conf')
NSS_BACKUP = Path('/var/lib/omarchy-kids-control/nss-hosts.json')
BLOCKED = (
    'brave.com', 'www.brave.com', 'laptop-updates.brave.com',
    'updates.bravesoftware.com', 'brave-browser-apt-release.s3.brave.com',
    'brave-browser-rpm-release.s3.brave.com',
    'dl.google.com', 'dl-ssl.google.com', 'googlechromelabs.github.io',
    'download.mozilla.org', 'download-installer.cdn.mozilla.net',
    'archive.mozilla.org', 'ftp.mozilla.org',
    'download.cdn.mozilla.net',
    'vivaldi.com', 'downloads.vivaldi.com', 'repo.vivaldi.com',
    'browser-update.vivaldi.com', 'zen-browser.app', 'updates.zen-browser.app',
    'download.microsoft.com', 'msedge.sf.dl.delivery.mp.microsoft.com',
    'opera.com', 'www.opera.com', 'download.opera.com', 'get.geo.opera.com',
    'www.torproject.org', 'dist.torproject.org',
)

def render(text, enabled, domains=BLOCKED):
    pattern = re.compile(r'^' + re.escape(BEGIN) + r'\n.*?^' + re.escape(END) + r'\n?', re.M | re.S)
    clean = pattern.sub('', text)
    if not enabled:
        return clean
    names = sorted({d for d in domains if re.fullmatch(r'[a-z0-9.-]+', d)})
    lines = [BEGIN]
    for name in names:
        lines.extend(['0.0.0.0 ' + name, ':: ' + name])
    return clean.rstrip('\n') + '\n' + '\n'.join(lines) + '\n' + END + '\n'

def files_first(line):
    body, separator, comment = line.partition('#')
    prefix, modules = body.split(':',1)
    tokens = re.findall(r'\[[^\]]*\]|\S+',modules)
    kept=[]
    index=0
    while index<len(tokens):
        if tokens[index]=='files':
            index+=1
            if index<len(tokens) and tokens[index].startswith('['): index+=1
        else:
            kept.append(tokens[index]);index+=1
    return prefix+': files'+(' '+' '.join(kept) if kept else '')+(' #'+comment.rstrip('\n') if separator else '')+'\n'

def configure_nss(enabled):
    text=NSS.read_text()
    lines=text.splitlines(keepends=True)
    matches=[index for index,line in enumerate(lines) if re.match(r'^\s*hosts\s*:',line)]
    if len(matches)!=1: raise RuntimeError('Expected one hosts lookup rule in nsswitch.conf.')
    index=matches[0];current=lines[index]
    saved=json.loads(NSS_BACKUP.read_text()) if NSS_BACKUP.exists() else None
    if enabled:
        if saved and current==saved['patched']: return
        patched=files_first(current)
        if current==patched: return
        NSS_BACKUP.write_text(json.dumps({'original':current,'patched':patched}))
        NSS_BACKUP.chmod(0o600)
        lines[index]=patched
    elif saved:
        # Do not undo unrelated administrator edits made during controlled mode.
        if current==saved['patched']: lines[index]=saved['original']
        NSS_BACKUP.unlink()
    else: return
    if ''.join(lines)!=text:
        replace_system_file(NSS,''.join(lines))

def replace_system_file(path, text):
    fd,temporary=tempfile.mkstemp(prefix='.omarchy-hosts-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            stream.write(text);stream.flush();os.fsync(stream.fileno())
        os.chmod(temporary,0o644)
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def apply(enabled):
    # Put the local file first while enabled. Otherwise a starting resolver can
    # temporarily answer from DNS despite the freshly written hosts block.
    configure_nss(enabled)
    current = HOSTS.read_text()
    revised = render(current, enabled)
    if current == revised:
        return
    # Only the marked block is replaced; unrelated host entries are retained.
    replace_system_file(HOSTS,revised)

def wait_until_applied(timeout=8):
    # systemd-resolved can briefly retain its previous /etc/hosts snapshot
    # after an atomic replace. Wait before reporting that mode-on completed.
    deadline=time.monotonic()+timeout
    while True:
        try:
            addresses={value[4][0] for value in socket.getaddrinfo('brave.com',443)}
        except socket.gaierror:
            addresses=set()
        if addresses <= {'0.0.0.0','::'}: return
        if time.monotonic()>=deadline:
            raise RuntimeError('The system resolver has not applied the browser-download host blocks.')
        time.sleep(0.25)
