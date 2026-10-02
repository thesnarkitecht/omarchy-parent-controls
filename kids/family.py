"""Parent capabilities and child requests. Called only by the serial local broker.

The HTTP relay has no privilege. Every remote operation is authenticated here;
children can submit requests but cannot make approvals or enroll a phone.
"""
import copy
import hashlib
import hmac
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from core import CATALOG, origin, validate_policy

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
DEFAULT_VOICE = {"enabled": False, "wake_enabled": True, "phrase": "Hey Laya"}


def youtube_host(host):
    return any(host == base or host.endswith('.' + base) for base in ('youtube.com', 'youtu.be', 'youtube-nocookie.com'))


def start_url(value):
    parsed = urlsplit(value)
    return origin(value) + (parsed.path or '/') + ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')


def website(value, name=''):
    """URL-first approval: preserve the start path and approve its exact origin."""
    if not isinstance(value, str) or not isinstance(name, str):
        raise ValueError('Paste a website link.')
    value = value.strip()
    if not value or len(value) > 2048:
        raise ValueError('Paste a website link.')
    if '://' not in value:
        value = 'https://' + value
    site = origin(value)
    host = urlsplit(site).hostname
    if youtube_host(host):
        raise ValueError('Add an individual video to Little Screen instead of approving YouTube.')
    label = short_text(name, 60) if name.strip() else host.removeprefix('www.')[:60]
    # Use the normalized origin (including IDNA), retaining only the URL path,
    # query and fragment supplied by the parent. Never fetch untrusted metadata.
    return label, start_url(value), site


def video_id(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Use a link to one YouTube video.")
    if VIDEO_ID.fullmatch(value):
        return value
    u = urlsplit(value)
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443):
        raise ValueError("Use an HTTPS YouTube video link.")
    query = parse_qs(u.query)
    if 'list' in query or 'index' in query:
        raise ValueError("Approve one video, not a playlist or channel.")
    key = ''
    if u.hostname == 'youtu.be':
        key = u.path.removeprefix('/')
    elif u.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        if u.path == '/watch' and len(query.get('v', [])) == 1:
            key = query['v'][0]
        elif re.fullmatch(r'/(shorts|embed)/[A-Za-z0-9_-]{11}', u.path):
            key = u.path.rsplit('/', 1)[1]
    if not VIDEO_ID.fullmatch(key):
        raise ValueError("Use a link to one YouTube video, not a channel or search.")
    return key


def short_text(value, limit=80):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError("Use a short, plain-text name.")
    return value.strip()


def read(store):
    try:
        return store.read('family.json')
    except FileNotFoundError:
        return {"version": 1, "name": "School computer", "phones": [], "requests": [],
                "videos": [], "voice": dict(DEFAULT_VOICE), "receipts": []}


def public(store):
    state = read(store)
    from activity import summary
    from access_control import status as access_status
    return {"screen_time": summary(store.path), "access": access_status(), "paired_phones": sum(1 for p in state['phones'] if 'pairing_expires' not in p), "name": state['name'], "requests": state['requests'], "videos": state['videos'],
            "voice": state['voice'], "policy": store.read('policy.json'),
            "controlled": Path('/etc/omarchy-kids/controlled-on').exists(),
            "requestable_apps": [{'id': key, 'name': app['name']} for key, app in CATALOG.items() if Path(app['binary']).is_file()],
            "voice_installed": Path('/usr/local/bin/school-voice').is_file()}


def parent_origin(endpoint):
    normalized = origin(endpoint)
    u = urlsplit(endpoint)
    if u.path not in ('', '/') or u.query or u.fragment:
        raise ValueError("Use the laptop's remote HTTPS address without a path or query.")
    return normalized


