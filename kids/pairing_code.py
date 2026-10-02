"""Five-minute encrypted rendezvous. The relay never receives the human code.

16 uniformly random base32 characters provide 80 bits of entropy. Separate
SHA-256 domains derive the lookup ID and AES-GCM key; the lookup ID is not a key.
"""
import hashlib
import json
import secrets
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sealed_remote import encode

ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'


def normalize(code):
    value = code.upper().replace('-', '').replace(' ', '')
    if len(value) != 16 or any(c not in ALPHABET for c in value):
        raise ValueError('Enter the 16-character code shown on the laptop.')
    return value


def digest(code, purpose):
    return hashlib.sha256(('parent-pocket/pairing/v1/' + purpose + '/' + normalize(code)).encode()).digest()


def wrap(pairing):
    code = ''.join(secrets.choice(ALPHABET) for _ in range(16))
    slot = digest(code, 'lookup').hex()
    expires = pairing['expires']
    if not time.time() < expires <= time.time() + 300:
        raise ValueError('Pairing expired. Generate a new code.')
    nonce = secrets.token_bytes(12)
    raw = json.dumps({'pairing': pairing, 'expires': expires}, separators=(',', ':')).encode()
    encrypted = nonce + AESGCM(digest(code, 'key')).encrypt(nonce, raw, slot.encode())
    return '-'.join(code[i:i+4] for i in range(0,16,4)), {'slot':slot, 'data':encode(encrypted), 'expires':expires}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Pairing service redirects are not allowed.')


def publish(pairing, config):
    from family import parent_origin
    endpoint = parent_origin(config['endpoint'])
    code, packet = wrap(pairing)
    packet['channel'] = hashlib.sha256(config['device_token'].encode()).hexdigest()
    request = Request(endpoint + '/v2/pairings', data=json.dumps(packet).encode(),
                      headers={'Content-Type':'application/json', 'Authorization':'Bearer '+config['device_token']}, method='POST')
    opener = build_opener(ProxyHandler({}), HTTPSHandler(), NoRedirect())
    try:
        with opener.open(request, timeout=90) as response:
            result = json.loads(response.read(4097))
        if result != {'expires':packet['expires']}:
            raise ValueError('The pairing service returned an invalid response.')
    except HTTPError as error:
        raise ValueError('Could not create a code. Wait a moment and choose Pair parent phone again.') from error
    if packet['expires'] <= time.time():
        raise ValueError('Pairing expired. Generate a new code.')
    return code, packet['expires']
