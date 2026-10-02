import {createHash} from 'node:crypto';
const hex = /^[0-9a-f]{64}$/;
const sha = value => createHash('sha256').update(value).digest('hex');

// Only ciphertext and opaque lookup IDs live here, at most five minutes.
// Tombstones prevent a consumed code being republished during its lifetime.
export class PairingInbox {
  constructor(clock = () => Date.now()) { this.clock=clock; this.entries=new Map(); this.attempts=new Map(); }
  prune() {
    const now=this.clock();
    for (const [key,value] of this.entries) if (value.expires*1000 <= now) this.entries.delete(key);
    for (const [key,value] of this.attempts) if (value.start+60000 <= now) this.attempts.delete(key);
  }
  allow(ip) {
    this.prune();
    if (!this.attempts.has(ip)) {
      if (this.attempts.size >= 2048) return false;
      this.attempts.set(ip,{start:this.clock(),count:0});
    }
    return ++this.attempts.get(ip).count <= 12;
  }
  publish(value, authorization) {
    this.prune();
    const token=/^Bearer ([A-Za-z0-9_-]{43})$/.exec(authorization || '')?.[1];
    if (!value || typeof value !== 'object' || Object.keys(value).sort().join(',') !== 'channel,data,expires,slot' ||
        !token || !hex.test(value.channel) || sha(token) !== value.channel || !hex.test(value.slot) ||
        typeof value.data !== 'string' || !/^[A-Za-z0-9_-]{38,3000}$/.test(value.data) ||
        !Number.isInteger(value.expires) || value.expires*1000 <= this.clock() || value.expires*1000 > this.clock()+300000)
      return [400,{error:'Invalid pairing'}];
    if (this.entries.has(value.slot)) return [409,{error:'Generate a new code'}];
    if (this.entries.size >= 128) return [503,{error:'Try again shortly'}];
    for (const entry of this.entries.values()) if (entry.channel === value.channel) entry.data=null;
    this.entries.set(value.slot,{...value});
    return [201,{expires:value.expires}];
  }
  redeem(value) {
    this.prune();
    if (!value || typeof value !== 'object' || Object.keys(value).join(',') !== 'slot' || !hex.test(value.slot))
      return [400,{error:'Invalid pairing code'}];
    const entry=this.entries.get(value.slot);
    if (!entry?.data) return [404,{error:'Code unavailable'}];
    const data=entry.data; entry.data=null; // Consume atomically before sending.
    return [200,{data}];
  }
  async handle(req,res,ip) {
    const reply=(status,body) => { res.statusCode=status; res.end(JSON.stringify(body)); };
    if (req.method !== 'POST' || req.headers.origin || req.headers['content-type'] !== 'application/json')
      return reply(400,{error:'Native pairing required'});
    if (!this.allow(ip)) return reply(429,{error:'Wait a minute and try again'});
    let body='',size=0;
    try {
      for await (const chunk of req) {
        size += chunk.length;
        if (size > 4096) { reply(413,{error:'Pairing too large'}); req.destroy(); return; }
        body += chunk.toString('utf8');
      }
      const value=JSON.parse(body);
      const [status,result]=req.url === '/v2/pairings' ? this.publish(value,req.headers.authorization) : this.redeem(value);
      reply(status,result);
    } catch { if (!res.writableEnded) reply(400,{error:'Invalid pairing'}); }
  }
}
