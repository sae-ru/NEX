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

def identifier_spans(text,needle):
    spans=[];i=0;n=len(text)
    def ident(c):return c.isalpha() or c=='_' or (c.isdigit() and False)
    while i<n:
        c=text[i]
        if c=='/' and i+1<n and text[i+1]=='/':
            j=text.find('\n',i+2);i=n if j<0 else j+1;continue
        if c=='/' and i+1<n and text[i+1]=='*':
            j=text.find('*/',i+2)
            if j<0:raise ValueError('unterminated comment');i=j+2;continue
        if c=='"':
            j=i+1
            while j<n:
                if text[j]=='\\':j+=2;continue
                if text[j]=='"':break
                j+=1
            if j>=n:raise ValueError('unterminated string')
            i=j+1;continue
        if c.isalpha() or c=='_':
            j=i+1
            while j<n and (text[j].isalnum() or text[j]=='_'):j+=1
            if text[i:j]==needle:spans.append((i,j))
            i=j;continue
        i+=1
    return spans

def qualified(symbol):
    if '::' not in symbol:raise ValueError('rename requires a fully qualified symbol')
    module,name=symbol.rsplit('::',1)
    if not module or not name:raise ValueError('invalid qualified symbol')
    return module,name

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
                backups[path]=original;temporary=path.with_name(path.name+'.rename-tmp');temporary.write_text(updated,encoding='utf-8',newline='');os.replace(temporary,path)
            _,after=invoke(compiler,root,['check','--json'])
        except Exception:
            for path,original in backups.items():path.write_text(original,encoding='utf-8',newline='')
            raise
        print(json.dumps({'schema':'nex.rename/1','ok':True,'dry_run':False,'import_alias':args.import_alias,'to':args.to,'head':head,'revision':after['revision'],'files':[str(p.relative_to(root)) for p,_,_ in plan]},indent=2));return 0
    from_module,old_name=qualified(args.source)
    if '::' not in args.to:raise SystemExit('source rename target must be fully qualified')
    to_module,new_name=args.to.rsplit('::',1)
    if from_module!=to_module:raise SystemExit('nex_rename source mode currently requires the same module')
    check=invoke(compiler,root,['check','--json'])[1];head=check['revision']
    files=[p for p in root.rglob('*.nex') if '.nex' not in p.relative_to(root).parts]
    plan=[]
    for path in sorted(files):
        text=path.read_text(encoding='utf-8');spans=identifier_spans(text,old_name)
        if not spans:continue
        pieces=[];last=0
        for first,lastspan in spans:pieces.append(text[last:first]);pieces.append(new_name);last=lastspan
        pieces.append(text[last:]);plan.append((path,text,''.join(pieces)))
    if not plan:raise SystemExit('no source identifier occurrences for '+old_name)
    if args.dry_run:
        print(json.dumps({'schema':'nex.rename/1','ok':True,'dry_run':True,'from':args.source,'to':args.to,'head':head,
            'files':[str(path.relative_to(root)) for path,_,_ in plan]},indent=2));return 0
    backups={}
    try:
        for path,original,updated in plan:
            backups[path]=original
            temporary=path.with_name(path.name+'.rename-tmp')
            temporary.write_text(updated,encoding='utf-8',newline='')
            os.replace(temporary,path)
        _,renamed=invoke(compiler,root,['identities','--kind','rename','--symbol',args.source,'--to',args.to,'--expected-revision',head,'--json'])
        _,after=invoke(compiler,root,['check','--json'])
    except Exception:
        for path,original in backups.items():path.write_text(original,encoding='utf-8',newline='')
        raise
    print(json.dumps({'schema':'nex.rename/1','ok':True,'dry_run':False,'from':args.source,'to':args.to,
        'head':head,'revision':after['revision'],'moved':renamed['moved'],
        'files':[str(path.relative_to(root)) for path,_,_ in plan]},indent=2));return 0

if __name__=='__main__':sys.exit(main())
