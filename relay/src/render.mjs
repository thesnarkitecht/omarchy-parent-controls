// Single-instance managed deployment. All state is disposable connection state;
// devices reconnect after host restarts. Parent secrets remain on the endpoints.
import http from 'node:http';
import {createHash, randomUUID} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {isIP} from 'node:net';
import {WebSocketServer, WebSocket} from 'ws';
import {Room} from './worker.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
const credential = /^[A-Za-z0-9_-]{43}$/;
const reject = (socket, code) => { socket.end(`HTTP/1.1 ${code} Rejected\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`); };

export function createRelay() {
  const rooms = new Map(), attempts = new Map();
  const devices = new WebSocketServer({noServer:true, maxPayload:1_400_000, perMessageDeflate:false});
  const parents = new WebSocketServer({noServer:true, maxPayload:18000, perMessageDeflate:false});
  const server = http.createServer((req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Type', 'application/json');
    if (req.method === 'GET' && req.url === '/health') {
      res.end(JSON.stringify({service:'parent-pocket-relay',version:2}));
    } else { res.statusCode=404; res.end('{"error":"Not found"}'); }
  });
  server.requestTimeout = 10000; server.headersTimeout = 10000;
  server.on('upgrade', (req, socket, head) => {
    socket.on('error', () => {});
    const route = /^\/v2\/(device|parent)\/([0-9a-f]{64})$/.exec(req.url || '');
    const token = /^Bearer ([A-Za-z0-9_-]{43})$/.exec(req.headers.authorization || '')?.[1];
    if (!route || req.method !== 'GET' || req.headers.origin || !credential.test(token || '')) return reject(socket,401);
    const forwarded = process.env.RENDER ? req.headers['x-forwarded-for']?.split(',').at(-1)?.trim() : null;
    const ip = isIP(forwarded || '') ? forwarded : socket.remoteAddress;
    const now = Date.now();
    if (attempts.size > 2048) return reject(socket,429);
    let attempt = attempts.get(ip);
    if (!attempt || now-attempt.start > 60000) { attempt={start:now,count:0}; attempts.set(ip,attempt); }
    if (++attempt.count > 60) return reject(socket,429);
    const device = route[1] === 'device', channel = route[2];
    const clientHash = req.headers['x-client-hash'];
    let room = rooms.get(channel);
    if (device) {
      if (sha(token) !== channel || typeof clientHash !== 'string' || !/^[0-9a-f]{64}$/.test(clientHash)) return reject(socket,401);
      if (!room) {
        if (rooms.size >= 32) return reject(socket,503);
        const sockets = new Set();
        const ctx = {getWebSockets(tag) { return [...sockets].filter(ws => ws.readyState === WebSocket.OPEN &&
          (tag === ws.state.peer || tag === (ws.state.device ? 'device' : 'parent'))); }};
        room = {sockets, handler:new Room(ctx, {}), clientHash};
      }
    } else {
      if (!room || ![...room.sockets].some(ws => ws.state.device && ws.readyState === WebSocket.OPEN)) return reject(socket,503);
      if (sha(token) !== room.clientHash) return reject(socket,401);
      if ([...room.sockets].filter(ws => !ws.state.device).length >= 8) return reject(socket,429);
    }
    // No awaits between authorization and upgrade: only a successful device
    // handshake can replace its predecessor or rotate its parent capability.
    (device ? devices : parents).handleUpgrade(req,socket,head,ws => {
      rooms.set(channel,room);
      if (device) {
        for (const existing of room.sockets)
          if (existing.state.device || room.clientHash !== clientHash) existing.close(1012,'Reconnected');
        room.clientHash = clientHash;
      }
      ws.state = {device,peer:randomUUID().replaceAll('-',''),pending:null,count:0,window:now};
      ws.deserializeAttachment = () => structuredClone(ws.state);
      ws.serializeAttachment = state => { ws.state=structuredClone(state); };
      const send = ws.send.bind(ws);
      ws.send = value => {
        if (ws.readyState !== WebSocket.OPEN) return;
        if (ws.bufferedAmount > 1_400_000) return ws.close(1008,'Slow connection');
        send(value);
      };
      room.sockets.add(ws); ws.alive = true;
      ws.on('pong', () => { ws.alive=true; });
      ws.on('message', (message, binary) => {
        ws.alive=true;
        if (binary) return ws.close(1008,'Text messages only');
        room.handler.webSocketMessage(ws,message.toString('utf8'));
      });
      ws.on('close', code => {
        room.sockets.delete(ws);
        room.handler.webSocketClose(ws,code);
        if (!room.sockets.size && rooms.get(channel) === room) rooms.delete(channel);
      });
      ws.on('error', () => ws.terminate());
    });
  });
  const heartbeat = setInterval(() => {
    const now=Date.now();
    for (const [key,value] of attempts) if (now-value.start > 60000) attempts.delete(key);
    for (const room of rooms.values()) for (const ws of room.sockets) {
      if (ws.readyState !== WebSocket.OPEN || !ws.alive) { ws.terminate(); continue; }
      ws.alive=false; ws.ping();
    }
  },30000);
  heartbeat.unref();
  const stop = () => {
    clearInterval(heartbeat);
    for (const room of rooms.values()) for (const ws of room.sockets) ws.terminate();
    devices.close(); parents.close(); server.close();
  };
  return {server,stop};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const relay=createRelay();
  relay.server.listen(Number(process.env.PORT || 8788),'0.0.0.0',() => console.log('Encrypted parent relay ready.'));
  process.on('SIGTERM',relay.stop); process.on('SIGINT',relay.stop);
}