def enroll(store, endpoint, name, relay=None, temporary=False):
    endpoint = parent_origin(endpoint)
    state = read(store)
    if type(temporary) is not bool:
        raise ValueError('Invalid pairing mode.')
    # Starting a fresh code invalidates older unclaimed codes on this laptop.
    state['phones'] = [p for p in state['phones'] if 'pairing_expires' not in p or
                       (not temporary and p['pairing_expires'] > store.clock())]
    if len(state['phones']) >= 8:
        raise ValueError("Revoke an old phone before pairing another.")
    token, key = secrets.token_urlsafe(32), secrets.token_hex(16)
    state['name'] = short_text(name)
    record = {'id': key, 'hash': hashlib.sha256(token.encode()).hexdigest()}
    if relay is not None:
        if (not isinstance(relay, dict) or set(relay) != {'channel', 'relay_token'}
                or not re.fullmatch(r'[0-9a-f]{64}', relay.get('channel', ''))
                or not re.fullmatch(r'[A-Za-z0-9_-]{43}', relay.get('relay_token', ''))):
            raise ValueError('Invalid remote connection configuration.')
        from sealed_remote import keys
        record['keys'] = keys(token, key)
    if temporary:
        record['pairing_expires'] = int(store.clock()) + 300
    state['phones'].append(record)
    store.save('family.json', state)
    return {'version': 2 if relay else 1, 'id': key, 'name': state['name'], 'endpoint': endpoint,
            'token': token, **(relay or {}), **({'expires': record['pairing_expires']} if temporary else {})}


def revoke(store):
    state = read(store)
    state['phones'] = []
    state['receipts'] = []
    store.save('family.json', state)
    return {}


def submit(store, request):
    if not isinstance(request, dict) or set(request) != {'kind', 'name', 'target', 'reason'}:
        raise ValueError("Invalid approval request.")
    kind = request['kind']
    name = short_text(request['name'], 60)
    reason = short_text(request['reason'], 240) if request['reason'] else ''
    target = request['target']
    if kind == 'website':
        target = origin(target)  # Deliberately approve only the requested exact host.
        if youtube_host(urlsplit(target).hostname):
            raise ValueError('Request a single video for Little Screen instead of the YouTube website.')
    elif kind == 'video':
        target = video_id(target)
    elif kind == 'app':
        if not isinstance(target, str) or target not in CATALOG:
            raise ValueError("That app is not in the supported school-app catalog.")
        name = CATALOG[target]['name']
    else:
        raise ValueError("Request a website, supported app, or individual video.")
    state = read(store)
    for item in state['requests']:
        if item['kind'] == kind and item['target'] == target and item['status'] == 'pending':
            return {'request': item}
    recent = [r for r in state['requests'] if r['created'] > store.clock() - 60]
    if len(recent) >= 5 or sum(r['status'] == 'pending' for r in state['requests']) >= 32:
        raise ValueError("Your requests are saved. Wait for a parent before adding more.")
    item = {'id': secrets.token_hex(16), 'kind': kind, 'name': name, 'target': target,
            'reason': reason, 'created': int(store.clock()), 'status': 'pending'}
    state['requests'] = [r for r in state['requests'] if r['status'] == 'pending'] + [r for r in state['requests'] if r['status'] != 'pending'][-96:]
    state['requests'].append(item)
    store.save('family.json', state)
    return {'request': item}


def save_policy(store, policy):
    policy = validate_policy(policy)
    from sandbox import trusted_executable
    for key in policy['native']:
        trusted_executable(CATALOG[key]['binary'])
    store.save('policy.json', policy)
    from native_runtime import configured, desktop_entries, revoke_webapps
    if configured():
        desktop_entries(policy)
        revoke_webapps()


