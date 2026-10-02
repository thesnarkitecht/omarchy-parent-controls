import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomBytes} from 'node:crypto';
import {once} from 'node:events';
import {PairingInbox} from '../src/pairings.mjs';
import {createRelay} from '../src/render.mjs';
const token=randomBytes(32).toString('base64url');
const packet=(expires=1300) => ({slot:randomBytes(32).toString('hex'),data:'a'.repeat(80),expires,
  channel:createHash('sha256').update(token).digest('hex')});

test('codes expire, are consumed once, and cannot be replaced or republished', () => {
  let now=1000000; const inbox=new PairingInbox(()=>now), value=packet();
  assert.equal(inbox.publish(value,'Bearer '+token)[0],201);
  assert.equal(inbox.publish({...value,data:'b'.repeat(80)},'Bearer '+token)[0],409);
  assert.deepEqual(inbox.redeem({slot:value.slot}),[200,{data:value.data}]);
  assert.equal(inbox.redeem({slot:value.slot})[0],404);
  assert.equal(inbox.publish(value,'Bearer '+token)[0],409);
  const next=packet(); assert.equal(inbox.publish(next,'Bearer '+token)[0],201);
  now=1300000; assert.equal(inbox.redeem({slot:next.slot})[0],404);
  assert.equal(inbox.entries.size,0);
});
test('new codes retire old ones; unauthenticated publishing and long expiry fail', () => {
  const inbox=new PairingInbox(()=>1000000), first=packet(), second=packet();
  assert.equal(inbox.publish(first,'')[0],400);
  assert.equal(inbox.publish(packet(1301),'Bearer '+token)[0],400);
  assert.equal(inbox.publish(first,'Bearer '+token)[0],201);
  assert.equal(inbox.publish(second,'Bearer '+token)[0],201);
  assert.equal(inbox.redeem({slot:first.slot})[0],404);
  assert.equal(inbox.redeem({slot:second.slot})[0],200);
});
test('attempts are bounded and expire', () => {
  let now=0; const inbox=new PairingInbox(()=>now);
  for(let i=0;i<12;i++) assert.equal(inbox.allow('client'),true);
  assert.equal(inbox.allow('client'),false);
  now=60000; assert.equal(inbox.allow('client'),true);
});
test('HTTP redemption is atomic, no-store, and rejects browser origins', async t => {
  const relay=createRelay(); t.after(relay.stop);
  relay.server.listen(0,'127.0.0.1'); await once(relay.server,'listening');
  const base='http://127.0.0.1:'+relay.server.address().port;
  const post=(path,body,headers={}) => fetch(base+path,{method:'POST',headers:{'content-type':'application/json',...headers},body:JSON.stringify(body)});
  const value=packet(Math.floor(Date.now()/1000)+300);
  assert.equal((await post('/v2/pairings',value,{authorization:'Bearer '+token,origin:'https://evil.example'})).status,400);
  assert.equal((await post('/v2/pairings',value,{authorization:'Bearer '+token})).status,201);
  const results=await Promise.all([post('/v2/pairings/redeem',{slot:value.slot}),post('/v2/pairings/redeem',{slot:value.slot})]);
  assert.deepEqual(results.map(x=>x.status).sort(),[200,404]);
  assert.equal(results[0].headers.get('cache-control'),'no-store');
});
