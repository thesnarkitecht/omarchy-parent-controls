"""Parent-authorized QR pairing with automatic managed relay setup."""
import argparse
import hashlib
import secrets
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from client import request

CONFIG = Path('/etc/omarchy-kids/remote.json')
RELAY = Path('/etc/omarchy-kids/relay.json')
SERVICE = Path('/usr/local/lib/omarchy-kids/remote-service.json')


def command(*args, **options):
    return subprocess.run(list(args), check=True, **options)


def prepare_remote(endpoint=None):
    from family import parent_origin
    if not endpoint and CONFIG.exists():
        endpoint = json.loads(CONFIG.read_text())['endpoint']
    if not endpoint:
        print('One-time remote connection setup. Use the HTTPS address assigned to this laptop by your hosted tunnel service. A VPN is not required.')
        endpoint = input('Laptop remote HTTPS address: ').strip()
    endpoint = parent_origin(endpoint)
    from control import atomic_json
    atomic_json(CONFIG, {'endpoint': endpoint})
    command('/usr/bin/systemctl', 'enable', '--now', 'omarchy-kids-remote.service')
    return endpoint


def prepare_relay():
    from family import parent_origin
    from control import atomic_json
    if RELAY.exists():
        config = json.loads(RELAY.read_text())
    else:
        service = json.loads(SERVICE.read_text())
        if not service.get('endpoint'):
            raise ValueError('Remote service has not been activated for this release. A parent can still manage this laptop locally.')
        config = {'endpoint': parent_origin(service['endpoint']),
                  'device_token': secrets.token_urlsafe(32), 'relay_token': secrets.token_urlsafe(32)}
        atomic_json(RELAY, config)
    parent_origin(config['endpoint'])
    command('/usr/bin/systemctl', 'enable', '--now', 'omarchy-kids-relay.service')
    return config['endpoint'], {'channel': hashlib.sha256(config['device_token'].encode()).hexdigest(),
                                'relay_token': config['relay_token']}


def main(argv=None):
    p = argparse.ArgumentParser(description='Pair a parent iPhone with this school computer')
    p.add_argument('--endpoint', help='Use an already-configured private endpoint (advanced)')
    p.add_argument('--name', default=socket.gethostname().split('.')[0][:60] or 'School laptop')
    p.add_argument('--revoke-all', action='store_true')
    p.add_argument('--qr', action='store_true', help='Show a QR code in this private parent terminal')
    p.add_argument('--wait', action='store_true', help='Keep the pairing screen open until Enter')
    args = p.parse_args(argv)
    if os.geteuid() != 0:
        raise SystemExit('Run omarchy-parent-controls pair and enter the parent PIN.')
    try:
        if args.revoke_all:
            request('remote-revoke')
            if RELAY.exists():
                config = json.loads(RELAY.read_text())
                config['relay_token'] = secrets.token_urlsafe(32)
                from control import atomic_json
                atomic_json(RELAY, config)
                command('/usr/bin/systemctl', 'restart', 'omarchy-kids-relay.service')
            print('All parent phones disconnected. Existing pairing codes no longer work.')
        else:
            if args.endpoint:
                endpoint, relay = prepare_remote(args.endpoint), None
            else:
                endpoint, relay = prepare_relay()
            reply = request('remote-enroll', endpoint=endpoint, name=args.name, relay=relay)
            print('\nOpen Parent Pocket → Pair a school computer → Scan pairing code.\nPair once. Your phone connects automatically whenever this laptop is awake and online.\n')
            if args.qr or not args.endpoint:
                command('/usr/bin/qrencode', '-t', 'ANSIUTF8', input=json.dumps(reply['pairing']), text=True)
            print('\nOr paste this pairing text in Parent Pocket:\n' + json.dumps(reply['pairing']))
            print('\nThis code grants parent access. Keep it private.')
        if args.wait:
            input('\nPress Enter to hide this code and close. ')
            print('\033[2J\033[3J\033[H', end='', flush=True)
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print('\nPairing did not finish: ' + str(error))
        if args.wait:
            input('\nPress Enter to close. ')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