def apply(store, state, operation, fields):
    if operation == 'review':
        if set(fields) != {'request_id', 'allow'} or type(fields['allow']) is not bool:
            raise ValueError("Invalid review.")
        item = next((r for r in state['requests'] if r['id'] == fields['request_id']), None)
        if item is None:
            raise ValueError("Request no longer exists.")
        desired = 'allowed' if fields['allow'] else 'denied'
        if item['status'] != 'pending':
            if item['status'] == desired:
                return
            raise ValueError("This request has already been reviewed. Refresh the app.")
        if fields['allow']:
            if item['kind'] == 'video':
                put_video(state, item['target'], item['name'])
            else:
                policy = store.read('policy.json')
                if item['kind'] == 'website':
                    # Stable ID makes a retried approval safe after a partial service failure.
                    key = 'ask-' + item['id']
                    policy['webapps'] = [a for a in policy['webapps'] if a['id'] != key]
                    policy['webapps'].append({'id': key, 'name': item['name'], 'url': item['target'], 'origins': [item['target']]})
                elif item['target'] not in policy['native']:
                    policy['native'].append(item['target'])
                save_policy(store, policy)
        item['status'], item['reviewed'] = desired, int(store.clock())
    elif operation == 'add-webapp':
        if not {'url'} <= set(fields) <= {'url', 'name'}:
            raise ValueError('Invalid website.')
        name, url, site = website(fields['url'], fields.get('name', ''))
        policy = store.read('policy.json')
        # Retrying the same start URL updates its label without granting more
        # hosts or duplicating entries; a different path may be a separate app.
        existing = next((a for a in policy['webapps'] if start_url(a['url']) == url), None)
        if existing:
            existing['name'] = name
        else:
            key = 'web-' + hashlib.sha256(url.encode()).hexdigest()[:24]
            policy['webapps'].append({'id': key, 'name': name, 'url': url, 'origins': [site]})
        save_policy(store, policy)
    elif operation == 'add-video':
        if not {'url'} <= set(fields) <= {'url', 'name'}:
            raise ValueError("Invalid video.")
        key = video_id(fields['url'].strip() if isinstance(fields['url'], str) else fields['url'])
        name = fields.get('name', '')
        if not isinstance(name, str):
            raise ValueError('Use a short, plain-text name.')
        put_video(state, key, short_text(name) if name.strip() else 'Video ' + key)
    elif operation == 'remove-video':
        if set(fields) != {'video_id'} or not isinstance(fields['video_id'], str) or not VIDEO_ID.fullmatch(fields['video_id']):
            raise ValueError("Invalid video ID.")
        state['videos'] = [v for v in state['videos'] if v['id'] != fields['video_id']]
    elif operation == 'remove-webapp':
        if set(fields) != {'app_id'} or not isinstance(fields['app_id'], str):
            raise ValueError("Invalid webapp.")
        policy = store.read('policy.json')
        policy['webapps'] = [a for a in policy['webapps'] if a['id'] != fields['app_id']]
        save_policy(store, policy)
    elif operation == 'set-paused':
        if set(fields) != {'paused'} or type(fields['paused']) is not bool:
            raise ValueError('Choose Pause or Resume.')
        from access_control import change
        change(fields['paused'])
    elif operation == 'set-voice':
        if (set(fields) != {'enabled', 'wake_enabled', 'phrase'} or type(fields['enabled']) is not bool
                or type(fields['wake_enabled']) is not bool or not isinstance(fields['phrase'], str)
                or not re.fullmatch(r'[A-Za-z]+(?: [A-Za-z]+){1,3}', fields['phrase'])):
            raise ValueError("Choose a wake phrase of two to four English words.")
        if fields['enabled'] and not Path('/usr/local/bin/school-voice').is_file():
            raise ValueError("Install voice support on this computer first.")
        state['voice'] = dict(fields)
    else:
        raise ValueError("This action is not available remotely.")


def put_video(state, key, name):
    videos = [v for v in state['videos'] if v['id'] != key]
    if len(videos) >= 100:
        raise ValueError("The library supports up to 100 individually approved videos.")
    state['videos'] = videos + [{'id': key, 'name': name}]


