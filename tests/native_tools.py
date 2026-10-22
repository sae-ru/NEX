"""Real Clang/LLVM ar commands beyond host argv limits, without a shell."""
import json,math,os,re,shlex,shutil,subprocess,sys
from pathlib import Path
import unittest
PROBE=str(Path(sys.argv.pop(2)).resolve())
import support as harness

class NativeTools(harness.ToolchainCase):
    def request(self,arguments,ok=True,env=None):
        file=self.root/'arguments.json';file.write_text(json.dumps(arguments,ensure_ascii=False))
        p=subprocess.run([PROBE,str(self.root/'unused.nex'),str(self.root/'cache'),json.dumps({'native_tool_arguments':str(file)})],
                         capture_output=True,text=True,env={**os.environ,**(env or {})},timeout=180)
        self.assertEqual(p.returncode==0,ok,p.stdout+p.stderr)
        return json.loads(p.stdout)

    def tools(self):
        compiler=Path(self.cli('doctor')['native_compiler'])
        return str(compiler),str(compiler.parent/'llvm-ar')

    def objects(self):
        compiler,archiver=self.tools()
        main=self.root/'main.cpp';main.write_text('int main(){return 42;}\n')
        empty=self.root/'empty.cpp';empty.write_text('static int unused;\n')
        for source in [main,empty]:
            p=subprocess.run([compiler,'-c',str(source),'-O2','-o',str(source.with_suffix('.o'))],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        noisy=self.root/'space "double" \'single\' \\ % 🧠\t'
        if sys.platform.startswith('linux'):noisy=Path(str(noisy)+'\nline')
        noisy.mkdir();alias=noisy/'empty.o';alias.symlink_to(empty.with_suffix('.o'))
        limit=max(os.sysconf('SC_ARG_MAX'),2*1024*1024)
        count=math.ceil((limit+65536)/(len(str(alias).encode())+1))
        arguments=[str(alias)]*count
        self.assertGreater(sum(len(v.encode())+1 for v in arguments),os.sysconf('SC_ARG_MAX'))
        return compiler,archiver,str(main.with_suffix('.o')),arguments

    def test_actual_clang_link_and_archive_exceed_host_argv_limit_with_literal_paths(self):
        compiler,archiver,main,objects=self.objects()
        log=self.root/'response-paths.json';wrapper=self.root/'clang forwarding wrapper'
        wrapper.write_text('#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\nPath('+repr(str(log))+').write_text(json.dumps([v[1:] for v in sys.argv[1:] if v.startswith("@")]))\nos.execv('+repr(compiler)+',['+repr(compiler)+',*sys.argv[1:]])\n')
        wrapper.chmod(0o755)
        temporary=self.root/'temp % with "quotes" \\ 🧠';temporary.mkdir()
        output=self.root/'linked-app'
        self.assertEqual(self.request([str(wrapper),main,*objects,'-o',str(output)],env={'TMPDIR':str(temporary)})['status'],0)
        response,=json.loads(log.read_text());self.assertFalse(Path(response).parent.exists())
        observed=subprocess.run([str(output)],capture_output=True,text=True,timeout=20)
        self.assertEqual(observed.returncode,42,observed.stderr)
        archive=self.root/'many-objects.a'
        self.assertEqual(self.request([archiver,'rcs',str(archive),*objects])['status'],0)
        table=subprocess.run([archiver,'t',str(archive)],capture_output=True,text=True,timeout=60)
        self.assertEqual(table.returncode,0,table.stderr)
        self.assertEqual(table.stdout.splitlines(),['empty.o']*len(objects))

    def test_failed_tool_retains_exact_arguments_and_nul_rejected_before_execution(self):
        compiler,_=self.tools()
        value='literal "double" \'single\' \\ % 🧠\t\n'
        arguments=[compiler,'--nex-intentionally-invalid-build-option',*(['-DNEX_LITERAL='+value]*4096)]
        failed=self.request(arguments,ok=False);self.assertEqual(failed['code'],'E_LINK')
        match=re.search(r'response file retained at ([^\n]+)',failed['message']);self.assertIsNotNone(match,failed)
        path=Path(match.group(1));self.addCleanup(shutil.rmtree,path.parent)
        self.assertEqual(shlex.split(path.read_text()),arguments[1:])
        self.assertEqual(path.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        invalid=self.request([compiler,'bad\x00argument'],ok=False)
        self.assertEqual(invalid['code'],'E_PROCESS');self.assertIn('NUL',invalid['message'])

if __name__=='__main__':unittest.main()
