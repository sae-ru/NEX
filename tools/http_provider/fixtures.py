"""Owned loopback DNS, HTTP/1.1, HTTP/2 and stalled TLS peers."""
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shutil
import selectors
import socket
import socketserver
import subprocess
import threading

ROOT=Path(__file__).resolve().parents[2]
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
class Fixtures:
 def __init__(self,out,doctor):
  self.out=Path(out);self.files=self.out/'gates';self.files.mkdir();self.events=[];self.lock=threading.Lock();self.stop=threading.Event();self.servers=[];self.node=None;self.dns=None;self.cert=self.out/'cert';self.cert.mkdir()
  try:
   openssl=Path(doctor['native_openssl_crypto']).resolve().parent.parent/'bin/openssl'
   if not openssl.is_file():openssl=shutil.which('openssl')
   if not openssl:raise RuntimeError('OpenSSL certificate tool is required')
   commands=[['req','-x509','-newkey','rsa:2048','-noenc','-subj','/CN=NEX owned HTTP root','-keyout',self.cert/'root.key','-out',self.cert/'root.pem','-days','2','-addext','basicConstraints=critical,CA:TRUE'],['req','-new','-newkey','rsa:2048','-noenc','-subj','/CN=api.example.test','-keyout',self.cert/'server.key','-out',self.cert/'server.csr']]
   (self.cert/'extensions').write_text('subjectAltName=DNS:api.example.test\nbasicConstraints=critical,CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
   commands.append(['x509','-req','-in',self.cert/'server.csr','-CA',self.cert/'root.pem','-CAkey',self.cert/'root.key','-CAcreateserial','-out',self.cert/'server.pem','-days','1','-extfile',self.cert/'extensions'])
   for index,args in enumerate(commands):
    p=subprocess.run(list(map(str,[openssl,*args])),capture_output=True,text=True,timeout=30);(self.out/('certificate-'+str(index)+'.stdout')).write_text(p.stdout);(self.out/('certificate-'+str(index)+'.stderr')).write_text(p.stderr)
    if p.returncode:raise RuntimeError('test certificate generation failed: '+p.stderr[-1000:])
   for p in self.cert.glob('*.key'):p.chmod(0o600)
   spec=importlib.util.spec_from_file_location('nex_http_owned_DNS',ROOT/'tools/dns_provider/verify.py');dns_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(dns_module);self.dns=dns_module.DNS(self.files,answer_ipv4='127.0.0.1',answer_ipv6='::1')
   owner=self
   class Server(http.server.ThreadingHTTPServer):daemon_threads=True
   class IPv6(Server):address_family=socket.AF_INET6
   class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def handle(self):
     try:super().handle()
     except (ConnectionResetError,BrokenPipeError):pass
    def action(self):
     body=self.rfile.read(int(self.headers.get('Content-Length','0')));payload=body or b'42';status=200;headers={}
     with owner.lock:owner.events.append({'method':self.command,'path':self.path,'authorization':self.headers.get('Authorization'),'cookie':self.headers.get('Cookie'),'port':self.server.server_address[1]})
     if self.path=='/missing':status=404
     elif self.path=='/redirect':status=302;headers['Location']='/ok'
     elif self.path=='/loop':status=302;headers['Location']='/loop'
     elif self.path=='/cross':status=302;headers['Location']='http://other.example.test:'+str(self.server.server_address[1])+'/credentials'
     elif self.path=='/credentials':payload=json.dumps({'authorization':self.headers.get('Authorization'),'cookie':self.headers.get('Cookie')}).encode()
     elif self.path=='/many':payload=b'x'*128
     elif self.path=='/invalid-UTF8':payload=bytes([255,128,0])
     elif self.path.startswith('/held-'):
      marker=digest(self.path);(owner.files/(marker+'.ready')).write_text('ready')
      while not (owner.files/(marker+'.release')).exists():
       if owner.stop.wait(.01):return
     try:
      self.send_response(status)
      for k,v in headers.items():self.send_header(k,v)
      if self.path=='/header-bytes':self.send_header('X-Bytes','\xff')
      if self.path=='/too-many-headers':
       for i in range(65):self.send_header('x-'+str(i),'value')
      self.send_header('Content-Length',str(len(payload)));self.end_headers()
      if self.command!='HEAD':self.wfile.write(payload)
     except (BrokenPipeError,ConnectionResetError):pass
    do_GET=action;do_POST=action;do_PUT=action;do_HEAD=action
   self.http=self.start(Server(('127.0.0.1',0),Handler));self.http6=self.start(IPv6(('::1',0),Handler));self.http_port=self.http.server_address[1];self.http6_port=self.http6.server_address[1]
   class Stalled(socketserver.ThreadingTCPServer):daemon_threads=True;allow_reuse_address=True
   class StallHandler(socketserver.BaseRequestHandler):
    def handle(self):
     with owner.lock:owner.events.append({'method':'TLS_HELLO','path':'/stalled-TLS','port':self.server.server_address[1]})
     while not owner.stop.wait(.01):
      self.request.settimeout(.01)
      try:
       data=self.request.recv(4096)
       if not data:return
      except socket.timeout:pass
      except OSError:return
   self.stall=self.start(Stalled(('127.0.0.1',0),StallHandler));self.stall_port=self.stall.server_address[1]
   node=shutil.which('node')
   if not node:raise RuntimeError('Node with built-in HTTP2 is required')
   self.node_log=(self.out/'http2-server.stderr').open('w');self.node=subprocess.Popen([node,str(Path(__file__).parent/'http2_fixture.js'),str(self.cert/'server.key'),str(self.cert/'server.pem'),str(self.files)],stdout=subprocess.PIPE,stderr=self.node_log,text=True)
   with selectors.DefaultSelector() as readiness:
    readiness.register(self.node.stdout,selectors.EVENT_READ)
    if not readiness.select(10):raise RuntimeError('owned HTTP2 server did not become ready')
    self.https_port=json.loads(self.node.stdout.readline())['port']
  except BaseException:self.close();raise
 def start(self,server):
  self.servers.append(server);threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True).start();return server
 def config(self,capacity=16):
  return {'schema':'nex.http-targets/1','maximum_calls':capacity,'resolvers':[{'address':'127.0.0.1','port':self.dns.port}],'ca_file':str(self.cert/'root.pem'),'authorities':[{'name':'backend','domain':'example.test','subdomains':True,'schemes':['http','https'],'ports':[self.http_port,self.http6_port,self.https_port,self.stall_port],'methods':['GET','POST','PUT','HEAD']},{'name':'ip4','domain':'127.0.0.1','subdomains':False,'schemes':['http'],'ports':[self.http_port],'methods':['GET']},{'name':'ip6','domain':'::1','subdomains':False,'schemes':['http'],'ports':[self.http6_port],'methods':['GET']}]}
 def close(self):
  self.stop.set()
  if self.node:self.node.terminate();self.node.wait(timeout=5);self.node=None;self.node_log.close()
  for server in self.servers:server.shutdown();server.server_close()
  self.servers=[]
  if self.dns:self.dns.close();self.dns=None
