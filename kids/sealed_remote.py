"""End-to-end parent messages. Only the root broker holds decryption keys.

Wire format: base64url(nonce[12] || AES-256-GCM ciphertext || tag[16]).
Keys use HKDF-SHA256 with the decoded pairing token, phone ID as salt,
and separate request/response context strings. The relay is not trusted.
"""
import base64
import json
import re
import secrets
import subprocess

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def encode(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def decode(value, maximum=1_500_000):
    if not isinstance(value, str) or len(value) > maximum or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid encrypted message.')
    try:
        data = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    except ValueError:
        raise ValueError('Invalid encrypted message.') from None
    if encode(data) != value:
        raise ValueError('Invalid encrypted message.')
    return data


def keys(token, phone):
    return {direction: encode(HKDF(algorithm=hashes.SHA256(), length=32,
            salt=phone.encode(), info=('parent-pocket/v2/' + direction).encode()).derive(decode(token)))
            for direction in ('request', 'response')}


def context(phone, rid, direction):
    return ('parent-pocket/v2/' + phone + '/' + rid + '/' + direction).encode()


def seal(key, phone, rid, direction, value):
    nonce = secrets.token_bytes(12)
    raw = json.dumps(value, separators=(',', ':')).encode()
    if len(raw) > 1_000_000:
        raise ValueError('Response too large.')
    return encode(nonce + AESGCM(decode(key)).encrypt(nonce, raw, context(phone, rid, direction)))


def open_message(key, phone, rid, direction, packet):
    data = decode(packet)
    if len(data) < 28:
        raise ValueError('Invalid encrypted message.')
    try:
        raw = AESGCM(decode(key)).decrypt(data[:12], data[12:], context(phone, rid, direction))
        return json.loads(raw)
    except (InvalidTag, ValueError, UnicodeError, RecursionError):
        raise ValueError('Invalid encrypted message.') from None


def dispatch(store, packet):
    from family import read, remote
    if not isinstance(packet, dict) or set(packet) != {'phone', 'id', 'data'}:
        raise ValueError('Invalid encrypted message.')
    phone, rid = packet['phone'], packet['id']
    if not all(isinstance(v, str) and re.fullmatch(r'[0-9a-f]{32}', v) for v in (phone, rid)):
        raise ValueError('Invalid encrypted message.')
    if not isinstance(packet['data'], str) or len(packet['data']) > 16000:
        raise ValueError('Invalid encrypted message.')
    record = next((p for p in read(store)['phones'] if p['id'] == phone and 'keys' in p), None)
    if record is None:
        raise ValueError('Pair this phone again.')
    body = open_message(record['keys']['request'], phone, rid, 'request', packet['data'])
    if not isinstance(body, dict) or body.get('id') != rid:
        raise ValueError('Invalid encrypted message.')
    # Return application errors inside authenticated encryption too. Never
    # mistake a relay-generated status/error for a successful laptop response.
    try:
        result = {'ok': True, **remote(store, body, encrypted=True)}
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        result = {'ok': False, 'error': str(error)[:240]}
    return {'packet': {'phone': phone, 'id': rid,
            'data': seal(record['keys']['response'], phone, rid, 'response', result)}}
