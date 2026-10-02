"""Local Pulse protocol transport for managed web apps, never a network server.

systemd owns the listening socket. This process runs as the desktop account,
checks the connecting worker UID and connects to that account's audio socket.
Only bytes are relayed; clients must disable shared-memory/FD audio transport.
No samples are stored or logged. Playback and recording are both supported.
"""
import logging
import os
from pathlib import Path
import pwd
import select
import socket
import stat
import struct
import threading

SOCKET = '/run/omarchy-kids-audio/native'
LIMIT = 256 * 1024


def peer_allowed(connection, worker_uid):
    if not hasattr(socket, 'SO_PEERCRED'):
        return False
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
    _, uid, _ = struct.unpack('3i', credentials)
    return uid == worker_uid


def pump(left, right):
    """Bound memory and apply backpressure in both audio directions."""
    peers = {left: right, right: left}
    pending = {left: bytearray(), right: bytearray()}
    eof = set()
    shut = set()
    for stream in peers:
        stream.setblocking(False)
    while True:
        for stream in peers:
            if peers[stream] in eof and not pending[stream] and stream not in shut:
                stream.shutdown(socket.SHUT_WR)
                shut.add(stream)
        if len(eof) == 2 and not any(pending.values()):
            return
        readers = [s for s in peers if s not in eof and len(pending[peers[s]]) < LIMIT]
        writers = [s for s in peers if pending[s]]
        readable, writable, _ = select.select(readers, writers, [], 30)
        for stream in writable:
            try:
                sent = stream.send(pending[stream])
            except BlockingIOError:
                continue
            if not sent:
                return
            del pending[stream][:sent]
        for stream in readable:
            try:
                chunk = stream.recv(min(65536, LIMIT - len(pending[peers[stream]])))
            except BlockingIOError:
                continue
            if chunk:
                pending[peers[stream]].extend(chunk)
            else:
                eof.add(stream)


def serve_connection(connection, upstream, worker_uid):
    with connection:
        if not peer_allowed(connection, worker_uid):
            return
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as backend:
            backend.settimeout(5)
            backend.connect(str(upstream))
            pump(connection, backend)


def main():
    from native_runtime import account
    child = account()
    if os.geteuid() == 0 or os.geteuid() != child['uid']:
        raise RuntimeError('The audio transport must run as the configured desktop account.')
    if os.environ.get('LISTEN_PID') != str(os.getpid()) or os.environ.get('LISTEN_FDS') != '1':
        raise RuntimeError('Start the audio transport through its systemd socket.')
    worker_uid = pwd.getpwnam('omarchy-kids').pw_uid
    upstream = Path('/run/user') / str(child['uid']) / 'pulse/native'
    slots = threading.BoundedSemaphore(64)
    def handle(connection):
        try:
            serve_connection(connection, upstream, worker_uid)
        except OSError as error:
            logging.warning('Web-app audio connection failed: %s. Check the desktop pipewire-pulse service.', error)
        finally:
            slots.release()
    with socket.socket(fileno=3) as listener:
        if listener.family != socket.AF_UNIX or listener.getsockname() != SOCKET:
            raise RuntimeError('Unexpected audio listening socket.')
        parent = Path(SOCKET).parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022:
            raise RuntimeError('The audio socket directory must be owned and protected by root.')
        while True:
            connection, _ = listener.accept()
            if slots.acquire(False):
                try:
                    threading.Thread(target=handle, args=(connection,), daemon=True).start()
                except Exception:
                    connection.close()
                    slots.release()
                    raise
            else:
                connection.close()


if __name__ == '__main__':
    main()
