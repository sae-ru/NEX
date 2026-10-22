"""Actual raw compiler inputs, including fragmented nonseekable streams."""
import hashlib,json,os,subprocess,sys,tempfile,threading,unittest
from pathlib import Path

COMPILER=str(Path(sys.argv.pop(1)).resolve())
PROBE=str(Path(sys.argv.pop(1)).resolve())

class FrontendIO(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='nex-compiler-io-')
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)/'quoted " % \\ Я🧠'
        self.root.mkdir()

    def command(self,path):return [PROBE,str(path),json.dumps({'read_file':True})]
    def read(self,path):return subprocess.run(self.command(path),capture_output=True,timeout=20)
    def assert_bytes(self,observed,expected):
        self.assertEqual(len(observed),len(expected))
        self.assertTrue(observed==expected,'raw byte mismatch: '+hashlib.sha256(observed).hexdigest()+' != '+hashlib.sha256(expected).hexdigest())

    def test_all_octets_across_empty_exact_and_partial_blocks(self):
        for size in [0,1,255,65535,65536,65537,131072,131173,2097169]:
            with self.subTest(size=size):
                raw=(bytes(range(256))*(size//256+1))[:size]
                path=self.root/('binary-'+str(size));path.write_bytes(raw)
                p=self.read(path);self.assertEqual(p.returncode,0,p.stderr)
                self.assert_bytes(p.stdout,raw)

    def test_missing_and_failed_directory_reads_are_file_diagnostics(self):
        for path in [self.root/'absent',self.root/'absent-parent'/'file',self.root]:
            with self.subTest(path=str(path)):
                p=self.read(path);self.assertEqual(p.returncode,1,p.stderr)
                error=json.loads(p.stdout);self.assertEqual(error['code'],'E_FILE')
                self.assertIn('cannot read '+str(path),error['message'])

    @unittest.skipUnless(hasattr(os,'mkfifo'),'POSIX FIFO required')
    def test_fragmented_fifo_preserves_data_until_writer_closes(self):
        path=self.root/'stream';os.mkfifo(path)
        raw=bytes(range(256))*1100+b'\x00partial\xff\r\n'
        first=threading.Event();continued=threading.Event();errors=[]
        def writer():
            try:
                with path.open('wb',buffering=0) as f:
                    f.write(raw[:37]);first.set()
                    if not continued.wait(5):raise RuntimeError('reader coordination timed out')
                    for start,end in [(37,65531),(65531,65539),(65539,200003),(200003,len(raw))]:
                        data=memoryview(raw)[start:end]
                        while data:
                            written=f.write(data);data=data[written:]
            except BaseException as e:errors.append(repr(e));first.set()
        p=subprocess.Popen(self.command(path),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        thread=threading.Thread(target=writer);thread.start()
        try:
            self.assertTrue(first.wait(5),'FIFO writer did not start')
            with self.assertRaises(subprocess.TimeoutExpired):p.wait(timeout=0.05)
            continued.set()
            stdout,stderr=p.communicate(timeout=20)
            self.assertEqual(p.returncode,0,stderr);self.assert_bytes(stdout,raw)
        finally:
            continued.set()
            if p.poll() is None:p.kill();p.communicate()
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])

    def test_zero_sized_devices_and_linux_procfs(self):
        null=Path('/dev/null')
        if null.exists():
            p=self.read(null);self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,b'')
        command_line=Path('/proc/self/cmdline')
        if command_line.exists():
            argv=self.command(command_line);p=subprocess.run(argv,capture_output=True,timeout=20)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assert_bytes(p.stdout,b'\x00'.join(os.fsencode(v) for v in argv)+b'\x00')

    def test_source_utf8_boundary_preserves_all_backends_and_rejections(self):
        prefix=b'module boundary;\n//'
        before=b'\npub fn text()->str{return "'
        emoji='🧠'.encode()
        raw=prefix+b'x'*(65534-len(prefix)-len(before))+before+emoji+b'";}\n'
        raw+=b'fn main()->unit!{io}{print(text());}\n'
        raw+=b'test fn edge()->unit{assert(len(text())==1);assert(len(utf8_bytes(text()))==4);}\n'
        self.assertEqual(raw.index(emoji),65534)
        source=self.root/'boundary.nex';source.write_bytes(raw)
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.19','entry':'boundary.nex'}))
        for args in [('check',),('eval',),('run','--profile','release'),('test',),('test','--target','web')]:
            with self.subTest(command=args):
                p=subprocess.run([COMPILER,*args,'--json'],cwd=self.root,capture_output=True,text=True,timeout=60)
                self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                result=json.loads(p.stdout)
                if args[0] in ['eval','run']:self.assertEqual(result['stdout'],'🧠\n')
        source.write_bytes(raw.replace(emoji,b'\xf0\x28\x8c\x28'))
        p=subprocess.run([COMPILER,'check','--json'],cwd=self.root,capture_output=True,text=True,timeout=20)
        self.assertNotEqual(p.returncode,0);self.assertEqual(json.loads(p.stdout)['code'],'E_UTF8')

if __name__=='__main__':unittest.main()
