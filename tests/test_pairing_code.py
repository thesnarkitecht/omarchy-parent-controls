import json
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'kids'))
from control import Store
import family
import pairing_code as code
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from sealed_remote import decode

class PairingCodeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=1000
        self.store=Store(Path(self.tmp.name),clock=lambda:self.now);self.store.initialize('12345678')
        self.relay={'channel':'a'*64,'relay_token':'b'*43}
    def enroll(self):
        return family.enroll(self.store,'https://parent-pocket-relay.onrender.com','School',self.relay,temporary=True)
    def status(self,pair,op='status'):
        return family.remote(self.store,{'token':pair['token'],'id':secrets.token_hex(16),'issued':self.now,'operation':op,'fields':{}})
    def test_code_only_endpoints_can_decrypt_and_lookup_is_not_key(self):
        pair=self.enroll()
        with patch('pairing_code.time.time',return_value=1000): human,packet=code.wrap(pair)
        self.assertEqual(len(code.normalize(human)),16)
        self.assertEqual(code.normalize(human.lower().replace('-',' ')),code.normalize(human))
        data=decode(packet['data']);nonce=data[:12]
        plain=AESGCM(code.digest(human,'key')).decrypt(nonce,data[12:],packet['slot'].encode())
        self.assertEqual(json.loads(plain)['pairing'],pair)
        self.assertNotIn(pair['token'],json.dumps(packet))
        with self.assertRaises(InvalidTag):AESGCM(bytes.fromhex(packet['slot'])).decrypt(nonce,data[12:],packet['slot'].encode())
    def test_expired_credentials_fail_even_if_relay_keeps_ciphertext(self):
        pair=self.enroll();self.now=1300
        with self.assertRaises(ValueError):self.status(pair)
    def test_successful_pairing_survives_code_expiry(self):
        pair=self.enroll();self.status(pair);self.now=1600
        self.assertEqual(self.status(pair)['name'],'School')
    def test_new_code_invalidates_pending_but_preserves_existing_phone(self):
        active=self.enroll();self.status(active)
        old=self.enroll();new=self.enroll()
        with self.assertRaises(ValueError):self.status(old)
        self.status(active);self.status(new)
    def test_pending_phone_cannot_mutate_before_pairing_status(self):
        pair=self.enroll()
        with self.assertRaises(ValueError):self.status(pair,'disable-controls')
        with self.assertRaises(ValueError):code.normalize('123456')
        with self.assertRaises(ValueError):code.normalize('IIII-OOOO-1111-0000')
