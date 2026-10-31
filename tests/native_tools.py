"""Real Clang/LLVM ar commands beyond host argv limits, without a shell."""
from host_fixture import private_permissions
import json,math,os,re,shlex,shutil,subprocess,sys
from pathlib import Path
import unittest
PROBE=str(Path(sys.argv.pop(2)).resolve())
import support as harness

class NativeTools(harness.ToolchainCase):
    def request(self,arguments,ok=True,env=None):
        file=self.root/'arguments.json';file.write_text(json.dumps(arguments,ensure_ascii=False), newline="\n")
        p=subprocess.run([PROBE,str(self.root/'unused.nex'),str(self.root/'cache'),json.dumps({'native_tool_arguments':str(file)})],
                         capture_output=True,text=True,env={**os.environ,**(env or {})},timeout=180)
        self.assertEqual(p.returncode==0,ok,p.stdout+p.stderr)
        return json.loads(p.stdout)

    def tools(self):
        compiler=Path(self.cli('doctor')['native_compiler'])
        return str(compiler),str(compiler.parent/'llvm-ar')

    def objects(self):
        compiler,archiver=self.tools()
        main=self.root/'main.cpp';main.write_text('int main(){return 42;}\n', newline="\n")
        empty=self.root/'empty.cpp';empty.write_text('static int unused;\n', newline="\n")
        for source in [main,empty]:
            p=subprocess.run([compiler,'-c',str(source),'-O2','-o',str(source.with_suffix('.o'))],capture_output=True,text=True,timeout=60)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        noisy=self.root/'space "double" \'single\' \\ % 🧠\t'
        if os.name=='nt':noisy=self.root/"space 'single' % 🧠"
        if sys.platform.startswith('linux'):noisy=Path(str(noisy)+'\nline')
        noisy.mkdir();alias=noisy/'empty.o';alias.symlink_to(empty.with_suffix('.o'))
        host_limit=32767 if os.name=='nt' else os.sysconf('SC_ARG_MAX')
        limit=host_limit if os.name=='nt' else max(host_limit,2*1024*1024)
        count=math.ceil((limit+65536)/(len(str(alias).encode())+1))
        arguments=[str(alias)]*count
        actual=len(subprocess.list2cmdline(arguments).encode('utf-16-le'))//2 if os.name=='nt' else sum(len(v.encode())+1 for v in arguments)
        self.assertGreater(actual,host_limit)
        return compiler,archiver,str(main.with_suffix('.o')),arguments

    def test_actual_clang_link_and_archive_exceed_host_argv_limit_with_literal_paths(self):
        compiler,archiver,main,objects=self.objects()
        log=self.root/'response-paths.json';wrapper=self.root/'clang forwarding wrapper'
        env={}
        if os.name=='nt':
            wrapper=wrapper.with_suffix('.exe')
            built=subprocess.run([compiler,'-std=c++20','-O2','-static','-municode','-I'+str(harness.REPO/'runtime'),str(harness.REPO/'tests/native_tool_forwarder.cpp'),'-o',str(wrapper)],capture_output=True,text=True,timeout=120)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            env.update(NEX_TEST_FORWARDER_LOG=str(log),NEX_TEST_FORWARDER_TARGET=compiler)
        else:
            wrapper.write_text('#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\nPath('+repr(str(log))+').write_text(json.dumps([v[1:] for v in sys.argv[1:] if v.startswith("@")]))\nos.execv('+repr(compiler)+',['+repr(compiler)+',*sys.argv[1:]])\n', newline="\n")
            wrapper.chmod(0o755)
        temporary=self.root/("temp % with 'quotes' 🧠" if os.name=='nt' else 'temp % with "quotes" \\ 🧠');temporary.mkdir()
        output=self.root/('linked-app.exe' if os.name=='nt' else 'linked-app')
        env.update({'TEMP':str(temporary),'TMP':str(temporary)} if os.name=='nt' else {'TMPDIR':str(temporary)})
        self.assertEqual(self.request([str(wrapper),main,*objects,'-o',str(output)],env=env)['status'],0)
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
        self.assertTrue(private_permissions(path.parent,0o700))
        self.assertTrue(private_permissions(path,0o600))
        invalid=self.request([compiler,'bad\x00argument'],ok=False)
        self.assertEqual(invalid['code'],'E_PROCESS');self.assertIn('NUL',invalid['message'])

if __name__=='__main__':unittest.main()
