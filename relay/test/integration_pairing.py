"""Hosted short-code acceptance with the actual Swift client and disposable state.

Usage: python relay/test/integration_pairing.py /path/to/hosted-pairing-checks
Build that binary from Parent Pocket's Tests/HostedPairingChecks.swift.
"""
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
from websockets.sync.client import connect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'kids'))
from control import Store
import family
import pairing_code
import sealed_remote

endpoint='https://parent-pocket-relay.onrender.com'
with tempfile.TemporaryDirectory() as folder:
    store=Store(Path(folder));store.initialize('12345678')
    config={'endpoint':endpoint,'device_token':secrets.token_urlsafe(32),'relay_token':secrets.token_urlsafe(32)}
    channel=hashlib.sha256(config['device_token'].encode()).hexdigest()
    pair=family.enroll(store,endpoint,'Pairing acceptance',{'channel':channel,'relay_token':config['relay_token']},temporary=True)
    errors=[]
    with connect('wss'+endpoint[5:]+'/v2/device/'+channel,proxy=None,close_timeout=1,
                 additional_headers={'Authorization':'Bearer '+config['device_token'],
                                     'X-Client-Hash':hashlib.sha256(config['relay_token'].encode()).hexdigest()}) as ws:
        code,expires=pairing_code.publish(pair,config)
        private=Path(folder)/'code';private.write_text(code);private.chmod(0o600)
        def serve():
            try:
                message=json.loads(ws.recv(timeout=110))
                response=sealed_remote.dispatch(store,message['packet'])['packet']
                ws.send(json.dumps({'peer':message['peer'],'packet':response}))
            except Exception as error:errors.append(error)
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        subprocess.run([sys.argv[1],str(private)],check=True,timeout=115)
        thread.join(timeout=5)
        assert not errors and not thread.is_alive(),errors
        assert 'pairing_expires' not in family.read(store)['phones'][0]
        family.revoke(store)
        print('PASS: laptop code publication and broker activation; disposable enrollment revoked')
