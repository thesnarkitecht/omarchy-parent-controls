import os
from pathlib import Path
import socket
import struct
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'kids'))
import audio_proxy


class AudioTransportTests(unittest.TestCase):
    def test_large_playback_and_capture_with_half_close_and_backpressure(self):
        app, front = socket.socketpair()
        back, audio = socket.socketpair()
        playback = bytes(range(256)) * 8192
        microphone = b'synthetic-microphone-data' * 65536
        errors = []
        def guarded(fn):
            try:
                fn()
            except Exception as error:
                errors.append(error)
        def read_all(stream):
            result = bytearray()
            while chunk := stream.recv(16384):
                result.extend(chunk)
            return bytes(result)
        def server():
            self.assertEqual(read_all(audio), playback)
            audio.sendall(microphone)
            audio.shutdown(socket.SHUT_WR)
        proxy_thread = threading.Thread(target=lambda: guarded(lambda: audio_proxy.pump(front, back)), daemon=True)
        audio_thread = threading.Thread(target=lambda: guarded(server), daemon=True)
        for stream in (app, audio):
            stream.settimeout(5)
        try:
            proxy_thread.start(); audio_thread.start()
            app.sendall(playback)
            app.shutdown(socket.SHUT_WR)
            self.assertEqual(read_all(app), microphone)
            proxy_thread.join(5); audio_thread.join(5)
            self.assertFalse(proxy_thread.is_alive())
            self.assertFalse(audio_thread.is_alive())
            self.assertEqual(errors, [])
        finally:
            for stream in (app, front, back, audio):
                stream.close()

    def test_kernel_peer_credentials_gate_worker_access(self):
        connection = MagicMock()
        with patch.object(socket, 'SO_PEERCRED', 17, create=True):
            for uid in (0, 1000, 964, 965):
                connection.getsockopt.return_value = struct.pack('3i', 123, uid, 964)
                self.assertEqual(audio_proxy.peer_allowed(connection, 964), uid == 964)

    def test_denied_client_never_connects_to_desktop_audio(self):
        with patch.object(audio_proxy, 'peer_allowed', return_value=False), \
             patch.object(audio_proxy.socket, 'socket') as backend:
            audio_proxy.serve_connection(MagicMock(), '/run/user/1000/pulse/native', 964)
            backend.assert_not_called()

    def test_service_refuses_root_or_other_accounts(self):
        for uid in (0, 1001):
            with patch('native_runtime.account', return_value={'uid': 1000}), \
                 patch.object(audio_proxy.os, 'geteuid', return_value=uid):
                with self.assertRaisesRegex(RuntimeError, 'desktop account'):
                    audio_proxy.main()

    def test_service_requires_systemd_socket_activation(self):
        with patch('native_runtime.account', return_value={'uid': 1000}), \
             patch.object(audio_proxy.os, 'geteuid', return_value=1000), \
             patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'systemd socket'):
                audio_proxy.main()

    def test_client_uses_copy_transport_and_no_automatic_network_fallback(self):
        text = (Path(__file__).resolve().parents[1] / 'native/pulse-client.conf').read_text()
        settings = dict(line.split('=', 1) for line in text.splitlines() if line and not line.startswith('#'))
        settings = {key.strip(): value.strip() for key, value in settings.items()}
        for name in ('enable-shm', 'enable-memfd', 'autospawn', 'auto-connect-localhost', 'auto-connect-display'):
            self.assertEqual(settings[name], 'no')


if __name__ == '__main__':
    unittest.main()
