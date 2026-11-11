#!/usr/bin/env python3
"""Generate a deterministic pure agreement corpus with seed and reproducer."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

OPS=('+','-','*')


def expression(rng,depth=0):
    if depth>=3 or (depth>0 and rng.random()<0.35):
        value=rng.randint(0,20)
        return str(value),value
    left,left_value=expression(rng,depth+1)
    right,right_value=expression(rng,depth+1)
    op=rng.choice(OPS)
    if op=='+':value=left_value+right_value
    elif op=='-':value=left_value-right_value
    else:value=left_value*right_value
    return f"({left} {op} {right})",value


def program(rng,name):
    module=name.replace("-","_")
    lines=[f"module agreement_generated_{module};","fn main() -> unit !{io} {"]
    expected=[]
    for _ in range(3):
        text,value=expression(rng)
        lines.append(f"  print({text});")
        expected.append(str(value))
    lines.append("}")
    return '\n'.join(lines)+'\n','\n'.join(expected)+'\n'


def sha(text):return hashlib.sha256(text.encode()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--count',type=int,default=3)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    if not 1<=args.count<=64:parser.error('--count must be 1..64')
    if args.directory.exists() and any(args.directory.iterdir()):parser.error('output directory must be absent or empty')
    args.directory.mkdir(parents=True,exist_ok=True)
    (args.directory/'cases').mkdir(exist_ok=True)
    rng=random.Random(args.seed)
    manifest={'schema':'nex.agreement/1','language':'0.28',
        'generator':{'tool':'tools/agreement_generate.py','seed':args.seed,'count':args.count},
        'cases':[]}
    for index in range(args.count):
        name=f'gen-{index:03d}'
        source,expected=program(rng,name)
        (args.directory/'cases'/(name+'.nex')).write_text(source)
        manifest['cases'].append({'name':name,'kind':'valid','source':'cases/'+name+'.nex',
            'entry':'main','expected_stdout':expected,'program_sha256':sha(source)})
    text=json.dumps(manifest,indent=2)+'\n'
    (args.directory/'cases.json').write_text(text)
    summary={'schema':'nex.agreement-generator/1','ok':True,'seed':args.seed,'count':args.count,
        'directory':str(args.directory),'manifest_sha256':sha(text),
        'reproduce':f'python3 tools/agreement_generate.py --seed {args.seed} --count {args.count} --directory {args.directory}'}
    if args.json:print(json.dumps(summary))
    else:print(json.dumps(summary,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
