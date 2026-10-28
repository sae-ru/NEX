const h = require('node:http2');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const [key, cert, gates] = process.argv.slice(2);
const server = h.createSecureServer({
  key: fs.readFileSync(key), cert: fs.readFileSync(cert),
  allowHTTP1: true, minVersion: 'TLSv1.2'
});
server.on('request', (req, res) => {
  req.on('error', () => {}); res.on('error', () => {});
  const chunks = [];
  req.on('data', value => chunks.push(value));
  req.on('end', () => {
    const payload = Buffer.concat(chunks);
    const answer = () => {
      if (res.destroyed) return;
      res.setHeader('x-protocol', req.httpVersion);
      res.setHeader('set-cookie', ['first=1', 'second=2']);
      res.end(payload.length ? payload : Buffer.from('42'));
    };
    if (req.url.startsWith('/held-')) {
      const marker = crypto.createHash('sha256').update(req.url).digest('hex');
      fs.writeFileSync(path.join(gates, marker + '.ready'), 'ready');
      const timer = setInterval(() => {
        if (res.destroyed) { clearInterval(timer); return; }
        if (fs.existsSync(path.join(gates, marker + '.release'))) {
          clearInterval(timer); answer();
        }
      }, 10);
      timer.unref();
    } else answer();
  });
});
server.on('tlsClientError', () => {});
server.listen(0, '127.0.0.1', () => {
  console.log(JSON.stringify({ port: server.address().port }));
});
