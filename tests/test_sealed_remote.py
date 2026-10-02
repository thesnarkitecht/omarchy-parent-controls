import json
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'kids'))
import family
import sealed_remote as sealed
from control import Store


class SealedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name), clock=lambda: 1000)
        self.store.initialize('12345678')
        self.pair = family.enroll(self.store, 'https://parent.example.org', 'Laptop',
                                 {'channel': 'a'*64, 'relay_token': 'b'*43})
        self.keys = sealed.keys(self.pair['token'], self.pair['id'])

    def packet(self, operation='status', fields=None, issued=1000):
        rid = secrets.token_hex(16)
        body = {'id': rid, 'token': self.pair['token'], 'issued': issued,
                'operation': operation, 'fields': fields or {}}
        return {'id': rid, 'phone': self.pair['id'], 'data': sealed.seal(
            self.keys['request'], self.pair['id'], rid, 'request', body)}

    def reply(self, packet):
        result = sealed.dispatch(self.store, packet)['packet']
        return sealed.open_message(self.keys['response'], result['phone'], result['id'], 'response', result['data'])

    def test_valid_request_and_encrypted_status(self):
        self.assertEqual(self.pair['version'], 2)
        result = self.reply(self.packet())
        self.assertTrue(result['ok']); self.assertEqual(result['name'], 'Laptop')
        self.assertNotIn('keys', json.dumps(result))

    def test_relay_cannot_modify_read_or_relabel_commands(self):
        packet = self.packet()
        for changes in ({'id': 'b'*32}, {'phone': 'b'*32}, {'data': packet['data'][:-10] + 'a'*10}):
            with self.assertRaises(ValueError): sealed.dispatch(self.store, {**packet, **changes})
        with self.assertRaises(ValueError):
            sealed.open_message(self.keys['response'], packet['phone'], packet['id'], 'request', packet['data'])

    def test_replay_is_idempotent_expired_rejected_and_revocation_immediate(self):
        packet = self.packet('add-video', {'url': 'https://youtu.be/abcdefghijk'})
        self.assertTrue(self.reply(packet)['ok']); self.assertTrue(self.reply(packet)['ok'])
        self.assertEqual(len(family.read(self.store)['videos']), 1)
        self.assertFalse(self.reply(self.packet(issued=900))['ok'])
        family.revoke(self.store)
        with self.assertRaises(ValueError): self.reply(packet)

    def test_only_existing_bounded_parent_operations_are_available(self):
        self.assertFalse(self.reply(self.packet('disable-controls'))['ok'])
        with patch('access_control.change') as change:
            self.assertTrue(self.reply(self.packet('set-paused', {'paused': True}))['ok'])
            change.assert_called_once_with(True)

    def test_no_default_service_does_not_silently_use_an_untrusted_host(self):
        import pair_parent
        service = Path(self.temp.name)/'service.json'; service.write_text('{"endpoint":null}')
        with patch.object(pair_parent, 'SERVICE', service), patch.object(pair_parent, 'RELAY', Path(self.temp.name)/'relay.json'):
            with self.assertRaises(ValueError): pair_parent.prepare_relay()

    def test_pairing_reuses_connection_and_keeps_credentials_private(self):
        import pair_parent
        service = Path(self.temp.name)/'service.json'; service.write_text('{"endpoint":"https://parent.example.org"}')
        config = Path(self.temp.name)/'relay.json'
        with patch.object(pair_parent, 'SERVICE', service), patch.object(pair_parent, 'RELAY', config), patch.object(pair_parent, 'command'):
            first = pair_parent.prepare_relay()
            self.assertEqual(first, pair_parent.prepare_relay())
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('device_token', first[1])
