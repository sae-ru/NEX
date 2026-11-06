"""Real ELF identities must not depend on a native compiler's default flags."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from host_fixture import run_native


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--identity-probe',type=Path,required=True)
    args=parser.parse_args()
    assert sys.platform.startswith('linux')
    compiler=args.compiler.absolute();probe=args.identity_probe.resolve(strict=True)
    root=Path(tempfile.mkdtemp(prefix='nex-ELF-fixture-identity-'))
    source=root/'main.cpp';source.write_text('extern "C" int answer(){return 42;} int main(){return answer();}\n')
    driver=root/'no-default-identity'
    driver.write_text('#!'+sys.executable+'\nimport os,sys\nargs=sys.argv[1:]\n'
                      'flags=["-Wl,--build-id=none"] if "-o" in args and not any(x in args for x in ("-c","-E","-S")) else []\n'
                      'os.execv('+repr(str(compiler))+',['+repr(str(compiler))+',*flags,*args])\n')
    driver.chmod(0o755)
    cases=[]
    try:
        for name,options,request,expected in [
                ('default-disabled',[],False,None),
                ('requested-executable',[],True,'generated'),
                ('requested-shared',['-shared','-fPIC'],True,'generated'),
                ('explicit-disabled',['-Wl,--build-id=none'],True,None),
                ('explicit-identity',['-Xlinker','--build-id=0x0011223344556677889900112233445566778899'],True,
                 '0011223344556677889900112233445566778899'),
                ('object-only',['-c'],True,None)]:
            output=root/name
            built=run_native([driver,'-std=c++20',*options,source,'-o',output],image_identity=request,
                             capture_output=True,text=True,timeout=120)
            (root/(name+'.stdout')).write_text(built.stdout);(root/(name+'.stderr')).write_text(built.stderr)
            assert built.returncode==0,(name,built.stdout,built.stderr)
            if name=='object-only':
                assert not any('--build-id'in value for value in built.args)
            else:
                identity=subprocess.run([str(probe),'identity',str(output)],capture_output=True,text=True,timeout=30)
                value=identity.stdout.strip().replace('-','').lower()
                if expected:
                    assert identity.returncode==0 and re.fullmatch('[0-9a-f]{40}',value),(name,identity.stdout,identity.stderr)
                    if expected!='generated':assert value==expected,(name,value)
                else:
                    assert identity.returncode!=0 and 'no UUID/build ID'in identity.stderr,(name,identity.stdout,identity.stderr)
                if '-shared'not in options:assert subprocess.run([str(output)],timeout=30).returncode==42
            cases.append({'name':name,'passed':True,'actual_compile_arguments':built.args})
        print(json.dumps({'ok':True,'cases':cases,'intentional_missing_id_controls_retained':True}))
    except BaseException:
        print('Preserved ELF identity fixture: '+str(root),file=sys.stderr)
        raise
    else:
        shutil.rmtree(root)


if __name__=='__main__':main()
