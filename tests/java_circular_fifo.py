"""Manual Apache queue port: original Java observations and backend agreement."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import support as h
import standard_library as helpers
from java_circular_fifo_cases import cases, protocol, source

FIXTURE = h.REPO/'tests/fixtures/java-circular-fifo'
EXAMPLE = h.REPO/'examples/java-circular-fifo'
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()

class JavaCircularFIFO(h.ToolchainCase):
    run_child = helpers.StandardLibrary.run_child
    strict_ts = helpers.StandardLibrary.strict_ts

    def project(self, folder, body, language='0.30'):
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'})+'\n')
        (folder/'main.nex').write_text(body,encoding='utf-8')
        shutil.copyfile(EXAMPLE/'circular_fifo.nex',folder/'circular_fifo.nex')
        if language=='0.30':
            shutil.copyfile(EXAMPLE/'nex.lock.json',folder/'nex.lock.json')

    def test_unmodified_upstream_frozen_and_optional_live_Java(self):
        captured=json.loads((FIXTURE/'upstream.json').read_text())
        self.assertEqual(captured['version'],'4.6.0')
        self.assertEqual(captured['license'],'Apache-2.0')
        for item in captured['selected_files']:
            path=FIXTURE/('upstream/'+item['path'] if item['path'].endswith('.java') else item['path'].split('/')[-1])
            self.assertEqual(sha(path),item['sha256'])
        self.assertEqual((EXAMPLE/'LICENSE.txt').read_bytes(),(FIXTURE/'LICENSE.txt').read_bytes())
        self.assertTrue((EXAMPLE/'NOTICE.txt').read_bytes().startswith((FIXTURE/'NOTICE.txt').read_bytes()))
        frozen=json.loads((FIXTURE/'oracle.json').read_text())
        self.assertEqual(frozen['oracle_source_sha256'],sha(FIXTURE/'Oracle.java'))
        self.assertEqual(frozen['upstream_capture_sha256'],sha(FIXTURE/'upstream.json'))
        self.assertEqual(frozen['inputs'],cases())
        expected=[(t['name'],str(index),op['operation']) for t in cases() for index,op in enumerate(t['commands'])]
        self.assertEqual([(r['trace'],r['step'],r['operation']) for r in frozen['outputs']],expected)
        self.assertEqual(len(expected),995)
        for row in frozen['outputs']:
            self.assertFalse(row['full'])
            self.assertEqual(int(row['size']),len(row['contents']))
            self.assertLessEqual(int(row['size']),int(row['capacity']))
            self.assertEqual(row['empty'],not row['contents'])
            self.assertEqual(row['at_capacity'],row['size']==row['capacity'])
        selected=os.environ.get('NEX_JAVA_HOME')
        if selected:
            tools=Path(selected)/'bin';suffix='.exe' if os.name=='nt' else ''
            classes=self.root/'java';classes.mkdir()
            self.run_child([tools/('javac'+suffix),'-d',classes,
                *sorted((FIXTURE/'upstream').rglob('*.java')),FIXTURE/'Oracle.java'])
            result=subprocess.run([str(tools/('java'+suffix)),'-cp',str(classes),'Oracle'],
                input=protocol(),capture_output=True,text=True,encoding='utf-8',timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(list(map(json.loads,result.stdout.splitlines())),frozen['outputs'])
            print(json.dumps({'live_Java':True,'observations':995,
                'version':self.run_child([tools/('java'+suffix),'--version'])}))

    def test_original_Java_reference_native_and_strict_async_TypeScript(self):
        self.project(self.root,source())
        pin=sha(h.NEX);checked=self.cli('check')
        reference=self.cli('eval','--steps','80000000',timeout=180)
        lines=reference['stdout'].splitlines()
        self.assertEqual(lines[-1],'java-circular-fifo-oracle-ok')
        original=json.loads((FIXTURE/'oracle.json').read_text())['outputs']
        self.assertEqual(list(map(json.loads,lines[:-1])),original)
        native={}
        for profile in ('debug','release'):
            result=self.cli('run','--profile',profile,'--task-steps','80000000',
                            '--task-timeout-ms','60000','--task-workers','2',timeout=300)
            self.assertEqual((result['stdout'],result['stderr']),(reference['stdout'],''))
            native[profile]={'exit_code':result['exit_code'],
                'stdout_sha256':hashlib.sha256(result['stdout'].encode()).hexdigest(),
                'task_execution':result.get('task_execution')}
        folder=self.root/'typescript'
        self.cli('emit','--kind','typescript','--entry','main','--directory',folder)
        mapping=json.loads((folder/'nex-map.json').read_text())
        self.assertEqual(mapping['revision'],checked['revision'])
        self.assertEqual(mapping['schema'],'nex.typescript-map/4')
        self.strict_ts(folder)
        (folder/'package.json').write_text('{"type":"module"}\n')
        (folder/'driver.mjs').write_text("import {entry} from './program.ts';\n"
            "await entry({steps:80000000,timeoutMs:60000,workers:2});\n")
        actual=self.run_child([os.environ.get('NEX_NODE','node'),'--no-warnings',
            '--experimental-strip-types',folder/'driver.mjs'],180)
        self.assertEqual(actual,reference['stdout'])
        self.assertEqual(sha(h.NEX),pin)
        report={'schema':'nex.manual-java-port-agreement/1','ok':True,'language':'0.30',
            'toolchain_scope':'ordinary source program; no compiler or syntax change',
            'upstream':'Apache Commons Collections4.6.0 CircularFifoQueue',
            'compiler_sha256':pin,'revision':checked['revision'],'source_sha256':sha(self.file),
            'port_sha256':sha(EXAMPLE/'circular_fifo.nex'),'oracle_sha256':sha(FIXTURE/'oracle.json'),
            'traces':48,'observations':995,'source_reference_steps':reference['steps'],
            'native':native,'strict_executed_TypeScript':True,'async_map_schema':mapping['schema'],
            'generic_cell_identity_and_cooperative_tasks':True,
            'complete_Java_runtime_or_converter':False,'performance_claimed':False}
        destination=os.environ.get('NEX_JAVA_CIRCULAR_FIFO_REPORT')
        if destination:Path(destination).write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))

    def test_effects_types_wire_and_retained_language_selection(self):
        prefix='module rejected;import "./circular_fifo.nex" as fifo;'
        cases_to_reject=[
            ('state','0.30','fn main()->unit!{throw}{fifo::create<i64>(1);}',{'E_EFFECT'}),
            ('throw','0.30','fn main()->unit!{state}{fifo::create<i64>(1);}',{'E_EFFECT'}),
            ('element','0.30','fn main()->unit!{state,throw}{let q:fifo::Queue<i64>=fifo::create<i64>(1);fifo::offer(q,"wrong");}',{'E_TYPE'}),
            ('wire','0.30','fn main()->unit!{state,throw,io}{let q:fifo::Queue<i64>=fifo::create<i64>(1);print(encode_json(q));}',{'E_GENERIC_BOUND'}),
            ('retained028','0.28','fn main()->unit{}',{'E_TYPE','E_LANGUAGE_VERSION'}),
            ('retained029','0.29','fn main()->unit{}',{'E_TYPE','E_LANGUAGE_VERSION'})]
        for name,language,body,codes in cases_to_reject:
            with self.subTest(name=name):
                folder=self.root/name;self.project(folder,prefix+body,language)
                diagnostic=self.cli('check',cwd=folder,ok=False)
                self.assertIn(diagnostic['code'],codes)
                self.assertEqual(json.loads((folder/'nex.json').read_text())['language'],language)

    def test_example_aliases_and_source_tests(self):
        self.project(self.root,(EXAMPLE/'main.nex').read_text())
        self.assertEqual(self.cli('eval')['stdout'],'java-circular-fifo-ok\n')
        self.assertTrue(self.cli('test','--target','web')['ok'])

if __name__=='__main__':unittest.main()
