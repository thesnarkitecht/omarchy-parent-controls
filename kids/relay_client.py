"""Outbound-only, unprivileged connection to the managed encrypted relay."""
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import ssl
import time

from client import request


def connection(config):
    from websockets.sync.client import connect
    from family import parent_origin
    endpoint = parent_origin(config['endpoint'])
    channel = hashlib.sha256(config['device_token'].encode()).hexdigest()
    headers = {'Authorization': 'Bearer ' + config['device_token'],
               'X-Client-Hash': hashlib.sha256(config['relay_token'].encode()).hexdigest()}
    # TLS verification remains on; no redirects or environment proxy routing.
    return connect('wss' + endpoint[5:] + '/v2/device/' + channel,
                   additional_headers=headers, ssl=ssl.create_default_context(),
                   proxy=None, open_timeout=15, close_timeout=5,
                   ping_interval=30, ping_timeout=30, max_size=18000, max_queue=4)


def serve(ws):
    for message in ws:
        try:
            packet = json.loads(message)
            if not isinstance(packet, dict) or set(packet) != {'peer', 'packet'}:
                continue
            import re
            if not isinstance(packet['peer'], str) or not re.fullmatch(r'[0-9a-f]{32}', packet['peer']):
                continue
            result = request('remote-sealed', packet=packet['packet'])
            ws.send(json.dumps({'peer': packet['peer'], 'packet': result['packet']}))
        except (ValueError, TypeError, KeyError, RuntimeError, OSError):
            # Invalid/revoked messages get no authenticated reply. No tokens,
            # ciphertexts, app names, or command bodies go into the journal.
            continue


def main():
    config = json.loads((Path(os.environ['CREDENTIALS_DIRECTORY'])/'relay.json').read_text())
    delay = 1
    while True:
        started = time.monotonic()
        try:
            with connection(config) as ws:
                logging.warning('Parent connection online.')
                serve(ws)
        except Exception:
            logging.warning('Parent connection interrupted; reconnecting automatically.')
        if time.monotonic() - started > 60:
            delay = 1
        time.sleep(random.uniform(delay / 2, delay))
        delay = min(60, delay * 2)
