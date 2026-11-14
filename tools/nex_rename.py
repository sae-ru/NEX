#!/usr/bin/env python3
"""Rename a checked project symbol in source and preserve its graph-local ID."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

def invoke(compiler,root,args,ok=True):
    result=subprocess.run([str(compiler),*args],cwd=root,capture_output=True,text=True,timeout=300)
    value=json.loads(result.stdout) if result.stdout.strip() else None
    if ok and result.returncode:
        raise RuntimeError('nex failed: '+repr(args)+'\n'+result.stdout+result.stderr)
    return result,value

def qualified(symbol):
    if '::' not in symbol:raise ValueError('rename requires a fully qualified symbol')
    module,name=symbol.rsplit('::',1)
    if not module or not name:raise ValueError('invalid qualified symbol')
    return module,name

def source_plan(compiler,root,source,target,head):
    from_module,old_name=qualified(source)
    to_module,new_name=qualified(target)
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',new_name):
        raise ValueError('new name must be a NEX identifier')
    _,analysis=invoke(compiler,root,['analyze','--references','--json'])
    if analysis['revision']!=head:raise RuntimeError('source changed while planning rename')
    selected=[symbol for symbol in analysis['symbols'] if symbol['symbol']==source]
    if len(selected)!=1:raise ValueError('rename requires one checked source declaration: '+source)
    symbol=selected[0]
    definition={'file':symbol['file'],'range':symbol['selection']}
    files={file['key']:file for file in analysis['files']}
    edits={}
    for occurrence in analysis['occurrences']:
        if occurrence['definition']==definition:
            span=occurrence['range']
            edits.setdefault(occurrence['file'],set()).add((span['begin'],span['end'],new_name.encode('utf-8')))
    if from_module!=to_module:
        data=files[symbol['file']]['text'].encode('utf-8')
        declaration=re.search(rb'(?m)^\s*module\s+('+re.escape(from_module.encode('utf-8'))+rb')\s*;',data)
        if not declaration:raise ValueError('no module declaration for '+from_module)
        edits.setdefault(symbol['file'],set()).add((*declaration.span(1),to_module.encode('utf-8')))
    plan=[]
    for key,ranges in sorted(edits.items()):
        file=files[key];path=Path(file['path']).resolve()
        if root not in path.parents:raise ValueError('rename would change a source outside the project: '+str(path))
        original=file['text'].encode('utf-8')
        if path.read_bytes()!=original:raise RuntimeError('source changed while planning rename: '+str(path))
        updated=original;end=len(original)
        for first,last,replacement in sorted(ranges,reverse=True):
            if not 0<=first<last<=end:raise ValueError('overlapping or invalid compiler reference ranges')
            updated=updated[:first]+replacement+updated[last:];end=first
        plan.append((path,original.decode('utf-8'),updated.decode('utf-8')))
    if not plan:raise ValueError('no checked source references for '+source)
    return plan

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',required=True,type=Path)
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--from',dest='source')
    parser.add_argument('--import-alias')
    parser.add_argument('--to',required=True)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    root=args.project.resolve();compiler=args.compiler.resolve()
    if bool(args.source)==bool(args.import_alias):raise SystemExit('select exactly one of --from or --import-alias')
    if args.import_alias and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',args.to):raise SystemExit('new name must be a NEX identifier')
    if args.import_alias:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',args.import_alias):raise SystemExit('import alias must be a NEX identifier')
        check=invoke(compiler,root,['check','--json'])[1];head=check['revision']
        files=[p for p in root.rglob('*.nex') if '.nex' not in p.relative_to(root).parts];plan=[]
        for path in sorted(files):
            text=path.read_text(encoding='utf-8');lines=text.splitlines(keepends=True);begin=0;spans=[]
            for line in lines:
                if re.search(r'\bimport\b[^;]*\bas\s+'+re.escape(args.import_alias)+r'\s*;',line):
                    match=re.search(r'\bas\s+('+re.escape(args.import_alias)+r')\s*;',line)
                    spans.append((begin+len(line[:match.start(1)].encode()),begin+len(line[:match.end(1)].encode())))
                else:
                    for match in re.finditer(r'\b'+re.escape(args.import_alias)+r'\b(\s*::)',line):spans.append((begin+len(line[:match.start()].encode()),begin+len(line[:match.start(1)].encode())))
                begin+=len(line.encode())
            if not spans:continue
            pieces=[];last=0
            for first,lastspan in spans:pieces.append(text.encode()[last:first].decode());pieces.append(args.to);last=lastspan
            pieces.append(text.encode()[last:].decode());plan.append((path,text,''.join(pieces)))
        if not plan:raise SystemExit('no import alias occurrences for '+args.import_alias)
        if args.dry_run:
            print(json.dumps({'schema':'nex.rename/1','ok':True,'dry_run':True,'import_alias':args.import_alias,'to':args.to,'head':head,'files':[str(p.relative_to(root)) for p,_,_ in plan]},indent=2));return 0
        backups={}
        try:
            for path,original,updated in plan:
                backups[path]=original
                temporary=path.with_name(path.name+'.rename-tmp')
                with temporary.open('w',encoding='utf-8',newline='') as output:output.write(updated)
                os.replace(temporary,path)
            _,after=invoke(compiler,root,['check','--json'])
        except Exception:
            for path,original in backups.items():
                with path.open('w',encoding='utf-8',newline='') as output:output.write(original)
            raise
        print(json.dumps({'schema':'nex.rename/1','ok':True,'dry_run':False,'import_alias':args.import_alias,'to':args.to,'head':head,'revision':after['revision'],'files':[str(p.relative_to(root)) for p,_,_ in plan]},indent=2));return 0
    qualified(args.source)
    qualified(args.to)
    check=invoke(compiler,root,['check','--json'])[1];head=check['revision']
    plan=source_plan(compiler,root,args.source,args.to,head)
    if args.dry_run:
        print(json.dumps({'schema':'nex.rename/1','ok':True,'dry_run':True,'from':args.source,'to':args.to,'head':head,
            'files':[str(path.relative_to(root)) for path,_,_ in plan]},indent=2));return 0
    backups={}
    try:
        for path,original,updated in plan:
            backups[path]=original
            temporary=path.with_name(path.name+'.rename-tmp')
            with temporary.open('w',encoding='utf-8',newline='') as output:output.write(updated)
            os.replace(temporary,path)
        _,renamed=invoke(compiler,root,['identities','--kind','rename','--symbol',args.source,'--to',args.to,'--expected-revision',head,'--json'])
        _,after=invoke(compiler,root,['check','--json'])
    except Exception:
        for path,original in backups.items():
            with path.open('w',encoding='utf-8',newline='') as output:output.write(original)
        raise
    print(json.dumps({'schema':'nex.rename/1','ok':True,'dry_run':False,'from':args.source,'to':args.to,
        'head':head,'revision':after['revision'],'moved':renamed['moved'],
        'files':[str(path.relative_to(root)) for path,_,_ in plan]},indent=2));return 0

if __name__=='__main__':sys.exit(main())
