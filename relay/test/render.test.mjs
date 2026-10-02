import {test} from 'node:test';
import assert from 'node:assert/strict';
import {once} from 'node:events';
import {createHash,randomBytes} from 'node:crypto';
import {WebSocket} from 'ws';
import {createRelay} from '../src/render.mjs';

const sha = x => createHash('sha256').update(x).digest('hex');
test('Render adapter authenticates, routes, reconnects and fails closed offline', async t => {
  const relay=createRelay(); t.after(relay.stop);
  relay.server.listen(0,'127.0.0.1'); await once(relay.server,'listening');
  const base='ws://127.0.0.1:'+relay.server.address().port;
  const deviceToken=randomBytes(32).toString('base64url'), parentToken=randomBytes(32).toString('base64url');
  const channel=sha(deviceToken);
  const open=async (role,token) => {
    const ws=new WebSocket(base+'/v2/'+role+'/'+channel,{headers:{Authorization:'Bearer '+token,'X-Client-Hash':sha(parentToken)}});
    await once(ws,'open'); return ws;
  };
  const denied=async (role,token,status) => {
    const ws=new WebSocket(base+'/v2/'+role+'/'+channel,{headers:{Authorization:'Bearer '+token,'X-Client-Hash':sha(parentToken)}});
    const [,response]=await once(ws,'unexpected-response'); assert.equal(response.statusCode,status); ws.terminate(); ws.on('error',()=>{});
  };
  await denied('device',parentToken,401);
  const device=await open('device',deviceToken);
  await denied('parent',randomBytes(32).toString('base64url'),401);
  const parent=await open('parent',parentToken);
  const packet={phone:'a'.repeat(32),id:'b'.repeat(32),data:'c'.repeat(50)};
  let next=once(device,'message'); parent.send(JSON.stringify(packet));
  const routed=JSON.parse((await next)[0]); assert.deepEqual(routed.packet,packet);
  next=once(parent,'message'); device.send(JSON.stringify(routed)); assert.deepEqual(JSON.parse((await next)[0]),packet);
  next=once(parent,'message'); device.close(); assert.deepEqual(JSON.parse((await next)[0]),{error:'Computer offline'});
  await denied('parent',parentToken,503);
  const replacement=await open('device',deviceToken), again=await open('parent',parentToken);
  next=once(replacement,'message'); again.send(JSON.stringify(packet)); assert.deepEqual(JSON.parse((await next)[0]).packet,packet);
  const closed=once(again,'close'); again.send(JSON.stringify(packet)); assert.equal((await closed)[0],1008);
});
