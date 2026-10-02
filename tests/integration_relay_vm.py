"""Destructive-session acceptance check for the isolated Omarchy test VM only."""
import hashlib,json,os,secrets,subprocess,sys,time
from pathlib import Path
from websockets.sync.client import connect
if sys.argv[1:] != ['--disposable-vm']:
 raise SystemExit('Run only in the disposable Omarchy VM with --disposable-vm; this pauses its desktop.')
sys.path.insert(0,'/usr/local/lib/omarchy-kids')
from client import request
import sealed_remote as sealed
state=Path('/var/lib/omarchy-kids-control/family.json')
backup=state.read_bytes() if state.exists() else None
host,client=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
channel=hashlib.sha256(host.encode()).hexdigest()
config={'channel':channel,'device_token':host,'relay_token':client}
script='''import sys,json,hashlib
sys.path.insert(0,"/usr/local/lib/omarchy-kids")
from websockets.sync.client import connect
from relay_client import serve
c=json.load(sys.stdin)
with connect("ws://10.0.2.2:8787/v2/device/"+c["channel"],additional_headers={"Authorization":"Bearer "+c["device_token"],"X-Client-Hash":hashlib.sha256(c["relay_token"].encode()).hexdigest()},proxy=None,close_timeout=1) as ws:
 serve(ws)
'''
worker=None
try:
 pair=request('remote-enroll',endpoint='https://relay.example.org',name='VM encrypted test',relay={'channel':channel,'relay_token':client})['pairing']
 keys=sealed.keys(pair['token'],pair['id'])
 worker=subprocess.Popen(['runuser','-u','nobody','--','python3','-c',script],stdin=subprocess.PIPE)
 worker.stdin.write(json.dumps(config).encode());worker.stdin.close()
 def phone(operation,fields):
  rid=secrets.token_hex(16)
  body={'token':pair['token'],'id':rid,'issued':int(time.time()),'operation':operation,'fields':fields}
  packet={'phone':pair['id'],'id':rid,'data':sealed.seal(keys['request'],pair['id'],rid,'request',body)}
  with connect('ws://10.0.2.2:8787/v2/parent/'+channel,additional_headers={'Authorization':'Bearer '+client},proxy=None,close_timeout=1) as ws:
   ws.send(json.dumps(packet));result=json.loads(ws.recv(timeout=50))
  return sealed.open_message(keys['response'],result['phone'],result['id'],'response',result['data'])
 for attempt in range(20):
  try:
   result=phone('status',{});break
  except Exception:
   if worker.poll() is not None:raise
   time.sleep(.5)
 else:raise AssertionError('VM failed to reach relay')
 assert result['ok'] and result['name']=='VM encrypted test'
 print('PASS: unprivileged VM connector reaches real root broker through managed relay',flush=True)
 result=phone('set-paused',{'paused':True});assert result['ok'] and result['access']['paused'] and result['access']['enforced'],result
 assert phone('status',{})['access']['paused']
 print('PASS: remote encrypted pause applies and connector remains available while paused',flush=True)
 result=phone('set-paused',{'paused':False});assert result['ok'] and not result['access']['paused'] and result['access']['enforced'],result
 result=phone('disable-controls',{});assert not result['ok']
 print('PASS: encrypted resume works; control-disable is rejected',flush=True)
 assert subprocess.run(['runuser','-u','nobody','--','test','-r',str(state)]).returncode!=0
 print('PASS: connector account cannot read parent credentials',flush=True)
finally:
 try:request('access-admin',paused=False)
 finally:
  if worker is not None:worker.terminate();worker.wait(timeout=10)
  if backup is None:state.unlink(missing_ok=True)
  else:state.write_bytes(backup)
  print('Restored VM phone pairings and resumed access.',flush=True)
