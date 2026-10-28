#!/usr/bin/env python3
"""Emit small owned ONNX test graphs without installing Python ML packages.

Field numbers follow the official v1.17.0 schema:
https://github.com/onnx/onnx/blob/v1.17.0/onnx/onnx.proto3
This is a fixture writer, not an ONNX parser or project converter.
"""
import argparse,hashlib,json,struct
from pathlib import Path

def varint(n):
 assert 0<=n<(1<<63);out=bytearray()
 while n>=128:out.append((n&127)|128);n>>=7
 out.append(n);return bytes(out)
def integer(field,value):return varint(field<<3)+varint(value)
def data(field,value):
 if isinstance(value,str):value=value.encode('utf-8')
 return varint((field<<3)|2)+varint(len(value))+value
def port(name,shape):
 dims=b''.join(data(1,integer(1,d)) for d in shape)
 return data(1,name)+data(2,data(1,integer(1,1)+data(2,dims)))
def tensor(name,shape,values):
 return b''.join(integer(1,d) for d in shape)+integer(2,1)+data(8,name)+data(9,struct.pack('<'+'f'*len(values),*values))
def node(name,op,inputs,outputs):return b''.join(data(1,s) for s in inputs)+b''.join(data(2,s) for s in outputs)+data(3,name)+data(4,op)
def model(name,nodes,inputs,outputs,initializers=()):
 graph=b''.join(data(1,n) for n in nodes)+data(2,name)+b''.join(data(5,t) for t in initializers)+b''.join(data(11,port(n,s)) for n,s in inputs)+b''.join(data(12,port(n,s)) for n,s in outputs)
 return integer(1,8)+data(2,'NEX model acceptance')+data(7,graph)+data(8,integer(2,13))
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.absolute();out.mkdir(exist_ok=False);rows=[]
 def write(name,raw,inputs,outputs,values,expected):
  root=out/name;root.mkdir();(root/'model.onnx').write_bytes(raw);spec={'schema':'nex.model-artifact/1','id':name,'sha256':hashlib.sha256(raw).hexdigest(),'inputs':[{'name':n,'dtype':'f32','shape':s} for n,s in inputs],'outputs':[{'name':n,'dtype':'f32','shape':s} for n,s in outputs]};(root/'spec.json').write_text(json.dumps(spec,indent=2)+'\n');(root/'example.json').write_text(json.dumps({'inputs':values,'expected':expected},indent=2)+'\n');rows.append({'id':name,'sha256':spec['sha256'],'bytes':len(raw),'inputs':len(inputs),'outputs':len(outputs)})
 shape=[3,2];inputs=[('X',shape)];outputs=[('Y',shape)];weights=[1,2,3,4,5,6];x=[-2,-1,0,1,2,3]
 write('mul3x2',model('mul3x2',[node('product','Mul',['X','W'],['Y'])],inputs,outputs,[tensor('W',shape,weights)]),inputs,outputs,[x],[[a*b for a,b in zip(x,weights)]])
 inputs=[('A',[32,32]),('B',[32,32])];outputs=[('Y',[32,32])];x=[(i*3)%7-3 for i in range(1024)];y=[(i*5+2)%7-3 for i in range(1024)];expected=[sum(x[i*32+k]*y[k*32+j] for k in range(32)) for i in range(32) for j in range(32)]
 write('matmul32',model('matmul32',[node('matrix','MatMul',['A','B'],['Y'])],inputs,outputs),inputs,outputs,[x,y],[expected])
 inputs=[('A',[2,3]),('B',[2,3])];outputs=[('sum',[2,3]),('difference',[2,3])];x=[1,2,3,4,5,6];y=[-2,-1,0,1,2,3]
 write('two-outputs',model('two-outputs',[node('add','Add',['A','B'],['sum']),node('subtract','Sub',['A','B'],['difference'])],inputs,outputs),inputs,outputs,[x,y],[[a+b for a,b in zip(x,y)],[a-b for a,b in zip(x,y)]])
 result={'schema':'nex.owned-onnx-fixtures/1','ok':True,'models':rows,'validated_by_runtime':False,'hardware_executed':False,'schema_reference':'https://github.com/onnx/onnx/blob/v1.17.0/onnx/onnx.proto3'};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
