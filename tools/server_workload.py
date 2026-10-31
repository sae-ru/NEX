#!/usr/bin/env python3
"""Private bounded HTTP workload launcher, supervised by the NEX parent group.

The workload is data. Only compiler-provided arguments choose an executable.
The child inherits this launcher's process group; never create a nested group.
"""
import argparse
import concurrent.futures
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

MAX_INPUT=1048576
MAX_RESPONSE=1048576
MAX_OUTPUT=4194304

class WorkloadError(Exception):
    def __init__(self,code,message):self.code=code;super().__init__(message)

def fail(message,code='E_SERVER_WORKLOAD'):
    raise WorkloadError(code,message)

def keys(value,allowed,label):
    if type(value) is not dict:fail(label+' must be an object')
    if set(value)-set(allowed):fail(label+' contains an unknown field')

def integer(value,minimum,maximum,label):
    if type(value) is not int or not minimum<=value<=maximum:fail(label+' is outside its integer range')
    return value

def text(value,maximum,label,empty=True):
    if type(value) is not str:fail(label+' must be text')
    try:size=len(value.encode('utf-8'))
    except UnicodeEncodeError:fail(label+' must contain Unicode scalar text')
    if size>maximum or (not empty and not size):fail(label+' is outside its text limit')
    return value

def decode(source):
    if len(source)>MAX_INPUT:fail('workload exceeds 1 MiB')
    def pairs(rows):
        result={}
        for name,value in rows:
            if name in result:fail('duplicate workload object key')
            result[name]=value
        return result
    def number(raw):
        if len(raw)>20:fail('workload integer is outside its range')
        return int(raw)
    def invalid(_):fail('workload numbers must be finite integers')
    try:value=json.loads(source.decode('utf-8'),object_pairs_hook=pairs,parse_int=number,parse_float=invalid,parse_constant=invalid)
    except (UnicodeDecodeError,json.JSONDecodeError,RecursionError):fail('workload must be bounded strict UTF-8 JSON')
    def scalars(value,depth=0):
        if depth>32:fail('workload exceeds depth32')
        if type(value) is str:text(value,MAX_INPUT,'workload string')
        elif type(value) is dict:
            for name,item in value.items():text(name,MAX_INPUT,'workload key');scalars(item,depth+1)
        elif type(value) is list:
            for item in value:scalars(item,depth+1)
    scalars(value);return value

def inspect(source):
    value=decode(source)
    keys(value,['schema','requests','phases','warmup','authorization_env','request_timeout_ms','startup_timeout_ms'],'workload')
    if value.get('schema')!='nex.server-workload/1':fail('expected nex.server-workload/1')
    requests=value.get('requests');phases=value.get('phases')
    if type(requests) is not list or not 1<=len(requests)<=128:fail('workload requires1..128 requests')
    if type(phases) is not list or not 1<=len(phases)<=16:fail('workload requires1..16 phases')
    normalized=[]
    for row in requests:
        keys(row,['method','path','body','content_type','expect'],'request')
        method=row.get('method','GET')
        if method not in ['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS']:fail('unsupported workload HTTP method')
        path=text(row.get('path'),2048,'request path',False)
        if not path.startswith('/') or path.startswith('//') or any(ord(c)<33 or ord(c)>126 or c in '#\\' for c in path):fail('request path must be a relative visible-ASCII HTTP target')
        body=text(row.get('body',''),65536,'request body')
        content=text(row.get('content_type','application/json'),128,'request content type',False)
        if any(ord(c)<32 or ord(c)>126 for c in content):fail('request content type must be visible ASCII')
        expected=row.get('expect');keys(expected,['status','text','sha256'],'request expectation')
        status=integer(expected.get('status'),100,599,'expected HTTP status')
        expected_text=text(expected['text'],65536,'expected response text') if 'text' in expected else None
        expected_hash=expected.get('sha256')
        if 'sha256' in expected and (type(expected_hash) is not str or not re.fullmatch('[a-f0-9]{64}',expected_hash)):fail('invalid expected response SHA-256')
        if expected_text is not None and expected_hash is not None and hashlib.sha256(expected_text.encode()).hexdigest()!=expected_hash:fail('response text differs from its expected SHA-256')
        normalized.append({'method':method,'path':path,'body':body,'content_type':content,'expect':{'status':status,'text':expected_text,'sha256':expected_hash}})
    normalized_phases=[]
    for row in phases:
        keys(row,['concurrency','iterations'],'phase')
        normalized_phases.append({'concurrency':integer(row.get('concurrency'),1,64,'phase concurrency'),
            'iterations':integer(row.get('iterations'),1,4096,'phase iterations')})
    warmup=integer(value.get('warmup',0),0,128,'warmup iterations')
    total=len(requests)*(warmup+sum(row['concurrency']*row['iterations'] for row in normalized_phases))
    if total>4096:fail('workload exceeds4096 total requests')
    authorization=value.get('authorization_env')
    if 'authorization_env' in value and (type(authorization) is not str or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,127}',authorization)):fail('invalid authorization environment variable')
    result={'schema':'nex.server-workload/1','requests':normalized,'phases':normalized_phases,'warmup':warmup,
        'authorization_env':authorization,'request_timeout_ms':integer(value.get('request_timeout_ms',1000),50,5000,'request timeout'),
        'startup_timeout_ms':integer(value.get('startup_timeout_ms',5000),50,15000,'startup timeout')}
    summary={'schema':'nex.server-workload-plan/1','sha256':hashlib.sha256(source).hexdigest(),'total_requests':total,
        'request_definitions':len(requests),'phases':normalized_phases,'warmup':warmup,'authorization_env':authorization,
        'request_timeout_ms':result['request_timeout_ms'],'startup_timeout_ms':result['startup_timeout_ms'],
        'loopback_only':True,'connection_policy':'one HTTP/1.1 connection per request; no redirect or retry',
        'authorization_values_captured':False,'request_payloads_captured':False}
    return result,summary

