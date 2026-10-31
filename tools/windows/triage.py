"""Classify actual CTest diagnostics without changing or skipping tests."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('junit',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    rows=[]
    patterns={
        'posix_fixture':r'/dev/null|os.*has no attribute .uname|mkdtemp failed|No such file.*[/]tmp|No such file.*[/]bin[/]',
        'sqlite_fixture_cleanup':r'WinError 32.*graph.db|PermissionError.*graph.db',
        'profile_gate':r'profiling remain pending|Windows profile',
        'foreign_gate':r'Windows source foreign|Windows task foreign',
        'shared_gate':r'shared.*require macOS or Linux|shared.*Mach-O|ELF',
        'server_gate':r'HTTP servers and profiling|HTTP.*requires.*POSIX',
        'missing_executable':r'Unable to find executable|WinError 2|FileNotFoundError',
        'process':r'E_TASK_PROCESS|E_PROCESS|E_TASK_TIMEOUT',
        'path_or_arguments':r'E_TOOLCHAIN|E_NATIVE|E_BUILD|E_IMPORT|E_PATH|E_ARGUMENT',
    }
    for case in ET.parse(args.junit).getroot().findall('.//testcase'):
        if case.attrib.get('status')=='run':continue
        output=case.findtext('system-out','')
        clues=list(dict.fromkeys(line.strip() for line in output.splitlines()
            if re.search(r'AssertionError:|[A-Za-z]+Error:|"message":|error:|mkdtemp failed',line)))
        rows.append({'name':case.attrib['name'],'status':case.attrib.get('status'),
                     'categories':[key for key,pattern in patterns.items() if re.search(pattern,output,re.I)],
                     'clues':clues[:20]})
    args.output.write_bytes((json.dumps(rows,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'groups':len(rows),'categories':dict(Counter(c for row in rows for c in row['categories']))}))
    for row in rows:
        if row['name'] in ('native_tool_arguments','native_arithmetic','graph_snapshots','storage','profiling','source_ffi','graph_queries','frontend_diagnostics','modules','enums','function_values','tasks','parallel_mapping'):
            print(row['name']+': '+str(row['clues'])[:900])


if __name__=='__main__':main()
