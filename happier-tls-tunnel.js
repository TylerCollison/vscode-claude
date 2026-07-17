#!/usr/bin/env node
/**
 * happier-tls-tunnel.js — TLS-wrapped TCP tunnel for happier-server
 *
 * Terminates TLS and forwards plaintext to a local HTTP backend.
 * This makes crypto.subtle available in the browser (secure context).
 * WebSocket connections pass through transparently (raw TCP tunnel).
 *
 * Uses only Node.js built-in modules — zero npm dependencies.
 */

const tls = require('tls');
const net = require('net');
const fs = require('fs');
const path = require('path');

const LISTEN_PORT = parseInt(process.env.TUNNEL_PORT || '3005', 10);
const TARGET_HOST = process.env.TUNNEL_TARGET_HOST || 'localhost';
const TARGET_PORT = parseInt(process.env.TUNNEL_TARGET_PORT || '3006', 10);
const CERT_DIR = process.env.TUNNEL_CERT_DIR || '/app/.happy/server-light';
const KEY_FILE = path.join(CERT_DIR, 'tunnel.key');
const CERT_FILE = path.join(CERT_DIR, 'tunnel.crt');

// --- Validate certs exist ---
for (const f of [KEY_FILE, CERT_FILE]) {
  if (!fs.existsSync(f)) {
    console.error(`FATAL: TLS cert not found: ${f}`);
    process.exit(1);
  }
}

const options = {
  key: fs.readFileSync(KEY_FILE),
  cert: fs.readFileSync(CERT_FILE),
};

let activeConnections = 0;

const server = tls.createServer(options, (tlsSocket) => {
  activeConnections++;
  const remoteAddr = `${tlsSocket.remoteAddress}:${tlsSocket.remotePort}`;

  let target;
  let retries = 3;

  const connectToBackend = () => {
    target = net.createConnection(TARGET_PORT, TARGET_HOST, () => {
      tlsSocket.pipe(target).pipe(tlsSocket);
    });

    target.on('error', (err) => {
      if (retries > 0 && (err.code === 'ECONNREFUSED' || err.code === 'ETIMEDOUT')) {
        console.warn(`[${remoteAddr}] Backend connection failed (${err.code}), retrying... (${retries} left)`);
        retries--;
        setTimeout(connectToBackend, 500);
        return;
      }
      console.error(`[${remoteAddr}] Backend error (${TARGET_HOST}:${TARGET_PORT}): ${err.message}`);
      cleanup();
    });

    target.on('end', () => { try { tlsSocket.end(); } catch (_) {} });
    target.on('close', cleanup);
  };

  const cleanup = () => {
    activeConnections--;
    try { tlsSocket.destroy(); } catch (_) {}
    try { target.destroy(); } catch (_) {}
  };

  tlsSocket.on('error', (err) => {
    console.error(`[${remoteAddr}] TLS socket error: ${err.message}`);
    cleanup();
  });

  tlsSocket.on('end', () => { try { target.end(); } catch (_) {} });
  tlsSocket.on('close', cleanup);

  connectToBackend();
});

server.listen(LISTEN_PORT, '0.0.0.0', () => {
  console.log(`Happier TLS tunnel listening on 0.0.0.0:${LISTEN_PORT}`);
  console.log(`  → forwarding to ${TARGET_HOST}:${TARGET_PORT}`);
  console.log(`  → 0 active connections`);
});

server.on('error', (err) => {
  console.error(`FATAL: TLS tunnel error: ${err.message}`);
  process.exit(1);
});
