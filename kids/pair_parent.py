"""Parent-terminal pairing; token is shown once and stored only as a hash."""
import argparse
import json
import os
import subprocess
from client import request

def main():
    p = argparse.ArgumentParser(description='Pair a parent iPhone with this school computer')
    p.add_argument('--endpoint')
    p.add_argument('--name', default='School computer')
    p.add_argument('--revoke-all', action='store_true')
    p.add_argument('--qr', action='store_true', help='Show a QR code in this private parent terminal')
    args = p.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo in a parent terminal. The existing parent PIN authorizes pairing.')
    if args.revoke_all:
        request('remote-revoke')
        print('All parent phone credentials for this computer have been revoked.')
    else:
        reply = request('remote-enroll', endpoint=args.endpoint, name=args.name)
        print(json.dumps(reply['pairing']))
        if args.qr:
            subprocess.run(['/usr/bin/qrencode','-t','ANSIUTF8'], input=json.dumps(reply['pairing']),text=True,check=True)

if __name__ == '__main__':
    main()
