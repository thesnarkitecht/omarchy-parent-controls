"""Encrypted suggestions through the managed relay. Audio stays on the laptop."""
import json
import ssl
import time
from websockets.sync.client import connect
from .sealed import keys, seal, open_message


def exchange(server, token, payload):
    phone, rid = server['device_id'], payload['id']
    pair_keys = keys(token, phone)
    packet = {'phone': phone, 'id': rid, 'data': seal(pair_keys['request'], phone, rid,
              'request', {'issued': int(time.time()), 'request': payload})}
    url = 'wss' + server['url'].rstrip('/')[5:] + '/v2/parent/' + server['channel']
    start = time.monotonic()
    with connect(url, additional_headers={'Authorization': 'Bearer ' + server['relay_token']},
                 ssl=ssl.create_default_context(), proxy=None, open_timeout=5,
                 close_timeout=1, max_size=8192, max_queue=1) as ws:
        ws.send(json.dumps(packet))
        result = json.loads(ws.recv(timeout=max(.1, 12-(time.monotonic()-start))))
        if (not isinstance(result, dict) or set(result) != {'phone', 'id', 'data'}
                or result['phone'] != phone or result['id'] != rid):
            raise ValueError('Invalid Laya response')
        body = open_message(pair_keys['response'], phone, rid, 'response', result['data'])
    if time.monotonic() - start > 15:
        raise ValueError('Laya response arrived too late; try again.')
    return json.dumps(body).encode()
