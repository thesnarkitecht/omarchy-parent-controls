"""Exercise a local or hosted relay using disposable enrollment, never real devices."""
import sys,json,secrets,hashlib,time,threading,os
from pathlib import Path
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus, ConnectionClosed
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'kids'))
import sealed_remote as sealed
from control import Store
import family
import tempfile
root=tempfile.TemporaryDirectory(); store=Store(Path(root.name));store.initialize('12345678')
host=secrets.token_urlsafe(32); client=secrets.token_urlsafe(32)
channel=hashlib.sha256(host.encode()).hexdigest()
base=os.environ.get('RELAY_TEST_URL','ws://127.0.0.1:8787').rstrip('/')+'/v2/'
headers={'Authorization':'Bearer '+host,'X-Client-Hash':hashlib.sha256(client.encode()).hexdigest()}
pair=family.enroll(store,'https://relay.example.org','Test laptop',{'channel':channel,'relay_token':client})
keys=sealed.keys(pair['token'],pair['id'])
def device():return connect(base+'device/'+channel,additional_headers=headers,proxy=None,close_timeout=1)
def parent(cap=client):return connect(base+'parent/'+channel,additional_headers={'Authorization':'Bearer '+cap},proxy=None,close_timeout=1)
def make(operation='status',fields=None):
 rid=secrets.token_hex(16)
 body={'token':pair['token'],'id':rid,'issued':int(time.time()),'operation':operation,'fields':fields or {}}
 return {'phone':pair['id'],'id':rid,'data':sealed.seal(keys['request'],pair['id'],rid,'request',body)}
with device() as d:
 try:
  with parent('z'*43):raise AssertionError('Unauthorized parent connected')
 except InvalidStatus as e:assert e.response.status_code==401
 with parent() as p:
  packet=make('add-video',{'url':'https://youtu.be/abcdefghijk'})
  p.send(json.dumps(packet)); forwarded=json.loads(d.recv(timeout=5))
  assert forwarded['packet']==packet
  reply=sealed.dispatch(store,forwarded['packet'])['packet']
  d.send(json.dumps({'peer':forwarded['peer'],'packet':reply}))
  got=json.loads(p.recv(timeout=5));body=sealed.open_message(keys['response'],got['phone'],got['id'],'response',got['data'])
  assert body['ok'] and len(body['videos'])==1
  print('PASS: real relay websocket roundtrip authenticates and applies encrypted command')
 with parent() as p:
  disconnected=time.monotonic(); d.close()
  # Managed proxies can delay transport-close propagation. The server's
  # 30-second heartbeat bounds dead-connection detection to two intervals.
  try:assert json.loads(p.recv(timeout=65 if base.startswith('wss:') else 5))=={'error':'Computer offline'}
  except ConnectionClosed:pass
 print(f'PASS: device disconnect closes waiting parent connections ({time.monotonic()-disconnected:.1f}s)')
time.sleep(.2)
try:
 with parent():raise AssertionError('Offline device accepted')
except InvalidStatus as e:assert e.response.status_code==503
with device() as d, parent() as p:
 packet=make();p.send(json.dumps(packet));assert json.loads(d.recv(timeout=5))['packet']==packet
 print('PASS: same pairing reconnects after network interruption')
 family.revoke(store)
 try:sealed.dispatch(store,packet);raise AssertionError('Revoked phone accepted')
 except ValueError:pass
 print('PASS: revoked phone cannot execute commands even with a live relay connection')
