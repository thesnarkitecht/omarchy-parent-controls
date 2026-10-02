import copy
import json
from pathlib import Path
import secrets
import unittest
from unittest.mock import patch
from school_voice import client, policy, relay
from school_voice.sealed import keys, open_message, seal


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((Path(__file__).resolve().parents[1]/'policy.example.json').read_text())
        self.token = secrets.token_urlsafe(32)
        self.server = self.policy['server']
        self.server.update(transport='relay', url='https://parent.example.org', channel='a'*64,
                           device_id=secrets.token_hex(16), relay_token=secrets.token_urlsafe(32))

    def test_policy_rejects_insecure_or_malformed_managed_connections(self):
        policy.validate(self.policy)
        for key, value in [('url', 'http://example.org'), ('transport', 'plain'), ('channel', 'short'), ('device_id', '../x'), ('relay_token', 'secret')]:
            candidate = copy.deepcopy(self.policy); candidate['server'][key] = value
            with self.assertRaises(ValueError): policy.validate(candidate)

    def test_transcript_is_encrypted_and_response_bound_to_request(self):
        phone = self.server['device_id']; rid = secrets.token_hex(16)
        payload = {'version': 1, 'id': rid, 'text': 'practice math', 'actions': {'open_math': 'Math'}}
        pair_keys = keys(self.token, phone)
        class Socket:
            def __enter__(inner): return inner
            def __exit__(inner, *args): pass
            def send(inner, text):
                self.assertNotIn('practice math', text)
                packet = json.loads(text)
                body = open_message(pair_keys['request'], phone, rid, 'request', packet['data'])
                self.assertEqual(body['request'], payload)
            def recv(inner, timeout):
                return json.dumps({'phone': phone, 'id': rid, 'data': seal(pair_keys['response'], phone, rid, 'response', {'version':1, 'id':rid, 'action':'open_math'})})
        with patch.object(relay, 'connect', return_value=Socket()) as connect:
            result = json.loads(relay.exchange(self.server, self.token, payload))
            self.assertEqual(result['action'], 'open_math')
            self.assertEqual(connect.call_args.kwargs['ssl'].verify_mode, __import__('ssl').CERT_REQUIRED)
            self.assertIsNone(connect.call_args.kwargs['proxy'])
