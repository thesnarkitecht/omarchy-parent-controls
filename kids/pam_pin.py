"""PAM helper: approve sudo with the existing parent PIN, never the login password."""
import os
import sys
from client import request
from native_runtime import account


def main():
    try:
        if os.environ.get('PAM_USER') != account()['user']:
            return 1
        raw = sys.stdin.buffer.read(128)
        pin = raw.rstrip(b'\0\n').decode('ascii')
        request('check-pin', pin=pin)
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
