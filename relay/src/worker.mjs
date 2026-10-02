// The service sees only routing capabilities and ciphertext. It has no parent
// token, decryption key, command parser, outbound fetch, or stored messages.
const hex32 = /^[0-9a-f]{32}$/;
const hex64 = /^[0-9a-f]{64}$/;
const token = /^[A-Za-z0-9_-]{43}$/;
const b64 = /^[A-Za-z0-9_-]+$/;
export const digest = async value => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))].map(x => x.toString(16).padStart(2, '0')).join('');
const deny = (status, error) => Response.json({ok: false, error}, {status, headers: {'Cache-Control': 'no-store'}});

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname === '/health')
      return Response.json({service: 'parent-pocket-relay', version: 2});
    const route = /^\/v2\/(device|parent)\/([0-9a-f]{64})$/.exec(url.pathname);
    if (!route || url.search || request.method !== 'GET') return deny(404, 'Not found');
    if (request.headers.has('Origin') || request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') return deny(400, 'Native connection required');
    const credential = /^Bearer ([A-Za-z0-9_-]{43})$/.exec(request.headers.get('Authorization') || '')?.[1];
    if (!token.test(credential || '')) return deny(401, 'Pair this device first');
    // Self-certifying device addresses require possession of a random 256-bit
    // secret before an object can be created. No reusable fleet admin key is
    // shipped to laptops. Parents use a different, less powerful capability.
    if (route[1] === 'device' && (await digest(credential) !== route[2] || !hex64.test(request.headers.get('X-Client-Hash') || '')))
      return deny(401, 'Invalid device');
    if (env.CONNECT_LIMIT && !(await env.CONNECT_LIMIT.limit({key: request.headers.get('CF-Connecting-IP') || 'local'})).success)
      return deny(429, 'Reconnect shortly');
    return env.ROOMS.get(env.ROOMS.idFromName(route[2])).fetch(request);
  }
};

export class Room {
  constructor(ctx, env) {
    this.ctx = ctx;
    ctx.setWebSocketAutoResponse(new WebSocketRequestResponsePair('ping', 'pong'));
  }
  async fetch(request) {
    const device = new URL(request.url).pathname.includes('/device/');
    if (device) {
      const hash = request.headers.get('X-Client-Hash');
      const old = await this.ctx.storage.get('client');
      if (old !== hash) {
        await this.ctx.storage.put('client', hash);
        for (const ws of this.ctx.getWebSockets('parent')) ws.close(1008, 'Pair again');
      }
      for (const ws of this.ctx.getWebSockets('device')) ws.close(1012, 'Reconnected');
    } else {
      const hash = await digest(request.headers.get('Authorization').slice(7));
      if (hash !== await this.ctx.storage.get('client')) return deny(401, 'Pair again');
      if (!this.ctx.getWebSockets('device').length) return deny(503, 'Computer offline');
      if (this.ctx.getWebSockets('parent').length >= 8) return deny(429, 'Connection busy');
    }
    const [client, server] = Object.values(new WebSocketPair());
    const peer = crypto.randomUUID().replaceAll('-', '');
    this.ctx.acceptWebSocket(server, [device ? 'device' : 'parent', peer]);
    server.serializeAttachment({device, peer, pending: null, count: 0, window: Date.now()});
    return new Response(null, {status: 101, webSocket: client});
  }
  webSocketMessage(ws, message) {
    const state = ws.deserializeAttachment();
    if (typeof message !== 'string' || message.length > (state.device ? 1_400_000 : 18000)) return ws.close(1009, 'Message too large');
    if (Date.now() - state.window > 60000) { state.window = Date.now(); state.count = 0; }
    if (++state.count > 120) return ws.close(1008, 'Too many messages');
    let value;
    try { value = JSON.parse(message); } catch { return ws.close(1008, 'Invalid message'); }
    const packet = state.device ? value?.packet : value;
    if (!packet || Object.keys(packet).sort().join(',') !== 'data,id,phone' || !hex32.test(packet.id) || !hex32.test(packet.phone)
        || typeof packet.data !== 'string' || !b64.test(packet.data) || packet.data.length < 38 || packet.data.length > (state.device ? 1_350_000 : 16000))
      return ws.close(1008, 'Invalid message');
    if (state.device) {
      if (!hex32.test(value.peer || '')) return ws.close(1008, 'Invalid peer');
      const target = this.ctx.getWebSockets(value.peer).find(s => !s.deserializeAttachment().device);
      if (target) {
        const parent = target.deserializeAttachment();
        if (parent.pending?.id === packet.id && parent.pending?.phone === packet.phone) {
          target.send(JSON.stringify(packet));
          parent.pending = null;
          target.serializeAttachment(parent);
        }
      }
    } else {
      if (state.pending) return ws.close(1008, 'Wait for the current request');
      const host = this.ctx.getWebSockets('device')[0];
      if (!host) return ws.close(1013, 'Computer offline');
      state.pending = {id: packet.id, phone: packet.phone};
      host.send(JSON.stringify({peer: state.peer, packet}));
    }
    ws.serializeAttachment(state);
  }
  webSocketClose(ws, code) {
    const state = ws.deserializeAttachment();
    ws.close(code === 1005 ? 1000 : code);
    if (state?.device && !this.ctx.getWebSockets('device').some(s => s.deserializeAttachment()?.peer !== state.peer))
      for (const parent of this.ctx.getWebSockets('parent')) {
        parent.send(JSON.stringify({error: 'Computer offline'}));
        parent.close(1013, 'Computer offline');
      }
  }
  webSocketError(ws) { ws.close(1011, 'Reconnect'); }
}
