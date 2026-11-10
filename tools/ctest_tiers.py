"""Inspect declared CTest tiers and their real fixture closure, without execution."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('nex_ctest_fixtures',HERE/'ctest_report.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
LABELS={'core','extended','browser','platform','sdk','scale'}


def decode(raw):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('duplicate JSON key: '+key)
            value[key]=item
        return value
    def invalid(value):raise ValueError('nonfinite JSON')
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=invalid)


def policy(raw):
    value=decode(raw)
    if not isinstance(value,dict)or value.get('schema')!='nex.ctest-tiers/1':raise ValueError('expected nex.ctest-tiers/1')
    tests=value.get('tests')
    if not isinstance(tests,dict)or not 1<=len(tests)<=10000:raise ValueError('expected a bounded explicit test catalogue')
    for name,labels in tests.items():
        if (not isinstance(name,str)or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',name)
            or not isinstance(labels,list)or not labels or any(not isinstance(x,str)or x not in LABELS for x in labels)
            or len(labels)!=len(set(labels))or len(set(labels)&{'core','extended'})!=1):
            raise ValueError('invalid labels for '+str(name))
        if 'core'in labels and labels!=['core']:raise ValueError('core must not depend on browser/platform/SDK/scale tiers')
    core=[name for name,labels in tests.items()if 'core'in labels]
    if not 1<=len(core)<=16:raise ValueError('keep the explicit core tier small (1..16 groups)')
    if set(value.get('labels',{}))!=LABELS:raise ValueError('declare every supported label')
    return value


def properties(test):
    result={}
    for row in test.get('properties',[]):
        if not isinstance(row,dict)or not isinstance(row.get('name'),str)or row['name']in result:raise ValueError('invalid/duplicate test property')
        result[row['name']]=row.get('value')
    return result


def inspect(value,registry):
    _,all_names=fixtures.fixture_closure(registry)
    tests={test['name']:test for test in registry['tests']};counts={name:[]for name in sorted(LABELS)}
    for name,test in tests.items():
        if name not in value['tests']:raise ValueError('unclassified registered test: '+name)
        observed=properties(test).get('LABELS')
        if not isinstance(observed,list)or len(observed)!=len(set(observed))or set(observed)!=set(value['tests'][name]):
            raise ValueError('actual CTest labels differ from policy: '+name)
        for label in observed:counts[label].append(name)
    if not counts['core']:raise ValueError('the configured host has no core tests')
    for name in counts['core']:
        props=properties(tests[name])
        if props.get('DISABLED'):raise ValueError('core test is disabled: '+name)
        command=tests[name].get('command')
        if not isinstance(command,list)or not command or any(not isinstance(x,str)for x in command):raise ValueError('core command must be observable')
        if any(Path(x).name.lower()in {'node','node.exe','npm','npm.cmd','npx','npx.cmd','tsc','tsc.cmd'}for x in command):
            raise ValueError('core command requires the browser toolchain: '+name)
    report={}
    for label,names in counts.items():
        names=sorted(names)
        if names:_,closure=fixtures.fixture_closure(registry,names)
        else:closure=set()
        if label=='core'and closure!=set(names):raise ValueError('core silently pulls in a preparation/cleanup fixture')
        budgets=[properties(tests[name]).get('TIMEOUT')for name in names]
        known=[x for x in budgets if type(x)in (int,float)and x>=0]
        report[label]={'selected_groups':names,'fixture_groups_added':sorted(closure-set(names)),
                       'declared_timeout_sum_seconds':sum(known),'groups_without_explicit_timeout':len(names)-len(known),
                       'measured_wall_seconds':None}
    return {'schema':'nex.ctest-tiers-report/1','ok':True,'registered_groups':len(all_names),
            'unlabelled_groups':[],'tiers':report,'full_suite_replaced_by_core':False,
            'runtime_measurements_claimed_by_inventory':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy',type=Path,default=HERE.parent/'cmake/test-tiers.json')
    parser.add_argument('--check-policy',action='store_true');parser.add_argument('--registry',type=Path)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    try:
        raw=args.policy.read_bytes();value=policy(raw)
        if args.check_policy:
            result={'schema':'nex.ctest-tiers-policy/1','ok':True,'classified_tests':len(value['tests']),
                    'core_groups':sum(labels==['core']for labels in value['tests'].values())}
        else:
            if not args.registry:raise ValueError('--registry is required for an actual configured inventory')
            content=args.registry.read_bytes();result=inspect(value,decode(content));result['registry_sha256']=hashlib.sha256(content).hexdigest()
        result['policy_sha256']=hashlib.sha256(raw).hexdigest()
        if args.output:
            with args.output.open('x',encoding='utf-8')as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
        else:print(json.dumps(result,ensure_ascii=False))
        return 0
    except (OSError,ValueError,TypeError,KeyError)as error:
        print(json.dumps({'ok':False,'error':str(error)}),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
