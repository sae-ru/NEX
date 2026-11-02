#!/usr/bin/env python3
"""Actual AST/native DNS calls against owned loopback UDP/TCP name servers."""
import argparse
import hashlib
import errno
import json
import os
from pathlib import Path
import re
import shutil
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
def digest(data):return hashlib.sha256(data).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
class DNS:
    def __init__(self,files,address='127.0.0.1',answer_ipv4='127.0.0.42',answer_ipv6='2001:db8::42'):
        self.answer_ipv4=answer_ipv4;self.answer_ipv6=answer_ipv6
        self.files=files;self.events=[];self.lock=threading.Lock();self.stop=threading.Event();owner=self
        family=socket.AF_INET6 if ':' in address else socket.AF_INET
        class UDP(socketserver.ThreadingUDPServer):daemon_threads=True;allow_reuse_address=False;address_family=family
        class TCP(socketserver.ThreadingTCPServer):daemon_threads=True;allow_reuse_address=False;address_family=family
        class Datagram(socketserver.BaseRequestHandler):
            def handle(self):owner.reply(self.request[0],self.client_address,self.request[1],'udp')
        class Stream(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(5)
                def read(count):
                    data=bytearray()
                    while len(data)<count:
                        chunk=self.request.recv(count-len(data))
                        if not chunk:return None
                        data.extend(chunk)
                    return bytes(data)
                try:
                    for _ in range(16):
                        prefix=read(2)
                        if prefix is None:return
                        length=struct.unpack('!H',prefix)[0]
                        if not 12<=length<=4096:return
                        packet=read(length)
                        if packet is None:return
                        owner.reply(packet,self.client_address,self.request,'tcp')
                except OSError:pass
        # TCP and UDP have separate ephemeral/excluded-port inventories on
        # Windows. Reserve a valid TCP port first, then bind its UDP partner.
        # Retry only a genuine address collision; policy denials still fail.
        for attempt in range(8):
            tcp=TCP((address,0),Stream)
            try:udp=UDP((address,tcp.server_address[1]),Datagram)
            except OSError as error:
                tcp.server_close()
                if (error.errno==errno.EADDRINUSE or getattr(error,'winerror',None)==10048) and attempt<7:continue
                raise
            self.tcp=tcp;self.udp=udp;self.port=tcp.server_address[1];break
        self.threads=[]
        for server in (self.udp,self.tcp):
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start();self.threads.append(thread)
    def count(self):
        with self.lock:return len(self.events)
    def reply(self,packet,peer,stream,transport):
        try:
            if len(packet)<12:return
            identifier,_,questions,_,_,_=struct.unpack('!6H',packet[:12])
            if questions!=1:return
            at=12;labels=[]
            while at<len(packet) and packet[at]:
                length=packet[at];at+=1
                if length>63 or at+length>len(packet):return
                labels.append(packet[at:at+length].decode('ascii'));at+=length
            at+=1
            if at+4>len(packet):return
            qtype,qclass=struct.unpack('!HH',packet[at:at+4]);question=packet[12:at+4];name='.'.join(labels).lower()
            with self.lock:self.events.append({'name':name,'qtype':qtype,'transport':transport})
            if name.startswith('held-'):
                marker=digest(name.encode());(self.files/(marker+'.ready')).write_text('ready')
                if not name.startswith('held-progress-'):return
                while not (self.files/(marker+'.release')).is_file():
                    if self.stop.wait(.01):return
            flags=0x8180;records=[]
            if name.startswith('missing.'):flags=0x8183
            elif name.startswith('tcp.') and transport=='udp':flags=0x8380
            elif qclass==1 and qtype in (1,28):
                count=8 if name.startswith('many.') and qtype==1 else 1
                if name.startswith('duplicate.'):count=2
                for i in range(count):
                    address=('10.0.0.'+str(i+1) if name.startswith('many.') else self.answer_ipv4) if qtype==1 else self.answer_ipv6
                    data=socket.inet_pton(socket.AF_INET if qtype==1 else socket.AF_INET6,address)
                    records.append(b'\xc0\x0c'+struct.pack('!HHIH',qtype,1,30,len(data))+data)
            answer=struct.pack('!6H',identifier,flags,1,len(records),0,0)+question+b''.join(records)
            if transport=='udp':
                if name.startswith('spoof.'):
                    data=socket.inet_pton(socket.AF_INET,'203.0.113.250') if qtype==1 else socket.inet_pton(socket.AF_INET6,'2001:db8::dead')
                    forged=struct.pack('!6H',identifier,0x8180,1,1,0,0)+question+b'\xc0\x0c'+struct.pack('!HHIH',qtype,1,30,len(data))+data
                    with socket.socket(stream.family,socket.SOCK_DGRAM) as rogue:rogue.sendto(forged,peer)
                    stream.sendto(struct.pack('!H',(identifier+1)%65536)+forged[2:],peer)
                stream.sendto(answer,peer)
            else:stream.sendall(struct.pack('!H',len(answer))+answer)
        except (OSError,UnicodeError,struct.error):return
    def close(self):
        self.stop.set()
        for server in (self.udp,self.tcp):server.shutdown();server.server_close()
        for thread in self.threads:thread.join(timeout=3)

def source_for_selected_sdk(program, sdk):
    """Author fresh025/026 scope/join fixtures; retain matching024 fixture effects."""
    language = json.loads((sdk/'share/nex/llm/language-pack.json').read_text())['language_version']
    if language not in ('0.25','0.26','0.27', '0.28'):
        return program
    program = re.sub(r'(fn\([^)]*:task_scope\)->[^{}]*!)\{(task,ffi(?:,fs)?)\}',
                     r'\1{\2,throw}', program)
    for effects in ['task,ffi,fs,io', 'task,ffi,io']:
        program = program.replace('server fn main()->unit !{'+effects+'}',
                                  'server fn main()->unit !{'+effects+',throw}')
    return program


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',type=Path);parser.add_argument('--compiler',type=Path);parser.add_argument('--resources',type=Path);parser.add_argument('--cares-prefix',type=Path,required=True);parser.add_argument('--output',type=Path);parser.add_argument('--case',action='append',default=[],help='Run selected diagnostic cases; does not satisfy full conformance')
    args=parser.parse_args();out=args.output.absolute() if args.output else Path(tempfile.mkdtemp(prefix='nex-dns-source-'));temporary=args.output is None
    if not temporary:out.mkdir(parents=True)
    cares=args.cares_prefix.resolve(strict=True)
    shutil.copy2(Path(__file__),out/'verify-input.py')
    report={'schema':'nex.dns-source-conformance/1','ok':False,'cases':[],'commands':[],'full_objective_complete':False,'DNS_server_scope':'owned loopback UDP/TCP only'};started=time.monotonic();peer=None;ipv6=None
    def save():report['seconds']=round(time.monotonic()-started,3);write(out/'report.json',report)
    def run(label,argv,*,cwd=None,env=None,expected=0,parsed=True):
        argv=list(map(str,argv));row={'label':label,'argv':argv,'state':'running'};report['commands'].append(row);report['state']=label;save()
        p=subprocess.run(argv,cwd=cwd or out,env=env,capture_output=True,text=True,timeout=240)
        (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr);row.update(exit_code=p.returncode,state='passed' if p.returncode==expected else 'failed');save()
        assert p.returncode==expected,(label,p.stdout[-4000:],p.stderr[-2500:])
        return json.loads(p.stdout) if parsed else p
    try:
        if args.sdk:sdk=args.sdk.resolve(strict=True)
        else:
            if not args.compiler or not args.resources:parser.error('use --sdk or --compiler and --resources')
            sdk=out/'source-projection';(sdk/'bin').mkdir(parents=True);(sdk/'share').mkdir();shutil.copy2(args.compiler.resolve(strict=True),sdk/'bin'/('nex.exe' if os.name=='nt' else 'nex'));(sdk/'share/nex').symlink_to(args.resources.resolve(strict=True),target_is_directory=True)
        compiler=sdk/'bin'/('nex.exe' if os.name=='nt' else 'nex');resources=sdk/'share/nex';env={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1','NEX_TRACY':'0'};env.pop('NEX_FOREIGN_CONFIG',None)
        files=out/'files';files.mkdir();env.update(NEX_FILES_ROOT=str(files),NEX_FILES_WRITE='1');peer=DNS(files)
        config={'schema':'nex.dns-targets/1','resolvers':[{'address':'127.0.0.1','port':peer.port}],'authorities':[{'name':'public','domain':'example.test','subdomains':True},{'name':'exact','domain':'exact.example.test','subdomains':False},{'name':'all','domain':'*','subdomains':True}]}
        targets=out/'targets.json';write(targets,config);project=out/'project % 🧠'
        run('prepare',[sys.executable,'-B',ROOT/'tools/dns_provider/prepare.py','--sdk',sdk,'--targets',targets,'--cares-prefix',cares,'--output',project,'--diagnostics'],env=env,parsed=False)
        prepared=json.loads((project/'evidence/report.json').read_text());assert prepared['ok'] and not prepared['network_executed'] and not prepared['module_initialized'] and peer.count()==0
        report.update(compiler_sha256=digest(compiler.read_bytes()),actual_compiler_toolchain=prepared['toolchain'],language=prepared['language'],provider_tools_from=str(ROOT),runtime_resources_from=str(resources),provider_manifest_sha256=prepared['manifest_sha256'],provider_module_sha256=prepared['module_sha256'])
        config['maximum_calls']=1;capacity_targets=out/'capacity.json';write(capacity_targets,config);capacity=out/'capacity-project'
        run('prepare-capacity',[sys.executable,'-B',ROOT/'tools/dns_provider/prepare.py','--sdk',sdk,'--targets',capacity_targets,'--cares-prefix',cares,'--output',capacity,'--diagnostics'],env=env,parsed=False)
        prefix=(project/'main.nex').read_text().split('server fn main()->unit',1)[0];capacity_prefix=(capacity/'main.nex').read_text().split('server fn main()->unit',1)[0]
        if not args.case or any(name.startswith('ipv6-') for name in args.case):ipv6=DNS(files,'::1')
        if ipv6:
            config['maximum_calls']=16;config['resolvers']=[{'address':'::1','port':ipv6.port}];ipv6_targets=out/'ipv6.json';write(ipv6_targets,config);ipv6_project=out/'ipv6-project'
            run('prepare-ipv6',[sys.executable,'-B',ROOT/'tools/dns_provider/prepare.py','--sdk',sdk,'--targets',ipv6_targets,'--cares-prefix',cares,'--output',ipv6_project,'--diagnostics'],env=env,parsed=False)
            ipv6_prefix=(ipv6_project/'main.nex').read_text().split('server fn main()->unit',1)[0]
        good='["127.0.0.42","2001:db8::42"]'
        cases=[
            ('addresses','assert(unwrap(dns::lookup(make_client(),"public","service.example.test",1000))=='+good+');',None),
            ('case-root','assert(unwrap(dns::execute(make_client(),dns::request("exact","EXACT.EXAMPLE.TEST.",64,1000)))=='+good+');',None),
            ('wildcard','assert(unwrap(dns::execute(make_client(),dns::request("all","outside.test",64,1000)))=='+good+');',None),
            ('duplicate','assert(unwrap(dns::execute(make_client(),dns::request("public","duplicate.example.test",64,1000)))=='+good+');',None),
            ('tcp-fallback','assert(unwrap(dns::execute(make_client(),dns::request("public","tcp.example.test",64,1000)))=='+good+');',None),
            ('spoof','assert(unwrap(dns::execute(make_client(),dns::request("public","spoof.example.test",64,1000)))=='+good+');',None),
            ('ipv6-resolver','assert(unwrap(dns::lookup(make_client(),"public","service.example.test",1000))=='+good+');',None),
            ('ipv6-tcp-fallback','assert(unwrap(dns::lookup(make_client(),"public","tcp.example.test",1000))=='+good+');',None),
            ('denied','assert(error_code(lookup_raw("unknown","service.example.test",64,1000))=="CAPABILITY");assert(error_code(lookup_raw("public","evil-example.test",64,1000))=="CAPABILITY");assert(error_code(lookup_raw("exact","sub.exact.example.test",64,1000))=="CAPABILITY");',None),
            ('invalid','assert(error_code(dns::execute(make_client(),dns::request("public","bad..example.test",64,1000)))=="VALIDATION");assert(error_code(lookup_raw("public","bad..example.test",64,1000))=="VALIDATION");assert(error_code(lookup_raw("public","service.example.test",0,1000))=="VALIDATION");assert(error_code(lookup_raw("public","service.example.test",64,0))=="VALIDATION");',None),
            ('not-found','assert(error_code(lookup_raw("public","missing.example.test",64,1000))=="E_DNS");',None),
            ('answer-limit','assert(error_code(lookup_raw("public","many.example.test",2,1000))=="E_DNS_LIMIT");',None),
            ('own-timeout','assert(error_code(lookup_raw("public","held-own-@LABEL@.example.test",64,60))=="E_DNS_TIMEOUT");assert(statistics_raw()[2]==0);assert(unwrap(lookup_raw("public","service.example.test",64,1000))=='+good+');',None),
            ('progress','let total:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi,fs}{let child:task<result<list<str>>>=task_spawn(s,server fn()->result<list<str>> !{task,ffi}{return lookup_raw("public","held-progress-@LABEL@.example.test",64,5000);});while !is_ok(file_read_text("@GATE@.ready")){task_yield();}var i:i64=0;while i<1000{i=i+1;}assert(unwrap(file_write_text("@GATE@.release","go")));assert(unwrap(task_wait(child))=='+good+');return i;});assert(total==1000);print("ASYNC_PROGRESS");',None),
            ('cancel','with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,fs}{let child:task<result<list<str>>>=task_spawn(s,server fn()->result<list<str>> !{task,ffi}{return lookup_raw("public","held-cancel-@LABEL@.example.test",64,30000);});while !is_ok(file_read_text("@GATE@.ready")){task_yield();}assert(task_cancel(child));task_wait(child);});','E_CANCELLED'),
            ('parent-deadline','lookup_raw("public","held-parent-@LABEL@.example.test",64,30000);','E_TIMEOUT'),
            ('capacity','with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,fs}{let child:task<result<list<str>>>=task_spawn(s,server fn()->result<list<str>> !{task,ffi}{return lookup_raw("public","held-capacity-@LABEL@.example.test",64,500);});while !is_ok(file_read_text("@GATE@.ready")){task_yield();}assert(error_code(lookup_raw("public","service.example.test",64,1000))=="E_DNS_BUSY");assert(error_code(task_wait(child))=="E_DNS_TIMEOUT");});assert(unwrap(lookup_raw("public","service.example.test",64,1000))=='+good+');assert(statistics_raw()[3]==1);',None),
        ]
        required=[name for name,_,_ in cases];assert set(args.case)<=set(required),'unknown selected DNS case'
        report.update(required_cases=required,selected_cases=args.case or required,full_conformance=not bool(args.case));save()
        for name,body,error in cases:
            if args.case and name not in args.case:continue
            for mode in ('eval','debug','release'):
                label=name+'-'+mode;selected=ipv6_project if name.startswith('ipv6-') else capacity if name=='capacity' else project;source_prefix=ipv6_prefix if name.startswith('ipv6-') else capacity_prefix if name=='capacity' else prefix;active_peer=ipv6 if name.startswith('ipv6-') else peer
                # Gate names are the actual queried FQDN, so the server proves IO started.
                domain=('held-progress-' if name=='progress' else 'held-cancel-' if name=='cancel' else 'held-capacity-')+label+'.example.test'
                text=body.replace('@LABEL@',label).replace('@GATE@',digest(domain.encode()));(selected/'main.nex').write_text(source_for_selected_sdk(source_prefix+'server fn main()->unit !{task,ffi,fs,io}{'+text+('print(42);' if not error else '')+'}\n', sdk))
                before=active_peer.count();args_run=[compiler,'eval' if mode=='eval' else 'run','--foreign',selected/'foreign.json','--task-workers','1','--task-steps','4000000','--task-timeout-ms','2000' if name=='parent-deadline' else '10000','--json']
                if mode!='eval':args_run+=['--profile',mode]
                result=run(label,args_run,cwd=selected,env=env,expected=(1 if mode=='eval' else 70) if error else 0)
                if error:
                    if mode=='eval':assert result.get('code')==error,(label,result)
                    else:
                        diagnostic=result.get('native_diagnostics',{}).get('diagnostics',[]);assert result.get('exit_code')==70 and len(diagnostic)==1 and diagnostic[0]['status']=='mapped' and diagnostic[0]['report']['code']==error,(label,result)
                else:assert result['ok'] and result['stdout']==('ASYNC_PROGRESS\n42\n' if name=='progress' else '42\n'),(label,result)
                if name in ('denied','invalid'):assert active_peer.count()==before
                stderr=(out/(label+'.stderr')).read_text()+'\n'+result.get('stderr','');retired=[json.loads(s) for s in re.findall(r'NEX_DNS_RETIRE (\{[^\n]+\})',stderr)];assert retired and all(s['opened']==s['closed'] and s['live']==0 for s in retired),(label,stderr)
                if name in ('tcp-fallback','ipv6-tcp-fallback'):assert any(e['transport']=='tcp' for e in active_peer.events[before:])
                report['cases'].append({'name':name,'mode':mode,'passed':True,'expected_error':error,'DNS_packets':active_peer.count()-before,'retired':retired});save()
        report.update(ok=True,state='passed',case_count=len(report['cases']))
    except BaseException as error:report.update(state='failed',error=repr(error));raise
    finally:
        if peer:peer.close();report['DNS_events']=peer.events
        if ipv6:ipv6.close();report['IPv6_DNS_events']=ipv6.events
        save()
    print(json.dumps({k:report.get(k) for k in ('ok','case_count','language','actual_compiler_toolchain','seconds')}))
    if temporary and report['ok']:shutil.rmtree(out)

if __name__=='__main__':main()
