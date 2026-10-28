// Ordinary loopback HTTPS/HTTP2 peer for incremental NEX response reads.
const http2 = require('node:http2');
const fs = require('node:fs');
const [key, certificate, events, release] = process.argv.slice(2);
const amount = 2 * 1024 * 1024 + 17;
const chunk = Buffer.alloc(16384);
for (let i = 0; i < chunk.length; ++i) chunk[i] = i % 256;
const server = http2.createSecureServer({
  key: fs.readFileSync(key), cert: fs.readFileSync(certificate),
  allowHTTP1: true, minVersion: 'TLSv1.2'
});
server.on('request', (request, response) => {
  request.on('error', () => {});
  response.on('error', () => {});
  fs.appendFileSync(events, JSON.stringify({protocol: request.httpVersion, path: request.url}) + '\n');
  response.writeHead(200, {'content-length': String(amount)});
  response.flushHeaders();
  let sent = 0;
  function write() {
    while (!response.destroyed && sent < amount) {
      const part = chunk.subarray(0, Math.min(chunk.length, amount - sent));
      sent += part.length;
      if (!response.write(part)) { response.once('drain', write); return; }
    }
    if (!response.destroyed) response.end();
  }
  if (request.url === '/concurrent' && release) {
    const timer = setInterval(() => {
      if (response.destroyed) { clearInterval(timer); return; }
      if (fs.existsSync(release)) { clearInterval(timer); write(); }
    }, 5);
    timer.unref();
  } else write();
});
server.listen(0, '127.0.0.1', () => {
  console.log(JSON.stringify({port: server.address().port}));
});
