"""Unprivileged loopback-only relay. Legacy direct HTTPS transport; the managed relay uses outbound WebSockets.

All authorization and state changes happen in the root-owned Unix broker.
This process has no credentials, no shell endpoint and no filesystem API.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from client import request


class Handler(BaseHTTPRequestHandler):
    server_version = 'ParentControls/1'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != '/v1/parent':
            return self.reply(404, {'ok': False, 'error': 'Not found'})
        if self.headers.get('Origin') or self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
            return self.reply(400, {'ok': False, 'error': 'Native parent app requests only'})
        if self.headers.get_content_type() != 'application/json':
            return self.reply(400, {'ok': False, 'error': 'Expected JSON'})
        authorization = self.headers.get('Authorization', '')
        if not authorization.startswith('Bearer ') or len(authorization) != 50:
            return self.reply(401, {'ok': False, 'error': 'Pair this phone first'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict) or set(body) != {'id', 'issued', 'operation', 'fields'}:
                raise ValueError('Invalid request')
            reply = request('remote-parent', envelope={**body, 'token': authorization[7:]})
        except (ValueError, TypeError, RecursionError):
            return self.reply(400, {'ok': False, 'error': 'Invalid request'})
        except RuntimeError as error:
            return self.reply(409, {'ok': False, 'error': str(error)[:240]})
        except OSError:
            return self.reply(503, {'ok': False, 'error': 'School computer is unavailable'})
        return self.reply(200, reply)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address=('127.0.0.1', 43127), handler=Handler):
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(address, handler)

    def process_request(self, request, address):
        if not self.slots.acquire(False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


def main():
    with Server() as server:
        server.serve_forever()