def median(values):
    values=sorted(values);middle=len(values)//2
    return values[middle] if len(values)%2 else (values[middle-1]+values[middle])/2

def percentile(values,proportion):
    return sorted(values)[max(0,math.ceil(len(values)*proportion)-1)]

def execute(specification,plan,command):
    if not command or not Path(command[0]).is_absolute():fail('compiler must provide an absolute server executable')
    forbidden=['--host','--port','--cert','--key']
    if any(arg in forbidden or any(arg.startswith(name+'=') for name in forbidden) for arg in command[1:]):fail('workload owns the loopback HTTP listener; host,port and TLS options are unsupported')
    token=None
    if specification['authorization_env']:
        token=os.environ.get(specification['authorization_env'],'')
        if not re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,8192}',token):fail('authorization environment value is unavailable or invalid','E_SERVER_WORKLOAD_AUTH')
    result={'schema':'nex.server-workload-result/1','ok':False,'definition_sha256':plan['sha256'],
        'planned_requests':plan['total_requests'],'completed_requests':0,'warmup_completed':0,'phases':[],
        'connection_policy':plan['connection_policy'],'authorization_values_captured':False,'request_payloads_captured':False,
        'loopback_only':True,'native_child_inherits_supervised_group':True}
    process=None;cancelled=threading.Event();output_limit=threading.Event();ready=queue.Queue();pumps=[]
    lock=threading.Lock();output_bytes=[0];counts={'completed':0}
    def pump(stream,destination,startup=False):
        initial=bytearray();announced=False
        while True:
            chunk=os.read(stream.fileno(),4096)
            if not chunk:
                if startup and not announced:ready.put(None)
                break
            if startup and not announced:
                initial.extend(chunk)
                if b'\n' in initial:
                    announced=True;ready.put(bytes(initial[:initial.index(b'\n')+1]))
                elif len(initial)>8192:
                    announced=True;ready.put(None)
            with lock:
                remaining=max(0,MAX_OUTPUT-output_bytes[0]);output_bytes[0]+=len(chunk)
                if output_bytes[0]>MAX_OUTPUT:output_limit.set();cancelled.set()
            if remaining:
                data=memoryview(chunk[:remaining])
                while data:
                    size=os.write(destination,data);data=data[size:]
    try:
        process=subprocess.Popen([*command,'--host','127.0.0.1','--port','0'],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        for stream,destination,startup in [(process.stdout,1,True),(process.stderr,2,False)]:
            thread=threading.Thread(target=pump,args=(stream,destination,startup),daemon=True);thread.start();pumps.append(thread)
        try:line=ready.get(timeout=specification['startup_timeout_ms']/1000)
        except queue.Empty:fail('server did not announce its listener before the startup deadline','E_SERVER_WORKLOAD_START')
        match=re.fullmatch(rb'NEX server http://127\.0\.0\.1:([0-9]+)\r?\n',line or b'')
        if not match:fail('server did not announce the expected loopback HTTP listener','E_SERVER_WORKLOAD_START')
        port=int(match.group(1))
        if not 1<=port<=65535:fail('invalid loopback listener port','E_SERVER_WORKLOAD_START')
        def request(row):
            if cancelled.is_set():fail('workload was cancelled','E_SERVER_WORKLOAD_CANCELLED')
            connection=http.client.HTTPConnection('127.0.0.1',port,timeout=specification['request_timeout_ms']/1000)
            headers={'Connection':'close','Content-Type':row['content_type']}
            if token:headers['Authorization']='Bearer '+token
            begin=time.perf_counter_ns()
            try:
                connection.request(row['method'],row['path'],body=row['body'].encode(),headers=headers)
                response=connection.getresponse();body=response.read(MAX_RESPONSE+1);elapsed=time.perf_counter_ns()-begin
                if len(body)>MAX_RESPONSE:fail('response exceeds1MiB','E_SERVER_WORKLOAD_RESPONSE')
                expected=row['expect']
                if response.status!=expected['status']:fail('unexpected HTTP response status','E_SERVER_WORKLOAD_RESPONSE')
                if expected['text'] is not None and body!=expected['text'].encode():fail('response differs from expected UTF-8 bytes','E_SERVER_WORKLOAD_RESPONSE')
                if expected['sha256'] is not None and hashlib.sha256(body).hexdigest()!=expected['sha256']:fail('response differs from expected SHA-256','E_SERVER_WORKLOAD_RESPONSE')
                with lock:counts['completed']+=1
                return elapsed
            except (OSError,http.client.HTTPException):fail('HTTP request did not complete; mutations are never retried','E_SERVER_WORKLOAD_TRANSPORT')
            finally:connection.close()
        for _ in range(specification['warmup']):
            for row in specification['requests']:request(row);result['warmup_completed']+=1
        for phase in specification['phases']:
            barrier=threading.Barrier(phase['concurrency'])
            def worker(_):
                barrier.wait(timeout=specification['startup_timeout_ms']/1000);samples=[]
                for _ in range(phase['iterations']):
                    for row in specification['requests']:samples.append(request(row))
                return samples
            begin=time.perf_counter_ns()
            with concurrent.futures.ThreadPoolExecutor(max_workers=phase['concurrency']) as executor:
                futures=[executor.submit(worker,index) for index in range(phase['concurrency'])]
                samples=[];errors=[]
                for future in futures:
                    try:samples.extend(future.result())
                    except Exception as error:errors.append(error);cancelled.set()
                if errors:raise errors[0]
            elapsed=time.perf_counter_ns()-begin
            result['phases'].append({'concurrency':phase['concurrency'],'iterations':phase['iterations'],'requests':len(samples),
                'duration_ns':elapsed,'requests_per_second':len(samples)*1e9/elapsed,'latency_ns':{'min':min(samples),
                'p50':median(samples),'p95':percentile(samples,.95),'p99':percentile(samples,.99),'max':max(samples)},'samples_ns':samples})
        if output_limit.is_set():fail('server output exceeded4MiB','E_SERVER_WORKLOAD_OUTPUT')
        result['ok']=True
    except WorkloadError as error:result.update(error={'code':error.code,'message':str(error)})
    except Exception:result.update(error={'code':'E_SERVER_WORKLOAD_INTERNAL','message':'server workload observation failed'})
    finally:
        cancelled.set()
        if process is not None:
            if process.poll() is None:
                if os.name=='nt':
                    def stop_server(process):
                        import ctypes as C
                        from ctypes import wintypes as W
                        """Ask this user's NEX server to drain and return through its normal exit."""
                        kernel=C.WinDLL('kernel32',use_last_error=True)
                        kernel.OpenEventW.argtypes=[W.DWORD,W.BOOL,W.LPCWSTR];kernel.OpenEventW.restype=W.HANDLE
                        kernel.SetEvent.argtypes=[W.HANDLE];kernel.SetEvent.restype=W.BOOL
                        kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
                        event=kernel.OpenEventW(2,False,'Local\\NEX.Server.Stop.'+str(process.pid))
                        if not event:
                            if process.poll() is not None:return
                            raise C.WinError(C.get_last_error())
                        try:
                            if not kernel.SetEvent(event):raise C.WinError(C.get_last_error())
                        finally:kernel.CloseHandle(event)
                    stop_server(process)
                else:process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait();result['ok']=False;result['forced_stop']=True
            result['server_exit_code']=process.returncode
            if process.returncode!=0:result['ok']=False
            if not result['ok'] and 'error' not in result:
                result['error']={'code':'E_SERVER_WORKLOAD_STOP','message':'server did not stop normally after the workload'}
            for thread in pumps:thread.join(timeout=1)
            for stream in [process.stdout,process.stderr]:stream.close()
        result['completed_requests']=counts['completed']
        result['all_expectations_met']=result['completed_requests']==result['planned_requests'] and result['ok']
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workload',type=Path,required=True);parser.add_argument('--expected-hash')
    parser.add_argument('--result',type=Path);parser.add_argument('--check',action='store_true')
    parser.add_argument('command',nargs=argparse.REMAINDER);arguments=parser.parse_args()
    try:
        with arguments.workload.open('rb') as source:raw=source.read(MAX_INPUT+1)
        spec,plan=inspect(raw)
        if arguments.expected_hash and plan['sha256']!=arguments.expected_hash:fail('frozen workload differs from its expected hash','E_SERVER_WORKLOAD_INPUT_CHANGED')
        if arguments.check:
            if arguments.result or arguments.command:fail('readonly check does not execute a command or write results')
            print(json.dumps(plan));return 0
        if arguments.result is None or arguments.result.exists():fail('launcher requires a new result file')
        command=arguments.command[1:] if arguments.command[:1]==['--'] else arguments.command
        result=execute(spec,plan,command)
        with arguments.result.open('x',encoding='utf-8') as output:json.dump(result,output);output.write('\n')
        return 0 if result['ok'] else 1
    except WorkloadError as error:
        print(json.dumps({'ok':False,'code':error.code,'message':str(error)}),file=sys.stderr);return 1
    except OSError:
        print(json.dumps({'ok':False,'code':'E_SERVER_WORKLOAD_FILE','message':'cannot read workload or write its result'}),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