def remote(store, envelope):
    if not isinstance(envelope, dict) or set(envelope) != {'token', 'id', 'issued', 'operation', 'fields'}:
        raise ValueError("Invalid parent request.")
    state = read(store)
    token = envelope['token']
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        raise ValueError("Pair this phone first.")
    digest = hashlib.sha256(token.encode()).hexdigest()
    phone = next((p for p in state['phones'] if hmac.compare_digest(p['hash'], digest)), None)
    if phone is None or phone.get('pairing_expires', store.clock() + 1) <= store.clock():
        raise ValueError("Pair this phone first.")
    rid, issued = envelope['id'], envelope['issued']
    if not isinstance(rid, str) or not re.fullmatch(r'[0-9a-f]{32}', rid) or type(issued) is not int or abs(store.clock() - issued) > 60:
        raise ValueError("Request expired. Refresh and try again.")
    operation, fields = envelope['operation'], envelope['fields']
    if not isinstance(operation, str) or not isinstance(fields, dict):
        raise ValueError("Invalid operation.")
    if operation == 'status':
        if fields:
            raise ValueError("Invalid status request.")
        if 'pairing_expires' in phone:
            del phone['pairing_expires']
            store.save('family.json', state)
        return public(store)
    if 'pairing_expires' in phone:
        raise ValueError('Finish pairing this phone before making changes.')
    fingerprint = hashlib.sha256(__import__('json').dumps([operation, fields], sort_keys=True).encode()).hexdigest()
    state['receipts'] = [r for r in state['receipts'] if r['time'] > store.clock() - 300]
    for receipt in state['receipts']:
        if receipt['id'] == rid and receipt['phone'] == phone['id']:
            if receipt['fingerprint'] != fingerprint:
                raise ValueError("Request ID already used.")
            return public(store)
    if len([r for r in state['receipts'] if r['time'] > store.clock() - 60]) >= 30:
        raise ValueError("Too many changes. Wait a moment.")
    apply(store, state, operation, fields)
    state['receipts'].append({'id': rid, 'phone': phone['id'], 'fingerprint': fingerprint, 'time': int(store.clock())})
    store.save('family.json', state)
    return public(store)


def voice_catalog(store):
    """Use the same approvals as the desktop; URLs/argv never come from an agent."""
    policy, state = store.read('policy.json'), read(store)
    apps = {}
    # These everyday applications are already allowed by the parent-controls desktop.
    for key, label, binary, cls, aliases in [
        ('calculator', 'Calculator', '/usr/bin/gnome-calculator', 'org.gnome.Calculator', ['calculator']),
        ('editor', 'Text Editor', '/usr/bin/gnome-text-editor', 'org.gnome.TextEditor', ['editor', 'notes']),
        ('videos', 'Little Screen', '/usr/local/bin/omarchy-kids-videos', 'little-screen', ['little screen', 'my videos', 'videos']),
    ]:
        if Path(binary).is_file():
            apps[key] = {'label': label, 'argv': [binary], 'classes': [cls], 'aliases': aliases}
    classes = {'math': 'sparkle-math', 'tuxpaint': 'tuxpaint', 'gcompris': 'org.kde.gcompris', 'supertux': 'supertux2', 'calculator': 'org.gnome.Calculator'}
    for key in policy['native']:
        app = CATALOG[key]
        if Path(app['binary']).is_file():
            apps[key] = {'label': app['name'], 'argv': [app['binary']], 'classes': [classes[key]], 'aliases': [app['name']]}
            if key == 'math':
                apps[key]['aliases'] += ['math', 'sparkle math']
                apps[key]['classes'].append('Math Match')
    for app in policy['webapps']:
        key = 'web_' + app['id'].replace('-', '_')
        apps[key] = {'label': app['name'], 'argv': ['/usr/local/bin/omarchy-kids-webapp', app['id']],
                     'classes': ['omarchy-webapp-' + app['id']], 'aliases': [app['name']],
                     'unit': 'omarchy-kids-webapp-' + app['id'] + '.service'}
    purposes = {'editor': 'writing stories, letters and notes', 'calculator': 'calculating sums and multiplication',
                'math': 'practicing math, arithmetic and fractions', 'videos': 'watching parent-picked videos',
                'tuxpaint': 'drawing and painting pictures', 'gcompris': 'educational activities and learning games',
                'supertux': 'playing the approved platform game'}
    for key, app in apps.items():
        if key in purposes: app['purpose'] = purposes[key]
    return {'voice': state['voice'], 'apps': apps}
