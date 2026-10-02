import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker, {Room, digest} from '../src/worker.mjs';

globalThis.WebSocketRequestResponsePair = class {};
class Socket {
  constructor(state) { this.state = state; this.sent = []; }
  deserializeAttachment() { return structuredClone(this.state); }
  serializeAttachment(s) { this.state = structuredClone(s); }
  send(s) { this.sent.push(JSON.parse(s)); }
  close(code) { this.closed = code; }
}
function fixture() {
  const host = new Socket({device:true,peer:'a'.repeat(32),count:0,window:Date.now()});
  const parent = new Socket({device:false,peer:'b'.repeat(32),pending:null,count:0,window:Date.now()});
  const other = new Socket({device:false,peer:'c'.repeat(32),pending:null,count:0,window:Date.now()});
  const ctx = {setWebSocketAutoResponse(){}, getWebSockets(tag){return [host,parent,other].filter(s=>!s.closed && (tag === s.state.peer || tag === (s.state.device?'device':'parent')));}};
  const room = new Room(ctx, {});
  const packet = {phone:'d'.repeat(32),id:'e'.repeat(32),data:'f'.repeat(60)};
  return {room,host,parent,other,packet,ctx};
}
test('one encrypted request is routed only to its originating parent', () => {
  const {room,host,parent,other,packet} = fixture();
  room.webSocketMessage(parent,JSON.stringify(packet));
  assert.deepEqual(host.sent[0],{peer:parent.state.peer,packet});
  room.webSocketMessage(host,JSON.stringify({peer:parent.state.peer,packet}));
  assert.deepEqual(parent.sent,[packet]); assert.equal(other.sent.length,0);
  room.webSocketMessage(host,JSON.stringify({peer:other.state.peer,packet}));
  assert.equal(other.sent.length,0);
});
test('out-of-order responses, request flooding and oversize payloads are rejected', () => {
  const {room,host,parent,packet} = fixture();
  room.webSocketMessage(parent,JSON.stringify(packet));
  room.webSocketMessage(host,JSON.stringify({peer:parent.state.peer,packet:{...packet,id:'0'.repeat(32)}}));
  assert.equal(parent.sent.length,0);
  room.webSocketMessage(parent,JSON.stringify(packet)); assert.equal(parent.closed,1008);
  room.webSocketMessage(host,'a'.repeat(1_400_001)); assert.equal(host.closed,1009);
});
test('offline commands are not queued for later execution', () => {
  const {room,host,parent,packet} = fixture(); host.closed = 1000;
  room.webSocketMessage(parent,JSON.stringify(packet)); assert.equal(parent.closed,1013);
  assert.equal(host.sent.length,0);
});
test('routing requires proof of the device secret and rejects browser origins', async () => {
  const credential='a'.repeat(43), channel=await digest(credential);
  const headers={Upgrade:'websocket',Authorization:'Bearer '+credential,'X-Client-Hash':'b'.repeat(64)};
  let forwarded=0;
  const env={ROOMS:{idFromName:x=>x,get:()=>({fetch:()=>{forwarded++;return new Response('ok');}})}};
  assert.equal((await worker.fetch(new Request('https://relay.example/v2/device/'+channel,{headers}),env)).status,200);
  for (const h of [{...headers,Authorization:'Bearer '+'c'.repeat(43)},{...headers,Origin:'https://evil.example'}])
    assert.notEqual((await worker.fetch(new Request('https://relay.example/v2/device/'+channel,{headers:h}),env)).status,200);
  assert.equal(forwarded,1);
});
